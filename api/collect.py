# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/collect.

The analytics beacon endpoint. A thin HTTP shell around
analytics.process_collect — the validation and storage logic is shared verbatim
with the local server (site/serve.py). Zero third-party packages; stdlib only.

Always answers 204 with an empty body: `navigator.sendBeacon` discards the
response, and giving nothing back keeps a public write endpoint from doubling as
a read oracle.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import analytics  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= analytics.MAX_BODY else b""
        analytics.process_collect(raw, self.headers.get)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
