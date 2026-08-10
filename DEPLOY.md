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
| `api/*.py` | The three serverless functions |
| `site/src/payments.py` | Shared Stripe + pricing logic |

You do **not** need to run the build yourself — Vercel runs it on every deploy.

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
   | `STRIPE_WEBHOOK_SECRET` | `whsec_…` | From step 3 below. Enables webhook signature checks. |
   | `PUBLIC_BASE_URL` | `https://esportsboost.com` | Optional. If unset, the origin is inferred from the request — fine for `*.vercel.app`. Set it once you have the custom domain so Stripe redirects land on it. |

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

4. **Test the full flow** with Stripe's test card `4242 4242 4242 4242`, any
   future expiry, any CVC. You should land on `/checkout/success` with a receipt,
   and see a `paid order → ESB-…` line in the function logs (Vercel → Project →
   Logs).

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
Postgres/KV, Supabase, or an email to the ops inbox). That's the natural next
step after this first deploy — the code is already isolated to one function so
it's a contained change.

---

## Local dev is unchanged

```bash
python3 site/build.py
STRIPE_SECRET_KEY=sk_test_… python3 site/serve.py 4321
```

`serve.py` and the Vercel functions share `site/src/payments.py`, so what you
test locally is what runs in production.
