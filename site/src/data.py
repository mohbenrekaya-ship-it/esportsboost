# -*- coding: utf-8 -*-
"""Single source of truth for the site.

Everything the pages render comes from here; the build also serialises the
subset the browser needs into assets/js/data.js, so client and server can
never drift apart.

⚠ CONTENT WARNING (carried over from the design handoff, do not ship as-is):
the game list beyond League of Legends, every statistic, the booster handles
and the reviews are PLACEHOLDERS. Wire STATS to Trustpilot / the orders table
/ the Discord widget and BOOSTERS to the real roster before launch.

That now covers a whole page per booster: BOOSTERS carries the ratings,
on-time rates, dispute counts, climb breakdowns and testimonials the profile
pages render, VETTING carries the funnel figures the boosters hero argues
from, and build.py's booster_history() derives a completed-orders table from
the booster's own ladder. All of it is invented. A profile reads like a
personnel record, which is exactly why none of it can go live unverified.
"""

SITE = "http://localhost:4321"
BRAND = "eSports Boost"
YEAR = 2026

PER_DIVISION = 26  # per-win / per-placement base; belongs in server-side pricing config
PER_STEP = 7       # per single division rung on the ladder (see subdivide() below)


class Ladder(list):
    """A flat rank ladder that also remembers the tier/division structure it
    was built from, so the UI can offer a two-step (tier → division) picker
    while pricing still runs on the flat per-rung list."""
    tiers = ()
    labels = ()
    apex = ()


def subdivide(tiers, labels, apex=()):
    """Expand base rank tiers into their real in-game divisions.

    `labels` run low→high within a tier (e.g. Iron IV → Iron I); any tier in
    `apex` is a single LP/points-based rank and stays whole. Pricing is
    per-rung, so more rungs = finer granularity — see PER_STEP.
    """
    out = Ladder()
    out.tiers, out.labels, out.apex = list(tiers), list(labels), tuple(apex)
    for t in tiers:
        if t in apex:
            out.append(t)
        else:
            out.extend("%s %s" % (t, lab) for lab in labels)
    return out


# Who actually enforces the terms of service for each ladder. The game page's
# safety band names them ("Riot flags accounts on patterns…", "against Riot's
# terms of service"), because a named publisher is what makes the argument
# concrete — the generic SAFETY copy still covers every other page.
PUBLISHERS = {
    "league-of-legends": "Riot", "valorant": "Riot", "teamfight-tactics": "Riot",
    "counter-strike-2": "Valve", "dota-2": "Valve",
    "marvel-rivals": "NetEase", "overwatch-2": "Blizzard",
    "apex-legends": "EA", "rocket-league": "Psyonix",
}


def publisher(g):
    return PUBLISHERS.get(g["slug"], "The publisher")


def _attach_structure(g):
    """Derive `tiers` (the ladder's main ranks) and `divmap` (tier → its
    ordered sub-ranks) for every game, including flat ladders like CS2 where
    each entry is its own tier with no divisions."""
    ld = g["ladder"]
    tiers = list(getattr(ld, "tiers", None) or ld)
    labels = list(getattr(ld, "labels", ()))
    apex = set(getattr(ld, "apex", ()))
    g["tiers"] = tiers
    g["divmap"] = {
        t: ([t] if (t in apex or not labels) else ["%s %s" % (t, lab) for lab in labels])
        for t in tiers
    }


GAMES = [
    dict(
        name="League of Legends", slug="league-of-legends", short="LoL", tab="League", factor=1.0, hue=262,
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald",
                          "Diamond", "Master"],
                         ["IV", "III", "II", "I"],
                         apex=("Master",)),
        prices={"Iron": 6, "Bronze": 8, "Silver": 9, "Gold": 12, "Platinum": 19,
                "Emerald": 30, "Diamond": 48, "Master": 60},
        # Per-tier price of one net win (flat within a tier), keyed on the rank
        # the player is currently at. Present → the wins service prices off this
        # table instead of the shared per/climb formula, the same way `prices`
        # overrides the division formula. Mirrored in app.js as winPrices.
        win_prices={"Iron": 3, "Bronze": 3, "Silver": 4, "Gold": 5, "Platinum": 8,
                    "Emerald": 13, "Diamond": 20, "Master": 40},
        # Per-tier price of one placement game, same shape as win_prices. Unranked
        # has no rank to read, so it prices at the ladder floor (Iron → 3).
        placement_prices={"Iron": 3, "Bronze": 3, "Silver": 4, "Gold": 5, "Platinum": 8,
                          "Emerald": 13, "Diamond": 20, "Master": 40},
        services="Elo boost · placements · net wins · duo · coaching",
        regions=["North America", "Europe West", "EU Nordic & East", "Oceania"],
        blurb="Solo/duo and flex, across NA and EU. Your booster plays your account inside your "
              "normal hours with a regional VPN, or queues beside you in duo and never "
              "touches the login at all.",
        meta="LoL elo boost from Iron to Master. Live price before you sign in, "
             "verified boosters, pro-rated refunds. Solo or duo, every region.",
        note="Every division from Iron IV to Diamond I is on the ladder; Master is "
             "LP-based and priced as a single step above Diamond I.",
    ),
    dict(
        name="Valorant", slug="valorant", short="VAL", factor=1.15, hue=352,
        # Valorant ranks up on RR (Rank Rating), not LP, and its ladder queue is
        # "Competitive". The dashboard mock and the game page read these so the
        # Valorant order never says "LP" or "Ranked solo". LoL and the rest
        # default to LP / Ranked solo.
        rank_unit="RR", queue_name="Competitive",
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Diamond",
                          "Ascendant", "Immortal"],
                         ["1", "2", "3"], apex=("Immortal",)),
        prices={"Iron": 4, "Bronze": 4, "Silver": 5, "Gold": 7, "Platinum": 9,
                "Diamond": 18, "Ascendant": 35, "Immortal": 100},
        # Per-tier price of one net win (flat within a tier), same shape as LoL's.
        win_prices={"Iron": 3, "Bronze": 3, "Silver": 4, "Gold": 5, "Platinum": 6,
                    "Diamond": 10, "Ascendant": 15, "Immortal": 22},
        # Placements share the win table; unranked prices at the floor (Iron → 3).
        placement_prices={"Iron": 3, "Bronze": 3, "Silver": 4, "Gold": 5, "Platinum": 6,
                          "Diamond": 10, "Ascendant": 15, "Immortal": 22},
        services="Rank boost · placements · unrated wins · duo · coaching",
        regions=["North America", "Europe", "Asia", "Latin America"],
        blurb="Radiant-level boosters with your own crosshair and sensitivity loaded in. "
              "Agent pool on request, and duo runs with voice if you want the coaching "
              "on the way up.",
        meta="Valorant rank boost, Iron to Immortal. Transparent live pricing, duo or "
             "solo, agent pool on request.",
        note="Act rank and episode resets shift the price; the quote is locked at "
             "checkout either way.",
    ),
    dict(
        name="Counter-Strike 2", slug="counter-strike-2", short="CS2", tab="CS2", factor=1.45, hue=32,
        ladder=["5k", "10k", "13k", "15k", "17k", "19k", "21k", "25k", "30k"],
        services="Premier rating · Faceit levels · Wingman · wins",
        regions=["North America", "Europe", "South America", "Asia", "Oceania"],
        blurb="Premier CS Rating and Faceit levels, run by FPL-adjacent players. Anti-cheat "
              "safe patterns, no smurf stacking, no rating farm scripts.",
        meta="CS2 Premier rating and Faceit level boosting. Live price, verified players, "
             "refunds pro-rated to the rating actually gained.",
        note="Ratings are shown in thousands of CS Rating points.",
    ),
    dict(
        name="Teamfight Tactics", slug="teamfight-tactics", short="TFT", tab="TFT", factor=0.8, hue=198,
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald",
                          "Diamond", "Master", "Challenger"],
                         ["IV", "III", "II", "I"], apex=("Master", "Challenger")),
        services="Rank boost · placements · double-up",
        regions=["North America", "Europe West", "EU Nordic & East", "Oceania", "Brazil", "Korea"],
        blurb="Set-current comp knowledge, not last patch's. Double-up runs are played with "
              "you, so the climb doubles as a lesson in tempo and econ.",
        meta="TFT rank boosting and double-up. Current-set comps, live pricing, no bots.",
        note="Ranked and Double Up share the ladder; Hyper Roll is quoted on request.",
    ),
    dict(
        name="Marvel Rivals", slug="marvel-rivals", short="RIV", tab="Rivals", factor=0.95, hue=8,
        ladder=subdivide(["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Grandmaster",
                          "Celestial", "Eternity", "One Above All"],
                         ["III", "II", "I"], apex=("Eternity", "One Above All")),
        services="Rank boost · net wins · duo · coaching",
        regions=["North America", "Europe", "Asia", "South America"],
        blurb="Role-locked or flexible, hero pool respected. Celestial and above are hand-"
              "matched to a booster who actually mains the roles you need covered.",
        meta="Marvel Rivals rank boost to Celestial, Eternity and One Above All. Live price, "
             "duo available.",
        note="One Above All is leaderboard-gated; those runs are quoted per order.",
    ),
    dict(
        name="Dota 2", slug="dota-2", short="DOTA", factor=1.25, hue=18,
        ladder=subdivide(["Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient",
                          "Divine", "Immortal"],
                         ["1", "2", "3", "4", "5"], apex=("Immortal",)),
        services="MMR boost · calibration · net wins · duo",
        regions=["North America East", "North America West", "Europe West", "Europe East", "Southeast Asia", "China", "South America"],
        blurb="MMR by bracket, calibration runs, and behaviour-score-safe play. Immortal "
              "boosters queue in their own bracket, never above it.",
        meta="Dota 2 MMR boosting and calibration, Herald to Immortal. Transparent per-"
             "bracket pricing.",
        note="MMR ranges are approximate per medal; exact MMR targets are set at checkout.",
    ),
    dict(
        name="Apex Legends", slug="apex-legends", short="APEX", factor=1.1, hue=6,
        ladder=subdivide(["Rookie", "Bronze", "Silver", "Gold", "Platinum", "Diamond",
                          "Master", "Predator"],
                         ["IV", "III", "II", "I"], apex=("Master", "Predator")),
        services="Rank boost · badges · kills · duo",
        regions=["North America", "Europe", "Asia", "South America", "Oceania"],
        blurb="RP climbs, 4K and 20-bomb badges, kill thresholds. Legend pool and playstyle "
              "matched so the account keeps looking like yours.",
        meta="Apex Legends rank boost and badge services, Rookie to Predator. Live pricing, "
             "duo queue available.",
        note="Predator is a moving cutoff; those orders are re-quoted daily before you pay.",
    ),
    dict(
        name="Overwatch 2", slug="overwatch-2", short="OW2", factor=0.9, hue=212,
        ladder=subdivide(["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master",
                          "Grandmaster", "Champion"],
                         ["5", "4", "3", "2", "1"], apex=("Champion",)),
        services="Rank boost · placements · net wins · duo",
        regions=["North America", "Europe", "Asia", "South America"],
        blurb="Per-role SR, open queue or role queue. Your hero pool is respected — the "
              "profile shouldn't read like a different player when it's done.",
        meta="Overwatch 2 competitive rank boost, per role. Bronze to Champion, duo or "
             "solo, live price.",
        note="Each role is ranked separately; pick the role you want moved at checkout.",
    ),
    dict(
        name="Rocket League", slug="rocket-league", short="RL", factor=0.7, hue=222,
        ladder=subdivide(["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Champion",
                          "Grand Champ", "Supersonic"],
                         ["I", "II", "III", "IV"], apex=("Supersonic",)),
        services="Rank boost · tournament wins · duo · coaching",
        regions=["North America East", "North America West", "Europe", "South America", "Oceania", "Asia"],
        blurb="1v1, 2v2 and 3v3 playlists, tournament wins, and duo sessions where the "
              "booster calls rotations live on voice.",
        meta="Rocket League rank boosting and tournament wins, Bronze to Supersonic Legend.",
        note="Each playlist has its own rank; the quote covers one playlist per order.",
    ),
]

# Short region codes — full names read best in the game-page region SELECT, but
# the homepage Best Sellers band draws its regions as CHIPS, which truncate at
# phone width ("North A…"). buildRegions() in app.js falls back to these on the
# chips only (CSS picks short below 760px); anything not listed keeps its full
# name. Shipped as `regionShort` in client_data.
REGION_SHORT = {
    "North America": "NA",
    "North America East": "NA E",
    "North America West": "NA W",
    "Europe": "EU",
    "Europe West": "EUW",
    "EU Nordic & East": "EUNE",
    "Europe East": "EUE",
    "Oceania": "OCE",
    "Southeast Asia": "SEA",
    "China": "CN",
    "Latin America": "LATAM",
    "South America": "SA",
    "Brazil": "BR",
    "Korea": "KR",
}

# Site-wide display order (games index, footer, dropdowns, client data). Change
# this one list to re-rank the games everywhere. The homepage mosaic has its own
# hand-tuned layout — see TILE_ORDER.
_ORDER = ["league-of-legends", "valorant", "marvel-rivals", "teamfight-tactics",
          "overwatch-2", "rocket-league", "dota-2", "apex-legends", "counter-strike-2"]
GAMES.sort(key=lambda g: _ORDER.index(g["slug"]))

for _g in GAMES:
    _attach_structure(_g)

# ── tier colours ──────────────────────────────────────────────────────────
# The rank marks in the order card are tinted by the tier they name, so the
# ladder reads as distance travelled and not just as two dropdowns. Named
# entries cover the metal tiers every game shares plus the apex tiers of the
# games that have their own; anything unnamed falls back to a positional ramp
# (cool grey at the floor → ember at the top), so a new game never needs a
# colour added here before it looks right.
#
# These are our own approximations on a dark ground, deliberately *not* lifted
# from the publishers' rank emblems — see the asset note in the handoff.
TIER_COLORS = {
    "Iron": "#8e8f94", "Bronze": "#b1764c", "Silver": "#a3adb8",
    "Gold": "#e0ac3e", "Platinum": "#4fb0aa", "Emerald": "#3fa06c",
    "Diamond": "#5f93de", "Master": "#a56fd0", "Grandmaster": "#e0574f",
    "Challenger": "#f0c674", "Ascendant": "#2fa88a", "Immortal": "#d24a5e",
    "Champion": "#7d6fe0", "Grand Champ": "#b45ad6", "Supersonic": "#ff7a3d",
    "Radiant": "#ffe07a", "Predator": "#e0574f", "Rookie": "#8e8f94",
    # Rivals' apex tier sits one rung above Grandmaster and the positional ramp
    # lands both on near-identical reds — two marks a rung apart have to be
    # tellable apart at 24px, which is the whole point of colouring them.
    "Celestial": "#c8577a",
}

