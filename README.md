# eSports Boost — site complet, thème « Ashfall » (handoff v2)

Refonte du site `esportsboost.com` construite sur le **handoff v2 « Ashfall »**
(`redesign_zip_v2/design_handoff_esportsboost_v2/`), qui remplace la direction
Nocturne du v1. La page d'accueil est la page immersive du v2 ; le reste du site
(23 pages) porte le même système.

**Toutes les images du design sont remplies** — le handoff livre 16 emplacements
vides, ce build en génère 34.

## Lancer le preview

```bash
python3 site/build.py && python3 site/serve.py 4321
```

Puis <http://localhost:4321>. Aucune dépendance : Python 3 standard uniquement
(pas de Node sur cette machine). `build.py` régénère entièrement `site/dist/` —
ne jamais éditer `dist/` à la main.

## Structure

```
site/
  src/data.py            source unique : jeux, échelles, prix, copy, feed, roster, FAQ
  src/art.py             générateurs SVG de toutes les images
  build.py               gabarits + génération de dist/ (+ data.js pour le client)
  serve.py               serveur de preview (URL sans .html, vraie page 404)
  public/assets/
    css/ashfall.css      design system v2 : tokens, type, composants, motion
    css/site.css         couche mise en page (hero, calculateur docké, mosaïque, responsive)
    js/app.js            état de commande, formule de prix, rendu, événements GA4
  dist/                  sortie générée (23 pages, 34 images, 844 Ko)
```

## Le thème Ashfall

Fond quasi noir `#06060a`, **un seul dégradé chaud** `#ffb046 → #ff3d0f` comme
unique élément saturé, display Chakra Petch capitales serrées, corps IBM Plex
Sans, IBM Plex Mono pour chaque micro-label. Angles à 2–3 px, aucune ombre sauf
le halo sous les boutons primaires. L'atmosphère (halo dérivant, grain
`feTurbulence`, scanlines 1 px, scrims, braises) est procédurale et posée sous le
contenu, en `pointer-events: none` — elle se compose par-dessus les vraies images
quand elles arriveront.

Les 4 animations (`drift`, `rise`, `marquee`, transitions) sont coupées sous
`prefers-reduced-motion`, le bandeau marquee se met en pause au survol, l'anneau
de focus ember est visible partout, les chips d'échelle sont de vrais `<button>`
navigables au clavier avec `aria-pressed`, et le bloc prix/ETA est en
`aria-live="polite"` — les 6 manques d'accessibilité listés dans le handoff sont
tous couverts.

## Pages

| URL | Contenu |
|---|---|
| `/` | Page immersive v2 : hero 800 px + **calculateur docké**, marquee, mosaïque 7 cellules, bandeau stats, feed « livré aujourd'hui » + roster, sécurité, dashboard, avis, bandeau de clôture au prix live |
| `/games/` | Les 9 jeux, étapes, roster, garanties |
| `/games/<jeu>.html` ×9 | Hero + wizard complet (Division / Net wins / Placements, mode, serveur, options), boosters, avis, FAQ, JSON-LD |
| `/checkout.html` | Checkout **invité** : e-mail → paiement, récapitulatif verrouillé, confirmation |
| `/track.html` | Suivi sans mot de passe (essayer `ESB-3F92K1`) |
| `/how-it-works`, `/boosters`, `/guarantee`, `/support`, `/reviews`, `/become-a-booster` | Pages de contenu |
| `/legal/terms`, `/legal/refunds`, `/legal/privacy` | Légal |
| `/404.html`, `/sitemap.xml`, `/robots.txt` | Technique |

Le prix est calculé **au même endroit** côté build (Python) et côté client (JS),
à partir de la formule du handoff. Le devis live se propage au calculateur, à la
barre mobile, au bandeau de clôture (`{résumé} — {prix}`) et au checkout.

## Les images générées (34)

Aucune n'est une image de jeu sous licence — ce sont des **compositions
abstraites originales** dans la palette Ashfall, faites pour que la page se lise
comme finie et pour que les vrais visuels se substituent sans toucher au layout.

| Fichier | Rôle | Emplacement du handoff |
|---|---|---|
| `hero.svg` (1600×900) | crêtes + ciel de braise, sujet à droite du centre | `im-hero` |
| `closing.svg` (1600×460) | bandeau de clôture | `im-cta` |
| `keyart-<jeu>.svg` ×9 (1200×700) | key art par jeu, un motif géométrique distinct chacun | `im-game-*` |
| `emblem-<jeu>.svg` ×9 | marque/emblème par jeu — vignettes du feed, lignes de la liste | `im-feed-1…4` |
| `avatar-<pseudo>.svg` ×10 | portraits silhouette rim-light du roster | `im-b1…b5` |
| `portrait-vantaa.svg` (480) | portrait du hero, crop cercle 232 px | `im-booster` |
| `dashboard.svg` | maquette de l'écran de suivi de commande | (référencé dans la copy) |
| `og-default.svg`, `favicon.svg` | partage social, onglet | — |

