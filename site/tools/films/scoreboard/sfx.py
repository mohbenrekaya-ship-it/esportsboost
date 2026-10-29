# -*- coding: utf-8 -*-
"""Cues for "You vs the grind". No transition noise (the client's rule 3):
small sounds only on what appears, hung on the word being spoken."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.28),
        ('pop', W('you', 5.5) - 0.1, 0.6),       # your side lands
        ('pop', W('grind') - 0.1, 0.6),          # and the grind's
        ('tap', W('three') - 0.12, 0.5),         # 300 hours
        ('tap', W('fortynine') - 0.12, 0.5),     # 49%
        ('tap', W('same') - 0.12, 0.5),          # last rank up
        ('boom', W('wins') - 0.14, 0.45),        # the score, softly
        ('ding', W('master') - 0.12, 0.6),       # a Master joins your side
        ('check', W('twentyfive') - 0.1, 0.65),  # the price
        ('pop', L[7] + 0.3, 0.6),                # the button
    ]
