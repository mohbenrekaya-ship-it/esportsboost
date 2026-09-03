# -*- coding: utf-8 -*-
"""Resolve a visitor's country without ever looking at their IP address.

The analytics schema is deliberately anonymous (see analytics.py), which rules
out the usual answer — sending the visitor's IP to a geolocation service. Three
signals are used instead, best first:

1. **The edge header.** Vercel attaches `x-vercel-ip-country` to every request
   at the CDN. The IP never reaches this code; only the two-letter result does.
   Accurate, free, and the only one available in production.
2. **The browser's IANA timezone** (`Europe/Paris`), which the browser hands over
   without any lookup. Nearly as good as IP for country, and the only signal
   that works in local development. Mapped below.
3. **The locale's region subtag** (`fr-FR` → FR). Weakest — it says what
   language the interface is in, not where the person is — so it is the last
   resort, and only when it carries an explicit region.

The table covers the zones real traffic actually arrives from. An unmapped zone
falls through to the locale rather than guessing, and an unresolved country is
stored as empty rather than as a wrong one.
"""

# IANA timezone → ISO 3166-1 alpha-2. Multi-zone countries list their zones;
# single-zone countries need only the canonical name.
TZ_COUNTRY = {
    # ── Europe ──────────────────────────────────────────────────────────
    "Europe/London": "GB", "Europe/Dublin": "IE", "Europe/Lisbon": "PT",
    "Europe/Madrid": "ES", "Atlantic/Canary": "ES", "Europe/Paris": "FR",
    "Europe/Brussels": "BE", "Europe/Amsterdam": "NL", "Europe/Luxembourg": "LU",
    "Europe/Berlin": "DE", "Europe/Zurich": "CH", "Europe/Vienna": "AT",
    "Europe/Rome": "IT", "Europe/Malta": "MT", "Europe/Copenhagen": "DK",
    "Europe/Oslo": "NO", "Europe/Stockholm": "SE", "Europe/Helsinki": "FI",
    "Europe/Tallinn": "EE", "Europe/Riga": "LV", "Europe/Vilnius": "LT",
    "Europe/Warsaw": "PL", "Europe/Prague": "CZ", "Europe/Bratislava": "SK",
    "Europe/Budapest": "HU", "Europe/Ljubljana": "SI", "Europe/Zagreb": "HR",
    "Europe/Belgrade": "RS", "Europe/Sarajevo": "BA", "Europe/Skopje": "MK",
    "Europe/Tirane": "AL", "Europe/Podgorica": "ME", "Europe/Bucharest": "RO",
    "Europe/Sofia": "BG", "Europe/Athens": "GR", "Europe/Istanbul": "TR",
    "Europe/Kiev": "UA", "Europe/Kyiv": "UA", "Europe/Minsk": "BY",
    "Europe/Chisinau": "MD", "Europe/Moscow": "RU", "Europe/Samara": "RU",
    "Europe/Kaliningrad": "RU", "Asia/Yekaterinburg": "RU",
    "Asia/Novosibirsk": "RU", "Asia/Krasnoyarsk": "RU", "Asia/Vladivostok": "RU",
    "Europe/Reykjavik": "IS", "Atlantic/Reykjavik": "IS",
    "Europe/Andorra": "AD", "Europe/Monaco": "MC", "Europe/San_Marino": "SM",
    "Europe/Nicosia": "CY", "Asia/Nicosia": "CY",

    # ── Americas ────────────────────────────────────────────────────────
    "America/New_York": "US", "America/Detroit": "US", "America/Chicago": "US",
    "America/Denver": "US", "America/Phoenix": "US", "America/Los_Angeles": "US",
    "America/Anchorage": "US", "Pacific/Honolulu": "US", "America/Boise": "US",
    "America/Indiana/Indianapolis": "US", "America/Kentucky/Louisville": "US",
    "America/Toronto": "CA", "America/Vancouver": "CA", "America/Edmonton": "CA",
    "America/Winnipeg": "CA", "America/Halifax": "CA", "America/St_Johns": "CA",
    "America/Mexico_City": "MX", "America/Tijuana": "MX", "America/Monterrey": "MX",
    "America/Cancun": "MX", "America/Guatemala": "GT", "America/Costa_Rica": "CR",
    "America/Panama": "PA", "America/Havana": "CU", "America/Santo_Domingo": "DO",
    "America/Puerto_Rico": "PR", "America/Jamaica": "JM",
    "America/Bogota": "CO", "America/Caracas": "VE", "America/Lima": "PE",
    "America/La_Paz": "BO", "America/Guayaquil": "EC", "America/Asuncion": "PY",
    "America/Montevideo": "UY", "America/Santiago": "CL",
    "America/Argentina/Buenos_Aires": "AR", "America/Argentina/Cordoba": "AR",
    "America/Sao_Paulo": "BR", "America/Bahia": "BR", "America/Fortaleza": "BR",
    "America/Recife": "BR", "America/Manaus": "BR", "America/Belem": "BR",
    "America/Porto_Velho": "BR", "America/Cuiaba": "BR",

    # ── Asia & Middle East ──────────────────────────────────────────────
    "Asia/Seoul": "KR", "Asia/Pyongyang": "KP", "Asia/Tokyo": "JP",
    "Asia/Shanghai": "CN", "Asia/Chongqing": "CN", "Asia/Urumqi": "CN",
    "Asia/Hong_Kong": "HK", "Asia/Macau": "MO", "Asia/Taipei": "TW",
    "Asia/Singapore": "SG", "Asia/Kuala_Lumpur": "MY", "Asia/Jakarta": "ID",
    "Asia/Makassar": "ID", "Asia/Jayapura": "ID", "Asia/Manila": "PH",
    "Asia/Bangkok": "TH", "Asia/Ho_Chi_Minh": "VN", "Asia/Saigon": "VN",
    "Asia/Phnom_Penh": "KH", "Asia/Vientiane": "LA", "Asia/Yangon": "MM",
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Colombo": "LK",
    "Asia/Kathmandu": "NP", "Asia/Dhaka": "BD", "Asia/Karachi": "PK",
    "Asia/Kabul": "AF", "Asia/Tehran": "IR", "Asia/Baghdad": "IQ",
    "Asia/Riyadh": "SA", "Asia/Dubai": "AE", "Asia/Qatar": "QA",
    "Asia/Kuwait": "KW", "Asia/Bahrain": "BH", "Asia/Muscat": "OM",
    "Asia/Amman": "JO", "Asia/Beirut": "LB", "Asia/Damascus": "SY",
    "Asia/Jerusalem": "IL", "Asia/Tel_Aviv": "IL", "Asia/Gaza": "PS",
    "Asia/Yerevan": "AM", "Asia/Baku": "AZ", "Asia/Tbilisi": "GE",
    "Asia/Almaty": "KZ", "Asia/Tashkent": "UZ", "Asia/Bishkek": "KG",
    "Asia/Dushanbe": "TJ", "Asia/Ashgabat": "TM", "Asia/Ulaanbaatar": "MN",

    # ── Africa ──────────────────────────────────────────────────────────
    "Africa/Casablanca": "MA", "Africa/Algiers": "DZ", "Africa/Tunis": "TN",
    "Africa/Tripoli": "LY", "Africa/Cairo": "EG", "Africa/Khartoum": "SD",
    "Africa/Lagos": "NG", "Africa/Accra": "GH", "Africa/Abidjan": "CI",
    "Africa/Dakar": "SN", "Africa/Nairobi": "KE", "Africa/Kampala": "UG",
    "Africa/Dar_es_Salaam": "TZ", "Africa/Addis_Ababa": "ET",
    "Africa/Johannesburg": "ZA", "Africa/Harare": "ZW", "Africa/Lusaka": "ZM",
    "Africa/Luanda": "AO", "Africa/Kinshasa": "CD", "Africa/Maputo": "MZ",

    # ── Oceania ─────────────────────────────────────────────────────────
    "Australia/Sydney": "AU", "Australia/Melbourne": "AU", "Australia/Brisbane": "AU",
    "Australia/Perth": "AU", "Australia/Adelaide": "AU", "Australia/Hobart": "AU",
    "Australia/Darwin": "AU", "Pacific/Auckland": "NZ", "Pacific/Fiji": "FJ",
    "Pacific/Port_Moresby": "PG", "Pacific/Guam": "GU",
}


