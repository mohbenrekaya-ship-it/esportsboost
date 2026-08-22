# Deploying esportsboost to Vercel

The site deploys as **one Vercel project**: the 24 static pages are served from
Vercel's CDN, and the three payment routes run as **Python serverless
functions** in `/api`. No Node, no build dependencies — Vercel runs
`python3 site/build.py` to generate `site/dist/`, exactly like local.

```
/api/checkout.py   POST /api/checkout   → create a Stripe Checkout Session
/api/session.py    GET  /api/session    → success-page receipt lookup
/api/webhook.py    POST /api/webhook    → Stripe fulfilment event
```

All three are thin shells over `site/src/payments.py`, the same module the local
`serve.py` uses — one source of truth for pricing and Stripe.

---

## What's already wired

| File | Purpose |
| --- | --- |
| `vercel.json` | Build command, output dir (`site/dist`), clean URLs, bundles `site/src/**` into the functions |
| `.vercelignore` | Keeps the reference `redesign_zip*/` dirs and local logs out of the upload |
| `api/*.py` | The serverless functions (payment, analytics, accounts, guides, boosters, support, auth) |
| `site/src/payments.py` | Shared Stripe + pricing logic |
| `site/src/analytics.py`, `insights.py`, `ops.py` | Shared analytics logic behind `/ops` |
| `site/src/mailer.py`, `support.py` | Outbound SMTP, and the `/api/support` contact form behind it |

You do **not** need to run the build yourself — Vercel runs it on every deploy.

---

## ⚠ Set `SITE_URL` before the first real deploy

This is the one variable that breaks silently. Every absolute URL in the build —
the `<link rel="canonical">` on all 114 pages, `og:url`, the JSON-LD `url`/`@id`
fields, all 110 entries in `sitemap.xml`, and the `Sitemap:` line in
`robots.txt` — is written against `data.py`'s `SITE`, at build time.

| Name | Value |
| --- | --- |
| `SITE_URL` | `https://esportsboost.com` |

Without it the build falls back to Vercel's own
`VERCEL_PROJECT_PRODUCTION_URL`, and if that is missing too, to
`http://localhost:4321`. A deploy carrying localhost canonicals tells every
crawler that all 114 pages are duplicates of a host it cannot reach, and the
sitemap you submit to Search Console is 110 dead URLs. Nothing looks wrong in a
browser — the pages render perfectly — so this is only ever caught by viewing
source or by the traffic never arriving.

Check it after deploying:

```bash
curl -s https://esportsboost.com/ | grep -o '<link rel="canonical"[^>]*>'
```

It must print your real domain. Re-deploy after changing it: `SITE` is read at
**build** time, so an env change needs a new build, not just a restart.

---

## Deploy — recommended path (browser only, no Node needed)

This machine has `git` but no Node, so the Vercel CLI isn't the easy route.
Use the Git integration instead:

1. **Create a free Vercel account** at <https://vercel.com/signup> (log in with
   GitHub is simplest).

2. **Put the project on GitHub.** From the project root:

   ```bash
   git init
   git add -A
   git commit -m "esportsboost site + Stripe payment functions"
   ```

   Create an empty repo on github.com, then:

   ```bash
   git remote add origin https://github.com/<you>/esportsboost.git
   git branch -M main
   git push -u origin main
   ```

3. **Import it on Vercel.** Dashboard → **Add New… → Project** → pick the repo →
   **Import**. Vercel reads `vercel.json`, so the framework is “Other”, the build
   command and output directory are already correct. Click **Deploy**.

   The site goes live at `https://<project>.vercel.app` within a minute. At this
   point the pages work and checkout falls back to its **preview confirmation**
   (no charge) because no Stripe key is set yet — see the next section to turn on
   real payments.

### Alternative: Vercel CLI

If you install Node first (`brew install node`), you can skip GitHub:

```bash
npm i -g vercel
vercel        # first run links/creates the project
vercel --prod # production deploy
```

---

## Turn on real payments (Stripe)

