# -*- coding: utf-8 -*-
"""Cues for "Duo". Three taps as the party fills, one hard hit on the dodge, and
a rising pair as the booster joins — the only two warm sounds in the film."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.28),
        ('tap', W('friends') - 0.1, 0.4),
        ('tap', W('queue') - 0.05, 0.4),
        ('tap', W('above') - 0.1, 0.45),
        ('boom', W('dodged') - 0.15, 0.55),            # the row greys out
        ('tap', W('duo') - 0.2, 0.45),
        ('pop', W('booster') - 0.12, 0.55),            # the booster joins
        ('sparkle', W('beside') - 0.1, 0.5),           # the link draws
        ('check', W('account') - 0.12, 0.45),
        ('check', W('games', 12.0) - 0.12, 0.45),
        ('check', W('hands') - 0.12, 0.45),
        ('ding', W('fiftysix') - 0.12, 0.6),
        ('pop', L[6] + 0.3, 0.6),
    ]
