# -*- coding: utf-8 -*-
"""The mystery-discount store — email capture at the top of the configurator.

The **seventh sibling** of `analytics.py`, `accounts.py`, `boosters.py`,
`orders.py`, `carts.py` and `guides.py`: same house rules (stdlib only, no build
step, Upstash Redis in prod / an NDJSON file in dev), same **separate store**
(`esb:bingo` / `mystery.ndjson`, never another store's key), reusing only
analytics' Upstash *transport*.

Why it exists (design_handoff_mystery_discount): the configurator proves intent —
somebody who set two ranks and read a price is a buyer — but captures nothing if
they leave. Eight seconds after their rank selection settles, the page offers a
sealed "mystery discount"; the address buys the right to open it.

**Every card pays the same 30%.** The pick is theatre, and the copy is written so
that it never claims otherwise: no odds, no luck, no "you beat the deck". Two
friends comparing cards find out in ten seconds, and a discovered lie on a store
whose central pitch is "the price does not move after checkout" costs more than
the twenty margin points ever earn. See `OFFER_PCT` below and the copy note in
build.py's `mystery_modal()`.

Where it differs from its siblings:

  * **Rows are mutated, not appended** — a row moves `issued → redeemed` (or
    `expired`), so the Upstash side is a **HASH** keyed by token (`HSET`), the
    same shape `carts.py` uses and for the same reason.
  * **The token IS the discount.** `data.py`'s `PROMOS` ships to every browser
    in `data.js`, so a static `CLIMB30` would be on a coupon aggregator inside a
    week — the handoff says so outright. Each capture mints one unguessable,
    single-use token instead, resolved **server-side only** against this store.
  * **One hour is a real deadline.** `TOKEN_TTL` is 3600 seconds and
    `redeemable()` enforces it. An offer that quietly still works teaches buyers
    to ignore every future countdown, which is worth more than one late order.
  * **One card per address, ever.** `EMAIL_KEY` is the record; a second capture
    from the same inbox returns the live token if there is one, and otherwise
    says the card is spent rather than minting a fresh 30%.
  * **It holds PII** (an email, a country), like accounts / carts / guides / orders
    — so the `/ops` payload is fetched on demand, never bundled into a refresh.

The row keeps the *configuration* the visitor had built, never a price: like
carts, the total is recomputed by `pricing.quote()` on read, so a tampered figure
can only ever mis-display in /ops and never mis-charge.
"""
import base64
import json
import os
import re
import secrets
import time

import analytics   # Upstash transport + store selection only — never its data
import geo

# ── limits ────────────────────────────────────────────────────────────────
MAX_BODY = 4 * 1024
MAX_ROWS = int(os.environ.get("BINGO_MAX", "20000") or 20000)
MAX_STR = 120
MAX_EMAIL = 160
MAX_ADDONS = 8
RECENT_CAP = 500

LIST_KEY = "esb:bingo"            # HASH: token -> row json
EMAIL_KEY = "esb:bingo:emails"    # SET: one card per address, ever

# The discount every card pays, as a fraction. Flat, not a weighted table — see
# the module docstring. Replaces the sitewide sale rather than stacking with it
# (pricing.resolve_promo, never-stack / best-wins), so a buyer gets 30% INSTEAD
# of the 15% code, never 45%.
OFFER_PCT = float(os.environ.get("BINGO_PCT", "0.30") or 0.30)
# One hour, and it means it. The reveal counts down to this.
TOKEN_TTL = int(os.environ.get("BINGO_TTL", "3600") or 3600)
TOKEN_BYTES = 6                   # ~10 chars of base32 — not guessable
TOKEN_RE = re.compile(r"^BINGO-[A-Z0-9]{8,20}$")

STATUSES = ("issued", "redeemed", "expired")

# The label the receipt shows beside the code, on both engines. Passed to
# pricing.quote() as `offer_label` so the checkout summary doesn't call this a
# "Come back offer" — the other thing that arrives through the same seam.
OFFER_LABEL = "Mystery discount"

# ── the follow-up: one second mail, at a better rate ──────────────────────
# A card that lapsed unbought is the strongest lead the site has — somebody who
# configured a climb, read a price, gave us an address and then stopped. This is
# the ONE mail that goes after it, and `followup.py` composes it.
#
# The row is **revived, not reissued**: `revive()` raises `pct` on the existing
# row and restarts its clock, so the token in the first mail keeps working, one
# card per inbox still holds, and `/api/bingo?token=` hands the browser the new
# percentage with no client change at all. Minting a second row would give one
# address two live discounts and break `find_by_email()`.
#
# ⚠ FOLLOWUP_PCT is a live margin decision, not a UI knob. At today's prices the
# extra five points is $1–$25 off a single order ON TOP of the thirty already
# given, and nothing here can tell you whether the second mail pays for itself —
# only the /ops Mystery tab against real traffic can. It is set by the business
# (2026-08-22); see CLAUDE.md.
FOLLOWUP_PCT = float(os.environ.get("BINGO_FOLLOWUP_PCT", "0.35") or 0.35)
# How long after the card expires the last-chance mail goes out. **Zero**, by
# the business's spec (2026-08-22): three mails — the code, a reminder at
# +30 min, and at +60 min one saying the card and the promo are over and the
# last chance is 35%. That third mail's whole subject is the expiry, so it lands
# ON it; the sweep runs every five minutes, so in practice 60–65 minutes after
# capture.
#
# Measured from the EXPIRY rather than from capture, so re-tuning `TOKEN_TTL`
# moves the chase with the deadline it is announcing instead of drifting into
# the live window. The two sweeps stay disjoint at any non-negative value:
# `due_warning()` requires `now < expires`, `due_followup()` requires
# `now >= expires + FOLLOWUP_DELAY`.
FOLLOWUP_DELAY = max(0, int(os.environ.get("BINGO_FOLLOWUP_DELAY", "0") or 0))
# The second window. Longer than the first hour — this one has to survive a
# night's sleep, and the mail says so — but still a real deadline, enforced by
# `redeemable()` exactly like the first.
FOLLOWUP_TTL = int(os.environ.get("BINGO_FOLLOWUP_TTL", str(24 * 3600)) or 24 * 3600)
# Past this, a lapsed card is simply left alone. A week-old configuration is not
# a live intent, the ladder may have been re-cut under it, and mailing it is how
# a discount programme turns into spam on the domain the order confirmations go
# out on.
FOLLOWUP_MAX_AGE = int(os.environ.get("BINGO_FOLLOWUP_MAX_AGE", str(3 * 86400))
                       or 3 * 86400)
