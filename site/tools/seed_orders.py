#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill the orders store with placeholder orders so the /ops "Orders" tab has
something to show in the preview.

    python3 site/tools/seed_orders.py --clear --count 120

Every order is a real, sellable configuration priced through pricing.quote() (so
the totals are honest arithmetic, not typed numbers), spread across the games, the
services, the add-ons and the order lifecycle. Each row carries `"syn": 1` — the
/ops Orders tab shows a standing "not real orders" banner while any are present,
exactly like the analytics, accounts and boosters seeders. These are invented
orders about invented boosters (see the warning at the top of src/data.py); clear
the store and let only real Stripe fulfilments write to it before launch.

Writing to a configured Upstash store requires --force: the default target is the
local NDJSON file, because seeding production by accident is the wrong surprise.
"""
import argparse
import base64
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import analytics    # noqa: E402
import data as D     # noqa: E402
import orders        # noqa: E402
import pricing       # noqa: E402

# Rough country pools per region word, so a seeded order's country is at least
# plausible for the region it was placed from. Placeholder like everything else.
_REGION_COUNTRIES = {
    "North America": ["US", "CA", "MX"], "Europe": ["DE", "FR", "GB", "ES", "SE", "PL"],
    "Europe West": ["FR", "GB", "DE", "NL", "ES"], "EU Nordic & East": ["SE", "FI", "PL", "NO"],
    "Oceania": ["AU", "NZ"], "Asia": ["JP", "KR", "SG", "PH"], "Korea": ["KR"],
    "Latin America": ["BR", "AR", "CL"], "South America": ["BR", "AR", "CO"],
    "Brazil": ["BR"], "China": ["CN"], "Southeast Asia": ["SG", "PH", "TH"],
    "North America East": ["US", "CA"], "North America West": ["US", "CA"],
    "Europe East": ["PL", "RO", "UA"],
}
_STATUS_WEIGHTS = [("delivered", 42), ("in_progress", 20), ("assigned", 14),
                   ("paid", 12), ("unclaimed", 6), ("refunded", 6)]
_COSRC = ["edge", "tz", "locale"]
_NOTES = ["", "", "", "Please play evenings CET only.", "No ranked flex, solo queue only.",
          "Keep my main runes.", "Ping me before each session.", "Duo voice optional."]


def _weighted(rng, pairs):
    r = rng.uniform(0, sum(w for _, w in pairs))
    for val, w in pairs:
        r -= w
        if r <= 0:
            return val
    return pairs[-1][0]


def _order_id(rng):
    raw = bytes(rng.getrandbits(8) for _ in range(4))
    return "ESB-" + base64.b32encode(raw).decode().rstrip("=")[:6]


def _boosters_for(slug):
    return [b["handle"] for b in D.BOOSTERS if b.get("slug") == slug]


def _fake_email(rng, handle):
    dom = rng.choice(["gmail.com", "outlook.com", "proton.me", "icloud.com", "yahoo.com"])
    return "%s%d@%s" % (handle, rng.randint(2, 998), dom)


def _make_order(rng, now):
    g = rng.choice(D.GAMES)
    ladder = g["ladder"]
    services = ["division"] * 6
    if "win" in g["services"].lower():
        services += ["wins"] * 2
    if "placement" in g["services"].lower():
        services += ["placements"] * 2
    if "coaching" in g["services"].lower():
        services += ["coaching"] * 1
    service = rng.choice(services)

    mode = "Duo queue" if rng.random() < 0.28 else "Piloted"
    region = rng.choice(g.get("regions") or ["Global"])
    country = rng.choice(_REGION_COUNTRIES.get(region, ["US", "GB", "DE"]))
    currency = "eur" if rng.random() < 0.4 else "usd"
    addons = [a["id"] for a in D.ADDONS if a["id"] != "offline" and rng.random() < 0.32]
    if rng.random() < 0.35:
        addons.append("offline")
    promo = "SPLIT15" if rng.random() < 0.45 else ""

    state = {"game": g["name"], "service": service, "mode": mode,
             "addons": addons, "promo": promo}

    row = {"game": g["name"], "slug": g["slug"], "service": service, "mode": mode,
           "region": region, "country": country, "cosrc": rng.choice(_COSRC),
           "currency": currency, "addons": addons, "promo": promo,
           "notes": rng.choice(_NOTES), "syn": 1}

    if service == "coaching":
        coach = rng.choice(D.COACHES)
        pack = rng.choice(D.COACH_PACKS)
        state.update(coach=D.COACHES.index(coach), pack=D.COACH_PACKS.index(pack))
        row.update(coach=coach["name"], hours=pack["hours"])
    elif service in ("wins", "placements"):
        frm = rng.choice(ladder)
        units = rng.randint(pricing.UNIT_MIN, pricing.UNIT_MAX)
        state["from"] = frm
        state[service] = units
        row.update(from_rank=frm, units=units)
        if service == "placements" and rng.random() < 0.25:
            state["unranked"] = True
            row["unranked"] = 1
    else:  # division
        i = rng.randint(0, len(ladder) - 2)
        j = rng.randint(i + 1, min(i + 6, len(ladder) - 1))
        state["from"], state["to"] = ladder[i], ladder[j]
        row.update(from_rank=ladder[i], to_rank=ladder[j])

    q = pricing.quote(state)
    if q.get("invalid"):
        return None
    row.update(subtotal=q["subtotal"], discount=q["discount"], total=q["total"], eta=q["eta"])

    # A named booster on some orders, but only one who actually plays this game.
    pool = _boosters_for(g["slug"])
    if pool and rng.random() < 0.55:
        row["booster"] = rng.choice(pool)

    row["status"] = _weighted(rng, _STATUS_WEIGHTS)
    row["order_id"] = _order_id(rng)
    # Spread the orders back over the window, newest-heavy.
    age_days = int(rng.random() ** 1.7 * 45)
    row["at"] = now - age_days * 86400 - rng.randint(0, 86400)
    row["email"] = _fake_email(rng, (row.get("booster") or g["short"]).lower())
    return row


def main():
    ap = argparse.ArgumentParser(description="Seed the orders store with placeholder orders.")
    ap.add_argument("--clear", action="store_true", help="wipe the store first")
    ap.add_argument("--count", type=int, default=120, help="how many orders to generate")
    ap.add_argument("--seed", type=int, default=7, help="RNG seed (reproducible)")
    ap.add_argument("--force", action="store_true",
                    help="allow writing to a configured Upstash store (default is the local file)")
    args = ap.parse_args()

    up = analytics.upstash_config()[0]
    if up and not args.force:
        sys.exit("Refusing to seed a configured Upstash store without --force. "
                 "Unset UPSTASH_* to seed the local file, or pass --force.")

    if args.clear:
        orders.clear()
        print("cleared %s store" % analytics.store_name())

    rng = random.Random(args.seed)
    now = int(time.time())
    rows, tries = [], 0
    while len(rows) < args.count and tries < args.count * 4:
        tries += 1
        r = _make_order(rng, now)
        if r:
            rows.append(r)

    n = orders.append(rows)
    print("seeded %d order(s) into the %s store (%d now stored)"
          % (n, analytics.store_name(), orders.count()))
    if n < len(rows):
        print("  (%d skipped — id collision; run with --clear to reseed)" % (len(rows) - n))


if __name__ == "__main__":
    main()
