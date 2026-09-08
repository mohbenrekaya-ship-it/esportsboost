# -*- coding: utf-8 -*-
"""Abandoned-checkout recovery mail — the sender behind `carts.py`.

One job: take the carts `carts.due()` says are ready, re-price each one, mail the
buyer a single-use discount and mark the row so it is never mailed twice.

It composes its own message and shares only the `mailer.py` *transport*, exactly
the way `support.py` and `payments.py` do — see the "Outbound mail" section of
CLAUDE.md. Nothing here is sent `From:` the visitor, every interpolated value is
escaped, and `mailer.send()` never raises.

Things that are load-bearing:

  * **The price is re-quoted at send time, never read off the stored row.**
    `carts.py` keeps the configuration, not a trusted total — same rule as
    `payments.build_session()`. If pricing moves between capture and send, the
    mail quotes what the buyer would actually be charged today.
  * **The offer is the cart's own token**, resolved by `carts.redeemable()` and
    priced through `pricing.quote(recovery_pct=…)`. It is single-use and dies
    with the cart, so it can never become a public coupon the way an entry in
    `D.PROMOS` would (that table ships to the browser).
  * **Marked before it is sent, not after.** A mail server that accepts the
    message and then times out would otherwise leave the row `pending` and mail
    the same person on the next sweep. Losing one recovery mail is a missed
    upsell; sending four is a spam complaint against the domain the order
    confirmations go out on.
  * **Never mails a cart that was paid.** `carts.recover()` burns the row from
    the Stripe webhook, and `due()` only ever returns `pending`.
  * **Silent when SMTP is unconfigured** — the same degradation the rest of the
    mail seam has, so a preview deploy captures carts without pretending mail
    went out.

⚠ Consent: this mails somebody who typed an address into the checkout form and
did not finish. The checkout note has to say that can happen — see the copy under
`#k-email` in build.py. Every message carries a one-click unsubscribe.
"""
import sys
import time
from html import escape as esc

import carts
import data as D
import pricing


SUBJECT = "You left %s behind — here's %d%% off to finish"
# The one-day recall, accounts only. It argues the shelf rather than the
# discount: the code has not changed and saying so again would read as a second,
# better offer that is not there.
CHASE_SUBJECT = "Still want the %s? Your %d%% code is live for %s"
FROM_NAME = "eSports Boost"
OFFER_LABEL = "Come back offer"


def _state(cart, recovery_pct=0):
    """The order dict `pricing.quote()` wants, rebuilt from a stored cart."""
    return {
        "game": cart.get("game") or "",
        "service": cart.get("service") or "division",
        "from": cart.get("from") or "",
        "to": cart.get("to") or "",
        "mode": cart.get("mode") or "Solo",
        "region": cart.get("region") or "",
        "addons": cart.get("addons") or [],
        "wins": cart.get("wins") or 1,
        "placements": cart.get("placements") or 3,
        "unranked": bool(cart.get("unranked")),
        "bundle": cart.get("bundle") or None,
        "booster": cart.get("booster") or "",
        "coach": 0, "pack": 1, "focus": [0], "slot": "",
        # ⚠ On an account cart these two ARE the price: `account_pick()` resolves
        # the listing from the id and refuses the quote without it, and the
        # currency picks the listing's market row rather than converting. Drop
        # either and every account cart reports as unpriceable — which is what
        # they all did before the store carried them.
        "account": cart.get("account") or "",
        "currency": cart.get("cur") or "",
        "promo": cart.get("token") or "",
        "recovery_pct": recovery_pct,
        "offer_label": OFFER_LABEL,
    }


def price_pair(cart):
    """(normal_quote, recovery_quote) for a cart, or (None, None) if the stored
    configuration no longer prices — a ladder can be re-cut between capture and
    send, and a mail quoting `—` is worse than no mail."""
    now_q = pricing.quote(_state(cart))
    if now_q.get("invalid"):
        return None, None
    off_q = pricing.quote(_state(cart, carts.pct_for(cart)))
    if off_q.get("invalid"):
        return None, None
    return now_q, off_q


