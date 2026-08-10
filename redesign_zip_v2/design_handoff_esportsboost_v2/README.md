# Handoff v2: eSports Boost — "Ashfall" immersive homepage

Supersedes `design_handoff_esportsboost_homepage/` (v1, which covered two Nocturne-based directions). This is the direction to build. v1 stays useful only as a record of the alternatives and of the shared pricing model.

## Overview

A single-page marketing homepage for a game-boosting marketplace. Its job is to get a competitive player from landing to a configured order without an account: the price calculator is docked into the bottom of the hero and is the primary conversion surface. Trust is carried by live proof — a today's-deliveries feed, an on-shift booster roster, verified reviews — rather than by badges.

Audience is competitive players chasing rank for real stakes plus repeat customers. Copy tone is blunt and gamer-native; carry it verbatim.

Design width **1440px**, desktop-first, dark.

## About the design files

The files in this bundle are **design references created in HTML** — a prototype showing intended look and behavior, not production code to lift. The HTML runs on a small in-house streaming-component runtime that will not exist in the target repo.

Recreate this design in the target codebase's existing environment (React, Vue, Svelte, Next.js…) using its established patterns, router and styling approach. If nothing exists yet: this page is one interactive island (the calculator) on otherwise static content — **Next.js (App Router) or Astro + a React island** are both right. Server-render everything except the calculator.

Carry over verbatim: all copy, the pricing formula, the exact token values, the layout measurements, and the motion specs below.

## Fidelity

**High-fidelity** for layout, type, color, spacing and motion — build it pixel-accurately.

**Not final: the imagery.** Every image position in the prototype is a drop-in placeholder component, empty until someone fills it. The design assumes real key art and photography; the procedural ember/noise/scanline layers under the images are part of the design and must survive once real art lands (they composite over it). See *Assets*.

**Not final: the content.** The game list and every statistic are placeholders. Only League of Legends was verifiable from the current site. Trustpilot (4.8/5, 3,140 reviews), 92,400 boosts, 41,000 Discord members, 18-minute median claim, the 100% recovery-rate claim, all five booster profiles, all four feed entries and all three reviews are invented. Replace before launch and wire the live ones to real sources (Trustpilot API, orders table, Discord widget, roster service). **The 100% recovery-rate line and the safety copy are marketing claims about your operations — get them checked before shipping.**

## Aesthetic direction

Named "Ashfall". Near-black ground, a single hot ember gradient as the only saturated element, condensed uppercase display type against neutral humanist body text, and monospace for every micro-label (kickers, section numbers, timestamps, stats). Nothing is decorative: the heat marks the one action on each screenful.

Rules of the direction, to hold while you build:

- **One hot color.** The ember gradient (`#ffb046 → #ff3d0f`) appears on primary buttons, active states, section kickers and the hero glow. Nothing else is saturated. Never use it as a large flat fill — it is always a gradient, a 1px border, a small mark, or a blurred atmospheric glow.
- **Panels are near-black, not grey.** `#0e0e16` on `#06060a`, separated by 1px `rgba(255,255,255,.08)` borders. No drop shadows anywhere except the ember bloom under primary buttons.
- **Square-ish corners.** 2–3px radius on everything (buttons, panels, chips). Circles only for avatars and dots.
- **Display type is uppercase and tight** — `letter-spacing: -0.02em`, `line-height: 0.94`. Body copy is normal case at `line-height: 1.6–1.75`.
- **Micro-labels are monospace, small, wide** — 9–10px at `letter-spacing: .14em–.3em`. They do the structural work (`01 / GAMES`, `2M AGO`, `VERIFIED ORDER · LOL · EUW`).
- **Atmosphere is procedural, layered under content**: a drifting multi-radial glow, an SVG `feTurbulence` grain, 1px scanlines, and directional scrims. All `pointer-events: none`.

## Typography

Google Fonts, weights as listed — load these three and nothing else:

| Role | Family | Weights | Used for |
| --- | --- | --- | --- |
| Display | **Chakra Petch** | 600, 700 | h1/h2/h3, buttons, stat values, names, rank chips — always `text-transform: uppercase` |
| Body | **IBM Plex Sans** | 400, 500 | paragraphs, list copy, review text |
| Mono | **IBM Plex Mono** | 400, 500 | kickers, section numbers, timestamps, footer, marquee, stat labels |

