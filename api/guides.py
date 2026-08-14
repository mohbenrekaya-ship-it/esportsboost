# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/guides.

The free-guides landing's lead endpoint. A thin HTTP shell around
guides.process_lead — the validation and storage logic is shared verbatim with
the local server (site/serve.py). Zero third-party packages; stdlib only.

Stores an email, which guides were picked, and whether the visitor opted into
the monthly mail — never a password (this is a mailing list, not an account; see
site/src/guides.py). Returns a small JSON status; an unparseable or oversized
body answers 204 with an empty body. The list is readable only through the
password-gated /api/ops.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import guides  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= guides.MAX_BODY else b""
        status, payload = guides.process_lead(raw, self.headers.get)
        if payload is None:                       # invalid → empty 204
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
