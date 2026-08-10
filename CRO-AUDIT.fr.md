# eSportsBoost — Audit du taux de conversion

**Date de l'audit :** 10 août 2026 · site en ligne uniquement (`www.esportsboost.com`), sans accès au dépôt ni aux analytics
**Stack observée :** Next.js (App Router, i18n `en`/`fr`) derrière CloudFront
**Tracking observé :** GA4 `G-GB2Q83DBQL`, Google Ads `AW-18171663463`, Meta Pixel + passerelle CAPI (`capig.datah04.com`)

## Périmètre et niveau de certitude

Tout ce qui suit est constaté depuis le front-end en production. Je n'ai **pas** pu mesurer votre taux de
conversion réel, la répartition de votre trafic, ni les points de décrochage — cela nécessite un accès
GA4/Ads. La priorisation repose donc sur **l'ampleur du frottement observé**, pas sur une perte mesurée.
Quand je fais une hypothèse, je le précise.

Le contexte le plus important : **vous achetez du trafic** (Google Ads et Meta Pixel sont actifs). Cela
rend les deux points P0 ci-dessous coûteux, et pas seulement sous-optimaux.

---

## P0 — À corriger en priorité

### 1. Le bouton d'achat ouvre un mur d'authentification. Aucune commande en tant qu'invité.

**Constat :** sur `/en/games/league-of-legends`, après avoir configuré un boost et cliqué sur le CTA
principal (« Rank Up For $9.6 »), une modale s'ouvre : *Sign in with Google / Facebook / Discord /
Login with email*. Aucune option « continuer en tant qu'invité », aucun paiement sans création de compte.

Pourquoi c'est le point n°1 :

- La création de compte obligatoire est l'une des causes d'abandon de panier les plus citées dans toutes
  les études publiées sur le sujet.
- Votre audience est **précisément motivée par la confidentialité**. Votre propre page vend « 100% Safe &
  Anonymous », « Show As Offline In Chat », « Invisible Mode », « VPN Protection » — puis exige que
  l'acheteur livre une identité Google/Facebook avant même de voir un formulaire de paiement. La promesse
  et le parcours se contredisent.
- Le boosting est un achat d'impulsion à 10–50 $. L'étape de création de compte coûte plus d'effort perçu
  que le produit ne coûte d'argent.

**Action :** mettre en place un checkout invité par simple e-mail. E-mail → paiement → création silencieuse
du compte après l'achat, avec envoi d'un lien magique pour suivre la commande. Garder le login social comme
option *rapide*, pas comme option *unique*.

**Bug secondaire dans la même modale :** le titre affiche « Welcome Back To Esports Boost » — on accueille
un nouvel acheteur comme un client fidèle. Juste en dessous, « Don't Have An Account? » est suivi d'un
bouton intitulé « Login With Email ». Le chemin d'inscription est libellé comme une connexion. Un nouveau
visiteur n'a aucune entrée visible.

### 2. Le tunnel e-commerce n'est pas tracké. Vos régies optimisent à l'aveugle.

**Constat :** après un chargement complet et une série d'interactions, le `dataLayer` ne contenait **que**
les événements natifs de GTM : `gtm.dom`, `gtm.scrollDepth`, `gtm.load`. Rien d'autre.

J'ai testé activement : changement d'onglet de service (Division Boost → Ranked Wins), bascule Solo/Duo,
clic sur le CTA de checkout. **Aucun événement envoyé.** Ni `view_item`, ni `add_to_cart`, ni
`begin_checkout`.

Conséquence : le Smart Bidding de Google Ads et l'algorithme de Meta n'ont aucun signal de milieu de tunnel.
Ils ne peuvent apprendre que sur les achats finaux (à supposer qu'ils soient trackés — je n'ai pas pu
atteindre une page de confirmation pour le vérifier). À ce niveau de prix, le volume d'achats est presque
certainement un signal trop rare pour entraîner les algorithmes : vous payez donc des clics que la régie
ne sait pas qualifier.

**Action :** implémenter les événements e-commerce GA4, puis les importer comme conversions dans Ads :

