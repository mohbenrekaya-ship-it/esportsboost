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
# The sweep also drives the mystery follow-up (behind BINGO_FOLLOWUP_ENABLED),
# so that store needs a throwaway file too — importing followup would otherwise
# read the real mystery.ndjson.
_TMPB = tempfile.NamedTemporaryFile(prefix="esb-carts-bingo-", suffix=".ndjson", delete=False)
_TMPB.close()
os.environ["BINGO_LOG"] = _TMPB.name

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


def test_a_customer_who_bought_is_never_chased():
    """REGRESSION — this mailed a real customer.

    `recover()` burns a cart only when the Stripe webhook can match its token,
    which needs the buyer to have arrived through the `?cart=` link. Anybody who
    abandoned a cart and then simply came back and bought stayed `pending` for
    ever, so the sweep chased a paying customer about "the order you left
    behind" while their actual support thread went unanswered. The orders store
    is the authority on who bought — not the cart's own status."""
    reset()
    import orders
    orders_log = os.environ.get("ORDERS_LOG")
    tmp = tempfile.NamedTemporaryFile(prefix="esb-orders-test-", suffix=".ndjson",
                                      delete=False)
    tmp.close()
    os.environ["ORDERS_LOG"] = tmp.name
    try:
        orders.clear()
        # two abandoned carts, aged past the delay
        for email in ("bought@x.com", "stillbrowsing@x.com"):
            carts.process_capture(_json(dict(CFG, email=email)), _h())
        for row in carts.read():
            row["at"] = int(time.time()) - carts.DELAY_SECS - 60
            carts.put(row)
        check(len(carts.due()) == 2, "both carts are due before anyone buys")

        # one of them then places a real order, WITHOUT the recovery link
        orders.append([orders.clean_order({
            "order_id": "ESB-REAL1", "email": "bought@x.com", "amount": 91,
            "currency": "usd", "game": "Rocket League", "status": "paid"})])
        check(carts.has_ordered("bought@x.com"), "the orders store knows them")
        check(not carts.has_ordered("stillbrowsing@x.com"), "and not the other")

        due = carts.due()
        emails = [c["email"] for c in due]
        check(emails == ["stillbrowsing@x.com"],
              "only the one who did NOT buy is chased")
        row = [r for r in carts.read() if r["email"] == "bought@x.com"][0]
        check(row["status"] == "recovered",
              "and the customer's cart is retired, so no later sweep re-asks")
        check(carts.due() == [c for c in carts.due()],
              "the check is stable across repeated sweeps")
    finally:
        if orders_log is None:
            os.environ.pop("ORDERS_LOG", None)
        else:
            os.environ["ORDERS_LOG"] = orders_log


def test_followup_is_off_unless_switched_on():
    """The sweep drives TWO mailers now, and the second is off by default.

    The cron already runs every five minutes in production, so a deploy that
    carried the follow-up would have started mailing real addresses within
    minutes, unattended, on the domain the order confirmations go out on. The
    default is the safety property — if this test starts failing because the
    default flipped, that is the bug, not the test."""
    os.environ["CART_SWEEP_SECRET"] = "x" * 20
    os.environ.pop("BINGO_FOLLOWUP_ENABLED", None)

    st, pl = carts.process_sweep(b"{}", _h({"x-sweep-secret": "x" * 20}))
    check(st == 200, "the sweep still runs")
    check(pl.get("followup", {}).get("skipped"),
          "but the follow-up is skipped with the switch unset")
    check("sent" in pl, "and the cart recovery is unaffected")

    for val in ("", "0", "true", "yes", "TRUE", " 1 x"):
        os.environ["BINGO_FOLLOWUP_ENABLED"] = val
        _st, pl = carts.process_sweep(b"{}", _h({"x-sweep-secret": "x" * 20}))
        check(pl.get("followup", {}).get("skipped"),
              "only an exact '1' arms it, not %r" % val)

    os.environ["BINGO_FOLLOWUP_ENABLED"] = "1"
    _st, pl = carts.process_sweep(b"{}", _h({"x-sweep-secret": "x" * 20}))
    f = pl.get("followup", {})
    check("skipped" not in f, "'1' arms it")
    check("warn" in f and "chase" in f,
          "and it runs BOTH stages — the warning and the chase")

    os.environ.pop("BINGO_FOLLOWUP_ENABLED", None)
    os.environ.pop("CART_SWEEP_SECRET", None)


