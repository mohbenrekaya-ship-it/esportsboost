# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/checkout.

A thin HTTP shell around payments.process_checkout — the actual Stripe/pricing
logic is shared verbatim with the local server (site/serve.py). Zero third-party
packages; stdlib only.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import payments  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= payments.MAX_BODY else b""
        base = payments.base_url_from(self.headers.get, self.headers.get("host", ""))
        status, payload = payments.process_checkout(raw, base)
        self._json(status, payload)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
