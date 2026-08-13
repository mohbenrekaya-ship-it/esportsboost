# -*- coding: utf-8 -*-
"""The roster store behind the boosters page, the "On shift now" rail and the
homepage "Delivered today" feed.

Until now the roster was baked into the HTML at build time from `data.py`'s
`BOOSTERS` list: correct, but frozen — every visitor saw the same table, the same
five faces on the rail and the same four deliveries in the feed, and adding a
booster meant a rebuild. This module puts that same data in a backend store —
the **third sibling** of `analytics.py` and `accounts.py`, same house rules
(stdlib only, no build step, Upstash Redis in prod / an NDJSON file in dev) — and
serves it live through a public read endpoint so those three panels can vary
between loads and pick up a store change without a rebuild.

Load-bearing rules, in the spirit of its two siblings:

  * **It is a SEPARATE store, and must stay one.** `esb:boosters` /
    `boosters.ndjson`, never analytics' `esb:ev` or accounts' `esb:accounts`.
    It reuses analytics' Upstash *transport* (`_upstash`) and store selection
    only — never another store's data.
  * **The write path is operator-only.** Unlike `/api/collect` and
    `/api/account`, there is no public write: boosters are staff records, not
    visitor submissions. The store is filled by `tools/seed_boosters.py` (and, in
    time, an admin flow); the only thing the site exposes is the **public read**
    `GET /api/boosters`, which is anonymous, holds no PII and carries no secret.
  * **The catalogue stays in `data.py`.** Tier colours, a game's short code and
    its ladder are catalogue facts, not per-person facts, so the store holds only
    the booster's own fields and this module *joins* them against `D.GAMES` when
    it builds the display payload. That keeps one source for a game's colour — the
    same `D.tier_color()` every rank mark on the site is drawn from.
  * **Still placeholder data.** Every seeded booster is invented (see the warning
    at the top of `data.py`), and the derived feed is not a record of real
    deliveries. Seeded rows carry `syn: 1`, the public payload reports whether any
    are present (`syn`), and the `/ops` Boosters tab shows a standing banner. Wire
    this to the real roster and clear the store before launch.

The public payload is built fresh on every request and **rotates on a short time
bucket**, so the rail and the feed are "live" rather than a fixed snapshot, while
staying deterministic within a bucket (two requests in the same few seconds
agree). Nothing here is a real-time event stream: the feed is *derived* from the
roster and the real ladders/pricing, the same sanctioned trick `demo_order()` and
`booster_history()` use for the dashboard mock — never a log of orders that
happened.
"""
import json
import math
import os
import random
import time

import analytics   # Upstash transport + store selection only — never its data
import data as D

# ── limits ────────────────────────────────────────────────────────────────
MAX_ROSTER = int(os.environ.get("BOOSTERS_MAX", "2000") or 2000)
MAX_HANDLE = 40
MAX_STR = 80

LIST_KEY = "esb:boosters"
# Mirrors the handles already in LIST_KEY so uniqueness is O(1) on Upstash
# (SISMEMBER), exactly as accounts.py mirrors emails. One handle, one row.
HANDLE_KEY = "esb:boosters:handles"

WR_TOP = 85     # top of the win-rate bar's span; its zero is D.WR_FLOOR. Kept in
                # step with build.py's WR_TOP — the bar reads the same two numbers.
ROTATE_SECS = 15    # how often the rail/feed selection turns over

# The fields a stored booster row may carry. Anything else a caller passes is
# dropped — the store is not a free-form bucket.
_STR_FIELDS = ("handle", "slug", "region", "peak", "peak_full", "tier",
               "queue", "wr", "role", "since", "rating", "ontime", "disputes")
_NUM_FIELDS = ("wr_n", "orders", "hue")


# ══════════════════════════════════════════════════════════════════════════
#  catalogue join — game facts live in data.py, not in the store
# ══════════════════════════════════════════════════════════════════════════
_BY_SLUG = {g["slug"]: g for g in D.GAMES}


def _game(row):
    return _BY_SLUG.get(row.get("slug"))


def _has_divisions(g):
    """True when the ladder has sub-ranks (Gold IV/III/…), so a climb reads as
    a division numeral + tier. Flat rating ladders (CS2's Premier numbers) are
    left out of the derived feed rather than drawn with a made-up format."""
    return any(len(subs) > 1 for subs in g["divmap"].values())


