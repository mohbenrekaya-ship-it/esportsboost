# -*- coding: utf-8 -*-
"""The gate in front of the analytics dashboard: auth + the JSON it reads.

`/ops/` is a public URL on the same deploy as the shop, so the HTML shell is
readable by anyone who guesses the path. That is fine and deliberate — the shell
holds no data. **Every number arrives through this module**, and this module
answers nothing without a valid credential.

Design notes worth keeping:

  * The password lives only in `OPS_PASSWORD`. With it unset, the API returns
    503 and the dashboard renders a setup notice rather than any data —
    unconfigured fails closed, never open.
  * Short passwords are refused at the door (`MIN_PASSWORD`). A one-route admin
    API on a public domain is exactly where a weak password gets found.
  * Login returns a short-lived HMAC token; the browser holds that, not the
    password, and it expires on its own.
  * Failed attempts are counted and throttled: Upstash when it is configured
    (the production path, shared across serverless invocations), otherwise an
    in-process counter — `serve.py` is one long-running process, so that is a
    real lockout rather than a no-op.
  * Comparisons use `hmac.compare_digest` — never `==`.
"""
import base64
import hmac
import json
import os
import time
from hashlib import sha256

import accounts
import analytics
import boosters
import carts
import guides
import insights
import maillist
import maillog
import mystery
import orders
import stock

TOKEN_TTL = 12 * 3600      # a working day, then log in again
MIN_PASSWORD = 12          # refuse to protect the dashboard with less
MAX_BODY = 8 * 1024
MAX_SOURCE = 160           # "source / medium", capped like every other body field
MAX_ATTEMPTS = 10          # per window, per deployment
ATTEMPT_WINDOW = 900       # 15 minutes


def password():
    return os.environ.get("OPS_PASSWORD", "")


def configured():
    return len(password()) >= MIN_PASSWORD


def _secret():
    """Signing key for session tokens. Distinct from the password itself so a
    leaked token can never be walked back into the password."""
    return sha256(("esb.ops.v1|" + password()).encode()).digest()


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_token(now=None):
    exp = int(now or time.time()) + TOKEN_TTL
    body = str(exp).encode()
    sig = hmac.new(_secret(), body, sha256).digest()
    return "%s.%s" % (_b64(body), _b64(sig))


def check_token(token, now=None):
    if not configured() or not token or token.count(".") != 1:
        return False
    body_b64, sig_b64 = token.split(".")
    try:
        pad = lambda s: s + "=" * (-len(s) % 4)               # noqa: E731
        body = base64.urlsafe_b64decode(pad(body_b64))
        sig = base64.urlsafe_b64decode(pad(sig_b64))
    except (ValueError, TypeError):
        return False
    if not hmac.compare_digest(hmac.new(_secret(), body, sha256).digest(), sig):
        return False
    try:
        return int(body) > int(now or time.time())
    except ValueError:
        return False


# ── brute-force throttle ──────────────────────────────────────────────────
# `/ops` is a public URL on the shop's own domain, so the login is reachable by
# anyone who guesses the path. Upstash carries the counter in production; the
# local path used to degrade to "no throttle at all", which is only defensible
# while `serve.py` is a private preview. It is one long-running process, so an
# in-memory counter is real protection there — the same fallback accounts.py
# uses, and the same reason.
_MEM_FAILS = [0, 0]        # [count, window_start]


def _attempt_key():
    return "esb:ops:fails"


def _too_many_attempts(now=None):
    now = int(now or time.time())
    if not analytics.upstash_config()[0]:
        count, start = _MEM_FAILS
        if now - start > ATTEMPT_WINDOW:
            return False
        return count >= MAX_ATTEMPTS
    try:
        res = analytics._upstash([["GET", _attempt_key()]])
    except analytics.StoreError:
        return False
    try:
        return int(res[0] or 0) >= MAX_ATTEMPTS
    except (TypeError, ValueError):
        return False


def _note_failure(now=None):
    now = int(now or time.time())
    if not analytics.upstash_config()[0]:
        if now - _MEM_FAILS[1] > ATTEMPT_WINDOW:
            _MEM_FAILS[0], _MEM_FAILS[1] = 0, now
        _MEM_FAILS[0] += 1
        return
    try:
        analytics._upstash([["INCR", _attempt_key()],
                            ["EXPIRE", _attempt_key(), ATTEMPT_WINDOW]])
    except analytics.StoreError:
        pass


