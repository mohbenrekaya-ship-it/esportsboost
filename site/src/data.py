# -*- coding: utf-8 -*-
"""Single source of truth for the site.

Everything the pages render comes from here; the build also serialises the
subset the browser needs into assets/js/data.js, so client and server can
never drift apart.

⚠ CONTENT WARNING (carried over from the design handoff, do not ship as-is):
the game list beyond League of Legends, every statistic, the booster handles
and the reviews are PLACEHOLDERS. Wire STATS to Trustpilot / the orders table
/ the Discord widget and BOOSTERS to the real roster before launch.
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
        name="League of Legends", slug="league-of-legends", short="LoL", factor=1.0, hue=262,
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald",
                          "Diamond", "Master"],
                         ["IV", "III", "II", "I"],
                         apex=("Master",)),
        prices={"Iron": 6, "Bronze": 8, "Silver": 9, "Gold": 12, "Platinum": 19,
                "Emerald": 30, "Diamond": 48, "Master": 60},
        services="Elo boost · placements · net wins · duo · coaching",
        regions=["EUW", "EUNE", "NA", "OCE", "BR", "LAN", "TR", "KR"],
        blurb="Solo/duo and flex, EUW to KR. Your booster plays your account inside your "
              "normal hours with a regional VPN, or queues beside you in duo and never "
              "touches the login at all.",
        meta="LoL elo boost from Iron to Master. Live price before you sign in, "
             "verified boosters, pro-rated refunds. Solo or duo, every region.",
        note="Every division from Iron IV to Diamond I is on the ladder; Master is "
             "LP-based and priced as a single step above Diamond I.",
    ),
    dict(
        name="Valorant", slug="valorant", short="VAL", factor=1.15, hue=352,
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Diamond",
                          "Ascendant", "Immortal"],
                         ["1", "2", "3"], apex=("Immortal",)),
        prices={"Iron": 4, "Bronze": 4, "Silver": 5, "Gold": 7, "Platinum": 9,
                "Diamond": 18, "Ascendant": 35, "Immortal": 100},
        services="Rank boost · placements · unrated wins · duo · coaching",
        regions=["EU", "NA", "AP", "KR", "BR", "LATAM"],
        blurb="Radiant-level boosters with your own crosshair and sensitivity loaded in. "
              "Agent pool on request, and duo runs with voice if you want the coaching "
              "on the way up.",
        meta="Valorant rank boost, Iron to Immortal. Transparent live pricing, duo or "
             "solo, agent pool on request.",
        note="Act rank and episode resets shift the price; the quote is locked at "
             "checkout either way.",
    ),
    dict(
        name="Counter-Strike 2", slug="counter-strike-2", short="CS2", factor=1.45, hue=32,
        ladder=["5k", "10k", "13k", "15k", "17k", "19k", "21k", "25k", "30k"],
        services="Premier rating · Faceit levels · Wingman · wins",
        regions=["EU", "NA", "SA", "Asia", "Oceania"],
        blurb="Premier CS Rating and Faceit levels, run by FPL-adjacent players. Anti-cheat "
              "safe patterns, no smurf stacking, no rating farm scripts.",
        meta="CS2 Premier rating and Faceit level boosting. Live price, verified players, "
             "refunds pro-rated to the rating actually gained.",
        note="Ratings are shown in thousands of CS Rating points.",
    ),
    dict(
        name="Teamfight Tactics", slug="teamfight-tactics", short="TFT", factor=0.8, hue=198,
        ladder=subdivide(["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald",
                          "Diamond", "Master", "Challenger"],
                         ["IV", "III", "II", "I"], apex=("Master", "Challenger")),
        services="Rank boost · placements · double-up",
        regions=["EUW", "EUNE", "NA", "OCE", "BR", "KR"],
        blurb="Set-current comp knowledge, not last patch's. Double-up runs are played with "
              "you, so the climb doubles as a lesson in tempo and econ.",
        meta="TFT rank boosting and double-up. Current-set comps, live pricing, no bots.",
        note="Ranked and Double Up share the ladder; Hyper Roll is quoted on request.",
    ),
    dict(
        name="Marvel Rivals", slug="marvel-rivals", short="RIV", factor=0.95, hue=8,
        ladder=subdivide(["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Grandmaster",
                          "Celestial", "Eternity", "One Above All"],
                         ["III", "II", "I"], apex=("Eternity", "One Above All")),
        services="Rank boost · net wins · duo · coaching",
        regions=["EU", "NA", "Asia", "SA"],
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
        regions=["EU West", "EU East", "US East", "US West", "SEA", "China", "SA"],
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
        regions=["EU", "NA", "Asia", "SA", "Oceania"],
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
        regions=["EU", "NA", "Asia", "SA"],
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
        regions=["EU", "NA East", "NA West", "SAM", "Oceania", "Asia"],
        blurb="1v1, 2v2 and 3v3 playlists, tournament wins, and duo sessions where the "
              "booster calls rotations live on voice.",
        meta="Rocket League rank boosting and tournament wins, Bronze to Supersonic Legend.",
        note="Each playlist has its own rank; the quote covers one playlist per order.",
    ),
]

# Site-wide display order (games index, footer, dropdowns, client data). Change
# this one list to re-rank the games everywhere. The homepage mosaic has its own
# hand-tuned layout — see TILE_ORDER.
_ORDER = ["league-of-legends", "valorant", "marvel-rivals", "teamfight-tactics",
          "overwatch-2", "rocket-league", "dota-2", "apex-legends", "counter-strike-2"]
GAMES.sort(key=lambda g: _ORDER.index(g["slug"]))

for _g in GAMES:
    _attach_structure(_g)

ADDONS = [
    dict(id="priority", label="Priority queue", pct=0.15,
         note="Pushed to the top of the board. Median claim drops to about 6 minutes."),
    dict(id="champ", label="Specific champions, agents or heroes", pct=0.10,
         note="Your booster plays a pool you choose, so the match history stays plausible."),
    dict(id="stream", label="Streamed to you", pct=0.12,
         note="A private stream link for every game, replayable for 14 days."),
    dict(id="offline", label="Offline appearance", pct=0.0,
         note="Always on. Friends see you offline for the whole order — never an extra."),
]

# ── placeholder statistics ────────────────────────────────────────────────
STATS = dict(
    trustpilot="4.8 / 5", reviews="3,140", boosts="92,400",
    discord="3,000", median_claim="18 min",
    online=34, free_now=25, reply="3m 40s",
)

BOOSTERS = [
    dict(handle="vantaa", game="LoL · EUW", peak="Challenger 1042 LP", wr="78%", queue="1 order",
         peak_full="Challenger 1042 LP · EUW", hue=20, orders=214),
    dict(handle="kx_reid", game="Valorant · NA", peak="Radiant #211", wr="74%", queue="free",
         peak_full="Radiant #211 · NA", hue=352, orders=168),
    dict(handle="sable", game="CS2 · EU", peak="FPL, 27k Premier", wr="71%", queue="2 orders",
         peak_full="FPL · 27k Premier · EU", hue=32, orders=141),
    dict(handle="orvo", game="LoL · NA", peak="Grandmaster 640 LP", wr="69%", queue="free",
         peak_full="Grandmaster 640 LP · NA", hue=210, orders=97),
    dict(handle="nine", game="Dota 2 · SEA", peak="Immortal 8.4k", wr="73%", queue="1 order",
         peak_full="Immortal 8.4k · SEA", hue=16, orders=203),
    dict(handle="petrichor", game="Valorant · EU", peak="Radiant 610 RR", wr="72%", queue="free",
         peak_full="Radiant 610 RR · EU", hue=280, orders=88),
    dict(handle="mera", game="TFT · EUW", peak="Challenger 980 LP", wr="Top-4 61%", queue="free",
         peak_full="Challenger 980 LP · EUW", hue=196, orders=76),
    dict(handle="cobalt_ix", game="OW2 · NA", peak="Champion, 4520 SR", wr="70%", queue="1 order",
         peak_full="Champion 4520 SR · NA", hue=212, orders=132),
    dict(handle="halden", game="Rocket League · EU", peak="SSL 1885 MMR", wr="76%", queue="free",
         peak_full="SSL 1885 MMR · EU", hue=224, orders=119),
    dict(handle="tsuro", game="Apex · EU", peak="Predator #740", wr="68%", queue="2 orders",
         peak_full="Predator #740 · EU", hue=6, orders=64),
]

# ── v2 "Ashfall" page content ─────────────────────────────────────────────
HERO = dict(
    kicker="Verified boosters — since 2019",
    line1="The rank is yours.",
    line2="The grind isn't.",
    lede="Set two ranks. See the final price before you make an account. Then watch every match "
         "land from the dashboard — no bots, no shared logins, no invoice that moves after checkout.",
    portrait_name="This month's #1 — vantaa",
    portrait_meta="Challenger 1042 LP · 78% WR · EUW · 214 orders",
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
# The left cell of the utility bar on every page. Derived from the auto promo
# above so the bar can never advertise a discount the checkout doesn't honour.
# Set PROMO_TEXT="" to hide the slot; `href` (optional) makes the line a link.
PROMO_TEXT = "Summer sale — %s off with code %s"
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
PROMO = dict(
    tag=("-" + promo_pct_label(_AUTO)) if _AUTO else "",
    text=(PROMO_TEXT % (promo_pct_label(_AUTO), _AUTO_CODE)) if _AUTO else "",
    href=PROMO_HREF,
)

MARQUEE = [
    "92,400 boosts delivered",
    "4.8 / 5 on Trustpilot — 3,140 reviews",
    "Most orders claimed within 18 min",
    "3,000 players in the Discord",
    "100% recovery rate on account reviews",
]

LIVE_FEED = [
    dict(climb="Platinum II → Diamond IV", game="League of Legends · EUW",
         slug="league-of-legends", time="2M ago", booster="vantaa"),
    dict(climb="Silver 3 → Ascendant 1", game="Valorant · NA",
         slug="valorant", time="14M ago", booster="kx_reid"),
    dict(climb="13,400 → 19,100 Premier", game="Counter-Strike 2 · EU",
         slug="counter-strike-2", time="38M ago", booster="sable"),
    dict(climb="Grandmaster → Celestial", game="Marvel Rivals · NA",
         slug="marvel-rivals", time="1H ago", booster="orvo"),
]

# ⚠ Marketing claims about your own operations — legal review before shipping.
SAFETY = dict(
    title="Why this doesn't get you banned",
    body=[
        "Anti-cheat looks for software, not skill. Every solo order runs behind an enterprise "
        "VPN matched to your region, the booster mirrors your sensitivity and crosshair, and "
        "sessions are scheduled inside the hours you normally play — so the activity pattern on "
        "the account never changes. Duo orders never touch your login at all.",
        "Across 92,400 completed orders the recovery rate on account reviews is 100%. If a boost "
        "triggers one, support files the appeal and the order is refunded in full while it runs. "
        "Your name, email and payment details are never shared with the booster.",
    ],
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
    ("rocket-league", ""),
]

# ⚠ Placeholder reviews — invented, not real customer testimony (see top of file).
# At least six per game so every game page fills its reviews grid. The League of
# Legends block stays first so the homepage feed reads LoL, as designed.
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
    dict(rank="Diamond 2 → Ascendant 1", game="Valorant · EU",
         text="Ran past the ETA by a day and they refunded the difference before I even opened "
              "a ticket about it."),
    dict(rank="Ascendant 3 → Immortal 1", game="Valorant · KR",
         text="Third order with the same booster now. He knows my setup and it just gets done "
              "on the nights I book."),
    # ── Counter-Strike 2 ───────────────────────────────────────────────────
    dict(rank="13k → 19k Premier", game="CS2 · EU",
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
    dict(rank="Faceit 6 → Faceit 9", game="CS2 · EU",
         text="Refund was pro-rated to the levels I actually gained when one match went sideways. "
              "Fair about it, no argument."),
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
    dict(rank="Grandmaster III → Celestial", game="Marvel Rivals · NA",
         text="Celestial push was hand-matched to someone who mains my roles. Felt like the "
              "account was in the right hands the whole time."),
    # ── Dota 2 ─────────────────────────────────────────────────────────────
    dict(rank="Archon 3 → Legend 2", game="Dota 2 · SEA",
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

GUARANTEES = [
    ("Guarantee", "Finished or refunded",
     "If a boost stalls past its ETA you get the unfinished portion back, pro-rated, "
     "without opening a ticket war."),
    ("Privacy", "Nobody sees your name",
     "Regional VPN, your own sensitivity and crosshair, offline appearance, and sessions "
     "inside your normal play hours."),
    ("Support", "Answered in minutes, not days",
     "Discord and email, 24/7, staffed by people who play the game. Median first reply "
     "last month: 3m 40s."),
]

DASHBOARD_POINTS = [
    ("Match-by-match history",
     "Every game your booster plays, with the LP swing, KDA and replay link."),
    ("Pause on one click",
     "Want to play tonight? Pause, and the account is free within minutes."),
    ("Chat with the booster, not a queue",
     "Ask for a champion pool, a schedule, or a swap. Support reads the same thread."),
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

LEGAL_UPDATED = "10 August 2026"
