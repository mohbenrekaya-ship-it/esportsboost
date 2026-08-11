#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static build for the esportsboost redesign — v2 "Ashfall".

    python3 site/build.py       →  site/dist/

No dependencies. Every page is generated from src/data.py; every image from
src/art.py. The homepage is the v2 immersive design; the rest of the site
carries the same system.
"""
import json
import os
import shutil
import sys
from html import escape as esc

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import art  # noqa: E402
import data as D  # noqa: E402
import pricing  # noqa: E402

DIST = os.path.join(HERE, "dist")
PUBLIC = os.path.join(HERE, "public")

BY_SLUG = {g["slug"]: g for g in D.GAMES}
BY_NAME = {g["name"]: g for g in D.GAMES}
BOOSTER = {b["handle"]: b for b in D.BOOSTERS}


# ══════════════════════════════════════════════════════════════════════════
#  pricing — mirrors assets/js/app.js exactly
# ══════════════════════════════════════════════════════════════════════════
def usd(n, cents=False):
    return ("${:,.2f}" if cents else "${:,.0f}").format(n)


def money(n, cents=False):
    """A static USD price wrapped so i18n.js can re-format it into the active
    currency client-side. The `data-usd` value is the raw USD amount."""
    raw = ("%.2f" % n) if cents else ("%d" % round(n))
    return '<span class="money" data-usd="%s">%s</span>' % (raw, usd(n, cents))


def quote(game, frm, to, mode="Solo"):
    """Static-card division quote. Delegates to the authoritative formula in
    pricing.quote() so build-time and runtime prices can never drift."""
    q = pricing.quote({"game": game, "service": "division", "from": frm,
                       "to": to, "mode": mode, "addons": []})
    if q["invalid"]:
        return dict(price="—", eta="—", total=0, summary=q["summary"])
    return dict(price=usd(q["total"]), total=q["total"], eta=q["eta"], summary=q["summary"])


def from_price(g):
    """`FROM $NN` — a one-division climb off the second tier."""
    return quote(g["name"], g["ladder"][1], g["ladder"][2])["total"]


# ══════════════════════════════════════════════════════════════════════════
#  shell
# ══════════════════════════════════════════════════════════════════════════
NAV = [
    ("/games/", "Games"),
    ("/#live", "Live"),
    ("/boosters.html", "Boosters"),
    ("/guarantee.html", "Safety"),
    ("/reviews.html", "Reviews"),
]

FOOT = [
    ("/legal/terms.html", "Terms"),
    ("/legal/refunds.html", "Refunds"),
    ("/legal/privacy.html", "Privacy"),
    ("/become-a-booster.html", "Become a booster"),
    ("/support.html#discord", "Discord"),
]


# Custom flag/symbol dropdowns for currency + language. Wired by i18n.js; the
# labels are display-only (the picked value drives the client-side switch).
_CHEV = ('<svg class="loc-chev" width="9" height="9" viewBox="0 0 10 10" aria-hidden="true">'
         '<path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" stroke-width="1.5" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')

CURRENCIES = [("USD", "$", "USD"), ("EUR", "€", "EUR")]
LANGUAGES = [("EN", "🇬🇧", "EN"), ("FR", "🇫🇷", "FR"), ("DE", "🇩🇪", "DE")]


def _loc_dropdown(kind, label, options):
    opts = "".join(
        '<li class="loc-opt" role="option" data-value="%s" tabindex="-1">'
        '<span class="loc-flag">%s</span><span class="loc-code">%s</span></li>'
        % (val, icon, esc(code)) for val, icon, code in options
    )
    first = options[0]
    return f"""<div class="loc" data-loc="{kind}">
        <button type="button" class="loc-btn" aria-haspopup="listbox" aria-expanded="false" aria-label="{esc(label)}">
          <span class="loc-flag" data-loc-icon>{first[1]}</span><span class="loc-code" data-loc-label>{esc(first[2])}</span>{_CHEV}
        </button>
        <ul class="loc-menu" role="listbox" aria-label="{esc(label)}">{opts}</ul>
      </div>"""


def locale_switcher():
    return f"""<div class="locale">
        {_loc_dropdown("currency", "Currency", CURRENCIES)}
        {_loc_dropdown("language", "Language", LANGUAGES)}
      </div>"""


def promo_slot():
    """Left cell of the utility bar — the editable site-wide promo (D.PROMO).
    Empty text renders an empty span so the bar keeps its space-between layout."""
    p = getattr(D, "PROMO", None) or {}
    text = (p.get("text") or "").strip()
    if not text:
        return '<span class="promo" aria-hidden="true"></span>'
    tag = (p.get("tag") or "").strip()
    chip = '<span class="promo-tag">%s</span>' % esc(tag) if tag else ""
    inner = '%s<span class="promo-text">%s</span>' % (chip, esc(text))
    href = (p.get("href") or "").strip()
    if href:
        return '<a class="promo" href="%s">%s</a>' % (esc(href), inner)
    return '<span class="promo">%s</span>' % inner


def chrome(current):
    links = "".join(
        '<a href="%s"%s>%s</a>' % (href, ' aria-current="page"' if current == href else "", esc(label))
        for href, label in NAV
    )
    # Rotating live-status ticker; last item repeats the first for a seamless loop.
    live_items = [
        "%s verified boosters on shift right now" % D.STATS["online"],
        "Most orders claimed within %s" % esc(D.STATS["median_claim"]),
        "%s boosters free and ready to start now" % D.STATS["free_now"],
        "Join %s players in our Discord community" % esc(D.STATS["discord"]),
    ]
    live_track = "".join('<span class="live-item">%s</span>' % m
                         for m in live_items + live_items[:1])
    live_sr = " · ".join(live_items)
    return f"""<div class="util-outer">
  <div class="wrap">
    <div class="util">
      {promo_slot()}
      <span class="live">
        <span class="live-dot" aria-hidden="true"></span>
        <span class="live-rot" aria-hidden="true"><span class="live-track">{live_track}</span></span>
        <span class="sr-only">{live_sr}</span>
      </span>
      {locale_switcher()}
    </div>
  </div>
</div>
<header class="nav-outer">
  <div class="wrap">
    <nav class="nav" aria-label="Main">
      <a class="nav-brand" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
      <button class="btn btn-secondary btn-sm nav-toggle" data-nav-toggle aria-expanded="false" aria-controls="nav-links">Menu</button>
      <div class="nav-links" id="nav-links">
        {links}
        <span class="nav-sep" aria-hidden="true"></span>
        <a href="/track.html">Track my order</a>
        <a class="btn btn-primary btn-sm" href="/games/">Start an order</a>
        <div class="nav-locale" aria-hidden="false">
          <span class="nav-locale-label">Currency &amp; language</span>
          {locale_switcher()}
        </div>
      </div>
    </nav>
  </div>
