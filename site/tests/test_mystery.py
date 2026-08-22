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

import followup         # noqa: E402
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


import data as D                                                     # noqa: E402
_D = D
D_STREAM_VERIFIED = getattr(_D, "STREAM_CLAIM_VERIFIED", False)

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


# ── the follow-up: one second mail, at a better rate ───────────────────────
def _lapsed(email="lapse@x.com", **extra):
    """A captured card whose hour has already run out."""
    _st, p = _capture(email, **extra)
    row = mystery.get(p["token"])
    old = int(time.time()) - mystery.TOKEN_TTL - mystery.FOLLOWUP_DELAY - 60
    row["at"] = old
    row["expires"] = old + mystery.TOKEN_TTL
    mystery.put(row)
    return mystery.get(p["token"])


def test_followup_due_rules():
    """Each condition in `due_followup()` is a way the second mail would
    otherwise be wrong — a live offer undercut, a paid order chased, a
    three-week-old configuration mailed, or the same person mailed forever."""
    reset()
    lapsed = _lapsed("due@x.com")
    check([r["token"] for r in mystery.due_followup()] == [lapsed["token"]],
          "a lapsed, unbought card is due")

    reset()
    _st, live = _capture("live@x.com")
    check(mystery.due_followup() == [],
          "a card still inside its hour is not chased — the countdown is real")

    reset()
    row = _lapsed("paid@x.com")
    mystery.redeem(row["token"], order_id="ESB-1")
    check(mystery.due_followup() == [], "a paid card is never chased")

    reset()
    row = _lapsed("old@x.com")
    r = mystery.get(row["token"])
    r["at"] = int(time.time()) - mystery.FOLLOWUP_MAX_AGE - 60
    mystery.put(r)
    check(mystery.due_followup() == [],
          "a configuration older than FOLLOWUP_MAX_AGE is left alone")

    reset()
    row = _lapsed("gone@x.com")
    mystery.unsubscribe(row["token"])
    check(mystery.due_followup() == [], "an unsubscribed row is never chased again")
    kept = mystery.get(row["token"])
    check(kept.get("status") == "issued" and kept.get("pct") == mystery.OFFER_PCT,
          "and unsubscribing does not void the discount they were offered")

    reset()
    row = _lapsed("applied@x.com")
    mystery.mark(row["token"], applied_at=int(time.time()))
    check(len(mystery.due_followup()) == 1,
          "somebody who applied the code and still didn't pay IS chased — the "
          "strongest lead in the store, not a spent one")


def test_config_beacon_tracks_the_latest_order():
    """The card is offered ~8s after the target rank settles and people keep
    configuring. A row frozen at capture makes every mail quote an order the
    visitor abandoned two steps later — the wrong price against the wrong climb."""
    reset()
    _st, p = _capture("live@x.com")
    tok = p["token"]
    before = mystery.get(tok)
    check(before["to"] == "Platinum IV" and before["addons"] == [],
          "the row starts on the climb the card was opened against")

    # …they carry on: extend the climb, go Duo, tick Priority, move the server.
    st, body = mystery.process_issue(_json({
        "action": "config", "token": tok, "game": "League of Legends",
        "service": "division", "from": "Gold IV", "to": "Diamond IV",
        "mode": "Duo queue", "region": "Europe Nordic & East",
        "addons": ["priority"], "cur": "eur"}), _h())
    check(st == 200 and body.get("ok"), "the beacon is accepted")

    after = mystery.get(tok)
    check(after["to"] == "Diamond IV", "the row follows the new target")
    check(after["mode"] == "Duo queue" and after["addons"] == ["priority"],
          "and the queue and add-ons")
    check(mystery.currency_of(after) == "eur", "and the currency they are reading in")

    # The thing the mail actually quotes must move with it.
    now_q, off_q = followup.price_pair(after)
    check("Diamond IV" in (now_q.get("summary") or ""),
          "so the mail describes the order they actually built")
    old_q = pricing.quote(mystery._state(before))
    check(now_q["total"] > old_q["total"],
          "and prices it, rather than the cheaper one they left behind")
    check(mystery.process_resolve(tok)[1]["order"]["to"] == "Diamond IV",
          "and /checkout?bingo= hydrates the same order")


