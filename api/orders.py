# -*- coding: utf-8 -*-
"""Vercel serverless function: GET /api/orders.

The signed-in customer's OWN orders, for /orders.html. A thin HTTP shell around
orders.customer_view — the store read and the split into active/delivered are
shared verbatim with the local server (site/serve.py).

Authenticated by the signed session cookie alone (oauth.read_session): the email
is taken from the verified session, never from the request, so no one can read
another customer's orders. Not signed in → {"authenticated": false}, and the
page renders its sign-in / empty state. Read-only; writes only ever come from
the Stripe webhook (payments._record_order).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site", "src"))
import oauth   # noqa: E402
import orders  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cookies = oauth.parse_cookies(self.headers.get("Cookie"))
        session = oauth.read_session(cookies.get(oauth.SESSION_COOKIE))
        if not session or not session.get("email"):
            payload = {"authenticated": False}
        else:
            payload = orders.customer_view(session["email"])
            payload.update({"authenticated": True, "name": session.get("name", ""),
                            "email": session.get("email", "")})
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
