#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drive the accounts shop's abandoned-cart sequence on a fake clock and print it.

    python3 site/tools/rehearse_account_carts.py

The sibling of `rehearse_mail_sequence.py`, and it exists for the same reason:
this sequence is time-based — the code 30 minutes after somebody leaves the pay
page, one recall a day later — so the only way to see it whole is to drive the
clock. Nothing here opens a socket. Every store is a temp file and
`mailer.send` is replaced with a capture, so it is safe to run on a laptop, in
CI, or on a box holding production credentials.

What it proves, in order:

  1. the two mails fire at the right minutes and nowhere else
  2. an account cart PRICES (the listing and the currency are stored, which is
     the whole reason these were never mailed before) and both messages quote
     the shop's own figure, to the cent, in the buyer's currency
  3. the guards hold: a boost is never recalled, a buyer is never chased, an
     unsubscribe sticks, a re-capture cannot reset the sequence, and nothing is
     ever sent twice
  4. every message landed in the outbox with its body

A developer script: never part of a build or a deploy.
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

for _k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    os.environ.pop(_k, None)
for _var in ("CARTS_LOG", "ORDERS_LOG", "MAILLOG_LOG", "BINGO_LOG"):
    _t = tempfile.NamedTemporaryFile(prefix="esb-rehearse-cart-", suffix=".ndjson",
                                     delete=False)
    _t.close()
    os.environ[_var] = _t.name
os.environ["SITE_URL"] = "https://www.esportsboost.com"

import carts        # noqa: E402
import maillog      # noqa: E402
import mailer       # noqa: E402
import orders       # noqa: E402
import recovery     # noqa: E402

SENT = []
CLOCK = [int(time.time())]
FAILS = []


def _capture(to, subject, text, html=None, reply_to="", sender_name="", kind="",
             **kw):
    SENT.append({"to": to, "subject": subject, "text": text, "kind": kind,
                 "at": CLOCK[0]})
    maillog.record(to=to, subject=subject, text=text, html=html or "", kind=kind,
                   ok=True, sender="info@esportsboost.com", now=CLOCK[0])
    return True, ""


mailer.send = _capture
mailer.configured = lambda: True