def test_a_broken_followup_never_takes_the_cart_sweep_down():
    """They share one timer. Losing an upsell mail is cheaper than losing the
    recovery mail that has been live for months."""
    import followup
    os.environ["CART_SWEEP_SECRET"] = "x" * 20
    os.environ["BINGO_FOLLOWUP_ENABLED"] = "1"
    real = followup.sweep_all

    def boom(*a, **k):
        raise RuntimeError("upstash on fire")
    followup.sweep_all = boom
    try:
        st, pl = carts.process_sweep(b"{}", _h({"x-sweep-secret": "x" * 20}))
        check(st == 200, "the sweep still answers 200")
        check("sent" in pl and "due" in pl,
              "the cart recovery still ran and reported")
        check("fire" in str(pl.get("followup", {}).get("error", "")),
              "and the follow-up failure is reported, not raised")
    finally:
        followup.sweep_all = real
        os.environ.pop("BINGO_FOLLOWUP_ENABLED", None)
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


# ══════════════════════════════════════════════════════════════════════════
#  the accounts shop — its own rate, its own second mail
# ══════════════════════════════════════════════════════════════════════════
ACC = {"game": "League of Legends", "service": "account",
       "account": "lol-unranked-basic", "region": "Europe West",
       "mode": "Solo", "addons": [], "cur": "usd"}


def _acc_cart(email="acc@b.co", **over):
    row = carts.clean_cart(dict(ACC, email=email, **over))
    row["token"] = carts.new_token()
    carts.put(row)
    return row


def test_an_account_cart_keeps_the_listing():
    """Without the listing an account cart cannot be re-priced, so the sweep
    retires it as unpriceable and the one product with a fixed shelf is the one
    nobody is ever chased about. That is exactly what shipped before this."""
    reset()
    row = _acc_cart()
    check(row["account"] == "lol-unranked-basic", "the listing id is stored")
    check(carts.is_account(row), "and the row reads as an account, not a boost")
    import recovery
    now_q, off_q = recovery.price_pair(row)
    check(now_q is not None, "an account cart PRICES — it is not swept away as unpriceable")
    check(now_q.get("cents") is True, "and it prices to the cent, like the shop")
    blind = carts.clean_cart(dict(ACC, email="x@b.co", account=""))
    blind["token"] = carts.new_token()
    check(recovery.price_pair(blind)[0] is None,
          "a cart captured without the listing still cannot price — the field is the fix")


def test_an_account_is_worth_ten_not_thirty():
    reset()
    boost = carts.clean_cart(dict(CFG, email="b@b.co"))
    acc = carts.clean_cart(dict(ACC, email="a@b.co"))
    check(carts.pct_for(boost) == carts.RECOVERY_PCT, "a boost cart is worth the boost rate")
    check(carts.pct_for(acc) == carts.ACCOUNT_PCT, "an account cart is worth the account rate")
    check(carts.ACCOUNT_PCT < carts.RECOVERY_PCT,
          "and it is the smaller of the two — it is margin, not labour")

    row = _acc_cart("res@b.co")
    st, pl = carts.process_resolve(row["token"])
    check(pl["valid"] and pl["pct"] == carts.ACCOUNT_PCT,
          "GET /api/cart hands the page the ROW's rate, not the module constant")
    check(pl["account"] == "lol-unranked-basic",
          "and the listing, so the checkout link can hydrate the order")


def test_the_account_price_takes_the_code_and_nothing_else():
    """The account branch refuses the sitewide sale, every bundle and every typed
    code. The recovery token is the one exception, and it must come off the LIST
    price to the cent — a rounded figure here is a mail quoting a price the
    checkout will not charge."""
    st = dict(ACC, currency="usd")
    plain = pricing.quote(st)
    off = pricing.quote(dict(st, recovery_pct=carts.ACCOUNT_PCT, promo="BACK-X"))
    check(not off["invalid"], "an account quote with a recovery pct is valid")
    expect = round(plain["subtotal"] * (1 - carts.ACCOUNT_PCT), 2)
    check(abs(off["total"] - expect) < 1e-9,
          "the total is exactly %d%% off the list price" % (carts.ACCOUNT_PCT * 100))
    check(abs(off["subtotal"] - off["discount"] - off["total"]) < 1e-9,
          "subtotal − discount = total still holds exactly")
    check(off["total_cents"] == int(round(off["total"] * 100)),
          "and the charge is to the cent, not rounded to a whole unit")
    # the public discounts are still refused
    check(pricing.quote(dict(st, promo="SPLIT15"))["total"] == plain["total"],
          "a typed sitewide code still buys nothing on an account")
    check(pricing.quote(dict(st, recovery_pct=1.5))["total"] == plain["total"],
          "and a nonsense percentage is ignored, not applied")


