# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/account.

The header auth endpoint (sign-up + sign-in). A thin HTTP shell around
accounts.process_signup — the validation, hashing and storage logic is shared
verbatim with the local server (site/serve.py). Zero third-party packages;
stdlib only.

Stores a name, an email and a salted PBKDF2 password hash (never a plaintext
password — see site/src/accounts.py). Sign-up / sign-in return a small JSON
status; an unknown mode or unparseable body answers 204 with an empty body.
The account list is readable only through the password-gated /api/ops.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import accounts  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= accounts.MAX_BODY else b""
        status, payload = accounts.process_signup(raw, self.headers.get)
        if payload is None:                       # log-in / invalid → empty 204
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        body = json.dumps(payload).encode()       # create → JSON status
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
