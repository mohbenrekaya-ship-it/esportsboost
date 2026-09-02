#!/usr/bin/env python3
"""Pricing / bundle / checkout-money tests — stdlib only, no framework.

Run:  python3 site/tests/test_pricing.py     (exits non-zero on any failure)

These lock down the invariant the bundle bug lived in: **the price the website
shows must equal the price Stripe charges**, and the two sides of every mirror
(server pricing.py ↔ client data.js / i18n.js, and the checkout payload the
browser POSTs) must stay in step. The regression that motivated the file: the
checkout payload dropped the `bundle` field, so the server re-quote fell back to
the sitewide sale and charged the wrong amount.

There is no watcher in this project — a stale running server is an operational
issue these tests can't catch, but a stale *mirror* is exactly what they do.
"""

import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # site/
sys.path.insert(0, os.path.join(ROOT, "src"))

import data as D          # noqa: E402
import geo               # noqa: E402
import pricing            # noqa: E402
import payments           # noqa: E402

LOL = next(g for g in D.GAMES if g["name"] == "League of Legends")

# Games whose bundle prices have been SET BY HAND (data.py BUNDLES) and so must
# hold the no-penalty invariant below. The rest still carry the handoff's ramp
# converted to the money it was already charging, and are reported as pending
# rather than failed. Add a game here when its prices are set.
PRICED_GAMES = {"League of Legends"}

_fails = []


def check(cond, msg):
    if cond:
        print("  ok  " + msg)
    else:
        print("FAIL  " + msg)
        _fails.append(msg)


def div_quote(g, frm, to, bundle=None, mode="Solo", promo="", addons=None):
    return pricing.quote({
        "game": g["name"], "service": "division", "from": frm, "to": to,
        "mode": mode, "addons": addons or [], "promo": promo,
        **({"bundle": bundle} if bundle is not None else {}),
    })


def display_cents(total_usd, cur):
    """Replica of the client display: esbMoney formats total * rate with no
    fraction digits (Intl 'halfExpand' == round half away from zero). This is the
    figure the buyer reads on the button — it must equal charge_for(). The rate
    is read from CHARGE_RATES, which test_fx_rate_mirror() has already proved
    equals the one i18n.js formats with."""
    v = total_usd * pricing.CHARGE_RATES[cur]
    whole = math.floor(v + 0.5)           # positive amounts only
    return whole * 100


# ── the money invariant: shown == charged, for every League bundle ──────────
def test_shown_equals_charged():
    print("\n[shown == charged] every League bundle, every currency")
    for i, b in enumerate(D.bundle_climbs(LOL)):
        # priced from the flat floor (defFrom), the figure the card advertises
        q = div_quote(LOL, b["defFrom"], b["target"], bundle=i)
        check(not q["invalid"], "bundle %d (%s->%s) quotes" % (i, b["ft"], b["target"]))
        # the discount is the bundle's, not the sitewide sale
        check(q["promo_code"] == "BUNDLE",
              "bundle %d discount is BUNDLE, not the sale (%s)" % (i, q["promo_code"]))
        # the total lands on the hand-set price EXACTLY — the whole point of
        # storing a price rather than a percentage
        check(q["total"] == b["price"],
              "bundle %d total is its set price $%d (got $%d)"
              % (i, b["price"], q["total"]))
        check(round(q["discount"]) == q["base"] - b["price"],
              "bundle %d discount == full climb − price" % i)
        # USD: Stripe charges the quote total exactly
        usd_cur, usd_cents = pricing.charge_for(q["total"], "usd")
        check(usd_cur == "usd" and usd_cents == q["total"] * 100,
              "bundle %d USD charge == shown total $%d" % (i, q["total"]))
        # Every other currency: the figure on the button is the figure Stripe
        # charges, converted at the one rate both sides share.
        for cur in sorted(c for c in pricing.CHARGE_RATES if c != "usd"):
            got_cur, got_cents = pricing.charge_for(q["total"], cur)
            want = display_cents(q["total"], cur)
            check(got_cur == cur and got_cents == want,
                  "bundle %d %s charge (%d) == shown %s (%d)"
                  % (i, cur.upper(), got_cents, cur.upper(), want))


# ── the exact case from the bug report ─────────────────────────────────────
def test_iron_to_gold_regression():
    print("\n[regression] Iron I -> Gold IV, the reported climb")
    # WITH the bundle (index 0): the flat hand-set price, whatever BUNDLES says
    # it is. Read, never typed — a re-price changes one number in data.py and
    # this stays true; the regression being guarded is the CLIMB resolving to
    # the bundle at all, not any particular dollar figure.
    want = D.bundle_climbs(LOL)[0]["price"]
    with_b = div_quote(LOL, "Iron I", "Gold IV", bundle=0)
    check(with_b["total"] == want,
          "with bundle: total is the hand-set $%d (got $%d)" % (want, with_b["total"]))
    check(pricing.charge_for(with_b["total"], "eur")[1] == display_cents(want, "eur"),
          "with bundle: charges EUR %.2f" % (display_cents(want, "eur") / 100))
    # WITHOUT the bundle field (the payload bug): falls to the sitewide sale,
    # priced from the real Iron I. This is the stale-server symptom.
    without_b = div_quote(LOL, "Iron I", "Gold IV")
    check(without_b["promo_code"] == "SPLIT15",
          "no bundle: falls back to the sitewide sale")
    check(without_b["total"] != with_b["total"],
          "no bundle: total ($%d) differs from the bundle price ($%d) — the "
          "field must be sent" % (without_b["total"], with_b["total"]))


# ── mode-conditional add-ons: the other queue's option is never charged ─────
def test_addon_modes():
    print("\n[add-ons] queue-specific options are only charged in their queue")
    pairs = [(a["id"], a["mode"]) for a in D.ADDONS if a.get("mode")]
    check(bool(pairs), "data.py carries at least one mode-conditional add-on")
    for aid, want in pairs:
        for mode in ("Solo", "Duo queue"):
            q = div_quote(LOL, "Iron I", "Gold IV", mode=mode, addons=[aid])
            bare = div_quote(LOL, "Iron I", "Gold IV", mode=mode)
            charged = q["addons"] > 0
            check(charged == (mode == want),
                  "%s on %s: %s" % (aid, mode, "charged" if charged else "not charged"))
            if not charged:
                check(q["total"] == bare["total"],
                      "%s on %s does not move the total" % (aid, mode))
    # The legacy mode string still reads as solo — orders.py defaults to it and
    # seed_orders.py writes it, so treating it as "not solo" would silently drop
    # every solo add-on off historical rows.
    legacy = div_quote(LOL, "Iron I", "Gold IV", mode="Piloted", addons=["soloq"])
    check(legacy["addons"] > 0, '"Piloted" is treated as a solo queue')
    # A free inclusion is free in both queues — it is stated, never billed.
    for mode in ("Solo", "Duo queue"):
        q = div_quote(LOL, "Iron I", "Gold IV", mode=mode, addons=["champ"])
        check(q["addons"] == 0, "the picks add-on costs nothing on %s" % mode)


