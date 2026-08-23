# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static-site generator for the `esportsboost.com` redesign, written in **plain Python 3 with no
dependencies** (no Node on this machine, no package manager, no lockfile). `python3 site/build.py`
generates every page of `site/dist/` from `site/src/data.py` — 24 pages of shop plus one profile per
booster (88 today, so 114 in total).

Not a git repository. The README is in French; the site copy and the design handoffs are in English.

## Commands

```bash
python3 site/build.py                    # regenerate site/dist/ (wipes and rebuilds it)
python3 site/serve.py 4321               # preview at http://localhost:4321
python3 site/build.py && python3 site/serve.py 4321

# analytics console at /ops — needs a password, else the API refuses everything
OPS_PASSWORD=some-long-password python3 site/serve.py 4321
python3 site/tools/seed_analytics.py --clear --days 70 --sessions 1600   # synthetic traffic
python3 site/tools/seed_analytics.py --clear --sessions 900 --accounts 40 # + synthetic header sign-ups
python3 site/tools/seed_boosters.py --clear   # fill the roster store from data.py's BOOSTERS
```

`.claude/launch.json` defines an `esportsboost` preview server on port 4321 — start it with the
preview tooling rather than a background shell. It serves `dist/` only, so **run the build first**
and rebuild after every source edit; there is no watcher and no HMR.

`serve.py` maps extensionless URLs to `.html` and serves the real `404.html`, so the preview walks
like production. It also hosts the **Stripe payment API** the checkout page calls — see
[Payments](#payments-stripe) below. With no `STRIPE_SECRET_KEY` set it stays a plain static preview.

Verification is: the four test files pass — `python3 site/tests/test_pricing.py` (the pricing engine,
the bundle rules, the JS/Python mirror, the currency charge and the checkout payload), `python3
site/tests/test_mail.py` (header injection, the honeypot, the rate cap and the two order mails),
`python3 site/tests/test_carts.py` (abandoned-checkout capture and the recovery token) and `python3
site/tests/test_mystery.py` (the mystery-discount token, its hour, one-card-per-inbox, the copy
rule that keeps the flat deck honest, and the follow-up: revive-not-reissue, one chase ever, and the
per-hour claim that drops itself when it stops arguing for the order, the halfway
warning's window, the config beacon's allowlist and the figures the mails are
built from) — the build succeeds (prints `built 114 pages + 207 images …
(+ /ops console)`), then load the affected pages and check the browser console. There is no linter
or formatter.

**The build has three environment switches**, all optional locally:

| Var | Effect |
| --- | --- |
| `SITE_URL` | The origin every canonical/og:url/sitemap URL is written against. **Required in production** — see DEPLOY.md; the fallback is `localhost:4321`. |
| `ESB_NO_MINIFY=1` | Ships the stylesheets uncompressed, so you can read them in devtools. |
| `ESB_ALLOW_UNSIGNED_WEBHOOK=1` | Lets `/api/webhook` accept unsigned events for local replay. Never set in production. |

CSS is minified into `dist/` by `minify_css()` (comments stripped, whitespace collapsed, nothing
else — `site.css` goes 445K → 266K raw, 97K → 44K gzipped). **The source keeps every comment**; only
the build output is stripped, so the documentation in the stylesheet costs nothing at runtime. JS is
deliberately *not* minified: doing it safely needs a real parser, and gzip already takes `app.js`
from 146K to 42K.

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
days  = max(1, round(0.5 + steps * 0.18 + climb * 0.045))   # DAYS_* in pricing.py; climb term only
                                                             # where the game has no `prices` table
```

Both sides cover all three services (division / wins / placements) and the add-on percentages;
`pricing.py` uses a half-up `_jsround()` so the Python total matches JS `Math.round` to the cent.
Add-ons are also filtered by queue before they are summed — `D.addon_applies()` server-side,
`addonApplies()` in app.js — so the mode-conditional pair (see the order-card section) can never be
charged in the queue it is not offered in, and the two sides must agree or checkout's `client_total`
guard rejects a valid order.

**The ETA is a band once a single figure would be false precision.** `eta_text()` in `pricing.py` and
`etaText()` in app.js (another mirror — `test_pricing.py` locks both the `DAYS_*` rates and the band)
render 1 day as "about 1 day", 2–3 as a figure, and anything past `ETA_EXACT` as a band opening **on**
the computed value: 7 days is "7–9 days". The band is proportional (`ETA_SPAN_PCT`, never under
`ETA_SPAN_MIN`), so a ladder longer than any shipped today widens it rather than quoting a fortnight to
the day. `days` itself stays an int — the demo order's "N days left", the booster profiles' completed
orders and `/orders.html` all read it as a number. The schedule was cut from 0.35/rung + 0.08/climb,
which quoted a full ladder at 12 days; the slowest climb on the site is now 7. The guarantee page
promises a 15% credit past the ETA, so a re-tune downward is a real commitment, not a copy change.

`PER_DIVISION`, the per-game `factor`s and the add-on percentages are still shipped in
`assets/js/data.js` for the live client quote; the **charge** amount is now computed server-side in
`pricing.py`, which closes the "prices are client-visible" pre-launch risk for the money that
actually moves.

### The saved order — one record per game

The configuration a visitor builds is kept **one record per game**, `esb.order.g.<slug>`, and every
surface that configures that game reads and writes the same key: the homepage Best Sellers band and
that game's own page are two views of one order, not two orders. `esb.order.last.v1` names the game
last configured anywhere; `esb.order.v1` is the separate hand-off snapshot `[data-continue]` commits
and checkout reads.

It used to be one record per *context* (`esb.order.home.v1` beside `esb.order.g.<slug>`), so a climb
set in the band was gone the moment the visitor followed it to the page it was for, and switching
game tabs reset the climb to the ladder default every time. `migrateLegacy()` files an existing
`esb.order.home.v1` under the game it names — once, on the next load — so nobody's stored climb is
dropped by the deploy.

- **Per game, because ranks cannot be shared.** Nine ladders name their rungs differently and
  "Gold II" is not a rung of CS2's. Everything that is *not* about a particular ladder is in
  `SHARED` and travels with the visitor across games instead — queue, server, add-ons, promo, the
  unit counts, the coaching picks. `from`/`to`, the bundle and the named booster stay with the game
  they were chosen on.
- **A page opens on its own game if it is pinned to one** (`data-game`), else the last game
  configured anywhere, else the catalogue's first — then **clamped to what the page actually draws**.
  The band carries four of the nine titles, so a visitor whose last order was on Apex cannot be shown
  it there; `recentOffered()` falls back to the most recent climb they set on a game the band *does*
  carry, rather than to the catalogue's first title over a climb they never set. Their Apex record is
  untouched and returns on the Apex page.
  Both lists are read off the DOM (`pageGames()` from `[data-game-tag]`, `pageServices()` from
  `[role=tab][data-service]`), never written down, so the band's four tabs and a game's three-or-four
  services stay the authority. A stored order naming something the page cannot draw is clamped, never
  dropped — losing the ranks is the thing this record exists to stop.
- **The service clamp is load-bearing.** The band is division-only and has no service tabs at all, so
  a `wins` order set on a game page would otherwise quote net wins there under two rank panels; and a
  game with no coaches has no Coaching tab for a booking carried in from one that has. It is applied
  only where there IS a configurator — checkout draws no tabs and must charge the service bought.
- **Pages with no configurator read the committed snapshot**, as before, and `HYDRATED` is what stops
  them writing over a real record: a page holding `DEFAULT` (no configurator, no snapshot — reachable
  from a stray `?booster=` link) writes `esb.order.v1` only.
- **`normalize()` is the one validator** and it runs on every path — first load, a game switch, the
  checkout snapshot. `fresh` (nothing stored at all) is what keeps the `regionPicked` migration off a
  first visit; marking a resolved region as the visitor's own pick would pin every new browser's
  server before it had touched the control.
- **A bfcache restore re-reads the record**, through the `pageshow`/`e.persisted` listener at the
  foot of app.js: back/forward hands a page back the JS state it held when the visitor left it, and
  with one shared record that state can now be stale rather than merely separate. Storage is the
  authority there, never the frozen object.
- Ranks persist indefinitely; `STATE_TTL` (36h) expires only the bundle and the named booster, for
  the reason on the constant.
- **This is per browser, not per account.** Signing in does not move it — `captureCart()` already
  posts a signed-in visitor's configuration to `carts.py`, but nothing reads it back, so restoring a
  config on another device would need a session-scoped `GET /api/cart` and a client restore path.

### build.py ↔ app.js contract: `data-*` attributes

`app.js` holds one order object in `localStorage` — **one record per game**, `esb.order.g.<slug>`
via `keyFor()`, plus `esb.order.last.v1` (the game last configured anywhere) and `esb.order.v1`, the
separate hand-off snapshot checkout reads. See
[The saved order](#the-saved-order--one-record-per-game) for what that key scheme guarantees. Every
price on a page is derived from one `quote()` call in one `render()` pass. It finds what to update purely through
attributes that `build.py` emits — there are no IDs or classes in the wiring. When adding markup,
reuse these rather than inventing new hooks:

| Attribute | Role |
| --- | --- |
| `data-configurator` (+ `data-game`) | Marks a wizard; the optional game pins the page to one game and fires `view_item` |
| `data-out="price\|eta\|summary\|summaryUpper\|game\|mode\|region\|free\|headline\|was\|discount\|saveAmt\|saveLine\|saveWith\|configLine\|steps\|stepsWord\|promoCode\|promoLabel\|promoEnds\|fromRank\|toRank"` | Text nodes rewritten on every render. `fromRank`/`toRank` are the whole rank names ("Gold IV") — `data-tiername` is the tier alone. Three shapes of the same saving: `discount` is the signed receipt figure (`−$16`), `saveAmt` the bare amount for a pill, `saveLine`/`saveWith` the sentences |
| `data-sel="game\|from\|to\|fromTier\|toTier\|region"` | `<select>` bound to state; ladder/tier/region options are refilled per game. The `*Tier` pair moves one endpoint's tier while keeping its division numeral, then clamps through the same rule as every other rank control |
| `data-service` / `data-panel` | Tab + panel pair for division / wins / placements |
| `data-mode`, `data-addon`, `data-stepper` (`data-step`, `data-min`, `data-max`) | Radios, checkboxes, ± counters |
| `data-tiergrid="from\|to"` | Tier buttons for one end, built by JS. Out-of-range tiers render `disabled` |
| `data-regions` | Region chips, built by JS from the game's region list |
| `data-rail` / `data-rail-caps` | Best Sellers rail: fill + two handles, and tier names positioned at each tier's centre node |
| `data-tiername="from\|to"` | Tier name beside a rank mark. **A mark on its own never names a rank** — it is the division numeral, so a pair of them reads "IV → IV". Every climb readout pairs each mark with one of these |
| `data-rankcolor="from\|to"` | Sets `--tier` from that end's rank and writes no text — for anything that takes the tier's colour without printing the numeral (the rank plate, whose emblem tints itself off it in CSS; the closing band's rank words) |
| `data-tierfit` | The rank plate's text column. app.js measures the game's widest tier name in it and sets `data-dense` 0–3, which CSS reads as 17 → 12.5px. Caches on `data-for`, skipped while the plate has no layout |
| `data-subseg="from\|to"` | Container whose division buttons are built by JS — the sub-ranks of that endpoint's tier. Out-of-range divisions render `disabled` |
| `data-ticks` / `data-tier-caps` | Game-page ladder strip: one tick per rung with the crossed span filled, and the tier names under it. Both are built by JS and rebuilt when the game changes |
| `data-mark="from\|to"` | Rank mark — division numeral, tinted via `--tier` from `D.tiercolors` (see `data.py`'s `tier_color()`) |
| `data-sum="base\|addons\|total\|eta\|summary\|game\|region\|mode\|addonlist\|was\|discount\|discountLabel"` | Checkout breakdown, and the closing band's configuration card — the two read the same hooks so one render() fills both and they cannot quote different money. There is no `climb` key: both Climb rows draw the pair as `data-mark` + `data-tiername` and fall back to `summary` on the unit services |
| `data-when-discount` / `data-when-no-discount` / `data-when-addons` | Rows that `hidden` themselves when the number they carry is zero — or, for `no-discount`, when it isn't |
| `data-when-service="division\|wins\|placements\|units"` | Element shown only on that service. `units` is wins + placements together — anything drawn as a rank pair needs one node for the pair and one for everything else, not one per service |
| `data-addon-lines` | Container JS fills with one receipt row per selected add-on. Each row is a **subtotal** delta taken in order, so the column telescopes and `boost + rows − discount = total` exactly. Deliberately *not* the same figure as `data-addon-price` below |
| `data-addon-price="<id>"` | Dollar cost of one add-on **on this order** — quoted as the difference with and without it, so it already includes the discount |
| `data-when-mode="Solo\|Duo queue"` | Element shown only in that queue — the mode-conditional add-on pair. Both ride in the DOM (i18n matches whole text nodes); the server renders the default queue and `paint()` swaps them. Needs the `.opt[hidden]` guard: `.opt` carries a `display` that beats the UA's `[hidden]` |
| `data-when-game="<name>"` | Element shown only for that game — the picks add-on's per-game name on the pages that are not pinned to one game (checkout ships all nine). Same reason both ride in the DOM |
| `data-promo`, `data-promo-apply`, `data-promo-msg` | Discount-code input, its button, and its status line |
| `data-promo-toggle` / `data-promo-box` | The "Have a code?" button and the input it reveals. The button only flips `aria-expanded`; CSS picks the label |
| `data-continue` | Checkout links: disabled on an invalid pair, fires `begin_checkout` before navigating |
| `data-game-link`, `data-game-tag` | Links/chips that follow the selected game |
| `data-ts` / `data-mins` | A relative timestamp, on any `.lf-ago` — the feed's rows and the demo page's order-card footer. `data-ts` (epoch seconds) is what a feed wired to the orders table emits and wins; `data-mins` counts back from page load and is the placeholder stand-in. `initFeed()` selects on the attribute, not on `.lf-row`, and re-derives the relative label and the clock from whichever is present |
| `data-rst-*` | The roster board. `data-rst-row` carries `data-game` / `data-free` / `data-win` — the filter reads only these, so a server-rendered board keeps working. `data-rst-game\|avail\|sort` are the three controls, `data-rst-body\|shown\|fgame\|ffree\|more\|reset\|empty*` the things `initRoster()` rewrites |
| `data-bp-*` | A profile's completed orders: `data-bp-row` (+ `data-mode`), `data-bp-filter`, `data-bp-body\|shown\|total\|more` |
| `data-gc-*` | The catalogue grid on `/games/`. `data-gc-card` carries `data-gc-riot\|valve\|coaching` (the filter reads only these, so a filter is one attribute) plus `data-gc-order\|price\|name` (the three sorts). `data-gc-filter\|sort\|sortsel` are the controls — the segment and the native select write one state and `initCatalog()` re-marks both — and `data-gc-grid\|foot\|shown\|reset\|sortlabel\|dots\|dot` are what it rewrites |
| `data-rv-stars` / `data-rv-game` | The two facts the reviews page filters and sorts a card on, emitted by `review_card(filterable=True)`. The whole feed reads only these, so a server-paged feed keeps working |
| `data-rvp-*` | The reviews feed's controls: `data-rvp-game\|rating\|sort` (three radio groups) and `data-rvp-dist` (the distribution rows, `aria-pressed` toggles). Both rating controls write one state — `initReviews()` re-marks both whenever either fires. `data-rvp-grid\|shown\|total\|crumb\|clear\|empty\|more\|more-label` are what it rewrites; `data-rvp-worst` is the hero's "Read the worst first" |
| `data-when-booster` / `data-out="booster"` / `data-sum="booster"` / `data-booster-clear` | The named booster. Rows that `hidden` themselves when none is set; it is an order attribute, never a price input — `quote()` must not read it |
| `data-prefill-email` | An email field the site already knows the address for — checkout's, today. Filled by `prefillEmail()` in app.js from the address the mystery modal captured, **only when the field is empty**, and it dispatches `input` so checkout's abandoned-cart capture sees it as typed. An attribute rather than `#k-email` because the wiring in app.js is attribute-based throughout |
| `data-myd-*` | The mystery-discount modal. `data-myd` is the root (`initMystery()` returns without it, so it only ever runs on a game page) and `data-myd-view` its readable state; `data-myd-step` marks the five cards, switched by **toggling `hidden`** — see that section for why a CSS rule cannot do it. `data-myd-card\|take\|pass\|open\|apply\|fullprice\|undo\|close\|back\|copy\|optin` are the controls, `data-myd-pick\|pct\|code\|was\|now\|save\|full\|timer\|note` the value nodes JS writes (all in i18n.js's `SKIP`) |
| `data-hd` | The header root. `initHeader()` returns immediately without it, which is what keeps the pay flow's reduced header inert |
| `data-hd-copy` | The promo code chip. Copies to the clipboard and flips to "Copied" for 1.5s via `data-copied` |
| `data-hd-item` / `data-hd-menu` | A nav item that owns a menu, and its trigger. `data-open` on the item is the one open-state hook — desktop draws it as a mega menu, the sheet as an accordion row |
| `data-hd-sheet` / `data-hd-panel-root` | The burger and the panel it controls. `--hd-top` on `<html>` is the header's live bottom edge, set on open so the fixed sheet meets the bar whether or not the promo band has scrolled away |
| `data-hd-auth` / `data-hd-auth-panel` / `data-hd-auth-close` / `data-hd-tab` / `data-hd-switch` | The auth panel: what opens it, the panel, its two closers, the tabs and the footer's switch. `data-mode="signin\|signup"` on the panel is what hides one side of every `data-hd-when` pair |
| `data-hd-when="signin\|signup"` | Copy that belongs to one tab. **Both variants ship in the DOM** — i18n.js matches whole text nodes, so a sentence swapped in by JS would arrive untranslated |
| `data-hd-dname` / `data-hd-email` / `data-hd-pass` / `data-hd-eye` / `data-hd-terms` / `data-hd-strength{,-note}` / `data-hd-status` | The form. `dname`, not `name`: `data-hd-name` is the account handle, and `paint()` would write the visitor's handle into the sign-up field |
| `data-hd-account` / `data-hd-account-menu` / `data-hd-logout` | The chip, its popover and the one row that is a button rather than a link |
| `data-hd-initial` / `data-hd-name` / `data-hd-mail` / `data-hd-meta` / `data-hd-badge` | What a session fills. `meta` and the badges render empty until there is an orders backend — see the auth placeholder note |

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
- **One filled button per viewport.** The header's one filled action is now **Log in** (see the site
  header section) — "Start an order" is gone from the chrome, so the rule holds everywhere without a
  per-page override. `layout(nav_outline=True)` survives as a no-op parameter that callers still
  pass; it used to drop the nav CTA to an outline on the game pages.
- **Appended media queries must not out-order the existing ones.** `site.css`'s hero breakpoints are
  plain `max-width` rules at equal specificity, so a new `@media (max-width: 1200px)` block at the
  end of the file beats the `max-width: 1000px` block above it on a phone. Bound new blocks with
  `min-width` (`@media (min-width: 1001px) and (max-width: 1200px)`) or re-state what they override.

## Language and currency — `i18n.js`

Two controls, persisted together in `esb.locale.v1`. They stay independent — a French reader can
still ask for dollars — but they are **not independent defaults**. Four currencies ship: **USD, EUR,
GBP and CAD**.

- **The markets, as the business set them** (`geo.currency_for()`): the **United States in dollars,
  Canada in Canadian dollars, the UK and the crown dependencies in sterling, the rest of Europe in
  euros**, and everywhere else the dollar — which is what an international price is quoted in, and
  the only other thing there is a rate for. `EU_COUNTRIES` is derived from the timezone table's
  `Europe/…` zones, so it is the whole continent rather than the eurozone: the rule is "the rest of
  Europe", those visitors are all on the EU shard, and a Pole quoted in euros is at least quoted a
  currency the site can actually charge, which a Pole quoted in złoty would not be.
- **A location implies a currency; failing that, a language does.** `defaultCurrency(lang)` is a
  six-step ladder and **the order is load-bearing at every rung** — see the comments on it, but the
  two that are easy to get wrong: the *European zone* test has to beat the locale, or a visitor in
  Paris whose browser is set to `en-GB` is quoted in pounds; and the *American zone* test has to sit
  after the country map and before the European locale list, so Toronto-without-a-table-entry can
  still reach CAD while an American with a French browser is quoted for the market he is in.
  **English is not a market** — it is read in London, Toronto and Los Angeles — which is why
  `LANG_CUR` (`fr`/`de` → EUR) is now the *last* resort rather than the first, reached only by a
  browser that reports no usable location at all. It is resolved where the store is read, *before*
  `window.ESB_LOCALE` is published, because app.js takes its first quote off that object — deriving
  it in `init()` would paint the page in dollars and swap it. The French page used to headline
  "à partir de **$5**" over a card quoting euros, which is the same one-set-of-numbers failure a
  bare `$5` in the chrome is.
- **CAD is a default nobody outside Canada gets, and that is the point.** It ships in the switcher
  for anyone who wants it, but only Canadian traffic opens on it.
- **Every currency these tables can hand somebody must have a charge rate.** A country mapped to a
  code missing from `CHARGE_RATES` displays perfectly and is charged in **dollars** at the Stripe
  page (`charge_for()` falls back), so the buyer sees one currency and pays another.
  `test_fx_rate_mirror()` asserts it.
- **`curPinned` is the visitor's own pick and outranks both.** Only a click on the currency dropdown
  sets it (`applyCurrency(cur, true)`); restoring a stored preference at boot must not, or a
  language- or region-set currency could never be moved by a later language change. Records written
  before the default existed carry no flag, and the migration test is **not** "does it disagree with
  the language" — under the old code USD was the default in every language *and every region*, so a
  stored USD means nothing and a returning French or British visitor would be read as having chosen
  dollars and left on them. Only a stored **non-USD** migrates in as pinned.
- **A language switch re-marks every switcher**, not just the one clicked: `syncAll()` walks all
  `.loc` on the page, and three mount per document (promo bar, nav sheet, footer). Miss it and five
  controls contradict the prices beside them.
- **The currency is also the Stripe charge** (`pricing.CHARGE_RATES` mirrors `ESB_RATES`), so this
  makes EUR the default *charge* currency for French and German traffic and GBP for British traffic,
  not just the display.
- **The rate table is the allowlist, and it exists three times.** `ESB_RATES` in i18n.js (display),
  `CHARGE_RATES` in pricing.py (the charge) and `CURRENCIES` in build.py (the dropdown) must hold the
  same four codes — `test_fx_rate_mirror()` asserts all three, in both directions, because the two
  ways to get this wrong are both silent: a currency the switcher offers with no server rate behind
  it is *charged in dollars* (`charge_for()` falls back to USD), so the buyer clicks "£72" and pays
  $72; and a currency priced server-side that the switcher never offers is dead weight. The rates
  are **hand-set, not a live feed** — the site quotes whole units, so a rate that moved with the
  market would re-price every card between one load and the next.
- **CAD is `C$` on every surface, and never a bare `$`.** Canada's own `en-CA` formats CAD as
  "$72" — identical to USD — so a Canadian could not tell which currency the page was quoting.
  `CUR_TAG` pins CAD to `en-US`; **do not "localise" it to `en-CA`/`fr-CA`.** That yields CLDR's
  "CA$", and the site shows **`C$`**, so `CUR_MARK` in i18n.js overrides it — by rewriting the
  formatter's `currency` **part** via `formatToParts()`, never by string-replacing the finished
  output, because where the mark sits is the formatter's business (it leads in `en-US`, trails in
  `fr-FR`). **Four surfaces draw that mark and all four must agree**: `CUR_MARK` (the displayed
  price), the icon column of build.py's `CURRENCIES` (the switcher control), `payments.CURRENCY_SIGNS`
  (the order confirmation mail) and `CUR_SYM` in ops.js (the /ops Orders tab). The last two fall back
  to a bare `$` for a code they don't know, so a missing entry is not a broken glyph — it is a CAD
  order labelled as US dollars in a customer's inbox. `test_currency_signs()` asserts all four agree,
  that the two maps cover `CHARGE_RATES`, and that no two currencies share a mark.
- **The pound is pinned to `en-GB` formatting, the euro follows the language.** `CUR_TAG` vs
  `EUR_TAG` in `formatter()`: the euro's symbol placement is genuinely language-specific ("€72" for
  an English reader, "72 €" for a French one), but the pound is a prefix mark wherever it is read and
  a French formatter renders GBP as "72,00 £GB".
- **A wider currency mark costs vertical space on the phone**, which is half of why the mark is `C$`
  and not `CA$`. `.mb-money` wraps, and on a discounted order it carries the price, its struck
  original and the save pill: at 375px that needs 201px against 188px available in `C$`, and 237px in
  `CA$`. So the pill still drops to its own line on a game page (bar 139px, against 109px in GBP) —
  but checkout, where `CA$` pushed it to a **third** row and a 166px bar, is back to two rows and
  137px. Nothing is hidden either way, because the reserve is measured (see the `.mobile-bar`
  section) — but this is why it had to stop being a constant.

