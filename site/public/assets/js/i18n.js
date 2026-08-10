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
      "No divisions": "Aucune division",
      "None": "Aucune",

      /* util bar / nav */
      "Currency": "Devise",
      "Language": "Langue",
      "34 boosters on shift": "34 boosters en service",
      "median claim 18 min": "prise médiane 18 min",
      "11 boosters free right now": "11 boosters libres maintenant",
      "34 boosters on shift · median claim 18 min · 11 boosters free right now · 41,000 players in the Discord":
        "34 boosters en service · prise médiane 18 min · 11 boosters libres maintenant · 41 000 joueurs sur le Discord",
      "Games": "Jeux",
      "Live": "En direct",
      "Boosters": "Boosters",
      "Safety": "Sécurité",
      "Reviews": "Avis",
      "Track my order": "Suivre ma commande",
      "Start an order": "Commander",
      "Menu": "Menu",
      "Skip to content": "Aller au contenu",

      /* footer */
      "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any of their subsidiaries. All trademarks, game titles, logos, and brand names are the property of their respective owners. eSports Boost provides independent gaming services and is not endorsed by or associated with any game publisher.":
        "Nous ne sommes affiliés ni à Riot Games, Inc., ni à Blizzard Entertainment, ni à Valve, ni à aucune de leurs filiales. Toutes les marques, titres de jeux, logos et noms de marque appartiennent à leurs propriétaires respectifs. eSports Boost fournit des services de jeu indépendants et n'est ni approuvé ni associé à un quelconque éditeur de jeux.",
      "Questions? Email us at": "Des questions ? Écrivez-nous à",
      "Legal": "Mentions légales",
      "24/7 Customer Support": "Support client 24/7",
      "Need help? Our support team is available anytime to assist you with your orders and questions.":
        "Besoin d'aide ? Notre équipe de support est disponible à tout moment pour vos commandes et vos questions.",
      "Let's Chat": "Discutons",
      "Visit Help Center": "Centre d'aide",
      "Privacy Policy": "Politique de confidentialité",
      "Terms of Service": "Conditions d'utilisation",
      "Refunds & Cancellations": "Remboursements et annulations",
      "Become a booster": "Devenir booster",
      "Discord": "Discord",
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
      "Verified boosters — 9 games — since 2019": "Boosters vérifiés — 9 jeux — depuis 2019",
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
      "18 min median time to a claimed order": "18 min de délai médian avant prise en charge",
      "41,000 players in the Discord": "41 000 joueurs sur le Discord",
      "100% recovery rate on account reviews": "100 % de récupération sur les examens de compte",

      /* section heads / home */
      "Nine ladders.": "Neuf ladders.",
      "Forty services.": "Quarante services.",
      "Every service is priced per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Chaque service est facturé à la division et affiché avant toute connexion. Placements, victoires nettes, coaching et duo sur chaque jeu.",
      "Delivered today": "Livré aujourd'hui",
      "Why this doesn't get you banned": "Pourquoi cela ne vous fait pas bannir",
      "You watch the whole thing": "Vous suivez tout du début à la fin",
      "Regional VPN": "VPN régional",
      "Pro-rated refunds": "Remboursements au prorata",
      "No account sharing on duo": "Aucun partage de compte en duo",
      "Order dashboard — live": "Tableau de bord de commande — en direct",
      "Order tracking dashboard with live match history": "Tableau de bord de suivi avec historique en direct",
      "What they said after": "Ce qu'ils ont dit après",
      "Verified orders only": "Commandes vérifiées uniquement",
      "Your climb starts at": "Votre montée commence à",
      "Final at checkout. Refunded in full until a booster claims it, pro-rated after that.":
        "Fixé au paiement. Remboursé intégralement jusqu'à la prise en charge, au prorata ensuite.",
      "Ready when you are": "Prêt quand vous l'êtes",
      "Know your price before you sign up.": "Connaissez votre prix avant de vous inscrire.",
      "The calculator is on every page. No account needed to see it.":
        "Le calculateur est sur chaque page. Aucun compte requis pour le voir.",
      "Talk to support": "Contacter le support",

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
      "If a boost stalls past its ETA you get the unfinished portion back, pro-rated, without opening a ticket war.":
        "Si un boost dépasse son délai, la partie non réalisée vous est remboursée au prorata, sans bataille de tickets.",
      "Privacy": "Confidentialité",
      "Nobody sees your name": "Personne ne voit votre nom",
      "Regional VPN, your own sensitivity and crosshair, offline appearance, and sessions inside your normal play hours.":
        "VPN régional, votre propre sensibilité et viseur, mode hors ligne, et sessions pendant vos horaires de jeu habituels.",
      "Support": "Support",
      "Answered in minutes, not days": "Réponse en minutes, pas en jours",
      "Discord and email, 24/7, staffed by people who play the game. Median first reply last month: 3m 40s.":
        "Discord et e-mail, 24/7, gérés par des joueurs. Première réponse médiane le mois dernier : 3 min 40 s.",

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

      /* guarantee page */
      "Safety & guarantee": "Sécurité et garantie",
      "Written down,": "Écrit noir sur blanc,",
      "not \"depends on": "pas « ça dépend",
      "the order\".": "de la commande ».",
      "A refund policy that needs a support ticket to explain isn't a policy. Here is the whole thing, in the three cases that actually happen.":
        "Une politique de remboursement qui nécessite un ticket de support pour être expliquée n'est pas une politique. La voici en entier, dans les trois cas qui arrivent réellement.",
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
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back. Not claimed within 24 hours of payment? Refunded in full, automatically.":
        "Si une commande dépasse son délai de livraison, nous vous prévenons avant que vous le remarquiez : continuer avec un crédit de 15 %, changer de booster, ou récupérer la portion inachevée. Non prise en charge dans les 24 heures suivant le paiement ? Remboursée intégralement, automatiquement.",
      "Refund": "Remboursement",
      "questions": "questions",
      "Boosting is against the terms of service of every game listed here. We reduce the risk as far as it can be reduced and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is lying to you.":
        "Le boosting va à l'encontre des conditions d'utilisation de chaque jeu listé ici. Nous réduisons le risque autant que possible et ne prétendrons pas qu'il est nul, car il ne l'est pas — tout concurrent qui affirme le contraire vous ment.",

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

      /* reviews page */
      "reviews": "avis",
      "Every review below is attached to a paid, completed order — pulled from Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so one-star reviews sit in the same feed.":
        "Chaque avis ci-dessous est rattaché à une commande payée et terminée — extrait de Trustpilot et de la note en page de commande, puis dédupliqué. Nous ne filtrons pas par note, les avis une étoile figurent dans le même flux.",
      "Unfiltered · 1★ reviews included": "Non filtré · avis 1★ inclus",
      "Overall rating summary": "Résumé de la note globale",
      "Overall rating": "Note globale",
      "Excellent": "Excellent",
      "Where the score": "D'où vient",
      "comes from": "la note",
      "A review request goes out once, on delivery, and never again. Nothing is incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than competitors who buy them, and it's the reason the score is worth reading at all.":
        "Une demande d'avis est envoyée une fois, à la livraison, et jamais plus. Rien n'est incité — pas de remise pour un avis, pas de récompense pour un cinq. Cela maintient un volume inférieur à celui des concurrents qui les achètent, et c'est pourquoi la note vaut la peine d'être lue.",

      /* track page */
      "Track an order": "Suivre une commande",
      "Your link works": "Votre lien fonctionne",
      "without a": "sans",
      "password.": "mot de passe.",
      "Guest orders are tracked by the link we emailed you. Lost it? Put the address you paid with below and we'll send it again. Nothing to remember, nothing to reset.":
        "Les commandes invité se suivent via le lien que nous vous avons envoyé par e-mail. Perdu ? Indiquez ci-dessous l'adresse utilisée pour payer et nous le renverrons. Rien à retenir, rien à réinitialiser.",
      "Order number": "Numéro de commande",
      "or the email you paid with": "ou l'e-mail utilisé pour payer",
      "Find my order": "Trouver ma commande",
      "Local preview — try order number ESB-3F92K1.": "Aperçu local — essayez le numéro de commande ESB-3F92K1.",
      "In progress": "En cours",
      "Progress": "Progression",
      "Match": "Partie",
      "Result": "Résultat",
      "When": "Quand",
      "Ranked solo": "Classée solo",
      "Win": "Victoire",
      "Loss": "Défaite",
      "min ago": "min",
      "Pause the order": "Mettre la commande en pause",
      "Request a different booster": "Demander un autre booster",
      "Message support": "Contacter le support",

      /* checkout */
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
      "Track this order": "Suivre cette commande",
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

      /* util bar / nav */
      "Currency": "Währung",
      "Language": "Sprache",
      "34 boosters on shift": "34 Booster im Dienst",
      "median claim 18 min": "mediane Annahme 18 Min.",
      "11 boosters free right now": "11 Booster jetzt frei",
      "34 boosters on shift · median claim 18 min · 11 boosters free right now · 41,000 players in the Discord":
        "34 Booster im Dienst · mediane Annahme 18 Min. · 11 Booster jetzt frei · 41.000 Spieler im Discord",
      "Games": "Spiele",
      "Live": "Live",
      "Boosters": "Booster",
      "Safety": "Sicherheit",
      "Reviews": "Bewertungen",
      "Track my order": "Bestellung verfolgen",
      "Start an order": "Bestellung starten",
      "Menu": "Menü",
      "Skip to content": "Zum Inhalt springen",

      /* footer */
      "We are not affiliated with Riot Games, Inc., Blizzard Entertainment, Valve, or any of their subsidiaries. All trademarks, game titles, logos, and brand names are the property of their respective owners. eSports Boost provides independent gaming services and is not endorsed by or associated with any game publisher.":
        "Wir sind weder mit Riot Games, Inc., Blizzard Entertainment, Valve noch einer ihrer Tochtergesellschaften verbunden. Alle Marken, Spieltitel, Logos und Markennamen sind Eigentum ihrer jeweiligen Inhaber. eSports Boost bietet unabhängige Gaming-Dienste und wird von keinem Spielehersteller unterstützt oder mit ihm in Verbindung gebracht.",
      "Questions? Email us at": "Fragen? Schreib uns an",
      "Legal": "Rechtliches",
      "24/7 Customer Support": "24/7-Kundensupport",
      "Need help? Our support team is available anytime to assist you with your orders and questions.":
        "Brauchst du Hilfe? Unser Support-Team ist jederzeit für deine Bestellungen und Fragen da.",
      "Let's Chat": "Los, chatten",
      "Visit Help Center": "Hilfecenter besuchen",
      "Privacy Policy": "Datenschutzerklärung",
      "Terms of Service": "Nutzungsbedingungen",
      "Refunds & Cancellations": "Rückerstattungen & Stornierungen",
      "Become a booster": "Booster werden",
      "Discord": "Discord",
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
      "Verified boosters — 9 games — since 2019": "Verifizierte Booster — 9 Spiele — seit 2019",
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
      "18 min median time to a claimed order": "18 Min. mediane Zeit bis zur Annahme",
      "41,000 players in the Discord": "41.000 Spieler im Discord",
      "100% recovery rate on account reviews": "100 % Erfolgsquote bei Konto-Prüfungen",

      /* section heads / home */
      "Nine ladders.": "Neun Ladders.",
      "Forty services.": "Vierzig Services.",
      "Every service is priced per division and shown before you sign in. Placements, net wins, coaching and duo on every title.":
        "Jeder Service wird pro Division berechnet und vor dem Anmelden angezeigt. Platzierungen, Netto-Siege, Coaching und Duo bei jedem Titel.",
      "Delivered today": "Heute geliefert",
      "Why this doesn't get you banned": "Warum du dafür nicht gebannt wirst",
      "You watch the whole thing": "Du siehst alles mit",
      "Regional VPN": "Regionales VPN",
      "Pro-rated refunds": "Anteilige Rückerstattungen",
      "No account sharing on duo": "Kein Kontoteilen im Duo",
      "Order dashboard — live": "Bestell-Dashboard — live",
      "Order tracking dashboard with live match history": "Bestell-Dashboard mit Live-Spielverlauf",
      "What they said after": "Was sie danach sagten",
      "Verified orders only": "Nur verifizierte Bestellungen",
      "Your climb starts at": "Dein Aufstieg beginnt bei",
      "Final at checkout. Refunded in full until a booster claims it, pro-rated after that.":
        "Endgültig an der Kasse. Bis zur Annahme voll erstattet, danach anteilig.",
      "Ready when you are": "Bereit, wenn du es bist",
      "Know your price before you sign up.": "Kenne deinen Preis, bevor du dich anmeldest.",
      "The calculator is on every page. No account needed to see it.":
        "Der Rechner ist auf jeder Seite. Kein Konto nötig, um ihn zu sehen.",
      "Talk to support": "Support kontaktieren",

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
      "If a boost stalls past its ETA you get the unfinished portion back, pro-rated, without opening a ticket war.":
        "Bleibt ein Boost über die ETA hinaus stecken, bekommst du den nicht erledigten Teil anteilig zurück — ohne Ticket-Krieg.",
      "Privacy": "Datenschutz",
      "Nobody sees your name": "Niemand sieht deinen Namen",
      "Regional VPN, your own sensitivity and crosshair, offline appearance, and sessions inside your normal play hours.":
        "Regionales VPN, deine eigene Empfindlichkeit und dein Fadenkreuz, Offline-Anzeige und Sitzungen in deinen üblichen Spielzeiten.",
      "Support": "Support",
      "Answered in minutes, not days": "Antwort in Minuten, nicht Tagen",
      "Discord and email, 24/7, staffed by people who play the game. Median first reply last month: 3m 40s.":
        "Discord und E-Mail, 24/7, betreut von Leuten, die das Spiel spielen. Mediane Erstantwort letzten Monat: 3 Min. 40 Sek.",

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

      /* guarantee page */
      "Safety & guarantee": "Sicherheit & Garantie",
      "Written down,": "Schriftlich festgehalten,",
      "not \"depends on": "nicht „kommt auf",
      "the order\".": "die Bestellung an“.",
      "A refund policy that needs a support ticket to explain isn't a policy. Here is the whole thing, in the three cases that actually happen.":
        "Eine Rückerstattungsrichtlinie, die ein Support-Ticket zur Erklärung braucht, ist keine Richtlinie. Hier ist das Ganze, in den drei Fällen, die wirklich vorkommen.",
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
      "If an order runs past its delivery window we message you before you notice: keep going with a 15% credit, swap the booster, or take the unfinished portion back. Not claimed within 24 hours of payment? Refunded in full, automatically.":
        "Läuft eine Bestellung über ihr Lieferfenster hinaus, melden wir uns, bevor du es merkst: mit 15 % Gutschrift weitermachen, den Booster tauschen oder den unfertigen Teil zurücknehmen. Nicht innerhalb von 24 Stunden nach Zahlung angenommen? Voll erstattet, automatisch.",
      "Refund": "Rückerstattungs-",
      "questions": "fragen",
      "Boosting is against the terms of service of every game listed here. We reduce the risk as far as it can be reduced and we will not pretend it is zero, because it isn't — any competitor telling you otherwise is lying to you.":
        "Boosting verstößt gegen die Nutzungsbedingungen jedes hier gelisteten Spiels. Wir senken das Risiko so weit wie möglich und tun nicht so, als wäre es null, denn das ist es nicht — jeder Konkurrent, der dir das Gegenteil erzählt, belügt dich.",

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

      /* reviews page */
      "reviews": "Bewertungen",
      "Every review below is attached to a paid, completed order — pulled from Trustpilot and the order-page rating, then deduplicated. We don't filter by score, so one-star reviews sit in the same feed.":
        "Jede Bewertung unten gehört zu einer bezahlten, abgeschlossenen Bestellung — aus Trustpilot und der Bewertung auf der Bestellseite gezogen und dedupliziert. Wir filtern nicht nach Sternen, Ein-Stern-Bewertungen stehen im selben Feed.",
      "Unfiltered · 1★ reviews included": "Ungefiltert · 1★-Bewertungen inklusive",
      "Overall rating summary": "Zusammenfassung der Gesamtbewertung",
      "Overall rating": "Gesamtbewertung",
      "Excellent": "Ausgezeichnet",
      "Where the score": "Woher die Bewertung",
      "comes from": "kommt",
      "A review request goes out once, on delivery, and never again. Nothing is incentivised — no discount for reviewing, no reward for a five. That keeps the volume lower than competitors who buy them, and it's the reason the score is worth reading at all.":
        "Eine Bewertungsanfrage geht einmal raus, bei Lieferung, und nie wieder. Nichts wird belohnt — kein Rabatt fürs Bewerten, keine Prämie für fünf Sterne. Das hält das Volumen niedriger als bei Konkurrenten, die sie kaufen, und deshalb ist die Bewertung überhaupt lesenswert.",

      /* track page */
      "Track an order": "Bestellung verfolgen",
      "Your link works": "Dein Link funktioniert",
      "without a": "ohne",
      "password.": "Passwort.",
      "Guest orders are tracked by the link we emailed you. Lost it? Put the address you paid with below and we'll send it again. Nothing to remember, nothing to reset.":
        "Gast-Bestellungen werden über den Link verfolgt, den wir dir gemailt haben. Verloren? Gib unten die Adresse ein, mit der du bezahlt hast, und wir schicken ihn erneut. Nichts zu merken, nichts zurückzusetzen.",
      "Order number": "Bestellnummer",
      "or the email you paid with": "oder die E-Mail, mit der du bezahlt hast",
      "Find my order": "Meine Bestellung finden",
      "Local preview — try order number ESB-3F92K1.": "Lokale Vorschau — probiere die Bestellnummer ESB-3F92K1.",
      "In progress": "In Bearbeitung",
      "Progress": "Fortschritt",
      "Match": "Spiel",
      "Result": "Ergebnis",
      "When": "Wann",
      "Ranked solo": "Ranked Solo",
      "Win": "Sieg",
      "Loss": "Niederlage",
      "min ago": "Min.",
      "Pause the order": "Bestellung pausieren",
      "Request a different booster": "Anderen Booster anfragen",
      "Message support": "Support kontaktieren",

      /* checkout */
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
      "Track this order": "Diese Bestellung verfolgen",
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
    "[data-track-note],[data-apply-note],[data-contact-note],[data-pay-error]," +
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
        loc.querySelector("[data-loc-icon]").textContent = opt.querySelector(".loc-flag").textContent;
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
