# Drop real assets here

Anything in this folder **overrides** the generated artwork on the next
`python3 site/build.py`. No code change, no layout change — the build rewrites
every `<img src>` and every `og:image` to the file you dropped, whatever its
extension (`.jpg .jpeg .png .webp .avif .svg`).

```
assets-in/
  keyart/<game-slug>.jpg        mosaic tiles, game-page hero, game cards, og:image
  emblem/<game-slug>.png        live-feed thumbnails, game-list rows
  avatar/<booster-handle>.jpg   roster rows
  hero.jpg                      homepage hero, 1440×800, dark, high contrast
  closing.jpg                   closing band, 1440×400, wide
  portrait.jpg                  hero portrait, square, circle-cropped to 232px
  dashboard.png                 order-tracking screenshot, 4:3
  og.png                        default social card, 1200×630
```

Game slugs: `league-of-legends valorant counter-strike-2 teamfight-tactics
marvel-rivals dota-2 apex-legends overwatch-2 rocket-league`

Booster handles: every `handle` in `data.py`'s `BOOSTERS` (78 today).

## What is already in `avatar/`

All 78 slots are filled: one **Bottts** robot per handle, generated from that
handle as the seed and downloaded once from DiceBear's API. They are *vendored*
— the built site serves them from `/assets/img/avatar-<handle>.svg` and makes no
request to dicebear.com at runtime.

    https://api.dicebear.com/10.x/bottts/svg?seed=<handle>

Bottts is by Pablo Stanley (https://bottts.com/), "free for personal and
commercial use"; each file carries that statement in its own `<metadata>` block,
so don't strip it when optimising. Re-run the URL above to regenerate one, or
drop a real photograph over it — the ring around it is unchanged either way.

**Only `avatar/`, deliberately not `portrait/`.** These read as characters at
38px and as cartoons at 96px, so the profile header and the home hero's
spotlight keep the generated rim-lit portrait. Dropping the same files into
`portrait/<handle>` would put a robot in both.

## Framing

Every tile crops with `object-fit: cover` under a bottom-heavy scrim, per the
handoff:

- **Game tiles** — keep the subject out of the bottom 30%; the title, service
  list and `FROM $NN` sit there.
- **Hero** — keep the subject out of the left 40% and right of centre (~62%
  across). It reads behind a heavy left scrim and the docked calculator.
- Dark, high-contrast source images. The page's ember glow, grain and scanlines
  composite *over* whatever lands here, so anything bright or busy fights them.

## Licensing

Official game key art, logos and character art are the publishers' trademarks
and copyright — Riot, Valve, NetEase, Blizzard, EA, Psyonix. They are not
mine to fetch, and a boosting service will not get them licensed. What goes
here has to be art you own, art you commissioned, or stock you hold a licence
for. The generated fallbacks exist so the site never looks broken while you
sort that out.

---

## Fonts — vendored, not hot-linked

`site/public/assets/fonts/` holds the site's two typefaces as woff2, served
first-party. They are **not** an `assets-in/` drop-in slot: they are committed
build inputs, copied to `dist/` like any other asset.

| Family | Weights | Ranges | Used for |
| --- | --- | --- | --- |
| Inter | 400, 500, 600, 700 | latin, latin-ext | `--display` and `--body` — nearly all text |
| IBM Plex Mono | 400, 500 | latin, latin-ext | `--mono` — kickers and spec labels |

Both are **SIL Open Font License 1.1**, which permits redistribution — that is
what makes vendoring them legitimate rather than a copy of someone's CDN.

They used to load from Google Fonts via `@import`. That was replaced because it
sent every visitor's IP to a third party before first paint (the analytics
pipeline is deliberately anonymous so the site stays out of consent-banner
territory — a font request gave that away for nothing), and because `@import`
inside a stylesheet is the slowest possible way to load a face: fetch the CSS,
parse it, discover Google's CSS, fetch that, parse it, *then* start the woff2.

`ashfall.css` still `@import`s Chakra Petch + IBM Plex Sans + IBM Plex Mono. It
is the vendored design system and is not edited (CLAUDE.md), so **`build.py`
strips any remote `@import` from `dist/` at build time**. The first two were
already dead weight — `type-b-sans.css` overrides `--display`/`--body` with
Inter, so they were downloaded and never painted.

To refresh or add a weight (needs network; `latin` covers French and German —
`latin-ext` is only for Central/Eastern European and is fetched lazily via
`unicode-range`, so adding it costs nothing until a page needs it):

```bash
curl -s -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0" \
  "https://fonts.googleapis.com/css?family=Inter:400,500,600,700&subset=latin,latin-ext"
```

Then download each `fonts.gstatic.com` URL in the response to
`inter-<weight>-<range>.woff2` and copy the matching `unicode-range` into the
`@font-face` blocks in `type-b-sans.css`. Use the **v1** API as above: the
`css2?family=…` endpoint hands back URLs that 404 outside a browser session.
After adding a weight, check the two `<link rel="preload">` tags in `build.py`'s
`layout()` still name the faces used above the fold (400 and 600 today).
