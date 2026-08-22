# -*- coding: utf-8 -*-
"""The second mystery-discount mail — the one that goes after a lapsed card.

`recovery.py` is to `carts.py` what this is to `mystery.py`: it takes the rows
`mystery.due_followup()` says are ready, re-prices each one, raises the offer,
and marks the row so the same person is never chased twice.

The lead it works is the best one the site has. Somebody opened the
configurator, set two ranks, read a price, handed over an address for a code —
and then did not buy. The first mail said one hour and meant it, so by the time
this runs that offer is genuinely dead.

It is the **second** stage of the sequence and `due_followup()` guarantees it
fires once — but the copy deliberately does not say it is the last word. A third
mail is planned, and a promise about what we will not send is a promise about
the roadmap rather than about this order: the mail states the deadline the store
enforces, and stops there.

**What it argues, and why each part is built the way it is:**

  * **A better rate, stated as a bump.** 30 → 35, on the same token, so the code
    already sitting in their inbox is the one that works. `mystery.revive()` is
    the whole mechanism (see the note there) — nothing is reissued.
  * **The price per hour of play**, from *their* configuration and in *their*
    currency, because "it is expensive" is the objection this mail exists to
    answer and a total answers it worse than a rate does. It is derived through
    `pricing.per_hour()` off the ETA the site already promises, never typed —
    and it is **dropped entirely** when the figure does not argue for the order
    (`pricing.per_hour_worth_saying()`). A long climb prices at $7–24/hour even
    at 35% off, and printing that is an argument against buying.
  * **What the free screen share is worth on this order**, quoted with the same
    arithmetic `pricing.addon_list_price()` uses for the struck figure on the
    order card — so the mail and the page state one number. The copy says
    **tick it**, not "it is included": `stream` is `pct=0` *with* a `was_pct`,
    which `data.py` calls free-but-optional and ships **unticked** on purpose.
    A mail promising an option the buyer then has to find, on a checkout where
    it sits unchecked, sells something the order does not carry — and
    pre-ticking it from a link would override a deliberate default that
    `test_free_optional_addons()` locks. Naming the row is the honest fix and
    it is the one that actually gets it attached. The *comparative* half of
    that pitch ("other sites charge for this") is gated on
    `D.STREAM_CLAIM_VERIFIED`, which is False: it is a claim about every
    competitor at once and it is not substantiated. Flip the flag when it is and
    the sentence ships with no code change, exactly the way `rating_ld()` waits
    on `TRUSTPILOT_URL`.
  * **Pause**, in the words the site already commits to (`D.DASHBOARD_POINTS`),
    not a new promise written for a sales mail.
  * **A link straight to checkout**, carrying the token — and the row's stored
    configuration comes back with it, so the page prices the order the mail
    quoted rather than whatever that browser was last holding.

Everything `recovery.py` is careful about applies here unchanged: nothing is
sent `From:` the visitor, every interpolated value is escaped, `mailer.send()`
never raises, the price is re-quoted at send time rather than read off the row,
and **the row is marked before the message goes out** — a half-succeeding SMTP
call must not leave the card chaseable on the next sweep.

⚠ The watch-live pitch is the load-bearing risk in this file, and it is a
product one rather than a code one: `streams.py` does not exist, so nothing
opens a Discord channel and nothing tells a booster to share their screen. The
mail makes that the centrepiece of the offer. Until the seam is built, every
order it wins is a manual promise somebody in ops has to keep. See CLAUDE.md's
"Watch live" section.
"""
import sys
import time
from html import escape as esc

import data as D
import mystery
import pricing


SUBJECT = "One more step: %d%% off your %s order"
# The struck figure beside the free screen share, as a fraction of the boost —
# the add-on table's own `was_pct`, read rather than repeated so the mail and
# the order card cannot quote two different values for the same option.
STREAM_ID = "stream"


