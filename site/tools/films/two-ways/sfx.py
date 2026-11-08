# -*- coding: utf-8 -*-
"""Cues for "Two ways out". Five taps for the queue, then the two lanes land as a
pair — one ember, one night — and the handset gets the only sparkle."""


def cues(W, L, lines, total):
    f = W('four') - 0.1
    return [
        ('riser', 0.0, 0.26),
        ('tap', W('stuck') - 0.15, 0.45),
        *[('tap', f + d, 0.4) for d in (0, 0.22, 0.44, 0.66)],
        ('boom', W('coin') - 0.15, 0.5),
        ('pop', W('duo') - 0.3, 0.5),
        ('check', W('game') - 0.1, 0.4),
        ('check', W('hands') - 0.1, 0.4),
        ('pop', W('solo') - 0.3, 0.5),
        ('check', W('laptop') - 0.1, 0.4),
        ('check', W('sleep') - 0.1, 0.4),
        ('ding', W('watch', 22.0) - 0.35, 0.55),
        ('sparkle', W('live', 24.0) - 0.2, 0.6),
        ('pop', L[7] + 0.3, 0.6),          # the lockup lands
        ('ding', L[8] - 0.3, 0.55),        # and the button, on the spoken CTA
    ]
