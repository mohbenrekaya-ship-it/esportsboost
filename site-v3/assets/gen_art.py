#!/usr/bin/env python3
"""Generate original, license-clean key art (SVG) for every image slot in the V3 site.

These are abstract emblem plates — NOT game screenshots or fan art. Nothing here reproduces
any studio's characters or marks; each title is evoked only through its signature palette and
a geometric motif. Safe to ship. Regenerate with:  python3 site-v3/assets/gen_art.py
"""
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keyart')
os.makedirs(OUT, exist_ok=True)

GOLD = '#b68235'
GOLD_L = '#facb8d'
INK_HI = '#201f1b'
INK_LO = '#100f0d'
LINE = '#f3f2f2'


def defs(uid, c1, c2, cx='50%', cy='38%'):
    return (
        '<defs>'
        f'<linearGradient id="bg{uid}" x1="0" y1="0" x2="0.15" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>'
        f'<radialGradient id="vg{uid}" cx="{cx}" cy="{cy}" r="80%">'
        '<stop offset="0" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.6"/></radialGradient>'
        f'<filter id="bl{uid}" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur stdDeviation="34"/></filter>'
        f'<pattern id="ht{uid}" width="18" height="18" patternTransform="rotate(-45)" patternUnits="userSpaceOnUse">'
        f'<line x1="0" y1="0" x2="0" y2="18" stroke="{LINE}" stroke-opacity="0.035" stroke-width="8"/></pattern>'
        '</defs>'
    )


def ground(w, h, uid):
    return (
        f'<rect width="{w}" height="{h}" fill="url(#bg{uid})"/>'
        f'<rect width="{w}" height="{h}" fill="url(#ht{uid})"/>'
    )


def glow(cx, cy, r, color, uid, op=0.55):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="{op}" filter="url(#bl{uid})"/>'


def vignette(w, h, uid):
    return f'<rect width="{w}" height="{h}" fill="url(#vg{uid})"/>'


def frame(w, h):
    m, t = 12, 15
    s = []
    s.append(f'<rect x="{m}" y="{m}" width="{w-2*m}" height="{h-2*m}" fill="none" '
             f'stroke="{LINE}" stroke-opacity="0.12" stroke-width="1"/>')
    for (x, y, dx, dy) in ((m, m, t, t), (w-m, m, -t, t), (m, h-m, t, -t), (w-m, h-m, -t, -t)):
        s.append(f'<path d="M{x} {y+dy} L{x} {y} L{x+dx} {y}" fill="none" '
                 f'stroke="{GOLD}" stroke-opacity="0.75" stroke-width="1.3"/>')
    return ''.join(s)


def wrap(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'preserveAspectRatio="xMidYMid slice" width="100%" height="100%">{body}</svg>')


# ── motifs (centered at cx,cy, sized by s) ──────────────────────────────────
def m_valorant(cx, cy, s, a, b):
    o = []
    for ang in (35, -35):
        rad = math.radians(ang)
        dx, dy = math.cos(rad) * s, math.sin(rad) * s
        o.append(f'<line x1="{cx-dx:.1f}" y1="{cy-dy:.1f}" x2="{cx+dx:.1f}" y2="{cy+dy:.1f}" '
                 f'stroke="{a}" stroke-width="6" stroke-linecap="round" opacity="0.9"/>')
    o.append(f'<path d="M{cx-s*0.5:.1f} {cy+s*0.7:.1f} L{cx:.1f} {cy-s*0.75:.1f} L{cx+s*0.5:.1f} {cy+s*0.7:.1f}" '
             f'fill="none" stroke="{b}" stroke-width="2.4" opacity="0.85"/>')
    for (mx, my) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        o.append(f'<line x1="{cx+mx*s*0.28:.1f}" y1="{cy+my*s*0.28:.1f}" '
                 f'x2="{cx+mx*s*0.5:.1f}" y2="{cy+my*s*0.5:.1f}" stroke="{GOLD_L}" stroke-width="2"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="3.4" fill="{GOLD_L}"/>')
    return ''.join(o)


def m_lol(cx, cy, s, a, b):
    o = []
    for i, rr in enumerate((s, s*0.66, s*0.34)):
        pts = ' '.join(f'{cx+rr*math.cos(math.radians(60*k-90)):.1f},{cy+rr*math.sin(math.radians(60*k-90)):.1f}'
                       for k in range(6))
        col = a if i == 0 else (b if i == 1 else GOLD_L)
        o.append(f'<polygon points="{pts}" fill="none" stroke="{col}" stroke-width="2.2" opacity="0.9"/>')
    o.append(f'<rect x="{cx-6}" y="{cy-6}" width="12" height="12" transform="rotate(45 {cx} {cy})" fill="{GOLD_L}"/>')
    return ''.join(o)


