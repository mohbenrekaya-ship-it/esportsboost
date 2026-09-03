# -*- coding: utf-8 -*-
"""The outbox — every message the site actually sent, with its full content.

The **eighth sibling** of `analytics.py`, `accounts.py`, `boosters.py`,
`orders.py`, `carts.py`, `guides.py` and `mystery.py`: same house rules (stdlib
only, no build step, Upstash Redis in prod / an NDJSON file in dev), a
**separate store** (`esb:maillog` / `maillog.ndjson`), reusing only analytics'
Upstash *transport*.

Why it exists: the site now sends six different kinds of mail from four modules
on a five-minute cron, and until this existed there was **no way to answer "what
did we actually send that person, and when"** except by asking them to forward
it. That is not a reporting gap, it is an operational one — a customer wrote in
asking why he was chased about an order he had not placed, and the only honest
answer available was a shrug.

Two properties make it trustworthy, and both are the point:

  * **It is written inside `mailer.send()`**, the one SMTP seam on the site, so
    a message cannot be sent without being recorded. Not by the recovery mailer,
    not by the follow-up, not by a new caller somebody adds next month. If it
    left the server, it is in here.
  * **It records the OUTCOME, not the intention.** `ok` is whatever the SMTP
    conversation returned, so a refused or timed-out message is in the log as a
    failure rather than being silently absent.

⚠ It holds the most sensitive data on the site: a recipient's address next to
the full body of what was sent to them, including their order and a live
discount code. Same treatment as accounts / carts / mystery — the `/ops` payload
is fetched on demand, never bundled into a dashboard refresh — plus a retention
cap, because an outbox that grows forever is a breach waiting for somewhere to
happen. Give it the same lawful basis, privacy-policy line and deletion path as
the other PII stores before launch.

It is append-only: a sent message is a historical fact and nothing may edit it.
So the Upstash side is a LIST (`LPUSH` + `LTRIM`), the shape `guides.py` uses,
not the HASH that `carts.py` and `mystery.py` need for mutable rows.
"""
import json
import os
import re
import time

import analytics   # Upstash transport + store selection only — never its data

LIST_KEY = "esb:maillog"

# Retention. An outbox is the highest-value target on the site, so it keeps the
# last N messages and forgets the rest rather than accumulating for ever.
MAX_ROWS = int(os.environ.get("MAILLOG_MAX", "2000") or 2000)
# Bodies are capped, not dropped: the point of the log is being able to read
# what somebody actually received. The text part is what /ops shows by default;
# the HTML is kept so the exact rendering can be reproduced.
MAX_TEXT = int(os.environ.get("MAILLOG_MAX_TEXT", "8000") or 8000)
MAX_HTML = int(os.environ.get("MAILLOG_MAX_HTML", "40000") or 40000)
MAX_STR = 300
RECENT_CAP = 400

