# -*- coding: utf-8 -*-
"""Every address the site has captured, in one view — the /ops "Mail discounts" tab.

**This module owns no store and writes nothing.** It is a read-only join across
the four places an email can already be, plus the orders store to answer the only
question that matters: did this person buy?

    carts.py     an abandoned checkout   → a 30% recovery token, one recovery mail
    mystery.py   a configurator capture  → a 30% card, then a warning, then a 35% chase
    guides.py    the free-guides landing → a mailing-list subscriber, no discount
    accounts.py  the header sign-up      → a lead, no discount
    orders.py    a real fulfilment       → CONVERTED

That it aggregates rather than copies is the load-bearing decision. Every one of
those stores is deliberately separate (see CLAUDE.md — the analytics store is
sworn to hold no PII, and the others hold different consents), and a fifth store
duplicating their emails would be a second copy of the most sensitive data on the
site, immediately out of sync with the four originals and needing its own
deletion path. Reading is free; copying is a liability. **Do not give this module
a store.**

What one row answers, which is what the tab was asked for:

  * **Converted or not.** `orders.for_email()` is the truth — a paid row against
    that address. A burned token (`recovered` / `redeemed`) counts too, because
    that is a payment the webhook attributed to the offer. Anything else is
    `open` while an offer is still live and `lapsed` once nothing is.
  * **Every mail it has been sent**, in order, with when: the mystery code, the
    half-hour warning, the last-chance chase, the cart recovery. This is the
    volume check — one capture can now reach four messages, and this is the only
    place that is visible per person.
  * **What they did about it** — opened a card and which one, pressed Apply,
    ticked the guides opt-in, unsubscribed, paid.

⚠ It reports what the stores hold, which is *sent*, not *delivered* or *opened*.
There is no open- or click-tracking on this site and adding one is a consent
decision, not a feature — so "Mailed 3" means three messages left the server.
"""
import time

import accounts
import carts
import guides
import mystery
import orders

RECENT_CAP = 500

# The lifecycle, most-advanced first. A row is labelled by the furthest state it
# has reached, never by the newest event — somebody who paid and then subscribed
# to the guides is still converted.
STATUSES = ("converted", "open", "lapsed", "unsubscribed")

SOURCES = ("mystery", "cart", "guides", "account", "order")


def _s(v, n=160):
    return str(v if v is not None else "").strip()[:n]


def _int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _mail(kind, at, note=""):
    return {"kind": kind, "at": _int(at), "note": note}


def _blank(email):
    return {
        "email": email, "first_seen": 0, "last_seen": 0,
        "sources": [], "mails": [], "country": "", "cosrc": "",
        "converted": False, "order_id": "", "paid": 0,
        "offer_token": "", "offer_pct": 0.0, "offer_live": False, "offer_expires": 0,
        "applied": 0, "pick": "", "optin": 0, "unsubscribed": False,
        "game": "", "summary": "", "mode": "", "value": 0, "offer_value": 0,
        "syn": 0,
    }


def _touch(row, at):
    at = _int(at)
    if not at:
        return
    row["first_seen"] = at if not row["first_seen"] else min(row["first_seen"], at)
    row["last_seen"] = max(row["last_seen"], at)