def m_cs2(cx, cy, s, a, b):
    o = []
    for (mx, my) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        o.append(f'<line x1="{cx+mx*s*0.22:.1f}" y1="{cy+my*s*0.22:.1f}" '
                 f'x2="{cx+mx*s*0.62:.1f}" y2="{cy+my*s*0.62:.1f}" stroke="{a}" stroke-width="5" stroke-linecap="round"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{s*0.5:.1f}" fill="none" stroke="{b}" stroke-width="2" opacity="0.7"/>')
    for i in range(3):
        y = cy + s*0.78 + i*9
        o.append(f'<rect x="{cx-s*0.5:.1f}" y="{y:.1f}" width="{s*(1-i*0.22):.1f}" height="4" fill="{GOLD}" opacity="{0.8-i*0.2:.2f}"/>')
    return ''.join(o)


def m_apex(cx, cy, s, a, b):
    o = []
    for i, rr in enumerate((s, s*0.62)):
        col = a if i == 0 else b
        o.append(f'<path d="M{cx:.1f} {cy-rr:.1f} L{cx+rr*0.9:.1f} {cy+rr*0.7:.1f} L{cx-rr*0.9:.1f} {cy+rr*0.7:.1f} Z" '
                 f'fill="none" stroke="{col}" stroke-width="2.6" opacity="0.9"/>')
    for k in range(3):
        yy = cy + s*0.9 + k*10
        o.append(f'<path d="M{cx-16} {yy:.1f} L{cx} {yy+9:.1f} L{cx+16} {yy:.1f}" fill="none" '
                 f'stroke="{GOLD_L}" stroke-width="2" opacity="{0.7-k*0.2:.2f}"/>')
    return ''.join(o)


def m_overwatch(cx, cy, s, a, b):
    o = [f'<circle cx="{cx}" cy="{cy}" r="{s:.1f}" fill="none" stroke="{a}" stroke-width="5" opacity="0.9"/>']
    for k in range(6):
        ang = math.radians(60*k - 20)
        o.append(f'<line x1="{cx+s*0.55*math.cos(ang):.1f}" y1="{cy+s*0.55*math.sin(ang):.1f}" '
                 f'x2="{cx+s*math.cos(ang):.1f}" y2="{cy+s*math.sin(ang):.1f}" stroke="{b}" stroke-width="2.4" opacity="0.6"/>')
    o.append(f'<path d="M{cx-s*0.34:.1f} {cy:.1f} A {s*0.34:.1f} {s*0.34:.1f} 0 1 1 {cx+s*0.34:.1f} {cy:.1f}" '
             f'fill="none" stroke="{GOLD_L}" stroke-width="3"/>')
    return ''.join(o)


def m_rocket(cx, cy, s, a, b):
    o = []
    for i, rot in enumerate((0, 60, 120)):
        col = a if i % 2 == 0 else b
        o.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{s:.1f}" ry="{s*0.42:.1f}" transform="rotate({rot} {cx} {cy})" '
                 f'fill="none" stroke="{col}" stroke-width="2" opacity="0.75"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{s*0.26:.1f}" fill="none" stroke="{GOLD_L}" stroke-width="2.4"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{GOLD_L}"/>')
    return ''.join(o)


MOTIF = {'valorant': m_valorant, 'lol': m_lol, 'cs2': m_cs2,
         'apex': m_apex, 'overwatch': m_overwatch, 'rocket': m_rocket}


# ── game cards ──────────────────────────────────────────────────────────────
GAMES = [
    ('eb-g1', 'valorant', '#ff4655', '#2ee6c9'),
    ('eb-g2', 'lol', '#c8aa6e', '#1e9de0'),
    ('eb-g3', 'cs2', '#f0a500', '#4a90d9'),
    ('eb-g4', 'apex', '#e03a2f', '#ff7a1a'),
    ('eb-g5', 'overwatch', '#f99e1a', '#9aa2ab'),
    ('eb-g6', 'rocket', '#2a9bff', '#ff9e1b'),
]


def card(uid, motif, a, b):
    w, h = 480, 212
    cx, cy = w*0.5, h*0.46
    body = (defs(uid, INK_HI, INK_LO) + ground(w, h, uid)
            + glow(cx, cy, 150, a, uid, 0.28) + glow(w*0.16, h*0.2, 120, b, uid, 0.16)
            + MOTIF[motif](cx, cy, 52, a, b) + vignette(w, h, uid) + frame(w, h))
    return wrap(w, h, body)


# ── hero (brand ascent) ─────────────────────────────────────────────────────
def hero():
    w, h, uid = 560, 392, 'hero'
    body = [defs(uid, INK_HI, INK_LO, cy='42%'), ground(w, h, uid),
            glow(w*0.7, h*0.42, 210, GOLD, uid, 0.30), glow(w*0.2, h*0.7, 150, GOLD_L, uid, 0.10)]
    base_y, bx, bw, gap = 300, 96, 40, 18
    heights = [58, 96, 132, 176, 214, 262]
    for i, hh in enumerate(heights):
        x = bx + i*(bw+gap)
        op = 0.35 + i*0.11
        body.append(f'<rect x="{x}" y="{base_y-hh}" width="{bw}" height="{hh}" fill="{GOLD}" opacity="{op:.2f}"/>')
        body.append(f'<rect x="{x}" y="{base_y-hh}" width="{bw}" height="3" fill="{GOLD_L}" opacity="0.9"/>')
    # summit marker
    sx, sy = bx + 5*(bw+gap) + bw/2, base_y - heights[-1] - 26
    body.append(f'<line x1="{sx}" y1="{sy+10}" x2="{sx}" y2="{base_y-heights[-1]}" stroke="{GOLD_L}" stroke-width="1.2" opacity="0.6"/>')
    body.append(f'<rect x="{sx-6}" y="{sy-6}" width="12" height="12" fill="{GOLD_L}"/>')
    body.append(f'<rect x="{sx-11}" y="{sy-11}" width="22" height="22" fill="none" stroke="{GOLD}" stroke-width="1" opacity="0.7"/>')
    # ground rules
    for k in range(4):
        yy = base_y + 2 + k*20
        body.append(f'<line x1="60" y1="{yy}" x2="{w-60}" y2="{yy}" stroke="{LINE}" stroke-opacity="{0.09-k*0.02:.2f}" stroke-width="1"/>')
    body.append(vignette(w, h, uid))
    body.append(frame(w, h))
    return wrap(w, h, ''.join(body))