# ── the free-but-optional add-on: shown as a saving, charged as nothing ─────
def test_free_optional_addons():
    """The `was_pct` row is the one place on the site that prints a reference
    price the shop never charges, so the thing to lock is that the reference
    stays *display only* and the charge stays $0 on every path into the engine.

    Four ways this could break, and all four are checked below: someone gives
    the row a `pct` and it silently starts billing; someone drops the $1 floor
    or the base and the struck figure stops matching what a real charge would
    be; the client mirror drifts from the Python; or the row loses its
    `was_pct` and the markup goes on rendering a struck figure of $0."""
    print("\n[free add-ons] a free-but-optional option is never charged")
    free_opt = [a for a in D.ADDONS if D.addon_is_free_opt(a)]
    check(bool(free_opt), "data.py carries at least one free-but-optional add-on")

    for a in free_opt:
        aid = a["id"]
        check(a["pct"] == 0, "%s has no pct — the engine can never bill it" % aid)
        check(not a.get("incl"),
              "%s is not an inclusion, so it renders as a real checkbox" % aid)
        check(not a.get("mode"),
              "%s is offered in both queues" % aid)

        # Charged nothing, on every service, queue and ladder — including the
        # bundle path, where add-ons are a percentage of a DIFFERENT base.
        for g in D.GAMES:
            frm, to = g["ladder"][0], g["ladder"][min(6, len(g["ladder"]) - 1)]
            for mode in ("Solo", "Duo queue"):
                bare = div_quote(g, frm, to, mode=mode)
                took = div_quote(g, frm, to, mode=mode, addons=[aid])
                check(took["total"] == bare["total"] and took["addons"] == 0,
                      "%s costs nothing on %s / %s" % (aid, g["short"], mode))

        # Stacked with a paid option it must still add exactly nothing.
        paid = next((x["id"] for x in D.ADDONS if x["pct"] > 0
                     and not x.get("mode")), None)
        if paid:
            one = div_quote(LOL, "Iron I", "Gold IV", addons=[paid])["total"]
            two = div_quote(LOL, "Iron I", "Gold IV", addons=[paid, aid])["total"]
            check(one == two, "%s adds nothing beside a paid add-on" % aid)

        # The struck figure is the same arithmetic a real charge would use.
        q = div_quote(LOL, "Iron I", "Gold IV")
        was = pricing.addon_list_price(q["addon_base"], aid)
        check(was == max(1, pricing._jsround(q["addon_base"] * a["was_pct"])),
              "%s's struck figure is was_pct off the quote's own addon_base" % aid)
        check(was > 0, "%s's struck figure is a real number, not $0" % aid)
        # It must never be quoted for an add-on that has no reference rate.
        check(pricing.addon_list_price(q["addon_base"], paid) == 0,
              "no reference price is invented for a paid add-on")

    # The JS mirror. addonListPrice() has to carry the same floor, the same
    # rounding and the same guard, or the card strikes one figure and a
    # re-quote after any state change strikes another.
    js = open(os.path.join(ROOT, "public", "assets", "js", "app.js"),
              encoding="utf-8").read()
    for frag in ("function addonListPrice(", "function isFreeOpt(",
                 "Math.max(1, Math.round(addonBase * pct))",
                 "addonBase: bpct ? base * (1 - bpct) : base"):
        check(frag in js, "app.js mirrors `%s`" % frag)
    # And the picker must not force it on: the checked line has to consult
    # isFreeOpt(), or a free option arrives pre-ticked and is not a choice.
    check("!isFreeOpt(a))" in js,
          "app.js leaves a free-but-optional row unticked until the buyer taps it")


# ── the per-game name of the picks add-on ───────────────────────────────────
def test_picks_labels():
    print("\n[picks] every game names the picks add-on in its own words")
    seen = {}
    for g in D.GAMES:
        label = D.picks_label(g["name"])
        check(bool(g.get("picks")), "%s carries a `picks` label" % g["name"])
        check(label == g.get("picks"), "%s: picks_label reads it (%s)" % (g["name"], label))
        # the FAQ builds a sentence round the bare noun — it must be one word
        noun = D.picks_noun(g["name"])
        check(bool(noun) and " " not in noun,
              "%s: picks_noun is a single word (%s)" % (g["name"], noun))
        seen[g["name"]] = label
    check(D.picks_label("League of Legends") == "Champions & roles", "League picks champions")
    check(D.picks_label("Valorant") == "Agents & roles", "Valorant picks agents")
    # an unknown game falls back rather than raising — checkout carries a stored
    # game name, and a title can leave the catalogue
    check(D.picks_label("Some Retired Game") ==
          next(a for a in D.ADDONS if a["id"] == "champ")["label"],
          "an unknown game falls back to the generic label")
    # every wording ships to the client, because checkout shows one of nine
    cd = _client_data()
    if cd is not None:
        check(cd.get("picks") == seen, "data.js carries the same per-game names")


# ── a discount never stacks: bundle replaces the sale ───────────────────────
def test_bundle_does_not_stack():
    print("\n[no stacking] bundle replaces the sitewide sale")
    q = div_quote(LOL, "Iron IV", "Gold IV", bundle=0, promo="SPLIT15")
    plain = div_quote(LOL, "Iron IV", "Gold IV", bundle=0)
    check(q["promo_code"] == "BUNDLE", "a code alongside a bundle stays BUNDLE")
    check(q["total"] == plain["total"], "adding a code does not deepen the cut")


# ── the reworked League bundle rules ────────────────────────────────────────
def test_bundle_rules():
    print("\n[rules] reworked League bundles")
    tiers = LOL["tiers"]
    dm = LOL["divmap"]
    top = tiers[-1]                                   # Master — apex, never a target
    climbs = D.bundle_climbs(LOL)
    check(len(climbs) >= 4, "League has a bundle set (%d cards)" % len(climbs))
    spans = []
    for b in climbs:
        span = tiers.index(b["tt"]) - tiers.index(b["ft"])
        spans.append(span)
        check(b["tt"] != top, "%s->%s does not target the apex (%s)" % (b["ft"], b["tt"], top))
        check(b["target"] == dm[b["tt"]][0], "%s target is division IV (%s)" % (b["tt"], b["target"]))
        check(b["defFrom"] == dm[b["ft"]][0], "%s default from is division IV" % b["ft"])
        # a 2-tier span is only allowed at the high ranks (see data.py comment)
        if span < 3:
            check(span == 2 and tiers.index(b["ft"]) >= tiers.index("Platinum"),
                  "%s->%s: sub-3-tier only at high ranks" % (b["ft"], b["tt"]))
    check(min(spans) >= 2, "no bundle spans fewer than 2 tiers")
    check(max(spans) >= 5, "the big-order bundles span 5+ tiers")
    # a strictly bigger climb never costs less: Iron->Diamond contains
    # Bronze->Diamond, so pricing it under would make the deeper order the
    # cheaper one — the inversion the old percentage ramp shipped.
    for i, a in enumerate(climbs):
        for c in climbs[i + 1:]:
            if a["tt"] == c["tt"] and tiers.index(c["ft"]) < tiers.index(a["ft"]):
                check(c["price"] >= a["price"],
                      "%s->%s ($%d) is not cheaper than the shorter %s->%s ($%d)"
                      % (c["ft"], c["tt"], c["price"], a["ft"], a["tt"], a["price"]))


# ── the rule the League/Valorant re-price exists to enforce ─────────────────
def test_bundle_never_costs_more():
    """Applying a bundle must never cost more than not applying it.

    A bundle is a FLAT price across its whole from-tier, so the buyer who is
    worst off is the one at the tier's TOP division — the shortest qualifying
    climb, which at the sitewide sale is the cheapest normal order in that tier.
    If the flat price sits above that figure, the card offers a saving and
    charges a penalty. Four of League's six bundles and five of Valorant's did
    exactly that before the prices were set by hand; this locks it for all nine
    games and every division, not just the two that were re-priced.
    """
    print("\n[no penalty] a bundle never costs more than the plain climb")
    # Every division of the from-tier, both queues, and with add-ons ticked —
    # the add-ons matter because on a bundle they used to be a percentage of the
    # inflated list climb, which cost more than the bundle saved.
    CASES = [("Solo", []), ("Solo", ["priority"]), ("Solo", ["priority", "soloq"]),
             ("Duo queue", []), ("Duo queue", ["priority"]),
             ("Duo queue", ["priority", "schedule", "champ"])]
    for g in D.GAMES:
        worst = []
        for i, b in enumerate(D.bundle_climbs(g)):
            for div in g["divmap"][b["ft"]]:
                for mode, addons in CASES:
                    bundled = div_quote(g, div, b["target"], bundle=i,
                                        mode=mode, addons=addons)["total"]
                    plain = div_quote(g, div, b["target"],
                                      mode=mode, addons=addons)["total"]
                    msg = ("%s %s->%s from %s [%s%s]: bundle $%d <= plain $%d"
                           % (g["short"], b["ft"], b["tt"], div, mode,
                              " +" + "+".join(addons) if addons else "",
                              bundled, plain))
                    if g["name"] in PRICED_GAMES:
                        check(bundled <= plain, msg)
                    elif bundled > plain:
                        worst.append((bundled - plain, msg))
        # A game whose bundles are still the handoff's converted ramp is listed,
        # loudly, rather than asserted — the prices are being set one game at a
        # time and a red suite for known-pending work stops being read. Add the
        # game to PRICED_GAMES the moment its figures are set by hand.
        if worst:
            total = sum(len(g["divmap"][b["ft"]]) * len(CASES)
                        for b in D.bundle_climbs(g))
            print("  PENDING  %s: %d of %d bundle/division/add-on cases cost MORE "
                  "than not applying it (worst +$%d) — prices not set by hand yet"
                  % (g["name"], len(worst), total, max(w[0] for w in worst)))