def _link(origin, cart, token):
    """Where the mail sends them back to.

    On a boost the token alone is enough: the buyer's configuration is already
    in that browser's localStorage, because a cart is captured ON the checkout
    page. An account is not — it is picked in the shop, two steps earlier — so
    somebody opening this on their phone would land on a checkout pricing
    whatever that device last configured, or the catalogue default. The listing
    and its shard therefore ride in the query and `accountFromQuery()` in app.js
    hydrates them through `normalize()`, the one validator; it strips both
    markers afterwards and leaves `cart=` in place for the discount resolve.
    Exactly the shape `?account=` links already take out of the shop."""
    from urllib.parse import quote as _q
    base = "%s/checkout?cart=%s" % (origin, token)
    if carts.is_account(cart) and cart.get("account"):
        base += "&account=%s" % _q(str(cart["account"]), safe="")
        if cart.get("region"):
            base += "&region=%s" % _q(str(cart["region"]), safe="")
    return base


def _unsub(origin, token):
    return "%s/api/cart/unsubscribe?token=%s" % (origin, token)


def _money(cart, q, amount):
    """One figure from a quote, in the currency the buyer was reading.

    Three things it has to respect, and they all ride on the QUOTE rather than
    on a guess about the product — the same rule `charge_for()` follows:
    `fixed` (an account price is the same digits in every market, so no rate is
    applied), `cents` (accounts are the one product priced to the cent — round
    $77.99 to $78 here and the mail quotes a price the checkout will not), and
    the row's own currency, converted through `pricing.CHARGE_RATES` and marked
    with `payments.CURRENCY_SIGNS`. No fifth sign table is defined here, for the
    reason CLAUDE.md's four-surfaces rule gives."""
    import payments
    cur = str(cart.get("cur") or "usd").lower()
    if cur not in pricing.CHARGE_RATES:
        cur = "usd"
    amt = float(amount or 0)
    if not q.get("fixed"):
        amt *= pricing.CHARGE_RATES[cur]
    sign = payments.CURRENCY_SIGNS.get(cur, "$")
    if q.get("cents"):
        return "%s%.2f" % (sign, amt)
    return "%s%d" % (sign, pricing._jsround(amt))


def _pct(cart):
    return int(round(carts.pct_for(cart) * 100))


def _what(cart, now_q):
    """What the buyer left behind, in the words of the product they left. An
    account is a thing on a shelf and a boost is a job of work, and the mail has
    to be able to say which — "your League of Legends order" over a ready-made
    account reads as a boost somebody never asked for."""
    if carts.is_account(cart):
        return now_q.get("summary") or "account"
    return now_q.get("summary") or cart.get("game") or "your order"


def _copy(cart, now_q, off_q, chase=False):
    """Every string that differs between the four messages this module can
    send — first or reminder, account or boost — resolved in ONE place so the
    subject, the heading and the body cannot describe different offers.

    ⚠ The reminder never raises the rate and never mints a second code. It is
    the same token at the same percentage with less time left on it, and the
    copy says so: a second mail quoting a better number teaches the reader that
    the first one was theatre, which is the one thing an expiring discount
    cannot survive."""
    pct = _pct(cart)
    what = _what(cart, now_q)
    acct = carts.is_account(cart)
    left = _left(cart)
    if chase:
        return {
            "subject": CHASE_SUBJECT % (what, pct, left),
            "head": "Your %s is still on the shelf." % what if acct
                    else "Still thinking it over?",
            "lede": ("Nobody else has taken it yet, and your <b style=\"color:#e8e3dd\">"
                     "%d%% code</b> is still live \u2014 for about %s." % (pct, left)),
            "text_head": "Your %s is still on the shelf." % what if acct
                         else "Still thinking it over?",
            "text_lede": ("Nobody else has taken it yet, and your %d%% code is "
                          "still live \u2014 for about %s." % (pct, left)),
            "cta": "Claim it" if acct else "Finish my order",
        }
    return {
        "subject": SUBJECT % (what, pct),
        "head": "You were one step away.",
        "lede": ("Your %s is still reserved in your basket. Here's "
                 "<b style=\"color:#e8e3dd\">%d%% off</b> to finish it."
                 % (esc(what), pct)) if acct else
                ("Your %s order is still saved. Here's "
                 "<b style=\"color:#e8e3dd\">%d%% off</b> to finish it."
                 % (esc(cart.get("game") or "boost"), pct)),
        "text_head": "You were one step away.",
        "text_lede": ("Your %s is still reserved in your basket." % what) if acct
                     else ("Your %s order is still saved."
                           % (cart.get("game") or "boost")),
        "cta": "Claim my account" if acct else "Finish my order",
    }