1. In the **Vercel dashboard → Project → Settings → Environment Variables**, add:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `STRIPE_SECRET_KEY` | `sk_test_…` (or `sk_live_…`) | Required to charge. Start with a **test** key. |
   | `STRIPE_WEBHOOK_SECRET` | `whsec_…` | **Required.** From step 3 below. Without it `/api/webhook` refuses every event (400 `webhook_not_configured`) — see the warning under step 3. |
   | `PUBLIC_BASE_URL` | `https://esportsboost.com` | **Set this.** If unset, the origin comes from the request's `Host` header, which the caller controls — a forged header then lands in Stripe's success/cancel URLs. Fine only for local work. |

   Add them for **Production** (and Preview if you want test payments on preview
   deploys). **Redeploy** after adding — env vars only apply to new deployments.

2. **Get your keys** at <https://dashboard.stripe.com/apikeys>. Use test mode
   while verifying; flip to live keys when you're ready to take real money.

3. **Create the webhook** at <https://dashboard.stripe.com/webhooks> → **Add
   endpoint**:
   - URL: `https://<your-domain>/api/webhook`
   - Event: `checkout.session.completed`
   - Copy the **Signing secret** (`whsec_…`) into `STRIPE_WEBHOOK_SECRET`, then
     redeploy.

   > ⚠ **`/api/webhook` fails closed.** With no `STRIPE_WEBHOOK_SECRET` set it
   > rejects everything rather than trusting the request body. That is
   > deliberate: the route is public, and an unverified
   > `checkout.session.completed` is a free order — anyone who can reach the URL
   > could post one for the most expensive climb on the board, with an address
   > they control, and it would land in the fulfilment store marked `paid`. If
   > orders stop appearing after a deploy, this variable is the first thing to
   > check; the function log prints `[webhook] refused: STRIPE_WEBHOOK_SECRET is
   > not set`. To replay unsigned events locally, set
   > `ESB_ALLOW_UNSIGNED_WEBHOOK=1` — never in production.

4. **Test the full flow** with Stripe's test card `4242 4242 4242 4242`, any
   future expiry, any CVC. You should land on `/checkout/success` with a receipt,
   and see a `paid order → ESB-…` line in the function logs (Vercel → Project →
   Logs).

---

## Turn on email (Hostinger SMTP)

Two things send mail, and both go through `site/src/mailer.py`, so this one
mailbox switches on both:

- **the support form** on `/support.html` → a ticket lands in the inbox, with
  the visitor's address as `Reply-To`, so hitting reply answers them;
- **a paid order** → the buyer gets a confirmation, and the inbox gets a copy so
  you see the order land without watching `/ops`.

1. In **Vercel → Project → Settings → Environment Variables**, add:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `SMTP_USER` | `info@esportsboost.com` | The **full address**, not `info`. This is the #1 cause of a `535` auth failure. |
   | `SMTP_PASSWORD` | the mailbox password | From hPanel → Emails → your mailbox. Not your Hostinger account password. |
   | `SMTP_HOST` | `smtp.hostinger.com` | Optional — that is already the default. |
   | `SMTP_PORT` | `465` | Optional. 465 is implicit TLS (the default); `587` switches to STARTTLS. |
   | `MAIL_FROM` | `info@esportsboost.com` | Optional, defaults to `SMTP_USER`. **Must be a mailbox on your own domain** — see the SPF note below. |
   | `SUPPORT_EMAIL` | `info@esportsboost.com` | Optional, defaults to `MAIL_FROM`. Where tickets and order copies land, if you ever split sending from receiving. |

   Redeploy afterwards — env vars only apply to new deployments.

2. **Test it before trusting it.** Locally, put the same values in `.env` and run:

   ```bash
   python3 site/tools/send_test_mail.py
   ```

   It sends one message through the exact code path the site uses and prints the
   SMTP error verbatim if it fails, with the three usual causes. `--order`
   renders the real order-confirmation template instead, so you can look at what
   a buyer receives without paying for a boost.