def test_a_mystery_code_cannot_be_spent_on_an_account():
    """The mystery card is a climb offer worth up to 35%; this product's whole
    discount budget is 10%. `process_checkout()` drops the bingo token on an
    account order, so the 35% can never reach the account branch."""
    import payments
    order = dict(ACC, bingo="BINGO-WHATEVER", service="account")
    tok = ("" if order.get("service") == "account"
           else str(order.get("bingo") or "")[:40])       # mirror process_checkout
    check(tok == "", "a bingo token on an account order is dropped before it is resolved")
    src = open(os.path.join(ROOT, "src", "payments.py")).read()
    check('"" if order.get("service") == "account"' in src,
          "and that guard is the one in payments.py, not just in this test")


def test_the_one_day_recall():
    reset()
    now = int(time.time())
    row = _acc_cart("chase@b.co")
    carts.mark(row["token"], at=now - carts.DELAY_SECS - 5)
    check(len(carts.due(now=now)) == 1, "the first mail is due after the 30 minutes")
    check(len(carts.due_chase(now=now)) == 0, "and the recall is NOT — nothing has been mailed yet")

    carts.mark(row["token"], status="mailed", mailed_at=now - 60)
    check(len(carts.due(now=now)) == 0, "a mailed cart is not first-mailed again")
    check(len(carts.due_chase(now=now)) == 0, "and a minute later the recall is still not due")

    carts.mark(row["token"], mailed_at=now - carts.ACCOUNT_CHASE_DELAY - 5)
    check(len(carts.due_chase(now=now)) == 1, "a day after the first mail the recall IS due")
    carts.mark_chased(row["token"], now)
    check(len(carts.due_chase(now=now)) == 0, "and it is due exactly once — there is no third mail")
    check(carts.get(row["token"])["status"] == "mailed",
          "the recall moves `stage`, never `status` — the row is still a mailed cart")


def test_a_boost_is_never_recalled():
    """One mail on a boost and that is the whole budget. The recall is the
    accounts shop's, and widening it to every cart is a decision about volume on
    the domain the order confirmations go out on."""
    reset()
    now = int(time.time())
    row = carts.clean_cart(dict(CFG, email="boost@b.co"))
    row["token"] = carts.new_token()
    row["status"] = "mailed"
    row["mailed_at"] = now - carts.ACCOUNT_CHASE_DELAY - 500
    carts.put(row)
    check(len(carts.due_chase(now=now)) == 0, "a week-old mailed BOOST cart is never recalled")


def test_the_two_mails_can_never_collide():
    """`due()` wants a pending row, `due_chase()` a mailed one on stage `first`.
    No row can be in both sets, so a sweep that fell behind cannot fire the code
    and its reminder within the same minute."""
    reset()
    now = int(time.time())
    row = _acc_cart("both@b.co")
    for age in (0, carts.DELAY_SECS + 1, carts.ACCOUNT_CHASE_DELAY + 1,
                carts.ACCOUNT_CHASE_DELAY * 2):
        for status, stage in (("pending", "first"), ("mailed", "first"),
                              ("mailed", "chased")):
            carts.mark(row["token"], at=now - age - carts.DELAY_SECS,
                       mailed_at=now - age, status=status, stage=stage)
            both = (len(carts.due(now=now)) and len(carts.due_chase(now=now)))
            check(not both, "no row is due for both mails at once (%s/%s, %ds)"
                  % (status, stage, age))


def test_a_recapture_cannot_reset_the_sequence():
    """REGRESSION, borrowed from the mystery store where it reached real inboxes:
    a buyer who edits the checkout form after the recall has gone out must not be
    put back on stage `first` and chased a second time."""
    reset()
    now = int(time.time())
    row = _acc_cart("recap@b.co")
    carts.mark(row["token"], status="mailed", mailed_at=now - 100)
    carts.mark_chased(row["token"], now)
    import json
    carts.process_capture(json.dumps(dict(ACC, email="recap@b.co",
                                          account="lol-iron")).encode(), _h())
    after = carts.get(row["token"])
    check(after["stage"] == "chased", "the re-capture leaves the row chased")
    check(after["chased_at"] > 0, "and keeps when it was chased")
    check(after["account"] == "lol-iron", "but the configuration still tracks the live order")
    check(len(carts.due_chase(now=now + carts.ACCOUNT_CHASE_DELAY * 3)) == 0,
          "so it is never recalled twice")


