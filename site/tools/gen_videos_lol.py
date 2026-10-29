#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The five League of Legends ad films, 9:16, English voice-over.

    ELEVEN_VOICE_ID=<voice> python3 site/tools/gen_videos_lol.py [names...] [--preview]
    NO_VO=1 python3 site/tools/gen_videos_lol.py 1-hard-stuck      # pictures only, no credits

Scripts and the figures they are allowed to quote: marketing/video-scripts-lol-en.md.
Every film follows the brief's three beats — "Do you play League of Legends, or
something similar?", then the stuck player, then eSports Boost.

⚠ EVERY NUMBER SPOKEN HERE IS READ FROM pricing.py AT RENDER TIME (see `P()`),
so a re-price cannot leave a video quoting a price the checkout does not charge.
The one thing that does not follow automatically is the VOICE: the line is
written out in words ("twenty-five dollars"), so re-render after a re-price and
re-read the lines.

⚠ NOTHING HERE MAY QUOTE THE REVIEW SCORE, THE REVIEW COUNT, THE CLIENT COUNT OR
THE ROSTER SIZE. They are invented placeholders (CLAUDE.md, *Placeholder data*),
and an ad is where an invented statistic stops being a to-do.
"""
import math, os, sys
from video_lib import *                                    # noqa: F403
import pricing as PR                                       # noqa: E402

OUT = os.path.join(ROOT, 'assets-out', 'videos')
GAME = LOL['name']


def P(frm, to, mode='Solo'):
    """What the site charges for that climb today, as a whole-dollar int."""
    q = PR.quote({'game': GAME, 'service': 'division', 'from': frm, 'to': to, 'mode': mode})
    assert not q['invalid'], (frm, to)
    return int(round(q['total'])), q['eta']


SILVER_GOLD, ETA_SG = P('Silver IV', 'Gold IV')
GOLD_PLAT, _ = P('Gold IV', 'Platinum IV')
BRONZE_SILVER, _ = P('Bronze IV', 'Silver IV')
FLOOR = int(round(PR.quote({'game': GAME, 'service': 'division',
                            'from': LOL['ladder'][0], 'to': LOL['ladder'][1], 'mode': 'Solo'})['total']))
WIN1 = int(round(PR.quote({'game': GAME, 'service': 'wins', 'from': 'Gold IV',
                           'to': 'Gold IV', 'mode': 'Solo', 'wins': 1})['total']))


# ——— shared pieces ———
def price_plate(climb, amount, note=None, w=900):
    """A climb and its price, drawn like the order card's summary."""
    h = 300 if note else 240
    im = card(w, h, r=34)
    p = card_pad(im, w)
    im.alpha_composite(fit(climb, 54, 800, INK, w - 120), (p + 60, p + 46))
    amt = fit('$%d' % amount, 110, 900, EMBER, w - 120)
    im.alpha_composite(amt, (p + 60, p + 110))
    if note:
        im.alpha_composite(fit(note, 40, 600, TEXT2, w - 120), (p + 60, p + 230))
    return im


