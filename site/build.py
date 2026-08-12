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
from datetime import datetime, timedelta
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

NAV = [
    ("/games/", "Games"),
    ("/#live", "Live"),
    ("/boosters/", "Boosters"),
    ("/guarantee.html", "Safety"),
    ("/reviews.html", "Reviews"),
]
# Only when HIDE_PLACEHOLDER_CLAIMS drops the pages behind them — never link
# to a destination the build didn't produce.
if not D.LIVE_FEED:
    NAV.remove(("/#live", "Live"))
if not D.BOOSTERS:
    NAV.remove(("/boosters/", "Boosters"))
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

CURRENCIES = [("USD", "$", "USD"), ("EUR", "€", "EUR")]
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
    through `data-loc-icon` (currency: $ / €)."""
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
        cards += hd_card("/games/", "grid", "All %s ladders" % spell(len(D.GAMES)),
                         tag="+%d" % len(rest),
                         note_html='<b class="hd-card-fig">%s</b><span>are live too</span>'
                                   % esc(", ".join(rest)))
    return cards


def hd_boosters_cards():
    n = D.STATS.get("online") or len(D.BOOSTERS)
    cards = hd_card("/boosters/", "users", "Browse the roster",
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
    cards += hd_card("/boosters/", "user-focus", "Hire a specific booster",
                     "Name one at checkout, no extra fee")
    cards += hd_card("/boosters/#vetting", "seal", "How we verify",
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
        lines.append(("hourglass", ["Median claim", ("b", claim)]))
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
    ("games", "Games", "Pick a ladder", hd_games_cards, lambda: str(len(D.GAMES))),
    ("boosters", "Boosters", "Who plays your order", hd_boosters_cards,
     lambda: str(D.STATS.get("online") or "")),
    ("safety", "Safety", "Before you buy", hd_safety_cards, lambda: ""),
]
HD_BY_KEY = {k: (label, sec, cards, count) for k, label, sec, cards, count in HD_MENUS}

# Which NAV entries open a menu. Live and Reviews are single destinations — the
# handoff is explicit that they get no menu, and a menu holding one link is a
# worse control than the link.
HD_NAV = [
    ("games", "/games/", "Games"),
    (None, "/#live", "Live"),
    ("boosters", "/boosters/", "Boosters"),
    ("safety", "/guarantee.html", "Safety"),
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
            f'<span class="hd-live-txt"><b>Online now</b><i aria-hidden="true">—</i>'
            f'<b class="hd-live-n">{n}</b><span>verified boosters</span></span></p>')


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

    An item with a menu is a `<button>` — the handoff's control, and the thing
    the mobile accordion needs. That makes the hub page unreachable from the nav
    itself without JS, so **the first card of every menu is that hub**
    (/games/, /boosters/, /guarantee.html) and site.css opens the panel on
    `:hover`/`:focus-within` under `.no-js`, which the head script clears the
    moment scripting is on.
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
                f'<button type="button" class="hd-link" data-hd-menu="{key}"'
                f' aria-expanded="false" aria-controls="hd-m-{key}"{cur}>'
                f'<span>{esc(label)}</span>{count}'
                f'{_ico("caret", 9, "ico hd-caret", stroke=True)}'
                f'{_ico("plus", 15, "ico hd-acc hd-acc-on", stroke=True)}'
                f'{_ico("minus", 15, "ico hd-acc hd-acc-off", stroke=True)}'
                f'</button>{hd_menu(key)}</div>')
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
        <!-- Confirm password: the second entry has to match before the account
             is created. Shares the main field's eye toggle, so revealing one
             reveals both. -->
        <div class="hd-pass hd-pass-confirm">
          <span class="hd-f-top"><span class="hd-label">Confirm password</span></span>
          <span class="hd-pass-wrap">
            <input class="hd-input hd-input-bare" type="password" name="password2" data-hd-pass2
              placeholder="Re-enter your password" autocomplete="new-password">
          </span>
        </div>
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


TRUSTPILOT_URL = getattr(D, "TRUSTPILOT_URL", "")

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
    here is a fabricated review signal published to every crawler. Returning an
    empty dict lets callers `update()` unconditionally.
    """
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
    """
    if not D.STATS.get("trustpilot") or not D.STATS.get("reviews"):
        return ""
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
    inner = (f'{logo}{stars}'
             f'<span class="tp-meta"><span class="tp-word">{esc(label)}</span> '
             f'<b>{esc(D.STATS["trustpilot"])}</b> · {esc(D.STATS["reviews"])} reviews</span>')
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
    ("/support.html", "Help center", None),
    ("/become-a-booster.html", "Become a booster", None),
]
FOOT_EMAIL = "info@esportsboost.com"
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
    support = "".join(
        '<li><a href="%s">%s%s</a></li>'
        % (h, _ico(ico, 15, "ico ft-link-ico", stroke=True) if ico else "",
           '<span>%s</span>' % esc(l))
        for h, l, ico in FOOT_SUPPORT
    )
    legal = "".join('<li><a href="%s"><span>%s</span></a></li>' % (h, esc(l))
                    for h, l in FOOT_LEGAL)
    social = "".join(
        '<a class="ft-social" href="%s" aria-label="%s" title="%s"%s>%s</a>'
        % (href, esc(name), esc(name), ' target="_blank" rel="noopener noreferrer"'
           if href.startswith("http") else "", svg)
        for name, (href, svg) in _SOCIAL.items()
    )
    return f"""<footer class="ft">
  <div class="wrap ft-in">
    <div class="ft-grid">
      <div class="ft-brand">
        <a class="nav-brand ft-mark" href="/"><span class="shard" aria-hidden="true"></span>esports<b>boost</b></a>
        <div class="ft-mail">
          <span class="ft-lab">Questions? Email us at</span>
          <a class="ft-mail-a" href="mailto:{FOOT_EMAIL}">{_ico("envelope", 15, "ico ft-mail-ico", stroke=True)}{FOOT_EMAIL}</a>
        </div>
        <div class="ft-soc">
          <span class="ft-lab">Follow along</span>
          <div class="ft-soc-row">{social}</div>
        </div>
        <p class="ft-disclaimer">{esc(FOOT_DISCLAIMER)}</p>
      </div>

      <nav class="ft-col" aria-label="Games">
        <h2 class="ft-head">Games</h2>
        <ul class="ft-list">{games}
          <li><a class="ft-all" href="/games/"><span>All <b>{len(D.GAMES)}</b> games</span>{_ico("arrow", 13, "ico", stroke=True)}</a></li>
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
      <span class="ft-copy">© {D.YEAR} {esc(D.BRAND)}. All Rights Reserved.</span>
      <div class="ft-bottom-r">
        {foot_pay()}
        <span class="ft-bottom-div" aria-hidden="true"></span>
        <div class="ft-loc">{locale_switcher()}</div>
      </div>
    </div>
  </div>
</footer>"""


def layout(path, title, desc, body, current=None, jsonld=None, og_image=None,
           mobile_bar=False, extra_js="", nav_outline=False, bare=False):
    ld = ""
    for block in (jsonld or []):
        ld += '<script type="application/ld+json">%s</script>\n' % json.dumps(block, ensure_ascii=False)
    bar = ""
    if mobile_bar:
        bar = """<div class="mobile-bar" role="region" aria-label="Live quote">
  <div>
    <div class="p"><span class="mobile-was" data-when-discount data-out="was" hidden></span><span data-out="price">—</span></div>
    <div class="s" data-out="summary">—</div>
  </div>
  <a class="btn btn-primary btn-sm" href="/checkout.html" data-continue>Continue</a>
