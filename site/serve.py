#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local preview + payments server for site/dist.

    python3 site/serve.py [port]

Serves the built site, maps extensionless paths to .html, returns the real 404
page so the whole site can be walked like the production one — and exposes the
Stripe payment API the checkout page calls:

    POST /api/checkout   → create a Stripe Checkout Session, return {url}
    GET  /api/session    → look up a completed session (success page)
    POST /api/webhook    → receive Stripe events (fulfilment)

…and the first-party analytics pipeline behind /ops:

    POST /api/collect    → store beacon events (public, anonymous, 204)
    POST /api/ops        → password-gated dashboard JSON

The payment logic itself lives in src/payments.py, the analytics logic in
src/analytics.py + src/insights.py + src/ops.py — all shared verbatim with the
Vercel serverless functions in /api. This file is just the local HTTP shell.
Stays true to the project's rule of no third-party packages. Nothing charges
until you configure a key:

    export STRIPE_SECRET_KEY=sk_test_...        # required to take payment
    export STRIPE_WEBHOOK_SECRET=whsec_...      # optional, enables /api/webhook
    export PUBLIC_BASE_URL=http://localhost:4321  # optional, else inferred
    python3 site/serve.py 4321

With no key set the site still previews; the checkout page detects the
un-configured API and shows its local preview confirmation instead of charging.
"""
import json
import os
import sys
import urllib.parse
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "dist")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4321


def _load_dotenv():
    """Dependency-free .env support so secrets (STRIPE_SECRET_KEY, …) survive
    restarts without being passed on the command line. A real environment
    variable always wins over the file. Looked for in the repo root and site/."""
    for path in (os.path.join(os.path.dirname(HERE), ".env"), os.path.join(HERE, ".env")):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except FileNotFoundError:
            pass


_load_dotenv()

sys.path.insert(0, os.path.join(HERE, "src"))
import accounts   # noqa: E402  — header sign-up list (also used by /api)
import analytics  # noqa: E402  — first-party event ingest (also used by /api)
import boosters   # noqa: E402  — roster store behind /api/boosters (also used by /api)
import carts      # noqa: E402  — abandoned-checkout capture behind /api/cart (also used by /api)
import guides     # noqa: E402  — free-guides mailing list behind /api/guides (also used by /api)
import mailer     # noqa: E402  — outbound SMTP seam (support tickets, order mail)
import oauth      # noqa: E402  — social sign-in (Google/Discord), also used by /api
import ops        # noqa: E402  — gated dashboard API (also used by /api)
import payments   # noqa: E402  — shared Stripe/pricing logic (also used by /api)
import support    # noqa: E402  — /api/support, the contact form (also used by /api)
import apply      # noqa: E402  — /api/apply, the become-a-booster form (also used by /api)


class Handler(SimpleHTTPRequestHandler):
    # ── static site (unchanged behaviour) ─────────────────────────────────
    def translate_path(self, path):
        raw = path.split("?", 1)[0]
        p = super().translate_path(raw)
        if not os.path.exists(p) and not raw.rstrip("/").endswith(".html"):
            alt = p.rstrip("/") + ".html"
            if os.path.isfile(alt):
                return alt
        # A clean URL whose name is ALSO a directory: /checkout beside
        # /checkout/success, /games beside /games/valorant. Vercel serves
        # <name>.html when there is one and <name>/index.html otherwise —
        # verified against production. The stdlib handler instead 301s to the
        # trailing-slash form, which production never does, so without this the
        # preview redirects on links the live site serves directly and stops
        # walking like production.
        if os.path.isdir(p) and not raw.endswith("/"):
            for cand in (p.rstrip("/") + ".html", os.path.join(p, "index.html")):
                if os.path.isfile(cand):
                    return cand
        return p

    def send_error(self, code, message=None, explain=None):
        page = os.path.join(ROOT, "404.html")
        if code == 404 and os.path.isfile(page):
            with open(page, "rb") as f:
                body = f.read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)

    def _geo_cookie(self):
        """The local stand-in for middleware.js, which only exists on Vercel.

        Same cookie, same name, same shape, so i18n.js's `cookieCountry()` is
        exercised for real in dev rather than only in production. Two sources:
        the edge header when something upstream sets it, and — because nothing
        does locally — a `?geo=XX` override that pins a country for the rest of
        the session. That override is what makes "does a US visitor see dollars"
        a thing you can answer on localhost instead of behind a VPN.

        Dev-only by construction: production serves static files and
        `api/*.py` through Vercel, and never runs this file."""
        try:
            cc = (self.headers.get("x-vercel-ip-country") or "").strip().upper()
            if not (len(cc) == 2 and cc.isalpha()):
                q = urllib.parse.urlparse(self.path or "").query
                cc = (urllib.parse.parse_qs(q).get("geo", [""])[0] or "").strip().upper()
            if len(cc) == 2 and cc.isalpha():
                return "esb_geo=%s; Path=/; Max-Age=86400; SameSite=Lax" % cc
        except Exception:
            pass
        return ""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        cookie = self._geo_cookie()
        if cookie:
            self.send_header("Set-Cookie", cookie)
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ── API — thin shell around payments.process_* ────────────────────────
    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/checkout":
            status, payload = payments.process_checkout(self._read_body(), self._base_url())
            return self._json(status, payload)
        if route == "/api/webhook":
            status, payload = payments.process_webhook(
                self._read_body(), self.headers.get("Stripe-Signature", ""))
            return self._json(status, payload)
        if route == "/api/collect":
            analytics.process_collect(self._read_body(), self.headers.get)
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/api/account":
            # Public, like /api/collect: the auth form is on every page. The store
            # is separate from analytics and holds only a salted password hash
            # (see accounts.py). Sign-up / sign-in return a small JSON status so
            # the client can act on it; an unknown mode returns an empty 204.
            status, payload = accounts.process_signup(self._read_body(), self.headers.get)
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/guides":
            # Public, like /api/collect: the free-guides form is on a public page.
            # A separate store from analytics and accounts (see guides.py); holds
            # an email + which guides were picked, no credential. Returns a small
            # JSON status; a bad body answers an empty 204.
            status, payload = guides.process_lead(self._read_body(), self.headers.get)
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/cart":
            # Public, like /api/collect: the checkout form is reachable by anyone.
            # Captures the email a buyer typed so an abandoned checkout can be
            # recovered. A separate store from analytics (which holds no PII) —
            # see carts.py. A bad body answers an empty 204.
            # A signed-in visitor is captured with nothing to type: the email
            # comes from the VERIFIED session cookie, never from the body — the
            # same rule /api/orders follows, and what stops a browser writing a
            # cart against somebody else's address.
            _cookies = oauth.parse_cookies(self.headers.get("Cookie"))
            _sess = oauth.read_session(_cookies.get(oauth.SESSION_COOKIE))
            status, payload = carts.process_capture(
                self._read_body(), self.headers.get,
                session_email=(_sess or {}).get("email", ""))
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/cart/sweep":
            # The 30-minute timer. Vercel functions cannot sleep, so an external
            # scheduler drives this. Fails CLOSED without CART_SWEEP_SECRET — an
            # open sweep endpoint is a free way to make the site mail people.
            status, payload = carts.process_sweep(self._read_body(), self.headers.get)
            return self._json(status, payload)
        if route == "/api/support":
            # Public, like /api/collect: the contact form is on a public page.
            # Stores nothing — the ticket is composed and mailed to the support
            # mailbox with the visitor in Reply-To (see support.py). A bad body
            # answers an empty 204; an unconfigured mailbox answers 503 and the
            # page falls back to its preview confirmation.
            status, payload = support.process_ticket(self._read_body(), self.headers.get)
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/apply":
            # Public, like /api/support: the become-a-booster form is on a public
            # page. Stores nothing — the application is composed and mailed to the
            # support mailbox (see apply.py). A bad body answers an empty 204; an
            # unconfigured mailbox answers 503 and the page falls back to its
            # preview confirmation.
            status, payload = apply.process_application(self._read_body(), self.headers.get)
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/ops":
            status, payload = ops.process_ops(self._read_body())
            return self._json(status, payload)
        if route == "/api/auth/logout":
            return self._auth(route)
        self.send_error(404)

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/session":
            sid = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
            status, payload = payments.process_session(sid)
            return self._json(status, payload)
        if route == "/api/cart":
            # Resolve a recovery token → its discount. The ONLY route to the
            # percentage: it is deliberately not in data.js, so the client cannot
            # learn it without a token the server issued. Unknown/spent/expired
            # all answer {"valid": false}.
            tok = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
            status, payload = carts.process_resolve(tok)
            return self._json(status, payload)
        if route == "/api/cart/unsubscribe":
            tok = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
            carts.process_unsubscribe(tok)
            # A human clicked a link in a mail client — answer with a page, not
            # JSON. 200 either way: whether a token exists is not public.
            body = (b"<!doctype html><meta charset=utf-8><title>Unsubscribed</title>"
                    b"<style>body{background:#0b0a09;color:#e8e3dd;font:16px/1.6 "
                    b"system-ui,sans-serif;display:grid;place-items:center;height:100vh;"
                    b"margin:0;text-align:center}a{color:#ff7a3f}</style>"
                    b"<div><h1>You're unsubscribed.</h1><p>We won't email you about "
                    b"this order again.</p><p><a href=\"/\">Back to eSports Boost</a>"
                    b"</p></div>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/boosters":
            # Public, anonymous read of the roster store — the dynamic source for
            # the boosters board, the "On shift now" rail and the delivered feed.
            # 204 when the store is empty so the client keeps the server-rendered
            # fallback rather than blanking those panels.
            status, payload = boosters.process_list()
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            return self._json(status, payload)
        if route == "/api/orders":
            # The signed-in customer's OWN orders, for /orders.html. Authenticated
            # by the signed session cookie alone (oauth.read_session) — the email
            # is taken from the verified session, never from the request, so no one
            # can read another customer's orders. Not signed in → {authenticated:
            # false}, and the page shows its sign-in / empty state.
            import orders as _orders  # noqa: E402 — lazy: only this route needs it
            cookies = oauth.parse_cookies(self.headers.get("Cookie"))
            session = oauth.read_session(cookies.get(oauth.SESSION_COOKIE))
            if not session or not session.get("email"):
                return self._json(200, {"authenticated": False})
            view = _orders.customer_view(session["email"])
            view.update({"authenticated": True, "name": session.get("name", ""),
                         "email": session.get("email", "")})
            return self._json(200, view)
        if route.startswith("/api/auth/"):
            return self._auth(route)
        if route.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

    # ── social sign-in (Google / Discord) — see src/oauth.py ───────────────
    def _auth(self, route):
        """Render an oauth.dispatch() descriptor: a JSON body or a 302 redirect,
        plus any Set-Cookie headers. All the flow logic lives in oauth so this
        server and the /api Vercel shells stay identical."""
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        r = oauth.dispatch(route, query, cookies, self._base_url(), self.headers.get)
        if r["not_found"]:
            return self.send_error(404)
        body = b"" if r["json"] is None else json.dumps(r["json"]).encode()
        self.send_response(r["status"])
        if r["location"] is not None:
            self.send_header("Location", r["location"])
        if r["json"] is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for c in r["set_cookie"]:
            self.send_header("Set-Cookie", c)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > payments.MAX_BODY:
            return b""
        return self.rfile.read(length)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _base_url(self):
        return payments.base_url_from(self.headers.get, "127.0.0.1:%d" % PORT)


if __name__ == "__main__":
    os.chdir(ROOT)
    key = payments.stripe_key()
    mode = "LIVE PAYMENTS" if key.startswith("sk_live") else \
        "test payments" if key else "payments OFF (set STRIPE_SECRET_KEY)"
    srv = HTTPServer(("127.0.0.1", PORT), partial(Handler, directory=ROOT))
    print("esportsboost preview → http://localhost:%d  [%s]" % (PORT, mode))
    print("  analytics → %s store, %d events · /ops %s"
          % (analytics.store_name(), analytics.count(),
             "unlocked with OPS_PASSWORD" if ops.configured()
             else "locked (set OPS_PASSWORD to open the dashboard)"))
    on = [p for p, ok in oauth.enabled().items() if ok]
    print("  social sign-in → %s"
          % (", ".join(on) + " enabled" if on
             else "OFF (set GOOGLE_/DISCORD_CLIENT_ID + _SECRET to enable)"))
    print("  outbound mail → %s%s"
          % (mailer.status(),
             "" if not mailer.configured()
             else " · tickets and order copies → %s" % mailer.support_addr()))
    srv.serve_forever()
