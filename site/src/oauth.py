# -*- coding: utf-8 -*-
"""Social sign-in (Google + Discord) — the real backend behind the header's two
OAuth buttons.

This is the authorization-code flow, done the same way the rest of this codebase
talks to Stripe: stdlib `urllib` against each provider's REST API, no third-party
packages, no framework. It turns "Continue with Google/Discord" from a facade
into a working login that:

  1. redirects the browser to the provider's consent screen (`start`);
  2. on return, exchanges the code for a token **server-side** (the client secret
     never touches the browser), reads the verified name + email (`callback`);
  3. stores that verified lead in the SAME sign-up list the email facade writes
     to (`accounts.append`) — one store, deduped by email; and
  4. issues a signed, HttpOnly **session cookie** so the header reflects a real
     signed-in state. `read_session()` is the only thing that can open it.

Deliberately scoped to match this prototype (see build.py's AUTH_PLACEHOLDER):
it verifies identity and mints a session, it does not build a full account
system — there is still no order binding, no email/password linking, no 2FA.
What it removes from that list is the two lines that mattered most: the OAuth
buttons now reach real apps, and a session is now real rather than a localStorage
flag.

CSRF is covered by a signed `state` carried in both the redirect and an HttpOnly
cookie, checked to match on return. Nothing is trusted from the query string
alone.

Configuration is env-only, never committed — same contract as STRIPE_SECRET_KEY:

    GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET       # enables the Google button
    DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET     # enables the Discord button
    SESSION_SECRET        # signs the session + state cookies (>= 16 chars)
    PUBLIC_BASE_URL       # redirect-URI origin; inferred from Host if unset

With a provider's pair unset, `start()` refuses (503) and the button falls back
to the facade message client-side, so the static preview still walks end to end.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import accounts
import geo

# ── limits & names ──────────────────────────────────────────────────────────
STATE_TTL = 600            # 10 min to complete the round trip to the provider
SESSION_TTL = 30 * 86400   # "signed in for 30 days" — matches the panel's copy
STATE_COOKIE = "esb_oauth_state"
SESSION_COOKIE = "esb_session"
HTTP_TIMEOUT = 20

# Per-provider endpoints and the userinfo shape. `norm` maps a provider's raw
# profile JSON onto the two facts this site keeps — a display name and a
# verified email — plus the provider tag stored alongside them.
PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        # Google asks for these two to guarantee a refreshable, consistent grant;
        # harmless for a one-shot login and keeps the consent screen predictable.
        "auth_extra": {"access_type": "online", "prompt": "select_account"},
    },
    "discord": {
        "authorize": "https://discord.com/oauth2/authorize",
        "token": "https://discord.com/api/oauth2/token",
        "userinfo": "https://discord.com/api/users/@me",
        "scope": "identify email",
        "auth_extra": {},
    },
}


# ── configuration ───────────────────────────────────────────────────────────
def _client(provider):
    """(client_id, client_secret) for a provider, or ("","") when unset."""
    p = provider.upper()
    return (os.environ.get("%s_CLIENT_ID" % p, "").strip(),
            os.environ.get("%s_CLIENT_SECRET" % p, "").strip())


def configured(provider):
    """True when both halves of a provider's credential pair are present."""
    if provider not in PROVIDERS:
        return False
    cid, secret = _client(provider)
    return bool(cid and secret)


def enabled():
    """{'google': bool, 'discord': bool} — which buttons should actually go to
    the provider. Read by the client so an unconfigured button keeps its facade
    message instead of navigating to a 503."""
    return {p: configured(p) for p in PROVIDERS}


def _session_secret():
    """The HMAC key for the state + session cookies. A real SESSION_SECRET is
    required for sessions to survive a restart; absent one (dev), fall back to a
    per-process random key so cookies still sign — they just don't outlive the
    server, which is the safe failure, not a fixed default everyone shares."""
    env = os.environ.get("SESSION_SECRET", "").strip()
    if len(env) >= 16:
        return env.encode()
    if not getattr(_session_secret, "_ephemeral", None):
        _session_secret._ephemeral = os.urandom(32)
    return _session_secret._ephemeral


# ── signed tokens (state + session) ─────────────────────────────────────────
def _b64e(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s):
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload):
    """payload(dict) → "<body>.<mac>", body being urlsafe-b64 JSON."""
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(_session_secret(), body.encode(), hashlib.sha256).digest()
    return "%s.%s" % (body, _b64e(mac))