</div>"""
    # `bare` strips the page to brand + padlock + help and drops the footer to a
    # legal line. Set on the pay flow only: its one job is finishing, so it
    # offers no exits. The body class carries the warmer checkout ground so the
    # header and footer match the section between them.
    head = chrome_min() if bare else chrome(current, nav_outline)
    foot = foot_min() if bare else footer()
    body_cls = ' class="co-page"' if bare else ""
    og_image = og_image or img("/assets/img/og-default.svg")
    canonical = D.SITE + path
    # `no-js` is stripped by the first line of the document. It is the only hook
    # site.css has for the header's scripting-off fallback: with it, the mega
    # menus open on :hover / :focus-within, so the nav still reaches nine games
    # and the roster without JS. app.js runs at the foot of the body, far too
    # late to clear it — hence the inline script rather than a class app.js
    # removes on load.
    return f"""<!doctype html>
<html lang="en" class="no-js">
<head>
<script>document.documentElement.classList.remove('no-js')</script>
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
<body{body_cls}>
<a class="btn btn-secondary btn-sm" href="#main" style="position:absolute;left:-9999px" onfocus="this.style.left='12px';this.style.top='12px';this.style.zIndex='99'" onblur="this.style.left='-9999px'">Skip to content</a>
{head}
<main id="main">
{body}
</main>
{foot}
{bar}
<script src="/assets/js/data.js"></script>
<script src="/assets/js/i18n.js"></script>
<script src="/assets/js/app.js"></script>
<script src="/assets/js/analytics.js" defer></script>
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
}


def _ico(name, size=16, cls="ico", stroke=False, evenodd=False):
    """One icon. Filled by default; `stroke=True` for the linework glyphs.

    `evenodd` is for the glyphs whose inner shape is a hole (play, seal) — the
    other filled icons knock theirs out with an opposite arc sweep, which a
    straight-line subpath can't do.
    """
    paint = ('fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"') if stroke else 'fill="currentColor"'
    if evenodd:
        paint += ' fill-rule="evenodd"'
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true" focusable="false"><path d="{_ICONS[name]}" {paint}/></svg>')


# Money-back / no account / VPN region. These are the three objections a
# grey-market buyer has, so they are answered where the decision is made — in
# both heroes, beside the CTA, not in the footer's fine print.
GUARANTEES_INLINE = (
    ("shield", "Money-back until a booster is assigned"),
    ("ghost", "No account needed"),
    ("globe", "VPN matched to your region"),
)


def guarantee_row():
    return '<div class="gtee-row">%s</div>' % "".join(
        f'<span class="gtee">{_ico(ico, 16, "gtee-ico")}{esc(txt)}</span>'
        for ico, txt in GUARANTEES_INLINE)


