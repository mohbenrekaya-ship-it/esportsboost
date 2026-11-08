# -*- coding: utf-8 -*-
"""The films: what is said, in what world it is shown, and which prices it quotes.

⚠ EACH FILM IS A DIFFERENT VISUAL FORMAT — a PLACE (a lock screen, a scoreboard,
the product's own screen, a calendar, a deck of cards, a placement tracker, a
party lobby, a win counter) — and the film MOVES between places. The first batch
was five variations of "big type centred on black" and was rejected on that.

⚠ THERE ARE TWO BATCHES AND THEY OPEN DIFFERENTLY, ON PURPOSE.

Films 1–8 are the LEAGUE batch and open "Do you play League of Legends?" —
nothing else. Films 9–13 are the CATALOGUE batch, and the business reversed that
on 2026-11-08: they open "Do you play League of Legends, Valorant, or any other
ranked game?", because they sell the shop rather than one ladder. Do not
"harmonise" the two — the opening is what tells them apart, and a League-only
film is still the right ad to run against a League keyword.

⚠ THE CATALOGUE BATCH IS ONE ARGUMENT IN FIVE REGISTERS, and the spine is the
business's own: the hook, then STUCK IN YOUR RANK, then TEAMMATES WHO WASTE YOUR
TIME AND ENERGY, then eSports Boost with TWO WAYS OUT — we duo queue beside you,
or we take the account to the rank you want while you sleep or watch a series —
and then THE SCREEN SHARE, which closes every one of the five. Every film states
that arc; what changes is the place it is staged in and which of the two ways
leads.

⚠ EVERY ONE OF THE FIVE ENDS ON THE SAME SPOKEN CTA — "Click the link below and
get your desired rank today." — the business's call (2026-11-08) on the grounds
that it out-clicks a brand sign-off. It is the LAST line, after the brand line,
so the film still says who it is before it says what to do; and the end card is
built to it rather than to the logo (the button lands on `Ls[8]`, not on the
close), because a CTA that is already on screen when the voice reaches it is not
a call to action, it is furniture.

⚠ NOT ONE OF THESE FIVE QUOTES A PRICE (the business's call, 2026-11-08), where
every film in the League batch does. So `prices` is empty on all five and the
guard that matters is `check_prices()`'s SECOND half: a take that says any
"<word> dollars" the script did not declare fails the build, because nothing
would be checking that figure against the engine.

⚠ THE CLOSE SELLS SOMETHING THAT IS NOT BUILT. `streams.py` does not exist:
nothing opens a Discord channel and nothing tells a booster to share a screen.
The `stream` add-on already rides into fulfilment as `metadata[addons]`, so this
is a manual ops promise today, and five ads make it the headline rather than a
row in a picker. See "Watch live" in CLAUDE.md — build the seam or the claim is
somebody opening a channel by hand on every order that mentions it.

⚠ AND IT IS WRITTEN AS A FACT ABOUT US, NEVER A COMPARISON. "Nobody else gives
you this" is a claim about every competitor at once, falsifiable by any one of
them, and it is the claim `D.STREAM_CLAIM_VERIFIED = False` exists to hold back.

⚠ NO TWO FILMS QUOTE THE SAME CLIMB OR THE SAME PRICE. Five films all ending on
"Silver to Gold, twenty-five dollars" is one ad shown five times, and it tells a
Platinum player the shop is not for him. The ladder runs Iron to Master and the
engine prices every rung of it.

⚠ NUMBERS ARE SPELLED OUT FOR THE VOICE and written as digits on screen. The
take is read as written, so "$36" would be read "dollar thirty-six".

`prices` is what the film SAYS, against what the site CHARGES: build_film.py
resolves each one through pricing.py and fails the build when they disagree. The
voice cannot be patched — a re-price means rewriting the line and re-recording.
"""

