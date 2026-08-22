# -*- coding: utf-8 -*-
"""The become-a-booster form's endpoint — `POST /api/apply` — behind
`/become-a-booster.html`.

The page has always had the application form; until now it was a facade whose
note said so out loud ("this form doesn't send anything"). This is the wire: a
validated application, composed as plain text and handed to `mailer.send()`,
landing in the support mailbox — the same inbox the contact form reaches.

It is a near-copy of `support.py`, deliberately: same house rules (stdlib only,
no build step, no third-party packages), the same public-write shape, and the
same one difference that shapes the module — **it stores nothing.** An
application is a message to a human, not a list to aggregate, so there is no
store, no `/ops` tab and no row anywhere. What the applicant typed exists in the
mailbox and nowhere else. When a real applications queue ships, this is the seam
that feeds it.

Load-bearing rules (identical to support.py):

  * **`/api/apply` is public and unauthenticated** — the form is on a public
    page. Which makes it a mail relay pointed at our own inbox, so it is
    defended three ways: every field is length-capped and validated here, a
    hidden honeypot field drops bots without telling them, and the route is rate
    limited per client.
  * **Nothing the applicant types reaches a header unsanitised.** `mailer`
    strips control characters from every header it writes; the game only reaches
    the subject line resolved by index against `D.GAMES`, never as a client
    string.
  * **The body is plain text, deliberately** — it carries a stranger's words.
  * **Nothing is sent to the applicant.** The only recipient is our own mailbox;
    an acknowledgement mail would make this a way to send stranger-written text
    to any address. The contact handle they give (Discord) is how we reach them.
  * **Restart the server after touching this file** — `/api/apply` lives in
    `serve.py`, and there is no watcher.
"""
import hashlib
import json
import re
import time

import analytics                # Upstash transport for the throttle counter
import data as D                # the game list the subject is resolved against
import geo
import mailer

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 16 * 1024
MAX_HANDLE = 80
MAX_RANK = 120
MAX_CONTACT = 120
MAX_OP = 2000                   # the textarea's ceiling; longer is truncated
MIN_CONTACT = 2

# One client may send a handful of applications in a window and no more. A real
# person applies once; anything past this is a script.
MAX_APPS = 4
APP_WINDOW = 900               # 15 minutes, same window support.py / accounts.py use

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

# In-process fallback counter for the throttle, used when there is no Upstash —
# under serve.py, one long-running process. Mirrors support.py / accounts.py.
_MEM_HITS = {}
_MEM_MAX = 4096


def _s(v, n):
    """Trim to a string, strip control chars, cap length."""
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _text(v, n):
    """Same, but keeps the newlines — this is the free-text field, not a header."""
    v = str(v if v is not None else "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v).strip()[:n]


# ══════════════════════════════════════════════════════════════════════════
#  throttle — per client, mirroring support.py's counter
# ══════════════════════════════════════════════════════════════════════════
def _key(client):
    """One counter per client, hashed so no address is written into a key."""
    return "esb:apply:hits:" + hashlib.sha256(
        ("apply|%s" % client).encode()).hexdigest()[:32]


def _too_many(key, now=None):
    now = int(now or time.time())
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["GET", key]])
            return int(res[0] or 0) >= MAX_APPS
        except (analytics.StoreError, TypeError, ValueError, IndexError):
            return False              # a store hiccup must not silence the form
    hit = _MEM_HITS.get(key)
    if not hit:
        return False
    count, start = hit
    if now - start > APP_WINDOW:
        _MEM_HITS.pop(key, None)
        return False
    return count >= MAX_APPS


def _note(key, now=None):
    now = int(now or time.time())
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["INCR", key], ["EXPIRE", key, APP_WINDOW]])
        except analytics.StoreError:
            pass
        return
    count, start = _MEM_HITS.get(key, (0, now))
    if now - start > APP_WINDOW:
        count, start = 0, now
    _MEM_HITS[key] = (count + 1, start)
    if len(_MEM_HITS) > _MEM_MAX:
        cutoff = now - APP_WINDOW
        for k, v in list(_MEM_HITS.items()):
            if v[1] < cutoff:
                _MEM_HITS.pop(k, None)


