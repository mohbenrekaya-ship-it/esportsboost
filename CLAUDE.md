# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static-site generator for the `esportsboost.com` redesign, written in **plain Python 3 with no
dependencies** (no Node on this machine, no package manager, no lockfile). `python3 site/build.py`
generates all 23 pages of `site/dist/` from `site/src/data.py`.

Not a git repository. The README is in French; the site copy and the design handoffs are in English.

## Commands

```bash
python3 site/build.py                    # regenerate site/dist/ (wipes and rebuilds it)
python3 site/serve.py 4321               # preview at http://localhost:4321
python3 site/build.py && python3 site/serve.py 4321
```

`.claude/launch.json` defines an `esportsboost` preview server on port 4321 — start it with the
preview tooling rather than a background shell. It serves `dist/` only, so **run the build first**
and rebuild after every source edit; there is no watcher and no HMR.

`serve.py` maps extensionless URLs to `.html` and serves the real `404.html`, so the preview walks
like production. It also hosts the **Stripe payment API** the checkout page calls — see
[Payments](#payments-stripe) below. With no `STRIPE_SECRET_KEY` set it stays a plain static preview.

There is **no test suite, linter, or formatter** in this project. Verification is: build succeeds
(prints `built 23 pages + 9 key art files`), then load the affected pages and check the browser
console.

## Architecture

Three layers, one direction of flow:

```
site/src/data.py  ──►  site/build.py  ──►  site/dist/*.html   (server-rendered prices, copy, JSON-LD)
                              │
                              └──────────►  dist/assets/js/data.js  ──►  public/assets/js/app.js
                                            (generated client mirror)     (live re-quoting in browser)
```

- **`site/src/data.py`** — single source of truth: games, ladders, pricing factors, add-ons, stats,
  boosters, reviews, FAQ, legal date. Adding a game here automatically produces its detail page,
  key art, sitemap entry, mosaic card and client data. Nothing else hard-codes a game.
- **`site/build.py`** (~1500 lines) — everything else. Sections in order: pricing → shell
  (`nav`/`footer`/`layout`) → reusable blocks (`wizard`, `game_cards`, `faq_block`, …) → one
  `page_*()` function per page → generated SVG assets → `main()`. Every page returns HTML through
  `layout()`, which owns `<head>`, canonical URL, OG/Twitter tags, JSON-LD injection, the optional
  sticky mobile price bar, and the two script tags.
- **`site/public/`** — static assets copied verbatim into `dist/` at build time.
- **`site/dist/`** — build output, deleted and recreated on every run. **Never edit it.** Edit
  `site/public/assets/…`, not `site/dist/assets/…` (they look identical; only `public/` survives).

### The pricing formula lives in one Python module + one JS mirror — keep them identical

`quote()` in [site/src/pricing.py](site/src/pricing.py) is the **authoritative** formula (Python):
`build.py` imports it for static `from $NN` cards, and `serve.py` calls it to compute the amount a
customer is actually charged — the browser never sends a price. `quote()` in
[site/public/assets/js/app.js:97](site/public/assets/js/app.js#L97) (JS, runtime) is the client
mirror that re-quotes live as the user configures. They implement the same formula and **must never
disagree on the same page — change one, change the other.**

```
steps = ladder.indexOf(to) - ladder.indexOf(from)      # <= 0 → invalid, render "—"
climb = max(1, i - 1)                                   # higher starting ranks cost more
base  = steps * PER_STEP * FACTOR[game] * (1 + climb * 0.045) * (Duo ? 1.55 : 1)
total = jsRound(base * (1 + Σ addon.pct))               # wins ×0.55 · placements ×0.7 of PER_DIVISION
days  = max(1, round(steps * 0.35 + climb * 0.08))
```

Both sides cover all three services (division / wins / placements) and the add-on percentages;
`pricing.py` uses a half-up `_jsround()` so the Python total matches JS `Math.round` to the cent.

`PER_DIVISION`, the per-game `factor`s and the add-on percentages are still shipped in
`assets/js/data.js` for the live client quote; the **charge** amount is now computed server-side in
`pricing.py`, which closes the "prices are client-visible" pre-launch risk for the money that
actually moves.

### build.py ↔ app.js contract: `data-*` attributes

`app.js` holds one order object in `localStorage` (`esb.order.v1`), and every price on a page is
derived from one `quote()` call in one `render()` pass. It finds what to update purely through
attributes that `build.py` emits — there are no IDs or classes in the wiring. When adding markup,
reuse these rather than inventing new hooks:

| Attribute | Role |
| --- | --- |
| `data-configurator` (+ `data-game`) | Marks a wizard; the optional game pins the page to one game and fires `view_item` |
| `data-out="price\|eta\|summary\|game\|mode\|region\|free\|headline"` | Text nodes rewritten on every render |
| `data-sel="game\|from\|to\|region"` | `<select>` bound to state; ladder/region options are refilled per game |
| `data-service` / `data-panel` | Tab + panel pair for division / wins / placements |
| `data-mode`, `data-addon`, `data-stepper` (`data-step`, `data-min`, `data-max`) | Radios, checkboxes, ± counters |
| `data-ladder` | Container whose tier chips are built by JS |
| `data-sum="base\|addons\|total\|eta\|summary\|game\|region\|mode\|addonlist"` | Checkout breakdown |
| `data-continue` | Checkout links: disabled on an invalid pair, fires `begin_checkout` before navigating |
| `data-game-link`, `data-game-tag` | Links/chips that follow the selected game |

Per-page scripts are passed as the `extra_js=` argument to `layout()` (checkout, track, support,
become-a-booster) and call the exposed `window.esbTrack` / `esbItemParams` / `esbQuote` / `esbState`.

## Conventions

- **Escape all interpolated data**: `build.py` uses f-strings and `%` into raw HTML, with
  `from html import escape as esc`. Anything from `data.py` goes through `esc()`.
- **`nocturne.css` is vendored verbatim** from the handoff — do not edit it. Page-specific layout
  goes in `site/public/assets/css/site.css`, which may only use Nocturne tokens
  (`var(--color-*)`, `--space-*`, `--radius-*`, `--shadow-*`) and no raw hex values.
- **Design system rules that are easy to break**: primary buttons are accent *outlines*, never
  filled; the saturated `--color-section` band appears exactly once site-wide (the homepage stat
  band); headings never go past weight 500; images go through the `.lighten` wrapper; focus is a
  2px accent `:focus-visible` ring, never the browser default.

## Design handoffs (`redesign_zip*/` — reference only, never imported at build time)

- **v1 `redesign_zip/design_handoff_esportsboost_homepage/`** — the Nocturne design system. **This is
  what `site/` currently implements**, using both of its directions: "Ladder" (B) on the homepage,
  "Ledger" (A) on the games index and game pages. `nocturne.css` is copied from here.
- **v2 `redesign_zip_v2/design_handoff_esportsboost_v2/`** — "Ashfall", an immersive 1440px
  desktop-first homepage that **supersedes v1 and is not implemented yet**. Its README carries the
  full spec (tokens, section-by-section measurements, motion, accessibility gaps). It uses the same
  pricing formula and per-game factors already in `data.py`. `image-slot.js` and the `.dc.html`
  prototype run on an in-house runtime and are explicitly not to be ported. If asked to "build the
  redesign", clarify whether that means the existing v1 site or a v2 rebuild — they are different
  visual systems.

## Placeholder data — do not present as real

`data.py`'s `STATS`, `BOOSTERS`, `REVIEWS` and every game except League of Legends are **invented
placeholders** carried over from the handoff, as is the key art (`keyart()` generates labelled SVG
placeholders). Both handoffs and the README flag this as blocking for launch. Keep the warning
comment at the top of `data.py` intact, and don't let placeholder statistics leak into new copy —
the site deliberately uses one single set of numbers everywhere.

## Payments (Stripe)

Checkout uses **Stripe Checkout** (hosted redirect). No card data ever touches this codebase. The
flow, still dependency-free (stdlib `urllib`/`hmac` talking to Stripe's REST API):

```
checkout.html  ──POST /api/checkout──►  serve.py  ──►  Stripe Checkout Session  ──►  redirect to Stripe
                                            │                                              │ pays
   checkout/success.html  ◄──redirect──────┘                                              ▼
        │  GET /api/session?id=cs_…  (payment_status, receipt)          POST /api/webhook (signed) → fulfil
```

- **`site/serve.py`** holds three routes: `POST /api/checkout` (validates the order, re-prices it
  with `pricing.quote()`, creates the Session), `GET /api/session` (success-page receipt lookup),
  `POST /api/webhook` (HMAC-verified `checkout.session.completed` → appends to `orders.log`; this is
  the fulfilment seam where an order would join the booster board).
- **The amount is never trusted from the client.** The browser POSTs only the *config* (game, ranks,
  mode, addons, region); the server recomputes the price. A tampered `wins`/`placements` is clamped
  (`pricing.UNIT_MIN..UNIT_MAX`); an invalid rank pair is refused before any Stripe call.
- **Config is env-only, never committed:** `STRIPE_SECRET_KEY` (required to charge — use a
  `sk_test_…` key in dev), `STRIPE_WEBHOOK_SECRET` (enables signature checks on `/api/webhook`),
  `PUBLIC_BASE_URL` (success/cancel origin; inferred from the `Host` header if unset). Run it as
  `STRIPE_SECRET_KEY=sk_test_… python3 site/serve.py 4321`.
- **Graceful degradation:** with no key set, `/api/checkout` returns `503` and the checkout page
  falls back to its local preview confirmation, so the static preview still walks end to end.
- Payment methods on the checkout page: **Card** (Stripe surfaces Apple Pay / Google Pay under it);
  **Crypto** is present but disabled with a "coming soon" label. PayPal was removed.
- Regenerate after editing `build.py`/`data.py`; the payment routes live in `serve.py` and take
  effect only when the server process is **restarted** (no watcher).

## CRO audit constraints

`CRO-AUDIT.md` (+ `.fr.md` translation) is the audit this build answers; the README lists which
findings are fixed. Several fixes are load-bearing and easy to regress:

- Guest checkout only — no login wall anywhere in the order flow.
- `begin_checkout` fires **before** navigation to checkout, not on arrival.
- All money formatted via `Intl.NumberFormat` / `usd()` — never a bare `$9.6`.
- No third-party trust badges linking off-brand; one set of statistics across the whole site.
- The configurator stays above the fold on every game page, with the sticky mobile price bar.
- Every page keeps its canonical tag, JSON-LD block and real `h1`/`h2`/`h3` hierarchy.