</header>"""


# Off-brand external review destination, supplied for the Trustpilot badge.
TRUSTPILOT_URL = "https://www.trustpilot.com/review/lolepicshop.com"

_tp_id = [0]


def _tp_stars_svg(fill, cid):
    """5 Trustpilot tiles; green up to `fill` (0–1) of the width, grey after."""
    W, GAP, N = 24, 6, 5
    total = N * W + (N - 1) * GAP
    star = ("M12 3.6l2.34 5.1 5.56.52-4.2 3.72 1.24 5.46L12 15.6"
            "l-4.94 2.8 1.24-5.46-4.2-3.72 5.56-.52z")

    def row(color):
        out = ""
        for i in range(N):
            x = i * (W + GAP)
            out += ('<rect x="%d" y="0" width="%d" height="%d" rx="2" fill="%s"/>'
                    '<path d="%s" transform="translate(%d,0)" fill="#ffffff"/>'
                    % (x, W, W, color, star, x))
        return out

    clip = round(total * max(0.0, min(1.0, fill)))
    return (f'<svg class="tp-svg" viewBox="0 0 {total} {W}" width="{total}" height="{W}" '
            f'role="img" aria-hidden="true" focusable="false">'
            f'<g>{row("#dcdce6")}</g>'
            f'<clipPath id="{cid}"><rect x="0" y="0" width="{clip}" height="{W}"/></clipPath>'
            f'<g clip-path="url(#{cid})">{row("#00b67a")}</g>'
            f'</svg>')


def trustpilot_badge(label="Excellent"):
    """Clickable Trustpilot rating badge linking to the external review page."""
    rating = D.STATS["trustpilot"].split("/")[0].strip()
    try:
        fill = float(rating) / 5.0
    except ValueError:
        fill = 1.0
    _tp_id[0] += 1
    stars = _tp_stars_svg(fill, "tpclip%d" % _tp_id[0])
    aria = ("%s rating on Trustpilot from %s reviews — read reviews on Trustpilot"
            % (D.STATS["trustpilot"], D.STATS["reviews"]))
    logo = ('<span class="tp-brand"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            '<path d="M12 2l2.6 6.8H22l-6 4.5 2.3 7L12 15.9 5.7 20.3 8 13.3 2 8.8h7.4z" '
            'fill="#00b67a"/></svg>Trustpilot</span>')
    return (f'<a class="tp-badge" href="{TRUSTPILOT_URL}" target="_blank" '
            f'rel="noopener nofollow" aria-label="{esc(aria)}">'
            f'{logo}{stars}'
            f'<span class="tp-meta"><span class="tp-word">{esc(label)}</span> '
            f'<b>{esc(D.STATS["trustpilot"])}</b> · {esc(D.STATS["reviews"])} reviews</span>'
            f'</a>')


_star_id = [0]


def star_row(fill, size=22, gap=7):
    """A 5-star row, ember-filled up to `fill` (0–1) over a faint base — the
    on-brand counterpart to the green Trustpilot tiles."""
    N, W = 5, size
    total = N * W + (N - 1) * gap
    path = ("M12 2l2.9 6.25 6.85.55-5.2 4.5 1.6 6.7L12 16.7 5.86 20.5l1.6-6.7"
            "L2.25 9.3l6.85-.55z")

    def stars(color):
        s = W / 24.0
        return "".join('<path d="%s" transform="translate(%d,0) scale(%.4f)" fill="%s"/>'
                       % (path, i * (W + gap), s, color) for i in range(N))

    _star_id[0] += 1
    cid, gid = "starclip%d" % _star_id[0], "startgrad%d" % _star_id[0]
    clip = round(total * max(0.0, min(1.0, fill)))
    return (f'<svg class="star-row" viewBox="0 0 {total} {W}" width="{total}" height="{W}" '
            f'role="img" aria-hidden="true" focusable="false">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0" stop-color="#ffb046"/><stop offset="1" stop-color="#ff3d0f"/>'
            f'</linearGradient></defs>'
            f'{stars("rgba(255,255,255,.14)")}'
            f'<clipPath id="{cid}"><rect x="0" y="0" width="{clip}" height="{W}"/></clipPath>'
            f'<g clip-path="url(#{cid})">{stars(f"url(#{gid})")}</g></svg>')


# Footer link columns. Games follow the site-wide order (first six); Legal is
# hand-curated. Re-rank in data.py's _ORDER, not here.
FOOT_GAMES = [g["name"] for g in D.GAMES[:6]]
FOOT_LEGAL = [
    ("/legal/privacy.html", "Privacy Policy"),
    ("/legal/terms.html", "Terms of Service"),
    ("/legal/refunds.html", "Refunds & Cancellations"),
]
FOOT_EMAIL = "info@esportsboost.com"
FOOT_DISCLAIMER = (
    "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any "
    "of their subsidiaries. All trademarks, game titles, logos, and brand names are the "
    "property of their respective owners. eSports Boost provides independent gaming "
    "services and is not endorsed by or associated with any game publisher."
)

# Inline single-path social glyphs, drawn on brand hairlines.
_SOCIAL = {
    "Facebook": ("https://facebook.com/", '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false"><path fill="currentColor" d="M14 8.5V6.8c0-.8.2-1.3 1.4-1.3H17V2.6c-.3 0-1.3-.1-2.4-.1-2.4 0-4 1.5-4 4.2v1.8H8v3.1h2.6V22H14v-8.4h2.5l.4-3.1H14z"/></svg>'),
    "Instagram": ("https://instagram.com/", '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="1.8" d="M7.5 3.5h9A4 4 0 0 1 20.5 7.5v9a4 4 0 0 1-4 4h-9a4 4 0 0 1-4-4v-9a4 4 0 0 1 4-4Z"/><circle cx="12" cy="12" r="3.6" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.2" cy="6.8" r="1.1" fill="currentColor"/></svg>'),
    "TikTok": ("https://tiktok.com/", '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false"><path fill="currentColor" d="M16.5 2h-3v13.2a2.7 2.7 0 1 1-2.1-2.6V9.5a5.9 5.9 0 1 0 5.1 5.8V8.9a6.7 6.7 0 0 0 3.9 1.2V7a3.9 3.9 0 0 1-3.9-3.9V2Z"/></svg>'),
    "Discord": ("/support.html#discord", '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false"><path fill="currentColor" d="M19.3 5.4A16 16 0 0 0 15.4 4l-.2.4a12 12 0 0 1 3.4 1.6 11 11 0 0 0-9.4 0A12 12 0 0 1 12.6 4l-.3-.4A16 16 0 0 0 8.5 5.4 17 17 0 0 0 5.5 17a16 16 0 0 0 4.7 2.4l.5-.9a10 10 0 0 1-1.7-.8l.4-.3a11 11 0 0 0 9 0l.4.3a10 10 0 0 1-1.7.8l.5.9a16 16 0 0 0 4.7-2.4 17 17 0 0 0-3-11.6ZM10 14.4a1.5 1.5 0 0 1 0-3 1.5 1.5 0 0 1 0 3Zm4.8 0a1.5 1.5 0 0 1 0-3 1.5 1.5 0 0 1 0 3Z"/></svg>'),
}


def footer():
    games = "".join(
        '<li><a href="/games/%s.html">%s</a></li>' % (BY_NAME[n]["slug"], esc(n))
        for n in FOOT_GAMES if n in BY_NAME
    )
    legal = "".join('<li><a href="%s">%s</a></li>' % (h, esc(l)) for h, l in FOOT_LEGAL)
    social = "".join(
        '<a class="foot-social" href="%s" aria-label="%s"%s>%s</a>'
        % (href, esc(name), ' target="_blank" rel="noopener noreferrer"'
           if href.startswith("http") else "", svg)
        for name, (href, svg) in _SOCIAL.items()
    )
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="foot-grid">
      <div class="foot-brand">
        <a class="nav-brand foot-mark" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
        <p class="foot-disclaimer">{esc(FOOT_DISCLAIMER)}</p>
        <p class="foot-email-label">Questions? Email us at</p>
        <a class="foot-email" href="mailto:{FOOT_EMAIL}">{FOOT_EMAIL}</a>
        <div class="foot-socials">{social}</div>
      </div>
      <nav class="foot-col" aria-label="Games">
        <h2 class="foot-head">Games</h2>
        <ul class="foot-list">{games}</ul>
      </nav>
      <nav class="foot-col" aria-label="Legal">
        <h2 class="foot-head">Legal</h2>
        <ul class="foot-list">{legal}</ul>
      </nav>
      <div class="foot-support">
        <h2 class="foot-head foot-head-accent">24/7 Customer Support</h2>
        <p class="foot-support-copy">Need help? Our support team is available anytime to assist you with your orders and questions.</p>
        <a class="btn btn-primary foot-support-btn" href="/support.html#discord">Let's Chat</a>
        <a class="btn btn-secondary foot-support-btn" href="/support.html">Visit Help Center</a>
      </div>
    </div>
    <div class="foot-bottom">© {D.YEAR} {esc(D.BRAND)}. All Rights Reserved.</div>
  </div>
</footer>"""