3. **Set SPF and DKIM on the domain, or the mail goes to spam.** Hostinger
   publishes both for you when the domain's DNS is with them (hPanel → Emails →
   DNS records); if DNS is elsewhere, copy the SPF `TXT` record and the DKIM key
   across. This matters because the site sends *as* `info@esportsboost.com` from
   Hostinger's servers — mail claiming your domain from an unlisted sender is
   what a spam filter is for.

   > The site never sends **as** a visitor. A stranger's address goes in
   > `Reply-To`, never `From` — a message From: someone else's domain fails
   > their SPF and burns yours. Don't "fix" a ticket's From line to make replies
   > easier; reply already works.

4. **Nothing is configured → nothing pretends.** Without `SMTP_USER` /
   `SMTP_PASSWORD` the support form answers `503` and shows a confirmation that
   says plainly that nothing was emailed and names the address to write to, and
   the order webhook skips the mail and still fulfils. The same contract the
   Stripe seam has: a preview deploy stays honest.

   > If `/api/support` returns `502` in production, the mailbox is configured
   > but the send failed — the function log carries the SMTP error. Should
   > Vercel's runtime ever block outbound SMTP (ports 465/587 work today), the
   > swap is `mailer.send()` to a provider's HTTP API; nothing else changes,
   > because that function is the only thing on the site that opens a socket to
   > a mail server.

---

## Turn on the analytics console (/ops)

The dashboard lives at `https://<your-domain>/ops`. It ships on every deploy but
**refuses to show anything until you configure it** — no password, no data.

1. **Create a free Upstash Redis database** at <https://console.upstash.com>
   (Vercel → Integrations → Upstash also works and injects the variables for
   you). This is where events are stored. It is needed because Vercel's
   filesystem is ephemeral: without it, every event is lost the moment the
   function freezes.