# Positional ramp for tiers with no named colour: L*-even stops from cool grey
# to ember, so any ladder length lands on a legible mark on the card ground.
_TIER_RAMP = ["#8e8f94", "#8f9ba8", "#6f9dc4", "#5f93de", "#7d84d8",
              "#a56fd0", "#d0699c", "#e0765a", "#f09a45", "#ffb046"]


def tier_color(game, tier):
    """Mark colour for one tier of one game. Named first, then the ramp."""
    if tier in TIER_COLORS:
        return TIER_COLORS[tier]
    tiers = game["tiers"]
    i = tiers.index(tier) if tier in tiers else 0
    span = max(1, len(tiers) - 1)
    return _TIER_RAMP[min(len(_TIER_RAMP) - 1,
                          round(i / span * (len(_TIER_RAMP) - 1)))]


def tier_colors(game):
    return {t: tier_color(game, t) for t in game["tiers"]}


def bundle_climbs(g):
    """Resolve this game's BUNDLES tier-pairs into concrete climbs.

    Each becomes `floorFrom` (the tier's division I — the cheapest start, so the
    advertised "from" price is a floor the order can only beat) → `target` (the
    upper tier's division IV). `defFrom` (division IV of the lower tier) is the
    default endpoint a click drops you on when your current division can't be
    kept. Skips any pair whose tiers a given game doesn't have, or that doesn't
    actually climb.
    """
    out = []
    dm = g.get("divmap") or {}
    ld = g["ladder"]
    for ft, tt, disc in BUNDLES.get(g["name"], []):
        if ft not in dm or tt not in dm:
            continue
        floor_from, target, def_from = dm[ft][-1], dm[tt][0], dm[ft][0]
        if ld.index(target) <= ld.index(floor_from):
            continue
        out.append(dict(ft=ft, tt=tt, floorFrom=floor_from, target=target,
                        defFrom=def_from, disc=disc))
    return out


def active_bundle(g, from_rank, to_rank, idx):
    """The opt-in bundle climb (index `idx`), but only while the current climb
    still matches it: `from_rank` in the bundle's from-tier and `to_rank` equal
    to its target. Changing division keeps the match; changing tier or target
    drops it. Returns the climb dict, or None — the handoff's rule, enforced on
    both the server and the client."""
    if idx is None:
        return None
    climbs = bundle_climbs(g)
    try:
        b = climbs[int(idx)]
    except (TypeError, ValueError, IndexError):
        return None
    dm = g.get("divmap") or {}
    from_tier = next((t for t, ranks in dm.items() if from_rank in ranks), None)
    return b if (from_tier == b["ft"] and to_rank == b["target"]) else None


def bundle_discount(g, from_rank, to_rank, idx):
    """The discount for a matching opt-in bundle, else 0. See active_bundle()."""
    b = active_bundle(g, from_rank, to_rank, idx)
    return b["disc"] if b else 0.0


# Notes are deliberately one line each: the order card draws them under the
# add-on name in an 11px row, and the handoff's layout budgets a single line
# there. A second line pushes the CTA below the fold — see CLAUDE.md.
# `label_sm` / `note_sm` are the phone's wording, where the order card is 358px
# wide and the long forms wrap to a second line — the handoff's mobile screen
# shortens exactly these two. Both variants ship in the DOM and CSS picks one,
# because i18n.js matches whole text nodes.
ADDONS = [
    dict(id="priority", label="Priority order", pct=0.15,
         note="First in the claim queue, claimed in about 6 minutes.",
         note_sm="First in the claim queue, about 6 minutes."),
    dict(id="champ", label="Champions, agents & roles", pct=0.10,
         label_sm="Champions & roles",
         note="Your booster plays the picks you choose."),
    dict(id="stream", label="Live game stream", pct=0.12,
         note="Watch every game from your dashboard."),
    dict(id="offline", label="Offline appearance", pct=0.0,
         note="Always on. Friends see you offline for the whole order."),
]

# ── Coaching — the fourth configurator product ─────────────────────────────
# ⚠ PLACEHOLDER, same standing as BOOSTERS/DEMO_ORDER: the four coaches, their
# rates, ratings and open slots are invented. Coaching is a booking flow, not a
# rank climb — it does not read the pricing ladder at all. Its price is
# `rate * pack.hours * (1 - pack.disc)` and nothing else (no duo, no add-ons, no
# sitewide promo), computed the same way in pricing.py and app.js.
#
# The tab renders only on games whose `services` string mentions "coaching"
# (LoL, Valorant, Marvel Rivals today), so a game we do not coach never offers
# it. Calendar and payment integration are unbuilt — see CLAUDE.md / the handoff.
COACHES = [
    dict(handle="renata", name="Renata", rating="5.0", role="Support main",
         rank="Challenger", rate=32),
    dict(handle="kpossan", name="Kossan", rating="4.9", role="Jungle · macro",
         rank="Grandmaster", rate=28),
    dict(handle="mireille", name="Mireille", rating="4.9", role="Mid · roams",
         rank="Master", rate=24),
    dict(handle="tavi", name="Tavi", rating="4.8", role="Top · matchups",
         rank="Master", rate=22),
]

# Hour packs: the only discount coaching ever carries. `disc` is a real, chosen
# rate reduction for buying more hours up front, not a placeholder percentage.
COACH_PACKS = [
    dict(hours=1, disc=0.0),
    dict(hours=3, disc=0.10),
    dict(hours=5, disc=0.18),
]

COACH_FOCUS = ["Laning", "Macro & rotations", "Champion pool", "VOD review"]

# First-session slots offered in the picker. Placeholder wording; a real booking
# calendar replaces this list.
COACH_SLOTS = ["Tonight, 20:00", "Tomorrow, 18:00", "Saturday, 15:00", "Sunday, 12:00"]

# ── Bundles — one-click popular climbs ─────────────────────────────────────
# Each entry is a (from-tier, to-tier) pair naming a common two-tier jump.
# Clicking a card configures that exact climb (from-tier IV → to-tier IV) on the
# Division boost tab; the price shown is the LIVE quote for that climb through
# the shared engine, so it can never advertise a number the checkout won't
# honour, and the sitewide sale is the only discount in play.
#
# Honest deviation from the handoff, which prices bundles at an invented 22–35%
# "bundle discount" on top of the sale. We keep one discount (the sale), so the
# strip is a shortcut to a popular climb rather than a fabricated deeper cut —
# the site's standing rule that a shown discount must be one the order really
# gets. Introduce a real bundle-only discount by adding a promo code and reading
# it here first. Games without an entry show no strip.
#
# Each entry is (from-tier, to-tier, discount). The discount is a REAL bundle-only
# cut that the server charges — it replaces the sitewide sale on a matching climb
# (never stacks), so the "−N%" pill and the struck price are a reduction the order
# actually gets, not a fabricated one. ⚠ These percentages are a business call:
# confirm they are the real bundle offer before launch.
#
# All nine games carry a set, so no game page is missing the strip. They share one
# shape — three two-tier jumps through the low ladder, then single-tier jumps where
# a tier is already a long climb — and one 22 → 35% ramp, so the offer reads the
# same everywhere until the real per-game economics replace it.
#
# One rule holds across all nine and should survive re-tuning: **the top rank of a
# ladder is never a bundle target.** Predator, Challenger, Immortal, One Above All,
# Supersonic, Champion, Master (LoL) and 30k are leaderboard- or cutoff-gated, and
# every game's own `note` says those orders are quoted per order — which is exactly
# what a fixed advertised bundle price cannot be. Lower apex ranks with a fixed
# threshold (Apex's Master) are fine.
BUNDLES = {
    "League of Legends": [
        ("Iron", "Silver", 0.22), ("Bronze", "Gold", 0.25), ("Silver", "Platinum", 0.28),
        ("Gold", "Platinum", 0.30), ("Platinum", "Emerald", 0.32), ("Emerald", "Diamond", 0.35),
    ],
    "Valorant": [
        ("Iron", "Silver", 0.22), ("Bronze", "Gold", 0.25), ("Silver", "Platinum", 0.28),
        ("Gold", "Platinum", 0.30), ("Platinum", "Diamond", 0.32), ("Diamond", "Ascendant", 0.35),
    ],
    "Teamfight Tactics": [
        ("Iron", "Silver", 0.22), ("Bronze", "Gold", 0.25), ("Silver", "Platinum", 0.28),
        ("Gold", "Platinum", 0.30), ("Platinum", "Emerald", 0.32), ("Emerald", "Diamond", 0.35),
    ],
    "Marvel Rivals": [
        ("Bronze", "Gold", 0.22), ("Silver", "Platinum", 0.25), ("Gold", "Diamond", 0.28),
        ("Platinum", "Diamond", 0.30), ("Diamond", "Grandmaster", 0.32),
        ("Grandmaster", "Celestial", 0.35),
    ],
    "Overwatch 2": [
        ("Bronze", "Gold", 0.22), ("Silver", "Platinum", 0.25), ("Gold", "Diamond", 0.28),
        ("Platinum", "Diamond", 0.30), ("Diamond", "Master", 0.32),
        ("Master", "Grandmaster", 0.35),
    ],
    "Rocket League": [
        ("Bronze", "Gold", 0.22), ("Silver", "Platinum", 0.25), ("Gold", "Diamond", 0.28),
        ("Platinum", "Diamond", 0.30), ("Diamond", "Champion", 0.32),
        ("Champion", "Grand Champ", 0.35),
    ],
    "Dota 2": [
        ("Herald", "Crusader", 0.22), ("Guardian", "Archon", 0.25), ("Crusader", "Legend", 0.28),
        ("Archon", "Legend", 0.30), ("Legend", "Ancient", 0.32), ("Ancient", "Divine", 0.35),
    ],
    "Apex Legends": [
        ("Rookie", "Silver", 0.22), ("Bronze", "Gold", 0.25), ("Silver", "Platinum", 0.28),
        ("Gold", "Platinum", 0.30), ("Platinum", "Diamond", 0.32), ("Diamond", "Master", 0.35),
    ],
    # Flat rating ladder — every rung is its own tier, so a bundle names two exact
    # CS Rating checkpoints rather than "any division of". bundle_strip() reads the
    # divmap and drops the "from any division" line for exactly this case.
    "Counter-Strike 2": [
        ("5k", "13k", 0.22), ("10k", "15k", 0.25), ("13k", "17k", 0.28),
        ("15k", "19k", 0.30), ("17k", "21k", 0.32), ("19k", "25k", 0.35),
    ],
}

# ── placeholder statistics ────────────────────────────────────────────────
# `trustpilot` and `reviews` are not written here — they are computed from
# REVIEW_DIST just below, which is the one place the rating lives.
STATS = dict(
    boosts="92,400",
    discord="3,000", median_claim="18 min",
    online=34, free_now=25, reply="3m 40s",
    # Footer line under the delivery feed. Counts the whole 24h window, not the
    # four rows above it — the feed is capped, the figure is not.
    closed_24h="41",
)

# ── the rating, and the only place it is written ──────────────────────────
# ⚠ Placeholder like everything else in this block: an invented count of
# reviews per star, not the review table.
#
# The site asserts this rating in five places — the reviews page's H1, its
# summary card, its distribution filter, the Trustpilot badge, and the checkout
# summary — and the reviews page draws three of them within one screen of each
# other. So none of them is typed: these counts are the only figures, the
# percentages are computed from them, and the average and the total below are
# too. Replace this dict with the real corpus and all five move together.
#
# Note what is NOT here: the reviews the page actually prints. REVIEWS below is
# a 58-entry sample of these 3,140 — the distribution describes the corpus, the
# feed shows a slice of it, and the count line on the page says which.
REVIEW_DIST = {5: 2612, 4: 372, 3: 94, 2: 34, 1: 28}

_RATED = sum(REVIEW_DIST.values())
STATS["reviews"] = "{:,}".format(_RATED) if _RATED else ""
STATS["trustpilot"] = ("%.1f / 5" % (sum(s * n for s, n in REVIEW_DIST.items()) / _RATED)
                       if _RATED else "")

# ── the roster ────────────────────────────────────────────────────────────
# `slug` names the game in GAMES: the roster chip renders that game's `short`,
# so a booster can never advertise a ladder the catalogue doesn't sell, and the
# chip can't drift from the game page it sits beside. `queue` is the source of
# truth for availability — "free" (the literal string) is what the free/busy
# status pill reads, everything else is an order count.
#
# `tier` is the peak's rank tier, written out rather than parsed off the front
# of `peak`. The roster table and the profile header tint their mark with
# tier_color(game, tier), so this has to be a rank that colour table resolves —
# a rung of that game's ladder, or a named apex above it (a peak is a career
# high, not something you can order, so Challenger is legal on a LoL ladder
# that stops selling at Master). The handoff parses the first word of the peak
# string and says outright that production should carry the field; this is it.
#
# `wr_n` is the same figure as `wr`, as an int, because the roster's win-rate
# bar is positional (normalised across WR_FLOOR..85) and a page that argues it
# doesn't self-report cannot render its one comparable figure off a string.
#
# ⚠ Every handle, figure and rank below is a PLACEHOLDER (see top of file) —
# including everything the profile pages render: `since`, `role`, `rating`,
# `ontime`, `disputes`, `reviews_n`, `climbs` and `review`.
WR_FLOOR = 62   # the win-rate floor the boosters page states out loud. Asserted
                # against every wr_n at import: a roster row under the floor
                # would contradict the headline three inches above it.

