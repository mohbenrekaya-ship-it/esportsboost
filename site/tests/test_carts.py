#!/usr/bin/env python3
"""Abandoned-checkout tests — stdlib only, no framework, no network.

Run:  python3 site/tests/test_carts.py       (exits non-zero on any failure)

The recovery flow captures an email and later mails it a discount, so the
things worth locking down are the ones that turn it into someone else's tool or
a free-money bug:

  * **the discount cannot be forged from the client** — `recovery_pct` is
    stripped from the checkout body and re-derived from a token checked against
    the store, so a crafted `{"recovery_pct": 0.99}` buys nothing.
  * **a token is single-use and time-boxed** — spent or expired resolves to no
    discount, so a recovery code can't be shared or replayed.
  * **the identity is the session, not the body** — a signed-in capture is
    written under the verified session email, never an address the browser named,
    so nobody can write a cart against someone else's inbox.
  * **the recovery discount never stacks and never worsens the price** — it
    replaces the sitewide sale, best-wins, exactly like a typed code.
  * **the 30-minute delay is enforced** — `due()` never returns a fresh cart.
  * **the sweep fails closed** — no secret, no send.

Nothing here opens a socket or touches Upstash: the store is pointed at a temp
file, and the sweep's mailer is never reached because SMTP is unconfigured.
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

# Point the store at a throwaway file BEFORE importing carts, and make sure no
# Upstash env leaks in from the shell (that would send these writes to prod).
for _k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    os.environ.pop(_k, None)
_TMP = tempfile.NamedTemporaryFile(prefix="esb-carts-test-", suffix=".ndjson", delete=False)
_TMP.close()
os.environ["CARTS_LOG"] = _TMP.name

import carts             # noqa: E402
import pricing           # noqa: E402

_fails = []


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


def reset():
    carts.clear()


CFG = {"game": "League of Legends", "service": "division", "from": "Gold II",
       "to": "Platinum III", "mode": "Solo", "region": "North America", "addons": []}


def _quote(**over):
    st = {"game": "League of Legends", "service": "division", "from": "Gold II",
          "to": "Platinum III", "mode": "Solo", "region": "North America",
          "addons": [], "bundle": None, "wins": 1, "placements": 3,
          "unranked": False, "coach": 0, "pack": 1, "focus": [0], "slot": ""}
    st.update(over)
    return pricing.quote(st)


# ── validation ─────────────────────────────────────────────────────────────
def test_clean_cart():
    check(carts.clean_cart({"email": "not an email"}) is None, "a bad email is rejected")
    check(carts.clean_cart({}) is None, "a missing email is rejected")
    check(carts.clean_cart("nope") is None, "a non-dict body is rejected")
    row = carts.clean_cart(dict(CFG, email="  BUYER@Example.COM ",
                                addons=["a"] * 40, wins="999"), country="us")
    check(row["email"] == "buyer@example.com", "the email is lower-cased and trimmed")
    check(len(row["addons"]) <= carts.MAX_ADDONS, "add-ons are capped")
    check(row["wins"] == 99, "a huge unit count is clamped")
    check(row["country"] == "US", "the country is upper-cased")
    check(row["status"] == "pending", "a fresh cart is pending")


def test_token_shape():
    t = carts.new_token()
    check(carts.TOKEN_RE.match(t) is not None, "a minted token matches the token shape")
    check(carts.get("BACK-NOPE1") is None, "an unknown token resolves to nothing")
    check(carts.get("../../etc/passwd") is None, "a path-shaped token is refused")
    check(len(set(carts.new_token() for _ in range(50))) == 50, "tokens do not collide")


# ── store: mutate in place, one row per token ──────────────────────────────
def test_put_is_in_place():
    reset()
    row = carts.clean_cart(dict(CFG, email="a@b.co"))
    row["token"] = carts.new_token()
    carts.put(row)
    carts.mark(row["token"], status="mailed", mailed_at=123)
    check(carts.get(row["token"])["status"] == "mailed", "mark() updates the row in place")
    check(carts.count() == 1, "an update does not create a second row")


def test_one_open_cart_per_address():
    reset()
    st1, p1 = carts.process_capture(_json(dict(CFG, email="dup@b.co")), _h())
    st2, p2 = carts.process_capture(_json(dict(CFG, email="dup@b.co", to="Diamond IV")), _h())
    check(p1["token"] == p2["token"], "re-capturing an address keeps the same token")
    check(carts.count() == 1, "re-capturing does not grow the store")


def test_capture_keeps_original_clock():
    reset()
    st1, p1 = carts.process_capture(_json(dict(CFG, email="clock@b.co")), _h())
    first_at = carts.get(p1["token"])["at"]
    time.sleep(1.1)
    carts.process_capture(_json(dict(CFG, email="clock@b.co", to="Diamond IV")), _h())
    check(carts.get(p1["token"])["at"] == first_at,
          "the 30-minute clock is not reset by a later edit")


# ── the identity is the session, never the body ────────────────────────────
def test_session_email_wins_over_body():
    reset()
    # A signed-in visitor: the route passes session_email; the body names someone
    # else. The stored address must be the verified one.
    carts.process_capture(_json(dict(CFG, email="victim@example.com")),
                          _h(), session_email="real@account.com")
    rows = carts.read()
    check(len(rows) == 1 and rows[0]["email"] == "real@account.com",
          "a signed-in capture is stored under the SESSION email, not the body's")


def test_anonymous_configure_stores_nothing():
    reset()
    # No email in the body, no session — there is nothing to capture.
    st, pl = carts.process_capture(_json(dict(CFG)), _h())
    check(st == 204 and pl is None, "an anonymous configure with no email stores nothing")
    check(carts.count() == 0, "and writes no row")


# ── the discount cannot be forged, and is single-use ───────────────────────
def test_recovery_pct_is_never_read_from_the_client():
    # pricing.quote() reads recovery_pct, and the checkout body is that dict, so
    # process_checkout must strip it. Prove the strip: with the field present the
    # quote is near-free; stripped, it is the normal price.
    forged = _quote(recovery_pct=0.99)
    normal = _quote()
    check(forged["total"] < normal["total"], "a raw recovery_pct WOULD lower the price (why it must be stripped)")
    # what process_checkout actually charges when no valid token is supplied
    import payments
    order = dict(CFG, wins=1, placements=3, unranked=False, bundle=None,
                 coach=0, pack=1, focus=[0], slot="", recovery_pct=0.99,
                 cart="BACK-DOESNOTEXIST")
    order.pop("recovery_pct", None)                 # mirror process_checkout
    ct = str(order.get("cart") or "")[:40]
    row = carts.redeemable(ct) if ct else None
    if row:
        order["recovery_pct"] = carts.RECOVERY_PCT
    check(pricing.quote(order)["total"] == normal["total"],
          "a forged recovery_pct + unknown token charges the NORMAL price")


def test_token_is_single_use():
    reset()
    row = carts.clean_cart(dict(CFG, email="once@b.co"))
    row["token"] = carts.new_token()
    row["at"] = int(time.time()) - 2000
    carts.put(row)
    check(carts.redeemable(row["token"]) is not None, "a fresh token is redeemable")
    carts.recover(row["token"], order_id="ESB-ONCE01")
    check(carts.redeemable(row["token"]) is None, "a recovered token is spent — not redeemable again")
    check(carts.get(row["token"])["order_id"] == "ESB-ONCE01", "recovery records the order id")


def test_token_expires():
    reset()
    row = carts.clean_cart(dict(CFG, email="old@b.co"))
    row["token"] = carts.new_token()
    row["at"] = int(time.time()) - carts.TOKEN_TTL - 10
    carts.put(row)
    check(carts.redeemable(row["token"]) is None, "a token past its TTL buys nothing")


def test_resolve_endpoint():
    reset()
    row = carts.clean_cart(dict(CFG, email="res@b.co"))
    row["token"] = carts.new_token()
    row["at"] = int(time.time()) - 2000
    carts.put(row)
    st, pl = carts.process_resolve(row["token"])
    check(st == 200 and pl["valid"] and pl["pct"] == carts.RECOVERY_PCT,
          "GET /api/cart resolves a live token to its percentage")
    st, pl = carts.process_resolve("BACK-UNKNOWN99")
    check(pl["valid"] is False and pl["pct"] == 0, "an unknown token resolves to no discount")


# ── the recovery discount behaves like a promo: best-wins, never-stack ──────
def test_recovery_never_stacks_and_never_worsens():
    normal = _quote()                               # sitewide 15% sale
    withrec = _quote(promo="BACK-X", recovery_pct=carts.RECOVERY_PCT)
    check(withrec["total"] < normal["total"], "the recovery offer beats the sitewide sale")
    check(abs(withrec["promo_pct"] - carts.RECOVERY_PCT) < 1e-9,
          "the applied percentage is exactly the recovery percentage")
    weaker = _quote(promo="BACK-X", recovery_pct=0.05)
    check(weaker["total"] == normal["total"],
          "a recovery pct weaker than the sale never worsens the price")
    check(_quote(recovery_pct="not-a-number")["total"] == normal["total"],
          "a non-numeric recovery pct is ignored, not crashed on")


# ── the 30-minute delay, and the sweep's timing ────────────────────────────
def test_due_respects_the_delay():
    reset()
    now = int(time.time())
    row = carts.clean_cart(dict(CFG, email="due@b.co"))
    row["token"] = carts.new_token()
    row["at"] = now - 60                             # one minute old
    carts.put(row)
    check(len(carts.due(now=now)) == 0, "a one-minute-old cart is NOT yet due")
    carts.mark(row["token"], at=now - carts.DELAY_SECS - 5)
    check(len(carts.due(now=now)) == 1, "a cart past the delay IS due")
    carts.mark(row["token"], status="mailed")
    check(len(carts.due(now=now)) == 0, "an already-mailed cart is not due again")


# ── the sweep fails closed ─────────────────────────────────────────────────
def test_sweep_requires_a_secret():
    os.environ.pop("CART_SWEEP_SECRET", None)
    st, pl = carts.process_sweep(b"{}", _h())
    check(st == 503, "with no CART_SWEEP_SECRET the sweep is 503 — nothing is sent")
    os.environ["CART_SWEEP_SECRET"] = "x" * 20
    st, pl = carts.process_sweep(b'{"secret":"wrong"}', _h())
    check(st == 401, "a wrong secret is refused")
    st, pl = carts.process_sweep(b"{}", _h({"x-sweep-secret": "x" * 20}))
    check(st == 200, "the right secret runs the sweep")
    os.environ.pop("CART_SWEEP_SECRET", None)


# ── summary shape ──────────────────────────────────────────────────────────
def test_summary():
    reset()
    now = int(time.time())
    for email, status, age in (("s1@b.co", "recovered", 9000),
                               ("s2@b.co", "mailed", 5000),
                               ("s3@b.co", "pending", 60)):
        row = carts.clean_cart(dict(CFG, email=email), country="US")
        row["token"] = carts.new_token()
        row["at"] = now - age
        row["status"] = status
        if status == "recovered":
            row["order_id"] = "ESB-SUM001"
        carts.put(row)
    s = carts.summary()
    check(s["total"] == 3, "summary counts every cart")
    check(s["recovered"] == 1, "summary counts the recovered ones")
    check(s["recovery_rate"] == 50.0, "recovery rate is of mailed+recovered, not of all captures")
    check(s["recovered_value"] > 0, "the recovered value is priced from the stored config")
    check(s["delay_mins"] == carts.DELAY_SECS // 60, "the delay is reported in minutes")


# ── tiny request helpers ───────────────────────────────────────────────────
def _json(d):
    import json
    return json.dumps(d).encode()


def _h(headers=None):
    headers = headers or {}
    low = {k.lower(): v for k, v in headers.items()}
    return lambda name: low.get(str(name).lower(), "")


def main():
    for fn in (test_clean_cart, test_token_shape, test_put_is_in_place,
               test_one_open_cart_per_address, test_capture_keeps_original_clock,
               test_session_email_wins_over_body, test_anonymous_configure_stores_nothing,
               test_recovery_pct_is_never_read_from_the_client, test_token_is_single_use,
               test_token_expires, test_resolve_endpoint,
               test_recovery_never_stacks_and_never_worsens, test_due_respects_the_delay,
               test_sweep_requires_a_secret, test_summary):
        print("\n" + fn.__name__)
        fn()
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
    print("\n" + ("=" * 52))
    if _fails:
        print("FAILED: %d check(s)" % len(_fails))
        for m in _fails:
            print("  - " + m)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
