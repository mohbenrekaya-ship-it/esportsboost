# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/support.

The contact form on /support.html. A thin HTTP shell around
support.process_ticket — the validation, throttling and mail composition are
shared verbatim with the local server (site/serve.py).

Stores nothing: the ticket is composed as plain text and sent to the support
mailbox with the visitor's address in Reply-To (see site/src/support.py). An
unparseable or oversized body answers 204 with an empty body; an unconfigured
mailbox answers 503, which is what makes the page fall back to its preview
confirmation instead of claiming a mail went out.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import support  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= support.MAX_BODY else b""
        status, payload = support.process_ticket(raw, self.headers.get)
        if payload is None:                       # invalid → empty 204
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
