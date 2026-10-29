# 5 video ads — League of Legends, English, 9:16

Same engine as the Enevie films (`outils/video_lib.py` ported to `site/tools/video_lib.py`):
1080×1920, 30 fps, ElevenLabs voice-over, synth music, ffmpeg. Each scene's length is set by
its voice line, so the timings below are estimates, not cuts.

**Every video follows the same three beats, in this order** (the brief):

1. **Hook** — "Do you play League of Legends?" (or "…or something similar?")
2. **Identify** — you are stuck in your rank and you want out
3. **Offer** — eSports Boost, with one real number and one real promise, then the CTA

## The figures these scripts are allowed to use

All read from `site/src/pricing.py` + `data.py` on 2026-10-29, sale already applied:

| Claim | Value | Source |
| --- | --- | --- |
| One division | **from $4** | `service_floor()` |
| Bronze IV → Silver IV | **$21** (list $25) | `quote()` |
| Silver IV → Gold IV | **$25** (list $30) | `quote()` |
| Gold IV → Platinum IV | **$36** (list $42) | `quote()` |
| Emerald IV → Diamond IV | **$91** (list $107) | `quote()` |
| One net win | **$3** | `quote()` |
| Delivery, one division | **about 1 day** | `eta_text()` |
| Duo queue | **+55%** | `DUO_MULT` |
| Watch your booster play | **free** | `ADDONS['stream']`, `pct=0` |
| Money-back until a booster is assigned | policy | `GUARANTEES_INLINE` |
| Pause it anytime · VPN matched to your region | policy | `GUARANTEES_INLINE` |

⚠ **Not usable in an ad, and not used below:** the review score and count, the client count,
the booster count and every booster's rank — all invented placeholders (see
*Placeholder data* in CLAUDE.md). An ad is the one surface where an invented statistic becomes
a legal problem rather than a to-do.

**The sale is now "Winter sale · ends 31 Jan"** (it read "Summer sale · ends 30 Sep" a month
after its own window closed, on every page). The code is still `SPLIT15`, so the ads, the
catalogue FAQ and anything already printed stay true. The scripts below say "15% off right now"
and never name a window, which is what keeps them usable after 31 Jan.

⚠ **"Watch your booster play" is sold and the Discord side is not built** (`streams.py` does not
exist). Video 4 is built entirely on that promise: either ops opens the channel by hand for
every order it brings in, or that video does not ship.

---

## 1 — "Hard stuck" (typo-choc, ~22 s)

The Enevie `2-typo-choc` shape: one full-bleed colour per line, giant type, no illustration.
Cheapest to produce, hardest hook. Cuts, not fades.

| # | On screen | Voice-over |
| --- | --- | --- |
| 1 | `DO YOU PLAY` / `LEAGUE OF LEGENDS?` (dark + ember) | "Do you play League of Legends, or something similar?" |
| 2 | `SAME RANK` / `SINCE LAST` / `SEASON?` (ember) | "And you're still in the same rank you were last season?" |
| 3 | `IT'S NOT` / `YOUR AIM.` / `IT'S THE 400` / `GAMES.` (dark) | "It's not your aim. It's the four hundred games it takes." |
| 4 | `WE PLAY THEM` / `FOR YOU` (ember grad) | "So we play them for you." |
| 5 | `SILVER → GOLD` / `$25` (dark + gold tier colour) | "Silver to Gold: twenty-five dollars. Usually done in about a day." |
| 6 | `MONEY BACK` / `UNTIL A BOOSTER` / `TAKES IT` | "Money back until a booster takes the order." |
| 7 | End card: logo, `esportsboost.com`, CTA button | "Link's right there." |

---

## 2 — "The climb" (illustrated, ~26 s)

The ladder strip from the game page, animated: tier marks in their real colours
(`tier_color()`), the ring on the current rank, the dot on the target, the span filling in.

| # | On screen | Voice-over |
| --- | --- | --- |
| 1 | Rank plate, Silver IV, dim | "Do you play League of Legends, or something similar?" |
| 2 | The ladder strip, ring stuck on Silver IV, LP bar bouncing 40→60→30 | "This is you. Same two divisions, over and over." |
| 3 | Calendar: 7 nights ticking, the ring doesn't move | "Because climbing out takes nights you don't have." |
| 4 | The span fills Silver → Gold, mark turns gold | "A booster does it in about a day." |
| 5 | Three chips: `Pause anytime` · `VPN in your region` · `Nobody sees your name` | "Paused whenever you like. On a VPN in your region. Your name never shows." |
| 6 | Price plate `$25` + `Silver IV → Gold IV` | "Twenty-five dollars for the climb." |
| 7 | End card | "eSports Boost. Link below." |