def layout(path, title, desc, body, current=None, jsonld=None, og_image=None,
           mobile_bar=False, extra_js=""):
    ld = ""
    for block in (jsonld or []):
        ld += '<script type="application/ld+json">%s</script>\n' % json.dumps(block, ensure_ascii=False)
    bar = ""
    if mobile_bar:
        bar = """<div class="mobile-bar" role="region" aria-label="Live quote">
  <div>
    <div class="p" data-out="price">—</div>
    <div class="s" data-out="summary">—</div>
  </div>
  <a class="btn btn-primary btn-sm" href="/checkout.html" data-continue>Continue</a>
</div>"""
    og_image = og_image or img("/assets/img/og-default.svg")
    canonical = D.SITE + path
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(D.BRAND)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{D.SITE}{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#06060a">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="/assets/css/ashfall.css">
<link rel="stylesheet" href="/assets/css/site.css">
<link rel="stylesheet" href="/assets/css/type-b-sans.css">
{ld}</head>
<body>
<a class="btn btn-secondary btn-sm" href="#main" style="position:absolute;left:-9999px" onfocus="this.style.left='12px';this.style.top='12px';this.style.zIndex='99'" onblur="this.style.left='-9999px'">Skip to content</a>
{chrome(current)}
<main id="main">
{body}
</main>
{footer()}
{bar}
<script src="/assets/js/data.js"></script>
<script src="/assets/js/i18n.js"></script>
<script src="/assets/js/app.js"></script>
{extra_js}</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════
#  blocks
# ══════════════════════════════════════════════════════════════════════════
FX = """<div class="fx fx-glow" aria-hidden="true"></div>
    <div class="fx fx-grain" aria-hidden="true"></div>
    <div class="fx fx-scan" aria-hidden="true"></div>
    <div class="fx fx-scrim" aria-hidden="true"></div>"""


def rule():
    return '<div class="wrap"><hr class="rule"></div>'


def sec_head(num, label, heading, note=None, right=None):
    aside = ""
    if note:
        aside = '<p class="sec-note">%s</p>' % esc(note)
    elif right:
        aside = '<span class="kicker kicker-dim">%s</span>' % esc(right)
    return f"""<div class="sec-head">
    <div class="sec-head-copy">
      <span class="sec-kicker"><span class="sec-kicker-n">{num}</span><span class="sec-kicker-l">{esc(label)}</span></span>
      <h2 class="h-sec">{heading}</h2>
    </div>
    {aside}
  </div>"""


def cta_band(live=False, title=None, sub=None, cta=("Start an order", "/games/")):
    if live:
        kicker = '<span class="kicker" data-out="summaryUpper">—</span>'
        head = '<h2 class="h-md">Your climb starts at <span data-out="price">—</span></h2>'
        sub = sub or "Final at checkout. Refunded in full until a booster claims it, pro-rated after that."
        dc = " data-continue"
    else:
        kicker = '<span class="kicker">Ready when you are</span>'
        head = '<h2 class="h-md">%s</h2>' % esc(title or "Know your price before you sign up.")
        sub = sub or "The calculator is on every page. No account needed to see it."
        dc = ""
    return f"""<section class="band">
  <img class="band-art" src="{img("/assets/img/closing.svg")}" alt="" width="1600" height="460" loading="lazy">
  <div class="fx fx-glow" aria-hidden="true"></div>
  <div class="fx fx-scrim" aria-hidden="true"></div>
  <div class="band-inner">
    <div class="wrap">
      {kicker}
      {head}
      <p style="font-size:15px;color:var(--text-3);max-width:54ch;margin:14px 0 0">{esc(sub)}</p>
      <div class="btn-row" style="padding-top:18px">
        <a class="btn btn-primary" href="{cta[1]}"{dc}>{esc(cta[0])}</a>
        <a class="btn btn-secondary" href="/support.html">Talk to support</a>
      </div>
    </div>
  </div>
</section>"""


def marquee():
    run = "".join('<span>%s</span><i aria-hidden="true">◆</i>' % esc(m) for m in D.MARQUEE)
    return f"""<div class="marquee" aria-hidden="true">
  <div class="marquee-track">
    <span class="marquee-run">{run}</span>
    <span class="marquee-run">{run}</span>
  </div>
</div>"""


def statband():
    stats = [
        (D.STATS["boosts"], "Boosts delivered"),
        (D.STATS["trustpilot"], "Trustpilot · %s reviews" % D.STATS["reviews"]),
        (D.STATS["median_claim"], "Median time to claim"),
        (D.STATS["discord"], "Players in the Discord"),
    ]
    cells = "".join('<div><div class="v">%s</div><div class="l">%s</div></div>' % (esc(v), esc(l))
                    for v, l in stats)
    return '<section class="statband"><div class="wrap">%s</div></section>' % cells


def guarantee_cards():
    cards = "".join(f"""<div class="card">
      <span class="card-kicker">{esc(k)}</span>
      <span class="card-title">{esc(t)}</span>
      <p class="card-body">{esc(b)}</p>
    </div>""" for k, t, b in D.GUARANTEES)
    return '<div class="cards-3">%s</div>' % cards


def steps_block():
    steps = "".join(f"""<div class="step">
      <span class="step-n">{n}</span>
      <div>
        <div class="step-t">{esc(t)}</div>
        <p class="t-14" style="margin:0;color:var(--text-3);line-height:1.7">{esc(b)}</p>
      </div>
    </div>""" for n, t, b in D.STEPS)
    return '<div class="steps">%s</div>' % steps


def mosaic():
    cells = []
    for idx, (slug, span) in enumerate(D.TILE_ORDER):
        g = BY_SLUG[slug]
        cells.append(f"""<a class="tile {span}" href="/games/{slug}.html">
      <img src="{img("/assets/img/keyart-%s.svg" % slug)}" alt="{esc(g['name'])} key art" width="1200" height="700" loading="lazy">
      <span class="tile-scrim" aria-hidden="true"></span>
      <span class="tile-edge" aria-hidden="true"></span>
      <span class="tile-num">0{idx + 1}</span>
      <span class="tile-body">
        <span class="tile-title">{esc(g['name'])}</span>
        <span class="tile-svc">{esc(g['services'])}</span>
        <span class="tile-from">From {money(from_price(g))}</span>
      </span>
    </a>""")
    rest = [g for g in D.GAMES if g["slug"] not in dict(D.TILE_ORDER)]
    cells.append(f"""<div class="tile-more">
      <span class="big">+ {len(rest)}<br>more</span>
      <span class="t-12" style="color:var(--text-5)">{esc(", ".join(g["name"] for g in rest))}</span>
      <a class="btn btn-ghost" href="/games/">All games →</a>
    </div>""")
    return '<div class="mosaic">%s</div>' % "".join(cells)


def game_cards(games=None):
    games = games or D.GAMES
    out = []
    for g in games:
        out.append(f"""<a class="tile gamecard" href="/games/{g['slug']}.html">
      <img src="{img('/assets/img/keyart-%s.svg' % g['slug'])}" alt="{esc(g['name'])} key art" width="1200" height="700" loading="lazy">
      <span class="tile-scrim" aria-hidden="true"></span>
      <span class="tile-edge" aria-hidden="true"></span>
      <span class="tile-body">
        <span class="tile-title">{esc(g['name'])}</span>
        <span class="tile-svc">{esc(g['services'])}</span>
        <span class="tile-from">From {money(from_price(g))}</span>
      </span>
    </a>""")
    return '<div class="gamegrid">%s</div>' % "".join(out)


def game_rows():
    out = []
    for g in D.GAMES:
        out.append(f"""<a class="gamerow" href="/games/{g['slug']}.html">
      <img src="{img('/assets/img/emblem-%s.svg' % g['slug'])}" alt="" width="52" height="52" loading="lazy">
      <span class="name">{esc(g['name'])}</span>
      <span class="t-13 svc" style="color:var(--text-5)">{esc(g['services'])}</span>
      <span class="from">From {money(from_price(g))}</span>
      <span class="btn btn-ghost cfg" style="justify-self:end">Configure →</span>
    </a>""")
    return '<div class="gamerows">%s</div>' % "".join(out)


def live_feed():
    cards = "".join(f"""<div class="feed-card">
      <img src="{img('/assets/img/emblem-%s.svg' % f['slug'])}" alt="" width="78" height="78" loading="lazy">
      <div class="stack" style="gap:4px;min-width:0">
        <span class="feed-climb">{esc(f['climb'])}</span>
        <span class="t-12" style="color:var(--text-5)">{esc(f['game'])}</span>
        <span class="feed-meta">{esc(f['time'])} · {esc(f['booster'])}</span>
      </div>
    </div>""" for f in D.LIVE_FEED)
    return '<div class="feed">%s</div>' % cards


def roster_panel(rows=None):
    rows = rows or D.BOOSTERS[:5]
    body = "".join(f"""<div class="roster-row">
      <img src="{img('/assets/img/avatar-%s.svg' % b['handle'])}" alt="" width="44" height="44" loading="lazy">
      <div class="stack" style="gap:1px;min-width:0">
        <span class="roster-handle">{esc(b['handle'])}</span>
        <span class="roster-peak">{esc(b['peak_full'])}</span>
      </div>
      <div>
        <div class="roster-wr">{esc(b['wr'])}</div>
        <div class="roster-q">{esc(b['queue'])}</div>
      </div>
    </div>""" for b in rows)
    return f"""<aside class="roster" id="boosters">
    <div class="roster-head"><span class="dot-live" aria-hidden="true"></span>On shift now — {D.STATS['online']}</div>
    {body}
    <div class="ember-box" style="padding:16px;display:flex;flex-direction:column;gap:8px;margin-top:8px">
      <span style="font-family:var(--display);font-weight:700;font-size:19px;text-transform:uppercase">{esc(D.STATS['discord'])} in the Discord</span>
      <span class="t-12" style="color:var(--text-4)">Free VOD reviews on Sundays, scrim pickups, and the booster application queue.</span>
      <a class="btn btn-ghost" href="/support.html#discord">Join the server →</a>
    </div>
  </aside>"""


def booster_table(rows, note=True):
    body = "".join(f"""<tr>
        <td class="handle">{esc(b['handle'])}</td>
        <td style="color:var(--text-5)">{esc(b['game'])}</td>
        <td>{esc(b['peak'])}</td>
        <td class="wr">{esc(b['wr'])}</td>
        <td class="mono-cell">{esc(b['queue'])}</td>
      </tr>""" for b in rows)
    foot = ('<p class="t-12" style="margin:12px 0 0;color:var(--text-5)">Every booster is trialled '
            'live before onboarding and reviewed monthly. Ranks shown are verified from match '
            'history, not self-reported.</p>') if note else ""
    return f"""<div class="table-scroll">
    <table class="table">
      <thead><tr><th>Booster</th><th>Game</th><th>Peak</th><th>Win rate</th><th>Queue</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>{foot}"""


def reviews_grid(items):
    cards = "".join(f"""<div class="card">
      <span class="card-kicker">{esc(r['rank'])}</span>
      <p class="card-body">{esc(r['text'])}</p>
      <span class="card-meta">Verified order · {esc(r['game'])}</span>
    </div>""" for r in items)
    return '<div class="cards-3">%s</div>' % cards


def _review_tile(r, i):
    """One review card — ember star row, quote mark, and a staggered
    scroll-reveal (JS arms `[data-reveal]`; degrades to static)."""
    return f"""<figure class="rev-tile" data-reveal style="--rev-i:{i}">
      <div class="rev-tile-head">
        <span class="rev-tile-stars">{star_row(1.0, size=15, gap=5)}</span>
        <span class="rev-tile-flag">Verified</span>
      </div>
      <span class="rev-tile-rank">{esc(r['rank'])}</span>
      <blockquote class="rev-tile-quote">{esc(r['text'])}</blockquote>
      <figcaption class="rev-tile-meta">Verified order · {esc(r['game'])}</figcaption>
    </figure>"""


def _reviews_one_per_game():
    """First review from each distinct game, in data order — so the homepage
    feed reads across the whole roster instead of nine League quotes."""
    seen, out = set(), []
    for r in D.REVIEWS:
        key = r["game"].split("·")[0].strip()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def review_carousel(items):
    """Auto-advancing review carousel — JS (`initCarousel`) sizes the slides,
    paginates and rotates. With JS off it degrades to a horizontal scroller."""
    tiles = "".join(_review_tile(r, i) for i, r in enumerate(items))
    return f"""<div class="rev-carousel" data-carousel>
      <div class="rev-carousel-viewport" data-carousel-viewport>
        <div class="rev-carousel-track" data-carousel-track>{tiles}</div>
      </div>
      <div class="rev-carousel-controls">
        <button class="rev-arrow" type="button" data-carousel-prev aria-label="Previous reviews">&#8249;</button>
        <div class="rev-dots" data-carousel-dots role="tablist" aria-label="Review pages"></div>
        <button class="rev-arrow" type="button" data-carousel-next aria-label="Next reviews">&#8250;</button>
      </div>
    </div>"""


def faq_block(items):
    rows = "".join(f"""<details>
      <summary>{esc(q)}</summary>
      <p>{esc(a)}</p>
    </details>""" for q, a in items)
    return '<div class="faq">%s</div>' % rows


def faq_ld(items):
    return {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items],
    }


def mode_seg(name):
    return f"""<div class="seg seg-full">
        <label class="seg-opt"><input type="radio" name="{name}" value="Solo" data-mode autocomplete="off"> Solo</label>
        <label class="seg-opt"><input type="radio" name="{name}" value="Duo queue" data-mode autocomplete="off"> Duo queue</label>
      </div>"""


def addons_block():
    rows = []
    for a in D.ADDONS:
        price = "Included" if a["pct"] == 0 else "+%d%%" % round(a["pct"] * 100)
        checked = " checked disabled" if a["pct"] == 0 else ""
        rows.append(f"""<label class="opt">
        <input type="checkbox" data-addon="{a['id']}"{checked} autocomplete="off">
        <span><span style="display:block">{esc(a['label'])}</span>
        <span class="note">{esc(a['note'])}</span></span>
        <span class="price">{price}</span>
      </label>""")
    return '<div class="opts">%s</div>' % "".join(rows)


def wizard(game=None):
    """The v1 quote card, restyled for Ashfall and kept for the game pages —
    the docked hero calculator is the homepage's version of the same state."""
    g = BY_NAME[game] if game else D.GAMES[0]
    regions = "".join('<option value="%s">%s</option>' % (esc(r), esc(r)) for r in g["regions"])
    ranks = "".join('<option value="%s">%s</option>' % (esc(r), esc(r)) for r in g["ladder"])
    attr = ' data-game="%s"' % esc(g["name"]) if game else ""
    return f"""<div class="wizard" data-configurator{attr}>
      <div class="wizard-head">
        <span class="calc-kicker">Checkout</span>
        <span class="tag tag-accent">Live</span>
      </div>

      <div class="tabs" role="tablist" aria-label="Service">
        <button class="tab" role="tab" data-service="division" aria-selected="true">Division boost</button>
        <button class="tab" role="tab" data-service="wins" aria-selected="false">Net wins</button>
        <button class="tab" role="tab" data-service="placements" aria-selected="false">Placements</button>
      </div>

      <div data-panel="division">
        <div class="two-up">
          <div class="field">
            <label for="w-from">Current rank</label>
            <select id="w-from" class="input" data-sel="from" autocomplete="off">{ranks}</select>
          </div>
          <div class="field">
            <label for="w-to">Target rank</label>
            <select id="w-to" class="input" data-sel="to" autocomplete="off">{ranks}</select>
          </div>
        </div>
      </div>

      <div data-panel="wins" hidden>
        <div class="two-up">
          <div class="field">
            <label for="w-from-wins">Current rank</label>
            <select id="w-from-wins" class="input" data-sel="from" autocomplete="off">{ranks}</select>
          </div>
          <div class="field">
            <label>How many net wins</label>
            <div class="stepper" data-stepper="wins" data-min="1" data-max="20">
              <button class="btn btn-icon" type="button" data-step="-1" aria-label="One win fewer">–</button>
              <output>5</output>
              <button class="btn btn-icon" type="button" data-step="1" aria-label="One win more">+</button>
            </div>
          </div>
        </div>
      </div>

      <div data-panel="placements" hidden>
        <div class="two-up">
          <div class="field">
            <label for="w-from-pl">Current rank</label>
            <select id="w-from-pl" class="input" data-sel="from" autocomplete="off">{ranks}</select>
          </div>
          <div class="field">
            <label>How many placement games</label>
            <div class="stepper" data-stepper="placements" data-min="1" data-max="10">
              <button class="btn btn-icon" type="button" data-step="-1" aria-label="One game fewer">–</button>
              <output>5</output>
              <button class="btn btn-icon" type="button" data-step="1" aria-label="One game more">+</button>
            </div>
          </div>
        </div>
      </div>

      <div class="two-up">
        <div class="field">
          <label>How it's played</label>
          {mode_seg("w-mode")}
        </div>
        <div class="field">
          <label for="w-region">Server</label>
          <select id="w-region" class="input" data-sel="region" autocomplete="off">{regions}</select>
        </div>
      </div>

      <details>
        <summary class="kicker kicker-dim" style="cursor:pointer">Options</summary>
        <div style="padding-top:12px">{addons_block()}</div>
      </details>

      <div class="wizard-div"></div>

      <div class="quote-row" aria-live="polite">
        <div class="stack" style="gap:4px">
          <span class="fig-lab" data-out="summary">—</span>
          <span class="quote-price" data-out="price">—</span>
        </div>
        <div class="stack" style="gap:4px;text-align:right">
          <span class="fig-lab">Delivered in</span>
          <span class="quote-eta" data-out="eta">—</span>
        </div>
      </div>

      <a class="btn btn-primary btn-block" href="/checkout.html" data-continue>Continue to checkout</a>
      <span class="fine">No account needed · Money-back until a booster is assigned · VPN matched to your region</span>
    </div>"""