def collect(now=None):
    """One dict per address, joined across every store. Newest activity first."""
    now = _int(now or time.time())
    by = {}

    def get(email):
        e = _s(email).lower()
        if not e:
            return None
        if e not in by:
            by[e] = _blank(e)
        return by[e]

    # ── the mystery capture: up to three mails and the richest behaviour ──
    for r in mystery.read():
        row = get(r.get("email"))
        if row is None:
            continue
        row["sources"].append("mystery")
        _touch(row, r.get("at"))
        row["game"] = row["game"] or _s(r.get("game"), 60)
        row["summary"] = row["summary"] or mystery._climb(r)
        row["mode"] = row["mode"] or _s(r.get("mode"), 20)
        row["country"] = row["country"] or _s(r.get("country"), 4)
        row["cosrc"] = row["cosrc"] or _s(r.get("cosrc"), 16)
        row["pick"] = row["pick"] or _s(r.get("pick"), 1)
        row["optin"] = row["optin"] or (1 if r.get("optin") else 0)
        row["syn"] = row["syn"] or (1 if r.get("syn") else 0)
        if r.get("mailed"):
            _mail_add(row, "code", r.get("at"), "%d%% card" % round((r.get("pct") or 0) * 100))
        if r.get("warned"):
            _mail_add(row, "warning", r.get("warned"), "hour running out")
        if r.get("followup_at"):
            _mail_add(row, "chase", r.get("followup_at"),
                      "%d%% last chance" % round((r.get("pct") or 0) * 100))
        if _int(r.get("applied_at")):
            row["applied"] = _int(r.get("applied_at"))
            _touch(row, r.get("applied_at"))
        if r.get("nomail"):
            row["unsubscribed"] = True
        if r.get("status") == "redeemed":
            row["converted"] = True
            row["order_id"] = row["order_id"] or _s(r.get("order_id"), 40)
            _touch(row, r.get("redeemed_at"))
        live = mystery.redeemable(r.get("token", ""), now=now)
        if live:
            row["offer_token"] = r["token"]
            row["offer_pct"] = float(r.get("pct") or 0)
            row["offer_live"] = True
            row["offer_expires"] = _int(r.get("expires"))
        val, off = mystery.price_pair(r)
        row["value"] = row["value"] or val
        row["offer_value"] = row["offer_value"] or off

    # ── the abandoned checkout: one recovery mail ─────────────────────────
    for r in carts.read():
        row = get(r.get("email"))
        if row is None:
            continue
        row["sources"].append("cart")
        _touch(row, r.get("at"))
        row["game"] = row["game"] or _s(r.get("game"), 60)
        row["summary"] = row["summary"] or carts._climb(r)
        row["mode"] = row["mode"] or _s(r.get("mode"), 20)
        row["country"] = row["country"] or _s(r.get("country"), 4)
        row["syn"] = row["syn"] or (1 if r.get("syn") else 0)
        if _int(r.get("mailed_at")):
            _mail_add(row, "recovery", r.get("mailed_at"),
                      "%d%% come back" % round(carts.RECOVERY_PCT * 100))
        if r.get("status") == "recovered":
            row["converted"] = True
            row["order_id"] = row["order_id"] or _s(r.get("order_id"), 40)
            _touch(row, r.get("recovered_at"))
        if r.get("status") == "expired":
            row["unsubscribed"] = True
        if not row["offer_live"] and carts.redeemable(r.get("token", ""), now=now):
            row["offer_token"] = r["token"]
            row["offer_pct"] = carts.RECOVERY_PCT
            row["offer_live"] = True
        normal, offer = carts._display_price(r)
        row["value"] = row["value"] or normal
        row["offer_value"] = row["offer_value"] or offer

    # ── the two lists with no discount attached ───────────────────────────
    for r in guides.read():
        row = get(r.get("email"))
        if row is None:
            continue
        row["sources"].append("guides")
        _touch(row, r.get("ts"))
        row["country"] = row["country"] or _s(r.get("co"), 4)
        row["cosrc"] = row["cosrc"] or _s(r.get("cosrc"), 16)
        row["optin"] = row["optin"] or (1 if r.get("optin") else 0)
        row["syn"] = row["syn"] or (1 if r.get("syn") else 0)

    for r in accounts.read():
        row = get(r.get("email"))
        if row is None:
            continue
        row["sources"].append("account")
        _touch(row, r.get("ts"))
        row["country"] = row["country"] or _s(r.get("co"), 4)
        row["cosrc"] = row["cosrc"] or _s(r.get("cosrc"), 16)
        row["syn"] = row["syn"] or (1 if r.get("syn") else 0)

    # ── conversion, from the one store that actually knows ────────────────
    # A burned token above already says "paid", but only the orders store can
    # tell us about somebody who bought at full price after being mailed — which
    # is exactly the case a discount programme has to be able to see.
    # `by_email`, not a broad try/except around the lookup: wrapping this in
    # `except Exception` once hid an AttributeError for a function name that did
    # not exist, and the whole conversion join was silently dead — every row read
    # "not converted" and revenue read $0. A store that is down should surface,
    # not quietly zero the one number this tab is for.
    for email, row in by.items():
        try:
            paid = [o for o in orders.by_email(email)
                    if o.get("status") != "refunded"]
        except (OSError, ValueError) as e:                     # store unreadable
            import sys
            sys.stderr.write("[maillist] orders lookup failed for one row: %s\n" % e)
            paid = []
        if paid:
            row["converted"] = True
            row["paid"] = sum(_int(o.get("total")) for o in paid)
            row["order_id"] = row["order_id"] or _s(paid[0].get("order_id"), 40)
            for o in paid:
                _touch(row, o.get("at") or o.get("ts"))
            row["sources"].append("order")

    for row in by.values():
        row["sources"] = sorted(set(row["sources"]))
        row["mails"].sort(key=lambda m: m["at"])
        row["mail_count"] = len(row["mails"])
        row["status"] = _status(row)
    return sorted(by.values(), key=lambda r: -r["last_seen"])