def ok(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def at(minutes):
    CLOCK[0] = T0 + minutes * 60
    return CLOCK[0]


def sweep():
    """One cron tick at the current clock — both mails, exactly as /api/sweep
    drives them."""
    before = len(SENT)
    out = recovery.sweep(now=CLOCK[0], origin="https://www.esportsboost.com")
    return out, SENT[before:]


def capture(email, **over):
    """One buyer reaching the pay page on a ready-made account."""
    body = dict({"email": email, "game": "League of Legends", "service": "account",
                 "account": "lol-unranked-basic", "region": "Europe West",
                 "mode": "Solo", "addons": [], "cur": "eur"}, **over)
    return carts.process_capture(json.dumps(body).encode(), lambda _k: "")


def age(token, minutes_ago):
    """Backdate a cart so `minutes_ago` have passed since it was captured."""
    r = carts.get(token)
    r["at"] = CLOCK[0] - minutes_ago * 60
    carts.put(r)


print("=" * 78)
print("ACCOUNT CART REHEARSAL — no socket is opened, no message leaves")
print("=" * 78)
print("schedule: left the pay page +0  ·  the code +%d min  ·  the recall +%dh"
      % (carts.DELAY_SECS // 60,
         (carts.DELAY_SECS + carts.ACCOUNT_CHASE_DELAY) // 3600))
print("rates   : account %g%%  ·  boost %g%%  ·  code lives %d days"
      % (carts.ACCOUNT_PCT * 100, carts.RECOVERY_PCT * 100,
         carts.TOKEN_TTL // 86400))

# ── 1. the sequence, minute by minute ─────────────────────────────────────
print("\n1. THE SEQUENCE, DRIVEN ON THE CLOCK")
st, payload = capture("player@example.com")
TOK = payload["token"]
T0 = carts.get(TOK)["at"]
ok(st == 200 and TOK.startswith("BACK-"), "the cart is captured with a token")
ok(len(SENT) == 0, "and nothing is mailed while they might still be paying")

timeline = []
for m in (5, 15, 29, 30, 31, 60, 600, 1439, 1440, 1470, 1471, 1475, 2000, 4320):
    at(m)
    _out, new = sweep()
    for msg in new:
        timeline.append((m, msg["kind"], msg["subject"]))

print("     %-8s %-24s %s" % ("minute", "kind", "subject"))
for m, kind, subj in timeline:
    print("     +%-7d %-24s %s" % (m, kind, subj[:44]))
ok(len(timeline) == 2, "exactly two mails, ever (%d)" % len(timeline))
ok(timeline and timeline[0][0] == 30 and timeline[0][1] == "cart_recovery",
   "the code lands on the 30-minute tick")
ok(len(timeline) > 1 and timeline[1][1] == "cart_recovery_chase",
   "the recall lands a day after the code, not a day after capture")
ok(len(timeline) > 1 and timeline[1][0] == 1470,
   "…at +%d minutes" % (timeline[1][0] if len(timeline) > 1 else -1))

# ── 2. what the two mails actually say ────────────────────────────────────
print("\n2. WHAT THEY SAY")
row = carts.get(TOK)
now_q, off_q = recovery.price_pair(row)
ok(now_q is not None, "an account cart prices at send time (the listing is stored)")
pct = int(round(carts.ACCOUNT_PCT * 100))
for msg in SENT:
    print("     " + msg["subject"])
first, again = SENT[0], SENT[1]
ok(("%d%%" % pct) in first["subject"] and ("%d%%" % pct) in again["subject"],
   "both quote the same %d%% — the recall is not a better offer" % pct)
ok(TOK in first["text"] and TOK in again["text"], "both carry the SAME code")
shown = recovery._money(row, off_q, off_q["total"])
ok(shown in first["text"] and shown in again["text"],
   "both quote the shop's own price, to the cent, in the buyer's currency (%s)" % shown)
ok(("account=%s" % row["account"]) in first["text"],
   "the link carries the listing, so a phone that never configured it lands right")
ok("/api/cart/unsubscribe?token=" in first["text"]
   and "/api/cart/unsubscribe?token=" in again["text"],
   "and both carry a one-click unsubscribe")
print("     list %s  →  with the code %s"
      % (recovery._money(row, now_q, now_q["subtotal"]), shown))

# ── 3. the guards ─────────────────────────────────────────────────────────
print("\n3. THE GUARDS")

# a boost cart is mailed once and never recalled
st, pb = capture("boost@example.com", service="division", account="",
                 **{"from": "Gold IV", "to": "Platinum II"})
age(pb["token"], 60)
n = len(SENT)
sweep()
ok(len(SENT) == n + 1, "a boost cart is mailed once")
carts.mark(pb["token"], mailed_at=CLOCK[0] - carts.ACCOUNT_CHASE_DELAY * 3)
n = len(SENT)
sweep()
ok(len(SENT) == n, "and never recalled — the second mail is the accounts shop's")

# somebody who came back and bought is never chased
st, pp = capture("paid@example.com")
age(pp["token"], 60)
sweep()                                             # the code goes out
orders.append([{"order_id": "ESB-PAID1", "email": "paid@example.com",
                "total": 30, "status": "paid", "service": "account",
                "game": "League of Legends"}])
carts.mark(pp["token"], mailed_at=CLOCK[0] - carts.ACCOUNT_CHASE_DELAY - 60)
n = len(SENT)
sweep()
ok(len(SENT) == n, "a buyer who came back and paid is never recalled")
ok(carts.get(pp["token"])["status"] == "recovered",
   "and the row is retired, so no later sweep asks again")

# an unsubscribe sticks
st, pu = capture("nomail@example.com")
carts.process_unsubscribe(pu["token"])
age(pu["token"], 60)
n = len(SENT)
sweep()
ok(len(SENT) == n, "an unsubscribed cart is never mailed")

# a re-capture cannot reset the sequence
st, pr = capture("recap@example.com")
age(pr["token"], 60)
sweep()
carts.mark(pr["token"], mailed_at=CLOCK[0] - carts.ACCOUNT_CHASE_DELAY - 60)
sweep()                                             # recalled
before = carts.get(pr["token"])
capture("recap@example.com", account="lol-iron")
after = carts.get(pr["token"])
ok(after["stage"] == "chased" and after["token"] == before["token"],
   "a re-capture cannot put a recalled cart back on stage one")
ok(after["account"] == "lol-iron",
   "but the configuration still tracks what they are actually looking at")
n = len(SENT)
sweep()
ok(len(SENT) == n, "and it is not recalled a second time")

# ── 4. the outbox ─────────────────────────────────────────────────────────
print("\n4. THE OUTBOX")
s = maillog.summary(days=30)
ok(s["total"] == len(SENT), "every message sent is in the outbox (%d)" % s["total"])
ok(all(r["text"] for r in s["recent"]), "each row carries its body")
print("     %-34s %s" % ("kind", "count"))
for k in s["kinds"]:
    print("     %-34s %d" % (k["label"], k["count"]))

# ── 5. what /ops shows ────────────────────────────────────────────────────
print("\n5. THE /OPS MODULE")
summ = carts.summary(days=30)
a = summ["accounts"]
print("     abandoned %d · mailed %d · recalled %d · recovered %d · rate %s%%"
      % (a["total"], a["mailed"], a["chased"], a["recovered"], a["recovery_rate"]))
ok(a["total"] < summ["total"], "accounts are reported apart from the boosts")
ok(a["chased"] >= 1, "and the recall is counted, so it can be judged")

print("\n" + "=" * 78)
if FAILS:
    print("FAILED: %d" % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED — %d mails, %d in the outbox" % (len(SENT), s["total"]))