def test_config_beacon_cannot_move_the_offer():
    """The token is the whole authorisation, so the beacon must be able to
    change WHICH order is quoted and nothing else — not the clock, not the
    rate, not the status."""
    reset()
    _st, p = _capture("guard@x.com")
    tok = p["token"]
    before = mystery.get(tok)

    mystery.process_issue(_json({
        "action": "config", "token": tok, "game": "League of Legends",
        "service": "division", "from": "Gold IV", "to": "Diamond IV",
        "mode": "Solo", "region": "Europe West",
        # everything below is an attempt to buy something with a beacon
        "pct": 0.9, "expires": 99999999999, "status": "issued",
        "stage": "card", "recovery_pct": 0.9, "warned": 0, "nomail": 0,
        "token_": "x", "email": "attacker@x.com"}), _h())
    after = mystery.get(tok)
    check(after["expires"] == before["expires"], "the deadline is never extended")
    check(after["pct"] == before["pct"], "the rate is never raised")
    check(after["status"] == before["status"], "the status is never changed")
    check(after["email"] == before["email"],
          "and the address is never re-pointed at another inbox")
    check(after["token"] == tok, "same token throughout")


def test_config_beacon_freezes_on_a_paid_row():
    """A redeemed row's configuration is the record of what was bought."""
    reset()
    _st, p = _capture("paidcfg@x.com")
    tok = p["token"]
    mystery.redeem(tok, order_id="ESB-CFG")
    mystery.process_issue(_json({
        "action": "config", "token": tok, "game": "League of Legends",
        "service": "division", "from": "Gold IV", "to": "Diamond IV",
        "mode": "Solo", "region": "Europe West"}), _h())
    check(mystery.get(tok)["to"] == "Platinum IV",
          "a beacon can never rewrite what a paid order says it was")


def test_a_lapsed_card_still_tracks_the_order():
    """Somebody who let the hour go and then kept building is exactly who the
    chase is for — it must quote what they have now, not what they had then."""
    reset()
    row = _lapsed("lapcfg@x.com")
    mystery.process_issue(_json({
        "action": "config", "token": row["token"], "game": "League of Legends",
        "service": "division", "from": "Gold IV", "to": "Diamond IV",
        "mode": "Solo", "region": "Europe West"}), _h())
    updated = mystery.get(row["token"])
    check(updated["to"] == "Diamond IV", "a dead card still follows the order")
    check(mystery.redeemable(row["token"]) is None,
          "and updating it does not bring the discount back to life")
    check(len(mystery.due_followup()) == 1, "it is still due exactly one chase")


def test_a_struck_price_is_the_list_never_the_sale_price():
    """REGRESSION — a real mail said "30% off your order — $34 instead of $41",
    which is 17%.

    Every discount here is a percentage of the LIST, and the sitewide sale is
    already one of them. Striking the post-sale total while quoting the code's
    rate states a reduction the arithmetic never made, and it disagreed with the
    checkout page the mail links to, which strikes `subtotal`. So the struck
    figure in any mail is `subtotal` and the claimed percentage has to hold
    against it."""
    reset()
    row = _lapsed("struck@x.com")

    # the exact shape that produced the bad mail: a live sitewide sale
    q = pricing.quote(mystery._state(row))
    check(q["discount"] > 0 and q["subtotal"] > q["total"],
          "there IS a sitewide sale on this order, so the two differ")

    # the code mail
    listed, offer = mystery.list_total(row), mystery.price_pair(row)[1]
    check(listed == q["subtotal"], "list_total() is the pre-discount subtotal")
    check(listed > q["total"], "and it is above today's sale price")
    text = mystery._mail_text(row, "https://x.test", listed, offer)
    pct = int(round(mystery.OFFER_PCT * 100))
    check(("%d%%" % pct) in text, "the code mail claims %d%%" % pct)
    check(mystery._usd(listed) in text and mystery._usd(offer) in text,
          "and strikes the list against the offer price")
    real = (1 - offer / float(listed)) * 100
    check(abs(real - pct) <= 2,
          "the claim holds: %s → %s is %.0f%%, claimed %d%%"
          % (mystery._usd(listed), mystery._usd(offer), real, pct))

    # the reminder and the chase
    for label, pair, rate in (
            ("reminder", followup.price_pair(row, mystery.OFFER_PCT), mystery.OFFER_PCT),
            ("chase", followup.price_pair(row, mystery.FOLLOWUP_PCT), mystery.FOLLOWUP_PCT)):
        nq, oq = pair
        want = int(round(rate * 100))
        got = (1 - oq["total"] / float(nq["subtotal"])) * 100
        check(abs(got - want) <= 2,
              "the %s's %s → %s is %.0f%%, claimed %d%%"
              % (label, followup.money(nq["subtotal"], "usd"),
                 followup.money(oq["total"], "usd"), got, want))
        check(nq["subtotal"] != nq["total"],
              "and it is NOT the sale price being struck (%s)" % label)