_CARET = ('<svg class="ob-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" '
          'focusable="false"><path d="M2 3.6 5 6.6 8 3.6" fill="none" stroke="currentColor" '
          'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


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


def fc_card():
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

    The Climb row names both ranks — mark + tier, twice, the same object the
    live feed and the dashboard mock draw. It was the two marks alone, which on
    a ladder whose divisions all end in the same numeral read "IV → IV": the
    colour told you the tiers apart but nothing said which they were, and an
    Iron IV → Gold IV order was indistinguishable from Silver IV → Diamond IV.
    The mark carries the numeral, the word beside it carries the tier.

    It does NOT append the mode, though: checkout does that because it has no
    queue row to carry it, and this card has one — borrowing that text would
    print "Solo" twice in four rows. The unit services have no pair of marks, so
    there the row falls back to the summary sentence.
    """
    return f"""<aside class="fc-card">
      <div class="fc-card-head">
        <span class="fc-card-t">Your configuration</span>
        <a class="fc-change" href="#top">Change</a>
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
              <span class="ob-mark" data-mark="from"></span>
              <span class="fc-marks-t" data-tiername="from">—</span>
              {_ico("arrow", 11, "ico fc-marks-arrow", stroke=True)}
              <span class="ob-mark" data-mark="to"></span>
              <span class="fc-marks-t is-to" data-tiername="to">—</span>
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
        <span class="fc-mb">{_ico("shield", 14, "ico")}<span>Money-back</span></span>
      </div>
    </aside>"""


def cta_band(live=False, title=None, sub=None, cta=("Configure your boost", "/games/")):
    """The last ask — design_handoff_footer, band 1.

    The premise of the handoff: by the time someone reaches the bottom of the
    page they have usually already touched a configurator, so the close is
    *their* order at *their* price, not a generic "get started". `live=True`
    says this page owns a configurator (the two that do: the homepage and the
    game pages), and the band renders the configuration line, the live price and
    the summary card beside it.

    `live=False` is the handoff's documented fallback for a page with nothing to
    read back. It is not an empty card and not a fabricated default: no card at
    all, the headline quotes the catalogue minimum, and one CTA back to the
    configurator. The handoff describes this state but does not draw it — it is
    flagged for the designer.

    Scoped on `.hero-a` rather than redeclaring the handoff palette: this band
    and the two heroes are the same design, so `.btn-primary`, `.grad-text` and
    the `--h-*` text colours all resolve to the handoff's ember for free. It is
    the warmest glow on the site (.26 against .13–.22 elsewhere), deliberately,
    because it is the final ask.
    """
    if live:
        # The price, the card total and the struck list price are three
        # assertions of one number; all three come off the same render() pass.
        head = ('Your climb starts at '
                '<span class="grad-text" data-out="price">—</span>')
        lede = sub or ("Final at checkout. Refunded in full until a booster claims it, "
                       "pro-rated after that.")
        config = f"""<div class="fc-config">
        <span class="fc-pair" data-when-service="division" hidden>
          <span class="ob-mark fc-mark" data-mark="from"></span>
          <span class="fc-rank" data-out="fromRank">—</span>
          {_ico("arrow", 13, "ico fc-arrow", stroke=True)}
          <span class="ob-mark fc-mark fc-mark-to" data-mark="to"></span>
          <span class="fc-rank fc-rank-to" data-out="toRank">—</span>
          <span class="fc-div" aria-hidden="true"></span>
          <span class="fc-queue">{_ico("user", 14, "ico", stroke=True)}<span data-out="mode">—</span></span>
        </span>
        <span class="fc-unit" data-when-service="units" data-out="summary" hidden>—</span>
      </div>"""
        buttons = (f'<a class="btn btn-primary" href="/checkout.html" data-continue>'
                   f'<span>Continue your order</span>{_ico("arrow", 15, "ico", stroke=True)}</a>'
                   f'<a class="btn btn-secondary" href="/support.html">'
                   f'{_ico("chat", 17, "ico fc-b2-ico", stroke=True)}<span>Talk to support</span></a>')
        card = fc_card()
    else:
        head = ('Your climb starts at <span class="grad-text">%s</span>'
                % money(catalogue_floor())) if not title else esc(title)
        lede = sub or ("Set two ranks and the price is on screen before you sign up. "
                       "No account, no quote request.")
        config = ""
        buttons = ('<a class="btn btn-primary" href="%s"><span>%s</span>%s</a>'
                   % (cta[1], esc(cta[0]), _ico("arrow", 15, "ico", stroke=True)))
        card = ""
    return f"""<section class="hero-a hero-a-lit fc{'' if card else ' fc-solo'}">
  <div class="fx fc-glow" aria-hidden="true"></div>
  <div class="fx hero-a-hatch" aria-hidden="true"></div>
  <div class="wrap fc-inner">
    <div class="fc-copy">
      {config}
      <h2 class="fc-h">{head}</h2>
      <p class="fc-lede">{esc(lede)}</p>
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


def guarantee_cards():
    """The three promises in the plain `cards-3` shell — /games/ and the game
    pages. The guarantee page draws the same three entries with their icon tile
    and proof line; see promise_cards()."""
    cards = "".join(f"""<div class="card">
      <span class="card-kicker">{esc(k)}</span>
      <span class="card-title">{esc(t)}</span>
      <p class="card-body">{esc(b)}</p>
    </div>""" for _ico_name, _stroke, k, t, b, _proof in D.GUARANTEES)
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
        tiles.append(f"""<a class="gg-tile gg-more" href="/games/">
      <span class="gg-more-top">
        <span class="gg-more-n">+{len(rest)}</span>
        <span class="gg-more-t"><b>{esc(joined)}</b> <span>ladders are live too.</span></span>
      </span>
      <span class="gg-more-btn"><span>All games</span>{_ico("arrow", 14, "ico", stroke=True)}</span>
    </a>""")
    return '<div class="gg-grid">%s</div>' % "".join(tiles)


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
            return (tier_mark(g, tier, label, strong=strong, wide=wide)
                    + ('<span class="lf-tier">%s</span>' % esc(name) if name else ""))
        rating_name = ('<span class="lf-tier is-to">%s</span>' % esc(f["rating"])) if wide else ""
        mins = f["mins"]
        rows += f"""<li class="lf-row">
        <span class="lf-when">
          <span class="lf-ago" data-mins="{mins}">{esc(_ago(mins))}</span>
          <span class="lf-clock" data-mins="{mins}">{esc(_clock(mins, now))}</span>
        </span>
        <span class="lf-rail" aria-hidden="true"><i class="lf-dot"></i></span>
        <span class="lf-climb">
          <span class="lf-letter" aria-hidden="true">{esc(f.get('initial') or (g['name'][0] if g else '?'))}</span>
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
        # The handoff's avatar is an initial on a tinted ring — the ring colour
        # is what carries availability, and a generated portrait is an
        # unreadable smudge at 38px. A real photograph dropped into
        # assets-in/avatar/<handle> mounts inside the same ring instead.
        face = (f'<img src="{img("/assets/img/avatar-%s.svg" % b["handle"])}" alt="" '
                f'width="38" height="38" loading="lazy">'
                if drop_in("avatar/" + b["handle"])
                else '<span class="rc-initial">%s</span>' % esc(b["handle"][:1].upper()))
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
      <a class="rc-all" href="/boosters/"><span>All <b>{n}</b> boosters</span>{_ico("arrow", 14, "ico", stroke=True)}</a>
    </div>"""


def discord_card():
    """The rail's second card. Was an uppercase heading over a centred text
    link; it now has a mark, a sentence-case heading and a real button."""
    d = getattr(D, "DISCORD", None)
    if not d or not D.STATS.get("discord"):
        return ""
    return f"""<div class="dcd">
      <div class="dcd-head">
        <span class="dcd-tile">{_ico("chat", 19, "ico", stroke=True)}</span>
        <span class="dcd-titles">
          <span class="dcd-title"><b>{esc(D.STATS['discord'])}</b> in the Discord</span>
          <span class="dcd-label">{esc(d['label'])}</span>
        </span>
      </div>
      <p class="dcd-body">{esc(d['body'])}</p>
      <a class="dcd-cta" href="{esc(d['href'])}">{esc(d['cta'])}{_ico("arrow", 14, "ico", stroke=True)}</a>
    </div>"""


def roster_panel(rows=None):
    """The right rail: who is on shift, then the Discord.

    Nobody on shift renders no roster card, never an empty one — but the rail
    still wraps whatever is left, because `.rail` is where the section's local
    tokens are declared and a bare Discord card outside it would lose them.
    """
    rows = rows or D.BOOSTERS[:5]
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


def demo_order():
    """D.DEMO_ORDER with its derived figures resolved. Cached on first call.

    Percentage, days left, the W–L record and the price are COMPUTED from the
    ranks in the fixture and the real formula, never typed. The handoff's whole
    premise is that the mock's numbers agree with each other, and a typed
    percentage drifts the moment a ladder gains a tier or a factor is retuned —
    the same property ladder_strip()'s "cheapest single division" has.

    One deliberate divergence from the drawn mock: it reads 62% complete, taken
    against a League ladder with no Emerald ("12 of ~19 divisions"). On this
    site's ladder Gold IV → Platinum II is 6 of the 12 rungs to Diamond IV, so
    the bar reads 50%. The handoff asks for the ladder distance; 62 was its
    arithmetic for it.
    """
    if getattr(demo_order, "_v", None):
        return demo_order._v
    O = dict(D.DEMO_ORDER)
    rank = lambda k: (" ".join(O[k])).strip()
    O["start_rank"], O["at_rank"], O["target_rank"] = (rank("start"), rank("at"),
                                                       rank("target"))
    pct = 0.0
    if _DEMO_GAME:
        L = _DEMO_GAME["ladder"]
        try:
            a, b, c = (L.index(O["start_rank"]), L.index(O["at_rank"]),
                       L.index(O["target_rank"]))
            pct = (b - a) / (c - a) if c > a else 0.0
        except ValueError:      # a fixture rank that is not on this ladder
            pct = 0.0
    # Priced WITH the fixture's add-ons, because the demo page's details rail
    # names them: a row reading "Add-ons: Champions, agents & roles" over a
    # "Paid" figure quoted without them is a hand-typed price by another route.
    addons = [a for a in list(O.get("addons") or []) if any(x["id"] == a for x in D.ADDONS)]
    O["addon_labels"] = [x["label"] for x in D.ADDONS if x["id"] in addons]
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
    demo_order._v = O
    return O


# The two SVG gradients inside the mock are referenced by id, so two panels on
# one page would both paint with the first one's stops — the bug the inlined
# game logos hit. One counter, one namespace per instance.
_DASH_N = 0


def dash_mock(example=False, live=False):
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
    uid, O, g = "dsh%d" % _DASH_N, demo_order(), _DEMO_GAME

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
            <span class="dm-lab">LP across the order</span>
            <span class="dm-net"><i>+{O['lp_net']}</i> LP net</span>
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
            <span class="dm-cap">Order start<i aria-hidden="true"> · </i>{esc(O['start_rank'])}</span>
            <span class="dm-cap is-now">Now<i aria-hidden="true"> · </i>{esc(O['at_rank'])}</span>
          </div>
        </div>"""

    rows = ""
    for m in O["matches"]:
        win = m["result"] == "Win"
        rows += f"""<div class="dm-row">
            <span class="dm-champ" style="--champ:{esc(m['champ'])}"></span>
            <span class="dm-queue">Ranked solo{_ico("play", 14, "dm-replay", evenodd=True)}</span>
            <span class="dm-res{' is-win' if win else ''}">{esc(m['result'])}</span>
            <span class="dm-kda">{esc(m['kda'])}</span>
            <span class="dm-lp{' is-up' if win else ''}">{esc(m['lp'])}</span>
          </div>"""

    pill = ('<span class="dm-example">Example</span>' if example else "")
    bar = "" if live else f"""<div class="dm-bar">
        <span class="dm-bar-l"><span class="dm-lab">Order</span><span class="dm-id">{esc(O['id'])}</span>{pill}</span>
        <span class="dm-status"><span class="dot-live dot-ok" aria-hidden="true"></span>In progress</span>
      </div>"""
    # The footer's right cell on the resolved order is the handoff's "All 38
    # games" link to the replay view. That view does not exist, so it is not
    # drawn — same rule that keeps the live feed's rows unlinked and the roster's
    # "Load more" out of the DOM when nothing is behind it. Build the replay
    # page and the link comes back.
    if live:
        mins = O["matches"][0]["when"] if O["matches"] else 0
        foot = f"""<span class="dm-foot-l"><span class="dot-live dot-ok" aria-hidden="true"></span>Updated live<i aria-hidden="true"> · </i>last game <b class="lf-ago" data-mins="{mins}">{esc(_ago(mins))}</b></span>"""
    else:
        foot = f"""<span class="dm-foot-l"><span class="dot-live dot-ok" aria-hidden="true"></span>Order dashboard · live</span>
        <span class="dm-foot-r">
          <span class="dm-btn">{_ico("pause", 13, "ico", stroke=True)}Pause</span>
          <span class="dm-btn">{_ico("chat", 13, "ico", stroke=True)}<span>Message <i>{esc(O['booster'])}</i></span></span>
        </span>"""
    shell = ('<div class="dm dm-open">' if live else
             '<div class="dm" role="img" aria-label="Preview of the order dashboard">')

    return f"""{shell}
      {bar}

      <div class="dm-body">
        <div class="dm-climb">
          {mark(O['start'])}<span class="dm-climb-t">{esc(O['start'][0])}</span>
          {_ico("arrow", 16, "dm-climb-arrow", stroke=True)}
          {mark(O['target'], strong=True)}<span class="dm-climb-t is-to">{esc(O['target'][0])}</span>
        </div>

        <div class="dm-prog">
          <span class="dm-prog-l">{mark(O['at'], small=True)}{esc(O['at_rank'])} · <b>{O['lp']} LP</b></span>
          <span class="dm-prog-r"><b>{O['pct']}%</b> complete<i aria-hidden="true"> · </i><b>{O['days_left']}</b> days left</span>
        </div>
        <div class="dm-track"><span class="dm-fill" style="width:{O['pct']}%"></span></div>

        {chart}

        <!-- The one line here left untranslated on purpose: "Last 5 of 38
             games" carries two figures inside the sentence, and splitting it
             into fragments the way the progress line is split would fix the
             English word order onto French and German, which put the count
             elsewhere. It falls back to English, which i18n.js is built for. -->
        <div class="dm-hist">
          <span class="dm-hist-t">Match history</span>
          <span class="dm-hist-m">Last {len(O['matches'])} of {O['games']} games · <b>{esc(O['record'])}</b></span>
        </div>
        <div class="dm-table">
          <div class="dm-row dm-head">
            <span></span><span>Queue</span><span>Result</span><span>K / D / A</span><span>LP</span>
          </div>
          {rows}
        </div>
      </div>

      <div class="dm-foot">{foot}</div>
    </div>"""


# The four things the dashboard lets you do that a DM cannot. Neutral chips, not
# accent outlines: they are facts about the order, not four more buttons. Icons
# follow the site's existing mapping — globe is Regional VPN and eye-off is
# Offline appearance everywhere else on the site, ghost is "no account".
DASHBOARD_CHIPS = (
    ("globe", False, "Regional VPN"),
    ("eye-off", True, "Offline appearance"),
    ("receipt", True, "Pro-rated refunds"),
    ("ghost", False, "No account sharing on duo"),
)


def dashboard_section(num=None, on_demo=False):
    """The whole section: the mock, the three claims, the chips and the CTAs.

    `num` numbers the eyebrow on the homepage, where the section is 04 in a run
    of numbered sections; /how-it-works.html has no such run, so it renders the
    same block with no kicker.

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
        f'<button class="dsh-demo" type="button" data-demo-open>'
        f'{_ico("monitor", 18, "dsh-demo-ico", evenodd=True)}Open the demo dashboard</button>'
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
      <div class="dsh-bens">{bens}</div>
      <div class="dsh-chips">{chips}</div>
      <div class="dsh-cta">
        <a class="btn btn-primary" href="/games/">Configure your boost{_ico("arrow", 15, "ico", stroke=True)}</a>
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


def spotlight_card():
    """Home hero, right column — the booster of the month in the card shell.

    This was floating text on the gradient, which read as an unfinished area.
    It is now the same surface as every other module on the site, and the one
    dot-separated string is split into two labelled figures.

    Name, order count and portrait come off the roster entry named by
    D.SPOTLIGHT, so this card can never quote different numbers than the
    roster panel or the boosters page. No such booster → no card: the handoff
    asks for the month with no qualifying booster to hide it, not to render an
    empty one.
    """
    if not SPOT_BOOSTER:
        return ""
    b = SPOT_BOOSTER
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
      <span class="spot-meta"><span>{b['orders']}</span> orders delivered</span>
      <div class="spot-stats">{stats}</div>
      <a class="spot-cta" href="{esc(_SPOT.get('href') or booster_href(b))}">{_ico("user", 15)}{esc(_SPOT.get('cta', ''))}</a>
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
    if D.STATS.get("trustpilot") and D.STATS.get("reviews"):
        bits.append(
            f'{_ico("star", 15, "hero-h-star")}'
            f'<span><b>{esc(D.STATS["trustpilot"])}</b> <span>on Trustpilot</span>'
            f'<i aria-hidden="true"> · </i><span>{esc(D.STATS["reviews"])}</span> '
            f'<span>reviews</span></span>')
    if D.STATS.get("boosts"):
        if bits:
            bits.append('<span class="hero-h-div" aria-hidden="true"></span>')
        bits.append('<span><b>%s</b> boosts delivered</span>' % esc(D.STATS["boosts"]))
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


def booster_face(b, px=38, lazy=True):
    """What sits inside the availability ring.

    Initials by default: the handoff's design, and a generated portrait is an
    unreadable smudge at 38px. A real photograph dropped into
    assets-in/avatar/<handle> mounts inside the same ring — the ring stays
    either way, because its colour is what encodes free / busy.
    """
    if drop_in("avatar/" + b["handle"]):
        return ('<img src="%s" alt="" width="%d" height="%d"%s>'
                % (img("/assets/img/avatar-%s.svg" % b["handle"]), px, px,
                   ' loading="lazy"' if lazy else ""))
    return '<span class="rst-initial">%s</span>' % esc(b["handle"][:1].upper())


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
      <a class="ds-cta" href="{esc(d['href'])}">{esc(V.get('strip_cta', 'Join'))}{_ico("arrow", 12, "ico", stroke=True)}</a>
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
        <a class="btn btn-primary" href="/games/">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
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
    hire = ("/games/%s.html?booster=%s" % (g["slug"], b["handle"])) if g else "/games/"
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
          <a class="btn btn-primary btn-sm" href="/games/">Order anyway</a>
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
          <span class="bp-climb">{fm}<span class="bp-tier">{esc(fn)}</span>
            {_ico("arrow", 12, "bp-arrow", stroke=True)}
            {tm}<span class="bp-tier is-to">{esc(tn)}</span></span>
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
    href = ("/games/%s.html?booster=%s" % (g["slug"], b["handle"])) if g else "/games/"
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
            "url": D.SITE + booster_href(b),
        },
    }, {
        "@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Boosters",
             "item": D.SITE + "/boosters/"},
            {"@type": "ListItem", "position": 3, "name": b["handle"],
             "item": D.SITE + booster_href(b)},
        ],
    }]

    body = f"""<section class="bp">
  <div class="bp-glow" aria-hidden="true"></div>
  <div class="wrap">
    <nav class="bp-crumbs" aria-label="Breadcrumb">
      <a href="/">Home</a>{_ico("chevron-right", 12, "bp-crumb-i", stroke=True)}
      <a href="/boosters/">Boosters</a>{_ico("chevron-right", 12, "bp-crumb-i", stroke=True)}
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
                  body, current="/boosters/", jsonld=ld, nav_outline=True,
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
        out += tier_mark(g, tier, label, strong=to, wide=bool(ladder), base="rv-mark")
        name = ladder if (to and ladder) else ("" if ladder else tier)
        if name:
            out += ('<span class="rv-tier%s">%s</span>'
                    % (" is-to" if to else "", esc(name)))
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
    duo = "Duo queue"
    if pct:
        duo += ' <span class="seg-pct">+%d%%</span>' % round((pricing.DUO_MULT - 1) * 100)
    solo_i = _ico("user", 15, "seg-ico", stroke=True) if icons else ""
    duo_i = _ico("users", 15, "seg-ico", stroke=True) if icons else ""
    return f"""<div class="seg seg-full">
        <label class="seg-opt"><input type="radio" name="{name}" value="Solo" data-mode autocomplete="off">{solo_i} Solo</label>
        <label class="seg-opt"><input type="radio" name="{name}" value="Duo queue" data-mode autocomplete="off">{duo_i} {duo}</label>
      </div>"""


def _addons_sorted():
    """Free inclusions first. Leading with what costs nothing establishes the
    block as generous before it asks for money — and the free one (offline
    appearance) is a trust proof that was previously buried."""
    return sorted(D.ADDONS, key=lambda a: (a["pct"] != 0, D.ADDONS.index(a)))


def addons_block(money=False, paid_only=False):
    """Add-on picker. `money` renders each price as the dollars it actually adds
    to this order rather than a percentage — used at checkout, where buyers
    price in currency, not maths.

    `paid_only` drops the always-on inclusion, so the order card shows the three
    add-ons the handoff draws and nothing else. It is a fact about every order
    rather than a choice, and a fourth checkbox row costs the card vertical
    budget its CTA needs to clear the fold. Checkout still lists all four.
    """
    rows = []
    for a in _addons_sorted():
        free = a["pct"] == 0
        if free and paid_only:
            continue
        if free:
            price = '<span class="price price-free">Included</span>'
        elif money:
            price = '<span class="price" data-addon-price="%s">—</span>' % esc(a["id"])
        else:
            price = '<span class="price">+%d%%</span>' % round(a["pct"] * 100)
        checked = " checked disabled" if free else ""
        rows.append(f"""<label class="opt{' opt-free' if free else ''}">
        <input type="checkbox" data-addon="{esc(a['id'])}"{checked} autocomplete="off">
        <span><span style="display:block">{esc(a['label'])}</span>
        <span class="note">{esc(a['note'])}</span></span>
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


