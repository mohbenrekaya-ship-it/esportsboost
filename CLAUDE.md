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

# analytics console at /ops — needs a password, else the API refuses everything
OPS_PASSWORD=some-long-password python3 site/serve.py 4321
python3 site/tools/seed_analytics.py --clear --days 70 --sessions 1600   # synthetic traffic
```

`.claude/launch.json` defines an `esportsboost` preview server on port 4321 — start it with the
preview tooling rather than a background shell. It serves `dist/` only, so **run the build first**
and rebuild after every source edit; there is no watcher and no HMR.

`serve.py` maps extensionless URLs to `.html` and serves the real `404.html`, so the preview walks
like production. It also hosts the **Stripe payment API** the checkout page calls — see
[Payments](#payments-stripe) below. With no `STRIPE_SECRET_KEY` set it stays a plain static preview.

There is **no test suite, linter, or formatter** in this project. Verification is: build succeeds
(prints `built 24 pages + 34 images … (+ /ops console)`), then load the affected pages and check the
browser console.

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
- **`site/tools/`** — developer scripts that are never part of a build or a deploy.

A second, separate flow runs alongside the shop — see [Analytics](#analytics--the-ops-console):

```
browser ──beacon──► /api/collect ──► analytics.py (store) ──► insights.py ──► /api/ops ──► /ops
```

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
| `data-out="price\|eta\|summary\|game\|mode\|region\|free\|headline\|was\|discount\|saveLine\|promoCode\|promoLabel\|promoEnds"` | Text nodes rewritten on every render |
| `data-sel="game\|from\|to\|region"` | `<select>` bound to state; ladder/region options are refilled per game |
| `data-service` / `data-panel` | Tab + panel pair for division / wins / placements |
| `data-mode`, `data-addon`, `data-stepper` (`data-step`, `data-min`, `data-max`) | Radios, checkboxes, ± counters |
| `data-ladder` | Container whose tier chips are built by JS |
| `data-sum="base\|addons\|total\|eta\|summary\|game\|region\|mode\|addonlist\|was\|discount\|discountLabel"` | Checkout breakdown |
| `data-when-discount` / `data-when-addons` | Rows that `hidden` themselves when the number they carry is zero |
| `data-addon-price="<id>"` | Dollar cost of one add-on **on this order** — quoted as the difference with and without it, so it already includes the discount |
| `data-promo`, `data-promo-apply`, `data-promo-msg` | Discount-code input, its button, and its status line |
| `data-continue` | Checkout links: disabled on an invalid pair, fires `begin_checkout` before navigating |
| `data-game-link`, `data-game-tag` | Links/chips that follow the selected game |

Per-page scripts are passed as the `extra_js=` argument to `layout()` (checkout, track, support,
become-a-booster) and call the exposed `window.esbTrack` / `esbItemParams` / `esbQuote` / `esbState` /
`esbPromo`.

`quote()` on both sides reads add-ons **from the state it is given**, not from the live page state —
they only agree by accident otherwise, and `data-addon-price` depends on quoting hypothetical states.

## Conventions

- **Escape all interpolated data**: `build.py` uses f-strings and `%` into raw HTML, with
  `from html import escape as esc`. Anything from `data.py` goes through `esc()`.
- **`ashfall.css` is the vendored design system** — do not edit it. Page-specific layout goes in
  `site/public/assets/css/site.css`, on top of it. There is no `nocturne.css` in the build; v1's
  system was replaced by v2 Ashfall (see the handoff note below).
- **Ashfall tokens**, all defined on `:root` in `ashfall.css`: grounds `--bg` / `--bg-2` / `--bg-3` /
  `--panel` / `--glass`; text `--text` down to `--text-7`; accent `--ember` / `--ember-lit` /
  `--ember-warm` / `--amber` / `--amber-pale` / `--ember-grad`; `--hairline{,-2,-3}`; type `--display`
  (Chakra Petch) / `--body` (IBM Plex Sans) / `--mono` (IBM Plex Mono); `--radius` (2px) /
  `--radius-lg` / `--gutter`. There are no `--color-*`, `--space-*` or `--shadow-*` tokens — those
  were v1's.
- **Prefer tokens over raw hex**, but the ember palette is repeated literally in a few places where a
  gradient stop or an on-accent text colour has no token (`#06060a` / `#120a06` on ember fills, the
  spark colours). Match the surrounding code rather than inventing a new token.
- **Design system rules that are easy to break**: primary buttons are **filled with `--ember-grad`**
  and carry an ember glow — they are not outlines; `--display` headings run to weight 700, so the
  "never past 500" rule from v1 no longer applies; the saturated stat band appears exactly once
  site-wide (the homepage `.statband`); focus is a 2px accent `:focus-visible` ring, never the
  browser default; `prefers-reduced-motion` kills every animation and transition globally.

## Design handoffs (`redesign_zip*/` — reference only, never imported at build time)

- **v1 `redesign_zip/design_handoff_esportsboost_homepage/`** — the Nocturne design system.
  **Superseded and no longer implemented**; its page structure ("Ladder" on the homepage, "Ledger" on
  the games index and game pages) still shows through, but its stylesheet and tokens are gone.
- **v2 `redesign_zip_v2/design_handoff_esportsboost_v2/`** — "Ashfall", an immersive 1440px
  desktop-first homepage. **This is what `site/` implements** — `ashfall.css` comes from here and
  `site.css` is layered on top of it. Its README carries the
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

