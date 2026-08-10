# Handoff: eSports Boost homepage redesign

## Overview

A redesign of the esportsboost.com marketing homepage for a game-boosting marketplace. The page's job is to get a competitive player from landing to a configured order without an account: the rank-boost price calculator ("order wizard") is the primary conversion surface and appears above the fold, not behind a signup.

Two directions were designed. **Both are in the same file** and must be treated as alternatives — pick one before implementing (see *Screens / Views*).

The immediate task for Claude Code: **build a full preview page** — a single working page per direction, running in the target codebase's environment, with the calculator live (game + rank selection recomputing price and ETA client-side).

## About the design files

The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior. They are not production code to copy directly. The HTML uses a small in-house streaming-component runtime that will not exist in the target repo.

The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, Next.js, etc.) using its established patterns, router, component library and styling approach. If no environment exists yet, pick the most appropriate framework for a marketing site with one interactive island (Next.js or Astro + React are both reasonable) and implement there.

Do carry over verbatim: all copy, all numbers, the pricing formula, the token values, and the layout measurements below.

## Fidelity

**High-fidelity.** Colors, typography, spacing and interaction states are final and come from a bound design system (Nocturne — `nocturne.css` is included in this bundle and is the source of truth). Recreate pixel-accurately. Where the target codebase already has a button/input/card primitive, use it, but restyle it to the token values below rather than inheriting a different look.

Content caveat for the product owner, repeated here so it isn't shipped by accident: **the game list and every statistic are placeholders.** Only League of Legends was verifiable from the current site. Trustpilot score (4.8/5, 3,140 reviews), completed boosts (92,400), Discord size (41,000), median claim time (18 min), booster handles and reviews are all invented and must be replaced with real data before launch. Wire the stats to real sources (Trustpilot API, orders table, Discord widget) rather than hard-coding them.

## Screens / Views

### Direction A — "Ledger" (id `1a` in the design file)

Copy-led editorial homepage. The headline owns the left column; the wizard is a compact quote card in the right column.