Base body: 15px / 1.6. Headings: `font-weight: 700`, `line-height: 0.94`, `letter-spacing: -0.02em`, uppercase.

Type scale as used:

| Element | Size | Notes |
| --- | --- | --- |
| Hero h1 | **108px** | `letter-spacing: -0.035em`; two lines, second line gradient-filled |
| Closing h2 | 76px | `max-width: 22ch` |
| Section h2 (Games) | 60px | two lines |
| Section h2 (Live, Reviews) | 52px | |
| Stat values | 44px | `line-height: 0.9` |
| Calculator price | 40px | `line-height: 0.9` |
| Big mosaic tile title | 34px | |
| Safety h3 | 30px | |
| "+ 3 more" | 30px | `line-height: 0.95` |
| Brand wordmark | 19px | |
| Hero body / section lead | 17px | `max-width: 52ch`, color `#c9c6c0` |
| Safety body | 14.5px | `line-height: 1.75`, `max-width: 68ch` |
| Body small / review text | 14px | `line-height: 1.7`, `#d8d5cf` |
| Nav links, meta | 13px | `letter-spacing: .04em` |
| Card meta, captions | 11–12px | `#9a9aad` |
| Mono micro-labels | 9–10px | `letter-spacing: .14em–.3em` |

The hero's second line is gradient text: `background: linear-gradient(96deg, #ffd39a, #ff4a1f 62%)` + `background-clip: text` + `color: transparent`. Keep a solid `#f4f1ec` fallback for browsers without it.

## Color tokens

| Name | Value | Use |
| --- | --- | --- |
| `--bg` | `#06060a` | page ground |
| `--bg-2` | `#08080d` | footer |
| `--bg-3` | `#0a0a11` | marquee strip, roster panel |
| `--panel` | `#0e0e16` | cards, feed rows, calculator body |
| `--glass` | `rgba(14,14,20,.78)` + `backdrop-filter: blur(18px)` | the docked calculator |
| `--nav-glass` | `rgba(6,6,10,.72)` + `blur(14px)` | nav bar |
| `--text` | `#f4f1ec` | primary text |
| `--text-2` | `#d8d5cf` | review copy |
| `--text-3` | `#c9c6c0` | body paragraphs |
| `--text-4` | `#a8a5b2` | secondary meta |
| `--text-5` | `#9a9aad` | tertiary meta, inactive nav |
| `--text-6` | `#8b8b99` | mono labels, inactive chips |
| `--text-7` | `#6f6f80` | footer, timestamps, utility bar |
| `--ember` | `#ff4a1f` | the accent — borders, dots, marquee diamonds |
| `--ember-lit` | `#ff6a3d` | links |
| `--amber` | `#ffb046` | gradient stop, win-rate figures |
| `--amber-pale` | `#ffd39a` | gradient text stop |
| `--ember-grad` | `linear-gradient(100deg, #ffb046, #ff3d0f)` | primary buttons, active chips |
| `--hairline` | `rgba(255,255,255,.08)` | panel borders, section rules |
| `--hairline-2` | `rgba(255,255,255,.07)` | nav/utility/footer rules |
| `--hairline-3` | `rgba(255,255,255,.12)` | inactive chip borders, nav divider |
| `--violet-deep` | `rgba(58,32,120,.5)` | the cold counterweight inside the hero glow only |

Hover on primary buttons: `filter: brightness(1.12)`. Focus: build a visible ring — `outline: 2px solid #ff6a3d; outline-offset: 2px` — the prototype relies on browser defaults and that is a gap to close.

## Layout & sections

Page gutter is **40px** left/right throughout. Sections in order:

### 1. Utility bar
`padding: 9px 40px`, 1px bottom hairline-2, mono 10px `letter-spacing: .18em`, `#6f6f80`. Three items, space-between: regions (`EUW · EUNE · NA · LAN · KR · SEA · OCE`), a live line in `#ff6a3d` (`34 BOOSTERS ON SHIFT — MEDIAN CLAIM 18 MIN`), then `USD ▾  EN ▾`.

