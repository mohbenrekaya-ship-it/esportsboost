#!/usr/bin/env python3
"""Account-stock tests — stdlib only, no framework, no network.

Run:  python3 site/tests/test_stock.py       (exits non-zero on any failure)

This store holds live credentials and hands one to a stranger the moment a
payment clears, so the things worth locking down are the ones that either sell
an account twice or leak one:

  * **a unit is claimed at most once** — two claims never return the same row,
    which is the property that stops two buyers being sent one login.
  * **a claim is idempotent per order** — Stripe retries its webhook, and the
    in-memory event de-dupe does not survive a cold start, so a redelivery must
    hand over the SAME account rather than burn a second one.
  * **the last unit is the last unit** — once a (listing, shard) is in the
    store, checkout refuses when it is empty; a pair the store has never held
    still sells on data.py's figure, so loading one shard does not take the
    other three off sale.
  * **no public payload carries a credential** — `public_counts()` and
    `summary()` are the two things that leave this module for a browser.
  * **the handover mail is redacted in the outbox** — the row proves the mail
    went out without keeping a second copy of the password.
  * **`user:pass` parses, and an ambiguous line is an error, not a guess** — a
    silently truncated password is discovered by the customer.

Nothing here opens a socket: the store is pointed at a temp file and SMTP is
unconfigured, so `mailer.send()` returns its "not configured" path.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

# Point every store this touches at a throwaway file BEFORE importing, and make
# sure no Upstash env leaks in from the shell (that would write to production
# inventory).
for _k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    os.environ.pop(_k, None)
_TMP = tempfile.NamedTemporaryFile(prefix="esb-stock-test-", suffix=".ndjson", delete=False)
_TMP.close()
os.environ["STOCK_LOG"] = _TMP.name
_TMPM = tempfile.NamedTemporaryFile(prefix="esb-stock-mail-", suffix=".ndjson", delete=False)
_TMPM.close()
os.environ["MAILLOG_LOG"] = _TMPM.name
# The handover must not try to reach a relay even if the developer's .env has
# one; `mailer.configured()` is false without these.
for _k in ("SMTP_USER", "SMTP_PASSWORD"):
    os.environ.pop(_k, None)

import data as D       # noqa: E402
import maillog         # noqa: E402
import mailer          # noqa: E402
import payments        # noqa: E402
import stock           # noqa: E402

_fails = []
SKU = "lol-gold"
REGION = D.ACCOUNT_REGIONS[0]
OTHER = D.ACCOUNT_REGIONS[1]


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


def reset():
    stock.clear()


def load(n=3, sku=SKU, region=REGION):
    text = "\n".join("player%d:secret%d" % (i, i) for i in range(n))
    rows, errors = stock.parse_lines(text, sku, region)
    stock.add(rows)
    return rows, errors


# -- the import format ----------------------------------------------------
def test_parse_user_pass():
    reset()
    rows, errors = stock.parse_lines(
        "\n".join([
            "# a comment",
            "",
            "alpha:pw1",
            "beta:pw2:inbox@mail.com",
            "gamma:pw3:inbox2@mail.com:inboxpw",
            "delta|pw:with:colons",
        ]), SKU, REGION)
    check(len(rows) == 4, "four accounts parsed, comments and blanks skipped")
    check(not errors, "no errors on a clean file")
    check(rows[0]["login"] == "alpha" and rows[0]["password"] == "pw1",
          "user:pass is the two-field shape")
    check(rows[1]["email"] == "inbox@mail.com" and not rows[1]["email_password"],
          "the third field is the account inbox")
    check(rows[2]["email_password"] == "inboxpw", "the fourth field is the inbox password")
    check(rows[3]["login"] == "delta" and rows[3]["password"] == "pw:with:colons",
          "a pipe separates a password that itself contains colons")
    check(all(r["sku"] == SKU and r["region"] == REGION for r in rows),
          "every unit carries the listing and the shard it was imported under")


def test_ambiguity_is_an_error_never_a_guess():
    rows, errors = stock.parse_lines("a:b:c:d:e", SKU, REGION)
    check(not rows and len(errors) == 1,
          "five colon-separated fields is refused, not truncated")
    check("|" in errors[0][1], "and the error says how to fix it")
    rows, errors = stock.parse_lines("noseparator", SKU, REGION)
    check(not rows and errors, "a line with no separator is an error")
    rows, errors = stock.parse_lines("who:", SKU, REGION)
    check(not rows and errors, "an empty password is an error")


def test_unknown_listing_or_shard_is_refused():
    rows, errors = stock.parse_lines("a:b", "lol-nonesuch", REGION)
    check(not rows and errors, "a listing the catalogue does not sell stores nothing")
    rows, errors = stock.parse_lines("a:b", SKU, "Mars")
    check(not rows and errors, "a shard the shop does not sell on stores nothing")


def test_one_row_per_login():
    reset()
    load(3)
    again, _ = stock.parse_lines("player0:changed", SKU, REGION)
    res = stock.add(again)
    check(res["added"] == 0 and res["duplicate"] == 1,
          "re-importing a login already on that shard adds nothing")
    check(stock.available(SKU, REGION) == 3, "so the count does not double")
    other, _ = stock.parse_lines("player0:secret0", SKU, OTHER)
    check(stock.add(other)["added"] == 1,
          "the same login on ANOTHER shard is a different unit (it is region-locked)")


# -- the claim ------------------------------------------------------------
def test_a_unit_is_claimed_at_most_once():
    reset()
    load(3)
    seen = set()
    for i in range(3):
        row = stock.claim(SKU, REGION, order_id="ESB-%d" % i, buyer="b%d@x.com" % i)
        check(row is not None, "claim %d returned a unit" % (i + 1))
        seen.add(row["id"])
    check(len(seen) == 3, "three claims, three different units - never the same login twice")
    check(stock.available(SKU, REGION) == 0, "the shelf is empty afterwards")
    check(stock.claim(SKU, REGION, order_id="ESB-9") is None,
          "and a fourth claim gets nothing rather than reselling one")


def test_a_claim_is_idempotent_per_order():
    reset()
    load(3)
    first = stock.claim(SKU, REGION, order_id="ESB-DUP", buyer="b@x.com")
    again = stock.claim(SKU, REGION, order_id="ESB-DUP", buyer="b@x.com")
    check(first and again and first["id"] == again["id"],
          "a redelivered webhook is handed the SAME account back")
    check(stock.available(SKU, REGION) == 2,
          "so a Stripe retry does not burn a second unit")


def test_claim_is_per_listing_and_per_shard():
    reset()
    load(2, sku=SKU, region=REGION)
    check(stock.claim(SKU, OTHER, order_id="ESB-X") is None,
          "a shard with no stock hands over nothing even when another shard has some")
    check(stock.claim("lol-iron", REGION, order_id="ESB-Y") is None,
          "and so does another listing")


def test_restock_puts_it_back():
    reset()
    load(1)
    row = stock.claim(SKU, REGION, order_id="ESB-REF", buyer="b@x.com")
    check(stock.available(SKU, REGION) == 0, "sold, so nothing on the shelf")
    back = stock.restock(row["id"])
    check(back and stock.available(SKU, REGION) == 1,
          "a refunded order's account goes back on sale")
    check(stock.claim(SKU, REGION, order_id="ESB-REF")["id"] == row["id"],
          "and the order id it carried is cleared, so it can be claimed again")


# -- what the shop is allowed to sell -------------------------------------
def test_the_last_unit_is_the_last_unit():
    reset()
    check(stock.sellable(SKU, REGION),
          "with an empty store every listing still sells on data.py's figure")
    load(1)
    check(stock.sellable(SKU, REGION), "a loaded listing with stock sells")
    check(stock.sellable("lol-iron", REGION),
          "a listing the store has NEVER held still sells on the catalogue figure - "
          "loading one tier does not take the others off sale")
    check(stock.sellable(SKU, OTHER),
          "and a shard the store has never held for this listing sells too")
    stock.claim(SKU, REGION, order_id="ESB-LAST")
    check(not stock.sellable(SKU, REGION),
          "but once that pair is sold out the store refuses it")


def test_checkout_refuses_an_account_it_cannot_hand_over():
    reset()
    load(1)
    stock.claim(SKU, REGION, order_id="ESB-GONE")
    order = {"service": "account", "account": SKU, "region": REGION,
             "game": D.ACCOUNT_GAME, "client_total": 0}
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_stock_check"
    try:
        status, payload = payments.process_checkout(json.dumps(order).encode(), "http://x")
    finally:
        os.environ.pop("STRIPE_SECRET_KEY", None)
    check(status == 409 and payload.get("error") == "out_of_stock",
          "checkout refuses a sold-out account BEFORE it reaches Stripe")
    check("another" in payload.get("message", "").lower(),
          "and tells the buyer what to do instead")


# -- nothing public may carry a credential --------------------------------
def test_no_public_payload_carries_a_credential():
    reset()
    load(2)
    row = stock.claim(SKU, REGION, order_id="ESB-PUB", buyer="b@x.com")
    blob = json.dumps(stock.public_counts())
    check("secret" not in blob and "player" not in blob,
          "/api/stock's payload holds no login and no password")
    check(json.loads(blob)["units"]["%s|%s" % (SKU, REGION)] == 1,
          "it is a count, and the count is right")
    ops_blob = json.dumps(stock.summary())
    check("secret" not in ops_blob, "the /ops list carries no password")
    check(row["login"] not in ops_blob, "and no full login - it is masked")
    check(row["id"] in ops_blob, "the unit id IS there, so one can be revealed on purpose")
    check(stock.reveal(row["id"])["password"] == row["password"],
          "reveal() - behind the ops token - is the one thing that returns it")


def test_sold_out_is_reported_as_a_zero_never_as_a_gap():
    """The bug this test exists for: a sold-out pair used to drop OUT of the
    public map, which the client reads as "not loaded" and answers with
    data.py's hand-set figure — putting a listing with nothing behind it back
    on the shelf, one page load after it sold out."""
    reset()
    load(1)
    stock.claim(SKU, REGION, order_id="ESB-ZERO")
    units = stock.public_counts()["units"]
    key = "%s|%s" % (SKU, REGION)
    check(key in units and units[key] == 0,
          "a sold-out pair is present in /api/stock with an explicit 0")
    check(("lol-iron|" + REGION) not in units,
          "a pair the store never held is absent, so it keeps the catalogue figure")


def test_the_public_route_publishes_nothing_by_default():
    """The business's call: the shop keeps quoting data.py's hand-set figures,
    and the store is enforced at the till instead of on the card. A 204 is what
    tells the client to keep the server-rendered numbers, and it is the answer
    both when the store is empty and when the counts are switched off."""
    reset()
    status, payload = stock.process_list()
    check(status == 204 and payload is None,
          "an empty store answers 204 so the shop keeps its server-rendered counts")
    load(1)
    check(stock.PUBLIC_COUNTS is False, "publishing counts is OFF unless asked for")
    status, payload = stock.process_list()
    check(status == 204 and payload is None,
          "a LOADED store still answers 204 with STOCK_PUBLIC_COUNTS unset")
    saved = stock.PUBLIC_COUNTS
    try:
        stock.PUBLIC_COUNTS = True
        status, payload = stock.process_list()
        check(status == 200 and payload["total"] == 1,
              "and answers with the real counts once it is switched on")
    finally:
        stock.PUBLIC_COUNTS = saved
    check(stock.sellable(SKU, REGION) is True,
          "switching the DISPLAY off never switches the sold-out refusal off")


# -- the handover ---------------------------------------------------------
def test_the_delivery_mail_states_the_credentials():
    reset()
    load(1)
    row = stock.claim(SKU, REGION, order_id="ESB-MAIL", buyer="b@x.com")
    text = stock.delivery_text(row, "ESB-MAIL")
    check(row["login"] in text and row["password"] in text,
          "the buyer's mail carries the login and the password")
    check("ESB-MAIL" in text, "and the order number")
    check(str(D.ACCOUNT_WARRANTY_MONTHS) in text,
          "and the warranty window, read off the constant")
    html = stock.delivery_html(row, "ESB-MAIL")
    check(row["password"] in html and "<table" in html, "the HTML part carries it too")


def test_the_handover_is_redacted_in_the_outbox():
    reset()
    load(1)
    row = stock.claim(SKU, REGION, order_id="ESB-LOG", buyer="b@x.com")
    check(not mailer.configured(),
          "SMTP is unconfigured in this test, so nothing is actually sent")
    ok, err = stock.deliver(row, "b@x.com", "ESB-LOG")
    check(not ok and err == "mail_not_configured",
          "an unconfigured mailbox degrades rather than pretending")
    rows = maillog.read()
    mine = [r for r in rows if r.get("kind") == "account_delivery"]
    check(len(mine) == 1, "the attempt is still recorded in the outbox")
    body = json.dumps(mine[0])
    check(row["password"] not in body and row["login"] not in body,
          "but the credentials are NOT in it - the outbox has no per-row deletion")
    check(row["id"] in body, "it names the unit instead, so ops can find the real ones")


def test_an_order_with_nothing_to_hand_over_is_reported():
    reset()
    load(1)
    stock.claim(SKU, REGION, order_id="ESB-TAKEN")
    res = stock.fulfil({"service": "account", "account": SKU, "region": REGION},
                       "ESB-EMPTY", "b@x.com")
    check(res["ok"] is False and res["reason"] == "out_of_stock",
          "a paid order with an empty shelf reports it rather than failing silently")
    alerts = [r for r in maillog.read() if r.get("kind") == "stock_alert"]
    check(len(alerts) >= 1, "and an alert to ops is logged (SMTP off -> recorded as failed)")


# -- the console's write path ---------------------------------------------
def test_there_are_44_slots_whether_or_not_they_are_stocked():
    reset()
    all_slots = stock.slots()
    check(len(all_slots) == len(D.ACCOUNTS) * len(D.ACCOUNT_REGIONS),
          "every listing x every server is a slot (%d), stocked or not"
          % (len(D.ACCOUNTS) * len(D.ACCOUNT_REGIONS)))
    check(all(s["shown"] >= 0 and "available" in s for s in all_slots),
          "each carries both figures — what we hold and what the site advertises")
    check(all(s["available"] is None for s in all_slots),
          "an unstocked slot's shelf count is None, not 0 — the same "
          "never-loaded/sold-out distinction the public map draws")
    one = stock.slot(SKU, REGION)
    check(one and one["listing"] and one["code"] and one["rows"] == [],
          "and one opens with its catalogue facts and an empty key list")
    check(stock.slot("nope", REGION) is None and stock.slot(SKU, "Mars") is None,
          "a slot that is not in the catalogue does not exist")


def test_add_edit_delete_a_key():
    reset()
    res = stock.process_import(SKU, REGION, "alpha:pw1\nbeta:pw2:in@x.com\nbroken")
    check(res["added"] == 2 and len(res["errors"]) == 1,
          "add reports what landed AND which line was refused, with its number")
    check(res["errors"][0]["line"] == 3, "the line number is the one in the paste")

    uid = stock.slot(SKU, REGION)["rows"][0]["id"]
    row = stock.update(uid, {"login": "renamed", "password": "newpw", "note": "checked"})
    check(row and row["login"] == "renamed" and row["password"] == "newpw",
          "edit rewrites the credential")
    check(stock.get(uid)["note"] == "checked", "and the note beside it")
    check(stock.update(uid, {"password": ""}) is None,
          "but a unit cannot be edited into having no password")
    check(stock.available(SKU, REGION) == 2, "editing never moves the shelf count")

    check(stock.delete(uid) is not None, "delete removes it")
    check(stock.available(SKU, REGION) == 1 and stock.get(uid) is None,
          "and it comes off the shelf with it — not left as a dead id in the queue")
    again = stock.add(stock.parse_lines("renamed:pw", SKU, REGION)[0])
    check(again["added"] == 1,
          "a deleted login can be added again — the dedupe set let go of it too")


def test_emptying_a_slot_completely_puts_it_back_on_the_catalogue_figure():
    """Otherwise a slot stocked, emptied and never sold from is pinned at zero:
    permanently refusing orders behind a page that still advertises it, with no
    way back except adding keys."""
    reset()
    load(1)
    check(stock.known(SKU, REGION) and not stock.sellable(SKU, REGION) is False,
          "a stocked pair is known")
    uid = stock.slot(SKU, REGION)["rows"][0]["id"]
    stock.delete(uid)
    check(not stock.known(SKU, REGION),
          "emptying it entirely forgets the pair")
    check(stock.sellable(SKU, REGION),
          "so it sells on data.py's figure again rather than refusing for ever")
    load(2)
    stock.claim(SKU, REGION, order_id="ESB-KEPT")
    check(stock.known(SKU, REGION) and stock.available(SKU, REGION) == 1,
          "a sold row keeps the pair known while it is still there")


def test_hold_takes_a_unit_off_sale_without_losing_it():
    reset()
    load(2)
    uid = stock.slot(SKU, REGION)["rows"][0]["id"]
    stock.hold(uid)
    check(stock.available(SKU, REGION) == 1, "a held unit is off the shelf")
    check(stock.get(uid)["status"] == "held", "but still stored")
    claimed = [stock.claim(SKU, REGION, order_id="ESB-H%d" % i) for i in range(2)]
    check(claimed[0] and claimed[0]["id"] != uid and claimed[1] is None,
          "and can never be claimed while it is held")
    stock.restock(uid)
    check(stock.available(SKU, REGION) == 1, "putting it back returns it to the shelf")


def test_one_handover_per_unit():
    reset()
    load(1)
    md = {"service": "account", "account": SKU, "region": REGION}
    stock.fulfil(md, "ESB-ONCE", "b@x.com")
    row = stock.by_order("ESB-ONCE")
    stock.mark(row["id"], mailed=123)               # pretend the first mail went out
    before = len([r for r in maillog.read() if r.get("kind") == "account_delivery"])
    res = stock.fulfil(md, "ESB-ONCE", "b@x.com")
    after = len([r for r in maillog.read() if r.get("kind") == "account_delivery"])
    check(res["reason"] == "already_delivered" and after == before,
          "a replayed event does not send a second copy of somebody's password")


def test_an_empty_shelf_sends_the_buyer_to_discord():
    """The confirmation has already told them the credentials are on the way and
    ACCOUNT_ETA promised instant, so silence here is not a delay — it is a
    broken promise they are sitting and watching."""
    reset()
    load(1)
    stock.claim(SKU, REGION, order_id="ESB-TAKEN")
    res = stock.fulfil({"service": "account", "account": SKU, "region": REGION},
                       "ESB-NOSTOCK", "buyer@example.com")
    check(res["reason"] == "out_of_stock", "the order is reported as unfulfilled")
    # The outbox is shared across these tests, so this order names itself.
    note = [r for r in maillog.read()
            if r.get("kind") == "account_backorder" and "ESB-NOSTOCK" in json.dumps(r)]
    check(len(note) == 1, "the BUYER is mailed, not only ops")
    body = json.dumps(note[0])
    check(D.DISCORD_URL in body, "and pointed at the Discord, where a person can hand it over")
    check("ESB-NOSTOCK" in body, "with the order number they have to quote")
    check("reply" in body.lower(), "and a reply-by-mail route for anyone not on Discord")
    check("hour" not in body.lower() and "minute" not in body.lower(),
          "it never invents a time — nothing here knows when the next unit lands")
    alerts = [r for r in maillog.read()
              if r.get("kind") == "stock_alert" and "ESB-NOSTOCK" in json.dumps(r)]
    check(alerts and "Discord" in json.dumps(alerts[0]),
          "and ops is told to watch for them there")


def test_the_backorder_note_needs_a_real_address():
    reset()
    ok, err = stock.notify_backorder("ESB-X", SKU, REGION, "")
    check(not ok and err == "no_recipient",
          "a guest checkout with no email gets no note, and says so rather than throwing")


def test_fulfil_never_raises():
    reset()
    for md in ({}, {"service": "account"}, {"service": "account", "account": "nope"},
               {"service": "account", "account": SKU, "region": "Mars"}):
        try:
            stock.fulfil(md, "ESB-JUNK", "")
        except Exception as e:                                  # noqa: BLE001
            check(False, "fulfil() raised on %r: %s" % (md, e))
            return
    check(True, "fulfil() swallows every junk payload - a raise here means Stripe "
                "redelivers and the order is fulfilled twice")


def test_purge_keeps_the_sale_and_drops_the_secret():
    reset()
    load(1)
    row = stock.claim(SKU, REGION, order_id="ESB-OLD", buyer="b@x.com")
    stock.mark(row["id"], sold_at=1)               # sold in 1970
    check(stock.purge_sold(30) == 1, "an old sale is purged")
    after = stock.get(row["id"])
    check(after["password"] == "" and after["login"] == "(purged)",
          "the credentials are gone")
    check(after["order_id"] == "ESB-OLD" and after["status"] == "sold",
          "the sale itself is still on the record")


def main():
    for fn in (test_parse_user_pass, test_ambiguity_is_an_error_never_a_guess,
               test_unknown_listing_or_shard_is_refused, test_one_row_per_login,
               test_a_unit_is_claimed_at_most_once, test_a_claim_is_idempotent_per_order,
               test_claim_is_per_listing_and_per_shard, test_restock_puts_it_back,
               test_the_last_unit_is_the_last_unit,
               test_checkout_refuses_an_account_it_cannot_hand_over,
               test_no_public_payload_carries_a_credential,
               test_sold_out_is_reported_as_a_zero_never_as_a_gap,
               test_the_public_route_publishes_nothing_by_default,
               test_the_delivery_mail_states_the_credentials,
               test_the_handover_is_redacted_in_the_outbox,
               test_an_order_with_nothing_to_hand_over_is_reported,
               test_there_are_44_slots_whether_or_not_they_are_stocked,
               test_add_edit_delete_a_key,
               test_emptying_a_slot_completely_puts_it_back_on_the_catalogue_figure,
               test_hold_takes_a_unit_off_sale_without_losing_it,
               test_one_handover_per_unit,
               test_an_empty_shelf_sends_the_buyer_to_discord,
               test_the_backorder_note_needs_a_real_address,
               test_fulfil_never_raises, test_purge_keeps_the_sale_and_drops_the_secret):
        print("\n" + fn.__name__)
        fn()
    for path in (_TMP.name, _TMPM.name):
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