BOOSTERS = [
    # ── League of Legends ──────────────────────────────────────────────────
    dict(handle="vantaa", slug="league-of-legends", region="EUW", hue=20,
         peak="Challenger 1042 LP", tier="Challenger", wr_n=78, queue="1 order",
         orders=214, role="Mid lane", since="Mar 2023",
         rating="4.9", ontime="98%", disputes="0",
         review=("Played my champs, kept to evenings like I asked, and finished two days "
                 "early. Second order with him.", "MK", 5.0, 3)),
    dict(handle="korrin", slug="league-of-legends", region="EUW", hue=34,
         peak="Challenger 1180 LP", tier="Challenger", wr_n=79, queue="free",
         orders=241, role="Jungle", since="Feb 2022",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="adze", slug="league-of-legends", region="NA", hue=46,
         peak="Challenger 990 LP", tier="Challenger", wr_n=77, queue="free",
         orders=176, role="ADC", since="Apr 2023",
         rating="4.9", ontime="99%", disputes="0"),
    dict(handle="ilva", slug="league-of-legends", region="EUW", hue=320,
         peak="Challenger 1055 LP", tier="Challenger", wr_n=76, queue="free",
         orders=205, role="Support", since="Jun 2022",
         rating="5.0", ontime="99%", disputes="0"),
    dict(handle="odain", slug="league-of-legends", region="NA", hue=12,
         peak="Challenger 1010 LP", tier="Challenger", wr_n=75, queue="free",
         orders=189, role="Top", since="Dec 2022",
         rating="4.8", ontime="96%", disputes="1"),
    dict(handle="lysander", slug="league-of-legends", region="EUW", hue=262,
         peak="Grandmaster 720 LP", tier="Grandmaster", wr_n=75, queue="1 order",
         orders=198, role="Mid lane", since="Jul 2022",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="veyra", slug="league-of-legends", region="EUW", hue=300,
         peak="Grandmaster 705 LP", tier="Grandmaster", wr_n=74, queue="free",
         orders=167, role="Mid lane", since="May 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="tenzo", slug="league-of-legends", region="EUW", hue=58,
         peak="Grandmaster 640 LP", tier="Grandmaster", wr_n=73, queue="free",
         orders=152, role="Top", since="Mar 2023",
         rating="4.7", ontime="95%", disputes="1"),
    dict(handle="quill", slug="league-of-legends", region="EUW", hue=140,
         peak="Grandmaster 660 LP", tier="Grandmaster", wr_n=73, queue="free",
         orders=158, role="Jungle", since="Nov 2022",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="sova_lt", slug="league-of-legends", region="EUNE", hue=228,
         peak="Master 480 LP", tier="Master", wr_n=71, queue="free",
         orders=134, role="Support", since="Sep 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="calder", slug="league-of-legends", region="NA", hue=94,
         peak="Master 520 LP", tier="Master", wr_n=70, queue="1 order",
         orders=118, role="Jungle", since="Jan 2024",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="arven", slug="league-of-legends", region="NA", hue=246,
         peak="Master 500 LP", tier="Master", wr_n=70, queue="free",
         orders=112, role="Mid lane", since="Mar 2024",
         rating="4.8", ontime="98%", disputes="0"),
    dict(handle="eiro", slug="league-of-legends", region="EUW", hue=184,
         peak="Master 515 LP", tier="Master", wr_n=69, queue="free",
         orders=103, role="Jungle", since="Jun 2024",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="kestrel_9", slug="league-of-legends", region="EUNE", hue=274,
         peak="Master 445 LP", tier="Master", wr_n=68, queue="free",
         orders=87, role="ADC", since="Apr 2024",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="tarn", slug="league-of-legends", region="EUW", hue=352,
         peak="Master 470 LP", tier="Master", wr_n=66, queue="2 orders",
         orders=92, role="Top", since="Jan 2025",
         rating="4.7", ontime="94%", disputes="0"),
    dict(handle="kasai", slug="league-of-legends", region="OCE", hue=170,
         peak="Challenger 905 LP", tier="Challenger", wr_n=75, queue="free",
         orders=138, role="Jungle", since="Aug 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="mako_oce", slug="league-of-legends", region="OCE", hue=88,
         peak="Grandmaster 690 LP", tier="Grandmaster", wr_n=72, queue="free",
         orders=121, role="Mid lane", since="Oct 2023",
         rating="4.8", ontime="97%", disputes="0"),

    # ── Valorant ───────────────────────────────────────────────────────────
    dict(handle="kx_reid", slug="valorant", region="NA", hue=352,
         peak="Radiant #211", tier="Immortal", wr_n=74, queue="free",
         orders=168, role="Duelist", since="Aug 2022",
         rating="4.9", ontime="97%", disputes="0",
         review=("Asked for Jett and Raze only and that's exactly what the match history "
                 "shows. Four days, no drama.", "TV", 5.0, 6)),
    dict(handle="nyx_ro", slug="valorant", region="EU", hue=6,
         peak="Radiant #144", tier="Radiant", wr_n=76, queue="free",
         orders=187, role="Initiator", since="Jan 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="wren", slug="valorant", region="NA", hue=160,
         peak="Radiant 700 RR", tier="Radiant", wr_n=75, queue="free",
         orders=171, role="Sentinel", since="Dec 2022",
         rating="4.8", ontime="96%", disputes="1"),
    dict(handle="sculp", slug="valorant", region="NA", hue=42,
         peak="Radiant 720 RR", tier="Radiant", wr_n=74, queue="1 order",
         orders=154, role="Sentinel", since="Aug 2022",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="sennet", slug="valorant", region="EU", hue=214,
         peak="Radiant #221", tier="Radiant", wr_n=74, queue="free",
         orders=158, role="Controller", since="Sep 2022",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="tovi", slug="valorant", region="NA", hue=78,
         peak="Radiant 655 RR", tier="Radiant", wr_n=73, queue="2 orders",
         orders=141, role="Duelist", since="Jun 2022",
         rating="4.7", ontime="95%", disputes="1"),
    dict(handle="petrichor", slug="valorant", region="EU", hue=280,
         peak="Radiant 610 RR", tier="Immortal", wr_n=72, queue="free",
         orders=88, role="Controller", since="Nov 2023",
         rating="4.9", ontime="98%", disputes="0",
         review=("Duo runs with voice — I actually learned the smokes instead of just "
                 "getting the rank.", "SN", 5.0, 4)),
    dict(handle="estra", slug="valorant", region="EU", hue=330,
         peak="Radiant 635 RR", tier="Radiant", wr_n=71, queue="free",
         orders=124, role="Sentinel", since="Aug 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="drev", slug="valorant", region="EU", hue=256,
         peak="Immortal 3 · 480 RR", tier="Immortal", wr_n=71, queue="free",
         orders=128, role="Controller", since="Oct 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="rilke", slug="valorant", region="NA", hue=16,
         peak="Immortal 3 · 505 RR", tier="Immortal", wr_n=70, queue="1 order",
         orders=119, role="Controller", since="Nov 2023",
         rating="4.7", ontime="94%", disputes="1"),
    dict(handle="laska", slug="valorant", region="EU", hue=100,
         peak="Immortal 3 · 410 RR", tier="Immortal", wr_n=69, queue="free",
         orders=106, role="Sentinel", since="Feb 2024",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="kova", slug="valorant", region="EU", hue=204,
         peak="Immortal 3 · 460 RR", tier="Immortal", wr_n=68, queue="free",
         orders=97, role="Duelist", since="Mar 2024",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="hollo", slug="valorant", region="NA", hue=236,
         peak="Immortal 3 · 440 RR", tier="Immortal", wr_n=66, queue="free",
         orders=79, role="Controller", since="Jun 2024",
         rating="4.7", ontime="94%", disputes="0"),
    dict(handle="renji_v", slug="valorant", region="Asia", hue=190,
         peak="Immortal 3 · 470 RR", tier="Immortal", wr_n=71, queue="free",
         orders=104, role="Duelist", since="Sep 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="solano_v", slug="valorant", region="LATAM", hue=22,
         peak="Immortal 2 · 380 RR", tier="Immortal", wr_n=69, queue="free",
         orders=86, role="Initiator", since="Dec 2023",
         rating="4.7", ontime="96%", disputes="0"),

    # ── the other seven ladders ────────────────────────────────────────────
    # One booster covers one game, and `slug` is what the roster chip reads —
    # so a booster can never advertise a ladder the catalogue doesn't sell.
    dict(handle="sable", slug="counter-strike-2", region="EU", hue=32,
         peak="FPL, 27k Premier", peak_full="FPL · 27k Premier · EU", tier="30k",
         wr_n=71, queue="2 orders", orders=141, role="AWP", since="Jan 2022",
         rating="4.8", ontime="96%", disputes="1",
         review=("Rating went up in a straight line, no forty-hour days that get you "
                 "flagged. Worth the wait for a slot.", "JD", 4.8, 5)),
    dict(handle="dvor", slug="counter-strike-2", region="NA", hue=48,
         peak="FPL-C, 25k Premier", peak_full="FPL-C · 25k Premier · NA", tier="25k",
         wr_n=69, queue="free", orders=108, role="IGL", since="Mar 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="krios", slug="counter-strike-2", region="EU", hue=14,
         peak="FPL, 26k Premier", peak_full="FPL · 26k Premier · EU", tier="30k",
         wr_n=72, queue="free", orders=167, role="Rifler", since="Aug 2021",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="talo", slug="counter-strike-2", region="NA", hue=204,
         peak="FPL-C, 24k Premier", peak_full="FPL-C · 24k Premier · NA", tier="25k",
         wr_n=68, queue="1 order", orders=124, role="Entry", since="Feb 2023",
         rating="4.7", ontime="95%", disputes="1"),
    # Rivals, not LoL: orvo delivers the Marvel Rivals order in LIVE_FEED below,
    # and a roster that calls the same person a League booster contradicts the
    # feed two columns away.
    dict(handle="orvo", slug="marvel-rivals", region="NA", hue=210,
         peak="Grandmaster 640 LP", tier="Grandmaster", wr_n=69, queue="free",
         orders=97, role="Vanguard", since="Feb 2025",
         rating="4.9", ontime="99%", disputes="0",
         review=("Kept to my hero pool and still closed it in three days. The stream "
                 "add-on is worth it with him.", "RP", 5.0, 2)),
    dict(handle="kaisen", slug="marvel-rivals", region="EU", hue=344,
         peak="Celestial 410 LP", tier="Celestial", wr_n=71, queue="free",
         orders=118, role="Strategist", since="Jan 2025",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="vellum", slug="marvel-rivals", region="EU", hue=280,
         peak="Eternity 300 LP", tier="Eternity", wr_n=72, queue="1 order",
         orders=142, role="Duelist", since="Dec 2024",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="sunder", slug="marvel-rivals", region="NA", hue=40,
         peak="Celestial 520 LP", tier="Celestial", wr_n=70, queue="free",
         orders=109, role="Duelist", since="Jan 2025",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="nine", slug="dota-2", region="SEA", hue=16,
         peak="Immortal 8.4k", tier="Immortal", wr_n=73, queue="1 order",
         orders=203, role="Mid / carry", since="Jun 2021",
         rating="4.8", ontime="95%", disputes="1",
         review=("Behaviour score untouched and the MMR stuck. He plays the bracket, "
                 "not the smurf.", "AL", 5.0, 8)),
    dict(handle="obrun", slug="dota-2", region="EU West", hue=136,
         peak="Divine 5", tier="Divine", wr_n=66, queue="1 order",
         orders=91, role="Offlane", since="Sep 2023",
         rating="4.6", ontime="93%", disputes="0"),
    dict(handle="veya", slug="dota-2", region="EU East", hue=286,
         peak="Immortal 7.1k", tier="Immortal", wr_n=71, queue="free",
         orders=156, role="Carry", since="Mar 2022",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="rurik", slug="dota-2", region="NA", hue=100,
         peak="Immortal 6.6k", tier="Immortal", wr_n=69, queue="2 orders",
         orders=118, role="Support", since="Nov 2022",
         rating="4.7", ontime="95%", disputes="0"),
    # TFT has no head-to-head win: its equivalent metric is the top-4 rate, so
    # the row prints that and `wr_n` is the figure inside its own string. Both
    # sides of the column have to say the same number — the bar is normalised on
    # one span, and a label that disagrees with the bar is the "win rate is
    # comparable" fix undone.
    dict(handle="mera", slug="teamfight-tactics", region="EUW", hue=196,
         peak="Challenger 980 LP", tier="Challenger", wr="Top-4 68%", wr_n=68,
         queue="free", orders=76, role="Flex / tempo", since="Apr 2024",
         rating="4.9", ontime="99%", disputes="0",
         review=("Current-set comps, not last patch's. Double-up runs were the best part.",
                 "EO", 5.0, 1)),
    dict(handle="vior", slug="teamfight-tactics", region="KR", hue=160,
         peak="Challenger 1010 LP", tier="Challenger", wr="Top-4 69%", wr_n=69,
         queue="free", orders=134, role="Flex / tempo", since="Oct 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="octa", slug="teamfight-tactics", region="NA", hue=20,
         peak="Challenger 940 LP", tier="Challenger", wr="Top-4 66%", wr_n=66,
         queue="1 order", orders=88, role="Fast 8", since="Jul 2024",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="pyra_tft", slug="teamfight-tactics", region="EUW", hue=318,
         peak="Master 410 LP", tier="Master", wr="Top-4 64%", wr_n=64,
         queue="free", orders=61, role="Reroll", since="Feb 2025",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="cobalt_ix", slug="overwatch-2", region="NA", hue=212,
         peak="Champion, 4520 SR", peak_full="Champion 4520 SR · NA", tier="Champion",
         wr_n=70, queue="1 order", orders=132, role="Main tank", since="Sep 2022",
         rating="4.7", ontime="94%", disputes="1",
         review=("Tank rank only, exactly as ordered, and the profile still looks like "
                 "mine afterwards.", "BR", 4.5, 7)),
    dict(handle="volk", slug="overwatch-2", region="NA", hue=24,
         peak="Champion, 4460 SR", peak_full="Champion 4460 SR · NA", tier="Champion",
         wr_n=72, queue="1 order", orders=147, role="Flex support", since="Jul 2022",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="rhyme", slug="overwatch-2", region="EU", hue=190,
         peak="Grandmaster, 4200 SR", peak_full="Grandmaster 4200 SR · EU", tier="Grandmaster",
         wr_n=68, queue="free", orders=101, role="Hitscan", since="Apr 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="ilse", slug="overwatch-2", region="EU", hue=300,
         peak="Grandmaster, 4050 SR", peak_full="Grandmaster 4050 SR · EU", tier="Grandmaster",
         wr_n=66, queue="2 orders", orders=79, role="Off-tank", since="Jan 2024",
         rating="4.6", ontime="94%", disputes="1"),
    dict(handle="halden", slug="rocket-league", region="EU", hue=224,
         peak="SSL 1885 MMR", tier="Supersonic", wr_n=76, queue="free",
         orders=119, role="2v2 / 3v3", since="May 2021",
         rating="4.9", ontime="98%", disputes="0",
         review=("Called rotations on voice the whole way up. I can hold the rank he "
                 "left me at, which is the point.", "FK", 5.0, 3)),
    dict(handle="dain", slug="rocket-league", region="NA", hue=140,
         peak="SSL 1820 MMR", tier="Supersonic", wr_n=74, queue="free",
         orders=133, role="1v1 / 2v2", since="Jun 2022",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="mox_rl", slug="rocket-league", region="NA", hue=30,
         peak="SSL 1795 MMR", tier="Supersonic", wr_n=71, queue="free",
         orders=112, role="3v3", since="Nov 2021",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="quor", slug="rocket-league", region="EU", hue=260,
         peak="GC3 1610 MMR", tier="Grand Champ", wr_n=68, queue="1 order",
         orders=96, role="2v2 / 3v3", since="Mar 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="tsuro", slug="apex-legends", region="EU", hue=6,
         peak="Predator #740", tier="Predator", wr_n=68, queue="2 orders",
         orders=64, role="Fragger", since="Oct 2024",
         rating="4.8", ontime="96%", disputes="0",
         review=("Badge order, delivered in two days with the clips to prove it.",
                 "MT", 5.0, 9)),
    dict(handle="rev_apex", slug="apex-legends", region="NA", hue=8,
         peak="Predator #610", tier="Predator", wr_n=70, queue="free",
         orders=97, role="IGL", since="Feb 2024",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="kryo", slug="apex-legends", region="EU", hue=210,
         peak="Predator #920", tier="Predator", wr_n=67, queue="1 order",
         orders=72, role="Fragger", since="Sep 2024",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="wisp_ax", slug="apex-legends", region="NA", hue=48,
         peak="Master, 41k RP", tier="Master", wr_n=66, queue="free",
         orders=58, role="Support / recon", since="Jan 2025",
         rating="4.7", ontime="94%", disputes="0"),

    # ── added roster — LoL & Valorant, EUW/EU + NA ─────────────────────────
    # PLACEHOLDER like the rest of this block (see the warning at the top of the
    # file): invented handles, ranks and figures. wr_n stays at or above WR_FLOOR.
    dict(handle="riven_ka", slug="league-of-legends", region="EUW", hue=284,
         peak="Challenger 1015 LP", tier="Challenger", wr_n=79, queue="free",
         orders=188, role="Mid lane", since="Feb 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="faelan", slug="league-of-legends", region="NA", hue=118,
         peak="Grandmaster 700 LP", tier="Grandmaster", wr_n=74, queue="free",
         orders=142, role="Jungle", since="May 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="otto_lux", slug="league-of-legends", region="EUW", hue=42,
         peak="Master 505 LP", tier="Master", wr_n=70, queue="1 order",
         orders=104, role="Support", since="Sep 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="vex_adc", slug="league-of-legends", region="NA", hue=350,
         peak="Challenger 985 LP", tier="Challenger", wr_n=77, queue="free",
         orders=173, role="ADC", since="Mar 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="sylric", slug="league-of-legends", region="EUW", hue=200,
         peak="Grandmaster 660 LP", tier="Grandmaster", wr_n=73, queue="free",
         orders=131, role="Top", since="Jul 2023",
         rating="4.8", ontime="96%", disputes="1"),
    dict(handle="mireille", slug="league-of-legends", region="EUW", hue=312,
         peak="Master 470 LP", tier="Master", wr_n=69, queue="free",
         orders=98, role="Mid lane", since="Nov 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="kaelo", slug="league-of-legends", region="NA", hue=88,
         peak="Master 445 LP", tier="Master", wr_n=66, queue="free",
         orders=71, role="Jungle", since="Feb 2024",
         rating="4.6", ontime="94%", disputes="0"),
    dict(handle="north_lol", slug="league-of-legends", region="NA", hue=222,
         peak="Grandmaster 640 LP", tier="Grandmaster", wr_n=72, queue="2 orders",
         orders=126, role="Top", since="Aug 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="avel", slug="league-of-legends", region="EUW", hue=160,
         peak="Challenger 1030 LP", tier="Challenger", wr_n=78, queue="free",
         orders=181, role="Jungle", since="Apr 2023",
         rating="4.9", ontime="99%", disputes="0"),
    dict(handle="ryse_ttv", slug="league-of-legends", region="EUW", hue=18,
         peak="Master 520 LP", tier="Master", wr_n=68, queue="1 order",
         orders=89, role="ADC", since="Jan 2024",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="dove", slug="league-of-legends", region="NA", hue=268,
         peak="Master 480 LP", tier="Master", wr_n=71, queue="free",
         orders=112, role="Support", since="Oct 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="kilian", slug="league-of-legends", region="EUW", hue=74,
         peak="Grandmaster 685 LP", tier="Grandmaster", wr_n=75, queue="free",
         orders=149, role="Mid lane", since="Jun 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="settmain", slug="league-of-legends", region="NA", hue=8,
         peak="Master 460 LP", tier="Master", wr_n=67, queue="free",
         orders=83, role="Top", since="Mar 2024",
         rating="4.6", ontime="94%", disputes="1"),
    dict(handle="yuna_lol", slug="league-of-legends", region="EUW", hue=330,
         peak="Challenger 995 LP", tier="Challenger", wr_n=76, queue="free",
         orders=167, role="Mid lane", since="May 2023",
         rating="4.9", ontime="98%", disputes="0"),

    dict(handle="reyna_x", slug="valorant", region="NA", hue=6,
         peak="Radiant #188", tier="Radiant", wr_n=76, queue="free",
         orders=176, role="Duelist", since="Feb 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="cirq", slug="valorant", region="EU", hue=210,
         peak="Immortal 3 · 470 RR", tier="Immortal", wr_n=70, queue="free",
         orders=101, role="Sentinel", since="Sep 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="veto", slug="valorant", region="NA", hue=150,
         peak="Radiant #241", tier="Radiant", wr_n=74, queue="free",
         orders=158, role="Initiator", since="Apr 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="mila_v", slug="valorant", region="EU", hue=286,
         peak="Radiant 610 RR", tier="Radiant", wr_n=73, queue="free",
         orders=139, role="Controller", since="Jun 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="gale_v", slug="valorant", region="NA", hue=34,
         peak="Immortal 3 · 505 RR", tier="Immortal", wr_n=68, queue="1 order",
         orders=94, role="Duelist", since="Dec 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="sero", slug="valorant", region="EU", hue=192,
         peak="Radiant #276", tier="Radiant", wr_n=75, queue="free",
         orders=161, role="Initiator", since="Mar 2023",
         rating="4.9", ontime="98%", disputes="0"),
    dict(handle="nova_k", slug="valorant", region="NA", hue=98,
         peak="Immortal 3 · 430 RR", tier="Immortal", wr_n=67, queue="free",
         orders=79, role="Sentinel", since="Feb 2024",
         rating="4.6", ontime="94%", disputes="0"),
    dict(handle="brimm", slug="valorant", region="EU", hue=246,
         peak="Immortal 3 · 455 RR", tier="Immortal", wr_n=69, queue="free",
         orders=97, role="Controller", since="Nov 2023",
         rating="4.7", ontime="95%", disputes="0"),
    dict(handle="zeke_v", slug="valorant", region="NA", hue=356,
         peak="Radiant 655 RR", tier="Radiant", wr_n=72, queue="2 orders",
         orders=133, role="Duelist", since="Jul 2023",
         rating="4.7", ontime="95%", disputes="1"),
    dict(handle="lyric", slug="valorant", region="EU", hue=126,
         peak="Radiant #302", tier="Radiant", wr_n=74, queue="free",
         orders=147, role="Initiator", since="May 2023",
         rating="4.8", ontime="97%", disputes="0"),
    dict(handle="sova_na", slug="valorant", region="NA", hue=180,
         peak="Immortal 3 · 410 RR", tier="Immortal", wr_n=66, queue="free",
         orders=72, role="Initiator", since="Mar 2024",
         rating="4.6", ontime="94%", disputes="0"),
    dict(handle="kaya_v", slug="valorant", region="EU", hue=64,
         peak="Immortal 3 · 490 RR", tier="Immortal", wr_n=71, queue="free",
         orders=113, role="Sentinel", since="Aug 2023",
         rating="4.8", ontime="96%", disputes="0"),
    dict(handle="flux_v", slug="valorant", region="NA", hue=320,
         peak="Radiant #144", tier="Radiant", wr_n=77, queue="free",
         orders=182, role="Duelist", since="Jan 2023",
         rating="4.9", ontime="99%", disputes="0"),
    dict(handle="echo_v", slug="valorant", region="EU", hue=228,
         peak="Immortal 3 · 445 RR", tier="Immortal", wr_n=68, queue="1 order",
         orders=91, role="Controller", since="Dec 2023",
         rating="4.7", ontime="95%", disputes="0"),
]