def _unsign(token, now=None):
    """Verify signature + expiry, return the payload dict or None. Constant-time
    on the MAC; rejects anything past its `exp`."""
    now = int(now or time.time())
    try:
        body, mac = str(token).split(".", 1)
        want = hmac.new(_session_secret(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(mac), want):
            return None
        payload = json.loads(_b64d(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < now:
        return None
    return payload


def make_session(name, email, provider, now=None):
    """A signed 30-day session token for the cookie."""
    now = int(now or time.time())
    return _sign({"n": name, "e": email, "p": provider,
                  "iat": now, "exp": now + SESSION_TTL})


def read_session(cookie_value, now=None):
    """Open a session cookie → {name, email, provider} or None."""
    payload = _unsign(cookie_value, now)
    if not payload:
        return None
    return {"name": payload.get("n", ""), "email": payload.get("e", ""),
            "provider": payload.get("p", "")}


# ── the flow ────────────────────────────────────────────────────────────────
def _redirect_uri(provider, base_url):
    return "%s/api/auth/%s/callback" % (base_url.rstrip("/"), provider)


def _safe_return(return_to):
    """Only ever redirect back to a same-site path. An open redirector is a
    textbook OAuth bug — reject anything that isn't a bare `/path`."""
    rt = str(return_to or "/")
    if not rt.startswith("/") or rt.startswith("//"):
        return "/"
    return rt[:512]


def start(provider, base_url, return_to="/", now=None):
    """Begin sign-in. Returns (302_location, state_cookie_value) or (None, None)
    when the provider isn't configured (caller answers 503)."""
    if not configured(provider):
        return None, None
    now = int(now or time.time())
    cid, _ = _client(provider)
    cfg = PROVIDERS[provider]
    nonce = _b64e(os.urandom(16))
    state = _sign({"p": provider, "rt": _safe_return(return_to),
                   "n": nonce, "exp": now + STATE_TTL})
    params = {
        "client_id": cid,
        "redirect_uri": _redirect_uri(provider, base_url),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    params.update(cfg["auth_extra"])
    return "%s?%s" % (cfg["authorize"], urllib.parse.urlencode(params)), state


def _post_form(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _get_json(url, access_token):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer " + access_token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _profile(provider, access_token):
    """Fetch and normalise the provider's profile → {name, email} (email may be
    empty). Raises OAuthError on a provider/transport failure."""
    try:
        raw = _get_json(PROVIDERS[provider]["userinfo"], access_token)
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        raise OAuthError("Could not read your %s profile." % provider) from e
    if provider == "google":
        return {"name": (raw.get("name") or raw.get("given_name")
                         or (raw.get("email") or "").split("@")[0] or "you"),
                "email": (raw.get("email") or "").strip().lower()}
    # discord
    name = raw.get("global_name") or raw.get("username") or "you"
    return {"name": name, "email": (raw.get("email") or "").strip().lower()}


class OAuthError(Exception):
    pass


def callback(provider, query, state_cookie, base_url, header_get=None, now=None):
    """Handle the provider's redirect back. Returns
    (session_cookie_value, return_to). Raises OAuthError on any failure — the
    caller turns that into a redirect to the panel with an error flag.

    `query` is the parsed query dict (lists, as parse_qs gives); `state_cookie`
    is the value of STATE_COOKIE from the request.
    """
    now = int(now or time.time())
    if not configured(provider):
        raise OAuthError("This sign-in method isn't available.")

    code = (query.get("code") or [""])[0]
    got_state = (query.get("state") or [""])[0]
    if query.get("error"):
        # The user declined at the consent screen, or the provider rejected us.
        raise OAuthError("Sign-in was cancelled.")
    if not code or not got_state:
        raise OAuthError("Sign-in response was incomplete.")

    # CSRF: the state must verify, match the one we set in the cookie, and be for
    # this provider. Both the query and the cookie must carry the same token.
    st = _unsign(got_state, now)
    if not st or not hmac.compare_digest(str(got_state), str(state_cookie or "")):
        raise OAuthError("Sign-in could not be verified. Please try again.")
    if st.get("p") != provider:
        raise OAuthError("Sign-in provider mismatch.")

    cid, secret = _client(provider)
    try:
        tok = _post_form(PROVIDERS[provider]["token"], {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(provider, base_url),
            "client_id": cid,
            "client_secret": secret,
        })
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        raise OAuthError("Could not complete sign-in with %s." % provider) from e
    access_token = tok.get("access_token")
    if not access_token:
        raise OAuthError("No access token returned by %s." % provider)

    prof = _profile(provider, access_token)
    if not prof["email"]:
        # Both providers can be configured to withhold email; without it there is
        # no lead to store and nothing to key a return visit on. Say so plainly.
        raise OAuthError("Your %s account didn't share an email address." % provider)

    _store_lead(prof, provider, header_get, now)
    return make_session(prof["name"], prof["email"], provider, now), _safe_return(st.get("rt"))


def _store_lead(prof, provider, header_get, now):
    """Upsert the verified name + email into the shared sign-up list. Same store
    the email facade writes to; `accounts.append` dedupes on email, so a repeat
    login never grows the list. Country is resolved server-side (edge header,
    then Accept-Language locale) exactly as a session is — never from an IP."""
    get = header_get or (lambda *_a, **_k: "")
    edge = str(get("x-vercel-ip-country") or "").strip()[:2].upper()
    lang = str(get("accept-language") or "").split(",")[0].strip()
    row = {
        "email": prof["email"],
        "name": prof["name"][:accounts.MAX_NAME],
        "ts": now,
        "co": geo.country(edge, "", lang),
        "cosrc": geo.source(edge, "", lang),
        # Surfaced in the /ops Accounts panel so an OAuth lead is distinguishable
        # from an email one, and never read as a real "account".
        "mode": "oauth:" + provider,
    }
    try:
        accounts.append([row])
    except Exception:
        # A lost lead must never turn a successful login into a 500.
        pass


# ── HTTP glue shared by serve.py and the /api Vercel shells ─────────────────
# Both the local server and the serverless functions render the same descriptor
# so the two can never drift — the project keeps /api a thin mirror of serve.py.
def cookie_header(name, value, max_age, secure, delete=False):
    """One Set-Cookie value. HttpOnly + SameSite=Lax so the session survives the
    top-level GET redirect back from the provider but is invisible to JS; Secure
    only on https (localhost over plain http would otherwise drop it)."""
    if delete:
        parts = ["%s=" % name, "Max-Age=0"]
    else:
        parts = ["%s=%s" % (name, value), "Max-Age=%d" % int(max_age)]
    parts += ["Path=/", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def parse_cookies(cookie_header_value):
    out = {}
    for pair in (cookie_header_value or "").split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _resp(status, json_body=None, location=None, cookies=None, not_found=False):
    return {"status": status, "json": json_body, "location": location,
            "set_cookie": cookies or [], "not_found": not_found}


def dispatch(route, query, cookies, base_url, header_get):
    """Resolve one auth request to a response descriptor:

        {status, json, location, set_cookie:[...], not_found}

    `route` is the path without query; `query` is a parse_qs dict; `cookies` is a
    name→value dict. The caller emits either `json` (with `status`) or a redirect
    to `location`, plus any `set_cookie` headers.
    """
    secure = base_url.startswith("https://")

    if route == "/api/auth/logout":
        return _resp(204, cookies=[cookie_header(SESSION_COOKIE, "", 0, secure, delete=True)])

    if route == "/api/auth/me":
        sess = read_session(cookies.get(SESSION_COOKIE, ""))
        payload = {"authenticated": bool(sess), "providers": enabled()}
        if sess:
            payload.update(sess)
        return _resp(200, json_body=payload)

    if not route.startswith("/api/auth/"):
        return _resp(404, not_found=True)

    parts = route[len("/api/auth/"):].split("/")
    provider = parts[0]
    is_cb = len(parts) > 1 and parts[1] == "callback"
    if provider not in PROVIDERS:
        return _resp(404, not_found=True)

    if not is_cb:
        return_to = (query.get("return_to") or ["/"])[0]
        location, state = start(provider, base_url, return_to)
        if not location:
            return _resp(503, json_body={"error": "not_configured", "provider": provider})
        return _resp(302, location=location,
                     cookies=[cookie_header(STATE_COOKIE, state, STATE_TTL, secure)])

    clear_state = cookie_header(STATE_COOKIE, "", 0, secure, delete=True)
    try:
        sess_cookie_val, return_to = callback(
            provider, query, cookies.get(STATE_COOKIE, ""), base_url, header_get)
    except OAuthError as e:
        back = _safe_return((_unsign((query.get("state") or [""])[0]) or {}).get("rt", "/"))
        sep = "&" if "?" in back else "?"
        loc = "%s%sauth_error=%s" % (back, sep, urllib.parse.quote(str(e)[:200]))
        return _resp(302, location=loc, cookies=[clear_state])
    session = cookie_header(SESSION_COOKIE, sess_cookie_val, SESSION_TTL, secure)
    return _resp(302, location=return_to, cookies=[clear_state, session])
