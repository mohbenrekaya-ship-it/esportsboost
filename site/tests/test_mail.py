#!/usr/bin/env python3
"""Outbound-mail tests — stdlib only, no framework, no network.

Run:  python3 site/tests/test_mail.py        (exits non-zero on any failure)

`/api/support` is a public, unauthenticated endpoint that composes a message
and sends it to our own inbox, so the things worth locking down here are the
ones that turn a contact form into someone else's tool:

  * **header injection** — a CR/LF in a subject or a Reply-To is a free Bcc.
  * **From is always us** — never the visitor, or the mail fails our own SPF
    and the domain's reputation goes with it.
  * **the topic is resolved server-side** — the subject line can only ever be
    one of the five topics the page offers, whatever the client sends.
  * **the honeypot and the rate cap answer** — and the honeypot's answer is a
    success, so a bot never learns which field gave it away.
  * **an unconfigured mailbox degrades**, it does not pretend or 500.

Nothing here opens a socket: `mailer.send` is stubbed, and `mailer.build` is
asserted on directly — which is why it exists as its own function.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

import mailer             # noqa: E402
import support            # noqa: E402

_fails = []


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


# ── a configured mailbox, without a mail server ───────────────────────────
SENT = []


def _fake_send(to, subject, text, html=None, reply_to="", sender_name=""):
    SENT.append({"to": to, "subject": subject, "text": text,
                 "html": html, "reply_to": reply_to})
    return True, ""


def configure(**over):
    """Point the module at a mailbox that does not exist. Nothing in these
    tests connects, so the password is a placeholder by construction."""
    env = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "info@esportsboost.com",
           "SMTP_PASSWORD": "not-a-real-password", "MAIL_FROM": "info@esportsboost.com",
           "SUPPORT_EMAIL": "info@esportsboost.com", "SMTP_PORT": "465"}
    env.update(over)
    os.environ.update(env)


def unconfigure():
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM",
              "SUPPORT_EMAIL", "SMTP_PORT"):
        os.environ.pop(k, None)


def post(body, client="203.0.113.7"):
    """Drive process_ticket the way a request would, with a fixed client so the
    rate cap is per test rather than shared."""
    import json
    headers = {"x-forwarded-for": client}
    return support.process_ticket(json.dumps(body).encode(),
                                  lambda k, d="": headers.get(k.lower(), d))


# ══════════════════════════════════════════════════════════════════════════
def test_header_injection():
    """A newline in anything a stranger typed must not reach a header."""
    configure()
    msg = mailer.build(
        "info@esportsboost.com",
        "Refund\r\nBcc: victim@example.com",
        "body",
        reply_to="attacker@example.com\r\nBcc: victim@example.com")
    check(msg is not None, "a message is built")
    check("\n" not in msg["Subject"] and "\r" not in msg["Subject"],
          "subject carries no CR/LF")
    check("Bcc" not in str(msg.keys()), "no Bcc header was smuggled in")
    check(msg["Reply-To"] is None,
          "a Reply-To carrying a header break is dropped, not passed through")
    # …and the clean version of the same address is kept.
    ok = mailer.build("info@esportsboost.com", "Refund", "b",
                      reply_to="buyer@example.com")
    check(ok["Reply-To"] == "buyer@example.com", "a clean Reply-To survives")


def test_from_is_always_us():
    configure()
    msg = mailer.build("info@esportsboost.com", "s", "b",
                       reply_to="stranger@example.com")
    check("info@esportsboost.com" in msg["From"],
          "From is our own mailbox, never the visitor's")
    check("stranger@example.com" not in msg["From"],
          "the visitor's address never reaches From")


def test_recipients_are_validated():
    configure()
    check(mailer.build("not-an-address", "s", "b") is None,
          "a junk recipient builds nothing rather than sending somewhere odd")
    msg = mailer.build(["a@example.com", "bad", "a@example.com", "b@example.com"], "s", "b")
    check(msg["To"] == "a@example.com, b@example.com",
          "recipients are de-duped and the junk one is dropped")


def test_topic_is_server_resolved():
    """The client sends an index; the label comes from data.py's own list."""
    check(support.topic_label(0) == "Order issue", "index 0 is the first topic")
    check(support.topic_label(99) == "Something else", "out of range falls to the last")
    check(support.topic_label("<script>") == "Something else",
          "a string topic cannot become the subject line")


def test_subject_carries_a_real_order_id_only():
    t = support.clean_ticket({"email": "buyer@example.com", "message": "where is it",
                              "order": "ESB-3F92K1", "topic": 0})
    subject, text = support.compose(t)
    check(subject == "[Support] Order issue · ESB-3F92K1", "a real order id tags the subject")

    t2 = support.clean_ticket({"email": "buyer@example.com", "message": "where is it",
                               "order": "not an order", "topic": 0})
    subject2, text2 = support.compose(t2)
    check("not an order" not in subject2.lower() or "NOT AN ORDER" not in subject2,
          "a malformed order id stays out of the subject")
    check("NOT AN ORDER" in text2 and "not a valid order id" in text2,
          "…but is shown in the body, flagged, for the human reading it")


