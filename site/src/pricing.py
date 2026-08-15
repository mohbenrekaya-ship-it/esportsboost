# -*- coding: utf-8 -*-
"""Authoritative, server-side pricing.

This is the Python source of truth for what an order costs. It mirrors the
`quote()` in ../public/assets/js/app.js exactly — the browser re-quotes for the
UI, but the number the customer is *charged* is only ever computed here, from a
trusted copy of the config, never taken from the client. **Change one, change
the other** (see CLAUDE.md).

`build.py` also imports `quote()` from this module for its static "from $NN"
cards, so the Python formula lives in exactly one place.
"""
import math

import data as D

BY_NAME = {g["name"]: g for g in D.GAMES}
ADDON = {a["id"]: a for a in D.ADDONS}

# Net wins / placements are a 1–5 grid (five per order is the product cap), so a
# tampered `wins`/`placements` is clamped into this range before it can reach the
# charge amount.
UNIT_MIN, UNIT_MAX = 1, 5

# Duo queue multiplier. Named so the order card can label the option with the
# real percentage instead of a hand-typed one that drifts. Mirrored literally in
# app.js — change one, change the other.
DUO_MULT = 1.55

# ── the delivery schedule ───────────────────────────────────────────────────
# `days` is the whole ETA: a fixed start-up allowance plus a per-rung rate, and
# on the games with no per-tier price table a per-climb term so a high-rank rung
# costs more time than a low-rank one. The start-up half day is the claim and the
# first session, before any rung moves — which also makes the effective per-rung
# time fall as an order gets longer, the way a booster who has an order open all
# week actually works. The rates were cut from 0.35/rung and 0.08/climb: a full
# ladder quoted 12 days, slower than the roster delivers, and the ETA is the
# figure the buyer weighs the price against.
DAYS_SETUP = 0.5
DAYS_PER_RUNG = 0.18
DAYS_PER_CLIMB = 0.045
DAYS_PER_WIN = 0.3
DAYS_PER_PLACEMENT = 0.26

# Past ETA_EXACT days a single figure is false precision — an order that could
# land anywhere across a week cannot honestly be quoted "7 days" — so the
# estimate is shown as a band opening ON the computed value: "7–9 days". The band
# is proportional (never under ETA_SPAN_MIN), so a longer ladder than any shipped
# today widens it instead of quoting a fortnight to the day.
ETA_EXACT = 3
ETA_SPAN_MIN, ETA_SPAN_PCT = 2, 0.3

# Display/charge FX rates, MIRRORED EXACTLY from i18n.js `window.ESB_RATES`. The
# quote is computed in USD, but the customer sees — and is charged in — whichever
# currency they picked, converted at these fixed rates. The Stripe session is
# created in that same currency at the same rate, so the amount on the Stripe page
# equals the amount on the button. Change one, change the other (see CLAUDE.md).
CHARGE_RATES = {"usd": 1.0, "eur": 0.92}


def charge_for(total_usd, currency):
    """(currency_code, integer minor units) for the Stripe line item.

    The button shows the total as `esbMoney(total)` — a WHOLE currency unit (no
    decimals), i.e. `round(total_usd * rate)`. We charge that exact figure so
    Stripe never quotes a different number than the customer clicked. Unknown
    currencies fall back to USD (the base the quote is already in)."""
    cur = str(currency or "usd").strip().lower()
    if cur not in CHARGE_RATES:
        cur = "usd"
    whole_units = _jsround(total_usd * CHARGE_RATES[cur])
    return cur, whole_units * 100


def _jsround(x):
    """Match JavaScript's Math.round (round-half-up) so the price the browser
    shows is exactly the price Stripe charges — Python's round() is banker's."""
    return int(math.floor(x + 0.5))


def eta_text(days):
    """The delivery estimate as the buyer reads it — one figure while that is an
    honest promise, a band once it isn't. Mirrored in app.js `etaText()` — change
    one, change the other."""
    if days <= 1:
        return "about 1 day"
    if days <= ETA_EXACT:
        return "%d days" % days
    span = max(ETA_SPAN_MIN, _jsround(days * ETA_SPAN_PCT))
    return "%d–%d days" % (days, days + span)


