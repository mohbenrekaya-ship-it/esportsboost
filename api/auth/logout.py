# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/auth/logout.

Clears the session cookie. Thin shell around oauth.dispatch — logic shared
verbatim with the local server (site/serve.py).
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
    def do_POST(self):
        route = urllib.parse.urlsplit(self.path).path
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        base = payments.base_url_from(self.headers.get, self.headers.get("host", ""))
        r = oauth.dispatch(route, {}, cookies, base, self.headers.get)
        body = b"" if r["json"] is None else json.dumps(r["json"]).encode()
        self.send_response(r["status"])
        for c in r["set_cookie"]:
            self.send_header("Set-Cookie", c)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)