def _rung(g, rung):
    """Split a ladder entry ("Gold IV") into (tier, division, colour). An apex
    rung ("Master") has no division. Colour is the catalogue's own tier tint."""
    for tier, subs in g["divmap"].items():
        if rung in subs:
            div = rung[len(tier):].strip()
            return tier, div, D.tier_color(g, tier)
    return rung, "", D.tier_color(g, rung)


def _wr_pct(wr_n):
    span = max(1, WR_TOP - D.WR_FLOOR)
    frac = (int(wr_n or 0) - D.WR_FLOOR) / span
    return max(6, min(100, round(frac * 100)))


# ══════════════════════════════════════════════════════════════════════════
#  store — mirrors accounts.append/read/clear/count against a separate key
# ══════════════════════════════════════════════════════════════════════════
def _s(v, n):
    return analytics._CTRL_RE.sub("", str(v if v is not None else "")).strip()[:n]


def clean_booster(row):
    """Validate one booster into a stored record, or None.

    Enforces what the roster page argues out loud: a real game slug, a unique
    handle, and a win rate at or above the floor `WR_FLOOR` the hero states — a
    row under it would contradict the headline three inches above the table, the
    same reason `data.py` asserts it at import.
    """
    if not isinstance(row, dict):
        return None
    handle = _s(row.get("handle"), MAX_HANDLE).lower()
    slug = _s(row.get("slug"), MAX_STR)
    if not handle or slug not in _BY_SLUG:
        return None
    try:
        wr_n = int(row.get("wr_n"))
    except (TypeError, ValueError):
        return None
    if wr_n < D.WR_FLOOR or wr_n > 100:
        return None

    out = {"handle": handle, "slug": slug, "wr_n": wr_n}
    for k in _STR_FIELDS:
        if k in ("handle", "slug"):
            continue
        v = _s(row.get(k), MAX_STR)
        if v:
            out[k] = v
    for k in ("orders", "hue"):
        try:
            out[k] = int(row.get(k))
        except (TypeError, ValueError):
            pass
    out.setdefault("queue", "free")
    out.setdefault("wr", "%d%%" % wr_n)
    out.setdefault("peak", "")
    g = _BY_SLUG[slug]
    out.setdefault("region", "")
    out.setdefault("peak_full", ("%s · %s" % (out["peak"], out["region"])).strip(" ·"))
    out.setdefault("tier", out["peak"].split()[0] if out["peak"] else g["tiers"][-1])
    if row.get("syn") in (1, True):
        out["syn"] = 1
    return out


def _file_handles():
    return {r.get("handle") for r in read() if r.get("handle")}


def append(rows):
    """Persist cleaned booster rows, **one row per handle**. Returns the number
    of NEW rows written; a row whose handle is already stored is dropped, and
    duplicates inside one batch collapse to the first. Never raises."""
    if not rows:
        return 0
    up = analytics.upstash_config()[0]
    seen, new = set(), []
    if up:
        for r in rows:
            h = r.get("handle")
            if not h or h in seen:
                continue
            try:
                res = analytics._upstash([["SISMEMBER", HANDLE_KEY, h]])
                if res and res[0]:
                    continue
            except analytics.StoreError:
                pass
            seen.add(h)
            new.append(r)
    else:
        existing = _file_handles()
        for r in rows:
            h = r.get("handle")
            if not h or h in seen or h in existing:
                continue
            seen.add(h)
            new.append(r)

    if not new:
        return 0
    lines = [json.dumps(r, separators=(",", ":")) for r in new]
    if up:
        try:
            cmds = [["LPUSH", LIST_KEY] + lines,
                    ["LTRIM", LIST_KEY, 0, MAX_ROSTER - 1]]
            cmds += [["SADD", HANDLE_KEY, r["handle"]] for r in new]
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


def log_path():
    return os.environ.get("BOOSTERS_LOG", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "boosters.ndjson")


def read(limit=MAX_ROSTER):
    """Return up to `limit` stored boosters."""
    limit = max(1, min(int(limit or MAX_ROSTER), MAX_ROSTER))
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
        if isinstance(r, dict) and r.get("handle") and r.get("slug") in _BY_SLUG:
            out.append(r)
    return out


