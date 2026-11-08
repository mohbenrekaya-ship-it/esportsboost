# 13 video ads — English, 9:16 (two batches)

Built with the Enevie pipeline ported into `site/tools/films/`: a HyperFrames project per
film (HTML + CSS + GSAP) rendered to 1080×1920 MP4, against **one ElevenLabs take timed to
the word**. The spoken lines live in `films/scripts.py`; this file is what the films are
allowed to claim and why each one looks the way it does.

## The rule the first attempt broke

The first five films were five variations of **big type centred on black**, and that is
one idea shown five times. A format here is a **place** — a lock screen, a scoreboard, the
product's own screen, a calendar, a deck of cards — and the film **moves between places**.
One scene held from start to finish is refused.

There are **two batches**, and they open differently on purpose.

**Films 1–8, the LEAGUE batch.** Three beats: **"Do you play League of Legends?"** → the
player who is stuck → eSports Boost. The hook is that sentence and nothing else; these
sell one ladder, against a League keyword.

**Films 9–13, the CATALOGUE batch** (2026-11-08). They sell the shop, so the hook names
it: **"Do you play League of Legends, Valorant, or any other ranked game?"** The spine is
the business's own —

> hook → **stuck in your rank** → **teammates who waste your time and energy** → at
> eSports Boost there are **two ways out**: we duo queue beside you, or we take the
> account to the rank you want **while you sleep or watch your favourite series** → and
> **you watch your booster play, live, on your phone.**

…and then the CTA, spoken last in all five: **"Click the link below and get your
desired rank today."** The end card is built to it — the lockup lands on the brand line,
the guarantee fills the gap, and the button plus "Click the link below" arrive with the
words. The eight League films keep their own closes.

Every one of the five states that arc. What changes is the place it is staged in, and
which of the two ways leads. ⚠ **None of the five quotes a price** — that was the call
with them — so `prices` is empty and the guard that matters is the one that fails a build
if the take says any figure the script did not declare.

## The thirteen

| # | Film | The place | The angle | Climb | Says |
| --- | --- | --- | --- | --- | --- |
| 1 | `notifications` | a phone at 2 a.m. | the lock screen filling with LP losses, then the one notification worth waiting for | Gold IV | — |
| 2 | `scoreboard` | a post-game scoreboard | you vs the grind: it wins three rows out of three, until a Master player joins your side | Gold → Platinum | $36 |
| 3 | `order-screen` | the product's own screen | how it actually works: pick two ranks, see the price before you pay, watch the climb | Platinum → Emerald | $57 |
| 4 | `one-month` | a month on a calendar | 28 nights crossed out for nothing, against one day | Emerald → Diamond | $91 |
| 5 | `myths` | three cards turned over | two things people believe are false — and the third is **true**, said in amber | one division | from $4 |
| 6 | `placements` | a 5-game placement tracker | four losses set the season; won placements open it above where you ended | placements ×5 | $16 |
| 7 | `duo` | a party screen with an open slot | your friends queue two divisions up and you get dodged; the booster takes the fourth seat beside you | Gold → Platinum, Duo | $56 |
| 8 | `five-wins` | the LP bar and a promo series | you don't need a rank, you need the five games you keep dropping | net wins ×1 | $3 a win |
| 9 | `teammates` | a post-game scoreboard | four strangers, one of them leaves; then a Master takes the open seat beside you | — | — |
| 10 | `asleep` | one phone, one night | 23:40 stuck → asleep → 02:10, the booster's game live → 07:10, four divisions up | — | — |
| 11 | `series` | a streaming app | the trade: you watch the season you wanted, your rank climbs on the other screen | — | — |
| 12 | `hours` | a season's ledger | 300 hours, 400 games, 0 divisions — then the two ways out | — | — |
| 13 | `two-ways` | two lanes | duo on your team, or solo while you sleep; one handset either way | — | — |

Film 5 is the one that argues against itself on purpose: boosting *is* against the game's
terms, the card says TRUE, and the film answers with the VPN and the play window rather
than selling past it. Same standard as the three FAQ answers on the site that argue
against the sale.

⚠ **No two films quote the same climb or the same price.** The ladder runs Iron to Master
and the engine prices every rung of it; five films all closing on "Silver to Gold,
twenty-five dollars" is one ad shown five times, and it tells a Platinum player the shop
is not for him. Films 6, 7 and 8 also sell a **product** rather than a division — net
wins, placements and duo are three of the four things the configurator offers and none of
them had an ad.

## The figures these films may use

Read from `site/src/pricing.py` at build time, and **checked against the spoken line** —
`check_prices()` fails the build if a price moves, because the voice spells numbers out
("twenty-five dollars") and cannot be patched. A re-price means rewriting the line in
`scripts.py` and re-recording.

| Claim | Value | Source |
| --- | --- | --- |
| One division | **from $4** | `service_floor()` |
| Gold IV → Platinum IV | **$36** | `quote()` |
| Platinum IV → Emerald IV | **$57** | `quote()` |
| Emerald IV → Diamond IV | **$91** | `quote()` |
| Gold IV → Platinum IV, Duo | **$56** | `quote()` |
| 5 placement games from Gold IV | **$16** | `quote()` |
| 1 net win from Gold IV | **$3** | `quote()` |
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
8. **The lockup is the site's own** — the ember shard beside `esports` + `boost`, in
   **Inter**, self-hosted per film under `assets/fonts/`. An ad's logo is the one element
   that has to match the page the click lands on.
9. ⚠ **A card sized for N rows is a hole until the Nth arrives.** Rows rest faint and
   light up, or the empty seat is given a meaning (the dashed "+ OPEN SLOT").
10. ⚠ **`W("word")` takes the FIRST match unless it is floored**, and the catalogue hook
   contains "play", "game", "you" and "other" — an unfloored `W("game")` lands at 3.6 s,
   in the title, not where it was written for.
11. ⚠ **Nothing is rewritten by a GSAP `.call()`.** The renderer seeks frame by frame, so a
   callback that mutates text fires on playback and not on a seek. Every variant ships in
   the DOM and is opacity-flipped — and two states sharing one slot must **replace** each
   other, the outgoing one leaving before the incoming one arrives, or a frame catches
   both and reads as a double exposure.

## Still open

⚠ **`streams.py` does not exist, and films 9–13 CLOSE on it.** All five end on "watch
your booster play, live, from your phone" — nothing opens a Discord channel and nothing
tells a booster to share a screen, so every order those ads win is a promise ops keeps by
hand. That was tolerable while the screen share was one row in a picker. It is the
headline now. Build the seam or pull the close. The claim is also written as a fact about
us and never as a comparison, because "nobody else gives you this" is falsifiable by any
one competitor and is what `D.STREAM_CLAIM_VERIFIED = False` holds back.

⚠ **The older note, kept:** "watch your booster play" is a promise a person
keeps by hand. Film 3 shows the live dashboard and says you watch the climb — which the
order page already does — but it does **not** sell the screen share. The film that did was
dropped for exactly that reason. Build the seam or keep the promise manually before any
film goes further than this.
