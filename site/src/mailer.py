# -*- coding: utf-8 -*-
"""The one SMTP seam — outbound mail for the whole site, stdlib only.

Two flows send mail and they both come through here:

    /api/support  →  support.py   →  a ticket lands in the support inbox
    /api/webhook  →  payments.py  →  the buyer gets an order confirmation,
                                     the support inbox gets a copy

This module is **transport only**. It knows how to reach the mailbox and how to
put a well-formed message on the wire; it composes nothing. Each caller writes
its own message, exactly the way analytics' Upstash transport is shared while
its data never is — see accounts.py / guides.py for the same split.

Configuration is env-only, never committed (see DEPLOY.md):

    SMTP_HOST       default smtp.hostinger.com — the mailbox this site was
                    built around. Set it for any other provider.
    SMTP_PORT       default 465 (implicit TLS). 587 switches to STARTTLS.
    SMTP_USER       the full mailbox address, e.g. info@esportsboost.com
    SMTP_PASSWORD   that mailbox's password
    MAIL_FROM       envelope + From address, default SMTP_USER
    MAIL_FROM_NAME  display name on From, default "eSports Boost"
    SUPPORT_EMAIL   where tickets and order copies land, default MAIL_FROM
    SMTP_TIMEOUT    socket timeout in seconds, default 12
    SMTP_INSECURE=1 allow an unencrypted local relay (dev only, never in prod)

Three rules here are load-bearing:

  * **Nothing is ever sent From: the visitor.** A message claiming to come from
    a stranger's address fails our own SPF/DMARC and burns the domain's
    reputation — the whole point of owning info@. The visitor's address goes in
    **Reply-To**, so hitting reply in the inbox still answers them.
  * **Every header is sanitised.** Subjects and Reply-To carry text a stranger
    typed into a public form; a bare CR/LF in either is header injection — a
    free Bcc to anywhere. `_header()` strips them, and an address that does not
    survive `_ADDR_RE` is dropped rather than passed through.
  * **`send()` never raises.** It returns `(ok, error)` and its callers decide.
    A support ticket answers the visitor honestly; the order webhook logs and
    still returns 200, because a non-200 makes Stripe retry the whole event and
    we would fulfil twice to send one email.

With nothing configured, `configured()` is False and every caller degrades the
way the Stripe seam does — the form falls back to its preview confirmation
rather than claiming a mail went out.
"""
import os
import re
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

# The mailbox this site was built around. Only ever reached when SMTP_USER and
# SMTP_PASSWORD are set, so a wrong default can't send anything anywhere.
DEFAULT_HOST = "smtp.hostinger.com"
DEFAULT_PORT = 465                  # implicit TLS; 587 means STARTTLS
DEFAULT_FROM_NAME = "eSports Boost"
DEFAULT_TIMEOUT = 12                # seconds — the webhook is on a clock

MAX_SUBJECT = 200
MAX_BODY = 64 * 1024                # a plain-text mail; cap it hard

# Loose shape check, the same one the ingest modules use — reject the obvious
# junk, never an MX lookup.
_ADDR_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,128}\.[A-Za-z]{2,24}$")
# CR, LF and every other control character. Header injection is the reason.
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ── configuration ─────────────────────────────────────────────────────────
def _env(name, default=""):
    return (os.environ.get(name) or "").strip() or default


def host():
    return _env("SMTP_HOST", DEFAULT_HOST)


