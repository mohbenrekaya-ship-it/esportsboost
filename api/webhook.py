# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/webhook.

Receives Stripe events (checkout.session.completed → fulfilment). Signature is
verified when STRIPE_WEBHOOK_SECRET is set. Thin shell around
payments.process_webhook.

Note: on Vercel the filesystem is read-only apart from /tmp, so the order log is
best-effort — the durable record here is the stderr line in the function logs.
Point ORDER_LOG at /tmp/orders.log if you want the file write to succeed.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import payments  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= payments.MAX_BODY else b""
        sig = self.headers.get("Stripe-Signature", "")
        status, payload = payments.process_webhook(raw, sig)
        self._json(status, payload)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
