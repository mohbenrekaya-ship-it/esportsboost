# -*- coding: utf-8 -*-
"""Procedural artwork for every image slot in the v2 handoff.

The design ships 16 empty drop-in slots. Nothing here is licensed game art —
these are **original abstract compositions in the Ashfall palette**, built so
the page reads as finished and so the real photography can drop in later
without any layout change. Real game key art and real booster portraits must
replace them before launch; the procedural ember/grain/scanline layers in the
page composite over whatever lands here.

Every generator is deterministic: same game, same picture, every build.
"""
import base64
import math
import os

LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets-in", "_logos")
_LOGO_CACHE = {}


def logo_uri(slug):
    """Data-URI of a real game logo dropped in assets-in/_logos/<slug>.(svg|png|jpg),
    or None. Kept out of the repo's committed art — these are the publishers'
    trademarks, fetched for an academic (non-commercial) project."""
    if slug in _LOGO_CACHE:
        return _LOGO_CACHE[slug]
    uri = None
    for ext, mime in ((".svg", "image/svg+xml"), (".png", "image/png"),
                      (".jpg", "image/jpeg"), (".jpeg", "image/jpeg"), (".webp", "image/webp")):
        path = os.path.join(LOGO_DIR, slug + ext)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                uri = "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))
            break
    _LOGO_CACHE[slug] = uri
    return uri


def _logo_image(uri, x, y, bw, bh):
    """A logo fitted (meet, centred) into a box, with a soft dark plate behind
    it so a light logo stays legible over the ember glow."""
    return (f'<image href="{uri}" x="{x:.0f}" y="{y:.0f}" width="{bw:.0f}" height="{bh:.0f}" '
            f'preserveAspectRatio="xMidYMid meet"/>')


EMBER = "#ff4a1f"
AMBER = "#ffb046"
PALE = "#ffd39a"
HOT = "#ff8a4c"
BG = "#06060a"


# ── deterministic noise ───────────────────────────────────────────────────
class Rng:
    """Tiny LCG so a game's art never shifts between builds."""

    def __init__(self, seed):
        self.s = (seed * 2654435761) % 2147483647 or 1

    def next(self):
        self.s = (self.s * 48271) % 2147483647
        return self.s / 2147483647

    def rng(self, a, b):
        return a + (b - a) * self.next()


def seed_of(text):
    return sum((i + 3) * ord(c) for i, c in enumerate(text))


def _defs(uid, hue, w, h, ha=0.85, hb=0.28):
    """Shared gradient / filter definitions."""
    return f"""
  <linearGradient id="sky{uid}" x1="0" y1="0" x2="0.35" y2="1">
    <stop offset="0" stop-color="hsl({hue},34%,11%)"/>
    <stop offset="0.55" stop-color="#0a0a12"/>
    <stop offset="1" stop-color="#06060a"/>
  </linearGradient>
  <radialGradient id="heat{uid}" cx="0.62" cy="0.44" r="0.55">
    <stop offset="0" stop-color="{EMBER}" stop-opacity="{ha}"/>
    <stop offset="0.45" stop-color="{AMBER}" stop-opacity="{hb}"/>
    <stop offset="1" stop-color="{AMBER}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="cold{uid}" cx="0.16" cy="0.82" r="0.6">
    <stop offset="0" stop-color="#3a2078" stop-opacity="0.55"/>
    <stop offset="1" stop-color="#3a2078" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="hot{uid}" x1="0" y1="0" x2="1" y2="0.4">
    <stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="#ff3d0f"/>
  </linearGradient>
  <linearGradient id="scrim{uid}" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="{BG}" stop-opacity="0.96"/>
    <stop offset="0.42" stop-color="{BG}" stop-opacity="0.32"/>
    <stop offset="1" stop-color="{BG}" stop-opacity="0"/>
  </linearGradient>
  <filter id="grain{uid}" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/>
  </filter>
  <filter id="blur{uid}" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="{max(6, w // 42)}"/>
  </filter>
  <pattern id="scan{uid}" width="4" height="4" patternUnits="userSpaceOnUse">
    <rect width="4" height="1" fill="#ffffff" fill-opacity="0.03"/>
  </pattern>
  <radialGradient id="vig{uid}" cx="0.5" cy="0.45" r="0.78">
    <stop offset="0.45" stop-color="#000000" stop-opacity="0"/>
    <stop offset="1" stop-color="#000000" stop-opacity="0.72"/>
  </radialGradient>
  <linearGradient id="rim{uid}" x1="0" y1="0" x2="1" y2="0.3">
    <stop offset="0" stop-color="{AMBER}" stop-opacity="0"/>
    <stop offset="0.55" stop-color="{AMBER}" stop-opacity="0.85"/>
    <stop offset="1" stop-color="{EMBER}" stop-opacity="0.15"/>
  </linearGradient>
  <linearGradient id="haze{uid}" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{HOT}" stop-opacity="0"/>
    <stop offset="0.5" stop-color="{HOT}" stop-opacity="0.16"/>
    <stop offset="1" stop-color="{HOT}" stop-opacity="0"/>
  </linearGradient>"""


