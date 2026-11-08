# -*- coding: utf-8 -*-
"""Cues for "Watch something else". Four soft taps as the episodes are watched,
nothing under the climbing bar, and the second screen lands on a sparkle."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.26),
        ('tap', W('rank') - 0.15, 0.45),
        ('pop', W('trade') - 0.2, 0.5),
        ('check', W('season') - 0.1, 0.4),
        ('check', W('season') + 0.55, 0.4),
        ('check', W('wanted') - 0.05, 0.4),
        ('check', W('wanted') + 0.55, 0.4),
        ('ding', W('account') + 1.1, 0.55),
        ('pop', W('screen') - 0.15, 0.5),
        ('sparkle', W('live', 20.0) - 0.15, 0.6),
        ('pop', L[7] + 0.3, 0.6),          # the lockup lands
        ('ding', L[8] - 0.3, 0.55),        # and the button, on the spoken CTA
    ]