def _clear_failures():
    if not analytics.upstash_config()[0]:
        _MEM_FAILS[0], _MEM_FAILS[1] = 0, 0
        return
    try:
        analytics._upstash([["DEL", _attempt_key()]])
    except analytics.StoreError:
        pass


# ── the one route ────────────────────────────────────────────────────────
MAX_RANGE = 400 * 86400          # a hair over a year, so "12 months" always fits


def _range(body):
    """An absolute window from the console, or None to fall back to `days`.

    The browser sends epochs because it is the only side that knows the
    reader's timezone. Validated here rather than trusted: an end before its
    start, or a range wider than MAX_RANGE, would walk the whole event store.
    """
    a, b = body.get("start"), body.get("end")
    if a is None or b is None:
        return None, None
    try:
        a, b = int(a), int(b)
    except (TypeError, ValueError):
        return None, None
    if a < 0 or b <= a or (b - a) > MAX_RANGE:
        return None, None
    return a, b


def dashboard_data(days=30, game=None, synthetic=False, start=None, end=None,
                   tzoff=0, source=None):
    events = analytics.read()
    payload = insights.compute(events, days=days, game=game, synthetic=synthetic,
                               start=start, end=end, tzoff=tzoff, source=source)
    payload["meta"]["store"] = analytics.store_name()
    return payload