# What each `kind` means, for the console. A caller passing an unknown kind is
# recorded verbatim rather than dropped — an unlabelled message in the outbox is
# still better than a missing one.
KINDS = {
    "order": "Order confirmation",
    "order_ops": "Order copy to ops",
    "support": "Support ticket",
    "cart_recovery": "Abandoned cart — 30%",
    "bingo_code": "Mystery card — the code",
    "bingo_warn": "Mystery card — reminder",
    "bingo_chase": "Mystery card — 35% last call",
    "application": "Booster application",
    # ⚠ Recorded with its body REDACTED — see mailer._log()'s `redact`. The row
    # proves the handover went out; the credentials themselves live once, in
    # the stock store, where they can be purged per account.
    "account_delivery": "Account handover — credentials",
    "stock_alert": "Stock alert to ops",
    "test": "Test message",
    "": "Other",
}

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def log_path():
    return os.environ.get("MAILLOG_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "maillog.ndjson")


def _s(v, n=MAX_STR):
    return _CTRL_RE.sub("", str(v if v is not None else ""))[:n]


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _up():
    return analytics.upstash_config()[0]


def record(to, subject, text="", html="", kind="", ok=True, error="",
           sender="", now=None):
    """Append one sent message. **Never raises** — a logging failure must not
    turn a delivered mail into an error the caller reports, and must never stop
    the next one being sent."""
    try:
        row = {
            "at": _int(now or time.time()),
            "to": _s(to, 320),
            "from": _s(sender, 320),
            "subject": _s(subject, 400),
            "kind": _s(kind, 32),
            "ok": 1 if ok else 0,
            "error": _s(error, 200),
            "text": _s(text, MAX_TEXT),
            "html": _s(html, MAX_HTML),
        }
        blob = json.dumps(row, separators=(",", ":"))
        if _up():
            analytics._upstash([["LPUSH", LIST_KEY, blob],
                                ["LTRIM", LIST_KEY, 0, MAX_ROWS - 1]])
            return True
        rows = read(MAX_ROWS - 1)
        rows.insert(0, row)
        with open(log_path(), "w") as f:
            for r in rows[:MAX_ROWS]:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        return True
    except Exception:                                          # noqa: BLE001
        return False


def read(limit=MAX_ROWS):
    """Every message, newest first."""
    limit = max(1, min(_int(limit, MAX_ROWS), MAX_ROWS))
    rows = []
    if _up():
        try:
            res = analytics._upstash([["LRANGE", LIST_KEY, 0, limit - 1]])
        except analytics.StoreError:
            return []
        for raw in (res[0] if res else []) or []:
            try:
                rows.append(json.loads(raw))
            except (ValueError, TypeError):
                continue
        return rows
    try:
        with open(log_path()) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    rows.sort(key=lambda r: -_int(r.get("at")))
    return rows[:limit]


def clear():
    if _up():
        try:
            analytics._upstash([["DEL", LIST_KEY]])
            return True
        except analytics.StoreError:
            return False
    try:
        open(log_path(), "w").close()
        return True
    except OSError:
        return False


def count():
    return len(read())


def store_name():
    return "upstash" if _up() else "file"


def summary(days=30, now=None, kind="", limit=RECENT_CAP):
    """The Outbox tab's payload: what went out, to whom, when, and the body.

    Fetched on demand like Accounts, Carts and Mystery — it is the most
    sensitive payload on the console and must never ride a dashboard refresh."""
    days = max(1, min(_int(days, 30), 365))
    now = _int(now or time.time())
    cutoff = now - days * 86400
    rows = [r for r in read() if _int(r.get("at")) >= cutoff]
    if kind:
        rows = [r for r in rows if (r.get("kind") or "") == kind]

    by_kind, by_day = {}, {}
    failed = 0
    recipients = set()
    for r in rows:
        k = r.get("kind") or ""
        b = by_kind.setdefault(k, {"kind": k, "label": KINDS.get(k, k or "Other"),
                                   "count": 0, "failed": 0})
        b["count"] += 1
        if not r.get("ok"):
            b["failed"] += 1
            failed += 1
        recipients.add((r.get("to") or "").lower())
        d = time.strftime("%Y-%m-%d", time.gmtime(_int(r.get("at"))))
        by_day[d] = by_day.get(d, 0) + 1

    recent = [{
        "at": _int(r.get("at")), "to": r.get("to", ""), "from": r.get("from", ""),
        "subject": r.get("subject", ""), "kind": r.get("kind", ""),
        "label": KINDS.get(r.get("kind") or "", r.get("kind") or "Other"),
        "ok": 1 if r.get("ok") else 0, "error": r.get("error", ""),
        "text": r.get("text", ""), "html": r.get("html", ""),
    } for r in rows[:limit]]

    return {
        "total": len(rows), "days": days, "failed": failed,
        "recipients": len(recipients),
        "kinds": sorted(by_kind.values(), key=lambda x: -x["count"]),
        "days_series": [{"day": d, "count": c} for d, c in sorted(by_day.items())],
        "recent": recent, "shown": len(recent), "store": store_name(),
        "cap": MAX_ROWS,
    }