def rank_picker(g, which, sfx=""):
    """One side of the two-step rank control: tier <select> + division buttons.

    Replaces the pair of flat `<select>`s the ladder used to be. Two bare lists
    of 29 ranks gave no sense of the distance being bought, which is the thing
    the price is for — the tier mark carries the tier's colour and the division
    numeral, and the divisions sit exposed as a radio row instead of hidden
    inside a dropdown.

    `data-sel="fromTier"/"toTier"` and `data-subseg` are both app.js hooks; the
    options here are only the first paint, refilled per game at runtime.
    """
    tiers = "".join('<option value="%s">%s</option>' % (esc(t), esc(t)) for t in g["tiers"])
    target = which == "to"
    label = "Target rank" if target else "Current rank"
    sid = "w-%s-tier%s" % (which, sfx)
    return f"""<div class="ob-rank{' ob-rank-target' if target else ''}">
        <label class="ob-lab" for="{sid}">{label}</label>
        <div class="ob-field">
          <span class="ob-mark" data-mark="{which}" aria-hidden="true"></span>
          <select class="ob-select" id="{sid}" data-sel="{which}Tier" autocomplete="off">{tiers}</select>
          {_CARET}
        </div>
        <div class="ob-divs" data-subseg="{which}" role="group" aria-label="{label} division"></div>
      </div>"""


