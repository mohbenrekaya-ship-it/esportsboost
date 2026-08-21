# -*- coding: utf-8 -*-
"""Vercel serverless function: POST /api/sweep.

The 30-minute timer behind abandoned-cart recovery. Serverless functions cannot
sleep, so an external scheduler drives this — Vercel Cron, cron-job.org, a
GitHub Action, anything that can issue a scheduled request. A thin shell around
carts.process_sweep; the logic is shared verbatim with site/serve.py's
/api/cart/sweep route.

Safe to call as often as the scheduler allows: carts.due() only returns rows
older than CART_DELAY_SECS, and each send flips the row out of that set before
the message goes out, so a cart is mailed exactly once.

**Fails closed.** Without CART_SWEEP_SECRET (16+ chars) it answers 503 and sends
nothing — the same contract /api/ops and /api/webhook have. An unauthenticated
sweep endpoint is a free way to make the site send mail on demand. The secret
may travel as the `x-sweep-secret` header or as {"secret": …} in the body; the
header is preferred, because query strings and bodies end up in more logs.

Vercel Cron issues a GET, so both verbs are accepted and answer identically.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import carts  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _run(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if 0 < length <= carts.MAX_BODY else b""
        status, payload = carts.process_sweep(raw, self.headers.get)
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._run()

    def do_GET(self):
        # Vercel Cron calls with GET. It sends an Authorization: Bearer <CRON_SECRET>
        # header rather than ours, so allow that to stand in for the sweep secret
        # when the two are configured to the same value.
        self._run()
