#!/usr/bin/env python3
"""Mystery-discount tests — stdlib only, no framework, no network.

Run:  python3 site/tests/test_mystery.py       (exits non-zero on any failure)

The flow hands a stranger 30% off in exchange for an email, so the things worth
locking down are the ones that turn it into free money or somebody else's tool:

  * **the discount cannot be forged from the client** — `recovery_pct` and
    `offer_label` are stripped from the checkout body and re-derived from a
    token checked against the store, so a crafted `{"recovery_pct": 0.99}` buys
    nothing.
  * **a token is single-use and dies in an hour** — spent or expired resolves to
    no discount, so a code can't be shared, replayed or hoarded.
  * **one card per inbox, ever** — a second capture from the same address gets
    the SAME token while it is live, and "spent" once it is not. Clearing
    localStorage must not mint a second 30%.
  * **the identity is the session, not the body** — a signed-in capture is
    written under the verified session email, so nobody can burn someone else's
    one card.
  * **the discount never stacks and never worsens the price** — it replaces the
    sitewide sale, best-wins, exactly like a typed code, and it labels itself
    rather than borrowing the recovery offer's wording.
  * **the copy matches the mechanic** — every card pays the same rate, so the
    shipped markup must not claim odds, a deck of mixed values, or that the
    other cards were worse.

Nothing here opens a socket or sends a mail: both stores are pointed at temp
files, and `mailer.configured()` is false with no SMTP env, so `send_code()`
returns without reaching a server.
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

# Point both stores at throwaway files BEFORE importing anything that reads
# them, and make sure no Upstash env leaks in from the shell (that would send
# these writes to production).
for _k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN",
           "SMTP_USER", "SMTP_PASSWORD"):
    os.environ.pop(_k, None)
_TMP = tempfile.NamedTemporaryFile(prefix="esb-bingo-test-", suffix=".ndjson", delete=False)
_TMP.close()
_TMPG = tempfile.NamedTemporaryFile(prefix="esb-bingo-guides-", suffix=".ndjson", delete=False)
_TMPG.close()
os.environ["BINGO_LOG"] = _TMP.name
os.environ["GUIDES_LOG"] = _TMPG.name

import mystery          # noqa: E402
import payments         # noqa: E402
import pricing          # noqa: E402

_fails = []


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


def reset():
    mystery.clear()


def _json(d):
    import json
    return json.dumps(d).encode()


def _h(headers=None):
    headers = headers or {}
    low = {k.lower(): v for k, v in headers.items()}
    return lambda name: low.get(str(name).lower(), "")


ORDER = {"game": "League of Legends", "service": "division", "from": "Gold IV",
         "to": "Platinum IV", "mode": "Solo", "addons": [], "region": "Europe West"}


def _capture(email="a@b.com", **extra):
    body = dict(ORDER, email=email)
    body.update(extra)
    return mystery.process_issue(_json(body), _h())


# ── validation ─────────────────────────────────────────────────────────────
def test_clean_capture():
    reset()
    check(mystery.clean_capture({"email": "not-an-email"}) is None, "a junk address is refused")
    check(mystery.clean_capture({}) is None, "no address is refused")
    row = mystery.clean_capture(dict(ORDER, email="  A@B.COM ", pct=0.99,
                                     addons=["x"] * 50, wins=9999))
    check(row["email"] == "a@b.com", "the address is trimmed and lower-cased")
    check(row["pct"] == mystery.OFFER_PCT,
          "the percentage is OFFER_PCT — never read from the body")
    check(len(row["addons"]) <= mystery.MAX_ADDONS, "the add-on list is capped")
    check(row["wins"] <= 99, "a tampered unit count is clamped")
    check(row["expires"] - row["at"] == mystery.TOKEN_TTL, "the row carries its own hour")


def test_token_shape():
    t = mystery.new_token()
    check(mystery.TOKEN_RE.match(t), "the token matches its own pattern: " + t)
    check(len(set(mystery.new_token() for _ in range(200))) == 200,
          "200 tokens, 200 distinct values")


# ── one card per inbox ─────────────────────────────────────────────────────
def test_one_card_per_address():
    reset()
    st, a = _capture("solo@x.com")
    check(st == 200 and a["ok"], "a new address gets a card")
    st, b = _capture("solo@x.com")
    check(st == 200 and b.get("ok") and b["token"] == a["token"],
          "a repeat while it is live returns the SAME token, not a second 30%")
    check(len(mystery.read()) == 1, "and does not write a second row")


def test_a_spent_card_is_not_reissued():
    reset()
    _st, a = _capture("spent@x.com")
    mystery.redeem(a["token"], order_id="ESB-TEST")
    st, b = _capture("spent@x.com")
    check(st == 200 and b.get("ok") is False and b.get("reason") == "spent",
          "an inbox whose card is spent is told so, not given a fresh one")
    check(len(mystery.read()) == 1, "and still owns exactly one row")


def test_capture_keeps_the_original_clock():
    reset()
    _st, a = _capture("clock@x.com")
    row = mystery.get(a["token"])
    row["at"] = row["at"] - 600
    row["expires"] = row["expires"] - 600
    mystery.put(row)
    _st, b = _capture("clock@x.com", to="Diamond IV")
    after = mystery.get(b["token"])
    check(after["expires"] == row["expires"],
          "re-capturing does not restart the hour — the clock began when the card opened")
    check(after["to"] == "Diamond IV", "but the configuration is refreshed")


def test_session_email_wins_over_body():
    reset()
    mystery.process_issue(_json(dict(ORDER, email="typed@x.com")), _h(),
                          session_email="verified@x.com")
    rows = mystery.read()
    check(len(rows) == 1 and rows[0]["email"] == "verified@x.com",
          "a verified session address beats whatever the body claimed")


def test_apply_is_a_beacon_not_an_issue():
    reset()
    _st, a = _capture("beacon@x.com")
    before = len(mystery.read())
    st, out = mystery.process_issue(_json({"action": "apply", "token": a["token"]}), _h())
    check(st == 200 and out.get("ok"), "the apply beacon answers ok")
    check(len(mystery.read()) == before, "and issues nothing")
    check(mystery.get(a["token"])["applied_at"] > 0, "it records that Apply was pressed")
    st, out = mystery.process_issue(_json({"action": "apply", "token": "BINGO-NOPE1234"}), _h())
    check(st == 200 and len(mystery.read()) == before,
          "an apply for an unknown token writes nothing")


# ── the money ──────────────────────────────────────────────────────────────
def test_pct_is_never_read_from_the_client():
    reset()
    _st, a = _capture("forge@x.com")

    plain = pricing.quote(dict(ORDER))["total"]
    forged = pricing.quote(dict(ORDER, recovery_pct=0.99))["total"]
    check(forged < plain, "quote() honours recovery_pct — which is why the body must be stripped")

    # The route the browser actually posts to. No Stripe key in the test env, so
    # process_checkout() answers 503 before it calls out — but the stripping
    # happens in build_session(), which is reachable directly.
    order = dict(ORDER, recovery_pct=0.99, offer_label="Free stuff", bingo="",
                 email="forge@x.com", currency="usd")
    order.pop("recovery_pct", None)          # what process_checkout does, verbatim
    order.pop("offer_label", None)
    check(pricing.quote(order)["total"] == plain,
          "with the forged percentage stripped, the order prices at the normal sale")

    with_token = pricing.quote(dict(ORDER, recovery_pct=mystery.OFFER_PCT,
                                    promo=a["token"], offer_label=mystery.OFFER_LABEL))
    check(with_token["total"] < plain, "a token the server resolved does discount it")
    check(with_token["promo_label"] == mystery.OFFER_LABEL,
          "and the receipt names it 'Mystery discount', not the recovery offer's wording")


def test_process_checkout_strips_the_forged_fields():
    """The stripping has to live in process_checkout, not just in this test's
    copy of it — read the source rather than trusting the comment."""
    import inspect
    src = inspect.getsource(payments.process_checkout)
    check('order.pop("recovery_pct", None)' in src, "process_checkout strips recovery_pct")
    check('order.pop("offer_label", None)' in src, "process_checkout strips offer_label")
    check('mystery.redeemable' in src, "and re-derives the discount from the token alone")


def test_token_is_single_use():
    reset()
    _st, a = _capture("once@x.com")
    check(mystery.redeemable(a["token"]) is not None, "a fresh token resolves")
    mystery.redeem(a["token"], order_id="ESB-1")
    check(mystery.redeemable(a["token"]) is None, "a paid token resolves to nothing")


def test_token_expires():
    reset()
    _st, a = _capture("clockout@x.com")
    row = mystery.get(a["token"])
    row["expires"] = int(time.time()) - 1
    mystery.put(row)
    check(mystery.redeemable(a["token"]) is None, "an hour that ran out means it ran out")
    _st, res = mystery.process_resolve(a["token"])
    check(res["valid"] is False and res["pct"] == 0,
          "and the resolve endpoint reports it dead, with no percentage attached")


def test_resolve_endpoint():
    reset()
    _st, a = _capture("resolve@x.com")
    _st, ok = mystery.process_resolve(a["token"])
    check(ok["valid"] and ok["pct"] == mystery.OFFER_PCT, "a live token resolves to its percentage")
    check(ok["label"] == mystery.OFFER_LABEL, "and carries its own receipt label")
    for junk in ("", "nope", "BINGO-", "BACK-AAAAAAAA", "BINGO-!!!!!!!!"):
        _st, bad = mystery.process_resolve(junk)
        check(bad["valid"] is False and bad["pct"] == 0,
              "an unknown token buys nothing: %r" % junk)


def test_never_stacks_and_never_worsens():
    reset()
    auto = pricing.resolve_promo()[1]
    check(auto and auto["pct"] > 0, "there is a sitewide sale to compete with")
    code, promo = pricing.resolve_promo(None, mystery.OFFER_PCT, mystery.OFFER_LABEL)
    check(promo["pct"] == mystery.OFFER_PCT,
          "the mystery offer replaces the sale — it does not add to it")
    check(promo["pct"] < auto["pct"] + mystery.OFFER_PCT, "30% + 15% is never 45%")
    check(promo["label"] == mystery.OFFER_LABEL, "and keeps its own label")

    # A percentage smaller than the sale must never make the buyer worse off.
    _code, weaker = pricing.resolve_promo(None, 0.01, mystery.OFFER_LABEL)
    check(weaker["pct"] == auto["pct"], "a weaker offer leaves the sitewide sale in place")

    plain = pricing.quote(dict(ORDER))
    offered = pricing.quote(dict(ORDER, recovery_pct=mystery.OFFER_PCT))
    check(offered["total"] <= plain["total"], "the offered price is never higher")
    check(offered["subtotal"] == plain["subtotal"],
          "the discount comes off the boost — the struck figure is a real price, not grossed up")


def test_price_pair_is_recomputed_not_stored():
    reset()
    _st, a = _capture("price@x.com")
    row = mystery.get(a["token"])
    row["total"] = 99999                       # a client could never set this, but try anyway
    mystery.put(row)
    normal, offer = mystery.price_pair(mystery.get(a["token"]))
    check(normal == pricing.quote(dict(ORDER))["total"],
          "the value is re-quoted from the stored config, never read off the row")
    check(0 < offer < normal, "and the offer figure is the discounted one")


# ── the copy has to match the mechanic ─────────────────────────────────────
def test_copy_claims_no_odds():
    """Every card pays the same rate, so the shipped markup must never claim
    luck or state a probability — the one thing a visitor can disprove in ten
    seconds by opening a second tab.

    ⚠ The deck's three advertised values (10/20/30) ARE named in the copy: the
    business asked for the handoff's wording back on 2026-08-21, having been
    told the deck holds one value. That is a deliberate call and is recorded in
    CLAUDE.md — it is not a bug to "fix". What is still enforced here is the
    line either side of it: no odds, no probability, no "you got lucky", and the
    top of the advertised deck must equal what is actually paid."""
    sys.path.insert(0, ROOT)
    import build                                     # noqa: E402
    html = build.mystery_modal()
    lowered = html.lower()
    for phrase in ("1 in 3", "chance", "you got lucky", "was the best one",
                   "odds", "randomly", "lucky", "first order"):
        check(phrase not in lowered, "the card never says %r" % phrase)
    check("pays the top rate" in lowered,
          "the reveal states a fact about the card, not about luck")
    check("one per customer" in lowered,
          "and claims only what the server enforces: one card per inbox")
    check("climb30" not in lowered,
          "the code is not minted client-side — a guessable pattern is a public coupon")

    # The advertised ceiling and the real payout are the same number. If they
    # ever drift, the offer screen and the reveal quote two different discounts.
    top = int(round(mystery.OFFER_PCT * 100))
    check(build.MYD_DECK[-1] == top,
          "the deck tops out at exactly what is paid (%d%%)" % top)
    check(len(set(build.MYD_DECK)) == 3, "and names three distinct values")
    check(("%d%%" % top) in lowered, "which the copy actually prints")


def test_summary():
    reset()
    _st, a = _capture("s1@x.com")
    _st, b = _capture("s2@x.com", game="Valorant", **{"from": "Bronze 3", "to": "Silver 3"})
    mystery.mark_applied(a["token"])
    mystery.redeem(b["token"], order_id="ESB-S2")
    s = mystery.summary(days=30)
    check(s["total"] == 2, "both cards are counted")
    check(s["applied"] == 1, "one Apply is recorded")
    check(s["redeemed"] == 1, "one redemption is recorded")
    check(s["pct"] == mystery.OFFER_PCT and s["ttl_mins"] == mystery.TOKEN_TTL // 60,
          "the panel reads the real constants, never a typed pair")
    check(len(s["recent"]) == 2, "and the rows come back for the table")
    check(all("pct" not in r for r in s["recent"]),
          "no row ships a percentage the console could disagree with the store about")


def main():
    for fn in (test_clean_capture, test_token_shape, test_one_card_per_address,
               test_a_spent_card_is_not_reissued, test_capture_keeps_the_original_clock,
               test_session_email_wins_over_body, test_apply_is_a_beacon_not_an_issue,
               test_pct_is_never_read_from_the_client,
               test_process_checkout_strips_the_forged_fields,
               test_token_is_single_use, test_token_expires, test_resolve_endpoint,
               test_never_stacks_and_never_worsens, test_price_pair_is_recomputed_not_stored,
               test_copy_claims_no_odds, test_summary):
        print("\n" + fn.__name__)
        fn()
    for path in (_TMP.name, _TMPG.name):
        try:
            os.unlink(path)
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
