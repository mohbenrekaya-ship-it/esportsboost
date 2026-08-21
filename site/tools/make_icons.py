#!/usr/bin/env python3
"""Rasterise the site's own mark into the icon files crawlers and phones need.

    python3 site/tools/make_icons.py

Writes, all from `art.favicon()` / `art.og()` so nothing here is a second
drawing of the brand:

    site/public/favicon.ico          16 + 32 + 48 + 64, root-served
    site/public/apple-touch-icon.png 180x180, full bleed
    site/public/icon-512.png         512x512, the schema.org Organization logo
    site/assets-in/og.png            1200x630, picked up by build.py's place()

WHY THIS EXISTS. The site shipped an SVG favicon and nothing else. Google Search
reads `<link rel="icon">` but also probes the root `/favicon.ico` on its own
schedule — ours was a 404, so the only path to a refresh was a full page crawl,
and Google's favicon cache is separate from Googlebot's and far slower. The
result was the redesign's title and description live in the SERP for days while
the *previous* site's logo stayed next to them. A real .ico at the root is the
one signal that does not wait for a page crawl.

The og:image was an SVG too, which X, Facebook, LinkedIn, Discord and Slack all
refuse — every link to the site previewed with no image at all.

WHY IT IS A TOOL AND NOT PART OF build.py. Vercel's build command is a bare
`python3 site/build.py` with no dependency install, so the build stays stdlib
only (see CLAUDE.md). This needs Pillow and a headless Chrome. It runs on a
developer's machine, its output is committed under site/public/, and
`.vercelignore` keeps site/tools/ out of the deploy entirely.

Re-run it whenever `art.favicon()` or `art.og()` changes. It renders the real
SVG rather than re-drawing the geometry, so the icons cannot drift from the mark
the pages paint.

Developer script — never part of a build or a deploy.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SITE, "src"))

import art  # noqa: E402

try:
    from PIL import Image
except ImportError:
    sys.exit("needs Pillow:  python3 -m pip install Pillow")

PUBLIC = os.path.join(SITE, "public")
ASSETS_IN = os.path.join(SITE, "assets-in")

# The card behind the mark. Same value as art.BG and as the pages' theme-color,
# restated here only because it is used to flatten the rounded corners away.
PLATE = (6, 6, 10, 255)

CHROME = os.environ.get("CHROME") or (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

WRAP = """<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;padding:0;background:transparent}
svg{display:block;width:100vw;height:100vh}</style>
%s"""


def render(svg, w, h, scale=2):
    """Screenshot one SVG through headless Chrome at `scale`x and return it.

    The SVG is wrapped in a page and stretched to the viewport rather than
    screenshotted as a document: Chrome sizes a bare SVG document off its own
    width/height attributes, so favicon.svg would come back 32x32 whatever
    --window-size said.
    """
    if not os.path.exists(CHROME):
        sys.exit("no Chrome at %s — set $CHROME to the binary" % CHROME)
    tmp = tempfile.mkdtemp(prefix="esb-icons-")
    try:
        page = os.path.join(tmp, "p.html")
        shot = os.path.join(tmp, "shot.png")
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(WRAP % svg)
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--force-device-scale-factor=%d" % scale,
               "--default-background-color=00000000",
               "--window-size=%d,%d" % (w, h),
               "--screenshot=" + shot, "file://" + page]
        run = subprocess.run(cmd, capture_output=True)
        if not os.path.isfile(shot):
            sys.exit("chrome failed:\n" + run.stderr.decode("utf-8", "replace")[-2000:])
        with open(shot, "rb") as fh:
            return Image.open(io.BytesIO(fh.read())).convert("RGBA")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def down(im, size):
    return im.resize((size, size), Image.LANCZOS)


def flatten(im):
    """Drop the mark onto an opaque square of the same plate colour.

    iOS and Android both apply their own mask to a touch icon, and Google draws
    the Organization logo on its own ground — a shape that is already rounded
    gets rounded twice and reads as a sticker. The corners go, the mark does not
    move.
    """
    plate = Image.new("RGBA", im.size, PLATE)
    plate.alpha_composite(im)
    return plate


def save_png(im, path):
    im.save(path, "PNG", optimize=True)
    print("  %-42s %s" % (os.path.relpath(path, os.path.dirname(SITE)),
                          "%dx%d" % im.size))


def main():
    os.makedirs(PUBLIC, exist_ok=True)
    os.makedirs(ASSETS_IN, exist_ok=True)

    print("favicon — art.favicon()")
    master = render(art.favicon(), 512, 512, scale=2)      # 1024 square

    # One .ico rather than an .ico plus a PNG link: the whole point of the root
    # .ico is that it is the path Google probes WITHOUT being told, so a second
    # rel="icon" only adds a choice for it to make. 64 is in there because the
    # SERP draws the icon at up to 64px, and the raster path should not have to
    # upscale a 48 if the SVG is ever declined. Pillow resamples each entry from
    # the master it is handed, so it is handed a 256 that was itself LANCZOS'd
    # down from 1024.
    ico = os.path.join(PUBLIC, "favicon.ico")
    down(master, 256).save(ico, "ICO",
                           sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("  %-42s %s" % ("site/public/favicon.ico", "16+32+48+64"))

    save_png(flatten(down(master, 180)), os.path.join(PUBLIC, "apple-touch-icon.png"))
    save_png(flatten(down(master, 512)), os.path.join(PUBLIC, "icon-512.png"))

    print("og:image — art.og()")
    og = render(art.og(), 1200, 630, scale=2).resize((1200, 630), Image.LANCZOS)
    og.convert("RGB").save(os.path.join(ASSETS_IN, "og.png"), "PNG", optimize=True)
    print("  %-42s %s" % ("site/assets-in/og.png", "1200x630"))

    print("\ndone — now run: python3 site/build.py")


if __name__ == "__main__":
    main()
