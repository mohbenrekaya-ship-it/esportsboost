# -*- coding: utf-8 -*-
"""The orders store behind the /ops "Orders" tab.

The **fourth sibling** of `analytics.py`, `accounts.py` and `boosters.py`: same
house rules (stdlib only, no build step, Upstash Redis in prod / an NDJSON file
in dev), same **separate store** (`esb:orders` / `orders.ndjson`, never another
store's key), reusing only analytics' Upstash *transport*.

Where it differs from its siblings:

  * **Write is operator/fulfilment-only, read is gated.** There is no public read
    (a customer's order is not public data) and no public write. Two writers fill
    it: the Stripe webhook (`payments.process_webhook`) appends a real fulfilled
    order, and `tools/seed_orders.py` fills it with placeholder orders for the
    preview. The only reader is the password-gated `/ops` console.
  * **It holds PII** (a customer email, a country), like `accounts.py` — so the
    `/ops` payload is fetched on demand rather than bundled into every dashboard
    refresh, and the console shows a standing "not real orders" banner while any
    seeded row is present.

An order row is the whole configuration the buyer paid for: the game, the climb
(from → to) or the unit/coaching product, the queue mode, the add-ons chosen, the
region, the named booster, the country the order came from, the currency it was
charged in, and the price breakdown. `detail()` re-quotes the stored config with
`pricing.quote()` so the drill-down can show a per-add-on cost breakdown that adds
up, exactly the way the checkout summary does — the store keeps the figures that
were charged, and the breakdown is derived on read.

Still placeholder data until launch: the seeded orders are invented (the same
invented roster and ladders the rest of the site carries — see the warning at the
top of `data.py`). Seeded rows carry `syn: 1`; clear the store and let only real
webhook fulfilments write to it before the site takes real traffic.
"""
import json
import os
import re
import time

import analytics   # Upstash transport + store selection only — never its data
import data as D
import pricing

# ── limits ────────────────────────────────────────────────────────────────
MAX_ORDERS = int(os.environ.get("ORDERS_MAX", "5000") or 5000)
MAX_STR = 120
MAX_ADDONS = 8
RECENT_CAP = 500

LIST_KEY = "esb:orders"
ID_KEY = "esb:orders:ids"     # mirrors order ids for O(1) de-dupe on Upstash

ORDER_ID_RE = re.compile(r"^ESB-[A-Z0-9]{3,12}$")

# The valid lifecycle a fulfilled order moves through. `unclaimed` and `refunded`
# are the two non-happy states the guarantee page promises to honour.
STATUSES = ("paid", "assigned", "in_progress", "delivered", "unclaimed", "refunded")

_BY_SLUG = {g["slug"]: g for g in D.GAMES}
_BY_NAME = {g["name"]: g for g in D.GAMES}
_ADDON_BY_ID = {a["id"]: a for a in D.ADDONS}


# ══════════════════════════════════════════════════════════════════════════
#  store — mirrors boosters.append/read/clear/count against a separate key
# ══════════════════════════════════════════════════════════════════════════
def _s(v, n=MAX_STR):
    return analytics._CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def _game_of(row):
    return _BY_SLUG.get(row.get("slug")) or _BY_NAME.get(row.get("game"))