def ladder_strip(g):
    """The climb, drawn. One tick per rung with the crossed span filled, tier
    captions underneath, and the two facts that make the price legible: how far
    this order actually goes, and what the cheapest possible order costs.

    The floor price is quoted through pricing.quote() like every other number on
    the site, so "cheapest single division" and the `from $NN` in the H1 are the
    same claim and cannot contradict each other.
    """
    floor = min(quote(g["name"], g["ladder"][i], g["ladder"][i + 1])["total"]
                for i in range(len(g["ladder"]) - 1))
    return f"""<div class="ob-ladder">
        <div class="ob-ticks" data-ticks aria-hidden="true"></div>
        <div class="ob-tiercaps" data-tier-caps aria-hidden="true"></div>
        <div class="ob-ladder-foot">
          <span><b data-out="steps">—</b> <span data-out="stepsWord">divisions</span> to climb</span>
          <span>Cheapest single division {money(floor)}</span>
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
    real rating — same rule as trustpilot_badge()."""
    if not D.STATS.get("trustpilot") or not D.STATS.get("reviews"):
        return ""
    star = ('<svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            '<path d="M12 2l2.6 6.8H22l-6 4.5 2.3 7L12 15.9 5.7 20.3 8 13.3 2 8.8h7.4z" '
            'fill="#00b67a"/></svg>')
    return (f'<span class="ob-tp">{star}<b>{esc(D.STATS["trustpilot"])}</b> on Trustpilot · '
            f'{esc(D.STATS["reviews"])} reviews</span>')