# ══════════════════════════════════════════════════════════════════════════
#  money — the buyer's currency, from the tables that already exist
# ══════════════════════════════════════════════════════════════════════════
def money(total_usd, cur="usd", decimals=0):
    """A whole-unit price in the row's currency.

    Converted through `pricing.CHARGE_RATES` — the same table the Stripe session
    is built from — and marked with `payments.CURRENCY_SIGNS`, which is one of
    the four surfaces CLAUDE.md requires to agree on `C$`. No fifth sign table
    is defined here for exactly that reason."""
    import payments
    cur = str(cur or "usd").lower()
    if cur not in pricing.CHARGE_RATES:
        cur = "usd"
    amount = float(total_usd or 0) * pricing.CHARGE_RATES[cur]
    sign = payments.CURRENCY_SIGNS.get(cur, "$")
    if decimals:
        return "%s%.*f" % (sign, decimals, amount)
    return "%s%d" % (sign, pricing._jsround(amount))


# ══════════════════════════════════════════════════════════════════════════
#  the numbers this mail argues with — all derived, none typed
# ══════════════════════════════════════════════════════════════════════════
def price_pair(row, pct=None):
    """(list quote, offer quote) for a row at the follow-up rate.

    Re-quoted at send time, never read off the stored row — same rule as
    `recovery.price_pair()` and `payments.build_session()`. (None, None) when
    the configuration no longer prices: a ladder can be re-cut between capture
    and send, and a mail quoting `—` is worse than no mail at all."""
    pct = mystery.FOLLOWUP_PCT if pct is None else pct
    now_q = pricing.quote(mystery._state(row))
    if now_q.get("invalid"):
        return None, None
    off_q = pricing.quote(mystery._state(row, pct))
    if off_q.get("invalid"):
        return None, None
    return now_q, off_q


def hourly(off_q, cur="usd"):
    """(hours, formatted rate) for the per-hour block, or (0, "").

    Empty means **do not make the argument** — see `pricing.PER_HOUR_MAX`. The
    rate is quoted against the discounted total, because that is the order the
    reader is being offered, and to two decimals, because a rate rounded to a
    whole unit reads as a price rather than a rate."""
    total, days = off_q.get("total") or 0, off_q.get("days") or 0
    if not pricing.per_hour_worth_saying(total, days):
        return 0, ""
    hours, rate = pricing.per_hour(total, days)
    if not hours:
        return 0, ""
    return hours, money(rate, cur, decimals=2)


def stream_worth(off_q, cur="usd"):
    """What the free screen share would cost on this order, or "".

    `addon_base` is what an add-on is a percentage OF on this quote — the list
    boost normally, a bundle's flat price on a bundle — so the figure is the one
    a real charge would be computed from, which is the property that makes the
    struck price on the order card defensible in the first place."""
    a = next((x for x in D.ADDONS if x.get("id") == STREAM_ID), None)
    was = float((a or {}).get("was_pct") or 0)
    if not was:
        return ""
    base = float(off_q.get("addon_base") or 0)
    worth = pricing._jsround(base * was)
    return money(worth, cur) if worth >= 1 else ""


def pause_promise():
    """The pause line, in the words the product already commits to."""
    for _glyph, title, body in D.DASHBOARD_POINTS:
        if "pause" in title.lower():
            return title, body
    return "Pause on one click", ""


def stream_label():
    """The row's own name, as the checkout page prints it — so the mail tells
    the buyer to tick something they will actually see."""
    a = next((x for x in D.ADDONS if x.get("id") == STREAM_ID), None)
    return (a or {}).get("label") or "Watch your booster play"


def stream_line():
    """The screen-share sentence. The comparative half ships only once the
    claim is substantiated — `D.STREAM_CLAIM_VERIFIED` is the same gate the
    add-on note's superlative sits behind."""
    if getattr(D, "STREAM_CLAIM_VERIFIED", False):
        return ("Most sites charge for a screen share, or will not do it at all. "
                "It is free on every order here.")
    return "It costs nothing, on any order, at any rank."


# ══════════════════════════════════════════════════════════════════════════
#  the message
# ══════════════════════════════════════════════════════════════════════════
def _link(origin, token):
    return "%s/checkout?bingo=%s" % (origin, token)


def _unsub(origin, token):
    return "%s/api/bingo/unsubscribe?token=%s" % (origin, token)


def _hours_left(row, now=None):
    secs = mystery._int(row.get("expires")) - int(now or time.time())
    return max(1, int(round(secs / 3600.0)))


