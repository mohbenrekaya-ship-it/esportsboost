# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/auth/:provider/callback.

The provider's redirect back: verifies the CSRF state, exchanges the code for a
token server-side, stores the verified lead, mints the session cookie, and
redirects to where sign-in began. Thin shell around oauth.dispatch — logic
shared verbatim with the local server (site/serve.py).
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "site", "src"))
import oauth     # noqa: E402
import payments  # noqa: E402  — base_url_from()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        base = payments.base_url_from(self.headers.get, self.headers.get("host", ""))
        r = oauth.dispatch(route, query, cookies, base, self.headers.get)
        if r["not_found"]:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"" if r["json"] is None else json.dumps(r["json"]).encode()
        self.send_response(r["status"])
        if r["location"] is not None:
            self.send_header("Location", r["location"])
        if r["json"] is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        for c in r["set_cookie"]:
            self.send_header("Set-Cookie", c)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)
