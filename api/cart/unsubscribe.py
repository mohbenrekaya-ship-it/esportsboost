# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/cart/unsubscribe?token=…

The one-click opt-out carried by every abandoned-cart recovery mail. A thin
shell around carts.process_unsubscribe; the logic is shared verbatim with
site/serve.py's route of the same path, and this file exists because that route
had no serverless twin — the link 404'd in production while working locally.

  * **One click, no login, no confirmation step.** An unsubscribe that asks the
    reader to authenticate is an unsubscribe that does not work, and it is the
    same domain the order confirmations go out on.
  * **200 either way.** Whether a token exists is not something an
    unauthenticated caller should be able to learn by watching status codes.
  * **A page, not JSON** — a human clicked this in their mail client.
"""
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "site", "src"))
import carts  # noqa: E402

PAGE = (b"<!doctype html><meta charset=utf-8><title>Unsubscribed</title>"
        b"<style>body{background:#0b0a09;color:#e8e3dd;font:16px/1.6 "
        b"system-ui,sans-serif;display:grid;place-items:center;height:100vh;"
        b"margin:0;text-align:center}a{color:#ff7a3f}</style>"
        b"<div><h1>You're unsubscribed.</h1><p>We won't email you about "
        b"this order again.</p><p><a href=\"/\">Back to eSports Boost</a>"
        b"</p></div>")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
        carts.process_unsubscribe(token)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PAGE)
