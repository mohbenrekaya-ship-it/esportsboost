# -*- coding: utf-8 -*-
"""The Meta Conversions API event: what it claims, and what it must never do.

Run: python3 site/tests/test_capi.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import capi                                                   # noqa: E402

RECORD = {"order_id": "ESB-3F92K1", "amount_total": 7799,
          "email": "  Buyer@Example.COM ", "at": 1762700000}
MD = {"currency": "eur", "detail": "Gold IV → Platinum II",
      "fbp": "fb.1.1762.999", "fbc": "fb.1.1762.abc",
      "ip": "203.0.113.9", "ua": "Mozilla/5.0", "country": "US"}


def test_event_id_is_the_order_id():
    """⚠ THE dedupe key. The browser pixel sends `eventID: order_id`; this must
    send the identical string as `event_id`, or Meta counts one sale twice and
    bids on revenue that does not exist."""
    ev = capi.build_event(RECORD, MD)
    assert ev["event_id"] == "ESB-3F92K1", ev.get("event_id")
    assert ev["event_name"] == "Purchase", ev["event_name"]
    print("ok  event_id is the order id")


def test_email_is_hashed_normalised_and_never_sent_raw():
    ev = capi.build_event(RECORD, MD)
    want = hashlib.sha256(b"buyer@example.com").hexdigest()
    assert ev["user_data"]["em"] == [want], ev["user_data"]["em"]
    blob = json.dumps(ev)
    for raw in ("Buyer@Example.COM", "buyer@example.com"):
        assert raw not in blob, "raw email in payload"
    print("ok  email hashed, trimmed and lower-cased; never raw")


def test_fbp_and_fbc_ride_raw():
    """They are opaque ids Meta issued itself. Hashing them matches nothing —
    a silent loss of exactly the attribution this module exists for."""
    ev = capi.build_event(RECORD, MD)
    assert ev["user_data"]["fbp"] == MD["fbp"]
    assert ev["user_data"]["fbc"] == MD["fbc"]
    print("ok  fbp/fbc sent unhashed")


def test_value_and_currency_travel_as_a_pair():
    """Meta reads a bare `value` against the ad account's own currency, so a
    €77.99 order would be banked as $77.99 and bid against on that."""
    ev = capi.build_event(RECORD, MD)
    assert ev["custom_data"]["value"] == 77.99, ev["custom_data"]
    assert ev["custom_data"]["currency"] == "EUR"

    no_cur = capi.build_event(RECORD, {k: v for k, v in MD.items()
                                       if k != "currency"})
    cd = no_cur["custom_data"]
    assert "value" not in cd and "currency" not in cd, cd
    print("ok  value and currency are all-or-nothing")


def test_cents_are_not_rounded_away():
    """Accounts are the one product priced in cents (pricing.charge_for), so a
    $77.99 sale must not be reported as $78."""
    ev = capi.build_event(RECORD, MD)
    assert ev["custom_data"]["value"] == 77.99
    print("ok  the cents survive")


def test_inert_without_a_token():
    """No token must mean no call and no pretending."""
    for var in ("META_CAPI_TOKEN",):
        os.environ.pop(var, None)
    assert capi.configured() is False
    res = capi.send_purchase(RECORD, MD)
    assert res["ok"] is False and res["reason"] == "not_configured", res
    print("ok  inert, and says so, with no token")


def test_an_event_with_nobody_in_it_is_not_sent():
    os.environ["META_CAPI_TOKEN"] = "test-token"
    try:
        res = capi.send_purchase({"order_id": "X", "at": 1}, {})
        assert res["ok"] is False and res["reason"] == "no_user_data", res
    finally:
        os.environ.pop("META_CAPI_TOKEN", None)
    print("ok  an unattributable event is refused, not sent as noise")


def test_send_never_raises():
    """It is called from inside the Stripe webhook, where an exception is a
    non-200, which is a redelivery, which is a second fulfilment."""
    os.environ["META_CAPI_TOKEN"] = "t"
    os.environ["META_PIXEL_ID"] = "1"
    try:
        for rec, md in ((None, None), ({}, {}), ({"order_id": object()}, {}),
                        (RECORD, {"currency": object()})):
            try:
                capi.send_purchase(rec or {}, md or {})
            except Exception as e:                            # noqa: BLE001
                raise AssertionError("send_purchase raised: %r" % e)
    finally:
        os.environ.pop("META_CAPI_TOKEN", None)
        os.environ.pop("META_PIXEL_ID", None)
    print("ok  never raises")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall capi tests passed")