# ══════════════════════════════════════════════════════════════════════════
#  which of the two server estates a visitor belongs to
# ══════════════════════════════════════════════════════════════════════════
# The order form has to open on SOME server, and until now it opened on North
# America for everyone — a European buyer's first act on the page was correcting
# it. The choice is deliberately binary, NA or EU, because that is where the
# roster actually is: 35 boosters on NA and 47 across the EU shards, against two
# on OCE and one apiece on LATAM, SEA and KR. Defaulting someone onto a shard
# one person covers is a slower claim and an emptier board, so the two big
# estates are the only defaults; every other server stays one tap away in the
# same control.
#
# North America here is the continent — Central America and the Caribbean
# included. They are tens of milliseconds from the NA shard and a third of a
# world from Frankfurt, so grouping them with Europe to satisfy a tidy
# "north/south" split would be the one grouping that is wrong on the only
# measure that matters to a player.
NA_COUNTRIES = {
    "US", "CA", "MX", "GT", "BZ", "SV", "HN", "NI", "CR", "PA",
    "CU", "DO", "HT", "JM", "PR", "BS", "TT", "BB",
}

# South America is listed rather than inferred, because the client classifies an
# `America/…` timezone as North American UNLESS it appears here — that way a zone
# neither table carries (America/Regina, America/Whitehorse) lands on NA, which
# is right far more often than not for that prefix.
SA_COUNTRIES = {"BR", "AR", "CL", "CO", "PE", "VE", "EC", "BO",
                "PY", "UY", "GY", "SR", "GF"}