# What the receipt calls the revived offer. Same role as OFFER_LABEL, and it has
# to differ: a checkout summary reading "Mystery discount" beside 35% would say
# the card paid a rate no card pays.
FOLLOWUP_LABEL = "Last-chance discount"

# ── the halfway warning ───────────────────────────────────────────────────
# Half an hour into the card's own hour, while the code is still LIVE and still
# at OFFER_PCT, one short mail says the clock is running out. It is the only
# message in the sequence that adds no offer at all — it argues the deadline
# the store already enforces, which is the one thing here that is unarguably
# true. Sent once, tracked by `warned` on the row.
#
# It must land INSIDE the hour or it is not a warning: `due_warning()` requires
# both `now >= at + WARN_DELAY` and `now < expires`, so a card that somehow
# slipped past its own deadline is left to the follow-up instead of being
# warned about a discount that has already gone.
WARN_DELAY = int(os.environ.get("BINGO_WARN_DELAY", "1800") or 1800)

STAGES = ("card", "followup")

# The configuration half of a row — everything that describes the ORDER rather
# than the offer. `update_config()` may write exactly these and nothing else,
# which is what stops a config beacon from touching the clock, the rate or the
# status. Named once here so the allowlist and the mail's `_state()` cannot
# drift apart.
CONFIG_FIELDS = ("game", "service", "from", "to", "mode", "region", "addons",
                 "wins", "placements", "unranked", "booster", "bundle", "cur")

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")