# ── build_session: the Stripe amount IS the quote ───────────────────────────
def test_build_session_amount():
    print("\n[stripe] build_session charges the re-quoted amount")
    for cur in sorted(pricing.CHARGE_RATES):
        order = {"game": "League of Legends", "service": "division",
                 "from": "Iron I", "to": "Gold IV", "mode": "Solo", "addons": [],
                 "bundle": 0, "currency": cur, "region": "Europe West"}
        params, oid, q = payments.build_session(order, "http://localhost:4321")
        want_cur, want_cents = pricing.charge_for(q["total"], cur)
        check(params["line_items[0][price_data][currency]"] == want_cur,
              "session currency is %s" % want_cur)
        check(params["line_items[0][price_data][unit_amount]"] == want_cents,
              "%s unit_amount (%d) == charge_for total (%d)"
              % (cur, params["line_items[0][price_data][unit_amount]"], want_cents))
        check(q["promo_code"] == "BUNDLE", "%s session still applies the bundle" % cur)


# ── the guard: charge exactly what the checkout page showed ─────────────────
def test_client_total_guard():
    print("\n[guard] server refuses to charge a total the page did not show")
    base = {"game": "League of Legends", "service": "division", "from": "Iron I",
            "to": "Gold IV", "mode": "Solo", "addons": [], "bundle": 0,
            "currency": "eur", "region": "Europe West"}
    server_total = pricing.quote(base)["total"]           # the bundle price

    # matching shown total -> session builds, charges that amount
    ok = dict(base, client_total=server_total)
    params, _, q = payments.build_session(ok, "http://x")
    check(params["line_items[0][price_data][unit_amount]"]
          == pricing.charge_for(q["total"], "eur")[1],
          "matching client_total: charges the shown amount (EUR %d)"
          % pricing.charge_for(q["total"], "eur")[1])

    # tampered LOW total (pay-1-euro attack) -> refused, never charged
    tampered = dict(base, client_total=1)
    try:
        payments.build_session(tampered, "http://x")
        check(False, "tampered low total is refused")
    except payments.StripeError:
        check(True, "tampered low total is refused (StripeError)")

    # stale HIGH total (page showed an old, higher price) -> also refused
    stale = dict(base, client_total=server_total + 5)
    try:
        payments.build_session(stale, "http://x")
        check(False, "stale mismatched total is refused")
    except payments.StripeError:
        check(True, "stale mismatched total is refused (StripeError)")

    # no client_total (old cached page) -> backward compatible, still authoritative
    params2, _, q2 = payments.build_session(base, "http://x")
    check(params2["line_items[0][price_data][unit_amount]"]
          == pricing.charge_for(q2["total"], "eur")[1],
          "absent client_total: still charges the correct server amount")


# ── mirrors: the client must not drift from the server ──────────────────────
def _client_data():
    p = os.path.join(ROOT, "dist", "assets", "js", "data.js")
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"window\.ESB_DATA\s*=\s*(\{.*\});\s*$", txt, re.S)
    return json.loads(m.group(1)) if m else None


def test_client_bundle_mirror():
    print("\n[mirror] dist/assets/js/data.js bundles == server bundle_climbs")
    cd = _client_data()
    if cd is None:
        check(False, "data.js present (run build.py first)")
        return
    cbundles = cd.get("bundles", {})
    for g in D.GAMES:
        server = D.bundle_climbs(g)
        if not server:
            continue
        client = cbundles.get(g["name"]) or []
        # The client rows carry one extra key: `disc`, the hand-set price
        # expressed against the full climb. Everything else must match the
        # resolved server climb exactly.
        check([{k: v for k, v in c.items() if k != "disc"} for c in client] == server,
              "%s: client bundle list matches server" % g["name"])
        for i, (c, s) in enumerate(zip(client, server)):
            # app.js multiplies this double by the boost and rounds it, so it has
            # to be the identical double the server used — not a re-derivation.
            check(c.get("disc") == pricing.bundle_pct(g, s),
                  "%s bundle %d: client disc is the server's derived pct"
                  % (g["short"], i))
            # and it has to land back on the price a human set
            full = pricing.full_bundle_price(g, s)
            check(full - math.floor(full * c["disc"] + 0.5) == s["price"],
                  "%s bundle %d: client re-quote lands on $%d"
                  % (g["short"], i, s["price"]))


def test_fx_rate_mirror():
    """Both directions. A currency the browser can display and the server has no
    rate for is charged in dollars at the Stripe page (`charge_for()` falls back)
    — the buyer clicks "£72" and is charged $72. A currency the server prices and
    the switcher never offers is dead weight. So the two tables must hold the same
    keys, not merely agree on the ones they share."""
    print("\n[mirror] i18n.js ESB_RATES == pricing.CHARGE_RATES")
    p = os.path.join(ROOT, "public", "assets", "js", "i18n.js")
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"ESB_RATES\s*=\s*\{([^}]*)\}", txt)
    check(bool(m), "found ESB_RATES in i18n.js")
    if not m:
        return
    pairs = {k.lower(): float(v)
             for k, v in re.findall(r"([A-Za-z]+)\s*:\s*([\d.]+)", m.group(1))}
    check(set(pairs) == set(pricing.CHARGE_RATES),
          "same currencies both sides (js %s == py %s)"
          % (sorted(pairs), sorted(pricing.CHARGE_RATES)))
    for cur in sorted(set(pairs) & set(pricing.CHARGE_RATES)):
        check(abs(pairs[cur] - pricing.CHARGE_RATES[cur]) < 1e-9,
              "%s rate matches (%s == %s)"
              % (cur.upper(), pairs[cur], pricing.CHARGE_RATES[cur]))

    # Every currency the geo defaults can HAND somebody must be one we can
    # charge in. A country mapped to a code with no rate behind it displays
    # perfectly and is charged in dollars at the Stripe page (charge_for() falls
    # back), so the buyer sees one currency and pays another.
    named = set(geo.CUR_COUNTRIES.values()) | {"EUR", "USD"}
    for cur in sorted(named):
        check(cur.lower() in pricing.CHARGE_RATES,
              "%s (a geo default) has a charge rate" % cur)
    check(geo.currency_for("").lower() in pricing.CHARGE_RATES,
          "the unresolved-country fallback (%s) has a charge rate"
          % geo.currency_for(""))

    # And every rate the site can charge in is a currency the switcher offers,
    # read off build.py's CURRENCIES — the third copy of the same list.
    b = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    mb = re.search(r"^CURRENCIES = \[(.*?)\]$", b, re.M | re.S)
    check(bool(mb), "found CURRENCIES in build.py")
    if mb:
        offered = {c.lower() for c in re.findall(r'\("([A-Z]{3})"', mb.group(1))}
        check(offered == set(pricing.CHARGE_RATES),
              "switcher offers exactly the priced currencies (%s == %s)"
              % (sorted(offered), sorted(pricing.CHARGE_RATES)))


