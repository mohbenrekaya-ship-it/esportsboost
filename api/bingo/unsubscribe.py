# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/bingo/unsubscribe?token=…

The opt-out at the foot of the mystery-discount follow-up mail. A thin shell
around `mystery.process_unsubscribe`; the logic is shared verbatim with
site/serve.py's route, and it exists as its own file for the reason
`api/cart/unsubscribe.py` does — every follow-up carries this link, and an
unsubscribe that 404s in production while working locally is a dead opt-out on
the same domain the order confirmations go out on.

One click, no login, no confirmation step. It answers 200 and a small HTML page
either way: whether a token exists is not something an unauthenticated caller
should be able to learn.

Unlike the cart's version this does **not** retire the offer — it sets `nomail`
and leaves the code redeemable. Voiding a live discount because somebody asked
for fewer emails punishes them for using the link.
"""
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "site", "src"))
import mystery  # noqa: E402

PAGE = (b"<!doctype html><meta charset=utf-8><title>Unsubscribed</title>"
        b"<style>body{background:#0b0a09;color:#e8e3dd;font:16px/1.6 "
        b"system-ui,sans-serif;display:grid;place-items:center;height:100vh;"
        b"margin:0;text-align:center}a{color:#ff7a3f}</style>"
        b"<div><h1>You're unsubscribed.</h1><p>We won't email you about "
        b"this order again. Your discount code still works.</p>"
        b"<p><a href=\"/\">Back to eSports Boost</a></p></div>")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
        mystery.process_unsubscribe(token)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PAGE)
