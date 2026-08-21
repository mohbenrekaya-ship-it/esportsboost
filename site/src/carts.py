# -*- coding: utf-8 -*-
"""Abandoned checkout capture — the store behind the /ops "Carts" tab.

The **fifth sibling** of `analytics.py`, `accounts.py`, `boosters.py` and
`orders.py`: same house rules (stdlib only, no build step, Upstash Redis in prod
/ an NDJSON file in dev), same **separate store** (`esb:carts` / `carts.ndjson`,
never another store's key), reusing only analytics' Upstash *transport*.

Why it exists: `/ops` already lists abandoned configurations, but the analytics
store is sworn to hold **no PII**, so those rows carry no email and nobody can be
contacted. This store is where the email a buyer typed into the checkout form is
kept, next to the configuration they were about to buy.

Where it differs from its siblings — and the one reason it is not an append-only
list like the other four:

  * **Rows are mutated, not just appended.** A cart moves `pending → mailed →
    recovered` (or `expired`), so the Upstash side is a **HASH** keyed by token
    (`HSET esb:carts <token> <json>`) rather than a LIST. `LPUSH` + `LTRIM` can
    append a lot cheaply but cannot rewrite row 40 in place, and a recovery
    mailer that cannot mark a row as sent will mail the same person every sweep.
  * **The token is the discount.** `data.py`'s `PROMOS` is shipped to the browser
    in `data.js`, so a static recovery code would be public the day it ships and
    everyone would have 30% off forever. Each cart instead carries its own
    unguessable single-use token, resolved **server-side only** against this
    store. `TOKEN_BYTES` is what makes it unguessable; do not shorten it.
  * **It holds PII** (an email, a country), like `accounts.py` and `orders.py` —
    so the `/ops` payload is fetched on demand rather than bundled into every
    dashboard refresh.

A cart row is the configuration the buyer had built when they gave us their
address, so a recovery mail can name the exact climb and `pricing.quote()` can
re-price it server-side at send time. The **price is never trusted from the
client** — same rule as `payments.build_session()`; `total` here is only ever a
display figure recomputed on read.
"""
import json
import os
import re
import secrets
import time

import analytics   # Upstash transport + store selection only — never its data

# ── limits ────────────────────────────────────────────────────────────────
MAX_CARTS = int(os.environ.get("CARTS_MAX", "5000") or 5000)
MAX_STR = 120
MAX_EMAIL = 160
MAX_ADDONS = 8
RECENT_CAP = 500

LIST_KEY = "esb:carts"          # HASH: token -> row json

# How long after capture a cart counts as abandoned and becomes mailable.
# The buyer asked for 30 minutes; the sweep is what actually enforces it.
DELAY_SECS = int(os.environ.get("CART_DELAY_SECS", "1800") or 1800)
# A recovery token stops working after this. A discount that never expires is a
# discount that ends up on a coupon site.
TOKEN_TTL = int(os.environ.get("CART_TOKEN_TTL", str(7 * 86400)) or 7 * 86400)
# The recovery discount, as a fraction. Replaces the sitewide sale rather than
# stacking with it — see pricing.resolve_promo().
RECOVERY_PCT = float(os.environ.get("CART_RECOVERY_PCT", "0.30") or 0.30)
TOKEN_BYTES = 8                 # ~13 chars of base32 — not guessable

STATUSES = ("pending", "mailed", "recovered", "expired")

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")
TOKEN_RE = re.compile(r"^BACK-[A-Z0-9]{8,20}$")


