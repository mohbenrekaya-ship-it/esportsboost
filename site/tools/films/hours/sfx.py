# -*- coding: utf-8 -*-
"""Cues for "What it cost you". Three taps as the ledger is totted up, one hit on
the zero, and the two ways land as a pair rather than a fanfare."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.26),
        ('tap', W('three') - 0.2, 0.45),
        ('tap', W('four') - 0.2, 0.45),
        ('boom', W('zero') - 0.2, 0.5),
        ('boom', W('stranger') - 0.25, 0.5),
        ('pop', W('duo') - 0.3, 0.5),
        ('pop', W('climb') - 0.25, 0.5),
        ('sparkle', W('sleep') - 0.15, 0.5),
        ('ding', W('watch') - 0.45, 0.55),
        ('sparkle', W('live') - 0.15, 0.6),
        ('pop', L[7] + 0.3, 0.6),          # the lockup lands
        ('ding', L[8] - 0.3, 0.55),        # and the button, on the spoken CTA
    ]
