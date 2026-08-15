# -*- coding: utf-8 -*-
"""The support form's endpoint — `POST /api/support` — behind /support.html.

The page has always had the form; until now it was a facade whose confirmation
said so out loud. This is the wire: a validated ticket, composed as plain text
and handed to `mailer.send()`, landing in the support mailbox with the visitor
in **Reply-To** so hitting reply in the inbox answers them.

It is a sibling of `accounts.py` / `guides.py` — same house rules (stdlib only,
no build step, no third-party packages) and the same public-write shape — with
one difference that shapes the whole module: **it stores nothing.** A ticket is
a message to a human, not a list to aggregate, so there is no store, no `/ops`
tab and no row anywhere. What the visitor typed exists in the mailbox and
nowhere else.

Load-bearing rules:

  * **`/api/support` is public and unauthenticated**, like `/api/collect` and
    `/api/guides`: the form is on a public page. Which makes it a mail relay
    pointed at our own inbox, so it is defended three ways — every field is
    length-capped and validated here, a hidden honeypot field drops bots
    without telling them, and the route is rate limited per client.
  * **Nothing the visitor types reaches a header unsanitised.** `mailer` strips
    control characters from every header it writes, and the order id only
    reaches the subject line when it matches the real order-id shape.
  * **The topic is resolved server-side**, by index, against `D.SUPPORT`. The
    browser sends `topic: 2`, never a string — so the subject line can only
    ever be one of the five topics the page actually offers.
  * **The body is plain text, deliberately.** A ticket carries a stranger's
    words; sending them as HTML means escaping them correctly forever. Text has
    no such failure mode, and an inbox renders it fine.
  * **Nothing is sent to the visitor.** The only recipient is our own mailbox.
    An acknowledgement mail would make this endpoint a way to send stranger-
    written text to any address on the internet, which is a spam relay with
    extra steps. The page confirms on screen instead, instantly, and the reply
    comes from a person.
  * **Restart the server after touching this file** — `/api/support` lives in
    `serve.py`, and there is no watcher.
"""
import hashlib
import json
import os
import re
import time

import analytics                # Upstash transport for the throttle counter
import data as D                # the topic list the subject is resolved against
import geo
import mailer

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 16 * 1024
MAX_EMAIL = 160
MAX_ORDER = 40
MAX_MESSAGE = 4000              # the textarea's ceiling; longer is truncated
MIN_MESSAGE = 4                 # matches the client's own check

# One client may open a handful of tickets in a window and no more. A person
# with a real problem writes once, maybe twice; anything past this is a script.
MAX_TICKETS = 5
TICKET_WINDOW = 900             # 15 minutes, same window accounts.py uses

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,128}\.[A-Za-z]{2,24}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# The real order-id shape, the same one orders.py enforces. Only a value that
# matches reaches the subject line; anything else rides in the body as typed.
_ORDER_RE = re.compile(r"^ESB-[A-Z0-9]{3,12}$")

# In-process fallback counter for the throttle, used when there is no Upstash —
# under serve.py, which is one long-running process. Mirrors accounts.py.
_MEM_HITS = {}
_MEM_MAX = 4096


def _s(v, n):
    """Trim to a string, strip control chars, cap length."""
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _text(v, n):
    """Same, but keeps the newlines — this is the message body, not a header."""
    v = str(v if v is not None else "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v).strip()[:n]


# ══════════════════════════════════════════════════════════════════════════
#  throttle — per client, mirroring accounts.py's counter
# ══════════════════════════════════════════════════════════════════════════
def _key(client):
    """One counter per client, hashed so no address is written into a key."""
    return "esb:sup:hits:" + hashlib.sha256(
        ("support|%s" % client).encode()).hexdigest()[:32]


def _too_many(key, now=None):
    now = int(now or time.time())
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["GET", key]])
            return int(res[0] or 0) >= MAX_TICKETS
        except (analytics.StoreError, TypeError, ValueError, IndexError):
            return False              # a store hiccup must not silence the form
    hit = _MEM_HITS.get(key)
    if not hit:
        return False
    count, start = hit
    if now - start > TICKET_WINDOW:
        _MEM_HITS.pop(key, None)
        return False
    return count >= MAX_TICKETS


def _note(key, now=None):
    now = int(now or time.time())
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["INCR", key], ["EXPIRE", key, TICKET_WINDOW]])
        except analytics.StoreError:
            pass
        return
    count, start = _MEM_HITS.get(key, (0, now))
    if now - start > TICKET_WINDOW:
        count, start = 0, now
    _MEM_HITS[key] = (count + 1, start)
    if len(_MEM_HITS) > _MEM_MAX:
        cutoff = now - TICKET_WINDOW
        for k, v in list(_MEM_HITS.items()):
            if v[1] < cutoff:
                _MEM_HITS.pop(k, None)


