# -*- coding: utf-8 -*-
"""Cues for "While you sleep". The night half is quiet on purpose — one tap per
game, a hit on the afk — and the only bright sounds are the two the morning gets."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.26),
        ('tap', W('rank') - 0.2, 0.42),
        ('pop', W('four') - 0.2, 0.45),
        ('check', W('four') + 0.6, 0.4),
        *[('tap', W('three') + d + 0.1, 0.45) for d in (0, 0.5, 1.0)],
        ('boom', W('afk') - 0.15, 0.5),
        ('sparkle', W('sleep') - 0.1, 0.6),
        ('check', W('vpn') - 0.25, 0.45),
        ('pop', W('two', 20.8) + 0.05, 0.5),
        ('sparkle', W('live', 23.0) - 0.15, 0.55),
        ('ding', W('rank', 25.2) - 0.05, 0.6),
        ('pop', L[7] + 0.3, 0.6),          # the lockup lands
        ('ding', L[8] - 0.3, 0.55),        # and the button, on the spoken CTA
    ]
