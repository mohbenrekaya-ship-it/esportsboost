# -*- coding: utf-8 -*-
"""Cues for "Placements". No transition noise; a sound only where something
lands, and the five wins get a lighter tap than the four losses."""


def cues(W, L, lines, total):
    lose, win = W('lose') - 0.05, W('win') - 0.05
    return [
        ('riser', 0.0, 0.28),
        *[('tap', lose + d, 0.5) for d in (0, 0.26, 0.52, 0.78)],
        ('boom', W('march') - 0.25, 0.42),
        *[('tap', win + d, 0.38) for d in (0, 0.22, 0.44, 0.66, 0.88)],
        ('check', W('opens') - 0.08, 0.65),
        ('ding', W('sixteen') - 0.12, 0.6),
        ('pop', L[6] + 0.3, 0.6),
    ]