# ══════════════════════════════════════════════════════════════════════════
#  pages
# ══════════════════════════════════════════════════════════════════════════
def page_home():
    # Homepage selector shows a curated subset of games (order preserved).
    # Rendered as angled "cut box" tiles — see .gsel in site.css; still wired
    # through data-game-tag so app.js drives the aria-pressed selection.
    chip_slugs = {"league-of-legends", "valorant", "teamfight-tactics",
                  "marvel-rivals"}
    chip_games = [g for g in D.GAMES if g["slug"] in chip_slugs]
    chips = "".join(
        '<button class="gsel-box" type="button" data-game-tag="%s"><span class="gsel-in">'
        '<span class="gsel-code">%s</span><span class="gsel-name">%s</span></span></button>'
        % (esc(g["name"]), esc(g["short"]), esc(g["name"])) for g in chip_games)
    H = D.HERO
    safety_p = "".join("<p>%s</p>" % esc(p) for p in D.SAFETY["body"])
    dash = "".join(f"""<div>
        <div class="step-t" style="font-size:16px">{esc(t)}</div>
        <p class="t-14" style="margin:0;color:var(--text-3)">{esc(b)}</p>
      </div>""" for t, b in D.DASHBOARD_POINTS)

    body = f"""<section class="hero" id="top">
  <img class="hero-art" src="{img("/assets/img/hero.svg")}" alt="" width="1600" height="900" fetchpriority="high">
  {FX}
  <div class="fx fx-sparks" aria-hidden="true"><span></span><span></span><span></span><span></span></div>

  <div class="wrap hero-inner">
    <div class="hero-copy">
      <span class="kicker">{esc(H['kicker'])}</span>
      <h1 class="h-lg">{esc(H['line1'])}<br><span class="grad-text">{esc(H['line2'])}</span></h1>
      <p class="lede">{esc(H['lede'])}</p>
      <div class="btn-row">
        <a class="btn btn-primary" href="/games/">Configure your boost</a>
        <a class="btn btn-secondary" href="#live">Watch a live boost</a>
      </div>
    </div>
    <div class="hero-side">
      <div class="portrait">
        <img src="/assets/img/portrait-vantaa.svg" alt="Top booster of the month, vantaa" width="232" height="232">
      </div>
      <div>
        <div class="portrait-name">{esc(H['portrait_name'])}</div>
        <div class="t-12" style="color:var(--text-5)">{esc(H['portrait_meta'])}</div>
      </div>
    </div>
  </div>

  <div class="calc-dock" id="calc">
    <div class="calc" data-configurator>
      <div class="calc-glow" aria-hidden="true"></div>
      <div class="calc-head">
        <div class="calc-head-l">
          <span class="calc-kicker">Fast Checkout</span>
          <span class="calc-tag"><i class="calc-live" aria-hidden="true"></i>Live pricing</span>
        </div>
      </div>
      <div class="gsel" role="group" aria-label="Choose a game">{chips}</div>

      <div class="calc-ladder">
        <div class="calc-route">
          <span class="calc-route-lab">Your climb</span>
          <span class="calc-route-val" data-out="summary">—</span>
        </div>
        <div class="calc-step" data-step-prompt data-step="1" aria-live="polite">
          <span class="calc-step-num" data-step-num>1</span>
          <span class="calc-step-txt" data-step-txt>Tap the rank you’re on now</span>
        </div>
        <div class="ladder-scroll">
          <div class="ladder" data-ladder role="group" aria-label="Rank tier"></div>
        </div>
        <div class="calc-subs">
          <div class="calc-sub">
            <span class="calc-sub-lab">Current division</span>
            <div class="seg seg-sub" data-subseg="from" role="group" aria-label="Current division"></div>
          </div>
          <div class="calc-sub">
            <span class="calc-sub-lab">Target division</span>
            <div class="seg seg-sub" data-subseg="to" role="group" aria-label="Target division"></div>
          </div>
        </div>
      </div>

      <div class="calc-foot">
        <div class="calc-foot-l">
          <div class="seg" role="group" aria-label="How it's played">
            <label class="seg-opt"><input type="radio" name="c-mode" value="Solo" data-mode autocomplete="off">Solo</label>
            <label class="seg-opt"><input type="radio" name="c-mode" value="Duo queue" data-mode autocomplete="off">Duo queue</label>
          </div>
          <div class="calc-metrics">
            <div class="calc-metric">
              <span class="fig-lab">Delivered in</span>
              <span class="fig-mid" data-out="eta">—</span>
            </div>
            <div class="calc-metric">
              <span class="fig-lab">Boosters free now</span>
              <span class="fig-mid"><i class="calc-live calc-live-sm" aria-hidden="true"></i><span data-out="free">—</span></span>
            </div>
          </div>
        </div>
        <div class="calc-quote" aria-live="polite">
          <div class="calc-quote-info">
            <span class="fig-lab">Total price</span>
            <span class="calc-price" data-out="price">—</span>
          </div>
          <a class="btn btn-primary calc-cta" href="/checkout.html" data-continue>Continue <span class="calc-cta-arrow" aria-hidden="true">&rarr;</span></a>
        </div>
      </div>
    </div>
  </div>
</section>

{marquee()}

<section class="wrap section" id="games" style="padding-bottom:20px">
  <div class="stack" style="gap:26px">
    {sec_head("01", "Games", "Nine ladders.<br>Forty services.",
              note="Every service is priced per division and shown before you sign in. Placements, "
                   "net wins, coaching and duo on every title.")}
    {mosaic()}
  </div>
</section>

{statband()}

<section class="wrap section" id="live" style="padding-bottom:0">
  <div class="live-grid">
    <div class="stack" style="gap:26px">
      {sec_head("02", "Live", "Delivered today")}
      {live_feed()}
      <div class="safety" id="safety">
        <span class="sec-kicker" style="padding-top:6px"><span class="sec-kicker-n">03</span><span class="sec-kicker-l">Safety</span></span>
        <div class="stack" style="gap:14px">
          <h3>{esc(D.SAFETY['title'])}</h3>
          {safety_p}
        </div>
      </div>
    </div>
    {roster_panel()}
  </div>
</section>

<section class="wrap section" style="padding-bottom:0">
  <div class="split-9-11">
    <figure class="shot">
      <img src="{img("/assets/img/dashboard.svg")}" alt="Order tracking dashboard with live match history" width="1000" height="750" loading="lazy">
      <figcaption>Order dashboard — live</figcaption>
    </figure>
    <div class="stack" style="gap:24px">
      <h2 class="h-sec">You watch the whole thing</h2>
      <div class="stack" style="gap:18px">{dash}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <span class="tag tag-accent">Regional VPN</span>
        <span class="tag tag-accent">Offline appearance</span>
        <span class="tag tag-accent">Pro-rated refunds</span>
        <span class="tag tag-accent">No account sharing on duo</span>
      </div>
    </div>
  </div>
</section>

<section class="wrap section" id="reviews">
  <div class="stack" style="gap:24px">
    {sec_head("04", "Reviews", "What they said after", right="Verified orders only")}
    <div class="rev-strip">
      {trustpilot_badge()}
      <span class="rev-strip-note">Every review is tied to a paid, completed order — nothing incentivised. One per game, across the roster.</span>
    </div>
    {review_carousel(_reviews_one_per_game())}
  </div>
</section>

{cta_band(live=True, cta=("Continue your order", "/checkout.html"))}"""

    ld = [
        {"@context": "https://schema.org", "@type": "Organization",
         "name": D.BRAND, "url": D.SITE, "logo": D.SITE + "/assets/img/favicon.svg",
         "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8",
                             "reviewCount": D.STATS["reviews"].replace(",", ""), "bestRating": "5"}},
        {"@context": "https://schema.org", "@type": "WebSite", "name": D.BRAND, "url": D.SITE},
    ]
    return layout("/", "Rank boosting with the price up front — %s" % D.BRAND,
                  "Set two ranks and see the exact price and delivery window before you make an "
                  "account. Verified boosters, guest checkout, pro-rated refunds. 9 games, every region.",
                  body, current=None, jsonld=ld, mobile_bar=True)


def page_games_index():
    body = f"""<section class="wrap section">
  <div class="stack" style="gap:26px">
    <div class="sec-head">
      <div class="sec-head-copy">
        <span class="kicker">Rank boosting · {len(D.GAMES)} games · since 2019</span>
        <h1 class="h-games">Pick your<br>battlefield.</h1>
      </div>
      <p class="sec-note">Prices are per division and shown before you sign in. Placements, net
      wins, coaching and duo on every title.</p>
    </div>
    {game_cards()}
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:26px">
      {sec_head("01", "How it runs", "Three steps, then<br>it's out of your hands")}
      {steps_block()}
    </div>
    {roster_panel()}
  </div>
</section>

<section class="wrap section-tight">{guarantee_cards()}</section>

{cta_band()}"""
    return layout("/games/", "All games — %s" % D.BRAND,
                  "Rank boosting for League of Legends, Valorant, CS2, TFT, Marvel Rivals, Dota 2, "
                  "Apex, Overwatch 2 and Rocket League. Live prices, no account needed.",
                  body, current="/games/")