**Frame:** 1280px wide content frame, `--color-bg` (#161826) ground. Page gutter 56px left/right throughout.

**Sections, top to bottom:**

1. **Nav bar** — `display:flex; align-items:center; gap:28px; padding:18px 56px`, 1px bottom border in `--color-divider`.
   - Brand "esportsboost" — Inter 500, 18px, `letter-spacing:-0.02em`; the word "boost" in `--color-accent` (#9184d9). `margin-right:auto` pushes the rest right.
   - Links: Games (current, accent), Boosters, Guarantee, Support — 14px, inherit color, no underline, `:hover` → accent.
   - 1px × 20px vertical divider in `--color-divider`.
   - "Sign in" at 0.75 opacity, then primary outlined button "Start an order".

2. **Hero** — `display:grid; grid-template-columns:1.15fr 0.85fr; gap:64px; padding:76px 56px 64px; align-items:start`.
   - Left column, `gap:22px`:
     - Kicker: `RANK BOOSTING · 9 GAMES · SINCE 2019` — h6 style: 13px, uppercase, `letter-spacing:0.08em`, `--color-accent`.
     - H1: "Stop grinding / a rank you / already beat." (hard line breaks as written) — Inter 500, **62px**, `line-height:1.02`, `letter-spacing:-0.03em`.
     - Body: 17px, `line-height:1.6`, `max-width:46ch`, color `color-mix(in srgb, var(--color-text) 78%, transparent)`. Copy: "A verified booster takes the queue you don't have time for. You pick the target, watch it happen from the dashboard, and keep the account. No bots, no shared logins, no guesswork on price."
     - Button row, `gap:12px`: primary outlined "Configure your boost", secondary "See booster ranks" — both `padding:11px 20px; font-size:15px`.
     - Stat row, `gap:34px; padding-top:30px`: three stat pairs — value Inter 500 26px, label 12px muted (`color-mix(in srgb, var(--color-text) 55%, transparent)`). Values: `4.8 / 5` (Trustpilot · 3,140 reviews), `92,400` (Boosts completed), `41,000` (Players in Discord).
   - Right column — the **order wizard card**: `background:var(--color-surface)` (#232532), `border-radius:14px`, `box-shadow:var(--shadow-md)`, `padding:24px`, `gap:16px`, flex column.
     - Header row: kicker "ORDER WIZARD · STEP 1 OF 3" (10px, uppercase, `letter-spacing:0.1em`, accent) + tag "Live price" (accent tag: `background:var(--color-accent-800)` #423a6a, `color:var(--color-accent-100)` #f5f4ff, 11px, `padding:3px 10px`, radius 6px).
     - Field "Game" — native `<select>`, 9 options (see *Data*).
     - Two-up grid `1fr 1fr; gap:12px`: "Current rank" and "Target rank" selects, options from the selected game's ladder.
     - Field "How it's played" — segmented control, full width, two equal options: Piloted / Duo queue.
     - 1px divider, `--color-divider`.
     - Quote row: left = summary line (12px muted, e.g. "Gold → Diamond · Piloted") above price (Inter 500, **34px**, `line-height:1.1`); right-aligned = "Est. delivery" label above ETA (Inter 500, 17px).
     - Primary outlined button, full width, `padding:11px`: "Continue to checkout".
     - Fine print, 11px muted, centered: "Money-back until a booster is assigned · VPN matched to your region".

3. **Fading rule** — full-width inside the 56px gutter: `height:1px; background:linear-gradient(to right, transparent, var(--color-divider) 48px, var(--color-divider) calc(100% - 48px), transparent)`. This end-fade is a design-system signature; use it for freestanding rules, not for box outlines.

4. **"Pick your game"** — `padding:64px 56px; gap:26px`. Header row: h2 34px `letter-spacing:-0.02em` + right-aligned note 13px muted "Prices are per division and shown before you sign in." Grid `repeat(3,1fr); gap:14px`, 9 cards.
   - Card: surface fill, radius 8px, `overflow:hidden`, no padding at root.
   - Image area: 104px tall, placeholder `repeating-linear-gradient(135deg, #262939 0 9px, #1d2030 9px 18px)` with a centered monospace label (10px, `letter-spacing:0.08em`, `--color-neutral-500` #9397ab) naming the asset to drop in, e.g. `key art — lol`. **Replace with real game key art**; wrap real photography in the design system's `.lighten` class (`mix-blend-mode:lighten`) per the DS guide.
   - Body `padding:4px 16px 16px; gap:6px`: title row — game name (Inter 500, 17px) and, right-aligned, "from $NN" in `--color-accent-300` (#d2cefd) 13px; below, service list 12px muted.

5. **"Three steps, then it's out of your hands"** + **booster table** — grid `1fr 1fr; gap:64px; padding:8px 56px 64px`.
   - Left: h2 34px, then three numbered steps. Each step is `grid-template-columns:34px 1fr; gap:16px`. The number is Inter 500 15px in accent, 1px accent border, radius 8px, `padding:4px 0`, centered. Step title 17px; body 14px muted. Copy is in the design file — carry it verbatim.
   - Right: header row h4 20px "Boosters on shift now" + neutral tag "34 online". Then a `.table`: columns Booster / Game / Peak / Win rate / Queue, 5 rows. Header cells 11px uppercase `letter-spacing:0.08em` at 60% text; body 14px; win-rate column in `--color-accent-300`. Row rules are painted as row-level gradients so the end-fade spans the whole row (see `nocturne.css` `.table`). Row `:hover` adds a 4% text tint. Footnote 12px muted below.
   - **These boosters are fabricated.** Back the table with the real on-shift roster or drop the section.

6. **Three guarantee cards** — grid `repeat(3,1fr); gap:16px; padding:48px 56px 64px`. Each: surface card, `padding:20px; gap:8px`, `box-shadow:var(--shadow-sm)`, kicker (accent 10px uppercase) / title 17px / body 13px at 0.8 opacity. Kickers: Guarantee, Privacy, Support.

7. **Closing CTA band** — `padding:44px 56px`, 1px top border in divider, `flex; justify-content:space-between; align-items:center`. Left: 24px Inter 500 line "Know your price before you sign up." + 14px muted subline. Right: primary outlined "Start an order" (`padding:11px 22px; font-size:15px`).

8. **Footer** — `padding:28px 56px 34px`, `background:var(--color-neutral-900)` (#292b31), 13px. Left: "© 2026 eSports Boost" muted. Right: link row `gap:22px` at 0.7 opacity — Terms, Refunds, Privacy, Become a booster, Discord.

### Direction B — "Ladder" (id `1b` in the design file)

The wizard *is* the hero. Same content set, different conversion structure.

1. **Nav** — same as A but no bottom border; links Games / How it works / Reviews / Support; the right-hand action is a **secondary** button "Track my order" (repeat-customer bias).

2. **Hero** — `padding:60px 56px 52px; gap:34px`, flex column.
   - Top row, `align-items:flex-end; justify-content:space-between; gap:48px`: left H1 **54px**, `line-height:1.03`, `letter-spacing:-0.03em`, `max-width:30ch` — "Where are you, and where should you be?" with a 16px/1.6 subline at 75% text; right, a right-justified wrapping row of 9 neutral game tags (`gap:10px`, `padding:6px 12px`, 12px, `cursor:pointer`, `max-width:560px`). In production these are the game switcher — clicking one swaps the ladder below.
   - **Wizard panel**: surface fill, radius 14px, `box-shadow:var(--shadow-md)`, `padding:30px 30px 26px`, `gap:26px`.
     - Row 1: game kicker + "Solo queue ranked ladder" (13px muted) on the left; segmented Piloted / Duo queue on the right.
     - Row 2: hint "Click a tier to set your current rank, then your target." (12px muted), then the **rank ladder** — a `flex; gap:6px` row of equal-width tier chips (`flex:1`), each `padding:12px 4px`, radius 8px, `cursor:pointer`, centered, with the tier name (Inter 500 13px) over a 10px monospace state tag (`you` / `target` / empty at 0.6 opacity). Three chip states:
       - **endpoint** (current or target): 1px `--color-accent` border, `background:color-mix(in srgb, var(--color-accent) 18%, transparent)`, text `--color-accent-100`.
       - **in range** (between the two): border `color-mix(in srgb, var(--color-accent) 40%, transparent)`, `background:color-mix(in srgb, var(--color-accent) 7%, transparent)`.
       - **idle**: 1px `--color-divider` border, transparent fill, text at 62%.
     - Row 3, above a 1px top divider with `padding-top:22px`: left group `gap:44px` — summary 12px muted over price (Inter 500 **40px**), "Delivered in" over ETA (19px), "Boosters free now" over count (19px); right — secondary "Add options" + primary "Continue" (`padding:12px 18px` / `12px 24px`, 15px).

3. **Full-bleed stat band** — `background:var(--color-section)` (#262a60), `padding:46px 56px`, grid `repeat(4,1fr); gap:24px`. Value Inter 500 36px `line-height:1`; label 13px in `--color-accent-200` (#e7e5fe). Four stats: 92,400 boosts / 4.8 / 5 Trustpilot / 18 min median claim / 41,000 Discord. **This is the only saturated flood on the page** — the design system permits exactly one such band. Do not add a second.

4. **"Every game, every service"** — `padding:60px 56px 20px; gap:20px`. h2 34px, then 9 rows (not cards): each `grid-template-columns:220px 1fr 120px 120px; gap:24px; align-items:center; padding:16px 0`, 1px bottom border in divider. Columns: game name (Inter 500 18px), service list (13px muted), "from $NN" (`--color-accent-300` 13px), and a right-justified ghost button "Configure →".

5. **Dashboard section** — `padding:56px`, grid `0.9fr 1.1fr; gap:56px; align-items:center`. Left: 4:3 placeholder, radius 14px, `repeating-linear-gradient(135deg, #262939 0 10px, #1d2030 10px 20px)`, centered monospace label `dashboard screenshot — order tracking` (11px, `--color-neutral-500`) — replace with a real screenshot. Right: h2 32px "You watch the whole thing", three title(16px)/body(14px muted) pairs at `gap:16px`, then a wrapping row of four accent tags: Regional VPN, Offline appearance, Pro-rated refunds, No account sharing on duo.

6. **Reviews** — grid `repeat(3,1fr); gap:16px; padding:8px 56px 60px`. Card `padding:20px; gap:10px`, `shadow-sm`: kicker = the rank climb (accent 10px uppercase), quote 14px at 0.9 opacity, meta 11px at 50% ("Verified order · LoL · EUW"). **Fabricated — replace with real Trustpilot pulls.**

7. **Sticky-value CTA band** — same geometry as A's band, but the headline restates the live quote: `"{summary} — {price}"`, e.g. "Silver → Diamond · Piloted — $184". Subline: "Nothing changes after checkout. Refunded in full until a booster claims it." Right: primary "Continue your order". This band must re-render with the wizard state.

8. **Footer** — identical to A.

## Interactions & behavior

- **Game select (A)** — changing the game resets current rank to ladder index 3 and target to index 5, then recomputes. Prevents an invalid pair when ladders differ in length.
- **Rank selects (A)** — controlled `<select>`s; every change recomputes price, ETA and the summary line.
- **Mode segmented control (both)** — Piloted (default) or Duo queue; Duo multiplies price by 1.55.
- **Ladder click-through (B)** — a two-click interaction with an explicit `next` pointer in state (`"from"` → `"to"` → `"from"`):
  - `next === "from"`: set current = clicked tier, target = the tier one step above it, `next = "to"`.
  - `next === "to"` and the clicked tier is above current: set target = clicked tier, `next = "from"`.
  - `next === "to"` and the clicked tier is at or below current: treat as a new start — current = clicked tier, target = one above, `next = "to"`.
  - Clicking the **top** tier as a start sets current = second-from-top, target = top. This guard exists so the price never renders as an em dash in a 40px slot.
  - Chips need `:hover` (accent tint) and keyboard operability — in production make them real `<button>`s in a `role="group"`, arrow-key navigable, `aria-pressed` on the endpoints.
- **Invalid pair** (target at or below current, reachable only via A's selects) — price and ETA render as `—` and the summary reads "Target must sit above your current rank". Consider disabling `Continue` in this state; the prototype does not.
- **No animation** in either direction beyond the design system's CSS state transitions. Keep it that way; if you add motion, keep it under 150ms on hover tints only.
- **Focus** — never leave the browser default. `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` globally, `outline-offset: 0` on `.input`, `-2px` inside the segmented control.
- **Responsive** — the prototype is desktop-only at 1280px. For the real build: collapse A's hero to one column under ~900px with the wizard card **below** the copy but above the fold on a phone if possible; B's ladder must become a horizontally scrollable row (`overflow-x:auto`, chips `min-width:72px`) or a two-select fallback under ~700px — it cannot compress to 9 chips on a 390px screen. Stat band goes 4 → 2 columns; game rows in B drop the service column.

## State management

Prototype state (one component, no routing):

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `aGame` | string | `"League of Legends"` | Direction A game select |
| `aFrom` / `aTo` | string | `"Gold"` / `"Diamond"` | Must be members of the current ladder |
| `aMode` | `"Piloted" \| "Duo queue"` | `"Piloted"` | |
| `bGame` | string | `"Valorant"` | Direction B |
| `bFrom` / `bTo` | string | `"Silver"` / `"Diamond"` | |
| `bMode` | same as `aMode` | `"Piloted"` | |
| `bNext` | `"from" \| "to"` | `"from"` | Which end the next ladder click sets |

Two tweakable inputs were exposed as props: `pricePerDivision` (number, default **26**) and `compactGames` (boolean, default false — shows 6 games instead of 9). In production `pricePerDivision` and the per-game factors belong in server-side pricing config, not the client.

**No data fetching** in the prototype. For the real page: game/ladder/pricing config and the stat band should be server-rendered or fetched at build time; the on-shift booster table and "boosters free now" count are the only live values.

### Pricing formula (carry over exactly, then move server-side)

```
ladder   = LADDERS[game]
i        = ladder.indexOf(from)
j        = ladder.indexOf(to)
steps    = j - i                         // <= 0 → invalid, render "—"
climb    = max(1, i - 1)                 // higher starting ranks cost more
price    = round(steps * perDivision * FACTOR[game] * (1 + climb * 0.22)
                 * (mode === "Duo queue" ? 1.55 : 1))
days     = max(1, round(steps * 1.4 + climb * 0.3))
eta      = days === 1 ? "about 1 day" : `${days} days`
summary  = `${from} → ${to} · ${mode}`
```

`FACTOR`: League of Legends 1.0, Valorant 1.15, Counter-Strike 2 1.45, Teamfight Tactics 0.8, Marvel Rivals 0.95, Dota 2 1.25, Apex Legends 1.1, Overwatch 2 0.9, Rocket League 0.7.

Card/row "from $NN" values are `quote(game, ladder[1], ladder[2], "Piloted")` — a one-division climb off the second tier.

## Data

Games, ladders and service lists (all placeholder except LoL — confirm with the product owner):

| Game | Ladder tiers | Services shown |
| --- | --- | --- |
| League of Legends | Iron → Bronze → Silver → Gold → Platinum → Emerald → Diamond → Master → Grandmaster → Challenger | Elo boost · placements · net wins · duo · coaching |
| Valorant | Iron → Bronze → Silver → Gold → Platinum → Diamond → Ascendant → Immortal → Radiant | Rank boost · placements · unrated wins · duo · coaching |
| Counter-Strike 2 | 5k → 10k → 13k → 15k → 17k → 19k → 21k → 25k → 30k (CS Rating) | Premier rating · Faceit levels · Wingman · wins |
| Teamfight Tactics | Iron → Bronze → Silver → Gold → Platinum → Emerald → Diamond → Master → Challenger | Rank boost · placements · double-up |
| Marvel Rivals | Bronze → Silver → Gold → Platinum → Diamond → Grandmaster → Celestial → Eternity → One Above All | Rank boost · net wins · duo · coaching |
| Dota 2 | Herald → Guardian → Crusader → Archon → Legend → Ancient → Divine → Immortal | MMR boost · calibration · net wins · duo |
| Apex Legends | Rookie → Bronze → Silver → Gold → Platinum → Diamond → Master → Predator | Rank boost · badges · kills · duo |
| Overwatch 2 | Bronze → Silver → Gold → Platinum → Diamond → Master → Grandmaster → Champion | Rank boost · placements · net wins · duo |
| Rocket League | Bronze → Silver → Gold → Platinum → Diamond → Champion → Grand Champ → Supersonic | Rank boost · tournament wins · duo · coaching |

Divisions (Gold IV → Gold I) are **not** modeled; the ladders are tier-level only. Real pricing almost certainly needs divisions and LP/RR offsets — treat the ladder array as the shape to extend, not the final data model.

## Design tokens

From `nocturne.css` (included). Use the CSS variables; do not hard-code the hexes.

**Colors**

| Token | Value | Use |
| --- | --- | --- |
| `--color-bg` | `#161826` | page ground |
| `--color-surface` | `#232532` | cards, inputs, panels |
| `--color-text` | `#e9e9ed` | body text |
| `--color-accent` | `#9184d9` | the single accent — lines, borders, marks, never a flood |
| `--color-divider` | `color-mix(in srgb, #e9e9ed 16%, transparent)` | hairlines |
| `--color-section` | `#262a60` | the one full-bleed stat band (B only) |
| `--color-neutral-100…900` | `#f3f5fe #e4e7f5 #cfd3e5 #b2b6ca #9397ab #75798c #595d6c #3f424d #292b31` | surfaces, muted text, footer |
| `--color-accent-100…900` | `#f5f4ff #e7e5fe #d2cefd #b5abfc #968ae0 #796cbf #5d5294 #423a6a #2b2741` | tinted fills (700–900), text on tints (100–300) |

Muted text is `color-mix(in srgb, var(--color-text) 55%, transparent)` (the `.text-muted` class); other opacities used are 78%, 75%, 70%, 62%, 60%, 50%.

Accent-on-ground is tuned to ~3:1 — fine for chrome, icons and large text, **not** for paragraph copy. Accent-colored body text uses `--color-accent-300`.

**Typography** — Inter for both heading and body (`--font-heading` / `--font-body`), headings at weight **500** and never bolder; hierarchy is size and space. Base 15px / `line-height:1.55`. Heading scale from the DS: h1 42 / h2 32 / h3 25 / h4 20 / h5 16 / h6 13 (uppercase, `letter-spacing:0.08em`), all `line-height:1.12`, `letter-spacing:-0.015em`. The two heroes override h1 to 62px (A) and 54px (B) at `-0.03em`, and section h2s to 34px at `-0.02em`. Monospace is used only for placeholder labels (`ui-monospace, SFMono-Regular, Menlo, monospace`).

**Spacing** — DS scale at 0.70× density: `--space-1` 2.8 / `-2` 5.6 / `-3` 8.4 / `-4` 11.2 / `-6` 16.8 / `-8` 22.4px. Page-scale rhythm in the layout uses explicit values: 56px gutters, 64px column gaps, 76/64/60/56/48/44px section paddings, 34/26/22/16/14/12/10/6px inner gaps.

**Radius** — `--radius-sm` 4px, `--radius-md` 8px (buttons, inputs, cards, chips), `--radius-lg` 14px (the two elevated panels, the 4:3 image).

**Shadows** — `--shadow-sm: 0 0 0 1px #3f424d`; `--shadow-md: 0 0 0 1px #595d6c, 0 6px 18px rgba(0,0,0,.55)`; `--shadow-lg: 0 0 0 1px #9397ab, 0 16px 40px rgba(0,0,0,.65)`. Elevation on this ground is an edge plus ambient darkness — do not stack them.

**Design-system rules to respect** (from `nocturne-readme.md`, included): left-aligned asymmetric layout; primary buttons are a 1px accent outline on transparent, never filled; no pure black or white; keep chroma low outside the accent; freestanding rules fade to transparent over 48px at each end; photographs go through `.lighten` and should be shot on dark backgrounds; icons are Phosphor.

## Assets

Nothing final. Four placeholder classes to fill:

1. **9 game key-art tiles** (A, 104px tall, ~3:1 crop) — labeled `key art — lol`, `key art — valorant`, etc.
2. **1 dashboard screenshot** (B, 4:3) — order tracking view.
3. **Icons** — none used yet. Where the build wants them (nav, guarantee cards, step numbers), use **Phosphor** at interface sizes on `currentColor`.
4. **Logo** — the wordmark is set type, not an asset: "esports" in `--color-text` + "boost" in `--color-accent`, Inter 500 18px, `-0.02em`. Swap in the real logo if one exists.

No brand assets from the design system are used beyond its tokens and component classes.

## Files in this bundle

- `Esports Boost Redesign.dc.html` — both directions, side by side, with the live calculator. Open it in a browser to interact. `1a` = Ledger, `1b` = Ladder. The template markup is the layout reference; the logic class at the bottom holds the pricing model and the ladder interaction.
- `nocturne.css` — the design system's only stylesheet: tokens plus the component layer (`.btn`, `.input`, `.seg`, `.card`, `.tag`, `.nav`, `.table`, `.dialog`, `.lighten`). Source of truth for every value above; safe to use as-is or port to the target codebase's styling system.
- `nocturne-readme.md` — the design system's written guidance: direction, color, type, interaction states, do/don't.

## Open decisions for whoever picks this up

1. **Which direction ships.** Not decided. A is safer for cold traffic (copy explains the service before asking for input); B converts returning customers faster and gives the calculator the whole hero. They can also be split-tested — the sections are interchangeable except for the hero and the stat band.
2. **Real game list and real numbers** — blocking. See *Fidelity*.
3. **Divisions and LP/RR offsets** in the pricing model — the current tier-only ladder is a prototype simplification.
4. Downstream screens (checkout steps 2–3, game service pages, order dashboard) are **not** designed yet.