# The page states a floor out loud; a row under it would make the page argue
# against itself. Cheaper to fail the build than to ship the contradiction.
for _b in BOOSTERS:
    assert _b["wr_n"] >= WR_FLOOR, (
        "%s is under the %d%% floor the boosters page states" % (_b["handle"], WR_FLOOR))
assert len({_b["handle"] for _b in BOOSTERS}) == len(BOOSTERS), "duplicate booster handle"

# The two roster figures the whole site quotes are COUNTED, not typed. They used
# to be hand-written and disagreed with the list underneath them the moment a
# booster was added — "34 on the board" over ten rows. Everything that says a
# number of boosters (the utility bar, the order card's "N of M free now", the
# rail's "All N boosters", the roster footer) reads these two, so counting them
# is what keeps that one claim true everywhere at once.
STATS["online"] = len(BOOSTERS)
STATS["free_now"] = sum(1 for _b in BOOSTERS if _b["queue"] == "free")

# ── booster avatars: a gaming glyph, not an initial ───────────────────────────
# The rail, the roster board and the track-order card all draw a booster inside
# the availability ring. That used to be the first letter of the handle, which
# on a 38px row reads as a placeholder and puts nine near-identical grey letters
# down one column. Each booster now gets one of these marks instead, tinted with
# their own `hue` — the same hue art.avatar() paints their profile portrait
# with, so the small avatar and the big one belong to the same person.
#
# Load-bearing:
#   * Every name here MUST be a key of build.py's `_ICONS` — build.py asserts it,
#     because a missing glyph would render an empty ring rather than fail.
#   * The pick is a pure function of the handle so the server-rendered row and
#     the one app.js draws from /api/boosters agree. `boosters.py` puts the
#     resolved name in its payload; the client never re-derives it.
#   * Availability stays the loud signal. `face_tint()` caps saturation well
#     under the ring's green/amber so a booster whose hue lands near either can
#     never be misread as a status colour — the rim and the pill own that.
FACE_GLYPHS = (
    "gamepad", "joystick", "dpad", "d20", "skull", "rocket", "flame", "potion",
    "crown", "sword", "knight", "shield-chevron", "trophy", "crosshair",
    "target", "bolt", "headset",
)


def _fnv(s):
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def face_glyph(handle):
    """Which glyph this handle wears."""
    return FACE_GLYPHS[_fnv(handle) % len(FACE_GLYPHS)]


def face_tint(handle, hue=None):
    """The glyph's colour and the plate behind it, from the booster's own hue.

    `hue` is optional because the roster store's `clean_booster()` does not
    require one: a row that arrives without it would otherwise hand every such
    booster the same hue-0 red, which is the column of identical avatars this
    replaces. Falls back to a hue off the handle, so a face is always theirs.
    """
    try:
        hue = int(hue)
    except (TypeError, ValueError):
        hue = None
    if hue is None:
        hue = (_fnv(handle) >> 8) % 360
    return ("hsl(%d 40%% 68%%)" % hue, "hsl(%d 26%% 14%%)" % hue)

# ── the vetting funnel (boosters hero) ────────────────────────────────────
# The right rail of the boosters page: the evidence for the H1's claim, in the
# shape of last month's intake. It replaced a card that previewed the same five
# rows as the table 300px below it.
#
# ⚠ These three figures are CLAIMS, not decoration — same status as STATS.
# Wire them to the applications queue before launch, and if the real numbers
# are less flattering ship the real numbers: the entire argument of this page
# is that it doesn't self-report. The three rule lines under them restate
# commitments the hero paragraph already makes; a fourth line means writing the
# sentence that backs it into the paragraph first.
VETTING = dict(
    title="How someone gets on this page",
    window="30 days",
    steps=[
        ("1,840", "applied last month"),
        ("96", "trialled live on our account — five games, watched"),
        ("11", "added to the board"),
    ],
    rules=[
        ("chart-up", "%d%% win-rate floor, checked monthly" % WR_FLOOR),
        ("plug", "Ranks read from the game API"),
        ("camera", "Trial games recorded and reviewed"),
    ],
    # The application channel, stated as a strip rather than a card: on this
    # page Discord is a supporting detail, not a headline offer. Four fragments
    # rather than one sentence because the member count sits in the middle of
    # it and i18n.js matches whole text nodes — build.py assembles them around
    # the figure's own <b>.
    strip=("Applications open in the", "Discord", "queue", "players in there."),
    strip_cta="Join",
)

# ── v2 "Ashfall" page content ─────────────────────────────────────────────
HERO = dict(
    kicker="",   # empty hides the slot entirely — build.py drops the element
    line1="The rank is yours.",
    line2="The grind isn't.",
    lede="Set two ranks. See the final price before you make an account. Then watch every match "
         "land from the dashboard — no bots, no shared logins, no invoice that moves after checkout.",
)

