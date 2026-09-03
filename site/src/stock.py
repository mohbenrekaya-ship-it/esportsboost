# -*- coding: utf-8 -*-
"""The listing store behind the accounts shop — the credentials themselves, and
the handover mail that sends one to the buyer the moment a payment clears.

This is the **eighth store sibling** of analytics / accounts / boosters /
orders / carts / mystery / guides: same house rules (stdlib only, no build step,
Upstash Redis in prod / an NDJSON file in dev), same operator-write /
public-read shape `boosters.py` has, and a **separate store** (`esb:stock` /
`stock.ndjson`, never another store's key). It reuses only analytics' Upstash
*transport*, never its data.

It closes the ⚠ that has been standing in `data.py` since the shop shipped:

    "STOCK IS A COUNT AND NOTHING DECREMENTS IT … the only place a sold-out
     listing can be stopped is account_pick(), on the server, at the moment
     somebody tries to pay for it … until it exists fulfilment is manual: the
     webhook records the listing id and an operator hands over one set of
     credentials."

Both halves are now built. Load-bearing rules:

  * ⚠ **THIS IS THE MOST SENSITIVE STORE ON THE SITE.** Every row is a live
    login to a real account somebody paid for. **No public route ever returns a
    credential** — `/api/stock` serves counts and nothing else, `summary()`
    (the /ops list) never carries a password, and the one function that does
    return one (`reveal()`) is reachable only behind the ops token. The
    handover mail's body is **redacted in the outbox** (`mailer.send(...,
    redact=True)`), so /ops records that the mail went out without keeping a
    second copy of the password forever. And by default it publishes **no
    counts at all** — see `PUBLIC_COUNTS`.
  * ⚠ **Credentials are stored in PLAINTEXT.** They have to be: the delivery
    mail has to reproduce them, so there is nothing to compare against and a
    hash is useless. That makes the store's access controls the whole
    protection — use Upstash in production (never the file store on a shared
    box), keep `UPSTASH_REDIS_REST_TOKEN` and `OPS_PASSWORD` out of anything
    committed, and run `tools/stock_import.py --purge-sold` on a schedule so a
    breach cannot reach further back than the warranty window.
  * **The claim is ATOMIC, because a double-sold account is unrecoverable.**
    Available unit ids sit in a per-(listing, shard) LIST and a claim is one
    `LPOP` — two Stripe webhooks arriving together cannot be handed the same
    row, which a read-modify-write over a HASH could not promise. The row
    itself lives in the HASH; the queue holds only ids.
  * **It is idempotent per order.** Stripe retries a webhook until it gets a
    200, and `payments._seen_event()` is in-memory only — it does not survive
    the process. `esb:stock:orders` maps order id → unit id, and a claim for an
    order that already has one returns that row instead of burning a second
    account.
  * **The store is the authority ONLY once it holds something.** With an empty
    store every count on the shop is `data.py`'s hand-set figure exactly as
    before, so loading real stock is what turns this on — there is no flag to
    forget. `has_data()` is that switch, and it is asked per (listing, shard)
    at the checkout guard so a listing the operator has not loaded yet still
    sells the old way rather than reading as sold out.
  * **Nothing here is placeholder.** Unlike its seven siblings this store ships
    empty and every row in it is real — there is no seeder, and rows carry no
    `syn` flag. An account in here is an account somebody can log into.

Restart the server after touching this file — `/api/stock` lives in `serve.py`
and the `stock` ops action in `ops.py`; there is no watcher.
"""
import json
import os
import re
import secrets
import sys
import time

import analytics   # Upstash transport + store selection only — never its data
import data as D

# ── limits ────────────────────────────────────────────────────────────────
MAX_UNITS = int(os.environ.get("STOCK_MAX", "20000") or 20000)
MAX_FIELD = 200            # a login, a password, an inbox address
MAX_NOTE = 300
MAX_IMPORT = 2000          # lines accepted in one import call

# ⚠ THE SHOP DOES NOT PUBLISH REAL STOCK, and that is the business's call
# (2026-09-03). `/api/stock` answers 204 unless STOCK_PUBLIC_COUNTS=1, so
# `initStock()` in app.js keeps every server-rendered `data.py` figure and the
# four counts on the page stay the hand-set marketing ones.
#
# What this does NOT switch off is the store itself: `sellable()` still refuses
# a sold-out (listing, shard) at checkout and the webhook still claims and
# mails a real account. So the page may advertise 8 Gold while 2 are on the
# shelf — the honest half is enforced at the till, not on the card, and the
# third buyer is refused with "that account has just been bought" rather than
# charged for something nobody can hand over.
#
# Flip it to 1 the day the counts on the page should be the real ones; nothing
# else has to change, because the client already treats a 200 as authoritative
# and a 204 as "keep the fallback".
PUBLIC_COUNTS = os.environ.get("STOCK_PUBLIC_COUNTS", "").strip() == "1"

LIST_KEY = "esb:stock"              # HASH: unit id -> row json
QUEUE_KEY = "esb:stock:q"           # LIST per (sku|region): available unit ids
ORDER_KEY = "esb:stock:orders"      # HASH: order id -> unit id (idempotency)
LOGIN_KEY = "esb:stock:logins"      # SET of sku|region|login (one row per login)
# Every (listing, shard) the store has EVER held. ⚠ Load-bearing: it is what
# tells "sold out" apart from "never loaded". Without it a pair whose queue has
# emptied is indistinguishable from one that was never stocked, and the
# fallback in `sellable()` — and the client's own — would quietly put a
# sold-out listing back on sale at data.py's hand-set figure.
PAIRS_KEY = "esb:stock:pairs"

# Statuses a unit can hold. `held` is an operator parking it without deleting —
# out of the queue, still in the store, still revealable.
AVAILABLE, SOLD, HELD = "available", "sold", "held"

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# The separators an import line may use, in the order they are tried. A colon
# is the format the operator asked for; the other two exist because a password
# may contain a colon and then needs a separator it does not contain.
SEPARATORS = ("\t", "|", ";", ":")


