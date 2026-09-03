#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static build for the esportsboost redesign — v2 "Ashfall".

    python3 site/build.py       →  site/dist/

No dependencies. Every page is generated from src/data.py; every image from
src/art.py. The homepage is the v2 immersive design; the rest of the site
carries the same system.
"""
import hashlib
import json
import os
import re
import shutil
import sys
from urllib.parse import quote as _urlq
from datetime import datetime, timedelta
from html import escape as esc

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import art  # noqa: E402
import data as D  # noqa: E402
import geo  # noqa: E402
# OFFER_PCT / TOKEN_TTL, so the mystery modal's copy quotes the discount and
# the deadline the server actually issues rather than a typed pair.
import mystery  # noqa: E402
import pricing  # noqa: E402

DIST = os.path.join(HERE, "dist")
PUBLIC = os.path.join(HERE, "public")

BY_SLUG = {g["slug"]: g for g in D.GAMES}
BY_NAME = {g["name"]: g for g in D.GAMES}
BOOSTER = {b["handle"]: b for b in D.BOOSTERS}

# ── Google Ads (gtag.js) ──────────────────────────────────────────────────
# The account tag and its Purchase conversion label. These are NOT secrets —
# the tag ships in every page's HTML to every visitor, so committing them is
# safe and, unlike an env var, can't silently go missing on a build (which is
# exactly what happened once). The env vars still override, so a staging
# project can point at a different account, or set GOOGLE_ADS_ID="" to disable:
#   GOOGLE_ADS_ID             the account tag (default AW-18171663463)
#   GOOGLE_ADS_PURCHASE_LABEL the Purchase conversion action's label
# The base tag needs only the id; the purchase conversion needs both. The
# conversion fires on the confirmed-paid success page against the REAL charged
# amount/currency/order id (see page_checkout_success), not the snippet's
# placeholder 1.0 EUR — that is what feeds Smart Bidding a true ROAS.
GOOGLE_ADS_ID = os.environ.get("GOOGLE_ADS_ID", "AW-18171663463").strip()
GOOGLE_ADS_PURCHASE_LABEL = os.environ.get(
    "GOOGLE_ADS_PURCHASE_LABEL", "CraYCOGOibAcEOeo9thD").strip()


def _gads_head():
    """The Google tag (gtag.js) for the <head> — one per page, as high as
    possible. Empty string when unconfigured. It defines the global `gtag()`
    and shares `window.dataLayer` with the site's own funnel beacon."""
    if not GOOGLE_ADS_ID:
        return ""
    gid = esc(GOOGLE_ADS_ID)
    return (
        "<!-- Google tag (gtag.js) -->\n"
        '<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>\n'
        "<script>\n"
        "window.dataLayer = window.dataLayer || [];\n"
        "function gtag(){dataLayer.push(arguments);}\n"
        "gtag('js', new Date());\n"
        "gtag('config', '%s');\n"
        "</script>\n" % (gid, gid)
    )


def gads_purchase_send_to():
    """`AW-…/label` for the Purchase conversion, or "" when either half is
    unset. The success-page script guards on this before calling gtag."""
    if GOOGLE_ADS_ID and GOOGLE_ADS_PURCHASE_LABEL:
        return "%s/%s" % (GOOGLE_ADS_ID, GOOGLE_ADS_PURCHASE_LABEL)
    return ""


# ══════════════════════════════════════════════════════════════════════════
#  pricing — mirrors assets/js/app.js exactly
# ══════════════════════════════════════════════════════════════════════════
def usd(n, cents=False):
    return ("${:,.2f}" if cents else "${:,.0f}").format(n)


def money(n, cents=False, fixed=False):
    """A static USD price wrapped so i18n.js can re-format it into the active
    currency client-side. The `data-usd` value is the raw USD amount."""
    raw = ("%.2f" % n) if cents else ("%d" % round(n))
    # `data-cents` travels with the price so i18n.js's reformatStaticMoney()
    # re-formats it to the cent on a currency switch. Without it a $14.99
    # account card re-renders as "€14" — a price nothing charges.
    flag = ' data-cents="1"' if cents else ""
    # ⚠ `data-fixed` says this figure is the SAME NUMBER in every currency and
    # must not be multiplied by a rate — the accounts rule. Without it a €24.90
    # card re-renders as "$27.07" the moment somebody switches currency.
    flag += ' data-fixed="1"' if fixed else ""
    return '<span class="money" data-usd="%s"%s>%s</span>' % (raw, flag, usd(n, cents))


def money_multi(prices, cents=True):
    """A price with ONE FIGURE PER CURRENCY in the DOM — the accounts rule.

    `prices` is the listing's own table (`{"usd": 29.90, "eur": 24.90, …}`).
    Each row ships as `data-<code>`, and i18n.js's reformatStaticMoney() picks
    the active currency's row instead of multiplying the dollar by a rate. That
    is what makes a currency switch a *lookup* here while it stays a conversion
    on every boosting price on the same page.

    `data-usd` doubles as the no-JS default and the fallback for a currency with
    no row — which cannot happen while data.py asserts the table covers
    CHARGE_RATES, and is why that assert exists."""
    base = float(prices[D.ACCOUNT_BASE_CUR])
    attrs = "".join(' data-%s="%.2f"' % (c, float(v)) for c, v in sorted(prices.items())
                    if c != D.ACCOUNT_BASE_CUR)
    return ('<span class="money" data-usd="%.2f"%s%s>%s</span>'
            % (base, ' data-cents="1"' if cents else "", attrs, usd(base, cents)))


def money_parts_multi(prices):
    """The two-size price — dollars big, cents small — with the same
    per-currency rows `money_multi()` ships."""
    base = float(prices[D.ACCOUNT_BASE_CUR])
    whole = int(base)
    attrs = "".join(' data-%s="%.2f"' % (c, float(v)) for c, v in sorted(prices.items())
                    if c != D.ACCOUNT_BASE_CUR)
    return ('<span class="money ac-money" data-usd="%.2f" data-cents="1"%s>'
            '<span class="ac-money-m" data-money-main>%s</span>'
            '<span class="ac-money-c" data-money-cents>%s</span></span>'
            % (base, attrs, usd(whole), (".%02d" % round((base - whole) * 100))))


def money_parts(n, fixed=False):
    """A cents price split for the two-size treatment the account cards use —
    the dollars big, the cents small. Server-side this is always USD; the client
    re-splits through `esbMoneyParts()` when the currency changes, which is what
    keeps "72,99 €" splitting in the right place for a French reader."""
    whole = int(n)
    return ('<span class="money ac-money" data-usd="%.2f" data-cents="1"%s>'
            '<span class="ac-money-m" data-money-main>%s</span>'
            '<span class="ac-money-c" data-money-cents>%s</span></span>'
            % (n, ' data-fixed="1"' if fixed else "",
               usd(whole), (".%02d" % round((n - whole) * 100))))


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
# The order dashboard, and the page the homepage's "Open the demo dashboard"
# and the checkout confirmation both land on. It was /track.html, "Track my
# order", until the rename: every order on it is D.DEMO_ORDER — a placeholder —
# and there is no lookup backend behind the form, so the honest name for what
# the page actually is is Demo. Referenced from the nav, the footer's support
# column, the dashboard section and both checkout confirmations, so it is one
# constant rather than six string literals.
DEMO_HREF = "/demo.html"

# The signed-in account's order history. The account menu's "My orders" lands
# here rather than jumping straight into the single demo dashboard — a list of
# orders, each opening its own view. Like the dashboard it renders, the orders
# on it are placeholder data (there is no per-customer order store behind the
# facade session — see AUTH_PLACEHOLDER); the page says so.
ORDERS_HREF = "/orders.html"

# /accounts.html — the ready-made-account board. Named here rather than
# written out five times: the nav, the header menu, the LoL teaser band, the
# footer and page_accounts() itself all point at it, which is exactly how
# DEMO_HREF came to exist.
ACCOUNTS_HREF = "/accounts.html"

NAV = [
    ("/games", "Games"),
    # The fifth product. Top-level rather than a card inside the Games menu:
    # it is bought instead of a boost, not as part of one, and a visitor who
    # came for an account has no reason to open a menu about ladders. Dropped
    # automatically when the catalogue is empty, the rule every other entry
    # below follows.
    (ACCOUNTS_HREF, "Accounts"),
    ("/#live", "Live"),
    ("/boosters", "Boosters"),
    ("/guarantee.html", "Safety"),
    # "Guides" is one word to match the rest of the nav — "Free" belongs on the
    # cards inside the page, where it reads as a benefit, not on the chrome,
    # where a price word reads as a promo banner. Placed after Safety.
    ("/guides.html", "Guides"),
    ("/reviews.html", "Reviews"),
]
# Only when HIDE_PLACEHOLDER_CLAIMS drops the pages behind them — never link
# to a destination the build didn't produce.
if not D.accounts_in_stock():
    NAV.remove((ACCOUNTS_HREF, "Accounts"))
if not D.LIVE_FEED:
    NAV.remove(("/#live", "Live"))
if not D.BOOSTERS:
    NAV.remove(("/boosters", "Boosters"))
if not getattr(D, "GUIDES", None):
    NAV.remove(("/guides.html", "Guides"))
if not D.REVIEWS:
    NAV.remove(("/reviews.html", "Reviews"))

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

# The picked value is validated against i18n.js's ESB_RATES / pricing.py's
# CHARGE_RATES — a currency listed here with no rate behind it cannot be
# charged, and falls back to USD at the Stripe session.
# CAD wears "C$", not "$" — Canada's own formatting renders CAD as a bare
# dollar sign, which is the one currency mark on this list a reader could
# confuse with another. The icon column IS the mark the site prints, and every
# surface that prints money agrees on it: i18n.js CUR_MARK, ops.js CUR_SYM and
# payments.CURRENCY_SIGNS (the order mail). test_currency_signs() locks it.
# Three, and the business's rule: the EU in euros, the UK in pounds, everywhere
# else in dollars. CAD was dropped with that rule — see geo.currency_for().
CURRENCIES = [("USD", "$", "USD"), ("EUR", "€", "EUR"), ("GBP", "£", "GBP")]
LANGUAGES = [("EN", "🇬🇧", "EN"), ("FR", "🇫🇷", "FR"), ("DE", "🇩🇪", "DE")]

# Static "translate" mark (文 + A) for the language button. The flags stay in the
# menu, but the closed control shows the glyph instead of whichever flag happens
# to be selected — a language is not a country, and EN under a Union Jack reads
# as "United Kingdom" to everyone outside it.
_LANG_GLYPH = (
    '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" focusable="false" '
    'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 2.6v1.7"/><path d="M3.4 5.2h11.2"/>'
    '<path d="M11.6 7.4c-1 3-3.3 5.4-7 6.9"/><path d="M6.2 7.4c1.4 3.2 3.6 5.4 6.8 6.6"/>'
    '<path d="M14.6 21.4l3.6-8.8 3.6 8.8"/><path d="M15.9 18.3h4.6"/></svg>'
)


def _loc_dropdown(kind, label, options, glyph=None):
    """One switcher. `glyph` pins a fixed mark on the button (language); without
    it the button mirrors the selected option's icon, which i18n.js swaps
    through `data-loc-icon` (currency: $ / € / £ / C$)."""
    opts = "".join(
        '<li class="loc-opt" role="option" data-value="%s" tabindex="-1">'
        '<span class="loc-flag">%s</span><span class="loc-code">%s</span></li>'
        % (val, icon, esc(code)) for val, icon, code in options
    )
    first = options[0]
    mark = ('<span class="loc-glyph" aria-hidden="true">%s</span>' % glyph if glyph
            else '<span class="loc-flag" data-loc-icon>%s</span>' % first[1])
    return f"""<div class="loc" data-loc="{kind}">
        <button type="button" class="loc-btn" aria-haspopup="listbox" aria-expanded="false" aria-label="{esc(label)}">
          {mark}<span class="loc-code" data-loc-label>{esc(first[2])}</span>{_CHEV}
        </button>
        <ul class="loc-menu" role="listbox" aria-label="{esc(label)}">{opts}</ul>
      </div>"""


def locale_switcher():
    return f"""<div class="locale">
        {_loc_dropdown("currency", "Currency", CURRENCIES)}
        {_loc_dropdown("language", "Language", LANGUAGES, glyph=_LANG_GLYPH)}
      </div>"""


# ══════════════════════════════════════════════════════════════════════════
#  the site header — design_handoff_site_header
# ══════════════════════════════════════════════════════════════════════════
# Two screens (1440 / 390) built as ONE component with breakpoints, the same
# way the Best Sellers band is. The header carries four jobs in ~106px: announce
# the promotion, prove there are boosters online, navigate nine ladders and a
# roster, and let a returning buyer reach their account.
#
# The whole thing is scoped on `.hd` in site.css — sixth scoped port after
# `.hero-a` / `.co` / `.gg` / `.dsh` / `.rst`. Product radii per element,
# sentence-case controls, nothing leaking past the scope.
#
# What is load-bearing here is written up in CLAUDE.md; the short version:
#
# - **One DOM, two presentations.** The nav items, their menus and the auth
#   panel are emitted once. On desktop `.hd-panel` is `display:contents` and the
#   menus are full-bleed panels under the bar; below 1000px the same nodes are
#   the sheet and its accordion. Emitting the menu twice is how the two drift.
# - **Every card points at a page this build produces.** The handoff's menus
#   carry a "Booster leaderboard" and an "FAQ" that have no page here; those
#   slots went to /reviews.html and the guarantee page's FAQ band. Same rule
#   NAV already follows a few lines up.
# - **Every figure is read, never typed.** Prices come from `from_price()`,
#   counts from `D.STATS`, the spotlight from `D.SPOTLIGHT` — so the menu can
#   never quote a number the page behind it contradicts.


def _hd_ico(name, size=17, cls="hd-ico"):
    """A header glyph. Linework at every size — the handoff's duotone sheet has
    no equivalent here and a two-tone fill at 17px reads as a smudge."""
    return _ico(name, size, cls, stroke=True)


# The OAuth buttons' brand marks. Unlike the rest of the header's linework
# glyphs, these are the networks' own logos in their own colours — Discord's
# Blurple mascot mark and Google's four-colour G (the same G `pay_glyphs()`
# draws). They carry their fills, so `.hd-oa-discord`'s tint no longer applies.
# The buttons are wired to a real flow now (src/oauth.py); before launch, replace
# these simplified marks with the assets from each provider's brand kit, which
# require the logo be used unmodified (same trademark rule as pay_marks()).
_HD_BRAND = {
    "discord": ('<svg class="{cls}" width="{s}" height="{s}" viewBox="0 0 24 24" '
                'aria-hidden="true" focusable="false"><path fill="#5865F2" '
                'd="M20.317 4.369a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.865'
                '-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037'
                'A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082'
                '.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295'
                ' 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008'
                '-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0'
                'a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1'
                '-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028'
                ' 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a'
                '.061.061 0 0 0-.031-.03zM8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.419'
                ' 2.157-2.419 1.211 0 2.176 1.096 2.157 2.42 0 1.332-.955 2.418-2.157 2.418zm7.975 0c-1.183'
                ' 0-2.157-1.086-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.211 0 2.176 1.096 2.157 2.42 0'
                ' 1.332-.946 2.418-2.157 2.418z"/></svg>'),
    "google": ('<svg class="{cls}" width="{s}" height="{s}" viewBox="0 0 18 18" '
               'aria-hidden="true" focusable="false">'
               '<path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1'
               '-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"/>'
               '<path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86'
               '-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"/>'
               '<path fill="#FBBC05" d="M3.97 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3.01'
               '-2.33Z"/>'
               '<path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9'
               ' 0 0 0 .96 4.96l3.01 2.33C4.68 5.17 6.66 3.58 9 3.58Z"/></svg>'),
}


def _hd_brand(name, size=17, cls="hd-oa-i"):
    """A network's own logo for an OAuth button — colour marks, not linework."""
    return _HD_BRAND[name].format(cls=cls, s=size)


# Card glyph per game. Generic shapes on purpose — see the `_ICONS` comment and
# `pay_marks()`: a game's own mark or key art needs licensing. Any slug not
# named here falls back to the catalogue tile, so a tenth game is never a
# missing icon.
HD_GAME_ICON = {
    "league-of-legends": "sword",
    "valorant": "crosshair",
    "marvel-rivals": "bolt",
    "teamfight-tactics": "knight",
    "overwatch-2": "shield-chevron",
    "rocket-league": "trophy",
    "dota-2": "sword",
    "apex-legends": "crosshair",
    "counter-strike-2": "crosshair",
}

# A stylized monogram per game — the first letter of its name, set in the display
# face (Chakra Petch) inside the card tile. Not the game's own logo, which needs
# licensing (same rule as HD_GAME_ICON, pay_marks() and the Trustpilot star); a
# letter is not a mark. One letter per game, and every one distinct, so the five
# menu cards never show the same initial twice — L V M T O R D A C.
HD_GAME_LETTER = {
    "league-of-legends": "L",
    "valorant": "V",
    "marvel-rivals": "M",
    "teamfight-tactics": "T",
    "overwatch-2": "O",
    "rocket-league": "R",
    "dota-2": "D",
    "apex-legends": "A",
    "counter-strike-2": "C",
}

# How many games get their own card before the catalogue tile takes the last
# slot. Five + "All nine ladders" is the handoff's grid.
HD_GAME_CARDS = 5


def _hd_services(g, n=4):
    """A game's first `n` services as a menu note — "Elo boost, Placements, Net
    wins, Duo". Read off the game's own catalogue entry, so a card can never
    advertise something the game page doesn't sell.

    One node per service, with the commas in `<i aria-hidden>` carriers. That is
    what makes the note translate: i18n.js matches whole text nodes, and every
    one of these words is already a key — the games grid renders the identical
    list as chips through `services_of()`. Joining them into one sentence would
    leave the menu quoting English services beside a French grid, and would need
    a new dictionary entry per game that drifts the moment `services` changes.

    The title case is `services_of()`'s, not the handoff's sentence case: the
    dictionary is keyed on these exact words, and matching the grid matters more
    than the capital letters.
    """
    parts = services_of(g)[:n]
    return '<i aria-hidden="true">,</i>'.join('<span>%s</span>' % esc(s) for s in parts)


def hd_card(href, icon, name, note="", tag="", tag_html="", figure="", note_html="", mark=""):
    """One menu card — the mega menu's grid cell and the nav sheet's row.

    `figure` is a number that belongs inside `note` (a review count, a roster
    size). It rides in its own `<b>` rather than being interpolated, because
    i18n.js matches whole text nodes: a note with a digit in the middle of it
    silently stops translating. Where a figure has to lead, `note` is the part
    after it and the `<b>` is emitted first.

    `tag_html` is the same escape hatch for a pill carrying money: a price has
    to go through `money()` or the menu keeps quoting dollars after the visitor
    switches the header to EUR — one set of numbers, everywhere, is the rule
    this build is held to.
    """
    pill = tag_html or ('<span class="hd-card-tag">%s</span>' % esc(tag) if tag else "")
    fig = '<b class="hd-card-fig">%s</b>' % esc(str(figure)) if figure != "" else ""
    body = note_html or ('<span>%s</span>' % esc(note))
    # A game card carries its monogram letter; everything else keeps its glyph.
    inner = '<span class="hd-card-mono">%s</span>' % esc(mark) if mark else _hd_ico(icon, 17, "hd-ico")
    tile_cls = "hd-card-tile hd-card-tile-mono" if mark else "hd-card-tile"
    return f"""<a class="hd-card" href="{esc(href)}">
            <span class="{tile_cls}" aria-hidden="true">{inner}</span>
            <span class="hd-card-body">
              <span class="hd-card-top"><span class="hd-card-name">{esc(name)}</span>{pill}</span>
              <span class="hd-card-note">{fig}{body}</span>
            </span>
          </a>"""


def hd_games_cards():
    cards = "".join(
        hd_card("/games/%s.html" % g["slug"], HD_GAME_ICON.get(g["slug"], "grid"),
                g["name"], note_html=_hd_services(g),
                mark=HD_GAME_LETTER.get(g["slug"], ""),
                tag_html='<span class="hd-card-tag"><span>From</span>%s</span>'
                         % money(from_price(g)))
        for g in D.GAMES[:HD_GAME_CARDS]
    )
    rest = [g["short"] for g in D.GAMES[HD_GAME_CARDS:]]
    if rest:
        # "+4" — how many ladders the five cards above don't name. The short
        # names are data and stay in their own node, so "are live too" survives
        # as a whole translatable phrase beside them.
        cards += hd_card("/games", "grid", "All %s games" % spell(len(D.GAMES)),
                         tag="+%d" % len(rest),
                         note_html='<b class="hd-card-fig">%s</b><span>are live too</span>'
                                   % esc(", ".join(rest)))
    return cards


def hd_boosters_cards():
    n = D.STATS.get("online") or len(D.BOOSTERS)
    cards = hd_card("/boosters", "users", "Browse the roster",
                    "verified boosters, one game each", figure=n)
    top = D.by_handle.get(D.SPOTLIGHT.get("handle", "")) if hasattr(D, "by_handle") else None
    if top is None:
        top = next((b for b in D.BOOSTERS if b["handle"] == D.SPOTLIGHT.get("handle")), None)
    if top:
        # The spotlight is roster data, exactly as the home hero's card reads it
        # — so the menu, the card and the profile can never name three people.
        cards += hd_card(booster_href(top), "trophy", D.SPOTLIGHT["eyebrow"],
                         "%s — %s, %d orders" % (top["handle"], top["tier"], top["orders"]),
                         tag="Top")
    # "No extra fee", not the handoff's "+10%": pricing.py charges nothing for a
    # named booster and the server recomputes every amount, so a fee here would
    # be a price the checkout refuses to honour. Same line the roster rail runs.
    cards += hd_card("/boosters", "user-focus", "Hire a specific booster",
                     "Name one at checkout, no extra fee")
    cards += hd_card("/boosters#vetting", "seal", "How we verify",
                     "Rank proof, trial orders, review floor")
    cards += hd_card("/become-a-booster.html", "briefcase", "Apply as a booster",
                     "Master+ with a clean account", tag="Hiring")
    if D.REVIEWS:
        cards += hd_card("/reviews.html", "star", "Read their reviews",
                         "reviews, filterable by game and score",
                         figure=D.STATS.get("reviews", ""))
    return cards


def hd_safety_cards():
    return "".join((
        hd_card("/guarantee.html", "shield-check", "The guarantee",
                "Refunded until a booster claims it"),
        hd_card("/guarantee.html#safety", "lock-key", "Account safety",
                "Regional VPN, your hours, offline"),
        hd_card("/guarantee.html#faq-password-and-settings", "prohibit", "What we never do",
                "No bots, no password changes"),
        hd_card("/legal/refunds.html", "receipt", "Refund policy",
                "Pro-rated, in five business days"),
        hd_card("/guarantee.html#faq", "question", "FAQ",
                "The six questions support gets most"),
        hd_card(DEMO_HREF, "package", "Demo dashboard",
                "No password — the link is the login"),
    ))


def hd_rail():
    """The mega menu's right rail — "Right now".

    The rail repeats the promo bar's proof on purpose: an open menu covers that
    bar, and the reassurance is exactly what a visitor mid-decision was reading.
    Every line is a figure the rest of the site already asserts, so none of them
    is typed here.
    """
    # (glyph, [parts]) — each part is either a plain string, which stays a whole
    # translatable text node, or a ("b", value) figure that rides in its own
    # <b>. Same split every counted sentence on this site uses.
    lines = []
    n = D.STATS.get("online")
    if n:
        lines.append(("users", [("b", n), "boosters on shift"]))
    claim = D.STATS.get("median_claim")
    if claim:
        lines.append(("hourglass", ["Time to claim", ("b", claim)]))
    lines.append(("shield-check", ["Money-back until claimed"]))
    rows = ""
    for ico, parts in lines:
        inner = "".join('<b>%s</b>' % esc(str(p[1])) if isinstance(p, tuple)
                        else '<span>%s</span>' % esc(p) for p in parts)
        rows += '<li>%s%s</li>' % (_hd_ico(ico, 17, "hd-rail-ico"), inner)
    # Points at the homepage's own delivery feed. Rendered only when there is a
    # feed to land on — same rule NAV follows for the "Live" item.
    more = ('<a class="hd-rail-more" href="/#live">Watch orders land live%s</a>'
            % _ico("arrow", 13, "ico", stroke=True)) if D.LIVE_FEED else ""
    return f"""<div class="hd-rail">
            <span class="hd-label">Right now</span>
            <ul class="hd-rail-list">{rows}</ul>
            {more}
          </div>"""


# key → (nav label, mega-menu section label, cards builder, sheet count)
HD_MENUS = [
    ("games", "Games", "Pick your game", hd_games_cards, lambda: str(len(D.GAMES))),
    ("boosters", "Boosters", "Who plays your order", hd_boosters_cards,
     lambda: str(D.STATS.get("online") or "")),
    ("safety", "Safety", "Before you buy", hd_safety_cards, lambda: ""),
]
HD_BY_KEY = {k: (label, sec, cards, count) for k, label, sec, cards, count in HD_MENUS}

# Which NAV entries open a menu. Live and Reviews are single destinations — the
# handoff is explicit that they get no menu, and a menu holding one link is a
# worse control than the link.
HD_NAV = [
    ("games", "/games", "Games"),
    # A single destination — no menu. Eight listings do not need a mega panel,
    # and a menu holding one link is a worse control than the link.
    (None, ACCOUNTS_HREF, "Accounts"),
    (None, "/#live", "Live"),
    ("boosters", "/boosters", "Boosters"),
    ("safety", "/guarantee.html", "Safety"),
    # Guides is a single destination — a lead-capture page, no menu. Same shape
    # as Live and Reviews.
    (None, "/guides.html", "Guides"),
    (None, "/reviews.html", "Reviews"),
]
HD_NAV = [(k, h, l) for k, h, l in HD_NAV if (h, l) in NAV]
HD_COUNTS = {"/reviews.html": lambda: D.STATS.get("reviews", "")}


def hd_promo():
    """The 38px promo band (34px on phones).

    Three groups. Left: the sale name, the **code chip** and the end date. The
    chip is a copy button with a dashed border — a code you cannot click is a
    code people mistype, and the dashes are what make it read as a coupon
    without button chrome. Centre: the availability status, absolutely centred
    because the two flanking groups are unequal widths and flex would push it
    off. Right: currency and language as quiet ghost buttons.

    The handoff drops the old "-15% off with code" wording — the sale name and
    the chip carry it. The percentage is not lost: it rides in the chip's
    accessible name, so the discount is still announced to anyone who cannot see
    that the bar is a coupon.
    """
    p = getattr(D, "PROMO", None) or {}
    code = (p.get("code") or "").strip()
    ends = (p.get("ends") or "").strip()
    label = (D.PROMOS.get(code, {}).get("label") or "").strip() if code else ""
    pct = (p.get("tag") or "").strip().lstrip("-")

    sale = '<span class="hd-sale">%s</span>' % esc(label) if label else ""
    chip = ""
    if code:
        aria = "Copy discount code %s%s" % (code, (" — %s off" % pct) if pct else "")
        chip = ('<button type="button" class="hd-code" data-hd-copy="%s" aria-label="%s">'
                '<span class="hd-code-t">%s</span><span class="hd-code-done">Copied</span>'
                '%s%s</button>'
                % (esc(code), esc(aria), esc(code),
                   _ico("copy", 11, "ico hd-code-i", stroke=True),
                   _ico("check", 11, "ico hd-code-ok", stroke=True)))
    end = ('<span class="hd-ends">%s<span>%s</span></span>'
           % (_ico("clock", 13, "ico", stroke=True), esc(ends))) if ends else ""
    return f"""<div class="hd-promo">
  <div class="wrap hd-promo-in">
    <div class="hd-promo-l">{sale}{chip}{end}</div>
    {hd_live()}
    <div class="hd-promo-r">{locale_switcher()}</div>
  </div>
</div>"""


def hd_live(cls=""):
    """"Online now — N verified boosters".

    A status, not a statistic: the copy opens with a word rather than a digit,
    and the dot sits in a soft green halo pulsing over 2.4s — slower than the
    site's 2s dots, because this one runs on every page and a fast pulse in
    peripheral vision is an irritant.

    Reads the same `D.STATS['online']` as the roster panel, the order card and
    the footer, so the site never quotes two roster counts. No stat → no line,
    and the bar falls back to promo-left / switchers-right.

    Every figure and separator rides in its own node: i18n.js matches whole text
    nodes, so "Online now" and "verified boosters" have to stay whole words.
    """
    n = D.STATS.get("online")
    if not n:
        return ""
    return (f'<p class="hd-live{(" " + cls) if cls else ""}">'
            f'<span class="hd-live-halo" aria-hidden="true"><span class="hd-live-dot"></span></span>'
            f'<span class="hd-live-txt"><b>Online Now</b><i aria-hidden="true">—</i>'
            f'<b class="hd-live-n" data-live="online" data-live-min="36" '
            f'data-raw="{n}">{n}</b><span>Verified Boosters</span></span></p>')


def hd_menu(key):
    """One mega menu. Full-bleed panel on desktop, accordion content in the
    sheet — the same nodes either way, so the two can never disagree."""
    label, sec, cards, _count = HD_BY_KEY[key]
    return f"""<div class="hd-menu" id="hd-m-{key}" data-hd-panel="{key}">
        <div class="wrap hd-menu-in">
          <div class="hd-menu-main">
            <span class="hd-label">{esc(sec)}</span>
            <div class="hd-cards">{cards()}</div>
          </div>
          {hd_rail()}
        </div>
      </div>"""


def hd_nav(current):
    """The nav items, grouped left with the brand.

    They used to be centred, which left ~400px of dead space either side and put
    the menu next to neither anchor. Items are 40px targets with hover, open and
    current states.

    An item with a menu is an `<a>` pointing at its hub (/games/, /boosters/,
    /guarantee.html), carrying the `data-hd-menu` disclosure hooks. On a real
    pointer at desktop width the panel opens on hover and a click follows the
    link to the hub; on the accordion (narrow or coarse-pointer) app.js
    intercepts the tap to toggle the section instead of navigating, since a hub
    that leaves the page on tap defeats the accordion. With scripting off the
    link still reaches the hub and site.css opens the panel on
    `:hover`/`:focus-within` under `.no-js`, which the head script clears the
    moment scripting is on. The hub also stays the first card of every menu, so
    it is reachable from inside the open panel as well.
    """
    out = ""
    for key, href, label in HD_NAV:
        cur = ' aria-current="page"' if current == href else ""
        count = ""
        if key:
            c = HD_BY_KEY[key][3]()
            if c:
                count = '<b class="hd-count">%s</b>' % esc(c)
        elif href in HD_COUNTS:
            c = HD_COUNTS[href]()
            if c:
                count = '<b class="hd-count">%s</b>' % esc(c)
        if not key:
            out += (f'<div class="hd-item"><a class="hd-link" href="{href}"{cur}>'
                    f'<span>{esc(label)}</span>{count}'
                    f'{_ico("caret-right", 15, "ico hd-go", stroke=True)}</a></div>')
            continue
        out += (f'<div class="hd-item" data-hd-item="{key}">'
                f'<a class="hd-link" href="{href}" data-hd-menu="{key}"'
                f' aria-expanded="false" aria-controls="hd-m-{key}"{cur}>'
                f'<span>{esc(label)}</span>{count}'
                f'{_ico("caret", 9, "ico hd-caret", stroke=True)}'
                f'{_ico("plus", 15, "ico hd-acc hd-acc-on", stroke=True)}'
                f'{_ico("minus", 15, "ico hd-acc hd-acc-off", stroke=True)}'
                f'</a>{hd_menu(key)}</div>')
    return out


def hd_actions(current):
    """Demo, a divider, and account access.

    **Log in carries the fill and "Start an order" is gone.** The old header put
    an ember *outline* on a CTA that already appears in every hero and every
    closing band — loud enough to read as primary, styled as secondary, and the
    fifth copy of one button on the page. The header's own job is account
    access, so that is what takes the one filled action here.

    Both account states are in the DOM; app.js unhides one. The chip shows live
    order state because that is the most common reason a returning buyer opens
    this menu.
    """
    cur = ' aria-current="page"' if current == DEMO_HREF else ""
    return f"""<div class="hd-actions">
      <a class="hd-demo" href="{DEMO_HREF}"{cur}>{_ico("monitor", 16, "ico", evenodd=True)}<span>Demo</span></a>
      <span class="hd-sep" aria-hidden="true"></span>
      <button type="button" class="hd-login" data-hd-auth="signin">
        <span>Log in</span>{_ico("arrow", 14, "ico", stroke=True)}
      </button>
      {hd_chip()}
      <button type="button" class="hd-burger" data-hd-sheet aria-expanded="false" aria-controls="hd-panel">
        {_ico("list", 21, "ico hd-burger-on", stroke=True)}{_ico("x", 19, "ico hd-burger-off", stroke=True)}
        <span class="sr-only">Menu</span>
      </button>
    </div>"""


def hd_chip():
    """The signed-in account chip. Hidden until app.js says there is a session —
    see AUTH_PLACEHOLDER."""
    return f"""<button type="button" class="hd-acct" data-hd-account aria-expanded="false"
        aria-controls="hd-account" hidden>
        <span class="hd-avatar" aria-hidden="true" data-hd-initial>—</span>
        <span class="hd-acct-txt">
          <span class="hd-acct-name" data-hd-name>—</span>
          <span class="hd-acct-meta" data-hd-meta></span>
        </span>
        {_ico("caret", 9, "ico hd-acct-caret", stroke=True)}
      </button>"""


def chrome(current, nav_outline=False):
    """The global header — promo band, nav band, menus, sheet, auth, account.

    `nav_outline` is kept as a no-op parameter: it used to drop the nav's "Start
    an order" to an outline on the game pages so the order card's gradient CTA
    was the only filled action in view. That CTA is gone from the header
    entirely now, so the rule it existed to serve — one filled button per
    viewport — holds everywhere without it. Callers still pass it.
    """
    return f"""{hd_promo()}
<header class="hd" data-hd>
  <div class="wrap hd-bar">
    <a class="hd-brand" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
    <div class="hd-panel" id="hd-panel" data-hd-panel-root>
      {hd_live("hd-live-sheet")}
      <nav class="hd-nav" aria-label="Main">{hd_nav(current)}</nav>
      <div class="hd-sheet-foot">
        <a class="hd-sheet-demo" href="{DEMO_HREF}">{_ico("monitor", 19, "ico", evenodd=True)}<span>Demo dashboard</span></a>
        <div class="hd-sheet-loc">{locale_switcher()}</div>
      </div>
    </div>
    {hd_actions(current)}
  </div>
</header>
{hd_account_menu()}
{hd_auth()}"""


# ── the auth panel ────────────────────────────────────────────────────────
# ⚠ PARTLY REAL — read this before wiring anything to it.
#
# Email/password login is now real: the form POSTs to /api/account, which
# verifies the password against a salted PBKDF2 hash in the account store (see
# src/accounts.py) — an unknown email or a wrong password is refused. Checkout
# stays guest-only (a CRO-AUDIT constraint: no login wall anywhere in the order
# flow), and orders are still tracked by an emailed link.
#
# What is NOT finished, and is blocking for launch — same standing as the fifty
# invented boosters, DEMO_ORDER and the review distribution:
#
#   - the email/password session is a record in localStorage, NOT the signed
#     server cookie the OAuth path mints (oauth.py). Move it onto the same
#     session so a login survives properly and can be revoked server-side;
#   - /api/account is public and unauthenticated (the form is on every page), so
#     it needs rate limiting — a real login endpoint is a credential-stuffing
#     target. Per-field validation and inline server errors are wired;
#   - the OAuth buttons ARE wired now — src/oauth.py runs the Google/Discord
#     authorization-code flow and mints a signed session cookie (set
#     GOOGLE_/DISCORD_CLIENT_ID + _SECRET + SESSION_SECRET to enable; unset, the
#     button keeps its facade message). Still outstanding: each provider's
#     licensed sign-in mark (the glyphs here are simplified, same trademark rule
#     as pay_marks() and the Trustpilot star), and linking an OAuth login to an
#     existing email/password account (today they are separate rows by email);
#   - password reset, email verification, 2FA, session expiry and the
#     guest → account claim flow all have to exist — the handoff lists them as
#     required follow-up, not options;
#   - the account menu's rows need pages behind them. Two of the handoff's five
#     have one here (My orders → the dashboard, Messages → support); Saved
#     configurations and Account settings are not built, so they are not
#     rendered. Same rule as the "Booster leaderboard" menu card.
#
# The panel says out loud, in two places, that an account is optional. That is
# not decoration: a header implying a login wall contradicts the two pages that
# close the sale, and it pre-empts the support ticket that begins "I can't find
# my order because I never made an account." Do not trim those notes, and do
# not trim the terms line's game-rules clause — it is the honest one.
AUTH_PLACEHOLDER = True


def _hd_field(name, hook, label, typ="text", placeholder="", autocomplete=""):
    """One labelled input. `hook` is the `data-hd-*` app.js binds to, kept
    separate from the field's `name`: the display name's input would otherwise
    take `data-hd-name`, which is already the account chip's and the popover's
    handle node — and `paint()` would write the visitor's handle into the form."""
    auto = ' autocomplete="%s"' % autocomplete if autocomplete else ""
    return f"""<label class="hd-f">
              <span class="hd-f-top"><span class="hd-label">{esc(label)}</span></span>
              <input class="hd-input" type="{typ}" name="{name}" data-hd-{hook}
                placeholder="{esc(placeholder)}"{auto}>
            </label>"""


def hd_auth():
    """The sign-in / sign-up panel — a 452px modal on desktop, a bottom sheet on
    phones, one DOM either way.

    Order is the argument. OAuth leads because that is where this audience
    already is (the site advertises a 3,000-player Discord), the optional-account
    note sits above it because the most useful thing this panel can say is that
    you don't need it, and the padlock line under the submit — "This is your
    store account, never your game login" — is the single most important
    sentence in the panel: the live fear in this market is credential theft, and
    it belongs here rather than on a help page.

    Both tabs' copy is in the DOM with one side hidden, so every sentence stays
    a whole text node for i18n.js.
    """
    if not AUTH_PLACEHOLDER:
        return ""
    tabs = "".join(
        f'<button type="button" class="hd-tab" data-hd-tab="{k}" role="tab"'
        f' aria-selected="{"true" if k == "signin" else "false"}">{esc(l)}</button>'
        for k, l in (("signin", "Log in"), ("signup", "Create account"))
    )
    return f"""<div class="hd-auth" data-hd-auth-panel hidden>
  <div class="hd-auth-scrim" data-hd-auth-close></div>
  <div class="hd-auth-card" role="dialog" aria-modal="true" aria-labelledby="hd-auth-t">
    <span class="hd-grab" aria-hidden="true"></span>
    <div class="hd-auth-head">
      <span class="hd-auth-brand" aria-hidden="true"><span class="shard"></span>esports<b>boost</b></span>
      <h2 class="hd-auth-title" id="hd-auth-t">
        <span data-hd-when="signin">Log in</span>
        <span data-hd-when="signup">Create your account</span>
      </h2>
      <button type="button" class="hd-x" data-hd-auth-close aria-label="Close">
        {_ico("x", 13, "ico", stroke=True)}
      </button>
    </div>

    <form class="hd-auth-body" data-hd-form novalidate>
      <div class="hd-tabs" role="tablist" aria-label="Log in or create an account">{tabs}</div>

      <p class="hd-note">
        {_hd_ico("user-dashed", 17, "hd-note-i")}
        <span data-hd-when="signup">An account is optional. It keeps every order, thread and saved
        configuration in one place — you can still buy as a guest.</span>
        <span data-hd-when="signin">Bought as a guest? You don't need an account. Use the link we
        emailed you, or resend it from the order tracker.</span>
      </p>

      <div class="hd-oauth">
        <button type="button" class="hd-oa" data-hd-oauth="discord">
          {_hd_brand("discord", 18, "hd-oa-i")}
          <span data-hd-when="signin">Continue with Discord</span>
          <span data-hd-when="signup">Sign up with Discord</span>
        </button>
        <button type="button" class="hd-oa" data-hd-oauth="google">
          {_hd_brand("google", 17, "hd-oa-i")}
          <span data-hd-when="signin">Continue with Google</span>
          <span data-hd-when="signup">Sign up with Google</span>
        </button>
      </div>

      <div class="hd-or"><span>or with email</span></div>

      <div data-hd-when="signup">
        {_hd_field("name", "dname", "Display name", placeholder="What your booster calls you",
                   autocomplete="nickname")}
      </div>
      {_hd_field("email", "email", "Email", typ="email", placeholder="you@example.com",
               autocomplete="email")}
      <div class="hd-pass">
        <span class="hd-f-top">
          <span class="hd-label">Password</span>
          <a class="hd-forgot" href="/support.html" data-hd-when="signin">Forgot it?</a>
        </span>
        <span class="hd-pass-wrap">
          <input class="hd-input hd-input-bare" type="password" name="password" data-hd-pass
            placeholder="Your password" data-hd-ph-signin="Your password"
            data-hd-ph-signup="At least 6 characters" autocomplete="current-password">
          <button type="button" class="hd-eye" data-hd-eye aria-pressed="false"
            aria-label="Show password">
            {_ico("eye", 15, "ico hd-eye-on", stroke=True)}{_ico("eye-off", 15, "ico hd-eye-off", stroke=True)}
          </button>
        </span>
      </div>

      <div data-hd-when="signup">
        <div class="hd-str" data-hd-strength aria-hidden="true"><i></i><i></i><i></i><i></i></div>
        <p class="hd-str-note" data-hd-strength-note>Six characters or more. A passphrase beats a
        symbol soup.</p>
        <button type="button" class="hd-terms" data-hd-terms aria-pressed="false">
          <span class="hd-check" aria-hidden="true">{_ico("check", 10, "ico", stroke=True)}</span>
          <span>I've read the <a href="/legal/terms.html">terms</a> and the
          <a href="/legal/privacy.html">privacy policy</a>, including how boosting relates to each
          game's rules.</span>
        </button>
      </div>

      <p class="hd-status" data-hd-status data-hd-when="signin">We'll keep you signed in on this
      device for 30 days.</p>

      <!-- General form error, shown on either tab. The status line above is
           sign-in only (data-hd-when), so a "create" error — a taken email —
           has nowhere to land without this. -->
      <p class="hd-err" data-hd-err role="alert" hidden></p>

      <button type="submit" class="hd-submit">
        <span data-hd-when="signin">Log in</span>
        <span data-hd-when="signup">Create account</span>
        {_ico("arrow", 15, "ico", stroke=True)}
      </button>

      <p class="hd-foot-note">
        {_ico("lock", 14, "ico", stroke=True)}
        <span data-hd-when="signin">This is your store account, never your game login.</span>
        <span data-hd-when="signup">We never ask for your game password here.</span>
      </p>

      <div class="hd-switch">
        <span data-hd-when="signin">New here?</span>
        <span data-hd-when="signup">Already have an account?</span>
        <button type="button" class="hd-switch-a" data-hd-switch>
          <span data-hd-when="signin">Create an account</span>
          <span data-hd-when="signup">Log in</span>
        </button>
      </div>
    </form>
  </div>
</div>"""


def hd_account_menu():
    """The signed-in popover — 268px desktop, 250px on phones.

    Three rows, not the handoff's five: Saved configurations and Account
    settings have no page in this build, and a row that goes nowhere is the dead
    control the roster's "Load more" rule exists to prevent. Log out is
    separated by a rule and 6px of margin so it is never a mis-tap.

    The count pills are rendered empty and filled by app.js from the session
    object. There is no orders backend, so nothing fills them today — which is
    correct: the handoff's "1 order live / 2 messages" is its own stated fixture,
    and a hard-coded count here would be a claim about the visitor.
    """
    if not AUTH_PLACEHOLDER:
        return ""
    rows = [
        (ORDERS_HREF, "package", "My orders", "orders"),
        ("/support.html", "chat", "Messages", "messages"),
    ]
    items = "".join(
        f'<a class="hd-arow" href="{h}">{_hd_ico(ico, 17, "hd-arow-i")}'
        f'<span>{esc(label)}</span>'
        f'<b class="hd-arow-badge" data-hd-badge="{key}" hidden></b></a>'
        for h, ico, label, key in rows
    )
    return f"""<div class="hd-account" id="hd-account" data-hd-account-menu hidden>
  <div class="hd-account-head">
    <span class="hd-avatar hd-avatar-lg" aria-hidden="true" data-hd-initial>—</span>
    <span class="hd-account-id">
      <span class="hd-account-name" data-hd-name>—</span>
      <span class="hd-account-mail" data-hd-mail></span>
    </span>
  </div>
  <div class="hd-account-rows">
    {items}
    <button type="button" class="hd-arow hd-arow-out" data-hd-logout>
      {_hd_ico("sign-out", 17, "hd-arow-i")}<span>Log out</span>
    </button>
  </div>
</div>"""


def chrome_min():
    """Distraction-free header for the pay flow (`layout(bare=True)`).

    The full chrome is a promo bar, a nine-link menu, a currency switcher and
    two more CTAs. On a page whose only job is finishing, every one of those is
    an exit. What is left is the brand — so the buyer knows whose form this is —
    a padlock, and a way to ask for help without leaving.

    Defined next to chrome() rather than in the checkout section because the two
    are alternatives: anything added to the nav has to be considered here too.
    """
    return f"""<header class="co-nav">
  <div class="wrap co-nav-in">
    <a class="nav-brand" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
    <div class="co-nav-r">
      <span class="co-secure">{_ico("lock", 15, "ico", stroke=True)}<span>Secure checkout</span></span>
      <span class="co-nav-sep" aria-hidden="true"></span>
      <a class="co-help" href="/support.html">{_ico("life", 15, "ico", stroke=True)}<span>Need a hand?</span></a>
    </div>
  </div>
</header>"""


def foot_min():
    """The legal strip a bare page keeps.

    The handoff draws no footer at all and the nav links are gone for good
    reason — but terms, privacy and the refund policy have to stay reachable
    from the screen where money changes hands, so they survive as one quiet
    line rather than as the four-column footer.
    """
    links = "".join('<a href="%s">%s</a>' % (h, esc(l)) for h, l in FOOT_LEGAL)
    return f"""<footer class="co-foot">
  <div class="wrap co-foot-in">
    <span>© {D.YEAR} {esc(D.BRAND)}</span>
    <nav class="co-foot-links" aria-label="Legal">{links}</nav>
  </div>
</footer>"""


def chrome_guides():
    """The guides page's reduced header — design_handoff_free_guides.

    A lead-capture page with five nav items is a page with five exits, so this
    strips the promo bar, the mega menu and the currency switcher exactly like
    checkout's `chrome_min()`. What is kept is different, though: not a padlock
    and a help link, but a status line ("Free guides · no payment") and one way
    back to the thing this page is a funnel for — boosting. The green
    book glyph matches the page's own accent, and "Guides" is still in every
    other page's nav, which is how a visitor reaches this one.
    """
    return f"""<header class="gd-nav">
  <div class="wrap gd-nav-in">
    <a class="nav-brand" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
    <div class="gd-nav-r">
      <span class="gd-nav-tag">{_ico("book", 15, "ico gd-nav-tag-ico", stroke=True)}<span>Free guides · no payment</span></span>
      <span class="gd-nav-sep" aria-hidden="true"></span>
      <a class="gd-nav-back" href="/games">{_ico("arrow", 15, "ico", stroke=True)}<span>Browse boosting</span></a>
    </div>
  </div>
</header>"""


TRUSTPILOT_URL = getattr(D, "TRUSTPILOT_URL", "")
DISCORD_URL = getattr(D, "DISCORD_URL", "")

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


# Reply-time clauses. Identical copy to before; they only shorten when
# HIDE_PLACEHOLDER_CLAIMS removes the measured figure, so the sentence stays
# grammatical rather than reading "median  last month".
reply_claim = (" — median %s last month" % esc(D.STATS["reply"])
               if D.STATS.get("reply") else "")
reply_month = (": %s" % esc(D.STATS["reply"])) if D.STATS.get("reply") else ""


def rating_ld():
    """`aggregateRating` for JSON-LD — `{}` unless a real rating exists.

    Search engines render this as star ratings in results, so an invented value
    here is a fabricated review signal published to every crawler — which is
    exactly why the booster profiles emit `Person`/`ProfilePage` and no rating
    at all. The same rule has to hold here: `STATS["trustpilot"]` and
    `STATS["reviews"]` are computed from `REVIEW_DIST`, which is invented, so
    "is STATS populated?" was never the question — it always is.

    The gate is `TRUSTPILOT_URL`, the signal the badge and the reviews page
    already use for "this rating is ours and checkable". While it is empty the
    figures still render on the page as marketing copy, but nothing is asserted
    to a crawler as structured data; the moment a real profile is wired up, the
    rating starts emitting with no code change. Fabricated review markup is a
    manual-action risk, and it is the one claim on the site a crawler acts on
    directly.
    """
    if not TRUSTPILOT_URL:
        return {}
    if not D.STATS.get("trustpilot") or not D.STATS.get("reviews"):
        return {}
    return {"aggregateRating": {
        "@type": "AggregateRating",
        "ratingValue": D.STATS["trustpilot"].split("/")[0].strip(),
        "reviewCount": D.STATS["reviews"].replace(",", ""), "bestRating": "5"}}


def trustpilot_badge(label="Excellent"):
    """Clickable Trustpilot rating badge linking to the external review page.

    Renders nothing without a real rating in STATS — the badge puts Trustpilot's
    name and logo behind whatever score it is given, so it must never be built
    from a placeholder.

    The count is `trustpilot_reviews`, not `reviews`: the site's corpus is
    Trustpilot plus the order-page rating, and only the Trustpilot part of it
    may be counted under Trustpilot's logo.
    """
    if not D.STATS.get("trustpilot") or not D.STATS.get("trustpilot_reviews"):
        return ""
    rating = D.STATS["trustpilot"].split("/")[0].strip()
    try:
        fill = float(rating) / 5.0
    except ValueError:
        fill = 1.0
    _tp_id[0] += 1
    stars = _tp_stars_svg(fill, "tpclip%d" % _tp_id[0])
    aria = ("%s rating on Trustpilot from %s reviews — read reviews on Trustpilot"
            % (D.STATS["trustpilot"], D.STATS["trustpilot_reviews"]))
    logo = ('<span class="tp-brand"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            '<path d="M12 2l2.6 6.8H22l-6 4.5 2.3 7L12 15.9 5.7 20.3 8 13.3 2 8.8h7.4z" '
            'fill="#00b67a"/></svg>Trustpilot</span>')
    inner = (f'{logo}{stars}'
             f'<span class="tp-meta"><span class="tp-word">{esc(label)}</span> '
             f'<b>{esc(D.STATS["trustpilot"])}</b> · {esc(D.STATS["trustpilot_reviews"])} reviews</span>')
    # Unlinked until D.TRUSTPILOT_URL names our own profile — a badge that sends
    # the buyer to another brand's page is worse than one that doesn't click.
    if not TRUSTPILOT_URL:
        return f'<span class="tp-badge tp-badge-flat">{inner}</span>'
    return (f'<a class="tp-badge" href="{esc(TRUSTPILOT_URL)}" target="_blank" '
            f'rel="noopener nofollow" aria-label="{esc(aria)}">{inner}</a>')


def reviews_all_link():
    """The "read all" link beside the badge in the reviews section head.

    Goes to Trustpilot only once D.TRUSTPILOT_URL names *our* profile — the
    same rule the badge above follows, for the same reason. Until then it goes
    to this site's own reviews page, which holds the same feed unfiltered.
    Wrapping the words in their own <span> keeps them a whole text node, which
    is what i18n.js matches on.
    """
    if TRUSTPILOT_URL:
        return (f'<a class="rv-all" href="{esc(TRUSTPILOT_URL)}" target="_blank" rel="noopener nofollow">'
                f'<span>Read all on Trustpilot</span>'
                f'{_ico("arrow-up-right", 12, "rv-all-ico", stroke=True)}</a>')
    return ('<a class="rv-all" href="/reviews.html"><span>Read all reviews</span>'
            + _ico("arrow", 12, "rv-all-ico", stroke=True) + '</a>')


def rating_stars(n, size=14, gap=3, gold="#e0ac3e", empty="#4f4a45"):
    """One review's rating — `n` solid stars, the rest drawn empty.

    Deliberately not the aggregate treatment: `_tp_stars_svg()` clips its row
    at an arbitrary fraction to draw a 4.8, which can't render "4 of 5" as four
    stars and one outline. A single review has a whole-number rating and has to
    show the missing star, or every card reads as five.

    The gold is the site's rating gold, never Trustpilot's green — the green
    belongs to the badge in the section head and nowhere else, or an on-site
    review reads as a Trustpilot one.
    """
    N, W = 5, size
    total = N * W + (N - 1) * gap
    solid = ("M12 2l2.9 6.25 6.85.55-5.2 4.5 1.6 6.7L12 16.7 5.86 20.5l1.6-6.7"
             "L2.25 9.3l6.85-.55z")
    s = W / 24.0
    body = "".join(
        '<path d="%s" transform="translate(%d,0) scale(%.4f)" fill="%s"%s/>'
        % (solid, i * (W + gap), s, gold if i < n else "none",
           '' if i < n else ' stroke="%s" stroke-width="2.2" stroke-linejoin="round"' % empty)
        for i in range(N))
    label = "%d out of 5" % n
    return (f'<svg class="rv-stars" viewBox="0 0 {total} {W}" width="{total}" height="{W}" '
            f'role="img" aria-label="{esc(label)}">{body}</svg>')


# Footer link columns. Games follow the site-wide order (first six); Legal is
# hand-curated. Re-rank in data.py's _ORDER, not here.
FOOT_GAMES = [g["name"] for g in D.GAMES[:6]]
FOOT_LEGAL = [
    ("/legal/privacy.html", "Privacy Policy"),
    ("/legal/terms.html", "Terms of Service"),
    ("/legal/refunds.html", "Refunds & Cancellations"),
]
FOOT_SUPPORT = [
    (DEMO_HREF, "Demo", "package"),
    ("/guides.html", "Free guides", "book"),
    ("/support.html", "Help center", None),
    ("/become-a-booster.html", "Become a booster", None),
]
if not getattr(D, "GUIDES", None):
    FOOT_SUPPORT = [row for row in FOOT_SUPPORT if row[0] != "/guides.html"]
FOOT_EMAIL = "info@esportsboost.com"
# The one mailbox on the site: the footer prints it, the support page's email
# card and its copy chip carry it, and src/mailer.py sends from it and delivers
# tickets to it (SUPPORT_EMAIL there, defaulting to MAIL_FROM). A second literal
# is how a page comes to advertise an address nobody reads — so there is one.
SUPPORT_EMAIL = FOOT_EMAIL
# The handoff's one hard rule about the support card's status line: "Online now"
# has to reflect real support availability, and if support is offline the dot
# and the label change rather than lying. There is no availability feed to read,
# so this is the seam — flip it, or wire it to one, and the card degrades to the
# median reply time instead of claiming somebody is at the keyboard. The 24/7
# heading above it is the promise this line is a live read-out of; if that stops
# being true, that copy changes too.
FOOT_SUPPORT_ONLINE = True
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


def foot_pay():
    """The bottom bar's payment strip.

    The handoff draws a generic card glyph plus PayPal, Apple, Google and BTC
    marks. Only the first two survive, for the reason pay_glyphs() gives at the
    foot of the order card: PayPal was removed from checkout and crypto is still
    "coming soon", so their marks in the footer would advertise two methods the
    buyer cannot use — and the handoff's own Fidelity note says the card glyph
    is a placeholder until the schemes' licensed artwork arrives. Card plus a
    wallet is what serve.py actually takes.
    """
    return (f'<span class="ft-pay">{_ico("lock", 14, "ico ft-pay-lock", stroke=True)}'
            f'{_ico("card", 17, "ico", stroke=True)}'
            f'{_ico("wallet", 17, "ico", stroke=True)}'
            f'<span class="sr-only">Card, Apple Pay and Google Pay accepted — '
            f'payments secured by Stripe</span></span>')


def foot_status():
    """Support-card status line. See FOOT_SUPPORT_ONLINE."""
    if FOOT_SUPPORT_ONLINE:
        return ('<span class="ft-sc-status"><span class="dot-live dot-ok" aria-hidden="true"></span>'
                '<span>Online now</span></span>')
    reply = D.STATS.get("reply")
    return ('<span class="ft-sc-status ft-sc-away"><span class="ft-sc-dot" aria-hidden="true"></span>'
            '<span>Typical reply</span>%s</span>'
            % (' <b>%s</b>' % esc(reply) if reply else ""))


def footer():
    """The site's directory — design_handoff_footer, band 2.

    Four columns: brand + contact + socials + the publisher disclaimer, the
    games, Support over Legal, and the support card. Then a bottom bar carrying
    the copyright, the payment marks and the two locale switchers.

    Load-bearing:

    - **The support card and the closing band's "Talk to support" are one
      destination.** The handoff is explicit that they are two entries to one
      thing; wiring them apart is how a live-chat rollout ends up with half its
      traffic on a contact form.
    - **The disclaimer sits under the socials, not under the logo.** It is legal
      text, and the handoff makes it the quietest thing on the page on purpose —
      at the top of the column it dominates the brand.
    - **"All N games" counts the catalogue**, so adding a game to data.py can
      never leave the footer advertising the wrong number.
    - **Socials are the four channels that exist.** The handoff draws six and
      says outright to replace them with the real set, because a tile linking
      nowhere is worse than one fewer tile.
    - **The brand lockup is the site's shard, not the handoff's lightning
      bolt** — the nav and the footer have to be the same mark.
    """
    games = "".join(
        '<li><a href="/games/%s.html">%s</a></li>' % (BY_NAME[n]["slug"], esc(n))
        for n in FOOT_GAMES if n in BY_NAME
    )
    # The accounts board, under the titles it sells for. Dropped with the board
    # itself when nothing is in stock — the same guard NAV makes, so the footer
    # can never advertise a page the build did not produce.
    accounts_link = ('<li><a href="%s">%s</a></li>' % (ACCOUNTS_HREF, esc("LoL accounts"))
                     if D.accounts_in_stock() else "")
    support = "".join(
        '<li><a href="%s">%s%s</a></li>'
        % (h, _ico(ico, 15, "ico ft-link-ico", stroke=True) if ico else "",
           '<span>%s</span>' % esc(l))
        for h, l, ico in FOOT_SUPPORT
    )
    legal = "".join('<li><a href="%s"><span>%s</span></a></li>' % (h, esc(l))
                    for h, l in FOOT_LEGAL)
    # Socials are hidden until the accounts behind them are real. The handoff's
    # own note says to replace its six tiles with the channels that exist, for
    # the reason a tile linking to a bare facebook.com/ is worse than one fewer
    # tile: it reads as an account, and the click proves there isn't one. Every
    # entry in _SOCIAL still points at a platform root rather than a page, so
    # the whole block renders nothing. Fill in the real URLs and it comes back —
    # `_SOCIAL` is the only thing to edit, and only entries with a real path are
    # drawn. Discord is deliberately NOT here: it is a live server, and it is
    # reached from the homepage card, the boosters strip and the support page.
    live_social = {n: v for n, v in _SOCIAL.items()
                   if v[0].startswith("http") and len(v[0].split("://", 1)[1].split("/", 1)) > 1
                   and v[0].split("://", 1)[1].split("/", 1)[1].strip("/")}
    social = "".join(
        '<a class="ft-social" href="%s" aria-label="%s" title="%s"%s>%s</a>'
        % (href, esc(name), esc(name), ' target="_blank" rel="noopener noreferrer"'
           if href.startswith("http") else "", svg)
        for name, (href, svg) in live_social.items()
    )
    social_block = ('<div class="ft-soc"><span class="ft-lab">Follow along</span>'
                    '<div class="ft-soc-row">%s</div></div>' % social) if social else ""
    return f"""<footer class="ft">
  <div class="wrap ft-in">
    <div class="ft-grid">
      <div class="ft-brand">
        <a class="nav-brand ft-mark" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
        <div class="ft-mail">
          <span class="ft-lab">Questions? Email us at</span>
          <a class="ft-mail-a" href="mailto:{FOOT_EMAIL}">{_ico("envelope", 15, "ico ft-mail-ico", stroke=True)}{FOOT_EMAIL}</a>
        </div>
        {social_block}
        <p class="ft-disclaimer">{esc(FOOT_DISCLAIMER)}</p>
      </div>

      <nav class="ft-col" aria-label="Games">
        <h2 class="ft-head">Games</h2>
        <ul class="ft-list">{games}{accounts_link}
          <li><a class="ft-all" href="/games"><span>All <b>{len(D.GAMES)}</b> games</span>{_ico("arrow", 13, "ico", stroke=True)}</a></li>
        </ul>
      </nav>

      <div class="ft-col ft-col-2">
        <nav aria-label="Support">
          <h2 class="ft-head">Support</h2>
          <ul class="ft-list">{support}</ul>
        </nav>
        <nav aria-label="Legal">
          <h2 class="ft-head">Legal</h2>
          <ul class="ft-list">{legal}</ul>
        </nav>
      </div>

      <div class="ft-sc">
        <div class="ft-sc-text">
          <div class="ft-sc-head">
            <span class="ft-sc-tile">{_ico("headset", 18, "ico", stroke=True)}</span>
            <span class="ft-sc-t">
              <span class="ft-sc-title">24/7 Customer Support</span>
              {foot_status()}
            </span>
          </div>
          <p class="ft-sc-copy">Need help? Our support team is available anytime to assist you with your orders and questions.</p>
        </div>
        <div class="ft-sc-btns">
          <a class="ft-sc-btn ft-sc-btn-1" href="/support.html">{_ico("chat", 15, "ico", stroke=True)}<span>Let's chat</span></a>
          <a class="ft-sc-btn" href="/support.html"><span>Visit help center</span></a>
        </div>
      </div>
    </div>

    <hr class="ft-rule">
    <div class="ft-bottom">
      <span class="ft-copy">© {D.YEAR} {esc(D.BRAND)}. All Rights Reserved.<!--
        The registered address rides in the copyright cell rather than as a
        fourth footer column: it is the one piece of chrome that has to be on
        every page for the e-commerce regs, and it belongs beside the entity
        it identifies. It is data, so it is one node and stays as written —
        the legal pages print the same D.company_lines(). -->
        <span class="ft-addr">{esc(D.company_address())}</span></span>
      <div class="ft-bottom-r">
        {foot_pay()}
        <span class="ft-bottom-div" aria-hidden="true"></span>
        <div class="ft-loc">{locale_switcher()}</div>
      </div>
    </div>
  </div>
</footer>"""


def _canon(path):
    """The public (clean) URL for a built file path.

    Files are written at `.html` paths (that is where they live), but Vercel's
    `cleanUrls` serves `/foo.html` at `/foo` and `/dir/index.html` at `/dir`,
    and the `.html` forms 308-redirect to those. `vercel.json` sets
    `trailingSlash: false`, so the slashed form of a directory page 308s too
    (`/games/` -> `/games`) — the clean form carries NO trailing slash, and the
    root `/` is the one exception. So every URL a crawler reads as
    authoritative — canonical, og:url, sitemap, JSON-LD `url`/`item`/`@id` — must
    be the clean form, or it points Google at a redirect and the canonical the
    served page advertises no longer matches its own address. Internal `href`s
    may stay `.html` (they redirect once and land on the same clean page); the
    indexing signals may not."""
    if path == "/index.html":
        return "/"
    if path.endswith("/index.html"):
        path = path[:-len("/index.html")]            # /boosters/index.html -> /boosters
    elif path.endswith(".html"):
        path = path[:-len(".html")]                  # /foo.html -> /foo
    return path.rstrip("/") or "/"                   # /games/ -> /games, / -> /


def _indexable(path):
    """Which built pages Google should index. Deliberately narrow — only the
    homepage, the games catalogue and the nine game pages. Everything else is
    served and crawlable but carries `noindex` and stays out of the sitemap:
    the 88 booster profiles and the roster are invented people, /demo is a
    fabricated order, and the trust/legal pages are not worth ranking while the
    site's data is placeholder. This is the "accueil + jeux" launch footprint;
    widen it the day the data is real (see the placeholder-data note in
    data.py)."""
    p = _canon(path)
    if p in ("/", "/games"):
        return True
    if p.startswith("/games/"):
        rest = p[len("/games/"):]
        return rest != "" and "/" not in rest        # /games/<slug>, one level deep
    return False


def layout(path, title, desc, body, current=None, jsonld=None, og_image=None,
           mobile_bar=False, extra_js="", nav_outline=False, bare=False,
           head=None, foot=None, body_class=None):
    ld = ""
    for block in (jsonld or []):
        ld += '<script type="application/ld+json">%s</script>\n' % json.dumps(block, ensure_ascii=False)
    bar = ""
    if mobile_bar:
        # The persistent quote on the phone — the `design_handoff_sticky_checkout_bar`
        # port. The configurator is ~1000px tall, so whatever the buyer changes is a
        # number that scrolls off-screen; the bar keeps cause and effect in one view.
        # It is the ONLY filled button on the page (the card drops its own CTA below
        # 1000px), and every figure is a `data-out` the card already fills — two
        # formatters producing one number is how the label and the total drift apart.
        #
        # The handoff's structure: an accent hairline; a price row whose left column
        # stacks the money over a one-line meta (ETA · config, the config truncating)
        # with the tall CTA spanning both on the right; then a small assurance row.
        # Its own home-indicator is mock chrome — a real page uses the safe-area
        # inset instead (see .mobile-bar in site.css).
        #
        # Deviation, deliberate: the handoff specifies `position: sticky`, but this
        # site ships the bar as `position: fixed` — the handoff's own "one thing that
        # will break this" is a clipping-overflow ancestor silently killing sticky,
        # and fixed is immune to it, produces the identical layered result, and is the
        # site's established pattern. Nothing else about the design changes.
        bar = f"""<div class="mobile-bar" aria-label="Live quote">
  <div class="mb-hair" aria-hidden="true"></div>
  <div class="mb-top">
    <div class="mb-left">
      <div class="mb-money" aria-live="polite">
        <span class="mb-price" data-out="price">—</span>
        <span class="mobile-was" data-when-discount data-out="was" hidden></span>
        <span class="mb-save" data-when-discount hidden><span>Save</span> <b data-out="saveAmt"></b></span>
      </div>
      <span class="mb-meta">
        {_ico("clock-countdown", 12, "mb-ico", stroke=True)}<span class="mb-eta" data-out="eta">—</span>
        <span class="mb-dot" aria-hidden="true">·</span>
        <span class="mb-cfg" data-out="summary">—</span>
      </span>
    </div>
    <a class="btn btn-primary mb-cta" href="/checkout.html" data-continue>
      <span data-hide-service="coaching">Checkout</span><span data-when-service="coaching" data-out="bookLabel" hidden></span>{_ico("arrow", 15, "ico", stroke=True)}
    </a>
  </div>
  <div class="mb-assure">
    <span class="mb-as">{_ico("lock", 11, "mb-ico", stroke=True)}<span>Secure checkout</span></span>
    <span class="mb-as-div" aria-hidden="true"></span>
    <span class="mb-as">{_ico("shield-check", 11, "mb-ico", stroke=True)}<span>Money-back guarantee</span></span>
  </div>
</div>"""
    # `bare` strips the page to brand + padlock + help and drops the footer to a
    # legal line. Set on the pay flow only: its one job is finishing, so it
    # offers no exits. The body class carries the warmer checkout ground so the
    # header and footer match the section between them.
    # `head`/`foot`/`body_class` let a page supply its own chrome without joining
    # the bare/pay-flow family — the guides landing uses a reduced header of its
    # own (chrome_guides) but keeps its own warm ground rather than checkout's.
    head = head if head is not None else (chrome_min() if bare else chrome(current, nav_outline))
    foot = foot if foot is not None else (foot_min() if bare else footer())
    body_cls = ' class="%s"' % body_class if body_class else (' class="co-page"' if bare else "")
    og_image = og_image or img("/assets/img/og-default.svg")
    canonical = D.SITE + _canon(path)
    # Launch footprint: only the homepage, the catalogue and the game pages are
    # indexed. Everything else stays crawlable (follow) but out of the index —
    # `follow` so link equity still reaches the pages that do rank.
    robots_meta = ("" if _indexable(path)
                   else '<meta name="robots" content="noindex, follow">\n')
    # `no-js` is stripped by the first line of the document. It is the only hook
    # site.css has for the header's scripting-off fallback: with it, the mega
    # menus open on :hover / :focus-within, so the nav still reaches nine games
    # and the roster without JS. app.js runs at the foot of the body, far too
    # late to clear it — hence the inline script rather than a class app.js
    # removes on load.
    #
    # THREE icon links, and the order is the contract. The SVG alone is what
    # shipped, and it left `/favicon.ico` a 404 — which matters because Google
    # crawls a favicon with a *different* crawler from Googlebot, against a
    # cache that refreshes far more slowly than a page does. The redesign's
    # title and description went live in the SERP within days while the
    # previous site's logo sat next to them, because the only path to the new
    # mark was a page crawl. The root .ico is the one Google re-requests on its
    # own, so it is first; a browser that understands SVG takes the second and
    # ignores it. iOS reads neither and needs the third.
    #
    # The .ico / apple-touch PNG are NOT under /assets/ on purpose: vercel.json
    # serves that prefix `immutable` for a year, which is right for a URL that
    # carries a content hash and a trap for an icon whose URL never changes.
    # At the root they get the default must-revalidate. The SVG stays where it
    # is and gets av()'d instead — same fix, the other way round. All three are
    # rasterised from art.favicon() by tools/make_icons.py; re-run it when the
    # mark changes.
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
<script>document.documentElement.classList.remove('no-js')</script>
<meta charset="utf-8">
{_gads_head()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots_meta}<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(D.BRAND)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{D.SITE}{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#06060a">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="{av('/assets/img/favicon.svg')}" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/assets/fonts/inter-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/inter-600-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{av('/assets/css/ashfall.css')}">
<link rel="stylesheet" href="{av('/assets/css/site.css')}">
<link rel="stylesheet" href="{av('/assets/css/type-b-sans.css')}">
{ld}</head>
<body{body_cls}>
<a class="btn btn-secondary btn-sm" href="#main" style="position:absolute;left:-9999px" onfocus="this.style.left='12px';this.style.top='12px';this.style.zIndex='99'" onblur="this.style.left='-9999px'">Skip to content</a>
{head}
<main id="main">
{body}
</main>
{foot}
{bar}
<script src="{av('/assets/js/data.js')}"></script>
<script src="{av('/assets/js/i18n.js')}"></script>
<script src="{av('/assets/js/app.js')}"></script>
<script src="{av('/assets/js/analytics.js')}" defer></script>
{extra_js}</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════
#  blocks
# ══════════════════════════════════════════════════════════════════════════
# Inline single-path icons for the order card and the hero trust row. Drawn
# here rather than pulled from an icon font: the handoff specifies Phosphor,
# but this build ships no third-party runtime and every other glyph on the site
# (social, Trustpilot, payment) is already an inline <svg>. Same shapes, one
# less request. `_ico()` returns a 24-grid path at whatever size the slot wants.
_ICONS = {
    "shield": "M12 2.6 4.6 5.5v6c0 4.4 3.1 8.1 7.4 9.9 4.3-1.8 7.4-5.5 7.4-9.9v-6z",
    "ghost": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4m0 3.6a2.9 2.9 0 1 1 0 5.8"
              " 2.9 2.9 0 0 1 0-5.8m0 13.2a7 7 0 0 1-5.1-2.2c1.1-1.7 3-2.8 5.1-2.8s4 1.1 5.1"
              " 2.8a7 7 0 0 1-5.1 2.2"),
    "globe": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4m6.3 8.3h-3a14 14 0 0 0-1.5-5.8"
              " 7.4 7.4 0 0 1 4.5 5.8M12 4.7c.9 1.3 1.7 3.5 1.9 6.4h-3.8c.2-2.9 1-5.1 1.9-6.4"
              "M5.7 11.1a7.4 7.4 0 0 1 4.5-5.8 14 14 0 0 0-1.5 5.8zm0 1.8h3a14 14 0 0 0 1.5 5.8"
              " 7.4 7.4 0 0 1-4.5-5.8M12 19.3c-.9-1.3-1.7-3.5-1.9-6.4h3.8c-.2 2.9-1 5.1-1.9 6.4"
              "m1.8-.6a14 14 0 0 0 1.5-5.8h3a7.4 7.4 0 0 1-4.5 5.8"),
    "info": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4m-.4 4a1.2 1.2 0 1 1 0 2.4"
             " 1.2 1.2 0 0 1 0-2.4M13 17h-.6a1.2 1.2 0 0 1-1.2-1.2v-3.4h-.6a.8.8 0 0 1 0-1.6h.6"
             "a1.2 1.2 0 0 1 1.2 1.2v3.4h.6a.8.8 0 0 1 0 1.6"),
    "arrow": "M4.4 12h15.2m-6-6 6 6-6 6",
    # Drawn only on links that leave the site — the review section's Trustpilot
    # link when D.TRUSTPILOT_URL names a profile.
    "arrow-up-right": "M7.4 16.6 16.6 7.4M9.2 7.4h7.4v7.4",
    "lock": "M7.4 10.4V7.6a4.6 4.6 0 0 1 9.2 0v2.8M5.6 10.4h12.8v9.2H5.6z",
    "check": "M4.8 12.4 9.5 17l9.7-10",
    # Clears a filter. Never a close button — nothing on this site opens a
    # dialog that an × would dismiss.
    "x": "M6.4 6.4 17.6 17.6M17.6 6.4 6.4 17.6",
    "card": "M3.2 6.4h17.6v11.2H3.2zM3.2 10h17.6M6.2 14.4h3.4",
    "wallet": "M3.4 7.6h14.4a2 2 0 0 1 2 2v6.8a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2zM15.8 11.8h4.8v3.4h-4.8z",
    "eye-off": ("M2.6 12S6 5.6 12 5.6c1.5 0 2.8.4 4 1M21.4 12s-3.4 6.4-9.4 6.4c-1.5 0-2.8-.4-4-1"
                "M9.9 9.9a3 3 0 0 0 4.2 4.2M3.6 3.6l16.8 16.8"),
    "bolt": "M13.4 2.4 4.6 13.2h5.6l-.6 8.4 8.8-10.8h-5.6z",
    "arrow-down": "M12 4.4v15.2m-6-6 6 6 6-6",
    "user": "M12 3.4a4.2 4.2 0 1 1 0 8.4 4.2 4.2 0 0 1 0-8.4M4.2 20.2a8.2 8.2 0 0 1 15.6 0",
    "users": ("M9 4.2a3.8 3.8 0 1 1 0 7.6 3.8 3.8 0 0 1 0-7.6M2.2 19.8a7.2 7.2 0 0 1 13.6 0"
              "M16.4 4.6a3.8 3.8 0 0 1 0 7.2M18 13.4a7.2 7.2 0 0 1 3.8 6.4"),
    # Knocked-out glyphs — the inner shape is a hole, so these are painted with
    # fill-rule="evenodd" rather than relying on the arc winding.
    "play": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4"
             "M9.9 8.1 16.5 12 9.9 15.9Z"),
    "seal": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4"
             "M10.8 16.2 6.5 11.9 8 10.4l2.8 2.8 5.2-5.2 1.5 1.5Z"),
    "star": "M12 3.1 14.7 9l6.4.6-4.9 4.3 1.5 6.3L12 16.9l-5.7 3.3 1.5-6.3L2.9 9.6 9.3 9Z",
    # Scalloped seal, check knocked out — the applied-discount mark. Same
    # evenodd painting as "seal"/"play"; "seal" is the plain check-circle.
    "badge": ("M12 2.4l2.4 1.7 2.9-.1.9 2.8 2.4 1.7-1 2.7 1 2.7-2.4 1.7-.9 2.8-2.9-.1L12 21.6"
              "l-2.4-1.7-2.9.1-.9-2.8-2.4-1.7 1-2.7-1-2.7 2.4-1.7.9-2.8 2.9.1z"
              "M10.7 15.9 7.4 12.6l1.5-1.5 1.8 1.8 4.4-4.4 1.5 1.5z"),
    # ── checkout linework ────────────────────────────────────────────────
    "life": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M12 8.2a3.8 3.8 0 1 0 0 7.6"
             " 3.8 3.8 0 0 0 0-7.6M5.5 5.5 9.3 9.3M18.5 5.5 14.7 9.3M18.5 18.5 14.7 14.7"
             "M5.5 18.5 9.3 14.7"),
    "clock": "M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M12 6.9v5.4l3.7 2.2",
    "tag": ("M3.8 11.7V4.6a.9.9 0 0 1 .9-.9h7.1l8.4 8.4-8 8z"
            "M8.4 7.5a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4"),
    "undo": "M9.6 6.2 5.2 10.6l4.4 4.4M5.2 10.6h8.9a5 5 0 0 1 0 10h-3.3",
    # ── live feed / roster / safety linework ─────────────────────────────
    "dot": "M12 4.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15",
    "caret-right": "M9.4 5.2 16.2 12l-6.8 6.8",
    "hourglass": ("M7 3.6h10M7 20.4h10M7.8 3.6v3.1c0 1.1.5 2.2 1.4 2.9l2.8 2.4 2.8-2.4"
                  "a3.8 3.8 0 0 0 1.4-2.9V3.6M7.8 20.4v-3.1c0-1.1.5-2.2 1.4-2.9l2.8-2.4"
                  " 2.8 2.4a3.8 3.8 0 0 1 1.4 2.9v3.1"),
    "crosshair": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M12 2.8v4.6M12 16.6v4.6"
                  "M2.8 12h4.6M16.6 12h4.6"),
    # Generic speech bubble — the Discord tile's mark. Not Discord's logo; same
    # trademark rule as pay_marks() and the Trustpilot star.
    "chat": ("M4.4 5.4h15.2v10.2H9.8l-4 3.6a.4.4 0 0 1-.7-.3v-3.3H4.4z"
             "M8.4 10.5h7.2"),
    # ── dashboard section linework ───────────────────────────────────────
    "list-search": ("M3.6 5.4h11.6M3.6 10.2h7.2M3.6 15h5.2M16.4 11.6a3.6 3.6 0 1 0 0 7.2"
                    " 3.6 3.6 0 0 0 0-7.2M19.1 17.3l2.6 2.6"),
    "pause-circle": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4"
                     "M10.2 8.8v6.4M13.8 8.8v6.4"),
    # The same badge drawn to be FILLED: the bars are real rects, so fill-rule
    # evenodd knocks them out of the disc. `pause-circle` above is stroke-only —
    # its bars are zero-width lines, which have no area to subtract, so filling
    # it paints a solid dot and the glyph stops reading as pause at all.
    "pause-badge": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4"
                    "M9.9 8.5h1.7v7H9.9zM12.4 8.5h1.7v7h-1.7z"),
    "pause": "M9.4 5.4v13.2M14.6 5.4v13.2",
    "receipt": ("M5.6 3.4h12.8v17.2l-2.6-1.7-2.6 1.7-2.6-1.7-2.4 1.7z"
                "M9 8.4h6M9 12.4h6"),
    # Screen with the play mark knocked out — the demo-dashboard link. Filled,
    # so the stand is its own subpath and the triangle is a hole (evenodd).
    "monitor": ("M3.2 4.4h17.6v12H3.2z"
                "M10.3 8.1 14.9 10.4 10.3 12.7Z"
                "M8.6 18.2h6.8v1.6H8.6z"),
    # ── demo page linework (design_handoff_track_order) ──────────────────
    # "arrow" mirrored — the resolved order's way back to the lookup. Drawn
    # rather than CSS-flipped so it sits on the same 24-grid as its sibling and
    # never inherits a transform from whatever it is nested in.
    "arrow-left": "M19.6 12H4.4m6-6-6 6 6 6",
    # "It never expires" — a lemniscate, two mirrored loops off the crossing.
    "infinity": ("M12 12c-1.6 2.4-2.9 3.6-4.6 3.6a3.6 3.6 0 0 1 0-7.2c1.7 0 3 1.2 4.6 3.6"
                 "m0 0c1.6-2.4 2.9-3.6 4.6-3.6a3.6 3.6 0 0 1 0 7.2c-1.7 0-3-1.2-4.6-3.6"),
    # Paper plane — the "link sent" notice. Linework: the outline plus the
    # fold, which is what reads as a plane rather than as a quadrilateral.
    "send": "M21.4 2.6 2.6 10.9l7.6 2.9 2.9 7.6zM10.2 13.8 21.4 2.6",
    # ── boosters roster + profile linework ───────────────────────────────
    # The vetting funnel's three mechanism lines, then the profile's badges.
    "chart-up": "M3.6 19.4h16.8M6.4 15.6l4-4.4 3.2 2.8 5.4-6.4M15.4 6.6h4.2v4.2",
    "plug": ("M8.6 3.6v4M13.4 3.6v4M6.4 7.6h9.2v3.2a4.6 4.6 0 0 1-4.6 4.6"
             "a4.6 4.6 0 0 1-4.6-4.6zM11 15.4v5"),
    "camera": "M3.4 6.6h11.2v10.8H3.4zM14.6 11.2l6-3.4v8.4l-6-3.4",
    "badge-id": ("M3.2 5.4h17.6v13.2H3.2zM9 12.4a2.3 2.3 0 1 1 0-4.6 2.3 2.3 0 0 1 0 4.6"
                 "M5.4 16.4a4.2 4.2 0 0 1 7.2 0M15 9.6h3.4M15 13.2h3.4"),
    "filter": "M3.4 5.4h17.2l-6.6 7.6v6.2l-4-2.4v-3.8z",
    # A single chevron pair — the profile breadcrumb's separator is a glyph, not
    # a slash, so it never reads as part of a page name.
    "chevron-right": "M9.6 6.4 15.2 12l-5.6 5.6",
    # ── final CTA + footer linework (design_handoff_footer) ───────────────
    "envelope": "M3.4 6.2h17.2v11.6H3.4zM3.4 6.6 12 13l8.6-6.4",
    "package": ("M12 3.1 20.5 7.7v8.6L12 20.9 3.5 16.3V7.7zM3.7 7.8 12 12.3l8.3-4.5"
                "M12 12.3v8.6M7.7 5.4l8.4 4.6"),
    "headset": ("M4.7 14.3v-2.5a7.3 7.3 0 0 1 14.6 0v2.5M4.7 12.8h1.5a1.4 1.4 0 0 1 1.4 1.4v3"
                "a1.4 1.4 0 0 1-1.4 1.4h-.1a1.4 1.4 0 0 1-1.4-1.4zM19.3 12.8h-1.5"
                "a1.4 1.4 0 0 0-1.4 1.4v3a1.4 1.4 0 0 0 1.4 1.4h.1a1.4 1.4 0 0 0 1.4-1.4z"
                "M19.3 17.6v.7a2.8 2.8 0 0 1-2.8 2.8H12"),
    # ── booster avatar marks (D.FACE_GLYPHS) ──────────────────────────────
    # One per booster instead of the first letter of their handle. Drawn as
    # linework in the same 24-box as every other glyph here, so a face is just
    # _ico(name, …, stroke=True) and inherits the same weight and joins. Eight
    # of the seventeen are icons this file already had (sword, knight,
    # shield-chevron, trophy, crosshair, target, bolt, headset) — these nine
    # are the additions. Reproductions of nothing: generic arcade shapes, the
    # same trademark rule pay_marks() and the Trustpilot star follow.
    "gamepad": ("M9.1 7.2h5.8a5.9 5.9 0 0 1 5.8 4.9l.7 4.1a2.7 2.7 0 0 1-5 1.8l-1.2-1.9H8.8"
                "l-1.2 1.9a2.7 2.7 0 0 1-5-1.8l.7-4.1a5.9 5.9 0 0 1 5.8-4.9Z"
                "M7.7 10.6v3.2M6.1 12.2h3.2M15.4 11.4h.01M17.6 13.4h.01"),
    "joystick": ("M12 3.4a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2M12 9.6v4.8"
                 "M4.6 20.6l2.2-4.9a1.5 1.5 0 0 1 1.4-.9h7.6a1.5 1.5 0 0 1 1.4.9l2.2 4.9Z"),
    # A plus alone reads as "add" — the hub circle is what makes it a d-pad.
    "dpad": ("M9.4 3.6h5.2v5.8h5.8v5.2h-5.8v5.8H9.4v-5.8H3.6V9.4h5.8Z"
             "M12 9.6a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8"),
    "d20": ("M12 2.6 20.4 7.4v9.2L12 21.4 3.6 16.6V7.4ZM12 2.6l5.6 8.6L12 15.8 6.4 11.2Z"
            "M6.4 11.2 3.6 16.6M17.6 11.2l2.8 5.4M12 15.8v5.6"),
    "skull": ("M18.6 17.4A8 8 0 1 0 5.4 17.4v2.2a1.6 1.6 0 0 0 1.6 1.6h10a1.6 1.6 0 0 0 1.6-1.6Z"
              "M7.6 12.4a1.9 1.9 0 1 0 3.8 0 1.9 1.9 0 1 0-3.8 0M12.6 12.4a1.9 1.9 0 1 0 3.8 0"
              " 1.9 1.9 0 1 0-3.8 0M9.6 18v3.2M14.4 18v3.2"),
    "rocket": ("M12 2.6c3.4 2.6 5.2 6.2 5.2 10l-2.3 3H9.1l-2.3-3c0-3.8 1.8-7.4 5.2-10Z"
               "M12 9.4a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2M7.1 13.6 4.6 16.3l.5 3.4 3.2-1.5"
               "M16.9 13.6l2.5 2.7-.5 3.4-3.2-1.5M10.3 19.6 12 21.7l1.7-2.1"),
    "flame": ("M12 21.4a6.2 6.2 0 0 0 6.2-6.2c0-5-4-7.4-6.2-12.6-2.2 5.2-6.2 7.6-6.2 12.6"
              "a6.2 6.2 0 0 0 6.2 6.2ZM12 21.3a2.9 2.9 0 0 0 2.9-2.9c0-2.3-1.9-3.5-2.9-5.9"
              "-1 2.4-2.9 3.6-2.9 5.9a2.9 2.9 0 0 0 2.9 2.9Z"),
    "potion": ("M9.4 3h5.2M10.6 3v5.6L6 16.3a3.5 3.5 0 0 0 3 5.3h6a3.5 3.5 0 0 0 3-5.3"
               "l-4.6-7.7V3M7.6 14.6h8.8"),
    "crown": "M3.4 7.2 6.9 11.7 12 4.9l5.1 6.8 3.5-4.5-1.6 10.4H5ZM5.2 20.4h13.6",
    # ── safety & guarantee linework (design_handoff_safety_guarantee) ─────
    # The three refund stages, in order: reverse ("undo", above), part-done,
    # overdue. The pie's cut slice is what "pro-rated" looks like.
    "pie": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4"
            "M12 12V2.8M12 12h9.2"),
    "bell": ("M6.2 10.4a5.8 5.8 0 0 1 11.6 0v4l1.8 2.8H4.4L6.2 14.4zM9.8 19.6a2.4 2.4 0 0 0 4.4 0"
             "M3 7.2a7.4 7.4 0 0 1 2.2-3.4M21 7.2a7.4 7.4 0 0 0-2.2-3.4"),
    # The disclaimer plate's mark. Deliberately a caution glyph in its own
    # muted amber, never the brand accent — this paragraph is an admission.
    "warn": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M12 7.2v5.6"
             "M12 15.4a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2"),
    # Shield with a check inside — the Guarantee promise. "shield" is the
    # filled crest the hero trust row uses; this one is linework, so it reads
    # as informational beside the other two promise glyphs rather than as a
    # second badge.
    "shield-check": ("M12 2.6 4.6 5.5v6c0 4.4 3.1 8.1 7.4 9.9 4.3-1.8 7.4-5.5 7.4-9.9v-6z"
                     "M8.6 11.8 11 14.2l4.4-4.4"),
    # The accordion's own state marks. `aria-expanded` carries the state for
    # assistive tech; these are aria-hidden decoration.
    "plus": "M12 5.6v12.8M5.6 12h12.8",
    "minus": "M5.6 12h12.8",
    # ── site header linework (design_handoff_site_header) ─────────────────
    # The handoff specifies Phosphor for all of these; drawn here for the same
    # reason as everything above — this build ships no icon font.
    "copy": ("M8.4 8.4h11.2v11.2H8.4zM15.6 8.4V4.4H4.4v11.2h4"),
    "caret": "M6.4 9.2 12 14.8l5.6-5.6",
    "eye": ("M2.6 12S6 5.6 12 5.6 21.4 12 21.4 12 18 18.4 12 18.4 2.6 12 2.6 12"
            "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6"),
    # Burger. Three rules, not a "hamburger" glyph with a title — the button
    # carries the label.
    "list": "M4 6.6h16M4 12h16M4 17.4h16",
    # ── mega-menu marks ───────────────────────────────────────────────────
    # One per menu card. Deliberately generic shapes, never the games' logos:
    # substituting real key art or a publisher's mark needs licensing, the same
    # rule pay_marks() and the Trustpilot star follow.
    "sword": ("M14.6 9.4 20.4 3.6h-3.2l-4.4 4.4M14.6 9.4l-2.8-2.8M14.6 9.4 8.2 15.8"
              "M11.8 6.6 5.4 13l-2 4.6 4.6-2 6.4-6.4M9.6 15.4l3.4 3.4M12.2 18l2.6-2.6"),
    "knight": ("M8.4 20.4h8.4v-1.8c0-4 2-5.4 2-9a5.4 5.4 0 0 0-5.4-5.4l-1-1.6-1.4 2.6-3 1.6"
               "-1.4 3.4 2.6-.6 1.4 1.6-3 3.2 1.8 1.8z"),
    "shield-chevron": ("M12 2.6 4.6 5.5v6c0 4.4 3.1 8.1 7.4 9.9 4.3-1.8 7.4-5.5 7.4-9.9v-6z"
                       "M8.4 11.6 12 8.2l3.6 3.4M8.4 15.6 12 12.2l3.6 3.4"),
    "grid": "M4 4h6.4v6.4H4zM13.6 4H20v6.4h-6.4zM4 13.6h6.4V20H4zM13.6 13.6H20V20h-6.4z",
    "trophy": ("M7.4 3.8h9.2v5a4.6 4.6 0 0 1-9.2 0zM7.4 5.4H4.6v1.4a3 3 0 0 0 3 3"
               "M16.6 5.4h2.8v1.4a3 3 0 0 1-3 3M12 13.4v3.4M8.6 20.2h6.8l-.8-3.4H9.4z"),
    "user-focus": ("M4 8V5.4a1.4 1.4 0 0 1 1.4-1.4H8M16 4h2.6A1.4 1.4 0 0 1 20 5.4V8"
                   "M20 16v2.6a1.4 1.4 0 0 1-1.4 1.4H16M8 20H5.4A1.4 1.4 0 0 1 4 18.6V16"
                   "M12 8.4a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2M8 17.4a4.6 4.6 0 0 1 8 0"),
    "briefcase": ("M3.4 7.6h17.2v11.6H3.4zM8.6 7.6V5.8a1.4 1.4 0 0 1 1.4-1.4h4"
                  "a1.4 1.4 0 0 1 1.4 1.4v1.8M3.4 12.6a19 19 0 0 0 17.2 0"),
    "lock-key": ("M5.6 10.4h12.8v9.2H5.6zM7.4 10.4V7.6a4.6 4.6 0 0 1 9.2 0v2.8"
                 "M12 13.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8M12 16.4v1.4"),
    "prohibit": "M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M5.5 5.5l13 13",
    "question": ("M12 2.8a9.2 9.2 0 1 0 0 18.4 9.2 9.2 0 0 0 0-18.4M9.2 9.4a2.8 2.8 0 1 1 3.6 3"
                 "c-.6.2-.8.7-.8 1.3v.8M12 16.4a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2"),
    "bookmark": "M6.4 3.6h11.2v16.8L12 16.6l-5.6 3.8z",
    # Open book — the guides mark. Two leaves meeting at a central spine.
    "book": ("M12 6.4C10.4 5.2 8.2 4.6 5.2 4.6v12.4c3 0 5.2.6 6.8 1.8"
             "M12 6.4c1.6-1.2 3.8-1.8 6.8-1.8v12.4c-3 0-5.2.6-6.8 1.8M12 6.4v12.6"),
    # Document with a folded corner — the "PDF, yours to keep" guarantee.
    "file": "M6.4 3.6h7.4l4.2 4.2v12.6H6.4zM13.4 3.6v4.6h4.6",
    "gear": ("M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8"
             "M19.3 13.4a7.6 7.6 0 0 0 0-2.8l2-1.4-2-3.4-2.3.9a7.6 7.6 0 0 0-2.4-1.4L14.2 3H9.8"
             "l-.4 2.3a7.6 7.6 0 0 0-2.4 1.4L4.7 5.8l-2 3.4 2 1.4a7.6 7.6 0 0 0 0 2.8l-2 1.4"
             " 2 3.4 2.3-.9a7.6 7.6 0 0 0 2.4 1.4l.4 2.3h4.4l.4-2.3a7.6 7.6 0 0 0 2.4-1.4"
             "l2.3.9 2-3.4z"),
    "sign-out": "M14.6 7.6V4.4H4.4v15.2h10.2v-3.2M10 12h10.4m-4-4 4 4-4 4",
    # The optional-account note's mark — a dashed avatar ring, drawn as four
    # arcs so the gaps are the glyph rather than a stroke-dasharray that would
    # rotate with the icon's size.
    "user-dashed": ("M6.1 4.9a9.2 9.2 0 0 1 3.4-1.9M14.5 3a9.2 9.2 0 0 1 3.4 1.9"
                    "M21 9.5a9.2 9.2 0 0 1 0 5M17.9 19.1a9.2 9.2 0 0 1-3.4 1.9"
                    "M9.5 21a9.2 9.2 0 0 1-3.4-1.9M3 14.5a9.2 9.2 0 0 1 0-5"
                    "M12 7.6a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6"
                    "M7.6 17.6a4.9 4.9 0 0 1 8.8 0"),
    # ── support page linework (design_handoff_support) ────────────────────
    # The handoff draws these in Phosphor duotone; drawn here as single-path
    # linework for the same reason as everything above — this build ships no
    # icon font. The channel-card meta glyphs, the "what to put in it" list
    # marks, and the form's helper marks.
    "timer": ("M12 21a8 8 0 1 0 0-16 8 8 0 0 0 0 16M12 9.4V13l2.8 1.8"
              "M9.6 2.8h4.8M12 2.8v2.2M18.6 6.4l1.4-1.4"),
    "clock-countdown": ("M20.9 13.4A9 9 0 1 1 12 3M12 7.6V12l3.2 1.9"
                        "M20.4 4.6l.6 3.4-3.4-.6"),
    "paperclip": ("M17.6 9.4 9.9 17a3.4 3.4 0 0 1-4.8-4.8l7.6-7.5a2.2 2.2 0 0 1 3.2 3.2"
                  "l-7.6 7.5a1.1 1.1 0 0 1-1.6-1.6l6.9-6.8"),
    "hash": "M8.6 3.8 6.8 20.2M17.2 3.8l-1.8 16.4M4.4 8.8h16M3.6 15.2h16",
    "target": ("M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7.6a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8"
               "M12 11.2a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6"),
    "image-square": ("M4.2 4.4h15.6v15.2H4.2zM4.2 15.6l4.6-4.4 3 2.9 3.9-3.8 4.1 4"
                     "M9.2 9.4a1.4 1.4 0 1 1-2.8 0 1.4 1.4 0 0 1 2.8 0"),
    "envelope-open": "M3.6 9.6 12 3.8l8.4 5.8v10.2H3.6zM3.6 9.6 12 15.2l8.4-5.6",
    "lock-simple": "M6 10.4h12v9.2H6zM8 10.4V7.6a4 4 0 0 1 8 0v2.8",
    # The open shackle — the mystery modal's "Open card C". Deliberately the
    # same body as lock-simple with the arm swung clear on the right, so the two
    # read as one object in two states rather than two different padlocks.
    "lock-open": "M6 10.4h12v9.2H6zM8 10.4V7.6a4 4 0 0 1 8 0",
}


def _ico(name, size=16, cls="ico", stroke=False, evenodd=False, sw=2):
    """One icon. Filled by default; `stroke=True` for the linework glyphs.

    `evenodd` is for the glyphs whose inner shape is a hole (play, seal) — the
    other filled icons knock theirs out with an opposite arc sweep, which a
    straight-line subpath can't do.

    `sw` is the stroke weight. It exists for the booster faces, which are drawn
    into a 38px ring rather than beside a line of text: 2 closes up the d-pad's
    hub and the skull's eyes at that size.
    """
    paint = (f'fill="none" stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" '
             'stroke-linejoin="round"') if stroke else 'fill="currentColor"'
    if evenodd:
        paint += ' fill-rule="evenodd"'
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true" focusable="false"><path d="{_ICONS[name]}" {paint}/></svg>')


# A missing glyph would draw an empty ring on every row rather than fail, so the
# cross-file contract between data.py's pool and this file's linework is checked
# at import — cheaper than shipping 78 blank avatars.
assert all(_n in _ICONS for _n in D.FACE_GLYPHS), (
    "D.FACE_GLYPHS names glyphs _ICONS has not got: %s"
    % sorted(set(D.FACE_GLYPHS) - set(_ICONS)))


# Discord's own brand mark, in Blurple — the real logo, per request. Note this
# is a trademark: before launch swap it for Discord's licensed sign-in/brand
# asset, same rule pay_marks() and the Trustpilot star follow.
_DISCORD_PATH = (
    "M20.317 4.369a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25"
    "a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0"
    " 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.058a.082.082 0 0 0 .031.057 19.9"
    " 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041"
    "-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074"
    " 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292"
    "a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225"
    " 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177"
    "-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.331c-1.183 0-2.157-1.085-2.157-2.419 0"
    "-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0"
    "c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0"
    " 1.333-.946 2.418-2.157 2.418z")


def _discord_mark(size=19, cls="ico dcd-mark"):
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true" focusable="false"><path d="{_DISCORD_PATH}" fill="#5865F2"/></svg>')


# The three objections a grey-market buyer actually has — money, control, and
# the account itself — answered where the decision is made: beside the CTA, not
# in the footer's fine print. Three, not four: they sit on one flex row that
# wraps at the hero's own measure (see .hero-h .gtee-row in site.css, which is
# why that rule is NOT a 2-column grid — a fourth item made the second row a
# lone cell beside a gap).
#
# Each line restates a claim the site already makes somewhere else, and none of
# them is an outcome promise: the VPN is a mechanism, not a guarantee that no
# account is ever actioned — the game pages' honesty plate is the one place that
# subject gets argued, and it must not be contradicted here.
# Icons in this row are filled, not stroked. Any whose inner shape is a hole
# has to say so — see _ico()'s `evenodd`.
_GTEE_EVENODD = {"pause-badge"}

GUARANTEES_INLINE = (
    ("shield", "Money-back until a booster is assigned"),
    ("pause-badge", "Pause it anytime"),
    ("globe", "VPN matched to your region"),
)


def guarantee_row():
    return '<div class="gtee-row">%s</div>' % "".join(
        f'<span class="gtee">{_ico(ico, 16, "gtee-ico", evenodd=(ico in _GTEE_EVENODD))}'
        f'{esc(txt)}</span>'
        for ico, txt in GUARANTEES_INLINE)


_CARET = ('<svg class="ob-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" '
          'focusable="false"><path d="M2 3.6 5 6.6 8 3.6" fill="none" stroke="currentColor" '
          'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')

# The two-headed caret on a rank plate's selector row. A plain down-caret reads
# as "opens a menu below"; this one says the value moves in both directions,
# which is what a tier list is.
_CARET_UD = ('<svg class="ob-updown" width="12" height="14" viewBox="0 0 12 14" aria-hidden="true" '
             'focusable="false"><path d="M3.2 5.4 6 2.6 8.8 5.4M3.2 8.6 6 11.4 8.8 8.6" '
             'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>')

# The rank emblem — a winged orb, drawn once and tinted per tier.
#
# Riot's (and every other publisher's) tier emblems are their IP, so the mark is
# hand-drawn, the same rule pay_marks() and the Trustpilot star follow. Nothing
# here carries a colour: each shape is mixed off `--tier` in CSS (.ob-em-* in
# site.css), which app.js already sets on the plate through data-rankcolor — so
# the emblem tints itself for all nine ladders with no per-game code and can
# never drift from the mark colours the rest of the site draws. The `fill`
# presentation attributes are the fallback for a browser with no color-mix().
_EMBLEM = (
    '<svg class="ob-em" viewBox="0 0 44 24" aria-hidden="true" focusable="false">'
    '<g class="ob-em-wing" fill="#5d5852">'
    '<path d="M16.8 8.6 Q10.4 2.8 3 3.4 Q6.1 8.2 13.7 12.2 Z"/>'
    '<path d="M15.4 13.2 Q9.2 10.4 2.2 12.2 Q6.3 15.5 14 16.8 Z"/></g>'
    '<g class="ob-em-wing" fill="#5d5852" transform="translate(44,0) scale(-1,1)">'
    '<path d="M16.8 8.6 Q10.4 2.8 3 3.4 Q6.1 8.2 13.7 12.2 Z"/>'
    '<path d="M15.4 13.2 Q9.2 10.4 2.2 12.2 Q6.3 15.5 14 16.8 Z"/></g>'
    '<circle class="ob-em-outer" cx="22" cy="12" r="7" fill="#4a4642"/>'
    '<circle class="ob-em-inner" cx="22" cy="12" r="5.1" fill="#8d8781"/>'
    '<circle class="ob-em-glow" cx="20.2" cy="10.1" r="1.7" fill="#ffffff" opacity=".85"/>'
    '</svg>')


def rule():
    return '<div class="wrap"><hr class="rule"></div>'


def sec_kicker(num, label):
    return (f'<span class="sec-kicker"><span class="sec-kicker-n">{num}</span>'
            f'<span class="sec-kicker-l">{esc(label)}</span></span>')


def sec_head(num, label, heading, note=None, right=None, right_html=None):
    aside = ""
    if note:
        aside = '<p class="sec-note">%s</p>' % esc(note)
    elif right:
        aside = '<span class="kicker kicker-dim">%s</span>' % esc(right)
    elif right_html:
        aside = right_html
    return f"""<div class="sec-head">
    <div class="sec-head-copy">
      {sec_kicker(num, label)}
      <h2 class="h-sec">{heading}</h2>
    </div>
    {aside}
  </div>"""


_FLOOR_CACHE = []


def catalogue_floor():
    """The cheapest order in the catalogue — one division, on the cheapest rung
    of the cheapest game.

    Quoted through pricing.quote() like every other number on the site, so the
    closing band's fallback headline and the game pages' "cheapest single
    division" are the same claim computed the same way. 270-odd quotes, so it is
    computed once and kept.
    """
    if not _FLOOR_CACHE:
        _FLOOR_CACHE.append(min(
            quote(g["name"], g["ladder"][i], g["ladder"][i + 1])["total"]
            for g in D.GAMES for i in range(len(g["ladder"]) - 1)))
    return _FLOOR_CACHE[0]


def fc_card(gate=False):
    """The closing band's configuration summary — design_handoff_footer, the
    right column of band 1.

    Deliberately the checkout summary's shape and, more importantly, its data
    contract: `data-sum` / `data-mark` / `data-when-*` are the same hooks
    page_checkout() uses, so one render() pass fills both and the two cards
    cannot quote different money for the same order. The handoff's README asks
    for exactly that reconciliation.

    What it drops relative to checkout: the add-on receipt rows, the upsell and
    the promo field. This card is a read-back of a decision already made a
    screen earlier, not a place to change it — "Change" goes back to the
    configurator instead.

    The Climb row names both ranks — tier + mark, twice, the same object the
    live feed and the dashboard mock draw. It was the two marks alone, which on
    a ladder whose divisions all end in the same numeral read "IV → IV": the
    colour told you the tiers apart but nothing said which they were, and an
    Iron IV → Gold IV order was indistinguishable from Silver IV → Diamond IV.
    The word leads and the mark trails it, so the pair reads "Iron IV".

    It does NOT append the mode, though: checkout does that because it has no
    queue row to carry it, and this card has one — borrowing that text would
    print "Solo" twice in four rows. The unit services have no pair of marks, so
    there the row falls back to the summary sentence.
    """
    # `gate=True` is the copy that rides on a page with no configurator: it
    # ships hidden and app.js unhides it only when there is a real stored order
    # to read back, and "Change" cannot mean "#top" there — the configurator is
    # on another page, so the link follows the order's own game instead.
    gate_attr = ' data-fc-when="order" hidden' if gate else ''
    change = ('<a class="fc-change" data-game-link href="/games">Change</a>' if gate
              else '<a class="fc-change" href="#top">Change</a>')
    return f"""<aside class="fc-card"{gate_attr}>
      <div class="fc-card-head">
        <span class="fc-card-t">Your boost</span>
        {change}
      </div>
      <div class="fc-rows">
        <div class="fc-row">
          <span class="fc-lab">Game</span>
          <span class="fc-val" data-sum="game">—</span>
        </div>
        <div class="fc-row">
          <span class="fc-lab">Climb</span>
          <span class="fc-val fc-val-climb">
            <span class="fc-marks" data-when-service="division" hidden>
              <span class="fc-marks-t" data-tiername="from">—</span>
              <span class="ob-mark" data-mark="from"></span>
              {_ico("arrow", 11, "ico fc-marks-arrow", stroke=True)}
              <span class="fc-marks-t is-to" data-tiername="to">—</span>
              <span class="ob-mark" data-mark="to"></span>
            </span>
            <span data-when-service="units" data-sum="summary" hidden>—</span>
          </span>
        </div>
        <div class="fc-row">
          <span class="fc-lab">Queue · Server</span>
          <span class="fc-val"><span data-sum="mode">—</span><i aria-hidden="true">·</i><span data-sum="region">—</span></span>
        </div>
        <div class="fc-row fc-row-off" data-when-discount hidden>
          <span class="fc-lab-off">{_ico("tag", 14, "ico")}<b data-out="promoCode">—</b></span>
          <span class="fc-val-off" data-sum="discount">—</span>
        </div>
      </div>
      <div class="fc-fade" aria-hidden="true"></div>
      <div class="fc-tot">
        <div class="fc-tot-l">
          <span class="fc-lab">Total, tax included</span>
          <span class="price-pair">
            <span class="fc-was" data-when-discount data-sum="was" hidden></span>
            <span class="fc-total" data-sum="total">—</span>
          </span>
        </div>
        <span class="fc-mb">{_ico("shield", 14, "ico")}<span>Money-back guarantee</span></span>
      </div>
    </aside>"""


def cta_band(live=False, title=None, sub=None, cta=("Configure your boost", "/games"),
             readback=True):
    """The last ask — design_handoff_footer, band 1.

    The premise of the handoff: by the time someone reaches the bottom of the
    page they have usually already touched a configurator, so the close is
    *their* order at *their* price, not a generic "get started". `live=True`
    says this page owns a configurator (the two that do: the homepage and the
    game pages), and the band renders the configuration line, the live price and
    the summary card beside it.

    `live=False` is the handoff's documented fallback for a page with nothing to
    read back: no card, the headline quotes the catalogue minimum, and one CTA
    back to the configurator. The handoff describes this state but does not draw
    it — it is flagged for the designer.

    `readback=True` (the default) ships the live version alongside it, hidden,
    for the visitor who HAS configured something. The order is kept per game and
    shared site-wide (see app.js's keyFor), so a page with no configurator of its
    own can still close on their climb rather than on the catalogue floor —
    which is what the handoff's premise asks for, and what "not a fabricated
    default" was protecting: this appears only when there is a real stored order
    behind it. The server always renders the FALLBACK visible, because a static
    page is cached for everybody and cannot know; app.js swaps them, so with no
    JS the band is still correct. Both states are in the DOM for the
    whole-text-node i18n rule.

    Pass `readback=False` where the band is not an order close — the support
    page's "Still stuck? Ask us." is asking a different question.

    Scoped on `.hero-a` rather than redeclaring the handoff palette: this band
    and the two heroes are the same design, so `.btn-primary`, `.grad-text` and
    the `--h-*` text colours all resolve to the handoff's ember for free. It is
    the warmest glow on the site (.26 against .13–.22 elsewhere), deliberately,
    because it is the final ask.
    """
    # The read-back half — the live price, the climb line, the card and the two
    # order buttons. Shared verbatim by `live=True` and by the hidden copy a
    # `readback` band carries, so the two can never drift into quoting the same
    # order two ways.
    gate = '' if live else ' data-fc-when="order" hidden'
    live_head = ('Your climb starts at '
                 '<span class="grad-text" data-out="price">—</span>')
    live_lede = ("Final at checkout. Refunded in full until a booster claims it, "
                 "pro-rated after that.")
    live_config = f"""<div class="fc-config"{gate}>
        <span class="fc-pair" data-when-service="division" hidden>
          <span class="fc-rank" data-rankcolor="from" data-out="fromRank">—</span>
          {_ico("arrow", 13, "ico fc-arrow", stroke=True)}
          <span class="fc-rank fc-rank-to" data-rankcolor="to" data-out="toRank">—</span>
          <span class="fc-div" aria-hidden="true"></span>
          <span class="fc-queue">{_ico("user", 14, "ico", stroke=True)}<span data-out="mode">—</span></span>
        </span>
        <span class="fc-unit" data-when-service="units" data-out="summary" hidden>—</span>
      </div>"""
    live_buttons = (f'<a class="btn btn-primary" href="/checkout.html" data-continue{gate}>'
                    f'<span>Continue your order</span>{_ico("arrow", 15, "ico", stroke=True)}</a>'
                    f'<a class="btn btn-secondary" href="/support.html"{gate}>'
                    f'{_ico("chat", 17, "ico fc-b2-ico", stroke=True)}<span>Talk to support</span></a>')

    if live:
        # The price, the card total and the struck list price are three
        # assertions of one number; all three come off the same render() pass.
        head, config, buttons = live_head, live_config, live_buttons
        lede = esc(sub or live_lede)
        card = fc_card()
        solo, mark = False, ""
    else:
        floor_head = (esc(title) if title else
                      'Your climb starts at <span class="grad-text">%s</span>'
                      % money(catalogue_floor()))
        floor_lede = esc(sub or ("Set two ranks and the price is on screen before you sign up. "
                                 "No account, no quote request."))
        floor_btn = ('<a class="btn btn-primary" href="%s"%s><span>%s</span>%s</a>'
                     % (cta[1], ' data-fc-when="none"' if readback else '',
                        esc(cta[0]), _ico("arrow", 15, "ico", stroke=True)))
        # The card starts hidden either way, so the band opens in its one-column
        # layout; app.js drops `fc-solo` when it unhides the card.
        solo = True
        if readback:
            head = ('<span data-fc-when="none">%s</span>'
                    '<span data-fc-when="order" hidden>%s</span>' % (floor_head, live_head))
            lede = ('<span data-fc-when="none">%s</span>'
                    '<span data-fc-when="order" hidden>%s</span>'
                    % (floor_lede, esc(live_lede)))
            config, buttons, card = live_config, floor_btn + live_buttons, fc_card(gate=True)
            mark = " data-fc-readback"
        else:
            head, lede, config, buttons, card, mark = floor_head, floor_lede, "", floor_btn, "", ""
    return f"""<section class="hero-a hero-a-lit fc{' fc-solo' if solo else ''}"{mark}>
  <div class="fx fc-glow" aria-hidden="true"></div>
  <div class="fx hero-a-hatch" aria-hidden="true"></div>
  <div class="wrap fc-inner">
    <div class="fc-copy">
      {config}
      <h2 class="fc-h">{head}</h2>
      <p class="fc-lede">{lede}</p>
      <div class="fc-cta">{buttons}</div>
    </div>
    {card}
  </div>
</section>"""


def marquee():
    if not D.MARQUEE:
        return ""
    run = "".join('<span>%s</span><i aria-hidden="true">◆</i>' % esc(m) for m in D.MARQUEE)
    return f"""<div class="marquee" aria-hidden="true">
  <div class="marquee-track">
    <span class="marquee-run">{run}</span>
    <span class="marquee-run">{run}</span>
  </div>
</div>"""


# The plain `cards-3` copy of D.GUARANTEES retired with the old /games/ page:
# every surface that draws the three promises now uses promise_cards(), which
# adds the icon tile and the proof line. One shell, so /games/ and
# /guarantee.html cannot render the same three promises two ways.


def steps_block():
    steps = "".join(f"""<div class="step">
      <span class="step-n">{n}</span>
      <div>
        <div class="step-t">{esc(t)}</div>
        <p class="t-14" style="margin:0;color:var(--text-3);line-height:1.7">{esc(b)}</p>
      </div>
    </div>""" for n, t, b in D.STEPS)
    return '<div class="steps">%s</div>' % steps


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("_ _ twenty thirty forty fifty sixty seventy eighty ninety").split()


def spell(n):
    """Small cardinal in words, for headings that count the catalogue.

    The handoff's "Nine ladders. Forty services." is called out as a figure that
    must be generated rather than typed — the catalogue actually carries 37
    services, and a heading that rounds up is the kind of claim nobody notices
    going stale. Falls back to digits past 99, where words stop helping.
    """
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    return str(n)


def services_of(g):
    """A game's services as a list. `data.py` stores them as one `·` run for the
    prose contexts; the grid needs them as separate chips."""
    return [s.strip()[:1].upper() + s.strip()[1:]
            for s in g["services"].split("·") if s.strip()]


def games_grid():
    """The catalogue section — the "Games grid" handoff.

    It answers one question ("do you cover my game?") and routes into the right
    configurator. The layout is a hierarchy rather than a uniform grid: the lead
    game takes a 2×2 featured tile, two more take double-width, the rest are
    single cells — which is exactly what `D.TILE_ORDER` already encodes, so the
    shape of this section is data, not markup.

    What the redesign fixed, and why each is easy to undo by accident:
      · **art and copy no longer collide.** Key art used to bleed into the
        titles — Valorant, Marvel Rivals and TFT all had a wordmark sitting on
        the card title. Art now has a reserved zone with a gradient veil at its
        base, so the two occupy separate bands;
      · **the tiles read as clickable** — each ends in a price and a circular
        arrow, and the border lifts to accent on hover. Nothing said so before;
      · **services became chips.** A 12px dot-separated run wrapped badly; pills
        scan and wrap cleanly;
      · **the price is a labelled figure**, not a pill floating in a corner
        (and "From$5" had lost its space);
      · **the overflow tile joined the system** — same shell, names the games it
        stands for, and carries a real action instead of a bare link;
      · **the 01–06 corner numbers are gone.** They implied an order the grid
        does not have.
    """
    # TILE_ORDER carries the old presentation classes; read them as size intent
    # so the data file does not have to learn this section's class names.
    def size(span):
        return "gg-feat" if "2x2" in span else ("gg-wide" if "span-2" in span else "gg-sm")

    tiles = []
    for slug, span in D.TILE_ORDER:
        g, cls = BY_SLUG[slug], size(span)
        feat = cls == "gg-feat"
        chips = "".join('<span class="gg-chip">%s</span>' % esc(s) for s in services_of(g))
        # The lead tile's badge is a claim about order volume that nothing in
        # data.py measures — same standing as STATS. Drop this line rather than
        # let it ship unverified.
        badge = (f'<span class="gg-badge">{_ico("bolt", 11, "ico")}'
                 f'<span>Most ordered</span></span>') if feat else ""
        go = (f'<span class="gg-go-l">Configure</span>' if feat else "")
        # The featured tile's zone is 252px and takes the full-height art; every
        # other zone is 78px and takes the band crop, which is the same scene
        # rendered at 1200×300 so the wordmark survives the crop.
        src, dims = (("keyart-%s.svg" % slug, (1200, 700)) if feat
                     else ("band-%s.svg" % slug, (1200, 300)))
        tiles.append(f"""<a class="gg-tile {cls}" href="/games/{slug}.html">
      <span class="gg-art">
        <img src="{img("/assets/img/" + src)}" alt="" width="{dims[0]}" height="{dims[1]}" loading="lazy">
        <span class="gg-veil" aria-hidden="true"></span>
        {badge}
      </span>
      <span class="gg-body">
        <span class="gg-title">{esc(g['name'])}</span>
        <span class="gg-chips">{chips}</span>
        <span class="gg-foot">
          <span class="gg-price"><span class="gg-from">From</span><span class="gg-fig">{money(from_price(g))}</span></span>
          <span class="gg-go">{go}<span class="gg-arrow" aria-hidden="true">{_ico("arrow", 14, "ico", stroke=True)}</span></span>
        </span>
      </span>
    </a>""")

    # The overflow tile counts itself. Hard-coding "+3" against a nine-game
    # catalogue is exactly how this tile goes stale.
    rest = [g for g in D.GAMES if g["slug"] not in dict(D.TILE_ORDER)]
    if rest:
        names = [g["name"] for g in rest]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        # Names outside the translatable node — i18n.js matches whole text nodes,
        # so a generated list interpolated into the sentence could never match.
        tiles.append(f"""<a class="gg-tile gg-more" href="/games">
      <span class="gg-more-top">
        <span class="gg-more-n">+{len(rest)}</span>
        <span class="gg-more-t"><b>{esc(joined)}</b> <span>are live too.</span></span>
      </span>
      <span class="gg-more-btn"><span>All games</span>{_ico("arrow", 14, "ico", stroke=True)}</span>
    </a>""")
    return '<div class="gg-grid">%s</div>' % "".join(tiles)


# `game_cards()` — the flat nine-tile grid — retired with the old /games/ page.
# The catalogue is `gc_catalog()` now (filterable, sortable, priced, with the
# service list on the card); the homepage keeps its own hierarchy in
# `games_grid()`. Two grids, two jobs, neither a copy of the other.


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


def tier_mark(game, tier, label, strong=False, wide=False, base="lf-mark"):
    """One tinted rank mark — the same object the configurators draw.

    Colour comes from D.tier_color() against that game's own ladder, so the
    feed and the game page can never tint the same rank differently. `strong`
    is the destination end (a heavier border), `wide` is for a rating value
    (CS2's Premier numbers) that needs more than a division numeral's width.

    `base` swaps the class prefix for a section that sizes its marks
    differently (the review cards) — one component, two sizes, never two
    implementations that can disagree about a colour.
    """
    c = D.tier_color(game, tier) if game else "#8e8f94"
    cls = base + (" is-to" if strong else "") + (" is-wide" if wide else "")
    return '<span class="%s" style="--tier:%s">%s</span>' % (cls, c, esc(label))


def _ago(mins):
    """"2 min ago" / "1 hr ago". Spelled out because the old "2M ago" read as
    months — the one abbreviation on the page that changed the claim."""
    if mins < 60:
        return "%d min ago" % max(1, mins)
    h = mins // 60
    return "%d hr ago" % h if h < 24 else "%d d ago" % (h // 24)


def _clock(mins, now=None):
    """Wall clock of a delivery, in the server's own zone. Server-rendered so
    the row says something without JS; app.js re-derives both this and the
    relative label on a timer once it loads."""
    t = (now or datetime.now()) - timedelta(minutes=mins)
    return t.strftime("%H:%M")


def live_feed():
    """Delivered today — a chronological list, newest first.

    Was a 2×2 card grid, which destroyed the ordering of a feed whose entire
    meaning is "just now". It is now a timeline: a rail with the newest entry
    carrying the accent dot and the warm timestamp, a real time column
    (relative and clock), and the climb drawn with the same tinted marks the
    configurators use rather than as plain text.

    Rows are deliberately NOT clickable: the handoff routes them at a public
    delivery receipt, and this site has no such page. Its own instruction for
    that case is to drop the caret and the pointer rather than ship a dead
    control. Same reason there is no "See the full feed" link beside the count.
    """
    if not D.LIVE_FEED:
        return ""
    now = datetime.now()
    rows = ""
    for i, f in enumerate(D.LIVE_FEED):
        g = BY_SLUG.get(f["slug"])
        wide = bool(f.get("rating"))
        # A rating ladder prints the number in the mark and writes the ladder's
        # name out once, on the destination side; a tier ladder prints the
        # division numeral (or the tier's first two letters when it has none)
        # and names the tier on both sides.
        def side(key, strong):
            tier, div = f[key]
            label = div or tier[:2].upper()
            name = "" if wide else tier
            return (('<span class="lf-tier">%s</span>' % esc(name) if name else "")
                    + tier_mark(g, tier, label, strong=strong, wide=wide))
        rating_name = ('<span class="lf-tier is-to">%s</span>' % esc(f["rating"])) if wide else ""
        mins = f["mins"]
        rows += f"""<li class="lf-row">
        <span class="lf-when">
          <span class="lf-ago" data-mins="{mins}">{esc(_ago(mins))}</span>
          <span class="lf-clock" data-mins="{mins}">{esc(_clock(mins, now))}</span>
        </span>
        <span class="lf-rail" aria-hidden="true"><i class="lf-dot"></i></span>
        <span class="lf-climb">
          <span class="lf-letter" aria-hidden="true">{esc(g['short'] if g else (f.get('initial') or '?'))}</span>
          <span class="lf-climb-in">{side('frm', False)}{_ico("arrow", 12, "lf-arrow", stroke=True)}{side('to', True)}{rating_name}</span>
        </span>
        <span class="lf-game">
          <span class="lf-game-n">{esc(g['name'] if g else f['slug'])}</span>
          <span class="lf-region">{esc(f['region'])}</span>
        </span>
        <span class="lf-by">
          <span class="lf-booster">{esc(f['booster'])}</span>
          <span class="lf-done">{_ico("seal", 11, "lf-done-ico", evenodd=True)}Delivered</span>
        </span>
      </li>"""
    # The figure is its own node: i18n.js matches whole text nodes, so a number
    # interpolated into a translatable sentence silently un-translates it.
    foot = ('<div class="lf-foot"><span><b>%s</b> orders closed in the last 24 hours</span></div>'
            % esc(D.STATS["closed_24h"])) if D.STATS.get("closed_24h") else ""
    return f"""<div class="lf">
      <ul class="lf-list">{rows}</ul>
      {foot}
    </div>"""


def roster_card(rows):
    """On shift now — the rail's first card.

    The hierarchy used to be inverted: win rate was the loud orange figure and
    availability was 9px fine print. Availability is the thing a buyer acts on,
    so it is the status pill now and win rate is a labelled secondary figure.
    Each row also carries its one game, because "Immortal 8.4k" alone doesn't
    say which ladder you are looking at.

    Rows open that booster's profile. They used to land on an anchor inside the
    roster table because no such page existed; it does now, and this card, the
    roster and the profile all read one BOOSTERS entry, so the three can never
    quote different numbers for the same person.
    """
    body = ""
    for b in rows:
        g = BY_SLUG.get(b.get("slug"))
        free = b["queue"] == "free"
        pill = ('<span class="rc-pill%s">%s%s</span>' %
                ("" if free else " is-busy",
                 _ico("dot", 9, "rc-pill-ico") if free
                 else _ico("hourglass", 10, "rc-pill-ico", stroke=True),
                 esc("Free" if free else b["queue"])))
        chip = ('<span class="rc-chip">%s</span>' % esc(g["short"])) if g else ""
        # The ring's colour carries availability; what sits inside it is the
        # booster's own mark — see booster_face(), shared with the roster board
        # and the track-order card so one person is one face everywhere.
        face = booster_face(b, cls="rc-initial")
        body += f"""<li><a class="rc-row" href="{booster_href(b)}">
        <span class="rc-ring{'' if free else ' is-busy'}">{face}</span>
        <span class="rc-who">
          <span class="rc-name">{esc(b['handle'])}{chip}</span>
          <span class="rc-rank">{esc(b['peak_full'])}</span>
        </span>
        <span class="rc-state">
          {pill}
          <span class="rc-wr"><b>{esc(b['wr'])}</b> win rate</span>
        </span>
      </a></li>"""
    n = D.STATS["online"]
    return f"""<div class="rc">
      <div class="rc-head">
        <span class="rc-title"><span class="dot-live dot-ok" aria-hidden="true"></span>On shift now</span>
        <span class="rc-count"><b>{n}</b> boosters</span>
      </div>
      <ul class="rc-list">{body}</ul>
      <a class="rc-all" href="/boosters"><span>Pick your booster</span>{_ico("arrow", 14, "ico", stroke=True)}</a>
    </div>"""


def discord_card():
    """The rail's second card. Was an uppercase heading over a centred text
    link; it now has a mark, a sentence-case heading and a real button."""
    d = getattr(D, "DISCORD", None)
    if not d or not D.STATS.get("discord"):
        return ""
    return f"""<div class="dcd">
      <div class="dcd-head">
        <span class="dcd-tile">{_discord_mark(19)}</span>
        <span class="dcd-titles">
          <span class="dcd-title"><b>{esc(D.STATS['discord'])}</b> in the Discord</span>
          <span class="dcd-label">{esc(d['label'])}</span>
        </span>
      </div>
      <p class="dcd-body">{esc(d['body'])}</p>
      <a class="dcd-cta" href="{esc(d['href'])}" target="_blank" rel="noopener noreferrer">{esc(d['cta'])}{_ico("arrow", 14, "ico", stroke=True)}</a>
    </div>"""


def roster_panel(rows=None):
    """The right rail: who is on shift, then the Discord.

    Nobody on shift renders no roster card, never an empty one — but the rail
    still wraps whatever is left, because `.rail` is where the section's local
    tokens are declared and a bare Discord card outside it would lose them.
    """
    if rows is None:
        # Default rail: interleave the two biggest ladders so the card reads as a
        # mixed roster (LoL + Valorant) rather than five League rows in a row.
        lol = [b for b in D.BOOSTERS if b.get("slug") == "league-of-legends"]
        val = [b for b in D.BOOSTERS if b.get("slug") == "valorant"]
        mixed = [b for pair in zip(lol, val) for b in pair]
        rows = (mixed or D.BOOSTERS)[:5]
    inner = (roster_card(rows) if rows else "") + discord_card()
    if not inner:
        return ""
    return '<aside class="rail" id="boosters">%s</aside>' % inner


def safety_block():
    """The banned-account objection, answered in prose with the mechanisms
    pulled out beside it.

    The kicker used to sit alone in an empty left column with the heading and
    the prose pushed right; it now sits above the heading, and the column it
    freed carries the proof: the recovery figure as a callout, then the four
    mechanisms as scannable lines. Those lines restate the paragraphs — they
    are labels, not additional claims, which is why they live in the same
    SAFETY entry as the copy they summarise.
    """
    S = D.SAFETY
    prose = "".join("<p>%s</p>" % esc(p) for p in S["body"])
    proof = ""
    fig, label = S.get("callout") or ("", "")
    if fig:
        proof += (f'<div class="sf-callout"><span class="sf-fig">{esc(fig)}</span>'
                  f'<span class="sf-fig-l">{esc(label)}</span></div>')
    if S.get("mechanisms"):
        lines = "".join('<li>%s%s</li>' % (_ico(ico, 16, "sf-ico", stroke=st), esc(txt))
                        for ico, st, txt in S["mechanisms"])
        proof += '<ul class="sf-mech">%s</ul>' % lines
    if S.get("link"):
        txt, href = S["link"]
        proof += ('<a class="sf-link" href="%s">%s%s</a>'
                  % (esc(href), esc(txt), _ico("arrow", 13, "ico", stroke=True)))
    return f"""<div class="sf-grid">
      <div class="sf-prose">{prose}</div>
      <div class="sf-proof">{proof}</div>
    </div>"""


# ══════════════════════════════════════════════════════════════════════════
#  04 Dashboard — design_handoff_dashboard
# ══════════════════════════════════════════════════════════════════════════
# The thing that separates this store from a Discord DM, sold with a replica of
# itself: the mock IS the evidence for the three claims beside it, so it is
# built as a working screen at real fidelity — live rank, progress, an LP chart
# and a real match table — rather than as a decorative panel.
#
# It is a REPLICA, not the dashboard. It reads a fixture (D.DEMO_ORDER), never
# order state, and nothing inside it navigates or mutates anything — see
# dash_mock() for why the Pause / Message controls are spans.
#
# What the redesign fixed, each easy to undo by accident:
#   · the mock was illegible. The LP line ran straight through the progress bar
#     and the meta text under it, and every label was 9px condensed caps. The
#     chart now has its own bordered panel with gridlines, an area fill, a
#     "now" marker and start/now captions, and overlaps nothing;
#   · progress reads as progress — current rank on the left with its mark,
#     "N% complete" on the right, and the bar spanning the panel under both.
#     The percentage used to be buried in the rank line;
#   · the match list became a table: header row, labelled K/D/A, a replay
#     affordance per row and a "last 5 of N" summary;
#   · Win and Loss stopped sharing a colour. Both were orange, which made the
#     history unreadable at a glance. Win is green, Loss neutral, and a lost LP
#     figure is muted rather than shouting louder than the wins;
#   · the two interactive claims got their controls. "Pause on one click" and
#     "chat with the booster" are asserted in the copy, so the panel footer
#     shows the Pause and Message controls the sentences promise — claim and
#     evidence in one viewport;
#   · the four capability labels became neutral chips. They were accent
#     outlines that looked like buttons but weren't;
#   · the section ends in an action. It previously stopped dead after the
#     benefit list.
_DEMO_GAME = next((g for g in D.GAMES if g["name"] == D.DEMO_ORDER["game"]), None)


_GAME_BY_NAME = {g["name"]: g for g in D.GAMES}


def _resolve_demo(src, g):
    """A demo-order fixture with its derived figures resolved.

    Percentage, days left, the W–L record and the price are COMPUTED from the
    ranks in the fixture and the real formula, never typed. The handoff's whole
    premise is that the mock's numbers agree with each other, and a typed
    percentage drifts the moment a ladder gains a tier or a factor is retuned —
    the same property ladder_strip()'s "cheapest single division" has.

    `g` is the game the order is on: its `rank_unit` / `queue_name` decide
    whether the card reads LP / Ranked solo (League, the default) or RR /
    Competitive (Valorant), so a Valorant order never quotes League terms.

    One deliberate divergence from the drawn League mock: it reads 62% complete,
    taken against a ladder with no Emerald. On this site's ladder Gold IV →
    Platinum II is 6 of the 12 rungs to Diamond IV, so the bar reads 50%.
    """
    O = dict(src)
    rank = lambda k: (" ".join(O[k])).strip()
    O["start_rank"], O["at_rank"], O["target_rank"] = (rank("start"), rank("at"),
                                                       rank("target"))
    O["unit"] = (g.get("rank_unit") if g else None) or "LP"
    O["queue"] = (g.get("queue_name") if g else None) or "Ranked solo"
    pct = 0.0
    if g:
        L = g["ladder"]
        try:
            a, b, c = (L.index(O["start_rank"]), L.index(O["at_rank"]),
                       L.index(O["target_rank"]))
            pct = (b - a) / (c - a) if c > a else 0.0
        except ValueError:      # a fixture rank that is not on this ladder
            pct = 0.0
    # Priced WITH the fixture's add-ons, because the demo page's details rail
    # names them: a row reading "Add-ons: Champions, agents & roles" over a
    # "Paid" figure quoted without them is a hand-typed price by another route.
    addons = [a for a in list(O.get("addons") or [])
              if any(x["id"] == a and D.addon_applies(x, O["mode"]) for x in D.ADDONS)]
    O["addon_labels"] = [D.addon_label(x, O["game"]) for x in D.ADDONS if x["id"] in addons]
    q = pricing.quote({"game": O["game"], "service": "division", "from": O["start_rank"],
                       "to": O["target_rank"], "mode": O["mode"], "addons": addons})
    O["pct"] = round(pct * 100)
    # Days left follows the same quote the shop would give for this climb, so
    # "N days left" and the price on /demo.html describe one order.
    O["days"] = q["days"]
    O["days_left"] = max(1, round(q["days"] * (1 - pct)))
    O["price"] = 0 if q["invalid"] else q["total"]
    wins = sum(1 for m in O["matches"] if m["result"] == "Win")
    O["record"] = "%dW %dL" % (wins, len(O["matches"]) - wins)
    # The live timeline event is derived, never stored: it is the rank the card
    # above it shows, timestamped off the newest match in the table beside it.
    # Anything else and the three can disagree about the same order.
    newest = O["matches"][0]["when"] if O["matches"] else 0
    O["events"] = ([(O["at"][0], O["at"][1], _ago(newest), "live")]
                   + [(t, d, when, "done") for t, d, when in O.get("milestones", [])])
    return O


def demo_order():
    """The League demo order (D.DEMO_ORDER), resolved and cached. Used by the
    homepage mock, /demo.html, the orders page and checkout — everywhere the
    site names one concrete order."""
    if getattr(demo_order, "_v", None):
        return demo_order._v
    demo_order._v = _resolve_demo(D.DEMO_ORDER, _DEMO_GAME)
    return demo_order._v


_GAME_DEMO_CACHE = {}


def game_demo_order(g):
    """The demo order for a game page's 'While it runs' mock: the game's own
    fixture (D.GAME_DEMOS) when it has one — so Valorant shows a Valorant climb
    in RR — else the League demo_order(), which is what every game page rendered
    before. Returned with the game it belongs to, so the caller marks it right."""
    src = D.GAME_DEMOS.get(g["name"])
    if not src:
        return demo_order(), _DEMO_GAME
    if g["name"] not in _GAME_DEMO_CACHE:
        _GAME_DEMO_CACHE[g["name"]] = _resolve_demo(src, g)
    return _GAME_DEMO_CACHE[g["name"]], g


# The two SVG gradients inside the mock are referenced by id, so two panels on
# one page would both paint with the first one's stops — the bug the inlined
# game logos hit. One counter, one namespace per instance.
_DASH_N = 0


def dash_mock(example=False, live=False, gp=False, order=None, game=None):
    """The order dashboard, drawn as a static replica of the real screen.

    One component, two instances — the marketing band's and the demo page's
    resolved order — because the track-order handoff carries the same
    ProgressCard / LpChart / MatchHistory as the dashboard handoff and asks for
    them to be built once. What differs is what surrounds them:

    `example` adds the Example pill to the header strip. On the homepage the
    card is obviously illustrative; beside a lookup form, a card showing an
    order code otherwise reads as *your* order. The handoff calls this out.

    `live` is the resolved-order variant: the header strip comes off (the page
    header carries the code), and the footer says when the last game was
    instead of naming the panel — the two actions it named have moved up to the
    page header, where they belong on a live order.

    The marketing instance is inert by construction, and that is a decision
    rather than an omission. The handoff offers two ways to keep it honest —
    leave the controls visual, or make the whole panel one link to the demo
    dashboard — and this takes the first: `role="img"` puts one labelled
    illustration in the accessibility tree instead of a fake table of somebody
    else's order, and the footer's Pause / Message controls are spans, so
    nothing there is focusable or clickable. A real <button> that does nothing
    is a trap for anyone arriving by keyboard, and the section already carries
    a real way in ("Open the demo dashboard"). Hover states stay — a screenshot
    of a live product should look alive — but the pointer cursor the prototype
    puts on match rows does not, because it promises a click that never comes.

    The `live` instance drops `role="img"`: there it is the page's subject
    rather than an illustration beside an argument, so its table is meant to be
    read. The Example pill moves to the page header for the same reason.
    """
    global _DASH_N
    _DASH_N += 1
    # order/game default to the League demo — the homepage and /demo.html pass
    # nothing. The game page passes its own game's order (Valorant in RR).
    uid, O, g = "dsh%d" % _DASH_N, order or demo_order(), game or _DEMO_GAME

    def mark(pair, strong=False, small=False):
        tier, div = pair
        base = "dm-mark dm-mark-sm" if small else "dm-mark"
        return tier_mark(g, tier, div or tier[:2].upper(), strong=strong, base=base)


    # LP across the order: 13 authored points across the 588-unit box, joined
    # into the line and closed to the baseline for the area fill.
    pts = O["chart"]
    step = 588 / (len(pts) - 1)
    xy = ["%g,%g" % (round(i * step, 1), y) for i, y in enumerate(pts)]
    # Every figure in this panel sits OUTSIDE the text node beside it —
    # i18n.js matches whole trimmed nodes, so "+412 LP net" as one node could
    # never be translated, and the separators ride in aria-hidden <i>s the same
    # way spotlight_card()'s do.
    chart = f"""<div class="dm-chart">
          <div class="dm-chart-head">
            <span class="dm-lab">{O['unit']} across the order</span>
            <span class="dm-net"><i>+{O['lp_net']}</i> {O['unit']} net</span>
          </div>
          <svg class="dm-plot" viewBox="0 0 588 104" preserveAspectRatio="none" aria-hidden="true" focusable="false">
            <defs>
              <linearGradient id="{uid}a" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#ff5a1f" stop-opacity=".28"/>
                <stop offset="100%" stop-color="#ff5a1f" stop-opacity="0"/>
              </linearGradient>
              <linearGradient id="{uid}l" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="#ffb03a"/><stop offset="100%" stop-color="#ff5a1f"/>
              </linearGradient>
            </defs>
            <line x1="0" y1="26" x2="588" y2="26" stroke="rgba(255,255,255,.055)" stroke-width="1"/>
            <line x1="0" y1="60" x2="588" y2="60" stroke="rgba(255,255,255,.055)" stroke-width="1"/>
            <line x1="0" y1="94" x2="588" y2="94" stroke="rgba(255,255,255,.09)" stroke-width="1"/>
            <path d="M{' L'.join(xy)} L588,94 L0,94 Z" fill="url(#{uid}a)"/>
            <polyline points="{' '.join(xy)}" fill="none" stroke="url(#{uid}l)" stroke-width="2.5"
                      stroke-linejoin="round" stroke-linecap="round"/>
            <circle cx="588" cy="{pts[-1]}" r="4.5" fill="#ff5a1f" stroke="#131110" stroke-width="2.5"/>
          </svg>
          <div class="dm-chart-caps">
            <span class="dm-cap">{'Start' if gp else 'Order start'}<i aria-hidden="true"> · </i>{esc(O['start_rank'])}</span>
            <span class="dm-cap is-now">Now<i aria-hidden="true"> · </i>{esc(O['at_rank'])}</span>
          </div>
        </div>"""

    rows = ""
    for m in O["matches"]:
        win = m["result"] == "Win"
        rows += f"""<div class="dm-row">
            <span class="dm-champ" style="--champ:{esc(m['champ'])}"></span>
            <span class="dm-queue">{esc(O['queue'])}{_ico("play", 14, "dm-replay", evenodd=True)}</span>
            <span class="dm-res{' is-win' if win else ''}">{esc(m['result'])}</span>
            <span class="dm-kda">{esc(m['kda'])}</span>
            <span class="dm-lp{' is-up' if win else ''}">{esc(m['lp'])}</span>
          </div>"""

    pill = ('<span class="dm-example">Example</span>' if example else "")
    bar = "" if (live or gp) else f"""<div class="dm-bar">
        <span class="dm-bar-l"><span class="dm-lab">Order</span><span class="dm-id">{esc(O['id'])}</span>{pill}</span>
        <span class="dm-status"><span class="dot-live dot-ok" aria-hidden="true"></span>In progress</span>
      </div>"""
    # The footer's right cell on the resolved order is the handoff's "All 38
    # games" link to the replay view. That view does not exist, so it is not
    # drawn — same rule that keeps the live feed's rows unlinked and the roster's
    # "Load more" out of the DOM when nothing is behind it. Build the replay
    # page and the link comes back.
    if gp:
        # The game page's variant: the same live footer, plus the order's game
        # count on the right (the handoff's "38 games this order").
        mins = O["matches"][0]["when"] if O["matches"] else 0
        foot = (f"""<span class="dm-foot-l"><span class="dot-live dot-ok" aria-hidden="true"></span>Updated live<i aria-hidden="true"> · </i>last game <b class="lf-ago" data-mins="{mins}">{esc(_ago(mins))}</b></span>"""
                f"""<span class="dm-foot-r dm-foot-games"><b>{O['games']}</b> games this order</span>""")
    elif live:
        mins = O["matches"][0]["when"] if O["matches"] else 0
        foot = f"""<span class="dm-foot-l"><span class="dot-live dot-ok" aria-hidden="true"></span>Updated live<i aria-hidden="true"> · </i>last game <b class="lf-ago" data-mins="{mins}">{esc(_ago(mins))}</b></span>"""
    else:
        foot = f"""<span class="dm-foot-l"><span class="dot-live dot-ok" aria-hidden="true"></span>Order dashboard · live</span>
        <span class="dm-foot-r">
          <span class="dm-btn">{_ico("pause", 13, "ico", stroke=True)}Pause</span>
          <span class="dm-btn">{_ico("chat", 13, "ico", stroke=True)}<span>Message <i>{esc(O['booster'])}</i></span></span>
        </span>"""
    if gp:
        shell = '<div class="dm dm-open dm-gp" role="img" aria-label="Preview of the order dashboard">'
    elif live:
        shell = '<div class="dm dm-open">'
    else:
        shell = '<div class="dm" role="img" aria-label="Preview of the order dashboard">'

    # The handoff's game-page card leads each rank with its mark and carries the
    # status pill on that row (there is no order bar above it to hold one).
    if gp:
        # The header names the FULL rank beside each mark ("Gold 1 → Diamond 1"),
        # matching the progress row below it ("Platinum 2") rather than the mark +
        # tier-only pairing. The mock is a static replica, so this is plain text,
        # not a data-tiername hook.
        climb = f"""<div class="dm-climb dm-climb-gp">
          <span class="dm-climb-pair">{mark(O['start'])}<span class="dm-climb-t">{esc(O['start_rank'])}</span></span>
          {_ico("arrow", 16, "dm-climb-arrow", stroke=True)}
          <span class="dm-climb-pair">{mark(O['target'], strong=True)}<span class="dm-climb-t is-to">{esc(O['target_rank'])}</span></span>
          <span class="dm-status dm-status-gp"><span class="dot-live dot-ok" aria-hidden="true"></span>In progress</span>
        </div>"""
    else:
        climb = f"""<div class="dm-climb">
          <span class="dm-climb-t">{esc(O['start'][0])}</span>{mark(O['start'])}
          {_ico("arrow", 16, "dm-climb-arrow", stroke=True)}
          <span class="dm-climb-t is-to">{esc(O['target'][0])}</span>{mark(O['target'], strong=True)}
        </div>"""

    return f"""{shell}
      {bar}

      <div class="dm-body">
        {climb}

        <div class="dm-prog">
          <span class="dm-prog-l"><span class="dm-prog-rank">{esc(O['at'][0])}{mark(O['at'], small=True)}</span> · <b>{O['lp']} {O['unit']}</b></span>
          <span class="dm-prog-r"><b>{O['pct']}%</b> complete<i aria-hidden="true"> · </i><b>{O['days_left']}</b> days left</span>
        </div>
        <div class="dm-track"><span class="dm-fill" style="width:{O['pct']}%"></span></div>

        {chart}

        <!-- The one line here left untranslated on purpose: "Last 5 of 38
             games" carries two figures inside the sentence, and splitting it
             into fragments the way the progress line is split would fix the
             English word order onto French and German, which put the count
             elsewhere. It falls back to English, which i18n.js is built for. -->
        {'' if gp else f'''<div class="dm-hist">
          <span class="dm-hist-t">Match history</span>
          <span class="dm-hist-m">Last {len(O['matches'])} of {O['games']} games · <b>{esc(O['record'])}</b></span>
        </div>'''}
        <div class="dm-table">
          <div class="dm-row dm-head">
            <span></span><span>Queue</span><span>Result</span><span>K / D / A</span><span>{O['unit']}</span>
          </div>
          {rows}
        </div>
      </div>

      <div class="dm-foot">{foot}</div>
    </div>"""


# The things the dashboard lets you do that a DM cannot. Neutral chips, not
# accent outlines: they are facts about the order, not more buttons. Icons
# follow the site's existing mapping — globe is Regional VPN and eye-off is
# Offline appearance everywhere else on the site.
#
# "No account sharing on duo" was a fifth chip here and was removed on request.
# The claim itself is not gone and must not be re-added here casually: it is
# SAFETY["body"]'s own line, rendered by safety_block() on the homepage and as
# a named measure on /guarantee.html. This row is the dashboard's feature list,
# and that is the one entry on it that was a safety promise rather than
# something the panel does.
DASHBOARD_CHIPS = (
    ("globe", False, "Regional VPN"),
    ("eye-off", True, "Offline appearance"),
    ("receipt", True, "Pro-rated refunds"),
)


def dashboard_section(num=None, on_demo=False, note=None, cta_href="/games"):
    """The whole section: the mock, the three claims, the chips and the CTAs.

    `num` numbers the eyebrow on the homepage, where the section is 04 in a run
    of numbered sections; /how-it-works.html has no such run, so it renders the
    same block with no kicker.

    `note` is the paragraph the games-catalogue handoff draws under the heading
    ("same dashboard on all nine titles"). Only that page passes one: on the
    homepage the three benefit rows below already carry the argument, and a
    fourth block of prose there pushes the CTA out of the viewport.

    `cta_href` is where "Configure your boost" goes. It defaults to the
    catalogue because three of the four pages that render this band have no
    configurator on them, so picking a title is genuinely the next step there.
    The homepage does have one — bs_band()'s Best Sellers dock, `#calc` — and
    it passes that instead: a button labelled "Configure your boost" should
    land on a configurator, not on a page asking which game first. Any caller
    passing a fragment must own that id, or the CTA is a no-op.

    `on_demo` is the demo page's copy of the band — the handoff carries this
    section over verbatim and asks for exactly two changes there: the Example
    pill on the card, and "Open the demo dashboard" becoming a control that
    opens the order in place rather than a link to another page. It is a real
    <button> because it does a real thing; everywhere else it stays a link.
    """
    bens = "".join(f"""<div class="dsh-ben">
          <span class="dsh-ben-ico">{_ico(ico, 19, "ico", stroke=True)}</span>
          <span class="dsh-ben-c">
            <span class="dsh-ben-t">{esc(title)}</span>
            <span class="dsh-ben-b">{esc(body)}</span>
          </span>
        </div>""" for ico, title, body in D.DASHBOARD_POINTS)
    chips = "".join(f'<span class="dsh-chip">{_ico(i, 12, "ico", stroke=s)}{esc(t)}</span>'
                    for i, s, t in DASHBOARD_CHIPS)
    # The demo page with the fixture order already open — the handoff leaves "a
    # route, a modal or a video" open, and this site already has the route,
    # rendering this same order. A link that lands somewhere showing different
    # numbers would undo the section's own argument.
    demo = "%s?order=%s" % (DEMO_HREF, esc(demo_order()["id"]))
    open_demo = (
        f'<a class="dsh-demo" href="/support.html">'
        f'<span class="dot-live dot-ok dsh-demo-dot" aria-hidden="true"></span>Talk to support</a>'
        if on_demo else
        f'<a class="dsh-demo" href="{demo}">'
        f'{_ico("monitor", 18, "dsh-demo-ico", evenodd=True)}Open the demo dashboard</a>')
    return f"""<section class="section dsh{' is-demo' if on_demo else ''}" id="dashboard">
  <div class="dsh-hatch" aria-hidden="true"></div>
  <div class="dsh-glow" aria-hidden="true"></div>
  <div class="wrap dsh-grid">
    {dash_mock(example=on_demo)}
    <div class="dsh-copy">
      {sec_kicker(num, "Dashboard") if num else ""}
      <h2 class="h-sec">You watch the whole thing</h2>
      {'<p class="dsh-note">%s</p>' % esc(note) if note else ""}
      <div class="dsh-bens">{bens}</div>
      <div class="dsh-chips">{chips}</div>
      <div class="dsh-cta">
        <a class="btn btn-primary" href="{cta_href}">Configure your boost{_ico("arrow", 15, "ico", stroke=True)}</a>
        {open_demo}
      </div>
    </div>
  </div>
</section>"""


# The home hero's booster of the month, resolved once. The card and the
# portrait asset emit_art() generates have to be about the same person, and an
# unknown handle has to fail the same way in both places.
_SPOT = getattr(D, "SPOTLIGHT", None) or {}
SPOT_BOOSTER = next((b for b in D.BOOSTERS if b["handle"] == _SPOT.get("handle")), None)
SPOT_PORTRAIT = "/assets/img/portrait-%s.svg" % SPOT_BOOSTER["handle"] if SPOT_BOOSTER else ""
# Where the card's CTA goes: this booster's game with them attached, exactly
# as the roster's Hire and the profile's request card resolve it. A booster
# whose slug isn't in the catalogue falls back to the games index rather than
# a broken /games/.html — the same guard both of those use.
_SPOT_GAME = BY_SLUG.get(SPOT_BOOSTER["slug"]) if SPOT_BOOSTER else None
SPOT_HIRE = ("/games/%s.html?booster=%s" % (_SPOT_GAME["slug"], SPOT_BOOSTER["handle"])
             if _SPOT_GAME else "/games")


def spotlight_card():
    """Home hero, right column — the booster of the month in the card shell.

    This was floating text on the gradient, which read as an unfinished area.
    It is now the same surface as every other module on the site, and the one
    dot-separated string is split into two labelled figures.

    Name, game, order count and portrait come off the roster entry named by
    D.SPOTLIGHT, so this card can never quote different numbers than the
    roster panel or the boosters page. No such booster → no card: the handoff
    asks for the month with no qualifying booster to hide it, not to render an
    empty one.

    The game is named from the booster's own `slug` against the catalogue —
    same rule as the roster chip, so the card can never advertise a ladder
    this build doesn't sell. It renders the full name rather than the roster's
    `short` because there is no column to fit here, and because the card is a
    stranger's introduction: "LoL" is for a table you are already scanning.

    The CTA goes to that game's configurator with the booster attached
    (?booster=<handle>), the same destination the roster's Hire and the
    profile's "Order with <handle>" use — the label says order, so the link
    has to start one. The profile is still one tap away from the name on
    either of those pages.
    """
    if not SPOT_BOOSTER:
        return ""
    b = SPOT_BOOSTER
    g = BY_SLUG.get(b["slug"])
    game = ('<span class="spot-game">%s</span>' % esc(g["name"])) if g else ""
    stats = ""
    for i, (val, label, sub) in enumerate(_SPOT.get("stats", [])):
        if i:
            stats += '<span class="spot-rule" aria-hidden="true"></span>'
        # The suffix is data (a region) and the label is copy, so they stay
        # separate text nodes — i18n.js translates whole nodes only.
        tail = ('<i aria-hidden="true"> · </i>%s' % esc(sub)) if sub else ""
        stats += (f'<div class="spot-stat"><span class="spot-stat-v">{esc(val)}</span>'
                  f'<span class="spot-stat-l">{esc(label)}{tail}</span></div>')
    return f"""<aside class="spot">
      <div class="spot-glow" aria-hidden="true"></div>
      <div class="spot-head">
        <span class="spot-eyebrow">{esc(_SPOT.get('eyebrow', ''))}</span>
        <span class="spot-badge">{_ico("seal", 12, "ico", evenodd=True)}Verified</span>
      </div>
      <span class="spot-portrait"><img src="{img(SPOT_PORTRAIT)}" alt="" width="196" height="196" fetchpriority="high"></span>
      <span class="spot-name">{esc(b['handle'])}</span>
      {game}
      <span class="spot-meta"><span>{b['orders']}</span> orders delivered</span>
      <div class="spot-stats">{stats}</div>
      <a class="spot-cta" href="{esc(_SPOT.get('href') or SPOT_HIRE)}">{_ico("user", 15)}<span class="spot-cta-t"><span>{esc(_SPOT.get('cta', ''))}</span> <b>{esc(b['handle'])}</b></span></a>
    </aside>"""


def hero_rating():
    """Home hero proof line: the Trustpilot score, then the volume.

    Reads the same D.STATS as trustpilot_badge() and the stat band — one set
    of figures across the site. Each half is dropped when its figure is
    missing, so a build with no real rating shows the volume alone rather than
    a bare star, and a build with neither renders nothing at all.

    The green star is a stand-in. The handoff is explicit that production uses
    Trustpilot's own widget or licensed mark — and this line stays unlinked
    until D.TRUSTPILOT_URL names our own profile, same rule as the badge.
    """
    bits = []
    if D.STATS.get("trustpilot"):
        # Score only — the review count is deliberately not repeated here. It is
        # stated on /reviews.html, where the distribution backing it is drawn and
        # a sceptic can actually check it; in the hero it was a second number
        # competing with the client count beside it for the same glance.
        bits.append(
            f'{_ico("star", 15, "hero-h-star")}'
            f'<span><b>{esc(D.STATS["trustpilot"])}</b> <span>on Trustpilot</span></span>')
    if D.STATS.get("clients"):
        if bits:
            bits.append('<span class="hero-h-div" aria-hidden="true"></span>')
        bits.append('<span><b>%s</b> clients</span>' % esc(D.STATS["clients"]))
    return ('<div class="hero-h-rating">%s</div>' % "".join(bits)) if bits else ""


def booster_table(rows, note=True):
    """The plain roster table the game pages still use for their one-game
    roster. The boosters page itself has the full board — see roster_board()."""
    if not rows:
        return ""
    body = "".join(f"""<tr id="b-{esc(b['handle'])}">
        <td class="handle"><a href="{booster_href(b)}">{esc(b['handle'])}</a></td>
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


# ══════════════════════════════════════════════════════════════════════════
#  Boosters — the roster page and one profile per booster
#  design_handoff_boosters_roster
# ══════════════════════════════════════════════════════════════════════════
# Two screens, one flow: /boosters/ lists everyone on the board, and every
# row's name opens that person's own page at /boosters/<handle>.html. Fifth
# scoped port after .hero-a / .co / .gg / .dsh — tokens on `.rst` (roster) and
# `.bp` (profile), product radii per element, nothing leaking past them.
#
# What the redesign fixed, each easy to undo by accident:
#   · the page showed the SAME FIVE BOOSTERS TWICE — a rail card in the hero,
#     then the identical five rows in the table 300px below it. The rail now
#     carries the vetting funnel, which is the evidence for the H1's claim, so
#     nothing on the page appears twice and the hero's void is closed;
#   · the roster became searchable. A 34-person board with no filter is a list,
#     not a tool: game chips, availability and sort, all live, with a count that
#     reflects them;
#   · availability got loud. It was 9px grey caps in the table while the rail
#     used green/amber pills for the same fact — the table has the pills now and
#     the avatar ring is tinted to match, so scanning for someone free works;
#   · win rate became comparable. Every figure was orange — ten identical
#     accents and therefore no signal. It is neutral with a bar under it,
#     normalised across the floor the page states out loud;
#   · every row can be acted on. The old table was inert; each row now has Hire
#     and a name that opens a profile.
#
# The one thing the prototype does not decide is where Hire goes. It goes to the
# configurator with the booster attached (?booster=<handle>) — the handoff's own
# "carry that booster into the configurator as the named booster" — and the name
# link goes to the profile, so both destinations exist and neither is a guess.

ROSTER_PAGE = 12     # rows visible before "Load more". The handoff draws 8 of 34; the
                     # board is 50 now, and 8 at a time is six clicks to the bottom
WR_TOP = 85          # top of the win-rate bar's span — its zero is D.WR_FLOOR


def booster_href(b):
    return "/boosters/%s.html" % b["handle"]


def _wr_frac(b):
    """Where this win rate sits between the floor the page states and WR_TOP.

    The handoff normalises across 60–85; the floor is 62 and it is written into
    the hero paragraph, the funnel card and the table's own argument, so the
    bar's zero is that floor rather than a second, unstated number. A booster
    exactly at the floor still draws a sliver — an empty track reads as missing
    data, and nobody on this board is missing data.
    """
    span = max(1, WR_TOP - D.WR_FLOOR)
    return max(0.06, min(1.0, (b["wr_n"] - D.WR_FLOOR) / span))


def booster_face(b, px=38, lazy=True, cls="rst-initial", glyph=19):
    """What sits inside the availability ring — on the rail, the roster board
    and the track-order card, from one place, so the same person is never drawn
    two different ways.

    It used to be the first letter of the handle. That is what a face falls back
    to when there is nothing to show, and a column of nine grey letters reads as
    exactly that: nine rows of missing data, on the page whose whole argument is
    that real people are behind the orders. Each booster now wears one of
    D.FACE_GLYPHS' marks, picked from their handle and tinted with their own
    hue — the hue art.avatar() paints their profile portrait with, so the 38px
    avatar and the 96px portrait belong to the same person.

    A generated portrait is still a smudge at this size, which is why the ring
    holds a glyph and not art.avatar(). A real photograph dropped into
    assets-in/avatar/<handle> mounts inside the same ring and wins — the ring
    stays either way, because its colour is what encodes free / busy.
    """
    if drop_in("avatar/" + b["handle"]):
        return ('<img src="%s" alt="" width="%d" height="%d"%s>'
                % (img("/assets/img/avatar-%s.svg" % b["handle"]), px, px,
                   ' loading="lazy"' if lazy else ""))
    ink, plate = D.face_tint(b["handle"], b.get("hue"))
    return ('<span class="%s is-face" style="--face:%s;--face-bg:%s">%s</span>'
            % (cls, esc(ink), esc(plate),
               _ico(D.face_glyph(b["handle"]), glyph, "face-ico", stroke=True)))


def is_free(b):
    return b["queue"] == "free"


def queue_pill(b, cls="rst-pill"):
    """Free / busy, as the pill the rail card already uses. `queue` is the one
    source of truth for availability — the ring colour beside it reads the same
    field, so the two can never disagree."""
    free = is_free(b)
    ico = (_ico("dot", 9, cls + "-ico") if free
           else _ico("hourglass", 10, cls + "-ico", stroke=True))
    return ('<span class="%s%s">%s%s</span>'
            % (cls, "" if free else " is-busy", ico, esc("Free" if free else b["queue"])))


def booster_mark(b, base="rst-mark", strong=True):
    """The peak's tier mark — the same object the configurators, the live feed
    and the reviews draw, tinted through D.tier_color() against this booster's
    own game. A second colour table for this page would defeat the point of
    drawing ranks as marks at all."""
    g = BY_SLUG.get(b["slug"])
    return tier_mark(g, b["tier"], b["tier"][:2].upper(), strong=strong, base=base)


def roster_games():
    """The games actually represented on the board, in site order — never a
    hand-written chip list. A chip that filters to nobody is a dead control."""
    seen, out = set(), []
    for g in D.GAMES:
        if g["slug"] in seen:
            continue
        if any(b["slug"] == g["slug"] for b in D.BOOSTERS):
            seen.add(g["slug"])
            out.append(g)
    return out


def vetting_card():
    """The hero's right rail: how someone gets on this page.

    This slot used to preview the same five rows as the table below it. It now
    carries last month's intake, which is the evidence for the headline — the
    page's whole claim is that it doesn't self-report, so the rail has to argue
    rather than repeat.

    The figures are deliberately NOT bars: 1,840 → 96 → 11 renders the last two
    as invisible slivers, so the numbers do the work. The three rule lines
    under them restate promises the hero paragraph already makes; they are
    labels, not new claims.
    """
    V = getattr(D, "VETTING", None)
    if not V or not V.get("steps"):
        return ""
    steps = ""
    last = len(V["steps"]) - 1
    for i, (fig, label) in enumerate(V["steps"]):
        out = i == last
        glyph = (_ico("seal", 20, "vf-seal", evenodd=True) if out
                 else _ico("arrow-down", 15, "vf-arrow", stroke=True))
        steps += (f'<li class="vf-step{" is-out" if out else ""}">'
                  f'<span class="vf-fig">{esc(fig)}</span>'
                  f'<span class="vf-label">{esc(label)}</span>{glyph}</li>')
    rules = "".join('<li>%s%s</li>' % (_ico(ico, 16, "vf-rule-ico", stroke=True), esc(txt))
                    for ico, txt in V.get("rules", []))
    return f"""<div class="vf" id="vetting">
      <div class="vf-head">
        <span class="vf-title">{esc(V['title'])}</span>
        <span class="vf-window">{esc(V['window'])}</span>
      </div>
      <ol class="vf-steps">{steps}</ol>
      <div class="vf-div" aria-hidden="true"></div>
      <ul class="vf-rules">{rules}</ul>
    </div>"""


def discord_strip():
    """A strip, not a card. On this page Discord is the application channel — a
    supporting detail beside the funnel, not a headline offer.

    Every figure rides in its own <b> and the em dash in an aria-hidden <i>:
    i18n.js matches whole text nodes, so a number interpolated into a sentence
    silently un-translates the whole sentence.
    """
    d = getattr(D, "DISCORD", None)
    V = getattr(D, "VETTING", None)
    n = D.STATS.get("discord")
    if not (d and V and n and V.get("strip")):
        return ""
    pre, word, mid, tail = V["strip"]
    return f"""<div class="ds">
      {_ico("chat", 19, "ds-ico", stroke=True)}
      <span class="ds-txt">{esc(pre)} <b>{esc(word)}</b> {esc(mid)}<i aria-hidden="true"> — </i><b>{esc(n)}</b> <span>{esc(tail)}</span></span>
      <a class="ds-cta" href="{esc(d['href'])}" target="_blank" rel="noopener noreferrer">{esc(V.get('strip_cta', 'Join'))}{_ico("arrow", 12, "ico", stroke=True)}</a>
    </div>"""


def roster_hero():
    return f"""<section class="rst rst-hero">
  <div class="rst-hero-glow" aria-hidden="true"></div>
  <div class="wrap rst-hero-grid">
    <div class="rst-hero-copy">
      <span class="rst-kicker">The roster</span>
      <h1 class="rst-h1">Verified from match history, not self-reported.</h1>
      <p class="rst-lede">Every applicant is trialled live on our account before they touch
      yours: five games, watched, in the bracket they claim. Ranks on this page are read from
      the API, not typed into a form. Anyone whose win rate drops below {D.WR_FLOOR}% over a
      rolling month comes off the board until they climb it back.</p>
      <div class="rst-cta-row">
        <a class="btn btn-primary" href="/games">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
        <a class="btn btn-outline" href="/become-a-booster.html">{_ico("badge-id", 17, "ico", stroke=True)}Apply as a booster</a>
      </div>
    </div>
    <aside class="rst-hero-rail">{vetting_card()}{discord_strip()}</aside>
  </div>
</section>"""


def roster_filters():
    """Game chips, availability and sort — all three AND-combined by app.js.

    Both groups are real radio groups (arrow-key navigable, one tab stop), and
    the chips are built from roster_games() so no chip can filter to nobody.
    Ten fixture rows filter fine in the browser; a 34-row board behind
    pagination has to filter server-side, and this markup is the contract for
    it — the JS reads data-* only.
    """
    chips = ('<button type="button" class="rst-chip is-wide is-on" role="radio" '
             'aria-checked="true" data-rst-game="">All games</button>')
    for g in roster_games():
        chips += ('<button type="button" class="rst-chip" role="radio" aria-checked="false" '
                  'data-rst-game="%s">%s</button>' % (esc(g["short"]), esc(g["short"])))

    def seg(name, opts, label):
        lid = "rst-%s-l" % name
        body = ""
        for i, opt in enumerate(opts):
            body += ('<button type="button" class="rst-seg-opt%s" role="radio" aria-checked="%s" '
                     'data-rst-%s="%s">%s</button>'
                     % (" is-on" if not i else "", "true" if not i else "false",
                        name, esc(opt), esc(opt)))
        return (f'<div class="rst-fgroup"><span class="rst-flabel" id="{lid}">{esc(label)}</span>'
                f'<div class="rst-seg" role="radiogroup" aria-labelledby="{lid}">{body}</div></div>')

    return f"""<div class="rst-filters">
      <div class="rst-fgroup">
        <span class="rst-flabel" id="rst-game-l">Game</span>
        <div class="rst-chips" role="radiogroup" aria-labelledby="rst-game-l">{chips}</div>
      </div>
      <div class="rst-fright">
        {seg("avail", ["Everyone", "Free now"], "Availability")}
        {seg("sort", ["Win rate", "Free first"], "Sort by")}
      </div>
    </div>"""


def roster_row(b, i):
    """One board row. A <div>, not a button: it holds two independent targets
    (the profile link and Hire), and a clickable row would swallow the Hire
    click. Hire stays enabled when the booster is busy — the pill already says
    "2 orders", so the action queues rather than being blocked."""
    g = BY_SLUG.get(b["slug"])
    free = is_free(b)
    hire = ("/games/%s.html?booster=%s" % (g["slug"], b["handle"])) if g else "/games"
    return f"""<div class="rst-row" data-rst-row data-game="{esc(g['short'] if g else '')}"
      data-free="{1 if free else 0}" data-win="{b['wr_n']}"{' hidden' if i >= ROSTER_PAGE else ''}>
      <a class="rst-who" href="{booster_href(b)}">
        <span class="rst-ring{'' if free else ' is-busy'}">{booster_face(b)}</span>
        <span class="rst-who-t">
          <span class="rst-handle">{esc(b['handle'])}</span>
          <span class="rst-orders"><b>{b['orders']}</b> orders delivered</span>
        </span>
      </a>
      <span class="rst-game">
        <span class="rst-code">{esc(g['short'] if g else '—')}</span>
        <span class="rst-server">{esc(b['region'])}</span>
      </span>
      <span class="rst-peak">{booster_mark(b)}<span class="rst-peak-t">{esc(b['peak'])}</span></span>
      <span class="rst-wr">
        <span class="rst-wr-v">{esc(b['wr'])}</span>
        <span class="rst-wr-bar"><i style="width:{round(_wr_frac(b) * 100)}%"></i></span>
      </span>
      {queue_pill(b, "rst-pill")}
      <a class="rst-hire" href="{esc(hire)}" data-rst-hire="{esc(b['handle'])}">Hire{_ico("arrow", 12, "ico", stroke=True)}</a>
    </div>"""


def roster_board():
    """The table, its empty state and its pager.

    Rows are server-rendered sorted by win rate — the page is correct with no
    JS, and app.js only re-orders what is already here. Everything past the
    first page is `hidden`, so "Load more" reveals real rows instead of being a
    control with nothing behind it.
    """
    rows = sorted(D.BOOSTERS, key=lambda b: -b["wr_n"])
    body = "".join(roster_row(b, i) for i, b in enumerate(rows))
    total = D.STATS.get("online") or len(rows)
    shown = min(ROSTER_PAGE, len(rows))
    more = ('<button type="button" class="rst-more" data-rst-more>Load more'
            + _ico("arrow-down", 14, "ico", stroke=True) + '</button>') if len(rows) > ROSTER_PAGE else ""
    head = "".join('<span>%s</span>' % esc(t) for t in
                   ("Booster", "Game · Server", "Peak this season", "Win rate · 30d", "Queue"))
    return f"""<div class="rst-table">
      <div class="rst-head" aria-hidden="true">{head}<span></span></div>
      <div class="rst-body" data-rst-body>{body}</div>
      <div class="rst-empty" data-rst-empty hidden>
        <span class="rst-empty-h" data-rst-empty-game-h hidden>Nobody free on <b data-rst-empty-game></b> right now</span>
        <span class="rst-empty-h" data-rst-empty-any-h>Nobody free right now</span>
        <span class="rst-empty-b"><b data-rst-empty-n>0</b> <span>on the board — start the order and the first one free claims it.</span></span>
        <span class="rst-empty-cta">
          <a class="btn btn-primary btn-sm" href="/games">Order anyway</a>
          <button type="button" class="btn btn-outline btn-sm" data-rst-reset>Show everyone</button>
        </span>
      </div>
      <div class="rst-foot">
        <span class="rst-count">Showing <b data-rst-shown>{shown}</b> of <b>{esc(str(total))}</b> <span>boosters</span><i data-rst-fgame aria-hidden="true" hidden></i><span data-rst-ffree hidden><i aria-hidden="true"> · </i><span>free now</span></span></span>
        {more}
      </div>
    </div>"""


# ── one profile per booster ───────────────────────────────────────────────

def booster_history(b, n=12):
    """The profile's completed-orders table, derived — never typed out per
    person.

    Ten hand-written tables would be two hundred lines of invented rows inside
    the file that is supposed to be the single source of truth, and they would
    drift from the ladders the moment a game gains a tier. Every row here is
    computed instead, from two things that are already on the page:

      · the rank bands in `climbs` — the rail card beside this table claims
        those are the climbs this booster works, so the table has to be made of
        them or the page contradicts itself one column apart. Bands are drawn
        in proportion to their own counts, so the busiest band shows up most;
      · pricing.quote(), for the delivery time — the same trick demo_order()
        uses for the dashboard mock, so every row is a climb the shop could
        actually sell at a duration the shop would actually quote.

    Deterministic: seeded on the handle, so a rebuild renders the same table
    and two builds of one commit are identical apart from the dates. Still
    placeholder data — see the warning at the top of data.py. Every order is in
    the booster's one game, which is why the table has no game column.
    """
    g = BY_SLUG.get(b["slug"])
    if not g:
        return []

    def rot(salt, m):
        h = 2166136261
        for c in "%s#%d" % (b["handle"], salt):
            h = (h * 16777619 + ord(c)) & 0xFFFFFFFF
        return h % max(1, m)

    # One entry per delivered climb in that band, so drawing uniformly from the
    # pool reproduces the card's distribution without a weighting pass.
    pool = []
    for name, cnt in (b.get("climbs") or []):
        ends = [e.strip() for e in name.split("→")]
        if len(ends) != 2 or any(e not in g["divmap"] for e in ends):
            continue        # a band naming a tier this ladder doesn't have
        pool += [ends] * max(1, cnt)
    if not pool:
        return []

    now = datetime.now()
    # The first row is the order the "Latest review" card cites, so it is dated
    # from that review rather than from a separate count — the quote and the
    # order it names have to be the same order on the same day.
    rows, oid, back = [], 4000 + rot(0, 90), max(1, b["review"][3])
    for i in range(n):
        lo, hi = pool[rot(i * 7 + 1, len(pool))]
        frm = g["divmap"][lo][rot(i * 11 + 3, len(g["divmap"][lo]))]
        to = g["divmap"][hi][rot(i * 13 + 5, len(g["divmap"][hi]))]
        mode = "Duo" if rot(i * 17 + 7, 3) == 0 else "Solo"
        q = pricing.quote({"game": g["name"], "service": "division", "from": frm,
                           "to": to, "mode": mode, "addons": []})
        if q["invalid"]:            # a band whose ends overlap on this ladder
            continue
        rating = b["review"][2] if i == 0 else (5.0, 5.0, 4.9, 5.0, 4.8)[rot(i * 19 + 9, 5)]
        d = now - timedelta(days=back)
        rows.append(dict(id="#%d" % oid, frm=frm, to=to, mode=mode, days=q["days"],
                         date="%d %s" % (d.day, d.strftime("%b")),
                         rating="%.1f" % rating))
        oid -= 7 + rot(i * 23 + 11, 14)
        back += q["days"] + 1 + rot(i * 29 + 13, 3)
    return rows


def _side_mark(g, rank, strong):
    """One end of a climb, drawn the way every other rank on the site is."""
    side = _rank_side(g, rank)
    if side is None:
        return ('<span class="bp-rank-plain">%s</span>' % esc(rank)), ""
    tier, div, ladder = side
    label = div or (tier if ladder else tier[:2].upper())
    return (tier_mark(g, tier, label, strong=strong, wide=bool(ladder), base="bp-mark"),
            ladder or tier)


BP_PAGE = 8      # order rows visible before "Load more" reveals the rest


def order_rows(b):
    g = BY_SLUG.get(b["slug"])
    out = ""
    for i, o in enumerate(booster_history(b)):
        fm, fn = _side_mark(g, o["frm"], False)
        tm, tn = _side_mark(g, o["to"], True)
        out += f"""<div class="bp-row" data-bp-row data-mode="{esc(o['mode'])}"{' hidden' if i >= BP_PAGE else ''}>
          <span class="bp-id">{esc(o['id'])}</span>
          <span class="bp-climb"><span class="bp-tier">{esc(fn)}</span>{fm}
            {_ico("arrow", 12, "bp-arrow", stroke=True)}
            <span class="bp-tier is-to">{esc(tn)}</span>{tm}</span>
          <span class="bp-q">{_ico("user" if o['mode'] == "Solo" else "users", 15, "bp-q-ico", stroke=True)}{esc(o['mode'])}</span>
          <span class="bp-days">{o['days']}<span> {esc("day" if o['days'] == 1 else "days")}</span></span>
          <span class="bp-date">{esc(o['date'])}</span>
          <span class="bp-rating">{_ico("star", 13, "bp-star")}{esc(o['rating'])}</span>
        </div>"""
    return out


def order_filters(b):
    """All / Solo / Duo, with the counts.

    The split is taken from the derived sample and applied to the real order
    total, so the three chips always sum to the figure in the stat card above
    them. Two hand-typed numbers would be two more things to keep in step.
    """
    rows = booster_history(b)
    if not rows:
        return "", 0, 0
    duo = sum(1 for r in rows if r["mode"] == "Duo")
    total = b["orders"]
    duo_n = round(total * duo / len(rows))
    counts = [("All", total), ("Solo", total - duo_n), ("Duo", duo_n)]
    chips = "".join(
        '<button type="button" class="bp-chip%s" role="radio" aria-checked="%s" '
        'data-bp-filter="%s">%s<b>%d</b></button>'
        % (" is-on" if not i else "", "true" if not i else "false", esc(lab), esc(lab), n)
        for i, (lab, n) in enumerate(counts))
    return ('<div class="bp-chips" role="radiogroup" aria-label="Queue">%s</div>' % chips,
            len(rows), total)


def request_card(b):
    """The rail's conversion element.

    The handoff prices naming a booster at +10% and flags the figure as
    invented. pricing.py charges no such fee and the server recomputes every
    amount, so a "+10%" here would be a price the checkout would not honour —
    the one thing this site is built not to do. The slot says what is true
    instead: naming a booster costs nothing. Introducing a real fee means
    adding it to pricing.py AND its app.js mirror first, and this label then
    reads it off the constant the way the Duo option reads DUO_MULT.

    The availability figure is the roster's own `queue` field, not a second
    invented "N slots open".
    """
    g = BY_SLUG.get(b["slug"])
    href = ("/games/%s.html?booster=%s" % (g["slug"], b["handle"])) if g else "/games"
    free = is_free(b)
    state = ('<span class="bp-slots"><span class="dot-live dot-ok" aria-hidden="true"></span>Free now</span>'
             if free else ('<span class="bp-slots is-busy"><b>%s</b> <span>ahead of you</span></span>'
                           % esc(b["queue"])))
    return f"""<div class="bp-card bp-req">
      <span class="bp-req-t">Request <b>{esc(b['handle'])}</b></span>
      <p class="bp-req-b">Name them at checkout and your order waits for them instead of going
      to the open board.</p>
      <div class="bp-req-row">
        <span class="bp-fee">
          <span class="bp-label">Named booster</span>
          <span class="bp-fee-v">No extra fee</span>
        </span>
        {state}
      </div>
      <a class="bp-req-cta" href="{esc(href)}"><span>Order with</span> <b>{esc(b['handle'])}</b>{_ico("arrow", 15, "ico", stroke=True)}</a>
    </div>"""


def climbs_card(b):
    """Which rank bands this booster actually works. Replaced a per-game
    breakdown, which stopped meaning anything once one booster covers one
    game."""
    rows = b.get("climbs") or []
    if not rows:
        return ""
    top = max(n for _, n in rows) or 1
    bars = "".join(f"""<li>
        <span class="bp-bar-h"><span class="bp-bar-n">{esc(name)}</span><span class="bp-bar-c">{n}</span></span>
        <span class="bp-bar"><i style="width:{round(n / top * 100)}%"></i></span>
      </li>""" for name, n in rows)
    return f"""<div class="bp-card">
      <span class="bp-label">Climbs delivered</span>
      <ul class="bp-bars">{bars}</ul>
    </div>"""


def review_card_rail(b):
    """The rail's testimony. Cites the newest row of the completed-orders table
    above it, so the quote and the order it names are the same order."""
    rv = b.get("review")
    if not rv:
        return ""
    text, initials, stars, days = rv
    hist = booster_history(b)
    oid = hist[0]["id"] if hist else ""
    ref = ('<span>Verified order</span> <b>%s</b>' % esc(oid)) if oid else '<span>Verified order</span>'
    # The figure rides in its own <b> so "days ago" stays a whole text node.
    ago = '<b>%d</b> <span>%s</span>' % (days, "day ago" if days == 1 else "days ago")
    return f"""<div class="bp-card">
      <div class="bp-rv-head">
        <span class="bp-label">Latest review</span>
        {rating_stars(stars, 12)}
      </div>
      <p class="bp-rv-q">{esc(text)}</p>
      <div class="bp-rv-by">
        <span class="bp-rv-av">{esc(initials)}</span>
        <span>{ref}<i aria-hidden="true"> · </i>{ago}</span>
      </div>
      <a class="bp-rv-all" href="/reviews.html"><span>All</span> <b>{b['reviews_n']}</b> <span>reviews</span>{_ico("arrow", 12, "ico", stroke=True)}</a>
    </div>"""


def booster_portrait(b):
    return "/assets/img/portrait-%s.svg" % b["handle"]


def page_booster(b):
    g = BY_SLUG.get(b["slug"])
    chips, have, total = order_filters(b)
    shown = min(BP_PAGE, have)
    rows = order_rows(b)
    spotlight = bool(SPOT_BOOSTER and b["handle"] == SPOT_BOOSTER["handle"])
    top = (('<span class="bp-badge is-lit">%sThis month\'s #1</span>'
            % _ico("bolt", 11, "ico")) if spotlight else "")
    spec = ('<span class="bp-badge is-flat">%s%s<i aria-hidden="true"> · </i>%s</span>'
            % (_ico("crosshair", 12, "ico", stroke=True), esc(g["name"] if g else ""),
               esc(b["role"]))) if g else ""
    live = ('<span class="bp-live"><span class="dot-live dot-ok" aria-hidden="true"></span>Free now</span>'
            if is_free(b)
            else ('<span class="bp-live is-busy"><b>%s</b> <span>in the queue</span></span>'
                  % esc(b["queue"])))
    stats = "".join(f"""<div class="bp-stat">
        <span class="bp-label">{esc(label)}</span>
        <span class="bp-stat-v">{esc(val)}{unit}</span>
      </div>""" for label, val, unit in (
        ("Orders delivered", str(b["orders"]), ""),
        ("Average rating", b["rating"], '<i class="bp-stat-u">/ 5</i>'),
        ("On-time rate", b["ontime"], ""),
        ("Disputes", b["disputes"], ""),
    ))
    # Only rendered when there are hidden rows behind it. The profile shows a
    # recent sample of a long history, not the whole thing — "the last N of M"
    # says that, and a Load more with nothing behind it would promise the other
    # two hundred orders are a click away. Same reason the live feed's rows
    # aren't links: no dead controls.
    more = ('<button type="button" class="rst-more" data-bp-more>Load more'
            + _ico("arrow-down", 14, "ico", stroke=True) + '</button>') if have > BP_PAGE else ""

    # Person/ProfilePage only — deliberately no aggregateRating or Review
    # markup. The ratings on this page are placeholders (see data.py); shipping
    # them as structured data would put invented review stars in search results,
    # which is both dishonest and against Google's own policy.
    ld = [{
        "@context": "https://schema.org", "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person", "name": b["handle"],
            "jobTitle": "%s booster" % (g["name"] if g else "Rank"),
            "knowsAbout": g["name"] if g else "",
            "image": D.SITE + img(booster_portrait(b)),
            "url": D.SITE + _canon(booster_href(b)),
        },
    }, {
        "@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Boosters",
             "item": D.SITE + "/boosters"},
            {"@type": "ListItem", "position": 3, "name": b["handle"],
             "item": D.SITE + _canon(booster_href(b))},
        ],
    }]

    body = f"""<section class="bp">
  <div class="bp-glow" aria-hidden="true"></div>
  <div class="wrap">
    <nav class="bp-crumbs" aria-label="Breadcrumb">
      <a href="/">Home</a>{_ico("chevron-right", 12, "bp-crumb-i", stroke=True)}
      <a href="/boosters">Boosters</a>{_ico("chevron-right", 12, "bp-crumb-i", stroke=True)}
      <span aria-current="page">{esc(b['handle'])}</span>
    </nav>
    <div class="bp-grid">
      <div class="bp-main">
        <header class="bp-id">
          <span class="bp-portrait"><img src="{img(booster_portrait(b))}" alt="" width="96" height="96" fetchpriority="high"></span>
          <div class="bp-id-t">
            <div class="bp-id-top">
              <h1 class="bp-name">{esc(b['handle'])}</h1>
              <span class="bp-badge is-ok">{_ico("seal", 12, "ico", evenodd=True)}Verified</span>
              {top}{spec}
            </div>
            <div class="bp-meta">
              <span class="bp-meta-i">{booster_mark(b, "bp-mark")}{esc(b['peak_full'])}</span>
              <span class="bp-meta-d" aria-hidden="true"></span>
              <span class="bp-meta-i"><span>Boosting since</span> <b>{esc(b['since'])}</b></span>
              <span class="bp-meta-d" aria-hidden="true"></span>
              {live}
            </div>
          </div>
        </header>

        <div class="bp-stats">{stats}</div>

        <div class="bp-orders-head">
          <h2 class="bp-h2">Completed orders</h2>
          {chips}
        </div>
        <div class="bp-table">
          <div class="bp-thead" aria-hidden="true">
            <span>Order</span><span>Climb</span><span>Queue</span>
            <span>Delivered</span><span>Completed</span><span>Rating</span>
          </div>
          <div class="bp-tbody" data-bp-body>{rows}</div>
          <div class="bp-foot">
            <!-- Two figures mid-sentence, so this one falls back to English in
                 fr/de: fragmenting it would impose English word order on both.
                 Same call the dashboard's "Last 5 of 38 games" makes. -->
            <span class="bp-count">Showing the last <b data-bp-shown>{shown}</b> of <b data-bp-total>{total}</b> <span>orders</span></span>
            {more}
          </div>
        </div>
      </div>

      <aside class="bp-rail">
        {request_card(b)}
        {climbs_card(b)}
        {review_card_rail(b)}
      </aside>
    </div>
  </div>
</section>"""
    return layout(booster_href(b),
                  "%s — %s booster · %s" % (b["handle"], g["short"] if g else "Rank", D.BRAND),
                  "%s boosts %s on %s: %s, %s win rate over 30 days, %s orders delivered. "
                  "Name them at checkout." % (b["handle"], g["name"] if g else "ranked",
                                              b["region"], b["peak"], b["wr"], b["orders"]),
                  body, current="/boosters", jsonld=ld, nav_outline=True,
                  og_image=img(booster_portrait(b)))


def reviews_grid(items):
    if not items:
        return ""
    cards = "".join(f"""<div class="card">
      <span class="card-kicker">{esc(r['rank'])}</span>
      <p class="card-body">{esc(r['text'])}</p>
      <span class="card-meta">Verified order · {esc(r['game'])}</span>
    </div>""" for r in items)
    return '<div class="cards-3">%s</div>' % cards


def _review_game(r):
    """The game dict a review belongs to, from its "LoL · EUW" label.

    Reviews name their game the way a customer would ("Apex", "LoL"), which is
    neither the full name nor the short code for every title, so the lookup
    tries both and then falls back to a prefix match. Returns (game, region);
    an unknown game is None and the card simply prints the label it was given.
    """
    head, _, region = r["game"].partition("·")
    key = head.strip()
    g = _REVIEW_GAMES.get(key.lower())
    if g is None:
        g = next((x for x in D.GAMES if x["name"].lower().startswith(key.lower())), None)
    return g, region.strip()


_REVIEW_GAMES = {}
for _g in D.GAMES:
    for _k in (_g["name"], _g.get("short"), _g.get("tab")):
        if _k:
            _REVIEW_GAMES.setdefault(_k.lower(), _g)


def _rank_side(game, side):
    """Split "Gold IV" into ("Gold", "IV", ""), against that game's ladder.

    Matching on the game's own tier names rather than on whitespace is what
    keeps multi-word tiers ("Grand Champ I") and rating ladders ("19k Premier",
    where the trailing word names the ladder, not a division) from parsing into
    nonsense. An unmatched side returns None and the caller drops back to
    printing the rank as written.
    """
    side = side.strip()
    # Longest tier name first, so "Grand Champ" is tried before "Champion".
    for t in sorted(game["tiers"], key=len, reverse=True):
        if side == t:
            return t, "", ""
        if not side.startswith(t + " "):
            continue
        rest = side[len(t) + 1:].strip()
        # A numeral after the tier is its division; a word is the ladder's own
        # name, carried on the rating ladders ("19k Premier").
        is_division = rest.isdigit() or (rest != "" and set(rest) <= set("IV"))
        return (t, rest, "") if is_division else (t, "", rest)
    return None


def review_climb(r):
    """The climb line — the same tinted marks the configurators and the live
    feed draw, so one climb reads identically everywhere on the site.

    Falls back to the rank as written for the orders that aren't a climb
    between two tiers at all ("10 placement games", "20-bomb + 4K badge"):
    inventing a mark for those would be drawing a rank that doesn't exist.
    """
    g, _ = _review_game(r)
    ends = [s for s in r["rank"].split("→")]
    sides = [_rank_side(g, s) for s in ends] if (g and len(ends) == 2) else []
    if not sides or any(s is None for s in sides):
        return '<span class="rv-climb-plain">%s</span>' % esc(r["rank"])

    # A rating ladder (CS2 Premier) prints the rating in the mark and names the
    # ladder once, on the destination; a tier ladder prints the division
    # numeral — or the tier's first two letters where it has none — and names
    # the tier on both sides.
    ladder = sides[0][2] or sides[1][2]
    out = ""
    for i, (tier, div, _sfx) in enumerate(sides):
        to = i == 1
        label = div or (tier if ladder else tier[:2].upper())
        if to:
            out += _ico("arrow", 12, "rv-climb-arrow", stroke=True)
        name = ladder if (to and ladder) else ("" if ladder else tier)
        if name:
            out += ('<span class="rv-tier%s">%s</span>'
                    % (" is-to" if to else "", esc(name)))
        out += tier_mark(g, tier, label, strong=to, wide=bool(ladder), base="rv-mark")
    return out


def _review_date(r, now=None):
    """"11 Aug" — `days` before the build, so the feed never freezes on the
    month it was written in. Same treatment as the live feed's timestamps."""
    d = (now or datetime.now()) - timedelta(days=int(r.get("days", 1)))
    return "%d %s" % (d.day, d.strftime("%b"))


def review_card(r, now=None, filterable=False, hide=False):
    """One review card.

    Ordered stars → date, climb, quote, provenance: the quote is the card's
    largest text because that is what a review card is for, and "Verified
    order" is said once, in the footer, instead of twice as it was.

    `filterable` adds the two facts /reviews.html filters and sorts on, and
    `hide` is how that page ships its second page already rendered. Both are
    attributes on the same card rather than a second markup path: the page and
    the homepage carousel must stay one component, or a review reads one way in
    the feed and another on the page the feed links to.
    """
    g, region = _review_game(r)
    name = g["name"] if g else r["game"].partition("·")[0].strip()
    stars = int(r.get("stars", 5))
    hooks = (' data-rv-stars="%d" data-rv-game="%s"' % (stars, esc(g["slug"] if g else ""))
             if filterable else "")
    return f"""<figure class="rv-card"{hooks}{' hidden' if hide else ''}>
      <div class="rv-card-top">
        {rating_stars(stars)}
        <span class="rv-date">{esc(_review_date(r, now))}</span>
      </div>
      <div class="rv-climb">{review_climb(r)}</div>
      <blockquote class="rv-quote">{esc(r['text'])}</blockquote>
      <figcaption class="rv-foot">
        <span class="rv-verified">{_ico("seal", 11, "rv-seal", evenodd=True)}<span>Verified order</span></span>
        <span class="rv-sep" aria-hidden="true">·</span>
        <span class="rv-game">{esc(name)}</span>
        {f'<span class="rv-sep" aria-hidden="true">·</span><span class="rv-region">{esc(region)}</span>' if region else ''}
      </figcaption>
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
    """Paged review carousel — `initCarousel` sizes the slides, pages them and
    keeps the range label and both arrow states in step with the page.

    Three per page on the desktop layout, and the arrows stop at the ends
    rather than wrapping: the range label says where you are, so a control that
    silently looped back to the start would contradict it. Nothing rotates on a
    timer either — a card the reader is halfway through must not slide away.

    With JS off the track stays a horizontal scroller and the controls are
    hidden, so the reviews are still all readable.
    """
    if not items:
        return ""
    now = datetime.now()
    cards = "".join(review_card(r, now) for r in items)
    total = len(items)
    return f"""<div class="rv-carousel" data-carousel data-carousel-total="{total}">
      <div class="rv-viewport" data-carousel-viewport>
        <div class="rv-track" data-carousel-track>{cards}</div>
      </div>
      <div class="rv-pager">
        <span class="rv-range" aria-live="polite"><span data-carousel-range>1&#8211;{min(3, total)} / {total}</span>&nbsp;<span>reviews</span></span>
        <div class="rv-pager-ctl">
          <div class="rv-dots" data-carousel-dots role="group" aria-label="Review pages"></div>
          <div class="rv-navs">
            <button class="rv-nav" type="button" data-carousel-prev aria-label="Previous reviews">{_ico("arrow", 15, "rv-nav-ico rv-nav-back", stroke=True)}</button>
            <button class="rv-nav" type="button" data-carousel-next aria-label="Next reviews">{_ico("arrow", 15, "rv-nav-ico", stroke=True)}</button>
          </div>
        </div>
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


def mode_seg(name, pct=False, icons=False):
    """Solo / Duo queue. `pct` prints what duo actually costs, read off the
    authoritative multiplier rather than typed in — the label can't drift from
    the formula the way a hard-coded "+35%" would. `icons` adds the one/two
    figure glyphs the Best Sellers band draws."""
    # Label reads "Duo" (the handoff's control), while the input value stays the
    # canonical "Duo queue" the pricing formula matches on.
    duo = "Duo"
    if pct:
        duo += ' <span class="seg-pct">+%d%%</span>' % round((pricing.DUO_MULT - 1) * 100)
    solo_i = _ico("user", 15, "seg-ico", stroke=True) if icons else ""
    duo_i = _ico("users", 15, "seg-ico", stroke=True) if icons else ""
    return f"""<div class="seg seg-full">
        <label class="seg-opt"><input type="radio" name="{name}" value="Solo" data-mode autocomplete="off">{solo_i} Solo</label>
        <label class="seg-opt"><input type="radio" name="{name}" value="Duo queue" data-mode autocomplete="off">{duo_i} {duo}</label>
      </div>"""


def _addons_sorted():
    """Free rows first, in ADDONS order. Leading with what costs nothing
    establishes the block as generous before it asks for money — the picks
    add-on and the offline appearance are trust proofs that were previously
    buried, and the free-but-optional stream row is the one the visitor is
    meant to see first of all, which is why it sits first in ADDONS."""
    return sorted(D.ADDONS, key=lambda a: (a["pct"] != 0, D.ADDONS.index(a)))


def addon_name(a, game=None):
    """An add-on's name as markup, with the phone's shorter wording beside it
    where data.py carries one.

    Only `champ` is per game (see `D.picks_label()`), and only the pages pinned
    to one game know which. Checkout does not — it is one static page for all
    nine — so with no `game` it ships **every** wording, one `data-when-game`
    node each, and app.js shows the order's. Same reason the two auth tabs and
    the two rank-plate labels both ride in the DOM: i18n.js matches whole text
    nodes, so a name written in by JS would arrive untranslated.
    """
    def one(txt, attrs=""):
        if a.get("label_sm"):
            return (f'<span class="opt-t-full"{attrs}>{esc(txt)}</span>'
                    f'<span class="opt-t-sm"{attrs}>{esc(a["label_sm"])}</span>')
        return f'<span{attrs}>{esc(txt)}</span>' if attrs else esc(txt)

    if a["id"] != "champ":
        return one(a["label"])
    if game:
        return one(D.picks_label(game))
    return "".join(one(D.picks_label(g["name"]),
                       ' data-when-game="%s"%s' % (esc(g["name"]), "" if i == 0 else " hidden"))
                   for i, g in enumerate(D.GAMES))


def addons_block(money=False, paid_only=False, game=None):
    """Add-on picker. `money` renders each price as the dollars it actually adds
    to this order rather than a percentage — used at checkout, where buyers
    price in currency, not maths.

    `paid_only` drops the free INCLUSIONS, for checkout's "Last chance to add"
    upsell: a row that is already ticked and cannot be unticked is not an
    upsell. It deliberately keeps the free-but-OPTIONAL row, which is untaken by
    default and is therefore the strongest thing that block can offer. An add-on
    flagged `incl` in data.py never renders here at all — checkout states that
    one in its own green strip.

    Three price shapes, matching the three states data.py's ADDONS block
    documents: a percentage or a live "+$N" for a paid option, a static
    "Included" chip for an inclusion, and — for a `was_pct` row — a struck
    reference figure beside the live "+$0" the engine actually quotes.

    Two of the add-ons are mode-conditional: solo orders are offered "Solo only
    queue", duo orders "Play on your schedule". Both ship in the DOM carrying
    `data-when-mode`, the one for the other queue `hidden`, and app.js swaps
    them on the mode radio — the whole-text-node rule again, and it also keeps
    the row count (and so the card's height) the same in both queues.

    `game` pins the per-game add-on name; see addon_name().
    """
    rows = []
    for a in _addons_sorted():
        free = a["pct"] == 0
        # Free but still a CHOICE — see D.addon_is_free_opt(). It is the one
        # zero-cost row that survives `paid_only`: checkout's "Last chance to
        # add" drops the inclusions because a ticked, disabled row is not an
        # upsell, but an untaken free option is the best upsell on the page.
        free_opt = D.addon_is_free_opt(a)
        if a.get("incl") or (free and paid_only and not free_opt):
            continue
        if free_opt:
            # Two live figures, never a typed one: the struck reference quoted
            # by pricing.addon_list_price() off this order's own base, and
            # beside it the same [data-addon-price] every paid row carries,
            # which quotes what ticking the box ACTUALLY does to the total. That
            # second figure is what keeps the row honest — it reads "+$0"
            # because the engine charges $0, not because the markup says so, and
            # it would start reading "+$21" the moment anybody set a `pct`.
            price = (
                '<span class="price price-freeopt">'
                '<s class="opt-was" data-addon-was="%s" title="%s"></s>'
                '<span class="opt-now" data-addon-price="%s">—</span>'
                '</span>' % (esc(a["id"]), esc(D.STREAM_WAS_NOTE), esc(a["id"])))
        elif free:
            price = '<span class="price price-free">Included</span>'
        elif money:
            price = '<span class="price" data-addon-price="%s">—</span>' % esc(a["id"])
        else:
            price = '<span class="price">+%d%%</span>' % round(a["pct"] * 100)
        checked = " checked disabled" if free and not free_opt else ""
        # Phone wording where the handoff shortens it; both variants ride in the
        # DOM so each stays a whole translatable node (see ADDONS in data.py).
        name = addon_name(a, game)
        note = esc(a["note"])
        if a.get("note_sm"):
            note = (f'<span class="opt-n-full">{esc(a["note"])}</span>'
                    f'<span class="opt-n-sm">{esc(a["note_sm"])}</span>')
        # The queue this row belongs to, and whether it starts hidden. The
        # server renders the default queue (Solo); app.js owns it from there.
        when = ""
        if a.get("mode"):
            when = ' data-when-mode="%s"%s' % (
                esc(a["mode"]), "" if D.addon_applies(a, "Solo") else " hidden")
        cls = " opt-freeopt" if free_opt else (" opt-free" if free else "")
        # The flag that makes the free row read as an offer rather than the
        # third checkbox in a list. It is rendered on exactly the condition that
        # makes the row free (`free_opt`, i.e. `pct == 0`), so it cannot come to
        # sit beside a price: give this add-on a rate and the flag disappears
        # with the strikethrough in the same edit.
        #
        # "FREE" is uppercase in the TEXT, not via text-transform, and that is
        # load-bearing: i18n.js matches whole text nodes case-sensitively, and
        # "Free" is already a key — the roster's, where it means *available* and
        # translates to "Libre". A lower-case flag here would render a French
        # visitor a green pill reading "Libre" beside a price.
        flag = '<b class="opt-flag">FREE</b>' if free_opt else ""
        rows.append(f"""<label class="opt{cls}"{when}>
        <input type="checkbox" data-addon="{esc(a['id'])}"{checked} autocomplete="off">
        <span><span style="display:block">{name}{flag}</span>
        <span class="note">{note}</span></span>
        {price}
      </label>""")
    return '<div class="opts">%s</div>' % "".join(rows)


def pay_marks():
    """Accepted-payment strip for the pay step, as `(chips, stripe_badge)`.

    Two pieces rather than one row: the handoff sets the green "Secured by
    Stripe" badge opposite the chips, so the reassurance is not read as a sixth
    payment method.

    Same chips as before — the dark field pill with a small glyph and the
    network's name — but the glyphs are now the networks' own marks in their own
    colours instead of the grey card/wallet stand-ins: Visa's blue card, the
    Mastercard interlock (#EB001B / #F79E1B / #FF5F00 lens), the Amex blue card,
    the Apple glyph and Google's four-colour G. Small, riding beside the label
    rather than replacing it, so nothing about the row's shape changes.

    Two caveats worth keeping in the file. **These are simplified marks, not the
    networks' released artwork** — the card schemes require their logos be used
    unmodified from the brand kit (Stripe ships all of them), so swap these for
    the official assets before launch. And displaying a mark is conditional on
    actually taking the method: the row must stay in step with what `serve.py`
    enables on the Stripe session, or it advertises a method the buyer cannot
    pick (the reason `pay_glyphs()` drops PayPal and BTC).

    Two pieces rather than one row: the handoff sets the green "Secured by
    Stripe" badge opposite the chips, so the reassurance is not read as a sixth
    payment method.
    """
    # A colour card in the network's blue — the magstripe band keeps it reading
    # as a card, not a plain rectangle. Visa and Amex differ only by hue, which
    # the label beside them resolves.
    def card_glyph(fill):
        return ('<svg class="co-pico" width="21" height="14" viewBox="0 0 21 14" '
                'aria-hidden="true" focusable="false">'
                f'<rect width="21" height="14" rx="2.5" fill="{fill}"/>'
                '<rect y="3" width="21" height="2.6" fill="#fff" opacity=".92"/></svg>')

    visa = card_glyph("#1434CB")
    amex = card_glyph("#1F72CF")

    # The interlock. r=5, centres 6 apart → intersections at x=9, y=5.5±4, so the
    # overlap lens spans (9,1.5)–(9,9.5).
    mastercard = ('<svg class="co-pico" width="18" height="12" viewBox="0 0 18 12" '
                  'aria-hidden="true" focusable="false">'
                  '<circle cx="6" cy="6" r="5" fill="#EB001B"/>'
                  '<circle cx="12" cy="6" r="5" fill="#F79E1B"/>'
                  '<path d="M9 2.2A5 5 0 0 1 9 9.8 5 5 0 0 1 9 2.2Z" fill="#FF5F00"/></svg>')

    apple = ('<svg class="co-pico" width="13" height="15" viewBox="0 0 13 15" '
             'aria-hidden="true" focusable="false"><path fill="#fff" '
             'd="M10.94 7.9c-.01-1.4 1.14-2.06 1.19-2.1-.65-.94-1.65-1.07-2.01-1.08-.86-.09-1.68.5'
             '-2.11.5-.43 0-1.1-.49-1.81-.47-.94.01-1.8.54-2.28 1.37-.97 1.68-.25 4.17.7 5.53.46'
             '.67 1.01 1.42 1.73 1.39.69-.03.96-.45 1.79-.45.83 0 1.08.45 1.81.44.75-.01 1.22-.68'
             ' 1.68-1.35.53-.78.74-1.52.76-1.56-.02-.01-1.46-.56-1.47-2.21ZM9.55 3.36c.38-.46.64'
             '-1.1.57-1.74-.55.02-1.21.37-1.61.83-.35.4-.66 1.06-.58 1.69.61.05 1.24-.31 1.62-.78Z"/>'
             '</svg>')

    # Google's four-colour G, 18u artboard scaled to 14px.
    google = ('<svg class="co-pico" width="14" height="14" viewBox="0 0 18 18" '
              'aria-hidden="true" focusable="false">'
              '<path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 '
              '0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"/>'
              '<path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86'
              '-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"/>'
              '<path fill="#FBBC05" d="M3.97 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08'
              'l3.01-2.33Z"/>'
              '<path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 '
              '9 0A9 9 0 0 0 .96 4.96l3.01 2.33C4.68 5.17 6.66 3.58 9 3.58Z"/></svg>')

    rows = [(visa, "Visa"), (mastercard, "Mastercard"), (amex, "Amex"),
            (apple, "Apple&nbsp;Pay"), (google, "Google&nbsp;Pay")]
    chips = "".join('<li class="co-chip">%s%s</li>' % (g, n) for g, n in rows)
    badge = ('<span class="co-stripe">%s<span>Secured by Stripe</span></span>'
             % _ico("lock", 14, "ico", stroke=True))
    return '<ul class="co-chiprow">%s</ul>' % chips, badge


def promo_field():
    """Discount-code row for the checkout summary.

    The auto promo (D.PROMOS) is already applied before anyone types anything,
    so this field exists for affiliate and win-back codes — and, just as much,
    so a buyer who read the top bar has somewhere obvious to put the code
    instead of abandoning the order looking for one.

    What the handoff fixed: it used to be an always-visible empty input whose
    placeholder read "SPLIT15 already applied". An empty field claiming a code
    is applied reads as the opposite. The applied state is now a sentence with a
    seal, and the input hides behind "Have another code?" — which is the only
    thing it was ever for, since the auto promo needs no typing.

    Both toggle labels sit in the DOM rather than being written by JS: i18n.js
    matches whole text nodes, so a label assembled at runtime could not be
    translated. render() shows the right one off `data-when-discount` /
    `data-when-no-discount`, and the button only flips `aria-expanded`.
    """
    return f"""<div class="co-code">
      <div class="co-code-row">
        <span class="co-code-on" data-when-discount hidden>{_ico("badge", 15, "ico", evenodd=True)}<b data-out="promoCode">—</b> <span>applied</span></span>
        <span class="co-code-off" data-when-no-discount hidden>{_ico("tag", 14, "ico")}<span>No code applied</span></span>
        <button class="co-code-tog" type="button" data-promo-toggle
                aria-expanded="false" aria-controls="co-code-box">
          <span class="co-tog-open" data-when-discount hidden>Have another code?</span>
          <span class="co-tog-open" data-when-no-discount hidden>Have a code?</span>
          <span class="co-tog-close">Close</span>
        </button>
      </div>
      <div class="co-code-box" id="co-code-box" data-promo-box hidden>
        <label class="sr-only" for="k-promo">Discount code</label>
        <input class="co-input" id="k-promo" data-promo type="text" inputmode="latin"
               autocomplete="off" spellcheck="false" placeholder="Enter a code">
        <button class="co-apply" type="button" data-promo-apply>Apply</button>
      </div>
      <span class="promo-msg" data-promo-msg role="status" aria-live="polite"></span>
    </div>"""


def rank_plate(g, which, sfx="", unit=False):
    """One end of the climb, drawn as the configurator handoff's **rank plate**.

    Every rank control in the card is this one object. Division boost draws two
    of them (the climb's ends); Net wins and Placements draw a single one at the
    card's full width (`unit=True`) for the rank being played from — those tabs
    used to carry a smaller, differently-shaped control, so the same question
    ("what rank are you?") was asked with two different widgets one tab apart.
    `sfx` keeps the `<select>` ids unique when several are in the document.

    The plate is a framed block: a label, a selector row (emblem tile · tier
    name · "change tier" · two-headed caret) and the tier's divisions as a row
    of pips. Five things in it are load-bearing, each replacing something that
    failed in review — see the handoff's own list:

      · **The tier name is plain text and the `<select>` is invisible on top of
        the whole row.** A native select is as wide as its widest option, so
        "Iron" sat a whole "Platinum" away from the rest of the row. The old
        control worked around that by measuring the label and sizing the select
        to it in JS; overlaying the real control removes the problem instead of
        correcting it, and keyboard + screen-reader behaviour still comes from a
        real select. The row is the hit target.
      · **The name is `nowrap` and both plate columns are `minmax(0,1fr)`**, so
        "Diamond" cannot make its plate wider than "Iron" — the two ends must
        stay identical at every rank.
      · **Out-of-range tiers arrive as `disabled` options** (app.js fills them),
        and out-of-range divisions render disabled. The limit is visible before
        the tap; the end you did not touch is never moved.
      · The emblem is tinted from `--tier`, set on this element by the
        `data-rankcolor` hook — no per-game code, and the same colour table as
        every other rank mark on the site.

    On the climb both label wordings ship in the DOM (desktop "You are" / "You
    want", phone "Current rank" / "Target rank") and CSS picks one: i18n.js
    matches whole text nodes, so a label swapped in by JS would arrive
    untranslated. The unit plate has no second plate to be read against, so it
    names the rank outright at every width and ships one wording. The label is
    `aria-hidden` either way because the select carries the full name itself,
    which is also what keeps the tier name from being announced twice.
    """
    tiers = "".join('<option value="%s">%s</option>' % (esc(t), esc(t)) for t in g["tiers"])
    target = which == "to"
    lab = "Target rank" if target else "Current rank"
    sid = "w-%s-tier%s" % (which, sfx)
    label = (f'<span class="ob-plate-lab" aria-hidden="true">{lab}</span>' if unit else
             f'<span class="ob-plate-lab" aria-hidden="true"'
             f'><span class="ob-plate-lab-lg">{"You want" if target else "You are"}</span'
             f'><span class="ob-plate-lab-sm">{lab}</span></span>')
    return f"""<div class="ob-rank ob-plate{' ob-plate-unit' if unit else ''}{' ob-rank-target' if target else ''}" data-rankcolor="{which}">
        {label}
        <div class="ob-selector">
          <span class="ob-emblem" aria-hidden="true">{_EMBLEM}</span>
          <span class="ob-sel-txt" data-tierfit aria-hidden="true">
            <span class="ob-tiername" data-tiername="{which}">{esc(g["tiers"][0])}</span>
            <span class="ob-change">Change tier</span>
          </span>
          {_CARET_UD}
          <select class="ob-tiersel" id="{sid}" data-sel="{which}Tier"
                  aria-label="{lab} tier" autocomplete="off">{tiers}</select>
        </div>
        <div class="ob-divs ob-pips" data-subseg="{which}" role="group" aria-label="{lab} division"></div>
      </div>"""


def ladder_strip(g):
    """The climb, drawn as tier tracks — the boost-hero handoff's ladder.

    One track per tier, each striped into its division slots and filled in that
    tier's own colour across the selected span, with a hollow ring at the current
    rank and an accent dot at the target. It replaces the flat tick strip: you
    can see *which* tiers you cross, not only how many bars are lit. `data-ladder`
    is the JS hook that builds the segments per game; `data-tier-caps` keeps the
    captions underneath (tinted per tier when inside the span).

    The floor price is quoted through pricing.quote() like every other number on
    the site, so "cheapest single division" and the `from $NN` in the H1 are the
    same claim and cannot contradict each other.
    """
    return f"""<div class="ob-ladder">
        <div class="ob-track" data-ladder aria-hidden="true"></div>
        <div class="ob-tiercaps" data-tier-caps aria-hidden="true"></div>
        <div class="ob-ladder-foot">
          <span><b data-out="steps">—</b> <span data-out="stepsWord">divisions</span> to climb</span>
          <span class="ob-ladder-hours">{_ico("clock-countdown", 14, "ob-ico", stroke=True)}Played in your preferred hours</span>
        </div>
      </div>"""


def pay_glyphs():
    """Accepted-payment glyphs for the foot of the order card.

    The handoff draws card / PayPal / Apple / BTC marks here. Only the first is
    drawn: PayPal was removed from checkout and crypto is still "coming soon",
    so shipping their marks under a Continue button would advertise two methods
    the buyer cannot actually use. Card plus a wallet glyph covers what
    `serve.py` really takes (Stripe surfaces Apple/Google Pay under Card), and
    the marks stay generic — Visa/Mastercard/Amex artwork is trademarked and
    has to come from Stripe's brand kit. Same rule as pay_marks().
    """
    return (f'<span class="ob-pay">{_ico("lock", 14, "ob-ico", stroke=True)}'
            f'{_ico("card", 16, "ob-ico", stroke=True)}'
            f'{_ico("wallet", 16, "ob-ico", stroke=True)}'
            f'<span class="sr-only">Card, Apple Pay and Google Pay accepted — '
            f'payments secured by Stripe</span></span>')


def ob_trust():
    """Compact rating line for the foot of the card. Renders nothing without a
    real rating — same rule as trustpilot_badge(), and it counts the same thing
    that badge counts: the reviews that are on Trustpilot, not the corpus."""
    if not D.STATS.get("trustpilot") or not D.STATS.get("trustpilot_reviews"):
        return ""
    star = ('<svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            '<path d="M12 2l2.6 6.8H22l-6 4.5 2.3 7L12 15.9 5.7 20.3 8 13.3 2 8.8h7.4z" '
            'fill="#00b67a"/></svg>')
    return (f'<span class="ob-tp">{star}<b>{esc(D.STATS["trustpilot"])}</b> on Trustpilot · '
            f'{esc(D.STATS["trustpilot_reviews"])} reviews</span>')


def offers_coaching(g):
    """True when this game's service list mentions coaching, so only games we
    actually coach show the fourth tab. Honest by construction — a game with no
    coaches never offers a coaching booking."""
    return "coaching" in (g.get("services") or "").lower()


def coaching_panel(g):
    """The Coaching tab — a booking flow, not a boost. Coach rows, hour packs,
    focus chips, a first-session slot and server, and the format line.

    All four coaches, their rates and slots are PLACEHOLDER (D.COACHES); calendar
    and payment are unbuilt. Every control is server-rendered so the tab reads
    with no JS; app.js manages the selected state and the live price, which comes
    from coach rate × pack only (see pricing.quote's coaching branch).
    """
    coaches = "".join(f"""<button type="button" class="ob-coach" data-coach="{i}"
          aria-pressed="{'true' if i == 0 else 'false'}">
          <span class="ob-coach-av" aria-hidden="true">{esc(c['name'][0])}</span>
          <span class="ob-coach-main">
            <span class="ob-coach-top">
              <span class="ob-coach-name">{esc(c['name'])}</span>
              <span class="ob-coach-rating">{_ico('star', 10, 'ob-coach-star')}{esc(c['rating'])}</span>
            </span>
            <span class="ob-coach-meta">{esc(c['rank'])} · {esc(c['role'])}</span>
          </span>
          <span class="ob-coach-price">
            <span class="ob-coach-rate">{money(c['rate'])}</span>
            <span class="ob-coach-per">per hour</span>
          </span>
        </button>""" for i, c in enumerate(D.COACHES))

    packs = "".join(f"""<button type="button" class="ob-pack" data-pack="{i}"
          aria-pressed="{'true' if i == 1 else 'false'}">
          <span class="ob-pack-h">{p['hours']}h</span>
          <span class="ob-pack-note">{'Single session' if p['disc'] == 0 else 'Save %d%%' % round(p['disc'] * 100)}</span>
        </button>""" for i, p in enumerate(D.COACH_PACKS))

    focus = "".join(f"""<button type="button" class="ob-focus" data-focus="{i}"
          aria-pressed="{'true' if i == 0 else 'false'}">{esc(f)}</button>"""
                    for i, f in enumerate(D.COACH_FOCUS))

    slots = "".join('<option value="%s">%s</option>' % (esc(s), esc(s)) for s in D.COACH_SLOTS)
    regions = "".join('<option value="%s">%s</option>' % (esc(r), esc(r)) for r in g["regions"])

    return f"""<div data-panel="coaching" hidden>
      <div class="ob-coach-head">
        <span class="ob-lab">Pick your coach</span>
        <span class="ob-coach-count"><b>{len(D.COACHES)}</b> <span>taking bookings</span></span>
      </div>
      <div class="ob-coaches" role="group" aria-label="Pick your coach">{coaches}</div>

      <div class="ob-cell ob-coach-gap">
        <span class="ob-lab">How many hours</span>
        <div class="ob-packs" role="group" aria-label="How many hours">{packs}</div>
      </div>

      <div class="ob-cell ob-coach-gap">
        <span class="ob-lab">What to work on</span>
        <div class="ob-focuses" role="group" aria-label="What to work on">{focus}</div>
      </div>

      <div class="ob-two ob-coach-gap">
        <div class="ob-cell">
          <label class="ob-lab" for="w-slot">First session</label>
          <div class="ob-field">
            {_ico('clock', 14, 'ob-ico', stroke=True)}
            <select class="ob-select" id="w-slot" data-sel-slot autocomplete="off">{slots}</select>
            {_CARET}
          </div>
        </div>
        <div class="ob-cell">
          <label class="ob-lab" for="w-region-c">Server</label>
          <div class="ob-field">
            {_ico('globe', 14, 'ob-ico')}
            <select class="ob-select" id="w-region-c" data-sel="region" autocomplete="off">{regions}</select>
            {_CARET}
          </div>
        </div>
      </div>

      <p class="ob-coach-fmt">{_ico('monitor', 15, 'ob-ico', stroke=True)}
        <span>Live on Discord, screen shared, recorded for you to keep.</span></p>
    </div>"""


def bundle_strip(g):
    """The bundle strip in the hero — the handoff's "Save big on bundles".

    Each card is a real bundle: a two-tier climb at a genuine discount (D.BUNDLES)
    that REPLACES the sitewide sale when applied, so the "−N%" pill and the struck
    → discounted price are a reduction the checkout actually charges (the server
    recomputes it in pricing.quote). Clicking a card configures the climb on the
    Division boost tab and marks the bundle active; it survives a division change
    and drops on a tier or target change. Renders nothing for a game with no
    bundles.

    Every label is read off the ladder, never typed, because all nine games render
    this strip and their divisions are all different (IV–I, 1–3, 5–1, I–IV, none):
    the target is the resolved rank name, and the "from any … division" line is
    dropped on a tier that has no divisions — CS2's flat CS Rating rungs, where a
    bundle names two exact checkpoints.
    """
    climbs = D.bundle_climbs(g)
    if not climbs:
        return ""
    dm = g.get("divmap") or {}
    # Every figure on a card is derived from the hand-set price against the full
    # climb, so the pill can only ever state the reduction the checkout charges.
    offs = [int(round(pricing.bundle_pct(g, b) * 100)) for b in climbs]
    max_off = max(offs)
    flat = not any(len(dm.get(b["ft"], ())) > 1 for b in climbs)
    tiers = g["tiers"]
    spans = [tiers.index(b["tt"]) - tiers.index(b["ft"]) for b in climbs]
    # The note is a claim about the set, so each is guarded by what the set
    # actually does. "The bigger the climb, the deeper the discount" only holds
    # while the percentages really do rise with the span — prices are set by
    # hand now, so a re-price can break the correlation, and the strip must not
    # keep advertising a ramp that is no longer there.
    ramped = sorted(zip(spans, offs)) == sorted(zip(spans, sorted(offs)))
    if flat:
        note = "Two rating bands up in one order"
    elif max(spans) - min(spans) >= 2:
        note = ("The bigger the climb, the deeper the discount" if ramped
                else "Whole-ladder climbs at one flat price")
    else:
        note = "Two tiers up in one order, from wherever you are"
    cards = ""
    for i, b in enumerate(climbs):
        # Price the FULL two-tier climb (from-tier's bottom division → target),
        # not the cheapest sub-climb: the bundle is a flat price every division
        # in the tier pays, so the struck figure has to be the real "two tiers
        # up" work — see pricing.py / app.js.
        full = pricing.full_bundle_price(g, b)
        price, off = b["price"], offs[i]
        sub = ("From any %s division" % b["ft"] if len(dm.get(b["ft"], ())) > 1
               else "Starts at %s" % b["floorFrom"])
        cards += f"""<button type="button" class="ob-bundle" data-bundle="{i}"
          data-bundle-to="{esc(b['target'])}" data-bundle-tier="{esc(b['ft'])}"
          data-bundle-floor="{esc(b['floorFrom'])}" data-bundle-def="{esc(b['defFrom'])}"
          data-bundle-amt="{price}" aria-pressed="false">
          <span class="ob-bundle-top">
            <span class="ob-bundle-name"><span>{esc(b['ft'])}</span><i aria-hidden="true">→</i><wbr><span>{esc(b['target'])}</span></span>
            <span class="ob-bundle-off">−{off}%</span>
          </span>
          <span class="ob-bundle-sub">{esc(sub)}</span>
          <span class="ob-bundle-price">
            <span class="ob-bundle-from">from</span>
            <span class="ob-bundle-list" data-bundle-list>{money(full)}</span>
            <span class="ob-bundle-amt" data-bundle-price>{money(price)}</span>
          </span>
          <span class="ob-bundle-cta">
            <span class="ob-bundle-apply">{_ico('plus', 12, 'ob-bundle-cico', stroke=True)}Apply bundle</span>
            <span class="ob-bundle-on">{_ico('check', 12, 'ob-bundle-cico', stroke=True)}Applied</span>
          </span>
        </button>"""
    return f"""<div class="ob-bundles">
      <div class="ob-bundles-head">
        <span class="ob-bundles-tile" aria-hidden="true">{_ico('tag', 18, 'ob-bundles-ico')}</span>
        <span class="ob-bundles-copy">
          <span class="ob-bundles-title">Save big on bundles</span>
          <span class="ob-bundles-note">{esc(note)}</span>
        </span>
        <span class="ob-bundles-pill">Up to {max_off}% off</span>
      </div>
      <div class="ob-bundles-grid">{cards}</div>
    </div>"""


def unit_grid(kind, label, note):
    """The 1–5 game grid for the Net wins / Placements tabs — the handoff's
    PerGamePanel. Replaces the ± stepper: both products are capped at five per
    order, so five exposed buttons read the cap at a glance and take one tap. The
    per-game price sits beside the label (quoted live, one unit at the current
    rank), and the note differs per product.
    """
    btns = "".join(
        '<button type="button" class="ob-count" data-count="%s" data-n="%d" '
        'aria-pressed="%s">%d</button>' % (kind, n, "true" if n == 3 else "false", n)
        for n in range(1, 6))
    return f"""<div class="ob-unit-block">
        <div class="ob-unit-head">
          <span class="ob-lab">{label}</span>
          <span class="ob-unit-price"><b data-out="{kind}Unit">—</b> <span>per game</span></span>
        </div>
        <div class="ob-counts" data-countgrid="{kind}" role="group" aria-label="{label}">{btns}</div>
        <span class="ob-unit-note">{_ico("info", 13, "ob-ico", stroke=True)}<span>{esc(note)}</span></span>
      </div>"""


def wizard(game=None):
    """The order card on the game pages — the "Ladder card" from the LoL boost
    hero handoff, ported onto Ashfall's tokens and this build's data contract.

    What the redesign changed, and why each one is load-bearing:
      · the ladder is visible (see rank_plate/ladder_strip) rather than implied
        by two dropdowns;
      · add-ons moved up from the checkout page and price themselves in dollars
        on *this* order — the buyer never has to multiply a percentage;
      · the CTA carries the live price, and it is the only filled button in the
        viewport (the nav's "Start an order" drops to an outline on these pages);
      · availability sits beside the delivery estimate, where it does conversion
        work, instead of in the hero's stat row.

    Every price still comes from one quote() call in app.js's render pass — this
    function only lays out the hooks in the documented data-* contract.
    """
    g = BY_NAME[game] if game else D.GAMES[0]
    regions = "".join('<option value="%s">%s</option>' % (esc(r), esc(r)) for r in g["regions"])
    attr = ' data-game="%s"' % esc(g["name"]) if game else ""
    # Numbers kept out of the translatable text nodes: i18n.js matches a node's
    # whole trimmed value against the dictionary, so "25 of 34 boosters free
    # now" could never be a key. Split this way, "of" and "boosters free now"
    # both are, and the live count still animates inside its own <b>.
    free = (f'<span class="ob-free"><span class="live-dot" aria-hidden="true"></span>'
            f'<b data-live="free">{D.STATS["free_now"]}</b> <span>of</span> '
            f'<b>{D.STATS["online"]}</b> <span>boosters free now</span></span>'
            if D.STATS.get("free_now") and D.STATS.get("online") else "")

    return f"""<div class="wizard ob" data-configurator{attr}>
      <div class="ob-head">
        <span class="ob-title">Build your boost</span>
        <span class="ob-livepill"><span class="ob-livedot" aria-hidden="true"></span>Live pricing</span>
      </div>

      <!-- Named booster, arriving from a roster Hire or a profile CTA
           (?booster=<handle>). Hidden unless one is named, so it costs the
           card's fold budget nothing for the buyers who never asked for it —
           the CTA has to clear the fold at 1440x900 and this row would
           otherwise come straight out of that. -->
      <div class="ob-named" data-when-booster hidden>
        {_ico("user", 14, "ico")}
        <span class="ob-named-t"><span>Ordering with</span> <b data-out="booster">—</b></span>
        <button type="button" class="ob-named-x" data-booster-clear>Change</button>
      </div>

      <div class="tabs ob-tabs" role="tablist" aria-label="Service">
        <button class="tab" role="tab" data-service="division" aria-selected="true">Division boost</button>
        <button class="tab" role="tab" data-service="wins" aria-selected="false">Net wins</button>
        <button class="tab" role="tab" data-service="placements" aria-selected="false">Placements</button>
        {'<button class="tab" role="tab" data-service="coaching" aria-selected="false">Coaching</button>' if offers_coaching(g) else ''}
      </div>

      <div data-panel="division">
        <div class="ob-ranks">
          {rank_plate(g, "from")}
          <!-- One arrow, two presentations: a ring between the plates on
               desktop, and on the phone the same ring centred in a hairline
               rule with the glyph rotated down, since the plates stack. -->
          <span class="ob-arrow" aria-hidden="true">
            <span class="ob-arrow-ring">{_ico("arrow", 13, "ico", stroke=True)}</span>
          </span>
          {rank_plate(g, "to")}
        </div>
        <div class="ob-err" data-when-invalid role="alert" hidden>
          {_ico("warn", 15, "ob-err-ico", stroke=True)}
          <span>Target must sit above your current rank</span>
        </div>
        {ladder_strip(g)}
      </div>

      <div data-panel="wins" hidden>
        {rank_plate(g, "from", "-wins", unit=True)}
        {unit_grid("wins", "How many net wins",
                   "A net win means one win above your losses — five is the cap per order.")}
      </div>

      <div data-panel="placements" hidden>
        <div class="ob-ranked" role="group" aria-label="Do you have a rank">
          <button type="button" class="ob-ranked-opt" data-ranked="1" aria-pressed="true">I have a rank</button>
          <button type="button" class="ob-ranked-opt" data-ranked="0" aria-pressed="false">Unranked</button>
        </div>
        <div data-when-ranked>{rank_plate(g, "from", "-pl", unit=True)}</div>
        <div class="ob-unranked" data-when-unranked hidden>
          {_ico("question", 18, "ob-unranked-ico", stroke=True)}
          <span>Fresh account or a new season — no MMR to read yet. Your booster plays all five and
          the rank you land is the rank you keep.</span>
        </div>
        {unit_grid("placements", "How many placement games",
                   "A placement game sets or resets your rank — five is the cap per order.")}
      </div>

      {coaching_panel(g) if offers_coaching(g) else ''}

      <!-- Shared queue/server/add-ons. Hidden on Coaching, which is a booking
           with no queue and no add-ons and carries its own server select. -->
      <div data-hide-service="coaching">
      <div class="ob-two">
        <div class="ob-cell">
          <span class="ob-lab">How it's played</span>
          {mode_seg("w-mode", icons=True)}
        </div>
        <div class="ob-cell">
          <label class="ob-lab" for="w-region">Server</label>
          <div class="ob-field">
            {_ico("globe", 14, "ob-ico")}
            <select class="ob-select" id="w-region" data-sel="region" autocomplete="off">{regions}</select>
            {_CARET}
          </div>
        </div>
      </div>

      <div class="ob-cell">
        <span class="ob-lab">Add-ons</span>
        {addons_block(money=True, game=g["name"])}
      </div>
      </div>

      <div class="ob-div"></div>

      <div class="ob-sum" aria-live="polite">
        <div class="ob-sum-l">
          <span class="ob-lab ob-lab-cfg" data-out="configLine">—</span>
          <span class="price-pair">
            <span class="quote-was" data-when-discount data-out="was" hidden></span>
            <span class="quote-price" data-out="price">—</span>
          </span>
          <span class="save-line" data-when-discount data-out="saveWith" hidden></span>
        </div>
        <div class="ob-sum-r">
          <span class="ob-lab"><span data-hide-service="coaching">Delivered in</span><span data-when-service="coaching" hidden>First session</span></span>
          <span class="quote-eta" data-out="eta">—</span>
        </div>
        <!-- Availability is its own cell, not a child of the estimate column:
             on desktop it sits under the days, on the phone it spans the row. -->
        <div class="ob-sum-free">
          <span data-hide-service="coaching">{free}</span>
          <span class="ob-free" data-when-service="coaching" hidden><span class="live-dot" aria-hidden="true"></span><b>{len(D.COACHES)}</b> <span>coaches taking bookings</span></span>
        </div>
      </div>

      <a class="btn btn-primary btn-block ob-cta" href="/checkout.html" data-continue>
        <span data-hide-service="coaching">Continue to checkout</span><span data-when-service="coaching" data-out="bookLabel" hidden>Book</span>
        {_ico("arrow", 15, "ico", stroke=True)}
      </a>

      {ob_included(g)}

      <div class="ob-assure">
        {ob_trust()}
        {pay_glyphs()}
      </div>
    </div>"""


def ob_included(g):
    """The always-on inclusions, stated as one line instead of costing a row.

    WHY IT SITS BELOW THE CTA. The order card's whole vertical budget is the
    handoff's one hard measurement — the CTA has to clear the fold at 1440×900 —
    and the add-on list is exactly three checkbox rows wide of it. A fourth row
    costs ~51px and puts the button under the fold on six of the nine ladders.
    Everything BELOW the button is free of that budget, which is the only reason
    the picks inclusion could give up its row without the claim being lost: it
    is a fact about every order, not a choice, so it reads as well in a strip as
    it did in a permanently-ticked checkbox — the same trade `offline` made
    first, and the same shape checkout's green strip already uses.

    Reads `incl`/zero-cost straight off data.py, so a new inclusion appears here
    with no edit and the line can never name something the picker also offers.
    The free-but-OPTIONAL row is excluded for the reason it exists: it is the
    buyer's to take.

    i18n: each name is its own text node with the separators in `<i aria-hidden>`
    carriers, so every name stays a whole translatable node — all of them are
    already dictionary keys, because the picker rendered the same words.
    """
    names = [addon_name(a, g["name"]) for a in D.ADDONS
             if a["pct"] == 0 and not D.addon_is_free_opt(a)]
    if not names:
        return ""
    sep = '<i class="ob-incl-sep" aria-hidden="true">·</i>'
    body = sep.join('<span>%s</span>' % n for n in names)
    return (f'<div class="ob-incl">{_ico("seal", 13, "ico", evenodd=True)}'
            f'<span class="ob-incl-k">Included free</span>{sep}{body}</div>')


def bs_tabs(games):
    """Game tabs for the Best Sellers band.

    The old tiles were skewed parallelograms that clipped their own text. These
    are ordinary tabs: a lettermark, the short code as a kicker, and the name —
    plus a shorter name that takes over below 900px, where the full one wraps.
    """
    out = []
    for g in games:
        short = g.get("tab") or g["name"].split(" ")[0]
        out.append(
            f'<button class="bs-tab" type="button" data-game-tag="{esc(g["name"])}" aria-pressed="false">'
            f'<span class="bs-mark" aria-hidden="true">{esc(g["name"][0])}</span>'
            f'<span class="bs-tab-txt">'
            f'<span class="bs-tab-code">{esc(g["short"])}</span>'
            f'<span class="bs-tab-name">{esc(g["name"])}</span>'
            f'<span class="bs-tab-name-sm">{esc(short)}</span>'
            f'</span></button>')
    return '<div class="bs-tabs" role="group" aria-label="Choose a game">%s</div>' % "".join(out)


def rank_panel(g, which):
    """One of the band's two rank panels.

    The band used to carry a single tier row with a "YOU" and a "TARGET" marker
    on it, which made two things impossible: telling which end a click would
    move, and ordering a climb inside one tier (Bronze IV → Bronze III), because
    a tier click always jumped to that tier's floor and the clamp then pushed the
    other end across the boundary. Two labelled panels fix both — each end has
    its own tier grid and division row, and out-of-range options are disabled
    rather than silently moving the end you did not touch.

    The `<select>` and the tier grid are both rendered: the grid is the desktop
    control, the select takes over below 900px where eight tiles would clip
    every label. Both carry the same disabled state, applied by app.js.
    """
    target = which == "to"
    label = "You want to be" if target else "You are here"
    sid = "bs-%s-tier" % which
    tiers = "".join('<option value="%s">%s</option>' % (esc(t), esc(t)) for t in g["tiers"])
    return f"""<div class="bs-panel{' bs-panel-target' if target else ''}">
        <div class="bs-panel-head">
          <span class="bs-lab" id="{sid}-lab">{label}</span>
          <span class="bs-panel-val">
            <span data-tiername="{which}">—</span>
            <span class="bs-tiermark" data-mark="{which}" aria-hidden="true"></span>
          </span>
        </div>
        <div class="bs-tiergrid" data-tiergrid="{which}" role="group" aria-labelledby="{sid}-lab"></div>
        <div class="bs-tiersel">
          <label class="sr-only" for="{sid}">{label} tier</label>
          <select class="bs-select" id="{sid}" data-sel="{which}Tier" autocomplete="off">{tiers}</select>
          {_CARET}
        </div>
        <div class="bs-divs" data-subseg="{which}" role="group" aria-label="{label} division"></div>
      </div>"""


def bs_included():
    """The two things every order carries, stated where the price is read."""
    rows = (("shield", "Money-back until claimed"), ("eye-off", "Offline appearance"))
    return "".join(f'<span class="bs-inc">{_ico(i, 14, "bs-inc-ico", stroke=(i == "eye-off"))}'
                   f'{esc(t)}</span>' for i, t in rows)


def bs_band(games):
    """The Best Sellers band — a compressed order flow on the homepage.

    Everything in it is one decision away from a price: pick a game, set both
    ends of the climb, choose queue and region, and the band quotes it in place.
    It runs on the same `data-*` contract and the same `quote()` as the game
    pages, so the same climb can never quote two different prices.
    """
    g = games[0]
    free = (f'<div class="bs-fig"><span class="bs-lab">Boosters free now</span>'
            f'<span class="bs-fig-v" data-live-stat><i class="bs-dot" aria-hidden="true"></i>'
            f'<span data-live="free">{D.STATS["free_now"]}</span></span></div>'
            if D.STATS.get("free_now") else "")

    return f"""<div class="bs-dock" id="calc">
    <div class="bs" data-configurator>
      <div class="bs-glow" aria-hidden="true"></div>

      <div class="bs-head">
        <div class="bs-head-l">
          <h2 class="bs-title">Best Sellers</h2>
          <span class="bs-pill">{_ico("bolt", 11, "bs-pill-ico")}Fast checkout</span>
        </div>
        <span class="bs-live"><i class="bs-livedot" aria-hidden="true"></i>
          <span class="bs-live-full">Live pricing</span><span class="bs-live-sm">Live</span></span>
      </div>

      {bs_tabs(games)}

      <div class="bs-ranks">
        {rank_panel(g, "from")}
        <span class="bs-arrow" aria-hidden="true">
          <span class="bs-arrow-r">{_ico("arrow", 18, "ico", stroke=True)}</span>
          <span class="bs-arrow-d">{_ico("arrow-down", 16, "ico", stroke=True)}</span>
        </span>
        {rank_panel(g, "to")}
      </div>

      <div class="bs-err" data-when-invalid role="alert" hidden>
        {_ico("warn", 15, "bs-err-ico", stroke=True)}
        <span>Target must sit above your current rank</span>
      </div>

      <div class="bs-ranks bs-controls">
        <div class="bs-cell">
          <span class="bs-lab">How it's played</span>
          {mode_seg("bs-mode", icons=True)}
        </div>
        <span aria-hidden="true"></span>
        <div class="bs-cell">
          <span class="bs-lab">Your region</span>
          <div class="bs-regions" data-regions role="group" aria-label="Your region"></div>
        </div>
      </div>

      <div class="bs-climb">
        <span class="bs-lab">Your climb</span>
        <span class="bs-climb-val" data-out="configLine">—</span>
        <span class="bs-climb-rule" aria-hidden="true"></span>
        <span class="bs-climb-steps"><span data-out="steps">—</span>
          <span data-out="stepsWord">divisions</span> to climb</span>
      </div>

      <div class="ob-track bs-track" data-ladder aria-hidden="true"></div>
      <div class="ob-tiercaps bs-tiercaps" data-tier-caps aria-hidden="true"></div>

      <div class="bs-div"></div>

      <div class="bs-result">
        <div class="bs-figs">
          <div class="bs-fig">
            <span class="bs-lab">Delivered in</span>
            <span class="bs-fig-v" data-out="eta">—</span>
          </div>
          {free}
          <div class="bs-fig bs-fig-inc">
            <span class="bs-lab">Included</span>
            <span class="bs-incs">{bs_included()}</span>
          </div>
        </div>
        <div class="bs-buy" aria-live="polite">
          <div class="bs-price">
            <span class="bs-lab">Total price</span>
            <span class="price-pair">
              <span class="bs-was" data-when-discount data-out="was" hidden></span>
              <span class="bs-total" data-out="price">—</span>
            </span>
            <span class="bs-save" data-when-discount data-out="saveWith" hidden></span>
          </div>
          <a class="btn btn-primary bs-cta" href="/checkout.html" data-continue>
            <span>Continue</span>{_ico("arrow", 16, "ico", stroke=True)}
          </a>
        </div>
      </div>
    </div>
  </div>"""


# ══════════════════════════════════════════════════════════════════════════
#  pages
# ══════════════════════════════════════════════════════════════════════════
def page_home():
    # The Best Sellers band offers a curated subset of games (site order kept) —
    # four tabs is what the band's grid is drawn for. Everything else about it
    # lives in bs_band().
    chip_slugs = {"league-of-legends", "valorant", "teamfight-tactics",
                  "marvel-rivals"}
    chip_games = [g for g in D.GAMES if g["slug"] in chip_slugs]
    H = D.HERO

    # ── 02 Live / 03 Safety — design_handoff_live_and_safety ──────────────
    # One screen answering "is this real, and is it safe?": the delivery feed
    # over the safety prose, with the rail (who is on shift, then the Discord)
    # running the length of both.
    #
    # With no feed the section still holds — the roster and the objection are
    # the argument. With neither feed nor roster, Safety is all that is left,
    # and it takes its own numbered heading rather than sitting under a "Live"
    # one that no longer describes anything on the page.
    feed, roster = live_feed(), roster_panel()
    live_dot = ('<span class="ls-live"><span class="dot-live dot-ok" aria-hidden="true"></span>'
                'Updates as orders close</span>')
    if feed or roster:
        head = sec_head("02", "Live", "Delivered today",
                        right_html=live_dot if feed else None) if feed else ""
        live_section = f"""<section class="wrap section ls" id="live" style="padding-bottom:0">
  <div class="ls-grid">
    <div class="ls-main">
      {head}
      {feed}
      {'<hr class="ls-rule">' if feed else ''}
      <div class="ls-safety" id="safety">
        {sec_kicker("03", "Safety")}
        <h2 class="h-sec">{esc(D.SAFETY['title'])}</h2>
        {safety_block()}
      </div>
    </div>
    {roster}
  </div>
</section>"""
    else:
        live_section = f"""<section class="wrap section ls" id="safety" style="padding-bottom:0">
  <div class="ls-main">
    {sec_head("02", "Safety", esc(D.SAFETY['title']))}
    {safety_block()}
  </div>
</section>"""

    # ── 04 Reviews — design_handoff_reviews ───────────────────────────────
    # The Trustpilot badge plus one testimonial per game. With no real reviews
    # the whole section goes — a "What they said after" heading over an empty
    # carousel is worse than no section at all.
    #
    # The head used to run three alignment systems at once: copy flush left,
    # the badge and its explainer centred, and a "Verified orders only" label
    # floating at the far right on its own baseline. It is one row now — copy
    # left, badge and the read-all link right, both ending on the heading's
    # baseline. The floating label is gone because every card carries a
    # Verified order badge of its own, and the explainer sits under the heading
    # where it reads as part of the section rather than as a caption to the
    # badge.
    carousel = review_carousel(_reviews_one_per_game())
    reviews_section = f"""<section class="section rv" id="reviews">
  <div class="rv-hatch" aria-hidden="true"></div>
  <div class="wrap rv-wrap">
    <div class="rv-head">
      <div class="rv-head-copy">
        <span class="sec-kicker"><span class="sec-kicker-n">05</span><span class="sec-kicker-l">Reviews</span></span>
        <h2 class="h-sec">What they said after</h2>
        <p class="rv-lede">Every review is tied to a paid, completed order — nothing incentivised. One per game, across the roster.</p>
      </div>
      <div class="rv-aside">
        {trustpilot_badge()}
        {reviews_all_link()}
      </div>
    </div>
    {carousel}
  </div>
</section>""" if carousel else ""

    # Home hero — design_handoff_home_hero. Same shell and the same scoped
    # palette as the game pages' "Ladder card" hero (.hero-a), which is the
    # sibling handoff: flat #0b0a09 ground, one warm double glow centred on the
    # card so the light anchors it rather than filling empty space, and the
    # diagonal hatch. All depth is CSS — the section carries no artwork now.
    #
    # The left column runs headline → paragraph → CTAs → proof, so the three
    # objections and the rating are answered where the decision is made rather
    # than only up in the promo bar.
    #
    # The primary CTA goes to the catalogue, not to `#calc` (the Best Sellers
    # dock further down this page). It is the first action on the site and the
    # visitor has not named a title yet: the dock opens on whichever game leads
    # the catalogue, so an Apex player scrolling into a League configurator has
    # to notice the game select and change it. `/games/` asks the question the
    # dock answers by assumption, and every card there lands on a real
    # configurator. Band 04's identically-labelled button still points at
    # `#calc` — by then the page has made its argument and the dock is the
    # nearer configurator.
    body = f"""<section class="hero-a hero-a-lit hero-h" id="top">
  <div class="fx hero-h-glow" aria-hidden="true"></div>
  <div class="fx hero-a-hatch" aria-hidden="true"></div>
  <div class="fx fx-grain" aria-hidden="true"></div>

  <div class="wrap hero-h-inner">
    <div class="hero-h-copy">
      {f'<span class="kicker">{esc(H["kicker"])}</span>' if H.get("kicker") else ''}
      <h1>{esc(H['line1'])}<br><span class="grad-text">{esc(H['line2'])}</span></h1>
      <p class="lede">{esc(H['lede'])}</p>
      <div class="btn-row hero-h-cta">
        <a class="btn btn-primary" href="/games">Configure your boost{_ico("arrow", 15, "ico", stroke=True)}</a>
        <a class="btn btn-secondary" href="{ACCOUNTS_HREF}">{_ico("user-dashed", 17, "hero-h-ico", stroke=True)}Buy LoL accounts</a>
      </div>
      <div class="hero-h-proof">
        {guarantee_row()}
        <hr class="hero-a-rule">
        {hero_rating()}
      </div>
    </div>
    {spotlight_card()}
  </div>

  {bs_band(chip_games)}
</section>

<section class="section gg" id="games">
  <div class="gg-hatch" aria-hidden="true"></div>
  <div class="wrap gg-wrap">
    {sec_head("01", "Services", "Pick your game.<br>We handle the rest.")}
    {games_grid()}
  </div>
</section>

{live_section}

{dashboard_section("04", cta_href="#calc")}

{reviews_section}

{cta_band(live=True, cta=("Continue your order", "/checkout.html"))}"""

    org = {"@context": "https://schema.org", "@type": "Organization",
           "name": D.BRAND, "url": D.SITE, "logo": D.SITE + "/icon-512.png",
           # The postal address and mailbox the legal pages and the footer
           # print, asserted once to a crawler. Unlike aggregateRating below,
           # these are checkable facts about us rather than a claim about what
           # other people said, so they are not gated on anything.
           "email": FOOT_EMAIL,
           "address": {"@type": "PostalAddress",
                       "streetAddress": D.COMPANY["street"],
                       "addressLocality": D.COMPANY["city"],
                       "postalCode": D.COMPANY["postcode"],
                       "addressCountry": D.COMPANY["country_code"]}}
    # An aggregateRating in JSON-LD is a machine-readable claim that search
    # engines surface as review stars. Only ever emit it from a real rating.
    org.update(rating_ld())
    ld = [org, {"@context": "https://schema.org", "@type": "WebSite",
                "name": D.BRAND, "url": D.SITE}]
    # nav_outline for the same reason the game pages set it: the hero's own
    # gradient CTA is the filled button in this viewport, so the nav's "Start
    # an order" drops to an outline rather than splitting the click.
    return layout("/", "Game Boosting Platform - %s" % D.BRAND,
                  "The game boosting platform for competitive games. Climb the ranks in League of "
                  "Legends, Valorant, CS2 and 6 more titles with verified, vetted boosters.",
                  body, current=None, jsonld=ld, mobile_bar=True, nav_outline=True)


# ══════════════════════════════════════════════════════════════════════════
#  /games/ — the catalogue — design_handoff_games_page
# ══════════════════════════════════════════════════════════════════════════
# Seventh scoped port after .hero-a / .co / .gg / .dsh / .rst / .tk — tokens on
# `.gc`, product radii per element, nothing leaking past the scope. It replaced
# a title grid with a paragraph beside it: nine cards that named a game and a
# price, no way to narrow them, and nothing below the grid except three steps
# and the three guarantee cards.
#
# The page's job is ROUTING, not converting: get the visitor onto the right game
# page with the right expectation already set. Everything under the grid exists
# so they arrive at the configurator having answered "which service", "how does
# it run", "who plays it" and "what if it goes wrong".
#
# Three components are SHARED, not re-cut — the handoff says so outright, and
# each is this site's canonical port of the handoff it came from:
#   · the order preview is `dash_mock()` through `dashboard_section()` (band 03),
#     the same card the homepage, /how-it-works and /demo.html draw;
#   · the FAQ is `sg_faq()` + `faq_accordion_js()`, the safety/support accordion,
#     so a question here behaves and deep-links exactly like one there;
#   · the trust cards are `promise_cards()` over D.GUARANTEES — the same three
#     promises, in the same shell as /guarantee.html.
# The on-shift panel is `roster_panel()` and the game list is D.GAMES, which is
# also what the header's Games menu renders. One source, per the handoff.
#
# Every figure is read, never typed. The handoff's nine "from" prices, nine order
# counts, "78 boosters" and "3,000 in the Discord" are flagged there as invented;
# prices come through `from_price()`/`money()`, the roster counts off BOOSTERS
# and STATS, the Discord size off STATS, the coaching count off the catalogue.
#
# Deviations from the handoff, all deliberate:
#   · **"Duo available" is not one of the filters.** Duo is offered on all nine
#     titles here (`mode_seg()` is in every configurator), so that chip would
#     return the whole catalogue — the handoff's own rule is that a filter has to
#     mean something. Its slot went to "Valve titles", which is real, is two, and
#     is the same publisher split the safety copy already argues per title.
#   · **the default sort is "Featured", not "Most ordered".** Nothing in this
#     build measures order volume; the handoff's nine order counts are invented
#     and they are what its default sort reads. Featured is the catalogue's own
#     editorial order (D.GAMES), which is what it actually is.
#   · **"Compare all titles" is not drawn.** It is referenced twice in the
#     handoff and the page it points at does not exist — same rule that keeps the
#     live feed's rows unlinked. The mobile bar carries the one real action.
#   · **the mobile trust cards are a snap rail, not a 4.6s auto-rotating
#     carousel.** These are the refund, privacy and support promises; a card that
#     slides itself away mid-sentence is the "moving element reads as a sales
#     device" rule the guarantee page is built on. The dots stay, and track the
#     rail rather than driving a timer.
def _gc_price_cents(g):
    return int(round(from_price(g) * 100))


_GC_FACTS = {}


def gc_facts():
    """Everything the page counts, computed once off the catalogue.

    Filters, the FAQ's two price extremes and the service band's coaching count
    all read this, so the chips' counts and the sentences under them cannot
    disagree about the same catalogue.
    """
    if not _GC_FACTS:
        by_price = sorted(D.GAMES, key=lambda g: (from_price(g), g["name"]))
        _GC_FACTS.update(
            riot=[g for g in D.GAMES if D.publisher(g) == "Riot"],
            valve=[g for g in D.GAMES if D.publisher(g) == "Valve"],
            coach=[g for g in D.GAMES if offers_coaching(g)],
            cheap=by_price[0], dear=by_price[-1])
    return _GC_FACTS


# (key, label, predicate) — single-select, `all` is the reset. Each chip carries
# its count, and none of them can return zero or the whole catalogue: that is the
# property that makes the row worth having (see the "Duo available" note above).
GC_FILTERS = [
    ("all", "All titles", lambda g: True),
    ("riot", "Riot titles", lambda g: D.publisher(g) == "Riot"),
    ("valve", "Valve titles", lambda g: D.publisher(g) == "Valve"),
    ("coaching", "With coaching", offers_coaching),
]

# (key, label). "Featured" is the catalogue's own order — see the deviation note.
GC_SORTS = [("featured", "Featured"), ("price", "Lowest price"), ("az", "A–Z")]


def gc_card(g, i, featured=False):
    """One title. The whole card is the link; the arrow disc is decorative.

    The three booleans the toolbar filters on and the two sort keys ride on the
    element as `data-*`, so the board keeps working if this grid is ever paged or
    rendered from a store — the same contract `data-rst-row` gives the roster.
    """
    chips = "".join('<span class="gc-svc">%s</span>' % esc(s) for s in services_of(g))
    # Same badge and the same wording as the homepage mosaic's lead tile: one
    # claim about order volume, said once, with the standing STATS has. It is
    # not a second figure — see games_grid().
    badge = (f'<span class="gc-badge">{_ico("bolt", 11, "ico")}<span>Most ordered</span></span>'
             if featured else "")
    go = '<span class="gc-go-l">Configure</span>' if featured else ""
    # The band crop, not the 1200x700 key art: this art zone is 92px and the
    # wordmarks do not survive a fifth-of-height crop. See emit_art().
    return f"""<a class="gc-card{' is-feat' if featured else ''}" href="/games/{g['slug']}.html"
      data-gc-card data-gc-riot="{1 if D.publisher(g) == 'Riot' else 0}"
      data-gc-valve="{1 if D.publisher(g) == 'Valve' else 0}"
      data-gc-coaching="{1 if offers_coaching(g) else 0}"
      data-gc-order="{i}" data-gc-price="{_gc_price_cents(g)}" data-gc-name="{esc(g['name'])}"
      style="--h: {g['hue']}">
      <span class="gc-art">
        <img src="{img('/assets/img/band-%s.svg' % g['slug'])}" alt="" width="1200" height="300" loading="lazy">
        <span class="gc-veil" aria-hidden="true"></span>
        {badge}
      </span>
      <span class="gc-body">
        <!-- No lettermark beside the name: the art above it is the game's own
             wordmark, so the tile read the title twice — once as a logo and
             again as an initial in a box. The hue still does its job on the art
             wash and the hover edge. -->
        <span class="gc-name-row">
          <span class="gc-name">{esc(g['name'])}</span>
        </span>
        <span class="gc-svcs">{chips}</span>
        <span class="gc-cardfoot">
          <span class="gc-price">
            <span class="gc-from">From</span>
            <span class="gc-fig">{money(from_price(g))}</span>
          </span>
          <span class="gc-go">{go}<span class="gc-arrow" aria-hidden="true">{_ico("arrow", 13, "ico", stroke=True)}</span></span>
        </span>
      </span>
    </a>"""


def gc_count(cls=""):
    """"Showing N of M titles." — the figures in their own nodes so the words
    around them stay whole translatable text nodes.

    Rendered twice, deliberately: on the phone it belongs beside the sort control
    above the grid, on desktop it is the centred line under it, and those are two
    places in the document. One `[data-gc-shown]` selector fills both.
    """
    return (f'<span class="gc-count{(" " + cls) if cls else ""}"><span>Showing</span> '
            f'<b data-gc-shown>{len(D.GAMES)}</b> <span>of</span> <b>{len(D.GAMES)}</b> '
            f'<span>titles.</span></span>')


def gc_toolbar():
    chips = ""
    for key, label, pred in GC_FILTERS:
        on = key == "all"
        chips += (f'<button type="button" class="gc-chip{" is-on" if on else ""}" '
                  f'data-gc-filter="{key}" aria-pressed="{"true" if on else "false"}">'
                  f'<span>{esc(label)}</span>'
                  f'<b class="gc-chip-n">{sum(1 for g in D.GAMES if pred(g))}</b></button>')
    segs = "".join(f'<button type="button" class="gc-seg-o{" is-on" if k == "featured" else ""}" '
                   f'data-gc-sort="{k}" aria-pressed="{"true" if k == "featured" else "false"}">'
                   f'{esc(lab)}</button>' for k, lab in GC_SORTS)
    opts = "".join('<option value="%s">%s</option>' % (k, esc(lab)) for k, lab in GC_SORTS)
    # Both controls are always in the DOM and CSS picks one — the same technique
    # the Best Sellers band uses for its tier grid and its native select, and for
    # the same reason: a three-option segmented control does not fit beside the
    # count at 390px. They write one state; initCatalog() re-marks both.
    return f"""<div class="gc-tools">
      <div class="gc-chips" role="group" aria-label="Filter titles">{chips}</div>
      <div class="gc-sortwrap">
        {gc_count("gc-count-sm")}
        <span class="gc-sort-l">Sort</span>
        <div class="gc-seg" role="group" aria-label="Sort titles">{segs}</div>
        <div class="gc-sortsel">
          {_ico("filter", 14, "gc-sortsel-i", stroke=True)}
          <span class="gc-sortsel-t" data-gc-sortlabel>{esc(GC_SORTS[0][1])}</span>
          {_CARET}
          <select class="gc-sortsel-s" data-gc-sortsel aria-label="Sort titles">{opts}</select>
        </div>
      </div>
    </div>"""


def gc_catalog():
    """The catalogue band: head, toolbar, grid, and the filtered footer.

    Every card is server-rendered in catalogue order, so the grid is complete and
    correctly ordered with no JS and legible to a crawler; initCatalog() only
    hides and re-orders what is already there. Same trade-off the roster board
    and the reviews feed make, and the same reason: this is the page a search
    engine reads to learn which titles exist.
    """
    lead = D.GAMES[0]
    cards = "".join(gc_card(g, i, featured=(g is lead)) for i, g in enumerate(D.GAMES))
    return f"""<section class="gc-band gc-cat">
  <div class="gc-glow" aria-hidden="true"></div>
  <div class="wrap gc-inner">
    <div class="gc-head">
      <div class="gc-head-l">
        <span class="gc-kicker">{esc(spell(len(D.GAMES)).capitalize())} games</span>
        <h1 class="gc-h1">Pick your game.</h1>
      </div>
      <p class="gc-head-p"><span>Prices are per division and shown before you sign in.
      Placements, net wins and duo on every title, coaching on</span>
      <b>{len(gc_facts()['coach'])}</b> <span>of them.</span></p>
    </div>
    {gc_toolbar()}
    <div class="gc-grid" data-gc-grid>{cards}</div>
    <div class="gc-foot" data-gc-foot hidden>
      {gc_count()}
      <button type="button" class="gc-reset" data-gc-reset>
        {_ico("undo", 13, "ico gc-reset-i", stroke=True)}<span>Show all {esc(spell(len(D.GAMES)))}</span>
      </button>
    </div>
  </div>
</section>"""


def gc_eyebrow(num, label):
    """The handoff's numbered marker — the site's shared `.sec-kicker`, restyled
    inside `.gc` exactly as `.sg` restyles it: an ember figure, a 14px rule, the
    label in body type. Two ports of the same handoff family, one component."""
    return sec_kicker(num, label)


def gc_services():
    """Band 01 — the four services, each ending in the "best for" line.

    That line is the whole band: most people cannot tell net wins from
    placements, and one plain sentence resolves it. Pinned with `margin-top:auto`
    so the four align across bodies of unequal length.

    The figures in the copy are substituted, not typed — the units cap is
    `pricing.UNIT_MAX` (the same constant `unit_grid()` draws five buttons from)
    and the coaching count is the catalogue's.
    """
    facts = gc_facts()
    fills = {"cap": spell(pricing.UNIT_MAX), "coach": spell(len(facts["coach"])),
             "n": spell(len(D.GAMES))}
    cards = ""
    for icon, name, body, best in D.CATALOG_SERVICES:
        cards += f"""<article class="gc-svc-card">
          <span class="gc-tile">{_ico(icon, 19, "ico", stroke=True)}</span>
          <h3 class="gc-svc-t">{esc(name)}</h3>
          <p class="gc-svc-b">{esc(body.format(**fills))}</p>
          <span class="gc-best">
            <span class="gc-best-l">Best for</span>
            <span class="gc-best-t">{esc(best)}</span>
          </span>
        </article>"""
    return f"""<section class="gc-band">
  <div class="wrap gc-inner">
    <div class="gc-head">
      <div class="gc-head-l">
        {gc_eyebrow("01", "Which service")}
        <h2 class="gc-h2">Four ways to buy a climb.</h2>
      </div>
      <p class="gc-head-p">Every title sells the first three. If you are not sure which one you
      want, read the "best for" line — it is usually the whole answer.</p>
    </div>
    <div class="gc-svcs-grid">{cards}</div>
  </div>
</section>"""


def gc_how():
    """Band 02 — three steps, and the proof beside them.

    The steps are D.STEPS (the site's one copy of them) and the right column is
    `roster_panel()`: who is on shift now, then the Discord card. That panel is
    what turns "N boosters" from a claim into something inspectable, and it reads
    BOOSTERS live through initBoosters() like every other place it renders.
    """
    rows = ""
    for n, t, b in D.STEPS:
        rows += f"""<div class="gc-step">
          <span class="gc-step-n">{esc(n)}</span>
          <span class="gc-step-c">
            <span class="gc-step-t">{esc(t)}</span>
            <span class="gc-step-b">{esc(b)}</span>
          </span>
        </div>"""
    return f"""<section class="gc-band gc-how">
  <div class="gc-glow gc-glow-r" aria-hidden="true"></div>
  <div class="wrap gc-how-grid">
    <div class="gc-how-l">
      {gc_eyebrow("02", "How it runs")}
      <h2 class="gc-h2 gc-h2-tight">Three steps, then it's out of your hands</h2>
      <div class="gc-steps">{rows}</div>
    </div>
    {roster_panel()}
  </div>
</section>"""


def gc_trust():
    """The trust band — D.GUARANTEES in the guarantee page's own card shell.

    Nothing new is claimed here: `promise_cards()` is the component and the
    entries are the same three promises, so the objections a buyer would
    otherwise discover at checkout are answered in the wording the policy page
    uses. On the phone the three become a snap rail with dots — see the note at
    the head of this section for why they do not rotate themselves.
    """
    # Real controls, so they are labelled and keep their pressed state rather
    # than being hidden decoration — a focusable button inside an aria-hidden
    # container is a trap for anyone arriving by keyboard. They are display:none
    # above 760px, which takes them out of the tab order with the rail.
    dots = "".join(f'<button type="button" class="gc-dot{" is-on" if i == 0 else ""}" '
                   f'data-gc-dot="{i}" aria-pressed="{"true" if i == 0 else "false"}" '
                   f'aria-label="{esc(t)}"></button>'
                   for i, (_i, _s, _k, t, _b, _p) in enumerate(D.GUARANTEES))
    return f"""<section class="gc-band">
  <div class="wrap gc-inner">
    {promise_cards()}
    <div class="gc-dots" data-gc-dots role="group" aria-label="Promises">{dots}</div>
  </div>
</section>"""


def gc_faq_items():
    """The five questions, with every figure substituted from the engine.

    The two prices in the "why do titles differ" answer are `pricing.quote()`
    through `from_price()`, and the pair they compare is the catalogue's actual
    cheapest and dearest — the handoff types "Valorant vs Dota", which stops
    being the right pair the moment a factor is re-tuned.
    """
    facts = gc_facts()
    code, promo = D.auto_promo()
    # The third element of a BUNDLES tuple is the hand-set FLAT PRICE in whole
    # USD, not a discount fraction — reading it as one published "bundle climbs
    # at 1500% to 30500% off" here and, worse, asserted it verbatim in the
    # FAQPage JSON-LD. The reduction is derived from that price against the full
    # climb by pricing.bundle_pct(), which is what the strip's own −N% pill
    # reads, so the answer and the nine game pages now state one number.
    discs = [pricing.bundle_pct(g, b) for g in D.GAMES for b in D.bundle_climbs(g)]
    discs = [d for d in discs if d > 0]
    lo, hi = (min(discs), max(discs)) if discs else (0, 0)
    # Only assert "the larger of the two" while it is arithmetically true. If a
    # sitewide code is ever raised past the cheapest bundle, the sentence stops
    # making the claim instead of quietly becoming false.
    pct = (promo or {}).get("pct", 0)
    oneof = ", and it is the larger of the two" if discs and lo >= pct else ""
    # `usd()`, not `money()`: an answer is one escaped text node and the same
    # string is asserted verbatim in the FAQPage JSON-LD, so a `.money` span
    # would print as markup here and ship as markup to search engines. The cost
    # is that these two figures stay in USD when the currency switches — the
    # cards above them, which are the buying surface, do convert.
    fills = {
        "n": spell(len(D.GAMES)),
        "cheap": facts["cheap"]["name"], "cp": usd(from_price(facts["cheap"])),
        "dear": facts["dear"]["name"], "dp": usd(from_price(facts["dear"])),
        "code": code or "The sitewide code", "pct": "%g%%" % round(pct * 100, 2),
        "lo": "%g%%" % round(lo * 100), "hi": "%g%%" % round(hi * 100),
        "oneof": oneof,
    }
    return [(fid, q.format(**fills), a.format(**fills)) for fid, q, a in D.CATALOG_FAQ]


def gc_faq(items):
    """Band 04 — the sticky column and the shared accordion.

    `sg_faq()` is the safety/support component: single-open, item 1 open on load,
    every answer in the DOM (the FAQPage JSON-LD asserts they are on the page, so
    they have to be) and a stable `#faq-<id>` per item that support can link at.
    """
    return f"""<section class="gc-band gc-faq-band" id="faq">
  <div class="wrap gc-faq-grid">
    <div class="gc-faq-copy">
      {gc_eyebrow("04", "FAQ")}
      <h2 class="gc-h2 gc-h2-sm">Asked on this page</h2>
      <p class="gc-faq-note">Title-specific questions live on each game's page. These are the
      ones about all {esc(spell(len(D.GAMES)))}.</p>
      <a class="btn btn-outline btn-sm gc-ask" href="/support.html">{_ico("chat", 15, "ico")}Ask support</a>
    </div>
    {sg_faq(items)}
  </div>
</section>"""


def gc_bar(lead):
    """The phone's sticky action bar.

    One action, not the handoff's two: "Compare all titles" has no page behind
    it. The bar is `position: fixed` rather than sticky — the handoff's frame is
    860px tall and a real page is not — and it hides itself while the header
    sheet is open, the same way `.mobile-bar` does.
    """
    return f"""<div class="gc-bar" role="region" aria-label="Start an order">
  <a class="btn btn-primary gc-bar-cta" href="/games/{lead['slug']}.html">
    <span>Start with {esc(lead.get('tab') or lead['short'])}</span>{_ico("arrow", 15, "ico", stroke=True)}
  </a>
</div>"""


def page_games_index():
    lead = D.GAMES[0]
    faq = gc_faq_items()
    n = spell(len(D.GAMES)).capitalize()
    body = f"""<div class="gc">
  <div class="gc-hatch" aria-hidden="true"></div>
  {gc_catalog()}
  {gc_services()}
  {gc_how()}
</div>

{dashboard_section("03", note="Same dashboard on all %s titles. It opens from the link we email "
                              "you — no password, no app — and updates as games finish."
                              % spell(len(D.GAMES)))}

<div class="gc">
  {gc_trust()}
  {gc_faq(faq)}
</div>

{cta_band(title="%s titles, one guarantee." % n,
          sub="Refunded in full until a booster claims it, pro-rated after that, and claimed in "
              "%s on average." % D.STATS["median_claim"],
          cta=("Start with %s" % (lead.get("tab") or lead["short"]),
               "/games/%s.html" % lead["slug"]))}

{gc_bar(lead)}"""
    return layout("/games", "All Games Boosting - %s" % D.BRAND,
                  "Rank boosting for League of Legends, Valorant, CS2, TFT, Marvel Rivals, Dota 2, "
                  "Apex, Overwatch 2 and Rocket League. Live prices, no account needed.",
                  body, current="/games",
                  jsonld=[faq_ld([(q, a) for _fid, q, a in faq])],
                  extra_js=faq_accordion_js(), body_class="gc-page")


# ══════════════════════════════════════════════════════════════════════════
#  game-page proof bands — design_handoff_lol_game_page, bands 01–06 + close
#
#  A full-fidelity port of the handoff's below-the-fold page: one numbered band
#  each for how it runs, what you watch while it runs, who plays it, why it is
#  safe, what buyers said, and the six questions. Scoped on `.gp` (its own token
#  set, same ember palette as the hero and the Best Sellers band). The bands 02
#  order preview reuses `dash_mock()` and 06 reuses `faq_block()` — the site's
#  canonical ports of the dashboard and support handoffs this one references —
#  so the game page cannot drift from them. Every price is still the shared
#  engine's; nothing here quotes a number of its own.
# ══════════════════════════════════════════════════════════════════════════
def _ago_days(days):
    """"3 days ago" / "1 week ago" — the review footer's relative date. Weeks
    once it passes seven days, so a two-month-old review doesn't read "63 days"."""
    try:
        d = max(0, int(days))
    except (TypeError, ValueError):
        d = 0
    if d <= 0:
        return "today"
    if d == 1:
        return "1 day ago"
    if d < 7:
        return "%d days ago" % d
    w = d // 7
    return "1 week ago" if w == 1 else "%d weeks ago" % w


def gp_eyebrow(num, label):
    return (f'<div class="gp-eyebrow"><span class="gp-eyebrow-n">{num}</span>'
            f'<span class="gp-eyebrow-bar" aria-hidden="true"></span>'
            f'<span class="gp-eyebrow-l">{esc(label)}</span></div>')


# 01 — the four steps. Icons are the site's linework glyphs (the handoff's
# Phosphor duotone set isn't shipped); the proof line is a checkable fact under
# each claim, one read off STATS so it can't drift.
def gp_steps(g):
    """The four steps. `%s` is the game's short name, so step 02 reads "a
    verified League booster" the way the handoff draws it."""
    tab = g.get("tab") or g["short"]
    claim = D.STATS["median_claim"].replace("min", "minutes")
    return [
        ("filter", "Configure and pay",
         "The number you see is the number you pay. Nothing is added later, and no account is "
         "needed to buy.", "Price fixed at checkout"),
        ("user", "A booster claims it",
         "It goes on the board and a verified %s booster takes it. If nothing claims it within "
         "24 hours, the order refunds itself." % tab, "Median %s" % claim),
        ("chart-up", "Watch it climb",
         "Every game appears on your order page with the result, the KDA and the LP swing. Pause "
         "it any time you want to play.", "Updated as games finish"),
        ("shield-check", "Finished, or refunded",
         "Delivered to the rank you set. Anything not delivered is refunded pro-rata, any time the "
         "order is open.", "Back within 5 business days"),
    ]


def gp_how(g):
    cards = ""
    for i, (icon, title, body, proof) in enumerate(gp_steps(g)):
        cards += f"""<div class="gp-step">
          <div class="gp-step-top">
            <span class="gp-step-ico">{_ico(icon, 19, "ico", stroke=True)}</span>
            <span class="gp-step-num">{i + 1:02d}</span>
          </div>
          <span class="gp-step-t">{esc(title)}</span>
          <p class="gp-step-b">{esc(body)}</p>
          <span class="gp-step-proof">{esc(proof)}</span>
        </div>"""
    return f"""<section class="gp-sec">
      <div class="wrap gp-inner">
        <div class="gp-head">
          <div class="gp-head-l">
            {gp_eyebrow("01", "How it runs")}
            <h2 class="gp-h2">Four steps, and you can see all of them.</h2>
          </div>
        </div>
        <div class="gp-steps">{cards}</div>
      </div>
    </section>"""


# 02 — the three things the order page gives you (the handoff's DASH_POINTS,
# distinct from the homepage's D.DASHBOARD_POINTS).
# {unit} is the game's ranking unit — "LP" on League, "RR" on Valorant — filled
# per page in gp_while(), so the bullets never quote League terms on a Valorant
# page. These strings are English-only (no i18n entries), so the substitution
# does not un-translate anything.
GP_WHILE_POINTS = [
    ("chart-up", "The {unit} graph, not a percentage",
     "Every game plotted from the rank you started at, so a bad night is visible instead of "
     "averaged away."),
    ("list-search", "Match history with replays",
     "Result, KDA and {unit} for every game, each with a replay link that stays live for 14 days."),
    ("chat", "One thread with your booster",
     "Ask for a champion, a pause or a swap. Support reads the same thread, so nothing gets "
     "repeated."),
]


def gp_while(g):
    order, gobj = game_demo_order(g)
    unit = order["unit"]
    points = ""
    for icon, name, note in GP_WHILE_POINTS:
        points += f"""<div class="gp-dp">
          {_ico(icon, 19, "gp-dp-ico", stroke=True)}
          <span class="gp-dp-txt"><span class="gp-dp-name">{esc(name.format(unit=unit))}</span>
          <span class="gp-dp-note">{esc(note.format(unit=unit))}</span></span>
        </div>"""
    return f"""<section class="gp-sec">
      <div class="gp-while-glow" aria-hidden="true"></div>
      <div class="wrap gp-inner gp-while">
        <div class="gp-while-copy">
          {gp_eyebrow("02", "While it runs")}
          <h2 class="gp-h2 gp-h2-tight">Watch every game land.</h2>
          <p class="gp-p">The order page opens from the link we email you — no password, no app. It
          updates as games finish, so you never have to ask where things are.</p>
          <div class="gp-dps">{points}</div>
        </div>
        <div class="gp-while-mock">{dash_mock(gp=True, order=order, game=gobj)}</div>
      </div>
    </section>"""


def gp_brow(g, b, top=False):
    """One booster row on the game page's roster board. A <div> holding two
    independent targets — the name links to the profile, the CTA carries the
    booster into this game's configurator (?booster=<handle>, the same link the
    roster's Hire and the spotlight card use; it never touches the price). The
    availability ring and the queue pill both read `queue`, so they can't drift.
    """
    order_href = "/games/%s.html?booster=%s" % (g["slug"], b["handle"])
    tint = D.tier_color(g, b["tier"])
    badge = (f'<span class="gp-brow-top">{_ico("crown", 11, "ico", stroke=True)}'
             f'<span>Top booster</span></span>') if top else ""
    return f"""<div class="gp-brow{' is-top' if top else ''}">
      <a class="gp-brow-who" href="{booster_href(b)}">
        <span class="gp-brow-ring rst-ring{'' if is_free(b) else ' is-busy'}">{booster_face(b)}</span>
        <span class="gp-brow-id">
          <span class="gp-brow-name">{esc(b["handle"])}{badge}</span>
          <span class="gp-brow-rank"><i class="gp-brow-tdot" style="--tier:{esc(tint)}" aria-hidden="true"></i>{esc(b["peak"])} <i aria-hidden="true">·</i> {esc(b["region"])}</span>
        </span>
      </a>
      <div class="gp-brow-stats">
        <span class="gp-brow-stat"><b>{esc(str(b["orders"]))}</b><span>Orders</span></span>
        <span class="gp-brow-stat"><b>{_ico("star", 12, "gp-brow-star")}{esc(b["rating"])}</b><span>Rating</span></span>
        <span class="gp-brow-stat gp-brow-ontime"><b>{esc(b["ontime"])}</b><span>On time</span></span>
      </div>
      <span class="gp-brow-role">{_ico("crosshair", 14, "gp-dp-ico", stroke=True)}{esc(b["role"])}</span>
      {queue_pill(b, "gp-brow-pill")}
      <a class="gp-brow-cta" href="{esc(order_href)}"><span>Order with</span> <b>{esc(b["handle"])}</b>{_ico("arrow", 14, "ico", stroke=True)}</a>
    </div>"""


def gp_who(g, roster):
    n = len([b for b in D.BOOSTERS if b["slug"] == g["slug"]]) or len(roster)
    tab = g.get("tab") or g["short"]
    # The floor the board is held to, read off the roster rather than typed:
    # the lowest peak tier any booster on this ladder holds.
    own = [b for b in D.BOOSTERS if b["slug"] == g["slug"]] or roster
    floor_tier = min((b["tier"] for b in own),
                     key=lambda t: g["tiers"].index(t) if t in g["tiers"] else 99)
    shown = roster[:3]
    rows = "".join(gp_brow(g, b, top=(i == 0)) for i, b in enumerate(shown))
    # "N more on the roster" — counted, never typed; the link lands on the same
    # full board "See the roster" does. Only drawn when there is genuinely more
    # behind it, so it is never a dead pointer to nothing.
    rest = max(0, n - len(shown))
    noun = "booster" if rest == 1 else "boosters"
    foot = (f"""<div class="gp-brow-foot">
        <span class="gp-brow-foot-t">{_ico("users", 15, "gp-dp-ico", stroke=True)}<span><b>{rest}</b> more {esc(tab)} {noun}</span> <i aria-hidden="true">on the roster, all {esc(floor_tier)} or above.</i></span>
        <a class="gp-brow-all" href="/boosters">See all <b>{n}</b>{_ico("arrow", 13, "ico", stroke=True)}</a>
      </div>""") if rest else ""
    return f"""<section class="gp-sec">
      <div class="wrap gp-inner gp-who">
        <div class="gp-who-copy">
          {gp_eyebrow("03", "Who plays it")}
          <h2 class="gp-h2 gp-h2-sm">Our {esc(tab)} boosters.</h2>
          <p class="gp-p gp-p-sm">{spell(n).capitalize()} of them, {esc(tab)} only — {esc(floor_tier)}
          or above, with a clean account history and a name you can look up. Order without naming
          anyone and it goes to whoever is free; name one and it waits for them.</p>
          <span class="gp-who-rule" aria-hidden="true"></span>
          <ul class="gp-who-feats">
            <li>{_ico("seal", 15, "gp-dp-ico", evenodd=True)}<span>Rank verified every month</span></li>
            <li>{_ico("undo", 15, "gp-dp-ico", stroke=True)}<span>One free swap, no reason needed</span></li>
          </ul>
          <a class="gp-outline" href="/boosters">See the roster{_ico("arrow", 14, "ico", stroke=True)}</a>
        </div>
        <div class="gp-who-board">{rows}{foot}</div>
      </div>
    </section>"""


# 04 — the five per-order mechanisms, in the handoff's wording. Same commitments
# as D.SAFETY["measures"] (which every other page still uses); ⚠ each is an
# operational promise falsifiable by one bad order, so it needs ops sign-off.
GP_MEASURES = [
    ("globe", "Enterprise VPN matched to your region",
     "Not a consumer VPN, and never a datacentre IP."),
    ("crosshair", "Your sensitivity, your crosshair, your runes",
     "Settings are mirrored at the start and restored at the end."),
    ("clock", "Played inside your normal hours",
     "You set the window at checkout. Nothing runs at 04:00 unless you do."),
    ("eye-off", "Offline appearance for the whole order",
     "Friends see you offline until it finishes."),
    ("users", "Duo never touches your login",
     "In duo your booster queues beside you from their own account."),
]


def gp_safety(g):
    rows = ""
    for icon, name, note in GP_MEASURES:
        rows += f"""<div class="gp-measure">
          {_ico(icon, 19, "gp-dp-ico", stroke=True)}
          <span class="gp-dp-txt"><span class="gp-dp-name">{esc(name)}</span>
          <span class="gp-dp-note">{esc(note)}</span></span>
        </div>"""
    pub = D.publisher(g)
    # The ToS admission, named to this game's publisher. Same commitment as
    # D.SAFETY["disclaimer"] (which the guarantee page still carries verbatim);
    # the order count is read off STATS rather than typed.
    disclaimer = (
        "Boosting is against %s's terms of service. We have never had an account actioned for "
        "any of our %s clients and we recover any that are, but nobody honest will tell you "
        "the risk is zero — and anyone who does is selling you something."
        % (pub, D.STATS["clients"]))
    return f"""<section class="gp-sec">
      <div class="wrap gp-inner gp-safety">
        <div class="gp-safety-copy">
          {gp_eyebrow("04", "Safety")}
          <h2 class="gp-h2 gp-h2-safe">Why this doesn't get you banned.</h2>
          <p class="gp-p">{esc(pub)} flags accounts on patterns, not accusations: a login from the
          other side of the world, a sudden change in hours, a win rate that doesn't look human. So
          we don't produce any of those patterns. Your booster connects through an enterprise VPN in
          your region, plays inside the hours you set, and keeps your settings.</p>
          <div class="gp-disclaimer">
            {_ico("warn", 18, "gp-disc-ico")}
            <span>{esc(disclaimer)}</span>
          </div>
        </div>
        <div class="gp-measure-card">
          <div class="gp-measure-head">
            <span class="gp-measure-t">What that means per order</span>
            <span class="gp-measure-pill">{_ico("seal", 11, "ico", evenodd=True)}Every order</span>
          </div>
          {rows}
        </div>
      </div>
    </section>"""


def gp_reviews(g, revs):
    if not revs:
        return ""
    cards = ""
    for r in revs[:3]:
        try:
            sc = max(1, min(5, int(str(r["stars"])[0])))
        except (ValueError, IndexError):
            sc = 5
        stars = "".join(_ico("star", 13, "gp-rv-star") for _ in range(sc))
        cards += f"""<div class="gp-rv-card">
          <div class="gp-rv-top">
            <span class="gp-rv-stars">{stars}</span>
            <span class="gp-rv-climb">{esc(r["rank"])}</span>
          </div>
          <p class="gp-rv-body">{esc(r["text"])}</p>
          <div class="gp-rv-foot">
            <span class="gp-rv-av" aria-hidden="true">{esc(r.get("initials", ""))}</span>
            <span class="gp-rv-who"><b>{esc(r.get("by", ""))}</b> · {esc(_ago_days(r.get("days", 1)))}</span>
            <span class="gp-rv-verified">{_ico("seal", 12, "ico", evenodd=True)}Verified</span>
          </div>
        </div>"""
    rating = D.STATS.get("trustpilot", "").split("/")[0].strip()
    tp_star = ('<svg class="gp-rv-tp" width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" '
               'focusable="false"><path d="M12 2l2.6 6.8H22l-6 4.5 2.3 7L12 15.9 5.7 20.3 8 13.3 2 8.8h7.4z" '
               'fill="#00b67a"/></svg>')
    aside = ""
    if rating:
        aside = f"""<div class="gp-rv-aside">
          <div class="gp-rv-score">
            <div class="gp-rv-rating"><span class="gp-rv-big">{esc(rating)}</span>
              <span class="gp-rv-outof">/ 5</span></div>
            <!-- The Trustpilot count, not the whole corpus: the line names them.
                 The score above it is still the corpus average — see STATS. -->
            <span class="gp-rv-tpline">{tp_star}<span>{esc(D.STATS["trustpilot_reviews"])} reviews on Trustpilot</span></span>
          </div>
          <a class="gp-rv-all" href="/reviews.html">Read them all{_ico("arrow-up-right", 13, "ico", stroke=True)}</a>
        </div>"""
    tab = g.get("tab") or g["short"]
    return f"""<section class="gp-sec">
      <div class="wrap gp-inner">
        <div class="gp-head">
          <div class="gp-head-l">
            {gp_eyebrow("05", "Reviews")}
            <h2 class="gp-h2 gp-h2-sm">From {esc(tab)} orders this month.</h2>
          </div>
          {aside}
        </div>
        <div class="gp-rv-grid">{cards}</div>
      </div>
    </section>"""


def gp_faq_items(g):
    """The six questions the handoff draws, per game. Every figure inside them is
    read off the engine, never typed: the duo uplift from pricing.DUO_MULT, the
    champions add-on from a real quote difference, the claim time from STATS."""
    duo = round((pricing.DUO_MULT - 1) * 100)
    champ = next((a for a in D.ADDONS if a["id"] == "champ"), None)
    # What the picks add-on costs on this page's default order — read off the
    # engine, never typed. It is free today, so the answer says so; give it a
    # percentage again in data.py and the same line quotes the real difference.
    #
    # usd(), not money(): the answer is escaped as one text node in gp_faq() AND
    # asserted verbatim in the FAQPage JSON-LD, so a money() `.money` span would
    # print as literal markup on the page (and in the structured data). Same
    # trade-off the /games/ catalogue FAQ makes — this figure stays in USD when
    # the currency switches.
    champ_line = ""
    if champ and champ["pct"]:
        base = {"game": g["name"], "service": "division", "from": g["ladder"][0],
                "to": g["ladder"][min(12, len(g["ladder"]) - 1)], "mode": "Solo"}
        off = pricing.quote(dict(base, addons=[]))["total"]
        on = pricing.quote(dict(base, addons=["champ"]))["total"]
        champ_line = ("It is an add-on, %s on this order. Your booster plays a pool you pick, "
                      "which also keeps the match history plausible. You can change the pool "
                      "mid-order in the thread." % usd(on - off))
    elif champ:
        champ_line = ("It is free on every order, not an upsell — \"%s\" is ticked before you "
                      "configure anything. Your booster plays a pool you pick, which also keeps "
                      "the match history plausible, and you can change it mid-order in the "
                      "thread." % D.picks_label(g["name"]))
    return [
        ("Do you need my account login?",
         "For solo, yes — your booster signs in and plays, through a VPN in your region and inside "
         "the hours you set. For duo, no: they queue beside you from their own account and never "
         "see your login at all. Either way we never ask for your email password or your 2FA codes."),
        ("Can I play while the order is running?",
         "Pause it first, from the order page. Pausing is free and resumes the same night if a slot "
         "is open. What you should not do is queue ranked alongside an unpaused solo order — two "
         "people on one account in the same queue is the fastest way to get flagged."),
        ("What happens if it goes past the estimate?",
         "A 15% credit applies automatically once the order runs past its window, and it shows on "
         "the order page without anyone asking. If it is badly over, we move it to a booster who "
         "is free."),
        ("Can I choose the %s they play?" % D.picks_noun(g["name"]), "Yes — " + champ_line),
        ("Why is duo more expensive?",
         "It takes longer. Your booster carries a live player rather than playing every role "
         "freely, so the same climb costs %d%% more and takes longer. It is the safer option and "
         "we would rather price it honestly than hide the difference." % duo),
        ("How do I follow the order without an account?",
         "The confirmation email carries a link that is the login. It never expires, works on any "
         "device, and opens the same dashboard shown above. Lost it? The demo page resends it to "
         "the address you paid with."),
    ]


def gp_faq(g, items):
    """Single-open accordion, item 1 open on load, numbered, with a +/− toggle.

    Native <details>/<summary> so every answer is in the DOM (the FAQPage JSON-LD
    asserts they are on the page) and the band works with scripting off; the
    single-open behaviour is one small handler in app.js.
    """
    rows = ""
    for i, (q, a) in enumerate(items):
        rows += f"""<details class="gp-faq-item"{' open' if i == 0 else ''}>
          <summary><span class="gp-faq-n">{i + 1:02d}</span><span class="gp-faq-q">{esc(q)}</span>
            <span class="gp-faq-pm" aria-hidden="true"></span></summary>
          <p class="gp-faq-a">{esc(a)}</p>
        </details>"""
    tab = g.get("tab") or g["short"]
    return f"""<section class="gp-sec">
      <div class="wrap gp-inner gp-faq">
        <div class="gp-faq-copy">
          {gp_eyebrow("06", "FAQ")}
          <h2 class="gp-h2 gp-h2-sm">Asked before every {esc(tab)} order</h2>
          <p class="gp-p gp-p-sm">If yours isn't here, Discord answers in about four minutes and you
          don't need an order to ask.</p>
          <a class="gp-outline" href="/support.html">{_discord_mark(16, "ico")}Ask in Discord</a>
        </div>
        <div class="gp-faq-list" data-gp-faq>{rows}</div>
      </div>
    </section>"""


def gp_close():
    """The last band — headline, two guarantees, the live configuration and total,
    and the one filled CTA. Reads the same `data-out` hooks the order card does,
    so the number here and the number in the card are one computation.

    Deliberately not the shared `cta_band()`: that draws a full configuration card
    (the footer handoff's close), and this page's handoff closes on a single line
    of read-back beside the button.
    """
    return f"""<section class="gp-sec gp-close">
      <div class="gp-close-glow" aria-hidden="true"></div>
      <div class="wrap gp-inner gp-close-inner">
        <div class="gp-close-l">
          <h2 class="gp-h2 gp-h2-close">Set two ranks. The price is the price.</h2>
          <div class="gp-close-gtees">
            <span class="gp-close-g">{_ico("shield-check", 16, "gp-close-ico", stroke=True)}Refunded in full until a booster claims it</span>
            <span class="gp-close-g">{_ico("timer", 16, "gp-close-ico", stroke=True)}Claimed in {esc(D.STATS["median_claim"].replace("min", "minutes"))} on average</span>
          </div>
        </div>
        <div class="gp-close-r">
          <div class="gp-close-quote">
            <span class="gp-close-cfg" data-out="configLine">—</span>
            <span class="gp-close-total" data-out="price">—</span>
          </div>
          <a class="gp-close-cta" href="/checkout.html" data-continue>
            Continue to checkout{_ico("arrow", 15, "ico", stroke=True)}
          </a>
        </div>
      </div>
    </section>"""


# ══════════════════════════════════════════════════════════════════════════
#  The mystery discount — design_handoff_mystery_discount
# ══════════════════════════════════════════════════════════════════════════
# A modal sequence that fires on a game page eight seconds after the visitor's
# target-rank selection settles. It offers a sealed "mystery discount", takes an
# email in exchange for opening it, reveals a 30% code and hands the buyer back
# to their order with the discount already applied.
#
# It exists for one reason: the configurator proves intent — somebody who set two
# ranks and read a price is a buyer — and captures nothing if they leave. This
# trades a discount for an address at the moment intent is highest.
#
# ── The mechanic, and what the copy is therefore allowed to say ────────────
# The deck shows three sealed cards. **Every card pays the same 30%**
# (`mystery.OFFER_PCT`) — the pick is theatre, not chance. The handoff is
# emphatic about the consequence and so is this port: the flow must never claim
# the 30% was luck, that the buyer beat odds, or state any probability. Two
# friends comparing cards, or one buyer opening a second tab, finds out in about
# ten seconds, and a discovered lie on a store whose central pitch is "the price
# does not move after checkout" costs far more than the twenty margin points.
#
# Two sentences of the handoff's own copy are **deliberately not shipped**, for
# exactly that rule — they are the only places its prototype states something the
# flat deck makes untrue:
#
#   * "The deck holds 10%, 20% and 30% off" — a claim about the deck's
#     composition. It has one value in it. The band still reads "Up to 30%",
#     which is true (and understated) whatever the deck holds.
#   * "Bingo — card C was the best one" — "best" implies the others were worse.
#     It reads "card C pays the top rate", which is true of every card and is
#     still the emotional peak the handoff asks for.
#
# "on your first order" went the same way. Nothing here can tell a first-time
# guest from a returning one before the modal fires, so the claim it makes is the
# one the server actually enforces: **one card per inbox, ever**
# (`mystery.find_by_email`). If an account backend ever lands, "first order" can
# come back — with a suppression rule behind it.
#
# ── What is server-side, and must stay there ───────────────────────────────
# The code is NOT minted here and is not `CLIMB30`: `D.PROMOS` ships to every
# browser in data.js, so a guessable pattern would be on a coupon aggregator
# within a week. `/api/bingo` issues one opaque single-use token per address,
# resolves the percentage server-side (`mystery.redeemable`), mails the code
# before this reveal renders, and burns it when the order is paid. The hour is
# enforced by the store, not by the countdown in this markup.
#
# ── i18n ──────────────────────────────────────────────────────────────────
# All five steps ship in the DOM with four of them `hidden`; a card written in by
# JS would arrive untranslated, the same rule the auth tabs and the
# mode-conditional add-ons follow. Figures and the card letter ride in their own
# nodes so the sentences around them stay whole translatable text nodes.
# ⚠ OFF. The card is not offered on the live site: mystery_modal() returns
# nothing, so no game page mounts `[data-myd]` and initMystery() finds no root
# and returns. Flip to True to put it back — it is one switch and no other code
# changed. What deliberately STAYS LIVE while it is off:
#
#   * mydBoot() still runs on every page, and /api/bingo?token= still resolves.
#     A code already in somebody's inbox keeps working for the hour it was sold
#     with; killing the modal must not strand a discount we already promised.
#   * The store, the mail sequence and the /ops Mystery tab are untouched. No new
#     cards are issued, so the rows drain on their own — nothing is left to warn
#     or chase once the oldest live card passes BINGO_FOLLOWUP_MAX_AGE.
#
# So this switch stops the OFFER, not the honouring of one. Turning the mails off
# as well is BINGO_FOLLOWUP_ENABLED in the environment, which is a separate call.
MYSTERY_MODAL_ENABLED = False

MYD_CARDS = ("A", "B", "C")
MYD_DEFAULT_PICK = "C"      # pre-selected so the CTA is never dead on arrival

# The three values the offer copy names. The TOP one IS the real payout
# (mystery.OFFER_PCT) and is derived from it, never typed: the deck's ceiling
# and the number the reveal quotes have to be the same figure or the card
# contradicts itself two screens apart. The two rungs below it are the decoys,
# rounded to a whole 5 so the list reads like a price list rather than
# arithmetic. Asserted distinct at import — a deck that advertised "10%, 10%
# and 10%" would ship on nine pages before anyone noticed.
def _myd_deck(pct):
    top = int(round(pct * 100))
    return (int(round(top / 3 / 5.0)) * 5, int(round(top * 2 / 3 / 5.0)) * 5, top)


MYD_DECK = _myd_deck(mystery.OFFER_PCT)
assert len(set(MYD_DECK)) == 3 and MYD_DECK[-1] == int(round(mystery.OFFER_PCT * 100)), (
    "MYD_DECK must be three distinct values topping out at mystery.OFFER_PCT: %r" % (MYD_DECK,))


def _myd_card(letter):
    """One sealed card. No value on the face — that is the mystery — and the
    "Picked" tag is pinned above the top edge rather than inside it, so choosing
    a card never reflows the row."""
    on = letter == MYD_DEFAULT_PICK
    return f"""<button type="button" class="myd-pick" data-myd-card="{letter}"
        aria-pressed="{'true' if on else 'false'}">
      <span class="myd-pick-tag">Picked</span>
      <span class="myd-pick-face">{_ico("question", 30, "myd-pick-ico", stroke=True)}</span>
      <span class="myd-pick-lab"><span>Card</span> <b>{letter}</b></span>
    </button>"""


def mystery_modal():
    """The five-step card. One root, one step visible, everything else `hidden`.

    `data-myd-view` on the root is the readable state, but the step that is
    actually on screen is the one without `hidden` — app.js toggles the
    attribute. That is not interchangeable with a CSS rule: `ashfall.css`
    declares `[hidden] { display: none !important }` globally, so a step
    rendered `hidden` here can never be revealed by a selector in site.css, at
    any specificity. Four of the five ship hidden so the page is correct before
    a line of JS runs.
    """
    return _myd_markup() if MYSTERY_MODAL_ENABLED else ""


def _myd_markup():
    """The card itself, built whether or not it is switched on.

    Split from mystery_modal() so the copy rules survive the switch:
    test_mystery.py's test_copy_claims_no_odds asserts against THIS, so the
    "no odds, no luck, the deck tops out at what is paid" guarantees keep being
    enforced while MYSTERY_MODAL_ENABLED is False. A card that is off is a card
    somebody will turn back on, and the copy has to still be honest when they do.
    """
    pct = int(round(mystery.OFFER_PCT * 100))
    mins = max(1, mystery.TOKEN_TTL // 60)
    hourly = "1 hour" if mins == 60 else "%d minutes" % mins
    auto = D.auto_promo()[1]
    sale = int(round((auto or {}).get("pct", 0) * 100))
    cards = "".join(_myd_card(c) for c in MYD_CARDS)
    # One node, not three: French puts a non-breaking space before every `%`
    # and joins with "et", so the list is a translatable phrase rather than
    # digits a mechanical substitution could assemble.
    deck = "%d%%, %d%% and %d%%" % MYD_DECK
    close = ('<button type="button" class="myd-x" data-myd-close aria-label="Close">'
             + _ico("x", 12, "ico", stroke=True) + "</button>")
    hair = '<span class="myd-hair" aria-hidden="true"></span>'

    return f"""<div class="myd" data-myd data-myd-view="offer" hidden>
  <div class="myd-back" data-myd-back></div>
  <div class="myd-scroll">

    <div tabindex="-1" class="myd-card" data-myd-step="offer" role="dialog" aria-modal="true"
         aria-labelledby="myd-offer-h">
      {hair}{close}
      <span class="myd-pill">{_ico("star", 12, "ico")}<span>Mystery discount</span></span>
      <div class="myd-head">
        <span class="myd-kicker"><span class="myd-dash" aria-hidden="true"></span>Sealed for you</span>
        <!-- The gradient takes the WHOLE line, not just the two words the
             handoff fills: splitting it leaves a bare "A" text node, and i18n.js
             matches whole text nodes — a dictionary entry for "A" would also
             rewrite the `<b>A</b>` that names the first sealed card. -->
        <span class="myd-h myd-h-grad" id="myd-offer-h">A mystery discount</span>
        <span class="myd-h-row">
          <span class="myd-h myd-h-2">on this order</span>
          <span class="myd-tag">One per customer</span>
        </span>
      </div>
      <div class="myd-band">
        <span class="myd-band-k">Up to</span>
        <span class="myd-band-n"><b data-myd-pct>{pct}</b>%</span>
        <span class="myd-band-u">off</span>
      </div>
      <p class="myd-p"><span>The deck holds</span> <b>{deck}</b> <span>off the order you just
      configured. Pick a card, tell us where to send the code, and we open it on the spot.</span></p>
      <div class="myd-picks">{cards}</div>
      <div class="myd-acts">
        <button type="button" class="myd-cta" data-myd-take>
          {_ico("lock-open", 16, "ico", stroke=True)}<span>Hold card</span> <b data-myd-pick>{MYD_DEFAULT_PICK}</b>
        </button>
        <button type="button" class="myd-ghost" data-myd-pass>No thanks, I'll pay full price</button>
      </div>
    </div>

    <div tabindex="-1" class="myd-card" data-myd-step="email" role="dialog" aria-modal="true"
         aria-labelledby="myd-email-h" hidden>
      {hair}{close}
      <div class="myd-email-head">
        <span class="myd-tile" data-myd-pick>{MYD_DEFAULT_PICK}</span>
        <span class="myd-email-t">
          <span class="myd-held"><span>Card</span> <b data-myd-pick>{MYD_DEFAULT_PICK}</b> <span>held for you</span></span>
          <span class="myd-h3" id="myd-email-h">Where should we send it?</span>
        </span>
      </div>
      <p class="myd-p myd-p-sm">We email the code so it survives a closed tab, then open the card
      on the next screen.</p>

      <label class="myd-lab" for="myd-email">Email</label>
      <input class="myd-input" id="myd-email" type="email" inputmode="email"
             autocomplete="email" spellcheck="false" placeholder="you@example.com"
             data-myd-email>
      <p class="myd-note" data-myd-note>The card is opened on the next screen either way.</p>

      <button type="button" class="myd-optin" data-myd-optin aria-pressed="false">
        <span class="myd-box" aria-hidden="true">{_ico("check", 10, "ico", stroke=True)}</span>
        <span class="myd-optin-t">Also send me the free rank guides and patch notes. One email a
        month, one click to stop.</span>
      </button>

      <button type="button" class="myd-cta myd-cta-mt" data-myd-open>
        {_ico("lock-open", 16, "ico", stroke=True)}<span>Open card</span> <b data-myd-pick>{MYD_DEFAULT_PICK}</b>
      </button>
      <p class="myd-fine myd-fine-c">{_ico("shield-check", 13, "ico", stroke=True)}<span>Never sold or
      rented.</span> <a href="/privacy.html">Privacy policy</a></p>
    </div>

    <div tabindex="-1" class="myd-card" data-myd-step="opening" role="dialog" aria-modal="true" hidden>
      {hair}
      <div class="myd-spin-wrap">
        <span class="myd-spin" aria-hidden="true"></span>
        <span class="myd-h3 myd-spin-t"><span>Opening card</span> <b data-myd-pick>{MYD_DEFAULT_PICK}</b></span>
        <span class="myd-note myd-note-c">Drawing your code on the server</span>
      </div>
    </div>

    <div tabindex="-1" class="myd-card myd-card-win" data-myd-step="reveal" role="dialog" aria-modal="true"
         aria-labelledby="myd-reveal-h" hidden>
      <span class="myd-hair myd-hair-win" aria-hidden="true"></span>{close}
      <div class="myd-rev-top">
        <span class="myd-won">{_ico("trophy", 12, "ico")}<span>Available for {hourly}</span></span>
        <span class="myd-timer">{_ico("clock-countdown", 12, "ico", stroke=True)}<b
          data-myd-timer aria-label="Time left on this code">59:59</b></span>
      </div>

      <div class="myd-prize" aria-live="polite">
        <span class="myd-prize-k" id="myd-reveal-h"><span>Bingo — card</span> <b data-myd-pick>{MYD_DEFAULT_PICK}</b>
          <span>pays the top rate</span></span>
        <span class="myd-prize-n"><b data-myd-pct>{pct}</b>%<i>off</i></span>
        <button type="button" class="myd-code" data-myd-copy>
          <b data-myd-code>—</b>{_ico("copy", 12, "ico", stroke=True)}
          <span class="myd-copied">Copied</span>
        </button>
        <span class="myd-prize-note">The best rate in the deck — double the {sale}% sale,
          and live for {hourly} from the moment you opened it.</span>
      </div>

      <div class="myd-tot">
        <span class="myd-tot-l">
          <span class="myd-tot-k">Your order</span>
          <span class="myd-tot-row"><s data-myd-was>—</s><b data-myd-now>—</b></span>
        </span>
        <span class="myd-tot-r">
          <span class="myd-tot-k">You save</span>
          <b class="myd-tot-save" data-myd-save>—</b>
        </span>
      </div>

      <div class="myd-acts">
        <button type="button" class="myd-cta" data-myd-apply>
          <span>Apply my discount</span>{_ico("arrow", 15, "ico", stroke=True)}
        </button>
        <button type="button" class="myd-ghost" data-myd-fullprice>
          <span>Continue at full price</span> <span aria-hidden="true">·</span> <b data-myd-full>—</b>
        </button>
      </div>
      <p class="myd-fine" data-myd-inbox>Live for {hourly} on this order. A copy is in your inbox,
      so closing this tab doesn't lose it.</p>
      <p class="myd-fine" data-myd-nomail hidden>Live for {hourly} on this order. Copy the code
      before you close this tab — we couldn't email it.</p>
    </div>

    <div tabindex="-1" class="myd-card" data-myd-step="passed" role="dialog" aria-modal="true"
         aria-labelledby="myd-passed-h" hidden>
      {close}
      <div class="myd-mid">
        <span class="myd-ring">{_ico("tag", 25, "myd-ring-ico", stroke=True)}</span>
        <span class="myd-h3" id="myd-passed-h" data-myd-passed-h>No problem.</span>
        <span class="myd-h3" data-myd-spent-h hidden>This address already used its card.</span>
        <p class="myd-p myd-p-c" data-myd-passed-p>Your order stays where it is and we won't ask
        again on this visit. The sitewide {sale}% code still applies at checkout.</p>
        <p class="myd-p myd-p-c" data-myd-spent-p hidden>One card per customer, and this inbox has
        opened its one. The sitewide {sale}% code still applies at checkout.</p>
        <button type="button" class="myd-ghost myd-ghost-mt" data-myd-close>Back to my order</button>
        <button type="button" class="myd-undo" data-myd-undo>Actually, let me pick a card</button>
      </div>
    </div>

  </div>
</div>"""


def gp_accounts_strip(g):
    """The cross-sell to /accounts.html, on the one game that has a board.

    Deliberately UNNUMBERED and after the FAQ. The six `.gp` bands are a numbered
    argument for buying a boost, and dropping a seventh into it would renumber
    five typed eyebrows and interrupt that run with an offer to buy something
    else. It sits where a reader who has finished the case is deciding — and it
    is a strip rather than a band because it is an alternative, not a pitch of
    equal weight.

    Returns "" for the other eight games and when nothing is in stock, so no page
    can advertise a board that isn't there — the same guard NAV makes.
    """
    if g["name"] != D.ACCOUNT_GAME or not D.accounts_in_stock():
        return ""
    return f"""<section class="gp-sec gp-acc">
      <div class="wrap gp-inner">
        <div class="gp-acc-card">
          <div class="gp-acc-l">
            <span class="gp-acc-k">{_ico("user-dashed", 15, "ico", stroke=True)}<span>Accounts</span></span>
            <h2 class="gp-acc-t">Or start on a second account.</h2>
            <p class="gp-acc-b"><span>Ready-made {esc(g['short'])} accounts from</span>
            <b>{ac_price_note()}</b> <span>— level 30 and ranked, on NA, EUW, EUNE and OCE,
            with full email access and a</span> <b>{D.ACCOUNT_WARRANTY_MONTHS}-month</b>
            <span>replacement. A boost is still the better buy if you want to keep
            your own name and skins.</span></p>
          </div>
          <a class="btn btn-outline gp-acc-cta" href="{ACCOUNTS_HREF}">
            <span>Browse accounts</span>{_ico("arrow", 15, "ico", stroke=True)}
          </a>
        </div>
      </div>
    </section>"""


def page_game(g):
    # money(), not usd(): this is the largest price on the page and the first
    # one a visitor reads, so it has to follow the currency switcher like every
    # other figure. A bare "$5" over a card quoting "€72" is the exact CRO
    # finding this build exists to answer. The .money span nests inside
    # .grad-text safely — the gradient is clipped to ALL descendant text and the
    # child inherits `color: transparent`, so the fill still shows through.
    fp = money(from_price(g))
    # This game's own boosters, capped: the board is 50 and League alone has 22,
    # which is a page of table inside a section that only has to establish that
    # real people cover this ladder. The full list is /boosters/.
    roster = [b for b in D.BOOSTERS if b["slug"] == g["slug"]][:6] or D.BOOSTERS[:4]
    def _for_game(r):
        token = r["game"].split(" · ")[0].strip().lower()
        return token in (g["name"].lower(), g["short"].lower()) or g["name"].lower().startswith(token)
    revs = [r for r in D.REVIEWS if _for_game(r)][:6]
    faq = gp_faq_items(g)

    product = {
        "@context": "https://schema.org", "@type": "Product",
        "name": "%s rank boosting" % g["name"], "description": g["meta"],
        "image": "%s/assets/img/keyart-%s.svg" % (D.SITE, g["slug"]),
        "brand": {"@type": "Brand", "name": D.BRAND},
        "offers": {"@type": "AggregateOffer", "priceCurrency": "USD",
                   "lowPrice": from_price(g),
                   "highPrice": quote(g["name"], g["ladder"][0], g["ladder"][-1])["total"],
                   "offerCount": len(g["ladder"]) * 2, "availability": "https://schema.org/InStock"},
    }
    product.update(rating_ld())

    # Hero stat row and the booster column are both pure claims about the
    # business. Each cell appears only if its number is real; with none of them
    # the row and the column vanish and the section falls back to one column.
    #
    # "Boosters free now" used to be the third cell here. It moved into the order
    # card, next to the delivery estimate, where availability is an argument for
    # ordering now rather than a statistic — and the promo bar's roster count and
    # this row's no longer state two different numbers in one viewport.
    # Each cell carries a full label and a short one; the phone shows the short
    # (the handoff abbreviates to "TRUSTPILOT / TO CLAIM / DELIVERED", and the
    # delivered figure to "92.4k"), CSS picks which. Both are in the DOM because
    # i18n.js matches whole text nodes.
    def _short_count(s):
        """"92,400" → "92.4k". Left alone if it isn't a plain number."""
        try:
            n = int(str(s).replace(",", ""))
        except ValueError:
            return s
        if n < 10000:
            return str(s)
        return ("%.1fk" % (n / 1000.0)).replace(".0k", "k")

    cells = [c for c in (
        (f'<div class="stat"><span class="stat-v"><b>{esc(D.STATS["trustpilot"].split("/")[0].strip())}</b>'
         f'<i>/ {esc(D.STATS["trustpilot"].split("/")[-1].strip())}</i></span>'
         f'<span class="stat-k"><span class="stat-k-full">Trustpilot</span>'
         f'<span class="stat-k-sm">Trustpilot</span></span></div>')
        if D.STATS["trustpilot"] else "",
        (f'<div class="stat"><span class="stat-v"><b>{esc(D.STATS["median_claim"].split(" ")[0])}</b>'
         f'<i>{esc(" ".join(D.STATS["median_claim"].split(" ")[1:]))}</i></span>'
         f'<span class="stat-k"><span class="stat-k-full">Booster time to claim</span>'
         f'<span class="stat-k-sm">To claim</span></span></div>') if D.STATS["median_claim"] else "",
        (f'<div class="stat"><span class="stat-v">'
         f'<b class="stat-n-full">{esc(D.STATS["clients"])}</b>'
         f'<b class="stat-n-sm">{esc(_short_count(D.STATS["clients"]))}</b></span>'
         f'<span class="stat-k"><span class="stat-k-full">Clients served</span>'
         f'<span class="stat-k-sm">Clients</span></span></div>') if D.STATS.get("clients") else "",
    ) if c]
    stat_row = ('<div class="stat-row">%s</div>' % "".join(cells)) if cells else ""

    ld = [
        product,
        faq_ld(faq),
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Games", "item": D.SITE + "/games"},
            {"@type": "ListItem", "position": 3, "name": g["name"],
             "item": "%s/games/%s" % (D.SITE, g["slug"])},
        ]},
    ]

    # The clipped game wordmark that used to sit behind this hero fought the H1
    # for the same space and lost twice; depth now comes from a warm radial glow
    # and a faint diagonal hatch, with the game's hue kept as the low corner
    # wash so the nine game pages still don't look like one page.
    body = f"""<section class="hero-a hero-a-lit" id="top" style="--game-hue:{g['hue']}">
  <div class="fx hero-a-glow" aria-hidden="true"></div>
  <div class="fx hero-a-hatch" aria-hidden="true"></div>
  <div class="fx fx-grain" aria-hidden="true"></div>
  <div class="wrap hero-a-inner">
    <div class="hero-copy" style="max-width:none">
      <nav class="crumbs crumbs-slash" aria-label="Breadcrumb">
        <a href="/">Home</a> <span aria-hidden="true">/</span> <a href="/games">Games</a>
        <span aria-hidden="true">/</span> <span class="crumbs-here">{esc(g['name'])}</span>
      </nav>
      <h1 class="h-lg" style="font-size:clamp(38px,5.4vw,68px)">{esc(g['name'])} boost<br><span class="grad-text">from {fp}.</span></h1>
      <p class="lede">{esc(g['blurb'])}</p>
      {stat_row}
      {bundle_strip(g)}
    </div>
    <div id="configure">{wizard(game=g['name'])}</div>
  </div>
</section>

<div class="gp">
{gp_how(g)}
{gp_while(g)}
{gp_who(g, roster)}
{gp_safety(g)}
{gp_reviews(g, revs)}
{gp_faq(g, faq)}
{gp_accounts_strip(g)}
</div>
{cta_band(live=True, cta=("Continue your order", "/checkout.html"))}
{mystery_modal()}"""

    # "<Game> boosting - eSports Boost" — a clean, consistent SERP title. The
    # longest game name ("Counter-Strike 2") lands at ~40 chars, well under
    # Google's ~60-char truncation point, so no length-fitting is needed.
    title = "%s Boosting - %s" % (g["name"], D.BRAND)
    return layout("/games/%s.html" % g["slug"],
                  title,
                  g["meta"], body, current="/games", jsonld=ld,
                  og_image=img("/assets/img/keyart-%s.svg" % g["slug"]), mobile_bar=True,
                  nav_outline=True)
# ══════════════════════════════════════════════════════════════════════════
#  /accounts.html — the League accounts shop  (`design_handoff_accounts_shop`)
#
#  The fifth product, and the only one that is not a service: a ready-made
#  account and a handover, sharing the checkout, the Stripe session and the
#  orders store with the four boosting products and nothing else. It reads none
#  of the rank engine — see pricing.quote()'s `service == "account"` branch.
#
#  The tenth scoped port after .hero-a / .co / .gg / .dsh / .rst / .tk / .hd /
#  .gc — tokens on `.ac`, product radii per element, nothing leaking past the
#  scope. It borrows `.gc`'s palette on purpose: the games catalogue and this
#  board are the same object, a filtered grid of things you can buy, and they
#  must not look like two products from two shops.
#
#  ── The two structural rules the handoff says are easy to reintroduce ─────
#
#  1 · **It is a two-step purchase, and the order is the design.** An account is
#    region-locked and cannot be transferred after sale, so the one irreversible
#    choice is made first, on a screen with nothing else on it. `ac_step_server()`
#    gates `ac_step_tiers()`; "Change server" returns and clears the filter and
#    the page. Do not "improve" this into one screen with a shard dropdown — the
#    dropdown is what the two-step layout exists to replace.
#
#  2 · **Stock is derived, never authored twice.** Four figures on this screen
#    state stock — the promo line, the server bar, each server card and each tier
#    card — and every one reduces to `D.account_stock()`. The version this
#    replaces authored a per-server figure by hand beside the per-listing one and
#    the two disagreed on screen. If real inventory arrives per (listing, shard),
#    it goes in at `account_stock()` and the other three follow for free.
#    ⚠ Nothing decrements these counts — see the ⚠ in data.py.
#
#  Everything else that is load-bearing:
#
#  · **The disclaimer is a framed plate above the fold of band 01, not an FAQ
#    row.** It is `D.ACCOUNT_DISCLAIMER`, verbatim, in the same caution amber
#    `gp_safety()` uses. On a page selling something risky the admission is the
#    credibility; a buyer who finds it in question two of an accordion has been
#    told after the decision.
#
#  · **One delivery promise, and it is `pricing.ACCOUNT_ETA`.** It appears in
#    the hero, the handover heading, step 02, every in-stock tier card, the
#    reviews band and the close. Six reads, one constant — composed with a
#    following word at each ("Instant Delivery", "in stock · instant") so the
#    one word still reads as English wherever it lands. ⚠ The scarce state is
#    the deliberate exception: under AC_SCARCE a card says "verified in 12 h"
#    and its CTA says Reserve, because that unit is NOT instant.
#
#  · **The rank marks are our own geometry, deliberately not Riot's emblems** —
#    the same trademark rule `pay_marks()`, the Trustpilot star and the rank
#    plate's `_EMBLEM` follow. `ac_mark()` draws a muted outer polygon with a
#    brighter inner facet, per listing. ⚠ The outer silhouette must stay above
#    ~3:1 against the card ground: an earlier version of the handoff had it at
#    34% and all eleven marks read as the same dot.
#
#  · **Tier colour is `D.account_tier_color()`, which is `tier_color()`.** The
#    site has ONE rank colour table and an account's Gold mark is the same Gold
#    the live feed, the rank plates and the checkout climb line draw. Unranked is
#    the only value this page owns, because it is not a rung of any ladder.
#
#  · **Both steps ship visible in the HTML, and step 2 is priced on the
#    reference shard.** The gate is a JS enhancement: with no JS the page is a
#    complete, priced, buyable EUW shop and a crawler reads all eleven listings.
#    `initAccounts()` hides step 2 until a server is chosen and re-prices every
#    card in place from the client mirror — the same derivation the server used.
#    `[data-ac-nojs]` is the "prices shown on Europe West" line JS removes.
#
#  · **The carousel translates a flex track by whole pages.** Cards are sized off
#    `--ac-per`, which CSS owns per breakpoint and JS reads back, so the page
#    count follows the layout instead of a second constant. ⚠ The handoff's own
#    defect here: verify a page change by asserting WHICH CARDS ARE ON SCREEN,
#    never by reading the label — a label that changes over a track that did not
#    move is how seven of eleven tiers were unreachable through two reviews.
#
#  · **The feature list mixes registers on purpose** — four spec rows, two green
#    ticks and ONE amber caution (`note`). Six identical green checkmarks read as
#    marketing; the amber line is what makes the rest credible. Every listing
#    carries one, asserted in data.py.
#
#  · **No struck price without a real one behind it.** `was` is a figure the
#    listing was actually sold at, carried through `quote()`'s subtotal/discount
#    so the card, the checkout receipt and the mail state one reduction.
#
#  Prices are server-rendered through money_parts()/money(), so the board follows
#  the currency switcher; the client re-splits through `esbMoneyParts()` when the
#  shard or the currency moves.
# ══════════════════════════════════════════════════════════════════════════


# A shard under this many units carries the amber "Low stock" badge on its
# server card. Business figures, not measurements: the badge is a nudge toward
# the shards that can actually be filled, and AC_SCARCE is the point where a
# handover stops being immediate and becomes a reservation.
AC_LOW_SHARD = 40
AC_SCARCE = 3


def ac_price_note():
    """"from $12.99" — the cheapest account anyone can actually buy, on any
    shard. Quoted off the catalogue (`D.account_floor()` reads stock), never
    typed, so a sold-out cheap listing can't leave the hero advertising a price
    nobody can pay."""
    return money_multi({c: D.account_floor(c) for c in D.ACCOUNT_CURRENCIES})


# ── The rank marks ────────────────────────────────────────────────────────
# Our own geometry, per the handoff and the same trademark rule everything else
# on this site follows: Riot's rank emblems are their artwork and using them
# needs licensing. If licensed files ever arrive they drop into the same tile
# and this table goes.
#
# Each entry is a list of (path, fill-level, stroke-level, stroke-width), where a
# level is a percentage of the tier colour mixed toward the card ground. The
# three unranked variants share a tier colour and MUST NOT share a mark, which is
# what the ring + 1/2/3 dots are for.
_AC_RING = "M16 3.6 A12.4 12.4 0 1 1 15.98 3.6 Z"
_AC_SHAPES = {
    "ring1": [(_AC_RING, None, 82, 2.6),
              ("M16 12.4 A3.6 3.6 0 1 1 15.99 12.4 Z", 96, None, 0)],
    "ring2": [(_AC_RING, None, 82, 2.6),
              ("M11 12.4 A3.4 3.4 0 1 1 10.99 12.4 Z", 96, None, 0),
              ("M21 12.4 A3.4 3.4 0 1 1 20.99 12.4 Z", 96, None, 0)],
    "ring3": [(_AC_RING, None, 82, 2.6),
              ("M16 8.4 A3.2 3.2 0 1 1 15.99 8.4 Z", 96, None, 0),
              ("M10.6 15.6 A3.2 3.2 0 1 1 10.59 15.6 Z", 96, None, 0),
              ("M21.4 15.6 A3.2 3.2 0 1 1 21.39 15.6 Z", 96, None, 0)],
    "diamond": [("M16 3.4 L28.6 16 L16 28.6 L3.4 16 Z", 58, 82, 1.4),
                ("M16 10 L22 16 L16 22 L10 16 Z", 96, None, 0)],
    "triangle": [("M16 2.8 L29 26.6 H3 Z", 58, 82, 1.4),
                 ("M16 11 L22.4 22.6 H9.6 Z", 96, None, 0)],
    "pentagon": [("M16 2.6 L29 12.2 L24 28 H8 L3 12.2 Z", 58, 82, 1.4),
                 ("M16 10.4 L22 14.8 L19.7 22.2 H12.3 L10 14.8 Z", 96, None, 0)],
    "hexagon": [("M16 2.4 L28.4 9.6 V22.4 L16 29.6 L3.6 22.4 V9.6 Z", 58, 82, 1.4),
                ("M16 10 L22 13.5 V20.5 L16 24 L10 20.5 V13.5 Z", 96, None, 0)],
    "octagon": [("M11.2 3 H20.8 L29 11.2 V20.8 L20.8 29 H11.2 L3 20.8 V11.2 Z", 58, 82, 1.4),
                ("M13.4 10.6 H18.6 L21.4 13.4 V18.6 L18.6 21.4 H13.4 L10.6 18.6 V13.4 Z",
                 96, None, 0)],
    "kite": [("M16 2.2 L27.4 16 L16 29.8 L4.6 16 Z", 58, 82, 1.4),
             ("M16 10 L21.2 16 L16 22 L10.8 16 Z", 96, None, 0)],
    "facet": [("M16 2.2 L27.4 16 L16 29.8 L4.6 16 Z", 58, 82, 1.4),
              ("M16 2.2 L27.4 16 H4.6 Z", 96, None, 0),
              ("M9.6 16 H22.4 L16 24.4 Z", 60, None, 0)],
    "star": [("M16 2 L19.9 11.6 L30 12.4 L22.3 19 L24.7 29 L16 23.7 L7.3 29 "
              "L9.7 19 L2 12.4 L12.1 11.6 Z", 58, 82, 1.4),
             ("M16 9.4 L18 14.4 L23.2 14.8 L19.2 18.2 L20.5 23.4 L16 20.6 "
              "L11.5 23.4 L12.8 18.2 L8.8 14.8 L14 14.4 Z", 96, None, 0)],
}

# The ground the marks are mixed toward — the card's own top stop, so a mark
# never sits on a tone it was not mixed against.
_AC_GROUND = (0x22, 0x1d, 0x19)


def _ac_mix(hexc, pct):
    """The tier colour at `pct`% over the card ground, resolved here rather than
    in `color-mix()`. These marks are static per listing, so computing the four
    stops at build time costs nothing and removes the fallback-`fill` dance the
    rank plate's emblem needs."""
    h = hexc.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = pct / 100.0
    return "#%02x%02x%02x" % tuple(
        round(c * f + g * (1 - f)) for c, g in zip(rgb, _AC_GROUND))


def ac_mark(a, size=26):
    """One listing's rank mark. Two or more flat shapes, no gradient, no
    photograph — all depth on this page is CSS."""
    colour = D.account_tier_color(a)
    paths = ""
    for d, fill, stroke, w in _AC_SHAPES.get(a["shape"], _AC_SHAPES["diamond"]):
        paths += '<path d="%s" fill="%s"%s stroke-linejoin="round"/>' % (
            d,
            _ac_mix(colour, fill) if fill else "none",
            (' stroke="%s" stroke-width="%s"' % (_ac_mix(colour, stroke), w))
            if stroke else "")
    return ('<span class="ac-emblem" style="--tier:%s">'
            '<svg viewBox="0 0 32 32" width="%d" height="%d" aria-hidden="true" '
            'focusable="false">%s</svg></span>' % (colour, size, size, paths))


def _ac_be(n):
    """"8k" / "124k" — blue essence as an account listing writes it. Unused
    while every listing is random (see the ⚠ in data.py), and kept because it is
    the one place the figure becomes a word if one ever comes back."""
    return "%dk" % round(n / 1000.0) if n >= 1000 else str(n)


# ── Step 1 — the server ───────────────────────────────────────────────────
def ac_server_card(sv):
    """One shard. The accent edge and "Most stock" go to the shard with the most
    units and the amber "Low stock" to any under AC_LOW_SHARD — both COMPUTED,
    so a shard that overtakes another cannot leave the badge on the wrong card.
    """
    region = sv["region"]
    code = D.account_code(region)
    units = D.account_units_on(region)
    top = max(D.account_units_on(s["region"]) for s in D.ACCOUNT_SERVERS)
    lead = units == top
    low = units < AC_LOW_SHARD
    badge = ""
    if lead:
        badge = '<span class="ac-sv-badge">Most stock</span>'
    elif low:
        badge = '<span class="ac-sv-badge is-low">Low stock</span>'
    return f"""<button type="button" class="ac-sv{' is-lead' if lead else ''}"
        data-ac-server="{esc(region)}">
      <span class="ac-sv-edge" aria-hidden="true"></span>
      <span class="ac-sv-top">
        <span class="ac-sv-code">{esc(code)}</span>
        {badge}
      </span>
      <span class="ac-sv-name">{esc(region)}</span>
      <span class="ac-sv-stock">{_ico("package", 13, "ico", stroke=True)}<b data-ac-sv-units>{units}</b>
        <span>in stock</span></span>
      <span class="ac-sv-foot">
        <span class="ac-sv-from"><span class="ac-sv-froml">From</span>
          {money_multi({c: D.account_shard_floor(region, c) for c in D.ACCOUNT_CURRENCIES})}</span>
        <span class="ac-sv-go" aria-hidden="true">{_ico("arrow", 13, "ico", stroke=True)}</span>
      </span>
    </button>"""


def ac_step_server():
    """Step 1. The region-lock warning is the reason this screen exists, so it
    sits above the cards rather than under them."""
    cards = "".join(ac_server_card(s) for s in D.ACCOUNT_SERVERS)
    return f"""<div class="ac-step ac-step-1" data-ac-step="server">
      <div class="ac-step-head">
        <span class="ac-step-k"><i class="ac-dash" aria-hidden="true"></i>
          <span>Step 1 of 2</span></span>
        <h2 class="ac-step-h">Which server do you play on?</h2>
        <p class="ac-step-p">Accounts are region-locked, so this is the one choice you
        cannot change after purchase. Pick the server you actually queue on.</p>
      </div>
      <div class="ac-sv-grid">{cards}</div>
    </div>"""


# ── Step 2 — the tiers ────────────────────────────────────────────────────
def ac_tier_card(a, region):
    """One listing, priced on one shard.

    Every shard-dependent node carries a `data-ac-*` hook: the price, the struck
    price, the shard name and code, the unit counts and the CTA's href all move
    when the server changes, and `initAccounts()` rewrites exactly these.
    Everything else is a fact about the listing and never moves.

    ⚠ ALL THREE STOCK STATES AND ALL THREE CTA LABELS SHIP IN THE DOM, with two
    of each hidden. That is the whole-text-node rule i18n.js imposes everywhere
    on this site: a label written in by JS arrives untranslated, and "Reserve"
    is exactly the kind of word a French reader would then meet in English. CSS
    picks the stock variant off the state class; JS toggles the CTAs.

    The CTA is a REAL link into checkout, so the card can be middle-clicked and
    crawled; the query is untrusted and the server re-resolves both the listing
    and the shard before it charges anything (`pricing.account_pick`)."""
    units = D.account_stock(a, region)
    price = D.account_price(a)
    was = D.account_was(a)
    # `account_badge()` is the one reader — "Cheapest" is computed there, so a
    # re-price can never leave the claim on a card that is not.
    label = D.account_badge(a)
    feat = label == "Best seller"
    low_badge = label == "Low stock"
    scarce = 0 < units <= AC_SCARCE
    state = "out" if not units else ("low" if scarce else "ok")
    href = "/checkout.html?account=%s&region=%s" % (
        esc(_urlq(a["id"])), esc(_urlq(region)))

    badge = (f'<span class="ac-badge{" is-low" if low_badge else ""}">{esc(label)}</span>'
             if label else "")
    struck = (f'<span class="ac-was" data-ac-was{"" if was > price else " hidden"}>'
              f'{money_multi(a["was"] if a.get("was") else a["price"])}</span>')

    # Four spec rows, two green ticks and one amber caution — the mix is the
    # point. See the ⚠ in the section header.
    # ⚠ A random listing gets ONE whole text node, not a `<b>` with the word
    # "Random" in it: French wants "BE/skins aléatoires" and German "Zufällige
    # BE/Skins", and a figure-carrier split would impose English word order on
    # both. A listing WITH an essence figure keeps the split, because there the
    # number is the thing that moves.
    be_row = ("<span>Random BE/Skins</span>" if D.account_be_random(a)
              else f'<b>{esc(_ac_be(a["be"]))}</b> <span>blue essence</span>')
    # The third row is the MMR band on a ranked listing and the level plus the
    # champion pool on an unranked one — an account with unplayed placements has
    # no rank MMR to state, and the pool is what a smurf is bought on.
    # `account_spec()` hands back a template so this is ONE text node with `{}`
    # placeholders: both translations move the figures, and a `<b>`-per-number
    # split would impose English word order on the row.
    spec = D.account_spec(a)
    spec_row = "<span>%s</span>" % esc(spec[0].format(*spec[1:]))
    feats = [
        ("globe", "spec", '<span data-ac-shard-name>%s</span>' % esc(region)),
        ("package", "spec", be_row),
        # ⚠ Two shapes, two marks: `account_spec()` states a CHAMPION POOL on an
        # unranked listing and an MMR BAND on a ranked one, and one glyph could
        # only ever be right for one of them — `users` is a cast of characters,
        # which says nothing about a rating. Derived from the tier through
        # `account_kind()`, so nothing is authored twice.
        ("users" if D.account_kind(a) == "unranked" else "shield-check",
         "spec", spec_row),
        ("check", "ok", "<span>%s</span>" % esc("Full email access")),
        ("check", "ok", "<span>%s</span>" % esc("Hand-levelled, never botted")),
        ("warn", "caution", "<span>%s</span>" % esc(a["note"])),
    ]
    rows = "".join(
        f'<li class="ac-ft is-{kind}">{_ico(ico, 16, "ico", stroke=True)}'
        f'<span class="ac-ft-t">{body}</span></li>'
        for ico, kind, body in feats)

    # Under AC_SCARCE the handover stops being immediate — the unit is reserved
    # and verified before it is handed over — so the card says so rather than
    # repeating the delivery figure the rest of the page quotes.
    stock = f"""<span class="ac-stock is-{state}" data-ac-stock>
        <span class="ac-sv-one" data-ac-sv="ok">{_ico("bolt", 11, "ico")}
          <b data-ac-units>{units}</b><span>in stock · {esc(pricing.ACCOUNT_ETA.lower())}</span></span>
        <span class="ac-sv-one" data-ac-sv="low">{_ico("hourglass", 11, "ico", stroke=True)}
          <b data-ac-units>{units}</b><span>left · verified in 12 h</span></span>
        <span class="ac-sv-one" data-ac-sv="out">{_ico("dot", 11, "ico")}
          <span>Sold out on this server</span></span>
      </span>"""

    # A sold-out listing keeps its card: the price and the spec are still the
    # honest answer to "what does a Diamond cost here", and the one real action
    # left is asking when it is back. Not a disabled button — there is nothing
    # to enable.
    # ⚠ The CTA keys ARE the stock states — `ok` / `low` / `out`, the same three
    # `[data-ac-stock]` carries. They were `buy` / `reserve` / `out` for one
    # revision and paint()'s `kind !== state` then hid all three, leaving every
    # card without a CTA at all. One vocabulary, or the two drift silently.
    ctas = f"""<a class="btn btn-primary ac-cta" data-ac-cta="ok" href="{href}"
          {"" if state == "ok" else "hidden"}><span>Buy now</span></a>
        <a class="btn ac-cta ac-cta-reserve" data-ac-cta="low" href="{href}"
          {"" if state == "low" else "hidden"}><span>Reserve</span></a>
        <a class="btn btn-outline ac-cta ac-cta-out" data-ac-cta="out" href="/support.html"
          {"" if state == "out" else "hidden"}><span>Ask when it is back</span></a>"""

    return f"""<article class="ac-card{' is-feat' if feat else ''}{' is-out' if not units else ''}"
        data-ac-card data-ac-id="{esc(a['id'])}" data-ac-kind="{esc(D.account_kind(a))}">
      <span class="ac-card-edge" aria-hidden="true"></span>
      <div class="ac-card-top">
        {ac_mark(a)}
        {badge}
      </div>
      <div class="ac-card-name">
        <h3 class="ac-name">{esc(a['name'])}</h3>
        <span class="ac-card-code" data-ac-code>{esc(D.account_code(region))}</span>
      </div>
      <ul class="ac-fts">{rows}</ul>
      <div class="ac-card-foot">
        {struck}
        <span class="ac-price" data-ac-price>{money_parts_multi(a["price"])}</span>
        {stock}
        <div class="ac-card-cta">{ctas}</div>
      </div>
    </article>"""


def ac_filter_bar():
    """Three buttons on a hairline, with the active filter's description and the
    page label at the right end.

    ⚠ This band was iterated four times in the handoff — chips, a segmented
    control, large underlined tabs, then this. The lesson that stuck was that
    step 2 had four stacked control rows and the fix was consolidating to two,
    not restyling the filters harder. Do not add a third row here."""
    icons = {"all": "list", "unranked": "bolt", "ranked": "trophy"}
    btns = ""
    for i, (key, label, _meta) in enumerate(D.ACCOUNT_KINDS):
        on = i == 0
        btns += (
            f'<button type="button" class="ac-fil{" is-on" if on else ""}" '
            f'data-ac-kind="{esc(key)}" aria-pressed="{"true" if on else "false"}">'
            f'{_ico(icons.get(key, "grid"), 20, "ico ac-fil-i", stroke=True)}'
            f'<span class="ac-fil-l">{esc(label)}</span>'
            f'<span class="ac-fil-n">{len(D.accounts_of_kind(key))}</span></button>')
    n = len(D.ACCOUNTS)
    return f"""<div class="ac-filbar" data-ac-filbar>
      <div class="ac-fils" role="group" aria-label="Tier">{btns}</div>
      <span class="ac-filmeta">
        <span data-ac-kindmeta>{esc(D.ACCOUNT_KINDS[0][2])}</span>
        <i class="ac-filsep" aria-hidden="true"></i>
        <span data-ac-pagelabel><span>Showing</span> <b>1</b><span>–</span><b>{n}</b>
          <span>of</span> <b>{n}</b> <span>tiers</span></span>
      </span>
    </div>"""


def ac_step_tiers(region):
    """Step 2: the server bar, the head row with the arrows, the filter bar and
    the carousel. Server-rendered on the reference shard — see the section
    header for why both steps ship visible."""
    cards = "".join(ac_tier_card(a, region) for a in D.ACCOUNTS)
    code = D.account_code(region)
    return f"""<div class="ac-step ac-step-2" data-ac-step="tiers" id="tiers">
      <div class="ac-bar">
        <span class="ac-bar-l">
          <span class="ac-bar-tick">{_ico("check", 14, "ico", stroke=True)}</span>
          <span class="ac-bar-txt">
            <span class="ac-bar-k">Step 1 · server</span>
            <span class="ac-bar-n"><span data-ac-server-name>{esc(region)}</span>
              <i aria-hidden="true">·</i>
              <span data-ac-server-code>{esc(code)}</span></span>
          </span>
        </span>
        <span class="ac-bar-r">
          <span class="ac-bar-stock"><b data-ac-server-stock>{D.account_units_on(region)}</b>
            <span>in stock on this server</span></span>
          <button type="button" class="ac-change" data-ac-change>
            {_ico("arrow-left", 13, "ico", stroke=True)}<span>Change server</span>
          </button>
        </span>
      </div>

      <div class="ac-step-row">
        <div class="ac-step-head is-left">
          <span class="ac-step-k"><i class="ac-dash" aria-hidden="true"></i>
            <span>Step 2 of 2</span></span>
          <h2 class="ac-step-h"><span>Pick your account on</span>
            <span data-ac-server-code>{esc(code)}</span></h2>
        </div>
        <div class="ac-arrows">
          <button type="button" class="ac-arrow" data-ac-prev aria-label="Previous tiers"
                  disabled>{_ico("arrow-left", 15, "ico", stroke=True)}</button>
          <button type="button" class="ac-arrow" data-ac-next aria-label="More tiers"
                  >{_ico("arrow", 15, "ico", stroke=True)}</button>
        </div>
      </div>

      {ac_filter_bar()}

      <!-- ⚠ The track moves by whole pages. Verify a page change by asserting
           which cards are on screen, never by reading the label. -->
      <div class="ac-rail">
        <div class="ac-track" data-ac-track>{cards}</div>
      </div>
      <div class="ac-dots" data-ac-dots role="tablist" aria-label="Pages"></div>
      <p class="ac-nojs" data-ac-nojs>Prices and stock shown on
        <b>{esc(region)}</b>. Pick a server above to see yours.</p>
    </div>"""


# ── Band 01 — the handover ────────────────────────────────────────────────
def ac_handover():
    steps = "".join(f"""<div class="ac-step-row-i">
        <span class="ac-hs-n">{esc(num)}</span>
        <span class="ac-hs-t">
          <span class="ac-hs-h">{esc(title)}</span>
          <span class="ac-hs-b">{esc(body)}</span>
        </span>
        <span class="ac-hs-time">{esc(when)}</span>
      </div>""" for num, when, title, body in D.ACCOUNT_STEPS)

    included = "".join(f"""<li class="ac-inc">
        <span class="ac-inc-i">{_ico(icon, 17, "ico", stroke=True)}</span>
        <span class="ac-inc-t"><b>{esc(name)}</b><span>{esc(note)}</span></span>
      </li>""" for icon, name, note in D.ACCOUNT_INCLUDED)

    return f"""<section class="ac-band ac-lift">
  <div class="ac-glow" aria-hidden="true"></div>
  <div class="wrap ac-inner ac-hand">
    <div class="ac-hand-l">
      {sec_kicker("01", "Handover")}
      <h2 class="ac-h2">{esc(pricing.ACCOUNT_ETA)}, from paying to playing.</h2>
      <p class="ac-band-p">Every account ships with the original email inbox, not just the
      game login — which is the only version of this that is actually yours. Change the
      email and the password on arrival and nobody, including us, can recover it
      afterwards.</p>
      <div class="ac-hsteps">{steps}</div>
    </div>
    <div class="ac-hand-r">
      <div class="ac-panel">
        <div class="ac-panel-head">
          <span class="ac-panel-t">What lands in your inbox</span>
          <span class="ac-panel-k">{esc(D.ACCOUNT_GAME)}</span>
        </div>
        <ul class="ac-incs">{included}</ul>
      </div>
      <!-- ⚠ VERBATIM AND NOT TO BE SOFTENED, and not to be moved into the FAQ.
           This page sells a product whose failure mode is losing the thing you
           bought; an accordion tells the buyer after the decision. -->
      <div class="ac-plate">
        <span class="ac-plate-ico">{_ico("warn", 18, "ico", stroke=True)}</span>
        <p class="ac-plate-b">{esc(D.ACCOUNT_DISCLAIMER)}</p>
      </div>
    </div>
  </div>
</section>"""


# ── Band 02 — why ours ────────────────────────────────────────────────────
def ac_why():
    cards = "".join(f"""<article class="ac-trust">
        <div class="ac-trust-head">
          <span class="ac-tile">{_ico(icon, 18, "ico", stroke=True)}</span>
          <span class="ac-trust-k">{esc(kicker)}</span>
        </div>
        <h3 class="ac-trust-t">{esc(title)}</h3>
        <p class="ac-trust-b">{esc(body)}</p>
        <span class="ac-proof">{_ico("check", 12, "ico", stroke=True)}<span>{esc(proof)}</span></span>
      </article>""" for icon, kicker, title, body, proof in D.ACCOUNT_TRUST)
    return f"""<section class="ac-band ac-lift">
  <div class="wrap ac-inner">
    <div class="ac-head">
      <div class="ac-head-l">
        {sec_kicker("02", "Why ours")}
        <h2 class="ac-h2">Hand-levelled, never botted.</h2>
      </div>
      <p class="ac-head-p">Three things decide whether a bought account is worth having: who
      played it, whether you can lock it to yourself, and what happens if it goes wrong.</p>
    </div>
    <div class="ac-trusts">{cards}</div>
  </div>
</section>"""


# ── Band 03 — buyers ──────────────────────────────────────────────────────
def ac_review_card(name, when, bought, stars, body):
    """The reviews page's card shell, with the climb row replaced by what was
    bought — an account order has no climb to draw, and the purchase tag IS the
    argument of this band. Same `.rv-*` atoms as `review_card()` (the stars, the
    quote, the verified seal), so a review reads the same here as on the page
    the rating links to.

    ⚠ The three reviews are invented, exactly like D.REVIEWS."""
    return f"""<figure class="rv-card ac-rv">
      <div class="rv-card-top">
        {rating_stars(stars)}
        <span class="rv-date">{esc(when)}</span>
      </div>
      <div class="ac-rv-tag">{esc(bought)}</div>
      <blockquote class="rv-quote">{esc(body)}</blockquote>
      <figcaption class="rv-foot">
        <span class="rv-verified">{_ico("seal", 11, "rv-seal", evenodd=True)}<span>Verified order</span></span>
        <span class="rv-sep" aria-hidden="true">·</span>
        <span class="rv-game">{esc(name)}</span>
      </figcaption>
    </figure>"""


def ac_buyers():
    """The rating is the SITE's one rating (`STATS["trustpilot"]`), not a second
    one computed for this page: the whole reason the reviews page publishes its
    distribution is that this site quotes one score everywhere."""
    cards = "".join(ac_review_card(n, w, b, s, t) for n, w, b, s, t in D.ACCOUNT_REVIEWS)
    return f"""<section class="ac-band">
  <div class="wrap ac-inner">
    <div class="ac-head">
      <div class="ac-head-l">
        {sec_kicker("03", "Buyers")}
        <h2 class="ac-h2">From accounts sold this month.</h2>
      </div>
      <div class="ac-rate">
        <span class="ac-rate-n">{esc(D.STATS['trustpilot'])}</span>
        <span class="ac-rate-t">{rating_stars(5)}
          <span class="ac-rate-l"><b>{esc(pricing.ACCOUNT_ETA)}</b><span>,
            every time</span></span>
        </span>
      </div>
    </div>
    <div class="ac-rvs">{cards}</div>
    <p class="ac-rv-note">{_ico("seal", 12, "ico", evenodd=True)}<span>Every review here is
    tied to a paid order id. We do not solicit them and we do not filter by score —</span>
    <a href="/reviews.html">read every review</a><span>.</span></p>
  </div>
</section>"""


# ── Band 04 — the FAQ ─────────────────────────────────────────────────────
def ac_faq_items():
    """Every figure substituted rather than typed — the warranty window is
    `D.ACCOUNT_WARRANTY_MONTHS`, so re-tuning it cannot leave a stale number in
    an answer. ⚠ The ids are a public contract: support links people at
    `/accounts.html#faq-<id>` and checkout deep-links `#faq-warranty`."""
    fills = {"months": D.ACCOUNT_WARRANTY_MONTHS}
    return [(fid, q, a.format(**fills)) for fid, q, a in D.ACCOUNT_FAQ]


def ac_faq(items):
    return f"""<section class="ac-band ac-faq-band">
  <div class="wrap ac-inner ac-faq-inner">
    <div class="ac-faq-l">
      {sec_kicker("04", "FAQ")}
      <h2 class="ac-h2">Before you buy an account.</h2>
      <p class="ac-faq-p">Three of these argue against the sale. They are the reason the
      other five are worth reading.</p>
      <a class="ac-link" href="/support.html"><span>Ask us anything else</span>
        {_ico("arrow", 13, "ico", stroke=True)}</a>
    </div>
    <div class="ac-faq-r">{sg_faq(items)}</div>
  </div>
</section>"""


def ac_close():
    """The handoff's close, not the shared `cta_band()`: the headline is the
    page's central claim said one last time, and there is nothing to read back —
    an account order has no climb, so `cta_band(live=True)` has nothing to
    close on."""
    return f"""<section class="hero-a hero-a-lit ac-close">
  <div class="fx hero-a-glow" aria-hidden="true"></div>
  <div class="wrap ac-close-in">
    <h2 class="ac-close-h">Full email access, or it's not an account.</h2>
    <p class="ac-close-p"><span>{esc(spell(len(D.ACCOUNTS)).capitalize())} tiers on
      {esc(spell(len(D.ACCOUNT_SERVERS)))} servers, from</span> {ac_price_note()}<span>,
      replaced for {D.ACCOUNT_WARRANTY_MONTHS} months if it ever breaks.</span></p>
    <div class="ac-close-a">
      <a class="btn btn-primary ac-close-cta" href="#top"><span>Pick your server</span></a>
      <a class="ac-link" href="/games/{esc(BY_NAME[D.ACCOUNT_GAME]['slug'])}.html">
        <span>Or boost the account you already play</span>
        {_ico("arrow", 13, "ico", stroke=True)}</a>
    </div>
  </div>
</section>"""


def page_accounts():
    faq = ac_faq_items()
    lol = BY_NAME[D.ACCOUNT_GAME]
    ref = D.ACCOUNT_REGIONS[0]              # the reference shard, EUW
    live = [a for a in D.ACCOUNTS
            if any(D.account_stock(a, s["region"]) for s in D.ACCOUNT_SERVERS)]

    # One Product with an AggregateOffer over what can actually be bought.
    # Deliberately no aggregateRating — the ratings on this site are placeholder
    # and `rating_ld()` is gated on TRUSTPILOT_URL for exactly that reason; a
    # page selling accounts must not be the one that leaks invented review stars
    # into a SERP.
    product = {
        "@context": "https://schema.org", "@type": "Product",
        "name": "%s accounts" % D.ACCOUNT_GAME,
        "description": "Ready-made %s accounts with full email access, delivered on the "
                       "server you pick." % D.ACCOUNT_GAME,
        "brand": {"@type": "Brand", "name": D.BRAND},
        "offers": {"@type": "AggregateOffer", "priceCurrency": "USD",
                   # The dollar row. Schema.org needs one currency and this is
                   # the base; the other markets are their own rows, not a
                   # conversion of this one, so there is no rate to express.
                   "lowPrice": "%.2f" % min((D.account_price(a) for a in live), default=0),
                   "highPrice": "%.2f" % max((D.account_price(a) for a in live), default=0),
                   "offerCount": len(live),
                   "availability": "https://schema.org/InStock"},
    }
    ld = [
        product,
        faq_ld([(q, a) for _fid, q, a in faq]),
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Accounts",
             "item": D.SITE + "/accounts"},
        ]},
    ]

    # ⚠ The hero is the ONE centred band on this page; everything below it is
    # flush left, matching the rest of the site.
    body = f"""<div class="ac" data-ac-shop>
  <section class="hero-a hero-a-lit ac-hero" id="top" style="--game-hue:{lol['hue']}">
    <div class="fx hero-a-glow" aria-hidden="true"></div>
    <div class="fx hero-a-hatch" aria-hidden="true"></div>
    <div class="fx fx-grain" aria-hidden="true"></div>
    <div class="wrap ac-hero-inner">
      <div class="ac-hero-copy">
        <span class="ac-hero-k">{esc(lol['name'])} accounts</span>
        <h1 class="ac-h1">Buy {esc(lol['name'])} accounts</h1>
        <p class="ac-hero-p">Ranked ready, full email access, no grind</p>
        <div class="ac-assure">
          <span class="ac-as">{_ico("bolt", 15, "ico")}
            <span>{esc(pricing.ACCOUNT_ETA)}</span></span>
          <span class="ac-as">{_ico("envelope", 15, "ico", stroke=True)}
            <span>Original inbox included</span></span>
          <span class="ac-as">{_ico("shield-check", 15, "ico", stroke=True)}
            <span>{D.ACCOUNT_WARRANTY_MONTHS}-month replacement warranty</span></span>
        </div>
      </div>

      {ac_step_server()}
      {ac_step_tiers(ref)}
    </div>
  </section>

  {ac_handover()}
  {ac_why()}
  {ac_buyers()}
  {ac_faq(faq)}
  {ac_close()}
</div>"""

    return layout(ACCOUNTS_HREF, "Buy %s Accounts - %s" % (D.ACCOUNT_GAME, D.BRAND),
                  "Ready-made League of Legends accounts from %s: unranked smurfs to "
                  "Master, full email access on every one, %s on EUW, NA, EUNE or OCE."
                  % (usd(D.account_floor("usd"), cents=True),
                     pricing.ACCOUNT_ETA.lower()),
                  body, current=ACCOUNTS_HREF, jsonld=ld,
                  extra_js=faq_accordion_js(), nav_outline=True)

def page_how():
    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">How it works</span>
      <h1 class="h-md">No account.<br>No surprises.<br>No ticket queue.</h1>
      <p class="lede">You can see the whole price before you tell us anything about yourself. That
      is the entire point of the way this is built: the calculator is the first thing on every page,
      the number it shows is the number you pay, and the only thing checkout asks for is an email to
      send the order link to.</p>
      <div class="btn-row"><a class="btn btn-primary" href="/games">Start an order</a></div>
    </div>
    <div class="stack" style="gap:26px">{steps_block()}</div>
  </div>
</section>

{rule()}

{dashboard_section()}

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
      month{reply_month}.</p>
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
    """The roster page — design_handoff_boosters_roster, screen 1.

    Two jobs that pull in different directions: prove the board is real (the
    hero) and let someone find and hire a booster (the table). They stay in
    separate bands so the proof never gets in the way of the search.
    """
    n, free = D.STATS.get("online") or len(D.BOOSTERS), D.STATS.get("free_now")
    live = f"""<div class="rst-live">
      <span class="rst-live-t"><span class="dot-live dot-ok" aria-hidden="true"></span>Updated live</span>
      <span class="rst-live-n">
        <span class="rst-live-stat"><b>{esc(str(n))}</b> <span>on the board</span></span>
        <i class="rst-live-sep" aria-hidden="true"></i>
        <span class="rst-live-stat is-free"><b>{esc(str(free))}</b> <span>free right now</span></span>
      </span>
    </div>""" if n else ""

    body = f"""{roster_hero()}

<section class="rst rst-board">
  <div class="wrap">
    <div class="rst-board-head">
      <div class="sec-head-copy">
        {sec_kicker("01", "Roster")}
        <h2 class="rst-h2">Everyone on shift</h2>
      </div>
      {live}
    </div>
    {roster_filters()}
    {roster_board()}
  </div>
</section>

{cta_band()}"""
    return layout("/boosters", "Boosters on shift — %s" % D.BRAND,
                  "Who plays your order: verified ranks, live trials, monthly review, one free swap "
                  "per order.", body, current="/boosters", nav_outline=True)


def sg_stats():
    """The hero's three figures — the column that closed the ~350px void under
    the CTA. They *back* the policy rather than restate it, which is the whole
    reason the void could be filled honestly: the figures were already true.

    `{n}` in a label marks the one number inside the sentence. It rides in its
    own `<b>` so the words either side stay whole translatable text nodes."""
    rows = ""
    for fig, label, num in D.GUARANTEE["stats"]:
        if num and "{n}" in label:
            before, after = label.split("{n}", 1)
            text = ("<span>%s</span> <b>%s</b> <span>%s</span>"
                    % (esc(before.strip()), esc(num), esc(after.strip())))
        else:
            text = "<span>%s</span>" % esc(label)
        rows += ('<div class="sg-stat"><span class="sg-stat-f">%s</span>'
                 '<span class="sg-stat-l">%s</span></div>' % (esc(fig), text))
    return '<div class="sg-stats">%s</div>' % rows


def sg_cases():
    """The three refund cases, in the order an order moves through them. The
    first takes the accent border and the shadow: it is where most refunds
    land, and the three read as a timeline rather than three equal boxes."""
    out = ""
    for i, (icon, stroke, stage, title, body) in enumerate(D.GUARANTEE["cases"]):
        lead = " is-lead" if i == 0 else ""
        out += f"""<article class="sg-case{lead}">
        <div class="sg-case-head">
          <span class="sg-tile">{_ico(icon, 17, "ico", stroke=stroke)}</span>
          <span class="sg-stage">{esc(stage)}</span>
        </div>
        <h2 class="sg-case-t">{esc(title)}</h2>
        <p class="sg-case-b">{esc(body)}</p>
      </article>"""
    return '<div class="sg-cases">%s</div>' % out


def sg_measures():
    """"What that means per order" — the same argument as the prose beside it,
    in a second register: prose for readers, list for scanners. Every row is a
    label for a claim SAFETY["body"] already makes."""
    rows = "".join(f"""<li class="sg-measure">
        {_ico(icon, 19, "sg-measure-i", stroke=stroke)}
        <span class="sg-measure-t">
          <span class="sg-measure-n">{esc(name)}</span>
          <span class="sg-measure-note">{esc(note)}</span>
        </span>
      </li>""" for icon, stroke, name, note in D.SAFETY["measures"])
    return f"""<aside class="sg-card">
      <div class="sg-card-head">
        <h3 class="sg-card-t">What that means per order</h3>
        <span class="sg-pill">{_ico("seal", 11, "ico", evenodd=True)}Every order</span>
      </div>
      <ul class="sg-measures">{rows}</ul>
    </aside>"""


def promise_cards():
    """The three promises with their icon tile and proof line — the guarantee
    page's copy of D.GUARANTEES. The proof line is pinned with `margin-top:auto`
    so the three stay aligned across cards with unequal bodies."""
    cards = "".join(f"""<article class="sg-promise">
        <div class="sg-promise-head">
          <span class="sg-tile">{_ico(icon, 18, "ico", stroke=stroke)}</span>
          <span class="sg-promise-k">{esc(kicker)}</span>
        </div>
        <h3 class="sg-promise-t">{esc(title)}</h3>
        <p class="sg-promise-b">{esc(body)}</p>
        <span class="sg-proof">{esc(proof)}</span>
      </article>""" for icon, stroke, kicker, title, body, proof in D.GUARANTEES)
    return '<div class="sg-promises">%s</div>' % cards


def sg_faq(items):
    """The accordion. Single-open, item 1 expanded on load so the band never
    reads as an empty list.

    Every answer is rendered into the DOM and hidden with the `hidden`
    attribute rather than conditionally built: the FAQPage JSON-LD asserts they
    are on the page, so they have to actually be. Each item carries a stable id
    — support links people at specific answers, so the ids are a public
    contract, not an implementation detail."""
    out = ""
    for i, (fid, q, a) in enumerate(items):
        open_ = i == 0
        out += f"""<div class="sg-q{' is-open' if open_ else ''}" id="faq-{esc(fid)}" data-sg-item>
        <h3 class="sg-q-h">
          <button type="button" class="sg-q-btn" id="faq-{esc(fid)}-h"
                  aria-expanded="{'true' if open_ else 'false'}" aria-controls="faq-{esc(fid)}-p">
            <span class="sg-q-n">{i + 1:02d}</span>
            <span class="sg-q-t">{esc(q)}</span>
            {_ico("plus", 14, "sg-q-c sg-q-c-p", stroke=True)}{_ico("minus", 14, "sg-q-c sg-q-c-m", stroke=True)}
          </button>
        </h3>
        <div class="sg-a" id="faq-{esc(fid)}-p" role="region"
             aria-labelledby="faq-{esc(fid)}-h"{'' if open_ else ' hidden'}>
          <p class="sg-a-b">{esc(a)}</p>
        </div>
      </div>"""
    return '<div class="sg-faq" data-sg-faq>%s</div>' % out


# The single-open accordion behaviour, shared verbatim by the safety page and
# the support page — the handoff's "reconcile the FAQ accordion into one
# component" applied to the script too, not just the markup and CSS. It selects
# the `.sg-faq` / `[data-sg-item]` markup that sg_faq() emits, so any page that
# renders that markup gets the same behaviour with one function call.
def faq_accordion_js():
    return """<script>
(function () {
  var root = document.querySelector('[data-sg-faq]');
  if (!root) return;
  var items = [].slice.call(root.querySelectorAll('[data-sg-item]'));

  function set(item, open) {
    item.classList.toggle('is-open', open);
    item.querySelector('.sg-q-btn').setAttribute('aria-expanded', open ? 'true' : 'false');
    var panel = item.querySelector('.sg-a');
    if (open) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
  }

  // Single-open: opening one closes the rest, and clicking the open item
  // collapses it, leaving all six closed.
  items.forEach(function (item) {
    item.querySelector('.sg-q-btn').addEventListener('click', function () {
      var open = !item.classList.contains('is-open');
      items.forEach(function (o) { set(o, false); });
      set(item, open);
      if (open && window.esbTrack) window.esbTrack('faq_open', { item_id: item.id });
    });
  });

  // Deep links: support sends people at a specific answer.
  function target() {
    var id = location.hash.slice(1);
    var item = id && document.getElementById(id);
    return (item && items.indexOf(item) >= 0) ? item : null;
  }
  function open(item) { items.forEach(function (o) { set(o, o === item); }); }

  // Offset for the sticky header, and land instantly: ashfall.css sets
  // `scroll-behavior: smooth` globally, which is the one thing the handoff
  // rules out here — a page whose subject is trust should not animate, and a
  // smooth landing on a sticky-heading layout drifts the question under the
  // header. It has to be 'instant', not 'auto' — 'auto' means "use the CSS
  // value", which is exactly the smooth we are overriding.
  //
  // The offset is the sheet's own `scroll-padding-top`, so the header and this
  // stay in step from one place.
  function reveal(item) {
    var pad = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 96;
    var top = item.getBoundingClientRect().top + window.pageYOffset - pad;
    window.scrollTo({ top: top, behavior: 'instant' });
  }

  // Open immediately so the answer is never expanded in front of the reader,
  // but scroll after load: the browser does its own fragment scroll and the
  // webfont swap reflows under us, and either one strands an earlier one.
  //
  // Scroll restoration has to be turned off for this load, or a reload of a
  // deep link puts the reader back where they were rather than on the answer
  // the link names — it runs after `load` and wins. Only when there is a
  // target: everywhere else the browser's own restore is the right behaviour.
  var first = target();
  if (first) {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    open(first);
    if (document.readyState === 'complete') reveal(first);
    else window.addEventListener('load', function () { reveal(first); });
  }
  window.addEventListener('hashchange', function () {
    var item = target();
    if (item) { open(item); reveal(item); }
  });
})();
</script>
"""


def page_guarantee():
    # The handoff types "35%" here; this site's duo multiplier is 1.55, and the
    # label reads it off the constant for the same reason mode_seg() does — a
    # typed percentage in a policy answer drifts silently from what is charged.
    duo = round((pricing.DUO_MULT - 1) * 100)
    faq = [(fid, q, a.replace("{duo}", str(duo))) for fid, q, a in D.GUARANTEE["faq"]]
    safety_prose = "".join('<p class="sg-prose">%s</p>' % esc(p) for p in D.SAFETY["body"])

    body = f"""<section class="sg">
  <div class="sg-hatch" aria-hidden="true"></div>

  <div class="sg-band sg-band-1">
    <div class="sg-glow" aria-hidden="true"></div>
    <div class="wrap sg-grid-1">
      <div class="sg-copy">
        <span class="sg-kicker">Safety &amp; guarantee</span>
        <h1 class="sg-h1">Written down, not "depends on the order".</h1>
        <p class="sg-lede">A refund policy that needs a support ticket to explain isn't a
        policy. Here is the whole thing, in the three cases that actually happen.</p>
        <a class="btn btn-primary sg-cta" href="/games">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
        {sg_stats()}
      </div>
      {sg_cases()}
    </div>
  </div>

  <div class="sg-band sg-band-2" id="safety">
    <div class="wrap sg-grid-2">
      <div class="sg-copy">
        {sec_kicker("02", "Safety")}
        <h2 class="sg-h2">{esc(D.SAFETY['title'])}</h2>
        {safety_prose}
        <div class="sg-disclaimer">
          {_ico("warn", 18, "sg-disclaimer-i", stroke=True)}
          <p>{esc(D.SAFETY['disclaimer'])}</p>
        </div>
      </div>
      {sg_measures()}
    </div>
  </div>

  <div class="sg-band sg-band-3">
    <div class="wrap">
      <div class="sg-head">
        <div class="sg-head-copy">
          {sec_kicker("03", "In short")}
          <h2 class="sg-h2 sg-h2-sm">Three promises, plainly</h2>
        </div>
        <a class="sg-terms" href="/legal/terms.html">Read the full terms{_ico("arrow-up-right", 13, "ico", stroke=True)}</a>
      </div>
      {promise_cards()}
    </div>
  </div>

  <div class="sg-band sg-band-last" id="faq">
    <div class="wrap sg-grid-4">
      <div class="sg-copy sg-faq-copy">
        {sec_kicker("04", "FAQ")}
        <h2 class="sg-h2 sg-h2-sm">The questions support gets most</h2>
        <p class="sg-faq-note">{esc(D.GUARANTEE['faq_note'])}</p>
        <a class="btn btn-outline btn-sm sg-ask" href="/support.html">{_ico("chat", 15, "ico")}Ask support</a>
      </div>
      {sg_faq(faq)}
    </div>
  </div>
</section>

{cta_band()}"""
    js = faq_accordion_js()
    return layout("/guarantee.html", "Refund and safety guarantee — %s" % D.BRAND,
                  "Full refund until a booster claims your order, pro-rated after that, automatic "
                  "refund if nobody claims it in 24 hours. The whole policy on one page.",
                  body, current="/guarantee.html",
                  jsonld=[faq_ld([(q, a) for _fid, q, a in faq])],
                  extra_js=js, nav_outline=True)


# ══════════════════════════════════════════════════════════════════════════
#  /support.html — design_handoff_support
# ══════════════════════════════════════════════════════════════════════════
# Most pages here exist to start an order; this one exists to END a worry, and
# the cheapest way to do that is often not to open a conversation at all. So the
# page descends by speed: the channel that answers in minutes (Discord), the one
# that answers in hours (email), then six answers that mean you never wrote in.
#
# Seventh scoped port after .hero-a / .co / .gg / .dsh / .rst / .tk — tokens on
# `.sp`, product radii per element, sentence-case controls, nothing leaking past
# the scope. It shares its FAQ accordion (sg_faq / faq_accordion_js) and its stat
# list (.sg-stat*) with the safety page rather than building twins, which is the
# handoff's explicit instruction — one component, reconciled.
#
# Two honesty edits vs the handoff, both documented on D.SUPPORT: the hero runs
# TWO stats not three (the invented "91%" is dropped), and the status pill reads
# the real FOOT_SUPPORT_ONLINE seam instead of a hard-coded "6 on shift".
#
# The form is no longer a facade: it POSTs to /api/support, which mails the
# ticket to SUPPORT_EMAIL with the visitor in Reply-To (src/support.py →
# src/mailer.py). It keeps the facade's honesty for the case where no mailbox is
# configured — a build without SMTP_* says plainly that nothing was emailed and
# names the address, the same call the demo page's "link sent" notice makes.
def sp_status():
    """The hero status pill — a status, not a statistic. Wired to the same
    FOOT_SUPPORT_ONLINE seam the footer's support card reads, so the two can
    never disagree about whether anyone is at the keyboard. Online: a pulsing
    green dot and 'Staffed right now'. Offline: it degrades to the typical
    reply time rather than lying about someone being on shift."""
    dot = ('<span class="sp-status-dot" aria-hidden="true">'
           '<span class="sp-status-core"></span></span>')
    if FOOT_SUPPORT_ONLINE:
        return (f'<div class="sp-status">{dot}'
                '<span class="sp-status-t"><b>Staffed right now</b> — '
                'someone is in #support</span></div>')
    reply = D.STATS.get("reply")
    tail = ' — typical reply <b>%s</b>' % esc(reply) if reply else ""
    return (f'<div class="sp-status sp-status-away">{dot}'
            f'<span class="sp-status-t">Away just now{tail}</span></div>')


def sp_stats():
    """The hero's figure column — the same .sg-stat* component the safety page
    uses. Each figure is read from D.STATS by key (never typed), so the reply
    time and the Discord size can't drift from the rest of the site."""
    rows = ""
    for key, label in D.SUPPORT["stats"]:
        fig = D.STATS.get(key, "")
        if not fig:
            continue
        rows += ('<div class="sg-stat"><span class="sg-stat-f">%s</span>'
                 '<span class="sg-stat-l">%s</span></div>' % (esc(fig), esc(label)))
    return '<div class="sg-stats sp-stats">%s</div>' % rows if rows else ""


def sp_channels():
    """The two channel cards. Discord is accent-bordered and carries the filled
    invite — that is the whole recommendation, made without a word of copy;
    email is the plain card with a copy-address chip. The Discord mark is the
    site's own Blurple lockup (`_discord_mark`), the one place a brand colour
    other than the accent appears — kept in step with the auth panel's mark."""
    reply = D.STATS.get("reply", "")
    reply_meta = ('<span class="sp-meta-i">%sMedian first reply <b>%s</b></span>'
                  % (_ico("timer", 16, "sp-meta-ico", stroke=True), esc(reply))) if reply else ""
    return f"""<div class="sp-channels">
      <div class="sp-card sp-card-lead" id="discord">
        <div class="sp-card-head">
          <span class="sp-tile sp-tile-dcd">{_discord_mark(20, "sp-tile-mark")}</span>
          <span class="sp-card-heads">
            <span class="sp-card-k sp-card-k-hot">Fastest</span>
            <span class="sp-card-t">Discord — open a ticket in #support</span>
          </span>
        </div>
        <p class="sp-card-b">Public server, private ticket channels. Order questions, refunds,
        booster swaps and pre-sales, 24/7. You can also just read what other buyers are saying
        before you order anything, which is rather the point of it being public.</p>
        <div class="sp-meta">
          {reply_meta}
          <span class="sp-meta-i">{_ico("clock-countdown", 16, "sp-meta-ico", stroke=True)}Open 24/7</span>
        </div>
        <a class="sp-invite" href="{esc(DISCORD_URL)}" target="_blank" rel="noopener noreferrer">Open the Discord invite{_ico("arrow-up-right", 15, "ico")}</a>
      </div>

      <div class="sp-card">
        <div class="sp-card-head">
          <span class="sp-tile sp-tile-mail">{_ico("envelope", 20, "sp-tile-ico", stroke=True)}</span>
          <span class="sp-card-heads">
            <span class="sp-card-k">On the record</span>
            <span class="sp-card-t">Email — {SUPPORT_EMAIL}</span>
          </span>
        </div>
        <p class="sp-card-b">Better for anything involving a payment dispute or a document. Answered
        in under two hours during EU and NA daytime, under six overnight.</p>
        <div class="sp-meta sp-meta-split">
          <span class="sp-meta-i">{_ico("paperclip", 16, "sp-meta-ico", stroke=True)}Attachments and receipts welcome</span>
          <button type="button" class="sp-cc" data-sp-copy="{SUPPORT_EMAIL}">
            <span class="sp-cc-t sp-cc-t-idle">Copy address</span>
            <span class="sp-cc-t sp-cc-t-done">Copied</span>
            {_ico("copy", 12, "sp-cc-ico sp-cc-ico-c", stroke=True)}{_ico("check", 12, "sp-cc-ico sp-cc-ico-k", stroke=True)}
          </button>
        </div>
      </div>
    </div>"""


def sp_include():
    """"What to put in it" — four rows that cut a round trip out of every ticket.
    That is the content the form band's left-column void was asking for, and it
    is worth more than a bigger form. Row 4 is the point of the list."""
    rows = "".join(
        f'<li class="sp-inc">{_ico(icon, 19, "sp-inc-ico", stroke=True)}'
        f'<span class="sp-inc-t"><span class="sp-inc-n">{esc(name)}</span>'
        f'<span class="sp-inc-note">{esc(note)}</span></span></li>'
        for icon, name, note in D.SUPPORT["include"])
    return (f'<div class="sp-include"><span class="sp-inc-h">What to put in it</span>'
            f'<ul class="sp-inc-list">{rows}</ul></div>')


def sp_form():
    """The contact form. It leads with a topic — five chips — because the topic
    sets the message placeholder to the thing support needs for that topic and
    shows or hides the order-number field. That is triage the buyer does for
    free, in one tap. Both the note line and the copy chip ship their two states
    as sibling nodes toggled by CSS, so i18n keeps matching whole text nodes.

    **It POSTs to `/api/support` and the mail is real** (src/support.py →
    src/mailer.py): the ticket lands in SUPPORT_EMAIL with the visitor in
    Reply-To. Three outcomes ship as three sibling nodes, all `hidden` until one
    is chosen, for the whole-text-node reason above — sent, "the mailbox isn't
    configured on this deploy" (the 503, which is what the static preview and
    any key-less deploy get), and "it didn't send, here is the address". The
    fallback keeps the old facade's honesty: it says plainly that nothing was
    emailed rather than confirming something that did not happen.

    The honeypot is a real defence, not decoration: `/api/support` is public and
    points at our own inbox. It is labelled, `tabindex="-1"` and
    `aria-hidden` — hidden from people and from assistive tech, present in the
    DOM for the bots that fill every field they find."""
    chips = ""
    for i, (label, needs, ph) in enumerate(D.SUPPORT["topics"]):
        sel = " is-sel" if i == 0 else ""
        chips += (f'<button type="button" class="sp-chip{sel}" data-sp-chip="{i}" '
                  f'data-sp-needs="{1 if needs else 0}" data-sp-ph="{esc(ph)}" '
                  f'aria-pressed="{"true" if i == 0 else "false"}">{esc(label)}</button>')
    first_ph = esc(D.SUPPORT["topics"][0][2])
    order_hidden = "" if D.SUPPORT["topics"][0][1] else " hidden"
    return f"""<form class="sp-form" data-sp-form novalidate>
      <span class="sp-flabel">What's it about</span>
      <div class="sp-chips">{chips}</div>

      <div class="sp-frow sp-frow-mt">
        <label class="sp-flabel" for="sp-email">Email</label>
        <span class="sp-tag sp-tag-req">Required</span>
      </div>
      <!-- id + name are load-bearing: without a name the browser cannot tell
           this apart from the order-number box below and autofills the email
           into that field instead. `autocomplete="off"` on the order box is the
           other half — it stops autofill targeting a free-text field at all. -->
      <input class="sp-input" id="sp-email" name="email" type="email" data-sp-email
             placeholder="you@example.com" autocomplete="email" inputmode="email">

      <div class="sp-order" data-sp-order-field{order_hidden}>
        <div class="sp-frow">
          <label class="sp-flabel" for="sp-order">Order number</label>
          <span class="sp-tag sp-tag-opt">Optional</span>
        </div>
        <input class="sp-input sp-input-code" id="sp-order" name="order" type="text"
               data-sp-order-input placeholder="ESB-3F92K1" autocomplete="off">
        <span class="sp-help">{_ico("envelope-open", 15, "sp-help-ico", stroke=True)}On your confirmation email, under the total.</span>
      </div>

      <label class="sp-flabel sp-flabel-mt" for="sp-message">Message</label>
      <textarea class="sp-input sp-textarea" id="sp-message" name="message" data-sp-msg placeholder="{first_ph}"></textarea>

      <div class="sp-hp" aria-hidden="true">
        <label for="sp-company">Company</label>
        <input id="sp-company" type="text" name="company" tabindex="-1" autocomplete="off" data-sp-hp>
      </div>

      <p class="sp-note" data-sp-note>
        <span class="sp-note-idle">One thread per message. Discord and email land in the same
        place, so pick either — not both.</span>
        <span class="sp-note-err">Add an email we can reply to, and a line or two about what happened.</span>
      </p>

      <button class="sp-send" type="submit" data-sp-send>
        <span class="sp-send-t sp-send-t-idle">Send message</span>
        <span class="sp-send-t sp-send-t-busy">Sending…</span>{_ico("arrow", 15, "ico")}</button>

      <div class="sp-sent" data-sp-sent hidden>
        {_ico("send", 16, "sp-sent-ico", stroke=True)}
        <span class="sp-sent-t"><b>Sent — it's in the inbox.</b>
        <span>The reply lands at</span> <b data-sp-sent-email>your address</b><i aria-hidden="true">.</i>
        <span>Discord is quicker if you'd rather not wait.</span></span>
      </div>

      <div class="sp-sent sp-sent-note" data-sp-preview hidden>
        {_ico("send", 16, "sp-sent-ico", stroke=True)}
        <span class="sp-sent-t"><b>Noted — this is a preview.</b>
        <span>Nothing was emailed: this build has no mailbox configured. Write to</span>
        <b>{SUPPORT_EMAIL}</b> <span>and it reaches the same people.</span></span>
      </div>

      <div class="sp-sent sp-sent-warn" data-sp-failed hidden>
        {_ico("warn", 16, "sp-sent-ico", stroke=True)}
        <span class="sp-sent-t"><b>That didn't send.</b>
        <span>Rather than lose it, write to</span> <b>{SUPPORT_EMAIL}</b>
        <span>or open a ticket in Discord — both land in the same place.</span></span>
      </div>

      <div class="sp-foot">
        {_ico("lock-simple", 14, "sp-foot-ico", stroke=True)}
        <span>We never ask for your game password here, or anywhere else.</span>
      </div>
    </form>"""


def page_support():
    body = f"""<section class="sp">
  <div class="sp-hatch" aria-hidden="true"></div>

  <div class="sp-band sp-band-1">
    <div class="sp-glow" aria-hidden="true"></div>
    <div class="wrap sp-grid-1">
      <div class="sp-copy">
        <span class="sp-kicker">Support</span>
        <h1 class="sp-h1">Two ways in. Both are read by people.</h1>
        <p class="sp-lede">No ticket robot, no "we'll get back to you within 48 hours". Discord is
        the fast one — that's where this market already lives, and it's where our staff sit all day.</p>
        {sp_status()}
        {sp_stats()}
      </div>
      {sp_channels()}
    </div>
  </div>

  <div class="sp-band sp-band-2">
    <div class="wrap sp-grid-2">
      <div class="sp-copy">
        {sec_kicker("02", "Write in")}
        <h2 class="sp-h2">Or write it here</h2>
        <p class="sp-lede sp-lede-2">Goes to the same inbox. If you have an order number, include
        it — it puts the message in front of the person handling that order.</p>
        {sp_include()}
      </div>
      {sp_form()}
    </div>
  </div>

  <div class="sp-band sp-band-3">
    <div class="wrap sp-grid-3">
      <div class="sp-copy sp-faq-copy">
        {sec_kicker("03", "FAQ")}
        <h2 class="sp-h2 sp-h2-faq">Before you write in</h2>
        <p class="sp-faq-note">Six answers that between them close most of the tickets we get.
        If yours isn't here, Discord is two clicks away.</p>
        <a class="btn btn-outline btn-sm sp-ask" href="#discord">{_discord_mark(16, "ico sp-ask-mark")}Ask in Discord</a>
      </div>
      {sg_faq(D.SUPPORT["faq"])}
    </div>
  </div>
</section>

{cta_band(title="Still stuck? Ask us.", sub="Discord is the fast one — our staff sit in it all day. Or write in above and it lands in the same inbox.", cta=("Ask us", "#discord"), readback=False)}"""
    js = faq_accordion_js() + """<script>
(function () {
  var form = document.querySelector('[data-sp-form]');
  if (!form) return;
  var chips = [].slice.call(form.querySelectorAll('[data-sp-chip]'));
  var orderField = form.querySelector('[data-sp-order-field]');
  var email = form.querySelector('[data-sp-email]');
  var msg = form.querySelector('[data-sp-msg]');
  var note = form.querySelector('[data-sp-note]');
  var sent = form.querySelector('[data-sp-sent]');
  var preview = form.querySelector('[data-sp-preview]');
  var failed = form.querySelector('[data-sp-failed]');
  var sentEmail = form.querySelector('[data-sp-sent-email]');
  var orderInput = form.querySelector('[data-sp-order-input]');
  var hp = form.querySelector('[data-sp-hp]');
  var send = form.querySelector('[data-sp-send]');
  var busy = false;

  // One slot, three outcomes. All three ship in the DOM and are toggled here,
  // never written — i18n matches whole text nodes, so a sentence assembled in
  // JS would arrive untranslated.
  function results(which) {
    [sent, preview, failed].forEach(function (n) { if (n) n.hidden = n !== which; });
  }

  function clearErr() {
    note.classList.remove('is-err');
    email.classList.remove('is-err');
    results(null);
  }

  // The topic is the cheapest triage on the page: it sets the message
  // placeholder and shows the order-number field. Changing topic must NOT
  // clear what has been typed — only the placeholder changes.
  function selectChip(chip) {
    chips.forEach(function (c) {
      var on = c === chip;
      c.classList.toggle('is-sel', on);
      c.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    msg.setAttribute('placeholder', chip.getAttribute('data-sp-ph'));
    if (orderField) orderField.hidden = chip.getAttribute('data-sp-needs') !== '1';
  }
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () { selectChip(chip); clearErr(); });
  });
  email.addEventListener('input', clearErr);
  msg.addEventListener('input', clearErr);

  function setBusy(on) {
    busy = on;
    if (send) { send.classList.toggle('is-busy', on); send.disabled = on; }
  }

  function showError() {
    note.classList.add('is-err');
    email.classList.add('is-err');
    results(null);
    email.focus();
  }

  // The real thing: POST /api/support, which composes the ticket server-side
  // and mails it to the support inbox with this address in Reply-To. The
  // client validates first so an obvious typo never costs a round trip, and
  // the server validates again because a browser check is not a check.
  //
  // Three server outcomes, three confirmations: sent (200), "no mailbox on
  // this deploy" (503 — the static preview and any deploy without SMTP), and
  // "it didn't go" (429/502/anything else), which names the address instead of
  // swallowing the message. The topic rides as its INDEX, never its label:
  // the server resolves it against data.py's own list, so the subject line can
  // only ever be one of the five topics this page offers.
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    var addr = (email.value || '').trim();
    var text = (msg.value || '').trim();
    if (!/^[^\\s@]+@[^\\s@]+\\.[a-z]{2,}$/i.test(addr) || text.length < 4) { showError(); return; }
    note.classList.remove('is-err');
    email.classList.remove('is-err');
    results(null);
    setBusy(true);

    var picked = 0;
    chips.forEach(function (c, i) { if (c.classList.contains('is-sel')) picked = i; });
    var body = {
      email: addr, message: text, topic: picked,
      order: (orderField && !orderField.hidden && orderInput ? orderInput.value : '').trim(),
      hp: hp ? hp.value : '',
      tz: (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
                         catch (err) { return ''; } })(),
      lang: (window.ESB_LOCALE && window.ESB_LOCALE.lang) || 'en'
    };

    fetch('/api/support', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
              .then(function (j) { return { status: r.status, data: j }; });
    }).then(function (res) {
      setBusy(false);
      if (res.status === 200 && res.data.sent) {
        if (sentEmail) sentEmail.textContent = addr;
        results(sent);
        msg.value = '';
        if (window.esbTrack) window.esbTrack('generate_lead', { method: 'contact_form' });
        return;
      }
      if (res.status === 503) {                       // no mailbox configured
        results(preview);
        if (window.esbTrack) window.esbTrack('generate_lead', { method: 'contact_form_preview' });
        return;
      }
      if (res.status === 400) { showError(); return; }
      results(failed);
    }).catch(function () { setBusy(false); results(failed); });
  });

  // The copy chip copies the address and confirms for ~1.5s, then reverts.
  var copyBtn = document.querySelector('[data-sp-copy]');
  if (copyBtn) {
    var revert;
    copyBtn.addEventListener('click', function () {
      var addr = copyBtn.getAttribute('data-sp-copy');
      function done() {
        copyBtn.classList.add('is-copied');
        clearTimeout(revert);
        revert = setTimeout(function () { copyBtn.classList.remove('is-copied'); }, 1500);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(addr).then(done, done);
      } else { done(); }
    });
  }
})();
</script>
"""
    return layout("/support.html", "Support — Discord and email, 24/7 | %s" % D.BRAND,
                  "Discord tickets and email support answered by people who play the game. Median "
                  "first reply %s." % D.STATS.get("reply", ""), body, current=None,
                  jsonld=[faq_ld([(q, a) for _fid, q, a in D.SUPPORT["faq"]])], extra_js=js)


# ══════════════════════════════════════════════════════════════════════════
#  /reviews.html — design_handoff_reviews
# ══════════════════════════════════════════════════════════════════════════
# The page has one job: let a sceptic verify the rating instead of taking it on
# faith. Everything is built to serve that, and three of the decisions below
# only make sense in that light —
#
#   · the distribution is a *control*, not a graphic. Its counts are what make
#     "we don't filter by score" checkable, so clicking a row filters the feed;
#   · "Lowest rated" is offered as prominently as "Highest rated". A page that
#     claims it hides nothing must let you go straight to the worst of it, and
#     D.REVIEWS carries the 1★ and 2★ that make the option return something;
#   · every number is derived. The H1's average, the card's figure and the five
#     percentages all come out of D.REVIEW_DIST, and the count line counts the
#     cards actually in the DOM.
#
# What this replaced: the same forty cards at one weight with no filters, no
# distribution and no paging — where nothing was findable and the page's own
# claim was unverifiable because every visible card was a five.
REVIEWS_PAGE = 12    # cards visible before "Load 30 more", per the handoff
REVIEWS_MORE = 30    # what one click costs — the button's label says so


def rating_dist():
    """5★…1★ as (stars, count, pct), computed from D.REVIEW_DIST.

    The percentages are derived here and nowhere else. A typed "83%" beside a
    count it no longer divides into is this page's argument failing in public,
    a centimetre from the sentence that promises the corpus is unfiltered.
    """
    total = sum(D.REVIEW_DIST.values())
    if not total:
        return []
    return [(s, D.REVIEW_DIST.get(s, 0), round(D.REVIEW_DIST.get(s, 0) * 100.0 / total))
            for s in (5, 4, 3, 2, 1)]


def dist_rows():
    """The distribution, drawn as five toggle buttons over the feed's rating.

    4★ and 5★ fill with the accent gradient; 3★ and below fill neutral — a
    negative rating stated plainly rather than dressed in brand colour. Each
    row is a toggle (`aria-pressed`), so clicking the selected one clears back
    to All; the segmented control beside the feed always sets.
    """
    out = ""
    for stars, count, pct in rating_dist():
        n = "{:,}".format(count)
        aria = "Filter to %d-star reviews, %d percent, %s reviews" % (stars, pct, n)
        out += f"""<button class="rvp-drow" type="button" data-rvp-dist="{stars}"
          aria-pressed="false" aria-label="{esc(aria)}">
          <span class="rvp-drow-k">{_ico("star", 11, "rvp-drow-star")}{stars}</span>
          <span class="rvp-drow-bar"><i class="{'is-warm' if stars >= 4 else ''}" style="width:{pct}%"></i></span>
          <span class="rvp-drow-n"><b>{pct}%</b><i aria-hidden="true"> · </i>{n}</span>
        </button>"""
    return out


def review_games():
    """The games the feed can actually be filtered to — those with a review.

    Data-driven for the reason the handoff gives: it draws six chips against
    nine catalogue games, which leaves an Apex review visible under "All games"
    and unreachable by filter. A chip here can never filter to nobody, and a
    tenth game arrives with its own chip.
    """
    have = {_review_game(r)[0]["slug"] for r in D.REVIEWS if _review_game(r)[0]}
    return [g for g in D.GAMES if g["slug"] in have]


def review_filters():
    """Game chips, rating and sort — AND-combined in that order by app.js.

    All three are real radio groups, same markup contract as the roster's
    filters (`role="radio"` + `aria-checked`, arrow-key navigable, one tab
    stop). The rating group and the distribution rows above write one state and
    have to stay in step in both directions.
    """
    chips = ('<button type="button" class="rvp-chip is-wide is-on" role="radio" '
             'aria-checked="true" data-rvp-game="">All games</button>')
    for g in review_games():
        chips += ('<button type="button" class="rvp-chip" role="radio" aria-checked="false" '
                  'data-rvp-game="%s">%s</button>' % (esc(g["slug"]), esc(g["short"])))

    def seg(name, opts, label):
        lid = "rvp-%s-l" % name
        body = ""
        for i, (val, text) in enumerate(opts):
            body += ('<button type="button" class="rvp-seg-opt%s" role="radio" aria-checked="%s" '
                     'data-rvp-%s="%s">%s</button>'
                     % (" is-on" if not i else "", "true" if not i else "false",
                        name, esc(val), text))
        return (f'<div class="rvp-fgroup"><span class="rvp-flabel" id="{lid}">{esc(label)}</span>'
                f'<div class="rvp-seg" role="radiogroup" aria-labelledby="{lid}">{body}</div></div>')

    # "Any", not the handoff's "All": i18n keys are global and "All" is already
    # the roster rail's "All 187 reviews", where French needs "Tous les". One
    # word, two sentences — and a rating filter reads as well either way.
    star = '<i class="rvp-seg-star" aria-hidden="true">&#9733;</i>'
    rating = seg("rating", [("all", "Any"), ("5", "5" + star), ("4", "4" + star),
                            ("low", "3" + star + " <span>or less</span>")], "Rating")
    sort = seg("sort", [("recent", "Most recent"), ("high", "Highest rated"),
                        ("low", "Lowest rated")], "Sort by")
    return f"""<div class="rvp-filters">
      <div class="rvp-fgroup">
        <span class="rvp-flabel" id="rvp-game-l">Game</span>
        <div class="rvp-chips" role="radiogroup" aria-labelledby="rvp-game-l">{chips}</div>
      </div>
      <div class="rvp-fright">{rating}{sort}</div>
    </div>"""


def page_reviews():
    """The aggregate, the distribution as a filter, and the feed under it."""
    score = D.STATS["trustpilot"].split("/")[0].strip()          # "4.8" of "4.8 / 5"
    try:
        fill = float(score) / 5.0
    except ValueError:
        fill = 1.0
    _tp_id[0] += 1
    tiles = _tp_stars_svg(fill, "rvptp%d" % _tp_id[0])

    # The H1 sizes the audience, not the corpus: "4.7 / 5 across 13K customers".
    # Read off STATS["clients"] and never typed, so this and the game-page stat
    # row cannot quote two different sizes of the same client base.
    #
    # ⚠ Note what that makes the headline claim, because the page is built to be
    # checked: the score is the average of REVIEW_DIST's 3,140 reviews, and the
    # distribution card one column to the right prints those same counts. The
    # headline now names the wider population those reviews came from. If the
    # two are ever read as one claim, the fix is the H1 — the card is the page's
    # evidence and REVIEW_DIST is the one place the rating is written.
    #
    # Rounded with its own helper rather than page_game()'s _short_count(),
    # which keeps a decimal ("13.3k") because there the phone abbreviates a
    # figure the desktop prints in full beside it. Here the rounded figure is
    # the only one on the line, and a decimal would read as a precision an
    # invented placeholder has not got.
    def _round_k(s):
        """"13,280" → "13K". Left alone if it isn't a plain number."""
        try:
            n = int(str(s).replace(",", ""))
        except ValueError:
            return str(s)
        return "%dK" % int(n / 1000.0 + 0.5) if n >= 1000 else str(s)

    # Falls back to the review corpus if the client count is ever emptied — the
    # same guard every other reader of STATS["clients"] carries. A headline
    # reading "4.7 / 5 across  customers" is worse than the line it replaced.
    if D.STATS.get("clients"):
        h1_fig, h1_word = _round_k(D.STATS["clients"]), "customers"
    else:
        h1_fig, h1_word = D.STATS["reviews"], "reviews"

    # Every review is rendered; everything past the first page ships `hidden`,
    # so the first page reads correctly with no JS and "Load 30 more" reveals
    # cards that are already in the document rather than fetching. Same
    # arrangement, and the same trade-off, as the roster board.
    now = datetime.now()
    total = len(D.REVIEWS)
    cards = "".join(review_card(r, now, filterable=True, hide=i >= REVIEWS_PAGE)
                    for i, r in enumerate(D.REVIEWS))

    # The external action only exists once D.TRUSTPILOT_URL names *our* profile
    # — the rule the badge and the section link already follow, and the reason
    # it matters most here: this page's whole argument is "go and check", and
    # sending the sceptic to a stranger's profile fails that worse than not
    # offering the trip. Until then the second action is the one the page can
    # honour on its own — the same climb down to the bad reviews the paragraph
    # above it promises, sorted worst first.
    # Direct link out to our Trustpilot profile. Deliberately NOT wired through
    # D.TRUSTPILOT_URL: that constant also gates rating_ld()'s aggregateRating
    # JSON-LD, and turning it on would publish the still-placeholder review
    # distribution to search engines (a manual-action risk — see data.py). The
    # link lives here only until that data is real.
    _tp_url = "https://www.trustpilot.com/review/lolepicshop.com"
    second = (f'<a class="btn btn-secondary" href="{esc(_tp_url)}" '
              f'target="_blank" rel="noopener nofollow">'
              f'<span class="rvp-tp-star" aria-hidden="true">&#9733;</span>'
              f'<span>See our reviews on Trustpilot</span>'
              f'{_ico("arrow-up-right", 13, "ico", stroke=True)}</a>')

    dist = dist_rows()
    hint = (f'<p class="rvp-hint">{_ico("info", 14, "rvp-hint-ico")}'
            f'<span>Click a row to filter the feed by that rating.</span></p>') if dist else ""

    body = f"""<div class="rvp" data-rvp>
  <div class="rvp-hatch" aria-hidden="true"></div>

  <section class="rvp-hero">
    <div class="rvp-glow" aria-hidden="true"></div>
    <div class="wrap rvp-hero-grid">
      <div class="rvp-copy">
        <span class="rvp-kicker">Reviews</span>
        <h1 class="rvp-h1"><b>{esc(D.STATS['trustpilot'])}</b> <span>across</span>
          <b>{esc(h1_fig)}</b> <span>{esc(h1_word)}</span></h1>
        <p class="rvp-lede">Every review below is attached to a paid, completed order — pulled from
        Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so
        one-star reviews sit in the same feed.</p>
        <div class="rvp-acts">
          <a class="btn btn-primary" href="/games">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
          {second}
        </div>
      </div>

      <aside class="rvp-sum" aria-labelledby="rvp-sum-h">
        <h2 class="sr-only" id="rvp-sum-h">Overall rating</h2>
        <div class="rvp-sum-head">
          <div class="rvp-sum-score">
            <span class="rvp-sum-n">{esc(score)}</span>
            <span class="rvp-sum-tp">
              {tiles}
              <span class="rvp-sum-word"><b>Excellent</b> <span>on Trustpilot</span></span>
            </span>
          </div>
          <span class="rvp-pill">{_ico("seal", 11, "rvp-pill-ico", evenodd=True)}<span>Verified only</span></span>
        </div>
        <div class="rvp-dist">{dist}</div>
        {hint}
      </aside>
    </div>
  </section>

  <section class="rvp-feed" id="reviews-feed">
    <div class="wrap">
      {review_filters()}

      <div class="rvp-count-row">
        <p class="rvp-count" aria-live="polite"><span>Showing</span> <b data-rvp-shown>{min(REVIEWS_PAGE, total)}</b>
          <span>of</span> <b data-rvp-total>{total}</b> <span>reviews</span><i data-rvp-crumb aria-hidden="true" hidden></i></p>
        <button type="button" class="rvp-clear" data-rvp-clear hidden>{_ico("x", 12, "ico", stroke=True)}<span>Clear filters</span></button>
      </div>

      <div class="rvp-grid" data-rvp-grid>{cards}</div>

      <div class="rvp-empty" data-rvp-empty hidden>
        {_ico("chat", 28, "rvp-empty-ico", stroke=True)}
        <span class="rvp-empty-h">Nothing matches that yet</span>
        <span class="rvp-empty-b">No review in the feed has that rating for this game. Widen the
        filters to see the rest.</span>
        <button type="button" class="btn btn-outline rvp-empty-btn" data-rvp-clear>Clear filters</button>
      </div>

      <div class="rvp-more-row">
        <button type="button" class="rvp-more" data-rvp-more{'' if total > REVIEWS_PAGE else ' hidden'}>
          <span data-rvp-more-label>Load {REVIEWS_MORE} more</span>{_ico("arrow-down", 14, "ico", stroke=True)}</button>
      </div>
    </div>
  </section>
</div>

{cta_band()}"""
    return layout("/reviews.html", "Reviews — %s" % D.BRAND,
                  "%s from %s verified orders. Unfiltered, one review request per completed order."
                  % (D.STATS["trustpilot"], D.STATS["reviews"]), body, current="/reviews.html")


# ══════════════════════════════════════════════════════════════════════════
#  the free guides landing — design_handoff_free_guides
# ══════════════════════════════════════════════════════════════════════════
# The site's one lead-capture page: two free PDFs for an email. The structural
# decision the handoff asks to preserve is "two guides is a choice inside ONE
# funnel, not two funnels on one page" — one hero, one form, one CTA, with the
# two covers as selectable cards inside the form. Both ticked by default; the
# selection is a game-preference signal to persist with the address.
#
# It uses `chrome_guides()`, a reduced header, for the same reason checkout does
# — a capture page should not offer five exits. The nav item that points here
# from every other page is still "Guides" (see NAV). The form is a facade in
# this build: `initGuides()` in app.js flips a local flag, there is no POST, no
# ESP, no double opt-in. All figures are placeholders (see data.py's GUIDES).

def _gd_tag(game):
    """League/Valorant identity tag — the guide's spine colour again."""
    mod = "gd-tag-lol" if game == "League" else "gd-tag-val"
    return '<span class="gd-tag %s">%s</span>' % (mod, esc(game))


def _gd_cover(g, selected):
    """The CSS book cover — a dark panel, a coloured spine, the brand lockup and
    real type. No imagery; if cover art is commissioned it drops into this box
    and keeps the spine. `--spine` is the guide's own colour."""
    return f"""<span class="gd-cover">
          <span class="gd-cover-glow" aria-hidden="true"></span>
          <span class="gd-cover-spine" aria-hidden="true"></span>
          <span class="gd-cover-brand"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></span>
          <span class="gd-cover-game">{esc(g["game"])}</span>
          <span class="gd-cover-title">{esc(g["cover_title"])}</span>
          <span class="gd-cover-meta">6 chapters · 6 drills</span>
        </span>"""


def _gd_form(second=False):
    """The lead form. Rendered twice — the hero card and the closing band's
    inline capture — sharing one state, so an address typed in one appears in
    the other (`initGuides()` mirrors every `[data-gd-email]`).

    `second` is the compact closing variant: just the email + a "Send them"
    button, no guide cards (they were chosen above) and no success swap of its
    own — submitting either capture flips the hero card to the success state.
    """
    G = D.GUIDES
    if second:
        return f"""<div class="gd-cap2" data-gd-cap>
        <div class="gd-cap2-row">
          <input class="gd-email gd-email-2" type="email" inputmode="email" autocomplete="email"
                 placeholder="you@example.com" aria-label="Email address" data-gd-email>
          <button type="button" class="gd-cta gd-cta-2" data-gd-send>
            <span>Send them</span>{_ico("arrow", 14, "ico", stroke=True)}</button>
        </div>
        <span class="gd-cap2-note" data-gd-ctanote>Arrives in about a minute. No card, no account.</span>
      </div>"""

    cards = ""
    for g in G["items"]:
        cards += f"""<button type="button" class="gd-card" data-gd-card="{esc(g['key'])}"
            data-gd-short="{esc(g['short'])}" aria-pressed="true" style="--spine:{esc(g['accent'])}"
            aria-label="{esc(g['title'])}">
          <span class="gd-check" data-gd-check aria-hidden="true">{_ico("check", 11, "ico", stroke=True)}</span>
          {_gd_cover(g, True)}
          <span class="gd-card-body">
            <span class="gd-card-title">{esc(g['title'])}</span>
            <span class="gd-card-note">{esc(g['note'])}</span>
          </span>
        </button>"""

    score = D.STATS.get("trustpilot", "").split("/")[0].strip()
    return f"""<div class="gd-form" data-gd-form>
        <div class="gd-form-head">
          <span class="gd-form-title">Which do you want?</span>
          <span class="gd-instant"><span class="dot-live dot-ok" aria-hidden="true"></span><span>Instant</span></span>
        </div>
        <p class="gd-form-sub">Take both — they're free, and most people play both.</p>

        <div class="gd-cards">{cards}</div>
        <div class="gd-pick" data-gd-pick aria-live="polite">Both guides, one email, two attachments.</div>

        <span class="gd-label">Email</span>
        <input class="gd-email" type="email" inputmode="email" autocomplete="email"
               placeholder="you@example.com" aria-label="Email address" data-gd-email>
        <div class="gd-note" data-gd-note>Used to send the guides. Nothing else unless you tick the box below.</div>

        <button type="button" class="gd-cta" data-gd-send>
          <span data-gd-cta>Send me both guides</span>{_ico("arrow", 15, "ico", stroke=True)}</button>

        <button type="button" class="gd-optin" data-gd-optin aria-pressed="true">
          <span class="gd-optbox" data-gd-optbox aria-hidden="true">{_ico("check", 10, "ico", stroke=True)}</span>
          <span class="gd-optin-t">Also send me one email a month with new guides and patch notes. Nothing else, and one click unsubscribes.</span>
        </button>

        <div class="gd-privacy">{_ico("lock", 13, "ico", stroke=True)}<span>We never sell your address. <a href="/legal/privacy.html">Privacy policy</a></span></div>
      </div>

      <div class="gd-success" data-gd-success hidden>
        <span class="gd-success-ico" aria-hidden="true">{_ico("send", 24, "ico", stroke=True)}</span>
        <span class="gd-success-h">Check your inbox.</span>
        <p class="gd-success-b"><span data-gd-sentline>Both guides are</span> on the way to
          <b data-gd-email-out>your address</b>. If nothing lands in two minutes, look in promotions — it
          sometimes goes there first.</p>
        <button type="button" class="gd-reset" data-gd-reset>{_ico("undo", 13, "ico", stroke=True)}<span>Use a different address</span></button>
      </div>

      <div class="gd-tp">{_ico("star", 15, "ico gd-tp-star")}<span>From the team behind
        <b>{esc(D.STATS.get("clients", ""))} clients</b> and {esc(score)} / 5 on Trustpilot.</span></div>"""


def page_guides():
    G = D.GUIDES
    st = G["stats"]

    # ── hero stat row ──
    stat_cells = [
        (str(st["downloads"]), "Players downloaded them"),
        (str(st["chapters"]), "Chapters + %d drills" % st["drills"]),
    ]
    stats_html = ""
    for i, (fig, lab) in enumerate(stat_cells):
        if i:
            stats_html += '<span class="gd-stat-div" aria-hidden="true"></span>'
        stats_html += (f'<div class="gd-stat"><span class="gd-stat-n">{esc(fig)}</span>'
                       f'<span class="gd-stat-l">{esc(lab)}</span></div>')
    # The rating cell pairs a figure with its "/ 5" unit, so it rides in its own
    # node the way the reviews page's does.
    stats_html += ('<span class="gd-stat-div" aria-hidden="true"></span>'
                   f'<div class="gd-stat"><span class="gd-stat-rate"><b>{esc(st["rating"])}</b>'
                   f'<span>/ 5</span></span><span class="gd-stat-l">Reader rating</span></div>')

    guarantees = [
        ("file", "PDFs, yours to keep"),
        ("badge", "Free, and they stay free"),
        ("envelope", "One email, no spam"),
    ]
    grow = "".join('<span class="gd-guar">%s<span>%s</span></span>'
                   % (_ico(ic, 16, "ico gd-guar-ico", stroke=True), esc(t))
                   for ic, t in guarantees)

    # ── band 01 — what's inside ──
    toc_cols = ""
    for g in G["items"]:
        rows = ""
        for num, name, note in G["toc"][g["key"]]:
            rows += f"""<div class="gd-ch">
            <span class="gd-ch-n">{esc(num)}</span>
            <span class="gd-ch-body"><span class="gd-ch-name">{esc(name)}</span>
              <span class="gd-ch-note">{esc(note)}</span></span>
            <span class="gd-ch-drill">{_ico("target", 11, "ico gd-ch-drill-ico", stroke=True)}<span>Drill</span></span>
          </div>"""
        toc_cols += f"""<div class="gd-toc-col">
          <div class="gd-toc-head">
            <span class="gd-toc-badge" style="--gd-badge:{esc(g['accent'])}">{esc(g['initial'])}</span>
            <span class="gd-toc-titles"><span class="gd-toc-title">{esc(g['title'])}</span>
              <span class="gd-toc-meta">{esc(g['game'])} · 6 chapters, 6 drills</span></span>
          </div>
          {rows}
        </div>"""

    # ── band 02 — who wrote them ──
    author_rows = "".join(f"""<div class="gd-author">
          <span class="gd-author-av" aria-hidden="true">{esc(a['initial'])}</span>
          <span class="gd-author-body"><span class="gd-author-name">{esc(a['name'])}</span>
            <span class="gd-author-meta">{esc(a['meta'])}</span></span>
          {_gd_tag(a['game'])}
        </div>""" for a in G["authors"])

    # ── band 03 — readers ──
    stars = "".join(_ico("star", 13, "ico gd-q-star") for _ in range(5))
    quote_cards = "".join(f"""<div class="gd-q">
          <div class="gd-q-top"><span class="gd-q-stars">{stars}</span>{_gd_tag(q['game'])}</div>
          <p class="gd-q-body">{esc(q['body'])}</p>
          <div class="gd-q-foot"><span class="gd-q-av" aria-hidden="true">{esc(q['initials'])}</span>
            <span class="gd-q-name"><b>{esc(q['name'])}</b> · {esc(q['rank'])}</span></div>
        </div>""" for q in G["quotes"])
    rscore = D.STATS.get("trustpilot", "").split("/")[0].strip()

    # ── band 04 — FAQ ──
    # Native single-open accordion (details[name]) so it reads correctly with no
    # JS; item 1 opens on load. The number and the +/- marker are CSS. The
    # answers stay in the DOM, which is what the FAQPage JSON-LD below asserts.
    faq_rows = ""
    for i, (fid, q, a) in enumerate(G["faq"]):
        faq_rows += f"""<details class="gd-faq-item" name="gd-faq" id="guide-faq-{esc(fid)}"{' open' if i == 0 else ''}>
          <summary class="gd-faq-q"><span class="gd-faq-n">{'0%d' % (i + 1)}</span>
            <span class="gd-faq-qt">{esc(q)}</span>
            <span class="gd-faq-mark" aria-hidden="true"><i class="gd-faq-plus"></i><i class="gd-faq-minus"></i></span></summary>
          <div class="gd-faq-a">{esc(a)}</div>
        </details>"""

    body = f"""<div class="gd" data-gd>
  <div class="gd-hatch" aria-hidden="true"></div>

  <section class="gd-hero">
    <div class="gd-hero-glow" aria-hidden="true"></div>
    <div class="wrap gd-hero-grid">
      <div class="gd-hero-copy">
        <span class="gd-kicker">{_ico("book", 13, "ico gd-kicker-ico", stroke=True)}<span>Free guides</span></span>
        <h1 class="gd-h1">The two guides our boosters actually wrote.</h1>
        <p class="gd-lede">One for League, one for Valorant. Six chapters and six drills each, on the
        things that decide games between Silver and Ascendant. Written by the people on our roster who
        play those ranks every day.</p>
        <div class="gd-guars">{grow}</div>
        <div class="gd-hero-rule" aria-hidden="true"></div>
        <div class="gd-stats">{stats_html}</div>
      </div>

      <aside class="gd-hero-form" aria-label="Get the guides">
        <div class="gd-card-shell">
          {_gd_form()}
        </div>
      </aside>
    </div>
  </section>

  <section class="gd-band gd-band-toc">
    <div class="wrap">
      <div class="gd-band-head">
        <div class="gd-eyebrow-wrap">
          <span class="gd-num">01</span><span class="gd-eyebrow-div" aria-hidden="true"></span>
          <span class="gd-eyebrow">What's inside</span>
        </div>
        <h2 class="gd-h2">Six chapters each, no padding.</h2>
        <p class="gd-band-sub">Every chapter ends with a drill you can run in a custom game in under ten
        minutes. That is the whole format: read it, then do it.</p>
      </div>
      <div class="gd-toc">{toc_cols}</div>
    </div>
  </section>

  <section class="gd-band gd-band-authors">
    <div class="wrap gd-authors-grid">
      <div class="gd-authors-copy">
        <div class="gd-eyebrow-wrap">
          <span class="gd-num">02</span><span class="gd-eyebrow-div" aria-hidden="true"></span>
          <span class="gd-eyebrow">Who wrote them</span>
        </div>
        <h2 class="gd-h2">Written by people who play these ranks for a living.</h2>
        <p class="gd-band-sub">Not a content team reading patch notes. Boosters from our own roster wrote
        a chapter each, and every claim is something they do in ranked that week — not theory borrowed
        from a pro scene you will never play in.</p>
        <div class="gd-authors-facts">
          <span class="gd-guar">{_ico("users", 17, "ico gd-guar-ico", stroke=True)}<span>Seven authors across two games</span></span>
          <span class="gd-guar">{_ico("undo", 17, "ico gd-guar-ico", stroke=True)}<span>Rewritten every patch cycle</span></span>
        </div>
      </div>
      <div class="gd-authors-card">
        <div class="gd-authors-card-head">
          <span class="gd-authors-card-t">The authors</span>
          <span class="gd-verified">{_ico("seal", 11, "ico", evenodd=True)}<span>Verified</span></span>
        </div>
        {author_rows}
      </div>
    </div>
  </section>

  <section class="gd-band gd-band-readers">
    <div class="wrap">
      <div class="gd-band-head gd-band-head-row">
        <div>
          <div class="gd-eyebrow-wrap">
            <span class="gd-num">03</span><span class="gd-eyebrow-div" aria-hidden="true"></span>
            <span class="gd-eyebrow">Readers</span>
          </div>
          <h2 class="gd-h2">What they changed for them.</h2>
        </div>
        <div class="gd-readers-rate">
          <span class="gd-stat-rate"><b>{esc(rscore)}</b><span>/ 5</span></span>
          <span class="gd-stat-l">From {esc(str(st["readers"]))} readers</span>
        </div>
      </div>
      <div class="gd-quotes">{quote_cards}</div>
    </div>
  </section>

  <section class="gd-band gd-band-faq">
    <div class="wrap gd-faq-grid">
      <div class="gd-faq-copy">
        <div class="gd-eyebrow-wrap">
          <span class="gd-num">04</span><span class="gd-eyebrow-div" aria-hidden="true"></span>
          <span class="gd-eyebrow">FAQ</span>
        </div>
        <h2 class="gd-h2">Before you hand over an email</h2>
        <p class="gd-band-sub">Fair questions. We would ask them too.</p>
      </div>
      <div class="gd-faq">{faq_rows}</div>
    </div>
  </section>

  <section class="gd-close">
    <div class="gd-close-glow" aria-hidden="true"></div>
    <div class="wrap gd-close-in">
      <div class="gd-close-copy">
        <h2 class="gd-close-h">Two guides. One email address.</h2>
        <div class="gd-guars">
          <span class="gd-guar">{_ico("lock", 16, "ico gd-guar-ico", stroke=True)}<span>Never sold, never rented</span></span>
          <span class="gd-guar">{_ico("check", 16, "ico gd-guar-ico", stroke=True)}<span>One click unsubscribes</span></span>
        </div>
      </div>
      {_gd_form(second=True)}
    </div>
  </section>
</div>"""

    ld = faq_ld([(q, a) for _fid, q, a in G["faq"]])
    return layout("/guides.html", "Free League & Valorant guides — %s" % D.BRAND,
                  "Two free field guides written by our boosters — six chapters and six drills each for "
                  "League and Valorant. One email, no spam, yours to keep.",
                  body, current="/guides.html", jsonld=[ld],
                  head=chrome_guides(), foot=foot_min(), body_class="gd-page")


# ══════════════════════════════════════════════════════════════════════════
#  the demo page — design_handoff_track_order
# ══════════════════════════════════════════════════════════════════════════
# One page, two states, exactly as the handoff draws them: the lookup (plus the
# Dashboard band, which answers "what does the link open?" with the interface
# itself) and the resolved order. The handoff's own note says these are two
# routes in production — /track and /orders/:token — because the emailed link
# has to deep-link. This build has no order store and no email, so both states
# render the one placeholder order, `?order=<id>` is the deep link, and the page
# is called Demo rather than "Track my order": there is nothing here to track.
#
# Ported at the same fidelity as the checkout and the order card, with its
# tokens scoped to `.tk` in site.css. Deviations, all deliberate:
#
#   · The full site chrome stays. The handoff drops it for checkout's reason —
#     "this is a task page, the only exits are support and the brand mark" —
#     which is true of a guest chasing an order and false of a visitor who
#     clicked Demo in the menu. Renaming the page inverts that argument.
#   · The "link sent" notice says no email was sent, because none is. The
#     handoff kills a dev line under the submit button as a bug, and it was
#     right — but that line leaked build detail into a product page, and this
#     one states what the page you are on is. The alternative is a confirmation
#     that nothing happened.
#   · "All 38 games" is not drawn: the replay view does not exist. Same rule
#     that keeps the live feed's rows unlinked.
#   · Pause is a real button that puts the card into a paused state. The
#     handoff leaves that state undesigned, but a dead control on a page whose
#     whole job is demonstrating the product is worse than a plain one.
#   · Message and the booster's profile link go to real destinations
#     (/support.html — support reads the same thread, per DASHBOARD_POINTS —
#     and the booster's own profile page).
def _demo_lookup(O):
    """State 1, band 1 — the two routes back into an order, and what they are.

    The two identifiers are separated by a real OR divider rather than by a
    field label reading "or the email you paid with", which is what made the
    old form read as though both were required.
    """
    return f"""<section class="section tk tk-look" data-demo-view="lookup">
  <div class="tk-hatch" aria-hidden="true"></div>
  <div class="tk-glow" aria-hidden="true"></div>
  <div class="wrap tk-grid">
    <div class="tk-copy">
      <span class="kicker">Demo</span>
      <h1 class="tk-h1">Your link works without a password.</h1>
      <p class="tk-lede">Guest orders are tracked by the link we emailed you. Lost it? Put the
      address you paid with below and we'll send it again. Nothing to remember, nothing to reset.</p>
      <div class="tk-assure">
        <span class="tk-assure-l">{_ico("ghost", 17, "tk-assure-i")}No account, no password — the link is the login</span>
        <span class="tk-assure-l">{_ico("infinity", 17, "tk-assure-i", stroke=True)}It never expires and works on any device</span>
      </div>
    </div>

    <form class="tk-card" data-demo-form novalidate>
      <div class="tk-card-head">
        <h2 class="tk-card-t">Find your order</h2>
        <span class="tk-safe">{_ico("shield-check", 11, "ico", stroke=True)}Guest safe</span>
      </div>

      <label class="tk-lab" for="tk-code">Order number</label>
      <input class="tk-in tk-in-code" id="tk-code" name="order" placeholder="{esc(O['id'])}"
             autocomplete="off" autocapitalize="characters" spellcheck="false" data-demo-code>
      <p class="tk-note" data-demo-note>On your confirmation email, under the total.</p>

      <div class="tk-or" aria-hidden="true"><span></span><span class="tk-or-w">or</span><span></span></div>

      <label class="tk-lab" for="tk-mail">The email you paid with</label>
      <input class="tk-in" id="tk-mail" name="email" type="email" placeholder="you@example.com"
             autocomplete="email" data-demo-mail>
      <p class="tk-help">We resend the link to that address. It never expires and it works on any device.</p>

      <button class="tk-submit" type="submit"><span data-demo-label>Find my order</span>{_ico("arrow", 15, "ico", stroke=True)}</button>

      <div class="tk-sent" data-demo-sent hidden>
        {_ico("send", 16, "tk-sent-i", stroke=True)}
        <span><b>Demo — no email was sent.</b> On the live site the link reaches
        <i data-demo-addr>you@example.com</i> inside a minute, it never expires, and it opens the
        dashboard below on any device.</span>
      </div>

      <p class="tk-hint">{_ico("envelope", 16, "tk-hint-i", stroke=True)}<span>The order number is in
      your confirmation email, on the line under the total.</span></p>
    </form>
  </div>
</section>"""


# The titles the live-watch feature covers — now EVERY game in the catalogue,
# which is a business decision (the `stream` add-on in data.py is offered on all
# nine) rather than a technical one. It stays a named list rather than being
# deleted for the reason it existed: the constraint is real and per-title, and
# narrowing it again has to be one edit here.
#
# What the customer watches is never the game's own spectator mode. Valorant has
# no spectator API at all (observers exist only in custom/tournament lobbies),
# and League's Spectator-v5 is ~3 minutes behind and needs a Riot production key
# no boosting service is granted. So the product is the booster's OWN SCREEN,
# shared into a private Discord voice channel — which is why it generalises to
# all nine titles at once: it never depended on the game, only on the booster.
#
# ⚠ That is also the whole risk. Listing a game here is a claim that a booster
# on it will actually stream, and the live half is NOT BUILT (see CLAUDE.md's
# "Watch live" section — streams.py, the gated /api/stream, the Discord channel
# per order). Nine titles is nine rosters that have to be briefed, not one.
WATCH_GAMES = tuple(g["slug"] for g in D.GAMES)


def offers_watch(g):
    """True when this game's orders can be watched live — every catalogue title
    today. Kept as a function rather than inlined `True` so narrowing it back to
    an allow-list is one edit in WATCH_GAMES, the way offers_coaching() reads a
    per-game field."""
    return (g or {}).get("slug") in WATCH_GAMES


def watch_panel(O, b, game):
    """"Watch live" — the customer's door into their booster's screen share.

    Discord carries the video; this panel carries the *state*. There is no
    embedded player and there is not going to be one: Discord has no iframe
    player for Go Live, so the honest shape is a status card plus a link out,
    not a video frame that would have to be faked. What the panel owes the
    visitor is the one thing the dashboard knows and Discord does not surface
    from outside — whether their booster is streaming right now.

    Both states ship in the DOM with one hidden, the whole-text-node rule the
    header's auth tabs and the mode-conditional add-ons follow: a sentence
    written in by JS arrives untranslated. The state is driven by the page
    script, which ties it to Pause — a paused order is not being played, so it
    cannot be being streamed, and two panels contradicting each other is the
    same defect the status pill fixed.

    The Discord mark is `_hd_brand()`'s, so this button and the OAuth button
    carry one mark; it is a simplified reproduction and carries the same
    pre-launch swap as `pay_marks()`.
    """
    if not offers_watch(game):
        return ""
    handle = esc(O["booster"] if not b else b["handle"])
    return f"""<div class="tko-watch" data-watch>
          <div class="tko-watch-t">
            <span class="tk-lab">Watch live</span>
            <span class="tko-watch-st" data-watch-st>
              <span class="dot-live dot-ok" aria-hidden="true"></span>
              <span data-watch-when="live">Streaming now</span>
              <span data-watch-when="off" hidden>Not streaming</span>
            </span>
          </div>
          <div class="tko-watch-b">
            {_ico("monitor", 19, "tko-watch-i", evenodd=True)}
            <span class="tko-watch-c">
              <span class="tko-watch-n"><b>{handle}</b>
                <span data-watch-when="live">is sharing their screen.</span>
                <span data-watch-when="off" hidden>isn't streaming right now.</span></span>
              <span class="tko-watch-m">{esc(game["name"])}<i aria-hidden="true"> · </i>Discord screen share</span>
            </span>
          </div>
          <a class="tko-watch-go" href="{esc(D.DISCORD_URL)}" target="_blank" rel="noopener">
            {_hd_brand("discord", 16, "tko-watch-d")}
            <span data-watch-when="live">Join and watch</span>
            <span data-watch-when="off" hidden>Open the order channel</span>
          </a>
          <p class="tko-watch-p">{_ico("lock-key", 14, "tko-watch-l", stroke=True)}
            <span>The channel is private to you and your booster, and closes when the order is delivered.</span></p>
        </div>"""


def _demo_rail(O):
    """The resolved order's right rail — booster, details, timeline, guarantee.

    Everything here is derived from the fixture and from data the rest of the
    site already renders: the booster is a roster entry (so the card and the
    profile it links to can never quote different numbers), the add-ons are
    ADDONS ids that were priced into the total on the "Paid" row, and the
    guarantee note's promise is the guarantee page's own wording rather than a
    second, drifting copy of the refund policy.
    """
    b = next((x for x in D.BOOSTERS if x["handle"] == O["booster"]), None)
    # No such booster → no card, the same way spotlight_card() handles it. An
    # order does have a booster, so the rest of the rail still renders.
    # The ring is amber, not the roster's free/busy green — this booster is on
    # *your* order, so the availability that colour encodes everywhere else on
    # the site has no meaning here. Same face as the roster otherwise, so a
    # photograph dropped into assets-in/avatar/<handle> lands in both.
    bst = "" if not b else f"""<div class="tko-card tko-bst">
          <span class="tko-avatar">{booster_face(b, px=40, lazy=False, glyph=21)}</span>
          <span class="tko-bst-c">
            <span class="tko-bst-n">{esc(b['handle'])}</span>
            <span class="tko-bst-m">{esc(b['peak'])}<i aria-hidden="true"> · </i><b>{b['orders']}</b> orders delivered</span>
          </span>
          <a class="tko-bst-go" href="{booster_href(b)}" aria-label="{esc('%s profile' % b['handle'])}">{_ico("arrow-up-right", 13, "ico", stroke=True)}</a>
        </div>"""

    details = [
        ("Game", esc(O["game"])),
        ("Queue · Server", "%s<i aria-hidden=\"true\"> · </i>%s" % (esc(O["mode"]), esc(O["region"]))),
        ("Play window", esc(O["window"])),
        ("Add-ons", ", ".join(esc(a) for a in O["addon_labels"]) or "None"),
        ("Paid", "%s<i aria-hidden=\"true\"> · </i>%s" % (money(O["price"]), esc(O["paid_on"]))),
    ]
    det = "".join(f'<div class="tko-det-r"><span class="tko-det-k">{esc(k)}</span>'
                  f'<span class="tko-det-v">{v}</span></div>' for k, v in details)

    # Timeline, newest first. Rank rows draw the same mark + tier-name pair as
    # every other rank readout on the site — a mark alone is the division
    # numeral, so "IV reached" would not say which ladder rung was reached.
    # `last` drops the connector: the line is painted as a 1px background on the
    # 13px dot column, not as a border on the row, so the final row would
    # otherwise trail a stub past the last dot.
    def tl_row(body, when, live=False, last=False):
        return (f'<div class="tko-tl-r{" is-last" if last else ""}">'
                f'<span class="tko-tl-rail"><span class="tko-tl-dot'
                f'{" is-live" if live else ""}"></span></span>'
                f'<span class="tko-tl-c"><span class="tko-tl-n">{body}</span>'
                f'<span class="tko-tl-w">{when}</span></span></div>')

    tl = ""
    for tier, div, when, state in O["events"]:
        m = tier_mark(_DEMO_GAME, tier, div or tier[:2].upper(), base="tko-tl-mark")
        tl += tl_row('%s<b>%s %s</b> reached' % (m, esc(tier), esc(div)), esc(when),
                     live=state == "live")
    tl += tl_row('<b>%s</b> claimed the order' % esc(O["booster"]),
                 '%s<i aria-hidden="true"> · </i><b>%d min</b> after payment'
                 % (esc(O["claimed"]), O["claim_lag"]))
    tl += tl_row("Order placed", esc(O["placed"]), last=True)

    # The refund promise, in the guarantee page's own words. GUARANTEE's second
    # case is the pro-rated one; taking its title rather than restating it is
    # what keeps this note and the policy from drifting apart, which the
    # handoff calls out as a hard requirement.
    promise = D.GUARANTEE["cases"][1][3]
    return f"""<div class="tko-rail">
        {bst}
        {watch_panel(O, b, _DEMO_GAME)}
        <div class="tko-card">
          <span class="tk-lab">Order details</span>
          <div class="tko-det">{det}</div>
        </div>
        <div class="tko-card">
          <span class="tk-lab">Timeline</span>
          <div class="tko-tl">{tl}</div>
        </div>
        <div class="tko-guar">
          {_ico("shield-check", 18, "tko-guar-i", stroke=True)}
          <span><b>{esc(promise)}</b> <span>— any time this order is open.</span>
          <a href="/guarantee.html">Read the guarantee</a></span>
        </div>
      </div>"""


def _demo_order_view(O):
    """State 2 — the order the emailed link opens.

    The two actions a live order actually gets used for sit in the page header,
    not in a card footer, and neither is filled: the visitor has already paid,
    so there is no primary action left to sell.
    """
    b = next((x for x in D.BOOSTERS if x["handle"] == O["booster"]), None)
    msg = f"""<a class="tko-act is-accent" href="/support.html">{_ico("chat", 14, "ico", stroke=True)}<span>Message <i>{esc(O['booster'])}</i></span></a>"""
    # Deliberately not an <h1> on the order code: both states ship in one
    # document, and the lookup's headline is the page's heading. Two <h1>s where
    # one is display:none is a crawler-visible hierarchy the CRO audit's own
    # rule rejects. When these become the two routes the handoff asks for, the
    # code is the order page's h1.
    return f"""<section class="section tk tk-order" data-demo-view="order" aria-label="Order {esc(O['id'])}" hidden>
  <div class="tk-hatch" aria-hidden="true"></div>
  <div class="tk-glow tk-glow-o" aria-hidden="true"></div>
  <div class="wrap">
    <div class="tko-head">
      <div class="tko-head-l">
        <button class="tko-back" type="button" data-demo-back aria-label="Back to the order lookup">{_ico("arrow-left", 15, "ico", stroke=True)}</button>
        <div class="tko-id">
          <span class="tk-lab">Order</span>
          <div class="tko-id-r">
            <span class="tko-code">{esc(O['id'])}</span>
            <span class="tko-live" data-demo-status><span class="dot-live dot-ok" aria-hidden="true"></span><span data-demo-status-label>In progress</span></span>
            <span class="dm-example">Example</span>
          </div>
        </div>
      </div>
      <div class="tko-acts">
        <button class="tko-act" type="button" data-demo-pause aria-pressed="false">{_ico("pause", 14, "ico", stroke=True)}<span data-demo-pause-label>Pause order</span></button>
        {msg}
      </div>
    </div>

    <div class="tko-grid">
      <div class="tko-col">
        <div class="tko-paused" data-demo-paused hidden role="status">
          {_ico("pause-circle", 17, "tko-paused-i", stroke=True)}
          <span><b>Order paused.</b> The account is free within minutes and the delivery clock
          stops. Resume whenever you're done playing.</span>
        </div>
        {dash_mock(live=True)}
      </div>
      {_demo_rail(O)}
    </div>
  </div>
</section>"""


def page_demo():
    """`/demo.html` — the order dashboard, and the lookup that opens it.

    Was `/track.html`, "Track my order". Every figure on it is D.DEMO_ORDER, a
    placeholder, and there is no order store behind the form, so the page is
    named for what it is. Both the homepage's "Open the demo dashboard" and the
    checkout confirmation land here on `?order=<id>` — one order rendered in
    three places, or the dashboard section stops being evidence of anything.
    """
    O = demo_order()
    # Dashboard band first: this is the demo, so lead with the product screen and
    # put the order lookup under it. The state switch below toggles the three
    # sections by selector, not by document order, so the swap is presentation
    # only — view() still hides lookup + band together and shows the order view.
    body = "%s\n%s\n%s" % (dashboard_section(on_demo=True), _demo_lookup(O),
                           _demo_order_view(O))
    # The state switch. Two things it is careful about: the resolved order is a
    # real history entry (`?order=`), so Back leaves the page the way the
    # visitor expects and the emailed-link premise survives; and the submit
    # label is owned here rather than by i18n's whole-node pass, because it
    # swaps between two strings — see the SKIP list in i18n.js.
    js = """<script>
(function () {
  var DEMO = %s;
  var form = document.querySelector('[data-demo-form]');
  if (!form) return;
  var lookup = document.querySelector('[data-demo-view="lookup"]');
  var band = document.getElementById('dashboard');
  var order = document.querySelector('[data-demo-view="order"]');
  var code = form.querySelector('[data-demo-code]');
  var mail = form.querySelector('[data-demo-mail]');
  var note = form.querySelector('[data-demo-note]');
  var sent = form.querySelector('[data-demo-sent]');
  var addr = form.querySelector('[data-demo-addr]');
  var label = form.querySelector('[data-demo-label]');
  var pause = order.querySelector('[data-demo-pause]');
  var pauseLabel = order.querySelector('[data-demo-pause-label]');
  var paused = order.querySelector('[data-demo-paused]');
  var status = order.querySelector('[data-demo-status]');
  var statusLabel = order.querySelector('[data-demo-status-label]');
  var watch = order.querySelector('[data-watch]');
  var HELP = 'On your confirmation email, under the total.';
  var ERR = "We can't find that order number. Check the confirmation email, or use the address you paid with below.";

  function t(s) { return window.esbT ? window.esbT(s) : s; }
  function valid(v) { return /^[^\\s@]+@[^\\s@]+\\.[a-z]{2,}$/i.test(v); }
  function val(el) { return (el.value || '').trim(); }

  // The button always names what it will do. A static label on a two-route
  // form is what made the original ambiguous.
  function relabel() {
    label.textContent = t(!val(code) && valid(val(mail)) ? 'Email me the link' : 'Find my order');
  }
  function clear() {
    code.classList.remove('is-err');
    code.classList.toggle('is-set', !!val(code));
    note.textContent = t(HELP);
    note.classList.remove('is-err');
    sent.hidden = true;
    relabel();
  }
  function fail() {
    code.classList.add('is-err');
    note.textContent = t(ERR);
    note.classList.add('is-err');
    sent.hidden = true;
    code.focus();
  }

  function view(open, push) {
    lookup.hidden = open; band.hidden = open; order.hidden = !open;
    if (push) {
      var url = location.pathname + (open ? '?order=' + encodeURIComponent(DEMO) : '');
      history.pushState({ demo: open }, '', url);
      window.scrollTo(0, 0);
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var id = val(code).toUpperCase();
    if (id) { if (id === DEMO) view(true, true); else fail(); return; }
    if (valid(val(mail))) {
      addr.textContent = val(mail);
      sent.hidden = false;
      note.textContent = t(HELP);
      note.classList.remove('is-err');
      code.classList.remove('is-err');
      return;
    }
    fail();
  });

  code.addEventListener('input', clear);
  mail.addEventListener('input', clear);

  document.addEventListener('click', function (e) {
    var open = e.target.closest && e.target.closest('[data-demo-open]');
    if (open) { e.preventDefault(); view(true, true); }
  });
  order.querySelector('[data-demo-back]').addEventListener('click', function () { view(false, true); });
  window.addEventListener('popstate', function () {
    view(new URLSearchParams(location.search).get('order') === DEMO, false);
  });

  // The status pill is part of the pause, not decoration beside it: an order
  // that says "In progress" while its own banner says it is paused is telling
  // the visitor two things at once.
  function setPaused(on) {
    pause.setAttribute('aria-pressed', on ? 'true' : 'false');
    pauseLabel.textContent = t(on ? 'Resume order' : 'Pause order');
    statusLabel.textContent = t(on ? 'Paused' : 'In progress');
    status.classList.toggle('is-paused', on);
    paused.hidden = !on;
    setWatch(!on);
  }

  // Watch-live follows the pause, because it has to: a paused order is not
  // being played, so it cannot be being streamed. Leaving the panel on "orvo is
  // sharing their screen" beside the order's own "paused" banner is the same
  // two-things-at-once defect the status pill above fixes. Both states are in
  // the DOM and one is hidden — i18n matches whole text nodes, so a sentence
  // written in here would arrive untranslated.
  function setWatch(live) {
    if (!watch) return;
    var n = watch.querySelectorAll('[data-watch-when]');
    for (var i = 0; i < n.length; i++) {
      n[i].hidden = n[i].getAttribute('data-watch-when') !== (live ? 'live' : 'off');
    }
    watch.classList.toggle('is-off', !live);
  }
  pause.addEventListener('click', function () {
    setPaused(pause.getAttribute('aria-pressed') !== 'true');
  });

  // A language switch re-renders through esbRender; the labels this file owns
  // go with it.
  var prev = window.esbRender;
  window.esbRender = function () {
    if (prev) prev.apply(this, arguments);
    relabel();
    note.textContent = t(note.classList.contains('is-err') ? ERR : HELP);
    setPaused(pause.getAttribute('aria-pressed') === 'true');
  };

  if (new URLSearchParams(location.search).get('order') === DEMO) view(true, false);
  relabel();
})();
</script>
""" % json.dumps(O["id"])
    return layout(DEMO_HREF, "Demo — the order dashboard — %s" % D.BRAND,
                  "See exactly what you get after paying: live rank, LP per game, match history, "
                  "pause and a direct line to your booster. No account, no password.",
                  body, current=DEMO_HREF, extra_js=js)


# ══════════════════════════════════════════════════════════════════════════
#  /orders — the account's order history
# ══════════════════════════════════════════════════════════════════════════
# The "My orders" destination. There is no per-customer order store behind the
# facade session, so — like DEMO_ORDER and the booster histories — the list is
# placeholder data, generated deterministically from the real ladders and the
# real formula so no figure is typed and nothing drifts from what the shop would
# actually sell. The active order is DEMO_ORDER (it opens the one dashboard the
# site really renders); the rest are delivered history. The page states out loud
# that it is a preview until a real orders backend lands.


def _ord_side(g, rank, strong):
    """One end of a climb, drawn with the live feed's mark so it needs no scoped
    CSS of its own. `g` is a game dict (same contract as `_side_mark`)."""
    side = _rank_side(g, rank)
    if side is None:
        return '<span class="ord-rank-plain">%s</span>' % esc(rank), ""
    tier, div, ladder = side
    label = div or (tier if ladder else tier[:2].upper())
    return (tier_mark(g, tier, label, strong=strong, wide=bool(ladder), base="lf-mark"),
            ladder or tier)


def _ord_climb(g, frm, to):
    """`Gold [IV] → Diamond [IV]` — tier then mark per end, the pairing the feed,
    the checkout and the closing band all use (a mark alone only names the
    division numeral, so the tier name leads and the mark trails it)."""
    fm, fn = _ord_side(g, frm, False)
    tm, tn = _ord_side(g, to, True)
    return (f'<span class="ord-climb"><span class="ord-tier">{esc(fn)}</span>{fm}'
            f'<i class="ord-arw" aria-hidden="true">→</i>'
            f'<span class="ord-tier">{esc(tn)}</span>{tm}</span>')


def order_history(n=6):
    """A deterministic list of delivered orders across several games.

    Modelled on `booster_history()`: every row is a real climb the shop could
    sell, priced and timed by `pricing.quote()`, seeded on a constant so a
    rebuild renders the same list. Placeholder data — there is no customer order
    store yet. Cached on first call.
    """
    if getattr(order_history, "_v", None) is not None:
        return order_history._v

    def rot(salt, m):
        h = 2166136261
        for c in "esb.orders#%d" % salt:
            h = (h * 16777619 + ord(c)) & 0xFFFFFFFF
        return h % max(1, m)

    games = [g for g in D.GAMES if len(g["ladder"]) >= 4]
    rows, now, back, oid = [], datetime.now(), 6, 0x9F2C10
    i = 0
    while len(rows) < n and i < n * 4:
        g = games[rot(i * 3 + 1, len(games))]
        L = g["ladder"]
        a = rot(i * 5 + 2, max(1, len(L) - 3))
        b = min(len(L) - 1, a + 1 + rot(i * 7 + 3, 3))
        i += 1
        if b <= a:
            continue
        frm, to = L[a], L[b]
        mode = "Duo" if rot(i * 11 + 4, 3) == 0 else "Solo"
        q = pricing.quote({"game": g["name"], "service": "division", "from": frm,
                           "to": to, "mode": mode, "addons": []})
        if q["invalid"]:
            continue
        d = now - timedelta(days=back)
        rows.append(dict(id="ESB-%06X" % (oid & 0xFFFFFF), game=g, frm=frm, to=to,
                         mode=mode, price=q["total"], days=q["days"],
                         date="%d %s %d" % (d.day, d.strftime("%b"), d.year),
                         ts=d))
        back += q["days"] + 2 + rot(i * 23 + 11, 6)
        oid -= 0x111 + rot(i * 29 + 13, 0x400)
    order_history._v = rows
    return rows


def _ord_active_card(O):
    """The in-progress order — DEMO_ORDER — as a compact card that opens the one
    real dashboard on `?order=`."""
    g = _DEMO_GAME
    climb = _ord_climb(g, O["start_rank"], O["target_rank"]) if g else esc(O["summary"] if O.get("summary") else "")
    at = _ord_side(g, O["at_rank"], True) if g else ("", O.get("at_rank", ""))
    at_html = "<span class=\"ord-tier\">%s</span>%s" % (at[1], at[0]) if g else esc(O.get("at_rank", ""))
    return f"""<article class="ord-active">
      <div class="ord-active-top">
        <span class="ord-status is-live"><span class="ord-dot" aria-hidden="true"></span><span>In progress</span></span>
        <span class="ord-oid">{esc(O['id'])}</span>
      </div>
      <div class="ord-active-body">
        <div class="ord-active-meta">
          <span class="ord-game">{esc(O['game'])}</span>
          <span class="ord-sep" aria-hidden="true">·</span><span>{esc(O['region'])}</span>
          <span class="ord-sep" aria-hidden="true">·</span><span>{esc(O['mode'])}</span>
          <span class="ord-sep" aria-hidden="true">·</span><span>with {esc(O['booster'])}</span>
        </div>
        <div class="ord-active-climb">{climb}<span class="ord-now"><span>now</span>{at_html}</span></div>
        <div class="ord-prog">
          <div class="ord-prog-bar"><i style="width:{O['pct']}%"></i></div>
          <span class="ord-prog-t"><b>{O['pct']}%</b><span>complete</span><i aria-hidden="true">·</i><b>{O['days_left']}</b><span>days left</span></span>
        </div>
      </div>
      <div class="ord-active-foot">
        <span class="ord-price ord-price-lg">{money(O['price'])}</span>
        <a class="btn btn-primary btn-sm" href="{DEMO_HREF}?order={esc(O['id'])}">Open dashboard{_ico("arrow", 15, "ico", stroke=True)}</a>
      </div>
    </article>"""


def _ord_row(o):
    return f"""<div class="ord-row">
      <span class="ord-cell ord-c-id"><span class="ord-oid">{esc(o['id'])}</span></span>
      <span class="ord-cell ord-c-game">{esc(o['game']['short'])}</span>
      <span class="ord-cell ord-c-climb">{_ord_climb(o['game'], o['frm'], o['to'])}</span>
      <span class="ord-cell ord-c-mode">{esc(o['mode'])}</span>
      <span class="ord-cell ord-c-date">{esc(o['date'])}</span>
      <span class="ord-cell ord-c-price">{money(o['price'])}</span>
      <span class="ord-cell ord-c-status"><span class="ord-status is-done">Delivered</span></span>
    </div>"""


def page_orders():
    """`/orders.html` — the signed-in account's OWN orders, read live from the
    orders store via `GET /api/orders` (email-scoped to the signed session).

    No fabricated data: the page ships as an empty shell and `initOrders()` in
    app.js fills it from the API. Three states, all in the DOM and toggled: signed
    out (a log-in prompt), signed in with no orders (an empty state), and real
    orders (the stats + table). The store is only written by the Stripe webhook,
    so a customer sees exactly what they paid for and nothing else."""
    head = "".join('<span>%s</span>' % esc(t) for t in
                   ("Order", "Game", "Climb", "Queue", "Date", "Paid", "Status"))
    body = f"""<section class="section ord" data-orders>
  <div class="wrap ord-wrap">
    <header class="ord-head">
      <span class="ord-eyebrow">Account</span>
      <h1 class="ord-h1">Your orders</h1>
      <p class="ord-sub">Every boost you've ordered — the one in progress, and the ones already delivered.</p>
      <p class="ord-hello" data-ord-hello hidden>{_ico("user", 14, "ico", stroke=True)}<span>Signed in as</span> <b data-ord-name></b></p>
    </header>

    <!-- Signed out: without an identity there are no orders to show. -->
    <div class="ord-guest" data-ord-guest hidden>
      <div class="ord-guest-c">
        <span class="ord-guest-i" aria-hidden="true">{_ico("user", 18, "ico", stroke=True)}</span>
        <span><b>Log in</b> to see your orders here — or track a single order by the link we emailed
        you. Checkout never needs an account.</span>
      </div>
      <div class="ord-guest-a">
        <button type="button" class="btn btn-primary btn-sm" data-hd-auth="signin">Log in</button>
        <a class="btn btn-outline btn-sm" href="{DEMO_HREF}">Track by link</a>
      </div>
    </div>

    <div class="ord-stats" data-ord-stats hidden>
      <div class="ord-stat"><span class="ord-stat-v" data-ord-stat="orders">0</span><span class="ord-stat-l">Orders</span></div>
      <div class="ord-stat"><span class="ord-stat-v" data-ord-stat="inprogress">0</span><span class="ord-stat-l">In progress</span></div>
      <div class="ord-stat"><span class="ord-stat-v" data-ord-stat="delivered">0</span><span class="ord-stat-l">Delivered</span></div>
      <div class="ord-stat"><span class="ord-stat-v" data-ord-stat="spent">—</span><span class="ord-stat-l">Lifetime spent</span></div>
    </div>

    <!-- Signed in, but no orders yet. -->
    <div class="ord-empty" data-ord-empty hidden>
      <span class="ord-empty-i" aria-hidden="true">{_ico("package", 22, "ico", stroke=True)}</span>
      <h2 class="ord-empty-h">No orders yet</h2>
      <p class="ord-empty-p">When you place an order it shows up here — the climb, the price and its
      status, updated as your booster works. Ready to start?</p>
      <div class="ord-empty-a">
        <a class="btn btn-primary btn-sm" href="/games">Browse games</a>
        <a class="btn btn-outline btn-sm" href="{DEMO_HREF}">Track by link</a>
      </div>
    </div>

    <div class="ord-section" data-ord-table-sec hidden>
      <h2 class="ord-h2">All orders</h2>
      <div class="ord-table">
        <div class="ord-thead" aria-hidden="true">{head}</div>
        <div class="ord-tbody" data-ord-tbody></div>
      </div>
    </div>
  </div>
</section>"""
    return layout(ORDERS_HREF, "Your orders — %s" % D.BRAND,
                  "Your order history: the boost in progress and every one already delivered.",
                  body, current=ORDERS_HREF)


# Preferred-hours options — the handoff's five, in its words. The old list read
# "My usual play hours (18:00–00:00)"; parenthesised clock ranges wrap inside a
# 46px field, and nobody was picking between four near-identical sentences.
CO_HOURS = ["Any time", "Mornings", "Afternoons", "Evenings", "Nights"]


def co_steps(active=1):
    """The three-step rail. `active` is 1-based; earlier steps render done.

    Was 9px mono tracked to .16em. These are the only words telling the buyer
    how much is still ahead of them, so they are 11.5px with 26px circles.
    """
    labels = ["Your email", "Order details", "Payment"]
    out = []
    for i, label in enumerate(labels, 1):
        state = "done" if i < active else ("on" if i == active else "off")
        mark = _ico("check", 12, "ico", stroke=True) if state == "done" else str(i)
        current = ' aria-current="step"' if state == "on" else ""
        out.append(f'<li class="co-step" data-step="{i}" data-state="{state}"{current}>'
                   f'<span class="co-step-n">{mark}</span>'
                   f'<span class="co-step-l">{esc(label)}</span></li>')
    return '<ol class="co-steps">%s</ol>' % "".join(out)


def page_checkout():
    """The last screen before payment — the "LoL Checkout" handoff.

    Its premise is that this store has no accounts, so checkout is a short form
    rather than a funnel: everything on the page either collects something the
    order genuinely needs, answers an objection, or shows the price.

    The five changes worth not undoing (handoff README §Overview):
      · the form is the wide LEFT column and the summary is 420px on the right.
        It used to be the other way round, with the summary wider than the form
        — the form is the task, the summary is only reference;
      · the always-on inclusion is a green strip, not a pre-ticked checkbox that
        cannot be unticked (which reads as a bug or a trick), so every remaining
        upsell row is a real choice;
      · the discount code states that it is applied — see promo_field();
      · selected add-ons are receipt rows, so the total can be explained by
        reading down the column;
      · email is marked Required and has a real error state. There was none.

    Plus a distraction-free header: `bare=True` drops the promo bar, the nav and
    the currency switcher, because a page whose only job is finishing should not
    offer exits.

    Everything priced here still comes from the one quote() pass in app.js
    through the documented data-* contract — the handoff is explicit that
    checkout must not re-implement pricing.
    """
    regions = "".join('<option value="%s">%s</option>' % (esc(r), esc(r))
                      for r in D.GAMES[0]["regions"])
    hours = "".join('<option value="%s">%s</option>' % (esc(h), esc(h)) for h in CO_HOURS)
    chips, stripe_badge = pay_marks()
    tp = trustpilot_badge()

    # The inclusions, stated. One strip per zero-cost add-on, name and sentence
    # both out of data.py, so the strip and the picker above can never disagree
    # about what is free or what it is called — the picks add-on became a free
    # inclusion and this is the only place checkout says so. No zero-cost add-on
    # in data.py, no strip. The name is addon_name() with no game, so the strip
    # carries all nine wordings and shows the order's; see that function.
    incl = "".join(
        f'<div class="co-incl">{_ico("seal", 15, "ico", evenodd=True)}'
        f'<span><b>{addon_name(a)}</b> <span>{esc(a["note"])}</span></span></div>'
        # Zero-cost, but NOT the free-but-optional row: that one is the buyer's
        # choice and is still sitting unticked in the upsell block above. A
        # strip claiming it is already on would contradict the empty checkbox
        # 200px away and hand them something they did not ask for.
        for a in D.ADDONS if a["pct"] == 0 and not D.addon_is_free_opt(a))

    # The account order's equivalent: what the handover actually includes. Same
    # strip, same green seal, different facts — read off D.ACCOUNT_DELIVERY so
    # the summary cannot describe a product /accounts.html does not sell.
    acct_incl = "".join(
        f'<div class="co-incl">{_ico("seal", 15, "ico", evenodd=True)}'
        f'<span><b>{esc(title)}</b> <span>{esc(body)}</span></span></div>'
        for _icon, _stroke, title, body in D.ACCOUNT_DELIVERY)

    body = f"""<section class="co">
  <div class="co-fx co-glow" aria-hidden="true"></div>
  <div class="co-fx co-hatch" aria-hidden="true"></div>
  <div class="wrap co-wrap">
    {co_steps(1)}

    <div class="co-grid">
      <div class="co-col">
        <h1 class="co-h1">Checkout</h1>
        <p class="co-lede">No account needed. We create the order under your email and send a
        one-click link to follow it. You can set a password afterwards if you want one.</p>

        <form class="co-card co-form" data-checkout novalidate>
          <div class="co-lab-row">
            <label class="co-lab" for="k-email">Email</label>
            <span class="co-req">Required</span>
          </div>
          <!-- `data-prefill-email` is the hook app.js fills when the site already
               knows this visitor's address — today that means they gave it to the
               mystery-discount modal on a game page, so arriving here they are not
               asked for it twice. It only ever fills an EMPTY field. -->
          <input class="co-input" id="k-email" type="email" required
                 inputmode="email" autocomplete="email" spellcheck="false"
                 data-prefill-email
                 placeholder="you@example.com" aria-describedby="k-email-note">
          <p class="co-note" id="k-email-note" data-email-note><span
          data-hide-service="account">Used for your order link, and to
          send you your cart if you don't finish. No marketing unless you tick the box at
          the end.</span><span data-when-service="account" hidden>This is where the login,
          the password and the recovery mailbox are sent. Check it is one you can open —
          no marketing unless you tick the box at the end.</span></p>

          <div class="co-two" data-hide-service="account">
            <div class="co-fieldset">
              <label class="co-lab" for="k-region">Server</label>
              <div class="co-field">
                {_ico("globe", 15, "ico")}
                <select class="co-select" id="k-region" data-sel="region" autocomplete="off">{regions}</select>
                {_CARET}
              </div>
            </div>
            <div class="co-fieldset">
              <label class="co-lab" for="k-hours">Preferred hours</label>
              <div class="co-field">
                {_ico("clock", 15, "ico", stroke=True)}
                <select class="co-select" id="k-hours" autocomplete="off">{hours}</select>
                {_CARET}
              </div>
            </div>
          </div>

          <div class="co-lab-row co-lab-row-sp">
            <label class="co-lab" for="k-notes"><span data-hide-service="account">Anything the
            booster should know</span><span data-when-service="account" hidden>Anything we
            should know</span></label>
            <span class="co-opt-lab">Optional</span>
          </div>
          <textarea class="co-input co-textarea" id="k-notes"
                    placeholder="Champion pool, roles, don't touch ranked flex…"></textarea>

          <div class="co-div"></div>

          <div class="co-pay">
            <div class="co-pay-l">
              <span class="co-lab">Pay with</span>
              {chips}
            </div>
            {stripe_badge}
          </div>
          <p class="co-note co-note-w">Card, Apple Pay and Google Pay are all on the next screen —
          details are entered on Stripe's secure checkout, so we never see or store them.
          Statements read as a neutral merchant name.</p>

          {f'<div class="co-div"></div>{tp}' if tp else ''}

          <label class="co-toggle">
            <input type="checkbox" id="k-optin">
            <span class="co-toggle-t"><span data-hide-service="account">Email me when my order is
            claimed and when it's done. Nothing else.</span><span data-when-service="account"
            hidden>Email me when the account is on its way. Nothing else.</span></span>
          </label>

          <p class="co-err" data-pay-error role="alert" hidden></p>

          <button class="co-cta" type="submit">
            {_ico("lock", 16, "ico", stroke=True)}<span data-btn-label>Place the order</span>
            {_ico("arrow", 16, "ico", stroke=True)}
          </button>

          <p class="co-refund" data-hide-service="account">{_ico("shield", 15, "ico")}<span>Refunded in full until a booster
          claims it</span><span aria-hidden="true">·</span><a href="/guarantee.html">Read the
          guarantee</a></p>
          <!-- The account's own promise. "Until a booster claims it" describes
               nothing here — no one claims an account — and a refund line that
               does not apply is worse than none. -->
          <p class="co-refund" data-when-service="account" hidden>{_ico("shield", 15, "ico")}<span>Replaced or
          refunded for {D.ACCOUNT_WARRANTY_MONTHS} months</span><span aria-hidden="true">·</span><a href="{ACCOUNTS_HREF}#faq-warranty">Read the
          warranty</a></p>

          <!-- The live total detaches into the games-page sticky bar: the same
               `.mobile-bar` + `.mb-*` component the nine game pages carry, so the
               two surfaces ship one bar design (hairline · big price · save pill ·
               tall CTA · assurance row). It is dual-classed `.co-bar` only so
               initStickyBar() shadows the form's own submit (a game page shadows
               `.ob-cta`) and so `.co`'s CSS reveals it at this page's 900px
               breakpoint. Every figure is a data hook render() already fills — the
               struck price, the save pill and the total can't quote three numbers.
               The CTA stays a real submit so it drives the pay form; `data-btn-label`
               keeps it in step with the main button's "Contacting payment…" swap. -->
          <div class="co-bar mobile-bar" role="region" aria-label="Live total">
            <div class="mb-hair" aria-hidden="true"></div>
            <div class="mb-top">
              <div class="mb-left">
                <div class="mb-money" aria-live="polite">
                  <span class="mb-price" data-sum="total">—</span>
                  <span class="mobile-was" data-when-discount data-sum="was" hidden></span>
                  <span class="mb-save" data-when-discount hidden><span>Save</span> <b data-out="saveAmt"></b></span>
                </div>
                <span class="mb-meta">
                  {_ico("clock-countdown", 12, "mb-ico", stroke=True)}<span class="mb-eta" data-sum="eta">—</span>
                  <span class="mb-dot" aria-hidden="true">·</span>
                  <span class="mb-cfg" data-sum="summary">—</span>
                </span>
              </div>
              <button class="btn btn-primary mb-cta" type="submit"><span data-btn-label>Place the order</span>{_ico("arrow", 15, "ico", stroke=True)}</button>
            </div>
            <div class="mb-assure">
              <span class="mb-as">{_ico("lock", 11, "mb-ico", stroke=True)}<span>Secure checkout</span></span>
              <span class="mb-as-div" aria-hidden="true"></span>
              <span class="mb-as">{_ico("shield-check", 11, "mb-ico", stroke=True)}<span>Money-back guarantee</span></span>
            </div>
          </div>
        </form>

        <div class="co-card co-done" data-confirm hidden>
          <span class="card-kicker">Order placed</span>
          <span class="card-title" data-order-id>ESB-000000</span>
          <p class="card-body">This is a local preview, so no payment was taken and no email was
          sent. In production this is the point where the order goes on the booster board, the
          confirmation email leaves, and <code>purchase</code> fires to GA4 and to the Meta CAPI
          gateway.</p>
          <a class="co-back co-back-inline" href="{DEMO_HREF}?order={esc(demo_order()['id'])}">See what the dashboard looks like</a>
        </div>
      </div>

      <aside class="co-aside">
        <div class="co-card co-sum">
          <div class="co-sum-head">
            <h2 class="co-sum-title">Order summary</h2>
            <span class="co-locked">{_ico("lock", 11, "ico", stroke=True)}<span>Locked at checkout</span></span>
          </div>

          <div class="co-lines">
            <div class="co-line">
              <span class="co-lab">Game</span><span class="co-val" data-sum="game">—</span>
            </div>
            <div class="co-line">
              <!-- Both labels ship in the DOM with one hidden: i18n.js matches
                   whole text nodes, so a word written in by JS arrives
                   untranslated. Same rule as the mode-conditional add-ons. -->
              <span class="co-lab"><span data-hide-service="account">Climb</span><span
                    data-when-service="account" hidden>Account</span></span>
              <span class="co-val co-climb">
                <span class="co-marks" data-when-service="division" hidden>
                  <span class="co-climb-r" data-tiername="from">—</span>
                  <span class="ob-mark" data-mark="from"></span>
                  {_ico("arrow", 12, "ico co-mark-arrow", stroke=True)}
                  <span class="co-climb-r is-to" data-tiername="to">—</span>
                  <span class="ob-mark" data-mark="to"></span>
                </span>
                <span class="co-climb-t" data-when-service="division" hidden><i aria-hidden="true">·</i><span data-out="mode">—</span></span>
                <span class="co-climb-t" data-when-service="units" data-sum="summary" hidden>—</span>
              </span>
            </div>
            <!-- An account order's summary already names its shard ("Gold ranked ·
                 Europe West"), so a second row repeating it says the same fact
                 twice in four lines. -->
            <div class="co-line" data-hide-service="account">
              <span class="co-lab">Server</span><span class="co-val" data-sum="region">—</span>
            </div>
            <!-- Only when the buyer arrived from a roster Hire or a profile
                 CTA. It carries no charge: pricing.py has no named-booster fee,
                 and a summary line that implied one would be a price the server
                 would not honour. -->
            <div class="co-line" data-when-booster hidden>
              <span class="co-lab">Booster</span><span class="co-val" data-sum="booster">—</span>
            </div>
            <div class="co-line">
              <span class="co-lab"><span data-hide-service="account">Boost</span><span
                    data-when-service="account" hidden>Price</span></span>
              <span class="co-val" data-sum="base">—</span>
            </div>
            <div data-addon-lines></div>
            <div class="co-line co-line-off" data-when-discount hidden>
              <span class="co-lab-off">{_ico("tag", 14, "ico")}<span data-sum="discountLabel">—</span></span>
              <span class="co-val co-val-off" data-sum="discount">—</span>
            </div>
          </div>

          <!-- Add-ons are a boost's, not an account's: pricing.quote() returns
               before the add-on block on `service == "account"`, so every row
               here would offer an option the server refuses to charge for. The
               inclusions strip goes with it — it states what a boost includes. -->
          <div data-when-service="account" hidden>{acct_incl}</div>
          <div data-hide-service="account">
            {incl}

            <div class="co-up">
              <span class="co-lab">Last chance to add</span>
              {addons_block(money=True, paid_only=True)}
            </div>
          </div>

          <div class="co-div co-div-push"></div>

          {promo_field()}

          <div class="co-totals">
            <div class="co-tot-l">
              <span class="co-lab">Total, tax included</span>
              <span class="price-pair">
                <span class="co-was" data-when-discount data-sum="was" hidden></span>
                <span class="co-total" data-sum="total">—</span>
              </span>
            </div>
            <div class="co-tot-r">
              <span class="co-lab">Delivered in</span>
              <span class="co-eta" data-sum="eta">—</span>
            </div>
          </div>

          <div class="co-chips" data-hide-service="account">
            <span class="co-tchip">{_ico("shield", 12, "ico")}<span>Money-back until claimed</span></span>
            <span class="co-tchip">{_ico("globe", 12, "ico")}<span>Regional VPN</span></span>
            <span class="co-tchip">{_ico("eye-off", 12, "ico", stroke=True)}<span>Offline appearance</span></span>
          </div>
          <!-- An account's three, stated in the same shell. "Regional VPN" and
               "offline appearance" describe a booster playing, which is nobody
               here; the warranty window is read off data.py so it cannot drift
               from the page that sold it. -->
          <div class="co-chips" data-when-service="account" hidden>
            <span class="co-tchip">{_ico("lock-key", 12, "ico", stroke=True)}<span>Full email access</span></span>
            <span class="co-tchip">{_ico("shield-check", 12, "ico", stroke=True)}<span>{D.ACCOUNT_WARRANTY_MONTHS}-month replacement</span></span>
            <span class="co-tchip">{_ico("clock", 12, "ico", stroke=True)}<span>{esc(pricing.ACCOUNT_ETA)}</span></span>
          </div>
        </div>
      </aside>
    </div>
  </div>
</section>
"""
    js = """<script>
(function () {
  var form = document.querySelector('[data-checkout]');
  var btns = form.querySelectorAll('button[type=submit]');
  var errBox = form.querySelector('[data-pay-error]');
  var mail = form.querySelector('#k-email');
  var note = form.querySelector('[data-email-note]');
  var NOTE = note.textContent;
  function T(s) { return window.esbT ? window.esbT(s) : s; }
  function each(sel, fn) {
    Array.prototype.forEach.call(document.querySelectorAll(sel), fn);
  }
  window.esbTrack('add_payment_info', window.esbItemParams());

  /* ── abandoned-cart capture ──────────────────────────────────────────
     Save the address as soon as it is a real one, so a checkout that is
     never finished can be recovered. Fires on blur and on a debounced
     pause, not on every keystroke: the server keeps ONE open cart per
     address (carts.find_pending), so a re-post updates the row rather than
     minting a second token, but there is no reason to spend the requests.
     Entirely best-effort — a failed capture must never surface to the buyer
     or block the pay button. The note under the field says this happens. */
  /* Arriving from a recovery mail: /checkout?cart=BACK-… The token alone is in
     the link; the DISCOUNT is resolved server-side and handed back here, purely
     so this page's live quote matches what the server will charge. A spent,
     unknown or expired token answers {valid:false} and the page simply prices
     at the normal sale — never an error, because the buyer did nothing wrong. */
  var recTok = (location.search.match(/[?&]cart=([A-Za-z0-9-]+)/) || [])[1] || '';
  if (recTok) {
    fetch('/api/cart?token=' + encodeURIComponent(recTok))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.valid) return;
        window.ESB_RECOVERY = { token: j.token, pct: j.pct };
        if (mail && !mail.value && j.email) mail.value = j.email;
        if (window.esbRender) window.esbRender();     // repaint at the new price
      }).catch(function () {});
  }

  /* Arriving from the mystery follow-up mail: /checkout?bingo=BINGO-…
     Same contract as ?cart= above — the link carries only the token and the
     discount is resolved server-side — with one addition that this flow needs
     and the cart flow does not. A cart is captured ON this page, so a returning
     buyer's configuration is already in localStorage; a mystery card is opened
     on a GAME page, and `esb.order.v1` is only written when someone presses
     Continue. Somebody who never did that — or who opens the mail on their
     phone — would land here with no order behind the price the mail quoted. So
     the row's stored configuration comes back with the token and is hydrated
     through app.js's own validator before the page renders. */
  var mydTok = (location.search.match(/[?&]bingo=([A-Za-z0-9-]+)/) || [])[1] || '';
  if (mydTok) {
    fetch('/api/bingo?token=' + encodeURIComponent(mydTok))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.valid) return;      // spent, expired or unknown: normal sale
        window.ESB_BINGO = { token: j.token, pct: j.pct,
                             label: j.label || 'Mystery discount' };
        // Keep it past this page load, so a buyer who steps back into the
        // configurator to change something does not lose the discount.
        // Also fills the email field — with the address the mail actually went
        // to, which outranks anything this browser prefilled earlier.
        if (window.esbBingoAdopt) window.esbBingoAdopt(j);
        else if (mail && !mail.value && j.email) mail.value = j.email;
        // Hydrate LAST: it renders, so the offer above is already in the price.
        if (j.order && window.esbHydrate) window.esbHydrate(j.order);
        else if (window.esbRender) window.esbRender();
      }).catch(function () {});
  }

  var CART_KEY = 'esb.cart.v1';
  var lastSent = '';
  function captureCart() {
    if (!mail || !mail.value) return;
    var email = mail.value.trim();
    if (!/^[^@\\s]+@[^@\\s.]+\\.[^@\\s]{2,}$/.test(email)) return;
    var st = window.esbState ? window.esbState() : {};
    var sig = email + '|' + JSON.stringify(st);
    if (sig === lastSent) return;              // nothing changed since last post
    lastSent = sig;
    var body = {
      email: email, game: st.game, service: st.service, from: st.from,
      to: st.to, mode: st.mode, region: st.region, addons: st.addons || [],
      wins: st.wins, placements: st.placements, unranked: !!st.unranked,
      booster: st.booster || '', bundle: st.bundle || '',
      tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ''),
      lang: (navigator.language || '')
    };
    try {
      fetch('/api/cart', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), keepalive: true
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (j && j.token) { try { localStorage.setItem(CART_KEY, j.token); } catch (e) {} }
        }).catch(function () {});
    } catch (e) { /* never surfaces to the buyer */ }
  }
  if (mail) {
    var capT;
    mail.addEventListener('blur', captureCart);
    mail.addEventListener('input', function () {
      clearTimeout(capT); capT = setTimeout(captureCart, 1200);
    });
    // The buyer leaving the tab is the whole point — take one last snapshot.
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') captureCart();
    });
  }

  if (/[?&]canceled=1/.test(location.search)) showError(
    'Payment canceled — nothing was charged. Your order is still here when you\\'re ready.',
    'canceled');

  function showError(msg, code) {
    errBox.textContent = msg;
    errBox.hidden = false;
    // One place for every way payment can fail, so cancellations, API refusals
    // and network drops all reach analytics without extra plumbing.
    if (window.esbEmit) window.esbEmit('checkout_error', {
      meta: { code: code || 'error', message: String(msg).slice(0, 160) }
    });
  }
  function busy(on) {
    // Rewrite only the label, never a button's innerHTML — the amount lives in
    // a [data-sum="total"] span that render() owns. Both the card CTA and the
    // sticky mobile one submit, so both move together.
    Array.prototype.forEach.call(btns, function (b) {
      b.disabled = on;
      b.classList.toggle('is-busy', !!on);
      var label = b.querySelector('[data-btn-label]');
      if (label) label.textContent = on ? T('Contacting payment…') : T('Place the order');
    });
  }

  /* Validated on submit, not on keystroke: telling someone their address is
     wrong while they are still typing it is why the old page was better off
     with no error state at all. The green valid border is live (CSS :valid on
     the field); the ember one waits for a real attempt and clears on the next
     change, which is the handoff's rule. */
  var EMAIL = /^[^\\s@]+@[^\\s@]+\\.[a-z]{2,}$/i;
  mail.addEventListener('input', function () {
    if (!form.hasAttribute('data-email-err')) return;
    form.removeAttribute('data-email-err');
    note.textContent = NOTE;
  });

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
    each('[data-step]', function (el) { el.setAttribute('data-state', 'done'); });
    form.hidden = true;
    document.querySelector('[data-confirm]').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    errBox.hidden = true;

    if (!EMAIL.test((mail.value || '').trim())) {
      form.setAttribute('data-email-err', '');
      note.textContent = T('Enter an email we can send the order link to.');
      mail.focus();
      return;
    }

    var s = window.esbState();
    var payload = {
      game: s.game, service: s.service, from: s.from, to: s.to, mode: s.mode,
      wins: s.wins, placements: s.placements, region: s.region, addons: s.addons,
      // Price-affecting state the server re-quote reads. Without these the server
      // recomputes a DIFFERENT price than the one shown: a dropped `bundle` falls
      // back to the sitewide sale (overcharging every bundle), `unranked` reverts
      // placements off the ladder floor, and coaching ignores the chosen pack.
      bundle: (s.bundle === null || s.bundle === undefined) ? null : s.bundle,
      unranked: !!s.unranked,
      coach: s.coach, pack: s.pack,
      // The account listing. On `service: "account"` it IS the price — drop it
      // and the server re-quote refuses the order outright rather than
      // mis-charging it, which is the safe half of this failure, but the buyer
      // sees "no longer available" on a listing that is in stock. The server
      // still re-resolves it against the catalogue and its stock flag; this is
      // only what the page asked to buy.
      account: s.account || '',
      // The exact total shown on this page (whole USD, before currency display).
      // The server recomputes the price and refuses the charge if it disagrees,
      // so Stripe always shows what the customer saw here. Not trusted as the
      // price — only compared — so a tampered value cannot lower the charge.
      client_total: (window.esbQuote ? (window.esbQuote(s) || {}).total : null),
      promo: s.promo || '',
      // The recovery token from an abandoned-cart mail, if this order came back
      // from one. Only the token travels — the discount PERCENTAGE is resolved
      // server-side against the carts store, never sent from here, or a crafted
      // body would buy any climb for nothing.
      cart: (window.ESB_RECOVERY && window.ESB_RECOVERY.token) || '',
      // The mystery-discount token, same contract: only the token travels and
      // the server resolves the percentage against its own store. A crafted
      // body carrying a percentage buys nothing — process_checkout() strips it.
      bingo: (window.ESB_BINGO && window.ESB_BINGO.token) || '',
      booster: s.booster || '',
      // Charge in the currency the customer is viewing prices in. The amount is
      // still recomputed server-side; only the currency choice rides along.
      currency: (window.ESB_LOCALE && window.ESB_LOCALE.currency) || 'USD',
      email: mail.value.trim(),
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
      showError(res.body.error || 'Payment could not be started. Please try again.',
                'api_' + res.status);
    }).catch(function () {
      busy(false);
      showError('Network error reaching payment. Please try again.', 'network');
    });
  });
})();
</script>
"""
    return layout("/checkout.html", "Checkout — %s" % D.BRAND,
                  "Guest checkout: email, then payment. No account required, refunded in full until "
                  "a booster claims the order.", body, extra_js=js, bare=True)


def page_checkout_success():
    # Same rail as checkout, all three done — the screen one click later should
    # not be wearing the previous design's progress indicator.
    body = """<section class="wrap section">
  <div class="stack" style="gap:26px;max-width:640px;margin-inline:auto">
    """ + co_steps(4) + """

    <div class="card" style="gap:14px">
      <span class="card-kicker" data-state-kicker>Confirming payment…</span>
      <h1 class="h-sec" data-state-title>One moment</h1>
      <p class="card-body" data-state-body>We're confirming your payment with Stripe.</p>
      <div class="stack" style="gap:8px" data-receipt hidden>
        <div class="sum-line"><span class="text-muted">Order</span><span data-r="order">—</span></div>
        <div class="sum-line"><span class="text-muted">Paid</span><span data-r="amount">—</span></div>
        <div class="sum-line"><span class="text-muted">Service</span><span data-r="detail">—</span></div>
        <div class="sum-line"><span class="text-muted">Delivered in</span><span data-r="eta">—</span></div>
      </div>
      <a class="btn btn-primary btn-sm" href="{demo}" style="align-self:flex-start">See what the dashboard looks like</a>
    </div>
  </div>
</section>
""".replace("{demo}", DEMO_HREF + "?order=" + demo_order()["id"])
    js = """<script>
(function () {
  var GADS_PURCHASE = '__GADS_PURCHASE_SEND_TO__';
  var q = new URLSearchParams(location.search);
  var sid = q.get('session_id');
  var kicker = document.querySelector('[data-state-kicker]');
  var title = document.querySelector('[data-state-title]');
  var bodyEl = document.querySelector('[data-state-body]');
  var receipt = document.querySelector('[data-receipt]');
  function set(k, t, b) { kicker.textContent = k; title.textContent = t; bodyEl.textContent = b; }
  // Format in whatever currency Stripe actually charged (returned by /api/session),
  // so the receipt matches the button — not always a dollar sign.
  function fmtMoney(amount, cur) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency', currency: (cur || 'usd').toUpperCase()
      }).format(amount);
    } catch (e) {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
    }
  }

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
        (typeof d.amount_total === 'number') ? fmtMoney(d.amount_total / 100, d.currency) : '—';
      document.querySelector('[data-r="detail"]').textContent = d.detail || '—';
      document.querySelector('[data-r="eta"]').textContent = d.eta || '—';
      receipt.hidden = false;
      // purchase — the real conversion, fired only on a confirmed-paid session
      try {
        var p = window.esbItemParams();
        p.transaction_id = d.order_id;
        if (typeof d.amount_total === 'number') p.value = d.amount_total / 100;
        if (d.currency) p.currency = String(d.currency).toUpperCase();
        window.esbTrack('purchase', p);
        // Google Ads Purchase conversion — real charged amount, not the
        // snippet's placeholder 1.0 EUR. No-op unless the tag is configured.
        if (GADS_PURCHASE && window.gtag) {
          window.gtag('event', 'conversion', {
            send_to: GADS_PURCHASE,
            value: (typeof d.amount_total === 'number') ? d.amount_total / 100 : undefined,
            currency: d.currency ? String(d.currency).toUpperCase() : undefined,
            transaction_id: d.order_id || ''
          });
        }
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
""".replace("__GADS_PURCHASE_SEND_TO__", gads_purchase_send_to())
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
    <form class="card" data-apply novalidate>
      <div class="field">
        <label for="b-handle">In-game name</label>
        <input class="input" id="b-handle" required placeholder="Name #TAG" data-ap-handle
          autocomplete="off">
      </div>
      <div class="two-up">
        <div class="field">
          <label for="b-game">Game</label>
          <select class="input" id="b-game" data-ap-game>{opts}</select>
        </div>
        <div class="field">
          <label for="b-rank">Peak rank</label>
          <input class="input" id="b-rank" required placeholder="Challenger 1042 LP" data-ap-rank
            autocomplete="off">
        </div>
      </div>
      <div class="field">
        <label for="b-contact">Discord</label>
        <input class="input" id="b-contact" required placeholder="username" data-ap-contact
          autocomplete="off">
      </div>
      <div class="field">
        <label for="b-op">Anything else</label>
        <textarea class="input" id="b-op" placeholder="Hours you can play, roles, other accounts…" data-ap-op></textarea>
      </div>
      <!-- Honeypot. /api/apply is a public endpoint pointing at our own inbox, so
           a bot that fills every field is answered as a success and dropped. -->
      <div class="sp-hp" aria-hidden="true">
        <label for="b-company">Company</label>
        <input id="b-company" type="text" name="company" tabindex="-1" autocomplete="off" data-ap-hp>
      </div>
      <button class="btn btn-primary btn-block" type="submit" data-ap-send>
        <span data-ap-send-idle>Apply</span><span data-ap-send-busy hidden>Sending…</span></button>
      <p class="fine" data-apply-note>We reply on Discord. We never share your details or pass your account to anyone.</p>
      <!-- Four outcomes, all shipped in the DOM and toggled (never written): a
           client-side validation miss, and the server's three (sent / no mailbox
           on this deploy / send failed). Mirrors the support form. -->
      <p class="fine ap-result" data-ap-error hidden><b>Almost — one more thing.</b> Add your in-game name, peak rank, and a Discord we can reach you on.</p>
      <p class="fine ap-result" data-ap-sent hidden><b>Application received.</b> We'll message you on Discord — keep an eye out.</p>
      <p class="fine ap-result" data-ap-preview hidden><b>Noted — this is a preview.</b> Nothing was emailed: this build has no mailbox configured. Send your application to <b>{SUPPORT_EMAIL}</b> and it reaches the same people.</p>
      <p class="fine ap-result" data-ap-failed hidden><b>That didn't send.</b> Rather than lose it, email <b>{SUPPORT_EMAIL}</b> with your rank and Discord.</p>
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
// The become-a-booster application. POST /api/apply composes the application
// server-side and mails it to the support inbox (see apply.py). The client
// validates first so an obvious miss never costs a round trip; the server
// validates again because a browser check is not a check. Three server
// outcomes, three confirmations: sent (200), "no mailbox on this deploy"
// (503 — the static preview and any deploy without SMTP), and "it didn't go"
// (429/502/anything else), which names the address instead of swallowing it.
(function () {
  var form = document.querySelector('[data-apply]');
  if (!form) return;
  var handle = form.querySelector('[data-ap-handle]');
  var game = form.querySelector('[data-ap-game]');
  var rank = form.querySelector('[data-ap-rank]');
  var contact = form.querySelector('[data-ap-contact]');
  var op = form.querySelector('[data-ap-op]');
  var hp = form.querySelector('[data-ap-hp]');
  var send = form.querySelector('[data-ap-send]');
  var idle = form.querySelector('[data-ap-send-idle]');
  var busyT = form.querySelector('[data-ap-send-busy]');
  var note = form.querySelector('[data-apply-note]');
  var rErr = form.querySelector('[data-ap-error]');
  var rSent = form.querySelector('[data-ap-sent]');
  var rPrev = form.querySelector('[data-ap-preview]');
  var rFail = form.querySelector('[data-ap-failed]');
  var busy = false;

  // One slot, five states. All ship in the DOM and are toggled here, never
  // written — i18n matches whole text nodes, so a sentence assembled in JS
  // would arrive untranslated. Showing any result hides the idle helper.
  function results(which) {
    [rErr, rSent, rPrev, rFail].forEach(function (n) { if (n) n.hidden = n !== which; });
    if (note) note.hidden = !!which;
  }
  function setBusy(on) {
    busy = on;
    if (send) send.disabled = on;
    if (idle) idle.hidden = on;
    if (busyT) busyT.hidden = !on;
  }
  [handle, rank, contact].forEach(function (el) {
    if (el) el.addEventListener('input', function () { if (rErr && !rErr.hidden) results(null); });
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    var h = ((handle && handle.value) || '').trim();
    var rk = ((rank && rank.value) || '').trim();
    var c = ((contact && contact.value) || '').trim();
    if (!h || !rk || c.length < 2) {
      results(rErr);
      (!h ? handle : !rk ? rank : contact).focus();
      return;
    }
    results(null);
    setBusy(true);
    var payload = {
      handle: h, rank: rk, contact: c,
      game: game ? game.selectedIndex : 0,
      op: ((op && op.value) || '').trim(),
      hp: hp ? hp.value : '',
      tz: (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
                         catch (err) { return ''; } })(),
      lang: (window.ESB_LOCALE && window.ESB_LOCALE.lang) || 'en'
    };
    fetch('/api/apply', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
              .then(function (j) { return { status: r.status, data: j }; });
    }).then(function (res) {
      setBusy(false);
      if (res.status === 200 && res.data.sent) {
        results(rSent);
        form.reset();
        if (window.esbTrack) window.esbTrack('generate_lead', { method: 'booster_application' });
        return;
      }
      if (res.status === 503) {
        results(rPrev);
        if (window.esbTrack) window.esbTrack('generate_lead', { method: 'booster_application_preview' });
        return;
      }
      results(rFail);
    }).catch(function () { setBusy(false); results(rFail); });
  });
})();
</script>
"""
    return layout("/become-a-booster.html", "Become a booster — %s" % D.BRAND,
                  "70–75% of the order value, weekly payouts, your own shifts. Live trial before "
                  "onboarding.", body, extra_js=js)


# One description per legal page. Kept beside LEGAL rather than derived from the
# title, because the useful sentence is the commitment the page makes, not its
# name — and these are the pages a buyer reads before deciding to trust us.
LEGAL_META = {
    "terms": "What you're buying, what we do with your account, and the quote "
             "we're held to. The price fixed at checkout never moves.",
    "privacy": "What we collect, what we don't, and how to have it deleted. No "
               "name, address or phone number — and credentials go when the order does.",
    "refunds": "Money-back until a booster is assigned, an automatic refund if "
               "nobody claims your order in 24 hours, and pro-rata after that.",
}

LEGAL = {
    "terms": ("Terms of service", [
        # The trading entity and where to serve it, named in the clause a reader
        # looks in for exactly that. Both come from D.COMPANY, so this sentence
        # and the identity block at the foot of the page cannot give two
        # addresses; the company number joins it on its own once it is set.
        ("Who we are", "%s sells rank-boosting and coaching services for the games listed "
         "on this site, from %s. Placing an order means you accept these terms."
         % (D.COMPANY["name"], D.company_address())),
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
        # UK GDPR art.13 wants the controller identified by name, postal address
        # and a contact route before anything else on the page — so this is the
        # first section, not a footnote. Same two sources as the terms clause
        # above and the identity block at the foot: D.COMPANY and FOOT_EMAIL.
        ("Who's responsible for your data", "%s, of %s, is the data controller for everything "
         "described below. Write to %s about any of it — access, correction or deletion — and "
         "the reply comes from a person, not a form."
         % (D.COMPANY["name"], D.company_address(), FOOT_EMAIL)),
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


# The entity block that closes every legal page. It is one function and three
# callers for the same reason FOOT_EMAIL is one literal: terms, privacy and
# refunds all have to name the same company at the same address, and three
# hand-written copies is how one of them comes to be a year out of date.
#
# The registration line renders only once D.company_registration() has something
# to say — see the ⚠ on D.COMPANY. An address is a fact about where we are; a
# company number is a claim about a register somebody can check, so the second
# one is gated and the first is not.
#
# i18n: the address lines are data and stay as written (same rule as game names
# and handles), so each label around them is its own whole text node — a street
# interpolated into a sentence would un-translate the sentence.
def legal_contact():
    reg = D.company_registration()
    lines = "".join('<span style="display:block">%s</span>' % esc(l)
                    for l in D.company_lines())
    reg_html = ('<p class="t-13" style="margin:0;color:var(--text-5)">%s</p>' % esc(reg)) if reg else ""
    return f"""<div class="stack" style="gap:10px;padding-top:4px;border-top:1px solid var(--hairline)">
      <h2 style="font-size:20px">Who to write to</h2>
      <p class="t-14" style="margin:0;color:var(--text-3);max-width:74ch;line-height:1.75">
        <b style="color:var(--text-2);font-weight:600">{esc(D.COMPANY["name"])}</b>
        {lines}
      </p>
      {reg_html}
      <p class="t-13" style="margin:0;color:var(--text-5)"><span>Email</span>
      <a href="mailto:{FOOT_EMAIL}">{FOOT_EMAIL}</a><i aria-hidden="true"> · </i><a
      href="/support.html">Open a support ticket</a></p>
    </div>"""


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
    {legal_contact()}
    <p class="t-13" style="margin:0;color:var(--text-5)">Questions about any of this go to
    <a href="/support.html">support</a>. Plain answers, same day.</p>
  </div>
</section>

{cta_band()}"""
    # "Privacy for eSports Boost." is 26 characters and tells a searcher
    # nothing, so Google writes its own snippet from the page anyway. These say
    # what the policy actually commits to — the refund window and the account
    # rules are what people search these pages for.
    desc = LEGAL_META.get(slug) or ("%s for %s. Read the full policy, last "
                                    "updated %s." % (title, D.BRAND, D.LEGAL_UPDATED))
    return layout("/legal/%s.html" % slug, "%s — %s" % (title, D.BRAND), desc, body)


def page_404():
    body = """<section class="wrap section">
  <div class="stack" style="gap:22px;max-width:60ch">
    <span class="kicker">Error 404</span>
    <h1 class="h-md">That page<br>isn't on<br>the ladder.</h1>
    <p class="lede">The link is dead or the page moved. The calculator is two clicks away either
    way.</p>
    <div class="btn-row">
      <a class="btn btn-primary" href="/games">Pick a game</a>
      <a class="btn btn-secondary" href="/">Back to the homepage</a>
    </div>
  </div>
</section>"""
    return layout("/404.html", "Page not found — %s" % D.BRAND,
                  "That page doesn't exist. Pick a game to start an order, check "
                  "an existing one, or ask support — every route from here is live.",
                  body)


# ══════════════════════════════════════════════════════════════════════════
#  /ops — the analytics console (deliberately NOT part of the shop)
# ══════════════════════════════════════════════════════════════════════════
OPS_TABS = [
    ("liveview", "Live view"),
    ("overview", "Overview"), ("funnel", "Funnel"), ("configurator", "Configurator"),
    ("journey", "Journey"), ("sessions", "Sessions"), ("orders", "Orders"),
    ("stock", "Stock"),
    ("carts", "Carts"),
    ("accounts", "Accounts"),
    ("guides", "Guides mails"),
    ("mystery", "Mystery"),
    ("maildiscounts", "Mail discounts"),
    ("outbox", "Outbox"),
    ("boosters", "Boosters"),
    ("acquisition", "Acquisition"), ("friction", "Friction"), ("abandoned", "Abandoned"),
    ("live", "Stream"),
]


def page_ops():
    """The dashboard shell.

    Everything here is chrome — not one number is server-rendered. The page is
    public (anyone can load the HTML) and empty until /api/ops accepts a
    password, which is what makes it safe to ship on the shop's own domain.

    It shares nothing with layout(): no nav, no footer, no ashfall.css, and
    critically no analytics.js — an ops tool that logged its own pageviews
    would pollute the very funnel it exists to measure.
    """
    tabs = "".join(
        '<button type="button" role="tab" data-tab="%s" aria-selected="%s">%s</button>'
        % (key, "true" if i == 0 else "false", esc(label))
        for i, (key, label) in enumerate(OPS_TABS))

    # The period control. It was four buttons — 7 / 30 / 90 / 365 — which could
    # only ever say "the last N days", so there was no way to ask for a single
    # day or for a calendar month. These are keys, not day counts: ops.js turns
    # each into an absolute start/end pair IN THE READER'S TIMEZONE, because
    # "today" resolved on the server is today in UTC, which is the wrong day for
    # part of every European evening. `custom` reveals the two date fields.
    OPS_RANGES = (
        ("today",     "Today"),
        ("yesterday", "Yesterday"),
        ("7d",        "Last 7 days"),
        ("30d",       "Last 30 days"),
        ("90d",       "Last 90 days"),
        ("mtd",       "This month"),
        ("lastmonth", "Last month"),
        ("12m",       "Last 12 months"),
        ("custom",    "Custom range\u2026"),
    )
    ranges = "".join(
        '<option value="%s"%s>%s</option>'
        % (key, " selected" if key == "30d" else "", esc(label))
        for key, label in OPS_RANGES)

    brand = ('<span class="brand-mark" aria-hidden="true"></span>'
             '<span class="brand-word">esports<b>boost</b></span>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analytics — {esc(D.BRAND)}</title>
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#08080c">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<!-- av()'d like every shop asset, and for a sharper reason here: /assets/* is
     served immutable for a year (vercel.json), and the console's JS talks to an
     API whose payload shape it has to agree with. An un-versioned ops.js means a
     deploy that changes /api/ops leaves the operator's cached script parsing a
     response it was never written for, with no reload that fixes it. -->
<link rel="stylesheet" href="{av('/assets/css/ops.css')}">
</head>
<body class="ops">

<div class="gate-screen" data-gate>
  <div class="gate">
    <div class="gate-brand">{brand}</div>
    <h2>Analytics console</h2>
    <p>{esc(D.BRAND)} — internal. This console is not linked from the site.</p>
    <form>
      <label class="field" style="display:none" for="ops-pw">Password</label>
      <input class="field" id="ops-pw" type="password" autocomplete="current-password"
             placeholder="Password" aria-label="Dashboard password" required>
      <button class="btn btn-primary" type="submit">Sign in</button>
    </form>
    <div class="err" data-gate-err role="alert"></div>
    <!-- Setup help, shown ONLY when the API reports it has no password configured.
         Left always-visible it reads as "the password isn't set" to someone who
         simply mistyped one, which is the opposite of helpful. -->
    <div class="note" data-gate-setup hidden>
      Set <code>OPS_PASSWORD</code> (12+ characters) in the environment and restart the
      server to enable this dashboard. Until then the API refuses every request.
    </div>
  </div>
</div>

<div class="shell" data-app hidden>
  <aside class="side">
    <a class="brand" href="/" title="{esc(D.BRAND)}">{brand}<span class="brand-tag">Analytics</span></a>
    <nav class="tabs" role="tablist" aria-label="Dashboard sections">{tabs}</nav>
    <div class="side-foot">
      <span class="store-chip" data-meta></span>
      <button class="btn btn-sm" type="button" data-signout>Sign out</button>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <button class="side-toggle" type="button" data-side-toggle aria-label="Toggle menu">
        <span></span><span></span><span></span>
      </button>
      <h1 class="topbar-title" data-tabtitle>Live view</h1>
      <span class="spacer"></span>
      <select class="field" id="ops-range" data-range aria-label="Period">{ranges}</select>
      <span class="dates" data-dates hidden>
        <input class="field" type="date" data-date-from aria-label="From date">
        <span class="dates-sep" aria-hidden="true">→</span>
        <input class="field" type="date" data-date-to aria-label="To date">
        <button class="btn btn-sm" type="button" data-date-apply>Apply</button>
      </span>
      <select class="field" id="ops-game" data-game aria-label="Filter by game">
        <option value="">All games</option>
      </select>
      <button class="btn btn-sm live-toggle" type="button" data-live aria-pressed="true"
              title="Auto-refresh the dashboard"><span class="live-dot"></span><span data-live-label>Live</span></button>
      <button class="btn btn-sm" type="button" data-refresh title="Refresh now" aria-label="Refresh">
        <span class="refresh-ico" aria-hidden="true"></span></button>
    </header>

    <div class="banner synthetic" data-synthetic hidden></div>

    <div class="content" data-panels></div>
  </main>
</div>

<script src="{av('/assets/js/ops.js')}"></script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════
#  emit
# ══════════════════════════════════════════════════════════════════════════
def img(rel):
    """Resolve an image path through whatever emit_art() actually wrote."""
    return IMG_MAP.get(rel, rel)


IMG_MAP = {}
_ASSET_V = {}


def av(rel):
    """A CSS/JS URL with a content hash on it — `/assets/js/app.js?v=8f2c1a`.

    Vercel serves `/assets/*` with `max-age=31536000, immutable` (vercel.json),
    which is the right header for a file whose URL changes when its bytes do and
    a trap for one that doesn't: without this a returning visitor keeps last
    deploy's app.js against this deploy's HTML for a year. The hash is of the
    built file, so `data.js` — generated per build from data.py — busts whenever
    the catalogue, the ladders or the prices move.

    Called from `layout()` after main() has populated dist/, so the file is
    always there; an unreadable one degrades to the bare path rather than
    breaking the build."""
    if rel not in _ASSET_V:
        try:
            with open(os.path.join(DIST, rel.lstrip("/")), "rb") as fh:
                _ASSET_V[rel] = hashlib.md5(fh.read()).hexdigest()[:8]
        except OSError:
            _ASSET_V[rel] = ""
    v = _ASSET_V[rel]
    return "%s?v=%s" % (rel, v) if v else rel


def minify_css(src):
    """Strip comments and collapse whitespace in a stylesheet.

    Deliberately conservative: it removes `/* … */` and squeezes runs of
    whitespace, and does nothing else — no selector merging, no colour or
    shorthand rewriting, no reordering. String literals and `url(…)` are copied
    through untouched, so a `content: "/*"` or a data URI cannot be mangled.

    Worth doing because this codebase documents itself in the stylesheet: the
    MOBILE PASS block alone explains four load-bearing decisions in prose, and
    `site.css` is ~40% comment by weight. That belongs in the source, not on the
    critical path of every first paint — it is render-blocking CSS. The source
    file keeps every word; only `dist/` is stripped."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        # Comments are tested BEFORE strings, and the order is load-bearing: a
        # `'` inside a comment ("don't", "the page's") is not a string opener,
        # but checking quotes first made it one — the fake string then ran to
        # the next apostrophe hundreds of lines away and copied everything
        # between it verbatim, comments included. Scanning left to right,
        # whichever token STARTS first wins, and the string branch below always
        # consumes a whole literal, so reaching `/*` here means we are not
        # inside one.
        if src.startswith("/*", i):           # comment — drop
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c in "\"'":                      # string literal — copy verbatim
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
        elif src.startswith("url(", i):
            # Only the UNQUOTED form needs verbatim handling. A quoted url() is
            # a string, and letting the string branch take it is what stops an
            # inline SVG data URI — which contains its own `url(%23n)` and a
            # dozen `'` — from ending this copy at the wrong `)` and leaving the
            # rest of the file mis-tokenised behind it.
            j = i + 4
            while j < n and src[j] in " \t\r\n":
                j += 1
            if j < n and src[j] in "\"'":
                out.append("url(")
                i = j
            else:
                end = src.find(")", i)
                end = n if end < 0 else end + 1
                out.append(src[i:end])
                i = end
        elif c in " \t\r\n":                  # whitespace run → one space
            while i < n and src[i] in " \t\r\n":
                i += 1
            out.append(" ")
        else:
            out.append(c)
            i += 1
    css = "".join(out)
    # Tighten around punctuation. The space BEFORE a colon is deliberately left
    # alone: `.a :first-child` (a descendant) and `.a:first-child` (the element
    # itself) are different selectors, and this file uses both forms.
    for ch in "{};,>":
        css = css.replace(" " + ch, ch).replace(ch + " ", ch)
    css = css.replace(": ", ":")
    return css.replace(";}", "}").strip()


# An internal link written as `/foo.html` is not wrong — it serves the right
# page — but under `cleanUrls` it serves it via a 308 to `/foo`, so every such
# href costs a crawler an extra hop on the way to a page it was already given
# the clean URL for in the sitemap and the canonical. There were 4,892 of them
# across the build, 294 of which pointed at an indexed game page. Rewriting
# them at the one place every page passes through is what makes it impossible
# for a new call site to reintroduce one; the alternative is 108 link literals
# spread over ~1500 lines, each of which has to remember the rule.
#
# Query strings and fragments are preserved (`/games/x.html?booster=y`,
# `/support.html#discord`), and a directory index collapses the way _canon()
# collapses it, so the two agree on what the clean form of a path is.
_HTML_HREF = re.compile(r'((?:href|action)=")(/[^"]*?)\.html((?:[#?][^"]*)?")')


def _clean_links(html):
    def one(m):
        path = m.group(2)
        if path.endswith("/index"):
            path = path[:-len("/index")]
        return m.group(1) + (path or "/") + m.group(3)
    return _HTML_HREF.sub(one, html)


def write(rel, content):
    path = os.path.join(DIST, rel.lstrip("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if rel.endswith(".html"):
        content = _clean_links(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return rel


# The currency i18n.js's prefix rule gives a zone with no explicit entry. Keep
# in step with defaultCurrency() there — this function exists only to work out
# which entries are therefore redundant and can be left out of the payload.
_PREFIX_CURRENCY = (("America/", "USD"), ("Europe/", "EUR"), ("Atlantic/", "EUR"))


def _prefix_currency(zone):
    for prefix, cur in _PREFIX_CURRENCY:
        if zone.startswith(prefix):
            return cur
    return "USD"


def client_data():
    payload = {
        "perDivision": D.PER_DIVISION,
        "perStep": D.PER_STEP,
        "ladders": {g["name"]: list(g["ladder"]) for g in D.GAMES},
        "tiers": {g["name"]: g["tiers"] for g in D.GAMES},
        "divmap": {g["name"]: g["divmap"] for g in D.GAMES},
        "tiercolors": {g["name"]: D.tier_colors(g) for g in D.GAMES},
        "factors": {g["name"]: g["factor"] for g in D.GAMES},
        "prices": {g["name"]: g["prices"] for g in D.GAMES if g.get("prices")},
        "winPrices": {g["name"]: g["win_prices"] for g in D.GAMES if g.get("win_prices")},
        "placePrices": {g["name"]: g["placement_prices"] for g in D.GAMES if g.get("placement_prices")},
        "services": {g["name"]: g["services"] for g in D.GAMES},
        # What the picks add-on is called on each game (champions / agents /
        # heroes / a playlist). Picker rows ship every wording in the DOM behind
        # [data-when-game]; this is for the receipt strings app.js rebuilds.
        "picks": {g["name"]: D.picks_label(g["name"]) for g in D.GAMES},
        "slugs": {g["name"]: g["slug"] for g in D.GAMES},
        "regions": {g["name"]: g["regions"] for g in D.GAMES},
        "regionShort": D.REGION_SHORT,
        # Which server the form opens on. The page is static, so the client
        # cannot read the edge header geo.py prefers — it uses geo.py's SECOND
        # and THIRD signals instead (the browser's IANA timezone, then the
        # locale's region subtag), and both tables below are DERIVED from
        # geo.py's so there is no second copy to drift from it. `saZones` is
        # the exception list, not the membership one: app.js reads an
        # `America/…` zone as North American unless it appears here, so a zone
        # neither table carries still lands on the right side of the Atlantic.
        "geo": {
            "saZones": sorted(z for z, c in geo.TZ_COUNTRY.items()
                              if c in geo.SA_COUNTRIES),
            "naCountries": sorted(geo.NA_COUNTRIES),
            # Currency by location, same two signals. `zoneCur` carries only the
            # zones whose answer DIFFERS from what i18n.js's prefix rule gives
            # (America/… → USD, Europe/… and Atlantic/… → EUR) — which is the
            # Canadian zones, Europe/London, and the handful of Russian and
            # Cypriot zones filed under `Asia/`. The rest would be ~120 entries
            # restating the prefix.
            "zoneCur": {z: geo.currency_for(c)
                        for z, c in geo.TZ_COUNTRY.items()
                        if geo.currency_for(c) != _prefix_currency(z)},
            # The locale fallback, for a browser that reports no timezone.
            "curCountries": dict(geo.CUR_COUNTRIES),
            "euCountries": sorted(geo.EU_COUNTRIES),
            # Language by location — the same three signals again, and derived
            # from geo.LANG_COUNTRIES so there is no second copy of the rule.
            # `langZones` is the timezone half, carried in full rather than as a
            # prefix rule: there is no prefix that means "France" the way
            # `Europe/…` means "the euro", and the map is one entry per listed
            # country. Both are empty maps the moment LANG_COUNTRIES is, so the
            # client falls back to English with no special case.
            "langCountries": dict(geo.LANG_COUNTRIES),
            "langZones": {z: geo.LANG_COUNTRIES[c]
                          for z, c in geo.TZ_COUNTRY.items()
                          if c in geo.LANG_COUNTRIES},
        },
        "addons": D.ADDONS,
        "promos": D.PROMOS,
        # Accounts — the flat-priced listings. The client needs the price and
        # the shard deltas (to re-quote the order checkout charges), the stock
        # base and the shard shares (to derive availability the same way
        # `D.account_stock()` does), and the name (the checkout summary prints
        # it). Sold-out listings are shipped rather than dropped — the card
        # renders its own state, and a client holding a cached data.js must be
        # able to tell "gone" from "never existed".
        #
        # ⚠ There is ONE stock derivation and it is `stock × share`, mirrored by
        # `accountStock()` in app.js. Shipping a pre-computed per-shard table
        # here would be the second authored figure data.py's ⚠ warns about, and
        # it would go stale against the server the first time a share moved.
        # `price` and `was` ship as the whole per-currency TABLE, not a figure:
        # the client picks the buyer's row exactly as pricing.py does, because
        # there is no rate between them to derive one from another.
        # `id` is repeated inside the row as well as being the key: the live
        # stock map (/api/stock) is keyed "<listing>|<shard>", so a listing
        # object has to be able to name itself when it is handed round on its
        # own — accountStock() takes the object, not the key.
        "accounts": {a["id"]: {"id": a["id"], "name": a["name"], "price": a["price"],
                               "was": a.get("was") or 0, "stock": a["stock"],
                               "tier": a["tier"], "kind": D.account_kind(a)}
                     for a in D.ACCOUNTS},
        # The shards, in the order the picker draws them. `code` is
        # REGION_SHORT's — the client never derives a second one. There is no
        # `delta`: a shard changes stock, never price.
        "accountServers": [{"region": s["region"], "code": D.account_code(s["region"]),
                            "share": s["share"]}
                           for s in D.ACCOUNT_SERVERS],
        "accountBaseCur": D.ACCOUNT_BASE_CUR,
        "accountOfferLabel": pricing.ACCOUNT_OFFER_LABEL,
        # The filter's description line, keyed by filter. app.js writes it into
        # one node rather than shipping three — it is a whole text node either
        # way, and esbT() resolves it the same way a server-rendered twin is.
        "accountKinds": {k: meta for k, _label, meta in D.ACCOUNT_KINDS},
        "accountGame": D.ACCOUNT_GAME,
        # The delivery promise, from pricing.py so the mirror cannot drift —
        # app.js translates it as a whole node, the server ships it in English
        # to the orders store and the confirmation mail.
        "accountEta": pricing.ACCOUNT_ETA,
        # Coaching — the booking product. Its price never touches the rank
        # engine, so the client carries the coach rates and pack discounts
        # directly and quote() reads them for service == "coaching".
        "coaches": D.COACHES,
        "coachPacks": D.COACH_PACKS,
        "coachFocus": D.COACH_FOCUS,
        "coachSlots": D.COACH_SLOTS,
        # Per-game bundle climbs (resolved tier-pairs). The client re-quotes each
        # through the shared engine, so a card can't show a price the order
        # wouldn't get. Only games with an entry get a strip.
        #
        # `disc` is DERIVED here from the bundle's hand-set `price` against the
        # full climb (pricing.bundle_pct) and shipped alongside it, so app.js
        # does no arithmetic of its own and the two engines apply the identical
        # double — the mirror can't drift from a rounding difference.
        "bundles": {g["name"]: [dict(b, disc=pricing.bundle_pct(g, b))
                                for b in D.bundle_climbs(g)]
                    for g in D.GAMES if D.bundle_climbs(g)},
        "boostersFree": D.STATS["free_now"],
        # handle → the one game that booster covers. The client validates
        # ?booster=<handle> against this before showing a name or attaching it
        # to an order: a query string is untrusted, and "Ordering with
        # <anything>" is a line the page would otherwise print for free.
        "boosters": {b["handle"]: BY_SLUG[b["slug"]]["name"]
                     for b in D.BOOSTERS if b["slug"] in BY_SLUG},
        # Exact icon SVGs the client roster/rail/feed renderers reuse, so a row
        # built in JS from /api/boosters is drawn with the same glyphs as the
        # server-rendered fallback beside it — one source (_ico), no drift.
        "icons": {
            "hireArrow": _ico("arrow", 12, "ico", stroke=True),
            "railArrow": _ico("arrow", 14, "ico", stroke=True),
            "moreArrow": _ico("arrow-down", 14, "ico", stroke=True),
            "pillDotRst": _ico("dot", 9, "rst-pill-ico"),
            "pillHourRst": _ico("hourglass", 10, "rst-pill-ico", stroke=True),
            "pillDotRc": _ico("dot", 9, "rc-pill-ico"),
            "pillHourRc": _ico("hourglass", 10, "rc-pill-ico", stroke=True),
            "feedArrow": _ico("arrow", 12, "lf-arrow", stroke=True),
            "feedSeal": _ico("seal", 11, "lf-done-ico", evenodd=True),
            # The drawn fallback face, one entry per glyph rather than one per
            # booster: /api/boosters names the glyph (`face`) and carries the
            # two tints, so 78 rows cost 17 marks here instead of 78.
            "faces": {_n: _ico(_n, 19, "face-ico", stroke=True) for _n in D.FACE_GLYPHS},
        },
        # Which boosters have a real avatar in site/assets-in/avatar/, and where
        # emit_art() put it. The server-rendered row resolves this through
        # drop_in(); a row app.js draws from the store has to be told, or the
        # live rail would fall back to the glyph beside a server-rendered board
        # showing photographs. Only handles with a real file are listed, so a
        # booster added without one still gets their glyph rather than a 404.
        "avatars": {_b["handle"]: img("/assets/img/avatar-%s.svg" % _b["handle"])
                    for _b in D.BOOSTERS if drop_in("avatar/" + _b["handle"])},
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
      hero.<ext>  portrait.<ext>  dashboard.<ext>  og.<ext>
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
    place("/assets/img/dashboard.svg", "dashboard", art.dashboard()); n += 1
    for g in D.GAMES:
        place("/assets/img/keyart-%s.svg" % g["slug"], "keyart/" + g["slug"],
              art.keyart(g["slug"], g["name"])); n += 1
        # Band crop of the same art, for the games grid's 78px art zones. A
        # 700-tall source cropped to 78px shows a fifth of its height, and the
        # wordmarks run from 60px (Overwatch) to 238px (Valorant) — no single
        # crop of it can hold both. Rendering the scene at 1200×300 puts every
        # logo inside the band instead. The handoff asks for exactly this:
        # "art that crops to a wide band".
        place("/assets/img/band-%s.svg" % g["slug"], "band/" + g["slug"],
              art.keyart(g["slug"], g["name"], 1200, 300)); n += 1
        place("/assets/img/emblem-%s.svg" % g["slug"], "emblem/" + g["slug"],
              art.emblem(g["slug"], g["short"])); n += 1
    for b in D.BOOSTERS:
        place("/assets/img/avatar-%s.svg" % b["handle"], "avatar/" + b["handle"],
              art.avatar(b["handle"], b["hue"])); n += 1
        # One portrait per booster: their profile header, and — for whoever
        # SPOTLIGHT names — the home hero's card, off the same file, so the
        # card and the page it links to can't show two different faces. The
        # legacy single "portrait" slot still wins for the spotlight booster so
        # an already-dropped photograph keeps working.
        slot = ("portrait" if (SPOT_BOOSTER and b["handle"] == SPOT_BOOSTER["handle"]
                               and drop_in("portrait")) else "portrait/" + b["handle"])
        place("/assets/img/portrait-%s.svg" % b["handle"], slot,
              art.avatar(b["handle"], b["hue"], size=480)); n += 1
    return n


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    shutil.copytree(PUBLIC, DIST)

    # Ship the stylesheets stripped. Source keeps its documentation; dist does
    # not carry it down the wire on every first paint. JS is deliberately NOT
    # minified here — doing it safely needs a parser (ASI and regex literals
    # make regex-based JS minification a correctness risk), and gzip already
    # takes app.js from 146K to 42K. Set ESB_NO_MINIFY=1 to debug against the
    # unstripped CSS.
    # Every font is self-hosted (see type-b-sans.css). ashfall.css is the
    # vendored design system and is not edited, so its remote @import is
    # stripped here instead: it pulls Chakra Petch + IBM Plex Sans + IBM Plex
    # Mono from Google, of which the first two are overridden by Inter and never
    # painted, and the third is now served from /assets/fonts. Leaving it in
    # would hand a third party the IP of every visitor before first paint for
    # two typefaces the site does not use — and would make the CSP's
    # `font-src 'self'` block the one it does.
    remote_import = re.compile(r"@import\s+url\(\s*['\"]?https?://[^)]*\)\s*;", re.I)
    for name in ("ashfall.css", "site.css", "type-b-sans.css", "ops.css"):
        p = os.path.join(DIST, "assets", "css", name)
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as fh:
            css = fh.read()
        css = remote_import.sub("", css)
        if os.environ.get("ESB_NO_MINIFY", "").strip() != "1":
            css = minify_css(css)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(css)

    write("/assets/js/data.js", client_data())
    images = emit_art()
    for name, out in REAL_ASSETS.items():
        base = "/assets/img/" + name.split("/")[-1]
        if name.startswith("keyart/"):
            IMG_MAP["/assets/img/keyart-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("band/"):
            IMG_MAP["/assets/img/band-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("emblem/"):
            IMG_MAP["/assets/img/emblem-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("avatar/"):
            IMG_MAP["/assets/img/avatar-%s.svg" % name.split("/")[1]] = out
        elif name.startswith("portrait/"):
            IMG_MAP["/assets/img/portrait-%s.svg" % name.split("/")[1]] = out
        elif name == "portrait":
            IMG_MAP[SPOT_PORTRAIT] = out
        else:
            IMG_MAP["/assets/img/%s.svg" % ("og-default" if name == "og" else name)] = out

    pages = [
        ("/index.html", page_home()),
        ("/games/index.html", page_games_index()),
        (ACCOUNTS_HREF, page_accounts()),
        ("/how-it-works.html", page_how()),
        ("/guarantee.html", page_guarantee()),
        ("/support.html", page_support()),
        (DEMO_HREF, page_demo()),
        (ORDERS_HREF, page_orders()),
        ("/checkout.html", page_checkout()),
        ("/checkout/success.html", page_checkout_success()),
        ("/become-a-booster.html", page_become_booster()),
        ("/404.html", page_404()),
    ]
    # Both of these pages are nothing but the placeholder roster and the
    # placeholder testimonials, so they are not built at all until that content
    # is real — an empty "Reviews" page ranks and reads worse than no page.
    if D.BOOSTERS:
        pages.insert(3, ("/boosters/index.html", page_boosters()))
        # One profile per booster. They are the roster's row targets, so they
        # ship with it or the table links into 404s.
        pages += [(booster_href(b), page_booster(b)) for b in D.BOOSTERS]
    if D.REVIEWS:
        pages.insert(6, ("/reviews.html", page_reviews()))
    # The lead-capture landing. Guarded on GUIDES the way Reviews/Boosters are on
    # their placeholder stores — an empty guides page ranks worse than none.
    if getattr(D, "GUIDES", None):
        pages.append(("/guides.html", page_guides()))
    pages += [("/legal/%s.html" % s, page_legal(s)) for s in LEGAL]
    pages += [("/games/%s.html" % g["slug"], page_game(g)) for g in D.GAMES]

    for rel, html in pages:
        write(rel, html)

    # /orders is account-scoped placeholder history reached only from the
    # account menu — kept out of search alongside the pay flow, not a page to
    # rank. It stays crawlable (no robots block) but unadvertised.
    # Only the pages that carry no `noindex` belong here — a sitemap listing a
    # noindex page sends Google two contradictory signals. `_indexable()` is the
    # single source of truth for both, so the sitemap and the meta tags can never
    # disagree: today that is the homepage, the catalogue and the nine game
    # pages. Clean-URL form, matching the canonical each page advertises.
    raw = ["/index.html"] + [r for r, _ in pages]
    urls = sorted(set(_canon(u) for u in raw if _indexable(u)))
    sm = "".join("  <url><loc>%s%s</loc></url>\n" % (D.SITE, u) for u in sorted(set(urls)))
    write("/sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % sm)
    write("/robots.txt",
          "User-agent: *\nAllow: /\nDisallow: /ops\nSitemap: %s/sitemap.xml\n" % D.SITE)

    # The console is written after the sitemap loop on purpose: it is not a page
    # of the shop, carries no canonical tag, and must never reach the sitemap,
    # robots.txt or any link on the site. Its own <meta robots> is noindex.
    write("/ops/index.html", page_ops())

    print("built %d pages + %d images → %s  (+ /ops console)" % (len(pages), images, DIST))


if __name__ == "__main__":
    main()