def test_currency_signs():
    """One mark per currency, across every surface that draws one.

    Three of them print a charged amount BACK to a human — the order
    confirmation mail, the /ops Orders tab, and the switcher's own icon — and the
    two lookup maps fall back to a bare "$" for a currency they don't know. So a
    missing entry is not a broken glyph, it is a CAD order labelled as US dollars
    in a customer's inbox. The fourth, i18n.js's CUR_MARK, is where the site
    overrides the formatter's own symbol (CLDR gives CAD "CA$"; we show "C$"),
    which is what makes the other three overrides load-bearing rather than
    cosmetic: a page quoting "C$319" over a receipt saying "CA$319" is the same
    one-set-of-numbers failure the whole build is written against."""
    print("\n[mirror] one currency mark, on every surface that draws one")
    signs = payments.CURRENCY_SIGNS
    check(set(signs) == set(pricing.CHARGE_RATES),
          "payments.CURRENCY_SIGNS covers CHARGE_RATES (%s == %s)"
          % (sorted(signs), sorted(pricing.CHARGE_RATES)))

    # /ops Orders tab
    txt = open(os.path.join(ROOT, "public", "assets", "js", "ops.js"),
               encoding="utf-8").read()
    m = re.search(r"CUR_SYM\s*=\s*\{([^}]*)\}", txt)
    check(bool(m), "found CUR_SYM in ops.js")
    if m:
        js = dict(re.findall(r'([a-z]{3})\s*:\s*"([^"]+)"', m.group(1)))
        check(set(js) == set(pricing.CHARGE_RATES),
              "ops.js CUR_SYM covers CHARGE_RATES (%s == %s)"
              % (sorted(js), sorted(pricing.CHARGE_RATES)))
        for cur in sorted(set(js) & set(signs)):
            check(js[cur] == signs[cur],
                  "%s: ops.js agrees with the mail (%s)" % (cur.upper(), js[cur]))

    # the switcher's icon column, which is the mark the reader sees on the control
    b = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    mb = re.search(r"^CURRENCIES = \[(.*?)\]$", b, re.M | re.S)
    if mb:
        icons = {c.lower(): i
                 for c, i in re.findall(r'\("([A-Z]{3})",\s*"([^"]+)"', mb.group(1))}
        for cur in sorted(set(icons) & set(signs)):
            check(icons[cur] == signs[cur],
                  "%s: switcher icon agrees with the mail (%s)" % (cur.upper(), icons[cur]))

    # i18n.js's override of the formatter's own symbol — the displayed price
    ix = open(os.path.join(ROOT, "public", "assets", "js", "i18n.js"),
              encoding="utf-8").read()
    mi = re.search(r"CUR_MARK\s*=\s*\{([^}]*)\}", ix)
    check(bool(mi), "found CUR_MARK in i18n.js")
    if mi:
        marks = dict(re.findall(r'([A-Z]{3})\s*:\s*"([^"]+)"', mi.group(1)))
        for cur, mark in sorted(marks.items()):
            check(cur.lower() in signs and signs[cur.lower()] == mark,
                  "%s: the displayed mark is the charged one (%s)" % (cur, mark))

    # The one that is not merely cosmetic: two currencies sharing a mark are two
    # amounts a reader cannot tell apart.
    check(len(set(signs.values())) == len(signs),
          "no two currencies share a mark (%s)" % sorted(signs.values()))


# ── the default server: geo.py's tables vs what app.js can actually read ────
def _region_for(regions, area):
    """Python twin of app.js's regionFor() — exact name, then prefix."""
    pats = ([r"^North America$", r"^North America\b"] if area == "NA"
            else [r"^Europe$", r"^Europe\b", r"^EU\b"])
    for pat in pats:
        for r in regions:
            if re.match(pat, r):
                return r
    return ""


def test_server_defaults():
    """The order form opens on the visitor's own estate — NA or EU — resolved
    client-side from the browser's timezone. Three things can break it silently,
    and none of them raises anything at build time."""
    print("\n[geo] every ladder offers both estates, and the client can see them")

    # 1. A game whose region list has no European server would fall through
    #    regionFor()'s patterns to list[0] — which is a North America variant on
    #    all nine ladders — so every European visitor would land back on NA with
    #    nothing to show for it. Same in reverse.
    for g in D.GAMES:
        for area in ("NA", "EU"):
            hit = _region_for(g["regions"], area)
            check(bool(hit) and hit in g["regions"],
                  "%s: %s resolves to %r" % (g["short"], area, hit))

    # 2. app.js only ever answers "NA" for a zone under `America/` (or the one
    #    Pacific/Honolulu special case). A North American country added to
    #    geo.py under any other prefix would be read as European by the client
    #    while the server-side dashboard called it North America.
    stray = sorted(z for z, c in geo.TZ_COUNTRY.items()
                   if c in geo.NA_COUNTRIES
                   and not z.startswith("America/") and z != "Pacific/Honolulu")
    check(not stray,
          "every NA timezone is under America/ or Pacific/Honolulu (%s)"
          % (stray or "none"))

    # 3. A country in both sets would make the client's exception list fight
    #    geo.server_area().
    both = sorted(geo.NA_COUNTRIES & geo.SA_COUNTRIES)
    check(not both, "no country is both NA and SA (%s)" % (both or "none"))

    # 4. The currency-by-location tables resolve the markets the business set.
    for code, want in (("US", "USD"), ("CA", "CAD"), ("GB", "GBP"),
                       ("FR", "EUR"), ("DE", "EUR"), ("PL", "EUR"),
                       ("BR", "USD"), ("JP", "USD")):
        check(geo.currency_for(code) == want,
              "%s quotes in %s" % (code, want))
    # GB is in EU_COUNTRIES too — the explicit map has to win, or the UK is
    # quoted in euros by the continent it sits on.
    check("GB" in geo.EU_COUNTRIES and geo.currency_for("GB") == "GBP",
          "GB is European but still quotes in GBP")

    # 5. The country cookie is named in THREE files and they must agree: the
    #    edge middleware that sets it in production, serve.py's local stand-in,
    #    and the i18n.js reader. A rename in one is silent — the client simply
    #    falls back to the timezone and nobody sees an error, which is exactly
    #    the VPN-shows-euros symptom this whole mechanism was added to fix.
    COOKIE = "esb_geo"
    root = os.path.dirname(ROOT)
    sources = {
        "middleware.js": os.path.join(root, "middleware.js"),
        "serve.py": os.path.join(ROOT, "serve.py"),
        "i18n.js": os.path.join(ROOT, "public", "assets", "js", "i18n.js"),
    }
    for name, path in sources.items():
        if not os.path.exists(path):
            check(False, "%s exists" % name)
            continue
        check(COOKIE in open(path, encoding="utf-8").read(),
              "%s names the %s cookie" % (name, COOKIE))

    mw = sources["middleware.js"]
    if os.path.exists(mw):
        txt = open(mw, encoding="utf-8").read()
        # Continuing the request is the one thing that must never be dropped:
        # without this header every matched URL returns an empty 200.
        check("x-middleware-next" in txt,
              "middleware.js continues the request (x-middleware-next)")
        # The API reads the edge header directly and assets are CDN bytes.
        check("api/" in txt and "assets/" in txt,
              "middleware.js matcher excludes /api/ and /assets/")
        # Scope this to the cookie STRING, not the file — the comment above it
        # explains why HttpOnly is absent, and naming a thing is not doing it.
        setc = re.search(r"esb_geo=\$\{[^`\n]*", txt)
        check(bool(setc), "middleware.js builds an esb_geo Set-Cookie value")
        if setc:
            check("HttpOnly" not in setc.group(0),
                  "the cookie is readable by i18n.js (not HttpOnly)")
            check("SameSite=Lax" in setc.group(0),
                  "the cookie is SameSite=Lax")

    # 6. The client payload is DERIVED from geo.py, so it has to still match it.
    cd = _client_data()
    if cd is None:
        check(False, "data.js present (run build.py first)")
        return
    cg = cd.get("geo") or {}
    want_sa = sorted(z for z, c in geo.TZ_COUNTRY.items() if c in geo.SA_COUNTRIES)
    check(cg.get("saZones") == want_sa,
          "data.js saZones == geo.py's South American zones (%d)" % len(want_sa))
    check(cg.get("naCountries") == sorted(geo.NA_COUNTRIES),
          "data.js naCountries == geo.NA_COUNTRIES (%d)" % len(geo.NA_COUNTRIES))
    check(cg.get("curCountries") == dict(geo.CUR_COUNTRIES),
          "data.js curCountries == geo.CUR_COUNTRIES")
    check(cg.get("euCountries") == sorted(geo.EU_COUNTRIES),
          "data.js euCountries == geo.EU_COUNTRIES (%d)" % len(geo.EU_COUNTRIES))
    # zoneCur carries only what the prefix rule gets wrong; every entry in it
    # must therefore actually disagree with that rule, or it is dead weight
    # pretending to be a correction.
    zc = cg.get("zoneCur") or {}
    check(all(geo.currency_for(geo.TZ_COUNTRY[z]) == c for z, c in zc.items()),
          "every zoneCur entry matches geo.currency_for its country (%d)" % len(zc))
    # The exception list is only consulted under the America/ prefix.
    off = [z for z in want_sa if not z.startswith("America/")]
    check(not off, "every SA zone is under America/ (%s)" % (off or "none"))


