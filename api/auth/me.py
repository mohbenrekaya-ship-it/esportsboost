# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/auth/me.

The client's session probe: returns the current session (if the signed cookie
opens) and which OAuth providers are wired. Thin shell around oauth.dispatch —
all logic is shared verbatim with the local server (site/serve.py).
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "site", "src"))
import oauth     # noqa: E402
import payments  # noqa: E402  — base_url_from()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        base = payments.base_url_from(self.headers.get, self.headers.get("host", ""))
        r = oauth.dispatch(route, query, cookies, base, self.headers.get)
        _emit(self, r)


def _emit(h, r):
    body = b"" if r["json"] is None else json.dumps(r["json"]).encode()
    h.send_response(r["status"])
    if r["location"] is not None:
        h.send_header("Location", r["location"])
    if r["json"] is not None:
        h.send_header("Content-Type", "application/json; charset=utf-8")
    for c in r["set_cookie"]:
        h.send_header("Set-Cookie", c)
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    if body:
        h.wfile.write(body)