def page_game(g):
    fp = usd(from_price(g))
    others = [x for x in D.GAMES if x["slug"] != g["slug"]][:6]
    roster = [b for b in D.BOOSTERS if b["game"].split(" · ")[0].lower() in
              (g["short"].lower(), g["name"].lower())] or D.BOOSTERS[:4]
    def _for_game(r):
        token = r["game"].split(" · ")[0].strip().lower()
        return token in (g["name"].lower(), g["short"].lower()) or g["name"].lower().startswith(token)
    revs = [r for r in D.REVIEWS if _for_game(r)][:6]
    faq = [(("What do I need to give you for %s?" % g["name"]),
            "For solo orders: your login and the server. Nothing else — no recovery email, no "
            "phone number, no password change. For duo, nothing at all; you keep the account and "
            "queue with the booster.")] + D.FAQ[:6]

    ld = [
        {"@context": "https://schema.org", "@type": "Product",
         "name": "%s rank boosting" % g["name"], "description": g["meta"],
         "image": "%s/assets/img/keyart-%s.svg" % (D.SITE, g["slug"]),
         "brand": {"@type": "Brand", "name": D.BRAND},
         "offers": {"@type": "AggregateOffer", "priceCurrency": "USD",
                    "lowPrice": from_price(g),
                    "highPrice": quote(g["name"], g["ladder"][0], g["ladder"][-1])["total"],
                    "offerCount": len(g["ladder"]) * 2, "availability": "https://schema.org/InStock"},
         "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8",
                             "reviewCount": D.STATS["reviews"].replace(",", ""), "bestRating": "5"}},
        faq_ld(faq),
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Games", "item": D.SITE + "/games/"},
            {"@type": "ListItem", "position": 3, "name": g["name"],
             "item": "%s/games/%s.html" % (D.SITE, g["slug"])},
        ]},
    ]

    body = f"""<section class="hero-a">
  <img class="hero-art" src="{img('/assets/img/keyart-%s.svg' % g['slug'])}" alt="" width="1200" height="700">
  {FX}
  <div class="wrap hero-a-inner">
    <div class="hero-copy" style="max-width:none">
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/">Home</a> · <a href="/games/">Games</a> · {esc(g['name'])}
      </nav>
      <span class="kicker">{esc(g['services'])}</span>
      <h1 class="h-lg" style="font-size:clamp(38px,5.4vw,76px)">{esc(g['name'])}<br><span class="grad-text">from {fp}.</span></h1>
      <p class="lede">{esc(g['blurb'])}</p>
      <div class="stat-row">
        <div class="stat"><b>{esc(D.STATS['trustpilot'])}</b><span>Trustpilot · {esc(D.STATS['reviews'])} reviews</span></div>
        <div class="stat"><b>{esc(D.STATS['median_claim'])}</b><span>Median time to claim</span></div>
        <div class="stat" data-live-stat><b data-live="free">{D.STATS['free_now']}</b><span><span class="live-dot" aria-hidden="true"></span>{esc(g['short'])} boosters free now</span></div>
      </div>
      <p class="t-12" style="margin:0;color:var(--text-5);max-width:52ch">{esc(g['note'])}</p>
    </div>
    <div id="configure">{wizard(game=g['name'])}</div>
  </div>
</section>

{marquee()}

<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:26px">
      {sec_head("01", "How it runs", "Three steps, then<br>it's out of your hands")}
      {steps_block()}
    </div>
    <div class="stack" style="gap:20px">
      <div class="sec-head">
        <div class="sec-head-copy">
          <span class="sec-kicker"><span class="sec-kicker-n">02</span><span class="sec-kicker-l">Boosters</span></span>
          <h2 class="h-sec" style="font-size:clamp(24px,2.6vw,32px)">On shift now</h2>
        </div>
        <span class="tag tag-neutral">{D.STATS['online']} online</span>
      </div>
      {booster_table(roster)}
    </div>
  </div>
</section>

<section class="wrap section-tight">{guarantee_cards()}</section>

{'''<section class="wrap section">
  <div class="stack" style="gap:24px">
    %s
    %s
  </div>
</section>''' % (sec_head("03", "Reviews", "%s orders,<br>in players' words" % esc(g['name']), right="Verified orders only"), reviews_grid(revs)) if revs else ''}

<section class="wrap section" style="padding-top:0">
  <div class="split">
    <div class="stack" style="gap:14px">
      {sec_head("04", "FAQ", "Questions people<br>ask before paying")}
      <p class="t-14" style="max-width:36ch;color:var(--text-5)">If the answer isn't here, Discord
      replies in minutes — median {esc(D.STATS['reply'])} last month.</p>
      <a class="btn btn-secondary" href="/support.html" style="align-self:flex-start">Ask us instead</a>
    </div>
    {faq_block(faq)}
  </div>
</section>

<section class="wrap section" style="padding-top:0">
  <div class="stack" style="gap:20px">
    <h2 class="h-sec" style="font-size:clamp(24px,2.6vw,32px)">Other games</h2>
    {game_cards(others)}
  </div>
</section>

{cta_band(live=True, cta=("Continue your order", "/checkout.html"))}"""

    return layout("/games/%s.html" % g["slug"],
                  "%s boosting — live price, no account needed | %s" % (g["name"], D.BRAND),
                  g["meta"], body, current="/games/", jsonld=ld,
                  og_image=img("/assets/img/keyart-%s.svg" % g["slug"]), mobile_bar=True)


def page_how():
    dash = "".join(f"""<div>
        <div class="step-t" style="font-size:16px">{esc(t)}</div>
        <p class="t-14" style="margin:0;color:var(--text-3)">{esc(b)}</p>
      </div>""" for t, b in D.DASHBOARD_POINTS)
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">How it works</span>
      <h1 class="h-md">No account.<br>No surprises.<br>No ticket queue.</h1>
      <p class="lede">You can see the whole price before you tell us anything about yourself. That
      is the entire point of the way this is built: the calculator is the first thing on every page,
      the number it shows is the number you pay, and the only thing checkout asks for is an email to
      send the order link to.</p>
      <div class="btn-row"><a class="btn btn-primary" href="/games/">Start an order</a></div>
    </div>
    <div class="stack" style="gap:26px">{steps_block()}</div>
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="split-9-11">
    <figure class="shot">
      <img src="{img("/assets/img/dashboard.svg")}" alt="Order tracking dashboard with live match history" width="1000" height="750" loading="lazy">
      <figcaption>Order dashboard — live</figcaption>
    </figure>
    <div class="stack" style="gap:24px">
      <h2 class="h-sec">You watch the whole thing</h2>
      <div class="stack" style="gap:18px">{dash}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <span class="tag tag-accent">Regional VPN</span>
        <span class="tag tag-accent">Offline appearance</span>
        <span class="tag tag-accent">Pro-rated refunds</span>
        <span class="tag tag-accent">No account sharing on duo</span>
      </div>
    </div>
  </div>
</section>

<section class="wrap section">
  <div class="stack" style="gap:24px">
    <h2 class="h-sec">Solo or duo</h2>
    <div class="cards-2">
      <div class="card">
        <span class="card-kicker">Solo</span>
        <span class="card-title">The booster plays alone</span>
        <p class="card-body">Fastest and cheapest. You hand over the login, they connect through a
        VPN in your region, appear offline, and play inside the hours you set. You keep the account
        and can pause or take it back at any moment from the dashboard.</p>
      </div>
      <div class="card">
        <span class="card-kicker">Duo queue · +55%</span>
        <span class="card-title">You play every game</span>
        <p class="card-body">Nobody logs into your account, ever. You queue with the booster, voice
        optional, and most of them will call rotations and review your mistakes on the way up. It
        costs more because it takes their time at your pace.</p>
      </div>
    </div>
  </div>
</section>

<section class="wrap section" style="padding-top:0">
  <div class="split">
    <div class="stack" style="gap:12px">
      <h2 class="h-sec">Everything else<br>people ask</h2>
      <p class="t-14" style="max-width:36ch;color:var(--text-5)">Median first reply on Discord last
      month: {esc(D.STATS['reply'])}.</p>
    </div>
    {faq_block(D.FAQ)}
  </div>
</section>

{cta_band()}"""
    return layout("/how-it-works.html", "How boosting works here — %s" % D.BRAND,
                  "Configure, pay as a guest, watch every match from the dashboard, pause whenever "
                  "you want. Solo or duo, both explained.",
                  body, current=None, jsonld=[faq_ld(D.FAQ)])


def page_boosters():
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">The roster</span>
      <h1 class="h-md">Verified from<br>match history,<br>not self-reported.</h1>
      <p class="lede">Every applicant is trialled live on our account before they touch yours: five
      games, watched, in the bracket they claim. Ranks on this page are read from the API, not typed
      into a form. Anyone whose win rate drops below 62% over a rolling month comes off the board
      until they climb it back.</p>
      <div class="btn-row">
        <a class="btn btn-primary" href="/games/">Start an order</a>
        <a class="btn btn-secondary" href="/become-a-booster.html">Apply as a booster</a>
      </div>
    </div>
    {roster_panel(D.BOOSTERS[:5])}
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="stack" style="gap:24px">
    {sec_head("01", "Roster", "Everyone on shift", right="Updated live")}
    {booster_table(D.BOOSTERS)}
  </div>
</section>

<section class="wrap section" style="padding-top:0">
  <div class="stack" style="gap:24px">
    <h2 class="h-sec">What we screen for</h2>
    <div class="cards-3">
      <div class="card">
        <span class="card-kicker">Rank</span><span class="card-title">Two brackets above yours</span>
        <p class="card-body">Nobody is assigned an order inside their own bracket. The gap is what
        makes the win rate hold up over a long climb.</p>
      </div>
      <div class="card">
        <span class="card-kicker">Behaviour</span><span class="card-title">Clean account history</span>
        <p class="card-body">No bans, no chat restrictions, no low behaviour score. A booster who
        gets your account reported is a booster who costs us the refund.</p>
      </div>
      <div class="card">
        <span class="card-kicker">Conduct</span><span class="card-title">One strike on account sharing</span>
        <p class="card-body">Credentials never leave the order. A booster caught passing an account
        to anyone else is removed the same day and paid out nothing.</p>
      </div>
    </div>
  </div>
</section>

{cta_band()}"""
    return layout("/boosters.html", "Boosters on shift — %s" % D.BRAND,
                  "Who plays your order: verified ranks, live trials, monthly review, one free swap "
                  "per order.", body, current="/boosters.html")


def page_guarantee():
    faq = [f for f in D.FAQ if "refund" in f[0].lower() or "safe" in f[0].lower() or "play while" in f[0].lower()]
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">Safety &amp; guarantee</span>
      <h1 class="h-md">Written down,<br>not "depends on<br>the order".</h1>
      <p class="lede">A refund policy that needs a support ticket to explain isn't a policy. Here is
      the whole thing, in the three cases that actually happen.</p>
      <div class="btn-row"><a class="btn btn-primary" href="/games/">Start an order</a></div>
    </div>
    <div class="stack" style="gap:12px">
      <div class="card">
        <span class="card-kicker">Before a booster claims it</span>
        <span class="card-title">100% back, no reason asked</span>
        <p class="card-body">One button in the order page. The money is back on the original payment
        method within 5 business days, and nobody will email you to ask why.</p>
      </div>
      <div class="card">
        <span class="card-kicker">Started but unfinished</span>
        <span class="card-title">Pro-rated on what wasn't delivered</span>
        <p class="card-body">Divisions not climbed and wins not won are refunded at the same rate
        you paid for them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond
        portion, calculated by the same formula that quoted you.</p>
      </div>
      <div class="card">
        <span class="card-kicker">Past the ETA</span>
        <span class="card-title">Your choice, and we tell you first</span>
        <p class="card-body">If an order runs past its delivery window we message you before you
        notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back.
        Not claimed within 24 hours of payment? Refunded in full, automatically.</p>
      </div>
    </div>
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="split">
    <span class="sec-kicker" style="padding-top:6px"><span class="sec-kicker-n">03</span><span class="sec-kicker-l">Safety</span></span>
    <div class="stack" style="gap:14px">
      <h2 class="h-sec">{esc(D.SAFETY['title'])}</h2>
      {"".join('<p style="font-size:14.5px;line-height:1.75;color:var(--text-3);max-width:68ch;margin:0">%s</p>' % esc(p) for p in D.SAFETY['body'])}
      <p class="t-13" style="color:var(--text-5);max-width:68ch;margin:8px 0 0">Boosting is against
      the terms of service of every game listed here. We reduce the risk as far as it can be reduced
      and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is
      lying to you.</p>
    </div>
  </div>
</section>

<section class="wrap section" style="padding-top:0">{guarantee_cards()}</section>

<section class="wrap section" style="padding-top:0">
  <div class="split">
    <div><h2 class="h-sec">Refund<br>questions</h2></div>
    {faq_block(faq)}
  </div>
</section>