def clear():
    """Wipe the roster store. Used by the seeder; never exposed over HTTP."""
    if analytics.upstash_config()[0]:
        try:
            analytics._upstash([["DEL", LIST_KEY], ["DEL", HANDLE_KEY]])
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
    """Is the store populated? The public endpoint answers 204 when it is empty,
    so the client keeps the server-rendered (data.py) fallback rather than
    blanking the roster."""
    return count() > 0


# ══════════════════════════════════════════════════════════════════════════
#  display payload — what /api/boosters serves (public, anonymous)
# ══════════════════════════════════════════════════════════════════════════
def _row_fields(row):
    """One booster as the roster board and rail need it: every derived display
    value (mark colour, bar %, hire link) computed here so the client renderer
    stays dumb and can never tint a rank differently than the server would."""
    g = _game(row)
    short = g["short"] if g else ""
    tier = row.get("tier") or (g["tiers"][-1] if g else "")
    color = D.tier_color(g, tier) if g else "#8e8f94"
    handle = row["handle"]
    wr_n = int(row.get("wr_n") or 0)
    _face_tint = D.face_tint(handle, row.get("hue"))
    return {
        "handle": handle,
        "slug": row.get("slug", ""),
        "gameShort": short,
        "gameName": g["name"] if g else row.get("slug", ""),
        "region": row.get("region", ""),
        "peak": row.get("peak", ""),
        "peakFull": row.get("peak_full") or ("%s · %s" % (row.get("peak", ""), row.get("region", ""))).strip(" ·"),
        "tier": tier,
        "markLabel": (tier[:2].upper() if tier else "?"),
        "markColor": color,
        "wr": row.get("wr") or ("%d%%" % wr_n),
        "wrN": wr_n,
        "wrPct": _wr_pct(wr_n),
        "orders": int(row.get("orders") or 0),
        "queue": row.get("queue", "free"),
        "free": row.get("queue") == "free",
        "initial": handle[:1].upper(),
        # The avatar's glyph and its two colours are resolved here, the same way
        # markColor is: the client renderer stays dumb and can never draw a
        # booster a different face than the server-rendered row it replaces.
        "face": D.face_glyph(handle),
        "faceInk": _face_tint[0],
        "facePlate": _face_tint[1],
        "href": "/boosters/%s.html" % handle,
        "hire": ("/games/%s.html?booster=%s" % (row["slug"], handle)) if g else "/games/",
    }


def _derive_feed(rows, bucket, n=4):
    """A rotating "Delivered today" set, DERIVED from the roster — never a log of
    real orders. Picks a handful of boosters for this time bucket and gives each
    a plausible climb on their own game's ladder, so every entry is a job the
    shop could actually sell. Deterministic within a bucket; different across
    them, which is what makes the feed vary between loads."""
    pool = [r for r in rows if _game(r) and _has_divisions(_game(r))]
    if not pool:
        return []
    rng = random.Random(("feed", bucket))
    rng.shuffle(pool)
    out = []
    for b in pool[:n]:
        g = _game(b)
        ladder = list(g["ladder"])
        r2 = random.Random(("climb", b["handle"], bucket))
        j = r2.randint(min(3, len(ladder) - 1), len(ladder) - 1)
        i = max(0, j - r2.randint(1, 3))
        ft, fd, fc = _rung(g, ladder[i])
        tt, td, tc = _rung(g, ladder[j])
        out.append({
            "slug": b["slug"], "gameName": g["name"], "gameShort": g["short"],
            "region": b.get("region", ""), "booster": b["handle"],
            "mins": r2.randint(2, 220),
            "frm": {"tier": ft, "label": fd or ft[:2].upper(), "color": fc},
            "to": {"tier": tt, "label": td or tt[:2].upper(), "color": tc},
        })
    out.sort(key=lambda e: e["mins"])       # newest (smallest) first
    return out


def _derive_shift(rows, bucket, n=5):
    """The rail's rotating selection — free boosters first (the thing a buyer
    acts on), shuffled within the bucket, busy rows only to fill the count."""
    rng = random.Random(("shift", bucket))
    free = [r for r in rows if r.get("queue") == "free"]
    busy = [r for r in rows if r.get("queue") != "free"]
    rng.shuffle(free)
    rng.shuffle(busy)
    return [_row_fields(b) for b in (free + busy)[:n]]