### 2. Nav
`display:flex; gap:34px; padding:18px 40px`, glass background, 1px bottom hairline-2. Brand at left with `margin-right:auto`: an 11×22px ember-gradient shard (`clip-path: polygon(0 0, 100% 18%, 62% 100%, 18% 62%)`) then "esports" + "boost" in `#ff4a1f`, Chakra Petch 700 19px uppercase. Links: Games (active, `#f4f1ec`), Live, Boosters, Safety, Reviews (`#9a9aad`), 1px×18px divider, "Sign in", then the ember-gradient CTA "Start an order" (mono-ish Chakra Petch 600 12px, `letter-spacing:.12em`, `padding:11px 20px`, radius 2px). Make it sticky in production.

### 3. Hero — 800px tall, `overflow:hidden`, `isolation:isolate`
Stack, bottom to top:
1. **z0** — full-bleed image slot (`1440×800`, dark, high contrast).
2. **z1** — the drifting glow: `inset:-12%`, `mix-blend-mode:screen`, `animation: drift 26s ease-in-out infinite`, and three radials — `38% 42% at 62% 34%` `rgba(255,77,28,.62)`, `30% 34% at 78% 62%` `rgba(255,176,70,.34)`, `46% 50% at 22% 78%` `rgba(58,32,120,.5)`.
3. **z2** — grain: inline SVG `feTurbulence` (`type=fractalNoise, baseFrequency=0.8, numOctaves=3`, 180×180 tile) at `opacity:.11`, `mix-blend-mode:overlay`.
4. **z2** — scanlines: `repeating-linear-gradient(to bottom, rgba(255,255,255,.028) 0 1px, transparent 1px 4px)`.
5. **z2** — scrims: `linear-gradient(to right, rgba(6,6,10,.94) 0%, rgba(6,6,10,.72) 42%, rgba(6,6,10,.18) 70%, rgba(6,6,10,.86) 100%)` over `linear-gradient(to top, #06060a 2%, transparent 46%)`.
6. **z2** — four ember sparks at `left:34%; bottom:120px`: 3–5px dots in `#ff8a4c / #ffb046 / #ff5a24 / #ffd39a`, each `box-shadow: 0 0 9–14px 3–4px` of its own color at ~.6 alpha, `animation: rise` at 7s / 9s / 11s / 8.5s with 0 / 1.4s / 3.1s / 2.2s delays.
7. **z3** — content: grid `1fr 400px`, `align-items:center`, `padding: 0 40px 90px`, `pointer-events:none` on the container with `pointer-events:auto` restored on the button rows. Left: mono kicker `VERIFIED BOOSTERS — 9 GAMES — SINCE 2019` in `#ff8a4c`, h1 108px ("The rank is yours." / gradient "The grind isn't."), 17px lead, two CTAs (ember-gradient primary with `box-shadow: 0 0 44px rgba(255,74,31,.34)`; outlined secondary `1px rgba(255,255,255,.22)`). Right, justified end: a 232px circular image slot ringed by a blurred `conic-gradient(from 210deg, rgba(255,176,70,.9), rgba(255,61,15,.15) 55%, rgba(255,176,70,.9))` at `inset:-14px; filter:blur(16px); opacity:.6`, with the booster caption under it.

### 4. Calculator — docked, `position:absolute; left:40px; right:40px; bottom:26px; z:4`
Glass panel, 1px `rgba(255,255,255,.1)`, radius 3px, `padding:18px 20px`, three rows at `gap:14px`:
- **Row 1** — mono kicker `PRICE CALCULATOR — NO ACCOUNT NEEDED` in `#ff8a4c` (left) and 9 game chips, right-justified, wrapping (mono 10px, `padding:6px 10px`, radius 2px; active = ember border + `rgba(255,74,31,.14)` fill + `#ffd9c9`; inactive = hairline-3 border + `#8b8b99`).
- **Row 2** — the rank ladder: `display:flex; gap:4px`, one equal chip per tier (`flex:1`), each `padding:11px 4px`, radius 2px, tier name in Chakra Petch 600 12px uppercase over an 8px mono state tag (`YOU` / `TARGET`), `transition: background .15s, border-color .15s`. Three states:
  - **endpoint** — `1px #ff4a1f`, `background: linear-gradient(160deg, rgba(255,176,70,.28), rgba(255,61,15,.18))`, text `#ffe9dc`.
  - **in range** — `1px rgba(255,74,31,.45)`, `background: rgba(255,74,31,.09)`, text `#f4f1ec`.
  - **idle** — `1px rgba(255,255,255,.12)`, transparent, text `#8b8b99`.