{cta_band()}"""
    return layout("/guarantee.html", "Refund and safety guarantee — %s" % D.BRAND,
                  "Full refund until a booster claims your order, pro-rated after that, automatic "
                  "refund if nobody claims it in 24 hours. The whole policy on one page.",
                  body, current="/guarantee.html", jsonld=[faq_ld(faq)])


def page_support():
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">Support</span>
      <h1 class="h-md">Two ways in.<br>Both are read<br>by people.</h1>
      <p class="lede">No ticket robot, no "we'll get back to you within 48 hours". Discord is the
      fast one — that's where this market already lives, and it's where our staff sit all day.</p>
      <div class="stat-row">
        <div class="stat"><b>{esc(D.STATS['reply'])}</b><span>Median first reply last month</span></div>
        <div class="stat"><b>{esc(D.STATS['discord'])}</b><span>Players in the Discord</span></div>
      </div>
    </div>
    <div class="stack" style="gap:12px">
      <div class="card" id="discord">
        <span class="card-kicker">Fastest</span>
        <span class="card-title">Discord — open a ticket in #support</span>
        <p class="card-body">Public server, private ticket channels. Order questions, refunds,
        booster swaps and pre-sales, 24/7. You can also just read what other buyers are saying
        before you order anything, which is rather the point of it being public.</p>
        <a class="btn btn-primary btn-sm" href="#discord" style="align-self:flex-start">Open the Discord invite</a>
      </div>
      <div class="card">
        <span class="card-kicker">On the record</span>
        <span class="card-title">Email — support@esportsboost.com</span>
        <p class="card-body">Better for anything involving a payment dispute or a document. Answered
        in under two hours during EU and NA daytime, under six overnight.</p>
      </div>
    </div>
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:12px">
      <h2 class="h-sec">Or write<br>it here</h2>
      <p class="t-14" style="max-width:40ch;color:var(--text-5)">Goes to the same inbox. If you have
      an order number, include it — it puts the message in front of the person handling that order.</p>
    </div>
    <form class="card" data-contact>
      <div class="field">
        <label for="c-email">Email</label>
        <input class="input" id="c-email" type="email" required placeholder="you@example.com">
      </div>
      <div class="field">
        <label for="c-order">Order number (optional)</label>
        <input class="input" id="c-order" type="text" placeholder="ESB-3F92K1">
      </div>
      <div class="field">
        <label for="c-msg">Message</label>
        <textarea class="input" id="c-msg" required placeholder="What's going on?"></textarea>
      </div>
      <button class="btn btn-primary btn-block" type="submit">Send message</button>
      <p class="fine" data-contact-note>Local preview — this form doesn't send anything.</p>
    </form>
  </div>
</section>

<section class="wrap section" style="padding-top:0">
  <div class="stack" style="gap:20px">
    <h2 class="h-sec">Before you write in</h2>
    {faq_block(D.FAQ)}
  </div>
</section>

{cta_band()}"""
    js = """<script>
document.querySelector('[data-contact]').addEventListener('submit', function (e) {
  e.preventDefault();
  document.querySelector('[data-contact-note]').textContent =
    'Local preview — nothing was sent. In production this posts to the support inbox.';
  window.esbTrack('generate_lead', { method: 'contact_form' });
});
</script>
"""
    return layout("/support.html", "Support — Discord and email, 24/7 | %s" % D.BRAND,
                  "Discord tickets and email support answered by people who play the game. Median "
                  "first reply 3m 40s.", body, current=None,
                  jsonld=[faq_ld(D.FAQ)], extra_js=js)


def page_reviews():
    tp = D.STATS["trustpilot"]                      # "4.8 / 5"
    score = tp.split("/")[0].strip()                # "4.8"
    try:
        fill = float(score) / 5.0
    except ValueError:
        fill = 1.0
    body = f"""<section class="wrap section rev-hero">
  <div class="rev-hero-copy">
    <span class="sec-kicker"><span class="sec-kicker-n">04</span><span class="sec-kicker-l">Reviews</span></span>
    <h1 class="h-sec">{esc(score)} / 5 across<br>{esc(D.STATS['reviews'])} reviews</h1>
    <p class="rev-lede">Every review below is attached to a paid, completed order — pulled from
    Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so one-star
    reviews sit in the same feed.</p>
    <div class="rev-hero-actions">
      <a class="btn btn-primary" href="/games/">Start an order</a>
      <span class="rev-chip">Unfiltered · 1&#9733; reviews included</span>
    </div>
  </div>

  <aside class="rev-card" aria-label="Overall rating summary">
    <span class="calc-kicker">Overall rating</span>
    <div class="rev-score">
      <div class="rev-score-num">{esc(score)}<span class="rev-score-den">/ 5</span></div>
      <div class="rev-score-side">
        {star_row(fill)}
        <span class="rev-score-word">Excellent</span>
      </div>
    </div>
    <div class="rev-count">Based on <b>{esc(D.STATS['reviews'])}</b> verified, completed orders</div>
    <div class="rev-card-div"></div>
    {trustpilot_badge()}
  </aside>
</section>

<section class="wrap section-tight" style="padding-top:0">{reviews_grid(D.REVIEWS)}</section>

<section class="wrap section">
  <div class="stack" style="gap:20px">
    <h2 class="h-sec">Where the score<br>comes from</h2>
    <p class="lede">A review request goes out once, on delivery, and never again. Nothing is
    incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than
    competitors who buy them, and it's the reason the score is worth reading at all.</p>
  </div>
</section>

{cta_band()}"""
    return layout("/reviews.html", "Reviews — %s" % D.BRAND,
                  "%s from %s verified orders. Unfiltered, one review request per completed order."
                  % (D.STATS["trustpilot"], D.STATS["reviews"]), body, current="/reviews.html")


def page_track():
    body = """<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">Track an order</span>
      <h1 class="h-md">Your link works<br>without a<br>password.</h1>
      <p class="lede">Guest orders are tracked by the link we emailed you. Lost it? Put the address
      you paid with below and we'll send it again. Nothing to remember, nothing to reset.</p>
    </div>
    <form class="card" data-track>
      <div class="field">
        <label for="t-order">Order number</label>
        <input class="input" id="t-order" placeholder="ESB-3F92K1">
      </div>
      <div class="field">
        <label for="t-email">or the email you paid with</label>
        <input class="input" id="t-email" type="email" placeholder="you@example.com">
      </div>
      <button class="btn btn-primary btn-block" type="submit">Find my order</button>
      <p class="fine" data-track-note>Local preview — try order number ESB-3F92K1.</p>
    </form>
  </div>
</section>

<section class="wrap section" style="padding-top:0" data-track-result hidden>
  <div class="calc" style="backdrop-filter:none;background:var(--panel)">
    <div class="calc-head">
      <span class="calc-kicker">ESB-3F92K1 — League of Legends · EUW · Solo</span>
      <span class="tag tag-accent">In progress</span>
    </div>
    <div class="calc-figs">
      <div><div class="fig-lab">Gold → Diamond</div><div class="fig-price">$112</div></div>
      <div><div class="fig-lab">Progress</div><div class="fig-mid">Platinum II · 62 LP</div></div>
      <div><div class="fig-lab">Booster</div><div class="fig-mid">vantaa</div></div>
      <div><div class="fig-lab">Delivered in</div><div class="fig-mid">2 days left</div></div>
    </div>
    <div class="table-scroll">
      <table class="table">
        <thead><tr><th>Match</th><th>Result</th><th>KDA</th><th>LP</th><th>When</th></tr></thead>
        <tbody>
          <tr><td>Ranked solo</td><td>Win</td><td>11 / 2 / 9</td><td class="wr">+24</td><td class="mono-cell">21 min ago</td></tr>
          <tr><td>Ranked solo</td><td>Win</td><td>7 / 4 / 14</td><td class="wr">+22</td><td class="mono-cell">58 min ago</td></tr>
          <tr><td>Ranked solo</td><td>Loss</td><td>3 / 6 / 7</td><td class="mono-cell">−18</td><td class="mono-cell">1 h ago</td></tr>
          <tr><td>Ranked solo</td><td>Win</td><td>15 / 3 / 5</td><td class="wr">+25</td><td class="mono-cell">2 h ago</td></tr>
        </tbody>
      </table>
    </div>
    <div class="btn-row">
      <button class="btn btn-secondary btn-sm" type="button">Pause the order</button>
      <button class="btn btn-secondary btn-sm" type="button">Request a different booster</button>
      <a class="btn btn-ghost" href="/support.html">Message support</a>
    </div>
  </div>
</section>
"""
    js = """<script>
document.querySelector('[data-track]').addEventListener('submit', function (e) {
  e.preventDefault();
  var id = (document.getElementById('t-order').value || '').trim().toUpperCase();
  var mail = (document.getElementById('t-email').value || '').trim();
  var box = document.querySelector('[data-track-result]');
  var note = document.querySelector('[data-track-note]');
  if (id === 'ESB-3F92K1') { box.hidden = false; note.textContent = 'Order found.'; box.scrollIntoView({ behavior: 'smooth' }); }
  else if (mail) { box.hidden = true; note.textContent = 'Local preview — in production a fresh tracking link goes to ' + mail + '.'; }
  else { box.hidden = true; note.textContent = 'No order with that number. Try ESB-3F92K1 in this preview.'; }
});
</script>
"""
    return layout("/track.html", "Track my order — %s" % D.BRAND,
                  "Follow a guest order without a password. Match history, live progress, pause and "
                  "booster swap in one place.", body, extra_js=js)