## The default server — `geo.py` + `window.esbGeo` in i18n.js

The order form has to open on *some* server, and it opened on **North America for every visitor on
earth**, so a European buyer's first act on the page was correcting the one control that decides who
can take their order. It is now resolved from where the visitor is.

- **The choice is binary — NA or EU — and that is a roster fact, not a simplification.**
  `geo.server_area()` owns the call: 35 boosters sit on NA and 47 across the EU shards, against two
  on OCE and one apiece on LATAM, SEA and KR. Defaulting somebody onto a shard one person covers is a
  slower claim and an emptier board. Every other server is still one tap away in the same control.
- **North America is the continent**, Central America and the Caribbean included (`NA_COUNTRIES`).
  They are tens of milliseconds from the NA shard and a third of a world from Frankfurt, so grouping
  them with Europe to satisfy a tidy north/south split would be wrong on the only measure a player
  feels. ⚠ **South America resolves to EU**, which is the stated rule and is the one case where it
  costs a real ping — six of the nine ladders list a South America or Brazil server. Changing it is
  one entry in `REGION_CUR`-style resolution (`_region_for` gains an "SA" area); it is a business
  call, not a technical one.
- **The signal is the edge's country when there is one, and the browser's IANA timezone otherwise.**
  `middleware.js` (Vercel Edge Middleware, the one JS file here that is not a browser asset) copies
  `x-vercel-ip-country` — the same header `geo.py` and the /ops dashboard already use — into an
  `esb_geo` cookie, which i18n.js reads synchronously at parse time. That is the only signal that
  follows the **connection** rather than the device, so it is the one a VPN, a roaming SIM or a
  traveller's laptop gets right: before it existed, /ops correctly reported a visitor as US while the
  storefront quoted them euros off their Paris system clock. **The whole cookie path is inert when
  the cookie is absent** — every local build, any non-Vercel host — and the timezone fallback below
  takes over unchanged, which is what lets the client ship ahead of the middleware.
  `serve.py` sets the same cookie locally from the header, or from a **`?geo=XX` dev override**, so
  "does a US visitor see dollars" is answerable on localhost instead of behind a VPN.
  ⚠ **`middleware.js` fronts every document request.** It must return `x-middleware-next: 1` or every
  matched URL serves an empty 200, and it must never throw. Both are asserted by
  `test_server_defaults()`; deploy it to a **preview** and click through before promoting.
- **The timezone is the fallback**, `geo.py`'s *second* choice after the edge header, and its third,
  the locale's region subtag, is the fallback when there is no timezone at all. It is a better signal than the locale here: a timezone
  says where the machine **is**, where `en-US` on a laptop in Berlin says only what language it is
  in. No request, no permission prompt, no PII. `navigator.geolocation` would need all three for a
  worse answer than a server list needs.
- **There is ONE location resolver and it is `window.esbGeo`** (`zone` / `region` / `area`), which
  lives in **i18n.js** purely because of load order: `data.js → i18n.js → app.js`, and the currency
  default has to be settled before `ESB_LOCALE` is published. `app.js`'s `serverArea()` is a
  delegation to it. Two copies of this reasoning is not a hypothetical — they existed for one
  revision and disagreed, quoting an American living in Berlin in dollars off his locale while
  sending him to the EU shard off his timezone.
- **There is one timezone table and it is `geo.py`'s.** `client_data()` derives the client's copy
  from it, and ships the **South American** zones as an *exception* list rather than the North
  American ones as a membership list: app.js reads an `America/…` zone as North American unless it
  appears there, so a zone neither table carries (`America/Regina`, `America/Whitehorse`) still lands
  on the right side of the Atlantic. `Pacific/Honolulu` is the one US zone outside that prefix and is
  special-cased. 508 bytes on the wire.
- **The estate is resolved against each game's own region list, never written down per game.** The
  nine ladders name the same two places five ways — "North America" / "North America East",
  "Europe" / "Europe West" / "EU Nordic & East" — so `regionFor()` matches the exact name first and
  the prefix second, which is what stops a game that has plain "Europe" being handed "Europe West".
  `test_server_defaults()` asserts every ladder resolves **both** estates: a game added with no
  European server would fall through to `list[0]`, which is a North America variant on all nine, and
  every European visitor would silently land back on NA.
- **It is a default, never an override — and `regionPicked` is what tells the two apart.** Only a
  touch of the Server control sets it; the geo default fills a state that has none. The migration is
  the same test `curPinned` makes and **not** the obvious one: every state written before the flag
  existed carries `North America`, because that was the old hardcoded default for every visitor on
  earth, so a stored North America is *not* evidence of a choice and is re-resolved. Any other region
  could only have got there by someone picking it, so it is kept and marked. Without this the fix
  reaches only browsers that have never seen the site. ⚠ Read the **raw parsed record** for that
  test, never the merged one — `Object.assign({}, DEFAULT, stored)` supplies a value for every field,
  so the merged object can never answer "did the stored state carry this key?". On a game change the **estate carries across** (`areaOf()`):
  someone on "Europe West" moving to a ladder that calls it "Europe" has not asked to be moved to
  America, and `list[0]` — the old fallback — would have done exactly that. A server that is neither
  estate (Oceania, Korea, Brazil) is kept when the new ladder has it and falls back to the visitor's
  own area when it does not.
- **The `<select>` ships with no `selected` option**, so the server-rendered control shows the first
  region until `paint()` writes `state.region` into it. That is one frame on DOMContentLoaded, the
  same trade the currency default makes; do not "fix" it by server-rendering a default, which would
  bake one estate into a static page cached for everybody.

### `{}` patterns in the dictionary

A key may carry `{}` placeholders — `"Our {} boosters."`, `"on the roster, all {} or above."` — and
the translation puts the placeholder where its own word order wants it. This is what makes
interpolated copy translatable at all: splitting a sentence into fragments around a `<b>` cannot move
the fragment, which is why the whole-text-node rule elsewhere says never to interpolate. Three
properties keep it safe, and all three are load-bearing:

- **Only keys written with `{}` take part**, and they are tried **only after an exact lookup misses**,
  so no existing entry changes behaviour.
- **A capture is copied through verbatim** — it is normally data (a game name, a tier, a publisher).
  The one exception is handled: a capture gets a single exact dictionary lookup on the way out, which
  is how the roster sentence's spelled count ("Thirty-one of them") lands as "Trente et un" and how
  the picks FAQ renders "Agents et rôles" inside the French sentence. A roster size that spells to a
  word with no entry passes through in English — add it rather than leaving it.
- **Keep the literal part long enough to be unambiguous.** `{}` is non-greedy but still matches
  anything; `"Starts at {}"` is about as short as one should get.

`esbT()` uses the same patterns, so a runtime string app.js builds around a game name resolves the
way its server-rendered twin does. `ANYPATS` is the pattern half of `ANYDICT`: asked once per node
before the original is stashed, so a node that only matches a pattern still restores to English.

**What is deliberately left in English**: rank and tier names, booster handles, game and publisher
names, reviewer names, payment-network brands, and the invented review/testimonial bodies — all data,
and all flagged for replacement before launch anyway. Plus the two documented figure-in-the-middle
sentences ("Last 5 of 38 games").

### Register and voice — the copy is written, not translated

Both dictionaries were reworked to read as a French and a German brand rather than an English one run
through a translator. The rules below are what that consists of; a later sweep that "corrects" them
puts the machine-translation smell back.

- **French is `tu` in the shop and `vous` in the policy copy**, and the switch is the point where the
  page stops selling and starts stating the contract: the safety & guarantee page's own hero, its
  three refund cases, the ToS admission, the measure card and its FAQ are `vous`, as are the legal
  pages and the footer disclaimer. Everything else — configurator, heroes, roster, support, checkout,
  guides, the mystery card — is `tu`. Sentences shared between the two (the three `D.GUARANTEES`
  cards) are written **impersonally** where French allows it, so they read right on either side of
  the seam. This was the user's explicit call; German stays `du` throughout, with `Sie` only in the
  legal block, because that is what a German esports brand does.
- **Gaming loanwords are kept, not translated.** French players say *roster*, *winrate*, *kills*,
  *peak*, *dispo*, *picks*, *classé*, *éco*, *half-buy*, *smokes*, *ladder*, *patch notes* — so the
  dictionary does too, and "effectif" / "taux de victoire" / "éliminations" are gone. German keeps
  *Winrate*, *Peak*, *Queue*, *Kader*, *Unranked*, *Eco*, *Crosshair-Placement*. **KDA is `K / D / A`
  in both** — the old German `K / T / A` was over-translation.
- **Words with a local meaning beat the literal one.** "Summer sale" is **"Promo d'été"**, never
  "Soldes": *soldes* names two state-fixed periods in French law, and a shop using it outside them has
  a DGCCRF problem, not a copy problem. Discord's own French UI says *salon*, not *canal*. Trustpilot's
  German label for this score is *Hervorragend*, not *Ausgezeichnet*. Valorant's German client names
  the roles *Duellant / Initiator / Wächter*.
- **French typography is applied to every value**: `’` for apostrophes, and a no-break space before
  `% : ; ? !`, inside `« »`, and in thousands separators. German gets the no-break space before `%`.
  They are real U+00A0 characters in the source — that is deliberate, and it is what stops a price
  wrapping away from its `%`.
- **The `{}` capture that spells a count needs its word in the dictionary.** `Four` / `Twenty-nine` /
  `Thirty-one` are entries for exactly that reason; a roster size that spells to a word with no entry
  renders the whole sentence's capture in English.
- **A key that carries a figure goes stale the moment the figure is re-tuned, and it fails silently** —
  the sentence just renders in English on the French and German pages. Four had already drifted this
  way (the catalogue's Valorant-vs-CS2 answer, the SPLIT15 answer, checkout's email note and the
  /orders sign-in prompt). **When you re-tune pricing, bundles or promo copy, grep the dictionary for
  the old figure**; there is no test for this. The cheapest check is to load a page in `fr`, walk the
  DOM and look for anything still in English.
- **Attributes take the `{}` patterns too.** `translateAttrs()` falls back to `patTranslate()` for the
  same reason text nodes do: the promo chip's accessible name is assembled from the live code and
  percentage ("Copy discount code SPLIT15 — 15% off"), so a fixed key would be stale on the next sale
  — and per the header section that label is the **only** place a screen reader hears the discount.
- **German has parity with French, and it has to keep it.** Every key in the `fr` block now has a `de`
  entry (`de` carries one extra, `"boosters"`). 217 were missing and were shipping the support page,
  the free-guides landing, the nine game pages' proof bands, the bundle strip, coaching and the unit
  grids to German readers **in English**. Adding a French entry without a German one re-opens that
  hole silently.
- ⚠ **`"queue"` translates to the empty string in both languages, on purpose.** It is the middle
  fragment of `VETTING["strip"]` (`pre` + `<b>Discord</b>` + `mid` + …), and neither language wants a
  word after the server's name there. An empty value is a legal translation (`d[core] !== undefined`
  is the test); do not "fix" it to a word.

## Mobile rules — the `MOBILE PASS` block at the foot of site.css

The last section of `site.css` is a set of corrections found by walking every page at 375px and
320px. Each one is a rule that has to *beat* the component rule it fixes, so the selectors restate
the specificity of what they override (`.ob-two .ob-select`, `.co-code-box .co-input`) rather than
relying on source order. Everything in it is bounded by `max-width`, so none of it can reach the
desktop layouts the handoffs were ported against — that is the property that lets the block sit last
without breaking the ordering rule above. Four things in it are load-bearing:

- **Form controls are 16px below 1000px, and that is a threshold, not a taste.** Mobile Safari zooms
  the viewport whenever a focused `input`/`select`/`textarea` renders under 16px and does not zoom
  back out. Every control on the site was 13.5–15.5px, so it fired on the checkout form, the support
  form, the application, the demo lookup, the guides capture, the header auth panel and every rank
  select. 15.5px still zooms. If a new field is added, it goes in that selector list.
- **A `<select>` in a flex row is only as tall as its own text.** `.ob-field` / `.co-field` /
  `.bs-tiersel` draw a 33–46px control, but `align-items: center` left the select 15–18px, so taps
  on the top and bottom thirds of a rank or region field did nothing. The select is stretched
  (`align-self: stretch`) and the mark and caret are pinned back to centre. Any new field built on
  that pattern needs the same pair.
- **Short controls grow an invisible `::after`, never padding** — the technique `.rv-dot::after`
  already used, because padding on the element itself is painted by its background or moves the row.
  The expansion is **vertical only** so it can never reach a control beside it, and three of them
  (`.hd-forgot`, `.hd-switch-a`, `.hd-eye`) carry clamped insets measured against their real
  clearance: they stop at 35–48px rather than 44 because the space is not there without moving the
  handoff's rows, and an overlay that reaches the password field steals that field's taps. If you
  add one, measure the gap above and below first — this is verifiable, not a judgement call.
- **`body { overflow: hidden }` does not lock scrolling on iOS.** `lockScroll()` in app.js pins the
  body (`position: fixed`) and parks the offset in a negative `top`, handing it back on close — the
  naive fix trades a scrolling background for the page jumping to the top every time the menu opens.
  Both the sheet and the auth modal go through it; `.hd-locked` stays on the body for anything keyed
  off it.

