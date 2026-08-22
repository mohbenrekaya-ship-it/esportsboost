#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the whole outbound-mail lifecycle against throwaway stores and print it.

    python3 site/tools/rehearse_mail_sequence.py

Nothing here opens a socket. Every store is pointed at a temp file and
`mailer.send` is replaced with a capture, so this can be run on a laptop, in
CI, or against production credentials without a single message leaving.

It exists because the sequence is time-based — a card, a reminder half an hour
later, a last call an hour after that — so the only way to see it whole is to
drive the clock. Two incidents reached real customers before this did.

What it proves, in order:

  1. the three mails fire at the right minutes and nowhere else
  2. each one says what it should, with prices from the live engine
  3. the guards hold: a buyer is never chased, an unsubscribe sticks, a
     re-capture cannot reset the offer, nothing is ever sent twice
  4. every message landed in the outbox with its body

A developer script: never part of a build or a deploy, like everything else in
site/tools/.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

for _k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    os.environ.pop(_k, None)
for _var in ("BINGO_LOG", "CARTS_LOG", "ORDERS_LOG", "MAILLOG_LOG", "GUIDES_LOG"):
    _t = tempfile.NamedTemporaryFile(prefix="esb-rehearse-", suffix=".ndjson",
                                     delete=False)
    _t.close()
    os.environ[_var] = _t.name
os.environ["SITE_URL"] = "https://www.esportsboost.com"

import carts        # noqa: E402
import followup     # noqa: E402
import maillog      # noqa: E402
import mailer       # noqa: E402
import mystery      # noqa: E402
import orders       # noqa: E402

SENT = []
_real_send = mailer.send


def _capture(to, subject, text, html=None, reply_to="", sender_name="", kind=""):
    SENT.append({"to": to, "subject": subject, "text": text, "kind": kind,
                 "at": CLOCK[0]})
    maillog.record(to=to, subject=subject, text=text, html=html or "", kind=kind,
                   ok=True, sender="info@esportsboost.com", now=CLOCK[0])
    return True, ""


mailer.send = _capture
mailer.configured = lambda: True

CLOCK = [int(time.time())]
FAILS = []


