# -*- coding: utf-8 -*-
"""The five League of Legends films: what is said, and in what world it is shown.

⚠ EACH FILM IS A DIFFERENT VISUAL FORMAT, not the same layout with other words.
The first five ads built here were five variations of "big type, centred, black
ground" and the owner rejected them on exactly that. A format here is a PLACE —
a phone lock screen, a scoreboard, the product's own screen, a calendar, a deck
of cards — and the film MOVES between places (the Enevie brief's rule 2: one
scene held from start to finish is refused).

⚠ NUMBERS ARE SPELLED OUT FOR THE VOICE and written as digits on screen. The
take is read as written, so "$25" would be read "dollar twenty-five".

⚠ What may be claimed is in marketing/video-scripts-lol-en.md. No review score,
no review count, no client count, no roster size — all invented placeholders.
Prices come from pricing.py through build_film.py and are checked against the
spoken line at build time, so a re-price fails the build instead of shipping a
film that quotes a figure the checkout does not charge.
"""

FILMS = {
    # ── 1. A phone at 2 a.m., notifications stacking up ────────────────────
    'notifications': dict(
        n=1, title='Notifications', mood='electro',
        # The place: a lock screen. It moves lock screen -> ladder -> order -> end.
        lines=[
            "Do you play League of Legends, or something similar?",
            "Then you know this screen.",
            "Minus eighteen LP. Minus twenty-two. Demoted.",
            "Four hundred games a season, and the same rank every time.",
            "This is the only notification worth waiting for.",
            "Gold four reached. Done by a verified booster, in about a day.",
            "Pick your rank at eSports Boost. Money back until a booster takes it.",
        ]),

    # ── 2. A versus scoreboard ─────────────────────────────────────────────
    'scoreboard': dict(
        n=2, title='You vs the grind', mood='electro',
        lines=[
            "Do you play League of Legends, or something similar?",
            "Here's the match nobody shows you.",
            "You, against the grind.",
            "Three hundred hours. Forty-nine percent win rate. Same division since March.",
            "The grind wins that one. Every season.",
            "So put a Master player on your side of the board.",
            "Silver to Gold, twenty-five dollars, about a day.",
            "eSports Boost. Pick your rank, we climb it.",
        ]),

    # ── 3. The product's own screen ────────────────────────────────────────
    'order-screen': dict(
        n=3, title='How it actually works', mood='pop',
        lines=[
            "Do you play League of Legends, or something similar?",
            "Stuck, and wondering how this actually works?",
            "You pick where you are, and where you want to be.",
            "The price is there before you pay. Silver to Gold, twenty-five dollars.",
            "A booster takes it, and you watch the whole climb from your phone.",
            "Live rank, every game, as it happens. Pause it whenever you like.",
            "Three taps at eSports Boost.",
        ]),

    # ── 4. One month of a calendar ─────────────────────────────────────────
    'one-month': dict(
        n=4, title='One month', mood='calm',
        lines=[
            "Do you play League of Legends, or something similar?",
            "This is your last month.",
            "Twenty-eight nights. Four hundred games.",
            "And you finished exactly where you started.",
            "This is the same climb, done for you.",
            "One day. Twenty-five dollars. Silver to Gold.",
            "Your nights back, and the rank you were playing for.",
            "eSports Boost.",
        ]),

    # ── 5. Three cards: the fears, turned over ─────────────────────────────
    'myths': dict(
        n=5, title='True or false', mood='playful',
        lines=[
            "Do you play League of Legends, or something similar?",
            "Three things people believe about boosting. Two of them are wrong.",
            "One. Someone keeps your account. False.",
            "You can pause it whenever you like, and your name never shows.",
            "Two. It costs a fortune. False.",
            "One division starts at four dollars. A whole rank, twenty-five.",
            "Three. It's against the rules. True, and we won't tell you otherwise.",
            "That's why it's played on a VPN in your region, in your normal hours.",
            "eSports Boost. Money back until a booster takes it.",
        ]),
}

# Figures the spoken lines contain, checked against pricing.py at build time.
# Spelling, because the voice reads words: a re-price breaks the build here
# rather than shipping a film that says a price the checkout does not charge.
SPOKEN_PRICES = {
    'twenty-five dollars': ('Silver IV', 'Gold IV'),
    'four dollars': None,          # the catalogue floor, checked separately
}