def wizard(game=None):
    """The order card on the game pages — the "Ladder card" from the LoL boost
    hero handoff, ported onto Ashfall's tokens and this build's data contract.

    What the redesign changed, and why each one is load-bearing:
      · the ladder is visible (see rank_picker/ladder_strip) rather than implied
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
      </div>

      <div data-panel="division">
        <div class="ob-ranks">
          {rank_picker(g, "from")}
          <span class="ob-arrow" aria-hidden="true">{_ico("arrow", 16, "ico", stroke=True)}</span>
          {rank_picker(g, "to")}
        </div>
        {ladder_strip(g)}
      </div>

      <div data-panel="wins" hidden>
        <div class="ob-ranks ob-ranks-unit">
          {rank_picker(g, "from", "-wins")}
          <div class="ob-unit">
            <span class="ob-lab">How many net wins</span>
            <div class="stepper" data-stepper="wins" data-min="1" data-max="20">
              <button class="btn btn-icon" type="button" data-step="-1" aria-label="One win fewer">–</button>
              <output>5</output>
              <button class="btn btn-icon" type="button" data-step="1" aria-label="One win more">+</button>
            </div>
          </div>
        </div>
      </div>

      <div data-panel="placements" hidden>
        <div class="ob-ranks ob-ranks-unit">
          {rank_picker(g, "from", "-pl")}
          <div class="ob-unit">
            <span class="ob-lab">How many placement games</span>
            <div class="stepper" data-stepper="placements" data-min="1" data-max="10">
              <button class="btn btn-icon" type="button" data-step="-1" aria-label="One game fewer">–</button>
              <output>5</output>
              <button class="btn btn-icon" type="button" data-step="1" aria-label="One game more">+</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ob-two">
        <div class="ob-cell">
          <span class="ob-lab">How it's played</span>
          {mode_seg("w-mode", pct=True)}
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
        {addons_block(money=True, paid_only=True)}
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
          <span class="ob-lab">Delivered in</span>
          <span class="quote-eta" data-out="eta">—</span>
          {free}
        </div>
      </div>

      <a class="btn btn-primary btn-block ob-cta" href="/checkout.html" data-continue>
        <span>Continue to checkout</span><span class="ob-cta-sep" aria-hidden="true">·</span><span data-out="price">—</span>
        {_ico("arrow", 15, "ico", stroke=True)}
      </a>

      <div class="ob-assure">
        {ob_trust()}
        {pay_glyphs()}
      </div>
    </div>"""


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
            <span class="bs-tiermark" data-mark="{which}" aria-hidden="true"></span>
            <span data-tiername="{which}">—</span>
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

      <div class="bs-ranks bs-controls">
        <div class="bs-cell">
          <span class="bs-lab">How it's played</span>
          {mode_seg("bs-mode", pct=True, icons=True)}
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

      <div class="bs-rail" data-rail aria-hidden="true">
        <span class="bs-rail-fill"></span>
        <span class="bs-rail-h bs-rail-h1"></span>
        <span class="bs-rail-h bs-rail-h2"></span>
      </div>
      <div class="bs-railcaps" data-rail-caps aria-hidden="true"></div>

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
        <a class="btn btn-primary" href="/games/">Configure your boost{_ico("arrow", 15, "ico", stroke=True)}</a>
        <a class="btn btn-secondary" href="#live">{_ico("play", 18, "hero-h-play", evenodd=True)}Watch a live boost</a>
      </div>
      {guarantee_row()}
      <hr class="hero-a-rule">
      {hero_rating()}
    </div>
    {spotlight_card()}
  </div>

  {bs_band(chip_games)}
</section>

<section class="section gg" id="games">
  <div class="gg-hatch" aria-hidden="true"></div>
  <div class="wrap gg-wrap">
    {sec_head("01", "Games",
              "%s ladders.<br>%s services." % (spell(len(D.GAMES)).capitalize(),
                                               spell(sum(len(services_of(g)) for g in D.GAMES)).capitalize()))}
    {games_grid()}
  </div>
</section>

{live_section}

{dashboard_section("04")}

{reviews_section}

{cta_band(live=True, cta=("Continue your order", "/checkout.html"))}"""

    org = {"@context": "https://schema.org", "@type": "Organization",
           "name": D.BRAND, "url": D.SITE, "logo": D.SITE + "/assets/img/favicon.svg"}
    # An aggregateRating in JSON-LD is a machine-readable claim that search
    # engines surface as review stars. Only ever emit it from a real rating.
    org.update(rating_ld())
    ld = [org, {"@context": "https://schema.org", "@type": "WebSite",
                "name": D.BRAND, "url": D.SITE}]
    # nav_outline for the same reason the game pages set it: the hero's own
    # gradient CTA is the filled button in this viewport, so the nav's "Start
    # an order" drops to an outline rather than splitting the click.
    return layout("/", "Rank boosting with the price up front — %s" % D.BRAND,
                  "Set two ranks and see the exact price and delivery window before you make an "
                  "account. Verified boosters, guest checkout, pro-rated refunds. 9 games, every region.",
                  body, current=None, jsonld=ld, mobile_bar=True, nav_outline=True)


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
    # This game's own boosters, capped: the board is 50 and League alone has 22,
    # which is a page of table inside a section that only has to establish that
    # real people cover this ladder. The full list is /boosters/.
    roster = [b for b in D.BOOSTERS if b["slug"] == g["slug"]][:6] or D.BOOSTERS[:4]
    def _for_game(r):
        token = r["game"].split(" · ")[0].strip().lower()
        return token in (g["name"].lower(), g["short"].lower()) or g["name"].lower().startswith(token)
    revs = [r for r in D.REVIEWS if _for_game(r)][:6]
    faq = [(("What do I need to give you for %s?" % g["name"]),
            "For solo orders: your login and the server. Nothing else — no recovery email, no "
            "phone number, no password change. For duo, nothing at all; you keep the account and "
            "queue with the booster.")] + D.FAQ[:6]

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
    cells = [c for c in (
        (f'<div class="stat"><span class="stat-v"><b>{esc(D.STATS["trustpilot"].split("/")[0].strip())}</b>'
         f'<i>/ {esc(D.STATS["trustpilot"].split("/")[-1].strip())}</i></span>'
         f'<span>Trustpilot · {esc(D.STATS["reviews"])} reviews</span></div>')
        if D.STATS["trustpilot"] and D.STATS["reviews"] else "",
        (f'<div class="stat"><span class="stat-v"><b>{esc(D.STATS["median_claim"].split(" ")[0])}</b>'
         f'<i>{esc(" ".join(D.STATS["median_claim"].split(" ")[1:]))}</i></span>'
         f'<span>Median time to claim</span></div>') if D.STATS["median_claim"] else "",
        (f'<div class="stat"><span class="stat-v"><b>{esc(D.STATS["boosts"])}</b></span>'
         f'<span>Boosts delivered</span></div>') if D.STATS.get("boosts") else "",
    ) if c]
    stat_row = ('<div class="stat-row">%s</div>' % "".join(cells)) if cells else ""

    # Service chips — first one is the page's headline service, the rest read as
    # "we also do these". Same string that used to run as one dim eyebrow line.
    svc = [s.strip() for s in g["services"].split("·") if s.strip()]
    chips = "".join('<span class="svc-chip%s">%s</span>'
                    % (" is-on" if i == 0 else "", esc(s)) for i, s in enumerate(svc))

    table = booster_table(roster)
    online = (f'<span class="tag tag-neutral">{D.STATS["online"]} online</span>'
              if D.STATS["online"] else "")
    booster_col = f"""<div class="stack" style="gap:20px">
      <div class="sec-head">
        <div class="sec-head-copy">
          <span class="sec-kicker"><span class="sec-kicker-n">02</span><span class="sec-kicker-l">Boosters</span></span>
          <h2 class="h-sec" style="font-size:clamp(24px,2.6vw,32px)">On shift now</h2>
        </div>
        {online}
      </div>
      {table}
    </div>""" if table else ""

    ld = [
        product,
        faq_ld(faq),
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": D.SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Games", "item": D.SITE + "/games/"},
            {"@type": "ListItem", "position": 3, "name": g["name"],
             "item": "%s/games/%s.html" % (D.SITE, g["slug"])},
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
        <a href="/">Home</a> <span aria-hidden="true">/</span> <a href="/games/">Games</a>
        <span aria-hidden="true">/</span> <span class="crumbs-here">{esc(g['name'])}</span>
      </nav>
      <div class="svc-chips">{chips}</div>
      <h1 class="h-lg" style="font-size:clamp(38px,5.4vw,68px)">{esc(g['name'])}<br><span class="grad-text">from {fp}.</span></h1>
      <p class="lede">{esc(g['blurb'])}</p>
      {stat_row}
      <hr class="hero-a-rule">
      {guarantee_row()}
      <p class="hero-a-note">{_ico("info", 14, "gtee-ico")}<span>{esc(g['note'])}</span></p>
    </div>
    <div id="configure">{wizard(game=g['name'])}</div>
  </div>
</section>

{marquee()}

<section class="wrap section">
  <div class="{'split' if booster_col else 'stack'}">
    <div class="stack" style="gap:26px">
      {sec_head("01", "How it runs", "Three steps, then<br>it's out of your hands")}
      {steps_block()}
    </div>
    {booster_col}
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
      replies in minutes{reply_claim}.</p>
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
                  og_image=img("/assets/img/keyart-%s.svg" % g["slug"]), mobile_bar=True,
                  nav_outline=True)


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
      <div class="btn-row"><a class="btn btn-primary" href="/games/">Start an order</a></div>
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
      <span class="rst-live-n"><b>{esc(str(n))}</b> <span>on the board</span><i aria-hidden="true"> · </i><b>{esc(str(free))}</b> <span>free right now</span></span>
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
    return layout("/boosters/", "Boosters on shift — %s" % D.BRAND,
                  "Who plays your order: verified ranks, live trials, monthly review, one free swap "
                  "per order.", body, current="/boosters/", nav_outline=True)


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
        <a class="btn btn-primary sg-cta" href="/games/">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
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
    js = """<script>
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
    return layout("/guarantee.html", "Refund and safety guarantee — %s" % D.BRAND,
                  "Full refund until a booster claims your order, pro-rated after that, automatic "
                  "refund if nobody claims it in 24 hours. The whole policy on one page.",
                  body, current="/guarantee.html",
                  jsonld=[faq_ld([(q, a) for _fid, q, a in faq])],
                  extra_js=js, nav_outline=True)


