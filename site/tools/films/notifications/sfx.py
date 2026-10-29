# -*- coding: utf-8 -*-
"""Sound cues for "Notifications".

The client's rule (Enevie BRIEF.md, rule 3): NO noise on transitions — no
whoosh. Only small sounds on the elements that appear, and a light riser at 0.
Times are in take time; they are hung on the spoken word, never on a constant."""


def cues(W, L, lines, total):
    first = W('minus')
    return [
        ('riser', 0.0, 0.28),
        ('tap', first - 0.1, 0.55),                      # the first loss lands
        ('tap', W('minus', first + 0.5) - 0.1, 0.55),    # the second
        ('boom', W('demoted') - 0.16, 0.5),              # demoted, softly
        ('ding', W('notification') - 0.12, 0.6),         # the one worth waiting for
        ('check', W('gold') + 0.05, 0.7),                # the rank lands
        ('sparkle', W('verified') - 0.1, 0.45),
        ('pop', L[6] + 0.3, 0.6),                        # the button
    ]