def process_ops(raw):
    """POST /api/ops → (status, payload).

    Body: {"action": "login"|"data", "password"?, "token"?, "days"?, "game"?,
           "source"?}
    """
    if not configured():
        return 503, {"error": "not_configured",
                     "message": "Set OPS_PASSWORD (%d+ characters) to enable the "
                                "dashboard." % MIN_PASSWORD}
    if not raw or len(raw) > MAX_BODY:
        return 400, {"error": "bad_request"}
    try:
        body = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return 400, {"error": "bad_request"}
    if not isinstance(body, dict):
        return 400, {"error": "bad_request"}

    action = str(body.get("action") or "data")
    try:
        days = max(1, min(int(body.get("days") or 30), 365))
    except (TypeError, ValueError):
        days = 30
    game = body.get("game") if isinstance(body.get("game"), str) else None
    # The Sessions tab's traffic-source filter — "google.com / referral", the
    # pair the table prints. Matched against a key the server itself built, so
    # anything unrecognised simply matches nothing; capped because it arrives
    # from the body like everything else here.
    source = body.get("source")
    source = source[:MAX_SOURCE] if isinstance(source, str) and source else None
    # Off by default: the dashboard's job is to report real traffic, and seeded
    # rows in the denominator are indistinguishable from real ones once they are
    # in. The console's own toggle is the only thing that turns them back on.
    synthetic = body.get("synthetic") is True
    r_start, r_end = _range(body)
    # getTimezoneOffset(), minutes. Bounded to the real range of world offsets
    # so a junk value cannot shift a label by years.
    try:
        tzoff = max(-900, min(900, int(body.get("tzoff") or 0)))
    except (TypeError, ValueError):
        tzoff = 0

    if action == "login":
        if _too_many_attempts():
            return 429, {"error": "throttled",
                         "message": "Too many failed attempts. Try again in 15 minutes."}
        given = body.get("password")
        ok = isinstance(given, str) and hmac.compare_digest(given, password())
        if not ok:
            _note_failure()
            time.sleep(0.4)          # blunt the online guessing rate
            return 401, {"error": "bad_password"}
        _clear_failures()
        return 200, {"token": make_token(),
                     "data": dashboard_data(days, game, synthetic, r_start, r_end,
                                            tzoff, source)}

    if not check_token(body.get("token")):
        return 401, {"error": "expired"}

    if action == "session":
        # One session's full timeline, fetched on click. Kept off the main
        # payload deliberately: bundling every session's events would mean
        # shipping the whole event store to the browser on every refresh.
        sid = body.get("session_id")
        if not isinstance(sid, str) or not analytics._ID_RE.match(sid):
            return 400, {"error": "bad_session"}
        detail = insights.session_detail(analytics.read(), sid)
        if detail is None:
            return 404, {"error": "not_found"}
        return 200, {"session": detail}

    if action == "accounts":
        # The header's sign-up list — a separate store from the analytics
        # events, and the only place emails live. Fetched on demand rather than
        # bundled into every dashboard refresh: it is PII, so it is read only
        # when the Accounts tab is actually open.
        return 200, {"accounts": accounts.summary(days)}

    if action == "boosters":
        # The roster store — a separate store from analytics and accounts, read
        # only here. Unlike Accounts it holds no PII, but it is fetched on demand
        # the same way rather than bundled into every dashboard refresh.
        return 200, {"boosters": boosters.summary()}

    if action == "carts":
        # The abandoned-checkout store — a separate store again, and like Accounts
        # and Orders it holds PII (the email a buyer typed or their session
        # supplied), so it is fetched on demand rather than bundled into every
        # dashboard refresh.
        return 200, {"carts": carts.summary(days)}

    if action == "guides":
        # The free-guides mailing list — its own store again, and like Accounts
        # it holds emails (PII), so it is fetched on demand rather than bundled
        # into every dashboard refresh.
        return 200, {"guides": guides.summary(days)}

    if action == "outbox":
        # The outbox — every message the site actually sent, with its body.
        # `maillog.py` writes it from inside `mailer.send()`, so nothing can
        # send without appearing here. Fetched ON DEMAND and never bundled into
        # a dashboard refresh: it is the most sensitive payload on the console,
        # holding a recipient's address next to the full text of what was sent
        # to them, live discount codes included.
        kind = str(body.get("kind") or "").strip()[:32]
        return 200, {"outbox": maillog.summary(days, kind=kind)}

    if action == "mystery":
        # The mystery-discount store — the emails the configurator modal
        # captured, next to the single-use token each one bought. PII plus a
        # live discount, so it is fetched on demand like Accounts and Carts and
        # never bundled into a dashboard refresh.
        return 200, {"mystery": mystery.summary(days)}

    if action == "maildiscounts":
        # Every captured address in one view — a read-only JOIN across carts,
        # mystery, guides, accounts and orders (see maillist.py). It owns no
        # store of its own on purpose: a fifth copy of the site's emails would
        # be its own liability and its own deletion path. PII, so it is fetched
        # on demand like Accounts and Carts.
        return 200, {"maildiscounts": maillist.summary(days)}

    if action == "stock":
        # The account-stock store — how many credentials are on the shelf per
        # (listing, shard), what has sold, and what a paid order never received.
        # Fetched on demand like every other store tab. ⚠ `stock.summary()`
        # never carries a password: the list is rendered into a browser, and
        # the question this tab answers is "how much is left", not "what is the
        # login". Reading one out is the separate, deliberate action below.
        return 200, {"stock": stock.summary(days)}

    if action == "stock_reveal":
        # ⚠ THE ONE ROUTE THAT RETURNS A LIVE CREDENTIAL, and the only reason it
        # exists is the case nothing else can resolve: a paid order whose
        # handover mail did not go out, which an operator has to send by hand.
        # Behind the ops token like everything else here, one unit at a time,
        # never in a list — and logged, because a credential read is a thing
        # somebody should be able to account for afterwards.
        uid = body.get("unit")
        if not isinstance(uid, str) or not uid.startswith("u_"):
            return 400, {"error": "bad_unit"}
        row = stock.reveal(uid)
        if row is None:
            return 404, {"error": "not_found"}
        time_now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        import sys as _sys
        _sys.stderr.write("[stock] credentials revealed in /ops: %s (%s)\n"
                          % (uid, time_now))
        return 200, {"unit": row}

    if action == "orders":
        # The orders store — the receipts fulfilment writes (and the seeder
        # fills). Holds PII (a customer email, a country), so it is fetched on
        # demand like Accounts, never bundled into the dashboard payload.
        return 200, {"orders": orders.summary(days)}

    if action == "order":
        # One order's full detail, fetched on click — the same on-demand pattern
        # as a session timeline, kept off the list payload.
        oid = body.get("order_id")
        if not isinstance(oid, str) or not orders.ORDER_ID_RE.match(oid.upper()):
            return 400, {"error": "bad_order"}
        det = orders.detail(oid)
        if det is None:
            return 404, {"error": "not_found"}
        return 200, {"order": det}

    return 200, {"data": dashboard_data(days, game, synthetic, r_start, r_end,
                                        tzoff, source)}
