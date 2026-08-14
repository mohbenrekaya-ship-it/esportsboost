# -*- coding: utf-8 -*-
"""Stripe payment logic, shared by the local server and the Vercel functions.

Both `site/serve.py` (long-running preview/dev server) and the serverless
functions in `/api/*.py` are thin HTTP shells around the three `process_*`
handlers below — so the checkout, receipt-lookup and webhook logic lives in
exactly one place, and stays true to the project's rule of no third-party
packages: it talks to Stripe's REST API directly over urllib and verifies
webhook signatures with the stdlib hmac/hashlib.

Configuration is env-only, never committed:

    STRIPE_SECRET_KEY     required to take payment (use sk_test_… in dev)
    STRIPE_WEBHOOK_SECRET optional, enables /api/webhook signature checks
    PUBLIC_BASE_URL       optional success/cancel origin, else inferred
    ORDER_LOG             optional path for the fulfilment log (see note)

With no key set, `process_checkout`/`process_session` return a 503 so the
checkout page falls back to its local preview confirmation.

Note on persistence: the webhook appends fulfilled orders to ORDER_LOG. On a
serverless host (Vercel) the filesystem is read-only apart from /tmp, so that
write is best-effort — the durable signal there is the stderr log line, which
shows up in the function logs. A real deployment would swap this seam for a
database or a queue.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import data as D  # noqa: E402  — the roster a named booster is resolved against
import pricing  # noqa: E402  — authoritative price, never trust the client

STRIPE_API = "https://api.stripe.com/v1"
MAX_BODY = 64 * 1024  # a checkout payload is tiny; cap it hard


def stripe_key():
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def webhook_secret():
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def order_log_path():
    return os.environ.get("ORDER_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "orders.log")


class StripeError(Exception):
    pass


def stripe_call(path, params=None, method="POST"):
    """One authenticated call to Stripe's REST API. Returns parsed JSON.
    Raises StripeError with the message Stripe gave us on a 4xx/5xx."""
    url = STRIPE_API + path
    data = urllib.parse.urlencode(params or {}, doseq=True).encode() if params else None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    auth = base64.b64encode((stripe_key() + ":").encode()).decode()
    req.add_header("Authorization", "Basic " + auth)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode()).get("error", {})
            msg = err.get("message") or e.reason
        except Exception:
            msg = str(e.reason)
        raise StripeError(msg)


def new_order_id():
    return "ESB-" + base64.b32encode(os.urandom(4)).decode().rstrip("=")[:6]


def build_session(order, base_url):
    """Turn a validated order into Stripe Checkout Session params. The amount
    comes from pricing.quote() — the client-supplied total is ignored."""
    q = pricing.quote(order)
    if q["invalid"]:
        raise StripeError(q["summary"])

    game = order.get("game", "")
    region = order.get("region", "")
    # A booster the customer named on the roster or a profile page. Resolved
    # against the real roster, never taken as written — the browser POSTs it,
    # and an unrecognised handle must not reach fulfilment as an assignment.
    # It carries no charge: there is no named-booster fee in quote(), so this
    # cannot move the amount and the profile page says so out loud.
    named = str(order.get("booster") or "").strip()
    booster = named if any(b["handle"] == named for b in D.BOOSTERS) else ""
    order_id = new_order_id()
    name = "%s boost" % game
    # What the customer sees on the Stripe page: the climb (from → to) and the
    # mode (Solo/Duo) from q["summary"], plus the named booster when they chose
    # one. Region, promo and the rest still ride in metadata for fulfilment.
    desc = q["summary"]
    if booster:
        desc += " · with %s" % booster

    params = {
        "mode": "payment",
        "success_url": base_url + "/checkout/success.html?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base_url + "/checkout.html?canceled=1",
        "client_reference_id": order_id,
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": q["total_cents"],
        "line_items[0][price_data][product_data][name]": name,
        "line_items[0][price_data][product_data][description]": desc,
        # order details ride along so fulfilment (webhook) has what it needs
        "metadata[order_id]": order_id,
        "metadata[game]": game,
        "metadata[service]": order.get("service", ""),
        "metadata[detail]": q["summary"][:490],
        "metadata[region]": region,
        "metadata[booster]": booster,
        "metadata[hours]": (order.get("hours") or "")[:490],
        "metadata[notes]": (order.get("notes") or "")[:490],
        "metadata[eta]": q["eta"],
        "metadata[promo]": q["promo_code"],
        "metadata[discount]": str(q["discount"]),
        "metadata[subtotal]": str(q["subtotal"]),
    }
    email = order.get("email", "").strip()
    if email:
        params["customer_email"] = email
    return params, order_id, q


# ── HTTP-agnostic route handlers — return (status_code, json_dict) ──────────


def process_checkout(raw, base_url):
    """POST /api/checkout body → (status, payload). `raw` is the request body
    bytes; `base_url` is the public origin for Stripe's redirect URLs."""
    if not stripe_key():
        # Not configured — let the page fall back to its preview confirmation.
        return 503, {"error": "payments_not_configured"}
    try:
        order = json.loads((raw or b"").decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return 400, {"error": "Malformed request"}
    if not isinstance(order, dict):
        return 400, {"error": "Malformed request"}
    try:
        params, order_id, q = build_session(order, base_url)
        session = stripe_call("/checkout/sessions", params)
    except StripeError as e:
        return 400, {"error": str(e)}
    return 200, {"url": session.get("url"), "order_id": order_id, "total": q["total"]}


def process_session(sid):
    """GET /api/session?id=cs_… → (status, receipt payload)."""
    if not stripe_key():
        return 503, {"error": "payments_not_configured"}
    if not sid or not sid.startswith("cs_"):
        return 400, {"error": "Missing session id"}
    try:
        s = stripe_call("/checkout/sessions/" + urllib.parse.quote(sid), method="GET")
    except StripeError as e:
        return 400, {"error": str(e)}
    md = s.get("metadata") or {}
    return 200, {
        "paid": s.get("payment_status") == "paid",
        "order_id": s.get("client_reference_id") or md.get("order_id"),
        "amount_total": s.get("amount_total"),
        "currency": s.get("currency"),
        "email": (s.get("customer_details") or {}).get("email"),
        "detail": md.get("detail"), "eta": md.get("eta"),
    }


def process_webhook(raw, sig_header):
    """POST /api/webhook → (status, payload). Verifies the Stripe signature when
    STRIPE_WEBHOOK_SECRET is set, then fulfils checkout.session.completed."""
    if webhook_secret() and not _verify_sig(raw, sig_header):
        return 400, {"error": "Bad signature"}
    try:
        event = json.loads((raw or b"").decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return 400, {"error": "Malformed event"}
    if event.get("type") == "checkout.session.completed":
        obj = event.get("data", {}).get("object", {})
        md = obj.get("metadata") or {}
        record = {
            "at": int(time.time()),
            "order_id": obj.get("client_reference_id") or md.get("order_id"),
            "amount_total": obj.get("amount_total"),
            "email": (obj.get("customer_details") or {}).get("email"),
            "detail": md.get("detail"), "game": md.get("game"),
            "region": md.get("region"), "notes": md.get("notes"),
        }
        # Fulfilment hook: in production this is where the order joins the
        # booster board and the confirmation email leaves. Here we log it —
        # to a file when the FS is writable, and always to stderr.
        try:
            with open(order_log_path(), "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass
        sys.stderr.write("paid order → %s\n" % record.get("order_id"))
    return 200, {"received": True}


def _verify_sig(payload, header):
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    t, v1 = parts.get("t"), parts.get("v1")
    if not t or not v1:
        return False
    signed = ("%s." % t).encode() + (payload or b"")
    expected = hmac.new(webhook_secret().encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return False
    # reject events older than 5 minutes (replay protection)
    try:
        return abs(time.time() - int(t)) <= 300
    except ValueError:
        return False


def base_url_from(get_header, fallback_host):
    """Build the public origin from request headers. Prefers PUBLIC_BASE_URL,
    then the forwarded proto + Host (Vercel sits behind TLS termination)."""
    env = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    host = get_header("host") or fallback_host
    fwd = get_header("x-forwarded-proto")
    if fwd:
        proto = fwd.split(",")[0].strip()
    else:
        # No proxy header → a direct connection. The local dev server speaks
        # plain HTTP, so localhost must not be handed an https redirect or Stripe
        # sends the browser back to https://localhost → ERR_SSL_PROTOCOL_ERROR.
        # Any real host reached directly still defaults to https.
        proto = "http" if host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0") else "https"
    return "%s://%s" % (proto, host)
