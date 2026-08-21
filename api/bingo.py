# -*- coding: utf-8 -*-
"""Vercel serverless function: /api/bingo.

The mystery-discount flow's endpoint (design_handoff_mystery_discount). A thin
HTTP shell around mystery.process_* — the validation, storage, token and mail
logic is shared verbatim with the local server (site/serve.py). Zero third-party
packages; stdlib only.

  * **POST** captures the email the modal asked for and issues ONE single-use,
    one-hour discount token against it, mailing the code before it answers.
    Public and unauthenticated, like /api/collect — the modal is on nine public
    pages. A signed-in visitor's address is taken from the verified session
    cookie, never the body. `{"action": "apply"}` records that the reveal's
    Apply was pressed and issues nothing.
  * **GET ?token=** resolves a token to its percentage. This is the only route
    to that number: it is deliberately NOT in data.js, so a client cannot learn
    the discount without a token the server issued, and the one-hour deadline is
    enforced here rather than trusted to a countdown in the browser. Unknown,
    already-spent and expired tokens all answer {"valid": false}.

Holds PII (an email, a country) next to a token that resolves to real money, so
it is a **separate store** — see site/src/mystery.py — readable only through the
password-gated /api/ops.
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import mystery  # noqa: E402
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
        raw = self.rfile.read(length) if 0 < length <= mystery.MAX_BODY else b""
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        sess = oauth.read_session(cookies.get(oauth.SESSION_COOKIE))
        status, payload = mystery.process_issue(
            raw, self.headers.get, session_email=(sess or {}).get("email", ""))
        self._send(status, payload)

    def do_GET(self):
        token = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
        status, payload = mystery.process_resolve(token)
        self._send(status, payload)