def _text(row, now_q, off_q, origin, cur):
    token = row.get("token", "")
    pct = int(round((row.get("pct") or mystery.FOLLOWUP_PCT) * 100))
    was = int(round(mystery.OFFER_PCT * 100))
    climb = now_q.get("summary") or row.get("game") or "your order"
    hours, rate = hourly(off_q, cur)
    worth = stream_worth(off_q, cur)
    _t, pause = pause_promise()
    out = (
        "Your card expired before you used it, so we put something better behind it.\n\n"
        "  %s  —  now %d%% off, up from %d%%.\n\n"
        "  %s\n"
        "  %s instead of %s. Delivery %s.\n\n"
        % (token, pct, was, climb,
           money(off_q["total"], cur), money(now_q["total"], cur), now_q.get("eta") or "")
    )
    if hours:
        out += (
            "If the price is what stopped you, look at it the other way. That order "
            "is about %d hours of play on your account. At %s that is %s an hour — "
            "and it is %d hours of climbing you do not have to do.\n\n"
            % (hours, money(off_q["total"], cur), rate, hours))
    out += (
        "And you do not have to take our word for any of it, because you can watch it "
        "happen. Tick \"%s\" at checkout and you get a live screen share of every game "
        "your booster plays, on your own dashboard%s. %s\n\n"
        % (stream_label(), (" — worth %s on this order" % worth) if worth else "",
           stream_line()))
    out += "%s %s\n\n" % (_t + ".", pause)
    # States the deadline the store actually enforces, and nothing about what
    # else we may or may not send. A mail promising "no third email" is a
    # promise about the ROADMAP, not about this order — the sequence is meant
    # to grow, and a claim like that turns the next stage into a broken word.
    out += ("This one runs for %d hours, and then the code stops working.\n\n"
            "Finish your order:\n%s\n\n" % (_hours_left(row), _link(origin, token)))
    out += ("The code works once and replaces the current sale rather than stacking with "
            "it, so %s is the final price.\n\n"
            "Not interested? Unsubscribe: %s\n"
            % (money(off_q["total"], cur), _unsub(origin, token)))
    return out