def _addon_total(base, addons, mode="Solo"):
    """Dollar cost of the selected add-ons, each floored at $1.

    An add-on is a percentage of the boost, so on a tiny order (a single net win
    at Iron is ~$3) 10–15% rounds below $0.50 and vanishes into the whole-dollar
    total — the option then reads "+$0", as if it were free. Each selected add-on
    instead costs at least $1: its real percentage once that is a dollar or more,
    a flat $1 below that. Summed per add-on (not as one combined percentage) so
    the receipt's telescoping rows and each option's own price stay ≥ $1 too.

    An add-on that belongs to the other queue is ignored rather than charged:
    the picker only ever offers one of the mode-conditional pair, so an id for
    the other one reached us through a stale localStorage state or a tampered
    payload, and billing for an option the page never showed is the one thing
    the client_total guard exists to prevent.

    Mirrored in app.js `addonTotal()` — change one, change the other."""
    total = 0
    for a in (addons or []):
        if a in ADDON and ADDON[a]["pct"] and D.addon_applies(ADDON[a], mode):
            total += max(1, _jsround(base * ADDON[a]["pct"]))
    return total


_BUNDLE_PCT = {}


def full_bundle_price(g, b):
    """What the bundle's climb costs at list price: the FULL from-tier climb
    (tier's bottom division → target), Solo, no add-ons. This is the struck
    figure on the card and the base the discount is taken off."""
    return quote({"game": g["name"], "service": "division", "from": b["defFrom"],
                  "to": b["target"], "mode": "Solo", "addons": []})["subtotal"]


def bundle_pct(g, b):
    """A bundle's hand-set price expressed as the discount fraction the engine
    applies: `1 − price / full`.

    BUNDLES stores the PRICE (see data.py), because that is the number a human
    sets and the number that has to sit under the cheapest normal order in the
    tier. Everything downstream — duo, add-ons, the EUR charge, the receipt's
    telescoping rows, checkout's `client_total` guard — is built on a percentage
    off the boost, so converting here means none of it changes and a Solo order
    still lands on exactly the stated price: `discount = jsround(full − price)`
    is exact on whole-dollar figures, so `total = full − discount = price`.

    Shipped to the client in `data.js` as `disc`, so app.js needs no arithmetic
    of its own and the two sides cannot drift. 0 for a price at or above list —
    a bundle that isn't a reduction is not applied at all.
    """
    key = (g["name"], b["defFrom"], b["target"], b["price"])
    if key not in _BUNDLE_PCT:
        full = full_bundle_price(g, b)
        _BUNDLE_PCT[key] = max(0.0, 1 - b["price"] / full) if full > 0 else 0.0
    return _BUNDLE_PCT[key]


def bundle_discount(g, from_rank, to_rank, idx):
    """The discount fraction for a matching opt-in bundle, else 0."""
    b = D.active_bundle(g, from_rank, to_rank, idx)
    return bundle_pct(g, b) if b else 0.0


def resolve_promo(code=None):
    """Pick the one discount that applies to an order.

    The auto promo applies with nothing typed; a typed code replaces it only
    when it is worth more. Discounts never stack, and an unknown or weaker code
    can never make the buyer's price worse. Returns (code, promo) or (None, None).
    """
    best_code, best = D.auto_promo()
    if code:
        typed = D.PROMOS.get(str(code).strip().upper())
        if typed and (best is None or typed["pct"] > best["pct"]):
            best_code, best = str(code).strip().upper(), typed
    return best_code, best