| Événement | Déclenchement | Paramètres |
|---|---|---|
| `view_item` | chargement d'une page jeu | `item_id` (jeu), `value`, `currency` |
| `select_item` | changement d'onglet de service | `item_variant` (division/wins/placements) |
| `add_to_cart` | sélection des rangs terminée | `value`, rangs en `item_variant` |
| `begin_checkout` | clic sur le CTA checkout (**avant l'ouverture de la modale**) | `value`, options |
| `login` / `sign_up` | authentification réussie | `method` |
| `purchase` | commande confirmée | `transaction_id`, `value`, `currency`, `items` |

Déclencher `begin_checkout` **avant** la modale d'authentification est le détail décisif : c'est le seul
moyen de mesurer ce que le mur de login vous coûte réellement. Ce chiffre tranchera aussi le point n°1
avec des données plutôt qu'avec des arguments.

Répliquer `purchase` côté serveur vers Meta CAPI (la passerelle est déjà en place) et vers les Enhanced
Conversions de Google Ads.

### 3. Les badges de confiance au moment du paiement pointent vers une autre société.

**Constat :** les deux éléments Trustpilot —

- « Rated 4.6/5 on ⭐Trustpilot », placé directement sous le CTA de checkout
- « Excellent · Based on 225 Verified Reviews »

— pointent vers `https://www.trustpilot.com/review/lolepicshop.com`.

Un acheteur qui clique sur votre preuve sociale au moment d'intention maximale atterrit sur la page
Trustpilot de **lolepicshop.com**. S'il s'agit d'une marque sœur, le visiteur ne le sait pas : il voit un
autre nom d'entreprise et l'interprète comme un template copié ou un signal d'arnaque.

**Action :** rediriger ces liens vers le profil Trustpilot d'esportsboost.com. Si vous n'en avez pas encore
un avec un volume réel, retirer le lien et utiliser des témoignages on-site en attendant — une affirmation
sans lien est moins risquée qu'un lien qui semble exposer une autre marque.

**Incohérence liée :** le hero de la page d'accueil annonce *« Rated 4.6 by over 10,000+ customers »*, et la
même page affiche *« Based on 225 Verified Reviews »*. Deux chiffres de confiance différents, tous deux
visibles, sur une seule page. Choisissez une formulation unique : « 4.6/5 sur 225 avis · plus de 10 000
commandes livrées » est honnête et cohérent.

---

## P1 — Fort impact, faible effort

### 4. Les prix s'affichent sans formatage : `$9.6`, `$1.92`

Devrait être `$9.60`. Un centime tronqué se lit comme un bug d'arrondi et, sur une page qui demande une
carte bancaire, signale discrètement « site amateur ». Un seul appel à `Intl.NumberFormat` corrige tous les
prix du site.

```js
new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(9.6) // "$9.60"
```

Utiliser le même helper pour le montant du cashback et le récapitulatif de commande.

### 5. Le configurateur est sous la ligne de flottaison sur toutes les pages jeu

Au-dessus de la ligne de flottaison sur `/games/league-of-legends` : visuel hero, titre du jeu, et une
bannière « 20% Cashback ». Le sélecteur de rang — le produit lui-même — commence vers 1050 px, sous un
viewport mobile de 812 px. L'utilisateur doit scroller ~1,3 écran de décoration pour atteindre ce qu'il
est venu chercher.

La bannière cashback est une offre de **rétention** qui occupe l'espace le plus précieux d'**acquisition**
du site.

**Action :** remonter le sélecteur de rang au-dessus de la bannière cashback ; réduire le hero à ~40vh.
Objectif : rang actuel → rang souhaité → prix visibles sans scroll sur un viewport de 812 px. À tester en
A/B — facile à mesurer une fois le point n°2 en place.

*(À votre crédit : la barre mobile fixe en bas, avec prix en direct et CTA, est bien faite. À conserver.)*

### 6. « 24/7 Customer Support » sans aucun chat en direct

« Let's Chat » et « Visit Help Center » mènent tous deux vers `/contact-us` — un formulaire. Aucun widget de
chat n'est chargé (vérifié pour Intercom, Crisp, Tawk, Zendesk, Tidio, Freshchat — aucun présent).

Promettre un support 24/7 et livrer un formulaire e-mail crée un écart promesse/réalité qui vous coûte
exactement les acheteurs hésitants dont vous avez besoin. Vu l'audience, **un Discord public vaut mieux
qu'un widget de chat** : c'est là que ce marché vit déjà, cela fait office de preuve sociale, et c'est
gratuit.

**Action :** soit installer un vrai chat, soit renommer en « Support 24/7 par e-mail et Discord » avec un
véritable lien d'invitation Discord. Ne pas laisser la version actuelle en l'état.

### 7. La FAQ sur les remboursements augmente le risque au lieu de le lever

> « Refund policies may depend on the order status and service conditions. Please contact our support team
> if you need help with refunds, cancellations, or order changes. »

C'est la dernière réponse que lit un acheteur hésitant avant de décider. Elle n'engage à rien. Tous vos
concurrents sur ce marché mettent une garantie explicite en avant.

**Action :** annoncer une politique concrète — par ex. « Boost non commencé sous 24h ? Remboursement
intégral, sans justification. Boost incomplet ? Remboursement au prorata de la partie non réalisée. »
Puis l'afficher sous forme de badge à côté du bouton de paiement, et non enterrée dans un accordéon.

---

## P2 — SEO et technique (effet cumulatif, retour plus lent)

### 8. Aucune donnée structurée

Zéro `application/ld+json` sur la page d'accueil comme sur les pages jeu. Vous disposez de toute la matière
première pour des résultats enrichis et n'en exploitez rien :

- `Product` + `Offer` + `AggregateRating` sur les pages jeu → prix et étoiles dans les SERP
- `FAQPage` sur les blocs FAQ (déjà rédigés, simplement non balisés)
- `BreadcrumbList`, `Organization`

C'est un gain pur de taux de clic en SERP — même position, plus de clics. Le gain SEO le moins cher
disponible.

### 9. Pas d'`og:image` — chaque lien partagé s'affiche sans aperçu

Les pages jeu ont `og:title` et `og:description` mais **aucun `og:image`** ni `twitter:card`.

Votre audience partage des liens sur **Discord**. Un lien sans image d'aperçu paraît cassé et se fait
ignorer. C'est de la distribution organique gratuite que vous jetez aujourd'hui.

**Action :** des images OG par jeu (`/opengraph-image.tsx` sous Next.js les génère au build), plus
`twitter:card=summary_large_image`.

### 10. Aucune balise canonique + un sitemap qui ne pointe que vers des redirections

- Aucun `<link rel="canonical">` sur les pages vérifiées.
- `/games/league-of-legends` → **307** → `/en/games/league-of-legends`. Les deux formes sont liées en
  interne depuis la même page d'accueil.
- `sitemap-0.xml` liste **17 URL, et toutes sont des URL sans préfixe de langue qui redirigent.** Un
  sitemap doit lister les destinations finales.
- **L'intégralité du site français est absente du sitemap.** `/fr/games/league-of-legends` renvoie un 200
  avec des meta correctement traduites : des pages réelles, fonctionnelles et traduites que vous ne
  soumettez pas à l'indexation.
- Le `hreflang` est bien servi via l'en-tête HTTP `Link` (en/fr/x-default). Ce point-là est correct.

**Action :** ajouter des canoniques auto-référencées ; régénérer le sitemap avec les URL préfixées par
langue pour `en` et `fr` ; normaliser les liens internes vers la forme préfixée.

### 11. La page d'accueil a un seul `<h1>` et zéro `<h2>`

« Choose Your Game », « Boosting Made Simple », « Our Blogs », « Frequently Asked Question » — aucun n'est
un titre au sens HTML. La page est sémantiquement plate pour les crawlers et non navigable au lecteur
d'écran.

Également : **27 images sur 74 n'ont pas d'attribut `alt`.**

### 12. La meta description de la page d'accueil ne sert à rien

> « eSports Boost is a platform that allows you to boost your skills and improve your game. »

Aucun mot-clé, aucun signal de prix, aucun différenciateur, aucun CTA — et suffisamment ambigu pour se lire
comme un site de coaching. Les descriptions des pages jeu sont bien meilleures ; alignez la page d'accueil
sur ce niveau.

### 13. TTFB ~1,07 s, et le HTML est explicitement non cacheable

```
cache-control: private, no-cache, no-store, max-age=0, must-revalidate
x-cache: Miss from cloudfront
```

Chaque visite déclenche un aller-retour complet vers l'origine ; CloudFront ne met rien en cache. Le seuil
« bon » de Google est < 800 ms, et le TTFB entre directement dans le calcul du LCP. Des pages marketing
n'ont aucune raison d'être en `no-store`.

**Action :** pour les pages jeu/blog/policies, utiliser l'ISR (`revalidate`) ou
`s-maxage=300, stale-while-revalidate`. Ne garder `no-store` que sur les routes authentifiées. Cela devrait
représenter une ligne par route — le plus gros gain de performance disponible d'un seul coup.

*(Le poids de la page est correct en soi : 628 Ko / 123 requêtes. Le plus gros asset est un fond WebP de
208 Ko.)*

### 14. Surface de contenu trop mince — 17 URL au total

Six pages jeu et cinq articles de blog, tous datés de 2023–2024, sur un site dont le pied de page affiche
© 2026. Des dates périmées sur votre seul contenu, pour un produit qui vend la « meta actuelle », fait
mauvais effet.

Vous n'avez aucune landing page sur les vrais mots-clés commerciaux : `lol duo boost`, `valorant rank
boost`, `iron to gold boost`, `elo boost pas cher`, ainsi que les variantes par région et par rang. Vos
concurrents se positionnent exactement là-dessus. C'est le levier de croissance de long terme, mais il est
plus lent que tout le reste — à traiter après les P0/P1.

---

## Ordre d'exécution recommandé

**Semaine 1 — instrumenter, puis corriger ce qui est mesurable**
1. Événements e-commerce GA4 (n°2) — à faire *en premier*, c'est ce qui prouvera tout le reste
2. Corriger les liens Trustpilot (n°3) et harmoniser les chiffres 4,6 / 225 / 10 000
3. Formatage des prix (n°4)
4. Copy de la modale : « Welcome Back » → neutre, corriger le libellé d'inscription (n°1b)

**Semaine 2 — le gros morceau**
5. Checkout invité (n°1) — avec `begin_checkout` déjà en place, vous verrez l'avant/après directement
6. Copy et badge de garantie de remboursement (n°7)
7. Lien Discord ou vrai chat (n°6)

**Semaine 3 — mise en page + SEO gratuit**
8. Configurateur au-dessus de la ligne de flottaison, testé en A/B (n°5)
9. JSON-LD (n°8), images OG (n°9)
10. Canoniques + régénération du sitemap (n°10)

**Semaine 4 et au-delà**
11. En-têtes de cache / ISR (n°13)
12. Titres et attributs alt (n°11), meta de la page d'accueil (n°12)
13. Landing pages par mot-clé (n°14)

---

## Ce dont j'ai besoin pour aller plus loin

- **Accès GA4 + Google Ads (lecture seule)** — pour remplacer « ce frottement a l'air coûteux » par « cette
  étape perd N % des sessions ». Cela peut modifier l'ordre des priorités si les données me contredisent.
- **Accès au dépôt** — l'essentiel des P0/P1 se réduit à un petit nombre de diffs concrets que je peux
  écrire directement.
- **Deux réponses que je ne peux pas obtenir de l'extérieur :**
  - `lolepicshop.com` vous appartient-il ? Cela détermine si le n°3 est un lien cassé ou un choix de marque.
  - Un événement `purchase` est-il déclenché sur la page de confirmation de commande ? Je n'ai pas pu
    finaliser un achat pour le vérifier.