def page_checkout():
    regions = "".join('<option>%s</option>' % esc(r) for r in D.GAMES[0]["regions"])
    body = f"""<section class="wrap checkout">
  <div class="stack" style="gap:26px">
    <div class="progress" aria-label="Checkout progress">
      <span class="on"><span class="dot">1</span> Your email</span>
      <span class="bar"></span>
      <span data-step2><span class="dot">2</span> Order details</span>
      <span class="bar"></span>
      <span data-step3><span class="dot">3</span> Payment</span>
    </div>

    <div class="stack" style="gap:12px">
      <h1 class="h-sec">Checkout</h1>
      <p class="t-14" style="max-width:56ch;color:var(--text-3)">No account needed. We create the
      order under your email and send a one-click link to follow it. You can set a password
      afterwards if you want one.</p>
    </div>

    <form class="card" style="gap:16px" data-checkout>
      <div class="field">
        <label for="k-email">Email</label>
        <input class="input" id="k-email" type="email" required placeholder="you@example.com">
        <p class="t-11" style="margin:7px 0 0;color:var(--text-6)">Used for the order link and
        nothing else. No marketing unless you tick the box at the end.</p>
      </div>

      <div class="two-up">
        <div class="field">
          <label for="k-region">Server</label>
          <select class="input" id="k-region" data-sel="region" autocomplete="off">{regions}</select>
        </div>
        <div class="field">
          <label for="k-hours">Preferred hours</label>
          <select class="input" id="k-hours">
            <option>Any time</option>
            <option>My usual play hours (18:00–00:00)</option>
            <option>While I'm at work (09:00–17:00)</option>
            <option>Overnight only</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label for="k-notes">Anything the booster should know (optional)</label>
        <textarea class="input" id="k-notes" placeholder="Champion pool, roles, don't touch ranked flex…"></textarea>
      </div>

      <div class="wizard-div"></div>

      <div class="field">
        <label>Pay with</label>
        <div class="seg seg-full" role="group" aria-label="Payment method">
          <label class="seg-opt"><input type="radio" name="pay" value="card" checked> Card</label>
          <label class="seg-opt is-disabled"><input type="radio" name="pay" value="crypto" disabled> Crypto <span class="t-11" style="color:var(--text-6)">— coming soon</span></label>
        </div>
        <p class="t-11" style="margin:8px 0 0;color:var(--text-6)">Card details are entered on
        Stripe's secure checkout — we never see or store them. Statements read as a neutral
        merchant name.</p>
      </div>

      <label class="opt" style="border-color:transparent;padding:0">
        <input type="checkbox">
        <span class="t-12" style="color:var(--text-5)">Email me when my order is claimed and when
        it's done. Nothing else.</span>
      </label>

      <p class="t-12" data-pay-error role="alert" hidden
         style="margin:0;padding:11px 13px;border-radius:var(--radius);
                background:rgba(255,74,31,.1);border:1px solid rgba(255,74,31,.4);
                color:var(--ember-lit)"></p>

      <button class="btn btn-primary btn-block" type="submit">Place the order</button>
      <p class="fine">Refunded in full until a booster claims it · <a href="/guarantee.html">Read the guarantee</a></p>
    </form>

    <div class="card" data-confirm hidden>
      <span class="card-kicker">Order placed</span>
      <span class="card-title" data-order-id>ESB-000000</span>
      <p class="card-body">This is a local preview, so no payment was taken and no email was sent.
      In production this is the point where the order goes on the booster board, the confirmation
      email leaves, and <code>purchase</code> fires to GA4 and to the Meta CAPI gateway.</p>
      <a class="btn btn-primary btn-sm" href="/track.html" style="align-self:flex-start">Track this order</a>
    </div>
  </div>

  <aside class="wizard summary-card">
    <div class="wizard-head">
      <span class="calc-kicker">Order summary</span>
      <span class="tag tag-accent">Locked at checkout</span>
    </div>
    <div class="stack">
      <div class="sum-line"><span class="text-muted">Game</span><span data-sum="game">—</span></div>
      <div class="sum-line"><span class="text-muted">Climb</span><span data-sum="summary">—</span></div>
      <div class="sum-line"><span class="text-muted">Server</span><span data-sum="region">—</span></div>
      <div class="sum-line"><span class="text-muted">Options</span><span data-sum="addonlist">—</span></div>
      <div class="wizard-div"></div>
      <div class="sum-line"><span class="text-muted">Boost</span><span data-sum="base">—</span></div>
      <div class="sum-line"><span class="text-muted">Options</span><span data-sum="addons">—</span></div>
    </div>
    <div class="sum-total">
      <div class="stack" style="gap:4px">
        <span class="fig-lab">Total, tax included</span>
        <span class="quote-price" data-sum="total">—</span>
      </div>
      <div class="stack" style="gap:4px;text-align:right">
        <span class="fig-lab">Delivered in</span>
        <span class="quote-eta" data-sum="eta">—</span>
      </div>
    </div>
    <div class="wizard-div"></div>
    <div class="trust-row">
      <span class="tag tag-neutral">Money-back until claimed</span>
      <span class="tag tag-neutral">Regional VPN</span>
      <span class="tag tag-neutral">Offline appearance</span>
    </div>
    <a class="btn btn-secondary btn-block btn-sm" href="/games/">Change the order</a>
  </aside>
</section>
"""
    js = """<script>
(function () {
  var form = document.querySelector('[data-checkout]');
  var btn = form.querySelector('button[type=submit]');
  var errBox = form.querySelector('[data-pay-error]');
  window.esbTrack('add_payment_info', window.esbItemParams());

  if (/[?&]canceled=1/.test(location.search)) showError(
    'Payment canceled — nothing was charged. Your order is still here when you\\'re ready.');

  function showError(msg) {
    errBox.textContent = msg;
    errBox.hidden = false;
  }
  function busy(on) {
    btn.disabled = on;
    btn.textContent = on ? 'Contacting payment…' : 'Place the order';
  }

  // No account, no wallet stored — we hand the order to Stripe Checkout, which
  // owns every card field. The amount is re-computed server-side; the browser
  // never sends a price. Falls back to the local preview when payments are off.
  function previewConfirm() {
    var id = 'ESB-' + Math.random().toString(36).slice(2, 8).toUpperCase();
    var p = window.esbItemParams();
    p.transaction_id = id;
    window.esbTrack('purchase', p);
    document.querySelector('[data-order-id]').textContent = id;
    document.querySelector('[data-confirm]').hidden = false;
    document.querySelector('[data-step2]').classList.add('on');
    document.querySelector('[data-step3]').classList.add('on');
    form.hidden = true;
    document.querySelector('[data-confirm]').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    errBox.hidden = true;
    var s = window.esbState();
    var payload = {
      game: s.game, service: s.service, from: s.from, to: s.to, mode: s.mode,
      wins: s.wins, placements: s.placements, region: s.region, addons: s.addons,
      email: (form.querySelector('#k-email') || {}).value || '',
      hours: (form.querySelector('#k-hours') || {}).value || '',
      notes: (form.querySelector('#k-notes') || {}).value || ''
    };
    busy(true);
    fetch('/api/checkout', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    }).then(function (res) {
      if (res.status === 503) { busy(false); previewConfirm(); return; }
      if (res.status === 200 && res.body.url) {
        // purchase fires on the success page, only once Stripe confirms payment.
        window.location.href = res.body.url;  // → Stripe Checkout
        return;
      }
      busy(false);
      showError(res.body.error || 'Payment could not be started. Please try again.');
    }).catch(function () {
      busy(false);
      showError('Network error reaching payment. Please try again.');
    });
  });
})();
</script>
"""
    return layout("/checkout.html", "Checkout — %s" % D.BRAND,
                  "Guest checkout: email, then payment. No account required, refunded in full until "
                  "a booster claims the order.", body, extra_js=js)


def page_checkout_success():
    body = """<section class="wrap section">
  <div class="stack" style="gap:26px;max-width:640px;margin-inline:auto">
    <div class="progress" aria-label="Checkout progress">
      <span class="on"><span class="dot">1</span> Your email</span>
      <span class="bar"></span>
      <span class="on"><span class="dot">2</span> Order details</span>
      <span class="bar"></span>
      <span class="on"><span class="dot">3</span> Payment</span>
    </div>

    <div class="card" style="gap:14px">
      <span class="card-kicker" data-state-kicker>Confirming payment…</span>
      <h1 class="h-sec" data-state-title>One moment</h1>
      <p class="card-body" data-state-body>We're confirming your payment with Stripe.</p>
      <div class="stack" style="gap:8px" data-receipt hidden>
        <div class="sum-line"><span class="text-muted">Order</span><span data-r="order">—</span></div>
        <div class="sum-line"><span class="text-muted">Paid</span><span data-r="amount">—</span></div>
        <div class="sum-line"><span class="text-muted">Order</span><span data-r="detail">—</span></div>
        <div class="sum-line"><span class="text-muted">Delivered in</span><span data-r="eta">—</span></div>
      </div>
      <a class="btn btn-primary btn-sm" href="/track.html" style="align-self:flex-start">Track this order</a>
    </div>
  </div>
</section>
"""
    js = """<script>
(function () {
  var q = new URLSearchParams(location.search);
  var sid = q.get('session_id');
  var kicker = document.querySelector('[data-state-kicker]');
  var title = document.querySelector('[data-state-title]');
  var bodyEl = document.querySelector('[data-state-body]');
  var receipt = document.querySelector('[data-receipt]');
  function set(k, t, b) { kicker.textContent = k; title.textContent = t; bodyEl.textContent = b; }
  var usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

  if (!sid) {
    set('No order', 'Nothing to show here', 'This page confirms a completed payment. Start an order to continue.');
    return;
  }
  fetch('/api/session?id=' + encodeURIComponent(sid)).then(function (r) {
    return r.json().then(function (d) { return { status: r.status, body: d }; });
  }).then(function (res) {
    var d = res.body || {};
    if (res.status === 200 && d.paid) {
      set('Payment received', 'You\\'re all set', 'Your order is on the booster board. We\\'ve emailed your one-click tracking link.');
      document.querySelector('[data-r="order"]').textContent = d.order_id || '—';
      document.querySelector('[data-r="amount"]').textContent =
        (typeof d.amount_total === 'number') ? usd.format(d.amount_total / 100) : '—';
      document.querySelector('[data-r="detail"]').textContent = d.detail || '—';
      document.querySelector('[data-r="eta"]').textContent = d.eta || '—';
      receipt.hidden = false;
      // purchase — the real conversion, fired only on a confirmed-paid session
      try {
        var p = window.esbItemParams();
        p.transaction_id = d.order_id;
        if (typeof d.amount_total === 'number') p.value = d.amount_total / 100;
        window.esbTrack('purchase', p);
      } catch (e) {}
      try { localStorage.removeItem('esb.order.v1'); } catch (e) {}
    } else if (res.status === 200) {
      set('Payment pending', 'Almost there', 'Stripe hasn\\'t confirmed this payment yet. If you completed checkout, it will settle shortly — your tracking email arrives when it does.');
    } else {
      set('Could not confirm', 'Something went wrong', d.error || 'We could not confirm this session.');
    }
  }).catch(function () {
    set('Could not confirm', 'Something went wrong', 'Network error confirming your payment.');
  });
})();
</script>
"""
    return layout("/checkout/success.html", "Order confirmed — %s" % D.BRAND,
                  "Your payment is confirmed and your order is on the booster board.",
                  body, extra_js=js)


def page_become_booster():
    opts = "".join("<option>%s</option>" % esc(g["name"]) for g in D.GAMES)
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">Work here</span>
      <h1 class="h-md">Get paid<br>for the queue<br>you'd play anyway.</h1>
      <p class="lede">Payouts weekly, 70% of the order value on solo and 75% on duo, no deductions
      for the platform's payment fees. Pick your own shifts; take an order or don't. What we ask for
      is the rank, a clean account history, and that you never pass an account to anyone.</p>
      <div class="stat-row">
        <div class="stat"><b>70–75%</b><span>Of the order, to you</span></div>
        <div class="stat"><b>Weekly</b><span>Payouts, no minimum</span></div>
        <div class="stat"><b>5 games</b><span>Live trial before onboarding</span></div>
      </div>
    </div>
    <form class="card" data-apply>
      <div class="field">
        <label for="b-handle">In-game name</label>
        <input class="input" id="b-handle" required placeholder="Name #TAG">
      </div>
      <div class="two-up">
        <div class="field">
          <label for="b-game">Game</label>
          <select class="input" id="b-game">{opts}</select>
        </div>
        <div class="field">
          <label for="b-rank">Peak rank</label>
          <input class="input" id="b-rank" required placeholder="Challenger 1042 LP">
        </div>
      </div>
      <div class="field">
        <label for="b-contact">Discord</label>
        <input class="input" id="b-contact" required placeholder="username">
      </div>
      <div class="field">
        <label for="b-op">Anything else</label>
        <textarea class="input" id="b-op" placeholder="Hours you can play, roles, other accounts…"></textarea>
      </div>
      <button class="btn btn-primary btn-block" type="submit">Apply</button>
      <p class="fine" data-apply-note>Local preview — this form doesn't send anything.</p>
    </form>
  </div>