def test_validation():
    configure()
    check(post({"email": "nope", "message": "hello there"})[0] == 400,
          "a junk address is refused")
    check(post({"email": "a@b.com", "message": "hi"})[0] == 400,
          "an empty-ish message is refused")
    status, payload = post({"email": "a@b.com", "message": "  "})
    check(payload.get("error") == "message", "…and the failing field is named")


def test_honeypot_is_silent():
    configure()
    SENT[:] = []
    support.mailer.send, real = _fake_send, support.mailer.send
    try:
        status, payload = post({"email": "bot@example.com", "message": "buy pills",
                                "hp": "Acme Inc"}, client="198.51.100.1")
    finally:
        support.mailer.send = real
    check(status == 200 and payload.get("sent") is True,
          "a filled honeypot is answered like a success")
    check(SENT == [], "…and nothing was sent")


def test_sends_with_reply_to_and_rate_caps():
    configure()
    SENT[:] = []
    support.mailer.send, real = _fake_send, support.mailer.send
    try:
        statuses = [post({"email": "buyer@example.com", "message": "my order is late",
                          "topic": 0, "order": "ESB-3F92K1"}, client="198.51.100.9")[0]
                    for _ in range(support.MAX_TICKETS + 1)]
    finally:
        support.mailer.send = real
    check(statuses[:support.MAX_TICKETS] == [200] * support.MAX_TICKETS,
          "the first %d tickets send" % support.MAX_TICKETS)
    check(statuses[-1] == 429, "the one past the cap is throttled")
    check(len(SENT) == support.MAX_TICKETS, "…and no mail left for it")
    first = SENT[0]
    check(first["to"] == "info@esportsboost.com", "the ticket goes to the support mailbox")
    check(first["reply_to"] == "buyer@example.com",
          "the visitor is the Reply-To, so replying in the inbox answers them")
    check(first["html"] is None, "a ticket is plain text — a stranger's words, never HTML")
    check("my order is late" in first["text"], "the message rides in the body")


def test_unconfigured_degrades():
    unconfigure()
    check(not mailer.configured(), "no mailbox → not configured")
    status, payload = post({"email": "buyer@example.com", "message": "a real question"},
                           client="198.51.100.44")
    check(status == 503 and payload.get("error") == "mail_not_configured",
          "the page is told to fall back rather than shown a fake confirmation")
    ok, err = mailer.send("a@example.com", "s", "b")
    check(ok is False and err == "mail_not_configured",
          "send() refuses without a mailbox instead of raising")


def test_order_mail():
    """The webhook's two messages: the buyer's receipt and the operator's copy."""
    configure()
    import payments
    SENT[:] = []
    real = mailer.send
    mailer.send = _fake_send
    try:
        payments._send_order_mail(
            {"order_id": "ESB-7K21A0", "amount_total": 5700,
             "email": "buyer@example.com"},
            {"game": "League of Legends", "detail": "Gold IV → Platinum II · Solo",
             "region": "EUW", "eta": "3–4 days", "currency": "eur",
             "notes": "<b>evenings only</b>"},
            {"customer_details": {"email": "buyer@example.com"}})
    finally:
        mailer.send = real
    check(len(SENT) == 2, "two messages leave on a paid order")
    buyer, op = SENT[0], SENT[1]
    check(buyer["to"] == "buyer@example.com", "the buyer gets their confirmation")
    check("ESB-7K21A0" in buyer["subject"], "the order id is in the subject")
    check("€57.00" in buyer["text"], "the amount is the one Stripe charged, in its currency")
    check("&lt;b&gt;evenings only&lt;/b&gt;" in buyer["html"],
          "customer-supplied notes are escaped in the HTML part")
    check("/demo.html" not in buyer["text"] and "?order=" not in buyer["text"],
          "no tracking link — that page does not exist yet")
    check(op["to"] == "info@esportsboost.com", "the operator gets a copy")
    check(op["reply_to"] == "buyer@example.com",
          "replying to the operator copy answers the customer")


def main():
    for fn in (test_header_injection, test_from_is_always_us,
               test_recipients_are_validated, test_topic_is_server_resolved,
               test_subject_carries_a_real_order_id_only, test_validation,
               test_honeypot_is_silent, test_sends_with_reply_to_and_rate_caps,
               test_unconfigured_degrades, test_order_mail):
        print("\n" + fn.__name__)
        fn()
    print("\n" + ("=" * 52))
    if _fails:
        print("FAILED: %d check(s)" % len(_fails))
        for m in _fails:
            print("  - " + m)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
