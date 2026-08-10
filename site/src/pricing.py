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

# stepper bounds — a tampered `wins`/`placements` is clamped into this range
# before it can reach the charge amount.
UNIT_MIN, UNIT_MAX = 1, 40


def _jsround(x):
    """Match JavaScript's Math.round (round-half-up) so the price the browser
    shows is exactly the price Stripe charges — Python's round() is banker's."""
    return int(math.floor(x + 0.5))


def _addon_pct(addons):
    return sum(ADDON[a]["pct"] for a in (addons or []) if a in ADDON)


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
    duo = 1.55 if mode == "Duo queue" else 1.0
    service = state.get("service", "division")

    if service == "wins":
        frm = state.get("from")
        if frm not in g["ladder"]:
            return _invalid("Unknown rank")
        w = _clamp(state.get("wins", 1))
        climb = _climb(g, frm)
        base = w * per * 0.55 * factor * (1 + climb * 0.045) * duo
        days = max(1, _jsround(w * 0.45))
        summary = "%d %s · %s · %s" % (w, "net win" if w == 1 else "net wins", frm, mode)
    elif service == "placements":
        frm = state.get("from")
        if frm not in g["ladder"]:
            return _invalid("Unknown rank")
        p = _clamp(state.get("placements", 1))
        climb = _climb(g, frm)
        base = p * per * 0.7 * factor * (1 + climb * 0.045) * duo
        days = max(1, _jsround(p * 0.4))
        summary = "%d placement %s · %s · %s" % (p, "game" if p == 1 else "games", frm, mode)
    else:
        ladder = g["ladder"]
        frm, to = state.get("from"), state.get("to")
        if frm not in ladder or to not in ladder:
            return _invalid("Unknown rank")
        i, j = ladder.index(frm), ladder.index(to)
        steps = j - i
        if steps <= 0:
            return _invalid("Target must sit above your current rank")
        climb = _climb(g, frm)
        base = steps * D.PER_STEP * factor * (1 + climb * 0.045) * duo
        days = max(1, _jsround(steps * 0.35 + climb * 0.08))
        summary = "%s → %s · %s" % (frm, to, mode)

    extra = base * _addon_pct(state.get("addons"))
    total = _jsround(base + extra)
    return dict(
        invalid=False, total=total, total_cents=total * 100,
        base=_jsround(base), addons=_jsround(extra), days=days,
        summary=summary,
        eta="about 1 day" if days == 1 else "%d days" % days,
    )


def _climb(g, frm):
    """Higher starting ranks cost more — the same multiplier the division
    boost uses, so a win/placement at Diamond prices above one at Bronze."""
    return max(1, g["ladder"].index(frm) - 1)


def _clamp(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = UNIT_MIN
    return max(UNIT_MIN, min(UNIT_MAX, n))


def _invalid(msg):
    return dict(invalid=True, total=0, total_cents=0, base=0, addons=0,
                days=0, summary=msg, eta="—")