def _mail_add(row, kind, at, note=""):
    """Record one send. Deduped on (kind, at) so a re-read of the same store
    never inflates somebody's mail count."""
    m = _mail(kind, at, note)
    if not any(x["kind"] == m["kind"] and x["at"] == m["at"] for x in row["mails"]):
        row["mails"].append(m)


def _status(row):
    if row["converted"]:
        return "converted"
    if row["unsubscribed"]:
        return "unsubscribed"
    return "open" if row["offer_live"] else "lapsed"


def summary(days=30, now=None):
    """The Mail discounts panel's payload."""
    days = max(1, min(_int(days, 30), 365))
    now = _int(now or time.time())
    cutoff = now - days * 86400
    everyone = collect(now=now)
    rows = [r for r in everyone if r["last_seen"] >= cutoff]

    by_status = {s: 0 for s in STATUSES}
    by_source = {s: 0 for s in SOURCES}
    by_country, by_mailkind = {}, {}
    mails = applied = optins = unsub = 0
    revenue = pipeline = 0
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        for s in r["sources"]:
            by_source[s] = by_source.get(s, 0) + 1
        for m in r["mails"]:
            by_mailkind[m["kind"]] = by_mailkind.get(m["kind"], 0) + 1
        mails += r["mail_count"]
        if r["applied"]:
            applied += 1
        if r["optin"]:
            optins += 1
        if r["unsubscribed"]:
            unsub += 1
        revenue += r["paid"]
        if not r["converted"]:
            pipeline += r["offer_value"] or r["value"]
        c = r["country"] or "??"
        by_country[c] = by_country.get(c, 0) + 1

    total = len(rows)
    conv = by_status.get("converted", 0)
    mailed_people = sum(1 for r in rows if r["mail_count"])
    return {
        "total": total, "days": days,
        "converted": conv,
        "conversion_rate": round(100.0 * conv / total, 1) if total else 0.0,
        # Of the people we actually mailed — a lead nobody could contact should
        # not drag the rate of the programme that did contact people.
        "mailed_people": mailed_people,
        "mailed_conversion_rate": round(
            100.0 * sum(1 for r in rows if r["mail_count"] and r["converted"]) / mailed_people, 1
        ) if mailed_people else 0.0,
        "mails_sent": mails,
        "mails_per_person": round(mails / mailed_people, 1) if mailed_people else 0.0,
        "applied": applied, "optins": optins, "unsubscribed": unsub,
        "revenue": revenue, "pipeline": pipeline,
        "synthetic": sum(1 for r in rows if r["syn"]),
        "statuses": [{"status": s, "count": by_status.get(s, 0)} for s in STATUSES],
        "sources": [{"source": s, "count": by_source.get(s, 0)} for s in SOURCES],
        "mailkinds": sorted(({"kind": k, "count": v} for k, v in by_mailkind.items()),
                            key=lambda x: -x["count"]),
        "countries": sorted(({"code": k, "count": v} for k, v in by_country.items()),
                            key=lambda x: (-x["count"], x["code"])),
        "recent": rows[:RECENT_CAP],
        "store": "joined",
    }
