/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — client-side currency + language switcher
   ---------------------------------------------------------------------------
   Loaded BEFORE app.js so window.esbMoney / window.ESB_LOCALE exist when the
   runtime takes its first quote. Two independent dimensions, both persisted:

     currency : USD | EUR | GBP  (both display AND the Stripe charge — the
                             checkout POSTs this and payments.py charges in it at
                             the same fixed ESB_RATES rate, so the Stripe page
                             matches the button. Amount is still recomputed
                             server-side.)
     language : en | fr | de

   Language is applied by walking the DOM and swapping any text node / attribute
   whose English source appears in ESB_I18N. Strings not in the dictionary fall
   back to English, so nothing ever breaks — it just stays untranslated.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var LKEY = "esb.locale.v1";

  /* ── where the visitor is ─────────────────────────────────────────────────
     ONE resolver, and it lives here rather than in app.js only because of load
     order: data.js → i18n.js → app.js, and the currency below has to be settled
     before ESB_LOCALE is published. app.js reads `area()` off window.esbGeo for
     the order form's default server, so the two geo-derived defaults on the site
     cannot disagree — which they briefly did, quoting an American living in
     Berlin in dollars off his locale while sending him to the EU shard off his
     timezone.

     The signals are geo.py's, in geo.py's order, minus the edge header a static
     page cannot read: the browser's IANA timezone first, the locale's region
     subtag second. No request, no permission prompt, no PII —
     navigator.geolocation would need all three for a worse answer than either
     of these defaults needs. */
  var GEO = (window.ESB_DATA || {}).geo || {};
  var SA_ZONES = {}, NA_COUNTRIES = {}, EU_COUNTRIES = {};
  (GEO.saZones || []).forEach(function (z) { SA_ZONES[z] = 1; });
  (GEO.naCountries || []).forEach(function (c) { NA_COUNTRIES[c] = 1; });
  (GEO.euCountries || []).forEach(function (c) { EU_COUNTRIES[c] = 1; });
  var ZONE_CUR = GEO.zoneCur || {};
  var REGION_CUR = GEO.curCountries || {};
  var ZONE_LANG = GEO.langZones || {};
  var REGION_LANG = GEO.langCountries || {};

  function zone() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }
    catch (e) { return ""; }
  }

  /* The country Vercel's edge resolved from the request IP, handed down by
     middleware.js as a plain cookie. This is geo.py's FIRST choice — the same
     `x-vercel-ip-country` the analytics store records — and the only signal here
     that follows the connection rather than the device, which is what makes it
     the one a VPN, a roaming SIM or a traveller's laptop gets right.

     Everything below is a fallback for when it is absent, which is every local
     build, any non-Vercel host, and the fraction of requests the edge cannot
     place. That is deliberate: this whole block is INERT without the cookie, so
     the client can ship ahead of the middleware and behave exactly as it did. */
  function cookieCountry() {
    try {
      var m = /(?:^|;\s*)esb_geo=([A-Za-z]{2})(?:\s*;|\s*$)/.exec(document.cookie || "");
      return m ? m[1].toUpperCase() : "";
    } catch (e) { return ""; }
  }

  /* `fr-FR` → FR. Only an explicit region subtag counts; a bare `fr` says
     nothing about location. Same rule as geo.py's _from_locale(). */
  function uiRegion() {
    try {
      var tags = navigator.languages && navigator.languages.length
        ? navigator.languages : [navigator.language];
      for (var i = 0; i < tags.length; i++) {
        var m = /^[a-z]{2,3}[-_](?:[A-Za-z]{4}[-_])?([A-Za-z]{2})\b/.exec(tags[i] || "");
        if (m) return m[1].toUpperCase();
      }
    } catch (e) {}
    return "";
  }

  /* "NA" or "EU" — the two server estates, read by app.js. `America/…` is North
     America unless the South-America exception list says otherwise, so a zone
     neither table carries (America/Regina) still lands on the right side of the
     Atlantic. See geo.server_area() for why the choice is binary. */
  function area() {
    var cc = cookieCountry();
    if (cc) return NA_COUNTRIES[cc] ? "NA" : "EU";
    var tz = zone();
    if (tz) {
      if (tz.indexOf("America/") === 0) return SA_ZONES[tz] ? "EU" : "NA";
      if (tz === "Pacific/Honolulu") return "NA";
      return "EU";
    }
    return NA_COUNTRIES[uiRegion()] ? "NA" : "EU";
  }

  window.esbGeo = { zone: zone, region: uiRegion, area: area, country: cookieCountry };

  /* ── a location implies a currency; failing that, a language does ─────────
     The markets as the business set them (geo.currency_for()): the United
     States in dollars, Canada in Canadian dollars, the UK and the crown
     dependencies in sterling, the rest of Europe in euros, everywhere else the
     dollar — which is what an international price is quoted in, and the only
     other thing there is a rate for.

     A page reading "à partir de $5" over a euro price card is the same
     one-set-of-numbers failure a bare `$5` in the chrome is, which is what the
     language map below was for. It survives as the LAST resort, because a
     language is a poor proxy for a market — a good one for `fr`/`de`, a useless
     one for English, which is read in London, Toronto and Los Angeles alike.

     All of it sets a DEFAULT only: a visitor who opens the dropdown pins their
     pick, and `curPinned` outranks every line of this forever after. */
  var LANG_CUR = { fr: "EUR", de: "EUR" };

  function defaultCurrency(lang) {
    var tz = zone(), reg = uiRegion();
    // The order matters, and every step earns its place:
    //  0. The edge's own answer, when there is one. This branch is the exact
    //     JS twin of geo.currency_for() — keep the two in step.
    var cc = cookieCountry();
    if (cc) {
      if (REGION_CUR[cc]) return REGION_CUR[cc];
      return EU_COUNTRIES[cc] ? "EUR" : "USD";
    }
    //  1. A zone we can place exactly. The only signal that separates Toronto
    //     from New York, or London from Dublin.
    if (tz && ZONE_CUR[tz]) return ZONE_CUR[tz];
    //  2. A European zone. Sterling is already answered above, so everything
    //     still here is the euro rule — and it must beat the locale, or a
    //     visitor in Paris whose browser is set to en-GB is quoted in pounds.
    if (tz && (tz.indexOf("Europe/") === 0 || tz.indexOf("Atlantic/") === 0)) return "EUR";
    //  3. The locale's own country, but only for the hard country→currency
    //     facts. This is what tells a browser in Regina it is Canadian when the
    //     zone table has never heard of America/Regina.
    if (reg && REGION_CUR[reg]) return REGION_CUR[reg];
    //  4. An American zone. AFTER the step above, so Toronto-without-a-table-
    //     entry can still reach CAD; but BEFORE the European locale list, so an
    //     American with a French browser is quoted for the market he is in.
    //     The whole continent is dollars: North America by the rule, South
    //     America because there is no rate for a real and the dollar is what an
    //     international price is quoted in.
    if (tz && (tz.indexOf("America/") === 0 || tz === "Pacific/Honolulu")) return "USD";
    //  5. A European locale, for a browser that reported no usable zone at all.
    if (reg && EU_COUNTRIES[reg]) return "EUR";
    //  6. And finally the language, the weakest proxy of the lot.
    return LANG_CUR[lang] || "USD";
  }

  /* ── a location implies a language too ────────────────────────────────────
     The site shipped in English to every visitor on earth, so a French buyer's
     first act on the page was correcting the one control that decides whether
     they can read it. This is `defaultCurrency()`'s twin and it reads the same
     three signals in the same order, against geo.LANG_COUNTRIES rather than
     the currency tables:

       0. the edge's own country, from the `esb_geo` cookie — the only signal
          that follows the CONNECTION, so the one a VPN or a roaming SIM gets
          right;
       1. the browser's IANA timezone, which says where the machine IS;
       2. the locale's region subtag, for a browser that reports no zone.

     Deliberately NOT the browser's language list. `navigator.language` says
     what the machine is set to, which is English on a great many French
     machines and is exactly the reason the site was in English for them. The
     business's rule is the location, and the dropdown is one tap away.

     A DEFAULT only: a visitor who picks a language pins it (`langPinned`) and
     the pin wins forever after — same contract as `curPinned`. */
  function defaultLang() {
    var cc = cookieCountry();
    if (cc) return REGION_LANG[cc] || "en";
    var tz = zone();
    if (tz && ZONE_LANG[tz]) return ZONE_LANG[tz];
    // A zone we could not place cannot fall through to the locale — a French
    // browser in Montreal or Brussels would be read as France. Only a browser
    // with no usable zone at all gets the region subtag.
    if (tz) return "en";
    var reg = uiRegion();
    return (reg && REGION_LANG[reg]) || "en";
  }

  /* ── the currencies, and the rate each is charged at ──────────────────────
     Fixed FX rate for both the displayed price AND the Stripe charge. The amount
     is recomputed server-side (pricing.py) in USD, then converted to the picked
     currency at THIS rate for the charge — pricing.CHARGE_RATES mirrors this map
     and test_pricing.py asserts they hold the same currencies at the same rates,
     so change one, change the other, or the Stripe page won't match the button.
     It doubles as the allowlist: a currency we have no rate for is one we cannot
     charge, so a stored or hand-typed code that isn't a key here is discarded. */
  var RATES = window.ESB_RATES = { USD: 1, EUR: 0.92, GBP: 0.79 };

  /* ── persisted locale, read synchronously so app.js sees it ───────────── */
  var locale = { lang: "en", currency: "USD", curPinned: false, langPinned: false };
  try {
    var raw = localStorage.getItem(LKEY);
    if (raw) {
      var s = JSON.parse(raw);
      if (s && (s.lang === "en" || s.lang === "fr" || s.lang === "de")) locale.lang = s.lang;
      if (s && RATES[s.currency]) locale.currency = s.currency;
      // Same migration the currency makes below, and for the same reason: under
      // the old code English was the default for every visitor in every region,
      // so a stored "en" is not evidence of a choice and a returning French
      // visitor — the whole case this fixes — would be read as having picked it.
      // Only a stored non-English can have come from a click on the dropdown.
      locale.langPinned = (s && typeof s.langPinned === "boolean") ? s.langPinned
        : !!(s && s.lang && s.lang !== "en");
      // Records written before this default existed carry no flag, and the test
      // is NOT "does it disagree with the language" — under the old code USD was
      // the default in every language and in every region, so a stored USD tells
      // us nothing and a returning French (or British) visitor — the whole case
      // this fixes — would be read as having chosen dollars and left on them.
      // Only a stored non-USD can have been picked deliberately, so only that
      // migrates in as pinned.
      locale.curPinned = (s && typeof s.curPinned === "boolean") ? s.curPinned
        : !!(s && s.currency && s.currency !== "USD");
    }
  } catch (e) {}
  // Resolved here, not in init(), because app.js reads ESB_LOCALE.currency and
  // .lang on its first quote — deriving either later would paint the page in
  // English dollars and swap it. The language is settled FIRST, so the currency
  // ladder's last resort (LANG_CUR) reads the language this visitor will
  // actually be shown rather than the one they were about to stop being on.
  if (!locale.langPinned) locale.lang = defaultLang();
  if (!locale.curPinned) locale.currency = defaultCurrency(locale.lang);
  window.ESB_LOCALE = locale;

  /* ── currency ─────────────────────────────────────────────────────────── */
  var LOCALE_TAG = { en: "en-US", fr: "fr-FR", de: "de-DE" };
  // The euro's symbol placement is language-specific — "€72" for an English
  // reader, "72 €" for a French or German one — so EUR follows the language.
  // The rest are pinned to a tag of their own instead of following the reader:
  // the dollar and the pound are prefix marks wherever they are read, a French
  // formatter renders GBP as "72,00 £GB", and CAD is the one that actually
  // matters — Canada's own en-CA formats it as a bare "$72", identical to USD,
  // so a Canadian could not tell which currency the page was quoting. en-US
  // gives it a distinct mark. Never move CAD to en-CA or fr-CA to "localise" it.
  var CUR_TAG = { USD: "en-US", GBP: "en-GB" };
  var EUR_TAG = { en: "en-IE", fr: "fr-FR", de: "de-DE" };

  /* A currency whose mark we set ourselves rather than take from the formatter.
     CLDR's en-US symbol for CAD is "CA$"; the site shows "C$" — shorter, and on
     a 375px phone the money line is the width that decides whether the save pill
     keeps its row. This is the ONLY place the site's own mark for a currency is
     decided, and it has to agree with the three server-side surfaces that print
     a charged amount back to a human — build.py's CURRENCIES icon, ops.js
     CUR_SYM and payments.CURRENCY_SIGNS. `test_currency_signs()` asserts all
     four, because a page quoting "C$319" over a receipt saying "CA$319" is the
     same one-set-of-numbers failure as a bare "$5" in the chrome. */
  // Empty today. It exists for a currency whose CLDR symbol is not the one the
  // site shows — CAD lived here as "C$" against CLDR's "CA$" until Canada was
  // folded into the dollar rule. A mark added here must also be added to
  // build.py's CURRENCIES, payments.CURRENCY_SIGNS and ops.js's CUR_SYM;
  // test_currency_signs() asserts all four agree.
  var CUR_MARK = {};
  var _fmtCache = {};
  function formatter(cur, lang, cents) {
    var tag = cur === "EUR" ? (EUR_TAG[lang] || "en-IE") : (CUR_TAG[cur] || "en-US");
    var key = cur + tag + (cents ? "2" : "0");
    if (!_fmtCache[key]) {
      _fmtCache[key] = new Intl.NumberFormat(tag, {
        style: "currency", currency: cur,
        minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0
      });
    }
    return _fmtCache[key];
  }

  // Currency-aware money. app.js delegates its usd() here.
  window.esbMoney = function (n, cents, fixed) {
    // ⚠ `fixed` is the accounts rule: that figure is the same DIGITS in every
    // currency (€24.90 / £24.90 / $24.90), so no rate is applied. Mirrors
    // pricing.charge_for()'s own `fixed` — the price shown and the price
    // charged have to agree, and they only do if both skip the multiply.
    var cur = locale.currency, rate = fixed ? 1 : (window.ESB_RATES[cur] || 1);
    var f = formatter(cur, locale.lang, cents), v = n * rate;
    var mark = CUR_MARK[cur];
    if (!mark) return f.format(v);
    // Rewrite the currency PART, not the finished string. Where the mark sits is
    // the formatter's business — it leads in en-US and trails in fr-FR — and a
    // string replace would have to know that, as well as never colliding with a
    // digit group that happened to spell the symbol.
    return f.formatToParts(v).map(function (part) {
      return part.type === "currency" ? mark : part.value;
    }).join("");
  };

  /* ── translation lookup, used by app.js for its dynamic strings ───────── */
  window.esbT = function (str) {
    if (locale.lang === "en") return str;
    var d = ESB_I18N[locale.lang];
    if (d && d[str] !== undefined) return d[str];
    // Same {} patterns the DOM walk uses, so a runtime string app.js builds
    // around a game name resolves the same way its server-rendered twin does.
    var pat = patTranslate(str, locale.lang);
    return pat !== null ? pat : str;
  };

  /* ── dictionary (English source → fr / de) ────────────────────────────── */
  var ESB_I18N = window.ESB_I18N = {
    fr: {
      /* dynamic fragments emitted by app.js */
      "Solo": "Solo",
      "Duo queue": "Duo",
      "net win": "victoire nette",
      "net wins": "victoires nettes",
      "placement game": "match de placement",
      "placement games": "matchs de placement",
      "about 1 day": "environ 1 jour",
      "days": "jours",
      "Target must sit above your current rank": "La cible doit être au-dessus de ton rang actuel",
      "Pick a target above your current rank": "Choisis une cible au-dessus de ton rang actuel",
      "YOU": "VOUS",
      "TARGET": "CIBLE",
      "YOU · TGT": "VOUS · CIBLE",
      "Tap the rank you’re on now": "Touche le rang où tu es",
      "Now tap the rank you want to reach": "Touche maintenant le rang que tu vises",
      "No divisions": "Aucune division",
      "None": "Aucune",

      /* site header — design_handoff_site_header */
      "Currency": "Devise",
      "Language": "Langue",
      "Summer sale": "Promo d’été",
      "ends 31 Aug": "jusqu’au 31 août",
      "Copied": "Copié",
      "verified boosters": "boosters vérifiés",
      "Games": "Jeux",
      "Live": "En direct",
      "Boosters": "Boosters",
      "Safety": "Sécurité",
      "Reviews": "Avis",
      "Log in": "Connexion",
      "Menu": "Menu",
      "Skip to content": "Aller au contenu",
      /* mega menus */
      "Pick your game": "Choisis ton jeu",
      "Who plays your order": "Qui joue ta commande",
      "Before you buy": "Avant d’acheter",
      "Right now": "En ce moment",
      "Top": "N° 1",
      "Hiring": "Recrute",
      "are live too": "sont aussi en ligne",
      "boosters on shift": "boosters en ligne",
      "Median claim": "Prise en charge médiane",
      "Watch orders land live": "Voir les commandes tomber en direct",
      "All nine games": "Les neuf jeux",
      "Browse the roster": "Voir le roster",
      "verified boosters, one game each": "boosters vérifiés, un jeu chacun",
      "Hire a specific booster": "Choisir un booster précis",
      "Name one at checkout, no extra fee": "Nomme-le au paiement, sans supplément",
      "How we verify": "Comment nous vérifions",
      "Rank proof, trial orders, review floor": "Rang prouvé, commandes d’essai, note minimale",
      "Master+ with a clean account": "Master+ et un compte sans sanction",
      "Read their reviews": "Lire leurs avis",
      "reviews, filterable by game and score": "avis, filtrables par jeu et par note",
      "The guarantee": "La garantie",
      "Refunded until a booster claims it": "Remboursé tant qu’aucun booster n’a pris la commande",
      "Account safety": "Sécurité du compte",
      "Regional VPN, your hours, offline": "VPN régional, tes horaires, hors ligne",
      "What we never do": "Ce que nous ne faisons jamais",
      "No bots, no password changes": "Aucun bot, aucun changement de mot de passe",
      "Pro-rated, in five business days": "Au prorata, sous cinq jours ouvrés",
      "FAQ": "FAQ",
      "The six questions support gets most": "Les six questions les plus posées au support",
      "Track an order": "Suivre une commande",
      "No password — the link is the login": "Sans mot de passe — le lien suffit",
      /* auth panel */
      "Create account": "Créer un compte",
      "Create your account": "Crée ton compte",
      "An account is optional. It keeps every order, thread and saved configuration in one place — you can still buy as a guest.":
        "Le compte est facultatif. Il rassemble tes commandes, tes échanges et tes configurations au même endroit — tu peux très bien acheter en invité.",
      "Bought as a guest? You don't need an account. Use the link we emailed you, or resend it from the order tracker.":
        "Tu as acheté en invité ? Pas besoin de compte. Utilise le lien reçu par e-mail, ou fais-le renvoyer depuis le suivi de commande.",
      "Continue with Discord": "Continuer avec Discord",
      "Continue with Google": "Continuer avec Google",
      "Sign up with Discord": "S’inscrire avec Discord",
      "Sign up with Google": "S’inscrire avec Google",
      "or with email": "ou par e-mail",
      "Display name": "Pseudo",
      "What your booster calls you": "Le nom que ton booster verra",
      "Password": "Mot de passe",
      "Your password": "Ton mot de passe",
      "At least 6 characters": "Au moins 6 caractères",
      "Forgot it?": "Oublié ?",
      "Show password": "Afficher le mot de passe",
      "Hide password": "Masquer le mot de passe",
      "Six characters or more. A passphrase beats a symbol soup.":
        "Six caractères minimum. Une phrase de passe vaut mieux qu’une soupe de symboles.",
      "Too short to be worth having.": "Trop court pour servir à quoi que ce soit.",
      "Getting there — add a few more words.": "Ça vient — ajoute encore quelques mots.",
      "Strong enough.": "Assez solide.",
      "I've read the": "J’ai lu les",
      "terms": "conditions",
      "privacy policy": "politique de confidentialité",
      "and the": "et la",
      ", including how boosting relates to each game's rules.":
        ", y compris ce que le boosting implique au regard des règles de chaque jeu.",
      "We'll keep you signed in on this device for 30 days.":
        "Tu restes connecté sur cet appareil pendant 30 jours.",
      "That email and password don't match. Check the address, or reset the password.":
        "Cet e-mail et ce mot de passe ne correspondent pas. Vérifie l’adresse, ou réinitialise le mot de passe.",
      "An account with this email already exists. Log in instead.":
        "Un compte existe déjà avec cet e-mail. Connecte-toi plutôt.",
      "Enter a valid email address.": "Entre une adresse e-mail valide.",
      "Choose a password of at least 6 characters.": "Choisis un mot de passe d’au moins 6 caractères.",
      "Please accept the terms to create your account.": "Accepte les conditions pour créer ton compte.",
      "Enter your password.": "Entre ton mot de passe.",
      "Couldn't reach the server. Check your connection and try again.":
        "Serveur injoignable. Vérifie ta connexion et réessaie.",
      "Couldn't create the account. Try again.": "Impossible de créer le compte. Réessaie.",
      "Sign-in didn't complete. Please try again.": "La connexion n’est pas allée au bout. Réessaie.",
      "That email and password don't match. Check them, or create an account.":
        "Cet e-mail et ce mot de passe ne correspondent pas. Vérifie-les, ou crée un compte.",
      "Social sign-in isn't connected yet. Use your email, or buy as a guest — checkout needs no account.":
        "La connexion Google/Discord n’est pas encore branchée. Utilise ton e-mail, ou achète en invité — le paiement ne demande aucun compte.",
      "This is your store account, never your game login.":
        "C’est ton compte boutique, jamais ton identifiant de jeu.",
      "We never ask for your game password here.": "On ne te demande jamais ton mot de passe de jeu ici.",
      "New here?": "Pas encore inscrit ?",
      "Already have an account?": "Tu as déjà un compte ?",
      "Create an account": "Créer un compte",
      /* account menu */
      "My orders": "Mes commandes",
      "Messages": "Messages",
      "Log out": "Se déconnecter",
      "live": "en cours",
      "Account": "Compte",
      "Your orders": "Tes commandes",
      "Every boost you've ordered \u2014 the one in progress, and the ones already delivered.":
        "Chaque boost que tu as commandé — celui en cours, et ceux déjà livrés.",
      "Signed in as": "Connecté en tant que",
      "You're viewing a sample history.": "Tu consultes un historique d’exemple.",
      "to see your orders here — or track a single order by the link we emailed you. Checkout never needs an account.":
        "pour voir tes commandes ici — ou suis une commande avec le lien reçu par e-mail. Le paiement ne demande jamais de compte.",
      "This order history is a preview. Until an account backend is live, the orders shown are example data, priced with the real quote \u2014 the same standing as the demo dashboard.":
        "Cet historique est un aperçu. Tant qu’il n’y a pas de backend de comptes, les commandes affichées sont des données d’exemple, tarifées avec le vrai devis — au même titre que le tableau de bord de démo.",
      "Track by link": "Suivre via le lien",
      "Orders": "Commandes",
      "Lifetime spent": "Total dépensé",
      "Open dashboard": "Ouvrir le tableau de bord",
      "Status": "Statut",
      "now": "actuel",

      /* footer */
      "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any of their subsidiaries. All trademarks, game titles, logos, and brand names are the property of their respective owners. eSports Boost provides independent gaming services and is not endorsed by or associated with any game publisher.":
        "Nous ne sommes affiliés ni à Riot Games, Inc., ni à Blizzard Entertainment, ni à Valve, ni à aucune de leurs filiales. Toutes les marques, titres de jeux, logos et noms de marque appartiennent à leurs propriétaires respectifs. eSports Boost fournit des services de jeu indépendants et n’est ni approuvé ni associé à un quelconque éditeur de jeux.",
      "Questions? Email us at": "Une question ? Écris-nous à",
      "Follow along": "Nous suivre",
      "games": "jeux",
      "Help center": "Centre d’aide",
      "Legal": "Mentions légales",
      "24/7 Customer Support": "Support client 24/7",
      "Online now": "En ligne",
      "Online Now": "En ligne",
      "Verified Boosters": "boosters vérifiés",
      "Typical reply": "Réponse habituelle en",
      "Need help? Our support team is available anytime to assist you with your orders and questions.":
        "Besoin d’aide ? Notre équipe est là à toute heure pour tes commandes et tes questions.",
      "Let's chat": "Discuter avec nous",
      "Visit help center": "Voir le centre d’aide",
      "Privacy Policy": "Politique de confidentialité",
      "Terms of Service": "Conditions d’utilisation",
      "Refunds & Cancellations": "Remboursements et annulations",
      "Become a booster": "Devenir booster",
      "Discord": "Discord",
      "Card, Apple Pay and Google Pay accepted — payments secured by Stripe":
        "Carte, Apple Pay et Google Pay acceptés — paiements sécurisés par Stripe",
      "© 2026 eSports Boost. All Rights Reserved.": "© 2026 eSports Boost. Tous droits réservés.",

      /* calculator / wizard */
      "Fast Checkout": "Paiement rapide",
      "Live pricing": "Prix en direct",
      "Choose a game": "Choisis un jeu",
      "Your climb": "Ta montée",
      "Rank tier": "Palier de rang",
      "Current division": "Division actuelle",
      "Target division": "Division cible",
      "How it's played": "Mode de jeu",
      /* order card — the "Ladder card" hero on the game pages */
      "Build your boost": "Compose ton boost",
      "of": "sur",
      "boosters free now": "boosters dispo",
      "Add-ons": "Options",
      "to climb": "à monter",
      "division": "division",
      "divisions": "divisions",
      "Cheapest single division": "Division la moins chère",
      "You save": "Tu économises",
      "Save": "Économie",
      "with": "avec",
      "Money-back until a booster is assigned": "Remboursé tant qu’aucun booster n’est assigné",
      "Money back until a booster claims it": "Remboursé tant qu’aucun booster n’a pris la commande",
      "Your hours, offline the whole time": "Tes horaires, hors ligne du début à la fin",
      "Pause any time — it's your account": "Pause quand tu veux — c’est ton compte",
      "Pause it anytime": "Pause quand tu veux",
      "Booster time to claim": "Prise en charge par un booster",
      "Time to claim": "Prise en charge",
      "We handle the rest.": "On s’occupe du reste.",
      "Discreet on your bank statement": "Discret sur ton relevé bancaire",
      "No account needed": "Aucun compte requis",
      "VPN matched to your region": "VPN dans ta région",
      "on Trustpilot": "sur Trustpilot",
      "Delivered in": "Livré en",
      "Boosters free now": "Boosters dispo",
      "Total price": "Prix total",
      "Total, tax included": "Total TTC",
      "Continue": "Continuer",
      "Service": "Service",
      "Division boost": "Boost de division",
      "Net wins": "Victoires nettes",
      "Placements": "Placements",
      "Current rank": "Rang actuel",
      "Target rank": "Rang cible",
      "You are": "Tu es",
      "You want": "Tu vises",
      "Change tier": "Changer de palier",
      "How many net wins": "Combien de victoires nettes",
      "How many placement games": "Combien de matchs de placement",
      "One win fewer": "Une victoire de moins",
      "One win more": "Une victoire de plus",
      "One game fewer": "Un match de moins",
      "One game more": "Un match de plus",
      "Server": "Serveur",
      "Options": "Options",
      "Continue to checkout": "Passer au paiement",
      "No account needed · Money-back until a booster is assigned · VPN matched to your region":
        "Sans compte · Remboursé jusqu’à l’attribution d’un booster · VPN dans ta région",
      "From": "À partir de",
      "from": "à partir de",
      "Configure your boost": "Configure ton boost",
      "Buy LoL accounts": "Acheter des comptes LoL",
      "Continue your order": "Reprends ta commande",

      /* home hero — the utility bar's roster count and the spotlight card.
         Numbers stay outside these nodes (build.py wraps them in <b>/<span>),
         and so does the booster's handle: the card's CTA is "Order with" +
         <b>vantaa</b>, which is why changing data.py's SPOTLIGHT no longer
         needs a new sentence here. The game name is data and stays as
         written, like every other game name on the site. */
      "verified boosters on shift right now": "boosters vérifiés en ligne maintenant",
      "Pick your booster": "Choisis ton booster",
      "This month's #1": "N°1 du mois",
      "Verified": "Vérifié",
      "orders delivered": "commandes livrées",
      "boosts delivered": "boosts livrés",
      "clients": "clients",
      "Clients served": "Clients servis",
      "Clients": "Clients",
      "Included": "Inclus",
      /* The order card's inclusions line — ob_included(). The names beside it
         are already keys above, because the picker used to render the same
         words as checkbox rows. */
      "Included free": "Inclus gratuitement",

      /* add-ons — the labels and notes in data.py's ADDONS, plus the per-game
         name of the picks add-on (`picks` on each game: League picks champions,
         Valorant agents, Rocket League a playlist). Every wording ships in the
         DOM and one is shown, so all of them have to be here. Each note has a
         phone variant beside it for the same reason. */
      /* The free-but-optional row. Its two figures are written by app.js
         through usd()/money() and never pass through here; what does is the
         label, the two notes and the `title` on the struck figure, which is the
         one string that says what that number refers to. ATTRS covers `title`,
         so it is translated with everything else. */
      /* Uppercase, and a SEPARATE key from "Free" above — that one is the
         roster's, where free means *available* ("Libre"). Case-sensitive
         lookup is what keeps the two apart; see addons_block() in build.py. */
      "FREE": "GRATUIT",
      "Watch your booster play": "Regarde ton booster jouer",
      /* Kept SHORT on purpose: an add-on note is one line by rule (a second
         costs ~14px of the card's fold budget), and the note column is 311px.
         The English sentence measures 311px exactly — a longer translation
         wraps and pushes the CTA under the fold on the tighter ladders. */
      "Live screen share. Only site that gives it free.":
        "Partage d’écran en direct. Seul site à l’offrir.",
      "Live screen share, every game.": "Partage d’écran en direct, chaque partie.",
      "What this is worth": "Ce que ça vaut",
      "Priority order": "Commande prioritaire",
      "First in the claim queue, claimed in about 6 minutes.":
        "Première de la file, prise en 6 minutes environ.",
      "First in the claim queue, about 6 minutes.": "Première de la file, 6 minutes environ.",
      "Solo only queue": "File solo uniquement",
      "Your booster plays alone, in ranked only — no parties.":
        "Ton booster joue seul, en classé — jamais en groupe.",
      "Plays alone, ranked only — no parties.": "Joue seul, en classé — jamais en groupe.",
      "Play on your schedule": "Joué à tes horaires",
      "Fixed session times, held for the whole order.": "Horaires fixes, réservés pour toute la commande.",
      "Fixed times, held for the whole order.": "Horaires fixes, réservés pour toute la commande.",
      "Champions & roles": "Champions et rôles",
      "Agents & roles": "Agents et rôles",
      "Heroes & roles": "Héros et rôles",
      "Legends & playstyle": "Légendes et style de jeu",
      "Comps & augments": "Compositions et augments",
      "Roles & maps": "Rôles et cartes",
      "Playlist & playstyle": "Playlist et style de jeu",
      "Champions, agents & roles": "Champions, agents et rôles",
      "Always free. Your booster plays the picks you choose.":
        "Toujours gratuit. Ton booster joue les picks que tu choisis.",
      "You choose the picks they play.": "Tu choisis les picks joués.",
      "Offline appearance": "Apparaître hors ligne",
      "Always on. Friends see you offline for the whole order.":
        "Toujours actif. Tes amis te voient hors ligne toute la commande.",

      /* hero (home) */
      "Verified boosters — since 2019": "Boosters vérifiés — depuis 2019",
      "The rank is yours.": "Le rang est à toi.",
      "The grind isn't.": "Le grind, non.",
      "Your price in 10 seconds. Claimed in about 18 minutes. Refunded in full until it is.":
        "Ton prix en 10 secondes. Pris en charge en 18 minutes environ. Intégralement remboursable jusque-là.",
      "This month's #1 — vantaa": "N°1 du mois — vantaa",
      "Challenger 1042 LP · 78% WR · EUW · 214 orders":
        "Challenger 1042 LP · 78 % WR · EUW · 214 commandes",
      "Top booster of the month, vantaa": "Meilleur booster du mois, vantaa",

      /* marquee */
      "92,400 boosts delivered": "92 400 boosts livrés",
      "4.8 / 5 on Trustpilot — 3,140 reviews": "4,8 / 5 sur Trustpilot — 3 140 avis",
      "Most orders claimed within 18 min": "La plupart des commandes prises en 18 min",
      "3,000 players in the Discord": "3 000 joueurs sur le Discord",
      "100% recovery rate on account reviews": "100 % de comptes récupérés après vérification",

      /* section heads / home */
      "Pick your game.": "Choisis ton jeu.",
      "The price is already on it.": "Le prix est déjà dessus.",
      "Nine games, thirty-seven services, priced per division.":
        "Neuf jeux, trente-sept services, au prix par division.",
      "Services": "Services",
      "Most ordered": "Le plus commandé",
      "Configure": "Configurer",
      "All games": "Tous les jeux",
      "are live too.": "sont aussi en ligne.",
      "Elo boost": "Boost d’elo",
      "Rank boost": "Boost de rang",
      "MMR boost": "Boost de MMR",
      "Unrated wins": "Victoires en non classé",
      "Tournament wins": "Victoires en tournoi",
      "Double-up": "Double-up",
      "Calibration": "Calibrage",
      "Badges": "Badges",
      "Kills": "Kills",
      "Premier rating": "Classement Premier",
      "Faceit levels": "Niveaux Faceit",
      "Wingman": "Wingman",
      "Wins": "Victoires",
      "Duo": "Duo",
      "Coaching": "Coaching",
      "Every service is priced per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Chaque service est facturé à la division et affiché avant toute connexion. Placements, victoires nettes, coaching et duo sur chaque jeu.",
      "Delivered today": "Livré aujourd’hui",
      "Why this doesn't get you banned": "Pourquoi tu ne te fais pas bannir",
      /* 04 Dashboard — the section and the mock inside it. Every figure in the
         mock sits outside these nodes (see dash_mock()), so the words match. */
      "Dashboard": "Tableau de bord",
      "You watch the whole thing": "Tu suis tout du début à la fin",
      "Regional VPN": "VPN régional",
      "Pro-rated refunds": "Remboursements au prorata",
      "Open the demo dashboard": "Voir le tableau de bord de démo",
      "Preview of the order dashboard": "Aperçu du tableau de bord de commande",
      "complete": "terminé",
      "days left": "jours restants",
      "LP across the order": "LP sur toute la commande",
      "LP net": "LP net",
      "RR across the order": "RR sur toute la commande",
      "RR net": "RR net",
      "Competitive": "Compétitif",
      "Order start": "Début de la commande",
      "Now": "Maintenant",
      "Match history": "Historique des parties",
      "K / D / A": "K / D / A",
      "LP": "LP",
      "Order dashboard · live": "Tableau de bord · en direct",
      "Pause": "Pause",
      "Order dashboard — live": "Tableau de bord de commande — en direct",
      "Order tracking dashboard with live match history":
        "Tableau de bord de suivi avec historique en direct",
      "What they said after": "Ce qu’ils en ont dit",
      "Every review is tied to a paid, completed order — nothing incentivised. One per game, across the roster.":
        "Chaque avis est rattaché à une commande payée et livrée — rien n’est offert en échange. Un par jeu, sur tout le roster.",
      "Read all reviews": "Lire tous les avis",
      "Read all on Trustpilot": "Tout lire sur Trustpilot",
      "Verified order": "Commande vérifiée",
      "Page": "Page",
      "Verified orders only": "Commandes vérifiées uniquement",
      "Your climb starts at": "Ta montée commence à",
      "Final at checkout. Refunded in full until a booster claims it, pro-rated after that.":
        "Fixé au paiement. Remboursé intégralement jusqu’à la prise en charge, au prorata ensuite.",
      "Set two ranks and the price is on screen before you sign up. No account, no quote request.":
        "Choisis deux rangs et le prix s’affiche avant toute inscription. Sans compte, sans demande de devis.",
      "Talk to support": "Contacter le support",
      "Your boost": "Ton boost",
      "Change": "Modifier",
      "Queue · Server": "File · Serveur",
      "Money-back guarantee": "Satisfait ou remboursé",

      /* stat band + roster */
      "Boosts delivered": "Boosts livrés",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3 140 avis",
      "Median time to claim": "Délai médian de prise en charge",
      "Players in the Discord": "Joueurs sur le Discord",
      "On shift now —": "En ligne —",
      "in the Discord": "sur le Discord",
      "Free VOD reviews on Sundays, scrim pickups, and the booster application queue.":
        "Analyses VOD gratuites le dimanche, scrims et file de candidatures booster.",
      "Join the server →": "Rejoindre le serveur →",
      "All games →": "Tous les jeux →",
      "more": "de plus",

      /* 02 Live / 03 Safety — the delivery feed, the rail and the safety proof.
         Numbers sit outside these nodes (<b>34</b> boosters), so the sentence
         still matches whole. "min ago" is shared with the track page. */
      "Updates as orders close": "Mis à jour dès qu’une commande est livrée",
      "Delivered": "Livré",
      "hr ago": "h",
      "d ago": "j",
      "orders closed in the last 24 hours": "commandes livrées ces 24 dernières heures",
      "All": "Tous les",
      "win rate": "de winrate",
      "Free": "Dispo",
      /* Availability comes off BOOSTERS[].queue — the status pill and the
         roster table's Queue column render the same strings. */
      "free": "dispo",
      "1 order": "1 commande",
      "2 orders": "2 commandes",
      "Free to join": "Gratuit",
      "Join the server": "Rejoindre le serveur",
      "Client satisfaction rate": "Taux de satisfaction client",
      "Your sensitivity and crosshair": "Ta sensibilité et ton viseur",
      "Played in your normal hours": "Joué à tes heures habituelles",
      "Offline the whole order": "Hors ligne pendant toute la commande",
      "Read the full safety policy": "Lire la politique de sécurité complète",

      /* steps */
      "Configure and pay": "Configure et paie",
      "Ranks, mode, champion or agent preferences, offline appear, scheduled hours. The price never changes after checkout.":
        "Rangs, mode, préférences de champions ou d’agents, mode hors ligne, horaires. Le prix ne bouge plus après le paiement.",
      "A booster claims it, usually inside 20 minutes":
        "Un booster la prend, généralement en moins de 20 minutes",
      "You see their rank, region, win rate and current queue before they start. Swap them once, free, no reason needed.":
        "Tu vois son rang, sa région, son winrate et sa file avant qu’il commence. Tu peux en changer une fois, gratuitement, sans justification.",
      "Track every match, pause any time": "Suis chaque partie, mets en pause quand tu veux",
      "Match history, LP graph and chat in one dashboard. Pause from the dashboard and the account is yours again in minutes.":
        "Historique, courbe de LP et chat dans un seul tableau de bord. Tu mets en pause et le compte est à toi en quelques minutes.",

      /* guarantees */
      "Guarantee": "Garantie",
      "Finished or refunded": "Terminé ou remboursé",
      "Every order ends in the rank you paid for or the money back for the part that never arrived. There is no third outcome.":
        "Chaque commande se termine au rang payé, ou par le remboursement de ce qui n’est jamais arrivé. Il n’y a pas de troisième issue.",
      "Privacy": "Confidentialité",
      "Nobody sees your name": "Personne ne voit ton nom",
      "Boosters get a rank, a server and your play window. Your name, email and payment details never reach them, and the order needs no account.":
        "Le booster reçoit un rang, un serveur et un créneau de jeu. Ton nom, ton e-mail et tes données de paiement ne lui parviennent jamais, et la commande ne demande aucun compte.",
      "Support": "Support",
      "Answered in minutes, not days": "Réponse en minutes, pas en jours",
      "One thread per order, staffed around the clock. If an account review lands, support files the appeal for you rather than pointing you at a form.":
        "Un fil par commande, tenu 24h/24. Si une vérification de compte tombe, le support dépose le recours à ta place au lieu de te renvoyer vers un formulaire.",

      /* dashboard points */
      "Match-by-match history": "Historique partie par partie",
      "Every game your booster plays, with the LP swing, KDA and replay link.":
        "Chaque partie de ton booster, avec l’écart de LP, le KDA et le lien de replay.",
      "Pause on one click": "Pause en un clic",
      "Want to play tonight? Pause, and the account is free within minutes.":
        "Envie de jouer ce soir ? Tu mets en pause, et le compte est libre en quelques minutes.",
      "Chat with the booster, not a queue": "Parle au booster, pas à une file",
      "Ask for a champion pool, a schedule, or a swap. Support reads the same thread.":
        "Demande un pool de champions, un horaire, un changement. Le support lit le même fil.",

      /* FAQ */
      "Do I need an account to see the price?": "Ai-je besoin d’un compte pour voir le prix ?",
      "No. The calculator is on every page and needs nothing from you. You only enter an email at checkout, and only so we can send you the order link.":
        "Non. Le calculateur est sur chaque page et ne te demande rien. Tu ne saisis un e-mail qu’au paiement, et uniquement pour recevoir le lien de commande.",
      "Can I check out without creating an account?": "Puis-je payer sans créer de compte ?",
      "Yes. Email, then payment. We create the order under that address and email you a one-click link to follow it. Set a password later if you want one, or never.":
        "Oui. E-mail, puis paiement. On crée la commande sous cette adresse et on t’envoie un lien en un clic pour la suivre. Tu mettras un mot de passe plus tard si tu en veux un, ou jamais.",
      "Is my account safe?": "Mon compte est-il en sécurité ?",
      "Your booster connects through a VPN in your region, appears offline, and plays inside the hours you set. We never ask for a Riot/Steam/Blizzard recovery email, never change your password, and never queue with other customers' accounts.":
        "Ton booster se connecte via un VPN dans ta région, apparaît hors ligne et joue pendant les horaires que tu fixes. On ne demande jamais d’e-mail de récupération Riot/Steam/Blizzard, on ne change jamais ton mot de passe et on ne lance jamais de file avec les comptes d’autres clients.",
      "What if I want to play while the boost is running?": "Et si je veux jouer pendant le boost ?",
      "Pause it from the dashboard. The account is free within minutes and the timer stops. Resume when you're done.":
        "Mets-le en pause depuis le tableau de bord. Le compte est libre en quelques minutes et le chrono s’arrête. Tu reprends quand tu as fini.",
      "What exactly is refunded, and when?": "Qu’est-ce qui est remboursé exactement, et quand ?",
      "In full, no questions, until a booster claims the order. After that, pro-rated on the part that hasn't been delivered — divisions not climbed, wins not won. Refunds are issued to the original payment method within 5 business days.":
        "Intégralement, sans question, jusqu’à ce qu’un booster prenne la commande. Ensuite, au prorata de ce qui n’a pas été livré — divisions non montées, victoires non obtenues. Le remboursement part sur le moyen de paiement d’origine sous 5 jours ouvrés.",
      "Solo or duo — which should I pick?": "Solo ou duo — que choisir ?",
      "Solo is faster and cheaper: the booster plays alone. Duo means you play every game with them, nobody logs into your account, and it costs 55% more for the extra time.":
        "Le solo est plus rapide et moins cher : le booster joue seul. En duo, tu joues chaque partie avec lui, personne ne se connecte à ton compte, et ça coûte 55 % de plus pour le temps en plus.",
      "How fast will someone start?": "En combien de temps quelqu’un commence-t-il ?",
      "Median time to a claimed order last month was 18 minutes. Priority queue takes that down to about 6. If nobody claims it within 24 hours, you get a full refund automatically — you don't have to ask.":
        "Le mois dernier, le délai médian de prise en charge était de 18 minutes. La file prioritaire le descend à 6 environ. Si personne ne la prend sous 24 heures, tu es remboursé intégralement, automatiquement — sans rien demander.",
      "Which payment methods do you take?": "Quels moyens de paiement acceptez-vous ?",
      "Cards, Apple Pay and Google Pay, all handled securely by Stripe. Crypto is coming soon. The card statement reads as a neutral merchant name, not the service.":
        "Carte, Apple Pay et Google Pay, tout est géré en sécurité par Stripe. La crypto arrive bientôt. Le relevé bancaire affiche un nom de marchand neutre, pas le service.",
      "Verified order ·": "Commande vérifiée ·",

      /* games index */
      "Pick your": "Choisissez votre",
      "battlefield.": "champ de bataille.",
      "Prices are per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Les prix sont à la division et affichés avant toute connexion. Placements, victoires nettes, coaching et duo sur chaque jeu.",
      "How it runs": "Comment ça marche",
      "Three steps, then": "Trois étapes, puis",
      "it's out of your hands": "ce n’est plus ton problème",
      "Configure →": "Configurer →",
      "Other games": "Autres jeux",

      /* games catalogue — design_handoff_games_page. Figures ride in their own
         <b> nodes, so the sentences around them stay whole keys; the two answers
         quoting a price or a percentage bake the current one in, like every
         other figure-bearing answer in this file. */
      "Nine titles": "Neuf jeux",
      "Pick your battlefield.": "Choisissez votre champ de bataille.",
      "Prices are per division and shown before you sign in. Placements, net wins and duo on every title, coaching on":
        "Les prix sont à la division et affichés avant toute connexion. Placements, victoires nettes et duo sur chaque jeu, coaching sur",
      "of them.": "d’entre eux.",
      "All titles": "Tous les jeux",
      "Riot titles": "Jeux Riot",
      "Valve titles": "Jeux Valve",
      "With coaching": "Avec coaching",
      "titles.": "jeux.",
      "Sort": "Trier",
      "Featured": "Sélection",
      "Lowest price": "Prix le plus bas",
      "Show all nine": "Afficher les neuf",
      "Which service": "Quel service",
      "Four ways to buy a climb.": "Quatre façons d’acheter une montée.",
      "Every title sells the first three. If you are not sure which one you want, read the \"best for\" line — it is usually the whole answer.":
        "Chaque jeu propose les trois premiers. Si tu hésites, lis la ligne « idéal pour » — c’est en général toute la réponse.",
      "Best for": "Idéal pour",
      "Two ranks, one price. Your booster climbs from where you are to where you want to be, and the number never moves after checkout.":
        "Deux rangs, un prix. Ton booster monte d’où tu es jusqu’où tu veux aller, et le montant ne bouge plus après le paiement.",
      "You know the rank you want": "Tu sais quel rang tu veux",
      "Priced per win above your losses, five to an order. A short push when you are close and do not want to commit to a full climb.":
        "Facturé par victoire au-dessus de tes défaites, cinq par commande. Un coup de pouce quand tu es proche et que tu ne veux pas t’engager sur une montée complète.",
      "You are one division short": "Il te manque une division",
      "We play up to five of your season games, on a ranked account or a fresh one. The rank you land is the rank you keep.":
        "On joue jusqu’à cinq de tes parties de classement, sur un compte classé ou un compte tout neuf. Le rang obtenu est celui que tu gardes.",
      "The season just reset": "La saison vient de repartir",
      "An hour with a coach from the roster, live on Discord, screen shared and recorded for you to keep. Live on four of the nine titles.":
        "Une heure avec un coach du roster, en direct sur Discord, écran partagé et enregistré pour toi. Disponible sur quatre des neuf jeux.",
      "You want to climb it yourself": "Tu veux monter toi-même",
      "Three steps, then it's out of your hands": "Trois étapes, puis ce n’est plus ton problème",
      "Same dashboard on all nine titles. It opens from the link we email you — no password, no app — and updates as games finish.":
        "Le même tableau de bord sur les neuf jeux. Il s’ouvre depuis le lien qu’on t’envoie par e-mail — sans mot de passe, sans application — et se met à jour à la fin de chaque partie.",
      "Asked on this page": "Questions posées sur cette page",
      "Title-specific questions live on each game's page. These are the ones about all nine.":
        "Les questions propres à un jeu sont sur sa page. Voici celles qui concernent les neuf.",
      "Are these all the titles you cover?": "Est-ce là tous les jeux que vous couvrez ?",
      "These nine are the ones with a live board and enough boosters to claim an order quickly. We take one-off requests on other titles in Discord, but there is no page and no instant price for them — if the queue cannot claim it, we say so rather than take the money.":
        "Ces neuf-là ont un tableau actif et assez de boosters pour prendre une commande vite. On accepte des demandes ponctuelles sur d’autres jeux via Discord, mais sans page ni prix instantané — si la file ne peut pas la prendre, on le dit plutôt que d’encaisser.",
      "Why is Valorant cheaper than Counter-Strike 2?":
        "Pourquoi Valorant est-il moins cher que Counter-Strike 2 ?",
      "A division is not the same amount of work in every game. Ladders are different lengths, matches are different lengths, and one rung near the top of a ladder can cost several near the bottom of another. Each title carries its own multiplier, and it is on screen before you sign in: the cheapest single division is $3 on Valorant and $8 on Counter-Strike 2.":
        "Une division ne représente pas le même travail dans chaque jeu. Les ladders n’ont pas la même longueur, les parties non plus, et un échelon près du sommet d’un ladder peut en coûter plusieurs en bas d’un autre. Chaque jeu a son propre multiplicateur, affiché avant toute connexion : la division la moins chère est à 3 $ sur Valorant et à 8 $ sur Counter-Strike 2.",
      "Does one booster cover several games?": "Un booster couvre-t-il plusieurs jeux ?",
      "No. Everyone on the board plays exactly one title, and their profile carries the peak rank, the win rate, the on-time record and the orders they have delivered on it. Somebody claiming three ladders at once is somebody we did not hire.":
        "Non. Chaque personne du roster joue exactement un jeu, et son profil affiche son peak, son winrate, sa ponctualité et les commandes qu’elle y a livrées. Quelqu’un qui prétend tenir trois ladders à la fois est quelqu’un qu’on n’a pas recruté.",
      "Can I order two titles at once?": "Puis-je commander deux jeux à la fois ?",
      "Yes, as two orders — each gets its own booster, price and dashboard. There is no cross-title bundle, because a discount spanning two boosters would be paying one of them less.":
        "Oui, en deux commandes — chacune avec son booster, son prix et son tableau de bord. Il n’existe pas de pack multi-jeux : une remise à cheval sur deux boosters reviendrait à en payer un moins.",
      "Do prices change during a sale?": "Les prix changent-ils pendant une promo ?",
      "SPLIT15 takes 15% off the whole catalogue with nothing to type. Each game page also carries bundle climbs at 19% to 37% off, and a bundle replaces the code rather than adding to it — there is only ever one discount on an order, and it is the larger of the two.":
        "SPLIT15 enlève 15 % sur tout le catalogue, sans rien à saisir. Chaque page de jeu propose aussi des packs de montée à −19 % à −37 %, et un pack remplace le code au lieu de s’y ajouter — il n’y a jamais qu’une seule remise par commande, et c’est la plus avantageuse des deux.",
      "Nine titles, one guarantee.": "Neuf jeux, une garantie.",
      "Refunded in full until a booster claims it, pro-rated after that, and claimed in 18 min on average.":
        "Remboursé intégralement jusqu’à la prise en charge, au prorata ensuite, et pris en charge en 18 min en moyenne.",
      "Start with League": "Commencer par League",

      /* game page */
      "Home": "Accueil",
      "Breadcrumb": "Fil d’Ariane",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3 140 avis",
      "boosters free now": "boosters dispo",
      "online": "en ligne",
      "orders,": "commandes,",
      "in players' words": "dans les mots des joueurs",
      "Questions people": "Les questions que les gens",
      "ask before paying": "posent avant de payer",
      "Ask us instead": "Demande-nous plutôt",
      "On shift now": "En ligne maintenant",

      /* booster table */
      "Booster": "Booster",
      "Game": "Jeu",
      "Peak": "Peak",
      "Win rate": "Winrate",
      "Queue": "File",
      "Every booster is trialled live before onboarding and reviewed monthly. Ranks shown are verified from match history, not self-reported.":
        "Chaque booster passe un essai en direct avant d’être intégré, puis est réévalué chaque mois. Les rangs affichés sont vérifiés depuis l’historique de parties, pas déclarés.",

      /* how-it-works */
      "How it works": "Comment ça marche",
      "No account.": "Pas de compte.",
      "No surprises.": "Pas de surprises.",
      "No ticket queue.": "Pas de file de tickets.",
      "You can see the whole price before you tell us anything about yourself. That is the entire point of the way this is built: the calculator is the first thing on every page, the number it shows is the number you pay, and the only thing checkout asks for is an email to send the order link to.":
        "Tu vois le prix complet avant de nous dire quoi que ce soit sur toi. C’est tout l’intérêt de cette conception : le calculateur est la première chose sur chaque page, le montant affiché est celui que tu paies, et le paiement ne demande qu’un e-mail pour t’envoyer le lien de commande.",
      "Solo or duo": "Solo ou duo",
      "The booster plays alone": "Le booster joue seul",
      "Fastest and cheapest. You hand over the login, they connect through a VPN in your region, appear offline, and play inside the hours you set. You keep the account and can pause or take it back at any moment from the dashboard.":
        "Le plus rapide et le moins cher. Tu confies les identifiants, le booster se connecte via un VPN dans ta région, apparaît hors ligne et joue pendant les horaires que tu fixes. Le compte reste à toi : tu peux le mettre en pause ou le reprendre à tout moment depuis le tableau de bord.",
      "You play every game": "Tu joues chaque partie",
      "Nobody logs into your account, ever. You queue with the booster, voice optional, and most of them will call rotations and review your mistakes on the way up. It costs more because it takes their time at your pace.":
        "Personne ne se connecte jamais à ton compte. Tu lances la file avec le booster, vocal en option, et la plupart appellent les rotations et corrigent tes erreurs en chemin. Ça coûte plus cher parce que ça mobilise leur temps à ton rythme.",
      "Everything else": "Tout ce que",
      "people ask": "les gens demandent",

      /* boosters roster + profile — design_handoff_boosters_roster */
      "Verified from match history, not self-reported.": "Vérifié depuis l’historique, pas déclaré.",
      "How someone gets on this page": "Comment on arrive sur cette page",
      "30 days": "30 jours",
      "applied last month": "candidatures le mois dernier",
      "trialled live on our account — five games, watched":
        "testés en direct sur notre compte — cinq parties, observées",
      "added to the board": "ajoutés au roster",
      "62% win-rate floor, checked monthly": "Winrate minimum de 62 %, vérifié chaque mois",
      "Ranks read from the game API": "Rangs lus depuis l’API du jeu",
      "Trial games recorded and reviewed": "Parties d’essai enregistrées et revues",
      "Applications open in the": "Les candidatures passent par le",
      "queue": "",
      "players in there.": "joueurs y sont.",
      "Join": "Rejoindre",
      "on the board": "sur le roster",
      "free right now": "dispo en ce moment",
      "Availability": "Disponibilité",
      "Everyone": "Tout le monde",
      "Free now": "Dispo",
      "Sort by": "Trier par",
      "Free first": "Dispo d’abord",
      "Game · Server": "Jeu · Serveur",
      "Peak this season": "Peak cette saison",
      "Win rate · 30d": "Winrate · 30 j",
      "Hire": "Réserver",
      "Nobody free on": "Personne de dispo sur",
      "right now": "en ce moment",
      "Nobody free right now": "Personne de dispo en ce moment",
      "on the board — start the order and the first one free claims it.":
        "sur le roster — lance la commande et le premier dispo la prend.",
      "Order anyway": "Commander quand même",
      "Show everyone": "Voir tout le monde",
      "Showing": "Affichage de",
      "free now": "dispo",
      "Load more": "Voir plus",
      "Boosting since": "Booster depuis",
      "in the queue": "dans la file",
      "Orders delivered": "Commandes livrées",
      "Average rating": "Note moyenne",
      "On-time rate": "Livraisons à l’heure",
      "Disputes": "Litiges",
      "Completed orders": "Commandes terminées",
      "Completed": "Terminée",
      "Rating": "Note",
      "On time": "À l’heure",
      "Top booster": "Meilleur booster",
      "Rank verified every month": "Rang vérifié chaque mois",
      "One free swap, no reason needed": "Un changement gratuit, sans justification",
      "See the roster": "Voir le roster",
      "See all": "Tout voir",
      "day": "jour",
      "Request": "Demander",
      "Name them at checkout and your order waits for them instead of going to the open board.":
        "Nomme-le au paiement et ta commande l’attend au lieu de partir sur le roster ouvert.",
      "Named booster": "Booster nommé",
      "No extra fee": "Sans supplément",
      "ahead of you": "avant toi",
      "Order with": "Commander avec",
      "Climbs delivered": "Montées livrées",
      /* "Showing the last N of M orders" — "of" is a shared key, so leaving
         these two out produced a half-translated sentence. Both languages take
         the figures in English order here; the French is slightly stiff and
         the German is idiomatic. */
      "Showing the last": "Affichage de",
      "orders": "dernières commandes",
      "Latest review": "Dernier avis",
      "day ago": "jour",
      "days ago": "jours",
      "Ordering with": "Commande avec",

      /* boosters page */
      "The roster": "Le roster",
      "Verified from": "Vérifié depuis",
      "match history,": "l’historique,",
      "not self-reported.": "pas déclaré.",
      "Every applicant is trialled live on our account before they touch yours: five games, watched, in the bracket they claim. Ranks on this page are read from the API, not typed into a form. Anyone whose win rate drops below 62% over a rolling month comes off the board until they climb it back.":
        "Chaque candidat passe un essai en direct sur notre compte avant de toucher au tien : cinq parties, observées, dans le palier qu’il revendique. Les rangs de cette page sont lus depuis l’API, pas saisis dans un formulaire. Quiconque voit son winrate passer sous 62 % sur un mois glissant quitte le roster jusqu’à le remonter.",
      "Apply as a booster": "Postuler comme booster",
      "Roster": "Roster",
      "Everyone on shift": "Tous en ligne",
      "Updated live": "Mis à jour en direct",

      /* guarantee page — design_handoff_safety_guarantee */
      "Safety & guarantee": "Sécurité et garantie",
      "Written down, not \"depends on the order\".":
        "Écrit noir sur blanc, pas « ça dépend de la commande ».",
      "A refund policy that needs a support ticket to explain isn't a policy. Here is the whole thing, in the three cases that actually happen.":
        "Une politique de remboursement qu’il faut un ticket de support pour expliquer n’est pas une politique. La voici en entier, dans les trois cas qui arrivent vraiment.",
      /* hero figures — the number is data, the unit is a word */
      "5 days": "5 jours",
      "24 hrs": "24 h",
      "Recovery rate on account reviews, across":
        "Taux de récupération sur les vérifications de compte, sur",
      "completed orders": "commandes terminées",
      "Refunds land back on the original payment method, no ticket needed":
        "Les remboursements reviennent sur le moyen de paiement d’origine, sans ticket",
      "Unclaimed after payment? Refunded in full, automatically":
        "Non prise en charge après paiement ? Remboursée intégralement, automatiquement",
      "Before a booster claims it": "Avant la prise en charge",
      "100% back, no reason asked": "100 % remboursé, sans justification",
      "One button in the order page. The money is back on the original payment method within 5 business days, and nobody will email you to ask why.":
        "Un bouton sur la page de commande. L’argent revient sur le moyen de paiement d’origine sous 5 jours ouvrés, et personne ne vous écrira pour demander pourquoi.",
      "Started but unfinished": "Commencé mais inachevé",
      "Pro-rated on what wasn't delivered": "Au prorata de ce qui n’a pas été livré",
      "Divisions not climbed and wins not won are refunded at the same rate you paid for them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond portion, calculated by the same formula that quoted you.":
        "Les divisions non montées et les victoires non obtenues sont remboursées au tarif auquel vous les avez payées. Un Gold → Diamant arrêté au Platine rembourse la portion Platine → Diamant, calculée par la formule qui vous a donné le prix.",
      "Past the ETA": "Au-delà du délai",
      "Your choice, and we tell you first": "À vous de choisir, et nous vous prévenons d’abord",
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back.":
        "Si une commande dépasse sa fenêtre de livraison, nous vous prévenons avant que vous le remarquiez : continuer avec un avoir de 15 %, changer de booster, ou récupérer la portion inachevée.",

      /* band 02 — the safety prose, the disclaimer plate, the measure card */
      "Anti-cheat looks for software, not skill. Every solo order runs behind an enterprise VPN matched to your region, the booster mirrors your sensitivity and crosshair, and sessions are scheduled inside the hours you normally play — so the activity pattern on the account never changes. Duo orders never touch your login at all.":
        "L’anti-triche cherche des logiciels, pas du talent. Chaque commande solo passe par un VPN professionnel situé dans votre région, le booster copie votre sensibilité et votre viseur, et les sessions sont planifiées dans vos horaires de jeu habituels — le schéma d’activité du compte ne change donc jamais. Les commandes duo ne touchent jamais à vos identifiants.",
      "If a boost triggers an account review, support files the appeal and the order is refunded in full while it runs. Your name, email and payment details are never shared with the booster.":
        "Si un boost déclenche une vérification de compte, le support dépose le recours et la commande est remboursée intégralement pendant la procédure. Votre nom, votre e-mail et vos données de paiement ne sont jamais communiqués au booster.",
      "Boosting is against the terms of service of every game listed here. We reduce the risk as far as it can be reduced and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is lying to you.":
        "Le boosting est contraire aux conditions d’utilisation de chacun des jeux listés ici. Nous réduisons le risque autant qu’il peut l’être et nous ne prétendrons pas qu’il est nul, parce qu’il ne l’est pas — tout concurrent qui affirme le contraire vous ment.",
      "What that means per order": "Ce que cela signifie par commande",
      "Every order": "Chaque commande",
      "Enterprise VPN, matched to your region": "VPN professionnel, adapté à votre région",
      "Not a consumer VPN and not a datacentre IP — the login location never changes.":
        "Ni un VPN grand public ni une IP de centre de données — le lieu de connexion ne change jamais.",
      "The booster mirrors your settings before the first game.":
        "Le booster reproduit vos réglages avant la première partie.",
      "Played inside your normal hours": "Joué pendant vos horaires habituels",
      "You set the window at checkout; sessions are scheduled inside it.":
        "Vous fixez la plage horaire au paiement ; les sessions y sont planifiées.",
      "Offline appearance, whole order": "Apparence hors ligne, toute la commande",
      "Friends see you offline until the order closes.":
        "Vos amis vous voient hors ligne jusqu’à la clôture de la commande.",
      "Duo never touches your login": "Le duo ne touche jamais à vos identifiants",
      "You play your own account. Nobody signs in but you.":
        "Vous jouez sur votre propre compte. Personne ne s’y connecte à part vous.",

      /* band 03 — three promises */
      "In short": "En bref",
      "Three promises, plainly": "Trois promesses, clairement",
      "Read the full terms": "Lire les conditions complètes",
      /* The Guarantee card's proof line is the same sentence the checkout page
         states — one entry, in the checkout block below, for both. The handoff
         requires the two to match word for word. */
      "Card details stay with Stripe": "Les données de carte restent chez Stripe",
      "Median first reply 3m 40s": "Première réponse médiane 3 min 40 s",

      /* band 04 — FAQ */
      "The questions support gets most": "Les questions que le support reçoit le plus",
      "The six support answers most. If yours isn't here, the thread on your order reaches a person, not a bot.":
        "Les six auxquelles le support répond le plus. Si la vôtre n’y est pas, le fil de votre commande arrive chez une personne, pas chez un bot.",
      "Ask support": "Contacter le support",
      "Can I play my own account while an order runs?":
        "Puis-je jouer sur mon propre compte pendant une commande ?",
      "Yes, and it costs nothing. Pause the order from the order page and the booster stops at the end of the current game; unpause and it resumes the same night if a slot is open. Playing ranked yourself while a solo order is unpaused is the one thing to avoid — two people queuing the same account is what looks abnormal, not the boost.":
        "Oui, et cela ne coûte rien. Mettez la commande en pause depuis sa page et le booster s’arrête à la fin de la partie en cours ; relancez-la et elle repart le soir même si un créneau est libre. La seule chose à éviter est de jouer vous-même en classé pendant qu’une commande solo tourne — ce sont deux personnes lançant des files sur le même compte qui paraissent anormales, pas le boost.",
      "What happens if my account gets a review or a ban?":
        "Que se passe-t-il si mon compte fait l’objet d’une vérification ou d’un bannissement ?",
      "Support files the appeal for you and the order is refunded in full while it runs, so you are never paying for an account you cannot use. Boosting still breaks every listed game's terms of service — the risk is reduced as far as it can be, not removed.":
        "Le support dépose le recours à votre place et la commande est remboursée intégralement pendant la procédure : vous ne payez jamais pour un compte inutilisable. Le boosting enfreint toujours les conditions d’utilisation de chaque jeu listé — le risque est réduit autant qu’il peut l’être, pas supprimé.",
      "Will the booster change my password or my settings?":
        "Le booster va-t-il changer mon mot de passe ou mes réglages ?",
      "No. Login details are used to sign in and nothing else — no password changes, no email changes, no purchases, no rune or loadout edits beyond the champions and roles you asked for. Sensitivity and crosshair are mirrored to yours, then restored. Change your password once the order closes anyway; the order page tells you when.":
        "Non. Les identifiants servent à se connecter, à rien d’autre — aucun changement de mot de passe, d’e-mail, aucun achat, aucune modification de runes ou d’équipement au-delà des champions et rôles demandés. La sensibilité et le viseur sont copiés sur les vôtres, puis rétablis. Changez tout de même votre mot de passe à la clôture ; la page de commande vous dit quand.",
      "How is the price calculated, and can it change after I pay?":
        "Comment le prix est-il calculé, et peut-il changer après paiement ?",
      "The price is per division crossed, so a longer climb costs more per step than a short one. It is fixed at checkout: the number on the button is the number charged, and nothing is added later. Duo adds 55% because the booster carries a second player, and add-ons are priced individually before you pay.":
        "Le prix est calculé par division franchie : une longue montée coûte donc plus cher par palier qu’une courte. Il est figé au paiement : le montant sur le bouton est celui qui est débité, et rien ne s’ajoute ensuite. Le duo ajoute 55 % parce que le booster porte un second joueur, et les options sont facturées individuellement avant le paiement.",
      "Do I have to make an account to order?": "Dois-je créer un compte pour commander ?",
      "No. Orders are created against your email and you get a one-click link to follow them. Set a password afterwards if you want the dashboard to remember your orders; skip it and the link still works. Your name, email and card details are never shared with the booster.":
        "Non. Les commandes sont créées à partir de votre e-mail et vous recevez un lien en un clic pour les suivre. Définissez un mot de passe ensuite si vous voulez que le tableau de bord retienne vos commandes ; sinon, le lien fonctionne quand même. Votre nom, votre e-mail et vos données de carte ne sont jamais communiqués au booster.",
      "Can I pick a specific booster?": "Puis-je choisir un booster précis ?",
      "Yes — name one at checkout from their profile and the order waits for them instead of going to the open board. That means a slower start, so we show their current queue and slots before you commit. Leave it open and the first free booster in your bracket claims it, usually inside 18 min.":
        "Oui — désignez-en un au paiement depuis son profil et la commande l’attend au lieu de partir sur le tableau ouvert. Le démarrage est donc plus lent, c’est pourquoi nous affichons sa file et ses créneaux avant que vous ne validiez. Laissez-la ouverte et le premier booster disponible de votre palier la prend, généralement en moins de 18 min.",

      /* support page */
      "Two ways in.": "Deux moyens de nous joindre.",
      "Both are read": "Les deux sont lus",
      "by people.": "par des humains.",
      "No ticket robot, no \"we'll get back to you within 48 hours\". Discord is the fast one — that's where this market already lives, and it's where our staff sit all day.":
        "Pas de robot à tickets, pas de « nous reviendrons vers vous sous 48 heures ». Discord est le plus rapide — c’est là que ce marché vit déjà, et là que notre équipe est toute la journée.",
      "Median first reply last month": "Première réponse médiane le mois dernier",
      "Fastest": "Le plus rapide",
      "Discord — open a ticket in #support": "Discord — ouvre un ticket dans #support",
      "Public server, private ticket channels. Order questions, refunds, booster swaps and pre-sales, 24/7. You can also just read what other buyers are saying before you order anything, which is rather the point of it being public.":
        "Serveur public, salons de tickets privés. Questions de commande, remboursements, changements de booster et avant-vente, 24/7. Tu peux aussi lire ce que disent les autres acheteurs avant de commander — c’est tout l’intérêt d’un serveur public.",
      "Open the Discord invite": "Ouvrir l’invitation Discord",
      "On the record": "Par écrit",
      "Email — info@esportsboost.com": "E-mail — info@esportsboost.com",
      "Better for anything involving a payment dispute or a document. Answered in under two hours during EU and NA daytime, under six overnight.":
        "Mieux pour un litige de paiement ou un document. Réponse en moins de deux heures en journée UE et NA, moins de six la nuit.",
      "Or write": "Ou écris",
      "it here": "ici",
      "Goes to the same inbox. If you have an order number, include it — it puts the message in front of the person handling that order.":
        "Ça arrive dans la même boîte. Si tu as un numéro de commande, indique-le — le message atterrit directement chez la personne qui la gère.",
      "Email": "E-mail",
      "Order number (optional)": "Numéro de commande (facultatif)",
      "Message": "Message",
      "What's going on?": "Qu’est-ce qui se passe ?",
      "Send message": "Envoyer le message",
      "Sending…": "Envoi…",
      /* The form's three outcomes. Each sentence is its own node — the address
         and the visitor's own email ride in <b>s of their own, so nothing here
         has a figure or a mailbox interpolated into a translatable string. */
      "Sent — it's in the inbox.": "Envoyé — c’est dans la boîte.",
      "The reply lands at": "La réponse arrivera à",
      "your address": "votre adresse",
      "Discord is quicker if you'd rather not wait.": "Discord est plus rapide si tu ne veux pas attendre.",
      "Noted — this is a preview.": "Noté — ceci est un aperçu.",
      "Nothing was emailed: this build has no mailbox configured. Write to":
        "Aucun e-mail n’a été envoyé : cette version n’a pas de boîte configurée. Écrivez à",
      "and it reaches the same people.": "et cela arrive aux mêmes personnes.",
      "That didn't send.": "L’envoi a échoué.",
      "Rather than lose it, write to": "Pour ne rien perdre, écris à",
      "or open a ticket in Discord — both land in the same place.":
        "ou ouvrez un ticket sur Discord — les deux arrivent au même endroit.",
      "Before you write in": "Avant de nous écrire",

      /* reviews page. The figures ride in their own nodes, so "4.7 / 5 across
         13K customers" is two translatable words around two numbers. "reviews"
         is still needed — it is the count line under the filters ("Showing 12
         of 58 reviews"). The rating segment says "Any" rather than the
         handoff's "All" because "All" is already taken by the roster rail's
         "All 187 reviews". */
      "reviews": "avis",
      "customers": "clients",
      "Every review below is attached to a paid, completed order — pulled from Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so one-star reviews sit in the same feed.":
        "Chaque avis ci-dessous est rattaché à une commande payée et livrée — récupéré sur Trustpilot et sur la note en page de commande, puis dédupliqué. On ne filtre pas par note : les avis une étoile sont dans le même flux.",
      "across": "sur",
      "Read the worst first": "Commencer par les pires",
      "Read on Trustpilot": "Lire sur Trustpilot",
      "Overall rating": "Note globale",
      "Verified only": "Vérifiés uniquement",
      "Click a row to filter the feed by that rating.":
        "Clique sur une ligne pour filtrer le flux par cette note.",
      "Any": "Toutes",
      "or less": "ou moins",
      "Most recent": "Plus récents",
      "Highest rated": "Mieux notés",
      "Lowest rated": "Moins bien notés",
      "Clear filters": "Effacer les filtres",
      "Nothing matches that yet": "Rien ne correspond",
      "No review in the feed has that rating for this game. Widen the filters to see the rest.":
        "Aucun avis du flux n’a cette note pour ce jeu. Élargis les filtres pour voir le reste.",
      "Load 30 more": "Charger 30 de plus",
      "Show the rest": "Afficher le reste",
      "Excellent": "Excellent",
      "Where the score": "D’où vient",
      "comes from": "la note",
      "A review request goes out once, on delivery, and never again. Nothing is incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than competitors who buy them, and it's the reason the score is worth reading at all.":
        "Une demande d’avis part une fois, à la livraison, et jamais plus. Rien n’est offert en échange — pas de remise pour un avis, pas de récompense pour un cinq. Ça garde un volume plus bas que chez les concurrents qui les achètent, et c’est pour ça que la note vaut la peine d’être lue.",

      /* the demo page (was "track my order") — design_handoff_track_order */
      "Demo": "Démo",
      "Demo dashboard": "Tableau de bord démo",
      "Your link works without a password.": "Ton lien marche sans mot de passe.",
      "Guest orders are tracked by the link we emailed you. Lost it? Put the address you paid with below and we'll send it again. Nothing to remember, nothing to reset.":
        "Les commandes invité se suivent avec le lien qu’on t’a envoyé par e-mail. Perdu ? Mets ci-dessous l’adresse utilisée pour payer et on te le renvoie. Rien à retenir, rien à réinitialiser.",
      "No account, no password — the link is the login":
        "Pas de compte, pas de mot de passe — le lien est la connexion",
      "It never expires and works on any device": "Il n’expire jamais et marche sur tous les appareils",
      "Find your order": "Retrouve ta commande",
      "Guest safe": "Sans compte",
      "Order number": "Numéro de commande",
      /* the two states of the helper line under the order-number field, and the
         two submit labels — page_demo()'s own script owns these nodes and asks
         for them through esbT, because they swap at runtime. */
      "On your confirmation email, under the total.": "Sur ton e-mail de confirmation, sous le total.",
      "We can't find that order number. Check the confirmation email, or use the address you paid with below.":
        "On ne trouve pas ce numéro de commande. Vérifie l’e-mail de confirmation, ou utilise ci-dessous l’adresse ayant servi au paiement.",
      "or": "ou",
      "The email you paid with": "L’e-mail utilisé pour payer",
      "We resend the link to that address. It never expires and it works on any device.":
        "On renvoie le lien à cette adresse. Il n’expire jamais et marche sur tous les appareils.",
      "Find my order": "Trouver ma commande",
      "Email me the link": "M’envoyer le lien",
      "Demo — no email was sent.": "Démo — aucun e-mail n’a été envoyé.",
      "On the live site the link reaches": "Sur le site en ligne, le lien parvient à",
      "inside a minute, it never expires, and it opens the dashboard below on any device.":
        "en moins d’une minute, il n’expire jamais, et il ouvre le tableau de bord ci-dessous sur tous les appareils.",
      "The order number is in your confirmation email, on the line under the total.":
        "Le numéro de commande est dans ton e-mail de confirmation, sur la ligne sous le total.",

      /* the resolved order */
      "Back to the order lookup": "Retour à la recherche de commande",
      "In progress": "En cours",
      "Paused": "En pause",
      "Example": "Exemple",
      "Pause order": "Mettre en pause",
      "Resume order": "Reprendre",
      "Order paused.": "Commande en pause.",
      "The account is free within minutes and the delivery clock stops. Resume whenever you're done playing.":
        "Le compte est libre en quelques minutes et le chrono de livraison s’arrête. Reprends quand tu as fini de jouer.",
      "last game": "dernière partie",
      "Play window": "Créneau de jeu",
      "Watch live": "Regarder en direct",
      "Streaming now": "Stream en cours",
      "Not streaming": "Pas de stream",
      "is sharing their screen.": "partage son écran.",
      "isn't streaming right now.": "ne stream pas pour le moment.",
      "Discord screen share": "Partage d’écran Discord",
      "Join and watch": "Rejoindre et regarder",
      "Open the order channel": "Ouvrir le salon de la commande",
      "The channel is private to you and your booster, and closes when the order is delivered.":
        "Le salon est privé entre toi et ton booster, et il ferme à la livraison de la commande.",
      "Timeline": "Chronologie",
      "reached": "atteint",
      "claimed the order": "a pris la commande",
      "after payment": "après le paiement",
      "Yesterday, 23:10": "Hier, 23:10",
      "— any time this order is open.": "— à tout moment tant que cette commande est ouverte.",
      "Progress": "Progression",
      "Match": "Partie",
      "Result": "Résultat",
      "When": "Quand",
      "Ranked solo": "Classé solo",
      "Win": "Victoire",
      "Loss": "Défaite",
      "min ago": "min",

      /* checkout */
      "Secure checkout": "Paiement sécurisé",
      "Need a hand?": "Besoin d’un coup de main ?",
      "Required": "Obligatoire",
      "Optional": "Facultatif",
      "Anything the booster should know": "Ce que le booster doit savoir",
      "Enter an email we can send the order link to.":
        "Indique un e-mail pour recevoir le lien de commande.",
      "Mornings": "Matins",
      "Afternoons": "Après-midis",
      "Evenings": "Soirées",
      "Nights": "Nuits",
      "Card, Apple Pay and Google Pay are all on the next screen — details are entered on Stripe's secure checkout, so we never see or store them. Statements read as a neutral merchant name.":
        "Carte, Apple Pay et Google Pay sont sur l’écran suivant — les données sont saisies sur le paiement sécurisé de Stripe, on ne les voit ni ne les stocke. Les relevés affichent un nom de marchand neutre.",
      "Secured by Stripe": "Sécurisé par Stripe",
      "Contacting payment…": "Ouverture du paiement…",
      "Refunded in full until a booster claims it":
        "Remboursé intégralement jusqu’à la prise en charge par un booster",
      "Last chance to add": "Dernière chance d’ajouter",
      "Discount code": "Code promo",
      "applied": "appliqué",
      "No code applied": "Aucun code appliqué",
      "Have a code?": "Tu as un code ?",
      "Have another code?": "Un autre code ?",
      "Enter a code": "Entrer un code",
      "Close": "Fermer",
      "Your email": "Ton e-mail",
      "Order details": "Détails de la commande",
      "Payment": "Paiement",
      "Checkout": "Paiement",
      "No account needed. We create the order under your email and send a one-click link to follow it. You can set a password afterwards if you want one.":
        "Aucun compte requis. On crée la commande sous ton e-mail et on t’envoie un lien en un clic pour la suivre. Tu pourras mettre un mot de passe ensuite si tu en veux un.",
      "Used for your order link, and to send you your cart if you don't finish. No marketing unless you tick the box at the end.":
        "Sert au lien de commande, et à t’envoyer ton panier si tu ne finis pas. Aucun marketing sauf si tu coches la case à la fin.",
      "Preferred hours": "Horaires préférés",
      "Any time": "N’importe quand",
      "My usual play hours (18:00–00:00)": "Mes horaires de jeu habituels (18h00–00h00)",
      "While I'm at work (09:00–17:00)": "Pendant que je travaille (09h00–17h00)",
      "Overnight only": "La nuit uniquement",
      "Anything the booster should know (optional)": "Ce que le booster doit savoir (facultatif)",
      "Champion pool, roles, don't touch ranked flex…": "Pool de champions, rôles, ne pas toucher au flex…",
      "Hours you can play, roles, other accounts…": "Heures où tu peux jouer, rôles, autres comptes…",
      "Pay with": "Payer avec",
      "Payment method": "Moyen de paiement",
      "Card": "Carte",
      "Crypto": "Crypto",
      "— coming soon": "— bientôt disponible",
      "Card details are entered on Stripe's secure checkout — we never see or store them. Statements read as a neutral merchant name.":
        "Les données de carte sont saisies sur le paiement sécurisé de Stripe — on ne les voit ni ne les stocke. Les relevés affichent un nom de marchand neutre.",
      "Email me when my order is claimed and when it's done. Nothing else.":
        "Préviens-moi quand ma commande est prise en charge et quand elle est terminée. Rien d’autre.",
      "Place the order": "Passer la commande",
      "Read the guarantee": "Lire la garantie",
      "Order placed": "Commande passée",
      "This is a local preview, so no payment was taken and no email was sent. In production this is the point where the order goes on the booster board, the confirmation email leaves, and":
        "Ceci est un aperçu local : aucun paiement n’a été prélevé et aucun e-mail envoyé. En production, c’est ici que la commande rejoint le tableau des boosters, que l’e-mail de confirmation part, et que",
      "fires to GA4 and to the Meta CAPI gateway.": "est envoyé à GA4 et à la passerelle Meta CAPI.",
      "See what the dashboard looks like": "Voir à quoi ressemble le tableau de bord",
      "Order summary": "Récapitulatif de commande",
      "Locked at checkout": "Figé au paiement",
      "Climb": "Montée",
      "Boost": "Boost",
      "Money-back until claimed": "Remboursé jusqu’à la prise en charge",
      "Change the order": "Modifier la commande",

      /* checkout success */
      "Confirming payment…": "Confirmation du paiement…",
      "One moment": "Un instant",
      "We're confirming your payment with Stripe.": "On confirme ton paiement avec Stripe.",
      "Order": "Commande",
      "Paid": "Payé",

      /* become a booster */
      "Work here": "Bosser ici",
      "Get paid": "Sois payé",
      "for the queue": "pour la file",
      "you'd play anyway.": "que tu jouerais de toute façon.",
      "Payouts weekly, 70% of the order value on solo and 75% on duo, no deductions for the platform's payment fees. Pick your own shifts; take an order or don't. What we ask for is the rank, a clean account history, and that you never pass an account to anyone.":
        "Paiements hebdomadaires, 70 % de la valeur de commande en solo et 75 % en duo, sans déduction des frais de paiement. Choisis tes créneaux ; prends une commande ou pas. Ce qu’on demande : le rang, un compte sans historique de sanction, et de ne jamais transmettre un compte à qui que ce soit.",
      "Of the order, to you": "De la commande, pour toi",
      "Weekly": "Hebdomadaire",
      "Payouts, no minimum": "Paiements, sans minimum",
      "5 games": "5 parties",
      "Live trial before onboarding": "Essai en direct avant l’intégration",
      "In-game name": "Pseudo en jeu",
      "Peak rank": "Meilleur rang atteint",
      "Anything else": "Autre chose",
      "Apply": "Postuler",
      "How the trial works": "Comment se passe l’essai",

      /* legal */
      "Last updated": "Dernière mise à jour",
      "Questions about any of this go to": "Toute question à ce sujet est à adresser au",
      "support": "support",
      "Plain answers, same day.": "Des réponses claires, le jour même.",
      "Terms of service": "Conditions d’utilisation",
      "Refund policy": "Politique de remboursement",
      /* The entity block that closes all three legal pages. The company name
         and the address lines are data and stay as written, like game names
         and handles — only the labels around them are translated. */
      "Who to write to": "À qui écrire",
      "Open a support ticket": "Ouvrir un ticket au support",
      "Who's responsible for your data": "Qui est responsable de vos données",

      /* 404 */
      "Error 404": "Erreur 404",
      "That page": "Cette page",
      "isn't on": "n’est pas",
      "the ladder.": "sur le ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Le lien est mort ou la page a bougé. Le calculateur est à deux clics dans tous les cas.",
      "Pick a game": "Choisir un jeu",
      "Back to the homepage": "Retour à l’accueil",

      /* free guides landing — design_handoff_free_guides. Long-form prose
         (the lede, band subs, chapter notes, author metas, reader quotes and
         the FAQ answers) stays as content, the same as review text. */
      "Free guides · no payment": "Guides gratuits · sans paiement",
      "Browse boosting": "Voir le boosting",
      "Free guides": "Guides gratuits",
      "The two guides our boosters actually wrote.":
        "Les deux guides que nos boosters ont vraiment écrits.",
      "PDFs, yours to keep": "Des PDF, à toi pour toujours",
      "Free, and they stay free": "Gratuits, et ils le restent",
      "One email, no spam": "Un e-mail, aucun spam",
      "Players downloaded them": "Joueurs les ont téléchargés",
      "Chapters + 12 drills": "Chapitres + 12 exercices",
      "Reader rating": "Note des lecteurs",
      "Which do you want?": "Lequel tu veux ?",
      "Instant": "Immédiat",
      "Take both — they're free, and most people play both.":
        "Prends les deux — ils sont gratuits, et la plupart jouent aux deux.",
      "Also send me one email a month with new guides and patch notes. Nothing else, and one click unsubscribes.":
        "Envoyez-moi aussi un e-mail par mois avec les nouveaux guides et les notes de patch. Rien d’autre, et un clic pour se désabonner.",
      "We never sell your address.": "On ne vend jamais ton adresse.",
      "Privacy policy": "Politique de confidentialité",
      "Check your inbox.": "Regarde ta boîte mail.",
      "on the way to": "en route vers",
      "If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        "Si rien n’arrive en deux minutes, regarde dans les promotions — ça y atterrit parfois d’abord.",
      "Use a different address": "Utiliser une autre adresse",
      /* CTA labels, helper, note, success line — swapped at runtime via esbT */
      "Send me both guides": "Envoyez-moi les deux guides",
      "Send me the League guide": "Envoyez-moi le guide League",
      "Send me the Valorant guide": "Envoyez-moi le guide Valorant",
      "Pick a guide first": "Choisis d’abord un guide",
      "Both guides, one email, two attachments.": "Deux guides, un e-mail, deux pièces jointes.",
      "Only one? The other is free too.": "Un seul ? L’autre est gratuit aussi.",
      "Pick at least one guide.": "Choisis au moins un guide.",
      "Used to send the guides. Nothing else unless you tick the box below.":
        "Sert à envoyer les guides. Rien d’autre, sauf si tu coches la case ci-dessous.",
      "Enter an address we can send the PDFs to.": "Indique une adresse pour recevoir les PDF.",
      "Arrives in about a minute. No card, no account.":
        "Arrive en une minute environ. Sans carte, sans compte.",
      "That address does not look right — check it and try again.":
        "Cette adresse a l’air incorrecte — vérifie-la et réessaie.",
      "Both guides are": "Les deux guides sont",
      "The League guide is": "Le guide League est",
      "The Valorant guide is": "Le guide Valorant est",
      "Your guide is": "Votre guide est",
      "What's inside": "Ce qu’ils contiennent",
      "Six chapters each, no padding.": "Six chapitres chacun, sans remplissage.",
      "Who wrote them": "Qui les a écrits",
      "Written by people who play these ranks for a living.":
        "Écrits par des gens qui jouent ces rangs pour vivre.",
      "The authors": "Les auteurs",
      "Seven authors across two games": "Sept auteurs sur deux jeux",
      "Rewritten every patch cycle": "Réécrits à chaque cycle de patch",
      "Readers": "Lecteurs",
      "What they changed for them.": "Ce qu’ils ont changé pour eux.",
      "Before you hand over an email": "Avant de donner ton e-mail",
      "Fair questions. We would ask them too.": "Questions légitimes. On se les poserait aussi.",
      "Two guides. One email address.": "Deux guides. Une adresse e-mail.",
      "Never sold, never rented": "Jamais vendue, jamais louée",
      "One click unsubscribes": "Un clic pour se désabonner",
      "Send them": "Envoyez-les",

      /* ── game pages: the six proof bands (design_handoff_lol_game_page) ──
         Ported after the dictionary was last swept, so the whole run below the
         configurator shipped in English on all nine ladders. The `{}` entries
         are the sentences that name the game, its publisher or its rank floor:
         one entry each instead of nine, and the placeholder sits where French
         word order wants it, not where English left it. */
      "Our {} boosters.": "Nos boosters {}.",
      "From {} orders this month.": "Sur les commandes {} ce mois-ci.",
      "Asked before every {} order": "Demandé avant chaque commande {}",
      "It goes on the board and a verified {} booster takes it. If nothing claims it within 24 hours, the order refunds itself.":
        "Elle part sur le tableau et un booster {} vérifié la prend. Si personne ne la prend sous 24 heures, la commande se rembourse toute seule.",
      "{} of them, {} only — {} or above, with a clean account history and a name you can look up. Order without naming anyone and it goes to whoever is free; name one and it waits for them.":
        "{} au total, sur {} uniquement — {} ou au-dessus, avec un compte sans sanction et un pseudo que tu peux vérifier. Commande sans désigner personne et elle part au premier dispo ; désignes-en un et elle l’attend.",
      "{} flags accounts on patterns, not accusations: a login from the other side of the world, a sudden change in hours, a win rate that doesn't look human. So we don't produce any of those patterns. Your booster connects through an enterprise VPN in your region, plays inside the hours you set, and keeps your settings.":
        "{} repère les comptes sur des schémas, pas sur des accusations : une connexion à l’autre bout du monde, un changement brusque d’horaires, un winrate qui n’a rien d’humain. On ne produit donc aucun de ces schémas. Ton booster se connecte via un VPN professionnel dans ta région, joue dans les horaires que tu fixes et garde tes réglages.",
      "Boosting is against {}'s terms of service. We have never had an account actioned for any of our {} clients and we recover any that are, but nobody honest will tell you the risk is zero — and anyone who does is selling you something.":
        "Le boosting est contraire aux conditions d’utilisation de {}. Aucun compte n’a jamais été sanctionné parmi nos {} clients, et on récupère ceux qui le seraient ; mais personne d’honnête ne te dira que le risque est nul — et quiconque l’affirme a quelque chose à te vendre.",
      /* The roster sentence spells its own count, so the capture is a WORD and
         gets the exact lookup patTranslate() runs on the way out. A roster size
         that lands on a spelling not listed here passes through in English —
         add it rather than leaving it. */
      "Four": "Quatre",
      "Twenty-nine": "Vingt-neuf",
      "Thirty-one": "Trente et un",

      /* 01 How it runs */
      "Four steps, and you can see all of them.": "Quatre étapes, et tu les vois toutes.",
      "The number you see is the number you pay. Nothing is added later, and no account is needed to buy.":
        "Le montant affiché est celui que tu paies. Rien ne s’ajoute ensuite, et aucun compte n’est nécessaire pour acheter.",
      "Price fixed at checkout": "Prix figé au paiement",
      "A booster claims it": "Un booster la prend",
      "Median 18 minutes": "18 minutes en médiane",
      "Watch it climb": "Regarde ça monter",
      "Every game appears on your order page with the result, the KDA and the LP swing. Pause it any time you want to play.":
        "Chaque partie apparaît sur ta page de commande avec le résultat, le KDA et l’écart de LP. Mets en pause dès que tu veux jouer.",
      "Updated as games finish": "Mis à jour à la fin de chaque partie",
      "Finished, or refunded": "Livrée, ou remboursée",
      "Delivered to the rank you set. Anything not delivered is refunded pro-rata, any time the order is open.":
        "Livrée au rang que tu as fixé. Tout ce qui ne l’est pas est remboursé au prorata, à tout moment tant que la commande est ouverte.",
      "Back within 5 business days": "Remboursé sous 5 jours ouvrés",

      /* 02 While it runs */
      "While it runs": "Pendant la commande",
      "Watch every game land.": "Regarde chaque partie tomber.",
      "The order page opens from the link we email you — no password, no app. It updates as games finish, so you never have to ask where things are.":
        "La page de commande s’ouvre depuis le lien qu’on t’envoie par e-mail — sans mot de passe, sans application. Elle se met à jour à la fin de chaque partie : tu n’as jamais à demander où ça en est.",
      "The LP graph, not a percentage": "La courbe de LP, pas un pourcentage",
      "The RR graph, not a percentage": "La courbe de RR, pas un pourcentage",
      "Every game plotted from the rank you started at, so a bad night is visible instead of averaged away.":
        "Chaque partie tracée depuis ton rang de départ : une mauvaise soirée se voit au lieu d’être noyée dans une moyenne.",
      "Match history with replays": "Historique des parties avec replays",
      "Result, KDA and LP for every game, each with a replay link that stays live for 14 days.":
        "Résultat, KDA et LP pour chaque partie, avec un lien de replay actif pendant 14 jours.",
      "Result, KDA and RR for every game, each with a replay link that stays live for 14 days.":
        "Résultat, KDA et RR pour chaque partie, avec un lien de replay actif pendant 14 jours.",
      "One thread with your booster": "Un seul fil avec ton booster",
      "Ask for a champion, a pause or a swap. Support reads the same thread, so nothing gets repeated.":
        "Demande un champion, une pause ou un changement. Le support lit le même fil : rien à répéter.",
      "games this order": "parties sur cette commande",

      /* 03 Who plays it */
      "Who plays it": "Qui y joue",
      "Rank verified every month": "Rang vérifié chaque mois",
      "One free swap, no reason needed": "Un changement gratuit, sans justification",

      /* 04 Safety */
      "Why this doesn't get you banned.": "Pourquoi tu ne te fais pas bannir.",
      "Enterprise VPN matched to your region": "VPN professionnel dans ta région",
      "Not a consumer VPN, and never a datacentre IP.":
        "Pas un VPN grand public, et jamais une IP de centre de données.",
      "Your sensitivity, your crosshair, your runes": "Ta sensibilité, ton viseur, tes runes",
      "Settings are mirrored at the start and restored at the end.":
        "Tes réglages sont copiés au début et rétablis à la fin.",
      "You set the window at checkout. Nothing runs at 04:00 unless you do.":
        "Tu fixes la plage horaire au paiement. Rien ne tourne à 4 h du matin sauf si c’est toi qui le décides.",
      "Offline appearance for the whole order": "Statut hors ligne pendant toute la commande",
      "Friends see you offline until it finishes.": "Tes amis te voient hors ligne jusqu’à la fin.",
      "In duo your booster queues beside you from their own account.":
        "En duo, ton booster lance la file à côté de toi depuis son propre compte.",

      /* 05 Reviews */
      "Read them all": "Lire tous les avis",

      /* 06 FAQ */
      "If yours isn't here, Discord answers in about four minutes and you don't need an order to ask.":
        "Si la tienne n’y est pas, Discord répond en quatre minutes environ, et tu n’as pas besoin d’une commande pour poser la question.",
      "Do you need my account login?": "Avez-vous besoin de mes identifiants ?",
      "For solo, yes — your booster signs in and plays, through a VPN in your region and inside the hours you set. For duo, no: they queue beside you from their own account and never see your login at all. Either way we never ask for your email password or your 2FA codes.":
        "En solo, oui — ton booster se connecte et joue, via un VPN dans ta région et dans les horaires que tu fixes. En duo, non : il lance la file à côté de toi depuis son propre compte et ne voit jamais tes identifiants. Dans les deux cas, on ne demande jamais le mot de passe de ta boîte mail ni tes codes 2FA.",
      "Can I play while the order is running?": "Puis-je jouer pendant la commande ?",
      "What happens if it goes past the estimate?": "Que se passe-t-il en cas de dépassement du délai ?",
      "A 15% credit applies automatically once the order runs past its window, and it shows on the order page without anyone asking. If it is badly over, we move it to a booster who is free.":
        "Un avoir de 15 % s’applique automatiquement dès qu’une commande dépasse sa fenêtre, et il apparaît sur la page de commande sans rien demander. En cas de gros retard, on la confie à un booster dispo.",
      "Why is duo more expensive?": "Pourquoi le duo coûte-t-il plus cher ?",
      "It takes longer. Your booster carries a live player rather than playing every role freely, so the same climb costs 55% more and takes longer. It is the safer option and we would rather price it honestly than hide the difference.":
        "Parce que c’est plus long. Ton booster porte un joueur en direct au lieu de jouer chaque rôle librement : la même montée coûte 55 % de plus et prend plus de temps. C’est l’option la plus sûre, et on préfère l’afficher honnêtement plutôt que masquer l’écart.",
      "How do I follow the order without an account?": "Comment suivre la commande sans compte ?",
      "The confirmation email carries a link that is the login. It never expires, works on any device, and opens the same dashboard shown above. Lost it? The demo page resends it to the address you paid with.":
        "L’e-mail de confirmation contient un lien qui tient lieu de connexion. Il n’expire jamais, marche sur tous les appareils et ouvre le tableau de bord montré ci-dessus. Perdu ? La page de démo le renvoie à l’adresse utilisée pour payer.",
      "Can I choose the champions they play?": "Puis-je choisir les champions qu’il joue ?",
      "Can I choose the agents they play?": "Puis-je choisir les agents qu’il joue ?",
      "Can I choose the roles they play?": "Puis-je choisir les rôles qu’il joue ?",
      "Can I choose the playlist they play?": "Puis-je choisir la playlist qu’il joue ?",

      /* the hero lede, one per ladder */
      "Solo/duo and flex, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Solo/duo et flex, sur NA et EU. Ton booster joue ton compte dans tes horaires habituels avec un VPN régional, ou lance la file à côté de toi en duo sans jamais toucher à tes identifiants.",
      "Competitive and unrated, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Compétitif et non classé, sur NA et EU. Ton booster joue ton compte dans tes horaires habituels avec un VPN régional, ou lance la file à côté de toi en duo sans jamais toucher à tes identifiants.",
      "Premier CS Rating and Faceit levels, run by FPL-adjacent players. Anti-cheat safe patterns, no smurf stacking, no rating farm scripts.":
        "CS Rating Premier et niveaux Faceit, assurés par des joueurs proches du FPL. Des schémas sans risque pour l’anti-triche, pas d’empilement de smurfs, pas de scripts de farm de rating.",
      "1v1, 2v2 and 3v3 playlists, tournament wins, and duo sessions where the booster calls rotations live on voice.":
        "Playlists 1c1, 2c2 et 3c3, victoires en tournoi, et sessions duo où le booster annonce les rotations en direct sur vocal.",

      /* the bundle strip */
      "Save big on bundles": "Grosses économies sur les packs",
      "Whole-ladder climbs at one flat price": "Des montées d’échelle entière à prix fixe",
      "Two tiers up in one order, from wherever you are":
        "Deux paliers de plus en une commande, d’où que tu partes",
      "Two rating bands up in one order": "Deux tranches de rating de plus en une commande",
      "Up to {}% off": "Jusqu’à −{} %",
      /* "Depuis n'importe quelle division {}" is the natural phrasing and it
         wrapped to a second line on a 216px bundle card where the English fits
         on one, leaving one card in the row of three taller than its
         neighbours. Shortened to fit the card it actually ships in. */
      "From any {} division": "Depuis toute division {}",
      "Starts at {}": "À partir de {}",
      "Apply bundle": "Appliquer le pack",
      "Applied": "Appliqué",
      "Played in your preferred hours": "Joué à tes heures préférées",

      /* net wins / placements */
      "per game": "par partie",
      "A net win means one win above your losses — five is the cap per order.":
        "Une victoire nette, c’est une victoire de plus que tes défaites — cinq maximum par commande.",
      "A placement game sets or resets your rank — five is the cap per order.":
        "Une partie de placement fixe ou réinitialise ton rang — cinq maximum par commande.",
      "I have a rank": "J’ai un rang",
      "Unranked": "Non classé",
      "Fresh account or a new season — no MMR to read yet. Your booster plays all five and the rank you land is the rank you keep.":
        "Compte neuf ou nouvelle saison — aucun MMR à lire pour l’instant. Ton booster joue les cinq parties et le rang obtenu est celui que tu gardes.",

      /* coaching */
      "Pick your coach": "Choisis ton coach",
      "How many hours": "Combien d’heures",
      "What to work on": "Sur quoi travailler",
      "First session": "Première session",
      "per hour": "de l’heure",
      "Single session": "Session unique",
      "Save {}%": "−{} %",
      "Laning": "Phase de lane",
      "Macro & rotations": "Macro et rotations",
      "Champion pool": "Pool de champions",
      "VOD review": "Analyse de VOD",
      "coaches taking bookings": "coachs prennent des réservations",
      "taking bookings": "prend des réservations",
      "Live on Discord, screen shared, recorded for you to keep.":
        "En direct sur Discord, écran partagé, enregistré et gardé pour toi.",

      /* ── the support page ─────────────────────────────────────────────── */
      "Two ways in. Both are read by people.": "Deux entrées. Les deux sont lues par des humains.",
      "Staffed right now": "Équipe en ligne",
      "— someone is in #support": "— quelqu’un est dans #support",
      "Median first reply": "Premier retour médian",
      "Open 24/7": "Ouvert 24/7",
      "Attachments and receipts welcome": "Pièces jointes et reçus bienvenus",
      "Copy address": "Copier l’adresse",
      "Write in": "Écris-nous",
      "Or write it here": "Ou écris-le ici",
      "What to put in it": "Ce qu’il faut y mettre",
      "The order number": "Le numéro de commande",
      "Anything starting ESB-. It skips triage and lands with the person on that order.":
        "Tout ce qui commence par ESB-. Ça saute le tri et arrive chez la personne qui suit la commande.",
      "What you expected": "Ce que tu attendais",
      "The rank, the date, the thing the checkout said you were buying.":
        "Le rang, la date, ce que le paiement disait que tu achetais.",
      "What actually happened": "Ce qui s’est réellement passé",
      "Screenshots beat descriptions. Paste them straight into the thread.":
        "Une capture vaut mieux qu’une description. Colle-la directement dans le fil.",
      "Nothing else": "Rien d’autre",
      "No passwords, no 2FA codes. Support will never ask for one, and won't act on a message that contains one.":
        "Pas de mot de passe, pas de code 2FA. Le support n’en demandera jamais et ne traitera pas un message qui en contient un.",
      "What's it about": "De quoi s’agit-il",
      "Order issue": "Problème de commande",
      "Refund": "Remboursement",
      "Booster swap": "Changement de booster",
      "Before I buy": "Avant d’acheter",
      "Something else": "Autre chose",
      "Company": "Société",
      "One thread per message. Discord and email land in the same place, so pick either — not both.":
        "Un fil par message. Discord et l’e-mail arrivent au même endroit : choisis l’un ou l’autre, pas les deux.",
      "Add an email we can reply to, and a line or two about what happened.":
        "Ajoute un e-mail où te répondre, et une ligne ou deux sur ce qui s’est passé.",
      "We never ask for your game password here, or anywhere else.":
        "On ne te demande jamais ton mot de passe de jeu, ni ici ni ailleurs.",
      "Six answers that between them close most of the tickets we get. If yours isn't here, Discord is two clicks away.":
        "Six réponses qui règlent à elles seules la plupart de nos tickets. Si la tienne n’y est pas, Discord est à deux clics.",
      "Where is my order? I never made an account.": "Où est ma commande ? Je n’ai jamais créé de compte.",
      "You do not need one. Guest orders are tracked by the link we emailed when you paid — it never expires and works on any device. Lost it? Open the order lookup, enter the address you paid with, and we send it again.":
        "Tu n’en as pas besoin. Les commandes invité se suivent avec le lien envoyé par e-mail au moment du paiement — il n’expire jamais et marche sur tous les appareils. Perdu ? Ouvre la recherche de commande, saisis l’adresse utilisée pour payer, et on te le renvoie.",
      "Nobody has claimed my order yet.": "Personne n’a encore pris ma commande.",
      "Median claim time is 18 min, and most of the rest go within the hour. If nothing has claimed it 24 hours after payment, the order refunds itself automatically — no ticket, no asking. Writing in before that does not move it up the board.":
        "Le délai médian de prise en charge est de 18 min, et la plupart des autres partent dans l’heure. Si rien ne l’a prise 24 heures après le paiement, la commande se rembourse toute seule — sans ticket, sans démarche. Nous écrire avant ne la fait pas remonter sur le tableau.",
      "Can I get a refund?": "Puis-je être remboursé ?",
      "In full, any time before a booster claims it. After that it is pro-rated on what has not been delivered — you keep the divisions already climbed and get the rest back. Money lands on the original payment method within 5 business days.":
        "Intégralement, à tout moment avant qu’un booster ne la prenne. Ensuite c’est au prorata de ce qui n’a pas été livré — tu gardes les divisions déjà montées et on te rend le reste. L’argent revient sur le moyen de paiement d’origine sous 5 jours ouvrés.",
      "Can I swap to a different booster?": "Puis-je changer de booster ?",
      "Yes, once per order, at no charge. Ask in the order thread. The order goes back on the board and is usually re-claimed the same day; if you would rather not say why, do not — we do not ask.":
        "Oui, une fois par commande et sans frais. Demande-le dans le fil de la commande. Elle retourne sur le tableau et repart en général le jour même ; si tu préfères ne pas dire pourquoi, ne le dis pas — on ne demande pas.",
      "Can I play on my account while an order is running?":
        "Puis-je jouer sur mon compte pendant une commande ?",
      "My order is past the delivery estimate.": "Ma commande a dépassé le délai annoncé.",
      "A 15% credit applies automatically once an order runs past its window, and it shows on the order page without anyone having to ask. If it is badly over, write in and we will move it to a booster who is free.":
        "Un avoir de 15 % s’applique automatiquement dès qu’une commande dépasse sa fenêtre, et il apparaît sur la page de commande sans rien avoir à demander. En cas de gros retard, écris-nous et on la confie à un booster dispo.",
      "Still stuck? Ask us.": "Toujours bloqué ? Écris-nous.",
      "Discord is the fast one — our staff sit in it all day. Or write in above and it lands in the same inbox.":
        "Discord est le plus rapide — notre équipe y est toute la journée. Ou écris-nous ci-dessus : ça arrive dans la même boîte.",
      "Ask us": "Écris-nous",

      /* ── the free-guides landing ──────────────────────────────────────── */
      "One for League, one for Valorant. Six chapters and six drills each, on the things that decide games between Silver and Ascendant. Written by the people on our roster who play those ranks every day.":
        "Un pour League, un pour Valorant. Six chapitres et six exercices chacun, sur ce qui décide les parties entre Silver et Ascendant. Écrits par les membres de notre roster qui jouent ces rangs tous les jours.",
      "Win the lane you already won.": "Gagne la lane que tu avais déjà gagnée.",
      "Stop losing rounds you already won.": "Arrête de perdre les rounds que tu avais gagnés.",
      "6 chapters · 6 drills": "6 chapitres · 6 exercices",
      "The League field guide": "Le guide de terrain League",
      "The Valorant field guide": "Le guide de terrain Valorant",
      "Iron to Diamond · wave control, roams, objectives":
        "D’Iron à Diamond · gestion des vagues, roams, objectifs",
      "Iron to Ascendant · crosshair, economy, retakes": "D’Iron à Ascendant · viseur, économie, retakes",
      ". If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        ". Si rien n’arrive en deux minutes, regarde dans les promotions — ça y atterrit parfois d’abord.",
      "From the team behind": "De l’équipe derrière",
      "and 4.7 / 5 on Trustpilot.": "et 4,7 / 5 sur Trustpilot.",
      "Every chapter ends with a drill you can run in a custom game in under ten minutes. That is the whole format: read it, then do it.":
        "Chaque chapitre se termine par un exercice à faire en partie personnalisée en moins de dix minutes. C’est tout le format : on lit, puis on fait.",
      "Drill": "Exercice",
      "Wave control": "Gestion des vagues",
      "Freeze, slow-push, crash — and which one the minute demands.":
        "Freeze, slow-push, crash — et lequel la minute réclame.",
      "Trading, not fighting": "Trader, pas se battre",
      "Why the lane is won by who spends time better, not who hits harder.":
        "Pourquoi la lane se gagne par celui qui gère mieux son temps, pas par celui qui tape le plus fort.",
      "Roams that pay": "Des roams rentables",
      "The three windows where leaving lane gains more than it costs.":
        "Les trois fenêtres où quitter la lane rapporte plus que cela ne coûte.",
      "Objectives as maths": "Les objectifs, c’est du calcul",
      "Dragon, herald and the setup that starts 40 seconds early.":
        "Dragon, héraut et la mise en place qui commence 40 secondes plus tôt.",
      "Six habits that cap your rank": "Six habitudes qui plafonnent ton rang",
      "Each with the tell you can spot in your own replays.":
        "Chacune avec l’indice repérable dans tes propres replays.",
      "Each with the tell you can spot in your own VODs.":
        "Chacune avec l’indice repérable dans tes propres VOD.",
      "The climb plan": "Le plan de montée",
      "Twelve ranked games a week, structured.": "Douze parties classées par semaine, structurées.",
      "Crosshair placement": "Placement du viseur",
      "Where the dot sits before you peek, not after.": "Où est le point avant de peek, pas après.",
      "Economy you can trust": "Une éco fiable",
      "When to force, when to save, and why the half-buy loses.":
        "Quand forcer, quand save, et pourquoi le half-buy perd.",
      "Retakes and the four-second rule": "Les retakes et la règle des quatre secondes",
      "Most retakes are lost before anyone shoots.":
        "La plupart des retakes sont perdus avant le premier tir.",
      "Utility that buys space": "L’utilitaire qui achète de l’espace",
      "Smokes and flashes as currency.": "Smokes et flashs comme monnaie d’échange.",
      "Not a content team reading patch notes. Boosters from our own roster wrote a chapter each, and every claim is something they do in ranked that week — not theory borrowed from a pro scene you will never play in.":
        "Pas une équipe de contenu qui lit les patch notes. Des boosters de notre propre roster ont écrit un chapitre chacun, et chaque affirmation est quelque chose qu’ils font en classé cette semaine-là — pas de la théorie piquée à une scène pro où tu ne joueras jamais.",
      "From 1,100 readers": "Sur 1 100 lecteurs",
      "Is it actually free, or free-ish?": "C’est vraiment gratuit, ou presque gratuit ?",
      "Free. There is no card, no trial, and no upsell inside either PDF. We publish them because a player who improves is a player who stays in the game, and some of them buy a boost or a coaching hour later. That is the whole business case.":
        "Gratuit. Pas de carte, pas d’essai, aucune vente additionnelle dans les PDF. On les publie parce qu’un joueur qui progresse est un joueur qui reste, et que certains achètent un boost ou une heure de coaching plus tard. Voilà tout le modèle.",
      "Can I take both?": "Puis-je prendre les deux ?",
      "Yes, and most people do — both are ticked by default. They arrive as two attachments in one email, so taking the second one costs you nothing extra, not even another form.":
        "Oui, et la plupart le font — les deux sont cochés par défaut. Ils arrivent en deux pièces jointes dans un seul e-mail : prendre le second ne te coûte rien de plus, pas même un autre formulaire.",
      "What do you do with my email?": "Que faites-vous de mon e-mail ?",
      "Send you the guides. If you tick the box, one email a month with new guides and patch notes. We never sell or rent the list, and one click unsubscribes — the link is in every email, not buried in a preference centre.":
        "T’envoyer les guides. Si tu coches la case, un e-mail par mois avec les nouveaux guides et les patch notes. On ne vend ni ne loue jamais la liste, et un clic suffit pour se désabonner — le lien est dans chaque e-mail, pas enfoui dans un centre de préférences.",
      "What rank are these written for?": "Pour quel rang sont-ils écrits ?",
      "Iron through Diamond for League, Iron through Ascendant for Valorant. The early chapters do most of the work at lower ranks; the habit and objective chapters matter more once you are past Platinum.":
        "D’Iron à Diamond pour League, d’Iron à Ascendant pour Valorant. Les premiers chapitres font l’essentiel du travail aux rangs bas ; ceux sur les habitudes et les objectifs comptent davantage une fois Platinum passé.",
      "Do I need to buy boosting to use them?": "Faut-il acheter un boost pour les utiliser ?",
      "No, and neither guide mentions our services beyond one line on the last page. If you would rather someone else did the climbing, that is a different page on this site — this one is for doing it yourself.":
        "Non, et aucun des deux guides ne parle de nos services au-delà d’une ligne en dernière page. Si tu préfères que quelqu’un d’autre fasse la montée, c’est une autre page du site — celle-ci est pour la faire toi-même.",

      /* ── homepage, checkout and the odds and ends ─────────────────────── */
      "Know your exact price in seconds. A verified booster claims your order in about 18 minutes — and until one does, every cent is refundable.":
        "Ton prix exact en quelques secondes. Un booster vérifié prend ta commande en 18 minutes environ — et tant que personne ne l’a prise, chaque centime est remboursable.",
      "Best Sellers": "Meilleures ventes",
      "Fast checkout": "Paiement rapide",
      "You are here": "Tu es ici",
      "You are here tier": "Palier où tu es",
      "You want to be": "Tu vises",
      "You want to be tier": "Palier visé",
      "Your region": "Ta région",
      "Nine games": "Neuf jeux",
      "Start an order": "Lancer une commande",
      "Ask in Discord": "Demander sur Discord",
      "Median first reply on Discord last month: 3m 40s.":
        "Premier retour médian sur Discord le mois dernier : 3 min 40 s.",
      "with vantaa": "avec vantaa",
      "Duo queue · +55%": "Duo · +55 %",

      /* The roster line is split around its <b>count</b>, so it is two nodes and
         each needs its own entry — the figure never enters the dictionary. */
      "more {} boosters": "boosters {} de plus",
      "more {} booster": "booster {} de plus",
      "on the roster, all {} or above.": "sur le roster, tous {} ou au-dessus.",
      "on Trustpilot · {} reviews": "sur Trustpilot · {} avis",
      "{} reviews on Trustpilot": "{} avis sur Trustpilot",
      "· {} reviews": "· {} avis",
      /* The capture is the game's own picks add-on, which is already a key
         above ("Champions & roles"), so patTranslate()'s lookup renders the
         French name inside the French sentence. ⚠ the English source reads
         "Yes — It is free", a stray capital from the way build.py joins the
         clause; the French is written correctly rather than reproducing it. */
      "Yes — It is free on every order, not an upsell — \"{}\" is ticked before you configure anything. Your booster plays a pool you pick, which also keeps the match history plausible, and you can change it mid-order in the thread.":
        "Oui — c’est gratuit sur chaque commande, pas une option payante : « {} » est coché avant même que tu configures quoi que ce soit. Ton booster joue un pool que tu choisis, ce qui rend aussi l’historique de parties plausible, et tu peux le changer en cours de commande dans le fil.",
      "Pause it first, from the order page. Pausing is free and resumes the same night if a slot is open. What you should not do is queue ranked alongside an unpaused solo order — two people on one account in the same queue is the fastest way to get flagged.":
        "Mets-la d’abord en pause, depuis la page de commande. La pause est gratuite et ça repart le soir même si un créneau est libre. Ce qu’il ne faut pas faire, c’est lancer du classé en parallèle d’une commande solo non mise en pause — deux personnes sur un compte dans la même file, c’est le moyen le plus rapide de se faire repérer.",

      /* mobile stat row, coaching slots and the roles under a booster's name */
      "To claim": "Prise en charge",
      "Tonight, 20:00": "Ce soir, 20:00",
      "Tomorrow, 18:00": "Demain, 18:00",
      "Saturday, 15:00": "Samedi, 15:00",
      "Sunday, 12:00": "Dimanche, 12:00",
      "Mid lane": "Mid lane",
      "Duelist": "Duelliste",
      "Initiator": "Initiateur",
      "Sentinel": "Sentinelle",
      "Rocket League, Apex Legends and Counter-Strike 2": "Rocket League, Apex Legends et Counter-Strike 2",
      "3m 40s": "3 min 40 s",

      /* the mystery discount — design_handoff_mystery_discount. Every step of
         the card ships in the DOM, so all five are translated here; the card
         letter, the issued code, the money and the countdown are in SKIP. */
      "Mystery discount": "Remise mystère",
      /* The other two labels a server-resolved offer can carry on the
         checkout receipt. Untranslated they render in English beside a
         French price — the one line on that page naming the discount. */
      "Last-chance discount": "Remise dernière chance",
      "Come back offer": "Offre retour",
      "Sealed for you": "Scellée pour toi",
      "A mystery discount": "Une remise mystère",
      "on this order": "sur cette commande",
      "One per customer": "Une par client",
      "Up to": "Jusqu’à",
      "off": "de remise",
      "The deck holds": "Le paquet contient",
      /* One node rather than three digits: French puts a non-breaking space
         before every `%` and joins with "et", so this is a phrase, not a list
         a mechanical substitution could assemble. Tied to BINGO_PCT = 0.30 —
         re-word it if the deck is ever re-cut. */
      "10%, 20% and 30%": "10 %, 20 % et 30 %",
      "off the order you just configured. Pick a card, tell us where to send the code, and we open it on the spot.":
        "de réduction sur la commande que tu viens de configurer. Choisis une carte, dis-nous où envoyer le code, et on l’ouvre sur-le-champ.",
      "Picked": "Choisie",
      "Hold card": "Réserver la carte",
      "No thanks, I'll pay full price": "Non merci, je paie plein tarif",
      "held for you": "réservée pour vous",
      "Where should we send it?": "On l’envoie où ?",
      "We email the code so it survives a closed tab, then open the card on the next screen.":
        "On envoie le code par e-mail pour qu’il survive à un onglet fermé, puis on ouvre la carte à l’écran suivant.",
      "The card is opened on the next screen either way.":
        "La carte est ouverte à l’écran suivant dans tous les cas.",
      "Enter an address we can send the code to.": "Indique une adresse pour recevoir le code.",
      "That didn't go through. Try again in a moment.": "Ça n’a pas marché. Réessaie dans un instant.",
      "Also send me the free rank guides and patch notes. One email a month, one click to stop.":
        "Envoyez-moi aussi les guides de rang gratuits et les notes de patch. Un e-mail par mois, un clic pour arrêter.",
      "Never sold or rented.": "Jamais vendue ni louée.",
      "Open card": "Ouvrir la carte",
      "Opening card": "Ouverture de la carte",
      "Drawing your code on the server": "Génération de ton code sur le serveur",
      "Available for 1 hour": "Valable 1 heure",
      "left": "restantes",
      "Bingo — card": "Bingo — la carte",
      "pays the top rate": "donne le taux maximum",
      "The best rate in the deck — double the 15% sale, and live for 1 hour from the moment you opened it.":
        "Le meilleur taux du paquet — le double des 15 % de la promo, et valable 1 heure à partir du moment où tu l’as ouverte.",
      "Your order": "Ta commande",
      "Apply my discount": "Appliquer ma remise",
      "Continue at full price": "Continuer au prix fort",
      "Live for 1 hour on this order. A copy is in your inbox, so closing this tab doesn't lose it.":
        "Valable 1 heure sur cette commande. Une copie est dans ta boîte mail : fermer cet onglet ne la perd pas.",
      "Live for 1 hour on this order. Copy the code before you close this tab — we couldn't email it.":
        "Valable 1 heure sur cette commande. Copie le code avant de fermer cet onglet — on n’a pas pu te l’envoyer par e-mail.",
      "No problem.": "Pas de souci.",
      "This address already used its card.": "Cette adresse a déjà utilisé sa carte.",
      "Your order stays where it is and we won't ask again on this visit. The sitewide 15% code still applies at checkout.":
        "Ta commande reste telle quelle et on ne redemandera pas pendant cette visite. Le code de 15 % du site s’applique toujours au paiement.",
      "One card per customer, and this inbox has opened its one. The sitewide 15% code still applies at checkout.":
        "Une carte par client, et cette boîte mail a ouvert la sienne. Le code de 15 % du site s’applique toujours au paiement.",
      "Back to my order": "Retour à ma commande",
      "Actually, let me pick a card": "Finalement, je choisis une carte",

      /* ── strings the pages gained after the last sweep: the account
         prompt, the application form's four outcomes, and the three
         accessible names that were still reaching FR/DE readers in
         English. The promo chip's is a {} pattern because it is built
         from the live code and percentage. */
      "When you place an order it shows up here — the climb, the price and its status, updated as your booster works. Ready to start?":
        "Dès que tu passes une commande, elle apparaît ici — la montée, le prix et son statut, mis à jour au fil du travail de ton booster. On commence ?",
      "Almost — one more thing.": "Presque — encore une chose.",
      "Add your in-game name, peak rank, and a Discord we can reach you on.":
        "Ajoute ton pseudo en jeu, ton meilleur rang, et un Discord où te joindre.",
      "Application received.": "Candidature reçue.",
      "We'll message you on Discord — keep an eye out.": "On t’écrit sur Discord — garde un œil dessus.",
      "Nothing was emailed: this build has no mailbox configured. Send your application to":
        "Aucun e-mail n’a été envoyé : cette version n’a pas de boîte configurée. Envoie ta candidature à",
      "Rather than lose it, email": "Pour ne rien perdre, écris à",
      "with your rank and Discord.": "avec ton rang et ton Discord.",
      "Main": "Navigation principale",
      "Log in or create an account": "Se connecter ou créer un compte",
      "Copy discount code {} — {} off": "Copier le code promo {} — {} de réduction",
      "Copy discount code {}": "Copier le code promo {}",
      "Checking that code…": "Vérification du code…",

      /* ── /accounts.html — the ready-made-account board, its cross-sell
         strip on the League page, and the checkout's account variants.
         Listing NAMES and rank bands are data and stay in English with every
         other rank on the site; every sentence around them is translated. */
      "Accounts": "Comptes",
      "{} accounts": "Comptes {}",
      "Level 30 and ranked, on NA, EUW, EUNE and OCE. Full email access on every one, so you change the recovery mailbox and the password the moment it lands and it is genuinely yours.":
        "Niveau 30 et classés, sur NA, EUW, EUNE et OCE. Accès complet à l’e-mail sur chacun : tu changes la boîte de récupération et le mot de passe dès la livraison, et le compte est vraiment à toi.",
      "Full email access": "Accès complet à l’e-mail",
      "{}-day replacement": "Remplacement sous {} jours",
      "Within the hour": "Sous une heure",
      "Eight": "Huit",
      "{} listings": "{} annonces",
      "listings": "annonces",
      "Pick a rank and a shard.": "Choisis un rang et un serveur.",
      "Every account ships with full email access, on the shard you pick, replaced inside":
        "Chaque compte est livré avec l’accès complet à l’e-mail, sur le serveur que tu choisis, et remplacé sous",
      "days if it is recovered. The exact division inside a band is whatever is in stock that day.":
        "jours s’il est récupéré. La division exacte dans une fourchette dépend du stock du jour.",
      "All ranks": "Tous les rangs",
      "Shard": "Serveur",
      "Any shard": "Tous les serveurs",
      "In stock": "En stock",
      "Sold out": "Épuisé",
      "level": "niveau",
      "blue essence": "essence bleue",
      "champions": "champions",
      "Buy": "Acheter",
      "Ask when it is back": "Demander quand il revient",
      "A clean level-30 with the essence to build a pool from scratch. No ranked games played, so placements are yours.":
        "Un niveau 30 propre, avec de quoi se construire un pool de zéro. Aucune partie classée jouée : les placements sont à toi.",
      "The same account with roughly double the essence — enough for a full role's worth of champions on day one.":
        "Le même compte avec environ deux fois plus d’essence — de quoi couvrir un rôle entier dès le premier jour.",
      "Placed and played. The exact division inside the band depends on what is in stock the day you order.":
        "Placé et joué. La division exacte dans la fourchette dépend du stock le jour de ta commande.",
      "Last season's Gold, honour level 2 or above, no restrictions on the account.":
        "Gold la saison dernière, honneur niveau 2 minimum, aucune restriction sur le compte.",
      "Platinum with a played match history — it does not read as a fresh account to anybody in your games.":
        "Platine avec un historique de parties réel — personne dans tes games ne le lira comme un compte neuf.",
      "Emerald on a full champion pool. The smallest stock on the page, so the shard list is short.":
        "Émeraude avec un pool de champions complet. Le plus petit stock de la page, d’où la liste de serveurs réduite.",
      "Diamond, hand-played, with the match history behind it. Ships with the honour level intact.":
        "Diamant, joué à la main, avec l’historique qui va avec. Livré avec le niveau d’honneur intact.",
      "The top of what we sell as a fixed listing. Anything above Diamond I is quoted per account in Discord.":
        "Le haut de ce que nous vendons à prix fixe. Au-dessus de Diamant I, chaque compte est chiffré sur Discord.",
      "Nothing in stock on that combination.": "Rien en stock sur cette combinaison.",
      "We had no": "Nous n’avions aucun compte",
      "account for": "pour",
      "when this page was built. Loosen one of the two, or ask us in Discord — stock moves daily.":
        "au moment où cette page a été générée. Élargis l’un des deux, ou demande-nous sur Discord : le stock bouge tous les jours.",
      "Show everything": "Tout afficher",
      "What arrives": "Ce que tu reçois",
      "Credentials, and the mailbox behind them.":
        "Les identifiants, et la boîte mail derrière.",
      "Full email access — you change the email and the password on delivery. Without that an account is a rental somebody else can end, so we do not sell one we cannot hand over completely.":
        "Accès complet à l’e-mail : tu changes l’adresse et le mot de passe à la livraison. Sans ça, un compte n’est qu’une location que quelqu’un d’autre peut arrêter — nous n’en vendons donc aucun que nous ne pouvons pas céder entièrement.",
      "Credentials by email": "Identifiants par e-mail",
      "Login, password and the recovery mailbox, sent to the address you check out with.":
        "Identifiant, mot de passe et boîte de récupération, envoyés à l’adresse utilisée au paiement.",
      "Usually within the hour": "En général sous une heure",
      "Manually handed over and checked before it is sent. Not an automated drop.":
        "Remis à la main et vérifié avant l’envoi. Ce n’est pas une livraison automatique.",
      "Replaced inside {} days": "Remplacé sous {} jours",
      "If it is recovered or banned in the warranty window you get another of the same rank, or the money back.":
        "S’il est récupéré ou banni pendant la garantie, tu en reçois un autre du même rang, ou tu es remboursé.",
      "Never resold": "Jamais revendu",
      "A listing leaves this page the moment it is sold. One buyer per account.":
        "Une annonce quitte cette page dès qu’elle est vendue. Un seul acheteur par compte.",
      "The risk": "Le risque",
      "What Riot's rules actually say.": "Ce que disent vraiment les règles de Riot.",
      "The same standard as the rest of the site: we tell you what the risk is, what we do about it, and where our warranty stops.":
        "La même règle que sur le reste du site : nous disons quel est le risque, ce que nous faisons contre, et où s’arrête notre garantie.",
      "Riot licenses an account to one person and does not permit it to be sold or transferred. If they act on that, the sanction is the account itself, not a suspension you sit out. We hand over full email access so the account is genuinely yours to secure, and we replace it inside the warranty window — but we will not tell you the risk is zero, because it isn't.":
        "Riot concède un compte à une seule personne et n’autorise ni sa vente ni son transfert. S’ils agissent, la sanction porte sur le compte lui-même, pas sur une suspension que l’on attend. Nous cédons l’accès complet à l’e-mail pour que le compte soit vraiment à vous et sécurisable, et nous le remplaçons pendant la garantie — mais nous ne vous dirons pas que le risque est nul, parce qu’il ne l’est pas.",
      "Read the full guarantee": "Lire toute la garantie",
      "Questions": "Questions",
      "The ones that decide it.": "Celles qui font la décision.",
      "Three of these argue against the sale. They are the reason the other four are worth reading.":
        "Trois d’entre elles jouent contre la vente. C’est pour ça que les quatre autres valent la lecture.",
      "Ask us anything else": "Pose-nous n’importe quelle autre question",
      "Is buying an account against Riot's rules?":
        "Acheter un compte, est-ce contraire aux règles de Riot ?",
      "Yes. An account is licensed to one person and Riot does not permit it to be sold or transferred. If they act on it, the account goes — that is a different outcome from a boosting suspension, and it is the reason the warranty below exists. Anyone telling you this is risk-free is selling you something.":
        "Oui. Un compte est concédé à une seule personne et Riot n’autorise ni sa vente ni son transfert. S’ils agissent, le compte disparaît — ce n’est pas la même issue qu’une suspension pour boost, et c’est la raison d’être de la garantie ci-dessous. Quiconque te dit que c’est sans risque a quelque chose à te vendre.",
      "Do I actually own it, or can you take it back?":
        "Est-ce qu’il est vraiment à moi, ou pouvez-vous le reprendre ?",
      "Every listing ships with full email access. You change the recovery mailbox and the password on delivery and we no longer hold anything that reaches it. We do not sell accounts we cannot hand over completely — an account without its email is a rental somebody else can end.":
        "Chaque annonce est livrée avec l’accès complet à l’e-mail. Tu changes la boîte de récupération et le mot de passe à la livraison, et nous ne détenons plus rien qui y donne accès. Nous ne vendons aucun compte que nous ne pouvons pas céder entièrement — un compte sans son e-mail est une location que quelqu’un d’autre peut arrêter.",
      "What happens if it is banned or recovered?":
        "Que se passe-t-il s’il est banni ou récupéré ?",
      "Inside {} days of delivery you get another account of the same rank, or the money back, your choice. After that window we cannot tell a recovery from a chargeback, so the warranty ends — that is the honest limit of it, and it is why the window is stated rather than implied.":
        "Dans les {} jours suivant la livraison, tu reçois un autre compte du même rang, ou tu es remboursé, au choix. Passé ce délai, nous ne pouvons plus distinguer une récupération d’une rétrofacturation, donc la garantie s’arrête — c’est sa limite honnête, et c’est pour ça que le délai est écrit plutôt que sous-entendu.",
      "Can I pick the exact division?": "Puis-je choisir la division exacte ?",
      "No. A listing names a band — Gold IV to Gold I — and you get what is in stock the day you order, inside that band. We do not know which one it will be when you buy, so we do not print a division we might not have.":
        "Non. Une annonce donne une fourchette — Gold IV à Gold I — et tu obtiens ce qui est en stock le jour de ta commande, dans cette fourchette. Nous ne savons pas laquelle ce sera au moment de l’achat, donc nous n’affichons pas une division que nous n’aurons peut-être pas.",
      "How fast is delivery?": "En combien de temps est-il livré ?",
      "Usually inside the hour, in the working day. Each handover is done by a person who checks the account first, so it is not instant and we do not claim it is — an automated drop is how buyers end up with an account somebody already logged into.":
        "En général sous une heure, en journée. Chaque remise est faite par une personne qui vérifie le compte avant, donc ce n’est pas instantané et nous ne le prétendons pas — c’est la livraison automatique qui fait atterrir les acheteurs sur un compte où quelqu’un s’est déjà connecté.",
      "Should I buy an account or a boost?": "Dois-je acheter un compte ou un boost ?",
      "If you want to keep your own name, your skins and your match history, buy the boost — it is the same rank on the account you already play. An account makes sense when you want a second one to queue on, or a clean shard to start on. If you are choosing between them on price alone, the boost is usually the better purchase.":
        "Si tu veux garder ton pseudo, tes skins et ton historique, prends le boost — c’est le même rang sur le compte que tu joues déjà. Un compte a du sens si tu en veux un deuxième pour queue, ou un serveur vierge pour repartir. Si tu hésites uniquement sur le prix, le boost est en général le meilleur achat.",
      "Can I play it from another country?": "Puis-je y jouer depuis un autre pays ?",
      "The shard is fixed — an EUW account stays on EUW — but nothing stops you playing it from anywhere. Riot does not sell shard transfers between the regions on this page, so pick the one your friends are on.":
        "Le serveur est fixe — un compte EUW reste sur EUW — mais rien ne t’empêche d’y jouer d’où tu veux. Riot ne vend pas de transfert entre les serveurs de cette page, alors prends celui de tes potes.",
      "Or climb on the account you already play.": "Ou monte sur le compte que tu joues déjà.",
      "A boost keeps your name, your skins and your match history. If you are choosing between the two on price alone, that is usually the better purchase.":
        "Un boost garde ton pseudo, tes skins et ton historique. Si tu hésites uniquement sur le prix, c’est en général le meilleur achat.",
      "Configure a {} boost": "Configurer un boost {}",
      "Or start on a second account.": "Ou pars sur un deuxième compte.",
      "Ready-made {} accounts from": "Comptes {} prêts à jouer à partir de",
      "— level 30 and ranked, on NA, EUW, EUNE and OCE, with full email access and a":
        "— niveau 30 et classés, sur NA, EUW, EUNE et OCE, avec accès complet à l’e-mail et un",
      "replacement. A boost is still the better buy if you want to keep your own name and skins.":
        "de remplacement. Un boost reste le meilleur achat si tu veux garder ton pseudo et tes skins.",
      "Browse accounts": "Voir les comptes",
      "Account": "Compte",
      "Price": "Prix",
      "This is where the login, the password and the recovery mailbox are sent. Check it is one you can open — no marketing unless you tick the box at the end.":
        "C’est là que sont envoyés l’identifiant, le mot de passe et la boîte de récupération. Vérifie que tu peux l’ouvrir — aucune pub sauf si tu coches la case à la fin.",
      "Anything we should know": "Quelque chose à nous signaler",
      "Replaced or refunded for {} days": "Remplacé ou remboursé pendant {} jours",
      "Read the warranty": "Lire la garantie de remplacement",
      "Email me when the account is on its way. Nothing else.":
        "Préviens-moi par e-mail quand le compte part. Rien d’autre.",
      /* The listing NAME, as a pattern: the rank it captures is data and passes
         through verbatim (a capture gets one exact dictionary lookup on the way
         out, which is what turns "Iron to Silver" into its own entry below).
         Only this page emits these, so the short literal is unambiguous. */
      "{} ranked": "{} classé",
      "Level 30 · {} BE": "Niveau 30 · {} BE",
      "Iron to Silver": "Iron à Silver",
    
      /* ── the accounts shop (/accounts.html) ───────────────────────────────────────────
         design_handoff_accounts_shop. Ranks, shard names, listing tiers and
         the reviewers' names are DATA and stay in English with every other
         rank on the site. The keys carrying a figure are written as `{}`
         patterns so a re-tuned warranty window or catalogue size cannot
         leave the sentence rendering in English — see CLAUDE.md. */
      "four": "quatre",
      "eleven": "onze",
      "Buy League of Legends accounts": "Acheter un compte League of Legends",
      "Ranked ready, full email access, no grind": "Prêt pour le classé, accès e-mail complet, zéro grind",
      "Original inbox included": "Boîte mail d’origine incluse",
      "{}-month replacement warranty": "{} mois de garantie de remplacement",
      "Step 1 of 2": "Étape 1 sur 2",
      "Step 2 of 2": "Étape 2 sur 2",
      "Which server do you play on?": "Sur quel serveur joues-tu ?",
      "Accounts are region-locked, so this is the one choice you cannot change after purchase. Pick the server you actually queue on.": "Un compte est verrouillé sur sa région : c’est le seul choix que tu ne pourras plus changer après l’achat. Prends le serveur sur lequel tu lances vraiment tes parties.",
      "Most stock": "Le plus de stock",
      "Low stock": "Stock faible",
      "in stock": "en stock",
      "Step 1 · server": "Étape 1 · serveur",
      "in stock on this server": "en stock sur ce serveur",
      "Change server": "Changer de serveur",
      "Pick your account on": "Choisis ton compte sur",
      "All tiers": "Tous les paliers",
      "Ranked": "Classé",
      "Everything in stock": "Tout ce qui est en stock",
      "Smurfs, placements unplayed": "Smurfs, placements non joués",
      "Iron to Master — previous season rewards included": "D’Iron à Master — récompenses de la saison précédente incluses",
      "tiers": "paliers",
      "Cheapest": "Le moins cher",
      "Best seller": "Meilleure vente",
      "On offer": "En promo",
      "Hand-levelled, never botted": "Monté à la main, jamais au bot",
      "Placements not played": "Placements non joués",
      "Previous season rewards": "Récompenses de la saison précédente",
      "in stock · {}": "en stock · {}",
      "left · verified in 12 h": "restant · vérifié sous 12 h",
      "Sold out on this server": "Épuisé sur ce serveur",
      "Buy now": "Acheter",
      "Reserve": "Réserver",
      "Prices and stock shown on": "Prix et stock affichés sur",
      ". Pick a server above to see yours.": ". Choisis ton serveur ci-dessus pour voir les tiens.",
      "Handover": "Remise",
      "Every account ships with the original email inbox, not just the game login — which is the only version of this that is actually yours. Change the email and the password on arrival and nobody, including us, can recover it afterwards.": "Chaque compte part avec la boîte mail d’origine, pas seulement l’identifiant de jeu — c’est la seule version de ce produit qui t’appartient vraiment. Change l’e-mail et le mot de passe dès la réception : personne, nous compris, ne pourra le récupérer ensuite.",
      "Minute 0": "Minute 0",
      "Pay for the account you picked": "Paie le compte que tu as choisi",
      "No account needed on our side. Card or wallet, and the price on the card is the price.": "Aucun compte à créer chez nous. Carte ou wallet, et le prix affiché sur la fiche est le prix payé.",
      "Credentials arrive by email": "Les identifiants arrivent par e-mail",
      "Login, password, and the original inbox with its recovery details. Sent to the address you paid with.": "Identifiant, mot de passe, et la boîte mail d’origine avec ses informations de récupération. Envoyés à l’adresse utilisée pour payer.",
      "First 10 min": "10 premières minutes",
      "Change the email and the password": "Change l’e-mail et le mot de passe",
      "Do this before your first game. A walkthrough is in the same email, and support will do it with you in Discord if you would rather.": "Fais-le avant ta première partie. Le pas-à-pas est dans le même e-mail, et le support le fait avec toi sur Discord si tu préfères.",
      "Covered {} months": "Couvert {} mois",
      "Play — and if it ever breaks, we replace it": "Joue — et si ça casse un jour, on le remplace",
      "Anything actioned inside the window is swapped for an account of the same rank, or refunded. One claim per account, no interrogation.": "Tout compte sanctionné pendant la période est échangé contre un compte du même rang, ou remboursé. Une réclamation par compte, sans interrogatoire.",
      "What lands in your inbox": "Ce qui arrive dans ta boîte mail",
      "The game login": "L’identifiant de jeu",
      "Username and password, tested minutes before it is sent.": "Pseudo et mot de passe, testés quelques minutes avant l’envoi.",
      "The original email inbox": "La boîte mail d’origine",
      "Address, password and recovery answers — this is what makes it yours.": "Adresse, mot de passe et réponses de récupération — c’est ce qui rend le compte réellement tien.",
      "A change-it-now walkthrough": "Un pas-à-pas pour tout changer",
      "Four steps to lock the account to you, with screenshots.": "Quatre étapes pour verrouiller le compte à ton nom, captures à l’appui.",
      "The full account sheet": "La fiche complète du compte",
      "Champions, skins, essence, honour level and match history at handover.": "Champions, skins, essence, niveau d’honneur et historique de parties au moment de la remise.",
      "A {}-month warranty note": "Une note de garantie de {} mois",
      "Your order id is the claim — nothing to register.": "Ton numéro de commande fait office de réclamation — rien à enregistrer.",
      "Riot licenses an account to one person and does not permit it to be sold or transferred. Changing the email and the password on arrival is what makes a ban unlikely rather than impossible, and it is why we hand over the inbox instead of only the login. We replace anything actioned inside the warranty window — but we will not tell you the risk is zero, because it isn't.": "Riot concède la licence d’un compte à une seule personne et n’autorise ni sa vente ni son transfert. Changer l’e-mail et le mot de passe dès la réception rend un bannissement improbable, pas impossible, et c’est la raison pour laquelle nous remettons la boîte mail et pas seulement l’identifiant. Nous remplaçons tout compte sanctionné pendant la période de garantie — mais nous ne vous dirons pas que le risque est nul, parce qu’il ne l’est pas.",
      "Why ours": "Pourquoi les nôtres",
      "Hand-levelled, never botted.": "Montés à la main, jamais au bot.",
      "Three things decide whether a bought account is worth having: who played it, whether you can lock it to yourself, and what happens if it goes wrong.": "Trois choses décident si un compte acheté vaut quelque chose : qui l’a joué, si tu peux le verrouiller à ton nom, et ce qui se passe quand ça tourne mal.",
      "Provenance": "Provenance",
      "Played by a person": "Joué par un humain",
      "Every account was levelled by a booster on our roster, in normal hours, on a regional connection. The match history reads like a player because it was one.": "Chaque compte a été monté par un booster du roster, à des horaires normaux, sur une connexion de la région. L’historique se lit comme celui d’un joueur parce que c’en était un.",
      "No scripts, no bots, ever": "Jamais de scripts, jamais de bots",
      "Ownership": "Propriété",
      "The inbox comes with it": "La boîte mail vient avec",
      "A login without its email is a rental — the seller can pull it back whenever they like. Ours ship with the original inbox and its recovery details.": "Un identifiant sans son e-mail, c’est une location : le vendeur peut le reprendre quand il veut. Les nôtres partent avec la boîte mail d’origine et ses informations de récupération.",
      "Yours to lock in 10 minutes": "À toi, verrouillé en 10 minutes",
      "Warranty": "Garantie",
      "Replaced for a year": "Remplacé pendant un an",
      "If the account is actioned within {} months we send an equivalent one. One claim per account, no interrogation, no restocking fee.": "Si le compte est sanctionné dans les {} mois, nous en envoyons un équivalent. Une réclamation par compte, sans interrogatoire ni frais de remise en stock.",
      "{} claims honoured last year": "{} réclamations honorées l’an dernier",
      "Buyers": "Acheteurs",
      "From accounts sold this month.": "Sur les comptes vendus ce mois-ci.",
      "4 days ago": "il y a 4 jours",
      "1 week ago": "il y a 1 semaine",
      "2 weeks ago": "il y a 2 semaines",
      "Email came with it, changed both in about five minutes with the guide. Match history looks like a real account, which is the bit I was worried about.": "L’e-mail était bien fourni, j’ai changé les deux en cinq minutes avec le guide. L’historique de parties ressemble à un vrai compte, et c’était ça qui m’inquiétait.",
      "Expensive, and worth it — the honour level and season rewards were exactly as listed. Support walked me through the email change on Discord.": "Cher, et ça les vaut — le niveau d’honneur et les récompenses de saison étaient exactement ceux annoncés. Le support m’a accompagné sur Discord pour le changement d’e-mail.",
      "Every review here is tied to a paid order id. We do not solicit them and we do not filter by score —": "Chaque avis ici est rattaché à un numéro de commande payée. Nous n’en sollicitons aucun et nous ne filtrons pas par note —",
      "read every review": "lire tous les avis",
      "Before you buy an account.": "Avant d’acheter un compte.",
      "Three of these argue against the sale. They are the reason the other five are worth reading.": "Trois de ces réponses jouent contre la vente. C’est pour ça que les cinq autres valent la peine d’être lues.",
      "Do I get the email as well as the login?": "Est-ce que je reçois l’e-mail en plus de l’identifiant ?",
      "Yes, on every account. You receive the game login and the original inbox with its password and recovery details, which is the difference between owning an account and renting one. Change both on arrival and nobody — including us — can take it back. We do not sell accounts we cannot hand over completely.": "Oui, sur chaque compte. Vous recevez l’identifiant de jeu et la boîte mail d’origine avec son mot de passe et ses informations de récupération : c’est toute la différence entre posséder un compte et le louer. Changez les deux à la réception et personne — nous compris — ne peut le reprendre. Nous ne vendons pas de comptes que nous ne pouvons pas remettre entièrement.",
      "Can the account be banned for this?": "Le compte peut-il être banni pour ça ?",
      "Buying an account is against Riot's terms of service, so the honest answer is that the risk is not zero. What reduces it is provenance and hygiene: every account was hand-levelled by a person rather than botted, and changing the email and password in the first ten minutes removes the only trail back to the sale. Anything actioned within {} months is replaced free.": "Acheter un compte est contraire aux conditions d’utilisation de Riot : la réponse honnête est que le risque n’est pas nul. Ce qui le réduit, c’est la provenance et l’hygiène — chaque compte a été monté à la main par un humain plutôt qu’au bot, et changer l’e-mail et le mot de passe dans les dix premières minutes efface la seule trace qui remonte à la vente. Tout compte sanctionné dans les {} mois est remplacé gratuitement.",
      "What happens if it is recovered or banned?": "Que se passe-t-il s’il est récupéré ou banni ?",
      "Inside {} months of delivery you get another account of the same rank, or the money back, your choice. One claim per account, no interrogation and no restocking fee. The claim is your order id — there is nothing to register.": "Dans les {} mois suivant la livraison, vous obtenez un autre compte du même rang, ou le remboursement, à votre choix. Une réclamation par compte, sans interrogatoire ni frais de remise en stock. La réclamation, c’est votre numéro de commande — il n’y a rien à enregistrer.",
      "Why is a Diamond account so much more than a smurf?": "Pourquoi un compte Diamond coûte-t-il tellement plus qu’un smurf ?",
      "A level 30 unranked takes a booster a couple of days. A Diamond account is weeks of ranked games at a rank where losses are expensive, plus the skins and rewards that accumulate on the way. The price tracks the hours behind the account, not the label on it.": "Un niveau 30 non classé prend deux jours à un booster. Un compte Diamond, ce sont des semaines de parties classées à un rang où les défaites coûtent cher, plus les skins et les récompenses accumulés en chemin. Le prix suit les heures derrière le compte, pas l’étiquette dessus.",
      "No. A listing names a tier and you get what is in stock the day you order, inside it. We do not know which division it will be when you buy, so we do not print one we might not have — everything else on the card is exact.": "Non. Une annonce nomme un palier et vous recevez ce qui est en stock ce jour-là, à l’intérieur de ce palier. Nous ne savons pas quelle division ce sera au moment de l’achat, donc nous n’en affichons pas une que nous pourrions ne pas avoir — tout le reste de la fiche est exact.",
      "Can I change server after buying?": "Puis-je changer de serveur après l’achat ?",
      "No — and it is why the server is the first thing we ask. Riot does sell a transfer service, but we do not offer transfers and an account's rank history does not follow it cleanly. Pick the region you actually queue on.": "Non — et c’est pour ça que le serveur est la première question. Riot vend bien un service de transfert, mais nous ne proposons pas de transferts et l’historique de classement d’un compte ne suit pas proprement. Choisissez la région sur laquelle vous jouez réellement.",
      "Can I get a refund if I change my mind?": "Puis-je être remboursé si je change d’avis ?",
      "Before the credentials are sent, yes — in full, no questions. Once they have been sent we cannot refund, because you have had access to the account and we cannot un-know the password. That is the trade for delivery in minutes, and it is why the listing shows every stat before you buy.": "Avant l’envoi des identifiants, oui — intégralement, sans question. Une fois envoyés, nous ne pouvons plus rembourser : vous avez eu accès au compte et le mot de passe ne peut pas être « désappris ». C’est la contrepartie d’une livraison en quelques minutes, et c’est pour ça que l’annonce affiche chaque statistique avant l’achat.",
      "Full email access, or it's not an account.": "Accès e-mail complet, sinon ce n’est pas un compte.",
      "{} tiers on {} servers, from": "{} paliers sur {} serveurs, à partir de",
      "Eleven": "Onze",
      "Pick your server": "Choisis ton serveur",
      "Or boost the account you already play": "Ou booste le compte que tu joues déjà",
      "Instant Delivery": "Livraison instantanée",

      "{}, from paying to playing.": "{}, entre le paiement et la première partie.",
      ", every time": ", à chaque commande",
      ", replaced for {} months if it ever breaks.": ", remplacé pendant {} mois si ça casse un jour.",

      "instant delivery": "livraison instantanée",

      "Low MMR": "MMR bas",
      "Standard MMR": "MMR standard",
      "High MMR": "MMR élevé",
      "Ordered at 2am and the credentials were in my inbox before I closed the tab. Bigger champion pool than the account I main on.": "Commandé à 2 h du matin, les identifiants étaient dans ma boîte avant que je ferme l’onglet. Pool de champions plus large que sur mon compte principal.",

      "Random BE/Skins": "BE/skins aléatoires",

      "{}+ champions": "{}+ champions",

    },

    de: {
      /* dynamic fragments emitted by app.js */
      "Solo": "Solo",
      "Duo queue": "Duo",
      "net win": "Netto-Sieg",
      "net wins": "Netto-Siege",
      "placement game": "Platzierungsspiel",
      "placement games": "Platzierungsspiele",
      "about 1 day": "etwa 1 Tag",
      "days": "Tage",
      "Target must sit above your current rank": "Das Ziel muss über deinem aktuellen Rang liegen",
      "Pick a target above your current rank": "Wähle ein Ziel über deinem aktuellen Rang",
      "YOU": "DU",
      "TARGET": "ZIEL",
      "YOU · TGT": "DU · ZIEL",
      "Tap the rank you’re on now": "Tipp auf den Rang, auf dem du bist",
      "Now tap the rank you want to reach": "Jetzt auf den Rang tippen, den du willst",
      "No divisions": "Keine Divisionen",
      "None": "Keine",

      /* site header — design_handoff_site_header */
      "Currency": "Währung",
      "Language": "Sprache",
      "Summer sale": "Sommer-Sale",
      "ends 31 Aug": "bis 31. Aug.",
      "Copied": "Kopiert",
      "verified boosters": "verifizierte Booster",
      "Games": "Spiele",
      "Live": "Live",
      "Boosters": "Booster",
      "Safety": "Sicherheit",
      "Reviews": "Bewertungen",
      "Log in": "Anmelden",
      "Menu": "Menü",
      "Skip to content": "Zum Inhalt springen",
      /* mega menus */
      "Pick your game": "Wähle dein Spiel",
      "Who plays your order": "Wer deine Bestellung spielt",
      "Before you buy": "Bevor du kaufst",
      "Right now": "Gerade jetzt",
      "Top": "Nr. 1",
      "Hiring": "Sucht Verstärkung",
      "are live too": "sind ebenfalls live",
      "boosters on shift": "Booster online",
      "Median claim": "Übernahme im Median",
      "Watch orders land live": "Bestellungen live eintreffen sehen",
      "All nine games": "Alle neun Spiele",
      "Browse the roster": "Den Kader ansehen",
      "verified boosters, one game each": "verifizierte Booster, je ein Spiel",
      "Hire a specific booster": "Einen bestimmten Booster buchen",
      "Name one at checkout, no extra fee": "Beim Bezahlen benennen, ohne Aufpreis",
      "How we verify": "Wie wir prüfen",
      "Rank proof, trial orders, review floor": "Rangnachweis, Probebestellungen, Mindestbewertung",
      "Master+ with a clean account": "Master+ und ein Account ohne Sanktionen",
      "Read their reviews": "Bewertungen der Booster lesen",
      "reviews, filterable by game and score": "Bewertungen, filterbar nach Spiel und Note",
      "The guarantee": "Die Garantie",
      "Refunded until a booster claims it": "Erstattet, bis ein Booster übernimmt",
      "Account safety": "Account-Sicherheit",
      "Regional VPN, your hours, offline": "Regionales VPN, deine Zeiten, offline",
      "What we never do": "Was wir nie tun",
      "No bots, no password changes": "Keine Bots, keine Passwortänderungen",
      "Pro-rated, in five business days": "Anteilig, in fünf Werktagen",
      "FAQ": "FAQ",
      "The six questions support gets most": "Die sechs häufigsten Fragen an den Support",
      "Track an order": "Bestellung verfolgen",
      "No password — the link is the login": "Kein Passwort — der Link ist der Login",
      /* auth panel */
      "Create account": "Konto erstellen",
      "Create your account": "Erstelle dein Konto",
      "An account is optional. It keeps every order, thread and saved configuration in one place — you can still buy as a guest.":
        "Ein Konto ist optional. Es bündelt jede Bestellung, jeden Verlauf und jede gespeicherte Konfiguration an einem Ort — du kannst weiterhin als Gast kaufen.",
      "Bought as a guest? You don't need an account. Use the link we emailed you, or resend it from the order tracker.":
        "Als Gast gekauft? Du brauchst kein Konto. Nutze den Link aus unserer E-Mail oder lass ihn dir in der Bestellverfolgung erneut schicken.",
      "Continue with Discord": "Weiter mit Discord",
      "Continue with Google": "Weiter mit Google",
      "Sign up with Discord": "Mit Discord registrieren",
      "Sign up with Google": "Mit Google registrieren",
      "or with email": "oder per E-Mail",
      "Display name": "Anzeigename",
      "What your booster calls you": "Wie dein Booster dich nennt",
      "Password": "Passwort",
      "Your password": "Dein Passwort",
      "At least 6 characters": "Mindestens 6 Zeichen",
      "Forgot it?": "Vergessen?",
      "Show password": "Passwort anzeigen",
      "Hide password": "Passwort verbergen",
      "Six characters or more. A passphrase beats a symbol soup.":
        "Sechs Zeichen oder mehr. Ein Passsatz schlägt einen Zeichensalat.",
      "Too short to be worth having.": "Zu kurz, um etwas zu taugen.",
      "Getting there — add a few more words.": "Fast — häng noch ein paar Wörter an.",
      "Strong enough.": "Stark genug.",
      "I've read the": "Ich habe die",
      "terms": "Nutzungsbedingungen",
      "privacy policy": "Datenschutzerklärung",
      "and the": "und die",
      ", including how boosting relates to each game's rules.":
        " gelesen, einschließlich dessen, wie sich Boosting zu den Regeln des jeweiligen Spiels verhält.",
      "We'll keep you signed in on this device for 30 days.":
        "Du bleibst auf diesem Gerät 30 Tage angemeldet.",
      "That email and password don't match. Check the address, or reset the password.":
        "E-Mail und Passwort passen nicht zusammen. Prüfe die Adresse oder setze das Passwort zurück.",
      "An account with this email already exists. Log in instead.":
        "Ein Konto mit dieser E-Mail existiert bereits. Melde dich stattdessen an.",
      "Enter a valid email address.": "Gib eine gültige E-Mail-Adresse ein.",
      "Choose a password of at least 6 characters.": "Wähle ein Passwort mit mindestens 6 Zeichen.",
      "Please accept the terms to create your account.":
        "Bitte akzeptiere die Bedingungen, um dein Konto zu erstellen.",
      "Enter your password.": "Gib dein Passwort ein.",
      "Couldn't reach the server. Check your connection and try again.":
        "Server nicht erreichbar. Prüfe deine Verbindung und versuche es erneut.",
      "Couldn't create the account. Try again.": "Konto konnte nicht erstellt werden. Versuche es erneut.",
      "Sign-in didn't complete. Please try again.":
        "Die Anmeldung wurde nicht abgeschlossen. Bitte versuche es erneut.",
      "That email and password don't match. Check them, or create an account.":
        "E-Mail und Passwort passen nicht zusammen. Prüfe sie oder erstelle ein Konto.",
      "Social sign-in isn't connected yet. Use your email, or buy as a guest — checkout needs no account.":
        "Die Anmeldung über soziale Konten ist noch nicht angebunden. Nutze deine E-Mail oder kaufe als Gast — die Kasse braucht kein Konto.",
      "This is your store account, never your game login.":
        "Das ist dein Shop-Konto, nie dein Spiel-Login.",
      "We never ask for your game password here.": "Wir fragen hier nie nach deinem Spiel-Passwort.",
      "New here?": "Neu hier?",
      "Already have an account?": "Du hast schon ein Konto?",
      "Create an account": "Konto erstellen",
      /* account menu */
      "My orders": "Meine Bestellungen",
      "Messages": "Nachrichten",
      "Log out": "Abmelden",
      "live": "aktiv",
      "Account": "Konto",
      "Your orders": "Deine Bestellungen",
      "Every boost you've ordered \u2014 the one in progress, and the ones already delivered.":
        "Jeder Boost, den du bestellt hast — der laufende und die bereits gelieferten.",
      "Signed in as": "Angemeldet als",
      "You're viewing a sample history.": "Du siehst einen Beispielverlauf.",
      "to see your orders here — or track a single order by the link we emailed you. Checkout never needs an account.":
        "um deine Bestellungen hier zu sehen — oder verfolge eine einzelne Bestellung über den Link aus unserer E-Mail. Die Kasse braucht nie ein Konto.",
      "This order history is a preview. Until an account backend is live, the orders shown are example data, priced with the real quote \u2014 the same standing as the demo dashboard.":
        "Dieser Bestellverlauf ist eine Vorschau. Solange kein Konto-Backend aktiv ist, sind die gezeigten Bestellungen Beispieldaten, mit dem echten Angebot berechnet — im selben Status wie das Demo-Dashboard.",
      "Track by link": "Über Link verfolgen",
      "Orders": "Bestellungen",
      "Lifetime spent": "Gesamt ausgegeben",
      "Open dashboard": "Dashboard öffnen",
      "Status": "Status",
      "now": "jetzt",

      /* footer */
      "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any of their subsidiaries. All trademarks, game titles, logos, and brand names are the property of their respective owners. eSports Boost provides independent gaming services and is not endorsed by or associated with any game publisher.":
        "Wir sind weder mit Riot Games, Inc., Blizzard Entertainment, Valve noch einer ihrer Tochtergesellschaften verbunden. Alle Marken, Spieltitel, Logos und Markennamen sind Eigentum ihrer jeweiligen Inhaber. eSports Boost bietet unabhängige Gaming-Dienste und wird von keinem Spielehersteller unterstützt oder mit ihm in Verbindung gebracht.",
      "Questions? Email us at": "Fragen? Schreib uns an",
      "Follow along": "Folg uns",
      "games": "Spiele",
      "Help center": "Hilfecenter",
      "Legal": "Rechtliches",
      "24/7 Customer Support": "24/7-Kundensupport",
      "Online now": "Jetzt online",
      "Online Now": "Jetzt online",
      "Verified Boosters": "verifizierte Booster",
      "Typical reply": "Antwort typischerweise in",
      "Need help? Our support team is available anytime to assist you with your orders and questions.":
        "Brauchst du Hilfe? Unser Support-Team ist jederzeit für deine Bestellungen und Fragen da.",
      "Let's chat": "Schreib uns",
      "Visit help center": "Zum Hilfecenter",
      "Privacy Policy": "Datenschutzerklärung",
      "Terms of Service": "Nutzungsbedingungen",
      "Refunds & Cancellations": "Rückerstattungen & Stornierungen",
      "Become a booster": "Booster werden",
      "Discord": "Discord",
      "Card, Apple Pay and Google Pay accepted — payments secured by Stripe":
        "Karte, Apple Pay und Google Pay akzeptiert — Zahlungen abgesichert durch Stripe",
      "© 2026 eSports Boost. All Rights Reserved.": "© 2026 eSports Boost. Alle Rechte vorbehalten.",

      /* calculator / wizard */
      "Fast Checkout": "Schneller Checkout",
      "Live pricing": "Live-Preise",
      "Choose a game": "Wähle ein Spiel",
      "Your climb": "Dein Aufstieg",
      "Rank tier": "Rangstufe",
      "Current division": "Aktuelle Division",
      "Target division": "Ziel-Division",
      "How it's played": "Spielweise",
      /* order card — the "Ladder card" hero on the game pages */
      "Build your boost": "Stell deinen Boost zusammen",
      "of": "von",
      "boosters free now": "Booster jetzt frei",
      "Add-ons": "Extras",
      "to climb": "vor dir",
      "division": "Division",
      "divisions": "Divisionen",
      "Cheapest single division": "Günstigste einzelne Division",
      "You save": "Du sparst",
      "Save": "Gespart",
      "with": "mit",
      "Money-back until a booster is assigned": "Geld zurück, bis ein Booster zugewiesen ist",
      "Money back until a booster claims it": "Geld zurück, bis ein Booster die Bestellung annimmt",
      "Your hours, offline the whole time": "Zu deinen Zeiten, durchgehend offline",
      "Pause any time — it's your account": "Jederzeit pausieren — es ist dein Konto",
      "Pause it anytime": "Jederzeit pausieren",
      "Booster time to claim": "Zeit bis zur Übernahme",
      "Time to claim": "Bis zur Übernahme",
      "We handle the rest.": "Wir kümmern uns um den Rest.",
      "Discreet on your bank statement": "Diskret auf deinem Kontoauszug",
      "No account needed": "Kein Konto nötig",
      "VPN matched to your region": "VPN passend zu deiner Region",
      "on Trustpilot": "auf Trustpilot",
      "Delivered in": "Geliefert in",
      "Boosters free now": "Booster jetzt frei",
      "Total price": "Gesamtpreis",
      "Total, tax included": "Gesamt, inkl. MwSt.",
      "Continue": "Weiter",
      "Service": "Service",
      "Division boost": "Divisions-Boost",
      "Net wins": "Netto-Siege",
      "Placements": "Platzierungen",
      "Current rank": "Aktueller Rang",
      "Target rank": "Ziel-Rang",
      "You are": "Du bist",
      "You want": "Du willst",
      "Change tier": "Stufe wechseln",
      "How many net wins": "Wie viele Netto-Siege",
      "How many placement games": "Wie viele Platzierungsspiele",
      "One win fewer": "Ein Sieg weniger",
      "One win more": "Ein Sieg mehr",
      "One game fewer": "Ein Spiel weniger",
      "One game more": "Ein Spiel mehr",
      "Server": "Server",
      "Options": "Optionen",
      "Continue to checkout": "Weiter zur Kasse",
      "No account needed · Money-back until a booster is assigned · VPN matched to your region":
        "Kein Konto nötig · Geld zurück bis ein Booster zugewiesen ist · VPN passend zu deiner Region",
      "From": "Ab",
      "from": "ab",
      "Configure your boost": "Konfiguriere deinen Boost",
      "Buy LoL accounts": "LoL-Accounts kaufen",
      "Continue your order": "Bestellung fortsetzen",

      /* home hero — see the note on the French block above. */
      "verified boosters on shift right now": "verifizierte Booster gerade online",
      "Pick your booster": "Wähle deinen Booster",
      "This month's #1": "Nr. 1 des Monats",
      "Verified": "Verifiziert",
      "orders delivered": "Bestellungen geliefert",
      "boosts delivered": "Boosts geliefert",
      "clients": "Kunden",
      "Clients served": "Betreute Kunden",
      "Clients": "Kunden",
      "Included": "Inklusive",
      /* The order card's inclusions line — see the French block above. */
      "Included free": "Kostenlos inklusive",

      /* add-ons — see the note on the French block above. */
      /* The free-but-optional row — see the note on the French block above. */
      /* See the note on the French block — a separate key from "Free". */
      "FREE": "GRATIS",
      "Watch your booster play": "Deinem Booster live zusehen",
      /* One line — see the note on the French block. */
      "Live screen share. Only site that gives it free.": "Bildschirm live mitsehen. Nur hier gratis.",
      "Live screen share, every game.": "Live-Bildschirmübertragung, jede Partie.",
      "What this is worth": "Was das wert ist",
      "Priority order": "Prioritäre Bestellung",
      /* Was "Ganz vorn in der Annahme-Warteschlange, angenommen in etwa 6
         Minuten." — 69 characters against a 311px one-line column, so it wrapped
         and cost the order card ~14px, which put the CTA under the fold at
         1440×900 on the German Rocket League and Marvel Rivals pages. An add-on
         note is one line by rule; keep any replacement inside ~62 characters. */
      "First in the claim queue, claimed in about 6 minutes.":
        "Ganz vorn in der Warteschlange, angenommen in etwa 6 Minuten.",
      "First in the claim queue, about 6 minutes.": "Ganz vorn in der Warteschlange, etwa 6 Minuten.",
      "Solo only queue": "Nur Solo-Queue",
      "Your booster plays alone, in ranked only — no parties.":
        "Dein Booster spielt allein, nur Ranked — keine Gruppen.",
      "Plays alone, ranked only — no parties.": "Spielt allein, nur Ranked — keine Gruppen.",
      "Play on your schedule": "Spiel zu deinen Zeiten",
      "Fixed session times, held for the whole order.":
        "Feste Zeiten, für die ganze Bestellung reserviert.",
      "Fixed times, held for the whole order.": "Feste Zeiten, für die ganze Bestellung reserviert.",
      "Champions & roles": "Champions & Rollen",
      "Agents & roles": "Agenten & Rollen",
      "Heroes & roles": "Helden & Rollen",
      "Legends & playstyle": "Legenden & Spielstil",
      "Comps & augments": "Comps & Augments",
      "Roles & maps": "Rollen & Maps",
      "Playlist & playstyle": "Playlist & Spielstil",
      "Champions, agents & roles": "Champions, Agenten & Rollen",
      "Always free. Your booster plays the picks you choose.":
        "Immer kostenlos. Dein Booster spielt die von dir gewählten Picks.",
      "You choose the picks they play.": "Du wählst die gespielten Picks.",
      "Offline appearance": "Offline erscheinen",
      "Always on. Friends see you offline for the whole order.":
        "Immer aktiv. Freunde sehen dich während der gesamten Bestellung offline.",

      /* hero (home) */
      "Verified boosters — since 2019": "Verifizierte Booster — seit 2019",
      "The rank is yours.": "Der Rang gehört dir.",
      "The grind isn't.": "Der Grind nicht.",
      "Your price in 10 seconds. Claimed in about 18 minutes. Refunded in full until it is.":
        "Dein Preis in 10 Sekunden. Angenommen in etwa 18 Minuten. Bis dahin voll erstattbar.",
      "This month's #1 — vantaa": "Nr. 1 des Monats — vantaa",
      "Challenger 1042 LP · 78% WR · EUW · 214 orders":
        "Challenger 1042 LP · 78 % WR · EUW · 214 Bestellungen",
      "Top booster of the month, vantaa": "Top-Booster des Monats, vantaa",

      /* marquee */
      "92,400 boosts delivered": "92.400 Boosts geliefert",
      "4.8 / 5 on Trustpilot — 3,140 reviews": "4,8 / 5 auf Trustpilot — 3.140 Bewertungen",
      "Most orders claimed within 18 min": "Meiste Aufträge in 18 Min. angenommen",
      "3,000 players in the Discord": "3.000 Spieler im Discord",
      "100% recovery rate on account reviews": "100 % Erfolgsquote bei Konto-Prüfungen",

      /* section heads / home */
      "Pick your game.": "Wähle dein Spiel.",
      "The price is already on it.": "Der Preis steht schon drauf.",
      "Nine games, thirty-seven services, priced per division.":
        "Neun Spiele, siebenunddreißig Services, Preis pro Division.",
      "Services": "Services",
      "Most ordered": "Am häufigsten bestellt",
      "Configure": "Konfigurieren",
      "All games": "Alle Spiele",
      "are live too.": "sind ebenfalls live.",
      "Elo boost": "Elo-Boost",
      "Rank boost": "Rang-Boost",
      "MMR boost": "MMR-Boost",
      "Unrated wins": "Unrated-Siege",
      "Tournament wins": "Turniersiege",
      "Double-up": "Double-up",
      "Calibration": "Kalibrierung",
      "Badges": "Abzeichen",
      "Kills": "Kills",
      "Premier rating": "Premier-Wertung",
      "Faceit levels": "Faceit-Level",
      "Wingman": "Wingman",
      "Wins": "Siege",
      "Duo": "Duo",
      "Coaching": "Coaching",
      "Every service is priced per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Jeder Service wird pro Division berechnet und vor dem Anmelden angezeigt. Platzierungen, Netto-Siege, Coaching und Duo bei jedem Titel.",
      "Delivered today": "Heute geliefert",
      "Why this doesn't get you banned": "Warum du dafür nicht gebannt wirst",
      /* 04 Dashboard — the section and the mock inside it. Every figure in the
         mock sits outside these nodes (see dash_mock()), so the words match. */
      "Dashboard": "Dashboard",
      "You watch the whole thing": "Du siehst alles mit",
      "Regional VPN": "Regionales VPN",
      "Pro-rated refunds": "Anteilige Rückerstattungen",
      "Open the demo dashboard": "Demo-Dashboard öffnen",
      "Preview of the order dashboard": "Vorschau des Bestell-Dashboards",
      "complete": "abgeschlossen",
      "days left": "Tage übrig",
      "LP across the order": "LP über die Bestellung",
      "LP net": "LP netto",
      "RR across the order": "RR über die Bestellung",
      "RR net": "RR netto",
      "Competitive": "Wettkampf",
      "Order start": "Bestellstart",
      "Now": "Jetzt",
      "Match history": "Spielverlauf",
      "K / D / A": "K / D / A",
      "LP": "LP",
      "Order dashboard · live": "Bestell-Dashboard · live",
      "Pause": "Pause",
      "Order dashboard — live": "Bestell-Dashboard — live",
      "Order tracking dashboard with live match history": "Bestell-Dashboard mit Live-Spielverlauf",
      "What they said after": "Was sie danach sagten",
      "Every review is tied to a paid, completed order — nothing incentivised. One per game, across the roster.":
        "Jede Bewertung gehört zu einer bezahlten, abgeschlossenen Bestellung — nichts ist incentiviert. Eine pro Spiel, quer durch den Kader.",
      "Read all reviews": "Alle Bewertungen lesen",
      "Read all on Trustpilot": "Alle auf Trustpilot lesen",
      "Verified order": "Verifizierte Bestellung",
      "Page": "Seite",
      "Verified orders only": "Nur verifizierte Bestellungen",
      "Your climb starts at": "Dein Aufstieg beginnt bei",
      "Final at checkout. Refunded in full until a booster claims it, pro-rated after that.":
        "Endgültig an der Kasse. Bis zur Annahme voll erstattet, danach anteilig.",
      "Set two ranks and the price is on screen before you sign up. No account, no quote request.":
        "Zwei Ränge wählen und der Preis steht da, noch vor jeder Anmeldung. Kein Konto, keine Angebotsanfrage.",
      "Talk to support": "Support kontaktieren",
      "Your boost": "Dein Boost",
      "Change": "Ändern",
      "Queue · Server": "Queue · Server",
      "Money-back guarantee": "Geld zurück",

      /* stat band + roster */
      "Boosts delivered": "Boosts geliefert",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3.140 Bewertungen",
      "Median time to claim": "Mediane Zeit bis zur Annahme",
      "Players in the Discord": "Spieler im Discord",
      "On shift now —": "Jetzt online —",
      "in the Discord": "im Discord",
      "Free VOD reviews on Sundays, scrim pickups, and the booster application queue.":
        "Sonntags kostenlose VOD-Analysen, Scrims und die Booster-Bewerbungen.",
      "Join the server →": "Server beitreten →",
      "All games →": "Alle Spiele →",
      "more": "mehr",

      /* 02 Live / 03 Safety — siehe den Kommentar im französischen Block. */
      "Updates as orders close": "Aktualisiert, sobald Bestellungen abgeschlossen werden",
      "Delivered": "Geliefert",
      "hr ago": "Std.",
      "d ago": "T.",
      "orders closed in the last 24 hours": "Bestellungen in den letzten 24 Stunden abgeschlossen",
      "boosters": "Booster",
      "All": "Alle",
      "win rate": "Winrate",
      "Free": "Frei",
      "free": "frei",
      "1 order": "1 Bestellung",
      "2 orders": "2 Bestellungen",
      "Free to join": "Kostenlos",
      "Join the server": "Server beitreten",
      "Client satisfaction rate": "Kundenzufriedenheitsrate",
      "Your sensitivity and crosshair": "Deine Sensitivität und dein Fadenkreuz",
      "Played in your normal hours": "Gespielt zu deinen üblichen Zeiten",
      "Offline the whole order": "Die ganze Bestellung offline",
      "Read the full safety policy": "Vollständige Sicherheitsrichtlinie lesen",

      /* steps */
      "Configure and pay": "Konfigurieren und zahlen",
      "Ranks, mode, champion or agent preferences, offline appear, scheduled hours. The price never changes after checkout.":
        "Ränge, Modus, Champion- oder Agenten-Vorlieben, Offline-Anzeige, geplante Zeiten. Der Preis ändert sich nach der Kasse nie.",
      "A booster claims it, usually inside 20 minutes":
        "Ein Booster nimmt sie an, meist in unter 20 Minuten",
      "You see their rank, region, win rate and current queue before they start. Swap them once, free, no reason needed.":
        "Du siehst Rang, Region, Siegrate und aktuelle Queue, bevor sie starten. Tausche einmal kostenlos, ohne Begründung.",
      "Track every match, pause any time": "Verfolge jedes Match, pausiere jederzeit",
      "Match history, LP graph and chat in one dashboard. Pause from the dashboard and the account is yours again in minutes.":
        "Spielverlauf, LP-Kurve und Chat in einem Dashboard. Pausiere im Dashboard und das Konto gehört in Minuten wieder dir.",

      /* guarantees */
      "Guarantee": "Garantie",
      "Finished or refunded": "Fertig oder erstattet",
      "Every order ends in the rank you paid for or the money back for the part that never arrived. There is no third outcome.":
        "Jede Bestellung endet im bezahlten Rang oder mit dem Geld zurück für den Teil, der nie ankam. Ein drittes Ergebnis gibt es nicht.",
      "Privacy": "Datenschutz",
      "Nobody sees your name": "Niemand sieht deinen Namen",
      "Boosters get a rank, a server and your play window. Your name, email and payment details never reach them, and the order needs no account.":
        "Booster bekommen einen Rang, einen Server und dein Spielfenster. Dein Name, deine E-Mail und deine Zahlungsdaten erreichen sie nie, und die Bestellung braucht kein Konto.",
      "Support": "Support",
      "Answered in minutes, not days": "Antwort in Minuten, nicht Tagen",
      "One thread per order, staffed around the clock. If an account review lands, support files the appeal for you rather than pointing you at a form.":
        "Ein Thread pro Bestellung, rund um die Uhr besetzt. Kommt eine Kontoprüfung, legt der Support den Einspruch für dich ein, statt dich auf ein Formular zu verweisen.",

      /* dashboard points */
      "Match-by-match history": "Match-für-Match-Verlauf",
      "Every game your booster plays, with the LP swing, KDA and replay link.":
        "Jedes Spiel deines Boosters, mit LP-Änderung, KDA und Replay-Link.",
      "Pause on one click": "Pause mit einem Klick",
      "Want to play tonight? Pause, and the account is free within minutes.":
        "Willst du heute Abend spielen? Pausiere, und das Konto ist in Minuten frei.",
      "Chat with the booster, not a queue": "Schreib dem Booster, nicht einer Queue",
      "Ask for a champion pool, a schedule, or a swap. Support reads the same thread.":
        "Bitte um einen Champion-Pool, einen Zeitplan oder einen Wechsel. Der Support liest denselben Thread.",

      /* FAQ */
      "Do I need an account to see the price?": "Brauche ich ein Konto, um den Preis zu sehen?",
      "No. The calculator is on every page and needs nothing from you. You only enter an email at checkout, and only so we can send you the order link.":
        "Nein. Der Rechner ist auf jeder Seite und verlangt nichts von dir. Du gibst nur an der Kasse eine E-Mail ein, nur damit wir dir den Bestell-Link schicken können.",
      "Can I check out without creating an account?": "Kann ich ohne Konto bezahlen?",
      "Yes. Email, then payment. We create the order under that address and email you a one-click link to follow it. Set a password later if you want one, or never.":
        "Ja. E-Mail, dann Zahlung. Wir erstellen die Bestellung unter dieser Adresse und mailen dir einen Ein-Klick-Link zum Verfolgen. Lege später ein Passwort fest, wenn du willst, oder nie.",
      "Is my account safe?": "Ist mein Konto sicher?",
      "Your booster connects through a VPN in your region, appears offline, and plays inside the hours you set. We never ask for a Riot/Steam/Blizzard recovery email, never change your password, and never queue with other customers' accounts.":
        "Dein Booster verbindet sich über ein VPN in deiner Region, erscheint offline und spielt in den von dir festgelegten Zeiten. Wir fragen nie nach einer Riot-/Steam-/Blizzard-Wiederherstellungs-E-Mail, ändern nie dein Passwort und spielen nie mit den Konten anderer Kunden.",
      "What if I want to play while the boost is running?":
        "Was, wenn ich während des Boosts spielen will?",
      "Pause it from the dashboard. The account is free within minutes and the timer stops. Resume when you're done.":
        "Pausiere ihn im Dashboard. Das Konto ist in Minuten frei und der Timer stoppt. Setze fort, wenn du fertig bist.",
      "What exactly is refunded, and when?": "Was genau wird erstattet, und wann?",
      "In full, no questions, until a booster claims the order. After that, pro-rated on the part that hasn't been delivered — divisions not climbed, wins not won. Refunds are issued to the original payment method within 5 business days.":
        "Voll, ohne Rückfragen, bis ein Booster die Bestellung annimmt. Danach anteilig auf den nicht gelieferten Teil — nicht erklommene Divisionen, nicht errungene Siege. Rückerstattungen erfolgen innerhalb von 5 Werktagen auf das ursprüngliche Zahlungsmittel.",
      "Solo or duo — which should I pick?": "Solo oder Duo — was soll ich wählen?",
      "Solo is faster and cheaper: the booster plays alone. Duo means you play every game with them, nobody logs into your account, and it costs 55% more for the extra time.":
        "Solo ist schneller und günstiger: Der Booster spielt allein. Duo heißt, du spielst jedes Spiel mit ihm, niemand meldet sich bei deinem Konto an, und es kostet 55 % mehr für die zusätzliche Zeit.",
      "How fast will someone start?": "Wie schnell fängt jemand an?",
      "Median time to a claimed order last month was 18 minutes. Priority queue takes that down to about 6. If nobody claims it within 24 hours, you get a full refund automatically — you don't have to ask.":
        "Die mediane Zeit bis zur Annahme betrug letzten Monat 18 Minuten. Die Prioritäts-Queue senkt das auf etwa 6. Nimmt sie niemand innerhalb von 24 Stunden an, erhältst du automatisch eine volle Rückerstattung — ohne zu fragen.",
      "Which payment methods do you take?": "Welche Zahlungsmethoden akzeptiert ihr?",
      "Cards, Apple Pay and Google Pay, all handled securely by Stripe. Crypto is coming soon. The card statement reads as a neutral merchant name, not the service.":
        "Karten, Apple Pay und Google Pay, alle sicher über Stripe abgewickelt. Krypto kommt bald. Der Kartenauszug zeigt einen neutralen Händlernamen, nicht den Dienst.",
      "Verified order ·": "Verifizierte Bestellung ·",

      /* games index */
      "Pick your": "Wähle dein",
      "battlefield.": "Schlachtfeld.",
      "Prices are per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Preise gelten pro Division und werden vor dem Anmelden angezeigt. Platzierungen, Netto-Siege, Coaching und Duo bei jedem Titel.",
      "How it runs": "So läuft es",
      "Three steps, then": "Drei Schritte, dann",
      "it's out of your hands": "ist es nicht mehr dein Problem",
      "Configure →": "Konfigurieren →",
      "Other games": "Weitere Spiele",

      /* games catalogue — design_handoff_games_page (see the fr block) */
      "Nine titles": "Neun Titel",
      "Pick your battlefield.": "Wähle dein Schlachtfeld.",
      "Prices are per division and shown before you sign in. Placements, net wins and duo on every title, coaching on":
        "Die Preise gelten pro Division und stehen vor der Anmeldung fest. Platzierungen, Netto-Siege und Duo bei jedem Titel, Coaching bei",
      "of them.": "davon.",
      "All titles": "Alle Titel",
      "Riot titles": "Riot-Titel",
      "Valve titles": "Valve-Titel",
      "With coaching": "Mit Coaching",
      "titles.": "Titeln.",
      "Sort": "Sortieren",
      "Featured": "Empfohlen",
      "Lowest price": "Niedrigster Preis",
      "Show all nine": "Alle neun anzeigen",
      "Which service": "Welcher Service",
      "Four ways to buy a climb.": "Vier Wege, einen Aufstieg zu kaufen.",
      "Every title sells the first three. If you are not sure which one you want, read the \"best for\" line — it is usually the whole answer.":
        "Jeder Titel verkauft die ersten drei. Wenn du unsicher bist, lies die Zeile „Ideal für“ — sie ist meist die ganze Antwort.",
      "Best for": "Ideal für",
      "Two ranks, one price. Your booster climbs from where you are to where you want to be, and the number never moves after checkout.":
        "Zwei Ränge, ein Preis. Dein Booster steigt von deinem Rang zum gewünschten Rang, und die Zahl ändert sich nach dem Bezahlen nicht mehr.",
      "You know the rank you want": "Du weißt, welchen Rang du willst",
      "Priced per win above your losses, five to an order. A short push when you are close and do not want to commit to a full climb.":
        "Pro Sieg über deinen Niederlagen berechnet, fünf pro Bestellung. Ein kurzer Schub, wenn du nah dran bist und dich nicht auf einen ganzen Aufstieg festlegen willst.",
      "You are one division short": "Dir fehlt eine Division",
      "We play up to five of your season games, on a ranked account or a fresh one. The rank you land is the rank you keep.":
        "Wir spielen bis zu fünf deiner Saisonspiele, auf einem gewerteten oder einem frischen Account. Der Rang, auf dem du landest, bleibt dir.",
      "The season just reset": "Die Saison hat gerade neu begonnen",
      "An hour with a coach from the roster, live on Discord, screen shared and recorded for you to keep. Live on four of the nine titles.":
        "Eine Stunde mit einem Coach aus dem Roster, live auf Discord, mit geteiltem Bildschirm und Aufzeichnung für dich. Bei vier der neun Titel verfügbar.",
      "You want to climb it yourself": "Du willst selbst aufsteigen",
      "Three steps, then it's out of your hands": "Drei Schritte, dann ist es nicht mehr dein Problem",
      "Same dashboard on all nine titles. It opens from the link we email you — no password, no app — and updates as games finish.":
        "Dasselbe Dashboard bei allen neun Titeln. Es öffnet sich über den Link, den wir dir per E-Mail schicken — ohne Passwort, ohne App — und aktualisiert sich, sobald Spiele enden.",
      "Asked on this page": "Auf dieser Seite gefragt",
      "Title-specific questions live on each game's page. These are the ones about all nine.":
        "Titelspezifische Fragen stehen auf der jeweiligen Spielseite. Hier geht es um alle neun.",
      "Are these all the titles you cover?": "Sind das alle Titel, die ihr abdeckt?",
      "These nine are the ones with a live board and enough boosters to claim an order quickly. We take one-off requests on other titles in Discord, but there is no page and no instant price for them — if the queue cannot claim it, we say so rather than take the money.":
        "Diese neun haben ein aktives Board und genug Booster, um eine Bestellung schnell zu übernehmen. Einzelanfragen zu anderen Titeln nehmen wir über Discord an, aber es gibt dafür keine Seite und keinen Sofortpreis — wenn die Warteschlange sie nicht übernehmen kann, sagen wir das, statt das Geld zu nehmen.",
      "Why is Valorant cheaper than Counter-Strike 2?":
        "Warum ist Valorant günstiger als Counter-Strike 2?",
      "A division is not the same amount of work in every game. Ladders are different lengths, matches are different lengths, and one rung near the top of a ladder can cost several near the bottom of another. Each title carries its own multiplier, and it is on screen before you sign in: the cheapest single division is $3 on Valorant and $8 on Counter-Strike 2.":
        "Eine Division bedeutet nicht in jedem Spiel gleich viel Arbeit. Ladders sind unterschiedlich lang, Matches ebenso, und eine Sprosse nahe der Spitze einer Ladder kann so viel kosten wie mehrere am unteren Ende einer anderen. Jeder Titel hat seinen eigenen Multiplikator, und er steht vor der Anmeldung auf dem Bildschirm: die günstigste einzelne Division kostet 3 $ bei Valorant und 8 $ bei Counter-Strike 2.",
      "Does one booster cover several games?": "Deckt ein Booster mehrere Spiele ab?",
      "No. Everyone on the board plays exactly one title, and their profile carries the peak rank, the win rate, the on-time record and the orders they have delivered on it. Somebody claiming three ladders at once is somebody we did not hire.":
        "Nein. Jede Person im Kader spielt genau einen Titel, und ihr Profil zeigt Peak, Winrate, Pünktlichkeit und die dort gelieferten Bestellungen. Wer drei Ladders gleichzeitig für sich beansprucht, ist jemand, den wir nicht eingestellt haben.",
      "Can I order two titles at once?": "Kann ich zwei Titel gleichzeitig bestellen?",
      "Yes, as two orders — each gets its own booster, price and dashboard. There is no cross-title bundle, because a discount spanning two boosters would be paying one of them less.":
        "Ja, als zwei Bestellungen — jede mit eigenem Booster, eigenem Preis und eigenem Dashboard. Ein titelübergreifendes Bundle gibt es nicht, denn ein Rabatt über zwei Booster hinweg hieße, einen von beiden schlechter zu bezahlen.",
      "Do prices change during a sale?": "Ändern sich die Preise während eines Sales?",
      "SPLIT15 takes 15% off the whole catalogue with nothing to type. Each game page also carries bundle climbs at 19% to 37% off, and a bundle replaces the code rather than adding to it — there is only ever one discount on an order, and it is the larger of the two.":
        "SPLIT15 zieht 15 % vom gesamten Katalog ab, ohne dass du etwas eingeben musst. Jede Spielseite führt außerdem Bundle-Aufstiege mit 19 % bis 37 % Rabatt, und ein Bundle ersetzt den Code, statt sich dazuzuaddieren — es gibt immer nur einen Rabatt pro Bestellung, und zwar den größeren von beiden.",
      "Nine titles, one guarantee.": "Neun Titel, eine Garantie.",
      "Refunded in full until a booster claims it, pro-rated after that, and claimed in 18 min on average.":
        "Volle Erstattung, bis ein Booster übernimmt, danach anteilig — im Schnitt in 18 Min. übernommen.",
      "Start with League": "Mit League starten",

      /* game page */
      "Home": "Startseite",
      "Breadcrumb": "Navigationspfad",
      "boosters free now": "Booster jetzt frei",
      "online": "online",
      "orders,": "Bestellungen,",
      "in players' words": "in den Worten der Spieler",
      "Questions people": "Fragen, die man",
      "ask before paying": "vor dem Zahlen stellt",
      "Ask us instead": "Frag stattdessen uns",
      "On shift now": "Jetzt online",

      /* booster table */
      "Booster": "Booster",
      "Game": "Spiel",
      "Peak": "Peak",
      "Win rate": "Winrate",
      "Queue": "Queue",
      "Every booster is trialled live before onboarding and reviewed monthly. Ranks shown are verified from match history, not self-reported.":
        "Jeder Booster spielt vor dem Onboarding einen Test live und wird monatlich überprüft. Die angezeigten Ränge sind aus dem Spielverlauf verifiziert, nicht selbst angegeben.",

      /* how-it-works */
      "How it works": "So funktioniert es",
      "No account.": "Kein Konto.",
      "No surprises.": "Keine Überraschungen.",
      "No ticket queue.": "Keine Ticket-Schlange.",
      "You can see the whole price before you tell us anything about yourself. That is the entire point of the way this is built: the calculator is the first thing on every page, the number it shows is the number you pay, and the only thing checkout asks for is an email to send the order link to.":
        "Du siehst den vollen Preis, bevor du uns irgendetwas über dich verrätst. Genau darum ist alles so gebaut: Der Rechner ist das Erste auf jeder Seite, die angezeigte Zahl ist die, die du zahlst, und die Kasse fragt nur nach einer E-Mail, um den Bestell-Link zu schicken.",
      "Solo or duo": "Solo oder Duo",
      "The booster plays alone": "Der Booster spielt allein",
      "Fastest and cheapest. You hand over the login, they connect through a VPN in your region, appear offline, and play inside the hours you set. You keep the account and can pause or take it back at any moment from the dashboard.":
        "Am schnellsten und günstigsten. Du übergibst den Login, der Booster verbindet sich über ein VPN in deiner Region, erscheint offline und spielt in den von dir gesetzten Zeiten. Du behältst das Konto und kannst es jederzeit im Dashboard pausieren oder zurücknehmen.",
      "You play every game": "Du spielst jedes Spiel",
      "Nobody logs into your account, ever. You queue with the booster, voice optional, and most of them will call rotations and review your mistakes on the way up. It costs more because it takes their time at your pace.":
        "Niemand meldet sich je bei deinem Konto an. Du spielst mit dem Booster in der Queue, Voice optional, und die meisten geben Rotationen an und besprechen deine Fehler auf dem Weg nach oben. Es kostet mehr, weil es ihre Zeit in deinem Tempo bindet.",
      "Everything else": "Alles andere,",
      "people ask": "was man fragt",

      /* boosters roster + profile — design_handoff_boosters_roster */
      "Verified from match history, not self-reported.":
        "Verifiziert aus dem Spielverlauf, nicht selbst angegeben.",
      "How someone gets on this page": "Wie man auf diese Seite kommt",
      "30 days": "30 Tage",
      "applied last month": "Bewerbungen im letzten Monat",
      "trialled live on our account — five games, watched":
        "live auf unserem Konto getestet — fünf Spiele, beobachtet",
      "added to the board": "in den Kader aufgenommen",
      "62% win-rate floor, checked monthly": "62 % Mindest-Winrate, monatlich geprüft",
      "Ranks read from the game API": "Ränge aus der Spiel-API gelesen",
      "Trial games recorded and reviewed": "Testspiele aufgezeichnet und ausgewertet",
      "Applications open in the": "Bewerben kannst du dich auf",
      "queue": "",
      "players in there.": "Spieler sind drin.",
      "Join": "Beitreten",
      "on the board": "im Kader",
      "free right now": "gerade frei",
      "Availability": "Verfügbarkeit",
      "Everyone": "Alle",
      "Free now": "Jetzt frei",
      "Sort by": "Sortieren nach",
      "Free first": "Frei zuerst",
      "Game · Server": "Spiel · Server",
      "Peak this season": "Peak diese Saison",
      "Win rate · 30d": "Winrate · 30 T",
      "Hire": "Buchen",
      "Nobody free on": "Niemand frei bei",
      "right now": "gerade",
      "Nobody free right now": "Gerade ist niemand frei",
      "on the board — start the order and the first one free claims it.":
        "im Kader — starte die Bestellung und der Erste, der frei wird, nimmt sie.",
      "Order anyway": "Trotzdem bestellen",
      "Show everyone": "Alle anzeigen",
      "Showing": "Angezeigt:",
      "free now": "jetzt frei",
      "Load more": "Mehr laden",
      "Boosting since": "Booster seit",
      "in the queue": "in der Queue",
      "Orders delivered": "Gelieferte Bestellungen",
      "Average rating": "Durchschnittliche Bewertung",
      "On-time rate": "Pünktlichkeitsquote",
      "Disputes": "Streitfälle",
      "Completed orders": "Abgeschlossene Bestellungen",
      "Completed": "Abgeschlossen",
      "Rating": "Bewertung",
      "On time": "Pünktlich",
      "Top booster": "Top-Booster",
      "Rank verified every month": "Rang jeden Monat überprüft",
      "One free swap, no reason needed": "Ein kostenloser Wechsel, ohne Angabe von Gründen",

      /* 04 Safety */
      "Why this doesn't get you banned.": "Warum du dafür nicht gebannt wirst.",
      "Enterprise VPN matched to your region": "Enterprise-VPN in deiner Region",
      "Not a consumer VPN, and never a datacentre IP.":
        "Kein Consumer-VPN, und nie eine Rechenzentrums-IP.",
      "Your sensitivity, your crosshair, your runes": "Deine Sensi, dein Crosshair, deine Runen",
      "Settings are mirrored at the start and restored at the end.":
        "Die Einstellungen werden am Anfang übernommen und am Ende zurückgesetzt.",
      "You set the window at checkout. Nothing runs at 04:00 unless you do.":
        "Du legst das Zeitfenster an der Kasse fest. Um 4 Uhr morgens läuft nichts, außer du willst es so.",
      "Offline appearance for the whole order": "Offline-Anzeige für die ganze Bestellung",
      "Friends see you offline until it finishes.": "Freunde sehen dich offline, bis sie fertig ist.",
      "In duo your booster queues beside you from their own account.":
        "Im Duo spielt dein Booster von seinem eigenen Account aus neben dir in der Queue.",

      /* 05 Reviews */
      "Read them all": "Alle lesen",

      /* 06 FAQ */
      "If yours isn't here, Discord answers in about four minutes and you don't need an order to ask.":
        "Ist deine nicht dabei: Auf Discord kommt die Antwort in etwa vier Minuten, und du brauchst keine Bestellung, um zu fragen.",
      "Do you need my account login?": "Braucht ihr meine Zugangsdaten?",
      "For solo, yes — your booster signs in and plays, through a VPN in your region and inside the hours you set. For duo, no: they queue beside you from their own account and never see your login at all. Either way we never ask for your email password or your 2FA codes.":
        "Bei Solo ja — dein Booster meldet sich an und spielt, über ein VPN in deiner Region und in den Zeiten, die du festlegst. Bei Duo nein: Er spielt von seinem eigenen Account aus neben dir und sieht deine Zugangsdaten nie. In beiden Fällen fragen wir nie nach dem Passwort deines E-Mail-Kontos oder deinen 2FA-Codes.",
      "Can I play while the order is running?": "Kann ich spielen, während die Bestellung läuft?",
      "What happens if it goes past the estimate?": "Was passiert, wenn die Lieferzeit überschritten wird?",
      "A 15% credit applies automatically once the order runs past its window, and it shows on the order page without anyone asking. If it is badly over, we move it to a booster who is free.":
        "Sobald eine Bestellung über ihr Zeitfenster läuft, greift automatisch eine Gutschrift von 15 %, und sie steht auf der Bestellseite, ohne dass jemand fragen muss. Ist der Verzug groß, geben wir sie an einen Booster weiter, der frei ist.",
      "Why is duo more expensive?": "Warum ist Duo teurer?",
      "It takes longer. Your booster carries a live player rather than playing every role freely, so the same climb costs 55% more and takes longer. It is the safer option and we would rather price it honestly than hide the difference.":
        "Weil es länger dauert. Dein Booster trägt einen echten Mitspieler, statt jede Rolle frei zu spielen — derselbe Aufstieg kostet 55 % mehr und braucht mehr Zeit. Es ist die sicherere Variante, und wir schreiben den Aufpreis lieber hin, als den Unterschied zu verstecken.",
      "How do I follow the order without an account?": "Wie verfolge ich die Bestellung ohne Konto?",
      "The confirmation email carries a link that is the login. It never expires, works on any device, and opens the same dashboard shown above. Lost it? The demo page resends it to the address you paid with.":
        "In der Bestätigungs-E-Mail steckt ein Link, der der Login ist. Er läuft nie ab, funktioniert auf jedem Gerät und öffnet genau das Dashboard von oben. Verloren? Die Demo-Seite schickt ihn erneut an die Adresse, mit der du bezahlt hast.",
      "Can I choose the champions they play?": "Kann ich die Champions aussuchen, die gespielt werden?",
      "Can I choose the agents they play?": "Kann ich die Agenten aussuchen, die gespielt werden?",
      "Can I choose the roles they play?": "Kann ich die Rollen aussuchen, die gespielt werden?",
      "Can I choose the playlist they play?": "Kann ich die Playlist aussuchen, die gespielt wird?",

      /* the hero lede, one per ladder */
      "Solo/duo and flex, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Solo/Duo und Flex, auf NA und EU. Dein Booster spielt deinen Account in deinen üblichen Zeiten über ein regionales VPN — oder er spielt im Duo neben dir und fasst die Zugangsdaten nie an.",
      "Competitive and unrated, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Wettkampf und Unrated, auf NA und EU. Dein Booster spielt deinen Account in deinen üblichen Zeiten über ein regionales VPN — oder er spielt im Duo neben dir und fasst die Zugangsdaten nie an.",
      "Premier CS Rating and Faceit levels, run by FPL-adjacent players. Anti-cheat safe patterns, no smurf stacking, no rating farm scripts.":
        "Premier CS Rating und Faceit-Level, gespielt von Leuten aus dem FPL-Umfeld. Muster, mit denen der Anti-Cheat kein Problem hat, kein Smurf-Stacking, keine Rating-Farm-Skripte.",
      "1v1, 2v2 and 3v3 playlists, tournament wins, and duo sessions where the booster calls rotations live on voice.":
        "1v1-, 2v2- und 3v3-Playlists, Turniersiege und Duo-Sessions, in denen der Booster die Rotationen live im Voice ansagt.",

      /* the bundle strip */
      "Save big on bundles": "Spar richtig mit Bundles",
      "Whole-ladder climbs at one flat price": "Ganze Ladder-Aufstiege zum Festpreis",
      "Two tiers up in one order, from wherever you are":
        "Zwei Stufen höher in einer Bestellung, egal wo du stehst",
      "Two rating bands up in one order": "Zwei Wertungsstufen höher in einer Bestellung",
      "Up to {}% off": "Bis zu −{} %",
      "From any {} division": "Ab jeder {}-Division",
      "Starts at {}": "Ab {}",
      "Apply bundle": "Bundle anwenden",
      "Applied": "Angewendet",
      "Played in your preferred hours": "Gespielt zu deinen Wunschzeiten",

      /* net wins / placements */
      "per game": "pro Spiel",
      "A net win means one win above your losses — five is the cap per order.":
        "Ein Netto-Sieg ist ein Sieg mehr als Niederlagen — fünf sind das Maximum pro Bestellung.",
      "A placement game sets or resets your rank — five is the cap per order.":
        "Ein Platzierungsspiel setzt deinen Rang fest oder neu — fünf sind das Maximum pro Bestellung.",
      "I have a rank": "Ich habe einen Rang",
      "Unranked": "Unranked",
      "Fresh account or a new season — no MMR to read yet. Your booster plays all five and the rank you land is the rank you keep.":
        "Frischer Account oder neue Saison — es gibt noch kein MMR zum Auslesen. Dein Booster spielt alle fünf, und der Rang, auf dem du landest, bleibt dir.",

      /* coaching */
      "Pick your coach": "Wähl deinen Coach",
      "How many hours": "Wie viele Stunden",
      "What to work on": "Woran gearbeitet wird",
      "First session": "Erste Sitzung",
      "per hour": "pro Stunde",
      "Single session": "Einzelsitzung",
      "Save {}%": "−{} %",
      "Laning": "Laning",
      "Macro & rotations": "Makro & Rotationen",
      "Champion pool": "Champion-Pool",
      "VOD review": "VOD-Analyse",
      "coaches taking bookings": "Coaches nehmen Buchungen an",
      "taking bookings": "nimmt Buchungen an",
      "Live on Discord, screen shared, recorded for you to keep.":
        "Live auf Discord, mit geteiltem Bildschirm, aufgezeichnet und für dich zum Behalten.",

      /* ── the support page ─────────────────────────────────────────────── */
      "Two ways in. Both are read by people.": "Zwei Wege rein. Beide werden von Menschen gelesen.",
      "Staffed right now": "Gerade besetzt",
      "— someone is in #support": "— jemand ist in #support",
      "Median first reply": "Mediane Erstantwort",
      "Open 24/7": "Rund um die Uhr offen",
      "Attachments and receipts welcome": "Anhänge und Belege willkommen",
      "Copy address": "Adresse kopieren",
      "Write in": "Schreib uns",
      "Or write it here": "Oder schreib es hier",
      "What to put in it": "Was reingehört",
      "The order number": "Die Bestellnummer",
      "Anything starting ESB-. It skips triage and lands with the person on that order.":
        "Alles, was mit ESB- anfängt. Das überspringt die Sortierung und landet direkt bei der Person, die die Bestellung betreut.",
      "What you expected": "Was du erwartet hast",
      "The rank, the date, the thing the checkout said you were buying.":
        "Der Rang, das Datum, das, was an der Kasse stand.",
      "What actually happened": "Was tatsächlich passiert ist",
      "Screenshots beat descriptions. Paste them straight into the thread.":
        "Screenshots schlagen Beschreibungen. Pack sie direkt in den Thread.",
      "Nothing else": "Sonst nichts",
      "No passwords, no 2FA codes. Support will never ask for one, and won't act on a message that contains one.":
        "Keine Passwörter, keine 2FA-Codes. Der Support fragt nie danach und bearbeitet keine Nachricht, in der eins steht.",
      "What's it about": "Worum geht es",
      "Order issue": "Problem mit der Bestellung",
      "Refund": "Rückerstattung",
      "Booster swap": "Booster-Wechsel",
      "Before I buy": "Vor dem Kauf",
      "Something else": "Etwas anderes",
      "Company": "Unternehmen",
      "One thread per message. Discord and email land in the same place, so pick either — not both.":
        "Ein Thread pro Nachricht. Discord und E-Mail landen am selben Ort — nimm eins von beiden, nicht beides.",
      "Add an email we can reply to, and a line or two about what happened.":
        "Gib eine E-Mail an, an die wir antworten können, und ein, zwei Zeilen dazu, was passiert ist.",
      "We never ask for your game password here, or anywhere else.":
        "Wir fragen hier nie nach deinem Spiel-Passwort, und woanders auch nicht.",
      "Six answers that between them close most of the tickets we get. If yours isn't here, Discord is two clicks away.":
        "Sechs Antworten, die zusammen die meisten unserer Tickets erledigen. Ist deine nicht dabei, ist Discord zwei Klicks entfernt.",
      "Where is my order? I never made an account.":
        "Wo ist meine Bestellung? Ich habe nie ein Konto angelegt.",
      "You do not need one. Guest orders are tracked by the link we emailed when you paid — it never expires and works on any device. Lost it? Open the order lookup, enter the address you paid with, and we send it again.":
        "Brauchst du auch nicht. Gast-Bestellungen laufen über den Link, den wir dir beim Bezahlen gemailt haben — er läuft nie ab und funktioniert auf jedem Gerät. Verloren? Öffne die Bestellsuche, gib die Adresse ein, mit der du bezahlt hast, und wir schicken ihn erneut.",
      "Nobody has claimed my order yet.": "Meine Bestellung hat noch niemand angenommen.",
      "Median claim time is 18 min, and most of the rest go within the hour. If nothing has claimed it 24 hours after payment, the order refunds itself automatically — no ticket, no asking. Writing in before that does not move it up the board.":
        "Die mediane Annahmezeit liegt bei 18 Min., der Rest geht meist innerhalb einer Stunde weg. Hat sie 24 Stunden nach der Zahlung niemand angenommen, erstattet sich die Bestellung automatisch — ohne Ticket, ohne Nachfragen. Vorher zu schreiben schiebt sie nicht nach oben.",
      "Can I get a refund?": "Bekomme ich mein Geld zurück?",
      "In full, any time before a booster claims it. After that it is pro-rated on what has not been delivered — you keep the divisions already climbed and get the rest back. Money lands on the original payment method within 5 business days.":
        "Voll, jederzeit bevor ein Booster sie annimmt. Danach anteilig auf das, was nicht geliefert wurde — die bereits erklommenen Divisionen behältst du, den Rest bekommst du zurück. Das Geld ist innerhalb von 5 Werktagen auf dem ursprünglichen Zahlungsmittel.",
      "Can I swap to a different booster?": "Kann ich den Booster wechseln?",
      "Yes, once per order, at no charge. Ask in the order thread. The order goes back on the board and is usually re-claimed the same day; if you would rather not say why, do not — we do not ask.":
        "Ja, einmal pro Bestellung, kostenlos. Sag im Bestell-Thread Bescheid. Die Bestellung geht zurück aufs Board und wird meist am selben Tag wieder angenommen; wenn du nicht sagen willst, warum, dann lass es — wir fragen nicht.",
      "Can I play on my account while an order is running?":
        "Kann ich auf meinem Account spielen, während eine Bestellung läuft?",
      "My order is past the delivery estimate.": "Meine Bestellung ist über der Lieferzeit.",
      "A 15% credit applies automatically once an order runs past its window, and it shows on the order page without anyone having to ask. If it is badly over, write in and we will move it to a booster who is free.":
        "Sobald eine Bestellung über ihr Zeitfenster läuft, greift automatisch eine Gutschrift von 15 %, und sie steht auf der Bestellseite, ohne dass jemand fragen muss. Ist der Verzug groß, schreib uns und wir geben sie an einen Booster weiter, der frei ist.",
      "Still stuck? Ask us.": "Immer noch fest? Frag uns.",
      "Discord is the fast one — our staff sit in it all day. Or write in above and it lands in the same inbox.":
        "Discord ist der schnelle Weg — unser Team sitzt den ganzen Tag drin. Oder schreib oben rein, es landet im selben Postfach.",
      "Ask us": "Frag uns",

      /* ── the free-guides landing ──────────────────────────────────────── */
      "One for League, one for Valorant. Six chapters and six drills each, on the things that decide games between Silver and Ascendant. Written by the people on our roster who play those ranks every day.":
        "Einer für League, einer für Valorant. Je sechs Kapitel und sechs Übungen, zu den Dingen, die Spiele zwischen Silver und Ascendant entscheiden. Geschrieben von den Leuten aus unserem Kader, die diese Ränge jeden Tag spielen.",
      "Win the lane you already won.": "Gewinn die Lane, die du längst gewonnen hattest.",
      "Stop losing rounds you already won.": "Hör auf, Runden zu verlieren, die du schon hattest.",
      "6 chapters · 6 drills": "6 Kapitel · 6 Übungen",
      "The League field guide": "Der League-Praxisguide",
      "The Valorant field guide": "Der Valorant-Praxisguide",
      "Iron to Diamond · wave control, roams, objectives":
        "Iron bis Diamond · Wellenkontrolle, Roams, Objectives",
      "Iron to Ascendant · crosshair, economy, retakes": "Iron bis Ascendant · Crosshair, Eco, Retakes",
      ". If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        ". Wenn in zwei Minuten nichts ankommt, sieh unter Werbung nach — dort landet es manchmal zuerst.",
      "From the team behind": "Vom Team hinter",
      "and 4.7 / 5 on Trustpilot.": "und 4,7 / 5 auf Trustpilot.",
      "Every chapter ends with a drill you can run in a custom game in under ten minutes. That is the whole format: read it, then do it.":
        "Jedes Kapitel endet mit einer Übung, die du in einem eigenen Spiel in unter zehn Minuten durchziehst. Mehr ist das Format nicht: lesen, dann machen.",
      "Drill": "Übung",
      "Wave control": "Wellenkontrolle",
      "Freeze, slow-push, crash — and which one the minute demands.":
        "Freeze, Slow-Push, Crash — und was die jeweilige Minute verlangt.",
      "Trading, not fighting": "Traden statt kämpfen",
      "Why the lane is won by who spends time better, not who hits harder.":
        "Warum die Lane der gewinnt, der seine Zeit besser nutzt, nicht der, der härter zuschlägt.",
      "Roams that pay": "Roams, die sich lohnen",
      "The three windows where leaving lane gains more than it costs.":
        "Die drei Fenster, in denen es mehr bringt, die Lane zu verlassen, als es kostet.",
      "Objectives as maths": "Objectives sind Mathe",
      "Dragon, herald and the setup that starts 40 seconds early.":
        "Drache, Herold und das Setup, das 40 Sekunden früher anfängt.",
      "Six habits that cap your rank": "Sechs Gewohnheiten, die deinen Rang deckeln",
      "Each with the tell you can spot in your own replays.":
        "Jede mit dem Anzeichen, das du in deinen eigenen Replays erkennst.",
      "Each with the tell you can spot in your own VODs.":
        "Jede mit dem Anzeichen, das du in deinen eigenen VODs erkennst.",
      "The climb plan": "Der Aufstiegsplan",
      "Twelve ranked games a week, structured.": "Zwölf Ranked-Spiele pro Woche, mit Struktur.",
      "Crosshair placement": "Crosshair-Placement",
      "Where the dot sits before you peek, not after.":
        "Wo der Punkt sitzt, bevor du peekst, nicht danach.",
      "Economy you can trust": "Eine Eco, auf die Verlass ist",
      "When to force, when to save, and why the half-buy loses.":
        "Wann forcen, wann saven, und warum der Half-Buy verliert.",
      "Retakes and the four-second rule": "Retakes und die Vier-Sekunden-Regel",
      "Most retakes are lost before anyone shoots.":
        "Die meisten Retakes sind verloren, bevor überhaupt jemand schießt.",
      "Utility that buys space": "Utility, die Platz kauft",
      "Smokes and flashes as currency.": "Smokes und Flashes als Währung.",
      "Not a content team reading patch notes. Boosters from our own roster wrote a chapter each, and every claim is something they do in ranked that week — not theory borrowed from a pro scene you will never play in.":
        "Kein Content-Team, das Patchnotes liest. Booster aus unserem eigenen Kader haben je ein Kapitel geschrieben, und jede Aussage ist etwas, das sie in derselben Woche in Ranked machen — keine Theorie aus einer Pro-Szene, in der du nie spielen wirst.",
      "From 1,100 readers": "Von 1.100 Lesern",
      "Is it actually free, or free-ish?": "Ist das wirklich kostenlos, oder nur fast?",
      "Free. There is no card, no trial, and no upsell inside either PDF. We publish them because a player who improves is a player who stays in the game, and some of them buy a boost or a coaching hour later. That is the whole business case.":
        "Kostenlos. Keine Karte, kein Testzeitraum, kein Upsell in den PDFs. Wir veröffentlichen sie, weil ein Spieler, der besser wird, ein Spieler ist, der dabeibleibt — und manche kaufen später einen Boost oder eine Coaching-Stunde. Mehr steckt nicht dahinter.",
      "Can I take both?": "Kann ich beide nehmen?",
      "Yes, and most people do — both are ticked by default. They arrive as two attachments in one email, so taking the second one costs you nothing extra, not even another form.":
        "Ja, und die meisten tun es — beide sind standardmäßig angehakt. Sie kommen als zwei Anhänge in einer E-Mail: Der zweite kostet dich nichts extra, nicht mal ein weiteres Formular.",
      "What do you do with my email?": "Was macht ihr mit meiner E-Mail?",
      "Send you the guides. If you tick the box, one email a month with new guides and patch notes. We never sell or rent the list, and one click unsubscribes — the link is in every email, not buried in a preference centre.":
        "Dir die Guides schicken. Wenn du das Häkchen setzt, eine E-Mail im Monat mit neuen Guides und Patchnotes. Wir verkaufen oder vermieten die Liste nie, und ein Klick meldet dich ab — der Link steht in jeder E-Mail, nicht vergraben in einem Einstellungscenter.",
      "What rank are these written for?": "Für welchen Rang sind die geschrieben?",
      "Iron through Diamond for League, Iron through Ascendant for Valorant. The early chapters do most of the work at lower ranks; the habit and objective chapters matter more once you are past Platinum.":
        "Iron bis Diamond für League, Iron bis Ascendant für Valorant. In den unteren Rängen leisten die frühen Kapitel die meiste Arbeit; ab Platinum zählen die Kapitel zu Gewohnheiten und Objectives mehr.",
      "Do I need to buy boosting to use them?": "Muss ich Boosting kaufen, um sie zu nutzen?",
      "No, and neither guide mentions our services beyond one line on the last page. If you would rather someone else did the climbing, that is a different page on this site — this one is for doing it yourself.":
        "Nein, und keiner der beiden Guides erwähnt unsere Dienste über eine Zeile auf der letzten Seite hinaus. Wenn du lieber jemand anderen aufsteigen lässt, ist das eine andere Seite hier — diese ist fürs Selbermachen.",

      /* ── homepage, checkout and the odds and ends ─────────────────────── */
      "Know your exact price in seconds. A verified booster claims your order in about 18 minutes — and until one does, every cent is refundable.":
        "Dein genauer Preis in Sekunden. Ein verifizierter Booster nimmt deine Bestellung in etwa 18 Minuten an — und bis dahin ist jeder Cent erstattbar.",
      "Best Sellers": "Bestseller",
      "Fast checkout": "Schneller Checkout",
      "You are here": "Du bist hier",
      "You are here tier": "Deine aktuelle Stufe",
      "You want to be": "Dein Ziel",
      "You want to be tier": "Ziel-Stufe",
      "Your region": "Deine Region",
      "Nine games": "Neun Spiele",
      "Start an order": "Bestellung starten",
      "Ask in Discord": "Auf Discord fragen",
      "Median first reply on Discord last month: 3m 40s.":
        "Mediane Erstantwort auf Discord letzten Monat: 3 Min. 40 Sek.",
      "with vantaa": "mit vantaa",
      "Duo queue · +55%": "Duo · +55 %",
      "more {} boosters": "weitere {}-Booster",
      "more {} booster": "weiterer {}-Booster",
      "on the roster, all {} or above.": "im Kader, alle {} oder höher.",
      "on Trustpilot · {} reviews": "auf Trustpilot · {} Bewertungen",
      "{} reviews on Trustpilot": "{} Bewertungen auf Trustpilot",
      "· {} reviews": "· {} Bewertungen",
      "Yes — It is free on every order, not an upsell — \"{}\" is ticked before you configure anything. Your booster plays a pool you pick, which also keeps the match history plausible, and you can change it mid-order in the thread.":
        "Ja — bei jeder Bestellung kostenlos, kein Upsell: „{}“ ist angehakt, bevor du überhaupt etwas konfigurierst. Dein Booster spielt einen Pool, den du aussuchst, was den Spielverlauf auch plausibel hält, und du kannst ihn mitten in der Bestellung im Thread ändern.",
      "Pause it first, from the order page. Pausing is free and resumes the same night if a slot is open. What you should not do is queue ranked alongside an unpaused solo order — two people on one account in the same queue is the fastest way to get flagged.":
        "Pausier sie zuerst, auf der Bestellseite. Pausieren ist kostenlos, und es geht noch am selben Abend weiter, wenn ein Slot frei ist. Was du nicht tun solltest: selbst Ranked spielen, während eine Solo-Bestellung unpausiert läuft — zwei Leute auf einem Account in derselben Queue ist der schnellste Weg, aufzufallen.",

      /* mobile stat row, coaching slots and the roles under a booster's name */
      "To claim": "Bis zur Übernahme",
      "Tonight, 20:00": "Heute Abend, 20:00",
      "Tomorrow, 18:00": "Morgen, 18:00",
      "Saturday, 15:00": "Samstag, 15:00",
      "Sunday, 12:00": "Sonntag, 12:00",
      "Mid lane": "Midlane",
      "Duelist": "Duellant",
      "Initiator": "Initiator",
      "Sentinel": "Wächter",
      "Rocket League, Apex Legends and Counter-Strike 2":
        "Rocket League, Apex Legends und Counter-Strike 2",
      "3m 40s": "3 Min. 40 Sek.",
      "See the roster": "Kader ansehen",
      "See all": "Alle ansehen",
      "day": "Tag",
      "Request": "Anfragen",
      "Name them at checkout and your order waits for them instead of going to the open board.":
        "Nenne ihn an der Kasse, dann wartet deine Bestellung auf ihn statt auf den offenen Kader zu gehen.",
      "Named booster": "Namentlicher Booster",
      "No extra fee": "Ohne Aufpreis",
      "ahead of you": "vor dir",
      "Order with": "Bestellen mit",
      "Climbs delivered": "Gelieferte Aufstiege",
      "Showing the last": "Angezeigt: die letzten",
      "orders": "Bestellungen",
      "Latest review": "Neueste Bewertung",
      "day ago": "Tag her",
      "days ago": "Tage her",
      "Ordering with": "Bestellung mit",

      /* boosters page */
      "The roster": "Der Kader",
      "Verified from": "Verifiziert aus",
      "match history,": "dem Spielverlauf,",
      "not self-reported.": "nicht selbst angegeben.",
      "Every applicant is trialled live on our account before they touch yours: five games, watched, in the bracket they claim. Ranks on this page are read from the API, not typed into a form. Anyone whose win rate drops below 62% over a rolling month comes off the board until they climb it back.":
        "Jeder Bewerber spielt einen Test live auf unserem Account, bevor er deinen anfasst: fünf Spiele, beobachtet, in der Liga, die er angibt. Die Ränge auf dieser Seite kommen aus der API, nicht aus einem Formular. Wessen Winrate über einen laufenden Monat unter 62 % fällt, fliegt aus dem Kader, bis er sie wieder hochspielt.",
      "Apply as a booster": "Als Booster bewerben",
      "Roster": "Kader",
      "Everyone on shift": "Alle online",
      "Updated live": "Live aktualisiert",

      /* guarantee page — design_handoff_safety_guarantee */
      "Safety & guarantee": "Sicherheit & Garantie",
      "Written down, not \"depends on the order\".":
        "Schriftlich festgehalten, nicht „kommt auf die Bestellung an“.",
      "A refund policy that needs a support ticket to explain isn't a policy. Here is the whole thing, in the three cases that actually happen.":
        "Eine Rückerstattungsrichtlinie, die ein Support-Ticket zur Erklärung braucht, ist keine Richtlinie. Hier ist das Ganze, in den drei Fällen, die wirklich vorkommen.",
      /* hero figures — the number is data, the unit is a word */
      "5 days": "5 Tage",
      "24 hrs": "24 Std.",
      "Recovery rate on account reviews, across": "Wiederherstellungsquote bei Kontoprüfungen, über",
      "completed orders": "abgeschlossene Bestellungen",
      "Refunds land back on the original payment method, no ticket needed":
        "Rückerstattungen landen auf dem ursprünglichen Zahlungsmittel, ohne Ticket",
      "Unclaimed after payment? Refunded in full, automatically":
        "Nach der Zahlung nicht angenommen? Voll erstattet, automatisch",
      "Before a booster claims it": "Bevor ein Booster sie annimmt",
      "100% back, no reason asked": "100 % zurück, ohne Begründung",
      "One button in the order page. The money is back on the original payment method within 5 business days, and nobody will email you to ask why.":
        "Ein Knopf auf der Bestellseite. Das Geld ist innerhalb von 5 Werktagen auf dem ursprünglichen Zahlungsmittel zurück, und niemand mailt dir, um nach dem Grund zu fragen.",
      "Started but unfinished": "Begonnen, aber unfertig",
      "Pro-rated on what wasn't delivered": "Anteilig auf das, was nicht geliefert wurde",
      "Divisions not climbed and wins not won are refunded at the same rate you paid for them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond portion, calculated by the same formula that quoted you.":
        "Nicht erklommene Divisionen und nicht errungene Siege werden zum selben Satz erstattet, den du gezahlt hast. Ein bei Platin gestopptes Gold → Diamant erstattet den Teil Platin → Diamant, berechnet mit derselben Formel, die dir den Preis nannte.",
      "Past the ETA": "Nach der ETA",
      "Your choice, and we tell you first": "Deine Wahl, und wir sagen es dir zuerst",
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back.":
        "Läuft eine Bestellung über ihr Lieferfenster hinaus, melden wir uns, bevor du es merkst: mit 15 % Gutschrift weitermachen, den Booster tauschen oder den unfertigen Teil zurücknehmen.",

      /* band 02 — the safety prose, the disclaimer plate, the measure card */
      "Anti-cheat looks for software, not skill. Every solo order runs behind an enterprise VPN matched to your region, the booster mirrors your sensitivity and crosshair, and sessions are scheduled inside the hours you normally play — so the activity pattern on the account never changes. Duo orders never touch your login at all.":
        "Anti-Cheat sucht nach Software, nicht nach Können. Jede Solo-Bestellung läuft hinter einem Enterprise-VPN in deiner Region, der Booster übernimmt deine Empfindlichkeit und dein Fadenkreuz, und Sitzungen werden in deinen üblichen Spielzeiten geplant — das Aktivitätsmuster des Kontos ändert sich also nie. Duo-Bestellungen berühren deine Zugangsdaten überhaupt nicht.",
      "If a boost triggers an account review, support files the appeal and the order is refunded in full while it runs. Your name, email and payment details are never shared with the booster.":
        "Löst ein Boost eine Kontoprüfung aus, legt der Support den Einspruch ein, und die Bestellung wird während des Verfahrens voll erstattet. Dein Name, deine E-Mail und deine Zahlungsdaten werden nie an den Booster weitergegeben.",
      "Boosting is against the terms of service of every game listed here. We reduce the risk as far as it can be reduced and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is lying to you.":
        "Boosting verstößt gegen die Nutzungsbedingungen jedes hier gelisteten Spiels. Wir senken das Risiko so weit wie möglich und tun nicht so, als wäre es null, denn das ist es nicht — jeder Konkurrent, der dir das Gegenteil erzählt, belügt dich.",
      "What that means per order": "Was das pro Bestellung bedeutet",
      "Every order": "Jede Bestellung",
      "Enterprise VPN, matched to your region": "Enterprise-VPN, passend zu deiner Region",
      "Not a consumer VPN and not a datacentre IP — the login location never changes.":
        "Kein Consumer-VPN und keine Rechenzentrums-IP — der Anmeldeort ändert sich nie.",
      "The booster mirrors your settings before the first game.":
        "Der Booster übernimmt deine Einstellungen vor der ersten Partie.",
      "Played inside your normal hours": "Gespielt in deinen üblichen Zeiten",
      "You set the window at checkout; sessions are scheduled inside it.":
        "Du legst das Zeitfenster an der Kasse fest; Sitzungen werden darin geplant.",
      "Offline appearance, whole order": "Offline-Anzeige, ganze Bestellung",
      "Friends see you offline until the order closes.":
        "Freunde sehen dich offline, bis die Bestellung abgeschlossen ist.",
      "Duo never touches your login": "Duo berührt deine Zugangsdaten nie",
      "You play your own account. Nobody signs in but you.":
        "Du spielst auf deinem eigenen Konto. Niemand meldet sich an außer dir.",

      /* band 03 — three promises */
      "In short": "Kurz gesagt",
      "Three promises, plainly": "Drei Versprechen, klar gesagt",
      "Read the full terms": "Vollständige Bedingungen lesen",
      /* Same sentence as the checkout page's refund line — one entry, in the
         checkout block below, for both. The handoff requires them to match. */
      "Card details stay with Stripe": "Kartendaten bleiben bei Stripe",
      "Median first reply 3m 40s": "Mediane Erstantwort 3 Min. 40 Sek.",

      /* band 04 — FAQ */
      "The questions support gets most": "Die Fragen, die der Support am häufigsten bekommt",
      "The six support answers most. If yours isn't here, the thread on your order reaches a person, not a bot.":
        "Die sechs, die der Support am häufigsten beantwortet. Ist deine nicht dabei, erreicht der Thread deiner Bestellung einen Menschen, keinen Bot.",
      "Ask support": "Support fragen",
      "Can I play my own account while an order runs?":
        "Kann ich auf meinem eigenen Konto spielen, während eine Bestellung läuft?",
      "Yes, and it costs nothing. Pause the order from the order page and the booster stops at the end of the current game; unpause and it resumes the same night if a slot is open. Playing ranked yourself while a solo order is unpaused is the one thing to avoid — two people queuing the same account is what looks abnormal, not the boost.":
        "Ja, und es kostet nichts. Pausiere die Bestellung auf ihrer Seite, und der Booster hört am Ende der laufenden Partie auf; hebst du die Pause auf, geht es noch am selben Abend weiter, sofern ein Slot frei ist. Das Einzige, was du vermeiden solltest: selbst Ranked spielen, während eine Solo-Bestellung nicht pausiert ist — dass zwei Personen mit demselben Konto in die Warteschlange gehen, wirkt auffällig, nicht der Boost.",
      "What happens if my account gets a review or a ban?":
        "Was passiert, wenn mein Konto geprüft oder gesperrt wird?",
      "Support files the appeal for you and the order is refunded in full while it runs, so you are never paying for an account you cannot use. Boosting still breaks every listed game's terms of service — the risk is reduced as far as it can be, not removed.":
        "Der Support legt den Einspruch für dich ein, und die Bestellung wird während des Verfahrens voll erstattet — du zahlst also nie für ein Konto, das du nicht nutzen kannst. Boosting verstößt trotzdem gegen die Nutzungsbedingungen jedes gelisteten Spiels — das Risiko ist so weit wie möglich gesenkt, nicht beseitigt.",
      "Will the booster change my password or my settings?":
        "Ändert der Booster mein Passwort oder meine Einstellungen?",
      "No. Login details are used to sign in and nothing else — no password changes, no email changes, no purchases, no rune or loadout edits beyond the champions and roles you asked for. Sensitivity and crosshair are mirrored to yours, then restored. Change your password once the order closes anyway; the order page tells you when.":
        "Nein. Die Zugangsdaten dienen zum Anmelden und sonst nichts — keine Passwortänderungen, keine E-Mail-Änderungen, keine Käufe, keine Runen- oder Loadout-Änderungen über die gewünschten Champions und Rollen hinaus. Empfindlichkeit und Fadenkreuz werden deinen angeglichen und danach wiederhergestellt. Ändere dein Passwort trotzdem, sobald die Bestellung abgeschlossen ist; die Bestellseite sagt dir wann.",
      "How is the price calculated, and can it change after I pay?":
        "Wie wird der Preis berechnet, und kann er sich nach der Zahlung ändern?",
      "The price is per division crossed, so a longer climb costs more per step than a short one. It is fixed at checkout: the number on the button is the number charged, and nothing is added later. Duo adds 55% because the booster carries a second player, and add-ons are priced individually before you pay.":
        "Der Preis gilt pro überquerter Division, ein langer Aufstieg kostet also pro Stufe mehr als ein kurzer. Er wird an der Kasse fixiert: Der Betrag auf dem Knopf ist der Betrag, der abgebucht wird, und später kommt nichts dazu. Duo kostet 55 % mehr, weil der Booster einen zweiten Spieler trägt, und Extras werden vor der Zahlung einzeln ausgewiesen.",
      "Do I have to make an account to order?": "Muss ich ein Konto anlegen, um zu bestellen?",
      "No. Orders are created against your email and you get a one-click link to follow them. Set a password afterwards if you want the dashboard to remember your orders; skip it and the link still works. Your name, email and card details are never shared with the booster.":
        "Nein. Bestellungen werden über deine E-Mail angelegt, und du bekommst einen Ein-Klick-Link, um sie zu verfolgen. Vergib danach ein Passwort, wenn das Dashboard deine Bestellungen behalten soll; lässt du es, funktioniert der Link trotzdem. Dein Name, deine E-Mail und deine Kartendaten werden nie an den Booster weitergegeben.",
      "Can I pick a specific booster?": "Kann ich einen bestimmten Booster wählen?",
      "Yes — name one at checkout from their profile and the order waits for them instead of going to the open board. That means a slower start, so we show their current queue and slots before you commit. Leave it open and the first free booster in your bracket claims it, usually inside 18 min.":
        "Ja — nenne an der Kasse einen aus seinem Profil, und die Bestellung wartet auf ihn, statt auf das offene Board zu gehen. Das bedeutet einen späteren Start, deshalb zeigen wir seine aktuelle Warteschlange und Slots, bevor du dich festlegst. Lässt du sie offen, nimmt sie der erste freie Booster in deinem Bereich an, meist innerhalb von 18 Min.",

      /* support page */
      "Two ways in.": "Zwei Wege zu uns.",
      "Both are read": "Beide werden",
      "by people.": "von Menschen gelesen.",
      "No ticket robot, no \"we'll get back to you within 48 hours\". Discord is the fast one — that's where this market already lives, and it's where our staff sit all day.":
        "Kein Ticket-Roboter, kein „wir melden uns innerhalb von 48 Stunden“. Discord ist der schnelle Weg — dort lebt dieser Markt bereits, und dort sitzt unser Team den ganzen Tag.",
      "Median first reply last month": "Mediane Erstantwort letzten Monat",
      "Fastest": "Am schnellsten",
      "Discord — open a ticket in #support": "Discord — öffne ein Ticket in #support",
      "Public server, private ticket channels. Order questions, refunds, booster swaps and pre-sales, 24/7. You can also just read what other buyers are saying before you order anything, which is rather the point of it being public.":
        "Öffentlicher Server, private Ticket-Kanäle. Bestellfragen, Rückerstattungen, Booster-Wechsel und Vorverkauf, 24/7. Du kannst auch einfach lesen, was andere Käufer sagen, bevor du bestellst — genau dafür ist er öffentlich.",
      "Open the Discord invite": "Discord-Einladung öffnen",
      "On the record": "Schriftlich",
      "Email — info@esportsboost.com": "E-Mail — info@esportsboost.com",
      "Better for anything involving a payment dispute or a document. Answered in under two hours during EU and NA daytime, under six overnight.":
        "Besser für alles rund um Zahlungsstreit oder Dokumente. Antwort in unter zwei Stunden tagsüber in EU und NA, unter sechs über Nacht.",
      "Or write": "Oder schreib",
      "it here": "es hier",
      "Goes to the same inbox. If you have an order number, include it — it puts the message in front of the person handling that order.":
        "Landet im selben Postfach. Wenn du eine Bestellnummer hast, gib sie an — so kommt die Nachricht direkt zur Person, die diese Bestellung bearbeitet.",
      "Email": "E-Mail",
      "Order number (optional)": "Bestellnummer (optional)",
      "Message": "Nachricht",
      "What's going on?": "Worum geht es?",
      "Send message": "Nachricht senden",
      "Sending…": "Wird gesendet…",
      /* Die drei Ausgänge des Formulars — siehe den Kommentar im französischen Block. */
      "Sent — it's in the inbox.": "Gesendet — es liegt im Postfach.",
      "The reply lands at": "Die Antwort kommt an",
      "your address": "deine Adresse",
      "Discord is quicker if you'd rather not wait.":
        "Discord ist schneller, wenn du nicht warten möchtest.",
      "Noted — this is a preview.": "Notiert — das ist eine Vorschau.",
      "Nothing was emailed: this build has no mailbox configured. Write to":
        "Es wurde keine E-Mail gesendet: diese Version hat kein Postfach konfiguriert. Schreib an",
      "and it reaches the same people.": "und es erreicht dieselben Leute.",
      "That didn't send.": "Das wurde nicht gesendet.",
      "Rather than lose it, write to": "Damit nichts verloren geht, schreib an",
      "or open a ticket in Discord — both land in the same place.":
        "oder öffne ein Ticket auf Discord — beides landet am selben Ort.",
      "Before you write in": "Bevor du uns schreibst",

      /* reviews page — siehe den Kommentar im französischen Block. */
      "reviews": "Bewertungen",
      "customers": "Kunden",
      "Every review below is attached to a paid, completed order — pulled from Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so one-star reviews sit in the same feed.":
        "Jede Bewertung unten gehört zu einer bezahlten, abgeschlossenen Bestellung — aus Trustpilot und der Bewertung auf der Bestellseite gezogen und dedupliziert. Wir filtern nicht nach Sternen, Ein-Stern-Bewertungen stehen im selben Feed.",
      "across": "bei",
      "Read the worst first": "Zuerst die schlechtesten lesen",
      "Read on Trustpilot": "Auf Trustpilot lesen",
      "Overall rating": "Gesamtbewertung",
      "Verified only": "Nur verifiziert",
      "Click a row to filter the feed by that rating.":
        "Klicke auf eine Zeile, um den Feed nach dieser Bewertung zu filtern.",
      "Any": "Alle",
      "or less": "oder weniger",
      "Most recent": "Neueste",
      "Highest rated": "Beste Bewertung",
      "Lowest rated": "Schlechteste Bewertung",
      "Clear filters": "Filter zurücksetzen",
      "Nothing matches that yet": "Dazu passt noch nichts",
      "No review in the feed has that rating for this game. Widen the filters to see the rest.":
        "Keine Bewertung im Feed hat diese Note für dieses Spiel. Erweitere die Filter, um den Rest zu sehen.",
      "Load 30 more": "30 weitere laden",
      "Show the rest": "Rest anzeigen",
      "Excellent": "Hervorragend",
      "Where the score": "Woher die Bewertung",
      "comes from": "kommt",
      "A review request goes out once, on delivery, and never again. Nothing is incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than competitors who buy them, and it's the reason the score is worth reading at all.":
        "Eine Bewertungsanfrage geht einmal raus, bei Lieferung, und nie wieder. Nichts wird belohnt — kein Rabatt fürs Bewerten, keine Prämie für fünf Sterne. Das hält das Volumen niedriger als bei Konkurrenten, die sie kaufen, und deshalb ist die Bewertung überhaupt lesenswert.",

      /* the demo page (was "track my order") — design_handoff_track_order */
      "Demo": "Demo",
      "Demo dashboard": "Demo-Dashboard",
      "Your link works without a password.": "Dein Link funktioniert ohne Passwort.",
      "Guest orders are tracked by the link we emailed you. Lost it? Put the address you paid with below and we'll send it again. Nothing to remember, nothing to reset.":
        "Gast-Bestellungen werden über den Link verfolgt, den wir dir gemailt haben. Verloren? Gib unten die Adresse ein, mit der du bezahlt hast, und wir schicken ihn erneut. Nichts zu merken, nichts zurückzusetzen.",
      "No account, no password — the link is the login":
        "Kein Konto, kein Passwort — der Link ist der Login",
      "It never expires and works on any device": "Er läuft nie ab und funktioniert auf jedem Gerät",
      "Find your order": "Bestellung finden",
      "Guest safe": "Ohne Konto",
      "Order number": "Bestellnummer",
      /* the two states of the helper line under the order-number field, and the
         two submit labels — page_demo()'s own script owns these nodes and asks
         for them through esbT, because they swap at runtime. */
      "On your confirmation email, under the total.":
        "In deiner Bestätigungs-E-Mail, unter dem Gesamtbetrag.",
      "We can't find that order number. Check the confirmation email, or use the address you paid with below.":
        "Diese Bestellnummer finden wir nicht. Prüfe die Bestätigungs-E-Mail oder nutze unten die Adresse, mit der du bezahlt hast.",
      "or": "oder",
      "The email you paid with": "Die E-Mail, mit der du bezahlt hast",
      "We resend the link to that address. It never expires and it works on any device.":
        "Wir schicken den Link erneut an diese Adresse. Er läuft nie ab und funktioniert auf jedem Gerät.",
      "Find my order": "Meine Bestellung finden",
      "Email me the link": "Link per E-Mail schicken",
      "Demo — no email was sent.": "Demo — es wurde keine E-Mail gesendet.",
      "On the live site the link reaches": "Auf der Live-Site erreicht der Link",
      "inside a minute, it never expires, and it opens the dashboard below on any device.":
        "innerhalb einer Minute, er läuft nie ab und öffnet das Dashboard unten auf jedem Gerät.",
      "The order number is in your confirmation email, on the line under the total.":
        "Die Bestellnummer steht in deiner Bestätigungs-E-Mail, in der Zeile unter dem Gesamtbetrag.",

      /* the resolved order */
      "Back to the order lookup": "Zurück zur Bestellsuche",
      "In progress": "In Bearbeitung",
      "Paused": "Pausiert",
      "Example": "Beispiel",
      "Pause order": "Bestellung pausieren",
      "Resume order": "Fortsetzen",
      "Order paused.": "Bestellung pausiert.",
      "The account is free within minutes and the delivery clock stops. Resume whenever you're done playing.":
        "Das Konto ist innerhalb von Minuten frei und die Lieferzeit stoppt. Setze fort, wenn du fertig gespielt hast.",
      "last game": "letztes Spiel",
      "Play window": "Spielzeiten",
      "Watch live": "Live zusehen",
      "Streaming now": "Streamt gerade",
      "Not streaming": "Streamt nicht",
      "is sharing their screen.": "teilt gerade den Bildschirm.",
      "isn't streaming right now.": "streamt gerade nicht.",
      "Discord screen share": "Discord-Bildschirmübertragung",
      "Join and watch": "Beitreten und zusehen",
      "Open the order channel": "Kanal zur Bestellung öffnen",
      "The channel is private to you and your booster, and closes when the order is delivered.":
        "Der Kanal ist privat zwischen dir und deinem Booster und wird nach der Lieferung geschlossen.",
      "Timeline": "Verlauf",
      "reached": "erreicht",
      "claimed the order": "hat die Bestellung angenommen",
      "after payment": "nach der Zahlung",
      "Yesterday, 23:10": "Gestern, 23:10",
      "— any time this order is open.": "— jederzeit, solange diese Bestellung offen ist.",
      "Progress": "Fortschritt",
      "Match": "Spiel",
      "Result": "Ergebnis",
      "When": "Wann",
      "Ranked solo": "Ranked Solo",
      "Win": "Sieg",
      "Loss": "Niederlage",
      "min ago": "Min.",

      /* checkout */
      "Secure checkout": "Sichere Kasse",
      "Need a hand?": "Brauchst du Hilfe?",
      "Required": "Erforderlich",
      "Optional": "Optional",
      "Anything the booster should know": "Etwas, das der Booster wissen sollte",
      "Enter an email we can send the order link to.":
        "Gib eine E-Mail an, an die wir den Bestell-Link senden können.",
      "Mornings": "Vormittags",
      "Afternoons": "Nachmittags",
      "Evenings": "Abends",
      "Nights": "Nachts",
      "Card, Apple Pay and Google Pay are all on the next screen — details are entered on Stripe's secure checkout, so we never see or store them. Statements read as a neutral merchant name.":
        "Karte, Apple Pay und Google Pay findest du alle auf dem nächsten Bildschirm — die Daten werden auf Stripes sicherer Kasse eingegeben, wir sehen und speichern sie nie. Auszüge zeigen einen neutralen Händlernamen.",
      "Secured by Stripe": "Gesichert durch Stripe",
      "Contacting payment…": "Zahlung wird vorbereitet…",
      "Refunded in full until a booster claims it":
        "Volle Rückerstattung, bis ein Booster die Bestellung annimmt",
      "Last chance to add": "Letzte Gelegenheit zum Hinzufügen",
      "Discount code": "Rabattcode",
      "applied": "angewendet",
      "No code applied": "Kein Code angewendet",
      "Have a code?": "Hast du einen Code?",
      "Have another code?": "Noch einen Code?",
      "Enter a code": "Code eingeben",
      "Close": "Schließen",
      "Your email": "Deine E-Mail",
      "Order details": "Bestelldetails",
      "Payment": "Zahlung",
      "Checkout": "Kasse",
      "No account needed. We create the order under your email and send a one-click link to follow it. You can set a password afterwards if you want one.":
        "Kein Konto nötig. Wir erstellen die Bestellung unter deiner E-Mail und senden einen Ein-Klick-Link zum Verfolgen. Du kannst danach ein Passwort festlegen, wenn du möchtest.",
      "Used for your order link, and to send you your cart if you don't finish. No marketing unless you tick the box at the end.":
        "Für deinen Bestell-Link, und um dir deinen Warenkorb zu schicken, falls du nicht fertig wirst. Kein Marketing, außer du setzt am Ende das Häkchen.",
      "Preferred hours": "Bevorzugte Zeiten",
      "Any time": "Jederzeit",
      "My usual play hours (18:00–00:00)": "Meine üblichen Spielzeiten (18:00–00:00)",
      "While I'm at work (09:00–17:00)": "Während ich arbeite (09:00–17:00)",
      "Overnight only": "Nur über Nacht",
      "Anything the booster should know (optional)": "Etwas, das der Booster wissen sollte (optional)",
      "Champion pool, roles, don't touch ranked flex…":
        "Champion-Pool, Rollen, Ranked Flex nicht anfassen…",
      "Hours you can play, roles, other accounts…": "Spielbare Zeiten, Rollen, andere Konten…",
      "Pay with": "Bezahlen mit",
      "Payment method": "Zahlungsmethode",
      "Card": "Karte",
      "Crypto": "Krypto",
      "— coming soon": "— bald verfügbar",
      "Card details are entered on Stripe's secure checkout — we never see or store them. Statements read as a neutral merchant name.":
        "Kartendaten werden auf Stripes sicherer Kasse eingegeben — wir sehen und speichern sie nie. Auszüge zeigen einen neutralen Händlernamen.",
      "Email me when my order is claimed and when it's done. Nothing else.":
        "Benachrichtige mich, wenn meine Bestellung angenommen und wenn sie fertig ist. Sonst nichts.",
      "Place the order": "Bestellung aufgeben",
      "Read the guarantee": "Garantie lesen",
      "Order placed": "Bestellung aufgegeben",
      "This is a local preview, so no payment was taken and no email was sent. In production this is the point where the order goes on the booster board, the confirmation email leaves, and":
        "Dies ist eine lokale Vorschau, es wurde also keine Zahlung eingezogen und keine E-Mail gesendet. In der Produktion landet hier die Bestellung auf dem Booster-Board, die Bestätigungs-E-Mail geht raus, und",
      "fires to GA4 and to the Meta CAPI gateway.": "wird an GA4 und das Meta-CAPI-Gateway gesendet.",
      "See what the dashboard looks like": "So sieht das Dashboard aus",
      "Order summary": "Bestellübersicht",
      "Locked at checkout": "An der Kasse fixiert",
      "Climb": "Aufstieg",
      "Boost": "Boost",
      "Money-back until claimed": "Geld zurück bis zur Annahme",
      "Change the order": "Bestellung ändern",

      /* checkout success */
      "Confirming payment…": "Zahlung wird bestätigt…",
      "One moment": "Einen Moment",
      "We're confirming your payment with Stripe.": "Wir bestätigen deine Zahlung mit Stripe.",
      "Order": "Bestellung",
      "Paid": "Bezahlt",

      /* become a booster */
      "Work here": "Arbeite bei uns",
      "Get paid": "Werde bezahlt",
      "for the queue": "für die Queue,",
      "you'd play anyway.": "die du eh spielen würdest.",
      "Payouts weekly, 70% of the order value on solo and 75% on duo, no deductions for the platform's payment fees. Pick your own shifts; take an order or don't. What we ask for is the rank, a clean account history, and that you never pass an account to anyone.":
        "Wöchentliche Auszahlungen, 70 % des Bestellwerts bei Solo und 75 % bei Duo, ohne Abzug der Zahlungsgebühren der Plattform. Wähle deine eigenen Schichten; nimm eine Bestellung an oder nicht. Wir verlangen den Rang, einen sauberen Konto-Verlauf und dass du nie ein Konto an jemanden weitergibst.",
      "Of the order, to you": "Der Bestellung, für dich",
      "Weekly": "Wöchentlich",
      "Payouts, no minimum": "Auszahlungen, kein Minimum",
      "5 games": "5 Spiele",
      "Live trial before onboarding": "Live-Test vor dem Onboarding",
      "In-game name": "Ingame-Name",
      "Peak rank": "Höchster Rang",
      "Anything else": "Sonstiges",
      "Apply": "Bewerben",
      "How the trial works": "So läuft der Test",

      /* legal */
      "Last updated": "Zuletzt aktualisiert",
      "Questions about any of this go to": "Fragen dazu gehen an den",
      "support": "Support",
      "Plain answers, same day.": "Klare Antworten, am selben Tag.",
      "Terms of service": "Nutzungsbedingungen",
      "Refund policy": "Rückerstattungsrichtlinie",
      /* Siehe den fr-Block: Firmenname und Anschrift sind Daten und bleiben
         unübersetzt — übersetzt werden nur die Beschriftungen drumherum. */
      "Who to write to": "An wen Sie schreiben",
      "Open a support ticket": "Support-Ticket eröffnen",
      "Who's responsible for your data": "Wer für Ihre Daten verantwortlich ist",

      /* 404 */
      "Error 404": "Fehler 404",
      "That page": "Diese Seite",
      "isn't on": "steht nicht",
      "the ladder.": "auf der Ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Der Link ist tot oder die Seite wurde verschoben. Der Rechner ist so oder so zwei Klicks entfernt.",
      "Pick a game": "Spiel auswählen",
      "Back to the homepage": "Zurück zur Startseite",

      /* free guides landing — design_handoff_free_guides */
      "Free guides · no payment": "Kostenlose Guides · keine Zahlung",
      "Browse boosting": "Boosting ansehen",
      "Free guides": "Kostenlose Guides",
      "The two guides our boosters actually wrote.":
        "Die zwei Guides, die unsere Booster wirklich geschrieben haben.",
      "PDFs, yours to keep": "PDFs, die dir gehören",
      "Free, and they stay free": "Kostenlos, und bleiben es",
      "One email, no spam": "Eine E-Mail, kein Spam",
      "Players downloaded them": "Spieler haben sie geladen",
      "Chapters + 12 drills": "Kapitel + 12 Übungen",
      "Reader rating": "Leserbewertung",
      "Which do you want?": "Welche möchtest du?",
      "Instant": "Sofort",
      "Take both — they're free, and most people play both.":
        "Nimm beide — sie sind kostenlos, und die meisten spielen beides.",
      "Also send me one email a month with new guides and patch notes. Nothing else, and one click unsubscribes.":
        "Schickt mir außerdem einmal im Monat eine E-Mail mit neuen Guides und Patchnotes. Sonst nichts, und ein Klick zum Abmelden.",
      "We never sell your address.": "Wir verkaufen deine Adresse nie.",
      "Privacy policy": "Datenschutzerklärung",
      "Check your inbox.": "Sieh in deinem Postfach nach.",
      "on the way to": "unterwegs an",
      "If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        "Wenn in zwei Minuten nichts ankommt, sieh unter Werbung nach — dort landet es manchmal zuerst.",
      "Use a different address": "Andere Adresse verwenden",
      "Send me both guides": "Schickt mir beide Guides",
      "Send me the League guide": "Schickt mir den League-Guide",
      "Send me the Valorant guide": "Schickt mir den Valorant-Guide",
      "Pick a guide first": "Wähle zuerst einen Guide",
      "Both guides, one email, two attachments.": "Zwei Guides, eine E-Mail, zwei Anhänge.",
      "Only one? The other is free too.": "Nur einer? Der andere ist auch kostenlos.",
      "Pick at least one guide.": "Wähle mindestens einen Guide.",
      "Used to send the guides. Nothing else unless you tick the box below.":
        "Wird zum Versand der Guides genutzt. Sonst nichts, außer du setzt unten das Häkchen.",
      "Enter an address we can send the PDFs to.":
        "Gib eine Adresse an, an die wir die PDFs senden können.",
      "Arrives in about a minute. No card, no account.":
        "Kommt in etwa einer Minute an. Keine Karte, kein Konto.",
      "That address does not look right — check it and try again.":
        "Diese Adresse sieht nicht richtig aus — prüfe sie und versuche es erneut.",
      "Both guides are": "Beide Guides sind",
      "The League guide is": "Der League-Guide ist",
      "The Valorant guide is": "Der Valorant-Guide ist",
      "Your guide is": "Dein Guide ist",
      "What's inside": "Was drin ist",
      "Six chapters each, no padding.": "Sechs Kapitel pro Guide, ohne Füllmaterial.",
      "Who wrote them": "Wer sie geschrieben hat",
      "Written by people who play these ranks for a living.":
        "Geschrieben von Leuten, die diese Ränge beruflich spielen.",
      "The authors": "Die Autoren",
      "Seven authors across two games": "Sieben Autoren in zwei Spielen",
      "Rewritten every patch cycle": "Zu jedem Patch neu geschrieben",
      "Readers": "Leser",
      "What they changed for them.": "Was sie für sie verändert haben.",
      "Before you hand over an email": "Bevor du eine E-Mail herausgibst",
      "Fair questions. We would ask them too.": "Faire Fragen. Wir würden sie auch stellen.",
      "Two guides. One email address.": "Zwei Guides. Eine E-Mail-Adresse.",
      "Never sold, never rented": "Nie verkauft, nie vermietet",
      "One click unsubscribes": "Ein Klick zum Abmelden",
      "Send them": "Schickt sie",

      /* ── game pages: the six proof bands (design_handoff_lol_game_page) ──
         See the French block: the `{}` entries are the sentences that name
         the game, its publisher or its rank floor, and the placeholder sits
         where German word order wants it, not where English left it. */
      "Our {} boosters.": "Unsere {}-Booster.",
      "From {} orders this month.": "Aus {}-Bestellungen diesen Monat.",
      "Asked before every {} order": "Vor jeder {}-Bestellung gefragt",
      "It goes on the board and a verified {} booster takes it. If nothing claims it within 24 hours, the order refunds itself.":
        "Sie geht aufs Board und ein verifizierter {}-Booster nimmt sie. Nimmt sie innerhalb von 24 Stunden niemand, erstattet sich die Bestellung von selbst.",
      "{} of them, {} only — {} or above, with a clean account history and a name you can look up. Order without naming anyone and it goes to whoever is free; name one and it waits for them.":
        "{} insgesamt, nur auf {} — {} oder höher, mit sauberem Account und einem Namen, den du nachschlagen kannst. Bestell ohne jemanden zu nennen und sie geht an den Nächsten, der frei ist; nenn einen und sie wartet auf ihn.",
      "{} flags accounts on patterns, not accusations: a login from the other side of the world, a sudden change in hours, a win rate that doesn't look human. So we don't produce any of those patterns. Your booster connects through an enterprise VPN in your region, plays inside the hours you set, and keeps your settings.":
        "{} greift Accounts wegen Mustern auf, nicht wegen Anschuldigungen: ein Login vom anderen Ende der Welt, plötzlich andere Spielzeiten, eine Winrate, die nicht menschlich aussieht. Also erzeugen wir keins dieser Muster. Dein Booster verbindet sich über ein Enterprise-VPN in deiner Region, spielt in den Zeiten, die du festlegst, und behält deine Einstellungen.",
      "Boosting is against {}'s terms of service. We have never had an account actioned for any of our {} clients and we recover any that are, but nobody honest will tell you the risk is zero — and anyone who does is selling you something.":
        "Boosting verstößt gegen die Nutzungsbedingungen von {}. Bei keinem unserer {} Kunden wurde je ein Account sanktioniert, und wir holen jeden zurück, bei dem es passiert — aber niemand, der ehrlich ist, sagt dir, das Risiko sei null. Wer das tut, will dir etwas verkaufen.",
      "Four": "Vier",
      "Twenty-nine": "Neunundzwanzig",
      "Thirty-one": "Einunddreißig",

      /* 01 How it runs */
      "Four steps, and you can see all of them.": "Vier Schritte, und du siehst sie alle.",
      "The number you see is the number you pay. Nothing is added later, and no account is needed to buy.":
        "Die Zahl, die du siehst, ist die Zahl, die du zahlst. Später kommt nichts dazu, und zum Kaufen brauchst du kein Konto.",
      "Price fixed at checkout": "Preis an der Kasse fixiert",
      "A booster claims it": "Ein Booster nimmt sie an",
      "Median 18 minutes": "Median 18 Minuten",
      "Watch it climb": "Sieh beim Aufstieg zu",
      "Every game appears on your order page with the result, the KDA and the LP swing. Pause it any time you want to play.":
        "Jedes Spiel taucht auf deiner Bestellseite auf, mit Ergebnis, KDA und LP-Änderung. Pausier sie, sobald du selbst spielen willst.",
      "Updated as games finish": "Aktualisiert, sobald Spiele enden",
      "Finished, or refunded": "Fertig, oder erstattet",
      "Delivered to the rank you set. Anything not delivered is refunded pro-rata, any time the order is open.":
        "Geliefert bis zu dem Rang, den du gesetzt hast. Was nicht geliefert wird, wird anteilig erstattet, jederzeit solange die Bestellung offen ist.",
      "Back within 5 business days": "Zurück in 5 Werktagen",

      /* 02 While it runs */
      "While it runs": "Während sie läuft",
      "Watch every game land.": "Sieh jedem Spiel live zu.",
      "The order page opens from the link we email you — no password, no app. It updates as games finish, so you never have to ask where things are.":
        "Die Bestellseite öffnet sich über den Link, den wir dir mailen — kein Passwort, keine App. Sie aktualisiert sich, sobald Spiele enden: Du musst nie nachfragen, wie es steht.",
      "The LP graph, not a percentage": "Die LP-Kurve, kein Prozentwert",
      "The RR graph, not a percentage": "Die RR-Kurve, kein Prozentwert",
      "Every game plotted from the rank you started at, so a bad night is visible instead of averaged away.":
        "Jedes Spiel ab deinem Startrang eingezeichnet: Ein schlechter Abend ist sichtbar, statt im Durchschnitt zu verschwinden.",
      "Match history with replays": "Spielverlauf mit Replays",
      "Result, KDA and LP for every game, each with a replay link that stays live for 14 days.":
        "Ergebnis, KDA und LP für jedes Spiel, jeweils mit einem Replay-Link, der 14 Tage gültig bleibt.",
      "Result, KDA and RR for every game, each with a replay link that stays live for 14 days.":
        "Ergebnis, KDA und RR für jedes Spiel, jeweils mit einem Replay-Link, der 14 Tage gültig bleibt.",
      "One thread with your booster": "Ein Thread mit deinem Booster",
      "Ask for a champion, a pause or a swap. Support reads the same thread, so nothing gets repeated.":
        "Bitte um einen Champion, eine Pause oder einen Wechsel. Der Support liest denselben Thread — nichts muss wiederholt werden.",
      "games this order": "Spiele in dieser Bestellung",

      /* 03 Who plays it */
      "Who plays it": "Wer es spielt",

      /* the mystery discount — design_handoff_mystery_discount */
      "Mystery discount": "Geheimrabatt",
      "Last-chance discount": "Last-Minute-Rabatt",
      "Come back offer": "Willkommen-zurück-Angebot",
      "Sealed for you": "Für dich versiegelt",
      "A mystery discount": "Ein Geheimrabatt",
      "on this order": "auf diese Bestellung",
      "One per customer": "Einer pro Kunde",
      "Up to": "Bis zu",
      "off": "Rabatt",
      "The deck holds": "Der Stapel enthält",
      "10%, 20% and 30%": "10 %, 20 % und 30 %",
      "off the order you just configured. Pick a card, tell us where to send the code, and we open it on the spot.":
        "Rabatt auf die Bestellung, die du gerade konfiguriert hast. Wähl eine Karte aus, sag uns, wohin der Code soll, und wir öffnen sie sofort.",
      "Picked": "Gewählt",
      "Hold card": "Karte reservieren",
      "No thanks, I'll pay full price": "Nein danke, ich zahle den vollen Preis",
      "held for you": "für dich reserviert",
      "Where should we send it?": "Wohin sollen wir ihn schicken?",
      "We email the code so it survives a closed tab, then open the card on the next screen.":
        "Wir schicken den Code per E-Mail, damit er einen geschlossenen Tab übersteht, und öffnen die Karte im nächsten Schritt.",
      "The card is opened on the next screen either way.":
        "Die Karte wird im nächsten Schritt so oder so geöffnet.",
      "Enter an address we can send the code to.":
        "Gib eine Adresse an, an die wir den Code schicken können.",
      "That didn't go through. Try again in a moment.":
        "Das hat nicht geklappt. Versuch es gleich noch einmal.",
      "Also send me the free rank guides and patch notes. One email a month, one click to stop.":
        "Schickt mir auch die kostenlosen Rang-Guides und Patchnotes. Eine E-Mail im Monat, ein Klick zum Abbestellen.",
      "Never sold or rented.": "Nie verkauft, nie vermietet.",
      "Open card": "Karte öffnen",
      "Opening card": "Karte wird geöffnet",
      "Drawing your code on the server": "Dein Code wird auf dem Server erstellt",
      "Available for 1 hour": "1 Stunde gültig",
      "left": "übrig",
      "Bingo — card": "Bingo — Karte",
      "pays the top rate": "zahlt den Höchstsatz",
      "The best rate in the deck — double the 15% sale, and live for 1 hour from the moment you opened it.":
        "Der beste Satz im Stapel — doppelt so viel wie die 15 % der Aktion, und ab dem Öffnen 1 Stunde gültig.",
      "Your order": "Deine Bestellung",
      "Apply my discount": "Rabatt anwenden",
      "Continue at full price": "Zum vollen Preis fortfahren",
      "Live for 1 hour on this order. A copy is in your inbox, so closing this tab doesn't lose it.":
        "1 Stunde lang für diese Bestellung gültig. Eine Kopie liegt in deinem Postfach — den Tab zu schließen verliert sie nicht.",
      "Live for 1 hour on this order. Copy the code before you close this tab — we couldn't email it.":
        "1 Stunde lang für diese Bestellung gültig. Kopiere den Code, bevor du den Tab schließt — wir konnten ihn nicht per E-Mail schicken.",
      "No problem.": "Kein Problem.",
      "This address already used its card.": "Diese Adresse hat ihre Karte bereits benutzt.",
      "Your order stays where it is and we won't ask again on this visit. The sitewide 15% code still applies at checkout.":
        "Deine Bestellung bleibt, wie sie ist, und wir fragen bei diesem Besuch nicht noch einmal. Der seitenweite 15-%-Code gilt an der Kasse weiterhin.",
      "One card per customer, and this inbox has opened its one. The sitewide 15% code still applies at checkout.":
        "Eine Karte pro Kunde, und dieses Postfach hat seine geöffnet. Der seitenweite 15-%-Code gilt an der Kasse weiterhin.",
      "Back to my order": "Zurück zu meiner Bestellung",
      "Actually, let me pick a card": "Doch, ich wähle eine Karte",

      /* ── strings the pages gained after the last sweep: the account
         prompt, the application form's four outcomes, and the three
         accessible names that were still reaching FR/DE readers in
         English. The promo chip's is a {} pattern because it is built
         from the live code and percentage. */
      "When you place an order it shows up here — the climb, the price and its status, updated as your booster works. Ready to start?":
        "Sobald du eine Bestellung aufgibst, taucht sie hier auf — der Aufstieg, der Preis und der Status, aktualisiert während dein Booster spielt. Losgehen?",
      "Almost — one more thing.": "Fast — eine Sache noch.",
      "Add your in-game name, peak rank, and a Discord we can reach you on.":
        "Trag deinen Ingame-Namen ein, deinen höchsten Rang und einen Discord, über den wir dich erreichen.",
      "Application received.": "Bewerbung angekommen.",
      "We'll message you on Discord — keep an eye out.":
        "Wir melden uns auf Discord — halt die Augen offen.",
      "Nothing was emailed: this build has no mailbox configured. Send your application to":
        "Es wurde keine E-Mail gesendet: diese Version hat kein Postfach konfiguriert. Schick deine Bewerbung an",
      "Rather than lose it, email": "Damit nichts verloren geht, mail an",
      "with your rank and Discord.": "mit deinem Rang und deinem Discord.",
      "Main": "Hauptnavigation",
      "Log in or create an account": "Anmelden oder Konto erstellen",
      "Copy discount code {} — {} off": "Rabattcode {} kopieren — {} Rabatt",
      "Copy discount code {}": "Rabattcode {} kopieren",
      "Checking that code…": "Code wird geprüft…",

      /* ── /accounts.html — the ready-made-account board, its cross-sell
         strip on the League page, and the checkout's account variants.
         Listing NAMES and rank bands are data and stay in English with every
         other rank on the site; every sentence around them is translated. */
      "Accounts": "Accounts",
      "{} accounts": "{}-Accounts",
      "Level 30 and ranked, on NA, EUW, EUNE and OCE. Full email access on every one, so you change the recovery mailbox and the password the moment it lands and it is genuinely yours.":
        "Level 30 und ranked, auf NA, EUW, EUNE und OCE. Bei jedem voller E-Mail-Zugang — du änderst Wiederherstellungs-Postfach und Passwort direkt bei der Lieferung, und der Account gehört wirklich dir.",
      "Full email access": "Voller E-Mail-Zugang",
      "{}-day replacement": "Ersatz innerhalb von {} Tagen",
      "Within the hour": "Innerhalb einer Stunde",
      "Eight": "Acht",
      "{} listings": "{} Angebote",
      "listings": "Angebote",
      "Pick a rank and a shard.": "Wähl einen Rang und einen Server.",
      "Every account ships with full email access, on the shard you pick, replaced inside":
        "Jeder Account kommt mit vollem E-Mail-Zugang, auf dem Server deiner Wahl, und wird innerhalb von",
      "days if it is recovered. The exact division inside a band is whatever is in stock that day.":
        "Tagen ersetzt, falls er zurückgeholt wird. Welche Division genau es innerhalb einer Spanne wird, hängt vom Lagerbestand des Tages ab.",
      "All ranks": "Alle Ränge",
      "Shard": "Server",
      "Any shard": "Alle Server",
      "In stock": "Auf Lager",
      "Sold out": "Ausverkauft",
      "level": "Level",
      "blue essence": "blaue Essenz",
      "champions": "Champions",
      "Buy": "Kaufen",
      "Ask when it is back": "Fragen, wann er zurück ist",
      "A clean level-30 with the essence to build a pool from scratch. No ranked games played, so placements are yours.":
        "Ein sauberer Level-30 mit genug Essenz, um dir einen Pool von Grund auf zu bauen. Keine Ranked-Spiele gespielt — die Platzierungen gehören dir.",
      "The same account with roughly double the essence — enough for a full role's worth of champions on day one.":
        "Derselbe Account mit ungefähr doppelter Essenz — genug für eine komplette Rolle ab Tag eins.",
      "Placed and played. The exact division inside the band depends on what is in stock the day you order.":
        "Platziert und gespielt. Welche Division genau es in der Spanne wird, hängt vom Lagerbestand am Bestelltag ab.",
      "Last season's Gold, honour level 2 or above, no restrictions on the account.":
        "Gold in der letzten Season, Ehre Stufe 2 oder höher, keine Einschränkungen auf dem Account.",
      "Platinum with a played match history — it does not read as a fresh account to anybody in your games.":
        "Platin mit echter Match-History — für niemanden in deinen Spielen sieht das nach einem frischen Account aus.",
      "Emerald on a full champion pool. The smallest stock on the page, so the shard list is short.":
        "Smaragd mit vollem Champion-Pool. Der kleinste Bestand auf der Seite — deshalb die kurze Server-Liste.",
      "Diamond, hand-played, with the match history behind it. Ships with the honour level intact.":
        "Diamant, von Hand gespielt, mit der passenden Match-History. Wird mit intaktem Ehre-Level geliefert.",
      "The top of what we sell as a fixed listing. Anything above Diamond I is quoted per account in Discord.":
        "Das Obere von dem, was wir zum Festpreis verkaufen. Über Diamant I wird jeder Account einzeln auf Discord angeboten.",
      "Nothing in stock on that combination.": "Nichts auf Lager für diese Kombination.",
      "We had no": "Wir hatten keinen",
      "account for": "Account für",
      "when this page was built. Loosen one of the two, or ask us in Discord — stock moves daily.":
        "als diese Seite gebaut wurde. Lockere eines von beiden, oder frag uns auf Discord — der Bestand ändert sich täglich.",
      "Show everything": "Alles anzeigen",
      "What arrives": "Was ankommt",
      "Credentials, and the mailbox behind them.":
        "Die Zugangsdaten — und das Postfach dahinter.",
      "Full email access — you change the email and the password on delivery. Without that an account is a rental somebody else can end, so we do not sell one we cannot hand over completely.":
        "Voller E-Mail-Zugang — du änderst Adresse und Passwort bei der Lieferung. Ohne das ist ein Account nur eine Miete, die jemand anderes beenden kann, also verkaufen wir keinen, den wir nicht vollständig übergeben können.",
      "Credentials by email": "Zugangsdaten per E-Mail",
      "Login, password and the recovery mailbox, sent to the address you check out with.":
        "Login, Passwort und Wiederherstellungs-Postfach, an die Adresse aus dem Checkout.",
      "Usually within the hour": "Normalerweise innerhalb einer Stunde",
      "Manually handed over and checked before it is sent. Not an automated drop.":
        "Von Hand übergeben und vor dem Versand geprüft. Keine automatische Auslieferung.",
      "Replaced inside {} days": "Ersetzt innerhalb von {} Tagen",
      "If it is recovered or banned in the warranty window you get another of the same rank, or the money back.":
        "Wird er im Garantiezeitraum zurückgeholt oder gebannt, bekommst du einen anderen im selben Rang — oder dein Geld zurück.",
      "Never resold": "Nie doppelt verkauft",
      "A listing leaves this page the moment it is sold. One buyer per account.":
        "Ein Angebot verschwindet von dieser Seite, sobald es verkauft ist. Ein Käufer pro Account.",
      "The risk": "Das Risiko",
      "What Riot's rules actually say.": "Was Riots Regeln wirklich sagen.",
      "The same standard as the rest of the site: we tell you what the risk is, what we do about it, and where our warranty stops.":
        "Derselbe Maßstab wie auf dem Rest der Seite: Wir sagen, worin das Risiko besteht, was wir dagegen tun und wo unsere Garantie endet.",
      "Riot licenses an account to one person and does not permit it to be sold or transferred. If they act on that, the sanction is the account itself, not a suspension you sit out. We hand over full email access so the account is genuinely yours to secure, and we replace it inside the warranty window — but we will not tell you the risk is zero, because it isn't.":
        "Riot lizenziert einen Account an eine Person und erlaubt weder Verkauf noch Übertragung. Wenn Riot einschreitet, trifft es den Account selbst, nicht eine Sperre, die man aussitzt. Wir übergeben vollen E-Mail-Zugang, damit der Account wirklich Ihnen gehört und von Ihnen abgesichert werden kann, und wir ersetzen ihn innerhalb der Garantie — aber wir werden Ihnen nicht sagen, das Risiko sei null, denn das ist es nicht.",
      "Read the full guarantee": "Die ganze Garantie lesen",
      "Questions": "Fragen",
      "The ones that decide it.": "Die, die es entscheiden.",
      "Three of these argue against the sale. They are the reason the other four are worth reading.":
        "Drei davon sprechen gegen den Kauf. Genau deshalb lohnt es sich, die anderen vier zu lesen.",
      "Ask us anything else": "Frag uns alles andere",
      "Is buying an account against Riot's rules?":
        "Verstößt der Kauf eines Accounts gegen Riots Regeln?",
      "Yes. An account is licensed to one person and Riot does not permit it to be sold or transferred. If they act on it, the account goes — that is a different outcome from a boosting suspension, and it is the reason the warranty below exists. Anyone telling you this is risk-free is selling you something.":
        "Ja. Ein Account ist an eine Person lizenziert, und Riot erlaubt weder Verkauf noch Übertragung. Wenn Riot einschreitet, ist der Account weg — das ist ein anderes Ergebnis als eine Sperre wegen Boosting, und genau dafür gibt es die Garantie unten. Wer dir sagt, das sei risikofrei, will dir etwas verkaufen.",
      "Do I actually own it, or can you take it back?":
        "Gehört er wirklich mir, oder könnt ihr ihn zurückholen?",
      "Every listing ships with full email access. You change the recovery mailbox and the password on delivery and we no longer hold anything that reaches it. We do not sell accounts we cannot hand over completely — an account without its email is a rental somebody else can end.":
        "Jedes Angebot kommt mit vollem E-Mail-Zugang. Du änderst bei der Lieferung Postfach und Passwort, und wir halten danach nichts mehr, was dorthin führt. Wir verkaufen keine Accounts, die wir nicht vollständig übergeben können — ein Account ohne seine E-Mail ist eine Miete, die jemand anderes beenden kann.",
      "What happens if it is banned or recovered?":
        "Was passiert, wenn er gebannt oder zurückgeholt wird?",
      "Inside {} days of delivery you get another account of the same rank, or the money back, your choice. After that window we cannot tell a recovery from a chargeback, so the warranty ends — that is the honest limit of it, and it is why the window is stated rather than implied.":
        "Innerhalb von {} Tagen nach der Lieferung bekommst du einen anderen Account im selben Rang oder dein Geld zurück, ganz wie du willst. Danach können wir eine Rückholung nicht mehr von einer Rückbuchung unterscheiden, also endet die Garantie — das ist ihre ehrliche Grenze, und deshalb steht die Frist da, statt angedeutet zu werden.",
      "Can I pick the exact division?": "Kann ich die genaue Division aussuchen?",
      "No. A listing names a band — Gold IV to Gold I — and you get what is in stock the day you order, inside that band. We do not know which one it will be when you buy, so we do not print a division we might not have.":
        "Nein. Ein Angebot nennt eine Spanne — Gold IV bis Gold I — und du bekommst, was am Bestelltag innerhalb dieser Spanne auf Lager ist. Wir wissen beim Kauf nicht, welche es wird, also drucken wir keine Division ab, die wir vielleicht nicht haben.",
      "How fast is delivery?": "Wie schnell ist die Lieferung?",
      "Usually inside the hour, in the working day. Each handover is done by a person who checks the account first, so it is not instant and we do not claim it is — an automated drop is how buyers end up with an account somebody already logged into.":
        "Meist innerhalb einer Stunde, im Tagesgeschäft. Jede Übergabe macht ein Mensch, der den Account vorher prüft — sofort ist das also nicht, und wir behaupten es auch nicht. Genau die automatische Auslieferung ist der Grund, warum Käufer auf Accounts landen, in die sich schon jemand eingeloggt hat.",
      "Should I buy an account or a boost?": "Account oder Boost — was soll ich kaufen?",
      "If you want to keep your own name, your skins and your match history, buy the boost — it is the same rank on the account you already play. An account makes sense when you want a second one to queue on, or a clean shard to start on. If you are choosing between them on price alone, the boost is usually the better purchase.":
        "Wenn du deinen Namen, deine Skins und deine Match-History behalten willst, nimm den Boost — das ist derselbe Rang auf dem Account, den du ohnehin spielst. Ein Account lohnt sich, wenn du einen zweiten zum Queuen willst oder einen sauberen Server für den Neustart. Wenn du nur nach dem Preis entscheidest, ist der Boost meistens der bessere Kauf.",
      "Can I play it from another country?": "Kann ich ihn aus einem anderen Land spielen?",
      "The shard is fixed — an EUW account stays on EUW — but nothing stops you playing it from anywhere. Riot does not sell shard transfers between the regions on this page, so pick the one your friends are on.":
        "Der Server steht fest — ein EUW-Account bleibt auf EUW — aber du kannst ihn von überall spielen. Riot verkauft zwischen den Servern auf dieser Seite keine Transfers, also nimm den, auf dem deine Freunde sind.",
      "Or climb on the account you already play.":
        "Oder steig auf dem Account auf, den du schon spielst.",
      "A boost keeps your name, your skins and your match history. If you are choosing between the two on price alone, that is usually the better purchase.":
        "Ein Boost behält deinen Namen, deine Skins und deine Match-History. Wenn du nur nach dem Preis entscheidest, ist das meistens der bessere Kauf.",
      "Configure a {} boost": "{}-Boost konfigurieren",
      "Or start on a second account.": "Oder starte auf einem zweiten Account.",
      "Ready-made {} accounts from": "Fertige {}-Accounts ab",
      "— level 30 and ranked, on NA, EUW, EUNE and OCE, with full email access and a":
        "— Level 30 und ranked, auf NA, EUW, EUNE und OCE, mit vollem E-Mail-Zugang und",
      "replacement. A boost is still the better buy if you want to keep your own name and skins.":
        "Ersatz. Ein Boost bleibt der bessere Kauf, wenn du deinen Namen und deine Skins behalten willst.",
      "Browse accounts": "Accounts ansehen",
      "Account": "Account",
      "Price": "Preis",
      "This is where the login, the password and the recovery mailbox are sent. Check it is one you can open — no marketing unless you tick the box at the end.":
        "Hierhin gehen Login, Passwort und Wiederherstellungs-Postfach. Prüf, dass du sie öffnen kannst — keine Werbung, außer du setzt das Häkchen am Ende.",
      "Anything we should know": "Etwas, das wir wissen sollten",
      "Replaced or refunded for {} days": "{} Tage lang Ersatz oder Erstattung",
      "Read the warranty": "Ersatzgarantie lesen",
      "Email me when the account is on its way. Nothing else.":
        "Mail mir, wenn der Account unterwegs ist. Sonst nichts.",
      /* The listing NAME, as a pattern: the rank it captures is data and passes
         through verbatim (a capture gets one exact dictionary lookup on the way
         out, which is what turns "Iron to Silver" into its own entry below).
         Only this page emits these, so the short literal is unambiguous. */
      "{} ranked": "{} ranked",
      "Level 30 · {} BE": "Level 30 · {} BE",
      "Iron to Silver": "Iron bis Silver",
    
      /* ── the accounts shop (/accounts.html) ───────────────────────────────────────────
         design_handoff_accounts_shop. Ranks, shard names, listing tiers and
         the reviewers' names are DATA and stay in English with every other
         rank on the site. The keys carrying a figure are written as `{}`
         patterns so a re-tuned warranty window or catalogue size cannot
         leave the sentence rendering in English — see CLAUDE.md. */
      "four": "vier",
      "eleven": "elf",
      "Buy League of Legends accounts": "League of Legends Accounts kaufen",
      "Ranked ready, full email access, no grind": "Ranked-ready, voller E-Mail-Zugang, kein Grind",
      "Original inbox included": "Original-Postfach inklusive",
      "{}-month replacement warranty": "{} Monate Austauschgarantie",
      "Step 1 of 2": "Schritt 1 von 2",
      "Step 2 of 2": "Schritt 2 von 2",
      "Which server do you play on?": "Auf welchem Server spielst du?",
      "Accounts are region-locked, so this is the one choice you cannot change after purchase. Pick the server you actually queue on.": "Accounts sind an ihre Region gebunden — das ist die eine Entscheidung, die du nach dem Kauf nicht mehr ändern kannst. Nimm den Server, auf dem du wirklich in die Queue gehst.",
      "Most stock": "Meiste Verfügbarkeit",
      "Low stock": "Wenig auf Lager",
      "in stock": "auf Lager",
      "Step 1 · server": "Schritt 1 · Server",
      "in stock on this server": "auf diesem Server auf Lager",
      "Change server": "Server wechseln",
      "Pick your account on": "Wähle deinen Account auf",
      "All tiers": "Alle Stufen",
      "Ranked": "Ranked",
      "Everything in stock": "Alles, was auf Lager ist",
      "Smurfs, placements unplayed": "Smurfs, Platzierungen ungespielt",
      "Iron to Master — previous season rewards included": "Iron bis Master — Belohnungen der letzten Season inklusive",
      "tiers": "Stufen",
      "Cheapest": "Am günstigsten",
      "Best seller": "Bestseller",
      "On offer": "Im Angebot",
      "Hand-levelled, never botted": "Von Hand geleveled, nie gebottet",
      "Placements not played": "Platzierungen ungespielt",
      "Previous season rewards": "Belohnungen der letzten Season",
      "in stock · {}": "auf Lager · {}",
      "left · verified in 12 h": "übrig · in 12 Std. geprüft",
      "Sold out on this server": "Auf diesem Server ausverkauft",
      "Buy now": "Jetzt kaufen",
      "Reserve": "Reservieren",
      "Prices and stock shown on": "Preise und Bestand gezeigt für",
      ". Pick a server above to see yours.": ". Wähle oben einen Server, um deine zu sehen.",
      "Handover": "Übergabe",
      "Every account ships with the original email inbox, not just the game login — which is the only version of this that is actually yours. Change the email and the password on arrival and nobody, including us, can recover it afterwards.": "Jeder Account kommt mit dem originalen E-Mail-Postfach, nicht nur mit dem Spiel-Login — und nur so gehört er wirklich dir. Ändere E-Mail und Passwort direkt nach Erhalt, dann kann ihn niemand mehr zurückholen, wir eingeschlossen.",
      "Minute 0": "Minute 0",
      "Pay for the account you picked": "Bezahle den Account, den du gewählt hast",
      "No account needed on our side. Card or wallet, and the price on the card is the price.": "Bei uns brauchst du kein Konto. Karte oder Wallet, und der Preis auf der Karte ist der Preis.",
      "Credentials arrive by email": "Die Zugangsdaten kommen per E-Mail",
      "Login, password, and the original inbox with its recovery details. Sent to the address you paid with.": "Login, Passwort und das originale Postfach mit seinen Wiederherstellungsdaten. An die Adresse, mit der du bezahlt hast.",
      "First 10 min": "Erste 10 Min.",
      "Change the email and the password": "Ändere E-Mail und Passwort",
      "Do this before your first game. A walkthrough is in the same email, and support will do it with you in Discord if you would rather.": "Mach das vor deiner ersten Runde. Die Anleitung liegt in derselben E-Mail, und der Support macht es auf Discord mit dir, wenn dir das lieber ist.",
      "Covered {} months": "{} Monate abgedeckt",
      "Play — and if it ever breaks, we replace it": "Spiel — und wenn es je kaputtgeht, ersetzen wir ihn",
      "Anything actioned inside the window is swapped for an account of the same rank, or refunded. One claim per account, no interrogation.": "Jeder Account, gegen den innerhalb des Zeitraums vorgegangen wird, wird gegen einen gleichrangigen getauscht oder erstattet. Ein Fall pro Account, ohne Verhör.",
      "What lands in your inbox": "Was in deinem Postfach landet",
      "The game login": "Der Spiel-Login",
      "Username and password, tested minutes before it is sent.": "Benutzername und Passwort, Minuten vor dem Versand getestet.",
      "The original email inbox": "Das originale E-Mail-Postfach",
      "Address, password and recovery answers — this is what makes it yours.": "Adresse, Passwort und Wiederherstellungsantworten — genau das macht ihn zu deinem.",
      "A change-it-now walkthrough": "Eine Anleitung zum sofortigen Ändern",
      "Four steps to lock the account to you, with screenshots.": "Vier Schritte, um den Account auf dich festzulegen, mit Screenshots.",
      "The full account sheet": "Das vollständige Account-Datenblatt",
      "Champions, skins, essence, honour level and match history at handover.": "Champions, Skins, Essenz, Ehrenstufe und Match-History zum Zeitpunkt der Übergabe.",
      "A {}-month warranty note": "Ein Garantieschein über {} Monate",
      "Your order id is the claim — nothing to register.": "Deine Bestellnummer ist der Garantiefall — nichts zu registrieren.",
      "Riot licenses an account to one person and does not permit it to be sold or transferred. Changing the email and the password on arrival is what makes a ban unlikely rather than impossible, and it is why we hand over the inbox instead of only the login. We replace anything actioned inside the warranty window — but we will not tell you the risk is zero, because it isn't.": "Riot lizenziert einen Account an eine einzige Person und erlaubt weder Verkauf noch Übertragung. Dass Sie E-Mail und Passwort direkt nach Erhalt ändern, macht eine Sperre unwahrscheinlich, nicht unmöglich — und genau deshalb übergeben wir das Postfach und nicht nur den Login. Wir ersetzen jeden Account, gegen den innerhalb der Garantiezeit vorgegangen wird — aber wir werden Ihnen nicht sagen, das Risiko sei null, denn das ist es nicht.",
      "Why ours": "Warum unsere",
      "Hand-levelled, never botted.": "Von Hand geleveled, nie gebottet.",
      "Three things decide whether a bought account is worth having: who played it, whether you can lock it to yourself, and what happens if it goes wrong.": "Drei Dinge entscheiden, ob ein gekaufter Account etwas taugt: wer ihn gespielt hat, ob du ihn auf dich festlegen kannst, und was passiert, wenn es schiefgeht.",
      "Provenance": "Herkunft",
      "Played by a person": "Von einem Menschen gespielt",
      "Every account was levelled by a booster on our roster, in normal hours, on a regional connection. The match history reads like a player because it was one.": "Jeder Account wurde von einem Booster aus unserem Kader geleveled, zu normalen Zeiten, über eine Verbindung aus der Region. Die Match-History liest sich wie die eines Spielers, weil es einer war.",
      "No scripts, no bots, ever": "Keine Skripte, keine Bots, nie",
      "Ownership": "Eigentum",
      "The inbox comes with it": "Das Postfach kommt mit",
      "A login without its email is a rental — the seller can pull it back whenever they like. Ours ship with the original inbox and its recovery details.": "Ein Login ohne seine E-Mail ist eine Miete — der Verkäufer kann ihn jederzeit zurückholen. Unsere kommen mit dem originalen Postfach und seinen Wiederherstellungsdaten.",
      "Yours to lock in 10 minutes": "In 10 Minuten auf dich festgelegt",
      "Warranty": "Garantie",
      "Replaced for a year": "Ein Jahr lang ersetzt",
      "If the account is actioned within {} months we send an equivalent one. One claim per account, no interrogation, no restocking fee.": "Wird innerhalb von {} Monaten gegen den Account vorgegangen, schicken wir einen gleichwertigen. Ein Fall pro Account, ohne Verhör und ohne Wiedereinlagerungsgebühr.",
      "{} claims honoured last year": "{} Garantiefälle im letzten Jahr eingelöst",
      "Buyers": "Käufer",
      "From accounts sold this month.": "Von Accounts, die diesen Monat verkauft wurden.",
      "4 days ago": "vor 4 Tagen",
      "1 week ago": "vor 1 Woche",
      "2 weeks ago": "vor 2 Wochen",
      "Email came with it, changed both in about five minutes with the guide. Match history looks like a real account, which is the bit I was worried about.": "Die E-Mail war dabei, beides in etwa fünf Minuten mit der Anleitung geändert. Die Match-History sieht aus wie ein echter Account, und genau davor hatte ich Bammel.",
      "Expensive, and worth it — the honour level and season rewards were exactly as listed. Support walked me through the email change on Discord.": "Teuer, und es wert — Ehrenstufe und Season-Belohnungen waren exakt wie angegeben. Der Support hat mich auf Discord durch den E-Mail-Wechsel geführt.",
      "Every review here is tied to a paid order id. We do not solicit them and we do not filter by score —": "Jede Bewertung hier hängt an einer bezahlten Bestellnummer. Wir fordern keine an und wir filtern nicht nach Note —",
      "read every review": "alle Bewertungen lesen",
      "Before you buy an account.": "Bevor du einen Account kaufst.",
      "Three of these argue against the sale. They are the reason the other five are worth reading.": "Drei dieser Antworten sprechen gegen den Verkauf. Genau deshalb lohnen sich die anderen fünf.",
      "Do I get the email as well as the login?": "Bekomme ich die E-Mail zusätzlich zum Login?",
      "Yes, on every account. You receive the game login and the original inbox with its password and recovery details, which is the difference between owning an account and renting one. Change both on arrival and nobody — including us — can take it back. We do not sell accounts we cannot hand over completely.": "Ja, bei jedem Account. Sie erhalten den Spiel-Login und das originale Postfach mit Passwort und Wiederherstellungsdaten — das ist der Unterschied zwischen einem Account besitzen und ihn mieten. Ändern Sie beides direkt nach Erhalt, dann kann ihn niemand zurückholen, wir eingeschlossen. Wir verkaufen keine Accounts, die wir nicht vollständig übergeben können.",
      "Can the account be banned for this?": "Kann der Account dafür gesperrt werden?",
      "Buying an account is against Riot's terms of service, so the honest answer is that the risk is not zero. What reduces it is provenance and hygiene: every account was hand-levelled by a person rather than botted, and changing the email and password in the first ten minutes removes the only trail back to the sale. Anything actioned within {} months is replaced free.": "Einen Account zu kaufen verstößt gegen Riots Nutzungsbedingungen, die ehrliche Antwort ist also: das Risiko ist nicht null. Was es senkt, sind Herkunft und Hygiene — jeder Account wurde von einem Menschen von Hand geleveled statt gebottet, und E-Mail und Passwort in den ersten zehn Minuten zu ändern löscht die einzige Spur zurück zum Verkauf. Wird innerhalb von {} Monaten gegen den Account vorgegangen, ersetzen wir ihn kostenlos.",
      "What happens if it is recovered or banned?": "Was passiert, wenn er zurückgeholt oder gesperrt wird?",
      "Inside {} months of delivery you get another account of the same rank, or the money back, your choice. One claim per account, no interrogation and no restocking fee. The claim is your order id — there is nothing to register.": "Innerhalb von {} Monaten nach Lieferung bekommen Sie einen anderen Account desselben Rangs oder Ihr Geld zurück, ganz wie Sie wollen. Ein Fall pro Account, ohne Verhör und ohne Wiedereinlagerungsgebühr. Der Garantiefall ist Ihre Bestellnummer — es gibt nichts zu registrieren.",
      "Why is a Diamond account so much more than a smurf?": "Warum kostet ein Diamond-Account so viel mehr als ein Smurf?",
      "A level 30 unranked takes a booster a couple of days. A Diamond account is weeks of ranked games at a rank where losses are expensive, plus the skins and rewards that accumulate on the way. The price tracks the hours behind the account, not the label on it.": "Ein Level-30-Unranked kostet einen Booster ein paar Tage. Ein Diamond-Account sind Wochen an Ranked-Spielen auf einem Rang, auf dem Niederlagen teuer sind, dazu die Skins und Belohnungen, die sich unterwegs ansammeln. Der Preis folgt den Stunden hinter dem Account, nicht dem Etikett darauf.",
      "No. A listing names a tier and you get what is in stock the day you order, inside it. We do not know which division it will be when you buy, so we do not print one we might not have — everything else on the card is exact.": "Nein. Ein Angebot nennt eine Stufe, und Sie bekommen, was am Bestelltag innerhalb dieser Stufe auf Lager ist. Wir wissen beim Kauf nicht, welche Division es sein wird, also drucken wir keine ab, die wir vielleicht nicht haben — alles andere auf der Karte ist exakt.",
      "Can I change server after buying?": "Kann ich den Server nach dem Kauf wechseln?",
      "No — and it is why the server is the first thing we ask. Riot does sell a transfer service, but we do not offer transfers and an account's rank history does not follow it cleanly. Pick the region you actually queue on.": "Nein — und genau deshalb fragen wir den Server zuerst. Riot verkauft zwar einen Transferdienst, aber wir bieten keine Transfers an, und die Ranglisten-History eines Accounts folgt ihm nicht sauber. Wählen Sie die Region, auf der Sie tatsächlich spielen.",
      "Can I get a refund if I change my mind?": "Bekomme ich mein Geld zurück, wenn ich es mir anders überlege?",
      "Before the credentials are sent, yes — in full, no questions. Once they have been sent we cannot refund, because you have had access to the account and we cannot un-know the password. That is the trade for delivery in minutes, and it is why the listing shows every stat before you buy.": "Bevor die Zugangsdaten raus sind: ja, vollständig und ohne Rückfragen. Sind sie einmal versendet, können wir nicht erstatten — Sie hatten Zugriff auf den Account, und ein Passwort lässt sich nicht wieder vergessen. Das ist der Preis für eine Lieferung in Minuten, und deshalb zeigt das Angebot jeden Wert schon vor dem Kauf.",
      "Full email access, or it's not an account.": "Voller E-Mail-Zugang, sonst ist es kein Account.",
      "{} tiers on {} servers, from": "{} Stufen auf {} Servern, ab",
      "Eleven": "Elf",
      "Pick your server": "Wähle deinen Server",
      "Or boost the account you already play": "Oder booste den Account, den du schon spielst",
      "Instant Delivery": "Sofortlieferung",

      "{}, from paying to playing.": "{}, von der Zahlung bis zur ersten Runde.",
      ", every time": ", jedes Mal",
      ", replaced for {} months if it ever breaks.": ", {} Monate lang ersetzt, falls je etwas kaputtgeht.",

      "instant delivery": "Sofortlieferung",

      "Low MMR": "Niedriger MMR",
      "Standard MMR": "Normaler MMR",
      "High MMR": "Hoher MMR",
      "Ordered at 2am and the credentials were in my inbox before I closed the tab. Bigger champion pool than the account I main on.": "Um 2 Uhr nachts bestellt, die Zugangsdaten waren im Postfach, bevor ich den Tab zugemacht habe. Größerer Champion-Pool als auf meinem Main.",

      "Random BE/Skins": "Zufällige BE/Skins",

      "{}+ champions": "{}+ Champions",

    }
  };

  /* union of all keys — marks a string as translatable on first encounter */
  var ANYDICT = {};
  ["fr", "de"].forEach(function (l) { for (var k in ESB_I18N[l]) ANYDICT[k] = 1; });

  /* ── {} patterns ──────────────────────────────────────────────────────────
     A key may carry `{}` placeholders. "It goes on the board and a verified {}
     booster takes it." is ONE entry covering all nine ladders, where the
     whole-text-node rule otherwise needs nine near-identical ones — and the
     count grows with the catalogue, which is how a tenth game ships half
     translated. It is not the interpolation the rest of this file warns about:
     the placeholder MOVES with the target's word order ("Demandé avant chaque
     commande {}"), which is exactly what splitting a sentence into fragments
     around a `<b>` cannot do.

     Three properties keep it safe. Only keys written with `{}` take part; they
     are tried only after an exact lookup misses, so no existing entry changes
     behaviour; and what a `{}` captures is copied through verbatim, because it
     is always data — a game name, a tier, a publisher, a figure. Keep the
     literal part of a pattern long enough to be unambiguous: `{}` is
     non-greedy but it will still match anything. */
  var _pats = {};
  function patterns(lang) {
    if (_pats[lang]) return _pats[lang];
    var out = [], d = ESB_I18N[lang] || {};
    for (var k in d) {
      if (k.indexOf("{}") === -1) continue;
      var rx = k.split("{}").map(function (part) {
        return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }).join("([^]+?)");
      out.push({ re: new RegExp("^" + rx + "$"), to: d[k] });
    }
    return (_pats[lang] = out);
  }

  function patTranslate(core, lang) {
    var ps = patterns(lang), d = ESB_I18N[lang] || {};
    for (var i = 0; i < ps.length; i++) {
      var m = core.match(ps[i].re);
      if (!m) continue;
      var j = 1;
      return ps[i].to.replace(/\{\}/g, function () {
        var cap = m[j++] || "";
        // A capture is normally data and passes through untouched — no game
        // name, tier or publisher is a dictionary key. The exception is the
        // roster sentence, which spells its own count ("Thirty-one of them"):
        // that IS a word, so a capture gets one exact lookup on the way out.
        return d[cap] !== undefined ? d[cap] : cap;
      });
    }
    return null;
  }

  // The pattern half of ANYDICT: is this node translatable in ANY language?
  // Asked once per node before the original is stashed, so a node that only
  // matches a pattern is still restored to English on the way back.
  var ANYPATS = null;
  function anyPatMatch(core) {
    if (!ANYPATS) {
      ANYPATS = [];
      ["fr", "de"].forEach(function (l) {
        patterns(l).forEach(function (p) { ANYPATS.push(p.re); });
      });
    }
    for (var i = 0; i < ANYPATS.length; i++) if (ANYPATS[i].test(core)) return true;
    return false;
  }

  /* ── DOM translation ──────────────────────────────────────────────────── */
  var ORIG = new WeakMap();      // text node → original English nodeValue
  var ATTR_ORIG = new WeakMap(); // element → { attr: original English value }
  // Skip JS-managed and value-bearing nodes. [data-sel] selects hold rank/region
  // codes rebuilt by app.js — never translate those; other static <option>s
  // (e.g. preferred hours) are fine to translate.
  var SKIP = "[data-out],[data-sum],[data-r],[data-order-id],[data-state-kicker]," +
    "[data-state-title],[data-state-body],[data-ladder],[data-subseg],[data-stepper]," +
    "[data-demo-note],[data-demo-label],[data-demo-addr],[data-demo-pause-label]," +
    "[data-demo-status-label]," +
    "[data-apply-note],[data-contact-note],[data-pay-error]," +
    // guides landing — strings the form rewrites at runtime through esbT()
    "[data-gd-cta],[data-gd-pick],[data-gd-note],[data-gd-ctanote]," +
    "[data-gd-sentline],[data-gd-email-out]," +
    // mystery discount — the card letter, the issued code, the money figures,
    // the countdown and the note the flow rewrites through esbT()
    "[data-myd-pick],[data-myd-code],[data-myd-was],[data-myd-now]," +
    "[data-myd-save],[data-myd-full],[data-myd-timer],[data-myd-note]," +
    ".money,.nav-brand,.locale,[data-sel],script,style,code,textarea,output";
  var ATTRS = ["placeholder", "aria-label", "title", "alt"];

  function norm(s) { return s.replace(/\s+/g, " ").trim(); }

  function translateTextNode(node, lang) {
    var orig = ORIG.get(node);
    var full = orig !== undefined ? orig : node.nodeValue;
    var m = full.match(/^(\s*)([\s\S]*?)(\s*)$/);
    var lead = m[1], coreRaw = m[2], trail = m[3];
    if (!coreRaw) return;
    var core = norm(coreRaw);
    var known = orig !== undefined || ANYDICT[core] === 1 || anyPatMatch(core);
    if (!known) return;
    if (orig === undefined) ORIG.set(node, full);
    var out = coreRaw;
    if (lang !== "en") {
      var d = ESB_I18N[lang], pat;
      if (d && d[core] !== undefined) out = d[core];
      else if ((pat = patTranslate(core, lang)) !== null) out = pat;
    }
    node.nodeValue = lead + out + trail;
  }

  function translateAttrs(el, lang) {
    var store = ATTR_ORIG.get(el);
    ATTRS.forEach(function (a) {
      if (!(store && a in store) && !el.hasAttribute(a)) return;
      var origVal = store && a in store ? store[a] : el.getAttribute(a);
      var core = norm(origVal || "");
      if (!core) return;
      if (!(store && a in store) && ANYDICT[core] !== 1 && !anyPatMatch(core)) return;
      if (!store) { store = {}; ATTR_ORIG.set(el, store); }
      if (!(a in store)) store[a] = origVal;
      var out = origVal;
      if (lang !== "en") {
        var d = ESB_I18N[lang], pat;
        // Attributes take the {} patterns too, for the same reason text nodes
        // do: the promo chip's accessible name is built from the live code and
        // percentage ("Copy discount code SPLIT15 — 15% off"), so a fixed key
        // would go stale the first time the sale changes — and that label is
        // the ONLY place a screen reader hears the discount.
        if (d && d[core] !== undefined) out = d[core];
        else if ((pat = patTranslate(core, lang)) !== null) out = pat;
      }
      el.setAttribute(a, out);
    });
  }

  function applyLang(lang, pinned) {
    locale.lang = lang;
    // Only a click pins. Applying the stored or geo-resolved language at boot
    // must not, or a default could never be moved by a later visit from
    // somewhere else — the same rule applyCurrency() follows.
    if (pinned) locale.langPinned = true;
    document.documentElement.setAttribute("lang", lang);
    // The language carries its currency with it until the visitor pins one, so
    // switching to French re-quotes the whole page in euros. Set before the walk
    // so the single reformatStaticMoney() / esbRender() pass at the foot of this
    // function does both jobs at once, and syncAll() re-marks the currency
    // control that just moved underneath the reader.
    if (!locale.curPinned) locale.currency = defaultCurrency(lang);
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        var p = n.parentElement;
        if (p && p.closest(SKIP)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (t) { translateTextNode(t, lang); });

    ATTRS_SEL.forEach(function (el) { translateAttrs(el, lang); });

    // EUR symbol placement is language-specific — re-format static prices too
    reformatStaticMoney();
    // let the runtime re-render its dynamic strings in the new language
    if (window.esbRender) window.esbRender();
    syncAll();
  }

  var ATTRS_SEL = [];
  function collectAttrEls() {
    ATTRS_SEL = Array.prototype.slice.call(
      document.querySelectorAll("[placeholder],[aria-label],[title],[alt]")
    ).filter(function (el) { return !el.closest("script,style"); });
  }

  /* ── currency application ─────────────────────────────────────────────── */
  // Re-format static server-rendered prices. EUR symbol placement depends on
  // language, so this runs on both currency and language changes.
  function reformatStaticMoney() {
    Array.prototype.forEach.call(document.querySelectorAll(".money[data-usd]"), function (el) {
      var n = parseFloat(el.getAttribute("data-usd"));
      if (isNaN(n)) return;
      /* ⚠ A `data-<code>` row wins over the rate. The accounts price is a table
         with one hand-set figure per market (see data.py), so switching
         currency there is a LOOKUP, not a conversion — while every boosting
         price on the same page still converts from data-usd. A row is used
         as-is, which is what `fixed` means below. */
      var own = el.getAttribute("data-" + locale.currency.toLowerCase());
      var fixedRow = own !== null && own !== "" && !isNaN(parseFloat(own));
      if (fixedRow) n = parseFloat(own);
      // A two-size price is re-split rather than flattened: writing textContent
      // over it would destroy the two spans and print the whole figure at the
      // small size. See esbMoneyParts().
      var fixed = fixedRow || el.hasAttribute("data-fixed");
      var main = el.querySelector("[data-money-main]");
      if (main) {
        var parts = window.esbMoneyParts(n, fixed);
        main.textContent = parts.main;
        var c = el.querySelector("[data-money-cents]");
        if (c) c.textContent = parts.cents;
        return;
      }
      // `data-cents` is the price's own flag, not the caller's: accounts are
      // the one product quoted to the cent, and a $14.99 card that re-formatted
      // to "€14" on a currency switch would quote a price nothing charges.
      el.textContent = window.esbMoney(n, el.hasAttribute("data-cents"), fixed);
    });
  }

  /* The same money, split for a two-size price — "$74" big, ".99" small.
     Done through formatToParts rather than by slicing the finished string,
     because where the mark and the separator sit is the formatter's business:
     en-US gives "$74.99", fr-FR "74,99 €". `main` is everything up to the
     decimal separator (symbol included wherever it falls) and `cents` is the
     separator plus the fraction plus anything after it, so main + cents is
     always exactly esbMoney(n, true). */
  window.esbMoneyParts = function (n, fixed) {
    var cur = locale.currency, rate = fixed ? 1 : (window.ESB_RATES[cur] || 1);
    var f = formatter(cur, locale.lang, true), mark = CUR_MARK[cur];
    var parts;
    try { parts = f.formatToParts(n * rate); }
    catch (e) { return { main: window.esbMoney(n, true, fixed), cents: "" }; }
    var main = "", cents = "", seen = false;
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      var v = (p.type === "currency" && mark) ? mark : p.value;
      if (p.type === "decimal") seen = true;
      if (seen) cents += v; else main += v;
    }
    return { main: main, cents: cents };
  };

  function applyCurrency(cur, pinned) {
    locale.currency = cur;
    // Only a click pins. Restoring a stored preference at boot must not, or the
    // language default could never move a currency it set itself.
    if (pinned) locale.curPinned = true;
    reformatStaticMoney();
    if (window.esbRender) window.esbRender();
  }

  function persist() {
    try { localStorage.setItem(LKEY, JSON.stringify(locale)); } catch (e) {}
  }

  /* ── flag dropdowns ───────────────────────────────────────────────────── */
  var OPEN = null;
  function closeMenus() {
    if (OPEN) {
      OPEN.setAttribute("data-open", "false");
      OPEN.querySelector(".loc-btn").setAttribute("aria-expanded", "false");
      OPEN = null;
    }
  }
  function openMenu(loc) {
    if (OPEN && OPEN !== loc) closeMenus();
    loc.setAttribute("data-open", "true");
    loc.querySelector(".loc-btn").setAttribute("aria-expanded", "true");
    OPEN = loc;
  }

  function syncDropdown(loc, kind) {
    var value = kind === "language" ? locale.lang.toUpperCase() : locale.currency;
    loc.querySelectorAll(".loc-opt").forEach(function (opt) {
      var on = opt.getAttribute("data-value") === value;
      opt.setAttribute("aria-selected", on ? "true" : "false");
      if (on) {
        // The language button wears a fixed translate glyph instead of the
        // selected flag, so it has no [data-loc-icon] to mirror into.
        var icon = loc.querySelector("[data-loc-icon]");
        if (icon) icon.textContent = opt.querySelector(".loc-flag").textContent;
        loc.querySelector("[data-loc-label]").textContent = opt.querySelector(".loc-code").textContent;
      }
    });
  }

  // Every .loc on the page. Three switchers mount per document — the promo bar,
  // the nav sheet and the footer — and a language pick now moves the currency
  // too, so re-marking only the control that was clicked leaves the other five
  // contradicting the prices beside them.
  function syncAll() {
    document.querySelectorAll(".loc").forEach(function (loc) {
      syncDropdown(loc, loc.getAttribute("data-loc"));
    });
  }

  function wireDropdown(loc) {
    var kind = loc.getAttribute("data-loc");
    var btn = loc.querySelector(".loc-btn");
    syncDropdown(loc, kind);

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (loc.getAttribute("data-open") === "true") closeMenus();
      else openMenu(loc);
    });

    loc.querySelectorAll(".loc-opt").forEach(function (opt) {
      var pick = function () {
        var val = opt.getAttribute("data-value");
        if (kind === "language") applyLang(val.toLowerCase(), true);
        else applyCurrency(val, true);
        persist();
        syncAll();
        closeMenus();
        btn.focus();
      };
      opt.addEventListener("click", function (e) { e.stopPropagation(); pick(); });
      opt.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
      });
    });

    // arrow / escape navigation within the open menu
    loc.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeMenus(); btn.focus(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      if (loc.getAttribute("data-open") !== "true") { openMenu(loc); }
      var opts = Array.prototype.slice.call(loc.querySelectorAll(".loc-opt"));
      var i = opts.indexOf(document.activeElement);
      var n = e.key === "ArrowDown" ? (i + 1) % opts.length : (i - 1 + opts.length) % opts.length;
      opts[n < 0 ? 0 : n].focus();
    });
  }

  /* ── wiring ───────────────────────────────────────────────────────────── */
  function init() {
    collectAttrEls();

    document.querySelectorAll(".loc").forEach(wireDropdown);
    document.addEventListener("click", closeMenus);

    // apply stored preferences (currency first so esbRender picks up both).
    // Both were already resolved at parse time — against the visitor's own pick
    // if they have one, else against where they are — so a visitor in France
    // with no pick of their own arrives on French and euros here.
    if (locale.currency !== "USD") applyCurrency(locale.currency);
    if (locale.lang !== "en") applyLang(locale.lang);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
