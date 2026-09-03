#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load, inspect and prune the account stock — the operator's side of src/stock.py.

    # what the shop sells, and what is on the shelf right now
    python3 site/tools/stock_import.py --status

    # load a batch: one account per line, user:pass
    python3 site/tools/stock_import.py --sku lol-gold --region "Europe West" \
        --file gold-euw.txt

    # …or paste them, ending with Ctrl-D
    python3 site/tools/stock_import.py --sku lol-gold --region EUW

    # look before you write
    python3 site/tools/stock_import.py --sku lol-iron --region EUW -f x.txt --dry-run

    # the credentials of one unit (after a failed handover)
    python3 site/tools/stock_import.py --reveal u_XXXXXXXX

    # put a refunded order's account back on the shelf
    python3 site/tools/stock_import.py --restock u_XXXXXXXX

    # delete the logins of anything sold longer ago than the warranty window
    python3 site/tools/stock_import.py --purge-sold 400

The line format is `user:pass`, with two optional fields:

    user:pass
    user:pass:inbox@mail.com
    user:pass:inbox@mail.com:inboxpassword

Blank lines and `#` comments are skipped. If a password contains a colon, use
`user|pass` (or a tab) on that line instead — the separator is chosen per line
and an ambiguous split is reported rather than guessed, because a silently
truncated password is discovered by the customer.

⚠ THE FILE YOU IMPORT IS A LIST OF LIVE LOGINS. Shred it afterwards, and keep it
out of the repo — `*.txt` in this directory is not gitignored for you.

⚠ WRITING TO A CONFIGURED UPSTASH STORE NEEDS --force. That is where real stock
lives, so this is the one seeder-shaped tool whose --force you will use in
anger; the guard is there so a stray run against a loaded `.env` cannot rewrite
production inventory by accident.

A developer/operator script: never part of a build or a deploy, like everything
else in site/tools/.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