# ── coaching (VOD review) ───────────────────────────────────────────────────
def coach():
    w, h, uid = 460, 340, 'coach'
    body = [defs(uid, INK_HI, INK_LO), ground(w, h, uid),
            glow(w*0.5, h*0.36, 170, GOLD, uid, 0.24)]
    sx, sy, sw, sh = 70, 60, w-140, 150
    body.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="none" stroke="{GOLD}" stroke-opacity="0.7" stroke-width="1.4"/>')
    # play triangle
    pcx, pcy = sx+sw/2, sy+sh/2
    body.append(f'<path d="M{pcx-16} {pcy-20} L{pcx+22} {pcy} L{pcx-16} {pcy+20} Z" fill="none" stroke="{GOLD_L}" stroke-width="2.4"/>')
    # annotation carets
    for (ax, ay) in ((sx+40, sy+34), (sx+sw-52, sy+40), (sx+sw-70, sy+sh-40)):
        body.append(f'<path d="M{ax} {ay+8} L{ax+8} {ay} L{ax+16} {ay+8}" fill="none" stroke="#2ee6c9" stroke-width="2" opacity="0.7"/>')
    # timeline scrubber
    ty = sy+sh+40
    body.append(f'<line x1="{sx}" y1="{ty}" x2="{sx+sw}" y2="{ty}" stroke="{LINE}" stroke-opacity="0.2" stroke-width="2"/>')
    body.append(f'<line x1="{sx}" y1="{ty}" x2="{sx+sw*0.62:.1f}" y2="{ty}" stroke="{GOLD}" stroke-width="2"/>')
    for k in range(9):
        tx = sx + k*(sw/8)
        body.append(f'<line x1="{tx:.1f}" y1="{ty-5}" x2="{tx:.1f}" y2="{ty+5}" stroke="{LINE}" stroke-opacity="0.25" stroke-width="1"/>')
    body.append(f'<circle cx="{sx+sw*0.62:.1f}" cy="{ty}" r="6" fill="{GOLD_L}"/>')
    # notes lines
    for k in range(3):
        yy = ty+30+k*16
        body.append(f'<line x1="{sx}" y1="{yy}" x2="{sx+sw*(0.9-k*0.2):.1f}" y2="{yy}" stroke="{LINE}" stroke-opacity="{0.14-k*0.03:.2f}" stroke-width="3"/>')
    body.append(vignette(w, h, uid))
    body.append(frame(w, h))
    return wrap(w, h, ''.join(body))


# ── valorant page banner (wide, brighter — shown at opacity .2) ──────────────
def banner():
    w, h, uid = 1600, 520, 'ban'
    a, b = '#ff4655', '#2ee6c9'
    body = [defs(uid, '#241a19', '#120d0d', cy='45%'), ground(w, h, uid),
            glow(w*0.66, h*0.4, 360, a, uid, 0.45), glow(w*0.2, h*0.7, 280, b, uid, 0.22),
            glow(w*0.5, h*0.5, 240, GOLD, uid, 0.18)]
    # scattered faint crosshairs
    for (gx, gy, sc) in ((260, 150, 30), (520, 360, 22), (1180, 200, 26), (1380, 380, 20), (820, 120, 18)):
        body.append(f'<g opacity="0.5">{m_valorant(gx, gy, sc, a, b)}</g>')
    # hero crosshair
    body.append(m_valorant(w*0.62, h*0.5, 120, a, b))
    # base rule
    body.append(f'<line x1="80" y1="{h-70}" x2="{w-80}" y2="{h-70}" stroke="{GOLD}" stroke-opacity="0.4" stroke-width="1"/>')
    body.append(vignette(w, h, uid))
    return wrap(w, h, ''.join(body))


def write(name, svg):
    with open(os.path.join(OUT, name + '.svg'), 'w') as f:
        f.write(svg)


if __name__ == '__main__':
    n = 0
    for uid, motif, a, b in GAMES:
        write(uid, card(uid, motif, a, b)); n += 1
    write('eb-hero', hero()); n += 1
    write('eb-coach', coach()); n += 1
    write('eb-val-banner', banner()); n += 1
    print('generated %d key-art files in %s' % (n, OUT))