def clean_order(row):
    """Validate one order into a stored record, or None.

    Requires an order id and a real game. Everything else is coerced into range —
    a stored order is a receipt, not a live quote, so we keep what was charged and
    never re-derive it here.
    """
    if not isinstance(row, dict):
        return None
    oid = _s(row.get("order_id"), 16).upper()
    if not ORDER_ID_RE.match(oid):
        return None
    g = _game_of(row)
    if not g:
        return None

    service = _s(row.get("service"), 16) or "division"
    if service not in ("division", "wins", "placements", "coaching"):
        service = "division"

    status = _s(row.get("status"), 16) or "paid"
    if status not in STATUSES:
        status = "paid"

    addons = []
    for a in (row.get("addons") or [])[:MAX_ADDONS]:
        aid = _s(a, 24)
        if aid in _ADDON_BY_ID and aid not in addons:
            addons.append(aid)

    out = {
        "order_id": oid,
        "at": _int(row.get("at"), int(time.time())),
        "status": status,
        "game": g["name"], "slug": g["slug"],
        "service": service,
        "mode": _s(row.get("mode"), 20) or "Piloted",
        "region": _s(row.get("region")),
        "country": _s(row.get("country"), 4).upper(),
        "cosrc": _s(row.get("cosrc"), 16),
        "currency": (_s(row.get("currency"), 6) or "usd").lower(),
        "booster": _s(row.get("booster"), 40),
        "promo": _s(row.get("promo"), 40),
        "eta": _s(row.get("eta"), 40),
        "email": _s(row.get("email"), 160),
        "notes": _s(row.get("notes"), MAX_STR),
        "addons": addons,
        "subtotal": _int(row.get("subtotal")),
        "discount": _int(row.get("discount")),
        "total": _int(row.get("total")),
    }
    # Product-specific configuration.
    if service in ("division",):
        out["from_rank"] = _s(row.get("from_rank") or row.get("from"), 40)
        out["to_rank"] = _s(row.get("to_rank") or row.get("to"), 40)
    elif service in ("wins", "placements"):
        out["from_rank"] = _s(row.get("from_rank") or row.get("from"), 40)
        out["units"] = max(pricing.UNIT_MIN, min(pricing.UNIT_MAX,
                                                  _int(row.get("units"), pricing.UNIT_MIN)))
        if row.get("unranked"):
            out["unranked"] = 1
    elif service == "coaching":
        out["coach"] = _s(row.get("coach"), 40)
        out["hours"] = max(1, _int(row.get("hours"), 1))

    if row.get("syn") in (1, True):
        out["syn"] = 1
    return out


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def log_path():
    return os.environ.get("ORDERS_STORE", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "orders.ndjson")


def _file_ids():
    return {r.get("order_id") for r in read() if r.get("order_id")}


def append(rows):
    """Persist cleaned order rows, **one row per order id**. Returns the number of
    NEW rows written; a row whose id is already stored is dropped. Never raises —
    a fulfilment write must never take down the webhook."""
    if not rows:
        return 0
    cleaned = [c for c in (clean_order(r) for r in rows) if c]
    if not cleaned:
        return 0
    up = analytics.upstash_config()[0]
    seen, new = set(), []
    if up:
        for r in cleaned:
            oid = r["order_id"]
            if oid in seen:
                continue
            try:
                res = analytics._upstash([["SISMEMBER", ID_KEY, oid]])
                if res and res[0]:
                    continue
            except analytics.StoreError:
                pass
            seen.add(oid)
            new.append(r)
    else:
        existing = _file_ids()
        for r in cleaned:
            oid = r["order_id"]
            if oid in seen or oid in existing:
                continue
            seen.add(oid)
            new.append(r)

    if not new:
        return 0
    lines = [json.dumps(r, separators=(",", ":")) for r in new]
    if up:
        try:
            cmds = [["LPUSH", LIST_KEY] + lines,
                    ["LTRIM", LIST_KEY, 0, MAX_ORDERS - 1]]
            cmds += [["SADD", ID_KEY, r["order_id"]] for r in new]
            analytics._upstash(cmds)
            return len(lines)
        except analytics.StoreError:
            return 0
    try:
        with open(log_path(), "a") as f:
            f.write("\n".join(lines) + "\n")
        return len(lines)
    except OSError:
        return 0


def read(limit=MAX_ORDERS):
    """Return up to `limit` stored orders, newest first."""
    limit = max(1, min(_int(limit, MAX_ORDERS), MAX_ORDERS))
    if analytics.upstash_config()[0]:
        try:
            res = analytics._upstash([["LRANGE", LIST_KEY, 0, limit - 1]])
        except analytics.StoreError:
            return []
        rows = res[0] if res else []
    else:
        try:
            with open(log_path()) as f:
                rows = f.read().splitlines()
        except OSError:
            return []
        rows = rows[-limit:][::-1]
    out = []
    for row in rows or []:
        try:
            r = json.loads(row)
        except (ValueError, TypeError):
            continue
        if isinstance(r, dict) and r.get("order_id"):
            out.append(r)
    return out