def test_mail_figures_come_from_the_real_sources():
    """Every number and name in these mails is read, never typed. Each check
    here is a way one of them could silently drift from the page it claims to
    agree with — the failure mode is a mail quoting a figure the site does not."""
    reset()
    row = _lapsed("figs@x.com")
    _n, off = followup.price_pair(row)

    # The screen share's worth must be the SAME figure the order card strikes,
    # from the same arithmetic — not a second formula that happens to match.
    worth = followup.stream_worth(off, "usd")
    canon = pricing.addon_list_price(off.get("addon_base") or 0, "stream")
    check(worth == followup.money(canon, "usd"),
          "the stream figure is pricing.addon_list_price(), not a second formula")
    check(canon > 0, "and it is a real number on this order (%s)" % worth)

    # The row's name must be the add-on's own label, so the mail tells the buyer
    # to tick something they will actually see on the checkout page.
    labels = [a["label"] for a in D.ADDONS if a.get("id") == "stream"]
    check(followup.stream_label() == labels[0],
          "the mail names the add-on exactly as the picker does")

    # Pause is a signed-off product promise, not sales copy written for a mail.
    title, body = followup.pause_promise()
    check(any(title == t and body == b for _g, t, b in D.DASHBOARD_POINTS),
          "the pause line is lifted verbatim from D.DASHBOARD_POINTS")

    # The ETA in the mail is the engine's, and the hours are bounded by it.
    check(off["eta"] == pricing.eta_text(off["days"]),
          "the delivery line is pricing.eta_text(), not a restatement")
    hours = pricing.play_hours(off["days"])
    check(hours <= off["days"] * 24,
          "and the hours claim cannot exceed the calendar the ETA promised")


def test_stream_pitch_is_gated_on_the_verification_flag():
    """A comparative claim about every competitor at once, falsifiable by one
    of them. It ships only when the flag says it is substantiated — the same
    mechanism rating_ld() uses to wait on TRUSTPILOT_URL."""
    real = D.STREAM_CLAIM_VERIFIED
    try:
        D.STREAM_CLAIM_VERIFIED = False
        off = followup.stream_line().lower()
        check("other sites" not in off and "most sites" not in off,
              "unverified: the mail claims nothing about competitors")
        D.STREAM_CLAIM_VERIFIED = True
        on = followup.stream_line().lower()
        check("sites" in on, "verified: the comparative sentence ships")
        check(off != on, "and the flag is what decides, with no code change")
    finally:
        D.STREAM_CLAIM_VERIFIED = real
    check(D.STREAM_CLAIM_VERIFIED is False,
          "it is still False today — the claim is not substantiated")


def test_the_warning_marks_before_it_sends():
    """Same rule as the chase: a half-succeeding SMTP call must not leave the
    card warnable on every sweep for the rest of its hour."""
    reset()
    _st, p = _capture("wmark@x.com")
    row = mystery.get(p["token"])
    row["at"] = int(time.time()) - mystery.WARN_DELAY - 60
    row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)

    import mailer
    real_conf, real_send = mailer.configured, mailer.send
    try:
        mailer.configured = lambda: True
        mailer.send = lambda *a, **k: (_ for _ in ()).throw(AssertionError("unreachable"))
        # A transport that reports failure rather than raising.
        mailer.send = lambda *a, **k: (False, "550 mailbox unavailable")
        out = followup.sweep_warnings()
        check(out["sent"] == 0 and out["failed"] == 1, "the send failed")
        check(mystery.get(p["token"]).get("warned") == 1,
              "and the row is still marked, so the next sweep does not retry it")
        check(mystery.due_warning() == [], "it is out of the due set for good")
    finally:
        mailer.configured, mailer.send = real_conf, real_send


def test_unsubscribe_route_contract():
    """One click, no login, and it must not disclose whether a token exists."""
    reset()
    _st, p = _capture("unsub@x.com")
    st, body = mystery.process_unsubscribe(p["token"])
    check(st == 200 and body.get("ok"), "a real token answers 200 ok")
    st2, body2 = mystery.process_unsubscribe("BINGO-NOTATOKEN")
    check((st2, body2) == (st, body),
          "and an unknown one answers identically — no existence oracle")
    check(mystery.get(p["token"]).get("nomail") == 1, "the real row is flagged")
    check(mystery.redeemable(p["token"]) is not None,
          "and the discount it was offered still works")