# ── home-hero booster spotlight ───────────────────────────────────────────
# The right column of the home hero (design_handoff_home_hero). It used to be
# floating text on the gradient; it is now the same card shell as every other
# module on the site, so it needs a booster to be about.
#
# `handle` names one of BOOSTERS above — the name, the order count and the
# portrait are all read off that entry, so this card can never disagree with
# the roster panel or the boosters page about the same person. Only the two
# labelled figures are written here: the handoff splits one dot-separated
# string ("Challenger 1042 LP · 78% WR · EUW") into two figures with their own
# labels, and peak_full is written differently per game ("Radiant #211",
# "FPL · 27k Premier · EU"), so there is no split rule to derive.
#
# A handle that is not on the roster hides the card — the handoff's fallback
# for a month with no qualifying booster is no card, never an empty one.
#
# `cta` is the label WITHOUT the handle — build.py appends it in its own <b>,
# the way the profile page's own "Order with vantaa" button does. i18n.js
# matches whole text nodes, so baking the name into the sentence meant every
# change of `handle` needed a new fr and de string; as a fragment it is one
# key that already exists and the handle stays data.
SPOTLIGHT = dict(
    handle="vantaa",
    eyebrow="This month's #1",
    # (figure, label, label suffix) — the suffix is data (a region), kept out
    # of the label's own text node so the label still translates.
    stats=[("1042 LP", "Challenger", ""), ("78%", "Win rate", "EUW")],
    cta="Order with",
    # Left blank: build.py points it at that handle's game configurator with
    # the booster attached (?booster=<handle>), so the destination follows
    # SPOTLIGHT["handle"] and matches what the button says it does.
    href="",
)

# ── Discount codes ─────────────────────────────────────────────────────────
# The single source of truth for every code the site honours. `pricing.py`
# resolves against this and applies the discount to the *charged* amount, so a
# code advertised here always works at checkout — never advertise one that
# isn't in this dict.
#
#   pct   fraction off the computed price (0.15 = 15% off)
#   label appears as the discount line item in the order summary
#   auto  True → applied to every order with nothing to type
#   ends  ISO date shown to the buyer; purely informational, not enforced
#
# Only one code applies to an order — discounts never stack. A typed code
# replaces the auto promo when it is worth more, and is otherwise ignored, so a
# buyer can never make their price worse by entering one.
PROMOS = {
    "SPLIT15": dict(pct=0.15, label="Summer sale", auto=True, ends="31 Aug"),
    # Affiliate and win-back codes go here, e.g.
    # "COMEBACK20": dict(pct=0.20, label="Welcome back", auto=False, ends=""),
}

# ── Top-bar promo slot ─────────────────────────────────────────────────────
# The left cell of the utility bar on every page. Every part of it — label,
# percentage, code, end date — is read off the auto promo above, so the bar can
# never advertise a discount the checkout doesn't honour.
#
# PROMO_TEXT is the lead-in only ("<label> — <pct> off with code"): build.py
# renders the code and the end date as their own spans so it can highlight the
# code and mute the date. Set PROMO_TEXT="" to hide the slot; `href` (optional)
# makes the line a link.
PROMO_TEXT = "%s — %s off with code"
PROMO_HREF = "/games/"


def auto_promo():
    """The code applied to every order with nothing to type, or (None, None).
    First `auto` entry wins — keep at most one."""
    for code, p in PROMOS.items():
        if p.get("auto"):
            return code, p
    return None, None


def promo_pct_label(p):
    return "%g%%" % round(p["pct"] * 100, 2)


_AUTO_CODE, _AUTO = auto_promo()
_HAS_PROMO = bool(_AUTO and PROMO_TEXT)
PROMO = dict(
    tag=("-" + promo_pct_label(_AUTO)) if _HAS_PROMO else "",
    text=(PROMO_TEXT % (_AUTO.get("label", "Sale"), promo_pct_label(_AUTO))) if _HAS_PROMO else "",
    code=_AUTO_CODE if _HAS_PROMO else "",
    ends=("ends %s" % _AUTO["ends"]) if (_HAS_PROMO and _AUTO.get("ends")) else "",
    href=PROMO_HREF,
)

# ── Trustpilot ─────────────────────────────────────────────────────────────
# eSports Boost's OWN Trustpilot profile. Left empty on purpose: the badge used
# to link to trustpilot.com/review/lolepicshop.com — a different brand name than
# the one on the page — which CRO-AUDIT #3 flags as reading like a copied
# template or a scam at the highest-intent moment in the funnel.
#
# While this is empty the badge still renders, showing the rating and review
# count, but as plain text with nothing to click. Set it to the real profile and
# every badge on the site becomes a link again, in one place.
TRUSTPILOT_URL = ""

MARQUEE = [
    "92,400 boosts delivered",
    "4.8 / 5 on Trustpilot — 3,140 reviews",
    "Most orders claimed within 18 min",
    "3,000 players in the Discord",
]

# ── delivered-today feed ──────────────────────────────────────────────────
# ⚠ PLACEHOLDER, like everything else in this block: these are four invented
# orders, not the orders table. Nothing here generates traffic — build.py
# renders exactly these rows and app.js only re-labels their clocks, so the
# feed can never show a delivery that did not happen.
#
# Wire to the real source by replacing this list with the last N closed orders
# and giving each row `ts` (epoch seconds, UTC) instead of `mins`; build.py and
# app.js both prefer `ts` when it is present. Keep the list capped — the footer
# figure (STATS["closed_24h"]) carries the rest.
#
#   slug     the game in GAMES — supplies the name, and the ladder the tier
#            marks take their colour from, so the feed and the game page can
#            never tint the same rank differently
#   initial  the lettermark. Chosen, not derived: Counter-Strike 2 is "C" and
#            Marvel Rivals is "R"
#   frm/to   (tier, division) — the tier must be a rung of that game's ladder,
#            because that is what tier_color() resolves against. Division is
#            what the mark prints; "" falls back to the tier's first 2 letters
#   rating   MMR-based ladders (CS2 Premier): the mark prints the rating number
#            in a wide mark and the tier name is written out beside it instead
#   mins     minutes before now. Only a placeholder stand-in for `ts`
LIVE_FEED = [
    dict(slug="league-of-legends", initial="L", region="EUW",
         frm=("Platinum", "II"), to=("Diamond", "IV"), mins=2, booster="vantaa"),
    dict(slug="valorant", initial="V", region="NA",
         frm=("Silver", "3"), to=("Ascendant", "1"), mins=14, booster="kx_reid"),
    dict(slug="counter-strike-2", initial="C", region="EU", rating="Premier",
         frm=("13k", "13,400"), to=("19k", "19,100"), mins=38, booster="sable"),
    dict(slug="marvel-rivals", initial="R", region="NA",
         frm=("Grandmaster", ""), to=("Celestial", ""), mins=60, booster="orvo"),
]

# ⚠ Marketing claims about your own operations — legal review before shipping.
#
# `body` is signed-off copy and must not be edited or split. `callout` and
# `mechanisms` restate it as scannable proof beside the prose — they are
# labels for claims the paragraphs already make, never new claims. Adding a
# fifth mechanism means adding the sentence that backs it to `body` first.
SAFETY = dict(
    title="Why this doesn't get you banned",
    body=[
        "Anti-cheat looks for software, not skill. Every solo order runs behind an enterprise "
        "VPN matched to your region, the booster mirrors your sensitivity and crosshair, and "
        "sessions are scheduled inside the hours you normally play — so the activity pattern on "
        "the account never changes. Duo orders never touch your login at all.",
        "If a boost triggers an account review, support files the appeal and the order is refunded "
        "in full while it runs. Your name, email and payment details are never shared with the "
        "booster.",
    ],
    callout=("97%", "Client satisfaction rate"),
    # (glyph, stroke?, label) — same shape as build.py's DASHBOARD_CHIPS.
    # "globe" is a filled glyph; the other three are linework.
    mechanisms=[
        ("globe", False, "VPN matched to your region"),
        ("crosshair", True, "Your sensitivity and crosshair"),
        ("clock", True, "Played in your normal hours"),
        ("eye-off", True, "Offline the whole order"),
    ],
    # The same list again, with a note per row and the fifth mechanism `body`
    # already backs ("Duo orders never touch your login at all"). The homepage
    # gets `mechanisms` — four labels beside the prose; the guarantee page gets
    # this — prose for readers, list for scanners, per the handoff.
    #
    # ⚠ The NOTES are the one place here that says more than `body` does. Each
    # is an operational commitment falsifiable by a single bad order, and the
    # handoff flags them as needing ops sign-off before launch: confirm the VPN
    # estate really is enterprise (not consumer, not datacentre IP), that
    # settings are mirrored then restored, and that the checkout play-window is
    # actually honoured in scheduling. If one isn't true, cut that note — the
    # name alone still works, and it is `body` that carries the argument.
    measures=[
        ("globe", False, "Enterprise VPN, matched to your region",
         "Not a consumer VPN and not a datacentre IP — the login location never changes."),
        ("crosshair", True, "Your sensitivity and crosshair",
         "The booster mirrors your settings before the first game."),
        ("clock", True, "Played inside your normal hours",
         "You set the window at checkout; sessions are scheduled inside it."),
        ("eye-off", True, "Offline appearance, whole order",
         "Friends see you offline until the order closes."),
        ("users", True, "Duo never touches your login",
         "You play your own account. Nobody signs in but you."),
    ],
    # Verbatim, and not to be softened: a page arguing for honesty cannot bury
    # the one paragraph that admits the risk is not zero. Rendered as a framed
    # plate on /guarantee.html so it reads as placed rather than left over.
    disclaimer=("Boosting is against the terms of service of every game listed here. We reduce "
                "the risk as far as it can be reduced and we will not pretend it is zero, "
                "because it isn't — any competitor telling you otherwise is lying to you."),
    link=("Read the full safety policy", "/guarantee.html"),
)

# ── Discord card (right rail) ─────────────────────────────────────────────
# The headline counts the same STATS["discord"] the stat band does. The mark is
# deliberately a generic chat glyph, not Discord's logo — same trademark rule
# as the payment marks and the Trustpilot star.
DISCORD = dict(
    label="Free to join",
    body="Free VOD reviews on Sundays, scrim pickups, and the booster application queue.",
    cta="Join the server",
    href="/support.html#discord",
)

# Mosaic: the six titles that get a tile, plus their span. Order mirrors the
# first six of GAMES so the homepage sorts games the same way the games index
# does; the remaining three fold into the "+ 3 more" cell. The spans are
# positional (big first tile, two wide tiles) — reassign by slot, not by game.
TILE_ORDER = [
    ("league-of-legends", "tile-span-2x2 tile-big"),
    ("valorant", "tile-span-2"),
    ("marvel-rivals", ""),
    ("teamfight-tactics", ""),
    ("overwatch-2", "tile-span-2"),
    ("dota-2", ""),
]

