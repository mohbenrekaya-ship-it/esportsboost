# 5 video ads — League of Legends, English, 9:16

Built with the Enevie pipeline ported into `site/tools/films/`: a HyperFrames project per
film (HTML + CSS + GSAP) rendered to 1080×1920 MP4, against **one ElevenLabs take timed to
the word**. The spoken lines live in `films/scripts.py`; this file is what the films are
allowed to claim and why each one looks the way it does.

## The rule the first attempt broke

The first five films were five variations of **big type centred on black**, and that is
one idea shown five times. A format here is a **place** — a lock screen, a scoreboard, the
product's own screen, a calendar, a deck of cards — and the film **moves between places**.
One scene held from start to finish is refused.

The three beats never change: **"Do you play League of Legends, or something similar?"** →
the player who is stuck → eSports Boost.

## The five

| # | Film | The place | The angle |
| --- | --- | --- | --- |
| 1 | `notifications` | a phone at 2 a.m. | the lock screen filling with LP losses, then the one notification worth waiting for |
| 2 | `scoreboard` | a post-game scoreboard | you vs the grind: it wins three rows out of three, until a Master player joins your side |
| 3 | `order-screen` | the product's own screen | how it actually works: pick two ranks, see the price before you pay, watch the climb |
| 4 | `one-month` | a month on a calendar | 28 nights crossed out for nothing, against one day |
| 5 | `myths` | three cards turned over | two things people believe are false — and the third is **true**, said in amber |

Film 5 is the one that argues against itself on purpose: boosting *is* against the game's
terms, the card says TRUE, and the film answers with the VPN and the play window rather
than selling past it. Same standard as the three FAQ answers on the site that argue
against the sale.

## The figures these films may use

Read from `site/src/pricing.py` at build time, and **checked against the spoken line** —
`check_prices()` fails the build if a price moves, because the voice spells numbers out
("twenty-five dollars") and cannot be patched. A re-price means rewriting the line in
`scripts.py` and re-recording.

| Claim | Value | Source |
| --- | --- | --- |
| One division | **from $4** | `service_floor()` |
| Silver IV → Gold IV | **$25** | `quote()` |
| Gold IV → Platinum IV | **$36** | `quote()` |
| Delivery, one division | **about 1 day** | `eta_text()` |
| Watch your booster play | **free** | `ADDONS['stream']` |
| Money back until a booster is assigned · Pause anytime · VPN matched to your region | policy | `GUARANTEES_INLINE` |

⚠ **Never used, in any film:** the review score, the review count, the client count, the
booster count and every booster's rank — invented placeholders (see *Placeholder data* in
CLAUDE.md). An ad is the one surface where that stops being a to-do and becomes a false
advertising claim. The end card carries the three signed-off guarantees and no rating.

**The sale** is "Winter sale · SPLIT15 · ends 31 Jan" on the site; no film names a window,
so none of them goes stale on 1 February.

## Production rules carried over from the Enevie brief

1. **8–12 shots of 2–3 s**, camera moves and transitions 0.8–1 s on soft curves. No whip,
   no flash, no brutal zoom — 15–20 shots of 1.5 s reads as too fast.
2. **The film moves from place to place.** A single scene, however well shot, is refused.
3. ⚠ **No sound on a transition** — no whoosh, ever. Small cues only on the elements that
   appear (pop, tap, ding, check, sparkle, soft boom), plus a light riser at 0 s.
4. **Every on-screen word means something.** No decorative labels.
5. **Frame 0 is the thumbnail**: a title and a visual are already on screen at 0 s.
6. **Reels safe zone**: anything to be read sits between y=180 and y=1550.
7. **The close**: logo, gradient button, chevrons pointing down at the platform's own
   button, ~2.7 s of hold after the last word.

## Still open

⚠ **`streams.py` does not exist**, so "watch your booster play" is a promise a person
keeps by hand. Film 3 shows the live dashboard and says you watch the climb — which the
order page already does — but it does **not** sell the screen share. The film that did was
dropped for exactly that reason. Build the seam or keep the promise manually before any
film goes further than this.