def ok(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def at(minutes):
    """Move the clock to N minutes after the card was opened."""
    CLOCK[0] = T0 + minutes * 60
    return CLOCK[0]


def sweep():
    """One cron tick, both mailers, at the current clock."""
    before = len(SENT)
    warn = followup.sweep_warnings(now=CLOCK[0])
    chase = followup.sweep(now=CLOCK[0])
    return warn, chase, SENT[before:]


def issue(email, **cfg):
    body = dict({"email": email, "game": "League of Legends", "service": "division",
                 "from": "Gold IV", "to": "Platinum II", "mode": "Solo",
                 "region": "Europe West", "addons": ["priority"], "cur": "usd"}, **cfg)
    import json
    return mystery.process_issue(json.dumps(body).encode(), lambda _k: "")


def age(token, minutes_ago):
    """Backdate a card so `minutes_ago` have passed since it was opened."""
    r = mystery.get(token)
    r["at"] = CLOCK[0] - minutes_ago * 60
    r["expires"] = r["at"] + mystery.TOKEN_TTL
    mystery.put(r)


print("=" * 78)
print("MAIL SEQUENCE REHEARSAL — no socket is opened, no message leaves")
print("=" * 78)
print("schedule: card +0  ·  reminder +%d  ·  card dies +%d  ·  chase +%d (live %dh)"
      % (mystery.WARN_DELAY // 60, mystery.TOKEN_TTL // 60,
         (mystery.TOKEN_TTL + mystery.FOLLOWUP_DELAY) // 60,
         mystery.FOLLOWUP_TTL // 3600))
print("rates   : card %d%%  ·  chase %d%%" % (mystery.OFFER_PCT * 100,
                                              mystery.FOLLOWUP_PCT * 100))

# ── 1. the happy path, minute by minute ───────────────────────────────────
print("\n1. THE SEQUENCE, DRIVEN ON THE CLOCK")
st, payload = issue("player@example.com")
TOK = payload["token"]
T0 = mystery.get(TOK)["at"]
ok(st == 200 and payload.get("ok"), "the card is issued")
ok(len(SENT) == 1 and SENT[0]["kind"] == "bingo_code", "mail 1 goes out at once")

timeline = []
for m in (5, 15, 29, 30, 31, 45, 59, 60, 61, 90, 119, 120, 121, 180, 240):
    at(m)
    _w, _c, new = sweep()
    for msg in new:
        timeline.append((m, msg["kind"], msg["subject"]))

print("     min  mail")
print("     ---  " + "-" * 62)
print("     %-4s %-14s %s" % (0, "bingo_code", SENT[0]["subject"]))
for m, kind, subj in timeline:
    print("     %-4s %-14s %s" % ("+%d" % m, kind, subj))

kinds = [k for _m, k, _s in timeline]
mins = [m for m, _k, _s in timeline]
ok(kinds == ["bingo_warn", "bingo_chase"],
   "exactly two more mails, in order: reminder then chase")
ok(mins[0] == mystery.WARN_DELAY // 60,
   "the reminder lands at +%d min" % (mystery.WARN_DELAY // 60))
ok(mins[1] == (mystery.TOKEN_TTL + mystery.FOLLOWUP_DELAY) // 60,
   "the chase lands at +%d min" % ((mystery.TOKEN_TTL + mystery.FOLLOWUP_DELAY) // 60))
ok(len(SENT) == 3, "three mails total across four hours of sweeps, never more")

# ── 2. what each one says ─────────────────────────────────────────────────
print("\n2. WHAT EACH MAIL SAYS")
code, warn, chase = SENT[0], SENT[1], SENT[2]
for label, m in (("1 code", code), ("2 reminder", warn), ("3 chase", chase)):
    print("     [%s] %s" % (label, m["subject"]))
ok(TOK in code["text"] and TOK in warn["text"] and TOK in chase["text"],
   "all three carry the same working code — revived, never reissued")
ok("30%" in code["subject"] and "30%" in warn["subject"],
   "the first two quote 30%")
ok("35%" in chase["subject"], "and only the chase quotes 35%")
ok("halfway" not in warn["text"].lower(), "the reminder never says 'halfway'")
ok("/checkout?bingo=" + TOK in warn["text"]
   and "/checkout?bingo=" + TOK in chase["text"],
   "both carry a direct checkout link with the token")
ok("unsubscribe?token=" + TOK in warn["text"]
   and "unsubscribe?token=" + TOK in chase["text"],
   "and a one-click unsubscribe")
row = mystery.get(TOK)
ok(row["pct"] == mystery.FOLLOWUP_PCT and row["stage"] == "followup",
   "the row ends chased, at the follow-up rate")

# ── 3. the guards ─────────────────────────────────────────────────────────
print("\n3. THE GUARDS")

# a buyer is never chased
at(0)
st, p = issue("buyer@example.com")
age(p["token"], 200)
orders.append([orders.clean_order({"order_id": "ESB-BUY01", "email": "buyer@example.com",
                                   "amount": 91, "currency": "usd",
                                   "game": "League of Legends", "status": "paid"})])
n = len(SENT)
at(200)
sweep()
ok(len(SENT) == n, "a customer who bought is never chased  <-- the Leo bug")
ok(mystery.get(p["token"]).get("nomail") == 1, "and the row is retired")

# an unsubscribe sticks, even through a re-capture
st, p2 = issue("quiet@example.com")
mystery.unsubscribe(p2["token"])
issue("quiet@example.com")
age(p2["token"], 200)
n = len(SENT)
sweep()
ok(len(SENT) == n, "an unsubscribed visitor is never mailed again")
ok(mystery.get(p2["token"])["nomail"] == 1, "and a re-capture does not undo it")

# a re-capture cannot reset a chased card
st, p3 = issue("recap@example.com")
age(p3["token"], 200)
sweep()                                        # chase it
before = mystery.get(p3["token"])
issue("recap@example.com", **{"to": "Diamond IV"})
after = mystery.get(p3["token"])
ok(after["stage"] == "followup" and after["pct"] == before["pct"],
   "a re-capture cannot reset a chased card  <-- the 1425-minute bug")
ok(after["to"] == "Diamond IV", "but the configuration still tracks the live order")
n = len(SENT)
sweep()
ok(len(SENT) == n, "and it is not chased a second time")

# a paid card is not chased
st, p4 = issue("paid@example.com")
mystery.redeem(p4["token"], order_id="ESB-PAID1")
age(p4["token"], 200)
n = len(SENT)
sweep()
ok(len(SENT) == n, "a redeemed card is never chased")

# ── 4. the outbox ─────────────────────────────────────────────────────────
print("\n4. THE OUTBOX")
s = maillog.summary(days=30)
ok(s["total"] == len(SENT), "every message sent is in the outbox (%d)" % s["total"])
ok(all(r["text"] for r in s["recent"]), "each row carries its body")
ok(sorted(k["kind"] for k in s["kinds"]) == ["bingo_chase", "bingo_code", "bingo_warn"],
   "grouped by kind for the console")
print("     %-28s %s" % ("kind", "count"))
for k in s["kinds"]:
    print("     %-28s %d" % (k["label"], k["count"]))

print("\n" + "=" * 78)
if FAILS:
    print("FAILED: %d" % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED — %d mails, %d in the outbox" % (len(SENT), s["total"]))