# ══════════════════════════════════════════════════════════════════════════
#  the ticket
# ══════════════════════════════════════════════════════════════════════════
def topic_label(index):
    """Resolve the topic chip's index against the page's own list. Out of range
    answers the last topic ("Something else"), never the client's own string."""
    topics = getattr(D, "SUPPORT", {}).get("topics") or []
    if not topics:
        return "Support"
    try:
        i = int(index)
    except (TypeError, ValueError):
        i = -1
    if not 0 <= i < len(topics):
        i = len(topics) - 1
    return str(topics[i][0])


def clean_ticket(body):
    """Validate one submission into the fields a ticket is composed from, or an
    `{"error": …}` dict naming the field that failed.

    Returns `{"email", "order", "topic", "message"}` — nothing is stored, so
    these exist only long enough to be written into a mail.
    """
    if not isinstance(body, dict):
        return {"error": "email"}
    email = _s(body.get("email"), MAX_EMAIL).lower()
    if not _EMAIL_RE.match(email):
        return {"error": "email"}
    message = _text(body.get("message"), MAX_MESSAGE)
    if len(message) < MIN_MESSAGE:
        return {"error": "message"}
    return {
        "email": email,
        "order": _s(body.get("order"), MAX_ORDER).upper(),
        "topic": topic_label(body.get("topic")),
        "message": message,
    }


def compose(ticket, ctx=None):
    """Turn a cleaned ticket into `(subject, text)`.

    The subject carries the topic and — only when it matches the real order-id
    shape — the order number, because that is what makes an inbox sortable. The
    body leads with the facts support needs before it quotes the visitor.
    """
    ctx = ctx or {}
    order = ticket.get("order", "")
    tagged = order if _ORDER_RE.match(order or "") else ""
    subject = "[Support] %s%s" % (ticket["topic"], " · %s" % tagged if tagged else "")

    lines = ["From:    %s" % ticket["email"],
             "Topic:   %s" % ticket["topic"]]
    if order:
        # An id that did not match the shape is still shown — a buyer mistyping
        # their own order number is exactly the ticket a human should see.
        lines.append("Order:   %s%s" % (order, "" if tagged else "  (not a valid order id)"))
    if ctx.get("co"):
        lines.append("Country: %s (%s)" % (ctx["co"], ctx.get("cosrc", "?")))
    lines.append("Sent:    %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
    lines += ["", "-" * 56, "", ticket["message"], "", "-" * 56, "",
              "Reply to this mail and it goes straight back to the sender."]
    return subject, "\n".join(lines)


def process_ticket(raw, header_get):
    """POST /api/support → (status, payload).

    Body: `{"email", "message", "topic"?, "order"?, "hp"?, "tz"?, "lang"?}`.
    `hp` is the honeypot — a field no human ever fills.

    Responses:
      · sent → `(200, {"sent": True})`
      · mail not configured → `(503, {"error": "mail_not_configured"})`, and the
        page falls back to its preview confirmation, the same contract the
        Stripe seam has.
      · bad address / empty message → `(400, {"error": "email"|"message"})`
      · too many from this client → `(429, {"error": "throttled"})`
      · SMTP refused it → `(502, {"error": "send_failed"})`, and the page tells
        the visitor to write to the address directly rather than swallowing it.
      · honeypot filled → `(200, {"sent": True})`. A bot is told nothing.
      · unparseable / oversized body → `(204, None)`
    """
    if not raw or len(raw) > MAX_BODY:
        return 204, None
    try:
        body = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return 204, None
    if not isinstance(body, dict):
        return 204, None

    # The honeypot is answered exactly like a success: a bot that learns which
    # field gave it away just stops filling that field.
    if _s(body.get("hp"), 80):
        return 200, {"sent": True}

    get = header_get or (lambda *_a, **_k: "")
    client = _s((get("x-forwarded-for") or "").split(",")[0].strip()
                or get("x-real-ip") or "", 64)
    key = _key(client)
    if _too_many(key):
        return 429, {"error": "throttled"}

    ticket = clean_ticket(body)
    if ticket.get("error"):
        _note(key)                    # a scripted probe pays for its failures
        return 400, {"error": ticket["error"]}

    if not mailer.configured():
        # Nothing is dropped silently: the page's fallback confirmation says
        # plainly that nothing was emailed, and names the address to write to.
        return 503, {"error": "mail_not_configured"}

    edge = _s(get("x-vercel-ip-country") or "", 2).upper()
    tz, lang = _s(body.get("tz"), 64), _s(body.get("lang"), 12)
    ctx = {"co": geo.country(edge, tz, lang), "cosrc": geo.source(edge, tz, lang)}

    subject, text = compose(ticket, ctx)
    ok, err = mailer.send(mailer.support_addr(), subject, text,
                          reply_to=ticket["email"])
    _note(key)                        # successes count too — this is a rate cap
    if not ok:
        return 502, {"error": err or "send_failed"}
    return 200, {"sent": True}