def clear():
    """Wipe the orders store. Used by the seeder; never exposed over HTTP."""
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["DEL", LIST_KEY], ["DEL", ID_KEY]])
        except analytics.StoreError:
            return False
        return True
    try:
        os.remove(log_path())
    except OSError:
        pass
    return True


def count():
    if analytics.upstash_config()[0]:
        try:
            return int((analytics._upstash([["LLEN", LIST_KEY]]) or [0])[0] or 0)
        except (analytics.StoreError, TypeError, ValueError):
            return 0
    try:
        with open(log_path()) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def has_data():
    return count() > 0


# ══════════════════════════════════════════════════════════════════════════
#  presentation helpers
# ══════════════════════════════════════════════════════════════════════════
def _climb_summary(row):
    """One human line for the order's product — the same shape the checkout and
    the closing band draw, so an operator reads it the way the buyer saw it."""
    svc = row.get("service")
    if svc == "coaching":
        h = _int(row.get("hours"), 1)
        return "%d hour%s coaching%s" % (h, "" if h == 1 else "s",
                                         " · " + row["coach"] if row.get("coach") else "")
    if svc in ("wins", "placements"):
        n = _int(row.get("units"), 1)
        where = "Unranked" if row.get("unranked") else (row.get("from_rank") or "")
        word = ("net win" if svc == "wins" else "placement") + ("" if n == 1 else "s")
        return "%d %s%s" % (n, word, " · " + where if where else "")
    frm, to = row.get("from_rank", ""), row.get("to_rank", "")
    if frm and to:
        return "%s → %s" % (frm, to)
    return frm or to or "—"


def _order_state(row):
    """Rebuild the pricing.quote() input dict from a stored order, so detail() can
    re-derive the per-add-on cost breakdown the same way the checkout page does."""
    st = {
        "game": row.get("game"),
        "service": row.get("service", "division"),
        "mode": row.get("mode", "Piloted"),
        "addons": list(row.get("addons") or []),
        "promo": row.get("promo") or "",
    }
    svc = st["service"]
    if svc == "division":
        st["from"], st["to"] = row.get("from_rank"), row.get("to_rank")
    elif svc == "wins":
        st["from"], st["wins"] = row.get("from_rank"), _int(row.get("units"), 1)
    elif svc == "placements":
        st["from"], st["placements"] = row.get("from_rank"), _int(row.get("units"), 1)
        if row.get("unranked"):
            st["unranked"] = True
    elif svc == "coaching":
        st["coach"] = 0
        # map stored coach name/hours back to indices for the quote
        for i, c in enumerate(D.COACHES):
            if c["name"] == row.get("coach") or c["handle"] == row.get("coach"):
                st["coach"] = i
                break
        for i, p in enumerate(D.COACH_PACKS):
            if p["hours"] == _int(row.get("hours"), 1):
                st["pack"] = i
                break
    return st


def _addon_breakdown(row):
    """Per-add-on marginal cost on this order — quoted as the difference the
    add-on makes to the total, the same trick the checkout's `data-addon-price`
    uses. Returns a list of {id, label, pct, cost}."""
    ids = list(row.get("addons") or [])
    if not ids:
        return []
    base_state = _order_state(row)
    with_all = pricing.quote(dict(base_state, addons=ids))
    if with_all.get("invalid"):
        return [{"id": i, "label": _ADDON_BY_ID.get(i, {}).get("label", i),
                 "pct": _ADDON_BY_ID.get(i, {}).get("pct", 0), "cost": None} for i in ids]
    out = []
    for aid in ids:
        without = pricing.quote(dict(base_state, addons=[x for x in ids if x != aid]))
        cost = with_all["total"] - without["total"] if not without.get("invalid") else None
        meta = _ADDON_BY_ID.get(aid, {})
        out.append({"id": aid, "label": meta.get("label", aid),
                    "pct": meta.get("pct", 0), "cost": cost})
    return out


def _short(row):
    g = _game_of(row)
    return g["short"] if g else (row.get("slug") or "??")