- **Row 3** — 1px top hairline, `padding-top:14px`: left group at `gap:34px` — summary (mono 10px `#8b8b99`) over price (Chakra Petch 700 40px), `DELIVERED IN` over ETA (19px), then the Piloted / Duo-queue toggle (two spans inside a 1px hairline-3 box, radius 2px, active one filled with the ember gradient and `#06060a` text). Right: ember-gradient "Continue".

In production: the ladder chips must be real `<button>`s inside a `role="group"`, arrow-key navigable, with `aria-pressed` on the endpoints; the game chips likewise. Keep the whole calculator keyboard-reachable — it is the conversion surface.

### 5. Marquee
`background:#0a0a11`, hairline-2 top and bottom, `padding:11px 0`, `overflow:hidden`. Inside, a `width:max-content` flex row with the item list duplicated twice and `animation: marquee 38s linear infinite` (translateX 0 → -50%). Items are mono 10px `letter-spacing:.24em` `#6f6f80` separated by `◆` in `#ff4a1f`: 92,400 boosts delivered / 4.8 / 5 on Trustpilot — 3,140 reviews / 18 min median time to a claimed order / 41,000 players in the Discord / 100% recovery rate on account reviews. Pause it on `prefers-reduced-motion` and on hover.

### 6. Games — `padding: 88px 40px 20px`
Header: left, mono `01 / GAMES` + h2 60px "Nine ladders. / Forty services."; right, a right-aligned 14px `#9a9aad` paragraph at `max-width:40ch`.

Mosaic: `grid-template-columns: repeat(4, 1fr); grid-auto-rows: 208px; gap: 12px`. Seven cells:

| Cell | Span | Title size |
| --- | --- | --- |
| League of Legends | 2 × 2 | 34px |
| Valorant | 2 × 1 | 18px |
| Counter-Strike 2 | 1 × 1 | 18px |
| Marvel Rivals | 1 × 1 | 18px |
| Dota 2 | 2 × 1 | 18px |
| Teamfight Tactics | 1 × 1 | 18px |
| "+ 3 more" (Apex, Overwatch 2, Rocket League) | 1 × 1 | 30px, no image |

Each image cell: `position:relative; overflow:hidden`, image slot at the base, then (all `pointer-events:none`) a `linear-gradient(to top, rgba(6,6,10,.95) 4%, rgba(6,6,10,.35) 46%, rgba(6,6,10,.08) 100%)` scrim, a 1px `rgba(255,255,255,.08)` inset border, a mono index (`01`…`06`) at `top:14px; left:16px` in `rgba(255,255,255,.62)`, and a bottom block at `left/right:16px; bottom:14px` with title, 11px service list `#a8a5b2`, and `FROM $NN` in mono `#ff8a4c`. The "+ 3 more" cell is a 1px hairline-3 box with `linear-gradient(150deg, rgba(255,74,31,.1), transparent 70%)`.

Add a hover state the prototype lacks: scale the image ~1.03 and lift the scrim slightly, 200ms ease.

### 7. Stat band — `margin-top:74px; padding:34px 40px`
`linear-gradient(100deg, rgba(255,74,31,.14), rgba(58,32,120,.2) 60%, transparent)` over `#0a0a11`, hairline top and bottom. Grid `repeat(4,1fr); gap:24px`. Each: value Chakra Petch 700 44px `line-height:.9`, then a mono 10px `letter-spacing:.18em` `#a8a5b2` label 6px below. 92,400 / 4.8 / 5 / 18 MIN / 41,000.

### 8. Live + roster — `padding: 84px 40px 0`, grid `1fr 420px`, `gap:56px`, `align-items:start`
**Left column** (`gap:26px`):
- mono `02 / LIVE` + h2 52px "Delivered today".
- Feed: grid `repeat(2,1fr); gap:12px`, four cards. Each card `#0e0e16`, 1px hairline, `padding:12px`, grid `78px 1fr; gap:14px; align-items:center`: a 78×78 image slot, then climb (Chakra Petch 600 15px uppercase), game+region (12px `#9a9aad`), and `TIME · BOOSTER` (mono 9px `#6f6f80`).
- Safety block, separated by a 1px hairline top and `padding-top:34px`: grid `150px 1fr; gap:30px` — mono `03 / SAFETY` in `#ff8a4c` at left, h3 30px "Why this doesn't get you banned" plus two 14.5px paragraphs at `max-width:68ch` right.