2. In **Vercel → Project → Settings → Environment Variables**, add:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `OPS_PASSWORD` | a long random string | **Required.** Minimum 12 characters or the API stays off. This is the only thing standing between the public internet and your business numbers — use a password manager, not a word. |
   | `UPSTASH_REDIS_REST_URL` | `https://…upstash.io` | From the Upstash console. |
   | `UPSTASH_REDIS_REST_TOKEN` | the REST token | From the Upstash console. |
   | `ANALYTICS_MAX_EVENTS` | `50000` | Optional. Caps the stored event list. |
   | `ACCOUNTS_MAX` | `20000` | Optional. Caps the stored sign-up list. |

   The sign-up list (the header's auth panel) uses the **same** Upstash
   credentials as analytics — a separate Redis key, no extra variables. Without
   Upstash it writes `accounts.ndjson` next to `analytics.ndjson`, both
   gitignored.

   **Redeploy** after adding — env vars only apply to new deployments.

3. **Check it.** Load a couple of pages on the live site, then open `/ops`, sign
   in, and look at the **Live** tab. Your own visit should be at the top. If the
   store badge in the header says `file` rather than `upstash`, the Upstash
   variables did not reach the function.

Notes worth keeping in mind:

- **Nothing is linked to `/ops`.** It is `noindex`, `Disallow`-ed in robots.txt
  and absent from the sitemap, but the URL is still guessable — the password is
  the actual security boundary, so treat it like one. Failed logins are
  throttled (10 per 15 minutes) once Upstash is configured.
- **The analytics data is anonymous and cookieless** — no IP, no email, no name
  — which is why the site needs no consent banner for it. Adding an identifying
  field to *that* store would change that. The **sign-up list is the deliberate
  exception**: it holds the name and email people submit through the header, so
  it is personal data. It lives in its own store precisely to keep the analytics
  guarantee intact, and it needs the usual treatment for PII — a lawful basis to
  collect it, a privacy-policy line that says you do, and a way to delete on
  request. **No password is ever stored** (the auth flow drops it in the
  browser); do not add one, this codebase does no hashing.
- **The account system is a facade until a real backend lands.** The header lets
  someone "create an account", but there is no session, verification or login —
  the sign-up list is a lead list, and `/ops` labels it as one. Wiring a real
  backend is blocking for treating these as accounts.
- **Clear seeded data before launch.** If you ever ran
  `site/tools/seed_analytics.py` against the production store, wipe it — `/ops`
  will warn you with a banner for as long as synthetic events are present.

---

## Turn on abandoned-checkout recovery

When a **signed-in** visitor configures an order, or **anyone** types their email
on the checkout page, and then doesn't pay, the configuration is captured. Thirty
minutes later a sweep mails them a single-use 30%-off link. A paid order burns the
code. The captured carts, and how many came back, are in the **Carts** tab of
`/ops`.

It needs three things already covered elsewhere in this doc — the Upstash store
(same credentials as analytics), **email** (the [Turn on email](#turn-on-email-hostinger-smtp)
section — the recovery mail goes out through the same SMTP seam), and Stripe (so
a payment can burn the token) — plus two of its own:

1. In **Vercel → Project → Settings → Environment Variables**, add:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `CART_SWEEP_SECRET` | a long random string (16+ chars) | **Required.** Protects `/api/sweep`. Without it the sweep is `503` and **no recovery mail is ever sent** — an unprotected sweep endpoint would let anyone make the site send mail on demand. |
   | `CRON_SECRET` | **the same value** as `CART_SWEEP_SECRET` | Vercel Cron sends `Authorization: Bearer $CRON_SECRET`; the sweep accepts that as its secret, so setting the two equal makes native cron authenticate itself. |
   | `CART_RECOVERY_PCT` | `0.30` | Optional. The discount, as a fraction. Defaults to 30%. |
   | `CART_DELAY_SECS` | `1800` | Optional. How long after capture a cart becomes mailable. Defaults to 30 minutes. |
   | `CART_TOKEN_TTL` | `604800` | Optional. How long a recovery code works. Defaults to 7 days. |
   | `CARTS_MAX` | `5000` | Optional. Caps the stored cart list. |

   **Redeploy** after adding.

2. **The sweep is already scheduled.** `vercel.json` carries a `crons` entry that
   hits `/api/sweep` every 5 minutes — this needs the **Vercel Pro** plan (Hobby
   caps cron at once per day, which cannot honour a 30-minute delay; on Hobby,
   point an external scheduler such as cron-job.org at
   `https://<your-domain>/api/sweep` with an `x-sweep-secret: <CART_SWEEP_SECRET>`
   header instead, and remove the `crons` block). A 5-minute cadence means the
   mail lands 30–35 minutes after capture — close enough to the promise, and
   deliberately not per-minute.

3. **Check it.** Locally, run the server with the secret set and a real captured
   cart older than the delay:

   ```
   CART_SWEEP_SECRET=… CART_DELAY_SECS=0 SMTP_USER=… SMTP_PASSWORD=… \
     python3 site/serve.py 4321
   curl -X POST localhost:4321/api/cart/sweep -H 'x-sweep-secret: …'
   ```

   It returns `{"due": N, "sent": N, …}`. In production, the **Carts** tab shows
   each cart move `Waiting → Mailed → Recovered`.

Notes worth keeping in mind:

- **The recovery discount never leaks and never stacks.** It is not a code in
  `data.py` (those ship to every browser in `data.js`) — it is a per-cart,
  single-use, server-resolved token. It **replaces** the sitewide sale rather
  than adding to it, so a recovered buyer gets 30%, never 45%.
- **The 30% is off the list price**, so someone who saw $88 (already 15% off)
  pays $73. The email states both figures honestly ("You saw $88 — now $73").
- **This store holds PII** (the email, the country), like the sign-up and orders
  stores — same treatment applies: a lawful basis, a privacy-policy line, a
  deletion path. The captured address is only ever used to recover *that* order;
  the checkout note under the email field says so, and every recovery mail
  carries a one-click unsubscribe.
- **A signed-in capture uses the verified session email**, never an address the
  browser names — so no one can write a cart against someone else's inbox. An
  anonymous configuration with no email stores nothing.
- **Clear seeded carts before launch**, the same as every other store — `/ops`
  banners any it finds.

---

## Turn on the mystery discount (the configurator's email capture)

Eight seconds after a visitor settles their **target rank** on a game page, a modal
offers a sealed "mystery discount". An email buys the right to open it; the reveal
shows a 30% code, live for one hour and single-use, and applying it returns them to
their order with the total already discounted. Every card opened, and how many were
paid for, is in the **Mystery** tab of `/ops`.

**Every card pays the same 30%.** The pick is theatre, and the copy is written so it
never claims otherwise — no odds, no luck, no deck of mixed values. Do not add any.
Two friends comparing cards find out in ten seconds, and a discovered lie on a store
whose central pitch is "the price does not move after checkout" costs more than the
twenty margin points earn.

It needs the Upstash store (same credentials as analytics) and, to actually deliver
the code, **email** ([Turn on email](#turn-on-email-hostinger-smtp)). It works
without SMTP — the code is still issued and the reveal drops its "a copy is in your
inbox" line for one that says to copy the code before closing the tab — but that is
a degraded mode, not the design.

1. Nothing is **required** in **Vercel → Project → Settings → Environment
   Variables**; every knob has a default:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `BINGO_PCT` | `0.30` | The discount, as a fraction. **This is a flat cost on every redeemed code — model it as 30%, not as an average.** |
   | `BINGO_TTL` | `3600` | How long a code works, in seconds. One hour. Change it and the modal's own copy follows (the band, the pill and the countdown all read this). |
   | `BINGO_MAX` | `20000` | Caps the stored list. |
   | `BINGO_FOLLOWUP_ENABLED` | *unset* | **The follow-up mailer is OFF until this is `1`.** It rides the cart cron, which already runs every five minutes — so without this gate the deploy that carries it starts mailing real addresses within minutes, unattended. Set it when somebody is awake to watch the first run. |
   | `BINGO_WARN_DELAY` | `1800` | Seconds after the code is issued before the **halfway warning** goes out. It adds no discount — it only says the hour is running out. |
   | `BINGO_FOLLOWUP_PCT` | `0.35` | The **second** offer, on a card that lapsed unbought. Another flat cost — model a chased row at 35%, not 30%. |
   | `BINGO_FOLLOWUP_DELAY` | `1800` | Seconds after the hour lapses before the follow-up goes out. |
   | `BINGO_FOLLOWUP_TTL` | `86400` | How long the revived code works. 24 hours. |
   | `BINGO_FOLLOWUP_MAX_AGE` | `259200` | Past this age a lapsed card is left alone entirely. 3 days. |
   | `ESB_PLAY_HOURS_PER_DAY` | `8` | Hours of play behind one ETA day. The follow-up divides the total by it to quote a per-hour figure — **set it at or below what the roster really does**, or the claim stops being true. |
   | `ESB_PER_HOUR_MAX` | `6` | Above this the per-hour block is dropped from the mail rather than printed. |

   The follow-up rides on the **same cron and the same secret** as the
   abandoned-cart sweep — `/api/sweep` runs both. If `CART_SWEEP_SECRET` is
   unset, neither mail is ever sent.

2. **Check it.** Locally, open a game page, change the target rank and wait five
   seconds. Or hit the API directly:

   ```
   curl -X POST localhost:4321/api/bingo -H 'Content-Type: application/json' \
     -d '{"email":"you@example.com","game":"League of Legends","service":"division",
          "from":"Gold IV","to":"Platinum IV","mode":"Solo","addons":[]}'
   ```

   It returns `{"ok": true, "token": "BINGO-…", "pct": 0.3, "seconds": 3600,
   "mailed": true|false}`. `curl 'localhost:4321/api/bingo?token=BINGO-…'` resolves
   it; a spent or expired one answers `{"valid": false}`.

Notes worth keeping in mind:

- **The code never leaks and never stacks.** It is not an entry in `data.py` (those
  ship to every browser in `data.js`) — it is a per-buyer, single-use,
  server-resolved token, and the browser only ever sends the token back. It
  **replaces** the sitewide sale rather than adding to it, so a buyer gets 30%,
  never 45%.
- **One card per inbox, ever.** A second capture from the same address returns the
  same token while it is live and says "already used its card" once it isn't —
  clearing localStorage does not mint a second 30%.
- **One hour is a real deadline.** The store enforces it, not the countdown: every
  page load re-checks the token, and an expired one simply re-prices at the normal
  sale. An offer that quietly still works teaches buyers to ignore every future
  countdown, which costs more than one late order.
- **It fires once per visitor and a decline is free.** No exit-intent second
  attempt, no re-fire on the next page, and it never opens over an order that
  already carries a discount (a typed code, a bundle, a recovery link).
- **This store holds PII** (the email, the country) next to a live discount, so it
  is the most sensitive of the six — same treatment as carts and orders: a lawful
  basis, a privacy-policy line, a deletion path.
- **Three mails, one of each, ever.** The code (30%, 1 hour); a **warning 30 minutes
  in** that adds no offer and just says the clock is running out; and, only if the card
  lapses unbought, the chase below. The warning fires *inside* the hour and the chase
  only *after* it, so they can never both pick up the same card — a test walks a card's
  whole life and asserts it. Preview all three without waiting an hour:
  `python3 site/tools/send_test_mail.py you@example.com --sequence` (it uses a throwaway
  store, so no real row is touched and no live token is spent).
- **Every mail quotes the order as it stands, not as it was when they gave us the
  address.** The browser beacons the live configuration back to the card while they keep
  building, so extending the climb or ticking Priority moves what the mails say and what
  the checkout link restores. It can only change *which order* the token quotes — never
  the deadline, the rate or the address.
- **The chase.** 30 minutes after
  the hour dies, `followup.py` raises the *same* token to 35% for 24 hours and mails
  it once — with the order's price per hour of play, what the free screen share is
  worth on it, and a link straight to `/checkout?bingo=…` that carries the
  configuration so the page prices the order the mail quoted. `revive()` flips the
  row's stage before the send, so a sweep every five minutes cannot mail twice. A
  paid card is never chased; an unsubscribe stops the mail and **keeps** the code.
- **The per-hour figure is a claim, and it is dropped when it is not a good one.**
  A long climb prices above `ESB_PER_HOUR_MAX` even at 35%, and the mail then makes
  no per-hour argument at all rather than a bad one. `ESB_PLAY_HOURS_PER_DAY` is an
  **ops commitment, not a measurement** — confirm 8 with ops the way `SAFETY`'s
  measure notes need confirming.
- **The marketing opt-in is separate from the code.** The code mail is
  transactional and goes either way; the ticked box writes to the same guides
  mailing list `/guides.html` does. Bundling consent into the transactional mail is
  what gets a sender blacklisted.
- ⚠ **Margin.** At today's prices a 30% code on a typical League climb is roughly
  $18–$150 off a single order. Decide what conversion lift makes that worth it
  before pointing real traffic at it, and read the **Mystery** tab's
  `Redeemed × 30%` rather than the lead count.

---

## Turn on social sign-in (Google + Discord)

The header's "Continue with Google / Discord" buttons run a real OAuth
authorization-code flow (`site/src/oauth.py`). Until you register an app for a
provider and set its two keys, that provider's button stays a facade — it shows
"Social sign-in isn't connected yet" instead of a dead redirect. So you can turn
on one, both, or neither. **No card or game credentials are involved**; the flow
only reads the person's name and verified email and mints a session.

1. **Register a Google app.** Google Cloud Console → **APIs & Services →
   Credentials → Create credentials → OAuth client ID → Web application**. Under
   **Authorized redirect URIs** add, exactly:
   - `https://esportsboost.com/api/auth/google/callback` (production)
   - `http://localhost:4321/api/auth/google/callback` (local dev, optional)

   Copy the **Client ID** and **Client secret**. (You'll also fill in the OAuth
   consent screen — user type *External*, scopes `email` + `profile`.)

2. **Register a Discord app.** Discord Developer Portal → **New Application →
   OAuth2**. Under **Redirects** add:
   - `https://esportsboost.com/api/auth/discord/callback`
   - `http://localhost:4321/api/auth/discord/callback` (optional)

   Copy the **Client ID** and **Client Secret**. Scopes used are `identify` +
   `email` — no bot, no server permissions.

3. In **Vercel → Project → Settings → Environment Variables**, add the pairs for
   whichever providers you registered, plus one shared signing key:

   | Name | Value | Notes |
   | --- | --- | --- |
   | `GOOGLE_CLIENT_ID` | `…apps.googleusercontent.com` | Enables the Google button. |
   | `GOOGLE_CLIENT_SECRET` | the client secret | Never committed; server-side only. |
   | `DISCORD_CLIENT_ID` | the application ID | Enables the Discord button. |
   | `DISCORD_CLIENT_SECRET` | the client secret | Never committed; server-side only. |
   | `SESSION_SECRET` | a long random string (≥ 16 chars) | **Required for sessions to persist.** Signs the session + CSRF-state cookies. Without it, logins work but every server restart/redeploy signs everyone out. Use a password manager. |
   | `PUBLIC_BASE_URL` | `https://esportsboost.com` | The redirect-URI origin. Shared with Stripe. If unset it's inferred from the request host — set it so the callback URL matches what you registered above. |

   **Redeploy** after adding.

4. **Check it.** On the live site, open the header's Log in panel and click
   **Continue with Google**. You should land on Google's consent screen, then
   return signed in — the header shows your account chip. The verified email
   appears in the `/ops` **Accounts** tab tagged `oauth:google`.

Notes worth keeping in mind:

- **The client secret never reaches the browser.** The code exchange happens
  server-side (`/api/auth/<provider>/callback`); the browser only ever carries a
  signed, `HttpOnly` session cookie it cannot read. `/api/auth/me` is what the
  page reads to know who is signed in.
- **The redirect URI must match byte-for-byte** what you registered, or the
  provider refuses the callback. That's driven by `PUBLIC_BASE_URL` — if the
  callback fails with a redirect-URI-mismatch, that variable and the registered
  URI disagree.
- **OAuth accounts and email/password accounts are separate rows by email** in
  this build. Someone who signed up with a password and later uses "Continue with
  Google" on the same address is a known unlinked edge — account linking is
  listed as follow-up in `build.py`'s `AUTH_PLACEHOLDER`, alongside replacing the
  simplified brand marks with each provider's licensed sign-in button.

---

## Custom domain (esportsboost.com)

Vercel dashboard → **Project → Settings → Domains → Add** `esportsboost.com`.
Vercel shows the DNS records to set at your registrar (an `A` record to Vercel's
IP, or a `CNAME` for `www`). TLS is issued automatically. Once it resolves, set
`PUBLIC_BASE_URL=https://esportsboost.com` and update the Stripe webhook URL to
match, then redeploy.

---

## Known limitation on serverless — order persistence

The webhook currently appends fulfilled orders to `orders.log`. On Vercel the
filesystem is **read-only apart from `/tmp`, which is ephemeral**, so that file
write is best-effort. The durable signal on Vercel is the **stderr log line**
(`paid order → …`), visible in the function logs.

For real fulfilment you'll want to replace that seam in
`site/src/payments.py → process_webhook` with a database or a queue (e.g. Vercel
Postgres/KV, Supabase). The **email half of that is now built** — a paid order
mails the buyer and copies the support inbox (see "Turn on email" above) — so
even before a queue exists, no order can clear without someone being told.

---

## Local dev is unchanged

```bash
python3 site/build.py
STRIPE_SECRET_KEY=sk_test_… python3 site/serve.py 4321
```

`serve.py` and the Vercel functions share `site/src/payments.py`, so what you
test locally is what runs in production.