# ── motifs — one silhouette language per game ─────────────────────────────
def _motif(kind, r, w, h, hue):
    """Foreground silhouettes. Everything sits in the bottom two thirds so the
    page's own scrims and the title block never fight the subject."""
    out = []
    dark = f"hsl({hue},22%,7%)"
    mid = f"hsl({hue},20%,10%)"

    if kind == "arcs":  # League of Legends — concentric arches
        cx, cy = w * 0.63, h * 0.62
        for i in range(5):
            rad = w * (0.10 + i * 0.075)
            out.append(f'<path d="M{cx - rad} {cy} A{rad} {rad} 0 0 1 {cx + rad} {cy}" '
                       f'fill="none" stroke="{AMBER}" stroke-opacity="{0.55 - i * 0.09:.2f}" stroke-width="{3.4 - i * 0.4:.1f}"/>')
        out.append(f'<path d="M0 {h} L0 {h * 0.72} L{w * 0.22} {h * 0.58} L{w * 0.42} {h * 0.78} L{w * 0.6} {h * 0.66} L{w} {h * 0.84} L{w} {h} Z" fill="{dark}"/>')

    elif kind == "shards":  # Valorant — angular fragments
        for i in range(7):
            x = r.rng(0, w)
            y = r.rng(h * 0.28, h * 0.86)
            s = r.rng(w * 0.04, w * 0.13)
            out.append(f'<path d="M{x} {y} L{x + s} {y - s * 0.5} L{x + s * 0.7} {y + s * 0.8} Z" '
                       f'fill="{mid}" stroke="{AMBER}" stroke-opacity="0.55" stroke-width="1.6"/>')
        out.append(f'<path d="M0 {h} L{w * 0.3} {h * 0.55} L{w * 0.55} {h * 0.8} L{w * 0.8} {h * 0.5} L{w} {h * 0.7} L{w} {h} Z" fill="{dark}"/>')

    elif kind == "grid":  # Counter-Strike 2 — crate stacks
        bw = w * 0.055
        for i in range(11):
            bh = r.rng(h * 0.10, h * 0.36)
            x = i * bw * 1.18 + w * 0.02
            out.append(f'<rect x="{x:.1f}" y="{h - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{dark}" '
                       f'stroke="{AMBER}" stroke-opacity="0.18"/>')
        out.append(f'<rect x="{w * 0.6:.0f}" y="{h * 0.30:.0f}" width="{w * 0.16:.0f}" height="1.5" fill="{HOT}" fill-opacity="0.5"/>')
        out.append(f'<rect x="{w * 0.675:.0f}" y="{h * 0.22:.0f}" width="1.5" height="{h * 0.16:.0f}" fill="{HOT}" fill-opacity="0.5"/>')

    elif kind == "hex":  # Teamfight Tactics — board
        s = w * 0.045
        for row in range(4):
            for col in range(9):
                cx = w * 0.06 + col * s * 1.75 + (row % 2) * s * 0.88
                cy = h * 0.52 + row * s * 1.5
                pts = " ".join("%.1f,%.1f" % (cx + s * math.cos(math.pi / 6 + k * math.pi / 3),
                                              cy + s * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6))
                op = 0.05 + 0.16 * r.next()
                out.append(f'<polygon points="{pts}" fill="{mid}" stroke="{AMBER}" stroke-opacity="{min(0.55, op * 2.4):.2f}" stroke-width="1.4"/>')

    elif kind == "burst":  # Marvel Rivals — radiating impact
        cx, cy = w * 0.66, h * 0.5
        for i in range(22):
            a = i * math.pi * 2 / 22 + 0.2
            l = r.rng(w * 0.08, w * 0.3)
            out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + math.cos(a) * l:.1f}" y2="{cy + math.sin(a) * l:.1f}" '
                       f'stroke="{AMBER}" stroke-opacity="{0.12 + 0.34 * r.next():.2f}" stroke-width="{r.rng(0.8, 2.4):.1f}"/>')
        out.append(f'<path d="M0 {h} L{w * 0.25} {h * 0.62} L{w * 0.5} {h * 0.85} L{w} {h * 0.6} L{w} {h} Z" fill="{dark}"/>')

    elif kind == "ridges":  # Dota 2 — layered ranges
        for layer in range(3):
            y0 = h * (0.5 + layer * 0.13)
            pts = ["0,%.0f" % h, "0,%.1f" % y0]
            x = 0.0
            while x < w:
                x += r.rng(w * 0.06, w * 0.14)
                pts.append("%.1f,%.1f" % (x, y0 + r.rng(-h * 0.12, h * 0.06)))
            pts += ["%.0f,%.0f" % (w, h)]
            shade = ["#0d0d16", "#0a0a12", dark][layer]
            out.append('<polygon points="%s" fill="%s"/>' % (" ".join(pts), shade))

    elif kind == "chevrons":  # Apex Legends
        for i in range(6):
            y = h * 0.3 + i * h * 0.11
            out.append(f'<path d="M{w * 0.2} {y} L{w * 0.42} {y + h * 0.07} L{w * 0.64} {y}" fill="none" '
                       f'stroke="{EMBER}" stroke-opacity="{0.48 - i * 0.06:.2f}" stroke-width="2.6"/>')
        out.append(f'<path d="M0 {h} L{w * 0.35} {h * 0.6} L{w * 0.7} {h * 0.82} L{w} {h * 0.58} L{w} {h} Z" fill="{dark}"/>')

    elif kind == "rings":  # Overwatch 2
        for i in range(4):
            rad = w * (0.09 + i * 0.06)
            out.append(f'<circle cx="{w * 0.68:.0f}" cy="{h * 0.46:.0f}" r="{rad:.0f}" fill="none" '
                       f'stroke="{PALE}" stroke-opacity="{0.42 - i * 0.07:.2f}" stroke-width="2"/>')
        out.append(f'<rect x="0" y="{h * 0.74:.0f}" width="{w}" height="{h * 0.26:.0f}" fill="{dark}"/>')

    else:  # "field" — Rocket League
        cy = h * 0.98
        for i in range(9):
            x = w * (i / 8.0)
            out.append(f'<line x1="{x:.0f}" y1="{h * 0.55:.0f}" x2="{w * 0.5 + (x - w * 0.5) * 2.4:.0f}" y2="{cy:.0f}" '
                       f'stroke="{AMBER}" stroke-opacity="0.26" stroke-width="1.3"/>')
        for i in range(4):
            out.append(f'<ellipse cx="{w * 0.5:.0f}" cy="{cy:.0f}" rx="{w * (0.12 + i * 0.12):.0f}" ry="{h * (0.06 + i * 0.07):.0f}" '
                       f'fill="none" stroke="{AMBER}" stroke-opacity="0.22" stroke-width="1.3"/>')
        out.append(f'<circle cx="{w * 0.7:.0f}" cy="{h * 0.42:.0f}" r="{w * 0.07:.0f}" fill="{mid}" stroke="{AMBER}" stroke-opacity="0.6" stroke-width="2"/>')

    return "\n  ".join(out)


