#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill the analytics store with SYNTHETIC traffic so /ops can be checked.

    python3 site/tools/seed_analytics.py --clear --days 30 --sessions 900

Every event this writes carries `"syn": 1`, and the dashboard shows a standing
"synthetic data" banner while any such event is in the store. That marker is the
point: this project already carries invented STATS/BOOSTERS/REVIEWS placeholders
(see the warning at the top of src/data.py), and seeded funnel numbers are
exactly the kind of thing that quietly becomes a slide in a real meeting. Do not
remove the flag, and clear the store before the site takes real traffic.

The behaviour model is deliberately not uniform noise — a dashboard tested on
uniform noise shows nothing, and every module here exists to find a pattern:

  * traffic sources differ in quality (paid clicks browse, Discord converts),
  * price resistance rises with the quoted total, using the REAL pricing.quote()
    on the REAL ladders, so the sensitivity curve is shaped by the actual
    formula rather than by a made-up number,
  * heavy re-quoting predicts abandonment,
  * mobile converts worse than desktop,
  * some visitors come back over several days before paying.

Writing to a configured Upstash store requires --force: the default target is
the local NDJSON file, because seeding production by accident is unrecoverable.
"""
import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import accounts                                     # noqa: E402
import analytics                                    # noqa: E402
import data as D                                    # noqa: E402
import pricing                                      # noqa: E402

DAY = 86400

# (source, medium, campaign, share, quality) — quality scales intent end to end.
SOURCES = [
    ("google", "organic", "", 0.30, 1.00),
    ("google", "cpc", "summer-elo", 0.14, 0.72),
    ("reddit", "referral", "", 0.12, 0.62),
    ("discord", "referral", "", 0.11, 1.45),
    ("youtube", "social", "creator-codes", 0.10, 0.80),
    ("direct", "none", "", 0.13, 1.25),
    ("twitter", "social", "", 0.06, 0.55),
    ("bing", "organic", "", 0.04, 0.85),
]
DEVICES = [("mobile", 0.58, 0.78), ("desktop", 0.38, 1.30), ("tablet", 0.04, 0.90)]
COUNTRIES = [("FR", 0.19), ("DE", 0.15), ("GB", 0.12), ("US", 0.14), ("BR", 0.09),
             ("TR", 0.08), ("PL", 0.07), ("ES", 0.06), ("NL", 0.05), ("SE", 0.05)]
ENTRIES = [("/", 0.34, 0.55), ("/games/:game", 0.29, 0.95), ("/games", 0.12, 0.80),
           ("/how-it-works", 0.09, 0.45), ("/reviews", 0.07, 0.40),
           ("/boosters", 0.05, 0.35), ("/guarantee", 0.04, 0.40)]
BROWSE = ["/", "/games", "/games/:game", "/how-it-works", "/guarantee",
          "/reviews", "/boosters", "/support"]
SERVICES = [("division", 0.74), ("wins", 0.16), ("placements", 0.10)]
ERRORS = [("api_503", "Payment could not be started. Please try again."),
          ("canceled", "Payment canceled — nothing was charged."),
          ("network", "Network error reaching payment.")]


def pick(rows, w=1):
    """Weighted choice over tuples, with the weight at index `w`."""
    total = sum(r[w] for r in rows)
    x = random.random() * total
    for r in rows:
        x -= r[w]
        if x <= 0:
            return r
    return rows[-1]


def game_weights():
    """League leads; the rest taper. Deterministic in game order so the mix is
    stable between runs and the game chart tells the same story twice."""
    out = []
    for i, g in enumerate(D.GAMES):
        out.append((g, 1.0 / (1.35 ** i)))
    return out


GAMES = game_weights()


def make_config(quality):
    g = pick(GAMES)[0]
    ladder = list(g["ladder"])
    service = pick(SERVICES)[0]
    cfg = {
        "game": g["name"], "service": service,
        "mode": "Duo queue" if random.random() < 0.18 else "Solo",
        "region": random.choice(g["regions"]),
        "addons": [],
    }
    # Only the add-ons this queue actually offers — a synthetic solo order
    # carrying the duo-only option would show up in the console as a choice the
    # picker never presented (and the engine never charged for).
    cfg["addons"] = [a["id"] for a in D.ADDONS
                     if D.addon_applies(a, cfg["mode"])
                     and random.random() < (0.30 if a["id"] == "priority" else 0.16)]
    if service == "division":
        # Most people start mid-ladder and aim a few rungs up; a minority buy a
        # long climb. That skew is what makes the rank matrix worth looking at.
        i = min(len(ladder) - 2, int(abs(random.gauss(len(ladder) * 0.42, len(ladder) * 0.18))))
        span = max(1, int(abs(random.gauss(4.5, 3.2))))
        j = min(len(ladder) - 1, i + span)
        cfg["from"], cfg["to"] = ladder[i], ladder[j]
    else:
        cfg["from"] = ladder[min(len(ladder) - 1,
                                 int(abs(random.gauss(len(ladder) * 0.45, len(ladder) * 0.2))))]
        cfg["to"] = cfg["from"]
        n = max(1, min(10, int(abs(random.gauss(5, 2.5)))))
        cfg["wins" if service == "wins" else "placements"] = n

    q = pricing.quote(cfg)
    if q.get("invalid"):
        return None
    cfg["total"] = q["total"]
    cfg["summary"] = q["summary"]
    return cfg


def price_resistance(total):
    """P(continue) given the quoted price. Calibrated so cheap orders convert
    well and the curve bends hard past ~$200 — the shape the dashboard exists
    to confirm or refute against real traffic."""
    if total < 25:
        return 0.62
    if total < 50:
        return 0.52
    if total < 100:
        return 0.38
    if total < 200:
        return 0.24
    if total < 400:
        return 0.13
    return 0.07


def build_session(anon, sid, t0, quality, dev, dev_mult, co, src, returning):
    """One visit → its list of events, chronological."""
    evs = []
    seq = [0]
    entry = pick(ENTRIES)
    entry_page, entry_intent = entry[0], entry[2]
    t = [t0]

    def ev(name, cfg=None, val=None, meta=None, gap=(4, 40), path=None):
        seq[0] += 1
        t[0] += random.randint(*gap)
        rec = {"t": t[0], "e": name, "a": anon, "s": sid, "n": seq[0],
               "p": path or entry_page, "src": src[0], "med": src[1],
               "cmp": src[2], "ref": src[0] if src[1] == "referral" else "",
               "dev": dev, "co": co, "lang": "en-GB", "syn": 1}
        if cfg:
            rec["cfg"] = cfg
        if val is not None:
            rec["val"] = val
        if meta:
            rec["meta"] = meta
        evs.append(rec)
        return rec

    if not returning:
        ev("session_start", gap=(0, 1))
    ev("page_view", gap=(0, 2))
    ev("scroll", meta={"pct": 25}, gap=(3, 25))

    page = entry_page
    for _ in range(random.randint(0, 3)):
        if random.random() > 0.55:
            break
        page = random.choice(BROWSE)
        ev("page_view", gap=(6, 90), path=page)
        if random.random() < 0.6:
            ev("scroll", meta={"pct": random.choice([50, 75, 100])}, gap=(4, 30), path=page)

    intent = quality * dev_mult * entry_intent
    if random.random() > min(0.95, 0.55 + intent * 0.35):
        return evs                                    # bounced before configuring

    cfg = make_config(quality)
    if not cfg:
        return evs
    game_page = "/games/:game"
    ev("view_item", cfg=cfg, gap=(3, 30), path=game_page)
    if random.random() > min(0.93, 0.62 + intent * 0.28):
        return evs                                    # looked at the price, left

    # Re-quoting: cheap sessions settle fast, expensive ones churn. Heavy
    # churn is itself a negative signal, applied below.
    requotes = max(1, int(abs(random.gauss(3.2, 2.6))))
    if cfg["total"] > 150:
        requotes += random.randint(0, 5)
    for _ in range(requotes):
        alt = make_config(quality)
        if alt:
            cfg = alt
        ev("configure", cfg=cfg, gap=(3, 45), path=game_page)
    if random.random() < 0.14:
        ev("select_promotion", cfg=dict(cfg, promo="SUMMER"), gap=(4, 30), path=game_page)

    p = price_resistance(cfg["total"]) * quality * dev_mult
    if requotes > 7:
        p *= 0.45                                     # thrash predicts abandonment
    if cfg["mode"] == "Duo queue":
        p *= 0.82                                     # the ×1.55 multiplier bites
    if returning:
        p *= 1.5

    if random.random() > min(0.92, p):
        return evs                                    # left at the configurator

    ev("begin_checkout", cfg=cfg, val=cfg["total"], gap=(5, 60), path=game_page)
    ev("page_view", gap=(2, 8), path="/checkout")
    if random.random() < 0.12:
        code, msg = random.choice(ERRORS)
        ev("checkout_error", cfg=cfg, meta={"code": code, "message": msg},
           gap=(10, 90), path="/checkout")
        if random.random() < 0.6:
            return evs
    ev("add_payment_info", cfg=cfg, val=cfg["total"], gap=(8, 120), path="/checkout")
    if random.random() > 0.74:
        return evs                                    # dropped at the payment step

    ev("purchase", cfg=cfg, val=cfg["total"], gap=(20, 240), path="/checkout/success",
       meta={"transaction_id": "ESB-%06X" % random.randrange(16 ** 6)})
    return evs


def main():
    ap = argparse.ArgumentParser(description="Seed the analytics store with synthetic traffic.")
    ap.add_argument("--days", type=int, default=30, help="window to spread traffic over")
    ap.add_argument("--sessions", type=int, default=900, help="approximate session count")
    ap.add_argument("--clear", action="store_true", help="wipe the store first")
    ap.add_argument("--force", action="store_true",
                    help="allow writing to a configured Upstash (production) store")
    ap.add_argument("--seed", type=int, default=20260811, help="RNG seed")
    ap.add_argument("--accounts", type=int, default=0, metavar="N",
                    help="also seed N synthetic header sign-ups (separate store)")
    args = ap.parse_args()

    if analytics.upstash_config()[0] and not args.force:
        sys.exit("Refusing to seed the Upstash store without --force.\n"
                 "Unset UPSTASH_REDIS_REST_URL to seed the local file instead.")

    random.seed(args.seed)
    now = int(time.time())
    start = now - args.days * DAY

    if args.clear:
        analytics.clear()
        accounts.clear()

    # A pool of visitors; some return across several days before buying.
    visitors = []
    for _ in range(int(args.sessions * 0.78)):
        src = pick(SOURCES, 3)
        dev = pick(DEVICES)
        visitors.append({
            "anon": "syn%09x" % random.randrange(16 ** 9),
            "src": (src[0], src[1], src[2]), "quality": src[4],
            "dev": dev[0], "dev_mult": dev[2], "co": pick(COUNTRIES)[0],
        })

    batch, total, sessions = [], 0, 0
    for v in visitors:
        visits = 1
        r = random.random()
        if r > 0.88:
            visits = 3
        elif r > 0.70:
            visits = 2
        first = random.uniform(start, now - 600)
        for k in range(visits):
            t0 = first + k * random.uniform(0.4 * DAY, 3.5 * DAY)
            if t0 > now - 120:
                break
            # Traffic breathes: evenings and weekends carry more of it.
            hour = time.gmtime(int(t0)).tm_hour
            if hour < 8 and random.random() < 0.55:
                continue
            sessions += 1
            evs = build_session(
                v["anon"], "syn%010x" % random.randrange(16 ** 10), int(t0),
                v["quality"], v["dev"], v["dev_mult"], v["co"], v["src"], k > 0)
            batch.extend(evs)
            if len(batch) >= 500:
                batch.sort(key=lambda e: e["t"])
                total += analytics.append(batch)
                batch = []
    if batch:
        batch.sort(key=lambda e: e["t"])
        total += analytics.append(batch)

    print("seeded %d synthetic events across %d sessions / %d visitors → %s store"
          % (total, sessions, len(visitors), analytics.store_name()))
    print("every event is flagged syn=1; /ops shows a synthetic-data banner while they are present")

    # Optional: synthetic header sign-ups, into their OWN store. Fake emails, so
    # each carries syn=1 exactly like the events — the Accounts panel shows its
    # own banner while any are present, and nothing here is a real address.
    if args.accounts > 0:
        if analytics.upstash_config()[0] and not args.force:
            sys.exit("Refusing to seed the Upstash accounts store without --force.")
        handles = ["kaydn", "mira", "tovi", "arbo", "nine", "vesk", "orla", "pell",
                   "juno", "riko", "sable", "wren", "dax", "elio", "nova", "quill"]
        rows = []
        for i in range(args.accounts):
            h = random.choice(handles) + str(random.randrange(10, 99))
            ts = int(random.uniform(start, now - 120))
            rows.append({
                "email": "syn-%06x@example.test" % random.randrange(16 ** 6),
                "name": h, "ts": ts, "co": pick(COUNTRIES)[0], "cosrc": "edge",
                "mode": "signup" if random.random() < 0.8 else "signin", "syn": 1,
            })
        rows.sort(key=lambda r: r["ts"])
        accounts.append(rows)
        print("seeded %d synthetic sign-ups → %s store (flagged syn=1)"
              % (len(rows), analytics.store_name()))


if __name__ == "__main__":
    main()
