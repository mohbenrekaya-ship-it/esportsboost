#!/usr/bin/env python3
"""Read a PNG and report its ink bounds. Stdlib only (zlib + struct).

Used to verify the exported ad logos: where the artwork actually lands in the
frame, and how far the farthest lit pixel sits from centre — which is what
decides whether a 1:1 logo survives Google's circle crop.

    python3 site/tools/png_probe.py site/assets-out/google-ads/*.png
"""

import math
import pathlib
import struct
import sys
import zlib


def read_rgba(path):
    """Decode a non-interlaced 8-bit PNG to (w, h, rows of RGBA tuples)."""
    buf = pathlib.Path(path).read_bytes()
    if buf[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path}: not a PNG")
    pos, idat, pal, trns = 8, bytearray(), None, None
    w = h = depth = ctype = interlace = None
    while pos < len(buf):
        (n,) = struct.unpack(">I", buf[pos:pos + 4])
        tag = buf[pos + 4:pos + 8]
        data = buf[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", data)
        elif tag == b"PLTE":
            pal = data
        elif tag == b"tRNS":
            trns = data
        elif tag == b"IDAT":
            idat += data
        elif tag == b"IEND":
            break
        pos += 12 + n
    if depth != 8 or interlace:
        raise SystemExit(f"{path}: need 8-bit non-interlaced (got depth={depth} interlace={interlace})")

    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(bytes(idat))
    stride = w * chans
    out, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - chans] if i >= chans else 0
            b = prev[i]
            c = prev[i - chans] if i >= chans else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                q = a + b - c
                pa, pb, pc = abs(q - a), abs(q - b), abs(q - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line

        row = []
        for x in range(w):
            px = line[x * chans:(x + 1) * chans]
            if ctype == 6:
                row.append(tuple(px))
            elif ctype == 2:
                row.append((px[0], px[1], px[2], 255))
            elif ctype == 4:
                row.append((px[0], px[0], px[0], px[1]))
            elif ctype == 0:
                row.append((px[0], px[0], px[0], 255))
            else:
                i = px[0]
                a = trns[i] if trns and i < len(trns) else 255
                row.append((pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2], a))
        out.append(row)
    return w, h, out


def bounds(w, h, rows, pred):
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        r = rows[y]
        for x in range(w):
            if pred(r[x]):
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return (x0, y0, x1, y1) if x1 >= 0 else None


def report(path):
    w, h, rows = read_rgba(path)
    ink = lambda p: p[3] > 8                      # noqa: E731 — anything visible
    box = bounds(w, h, rows, ink)
    corners = [rows[0][0], rows[0][w - 1], rows[h - 1][0], rows[h - 1][w - 1]]
    transparent_bg = all(c[3] == 0 for c in corners)

    print(f"{pathlib.Path(path).name}")
    print(f"  canvas      {w} x {h}   ratio {w // math.gcd(w, h)}:{h // math.gcd(w, h)}")
    print(f"  background  {'transparent' if transparent_bg else 'opaque ' + str(corners[0][:3])}")
    if not box:
        print("  artwork     none\n")
        return
    x0, y0, x1, y1 = box
    cx, cy = (w - 1) / 2, (h - 1) / 2
    print(f"  artwork     {x1 - x0 + 1} x {y1 - y0 + 1} at {x0},{y0}"
          f"   centred: dx={((x0 + x1) / 2 - cx):+.1f} dy={((y0 + y1) / 2 - cy):+.1f}")

    if w == h:
        # Distance to the farthest *visible pixel*, not to a bounding-box corner:
        # this artwork is a disc, so its bbox corners are empty and using them
        # reports a clip that will never happen.
        far = 0.0
        for y in range(h):
            r = rows[y]
            for x in range(w):
                if ink(r[x]):
                    d = math.hypot(x - cx, y - cy)
                    if d > far:
                        far = d
        pct = far / (w / 2) * 100
        # <=100% survives Google's circle crop; the artwork is a disc inscribed
        # in the square, so 100% is exactly tangent and loses nothing.
        print(f"  circle crop farthest visible pixel at {pct:.0f}% of the radius"
              f" {'✓ safe' if pct <= 100.5 else '✗ WILL CLIP'}")
    else:
        m = min(x0, w - 1 - x1, y0, h - 1 - y1)
        print(f"  margin      {m}px ({m / h * 100:.0f}% of height) on the tightest side")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    for a in args:
        report(a)