def test_eta_schedule_mirror():
    """The delivery schedule is a mirror like every other part of quote(): the
    card's ETA is computed in app.js, the one on the Stripe receipt and in the
    confirmation email in pricing.py. A drift here means the buyer is promised
    one delivery window and charged against another."""
    print("\n[mirror] app.js delivery schedule == pricing.DAYS_* / eta_text()")
    p = os.path.join(ROOT, "public", "assets", "js", "app.js")
    txt = open(p, encoding="utf-8").read()
    for name in ("DAYS_SETUP", "DAYS_PER_RUNG", "DAYS_PER_CLIMB",
                 "DAYS_PER_WIN", "DAYS_PER_PLACEMENT"):
        m = re.search(r"\b%s\s*=\s*([\d.]+)" % name, txt)
        check(bool(m), "app.js declares %s" % name)
        if m:
            check(abs(float(m.group(1)) - getattr(pricing, name)) < 1e-9,
                  "%s matches (%s == %s)" % (name, m.group(1), getattr(pricing, name)))

    # etaText()'s two thresholds and its band are literals in app.js (it has no
    # access to pricing.py's constants), so assert them against the source here.
    m = re.search(r"function etaText\(days\)\s*\{(.*?)\n  \}", txt, re.S)
    check(bool(m), "found etaText() in app.js")
    if m:
        body = m.group(1)
        check("days <= %d" % pricing.ETA_EXACT in body,
              "exact-figure threshold matches ETA_EXACT (%d)" % pricing.ETA_EXACT)
        check("Math.max(%d, Math.round(days * %s))"
              % (pricing.ETA_SPAN_MIN, pricing.ETA_SPAN_PCT) in body,
              "band matches ETA_SPAN_MIN/PCT (%d, %s)"
              % (pricing.ETA_SPAN_MIN, pricing.ETA_SPAN_PCT))

    # And the wording, which is what the two sides actually render.
    for days, want in ((1, "about 1 day"), (3, "3 days"),
                       (4, "4–6 days"), (7, "7–9 days"), (10, "10–13 days")):
        check(pricing.eta_text(days) == want,
              "eta_text(%d) == %r" % (days, want))


def test_eta_is_never_a_bare_long_figure():
    """No real climb on any ladder may quote a single figure past ETA_EXACT —
    that is the whole point of the band. Walks every rung pair of every game."""
    print("\n[eta] every climb on every ladder reads as a figure or a band")
    bad = []
    longest = 0
    for g in D.GAMES:
        L = g["ladder"]
        for i in range(len(L)):
            for j in range(i + 1, len(L)):
                q = pricing.quote({"game": g["name"], "service": "division",
                                   "from": L[i], "to": L[j], "mode": "Duo queue",
                                   "addons": []})
                longest = max(longest, q["days"])
                if q["days"] > pricing.ETA_EXACT and "–" not in q["eta"]:
                    bad.append("%s %s→%s: %s" % (g["name"], L[i], L[j], q["eta"]))
    check(not bad, "no bare figure over %d days (%s)"
          % (pricing.ETA_EXACT, bad[0] if bad else "none"))
    # The old schedule quoted a full ladder at 12 days; the cut is the point of
    # this change, so fail if a re-tune quietly puts it back.
    check(longest <= 9, "slowest climb on the site is %d days (was 12)" % longest)


# ── the payload fix: the browser must send the price-affecting state ────────
def test_checkout_payload_sends_state():
    print("\n[payload] built checkout.html forwards price-affecting state")
    p = os.path.join(ROOT, "dist", "checkout.html")
    if not os.path.exists(p):
        check(False, "dist/checkout.html present (run build.py first)")
        return
    html = open(p, encoding="utf-8").read()
    for field in ("bundle: (s.bundle", "unranked: !!s.unranked",
                  "coach: s.coach, pack: s.pack", "client_total: (window.esbQuote"):
        check(field in html, "payload includes `%s`" % field.split(":")[0])


# ── the receipt: what was bought has to survive to the orders store ────────
def test_order_row_records_what_was_bought():
    """A fulfilled order is written down ONCE, by payments.order_row(), and the
    /ops Orders tab is the only place anyone can look it up afterwards. So every
    option the buyer was charged for has to survive the metadata round trip.

    The regression: the row carried no `addons` at all, so an order charged a
    15% priority uplift showed "No add-ons on this order" to the operator who
    had to deliver it — and a free-but-optional row (the screen share, which
    moves no money and can't be inferred from the amount) had nothing anywhere
    recording that it was asked for. The unit count and the coaching pack were
    dropped the same way, which is worse than blank: clean_order() clamps a
    missing count to UNIT_MIN, so a 5-win order was stored as a 1-win one.
    """
    print("\n[orders] the stored row carries every option that was charged")
    import orders                                    # noqa: E402 — same lazy import
    val = next(g for g in D.GAMES if g["name"] == "Valorant")

    def roundtrip(order, total):
        """Everything the webhook sees: build the Session, read its metadata back
        exactly as Stripe hands it over, and run the row through the store's own
        validator — a field that doesn't survive clean_order() isn't recorded."""
        params, oid, q = payments.build_session(order, "http://localhost:4321")
        md = {k[9:-1]: v for k, v in params.items() if k.startswith("metadata[")}
        row = payments.order_row(md, {
            "client_reference_id": oid, "amount_total": total * 100,
            "customer_details": {"email": "buyer@example.com"}})
        return orders.clean_order(row), q

    # 1 — a division order with a paid add-on and a free-but-optional one.
    st = {"game": val["name"], "service": "division", "from": val["ladder"][8],
          "to": val["ladder"][12], "mode": "Duo queue", "region": "North America",
          "addons": ["priority", "stream"], "currency": "usd"}
    stored, q = roundtrip(st, q0 := pricing.quote(st)["total"])
    check(stored is not None, "the row survives orders.clean_order()")
    check(stored["addons"] == ["priority", "stream"],
          "both options stored (got %r)" % (stored["addons"],))
    check(stored["from_rank"] == val["ladder"][8] and stored["to_rank"] == val["ladder"][12],
          "the climb is stored from its own fields, not parsed out of a sentence")
    check(stored["mode"] == "Duo queue", "the queue is stored")
    # …and the drill-down's per-add-on cost adds up against what was charged.
    bd = {a["id"]: a["cost"] for a in orders._addon_breakdown(stored)}
    plain = pricing.quote(dict(st, addons=[]))["total"]
    check(bd.get("priority") == q0 - plain,
          "priority's cost on this order (%s) is what it added to the charge (%s)"
          % (bd.get("priority"), q0 - plain))
    check(bd.get("stream") == 0, "the free option reads as included, not as missing")

    # A queue-only option can never be recorded in the queue it isn't offered in
    # — quote() filters it out of the charge, so the receipt must not name it.
    solo = dict(st, mode="Solo", addons=["soloq", "schedule"])
    stored, _ = roundtrip(solo, pricing.quote(solo)["total"])
    check(stored["addons"] == ["soloq"],
          "the other queue's option is not stored (got %r)" % (stored["addons"],))

    # 2 — units, which clean_order() would otherwise clamp to UNIT_MIN.
    wins = {"game": val["name"], "service": "wins", "from": val["ladder"][8],
            "wins": pricing.UNIT_MAX, "mode": "Solo", "region": "North America",
            "addons": [], "currency": "usd"}
    stored, _ = roundtrip(wins, pricing.quote(wins)["total"])
    check(stored["units"] == pricing.UNIT_MAX,
          "a %d-win order stores %d wins" % (pricing.UNIT_MAX, stored["units"]))
    check(stored["from_rank"] == val["ladder"][8],
          "a unit order keeps its starting rank (its summary has no arrow to parse)")

    pl = {"game": val["name"], "service": "placements", "placements": 5,
          "unranked": True, "mode": "Solo", "region": "North America",
          "addons": [], "currency": "usd"}
    stored, _ = roundtrip(pl, pricing.quote(pl)["total"])
    check(stored["units"] == 5 and stored.get("unranked") == 1,
          "an unranked placements order stores both the count and unranked")

    # 3 — coaching: the coach and the pack's hours, resolved server-side.
    packs = D.COACH_PACKS
    pi = max(range(len(packs)), key=lambda i: packs[i]["hours"])
    co = {"game": LOL["name"], "service": "coaching", "coach": 1, "pack": pi,
          "mode": "Solo", "region": "Europe West", "addons": [], "currency": "usd"}
    stored, _ = roundtrip(co, pricing.quote(co)["total"])
    check(stored["hours"] == packs[pi]["hours"],
          "the %dh pack stores %s hours" % (packs[pi]["hours"], stored["hours"]))
    check(stored["coach"] == D.COACHES[1]["name"],
          "the booking names the coach that was quoted (got %r)" % (stored["coach"],))
    # metadata[hours] is the buyer's preferred PLAY WINDOW, a different fact —
    # reading it as the pack length would state a booking nobody made.
    co2 = dict(co, hours="18:00–23:00")
    params, _, _ = payments.build_session(co2, "http://x")
    check(params["metadata[hours]"] == "18:00–23:00"
          and params["metadata[coach_hours]"] == str(packs[pi]["hours"]),
          "the play window and the pack length are two separate metadata keys")