# ══════════════════════════════════════════════════════════════════════════
#  aggregation — what the /ops Orders tab reads (password-gated)
# ══════════════════════════════════════════════════════════════════════════
def summary(days=30):
    """The Orders panel's list payload: totals, revenue, splits by status and by
    game, and a recent list (one compact row per order). Detail is fetched
    separately, on click, exactly as a session timeline is."""
    days = max(1, min(_int(days, 30), 365))
    cutoff = int(time.time()) - days * 86400
    rows = [r for r in read() if _int(r.get("at")) >= cutoff]

    total = len(rows)
    revenue = sum(_int(r.get("total")) for r in rows if r.get("status") != "refunded")
    refunded = sum(1 for r in rows if r.get("status") == "refunded")
    synthetic = sum(1 for r in rows if r.get("syn"))
    aov = round(revenue / max(1, total - refunded)) if total else 0

    by_status = {}
    for s in STATUSES:
        by_status[s] = 0
    for r in rows:
        by_status[r.get("status", "paid")] = by_status.get(r.get("status", "paid"), 0) + 1

    by_game = {}
    for r in rows:
        key = _short(r)
        s = by_game.setdefault(key, {"game": key, "count": 0, "revenue": 0})
        s["count"] += 1
        if r.get("status") != "refunded":
            s["revenue"] += _int(r.get("total"))
    games = sorted(by_game.values(), key=lambda x: (-x["revenue"], -x["count"]))

    recent = []
    for r in sorted(rows, key=lambda r: -_int(r.get("at")))[:RECENT_CAP]:
        recent.append({
            "order_id": r.get("order_id", ""),
            "at": _int(r.get("at")),
            "status": r.get("status", "paid"),
            "game": _short(r),
            "service": r.get("service", "division"),
            "summary": _climb_summary(r),
            "mode": r.get("mode", ""),
            "booster": r.get("booster", ""),
            "region": r.get("region", ""),
            "country": r.get("country", ""),
            "currency": r.get("currency", "usd"),
            "total": _int(r.get("total")),
            "syn": 1 if r.get("syn") else 0,
        })

    return {
        "total": total, "revenue": revenue, "aov": aov, "refunded": refunded,
        "synthetic": synthetic, "days": days,
        "statuses": [{"status": s, "count": by_status.get(s, 0)} for s in STATUSES],
        "games": games, "recent": recent,
        "store": analytics.store_name(),
    }


def detail(order_id):
    """One order, everything: the full stored record plus a derived add-on cost
    breakdown and a resolved product line. Returns None if the id is unknown."""
    oid = _s(order_id, 16).upper()
    if not ORDER_ID_RE.match(oid):
        return None
    row = next((r for r in read() if r.get("order_id", "").upper() == oid), None)
    if not row:
        return None
    g = _game_of(row)
    return {
        "order_id": row.get("order_id"),
        "at": _int(row.get("at")),
        "status": row.get("status", "paid"),
        "game": row.get("game", ""),
        "gameShort": _short(row),
        "slug": row.get("slug", ""),
        "service": row.get("service", "division"),
        "summary": _climb_summary(row),
        "from_rank": row.get("from_rank", ""),
        "to_rank": row.get("to_rank", ""),
        "units": _int(row.get("units")) or None,
        "unranked": 1 if row.get("unranked") else 0,
        "coach": row.get("coach", ""),
        "hours": _int(row.get("hours")) or None,
        "mode": row.get("mode", ""),
        "region": row.get("region", ""),
        "country": row.get("country", ""),
        "cosrc": row.get("cosrc", ""),
        "rankUnit": (g or {}).get("rank_unit", "LP"),
        "queueName": (g or {}).get("queue_name", "Ranked"),
        "currency": row.get("currency", "usd"),
        "booster": row.get("booster", ""),
        "promo": row.get("promo", ""),
        "eta": row.get("eta", ""),
        "email": row.get("email", ""),
        "notes": row.get("notes", ""),
        "addons": _addon_breakdown(row),
        "subtotal": _int(row.get("subtotal")),
        "discount": _int(row.get("discount")),
        "total": _int(row.get("total")),
        "syn": 1 if row.get("syn") else 0,
        "store": analytics.store_name(),
    }
