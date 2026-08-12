# -*- coding: utf-8 -*-
"""The account store behind the header's auth panel.

This is a real credential store: `POST /api/account` with `mode:"signup"`
creates an account (name, email, salted password hash) and `mode:"signin"`
verifies an email + password against it. A sign-in for an unknown email or a
wrong password is refused (401) — the panel no longer accepts anything. The
same rows are what the `/ops` Accounts console lists.

What is deliberately still minimal (see `build.py`'s `AUTH_PLACEHOLDER` block):
there is no email verification, no password-reset flow, and the browser session
is a `localStorage` record rather than a signed server token. Checkout stays
guest-only. So this is genuine authentication, but not yet a full account system
— finish those before it carries anything that matters.

Load-bearing rules:

  * **Passwords are only ever stored hashed.** `hash_password()` runs PBKDF2-
    HMAC-SHA256 with a per-account random salt (stdlib `hashlib`); the plaintext
    is verified once and never written, and the hash never leaves this module —
    the `/ops` payload whitelists fields, so it is not in any dashboard. Never
    store, log or return a plaintext password.
  * **This is a SEPARATE store from analytics.** `analytics.py` is anonymous by
    construction and that is what keeps it out of consent-banner territory — an
    email in that store would break the guarantee its own header makes. So the
    two never share a key or a file: analytics is `esb:ev` / `analytics.ndjson`,
    this is `esb:accounts` / `accounts.ndjson`. It reuses analytics' Upstash
    transport (`_upstash`) and store-selection only — never its data.

`/api/account` is public and unauthenticated, like `/api/collect`: the auth form
is on every page. So everything is length-capped and validated below, nothing is
stored that did not survive `clean_signup()`, and the list is read only through
the password-gated `/ops` API. A real login endpoint is necessarily an
authentication oracle (a wrong password is distinguishable from an unknown
email is avoided — both answer the same 401 — but a valid pair is not); a
production deployment needs rate limiting on this route.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time

import analytics
import geo

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 4 * 1024
MAX_ACCOUNTS = int(os.environ.get("ACCOUNTS_MAX", "20000") or 20000)
MAX_NAME = 60
MAX_EMAIL = 160

MAX_PASSWORD = 256          # cap before hashing — a huge string would DoS PBKDF2
MIN_PASSWORD = 6            # enforced on signup, client and server

LIST_KEY = "esb:accounts"
# One address signs up once. This SET mirrors the emails already in LIST_KEY and
# is what makes the uniqueness check O(1) on the Upstash path (SISMEMBER) instead
# of scanning the whole list per signup. It is written in the same pipeline as
# the row, cleared with it, and — because the list is capped and the set is not —
# an email trimmed out of the (huge) list still blocks a re-signup, which is the
# behaviour we want: they did sign up once.
EMAIL_KEY = "esb:accounts:emails"
# Password hashes, keyed by email. Kept OUT of the displayed list on Upstash (a
# Redis HASH, HGET is O(1) at login); on the file store the hash rides in the row
# instead, and the /ops payload whitelists fields so it never surfaces there.
CRED_KEY = "esb:accounts:cred"

# ── password hashing (PBKDF2-HMAC-SHA256, stdlib only) ──────────────────────
_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERS = 240000
_SALT_BYTES = 16


def hash_password(password):
    """Encode a password as ``pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>``."""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return "%s$%d$%s$%s" % (_PBKDF2_ALGO, _PBKDF2_ITERS, salt.hex(), dk.hex())


def verify_password(password, encoded):
    """Constant-time check of a plaintext password against a stored hash."""
    try:
        algo, iters, salt_hex, hash_hex = (encoded or "").split("$", 3)
        if algo != _PBKDF2_ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"),
            bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)

# Same shape as a real address, loosely — this is a display list, not an MX
# check. It rejects the obvious junk and caps the length; a bounced address is
# the ops reader's problem, not a reason to drop a lead at the door.
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,128}\.[A-Za-z]{2,24}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def log_path():
    return os.environ.get("ACCOUNTS_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "accounts.ndjson")


def _s(v, n):
    """Trim to a string, strip control chars, cap length."""
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


# ══════════════════════════════════════════════════════════════════════════
#  store — mirrors analytics.append/read/clear/count against a separate key
# ══════════════════════════════════════════════════════════════════════════
def _file_emails():
    """Every email currently in the file store — the dedup index for the local
    path (the Upstash path uses the EMAIL_KEY set instead)."""
    return {r.get("email") for r in read() if r.get("email")}


def append(rows):
    """Persist cleaned signups, **one row per email**. Returns the number of
    NEW rows written; a submission whose email is already stored is dropped, and
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
                    continue                    # already signed up
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
                    ["LTRIM", LIST_KEY, 0, MAX_ACCOUNTS - 1]]
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