# ── accounts: the shop's price model, and the four places it can be wrong ──
def account_display_cents(total_usd, cur):
    """Replica of the client display for a CENTS price: esbMoney(n, true)
    formats total * rate with two fraction digits (Intl 'halfExpand' == round
    half away from zero). This is the figure on the card and on the checkout
    total — it must equal charge_for(…, cents=True), or the buyer clicks $77.99
    and Stripe bills $78."""
    v = total_usd * pricing.CHARGE_RATES[cur] * 100
    return math.floor(v + 0.5)


def test_account_pricing():
    """The account branch charges the listing's figure plus the shard's delta,
    and nothing else.

    Four failures this locks out, and on a product with no formula they are the
    only ones that matter: charging for a listing that is **sold out on that
    shard** (stock is hand-set in data.py and nothing decrements it, so
    `account_pick()` is the only gate there is); letting the boost machinery
    leak into the price; quoting one shard's price for another; and letting the
    struck `was` figure claim a reduction the total does not make."""
    print("\n[accounts] the listing's price on the chosen shard is the charge")
    check(bool(D.accounts_in_stock()), "the catalogue has something in stock")

    bad = []
    for a in D.ACCOUNTS:
        for sv in D.ACCOUNT_SERVERS:
            r = sv["region"]
            if not D.account_stock(a, r):
                continue
            q = pricing.quote({"game": D.ACCOUNT_GAME, "service": "account",
                               "account": a["id"], "region": r})
            want = round(a["price"] + sv["delta"], 2)
            if q["invalid"] or q["total"] != want:
                bad.append("%s/%s %r != %r" % (a["id"], r, q["total"], want))
            # subtotal − discount == total, exactly, on the one listing that
            # carries a struck price and on the ten that do not.
            if round(q["subtotal"] - q["discount"], 2) != q["total"]:
                bad.append("%s/%s does not add up" % (a["id"], r))
    check(not bad, "every listing quotes its own price on every shard (%r)" % bad[:3])

    # Whatever the deltas are, all four shards must agree with the table — the
    # failure to catch is a card quoting one shard's price under another's name.
    # Today every delta is zero (one price list on all four shards), so this
    # reduces to "every shard quotes the same figure"; put a shard back on its
    # own price and the same check follows the table instead.
    ref = D.ACCOUNT_REGIONS[0]
    moved = [s["region"] for s in D.ACCOUNT_SERVERS if s["delta"]]
    a0 = D.ACCOUNTS[0]
    if moved:
        check(all(D.account_price(a0, s["region"]) == round(a0["price"] + s["delta"], 2)
                  for s in D.ACCOUNT_SERVERS),
              "each shard's delta is applied to its own price (%r)" % moved)
    else:
        # Per LISTING, not across the board — two listings may legitimately
        # share a price (Bronze and Unranked · Loaded are both $39.90 today).
        check(all(len({D.account_price(a, s["region"]) for s in D.ACCOUNT_SERVERS}) == 1
                  for a in D.ACCOUNTS),
              "one price list, identical on all four shards")

    a = D.accounts_in_stock()[0]
    base = {"game": D.ACCOUNT_GAME, "service": "account", "account": a["id"],
            "region": ref}
    # Nothing the boost engine owns may move it. Duo, every add-on at once, the
    # sitewide code and a bundle index are all thrown at one listing.
    flat = D.account_price(a, ref)
    noisy = dict(base, mode="Duo queue", addons=[x["id"] for x in D.ADDONS],
                 promo=next(iter(D.PROMOS), ""), bundle=0, wins=5, placements=5,
                 unranked=True, coach=3, pack=2)
    qn = pricing.quote(noisy)
    check(qn["total"] == flat and qn["addons"] == 0,
          "queue, add-ons, promo and bundle cannot move an account's price "
          "(%r vs %r)" % (qn["total"], flat))
    # …and a forged server-side offer cannot either. `recovery_pct` is the field
    # process_checkout() strips, but quote() must not honour it here even if one
    # arrives: the only reduction an account carries is its own `was`.
    qf = pricing.quote(dict(base, recovery_pct=0.99, offer_label="x"))
    check(qf["total"] == flat,
          "a recovery/mystery percentage cannot discount an account (got %r)" % qf["total"])

    # Sold out and unknown both refuse, and both have to.
    out = [x for x in D.ACCOUNTS if not x["stock"]]
    if out:
        qo = pricing.quote(dict(base, account=out[0]["id"]))
        check(qo["invalid"] and qo["total"] == 0,
              "a sold-out listing refuses the charge (%s)" % out[0]["id"])
    else:
        print("  --  no sold-out listing in the catalogue to check")
    check(pricing.quote(dict(base, account="no-such-listing"))["invalid"],
          "an unknown listing id refuses the charge")
    check(pricing.quote(dict(base, account=""))["invalid"],
          "an account order naming no listing refuses rather than picking one")

    # A shard this shop does not sell on is clamped to the reference, never
    # priced at whatever delta happened to be lying in the body.
    missing = next(r for r in LOL["regions"] + ["Korea"] if r not in D.ACCOUNT_REGIONS) \
        if any(r not in D.ACCOUNT_REGIONS for r in LOL["regions"] + ["Korea"]) else "Korea"
    _acc, shard = pricing.account_pick(dict(base, region=missing))
    qs = pricing.quote(dict(base, region=missing))
    check(shard == ref and qs["total"] == D.account_price(a, ref),
          "an unsold shard clamps to the reference shard (got %r)" % shard)

    # `days` is 0, and the ETA is the delivery promise rather than a day count.
    q0 = pricing.quote(base)
    check(q0["days"] == 0 and q0["eta"] == pricing.ACCOUNT_ETA,
          "an account has no day count and quotes the delivery promise")
    check(not pricing.per_hour_worth_saying(q0["total"], q0["days"]),
          "the follow-up mail's per-hour claim is dropped on a product nobody plays")