def _html(row, now_q, off_q, origin, cur):
    token = row.get("token", "")
    pct = int(round((row.get("pct") or mystery.FOLLOWUP_PCT) * 100))
    was = int(round(mystery.OFFER_PCT * 100))
    hours, rate = hourly(off_q, cur)
    worth = stream_worth(off_q, cur)
    _t, pause = pause_promise()

    hour_block = ""
    if hours:
        hour_block = """\
  <table style="width:100%%;border-collapse:collapse;background:#141210;border:1px solid \
rgba(255,255,255,.10);border-radius:10px;margin:0 0 20px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;\
color:#8f8880">If the price is what stopped you</p>
      <p style="margin:0;font-size:15px;line-height:1.6;color:#b9b2aa">
        That order is about <b style="color:#e8e3dd">%(hours)d hours of play</b> on your
        account. At %(now)s that is <b style="color:#ff7a3f">%(rate)s an hour</b> — and it is
        %(hours)d hours of climbing you do not have to do.</p>
    </td></tr>
  </table>""" % {"hours": hours, "now": esc(money(off_q["total"], cur)), "rate": esc(rate)}

    return """\
<!doctype html><html><body style="margin:0;background:#0b0a09;font-family:-apple-system,\
Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8e3dd">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
  <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#ff7a3f;\
margin:0 0 8px">eSports Boost</p>
  <h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">Your card expired. This one is better.</h1>
  <p style="font-size:15px;line-height:1.6;color:#b9b2aa;margin:0 0 24px">
    You did not use it in the hour, so we put <b style="color:#e8e3dd">%(pct)d%% off</b> behind
    the same code — up from %(was)d%%. Nothing else to do; it is already on the order below.</p>

  <table style="width:100%%;border-collapse:collapse;background:#141210;border:1px solid \
rgba(255,255,255,.10);border-radius:10px;margin:0 0 20px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 6px;font-size:16px;font-weight:600">%(climb)s</p>
      <p style="margin:0;font-size:13px;color:#8f8880">Delivery %(eta)s</p>
      <p style="margin:14px 0 0;font-size:22px;font-weight:700">
        <span style="color:#8f8880;font-weight:400;font-size:16px;\
text-decoration:line-through">%(oldp)s</span>
        &nbsp;%(newp)s</p>
    </td></tr>
  </table>
%(hour_block)s
  <table style="width:100%%;border-collapse:collapse;background:#0f1a12;border:1px solid \
rgba(74,222,128,.28);border-radius:10px;margin:0 0 24px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;\
color:#4ade80">Free to add%(worth_tag)s</p>
      <p style="margin:0 0 10px;font-size:15px;line-height:1.6;color:#b9b2aa">
        <b style="color:#e8e3dd">%(stream_label)s.</b> A live screen share of every game,
        on your own dashboard. %(stream)s Tick it at checkout — it is the row with the
        green FREE flag.</p>
      <p style="margin:0;font-size:15px;line-height:1.6;color:#b9b2aa">
        <b style="color:#e8e3dd">%(pause_t)s</b> %(pause)s</p>
    </td></tr>
  </table>

  <p style="margin:0 0 8px;font-size:14px;color:#b9b2aa">Your code:</p>
  <p style="margin:0 0 24px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;\
font-size:20px;font-weight:700;letter-spacing:.06em;color:#ff7a3f;border:1px dashed \
rgba(255,122,63,.5);border-radius:8px;padding:12px 16px;text-align:center">%(token)s</p>

  <p style="margin:0 0 12px"><a href="%(link)s" style="display:block;text-align:center;\
background:linear-gradient(180deg,#ff8a3f,#ff4a1f);color:#120a06;font-weight:700;\
font-size:16px;text-decoration:none;padding:15px 20px;border-radius:10px">\
Finish my order — %(newp)s</a></p>
  <p style="margin:0 0 28px;text-align:center;font-size:13px;color:#8f8880">
    Runs for %(left)d hours, then the code stops working.</p>

  <p style="font-size:12px;line-height:1.6;color:#77706a;margin:0 0 6px">
    The code works once and replaces the current sale rather than stacking with it, so
    %(newp)s is the final price.</p>
  <p style="font-size:12px;color:#77706a;margin:0">
    <a href="%(unsub)s" style="color:#77706a">Unsubscribe</a></p>
</div></body></html>""" % {
        "pct": pct, "was": was,
        "climb": esc(now_q.get("summary") or row.get("game") or "your order"),
        "eta": esc(now_q.get("eta") or ""),
        "oldp": esc(money(now_q["total"], cur)), "newp": esc(money(off_q["total"], cur)),
        "hour_block": hour_block,
        "worth_tag": (" — worth %s" % esc(worth)) if worth else "",
        "stream": esc(stream_line()), "stream_label": esc(stream_label()),
        "pause_t": esc(_t), "pause": esc(pause),
        "token": esc(token), "link": esc(_link(origin, token)),
        "unsub": esc(_unsub(origin, token)), "left": _hours_left(row),
    }


# ══════════════════════════════════════════════════════════════════════════
#  mail 2 of 3 — the halfway warning, while the card is still live
# ══════════════════════════════════════════════════════════════════════════
# The only message in the sequence that adds nothing. It does not raise the
# rate, does not extend the clock and does not make a new argument — it says the
# code is running out, which is the one claim on this whole flow that the store
# itself enforces and that nobody can dispute. ⚠ It states the REMAINING TIME
# and never "halfway through its hour": that phrasing is only true while
# WARN_DELAY is exactly half of TOKEN_TTL, and it is what turned a mis-routed
# row into a mail reading "1425 minutes left … halfway through its hour". That is exactly why it is short:
# a mail with no new offer that still takes three screens to say so reads as
# padding, and the reader has already seen the pitch half an hour ago.
WARN_SUBJECT = "Your %d%% code ends in %d minutes"


def _mins_left(row, now=None):
    secs = mystery._int(row.get("expires")) - int(now or time.time())
    return max(1, int(round(secs / 60.0)))


def _warn_text(row, now_q, off_q, origin, cur, mins):
    token = row.get("token", "")
    return (
        "Quick one — your code runs out in %d minutes.\n\n"
        "  %s  —  %d%% off, %d minutes left.\n\n"
        "  %s\n"
        "  %s instead of %s. Delivery %s.\n\n"
        "Finish your order:\n%s\n\n"
        "When the %d minutes are up the code stops working and the price goes "
        "back to %s. Nothing else about the order changes.\n\n"
        "Not interested? Unsubscribe: %s\n"
        % (mins, token, int(round((row.get("pct") or mystery.OFFER_PCT) * 100)), mins,
           now_q.get("summary") or row.get("game") or "your order",
           money(off_q["total"], cur), money(now_q["total"], cur),
           now_q.get("eta") or "", _link(origin, token), mins,
           money(now_q["total"], cur), _unsub(origin, token)))