MOTIFS = {
    "league-of-legends": ("arcs", 20),
    "valorant": ("shards", 352),
    "counter-strike-2": ("grid", 32),
    "teamfight-tactics": ("hex", 196),
    "marvel-rivals": ("burst", 8),
    "dota-2": ("ridges", 16),
    "apex-legends": ("chevrons", 4),
    "overwatch-2": ("rings", 210),
    "rocket-league": ("field", 224),
}


def _sparks(r, w, h, n=14):
    out = []
    for _ in range(n):
        x, y = r.rng(w * 0.1, w * 0.95), r.rng(h * 0.2, h * 0.95)
        rad = r.rng(0.9, 2.6)
        c = [HOT, AMBER, PALE, "#ff5a24"][int(r.next() * 4) % 4]
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rad:.1f}" fill="{c}" fill-opacity="{r.rng(0.35, 0.9):.2f}"/>')
    return "\n  ".join(out)


def _depth(r, w, h, hue):
    """Far ridge and haze bands. This is what makes a tile read as a
    photograph with distance in it rather than a flat gradient."""
    out = []
    for i in range(3):
        y = h * (0.34 + i * 0.09)
        out.append('<rect x="0" y="%.0f" width="%d" height="%.0f" fill="url(#hazeH)" opacity="%.2f"/>'
                   % (y, w, h * 0.035, 0.7 - i * 0.2))
    pts = ["0,%.0f" % h, "0,%.0f" % (h * 0.60)]
    x, y0 = 0.0, h * 0.60
    while x < w:
        x += r.rng(w * 0.08, w * 0.17)
        pts.append("%.1f,%.1f" % (x, y0 + r.rng(-h * 0.10, h * 0.05)))
    pts.append("%.0f,%.0f" % (w, h))
    out.append('<polygon points="%s" fill="#0b0b13"/>' % " ".join(pts))
    return "\n  ".join(out)


