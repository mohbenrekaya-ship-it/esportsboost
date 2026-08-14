# -*- coding: utf-8 -*-
"""The guides-mail store behind the free-guides landing (design_handoff_free_guides).

The lead form on `/guides.html` asks for one email to send the two field guides
to. This is where that address is kept, and the `/ops` **Guides mails** tab is
where it is read. It is a deliberate sibling of `accounts.py`: same house rules
(stdlib only, no build step, Upstash Redis in prod / an NDJSON file in dev), same
public-write / gated-read shape, and a **separate store** — a guides subscriber is
not a header sign-up, and the two lists have different meanings and different
consents.

Load-bearing rules, the same ones accounts.py keeps:

  * **A separate store from analytics AND from accounts.** analytics is anonymous
    by construction (`esb:ev` / `analytics.ndjson`); an email in it would break
    the guarantee its header makes. accounts is `esb:accounts`. This is
    `esb:guides` / `guides.ndjson`. It reuses only analytics' Upstash *transport*
    (`_upstash`) and store selection, never its data. Do not merge them.
  * **`POST /api/guides` is public and unauthenticated**, like `/api/collect` and
    `/api/account`: the form is on a public page. Everything is length-capped and
    validated in `clean_lead()`; nothing is stored that did not survive it, and
    the list is read only through the password-gated `/ops` `guides` action.
  * **One address, one row.** `append()` dedupes on the lower-cased email, so a
    repeat submission is dropped and the first wins — the same integrity property
    accounts.py has, so the ops repeat count should read zero.
  * **No password, ever.** Unlike accounts this holds no credential — it is purely
    a mailing list. `email`, the guides they picked, whether they opted into the
    monthly mail, and the resolved country. Nothing that authenticates anyone.
  * **Restart the server after touching this file.** `/api/guides` lives in
    `serve.py` (and the `guides` ops action in `ops.py`); the routes only reload
    on a process restart — there is no watcher.
"""
import json
import os
import re
import time

import analytics
import geo

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 4 * 1024
MAX_LEADS = int(os.environ.get("GUIDES_MAX", "50000") or 50000)
MAX_EMAIL = 160
MAX_GUIDES = 120            # the joined key list ("lol,val") is tiny; cap anyway

LIST_KEY = "esb:guides"
# One address subscribes once. Mirrors the emails in LIST_KEY for an O(1)
# uniqueness check on the Upstash path — same pattern as accounts.EMAIL_KEY.
EMAIL_KEY = "esb:guides:emails"

# Loose shape check, not an MX lookup — reject the obvious junk, cap the length.
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,128}\.[A-Za-z]{2,24}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# The guide keys are data.py's GUIDES item keys ("lol", "val"); accept a short
# comma list of slug-ish tokens and nothing else.
_GUIDES_RE = re.compile(r"^[a-z0-9,_-]{0,%d}$" % MAX_GUIDES)


def log_path():
    return os.environ.get("GUIDES_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "guides.ndjson")


def _s(v, n):
    """Trim to a string, strip control chars, cap length."""
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


# ══════════════════════════════════════════════════════════════════════════
#  store — mirrors accounts.append/read/clear/count against a separate key
# ══════════════════════════════════════════════════════════════════════════
def _file_emails():
    return {r.get("email") for r in read() if r.get("email")}


def append(rows):
    """Persist cleaned leads, **one row per email**. Returns the number of NEW
    rows written; a submission whose email is already stored is dropped, and
    duplicates inside one batch collapse to the first. Never raises: a lost lead
    must not turn into a 500 on a page the visitor is looking at.
    """
    if not rows:
        return 0
    up = analytics.upstash_config()[0]
    seen, new = set(), []

    if up:
        for r in rows:
            e = r.get("email")
            if not e or e in seen:
                continue
            try:
                res = analytics._upstash([["SISMEMBER", EMAIL_KEY, e]])
                if res and res[0]:
                    continue                    # already subscribed
            except analytics.StoreError:
                pass          # can't verify → allow rather than lose the lead
            seen.add(e)
            new.append(r)
    else:
        existing = _file_emails()
        for r in rows:
            e = r.get("email")
            if not e or e in seen or e in existing:
                continue
            seen.add(e)
            new.append(r)

    if not new:
        return 0
    lines = [json.dumps(r, separators=(",", ":")) for r in new]

    if up:
        try:
            cmds = [["LPUSH", LIST_KEY] + lines,
                    ["LTRIM", LIST_KEY, 0, MAX_LEADS - 1]]
            cmds += [["SADD", EMAIL_KEY, r["email"]] for r in new]
            analytics._upstash(cmds)
            return len(lines)
        except analytics.StoreError:
            return 0
    try:
        with open(log_path(), "a") as f:
            f.write("\n".join(lines) + "\n")
        return len(lines)
    except OSError:
        return 0


def read(limit=MAX_LEADS):
    """Return up to `limit` stored leads, newest first."""
    limit = max(1, min(int(limit or MAX_LEADS), MAX_LEADS))
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["LRANGE", LIST_KEY, 0, limit - 1]])
        except analytics.StoreError:
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
            r = json.loads(row)
        except (ValueError, TypeError):
            continue
        if isinstance(r, dict) and r.get("email"):
            out.append(r)
    return out


def clear():
    """Wipe the list. Used by tooling; never exposed over HTTP."""
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["DEL", LIST_KEY], ["DEL", EMAIL_KEY]])
        except analytics.StoreError:
            return False
        return True
    try:
        os.remove(log_path())
    except OSError:
        pass
    return True


def count():
    if analytics.upstash_config()[0]:
        try:
            return int((analytics._upstash([["LLEN", LIST_KEY]]) or [0])[0] or 0)
        except (analytics.StoreError, TypeError, ValueError):
            return 0
    try:
        with open(log_path()) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


