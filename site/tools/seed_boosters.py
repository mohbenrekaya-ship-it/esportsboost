#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill the roster store from data.py's placeholder BOOSTERS so the dynamic
boosters board, the "On shift now" rail and the "Delivered today" feed have
something to serve.

    python3 site/tools/seed_boosters.py --clear

Every row this writes carries `"syn": 1`, exactly like the analytics and accounts
seeders — the public payload reports it (`syn`) and the /ops Boosters tab shows a
standing "synthetic data" banner while any are present. That marker is the point:
these fifty boosters are invented (see the warning at the top of src/data.py), and
a seeded roster is exactly the kind of thing that quietly becomes real. Do not
remove the flag, and clear the store and load the real roster before launch.

Writing to a configured Upstash store requires --force: the default target is the
local NDJSON file, because seeding production by accident is the wrong kind of
surprise.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import analytics    # noqa: E402
import boosters     # noqa: E402
import data as D    # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Seed the roster store from data.py's BOOSTERS.")
    ap.add_argument("--clear", action="store_true", help="wipe the store first")
    ap.add_argument("--force", action="store_true",
                    help="allow writing to a configured Upstash store (default target is the local file)")
    args = ap.parse_args()

    up = analytics.upstash_config()[0]
    if up and not args.force:
        sys.exit("Refusing to seed a configured Upstash store without --force. "
                 "Unset UPSTASH_* to seed the local file, or pass --force.")

    if args.clear:
        boosters.clear()
        print("cleared %s store" % analytics.store_name())

    rows = []
    for b in D.BOOSTERS:
        row = boosters.clean_booster(dict(b, syn=1))
        if row:
            rows.append(row)

    n = boosters.append(rows)
    print("seeded %d booster(s) into the %s store (%d in data.py, %d now stored)"
          % (n, analytics.store_name(), len(D.BOOSTERS), boosters.count()))
    if n < len(rows):
        print("  (%d skipped — already present; run with --clear to reseed)" % (len(rows) - n))


if __name__ == "__main__":
    main()