def _foreground(r, w, h):
    """Near-black mass across the bottom with a hot rim on its leading edge."""
    y0 = h * 0.78
    pts = ["0,%.0f" % h, "0,%.1f" % (y0 + r.rng(0, h * 0.06))]
    edge = []
    x = 0.0
    while x < w:
        x += r.rng(w * 0.10, w * 0.22)
        yy = y0 + r.rng(-h * 0.09, h * 0.04)
        pts.append("%.1f,%.1f" % (x, yy))
        edge.append("%.1f,%.1f" % (x, yy))
    pts.append("%.0f,%.0f" % (w, h))
    return ('<polygon points="%s" fill="#06060a"/>\n  '
            '<polyline points="%s" fill="none" stroke="url(#rimH)" stroke-width="%.1f" opacity="0.75"/>'
            % (" ".join(pts), " ".join(edge), max(1.2, h / 340.0)))


def scene(uid, kind, hue, w, h, seed, label=None, heat=(0.62, 0.44), ha=0.85, hb=0.28, logo=None):
    """A full Ashfall composition at any aspect ratio. When `logo` (a data-URI)
    is supplied, the real game mark sits in the upper field over the glow and
    the mono caption is dropped."""
    r = Rng(seed)
    hx, hy = heat
    depth = _depth(r, w, h, hue).replace("hazeH", "haze" + uid)
    fore = _foreground(r, w, h).replace("rimH", "rim" + uid)
    mono = "ui-monospace, SFMono-Regular, Menlo, monospace"
    cap = ""
    overlay = ""
    if logo:
        bw = w * 0.46
        bh = h * 0.34
        lx = (w - bw) / 2
        ly = h * 0.19
        blur = max(4, w // 90)
        # Whiten every logo to one pale silhouette (Ashfall keeps a single hot
        # colour; a neutral mark fits and stays legible whatever its native
        # colours), with an ember glow bloomed behind it.
        overlay = f"""<filter id="lw{uid}" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">
    <feColorMatrix type="matrix" values="0 0 0 0 0.97  0 0 0 0 0.95  0 0 0 0 0.90  0 0 0 1 0"/>
  </filter>
  <filter id="lg{uid}" x="-60%" y="-60%" width="220%" height="220%" color-interpolation-filters="sRGB">
    <feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 0.5  0 0 0 0 0.16  0 0 0 0.85 0"/>
    <feGaussianBlur stdDeviation="{blur}"/>
  </filter>
  <image href="{logo}" x="{lx:.0f}" y="{ly + 8:.0f}" width="{bw:.0f}" height="{bh:.0f}" preserveAspectRatio="xMidYMid meet" filter="url(#lg{uid})"/>
  <image href="{logo}" x="{lx:.0f}" y="{ly:.0f}" width="{bw:.0f}" height="{bh:.0f}" preserveAspectRatio="xMidYMid meet" filter="url(#lw{uid})"/>"""
    elif label:
        cap = (f'<text x="{w * 0.035:.0f}" y="{h - h * 0.055:.0f}" font-family="{mono}" '
               f'font-size="{max(9, w // 78)}" letter-spacing="{max(2, w // 260)}" '
               f'fill="#ffffff" fill-opacity="0.30">{label}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<defs>{_defs(uid, hue, w, h, ha, hb)}</defs>
  <rect width="{w}" height="{h}" fill="url(#sky{uid})"/>
  <ellipse cx="{w * hx:.0f}" cy="{h * hy:.0f}" rx="{w * 0.30:.0f}" ry="{h * 0.34:.0f}" fill="url(#heat{uid})" filter="url(#blur{uid})"/>
  <ellipse cx="{w * 0.14:.0f}" cy="{h * 0.88:.0f}" rx="{w * 0.30:.0f}" ry="{h * 0.36:.0f}" fill="url(#cold{uid})" filter="url(#blur{uid})"/>
  {depth}
  {_motif(kind, r, w, h, hue)}
  {fore}
  {_sparks(r, w, h)}
  <rect width="{w}" height="{h}" fill="url(#scan{uid})"/>
  <rect width="{w}" height="{h}" fill="url(#vig{uid})"/>
  <rect width="{w}" height="{h}" fill="url(#scrim{uid})"/>
  <rect width="{w}" height="{h}" filter="url(#grain{uid})" opacity="0.15" style="mix-blend-mode:overlay"/>
  {overlay}
  {cap}
</svg>
"""


# ── public generators ─────────────────────────────────────────────────────
def keyart(slug, name, w=1200, h=700):
    """Tile art: the heat sits lower and drifts per title so six tiles in one
    mosaic don't read as the same picture six times."""
    kind, hue = MOTIFS[slug]
    r = Rng(seed_of(slug + "heat"))
    heat = (r.rng(0.42, 0.80), r.rng(0.26, 0.46))
    lg = logo_uri(slug)
    # a real logo carries the branding, so pull the heat centre behind it
    if lg:
        heat = (0.5, 0.32)
    return scene("k" + slug.replace("-", ""), kind, hue, w, h, seed_of(slug),
                 label=name.upper(), heat=heat, ha=0.72, hb=0.24, logo=lg)


def hero(w=1600, h=900):
    return scene("hero", "ridges", 18, w, h, seed_of("ashfall-hero"), heat=(0.64, 0.36))


def closing(w=1600, h=460):
    return scene("cta", "shards", 12, w, h, seed_of("ashfall-closing"), heat=(0.76, 0.55))


def avatar(handle, hue, size=240):
    """Booster portrait: rim-lit silhouette, circle-crop safe."""
    r = Rng(seed_of(handle))
    uid = "a" + "".join(ch for ch in handle if ch.isalnum())
    s = size
    head_y = s * 0.40
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<defs>
  <linearGradient id="bg{uid}" x1="0" y1="0" x2="0.6" y2="1">
    <stop offset="0" stop-color="hsl({hue},30%,13%)"/><stop offset="1" stop-color="#08080e"/>
  </linearGradient>
  <radialGradient id="rim{uid}" cx="0.74" cy="0.3" r="0.62">
    <stop offset="0" stop-color="{EMBER}" stop-opacity="0.75"/>
    <stop offset="1" stop-color="{EMBER}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="lit{uid}" x1="1" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{AMBER}" stop-opacity="0.9"/>
    <stop offset="0.55" stop-color="{EMBER}" stop-opacity="0.25"/>
    <stop offset="1" stop-color="{EMBER}" stop-opacity="0"/>
  </linearGradient>
  <filter id="g{uid}"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3"/></filter>
</defs>
  <rect width="{s}" height="{s}" fill="url(#bg{uid})"/>
  <rect width="{s}" height="{s}" fill="url(#rim{uid})"/>
  <path d="M{s * -0.06} {s * 1.02} C{s * -0.02} {s * 0.74}, {s * 0.24} {s * 0.62}, {s * 0.44} {s * 0.60}
           L{s * 0.62} {s * 0.60} C{s * 0.84} {s * 0.64}, {s * 1.04} {s * 0.76}, {s * 1.08} {s * 1.02} Z"
        fill="#07070d"/>
  <path d="M{s * 0.30} {s * 0.40} C{s * 0.30} {s * 0.17}, {s * 0.70} {s * 0.15}, {s * 0.69} {s * 0.40}
           C{s * 0.69} {s * 0.58}, {s * 0.60} {s * 0.66}, {s * 0.49} {s * 0.66}
           C{s * 0.38} {s * 0.66}, {s * 0.30} {s * 0.57}, {s * 0.30} {s * 0.40} Z" fill="#07070d"/>
  <path d="M{s * 0.29} {s * 0.38} C{s * 0.31} {s * 0.14}, {s * 0.72} {s * 0.13}, {s * 0.70} {s * 0.34}
           C{s * 0.63} {s * 0.26}, {s * 0.44} {s * 0.24}, {s * 0.35} {s * 0.33} Z" fill="#0b0b13"/>
  <path d="M{s * 0.69} {s * 0.28} C{s * 0.72} {s * 0.40}, {s * 0.68} {s * 0.58}, {s * 0.55} {s * 0.65}"
        fill="none" stroke="url(#lit{uid})" stroke-width="{s * 0.032}" stroke-linecap="round"/>
  <path d="M{s * 0.66} {s * 0.62} C{s * 0.86} {s * 0.68}, {s * 1.02} {s * 0.80}, {s * 1.06} {s * 1.0}"
        fill="none" stroke="url(#lit{uid})" stroke-width="{s * 0.026}"/>
  <path d="M{s * 0.32} {s * 0.44} C{s * 0.30} {s * 0.56}, {s * 0.34} {s * 0.62}, {s * 0.40} {s * 0.65}"
        fill="none" stroke="{EMBER}" stroke-opacity="0.35" stroke-width="{s * 0.014}"/>
  <circle cx="{s * r.rng(0.2, 0.8):.0f}" cy="{s * r.rng(0.15, 0.5):.0f}" r="1.6" fill="{PALE}" fill-opacity="0.8"/>
  <circle cx="{s * r.rng(0.2, 0.8):.0f}" cy="{s * r.rng(0.15, 0.5):.0f}" r="1.2" fill="{AMBER}" fill-opacity="0.7"/>
  <rect width="{s}" height="{s}" filter="url(#g{uid})" opacity="0.12" style="mix-blend-mode:overlay"/>
</svg>
"""


def emblem(slug, short, size=160):
    """Per-game mark for the feed thumbnails and list rows. Uses the real game
    logo (whitened) when one is present in assets-in/_logos/, else an original
    abstract glyph."""
    kind, hue = MOTIFS[slug]
    r = Rng(seed_of(slug + "emblem"))
    uid = "e" + slug.replace("-", "")
    s = size
    c = s / 2.0
    lg = logo_uri(slug)
    if lg:
        b = s * 0.66
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<defs>
  <linearGradient id="b{uid}" x1="0" y1="0" x2="0.7" y2="1">
    <stop offset="0" stop-color="hsl({hue},26%,12%)"/><stop offset="1" stop-color="#07070d"/>
  </linearGradient>
  <filter id="lw{uid}" color-interpolation-filters="sRGB">
    <feColorMatrix type="matrix" values="0 0 0 0 0.97  0 0 0 0 0.95  0 0 0 0 0.90  0 0 0 1 0"/>
  </filter>
</defs>
  <rect width="{s}" height="{s}" fill="url(#b{uid})"/>
  <circle cx="{s * 0.78:.0f}" cy="{s * 0.2:.0f}" r="{s * 0.42:.0f}" fill="{EMBER}" fill-opacity="0.18"/>
  <image href="{lg}" x="{(s - b) / 2:.0f}" y="{(s - b) / 2:.0f}" width="{b:.0f}" height="{b:.0f}" preserveAspectRatio="xMidYMid meet" filter="url(#lw{uid})"/>
</svg>
"""
    marks = {
        "arcs": f'<path d="M{c - s * 0.2} {c + s * 0.14} A{s * 0.2} {s * 0.2} 0 0 1 {c + s * 0.2} {c + s * 0.14}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.055}"/><path d="M{c} {c - s * 0.2} L{c} {c + s * 0.14}" stroke="url(#h{uid})" stroke-width="{s * 0.055}"/>',
        "shards": f'<path d="M{c} {c - s * 0.22} L{c + s * 0.2} {c + s * 0.2} L{c} {c + s * 0.07} L{c - s * 0.2} {c + s * 0.2} Z" fill="url(#h{uid})"/>',
        "grid": f'<circle cx="{c}" cy="{c}" r="{s * 0.17}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.045}"/><path d="M{c} {c - s * 0.26} L{c} {c - s * 0.09} M{c} {c + s * 0.09} L{c} {c + s * 0.26} M{c - s * 0.26} {c} L{c - s * 0.09} {c} M{c + s * 0.09} {c} L{c + s * 0.26} {c}" stroke="url(#h{uid})" stroke-width="{s * 0.045}"/>',
        "hex": f'<polygon points="{c},{c - s * 0.22} {c + s * 0.19},{c - s * 0.11} {c + s * 0.19},{c + s * 0.11} {c},{c + s * 0.22} {c - s * 0.19},{c + s * 0.11} {c - s * 0.19},{c - s * 0.11}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.05}"/>',
        "burst": "".join(f'<line x1="{c}" y1="{c}" x2="{c + math.cos(i * math.pi / 4) * s * 0.24:.1f}" y2="{c + math.sin(i * math.pi / 4) * s * 0.24:.1f}" stroke="url(#h{uid})" stroke-width="{s * 0.04}"/>' for i in range(8)),
        "ridges": f'<path d="M{c - s * 0.26} {c + s * 0.16} L{c - s * 0.08} {c - s * 0.16} L{c + s * 0.04} {c + s * 0.02} L{c + s * 0.14} {c - s * 0.1} L{c + s * 0.26} {c + s * 0.16} Z" fill="url(#h{uid})"/>',
        "chevrons": f'<path d="M{c - s * 0.2} {c + s * 0.04} L{c} {c - s * 0.18} L{c + s * 0.2} {c + s * 0.04}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.055}"/><path d="M{c - s * 0.2} {c + s * 0.2} L{c} {c - s * 0.02} L{c + s * 0.2} {c + s * 0.2}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.055}" opacity="0.5"/>',
        "rings": f'<circle cx="{c}" cy="{c}" r="{s * 0.22}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.05}"/><circle cx="{c}" cy="{c}" r="{s * 0.08}" fill="url(#h{uid})"/>',
        "field": f'<circle cx="{c}" cy="{c}" r="{s * 0.2}" fill="none" stroke="url(#h{uid})" stroke-width="{s * 0.05}"/><path d="M{c - s * 0.2} {c} L{c + s * 0.2} {c}" stroke="url(#h{uid})" stroke-width="{s * 0.05}"/>',
    }
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<defs>
  <linearGradient id="h{uid}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="#ff3d0f"/>
  </linearGradient>
  <linearGradient id="b{uid}" x1="0" y1="0" x2="0.7" y2="1">
    <stop offset="0" stop-color="hsl({hue},26%,12%)"/><stop offset="1" stop-color="#07070d"/>
  </linearGradient>
  <filter id="g{uid}"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3"/></filter>
</defs>
  <rect width="{s}" height="{s}" fill="url(#b{uid})"/>
  <circle cx="{s * 0.78:.0f}" cy="{s * 0.2:.0f}" r="{s * 0.34:.0f}" fill="{EMBER}" fill-opacity="0.16"/>
  {marks.get(kind, "")}
  <text x="{s * 0.5}" y="{s * 0.87}" text-anchor="middle" font-family="ui-monospace, Menlo, monospace"
        font-size="{s * 0.085:.0f}" letter-spacing="{s * 0.02:.1f}" fill="#ffffff" fill-opacity="0.42">{short.upper()}</text>
  <rect width="{s}" height="{s}" filter="url(#g{uid})" opacity="0.1" style="mix-blend-mode:overlay"/>
</svg>
"""


def favicon():
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <defs><linearGradient id="f" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="#ff3d0f"/></linearGradient></defs>
  <rect width="32" height="32" rx="3" fill="{BG}"/>
  <path d="M11 5 L23 9.8 L18.4 27 L13.2 20.6 Z" fill="url(#f)"/>
</svg>
"""


def dashboard(w=1000, h=750):
    """Order-tracking UI illustration — stands in for the real screenshot."""
    r = Rng(seed_of("dashboard"))
    rows = []
    y = 300
    for i, (res, kda, lp) in enumerate([("WIN", "11 / 2 / 9", "+24"), ("WIN", "7 / 4 / 14", "+22"),
                                        ("LOSS", "3 / 6 / 7", "−18"), ("WIN", "15 / 3 / 5", "+25"),
                                        ("WIN", "9 / 1 / 11", "+21")]):
        col = AMBER if lp.startswith("+") else "#8b8b99"
        rows.append(f"""<g>
    <rect x="40" y="{y}" width="{w - 80}" height="52" fill="#0e0e16" stroke="#ffffff" stroke-opacity="0.06"/>
    <rect x="56" y="{y + 14}" width="24" height="24" rx="2" fill="hsl({(i * 37 + 18) % 360},28%,16%)"/>
    <text x="94" y="{y + 31}" font-family="ui-monospace, Menlo, monospace" font-size="13" fill="#f4f1ec">RANKED SOLO</text>
    <text x="{w * 0.42:.0f}" y="{y + 31}" font-family="ui-monospace, Menlo, monospace" font-size="13" fill="{col}">{res}</text>
    <text x="{w * 0.58:.0f}" y="{y + 31}" font-family="ui-monospace, Menlo, monospace" font-size="13" fill="#9a9aad">{kda}</text>
    <text x="{w - 66:.0f}" y="{y + 31}" text-anchor="end" font-family="ui-monospace, Menlo, monospace" font-size="14" fill="{col}">{lp}</text>
  </g>""")
        y += 60

    spark = " ".join("%.0f,%.0f" % (40 + i * ((w - 80) / 11.0), 236 - (i * 8) - r.rng(0, 26)) for i in range(12))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<defs>
  <linearGradient id="dh" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{AMBER}"/><stop offset="1" stop-color="#ff3d0f"/>
  </linearGradient>
  <filter id="dg"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3"/></filter>
</defs>
  <rect width="{w}" height="{h}" fill="#08080e"/>
  <circle cx="{w * 0.85:.0f}" cy="60" r="220" fill="{EMBER}" fill-opacity="0.10"/>
  <text x="40" y="56" font-family="ui-monospace, Menlo, monospace" font-size="12" letter-spacing="4" fill="{HOT}">ORDER ESB-3F92K1 — IN PROGRESS</text>
  <text x="40" y="112" font-family="Impact, system-ui, sans-serif" font-size="44" fill="#f4f1ec">GOLD → DIAMOND</text>
  <rect x="40" y="140" width="{w - 80}" height="8" rx="1" fill="#12121c"/>
  <rect x="40" y="140" width="{(w - 80) * 0.62:.0f}" height="8" rx="1" fill="url(#dh)"/>
  <text x="40" y="176" font-family="ui-monospace, Menlo, monospace" font-size="12" letter-spacing="3" fill="#9a9aad">PLATINUM II · 62 LP · 62% COMPLETE · 2 DAYS LEFT</text>
  <polyline points="{spark}" fill="none" stroke="url(#dh)" stroke-width="2.5"/>
  <text x="40" y="278" font-family="ui-monospace, Menlo, monospace" font-size="11" letter-spacing="3" fill="#8b8b99">MATCH HISTORY</text>
  {"".join(rows)}
  <rect width="{w}" height="{h}" filter="url(#dg)" opacity="0.09" style="mix-blend-mode:overlay"/>
</svg>
"""


def og(w=1200, h=630):
    base = scene("og", "ridges", 16, w, h, seed_of("og"), heat=(0.7, 0.34))
    overlay = f"""  <text x="72" y="330" font-family="Chakra Petch, Impact, system-ui, sans-serif" font-size="86" font-weight="700"
        letter-spacing="-2" fill="#f4f1ec">THE RANK IS YOURS.</text>
  <text x="72" y="424" font-family="Chakra Petch, Impact, system-ui, sans-serif" font-size="86" font-weight="700"
        letter-spacing="-2" fill="{EMBER}">THE GRIND ISN'T.</text>
  <text x="72" y="492" font-family="ui-monospace, Menlo, monospace" font-size="21" letter-spacing="5"
        fill="#a8a5b2">VERIFIED BOOSTERS — 9 GAMES — NO ACCOUNT NEEDED</text>
  <text x="72" y="112" font-family="Chakra Petch, Impact, system-ui, sans-serif" font-size="30" font-weight="700"
        letter-spacing="1" fill="#f4f1ec">ESPORTS<tspan fill="{EMBER}">BOOST</tspan></text>
</svg>
"""
    return base.replace("</svg>\n", overlay)