def log_path():
    return os.environ.get("STOCK_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "stock.ndjson")


def store_name():
    return analytics.store_name()


def _up():
    return analytics.upstash_config()[0]


def _s(v, n=MAX_FIELD):
    return _CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def new_id():
    """An unguessable unit id. Unguessable because it is what `reveal()` and the
    ops drill-down address a credential by."""
    return "u_" + secrets.token_urlsafe(12)


# ══════════════════════════════════════════════════════════════════════════
#  the catalogue join — a unit names a listing and a shard, never re-states one
# ══════════════════════════════════════════════════════════════════════════
def sku_ok(sku):
    return D.account(str(sku or "").strip()) is not None


def region_ok(region):
    return str(region or "").strip() in D.ACCOUNT_REGIONS


def queue_key(sku, region):
    return "%s:%s|%s" % (QUEUE_KEY, sku, region)


def listing_name(sku):
    a = D.account(sku)
    return a["name"] if a else sku


def clean_unit(row):
    """Validate one credential into a stored record, or None.

    A unit that does not name a real listing and a real shard is refused rather
    than stored: the shard decides which credentials fulfilment may hand over,
    and a row filed under a listing the catalogue does not sell can never be
    claimed by anything — it would sit in the store looking like stock.
    """
    if not isinstance(row, dict):
        return None
    sku = _s(row.get("sku"), 60)
    region = _s(row.get("region"), 60)
    login = _s(row.get("login"))
    password = _s(row.get("password"))
    if not sku_ok(sku) or not region_ok(region) or not login or not password:
        return None
    out = {
        "id": _s(row.get("id"), 40) or new_id(),
        "sku": sku,
        "region": region,
        "login": login,
        "password": password,
        "email": _s(row.get("email")),
        "email_password": _s(row.get("email_password")),
        "note": _s(row.get("note"), MAX_NOTE),
        "status": row.get("status") if row.get("status") in (AVAILABLE, SOLD, HELD) else AVAILABLE,
        "at": _int(row.get("at")) or int(time.time()),
        "order_id": _s(row.get("order_id"), 40),
        "buyer": _s(row.get("buyer")),
        "sold_at": _int(row.get("sold_at")),
        "mailed": _int(row.get("mailed")),
        "mail_error": _s(row.get("mail_error")),
    }
    return out


# ══════════════════════════════════════════════════════════════════════════
#  the import format — `user:pass`, one account per line
# ══════════════════════════════════════════════════════════════════════════
def _split(line):
    """Split one import line into its fields.

    The separator is chosen per line, most exotic first: a password containing
    a colon is a real thing and the operator gets `user|pass` (or a tab) as the
    way out. **Ambiguity is an error, never a guess** — a line that splits into
    more fields than the format has is reported back with its number rather
    than stored with half a password in it, because a silently truncated
    credential is discovered by the customer, not by us.
    """
    for sep in SEPARATORS:
        if sep in line:
            return [p.strip() for p in line.split(sep)], sep
    return [line.strip()], ""


def parse_lines(text, sku, region, note=""):
    """`user:pass` lines → (rows, errors).

    Four shapes, all optional past the second field:

        user:pass
        user:pass:inbox@mail.com
        user:pass:inbox@mail.com:inboxpassword

    Blank lines and `#` comments are skipped. Errors carry the line number and
    the reason, so an import of 300 accounts tells the operator exactly which
    three lines to fix instead of failing as a lump.
    """
    rows, errors = [], []
    if not sku_ok(sku):
        return [], [(0, "unknown listing %r — see site/tools/stock_import.py --list" % sku)]
    if not region_ok(region):
        return [], [(0, "unknown server %r — one of: %s"
                     % (region, ", ".join(D.ACCOUNT_REGIONS)))]
    seen = set()
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if len(rows) + len(errors) >= MAX_IMPORT:
            errors.append((n, "import capped at %d lines" % MAX_IMPORT))
            break
        parts, sep = _split(line)
        if len(parts) < 2:
            errors.append((n, "no separator — expected user:pass"))
            continue
        if len(parts) > 4:
            errors.append((n, "%d fields split on %r — if the password contains "
                              "%r, use user|pass instead"
                           % (len(parts), sep, sep)))
            continue
        login, password = parts[0], parts[1]
        if not login or not password:
            errors.append((n, "empty user or password"))
            continue
        key = login.lower()
        if key in seen:
            errors.append((n, "duplicate of an earlier line in this file"))
            continue
        seen.add(key)
        unit = clean_unit({
            "sku": sku, "region": region, "login": login, "password": password,
            "email": parts[2] if len(parts) > 2 else "",
            "email_password": parts[3] if len(parts) > 3 else "",
            "note": note,
        })
        if not unit:
            errors.append((n, "rejected — check the login and password lengths"))
            continue
        rows.append(unit)
    return rows, errors


# ══════════════════════════════════════════════════════════════════════════
#  store — a HASH of rows plus one queue of available ids per (listing, shard)
# ══════════════════════════════════════════════════════════════════════════
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
                if isinstance(r, dict) and r.get("id"):
                    out[r["id"]] = r
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


def _login_key(row):
    return "%s|%s|%s" % (row["sku"], row["region"], row["login"].lower())


def add(rows):
    """Persist cleaned units, **one row per (listing, shard, login)**.

    Returns {"added", "duplicate"}. A login already stored on that shard is
    dropped rather than stored twice: re-importing the same sheet is a thing
    operators do, and the second copy would be a second sale of one account.
    """
    rows = [r for r in (rows or []) if r]
    if not rows:
        return {"added": 0, "duplicate": 0}
    fresh, dupes, seen = [], 0, set()
    if _up():
        for r in rows:
            k = _login_key(r)
            if k in seen:
                dupes += 1
                continue
            try:
                res = analytics._upstash([["SISMEMBER", LOGIN_KEY, k]])
                if res and res[0]:
                    dupes += 1
                    continue
            except analytics.StoreError:
                pass
            seen.add(k)
            fresh.append(r)
        if not fresh:
            return {"added": 0, "duplicate": dupes}
        cmds = []
        for r in fresh:
            cmds.append(["HSET", LIST_KEY, r["id"], json.dumps(r, separators=(",", ":"))])
            cmds.append(["SADD", LOGIN_KEY, _login_key(r)])
            cmds.append(["SADD", PAIRS_KEY, "%s|%s" % (r["sku"], r["region"])])
            if r["status"] == AVAILABLE:
                cmds.append(["RPUSH", queue_key(r["sku"], r["region"]), r["id"]])
        try:
            analytics._upstash(cmds)
        except analytics.StoreError as e:
            sys.stderr.write("[stock] add failed: %s\n" % e)
            return {"added": 0, "duplicate": dupes}
        return {"added": len(fresh), "duplicate": dupes}

    store = _read_file()
    existing = {_login_key(r) for r in store.values() if r.get("login")}
    for r in rows:
        k = _login_key(r)
        if k in seen or k in existing:
            dupes += 1
            continue
        seen.add(k)
        store[r["id"]] = r
        fresh.append(r)
    if fresh and not _write_file(store):
        return {"added": 0, "duplicate": dupes}
    return {"added": len(fresh), "duplicate": dupes}


def get(uid):
    uid = _s(uid, 40)
    if not uid:
        return None
    if _up():
        try:
            res = analytics._upstash([["HGET", LIST_KEY, uid]])
        except analytics.StoreError:
            return None
        raw = res[0] if res else None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    return _read_file().get(uid)


def put(row):
    """Insert or replace one row by id. The queue is NOT touched here — a row's
    place in the claim queue is owned by `add()` / `claim()` / `restock()`, so a
    field patch can never duplicate an id in it."""
    if not row or not row.get("id"):
        return False
    if _up():
        try:
            analytics._upstash([["HSET", LIST_KEY, row["id"],
                                 json.dumps(row, separators=(",", ":"))]])
            return True
        except analytics.StoreError:
            return False
    store = _read_file()
    store[row["id"]] = row
    return _write_file(store)


def mark(uid, **fields):
    row = get(uid)
    if not row:
        return None
    row.update(fields)
    put(row)
    return row


def read(limit=MAX_UNITS):
    """Every unit, newest first."""
    limit = max(1, min(_int(limit, MAX_UNITS) or MAX_UNITS, MAX_UNITS))
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


def count():
    if _up():
        try:
            return _int((analytics._upstash([["HLEN", LIST_KEY]]) or [0])[0])
        except (analytics.StoreError, TypeError, ValueError):
            return 0
    return len(_read_file())


def has_data():
    """Is the store populated at all?

    This is the switch that hands stock control over from `data.py`'s hand-set
    figures to real inventory. It is deliberately store-wide rather than a
    config flag: loading the first batch turns it on, clearing the store turns
    it back off, and there is nothing to forget to set."""
    return count() > 0


def clear():
    """Wipe the store. Operator-only — never exposed over HTTP."""
    if _up():
        cmds = [["DEL", LIST_KEY], ["DEL", ORDER_KEY], ["DEL", LOGIN_KEY],
                ["DEL", PAIRS_KEY]]
        for a in D.ACCOUNTS:
            for region in D.ACCOUNT_REGIONS:
                cmds.append(["DEL", queue_key(a["id"], region)])
        try:
            analytics._upstash(cmds)
        except analytics.StoreError:
            return False
        return True
    try:
        os.remove(log_path())
    except OSError:
        pass
    return True


# ══════════════════════════════════════════════════════════════════════════
#  availability — the one derivation the shop, the guard and /ops all read
# ══════════════════════════════════════════════════════════════════════════
def available(sku, region):
    """Units of one listing on one shard that can be sold right now."""
    if not sku_ok(sku) or not region_ok(region):
        return 0
    if _up():
        try:
            return _int((analytics._upstash(
                [["LLEN", queue_key(sku, region)]]) or [0])[0])
        except (analytics.StoreError, TypeError, ValueError):
            return 0
    return sum(1 for r in _read_file().values()
               if r.get("sku") == sku and r.get("region") == region
               and r.get("status") == AVAILABLE)


def known_pairs():
    """Every "<listing>|<shard>" the store has ever held.

    ⚠ This is the set that makes a ZERO meaningful. A pair in here with no
    units is SOLD OUT; a pair that is not in here has never been stocked and
    still sells on `data.py`'s hand-set figure. Both the checkout guard and the
    client's own `accountStock()` lean on that distinction, and it is why
    `available_map()` reports an explicit 0 rather than omitting the key."""
    if _up():
        try:
            res = analytics._upstash([["SMEMBERS", PAIRS_KEY]])
        except analytics.StoreError:
            return set()
        return set(res[0] or []) if res else set()
    return {"%s|%s" % (r.get("sku"), r.get("region"))
            for r in _read_file().values() if r.get("sku")}


def available_map():
    """{"<listing id>|<shard>": units} for every pair the store has ever held —
    **including the ones that are now at zero**. See `known_pairs()`."""
    pairs = sorted(known_pairs())
    if not pairs:
        return {}
    out = {}
    if _up():
        split = [p.split("|", 1) for p in pairs]
        try:
            res = analytics._upstash([["LLEN", queue_key(s, r)] for s, r in split])
        except analytics.StoreError:
            return {}
        for p, n in zip(pairs, res or []):
            out[p] = _int(n)
        return out
    for p in pairs:
        out[p] = 0
    for r in _read_file().values():
        if r.get("status") != AVAILABLE:
            continue
        k = "%s|%s" % (r.get("sku"), r.get("region"))
        if k in out:
            out[k] = out[k] + 1
    return out


def units_on(region, amap=None):
    amap = available_map() if amap is None else amap
    return sum(v for k, v in amap.items() if k.endswith("|" + region))


def total_available(amap=None):
    amap = available_map() if amap is None else amap
    return sum(amap.values())


def sellable(sku, region):
    """Can this (listing, shard) be sold?

    ⚠ The fallback is per (listing, shard), not store-wide. An operator who has
    loaded EUW but not EUNE has a populated store and no EUNE queue, and reading
    that as "EUNE is sold out" would take four shards off sale to load one. So a
    pair the store has never held falls back to `data.py`'s hand-set figure —
    the behaviour the shop had before this store existed — and a pair it HAS
    held is the store's own answer, which is what makes the last unit the last
    unit."""
    if not sku_ok(sku) or not region_ok(region):
        return False
    if known(sku, region):
        return available(sku, region) > 0
    return D.account_stock(D.account(sku), region) > 0


def known(sku, region):
    """Has this (listing, shard) ever been loaded? A sold-out pair stays known —
    the queue is empty but the pair is still in `PAIRS_KEY`, which is what stops
    the fallback in `sellable()` resurrecting a listing that genuinely ran out."""
    if _up():
        try:
            res = analytics._upstash([["SISMEMBER", PAIRS_KEY, "%s|%s" % (sku, region)]])
            return bool(res and res[0])
        except analytics.StoreError:
            return False
    return "%s|%s" % (sku, region) in known_pairs()


# ══════════════════════════════════════════════════════════════════════════
#  the claim — atomic, and idempotent per order
# ══════════════════════════════════════════════════════════════════════════
def by_order(order_id):
    """The unit already handed to an order, if there is one."""
    order_id = _s(order_id, 40)
    if not order_id:
        return None
    if _up():
        try:
            res = analytics._upstash([["HGET", ORDER_KEY, order_id]])
        except analytics.StoreError:
            return None
        uid = res[0] if res else None
        return get(uid) if uid else None
    for r in _read_file().values():
        if r.get("order_id") == order_id:
            return r
    return None


def claim(sku, region, order_id="", buyer=""):
    """Take one unit off the shelf for a paid order. Returns the row, or None
    when there is nothing left to hand over.

    **Atomic**, because a double-sold account cannot be un-sold: on Upstash the
    id comes off the queue with one `LPOP`, so two webhooks arriving in the same
    millisecond get two different rows or one of them gets nothing.

    **Idempotent**, because Stripe retries: an order that already claimed a unit
    is handed the same row back rather than a second account. `payments`'
    in-memory event de-dupe does not survive a cold start, so this is the guard
    that actually holds in production.
    """
    if not sku_ok(sku) or not region_ok(region):
        return None
    order_id = _s(order_id, 40)
    if order_id:
        prior = by_order(order_id)
        if prior:
            return prior
    now = int(time.time())
    if _up():
        for _ in range(8):          # skip ids whose row has gone missing
            try:
                res = analytics._upstash([["LPOP", queue_key(sku, region)]])
            except analytics.StoreError:
                return None
            uid = res[0] if res else None
            if not uid:
                return None
            row = get(uid)
            if not row:
                continue
            row.update({"status": SOLD, "order_id": order_id, "buyer": _s(buyer),
                        "sold_at": now})
            cmds = [["HSET", LIST_KEY, uid, json.dumps(row, separators=(",", ":"))]]
            if order_id:
                cmds.append(["HSET", ORDER_KEY, order_id, uid])
            try:
                analytics._upstash(cmds)
            except analytics.StoreError:
                # The id is already off the queue; leaving the row unmarked
                # would sell it twice. Report nothing rather than a row we
                # could not record — the ops alert is the fallback.
                sys.stderr.write("[stock] claim write failed for %s\n" % uid)
                return None
            return row
        return None

    store = _read_file()
    pool = sorted((r for r in store.values()
                   if r.get("sku") == sku and r.get("region") == region
                   and r.get("status") == AVAILABLE),
                  key=lambda r: _int(r.get("at")))
    if not pool:
        return None
    row = pool[0]
    row.update({"status": SOLD, "order_id": order_id, "buyer": _s(buyer),
                "sold_at": now})
    store[row["id"]] = row
    _write_file(store)
    return row


def restock(uid):
    """Put a sold or held unit back on the shelf — the undo for a refunded or
    cancelled order. Re-queues the id exactly once."""
    row = get(uid)
    if not row or row.get("status") == AVAILABLE:
        return None
    order_id = row.get("order_id") or ""
    row.update({"status": AVAILABLE, "order_id": "", "buyer": "", "sold_at": 0,
                "mailed": 0, "mail_error": ""})
    if _up():
        cmds = [["HSET", LIST_KEY, row["id"], json.dumps(row, separators=(",", ":"))],
                ["RPUSH", queue_key(row["sku"], row["region"]), row["id"]]]
        if order_id:
            cmds.append(["HDEL", ORDER_KEY, order_id])
        try:
            analytics._upstash(cmds)
        except analytics.StoreError:
            return None
        return row
    store = _read_file()
    store[row["id"]] = row
    _write_file(store)
    return row


def hold(uid):
    """Take a unit off sale without deleting it — a login that failed a check.
    It leaves the queue lazily: `claim()` skips a row whose status is not
    AVAILABLE by re-reading it, so nothing has to surgically remove an id."""
    row = get(uid)
    if not row or row.get("status") != AVAILABLE:
        return None
    return mark(uid, status=HELD)


def purge_sold(older_than_days=400):
    """Delete the credentials of units sold longer ago than the warranty window.

    ⚠ Run this. The store's exposure is "every account we have ever sold" until
    something prunes it, and after the warranty expires there is no reason left
    to hold a login — the order row in `orders.py` still records the sale. The
    row is kept (so the sale is still auditable) and only the secrets are
    blanked."""
    cutoff = int(time.time()) - max(1, _int(older_than_days, 400)) * 86400
    done = 0
    for r in read():
        if r.get("status") != SOLD or not _int(r.get("sold_at")):
            continue
        if _int(r.get("sold_at")) > cutoff or not (r.get("password") or r.get("login")):
            continue
        r.update({"login": "(purged)", "password": "", "email": "",
                  "email_password": "", "purged": int(time.time())})
        put(r)
        done += 1
    return done


def update(uid, fields):
    """Edit one unit's credentials. Returns the row, or None.

    ⚠ Only the credential fields — a status change is `hold()` / `restock()`
    and a removal is `delete()`, because both of those have to move the claim
    queue and this must not. Editing the login also moves it in `LOGIN_KEY`, or
    the old one keeps blocking a re-import and the new one is not protected
    from being added twice.
    """
    row = get(uid)
    if not row:
        return None
    old_login = row.get("login", "")
    out = {}
    for k in ("login", "password", "email", "email_password"):
        if k in fields:
            out[k] = _s(fields[k])
    if "note" in fields:
        out["note"] = _s(fields["note"], MAX_NOTE)
    if not out:
        return row
    if "login" in out and not out["login"]:
        return None                      # a unit with no login is not a unit
    if "password" in out and not out["password"]:
        return None
    row.update(out)
    row["edited"] = int(time.time())
    if not put(row):
        return None
    if _up() and out.get("login") and out["login"] != old_login:
        try:
            analytics._upstash([
                ["SREM", LOGIN_KEY, "%s|%s|%s" % (row["sku"], row["region"], old_login.lower())],
                ["SADD", LOGIN_KEY, _login_key(row)]])
        except analytics.StoreError:
            pass
    return row


def delete(uid):
    """Remove one unit outright. Returns the row it removed, or None.

    Takes the id out of the claim queue as well as the store, so a delete can
    never leave an id that resolves to nothing — `claim()` skips those, but only
    for a bounded number of tries, and enough of them would look like an empty
    shelf on a full one.

    ⚠ **Deleting the LAST row of a pair — of any status — forgets the pair.**
    A slot with nothing in it at all is indistinguishable from one that was
    never stocked, and holding it "known" would pin it at zero: permanently off
    sale, behind a page still advertising it, with no way back except adding
    keys. A *sold* row is what normally keeps a pair known (that is genuinely
    sold out, and it must not fall back to the hand-set figure) — so deleting a
    sold row deletes the evidence of the sale along with the credential, which
    is what the console's confirm dialog warns about. See `known_pairs()` for
    why this distinction is the whole basis of the fallback."""
    row = get(uid)
    if not row:
        return None
    sku, region = row.get("sku", ""), row.get("region", "")
    if _up():
        cmds = [["HDEL", LIST_KEY, uid],
                ["LREM", queue_key(sku, region), 0, uid],
                ["SREM", LOGIN_KEY, _login_key(row)]]
        if row.get("order_id"):
            cmds.append(["HDEL", ORDER_KEY, row["order_id"]])
        try:
            analytics._upstash(cmds)
        except analytics.StoreError:
            return None
    else:
        store = _read_file()
        store.pop(uid, None)
        if not _write_file(store):
            return None
    _forget_if_untouched(sku, region)
    return row


def _forget_if_untouched(sku, region):
    """Drop a (listing, shard) out of `PAIRS_KEY` once no row of it remains at
    all — see the ⚠ on `delete()`."""
    if available(sku, region):
        return False
    for r in read():
        if r.get("sku") == sku and r.get("region") == region:
            return False              # a sold or held row is still a row
    if _up():
        try:
            analytics._upstash([["SREM", PAIRS_KEY, "%s|%s" % (sku, region)]])
        except analytics.StoreError:
            return False
    return True                       # the file store derives pairs from rows


def slot(sku, region):
    """One product on one server: the 44th of the board, opened.

    Everything the console needs to stock and manage that pair — the catalogue
    facts, both counts (what we hold and what the page advertises), and the
    units themselves, **masked**. A password is still one deliberate `reveal()`
    per unit from here."""
    a = D.account(sku)
    if not a or not region_ok(region):
        return None
    rows = [r for r in read()
            if r.get("sku") == sku and r.get("region") == region]
    rows.sort(key=lambda r: (r.get("status") != AVAILABLE, -_int(r.get("at"))))
    n_avail = sum(1 for r in rows if r.get("status") == AVAILABLE)
    return {
        "sku": sku,
        "listing": a["name"],
        "tier": a["tier"],
        "kind": D.account_kind(a),
        "region": region,
        "code": D.account_code(region),
        "known": known(sku, region),
        "available": n_avail,
        "sold": sum(1 for r in rows if r.get("status") == SOLD),
        "held": sum(1 for r in rows if r.get("status") == HELD),
        # What /accounts.html advertises for this pair. Hand-set in data.py and
        # published while PUBLIC_COUNTS is off, which is exactly why the console
        # shows both numbers side by side.
        "shown": D.account_stock(a, region),
        "public_counts": PUBLIC_COUNTS,
        "undelivered": sum(1 for r in rows
                           if r.get("status") == SOLD and not _int(r.get("mailed"))
                           and not _int(r.get("purged"))),
        "rows": [_public_row(r) for r in rows],
    }


def slots():
    """All 44 — every listing on every server, with both counts. The board."""
    amap = available_map()
    pairs = known_pairs()
    sold = [r for r in read() if r.get("status") == SOLD]
    out = []
    for a in D.ACCOUNTS:
        for rg in D.ACCOUNT_REGIONS:
            key = "%s|%s" % (a["id"], rg)
            out.append({
                "sku": a["id"], "listing": a["name"], "tier": a["tier"],
                "kind": D.account_kind(a), "region": rg, "code": D.account_code(rg),
                "known": key in pairs,
                "available": amap.get(key, 0) if key in pairs else None,
                "sold": sum(1 for r in sold
                            if r.get("sku") == a["id"] and r.get("region") == rg),
                "shown": D.account_stock(a, rg),
            })
    return out


def process_import(sku, region, text, note=""):
    """The console's add-keys action: parse `user:pass` lines and store them.

    Returns what the operator needs to see — how many landed, how many were
    already there, and every line that was refused **with its number**, because
    an import of 300 accounts has to say which three to fix."""
    rows, errors = parse_lines(text, sku, region, note=note)
    res = {"added": 0, "duplicate": 0,
           "errors": [{"line": n, "message": m} for n, m in errors]}
    if rows:
        got = add(rows)
        res["added"] = got["added"]
        res["duplicate"] = got["duplicate"]
    return res


def reveal(uid):
    """One unit's full credentials. **The only function that returns a
    password**, and the only caller is the ops console behind its token."""
    row = get(uid)
    if not row:
        return None
    out = dict(row)
    out["listing"] = listing_name(row.get("sku"))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  the handover mail — what the buyer actually paid for
# ══════════════════════════════════════════════════════════════════════════
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _origin():
    try:
        import payments
        return payments.site_origin()
    except Exception:                                          # noqa: BLE001
        return "https://www.esportsboost.com"


def _steps():
    """⚠ The order of these is the warranty's own assumption. `ACCOUNT_DISCLAIMER`
    says changing the email and the password on arrival is what makes a ban
    unlikely rather than impossible, and the confirmation mail already tells the
    buyer the walkthrough is in this one. Do not reorder them so the password
    comes before the inbox: the recovery address is what an original owner would
    use to take the account back."""
    return [
        "Sign in to the account inbox first, with the address and password above.",
        "Change that inbox password, then turn on two-factor on the inbox.",
        "Sign in to the game account and change its email to one of your own.",
        "Change the game account password last, once the email change is confirmed.",
    ]


def _rows(row, order_id, md=None):
    md = md or {}
    out = [("Order", order_id or ""),
           ("Account", listing_name(row.get("sku"))),
           ("Server", row.get("region") or ""),
           ("Login", row.get("login") or ""),
           ("Password", row.get("password") or "")]
    if row.get("email"):
        out.append(("Account inbox", row["email"]))
    if row.get("email_password"):
        out.append(("Inbox password", row["email_password"]))
    if row.get("note"):
        out.append(("Note", row["note"]))
    return [(k, str(v)) for k, v in out if str(v).strip()]


def delivery_text(row, order_id, md=None):
    body = "\n".join("%-16s%s" % (k, v) for k, v in _rows(row, order_id, md))
    steps = "\n".join("  %d. %s" % (i + 1, s) for i, s in enumerate(_steps()))
    return """Here is the account you bought. Everything you need is below.

%s

Secure it before your first game — in this order
%s

Anything actioned on this account inside %d months is replaced free: reply to
this mail with the order number and we will sort it.

Keep this message, or save the details somewhere safe and delete it. Anyone who
can read it can sign in.

The full warranty: %s/accounts.html#faq-warranty
eSports Boost
""" % (body, steps, D.ACCOUNT_WARRANTY_MONTHS, _origin())


def delivery_html(row, order_id, md=None):
    cells = "".join(
        '<tr><td style="padding:7px 16px 7px 0;color:#6b6b76;font-size:13px;'
        'white-space:nowrap;vertical-align:top">%s</td>'
        '<td style="padding:7px 0;color:#16161a;font-size:14px;font-weight:600;'
        'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all">%s</td></tr>'
        % (_esc(k), _esc(v)) for k, v in _rows(row, order_id, md))
    steps = "".join('<li style="margin:0 0 6px">%s</li>' % _esc(s) for s in _steps())
    return """<!doctype html><html><body style="margin:0;padding:24px;background:#f5f5f7;
 font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;
 background:#fff;border-radius:10px;border:1px solid #e4e4ea">
<tr><td style="padding:26px 26px 8px">
  <p style="margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
   color:#ff4a1f;font-weight:700">Your account</p>
  <h1 style="margin:0 0 14px;font-size:20px;color:#16161a">Here are your details.</h1>
  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%%;
   border-top:1px solid #ececf1;border-bottom:1px solid #ececf1;margin:0 0 18px">%s</table>
  <p style="margin:0 0 8px;font-size:14px;font-weight:700;color:#16161a">
   Secure it before your first game — in this order</p>
  <ol style="margin:0 0 18px;padding-left:20px;font-size:14px;line-height:1.55;color:#4a4a55">%s</ol>
  <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">
   Anything actioned on this account inside %d months is replaced free — reply to
   this mail with the order number and we will sort it. Keep this message, or save
   the details somewhere safe and delete it: anyone who can read it can sign in.</p>
  <p style="margin:0 0 22px"><a href="%s/accounts.html#faq-warranty"
   style="display:inline-block;padding:10px 16px;border-radius:6px;background:#ff4a1f;
   color:#fff;text-decoration:none;font-size:14px;font-weight:600">Read the warranty</a></p>
</td></tr>
<tr><td style="padding:14px 26px 22px;border-top:1px solid #ececf1;font-size:12px;color:#8a8a95">
  eSports Boost · <a href="%s" style="color:#8a8a95">esportsboost.com</a>
</td></tr>
</table></body></html>""" % (cells, steps, D.ACCOUNT_WARRANTY_MONTHS,
                             _origin(), _origin())


def deliver(row, buyer, order_id="", md=None):
    """Mail one claimed unit to the buyer. Returns (ok, error).

    ⚠ `redact=True` is load-bearing: `mailer.send()` writes every message into
    the outbox with its body, and this body is a live login. The row still
    lands there — so /ops can prove the handover went out, which is the whole
    point of the outbox — with the credentials replaced by a pointer to the
    unit id. The store already holds them once; it must not hold them twice,
    in a store that is retention-capped rather than purgeable per account.
    """
    import mailer                # lazy: only the fulfilment path sends mail
    if not row:
        return False, "no_unit"
    # No `configured()` guard and no recipient check of our own: `mailer.send()`
    # already answers both — with a `(False, reason)` pair AND an outbox row.
    # Short-circuiting here would degrade quietly instead, and "we had no
    # mailbox" would be indistinguishable from "we never tried" on the one mail
    # where somebody is sitting waiting for it.
    subject = "Your League account%s" % (" — %s" % order_id if order_id else "")
    ok, err = mailer.send(
        buyer, subject, delivery_text(row, order_id, md),
        html=delivery_html(row, order_id, md), kind="account_delivery",
        redact="Account credentials — not stored in the outbox. "
               "See /ops → Stock, unit %s." % row.get("id", ""))
    mark(row["id"], mailed=int(time.time()) if ok else 0, mail_error="" if ok else err)
    return ok, err


# ⚠ A BUSINESS COMMITMENT, and it is one line to remove. When we take money for
# an account we cannot hand over, this mail offers the buyer a refund rather
# than only a wait. `pricing.ACCOUNT_ETA` promised them instant delivery and the
# confirmation they have already read says the credentials are on their way —
# so the alternative to offering the refund is asking somebody to wait an
# unstated length of time for something they were told they already had. Set it
# False if the business would rather handle refunds case by case; the rest of
# the mail stands on its own.
BACKORDER_OFFER_REFUND = True


def _backorder_text(order_id, listing, region, discord):
    return """Your payment went through. One thing about the handover:

Order      %s
Account    %s
Server     %s

This one is being prepared by hand rather than sent automatically, so the
details are not in your inbox yet.

The fastest way to get them
  Join our Discord and send us your order number, %s. We hand the
  details over there:
  %s

You can also just reply to this mail with that order number and we will send
them here instead.%s

eSports Boost
""" % (order_id or "", listing, region, order_id or "your order number", discord,
       ("\n\nIf you would rather not wait, say so in either place and we will "
        "refund\nthe order in full.") if BACKORDER_OFFER_REFUND else "")


def _backorder_html(order_id, listing, region, discord):
    rows = "".join(
        '<tr><td style="padding:6px 16px 6px 0;color:#6b6b76;font-size:13px;'
        'white-space:nowrap">%s</td><td style="padding:6px 0;color:#16161a;'
        'font-size:14px;font-weight:600">%s</td></tr>' % (_esc(k), _esc(v))
        for k, v in (("Order", order_id or ""), ("Account", listing),
                     ("Server", region)) if str(v).strip())
    refund = ('<p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">'
              "If you would rather not wait, say so in either place and we will refund the "
              "order in full.</p>") if BACKORDER_OFFER_REFUND else ""
    return """<!doctype html><html><body style="margin:0;padding:24px;background:#f5f5f7;
 font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;
 background:#fff;border-radius:10px;border:1px solid #e4e4ea">
<tr><td style="padding:26px 26px 8px">
  <p style="margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;
   color:#ff4a1f;font-weight:700">Your account</p>
  <h1 style="margin:0 0 14px;font-size:20px;color:#16161a">One step before we hand it over.</h1>
  <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">
   Your payment went through. This one is being prepared by hand rather than sent
   automatically, so the details are not in your inbox yet.</p>
  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%%;
   border-top:1px solid #ececf1;border-bottom:1px solid #ececf1;margin:0 0 18px">%s</table>
  <p style="margin:0 0 14px;font-size:14px;line-height:1.55;color:#4a4a55">
   <b>The fastest way to get them:</b> join our Discord and send us your order number —
   we hand the details over there.</p>
  <p style="margin:0 0 18px"><a href="%s"
   style="display:inline-block;padding:10px 16px;border-radius:6px;background:#5865f2;
   color:#fff;text-decoration:none;font-size:14px;font-weight:600">Join the Discord</a></p>
  <p style="margin:0 0 18px;font-size:14px;line-height:1.55;color:#4a4a55">
   You can also just reply to this mail with that order number and we will send them
   here instead.</p>
  %s
</td></tr>
<tr><td style="padding:14px 26px 22px;border-top:1px solid #ececf1;font-size:12px;color:#8a8a95">
  eSports Boost
</td></tr>
</table></body></html>""" % (rows, _esc(discord), refund)


def notify_backorder(order_id, sku, region, buyer):
    """Tell the BUYER when their paid account cannot be handed over yet.

    ⚠ This mail exists because the one before it is now wrong. The order
    confirmation has already told them the credentials are on their way to that
    address, and `ACCOUNT_ETA` promised instant — so silence here is not a delay,
    it is a broken promise they are sitting and watching. It names the one place
    a person can actually hand the account over (the Discord), quotes the order
    number they need to give, and offers the reply-by-mail route for somebody
    who does not use Discord.

    It never states a time. Nothing in the system knows when the next unit
    arrives, and a made-up "within 2 hours" would be the second promise broken
    in the same order."""
    import mailer
    if not mailer.valid(buyer or ""):
        return False, "no_recipient"
    discord = getattr(D, "DISCORD_URL", "")
    listing = listing_name(sku)
    ok, err = mailer.send(
        buyer, "About your account — %s" % (order_id or "your order"),
        _backorder_text(order_id, listing, region, discord),
        html=_backorder_html(order_id, listing, region, discord),
        kind="account_backorder")
    if not ok:
        sys.stderr.write("[stock] backorder note to %s failed: %s\n" % (buyer, err))
    return ok, err


def alert_ops(subject, body):
    """Tell a human. Used for the two cases nothing else can resolve: a paid
    order with nothing left to hand over, and a handover whose mail bounced."""
    try:
        import mailer
        # Sent unconditionally, so the attempt lands in the outbox either way —
        # an unconfigured mailbox is exactly when somebody needs to find this
        # afterwards. stderr carries it too, because with no mail going out the
        # server log is the only thing an operator is reading.
        ok, err = mailer.send(mailer.support_addr(), subject, body, kind="stock_alert")
        if not ok:
            sys.stderr.write("[stock] ALERT (%s): %s\n%s\n" % (err, subject, body))
        return ok
    except Exception as e:                                     # noqa: BLE001
        sys.stderr.write("[stock] alert failed: %s\n" % e)
        return False


def fulfil(md, order_id, buyer):
    """The webhook's whole account path: claim one unit and mail it.

    Returns a small dict for the log. **Never raises** — it is called from
    inside the Stripe webhook, where an exception means a non-200, which means
    Stripe redelivers and the order is fulfilled twice.
    """
    sku = _s((md or {}).get("account"), 60)
    region = _s((md or {}).get("region"), 60)
    if not sku_ok(sku):
        return {"ok": False, "reason": "not_an_account"}
    if not region_ok(region):
        region = D.ACCOUNT_REGIONS[0]
    try:
        row = claim(sku, region, order_id=order_id, buyer=buyer)
    except Exception as e:                                     # noqa: BLE001
        sys.stderr.write("[stock] claim failed: %s\n" % e)
        row = None
    if not row:
        # The buyer first — they have just been told by the confirmation that
        # their credentials are on the way, and that is now untrue. They get the
        # Discord, where a person can actually hand the account over.
        try:
            notify_backorder(order_id, sku, region, buyer)
        except Exception as e:                                 # noqa: BLE001
            sys.stderr.write("[stock] backorder note skipped: %s\n" % e)
        alert_ops(
            "STOCK EMPTY — %s is paid and has nothing to hand over" % (order_id or "an order"),
            "A customer has paid for an account and the store had no unit left.\n\n"
            "Order      %s\nAccount    %s\nServer     %s\nCustomer   %s\n\n"
            "They have been mailed and pointed at the Discord with their order\n"
            "number — WATCH FOR THEM THERE. Load stock and hand it over, or refund.\n"
            % (order_id or "", listing_name(sku), region, buyer or ""))
        return {"ok": False, "reason": "out_of_stock"}
    if _int(row.get("mailed")):
        # The claim is idempotent, so a replayed event lands on the row it
        # already handed over — but `deliver()` is not, and a second copy of a
        # customer's password is a second thing to leak. One handover per unit.
        return {"ok": True, "reason": "already_delivered", "unit": row.get("id", "")}
    try:
        ok, err = deliver(row, buyer, order_id, md)
    except Exception as e:                                     # noqa: BLE001
        sys.stderr.write("[stock] delivery failed: %s\n" % e)
        ok, err = False, str(e)
    if not ok:
        alert_ops(
            "DELIVERY FAILED — %s" % (order_id or "an account order"),
            "An account was claimed for a paid order and the handover mail did "
            "not go out.\n\n"
            "Order      %s\nAccount    %s\nServer     %s\nCustomer   %s\n"
            "Unit       %s\nError      %s\n\n"
            "The credentials are in /ops → Stock under that unit id. Send them by "
            "hand.\n"
            % (order_id or "", listing_name(sku), region, buyer or "",
               row.get("id", ""), err))
    return {"ok": ok, "reason": "" if ok else (err or "mail_failed"),
            "unit": row.get("id", "")}


# ══════════════════════════════════════════════════════════════════════════
#  the public read — counts, and never anything else
# ══════════════════════════════════════════════════════════════════════════
def public_counts():
    """What `/api/stock` serves: how many units of each listing are on each
    shard, and the two totals the shop's four stock figures are drawn from.

    ⚠ Counts only. This route is anonymous and public — it must never grow a
    field that names a login, and the row shape is deliberately a flat
    "<listing>|<shard>": n map rather than a list of anything.
    """
    amap = available_map()
    return {
        "units": amap,
        "servers": {rg: units_on(rg, amap) for rg in D.ACCOUNT_REGIONS},
        "total": total_available(amap),
    }


def process_list():
    """GET /api/stock → (status, payload).

    204 in two cases, and the client handles both the same way — it keeps the
    server-rendered `data.py` figures rather than blanking every count on the
    shop: when the store is empty, and when `STOCK_PUBLIC_COUNTS` is not set,
    which is the shipped default. See the ⚠ on `PUBLIC_COUNTS`."""
    if not PUBLIC_COUNTS or not has_data():
        return 204, None
    return 200, public_counts()


# ══════════════════════════════════════════════════════════════════════════
#  /ops — the Stock tab's payload. NEVER carries a password.
# ══════════════════════════════════════════════════════════════════════════
def _public_row(r):
    """One unit as the console lists it. The password is not here and must not
    be added: the list is rendered into a browser and cached in its memory, and
    the tab is read to answer "how much is left", not "what is the login". The
    per-unit reveal is a separate, deliberate click."""
    return {
        "id": r.get("id", ""),
        "sku": r.get("sku", ""),
        "listing": listing_name(r.get("sku")),
        "region": r.get("region", ""),
        "login": _mask(r.get("login", "")),
        "status": r.get("status", ""),
        "at": _int(r.get("at")),
        "order_id": r.get("order_id", ""),
        "buyer": r.get("buyer", ""),
        "sold_at": _int(r.get("sold_at")),
        "mailed": _int(r.get("mailed")),
        "mail_error": r.get("mail_error", ""),
        "purged": _int(r.get("purged")),
        "note": r.get("note", ""),
    }


def _mask(login):
    """Enough of a login to recognise a row, never enough to sign in with."""
    login = str(login or "")
    if len(login) <= 3:
        return login[:1] + "…"
    return login[:3] + "…" + ("" if len(login) < 6 else login[-1:])


def summary(days=30, now=None):
    """The Stock tab: what is on the shelf per (listing, shard), what has sold,
    what failed to send, and the rows."""
    now = _int(now or time.time())
    rows = read()
    since = now - max(1, _int(days, 30)) * 86400
    amap = available_map()

    sold = [r for r in rows if r.get("status") == SOLD]
    sold_window = [r for r in sold if _int(r.get("sold_at")) >= since]
    undelivered = [_public_row(r) for r in sold
                   if not _int(r.get("mailed")) and not _int(r.get("purged"))]

    # ⚠ `None` where the store has never held that pair, a NUMBER (zero
    # included) where it has. The console draws the first as "·" — meaning "this
    # one still sells on data.py's count" — and the second as the figure, so a
    # sold-out tier reads as 0 rather than as "not stocked here". Collapsing the
    # two is the same mistake that used to drop a sold-out pair out of the
    # public map and put it back on sale.
    # EVERY listing on EVERY shard, always — the shop sells 11 products on each
    # of 4 servers and the console is where they are stocked, so all 44 slots
    # have to be visible whether or not anything is in them. Filtering to the
    # ones that already have units made an empty store look like a shop with no
    # products, which is the opposite of what this tab is for.
    pairs = known_pairs()
    by_listing = []
    for a in D.ACCOUNTS:
        per, cat = {}, {}
        for rg in D.ACCOUNT_REGIONS:
            key = "%s|%s" % (a["id"], rg)
            per[rg] = amap.get(key, 0) if key in pairs else None
            # What the PAGE currently claims for this pair. It is `data.py`'s
            # hand-set figure and it is what a visitor reads, because publishing
            # the real counts is off (see PUBLIC_COUNTS) — so the console is the
            # only place the two can be compared, and that comparison is the
            # whole reason this column exists.
            cat[rg] = D.account_stock(a, rg)
        total = sum(v for v in per.values() if v)
        # Sold PER SHARD as well as in total: the console is organised by
        # server, and one number covering all four in a table headed "Europe
        # West" is a figure about somewhere else.
        sold_by = {rg: sum(1 for r in sold if r.get("sku") == a["id"]
                           and r.get("region") == rg)
                   for rg in D.ACCOUNT_REGIONS}
        by_listing.append({"sku": a["id"], "listing": a["name"], "tier": a["tier"],
                           "kind": D.account_kind(a),
                           "available": total, "sold": sum(sold_by.values()),
                           "sold_by": sold_by, "servers": per,
                           "shown": cat, "shown_total": sum(cat.values()),
                           "catalogue": int(a.get("stock") or 0)})

    return {
        "store": store_name(),
        "total": len(rows),
        "available": total_available(amap),
        "sold": len(sold),
        "sold_window": len(sold_window),
        "held": sum(1 for r in rows if r.get("status") == HELD),
        "undelivered": undelivered,
        "servers": [{"region": rg, "code": D.account_code(rg),
                     "available": units_on(rg, amap),
                     "sold": sum(1 for r in sold if r.get("region") == rg),
                     "shown": D.account_units_on(rg)} for rg in D.ACCOUNT_REGIONS],
        # Off unless STOCK_PUBLIC_COUNTS=1 — the console says which of the two
        # columns below the shop is actually quoting.
        "public_counts": PUBLIC_COUNTS,
        "products": len(D.ACCOUNTS),
        "shards": len(D.ACCOUNT_REGIONS),
        "listings": by_listing,
        "rows": [_public_row(r) for r in rows[:400]],
        "days": days,
    }