def _left(cart, now=None):
    """How long the code has left, in words. Derived from the token's own TTL
    and the row's capture time — never a typed "24 hours", which goes stale the
    moment `CART_TOKEN_TTL` moves and is simply false on a reminder sent a day
    into a seven-day window."""
    now = int(now or time.time())
    secs = carts.TOKEN_TTL - (now - int(cart.get("at") or now))
    if secs <= 0:
        return "a few more minutes"
    days = secs // 86400
    if days >= 2:
        return "%d more days" % days
    hours = max(1, secs // 3600)
    if hours >= 24:
        return "another day"
    return "%d more hour%s" % (hours, "" if hours == 1 else "s")


def _text(cart, now_q, off_q, origin, chase=False):
    token = cart.get("token", "")
    c = _copy(cart, now_q, off_q, chase)
    return (
        "%s\n\n"
        "%s\n\n"
        "  %s\n"
        "  You saw %s \u2014 now %s with the code below.\n\n"
        "Use this code at checkout to take %d%% off:\n\n"
        "  %s\n\n"
        "Finish your order here:\n%s\n\n"
        "The code works once and expires in %s. It replaces the current "
        "sale rather than stacking with it, so %s is the final price.\n\n"
        "Not interested? Unsubscribe: %s\n"
        % (c["text_head"], c["text_lede"], _what(cart, now_q),
           _money(cart, now_q, now_q["subtotal"]),
           _money(cart, off_q, off_q["total"]),
           _pct(cart), token, _link(origin, cart, token), _left(cart),
           _money(cart, off_q, off_q["total"]), _unsub(origin, token))
    )


def _html(cart, now_q, off_q, origin, chase=False):
    token = esc(cart.get("token", ""))
    c = _copy(cart, now_q, off_q, chase)
    climb = esc(_what(cart, now_q))
    eta = esc(now_q.get("eta") or "")
    link = esc(_link(origin, cart, cart.get("token", "")))
    unsub = esc(_unsub(origin, cart.get("token", "")))
    return """\
<!doctype html><html><body style="margin:0;background:#0b0a09;font-family:-apple-system,\
Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8e3dd">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
  <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#ff7a3f;\
margin:0 0 8px">eSports Boost</p>
  <h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">%(head)s</h1>
  <p style="font-size:15px;line-height:1.6;color:#b9b2aa;margin:0 0 24px">%(lede)s</p>

  <table style="width:100%%;border-collapse:collapse;background:#141210;border:1px solid \
rgba(255,255,255,.10);border-radius:10px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 6px;font-size:16px;font-weight:600">%(climb)s</p>
      <p style="margin:0;font-size:13px;color:#8f8880">Delivery %(eta)s</p>
      <p style="margin:14px 0 0;font-size:22px;font-weight:700">
        <span style="color:#8f8880;font-weight:400;font-size:16px;\
text-decoration:line-through">%(was)s</span>
        &nbsp;%(now)s</p>
    </td></tr>
  </table>

  <p style="margin:24px 0 8px;font-size:14px;color:#b9b2aa">Your code:</p>
  <p style="margin:0 0 24px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;\
font-size:20px;font-weight:700;letter-spacing:.06em;color:#ff7a3f;border:1px dashed \
rgba(255,122,63,.5);border-radius:8px;padding:12px 16px;text-align:center">%(token)s</p>

  <p style="margin:0 0 28px"><a href="%(link)s" style="display:block;text-align:center;\
background:linear-gradient(180deg,#ff8a3f,#ff4a1f);color:#120a06;font-weight:700;\
font-size:16px;text-decoration:none;padding:15px 20px;border-radius:10px">%(cta)s</a></p>

  <p style="font-size:12px;line-height:1.6;color:#77706a;margin:0 0 6px">
    The code works once and expires in %(left)s. It replaces the current sale rather than
    stacking with it, so %(now)s is the final price.</p>
  <p style="font-size:12px;color:#77706a;margin:0">
    <a href="%(unsub)s" style="color:#77706a">Unsubscribe</a></p>
</div></body></html>""" % {
        "head": esc(c["head"]), "lede": c["lede"], "cta": esc(c["cta"]),
        "climb": climb, "eta": eta, "token": token, "link": link,
        "unsub": unsub, "left": esc(_left(cart)),
        "was": esc(_money(cart, now_q, now_q["subtotal"])),
        "now": esc(_money(cart, off_q, off_q["total"])),
    }



def send_one(cart, origin=None, now=None):
    """Mail one cart. Returns (sent, reason).

    Marks the row **before** handing it to SMTP: a send that half-succeeds must
    not leave the cart mailable again on the next sweep.
    """
    import mailer  # lazy: only the sweep sends mail
    if not mailer.configured():
        return False, "smtp_unconfigured"

    email = cart.get("email") or ""
    if not mailer.valid(email):
        carts.mark(cart["token"], status="expired")
        return False, "bad_address"

    now_q, off_q = price_pair(cart)
    if not now_q:
        carts.mark(cart["token"], status="expired")
        return False, "unpriceable"

    if origin is None:
        import payments
        origin = payments.site_origin()

    now = int(now or time.time())
    carts.mark(cart["token"], status="mailed", mailed_at=now)

    ok, err = mailer.send(
        email, _copy(cart, now_q, off_q)["subject"],
        _text(cart, now_q, off_q, origin),
        html=_html(cart, now_q, off_q, origin), kind="cart_recovery")
    if not ok:
        sys.stderr.write("[recovery] %s -> %s failed: %s\n"
                         % (cart.get("token"), email, err))
        return False, err or "send_failed"
    return True, ""


def send_chase(cart, origin=None, now=None):
    """The one-day recall on an account cart. Returns (sent, reason).

    Same contract as `send_one()` in every respect that matters — marked before
    it is handed to SMTP, silent without a mailbox, never sent to a cart that
    was paid — with two differences that are the whole point of it being a
    separate function:

      * **It flips `stage`, not `status`.** The row stays `mailed`, because that
        is what it is; `stage` is what `due_chase()` reads, so one reminder is
        one reminder.
      * **It re-quotes and re-checks.** A listing that sold out in the
        intervening day no longer prices, and the row is retired rather than
        mailed — chasing somebody about a shelf that is empty is worse than
        saying nothing, and `ACCOUNT_ETA` promises them an instant handover.
    """
    import mailer
    if not mailer.configured():
        return False, "smtp_unconfigured"

    email = cart.get("email") or ""
    if not mailer.valid(email):
        carts.mark(cart["token"], status="expired")
        return False, "bad_address"

    now_q, off_q = price_pair(cart)
    if not now_q:
        # Sold out, or the catalogue moved under it. Retire rather than chase.
        carts.mark(cart["token"], status="expired")
        return False, "unpriceable"

    if origin is None:
        import payments
        origin = payments.site_origin()

    now = int(now or time.time())
    carts.mark_chased(cart["token"], now)

    ok, err = mailer.send(
        email, _copy(cart, now_q, off_q, chase=True)["subject"],
        _text(cart, now_q, off_q, origin, chase=True),
        html=_html(cart, now_q, off_q, origin, chase=True),
        kind="cart_recovery_chase")
    if not ok:
        sys.stderr.write("[recovery] chase %s -> %s failed: %s\n"
                         % (cart.get("token"), email, err))
        return False, err or "send_failed"
    return True, ""


def sweep(now=None, limit=50, origin=None):
    """Mail every cart that is due. Safe to call as often as you like — `due()`
    only returns `pending` rows older than `carts.DELAY_SECS`, and `send_one()`
    flips each one out of that set before the message goes out.

    Returns a summary dict for the caller to log or return as JSON.
    """
    now = int(now or time.time())
    rows = carts.due(now=now, limit=limit)
    sent = failed = 0
    reasons = {}
    for cart in rows:
        ok, why = send_one(cart, origin=origin, now=now)
        if ok:
            sent += 1
        else:
            failed += 1
            reasons[why] = reasons.get(why, 0) + 1
            if why == "smtp_unconfigured":
                break          # nothing will send this run; stop burning rows

    # ── the one-day recall, accounts only ────────────────────────────────
    # On the same sweep and behind the same secret, for the reason
    # `carts.process_sweep()` gives about the mystery follow-up: a second cron
    # entry is a second schedule and a second secret to keep in step. It cannot
    # collide with the first mail by construction — `due()` wants a `pending`
    # row and `due_chase()` a `mailed` one on stage `first`, and no row is both.
    chase_sent = chase_failed = 0
    chase_rows = []
    if "smtp_unconfigured" not in reasons:
        chase_rows = carts.due_chase(now=now, limit=limit)
        for cart in chase_rows:
            ok, why = send_chase(cart, origin=origin, now=now)
            if ok:
                chase_sent += 1
            else:
                chase_failed += 1
                reasons[why] = reasons.get(why, 0) + 1
                if why == "smtp_unconfigured":
                    break
    return {"due": len(rows), "sent": sent, "failed": failed,
            "chase_due": len(chase_rows), "chase_sent": chase_sent,
            "chase_failed": chase_failed,
            "reasons": reasons, "at": now}
