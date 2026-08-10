# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/session?id=cs_…

Success-page receipt lookup. Thin shell around payments.process_session.
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import payments  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        sid = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
        status, payload = payments.process_session(sid)
        self._json(status, payload)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
