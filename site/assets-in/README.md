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

Booster handles: `vantaa kx_reid sable orvo nine petrichor mera cobalt_ix
halden tsuro`

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