# ── which money a market is quoted in ──────────────────────────────────────
# The business rule, in the words it was set in: the United States in dollars,
# Canada in Canadian dollars, the UK and the crown dependencies in sterling, the
# rest of Europe in euros. Everywhere else keeps the dollar, which is what an
# international price is quoted in — there is no rate for anything else, and a
# currency the site cannot charge in must never be displayed (see
# test_fx_rate_mirror, which asserts every code named here is in CHARGE_RATES).
#
# Only the countries whose answer is NOT the fallback need an entry; US and MX
# are listed anyway because being explicit is what stops them falling through to
# the language map, where a American reading the site in French would be quoted
# euros for a North American order.
CUR_COUNTRIES = {
    "GB": "GBP", "IM": "GBP", "JE": "GBP", "GG": "GBP",
    "US": "USD", "MX": "USD",
}

# Europe, taken from the timezone table rather than listed by hand, so a country
# added there joins the euro default without a second edit. Deliberately the
# whole continent and not the eurozone: the rule is "the rest of Europe", these
# visitors are all on the EU shard, and the site has no rate for zloty, krona or
# forint — a Pole quoted in euros is being quoted a currency we can actually
# charge, which a Pole quoted in złoty would not be.
EU_COUNTRIES = frozenset(
    c for z, c in TZ_COUNTRY.items() if z.startswith("Europe/")
)


# ══════════════════════════════════════════════════════════════════════════
#  which language a country's traffic is shown in by default
# ══════════════════════════════════════════════════════════════════════════
# The site ships three languages and opened in English for every visitor on
# earth, so a French buyer's first act on the page was correcting the one
# control that decides whether they can read it. This is the language half of
# `currency_for()`, and it is a country map for the same reason: a location is
# a market, where a browser's language list is only what the machine is set to.
#
# ⚠ It is deliberately NARROW — one entry, France. Every country listed here is
# a claim that our translation of that language is the one its readers expect,
# and only French and German are written at all (see the register-and-voice
# rules in CLAUDE.md). Adding Germany, Belgium, Austria or Switzerland is one
# line each; it is a business call, not a technical one, because a Belgian
# quoted in the French of France and a Swiss reader handed `du` are both
# decisions somebody owns.
#
# It sets a DEFAULT only. A visitor who opens the language dropdown pins their
# pick, and that pin outranks this forever after — same contract as the
# currency's `curPinned` and the server's `regionPicked`.
LANG_COUNTRIES = {
    "FR": "fr",
}


def language_for(code):
    """The language a country's traffic is shown in by default, or "" when it
    is one we have no opinion about (which the caller reads as English)."""
    return LANG_COUNTRIES.get(str(code or "").strip().upper(), "")


def currency_for(code):
    """The currency a country's traffic is quoted and charged in by default."""
    code = str(code or "").strip().upper()
    if code in CUR_COUNTRIES:
        return CUR_COUNTRIES[code]
    return "EUR" if code in EU_COUNTRIES else "USD"


def server_area(code):
    """"NA" or "EU" for a country code — the estate its traffic should default
    to. Anything we cannot place (including an empty code) resolves to EU: it is
    the larger of the two rosters, and it is where the non-American traffic this
    falls through for actually is."""
    return "NA" if str(code or "").strip().upper() in NA_COUNTRIES else "EU"


def _from_locale(lang):
    """`fr-FR` → FR. Only an explicit two-letter region subtag counts; a bare
    `fr` says nothing about location and returns nothing."""
    for part in str(lang or "").replace("_", "-").split("-")[1:]:
        if len(part) == 2 and part.isalpha():
            return part.upper()
    return ""


def country(header_country="", tz="", lang=""):
    """Best available country code, or "" when nothing is trustworthy."""
    code = str(header_country or "").strip().upper()
    if len(code) == 2 and code.isalpha():
        return code
    hit = TZ_COUNTRY.get(str(tz or "").strip())
    if hit:
        return hit
    return _from_locale(lang)


def source(header_country="", tz="", lang=""):
    """Which signal answered — surfaced in the dashboard so a country is never
    read as more precise than it is."""
    code = str(header_country or "").strip().upper()
    if len(code) == 2 and code.isalpha():
        return "edge"
    if TZ_COUNTRY.get(str(tz or "").strip()):
        return "timezone"
    return "locale" if _from_locale(lang) else ""