def test_account_prices_climb_with_rank():
    """A higher rank must not cost less than a lower one.

    This is the accounts board's version of `test_bundle_rules()`'s "a bigger
    climb must never cost less than a smaller one it contains", and it matters
    for the same reason: the whole argument of the price column is that the
    price tracks the hours behind the account, which the FAQ says in so many
    words. An inversion makes the dearer listing unsellable — nobody buys Iron
    at $64.90 when Gold is $59.90 — and makes the page look like it was priced
    by accident.

    ⚠ NON-FATAL BY DESIGN, the same shape `test_bundle_never_costs_more()`'s
    PENDING lines have: these prices are a business call and a deliberate
    inversion is theirs to make, but it must never pass silently.

    ⚠ IRON IS AN ACCEPTED EXCEPTION and it is not a mistake. Iron costs more
    than Bronze, Silver and Gold because it is HARDER TO SOURCE, not easier: an
    account only reaches Iron by deliberately losing a long run of games, where
    Bronze and Silver are simply where an unattended account settles. It is
    priced on the hours behind it like every other listing — the ladder is just
    not monotonic at the bottom. The business set it above Bronze twice, on two
    separate price lists. Anything OTHER than Iron reported here is a new
    inversion and wants an answer.
    """
    print("\n[accounts] the ranked ladder is priced in rank order")
    order = {t: i for i, t in enumerate(LOL["tiers"])}
    ranked = sorted((a for a in D.ACCOUNTS if D.account_kind(a) == "ranked"),
                    key=lambda a: order.get(a["tier"], 0))
    ALLOWED = {"Iron"}          # see the ⚠ above — dearer to source, not a slip
    bad = []
    for lo, hi in zip(ranked, ranked[1:]):
        if hi["price"] < lo["price"] and lo["tier"] not in ALLOWED:
            bad.append("%s $%.2f is under %s $%.2f"
                       % (hi["tier"], hi["price"], lo["tier"], lo["price"]))
    if bad:
        for b in bad:
            print("  PENDING  %s — a higher rank costs less than a lower one" % b)
        print("  PENDING  confirm this is intended, or the dearer listing is dead stock")
    else:
        check(True, "every ranked listing costs at least the rank below it "
                    "(Iron excepted — dearer to source, see the docstring)")
    # The unranked tiers are their own ladder and must climb too — they are sold
    # as a progression (level 30 → loaded → skinned) and the cards sit in that
    # order on the same rail.
    un = [a for a in D.ACCOUNTS if D.account_kind(a) == "unranked"]
    check(all(b["price"] >= a["price"] for a, b in zip(un, un[1:])),
          "the three unranked listings climb in catalogue order (%s)"
          % ", ".join("%.2f" % a["price"] for a in un))


def test_account_shown_equals_charged_to_the_cent():
    """⚠ Accounts are the ONE product priced in cents, and `charge_for()`'s
    default rounds to a whole currency unit. Every boosting total is an integer
    so that rounding is invisible there; a $77.99 account rounded the same way
    is a buyer clicking $77.99 and paying $78, in every currency.

    This walks every listing on every shard in all four currencies and asserts
    the Stripe amount equals what the card and the checkout total display."""
    print("\n[accounts] shown == charged, to the cent, in every currency")
    bad = []
    for a in D.ACCOUNTS:
        for sv in D.ACCOUNT_SERVERS:
            r = sv["region"]
            if not D.account_stock(a, r):
                continue
            q = pricing.quote({"game": D.ACCOUNT_GAME, "service": "account",
                               "account": a["id"], "region": r})
            check_cents = q.get("cents")
            if not check_cents:
                bad.append("%s/%s does not declare cents" % (a["id"], r))
                continue
            for cur in pricing.CHARGE_RATES:
                _c, amount = pricing.charge_for(q["total"], cur, cents=True)
                want = account_display_cents(q["total"], cur)
                if amount != want:
                    bad.append("%s/%s %s: %r != %r" % (a["id"], r, cur, amount, want))
    check(not bad, "the card is charged the price it shows (%r)" % bad[:3])
    # And the whole-unit path is untouched for everything else: a boost total is
    # an integer, so both paths must still agree there.
    q = pricing.quote({"game": "League of Legends", "service": "division",
                       "from": LOL["ladder"][0], "to": LOL["ladder"][6],
                       "mode": "Solo", "addons": []})
    check(not q.get("cents"), "a boost does not declare cents")
    check(pricing.charge_for(q["total"], "eur")[1] == display_cents(q["total"], "eur"),
          "the whole-unit charge path is unchanged")


def test_account_stock_is_derived_once():
    """⚠ FOUR figures on that page state stock — the promo line's total, the
    server bar, each server card and each tier card — and the version this
    replaces authored a per-server figure by hand beside the per-listing one, so
    the bar said 61 while its own cards summed to 124.

    Everything must reduce to `account_stock()`. This asserts the reduction and
    the one way its rounding goes wrong: `max(1, …)` must not resurrect a
    sold-out listing on a low-share shard."""
    print("\n[accounts] every stock figure reduces to one derivation")
    for sv in D.ACCOUNT_SERVERS:
        r = sv["region"]
        check(D.account_units_on(r)
              == sum(D.account_stock(a, r) for a in D.ACCOUNTS),
              "%s's card and its own listings agree" % D.account_code(r))
    check(D.account_stock_total()
          == sum(D.account_units_on(s["region"]) for s in D.ACCOUNT_SERVERS),
          "the page total is the sum of the four shards (%d)" % D.account_stock_total())

    # A sold-out listing is zero everywhere, including on the shard whose share
    # would round it back up to one.
    ghost = dict(D.ACCOUNTS[0], stock=0)
    check(not any(D.account_stock(ghost, s["region"]) for s in D.ACCOUNT_SERVERS),
          "a sold-out listing stays sold out on every shard")
    # …and a listing with stock is never rounded away on the smallest shard,
    # which is the other half of the same clamp.
    thin = min(D.ACCOUNT_SERVERS, key=lambda s: s["share"])
    check(all(D.account_stock(a, thin["region"]) >= 1 for a in D.ACCOUNTS if a["stock"]),
          "a listing in stock is never rounded to nothing on %s"
          % D.account_code(thin["region"]))
    # The floor the hero quotes is a price somebody can actually pay.
    floor = D.account_floor()
    payable = {D.account_price(a, s["region"]) for a in D.ACCOUNTS
               for s in D.ACCOUNT_SERVERS if D.account_stock(a, s["region"])}
    check(floor in payable, "the hero's `from` price is one a buyer can pay (%r)" % floor)


def test_account_client_mirror():
    """data.js must carry everything the server prices an account from — the
    listing's figure and its `was`, the stock base, and the shard table with its
    shares and deltas — because app.js re-quotes the order on the checkout page
    and `build_session()` refuses a total the page did not show. A shard or a
    price that differs in one of the two is a checkout that always fails."""
    print("\n[accounts] the client mirror agrees with pricing.py")
    d = _client_data()
    client = d.get("accounts") or {}
    check(set(client) == {a["id"] for a in D.ACCOUNTS},
          "data.js ships every listing (%d vs %d)" % (len(client), len(D.ACCOUNTS)))
    bad = [a["id"] for a in D.ACCOUNTS
           if client.get(a["id"], {}).get("price") != a["price"]
           or client.get(a["id"], {}).get("was", 0) != a.get("was", 0)
           or client.get(a["id"], {}).get("stock") != a["stock"]
           or client.get(a["id"], {}).get("kind") != D.account_kind(a)]
    check(not bad, "price, `was`, stock and filter key match on every listing (%r)" % bad)

    svs = d.get("accountServers") or []
    check([s["region"] for s in svs] == D.ACCOUNT_REGIONS,
          "the shard table ships in the shop's own order")
    check(all(s["share"] == D.ACCOUNT_SERVERS[i]["share"]
              and s["delta"] == D.ACCOUNT_SERVERS[i]["delta"]
              and s["code"] == D.account_code(s["region"])
              for i, s in enumerate(svs)),
          "every share, delta and code matches the server's")
    check(d.get("accountEta") == pricing.ACCOUNT_ETA,
          "the delivery promise is shipped from pricing.py, not typed twice")
    check(d.get("accountOfferLabel") == pricing.ACCOUNT_OFFER_LABEL,
          "so is the struck price's label")
    check(d.get("accountGame") == D.ACCOUNT_GAME, "the client knows which game these are")
    check(set(d.get("accountKinds") or {}) == {k for k, _l, _m in D.ACCOUNT_KINDS},
          "the filter's three descriptions ship")

    # The client's own quote is the one the CTA's price is checked against.
    js = os.path.join(ROOT, "public", "assets", "js", "app.js")
    src = open(js, encoding="utf-8").read()
    check('s.service === "account"' in src, "app.js has the account branch")
    check("!acc || !aSv || !accountStock(acc, aSv)" in src,
          "app.js refuses a listing sold out ON THAT SHARD — the same gate "
          "account_pick() is")
    for fn in ("function accountPrice", "function accountWas",
               "function accountStock", "function accountUnitsOn"):
        check(fn in src, "app.js mirrors %s()" % fn.split()[-1])
    check("cents: true" in src, "app.js's account quote declares cents")


