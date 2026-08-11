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
import analytics  # noqa: E402  — first-party event ingest (also used by /api)
import ops        # noqa: E402  — gated dashboard API (also used by /api)
import payments   # noqa: E402  — shared Stripe/pricing logic (also used by /api)


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
        if route == "/api/ops":
            status, payload = ops.process_ops(self._read_body())
            return self._json(status, payload)
        self.send_error(404)

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/session":
            sid = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
            status, payload = payments.process_session(sid)
            return self._json(status, payload)
        if route.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

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
    srv.serve_forever()