The same rule covers **seeded analytics**: every event written by `tools/seed_analytics.py` carries
`"syn": 1`, and `/ops` shows a standing "synthetic data — not real traffic" banner for as long as
any are in the window. Keep that flag. Seeded funnel numbers are exactly the kind of thing that
quietly becomes a slide in a real meeting. Clear the store before the site takes real traffic.

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

## Analytics & the /ops console

`app.js` has always pushed a clean funnel into `window.dataLayer` — nothing read it. The analytics
layer is the other end of that pipe, plus a password-gated dashboard at **`/ops`**. Same house
rules: stdlib only, no third-party packages, no build step.

```
public/assets/js/analytics.js  ──►  POST /api/collect  ──►  src/analytics.py   (validate + store)
                                                                    │
     /ops  ◄── POST /api/ops ◄── src/ops.py (auth) ◄── src/insights.py (aggregate)
```

| File | Role |
| --- | --- |
| `site/public/assets/js/analytics.js` | The beacon. Anonymous id + session, first-touch UTM, `page_view`, `configure`, scroll, errors, and a bridge that mirrors every existing `dataLayer` push. |
| `site/src/analytics.py` | Event validation (strict allowlist) and the store. |
| `site/src/geo.py` | Country resolution with no IP lookup: Vercel's edge header, else the browser's IANA timezone, else the locale's region subtag. |
| `site/src/insights.py` | All aggregation. **Every number on the dashboard is defined exactly once, here.** |
| `site/src/ops.py` | Password auth + two routes: the dashboard payload, and one session's full timeline on demand. |
| `site/public/assets/js/ops.js`, `ops.css` | The console. Self-contained; shares nothing with the shop's stylesheets. |
| `site/tools/seed_analytics.py` | Synthetic traffic for testing. |
| `api/collect.py`, `api/ops.py` | Vercel shells, mirroring the `serve.py` routes. |

**Two stores, chosen by environment.** With `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`
set, events go to Upstash Redis over its REST API (stdlib `urllib`) — required in production,
because Vercel's filesystem is ephemeral and a file would lose every event when the function froze.
Otherwise they append to a local `site/analytics.ndjson`, so `serve.py` collects for real in dev
with nothing to configure.

**Things that are load-bearing and easy to break:**

- **The schema is anonymous by construction.** No cookie, no IP, no name, no email — the visitor id
  is a random string the browser mints itself, and country comes from the edge header Vercel already
  attaches. That is what keeps this out of consent-banner territory. **Do not add a field that could
  identify a person.**
- **`/api/collect` is public and unauthenticated.** Everything is allowlisted, length-capped and
  type-checked in `_clean_event()`; nothing is stored that did not survive it. It always answers
  `204` with an empty body so it cannot double as a read oracle.
- **The dashboard fails closed.** With `OPS_PASSWORD` unset (or under 12 characters) `/api/ops`
  returns 503 and `/ops` renders a setup notice. The HTML shell is public but holds no data — every
  number arrives through the gated API.
- **`/ops` never reports on itself.** `analytics.js` returns early on `/ops` paths; the console does
  not load it. An ops tool logging its own pageviews would pollute the funnel it exists to measure.
- **`/ops` is not part of the shop.** No canonical tag, not in `sitemap.xml`, `Disallow: /ops` in
  robots.txt, `noindex` in its own head, and zero links to it from any page. It is written after the
  sitemap loop in `main()` for exactly that reason.
- **The re-quote count drives real conclusions.** `configure` fires only when the quote signature
  actually changes, watched through the documented `data-*` contract rather than app.js internals.
  The `dataLayer` bridge deliberately ignores `select_item`/`add_to_cart` so re-quotes aren't
  double-counted.
- **Invalid configurations quote as `total: 0`.** `insights.py` excludes them from the price curve
  and the rank matrix — left in, they sink into the cheapest band and understate conversion exactly
  where the chart is read most. They still count as re-quotes, and surface separately in Friction.
- **Chart colors were computed, not chosen.** `ops.css` uses the data-viz reference palette's dark
  column, validated against its own `--surface`. Changing a hex means re-running those checks.
- **Session timelines are fetched one at a time** (`action: "session"`), never bundled into the
  dashboard payload — bundling them would ship the entire event store to the browser on every
  refresh. Time-on-page is derived from gaps between consecutive events; there is no unload event,
  so a session's *last* page reports a floor, flagged `partial`, and the UI says so rather than
  quietly under-reporting.
- **Anything toggled with the `hidden` attribute must not have a `display` rule**, or it stays
  visible — `.banner` needed an explicit `[hidden]` guard for exactly this reason.
- **Country is resolved server-side and never trusted from the body**, and never from an IP lookup:
  the edge header wins, then the browser's timezone, then the locale region. Each session records
  *which* signal answered (`cosrc`) and the dashboard shows it, so an inferred country is never read
  as a measured one. `.env` is gitignored — `serve.py` loads it at startup, so a key left there would
  otherwise be committed.

## CRO audit constraints

`CRO-AUDIT.md` (+ `.fr.md` translation) is the audit this build answers; the README lists which
findings are fixed. Several fixes are load-bearing and easy to regress:

- Guest checkout only — no login wall anywhere in the order flow.
- `begin_checkout` fires **before** navigation to checkout, not on arrival.
- All money formatted via `Intl.NumberFormat` / `usd()` — never a bare `$9.6`.
- No third-party trust badges linking off-brand; one set of statistics across the whole site.
- The configurator stays above the fold on every game page, with the sticky mobile price bar.
- Every page keeps its canonical tag, JSON-LD block and real `h1`/`h2`/`h3` hierarchy.
