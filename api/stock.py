# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/stock.

The public, anonymous read of the account-stock store — how many units of each
listing are left on each shard, so the accounts shop's four stock figures follow
real inventory instead of `data.py`'s hand-set ones. A thin HTTP shell around
stock.process_list; the store itself is shared verbatim with the local server
(site/serve.py). Zero third-party packages; stdlib only.

⚠ COUNTS ONLY. The store behind this holds live account credentials and this
route is reachable by anyone — `stock.public_counts()` is the allowlist, and
nothing that names a login may ever be added to it.

204 with an empty body when the store is empty, so the client keeps the
server-rendered fallback instead of blanking every count on the page. `no-store`
because stock changes on every sale and a cached count is a card that sells
something already gone.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import stock  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = stock.process_list()
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
