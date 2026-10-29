# -*- coding: utf-8 -*-
"""Cues for "How it actually works" — the product's own screen."""


def cues(W, L, lines, total):
    return [
        ('riser', 0.0, 0.28),
        ('tap', W('pick') - 0.1, 0.5),            # the rank you are
        ('tap', W('where', 7.8) - 0.1, 0.5),      # the rank you want
        ('ding', W('price') - 0.12, 0.6),         # the price appears
        ('check', W('dollars') + 0.15, 0.6),      # the button
        ('pop', W('booster') - 0.12, 0.6),        # claimed
        ('sparkle', W('happens') - 0.08, 0.45),   # the live point lands
        ('tap', W('pause') - 0.12, 0.5),
        ('pop', L[6] + 0.3, 0.6),
    ]
