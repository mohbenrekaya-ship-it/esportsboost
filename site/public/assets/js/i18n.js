/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — client-side currency + language switcher
   ---------------------------------------------------------------------------
   Loaded BEFORE app.js so window.esbMoney / window.ESB_LOCALE exist when the
   runtime takes its first quote. Two independent dimensions, both persisted:

     currency : USD | EUR   (display only — the Stripe charge stays USD)
     language : en | fr | de

   Language is applied by walking the DOM and swapping any text node / attribute
   whose English source appears in ESB_I18N. Strings not in the dictionary fall
   back to English, so nothing ever breaks — it just stays untranslated.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var LKEY = "esb.locale.v1";

  /* ── persisted locale, read synchronously so app.js sees it ───────────── */
  var locale = { lang: "en", currency: "USD" };
  try {
    var raw = localStorage.getItem(LKEY);
    if (raw) {
      var s = JSON.parse(raw);
      if (s && (s.lang === "en" || s.lang === "fr" || s.lang === "de")) locale.lang = s.lang;
      if (s && (s.currency === "USD" || s.currency === "EUR")) locale.currency = s.currency;
    }
  } catch (e) {}
  window.ESB_LOCALE = locale;

  /* ── currency ─────────────────────────────────────────────────────────── */
  // Fixed display rate. The amount actually charged is recomputed server-side
  // in USD (pricing.py) — this only converts what the customer sees.
  window.ESB_RATES = { USD: 1, EUR: 0.92 };

  var LOCALE_TAG = { en: "en-US", fr: "fr-FR", de: "de-DE" };
  var EUR_TAG = { en: "en-IE", fr: "fr-FR", de: "de-DE" };
  var _fmtCache = {};
  function formatter(cur, lang, cents) {
    var tag = cur === "EUR" ? (EUR_TAG[lang] || "en-IE") : "en-US";
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
    return formatter(cur, locale.lang, cents).format(n * rate);
  };

  /* ── translation lookup, used by app.js for its dynamic strings ───────── */
  window.esbT = function (str) {
    if (locale.lang === "en") return str;
    var d = ESB_I18N[locale.lang];
    return (d && d[str] !== undefined) ? d[str] : str;
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
      "Pick a ladder": "Choisissez un classement",
      "Who plays your order": "Qui joue votre commande",
      "Before you buy": "Avant d'acheter",
      "Right now": "En ce moment",
      "Top": "N° 1",
      "Hiring": "Recrute",
      "are live too": "sont aussi en ligne",
      "boosters on shift": "boosters en service",
      "Median claim": "Prise en charge médiane",
      "Watch orders land live": "Voir les commandes arriver en direct",
      "All nine ladders": "Les neuf classements",
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
      "Re-enter your password": "Ressaisissez votre mot de passe.",
      "The passwords don't match.": "Les mots de passe ne correspondent pas.",
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
      "with": "avec",
      "Money-back until a booster is assigned": "Remboursé tant qu'aucun booster n'est assigné",
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
         so the sentences keep matching. "See vantaa profile" carries the
         booster's handle: changing data.py's SPOTLIGHT means adding the new
         sentence here too. */
      "verified boosters on shift right now": "boosters vérifiés en service maintenant",
      "This month's #1": "N°1 du mois",
      "Verified": "Vérifié",
      "orders delivered": "commandes livrées",
      "boosts delivered": "boosts livrés",
      "See vantaa profile": "Voir le profil de vantaa",
      "Included": "Inclus",

      /* add-ons */
      "Priority queue": "File prioritaire",
      "Pushed to the top of the board. Median claim drops to about 6 minutes.":
        "Placé en tête de liste. La prise médiane passe à environ 6 minutes.",
      "Specific champions, agents or heroes": "Champions, agents ou héros précis",
      "Your booster plays a pool you choose, so the match history stays plausible.":
        "Votre booster joue un pool que vous choisissez, pour un historique crédible.",
      "Streamed to you": "Diffusé pour vous",
      "A private stream link for every game, replayable for 14 days.":
        "Un lien de stream privé pour chaque partie, rejouable pendant 14 jours.",
      "Offline appearance": "Apparaître hors ligne",
      "Always on. Friends see you offline for the whole order — never an extra.":
        "Toujours actif. Vos amis vous voient hors ligne durant toute la commande — jamais en option payante.",

      /* hero (home) */
      "Verified boosters — since 2019": "Boosters vérifiés — depuis 2019",
      "The rank is yours.": "Le rang est à vous.",
      "The grind isn't.": "Le grind, non.",
      "Set two ranks. See the final price before you make an account. Then watch every match land from the dashboard — no bots, no shared logins, no invoice that moves after checkout.":
        "Fixez deux rangs. Voyez le prix final avant de créer un compte. Puis suivez chaque partie depuis le tableau de bord — sans bots, sans identifiants partagés, sans facture qui bouge après le paiement.",
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
      "Nine ladders.": "Neuf ladders.",
      "Thirty-seven services.": "Trente-sept services.",
      "Most ordered": "Le plus commandé",
      "Configure": "Configurer",
      "All games": "Tous les jeux",
      "ladders are live too.": "sont aussi en ligne.",
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
      "No account sharing on duo": "Aucun partage de compte en duo",
      "Open the demo dashboard": "Voir le tableau de bord de démo",
      "Preview of the order dashboard": "Aperçu du tableau de bord de commande",
      "complete": "terminé",
      "days left": "jours restants",
      "LP across the order": "LP sur toute la commande",
      "LP net": "LP net",
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
      "Your configuration": "Votre configuration",
      "Change": "Modifier",
      "Queue · Server": "File · Serveur",
      "Money-back": "Satisfait ou remboursé",

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
      "Recovery rate on account reviews": "Taux de récupération sur les vérifications de compte",
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
      "What we screen for": "Ce que nous vérifions",
      "Rank": "Rang",
      "Two brackets above yours": "Deux paliers au-dessus du vôtre",
      "Nobody is assigned an order inside their own bracket. The gap is what makes the win rate hold up over a long climb.":
        "Personne ne se voit attribuer une commande dans son propre palier. C'est cet écart qui maintient le taux de victoire sur une longue montée.",
      "Behaviour": "Comportement",
      "Clean account history": "Historique de compte propre",
      "No bans, no chat restrictions, no low behaviour score. A booster who gets your account reported is a booster who costs us the refund.":
        "Pas de bannissement, pas de restriction de chat, pas de score de comportement bas. Un booster qui fait signaler votre compte est un booster qui nous coûte le remboursement.",
      "Conduct": "Conduite",
      "One strike on account sharing": "Tolérance zéro sur le partage de compte",
      "Credentials never leave the order. A booster caught passing an account to anyone else is removed the same day and paid out nothing.":
        "Les identifiants ne quittent jamais la commande. Un booster surpris à transmettre un compte à un tiers est retiré le jour même et n'est pas payé.",

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
      "Across 92,400 completed orders the recovery rate on account reviews is 100%. If a boost triggers one, support files the appeal and the order is refunded in full while it runs. Your name, email and payment details are never shared with the booster.":
        "Sur 92 400 commandes terminées, le taux de récupération sur les vérifications de compte est de 100 %. Si un boost en déclenche une, le support dépose le recours et la commande est remboursée intégralement pendant la procédure. Votre nom, votre e-mail et vos données de paiement ne sont jamais communiqués au booster.",
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
      "Support files the appeal for you and the order is refunded in full while it runs, so you are never paying for an account you cannot use. Across 92,400 completed orders the recovery rate on reviews is 100%. Boosting still breaks every listed game's terms of service — the risk is reduced as far as it can be, not removed.":
        "Le support dépose le recours à votre place et la commande est remboursée intégralement pendant la procédure : vous ne payez jamais pour un compte inutilisable. Sur 92 400 commandes terminées, le taux de récupération sur les vérifications est de 100 %. Le boosting enfreint toujours les conditions d'utilisation de chaque jeu listé — le risque est réduit autant que possible, pas supprimé.",
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
      "Email — support@esportsboost.com": "E-mail — support@esportsboost.com",
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
      "Local preview — this form doesn't send anything.": "Aperçu local — ce formulaire n'envoie rien.",
      "Before you write in": "Avant de nous écrire",

      /* reviews page. The figures ride in their own nodes, so "4.8 / 5 across
         3,140 reviews" is three translatable words around two numbers. The
         rating segment says "Any" rather than the handoff's "All" because
         "All" is already taken by the roster rail's "All 187 reviews". */
      "reviews": "avis",
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
      "included — friends see you offline for the whole order.":
        "inclus — vos amis vous voient hors ligne pendant toute la commande.",
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

      /* 404 */
      "Error 404": "Erreur 404",
      "That page": "Cette page",
      "isn't on": "n'est pas",
      "the ladder.": "sur le ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Le lien est mort ou la page a été déplacée. Le calculateur est à deux clics dans tous les cas.",
      "Pick a game": "Choisir un jeu",
      "Back to the homepage": "Retour à l'accueil"
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
      "Pick a ladder": "Wähle eine Rangliste",
      "Who plays your order": "Wer deine Bestellung spielt",
      "Before you buy": "Bevor du kaufst",
      "Right now": "Gerade jetzt",
      "Top": "Nr. 1",
      "Hiring": "Sucht Verstärkung",
      "are live too": "sind ebenfalls live",
      "boosters on shift": "Booster im Dienst",
      "Median claim": "Übernahme im Median",
      "Watch orders land live": "Bestellungen live eintreffen sehen",
      "All nine ladders": "Alle neun Ranglisten",
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
      "Re-enter your password": "Passwort erneut eingeben",
      "The passwords don't match.": "Die Passwörter stimmen nicht überein.",
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
      "with": "mit",
      "Money-back until a booster is assigned": "Geld zurück, bis ein Booster zugewiesen ist",
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
      "This month's #1": "Nr. 1 des Monats",
      "Verified": "Verifiziert",
      "orders delivered": "Bestellungen geliefert",
      "boosts delivered": "Boosts geliefert",
      "See vantaa profile": "Profil von vantaa ansehen",
      "Included": "Inklusive",

      /* add-ons */
      "Priority queue": "Prioritäts-Queue",
      "Pushed to the top of the board. Median claim drops to about 6 minutes.":
        "Ganz nach oben auf dem Board. Die mediane Annahme sinkt auf etwa 6 Minuten.",
      "Specific champions, agents or heroes": "Bestimmte Champions, Agenten oder Helden",
      "Your booster plays a pool you choose, so the match history stays plausible.":
        "Dein Booster spielt einen von dir gewählten Pool, damit der Spielverlauf plausibel bleibt.",
      "Streamed to you": "Für dich gestreamt",
      "A private stream link for every game, replayable for 14 days.":
        "Ein privater Stream-Link für jedes Spiel, 14 Tage lang abspielbar.",
      "Offline appearance": "Offline erscheinen",
      "Always on. Friends see you offline for the whole order — never an extra.":
        "Immer aktiv. Freunde sehen dich während der gesamten Bestellung offline — nie ein Aufpreis.",

      /* hero (home) */
      "Verified boosters — since 2019": "Verifizierte Booster — seit 2019",
      "The rank is yours.": "Der Rang gehört dir.",
      "The grind isn't.": "Der Grind nicht.",
      "Set two ranks. See the final price before you make an account. Then watch every match land from the dashboard — no bots, no shared logins, no invoice that moves after checkout.":
        "Lege zwei Ränge fest. Sieh den Endpreis, bevor du ein Konto erstellst. Verfolge dann jedes Match im Dashboard — keine Bots, keine geteilten Logins, keine Rechnung, die sich nach der Kasse ändert.",
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
      "Nine ladders.": "Neun Ladders.",
      "Thirty-seven services.": "Siebenunddreißig Services.",
      "Most ordered": "Am häufigsten bestellt",
      "Configure": "Konfigurieren",
      "All games": "Alle Spiele",
      "ladders are live too.": "sind ebenfalls live.",
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
      "No account sharing on duo": "Kein Kontoteilen im Duo",
      "Open the demo dashboard": "Demo-Dashboard öffnen",
      "Preview of the order dashboard": "Vorschau des Bestell-Dashboards",
      "complete": "abgeschlossen",
      "days left": "Tage übrig",
      "LP across the order": "LP über die Bestellung",
      "LP net": "LP netto",
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
      "Your configuration": "Deine Konfiguration",
      "Change": "Ändern",
      "Queue · Server": "Warteschlange · Server",
      "Money-back": "Geld zurück",

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
      "Recovery rate on account reviews": "Wiederherstellungsquote bei Kontoprüfungen",
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
      "What we screen for": "Worauf wir prüfen",
      "Rank": "Rang",
      "Two brackets above yours": "Zwei Ligen über deiner",
      "Nobody is assigned an order inside their own bracket. The gap is what makes the win rate hold up over a long climb.":
        "Niemand bekommt eine Bestellung in seiner eigenen Liga zugewiesen. Dieser Abstand hält die Siegrate über einen langen Aufstieg stabil.",
      "Behaviour": "Verhalten",
      "Clean account history": "Sauberer Konto-Verlauf",
      "No bans, no chat restrictions, no low behaviour score. A booster who gets your account reported is a booster who costs us the refund.":
        "Keine Bans, keine Chat-Sperren, kein niedriger Verhaltenswert. Ein Booster, der dein Konto gemeldet bekommt, kostet uns die Rückerstattung.",
      "Conduct": "Konduite",
      "One strike on account sharing": "Null Toleranz beim Kontoteilen",
      "Credentials never leave the order. A booster caught passing an account to anyone else is removed the same day and paid out nothing.":
        "Zugangsdaten verlassen nie die Bestellung. Ein Booster, der ein Konto an jemand anderen weitergibt, wird noch am selben Tag entfernt und nicht bezahlt.",

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
      "Across 92,400 completed orders the recovery rate on account reviews is 100%. If a boost triggers one, support files the appeal and the order is refunded in full while it runs. Your name, email and payment details are never shared with the booster.":
        "Über 92.400 abgeschlossene Bestellungen liegt die Wiederherstellungsquote bei Kontoprüfungen bei 100 %. Löst ein Boost eine aus, legt der Support den Einspruch ein, und die Bestellung wird während des Verfahrens voll erstattet. Dein Name, deine E-Mail und deine Zahlungsdaten werden nie an den Booster weitergegeben.",
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
      "Support files the appeal for you and the order is refunded in full while it runs, so you are never paying for an account you cannot use. Across 92,400 completed orders the recovery rate on reviews is 100%. Boosting still breaks every listed game's terms of service — the risk is reduced as far as it can be, not removed.":
        "Der Support legt den Einspruch für dich ein, und die Bestellung wird während des Verfahrens voll erstattet — du zahlst also nie für ein Konto, das du nicht nutzen kannst. Über 92.400 abgeschlossene Bestellungen liegt die Wiederherstellungsquote bei Prüfungen bei 100 %. Boosting verstößt trotzdem gegen die Nutzungsbedingungen jedes gelisteten Spiels — das Risiko ist so weit wie möglich gesenkt, nicht beseitigt.",
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
      "Email — support@esportsboost.com": "E-Mail — support@esportsboost.com",
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
      "Local preview — this form doesn't send anything.": "Lokale Vorschau — dieses Formular sendet nichts.",
      "Before you write in": "Bevor du uns schreibst",

      /* reviews page — siehe den Kommentar im französischen Block. */
      "reviews": "Bewertungen",
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
      "included — friends see you offline for the whole order.":
        "inklusive — Freunde sehen dich während der ganzen Bestellung offline.",
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

      /* 404 */
      "Error 404": "Fehler 404",
      "That page": "Diese Seite",
      "isn't on": "steht nicht",
      "the ladder.": "auf dem Ladder.",
      "The link is dead or the page moved. The calculator is two clicks away either way.":
        "Der Link ist tot oder die Seite wurde verschoben. Der Rechner ist so oder so zwei Klicks entfernt.",
      "Pick a game": "Spiel auswählen",
      "Back to the homepage": "Zurück zur Startseite"
    }
  };

  /* union of all keys — marks a string as translatable on first encounter */
  var ANYDICT = {};
  ["fr", "de"].forEach(function (l) { for (var k in ESB_I18N[l]) ANYDICT[k] = 1; });

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
    var known = orig !== undefined || ANYDICT[core] === 1;
    if (!known) return;
    if (orig === undefined) ORIG.set(node, full);
    var out = coreRaw;
    if (lang !== "en") {
      var d = ESB_I18N[lang];
      if (d && d[core] !== undefined) out = d[core];
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

  function applyCurrency(cur) {
    locale.currency = cur;
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
        else applyCurrency(val);
        persist();
        syncDropdown(loc, kind);
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

    // apply stored preferences (currency first so esbRender picks up both)
    if (locale.currency !== "USD") applyCurrency(locale.currency);
    if (locale.lang !== "en") applyLang(locale.lang);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
