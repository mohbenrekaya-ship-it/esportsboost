# eSportsBoost — Conversion Rate Audit

**Audited:** 10 Aug 2026 · live site only (`www.esportsboost.com`), no repo, no analytics access
**Stack observed:** Next.js (App Router, i18n `en`/`fr`) behind CloudFront
**Tracking observed:** GA4 `G-GB2Q83DBQL`, Google Ads `AW-18171663463`, Meta Pixel + CAPI gateway (`capig.datah04.com`)

## Scope & confidence

Everything below is observed from the live front end. I could **not** measure your actual conversion rate,
traffic mix, or where users drop — that needs GA4/Ads access. So the prioritisation is based on the *size
of the friction*, not on measured loss. Where I'm inferring, I say so.

The single most important context: **you are paying for traffic** (Google Ads + Meta pixel are live).
That makes the two P0 items below expensive, not just suboptimal.

---

## P0 — Fix first

### 1. The buy button opens a login wall. There is no guest checkout.

**Observed:** on `/en/games/league-of-legends`, configuring a boost and clicking the primary CTA
("Rank Up For $9.6") opens a modal: *Sign in with Google / Facebook / Discord / Login with email*.
No "continue as guest", no "checkout without an account" option is presented.

Why this is the top item:

- Forced account creation is one of the most-cited causes of checkout abandonment in every published
  cart-abandonment study.
- Your audience is **specifically privacy-motivated**. Your own page sells "100% Safe & Anonymous",
  "Show As Offline In Chat", "Invisible Mode", "VPN Protection" — and then requires the buyer to hand
  over a Google/Facebook identity before they can see a payment form. The offer and the flow contradict
  each other.
- Boosting is an impulse purchase at a $10–50 price point. The account step costs more perceived effort
  than the product costs money.

**Action:** add email-only guest checkout. Collect email → payment → create the account silently
post-purchase and email a magic link to track the order. Keep social login as the *fast* option, not
the *only* option.

**Secondary bug in the same modal:** the heading says "Welcome Back To Esports Boost" — greeting a
first-time buyer as a returning one. Below it, "Don't Have An Account?" is followed by a button labelled
"Login With Email". The signup path is labelled as login. New users have no visible way in.

### 2. The ecommerce funnel is not tracked. Your ad platforms are optimising blind.

**Observed:** `dataLayer` after a full page load and a series of interactions contained **only** GTM
built-ins: `gtm.dom`, `gtm.scrollDepth`, `gtm.load`. Nothing else.

I actively tested this — switched service tab (Division Boost → Ranked Wins), toggled Solo/Duo, and
clicked the checkout CTA. **Zero events pushed.** No `view_item`, no `add_to_cart`, no `begin_checkout`.

