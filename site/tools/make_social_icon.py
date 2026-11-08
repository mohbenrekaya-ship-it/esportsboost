#!/usr/bin/env python3
"""The brand mark as a square profile picture, for Instagram / Meta / X / Discord.

    <venv-with-Pillow> python3 site/tools/make_social_icon.py

Writes into site/assets-out/brand/:

    esportsboost-icon-1080.png       the profile picture — mark on the site ground
    esportsboost-icon-512.png        the same, for anywhere that caps smaller
    esportsboost-mark-1080.png       the mark alone, transparent, to place yourself

WHY NOT JUST USE site/public/icon-512.png. That one exists for crawlers and
phones: it is the favicon geometry at full bleed, drawn to be legible at 16px in
a browser tab. A social profile is CROPPED TO A CIRCLE and displayed at ~110px,
so the corners are thrown away and a mark sized for a square reads as a cropped
shape rather than a logo. This set sizes the mark to 60% of the canvas, which
puts its whole diagonal comfortably inside the inscribed circle, and centres it
on its own bounding box rather than on the favicon's 32-unit grid — where it
sits a unit right of centre, invisible at 16px and obvious at 1080.

⚠ THE GEOMETRY IS READ FROM art.favicon(), NEVER RE-DRAWN. The site has one
mark; a second copy of these four points is how the profile picture and the
favicon come to be slightly different shapes. The gradient is `.shard`'s own
(#ffb046 -> #ff3d0f, top to bottom), the ground is art.BG.

Developer script — never part of a build or a deploy.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SITE, "src"))

import art  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("needs Pillow:  python3 -m pip install Pillow")

OUT = os.path.join(SITE, "assets-out", "brand")
FILL = 0.60          # the mark's height as a share of the canvas
TOP, BOT = (0xFF, 0xB0, 0x46), (0xFF, 0x3D, 0x0F)     # .shard's gradient stops


def mark_points():
    """The four points of the shard, read out of art.favicon()'s path."""
    svg = art.favicon()
    d = re.search(r'<path d="([^"]+)"', svg).group(1)
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    pts = list(zip(nums[0::2], nums[1::2]))
    assert len(pts) == 4, pts
    return pts


def render(size, ground):
    pts = mark_points()
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = (size * FILL) / h                       # scale so the HEIGHT fills FILL
    # centre on the mark's own box, not on the favicon's grid — the path sits a
    # unit right of centre there, which is invisible at 16px and obvious at 1080
    ox = (size - w * k) / 2.0 - min(xs) * k
    oy = (size - h * k) / 2.0 - min(ys) * k
    poly = [(x * k + ox, y * k + oy) for x, y in pts]

    img = Image.new("RGBA", (size, size), ground)
    grad = Image.new("RGBA", (size, size))
    g = ImageDraw.Draw(grad)
    for y in range(size):                        # linear-gradient(#ffb046, #ff3d0f)
        t = y / float(size - 1)
        g.line([(0, y), (size, y)],
               fill=tuple(int(round(a + (b - a) * t)) for a, b in zip(TOP, BOT)) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    bg = tuple(int(art.BG[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    for name, size, ground in (("esportsboost-icon-1080.png", 1080, bg),
                               ("esportsboost-icon-512.png", 512, bg),
                               ("esportsboost-mark-1080.png", 1080, (0, 0, 0, 0))):
        p = os.path.join(OUT, name)
        render(size, ground).save(p)
        print("->", os.path.relpath(p, SITE), "%dx%d" % (size, size))


if __name__ == "__main__":
    main()