**Right column** — roster panel: `#0a0a11`, 1px hairline, `padding:22px`, `gap:14px`. Header: an 8px ember dot with `box-shadow: 0 0 0 4px rgba(255,74,31,.2)` + mono `ON SHIFT NOW — 34`. Five rows, grid `44px 1fr auto`, `padding:10px 0`, 1px bottom hairline-2: 44px circular avatar slot, handle (Chakra Petch 600 14px uppercase) over peak rank (11px `#9a9aad`), then win rate (Chakra Petch 600 14px `#ffb046`) over queue state (mono 9px `#6f6f80`). Below, a Discord card: 1px `rgba(255,74,31,.4)`, `linear-gradient(150deg, rgba(255,74,31,.12), transparent)`, `padding:16px` — "41,000 in the Discord", a 12px line, and a mono link `JOIN THE SERVER →`.

### 9. Reviews — `padding: 80px 40px 0`
Header: mono `04 / REVIEWS` + h2 52px "What they said after"; right, mono `VERIFIED ORDERS ONLY` in `#6f6f80`. Grid `repeat(3,1fr); gap:12px`. Cards `#0e0e16`, 1px hairline, `padding:22px`, `gap:12px`: mono rank-climb kicker in `#ff8a4c`, 14px/1.7 quote in `#d8d5cf`, then mono 9px meta pinned to the bottom with `margin-top:auto`.

### 10. Closing band — `margin-top:84px`, 400px tall
Same stack as the hero but simpler: full-bleed image slot, one drifting radial (`40% 60% at 76% 60%`, `rgba(255,77,28,.5)`, `drift 32s`), scrims left-to-right and bottom-up, then content at `padding: 0 40px`, vertically centered: mono uppercased live summary (e.g. `GOLD → DIAMOND · PILOTED`), h2 76px "Your climb starts at $NNN" — **the live price interpolated into the headline** — a 15px line, and two CTAs.

### 11. Footer
`padding: 30px 40px 36px`, `#08080d`, 1px top hairline-2, mono 10px `letter-spacing:.16em` `#6f6f80`. Left `© 2026 ESPORTS BOOST`; right, `gap:22px`: TERMS, REFUNDS, PRIVACY, BECOME A BOOSTER, DISCORD.

## Motion

Four keyframe animations, all decorative and all of which must be disabled under `@media (prefers-reduced-motion: reduce)` — the prototype does not do this and it is a required fix.

```css
@keyframes drift {                     /* hero + closing glow, 26s / 32s ease-in-out infinite */
  0%   { transform: translate3d(-3%, 2%, 0) scale(1.06); }
  50%  { transform: translate3d(4%, -3%, 0) scale(1.14); }
  100% { transform: translate3d(-3%, 2%, 0) scale(1.06); }
}
@keyframes rise {                      /* hero sparks, 7–11s linear infinite, staggered */
  0%   { transform: translateY(0) scale(1); opacity: 0; }
  12%  { opacity: .9; }
  100% { transform: translateY(-260px) scale(.4); opacity: 0; }
}
@keyframes marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes sweep   { from { background-position: -40% 0; } to { background-position: 140% 0; } }
```

`sweep` is declared but unused — drop it or use it for a loading shimmer.

Everything else is CSS state transitions: ladder chips `background .15s, border-color .15s`; primary buttons `filter: brightness(1.12)` on hover; the tile hover lift noted above (200ms).

Performance: the glow layers are large blurred composites. Keep them on `transform`/`opacity` only (they are), and consider `will-change: transform` on the two drifting layers. Do not add more full-bleed blurs.

## Interactions & behavior

- **Game chip click** — sets the game, resets current rank to ladder index 3 and target to `min(6, len-1)`, resets the click pointer to `"from"`, recomputes.
- **Ladder click-through** — two-click, with an explicit `next` pointer (`"from"` → `"to"` → `"from"`):
  - `next === "from"`: current = clicked tier, target = one tier above, `next = "to"`.
  - `next === "to"` and clicked tier is above current: target = clicked tier, `next = "from"`.
  - `next === "to"` and clicked tier is at or below current: restart — current = clicked tier, target = one above, `next = "to"`.
  - Clicking the **top** tier as a start sets current = second-from-top, target = top. This guard exists so the price never renders as an em dash in a 40px slot or in the closing headline.
