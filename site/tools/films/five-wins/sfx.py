# -*- coding: utf-8 -*-
"""Cues for "Five wins". The two promo losses are the only heavy hits; the five
wins are lighter taps, so the recovery reads as counting rather than as a fight."""


def cues(W, L, lines, total):
    tw = W('five', 13.0) - 0.08
    return [
        ('riser', 0.0, 0.28),
        ('boom', W('rank') + 0.18, 0.4),               # the struck line
        ('pop', W('stop') - 0.18, 0.5),
        ('tap', W('eighty') + 0.05, 0.42),
        ('check', W('series') + 0.18, 0.5),            # game 1 won
        ('boom', W('lose') - 0.05, 0.5),               # game 2 lost
        ('boom', W('two', 9.1) + 0.12, 0.5),           # game 3 lost
        ('boom', W('square') - 0.2, 0.5),              # the bar empties
        *[('tap', tw + 1.4 * i / 5, 0.4) for i in range(5)],
        ('ding', W('stops') + 0.02, 0.6),
        ('sparkle', W('just') - 0.12, 0.45),
        ('ding', W('three') - 0.05, 0.6),
        ('pop', L[6] + 0.3, 0.6),
    ]
