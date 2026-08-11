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
  * Failed attempts are counted and throttled when Upstash is configured (the
    production path). Locally there is no shared state to count in, so the
    throttle degrades to the constant-time compare alone.
  * Comparisons use `hmac.compare_digest` — never `==`.
"""
import base64
import hmac
import json
import os
import time
from hashlib import sha256

import analytics
import insights

TOKEN_TTL = 12 * 3600      # a working day, then log in again
MIN_PASSWORD = 12          # refuse to protect the dashboard with less
MAX_BODY = 8 * 1024
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


# ── brute-force throttle (shared state only exists on the Upstash path) ───
def _attempt_key():
    return "esb:ops:fails"


def _too_many_attempts():
    if not analytics.upstash_config()[0]:
        return False
    try:
        res = analytics._upstash([["GET", _attempt_key()]])
    except analytics.StoreError:
        return False
    try:
        return int(res[0] or 0) >= MAX_ATTEMPTS
    except (TypeError, ValueError):
        return False


def _note_failure():
    if not analytics.upstash_config()[0]:
        return
    try:
        analytics._upstash([["INCR", _attempt_key()],
                            ["EXPIRE", _attempt_key(), ATTEMPT_WINDOW]])
    except analytics.StoreError:
        pass


def _clear_failures():
    if not analytics.upstash_config()[0]:
        return
    try:
        analytics._upstash([["DEL", _attempt_key()]])
    except analytics.StoreError:
        pass


# ── the one route ────────────────────────────────────────────────────────
def dashboard_data(days=30, game=None):
    events = analytics.read()
    payload = insights.compute(events, days=days, game=game)
    payload["meta"]["store"] = analytics.store_name()
    return payload


def process_ops(raw):
    """POST /api/ops → (status, payload).

    Body: {"action": "login"|"data", "password"?, "token"?, "days"?, "game"?}
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
        return 200, {"token": make_token(), "data": dashboard_data(days, game)}

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

    return 200, {"data": dashboard_data(days, game)}