# The same .env loader serve.py uses, so this writes to the store the running
# server reads.
for _path in (os.path.join(os.path.dirname(ROOT), ".env"), os.path.join(ROOT, ".env")):
    try:
        with open(_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

import analytics    # noqa: E402
import data as D    # noqa: E402
import stock        # noqa: E402


def _region(name):
    """Accept the shard's own name or the code the cards print ("EUW")."""
    name = (name or "").strip()
    for rg in D.ACCOUNT_REGIONS:
        if name.lower() in (rg.lower(), D.account_code(rg).lower()):
            return rg
    return name


def _status():
    amap = stock.available_map()
    live = stock.has_data()
    print("store: %s%s" % (stock.store_name(),
                           "" if live else "  (EMPTY — the shop is still quoting "
                                           "data.py's hand-set figures)"))
    print("")
    head = "%-22s %-22s" % ("listing", "id")
    for rg in D.ACCOUNT_REGIONS:
        head += " %5s" % D.account_code(rg)
    print(head + "   sold")
    print("-" * (len(head) + 7))
    sold = {}
    for r in stock.read():
        if r.get("status") == stock.SOLD:
            sold[r["sku"]] = sold.get(r["sku"], 0) + 1
    for a in D.ACCOUNTS:
        line = "%-22s %-22s" % (a["name"][:22], a["id"][:22])
        for rg in D.ACCOUNT_REGIONS:
            n = amap.get("%s|%s" % (a["id"], rg), 0)
            known = stock.known(a["id"], rg) if live else False
            line += " %5s" % (str(n) if known or n else "·")
        print(line + "   %4d" % sold.get(a["id"], 0))
    print("")
    print("· = never loaded, so that listing still sells on data.py's figure.")
    print("%d unit(s) stored · %d available · %d sold"
          % (stock.count(), stock.total_available(amap),
             sum(sold.values())))
    undelivered = [r for r in stock.read()
                   if r.get("status") == stock.SOLD and not r.get("mailed")
                   and not r.get("purged")]
    if undelivered:
        print("")
        print("⚠ %d SOLD UNIT(S) WERE NEVER MAILED — hand them over:" % len(undelivered))
        for r in undelivered[:20]:
            print("   %s  %-18s %-16s %s"
                  % (r["id"], stock.listing_name(r["sku"]), r.get("order_id", ""),
                     r.get("buyer", "")))


def main():
    ap = argparse.ArgumentParser(
        description="Load and manage the account stock store.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sku", help="listing id, e.g. lol-gold (see --list)")
    ap.add_argument("--region", help='shard name or code, e.g. "Europe West" or EUW')
    ap.add_argument("-f", "--file", help="file of user:pass lines (default: stdin)")
    ap.add_argument("--note", default="", help="a note stored on every unit in this batch")
    ap.add_argument("--list", action="store_true", help="list the listing ids and shards")
    ap.add_argument("--status", action="store_true", help="what is on the shelf")
    ap.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    ap.add_argument("--reveal", metavar="UNIT", help="print one unit's full credentials")
    ap.add_argument("--restock", metavar="UNIT", help="put a sold/held unit back on sale")
    ap.add_argument("--hold", metavar="UNIT", help="take a unit off sale without deleting it")
    ap.add_argument("--purge-sold", nargs="?", type=int, const=400, metavar="DAYS",
                    help="blank the credentials of units sold over DAYS ago (default 400)")
    ap.add_argument("--clear", action="store_true", help="WIPE the whole store")
    ap.add_argument("--force", action="store_true",
                    help="allow writing to a configured Upstash store")
    args = ap.parse_args()

    up = analytics.upstash_config()[0]
    writing = bool(args.file or args.sku or args.clear or args.restock
                   or args.hold or args.purge_sold is not None) and not args.dry_run
    if up and writing and not args.force:
        sys.exit("Refusing to write to the configured Upstash store without --force.\n"
                 "That is production inventory. Re-run with --force if you mean it.")

    if args.list:
        print("listings:")
        for a in D.ACCOUNTS:
            print("  %-22s %-22s %s" % (a["id"], a["name"], a["tier"]))
        print("\nservers:")
        for rg in D.ACCOUNT_REGIONS:
            print("  %-6s %s" % (D.account_code(rg), rg))
        return

    if args.status:
        return _status()

    if args.reveal:
        row = stock.reveal(args.reveal)
        if not row:
            sys.exit("no unit %r" % args.reveal)
        print("⚠ live credentials — do not paste these anywhere they are stored.\n")
        for k in ("id", "listing", "region", "status", "login", "password", "email",
                  "email_password", "note", "order_id", "buyer"):
            if row.get(k):
                print("  %-16s%s" % (k, row[k]))
        if row.get("sold_at"):
            print("  %-16s%s" % ("sold",
                                 time.strftime("%Y-%m-%d %H:%M UTC",
                                               time.gmtime(row["sold_at"]))))
        print("  %-16s%s" % ("mailed", "yes" if row.get("mailed") else "NO"))
        return

    if args.restock:
        row = stock.restock(args.restock)
        if not row:
            sys.exit("no unit %r, or it is already on sale" % args.restock)
        print("%s is back on sale (%s · %s)"
              % (row["id"], stock.listing_name(row["sku"]), row["region"]))
        return

    if args.hold:
        row = stock.hold(args.hold)
        if not row:
            sys.exit("no available unit %r" % args.hold)
        print("%s is off sale (still stored, still revealable)" % row["id"])
        return

    if args.purge_sold is not None:
        n = stock.purge_sold(args.purge_sold)
        print("purged the credentials of %d unit(s) sold over %d days ago"
              % (n, args.purge_sold))
        return

    if args.clear:
        stock.clear()
        print("cleared the %s stock store" % stock.store_name())
        if not (args.sku and args.region):
            return

    if not args.sku or not args.region:
        ap.error("--sku and --region are required to import "
                 "(try --list, or --status)")

    region = _region(args.region)
    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        if sys.stdin.isatty():
            print("Paste %s accounts for %s as user:pass, one per line. Ctrl-D to finish."
                  % (args.sku, region))
        text = sys.stdin.read()

    rows, errors = stock.parse_lines(text, args.sku, region, note=args.note)
    for n, msg in errors:
        print("  line %-4s %s" % (n or "-", msg), file=sys.stderr)
    if not rows:
        sys.exit("nothing to import (%d error(s))" % len(errors))

    if args.dry_run:
        print("would import %d unit(s) of %s on %s:"
              % (len(rows), stock.listing_name(args.sku), region))
        for r in rows[:10]:
            print("   %s  %s" % (stock._mask(r["login"]), "•" * 8))
        if len(rows) > 10:
            print("   … and %d more" % (len(rows) - 10))
        return

    res = stock.add(rows)
    print("imported %d unit(s) of %s on %s into the %s store"
          % (res["added"], stock.listing_name(args.sku), region, stock.store_name()))
    if res["duplicate"]:
        print("  (%d skipped — that login is already stored on this shard)"
              % res["duplicate"])
    if errors:
        print("  (%d line(s) rejected — see above)" % len(errors))
    print("  %s now has %d available on %s"
          % (args.sku, stock.available(args.sku, region), region))


if __name__ == "__main__":
    main()