Tout est déterministe : même build, même image. Les motifs par jeu sont dans
`MOTIFS` (`src/art.py`) — arches, éclats, caisses, hexagones, impact, crêtes,
chevrons, anneaux, terrain. Chaque composition est bâtie en couches (horizon,
bandes de brume, crête lointaine, halo de braise, motif, masse de premier plan
avec liseré chaud, scanlines, vignettage, grain).

### Poser les vraies images : `site/assets-in/`

Tout fichier déposé dans ce dossier **remplace** l'image générée au prochain
build, quelle que soit son extension (`.jpg .png .webp .avif .svg`). Le build
réécrit tous les `<img src>` **et** les `og:image` correspondants — aucun
changement de code, aucun changement de layout.

```
site/assets-in/
  keyart/valorant.jpg        → tuile mosaïque + hero page jeu + carte + og:image
  emblem/valorant.png        → vignette du feed + ligne de liste
  avatar/vantaa.jpg          → ligne du roster
  hero.jpg  closing.jpg  portrait.jpg  dashboard.png  og.png
```

Cadrage et contraintes dans [site/assets-in/README.md](site/assets-in/README.md).

### Vrais logos des jeux (contexte académique / PFE)

Les **9 logos officiels** sont récupérés depuis Wikimedia Commons / Wikipedia et
compositée sur les fonds Ashfall : tuile mosaïque, hero de page jeu, cartes de
`/games/`, vignettes du feed et lignes de liste. Chaque logo est traité en
silhouette pâle uniforme (`feColorMatrix`) — cohérent avec la discipline
monochrome du thème et lisible quel que soit sa couleur d'origine (Overwatch et
Apex, sombres à l'origine, ressortent ; le fond rouge parasite du SVG Dota a été
retiré pour ne garder que les lames).

Les logos vivent dans `site/assets-in/_logos/<slug>.svg`, **hors du dépôt d'art
généré** : ce sont des marques déposées de Riot, Valve, NetEase, Blizzard, EA et
Psyonix, réutilisées ici dans un cadre **académique et non commercial** (PFE).
Pour une mise en ligne réelle il faudrait la licence des ayants droit, ou des
visuels que vous possédez — le dossier `assets-in/` reste le point d'entrée.

Récupérer / rafraîchir les logos : ils sont déjà dans `assets-in/_logos/`. Le
build les inline en data-URI ; supprimer un fichier fait retomber ce jeu sur son
emblème abstrait généré.

## Correctifs de l'audit CRO intégrés

- **P0-1** checkout invité par e-mail, aucun mur d'authentification
- **P0-2** `dataLayer` complet : `view_item`, `select_item`, `add_to_cart`,
  `begin_checkout` (**avant** la navigation), `add_payment_info`, `purchase`, `generate_lead`
- **P0-3** aucun lien Trustpilot vers une autre marque ; un seul jeu de chiffres partout
- **P1-4** prix via `Intl.NumberFormat` (jamais de `$9.6`)
- **P1-5** calculateur au-dessus de la ligne de flottaison sur **toutes** les pages, barre mobile live
- **P1-6/7** Discord + e-mail assumés, politique de remboursement explicite
- **P2-8/9/10/11** JSON-LD, `og:image` par jeu, canonical, sitemap des URL finales, hiérarchie de titres, `alt`

## À faire avant une mise en ligne

1. **Données placeholder** — le handoff est formel : la liste des jeux hors LoL,
   toutes les statistiques (4.8/5, 3 140 avis, 92 400 boosts, 41 000 Discord,
   18 min, **100 % de taux de récupération**), les 5 boosters, les 4 entrées du
   feed et les 3 avis sont **inventés**. Tout est dans `site/src/data.py`.
2. **Revue juridique** des affirmations de la section « sécurité » et du 100 % de
   récupération — le handoff v2 le demande explicitement.
3. **Vraies images** — remplacer les SVG générés par le key art sous licence, les
   vraies photos de boosters et une vraie capture du dashboard. Le layout ne bouge pas.
4. **Tarification côté serveur** — `PER_DIVISION`, les `FACTOR` et les options
   sont côté client ; il faut aussi modéliser les divisions et les offsets LP/RR.
5. **i18n `fr`** — le site actuel a `en`/`fr` ; ce preview est en anglais (la copy
   du handoff l'est). `data.py` est prêt à recevoir un second jeu de chaînes.
6. **Paiement, comptes, dashboard** — les formulaires ne postent nulle part et
   aucune donnée de paiement n'est demandée. Étapes 2–3 du checkout et dashboard
   non conçus dans le handoff.
