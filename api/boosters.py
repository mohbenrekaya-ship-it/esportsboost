# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/boosters.

The public, anonymous read of the roster store — the dynamic source for the
boosters board, the homepage "On shift now" rail and the "Delivered today" feed.
A thin HTTP shell around boosters.process_list; the store and the display payload
are shared verbatim with the local server (site/serve.py). Zero third-party
packages; stdlib only.

204 with an empty body when the store is empty, so the client keeps the
server-rendered fallback instead of blanking those panels. `no-store` because the
payload rotates per request and must never be cached by an intermediary.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import boosters  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = boosters.process_list()
        if payload is None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