def create_account(row, encoded):
    """Append a signup row and persist its password hash. Returns the number of
    new rows written (0 if the email was already present). Upstash keeps the hash
    in the CRED_KEY hash — never in the displayed list; the file store carries it
    in the row (the /ops payload whitelists fields, so it never leaves the box).
    """
    up = analytics.upstash_config()[0]
    if not up:
        row = dict(row, pw=encoded)
    n = append([row])
    if n and up:
        try:
            analytics._upstash([["HSET", CRED_KEY, row["email"], encoded]])
        except analytics.StoreError:
            pass
    return n


def credential(email):
    """The stored password hash for an email, or "" if there is none. O(1) on
    Upstash (HGET); a scan of the file store otherwise."""
    email = (email or "").strip().lower()
    if not email:
        return ""
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["HGET", CRED_KEY, email]])
            return (res[0] if res else "") or ""
        except analytics.StoreError:
            return ""
    for r in read():
        if r.get("email") == email:
            return r.get("pw") or ""
    return ""


def read(limit=MAX_ACCOUNTS):
    """Return up to `limit` stored signups, newest first."""
    limit = max(1, min(int(limit or MAX_ACCOUNTS), MAX_ACCOUNTS))
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
    """Wipe the list. Used by the seeder; never exposed over HTTP."""
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["DEL", LIST_KEY], ["DEL", EMAIL_KEY], ["DEL", CRED_KEY]])
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


def email_exists(email):
    """Is this address already in the list? Lower-cased first, so the check is
    case-insensitive. O(1) against the EMAIL_KEY set on Upstash; a scan on the
    file store. Fails **open** (False) if the store can't be reached — a create
    should not be blocked by an unverifiable check, and `append()` dedupes
    anyway, so a slip here can't actually double the list."""
    email = (email or "").strip().lower()
    if not email:
        return False
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["SISMEMBER", EMAIL_KEY, email]])
            return bool(res and res[0])
        except analytics.StoreError:
            return False
    return email in _file_emails()


# ══════════════════════════════════════════════════════════════════════════
#  ingest
# ══════════════════════════════════════════════════════════════════════════
def clean_signup(body, now, ctx):
    """Validate one submission into a stored row, or None.

    Stored keys: `email`, `name`, `ts`, `co` (country), `cosrc` (which signal
    resolved it), `mode` (signin|signup), and `syn` only when the seeder set it.
    No password key exists — see the module header.
    """
    if not isinstance(body, dict):
        return None
    email = _s(body.get("email"), MAX_EMAIL).lower()
    if not _EMAIL_RE.match(email):
        return None
    row = {
        "email": email,
        "name": _s(body.get("name"), MAX_NAME),
        "ts": now,
        "co": ctx.get("co", ""),
        "cosrc": ctx.get("cosrc", ""),
    }
    mode = _s(body.get("mode"), 8)
    if mode in ("signin", "signup"):
        row["mode"] = mode
    # Passthrough only — the public endpoint never sets it; the seeder does, and
    # the ops banner keys off it exactly like the analytics store's `syn`.
    if body.get("syn") in (1, True):
        row["syn"] = 1
    return row


def _login(email, password):
    """Verify an email + password against the store. `(200, {...})` on a match,
    `(401, {"error": "invalid"})` otherwise. The same 401 answers an unknown
    email and a wrong password, so the endpoint is not a bare account-existence
    oracle; the returned name lets the client greet the account by its handle."""
    email = _s(email, MAX_EMAIL).lower()
    if not _EMAIL_RE.match(email) or not password:
        return 401, {"error": "invalid"}
    enc = credential(email)
    if not enc or not verify_password(password, enc):
        return 401, {"error": "invalid"}
    name = ""
    for r in read():
        if r.get("email") == email:
            name = r.get("name", "")
            break
    return 200, {"ok": True, "email": email, "name": name}


