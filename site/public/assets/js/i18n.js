/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — client-side currency + language switcher
   ---------------------------------------------------------------------------
   Loaded BEFORE app.js so window.esbMoney / window.ESB_LOCALE exist when the
   runtime takes its first quote. Two independent dimensions, both persisted:

     currency : USD | EUR | GBP | CAD  (both display AND the Stripe charge — the
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

  /* ── the currencies, and the rate each is charged at ──────────────────────
     Fixed FX rate for both the displayed price AND the Stripe charge. The amount
     is recomputed server-side (pricing.py) in USD, then converted to the picked
     currency at THIS rate for the charge — pricing.CHARGE_RATES mirrors this map
     and test_pricing.py asserts they hold the same currencies at the same rates,
     so change one, change the other, or the Stripe page won't match the button.
     It doubles as the allowlist: a currency we have no rate for is one we cannot
     charge, so a stored or hand-typed code that isn't a key here is discarded. */
  var RATES = window.ESB_RATES = { USD: 1, EUR: 0.92, GBP: 0.79, CAD: 1.37 };

  /* ── persisted locale, read synchronously so app.js sees it ───────────── */
  var locale = { lang: "en", currency: "USD", curPinned: false };
  try {
    var raw = localStorage.getItem(LKEY);
    if (raw) {
      var s = JSON.parse(raw);
      if (s && (s.lang === "en" || s.lang === "fr" || s.lang === "de")) locale.lang = s.lang;
      if (s && RATES[s.currency]) locale.currency = s.currency;
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
  // Resolved here, not in init(), because app.js reads ESB_LOCALE.currency on
  // its first quote — deriving it later would paint the page in $ and swap it.
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
  var CUR_TAG = { USD: "en-US", GBP: "en-GB", CAD: "en-US" };
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
  var CUR_MARK = { CAD: "C$" };
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
  window.esbMoney = function (n, cents) {
    var cur = locale.currency, rate = window.ESB_RATES[cur] || 1;
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
      "Duo queue": "File duo",
      "net win": "victoire nette",
      "net wins": "victoires nettes",
      "placement game": "match de placement",
      "placement games": "matchs de placement",
      "about 1 day": "environ 1 jour",
      "days": "jours",
      "Target must sit above your current rank": "La cible doit être au-dessus de votre rang actuel",
      "Pick a target above your current rank": "Choisissez une cible au-dessus de votre rang actuel",
      "YOU": "VOUS",
      "TARGET": "CIBLE",
      "YOU · TGT": "VOUS · CIBLE",
      "Tap the rank you’re on now": "Touchez le rang où vous êtes",
      "Now tap the rank you want to reach": "Touchez le rang que vous visez",
      "No divisions": "Aucune division",
      "None": "Aucune",

      /* site header — design_handoff_site_header */
      "Currency": "Devise",
      "Language": "Langue",
      "Summer sale": "Soldes d'été",
      "ends 31 Aug": "jusqu'au 31 août",
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
      "Pick your game": "Choisissez votre jeu",
      "Who plays your order": "Qui joue votre commande",
      "Before you buy": "Avant d'acheter",
      "Right now": "En ce moment",
      "Top": "N° 1",
      "Hiring": "Recrute",
      "are live too": "sont aussi en ligne",
      "boosters on shift": "boosters en service",
      "Median claim": "Prise en charge médiane",
      "Watch orders land live": "Voir les commandes arriver en direct",
      "All nine games": "Les neuf jeux",
      "Browse the roster": "Parcourir l'équipe",
      "verified boosters, one game each": "boosters vérifiés, un jeu chacun",
      "Hire a specific booster": "Choisir un booster précis",
      "Name one at checkout, no extra fee": "Nommez-le au paiement, sans supplément",
      "How we verify": "Comment nous vérifions",
      "Rank proof, trial orders, review floor": "Preuve de rang, commandes d'essai, note plancher",
      "Master+ with a clean account": "Master+ avec un compte sans historique",
      "Read their reviews": "Lire leurs avis",
      "reviews, filterable by game and score": "avis, filtrables par jeu et par note",
      "The guarantee": "La garantie",
      "Refunded until a booster claims it": "Remboursé tant qu'aucun booster n'a pris la commande",
      "Account safety": "Sécurité du compte",
      "Regional VPN, your hours, offline": "VPN régional, vos horaires, hors ligne",
      "What we never do": "Ce que nous ne faisons jamais",
      "No bots, no password changes": "Pas de bots, aucun changement de mot de passe",
      "Pro-rated, in five business days": "Au prorata, sous cinq jours ouvrés",
      "FAQ": "FAQ",
      "The six questions support gets most": "Les six questions les plus posées au support",
      "Track an order": "Suivre une commande",
      "No password — the link is the login": "Sans mot de passe — le lien est la connexion",
      /* auth panel */
      "Create account": "Créer un compte",
      "Create your account": "Créez votre compte",
      "An account is optional. It keeps every order, thread and saved configuration in one place — you can still buy as a guest.":
        "Le compte est facultatif. Il rassemble vos commandes, vos échanges et vos configurations enregistrées au même endroit — vous pouvez tout de même acheter en tant qu'invité.",
      "Bought as a guest? You don't need an account. Use the link we emailed you, or resend it from the order tracker.":
        "Vous avez acheté en tant qu'invité ? Aucun compte n'est nécessaire. Utilisez le lien reçu par e-mail, ou renvoyez-le depuis le suivi de commande.",
      "Continue with Discord": "Continuer avec Discord",
      "Continue with Google": "Continuer avec Google",
      "Sign up with Discord": "S'inscrire avec Discord",
      "Sign up with Google": "S'inscrire avec Google",
      "or with email": "ou par e-mail",
      "Display name": "Nom affiché",
      "What your booster calls you": "Le nom que votre booster utilisera",
      "Password": "Mot de passe",
      "Your password": "Votre mot de passe",
      "At least 6 characters": "Au moins 6 caractères",
      "Forgot it?": "Oublié ?",
      "Show password": "Afficher le mot de passe",
      "Hide password": "Masquer le mot de passe",
      "Six characters or more. A passphrase beats a symbol soup.":
        "Six caractères ou plus. Une phrase de passe vaut mieux qu'une soupe de symboles.",
      "Too short to be worth having.": "Trop court pour servir à quelque chose.",
      "Getting there — add a few more words.": "On y arrive — ajoutez quelques mots.",
      "Strong enough.": "Assez solide.",
      "I've read the": "J'ai lu les",
      "terms": "conditions",
      "privacy policy": "politique de confidentialité",
      "and the": "et la",
      ", including how boosting relates to each game's rules.":
        ", y compris ce que le boosting implique au regard des règles de chaque jeu.",
      "We'll keep you signed in on this device for 30 days.":
        "Vous resterez connecté sur cet appareil pendant 30 jours.",
      "That email and password don't match. Check the address, or reset the password.":
        "Cet e-mail et ce mot de passe ne correspondent pas. Vérifiez l'adresse, ou réinitialisez le mot de passe.",
      "An account with this email already exists. Log in instead.": "Un compte avec cet e-mail existe déjà. Connectez-vous plutôt.",
      "Enter a valid email address.": "Saisissez une adresse e-mail valide.",
      "Choose a password of at least 6 characters.": "Choisissez un mot de passe d'au moins 6 caractères.",
      "Please accept the terms to create your account.": "Veuillez accepter les conditions pour créer votre compte.",
      "Enter your password.": "Saisissez votre mot de passe.",
      "Couldn't reach the server. Check your connection and try again.": "Impossible de joindre le serveur. Vérifiez votre connexion et réessayez.",
      "Couldn't create the account. Try again.": "Impossible de créer le compte. Réessayez.",
      "Sign-in didn't complete. Please try again.": "La connexion n'a pas abouti. Veuillez réessayer.",
      "That email and password don't match. Check them, or create an account.": "Cet e-mail et ce mot de passe ne correspondent pas. Vérifiez-les, ou créez un compte.",
      "Social sign-in isn't connected yet. Use your email, or buy as a guest — checkout needs no account.":
        "La connexion via un réseau n'est pas encore active. Utilisez votre e-mail, ou achetez en invité — le paiement ne demande aucun compte.",
      "This is your store account, never your game login.":
        "C'est votre compte boutique, jamais votre identifiant de jeu.",
      "We never ask for your game password here.":
        "Nous ne demandons jamais votre mot de passe de jeu ici.",
      "New here?": "Nouveau ici ?",
      "Already have an account?": "Vous avez déjà un compte ?",
      "Create an account": "Créer un compte",
      /* account menu */
      "My orders": "Mes commandes",
      "Messages": "Messages",
      "Log out": "Se déconnecter",
      "live": "en cours",
      "Account": "Compte",
      "Your orders": "Vos commandes",
      "Every boost you've ordered \u2014 the one in progress, and the ones already delivered.": "Chaque boost que vous avez commandé — celui en cours et ceux déjà livrés.",
      "Signed in as": "Connecté en tant que",
      "You're viewing a sample history.": "Vous consultez un historique d\u2019exemple.",
      "to keep your orders in one place \u2014 or track a single order by the link we emailed you. Checkout never needs an account.": "pour garder vos commandes au même endroit — ou suivez une commande via le lien reçu par e-mail. Le paiement ne demande jamais de compte.",
      "This order history is a preview. Until an account backend is live, the orders shown are example data, priced with the real quote \u2014 the same standing as the demo dashboard.": "Cet historique de commandes est un aperçu. Tant qu'un backend de comptes n'est pas actif, les commandes affichées sont des données d'exemple, tarifées avec le vrai devis — au même titre que le tableau de bord de démo.",
      "Track by link": "Suivre via le lien",
      "Orders": "Commandes",
      "Lifetime spent": "Total dépensé",
      "Open dashboard": "Ouvrir le tableau de bord",
      "Status": "Statut",
      "now": "actuel",

      /* footer */
      "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any of their subsidiaries. All trademarks, game titles, logos, and brand names are the property of their respective owners. eSports Boost provides independent gaming services and is not endorsed by or associated with any game publisher.":
        "Nous ne sommes affiliés ni à Riot Games, Inc., ni à Blizzard Entertainment, ni à Valve, ni à aucune de leurs filiales. Toutes les marques, titres de jeux, logos et noms de marque appartiennent à leurs propriétaires respectifs. eSports Boost fournit des services de jeu indépendants et n'est ni approuvé ni associé à un quelconque éditeur de jeux.",
      "Questions? Email us at": "Des questions ? Écrivez-nous à",
      "Follow along": "Suivez-nous",
      "games": "jeux",
      "Help center": "Centre d'aide",
      "Legal": "Mentions légales",
      "24/7 Customer Support": "Support client 24/7",
      "Online now": "En ligne",
      "Online Now": "En ligne",
      "Verified Boosters": "boosters vérifiés",
      "Typical reply": "Réponse habituelle en",
      "Need help? Our support team is available anytime to assist you with your orders and questions.":
        "Besoin d'aide ? Notre équipe de support est disponible à tout moment pour vos commandes et vos questions.",
      "Let's chat": "Discutons",
      "Visit help center": "Centre d'aide",
      "Privacy Policy": "Politique de confidentialité",
      "Terms of Service": "Conditions d'utilisation",
      "Refunds & Cancellations": "Remboursements et annulations",
      "Become a booster": "Devenir booster",
      "Discord": "Discord",
      "Card, Apple Pay and Google Pay accepted — payments secured by Stripe":
        "Carte, Apple Pay et Google Pay acceptés — paiements sécurisés par Stripe",
      "© 2026 eSports Boost. All Rights Reserved.": "© 2026 eSports Boost. Tous droits réservés.",

      /* calculator / wizard */
      "Fast Checkout": "Paiement rapide",
      "Live pricing": "Prix en direct",
      "Choose a game": "Choisissez un jeu",
      "Your climb": "Votre montée",
      "Rank tier": "Palier de rang",
      "Current division": "Division actuelle",
      "Target division": "Division cible",
      "How it's played": "Mode de jeu",
      /* order card — the "Ladder card" hero on the game pages */
      "Build your boost": "Composez votre boost",
      "of": "sur",
      "boosters free now": "boosters libres",
      "Add-ons": "Options",
      "to climb": "à gravir",
      "division": "division",
      "divisions": "divisions",
      "Cheapest single division": "Division la moins chère",
      "You save": "Vous économisez",
      "Save": "Économie",
      "with": "avec",
      "Money-back until a booster is assigned": "Remboursé tant qu'aucun booster n'est assigné",
      "Money back until a booster claims it": "Remboursé tant qu'aucun booster n'a pris la commande",
      "Your hours, offline the whole time": "À vos horaires, hors ligne du début à la fin",
      "Pause any time — it's your account": "Mettez en pause quand vous voulez — c'est votre compte",
      "Pause it anytime": "Mettez en pause quand vous voulez",
      "Booster time to claim": "Prise en charge par un booster",
      "Time to claim": "Prise en charge",
      "We handle the rest.": "On s'occupe du reste.",
      "Discreet on your bank statement": "Discret sur votre relevé bancaire",
      "No account needed": "Aucun compte requis",
      "VPN matched to your region": "VPN adapté à votre région",
      "on Trustpilot": "sur Trustpilot",
      "Delivered in": "Livré en",
      "Boosters free now": "Boosters libres",
      "Total price": "Prix total",
      "Total, tax included": "Total, taxes comprises",
      "Continue": "Continuer",
      "Service": "Service",
      "Division boost": "Boost de division",
      "Net wins": "Victoires nettes",
      "Placements": "Placements",
      "Current rank": "Rang actuel",
      "Target rank": "Rang cible",
      "You are": "Vous êtes",
      "You want": "Vous visez",
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
        "Sans compte · Remboursé jusqu'à l'attribution d'un booster · VPN adapté à votre région",
      "From": "À partir de",
      "from": "à partir de",
      "Configure your boost": "Configurez votre boost",
      "Watch a live boost": "Voir un boost en direct",
      "Continue your order": "Continuer votre commande",

      /* home hero — the utility bar's roster count and the spotlight card.
         Numbers stay outside these nodes (build.py wraps them in <b>/<span>),
         and so does the booster's handle: the card's CTA is "Order with" +
         <b>vantaa</b>, which is why changing data.py's SPOTLIGHT no longer
         needs a new sentence here. The game name is data and stays as
         written, like every other game name on the site. */
      "verified boosters on shift right now": "boosters vérifiés en service maintenant",
      "Pick your booster": "Choisissez votre booster",
      "This month's #1": "N°1 du mois",
      "Verified": "Vérifié",
      "orders delivered": "commandes livrées",
      "boosts delivered": "boosts livrés",
      "clients": "clients",
      "Clients served": "Clients servis",
      "Clients": "Clients",
      "Included": "Inclus",

      /* add-ons — the labels and notes in data.py's ADDONS, plus the per-game
         name of the picks add-on (`picks` on each game: League picks champions,
         Valorant agents, Rocket League a playlist). Every wording ships in the
         DOM and one is shown, so all of them have to be here. Each note has a
         phone variant beside it for the same reason. */
      "Priority order": "Commande prioritaire",
      "First in the claim queue, claimed in about 6 minutes.":
        "Première de la file de prise en charge, prise en 6 minutes environ.",
      "First in the claim queue, about 6 minutes.":
        "Première de la file, 6 minutes environ.",
      "Solo only queue": "File solo uniquement",
      "Your booster plays alone, in ranked only — no parties.":
        "Votre booster joue seul, en classé uniquement — jamais en groupe.",
      "Plays alone, ranked only — no parties.":
        "Joue seul, en classé — jamais en groupe.",
      "Play on your schedule": "Jouez à vos horaires",
      "Fixed session times, held for the whole order.":
        "Horaires de session fixes, réservés pour toute la commande.",
      "Fixed times, held for the whole order.":
        "Horaires fixes, réservés pour toute la commande.",
      "Champions & roles": "Champions et rôles",
      "Agents & roles": "Agents et rôles",
      "Heroes & roles": "Héros et rôles",
      "Legends & playstyle": "Légendes et style de jeu",
      "Comps & augments": "Compositions et augments",
      "Roles & maps": "Rôles et cartes",
      "Playlist & playstyle": "Playlist et style de jeu",
      "Champions, agents & roles": "Champions, agents et rôles",
      "Always free. Your booster plays the picks you choose.":
        "Toujours gratuit. Votre booster joue les choix que vous faites.",
      "You choose the picks they play.":
        "Vous choisissez les picks joués.",
      "Offline appearance": "Apparaître hors ligne",
      "Always on. Friends see you offline for the whole order.":
        "Toujours actif. Vos amis vous voient hors ligne durant toute la commande.",

      /* hero (home) */
      "Verified boosters — since 2019": "Boosters vérifiés — depuis 2019",
      "The rank is yours.": "Le rang est à vous.",
      "The grind isn't.": "Le grind, non.",
      "Your price in 10 seconds. Claimed in about 18 minutes. Refunded in full until it is.":
        "Votre prix en 10 secondes. Prise en charge en 18 minutes environ. Remboursé intégralement jusque-là.",
      "This month's #1 — vantaa": "N°1 du mois — vantaa",
      "Challenger 1042 LP · 78% WR · EUW · 214 orders": "Challenger 1042 LP · 78 % WR · EUW · 214 commandes",
      "Top booster of the month, vantaa": "Meilleur booster du mois, vantaa",

      /* marquee */
      "92,400 boosts delivered": "92 400 boosts livrés",
      "4.8 / 5 on Trustpilot — 3,140 reviews": "4,8 / 5 sur Trustpilot — 3 140 avis",
      "Most orders claimed within 18 min": "La plupart des commandes prises en 18 min",
      "3,000 players in the Discord": "3 000 joueurs sur le Discord",
      "100% recovery rate on account reviews": "100 % de récupération sur les examens de compte",

      /* section heads / home */
      "Pick your game.": "Choisissez votre jeu.",
      "The price is already on it.": "Le prix est déjà dessus.",
      "Nine games, thirty-seven services, priced per division.":
        "Neuf jeux, trente-sept services, au prix par division.",
      "Services": "Services",
      "Most ordered": "Le plus commandé",
      "Configure": "Configurer",
      "All games": "Tous les jeux",
      "are live too.": "sont aussi en ligne.",
      "Elo boost": "Boost d'elo",
      "Rank boost": "Boost de rang",
      "MMR boost": "Boost de MMR",
      "Unrated wins": "Victoires non classées",
      "Tournament wins": "Victoires en tournoi",
      "Double-up": "Double-up",
      "Calibration": "Calibrage",
      "Badges": "Badges",
      "Kills": "Éliminations",
      "Premier rating": "Classement Premier",
      "Faceit levels": "Niveaux Faceit",
      "Wingman": "Wingman",
      "Wins": "Victoires",
      "Duo": "Duo",
      "Coaching": "Coaching",
      "Every service is priced per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Chaque service est facturé à la division et affiché avant toute connexion. Placements, victoires nettes, coaching et duo sur chaque jeu.",
      "Delivered today": "Livré aujourd'hui",
      "Why this doesn't get you banned": "Pourquoi cela ne vous fait pas bannir",
      /* 04 Dashboard — the section and the mock inside it. Every figure in the
         mock sits outside these nodes (see dash_mock()), so the words match. */
      "Dashboard": "Tableau de bord",
      "You watch the whole thing": "Vous suivez tout du début à la fin",
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
      "K / D / A": "K / M / A",
      "LP": "LP",
      "Order dashboard · live": "Tableau de bord · en direct",
      "Pause": "Pause",
      "Order dashboard — live": "Tableau de bord de commande — en direct",
      "Order tracking dashboard with live match history": "Tableau de bord de suivi avec historique en direct",
      "What they said after": "Ce qu'ils ont dit après",
      "Every review is tied to a paid, completed order — nothing incentivised. One per game, across the roster.":
        "Chaque avis est lié à une commande payée et terminée — rien n'est incité. Un par jeu, sur tout le roster.",
      "Read all reviews": "Lire tous les avis",
      "Read all on Trustpilot": "Tout lire sur Trustpilot",
      "Verified order": "Commande vérifiée",
      "Page": "Page",
      "Verified orders only": "Commandes vérifiées uniquement",
      "Your climb starts at": "Votre montée commence à",
      "Final at checkout. Refunded in full until a booster claims it, pro-rated after that.":
        "Fixé au paiement. Remboursé intégralement jusqu'à la prise en charge, au prorata ensuite.",
      "Set two ranks and the price is on screen before you sign up. No account, no quote request.":
        "Choisissez deux rangs et le prix s'affiche avant toute inscription. Sans compte, sans devis.",
      "Talk to support": "Contacter le support",
      "Your boost": "Votre boost",
      "Change": "Modifier",
      "Queue · Server": "File · Serveur",
      "Money-back guarantee": "Satisfait ou remboursé",

      /* stat band + roster */
      "Boosts delivered": "Boosts livrés",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3 140 avis",
      "Median time to claim": "Délai médian de prise en charge",
      "Players in the Discord": "Joueurs sur le Discord",
      "On shift now —": "En service —",
      "in the Discord": "sur le Discord",
      "Free VOD reviews on Sundays, scrim pickups, and the booster application queue.":
        "Analyses VOD gratuites le dimanche, scrims et file de candidatures booster.",
      "Join the server →": "Rejoindre le serveur →",
      "All games →": "Tous les jeux →",
      "more": "de plus",

      /* 02 Live / 03 Safety — the delivery feed, the rail and the safety proof.
         Numbers sit outside these nodes (<b>34</b> boosters), so the sentence
         still matches whole. "min ago" is shared with the track page. */
      "Updates as orders close": "Mis à jour dès qu'une commande est livrée",
      "Delivered": "Livré",
      "hr ago": "h",
      "d ago": "j",
      "orders closed in the last 24 hours": "commandes livrées ces 24 dernières heures",
      "All": "Tous les",
      "win rate": "de victoires",
      "Free": "Libre",
      /* Availability comes off BOOSTERS[].queue — the status pill and the
         roster table's Queue column render the same strings. */
      "free": "libre",
      "1 order": "1 commande",
      "2 orders": "2 commandes",
      "Free to join": "Gratuit",
      "Join the server": "Rejoindre le serveur",
      "Client satisfaction rate": "Taux de satisfaction client",
      "Your sensitivity and crosshair": "Votre sensibilité et votre viseur",
      "Played in your normal hours": "Joué à vos heures habituelles",
      "Offline the whole order": "Hors ligne pendant toute la commande",
      "Read the full safety policy": "Lire la politique de sécurité complète",

      /* steps */
      "Configure and pay": "Configurez et payez",
      "Ranks, mode, champion or agent preferences, offline appear, scheduled hours. The price never changes after checkout.":
        "Rangs, mode, préférences de champion ou d'agent, mode hors ligne, horaires. Le prix ne change jamais après le paiement.",
      "A booster claims it, usually inside 20 minutes": "Un booster la prend, généralement en moins de 20 minutes",
      "You see their rank, region, win rate and current queue before they start. Swap them once, free, no reason needed.":
        "Vous voyez leur rang, région, taux de victoire et file avant qu'ils commencent. Changez-en une fois, gratuitement, sans justification.",
      "Track every match, pause any time": "Suivez chaque partie, mettez en pause à tout moment",
      "Match history, LP graph and chat in one dashboard. Pause from the dashboard and the account is yours again in minutes.":
        "Historique, courbe de LP et chat dans un seul tableau de bord. Mettez en pause et le compte vous revient en quelques minutes.",

      /* guarantees */
      "Guarantee": "Garantie",
      "Finished or refunded": "Terminé ou remboursé",
      "Every order ends in the rank you paid for or the money back for the part that never arrived. There is no third outcome.":
        "Chaque commande se termine au rang que vous avez payé, ou par le remboursement de la partie qui n'est jamais arrivée. Il n'y a pas de troisième issue.",
      "Privacy": "Confidentialité",
      "Nobody sees your name": "Personne ne voit votre nom",
      "Boosters get a rank, a server and your play window. Your name, email and payment details never reach them, and the order needs no account.":
        "Les boosters reçoivent un rang, un serveur et vos horaires de jeu. Votre nom, votre e-mail et vos données de paiement ne leur parviennent jamais, et la commande ne nécessite aucun compte.",
      "Support": "Support",
      "Answered in minutes, not days": "Réponse en minutes, pas en jours",
      "One thread per order, staffed around the clock. If an account review lands, support files the appeal for you rather than pointing you at a form.":
        "Un fil par commande, suivi 24h/24. Si une vérification de compte tombe, le support dépose le recours à votre place au lieu de vous renvoyer vers un formulaire.",

      /* dashboard points */
      "Match-by-match history": "Historique partie par partie",
      "Every game your booster plays, with the LP swing, KDA and replay link.":
        "Chaque partie de votre booster, avec le gain de LP, le KDA et le lien de replay.",
      "Pause on one click": "Pause en un clic",
      "Want to play tonight? Pause, and the account is free within minutes.":
        "Envie de jouer ce soir ? Mettez en pause, et le compte est libre en quelques minutes.",
      "Chat with the booster, not a queue": "Discutez avec le booster, pas une file",
      "Ask for a champion pool, a schedule, or a swap. Support reads the same thread.":
        "Demandez un pool de champions, un horaire ou un changement. Le support lit le même fil.",

      /* FAQ */
      "Do I need an account to see the price?": "Ai-je besoin d'un compte pour voir le prix ?",
      "No. The calculator is on every page and needs nothing from you. You only enter an email at checkout, and only so we can send you the order link.":
        "Non. Le calculateur est sur chaque page et ne demande rien. Vous ne saisissez un e-mail qu'au paiement, uniquement pour recevoir le lien de commande.",
      "Can I check out without creating an account?": "Puis-je payer sans créer de compte ?",
      "Yes. Email, then payment. We create the order under that address and email you a one-click link to follow it. Set a password later if you want one, or never.":
        "Oui. E-mail, puis paiement. Nous créons la commande sous cette adresse et vous envoyons un lien en un clic pour la suivre. Définissez un mot de passe plus tard si vous le souhaitez, ou jamais.",
      "Is my account safe?": "Mon compte est-il en sécurité ?",
      "Your booster connects through a VPN in your region, appears offline, and plays inside the hours you set. We never ask for a Riot/Steam/Blizzard recovery email, never change your password, and never queue with other customers' accounts.":
        "Votre booster se connecte via un VPN dans votre région, apparaît hors ligne et joue pendant les horaires que vous fixez. Nous ne demandons jamais d'e-mail de récupération Riot/Steam/Blizzard, ne changeons jamais votre mot de passe et ne jouons jamais avec les comptes d'autres clients.",
      "What if I want to play while the boost is running?": "Et si je veux jouer pendant le boost ?",
      "Pause it from the dashboard. The account is free within minutes and the timer stops. Resume when you're done.":
        "Mettez-le en pause depuis le tableau de bord. Le compte est libre en quelques minutes et le chrono s'arrête. Reprenez quand vous avez fini.",
      "What exactly is refunded, and when?": "Qu'est-ce qui est remboursé exactement, et quand ?",
      "In full, no questions, until a booster claims the order. After that, pro-rated on the part that hasn't been delivered — divisions not climbed, wins not won. Refunds are issued to the original payment method within 5 business days.":
        "Intégralement, sans question, jusqu'à la prise en charge de la commande. Ensuite, au prorata de la partie non livrée — divisions non gravies, victoires non obtenues. Les remboursements sont émis sur le moyen de paiement d'origine sous 5 jours ouvrés.",
      "Solo or duo — which should I pick?": "Solo ou duo — que choisir ?",
      "Solo is faster and cheaper: the booster plays alone. Duo means you play every game with them, nobody logs into your account, and it costs 55% more for the extra time.":
        "Le solo est plus rapide et moins cher : le booster joue seul. Le duo signifie que vous jouez chaque partie avec lui, personne ne se connecte à votre compte, et cela coûte 55 % de plus pour le temps supplémentaire.",
      "How fast will someone start?": "En combien de temps quelqu'un commence-t-il ?",
      "Median time to a claimed order last month was 18 minutes. Priority queue takes that down to about 6. If nobody claims it within 24 hours, you get a full refund automatically — you don't have to ask.":
        "Le délai médian de prise en charge le mois dernier était de 18 minutes. La file prioritaire le réduit à environ 6. Si personne ne la prend sous 24 heures, vous êtes remboursé intégralement automatiquement — sans avoir à demander.",
      "Which payment methods do you take?": "Quels moyens de paiement acceptez-vous ?",
      "Cards, Apple Pay and Google Pay, all handled securely by Stripe. Crypto is coming soon. The card statement reads as a neutral merchant name, not the service.":
        "Cartes, Apple Pay et Google Pay, tous gérés en toute sécurité par Stripe. La crypto arrive bientôt. Le relevé de carte affiche un nom de marchand neutre, pas le service.",
      "Verified order ·": "Commande vérifiée ·",

      /* games index */
      "Pick your": "Choisissez votre",
      "battlefield.": "champ de bataille.",
      "Prices are per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Les prix sont à la division et affichés avant toute connexion. Placements, victoires nettes, coaching et duo sur chaque jeu.",
      "How it runs": "Comment ça marche",
      "Three steps, then": "Trois étapes, puis",
      "it's out of your hands": "ce n'est plus votre affaire",
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
      "of them.": "d'entre eux.",
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
      "Four ways to buy a climb.": "Quatre façons d'acheter une montée.",
      "Every title sells the first three. If you are not sure which one you want, read the \"best for\" line — it is usually the whole answer.":
        "Chaque jeu vend les trois premiers. Si vous ne savez pas lequel choisir, lisez la ligne « idéal pour » — c'est en général toute la réponse.",
      "Best for": "Idéal pour",
      "Two ranks, one price. Your booster climbs from where you are to where you want to be, and the number never moves after checkout.":
        "Deux rangs, un prix. Votre booster grimpe d'où vous êtes jusqu'où vous voulez être, et le montant ne bouge plus après le paiement.",
      "You know the rank you want": "Vous savez quel rang vous voulez",
      "Priced per win above your losses, five to an order. A short push when you are close and do not want to commit to a full climb.":
        "Facturé par victoire au-dessus de vos défaites, cinq par commande. Un coup de pouce quand vous êtes proche et ne voulez pas vous engager sur une montée complète.",
      "You are one division short": "Il vous manque une division",
      "We play up to five of your season games, on a ranked account or a fresh one. The rank you land is the rank you keep.":
        "Nous jouons jusqu'à cinq de vos parties de classement, sur un compte classé ou un compte neuf. Le rang obtenu est le rang que vous gardez.",
      "The season just reset": "La saison vient de repartir",
      "An hour with a coach from the roster, live on Discord, screen shared and recorded for you to keep. Live on four of the nine titles.":
        "Une heure avec un coach du roster, en direct sur Discord, écran partagé et enregistré pour vous. Disponible sur quatre des neuf jeux.",
      "You want to climb it yourself": "Vous voulez grimper vous-même",
      "Three steps, then it's out of your hands": "Trois étapes, puis ce n'est plus votre affaire",
      "Same dashboard on all nine titles. It opens from the link we email you — no password, no app — and updates as games finish.":
        "Le même tableau de bord sur les neuf jeux. Il s'ouvre depuis le lien envoyé par e-mail — sans mot de passe, sans application — et se met à jour à la fin de chaque partie.",
      "Asked on this page": "Questions posées sur cette page",
      "Title-specific questions live on each game's page. These are the ones about all nine.":
        "Les questions propres à un jeu sont sur sa page. Voici celles qui concernent les neuf.",
      "Are these all the titles you cover?": "Est-ce là tous les jeux que vous couvrez ?",
      "These nine are the ones with a live board and enough boosters to claim an order quickly. We take one-off requests on other titles in Discord, but there is no page and no instant price for them — if the queue cannot claim it, we say so rather than take the money.":
        "Ces neuf-là sont ceux qui ont un tableau actif et assez de boosters pour prendre une commande rapidement. Nous acceptons des demandes ponctuelles sur d'autres jeux via Discord, mais il n'y a ni page ni prix instantané pour eux — si la file ne peut pas la prendre, nous le disons plutôt que d'encaisser.",
      "Why is Valorant cheaper than Counter-Strike 2?": "Pourquoi Valorant est-il moins cher que Counter-Strike 2 ?",
      "A division is not the same amount of work in every game. Ladders are different lengths, matches are different lengths, and one rung near the top of a ladder can cost several near the bottom of another. Each title carries its own multiplier, and it is on screen before you sign in: the cheapest single division is $3 on Valorant and $9 on Counter-Strike 2.":
        "Une division ne représente pas le même travail dans chaque jeu. Les échelles n'ont pas la même longueur, les parties non plus, et un échelon près du sommet d'une échelle peut en coûter plusieurs en bas d'une autre. Chaque jeu a son propre multiplicateur, affiché avant toute connexion : la division la moins chère est à 3 $ sur Valorant et à 9 $ sur Counter-Strike 2.",
      "Does one booster cover several games?": "Un booster couvre-t-il plusieurs jeux ?",
      "No. Everyone on the board plays exactly one title, and their profile carries the peak rank, the win rate, the on-time record and the orders they have delivered on it. Somebody claiming three ladders at once is somebody we did not hire.":
        "Non. Chaque personne du tableau joue exactement un jeu, et son profil affiche le rang maximal, le taux de victoire, la ponctualité et les commandes livrées. Quelqu'un qui prétend tenir trois échelles à la fois est quelqu'un que nous n'avons pas recruté.",
      "Can I order two titles at once?": "Puis-je commander deux jeux à la fois ?",
      "Yes, as two orders — each gets its own booster, price and dashboard. There is no cross-title bundle, because a discount spanning two boosters would be paying one of them less.":
        "Oui, en deux commandes — chacune avec son booster, son prix et son tableau de bord. Il n'existe pas de pack multi-jeux, car une remise à cheval sur deux boosters reviendrait à en payer un moins.",
      "Do prices change during a sale?": "Les prix changent-ils pendant une promotion ?",
      "SPLIT15 takes 15% off the whole catalogue with nothing to type. Each game page also carries bundle climbs at 22% to 35% off, and a bundle replaces the code rather than adding to it — there is only ever one discount on an order, and it is the larger of the two.":
        "SPLIT15 retire 15 % sur tout le catalogue, sans rien à saisir. Chaque page de jeu propose aussi des packs de montée à 22 % à 35 % de remise, et un pack remplace le code au lieu de s'y ajouter — il n'y a jamais qu'une seule remise sur une commande, et c'est la plus avantageuse des deux.",
      "Nine titles, one guarantee.": "Neuf jeux, une garantie.",
      "Refunded in full until a booster claims it, pro-rated after that, and claimed in 18 min on average.":
        "Remboursé intégralement jusqu'à la prise en charge, au prorata ensuite, et pris en charge en 18 min en moyenne.",
      "Start with League": "Commencer par League",

      /* game page */
      "Home": "Accueil",
      "Breadcrumb": "Fil d'Ariane",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3 140 avis",
      "boosters free now": "boosters libres",
      "online": "en ligne",
      "orders,": "commandes,",
      "in players' words": "dans les mots des joueurs",
      "Questions people": "Les questions que les gens",
      "ask before paying": "posent avant de payer",
      "Ask us instead": "Demandez-nous plutôt",
      "On shift now": "En service maintenant",

      /* booster table */
      "Booster": "Booster",
      "Game": "Jeu",
      "Peak": "Sommet",
      "Win rate": "Taux de victoire",
      "Queue": "File",
      "Every booster is trialled live before onboarding and reviewed monthly. Ranks shown are verified from match history, not self-reported.":
        "Chaque booster est testé en direct avant l'intégration et évalué chaque mois. Les rangs affichés sont vérifiés depuis l'historique, pas déclarés.",

      /* how-it-works */
      "How it works": "Comment ça marche",
      "No account.": "Pas de compte.",
      "No surprises.": "Pas de surprises.",
      "No ticket queue.": "Pas de file de tickets.",
      "You can see the whole price before you tell us anything about yourself. That is the entire point of the way this is built: the calculator is the first thing on every page, the number it shows is the number you pay, and the only thing checkout asks for is an email to send the order link to.":
        "Vous voyez le prix complet avant de nous dire quoi que ce soit sur vous. C'est tout l'intérêt de cette conception : le calculateur est la première chose sur chaque page, le montant affiché est celui que vous payez, et le paiement ne demande qu'un e-mail pour envoyer le lien de commande.",
      "Solo or duo": "Solo ou duo",
      "The booster plays alone": "Le booster joue seul",
      "Fastest and cheapest. You hand over the login, they connect through a VPN in your region, appear offline, and play inside the hours you set. You keep the account and can pause or take it back at any moment from the dashboard.":
        "Le plus rapide et le moins cher. Vous confiez les identifiants, le booster se connecte via un VPN dans votre région, apparaît hors ligne et joue pendant les horaires que vous fixez. Vous gardez le compte et pouvez le mettre en pause ou le reprendre à tout moment depuis le tableau de bord.",
      "You play every game": "Vous jouez chaque partie",
      "Nobody logs into your account, ever. You queue with the booster, voice optional, and most of them will call rotations and review your mistakes on the way up. It costs more because it takes their time at your pace.":
        "Personne ne se connecte jamais à votre compte. Vous jouez avec le booster, voix en option, et la plupart appelleront les rotations et corrigeront vos erreurs en chemin. Cela coûte plus cher car cela mobilise leur temps à votre rythme.",
      "Everything else": "Tout ce que",
      "people ask": "les gens demandent",

      /* boosters roster + profile — design_handoff_boosters_roster */
      "Verified from match history, not self-reported.":
        "Vérifié depuis l'historique, pas déclaré.",
      "How someone gets on this page": "Comment on arrive sur cette page",
      "30 days": "30 jours",
      "applied last month": "candidatures le mois dernier",
      "trialled live on our account — five games, watched":
        "testés en direct sur notre compte — cinq parties, observées",
      "added to the board": "ajoutés à l'effectif",
      "62% win-rate floor, checked monthly": "Plancher de 62 % de victoires, vérifié chaque mois",
      "Ranks read from the game API": "Rangs lus depuis l'API du jeu",
      "Trial games recorded and reviewed": "Parties d'essai enregistrées et revues",
      "Applications open in the": "Les candidatures sont ouvertes dans la file",
      "queue": "d'attente",
      "players in there.": "joueurs y sont.",
      "Join": "Rejoindre",
      "on the board": "dans l'effectif",
      "free right now": "libres en ce moment",
      "Availability": "Disponibilité",
      "Everyone": "Tout le monde",
      "Free now": "Libres",
      "Sort by": "Trier par",
      "Free first": "Libres d'abord",
      "Game · Server": "Jeu · Serveur",
      "Peak this season": "Sommet cette saison",
      "Win rate · 30d": "Taux de victoire · 30 j",
      "Hire": "Engager",
      "Nobody free on": "Personne de libre sur",
      "right now": "en ce moment",
      "Nobody free right now": "Personne de libre en ce moment",
      "on the board — start the order and the first one free claims it.":
        "dans l'effectif — lancez la commande et le premier libre la prend.",
      "Order anyway": "Commander quand même",
      "Show everyone": "Voir tout le monde",
      "Showing": "Affichage de",
      "free now": "libres",
      "Load more": "Voir plus",
      "Boosting since": "Booster depuis",
      "in the queue": "dans la file",
      "Orders delivered": "Commandes livrées",
      "Average rating": "Note moyenne",
      "On-time rate": "Livraisons à l'heure",
      "Disputes": "Litiges",
      "Completed orders": "Commandes terminées",
      "Completed": "Terminée",
      "Rating": "Note",
      "On time": "À l'heure",
      "Top booster": "Meilleur booster",
      "Rank verified every month": "Rang vérifié chaque mois",
      "One free swap, no reason needed": "Un changement gratuit, sans justification",
      "See the roster": "Voir l'effectif",
      "See all": "Tout voir",
      "day": "jour",
      "Request": "Demander",
      "Name them at checkout and your order waits for them instead of going to the open board.":
        "Nommez-le au paiement et votre commande l'attend au lieu de partir sur l'effectif ouvert.",
      "Named booster": "Booster nommé",
      "No extra fee": "Sans supplément",
      "ahead of you": "avant vous",
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
      "The roster": "L'effectif",
      "Verified from": "Vérifié depuis",
      "match history,": "l'historique,",
      "not self-reported.": "pas déclaré.",
      "Every applicant is trialled live on our account before they touch yours: five games, watched, in the bracket they claim. Ranks on this page are read from the API, not typed into a form. Anyone whose win rate drops below 62% over a rolling month comes off the board until they climb it back.":
        "Chaque candidat est testé en direct sur notre compte avant de toucher au vôtre : cinq parties, observées, dans le palier qu'il revendique. Les rangs de cette page sont lus depuis l'API, pas saisis dans un formulaire. Quiconque voit son taux de victoire passer sous 62 % sur un mois glissant quitte l'effectif jusqu'à le remonter.",
      "Apply as a booster": "Postuler comme booster",
      "Roster": "Effectif",
      "Everyone on shift": "Tous en service",
      "Updated live": "Mis à jour en direct",

      /* guarantee page — design_handoff_safety_guarantee */
      "Safety & guarantee": "Sécurité et garantie",
      "Written down, not \"depends on the order\".":
        "Écrit noir sur blanc, pas « ça dépend de la commande ».",
      "A refund policy that needs a support ticket to explain isn't a policy. Here is the whole thing, in the three cases that actually happen.":
        "Une politique de remboursement qui nécessite un ticket de support pour être expliquée n'est pas une politique. La voici en entier, dans les trois cas qui arrivent réellement.",
      /* hero figures — the number is data, the unit is a word */
      "5 days": "5 jours",
      "24 hrs": "24 h",
      "Recovery rate on account reviews, across": "Taux de récupération sur les vérifications de compte, sur",
      "completed orders": "commandes terminées",
      "Refunds land back on the original payment method, no ticket needed":
        "Les remboursements reviennent sur le moyen de paiement d'origine, sans ticket",
      "Unclaimed after payment? Refunded in full, automatically":
        "Non prise en charge après paiement ? Remboursée intégralement, automatiquement",
      "Before a booster claims it": "Avant la prise en charge",
      "100% back, no reason asked": "100 % remboursé, sans justification",
      "One button in the order page. The money is back on the original payment method within 5 business days, and nobody will email you to ask why.":
        "Un bouton sur la page de commande. L'argent revient sur le moyen de paiement d'origine sous 5 jours ouvrés, et personne ne vous écrira pour demander pourquoi.",
      "Started but unfinished": "Commencé mais inachevé",
      "Pro-rated on what wasn't delivered": "Au prorata de ce qui n'a pas été livré",
      "Divisions not climbed and wins not won are refunded at the same rate you paid for them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond portion, calculated by the same formula that quoted you.":
        "Les divisions non gravies et les victoires non obtenues sont remboursées au tarif que vous avez payé. Un Gold → Diamant arrêté au Platine rembourse la portion Platine → Diamant, calculée par la formule qui vous a coté.",
      "Past the ETA": "Au-delà du délai",
      "Your choice, and we tell you first": "À vous de choisir, et nous vous prévenons d'abord",
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back.":
        "Si une commande dépasse son délai de livraison, nous vous prévenons avant que vous le remarquiez : continuer avec un crédit de 15 %, changer de booster, ou récupérer la portion inachevée.",

      /* band 02 — the safety prose, the disclaimer plate, the measure card */
      "Anti-cheat looks for software, not skill. Every solo order runs behind an enterprise VPN matched to your region, the booster mirrors your sensitivity and crosshair, and sessions are scheduled inside the hours you normally play — so the activity pattern on the account never changes. Duo orders never touch your login at all.":
        "L'anti-triche cherche des logiciels, pas du talent. Chaque commande solo passe par un VPN professionnel dans votre région, le booster reproduit votre sensibilité et votre viseur, et les sessions sont planifiées pendant vos horaires de jeu habituels — le schéma d'activité du compte ne change donc jamais. Les commandes duo ne touchent jamais à vos identifiants.",
      "If a boost triggers an account review, support files the appeal and the order is refunded in full while it runs. Your name, email and payment details are never shared with the booster.":
        "Si un boost déclenche une vérification de compte, le support dépose le recours et la commande est remboursée intégralement pendant la procédure. Votre nom, votre e-mail et vos données de paiement ne sont jamais communiqués au booster.",
      "Boosting is against the terms of service of every game listed here. We reduce the risk as far as it can be reduced and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is lying to you.":
        "Le boosting va à l'encontre des conditions d'utilisation de chaque jeu listé ici. Nous réduisons le risque autant que possible et ne prétendrons pas qu'il est nul, car il ne l'est pas — tout concurrent qui affirme le contraire vous ment.",
      "What that means per order": "Ce que cela signifie par commande",
      "Every order": "Chaque commande",
      "Enterprise VPN, matched to your region": "VPN professionnel, adapté à votre région",
      "Not a consumer VPN and not a datacentre IP — the login location never changes.":
        "Ni un VPN grand public ni une IP de centre de données — le lieu de connexion ne change jamais.",
      "The booster mirrors your settings before the first game.":
        "Le booster reproduit vos réglages avant la première partie.",
      "Played inside your normal hours": "Joué pendant vos horaires habituels",
      "You set the window at checkout; sessions are scheduled inside it.":
        "Vous fixez la plage horaire au paiement ; les sessions y sont planifiées.",
      "Offline appearance, whole order": "Apparence hors ligne, toute la commande",
      "Friends see you offline until the order closes.":
        "Vos amis vous voient hors ligne jusqu'à la clôture de la commande.",
      "Duo never touches your login": "Le duo ne touche jamais à vos identifiants",
      "You play your own account. Nobody signs in but you.":
        "Vous jouez sur votre propre compte. Personne ne s'y connecte à part vous.",

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
        "Les six auxquelles le support répond le plus. Si la vôtre n'y est pas, le fil de votre commande atteint une personne, pas un bot.",
      "Ask support": "Contacter le support",
      "Can I play my own account while an order runs?":
        "Puis-je jouer sur mon propre compte pendant une commande ?",
      "Yes, and it costs nothing. Pause the order from the order page and the booster stops at the end of the current game; unpause and it resumes the same night if a slot is open. Playing ranked yourself while a solo order is unpaused is the one thing to avoid — two people queuing the same account is what looks abnormal, not the boost.":
        "Oui, et cela ne coûte rien. Mettez la commande en pause depuis sa page et le booster s'arrête à la fin de la partie en cours ; relancez-la et elle reprend le soir même si un créneau est libre. La seule chose à éviter est de jouer en classé vous-même pendant qu'une commande solo est active — c'est le fait que deux personnes lancent des files sur le même compte qui paraît anormal, pas le boost.",
      "What happens if my account gets a review or a ban?":
        "Que se passe-t-il si mon compte fait l'objet d'une vérification ou d'un bannissement ?",
      "Support files the appeal for you and the order is refunded in full while it runs, so you are never paying for an account you cannot use. Boosting still breaks every listed game's terms of service — the risk is reduced as far as it can be, not removed.":
        "Le support dépose le recours à votre place et la commande est remboursée intégralement pendant la procédure : vous ne payez jamais pour un compte inutilisable. Le boosting enfreint toujours les conditions d'utilisation de chaque jeu listé — le risque est réduit autant que possible, pas supprimé.",
      "Will the booster change my password or my settings?":
        "Le booster va-t-il changer mon mot de passe ou mes réglages ?",
      "No. Login details are used to sign in and nothing else — no password changes, no email changes, no purchases, no rune or loadout edits beyond the champions and roles you asked for. Sensitivity and crosshair are mirrored to yours, then restored. Change your password once the order closes anyway; the order page tells you when.":
        "Non. Les identifiants servent à se connecter et à rien d'autre — aucun changement de mot de passe, d'e-mail, aucun achat, aucune modification de runes ou d'équipement au-delà des champions et rôles demandés. La sensibilité et le viseur sont alignés sur les vôtres, puis rétablis. Changez tout de même votre mot de passe à la clôture ; la page de commande vous indique quand.",
      "How is the price calculated, and can it change after I pay?":
        "Comment le prix est-il calculé, et peut-il changer après paiement ?",
      "The price is per division crossed, so a longer climb costs more per step than a short one. It is fixed at checkout: the number on the button is the number charged, and nothing is added later. Duo adds 55% because the booster carries a second player, and add-ons are priced individually before you pay.":
        "Le prix est calculé par division franchie : une longue montée coûte donc plus cher par palier qu'une courte. Il est fixé au paiement : le montant sur le bouton est celui qui est débité, et rien n'est ajouté ensuite. Le duo ajoute 55 % parce que le booster porte un second joueur, et les options sont facturées individuellement avant le paiement.",
      "Do I have to make an account to order?":
        "Dois-je créer un compte pour commander ?",
      "No. Orders are created against your email and you get a one-click link to follow them. Set a password afterwards if you want the dashboard to remember your orders; skip it and the link still works. Your name, email and card details are never shared with the booster.":
        "Non. Les commandes sont créées à partir de votre e-mail et vous recevez un lien en un clic pour les suivre. Définissez un mot de passe ensuite si vous voulez que le tableau de bord retienne vos commandes ; sinon, le lien fonctionne quand même. Votre nom, votre e-mail et vos données de carte ne sont jamais communiqués au booster.",
      "Can I pick a specific booster?": "Puis-je choisir un booster précis ?",
      "Yes — name one at checkout from their profile and the order waits for them instead of going to the open board. That means a slower start, so we show their current queue and slots before you commit. Leave it open and the first free booster in your bracket claims it, usually inside 18 min.":
        "Oui — désignez-en un au paiement depuis son profil et la commande l'attend au lieu de partir sur le tableau ouvert. Cela signifie un démarrage plus lent, c'est pourquoi nous affichons sa file et ses créneaux avant que vous ne validiez. Laissez-la ouverte et le premier booster libre de votre palier la prend, généralement en moins de 18 min.",

      /* support page */
      "Two ways in.": "Deux moyens de nous joindre.",
      "Both are read": "Les deux sont lus",
      "by people.": "par des humains.",
      "No ticket robot, no \"we'll get back to you within 48 hours\". Discord is the fast one — that's where this market already lives, and it's where our staff sit all day.":
        "Pas de robot à tickets, pas de « nous vous répondrons sous 48 heures ». Discord est le plus rapide — c'est là que ce marché vit déjà, et là que notre équipe est présente toute la journée.",
      "Median first reply last month": "Première réponse médiane le mois dernier",
      "Fastest": "Le plus rapide",
      "Discord — open a ticket in #support": "Discord — ouvrez un ticket dans #support",
      "Public server, private ticket channels. Order questions, refunds, booster swaps and pre-sales, 24/7. You can also just read what other buyers are saying before you order anything, which is rather the point of it being public.":
        "Serveur public, canaux de tickets privés. Questions de commande, remboursements, changements de booster et avant-vente, 24/7. Vous pouvez aussi lire ce que disent les autres acheteurs avant de commander, ce qui est tout l'intérêt d'un serveur public.",
      "Open the Discord invite": "Ouvrir l'invitation Discord",
      "On the record": "Par écrit",
      "Email — info@esportsboost.com": "E-mail — info@esportsboost.com",
      "Better for anything involving a payment dispute or a document. Answered in under two hours during EU and NA daytime, under six overnight.":
        "Préférable pour tout litige de paiement ou document. Réponse en moins de deux heures en journée UE et NA, moins de six la nuit.",
      "Or write": "Ou écrivez",
      "it here": "ici",
      "Goes to the same inbox. If you have an order number, include it — it puts the message in front of the person handling that order.":
        "Va dans la même boîte de réception. Si vous avez un numéro de commande, indiquez-le — cela met le message devant la personne qui gère cette commande.",
      "Email": "E-mail",
      "Order number (optional)": "Numéro de commande (facultatif)",
      "Message": "Message",
      "What's going on?": "Que se passe-t-il ?",
      "Send message": "Envoyer le message",
      "Sending…": "Envoi…",
      /* The form's three outcomes. Each sentence is its own node — the address
         and the visitor's own email ride in <b>s of their own, so nothing here
         has a figure or a mailbox interpolated into a translatable string. */
      "Sent — it's in the inbox.": "Envoyé — c'est dans la boîte de réception.",
      "The reply lands at": "La réponse arrivera à",
      "your address": "votre adresse",
      "Discord is quicker if you'd rather not wait.": "Discord est plus rapide si vous préférez ne pas attendre.",
      "Noted — this is a preview.": "Noté — ceci est un aperçu.",
      "Nothing was emailed: this build has no mailbox configured. Write to":
        "Aucun e-mail n'a été envoyé : cette version n'a pas de boîte configurée. Écrivez à",
      "and it reaches the same people.": "et cela arrive aux mêmes personnes.",
      "That didn't send.": "L'envoi a échoué.",
      "Rather than lose it, write to": "Plutôt que de le perdre, écrivez à",
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
        "Chaque avis ci-dessous est rattaché à une commande payée et terminée — extrait de Trustpilot et de la note en page de commande, puis dédupliqué. Nous ne filtrons pas par note, les avis une étoile figurent dans le même flux.",
      "across": "sur",
      "Read the worst first": "Voir les pires d'abord",
      "Read on Trustpilot": "Lire sur Trustpilot",
      "Overall rating": "Note globale",
      "Verified only": "Vérifiés uniquement",
      "Click a row to filter the feed by that rating.":
        "Cliquez sur une ligne pour filtrer le flux par cette note.",
      "Any": "Toutes",
      "or less": "ou moins",
      "Most recent": "Plus récents",
      "Highest rated": "Mieux notés",
      "Lowest rated": "Moins bien notés",
      "Clear filters": "Effacer les filtres",
      "Nothing matches that yet": "Aucun avis ne correspond",
      "No review in the feed has that rating for this game. Widen the filters to see the rest.":
        "Aucun avis du flux n'a cette note pour ce jeu. Élargissez les filtres pour voir le reste.",
      "Load 30 more": "Charger 30 de plus",
      "Show the rest": "Afficher le reste",
      "Excellent": "Excellent",
      "Where the score": "D'où vient",
      "comes from": "la note",
      "A review request goes out once, on delivery, and never again. Nothing is incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than competitors who buy them, and it's the reason the score is worth reading at all.":
        "Une demande d'avis est envoyée une fois, à la livraison, et jamais plus. Rien n'est incité — pas de remise pour un avis, pas de récompense pour un cinq. Cela maintient un volume inférieur à celui des concurrents qui les achètent, et c'est pourquoi la note vaut la peine d'être lue.",

      /* the demo page (was "track my order") — design_handoff_track_order */
      "Demo": "Démo",
      "Demo dashboard": "Tableau de bord démo",
      "Your link works without a password.": "Votre lien fonctionne sans mot de passe.",
      "Guest orders are tracked by the link we emailed you. Lost it? Put the address you paid with below and we'll send it again. Nothing to remember, nothing to reset.":
        "Les commandes invité se suivent via le lien que nous vous avons envoyé par e-mail. Perdu ? Indiquez ci-dessous l'adresse utilisée pour payer et nous le renverrons. Rien à retenir, rien à réinitialiser.",
      "No account, no password — the link is the login":
        "Pas de compte, pas de mot de passe — le lien est la connexion",
      "It never expires and works on any device":
        "Il n'expire jamais et fonctionne sur tous les appareils",
      "Find your order": "Retrouvez votre commande",
      "Guest safe": "Sans compte",
      "Order number": "Numéro de commande",
      /* the two states of the helper line under the order-number field, and the
         two submit labels — page_demo()'s own script owns these nodes and asks
         for them through esbT, because they swap at runtime. */
      "On your confirmation email, under the total.":
        "Sur votre e-mail de confirmation, sous le total.",
      "We can't find that order number. Check the confirmation email, or use the address you paid with below.":
        "Nous ne trouvons pas ce numéro de commande. Vérifiez l'e-mail de confirmation, ou utilisez ci-dessous l'adresse ayant servi au paiement.",
      "or": "ou",
      "The email you paid with": "L'e-mail utilisé pour payer",
      "We resend the link to that address. It never expires and it works on any device.":
        "Nous renvoyons le lien à cette adresse. Il n'expire jamais et fonctionne sur tous les appareils.",
      "Find my order": "Trouver ma commande",
      "Email me the link": "M'envoyer le lien",
      "Demo — no email was sent.": "Démo — aucun e-mail n'a été envoyé.",
      "On the live site the link reaches": "Sur le site en ligne, le lien parvient à",
      "inside a minute, it never expires, and it opens the dashboard below on any device.":
        "en moins d'une minute, il n'expire jamais et il ouvre le tableau de bord ci-dessous sur tous les appareils.",
      "The order number is in your confirmation email, on the line under the total.":
        "Le numéro de commande figure dans votre e-mail de confirmation, sur la ligne sous le total.",

      /* the resolved order */
      "Back to the order lookup": "Retour à la recherche de commande",
      "In progress": "En cours",
      "Paused": "En pause",
      "Example": "Exemple",
      "Pause order": "Mettre en pause",
      "Resume order": "Reprendre",
      "Order paused.": "Commande en pause.",
      "The account is free within minutes and the delivery clock stops. Resume whenever you're done playing.":
        "Le compte est libre en quelques minutes et le délai de livraison s'arrête. Reprenez quand vous avez fini de jouer.",
      "last game": "dernière partie",
      "Play window": "Créneau de jeu",
      "Watch live": "Regarder en direct",
      "Streaming now": "En diffusion",
      "Not streaming": "Hors diffusion",
      "is sharing their screen.": "partage son écran.",
      "isn't streaming right now.": "ne diffuse pas pour le moment.",
      "Discord screen share": "Partage d'écran Discord",
      "Join and watch": "Rejoindre et regarder",
      "Open the order channel": "Ouvrir le salon de la commande",
      "The channel is private to you and your booster, and closes when the order is delivered.":
        "Le salon est privé entre vous et votre booster, et se ferme à la livraison de la commande.",
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
      "Ranked solo": "Classée solo",
      "Win": "Victoire",
      "Loss": "Défaite",
      "min ago": "min",

      /* checkout */
      "Secure checkout": "Paiement sécurisé",
      "Need a hand?": "Besoin d'aide ?",
      "Required": "Obligatoire",
      "Optional": "Facultatif",
      "Anything the booster should know": "Ce que le booster doit savoir",
      "Enter an email we can send the order link to.":
        "Saisissez un e-mail auquel envoyer le lien de commande.",
      "Mornings": "Matins",
      "Afternoons": "Après-midis",
      "Evenings": "Soirées",
      "Nights": "Nuits",
      "Card, Apple Pay and Google Pay are all on the next screen — details are entered on Stripe's secure checkout, so we never see or store them. Statements read as a neutral merchant name.":
        "Carte, Apple Pay et Google Pay sont tous sur l'écran suivant — les données sont saisies sur le paiement sécurisé de Stripe, nous ne les voyons ni ne les stockons jamais. Les relevés affichent un nom de marchand neutre.",
      "Secured by Stripe": "Sécurisé par Stripe",
      "Contacting payment…": "Connexion au paiement…",
      "Refunded in full until a booster claims it":
        "Remboursé intégralement jusqu'à la prise en charge par un booster",
      "Last chance to add": "Dernière chance d'ajouter",
      "Discount code": "Code de réduction",
      "applied": "appliqué",
      "No code applied": "Aucun code appliqué",
      "Have a code?": "Vous avez un code ?",
      "Have another code?": "Vous avez un autre code ?",
      "Enter a code": "Saisir un code",
      "Close": "Fermer",
      "Your email": "Votre e-mail",
      "Order details": "Détails de la commande",
      "Payment": "Paiement",
      "Checkout": "Paiement",
      "No account needed. We create the order under your email and send a one-click link to follow it. You can set a password afterwards if you want one.":
        "Aucun compte requis. Nous créons la commande sous votre e-mail et envoyons un lien en un clic pour la suivre. Vous pourrez définir un mot de passe ensuite si vous le souhaitez.",
      "Used for the order link and nothing else. No marketing unless you tick the box at the end.":
        "Utilisé pour le lien de commande et rien d'autre. Pas de marketing sauf si vous cochez la case à la fin.",
      "Preferred hours": "Horaires préférés",
      "Any time": "N'importe quand",
      "My usual play hours (18:00–00:00)": "Mes horaires de jeu habituels (18h00–00h00)",
      "While I'm at work (09:00–17:00)": "Pendant que je travaille (09h00–17h00)",
      "Overnight only": "La nuit uniquement",
      "Anything the booster should know (optional)": "Ce que le booster doit savoir (facultatif)",
      "Champion pool, roles, don't touch ranked flex…": "Pool de champions, rôles, ne pas toucher au flex classé…",
      "Hours you can play, roles, other accounts…": "Heures où vous pouvez jouer, rôles, autres comptes…",
      "Pay with": "Payer avec",
      "Payment method": "Moyen de paiement",
      "Card": "Carte",
      "Crypto": "Crypto",
      "— coming soon": "— bientôt disponible",
      "Card details are entered on Stripe's secure checkout — we never see or store them. Statements read as a neutral merchant name.":
        "Les données de carte sont saisies sur le paiement sécurisé de Stripe — nous ne les voyons ni ne les stockons jamais. Les relevés affichent un nom de marchand neutre.",
      "Email me when my order is claimed and when it's done. Nothing else.":
        "Prévenez-moi quand ma commande est prise en charge et terminée. Rien d'autre.",
      "Place the order": "Passer la commande",
      "Read the guarantee": "Lire la garantie",
      "Order placed": "Commande passée",
      "This is a local preview, so no payment was taken and no email was sent. In production this is the point where the order goes on the booster board, the confirmation email leaves, and":
        "Ceci est un aperçu local : aucun paiement n'a été prélevé et aucun e-mail envoyé. En production, c'est ici que la commande rejoint le tableau des boosters, que l'e-mail de confirmation part, et que",
      "fires to GA4 and to the Meta CAPI gateway.": "est envoyé à GA4 et à la passerelle Meta CAPI.",
      "See what the dashboard looks like": "Voir à quoi ressemble le tableau de bord",
      "Order summary": "Récapitulatif de commande",
      "Locked at checkout": "Verrouillé au paiement",
      "Climb": "Montée",
      "Boost": "Boost",
      "Money-back until claimed": "Remboursé jusqu'à la prise en charge",
      "Change the order": "Modifier la commande",

      /* checkout success */
      "Confirming payment…": "Confirmation du paiement…",
      "One moment": "Un instant",
      "We're confirming your payment with Stripe.": "Nous confirmons votre paiement avec Stripe.",
      "Order": "Commande",
      "Paid": "Payé",

      /* become a booster */
      "Work here": "Travailler ici",
      "Get paid": "Soyez payé",
      "for the queue": "pour la file",
      "you'd play anyway.": "que vous joueriez de toute façon.",
      "Payouts weekly, 70% of the order value on solo and 75% on duo, no deductions for the platform's payment fees. Pick your own shifts; take an order or don't. What we ask for is the rank, a clean account history, and that you never pass an account to anyone.":
        "Paiements hebdomadaires, 70 % de la valeur de commande en solo et 75 % en duo, sans déduction des frais de paiement de la plateforme. Choisissez vos créneaux ; prenez une commande ou non. Ce que nous demandons : le rang, un historique de compte propre, et de ne jamais transmettre un compte à qui que ce soit.",
      "Of the order, to you": "De la commande, pour vous",
      "Weekly": "Hebdomadaire",
      "Payouts, no minimum": "Paiements, sans minimum",
      "5 games": "5 parties",
      "Live trial before onboarding": "Essai en direct avant l'intégration",
      "In-game name": "Pseudo en jeu",
      "Peak rank": "Rang maximal",
      "Anything else": "Autre chose",
      "Apply": "Postuler",
      "How the trial works": "Comment se déroule l'essai",

      /* legal */
      "Last updated": "Dernière mise à jour",
      "Questions about any of this go to": "Toute question à ce sujet est à adresser au",
      "support": "support",
      "Plain answers, same day.": "Des réponses claires, le jour même.",
      "Terms of service": "Conditions d'utilisation",
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
      "isn't on": "n'est pas",
      "the ladder.": "sur le ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Le lien est mort ou la page a été déplacée. Le calculateur est à deux clics dans tous les cas.",
      "Pick a game": "Choisir un jeu",
      "Back to the homepage": "Retour à l'accueil",

      /* free guides landing — design_handoff_free_guides. Long-form prose
         (the lede, band subs, chapter notes, author metas, reader quotes and
         the FAQ answers) stays as content, the same as review text. */
      "Free guides · no payment": "Guides gratuits · sans paiement",
      "Browse boosting": "Parcourir le boosting",
      "Free guides": "Guides gratuits",
      "The two guides our boosters actually wrote.": "Les deux guides que nos boosters ont vraiment écrits.",
      "PDFs, yours to keep": "Des PDF, à vous pour toujours",
      "Free, and they stay free": "Gratuits, et ils le restent",
      "One email, no spam": "Un e-mail, aucun spam",
      "Players downloaded them": "Joueurs les ont téléchargés",
      "Chapters + 12 drills": "Chapitres + 12 exercices",
      "Reader rating": "Note des lecteurs",
      "Which do you want?": "Lequel voulez-vous ?",
      "Instant": "Immédiat",
      "Take both — they're free, and most people play both.":
        "Prenez les deux — ils sont gratuits, et la plupart des gens jouent aux deux.",
      "Also send me one email a month with new guides and patch notes. Nothing else, and one click unsubscribes.":
        "Envoyez-moi aussi un e-mail par mois avec les nouveaux guides et les notes de patch. Rien d'autre, et un clic pour se désabonner.",
      "We never sell your address.": "Nous ne vendons jamais votre adresse.",
      "Privacy policy": "Politique de confidentialité",
      "Check your inbox.": "Vérifiez votre boîte de réception.",
      "on the way to": "en route vers",
      "If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        "Si rien n'arrive dans deux minutes, regardez dans les promotions — il y atterrit parfois en premier.",
      "Use a different address": "Utiliser une autre adresse",
      /* CTA labels, helper, note, success line — swapped at runtime via esbT */
      "Send me both guides": "Envoyez-moi les deux guides",
      "Send me the League guide": "Envoyez-moi le guide League",
      "Send me the Valorant guide": "Envoyez-moi le guide Valorant",
      "Pick a guide first": "Choisissez d'abord un guide",
      "Both guides, one email, two attachments.": "Deux guides, un e-mail, deux pièces jointes.",
      "Only one? The other is free too.": "Un seul ? L'autre est gratuit aussi.",
      "Pick at least one guide.": "Choisissez au moins un guide.",
      "Used to send the guides. Nothing else unless you tick the box below.":
        "Sert à envoyer les guides. Rien d'autre, sauf si vous cochez la case ci-dessous.",
      "Enter an address we can send the PDFs to.": "Entrez une adresse à laquelle envoyer les PDF.",
      "Arrives in about a minute. No card, no account.": "Arrive en une minute environ. Sans carte, sans compte.",
      "That address does not look right — check it and try again.":
        "Cette adresse semble incorrecte — vérifiez-la et réessayez.",
      "Both guides are": "Les deux guides sont",
      "The League guide is": "Le guide League est",
      "The Valorant guide is": "Le guide Valorant est",
      "Your guide is": "Votre guide est",
      "What's inside": "Ce qu'ils contiennent",
      "Six chapters each, no padding.": "Six chapitres chacun, sans remplissage.",
      "Who wrote them": "Qui les a écrits",
      "Written by people who play these ranks for a living.":
        "Écrits par des gens qui jouent ces rangs pour vivre.",
      "The authors": "Les auteurs",
      "Seven authors across two games": "Sept auteurs sur deux jeux",
      "Rewritten every patch cycle": "Réécrits à chaque cycle de patch",
      "Readers": "Lecteurs",
      "What they changed for them.": "Ce qu'ils ont changé pour eux.",
      "Before you hand over an email": "Avant de donner votre e-mail",
      "Fair questions. We would ask them too.": "Des questions légitimes. Nous les poserions aussi.",
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
        "Elle passe sur le tableau et un booster {} vérifié la prend. Si personne ne la prend sous 24 heures, la commande se rembourse d'elle-même.",
      "{} of them, {} only — {} or above, with a clean account history and a name you can look up. Order without naming anyone and it goes to whoever is free; name one and it waits for them.":
        "{} au total, sur {} uniquement — {} ou au-dessus, avec un historique de compte propre et un nom que vous pouvez vérifier. Commandez sans désigner personne et elle part au premier libre ; désignez-en un et elle l'attend.",
      "{} flags accounts on patterns, not accusations: a login from the other side of the world, a sudden change in hours, a win rate that doesn't look human. So we don't produce any of those patterns. Your booster connects through an enterprise VPN in your region, plays inside the hours you set, and keeps your settings.":
        "{} signale les comptes sur des schémas, pas sur des accusations : une connexion à l'autre bout du monde, un changement soudain d'horaires, un taux de victoire qui n'a rien d'humain. Nous ne produisons donc aucun de ces schémas. Votre booster se connecte via un VPN professionnel dans votre région, joue dans les horaires que vous fixez et conserve vos réglages.",
      "Boosting is against {}'s terms of service. We have never had an account actioned for any of our {} clients and we recover any that are, but nobody honest will tell you the risk is zero — and anyone who does is selling you something.":
        "Le boosting est contraire aux conditions d'utilisation de {}. Aucun compte n'a jamais été sanctionné parmi nos {} clients, et nous récupérons ceux qui le seraient ; mais personne d'honnête ne vous dira que le risque est nul — et quiconque l'affirme a quelque chose à vous vendre.",
      /* The roster sentence spells its own count, so the capture is a WORD and
         gets the exact lookup patTranslate() runs on the way out. A roster size
         that lands on a spelling not listed here passes through in English —
         add it rather than leaving it. */
      "Four": "Quatre",
      "Twenty-nine": "Vingt-neuf",
      "Thirty-one": "Trente et un",

      /* 01 How it runs */
      "Four steps, and you can see all of them.": "Quatre étapes, et vous les voyez toutes.",
      "The number you see is the number you pay. Nothing is added later, and no account is needed to buy.":
        "Le montant affiché est celui que vous payez. Rien n'est ajouté ensuite, et aucun compte n'est nécessaire pour acheter.",
      "Price fixed at checkout": "Prix figé au paiement",
      "A booster claims it": "Un booster la prend",
      "Median 18 minutes": "18 minutes en médiane",
      "Watch it climb": "Suivez la montée",
      "Every game appears on your order page with the result, the KDA and the LP swing. Pause it any time you want to play.":
        "Chaque partie apparaît sur votre page de commande avec le résultat, le KDA et l'écart de LP. Mettez en pause dès que vous voulez jouer.",
      "Updated as games finish": "Mis à jour à la fin de chaque partie",
      "Finished, or refunded": "Livrée, ou remboursée",
      "Delivered to the rank you set. Anything not delivered is refunded pro-rata, any time the order is open.":
        "Livrée au rang que vous avez fixé. Tout ce qui ne l'est pas est remboursé au prorata, à tout moment tant que la commande est ouverte.",
      "Back within 5 business days": "Remboursé sous 5 jours ouvrés",

      /* 02 While it runs */
      "While it runs": "Pendant la commande",
      "Watch every game land.": "Voyez chaque partie tomber.",
      "The order page opens from the link we email you — no password, no app. It updates as games finish, so you never have to ask where things are.":
        "La page de commande s'ouvre depuis le lien que nous vous envoyons par e-mail — sans mot de passe, sans application. Elle se met à jour à la fin de chaque partie : vous n'avez jamais à demander où en sont les choses.",
      "The LP graph, not a percentage": "La courbe de LP, pas un pourcentage",
      "The RR graph, not a percentage": "La courbe de RR, pas un pourcentage",
      "Every game plotted from the rank you started at, so a bad night is visible instead of averaged away.":
        "Chaque partie tracée depuis votre rang de départ : une mauvaise soirée se voit au lieu d'être noyée dans une moyenne.",
      "Match history with replays": "Historique des parties avec replays",
      "Result, KDA and LP for every game, each with a replay link that stays live for 14 days.":
        "Résultat, KDA et LP pour chaque partie, avec un lien de replay actif pendant 14 jours.",
      "Result, KDA and RR for every game, each with a replay link that stays live for 14 days.":
        "Résultat, KDA et RR pour chaque partie, avec un lien de replay actif pendant 14 jours.",
      "One thread with your booster": "Un seul fil avec votre booster",
      "Ask for a champion, a pause or a swap. Support reads the same thread, so nothing gets repeated.":
        "Demandez un champion, une pause ou un changement. Le support lit le même fil : rien n'est à répéter.",
      "games this order": "parties sur cette commande",

      /* 03 Who plays it */
      "Who plays it": "Qui y joue",
      "Rank verified every month": "Rang vérifié chaque mois",
      "One free swap, no reason needed": "Un changement gratuit, sans justification",

      /* 04 Safety */
      "Why this doesn't get you banned.": "Pourquoi cela ne vous fait pas bannir.",
      "Enterprise VPN matched to your region": "VPN professionnel dans votre région",
      "Not a consumer VPN, and never a datacentre IP.":
        "Pas un VPN grand public, et jamais une IP de centre de données.",
      "Your sensitivity, your crosshair, your runes": "Votre sensibilité, votre viseur, vos runes",
      "Settings are mirrored at the start and restored at the end.":
        "Vos réglages sont reproduits au début et rétablis à la fin.",
      "You set the window at checkout. Nothing runs at 04:00 unless you do.":
        "Vous fixez la plage horaire au paiement. Rien ne tourne à 4 h du matin sauf si c'est votre choix.",
      "Offline appearance for the whole order": "Statut hors ligne pendant toute la commande",
      "Friends see you offline until it finishes.": "Vos amis vous voient hors ligne jusqu'à la fin.",
      "In duo your booster queues beside you from their own account.":
        "En duo, votre booster fait la file à côté de vous depuis son propre compte.",

      /* 05 Reviews */
      "Read them all": "Lire tous les avis",

      /* 06 FAQ */
      "If yours isn't here, Discord answers in about four minutes and you don't need an order to ask.":
        "Si la vôtre n'y est pas, Discord répond en quatre minutes environ et vous n'avez pas besoin d'une commande pour poser la question.",
      "Do you need my account login?": "Avez-vous besoin de mes identifiants ?",
      "For solo, yes — your booster signs in and plays, through a VPN in your region and inside the hours you set. For duo, no: they queue beside you from their own account and never see your login at all. Either way we never ask for your email password or your 2FA codes.":
        "En solo, oui — votre booster se connecte et joue, via un VPN dans votre région et dans les horaires que vous fixez. En duo, non : il fait la file à côté de vous depuis son propre compte et ne voit jamais vos identifiants. Dans les deux cas, nous ne demandons jamais le mot de passe de votre e-mail ni vos codes 2FA.",
      "Can I play while the order is running?": "Puis-je jouer pendant la commande ?",
      "What happens if it goes past the estimate?": "Que se passe-t-il en cas de dépassement du délai ?",
      "A 15% credit applies automatically once the order runs past its window, and it shows on the order page without anyone asking. If it is badly over, we move it to a booster who is free.":
        "Un avoir de 15 % s'applique automatiquement dès qu'une commande dépasse sa fenêtre, et il apparaît sur la page de commande sans rien demander. En cas de retard important, nous la confions à un booster disponible.",
      "Why is duo more expensive?": "Pourquoi le duo coûte-t-il plus cher ?",
      "It takes longer. Your booster carries a live player rather than playing every role freely, so the same climb costs 55% more and takes longer. It is the safer option and we would rather price it honestly than hide the difference.":
        "Parce que c'est plus long. Votre booster porte un joueur en direct au lieu de jouer chaque rôle librement : la même montée coûte 55 % de plus et prend plus de temps. C'est l'option la plus sûre, et nous préférons l'afficher honnêtement plutôt que masquer l'écart.",
      "How do I follow the order without an account?": "Comment suivre la commande sans compte ?",
      "The confirmation email carries a link that is the login. It never expires, works on any device, and opens the same dashboard shown above. Lost it? The demo page resends it to the address you paid with.":
        "L'e-mail de confirmation contient un lien qui tient lieu de connexion. Il n'expire jamais, fonctionne sur tous les appareils et ouvre le tableau de bord montré ci-dessus. Perdu ? La page de démo le renvoie à l'adresse utilisée pour le paiement.",
      "Can I choose the champions they play?": "Puis-je choisir les champions qu'il joue ?",
      "Can I choose the agents they play?": "Puis-je choisir les agents qu'il joue ?",
      "Can I choose the roles they play?": "Puis-je choisir les rôles qu'il joue ?",
      "Can I choose the playlist they play?": "Puis-je choisir la playlist qu'il joue ?",

      /* the hero lede, one per ladder */
      "Solo/duo and flex, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Solo/duo et flex, sur NA et EU. Votre booster joue votre compte dans vos horaires habituels avec un VPN régional, ou fait la file à côté de vous en duo sans jamais toucher à vos identifiants.",
      "Competitive and unrated, across NA and EU. Your booster plays your account inside your normal hours with a regional VPN, or queues beside you in duo and never touches the login at all.":
        "Compétitif et non classé, sur NA et EU. Votre booster joue votre compte dans vos horaires habituels avec un VPN régional, ou fait la file à côté de vous en duo sans jamais toucher à vos identifiants.",
      "Premier CS Rating and Faceit levels, run by FPL-adjacent players. Anti-cheat safe patterns, no smurf stacking, no rating farm scripts.":
        "CS Rating Premier et niveaux Faceit, assurés par des joueurs proches du FPL. Des schémas sans risque pour l'anti-triche, pas d'empilement de smurfs, pas de scripts de farm de rating.",
      "1v1, 2v2 and 3v3 playlists, tournament wins, and duo sessions where the booster calls rotations live on voice.":
        "Playlists 1c1, 2c2 et 3c3, victoires en tournoi, et sessions duo où le booster annonce les rotations en direct sur vocal.",

      /* the bundle strip */
      "Save big on bundles": "Économisez gros sur les packs",
      "Whole-ladder climbs at one flat price": "Des montées d'échelle entière à prix fixe",
      "Two tiers up in one order, from wherever you are":
        "Deux paliers de plus en une commande, d'où que vous partiez",
      "Two rating bands up in one order": "Deux tranches de rating de plus en une commande",
      "Up to {}% off": "Jusqu'à −{} %",
      /* "Depuis n'importe quelle division {}" is the natural phrasing and it
         wrapped to a second line on a 216px bundle card where the English fits
         on one, leaving one card in the row of three taller than its
         neighbours. Shortened to fit the card it actually ships in. */
      "From any {} division": "Depuis toute division {}",
      "Starts at {}": "À partir de {}",
      "Apply bundle": "Appliquer le pack",
      "Applied": "Appliqué",
      "Played in your preferred hours": "Joué à vos heures préférées",

      /* net wins / placements */
      "per game": "par partie",
      "A net win means one win above your losses — five is the cap per order.":
        "Une victoire nette, c'est une victoire de plus que vos défaites — cinq au maximum par commande.",
      "A placement game sets or resets your rank — five is the cap per order.":
        "Une partie de placement fixe ou réinitialise votre rang — cinq au maximum par commande.",
      "I have a rank": "J'ai un rang",
      "Unranked": "Non classé",
      "Fresh account or a new season — no MMR to read yet. Your booster plays all five and the rank you land is the rank you keep.":
        "Compte neuf ou nouvelle saison — aucun MMR à lire pour l'instant. Votre booster joue les cinq parties et le rang obtenu est celui que vous gardez.",

      /* coaching */
      "Pick your coach": "Choisissez votre coach",
      "How many hours": "Combien d'heures",
      "What to work on": "Sur quoi travailler",
      "First session": "Première session",
      "per hour": "de l'heure",
      "Single session": "Session unique",
      "Save {}%": "−{} %",
      "Laning": "Phase de lane",
      "Macro & rotations": "Macro et rotations",
      "Champion pool": "Pool de champions",
      "VOD review": "Analyse de VOD",
      "coaches taking bookings": "coachs prennent des réservations",
      "taking bookings": "prend des réservations",
      "Live on Discord, screen shared, recorded for you to keep.":
        "En direct sur Discord, écran partagé, enregistré et gardé pour vous.",

      /* ── the support page ─────────────────────────────────────────────── */
      "Two ways in. Both are read by people.": "Deux entrées. Les deux sont lues par des humains.",
      "Staffed right now": "Équipe présente en ce moment",
      "— someone is in #support": "— quelqu'un est dans #support",
      "Median first reply": "Premier retour médian",
      "Open 24/7": "Ouvert 24/7",
      "Attachments and receipts welcome": "Pièces jointes et reçus bienvenus",
      "Copy address": "Copier l'adresse",
      "Write in": "Écrivez-nous",
      "Or write it here": "Ou écrivez-le ici",
      "What to put in it": "Ce qu'il faut y mettre",
      "The order number": "Le numéro de commande",
      "Anything starting ESB-. It skips triage and lands with the person on that order.":
        "Tout ce qui commence par ESB-. Cela évite le tri et arrive directement chez la personne en charge de la commande.",
      "What you expected": "Ce que vous attendiez",
      "The rank, the date, the thing the checkout said you were buying.":
        "Le rang, la date, ce que le paiement disait que vous achetiez.",
      "What actually happened": "Ce qui s'est réellement passé",
      "Screenshots beat descriptions. Paste them straight into the thread.":
        "Une capture vaut mieux qu'une description. Collez-la directement dans le fil.",
      "Nothing else": "Rien d'autre",
      "No passwords, no 2FA codes. Support will never ask for one, and won't act on a message that contains one.":
        "Pas de mots de passe, pas de codes 2FA. Le support n'en demandera jamais et ne traitera pas un message qui en contient un.",
      "What's it about": "De quoi s'agit-il",
      "Order issue": "Problème de commande",
      "Refund": "Remboursement",
      "Booster swap": "Changement de booster",
      "Before I buy": "Avant d'acheter",
      "Something else": "Autre chose",
      "Company": "Société",
      "One thread per message. Discord and email land in the same place, so pick either — not both.":
        "Un fil par message. Discord et l'e-mail arrivent au même endroit : choisissez l'un ou l'autre, pas les deux.",
      "Add an email we can reply to, and a line or two about what happened.":
        "Ajoutez un e-mail auquel répondre, et une ligne ou deux sur ce qui s'est passé.",
      "We never ask for your game password here, or anywhere else.":
        "Nous ne demandons jamais le mot de passe de votre jeu, ni ici ni ailleurs.",
      "Six answers that between them close most of the tickets we get. If yours isn't here, Discord is two clicks away.":
        "Six réponses qui règlent à elles seules la plupart de nos tickets. Si la vôtre n'y est pas, Discord est à deux clics.",
      "Where is my order? I never made an account.":
        "Où est ma commande ? Je n'ai jamais créé de compte.",
      "You do not need one. Guest orders are tracked by the link we emailed when you paid — it never expires and works on any device. Lost it? Open the order lookup, enter the address you paid with, and we send it again.":
        "Vous n'en avez pas besoin. Les commandes invité se suivent avec le lien envoyé par e-mail au moment du paiement — il n'expire jamais et fonctionne sur tous les appareils. Perdu ? Ouvrez la recherche de commande, saisissez l'adresse utilisée pour le paiement et nous le renvoyons.",
      "Nobody has claimed my order yet.": "Personne n'a encore pris ma commande.",
      "Median claim time is 18 min, and most of the rest go within the hour. If nothing has claimed it 24 hours after payment, the order refunds itself automatically — no ticket, no asking. Writing in before that does not move it up the board.":
        "Le délai médian de prise en charge est de 18 min, et la plupart des autres partent dans l'heure. Si rien ne l'a prise 24 heures après le paiement, la commande se rembourse automatiquement — sans ticket, sans démarche. Nous écrire avant cela ne la fait pas remonter sur le tableau.",
      "Can I get a refund?": "Puis-je être remboursé ?",
      "In full, any time before a booster claims it. After that it is pro-rated on what has not been delivered — you keep the divisions already climbed and get the rest back. Money lands on the original payment method within 5 business days.":
        "Intégralement, à tout moment avant qu'un booster ne la prenne. Ensuite, c'est au prorata de ce qui n'a pas été livré — vous gardez les divisions déjà gravies et le reste vous est rendu. L'argent revient sur le moyen de paiement d'origine sous 5 jours ouvrés.",
      "Can I swap to a different booster?": "Puis-je changer de booster ?",
      "Yes, once per order, at no charge. Ask in the order thread. The order goes back on the board and is usually re-claimed the same day; if you would rather not say why, do not — we do not ask.":
        "Oui, une fois par commande et sans frais. Demandez-le dans le fil de la commande. Elle retourne sur le tableau et est généralement reprise le jour même ; si vous préférez ne pas dire pourquoi, ne le dites pas — nous ne le demandons pas.",
      "Can I play on my account while an order is running?":
        "Puis-je jouer sur mon compte pendant une commande ?",
      "My order is past the delivery estimate.": "Ma commande a dépassé le délai annoncé.",
      "A 15% credit applies automatically once an order runs past its window, and it shows on the order page without anyone having to ask. If it is badly over, write in and we will move it to a booster who is free.":
        "Un avoir de 15 % s'applique automatiquement dès qu'une commande dépasse sa fenêtre, et il apparaît sur la page de commande sans rien avoir à demander. En cas de retard important, écrivez-nous et nous la confierons à un booster disponible.",
      "Still stuck? Ask us.": "Toujours bloqué ? Écrivez-nous.",
      "Discord is the fast one — our staff sit in it all day. Or write in above and it lands in the same inbox.":
        "Discord est le plus rapide — notre équipe y est toute la journée. Ou écrivez-nous ci-dessus : cela arrive dans la même boîte.",
      "Ask us": "Écrivez-nous",

      /* ── the free-guides landing ──────────────────────────────────────── */
      "One for League, one for Valorant. Six chapters and six drills each, on the things that decide games between Silver and Ascendant. Written by the people on our roster who play those ranks every day.":
        "Un pour League, un pour Valorant. Six chapitres et six exercices chacun, sur ce qui décide les parties entre Silver et Ascendant. Écrits par les membres de notre effectif qui jouent ces rangs tous les jours.",
      "Win the lane you already won.": "Gagnez la lane que vous aviez déjà gagnée.",
      "Stop losing rounds you already won.": "Arrêtez de perdre les rounds que vous aviez gagnés.",
      "6 chapters · 6 drills": "6 chapitres · 6 exercices",
      "The League field guide": "Le guide de terrain League",
      "The Valorant field guide": "Le guide de terrain Valorant",
      "Iron to Diamond · wave control, roams, objectives":
        "D'Iron à Diamond · gestion des vagues, roams, objectifs",
      "Iron to Ascendant · crosshair, economy, retakes":
        "D'Iron à Ascendant · viseur, économie, retakes",
      ". If nothing lands in two minutes, look in promotions — it sometimes goes there first.":
        ". Si rien n'arrive en deux minutes, regardez dans les promotions — il y atterrit parfois d'abord.",
      "From the team behind": "De l'équipe derrière",
      "and 4.7 / 5 on Trustpilot.": "et 4,7 / 5 sur Trustpilot.",
      "Every chapter ends with a drill you can run in a custom game in under ten minutes. That is the whole format: read it, then do it.":
        "Chaque chapitre se termine par un exercice à faire en partie personnalisée en moins de dix minutes. C'est tout le format : on lit, puis on fait.",
      "Drill": "Exercice",
      "Wave control": "Gestion des vagues",
      "Freeze, slow-push, crash — and which one the minute demands.":
        "Freeze, slow-push, crash — et lequel la minute réclame.",
      "Trading, not fighting": "Échanger, pas combattre",
      "Why the lane is won by who spends time better, not who hits harder.":
        "Pourquoi la lane se gagne par celui qui emploie mieux son temps, pas par celui qui frappe le plus fort.",
      "Roams that pay": "Des roams rentables",
      "The three windows where leaving lane gains more than it costs.":
        "Les trois fenêtres où quitter la lane rapporte plus que cela ne coûte.",
      "Objectives as maths": "Les objectifs comme un calcul",
      "Dragon, herald and the setup that starts 40 seconds early.":
        "Dragon, héraut et la mise en place qui commence 40 secondes plus tôt.",
      "Six habits that cap your rank": "Six habitudes qui plafonnent votre rang",
      "Each with the tell you can spot in your own replays.":
        "Chacune avec l'indice repérable dans vos propres replays.",
      "Each with the tell you can spot in your own VODs.":
        "Chacune avec l'indice repérable dans vos propres VOD.",
      "The climb plan": "Le plan de montée",
      "Twelve ranked games a week, structured.": "Douze parties classées par semaine, structurées.",
      "Crosshair placement": "Placement du viseur",
      "Where the dot sits before you peek, not after.":
        "Où se trouve le point avant de peek, pas après.",
      "Economy you can trust": "Une économie fiable",
      "When to force, when to save, and why the half-buy loses.":
        "Quand forcer, quand économiser, et pourquoi le demi-achat perd.",
      "Retakes and the four-second rule": "Les retakes et la règle des quatre secondes",
      "Most retakes are lost before anyone shoots.":
        "La plupart des retakes sont perdus avant le premier tir.",
      "Utility that buys space": "Les utilitaires qui achètent de l'espace",
      "Smokes and flashes as currency.": "Smokes et flashs comme monnaie d'échange.",
      "Not a content team reading patch notes. Boosters from our own roster wrote a chapter each, and every claim is something they do in ranked that week — not theory borrowed from a pro scene you will never play in.":
        "Pas une équipe de contenu qui lit les notes de patch. Des boosters de notre propre effectif ont écrit un chapitre chacun, et chaque affirmation est quelque chose qu'ils font en classé cette semaine-là — pas de la théorie empruntée à une scène pro où vous ne jouerez jamais.",
      "From 1,100 readers": "Sur 1 100 lecteurs",
      "Is it actually free, or free-ish?": "Est-ce vraiment gratuit, ou presque gratuit ?",
      "Free. There is no card, no trial, and no upsell inside either PDF. We publish them because a player who improves is a player who stays in the game, and some of them buy a boost or a coaching hour later. That is the whole business case.":
        "Gratuit. Pas de carte, pas d'essai, aucune vente additionnelle dans les PDF. Nous les publions parce qu'un joueur qui progresse est un joueur qui reste, et que certains achètent un boost ou une heure de coaching plus tard. Voilà tout le modèle.",
      "Can I take both?": "Puis-je prendre les deux ?",
      "Yes, and most people do — both are ticked by default. They arrive as two attachments in one email, so taking the second one costs you nothing extra, not even another form.":
        "Oui, et la plupart le font — les deux sont cochés par défaut. Ils arrivent en deux pièces jointes dans un seul e-mail : prendre le second ne coûte rien de plus, pas même un autre formulaire.",
      "What do you do with my email?": "Que faites-vous de mon e-mail ?",
      "Send you the guides. If you tick the box, one email a month with new guides and patch notes. We never sell or rent the list, and one click unsubscribes — the link is in every email, not buried in a preference centre.":
        "Vous envoyer les guides. Si vous cochez la case, un e-mail par mois avec les nouveaux guides et les notes de patch. Nous ne vendons ni ne louons jamais la liste, et un clic suffit pour se désabonner — le lien est dans chaque e-mail, pas enfoui dans un centre de préférences.",
      "What rank are these written for?": "Pour quel rang sont-ils écrits ?",
      "Iron through Diamond for League, Iron through Ascendant for Valorant. The early chapters do most of the work at lower ranks; the habit and objective chapters matter more once you are past Platinum.":
        "D'Iron à Diamond pour League, d'Iron à Ascendant pour Valorant. Les premiers chapitres font l'essentiel du travail aux rangs bas ; les chapitres sur les habitudes et les objectifs comptent davantage une fois Platinum passé.",
      "Do I need to buy boosting to use them?": "Dois-je acheter un boost pour les utiliser ?",
      "No, and neither guide mentions our services beyond one line on the last page. If you would rather someone else did the climbing, that is a different page on this site — this one is for doing it yourself.":
        "Non, et aucun des deux guides ne mentionne nos services au-delà d'une ligne en dernière page. Si vous préférez que quelqu'un d'autre fasse la montée, c'est une autre page de ce site — celle-ci est pour la faire vous-même.",

      /* ── homepage, checkout and the odds and ends ─────────────────────── */
      "Know your exact price in seconds. A verified booster claims your order in about 18 minutes — and until one does, every cent is refundable.":
        "Votre prix exact en quelques secondes. Un booster vérifié prend votre commande en 18 minutes environ — et tant que personne ne l'a prise, chaque centime est remboursable.",
      "Best Sellers": "Meilleures ventes",
      "Fast checkout": "Paiement rapide",
      "You are here": "Vous êtes ici",
      "You are here tier": "Palier où vous êtes",
      "You want to be": "Vous visez",
      "You want to be tier": "Palier visé",
      "Your region": "Votre région",
      "Nine games": "Neuf jeux",
      "Start an order": "Lancer une commande",
      "Ask in Discord": "Demander sur Discord",
      "Median first reply on Discord last month: 3m 40s.":
        "Premier retour médian sur Discord le mois dernier : 3 min 40 s.",
      "with vantaa": "avec vantaa",
      "Duo queue · +55%": "File duo · +55 %",
      "SPLIT15 takes 15% off the whole catalogue with nothing to type. Each game page also carries bundle climbs at 19% to 37% off, and a bundle replaces the code rather than adding to it — there is only ever one discount on an order, and it is the larger of the two.":
        "SPLIT15 retire 15 % sur tout le catalogue sans rien à saisir. Chaque page de jeu propose aussi des packs de montée à −19 % à −37 %, et un pack remplace le code au lieu de s'y ajouter — il n'y a jamais qu'une seule remise par commande, et c'est la plus avantageuse des deux.",

      /* The roster line is split around its <b>count</b>, so it is two nodes and
         each needs its own entry — the figure never enters the dictionary. */
      "more {} boosters": "boosters {} de plus",
      "more {} booster": "booster {} de plus",
      "on the roster, all {} or above.": "sur le tableau, tous {} ou au-dessus.",
      "on Trustpilot · {} reviews": "sur Trustpilot · {} avis",
      "{} reviews on Trustpilot": "{} avis sur Trustpilot",
      "· {} reviews": "· {} avis",
      /* The capture is the game's own picks add-on, which is already a key
         above ("Champions & roles"), so patTranslate()'s lookup renders the
         French name inside the French sentence. ⚠ the English source reads
         "Yes — It is free", a stray capital from the way build.py joins the
         clause; the French is written correctly rather than reproducing it. */
      "Yes — It is free on every order, not an upsell — \"{}\" is ticked before you configure anything. Your booster plays a pool you pick, which also keeps the match history plausible, and you can change it mid-order in the thread.":
        "Oui — c'est gratuit sur chaque commande, pas une option payante : « {} » est coché avant même que vous ne configuriez quoi que ce soit. Votre booster joue un pool que vous choisissez, ce qui rend aussi l'historique de parties plausible, et vous pouvez le modifier en cours de commande dans le fil.",
      "Pause it first, from the order page. Pausing is free and resumes the same night if a slot is open. What you should not do is queue ranked alongside an unpaused solo order — two people on one account in the same queue is the fastest way to get flagged.":
        "Mettez-la d'abord en pause, depuis la page de commande. La pause est gratuite et la reprise se fait le soir même si un créneau est libre. Ce qu'il ne faut pas faire, c'est lancer une partie classée en parallèle d'une commande solo non mise en pause — deux personnes sur un compte dans la même file, c'est le moyen le plus rapide de se faire repérer.",

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
      "Rocket League, Apex Legends and Counter-Strike 2":
        "Rocket League, Apex Legends et Counter-Strike 2",
      "3m 40s": "3 min 40 s"
    },

    de: {
      /* dynamic fragments emitted by app.js */
      "Solo": "Solo",
      "Duo queue": "Duo-Queue",
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
      "boosters on shift": "Booster im Dienst",
      "Median claim": "Übernahme im Median",
      "Watch orders land live": "Bestellungen live eintreffen sehen",
      "All nine games": "Alle neun Spiele",
      "Browse the roster": "Das Team ansehen",
      "verified boosters, one game each": "verifizierte Booster, je ein Spiel",
      "Hire a specific booster": "Einen bestimmten Booster buchen",
      "Name one at checkout, no extra fee": "Beim Bezahlen benennen, ohne Aufpreis",
      "How we verify": "Wie wir prüfen",
      "Rank proof, trial orders, review floor": "Rangnachweis, Probebestellungen, Bewertungsgrenze",
      "Master+ with a clean account": "Master+ mit sauberem Account",
      "Read their reviews": "Ihre Bewertungen lesen",
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
      "An account with this email already exists. Log in instead.": "Ein Konto mit dieser E-Mail existiert bereits. Melde dich stattdessen an.",
      "Enter a valid email address.": "Gib eine gültige E-Mail-Adresse ein.",
      "Choose a password of at least 6 characters.": "Wähle ein Passwort mit mindestens 6 Zeichen.",
      "Please accept the terms to create your account.": "Bitte akzeptiere die Bedingungen, um dein Konto zu erstellen.",
      "Enter your password.": "Gib dein Passwort ein.",
      "Couldn't reach the server. Check your connection and try again.": "Server nicht erreichbar. Prüfe deine Verbindung und versuche es erneut.",
      "Couldn't create the account. Try again.": "Konto konnte nicht erstellt werden. Versuche es erneut.",
      "Sign-in didn't complete. Please try again.": "Die Anmeldung wurde nicht abgeschlossen. Bitte versuche es erneut.",
      "That email and password don't match. Check them, or create an account.": "E-Mail und Passwort passen nicht zusammen. Prüfe sie oder erstelle ein Konto.",
      "Social sign-in isn't connected yet. Use your email, or buy as a guest — checkout needs no account.":
        "Die Anmeldung über soziale Konten ist noch nicht angebunden. Nutze deine E-Mail oder kaufe als Gast — die Kasse braucht kein Konto.",
      "This is your store account, never your game login.":
        "Das ist dein Shop-Konto, nie dein Spiel-Login.",
      "We never ask for your game password here.":
        "Wir fragen hier nie nach deinem Spiel-Passwort.",
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
      "Every boost you've ordered \u2014 the one in progress, and the ones already delivered.": "Jeder Boost, den du bestellt hast — der laufende und die bereits gelieferten.",
      "Signed in as": "Angemeldet als",
      "You're viewing a sample history.": "Du siehst einen Beispielverlauf.",
      "to keep your orders in one place \u2014 or track a single order by the link we emailed you. Checkout never needs an account.": "um deine Bestellungen an einem Ort zu behalten — oder verfolge eine Bestellung über den Link aus unserer E-Mail. Die Kasse braucht nie ein Konto.",
      "This order history is a preview. Until an account backend is live, the orders shown are example data, priced with the real quote \u2014 the same standing as the demo dashboard.": "Dieser Bestellverlauf ist eine Vorschau. Solange kein Konto-Backend aktiv ist, sind die gezeigten Bestellungen Beispieldaten, mit dem echten Angebot berechnet — im selben Status wie das Demo-Dashboard.",
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
      "Follow along": "Folge uns",
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
      "Let's chat": "Los, chatten",
      "Visit help center": "Hilfecenter besuchen",
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
      "to climb": "zu erklimmen",
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
      "Total, tax included": "Gesamt, inkl. Steuern",
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
      "Watch a live boost": "Live-Boost ansehen",
      "Continue your order": "Bestellung fortsetzen",

      /* home hero — see the note on the French block above. */
      "verified boosters on shift right now": "verifizierte Booster jetzt im Dienst",
      "Pick your booster": "Wähle deinen Booster",
      "This month's #1": "Nr. 1 des Monats",
      "Verified": "Verifiziert",
      "orders delivered": "Bestellungen geliefert",
      "boosts delivered": "Boosts geliefert",
      "clients": "Kunden",
      "Clients served": "Betreute Kunden",
      "Clients": "Kunden",
      "Included": "Inklusive",

      /* add-ons — see the note on the French block above. */
      "Priority order": "Prioritäre Bestellung",
      "First in the claim queue, claimed in about 6 minutes.":
        "Ganz vorn in der Annahme-Warteschlange, angenommen in etwa 6 Minuten.",
      "First in the claim queue, about 6 minutes.":
        "Ganz vorn in der Warteschlange, etwa 6 Minuten.",
      "Solo only queue": "Nur Solo-Queue",
      "Your booster plays alone, in ranked only — no parties.":
        "Dein Booster spielt allein, nur Ranked — niemals in einer Gruppe.",
      "Plays alone, ranked only — no parties.":
        "Spielt allein, nur Ranked — keine Gruppen.",
      "Play on your schedule": "Spiel zu deinen Zeiten",
      "Fixed session times, held for the whole order.":
        "Feste Sitzungszeiten, für die ganze Bestellung reserviert.",
      "Fixed times, held for the whole order.":
        "Feste Zeiten, für die ganze Bestellung reserviert.",
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
      "You choose the picks they play.":
        "Du wählst die gespielten Picks.",
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
      "Challenger 1042 LP · 78% WR · EUW · 214 orders": "Challenger 1042 LP · 78 % WR · EUW · 214 Bestellungen",
      "Top booster of the month, vantaa": "Top-Booster des Monats, vantaa",

      /* marquee */
      "92,400 boosts delivered": "92.400 Boosts geliefert",
      "4.8 / 5 on Trustpilot — 3,140 reviews": "4,8 / 5 auf Trustpilot — 3.140 Bewertungen",
      "Most orders claimed within 18 min": "Meiste Aufträge in 18 Min. angenommen",
      "3,000 players in the Discord": "3.000 Spieler im Discord",
      "100% recovery rate on account reviews": "100 % Erfolgsquote bei Konto-Prüfungen",

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
      "K / D / A": "K / T / A",
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
      "Queue · Server": "Warteschlange · Server",
      "Money-back guarantee": "Geld zurück",

      /* stat band + roster */
      "Boosts delivered": "Boosts geliefert",
      "Trustpilot · 3,140 reviews": "Trustpilot · 3.140 Bewertungen",
      "Median time to claim": "Mediane Zeit bis zur Annahme",
      "Players in the Discord": "Spieler im Discord",
      "On shift now —": "Jetzt im Dienst —",
      "in the Discord": "im Discord",
      "Free VOD reviews on Sundays, scrim pickups, and the booster application queue.":
        "Kostenlose VOD-Analysen sonntags, Scrims und die Booster-Bewerbungsschlange.",
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
      "win rate": "Siegrate",
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
      "A booster claims it, usually inside 20 minutes": "Ein Booster nimmt sie an, meist in unter 20 Minuten",
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
      "Chat with the booster, not a queue": "Chatte mit dem Booster, nicht mit einer Warteschlange",
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
      "What if I want to play while the boost is running?": "Was, wenn ich während des Boosts spielen will?",
      "Pause it from the dashboard. The account is free within minutes and the timer stops. Resume when you're done.":
        "Pausiere ihn im Dashboard. Das Konto ist in Minuten frei und der Timer stoppt. Setze fort, wenn du fertig bist.",
      "What exactly is refunded, and when?": "Was genau wird erstattet, und wann?",
      "In full, no questions, until a booster claims the order. After that, pro-rated on the part that hasn't been delivered — divisions not climbed, wins not won. Refunds are issued to the original payment method within 5 business days.":
        "Voll, ohne Rückfragen, bis ein Booster die Bestellung annimmt. Danach anteilig auf den nicht gelieferten Teil — nicht erklommene Divisionen, nicht errungene Siege. Rückerstattungen erfolgen innerhalb von 5 Werktagen auf das ursprüngliche Zahlungsmittel.",
      "Solo or duo — which should I pick?": "Solo oder Duo — was soll ich wählen?",
      "Solo is faster and cheaper: the booster plays alone. Duo means you play every game with them, nobody logs into your account, and it costs 55% more for the extra time.":
        "Solo ist schneller und günstiger: Der Booster spielt allein. Duo heißt, du spielst jedes Spiel mit ihm, niemand meldet sich bei deinem Konto an, und es kostet 55 % mehr für die zusätzliche Zeit.",
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
      "it's out of your hands": "ist es aus deinen Händen",
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
        "Jeder Titel verkauft die ersten drei. Wenn du unsicher bist, lies die Zeile „Ideal für\" — sie ist meist die ganze Antwort.",
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
      "Three steps, then it's out of your hands": "Drei Schritte, dann ist es nicht mehr deine Sache",
      "Same dashboard on all nine titles. It opens from the link we email you — no password, no app — and updates as games finish.":
        "Dasselbe Dashboard bei allen neun Titeln. Es öffnet sich über den Link, den wir dir per E-Mail schicken — ohne Passwort, ohne App — und aktualisiert sich, sobald Spiele enden.",
      "Asked on this page": "Auf dieser Seite gefragt",
      "Title-specific questions live on each game's page. These are the ones about all nine.":
        "Titelspezifische Fragen stehen auf der jeweiligen Spielseite. Hier geht es um alle neun.",
      "Are these all the titles you cover?": "Sind das alle Titel, die ihr abdeckt?",
      "These nine are the ones with a live board and enough boosters to claim an order quickly. We take one-off requests on other titles in Discord, but there is no page and no instant price for them — if the queue cannot claim it, we say so rather than take the money.":
        "Diese neun haben ein aktives Board und genug Booster, um eine Bestellung schnell zu übernehmen. Einzelanfragen zu anderen Titeln nehmen wir über Discord an, aber es gibt dafür keine Seite und keinen Sofortpreis — wenn die Warteschlange sie nicht übernehmen kann, sagen wir das, statt das Geld zu nehmen.",
      "Why is Valorant cheaper than Counter-Strike 2?": "Warum ist Valorant günstiger als Counter-Strike 2?",
      "A division is not the same amount of work in every game. Ladders are different lengths, matches are different lengths, and one rung near the top of a ladder can cost several near the bottom of another. Each title carries its own multiplier, and it is on screen before you sign in: the cheapest single division is $3 on Valorant and $9 on Counter-Strike 2.":
        "Eine Division bedeutet nicht in jedem Spiel gleich viel Arbeit. Leitern sind unterschiedlich lang, Matches ebenso, und eine Sprosse nahe der Spitze einer Leiter kann so viel kosten wie mehrere am unteren Ende einer anderen. Jeder Titel hat seinen eigenen Multiplikator, und er steht vor der Anmeldung auf dem Bildschirm: die günstigste einzelne Division kostet 3 $ bei Valorant und 9 $ bei Counter-Strike 2.",
      "Does one booster cover several games?": "Deckt ein Booster mehrere Spiele ab?",
      "No. Everyone on the board plays exactly one title, and their profile carries the peak rank, the win rate, the on-time record and the orders they have delivered on it. Somebody claiming three ladders at once is somebody we did not hire.":
        "Nein. Jede Person auf dem Board spielt genau einen Titel, und ihr Profil zeigt den Höchstrang, die Siegquote, die Pünktlichkeit und die gelieferten Bestellungen. Wer drei Leitern gleichzeitig für sich beansprucht, ist jemand, den wir nicht eingestellt haben.",
      "Can I order two titles at once?": "Kann ich zwei Titel gleichzeitig bestellen?",
      "Yes, as two orders — each gets its own booster, price and dashboard. There is no cross-title bundle, because a discount spanning two boosters would be paying one of them less.":
        "Ja, als zwei Bestellungen — jede mit eigenem Booster, eigenem Preis und eigenem Dashboard. Ein titelübergreifendes Bundle gibt es nicht, denn ein Rabatt über zwei Booster hinweg hieße, einen von beiden schlechter zu bezahlen.",
      "Do prices change during a sale?": "Ändern sich die Preise während eines Sales?",
      "SPLIT15 takes 15% off the whole catalogue with nothing to type. Each game page also carries bundle climbs at 22% to 35% off, and a bundle replaces the code rather than adding to it — there is only ever one discount on an order, and it is the larger of the two.":
        "SPLIT15 zieht 15 % vom gesamten Katalog ab, ohne dass du etwas eingeben musst. Jede Spielseite führt außerdem Bundle-Aufstiege mit 22 % bis 35 % Rabatt, und ein Bundle ersetzt den Code, statt sich dazuzuaddieren — es gibt immer nur einen Rabatt pro Bestellung, und zwar den größeren von beiden.",
      "Nine titles, one guarantee.": "Neun Titel, eine Garantie.",
      "Refunded in full until a booster claims it, pro-rated after that, and claimed in 18 min on average.":
        "Volle Erstattung, bis ein Booster übernimmt, danach anteilig — im Schnitt in 18 Min. übernommen.",
      "Start with League": "Mit League starten",

      /* game page */
      "Home": "Startseite",
      "Breadcrumb": "Brotkrümelnavigation",
      "boosters free now": "Booster jetzt frei",
      "online": "online",
      "orders,": "Bestellungen,",
      "in players' words": "in den Worten der Spieler",
      "Questions people": "Fragen, die man",
      "ask before paying": "vor dem Zahlen stellt",
      "Ask us instead": "Frag stattdessen uns",
      "On shift now": "Jetzt im Dienst",

      /* booster table */
      "Booster": "Booster",
      "Game": "Spiel",
      "Peak": "Höchstrang",
      "Win rate": "Siegrate",
      "Queue": "Queue",
      "Every booster is trialled live before onboarding and reviewed monthly. Ranks shown are verified from match history, not self-reported.":
        "Jeder Booster wird vor dem Onboarding live getestet und monatlich überprüft. Die angezeigten Ränge sind aus dem Spielverlauf verifiziert, nicht selbst angegeben.",

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
      "62% win-rate floor, checked monthly": "62 % Mindest-Siegrate, monatlich geprüft",
      "Ranks read from the game API": "Ränge aus der Spiel-API gelesen",
      "Trial games recorded and reviewed": "Testspiele aufgezeichnet und ausgewertet",
      "Applications open in the": "Bewerbungen laufen über die",
      "queue": "Warteschlange",
      "players in there.": "Spieler sind dort.",
      "Join": "Beitreten",
      "on the board": "im Kader",
      "free right now": "gerade frei",
      "Availability": "Verfügbarkeit",
      "Everyone": "Alle",
      "Free now": "Jetzt frei",
      "Sort by": "Sortieren nach",
      "Free first": "Frei zuerst",
      "Game · Server": "Spiel · Server",
      "Peak this season": "Höchstrang diese Saison",
      "Win rate · 30d": "Siegrate · 30 T",
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
      "in the queue": "in der Warteschlange",
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
      "See the roster": "Kader ansehen",
      "See all": "Alle ansehen",
      "day": "Tag",
      "Request": "Anfrage:",
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
        "Jeder Bewerber wird live auf unserem Konto getestet, bevor er deins berührt: fünf Spiele, beobachtet, in der angegebenen Liga. Die Ränge auf dieser Seite werden aus der API gelesen, nicht in ein Formular getippt. Wessen Siegrate über einen laufenden Monat unter 62 % fällt, verlässt den Kader, bis er sie wieder hochspielt.",
      "Apply as a booster": "Als Booster bewerben",
      "Roster": "Kader",
      "Everyone on shift": "Alle im Dienst",
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
      "100% back, no reason asked": "100 % zurück, ohne Begründung",
      "One button in the order page. The money is back on the original payment method within 5 business days, and nobody will email you to ask why.":
        "Ein Knopf auf der Bestellseite. Das Geld ist innerhalb von 5 Werktagen auf dem ursprünglichen Zahlungsmittel zurück, und niemand mailt dir, um nach dem Grund zu fragen.",
      "Started but unfinished": "Begonnen, aber unfertig",
      "Pro-rated on what wasn't delivered": "Anteilig auf das, was nicht geliefert wurde",
      "Divisions not climbed and wins not won are refunded at the same rate you paid for them. Gold → Diamond stopped at Platinum returns the Platinum → Diamond portion, calculated by the same formula that quoted you.":
        "Nicht erklommene Divisionen und nicht errungene Siege werden zum selben Satz erstattet, den du gezahlt hast. Ein bei Platin gestopptes Gold → Diamant erstattet den Teil Platin → Diamant, berechnet mit derselben Formel, die dir den Preis nannte.",
      "Past the ETA": "Nach der ETA",
      "Your choice, and we tell you first": "Deine Wahl, und wir sagen es dir zuerst",
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back.":
        "Läuft eine Bestellung über ihr Lieferfenster hinaus, melden wir uns, bevor du es merkst: mit 15 % Gutschrift weitermachen, den Booster tauschen oder den unfertigen Teil zurücknehmen.",

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
        "Der Preis gilt pro überquerter Division, ein langer Aufstieg kostet also pro Stufe mehr als ein kurzer. Er wird an der Kasse fixiert: Der Betrag auf dem Knopf ist der Betrag, der abgebucht wird, und später kommt nichts dazu. Duo kostet 55 % mehr, weil der Booster einen zweiten Spieler trägt, und Extras werden vor der Zahlung einzeln ausgewiesen.",
      "Do I have to make an account to order?":
        "Muss ich ein Konto anlegen, um zu bestellen?",
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
      "Discord is quicker if you'd rather not wait.": "Discord ist schneller, wenn du nicht warten möchtest.",
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
      "Excellent": "Ausgezeichnet",
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
      "It never expires and works on any device":
        "Er läuft nie ab und funktioniert auf jedem Gerät",
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
      "Contacting payment…": "Zahlung wird kontaktiert…",
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
      "Used for the order link and nothing else. No marketing unless you tick the box at the end.":
        "Wird nur für den Bestell-Link verwendet, sonst nichts. Kein Marketing, außer du setzt am Ende das Häkchen.",
      "Preferred hours": "Bevorzugte Zeiten",
      "Any time": "Jederzeit",
      "My usual play hours (18:00–00:00)": "Meine üblichen Spielzeiten (18:00–00:00)",
      "While I'm at work (09:00–17:00)": "Während ich arbeite (09:00–17:00)",
      "Overnight only": "Nur über Nacht",
      "Anything the booster should know (optional)": "Etwas, das der Booster wissen sollte (optional)",
      "Champion pool, roles, don't touch ranked flex…": "Champion-Pool, Rollen, Ranked Flex nicht anfassen…",
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
      "Work here": "Arbeite hier",
      "Get paid": "Werde bezahlt",
      "for the queue": "für die Queue,",
      "you'd play anyway.": "die du eh spielen würdest.",
      "Payouts weekly, 70% of the order value on solo and 75% on duo, no deductions for the platform's payment fees. Pick your own shifts; take an order or don't. What we ask for is the rank, a clean account history, and that you never pass an account to anyone.":
        "Wöchentliche Auszahlungen, 70 % des Bestellwerts bei Solo und 75 % bei Duo, ohne Abzug der Zahlungsgebühren der Plattform. Wähle deine eigenen Schichten; nimm eine Bestellung an oder nicht. Wir verlangen den Rang, einen sauberen Konto-Verlauf und dass du nie ein Konto an jemanden weitergibst.",
      "Of the order, to you": "Der Bestellung, für dich",
      "Weekly": "Wöchentlich",
      "Payouts, no minimum": "Auszahlungen, kein Minimum",
      "5 games": "5 Spiele",
      "Live trial before onboarding": "Live-Test vor dem Onboarding",
      "In-game name": "Ingame-Name",
      "Peak rank": "Höchstrang",
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
      "the ladder.": "auf dem Ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Der Link ist tot oder die Seite wurde verschoben. Der Rechner ist so oder so zwei Klicks entfernt.",
      "Pick a game": "Spiel auswählen",
      "Back to the homepage": "Zurück zur Startseite",

      /* free guides landing — design_handoff_free_guides */
      "Free guides · no payment": "Kostenlose Guides · keine Zahlung",
      "Browse boosting": "Boosting ansehen",
      "Free guides": "Kostenlose Guides",
      "The two guides our boosters actually wrote.": "Die zwei Guides, die unsere Booster wirklich geschrieben haben.",
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
      "Enter an address we can send the PDFs to.": "Gib eine Adresse an, an die wir die PDFs senden können.",
      "Arrives in about a minute. No card, no account.": "Kommt in etwa einer Minute an. Keine Karte, kein Konto.",
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
      "Send them": "Schickt sie"
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
      if (!(store && a in store) && ANYDICT[core] !== 1) return;
      if (!store) { store = {}; ATTR_ORIG.set(el, store); }
      if (!(a in store)) store[a] = origVal;
      var out = origVal;
      if (lang !== "en") {
        var d = ESB_I18N[lang];
        if (d && d[core] !== undefined) out = d[core];
      }
      el.setAttribute(a, out);
    });
  }

  function applyLang(lang) {
    locale.lang = lang;
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
      if (!isNaN(n)) el.textContent = window.esbMoney(n, false);
    });
  }

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
        if (kind === "language") applyLang(val.toLowerCase());
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
    // locale.currency was already resolved against the language at parse time,
    // so a French visitor with no pick of their own arrives on EUR here.
    if (locale.currency !== "USD") applyCurrency(locale.currency);
    if (locale.lang !== "en") applyLang(locale.lang);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