# ⚠ Placeholder reviews — invented, not real customer testimony (see top of file).
# At least six per game so every game page fills its reviews grid. The League of
# Legends block stays first so the homepage feed reads LoL, as designed.
#
# Four entries are rated below four, and they are load-bearing: /reviews.html
# says out loud that nothing is filtered by score, offers a "3★ or less" filter
# and a "Lowest rated" sort, and an empty result behind either of those reads as
# suppression — the exact thing the sentence denies. One of them (the League 3★)
# sits inside the first twelve so the default feed is not a wall of fives. Keep
# that property when this list is replaced by the real corpus.
#
# They complain about delay, silence and a booster swap, never about a ban or a
# stolen account: an invented review must not allege a harm the service claims
# never happens.
REVIEWS = [
    # ── League of Legends ──────────────────────────────────────────────────
    dict(rank="Gold IV → Platinum II", game="LoL · EUW",
         text="Booster took it in two evenings and left notes on what I was doing wrong in my "
              "own replays. Didn't expect that part."),
    dict(rank="Silver II → Gold I", game="LoL · EUNE",
         text="First boost I've ordered where the price on the calculator was exactly what came "
              "off my card. No upsell after."),
    dict(rank="Platinum IV → Diamond IV", game="LoL · NA",
         text="Duo queue, voice on, and he called every rotation. Felt like a coaching block I "
              "happened to win LP in."),
    dict(rank="Bronze I → Silver I", game="LoL · BR",
         text="Offline appearance the whole time, so none of my friends pinged me about it. "
              "Account still reads like mine."),
    dict(rank="Emerald III → Diamond II", game="LoL · EUW",
         text="Paused it for a weekend because I wanted to play, and it was back on the board "
              "within minutes when I un-paused."),
    dict(rank="Gold III → Platinum IV", game="LoL · EUW", stars=3,
         text="Sat unclaimed for two days after I paid and I had to chase it in Discord. Quick "
              "once someone picked it up, but I'd already asked for the refund by then."),
    dict(rank="Diamond IV → Master", game="LoL · KR",
         text="They queued in my normal evening hours on a regional VPN. No login change, no "
              "weird IP flags, no drama."),
    # ── Valorant ───────────────────────────────────────────────────────────
    dict(rank="Silver 2 → Gold 3", game="Valorant · EU",
         text="Loaded my own crosshair and sens before the first game. Match history looks like "
              "I actually played it."),
    dict(rank="Bronze 3 → Silver 2", game="Valorant · NA",
         text="Duo the whole way, voice on, no drama. Paused it twice because I wanted to play "
              "and it was free within ten minutes both times."),
    dict(rank="Gold 1 → Platinum 2", game="Valorant · AP",
         text="Asked for a specific agent pool so it stayed plausible. Every game was on Jett "
              "or Raze like I requested."),
    dict(rank="Platinum 3 → Diamond 1", game="Valorant · BR",
         text="Booster was clearly Radiant-level. Watched two of the games on the stream link "
              "and it wasn't close."),
    dict(rank="Diamond 2 → Ascendant 1", game="Valorant · EU", stars=4,
         text="Ran past the ETA by a day and they refunded the difference before I even opened "
              "a ticket about it."),
    dict(rank="Ascendant 3 → Immortal 1", game="Valorant · KR",
         text="Third order with the same booster now. He knows my setup and it just gets done "
              "on the nights I book."),
    # ── Counter-Strike 2 ───────────────────────────────────────────────────
    dict(rank="13k → 19k Premier", game="CS2 · EU", stars=4,
         text="Price on the calculator was the price I paid. That's the only reason I came back "
              "a third time."),
    dict(rank="10k → 15k Premier", game="CS2 · NA",
         text="No smurf stacking, no rating farm scripts. Just clean Premier games in my own "
              "region, spread over a week."),
    dict(rank="15k → 21k Premier", game="CS2 · EU",
         text="FPL-adjacent player took it. You can tell from the demos — the aim and the calls "
              "are a different tier."),
    dict(rank="5k → 13k Premier", game="CS2 · SA",
         text="Booked it low expecting a mess and it was the smoothest order I've had. Updated "
              "after every session."),
    dict(rank="17k → 25k Premier", game="CS2 · Asia",
         text="Anti-cheat-safe patterns the whole way, no bans, no overwatch flags. Rating "
              "stuck after the boost ended."),
    dict(rank="Faceit 6 → Faceit 9", game="CS2 · EU", stars=4,
         text="Refund was pro-rated to the levels I actually gained when one match went sideways. "
              "Fair about it, no argument."),
    dict(rank="13k → 17k Premier", game="CS2 · EU", stars=2,
         text="The second booster finished it, but the first one dropped it after two days and "
              "nobody told me — I found out by opening a ticket. The refund was fair. The "
              "silence wasn't."),
    # ── Teamfight Tactics ──────────────────────────────────────────────────
    dict(rank="10 placement games", game="TFT · EUW",
         text="Placements came back Diamond IV. Ordered at 1am, claimed before I woke up."),
    dict(rank="Gold II → Platinum I", game="TFT · NA",
         text="Current-set comps, not last patch's. You could see them playing the actual meta "
              "in the match history."),
    dict(rank="Silver III → Gold I", game="TFT · EUNE",
         text="Double-up run played with me, so it doubled as a lesson on econ and when to roll. "
              "Worth it just for that."),
    dict(rank="Platinum I → Diamond III", game="TFT · BR",
         text="No bots, no scripted play. Real games, real tempo, and the LP graph moved the "
              "way you'd expect from a human."),
    dict(rank="Emerald II → Diamond I", game="TFT · EUW",
         text="Cheapest of the games I've boosted and it still came with per-session updates. "
              "Didn't feel like a budget service."),
    dict(rank="Diamond III → Master", game="TFT · KR",
         text="Booster was Challenger on the ladder and it showed in the positioning. Clean "
              "climb, no losing streaks parked on my account."),
    # ── Marvel Rivals ──────────────────────────────────────────────────────
    dict(rank="Bronze → Platinum", game="Marvel Rivals · EU",
         text="Long climb, updated after every session, and I could see the match history live. "
              "No surprises anywhere."),
    dict(rank="Silver II → Gold I", game="Marvel Rivals · NA",
         text="Hero pool respected — they stuck to the roles I actually play, so the profile "
              "didn't turn into someone else's."),
    dict(rank="Gold I → Platinum II", game="Marvel Rivals · Asia",
         text="Duo queue with voice and the booster called the whole fight every round. Learned "
              "more than the rank was worth."),
    dict(rank="Platinum III → Diamond II", game="Marvel Rivals · SA",
         text="Booked role-locked support and that's exactly what I got. Every game, no flexing "
              "onto DPS to pad the win rate."),
    dict(rank="Diamond II → Grandmaster", game="Marvel Rivals · EU",
         text="Price locked at checkout even though I ordered right before a season reset. Didn't "
              "move a cent after."),
    dict(rank="Gold III → Platinum I", game="Marvel Rivals · EU", stars=3,
         text="Got the rank, didn't get the role. I booked support only and half the games are "
              "on a duelist, so the profile doesn't read like mine any more."),
    dict(rank="Grandmaster III → Celestial", game="Marvel Rivals · NA",
         text="Celestial push was hand-matched to someone who mains my roles. Felt like the "
              "account was in the right hands the whole time."),
    # ── Dota 2 ─────────────────────────────────────────────────────────────
    dict(rank="Archon 3 → Legend 2", game="Dota 2 · SEA", stars=4,
         text="Behaviour score untouched, no reports, no weird hours. They played my usual "
              "evening slot and that was that."),
    dict(rank="Crusader 1 → Archon 4", game="Dota 2 · EU West",
         text="MMR came in right where the bracket estimate said it would. No overshoot, no "
              "surprise recalibration afterwards."),
    dict(rank="Legend 4 → Ancient 2", game="Dota 2 · US East",
         text="Calibration run played my signature heroes so the profile stayed believable. "
              "Nobody in my stack noticed a thing."),
    dict(rank="Guardian 2 → Crusader 3", game="Dota 2 · SA",
         text="Started low and nervous about it, but the updates after every session kept me in "
              "the loop the whole way up."),
    dict(rank="Ancient 3 → Divine 1", game="Dota 2 · EU East",
         text="Immortal booster who stayed in my bracket the whole time, never queued above it. "
              "Exactly what the page promised."),
    dict(rank="Divine 2 → Immortal", game="Dota 2 · China",
         text="Duo the last stretch and the rotations he called were a different game entirely. "
              "Behaviour score actually went up."),
    dict(rank="Legend 1 → Ancient 1", game="Dota 2 · EU West", stars=1,
         text="Four days, no progress, then they cancelled it on me. Full refund the same day, "
              "which is the only thing that went right. Nothing was delivered."),
    # ── Apex Legends ───────────────────────────────────────────────────────
    dict(rank="Gold → Diamond", game="Apex · NA",
         text="Refund on the last two divisions when they ran past the ETA, without me having "
              "to chase it. Rare."),
    dict(rank="Silver IV → Gold II", game="Apex · EU",
         text="Legend pool matched to mine, so the account still looks like I play it. No "
              "off-meta picks I'd never touch."),
    dict(rank="Platinum II → Diamond III", game="Apex · Asia",
         text="Duo queue on voice and the booster carried the IGL calls the whole time. Climbed "
              "and learned rotations at once."),
    dict(rank="20-bomb + 4K badge", game="Apex · NA",
         text="Booked both badges on one legend and they landed inside three sessions. Match "
              "history backs it up cleanly."),
    dict(rank="Diamond III → Master", game="Apex · SA",
         text="Re-quoted daily on the way to Master because Pred was moving, and the number "
              "never jumped after I paid."),
    dict(rank="Gold II → Platinum I", game="Apex · Oceania",
         text="OCE booster in my own region, no cross-region ping weirdness. Played my normal "
              "hours and kept me posted."),
    # ── Overwatch 2 ────────────────────────────────────────────────────────
    dict(rank="Platinum → Diamond", game="Overwatch 2 · EU",
         text="Asked for support only and that's what I got. Profile still looks like mine, "
              "which was the whole point."),
    dict(rank="Gold 3 → Platinum 1", game="Overwatch 2 · NA",
         text="Per-role SR moved on exactly the role I booked and left the others alone. Clean, "
              "no collateral on my tank rank."),
    dict(rank="Silver 2 → Gold 2", game="Overwatch 2 · Asia",
         text="Hero pool respected the whole way. It doesn't read like a different player logged "
              "in, which is why I paid for that."),
    dict(rank="Diamond 4 → Master 5", game="Overwatch 2 · EU",
         text="Duo queue, voice on, and the shot-calling alone was worth the add-on. Won more "
              "than I expected to."),
    dict(rank="Master 3 → Grandmaster 4", game="Overwatch 2 · NA",
         text="Booster was Champion on the DPS role and it showed. No lost streaks parked on the "
              "account while I wasn't watching."),
    dict(rank="Bronze → Platinum", game="Overwatch 2 · SA",
         text="Big jump and they updated after every block of games. Watched a couple on the "
              "stream link — all legit."),
    # ── Rocket League ──────────────────────────────────────────────────────
    dict(rank="Champion → Grand Champ", game="Rocket League · EU",
         text="Booster called rotations on voice the whole duo run. Honestly worth it for the "
              "coaching alone."),
    dict(rank="Gold II → Platinum I", game="Rocket League · NA East",
         text="One playlist, quoted per order like the note said, and the price never moved. "
              "Exactly the 2v2 rank I booked."),
    dict(rank="Silver III → Gold II", game="Rocket League · SAM",
         text="Started low expecting a bot farm and got real games instead. MMR held after the "
              "order finished."),
    dict(rank="Platinum I → Diamond II", game="Rocket League · NA West",
         text="Duo sessions in my own region, no lag, and the rotation callouts stuck with me "
              "well past the boost."),
    dict(rank="Diamond III → Champion I", game="Rocket League · EU",
         text="Paused mid-order for a tournament I wanted to play myself, un-paused after, and "
              "it picked straight back up."),
    dict(rank="Grand Champ I → Supersonic", game="Rocket League · Oceania",
         text="SSL push handled by someone clearly at that level. Mechanics in the replays are "
              "nowhere near mine — in a good way."),
]

# Every review card carries a rating and a date. Both are placeholder like the
# copy above.
#
# `stars` defaults to 5 and is spelled out above only on the reviews that read
# as a four — a wall of identical five-star cards reads as fabricated, which is
# the opposite of what the section is for. `days` is how long ago the order
# closed; build.py turns it into a real date, so the feed ages with the build
# instead of freezing on whatever month it was written in. Newest first, one
# day apart, in the order the list is written.
# ⚠ Reviewer display names are INVENTED, exactly like the review copy above and
# the fifty booster profiles — a first name and a surname initial, assigned
# deterministically by position so a rebuild never reshuffles who said what. The
# game pages draw them beside an initials avatar. They must be replaced with the
# real corpus (or dropped) before launch, along with everything else in this
# block; see the placeholder warning at the top of this file.
_REVIEW_NAMES = (
    "Marek K.", "Dee R.", "Tomas V.", "Ilias B.", "Sanne D.", "Rafa M.",
    "Jonas L.", "Priya N.", "Emre A.", "Nils P.", "Owen T.", "Kaisa H.",
    "Bruno S.", "Lena F.", "Arto V.", "Mateo G.", "Yusuf C.", "Nora W.",
    "Pavel Z.", "Iris K.",
)


