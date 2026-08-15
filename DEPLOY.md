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