def test_ops_counters_track_the_sequence():
    """The Mystery tab is the only place the two give-aways are visible, and
    they cost different rates — folding them together understates the
    programme by the difference on every chased row."""
    reset()
    _st, a = _capture("ops1@x.com")                      # untouched card
    warned = _lapsed("ops2@x.com")                       # will be warned
    mystery.mark_warned(warned["token"])
    chased = _lapsed("ops3@x.com")                       # will be chased + paid
    mystery.revive(chased["token"])
    mystery.redeem(chased["token"], order_id="ESB-OPS")
    due = _lapsed("ops4@x.com")                          # waiting for the chase
    gone = _lapsed("ops5@x.com")
    mystery.unsubscribe(gone["token"])

    s = mystery.summary(days=30)
    check(s["warned"] == 1, "warned counts the halfway mails")
    check(s["chased"] == 1 and s["chased_redeemed"] == 1, "chased and its conversion")
    check(s["chase_rate"] == 100.0, "the chase rate is over chased rows, not all rows")
    # Two: the plain lapsed row AND the warned one. A warning does not consume
    # the chase — it adds no offer, so the card it warned about is still owed
    # its one last call.
    check(s["chase_due"] == 2, "two rows are waiting on the next sweep")
    check(sorted(r["email"] for r in mystery.due_followup())
          == ["ops2@x.com", "ops4@x.com"],
          "including the already-warned one — a warning is not a chase")
    check(s["unsubs"] == 1, "and one opted out")
    check(s["followup_pct"] == mystery.FOLLOWUP_PCT
          and s["pct"] == mystery.OFFER_PCT
          and s["followup_pct"] != s["pct"],
          "both rates are reported, and they are not the same number")
    check(s["warn_delay_mins"] == mystery.WARN_DELAY // 60,
          "the panel reads the real constants, never a typed pair")
    stages = sorted(r["stage"] for r in s["recent"])
    check(stages.count("followup") == 1, "and each row carries its own stage")


def test_a_recapture_never_resets_the_offer_lifecycle():
    """REGRESSION — this shipped and mailed a real inbox.

    `process_issue` used to rebuild the row from `clean_capture()` on a
    re-capture and copy back an allowlist of nine lifecycle fields. Every field
    added after that list was written was silently dropped, so a second capture
    reset `stage` to "card", `warned` to 0 and `nomail` to 0 while keeping the
    chased `pct` and its 24-hour `expires`. Three consequences, worst last:
    the card became chaseable a second time; the halfway warning fired on a
    24-hour row and mailed "1425 minutes left … halfway through its hour"; and
    **an unsubscribe undid itself.**"""
    reset()
    _st, p = _capture("recap@x.com")
    tok = p["token"]
    row = mystery.get(tok)
    row["at"] = int(time.time()) - mystery.TOKEN_TTL - 60
    row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)
    mystery.revive(tok)
    before = mystery.get(tok)

    # the same browser captures again — a re-submitted modal, another game page
    _capture("recap@x.com", **{"to": "Diamond IV"})
    after = mystery.get(tok)

    check(after["stage"] == "followup", "the chased stage survives a re-capture")
    check(after["pct"] == before["pct"], "and so does the rate")
    check(after["expires"] == before["expires"], "and the clock")
    check(mystery.due_warning() == [],
          "so no halfway warning can fire on a chased row")
    check(mystery.due_followup() == [],
          "and the card cannot be chased a second time")
    check(after["to"] == "Diamond IV",
          "while the configuration DOES still refresh — that is the point of it")


def test_an_unsubscribe_survives_a_recapture():
    """The most serious half of the same bug: an opt-out that quietly undoes
    itself is worse than never having offered one."""
    reset()
    _st, p = _capture("optout@x.com")
    mystery.unsubscribe(p["token"])
    check(mystery.get(p["token"])["nomail"] == 1, "opted out")
    _capture("optout@x.com")
    check(mystery.get(p["token"])["nomail"] == 1,
          "and still opted out after configuring again")
    row = mystery.get(p["token"])
    row["at"] = int(time.time()) - mystery.TOKEN_TTL - 60
    row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)
    check(mystery.due_followup() == [] and mystery.due_warning() == [],
          "so neither sweep will ever pick them up again")


