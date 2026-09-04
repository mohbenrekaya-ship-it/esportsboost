# -*- coding: utf-8 -*-
"""First-party analytics: the event store and the ingest endpoint.

The sales site already emits a clean funnel (`view_item` → `begin_checkout` →
`purchase`, see public/assets/js/app.js) into `window.dataLayer`, but nothing
ever read that array. This module is the other end of the pipe: it takes those
events from `/api/collect` and puts them somewhere they survive a request.

Two stores, chosen by environment — same interface, no third-party packages:

  * **Upstash Redis** over its REST API (stdlib `urllib`) when
    `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` are set. This is the
    production path: Vercel's filesystem is ephemeral, so a file would lose
    every event the moment the function froze.
  * **A local NDJSON file** otherwise, so `serve.py` collects for real during
    development with nothing to configure.

Privacy: the schema is anonymous by construction. No IP is stored, no cookie is
set, no field carries a name or an email — the visitor id is a random string the
browser mints for itself. Country comes from the edge header Vercel already
attaches, never from an IP lookup we perform. That keeps this out of
consent-banner territory, which is also why it is worth defending: do not add a
field here that could identify a person.

`/api/collect` is a public, unauthenticated endpoint — anything reaching it is
hostile until proven otherwise. Everything is allowlisted, length-capped and
type-checked below; nothing is stored that did not survive `_clean_event()`.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import geo

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 64 * 1024      # a beacon payload is tiny; cap it hard
MAX_BATCH = 20            # events per POST
MAX_EVENTS = int(os.environ.get("ANALYTICS_MAX_EVENTS", "50000") or 50000)
HTTP_TIMEOUT = 5

LIST_KEY = "esb:ev"

# Every event the client is allowed to name. An unknown name is dropped rather
# than stored — otherwise the store is a free-form public write target.
ALLOWED_EVENTS = {
    "session_start", "page_view", "view_item", "configure", "select_promotion",
    # The mystery-discount modal was shown. The mystery store only records cards
    # people actually opened, so without this there is no denominator for the
    # flow — "N leads" reads as a win with no idea what it cost in interruptions.
    "view_promotion",
    "add_to_cart", "begin_checkout", "add_payment_info", "purchase",
    "generate_lead", "checkout_error", "js_error", "scroll", "engage",
    # Emitted once per page as the visitor leaves — pagehide, or the tab going
    # hidden, whichever fires first. It is what gives a session a real duration:
    # every other event on a landing page fires within milliseconds of load, so
    # without it a two-minute read and an instant bounce both record 0s, which
    # is the one distinction paid traffic has to be judged on. `meta.sec` is the
    # dwell the page measured for itself.
    "page_exit",
    # The account flow, end to end: the panel opening, a departure for an OAuth
    # provider, the two outcomes, the sign-out, and every refusal in between.
    # Without these a session that creates an account looks exactly like one
    # that browsed past the header — the sign-up shows up in the /ops Accounts
    # list with no way back to what the visitor was doing when they made it.
    # These record THAT an account step happened, never WHOSE: the email and the
    # name live in the accounts store, which is a separate store for precisely
    # that reason. Nothing below may ever carry either — see the note at the top
    # of this file, and `meta` is capped and stringified like every other field.
    "auth_open", "oauth_start", "sign_up", "login", "logout", "auth_error",
    # The accounts shop (`/accounts`), which is NOT a configurator and so fires
    # none of the funnel's own events. Between `page_view` and `begin_checkout`
    # that page emitted nothing at all, which made three very different visits
    # indistinguishable in /ops: somebody who read the hero and left, somebody
    # who picked a server and balked at the board, and somebody whose browser
    # loaded the HTML but never mounted the shop. In order:
    #   account_shop    the shop mounted and is interactive (the denominator,
    #                   and the one thing `page_view` cannot say — a page_view
    #                   on /accounts with no account_shop behind it is a broken
    #                   render, not a bounce)
    #   account_server  step 1 answered: a shard was picked
    #   account_tiers   step 2 on screen with real cards, once per shard
    # `meta` carries the shard code and two counts (`tiers`, `stock`) — product
    # facts about the page, never about the person, like everything else here.
    "account_shop", "account_server", "account_tiers",
}

# Configurator fields mirrored from the order state in app.js. Anything else in
# a posted `cfg` is discarded.
CFG_STR = ("game", "service", "from", "to", "mode", "region", "promo", "summary")
CFG_NUM = ("total", "wins", "placements", "steps")

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ══════════════════════════════════════════════════════════════════════════
#  stores
# ══════════════════════════════════════════════════════════════════════════
def upstash_config():
    """(url, token) when Upstash is configured, else (None, None)."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    return (url, token) if url and token else (None, None)


