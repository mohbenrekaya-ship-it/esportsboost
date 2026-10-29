# -*- coding: utf-8 -*-
"""Cues for "True or false". One sound per card turned over; the third is a
softer one, because that card says the risk is real and a bright ding would
sell past it."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.28),
        ('tap', W('three') + 0.15, 0.4), ('tap', W('things') + 0.15, 0.4), ('tap', W('people') + 0.15, 0.4),
        ('check', W('false') - 0.12, 0.65),          # card 1: false
        ('check', W('false', 17.0) - 0.12, 0.65),    # card 2: false
        ('boom', W('true') - 0.12, 0.42),            # card 3: true, stated softly
        ('pop', L[8] + 0.3, 0.6),
    ]