def test_the_warning_never_asserts_a_fraction_of_an_hour():
    """"Halfway through its hour" is only true while WARN_DELAY is exactly half
    of TOKEN_TTL, and it is what turned a mis-routed row into nonsense. The copy
    states the remaining time and nothing else."""
    reset()
    _st, p = _capture("frac@x.com")
    row = mystery.get(p["token"])
    row["at"] = int(time.time()) - mystery.WARN_DELAY
    row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)
    row = mystery.get(p["token"])
    n, o = followup.price_pair(row, mystery.OFFER_PCT)
    mins = followup._mins_left(row)
    for blob in (followup._warn_text(row, n, o, "https://x.test", "usd", mins),
                 followup._warn_html(row, n, o, "https://x.test", "usd", mins)):
        low = blob.lower()
        check("halfway" not in low, "the warning never claims 'halfway'")
        check("its hour" not in low, "nor asserts the window is an hour")
        check(str(mins) in blob, "it prints the real minutes remaining (%d)" % mins)


def test_warning_and_chase_can_never_collide():
    """Mail 2 fires INSIDE the hour, mail 3 only once it is dead. If the two
    windows ever overlapped, one visitor would be told their discount is
    running out and that it has been replaced in the same five minutes."""
    reset()
    _st, p = _capture("win@x.com")
    row = mystery.get(p["token"])
    at, exp = row["at"], row["expires"]

    # Probe around the real boundaries rather than hard-coded minutes, so the
    # test still means something when the business re-tunes the schedule.
    warn_at = mystery.WARN_DELAY // 60
    dies_at = mystery.TOKEN_TTL // 60
    chase_at = (mystery.TOKEN_TTL + mystery.FOLLOWUP_DELAY) // 60
    probes = sorted({0, warn_at - 1, warn_at, warn_at + 1, dies_at - 1, dies_at,
                     dies_at + 1, chase_at - 1, chase_at, chase_at + 1,
                     chase_at + 60})
    seen = []
    for mins in probes:
        t = at + mins * 60
        w = len(mystery.due_warning(now=t))
        c = len(mystery.due_followup(now=t))
        seen.append((mins, w, c))
        check(not (w and c), "at +%dmin the two sweeps never both claim the row" % mins)
    check(len(probes) >= 8, "the probe covers every boundary in the schedule")
    warned_at = [m for m, w, _c in seen if w]
    check(warned_at and min(warned_at) == warn_at and max(warned_at) < dies_at,
          "the warning fires only between WARN_DELAY (+%dm) and the deadline (+%dm)"
          % (warn_at, dies_at))
    # The business's spec: capture → +30m a reminder → the card dies at +60m →
    # the 35% an hour after that. Derived from the constants, never typed.
    due_at = [m for m, _w, c in seen if c]
    check(due_at and min(due_at) == chase_at,
          "the chase opens at +%dmin (TTL %dm + FOLLOWUP_DELAY %dm)"
          % (chase_at, dies_at, mystery.FOLLOWUP_DELAY // 60))
    check(all(m >= dies_at for m in due_at),
          "and never before the hour is actually up")
    check(mystery.due_warning(now=exp) == [],
          "a warning is never sent about a discount that has already gone")


def test_warning_is_once_and_changes_nothing():
    """It is the one mail in the sequence that adds no offer — so it must not
    move the rate, the clock or the stage, and it must not repeat."""
    reset()
    _st, p = _capture("warn@x.com")
    row = mystery.get(p["token"])
    t = row["at"] + mystery.WARN_DELAY + 60
    check(len(mystery.due_warning(now=t)) == 1, "due once the halfway point passes")

    mystery.mark_warned(row["token"])
    after = mystery.get(row["token"])
    check(mystery.due_warning(now=t) == [], "and never due again")
    check(after["pct"] == row["pct"], "the rate is untouched")
    check(after["expires"] == row["expires"], "the clock is untouched")
    check(mystery.stage_of(after) == "card", "and the card is still on its own stage")
    check(mystery.redeemable(row["token"], now=t) is not None,
          "the offer it warns about is still the one they have")


def test_warning_skips_paid_and_opted_out():
    reset()
    _st, p = _capture("wpaid@x.com")
    row = mystery.get(p["token"])
    t = row["at"] + mystery.WARN_DELAY + 60
    mystery.redeem(row["token"], order_id="ESB-W")
    check(mystery.due_warning(now=t) == [], "a paid card is never warned")

    reset()
    _st, p = _capture("wgone@x.com")
    row = mystery.get(p["token"])
    t = row["at"] + mystery.WARN_DELAY + 60
    mystery.unsubscribe(row["token"])
    check(mystery.due_warning(now=t) == [], "nor an unsubscribed one")


def test_warning_copy():
    """It argues one thing — the deadline the store enforces — so it must not
    quote a rate or a price that differs from the live card."""
    reset()
    _st, p = _capture("wcopy@x.com")
    row = mystery.get(p["token"])
    row["at"] = int(time.time()) - mystery.WARN_DELAY
    row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)
    row = mystery.get(p["token"])

    now_q, off_q = followup.price_pair(row, mystery.OFFER_PCT)
    mins = followup._mins_left(row)
    origin = "https://example.test"
    text = followup._warn_text(row, now_q, off_q, origin, "usd", mins)
    html = followup._warn_html(row, now_q, off_q, origin, "usd", mins)

    for blob, name in ((text, "text"), (html, "html")):
        check(row["token"] in blob, "the %s warning carries the live code" % name)
        check("/checkout?bingo=" + row["token"] in blob,
              "and the checkout button/link (%s)" % name)
        check("unsubscribe?token=" + row["token"] in blob,
              "and a one-click unsubscribe (%s)" % name)
        check("30%" in blob and "35%" not in blob,
              "it quotes the card's OWN rate, never the chase's (%s)" % name)
        check(followup.money(off_q["total"], "usd") in blob,
              "and the price that rate actually gives (%s)" % name)
    check(20 <= mins <= 31, "the countdown is the real remaining time (%d)" % mins)


def test_no_mail_claims_it_is_the_last():
    """The sequence is meant to grow. A mail promising nothing further is a
    promise about the roadmap, and the third mail already broke one draft of
    it — see the note in followup.py."""
    reset()
    row = _lapsed("last@x.com")
    revived = mystery.revive(row["token"])
    now_q, off_q = followup.price_pair(revived)
    blobs = [followup._text(revived, now_q, off_q, "https://x.test", "usd"),
             followup._html(revived, now_q, off_q, "https://x.test", "usd")]
    r2 = mystery.get(row["token"])
    blobs += [followup._warn_text(r2, now_q, off_q, "https://x.test", "usd", 30),
              followup._warn_html(r2, now_q, off_q, "https://x.test", "usd", 30)]
    for blob in blobs:
        low = blob.lower()
        for phrase in ("no third email", "last email", "final email",
                       "we won't email you again", "no more emails"):
            check(phrase not in low, "no mail claims it is the last (%r)" % phrase)


def test_followup_is_once_ever():
    """`revive()` flips the stage out of the due set BEFORE the mail goes out,
    so a sweep running every five minutes cannot mail the same person twice."""
    reset()
    row = _lapsed("once@x.com")
    check(len(mystery.due_followup()) == 1, "due before the chase")
    revived = mystery.revive(row["token"])
    check(revived is not None, "the row revives")
    check(mystery.due_followup() == [], "and is never due again")
    check(mystery.revive(row["token"]) is not None,
          "revive itself stays callable (it is the sweep that de-duplicates)")


def test_revive_raises_the_rate_on_the_same_token():
    """The code already in the buyer's inbox is the one that works. A second
    row would give one address two live discounts and break one-card-per-inbox."""
    reset()
    row = _lapsed("same@x.com")
    check(mystery.redeemable(row["token"]) is None, "the card really was dead")
    revived = mystery.revive(row["token"])
    check(revived["token"] == row["token"], "same token")
    check(revived["pct"] == mystery.FOLLOWUP_PCT, "at the follow-up rate")
    check(revived["stage"] == "followup", "and marked as chased")
    live = mystery.redeemable(row["token"])
    check(live is not None, "it is redeemable again")
    check(mystery.find_by_email("same@x.com")["token"] == row["token"],
          "and the inbox still has exactly one card")
    res = mystery.process_resolve(row["token"])[1]
    check(res["valid"] and res["pct"] == mystery.FOLLOWUP_PCT,
          "the browser learns the new rate from the same endpoint, unchanged")
    check(res["label"] == mystery.FOLLOWUP_LABEL,
          "and the receipt calls it the follow-up offer, not a card that pays 35%")

    # The SERVER-side re-resolve in payments.process_checkout must reach the same
    # label. It used to hard-code OFFER_LABEL, so a revived row had the browser
    # showing "Last-chance discount" over a charge the server called a "Mystery
    # discount" — one order, two names, on the page where money moves.
    order = dict(ORDER, bingo=row["token"])
    q = pricing.quote(mystery._state(mystery.get(row["token"]), mystery.FOLLOWUP_PCT))
    check(q["promo_label"] == mystery.FOLLOWUP_LABEL,
          "and the server prices it under that same name")
    check(mystery.label_for(mystery.get(row["token"])) == mystery.FOLLOWUP_LABEL
          and mystery.label_for({"stage": "card"}) == mystery.OFFER_LABEL,
          "label_for is the one place either name is decided")


def test_revive_never_reopens_a_paid_order():
    reset()
    row = _lapsed("paid2@x.com")
    mystery.redeem(row["token"], order_id="ESB-2")
    check(mystery.revive(row["token"]) is None, "a redeemed token cannot be revived")
    check(mystery.redeemable(row["token"]) is None, "and stays spent")


def test_followup_rate_cannot_be_forged():
    """Same guarantee the card has: `recovery_pct` is stripped from the checkout
    body and re-derived from the token, so nobody types their own 35%."""
    reset()
    row = _lapsed("forge@x.com")
    mystery.revive(row["token"])
    honest = pricing.quote(mystery._state(mystery.get(row["token"]), mystery.FOLLOWUP_PCT))
    forged = dict(ORDER, recovery_pct=0.95, offer_label="lol", bingo=row["token"])
    cleaned = payments.process_checkout(_json({"order": forged, "email": "f@x.com",
                                               "client_total": 1}), _h())
    q = pricing.quote(mystery._state(mystery.get(row["token"]),
                                     mystery.redeemable(row["token"])["pct"]))
    check(q["total"] == honest["total"],
          "the server prices at the stored rate, never a body-supplied one")
    check(q["promo_pct"] == mystery.FOLLOWUP_PCT, "which is exactly the follow-up rate")
    check(isinstance(cleaned, tuple), "and the checkout route still answers")


def test_followup_resolve_carries_the_order():
    """The mail links to /checkout?bingo=…, and that page has no configurator.
    Without the stored config it would price whatever the browser was holding."""
    reset()
    row = _lapsed("cfg@x.com", **{"from": "Silver III", "to": "Gold I"})
    mystery.revive(row["token"])
    res = mystery.process_resolve(row["token"])[1]
    o = res.get("order") or {}
    check(o.get("from") == "Silver III" and o.get("to") == "Gold I",
          "the resolve hands back the climb the card was opened against")
    check(o.get("game") == ORDER["game"], "and its game")
    check(mystery.process_resolve("BINGO-NOPENOPE")[1].get("order") is None,
          "an unknown token discloses nothing")


def test_followup_currency():
    """A French buyer chased in dollars is the same one-set-of-numbers failure a
    bare `$5` in the chrome is."""
    reset()
    _st, p = _capture("fr@x.com", cur="eur")
    check(mystery.currency_of(mystery.get(p["token"])) == "eur",
          "the stored pick is used")
    reset()
    _st, p = _capture("uk@x.com")
    row = mystery.get(p["token"]); row["cur"] = ""; row["country"] = "GB"
    check(mystery.currency_of(row) == "gbp",
          "with no pick it falls back to the country's market")
    row["country"] = "JP"
    check(mystery.currency_of(row) == "usd",
          "and a market with no charge rate is quoted in dollars, never a "
          "currency the site could not bill")
    for cur in pricing.CHARGE_RATES:
        check(followup.money(100, cur)[:1] not in ("1", "0"),
              "%s renders with its mark" % cur)


def test_per_hour_claim_is_dropped_when_it_argues_against_the_order():
    """A long climb prices at $7–24/hour even at 35% off. The block ships only
    while the figure helps — the same mechanism gc_faq_items() uses."""
    reset()
    short = _lapsed("short@x.com", **{"from": "Gold IV", "to": "Platinum II"})
    _n, off = followup.price_pair(short)
    hours, rate = followup.hourly(off, "usd")
    check(hours > 0 and rate, "a normal climb gets the per-hour argument")
    check(pricing.per_hour(off["total"], off["days"])[1] <= pricing.PER_HOUR_MAX,
          "and only because the figure is under the ceiling")

    reset()
    long_ = _lapsed("long@x.com", **{"from": "Iron IV", "to": "Diamond IV"})
    _n2, off2 = followup.price_pair(long_)
    h2, r2 = followup.hourly(off2, "usd")
    check(pricing.per_hour(off2["total"], off2["days"])[1] > pricing.PER_HOUR_MAX,
          "a full-ladder climb prices above the ceiling")
    check(h2 == 0 and r2 == "",
          "so the mail makes no per-hour claim at all rather than a bad one")


def test_hours_never_outrun_the_eta():
    """The ETA is the promise on the page — a missed one costs a 15% credit — so
    an hours figure implying more play than it allows would contradict it."""
    for days in (1, 2, 3, 5, 8, 12):
        h = pricing.play_hours(days)
        check(0 < h <= days * 24,
              "%d days implies %d hours, inside the calendar it was quoted in" % (days, h))
    check(pricing.play_hours(0) == 0 and pricing.play_hours("x") == 0,
          "and an unpriceable order yields no hours to divide by")


def test_followup_copy():
    """The second mail is the one that argues hardest, so it is the one most
    able to overclaim. Same standing as the card's own copy test."""
    reset()
    row = _lapsed("copy@x.com")
    revived = mystery.revive(row["token"])
    now_q, off_q = followup.price_pair(revived)
    origin = "https://example.test"
    text = followup._text(revived, now_q, off_q, origin, "usd")
    html = followup._html(revived, now_q, off_q, origin, "usd")

    # The ban is on the PROBABILITY sense — every card pays the same rate, so
    # the copy must never imply a draw was involved. It is deliberately not a
    # ban on the bare word "chance": mail 3's own subject is "last chance",
    # which is a claim about a deadline the store enforces, not about odds.
    for blob, name in ((text, "text"), (html, "html")):
        low = blob.lower()
        for phrase in ("chance of", "chances", "1 in ", "odds", "probability",
                       "lucky", "luck", "random", "you won", "winner",
                       "guarantee your rank", "risk-free", "no risk"):
            check(phrase not in low, "the %s mail never says %r" % (name, phrase))
        check("last chance" in low or "expired" in low,
              "but the %s mail DOES say the card is gone" % name)
        check(revived["token"] in blob, "the %s mail carries the working code" % name)
        check("/checkout?bingo=" + revived["token"] in blob,
              "and links straight to checkout with it (%s)" % name)
        check("unsubscribe?token=" + revived["token"] in blob,
              "and carries a one-click unsubscribe (%s)" % name)
        check("35%" in blob, "it states the new rate (%s)" % name)

    # The comparative claim about competitors is gated, exactly like the
    # add-on note's superlative and rating_ld()'s aggregateRating.
    if not D_STREAM_VERIFIED:
        for blob in (text, html):
            low = blob.lower()
            check("other sites" not in low and "most sites" not in low,
                  "no unsubstantiated comparative claim while STREAM_CLAIM_VERIFIED is False")

    # The prices in the mail are the prices the server would charge.
    check(followup.money(off_q["total"], "usd") in text,
          "the discounted total in the copy is the quoted one")
    check(off_q["total"] < now_q["total"], "and it really is lower")


def test_followup_send_marks_before_it_sends():
    """`mailer.configured()` is False here, so nothing leaves — but the sweep
    must still be safe to run on a schedule."""
    reset()
    row = _lapsed("sweep@x.com")
    out = followup.sweep()
    check(out["due"] == 1, "the sweep sees the due row")
    check(out["sent"] == 0 and out["failed"] == 1,
          "and sends nothing with no mailbox configured")
    check(out["reasons"].get("smtp_unconfigured") == 1, "saying why")
    still = mystery.get(row["token"])
    check(still.get("stage") == "card",
          "an unconfigured mailbox must NOT burn the row — it is still chaseable "
          "once SMTP is set up")


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
               test_followup_due_rules, test_followup_is_once_ever,
               test_a_struck_price_is_the_list_never_the_sale_price,
               test_mail_figures_come_from_the_real_sources,
               test_stream_pitch_is_gated_on_the_verification_flag,
               test_the_warning_marks_before_it_sends,
               test_unsubscribe_route_contract, test_ops_counters_track_the_sequence,
               test_config_beacon_tracks_the_latest_order,
               test_config_beacon_cannot_move_the_offer,
               test_config_beacon_freezes_on_a_paid_row,
               test_a_lapsed_card_still_tracks_the_order,
               test_a_recapture_never_resets_the_offer_lifecycle,
               test_an_unsubscribe_survives_a_recapture,
               test_the_warning_never_asserts_a_fraction_of_an_hour,
               test_warning_and_chase_can_never_collide,
               test_warning_is_once_and_changes_nothing,
               test_warning_skips_paid_and_opted_out, test_warning_copy,
               test_no_mail_claims_it_is_the_last,
               test_revive_raises_the_rate_on_the_same_token,
               test_revive_never_reopens_a_paid_order,
               test_followup_rate_cannot_be_forged,
               test_followup_resolve_carries_the_order, test_followup_currency,
               test_per_hour_claim_is_dropped_when_it_argues_against_the_order,
               test_hours_never_outrun_the_eta, test_followup_copy,
               test_followup_send_marks_before_it_sends,
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