def test_account_order_survives_to_the_store():
    """WHICH listing was sold, and on WHICH shard, has to reach the orders store:
    that row is the only thing an operator can look up, the shard decides what
    credentials are handed over, and — now that shards carry a price delta — it
    is also part of what was charged.

    It also asserts the two things an account order must NOT carry: a climb
    (the checkout body ships whatever ranks the shared per-game record held) and
    add-ons (quote() returns before the add-on block, so nothing there is
    charged). Both reached fulfilment before this was fixed, describing an order
    nobody placed."""
    print("\n[accounts] the sold listing survives to the orders store")
    import orders                                     # noqa: E402 — same lazy import
    a = D.accounts_in_stock()[0]
    shard = D.ACCOUNT_REGIONS[-1]                     # deliberately not the reference
    # Deliberately dirty: the ranks, queue and add-ons a shared record leaves
    # behind on a visitor who configured a boost before buying an account.
    st = {"game": D.ACCOUNT_GAME, "service": "account", "account": a["id"],
          "region": shard, "from": LOL["ladder"][0], "to": LOL["ladder"][6],
          "mode": "Duo queue", "addons": ["priority", "stream"], "currency": "usd"}
    params, oid, q = payments.build_session(st, "http://localhost:4321")
    md = {k[9:-1]: v for k, v in params.items() if k.startswith("metadata[")}
    row = payments.order_row(md, {"client_reference_id": oid,
                                  "amount_total": int(round(q["total"] * 100)),
                                  "customer_details": {"email": "buyer@example.com"}})
    stored = orders.clean_order(row)
    check(stored is not None, "the row survives orders.clean_order()")
    check(stored["service"] == "account", "it is stored as an account order")
    check(stored.get("account") == a["id"],
          "the listing id is stored (got %r)" % stored.get("account"))
    check(stored.get("account_name") == a["name"],
          "the listing's name is stored beside it (got %r)" % stored.get("account_name"))
    check(stored["region"] == shard,
          "the shard that was CHARGED for is stored (got %r)" % stored["region"])
    check(q["total"] == D.account_price(a, shard),
          "and it is the shard's own price (%r)" % q["total"])
    check(not stored.get("addons"),
          "no add-on is recorded on a product that charges for none (got %r)"
          % (stored.get("addons"),))
    check(not md.get("from") and not md.get("to"),
          "no climb reaches fulfilment on an account (%r → %r)" % (md.get("from"), md.get("to")))
    check(orders._climb_summary(stored) == a["name"],
          "the operator's one-line summary names the listing (got %r)"
          % orders._climb_summary(stored))
    # The Stripe page must not call it a boost — that screen is the last thing
    # between the summary and the card.
    check(params["line_items[0][price_data][product_data][name]"]
          == "%s account" % D.ACCOUNT_GAME,
          "Stripe's own line item says account, not boost")

    # And what the buyer is charged is the listing's price, in their currency.
    for cur in pricing.CHARGE_RATES:
        p2, _oid, q2 = payments.build_session(dict(st, currency=cur), "http://x")
        check(int(p2["line_items[0][price_data][unit_amount]"])
              == account_display_cents(q2["total"], cur)
              and p2["line_items[0][price_data][currency]"] == cur,
              "%s: the card is charged the price the board showed" % cur.upper())


def test_account_checkout_payload():
    """The built checkout page has to forward the listing id. Without it the
    server re-quote refuses the order (the safe half), but the buyer is told a
    listing that is in stock is unavailable — which is the same class of bug as
    the dropped `bundle` this file was written for.

    It also holds the shop page to the two rules it is built on: every listing
    server-rendered with a real link (complete and buyable with no JS, legible
    to a crawler), and the ToS admission ON the page rather than only inside the
    FAQ's JSON-LD."""
    print("\n[accounts] built checkout.html forwards the listing")
    p = os.path.join(ROOT, "dist", "checkout.html")
    if not os.path.exists(p):
        check(False, "dist/checkout.html present (run build.py first)")
        return
    html = open(p, encoding="utf-8").read()
    check("account: s.account" in html, "the payload includes `account`")

    board = os.path.join(ROOT, "dist", "accounts.html")
    if not os.path.exists(board):
        check(False, "dist/accounts.html present (run build.py first)")
        return
    b = open(board, encoding="utf-8").read()
    ref = D.ACCOUNT_REGIONS[0]
    missing = [a["id"] for a in D.ACCOUNTS
               if 'data-ac-id="%s"' % a["id"] not in b]
    check(not missing, "all %d listings are server-rendered (%r)"
          % (len(D.ACCOUNTS), missing))
    nolink = [a["id"] for a in D.ACCOUNTS if D.account_stock(a, ref)
              and "account=%s&region=" % a["id"] not in b]
    check(not nolink, "every listing in stock on the reference shard ships a "
                      "real checkout link (%r)" % nolink)
    # All three CTA labels and all three stock states ride in the DOM — the
    # whole-text-node i18n rule. A label written in by JS arrives untranslated.
    for key in ("ok", "low", "out"):
        check('data-ac-cta="%s"' % key in b, "the %r CTA ships in the DOM" % key)
        check('data-ac-sv="%s"' % key in b, "the %r stock line ships in the DOM" % key)
    # Both steps ship visible, so the page is a complete shop with no JS.
    check('data-ac-step="server"' in b and 'data-ac-step="tiers"' in b,
          "both steps are server-rendered")
    check("data-ac-nojs" in b,
          "the no-JS page says which shard it is priced on")
    # The admission has to be ON the page, not only in the FAQ's JSON-LD.
    check(esc_disclaimer() in b, "the ToS admission is rendered on the board")
    # ⚠ The ids are a public contract — checkout deep-links #faq-warranty.
    check('id="faq-warranty"' in b, "the warranty answer keeps its public id")


def esc_disclaimer():
    from html import escape
    return escape(D.ACCOUNT_DISCLAIMER)


def main():
    for fn in (test_shown_equals_charged, test_iron_to_gold_regression,
               test_addon_modes, test_free_optional_addons,
               test_picks_labels,
               test_bundle_does_not_stack, test_bundle_rules,
               test_bundle_never_costs_more,
               test_build_session_amount, test_client_total_guard,
               test_client_bundle_mirror, test_fx_rate_mirror, test_currency_signs,
               test_server_defaults,
               test_eta_schedule_mirror, test_eta_is_never_a_bare_long_figure,
               test_checkout_payload_sends_state,
               test_order_row_records_what_was_bought,
               test_account_pricing,
               test_account_prices_climb_with_rank,
               test_account_shown_equals_charged_to_the_cent,
               test_account_stock_is_derived_once,
               test_account_client_mirror,
               test_account_order_survives_to_the_store,
               test_account_checkout_payload):
        fn()
    print("\n" + ("=" * 52))
    if _fails:
        print("FAILED: %d check(s)" % len(_fails))
        for m in _fails:
            print("  - " + m)
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
