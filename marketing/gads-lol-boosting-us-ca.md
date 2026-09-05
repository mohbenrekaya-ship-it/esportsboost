# Google Ads — LoL Boosting — US & Canada

Landing page: https://www.esportsboost.com/games/league-of-legends
(the clean URL, deliberately — `/games/league-of-legends.html` 308-redirects to it and
an extra hop on every paid click is latency nobody is paying for)

Status to create in: **PAUSED** (publish by hand after review)

Scope and budget are the owner's call, taken 2026-09-05: **League of Legends only**,
**EUR 20.00/day**, **max CPC EUR 1.20** — the same settings as the accounts campaign
that is currently converting, so the two are readable against each other.

## Campaign settings
- Type: Search. **Uncheck Display Network and Search Partners.**
- Locations: United States, Canada
- Location option: **Presence — people in your targeted locations** (NOT "presence or interest")
  ⚠ This is the setting the accounts clones lost. On 2026-09-04, six of twelve paid clicks
  came from GB / NL / KW / FR against a US+CA campaign. Check it on the review screen, not
  just on the form.
- Language: English
- Bidding: **Maximize clicks**, max CPC EUR 1.20 (no boosting conversion history yet)
- Budget: EUR 20.00/day
- AI Max: **OFF** at campaign and ad group level. The review page must read
  "Search term matching: Using only your keywords and match types."
- Ad rotation: optimise · Ad schedule: all day

## Ad group 1 — Elo boost (generic)  (phrase)
"lol elo boost"
"league of legends elo boost"
"elo boost lol"
"buy elo boost"
"elo boosting service"
"lol boosting service"
"league of legends boosting"
"league boosting service"
"lol boost service"
"buy lol boost"

## Ad group 2 — Rank / division targets  (phrase)
"lol rank boost"
"league of legends rank boost"
"lol gold boost"
"lol platinum boost"
"lol emerald boost"
"lol diamond boost"
"buy gold boost lol"
"buy platinum boost lol"
"buy diamond boost lol"
"league of legends division boost"
"lol division boost"
"lol rank boosting service"

## Ad group 3 — Duo queue  (phrase)
"lol duo boost"
"league of legends duo boost"
"duo queue boosting"
"lol duo queue boost"
"duo boost league of legends"
"lol duo boosting service"

## Ad group 4 — Wins & placements  (phrase)
"lol placement matches boost"
"league of legends placement boost"
"lol placement games boost"
"buy lol wins"
"lol net wins boost"
"league of legends win boost"

## Responsive search ad — headlines (<=30 chars)
LoL Elo Boost From $4
League Of Legends Boosting
Solo Or Duo Queue Boosting
Live Price Before You Pay
Money Back Until It Starts
Pick Your Booster, No Fee
Bundles Up To 37% Off
Gold, Plat & Diamond Boost
Net Wins & Placements Too
Pro-Rated If We Stop Early
No Login Needed For Duo
Secure Stripe Checkout
Your Rank, Your Schedule
Buy A LoL Boost Today
Price Fixed At Checkout

## Responsive search ad — descriptions (<=90 chars)
League of Legends elo boost. Solo or duo queue, live price before you pay. From $4.
Full money back until a booster claims it. Pro-rated refund if the order stops early.
Name the booster you want at no extra fee. Divisions, net wins and placements.
Bundle a multi-tier climb and save up to 37%. Secure checkout, price fixed at checkout.

## Sitelinks
Safety & Guarantee   -> /guarantee
How It Works         -> /how-it-works
Customer Reviews     -> /reviews
Talk To Support      -> /support

## Campaign negative keyword list  "LoL boosting — global negatives"
free
hack
hacked
generator
gen
cracked
crack
script
scripts
bot
bots
cheat
cheats
unban
appeal
banned
ban
recovery
recover
how to
tutorial
guide
guides
reddit
forum
jobs
job
hiring
salary
career
apply
account
accounts
smurf
buy account
valorant
csgo
cs2
counter strike
dota
apex
overwatch
fortnite
wow
tft
teamfight
rocket league
wild rift
mobile legends

⚠ `account` / `accounts` / `smurf` are negatives HERE on purpose — those searches belong to
the accounts campaign, which is live on the same account. Without them the two campaigns bid
against each other on the same auctions, which is exactly what the three accounts clones were
doing on 2026-09-03.

---

## Every figure in the copy, and where it comes from
Nothing here is typed from memory. Re-derive after any re-price — the last one (2026-08-30,
-21%) silently invalidated four dictionary strings that carried figures.

| Claim | Source | Value today |
| --- | --- | --- |
| "From $4" | the H1 on the live page, `from_price()` over every rung | $4 |
| "Up to 37% off" | `pricing.bundle_pct()` over the LoL bundles | 19%–37% |
| "Money back until it starts" | `D.GUARANTEE["cases"][0]` | 100% back before a booster claims it |
| "Pro-rated if we stop early" | `D.GUARANTEE["cases"][1]` | refunded at the rate paid |
| "Pick your booster, no fee" | `pricing.py` charges nothing for a named booster | $0 |
| "No login needed for duo" | `SAFETY["body"]` — duo never touches the login | true |
| Solo / duo | `pricing.DUO_MULT` = 1.55 | duo is +55% |

