# -*- coding: utf-8 -*-
"""Cues for "Four strangers". The four teammate rows are light taps; the one who
left is the only hard hit, and the screen share lands on a sparkle, not a boom."""


def cues(W, L, lines, total):
    s = W('strangers') - 0.1
    return [
        ('riser', 0.0, 0.28),
        ('pop', W('problem') - 0.2, 0.5),
        *[('tap', s + d, 0.42) for d in (0, 0.35, 0.7, 1.05)],
        ('boom', W('one', 9.5) + 0.2, 0.5),
        ('boom', W('minutes') - 0.12, 0.55),
        ('tap', W('three') - 0.1, 0.45),
        ('pop', L[4] + 0.05, 0.5),
        ('ding', W('master') - 0.1, 0.55),
        *[('check', W(k) - 0.12, 0.4) for k in ('account', 'hands')],
        ('check', W('games', 24.0) - 0.12, 0.4),
        ('sparkle', W('live', 26.0) - 0.1, 0.55),
        ('ding', W('phone', 27.0) - 0.15, 0.6),
        ('pop', L[7] + 0.3, 0.6),          # the lockup lands
        ('ding', L[8] - 0.3, 0.55),        # and the button, on the spoken CTA
    ]
