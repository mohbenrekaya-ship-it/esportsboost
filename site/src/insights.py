# -*- coding: utf-8 -*-
"""Turn raw analytics events into the numbers the ops dashboard renders.

Pure Python over a list of event dicts — no database, no query language, no
dependencies. Everything the dashboard shows is computed here in one pass per
module, so the front end stays a dumb renderer and every number in it has
exactly one definition, written down once, in this file.

The unit of analysis is the **session**, not the pageview: a visitor who
re-quotes eleven rank pairs and leaves is one story, and it is the story this
business needs to read. `sessionize()` builds those stories; each `_mod_*`
function answers one question about them.

Definitions used throughout (stated once so the dashboard never has to guess):

  * **Visitor** — a distinct anonymous id. **Session** — a distinct session id;
    the client opens a new one after 30 minutes idle.
  * **Conversion rate** — purchasing sessions ÷ sessions. Session-based, not
    visitor-based, so it matches what the funnel shows.
  * **Reached a funnel step** — the session emitted that event at least once.
    Steps are cumulative and monotonic by construction: reaching a later step
    back-fills the earlier ones, so a lost `view_item` beacon can never make a
    funnel stage show more sessions than the stage above it.
  * **A session's configuration** — the last configurator state seen in it. For
    a purchase, the configuration attached to the purchase event.
"""
import time
from collections import Counter, OrderedDict, defaultdict

import data as D

DAY = 86400

# The funnel, in order. Each step lists the events that count as reaching it.
FUNNEL = [
    ("session",   "Visited the site",     ("page_view", "session_start")),
    ("view_item", "Opened a configurator", ("view_item",)),
    ("configure", "Configured an order",  ("configure", "add_to_cart", "select_promotion")),
    ("checkout",  "Started checkout",     ("begin_checkout",)),
    ("payment",   "Reached payment",      ("add_payment_info",)),
    ("purchase",  "Paid",                 ("purchase",)),
]

PRICE_BUCKETS = [(0, 25), (25, 50), (50, 100), (100, 200), (200, 400), (400, None)]
THRASH_BUCKETS = [(1, 1), (2, 3), (4, 6), (7, 10), (11, None)]

EVENT_LABELS = {
    "session_start": "New session", "page_view": "Page view",
    "view_item": "Opened configurator", "configure": "Changed configuration",
    "select_promotion": "Applied a promo", "add_to_cart": "Added an add-on",
    "begin_checkout": "Started checkout", "add_payment_info": "Reached payment",
    "purchase": "Paid", "generate_lead": "Submitted a form",
    "checkout_error": "Checkout error", "js_error": "Script error",
    "scroll": "Scrolled", "engage": "Engaged",
}


