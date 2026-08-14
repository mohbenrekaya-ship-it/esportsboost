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


def _jsround(x):
    """Match JavaScript's Math.round (round-half-up) so the price the browser
    shows is exactly the price Stripe charges — Python's round() is banker's."""
    return int(math.floor(x + 0.5))


def _addon_total(base, addons):
    """Dollar cost of the selected add-ons, each floored at $1.

    An add-on is a percentage of the boost, so on a tiny order (a single net win
    at Iron is ~$3) 10–15% rounds below $0.50 and vanishes into the whole-dollar
    total — the option then reads "+$0", as if it were free. Each selected add-on
    instead costs at least $1: its real percentage once that is a dollar or more,
    a flat $1 below that. Summed per add-on (not as one combined percentage) so
    the receipt's telescoping rows and each option's own price stay ≥ $1 too.
    Mirrored in app.js `addonTotal()` — change one, change the other."""
    total = 0
    for a in (addons or []):
        if a in ADDON and ADDON[a]["pct"]:
            total += max(1, _jsround(base * ADDON[a]["pct"]))
    return total


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
        days = max(1, _jsround(w * 0.45))
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
        days = max(1, _jsround(p * 0.4))
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
            days = max(1, _jsround(steps * 0.35))
        else:
            climb = _climb(g, frm)
            base = steps * D.PER_STEP * factor * (1 + climb * 0.045) * duo
            days = max(1, _jsround(steps * 0.35 + climb * 0.08))
        summary = "%s → %s · %s" % (frm, to, mode)

    boost = _jsround(base)
    extra = _addon_total(base, state.get("addons"))
    subtotal = boost + extra

    # Discount comes off the boost only, so the strikethrough shown to the buyer
    # is a real reduction from what the climb would otherwise cost — never a
    # grossed-up reference price. Add-ons are à-la-carte and NOT discounted: on a
    # small order the sale would otherwise grow by exactly the add-on's $1 floor
    # and cancel it, so a ticked option read "+$0" even after the floor. Charging
    # them on top of the discounted boost keeps every add-on worth its ≥$1 in the
    # final total. The receipt still balances: boost + add-ons − discount = total.
    #
    # A bundle (opt-in, division only) REPLACES the sitewide sale when the current
    # climb still matches it — the handoff's rule that only one discount is ever
    # in play. Otherwise the usual promo resolution applies.
    bpct = D.bundle_discount(g, state.get("from"), state.get("to"),
                             state.get("bundle")) if service == "division" else 0.0
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
        eta="about 1 day" if days == 1 else "%d days" % days,
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
