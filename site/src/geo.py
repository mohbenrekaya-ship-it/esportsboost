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
