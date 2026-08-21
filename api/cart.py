# -*- coding: utf-8 -*-
"""Vercel serverless function: /api/cart.

Abandoned-checkout capture. A thin HTTP shell around carts.process_* — the
validation, storage and token logic is shared verbatim with the local server
(site/serve.py). Zero third-party packages; stdlib only.

  * **POST** captures the email a buyer typed into the checkout form, next to
    the configuration they were building. Public and unauthenticated, like
    /api/collect — the form is reachable by anyone. A bad body answers 204.
  * **GET ?token=** resolves a recovery token to its discount. This is the only
    route to that percentage: it is deliberately NOT in data.js, so a client
    cannot learn it without a token the server issued. Unknown, already-spent
    and expired tokens all answer {"valid": false}.

Holds PII (an email, a country), so it is a **separate store** from the
anonymous analytics events — see site/src/carts.py — and is readable only
through the password-gated /api/ops.
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import carts  # noqa: E402
import oauth  # noqa: E402 — verified session → the signed-in visitor's email


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        if payload is None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= carts.MAX_BODY else b""
        # Signed-in visitors are captured while they configure, with no field to
        # fill: the address comes from the verified session cookie, never the
        # body. Mirrors serve.py's /api/cart route.
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        sess = oauth.read_session(cookies.get(oauth.SESSION_COOKIE))
        status, payload = carts.process_capture(
            raw, self.headers.get, session_email=(sess or {}).get("email", ""))
        self._send(status, payload)

    def do_GET(self):
        token = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
        status, payload = carts.process_resolve(token)
        self._send(status, payload)