def _warn_html(row, now_q, off_q, origin, cur, mins):
    token = row.get("token", "")
    pct = int(round((row.get("pct") or mystery.OFFER_PCT) * 100))
    return """\
<!doctype html><html><body style="margin:0;background:#0b0a09;font-family:-apple-system,\
Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8e3dd">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
  <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#ff7a3f;\
margin:0 0 8px">eSports Boost</p>
  <h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">%(mins)d minutes left on your code.</h1>
  <p style="font-size:15px;line-height:1.6;color:#b9b2aa;margin:0 0 24px">
    Your <b style="color:#e8e3dd">%(pct)d%% off</b> is already on the order below — you just
    have to finish it before the clock runs out.</p>

  <table style="width:100%%;border-collapse:collapse;background:#141210;border:1px solid \
rgba(255,255,255,.10);border-radius:10px;margin:0 0 24px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 6px;font-size:16px;font-weight:600">%(climb)s</p>
      <p style="margin:0;font-size:13px;color:#8f8880">Delivery %(eta)s</p>
      <p style="margin:14px 0 0;font-size:22px;font-weight:700">
        <span style="color:#8f8880;font-weight:400;font-size:16px;\
text-decoration:line-through">%(oldp)s</span>
        &nbsp;%(newp)s</p>
    </td></tr>
  </table>

  <p style="margin:0 0 8px;font-size:14px;color:#b9b2aa">Your code:</p>
  <p style="margin:0 0 24px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;\
font-size:20px;font-weight:700;letter-spacing:.06em;color:#ff7a3f;border:1px dashed \
rgba(255,122,63,.5);border-radius:8px;padding:12px 16px;text-align:center">%(token)s</p>

  <p style="margin:0 0 12px"><a href="%(link)s" style="display:block;text-align:center;\
background:linear-gradient(180deg,#ff8a3f,#ff4a1f);color:#120a06;font-weight:700;\
font-size:16px;text-decoration:none;padding:15px 20px;border-radius:10px">\
Finish my order &mdash; %(newp)s</a></p>
  <p style="margin:0 0 28px;text-align:center;font-size:13px;color:#8f8880">
    %(mins)d minutes, then the price goes back to %(oldp)s.</p>

  <p style="font-size:12px;color:#77706a;margin:0">
    <a href="%(unsub)s" style="color:#77706a">Unsubscribe</a></p>
</div></body></html>""" % {
        "mins": mins, "pct": pct,
        "climb": esc(now_q.get("summary") or row.get("game") or "your order"),
        "eta": esc(now_q.get("eta") or ""),
        "oldp": esc(money(now_q["total"], cur)), "newp": esc(money(off_q["total"], cur)),
        "token": esc(token), "link": esc(_link(origin, token)),
        "unsub": esc(_unsub(origin, token)),
    }


def send_warning(row, origin=None, now=None):
    """Mail the halfway warning. Returns (sent, reason).

    **Marks the row before it sends**, same rule as the chase: a half-succeeding
    SMTP call must not leave the card warnable on every sweep for the rest of
    its hour. Unlike `send_one()` this touches nothing else — no revive, no new
    rate, no new clock. The offer the reader is being warned about is exactly
    the one they already have.
    """
    import mailer
    if not mailer.configured():
        return False, "smtp_unconfigured"

    email = row.get("email") or ""
    if not mailer.valid(email):
        mystery.mark(row["token"], nomail=1)
        return False, "bad_address"

    now = int(now or time.time())
    now_q, off_q = price_pair(row, row.get("pct") or mystery.OFFER_PCT)
    if not now_q:
        mystery.mark(row["token"], nomail=1)
        return False, "unpriceable"

    mins = _mins_left(row, now)
    if origin is None:
        import payments
        origin = payments.site_origin()
    cur = mystery.currency_of(row)

    mystery.mark_warned(row["token"], now=now)
    ok, err = mailer.send(
        email,
        WARN_SUBJECT % (int(round((row.get("pct") or mystery.OFFER_PCT) * 100)), mins),
        _warn_text(row, now_q, off_q, origin, cur, mins),
        html=_warn_html(row, now_q, off_q, origin, cur, mins), kind="bingo_warn")
    if not ok:
        sys.stderr.write("[followup] warn %s -> %s failed: %s\n"
                         % (row.get("token"), email, err))
        return False, err or "send_failed"
    return True, ""