def _closed_24h(rows, now):
    """A rolling "orders closed in the last 24 hours" figure, DERIVED from the
    board so it moves like a real counter instead of sitting frozen at one typed
    number. It is deliberately *not* per-reload noise: the base scales with the
    roster size, a time-of-day curve lifts the evening, and the only wobble turns
    over on a coarse bucket (`CLOSED_BUCKET`), so within a couple of minutes two
    reloads agree and across an hour it drifts. Still a placeholder — the store
    is seeded (`syn`), and a real figure has to come from the orders table."""
    n = len(rows)
    if not n:
        return 0
    base = n * 0.82                                   # ~ deliveries/day per booster on the board
    hour = time.gmtime(now).tm_hour + time.gmtime(now).tm_min / 60.0
    tod = 1.0 + 0.14 * math.sin((hour / 24.0) * 2 * math.pi - 1.6)   # busier evenings
    wob = random.Random(("closed", now // CLOSED_BUCKET)).uniform(-3, 5)
    return max(1, round(base * tod + wob))


CLOSED_BUCKET = 150     # the rolling count drifts on this bucket (2.5 min), not per reload


def public_payload(now=None):
    """The `GET /api/boosters` body. Fresh per request, rotating on ROTATE_SECS.

    Returns the whole board (sorted by win rate, as the server-rendered table
    is), a rotating rail selection, a rotating derived feed, and the counts the
    three panels quote — plus `syn` when any stored row is seeded.
    """
    now = int(now or time.time())
    bucket = now // ROTATE_SECS
    rows = read()
    board = [_row_fields(b) for b in sorted(rows, key=lambda b: -int(b.get("wr_n") or 0))]
    free_now = sum(1 for b in rows if b.get("queue") == "free")
    return {
        "boosters": board,
        "shift": _derive_shift(rows, bucket),
        "feed": _derive_feed(rows, bucket),
        "stats": {
            "online": len(rows),
            "free_now": free_now,
            "closed_24h": _closed_24h(rows, now),
        },
        "syn": any(b.get("syn") for b in rows),
        "store": analytics.store_name(),
    }


# ══════════════════════════════════════════════════════════════════════════
#  ingest — the public read endpoint (serve.py + api/boosters.py share this)
# ══════════════════════════════════════════════════════════════════════════
def process_list():
    """GET /api/boosters → (status, payload).

    204 (no body) when the store is empty, so the client falls back to the
    server-rendered roster rather than blanking it. 200 with the payload
    otherwise.
    """
    if not has_data():
        return 204, None
    return 200, public_payload()


# ══════════════════════════════════════════════════════════════════════════
#  aggregation — what the /ops Boosters tab reads (password-gated)
# ══════════════════════════════════════════════════════════════════════════
RECENT_CAP = 400


def summary():
    """The Boosters panel's payload: totals, a free/busy split, a per-game
    breakdown and the rows themselves (capped)."""
    rows = read()
    total = len(rows)
    free = sum(1 for b in rows if b.get("queue") == "free")
    synthetic = sum(1 for b in rows if b.get("syn"))

    by_game = {}
    for b in rows:
        g = _game(b)
        key = g["short"] if g else (b.get("slug") or "??")
        s = by_game.setdefault(key, {"game": key, "count": 0, "free": 0})
        s["count"] += 1
        if b.get("queue") == "free":
            s["free"] += 1
    games = sorted(by_game.values(), key=lambda x: (-x["count"], x["game"]))

    recent = []
    ranked = sorted(rows, key=lambda b: -int(b.get("wr_n") or 0))[:RECENT_CAP]
    for b in ranked:
        g = _game(b)
        recent.append({
            "handle": b.get("handle", ""),
            "game": g["short"] if g else b.get("slug", ""),
            "region": b.get("region", ""),
            "peak": b.get("peak", ""),
            "wr": b.get("wr") or ("%d%%" % int(b.get("wr_n") or 0)),
            "wr_n": int(b.get("wr_n") or 0),
            "orders": int(b.get("orders") or 0),
            "queue": b.get("queue", ""),
            "free": b.get("queue") == "free",
            "syn": 1 if b.get("syn") else 0,
        })

    return {
        "total": total, "free": free, "busy": total - free,
        "synthetic": synthetic,
        "games": games, "recent": recent,
        "store": analytics.store_name(),
    }