def _initials(name):
    """"Marek K." → "MK". Two letters at most; the avatar is 26px."""
    parts = [p for p in str(name).replace(".", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


for _i, _r in enumerate(REVIEWS):
    _r.setdefault("stars", 5)
    _r.setdefault("days", _i + 1)
    _r.setdefault("by", _REVIEW_NAMES[_i % len(_REVIEW_NAMES)])
    _r.setdefault("initials", _initials(_r["by"]))


# ── roster: the derived half ──────────────────────────────────────────────
# Fifty boosters written out longhand would be a thousand lines of fields that
# repeat a pattern, and every one of them a place for the roster to contradict
# itself. Only the irreducible facts about a person are typed above; everything
# below is computed from them, so it cannot drift:
#
#   game / peak_full   the game's own `short` and the booster's region
#   wr                 the same figure as wr_n (TFT writes its own, see mera)
#   reviews_n          orders × the sampled review rate
#   climbs             the four ladder bands below their peak, splitting
#                      `orders` — so the profile's "Climbs delivered" card and
#                      its completed-orders table are made of the same climbs,
#                      and the card's counts add up to the stat card above it
#   review             one of this game's REVIEWS entries, picked by handle
#
# Deriving the testimonial is deliberate: the alternative is fifty *more*
# invented quotes, and these are already the site's placeholder reviews. It
# stays a placeholder either way — see the warning at the top of this file.
_BOOSTER_BY_SLUG = {g["slug"]: g for g in GAMES}

# 187 reviews against 214 delivered orders — the ratio the hand-written pair
# implied, kept so the derived figure reproduces it exactly.
_REVIEW_RATE = 187 / 214

# Descending share of a booster's orders across the four bands they work. The
# last band takes the remainder, so the four always sum to `orders` exactly.
_BAND_SHARE = (0.332, 0.294, 0.224)


def _handle_seed(handle, salt=0):
    h = 2166136261
    for c in "%s#%d" % (handle, salt):
        h = (h * 16777619 + ord(c)) & 0xFFFFFFFF
    return h


def _climb_bands(g, b):
    """The rank bands a booster actually works: the four rungs below their peak.

    A peak is a career high, so the bands END at it — a Challenger player sells
    the climbs up to Master, not the ones above their own rank. A peak above
    the ladder we sell (Challenger on a League ladder that stops at Master)
    lands on the top of the ladder, which is the same thing.
    """
    tiers = g["tiers"]
    hi = tiers.index(b["tier"]) if b["tier"] in tiers else len(tiers) - 1
    hi = max(1, hi)
    pairs = [("%s → %s" % (tiers[i], tiers[i + 1])) for i in range(max(0, hi - 4), hi)]
    if not pairs:
        return []
    total, out, spent = b["orders"], [], 0
    for i, name in enumerate(pairs[:-1]):
        n = max(1, round(total * _BAND_SHARE[min(i, len(_BAND_SHARE) - 1)]))
        out.append((name, n))
        spent += n
    out.append((pairs[-1], max(1, total - spent)))
    return out


def _pick_review(b):
    """One of this game's placeholder reviews, as (text, initials, stars, days).

    Same pool the reviews page draws from, matched on the booster's own game so
    a League profile never quotes a Valorant order. No game copy → no card:
    review_card_rail() drops it rather than rendering an empty one.

    Four stars and up, which is not score-filtering in the sense /reviews.html
    denies — that page shows every one of these. It is attribution: the low
    fixtures are complaints about an order changing hands or never being
    claimed, so printing one on a named booster's profile as *their* latest
    review invents a specific accusation against a specific person.
    """
    g = _BOOSTER_BY_SLUG.get(b["slug"])
    if not g:
        return None
    token = g["short"].lower()
    pool = [r for r in REVIEWS
            if r["stars"] >= 4
            and r["game"].split(" · ")[0].strip().lower() in (token, g["name"].lower())]
    if not pool:
        return None
    seed = _handle_seed(b["handle"])
    r = pool[seed % len(pool)]
    letters = [c for c in b["handle"].upper() if c.isalpha()][:2] or ["B"]
    return (r["text"], "".join(letters), float(r["stars"]), 1 + seed % 9)


for _b in BOOSTERS:
    _g = _BOOSTER_BY_SLUG.get(_b["slug"])
    _b.setdefault("wr", "%d%%" % _b["wr_n"])
    if _g:
        _b.setdefault("game", "%s · %s" % (_g["short"], _b["region"]))
        _b.setdefault("peak_full", "%s · %s" % (_b["peak"], _b["region"]))
        _b.setdefault("climbs", _climb_bands(_g, _b))
    _b.setdefault("reviews_n", max(1, round(_b["orders"] * _REVIEW_RATE)))
    if not _b.get("review"):
        _b["review"] = _pick_review(_b)
    assert sum(n for _, n in _b["climbs"]) == _b["orders"], (
        "%s: climb bands must add up to the order count the stat card shows" % _b["handle"])


STEPS = [
    ("01", "Configure and pay",
     "Ranks, mode, champion or agent preferences, offline appear, scheduled hours. "
     "The price never changes after checkout."),
    ("02", "A booster claims it, usually inside 20 minutes",
     "You see their rank, region, win rate and current queue before they start. "
     "Swap them once, free, no reason needed."),
    ("03", "Track every match, pause any time",
     "Match history, LP graph and chat in one dashboard. Pause from the dashboard and "
     "the account is yours again in minutes."),
]

# (glyph, stroke?, kicker, title, body, proof) — the three promises, twice:
# bare kicker/title/body in the `cards-3` shell on /games/ and the game pages,
# and with the icon tile and the proof line on /guarantee.html, which is where
# the handoff draws them. One entry per promise so the two can never disagree.
#
# The proof line is the card's receipt: a single checkable fact under a claim.
# Support's is read off STATS["reply"] rather than typed — the handoff's own
# "Median first reply 4 minutes" is flagged there as an invented figure, and
# this site already measures one.
GUARANTEES = [
    ("shield-check", True, "Guarantee", "Finished or refunded",
     "Every order ends in the rank you paid for or the money back for the part that never "
     "arrived. There is no third outcome.",
     "Refunded in full until a booster claims it"),
    ("ghost", False, "Privacy", "Nobody sees your name",
     "Boosters get a rank, a server and your play window. Your name, email and payment "
     "details never reach them, and the order needs no account.",
     "Card details stay with Stripe"),
    ("headset", True, "Support", "Answered in minutes, not days",
     "One thread per order, staffed around the clock. If an account review lands, support "
     "files the appeal for you rather than pointing you at a form.",
     "Median first reply %s" % STATS["reply"]),
]

# ── /guarantee.html — the refund policy itself ────────────────────────────
# ⚠ POLICY TEXT, not marketing copy. Every number below is a commitment the
# business is held to: 5 business days to refund, 24 hours to an automatic
# refund on an unclaimed order, 15% credit past the ETA, and the pro-rata rule.
# Legal review before shipping, and version this block rather than editing it
# in place — the checkout page's refund line must stay word-for-word with it.
#
# `{n}` in a stat label marks the one figure inside the sentence: build.py
# splits there and wraps the number in its own node, so the words around it
# stay whole translatable text nodes (see CLAUDE.md's i18n rule).
GUARANTEE = dict(
    stats=[
        ("5 days", "Refunds land back on the original payment method, no ticket needed", ""),
        ("24 hrs", "Unclaimed after payment? Refunded in full, automatically", ""),
    ],
    # (glyph, stroke?, stage, title, body). The order is the order an order
    # moves through — before a booster claims it, mid-climb, past the ETA — and
    # the first card takes the accent border because it is where most refunds
    # land. Reordering these breaks the argument.
    cases=[
        ("undo", True, "Before a booster claims it", "100% back, no reason asked",
         "One button in the order page. The money is back on the original payment method "
         "within 5 business days, and nobody will email you to ask why."),
        ("pie", True, "Started but unfinished", "Pro-rated on what wasn't delivered",
         "Divisions not climbed and wins not won are refunded at the same rate you paid for "
         "them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond portion, "
         "calculated by the same formula that quoted you."),
        ("bell", True, "Past the ETA", "Your choice, and we tell you first",
         "If an order runs past its delivery window we message you before you notice: keep "
         "going with a 15% credit, swap the booster, or take the unfinished portion back."),
    ],
    # (id, question, answer). The id is a deep-link target — support sends
    # people to a specific answer ("see the ban question"), so these are a
    # public contract: rename one and the links in old tickets stop landing.
    #
    # ⚠ Three answers contradict the sales pitch on purpose: don't queue ranked
    # alongside an unpaused solo order, naming a booster means a slower start,
    # and the ToS risk is real. They are why the page is credible. Keep them.
    #
    # `{duo}` is filled from pricing.DUO_MULT in build.py — data.py cannot
    # import pricing (pricing imports data), and a typed percentage here would
    # drift from the formula the way the handoff's "35%" already has.
    faq=[
        ("play-along", "Can I play my own account while an order runs?",
         "Yes, and it costs nothing. Pause the order from the order page and the booster "
         "stops at the end of the current game; unpause and it resumes the same night if a "
         "slot is open. Playing ranked yourself while a solo order is unpaused is the one "
         "thing to avoid — two people queuing the same account is what looks abnormal, not "
         "the boost."),
        ("review-or-ban", "What happens if my account gets a review or a ban?",
         "Support files the appeal for you and the order is refunded in full while it runs, "
         "so you are never paying for an account you cannot use. Boosting still breaks every "
         "listed game's terms of service — the risk is reduced as far as it can be, not removed."),
        ("password-and-settings", "Will the booster change my password or my settings?",
         "No. Login details are used to sign in and nothing else — no password changes, no "
         "email changes, no purchases, no rune or loadout edits beyond the champions and "
         "roles you asked for. Sensitivity and crosshair are mirrored to yours, then "
         "restored. Change your password once the order closes anyway; the order page tells "
         "you when."),
        ("price", "How is the price calculated, and can it change after I pay?",
         "The price is per division crossed, so a longer climb costs more per step than a "
         "short one. It is fixed at checkout: the number on the button is the number "
         "charged, and nothing is added later. Duo adds {duo}% because the booster carries a "
         "second player, and add-ons are priced individually before you pay."),
        ("no-account", "Do I have to make an account to order?",
         "No. Orders are created against your email and you get a one-click link to follow "
         "them. Set a password afterwards if you want the dashboard to remember your orders; "
         "skip it and the link still works. Your name, email and card details are never "
         "shared with the booster."),
        ("named-booster", "Can I pick a specific booster?",
         "Yes — name one at checkout from their profile and the order waits for them instead "
         "of going to the open board. That means a slower start, so we show their current "
         "queue and slots before you commit. Leave it open and the first free booster in "
         "your bracket claims it, usually inside %s." % STATS["median_claim"]),
    ],
    # The handoff's FAQ intro claims the six are "ranked by volume over the last
    # 90 days" and flags it as invented. This order is editorial, so the
    # sentence says so instead of borrowing authority it hasn't got.
    faq_note=("The six support answers most. If yours isn't here, the thread on your order "
              "reaches a person, not a bot."),
)

# (icon, title, body) — same shape as SAFETY["mechanisms"]: the glyph belongs
# with the line it labels, so a reordered list can't hand a claim the wrong
# icon. Every one of these is a promise the shipped dashboard is held to — if
# pause takes an hour rather than minutes, this copy changes.
DASHBOARD_POINTS = [
    ("list-search", "Match-by-match history",
     "Every game your booster plays, with the LP swing, KDA and replay link."),
    ("pause-circle", "Pause on one click",
     "Want to play tonight? Pause, and the account is free within minutes."),
    ("chat", "Chat with the booster, not a queue",
     "Ask for a champion pool, a schedule, or a swap. Support reads the same thread."),
]

# ── The demo order ─────────────────────────────────────────────────────────
# One invented order, rendered twice: as the dashboard mock on the homepage and
# as the resolved order on /demo.html. It lives here rather than in either page
# because the homepage section links straight at the demo page — a buyer who
# follows "Open the demo dashboard" has to land on the same ESB-3F92K1, with the
# same five games on it, or the mock stops being evidence of anything.
#
# Same standing as STATS and REVIEWS: a placeholder, not a real order. Which is
# why the page it fills is called Demo and both renderings carry an "Example"
# pill — an order code on a page called "Track my order" reads as *your* order.
#
# Deliberately NOT stored here, because build.py derives them and they must stay
# true if these ranks move: the completion percentage (ladder distance covered),
# the days left, the W-L record, the price, and the timeline's live event.
DEMO_ORDER = dict(
    id="ESB-3F92K1",
    game="League of Legends", region="EUW", mode="Solo", booster="vantaa",
    start=("Gold", "IV"),            # where the order was bought
    at=("Platinum", "II"), lp=62,    # where the booster has got to
    target=("Diamond", "IV"),
    games=38, lp_net=412,
    # LP across the order: 13 authored points on the chart's 104-unit box, where
    # 94 is the baseline and smaller is higher. A dip early, then the climb.
    # Hand-plotted to match the story above — re-plot them if it changes.
    chart=(88, 82, 90, 74, 77, 62, 55, 64, 44, 35, 40, 22, 12),
    # The last five games, newest first. `when` is minutes ago. `champ` is the
    # tint of the portrait slot, not a tier colour: Riot's champion art is
    # licensed, so the slot ships as an abstract marker sized for a real 30px
    # portrait to drop into.
    matches=[
        dict(result="Win",  kda="11 / 2 / 9", lp="+24", when=21,  champ="#b1764c"),
        dict(result="Win",  kda="7 / 4 / 14", lp="+22", when=58,  champ="#a37ad6"),
        dict(result="Loss", kda="3 / 6 / 7",  lp="−18", when=64,  champ="#5f93de"),
        dict(result="Win",  kda="15 / 3 / 5", lp="+25", when=120, champ="#3fa06c"),
        dict(result="Win",  kda="9 / 1 / 11", lp="+21", when=181, champ="#4fb0aa"),
    ],
    # ── the order-details rail (design_handoff_track_order) ────────────────
    # Add-ons are ADDONS ids, not typed labels, and build.py prices the order
    # with them — a details row naming an upsell the quote didn't charge for is
    # the same class of bug as a hand-typed price.
    addons=("champ",),
    window="Evenings",
    # Timeline, oldest last. The live event on top is NOT stored: build.py
    # derives it from `at` and the newest match, so the first row can never
    # contradict the card beside it. `milestones` are the rank rows below it,
    # newest first — the rank is separate from the wording so it can be drawn
    # as a tier mark and the sentence around it stays translatable.
    milestones=[("Platinum", "IV", "Yesterday, 23:10")],
    claimed="4 Aug, 21:32", claim_lag=11,   # minutes between payment and claim
    placed="4 Aug, 21:21", paid_on="4 Aug",
)

# ── Per-game demo orders for the game page's "While it runs" mock ───────────
# The homepage and /demo.html render DEMO_ORDER (a League order). The game page's
# "02 While it runs" band renders the order for THE GAME BEING VIEWED, so a
# Valorant page shows a Valorant climb in RR, not a League climb in LP. Any game
# without an entry falls back to DEMO_ORDER — same as before. These are the same
# kind of placeholder as DEMO_ORDER: an invented order drawn as a product shot.
# build.py derives pct / days / record / price / timeline from the ranks, exactly
# as it does for DEMO_ORDER; unit ("RR") and queue ("Competitive") come off the
# game. Ranks must be rungs of that game's ladder.
GAME_DEMOS = {
    "Valorant": dict(
        id="ESB-7K21RA",
        game="Valorant", region="EU", mode="Solo", booster="orvo",
        start=("Gold", "1"),
        at=("Platinum", "2"), lp=64,        # RR within the current act
        target=("Diamond", "1"),
        games=41, lp_net=305,               # net RR across the order
        chart=(90, 84, 92, 78, 80, 66, 58, 67, 47, 38, 43, 26, 14),
        # Valorant match records: agent-tint slot, KDA, RR swing per game.
        matches=[
            dict(result="Win",  kda="22 / 14 / 6", lp="+24", when=18,  champ="#d05a5a"),
            dict(result="Win",  kda="18 / 11 / 8", lp="+21", when=52,  champ="#4fa3c7"),
            dict(result="Loss", kda="9 / 16 / 4",  lp="−17", when=61,  champ="#7a6cd6"),
            dict(result="Win",  kda="25 / 12 / 7", lp="+26", when=115, champ="#4fb07a"),
            dict(result="Win",  kda="16 / 9 / 11", lp="+20", when=174, champ="#c79a4f"),
        ],
    ),
}

# ── /games/ — the catalogue page — design_handoff_games_page ───────────────
# The two pieces of copy that page owns: the four service explainers (band 01)
# and the five questions asked about the catalogue rather than about one title
# (band 04). Everything else on it — prices, counts, the roster, the Discord
# size, the reply time — is read off the catalogue, the pricing engine, BOOSTERS
# or STATS by build.py. The handoff's own nine "from" prices, nine order counts,
# 78-booster figure and "3,000 in the Discord" are flagged there as invented, and
# this site already computes every one of them.
#
# `{...}` markers are figures build.py substitutes so no number is typed here:
#   {cap}   the units cap (pricing.UNIT_MAX)      {n}      titles in the catalogue
#   {coach} titles with coaching                  {cheap}  cheapest title, {cp} its price
#   {code}  the auto promo code, {pct} its cut    {dear}   dearest title,  {dp} its price
#   {lo}–{hi}  the bundle discount range
CATALOG_SERVICES = [
    ("chart-up", "Division boost",
     "Two ranks, one price. Your booster climbs from where you are to where you want to "
     "be, and the number never moves after checkout.",
     "You know the rank you want"),
    ("plus", "Net wins",
     "Priced per win above your losses, {cap} to an order. A short push when you are close "
     "and do not want to commit to a full climb.",
     "You are one division short"),
    ("target", "Placements",
     "We play up to {cap} of your season games, on a ranked account or a fresh one. The "
     "rank you land is the rank you keep.",
     "The season just reset"),
    ("monitor", "Coaching",
     "An hour with a coach from the roster, live on Discord, screen shared and recorded for "
     "you to keep. Live on {coach} of the {n} titles.",
     "You want to climb it yourself"),
]

# ⚠ Two answers below are commitments, not descriptions, and each is falsifiable
# by a single order: that a booster plays exactly one title, and that there is no
# cross-title bundle. The second is a structural claim — if sales ever wants a
# cross-title discount, this answer has to change first (the handoff says so too).
# Ids are a public contract: support links people at #faq-<id>, so renaming one
# breaks the links in old tickets.
CATALOG_FAQ = [
    ("titles", "Are these all the titles you cover?",
     "These {n} are the ones with a live board and enough boosters to claim an order "
     "quickly. We take one-off requests on other titles in Discord, but there is no page "
     "and no instant price for them — if the queue cannot claim it, we say so rather than "
     "take the money."),
    ("price-differs", "Why is {cheap} cheaper than {dear}?",
     "A division is not the same amount of work in every game. Ladders are different "
     "lengths, matches are different lengths, and one rung near the top of a ladder can "
     "cost several near the bottom of another. Each title carries its own multiplier, and "
     "it is on screen before you sign in: the cheapest single division is {cp} on {cheap} "
     "and {dp} on {dear}."),
    ("one-game", "Does one booster cover several games?",
     "No. Everyone on the board plays exactly one title, and their profile carries the peak "
     "rank, the win rate, the on-time record and the orders they have delivered on it. "
     "Somebody claiming three ladders at once is somebody we did not hire."),
    ("two-titles", "Can I order two titles at once?",
     "Yes, as two orders — each gets its own booster, price and dashboard. There is no "
     "cross-title bundle, because a discount spanning two boosters would be paying one of "
     "them less."),
    # `{oneof}` is the "and the bundle is the deeper cut" clause. build.py only
    # writes it when the cheapest bundle actually beats the sitewide code —
    # re-tune either and the sentence stops asserting it rather than going stale.
    ("sale", "Do prices change during a sale?",
     "{code} takes {pct} off the whole catalogue with nothing to type. Each game page also "
     "carries bundle climbs at {lo} to {hi} off, and a bundle replaces the code rather than "
     "adding to it — there is only ever one discount on an order{oneof}."),
]

FAQ = [
    ("Do I need an account to see the price?",
     "No. The calculator is on every page and needs nothing from you. You only enter an "
     "email at checkout, and only so we can send you the order link."),
    ("Can I check out without creating an account?",
     "Yes. Email, then payment. We create the order under that address and email you a "
     "one-click link to follow it. Set a password later if you want one, or never."),
    ("Is my account safe?",
     "Your booster connects through a VPN in your region, appears offline, and plays inside "
     "the hours you set. We never ask for a Riot/Steam/Blizzard recovery email, never change "
     "your password, and never queue with other customers' accounts."),
    ("What if I want to play while the boost is running?",
     "Pause it from the dashboard. The account is free within minutes and the timer stops. "
     "Resume when you're done."),
    ("What exactly is refunded, and when?",
     "In full, no questions, until a booster claims the order. After that, pro-rated on the "
     "part that hasn't been delivered — divisions not climbed, wins not won. Refunds are "
     "issued to the original payment method within 5 business days."),
    ("Solo or duo — which should I pick?",
     "Solo is faster and cheaper: the booster plays alone. Duo means you play every game "
     "with them, nobody logs into your account, and it costs 55% more for the extra time."),
    ("How fast will someone start?",
     "Median time to a claimed order last month was 18 minutes. Priority queue takes that "
     "down to about 6. If nobody claims it within 24 hours, you get a full refund "
     "automatically — you don't have to ask."),
    ("Which payment methods do you take?",
     "Cards, Apple Pay and Google Pay, all handled securely by Stripe. Crypto is coming soon. "
     "The card statement reads as a neutral merchant name, not the service."),
]

# ── /support — design_handoff_support ──────────────────────────────────────
# The contact page's content: two channels, a triage form, and a six-item FAQ.
# Kept next to GUARANTEE because their FAQs overlap (refunds, pausing, playing
# during an order) and MUST NOT diverge — same facts, different words for a
# different reader. If a policy number moves in GUARANTEE, move it here too.
#
# Two deliberate honesty edits vs the handoff, same standing as the placeholder
# note at the top of this file:
#   · the hero runs TWO stats, not three. The handoff's third, "91% closed on
#     the first reply", has no source, and its own note says to measure it or
#     drop the row. Both figures here are read from STATS, so they can't drift.
#   · the status pill is wired to the real FOOT_SUPPORT_ONLINE seam in build.py
#     rather than hard-coding a headcount ("6 on shift, EU and NA") — an
#     invented rota number of a kind nothing else on the site carries. If it
#     cannot be a live read-out, build.py degrades it to the reply time.
#
# ⚠ Two lines below are commitments this page invents and ops must confirm
# before launch (the handoff flags both): the free booster swap ("once per
# order, at no charge") in the swap FAQ, and — softened here already — the
# "we won't act on a message that contains one" password line. Where one isn't
# operationally true, cut it rather than soften it further.
SUPPORT = dict(
    # Hero stat list — (STATS key, label). The figure is read from STATS so the
    # page can't quote a different reply time or Discord size than the rest of
    # the site. Two, not three; see the note above.
    stats=[
        ("reply", "Median first reply last month"),
        ("discord", "Players in the Discord"),
    ],
    # "What to put in it" — four rows that cut a round trip out of every ticket.
    # (icon, name, note). Row 4 is the point of the list — keep it.
    include=[
        ("hash", "The order number",
         "Anything starting ESB-. It skips triage and lands with the person on that order."),
        ("target", "What you expected",
         "The rank, the date, the thing the checkout said you were buying."),
        ("image-square", "What actually happened",
         "Screenshots beat descriptions. Paste them straight into the thread."),
        ("lock-key", "Nothing else",
         "No passwords, no 2FA codes. Support will never ask for one, and won't act on a "
         "message that contains one."),
    ],
    # Topic chips. (label, needs_order, placeholder). Choosing a topic sets the
    # message placeholder — the cheapest triage on the page — and shows the
    # order-number field for the three order-related topics. Changing topic must
    # not clear what has been typed; only the placeholder changes.
    topics=[
        ("Order issue", True,
         "What the order was meant to do, and what it did instead."),
        ("Refund", True,
         "What you want refunded and why. We read the order before replying, so you can "
         "keep it short."),
        ("Booster swap", True,
         "Which order, and whether you want a reason on the record. You do not have to "
         "give one."),
        ("Before I buy", False,
         "Ask anything. Pre-sales questions sit in the same queue as everything else."),
        ("Something else", False,
         "What's going on?"),
    ],
    # Six answers, ordered by ticket volume — the first two are the majority of
    # contacts and both resolve without a human. (id, question, answer). The ids
    # are deep-link targets (support links people at a specific answer), so they
    # are a public contract: renaming one breaks the links in old tickets.
    faq=[
        ("find-order", "Where is my order? I never made an account.",
         "You do not need one. Guest orders are tracked by the link we emailed when you "
         "paid — it never expires and works on any device. Lost it? Open the order lookup, "
         "enter the address you paid with, and we send it again."),
        ("unclaimed", "Nobody has claimed my order yet.",
         "Median claim time is %s, and most of the rest go within the hour. If nothing has "
         "claimed it 24 hours after payment, the order refunds itself automatically — no "
         "ticket, no asking. Writing in before that does not move it up the board."
         % STATS["median_claim"]),
        ("refund", "Can I get a refund?",
         "In full, any time before a booster claims it. After that it is pro-rated on what "
         "has not been delivered — you keep the divisions already climbed and get the rest "
         "back. Money lands on the original payment method within 5 business days."),
        ("swap", "Can I swap to a different booster?",
         "Yes, once per order, at no charge. Ask in the order thread. The order goes back "
         "on the board and is usually re-claimed the same day; if you would rather not say "
         "why, do not — we do not ask."),
        ("play-during", "Can I play on my account while an order is running?",
         "Pause it first, from the order page. Pausing is free and resumes the same night "
         "if a slot is open. What you should not do is queue ranked alongside an unpaused "
         "solo order — two people on one account in the same queue is the fastest way to "
         "get flagged."),
        ("past-eta", "My order is past the delivery estimate.",
         "A 15% credit applies automatically once an order runs past its window, and it "
         "shows on the order page without anyone having to ask. If it is badly over, write "
         "in and we will move it to a booster who is free."),
    ],
)

LEGAL_UPDATED = "10 August 2026"


# ── the free guides landing (lead capture) ────────────────────────────────
# design_handoff_free_guides. The only page whose success metric is a list, not
# an order: two free PDFs (a League field guide and a Valorant field guide) in
# exchange for an email. Both guides are ticked by default — the second costs
# nothing to give and the card selection is a game-preference signal to store
# with the address.
#
# ⚠ PLACEHOLDER like everything else invented in this file (see top). Blocking
# for launch, specifically:
#   · the download counts, the reader rating and the three reader quotes are
#     invented; keep the delivered-boosts figure and the Trustpilot average in
#     step with STATS above, they are the same claims;
#   · every author's rank and role is invented. The names obey the site's
#     roster rule — a booster plays exactly ONE game — so the League authors are
#     League handles and the Valorant authors are Valorant handles, and none is
#     listed under two games. In production this list reads from the one roster
#     source that also feeds BOOSTERS and the profile pages;
#   · the SIX League chapter titles describe a guide that does not exist yet.
#     The Valorant guide is real (six chapters, six drills). The hero says "12
#     chapters + 12 drills" — that is 6+6 twice; do not let the count drift from
#     the artifact.
GUIDES = dict(
    # Hero stat row + reader band. Figures ride in their own nodes in build.py.
    stats=dict(downloads="14,200", chapters=12, drills=12, rating="4.8", readers="1,100"),
    # Spine colours are each guide's identity, reused on the chapter badges,
    # author tags and review tags. `key` keys the toc below and the client state.
    items=[
        dict(key="lol", game="League of Legends", short="League", initial="L",
             title="The League field guide", cover_title="Win the lane you already won.",
             note="Iron to Diamond · wave control, roams, objectives", accent="#5f93de"),
        dict(key="val", game="Valorant", short="Valorant", initial="V",
             title="The Valorant field guide", cover_title="Stop losing rounds you already won.",
             note="Iron to Ascendant · crosshair, economy, retakes", accent="#c8577a"),
    ],
    # Six chapters each, every one ending in a drill. ⚠ the League six are titles
    # for an unwritten guide.
    toc=dict(
        lol=[
            ("01", "Wave control", "Freeze, slow-push, crash — and which one the minute demands."),
            ("02", "Trading, not fighting", "Why the lane is won by who spends time better, not who hits harder."),
            ("03", "Roams that pay", "The three windows where leaving lane gains more than it costs."),
            ("04", "Objectives as maths", "Dragon, herald and the setup that starts 40 seconds early."),
            ("05", "Six habits that cap your rank", "Each with the tell you can spot in your own replays."),
            ("06", "The climb plan", "Twelve ranked games a week, structured."),
        ],
        val=[
            ("01", "Crosshair placement", "Where the dot sits before you peek, not after."),
            ("02", "Economy you can trust", "When to force, when to save, and why the half-buy loses."),
            ("03", "Retakes and the four-second rule", "Most retakes are lost before anyone shoots."),
            ("04", "Utility that buys space", "Smokes and flashes as currency."),
            ("05", "Six habits that cap your rank", "Each with the tell you can spot in your own VODs."),
            ("06", "The climb plan", "Twelve ranked games a week, structured."),
        ],
    ),
    # Seven authors across two games. `game` is "League" or "Valorant" — it tints
    # the tag and must not put one handle under both.
    authors=[
        dict(name="vantaa", initial="V", meta="Challenger 1042 LP · Mid", game="League"),
        dict(name="kirona", initial="K", meta="Grandmaster 604 LP · Jungle", game="League"),
        dict(name="draeg", initial="D", meta="Master 388 LP · Top", game="League"),
        dict(name="calla", initial="C", meta="Radiant 412 RR · Duelist", game="Valorant"),
        dict(name="nyx", initial="N", meta="Immortal 3 · Controller", game="Valorant"),
        dict(name="perko", initial="P", meta="Immortal 2 · Sentinel", game="Valorant"),
        dict(name="tovi", initial="T", meta="Radiant 388 RR · Initiator", game="Valorant"),
    ],
    # ⚠ Invented reader testimonials. `game` tints the tag so both audiences see
    # themselves.
    quotes=[
        dict(name="Marek K.", initials="MK", rank="Gold 2 → Platinum 3", game="Valorant",
             body="The economy chapter alone was worth it. I was force-buying every second round and "
                  "losing the round after. Stopped doing that and climbed a full rank in three weeks."),
        dict(name="Dee R.", initials="DR", rank="Silver II → Gold IV", game="League",
             body="The wave control chapter rewired how I think about lane. I had been shoving every "
                  "wave without knowing why, and the freeze section explained what that was costing me."),
        dict(name="Tomas V.", initials="TV", rank="Platinum 1 → Diamond 2", game="Valorant",
             body="The six habits chapter called me out on three of them. Uncomfortable read, which is "
                  "probably the point."),
    ],
    # Five, single-open. Q1 answers motive (the objection on a page asking for
    # data is "why is this free", not price); Q2 answers the take-both question
    # the two-guide format creates. ids are stable deep-link anchors.
    faq=[
        ("free", "Is it actually free, or free-ish?",
         "Free. There is no card, no trial, and no upsell inside either PDF. We publish them "
         "because a player who improves is a player who stays in the game, and some of them buy a "
         "boost or a coaching hour later. That is the whole business case."),
        ("both", "Can I take both?",
         "Yes, and most people do — both are ticked by default. They arrive as two attachments in "
         "one email, so taking the second one costs you nothing extra, not even another form."),
        ("email", "What do you do with my email?",
         "Send you the guides. If you tick the box, one email a month with new guides and patch "
         "notes. We never sell or rent the list, and one click unsubscribes — the link is in every "
         "email, not buried in a preference centre."),
        ("rank", "What rank are these written for?",
         "Iron through Diamond for League, Iron through Ascendant for Valorant. The early chapters "
         "do most of the work at lower ranks; the habit and objective chapters matter more once you "
         "are past Platinum."),
        ("need-boost", "Do I need to buy boosting to use them?",
         "No, and neither guide mentions our services beyond one line on the last page. If you would "
         "rather someone else did the climbing, that is a different page on this site — this one is "
         "for doing it yourself."),
    ],
)