def log_path():
    return os.environ.get("CARTS_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "carts.ndjson")


def _s(v, n=MAX_STR):
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def new_token():
    """An unguessable, single-use recovery code. Base32 so it survives being
    read aloud, pasted from an email client, or typed in the promo box."""
    raw = secrets.token_bytes(TOKEN_BYTES)
    import base64
    body = base64.b32encode(raw).decode().rstrip("=")
    return "BACK-" + body


# ══════════════════════════════════════════════════════════════════════════
#  validation — everything a public endpoint writes goes through here
# ══════════════════════════════════════════════════════════════════════════
def clean_cart(body, now=None, country=""):
    """Validate one captured checkout. Returns a row dict or None.

    Mirrors `accounts.clean_signup()` / `orders.clean_order()`: allowlisted keys,
    length caps, no field the caller can use to inflate anything. The price is
    **not** read from the body — it is recomputed on read, so a tampered total
    can only ever mis-display in /ops, never mis-charge.
    """
    if not isinstance(body, dict):
        return None
    email = _s(body.get("email"), MAX_EMAIL).lower()
    if not email or not _EMAIL_RE.match(email):
        return None

    addons = body.get("addons")
    if not isinstance(addons, list):
        addons = []
    addons = [_s(a, 40) for a in addons[:MAX_ADDONS] if a]

    now = _int(now or time.time())
    return {
        "email": email,
        "at": now,
        "updated": now,
        "status": "pending",
        "game": _s(body.get("game")),
        "service": _s(body.get("service"), 20),
        "from": _s(body.get("from"), 40),
        "to": _s(body.get("to"), 40),
        "mode": _s(body.get("mode"), 20),
        "region": _s(body.get("region"), 40),
        "addons": addons,
        "wins": max(0, min(_int(body.get("wins"), 0), 99)),
        "placements": max(0, min(_int(body.get("placements"), 0), 99)),
        "unranked": bool(body.get("unranked")),
        "booster": _s(body.get("booster"), 40),
        "bundle": _s(body.get("bundle"), 60),
        "country": _s(country, 4).upper(),
        "session": _s(body.get("session"), 40),
        "mailed_at": 0,
        "recovered_at": 0,
        "order_id": "",
    }


# ══════════════════════════════════════════════════════════════════════════
#  store
# ══════════════════════════════════════════════════════════════════════════
def _up():
    return analytics.upstash_config()[0]


def _read_file():
    """Every row in the file store, last write per token winning."""
    out = {}
    try:
        with open(log_path()) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                t = r.get("token")
                if t:
                    out[t] = r
    except OSError:
        return {}
    return out


def _write_file(rows):
    try:
        with open(log_path(), "w") as f:
            for r in rows.values():
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def put(row):
    """Insert or replace one cart by its token. Never raises — a lost capture
    must not 500 the checkout page the buyer is standing on."""
    token = row.get("token")
    if not token:
        return False
    row["updated"] = _int(time.time())
    blob = json.dumps(row, separators=(",", ":"))
    if _up():
        try:
            analytics._upstash([["HSET", LIST_KEY, token, blob]])
            return True
        except analytics.StoreError:
            return False
    rows = _read_file()
    rows[token] = row
    return _write_file(rows)


def get(token):
    """One cart by token, or None."""
    token = _s(token, 40).upper()
    if not TOKEN_RE.match(token):
        return None
    if _up():
        try:
            res = analytics._upstash([["HGET", LIST_KEY, token]])
        except analytics.StoreError:
            return None
        raw = res[0] if res else None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    return _read_file().get(token)


def read(limit=MAX_CARTS):
    """Every cart, newest first."""
    if _up():
        try:
            res = analytics._upstash([["HGETALL", LIST_KEY]])
        except analytics.StoreError:
            return []
        flat = res[0] if res else []
        rows = []
        # HGETALL comes back as [field, value, field, value, ...]
        if isinstance(flat, dict):
            items = flat.values()
        else:
            items = (flat or [])[1::2]
        for raw in items:
            try:
                rows.append(json.loads(raw))
            except (ValueError, TypeError):
                continue
    else:
        rows = list(_read_file().values())
    rows.sort(key=lambda r: -_int(r.get("at")))
    return rows[:limit]


def find_pending(email):
    """The open cart for an address, if there is one — so a buyer editing the
    checkout form updates their cart instead of minting a new one per keystroke
    batch, and one abandoned checkout is one recovery mail."""
    email = _s(email, MAX_EMAIL).lower()
    for r in read():
        if r.get("email") == email and r.get("status") in ("pending", "mailed"):
            return r
    return None


def mark(token, **fields):
    """Patch one cart in place. Returns the updated row or None."""
    row = get(token)
    if not row:
        return None
    row.update(fields)
    put(row)
    return row


def due(now=None, delay=None, limit=200):
    """Carts that are ready for a recovery mail: still `pending`, captured at
    least `delay` ago, and not older than the token's own lifetime (there is no
    point mailing a discount that is already dead)."""
    now = _int(now or time.time())
    delay = DELAY_SECS if delay is None else delay
    out = []
    for r in read():
        if r.get("status") != "pending":
            continue
        at = _int(r.get("at"))
        if now - at < delay:
            continue
        if now - at > TOKEN_TTL:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def redeemable(token, now=None):
    """The row a recovery token still entitles to a discount, or None.

    Single-use and time-boxed: a cart that has already been recovered, or whose
    token has aged past `TOKEN_TTL`, buys nothing. This is the **only** place the
    recovery percentage is resolved — never `D.PROMOS`, which ships to the
    browser.
    """
    row = get(token)
    if not row:
        return None
    if row.get("status") == "recovered":
        return None
    now = _int(now or time.time())
    if now - _int(row.get("at")) > TOKEN_TTL:
        return None
    return row


def recover(token, order_id="", now=None):
    """Burn a token when the order it belongs to is paid."""
    return mark(token, status="recovered", order_id=_s(order_id, 40),
                recovered_at=_int(now or time.time()))


def _display_price(row):
    """What a cart is worth, recomputed from its stored configuration — never a
    trusted total (the store keeps the config, not a price the client sent). The
    normal figure and the recovery figure, whole USD, or (0, 0) if the config no
    longer prices."""
    try:
        import recovery
        now_q, off_q = recovery.price_pair(row)
        if not now_q:
            return 0, 0
        return _int(now_q.get("total")), _int(off_q.get("total"))
    except Exception:                                          # noqa: BLE001
        return 0, 0


def _climb(row):
    """A one-line description of the order, from the stored config."""
    svc = row.get("service") or "division"
    if svc in ("wins", "placements"):
        n = row.get(svc) or 0
        noun = "net win" if svc == "wins" else "placement"
        return "%d %s%s" % (n, noun, "" if n == 1 else "s")
    if svc == "coaching":
        return "coaching"
    a, b = row.get("from") or "", row.get("to") or ""
    return ("%s → %s" % (a, b)).strip(" →") or (row.get("game") or "—")


def summary(days=30, now=None):
    """The Carts panel's list payload: totals, a status split, per-game and
    per-country breakdowns, the recovery figures (how many came back and what
    that was worth), and a recent list. Fetched on demand like Accounts and
    Orders — it holds PII, so it is never bundled into the dashboard refresh.
    """
    days = max(1, min(_int(days, 30), 365))
    now = _int(now or time.time())
    cutoff = now - days * 86400
    rows = [r for r in read() if _int(r.get("at")) >= cutoff]

    by_status = {s: 0 for s in STATUSES}
    by_game, by_country = {}, {}
    recovered_value = potential_value = 0
    recent = []
    for r in sorted(rows, key=lambda r: -_int(r.get("at"))):
        st = r.get("status", "pending")
        by_status[st] = by_status.get(st, 0) + 1

        normal, offer = _display_price(r)
        potential_value += normal
        if st == "recovered":
            recovered_value += normal

        g = r.get("game") or "—"
        gs = by_game.setdefault(g, {"game": g, "count": 0, "recovered": 0})
        gs["count"] += 1
        if st == "recovered":
            gs["recovered"] += 1

        c = r.get("country") or "—"
        by_country[c] = by_country.get(c, 0) + 1

        if len(recent) < RECENT_CAP:
            recent.append({
                "token": r.get("token", ""),
                "email": r.get("email", ""),
                "at": _int(r.get("at")),
                "updated": _int(r.get("updated")),
                "mailed_at": _int(r.get("mailed_at")),
                "recovered_at": _int(r.get("recovered_at")),
                "status": st,
                "game": g,
                "service": r.get("service", "division"),
                "summary": _climb(r),
                "mode": r.get("mode", ""),
                "region": r.get("region", ""),
                "country": c,
                "value": normal,
                "offer": offer,
                "order_id": r.get("order_id", ""),
                "session": r.get("session", ""),
                "syn": 1 if r.get("syn") else 0,
            })

    total = len(rows)
    recovered = by_status.get("recovered", 0)
    mailed = by_status.get("mailed", 0)
    # Recovery rate is of the carts we actually mailed (mailed → recovered), not
    # of every capture — an anonymous cart nobody could mail should not drag the
    # rate down.
    mailed_or_recovered = mailed + recovered
    rate = round(100.0 * recovered / mailed_or_recovered, 1) if mailed_or_recovered else 0.0

    games = sorted(by_game.values(), key=lambda x: -x["count"])
    countries = sorted(
        ({"country": k, "count": v} for k, v in by_country.items()),
        key=lambda x: -x["count"])

    return {
        "total": total,
        "days": days,
        "recovered": recovered,
        "recovered_value": recovered_value,
        "potential_value": potential_value,
        "recovery_rate": rate,
        "recovery_pct": RECOVERY_PCT,
        "delay_mins": DELAY_SECS // 60,
        "synthetic": sum(1 for r in rows if r.get("syn")),
        "statuses": [{"status": s, "count": by_status.get(s, 0)} for s in STATUSES],
        "games": games,
        "countries": countries,
        "recent": recent,
        "store": store_name(),
    }


def clear():
    if _up():
        try:
            analytics._upstash([["DEL", LIST_KEY]])
            return True
        except analytics.StoreError:
            return False
    return _write_file({})


def count():
    return len(read())


def store_name():
    return "upstash" if _up() else "file"


# ══════════════════════════════════════════════════════════════════════════
#  request handling — serve.py and api/cart.py are both thin shells over this
# ══════════════════════════════════════════════════════════════════════════
MAX_BODY = 4 * 1024


def _body(raw):
    if not raw or len(raw) > MAX_BODY:
        return None
    try:
        b = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return None
    return b if isinstance(b, dict) else None


def process_capture(raw, header_get, session_email=""):
    """POST /api/cart → (status, payload).

    Public and unauthenticated, like `/api/collect` and `/api/account` — the
    checkout form is reachable by anyone. Everything is allowlisted and capped in
    `clean_cart()`; the price is never read from the body.

    Two ways an address arrives, and the **caller resolves the second one**:

      * the buyer typed it into the checkout form (it is in the body), or
      * `session_email` — taken from the *verified* session cookie by the route
        shell, exactly the way `/api/orders` reads it. This is what lets a
        signed-in visitor be captured **while they configure**, with no field to
        fill and nothing to type. It is never read from the body: a browser that
        could name its own account would be able to write a cart against anyone
        else's address and have the site mail them.

    The session wins when both are present — it is verified and the form field
    is not. With neither, there is nothing to capture and the answer is 204.

    One open cart per address: a buyer editing the form or re-configuring updates
    their existing row rather than minting a token each time, so one abandoned
    checkout is one recovery mail. Returns the token so the client can stop
    re-posting.
    """
    body = _body(raw)
    if body is None:
        return 204, None
    if session_email:
        body = dict(body, email=session_email)

    get = header_get or (lambda _k: "")
    import geo
    edge = _s(get("x-vercel-ip-country") or "", 2).upper()
    country = geo.country(edge, _s(body.get("tz"), 64), _s(body.get("lang"), 12))

    row = clean_cart(body, country=country)
    if row is None:
        return 204, None

    existing = find_pending(row["email"])
    if existing:
        # Keep the token (it may already be in an inbox) and the original
        # capture time (the 30-minute clock must not restart on every keystroke),
        # but take the newer configuration.
        row["token"] = existing["token"]
        row["at"] = existing.get("at", row["at"])
        row["status"] = existing.get("status", "pending")
        row["mailed_at"] = existing.get("mailed_at", 0)
    else:
        row["token"] = new_token()
    put(row)
    return 200, {"ok": True, "token": row["token"]}


def process_resolve(token):
    """GET /api/cart?token=… → (status, payload).

    The **only** way a client learns the recovery percentage. It is not in
    `data.js`, so a token is the sole route to the discount and it is checked
    here against the store: unknown, spent or expired all answer the same
    `{"valid": false}` with no discount attached.

    The client needs the figure so its live quote matches what the server will
    charge — `payments.build_session()` refuses a total the page did not show.
    """
    row = redeemable(token)
    if not row:
        return 200, {"valid": False, "pct": 0}
    return 200, {"valid": True, "pct": RECOVERY_PCT, "token": row["token"],
                 "game": row.get("game", ""), "from": row.get("from", ""),
                 "to": row.get("to", ""), "mode": row.get("mode", ""),
                 "service": row.get("service", ""), "region": row.get("region", ""),
                 "addons": row.get("addons", []), "wins": row.get("wins", 0),
                 "placements": row.get("placements", 0),
                 "unranked": bool(row.get("unranked")), "email": row.get("email", "")}


def process_unsubscribe(token):
    """GET /api/cart/unsubscribe?token=… → (status, payload).

    One click, no login, no confirmation step — an unsubscribe that asks the
    reader to authenticate is an unsubscribe that does not work. Retires the
    cart so no further sweep can pick it up. Answers 200 either way: whether a
    token exists is not something an unauthenticated caller should learn.
    """
    row = get(token)
    if row:
        mark(row["token"], status="expired")
    return 200, {"ok": True}


def process_sweep(raw, header_get):
    """POST /api/cart/sweep → (status, payload).

    The 30-minute timer. Vercel functions cannot sleep, so an external caller
    drives this: Vercel Cron, cron-job.org, a GitHub Action — anything that can
    hit it on a schedule. Safe to call as often as the scheduler allows; `due()`
    only ever returns rows past `DELAY_SECS` and each send flips the row out of
    that set before the message goes out.

    **Protected by `CART_SWEEP_SECRET`.** Unset → 503 and nothing is sent, the
    same fail-closed contract `/api/ops` and `/api/webhook` have: an open sweep
    endpoint is a free way to make the site mail arbitrary people on demand.

    The secret may arrive three ways, checked in this order:
      * `x-sweep-secret` header — the explicit path (cron-job.org, curl);
      * `Authorization: Bearer <secret>` — what **Vercel Cron** sends, using the
        `CRON_SECRET` env var Vercel injects. Set `CART_SWEEP_SECRET` and
        `CRON_SECRET` to the same value and native cron just works;
      * `{"secret": …}` in the POST body — the fallback for a scheduler that can
        only set a body.
    Header paths are preferred: a query string or body ends up in more logs.
    """
    secret = os.environ.get("CART_SWEEP_SECRET", "").strip()
    if len(secret) < 16:
        return 503, {"error": "not_configured",
                     "message": "Set CART_SWEEP_SECRET (16+ chars) to enable the sweep."}
    get_h = header_get or (lambda _k: "")
    given = (get_h("x-sweep-secret") or "").strip()
    if not given:
        auth = (get_h("authorization") or "").strip()
        if auth[:7].lower() == "bearer ":
            given = auth[7:].strip()
    if not given:
        body = _body(raw) or {}
        given = str(body.get("secret") or "").strip()
    import hmac as _hmac
    if not _hmac.compare_digest(given, secret):
        return 401, {"error": "unauthorized"}

    import recovery
    return 200, recovery.sweep()