def store_name():
    return "upstash" if upstash_config()[0] else "file"


def log_path():
    return os.environ.get("ANALYTICS_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "analytics.ndjson")


class StoreError(Exception):
    pass


def _upstash(commands):
    """Run a pipeline of Redis commands against Upstash's REST API.

    `commands` is a list of arg-lists, e.g. [["LPUSH", key, val], ["LTRIM", …]].
    Returns the list of results. Raises StoreError on any transport failure —
    callers decide whether that is fatal (reading) or swallowed (writing).
    """
    url, token = upstash_config()
    if not url:
        raise StoreError("Upstash not configured")
    body = json.dumps(commands).encode()
    req = urllib.request.Request(
        url + "/pipeline", data=body, method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            out = json.loads(r.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        raise StoreError("Upstash HTTP %s: %s" % (e.code, e.read()[:200]))
    except Exception as e:                                    # noqa: BLE001
        raise StoreError("Upstash unreachable: %s" % e)
    for item in out if isinstance(out, list) else []:
        if isinstance(item, dict) and item.get("error"):
            raise StoreError(str(item["error"])[:200])
    return [i.get("result") if isinstance(i, dict) else i
            for i in (out if isinstance(out, list) else [])]


def append(events):
    """Persist a list of cleaned events. Never raises: a dropped analytics
    event must never turn into a 500 on a page the customer is looking at."""
    if not events:
        return 0
    lines = [json.dumps(e, separators=(",", ":")) for e in events]
    if upstash_config()[0]:
        try:
            # Newest-first list, trimmed to the cap so the store is bounded.
            _upstash([["LPUSH", LIST_KEY] + lines,
                      ["LTRIM", LIST_KEY, 0, MAX_EVENTS - 1]])
            return len(lines)
        except StoreError:
            return 0
    try:
        with open(log_path(), "a") as f:
            f.write("\n".join(lines) + "\n")
        return len(lines)
    except OSError:
        return 0


def read(limit=MAX_EVENTS):
    """Return up to `limit` stored events, newest first."""
    limit = max(1, min(int(limit or MAX_EVENTS), MAX_EVENTS))
    if upstash_config()[0]:
        try:
            res = _upstash([["LRANGE", LIST_KEY, 0, limit - 1]])
        except StoreError:
            return []
        rows = res[0] if res else []
    else:
        try:
            with open(log_path()) as f:
                rows = f.read().splitlines()
        except OSError:
            return []
        rows = rows[-limit:][::-1]          # file is oldest-first; flip it
    out = []
    for row in rows or []:
        try:
            ev = json.loads(row)
        except (ValueError, TypeError):
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def clear():
    """Wipe the store. Used by the seeder; never exposed over HTTP."""
    if upstash_config()[0]:
        try:
            _upstash([["DEL", LIST_KEY]])
        except StoreError:
            return False
        return True
    try:
        os.remove(log_path())
    except OSError:
        pass
    return True


def count():
    if upstash_config()[0]:
        try:
            res = _upstash([["LLEN", LIST_KEY]])
        except StoreError:
            return 0
        return int(res[0] or 0) if res else 0
    try:
        with open(log_path()) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ══════════════════════════════════════════════════════════════════════════
#  ingest
# ══════════════════════════════════════════════════════════════════════════
def _s(v, n=120):
    """Any client value → a bounded, control-char-free string."""
    if v is None or isinstance(v, (dict, list)):
        return ""
    return _CTRL_RE.sub("", str(v))[:n].strip()


def _num(v, lo=-1e9, hi=1e9):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):   # NaN / ±inf
        return None
    return max(lo, min(hi, round(f, 2)))


def _id(v):
    v = _s(v, 40)
    return v if _ID_RE.match(v) else ""


def device_class(ua):
    ua = (ua or "").lower()
    if "ipad" in ua or ("android" in ua and "mobile" not in ua) or "tablet" in ua:
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    return "desktop"


def _clean_cfg(cfg):
    if not isinstance(cfg, dict):
        return None
    out = {}
    for k in CFG_STR:
        v = _s(cfg.get(k), 80)
        if v:
            out[k] = v
    for k in CFG_NUM:
        v = _num(cfg.get(k), 0, 100000)
        if v is not None:
            out[k] = v
    addons = cfg.get("addons")
    if isinstance(addons, list):
        out["addons"] = [_s(a, 40) for a in addons[:10] if _s(a, 40)]
    if cfg.get("invalid"):
        out["invalid"] = True
    return out or None


def _clean_event(raw, now, ctx):
    """One posted event → the stored record, or None if it fails the gate."""
    if not isinstance(raw, dict):
        return None
    name = _s(raw.get("e") or raw.get("event"), 40)
    if name not in ALLOWED_EVENTS:
        return None
    anon, sess = _id(raw.get("a")), _id(raw.get("s"))
    if not anon or not sess:
        return None

    ev = {"t": now, "e": name, "a": anon, "s": sess}

    seq = _num(raw.get("n"), 0, 10000)
    if seq is not None:
        ev["n"] = int(seq)
    for key, src, n in (("p", "p", 160), ("ref", "ref", 80), ("src", "src", 60),
                        ("med", "med", 40), ("cmp", "cmp", 60), ("lang", "lang", 12),
                        ("tz", "tz", 48)):
        v = _s(raw.get(src), n)
        if v:
            ev[key] = v
    val = _num(raw.get("val"), 0, 100000)
    if val is not None:
        ev["val"] = val
    cfg = _clean_cfg(raw.get("cfg"))
    if cfg:
        ev["cfg"] = cfg
    meta = raw.get("meta")
    if isinstance(meta, dict):
        m = {}
        for k in list(meta)[:8]:
            key = _s(k, 24)
            v = meta[k]
            if key:
                m[key] = _num(v, -1e9, 1e9) if isinstance(v, (int, float)) else _s(v, 160)
        if m:
            ev["meta"] = m

    # Server-side context — the client cannot set or spoof these.
    ev["dev"] = ctx["dev"]
    # Country is resolved here rather than trusted from the body: the edge
    # header wins, and the browser's timezone/locale only fill in behind it.
    co = geo.country(ctx["co"], ev.get("tz"), ev.get("lang"))
    if co:
        ev["co"] = co
        ev["cosrc"] = geo.source(ctx["co"], ev.get("tz"), ev.get("lang"))
    return ev


def process_collect(raw, header_get):
    """POST /api/collect → (status, payload).

    Body is `{"events": [...]}` or a bare list. Returns 204 with an empty body
    on success — the browser's `sendBeacon` ignores the response either way, and
    a 204 keeps the endpoint useless as an oracle.
    """
    if not raw or len(raw) > MAX_BODY:
        return 204, None
    try:
        body = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return 204, None
    events = body.get("events") if isinstance(body, dict) else body
    if not isinstance(events, list):
        return 204, None

    get = header_get or (lambda *_a, **_k: "")
    country = _s(get("x-vercel-ip-country") or "", 2).upper()
    ctx = {
        "dev": device_class(get("user-agent") or ""),
        "co": country if len(country) == 2 and country.isalpha() else "",
    }
    now = int(time.time())
    clean = [c for c in (_clean_event(e, now, ctx) for e in events[:MAX_BATCH]) if c]
    append(clean)
    return 204, None
