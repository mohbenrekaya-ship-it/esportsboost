# Meta ads — the catalogue batch (films 9–13), English

Copy for the five 9:16 films in `site/assets-out/videos/9…13`. One set per film, so the
text and the video open on the same thought — a Reel whose caption argues something else
reads as two ads stacked.

**Placement note.** These are vertical video for Reels and Stories, where Meta shows the
**primary text truncated to roughly 125 characters** and frequently drops the headline and
description entirely. So every primary text below is written to land whole inside that
limit, and the headline is written to work if it never appears.

⚠ **What this copy may NOT say, and why.** The same rule the films follow: the review
score, the review count, the client count and the roster size in `data.py` are invented
placeholders (see *Placeholder data* in CLAUDE.md), and an ad is where a placeholder stops
being a to-do and becomes a false advertising claim. No "4.8/5", no "13,000 customers", no
"78 boosters". No prices either — the catalogue five deliberately quote none, and a price
in the caption over a video that quotes none is the one thing a viewer can catch.
No comparative claim ("nobody else", "the only site") — that is
`D.STREAM_CLAIM_VERIFIED = False`, and it is falsifiable by any one competitor.

⚠ **"Watch your booster play" is a manual ops promise.** `streams.py` does not exist. It
is in the copy because it is in the films; it is honoured by a person opening a Discord
channel by hand on every order that mentions it. See *Watch live* in CLAUDE.md.

⚠ **Expect rejections, and do not escalate by rewording.** Meta reviews game-boosting
against its Circumventing Systems and Unrealistic Outcomes policies, and account services
are refused more often than they are approved. If a set is rejected, the fix is an appeal
with the guarantee page as context, not a softer synonym for "boost" — a reworded
resubmission of a refused ad is what gets an account restricted.

---

## 9 · `teammates` — four strangers

- **Primary** — Four strangers every game, and one of them decides it in the first ten minutes. Stop queueing with strangers.
- **Headline** — Duo with a Master player
- **Description** — Money back until a booster takes it
- **Button** — Learn more

## 10 · `asleep` — while you sleep

- **Primary** — Still in the rank you were stuck in last season? Sleep through the climb instead, and wake up where you were playing to get.
- **Headline** — Rank up while you sleep
- **Description** — Watch it live from your phone
- **Button** — Learn more

## 11 · `series` — watch something else

- **Primary** — Here's the trade. You watch the season you actually wanted to watch, and a verified booster climbs your account while you do.
- **Headline** — Get your evenings back
- **Description** — Pause it whenever you like
- **Button** — Learn more

## 12 · `hours` — what it cost you

- **Primary** — A season of 300 hours and 400 games, and the same rank you started on. Most of them lost by someone who left at minute four.
- **Headline** — Two ways out of the grind
- **Description** — Duo with us, or while you sleep
- **Button** — Learn more

## 13 · `two-ways` — two ways out

- **Primary** — Ranked is four strangers and a coin flip. Two ways out: a Master on your team, or we climb it while you sleep.
- **Headline** — Pick your rank, we climb it
- **Description** — Money back until a booster takes it
- **Button** — Learn more

---

## Evergreen, for any of the five

Use when testing creative against a single caption rather than pairing one to one.

- Your rank isn't a skill problem. It's a teammate problem.
- Stuck in your rank because of four strangers a game? There is a way out of that.
- Two ways out: we duo beside you, or we climb it while you sleep. You watch either one, live.
- You don't need more hours. You need the games you keep losing to someone who left.

## What every set may claim, because the site is held to it

These are the signed-off commitments in `GUARANTEES_INLINE` and `SAFETY`, and each is
falsifiable by one bad order — so they are the only promises the copy makes:

- Money back until a booster takes the order
- Pause it whenever you like
- Played on a VPN matched to your own region, in your normal hours
- Duo orders never touch your login at all

⚠ **"In your normal hours", never "the hours you set"** — the control behind that second
phrasing was removed from checkout on 2026-09-09 and five strings on the site were changed
with it. Copy that reintroduces it promises a field that no longer exists.

## Still to do

- **fr / de.** The site ships both and the films are English only. A French or German set
  needs the register `i18n.js` uses — `tu` in the shop, `vous` in the policy copy — not a
  translation of the above.
- **The League batch (films 1–8) needs its own sets.** Those quote prices, so their copy
  can too, and every figure has to be re-checked against `pricing.py` the day it is written
  — the same reason `check_prices()` exists. ⚠ `marketing/gads-lol-boosting-us-ca.md` still
  carries "Bundles Up To 37% Off" and bundles are off the storefront; do not copy that line
  into Meta, and fix it in the Ads account.