def quote(state):
    """`state` is the client order dict: game, service, from, to, mode, wins,
    placements, addons. Returns price fields plus `total` (whole USD) and
    `total_cents` for Stripe. `invalid` marks an impossible configuration."""
    game = state.get("game")
    g = BY_NAME.get(game)
    if not g:
        return _invalid("Unknown game")

    per = D.PER_DIVISION
    factor = g["factor"]
    mode = state.get("mode", "Piloted")
    duo = DUO_MULT if mode == "Duo queue" else 1.0
    service = state.get("service", "division")

    if service == "coaching":
        # Booking product: price is rate × hours × (1 − pack discount) and
        # nothing else — no rank, no duo, no add-ons, no sitewide promo. The
        # pack discount is expressed as `discount` so the card's struck price and
        # save line read it the same way a promo would.
        coaches, packs = D.COACHES, D.COACH_PACKS
        ci = _idx(state.get("coach", 0), len(coaches))
        pi = _idx(state.get("pack", 1), len(packs))
        coach, pack = coaches[ci], packs[pi]
        hours = pack["hours"]
        listed = coach["rate"] * hours
        total = _jsround(listed * (1 - pack["disc"]))
        hrs = "%d hour" % hours if hours == 1 else "%d hours" % hours
        return dict(
            invalid=False, total=total, total_cents=total * 100,
            subtotal=listed, discount=listed - total,
            promo_code="", promo_label="", promo_pct=0, promo_ends="",
            base=listed, addons=0, days=hours,
            summary="%s coaching with %s" % (hrs, coach["name"]),
            eta="First session",
        )

    if service == "wins":
        frm = state.get("from")
        if frm not in g["ladder"]:
            return _invalid("Unknown rank")
        w = _clamp(state.get("wins", 1))
        wp = g.get("win_prices")
        if wp:
            # Per-tier win table: flat price per win within the tier the player
            # is at. No factor/climb bonus — the table already ramps by tier,
            # exactly like the division `prices` branch. Mirrored in app.js.
            base = w * _tier_price(g, frm, wp) * duo
        else:
            climb = _climb(g, frm)
            base = w * per * 0.55 * factor * (1 + climb * 0.045) * duo
        days = max(1, _jsround(w * DAYS_PER_WIN))
        summary = "%d %s · %s · %s" % (w, "net win" if w == 1 else "net wins", frm, mode)
    elif service == "placements":
        frm = state.get("from")
        unranked = bool(state.get("unranked"))
        if not unranked and frm not in g["ladder"]:
            return _invalid("Unknown rank")
        p = _clamp(state.get("placements", 1))
        pp = g.get("placement_prices")
        if pp:
            # Per-tier placement table, same shape as win_prices. Unranked has no
            # rank to read, so it prices at the ladder floor (first tier).
            floor = g["tiers"][0]
            unit = pp.get(floor, 0) if unranked else _tier_price(g, frm, pp)
            base = p * unit * duo
        else:
            # Unranked has no starting rank to read a climb off — price at the floor.
            climb = 1 if unranked else _climb(g, frm)
            base = p * per * 0.7 * factor * (1 + climb * 0.045) * duo
        days = max(1, _jsround(p * DAYS_PER_PLACEMENT))
        where = "Unranked" if unranked else frm
        summary = "%d placement %s · %s · %s" % (p, "game" if p == 1 else "games", where, mode)
    else:
        ladder = g["ladder"]
        frm, to = state.get("from"), state.get("to")
        if frm not in ladder or to not in ladder:
            return _invalid("Unknown rank")
        # A matching bundle is a FLAT price across its whole from-tier: every
        # division quotes as the FULL two-tier climb (the from-tier's bottom
        # division → target), so Emerald I → Diamond IV costs the same as the
        # real Emerald IV → Diamond IV work — the "two tiers up in one order"
        # the card advertises, discounted, never a sliver of it. The buyer's
        # real ranks still show in the summary. Mirrored in app.js.
        bundle = D.active_bundle(g, frm, to, state.get("bundle"))
        price_from = bundle["defFrom"] if bundle else frm
        i, j = ladder.index(price_from), ladder.index(to)
        steps = j - i
        if steps <= 0:
            return _invalid("Target must sit above your current rank")
        prices = g.get("prices")
        if prices:
            # per-division tier table: each rung climbed costs the price of the
            # tier it lands in. No factor/climb bonus — the table already makes
            # higher tiers pricier.
            base = sum(_rung_price(g, ladder[k]) for k in range(i + 1, j + 1)) * duo
            days = max(1, _jsround(DAYS_SETUP + steps * DAYS_PER_RUNG))
        else:
            climb = _climb(g, frm)
            base = steps * D.PER_STEP * factor * (1 + climb * 0.045) * duo
            days = max(1, _jsround(DAYS_SETUP + steps * DAYS_PER_RUNG
                                   + climb * DAYS_PER_CLIMB))
        summary = "%s → %s · %s" % (frm, to, mode)

    # A bundle (opt-in, division only) REPLACES the sitewide sale when the current
    # climb still matches it — the handoff's rule that only one discount is ever
    # in play. Otherwise the usual promo resolution applies. Resolved BEFORE the
    # add-ons, because on a bundle it is what they are a percentage of.
    bpct = bundle_discount(g, state.get("from"), state.get("to"),
                           state.get("bundle")) if service == "division" else 0.0

    boost = _jsround(base)
    # An add-on is a percentage of the boost the buyer is paying for. On a bundle
    # that is the bundle's flat PRICE, not the list climb it is discounted from —
    # a bundle prices every division of its from-tier as the tier's full climb,
    # so charging 15% of that list figure billed the buyer for priority on a
    # $98 order they are paying $67 for. On the short climbs that is $3 more
    # add-on than the plain order charges, which is more than the few dollars a
    # bundle saves: ticking Priority made "Apply bundle" cost MORE than not
    # applying it, the exact trap the hand-set prices exist to remove. The
    # sitewide sale deliberately does NOT do this (see below); a bundle must,
    # because its boost is inflated to the tier floor and the sale's is not.
    extra = _addon_total(base * (1 - bpct) if bpct else base,
                         state.get("addons"), mode)
    subtotal = boost + extra

    # Discount comes off the boost only, so the strikethrough shown to the buyer
    # is a real reduction from what the climb would otherwise cost — never a
    # grossed-up reference price. Add-ons are à-la-carte and NOT discounted by the
    # sitewide sale: on a small order it would otherwise grow by exactly the
    # add-on's $1 floor and cancel it, so a ticked option read "+$0" even after
    # the floor. Charging them on top of the discounted boost keeps every add-on
    # worth its ≥$1 in the final total. The receipt still balances either way:
    # boost + add-ons − discount = total.
    if bpct:
        pcode, promo = "BUNDLE", {"pct": bpct, "label": "Bundle", "ends": ""}
    else:
        pcode, promo = resolve_promo(state.get("promo"))
    discount = _jsround(boost * promo["pct"]) if promo else 0
    total = subtotal - discount

    return dict(
        invalid=False, total=total, total_cents=total * 100,
        subtotal=subtotal, discount=discount,
        promo_code=pcode or "", promo_label=(promo or {}).get("label", ""),
        promo_pct=(promo or {}).get("pct", 0), promo_ends=(promo or {}).get("ends", ""),
        base=_jsround(base), addons=extra, days=days,
        summary=summary,
        eta=eta_text(days),
    )


def _tier_price(g, rank, table):
    """Look a rank's tier up in a per-tier price table (`prices`, `win_prices`).
    Returns the price of the tier the rank belongs to, or 0."""
    for tier, ranks in g["divmap"].items():
        if rank in ranks:
            return table.get(tier, 0)
    return 0


def _rung_price(g, rank):
    """Price of a single division rung, from the game's per-tier table: the
    price of the tier the destination rank belongs to."""
    return _tier_price(g, rank, g.get("prices") or {})


def _climb(g, frm):
    """Higher starting ranks cost more — the same multiplier the division
    boost uses, so a win/placement at Diamond prices above one at Bronze."""
    return max(1, g["ladder"].index(frm) - 1)


def _idx(n, length):
    """Clamp a client-supplied list index into range — a tampered coach/pack
    selection can never read past the list."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(length - 1, n))


def _clamp(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = UNIT_MIN
    return max(UNIT_MIN, min(UNIT_MAX, n))


def _invalid(msg):
    return dict(invalid=True, total=0, total_cents=0, subtotal=0, discount=0,
                promo_code="", promo_label="", promo_pct=0, promo_ends="",
                base=0, addons=0, days=0, summary=msg, eta="—")
