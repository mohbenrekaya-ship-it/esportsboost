# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/ops.

The analytics dashboard's only data source. A thin HTTP shell around
ops.process_ops — auth and aggregation are shared verbatim with the local server
(site/serve.py). Zero third-party packages; stdlib only.

Responses are `no-store` and `noindex`: dashboard numbers must never be cached
by an intermediary or picked up by a crawler.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import ops  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= ops.MAX_BODY else b""
        status, payload = ops.process_ops(raw)
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(body)
