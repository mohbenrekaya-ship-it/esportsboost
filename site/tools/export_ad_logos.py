#!/usr/bin/env python3
"""Export esportsboost.com's real logo as Google Ads logo assets.

    python3 site/tools/export_ad_logos.py

Sources are the production site's own files, fetched once and cached in
`tools/.assetcache/`:

  * `/icon0.svg`      — a Figma export: an SVG wrapper around a 1024x1024 PNG.
                        The embedded PNG is lifted out byte-for-byte and used as
                        the square master. This is the favicon.
  * `/mainLogo.webp`  — the 959x159 header lockup (eagle + wordmark), used as
                        the landscape master.

NOTE: this is deliberately *not* `site/`'s own favicon. `site/` is the redesign
prototype and `art.favicon()` draws an ember shard that is nothing like the live
brand. Ads have to carry the mark customers actually see.

Google's image-asset spec for logos:

    ratio  minimum     recommended   max file size   formats
    1:1    128 x 128   1200 x 1200   5120 KB         PNG, JPG, static GIF
    4:1    512 x 128   1200 x 300    5120 KB         PNG, JPG, static GIF

Nothing here is ever upscaled — every asset is at or below its source's native
resolution, so no fake detail is invented. That means the 1:1 tops out at the
master's native 1024x1024 rather than the recommended 1200; 1024 is 8x the
minimum and Google accepts it without complaint.

Developer script — never part of a build or a deploy. Output goes to
`site/assets-out/google-ads/`, outside `dist/`, which `build.py` wipes.
"""

import base64
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import urllib.request
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from png_probe import read_rgba  # noqa: E402  — shares the stdlib PNG reader

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "assets-out" / "google-ads"
CACHE = ROOT / "tools" / ".assetcache"

SQUARE_SRC = "https://esportsboost.com/icon0.svg"
LANDSCAPE_SRC = "https://www.esportsboost.com/mainLogo.webp"

# The live site's body background: rgb(1, 3, 0). Used for the opaque variants so
# the logo sits on the same ground it does on the site.
BRAND_BG = (1, 3, 0)


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def fetch(url, name):
    path = CACHE / name
    if not path.exists():
        print(f"  fetching {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            path.write_bytes(r.read())
    return path


def png_from_svg_wrapper(svg_path, out_path):
    """Lift the embedded PNG out of a Figma-style <image href="data:..."> SVG.
    Byte-for-byte — no re-encode, so the master is exactly what ships."""
    s = svg_path.read_text(errors="replace")
    m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", s)
    if not m:
        raise SystemExit(f"{svg_path.name}: no embedded PNG found")
    out_path.write_bytes(base64.b64decode(m.group(1)))
    return out_path


def webp_to_png(src, out_path):
    subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(out_path)],
                   check=True, capture_output=True)
    return out_path


# --------------------------------------------------------------------------
# Pixels. Rows are flat bytearrays of RGBA, which keeps the 1024x1024 composite
# fast enough in pure Python.
# --------------------------------------------------------------------------
def load(path):
    w, h, rows = read_rgba(path)
    return w, h, [bytearray(b for px in row for b in px) for row in rows]


def trim(w, h, rows, thresh=8):
    """Crop away transparent edges. The header lockup ships with 9px of padding
    on the left and 1px on the right; centring the file rather than the artwork
    would leave the logo off-axis in the ad slot. The threshold discards fringe
    under ~3% alpha, which carries no visible ink at any size."""
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = rows[y]
        for x in range(w):
            if row[x * 4 + 3] > thresh:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if x1 < 0:
        return w, h, rows
    return x1 - x0 + 1, y1 - y0 + 1, [bytearray(r[x0 * 4:(x1 + 1) * 4]) for r in rows[y0:y1 + 1]]


def canvas(w, h, bg):
    """`bg` is None for transparent, or an (r, g, b) laid down opaque."""
    px = bytes((0, 0, 0, 0)) if bg is None else bytes((*bg, 255))
    return [bytearray(px * w) for _ in range(h)]


def paste(dst, dw, dh, src, sw, sh, x, y):
    """Source-over composite of `src` onto `dst` at (x, y)."""
    for j in range(sh):
        ty = y + j
        if not 0 <= ty < dh:
            continue
        drow, srow = dst[ty], src[j]
        for i in range(sw):
            tx = x + i
            if not 0 <= tx < dw:
                continue
            a = srow[i * 4 + 3]
            if a == 0:
                continue
            d, s = tx * 4, i * 4
            if a == 255:
                drow[d:d + 4] = srow[s:s + 4]
            else:
                inv = 255 - a
                for c in range(3):
                    drow[d + c] = (srow[s + c] * a + drow[d + c] * inv + 127) // 255
                drow[d + 3] = a + (drow[d + 3] * inv + 127) // 255
    return dst