def sweep_warnings(now=None, limit=50, origin=None):
    """Warn every card that is halfway through its hour."""
    now = int(now or time.time())
    rows = mystery.due_warning(now=now, limit=limit)
    sent = failed = 0
    reasons = {}
    for row in rows:
        ok, why = send_warning(row, origin=origin, now=now)
        if ok:
            sent += 1
        else:
            failed += 1
            reasons[why] = reasons.get(why, 0) + 1
            if why == "smtp_unconfigured":
                break
    return {"due": len(rows), "sent": sent, "failed": failed,
            "reasons": reasons, "at": now}


# ══════════════════════════════════════════════════════════════════════════
#  mail 3 of 3 — the chase, once the card is dead
# ══════════════════════════════════════════════════════════════════════════
def send_one(row, origin=None, now=None):
    """Chase one lapsed card. Returns (sent, reason).

    **Revives the row before handing anything to SMTP.** `revive()` flips the
    stage out of the `due_followup()` set, so a send that half-succeeds costs
    one mail rather than mailing the same person on every five-minute sweep
    from now on — the same trade `recovery.send_one()` makes and for the same
    reason. It also means the better rate is live the moment the message can
    possibly be read.
    """
    import mailer                     # lazy: only the sweep sends mail
    if not mailer.configured():
        return False, "smtp_unconfigured"

    email = row.get("email") or ""
    if not mailer.valid(email):
        mystery.mark(row["token"], nomail=1)
        return False, "bad_address"

    now_q, off_q = price_pair(row)
    if not now_q:
        # Unpriceable today. Retire it from the sweep rather than trying again
        # every five minutes for three days — the configuration is not coming
        # back, and the buyer's own token is untouched either way.
        mystery.mark(row["token"], nomail=1)
        return False, "unpriceable"

    if origin is None:
        import payments
        origin = payments.site_origin()

    now = int(now or time.time())
    revived = mystery.revive(row["token"], now=now)
    if not revived:
        return False, "already_paid"
    cur = mystery.currency_of(revived)

    ok, err = mailer.send(
        email,
        SUBJECT % (int(round(revived.get("pct", mystery.FOLLOWUP_PCT) * 100)),
                   row.get("game") or "boost"),
        _text(revived, now_q, off_q, origin, cur),
        html=_html(revived, now_q, off_q, origin, cur), kind="bingo_chase")
    if not ok:
        sys.stderr.write("[followup] %s -> %s failed: %s\n"
                         % (row.get("token"), email, err))
        return False, err or "send_failed"
    mystery.mark(revived["token"], followup_mailed=1)
    return True, ""


def sweep(now=None, limit=50, origin=None):
    """Chase every card that is due. Safe to call as often as the scheduler
    allows: `due_followup()` only returns un-chased rows past their deadline,
    and `send_one()` revives each one out of that set before the message goes
    out, so an address is mailed exactly once.

    Returns a summary dict for the caller to log or return as JSON.
    """
    now = int(now or time.time())
    rows = mystery.due_followup(now=now, limit=limit)
    sent = failed = 0
    reasons = {}
    for row in rows:
        ok, why = send_one(row, origin=origin, now=now)
        if ok:
            sent += 1
        else:
            failed += 1
            reasons[why] = reasons.get(why, 0) + 1
            if why == "smtp_unconfigured":
                break          # nothing will send this run; stop burning rows
    return {"due": len(rows), "sent": sent, "failed": failed,
            "reasons": reasons, "at": now}


def sweep_all(now=None, limit=50, origin=None):
    """Both stages, in the order a card meets them.

    Warnings first: a card that is halfway through its hour is a live offer and
    the cheaper mail to get out on time, and running the chase first would give
    a slow sweep the chance to expire a row between the two passes. They can
    never collide on one row anyway — `due_warning()` requires the card still be
    inside its hour and `due_followup()` requires it be past it.
    """
    now = int(now or time.time())
    return {"warn": sweep_warnings(now=now, limit=limit, origin=origin),
            "chase": sweep(now=now, limit=limit, origin=origin), "at": now}