def chip_stack(labels, size=44, step=86):
    """One proof line per row, centred — three of these on ONE line runs 1,180px
    wide and clips at both edges of a 1,080 frame."""
    rows = [(check_icon(40, GREEN, BG), text(l, size, 600, TEXT2)) for l in labels]
    w = max(ic.width + 16 + tx.width for ic, tx in rows) + 40
    im = Image.new('RGBA', (w, step * len(rows)), (0, 0, 0, 0))
    for i, (ic, tx) in enumerate(rows):
        tot = ic.width + 16 + tx.width
        y = i * step + step // 2
        im.alpha_composite(ic, ((w - tot) // 2, y - ic.height // 2))
        im.alpha_composite(tx, ((w - tot) // 2 + ic.width + 16, y - tx.height // 2))
    return im


def chip_row(labels, size=38):
    """Two short proof chips on one line. Three do not fit — use chip_stack."""
    sprites = [(check_icon(36, GREEN, BG), text(l, size, 600, TEXT2)) for l in labels]
    gap, pad = 26, 20
    wds = [ic.width + 12 + tx.width for ic, tx in sprites]
    total = sum(wds) + gap * (len(sprites) - 1)
    im = Image.new('RGBA', (int(total) + pad * 2, 60), (0, 0, 0, 0))
    x = pad
    for (ic, tx), wd in zip(sprites, wds):
        im.alpha_composite(ic, (int(x), (60 - ic.height) // 2))
        im.alpha_composite(tx, (int(x + ic.width + 12), (60 - tx.height) // 2))
        x += wd + gap
    return im


def end_scene(sub, vo, button="Start my climb"):
    return Scene(EndCard(sub=sub, button=button), vo, min_dur=3.2, hold=1.7, sfx=[(0.6, 'pop')])


# ——— 1. Hard stuck (typo) ———
def v_hard_stuck():
    scenes = []
    defs = [
        ([("DO YOU PLAY", 128, INK), ("LEAGUE OF LEGENDS?", 100, EMBER)], None, 0,
         "Do you play League of Legends, or something similar?"),
        ([("SAME RANK", 150, INK), ("SINCE LAST", 120, INK), ("SEASON?", 180, EMBER)], None, 0,
         "And you're still in the same rank you were last season?"),
        ([("IT'S NOT", 140, TEXT2), ("YOUR AIM.", 190, INK)], None, 0,
         "It's not your aim."),
        ([("IT'S THE", 120, TEXT2), ("400 GAMES", 190, EMBER), ("IT TAKES.", 120, INK)], None, 0,
         "It's the four hundred games it takes."),
        ([("SO WE PLAY", 130, INK), ("THEM FOR YOU", 130, EMBER)], arrow_right(150, EMBER_LIT), 0,
         "So we play them for you."),
    ]
    for items, ic, spin, vo in defs:
        fn, times = typo(items, icon=ic, icon_spin=spin)
        scenes.append(Scene(fn, vo, min_dur=1.9, hold=0.42, vo_delay=0.08,
                            sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.15) for i in range(len(items))]))

    plate = price_plate("Silver IV  →  Gold IV", SILVER_GOLD, ETA_SG.capitalize())
    rk_a, rk_b = rank_mark('Silver IV', 150), rank_mark('Gold IV', 150)
    def price(t, c):
        cv = bg_soft().copy()
        p = ease_out(prog(t, 0.05, 0.4))
        put(cv, rk_a, W / 2 - 150, 620, a=p, s=lerp(0.8, 1, p))
        put(cv, arrow_right(70, TEXT3), W / 2, 620, a=p)
        put(cv, rk_b, W / 2 + 150, 620, a=ease_out(prog(t, 0.22, 0.4)), s=lerp(0.8, 1, ease_out(prog(t, 0.22, 0.4))))
        q = ease_out(prog(t, 0.4, 0.45))
        put(cv, plate, W / 2, 1010 + (1 - q) * 70, a=q)
        return cv
    scenes.append(Scene(price, "Silver to Gold: twenty-five dollars, and it's usually done in about a day.",
                        min_dur=2.6, hold=0.5, sfx=[(0.5, 'pop'), (0.95, 'pop', 0.8)]))

    fn, times = typo([("MONEY BACK", 120, INK), ("UNTIL A BOOSTER", 92, TEXT2), ("TAKES IT", 150, GREEN)])
    scenes.append(Scene(fn, "Money back until a booster takes the order.", min_dur=1.9, hold=0.45,
                        sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.1) for i in range(3)]))
    scenes.append(end_scene("One division from $%d" % FLOOR, "Link's right there."))
    return dict(name='1-hard-stuck', mood='electro', voice_speed=0.95, scenes=scenes,
                logo_mode=None, transition='cut')


# ——— 2. The climb (the ladder, animated) ———
def v_the_climb():
    scenes = []
    fn, times = typo([("DO YOU PLAY", 124, INK), ("LEAGUE OF LEGENDS?", 98, EMBER)])
    scenes.append(Scene(fn, "Do you play League of Legends, or something similar?", min_dur=1.9, hold=0.4,
                        sfx=[(lambda c, tm=times: tm(c)[0], 'pop', 1.1)]))

    plate, word = rank_mark('Silver IV', 240), rank_word('Silver IV', 92)
    def stuck(t, c):
        cv = bg_soft().copy()
        p = ease_out(prog(t, 0.05, 0.4))
        put(cv, plate, W / 2, 660, a=p, s=lerp(0.85, 1, p))
        put(cv, word, W / 2, 860, a=ease_out(prog(t, 0.2, 0.4)))
        # LP that climbs and falls back: the whole feeling of being hard stuck
        lp = 0.45 + 0.33 * math.sin(t * 2.1)
        put(cv, lp_bar(lp, 620, 26), W / 2, 980, a=ease_out(prog(t, 0.35, 0.4)))
        put(cv, text("%d LP" % round(lp * 100), 44, 700, TEXT2), W / 2, 1050,
            a=ease_out(prog(t, 0.45, 0.4)))
        return cv
    scenes.append(Scene(stuck, "This is you. Same two divisions, over and over.",
                        min_dur=2.4, hold=0.45, sfx=[(0.45, 'pop')]))

    nights = [text("Mon", 40, 700, TEXT3), text("Tue", 40, 700, TEXT3), text("Wed", 40, 700, TEXT3),
              text("Thu", 40, 700, TEXT3), text("Fri", 40, 700, TEXT3)]
    def grind(t, c):
        cv = bg_soft().copy()
        headline(cv, t, [("Climbing out", 560, 86, INK, 850), ("takes nights you", 660, 86, INK, 850),
                         ("don't have.", 760, 86, EMBER, 900)], start=0.05)
        for i, n in enumerate(nights):
            a = ease_out(prog(t, 0.55 + i * 0.16, 0.3))
            x = W / 2 - 400 + i * 200
            put(cv, circle(96, PANEL), x, 1020, a=a)
            put(cv, n, x, 1020, a=a)
            if prog(t, 0.72 + i * 0.16, 0.2) > 0.5:
                put(cv, check_icon(54, HAIR, TEXT3), x + 34, 1062, a=a)
        put(cv, plate, W / 2, 1300, a=ease_out(prog(t, 1.25, 0.4)) * 0.75, s=0.7)
        put(cv, text("still Silver IV", 44, 700, TEXT3), W / 2, 1450, a=ease_out(prog(t, 1.4, 0.4)))
        return cv
    scenes.append(Scene(grind, "Because climbing out takes nights you don't have.",
                        min_dur=3.0, hold=0.5, sfx=[(0.6 + i * 0.16, 'tap', 0.7) for i in range(5)]))

    def climb(t, c):
        cv = bg_soft().copy()
        f = ease_io(clamp((t - 0.35) / 1.5))
        put(cv, ladder('Silver IV', 'Gold IV', fill_to=f), W / 2, 760)
        put(cv, rank_mark('Silver IV' if f < 0.9 else 'Gold IV', 200), W / 2, 1060,
            a=ease_out(prog(t, 0.15, 0.4)))
        put(cv, rank_word('Gold IV', 90), W / 2, 1260, a=ease_out(prog(t, 1.55, 0.35)))
        if f >= 0.999:
            put(cv, sparkle(120, AMBER), W / 2 + 190, 980, a=0.9 * abs(math.sin(t * 6)))
        return cv
    scenes.append(Scene(climb, "A booster does it in about a day.", min_dur=3.0, hold=0.6,
                        sfx=[(0.35, 'whoosh', 0.7), (1.85, 'pop', 1.2)]))

    chips = chip_stack(EndCard.GUARANTEES)
    def promises(t, c):
        cv = bg_soft().copy()
        headline(cv, t, [("Paused whenever", 640, 82, INK, 850), ("you like.", 740, 82, EMBER, 900)], start=0.05)
        put(cv, chips, W / 2, 1010, a=ease_out(prog(t, 0.5, 0.45)))
        put(cv, price_plate("Silver IV  →  Gold IV", SILVER_GOLD), W / 2, 1380,
            a=ease_out(prog(t, 0.8, 0.45)))
        return cv
    scenes.append(Scene(promises, "Paused whenever you like, on a VPN in your region, and your name never shows. "
                                  "Twenty-five dollars for the climb.", min_dur=3.0, hold=0.5, sfx=[(0.9, 'pop')]))
    scenes.append(end_scene("Every rank has its own price", "Pick my rank"))
    return dict(name='2-the-climb', mood='electro', scenes=scenes, logo_mode=None)


# ——— 3. Which one are you? (quiz) ———
def quiz_card(question, options, chosen=None, w=940):
    h = 520
    im = card(w, h, r=44)
    p = card_pad(im, w)
    lines = wrap(question, 62, 850, w - 120)
    y = p + 60
    for ln in lines:
        sp = text(ln, 62, 850, INK)
        im.alpha_composite(sp, (p + (w - sp.width) // 2, y)); y += 78
    bw, bh = (w - 160) // len(options), 130
    for j, lab in enumerate(options):
        sel = chosen == j
        b = rrect(bw, bh, 30, EMBER if sel else PANEL)
        if not sel:
            b.alpha_composite(rrect(bw, bh, 30, HAIR), (0, 0))
            b.alpha_composite(rrect(bw - 6, bh - 6, 27, PANEL), (3, 3))
        t_ = fit(lab, 52, 850, (6, 6, 10) if sel else INK, bw - 50)
        b.alpha_composite(t_, ((bw - t_.width) // 2, (bh - t_.height) // 2))
        im.alpha_composite(b, (p + 80 + j * (bw + (80 if len(options) == 2 else 20)), p + h - bh - 70))
    return im


CURSOR = None
def cursor():
    global CURSOR
    if CURSOR is None:
        c = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
        sh = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse((28, 34, 92, 98), fill=(0, 0, 0, 150))
        c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        c.alpha_composite(circle(64, INK), (28, 28))
        c.alpha_composite(circle(42, (150, 150, 162)), (39, 39))
        CURSOR = c
    return CURSOR


def quiz_scene(question, options, pick, from_xy=(880, 1500)):
    """The cursor flies in and taps an answer. `pick` is the option index."""
    def fn(t, c):
        cv = bg_soft().copy()
        tap = max(0.55, c.vo_end - 0.25)
        chosen = pick if t > tap else None
        cardim = quiz_card(question, options, chosen)
        p = ease_out(prog(t, 0.05, 0.4))
        put(cv, cardim, W / 2, 900 + (1 - p) * 60, a=p)
        n = len(options)
        bw = (940 - 160) // n
        gap = 80 if n == 2 else 20
        bx = (W - 940) / 2 + 40 + 80 + pick * (bw + gap) + bw / 2
        by = 900 + 520 / 2 - 130 / 2 - 70 + 65
        k = ease_io(clamp((t - 0.3) / max(0.35, tap - 0.3)))
        x, y = lerp_pt(from_xy, (bx, by), k)
        put(cv, cursor(), x, y, a=clamp(prog(t, 0.25, 0.2)), s=0.92 if t > tap else 1.0)
        return cv
    return fn


def v_which_one():
    scenes = [
        Scene(quiz_scene("Do you play League of Legends?", ("Yes", "No"), 0),
              "Do you play League of Legends, or something similar?", min_dur=2.6, hold=0.4,
              sfx=[(lambda c: max(0.55, c.vo_end - 0.25), 'pop', 1.2)]),
        Scene(quiz_scene("Stuck in your rank right now?", ("Yes", "No"), 0),
              "Are you stuck in your rank right now?", min_dur=2.4, hold=0.4,
              sfx=[(lambda c: max(0.55, c.vo_end - 0.25), 'pop', 1.2)]),
        Scene(quiz_scene("Which one are you in?", ("Bronze", "Silver", "Gold"), 1),
              "Pick the one you're sitting in.", min_dur=2.6, hold=0.5,
              sfx=[(lambda c: max(0.55, c.vo_end - 0.25), 'pop', 1.2)]),
    ]

    plate = price_plate("Silver IV  →  Gold IV", SILVER_GOLD, ETA_SG.capitalize())
    def answer(t, c):
        cv = bg_soft().copy()
        p = ease_out(prog(t, 0.05, 0.4))
        put(cv, rank_mark('Silver IV', 160), W / 2 - 160, 620, a=p)
        put(cv, arrow_right(66, TEXT3), W / 2, 620, a=p)
        put(cv, rank_mark('Gold IV', 160), W / 2 + 160, 620, a=ease_out(prog(t, 0.2, 0.4)))
        q = ease_out(prog(t, 0.4, 0.45))
        put(cv, plate, W / 2, 1020 + (1 - q) * 60, a=q)
        return cv
    scenes.append(Scene(answer, "Silver to Gold is twenty-five dollars, and about a day.",
                        min_dur=2.6, hold=0.5, sfx=[(0.5, 'pop')]))

    rows = [("Bronze IV → Silver IV", BRONZE_SILVER), ("Silver IV → Gold IV", SILVER_GOLD),
            ("Gold IV → Platinum IV", GOLD_PLAT)]
    plates = [price_plate(c_, v, w=860) for c_, v in rows]
    def grid(t, c):
        cv = bg_soft().copy()
        headline(cv, t, [("Every rank has", 500, 80, INK, 850), ("its own price.", 596, 80, EMBER, 900)], start=0.02)
        for i, pl in enumerate(plates):
            a = ease_out(prog(t, 0.35 + i * 0.22, 0.4))
            put(cv, pl, W / 2, 860 + i * 270, a=a, s=lerp(0.94, 1, a))
        put(cv, text("One division from $%d" % FLOOR, 46, 700, TEXT2), W / 2, 1690,
            a=ease_out(prog(t, 1.15, 0.4)))
        return cv
    scenes.append(Scene(grid, "Every rank has its own price. One division starts at four dollars.",
                        min_dur=3.2, hold=0.6, sfx=[(0.4 + i * 0.22, 'pop', 0.9) for i in range(3)]))
    scenes.append(end_scene("Money back until a booster takes it", "Find my rank"))
    return dict(name='3-which-one-are-you', mood='electro', scenes=scenes, logo_mode=None)


# ——— 4. Watch it happen ———
# ⚠ THIS FILM SELLS THE SCREEN SHARE AND THE DISCORD SIDE IS NOT BUILT.
# `streams.py` does not exist: nothing opens a channel and nothing tells a
# booster to share. Every order this brings in is a promise a person has to keep
# by hand. Either that is arranged with ops, or this film does not ship.
def dash_card(t, w=940):
    h = 620
    im = card(w, h, r=40)
    p = card_pad(im, w)
    im.alpha_composite(text("Your order", 40, 700, TEXT2), (p + 56, p + 44))
    pill_ = pill("IN PROGRESS", 30, 850, GREEN, (12, 40, 28))
    im.alpha_composite(pill_, (p + w - pill_.width - 56, p + 38))
    im.alpha_composite(rank_mark('Silver IV', 96, ring=True), (p + 56, p + 120))
    im.alpha_composite(arrow_right(44, TEXT3), (p + 176, p + 148))
    im.alpha_composite(rank_mark('Gold IV', 96, ring=True), (p + 240, p + 120))
    im.alpha_composite(fit("6 of 12 rungs", 40, 700, TEXT2, 300), (p + 380, p + 152))
    im.alpha_composite(lp_bar(clamp(0.2 + 0.5 * ease_io(clamp((t - 0.6) / 1.6))), w - 112, 22), (p + 56, p + 250))
    # a chart that climbs as the scene runs
    pts, n = [], 14
    k = ease_io(clamp((t - 0.8) / 1.8))
    for i in range(n):
        x = p + 56 + i * (w - 112) / (n - 1)
        v = 0.25 + 0.5 * (i / (n - 1)) + 0.07 * math.sin(i * 1.7)
        pts.append((x, p + 520 - v * 180 * (1 if i / (n - 1) <= k else 0) - (0 if i / (n - 1) <= k else -40)))
    shown = [q for i, q in enumerate(pts) if i / (n - 1) <= k] or pts[:1]
    if len(shown) > 1:
        ImageDraw.Draw(im).line(shown, fill=EMBER + (255,), width=7, joint='curve')
    for i, q in enumerate(shown[-1:]):
        im.alpha_composite(circle(22, EMBER_LIT), (int(q[0]) - 11, int(q[1]) - 11))
    im.alpha_composite(text("LP today", 34, 600, TEXT3), (p + 56, p + 540))
    return im


def v_watch():
    scenes = []
    fn, times = typo([("DO YOU PLAY", 124, INK), ("LEAGUE OF LEGENDS?", 98, EMBER)])
    scenes.append(Scene(fn, "Do you play League of Legends, or something similar?", min_dur=1.9, hold=0.4,
                        sfx=[(lambda c, tm=times: tm(c)[0], 'pop', 1.1)]))
    fn, times = typo([("STUCK IN GOLD", 130, INK), ("AND TIRED OF", 96, TEXT2), ("GRINDING?", 160, EMBER)])
    scenes.append(Scene(fn, "Stuck in the same rank, and tired of grinding for it?", min_dur=2.0, hold=0.4,
                        sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.1) for i in range(3)]))

    quote = card(900, 260, r=34)
    _p = card_pad(quote, 900)
    for i, ln in enumerate(wrap("“So I just hand it over and hope?”", 56, 800, 780)):
        quote.alpha_composite(text(ln, 56, 800, INK), (_p + 60, _p + 60 + i * 76))
    def objection(t, c):
        cv = bg_soft().copy()
        p = ease_out(prog(t, 0.05, 0.4))
        put(cv, quote, W / 2, 860 + (1 - p) * 50, a=p)
        return cv
    scenes.append(Scene(objection, "The usual problem with paying someone: you hand it over and hope.",
                        min_dur=2.4, hold=0.45, sfx=[(0.3, 'pop')]))

    def dash(t, c):
        cv = bg_soft().copy()
        p = ease_out(prog(t, 0.05, 0.45))
        put(cv, dash_card(t), W / 2, 900 + (1 - p) * 60, a=p)
        put(cv, text("Live rank, every game, as it happens", 44, 650, TEXT2), W / 2, 1320,
            a=ease_out(prog(t, 0.7, 0.4)))
        return cv
    scenes.append(Scene(dash, "Here you watch it. Live rank, every game, as it happens.",
                        min_dur=3.2, hold=0.6, sfx=[(0.3, 'pop'), (1.5, 'tap', 0.6)]))

    free = pill("FREE", 40, 900, (6, 6, 10), GREEN)
    def stream(t, c):
        cv = bg_soft().copy()
        headline(cv, t, [("Watch your", 580, 92, INK, 850), ("booster play", 686, 92, EMBER, 900)], start=0.04)
        put(cv, free, W / 2, 850, a=ease_out(prog(t, 0.45, 0.35)), s=pop(prog(t, 0.45, 0.35)))
        put(cv, chip_row(("Their screen, live", "No extra cost")), W / 2, 1010,
            a=ease_out(prog(t, 0.7, 0.4)))
        put(cv, price_plate("Gold IV  →  Platinum IV", GOLD_PLAT), W / 2, 1290,
            a=ease_out(prog(t, 0.95, 0.45)))
        return cv
    scenes.append(Scene(stream, "And you can watch your booster's screen while they play. That's free. "
                                "Gold to Platinum: thirty-six dollars.", min_dur=3.4, hold=0.6,
                        sfx=[(0.5, 'pop', 1.2), (1.05, 'pop', 0.9)]))
    scenes.append(end_scene("Watch it climb, from your phone", "Start my climb"))
    return dict(name='4-watch-it-happen', mood='electro', scenes=scenes, logo_mode=None)


# ——— 5. Less than a skin ———
def v_skin():
    scenes = []
    fn, times = typo([("DO YOU PLAY", 124, INK), ("LEAGUE OF LEGENDS?", 98, EMBER)])
    scenes.append(Scene(fn, "Do you play League of Legends, or something similar?", min_dur=1.9, hold=0.4,
                        sfx=[(lambda c, tm=times: tm(c)[0], 'pop', 1.1)]))
    fn, times = typo([("HARD STUCK", 160, INK), ("FOR MONTHS?", 130, EMBER)])
    scenes.append(Scene(fn, "Been hard stuck for months, and the climb just isn't happening?",
                        min_dur=2.0, hold=0.4,
                        sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.1) for i in range(2)]))

    # A skin is drawn as a tile, never a screenshot: the splash art is licensed,
    # the same rule pay_marks() and the rank emblems follow.
    def skin_tile(label, price, accent):
        im = card(420, 520, r=34)
        p = card_pad(im, 420)
        art = shape(360, 300, lambda d, k: d.rounded_rectangle((0, 0, 360 * k, 300 * k), 20 * k, fill=accent + (70,)))
        im.alpha_composite(art, (p + 30, p + 30))
        im.alpha_composite(fit(label, 40, 800, INK, 320), (p + 30, p + 360))
        im.alpha_composite(fit(price, 70, 900, accent, 320), (p + 30, p + 420))
        return im
    skin = skin_tile("A skin", "$22", SKY)
    rank = skin_tile("A whole rank", "$%d" % SILVER_GOLD, EMBER)
    def compare(t, c):
        cv = bg_soft().copy()
        a = ease_out(prog(t, 0.05, 0.4))
        put(cv, skin, W / 2 - 240, 820, a=a, s=lerp(0.9, 1, a))
        b = ease_out(prog(t, max(0.45, c.vo_end * 0.55), 0.4))
        put(cv, rank, W / 2 + 240, 820, a=b, s=lerp(0.9, 1, b))
        put(cv, text("vs", 54, 800, TEXT3), W / 2, 820, a=min(a, b))
        return cv
    scenes.append(Scene(compare, "You'll spend twenty-two on a skin without thinking about it. "
                                 "A whole rank is twenty-five.", min_dur=3.4, hold=0.6,
                        sfx=[(0.3, 'pop'), (1.6, 'pop', 1.2)]))

    fn, times = typo([("ONE DIVISION", 110, TEXT2), ("FROM $%d" % FLOOR, 210, EMBER),
                      ("ONE WIN, $%d" % WIN1, 90, INK)])
    scenes.append(Scene(fn, "One division starts at four dollars. One win, three.", min_dur=2.2, hold=0.45,
                        sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.1) for i in range(3)]))

    pct = int(round(D.PROMOS['SPLIT15']['pct'] * 100))
    fn, times = typo([("%d%% OFF" % pct, 210, EMBER), ("RIGHT NOW", 120, INK)])
    scenes.append(Scene(fn, "Fifteen percent off right now, applied at checkout — nothing to type.",
                        min_dur=2.2, hold=0.5,
                        sfx=[(lambda c, i=i, tm=times: tm(c)[i], 'pop', 1.2) for i in range(2)]))
    scenes.append(end_scene("Pick your rank, we climb it", "Start my climb"))
    return dict(name='5-less-than-a-skin', mood='electro', scenes=scenes, logo_mode=None)


VIDEOS = {'1-hard-stuck': v_hard_stuck, '2-the-climb': v_the_climb,
          '3-which-one-are-you': v_which_one, '4-watch-it-happen': v_watch,
          '5-less-than-a-skin': v_skin}

if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or list(VIDEOS)
    for nm in names:
        v = VIDEOS[nm]()
        kw = dict(voice_speed=v.get('voice_speed', 0.95), logo_mode=v.get('logo_mode', None),
                  transition=v.get('transition', 'fade'))
        if '--preview' in sys.argv:
            total = render(v['name'], v['scenes'], v['mood'], OUT,
                           preview=os.path.join(OUT, '_preview-%s.jpg' % v['name']), **kw)
            print('%s: %.1f s (preview)' % (v['name'], total))
        else:
            out, total = render(v['name'], v['scenes'], v['mood'], OUT, **kw)
            print('%s: %.1f s -> %s' % (v['name'], total, out))