# ══════════════════════════════════════════════════════════════════════════
#  the application
# ══════════════════════════════════════════════════════════════════════════
def game_label(index):
    """Resolve the game select's index against the catalogue. Out of range
    answers the first game, never the client's own string — so the subject line
    can only ever name a game the site actually sells."""
    games = getattr(D, "GAMES", []) or []
    if not games:
        return "Unknown"
    try:
        i = int(index)
    except (TypeError, ValueError):
        i = 0
    if not 0 <= i < len(games):
        i = 0
    return str(games[i].get("name", "Unknown"))


def clean_application(body):
    """Validate one submission into the fields an application is composed from,
    or an `{"error": …}` dict naming the field that failed.

    Returns `{"handle", "game", "rank", "contact", "op"}` — nothing is stored,
    so these exist only long enough to be written into a mail.
    """
    if not isinstance(body, dict):
        return {"error": "handle"}
    handle = _s(body.get("handle"), MAX_HANDLE)
    if not handle:
        return {"error": "handle"}
    rank = _s(body.get("rank"), MAX_RANK)
    if not rank:
        return {"error": "rank"}
    contact = _s(body.get("contact"), MAX_CONTACT)
    if len(contact) < MIN_CONTACT:
        return {"error": "contact"}
    return {
        "handle": handle,
        "game": game_label(body.get("game")),
        "rank": rank,
        "contact": contact,
        "op": _text(body.get("op"), MAX_OP),
    }


def compose(app, ctx=None):
    """Turn a cleaned application into `(subject, text)`.

    The subject carries the in-game name and the game, because that is what makes
    an inbox sortable. The body leads with the facts recruiting needs.
    """
    ctx = ctx or {}
    subject = "[Booster application] %s · %s" % (app["handle"], app["game"])

    lines = ["Handle:  %s" % app["handle"],
             "Game:    %s" % app["game"],
             "Rank:    %s" % app["rank"],
             "Contact: %s" % app["contact"]]
    if ctx.get("co"):
        lines.append("Country: %s (%s)" % (ctx["co"], ctx.get("cosrc", "?")))
    lines.append("Sent:    %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime()))
    lines += ["", "-" * 56, ""]
    lines.append(app["op"] or "(no additional notes)")
    lines += ["", "-" * 56, "",
              "Reach the applicant on the contact handle above."]
    return subject, "\n".join(lines)


def process_application(raw, header_get):
    """POST /api/apply → (status, payload).

    Body: `{"handle", "rank", "contact", "game"?, "op"?, "hp"?, "tz"?, "lang"?}`.
    `hp` is the honeypot — a field no human ever fills.

    Responses mirror support.process_ticket exactly:
      · sent → `(200, {"sent": True})`
      · mail not configured → `(503, {"error": "mail_not_configured"})`
      · missing required field → `(400, {"error": "handle"|"rank"|"contact"})`
      · too many from this client → `(429, {"error": "throttled"})`
      · SMTP refused it → `(502, {"error": "send_failed"})`
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

    # The honeypot is answered exactly like a success.
    if _s(body.get("hp"), 80):
        return 200, {"sent": True}

    get = header_get or (lambda *_a, **_k: "")
    client = _s((get("x-forwarded-for") or "").split(",")[0].strip()
                or get("x-real-ip") or "", 64)
    key = _key(client)
    if _too_many(key):
        return 429, {"error": "throttled"}

    app = clean_application(body)
    if app.get("error"):
        _note(key)                    # a scripted probe pays for its failures
        return 400, {"error": app["error"]}

    if not mailer.configured():
        return 503, {"error": "mail_not_configured"}

    edge = _s(get("x-vercel-ip-country") or "", 2).upper()
    tz, lang = _s(body.get("tz"), 64), _s(body.get("lang"), 12)
    ctx = {"co": geo.country(edge, tz, lang), "cosrc": geo.source(edge, tz, lang)}

    subject, text = compose(app, ctx)
    ok, err = mailer.send(mailer.support_addr(), subject, text, kind="application")
    _note(key)                        # successes count too — this is a rate cap
    if not ok:
        return 502, {"error": err or "send_failed"}
    return 200, {"sent": True}