def page_support():
    cells = [c for c in (
        (f'<div class="stat"><b>{esc(D.STATS["reply"])}</b>'
         f'<span>Median first reply last month</span></div>') if D.STATS["reply"] else "",
        (f'<div class="stat"><b>{esc(D.STATS["discord"])}</b>'
         f'<span>Players in the Discord</span></div>') if D.STATS["discord"] else "",
    ) if c]
    support_stats = ('<div class="stat-row">%s</div>' % "".join(cells)) if cells else ""

    body = f"""<section class="wrap section">
  <div class="split">
    <div class="stack" style="gap:22px">
      <span class="kicker">Support</span>
      <h1 class="h-md">Two ways in.<br>Both are read<br>by people.</h1>
      <p class="lede">No ticket robot, no "we'll get back to you within 48 hours". Discord is the
      fast one — that's where this market already lives, and it's where our staff sit all day.</p>
      {support_stats}
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
    if D.TRUSTPILOT_URL:
        second = (f'<a class="btn btn-secondary" href="{esc(D.TRUSTPILOT_URL)}" '
                  f'target="_blank" rel="noopener nofollow">'
                  f'<span class="rvp-tp-star" aria-hidden="true">&#9733;</span>'
                  f'<span>Read on Trustpilot</span>'
                  f'{_ico("arrow-up-right", 13, "ico", stroke=True)}</a>')
    else:
        second = ('<a class="btn btn-secondary" href="#reviews-feed" data-rvp-worst>'
                  + _ico("arrow-down", 15, "ico", stroke=True)
                  + '<span>Read the worst first</span></a>')

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
          <b>{esc(D.STATS['reviews'])}</b> <span>reviews</span></h1>
        <p class="rvp-lede">Every review below is attached to a paid, completed order — pulled from
        Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so
        one-star reviews sit in the same feed.</p>
        <div class="rvp-acts">
          <a class="btn btn-primary" href="/games/">Start an order{_ico("arrow", 15, "ico", stroke=True)}</a>
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
          <span class="tko-avatar">{booster_face(b, px=40, lazy=False)}</span>
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
    body = "%s\n%s\n%s" % (_demo_lookup(O), dashboard_section(on_demo=True),
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
    """`[IV] Gold → [IV] Diamond` — mark + tier per end, the pairing the feed,
    the checkout and the closing band all use (a mark alone only names the
    division numeral)."""
    fm, fn = _ord_side(g, frm, False)
    tm, tn = _ord_side(g, to, True)
    return (f'<span class="ord-climb">{fm}<span class="ord-tier">{esc(fn)}</span>'
            f'<i class="ord-arw" aria-hidden="true">→</i>'
            f'{tm}<span class="ord-tier">{esc(tn)}</span></span>')


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
    at_html = "%s<span class=\"ord-tier\">%s</span>" % at if g else esc(O.get("at_rank", ""))
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
    """`/orders.html` — the signed-in account's order history."""
    active = demo_order()
    hist = order_history()
    total = len(hist) + 1
    spent = active["price"] + sum(o["price"] for o in hist)

    head = "".join('<span>%s</span>' % esc(t) for t in
                   ("Order", "Game", "Climb", "Queue", "Delivered", "Paid", "Status"))
    rows = "".join(_ord_row(o) for o in hist)

    body = f"""<section class="section ord">
  <div class="wrap ord-wrap">
    <header class="ord-head">
      <span class="ord-eyebrow">Account</span>
      <h1 class="ord-h1">Your orders</h1>
      <p class="ord-sub">Every boost you've ordered — the one in progress, and the ones already delivered.</p>
      <p class="ord-hello" data-ord-hello hidden>{_ico("user", 14, "ico", stroke=True)}<span>Signed in as</span> <b data-ord-name></b></p>
    </header>

    <div class="ord-guest" data-ord-guest>
      <div class="ord-guest-c">
        <span class="ord-guest-i" aria-hidden="true">{_ico("user", 18, "ico", stroke=True)}</span>
        <span>You're viewing a sample history. <b>Log in</b> to keep your orders in one place — or track a single order by the link we emailed you. Checkout never needs an account.</span>
      </div>
      <div class="ord-guest-a">
        <button type="button" class="btn btn-primary btn-sm" data-hd-auth="signin">Log in</button>
        <a class="btn btn-outline btn-sm" href="{DEMO_HREF}">Track by link</a>
      </div>
    </div>

    <div class="ord-stats">
      <div class="ord-stat"><span class="ord-stat-v">{total}</span><span class="ord-stat-l">Orders</span></div>
      <div class="ord-stat"><span class="ord-stat-v">1</span><span class="ord-stat-l">In progress</span></div>
      <div class="ord-stat"><span class="ord-stat-v">{len(hist)}</span><span class="ord-stat-l">Delivered</span></div>
      <div class="ord-stat"><span class="ord-stat-v">{money(spent)}</span><span class="ord-stat-l">Lifetime spent</span></div>
    </div>

    <div class="ord-section">
      <h2 class="ord-h2">In progress</h2>
      {_ord_active_card(active)}
    </div>

    <div class="ord-section">
      <h2 class="ord-h2">Delivered</h2>
      <div class="ord-table">
        <div class="ord-thead" aria-hidden="true">{head}</div>
        <div class="ord-tbody">{rows}</div>
      </div>
    </div>

    <p class="ord-note">{_ico("info", 15, "ico", stroke=True)}
      <span>This order history is a preview. Until an account backend is live, the orders shown are
      example data, priced with the real quote — the same standing as the demo dashboard.</span></p>
  </div>
</section>"""
    return layout(ORDERS_HREF, "Your orders — %s" % D.BRAND,
                  "Your order history: the boost in progress and every one already delivered, "
                  "each with its climb, price and dashboard.",
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

    # The inclusion, stated. The bold name comes from data.py so the strip and
    # the add-on list can never disagree about what it is called; the sentence
    # is page copy, because data.py's note leads with "Always on." for the
    # add-on row — where nothing else says so — and here the strip already does.
    # No zero-cost add-on in data.py, no strip.
    free = next((a for a in D.ADDONS if a["pct"] == 0), None)
    incl = ""
    if free:
        incl = (f'<div class="co-incl">{_ico("seal", 15, "ico", evenodd=True)}'
                f'<span><b>{esc(free["label"])}</b> <span>included — friends see you offline '
                f'for the whole order.</span></span></div>')

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
          <input class="co-input" id="k-email" type="email" required
                 inputmode="email" autocomplete="email" spellcheck="false"
                 placeholder="you@example.com" aria-describedby="k-email-note">
          <p class="co-note" id="k-email-note" data-email-note>Used for the order link and nothing
          else. No marketing unless you tick the box at the end.</p>

          <div class="co-two">
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
            <label class="co-lab" for="k-notes">Anything the booster should know</label>
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
            <span class="co-toggle-t">Email me when my order is claimed and when it's done.
            Nothing else.</span>
          </label>

          <p class="co-err" data-pay-error role="alert" hidden></p>

          <button class="co-cta" type="submit">
            {_ico("lock", 16, "ico", stroke=True)}<span data-btn-label>Place the order</span>
            <span class="co-cta-sep" aria-hidden="true">·</span><span data-sum="total">—</span>
            {_ico("arrow", 16, "ico", stroke=True)}
          </button>

          <p class="co-refund">{_ico("shield", 15, "ico")}<span>Refunded in full until a booster
          claims it</span><span aria-hidden="true">·</span><a href="/guarantee.html">Read the
          guarantee</a></p>

          <div class="co-bar" role="region" aria-label="Live total">
            <span class="co-bar-p">
              <span class="co-was" data-when-discount data-sum="was" hidden></span>
              <span class="co-total" data-sum="total">—</span>
            </span>
            <button class="co-cta" type="submit"><span data-btn-label>Place the order</span></button>
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
              <span class="co-lab">Climb</span>
              <span class="co-val co-climb">
                <span class="co-marks" data-when-service="division" hidden>
                  <span class="ob-mark" data-mark="from"></span>
                  <span class="co-climb-r" data-tiername="from">—</span>
                  {_ico("arrow", 12, "ico co-mark-arrow", stroke=True)}
                  <span class="ob-mark" data-mark="to"></span>
                  <span class="co-climb-r is-to" data-tiername="to">—</span>
                </span>
                <span class="co-climb-t" data-when-service="division" hidden><i aria-hidden="true">·</i><span data-out="mode">—</span></span>
                <span class="co-climb-t" data-when-service="units" data-sum="summary" hidden>—</span>
              </span>
            </div>
            <div class="co-line">
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
              <span class="co-lab">Boost</span><span class="co-val" data-sum="base">—</span>
            </div>
            <div data-addon-lines></div>
            <div class="co-line co-line-off" data-when-discount hidden>
              <span class="co-lab-off">{_ico("tag", 14, "ico")}<span data-sum="discountLabel">—</span></span>
              <span class="co-val co-val-off" data-sum="discount">—</span>
            </div>
          </div>

          {incl}

          <div class="co-up">
            <span class="co-lab">Last chance to add</span>
            {addons_block(money=True, paid_only=True)}
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

          <div class="co-chips">
            <span class="co-tchip">{_ico("shield", 12, "ico")}<span>Money-back until claimed</span></span>
            <span class="co-tchip">{_ico("globe", 12, "ico")}<span>Regional VPN</span></span>
            <span class="co-tchip">{_ico("eye-off", 12, "ico", stroke=True)}<span>Offline appearance</span></span>
          </div>

          <a class="co-back" href="/games/" data-game-link>{_ico("undo", 14, "ico", stroke=True)}<span>Change the order</span></a>
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
      promo: s.promo || '',
      booster: s.booster || '',
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
#  /ops — the analytics console (deliberately NOT part of the shop)
# ══════════════════════════════════════════════════════════════════════════
OPS_TABS = [
    ("overview", "Overview"), ("funnel", "Funnel"), ("configurator", "Configurator"),
    ("journey", "Journey"), ("sessions", "Sessions"), ("accounts", "Accounts"),
    ("acquisition", "Acquisition"), ("friction", "Friction"), ("abandoned", "Abandoned"),
    ("live", "Live"),
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

    ranges = "".join(
        '<button type="button" data-days="%d" aria-pressed="%s">%s</button>'
        % (days, "true" if days == 30 else "false", esc(label))
        for days, label in ((7, "7 days"), (30, "30 days"), (90, "90 days"), (365, "1 year")))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analytics — {esc(D.BRAND)}</title>
<meta name="robots" content="noindex, nofollow, noarchive">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#0a0a0f">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/css/ops.css">
</head>
<body class="ops">

<div class="wrap" data-gate>
  <div class="gate">
    <h2>Analytics</h2>
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

<div class="wrap" data-app hidden>
  <header class="top">
    <h1>Analytics</h1>
    <span class="sub">{esc(D.BRAND)}</span>
    <span class="spacer"></span>
    <span data-meta></span>
    <button class="btn btn-sm live-toggle" type="button" data-live aria-pressed="true"
            title="Auto-refresh the dashboard"><span class="live-dot"></span><span data-live-label>Live</span></button>
    <button class="btn btn-sm" type="button" data-refresh>Refresh</button>
    <button class="btn btn-sm" type="button" data-signout>Sign out</button>
  </header>

  <div class="filters">
    <label for="ops-game">Period</label>
    <span class="seg" data-range>{ranges}</span>
    <select class="field" id="ops-game" data-game aria-label="Filter by game">
      <option value="">All games</option>
    </select>
  </div>

  <div class="banner synthetic" data-synthetic hidden></div>

  <nav class="tabs" role="tablist" aria-label="Dashboard sections">{tabs}</nav>

  <div data-panels></div>
</div>

<script src="/assets/js/ops.js"></script>
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
        "tiercolors": {g["name"]: D.tier_colors(g) for g in D.GAMES},
        "factors": {g["name"]: g["factor"] for g in D.GAMES},
        "prices": {g["name"]: g["prices"] for g in D.GAMES if g.get("prices")},
        "services": {g["name"]: g["services"] for g in D.GAMES},
        "slugs": {g["name"]: g["slug"] for g in D.GAMES},
        "regions": {g["name"]: g["regions"] for g in D.GAMES},
        "addons": D.ADDONS,
        "promos": D.PROMOS,
        "boostersFree": D.STATS["free_now"],
        # handle → the one game that booster covers. The client validates
        # ?booster=<handle> against this before showing a name or attaching it
        # to an order: a query string is untrusted, and "Ordering with
        # <anything>" is a line the page would otherwise print for free.
        "boosters": {b["handle"]: BY_SLUG[b["slug"]]["name"]
                     for b in D.BOOSTERS if b["slug"] in BY_SLUG},
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
    pages += [("/legal/%s.html" % s, page_legal(s)) for s in LEGAL]
    pages += [("/games/%s.html" % g["slug"], page_game(g)) for g in D.GAMES]

    for rel, html in pages:
        write(rel, html)

    # /orders is account-scoped placeholder history reached only from the
    # account menu — kept out of search alongside the pay flow, not a page to
    # rank. It stays crawlable (no robots block) but unadvertised.
    urls = ["/"] + [r for r, _ in pages if r not in
                    ("/index.html", "/404.html", "/checkout.html", "/checkout/success.html",
                     ORDERS_HREF)]
    urls = [u.replace("/index.html", "/") for u in urls]
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
