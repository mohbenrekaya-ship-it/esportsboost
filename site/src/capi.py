# -*- coding: utf-8 -*-
"""Meta Conversions API — the server-side twin of the browser Purchase pixel.

The pixel on `/checkout/success` is the only thing telling Meta a sale happened,
and it is the least reliable reporter in the stack: it needs the buyer to land
back on the success page with scripting intact, which an ad blocker, a closed
tab, a dead battery or iOS tracking prevention each defeat on their own. The
money, meanwhile, is confirmed server-side in `/api/webhook`, where none of that
applies. This module reports from there.

It is deliberately NOT the Conversions API Gateway. That product provisions a
cloud proxy on a recurring bill, for shops with no backend; this site confirms
every payment in a function it already runs, so the gateway would be a paid hop
between two things we own.

⚠ THE TWO EVENTS MUST DEDUPE OR EVERY SALE IS COUNTED TWICE, and `event_id` is
the whole mechanism: Meta drops a (event_name, event_id) pair it has already
seen for 48 hours. The pixel sends `eventID: order_id` (build.py, the Purchase
block) and this sends `event_id: order_id`. They are the same string because
they are the same order. Change one and you have double-counted revenue that
Ads Manager will bid on.

House rules, same as payments.py: stdlib only, no packages. Never raises — it
is called from inside the webhook, where an exception is a non-200, which is a
Stripe redelivery, which is a second fulfilment.

Config is env-only:
    META_CAPI_TOKEN    a System User access token with ads_management.
                       REQUIRED — with none set this module is inert and says
                       so once, rather than pretending.
    META_PIXEL_ID      the dataset, defaulting to the same id build.py ships to
                       the browser, so the two halves cannot address different
                       datasets by accident.
    META_CAPI_TEST_CODE  optional; routes events to Events Manager's Test
                       Events tab instead of the live dataset.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = "v21.0"
HTTP_TIMEOUT = 6


def _token():
    return os.environ.get("META_CAPI_TOKEN", "").strip()


def _dataset():
    # Same default as build.py's META_PIXEL_ID: the browser pixel and this must
    # address one dataset, or the deduplication above has nothing to dedupe
    # against and both events land as separate sales.
    return os.environ.get("META_PIXEL_ID", "1145104387855719").strip()


def configured():
    return bool(_token() and _dataset())


def _sha(value):
    """Meta requires every personal identifier SHA-256'd, over a normalised
    value: trimmed and lower-cased. Hashing an untrimmed or mixed-case address
    produces a different digest from the one Meta computes for the same person,
    which does not error — it silently fails to match and quietly costs you the
    attribution this module exists to get."""
    v = (value or "").strip().lower()
    if not v:
        return ""
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def build_event(record, md, event_source_url=""):
    """One Purchase event from what the webhook already holds.

    `record` is payments.py's own dict (order id, amount_total in CENTS, email);
    `md` is the Stripe metadata, which is where the browser cookies and the
    currency ride.
    """
    order_id = str(record.get("order_id") or "")
    user = {}

    em = _sha(record.get("email"))
    if em:
        user["em"] = [em]

    # fbp / fbc are Meta's own browser cookies and are sent RAW — they are
    # already opaque identifiers, and hashing them matches nothing. They are the
    # difference between an event Meta can attribute to a click and one it
    # cannot, which is why checkout captures them into the metadata at all.
    if md.get("fbp"):
        user["fbp"] = str(md["fbp"])[:255]
    if md.get("fbc"):
        user["fbc"] = str(md["fbc"])[:255]
    # Also unhashed, per Meta's schema.
    if md.get("ip"):
        user["client_ip_address"] = str(md["ip"])[:64]
    if md.get("ua"):
        user["client_user_agent"] = str(md["ua"])[:500]
    if md.get("country"):
        user["country"] = _sha(md["country"])

    custom = {"content_type": "product"}
    # value and currency travel as a PAIR or not at all — the same rule the
    # browser pixel follows. Meta reads a bare `value` against the ad account's
    # own currency, so a €79 order would be banked as $79 of revenue and bid on.
    amount, cur = record.get("amount_total"), md.get("currency")
    if isinstance(amount, (int, float)) and cur:
        custom["value"] = round(float(amount) / 100.0, 2)
        custom["currency"] = str(cur).upper()
    if md.get("detail"):
        custom["content_name"] = str(md["detail"])[:200]
    if order_id:
        custom["order_id"] = order_id

    ev = {
        "event_name": "Purchase",
        "event_time": int(record.get("at") or time.time()),
        "action_source": "website",
        "user_data": user,
        "custom_data": custom,
    }
    if order_id:
        ev["event_id"] = order_id          # ⚠ dedupe key — see the module note
    if event_source_url:
        ev["event_source_url"] = event_source_url
    return ev


def send_purchase(record, md, event_source_url=""):
    """POST one Purchase. Returns a small dict; never raises.

    The return value is for the log line and the tests, not for the webhook —
    a failure here must not change what the webhook answers Stripe.
    """
    if not configured():
        return {"ok": False, "reason": "not_configured"}
    ev = build_event(record, md, event_source_url)
    # No identifiers at all means Meta cannot attribute it to anyone, and the
    # event is pure noise in the dataset. Say so rather than sending it.
    if not ev["user_data"]:
        return {"ok": False, "reason": "no_user_data"}

    payload = {"data": json.dumps([ev])}
    test_code = os.environ.get("META_CAPI_TEST_CODE", "").strip()
    if test_code:
        payload["test_event_code"] = test_code

    url = "https://graph.facebook.com/%s/%s/events" % (API_VERSION, _dataset())
    body = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 # The token goes in a header, never the query string: a URL is
                 # the thing most likely to end up in a log or an error message.
                 "Authorization": "Bearer " + _token()})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            out = json.loads(r.read().decode() or "{}")
        return {"ok": True, "received": out.get("events_received"),
                "event_id": ev.get("event_id", "")}
    except urllib.error.HTTPError as e:
        # Meta's error body names the real problem (expired token, wrong
        # dataset, malformed field). Swallowing it is how this goes unnoticed
        # for a month, exactly as the analytics store did.
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:                                      # noqa: BLE001
            pass
        return {"ok": False, "reason": "http_%s" % e.code, "detail": detail}
    except Exception as e:                                     # noqa: BLE001
        return {"ok": False, "reason": "unreachable", "detail": str(e)[:200]}


def log_result(order_id, res):
    """One stderr line per order, whatever happened. The analytics store spent
    months reporting a confident zero because its failures went nowhere."""
    if res.get("reason") == "not_configured":
        return
    sys.stderr.write(
        "[capi] %s → %s%s\n"
        % (order_id or "?",
           "sent" if res.get("ok") else "FAILED (%s)" % res.get("reason"),
           (" " + res["detail"]) if res.get("detail") else ""))