Consequence: Google Ads Smart Bidding and Meta's optimiser have no mid-funnel signal. They can only
learn from final purchases (if those even fire — I couldn't reach a thank-you page to confirm). With
purchase volume at this price point, that's almost certainly too sparse a signal to train on, so you are
paying for clicks the algorithm cannot qualify.

**Action:** implement GA4 ecommerce events, then import them as Ads conversions:

| Event | Fires when | Params |
|---|---|---|
| `view_item` | game page loads | `item_id` (game), `value`, `currency` |
| `select_item` | service tab switched | `item_variant` (division/wins/placements) |
| `add_to_cart` | rank selection completes | `value`, ranks as `item_variant` |
| `begin_checkout` | checkout CTA clicked (**fire before the auth modal**) | `value`, options |
| `login` / `sign_up` | auth completes | `method` |
| `purchase` | order confirmed | `transaction_id`, `value`, `currency`, `items` |

Firing `begin_checkout` *before* the auth modal is the important detail — it's the only way you'll
measure how many people the login wall actually costs you. That number will also settle item #1 with
data rather than argument.

Mirror `purchase` server-side to Meta CAPI (the gateway is already installed) and to Google Ads
Enhanced Conversions.

### 3. Trust badges at the point of purchase link to a different company.

**Observed:** both Trustpilot elements —

- "Rated 4.6/5 on ⭐Trustpilot", sitting directly beneath the checkout CTA
- "Excellent · Based on 225 Verified Reviews"

— link to `https://www.trustpilot.com/review/lolepicshop.com`.

A buyer who clicks your review proof at the highest-intent moment lands on **lolepicshop.com's**
Trustpilot page. If that's a sister brand, the visitor doesn't know that; they see a different company
name and read it as a copied template or a scam signal.

**Action:** point these at esportsboost.com's own Trustpilot profile. If you don't have one yet with
real volume, remove the link and use on-site testimonials until you do — an unlinked claim is safer
than a link that appears to expose a different brand.

**Related inconsistency:** the homepage hero says *"Rated 4.6 by over 10,000+ customers"*, and the same
page says *"Based on 225 Verified Reviews"*. Two different trust numbers, both visible, one page. Pick
one framing: "4.6/5 from 225 reviews · 10,000+ orders delivered" is honest and consistent.

---

## P1 — High impact, low effort

### 4. Prices render unformatted: `$9.6`, `$1.92`

Should be `$9.60`. A truncated cent reads as a rounding bug and, on a page asking for card details,
quietly signals "amateur build". One `Intl.NumberFormat` call fixes every price on the site.

```js
new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(9.6) // "$9.60"
```

Use the same helper for the cashback figure and the checkout summary.

### 5. The configurator is below the fold on every game page

Above the fold on `/games/league-of-legends`: hero art, the game title, and a 20% Cashback banner. The
rank selector — the actual product — starts around 1050px, below a 812px mobile viewport. Users must
scroll past ~1.3 screens of decoration to reach the thing they came for.

The cashback banner is a *retention* offer occupying the site's most valuable *acquisition* real estate.

**Action:** move the rank selector above the cashback banner; shrink the hero to ~40vh. Target: current
rank → desired rank → price visible without scrolling on a 812px viewport. A/B this one, it's easy to
measure once #2 is in place.

*(Credit where due: the mobile sticky bottom bar with live price + CTA is well done. Keep it.)*

### 6. "24/7 Customer Support" with no live chat

Both "Let's Chat" and "Visit Help Center" go to `/contact-us` — a form. No chat widget is loaded
(checked for Intercom, Crisp, Tawk, Zendesk, Tidio, Freshchat — none present).

Promising 24/7 support and delivering an email form is a promise/delivery gap that costs you exactly the
hesitant buyers you need. Given the audience, **a public Discord is worth more than a chat widget** —
it's where this market already lives, it doubles as social proof, and it's free.

**Action:** either install real chat, or relabel to "24/7 support via email & Discord" and link an
actual Discord invite. Don't leave the current version.

### 7. The refund FAQ increases risk instead of removing it

> "Refund policies may depend on the order status and service conditions. Please contact our support team
> if you need help with refunds, cancellations, or order changes."

This is the answer a hesitant buyer reads last before deciding. It commits to nothing. Every competitor
in this space leads with an explicit guarantee.

**Action:** state a concrete policy — e.g. "Not started within 24h? Full refund, no questions.
Boost incomplete? Pro-rated refund on the unfinished portion." Then put it as a badge next to the
checkout button, not buried in an accordion.

---

## P2 — SEO & technical (compounding, slower payoff)

### 8. No structured data anywhere

Zero `application/ld+json` on the homepage or game pages. You have all the raw material for rich results
and are using none of it:

- `Product` + `Offer` + `AggregateRating` on game pages → price and stars in the SERP
- `FAQPage` on the FAQ blocks (already written, just unmarked)
- `BreadcrumbList`, `Organization`

This is a pure SERP click-through-rate gain — same ranking, more clicks. Cheapest SEO win available.

### 9. No `og:image` — every shared link previews blank

Game pages have `og:title` and `og:description` but **no `og:image`** and no `twitter:card`.

Your audience shares links on **Discord**. A link with no preview image looks broken and gets ignored.
This is free organic distribution you're currently discarding.

**Action:** per-game OG images (`/opengraph-image.tsx` in Next.js generates them at build time), plus
`twitter:card=summary_large_image`.

### 10. No canonical tags + sitemap points entirely at redirects

- No `<link rel="canonical">` on any page checked.
- `/games/league-of-legends` → **307** → `/en/games/league-of-legends`. Both forms are linked internally
  from the same homepage.
- `sitemap-0.xml` lists **17 URLs, and every one of them is a redirecting non-locale URL.** Sitemaps must
  list final destinations.
- The **entire French site is missing from the sitemap.** `/fr/games/league-of-legends` returns 200 with
  properly translated meta — real, working, translated pages that you are not submitting for indexing.
- `hreflang` is served correctly via HTTP `Link` header (en/fr/x-default). That part is fine.

**Action:** add self-referencing canonicals; regenerate the sitemap with locale-prefixed URLs for both
`en` and `fr`; normalise internal links to the prefixed form.

### 11. Homepage has one `<h1>` and zero `<h2>` elements

"Choose Your Game", "Boosting Made Simple", "Our Blogs", "Frequently Asked Question" — none are headings.
The page is semantically flat to crawlers and unnavigable by screen reader.

Also: **27 of 74 images have no `alt`.**

### 12. Homepage meta description is doing nothing

> "eSports Boost is a platform that allows you to boost your skills and improve your game."

No keyword, no price signal, no differentiator, no CTA — and it's ambiguous enough to read as a coaching
site. The game pages' descriptions are much better; bring the homepage up to that standard.

### 13. TTFB ~1.07s, and HTML is explicitly uncacheable

```
cache-control: private, no-cache, no-store, max-age=0, must-revalidate
x-cache: Miss from cloudfront
```

Every visit is a full origin round-trip; CloudFront caches nothing. Google's "good" threshold is <800ms,
and TTFB is a direct input to LCP. Marketing pages have no reason to be `no-store`.

**Action:** for game/blog/policy pages use ISR (`revalidate`) or `s-maxage=300, stale-while-revalidate`.
Keep `no-store` only on authenticated routes. Should be a one-line change per route — the biggest
single perf win available.

*(Page weight itself is fine: 628KB / 123 requests. Largest asset is a 208KB WebP background.)*

### 14. Thin content surface — 17 URLs total

Six game pages and five blog posts, all dated 2023–2024, on a site whose footer reads © 2026. Stale
dates on the only content you have is a bad look for a "current meta" product.

You have no landing pages for the actual money keywords: `lol duo boost`, `valorant rank boost`,
`iron to gold boost`, `elo boost cheap`, per-region and per-rank variants. Competitors rank on exactly
these. This is the long-term growth lever, but it's slower than everything above — do it after P0/P1.

---

## Suggested sequence

**Week 1 — instrument, then fix what you can measure**
1. GA4 ecommerce events (#2) — do this *first*, it's how you'll prove the rest
2. Fix Trustpilot links (#3) and reconcile the 4.6 / 225 / 10,000 numbers
3. Price formatting (#4)
4. Modal copy: "Welcome Back" → neutral, fix the signup label (#1b)

**Week 2 — the big one**
5. Guest checkout (#1) — with `begin_checkout` already firing, you'll see the before/after directly
6. Refund guarantee copy + badge (#7)
7. Discord link or real chat (#6)

**Week 3 — layout + free SEO**
8. Configurator above the fold, A/B tested (#5)
9. JSON-LD (#8), OG images (#9)
10. Canonicals + sitemap regeneration (#10)

**Week 4+**
11. Cache headers / ISR (#13)
12. Headings + alt text (#11), homepage meta (#12)
13. Keyword landing pages (#14)

---

## What I need to go further

- **GA4 + Google Ads access (read-only)** — to replace "this friction looks expensive" with "this step
  loses N% of sessions". Changes the priority order if the data disagrees with me.
- **Repo access** — most of P0/P1 is a small number of concrete diffs I can write directly.
- **Answers to two things I couldn't determine from outside:**
  - Is `lolepicshop.com` yours? It changes whether #3 is a broken link or a branding decision.
  - Does a `purchase` event fire on the order-confirmation page? I couldn't complete a purchase to check.