`initScrollHints()` is the fifth piece and lives in app.js: the rails that genuinely overflow
(`.ob-tabs`, `.ob-bundles-grid`, the chip rows, the catalogue's chips and service rail) get
`data-scrollhint`, which CSS draws as a
right-edge fade, and `data-scroll-end` clears it at the end of the scroll. It is set from JS and not
in the markup because whether a rail overflows depends on the width, the language and the game's own
tab set — a fade over a row that already fits points at nothing. This is what stopped the game
page's Coaching tab from sitting off-screen with nothing saying the row moved.

## The site header — every page mounts it

`chrome()` is the **"Site header + authentication"** handoff (`design_handoff_site_header`), two
screens (1440 / 390) built as one component with breakpoints. It is the sixth scoped port after
`.hero-a` / `.co` / `.gg` / `.dsh` / `.rst` — tokens on `.hd` (plus `.hd-promo`, `.hd-account`,
`.hd-auth`, which are its siblings in the document), product radii per element, sentence-case
controls, nothing leaking past the scope. It replaced a utility bar carrying a promo *sentence* and a
three-column nav whose menu was centred in ~400px of dead space either side.

The pieces: `hd_promo()` · `hd_live()` · `hd_nav()` · `hd_menu()` / `hd_card()` / `hd_rail()` ·
`hd_actions()` / `hd_chip()` · `hd_auth()` · `hd_account_menu()`. `chrome_min()` is unchanged and is
still what `layout(bare=True)` renders on checkout.

- **One DOM, two presentations.** The nav items, their menus and the auth panel are emitted once. On
  desktop `.hd-panel` is `display:contents` and the menus are full-bleed panels hung off the sticky
  bar; below 1000px the same nodes *are* the sheet and its accordion, and the auth modal becomes the
  bottom sheet. Emitting the menu twice is how the two versions drift apart.
- **The mega menu is positioned against `.hd`, which is the sticky element.** Nothing between the
  panel and `.hd` may be given `position` — the panel is `left:0;right:0;top:100%` and resolves to
  the nearest positioned ancestor. The promo band is deliberately *not* sticky: the handoff's
  recommendation is to keep the 68px nav and let the 38px bar scroll away.
- **Log in is the filled button and "Start an order" is gone.** The old header put an ember *outline*
  on a CTA that already appears in every hero and every closing band — loud enough to read as
  primary, styled as secondary, and the fifth copy of one button on the page. The header's own job is
  account access. This was the user's explicit call in the handoff.
- **Every menu card points at a page this build produces**, the same rule `NAV` follows. The
  handoff's "Booster leaderboard" and its own FAQ page do not exist here, so those slots went to
  `/reviews.html` and the guarantee page's FAQ band — which is why `page_guarantee()` now carries
  `id="safety"` and `id="faq"`, and `vetting_card()` carries `id="vetting"`.
- **Every figure is read, never typed.** Prices come from `from_price()` through `money()` (so the
  menu re-quotes in EUR with the rest of the page — a bare `$5` in the chrome is exactly the CRO
  finding this build answers), counts from `D.STATS`, the top booster from `D.SPOTLIGHT`. The
  handoff's "34 boosters" and "+10% for a named booster" are both stale: the roster is counted, and
  `pricing.py` charges nothing for a named booster, so the card says **"no extra fee"**.
- **A nav item with a menu is a `<button>`, so the hub page is unreachable from the nav without JS.**
  Two things cover that: the hub is the first (or last) card *inside* its own menu — `/games/`,
  `/boosters/`, `/guarantee.html` — and `layout()` writes `<html class="no-js">` with an inline head
  script that strips it, which site.css uses to open the menus on `:hover` / `:focus-within` at
  desktop width. Do not remove either half; together they are why the nav still reaches nine ladders
  with scripting off.
- **Only one surface is open at a time**, and every one closes on Escape and on an outside click,
  returning focus to its trigger. Desktop menus also open on hover with a 120ms enter / 250ms leave
  delay — the leave delay is what stops a diagonal mouse path to a card in the panel's far corner
  from closing it underneath the pointer.
- **The sheet is `position:fixed`, not in flow.** The mock is a 390×860 frame; a real page is not,
  and a sheet that pushes 4,000px of content down leaves the visitor scrolling back to the header.
  `--hd-top` is set from the header's live `getBoundingClientRect().bottom` on open, on scroll and on
  resize. The sheet also hides the page's `.mobile-bar`, which otherwise sits on top of the last
  accordion section quoting a configuration the visitor has navigated away from.
- **The accordion opens section 0 when the sheet opens** (the handoff's default). It cannot be marked
  open in the HTML — the same `data-open` attribute renders the Games mega menu hanging open on load
  at desktop width.
- **The availability line is a status, not a statistic.** It opens with a word rather than a digit,
  the dot sits in a soft green halo, and it pulses over **2.4s** — slower than the site's 2s dots,
  because this one runs on every page. Below 1000px it moves out of the bar and into the sheet: three
  groups do not fit at that width and the sale is the more time-sensitive one.
- **The code chip is a copy button.** A dashed border with no button chrome is the whole affordance —
  it reads as a coupon, and a code you cannot click is a code people mistype. It confirms for 1.5s.
  The handoff drops the old "-15% off with code" wording; the percentage is not lost, it rides in the
  chip's accessible name so a screen reader still hears the discount.
- **i18n**: every figure and separator rides in its own `<b>` / `<i aria-hidden>` so the words around
  it stay whole translatable nodes, and **both auth tabs' copy is in the DOM** with one side hidden
  for the same reason. Menu card notes are one node per service — the words are already dictionary
  keys, because the games grid renders the identical list as chips through `services_of()`; joining
  them into a sentence would leave the menu quoting English services beside a French grid. Card names
  and every panel string are in both `fr` and `de`.
- **Breakpoints follow the site's 1200/1000/760**, not the handoff's 1280/1024/768. 1200 tightens the
  nav, drops the Demo button and takes the card grid to 2 columns; 1000 is the whole mobile pattern
  (brand, Log in, burger, sheet, bottom-sheet auth); 760 is the phone promo bar. The handoff draws
  1440 and 390 and asks for the middle to be confirmed with the designer.

Deviations from the handoff, all deliberate: the brand lockup stays the site's shard, not the
handoff's lightning bolt (the nav, the footer and the auth panel have to be the same mark); glyphs
are inline `_ico()` linework rather than the Phosphor font, since this build ships no icon runtime;
game marks and the Discord/Google marks are generic shapes, the same trademark rule `pay_marks()` and
the Trustpilot star follow; the optional-account note is kept at phone width, where the handoff makes
it desktop-only, because the guest-checkout contract matters most where the traffic is; and
`/demo.html` keeps the full header rather than the reduced one — the handoff strips "track-order"
because a buyer is mid-task there, but on this site that page is a browsable demo the nav and the
footer both link to.

## The Best Sellers band (homepage)

`bs_band()` is the `design_handoff_best_sellers` handoff — a compressed order flow between the hero
and the games grid, ported at full fidelity with its own tokens on `.bs`, same arrangement as the
game-page card. Two screens are designed (1440 and 390) and both are implemented as one component
with breakpoints, not two.

- **Clamp the end the user touched; never move the other one.** This is the handoff's headline fix
  and it is easy to regress. `setNode()` clamps only the value just chosen, and anything out of range
  renders `disabled` (`nodeOk()` / `tierOk()`) so the limit is visible before the tap. The old rule
  moved the untouched end, which silently demoted the player's current rank and made **Bronze IV →
  Bronze III unorderable**. There is no test suite — if you touch the picker, check that one climb.
- **Switching tier keeps the division numeral** (`tierNode()`), so Bronze IV → Silver IV is one click.
- **Switching game resets to `from = node 0`, `to = node 12`** — ranks do not carry across ladders.
- **The band shares `quote()` with the game pages.** The same climb must never quote two prices.
- **The mobile screen swaps the tier grid for a native `<select>`** with the same disabled options —
  an 8-tile grid clips every label at 390px. Both controls are always in the DOM; CSS picks one.
- **The handoff's sticky mobile price bar is deliberately not built**: this site already has the
  page-level `.mobile-bar`, which does the same job across the whole page. Two would stack.
- Retired with the old calculator: `data-ladder`, `data-step-prompt`, `.gsel`, `.ladder`, `.tier`,
  and the `next`/`guided` state keys. `.calc` / `.calc-head` / `.calc-kicker` / `.calc-figs` survive
  — track, checkout and reviews still use that panel shell.

## The game-page hero + order card

The card's **rank controls** are a later handoff of their own —
**`design_handoff_configurator`**, "the live-pricing configurator", two screens (desktop in a 470px
column, mobile at 390). It re-drew the one thing every order goes through, and everything below
about the card still holds; what it replaced was the rank *field*:

- **Each end of the climb is a framed plate** (`rank_plate()` → `.ob-plate`): a label, a selector
  row — 40px emblem tile · tier name · "change tier" · a two-headed caret — and the tier's divisions
  as a row of filled pips. `.ob-rank-target` is the accented one. The unit tabs draw the same object
  at full width (`unit=True`); see the Net wins / Placements note further down.
- **The `<select>` is invisible, laid over the whole selector row** (`.ob-tiersel`, `opacity: 0`,
  `inset: 0`). A visible native select is as wide as its widest option, which stranded "Iron" a
  whole "Platinum" from the rest of the row; the old control worked around it by measuring the
  label and sizing the select to it in JS. The row is the hit target, the real control still
  supplies keyboard and screen-reader behaviour, and `sizeTierSelect()` is gone. Do not revert it
  to a visible select. It carries `font-size: 16px` for the same reason every other field does —
  iOS zooms a focused control under 16px, invisible or not.
- **The emblem is one drawing, tinted per tier in CSS.** `_EMBLEM` is a hand-drawn winged orb (tier
  emblems are publisher IP — the same rule `pay_marks()` and the Trustpilot star follow). Its four
  shapes are `color-mix()`ed off `--tier`, which `data-rankcolor` sets on the plate, so it works on
  all nine ladders with no per-game code and can never drift from the site's other rank marks. The
  target end runs one step brighter. `fill` presentation attributes are the no-`color-mix` fallback.
- **The plate's own measurements are 36px emblem / 12px padding / 8px selector padding, where the
  handoff draws 40 / 14 / 10.** That is not a style tweak: the handoff calls 40px a *fit* constraint
  (it went 48 → 40 so League's longest tier name sat whole beside it) and asks for a re-measure if
  the copy changes. It did — nine ladders, up to "One Above All" — so the same trade goes one step
  further and the pixels go to the name. See the two fitting passes below.
- **Clamping is unchanged and still load-bearing**: clamp the end the user touched, never move the
  other one; out-of-range tiers arrive as `disabled` options and out-of-range divisions render
  disabled, so the limit is visible before the tap. **Bronze IV → Bronze III must stay orderable** —
  there is no test suite, so check that climb by hand after touching the picker.
- **On the phone the plates stack**, the labels change from "You are" / "You want" to "Current rank"
  / "Target rank" (both wordings ship in the DOM and CSS picks one — i18n.js matches whole text
  nodes), the arrow becomes a ring centred in a hairline rule with its glyph rotated down, and the
  pips grow to 44px.

`page_game()`'s first section is otherwise the **"Ladder card"** handoff
(`design_handoff_lol_boost_hero`),
which replaced two bare rank `<select>`s. It is ported at **full fidelity, including its own tokens**
— this is the one deliberate exception to "layer on Ashfall". The handoff's palette, radii and
sentence-case control typography are declared on `.hero-a` in `site.css` and nothing leaks past it:

- `--ember`/`--ember-grad` are **re-declared on `.hero-a`** to the handoff's `#ff5a1f`, so existing
  component rules (`.btn-primary`, `.seg-opt:has(input:checked)`, `.tab[aria-selected]`) pick the
  handoff accent up without a single `!important`. Do the same for anything else you add there.
- Radii are explicit per element (6 division · 7 mark/segment · 9 field/row · 10 ladder/CTA ·
  14 card · 5 checkbox · 999 pills), **not** `--radius`. Ashfall's 2px would flatten the card.
- Ashfall uppercases and tracks its controls; the handoff draws tabs, the card title, the segmented
  control and the CTA in **sentence case**. Those overrides are why `.ob-tabs .tab`, `.ob-title`,
  `.ob .seg-opt` and `.ob-cta` restate `text-transform`/`letter-spacing`.
- Type is Inter already — `type-b-sans.css` owns `--display`/`--body` site-wide and loads last.

Things that are load-bearing here:

- **The card is generic, not LoL-only.** `rank_plate()`, `ladder_strip()` and `wizard()` read
  `tiers`/`divmap`/`prices` out of `data.py`, so all nine game pages get it and a new game needs no
  code. Tier mark colours come from `TIER_COLORS` with a positional ramp fallback — an unnamed tier
  is never a missing colour.
- **"Cheapest single division $N" is quoted, not typed.** `ladder_strip()` runs `pricing.quote()`
  over every rung and takes the minimum, so it and the H1's `from $N` are the same claim and cannot
  drift apart. The handoff calls this out as the bug it was fixing — keep the property if pricing
  is re-tuned.
- **Duo's "+55%" is read off `pricing.DUO_MULT`**, so the label can't drift from the formula.
- **The CTA has to clear the fold at 1440×900** (the one measurement the handoff carries from the
  mock). It currently lands at **881–895 across the nine games** — the framed rank plates cost ~59px
  a side and that is where the old ~833–883 slack went. Anything added to the card comes out of what
  is left, which on Dota 2 and Rocket League is single digits. Measure every game, don't eyeball one:
  the ladders whose tier captions wrap to two lines are the tall ones.
  Two things were given back to pay for the plates, and both should survive a re-tune: `.ob-sum`
  spans its left column across both grid rows, so the block is as tall as its taller *column*
  rather than the left column plus the availability line (~24px, and it is also how the
  configurator handoff draws that stack); and `.ob-track` is 26px rather than the handoff's 30,
  because the tallest thing in it is the 16px target dot 1px off the bottom.
- **Availability lives in the card, not the hero stat row.** "N of M boosters free now" sits beside
  the delivery estimate, where it argues for ordering now; the hero's third stat is boosts delivered.
  Putting a roster count in both places is how the two conflicting numbers got shipped last time.
- **The card shows three add-on rows, and it is three in both queues.** Four ship in the DOM:
  **"Watch your booster play"**, Priority order, and a **mode-conditional pair** — Solo is offered
  "Solo only queue", Duo "Play on your schedule" — of which one is always `hidden`. Emitting both is
  the whole-text-node rule (a label written in by JS arrives untranslated), and hiding one is what
  keeps the row count, and so the card's height, the same whichever queue is picked. **Three is the
  budget, not a preference**: a fourth row costs ~51px and puts the CTA under the fold at 1440×900 on
  six of the nine ladders (measured — see the fold note below). Both inclusions are therefore flagged
  `incl` in data.py and render in **no** picker; they are stated instead, by `ob_included()` under
  the card's CTA (free of the fold budget, which is the whole reason it sits there) and by checkout's
  green strip. `addons_block(paid_only=True)` is checkout's upsell only — a ticked, disabled row is
  not a "last chance to add", but the free-but-optional row **is** kept there, because an untaken
  free option is the strongest thing that block can offer.
- **Add-ons have THREE states, and the third is `was_pct`.** `pct > 0` is a paid option; `pct == 0`
  with no `was_pct` is an inclusion (ticked-and-disabled, or `incl` and not drawn at all); `pct == 0`
  **with** `was_pct` is **free but optional** — an ordinary empty checkbox the buyer has to tick,
  carried in `state.addons` like any paid option and charged nothing, because `_addon_total()` on
  both sides skips a zero `pct`. `D.addon_is_free_opt()` is the discriminator, mirrored by
  `isFreeOpt()` in app.js. It opens **unticked** — app.js's "a zero-cost add-on is always on" rule
  has an explicit exception for it, and `test_free_optional_addons()` locks that, the $0 charge on
  every game × queue × bundle path, and the JS mirror.
- **The struck figure beside it is `pricing.addon_list_price()`, and it is the site's one reference
  price.** ⚠ Worth knowing before you touch it: `quote()` takes the sitewide discount off the boost
  alone *specifically* so its strikethrough is "never a grossed-up reference price" (the comment is
  still in pricing.py). This row is the deliberate exception — 50% of the boost, struck, beside the
  live "+$0". Two things keep it as defensible as it can be: it is quoted by the **same arithmetic
  and the same `addon_base`** a real charge would use (so on a bundle it strikes 50% of the bundle's
  flat price, not of the list climb — the trap that inflated add-ons before), and it is display-only,
  never summed. It is a **business call, not a technical one**; if legal wants it airtight the fix is
  `D.STREAM_WAS_NOTE`, the one string naming what the figure refers to, not the number or the markup.
  ⚠ `D.STREAM_CLAIM_VERIFIED` is `False`: "Only site that gives it free" is an unsubstantiated
  comparative claim, same standing as the placeholder statistics.
- **A free option still has to reach fulfilment.** A paid add-on is implied by the amount; a free one
  moves no money and would arrive at the board with nothing recording that it was asked for — and
  this one is an obligation on whoever claims the order. `payments.build_session()` therefore carries
  `metadata[addons]` (queue-filtered by the same `addon_applies()` call `quote()` makes), both
  order mails state an **Options** row through `_addon_names()`, and `payments.order_row()` writes
  the ids into the **orders store**, which is the only record anybody can look up after the mail is
  read — the /ops drill-down's "Options chosen" table is that row. ⚠ **Every field in that row comes
  from Stripe metadata, so a product fact that exists only inside `metadata[detail]`'s sentence is
  not recorded**: the row carried no add-ons at all for a while, and the unit count and coaching pack
  were silently clamped to their minimums, which states a figure nobody bought. Adding a product
  option means adding it in `build_session()` **and** `order_row()`; `test_pricing.py`'s
  `test_order_row_records_what_was_bought()` walks the round trip for all four products. ⚠ The live
  half of the feature is still not built — see
  [Watch live](#watch-live--the-boosters-screen-share--watch_panel).
- **The queue owns its add-ons on both sides.** `D.addon_applies()` (mirrored by `addonApplies()` in
  app.js) is the filter, and `pricing.quote()` re-applies it, so the other queue's option is never
  charged whatever the payload says. app.js drops it from `state.addons` on the mode change and once
  at load, or the receipt would list a row the server does not bill. Since `payments.build_session()`
  refuses to charge a total the page did not show, the two filters agreeing is not cosmetic — a
  drift here is a failed checkout on a valid order. `test_addon_modes()` covers it.
- **Only one add-on's name is per game** — the picks one. `picks` on each game in data.py names it
  ("Champions & roles", "Agents & roles", "Playlist & playstyle"), read through `D.picks_label()`;
  `D.picks_noun()` derives the bare noun the game-page FAQ builds a sentence around, so the two
  cannot drift. A game page renders its own wording; **checkout ships all nine** behind
  `data-when-game` and shows the order's, because it is one static page for all nine.
- **Add-on notes must stay one line, and `.ob .opt .note` now enforces it** with
  `nowrap`/`ellipsis` — the same floor `.ob-cap` puts under the tier captions. A second line costs
  ~14px of the fold budget, and the width a note gets is **not a constant**: the price column beside
  it grows with the game's own prices and with the currency mark (League's `$52 +$0` is ~25px wider
  than Rocket League's, and `C$` wider again), so one sentence fits on one ladder and wraps on the
  next. Every translation is longer than the English, too — the FR and DE notes for the stream,
  priority, solo-queue and schedule rows were all over the line and were shortened. Clipping makes
  the row height deterministic in every language, game and currency; the copy is then written short
  enough that nothing reaches the ellipsis. **Shorten the sentence, don't remove the guard** — and
  keep new notes inside ~62 characters. Checkout deliberately still wraps: no fold budget there.
- **The free-but-optional row is drawn as the offer it is, and the hierarchy is bought without
  height.** `.opt-freeopt` gets a green tint, a green border, a bold name and a **"FREE" flag**; the
  4px of padding it gains is taken back off the two paid rows below it, so the block's total height
  is unchanged and the CTA still clears the fold on all nine ladders in all three languages (832–900
  measured). Green, **not ember**: ember is the CTA 60px underneath, and a second ember block there
  makes two primary actions out of one — green is already the site's free/included/live colour. It
  stays green when **checked**, which needs `.ob .opt-freeopt:has(input:checked)` to sit *below*
  `.ob .opt:has(input:checked)` in the file: they tie on specificity and it wins on source order.
- **⚠ The flag's text is uppercase `FREE` in the MARKUP, never `text-transform`.** i18n.js matches
  whole text nodes **case-sensitively**, and `"Free"` is already a dictionary key — the roster's,
  where free means *available* and French renders it "Libre". A lower-cased flag here would put a
  green pill reading "Libre" beside a price. `"FREE"` is its own key (GRATUIT / GRATIS).
- **Two things in the card size themselves to the game's longest tier name, and both measure the
  text rather than the box.** Tier *count* is not the test — Dota's eight long names overflow where
  Valorant's eight do not.
  - `data-tier-caps` (the ladder captions) steps 9.5 → 8 → 7.25px and releases `nowrap` at the two
    small steps, because no size fixes a two-word tier on its own: "Grand Champ" measures 56px at
    7.25px against Rocket League's 49px cell and has to break at its space. A caption cell is a
    `1fr` flex item, so **its `scrollWidth` always equals its `clientWidth`** whether the name fits
    or not — the original test compared exactly those two and was therefore true on every ladder,
    pinning all nine games to the small step and detecting nothing. It measures a `Range` over the
    contents now. `.ob-cap` carries `overflow: hidden` as the floor under the ramp: a 9-tier ladder
    cannot label "Grandmaster" (57px at 7.25px, 43px cell) at any legible size, and a clipped
    caption inside its own cell beats one painted over its neighbours.
  - `data-tierfit` (the rank plate's tier name) steps 17 → 15 → 13.5 → 12.5px. 17px is the
    handoff's, and it was drawn against League, whose longest name fits with room to spare;
    "Grandmaster" and "One Above All" do not, so Marvel Rivals, Overwatch 2 and Rocket League land
    on 13.5px and the other six stay at 17. It is sized off the game's **widest** name, not the one
    on screen, or the type would resize under the reader on every tier change and the two plates
    would disagree.
  - Both cache the verdict per game, and both re-run on `document.fonts.ready` — a first render
    measures the fallback face, and a verdict reached there would otherwise stand for the visit.
    `data-tier-caps` also skips measuring while the Division panel is `hidden` (the other three
    tabs): every cell reads zero there, which "fits nothing" and latches the smallest step. That is
    what `data-fit` is for, kept separate from `fillCells`' `data-for` so a skipped measurement is
    retried rather than remembered.
- **i18n matches whole text nodes.** `translateTextNode()` looks up a node's entire trimmed value,
  so interpolating a number or a separator into a translatable string silently un-translates it —
  this is why the CTA is `<span>Continue to checkout</span><span>·</span><span data-out="price">`
  and why "N of M boosters free now" is split into `of` + `boosters free now` around its `<b>`s.
  Add new card strings to both `fr` and `de` in `i18n.js`.

### The `design_handoff_lol_game_page` port — the whole game page

`page_game()` is a **full port of the LoL game-page handoff** — the hero configurator plus the six
proof bands and the close. The old below-the-fold layout (three-step block + booster table + guarantee
cards + reviews grid + FAQ split + "Other games" + marquee) was **replaced wholesale**; only the
pricing was kept (the shared engine). The bands, in order, are numbered `.gp` sections scoped on their
own ember token set:

- **01 How it runs** (`gp_how`/`gp_steps`) — four step cards (icon tile, ghosted number, body, a
  proof line pinned with `margin-top:auto`). Step 02 names the game ("a verified League booster").
- **02 While it runs** (`gp_while`) — copy + `GP_WHILE_POINTS` (this handoff's three, not the
  homepage's `D.DASHBOARD_POINTS`), with `dash_mock(gp=True)` on the right. That variant is the
  handoff's arrangement of the shared card: each rank led by its mark, the "In progress" pill on the
  climb row (there is no order bar), no match-history title row, "Start ·" captions, and the game
  count in the footer. Same component as the homepage and `/demo.html`, so they cannot drift.
- **03 Who plays it** (`gp_who`) — copy + three booster cards from this game's `D.BOOSTERS`, the #1
  card accent-bordered; "See the roster" → `/boosters/`. The count and the "Master or above" floor
  are both read off the roster, never typed.
- **04 Safety** (`gp_safety`) — the ban-pattern argument named to the game's publisher
  (`D.publisher()` / `D.PUBLISHERS`, e.g. "Riot flags accounts on patterns…"), the ToS admission in a
  framed plate with a caution-amber (`#c9955f`) glyph, and a five-row "what that means per order"
  card from `GP_MEASURES` (the handoff's wording of the same commitments `SAFETY["measures"]` states
  elsewhere — ⚠ each still needs ops sign-off).
- **05 Reviews** (`gp_reviews`) — three cards: stars, a **neutral** climb tag (not accent — three
  ember pills would out-shout the reviews), the body, then an initials avatar + reviewer name +
  relative date and a green Verified mark. Names come from `D.REVIEWS[].by`/`initials`, which
  `data.py` assigns deterministically from `_REVIEW_NAMES` — ⚠ **invented**, same standing as the
  review copy. The aside is the rating, the Trustpilot count and "Read them all".
- **06 FAQ** (`gp_faq`/`gp_faq_items`) — the handoff's six questions, with every figure read off the
  engine (duo % from `pricing.DUO_MULT`, the champions add-on from a real quote difference). Sticky
  left column; native `<details>` so all answers are in the DOM for the FAQPage JSON-LD and the band
  works with no JS, numbered, with a drawn +/− toggle and an ember-bordered open state. Single-open
  is one `toggle` handler in app.js on `[data-gp-faq]`.
- **Close** (`gp_close`) — the handoff's close, **not** the shared `cta_band()`: headline, two inline
  guarantees, the live config line + total, and one uppercase filled CTA. It reads the same
  `data-out` hooks as the order card, so the two quote one number.

The hero carries **no service-chips row and no guarantee/note rows** — the handoff ends the left
column at the bundle strip (which sits above a 1px rule). On mobile the stat row stays **above** the
configurator and abbreviates (`.stat-k-sm` / `.stat-n-sm`: "Trustpilot / To claim / Delivered" and
92,400 → 92.4k), and the "Home" crumb drops — all per the handoff's 390px screen.

The design prototype renders: copy `redesign_zip*/design_handoff_lol_game_page/` into `site/dist/`
and open it through the preview server to diff a band against the build. Delete it before shipping
(a rebuild wipes `dist/` anyway).

Then the three hero-level additions, all layered onto the existing configurator and the **one shared
pricing engine** (no per-page formula — the deliberate call was to keep `pricing.py` / `app.js quote()`
authoritative for the whole site, not adopt the handoff's separate PER_TIER model, which League's
`prices` table already implements anyway):

- **Coaching is the fourth tab** (`data-service="coaching"`), shown only where `offers_coaching(g)`
  is true (the game's `services` string mentions coaching — LoL/Valorant/Rivals today). It is a
  booking, not a climb: `pricing.quote()` and `app.js` gain a `service == "coaching"` branch priced
  as `coach.rate * pack.hours * (1 - pack.disc)` and **nothing else** — no rank, no duo, no add-ons,
  no sitewide promo. The pack discount rides in the `discount`/`subtotal` fields so the struck price
  and save line read it like a promo. `D.COACHES` / `COACH_PACKS` / `COACH_FOCUS` / `COACH_SLOTS`
  are **placeholder** (invented coaches/rates/slots; calendar + payment unbuilt). State: `coach`,
  `pack` (indices), `focus` (index set), `slot`. The shared summary/CTA re-read per product via
  `data-hide-service` (hide queue/add-ons/boosters-free/"Continue to checkout" on coaching) and
  `data-when-service="coaching"` ("First session", the coaches-taking-bookings line, the `bookLabel`
  = "Book N hours"). Checkout charges coaching correctly (server re-quote), though its summary still
  labels the row "Climb" and its add-on rows quote +$0 — the handoff flags "what Continue carries
  into checkout" as not-designed; refine on the checkout page, not here.
- **Net wins / Placements are a 1–5 grid** (`unit_grid()`), not the old ± stepper — five per order is
  the product cap (`pricing.UNIT_MAX = 5`), shown as five exposed buttons with a live **"$N per game"**
  (`data-out="winsUnit"`/`placementsUnit`, quoted at one unit / current rank) and a per-product note.
  Placements opens with an **"I have a rank / Unranked"** toggle (`data-ranked`); Unranked hides the
  rank control (`data-when-ranked`) and shows the plate (`data-when-unranked`), and `state.unranked`
  prices at the ladder floor (`climb = 1`) on both server and client.
  The rank above each grid is **the same `rank_plate()` the climb draws**, one full-width copy
  (`rank_plate(g, "from", sfx, unit=True)` → `.ob-plate-unit`, and `sfx` is what keeps the three
  `<select>` ids unique). It replaced a second, smaller rank control that lived only on these two
  tabs: one tab apart, the same question was asked with a different widget, a different selected-
  division treatment (outline vs the plate's filled pip) and a select that needed JS width
  measurement to sit beside its mark. The unit plate labels itself "Current rank" at every width —
  it has no second plate beside it for "You are" to be read against.
- **The bundle strip** (`bundle_strip(g)` in the hero, `D.BUNDLES` / `bundle_climbs()`) is the
  handoff's "Save big on bundles": each card is a multi-tier climb at a **flat hand-set price**
  (`(ft, tt, price)` in `D.BUNDLES`, whole USD) that **replaces the sitewide sale** on a matching
  climb. **The price is the stored figure; the `−N%` pill and the struck price are derived from it**
  against the full climb (`pricing.bundle_pct()` / `full_bundle_price()`), so the badge can never
  claim a cut the checkout doesn't charge and re-pricing a bundle is one number in one place.
  `pricing.quote()` reads `state.bundle` and `data.active_bundle()` re-verifies the match
  server-side. Opt-in, never auto-set: `data-bundle` click sets `state.bundle` + configures the climb
  (keeps the current division in the lower tier). It **survives a division change, drops on a tier or
  target change** (`bundleAfter()` in `setNode`, `bundleDiscount()` in `quote`). `aria-pressed` =
  Applied. On mobile it is a horizontal swipe rail after the configurator (`.hero-copy` order 3).
  The ladder foot reads "Played in your preferred hours" and the queue control "Duo +55%".
  - **Applying a bundle must never cost more than not applying it.** This is the rule the price model
    exists to serve, and it is not automatic: a bundle is a *flat* price across its whole from-tier
    (priced as that tier's bottom division → target), so the buyer at the tier's **top** division is
    ordering the shortest climb and is the one a too-high flat price penalises. The price therefore
    has to sit under the cheapest normal order in the tier — that top division's climb, at the
    sitewide sale. Under the old percentage ramp, four of League's six bundles and five of Valorant's
    six charged a penalty for opting in (up to +$24), while the card advertised a saving. Two things
    keep it fixed: the League prices are set $1–4 under that line, and **add-ons on a bundle are a
    percentage of the bundle's price, not of the inflated list climb** (`pricing.quote()`, mirrored in
    app.js) — without that, ticking Priority cost $3 more on the bundle than on the plain order and
    re-created the trap on its own. `test_bundle_never_costs_more()` walks every bundle × division ×
    queue × add-on set. It **hard-fails only for the games in the test's `PRICED_GAMES`** (League
    today) and prints a `PENDING` line for the rest, which still carry the handoff's converted ramp
    and still have the penalty — add a game there the moment its prices are set by hand.
  - **A bigger climb must never cost less than a smaller one it contains.** The old ramp priced
    Iron → Diamond ($234) *under* Bronze → Diamond ($239). `test_bundle_rules()` asserts it now.
  - **All nine games carry a set**, so the strip renders on every game page (it still renders nothing
    for a game with no `BUNDLES` entry). ⚠ Only **League** is priced; the other eight are the
    handoff's invented ramp converted to the same money it was already charging, and are a business
    call before launch. One rule should survive that re-pricing: **the top rank of a
    ladder is never a bundle target** — Predator, Challenger, Immortal, One Above All, Supersonic,
    Champion, LoL's Master and CS2's 30k are cutoff- or leaderboard-gated, and each game's own `note`
    says those orders are quoted per order, which a fixed advertised price cannot be.
  - **Every label is read off the ladder, never typed** — nine ladders number their divisions five
    different ways (IV–I, 1–3, 1–5, 5–1, I–IV) and CS2 has none. The card names the resolved target
    rank (`b['target']`), so Valorant reads "Iron → Silver 1"; it used to append a literal `IV` and
    quoted Valorant a division that does not exist. The sub-line is "From any *tier* division" only
    where that tier has divisions, else "Starts at *rung*", and the head note swaps "tiers" for
    "rating bands" on a flat ladder. A card with a single-rung from-tier has `floorFrom == defFrom`.
  - **The name wraps at the arrow, by construction.** Each end is a nowrap `<span>` and the only
    break opportunity is a `<wbr>` after the `<i>` arrow, so a long name ("Diamond → Grandmaster
    III", wider than a 216px card) breaks as "Diamond →" / "Grandmaster III" and never splits a rank
    from its division, which reads as two ranks. The arrow's `.28em` padding is sized to the two
    spaces it replaced — widen it and a name that fit before starts wrapping. The grid is
    `repeat(3, minmax(0, 1fr))`: with auto-min columns a nowrap name grows the track past the copy
    column and clips the last card's `−N%` pill.
- **The tier-track ladder** replaced the flat tick strip. `ladder_strip()` emits `data-ladder`;
  `app.js` builds one `.ob-seg` per tier, striped into its division slots (`--slots`) and filled in
  that tier's colour (`--tier` from `tierColor()`) across the span, with a hollow `.ob-seg-ring` at
  `from` and an accent `.ob-seg-dot` at `to`. Generic — it reads `divsOf()`, so it works for flat
  ladders (CS2: one slot per rung) as well as LoL's divisions. Captions (`data-tier-caps`) are now
  tinted per tier when in-span. The old `data-ticks` render hook is dead but left in place.

## The games catalogue (`/games/`)

`page_games_index()` is the **"Games catalog"** handoff (`design_handoff_games_page`), two screens
(1440 / 390) built as one component with breakpoints. Eighth scoped port after `.hero-a` / `.co` /
`.gg` / `.dsh` / `.rst` / `.tk` / `.hd` — tokens on `.gc`, product radii per element, nothing leaking.
It replaced a flat nine-tile grid with a paragraph beside it, three steps and the guarantee cards.

**Its job is routing, not converting.** Everything under the grid exists so the visitor arrives at a
configurator having already answered "which service", "how does it run", "who plays it" and "what if
it goes wrong". The bands are: catalogue · 01 which service · 02 how it runs · 03 dashboard ·
trust · 04 FAQ · close.

- **Three components are shared, not re-cut** — the handoff says so outright, and each is this
  build's canonical port of the handoff it names: band 03 is `dashboard_section()` (so the mock is
  the same `dash_mock()` the homepage, `/how-it-works` and `/demo.html` draw); the FAQ is `sg_faq()`
  + `faq_accordion_js()`, the safety/support accordion, so an answer here deep-links and behaves
  exactly like one there; the trust cards are `promise_cards()` over `D.GUARANTEES`. The on-shift
  rail is `roster_panel()` and the title list is `D.GAMES` — the same list the header's Games menu
  renders. `dashboard_section()` gained one optional `note=` for this page's standfirst; nothing
  else about it moved.
- **Every figure is read, never typed.** The handoff's nine "from" prices, nine order counts, "78
  boosters" and "3,000 in the Discord" are flagged there as invented: prices come through
  `from_price()` → `money()`, the roster counts off `BOOSTERS`/`STATS`, the coaching count and the
  FAQ's two price extremes off the catalogue, the sale answer off `PROMOS` and `D.BUNDLES`.
  `gc_facts()` computes the lot once so the chips' counts and the sentences under them cannot
  disagree.
- **"Duo available" is not one of the filters.** Duo is offered on all nine titles here
  (`mode_seg()` is in every configurator), so that chip would return the whole catalogue — the
  handoff's own rule is that a filter has to mean something. Its slot went to **Valve titles**, which
  is real, is two, and is the publisher split `gp_safety()` already argues per title. The four chips
  are All / Riot / Valve / With coaching, single-select with `all` as the reset, each carrying its
  count; none can return zero or all nine. **If a filter is ever added that can return nothing, that
  empty state has to be designed** — the grid must not just collapse.
- **The default sort is "Featured", not the handoff's "Most ordered".** Nothing in this build
  measures order volume, and the handoff's nine order counts — which are what its default sort reads
  — are invented. Featured is the catalogue's own editorial order (`D.GAMES`), which is what it
  actually is. The lead card still carries the **"Most ordered"** badge: one claim, said once, in the
  same words `games_grid()`'s lead tile uses, with the standing `STATS` has.
- **Everything is server-rendered; JS only hides and re-orders.** All nine cards ship in catalogue
  order, so the page is correct with no JS and legible to a crawler — this is the page a search
  engine reads to learn which titles exist. `initCatalog()` filters, sorts and counts through the
  `data-gc-*` contract, the same trade-off the roster board and the reviews feed make.
- **A card's accent is one number, not a colour.** Each card carries its game's `hue` as `--h`
  (data.py's, the same hue its key art is generated from) and the art wash and hover edge are both
  `hsl(var(--h) …)`. A per-title colour table — the handoff ships one — drifts from the art the
  moment a game is re-tinted. Art is the `band-<slug>.svg` crop, not the 1200×700 key art: the zone
  is 92px and a wordmark does not survive a fifth-of-height crop.
- **The name row carries no lettermark.** The handoff puts an initial in a tinted box beside the
  title, which on this build sits directly under art that already *is* the game's wordmark — so the
  tile said the name twice, once as a logo and again as a letter. `.gc-name-row` survives as the
  row's `min-width: 0` wrapper.
- **The filter chips and the sort control are one state with two presentations.** The segmented
  control and the native `<select>` are both in the DOM at every width and CSS picks one (a
  three-option segment does not fit beside the count at 390px); `initCatalog()` re-marks both
  whichever fired. Same technique as the Best Sellers tier grid, same reason.
- **"Compare all titles" is not drawn.** It is referenced twice in the handoff and the page behind it
  does not exist — the rule that keeps the live feed's rows unlinked. The phone's `.gc-bar` carries
  the one real action ("Start with <lead game>", read off the catalogue). It is `position: fixed`
  (the handoff's frame is 860px; a real page is not) and hides while the header sheet is open, the
  same way `.mobile-bar` does.
- **The mobile trust cards are a snap rail, not a 4.6s auto-rotating carousel.** These are the
  refund, privacy and support promises; a card that slides itself away mid-sentence is the "a moving
  element reads as a sales device" rule the guarantee page is built on. The dots stay and follow the
  rail (`initCatalogRail()`), and the click marks the dot itself so a tap on an already-scrolled-to
  card is never a dead control. The service cards are a swipe rail for the handoff's own reason —
  they are read once, in order.
- **The FAQ ids are a public contract**, like the guarantee page's: support links people at
  `#faq-<id>`, so renaming one in `D.CATALOG_FAQ` breaks the links in old tickets. Two answers carry
  a commitment rather than a description — one booster per title, and no cross-title bundle — and the
  second is structural: if sales ever wants a cross-title discount, that answer changes first.
  Answers substitute `usd()`, not `money()`: an answer is one escaped text node **and** the same
  string is asserted verbatim in the FAQPage JSON-LD, so a `.money` span would print as markup on
  both. The two figures there stay in USD when the currency switches; the cards above them convert.
- **The sale answer only claims "the larger of the two" while it is true.** `gc_faq_items()` compares
  the cheapest bundle against the auto promo and drops the clause otherwise, rather than letting a
  re-tuned code quietly falsify it.
- **The bundle range in that answer is derived, never read off `BUNDLES` directly.** The third
  element of a `BUNDLES` tuple is the hand-set **flat price in whole USD**, not a discount fraction —
  it used to be a fraction, and `gc_faq_items()` was left reading it as one, so the page published
  "bundle climbs at **1500% to 30500%** off" as copy *and* asserted it verbatim in the FAQPage
  JSON-LD. The reduction comes from `pricing.bundle_pct()`, the same call the strip's own `−N%` pill
  makes, so the answer and the nine game pages state one number (19–38% today).
- **Breakpoints follow the site's 1200/1000/760**, not the handoff's 1280/1024/768: 1200 takes the
  services to two columns and narrows the rail; 1000 is two card columns, the head stacked and the
  FAQ column unsticky; 760 is the whole phone pattern (one card per row, chip rail, native sort,
  service and trust rails, sticky bar). The handoff draws 1440 and 390 and asks for the middle to be
  confirmed with the designer.
- **i18n**: every figure rides in its own `<b>` so the sentences stay whole translatable nodes — the
  head paragraph is split at the coaching count, and "Showing N of M titles." reuses the roster's
  `Showing` / `of` keys. All card, service, FAQ and close strings are in both `fr` and `de`; game
  names, ranks and handles are data and stay as written.

Retired with the old page: `game_cards()` (the flat tile grid) and `guarantee_cards()` (the plain
`cards-3` copy of `D.GUARANTEES` — `promise_cards()` is the one shell now).

## The sticky mobile checkout bar (`.mobile-bar`)

`layout(mobile_bar=True)` — the nine game pages. It is the **`design_handoff_sticky_checkout_bar`**
port: the persistent bottom bar that keeps the live price, ETA, configuration and the one CTA in view
while the ~1000px configurator scrolls. Below 1000px the card deliberately drops its own total and
CTA (`.ob-sum-l .price-pair, .ob-cta, .ob-assure { display: none }`) so exactly one filled button is
on screen. It is **not** the Best Sellers handoff's own sticky bar, still deliberately not built —
two would stack. `/games/` has no configurator and so no price to pin: its phone bar is `.gc-bar`,
one CTA into the lead game, and the two never appear together.

Structure (handoff anatomy, top to bottom):

- **Accent hairline** (`.mb-hair`) — 2px, ember faded to transparent at both ends. A full-width solid
  accent line reads as an error; the fade makes it a highlight. It uses the `#ff5a1f` literal, not
  `var(--ember)`: the bar is outside `.hero-a`, where `--ember` is the site's global `#ff4a1f`.
- **Price row** (`.mb-top`) — the money over a one-line meta on the **left** (`.mb-left`), the tall
  CTA spanning both on the **right**. The money line is the 30px total, the struck original, and the
  saving as a **pill** (`data-out="saveAmt"` — `discount` is the signed receipt figure, and a pill
  opening with a minus reads as a charge). The meta is `clock · ETA · config`; only the config
  (`.mb-cfg`) may shrink — it grows with tier names and truncating it is correct, because the price
  and ETA to its left must never be pushed. `.mb-money` wraps as the safety valve (EUR runs wider).
- **CTA** (`.mb-cta`) — 54px, the one filled button. It **relabels per product** through the card's
  own hooks: `data-hide-service="coaching"` hides "Checkout" and `data-out="bookLabel"` shows
  "Book 3 hours" on coaching, where the meta's `days` also becomes the session day ("Tonight, 20:00").
- **Assurance row** (`.mb-assure`) — centred, secure-checkout / money-back with a 1px divider. The
  **glyphs carry the green, the words stay muted** — two green sentences under an ember button is a
  third accent in 40px of bar.

Load-bearing:

- **`position: fixed`, not the handoff's `sticky`.** The handoff's own headline risk is a
  clipping-overflow ancestor silently disabling sticky; fixed is immune, produces the identical
  layered result, and is the site's established pattern. This is the one deliberate deviation.
- **The ground is a gradient + `blur(16px)` + an *upward* shadow** (`0 -14px 34px`), so the page reads
  *through* the bar as content scrolls under it and the shadow separates it — the 1px border alone
  was not enough on a dark ground.
- **The home indicator is mock chrome; production uses the safe-area inset.** The root carries
  `padding-bottom: env(safe-area-inset-bottom)` so the CTA clears the iOS home bar.
- **`body.has-bar` padding is measured at RUNTIME, not written down.** The reserve keeps the last row
  of the page reachable instead of pinned under the fixed bar, and the thing it has to clear *moves*:
  `.mb-money` is `flex-wrap: wrap`, so the save pill drops to a second line whenever the price, its
  struck original and the pill stop fitting, and the bar goes 109 → 139 → (on checkout) 166px.
  **Which totals do that is a property of the number, not of the page** — a three-figure total
  already wraps at 375px in dollars, and CAD's `C$` prefix over a 1.37× amount wraps at nearly all
  of them. The four hand-set constants were each measured against one configuration and were wrong by
  16–23px for the rest, so `initBarReserve()` in app.js measures the bar and publishes `--mb-h` on
  `<html>`, re-measuring on every `esb:render`, on resize and on `document.fonts.ready` — the same way
  `--hd-top` follows the header's live bottom edge. The constants survive as the `var()` fallbacks
  (116 / 146 coaching / 146 below 360px / 150 checkout), which is what a no-JS page and the frame
  before the first measurement get. `--mb-h` is cleared, not set to 0, when the bar is `display:none`
  above its breakpoint. Coaching pages still carry `has-bar-coach` for that fallback — app.js sets it
  when a `[data-service="coaching"]` tab exists, so the six non-coaching games never pay the taller
  no-JS reserve.
- **It declares its own `--h-tint` / `--l-good`**: a child of `<body>`, outside `.hero-a` and
  `.rail`, and an unresolvable `var()` computes to the *initial* value, not an inherited one.
- **Every figure is a `data-out` the order card already fills**, so the bar and the card cannot quote
  two prices — the handoff's "do not recompute" rule. `.mb-money` is `aria-live="polite"` so a screen
  reader announces the new total after an input change. "Save" is its own translatable node.

## The checkout page

`page_checkout()` is the **"LoL Checkout"** handoff (`design_handoff_lol_checkout`), ported the same
way as the order card above: high-fidelity, with its tokens and measurements declared locally on
`.co` in `site.css`. Same rules apply — explicit radii, sentence-case controls, nothing leaking past
the scope. Five things are load-bearing:

- **The form is the left column, the summary is 420px on the right.** It used to be the other way
  round, with the summary *wider* than the form. The form is the task; the summary is reference.
- **Both cards end on the same baseline.** `.co-aside` is a flex parent, `.co-sum` is `flex:1`, and
  `.co-div-push` carries `margin-top:auto` — so the summary's spare height collects *above* the
  totals instead of leaving a gap under them. Reproduce the behaviour, not the measurement: the two
  natural heights move every time an upsell is toggled.
- **The Climb line names both ranks.** `[IV] Iron → [IV] Gold · Solo` — a `data-mark` is the division
  numeral alone, so the line used to read "IV → IV Gold · Solo" and never told the buyer which rank
  they were paying to leave. Same pairing as the closing band's card; see that section.
- **The summary column adds up.** `boost + one row per add-on − discount = total`, exactly, because
  `[data-addon-lines]` quotes subtotal deltas in order. Those rows are pre-discount, so they do not
  match the `+$N` on the picker above them, which answers "what does ticking this do to my total".
  Both are true; the discount row between them is what reconciles them. Don't "fix" one to match the
  other without deciding which question the buyer is asking.
- **The discount code states that it is applied.** The old field was an empty input whose
  placeholder claimed a code was already on, which reads as the opposite. Both toggle labels live in
  the DOM (i18n matches whole text nodes); the button only flips `aria-expanded`.
- **`layout(bare=True)` is what makes it a pay flow.** No promo bar, no nav, no currency switcher —
  a page whose only job is finishing should not offer exits. The legal links survive in `foot_min()`
  because terms/privacy/refunds have to be reachable where money moves.

Everything toggled with `hidden` inside `.co` is caught by one `.co [hidden] { display: none; }`
guard at the end of the section — the rows all carry a `display` value, which otherwise beats the
UA's `[hidden]` (the bug `.banner` hit in the ops console).

- **The "Pay with" chips keep the dark-pill + label shape, with coloured brand glyphs.** Same chip
  as always — field-coloured pill, small glyph, the network's name — but `pay_marks()` now draws the
  networks' own marks in their own colours (Visa/Amex blue cards, the Mastercard interlock, the Apple
  glyph, Google's four-colour G) instead of the grey card/wallet stand-ins. They ride *beside* the
  label, so the row's geometry is unchanged. Two things to keep in mind: these are **simplified marks,
  not the released artwork** — the schemes require their logos be used unmodified from the brand kit
  (Stripe ships all of them), so swap before launch; and the row must stay in step with what
  `serve.py` actually enables on the Stripe session, or it advertises a method the buyer cannot pick.
  `pay_glyphs()` (order-card foot) and `foot_pay()` (footer) are unchanged and still generic.

Deviations from the handoff, all deliberate: add-on names and prices come from `data.py` and the real formula, not the mock's flat
$13/$9/$10; and on mobile the form keeps source order with the price in a sticky bar, rather than
the README's summary-first-behind-a-disclosure, which is not designed and would push the one
required input below the fold. The README asks for breakpoints to be confirmed with the designer.

## The home hero + booster spotlight

`page_home()`'s first section is the **"Home hero"** handoff (`design_handoff_home_hero`), the
sibling of the Ladder card above — same palette, same card shell. It **rides on `.hero-a`'s scoped
tokens rather than redeclaring them**: the section is `class="hero-a hero-a-lit hero-h"`, so
`.btn-primary`, `.grad-text` and the `--h-*` text colours pick up the handoff accent for free. Only
the values this handoff sets differently live under `.hero-h` in `site.css`.

- **The copy column is `.hero-h-copy`, deliberately not `.hero-copy`.** The game hero's ≤1000px
  rules reflow `.hero-a .hero-copy` with `display:contents` and `order:` to lift the order card
  above the proof. Those selectors are all anchored on `.hero-copy` for that reason — a bare
  `.hero-a .lede` reorders the home hero's paragraph to the bottom of the column. If you add a
  `.hero-a`-scoped rule, anchor it.
- **Column order is the argument.** Headline → paragraph → CTAs → three guarantees → rule → rating.
  The objections are answered beside the buttons, where the decision is made.
- **One filled button in the viewport**, same rule as the game pages: `page_home()` passes
  `nav_outline=True`, the secondary CTA is a real outline with a `play` glyph, and the hero's
  gradient CTA is the only filled action.
- **`guarantee_row()` is shared with `page_game()`.** One copy of money-back / no account / VPN
  region, in `GUARANTEES_INLINE` — the two heroes cannot drift.
- **The spotlight is roster data, not hero copy.** `D.SPOTLIGHT["handle"]` names a booster in
  `D.BOOSTERS`; the name, order count and portrait filename all come off that entry, so the card,
  the roster panel and the boosters page can't quote different numbers for the same person. An
  unknown handle **hides the card** — the handoff's fallback for a month with no qualifying booster
  is no card, never an empty one. `emit_art()` generates `portrait-<handle>.svg` from the same
  constant.
- **Mobile (≤760px) drops the card, the three guarantees and "N boosts delivered."** Four proof
  blocks push the CTA below the fold; the phone ships headline → paragraph → CTAs → one rating line.
  The headline steps down from the drawn 46px via `min(46px, calc(12.4vw - 5px))` — "The rank is
  yours." needs ~369px at 46px and a 390px phone gives the column 350, and holding two lines matters
  more than the exact size.
- **Breakpoints follow the site's 1200/1000/760, not the README's 1280/1024/768**, so the hero
  reflows in step with the header and the sections around it. The handoff draws 1440 and 390 only
  and asks for the middle to be confirmed with the designer.
- **The utility bar now has three groups**, not two: `availability_slot()` puts the roster count in
  the centre on every page, reading the same `D.STATS["online"]` as the roster panel and the order
  card, and hiding below 1000px.
- **The portrait and the Trustpilot star are placeholders.** The handoff requires a real photograph
  in the ring and Trustpilot's licensed mark or widget; the generated avatar and the green star are
  stand-ins, same status as everything else in [Placeholder data](#placeholder-data--do-not-present-as-real).
- **The card names the game, and its CTA starts an order.** `.spot-game` is the booster's ladder,
  resolved from their own `slug` against the catalogue (full `name`, not the roster's `short` — there
  is no column to fit here), because "Challenger 1042 LP" means nothing until you know which game it
  is on. The CTA is **"Order with <handle>"** → `/games/<slug>.html?booster=<handle>`, the same
  destination the roster's Hire and the profile's request card use, so the label and the link agree;
  the profile is still one tap from the name on either of those pages. `SPOT_HIRE` resolves it once
  and falls back to `/games/` for a booster whose slug isn't in the catalogue.
- **i18n**: the CTA is `"Order with"` + the handle in its own `<b>`, wrapped as one flex item so the
  gap between them is a word space rather than the row's 9px. The handle is data, so changing
  `D.SPOTLIGHT["handle"]` no longer needs a new `fr`/`de` sentence — that key is already the profile
  card's. The game name is data too and stays as written. Numbers stay outside the translatable
  nodes — see the whole-text-node rule above.

## The stat band + 02 Live / 03 Safety

`statband()`, `live_feed()`, `roster_card()`, `discord_card()` and `safety_block()` are the
**"Live and safety"** handoff (`design_handoff_live_and_safety`) — the stretch of the homepage that
answers "is this real, and is it safe?". Scoped the same way as the other ports: `.ls` (section),
`.lf` (feed), `.rc` (roster), `.dcd` (Discord), `.sf` (safety), with the local tokens on `.ls, .rail`
so nothing leaks. `.rail` carries its own copy because `roster_panel()` also renders on
`/boosters.html` and `/games/`, outside `.ls`.

- **The stat band is warm now.** It was a purple-blue gradient — the one cool surface on a warm
  site — and the four figures floated with nothing between them. It is the ember fading left to
  right with a 1px divider per cell. `_figure_unit()` splits `D.STATS`' written values ("4.8 / 5",
  "18 min") into the 38px figure and its 17px unit; `initStats()` counts up `.statband .v .n`, not
  `.v`, or it would overwrite the unit node.
- **The feed is a timeline, not a grid.** The 2×2 card layout destroyed the ordering of a feed whose
  whole meaning is "just now". Newest first, one rail with the accent dot and the warm timestamp on
  `:first-child` — which is also why a live source only has to *prepend* a row to get the treatment.
- **Feed rows are deliberately inert.** The handoff routes them at a public delivery receipt, and
  this site has no such page; its own instruction for that case is to drop the caret and the pointer
  rather than ship a dead control. Same reason there is no "See the full feed" link beside the count.
  Build the receipt page and the rows become links.
- **Tier marks come from `D.tier_color()`, never from the handoff's hex list.** The point of drawing
  the climb with marks is that it matches every other rank display on the site; a second colour table
  would defeat it. `tier_mark()` is the shared object, tinted through `--tier`. A feed entry's `frm`
  / `to` tier **must be a rung of that game's ladder** — that is what the colour resolves against.
- **Relative times re-render on a timer** (`initFeed()` in app.js). A static page can sit open for an
  hour, so "2 min ago" has to keep meaning it. Rows carry `data-ts` (epoch seconds — what a feed
  wired to the orders table emits) or `data-mins` (the placeholder stand-in, counted from page load);
  `_ago()` in build.py and `label()` in app.js must stay identical or a reload changes the wording.
  **Nothing generates feed entries** — the four rows are exactly what `D.LIVE_FEED` holds.
- **Availability is the loud thing in the roster, not win rate.** That hierarchy was inverted:
  "FREE" was 9px fine print under an orange win-rate figure. The status pill reads `queue == "free"`,
  and the avatar ring's colour encodes the same fact — keep them in step. Rows link to
  `/boosters.html#b-<handle>` (the table rows carry those ids) until per-booster profiles exist.
- **Roster avatars are a face, never a letter** — see [Booster faces](#booster-faces--the-avatar-in-the-ring)
  below. `booster_face()` is the one implementation, shared by the rail, the board and the
  track-order card; the ring around it is unchanged and still carries free / busy.
- **`BOOSTERS[].slug` names the game**, so the chip renders that game's `short` and a booster can
  never advertise a ladder the catalogue doesn't sell. orvo is a Rivals booster precisely because
  the feed has them delivering the Rivals order two columns away.
- **The safety mechanisms are labels, not new claims.** The four lines restate `SAFETY["body"]`,
  which is signed-off copy that must not be edited or split. A fifth mechanism means writing the
  sentence that backs it into `body` first.
- **The Discord mark is a generic chat glyph**, not Discord's logo — same trademark rule as
  `pay_marks()` and the Trustpilot star.
- **Breakpoints follow the site's 1200/1000/760**, not the handoff's 1280/1024/768. 1200 narrows the
  rail to 340 and drops the safety proof column under the prose; 1000 goes single column with the
  rail last and gives the feed its game column back; 760 strips the clock, the rail and the game
  column from feed rows and the win rate from roster rows. The handoff draws 1440 only and asks for
  the middle to be confirmed with the designer.
- **i18n**: every figure sits in its own `<b>` (`<b>34</b> boosters`, `<b>41</b> orders closed…`) so
  the sentence still matches whole. `.rc-all` wraps its label in one `<span>` — the button is a flex
  container and three bare children would space out as three flex items.

## 04 Dashboard — the section and its mock

`dashboard_section()` is the **"Dashboard section"** handoff (`design_handoff_dashboard`), sitting
between Safety and Reviews on the homepage — which is why **Reviews is now `05`**. It renders again
on `/how-it-works.html` with `num=None` (no kicker there: no numbered run to join). Fourth scoped
exception after `.hero-a` / `.co` / `.gg` — tokens on `.dsh`, product radii per element, nothing
leaking past. It replaced a `.split-9-11` figure holding `art.dashboard()`'s generated placeholder.

- **The mock is the argument.** It is the evidence for the three claims beside it, so it is built as
  a working screen at real fidelity — live rank, progress, an LP chart, a real match table — not as
  a decorative panel. Anything that makes it look generated undoes the section.
- **"Configure your boost" goes to a configurator, not the catalogue** (`cta_href=`). It defaults to
  `/games/`, which is right on the three pages that have no configurator on them (`/games/`,
  `/how-it-works.html`, `/demo.html`) — picking a title genuinely is the next step there. The
  homepage passes `cta_href="#calc"`, the Best Sellers dock, because it *has* one: the band used to
  send its own visitors off the page to choose a game they could have configured 4,000px above.
  A caller passing a fragment owns that id, or the CTA is a no-op.
- **`dash_mock()` is inert by construction, and that is a decision.** `role="img"` puts one labelled
  illustration in the accessibility tree instead of a fake table of somebody else's order, and the
  footer's Pause / Message controls are **spans**, so nothing in the panel is focusable or clickable
  — a real `<button>` that does nothing is a trap for anyone arriving by keyboard. Hover states stay
  (a screenshot of a live product should look alive); the prototype's pointer cursor on match rows
  does not, because it promises a click that never comes. The handoff sanctions exactly this.
- **`dash_mock()` has two callers and three switches.** `example=True` adds the Example pill to the
  header strip (the demo page's copy of the band); `live=True` is the resolved-order variant on
  `/demo.html` — no header strip, a footer that says when the last game was, and no `role="img"`,
  because there the table is the page's subject rather than an illustration beside an argument.
  Build the card once: the track-order handoff carries the same ProgressCard / LpChart /
  MatchHistory and asks for exactly that.
- **Every figure in the mock is derived, not typed.** `demo_order()` computes the completion
  percentage from the ladder distance, the days left and the price from `pricing.quote()`, and the
  W–L record by counting the rows. The handoff draws **62%**; on this site's League ladder Gold IV →
  Platinum II is 6 of the 12 rungs to Diamond IV, so it renders **50%**. The handoff asks for the
  ladder distance — 62 was its arithmetic against a ladder with no Emerald.
- **`D.DEMO_ORDER` is one order rendered on two pages.** "Open the demo dashboard" links at
  `/demo.html?order=ESB-3F92K1` (`DEMO_HREF` in build.py — never a literal), which opens the
  resolved order directly, so the demo page and the mock **must** show the same order — a visitor
  who follows the link and finds different games on it has been shown a mock-up, not a product.
  Both read this one fixture.
- **The two pulsing dots need `--l-good` in scope.** `.dot-live.dot-ok` is shared with the live feed
  and reads that token by name; `.dsh` declares it for the same reason `.rail` does. An unresolvable
  `var()` computes to the *initial* value, not an inherited one — the dots painted transparent.
- **The chart is a hand-plotted polyline**, 13 authored points in `DEMO_ORDER["chart"]` on a 104-unit
  box; `dash_mock()` spaces them across the 588-unit width. If the fixture's story changes, re-plot
  them. Both gradient ids are namespaced per instance (`_DASH_N`) — two panels on a page would
  otherwise both paint with the first one's stops, the bug the inlined game logos hit.
- **Champion slots are coloured placeholder tiles**, sized for a real 30px portrait to drop in.
  Riot's champion art is licensed — same rule as `pay_marks()` and the Trustpilot star.
- **Win and Loss must not share a colour.** They both used to be orange, which made the history
  unreadable at a glance; Win is green, Loss neutral, and a lost LP figure is muted rather than
  louder than the wins.
- **Every claim in the copy column is a promise the product is held to.** If pause takes an hour
  rather than minutes, or chat routes through support, `D.DASHBOARD_POINTS` changes.
- **i18n**: figures and `·` separators ride in `<b>`/`<i aria-hidden>` carriers so the words around
  them stay whole translatable nodes ("complete", "days left", "LP net", "Order start"). The one
  exception is documented in the markup: "Last 5 of 38 games" carries two figures mid-sentence, and
  fragmenting it would impose English word order on French and German, so it falls back to English.
- **Breakpoints follow the site's 1200/1000/760**, not the handoff's 1280/1024/768. Below 1000 the
  copy comes first and the mock below it at full width; below 760 the mock drops the K/D/A column and
  the chart captions and the table goes to four columns. The handoff draws 1440 only.

## The orders page (`/orders.html`)

`page_orders()` is the **"My orders"** destination — the account menu's My orders row lands here
(`ORDERS_HREF`), not on the single demo dashboard. It is a net-new page (no handoff), so it layers on
Ashfall tokens rather than porting a scoped design; rank marks reuse the live feed's `.lf-mark`, so a
climb here is tinted like every other climb on the site.

- **The order data is placeholder, and the page says so.** There is no per-customer order store behind
  the [facade session](#accounts--the-sign-up-list-in-ops), so — like `DEMO_ORDER` and the booster
  histories — the list is generated, never typed. The active order **is** `demo_order()` (it opens the
  one dashboard the site actually renders, on `?order=`); the delivered rows come from
  `order_history()`, which walks real ladders and prices every row with `pricing.quote()`, seeded on a
  constant so a rebuild is identical. A standing note calls it a preview until an account backend lands.
- **It personalises client-side, and works without JS.** The full sample history is server-rendered; the
  guest prompt ("you're viewing a sample — log in") is visible by default and `initOrders()` in app.js
  drops it and shows "Signed in as <name>" when the facade session is present. Session changes re-run it
  through `paint()`, so logging in or out on the page flips the state without a reload. The name rides in
  its own `<b>` so the greeting stays a whole translatable node.
- **It is account-scoped, so it is out of the sitemap** (alongside the pay flow) — reached only from the
  account menu, not a page to rank. Still crawlable; no robots block.
- **i18n**: all card strings are in `fr`/`de`; ranks, game names, order ids and dates are data and stay
  as written, same as everywhere. Money runs through `money()`, so the prices convert with the currency
  switch (the delivered totals and the active price both re-quote in EUR).

## The demo page (`/demo.html`, was `/track.html`)

`page_demo()` is the **"Track an order"** handoff (`design_handoff_track_order`) — a lookup, the
Dashboard band underneath it, and the order dashboard the emailed link opens. Sixth scoped port after
`.hero-a` / `.co` / `.gg` / `.dsh` / `.rst`: tokens on `.tk`, product radii per element, nothing
leaking. It replaced a two-field form beside a headline with roughly 40% of the band empty, a dev line
shipping as help text, and no state at all after submitting.

**The rename is the point.** Every figure on the page is `D.DEMO_ORDER` — a placeholder — and there is
no order store behind the form, so "Track my order" was a page promising something the build cannot
do. It is `/demo.html`, the nav and footer say **Demo**, and the URL lives in **`DEMO_HREF`** in
build.py, not as six string literals. `?order=<id>` is the deep link; the homepage's "Open the demo
dashboard" and both checkout confirmations point at it.

- **Two states, two sections, one of them `hidden`** — `[data-demo-view="lookup"]` (+ the `#dashboard`
  band) and `[data-demo-view="order"]`. The switch pushes real history, so Back leaves the page the
  way a visitor expects. In production the handoff wants **two routes** (`/track` and
  `/orders/:token`) so the emailed link can deep-link; `?order=` is this build's stand-in.
- **Everything toggled with `hidden` needs the `.tk [hidden]` guard.** The rows all carry a
  `display`, which otherwise beats the UA's `[hidden]` — the same bug `.co` and the ops console's
  `.banner` hit.
- **The full site chrome stays.** The handoff drops it for checkout's reason ("a task page, the only
  exits are support and the brand mark"), which is true of a guest chasing an order and false of a
  visitor who clicked Demo in the menu. Renaming the page inverts that argument.
- **The "link sent" notice says no email was sent**, because none is. The handoff kills a dev line
  under the submit button as a bug and it was right — but that line leaked build detail into a
  product page, and this one states what the page you are on *is*. The alternative is a confirmation
  that nothing happened.
- **No dead controls, same rule as the live feed.** "All 38 games" is not drawn (there is no replay
  view); Message goes to `/support.html` (support reads the same thread, per `DASHBOARD_POINTS`); the
  booster's arrow goes to their real profile; and **Pause is a real button** that puts the card into a
  paused state. That state is undesigned in the handoff, but a dead control on a page whose whole job
  is demonstrating the product is worse than a plain one.
- **Pause owns the status pill too.** An order reading "In progress" beside its own "Order paused"
  banner is telling the visitor two things at once, so `setPaused()` rewrites both and stops the dot.
- **Every figure is derived.** Add-ons in the details rail are `ADDONS` ids that were **priced into**
  the quote behind the "Paid" row; the timeline's live event is built from `at` + the newest match, so
  it cannot contradict the card; the guarantee note's promise is `GUARANTEE["cases"][1]`'s own title,
  because the handoff requires that wording to match the safety page exactly.
- **Timeline rows name the rank, not just the mark.** A `data-mark`-style mark is the division numeral
  alone — "IV reached" says nothing. Same mark + tier-name pairing as the feed, the checkout climb
  line and the closing band's card.
- **The connector is a 1px background on the 13px dot column**, not a border on the row. The column is
  13px so the 11px live dot centres in it; painting the gradient at the column's full width renders as
  stacked grey blocks rather than a line — a defect the handoff caught in review.
- **The submit label follows the filled field** ("Find my order" / "Email me the link"). A static
  label on a two-route form is what made the original ambiguous. That node, the helper line and the
  two Pause labels are in **i18n.js's `SKIP` list** and owned by the page script through `esbT`,
  because they swap at runtime; the script wraps `window.esbRender` so a language switch takes them.
- **Breakpoints follow the site's 1200/1000/760.** 1200 narrows the form to 520 and drops the order's
  rail under the card as a pair (the two short cards span both columns, or they leave a void beside
  the tall ones); 1000 stacks the lookup with the **form first** and stretches the header actions;
  760 gives the phone the handoff's order — headline, paragraph, card, assurance lines — via
  `display:contents` on `.tk-copy`, the same technique the home hero uses. This page arrives by email,
  so the handoff flags mobile as required work rather than a nice-to-have, but it draws 1440 only.
- **The match table's mobile columns are `.dm`'s, not the handoff's.** Below 760 the shared card drops
  K/D/A and keeps the champion square; the handoff asks for the reverse. One component, one
  behaviour — changing it changes the homepage.

## Watch live — the booster's screen share (`watch_panel()`)

`watch_panel()` renders in `_demo_rail()`, under the booster card, and is the customer's door into
watching their own order being played. **The video is Discord's; this panel is only the state.**

- **Neither title can be watched through the game, and that is why the design is what it is.**
  Valorant has no spectator API at all — observers exist only in custom/tournament lobbies. League's
  Spectator-v5 exists but is ~3 minutes behind and needs a Riot **production key**, which is not
  granted to a service whose product breaks the game's ToS. So there is no path through Riot for
  either game, and what the customer watches is the booster's **own screen**, shared into a private
  Discord voice channel.
- **`WATCH_GAMES` is now every catalogue title, and that is a business decision.** It was a two-title
  allow-list; the `stream` add-on is sold on all nine, so the panel follows. It generalises cleanly
  *because* the product was never the game's spectator mode — it is the booster's own screen, which
  never depended on the title. It stays a named list rather than an inlined `True` so narrowing it
  again is one edit. ⚠ Listing a game is a claim that a booster on it will actually stream, and
  nine titles is nine rosters to brief, not one.
- **There is no embedded player and there is not going to be one.** Discord ships no iframe player
  for Go Live. Drawing a video frame here would be a mock-up of something the product cannot do —
  which is the exact trap `/demo.html` was renamed to avoid. The panel's job is the one fact Discord
  does not surface from outside: *is my booster streaming right now*.
- **The state follows Pause, because it has to.** A paused order is not being played, so it cannot be
  being streamed; leaving the panel on "sharing their screen" beside the order's own paused banner is
  the same two-things-at-once defect the status pill fixed. `setWatch()` is called from `setPaused()`,
  never independently.
- **Both states ship in the DOM with one hidden** — the whole-text-node rule the auth tabs and the
  mode-conditional add-ons follow. A sentence written in by JS arrives untranslated. Same for the two
  CTA labels; both are real destinations, so neither is a dead control.
- **The CTA is an outline, and deliberately.** The order view has no filled action at all — the
  visitor has already paid — so the one-filled-button-per-viewport rule holds across the page.
  Blurple appears on the mark and on hover only, so the card is never a second accent beside the
  ember guarantee note under it. The Discord mark is `_hd_brand()`'s, shared with the OAuth button,
  and carries the same pre-launch swap for the licensed asset as `pay_marks()`.

⚠ **The live half is not built, and it is now SOLD.** The panel's state is driven by the demo page's
Pause control against one fixture; nothing asks Discord anything. That was tolerable while the panel
was a demo-only facade — it is not, now that "Watch your booster play" is the first row of every
configurator and rides into fulfilment as `metadata[addons]`. Until `streams.py` exists, honouring it
is a manual ops promise: somebody has to open a channel and tell the booster to share. **Either build
the seam below or take the row out** — the one thing that must not happen is a paid order carrying an
option nobody knows about. What a real one needs, and the shape it should take:

- **`src/streams.py`, a sixth store sibling** of `analytics` / `accounts` / `boosters` / `orders` /
  `carts` — `esb:streams`, one row per order (order id, booster handle, channel id, `offline|live`,
  `started_at`). Operator-write, customer-read.
- **`GET /api/stream?order=…`, gated exactly like `/api/orders`**: the email comes from the verified
  session cookie, never the request, or one customer can watch another's boost.
- **Discord's REST API needs no gateway connection** — creating a channel, setting permission
  overwrites and reading who is in a voice channel are plain HTTPS calls with a bot token. That is
  `urllib` and the house rules, and critically it runs on Vercel serverless, which a websocket bot
  cannot.
- **`oauth._profile()` currently discards `raw["id"]`** on the Discord branch. That snowflake is what
  lets a permission overwrite grant *one named customer* access to *one channel* — capture it before
  building the rest, or the fallback is invite links and strangers in the server.
- **Two decisions to make before it ships**, both permission-overwrite one-liners and neither
  reversible quietly: whether the customer gets mic permission (a private channel with the booster is
  an unmonitored back channel, which is how orders get arranged off-platform), and whether Nitro is
  bought per booster — free Go Live caps at 720p30.
- The CSP in `vercel.json` does **not** need changing for this: the panel links out, it does not
  embed. It would need `frame-src`/`media-src` only if V2 pulls the video back in-page behind a
  managed provider (Cloudflare Stream Live, signed playback URLs, ~2–5s on LL-HLS).

## The closing band + the footer

`cta_band()`, `fc_card()` and `footer()` are the **"Final CTA + Footer"** handoff
(`design_handoff_footer`) — two bands designed as a pair and shipped as two independent components,
because the footer renders on every page and the band must never appear on checkout. The band
replaced a 400px `.band` with a background illustration and a generic "Ready when you are"; the
footer replaced a four-column strip with a centred copyright.

- **The close is their order, not a pitch.** The band reads back the configuration the visitor has
  already made — the climb in words, the live price, and a summary card. `live=True` says this page
  owns a configurator; only the homepage and the game pages pass it.
- **`live=False` is the handoff's documented fallback, and it is deliberate.** A page with no
  configurator has nothing *of its own* to read back, so it gets no card, a headline quoting
  `catalogue_floor()` and one CTA. Not an empty card, and not a fabricated default order — the
  handoff is explicit about both. It is described but not drawn, and is flagged for the designer.
- **`readback=True` (the default on the `live=False` bands) ships the live version beside it,
  hidden.** Since the order is now kept per game and shared site-wide (see
  [The saved order](#the-saved-order--one-record-per-game)), a page with no configurator *can* close
  on the visitor's own climb — which is the handoff's premise, and is not what "no fabricated
  default" was protecting against: it appears **only when a real stored order is behind it**
  (`HYDRATED`). The server always renders the FALLBACK visible, because a static page is cached for
  everybody and cannot know which visitor it is; app.js's `[data-fc-when]` pass swaps them and drops
  `fc-solo` when it unhides the card, so with no JS the band is still correct and every string is in
  the DOM for the whole-text-node i18n rule (they are the live band's own strings, so `fr`/`de` were
  already complete). `[data-fc-readback]` on the section is also what tells app.js this page
  resolves the saved order rather than the checkout snapshot — the pay flow is the one page with
  neither that marker nor a configurator.
- **Coaching is deliberately not read back.** It is a booking, not a climb: "Your climb starts at
  €79" over a card whose Climb row is empty describes nothing that was bought, and re-quoting the
  stored ranks as a boost to fill it would invent a price the visitor was never shown.
- **`readback=False` where the band is not an order close** — the support page's "Still stuck? Ask
  us." is asking a different question, and its CTA is Discord.
- **`catalogue_floor()` is quoted, never typed.** It is `pricing.quote()` over every rung of every
  game, so "Your climb starts at $3" and Valorant's "Cheapest single division $3" are the same claim.
- **The card shares the checkout summary's data contract**, not just its shape — `data-sum` /
  `data-mark` / `data-when-*`. One `render()` pass fills both, so the two can never disagree about
  the same order. The band's headline, the card total and the struck price are three assertions of
  one number for the same reason.
- **The Climb row names both ranks — mark + tier, twice.** It used to be the two marks alone, and
  since a mark is only the division numeral, an Iron IV → Gold IV order rendered "IV → IV": the
  colours told the tiers apart but nothing said which they were. Checkout had the same hole from the
  other side, naming only the *target* tier. Both now draw `data-mark` + `data-tiername` per end, the
  same object the live feed and the dashboard mock draw. It does **not** append the mode, though —
  checkout does that because it has no queue row, and this card has one, so borrowing that text
  prints "Solo" twice in four rows.
- **`.fc` rides on `.hero-a`'s scoped tokens** (`class="hero-a hero-a-lit fc"`) rather than
  redeclaring the handoff palette — same design as the two heroes, so `.btn-primary`, `.grad-text`
  and `.ob-mark` resolve to the handoff ember for free. `.ft` declares its own copy of the `--h-*`
  and `--l-good` names because the shared parts (`.ico`, `.dot-live`) read them by name and an
  unresolvable `var()` computes to the *initial* value, not an inherited one.
- **The band's CTA labels are uppercase and tracked** — the footer's register, deliberately not the
  sentence case `.hero-h-cta` uses. Same geometry otherwise.
- **"Talk to support" and "Let's chat" are one destination.** The handoff says so outright; wiring
  them apart is how a live-chat rollout loses half its traffic to a contact form.
- **`FOOT_SUPPORT_ONLINE` is a real seam, not decoration.** The handoff requires that "Online now"
  reflect actual availability and that the dot and label change rather than lie. False degrades the
  card to the median reply time; the 24/7 heading above it is the promise this line reads out.
- **"All N games" counts `D.GAMES`**, so adding a game can't leave the footer advertising 9.
- **Socials are the four channels that exist**, not the handoff's six — its own note says to replace
  them with the real set, because a tile linking nowhere is worse than one fewer tile. The brand
  lockup stays the site's shard, not the handoff's lightning bolt: the nav and the footer have to be
  the same mark.
- **`foot_pay()` drops PayPal and BTC** for the reason `pay_glyphs()` gives — checkout takes neither,
  and the card marks stay generic until Stripe's brand kit lands.
- **The footer's locale menu opens upward.** It sits at the foot of the document; the shared
  `.loc-menu` rule drops it below the button, which is off the page.
- **Everything toggled with `hidden` needs the `.fc [hidden]` / `.ft [hidden]` guard** — the rows all
  carry a `display`, which otherwise beats the UA's `[hidden]`. Same bug the checkout column and the
  ops console's `.banner` hit.
- **Breakpoints follow the site's 1200/1000/760.** At 1200 the band's card narrows to 340 and the
  support card turns side-on across its own row rather than stretching two buttons over 1400px; at
  1000 the band goes single column with the card first (it is the substance of the close); at 760
  both CTAs go full width and the footer stacks with 44px link rows. Mobile keeps the full summary
  card rather than the README's collapsed disclosure, which is not designed — same call the checkout
  page made. The handoff draws 1440 only and asks for the rest to be confirmed with the designer.
- **i18n**: `fromRank`/`toRank` and every figure ride in their own nodes so the sentences around them
  stay whole. New strings are in both `fr` and `de`, including the payment strip's screen-reader
  sentence, which `pay_glyphs()` had been shipping untranslated.

## The boosters roster + one profile per booster

`page_boosters()` and `page_booster(b)` are the **"Boosters roster"** handoff
(`design_handoff_boosters_roster`), two screens that are one flow: `/boosters/` lists the board and
every row's name opens `/boosters/<handle>.html`. Fifth scoped port after `.hero-a` / `.co` / `.gg` /
`.dsh` — tokens on `.rst` (roster) and `.bp` (profile), product radii per element, nothing leaking.

- **The page URL is `/boosters/`, not `/boosters.html`.** Profiles live in that directory, and a
  `boosters.html` beside a `boosters/` makes `/boosters` resolve differently per host. Same shape as
  `/games/` — `page_boosters()` is written to `/boosters/index.html` and NAV carries `/boosters/`.
- **Nothing on the roster page may appear twice.** The version this replaces showed the same five
  boosters in a hero rail card and again in the table 300px below. The rail now carries
  `vetting_card()` — last month's intake, which is the *evidence* for the H1's claim. If you put a
  roster preview back in that slot you have undone the redesign.
- **The funnel figures are claims** (`D.VETTING`), not decoration, and they are deliberately not bars:
  1,840 → 96 → 11 renders the last two as invisible slivers. The three rule lines under them restate
  promises the hero paragraph already makes; a fourth line means writing that sentence into the
  paragraph first.
- **`D.WR_FLOOR` is asserted, not just stated.** The hero says boosters drop off the board below 62%;
  `data.py` fails the import if any `wr_n` is under it, and the roster's win-rate bar is normalised
  from that floor to `WR_TOP`. The bar's zero and the sentence are the same number on purpose.
- **`STATS["online"]` / `STATS["free_now"]` are counted from `BOOSTERS`**, not typed. Every "N
  boosters" on the site reads them (utility bar, order card, rail, roster footer), so counting is what
  keeps one claim true everywhere — a hand-typed 34 over a 50-row table is exactly the bug this fixes.
- **Availability is the loud thing.** `queue_pill()` and the avatar ring both read `queue`, so they
  cannot drift; win rate is neutral with a bar under it, because ten orange figures are ten identical
  accents and therefore no signal.
- **Hire stays enabled for busy boosters** and goes to `/games/<slug>.html?booster=<handle>` — the
  handoff's "carry that booster into the configurator as the named booster". The name link goes to the
  profile. `?booster=` is validated against `D.boosters` in the client data and against `D.BOOSTERS`
  again in `payments.py`; it rides the order as `metadata[booster]` and **never touches the price**.
- **There is no named-booster fee.** The handoff prices it at +10% and flags the figure as invented;
  `pricing.py` charges nothing, and the server recomputes every amount, so the rail card says "No extra
  fee". Introducing a real one means adding it to `pricing.py` *and* its `app.js` mirror first — then
  the label reads it off the constant the way Duo reads `DUO_MULT`.
- **No dead controls.** "Load more" is rendered only when rows are actually `hidden` behind it
  (`ROSTER_PAGE` / `BP_PAGE`, mirrored by `RST_PAGE` in app.js — change one, change the other), and the
  profile's footer says "the last N of M orders" because the page shows a recent sample, not the whole
  history. Same rule that keeps the live feed's rows unlinked.
- **The empty state is required.** A game with nobody free is normal; `[data-rst-empty]` names the
  game, counts who covers it, and offers Order anyway / Show everyone. Two headlines live in the DOM
  (one hidden) because "Nobody free on DOTA" has no form when the chip is on "All games".
- **Everything on a profile is derived from the booster's own data.** `booster_history()` builds the
  completed-orders table from the rank bands in `climbs` — the same bands the rail card claims — and
  takes each delivery time from `pricing.quote()`, the way `demo_order()` does for the dashboard mock.
  `_climb_bands()` splits `orders` across the four bands below the peak, so the card's counts add up to
  the stat card above it (it reproduces the handoff's 71/63/48/32 for vantaa exactly). Seeded on the
  handle, so a rebuild renders the same table.
- **No `aggregateRating` in the JSON-LD.** The profile emits `ProfilePage` + `Person` only. The ratings
  are placeholders; shipping them as structured data would put invented review stars in search results.
- **Portraits are per booster** (`portrait-<handle>.svg`, drop-in slot `portrait/<handle>`); the home
  hero's spotlight reads the same file for whoever `SPOTLIGHT` names, so the card and the page it links
  to can never show two faces. The portrait is a *different* asset from the 38px avatar and stays
  `art.avatar()`'s rim-lit silhouette — the shipped avatars read as characters in a ring and as
  cartoons at 96px, which is why `assets-in/portrait/` is deliberately left empty.
- **Game pages cap their roster at 6** (`page_game()`); League alone has 22 boosters and that section
  only has to establish that real people cover the ladder. The full board is `/boosters/`.
- **Breakpoints follow the site's 1200/1000/760.** 1200 stacks the hero and moves Peak under the
  handle; 1000 goes to Booster/Game/Win/Hire with the queue pill under the handle; 760 turns both
  tables into cards. The handoff draws 1440 only and asks for the middle to be confirmed.
- **i18n**: figures ride in their own `<b>` as everywhere else. Two sentences carry two figures
  mid-sentence and deliberately fall back to English — the profile's "Showing the last N of M orders"
  is translated with English word order, and the roster's count works because "of" is already a
  shared key. New card strings are in both `fr` and `de`.

## Booster faces — the avatar in the ring

Three surfaces draw a booster inside the availability ring: the "On shift now" rail
(`roster_card()`), the roster board (`roster_board()`) and the track-order card (`.tko-avatar`).
`booster_face()` in build.py is the **one** implementation all three call, so a person is one face
everywhere. It used to be the first letter of the handle — which is what a face falls back to when
there is nothing to show, so the boosters page argued that real people are behind the orders over a
column of nine grey letters saying the opposite.

The order of preference, server and client alike:

1. **`assets-in/avatar/<handle>.<ext>`** — a real image, resolved through `drop_in()`. All 78 slots
   are filled today with one DiceBear **Bottts** robot per handle, seeded on the handle and
   downloaded once. They are **vendored**: the site serves `/assets/img/avatar-<handle>.svg` and
   makes no runtime request to dicebear.com. Licence, regeneration URL and the reason `portrait/`
   is deliberately *not* filled are in [site/assets-in/README.md](site/assets-in/README.md).
2. **A drawn glyph** — `D.FACE_GLYPHS`, seventeen arcade marks (gamepad, d20, skull, potion, crown …)
   in build.py's `_ICONS`, picked from the handle by `D.face_glyph()` and tinted by `D.face_tint()`
   from the booster's own `hue` — the hue `art.avatar()` paints their portrait with. This is what a
   booster added without artwork gets. Never a blank ring.
3. **The initial** — reachable only from `app.js`, and only against a `data.js` cached from before
   any of this shipped.

Load-bearing:

- **Every name in `D.FACE_GLYPHS` must be a key of build.py's `_ICONS`** — build.py asserts it at
  import, because a missing glyph draws 78 empty rings rather than failing.
- **The client never picks a face or a colour.** `boosters.py`'s `_row()` resolves `face` / `faceInk`
  / `facePlate` the same way it resolves `markColor`, and `client_data()` ships `avatars` (handle →
  URL, only for handles that actually have a file) plus `icons.faces` (17 marks, not 78). `faceMark()`
  in app.js walks the same three steps in the same order, so a row swapped in from `/api/boosters`
  can't be drawn differently than the server-rendered row it replaces.
- **`D.face_tint()` takes the handle as well as the hue.** `clean_booster()` does not require `hue`,
  and a store row without one would otherwise hand every such booster the same hue-0 red.
- **The tint is identity, never status.** Saturation is capped well under the ring's green / amber so
  a booster whose hue lands near either still reads free or busy off the rim and the pill. The three
  `.is-face` CSS selectors carry their ring (`.rst-ring .rst-initial.is-face`, …) to clear the
  `.tko-avatar .rst-initial` rule 5,400 lines further down — specificity, not source order.

## The reviews page

`page_reviews()` is the **"Reviews page"** handoff (`design_handoff_reviews`) — the page the
"4.8 / 5 · 3,140 reviews" line in the hero, the checkout and the footer leads to when someone decides
to actually check. It has one job: **let a sceptic verify the rating instead of taking it on faith**,
and every decision below is that job. It replaced a wall of ~58 identical cards at one visual weight
with no filters, no distribution and no paging — where nothing was findable and the page's own claim
was unverifiable, because every visible card was a five. Scoped on `.rvp`, tokens declared locally.

- **The distribution is a control, not a graphic.** Five rows, each a `<button aria-pressed>` that
  filters the feed. The counts are what make "we don't filter by score" checkable, so the reader can
  act on them where they read them. 4★/5★ fill with the accent; 3★ and below fill neutral — a
  negative rating shown plainly rather than dressed in brand colour.
- **`D.REVIEW_DIST` is the one place the rating is written.** `STATS["trustpilot"]` (the average) and
  `STATS["reviews"]` (the total) are computed from it in `data.py`, and `rating_dist()` computes the
  percentages. The H1's score, the summary card, the five rows, the Trustpilot badge and the checkout
  all read one source, so the numbers on this page cannot contradict each other or the rest of the
  site. The badge and the checkout summary read the same two STATS keys they always did.
- **The H1 sizes the audience, not the corpus** — "4.7 / 5 across 13K customers", where the figure is
  `STATS["clients"]` rounded by `page_reviews()`'s own `_round_k()` (deliberately not `_short_count()`,
  whose decimal would claim a precision a placeholder has not got). It reads off the same key the
  game-page stat row and the safety plate do, so the site still cannot quote two client counts — but
  note the split it introduces and keep it in view: **the score is the average of the 3,140 reviews in
  `REVIEW_DIST`, which the distribution card prints in full one column to the right.** The headline
  names the wider population those reviews came from, not what the average is over. This was an
  explicit call; the four other readers of that key still say "clients", and only this one says
  "customers". If the two are ever read as one claim, the H1 is what changes — the card is the page's
  evidence, and `REVIEW_DIST` is where the rating lives.
- **`D.REVIEWS` must keep its sub-five-star entries.** The page offers a `3★ or less` filter and a
  `Lowest rated` sort *because* the paragraph above them says nothing is hidden; an empty result
  behind either reads as suppression. One 3★ sits inside the first twelve so the default feed is not
  a wall of fives. `_pick_review()` in `data.py` still draws booster testimonials from 4★+ — that is
  attribution, not filtering: the low fixtures complain about an order changing hands, which cannot
  be printed on one named booster's profile as *their* review.
- **"Lowest rated" stays in the sort options.** Removing it to make the feed look better would
  contradict the copy two bands above it.
- **The count line counts the DOM.** Its second figure is the *filtered* total — how many reviews
  match, not the page size — and with no filter on it is the number of reviews the page actually
  publishes (58 today), never the 3,140 the aggregate is computed over. The handoff prints
  "Showing 12 of 3,140" over twelve fixtures; on a feed holding 58 that is the one claim on the page
  a sceptic could disprove by counting, which is the opposite of what the page is for.
- **The card is `review_card()`, shared with the homepage feed** — `filterable=True` adds the two
  facts the filter reads, `hide=True` ships the second page collapsed. One component, or a review
  reads one way in the feed and another on the page the feed links to.
- **Everything is server-rendered; JS only hides.** Every review is in the HTML with everything past
  `REVIEWS_PAGE` already `hidden`, so the first page reads correctly with no JS and "Load 30 more"
  reveals cards already in the document rather than fetching (the button itself is inert without JS,
  the same trade-off the roster's makes). `RVP_PAGE` / `RVP_MORE` in app.js mirror `REVIEWS_PAGE` /
  `REVIEWS_MORE` in build.py — change one, change the other. At 3,140 reviews the filter, sort and
  page become query parameters and the `data-rv-*` pair on each card is the contract for them.
- **Two controls, one state.** The distribution rows and the rating segments both write `rating` and
  are re-marked together. A row toggles back to All when it is already selected; the segments always
  set. 3★/2★/1★ have no segment, so none is marked then — that is correct, not a bug.
- **The chips are data-driven** (`review_games()`): the handoff draws six against nine catalogue
  games, which leaves an Apex review visible under "All games" and unreachable by filter. A chip
  here can never filter to nobody, and a tenth game arrives with its own chip.
- **The filter bar and the "Load more" button are the roster's**, shared by selector group in
  `site.css` rather than copied — same control, same values, from the sibling handoff. That is also
  why `.rvp` declares two overlapping token sets; the comment on the block explains which is which
  before you add a third component to this page.
- **"Read on Trustpilot" only exists once `D.TRUSTPILOT_URL` names our own profile**, the rule the
  badge already follows — and it matters most here, where the page's whole argument is "go and
  check". Until then the second action is "Read the worst first", which sets the `Lowest rated` sort
  the paragraph promises. The green tile block is still the placeholder mark, same standing as the
  rest of [Placeholder data](#placeholder-data--do-not-present-as-real).
- **"Where the score comes from" is kept below the feed.** The handoff does not draw it, but it is
  the only place the site says review requests are never incentivised — deleting signed-off copy is
  not part of porting a screen.
- **Breakpoints follow the site's 1200/1000/760**, not the handoff's 1280/1024/768. 1000 stacks the
  hero and goes to two columns; 760 is one column with 44px chips and taller distribution rows,
  which are the primary rating filter at that width. The handoff draws 1440 only.
- **i18n**: the H1's figures ride in their own nodes, so "across" and "customers" stay whole
  translatable words (`"reviews"` is still a key — it is the count line under the filters). The
  rating segment says **"Any"**, not the handoff's "All" — `"All"` is already
  the roster rail's "All 187 reviews", where French needs "Tous les". "Load 30 more" and "Show the
  rest" are two whole labels rather than one with a number interpolated into it.

## The safety & guarantee page

`page_guarantee()` is the **"Safety & guarantee"** handoff (`design_handoff_safety_guarantee`) — the
refund policy, the account-safety argument, three promises and an FAQ, in four bands. Sixth scoped
port after `.hero-a` / `.co` / `.gg` / `.dsh` / `.rst` — tokens on `.sg`, product radii per element,
nothing leaking. It is where "Money-back until a booster is assigned", checkout's "Read the
guarantee" and the nav's Safety link all land.

Its job is narrow and unusual for a marketing page: **be the page a sceptic can finish reading and
still trust.** Every claim is a number that can be checked, a mechanism that can be described, or an
admission. That is a design constraint, not just a copy one:

- **Nothing on this page animates and nothing pulses.** On a page whose subject is trust, a moving
  element reads as a sales device. The accordion is the only motion, and it is suppressed under
  `prefers-reduced-motion`.
- **One filled button on the whole page** — the hero CTA. `nav_outline=True` drops the header's, the
  FAQ's "Ask support" is a real outline and "Read the full terms" is a bare link.
- **The disclaimer is a framed plate, not fine print.** `SAFETY["disclaimer"]` is verbatim and is not
  to be softened: a page arguing for honesty cannot bury the one paragraph admitting the risk isn't
  zero. It was a ragged column floating mid-band, which is how the most important paragraph on the
  page came to look like an afterthought. Its glyph is `--g-caution`, deliberately **not** the accent.
- **The hero's stat list is what earns the column's height.** The old hero stopped at the CTA with
  ~350px of empty gradient under it. The three figures *back* the policy rather than restate it, so
  the void closed without stretching anything — delete them and it reopens.
- **Band 2 is flush left**, like every other section here. The kicker used to sit alone at the left
  edge with the heading and both paragraphs pushed into the right column; half a full-width band was
  empty and it read as a layout error. The measure card is the same argument in a second register —
  prose for readers, list for scanners.
- **`SAFETY["measures"]` is `mechanisms` plus the fifth line `body` already backs** ("Duo orders never
  touch your login at all"). The five *notes*, though, are the one place on the page that says more
  than `body` does — each is an operational commitment falsifiable by a single bad order, and
  `data.py` carries the ⚠ listing which need ops sign-off. If one isn't true, cut that note; the name
  alone still works.
- **`D.GUARANTEES` is one list rendered twice.** `guarantee_cards()` draws kicker/title/body in the
  plain `cards-3` shell on `/games/` and the game pages; `promise_cards()` draws the same entries with
  their icon tile and proof line here. Six-tuples — `(glyph, stroke?, kicker, title, body, proof)`.
  The proof line is pinned with `margin-top:auto`, which is what keeps the three on one baseline
  across cards with unequal bodies.
- **Support's proof line reads `STATS["reply"]`.** The handoff types "Median first reply 4 minutes"
  and flags it as invented; this site already measures 3m 40s, so the line is quoted, not typed.
- **The duo percentage is read off `pricing.DUO_MULT`**, same as `mode_seg(pct=True)`. The handoff's
  FAQ types 35%; this site charges 55%, and a typed percentage in a *policy answer* is exactly the
  kind of claim that drifts silently from what is billed.
- **The FAQ is single-open, and every answer is in the DOM.** Item 1 is open on load so the band never
  reads as an empty list; opening one closes the rest; clicking the open one collapses it. Panels are
  toggled with the `hidden` attribute, never conditionally rendered — the FAQPage JSON-LD asserts the
  answers are on the page, so they have to be. `.sg [hidden] { display: none; }` is the guard the rows
  need, same bug `.co` and the ops console's `.banner` hit.
- **The FAQ ids are a public contract.** Support links people at specific answers, so
  `#faq-<id>` comes from `D.GUARANTEE["faq"]` and renaming one breaks the links in old tickets. The
  deep-link scroll must be **`behavior: 'instant'`, not `'auto'`** — `ashfall.css` sets
  `scroll-behavior: smooth` globally and `'auto'` means "use the CSS value", so `'auto'` reintroduces
  exactly the animation being overridden. It also sets `history.scrollRestoration = 'manual'`, but
  only when there is a hash target: restoration runs after `load` and otherwise wins, putting a
  reader who reloads a deep link back where they were rather than on the answer the link names. The
  offset is the sheet's own `scroll-padding-top`, so the header and this stay in step from one place.
- **Three answers contradict the sales pitch on purpose**: don't queue ranked alongside an unpaused
  solo order, naming a booster means a slower start, and the ToS risk is real. They are why the page
  is credible; removing them is the single easiest way to make it worthless.
- **The FAQ intro doesn't claim a ranking it hasn't got.** The handoff's "Ranked by volume over the
  last 90 days" is flagged there as invented — this order is editorial, so the sentence says so.
- **The measure card's row rules come off in the 2-up layout** (≤1200px), rather than being trimmed on
  the last row: an odd count leaves one cell ruled and its neighbour bare, drawing a half-width line
  across the middle of the card. Whitespace separates instead, and it stays right at any list length.
- **Breakpoints follow the site's 1200/1000/760**, not the README's 1280/1024/768. 1200 narrows the
  case column and drops the measure card under the prose two-up; 1000 goes single column and the FAQ's
  sticky heading becomes a static header; 760 stacks the stat figures over their labels, aligns the
  FAQ headers to the top for two-line questions and drops the answer inset from 62px to 18px. The
  disclaimer stays full width at every size — it is never collapsed into a tooltip or a "read more".
  The handoff draws 1440 only and asks for the rest to be confirmed with the designer.
- **i18n**: the hero stat's one figure rides in its own `<b>` so the words either side stay whole
  translatable nodes; "5 days" / "24 hrs" are translated as words. The Guarantee card's proof line is
  the same sentence checkout states, so it has **one** dictionary entry, in the checkout block — the
  handoff requires the two to match word for word.

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

`data.py`'s `STATS`, `REVIEW_DIST`, `BOOSTERS`, `VETTING`, `LIVE_FEED`, `REVIEWS`, `DEMO_ORDER` and
every game except League of Legends are **invented placeholders** carried over from the handoff, as is
the key art (`keyart()` generates labelled SVG placeholders). Three of these read most like live data
and are not:
the homepage feed renders exactly the four rows in `LIVE_FEED` and nothing on the page ever adds a
fifth; `DEMO_ORDER` is one invented order drawn as a product screenshot in the dashboard section and as
the whole of `/demo.html`, which is why that page carries an Example pill in both places it shows the
order code; and **the fifty booster profiles are fifty invented people** — handles,
ranks, ratings, on-time rates, dispute counts, order histories and testimonials. A profile reads like a
personnel record, which is exactly why none of it can go live unverified, and `VETTING`'s 1,840 / 96 /
11 are load-bearing claims that must be wired to the applications queue (if the real numbers are less
flattering, ship the real numbers — the page's whole argument is that it doesn't self-report). Both
handoffs and the README flag this as blocking for launch. Their **avatars are placeholders too**: the
robots in `assets-in/avatar/` are generated from the handle, not photographs of anybody, which is the
one honest thing to put on an invented profile — a stock photograph of a real person would assert
that the invented booster exists. Replace them with real photographs of the real roster, not with
better-looking stock ones (see [Booster faces](#booster-faces--the-avatar-in-the-ring)).

**The "Watch live" panel is a facade too.** It renders real state transitions against the demo
fixture and links to the public Discord invite, but no order has a private channel behind it and
nothing asks Discord whether anyone is streaming — see the Watch live section for the seam. Do
not put it on a game page or in the order mail until `streams.py` exists.

**The header's auth panel is now partly real, not a pure facade.** `build.py`'s `AUTH_PLACEHOLDER`
block carries the full list. Email/password **login is server-verified**: the form POSTs to
`/api/account`, which checks the password against a salted PBKDF2 hash in the account store (see
[Accounts](#accounts--the-sign-up-list-in-ops)) — an unknown email or a wrong password is refused,
so the panel no longer accepts anything. What is **still unfinished and blocking for launch**: the
email/password session is a `localStorage` record, not the signed server cookie the OAuth path
(`oauth.py`) mints; there is no email verification, no password reset, and no rate limiting on the
public `/api/account`. Checkout stays guest-only, orders are tracked by an emailed link, and the
panel still says twice that an account is optional and is never their game login.

`REVIEW_DIST` is one of these and the most quotable: 2,444 / 540 / 94 / 34 / 28 invented
reviews per star, drawn on `/reviews.html` as a distribution a visitor is invited to check the rating
against, and the source `STATS["trustpilot"]` and `STATS["reviews"]` are computed from. It has to be
counted from the real corpus before launch — and so do the four sub-five-star reviews written to keep
the `3★ or less` filter from returning nothing, which are complaints attributed to nobody about
orders that never happened. Keep the warning comment at the top of
`data.py` intact, and don't let placeholder statistics leak into new copy — the site deliberately uses
one single set of numbers everywhere.

**Two review counts, and they are not interchangeable.** `STATS["reviews"]` (3,140) is the whole
corpus — Trustpilot plus the order-page rating, deduplicated, which is what `/reviews.html` says in
its own standfirst — and `STATS["trustpilot_reviews"]` (229) is the part of it that is *on
Trustpilot*. Only the second may stand next to Trustpilot's name or logo, so `trustpilot_badge()`,
`ob_trust()`, the game page's review aside and the marquee all read it; the reviews page's own
"4.7 across 3,140 reviews", its meta description and `rating_ld()`'s `reviewCount` keep the corpus
figure, because that is what the average is computed over. ⚠ The **score** beside the Trustpilot
count is still the corpus average, not Trustpilot's own — when `TRUSTPILOT_URL` names our profile,
the score on a Trustpilot-branded badge has to come from that profile too, or the badge attributes
our average to them. Both counts are placeholders until then.

Two mechanisms enforce that now, and both should survive:

- **`rating_ld()` is gated on `D.TRUSTPILOT_URL`, not on "is STATS populated?"** The nine game pages
  and `/reviews.html` were emitting `aggregateRating` (4.8 / 3,140) as JSON-LD — the machine-readable
  claim search engines render as review stars — computed from this invented distribution. That is the
  same thing the booster profiles deliberately refuse to do, for the same reason, and fabricated
  review markup is a manual-action risk. While `TRUSTPILOT_URL` is empty the figures still render as
  page copy but nothing is asserted to a crawler; wiring a real profile turns the structured data back
  on with no code change.
- **No figure on the site invents its own movement.** `[data-live]` numbers used to *wander* on a
  timer (`wanderStat()`): the header's roster count drifted ±1–2 every few seconds with nothing behind
  it, floored at 36 against a real 88, so the page showed **87 in the header, 84 in the "On shift now"
  rail and 88 in the server-rendered HTML at the same moment**. They are now written only by
  `setLiveStat()`, which `initBoosters()` calls with the counts from the same `/api/boosters` payload
  the rail and the board are drawn from. If you want a figure to look live, make it *be* live — one
  source, or it is three numbers.

`GUARANTEE` and `SAFETY` are a different kind of unverified: not invented statistics but **written
commitments**. The refund page states 5 business days to a refund, 24 hours to an automatic refund on
an unclaimed order, a 15% credit past the ETA and a pro-rata rule — and its FAQ asserts that pausing
is free and resumes the same night, that boosters never change a password or make a purchase, that
settings are mirrored then restored, and that the price is fixed at checkout. `SAFETY["measures"]`'s
five notes do the same for the VPN estate and the play window. **Each is falsifiable by a single bad
order.** Legal review the policy numbers and confirm the operational ones with ops before the page
ships; where one isn't true, cut the line rather than soften it — the page's whole argument is that
it says the checkable thing.

`CATALOG_FAQ` (the `/games/` answers) carries two of the same kind: that **everyone on the roster
plays exactly one title**, and that **there is no cross-title bundle**. The first is an intake rule
ops has to hold; the second is structural — if sales ever wants a cross-title discount, that answer
has to change before the offer ships.

The **mystery-discount store** is the newest of these and the most sensitive: `mystery.ndjson` /
`esb:bingo` holds a real email next to a token that is worth 30% of a real order for an hour. It is
not placeholder data — a captured address is a real person — so it needs the same treatment as the
carts and orders stores before launch: a lawful basis, a privacy-policy line and a deletion path.
Clear any rows written while testing; the /ops **Mystery** tab banners seeded ones.

The same rule covers **seeded analytics**: every event written by `tools/seed_analytics.py` carries
`"syn": 1`, and `/ops` shows a standing "synthetic data — not real traffic" banner for as long as
any are in the window. Keep that flag. Seeded funnel numbers are exactly the kind of thing that
quietly becomes a slide in a real meeting. Clear the store before the site takes real traffic.

The **roster store** (`src/boosters.py`, see [The roster store](#the-roster-store--boosters-in-the-backend))
is the same kind of hazard, now that the boosters board, the "On shift now" rail and the "Delivered
today" feed read it live instead of from the frozen HTML. `tools/seed_boosters.py` fills it with the
same fifty invented people and tags every row `syn: 1`; the public `/api/boosters` payload reports
`syn`, and the `/ops` Boosters tab shows a standing banner. The derived feed is **not** a log of real
deliveries — it is invented from the roster on the fly. Clear the store and load the real roster
(wired to the applications queue and the orders table) before launch.

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
- **`/api/webhook` fails CLOSED.** With no `STRIPE_WEBHOOK_SECRET` it refuses every event rather than
  trusting the body. It used to skip verification entirely when the secret was absent, which made a
  misconfigured deploy a free-order endpoint: an unsigned POST wrote a `status: "paid"` row for any
  climb, with an attacker-supplied email, straight into the fulfilment store. An unconfigured secret
  is a deployment mistake and now reads as one. `ESB_ALLOW_UNSIGNED_WEBHOOK=1` reopens it for local
  replay only.
- **Fulfilment is idempotent.** Stripe retries until it gets a 200, so the same event arrives several
  times as a matter of course: `_seen_event()` drops the repeat before it reaches the log or the
  store (the store also dedupes on `order_id`, which is what survives a restart). Session creation
  sends an `Idempotency-Key` of the minted order id, so a double-clicked Pay button resolves to one
  Session instead of two.
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
- ⚠ **A price change in `data.py` needs the server restarted too, not just a rebuild**, and the
  symptom is misleading. `serve.py` imports the price tables once at boot, so after a re-price the
  browser is served a freshly built `data.js` with the NEW prices while the running process still
  quotes the OLD ones. Every checkout then dies on the `client_total` guard with *"The price updated
  since you configured this order. Please refresh the page and try again."* — which is the one thing
  that does **not** fix it, because the client is the side that is right. The real tell is in
  `serve.py`'s stderr: `[checkout] price mismatch: shown=227 server=197`, where the ratio between
  the two numbers is exactly the re-price factor. The guard is working as designed — it refused to
  charge a number the page never showed — so do not "fix" the guard; restart the server. In
  production this cannot happen: a deploy replaces the functions.

## Outbound mail — the support form and the order confirmation

`src/mailer.py` is the **one SMTP seam** on the site: stdlib `smtplib` against the Hostinger
mailbox, no packages, and it composes nothing. Two flows send through it, and they compose their own
messages the way `accounts.py` and `guides.py` share analytics' Upstash *transport* but never its
data:

```
/support.html ──POST /api/support──► src/support.py ──► mailer ──► info@  (Reply-To: the visitor)
/api/webhook (paid) ──► payments._send_order_mail ──► mailer ──┬─► the buyer's confirmation
                                                               └─► a copy to info@
```

Config is env-only (`SMTP_USER`, `SMTP_PASSWORD`, host/port/`MAIL_FROM`/`SUPPORT_EMAIL` optional —
see DEPLOY.md's "Turn on email"). `python3 site/tools/send_test_mail.py` sends one message through
the same path and prints the SMTP error verbatim; `--order` renders the buyer's template.

- **Nothing is ever sent `From:` the visitor.** A message claiming a stranger's address fails our own
  SPF and burns the domain. The visitor rides in **`Reply-To`**, so replying in the inbox answers
  them — the support ticket and the operator's order copy both do this.
- **Every header is sanitised** (`mailer._header` / `_addr`). Subjects and Reply-To carry text a
  stranger typed into a public form, and a bare CR/LF in either is a free Bcc. `test_mail.py` locks
  it; don't route a new header around those two functions.
- **`send()` never raises** — it returns `(ok, error)`. The webhook's call is *additionally* wrapped
  and swallowed, because Stripe answers a non-200 by redelivering the event: a mail server having a
  bad minute would otherwise fulfil the order twice. `_seen_event()` already stops the retry burst,
  so a customer is never mailed twice for one payment.
- **`/api/support` stores nothing.** A ticket is a message to a human, not a list to aggregate —
  there is no store, no `/ops` tab, no row. It is defended three ways instead: everything validated
  and capped in `clean_ticket()`, a honeypot field (answered as a *success*, so a bot never learns
  which field gave it away), and a rate cap of `MAX_TICKETS` per client per 15 minutes, mirroring
  accounts.py's counter.
- **The topic is resolved server-side by index** against `D.SUPPORT["topics"]`, so the subject line
  can only ever be one of the five the page offers. The order number reaches the subject only when it
  matches the real `ESB-…` shape; a mistyped one still shows in the body, flagged, because a buyer
  fumbling their own order number is exactly the ticket a human should see.
- **A ticket is plain text, deliberately** — it carries a stranger's words, and HTML would mean
  escaping them correctly forever. The buyer's confirmation *is* HTML (with `esc()` on every
  interpolated value) because it is ours.
- **No tracking link in the order mail.** The site's FAQ promises orders are tracked by an emailed
  link and that page does not exist — `/demo.html` renders one invented fixture. A link would open
  somebody else's demo order. When a real per-order page ships it goes in `_order_text`/`_order_html`
  and that FAQ answer becomes true. ⚠ The one commitment the mail does make — "we email you when a
  booster claims it" — is **not built**; ops has to hold it or the line comes out.
- **`site_origin()` skips a localhost origin** whichever variable holds it. `PUBLIC_BASE_URL` is
  routinely a dev origin, and a `127.0.0.1` link in a customer's inbox is wrong in every environment.
- **Unconfigured degrades, never pretends.** No mailbox → `/api/support` answers 503 and the page
  shows a confirmation that says plainly nothing was emailed and names the address; the webhook skips
  the mail and still fulfils. Same contract as the Stripe seam. The form's three outcomes (sent /
  preview / failed) all ship in the DOM and are toggled, per the whole-text-node i18n rule.
- **`SUPPORT_EMAIL` in build.py is the one address in the copy** (`= FOOT_EMAIL`, `info@`), read by
  the footer, the support page's email card and its copy chip. A second literal is how a page comes
  to advertise a mailbox nobody reads.
- **Restart the server after touching these files** — `/api/support` lives in `serve.py`, no watcher.
  `api/support.py` is the Vercel shell mirroring it.

## Abandoned-checkout recovery — `carts.py` + `recovery.py`

`src/carts.py` is the **fifth store sibling** of `analytics.py` / `accounts.py` / `boosters.py` /
`orders.py` (stdlib only, Upstash in prod / NDJSON in dev, separate `esb:carts` key), and the one
place a captured email lives next to the configuration it was about to buy. `src/recovery.py` is the
mailer that acts on it. The whole flow:

```
signed-in configure ─┐                          ┌─ sweep (every 5 min, /api/sweep) ─► recovery mail (30% token)
checkout email typed ─┴─► POST /api/cart ─► carts store ─┤
   Stripe webhook (paid) ─► carts.recover() burns token ─┘  (GET /api/cart?token= resolves the discount)
```

- **Two capture points, one of them silent.** A **signed-in** visitor is captured *while they
  configure* (`app.js` `captureCart()` posts on every debounced state change) — no field, no prompt;
  the email comes from the **verified session cookie**, read by the route shell exactly the way
  `/api/orders` does, never from the body. Anyone else is captured when they **type** into `#k-email`
  on checkout. An anonymous configure with no email **stores nothing** (204). `process_capture(raw,
  header_get, session_email="")` — the session wins when both are present, because it is verified and
  the field is not. This is what stops a browser writing a cart against someone else's inbox.
- **It is not an append-only list.** A cart mutates `pending → mailed → recovered` (or `expired`), so
  the Upstash side is a **HASH keyed by token** (`HSET`), not `LPUSH`. A mailer that can't mark a row
  as sent will mail the same person every sweep.
- **The token IS the discount, and it never touches `data.py`.** `D.PROMOS` ships to the browser in
  `data.js`, so a static recovery code would be public the day it shipped. Each cart carries an
  unguessable single-use token; the percentage is resolved **server-side only** — `carts.redeemable()`
  (unknown / spent / expired → nothing) and `pricing.resolve_promo(recovery_pct=…)`, which obeys the
  same **never-stack, best-wins** rule as a typed code: 30% *replaces* the 15% sale, never 45%.
- **The client can't forge it.** `pricing.quote()` reads `recovery_pct` straight out of the order
  dict, and that dict is the checkout body — so `payments.process_checkout()` **strips it
  unconditionally** and re-derives it from the token alone (`order.pop("recovery_pct")` then a store
  lookup). A crafted `{"recovery_pct": 0.99}` would otherwise buy a $450 climb for $4.
  `test_carts.py` locks this.
- **The price is re-quoted at send time**, never read off the stored row (`recovery.price_pair()`) —
  same rule as `payments.build_session()`. A cart whose config no longer prices is mailed nothing.
- **The mail marks the row before it sends** (`recovery.send_one()`): a half-succeeding SMTP call must
  not leave the cart mailable again. Losing one recovery mail is a missed upsell; sending four is a
  spam complaint on the domain the order confirmations go out on. And the **webhook burns the token**
  on payment (`carts.recover()`), so a paid order is never mailed and a code is never spent twice.
- **The sweep fails closed.** `/api/sweep` (and `/api/cart/sweep` on serve.py) is 503 without
  `CART_SWEEP_SECRET` (16+ chars). The secret arrives as `x-sweep-secret`, or as
  `Authorization: Bearer` (what **Vercel Cron** sends via `CRON_SECRET` — set the two equal), or a
  body `secret`. `vercel.json` schedules it every 5 minutes (**Pro** plan; Hobby caps cron at daily —
  use an external trigger there). A 5-min cadence lands the mail 30–35 min after capture.
- **The checkout email note changed.** It used to promise "the order link and nothing else"; a
  recovery mail breaks that, so it now says "and to send you your cart if you don't finish." Every
  mail carries a one-click unsubscribe (`/api/cart/unsubscribe` → row `expired`).
- **`/ops` "Carts" tab** (a sibling of Orders) shows capture/recovery totals, the status split, the
  per-game breakdown and the rows, CSV-exportable. It is **distinct from the "Abandoned" tab**, which
  is the anonymous analytics view with no email. Read-only; `ops.py`'s `carts` action → `carts.summary()`.
- **Still placeholder-adjacent:** this only helps once real signed-in traffic and real checkouts
  exist. At today's volume it captures very few people — the typed-email path on checkout is the main
  source until sign-in adoption grows.
- **Restart the server after touching these files** — `/api/cart`, `/api/sweep` live in `serve.py`,
  no watcher. `api/cart.py`, `api/cart/unsubscribe.py` and `api/sweep.py` are the Vercel shells — the
  unsubscribe one exists because every recovery mail carries that link and it 404'd in
  production while working locally, which is a dead opt-out on the domain the order
  confirmations go out on. Env knobs: `CART_SWEEP_SECRET`
  (required), `CART_RECOVERY_PCT` (0.30), `CART_DELAY_SECS` (1800), `CART_TOKEN_TTL` (604800).

## The mystery discount — `mystery.py` + the modal on every game page

`design_handoff_mystery_discount`. Eight seconds after a visitor settles their **target rank** on a
game page, a modal offers a sealed "mystery discount"; an email buys the right to open it; the reveal
shows a 30% code and applying it hands them back to their order with the total already discounted. It
exists because the configurator proves intent — somebody who set two ranks and read a price is a
buyer — and captured nothing if they left.

```
target rank settles ──800ms──► 4s ──► modal ──email──► POST /api/bingo ──► token + mail
                                                              │
      every page load ──► GET /api/bingo?token= ──► ESB_BINGO ──► quote() re-prices
                                                              │
                       checkout POST { bingo: token } ──► payments re-resolves ──► Stripe
                                                              │
                                        webhook (paid) ──► mystery.redeem() burns it
```

- **Every card pays the same 30%, and that decides what the copy may say.** The pick is theatre, not
  chance. The flow must never claim the 30% was luck, that the buyer beat odds, or state any
  probability — two friends comparing cards find out in ten seconds, and a discovered lie on a store
  whose central pitch is "the price does not move after checkout" costs more than twenty margin
  points. `test_mystery.py::test_copy_claims_no_odds` asserts the shipped markup against that list.
  Two of the handoff's own strings are **deliberately not shipped** for exactly this rule, and a
  third was put back by the business after being flagged:
  - *"Bingo — card C was the best one"* — "best" implies the others were worse. It reads **"card C
    pays the top rate"**, which is true of every card and is still the emotional peak.
  - *"on your first order"* + a **First order** pill — nothing here can tell a first-time guest from a
    returning one before the modal fires. The pill claims only what the server enforces: **one card
    per inbox, ever**. If an account backend lands, "first order" can come back with a real
    suppression rule behind it.
  - ⚠ *"The deck holds 10%, 20% and 30% off"* — **shipped, on the business's explicit instruction
    (2026-08-21), having been told the deck holds one value.** It is the one line on the card that
    states something the flat deck makes untrue, and it is the line a second tab disproves. Recorded
    here rather than argued again: it is a standing decision, not an oversight, and it is not to be
    "corrected" by a later pass. The two rungs are derived from `OFFER_PCT` (`MYD_DECK` in build.py,
    asserted distinct and topping out at the real payout) so the deck's ceiling and the reveal can
    never quote two different numbers. **If it is ever revisited, the honest fix is the mechanic, not
    the sentence** — the handoff's v3 draws a real weighted 15/20/25/40 table at a blended 19.4%,
    under which naming several values is true. `test_copy_claims_no_odds` still enforces everything
    either side of it: no odds, no probability, no "lucky", no "was the best one".
  If the business ever wants genuine variance, the handoff's v3 carries a weighted 15/20/25/40 table
  at a blended 19.4% — its claims are honest *under randomness*. **Do not mix the two**: either every
  card pays the same and the copy avoids odds, or the draw is real and the odds may be stated.
- **`src/mystery.py` is the seventh store sibling** of analytics / accounts / boosters / orders /
  carts / guides — same house rules, a **separate store** (`esb:bingo` / `mystery.ndjson`), and a
  HASH keyed by token rather than a list, because rows move `issued → redeemed`. It reuses only
  analytics' Upstash *transport*.
- **The token IS the discount, and it never touches `data.py`.** `D.PROMOS` ships to every browser in
  `data.js`, so `CLIMB30` would be on a coupon aggregator within a week — the handoff says so
  outright. Each capture mints one unguessable single-use token; the percentage is resolved
  **server-side only** (`mystery.redeemable()`), and it obeys the same never-stack, best-wins rule a
  typed code does: 30% *replaces* the 15% sale, never 45%.
- **`pricing.resolve_promo(code, recovery_pct, offer_label)` is the ONE seam both token offers arrive
  through** — this one and the abandoned-cart recovery. `offer_label` exists only so the two do not
  borrow each other's wording on the receipt; it is cosmetic and is stripped from the checkout body
  alongside `recovery_pct`.
- **The client cannot forge it.** `payments.process_checkout()` pops `recovery_pct` **and**
  `offer_label` unconditionally and re-derives both from the token alone. `build_session()` only
  writes `metadata[bingo]` for a token the server itself resolved, so a made-up one can never be
  burned or credited at fulfilment. `test_mystery.py` locks all of it.
- **The JS mirror reads the offer off the STATE, not off a global.** `resolvePromo(code, s)` checks
  `s.recoveryPct` first and falls back to `window.ESB_BINGO` / `window.ESB_RECOVERY`. That is what
  lets the modal ask for a *hypothetical* quote — its whole before/after row is "what would this cost
  with 30% on it" — and it is the rule `pricing.py` already follows.
- **One hour is a real deadline, enforced by the store.** `mydBoot()` re-validates the stored token on
  **every** page load (checkout included — that page has no modal but must carry the price), and the
  reveal's own countdown clears `ESB_BINGO` and re-renders the moment it hits zero. An offer that
  quietly still works teaches buyers to ignore every future countdown.
- **The trigger is a real interaction, never a restore.** `initMystery()` arms only from
  `change`/`click` on the rank controls themselves, so a rehydrated localStorage state, a `?booster=`
  link, a bundle click or a game switch cannot fire it. A **target** control (`data-sel="to"`,
  `toTier`, `[data-subseg="to"]`) has to have been touched at least once — "after choosing his desired
  rank" — and then ~800ms of no rank input has to settle before it can fire. `MYD_AFTER_PICK` in
  app.js is the whole wait **measured from the last rank input** (6 seconds), with the settle window
  INSIDE it rather than added to it — so the constant is the figure the business asked for and not
  800ms more than it. The handoff drew 3s, this build shipped 4, then 8; the number
  is a business call about how long a visitor is left alone with the price, so change it there and
  nowhere else.
- **Once per visitor, and a decline is genuinely free.** The flag is written when the card is *shown*.
  No exit-intent second attempt, no re-fire on the next page; the `passed` card's own reversal link is
  the only way back in. It also never opens over an order that already carries a discount (a typed
  code, an applied bundle, a recovery token, a `?cart=`/`?promo=` link), over the header's sheet or
  auth panel, or on a page without a pinned configurator — so never on checkout, `/games/` or the
  homepage.
- **`ashfall.css` declares `[hidden] { display: none !important }` globally.** The five steps are
  therefore switched by **toggling the attribute** in `setView()`, not by a
  `[data-myd-view="…"] [data-myd-step="…"]` CSS rule — no selector in `site.css` can beat that
  `!important` at any specificity. `data-myd-view` on the root stays as the readable state (Escape and
  the focus trap key off it). Four of the five ship `hidden` so the page is correct before any JS runs.
- **The reveal's code chip shows the real token**, not a friendly label: it is a copy button, and a
  code you cannot paste at checkout is a support ticket. The order card's *save line* names the offer
  instead (`You save €32 · Mystery discount`), the same treatment `BUNDLE` gets — an internal
  identifier is not something a shopper reads mid-sentence. Checkout's discount row still prints the
  code, because that row is a receipt. `wirePromo()` gives an unknown `BINGO-`/`BACK-` shaped code one
  server lookup before calling it invalid, so a buyer who typed the code from their inbox is not
  refused by their own checkout.
- **The mail goes out before the reveal renders**, not after — the reveal promises a copy in the
  inbox, and a send queued behind the animation would put that promise on screen before it was true.
  With no SMTP the code is still issued and the modal swaps to a "copy it before you close this tab"
  line; `mailed` in the response is what picks between them. Degrade, never pretend.
- **The marketing opt-in is separate from the code.** The code mail is transactional and goes either
  way; the ticked box writes to `guides.py`'s list — the same one `/guides.html` fills, per the
  handoff's "one list, one preference centre, one unsubscribe". Bundling consent into a transactional
  mail is what gets a sender blacklisted.
- **The discount survives a reload AND a re-configure.** `quote()` re-prices against the new total
  rather than dropping the token when the buyer extends their climb — taking a discount away at the
  moment somebody increases their order is the worst possible time to take it back.
- **The address carries to checkout, so nobody is asked for it twice.** The modal stores it as
  `mail` on the `esb.bingo.v1` record and `mydBoot()` fills any `data-prefill-email` field from it
  synchronously at boot — before the buyer can start typing over it, and **without waiting on the
  token resolve**, which is what makes it outlive the code: someone who declined, or whose hour
  lapsed, still doesn't re-type their email. It never overwrites a field that already has a value,
  and it dispatches `input` so checkout's abandoned-cart capture treats it exactly like a typed
  address — without that, a buyer who prefilled and then left would be uncapturable. A signed-in
  visitor's verified address is the obvious second source and goes through the same helper rather
  than growing a second mechanism.
- **Applying returns to the configurator, not to checkout**, and there is no confirmation screen. The
  trigger fires eight seconds after the rank settles, so queue, server and add-ons may still be unset,
  and a percentage scales with the order — time spent configuring with −30% visible is worth more than
  one saved tap, and the sticky bar keeps checkout one tap away. **If the trigger ever moves to
  exit-intent or onto the checkout button, flip this**: there is nothing left to configure at that
  point and direct-to-checkout is right.
- **`/ops` "Mystery" tab** (a sibling of Carts): cards opened, how many are live, Apply rate, redeem
  rate, what was bought, the pick split and the rows, CSV-exportable. Read-only. The pick split is
  there because C is pre-selected — a flat A/B/C column means the mechanic engages people and an
  all-C column means it is pure friction. ⚠ **The cost is flat, not blended**: read
  `Redeemed × 30%`, never an average.
- **i18n**: all five steps ship in the DOM (a card written in by JS arrives untranslated), the card
  letter and every figure ride in their own nodes, and the value nodes are in i18n.js's `SKIP` list.
  Full `fr` and `de`.
- **Restart the server after touching these files** — `/api/bingo` lives in `serve.py`, no watcher.
  `api/bingo.py` is the Vercel shell. Env knobs: `BINGO_PCT` (0.30), `BINGO_TTL` (3600), `BINGO_MAX`.
- ⚠ **It is a live margin decision, not a UI feature.** At today's prices a redeemed code is $18–$150
  off a single order. `test_mystery.py` covers the plumbing; nothing can tell you whether the lift
  pays for it except real traffic and the Mystery tab.

### The mail sequence — `followup.py`, two more mails after the code

`src/followup.py` is to `mystery.py` what `recovery.py` is to `carts.py`: the mailer that works the
rows the store says are ready. A card that ran out of its hour unbought is the best lead the site
has — somebody set two ranks, read a price, gave an address and then stopped — and this is the
**only** other message that will ever be sent about it.

```
capture ──► MAIL 1  the code            30%, 1h    (mystery.send_code)
   +30m ──► MAIL 2  the reminder        30%, 30m left — NO new offer
   +60m ──► MAIL 3  card is over        35%, 24h   (mystery.revive: SAME token)
                          │
     all three ──► /checkout?bingo=<token> ──► the resolve carries the CONFIG
```

`/api/sweep` — the **same cron and secret as the cart recovery** — runs
`followup.sweep_all()`, which does warnings then chases. ⚠ **It is held behind
`BINGO_FOLLOWUP_ENABLED=1` and is OFF by default**, checked in
`carts.process_sweep()` before `followup` is even imported. That cron already runs
every five minutes in production, so without the gate the deploy carrying this
feature would have started mailing real addresses within minutes, unattended, on
the domain the order confirmations go out on. The default is the safety property,
not an oversight — `test_followup_is_off_unless_switched_on()` asserts it, along
with the fact that only an exact `"1"` arms it. A broken follow-up is caught and
must never take the cart recovery down with it; that has its own test too. **The two windows cannot
overlap by construction**: `due_warning()` requires the card still be inside its
hour, `due_followup()` requires it be past it. `test_warning_and_chase_can_never_collide()`
walks a card's whole life and asserts no minute claims both, because the failure it
prevents is a visitor told their discount is running out and that it has been
replaced in the same five minutes.

- ⚠ **The row tracks the LIVE order, or none of this is worth sending.** The card is
  offered ~6s after the target rank settles and people keep configuring afterwards —
  they add Priority, switch to Duo, move the server, extend the climb. A row frozen at
  capture makes all three mails quote an order the visitor abandoned two steps later,
  and `/checkout?bingo=` hydrate a basket they never wanted: not a slightly stale mail,
  an irrelevant one. `captureBingoConfig()` in app.js therefore beacons the current
  state on every `save()` (debounced 2.5s, same contract as `captureCart()`, and it
  runs on checkout too), and `mystery.update_config()` writes **`CONFIG_FIELDS` and
  nothing else**. Not `expires` — an edit is not a reason to restart a countdown, and a
  deadline that renews itself whenever the buyer touches a control is not a deadline.
  Not `pct`, `status`, `stage` or `email` either, so the beacon can neither improve its
  own offer, revive a dead card, nor re-point a row at another inbox. A **redeemed**
  row is frozen: its configuration is the record of what was bought. A **lapsed** one
  still tracks, because somebody who let the hour go and kept building is exactly who
  the chase is for.
- ⚠ **A re-capture may only touch `CONFIG_FIELDS`, and this shipped broken once.**
  `process_issue` used to rebuild the row from `clean_capture()` and copy back an
  allowlist of nine lifecycle fields, which silently dropped every field added after
  that list was written. A second capture on a chased row reset `stage` to `card`,
  `warned` to 0 and `nomail` to 0 while keeping the 35% and its 24-hour clock — so the
  card became chaseable twice, the reminder fired on a 24-hour row and mailed a real
  inbox *"1425 minutes left … halfway through its hour"*, and **an unsubscribe undid
  itself**. It now patches the EXISTING row with `CONFIG_FIELDS`, the same allowlist
  `update_config()` uses, so there is one definition of what a capture may change.
  Two regression tests hold it.
- **Mail 2 adds nothing, and that is the design.** It does not raise the rate,
  extend the clock or change the stage — `mark_warned()` writes one flag. It argues
  the deadline the store already enforces, which is the one claim on this whole flow
  that is unarguably true, so it is short: the reader saw the pitch half an hour ago.
  `warned` is its own field rather than a `stage`, precisely because the card is
  still on stage `card` afterwards.
- ⚠ **No mail may claim to be the last one.** A draft of mail 3 said "there is no
  third email" and mail 2 then made it false. A promise about what we will *not*
  send is a promise about the roadmap, not about the order in front of the reader —
  the mails state the deadline and stop. `test_no_mail_claims_it_is_the_last()`
  holds every variant to it.

- **The row is revived, never reissued.** `revive()` raises `pct` on the existing row and restarts
  its clock, keeping `status: issued` and flipping `stage` to `followup`. So the code already in the
  buyer's inbox is the one that works, one-card-per-inbox still holds, and **every client path picks
  the new rate up from `/api/bingo?token=` with no change on the client at all**. A second row would
  give one address two live discounts and break `find_by_email()`.
- **One of each, ever, and that is the whole idempotency story.** `due_followup()` requires
  `stage == "card"`, and `send_one()` revives the row — flipping it out of that set — *before* the
  message goes to SMTP. A sweep running every five minutes therefore cannot mail twice, and a crash
  between the two leaves the row chased rather than chaseable. Same trade `recovery.send_one()`
  makes: losing one upsell beats sending four.
- **A paid card is never chased and a live one is never undercut.** `revive()` refuses a `redeemed`
  row outright, and `due_followup()` waits until `expires + FOLLOWUP_DELAY` — offering a better rate
  while the first offer is still running teaches the buyer that the countdown is theatre, which is
  the one thing `TOKEN_TTL` exists to stop. A row with `applied_at` set **is** chased: somebody who
  pressed Apply and still did not pay is the strongest lead in the store, not a spent one.
- **The unsubscribe stops the mail and keeps the code.** Deliberately not `carts.py`'s
  `status="expired"` — a cart *is* its offer, but this row is a live discount the reader was just
  handed, and voiding it because they asked for fewer emails punishes them for using the link.
  `nomail` is the flag, `due_followup()` reads it, and it is the whole opt-out because this is the
  only mail the store sends. `/api/bingo/unsubscribe` mirrors the cart route in `serve.py`, with
  `api/bingo/unsubscribe.py` as its Vercel shell for the reason `api/cart/unsubscribe.py` exists.
  It retires the row from **both** sweeps, since `nomail` is read by each.
- ⚠ **A struck price in a mail is the LIST (`subtotal`), never the sale price.** Every
  discount here is a percentage of the list, and the sitewide sale is already one of them,
  so striking the post-sale total while quoting the code's rate states a reduction the
  arithmetic never made: a $48 climb sells at $41 in a 15% sale and $34 with the code, and
  the code mail shipped *"30% off your order — $34 instead of $41"*, which is 17%. It also
  disagreed with the checkout page it links to, which strikes `subtotal`.
  `mystery.list_total()` exists for this; `price_pair()`'s first element is the sale price
  and belongs only in /ops, where "what an order is worth" is the question.
  `test_a_struck_price_is_the_list_never_the_sale_price()` holds all three mails to it.
- **The mail argues with four derived numbers and types none of them.** The price pair is re-quoted
  at send time (`price_pair()`), never read off the row — same rule as `payments.build_session()`;
  the ETA is `quote()`'s; the screen share's worth is `was_pct × addon_base`, the same arithmetic
  behind the struck figure on the order card, so the mail and the page state one number; and the
  per-hour figure comes through `pricing.per_hour()`.
- ⚠ **The per-hour claim is dropped when it does not argue for the order.** `pricing.play_hours()` is
  `days × PLAY_HOURS_PER_DAY`, **bounded by the ETA** rather than computed beside it — the ETA is the
  promise on the page and a missed one costs a 15% credit, so an hours figure implying more play than
  it allows would contradict the guarantee page. A long climb still prices at $7–24/hour even at 35%,
  and `per_hour_worth_saying()` (`PER_HOUR_MAX`, $6) drops the whole block rather than printing a
  figure that argues against the sale. 92% of catalogue climbs come in under it. Same mechanism as
  `gc_faq_items()`'s "the larger of the two" clause: the claim ships only while it is true.
  **`PLAY_HOURS_PER_DAY` is an ops commitment, not a measurement** — the mail divides by it, so a
  value set too high understates the rate and the claim stops being true. Confirm 8 with ops the way
  `SAFETY`'s measure notes need confirming.
- ⚠ **The comparative half of the stream pitch is gated on `D.STREAM_CLAIM_VERIFIED`**, which is
  `False`. "Other sites charge for this" is a claim about every competitor at once and is falsifiable
  by one of them; the shipped sentence says only what is true of us. Flip the flag when it is
  substantiated and the sentence ships with no code change — the same mechanism `rating_ld()` uses to
  wait on `TRUSTPILOT_URL`.
- **The mail says "tick it", not "it is included".** `stream` is `pct=0` **with** a `was_pct`, which
  is free-but-*optional* and ships **unticked** on purpose. A mail promising an option the buyer then
  has to find, on a checkout where it sits unchecked, sells something the order does not carry — and
  pre-ticking it from a link would override a deliberate default `test_free_optional_addons()` locks.
  Naming the row is the honest fix and it is also the one that gets it attached.
- **The checkout link carries the configuration, and it has to.** A cart is captured *on* the
  checkout page, so a returning buyer's order is already in localStorage; a mystery card is opened on
  a **game** page, and `esb.order.v1` is only written when somebody presses Continue. Someone who
  never did — or who opens the mail on their phone — would land on a checkout pricing whatever that
  browser was holding, or the catalogue default. So `process_resolve()` returns `order` and
  `window.esbHydrate()` (new, in app.js) installs it **through `normalize()`**, the one validator.
  `window.esbBingoAdopt()` stores the token so stepping back into the configurator does not lose it.
- **One cron, two mailers.** `carts.process_sweep()` owns `CART_SWEEP_SECRET`, so it is the function
  holding the door; it now calls `followup.sweep()` after `recovery.sweep()` and returns it under
  `followup`, with the cart fields left at the top level so anything already reading that response
  keeps working. A broken follow-up is caught and logged rather than taking the cart sweep down with
  it. No second cron entry, no second secret to keep in step.
- **The row stores the buyer's currency** (`cur`, sent by app.js from `ESB_LOCALE.currency`), because
  this mail quotes money and a French buyer chased in dollars is the same one-set-of-numbers failure
  a bare `$5` in the chrome is. `currency_of()` falls back to `geo.currency_for(country)` and then to
  USD, so a currency with no charge rate behind it can never be displayed. `followup.money()` reads
  `pricing.CHARGE_RATES` and `payments.CURRENCY_SIGNS` — **no fifth sign table**, per the four-surfaces
  rule above.
- **`/ops` Mystery tab** gains its own banner: chased, bought, waiting, opted out, and the chase rate.
  ⚠ **Read the two rates separately** — a chased row costs 35%, not 30%, so folding them together
  understates the programme by the difference on every one.
- **Restart the server after touching these files** — `/api/bingo/unsubscribe` and `/api/cart/sweep`
  live in `serve.py`, no watcher. Env knobs: `BINGO_FOLLOWUP_PCT` (0.35), `BINGO_FOLLOWUP_DELAY`
  (**0** — the third mail's subject IS the expiry, so it lands on it: the
  business's spec is "one with the code, one reminder after 30 min, and one
  after 1 hour to say card and promo is over and last chance is 35%"),
  `BINGO_FOLLOWUP_TTL` (86400),
  `BINGO_FOLLOWUP_MAX_AGE` (259200),
  `BINGO_WARN_DELAY` (1800), `ESB_PLAY_HOURS_PER_DAY` (8), `ESB_PER_HOUR_MAX` (6).
- **`site/tools/rehearse_mail_sequence.py`** drives the whole lifecycle on a fake
  clock against throwaway stores with a captured transport — the three mails at the
  right minutes, what each says, every guard (a buyer is never chased, an unsubscribe
  sticks, a re-capture cannot reset a chased card, nothing sends twice) and the outbox.
  No socket is opened. Run it before touching the cron; it is the only way to see a
  time-based sequence whole, and it exists because two incidents reached real customers
  first.
- **`site/tools/send_test_mail.py --sequence`** renders and sends all three against a
  sample card in a **throwaway store**, so no real row is touched and no live token is
  spent. `--code` / `--warn` / `--chase` send one. It is the only way to look at these
  in a real client without waiting out an hour.
- ⚠ **The watch-live pitch is the load-bearing risk here, and it is a product one.** `streams.py`
  does not exist: nothing opens a Discord channel and nothing tells a booster to share their screen.
  This mail makes that the centrepiece of the offer, on top of the configurator row that already
  sells it. Until the seam is built, every order it wins is a manual promise ops has to keep. See
  [Watch live](#watch-live--the-boosters-screen-share--watch_panel).

## The outbox — `maillog.py`, proof of what was actually sent

The site sends seven kinds of mail from six modules on a five-minute cron, and until
this existed there was no way to answer *"what did we send that person, and when"*
except asking them to forward it. That is an operational gap, not a reporting one: a
customer wrote in asking why he was chased about an order he had not placed, and the
only honest answer available was a shrug.

- **It is written inside `mailer.send()`, and that placement is the whole guarantee.**
  Not by each caller — by the one SMTP seam on the site. A message cannot go out
  without being recorded, whoever adds the caller and whenever they add it.
  `test_every_send_lands_in_the_outbox()` asserts the placement; a second test walks
  the real call sites and fails if any `mailer.send()` forgets its `kind`.
- **Failures are logged too.** "We tried and the relay refused" and "we never tried"
  are different facts, and only one is a bug. An absent row would conflate them.
- **The body is stored, capped not dropped** — the point is being able to read what
  somebody actually received. Text and HTML both; `MAILLOG_MAX_TEXT` / `_MAX_HTML`.
- **Append-only, so a LIST** (`LPUSH` + `LTRIM`), the `guides.py` shape — a sent
  message is a historical fact and nothing may edit it. `MAILLOG_MAX` (2000) is the
  retention cap; an outbox that grows for ever is a breach waiting for somewhere to
  happen.
- ⚠ **The most sensitive store on the site**: a recipient's address beside the full
  text sent to them, live discount codes included. Fetched on demand in /ops, never
  bundled into a refresh, and it needs the same lawful basis, privacy-policy line and
  deletion path as carts / mystery / accounts before launch.

## Mail discounts — one view over every captured address

`src/maillist.py` + the `/ops` **Mail discounts** tab. One row per email address,
answering three things per person: **converted or not**, **every mail we sent them**, and
**what they did about it**.

- **It owns no store and writes nothing.** It is a read-only JOIN over `carts` (abandoned
  checkouts), `mystery` (cards, warnings, chases), `guides`, `accounts` and `orders`. A
  fifth store duplicating those emails would be a second copy of the most sensitive data on
  the site, immediately out of sync with the five originals and needing its own deletion
  path. **Do not give this module a store.**
- **`orders.by_email()` decides who converted**, not a burned token — that is what catches
  somebody who was mailed and then bought at full price, which is the case a discount
  programme most needs to see. A `recovered`/`redeemed` token counts too, since the webhook
  attributed that payment to the offer.
- **Two conversion rates, deliberately separate.** Over every captured address ("is
  collecting emails worth it") and over the people actually mailed ("are the mails worth
  it"). A lead nobody could contact belongs in the first and must never drag the second.
- ⚠ **It reports `sent`, not `delivered` or `opened`.** There is no open- or click-tracking
  on this site and adding one is a consent decision, not a feature. "Mailed 3" means three
  messages left the server.
- **The mail trail is the volume check.** One capture can now reach four messages — the
  code, the warning, the last chance, and the cart's come-back — and this tab is the only
  place that is visible per person. Watch it before turning `BINGO_FOLLOWUP_ENABLED` on.

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
| `site/src/mailer.py`, `support.py` | The SMTP seam and the contact form behind `/api/support` — see [Outbound mail](#outbound-mail--the-support-form-and-the-order-confirmation). Sends only; stores nothing. |
| `site/src/insights.py` | All aggregation. **Every number on the dashboard is defined exactly once, here.** |
| `site/src/ops.py` | Password auth + two routes: the dashboard payload, and one session's full timeline on demand. |
| `site/public/assets/js/ops.js`, `ops.css` | The console. Self-contained; shares nothing with the shop's stylesheets. |
| `site/tools/seed_analytics.py` | Synthetic traffic for testing. |
| `site/src/accounts.py` | The header sign-up list — a **separate** store, `POST /api/account` to write, `ops.py`'s `accounts` action to read. Holds name + email, never a password. The *moment* an account is made is in the analytics stream instead — see [the account flow](#the-account-flow-in-the-session-timeline). |
| `site/src/boosters.py` | The roster store — another **separate** store (operator-write / public-read), `GET /api/boosters` to read, `ops.py`'s `boosters` action for the console. See [The roster store](#the-roster-store--boosters-in-the-backend). |
| `site/tools/seed_boosters.py` | Fills the roster store from `data.py`'s `BOOSTERS` (tags rows `syn`). |
| `site/src/mystery.py` | The mystery-discount store — a **separate** store again, `POST /api/bingo` to capture + issue, `GET /api/bingo?token=` to resolve, `ops.py`'s `mystery` action to read. Holds an email next to a live single-use discount. See [The mystery discount](#the-mystery-discount--mysterypy--the-modal-on-every-game-page). |
| `site/src/maillog.py` | **The outbox** — every message the site actually sent, with its body. Written from inside `mailer.send()`, the one SMTP seam, so nothing can send without appearing; failures are recorded too. `ops.py`'s `outbox` action → the /ops **Outbox** tab. Append-only (LIST), retention-capped, and the most sensitive store here: a recipient's address next to a live discount code. |
| `site/src/followup.py` | The second mystery mail — revives a lapsed card to 35% and chases it once, on the same cron as the cart sweep. Composes its own message; shares only `mailer.py`'s transport. See [The follow-up](#the-follow-up--followuppy-one-second-mail-on-a-lapsed-card). |
| `api/collect.py`, `api/account.py`, `api/boosters.py`, `api/support.py`, `api/bingo.py`, `api/bingo/unsubscribe.py`, `api/ops.py` | Vercel shells, mirroring the `serve.py` routes. |

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
- **The Sessions tab's traffic-source filter is applied SERVER-side, before the newest-300 cap.**
  `_mod_sessions(sess, source)` narrows on the `"source / medium"` pair the table prints — the pair,
  not the source alone, so a `google.com / cpc` campaign can never hide inside `google.com /
  referral`. Filtering the rows in the browser would answer a different question and look identical:
  "every google visit this month" against "the google visits among the last 300 sessions". The menu
  is tallied **before** the filter, or picking one collapses it to the thing already picked, and a
  pick with nothing left in the period is kept in the control with a `(0)` rather than snapping back
  to All. The payload is `{rows, total, limit, source, sources, stats}` — it was a bare list.
- **That tab's tiles are counted over every MATCHED session, not over the page below them.** They
  used to be recomputed in `ops.js` from the capped rows, so a store with more than 300 sessions in
  the window published the cap as the period's session count (the tile read exactly `300`). `stats`
  in the sessions payload is the one definition now, and the sub-line says when the table is showing
  fewer rows than the tiles counted.
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

### Accounts — the sign-up list in /ops

The header's auth panel (see the site header section) has no real backend, so what "create an
account" actually produces is a name and an email. `accounts.py` is where that lead is kept, and the
**Accounts** tab in `/ops` is where it is read. It is a deliberate sibling of the analytics pipeline,
not part of it — same house rules (stdlib, no build step, file store in dev / Upstash in prod), same
public-write / gated-read shape, but a **separate store** because it holds PII the analytics store is
sworn never to.

- **It is a different store from analytics, and must stay one.** `esb:accounts` / `accounts.ndjson`,
  never `esb:ev` / `analytics.ndjson`. The analytics schema's whole value is being anonymous and
  consent-banner-free; an email in it breaks that. `accounts.py` reuses only analytics' Upstash
  *transport* (`_upstash`) and store selection, never its data. Do not merge them.
- **Passwords are only ever stored hashed.** Sign-up sends the password to `/api/account`;
  `hash_password()` runs PBKDF2-HMAC-SHA256 with a per-account random salt (stdlib `hashlib`) and the
  plaintext is verified once and never written. The hash is kept **out of the `/ops` payload** (Upstash
  keeps it in the `esb:accounts:cred` HASH, never the displayed list; the file store carries it in the
  row, and `summary()` whitelists fields). Never store, log or return a plaintext password.
- **Sign-in is verified server-side.** `_login()` in `accounts.py` reads the stored hash for the email
  and `verify_password()`s it in constant time (`hmac.compare_digest`). An unknown email and a wrong
  password both answer the same `401 {"error":"invalid"}` — the panel no longer accepts anything.
- **`/api/account` is public and unauthenticated**, exactly like `/api/collect`: the form is on every
  page. Everything is length-capped and validated (`clean_signup()` for the row, the password capped
  before hashing), and the list is read only through the password-gated `ops.py` `accounts` action,
  fetched on demand (it is PII, kept off every dashboard refresh the way session timelines are).
- **The login is rate limited and timing-flat, and both halves are load-bearing.** Failures are
  counted per (identity, client) — Upstash in production, an in-process counter under `serve.py`,
  which is one long-running process — and lock that pair out for `ATTEMPT_WINDOW` after
  `MAX_ATTEMPTS`. Matching 401 bodies were *not* enough on their own: `_login()` returned early when
  no credential existed, so an unregistered address answered in ~0ms against ~75ms for a registered
  one, and that 2000× gap enumerates the whole customer list whatever the body says. An unknown email
  now pays the same PBKDF2 against `decoy_hash()`. Sign-up is throttled per client too — its 409 is
  the same existence oracle from the other side.
- **One address, one row.** `append()` dedupes on email (lower-cased in `clean_signup()`): a repeat
  submission is dropped, first-signup wins, and duplicates inside one batch collapse. On Upstash the
  check is O(1) against the `esb:accounts:emails` SET, written in the same pipeline as the row and
  cleared with it; on the file store it scans `read()`. So re-signing-in with an existing email, or
  the facade beacon firing twice, never grows the list. The ops panel's repeat count is therefore an
  integrity check that should read zero — it only renders a tile if a duplicate ever slips through.
  (Real "that email is already registered" feedback to the visitor still needs the account backend;
  the facade beacon is fire-and-forget.)
- **Country is resolved the same way as a session** — edge header, then timezone, then locale, never
  an IP — and `cosrc` records which signal answered, shown in the panel.
- **The panel says what it is.** A standing banner names it a sign-up list against a facade, not an
  account system, so a seeded or half-built figure is never read as real customers. A second banner
  appears if any row carries `syn` (the seeder's flag, same as analytics). The store must be cleared,
  and a real backend + privacy-policy line + deletion path must exist, before these are treated as
  accounts — it is blocking for launch.
- **Restart the server after touching these files.** Like the payment and analytics routes, the
  `/api/account` and `accounts` routes live in `serve.py` / `ops.py` and only take effect on a
  process restart — there is no watcher.

#### The account flow in the session timeline

The Accounts tab answers *who* signed up; it could never answer *when, from where, or instead of
what*. Six analytics events put the flow into the `/ops` session timeline beside everything else the
visitor did, so a sign-up is readable against the order that was on screen at the time.

| Event | Reads as | Fired by |
| --- | --- | --- |
| `auth_open` | Opened the account panel | `openAuth()` — on the **open**, not the submit |
| `oauth_start` | Left for a sign-in provider | `oauthGo()`, before the redirect |
| `sign_up` | Created an account | the form's 2xx, or `?auth=<p>&new=1` on the OAuth return |
| `login` | Logged in | the form's 2xx, or `?auth=<p>` on the OAuth return |
| `auth_error` | Account step refused | every non-ok status, with the server's own reason |
| `logout` | Logged out | `signOut()` |

- ⚠ **These record the STEP, never the person.** The analytics store's whole value is that it is
  anonymous and therefore consent-banner-free (see the note at the top of `analytics.py`); the email
  and the name are in the **accounts** store, which is a separate store for exactly this reason. The
  bridge in `analytics.js` carries a fixed `META_KEYS` allowlist — `method`, `mode`, `reason`,
  `transaction_id`, `promotion` — so a future caller passing `email` into `track()` cannot silently
  persist it. Do not widen that list to anything identifying.
- **`auth_open` fires on the open because the drop is the point.** Sign-ups alone are a number with
  no denominator; open → refused → created is a funnel. `auth_error` carries the server's own status
  (`exists` / `invalid` / `weak` / `email` / `network`), because an "email already registered" wall
  and a wrong password are two completely different fixes and look identical in a raw count.
- **The OAuth round trip happens off-page, so the outcome is carried back in the query.**
  `oauth._mark_return()` appends `?auth=<provider>` and, when `accounts.append()` actually created a
  row, `&new=1`; app.js emits one `sign_up` or `login` from it and **strips both markers** with
  `stripQuery()`, so a refresh never counts the login twice. `_store_lead()` returning that boolean is
  the only place a first Google sign-in is distinguishable from the fiftieth — the browser cannot
  tell. An `oauth_start` with no `login`/`sign_up`/`auth_error` after it **is** the consent-screen
  drop, and nothing else observes it.
- **`session_start` carries `meta.account = "in"|"out"`.** A visitor who logged in last week emits no
  login of their own, and reading them as a guest is the one way this count goes quietly wrong. It is
  a boolean about the browser (`esb.session.v1` present), not an id.
- **`insights.py` folds those into one `acct` per session** — `signed_up` > `logged_in` >
  `signed_in`, `ACCT_RANK` — surfaced as a chip in the sessions table, a fact in the drill-down and
  an `account_step` column in the CSV. The **"Signed up" KPI counts `signed_up` only**, deliberately
  not "sessions with an account", which folds in everyone who was already logged in and reads as a
  far bigger number than the panel produced.
- **None of it touches the FUNNEL.** Checkout is guest-only, so the account flow sits *beside* the
  purchase funnel rather than inside it; adding these names to `FUNNEL` would put a login on the path
  to a purchase that never requires one.
- `tools/seed_analytics.py` seeds the flow with a deliberately unflattering shape (most opens close
  again), so the console can be checked without waiting for real traffic. Seeded rows carry `syn: 1`
  like everything else.

### The roster store — boosters in the backend

`src/boosters.py` is the **third sibling** of `analytics.py` and `accounts.py`: same house rules
(stdlib only, no build step, Upstash Redis in prod / an NDJSON file in dev), same public-write? — no,
**operator-write / public-read** shape, and a **separate store** (`esb:boosters` / `boosters.ndjson`,
never analytics' `esb:ev` or accounts' `esb:accounts`; it reuses only analytics' Upstash *transport*).
It exists because the roster used to be frozen into the HTML at build time — every visitor saw the
same table, the same five faces on the rail and the same four deliveries in the feed. Now those three
panels read a live store and vary between loads.

```
data.py BOOSTERS ──seed_boosters.py──► boosters store ──► GET /api/boosters ──► app.js re-renders
   (build-time fallback, SEO, counts)     (esb:boosters)    (public, rotating)   the 3 panels live
```

- **One public read, no public write.** `GET /api/boosters` is anonymous, holds no PII and no secret,
  and returns the whole board (sorted by win rate, as the server-rendered table is), a **rotating**
  rail selection, a **rotating derived** feed, and the counts the three panels quote. It is the only
  thing the site exposes; the store is filled by `tools/seed_boosters.py` (and, later, an admin flow).
  There is deliberately no public write — boosters are staff records, not visitor submissions.
- **The three panels are progressive enhancement, not a SPA.** `live_feed()`, `roster_card()` and
  `roster_board()` still render from `data.py` at build time, so the page is correct with no JS and
  legible to a crawler. `initBoosters()` in app.js then fetches `/api/boosters`; a **204 (empty
  store), a non-200 or a network failure leaves the server-rendered fallback in place** — the panels
  never blank. On success it swaps `.lf-list`, `.rc-list` and `[data-rst-body]` in, re-attaches the
  feed ticker (`initFeed()` is re-entrant — it clears its prior interval) and re-runs the roster
  filters (`window.esbRefreshRoster`, which re-reads rows from the DOM each draw).
- **JS rows are drawn with the server's own glyphs.** `client_data()` ships an `icons` map built from
  build.py's `_ico()` — the arrow, dot, hourglass and seal the three renderers reuse — so a row built
  in JS is drawn with the same marks as its server twin. Rank marks are tinted server-side
  (`markColor` from `D.tier_color()`), so the client renderer never owns a colour and can't drift.
- **The rotation is deterministic within a time bucket** (`ROTATE_SECS`), so two requests a few
  seconds apart agree, but a later load differs — that is the "not always the same preview". The
  **feed is DERIVED, never a log of real orders**: `_derive_feed()` picks a rotating handful of
  boosters and gives each a plausible climb on their own game's ladder — the same sanctioned trick
  `demo_order()` and `booster_history()` use, never a claim that those deliveries happened. Flat
  rating ladders (CS2's Premier numbers) are left out of the feed rather than drawn with a made-up
  format. `closed_24h` (the feed's "N orders closed in the last 24 hours") is `_closed_24h()` —
  derived from the roster size with a time-of-day curve and a **coarse** wobble bucket
  (`CLOSED_BUCKET`, ~2.5 min), so it drifts like a real rolling counter rather than flickering per
  reload. Still a placeholder — a real figure comes from the orders table.
- **`clean_booster()` enforces what the page argues.** A real game slug, a unique handle, and a win
  rate at or above `WR_FLOOR` — a row under the floor would contradict the boosters hero three inches
  above the table, the same reason `data.py` asserts it at import. `WR_TOP` here is kept in step with
  build.py's, because the roster's win-rate bar reads both numbers.
- **`/ops` has a read-only Boosters tab.** A sibling of Accounts (`ops.py`'s `boosters` action →
  `boosters.summary()`): totals, a free/busy split, a per-game breakdown and the roster itself,
  fetched on demand and CSV-exportable. A standing banner names it a placeholder store; a second
  banner appears if any row carries `syn` (the seeder's flag). It is read-only by design — writes go
  through the seed tool, not the console.
- **Still placeholder data — blocking for launch.** The seeded roster is the same fifty invented
  people `data.py` carries (see [Placeholder data](#placeholder-data--do-not-present-as-real)), and
  the derived feed is not a record of real deliveries. Clear the store and load the real roster —
  wired to the applications queue and the orders table — before the site takes real traffic.
- **Restart the server after touching these files.** Like every other `/api` route, `/api/boosters`
  and the `boosters` ops action live in `serve.py` / `ops.py` and only take effect on a process
  restart — there is no watcher. `api/boosters.py` is the Vercel shell mirroring the serve.py route.

## Social sign-in — Google + Discord OAuth

`src/oauth.py` is the real authorization-code flow behind the header's two OAuth buttons — the same
house rules as payments (stdlib `urllib` against each provider's REST API, no packages, no framework).
It turns "Continue with Google/Discord" from a facade into a working login: redirect to the provider,
exchange the code **server-side** (the client secret never touches the browser), read the verified
name + email, store that lead in the **same** `accounts.py` list the email form writes to, and mint a
signed **HttpOnly session cookie**.

```
button ─► GET /api/auth/<provider> ─► 302 to provider ─┐ (Set-Cookie: signed state)
                                                        ▼ user consents
header ◄─ 302 return_to ◄─ GET /api/auth/<provider>/callback  (Set-Cookie: signed session)
  │  reads /api/auth/me (session + which providers are wired)   └─► accounts.append(verified lead)
```

- **The flow logic lives in `oauth.dispatch()` alone.** `serve.py`'s `_auth()` and the four
  `api/auth/*` Vercel shells both render the same `{status, json, location, set_cookie}` descriptor,
  so the local server and the serverless functions can't drift — the project's rule that `/api` is a
  thin mirror of `serve.py`. The Vercel routes are `api/auth/me.py`, `api/auth/logout.py`,
  `api/auth/[provider].py` and `api/auth/[provider]/callback.py`.
- **Four routes.** `GET /api/auth/<provider>` starts it (signed state cookie + 302);
  `GET /api/auth/<provider>/callback` finishes it (token exchange → session cookie → 302 to
  `return_to`); `GET /api/auth/me` is the client's source of truth (current session + `{google,
  discord}` availability); `POST /api/auth/logout` clears the cookie.
- **CSRF is a signed `state` in both the redirect and an HttpOnly cookie**, checked to match on
  return; nothing is trusted from the query string alone. `return_to` is validated by `_safe_return()`
  to a bare same-site `/path` — an open redirector is the classic OAuth bug.
- **The session cookie is signed with `SESSION_SECRET`** (HMAC-SHA256, `_sign`/`_unsign`), `HttpOnly`,
  `SameSite=Lax`, `Secure` only on https (localhost over http would drop it), 30-day expiry to match
  the panel's copy. Absent `SESSION_SECRET`, it falls back to a per-process random key — logins work
  but don't survive a restart, which is the safe failure, not a shared default.
- **Graceful degradation, same contract as Stripe.** A provider with no `CLIENT_ID`/`CLIENT_SECRET`
  pair is reported disabled by `/api/auth/me`; `app.js` keeps that button's honest facade message
  ("Social sign-in isn't connected yet") instead of navigating to a 503. So the static preview still
  walks. Config is env-only: `GOOGLE_/DISCORD_CLIENT_ID` + `_SECRET`, `SESSION_SECRET`,
  `PUBLIC_BASE_URL` (the redirect-URI origin, shared with Stripe). See DEPLOY.md.
- **The client reconciles two session mechanisms.** Email/password logins are a `localStorage` record
  (`esb.session.v1`); OAuth logins are the server cookie. `loadMe()` in `app.js` upgrades the header
  to a live cookie session but never clears a localStorage one when the cookie is absent, and
  `signOut()` clears both. A failed callback returns to `?auth_error=<msg>`, which the header surfaces
  in the panel and strips from the URL.
- **An OAuth lead is stored via `accounts.append`, not `create_account`** — it has no local password
  (the provider is the credential), so `credential(email)` is empty for it and email/password login
  won't match. It's tagged `mode: "oauth:<provider>"`, visible in the `/ops` Accounts tab. Linking an
  OAuth login to an existing email/password row is unbuilt — see `build.py`'s `AUTH_PLACEHOLDER`.
- **The brand marks are `_hd_brand()` in `build.py`** — Discord's Blurple mascot and Google's
  four-colour G, simplified reproductions. Before launch, swap for each provider's licensed sign-in
  button asset (same trademark rule as `pay_marks()`).
- **Restart the server after touching these files** — `/api/auth/*` lives in `serve.py`, no watcher.

## CRO audit constraints

`CRO-AUDIT.md` (+ `.fr.md` translation) is the audit this build answers; the README lists which
findings are fixed. Several fixes are load-bearing and easy to regress:

- Guest checkout only — no login wall anywhere in the order flow.
- `begin_checkout` fires **before** navigation to checkout, not on arrival.
- All money formatted via `Intl.NumberFormat` / `usd()` — never a bare `$9.6`.
- No third-party trust badges linking off-brand; one set of statistics across the whole site.
- The configurator stays above the fold on every game page, with the sticky mobile price bar.
- Every page keeps its canonical tag, JSON-LD block and real `h1`/`h2`/`h3` hierarchy.
