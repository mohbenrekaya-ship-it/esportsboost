#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send one test message through the configured mailbox, and say what broke.

    python3 site/tools/send_test_mail.py                  # → SUPPORT_EMAIL
    python3 site/tools/send_test_mail.py me@example.com    # → somewhere else
    python3 site/tools/send_test_mail.py --order           # the buyer's receipt
    python3 site/tools/send_test_mail.py me@x.com --sequence   # all 3 mystery mails
    python3 site/tools/send_test_mail.py me@x.com --code|--warn|--chase   # just one

With no SMTP_PASSWORD in `.env` it asks for one at the prompt (never echoed,
never written anywhere, this process only). `--ask` forces that prompt even when
`.env` does have one.

This is the first thing to run after putting SMTP_* in `.env`: it uses the same
`mailer.py` the support form and the order webhook use, so if this lands in the
inbox, both of those will too — and if it doesn't, the failure here is the same
failure they would have hit silently.

`--order` renders the real order-confirmation mail against a sample order, which
is how you look at the template without paying for a boost.

`--sequence` does the same for the three mystery-discount mails — the code, the
halfway warning and the 35% chase — against a sample card in a THROWAWAY store,
so nobody's real row is touched and no real token is spent. Every figure is
quoted by the live engine, so what lands in the inbox is what a buyer would get.

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


def _prompt_password():
    """Ask for the mailbox password at the terminal, for this process only.

    `.env` is the normal home for it, but there are two good reasons to be able
    to type it instead: a shared machine where the secret should not sit on
    disk, and a one-off test where putting it in the shell command would write
    it into `~/.zsh_history`. `getpass` echoes nothing, the value never leaves
    this process, and nothing here writes it anywhere.

    Only ever offered on a real terminal — in CI or a pipe there is nobody to
    ask, and prompting would hang the run instead of failing it.
    """
    if not sys.stdin.isatty():
        return False
    import getpass
    try:
        pw = getpass.getpass("SMTP password for %s (not echoed, not saved): "
                             % (mailer.user() or "the mailbox"))
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    pw = pw.strip()
    if not pw:
        return False
    os.environ["SMTP_PASSWORD"] = pw
    return True

SEQ_FLAGS = ("--sequence", "--code", "--warn", "--chase")

# The sample card the sequence is rendered against. A real League climb with a
# paid add-on on it, so the receipt lines, the per-hour figure and the struck
# stream price all have something true to say.
SAMPLE = {"email": "", "game": "League of Legends", "service": "division",
          "from": "Gold IV", "to": "Platinum II", "mode": "Solo",
          "region": "Europe West", "addons": ["priority"], "cur": "usd"}


def _sample_row(to, stage, cur=""):
    """One card in a throwaway store — never the real one.

    `mystery.log_path()` is redirected before the module is imported by the
    caller, so nothing here can write to `mystery.ndjson`, spend a live token or
    put a test address next to a real one."""
    import mystery
    body = dict(SAMPLE, email=to)
    if cur:
        body["cur"] = cur
    row = mystery.clean_capture(body)
    row["token"] = mystery.new_token()
    now = int(__import__("time").time())
    if stage == "chase":
        # As the sweep would leave it: revived, at the follow-up rate, on its
        # own 24-hour clock.
        row.update(stage="followup", pct=mystery.FOLLOWUP_PCT,
                   expires=now + mystery.FOLLOWUP_TTL)
    elif stage == "warn":
        # Halfway through the hour, which is what the warning talks about.
        row["at"] = now - mystery.WARN_DELAY
        row["expires"] = row["at"] + mystery.TOKEN_TTL
    mystery.put(row)
    return row


def send_sequence(to, which):
    """Send one or all three of the mystery-discount mails. Returns (sent, failed)."""
    import followup
    import mystery
    origin = payments.site_origin()
    want = ("code", "warn", "chase") if which == "--sequence" else (which[2:],)
    sent = failed = 0
    for stage in want:
        row = _sample_row(to, stage)
        cur = mystery.currency_of(row)
        if stage == "code":
            ok = mystery.send_code(row)
            err = "" if ok else "send_failed"
        else:
            now_q, off_q = followup.price_pair(
                row, row["pct"] if stage == "chase" else mystery.OFFER_PCT)
            if not now_q:
                ok, err = False, "unpriceable"
            elif stage == "warn":
                mins = followup._mins_left(row)
                ok, err = mailer.send(
                    to, followup.WARN_SUBJECT % (int(round(row["pct"] * 100)), mins),
                    followup._warn_text(row, now_q, off_q, origin, cur, mins),
                    html=followup._warn_html(row, now_q, off_q, origin, cur, mins))
            else:
                ok, err = mailer.send(
                    to, followup.SUBJECT % (int(round(row["pct"] * 100)), row["game"]),
                    followup._text(row, now_q, off_q, origin, cur),
                    html=followup._html(row, now_q, off_q, origin, cur))
        label = {"code": "1. the code (30%%, 1h)",
                 "warn": "2. halfway warning (30 min left)",
                 "chase": "3. the chase (35%%, 24h)"}[stage]
        if ok:
            sent += 1
            print("  sent  %-34s %s" % (label % () if "%%" in label else label,
                                        row["token"]))
        else:
            failed += 1
            print("  FAIL  %-34s %s" % (label % () if "%%" in label else label, err))
    return sent, failed

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
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_order = "--order" in flags
    seq = next((f for f in flags if f in SEQ_FLAGS), "")

    # Redirect the mystery store BEFORE the module is imported anywhere, so a
    # sample card can never be written next to real ones.
    if seq:
        import tempfile
        os.environ["BINGO_LOG"] = tempfile.NamedTemporaryFile(
            prefix="esb-mailtest-", suffix=".ndjson", delete=False).name

    # No password on disk? Offer to take it here rather than making the caller
    # put it in `.env` or on the command line. `--ask` forces the prompt even
    # when one IS configured, for testing a different mailbox.
    if "--ask" in flags or (not mailer.configured() and mailer.user()
                            and mailer.host() and not mailer.password()):
        _prompt_password()

    print("mailbox : %s" % mailer.status())
    if not mailer.configured():
        print("\nNothing to send through.\n  → %s" % HINTS["mail_not_configured"])
        return 1
    to = args[0] if args else mailer.support_addr()

    if seq:
        print("sending : %s → %s  (mystery sequence)" % (mailer.from_addr(), to))
        print("store   : throwaway — %s\n" % os.environ["BINGO_LOG"])
        sent, failed = send_sequence(to, seq)
        print("\n%d sent, %d failed." % (sent, failed))
        if not failed:
            print("Every link in them points at %s." % payments.site_origin())
        return 1 if failed else 0

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