</section>

{rule()}

<section class="wrap section">
  <div class="stack" style="gap:24px">
    <h2 class="h-sec">How the trial works</h2>
    {steps_block()}
  </div>
</section>
"""
    js = """<script>
document.querySelector('[data-apply]').addEventListener('submit', function (e) {
  e.preventDefault();
  document.querySelector('[data-apply-note]').textContent = 'Local preview — nothing was sent.';
  window.esbTrack('generate_lead', { method: 'booster_application' });
});
</script>
"""
    return layout("/become-a-booster.html", "Become a booster — %s" % D.BRAND,
                  "70–75% of the order value, weekly payouts, your own shifts. Live trial before "
                  "onboarding.", body, extra_js=js)


LEGAL = {
    "terms": ("Terms of service", [
        ("Who we are", "eSports Boost sells rank-boosting and coaching services for the games listed "
         "on this site. Placing an order means you accept these terms."),
        ("What you're buying", "A named target — a rank, a number of wins, or a set of placement "
         "games — delivered by a booster we assign. The quote shown at checkout is fixed; we will "
         "never ask for more money to finish an order you have already paid for."),
        ("Your account", "For solo orders you give us credentials to play on. We use them only "
         "for your order, never change your password or recovery details, and delete them when the "
         "order closes. You may take the account back at any moment from the order page."),
        ("Game terms", "Boosting breaches the terms of service of every game we cover. You are "
         "choosing to accept that risk. We mitigate it as described on the guarantee page and we do "
         "not indemnify you against action taken by the game publisher."),
        ("Chargebacks", "Talk to us first. A chargeback opened without contacting support closes "
         "the order and forfeits any pro-rated refund you would otherwise have been owed."),
    ]),
    "refunds": ("Refund policy", [
        ("Before a booster claims it", "100% refunded, on request, no reason required. Money returns "
         "to the original payment method within 5 business days."),
        ("Not claimed within 24 hours", "Refunded in full automatically. You do not have to ask, and "
         "we do not wait for you to notice."),
        ("Started but unfinished", "Refunded pro-rata on the undelivered portion, calculated with the "
         "same formula that produced your quote — divisions not climbed, wins not won."),
        ("Past the delivery window", "We contact you before the ETA lapses with three options: "
         "continue with a 15% credit, swap the booster free of charge, or take the unfinished "
         "portion back in cash."),
        ("What isn't refundable", "Rank lost after delivery, on games you played yourself. Orders "
         "where the account was changed mid-boost by someone other than the assigned booster. "
         "Coaching sessions already attended."),
    ]),
    "privacy": ("Privacy", [
        ("What we collect", "An email address, the order details, and payment metadata from our "
         "processor. For solo orders, the game credentials you supply, encrypted at rest."),
        ("What we don't collect", "We do not require a name, an address or a phone number, and we do "
         "not ask for the recovery email on your game account."),
        ("Credentials", "Stored encrypted, visible only to the assigned booster and to support, and "
         "deleted when the order closes. Never shared between orders or with third parties."),
        ("Analytics", "We measure the funnel with Google Analytics 4 and Meta's conversion API, "
         "including the checkout steps, so we can tell where the site frustrates people. No order "
         "content or credentials are ever sent to either."),
        ("Deleting your data", "Ask on Discord or by email and everything attached to your address "
         "is removed within 30 days, except records we are legally required to keep for accounting."),
    ]),
}


def page_legal(slug):
    title, sections = LEGAL[slug]
    blocks = "".join(f"""<div class="stack" style="gap:8px">
      <h2 style="font-size:20px">{esc(h)}</h2>
      <p class="t-14" style="margin:0;color:var(--text-3);max-width:74ch;line-height:1.75">{esc(t)}</p>
    </div>""" for h, t in sections)
    body = f"""<section class="wrap section">
  <div class="stack" style="gap:32px;max-width:840px">
    <div class="stack" style="gap:12px">
      <span class="kicker">Legal</span>
      <h1 class="h-sec">{esc(title)}</h1>
      <span class="kicker kicker-dim">Last updated {esc(D.LEGAL_UPDATED)}</span>
    </div>
    {blocks}
    <p class="t-13" style="margin:0;color:var(--text-5)">Questions about any of this go to
    <a href="/support.html">support</a>. Plain answers, same day.</p>
  </div>
</section>

{cta_band()}"""
    return layout("/legal/%s.html" % slug, "%s — %s" % (title, D.BRAND),
                  "%s for %s." % (title, D.BRAND), body)


def page_404():
    body = """<section class="wrap section">
  <div class="stack" style="gap:22px;max-width:60ch">
    <span class="kicker">Error 404</span>
    <h1 class="h-md">That page<br>isn't on<br>the ladder.</h1>
    <p class="lede">The link is dead or the page moved. The calculator is two clicks away either
    way.</p>
    <div class="btn-row">
      <a class="btn btn-primary" href="/games/">Pick a game</a>
      <a class="btn btn-secondary" href="/">Back to the homepage</a>
    </div>
  </div>
</section>"""
    return layout("/404.html", "Page not found — %s" % D.BRAND, "That page doesn't exist.", body)


# ══════════════════════════════════════════════════════════════════════════
#  emit
# ══════════════════════════════════════════════════════════════════════════
def img(rel):
    """Resolve an image path through whatever emit_art() actually wrote."""
    return IMG_MAP.get(rel, rel)


IMG_MAP = {}


def write(rel, content):
    path = os.path.join(DIST, rel.lstrip("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return rel


def client_data():
    payload = {
        "perDivision": D.PER_DIVISION,
        "perStep": D.PER_STEP,
        "ladders": {g["name"]: list(g["ladder"]) for g in D.GAMES},
        "tiers": {g["name"]: g["tiers"] for g in D.GAMES},
        "divmap": {g["name"]: g["divmap"] for g in D.GAMES},
        "factors": {g["name"]: g["factor"] for g in D.GAMES},
        "prices": {g["name"]: g["prices"] for g in D.GAMES if g.get("prices")},
        "services": {g["name"]: g["services"] for g in D.GAMES},
        "slugs": {g["name"]: g["slug"] for g in D.GAMES},
        "regions": {g["name"]: g["regions"] for g in D.GAMES},
        "addons": D.ADDONS,
        "boostersFree": D.STATS["free_now"],
    }
    return ("/* generated by build.py — do not edit */\nwindow.ESB_DATA = %s;\n"
            % json.dumps(payload, ensure_ascii=False, indent=2))


ASSETS_IN = os.path.join(HERE, "assets-in")
DROP_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg")


def drop_in(name):
    """Look for a real, licensed asset in site/assets-in/ before falling back
    to the generated one. Drop `keyart/valorant.jpg` in and the next build uses
    it everywhere that game appears — no code change, no layout change.

    Named slots:
      keyart/<game-slug>.<ext>     mosaic tiles, game-page hero, game cards
      emblem/<game-slug>.<ext>     live-feed thumbs, game-list rows
      avatar/<booster-handle>.<ext>  roster rows
      hero.<ext>  closing.<ext>  portrait.<ext>  dashboard.<ext>  og.<ext>
    """
    for ext in DROP_EXT:
        src = os.path.join(ASSETS_IN, name + ext)
        if os.path.isfile(src):
            return src
    return None


def place(rel, name, generated):
    """Copy the dropped-in file to `rel` if one exists, else write the SVG."""
    src = drop_in(name)
    if src:
        out = os.path.splitext(rel)[0] + os.path.splitext(src)[1]
        dst = os.path.join(DIST, out.lstrip("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        REAL_ASSETS[name] = out
        return out
    write(rel, generated)
    return rel


REAL_ASSETS = {}


def emit_art():
    """Fill every image slot the handoff leaves empty. Generated originals by
    default; anything present in site/assets-in/ wins — see drop_in()."""
    n = 0
    write("/assets/img/favicon.svg", art.favicon()); n += 1
    place("/assets/img/og-default.svg", "og", art.og()); n += 1
    place("/assets/img/hero.svg", "hero", art.hero()); n += 1
    place("/assets/img/closing.svg", "closing", art.closing()); n += 1
    place("/assets/img/dashboard.svg", "dashboard", art.dashboard()); n += 1
    for g in D.GAMES:
        place("/assets/img/keyart-%s.svg" % g["slug"], "keyart/" + g["slug"],
              art.keyart(g["slug"], g["name"])); n += 1
        place("/assets/img/emblem-%s.svg" % g["slug"], "emblem/" + g["slug"],
              art.emblem(g["slug"], g["short"])); n += 1
    for b in D.BOOSTERS:
        place("/assets/img/avatar-%s.svg" % b["handle"], "avatar/" + b["handle"],
              art.avatar(b["handle"], b["hue"])); n += 1
    place("/assets/img/portrait-vantaa.svg", "portrait", art.avatar("vantaa", 20, size=480)); n += 1
    return n


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    shutil.copytree(PUBLIC, DIST)

    write("/assets/js/data.js", client_data())
    images = emit_art()
    for name, out in REAL_ASSETS.items():
        base = "/assets/img/" + name.split("/")[-1]
        if name.startswith("keyart/"):
            IMG_MAP["/assets/img/keyart-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("emblem/"):
            IMG_MAP["/assets/img/emblem-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("avatar/"):
            IMG_MAP["/assets/img/avatar-%s.svg" % name.split("/")[1]] = out
        elif name == "portrait":
            IMG_MAP["/assets/img/portrait-vantaa.svg"] = out
        else:
            IMG_MAP["/assets/img/%s.svg" % ("og-default" if name == "og" else name)] = out

    pages = [
        ("/index.html", page_home()),
        ("/games/index.html", page_games_index()),
        ("/how-it-works.html", page_how()),
        ("/boosters.html", page_boosters()),
        ("/guarantee.html", page_guarantee()),
        ("/support.html", page_support()),
        ("/reviews.html", page_reviews()),
        ("/track.html", page_track()),
        ("/checkout.html", page_checkout()),
        ("/checkout/success.html", page_checkout_success()),
        ("/become-a-booster.html", page_become_booster()),
        ("/404.html", page_404()),
    ]
    pages += [("/legal/%s.html" % s, page_legal(s)) for s in LEGAL]
    pages += [("/games/%s.html" % g["slug"], page_game(g)) for g in D.GAMES]

    for rel, html in pages:
        write(rel, html)

    urls = ["/"] + [r for r, _ in pages if r not in
                    ("/index.html", "/404.html", "/checkout.html", "/checkout/success.html")]
    urls = [u.replace("/index.html", "/") for u in urls]
    sm = "".join("  <url><loc>%s%s</loc></url>\n" % (D.SITE, u) for u in sorted(set(urls)))
    write("/sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % sm)
    write("/robots.txt", "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % D.SITE)

    print("built %d pages + %d images → %s" % (len(pages), images, DIST))


if __name__ == "__main__":
    main()