def write_png(path, w, h, rows):
    """Encode 8-bit RGBA. Sub filter: these logos are wide flat runs, which Sub
    turns into long zero stretches for zlib."""
    raw = bytearray()
    for row in rows:
        out = bytearray(len(row))
        out[:4] = row[:4]
        for i in range(4, len(row)):
            out[i] = (row[i] - row[i - 4]) & 255
        raw += b"\x01" + out

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    pathlib.Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b""))


def downscale(src, dst, w, h):
    shutil.copyfile(src, dst)
    subprocess.run(["sips", "-z", str(h), str(w), str(dst)], check=True, capture_output=True)


def probe(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "hasAlpha",
                          str(path)], check=True, capture_output=True, text=True).stdout
    g = dict(l.strip().split(": ", 1) for l in out.splitlines() if ": " in l)
    return int(g["pixelWidth"]), int(g["pixelHeight"]), g.get("hasAlpha") == "yes"


# --------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    print("sources")
    sq_master = png_from_svg_wrapper(fetch(SQUARE_SRC, "icon0.svg"), CACHE / "square-master.png")
    ls_master = webp_to_png(fetch(LANDSCAPE_SRC, "mainLogo.webp"), CACHE / "landscape-master.png")

    sw, sh, sq = load(sq_master)
    lw0, lh0, ls0 = load(ls_master)
    lw, lh, ls = trim(lw0, lh0, ls0)
    print(f"  square master    {sw} x {sh}")
    print(f"  landscape master {lw0} x {lh0}  → {lw} x {lh} trimmed")
    if sw != sh:
        raise SystemExit(f"square master is not 1:1 ({sw}x{sh})")

    print(f"→ {OUT}")
    made = []

    def emit(name, w, h, rows):
        p = OUT / name
        write_png(p, w, h, rows)
        made.append((p, w, h))
        return p

    # ---- 1:1 -------------------------------------------------------------
    # The mark is a circle already inscribed in its square, so Google's circle
    # crop lands exactly on the artwork edge — nothing to inset.
    sq_alpha = emit(f"logo-1x1-{sw}.png", sw, sh, paste(canvas(sw, sh, None), sw, sh, sq, sw, sh, 0, 0))
    sq_solid = emit(f"logo-1x1-{sw}-solid.png", sw, sh,
                    paste(canvas(sw, sh, BRAND_BG), sw, sh, sq, sw, sh, 0, 0))

    # ---- 4:1 -------------------------------------------------------------
    # The lockup is placed at native size and centred: 959 of 1200 wide leaves a
    # 10% side margin, and no pixel is stretched.
    LW, LH = 1200, 300
    if lw > LW or lh > LH:
        raise SystemExit(f"landscape master {lw}x{lh} does not fit {LW}x{LH} without upscaling")
    x, y = (LW - lw) // 2, (LH - lh) // 2
    ls_solid = emit("logo-4x1-1200x300-solid.png", LW, LH,
                    paste(canvas(LW, LH, BRAND_BG), LW, LH, ls, lw, lh, x, y))
    emit("logo-4x1-1200x300-transparent-dark-bg-only.png", LW, LH,
         paste(canvas(LW, LH, None), LW, LH, ls, lw, lh, x, y))

    # ---- downscales ------------------------------------------------------
    for name, src, w, h in [
        ("logo-1x1-512.png",       sq_alpha, 512, 512),
        ("logo-1x1-256.png",       sq_alpha, 256, 256),
        ("logo-1x1-128.png",       sq_alpha, 128, 128),
        ("logo-1x1-512-solid.png", sq_solid, 512, 512),
        ("logo-4x1-512x128.png",   ls_solid, 512, 128),
    ]:
        downscale(src, OUT / name, w, h)
        made.append((OUT / name, w, h))

    ok = True
    for path, want_w, want_h in sorted(made, key=lambda m: m[0].name):
        w, h, alpha = probe(path)
        kb = path.stat().st_size / 1024
        bad = []
        if (w, h) != (want_w, want_h):
            bad.append(f"expected {want_w}x{want_h}")
        if kb > 5120:
            bad.append("over 5120 KB")
        if w == h and w < 128:
            bad.append("below the 1:1 minimum")
        if w != h and (w < 512 or h < 128):
            bad.append("below the 4:1 minimum")
        ok = ok and not bad
        note = ("  ** " + "; ".join(bad) + " **") if bad else ""
        print(f"  {path.name:46s} {w:>4} x {h:<4} {'alpha' if alpha else 'opaque':6s} {kb:7.1f} KB{note}")
    if not ok:
        raise SystemExit("some assets failed their checks")


if __name__ == "__main__":
    main()