def process_signup(raw, header_get):
    """POST /api/account → (status, payload).

    Body: {"email", "password", "name"?, "mode"?, "tz"?, "lang"?}. Country is
    resolved server-side from the edge header, then the browser timezone, then
    the locale — never trusted from the body, never from an IP lookup.

    Responses, by `mode`:
      · **signup, new email** → `(200, {"created": True, "email", "name"})`, and
        the account (name, email, salted password hash) is stored.
      · **signup, weak/short password** → `(400, {"error": "weak"})`.
      · **signup, invalid email** → `(400, {"error": "email"})`.
      · **signup, email already registered** → `(409, {"error": "exists"})`,
        nothing stored — the create flow tells the visitor to log in instead.
      · **signin, valid credentials** → `(200, {"ok": True, "email", "name"})`.
      · **signin, bad credentials** → `(401, {"error": "invalid"})`.
      · unknown mode / unparseable body → `(204, None)`.

    NB both create-exists (409) and login are authentication oracles by nature;
    a production deployment needs rate limiting on this route (module header).
    """
    if not raw or len(raw) > MAX_BODY:
        return 204, None
    try:
        body = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return 204, None
    if not isinstance(body, dict):
        return 204, None

    mode = _s(body.get("mode"), 8)
    password = str(body.get("password") or "")[:MAX_PASSWORD]

    if mode == "signin":
        return _login(body.get("email"), password)
    if mode != "signup":
        return 204, None                     # unknown mode records nothing

    get = header_get or (lambda *_a, **_k: "")
    edge = _s(get("x-vercel-ip-country") or "", 2).upper()
    tz = _s(body.get("tz"), 64)
    lang = _s(body.get("lang"), 12)
    ctx = {
        "co": geo.country(edge, tz, lang),
        "cosrc": geo.source(edge, tz, lang),
    }
    row = clean_signup(body, int(time.time()), ctx)
    if row is None:
        return 400, {"error": "email"}
    if len(password) < MIN_PASSWORD:
        return 400, {"error": "weak"}
    if email_exists(row["email"]):
        return 409, {"error": "exists"}
    create_account(row, hash_password(password))   # re-checks uniqueness itself
    return 200, {"created": True, "email": row["email"], "name": row["name"]}


# ══════════════════════════════════════════════════════════════════════════
#  aggregation — what /ops reads
# ══════════════════════════════════════════════════════════════════════════
RECENT_CAP = 300      # rows shipped to the console; the list is a lead sheet


def summary(days=30, now=None):
    """The Accounts panel's payload: totals, a per-day series, a country split
    and the most recent rows (capped, newest first)."""
    now = int(now or time.time())
    rows = read()
    since = now - days * 86400

    total = len(rows)
    window = [r for r in rows if int(r.get("ts") or 0) >= since]
    synthetic = sum(1 for r in rows if r.get("syn"))

    # 24h / 7d headline counts, always against the full store.
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

    by_country = {}
    for r in window:
        co = r.get("co") or "??"
        by_country[co] = by_country.get(co, 0) + 1
    countries = sorted(
        ({"code": k, "count": v} for k, v in by_country.items()),
        key=lambda x: (-x["count"], x["code"]))

    # A signup counts as a returning email if that address appears more than
    # once across the store — the closest this list has to "existing customer".
    seen = {}
    for r in rows:
        seen[r["email"]] = seen.get(r["email"], 0) + 1
    unique = len(seen)
    repeat = sum(1 for c in seen.values() if c > 1)

    recent = [{
        "email": r["email"], "name": r.get("name", ""), "ts": int(r.get("ts") or 0),
        "co": r.get("co", ""), "cosrc": r.get("cosrc", ""),
        "mode": r.get("mode", ""), "syn": 1 if r.get("syn") else 0,
    } for r in rows[:RECENT_CAP]]

    return {
        "total": total, "unique": unique, "repeat": repeat,
        "in_window": len(window), "last_24h": last_24h, "last_7d": last_7d,
        "synthetic": synthetic, "days": days,
        "series": series, "countries": countries, "recent": recent,
        "store": analytics.store_name(),
    }