# ══════════════════════════════════════════════════════════════════════════
#  small helpers
# ══════════════════════════════════════════════════════════════════════════
def _rate(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return 0
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def _money(x):
    return round(float(x or 0), 2)


def _tier_index():
    """rank string → (game, tier) for every game, from data.py's divmap."""
    idx = {}
    for g in D.GAMES:
        for tier, ranks in g["divmap"].items():
            for r in ranks:
                idx[(g["name"], r)] = tier
    return idx


TIER_OF = _tier_index()
ADDON_LABEL = {a["id"]: a["label"] for a in D.ADDONS}
ADDON_PCT = {a["id"]: a["pct"] for a in D.ADDONS}
GAME_NAMES = [g["name"] for g in D.GAMES]
SLUG_TO_GAME = {g["slug"]: g["name"] for g in D.GAMES}


def norm_path(p):
    """Collapse per-item pages so paths aggregate. /games/valorant → /games/:game"""
    p = (p or "/").split("?")[0].split("#")[0]
    if p.endswith("/index.html"):
        p = p[: -len("index.html")]
    if p.endswith(".html"):
        p = p[:-5]
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    if p.startswith("/games/") and p != "/games":
        return "/games/:game"
    if p.startswith("/legal/"):
        return "/legal/:doc"
    return p or "/"


# ══════════════════════════════════════════════════════════════════════════
#  sessionize
# ══════════════════════════════════════════════════════════════════════════
class Session(object):
    __slots__ = ("id", "anon", "start", "end", "events", "pages", "entry", "dev",
                 "co", "src", "med", "cmp", "ref", "reached", "configs",
                 "last_cfg", "buy_cfg", "value", "requotes", "returning", "lang",
                 "tz", "cosrc")

    def __init__(self, sid, anon):
        self.id, self.anon = sid, anon
        self.start = self.end = 0
        self.events, self.pages, self.configs = [], [], []
        self.entry = self.dev = self.co = ""
        self.src = self.med = self.cmp = self.ref = self.lang = ""
        self.tz = self.cosrc = ""
        self.reached = set()
        self.last_cfg = self.buy_cfg = None
        self.value = 0.0
        self.requotes = 0
        self.returning = False

    @property
    def paid(self):
        return "purchase" in self.reached

    @property
    def cfg(self):
        return self.buy_cfg or self.last_cfg


def sessionize(events):
    """Ordered events → Session objects, oldest first."""
    step_of = {}
    for key, _label, names in FUNNEL:
        for n in names:
            step_of[n] = key

    out = OrderedDict()
    for ev in sorted(events, key=lambda e: (e.get("t", 0), e.get("n", 0))):
        sid, anon = ev.get("s"), ev.get("a")
        if not sid or not anon:
            continue
        s = out.get(sid)
        if s is None:
            s = out[sid] = Session(sid, anon)
            s.start = ev.get("t", 0)
        s.end = ev.get("t", s.end)
        s.events.append(ev)

        name = ev.get("e")
        if name in step_of:
            s.reached.add(step_of[name])
        if name == "configure":
            s.requotes += 1
        for attr in ("dev", "co", "src", "med", "cmp", "ref", "lang", "tz", "cosrc"):
            if not getattr(s, attr) and ev.get(attr):
                setattr(s, attr, ev[attr])
        if ev.get("p"):
            p = norm_path(ev["p"])
            if not s.entry:
                s.entry = p
            if not s.pages or s.pages[-1] != p:
                s.pages.append(p)
        cfg = ev.get("cfg")
        if cfg:
            s.last_cfg = cfg
            if name == "configure":
                s.configs.append(cfg)
        if name == "purchase":
            s.buy_cfg = cfg or s.last_cfg
            s.value += float(ev.get("val") or (cfg or {}).get("total") or 0)

    # Funnel steps are cumulative: reaching a later step implies the earlier
    # ones, even if that beacon never arrived.
    order = [k for k, _l, _n in FUNNEL]
    for s in out.values():
        top = max((order.index(k) for k in s.reached), default=-1)
        if top >= 0:
            s.reached = set(order[: top + 1])
    return list(out.values())


# ══════════════════════════════════════════════════════════════════════════
#  modules
# ══════════════════════════════════════════════════════════════════════════
def _mod_overview(sess, prev_sess, pageviews):
    orders = [s for s in sess if s.paid]
    rev = _money(sum(s.value for s in orders))
    p_orders = [s for s in prev_sess if s.paid]
    p_rev = _money(sum(s.value for s in p_orders))

    def delta(now, was):
        if not was:
            return None
        return round(100.0 * (now - was) / was, 1)

    return {
        "visitors": len(set(s.anon for s in sess)),
        "sessions": len(sess),
        "pageviews": pageviews,
        "orders": len(orders),
        "revenue": rev,
        "cr": _rate(len(orders), len(sess)),
        "aov": _money(rev / len(orders)) if orders else 0.0,
        "delta": {
            "sessions": delta(len(sess), len(prev_sess)),
            "orders": delta(len(orders), len(p_orders)),
            "revenue": delta(rev, p_rev),
            "cr": delta(_rate(len(orders), len(sess)), _rate(len(p_orders), len(prev_sess))),
        },
    }


def _mod_timeseries(sess, start, end):
    days = OrderedDict()
    d = start - (start % DAY)
    while d <= end:
        days[d] = {"d": time.strftime("%Y-%m-%d", time.gmtime(d)),
                   "sessions": 0, "orders": 0, "revenue": 0.0, "visitors": 0}
        d += DAY
    seen = defaultdict(set)
    for s in sess:
        key = s.start - (s.start % DAY)
        row = days.get(key)
        if row is None:
            continue
        row["sessions"] += 1
        seen[key].add(s.anon)
        if s.paid:
            row["orders"] += 1
            row["revenue"] = _money(row["revenue"] + s.value)
    for key, row in days.items():
        row["visitors"] = len(seen.get(key, ()))
    return list(days.values())


def _mod_funnel(sess):
    total = len(sess)
    rows, prev = [], None
    for key, label, _names in FUNNEL:
        n = sum(1 for s in sess if key in s.reached)
        rows.append({
            "key": key, "label": label, "sessions": n,
            "pct_total": _rate(n, total),
            "pct_prev": _rate(n, prev) if prev is not None else 100.0,
            "lost": (prev - n) if prev is not None else 0,
        })
        prev = n
    return rows


def _bucket_label(lo, hi):
    return ("$%d+" % lo) if hi is None else ("$%d–%d" % (lo, hi))


def _mod_configurator(sess, game=None):
    active = [s for s in sess if s.cfg]
    # An impossible rank pair quotes as total 0 (pricing.py `_invalid`), which is
    # not a price anybody was shown — left in, it would sink into the cheapest
    # band and understate conversion exactly where the price curve is read most.
    # Still a real re-quote, so the thrash and funnel modules keep counting it.
    priced = [s for s in active if not s.cfg.get("invalid")]

    # ── which game do we draw the rank matrix for? ──────────────────────
    per_game = Counter(s.cfg.get("game") for s in active if s.cfg.get("game"))
    focus = game if game in per_game else (per_game.most_common(1)[0][0] if per_game else
                                           (GAME_NAMES[0] if GAME_NAMES else ""))
    gdef = next((g for g in D.GAMES if g["name"] == focus), None)
    tiers = list(gdef["tiers"]) if gdef else []

    cells = defaultdict(lambda: {"n": 0, "orders": 0, "revenue": 0.0})
    for s in priced:
        c = s.cfg
        if c.get("game") != focus or c.get("service") != "division":
            continue
        ft = TIER_OF.get((focus, c.get("from")))
        tt = TIER_OF.get((focus, c.get("to")))
        if not ft or not tt:
            continue
        cell = cells[(ft, tt)]
        cell["n"] += 1
        if s.paid:
            cell["orders"] += 1
            cell["revenue"] = _money(cell["revenue"] + s.value)
    matrix = [{"f": f, "t": t, "n": v["n"], "orders": v["orders"],
               "revenue": v["revenue"], "cr": _rate(v["orders"], v["n"])}
              for (f, t), v in cells.items()]
    matrix.sort(key=lambda r: -r["n"])

    # ── price sensitivity ───────────────────────────────────────────────
    price = []
    for lo, hi in PRICE_BUCKETS:
        rows = [s for s in priced
                if lo <= float(s.cfg.get("total") or 0) and
                (hi is None or float(s.cfg.get("total") or 0) < hi)]
        buys = [s for s in rows if s.paid]
        price.append({
            "label": _bucket_label(lo, hi), "lo": lo, "hi": hi,
            "sessions": len(rows), "orders": len(buys),
            "cr": _rate(len(buys), len(rows)),
            "revenue": _money(sum(s.value for s in buys)),
        })

    # ── re-quote thrash ─────────────────────────────────────────────────
    thrash = []
    touched = [s for s in sess if s.requotes > 0]
    for lo, hi in THRASH_BUCKETS:
        rows = [s for s in touched if s.requotes >= lo and (hi is None or s.requotes <= hi)]
        buys = [s for s in rows if s.paid]
        thrash.append({
            "label": ("%d+" % lo) if hi is None else (str(lo) if lo == hi else "%d–%d" % (lo, hi)),
            "sessions": len(rows), "orders": len(buys), "cr": _rate(len(buys), len(rows)),
        })

    # ── add-on attach ───────────────────────────────────────────────────
    addons = []
    base_cr = _rate(sum(1 for s in active if s.paid), len(active))
    for aid, label in ADDON_LABEL.items():
        rows = [s for s in active if aid in (s.cfg.get("addons") or [])]
        buys = [s for s in rows if s.paid]
        cr = _rate(len(buys), len(rows))
        addons.append({
            "id": aid, "label": label, "pct": ADDON_PCT.get(aid, 0),
            "sessions": len(rows), "attach": _rate(len(rows), len(active)),
            "orders": len(buys), "cr": cr, "lift": round(cr - base_cr, 1),
            "revenue": _money(sum(s.value for s in buys)),
        })
    addons.sort(key=lambda r: -r["attach"])

    def split(field, values=None):
        out = []
        keys = values or sorted(set(s.cfg.get(field) or "" for s in active) - {""})
        for k in keys:
            rows = [s for s in active if s.cfg.get(field) == k]
            buys = [s for s in rows if s.paid]
            out.append({
                "name": k, "sessions": len(rows), "orders": len(buys),
                "cr": _rate(len(buys), len(rows)),
                "revenue": _money(sum(s.value for s in buys)),
                "aov": _money(sum(s.value for s in buys) / len(buys)) if buys else 0.0,
            })
        return sorted(out, key=lambda r: -r["sessions"])

    modes = split("mode", ["Solo", "Duo queue"])
    services = split("service", ["division", "wins", "placements"])

    # ── game mix: attention share vs revenue share ──────────────────────
    games, tot_rev = [], sum(s.value for s in active if s.paid) or 0.0
    for name in GAME_NAMES:
        rows = [s for s in active if s.cfg.get("game") == name]
        buys = [s for s in rows if s.paid]
        rev = _money(sum(s.value for s in buys))
        games.append({
            "name": name, "sessions": len(rows), "orders": len(buys),
            "revenue": rev, "cr": _rate(len(buys), len(rows)),
            "share_traffic": _rate(len(rows), len(active)),
            "share_revenue": _rate(rev, tot_rev) if tot_rev else 0.0,
        })
    games.sort(key=lambda r: -r["sessions"])

    return {
        "focus": focus, "tiers": tiers, "matrix": matrix,
        "games_available": [g for g, _ in per_game.most_common()],
        "price": price, "thrash": thrash, "addons": addons,
        "modes": modes, "services": services, "games": games,
        "base_cr": base_cr,
    }


def _mod_journey(sess, first_seen):
    paths = defaultdict(lambda: {"sessions": 0, "orders": 0, "revenue": 0.0})
    for s in sess:
        if not s.pages:
            continue
        key = " → ".join(s.pages[:5]) + (" → …" if len(s.pages) > 5 else "")
        row = paths[key]
        row["sessions"] += 1
        if s.paid:
            row["orders"] += 1
            row["revenue"] = _money(row["revenue"] + s.value)
    top_paths = [{"path": k, **v, "cr": _rate(v["orders"], v["sessions"])}
                 for k, v in paths.items()]
    top_paths.sort(key=lambda r: -r["sessions"])

    entries = defaultdict(lambda: {"sessions": 0, "orders": 0, "revenue": 0.0})
    for s in sess:
        if not s.entry:
            continue
        row = entries[s.entry]
        row["sessions"] += 1
        if s.paid:
            row["orders"] += 1
            row["revenue"] = _money(row["revenue"] + s.value)
    entry_rows = [{"page": k, **v, "cr": _rate(v["orders"], v["sessions"])}
                  for k, v in entries.items()]
    entry_rows.sort(key=lambda r: -r["sessions"])

    new = [s for s in sess if not s.returning]
    ret = [s for s in sess if s.returning]
    cohorts = [
        {"name": "First visit", "sessions": len(new),
         "orders": sum(1 for s in new if s.paid), "cr": _rate(sum(1 for s in new if s.paid), len(new)),
         "revenue": _money(sum(s.value for s in new if s.paid))},
        {"name": "Returning", "sessions": len(ret),
         "orders": sum(1 for s in ret if s.paid), "cr": _rate(sum(1 for s in ret if s.paid), len(ret)),
         "revenue": _money(sum(s.value for s in ret if s.paid))},
    ]

    # How many sessions, and how long, before the visitor paid.
    by_anon = defaultdict(list)
    for s in sorted(sess, key=lambda x: x.start):
        by_anon[s.anon].append(s)
    nth, lags = Counter(), []
    for anon, rows in by_anon.items():
        for i, s in enumerate(rows):
            if s.paid:
                nth[min(i + 1, 5)] += 1
                lags.append(max(0, s.end - first_seen.get(anon, s.start)))
                break
    sessions_to_buy = [{"n": ("%d+" % n) if n == 5 else str(n), "count": nth.get(n, 0)}
                       for n in range(1, 6)]

    lag_buckets = [("< 10 min", 0, 600), ("10–60 min", 600, 3600),
                   ("1–24 h", 3600, DAY), ("1–7 days", DAY, 7 * DAY),
                   ("> 7 days", 7 * DAY, None)]
    lag_rows = [{"label": lbl,
                 "count": sum(1 for v in lags if v >= lo and (hi is None or v < hi))}
                for lbl, lo, hi in lag_buckets]

    return {
        "paths": top_paths[:12], "entry": entry_rows[:10], "cohorts": cohorts,
        "sessions_to_buy": sessions_to_buy, "lag": lag_rows,
        "median_lag_min": int(_median(lags) / 60) if lags else 0,
    }


def _mod_acquisition(sess):
    rows = defaultdict(lambda: {"sessions": 0, "orders": 0, "revenue": 0.0})
    for s in sess:
        src = s.src or (s.ref or "direct")
        med = s.med or ("referral" if s.ref else "none")
        row = rows[(src, med, s.cmp or "")]
        row["sessions"] += 1
        if s.paid:
            row["orders"] += 1
            row["revenue"] = _money(row["revenue"] + s.value)
    out = [{"source": k[0], "medium": k[1], "campaign": k[2], **v,
            "cr": _rate(v["orders"], v["sessions"]),
            "rps": _money(v["revenue"] / v["sessions"]) if v["sessions"] else 0.0}
           for k, v in rows.items()]
    out.sort(key=lambda r: -r["revenue"] or -r["sessions"])
    return out[:15]


def _mod_friction(sess, events):
    errs = defaultdict(lambda: {"count": 0, "sessions": set()})
    for ev in events:
        if ev.get("e") not in ("checkout_error", "js_error"):
            continue
        meta = ev.get("meta") or {}
        msg = str(meta.get("message") or meta.get("code") or "unknown")[:160]
        row = errs[(ev["e"], msg)]
        row["count"] += 1
        row["sessions"].add(ev.get("s"))
    error_rows = [{"kind": k[0], "message": k[1], "count": v["count"],
                   "sessions": len(v["sessions"])} for k, v in errs.items()]
    error_rows.sort(key=lambda r: -r["count"])

    began = [s for s in sess if "checkout" in s.reached]
    paid = [s for s in began if s.paid]
    at_payment = [s for s in sess if "payment" in s.reached and not s.paid]
    abandon = {
        "began": len(began), "paid": len(paid),
        "abandoned": len(began) - len(paid),
        "rate": _rate(len(began) - len(paid), len(began)),
        "at_payment": len(at_payment),
        "lost": _money(sum(float((s.cfg or {}).get("total") or 0)
                           for s in began if not s.paid)),
        # Sessions whose last configuration was impossible (target at or below
        # the current rank). They see an em dash instead of a price, so a high
        # number here is a UI problem, not a pricing one.
        "invalid": sum(1 for s in sess if (s.cfg or {}).get("invalid")),
    }

    def split(attr, label_map=None):
        rows = defaultdict(lambda: {"sessions": 0, "orders": 0, "revenue": 0.0})
        for s in sess:
            row = rows[getattr(s, attr) or "unknown"]
            row["sessions"] += 1
            if s.paid:
                row["orders"] += 1
                row["revenue"] = _money(row["revenue"] + s.value)
        out = [{"name": (label_map or {}).get(k, k), **v,
                "cr": _rate(v["orders"], v["sessions"])} for k, v in rows.items()]
        return sorted(out, key=lambda r: -r["sessions"])

    return {"errors": error_rows[:12], "abandon": abandon,
            "devices": split("dev"), "countries": split("co")[:10]}


def _mod_abandoned(sess, limit=60):
    rows = []
    for s in sess:
        if s.paid or not s.cfg:
            continue
        c = s.cfg
        if not c.get("game"):
            continue
        step = "configured"
        if "payment" in s.reached:
            step = "reached payment"
        elif "checkout" in s.reached:
            step = "started checkout"
        rows.append({
            "at": s.end, "value": _money(c.get("total") or 0),
            "game": c.get("game", ""), "service": c.get("service", ""),
            "from": c.get("from", ""), "to": c.get("to", ""),
            "mode": c.get("mode", ""), "region": c.get("region", ""),
            "addons": [ADDON_LABEL.get(a, a) for a in (c.get("addons") or [])],
            "step": step, "requotes": s.requotes, "device": s.dev,
            "source": s.src or s.ref or "direct", "country": s.co,
            "returning": s.returning, "session": s.id,
        })
    rows.sort(key=lambda r: (-r["value"], -r["at"]))
    return rows[:limit]


def _page_visits(rows):
    """Consecutive page visits in a session, with time spent on each.

    There is no "left the page" event — a browser that closes sends nothing —
    so a visit lasts from its first event until the first event on the NEXT
    page. The final visit can only be measured to the session's last event,
    which is a floor, not the true dwell: it is flagged `partial` so the UI can
    say "at least" rather than quietly under-reporting.
    """
    visits, cur = [], None
    for ev in rows:
        p, t = ev.get("p"), ev.get("t", 0)
        if not p:
            continue
        if cur is None or cur["path"] != p:
            if cur:
                cur["end"] = t                      # ends when the next page starts
                visits.append(cur)
            cur = {"path": p, "start": t, "end": t, "events": 0}
        cur["end"] = max(cur["end"], t)
        cur["events"] += 1
    if cur:
        cur["partial"] = True
        visits.append(cur)
    for v in visits:
        v["seconds"] = max(0, v["end"] - v["start"])
        v.setdefault("partial", False)
    return visits


def _furthest_step(reached):
    label = ""
    for key, text, _names in FUNNEL:
        if key in reached:
            label = text
    return label


def _session_row(s):
    """One row of the sessions list — everything answerable without the
    full timeline."""
    visits = _page_visits(s.events)
    cfg = s.cfg or {}
    return {
        "id": s.id, "anon": s.anon,
        "start": s.start, "end": s.end, "duration": max(0, s.end - s.start),
        "src": s.src or s.ref or "direct", "med": s.med or "none", "cmp": s.cmp or "",
        "ref": s.ref, "dev": s.dev or "", "co": s.co or "", "lang": s.lang or "",
        "tz": s.tz or "", "cosrc": s.cosrc or "",
        "entry": s.entry or "", "exit": visits[-1]["path"] if visits else "",
        "pages": len(visits), "events": len(s.events),
        "returning": s.returning, "requotes": s.requotes,
        "paid": s.paid, "step": _furthest_step(s.reached),
        "value": _money(s.value or cfg.get("total") or 0),
        "game": cfg.get("game", ""), "summary": cfg.get("summary", ""),
    }


def _mod_sessions(sess, limit=300):
    rows = [_session_row(s) for s in sorted(sess, key=lambda x: -x.start)]
    return rows[:limit]


def session_detail(events, session_id, first_seen=None):
    """Everything about one session: attribution, per-page dwell, and the full
    event timeline. Fetched on demand — shipping every session's timeline to
    the browser would mean sending the entire event store."""
    rows = [e for e in events if e.get("s") == session_id]
    if not rows:
        return None
    rows.sort(key=lambda e: (e.get("t", 0), e.get("n", 0)))

    if first_seen is None:
        first_seen = {}
        for e in events:
            a, t = e.get("a"), e.get("t", 0)
            if a and (a not in first_seen or t < first_seen[a]):
                first_seen[a] = t

    s = sessionize(rows)[0]
    s.returning = first_seen.get(s.anon, s.start) < s.start - 60

    t0 = rows[0].get("t", 0)
    timeline = []
    for i, ev in enumerate(rows):
        nxt = rows[i + 1].get("t") if i + 1 < len(rows) else None
        cfg = ev.get("cfg") or {}
        timeline.append({
            "t": ev.get("t", 0), "offset": ev.get("t", 0) - t0,
            "gap": (nxt - ev.get("t", 0)) if nxt is not None else None,
            "e": ev.get("e", ""), "label": EVENT_LABELS.get(ev.get("e", ""), ev.get("e", "")),
            "path": ev.get("p", ""),
            "game": cfg.get("game", ""), "summary": cfg.get("summary", ""),
            "mode": cfg.get("mode", ""), "region": cfg.get("region", ""),
            "service": cfg.get("service", ""),
            "addons": [ADDON_LABEL.get(a, a) for a in (cfg.get("addons") or [])],
            "price": _money(cfg.get("total") or 0),
            "invalid": bool(cfg.get("invalid")),
            "value": _money(ev.get("val") or 0),
            "meta": ev.get("meta") or {},
        })

    visits = _page_visits(rows)
    # Same page visited twice = two visits in the timeline, one row in the
    # totals — "time consumed on every page" is a per-page total.
    totals = OrderedDict()
    for v in visits:
        row = totals.setdefault(v["path"], {"path": v["path"], "seconds": 0,
                                            "visits": 0, "partial": False})
        row["seconds"] += v["seconds"]
        row["visits"] += 1
        row["partial"] = row["partial"] or v["partial"]

    return {
        "summary": _session_row(s),
        "timeline": timeline,
        "visits": [{"path": v["path"], "seconds": v["seconds"],
                    "partial": v["partial"], "at": v["start"]} for v in visits],
        "pages": list(totals.values()),
    }


def _mod_live(events, limit=40):
    out = []
    for ev in sorted(events, key=lambda e: -e.get("t", 0))[:limit]:
        cfg = ev.get("cfg") or {}
        out.append({
            "t": ev.get("t", 0), "e": ev.get("e", ""),
            "label": EVENT_LABELS.get(ev.get("e", ""), ev.get("e", "")),
            "path": ev.get("p", ""), "game": cfg.get("game", ""),
            "summary": cfg.get("summary", ""),
            "value": _money(ev.get("val") or cfg.get("total") or 0),
            "device": ev.get("dev", ""), "country": ev.get("co", ""),
            "source": ev.get("src", "") or ev.get("ref", ""),
        })
    return out


# ── the live view ─────────────────────────────────────────────────────────
# A Shopify-style "right now" panel. Deliberately independent of the dashboard's
# `days` window: it always reads the last few minutes, so the period selector
# never changes what it shows. The client polls it every 10s (see ops.js).
NOW_WINDOW = 5 * 60          # "visitors right now" — active in the last 5 minutes
LIVE_WINDOW = 30 * 60        # the live session horizon — carts, locations, games
SPARK_MINUTES = 30           # per-minute visitor bars


def _session_game(s):
    """The game a live session is on — from the configured order if there is
    one, else from the `/games/<slug>` page it is sitting on. That second path
    is what lets a visitor still browsing a game page count toward it before
    they have quoted anything."""
    g = (s.cfg or {}).get("game") if s.cfg else None
    if g:
        return g
    for ev in s.events:
        p = (ev.get("p") or "").split("?")[0].split("#")[0]
        if p.startswith("/games/"):
            slug = p[len("/games/"):]
            if slug.endswith(".html"):
                slug = slug[:-5]
            slug = slug.strip("/")
            if slug in SLUG_TO_GAME:
                return SLUG_TO_GAME[slug]
    return None


def _mod_liveview(events, first_seen, now):
    """Real-time snapshot: who is on the site now, and what they are doing.

    `first_seen` (anon → earliest timestamp we hold) is reused from compute()
    so "returning" means the same thing here as everywhere else on the site.
    """
    now = int(now)
    live_start = now - LIVE_WINDOW
    now_start = now - NOW_WINDOW

    recent = [e for e in events if e.get("t", 0) >= live_start]

    # Visitors right now — distinct anon ids with any beacon in the last 5 min.
    active = {e.get("a") for e in recent
              if e.get("a") and e.get("t", 0) >= now_start}

    # Per-minute unique-visitor bars, oldest → newest, so the row reads left to
    # right like a clock. A minute with nobody in it is a real zero, not a gap.
    buckets = [set() for _ in range(SPARK_MINUTES)]
    span = SPARK_MINUTES * 60
    for e in events:
        a, t = e.get("a"), e.get("t", 0)
        if not a or t < now - span or t > now:
            continue
        idx = SPARK_MINUTES - 1 - int((now - t) // 60)
        if 0 <= idx < SPARK_MINUTES:
            buckets[idx].add(a)
    spark = [len(b) for b in buckets]

    # Sessionize the live horizon and read where each session got to. `reached`
    # is the cumulative funnel-key set, so classifying is one membership test.
    sess = [s for s in sessionize(recent) if s.end >= live_start]

    # Live sessions grouped by game — the "product view". This site has no cart,
    # so instead of a cart funnel we split each game's live sessions by how far
    # they got: browsing → configuring → checking out → purchased. A session's
    # game comes from its order or the /games/<slug> page it is on.
    games = OrderedDict()
    loc = defaultdict(set)
    first = returning = 0
    # Site-wide behaviour tally — the summary boxes above the per-game view.
    # Counts every live session by its furthest stage, game page or not.
    tally = {"browsing": 0, "configuring": 0, "checkout": 0, "purchased": 0}
    for s in sess:
        if s.co:
            loc[s.co].add(s.anon)
        if first_seen.get(s.anon, s.start) < s.start - 60:
            returning += 1
        else:
            first += 1
        if s.paid:
            stage = "purchased"
        elif "checkout" in s.reached:
            stage = "checkout"
        elif "configure" in s.reached:
            stage = "configuring"
        else:
            stage = "browsing"
        tally[stage] += 1
        g = _session_game(s)
        if not g:
            continue
        row = games.setdefault(g, {"name": g, "sessions": 0, "browsing": 0,
                                   "configuring": 0, "checkout": 0, "purchased": 0})
        row["sessions"] += 1
        row[stage] += 1
    behavior = [
        {"key": "browsing",    "label": "Just browsing", "count": tally["browsing"]},
        {"key": "configuring", "label": "Configuring",   "count": tally["configuring"]},
        {"key": "checkout",    "label": "Checking out",  "count": tally["checkout"]},
        {"key": "purchased",   "label": "Purchased",     "count": tally["purchased"]},
    ]

    products = sorted(games.values(), key=lambda r: -r["sessions"])[:8]
    locations = sorted(({"code": k, "sessions": len(v)} for k, v in loc.items()),
                       key=lambda r: -r["sessions"])[:6]

    # Last 24 hours — the "today"-ish headline totals, always this window
    # regardless of the period selector.
    day = sessionize([e for e in events if e.get("t", 0) >= now - DAY])
    orders = [s for s in day if s.paid]

    return {
        "now_secs": NOW_WINDOW, "window_mins": LIVE_WINDOW // 60,
        "visitors": len(active),
        "sessions_live": len(sess),
        "spark": spark, "spark_minutes": SPARK_MINUTES,
        "behavior": behavior,
        "products": products,
        "locations": locations,
        "customers": {"first": first, "returning": returning},
        "today": {
            "sessions": len(day), "orders": len(orders),
            "revenue": _money(sum(s.value for s in orders)),
        },
    }


def stripe_summary(days=30):
    """Paid orders straight from Stripe — the money's own source of truth,
    independent of whether a beacon ever fired. Returns None when no key is
    configured, which is the normal state in a static preview."""
    try:
        import payments
    except ImportError:
        return None
    if not payments.stripe_key():
        return None
    try:
        res = payments.stripe_call(
            "/checkout/sessions",
            {"limit": 100, "created[gte]": int(time.time()) - days * DAY},
            method="GET")
    except Exception:                                          # noqa: BLE001
        return None

    rows, by_game, by_region, emails = [], Counter(), Counter(), Counter()
    revenue = 0.0
    for s in res.get("data", []):
        if s.get("payment_status") != "paid":
            continue
        md = s.get("metadata") or {}
        amount = (s.get("amount_total") or 0) / 100.0
        revenue += amount
        by_game[md.get("game") or "—"] += 1
        by_region[md.get("region") or "—"] += 1
        email = (s.get("customer_details") or {}).get("email")
        if email:
            emails[email] += 1
        rows.append({
            "at": s.get("created", 0), "amount": _money(amount),
            "order_id": s.get("client_reference_id") or md.get("order_id") or "",
            "game": md.get("game", ""), "detail": md.get("detail", ""),
            "region": md.get("region", ""), "promo": md.get("promo", ""),
            "discount": _money(float(md.get("discount") or 0)),
        })
    rows.sort(key=lambda r: -r["at"])
    return {
        "orders": len(rows), "revenue": _money(revenue),
        "aov": _money(revenue / len(rows)) if rows else 0.0,
        "discount": _money(sum(r["discount"] for r in rows)),
        "repeat": sum(1 for _e, n in emails.items() if n > 1),
        "customers": len(emails),
        "by_game": [{"name": k, "orders": v} for k, v in by_game.most_common()],
        "by_region": [{"name": k, "orders": v} for k, v in by_region.most_common()],
        "recent": rows[:20],
    }


# ══════════════════════════════════════════════════════════════════════════
#  entry point
# ══════════════════════════════════════════════════════════════════════════
def compute(events, days=30, game=None, now=None, with_stripe=True):
    """All dashboard modules for the trailing `days` window, plus the window
    immediately before it for the deltas."""
    now = int(now or time.time())
    days = max(1, min(int(days or 30), 365))
    start = now - days * DAY
    prev_start = start - days * DAY

    # First-seen is computed over everything we hold, not just the window, so a
    # visitor returning after the window opened is still counted as returning.
    first_seen = {}
    for ev in events:
        a, t = ev.get("a"), ev.get("t", 0)
        if a and (a not in first_seen or t < first_seen[a]):
            first_seen[a] = t

    window = [e for e in events if e.get("t", 0) >= start]
    prev_window = [e for e in events if prev_start <= e.get("t", 0) < start]

    sess = sessionize(window)
    prev_sess = sessionize(prev_window)
    for s in sess:
        s.returning = first_seen.get(s.anon, s.start) < s.start - 60

    pageviews = sum(1 for e in window if e.get("e") == "page_view")

    return {
        "meta": {
            "days": days, "start": start, "end": now,
            "generated": now, "events": len(window), "stored": len(events),
            # Seeded events carry syn=1 (see tools/seed_analytics.py). The
            # dashboard must keep saying so for as long as any are in the
            # window — placeholder numbers that lose their label become real
            # numbers in someone's head.
            "synthetic": sum(1 for e in window if e.get("syn")),
        },
        "overview": _mod_overview(sess, prev_sess, pageviews),
        "timeseries": _mod_timeseries(sess, start, now),
        "funnel": _mod_funnel(sess),
        "configurator": _mod_configurator(sess, game),
        "journey": _mod_journey(sess, first_seen),
        "acquisition": _mod_acquisition(sess),
        "friction": _mod_friction(sess, window),
        "sessions": _mod_sessions(sess),
        "abandoned": _mod_abandoned(sess),
        "live": _mod_live(window),
        # The live view is always "right now", not the selected period — it
        # reads its own short windows off the full store.
        "liveview": _mod_liveview(events, first_seen, now),
        "stripe": stripe_summary(days) if with_stripe else None,
    }
