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
        p = super().translate_path(path.split("?", 1)[0])
        if not os.path.exists(p) and not path.rstrip("/").endswith(".html"):
            alt = p.rstrip("/") + ".html"
            if os.path.isfile(alt):
                return alt
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

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
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