## Deliberate omissions — do not "improve" the ads by adding these back
- **No rating, star score or review count.** `STATS["trustpilot"]` and `REVIEW_DIST` are
  invented placeholder data. Same rule the accounts campaign follows.
- **No booster counts and no "Master+" floor.** The 88-strong roster is fifty-odd invented
  people; the win-rate floor is asserted against invented data.
- **No "boosts delivered" figure.** `STATS` is placeholder.
- **No coaching.** `D.COACHES` / rates / slots are invented and neither the calendar nor the
  payment path is built. It is a tab on the page, not something to buy traffic for.
- **No "watch your booster play".** The add-on is sold and rides into fulfilment, but
  `streams.py` does not exist — nothing opens a Discord channel and nothing tells a booster to
  share a screen. Advertising it buys clicks against a promise only a human can keep by hand.
- **No delivery-time claim.** The ETA is computed per climb and rendered as a band; a fixed
  "in 24 hours" in an ad is false on any long ladder, and the guarantee pays 15% for a missed
  ETA, so it is a real liability rather than a copy choice.
- **No order-tracking claim.** `/demo` renders one invented fixture; there is no per-order
  page yet, and the FAQ already promises an emailed link that is not built.

## Before enabling
1. Re-read the four ads yourself — boosting is a standing disapproval risk under Google's
   policies whatever the initial review says.
2. Confirm on the review screen: Search Partners OFF, Display OFF, **Presence**, AI Max off.
3. Then flip the campaign from Paused to Enabled.
4. After ~a week, read the search terms report and add negatives.

===============================================================
# STATUS 2026-09-05 — BUILT AND PAUSED
===============================================================
Account 724-906-5333 (info@esportsboost.com), currency EUR.
**Campaign id 24218765186 — "LoL Boosting | US-CA | Search" — LIVE OBJECT, status PAUSED.**
Verified after pausing: €0.00 cost, 0 impressions, 0 clicks. It has never served.

## Complete
- Search campaign, objective Website traffic, goal Purchases (the existing
  AW-18171663463 Purchase conversion), final URL /games/league-of-legends.
- Networks: **Search Partners OFF, Display OFF** (both are checked by default —
  they were unchecked by hand).
- Locations: United States + Canada, **Presence**.
  ⚠ Google's default here is "Presence **or interest**", and that is almost
  certainly what put the accounts campaign's clicks in GB / NL / KW / FR on
  2026-09-04. The radio was moved deliberately; check it on any future clone.
- Language: English only. French was offered and declined — we have no French
  ad copy for boosting, and half-translated ads are worse than none.
- Bidding: **Maximize clicks, max CPC EUR 1.20**. Budget **EUR 20.00/day**.
- AI Max **OFF**, text customization OFF, final URL expansion OFF. The review
  screen prints "Text customization and Final URL expansion turned on" anyway —
  that wording is misleading: asset optimization is inert while the AI Max
  master toggle is off, and the same screen confirms
  "Search term matching: Using only your keywords and match types".
- **Ad group 1 — Elo boost (generic): 10 phrase keywords, 1 responsive search
  ad with all 15 headlines and all 4 descriptions from this file.**
  ⚠ Google pre-filled 5 headlines and 3 descriptions of its own and they were
  ALL replaced. Two of its descriptions were factually wrong — "League of
  Legends boost from $6" and "…Is a Cheap, Professional Boosting Service" —
  against a page that says from $4. This is the reason the AI copy step is
  skipped: generated assets are not checked against the placeholder-data rules.
- **49 campaign-level negative keywords** applied (broad match).
- Ad strength: Average.

## NOT done — the campaign is incomplete as it stands
- **Ad groups 2, 3 and 4 do not exist** (Rank/division 12 kw, Duo queue 6 kw,
  Wins & placements 6 kw, and an RSA each). Only ad group 1 is built, so the
  campaign currently covers the generic elo-boost intent and nothing else.
- **No sitelinks.** The four in this file are still to be added.
- Ad group 1 is still called "Ad group 1"; rename it "Elo boost (generic)".
- No display paths on the ad.

## The one number to weigh before enabling
Google estimates **avg CPC EUR 1.24-1.28** for this keyword set — at or just
above the EUR 1.20 cap, which is why it also estimates only **10-12 clicks a
week** against a EUR 20/day budget. The cap, not the budget, is the constraint.
Either raise the cap or accept a slow read; do not raise the budget expecting
more traffic.

## Before enabling
1. Build the three missing ad groups, or accept the narrower coverage knowingly.
2. Re-read the ad yourself — boosting is a standing disapproval risk whatever
   the initial review says.
3. Confirm on the campaign settings screen: Search Partners OFF, Display OFF,
   **Presence**, AI Max off.
4. Then flip from Paused to Enabled.
5. After ~a week, read the search terms report and add negatives.