def port():
    try:
        return int(_env("SMTP_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


def user():
    return _env("SMTP_USER")


def password():
    # Read, never logged, never returned to any caller.
    return os.environ.get("SMTP_PASSWORD") or ""


def from_addr():
    """The address every message is sent as. Must be a mailbox on our own
    domain or the mail fails SPF/DMARC — see the module note."""
    return _env("MAIL_FROM", user())


def from_name():
    return _env("MAIL_FROM_NAME", DEFAULT_FROM_NAME)


def support_addr():
    """Where tickets and order copies land. Same mailbox as MAIL_FROM unless
    the operator splits them (info@ sends, support@ receives)."""
    return _env("SUPPORT_EMAIL", from_addr())


def timeout():
    try:
        return max(2, min(30, int(_env("SMTP_TIMEOUT", str(DEFAULT_TIMEOUT)))))
    except ValueError:
        return DEFAULT_TIMEOUT


def configured():
    """True when there is a mailbox to send through. Every caller checks this
    first and degrades honestly rather than pretending a mail went out."""
    return bool(host() and user() and password() and valid(from_addr()))


def status():
    """A one-line description for the server banner and the ops console. Never
    includes the password, and never the whole address — the mailbox name and
    host are enough to tell a misconfiguration from a working one."""
    if not configured():
        missing = [n for n, v in (("SMTP_USER", user()), ("SMTP_PASSWORD", password()),
                                  ("SMTP_HOST", host())) if not v]
        return "OFF (set %s)" % ", ".join(missing or ["MAIL_FROM to a valid address"])
    return "%s via %s:%d" % (from_addr(), host(), port())


# ── header hygiene ────────────────────────────────────────────────────────
def valid(addr):
    return bool(_ADDR_RE.match((addr or "").strip()))


def _header(value, cap=MAX_SUBJECT):
    """One header value, safe to write: control characters (CR/LF above all)
    removed, whitespace collapsed, length capped. This is the header-injection
    guard — everything a stranger typed passes through it."""
    v = _CTRL_RE.sub(" ", str(value if value is not None else ""))
    return " ".join(v.split())[:cap]


def _addr(value):
    """A single address, or "" if it is not one. `parseaddr` first so a value
    like `Name <a@b.com>` is reduced to the mailbox before it is checked — a
    display name is another place a newline could hide."""
    _name, mail = parseaddr(_header(value, 320))
    mail = mail.strip()
    return mail if valid(mail) else ""


def _addr_list(value):
    """Recipients: one address or a list of them, junk dropped, order kept."""
    if not value:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    out = []
    for item in items:
        a = _addr(item)
        if a and a not in out:
            out.append(a)
    return out


# ── send ──────────────────────────────────────────────────────────────────
def build(to, subject, text, html=None, reply_to="", sender_name=""):
    """Compose one message. Split out from `send()` so the tests can assert on
    the headers without opening a socket."""
    to_list = _addr_list(to)
    sender = from_addr()
    if not to_list or not valid(sender):
        return None

    msg = EmailMessage()
    msg["From"] = formataddr((_header(sender_name or from_name(), 80), sender))
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = _header(subject) or "(no subject)"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@", 1)[-1] or None)
    reply = _addr(reply_to)
    if reply:
        # The visitor's own address. This is what makes "reply" in the inbox
        # answer the person who wrote in, while From stays our domain.
        msg["Reply-To"] = reply
    msg["Auto-Submitted"] = "auto-generated"     # keeps us out of vacation loops
    # Quoted-printable rather than 8-bit: the copy is full of em dashes, arrows
    # and "·", and a relay that does not advertise 8BITMIME is entitled to
    # mangle raw 8-bit bytes. QP is 7-bit clean and every client decodes it.
    msg.set_content(str(text or "")[:MAX_BODY], cte="quoted-printable")
    if html:
        msg.add_alternative(str(html)[:MAX_BODY], subtype="html")
    return msg


def send(to, subject, text, html=None, reply_to="", sender_name=""):
    """Send one message. Returns `(ok, error)` and **never raises** — the two
    callers both have something better to do with a failure than 500.

    `to` may be one address or a list. `reply_to` is where a human reply should
    go (the visitor, on a support ticket); From is always our own mailbox.
    """
    if not configured():
        return False, "mail_not_configured"
    msg = build(to, subject, text, html, reply_to, sender_name)
    if msg is None:
        return False, "no_recipient"

    ctx = ssl.create_default_context()
    started = time.time()
    try:
        if port() == 465:
            with smtplib.SMTP_SSL(host(), port(), timeout=timeout(), context=ctx) as s:
                s.login(user(), password())
                s.send_message(msg)
        else:
            with smtplib.SMTP(host(), port(), timeout=timeout()) as s:
                s.ehlo()
                if s.has_extn("starttls"):
                    s.starttls(context=ctx)
                    s.ehlo()
                elif _env("SMTP_INSECURE") != "1":
                    # A relay that cannot encrypt is a relay we do not hand a
                    # password to. Local test relays opt in explicitly.
                    return False, "starttls_unavailable"
                s.login(user(), password())
                s.send_message(msg)
    except (smtplib.SMTPException, ssl.SSLError, OSError) as e:
        # The address is deliberately not logged — the ticket body is the
        # visitor's, and this line ends up in a hosting provider's log viewer.
        sys.stderr.write("[mail] send failed after %.1fs: %s: %s\n"
                         % (time.time() - started, type(e).__name__, e))
        return False, "send_failed"
    return True, ""
