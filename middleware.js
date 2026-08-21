/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — Vercel Edge Middleware: hand the browser its country
   ---------------------------------------------------------------------------
   The ONE JavaScript file in this project that is not a browser asset, and the
   only thing here that does not run on Python. It exists because of a gap
   nothing else can close:

     · Every page is STATIC and CDN-cached, so the HTML cannot carry a
       per-visitor value.
     · `x-vercel-ip-country` is the country Vercel resolves at the edge from the
       request IP. It is geo.py's first and best signal — the one the /ops
       dashboard already reports — and the only one that follows the CONNECTION
       rather than the device, so it is the one a VPN, a roaming SIM or a
       traveller's laptop gets right.
     · A browser cannot read that header on a document response.

   So this copies it into a plain cookie, which i18n.js reads synchronously at
   parse time — before ESB_LOCALE is published, with no request and no flash of
   the wrong currency. Without it the client falls back to the browser timezone
   and behaves exactly as it did before; see `cookieCountry()` there.

   Load-bearing:

   · It MUST continue the request. `x-middleware-next: 1` is what tells Vercel
     to carry on to the static asset or function that would otherwise have
     served this URL — it is what `next()` from @vercel/edge compiles to, spelled
     out here because this project ships no package.json and installs nothing.
     Get this wrong and every URL on the site returns an empty 200.
   · It MUST NOT throw. This runs in front of every document request, so an
     exception here is the whole site down. Everything is inside a try, and the
     catch still returns the continue-header — a missing cookie costs a European
     visitor a currency default, an exception costs everybody the page.
   · The cookie is NOT HttpOnly, deliberately: i18n.js has to read it. It holds a
     two-letter country code and nothing else — no id, no IP, nothing that
     identifies a person — which is what keeps it a functional preference cookie
     of the same kind as a language cookie, and keeps the analytics store's
     anonymous-by-construction promise intact.
   ───────────────────────────────────────────────────────────────────────── */

export const config = {
  /* Documents only. `/api/*` reads the header directly through geo.py and needs
     no cookie; assets are bytes on a CDN and a Set-Cookie on them is waste. */
  matcher: ['/((?!api/|assets/|_vercel/|favicon|robots\\.txt|sitemap\\.xml).*)'],
};

export default function middleware(request) {
  const headers = { 'x-middleware-next': '1' };
  try {
    const cc = (request.headers.get('x-vercel-ip-country') || '').trim().toUpperCase();
    /* Validated, not trusted: this value is echoed into a Set-Cookie, and a
       header carrying a stray `;` would otherwise let an upstream write cookie
       attributes of its own choosing. Two ASCII letters or nothing. */
    if (/^[A-Z]{2}$/.test(cc)) {
      headers['set-cookie'] =
        `esb_geo=${cc}; Path=/; Max-Age=86400; SameSite=Lax; Secure`;
    }
  } catch (e) {
    /* fall through — the page still serves, the client still has the timezone */
  }
  return new Response(null, { headers });
}