# ══════════════════════════════════════════════════════════════════════════
#  ingest
# ══════════════════════════════════════════════════════════════════════════
def clean_lead(body, now, ctx):
    """Validate one submission into a stored row, or None.

    Stored keys: `email`, `guides` (comma-joined guide keys, e.g. "lol,val"),
    `optin` (1 when they asked for the monthly mail, else 0), `ts`, `co`
    (country), `cosrc` (which signal resolved it), and `syn` only when seeded.
    """
    if not isinstance(body, dict):
        return None
    email = _s(body.get("email"), MAX_EMAIL).lower()
    if not _EMAIL_RE.match(email):
        return None
    guides = _s(body.get("guides"), MAX_GUIDES).lower()
    if not _GUIDES_RE.match(guides):
        guides = ""
    row = {
        "email": email,
        "guides": guides,
        "optin": 1 if body.get("optin") in (1, True, "1", "true") else 0,
        "ts": now,
        "co": ctx.get("co", ""),
        "cosrc": ctx.get("cosrc", ""),
    }
    # Passthrough only — the public endpoint never sets it; tooling does, and the
    # ops banner keys off it exactly like the analytics store's `syn`.
    if body.get("syn") in (1, True):
        row["syn"] = 1
    return row


def process_lead(raw, header_get):
    """POST /api/guides → (status, payload).

    Body: {"email", "guides"?, "optin"?, "tz"?, "lang"?}. Country is resolved
    server-side from the edge header, then the browser timezone, then the locale
    — never trusted from the body, never from an IP lookup.

    Responses:
      · valid, new email → `(200, {"stored": True, "email"})`, row persisted.
      · valid, email already subscribed → `(200, {"stored": False, "email"})`.
      · invalid email → `(400, {"error": "email"})`.
      · unparseable / oversized body → `(204, None)`.

    Always answers even on a store failure — a lost lead must not surface as an
    error on the page the visitor is looking at.
    """
    if not raw or len(raw) > MAX_BODY:
        return 204, None
    try:
        body = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return 204, None
    if not isinstance(body, dict):
        return 204, None

    get = header_get or (lambda *_a, **_k: "")
    edge = _s(get("x-vercel-ip-country") or "", 2).upper()
    tz = _s(body.get("tz"), 64)
    lang = _s(body.get("lang"), 12)
    ctx = {
        "co": geo.country(edge, tz, lang),
        "cosrc": geo.source(edge, tz, lang),
    }
    row = clean_lead(body, int(time.time()), ctx)
    if row is None:
        return 400, {"error": "email"}
    n = append([row])
    return 200, {"stored": bool(n), "email": row["email"]}


# ══════════════════════════════════════════════════════════════════════════
#  aggregation — what /ops reads
# ══════════════════════════════════════════════════════════════════════════
RECENT_CAP = 300      # rows shipped to the console; the list is a mailing list


def summary(days=30, now=None):
    """The Guides mails panel's payload: totals, a per-day series, a per-guide
    split, a country split and the most recent rows (capped, newest first)."""
    now = int(now or time.time())
    rows = read()
    since = now - days * 86400

    total = len(rows)
    window = [r for r in rows if int(r.get("ts") or 0) >= since]
    synthetic = sum(1 for r in rows if r.get("syn"))
    optins = sum(1 for r in rows if r.get("optin"))

    day = now - 86400
    week = now - 7 * 86400
    last_24h = sum(1 for r in rows if int(r.get("ts") or 0) >= day)
    last_7d = sum(1 for r in rows if int(r.get("ts") or 0) >= week)

    # Per-day counts across the selected window, oldest → newest, no gaps.
    by_day = {}
    for r in window:
        d = time.strftime("%Y-%m-%d", time.gmtime(int(r.get("ts") or 0)))
        by_day[d] = by_day.get(d, 0) + 1
    series = []
    for i in range(days - 1, -1, -1):
        d = time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))
        series.append({"date": d, "count": by_day.get(d, 0)})

    # Which guides they asked for — one lead can pick both, so this counts picks,
    # not leads, and the two need not sum to `total`.
    by_guide = {}
    for r in rows:
        for key in (r.get("guides") or "").split(","):
            key = key.strip()
            if key:
                by_guide[key] = by_guide.get(key, 0) + 1
    guides = sorted(
        ({"key": k, "count": v} for k, v in by_guide.items()),
        key=lambda x: (-x["count"], x["key"]))

    by_country = {}
    for r in window:
        co = r.get("co") or "??"
        by_country[co] = by_country.get(co, 0) + 1
    countries = sorted(
        ({"code": k, "count": v} for k, v in by_country.items()),
        key=lambda x: (-x["count"], x["code"]))

    seen = {}
    for r in rows:
        seen[r["email"]] = seen.get(r["email"], 0) + 1
    unique = len(seen)
    repeat = sum(1 for c in seen.values() if c > 1)

    recent = [{
        "email": r["email"], "guides": r.get("guides", ""),
        "optin": 1 if r.get("optin") else 0, "ts": int(r.get("ts") or 0),
        "co": r.get("co", ""), "cosrc": r.get("cosrc", ""),
        "syn": 1 if r.get("syn") else 0,
    } for r in rows[:RECENT_CAP]]

    return {
        "total": total, "unique": unique, "repeat": repeat,
        "in_window": len(window), "last_24h": last_24h, "last_7d": last_7d,
        "optins": optins, "synthetic": synthetic, "days": days,
        "series": series, "guides": guides, "countries": countries,
        "recent": recent, "store": analytics.store_name(),
    }
