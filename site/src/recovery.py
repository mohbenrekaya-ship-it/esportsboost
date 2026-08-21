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


SUBJECT = "You left %s behind — here's 30%% off to finish"
FROM_NAME = "eSports Boost"


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
        "promo": cart.get("token") or "",
        "recovery_pct": recovery_pct,
    }


def price_pair(cart):
    """(normal_quote, recovery_quote) for a cart, or (None, None) if the stored
    configuration no longer prices — a ladder can be re-cut between capture and
    send, and a mail quoting `—` is worse than no mail."""
    now_q = pricing.quote(_state(cart))
    if now_q.get("invalid"):
        return None, None
    off_q = pricing.quote(_state(cart, carts.RECOVERY_PCT))
    if off_q.get("invalid"):
        return None, None
    return now_q, off_q


def _link(origin, token):
    return "%s/checkout?cart=%s" % (origin, token)


def _unsub(origin, token):
    return "%s/api/cart/unsubscribe?token=%s" % (origin, token)


def _usd(n):
    return "$%s" % int(round(n))


def _text(cart, now_q, off_q, origin):
    token = cart.get("token", "")
    climb = now_q.get("summary") or cart.get("game") or "your order"
    return (
        "You were one step away.\n\n"
        "Your %s order is still saved:\n\n"
        "  %s\n"
        "  You saw %s — now %s with the code below.\n\n"
        "Use this code at checkout to take 30%% off:\n\n"
        "  %s\n\n"
        "Finish your order here:\n%s\n\n"
        "The code works once and expires in 7 days. It replaces the current "
        "sale rather than stacking with it, so %s is the final price.\n\n"
        "Not interested? Unsubscribe: %s\n"
        % (cart.get("game") or "boost", climb,
           _usd(now_q["total"]), _usd(off_q["total"]),
           token, _link(origin, token), _usd(off_q["total"]),
           _unsub(origin, token))
    )


def _html(cart, now_q, off_q, origin):
    token = esc(cart.get("token", ""))
    climb = esc(now_q.get("summary") or cart.get("game") or "your order")
    game = esc(cart.get("game") or "boost")
    eta = esc(now_q.get("eta") or "")
    link = esc(_link(origin, cart.get("token", "")))
    unsub = esc(_unsub(origin, cart.get("token", "")))
    return """\
<!doctype html><html><body style="margin:0;background:#0b0a09;font-family:-apple-system,\
Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8e3dd">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
  <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#ff7a3f;\
margin:0 0 8px">eSports Boost</p>
  <h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">You were one step away.</h1>
  <p style="font-size:15px;line-height:1.6;color:#b9b2aa;margin:0 0 24px">
    Your %(game)s order is still saved. Here's <b style="color:#e8e3dd">30%% off</b> to finish it.</p>

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
font-size:16px;text-decoration:none;padding:15px 20px;border-radius:10px">\
Finish my order</a></p>

  <p style="font-size:12px;line-height:1.6;color:#77706a;margin:0 0 6px">
    The code works once and expires in 7 days. It replaces the current sale rather than
    stacking with it, so %(now)s is the final price.</p>
  <p style="font-size:12px;color:#77706a;margin:0">
    <a href="%(unsub)s" style="color:#77706a">Unsubscribe</a></p>
</div></body></html>""" % {
        "game": game, "climb": climb, "eta": eta, "token": token, "link": link,
        "unsub": unsub, "was": esc(_usd(now_q["total"])),
        "now": esc(_usd(off_q["total"])),
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
        email, SUBJECT % (cart.get("game") or "your boost"),
        _text(cart, now_q, off_q, origin),
        html=_html(cart, now_q, off_q, origin))
    if not ok:
        sys.stderr.write("[recovery] %s -> %s failed: %s\n"
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
    return {"due": len(rows), "sent": sent, "failed": failed,
            "reasons": reasons, "at": now}