- **Mode toggle** — Piloted (default) or Duo queue; Duo multiplies the price by 1.55.
- **Live values propagate** to two places besides the calculator: the closing band's mono kicker (uppercased summary) and its 76px headline (price). Both must re-render with calculator state.
- **Invalid pair** — unreachable through the UI given the guards above, but the model still returns `—` / `—` / "Target must sit above your current rank". Keep that path and disable `Continue` if it is ever reachable.
- **Anchors** — nav and CTAs link to `#top`, `#calc`, `#games`, `#live`, `#boosters`, `#safety`, `#reviews`. Use smooth scrolling with a sticky-nav offset.
- **Responsive** — the prototype is a fixed 1440px canvas; nothing below that is designed. Required decisions for the real build:
  - Hero h1 108px → clamp down to ~44px on mobile; hero height from 800px to ~640px.
  - The docked calculator cannot stay docked on a phone. Below ~900px, unpin it and make it its own full-width section directly under the hero, with the ladder becoming a horizontally scrollable chip row (`overflow-x:auto`, chips `min-width:76px`) or a two-select fallback below ~700px. Nine chips do not fit 390px.
  - Games mosaic 4 columns → 2 (LoL keeps a 2×2 span) → 1.
  - Stat band 4 → 2 → 1. Live+roster grid stacks, roster last. Reviews 3 → 1.
  - Booster portrait 232px → hide below ~900px rather than shrinking it; the ring loses its effect small.

## State management

One island's worth of state:

| Key | Type | Default |
| --- | --- | --- |
| `game` | string | `"League of Legends"` |
| `from` | string | `"Gold"` |
| `to` | string | `"Diamond"` |
| `mode` | `"Piloted" \| "Duo queue"` | `"Piloted"` |
| `next` | `"from" \| "to"` | `"from"` |

`pricePerDivision` is exposed as a tweakable prop (default **26**) purely for design review. In production it and the per-game factors belong in server-side pricing config.

Consider persisting `{game, from, to, mode}` to the URL as query params so a configured quote is shareable, and rehydrating the checkout from it.

**No data fetching** in the prototype. For the real page: game/ladder/pricing config server-rendered or fetched at build; the feed, roster and on-shift count are the live values.

### Pricing formula (carry over exactly, then move server-side)

```
ladder  = LADDERS[game]
i       = ladder.indexOf(from)
j       = ladder.indexOf(to)
steps   = j - i                          // <= 0 → invalid, render "—"
climb   = max(1, i - 1)                  // higher starting ranks cost more
price   = round(steps * perDivision * FACTOR[game] * (1 + climb * 0.22)
                * (mode === "Duo queue" ? 1.55 : 1))
days    = max(1, round(steps * 1.4 + climb * 0.3))
eta     = days === 1 ? "about 1 day" : `${days} days`
summary = `${from} → ${to} · ${mode}`
```

`FACTOR`: League of Legends 1.0, Valorant 1.15, Counter-Strike 2 1.45, Teamfight Tactics 0.8, Marvel Rivals 0.95, Dota 2 1.25, Apex Legends 1.1, Overwatch 2 0.9, Rocket League 0.7.

Mosaic `FROM $NN` values are `quote(game, ladder[1], ladder[2], "Piloted")` — a one-division climb off the second tier.

## Data

Ladders and service lists (placeholder except LoL — confirm before building):

| Game | Ladder tiers | Services |
| --- | --- | --- |
| League of Legends | Iron → Bronze → Silver → Gold → Platinum → Emerald → Diamond → Master → Grandmaster → Challenger | Elo boost · placements · net wins · duo · coaching |
| Valorant | Iron → Bronze → Silver → Gold → Platinum → Diamond → Ascendant → Immortal → Radiant | Rank boost · placements · unrated wins · duo |
| Counter-Strike 2 | 5k → 10k → 13k → 15k → 17k → 19k → 21k → 25k → 30k (CS Rating) | Premier rating · Faceit levels · Wingman |
| Teamfight Tactics | Iron → Bronze → Silver → Gold → Platinum → Emerald → Diamond → Master → Challenger | Rank boost · placements · double-up |
| Marvel Rivals | Bronze → Silver → Gold → Platinum → Diamond → Grandmaster → Celestial → Eternity → One Above All | Rank boost · net wins · duo · coaching |
| Dota 2 | Herald → Guardian → Crusader → Archon → Legend → Ancient → Divine → Immortal | MMR boost · calibration · net wins · duo |
| Apex Legends | Rookie → Bronze → Silver → Gold → Platinum → Diamond → Master → Predator | Rank boost · badges · kills |
| Overwatch 2 | Bronze → Silver → Gold → Platinum → Diamond → Master → Grandmaster → Champion | Rank boost · placements · net wins |
| Rocket League | Bronze → Silver → Gold → Platinum → Diamond → Champion → Grand Champ → Supersonic | Rank boost · tournament wins · duo |

