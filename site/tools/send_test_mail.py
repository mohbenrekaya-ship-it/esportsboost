#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send one test message through the configured mailbox, and say what broke.

    python3 site/tools/send_test_mail.py                  # → SUPPORT_EMAIL
    python3 site/tools/send_test_mail.py me@example.com    # → somewhere else
    python3 site/tools/send_test_mail.py --order           # the buyer's receipt

This is the first thing to run after putting SMTP_* in `.env`: it uses the same
`mailer.py` the support form and the order webhook use, so if this lands in the
inbox, both of those will too — and if it doesn't, the failure here is the same
failure they would have hit silently.

`--order` renders the real order-confirmation mail against a sample order, which
is how you look at the template without paying for a boost.

A developer script: never part of a build or a deploy, like everything else in
site/tools/.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

# The same .env loader serve.py uses, so this behaves like the running server.
for path in (os.path.join(os.path.dirname(ROOT), ".env"), os.path.join(ROOT, ".env")):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

import mailer     # noqa: E402
import payments   # noqa: E402

HINTS = {
    "mail_not_configured":
        "Set SMTP_USER and SMTP_PASSWORD in .env (SMTP_HOST defaults to\n"
        "     smtp.hostinger.com). MAIL_FROM must be a real mailbox on the domain.",
    "starttls_unavailable":
        "The server offered no STARTTLS on this port. Use port 465, which is\n"
        "     implicit TLS, or check SMTP_HOST.",
    "send_failed":
        "The line above says why. The usual three:\n"
        "     · 535 authentication failed → wrong mailbox password, or SMTP_USER\n"
        "       is not the FULL address (info@esportsboost.com, not 'info')\n"
        "     · timeout → wrong host/port, or the network blocks outbound SMTP\n"
        "     · 550 relay denied → MAIL_FROM is not a mailbox on this account",
}


def main():
    args = [a for a in sys.argv[1:] if a != "--order"]
    as_order = "--order" in sys.argv[1:]

    print("mailbox : %s" % mailer.status())
    if not mailer.configured():
        print("\nNothing to send through.\n  → %s" % HINTS["mail_not_configured"])
        return 1
    to = args[0] if args else mailer.support_addr()
    print("sending : %s → %s%s" % (mailer.from_addr(), to,
                                   "  (order confirmation)" if as_order else ""))

    if as_order:
        rows = payments._order_rows(
            {"order_id": "ESB-TEST01", "amount_total": 5700},
            {"game": "League of Legends", "detail": "Gold IV → Platinum II · Solo",
             "region": "EUW", "eta": "3–4 days", "currency": "usd"})
        origin = payments.site_origin()
        ok, err = mailer.send(to, "Your order is confirmed — ESB-TEST01 (test)",
                              payments._order_text(rows, origin),
                              html=payments._order_html(rows, origin))
    else:
        ok, err = mailer.send(
            to, "eSports Boost — SMTP test",
            "If you are reading this, the site can send mail.\n\n"
            "Sent by site/tools/send_test_mail.py. The support form and the\n"
            "order confirmation both go through this same mailbox.\n",
            reply_to=mailer.support_addr())

    if ok:
        print("\nSent. If it is not in the inbox within a minute, check the spam\n"
              "folder — and if it landed there, the domain needs SPF/DKIM records\n"
              "(DEPLOY.md, 'Turn on email').")
        return 0
    print("\nFAILED: %s" % err)
    print("  → %s" % HINTS.get(err, "See the SMTP error above."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