---

## 3 — "Which one are you?" (quiz, ~27 s)

The Enevie `3-quiz-eligibilite` shape — a cursor that taps the answers, so the viewer picks
their own rank and the price lands on theirs.

| # | On screen | Voice-over |
| --- | --- | --- |
| 1 | Card: `Do you play League of Legends?` + Yes / No, cursor taps **Yes** | "Do you play League of Legends, or something similar?" |
| 2 | Card: `Stuck in your rank right now?` cursor taps **Yes** | "Are you stuck in your rank right now?" |
| 3 | Four rank tiles — Iron, Bronze, Silver, Gold — cursor taps **Silver** | "Pick the one you're sitting in." |
| 4 | The tile expands: `Silver IV → Gold IV` · `$25` · `about 1 day` | "Silver to Gold is twenty-five dollars, and about a day." |
| 5 | Grid of the other prices: `Bronze → Silver $21` · `Gold → Plat $36` · `one division from $4` | "Every rank has its own price. One division starts at four dollars." |
| 6 | `MONEY BACK UNTIL A BOOSTER TAKES IT` | "And it's refundable until a booster takes it." |
| 7 | End card | "Find your rank on the site." |

---

## 4 — "Watch it happen" (~25 s) ⚠ see the warning above

The objection this one answers is "how do I know anyone is even playing?". It is the only
video that needs a feature ops has to honour by hand today.

| # | On screen | Voice-over |
| --- | --- | --- |
| 1 | Dark, ember, `DO YOU PLAY LEAGUE?` | "Do you play League of Legends, or something similar?" |
| 2 | `STUCK IN GOLD` + a flat LP line | "Stuck in the same rank, and tired of grinding for it?" |
| 3 | Objection card: `"So I just… hand it over and hope?"` | "The usual problem with paying someone: you hand it over and hope." |
| 4 | Dashboard mock: live rank, LP chart climbing, match rows landing | "Here you watch it. Live rank, every game, as it happens." |
| 5 | `WATCH YOUR BOOSTER PLAY` + `FREE` flag (green) | "And you can watch your booster's screen while they play. That's free." |
| 6 | `Gold IV → Platinum IV` · `$36` | "Gold to Platinum: thirty-six dollars." |
| 7 | End card | "eSports Boost." |

---

## 5 — "Less than a skin" (~24 s)

The money angle. Compares a rank to a thing the viewer already buys — no competitor named,
no price claimed for anyone else.

| # | On screen | Voice-over |
| --- | --- | --- |
| 1 | `DO YOU PLAY` / `LEAGUE OF LEGENDS?` | "Do you play League of Legends, or something similar?" |
| 2 | `YOU'VE BEEN` / `HARD STUCK` / `FOR MONTHS` | "Been hard stuck for months, and the climb isn't happening?" |
| 3 | A skin splash tile, price pill `$22` | "You'll spend twenty-two on a skin without thinking about it." |
| 4 | Beside it: rank plate Silver → Gold, price pill `$25` | "A whole rank is twenty-five." |
| 5 | `ONE DIVISION` / `FROM $4` | "One division starts at four dollars. One win, three." |
| 6 | `15% OFF RIGHT NOW` (ember) | "Fifteen percent off right now, applied at checkout." |
| 7 | End card | "Pick your rank. Link below." |

---

## Production notes

- **Voice**: ElevenLabs, `eleven_multilingual_v2`, `language_code: "en"` — `tts_eleven()` has
  `'fr'` hardcoded and gains a `ELEVEN_LANG` switch in the port. Render 3 sample lines in 3
  voices and pick one before the 5 videos go out, the way the Enevie voices were sampled.
- **Palette**: Ashfall, not Enevie's green. `--ember #ff4a1f`, `--bg #06060a`, amber, and the
  **tier colours from `D.tier_color()`** so a Gold mark in a video is the same gold as on site.
- **Logo**: `site/assets-out/google-ads/logo-4x1-1200x300-transparent-dark-bg-only.png`, already
  exported and transparent on dark.
- **Font**: the engine needs a variable TTF. `Montserrat.ttf` is in the Enevie tooling and reads
  right for a gaming brand; the site's own Chakra Petch would be closer to the brand if a TTF
  is dropped into `site/tools/fonts/`.
- **Music**: `mood='electro'` from the synth library — original, no licence, no takedown.