Divisions (Gold IV → Gold I) and LP/RR offsets are **not** modeled — tier level only. Real pricing almost certainly needs them; treat the ladder array as the shape to extend.

## Assets

**Nothing is final.** The prototype mounts 16 drop-in slots via the bundled `image-slot.js`; a dropped file persists in a sibling `.image-slots.state.json`. That component is a **prototyping device — do not port it.** In the real build these are ordinary `<img>` / `next/image` sources.

| Slot id | Position | Needed asset |
| --- | --- | --- |
| `im-hero` | Hero, full bleed | 1440×800 dark, high-contrast key art. Must read behind heavy left and bottom scrims — subject right of center, ~62% across |
| `im-booster` | Hero right | Square portrait, 232px circle crop, dark background |
| `im-game-league-of-legends` | Mosaic 2×2 | ~700×430 key art |
| `im-game-valorant`, `im-game-dota-2` | Mosaic 2×1 | ~700×210 |
| `im-game-counter-strike-2`, `im-game-marvel-rivals`, `im-game-teamfight-tactics` | Mosaic 1×1 | ~345×210 |
| `im-feed-1…4` | Live feed | 78×78 square match/game thumbs |
| `im-b1…b5` | Roster | 44×44 square avatars |
| `im-cta` | Closing band | 1440×400 dark, wide |

Sizing note: every tile crops to `object-fit: cover` under a bottom-heavy scrim — keep subjects out of the bottom 30% of game tiles and out of the left 40% of the hero.

**Icons:** none used. The design is intentionally icon-free — resist adding them; the mono labels carry the structure. If a nav or footer genuinely needs one, use a single-weight outline set at 16px on `currentColor`.

**Logo:** the wordmark is set type plus one clipped shard, not an asset — "esports" in `#f4f1ec` + "boost" in `#ff4a1f`, Chakra Petch 700 19px uppercase, preceded by an 11×22px ember-gradient shape. Replace with the real logo if one exists.

## Accessibility gaps to close (the prototype does not handle these)

1. No `prefers-reduced-motion` handling — required for the drift, rise and marquee animations.
2. Ladder and game chips are `<span onClick>` — must become buttons with keyboard support and `aria-pressed`.
3. No visible focus ring — the design's own ember ring is specified above; implement it.
4. Contrast: `#6f6f80` on `#06060a` (footer, timestamps, utility bar) is ~4.3:1 at 9–10px — legally borderline at that size. Lift those to `#8b8b99` or raise the size to 11px.
5. The price/ETA update on chip click needs an `aria-live="polite"` region so it is announced.
6. Decorative layers need `aria-hidden="true"` alongside `pointer-events:none`.

## Files in this bundle

- `Esports Boost Immersive.dc.html` — the design. Open in a browser to interact: click game chips and rank tiers, toggle Piloted/Duo. The markup is the layout reference; the logic class at the end holds the pricing model, the ladder interaction and all placeholder data.
- `image-slot.js` — the drop-in placeholder component the design mounts. Prototyping device only; do not port.
- `v1-README.md` — the earlier handoff, covering the two superseded Nocturne-based directions. Reference only.

## Open decisions

1. **Real game list and real numbers** — blocking. See *Fidelity*.
2. **Real imagery** — blocking for the hero, the six mosaic tiles and the closing band; the page's whole effect depends on them. Everything else degrades gracefully.
3. **Divisions and LP/RR offsets** in the pricing model.
4. Downstream screens — checkout steps 2–3, per-game service pages, order dashboard — are **not designed yet**. The dashboard is referenced in copy ("watch every match land from the dashboard"), so it needs to exist.
5. Legal review of the safety and recovery-rate claims.
