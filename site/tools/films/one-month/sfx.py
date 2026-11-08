# -*- coding: utf-8 -*-
"""Cues for "One month". The 28 nights are NOT given 28 sounds — that is a
machine gun, and the client's rule is small sounds on what appears. Four taps
mark the sweep, and the beats land on the spoken figures."""


def cues(W, L, lines, total):
    t0, t1 = W('twentyeight') - 0.1, W('games') + 0.5
    span = t1 - t0
    return [
        ('riser', 0.0, 0.28),
        *[('tap', t0 + span * k / 4, 0.32) for k in range(4)],
        ('boom', W('four') - 0.1, 0.4),          # 400 games
        ('tap', W('exactly') - 0.08, 0.5),       # the rank that did not move
        ('ding', W('one', 13.0) - 0.12, 0.6),    # one day
        ('check', W('ninetyone') - 0.1, 0.65),  # the price
        ('sparkle', L[6] + 0.2, 0.45),           # the nights come back
        ('pop', L[7] + 0.3, 0.6),
    ]