FILMS = {
    # ── 1. A phone at 2 a.m., notifications stacking up ────────────────────
    'notifications': dict(
        n=1, title='Notifications', mood='electro',
        prices=[],                       # no price spoken: this one sells the feeling
        lines=[
            "Do you play League of Legends?",
            "Then you know this screen.",
            "Minus eighteen LP. Minus twenty-two. Demoted.",
            "Four hundred games a season, and the same rank every time.",
            "This is the only notification worth waiting for.",
            "Gold four reached. Played by a verified booster, in about a day.",
            "Pick your rank at eSports Boost. Money back until a booster takes it.",
        ]),

    # ── 2. A versus scoreboard ─────────────────────────────────────────────
    'scoreboard': dict(
        n=2, title='You vs the grind', mood='electro',
        prices=[('thirty-six dollars', ('division', 'Gold IV', 'Platinum IV'))],
        lines=[
            "Do you play League of Legends?",
            "Here's the match nobody shows you.",
            "You, against the grind.",
            "Three hundred hours. Forty-nine percent win rate. Same division since March.",
            "The grind wins that one. Every season.",
            "So put a Master player on your side of the board.",
            "Gold to Platinum: thirty-six dollars, about a day.",
            "eSports Boost. Pick your rank, we climb it.",
        ]),

    # ── 3. The product's own screen ────────────────────────────────────────
    'order-screen': dict(
        n=3, title='How it actually works', mood='pop',
        prices=[('fifty-seven dollars', ('division', 'Platinum IV', 'Emerald IV'))],
        lines=[
            "Do you play League of Legends?",
            "Stuck, and wondering how this actually works?",
            "You pick where you are, and where you want to be.",
            "The price is there before you pay. Platinum to Emerald, fifty-seven dollars.",
            "A booster takes it, and you watch the whole climb from your phone.",
            "Live rank, every game, as it happens. Pause it whenever you like.",
            "Three taps at eSports Boost.",
        ]),

    # ── 4. One month of a calendar ─────────────────────────────────────────
    'one-month': dict(
        n=4, title='One month', mood='calm',
        prices=[('ninety-one dollars', ('division', 'Emerald IV', 'Diamond IV'))],
        lines=[
            "Do you play League of Legends?",
            "This is your last month.",
            "Twenty-eight nights. Four hundred games.",
            "And you finished exactly where you started.",
            "This is the same climb, done for you.",
            "Emerald to Diamond. One day. Ninety-one dollars.",
            "Your nights back, and the rank you were playing for.",
            "eSports Boost.",
        ]),

    # ── 5. Three cards: the fears, turned over ─────────────────────────────
    'myths': dict(
        n=5, title='True or false', mood='playful',
        prices=[('four dollars', ('division', 'FLOOR', None))],
        lines=[
            "Do you play League of Legends?",
            "Three things people believe about boosting. Two of them are wrong.",
            "One. Someone keeps your account. False.",
            "You can pause it whenever you like, and your name never shows.",
            "Two. It costs a fortune. False.",
            "One division starts at four dollars.",
            "Three. It's against the rules. True, and we won't tell you otherwise.",
            "That's why it's played on a VPN in your region, in your normal hours.",
            "eSports Boost. Money back until a booster takes it.",
        ]),

    # ── 6. Ten placement games ─────────────────────────────────────────────
    'placements': dict(
        n=6, title='Placements', mood='electro',
        prices=[('sixteen dollars', ('placements', 'Gold IV', 5))],
        lines=[
            "Do you play League of Legends?",
            "New season. Your placements decide where you sit for months.",
            "Lose four of them, and you spend until March climbing back.",
            "Win them, and the season opens above where you ended.",
            "Five placement games, played by a Master player.",
            "Sixteen dollars. Usually done in a day.",
            "eSports Boost. Start the season where you meant to.",
        ]),

    # ── 7. The party screen ────────────────────────────────────────────────
    'duo': dict(
        n=7, title='Duo', mood='pop',
        prices=[('fifty-six dollars', ('division', 'Gold IV', 'Platinum IV', 'Duo queue'))],
        lines=[
            "Do you play League of Legends?",
            "Your friends queue two divisions above you.",
            "And you're the one who gets dodged.",
            "Duo queue: the booster plays beside you, not instead of you.",
            "Same account, same games, your hands on the keyboard.",
            "Gold to Platinum, together: fifty-six dollars.",
            "eSports Boost. Climb with them, not behind them.",
        ]),

    # ══ THE CATALOGUE BATCH ═══════════════════════════════════════════════
    # Hook names the shop, not one ladder. Two ways out: duo, or while you sleep.

    # ── 9. A post-game scoreboard of four strangers ────────────────────────
    'teammates': dict(
        n=9, title='Four strangers', mood='electro',
        prices=[],
        lines=[
            "Do you play League of Legends, Valorant, or any other ranked game?",
            "Then you already know the problem isn't you.",
            "Four strangers every match. One of them decides it in the first ten minutes.",
            "Three hundred hours, and the same rank you started the season on.",
            "At eSports Boost you stop queueing with strangers.",
            "A Master player duos with you. Your account, your hands, your games.",
            "And you watch every game of it live, from your phone.",
            "eSports Boost. Stop carrying people who never carry you.",
            "Click the link below and get your desired rank today.",
        ]),

    # ── 10. A bedside clock through the night ──────────────────────────────
    'asleep': dict(
        n=10, title='While you sleep', mood='calm',
        prices=[],
        lines=[
            "Do you play League of Legends, Valorant, or any other ranked game?",
            "And you're still sitting in the rank you were stuck in last season.",
            "Four games a night, three of them lost by somebody who went afk.",
            "At eSports Boost you can sleep through the climb instead.",
            "A verified booster plays your account on a VPN in your own region.",
            "And if you wake up at two in the morning, you can watch them play, live, on your phone.",
            "You wake up at the rank you were playing to reach.",
            "eSports Boost.",
            "Click the link below and get your desired rank today.",
        ]),

    # ── 11. A streaming app, episodes against divisions ────────────────────
    'series': dict(
        n=11, title='Watch something else', mood='pop',
        prices=[],
        lines=[
            "Do you play League of Legends, Valorant, or any other ranked game?",
            "Stuck at the same rank, losing your evenings to teammates you'll never see again.",
            "So here's the trade.",
            "You watch the season of something you actually wanted to watch.",
            "A verified booster climbs your account while you do.",
            "And on the other screen, whenever you want it: their game, live on your phone.",
            "Your evenings back, and the rank you were grinding for.",
            "eSports Boost.",
            "Click the link below and get your desired rank today.",
        ]),

    # ── 12. An hours ledger ────────────────────────────────────────────────
    'hours': dict(
        n=12, title='What it cost you', mood='electro',
        prices=[],
        lines=[
            "Do you play League of Legends, Valorant, or any other ranked game?",
            "Add up what this season actually cost you.",
            "Three hundred hours. Four hundred games. Zero divisions.",
            "Most of them decided by a stranger who stopped playing at minute four.",
            "At eSports Boost there are two ways out of that.",
            "We duo beside you, or we climb it while you sleep.",
            "And either way, you watch it happen live, from your phone.",
            "eSports Boost. Your evenings back, and the rank with them.",
            "Click the link below and get your desired rank today.",
        ]),

    # ── 13. Two lanes: duo or solo ─────────────────────────────────────────
    'two-ways': dict(
        n=13, title='Two ways out', mood='pop',
        prices=[],
        lines=[
            "Do you play League of Legends, Valorant, or any other ranked game?",
            "And you're stuck, because ranked is four strangers and a coin flip.",
            "eSports Boost gives you two ways out of it.",
            "Duo queue: a Master player on your team every game, your hands on the keyboard.",
            "Or solo: you close the laptop, and the climb happens while you sleep.",
            "And the part that changes it: watch your booster play, live, from your phone.",
            "Same account, money back until a booster takes it.",
            "eSports Boost. Pick your rank, we climb it.",
            "Click the link below and get your desired rank today.",
        ]),

    # ── 8. A win counter ───────────────────────────────────────────────────
    'five-wins': dict(
        n=8, title='Five wins', mood='electro',
        prices=[('three dollars', ('wins', 'Gold IV', 1))],
        lines=[
            "Do you play League of Legends?",
            "You don't need a new rank. You need to stop losing the same five games.",
            "Eighty LP. Promo series. Lose two, back to square one.",
            "Net wins: a booster plays until you're five wins up, and stops.",
            "Not a rank. Just the wins you keep dropping.",
            "Three dollars a win. Yours by tomorrow.",
            "eSports Boost.",
        ]),
}