def log_path():
    return os.environ.get("BINGO_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "mystery.ndjson")


def _s(v, n=MAX_STR):
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def new_token():
    """An unguessable, single-use code. Base32 so it survives being read aloud,
    pasted out of an email client, or typed into the promo box — which is the
    point of showing it at all: the reveal's code chip has a copy button, so the
    string on screen has to be the string the server will honour."""
    body = base64.b32encode(secrets.token_bytes(TOKEN_BYTES)).decode().rstrip("=")
    return "BINGO-" + body


# ══════════════════════════════════════════════════════════════════════════
#  validation — everything a public endpoint writes goes through here
# ══════════════════════════════════════════════════════════════════════════
def clean_capture(body, now=None, country="", cosrc=""):
    """Validate one capture into a stored row, or None.

    Mirrors `carts.clean_cart()`: allowlisted keys, length caps, and no field a
    caller can use to inflate anything. The percentage is **not** read from the
    body — it is `OFFER_PCT`, resolved here and nowhere else."""
    if not isinstance(body, dict):
        return None
    email = _s(body.get("email"), MAX_EMAIL).lower()
    if not email or not _EMAIL_RE.match(email):
        return None

    addons = body.get("addons")
    if not isinstance(addons, list):
        addons = []
    addons = [_s(a, 40) for a in addons[:MAX_ADDONS] if a]

    now = _int(now or time.time())
    return {
        "email": email,
        "at": now,
        "updated": now,
        "expires": now + TOKEN_TTL,
        "status": "issued",
        "pct": OFFER_PCT,
        # Which sealed card they tapped. Pure theatre — it changes nothing about
        # the discount — but it is the one thing the flow asks them to choose,
        # so it is worth being able to see whether anyone ever moves off C.
        "pick": (_s(body.get("pick"), 1).upper() or "C")[:1],
        "optin": 1 if body.get("optin") in (1, True, "1", "true") else 0,
        "game": _s(body.get("game")),
        "service": _s(body.get("service"), 20),
        "from": _s(body.get("from"), 40),
        "to": _s(body.get("to"), 40),
        "mode": _s(body.get("mode"), 20),
        "region": _s(body.get("region"), 40),
        "addons": addons,
        "wins": max(0, min(_int(body.get("wins"), 0), 99)),
        "placements": max(0, min(_int(body.get("placements"), 0), 99)),
        "unranked": bool(body.get("unranked")),
        "booster": _s(body.get("booster"), 40),
        "bundle": _s(body.get("bundle"), 60),
        "country": _s(country, 4).upper(),
        "cosrc": _s(cosrc, 16),
        "session": _s(body.get("session"), 40),
        # The currency they are reading the site in. Stored because the
        # follow-up mail quotes a price and a per-hour figure, and quoting a
        # French buyer in dollars is the same one-set-of-numbers failure a bare
        # `$5` in the chrome is. Unknown or absent falls back at read time to
        # the country's market (`_currency()`), never blindly to USD.
        "cur": _s(body.get("cur"), 3).lower(),
        "mailed": 0,
        "applied_at": 0,
        "redeemed_at": 0,
        "order_id": "",
        # Which offer the row is currently carrying. `card` is the hour the
        # modal opened; `followup` is the revived second window. It is also the
        # once-ever flag on the second mail — see `due_followup()`.
        "stage": "card",
        # The halfway warning went out. Its own flag rather than a `stage`,
        # because the card is still on stage `card` afterwards — the warning
        # changes nothing about the offer, which is the point of it.
        "warned": 0,
        "followup_at": 0,
        "followup_mailed": 0,
        # One click in the second mail retires the row from every future sweep
        # WITHOUT voiding the discount it was just offered. Killing the code
        # because somebody asked for fewer emails is punitive, and it is not
        # what the link says it does.
        "nomail": 0,
    }


# ══════════════════════════════════════════════════════════════════════════
#  store — the carts.py shape: a HASH keyed by token, rows rewritten in place
# ══════════════════════════════════════════════════════════════════════════
def _up():
    return analytics.upstash_config()[0]


def _read_file():
    out = {}
    try:
        with open(log_path()) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                t = r.get("token")
                if t:
                    out[t] = r
    except OSError:
        return {}
    return out


def _write_file(rows):
    try:
        with open(log_path(), "w") as f:
            for r in rows.values():
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        return True
    except OSError:
        return False


def put(row):
    """Insert or replace one row by its token. Never raises — a lost capture
    must not 500 the page the visitor is standing on."""
    token = row.get("token")
    if not token:
        return False
    row["updated"] = _int(time.time())
    blob = json.dumps(row, separators=(",", ":"))
    if _up():
        try:
            analytics._upstash([["HSET", LIST_KEY, token, blob],
                                ["SADD", EMAIL_KEY, row.get("email", "")]])
            return True
        except analytics.StoreError:
            return False
    rows = _read_file()
    rows[token] = row
    return _write_file(rows)


def get(token):
    """One row by token, or None."""
    token = _s(token, 40).upper()
    if not TOKEN_RE.match(token):
        return None
    if _up():
        try:
            res = analytics._upstash([["HGET", LIST_KEY, token]])
        except analytics.StoreError:
            return None
        raw = res[0] if res else None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    return _read_file().get(token)


def read(limit=MAX_ROWS):
    """Every row, newest first."""
    if _up():
        try:
            res = analytics._upstash([["HGETALL", LIST_KEY]])
        except analytics.StoreError:
            return []
        flat = res[0] if res else []
        items = flat.values() if isinstance(flat, dict) else (flat or [])[1::2]
        rows = []
        for raw in items:
            try:
                rows.append(json.loads(raw))
            except (ValueError, TypeError):
                continue
    else:
        rows = list(_read_file().values())
    rows.sort(key=lambda r: -_int(r.get("at")))
    return rows[:limit]


def find_by_email(email):
    """The row already issued to an address, if there is one. One card per
    inbox, ever — this is what stops a visitor clearing localStorage and minting
    a second 30% against the same address."""
    email = _s(email, MAX_EMAIL).lower()
    if not email:
        return None
    if _up():
        # The SET is the O(1) "has this address had a card?" check; only when it
        # says yes do we pay for a scan to find which row.
        try:
            res = analytics._upstash([["SISMEMBER", EMAIL_KEY, email]])
            if not (res and res[0]):
                return None
        except analytics.StoreError:
            pass                    # can't verify → fall through to the scan
    for r in read():
        if r.get("email") == email:
            return r
    return None


def mark(token, **fields):
    """Patch one row in place. Returns the updated row or None."""
    row = get(token)
    if not row:
        return None
    row.update(fields)
    put(row)
    return row


def redeemable(token, now=None):
    """The row a token still entitles to a discount, or None.

    Single-use and time-boxed, and this is the **only** place the percentage is
    resolved — never `D.PROMOS`, which ships to the browser. A spent token, an
    expired one and an unknown one all resolve the same way: nothing."""
    row = get(token)
    if not row:
        return None
    if row.get("status") != "issued":
        return None
    now = _int(now or time.time())
    if now >= _int(row.get("expires")):
        return None
    return row


def redeem(token, order_id="", now=None):
    """Burn a token when the order it belongs to is paid."""
    return mark(token, status="redeemed", order_id=_s(order_id, 40),
                redeemed_at=_int(now or time.time()))


# ══════════════════════════════════════════════════════════════════════════
#  the follow-up — one second offer on a card that lapsed unbought
# ══════════════════════════════════════════════════════════════════════════
def stage_of(row):
    return (row or {}).get("stage") or "card"


def label_for(row):
    """What the receipt calls this row's discount. Read from the row rather
    than passed around, so the checkout summary, the order mail and /ops cannot
    label one token three ways."""
    return FOLLOWUP_LABEL if stage_of(row) == "followup" else OFFER_LABEL


def revive(token, pct=None, ttl=None, now=None):
    """Raise a lapsed card to the follow-up rate and restart its clock.

    **The same row and the same token.** The code already in the buyer's inbox
    keeps working, `find_by_email()` still finds exactly one card, and every
    client path — `mydBoot()`, the promo box, checkout — picks the new
    percentage up from `/api/bingo?token=` with no change on the client at all.

    Returns the revived row, or None if the token is unknown. It deliberately
    does NOT check whether the row is expired: a lapsed card is precisely what
    this exists to bring back. It will not touch a **redeemed** one, though —
    that order is paid, and re-opening a spent token is free money.
    """
    row = get(token)
    if not row or row.get("status") == "redeemed":
        return None
    now = _int(now or time.time())
    return mark(row["token"], status="issued", stage="followup",
                pct=float(FOLLOWUP_PCT if pct is None else pct),
                expires=now + _int(FOLLOWUP_TTL if ttl is None else ttl),
                followup_at=now)


def due_followup(now=None, limit=200, delay=None):
    """Cards ready for the second mail: the lapsed, unbought, un-chased ones.

    Five conditions, and each one is a way the mail would otherwise be wrong:

      * `status == "issued"` — never a paid order (`redeemed`) and never a row
        somebody unsubscribed into `expired`;
      * `stage == "card"` — **one follow-up, ever**. This is the whole
        idempotency story: `revive()` flips the stage before the message goes
        out, so a sweep running every five minutes cannot mail twice, and a
        crash between the two leaves the row chased rather than chaseable;
      * past `expires + delay` — the first offer has genuinely died. Mailing a
        better rate while the first one is still live would teach the buyer the
        countdown is theatre, which is the one thing `TOKEN_TTL` exists to stop;
      * younger than `FOLLOWUP_MAX_AGE` — a stale configuration is not intent;
      * `nomail` unset and an address present.

    An `applied_at` row is deliberately **included**: somebody who pressed Apply
    and still did not pay is the strongest lead in the store, not a spent one.
    """
    now = _int(now or time.time())
    delay = FOLLOWUP_DELAY if delay is None else _int(delay)
    out = []
    for r in read():
        if r.get("status") != "issued" or stage_of(r) != "card":
            continue
        if r.get("nomail") or not r.get("email"):
            continue
        if now < _int(r.get("expires")) + delay:
            continue
        if now - _int(r.get("at")) > FOLLOWUP_MAX_AGE:
            continue
        # Somebody who bought at full price is a customer, not a lead. The
        # token is only burned when the webhook can match it, so a buyer who
        # never used the code leaves this row `issued` for ever — see
        # `carts.has_ordered()`, which exists for exactly this and cost a real
        # customer a "you left this behind" mail about an order they had made.
        if _has_ordered(r.get("email")):
            mark(r["token"], nomail=1)
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def update_config(token, body):
    """Re-point a live row at the order the visitor is building NOW.

    The card is offered ~8 seconds after the target rank settles, and people
    keep configuring afterwards — they add Priority, switch to Duo, move the
    server, extend the climb, apply a bundle. Without this the row freezes at
    the moment the address was typed and all three mails quote an order that was
    abandoned two steps later, which makes the mail irrelevant rather than
    merely inaccurate: the price is wrong, the climb is wrong, and
    `/checkout?bingo=…` hydrates the wrong basket.

    **It writes `CONFIG_FIELDS` and nothing else.** Not `expires` — an edit is
    not a reason to restart a countdown, and a deadline that renews itself every
    time the buyer touches a control is not a deadline. Not `pct`, `status` or
    `stage` either, so a beacon can neither improve its own offer nor revive a
    dead one; `redeemable()` still decides that on the clock alone.

    A **redeemed** row is frozen: its configuration is the record of what was
    actually bought, and a later beacon from a browser still holding the token
    must not rewrite the receipt.
    """
    row = get(token)
    if not row or row.get("status") == "redeemed":
        return None
    fresh = clean_capture(dict(body or {}, email=row.get("email") or "x@y.zz"))
    if fresh is None:
        return None
    patch = {k: fresh[k] for k in CONFIG_FIELDS if k in fresh}
    # A blank currency means the beacon did not carry one; keep what we had
    # rather than losing a known market to an empty string.
    if not patch.get("cur"):
        patch.pop("cur", None)
    row.update(patch)
    put(row)
    return row


def _has_ordered(email):
    """Shared with `carts.has_ordered()` rather than reimplemented — one
    definition of "this address is a customer, stop selling to them"."""
    try:
        import carts
        return carts.has_ordered(email)
    except Exception:                                          # noqa: BLE001
        return False


def due_warning(now=None, limit=200, delay=None):
    """Cards halfway through their hour that have not been warned yet.

    The mirror of `due_followup()`, with the window inverted: this one fires
    while the offer is still LIVE, that one only once it is dead. The two can
    never both pick up the same row on the same sweep, which is what stops a
    visitor being told their discount is ending and that it has been replaced
    in the same five minutes.

      * `status == "issued"` and `stage == "card"` — never a paid card, never
        one already chased (a revived row has its own 24h clock and is not
        halfway through anything);
      * `warned` unset — **once, ever**, the same guarantee the chase makes;
      * past `at + WARN_DELAY` and still **inside** `expires` — a warning that
        arrives after the thing it warns about is a worse mail than none;
      * `nomail` unset and an address present.
    """
    now = _int(now or time.time())
    delay = WARN_DELAY if delay is None else _int(delay)
    out = []
    for r in read():
        if r.get("status") != "issued" or stage_of(r) != "card":
            continue
        if r.get("warned") or r.get("nomail") or not r.get("email"):
            continue
        at, exp = _int(r.get("at")), _int(r.get("expires"))
        if now < at + delay or now >= exp:
            continue
        if _has_ordered(r.get("email")):
            mark(r["token"], nomail=1)
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def mark_warned(token, now=None):
    """Stamp the halfway warning. Never changes the offer or the clock."""
    return mark(token, warned=1, warned_at=_int(now or time.time()))


def unsubscribe(token):
    """Retire a row from every future sweep, keeping its discount alive.

    Deliberately NOT `carts.process_unsubscribe()`'s `status="expired"`. A cart
    IS its offer, so retiring one costs nothing; here the row is a live code the
    reader was just handed, and voiding it because they asked for fewer emails
    punishes them for using the link. `due_followup()` reads `nomail`, and the
    follow-up is the only mail this store ever sends, so one flag is the whole
    opt-out."""
    row = get(token)
    if not row:
        return None
    return mark(row["token"], nomail=1)


def process_unsubscribe(token):
    """GET /api/bingo/unsubscribe?token=… → (status, payload).

    One click, no login, no confirmation step. Answers 200 either way: whether
    a token exists is not something an unauthenticated caller should learn."""
    unsubscribe(token)
    return 200, {"ok": True}


def clear():
    if _up():
        try:
            analytics._upstash([["DEL", LIST_KEY], ["DEL", EMAIL_KEY]])
            return True
        except analytics.StoreError:
            return False
    return _write_file({})


def count():
    return len(read())


def store_name():
    return "upstash" if _up() else "file"


# ══════════════════════════════════════════════════════════════════════════
#  the code mail — composed here, transported by mailer.py
# ══════════════════════════════════════════════════════════════════════════
# The handoff's rule: **send before the reveal renders, not after.** The reveal
# says a copy is in the inbox; if the send were queued behind the animation and
# failed, the promise would already be on screen. `process_issue()` therefore
# mails synchronously and reports back whether it went, and the modal hides that
# sentence when it did not — the same "degrade, never pretend" contract the rest
# of the mail seam has (see CLAUDE.md, "Outbound mail").
SUBJECT = "Your %d%% code — live for the next hour"


def _origin():
    try:
        import payments
        return payments.site_origin()
    except Exception:                                          # noqa: BLE001
        return ""


def _mail_text(row, origin, total, offer_total):
    mins = max(1, TOKEN_TTL // 60)
    link = "%s/games/" % origin if origin else ""
    body = (
        "You opened the card. Here is the code.\n\n"
        "  %s\n\n"
        "It takes %d%% off your order — %s instead of %s — and it replaces the\n"
        "current sale rather than stacking with it, so that is the final price.\n\n"
        "It works once and it is live for %d minutes from now.\n"
        % (row.get("token", ""), int(round(row.get("pct", OFFER_PCT) * 100)),
           _usd(offer_total), _usd(total), mins))
    if link:
        body += "\nPick up where you left off:\n%s\n" % link
    body += ("\nYou are getting this because you asked us to email the code. "
             "We won't add you to anything else unless you ticked the box.\n")
    return body


def _mail_html(row, origin, total, offer_total):
    from html import escape as esc
    mins = max(1, TOKEN_TTL // 60)
    pct = int(round(row.get("pct", OFFER_PCT) * 100))
    link = esc("%s/games/" % origin) if origin else ""
    cta = ('<p style="margin:0 0 28px"><a href="%s" style="display:block;text-align:center;'
           'background:linear-gradient(180deg,#ff8a3f,#ff4a1f);color:#120a06;font-weight:700;'
           'font-size:16px;text-decoration:none;padding:15px 20px;border-radius:10px">'
           'Finish my order</a></p>' % link) if link else ""
    return """\
<!doctype html><html><body style="margin:0;background:#0b0a09;font-family:-apple-system,\
Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e8e3dd">
<div style="max-width:520px;margin:0 auto;padding:32px 24px">
  <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#ff7a3f;\
margin:0 0 8px">eSports Boost</p>
  <h1 style="font-size:26px;line-height:1.25;margin:0 0 16px">You opened the card.</h1>
  <p style="font-size:15px;line-height:1.6;color:#b9b2aa;margin:0 0 24px">
    Here is your <b style="color:#e8e3dd">%(pct)d%%</b> code. It works once, and it is live for
    the next %(mins)d minutes.</p>

  <p style="margin:0 0 24px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;\
font-size:20px;font-weight:700;letter-spacing:.06em;color:#ff7a3f;border:1px dashed \
rgba(255,122,63,.5);border-radius:8px;padding:12px 16px;text-align:center">%(token)s</p>

  <table style="width:100%%;border-collapse:collapse;background:#141210;border:1px solid \
rgba(255,255,255,.10);border-radius:10px">
    <tr><td style="padding:18px 20px">
      <p style="margin:0 0 6px;font-size:16px;font-weight:600">%(climb)s</p>
      <p style="margin:10px 0 0;font-size:22px;font-weight:700">
        <span style="color:#8f8880;font-weight:400;font-size:16px;\
text-decoration:line-through">%(was)s</span>
        &nbsp;%(now)s</p>
    </td></tr>
  </table>

  <p style="margin:24px 0 0"></p>
  %(cta)s
  <p style="font-size:12px;line-height:1.6;color:#77706a;margin:0">
    It replaces the current sale rather than stacking with it, so %(now)s is the final price.
    You are getting this because you asked us to email the code.</p>
</div></body></html>""" % {
        "pct": pct, "mins": mins, "token": esc(row.get("token", "")),
        "climb": esc(_climb(row)), "cta": cta,
        "was": esc(_usd(total)), "now": esc(_usd(offer_total)),
    }


def _usd(n):
    return "$%s" % int(round(n or 0))


def _climb(row):
    """A one-line description of the order, from the stored config."""
    svc = row.get("service") or "division"
    if svc in ("wins", "placements"):
        n = row.get(svc) or 0
        noun = "net win" if svc == "wins" else "placement"
        return "%d %s%s" % (n, noun, "" if n == 1 else "s")
    if svc == "coaching":
        return "%s coaching" % (row.get("game") or "")
    a, b = row.get("from") or "", row.get("to") or ""
    return ("%s → %s" % (a, b)).strip(" →") or (row.get("game") or "your order")


def _state(row, pct=0):
    """The order dict `pricing.quote()` wants, rebuilt from a stored row —
    the same shape `recovery._state()` builds from a cart."""
    return {
        "game": row.get("game") or "",
        "service": row.get("service") or "division",
        "from": row.get("from") or "",
        "to": row.get("to") or "",
        "mode": row.get("mode") or "Solo",
        "region": row.get("region") or "",
        "addons": row.get("addons") or [],
        "wins": row.get("wins") or 1,
        "placements": row.get("placements") or 3,
        "unranked": bool(row.get("unranked")),
        "bundle": row.get("bundle") or None,
        "booster": row.get("booster") or "",
        "coach": 0, "pack": 1, "focus": [0], "slot": "",
        "promo": row.get("token") or "",
        "recovery_pct": pct,
        "offer_label": label_for(row),
    }


def list_total(row):
    """The order's LIST price — `subtotal`, before any discount.

    ⚠ This, not `price_pair()`'s first element, is what a mail may strike
    through. That one is the price **with the sitewide sale already on it**, so
    striking it while claiming "30% off" states a reduction that is not what the
    arithmetic did: a $48 climb sells at $41 in a 15% sale and at $34 with the
    code, and "30% off — $34 instead of $41" is a 17% claim wearing a 30% label.
    It also disagreed with the checkout page the mail links to, which strikes the
    list. Every discount on this site is a percentage of the list, so the list is
    the only figure a percentage may be quoted against."""
    import pricing
    q = pricing.quote(_state(row))
    return 0 if q.get("invalid") else _int(q.get("subtotal"))


def price_pair(row):
    """(normal_total, offer_total) for a stored row, recomputed — never a total
    the client sent. (0, 0) when the configuration no longer prices.

    The first element is the price **at today's sale**, which is what /ops means
    by what an order is worth. For the figure a mail strikes through, use
    `list_total()` — see the warning there."""
    import pricing
    now_q = pricing.quote(_state(row))
    if now_q.get("invalid"):
        return 0, 0
    off_q = pricing.quote(_state(row, row.get("pct") or OFFER_PCT))
    if off_q.get("invalid"):
        return 0, 0
    return _int(now_q.get("total")), _int(off_q.get("total"))


def currency_of(row):
    """The currency this row should be quoted in.

    The visitor's own pick when the capture carried one, else the market their
    country belongs to — `geo.currency_for()`, the same rule `i18n.js` opens the
    storefront on, so the mail and the page they left agree. Anything without a
    charge rate behind it falls back to dollars rather than displaying a
    currency the site could not actually bill (see `pricing.CHARGE_RATES` and
    CLAUDE.md's "every currency these tables can hand somebody must have a
    charge rate")."""
    import pricing
    cur = _s((row or {}).get("cur"), 3).lower()
    if cur not in pricing.CHARGE_RATES:
        cur = geo.currency_for(_s((row or {}).get("country"), 2).upper()).lower()
    return cur if cur in pricing.CHARGE_RATES else "usd"


def send_code(row):
    """Mail the code. Returns True only if a message actually went out.

    Never raises and never blocks the issue: an unconfigured or unhappy mailbox
    means the reveal drops its "a copy is in your inbox" line, not that the
    buyer loses the discount they were just promised."""
    try:
        import mailer
        if not mailer.configured() or not mailer.valid(row.get("email") or ""):
            return False
        _sale, offer_total = price_pair(row)
        total = list_total(row)        # strike the LIST, never the sale price
        origin = _origin()
        ok, err = mailer.send(
            row["email"], SUBJECT % int(round((row.get("pct") or OFFER_PCT) * 100)),
            _mail_text(row, origin, total, offer_total),
            html=_mail_html(row, origin, total, offer_total), kind="bingo_code")
        if not ok:
            import sys
            sys.stderr.write("[bingo] %s mail failed: %s\n" % (row.get("token"), err))
        return bool(ok)
    except Exception as e:                                     # noqa: BLE001
        import sys
        sys.stderr.write("[bingo] mail skipped: %s\n" % e)
        return False


# ══════════════════════════════════════════════════════════════════════════
#  request handling — serve.py and api/bingo.py are both thin shells over this
# ══════════════════════════════════════════════════════════════════════════
def _body(raw):
    if not raw or len(raw) > MAX_BODY:
        return None
    try:
        b = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return None
    return b if isinstance(b, dict) else None


def _payload(row, mailed):
    """What the modal needs to render its reveal, and nothing more."""
    return {
        "ok": True, "token": row["token"], "pct": row.get("pct", OFFER_PCT),
        "expires": _int(row.get("expires")),
        "seconds": max(0, _int(row.get("expires")) - _int(time.time())),
        "mailed": bool(mailed), "label": OFFER_LABEL,
    }


def process_issue(raw, header_get, session_email=""):
    """POST /api/bingo → (status, payload).

    Public and unauthenticated, like `/api/collect` and `/api/guides` — the
    modal is on nine public pages. Everything is allowlisted and capped in
    `clean_capture()`, and the discount percentage is never read from the body.

    A signed-in visitor's address comes from the **verified session cookie**
    when there is one, exactly the way `/api/cart` and `/api/orders` resolve it:
    a browser must never be able to mint a card against somebody else's inbox.

    Three answers:
      · a new address                    → `{ok: true, token, pct, seconds}` and
                                           the code is mailed before we return.
      · an address with a live card      → the SAME token, so a lost tab does
                                           not cost the visitor their discount.
      · an address whose card is spent
        or expired                       → `{ok: false, reason: "spent"}`. One
                                           card per inbox, ever — the modal has
                                           a designed state for this and says so
                                           plainly rather than minting a second.
    """
    body = _body(raw)
    if body is None:
        return 204, None

    # One route, two verbs. `apply` is a beacon, not an issue: it records that
    # the buyer pressed Apply on the reveal, which is the only place the funnel
    # between "opened a card" and "paid for one" can be measured. It carries a
    # token and nothing else, and it can never mint or extend anything.
    action = _s(body.get("action"), 12)
    if action == "apply":
        mark_applied(_s(body.get("token"), 40).upper())
        return 200, {"ok": True}

    # The config beacon. Like `apply` it is a write against an EXISTING token
    # and can never mint, extend or improve anything — see `update_config()`.
    # The token is the whole authorisation, which is sound because the only
    # thing it can change is which order that same token quotes, and every
    # price is re-computed server-side at send and at checkout regardless.
    if action == "config":
        update_config(_s(body.get("token"), 40).upper(), body)
        return 200, {"ok": True}

    if session_email:
        body = dict(body, email=session_email)

    get_h = header_get or (lambda _k: "")
    edge = _s(get_h("x-vercel-ip-country") or "", 2).upper()
    tz, lang = _s(body.get("tz"), 64), _s(body.get("lang"), 12)
    row = clean_capture(body, country=geo.country(edge, tz, lang),
                        cosrc=geo.source(edge, tz, lang))
    if row is None:
        return 400, {"ok": False, "reason": "email"}

    existing = find_by_email(row["email"])
    if existing:
        live = redeemable(existing.get("token", ""))
        if live:
            # Same card, same clock. Refresh the configuration so a later
            # checkout re-prices against what they are actually building, but
            # never the expiry — the hour started when the card was opened.
            #
            # ⚠ Patch the EXISTING row with the config fields, never rebuild a
            # fresh one and copy some fields back. It used to keep an allowlist
            # of nine lifecycle fields, which silently dropped every field added
            # after it was written: a re-capture reset `stage` to "card",
            # `warned` to 0 and — worst — `nomail` to 0, so a chased card became
            # chaseable again, a warning fired on a 24-hour row quoting "1425
            # minutes… halfway through its hour", and an unsubscribe undid
            # itself. `CONFIG_FIELDS` is the same allowlist `update_config()`
            # uses, so there is ONE definition of what a capture may change and
            # a new lifecycle field can never leak through it again.
            fresh = {k: row[k] for k in CONFIG_FIELDS if k in row}
            if not fresh.get("cur"):
                fresh.pop("cur", None)      # never lose a known market to ""
            existing.update(fresh)
            put(existing)
            return 200, _payload(existing, existing.get("mailed"))
        return 200, {"ok": False, "reason": "spent"}

    row["token"] = new_token()
    put(row)

    # The marketing opt-in is deliberately SEPARATE from the code: the code mail
    # is transactional and goes either way, and bundling consent into it is what
    # gets a sender blacklisted. This writes the same guides list the /guides
    # landing does — one list, one preference centre, one unsubscribe.
    if row.get("optin"):
        try:
            import guides
            lead = guides.clean_lead(
                {"email": row["email"], "guides": "", "optin": 1},
                row["at"], {"co": row.get("country", ""), "cosrc": row.get("cosrc", "")})
            if lead:
                guides.append([lead])
        except Exception:                                      # noqa: BLE001
            pass          # a mailing-list hiccup must not cost them the code

    mailed = send_code(row)
    if mailed:
        row["mailed"] = 1
        put(row)
    return 200, _payload(row, mailed)


def process_resolve(token):
    """GET /api/bingo?token=… → (status, payload).

    The **only** way a client learns the percentage: it is not in `data.js`, so
    a token is the sole route to it. The browser calls this on every page load
    that carries a stored token, which is also what makes the one-hour deadline
    real — the moment it lapses the page re-prices at the normal sale on its own.
    Unknown, spent and expired all answer the same `{"valid": false}`."""
    row = redeemable(token)
    if not row:
        return 200, {"valid": False, "pct": 0}
    return 200, {"valid": True, "token": row["token"], "pct": row.get("pct", OFFER_PCT),
                 "label": label_for(row), "stage": stage_of(row),
                 "expires": _int(row.get("expires")),
                 "seconds": max(0, _int(row.get("expires")) - _int(time.time())),
                 "email": row.get("email", ""),
                 # The configuration the card was opened against. The follow-up
                 # mail links straight to /checkout?bingo=…, and that page has
                 # no configurator: without this it would price whatever the
                 # browser happened to be holding — a different order from the
                 # one the mail quoted, or on a fresh device no order at all.
                 # It is the row's own config handed back to the row's own
                 # token, so it discloses nothing the token did not already.
                 "order": order_of(row)}


def order_of(row):
    """The stored configuration, in the shape app.js's `normalize()` wants.

    Mirrors `carts.py`'s resolve payload. Everything here was written through
    `clean_capture()` and is re-validated by `normalize()` on arrival, so the
    client end is not trusting this any more than it trusts localStorage."""
    return {"game": row.get("game", ""), "service": row.get("service", "division"),
            "from": row.get("from", ""), "to": row.get("to", ""),
            "mode": row.get("mode", ""), "region": row.get("region", ""),
            "addons": row.get("addons", []), "wins": row.get("wins", 0),
            "placements": row.get("placements", 0),
            "unranked": bool(row.get("unranked")),
            "booster": row.get("booster", ""), "bundle": row.get("bundle", "")}


def mark_applied(token, now=None):
    """The buyer pressed Apply. Not a burn — the code is only spent on payment —
    but it is the number that says whether the reveal actually converts."""
    row = redeemable(token)
    if not row or _int(row.get("applied_at")):
        return None
    return mark(row["token"], applied_at=_int(now or time.time()))


# ══════════════════════════════════════════════════════════════════════════
#  aggregation — what /ops reads
# ══════════════════════════════════════════════════════════════════════════
def summary(days=30, now=None):
    """The Mystery tab's payload: how many cards were opened, how many were
    applied, how many were actually paid for, what that was worth, and the rows.
    Fetched on demand like Accounts and Carts — it holds PII."""
    days = max(1, min(_int(days, 30), 365))
    now = _int(now or time.time())
    cutoff = now - days * 86400
    rows = [r for r in read() if _int(r.get("at")) >= cutoff]

    by_status = {s: 0 for s in STATUSES}
    by_game, by_country, by_pick = {}, {}, {}
    applied = optins = mailed = live = 0
    # The second mail's own funnel. `chased` is how many lapsed cards were
    # revived; `chased_redeemed` how many of those were then paid for. Read
    # together they are the only thing that says whether giving the extra five
    # points back is buying orders or buying nothing — see FOLLOWUP_PCT.
    chased = chased_redeemed = chase_due = unsubs = warned = 0
    redeemed_value = potential_value = 0
    recent = []
    for r in sorted(rows, key=lambda r: -_int(r.get("at"))):
        st = r.get("status", "issued")
        # An `issued` row past its hour is expired in every way that matters;
        # counting it as live would overstate the funnel's open end.
        if st == "issued" and now >= _int(r.get("expires")):
            st = "expired"
        elif st == "issued":
            live += 1
        by_status[st] = by_status.get(st, 0) + 1

        normal, offer = price_pair(r)
        potential_value += normal
        if r.get("status") == "redeemed":
            redeemed_value += normal
        if _int(r.get("applied_at")):
            applied += 1
        if r.get("optin"):
            optins += 1
        if r.get("mailed"):
            mailed += 1
        if stage_of(r) == "followup":
            chased += 1
            if r.get("status") == "redeemed":
                chased_redeemed += 1
        elif (r.get("status") == "issued" and not r.get("nomail") and r.get("email")
              and now >= _int(r.get("expires")) + FOLLOWUP_DELAY
              and now - _int(r.get("at")) <= FOLLOWUP_MAX_AGE):
            chase_due += 1
        if r.get("nomail"):
            unsubs += 1
        if r.get("warned"):
            warned += 1

        g = r.get("game") or "—"
        gs = by_game.setdefault(g, {"game": g, "count": 0, "redeemed": 0})
        gs["count"] += 1
        if r.get("status") == "redeemed":
            gs["redeemed"] += 1

        c = r.get("country") or "—"
        by_country[c] = by_country.get(c, 0) + 1
        p = (r.get("pick") or "—")[:1]
        by_pick[p] = by_pick.get(p, 0) + 1

        if len(recent) < RECENT_CAP:
            recent.append({
                "token": r.get("token", ""), "email": r.get("email", ""),
                "at": _int(r.get("at")), "expires": _int(r.get("expires")),
                "applied_at": _int(r.get("applied_at")),
                "redeemed_at": _int(r.get("redeemed_at")),
                "status": st, "game": g, "pick": p,
                "stage": stage_of(r), "followup_at": _int(r.get("followup_at")),
                "warned": 1 if r.get("warned") else 0,
                "nomail": 1 if r.get("nomail") else 0,
                "summary": _climb(r), "mode": r.get("mode", ""),
                "optin": 1 if r.get("optin") else 0,
                "mailed": 1 if r.get("mailed") else 0,
                "co": c, "cosrc": r.get("cosrc", ""),
                "value": normal, "offer": offer,
                "order_id": r.get("order_id", ""),
                "syn": 1 if r.get("syn") else 0,
            })

    total = len(rows)
    redeemed = by_status.get("redeemed", 0)
    # Of the cards actually opened — the question the tab exists to answer is
    # "does giving 30% away buy orders", so the denominator is every card issued.
    rate = round(100.0 * redeemed / total, 1) if total else 0.0
    apply_rate = round(100.0 * applied / total, 1) if total else 0.0

    return {
        "total": total, "days": days, "live": live, "mailed": mailed,
        "applied": applied, "apply_rate": apply_rate,
        "redeemed": redeemed, "redeem_rate": rate,
        "redeemed_value": redeemed_value, "potential_value": potential_value,
        "optins": optins, "pct": OFFER_PCT, "ttl_mins": TOKEN_TTL // 60,
        "warned": warned, "warn_delay_mins": WARN_DELAY // 60,
        "chased": chased, "chased_redeemed": chased_redeemed,
        "chase_due": chase_due, "unsubs": unsubs,
        "followup_pct": FOLLOWUP_PCT, "followup_ttl_mins": FOLLOWUP_TTL // 60,
        # Of the cards actually chased — "did the second mail convert", which is
        # a different question from the programme's overall redeem rate above.
        "chase_rate": (round(100.0 * chased_redeemed / chased, 1) if chased else 0.0),
        "synthetic": sum(1 for r in rows if r.get("syn")),
        "statuses": [{"status": s, "count": by_status.get(s, 0)} for s in STATUSES],
        "games": sorted(by_game.values(), key=lambda x: -x["count"]),
        "picks": sorted(({"pick": k, "count": v} for k, v in by_pick.items()),
                        key=lambda x: x["pick"]),
        "countries": sorted(({"code": k, "count": v} for k, v in by_country.items()),
                            key=lambda x: (-x["count"], x["code"])),
        "recent": recent, "store": store_name(),
    }