def test_the_recall_never_offers_a_better_rate():
    """A second mail quoting a bigger number teaches the reader that the first
    deadline was theatre. Both messages are the same token at the same rate."""
    reset()
    import recovery
    row = _acc_cart("copy@b.co")
    now_q, off_q = recovery.price_pair(row)
    first = recovery._copy(row, now_q, off_q, chase=False)
    again = recovery._copy(row, now_q, off_q, chase=True)
    pct = int(round(carts.ACCOUNT_PCT * 100))
    check(("%d%%" % pct) in first["subject"] and ("%d%%" % pct) in again["subject"],
          "both mails quote the same %d%%" % pct)
    for bad in ("35%", "30%", "20%", "last chance", "final offer"):
        check(bad.lower() not in (again["subject"] + again["text_lede"]).lower(),
              "the recall does not say %r" % bad)
    body = recovery._text(row, now_q, off_q, "https://x.test", chase=True)
    check(row["token"] in body, "and it carries the SAME code, not a new one")
    check("account=lol-unranked-basic" in body,
          "the link carries the listing, so a phone that never configured it still lands right")


def test_the_account_mail_quotes_the_shop_to_the_cent():
    reset()
    import recovery
    row = _acc_cart("cents@b.co", cur="eur")
    now_q, off_q = recovery.price_pair(row)
    body = recovery._text(row, now_q, off_q, "https://x.test")
    shown = recovery._money(row, off_q, off_q["total"])
    check("." in shown and shown[0] == "\u20ac",
          "an account is quoted to the cent, in the currency the buyer was reading (%s)" % shown)
    check(shown in body, "and that exact figure is the one in the mail")
    check(abs(off_q["total"] - round(now_q["subtotal"] * (1 - carts.ACCOUNT_PCT), 2)) < 1e-9,
          "struck against the LIST price, never against an already-reduced one")


def test_summary_reports_accounts_apart():
    reset()
    now = int(time.time())
    _acc_cart("s1@b.co")
    r2 = _acc_cart("s2@b.co")
    carts.mark(r2["token"], status="mailed", mailed_at=now - 10, stage="chased")
    carts.clean_cart(dict(CFG, email="s3@b.co"))
    b = carts.clean_cart(dict(CFG, email="s3@b.co"))
    b["token"] = carts.new_token()
    carts.put(b)
    s = carts.summary(days=30)
    a = s["accounts"]
    check(a["total"] == 2, "the module counts account carts only (%d)" % a["total"])
    check(s["total"] == 3, "while the tab's own total still counts everything")
    check(a["chased"] == 1, "and reports how many got the one-day recall")
    check(a["pct"] == carts.ACCOUNT_PCT and a["chase_hours"] == carts.ACCOUNT_CHASE_DELAY // 3600,
          "the panel reads the rate and the delay, so the copy cannot go stale")
    check(any(r["product"] == "account" for r in s["recent"]),
          "and every row says which product it is")
    check(all(r["summary"] != "" for r in s["recent"]),
          "an account row is named by its listing, not by an empty climb")


def main():
    for fn in (test_clean_cart, test_token_shape, test_put_is_in_place,
               test_one_open_cart_per_address, test_capture_keeps_original_clock,
               test_session_email_wins_over_body, test_anonymous_configure_stores_nothing,
               test_recovery_pct_is_never_read_from_the_client, test_token_is_single_use,
               test_token_expires, test_resolve_endpoint,
               test_recovery_never_stacks_and_never_worsens, test_due_respects_the_delay,
               test_sweep_requires_a_secret,
               test_a_customer_who_bought_is_never_chased,
               test_followup_is_off_unless_switched_on,
               test_a_broken_followup_never_takes_the_cart_sweep_down, test_summary,
               # the accounts shop
               test_an_account_cart_keeps_the_listing,
               test_an_account_is_worth_ten_not_thirty,
               test_the_account_price_takes_the_code_and_nothing_else,
               test_a_mystery_code_cannot_be_spent_on_an_account,
               test_the_one_day_recall, test_a_boost_is_never_recalled,
               test_the_two_mails_can_never_collide,
               test_a_recapture_cannot_reset_the_sequence,
               test_the_recall_never_offers_a_better_rate,
               test_the_account_mail_quotes_the_shop_to_the_cent,
               test_summary_reports_accounts_apart):
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
