/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — client runtime
   One quote function, one render pass. Every price on a given page is derived
   from the same computation, so that page's calculator, sticky bar and CTA
   band can never disagree.

   The order the visitor is building is kept ONE PER GAME and shared by every
   surface that configures that game: the homepage band and that game's own
   page read and write the same record, so a climb set in one is still there in
   the other, and still there after a trip to /support.html, a sign-in, or a
   visit tomorrow. Whichever configurator you "Continue" from is snapshotted
   into CHECKOUT_KEY, which the checkout page reads.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var D = window.ESB_DATA;

  // The checkout page reads this snapshot; a configurator commits to it only
  // when the customer clicks Continue (see the [data-continue] handler).
  var CHECKOUT_KEY = "esb.order.v1";

  // The game the visitor last configured, on ANY surface. It is what lets a
  // configurator with no game of its own — the homepage band — reopen on the
  // ladder they were last looking at rather than on the catalogue's first
  // title, and it is the only thing that has to be remembered site-wide.
  var LAST_KEY = "esb.order.last.v1";

  // This page's configurator and the game it is pinned to, read once: the
  // scripts sit at the foot of the body, so the DOM is already parsed.
  var CFG = document.querySelector("[data-configurator]");
  var PINNED = (CFG && CFG.getAttribute("data-game")) || "";

  // The closing band on a page that owns no configurator (reviews, guarantee,
  // /games/, the roster, legal). It ships the catalogue-floor fallback visible
  // and a read-back of the visitor's own order hidden, and this is the marker
  // that says so — a page carrying one resolves the saved order like a
  // configurator page rather than reading the checkout snapshot.
  var FCB = document.querySelector("[data-fc-readback]");

  /* ONE record per GAME, shared by every surface that configures that game.
     The homepage band and that game's page write the same key, so a climb set
     in the band is still set when the visitor follows it to the page it was
     for — and the other way round. It used to be one order per *context*
     ("esb.order.home.v1" beside "esb.order.g.<slug>"), which meant the two
     calculators for the same ladder each remembered a different climb and
     whichever one you landed on next contradicted the one you had just left.

     Per GAME rather than one order for the whole site, because the ranks are
     the one thing that cannot be shared: nine ladders name their rungs
     differently and "Gold II" is not a rung of CS2's. Everything that is not
     about a particular ladder follows the visitor across games instead — see
     SHARED below. */
  function keyFor(game) {
    return "esb.order.g." + ((D.slugs && D.slugs[game]) || game);
  }

  /* ── money ───────────────────────────────────────────────────────────── */
  var fmt0 = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0
  });
  var fmt2 = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
  // Currency-aware when i18n.js is loaded (USD/EUR display); plain USD otherwise.
  function usd(n, cents, fixed) {
    if (window.esbMoney) return window.esbMoney(n, cents, fixed);
    return (cents ? fmt2 : fmt0).format(n);
  }
  // Language-aware fragment lookup (English fallback when i18n.js is absent).
  function T(s) { return window.esbT ? window.esbT(s) : s; }

  /* ── analytics — every funnel step emits, before any UI gate ─────────── */
  window.dataLayer = window.dataLayer || [];
  function track(event, params) {
    var payload = Object.assign({ event: event }, params || {});
    window.dataLayer.push(payload);
    if (window.ESB_DEBUG) console.debug("[dataLayer]", payload);
  }
  window.esbTrack = track;

  /* ── which server the form opens on ───────────────────────────────────────
     It used to open on North America for every visitor on earth, so a European
     buyer's first act on the page was correcting it — on the one control that
     decides who can take their order. The default is now read from where they
     are, and it is deliberately binary: NA or EU, the two estates the roster
     actually covers in depth (see geo.py's server_area(), which owns that call
     and the reasoning). Every other server is still one tap away in the same
     control, and a visitor who picks one keeps it — this only decides what is
     selected before anybody touches anything.

     The signal is the browser's own IANA timezone. That is geo.py's second
     choice after the edge header, which a static page cannot read, and it is a
     better one here than the locale: it says where the machine IS, where
     `en-US` on a laptop in Berlin says only what language it is in. It costs no
     request, no permission prompt and no PII — navigator.geolocation would need
     all three for a worse answer than a server list needs. */
  /* The estate — "NA" or "EU" — comes from window.esbGeo, which i18n.js
     publishes. It lives there rather than here purely because of load order:
     i18n.js runs first and has to settle the currency off the same location
     before ESB_LOCALE is published, and two copies of that reasoning would
     disagree the day one of them was edited. i18n.js ships on every page
     layout() renders, so the fallback below is inert. */
  function serverArea() {
    return (window.esbGeo && window.esbGeo.area()) || "EU";
  }

  /* The nine ladders name the same two estates five different ways — "North
     America" / "North America East", "Europe" / "Europe West" / "EU Nordic &
     East" — so the estate is resolved against the game's OWN list rather than
     written down per game. Exact name first, then the prefix, so a game that
     has plain "Europe" is never handed "Europe West". */
  function regionFor(game, area) {
    var list = D.regions[game] || [];
    var pats = area === "NA"
      ? [/^North America$/, /^North America\b/]
      : [/^Europe$/, /^Europe\b/, /^EU\b/];
    for (var p = 0; p < pats.length; p++) {
      for (var i = 0; i < list.length; i++) {
        if (pats[p].test(list[i])) return list[i];
      }
    }
    return list[0] || "";
  }

  /* The estate a region NAME belongs to, so switching game carries the choice
     across instead of resetting it — a visitor on "Europe West" who moves to a
     ladder that calls it "Europe" has not asked to be moved to America. Returns
     "" for the servers that are neither (Oceania, Korea, Brazil…), which fall
     back to the visitor's own area. */
  function areaOf(name) {
    if (/^North America\b/.test(name || "")) return "NA";
    if (/^Europe\b|^EU\b/.test(name || "")) return "EU";
    return "";
  }

  function defaultRegion(game, current) {
    return regionFor(game, areaOf(current) || serverArea());
  }

  /* ── state ───────────────────────────────────────────────────────────── */
  var DEFAULT = {
    game: "League of Legends", service: "division",
    // Opens on Iron I → Gold II, the handoff's default climb (11 divisions).
    from: "Iron I", to: "Gold II", mode: "Solo",
    // Net wins / placements are a 1–5 grid now, capped at five per order.
    // `unranked` is placements-only: no MMR to read, so the rank picker is hidden
    // and the price falls back to the ladder floor.
    wins: 3, placements: 3, unranked: false,
    // Full region name (not a short code): it must match an entry in
    // D.regions[game], because a fresh visitor gets DEFAULT verbatim before
    // load()'s normalization runs. Filled in below rather than written here —
    // it is resolved from the visitor's own timezone, so there is no one name
    // that is right to store in the literal.
    region: "",
    // Whether the region above is the VISITOR'S pick or just what we resolved
    // for them. Only a touch of the Server control sets it, and once set the geo
    // default never moves that endpoint again — the same contract `curPinned`
    // has for the currency, and for the same reason.
    regionPicked: false,
    addons: [], promo: "",
    // Opt-in bundle (index into D.bundles[game]) — a real discount that replaces
    // the sitewide sale on a matching climb. Never auto-set; dropped when the
    // climb stops matching (tier or target change). See bundleDiscount().
    bundle: null,
    // Coaching (service === "coaching") — a booking, not a climb. `coach` and
    // `pack` are indices into D.coaches / D.coachPacks; `focus` is a set of the
    // topics to work on; `slot` is the first-session time. Priced only off coach
    // rate × pack, so these never enter the rank engine.
    coach: 0, pack: 1, focus: [0], slot: (D.coachSlots && D.coachSlots[0]) || "",
    // The account listing an order names (an id in D.accounts), set only by the
    // accounts page's Buy button. It is the WHOLE product on service ===
    // "account": no rank, no queue, no add-ons, no sale — see quote(). Empty on
    // every other service, and quote() refuses to price an account order that
    // does not name a live listing rather than falling back to one, because a
    // fallback here would charge for an account nobody chose.
    account: "",
    // A named booster, arriving from a roster Hire or a profile CTA. It is an
    // order attribute, never a price input: pricing.py charges no fee for it,
    // so quote() must not read it. If naming a booster ever costs money it
    // goes into the formula on BOTH sides first.
    booster: ""
  };

  // Resolved once, at parse time, so the object handed to a fresh visitor is
  // already correct — paint() writes state.region into the <select>, and the
  // server-rendered options carry no `selected`, so this is what the control
  // opens on. DEFAULT.game is the resolution target: load() re-resolves per
  // game for anyone arriving with a stored order on a different one.
  DEFAULT.region = regionFor(DEFAULT.game, serverArea());

  /* How long a saved configuration still describes what the visitor wants.
     The ranks are worth remembering across a session or a day — someone who
     comes back to compare is mid-decision. A named booster and a bundle are
     not: they are choices made in a moment, and three weeks later the page
     greets a returning visitor with "Ordering with vantaa" and a bundle
     discount applied to a climb they have no memory of picking. Ranks persist;
     the two attached commitments expire. */
  var STATE_TTL = 36 * 3600 * 1000;      // 36h — over a night, not over a month

  /* The fields that are NOT about a particular ladder. They follow the visitor
     from game to game: somebody who has just said Duo queue, Europe West and
     "watch me play" has not asked to be put back on Solo and North America by
     tapping a different title. Everything else — from/to, the bundle, the
     named booster — belongs to the game it was chosen on and stays there. */
  var SHARED = ["service", "mode", "region", "regionPicked", "addons", "promo",
                "wins", "placements", "unranked",
                "coach", "pack", "focus", "slot"];

  function readRecord(key) {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch (e) { return null; }
  }

  // The last game configured anywhere, validated — a stored name the catalogue
  // no longer sells must not decide what a page opens on.
  function lastGame() {
    try {
      var g = localStorage.getItem(LAST_KEY) || "";
      return D.ladders[g] ? g : "";
    } catch (e) { return ""; }
  }

  /* What THIS page's configurator can actually represent, read off the DOM
     rather than written down — the same contract every other control here is
     wired through. The band draws four game tabs and no service tabs; a game
     page draws one game and three or four services. A stored order naming
     something the page cannot draw is CLAMPED, never dropped: losing the ranks
     is the thing the shared record exists to stop. */
  function pageGames() {
    if (PINNED) return [PINNED];
    var out = [];
    each("[data-game-tag]", function (el) {
      var g = el.getAttribute("data-game-tag");
      if (g && out.indexOf(g) < 0) out.push(g);
    });
    each("[data-sel='game'] option", function (el) {
      if (out.indexOf(el.value) < 0) out.push(el.value);
    });
    return out;
  }
  /* The most recently configured game this page can actually draw. The band
     carries four of the nine titles, so a visitor whose last order was on Apex
     cannot be shown it here — but the catalogue's first title over a climb they
     never set reads as "it forgot my order", where the last climb they set on a
     game the band DOES carry is still theirs. Their Apex record is untouched
     and comes back on the Apex page. */
  function recentOffered(list) {
    var best = "", at = -1;
    list.forEach(function (g) {
      var r = readRecord(keyFor(g));
      if (r && (r.savedAt || 0) > at) { at = r.savedAt || 0; best = g; }
    });
    return best;
  }

  function pageServices() {
    var out = [];
    each("[role=tab][data-service]", function (el) {
      out.push(el.getAttribute("data-service"));
    });
    return out;
  }

  /* Bring a stored record up to what this page can quote. `game` is the game
     the record is FILED under (the key is the authority, not the record's own
     field, which can be a stale schema); "" means the checkout snapshot, which
     names its own game. */
  function normalize(stored, game) {
    try {
      // Keep the PARSED record as well as the merged one. Anything that has to
      // ask "did the stored state actually carry this key?" must read `stored`:
      // DEFAULT supplies a value for every field, so the merged object can never
      // answer that question. The regionPicked migration below is exactly that.
      // Nothing stored at all: a first visit, which must NOT take the
      // migration below. It marks a resolved region as the visitor's own pick,
      // and a fresh visitor has not picked anything — doing it here would pin
      // every new browser's server before it had touched the control.
      var fresh = !stored;
      stored = stored || {};
      var s = Object.assign({}, DEFAULT, stored);
      if (game) s.game = game;
      if (!D.ladders[s.game]) return Object.assign({}, DEFAULT);
      if (!s.savedAt || (Date.now() - s.savedAt) > STATE_TTL) {
        s.booster = DEFAULT.booster;
        s.bundle = DEFAULT.bundle;
      }
      var l = D.ladders[s.game];
      var i = l.indexOf(s.from), j = l.indexOf(s.to);
      // A stored pair can only be invalid through tampering or a stale schema;
      // never hand the page a quote that renders as an em dash on first paint.
      if (i < 0 || j < 0 || j <= i) {
        s.from = l[0];
        s.to = l[Math.min(12, l.length - 1)];
      }
      // A stored region this game doesn't offer: keep the ESTATE if the stored
      // name names one (Europe West → Europe), else fall back to the visitor's
      // own. list[0] is a North America variant on all nine ladders, so the old
      // fallback quietly sent every European back to America on a game change.
      if ((D.regions[s.game] || []).indexOf(s.region) < 0) {
        s.region = defaultRegion(s.game, s.region);
      } else if (!fresh && typeof stored.regionPicked !== "boolean") {
        // Migration, and it is the same test `curPinned` makes rather than the
        // obvious one. Every state written before this flag existed carries the
        // region the OLD code defaulted to — "North America", hardcoded, for
        // every visitor on earth — so a stored North America is not evidence of
        // a choice and has to be re-resolved, or the geo default would reach
        // only browsers that had never seen the site. Any OTHER region could
        // only have got there by someone picking it, so it stays and is marked.
        if (areaOf(s.region) === "NA") {
          s.region = defaultRegion(s.game, "");
          s.regionPicked = false;
        } else {
          s.regionPicked = true;
        }
      }
      if (s.mode !== "Solo" && s.mode !== "Duo queue") s.mode = "Solo";  // migrate old "Piloted"
      // Drop anything the catalogue no longer sells (the retired stream option)
      // and anything belonging to the other queue — a stored state predates
      // both the mode split and the picks add-on going free.
      s.addons = addonsFor(s.addons, s.mode);
      if (!s.slot) s.slot = (D.coachSlots && D.coachSlots[0]) || "";
      /* A listing that has been re-priced out of the catalogue, or sold out
         since the order was stored. Cleared rather than substituted: quote()
         then refuses the order instead of quietly charging for a different
         account, which is the one failure this product must not have. */
      if (s.account && !(D.accounts || {})[s.account]) s.account = "";
      // Grid caps at five now; migrate a stored 6–20 from the old stepper.
      s.wins = Math.max(1, Math.min(5, s.wins | 0));
      s.placements = Math.max(1, Math.min(5, s.placements | 0));
      /* A service this page cannot draw. The band is division-only and carries
         no service tabs at all, so a "wins" order set on a game page would
         quote net wins there under two rank panels; and a game with no coaches
         has no Coaching tab for a booking carried in from one that has. Only
         ever clamped where there IS a configurator — checkout draws no tabs
         and must charge the service that was bought. */
      if (CFG) {
        var svc = pageServices();
        if (svc.indexOf(s.service) < 0) s.service = "division";
      }
      return s;
    } catch (e) { return Object.assign({}, DEFAULT); }
  }

  /* Did `state` come from a stored record at all? A page with no configurator
     and no committed snapshot is holding DEFAULT, and DEFAULT must never be
     written over a game record the visitor actually built — which is reachable
     from a stray ?booster= link on a page that has no order form on it. */
  var HYDRATED = false;

  function load() {
    // The pay flow (checkout, success) reads the committed snapshot, exactly as
    // before: that is the order the buyer pressed Continue on, not whatever was
    // configured after it. It is the only page with neither a configurator nor
    // a read-back band, which is what tells the two apart.
    if (!CFG && !FCB) {
      var snap = readRecord(CHECKOUT_KEY);
      HYDRATED = !!snap;
      return normalize(snap, "");
    }

    // The game this page opens on: its own if it is pinned to one, else the
    // one last configured anywhere, else the catalogue's first — clamped to
    // what the page draws, since the band has four tabs and cannot show a
    // fifth ladder.
    var offered = pageGames();
    var game = PINNED || lastGame() || DEFAULT.game;
    if (offered.length && offered.indexOf(game) < 0) {
      game = recentOffered(offered) || offered[0];
    }

    var rec = readRecord(keyFor(game));
    HYDRATED = !!rec;                  // a real order for this game, not DEFAULT
    if (!rec) {
      // Never configured THIS game. The ranks fall back to the ladder's own
      // default (they cannot carry — different rungs), but everything that is
      // not about a ladder does carry, so a queue and a server chosen one
      // title ago are not silently undone by opening another game's page.
      var last = lastGame();
      var prev = last && last !== game ? readRecord(keyFor(last)) : null;
      if (prev) {
        rec = {};
        SHARED.forEach(function (k) {
          if (prev[k] !== undefined) rec[k] = prev[k];
        });
      }
    }
    return normalize(rec, game);
  }

  /* One-time migration off the old per-context key. The band used to keep its
     own order at "esb.order.home.v1", so a returning visitor's last climb is
     sitting in there — dropping it on deploy is exactly the loss this change
     exists to stop. It is filed under the game it names, and only where that
     game has no record of its own: a game page's order is the more considered
     of the two, and it is the one whose page quoted a price. */
  function migrateLegacy() {
    try {
      var rec = readRecord("esb.order.home.v1");
      if (!rec) return;
      var g = rec.game;
      if (g && D.ladders[g] && !readRecord(keyFor(g))) {
        localStorage.setItem(keyFor(g), JSON.stringify(rec));
        if (!localStorage.getItem(LAST_KEY)) localStorage.setItem(LAST_KEY, g);
      }
      localStorage.removeItem("esb.order.home.v1");
    } catch (e) {}
  }

  migrateLegacy();
  var state = load();

  function save() {
    try {
      state.savedAt = Date.now();          // stamps the TTL load() reads
      // The game's own record — what every surface that configures this game
      // reads — plus the pointer telling a game-less configurator which ladder
      // to reopen on.
      if (CFG || HYDRATED) {
        localStorage.setItem(keyFor(state.game), JSON.stringify(state));
        localStorage.setItem(LAST_KEY, state.game);
      }
      // On checkout there is no configurator and `state` IS the committed
      // snapshot, so that is the record an edit there has to write back.
      if (!CFG) localStorage.setItem(CHECKOUT_KEY, JSON.stringify(state));
    } catch (e) {}
    captureCart();
    captureBingoConfig();
  }

  /* ── abandoned-cart capture, while they configure ────────────────────────
     Posts the configuration on every state change, heavily debounced. There is
     NO email here and none is ever asked for: the server attaches the address
     from the visitor's *verified* session cookie and answers 204 when there
     isn't one, so an anonymous configurator stores nothing. That is also why
     this can be unconditional — the browser never learns whether a cart was
     written, and cannot name an account it isn't signed into.
     Fire-and-forget: a failed capture must never surface or block the UI. */
  var _capT = null, _capLast = "";
  function captureCart() {
    if (!window.fetch) return;
    clearTimeout(_capT);
    _capT = setTimeout(function () {
      var q = quote(state);
      if (!q || q.invalid) return;             // nothing worth recovering yet
      var sig = JSON.stringify([state.game, state.service, state.from, state.to,
                                state.mode, state.region, state.addons,
                                state.wins, state.placements, state.unranked]);
      if (sig === _capLast) return;
      _capLast = sig;
      try {
        fetch("/api/cart", {
          method: "POST", headers: { "Content-Type": "application/json" },
          credentials: "same-origin",          // the session cookie is the point
          body: JSON.stringify({
            game: state.game, service: state.service, from: state.from,
            to: state.to, mode: state.mode, region: state.region,
            addons: state.addons || [], wins: state.wins,
            placements: state.placements, unranked: !!state.unranked,
            booster: state.booster || "", bundle: state.bundle || "",
            tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
            lang: (navigator.language || "")
          })
        }).catch(function () {});
      } catch (e) {}
    }, 2500);
  }

  /* ── keep a live mystery card pointed at the CURRENT order ───────────────
     The card is offered ~4s after the target rank settles, and people keep
     configuring afterwards. Without this the row freezes at the moment the
     address was typed, and all three mails quote an order the visitor moved on
     from two steps later — the wrong price against the wrong climb, and
     /checkout?bingo= hydrating a basket they abandoned. That is not a slightly
     stale mail, it is an irrelevant one.

     Carries the token and the configuration, nothing else: the server writes
     `CONFIG_FIELDS` only, so this can never extend the hour, raise the rate or
     revive a dead card. Same debounce and same fire-and-forget contract as
     `captureCart()` above — a failed beacon must never surface or block.
     Runs wherever `save()` does, so a change made on the game page and one made
     on checkout are both picked up. */
  var _mydT = null, _mydLast = "";
  function captureBingoConfig() {
    if (!window.fetch) return;
    var rec = mydRead();
    if (!rec.token) return;                    // no card, nothing to point
    clearTimeout(_mydT);
    _mydT = setTimeout(function () {
      var q = quote(state);
      if (!q || q.invalid) return;             // never re-point at a broken pair
      var sig = JSON.stringify([rec.token, state.game, state.service, state.from,
                                state.to, state.mode, state.region, state.addons,
                                state.wins, state.placements, state.unranked,
                                state.bundle, state.booster]);
      if (sig === _mydLast) return;
      _mydLast = sig;
      try {
        fetch("/api/bingo", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "config", token: rec.token,
            game: state.game, service: state.service, from: state.from,
            to: state.to, mode: state.mode, region: state.region,
            addons: state.addons || [], wins: state.wins,
            placements: state.placements, unranked: !!state.unranked,
            booster: state.booster || "", bundle: state.bundle || "",
            cur: ((window.ESB_LOCALE && window.ESB_LOCALE.currency) || "").toLowerCase()
          }), keepalive: true
        }).catch(function () {});
      } catch (e) {}
    }, 2500);
  }

  function set(patch, evt) {
    Object.assign(state, patch);
    save();
    render();
    if (evt) track(evt, itemParams());
  }
  window.esbState = function () { return state; };

  /* Replace the live order with a server-supplied one.

     One caller today: checkout, arriving from a mystery follow-up mail at
     /checkout?bingo=… on a browser that may never have configured anything. The
     mail quotes a specific climb at a specific price, and that page has no
     configurator to rebuild it from — without this it would price whatever the
     browser happened to be holding, or the catalogue default on a fresh device,
     and the total under the CTA would not be the total in the mail.

     It goes through `normalize()` like every other path into `state`: the config
     comes back from the row the token names, so it is server-vouched, but a
     validator that only runs on the paths we happen to distrust is not one. */
  window.esbHydrate = function (order) {
    if (!order || typeof order !== "object") return false;
    var next = normalize(Object.assign({}, state, order), order.game || state.game);
    HYDRATED = true;             // a real order, so save() may write the record
    Object.assign(state, next);
    save();
    render();
    return true;
  };

  /* ── pricing — the handoff formula, unchanged, plus the two unit
        services and the add-on multipliers. Server-side in production. ─── */
  function ladderOf(game) { return D.ladders[game] || []; }
  // two-step picker: main tiers, and the sub-ranks within a tier
  function tiersOf(game) { return (D.tiers && D.tiers[game]) || ladderOf(game); }
  function divsOf(game, tier) {
    var m = D.divmap && D.divmap[game];
    return (m && m[tier]) || [tier];
  }
  function tierOf(game, rank) {
    var m = D.divmap && D.divmap[game];
    if (m) { for (var t in m) { if (m[t].indexOf(rank) >= 0) return t; } }
    return rank;
  }
  // mark colour for a tier — named palette first, positional ramp behind it.
  // Mirrors data.py's tier_color(); the map is generated into data.js.
  function tierColor(game, tier) {
    var m = (D.tiercolors && D.tiercolors[game]) || {};
    return m[tier] || "var(--text-4)";
  }
  // the division part of a rank ("Gold IV" → "IV"). Tiers that are a single
  // LP-based rank have none, so the mark falls back to the tier's own initials.
  function divOf(game, rank) {
    var t = tierOf(game, rank);
    return String(rank).slice(t.length).trim()
        || t.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase();
  }
  // per-division tier price for a rank, from the game's price table (or null)
  function rungPrice(game, rank) {
    var p = D.prices && D.prices[game];
    return p ? (p[tierOf(game, rank)] || 0) : null;
  }
  // per-tier price of one net win, from the game's win table (or null). Mirrors
  // pricing.py's win_prices branch — a game without a table falls to the formula.
  function winUnit(game, rank) {
    var p = D.winPrices && D.winPrices[game];
    return p ? (p[tierOf(game, rank)] || 0) : null;
  }
  // per-tier price of one placement game, from the game's placement table (or
  // null). `unranked` reads the ladder floor. Mirrors pricing.py's placement_prices.
  function placeUnit(game, rank, unranked) {
    var p = D.placePrices && D.placePrices[game];
    if (!p) return null;
    if (unranked) { var t = (D.tiers && D.tiers[game]) || []; return p[t[0]] || 0; }
    return p[tierOf(game, rank)] || 0;
  }

  /* Reads the add-ons off the state it is given, not the live page state —
     pricing.py's _addon_pct() takes them from its argument, so a quote() over
     any state other than the current one used to silently disagree with the
     amount the server charges. */
  /* Dollar cost of the selected add-ons, each floored at $1. An add-on is a
     percentage of the boost, so on a tiny order (one net win at Iron is ~$3)
     10–15% rounds below $0.50 and vanishes into the whole-dollar total — the
     option reads "+$0", as if free. Each selected add-on instead costs at least
     $1: its real percentage once that is a dollar or more, a flat $1 below that.
     Summed per add-on so each receipt row and each option's own price stay ≥ $1.
     Mirrors pricing.py `_addon_total()` — change one, change the other. */
  function addonById(id) {
    return (D.addons || []).filter(function (x) { return x.id === id; })[0];
  }

  /* An add-on's name on the game this order is for. Only the picks add-on
     varies — League picks champions, Valorant agents, Rocket League a playlist
     — and its per-game wording is `picks` on the game. Mirrors data.py's
     addon_label() / picks_label(). Picker rows do NOT go through this: they
     ship every wording in the DOM behind [data-when-game], because i18n.js
     matches whole text nodes. This is for the receipt strings, which are
     rebuilt each render anyway. */
  function addonLabel(a, game) {
    if (a.id !== "champ") return a.label;
    return (D.picks && D.picks[game || state.game]) || a.label;
  }

  /* Whether a mode-conditional add-on belongs on an order in this queue. Solo
     orders are offered "Solo only queue", duo orders "Play on your schedule";
     an add-on with no `mode` is on offer in both. The test is duo-or-not, the
     same one DUO_MULT makes, so any non-duo mode string reads as solo.
     Mirrors data.py `addon_applies()`. The server refuses to charge a total the
     page did not show, so the two filters agreeing is what keeps checkout from
     erroring on a perfectly valid order. */
  function addonApplies(want, mode) {
    return !want || (mode === "Duo queue") === (want === "Duo queue");
  }

  /* The add-ons that survive into `mode`: known ids only, and none belonging to
     the other queue. Used on every mode change and once at load, so a stored
     order can never list — or be charged for — an option its queue does not
     offer, or one the catalogue has stopped selling. */
  function addonsFor(list, mode) {
    return (list || []).filter(function (id) {
      var a = addonById(id);
      return !!a && addonApplies(a.mode, mode);
    });
  }

  function addonTotal(base, s) {
    var st = s || state, total = 0;
    (st.addons || []).forEach(function (id) {
      var a = addonById(id);
      if (a && a.pct && addonApplies(a.mode, st.mode)) {
        total += Math.max(1, Math.round(base * a.pct));
      }
    });
    return total;
  }

  /* Whether an add-on is free BUT still the buyer's choice. `was_pct` is the
     only thing separating a row that renders as an empty checkbox from an
     inclusion that renders ticked and disabled — both have pct === 0 and
     neither is ever charged. Mirrors data.py `addon_is_free_opt()`. */
  function isFreeOpt(a) {
    return !!a && !a.pct && !!a.was_pct;
  }

  /* What a free-but-optional add-on WOULD cost if it were priced like the paid
     ones — the struck figure beside its "Free", and nothing else. Deliberately
     the SAME arithmetic addonTotal() charges with, was_pct in place of pct and
     the same $1 floor, off the same addonBase (so a bundle order strikes 50% of
     the bundle's flat price, not of the list climb it is discounted from).
     Mirrors pricing.py `addon_list_price()` — change one, change the other. */
  function addonListPrice(addonBase, id) {
    var a = addonById(id), pct = a && a.was_pct;
    if (!pct || !addonBase) return 0;
    return Math.max(1, Math.round(addonBase * pct));
  }

  /* Pick the one discount that applies. Mirrors resolve_promo() in
     ../../../src/pricing.py — the auto promo applies with nothing typed, a
     typed code replaces it only when worth more, and discounts never stack. */
  function resolvePromo(code, s) {
    var promos = D.promos || {}, bestCode = null, best = null;
    for (var k in promos) { if (promos[k].auto) { bestCode = k; best = promos[k]; break; } }
    if (code) {
      var typed = promos[String(code).trim().toUpperCase()];
      if (typed && (!best || typed.pct > best.pct)) {
        bestCode = String(code).trim().toUpperCase(); best = typed;
      }
    }
    /* The two SERVER-RESOLVED offers: the abandoned-cart recovery code and the
       mystery discount. Neither is in D.promos and neither ever can be — that
       table ships to every browser in data.js, so a static code would be public
       the day it shipped. Each store issues one unguessable single-use token
       instead; the browser learns the percentage only after the SERVER has
       validated that token (GET /api/cart, GET /api/bingo), and it exists here
       purely so this quote matches what the server will charge —
       payments.build_session() refuses a total the page did not show. The
       percentage is never sent back; only the token is.

       Read off the STATE first, and the globals only as the fallback. That is
       what lets a hypothetical quote be asked for — "what would this order cost
       with 30% on it" is the whole of the mystery modal's before/after row —
       and it is also the rule pricing.py already follows (`quote()` reads
       `state["recovery_pct"]`, never a module global). Same never-stack,
       best-wins as pricing.resolve_promo(). */
    var st = s || {};
    var offer = st.recoveryPct !== undefined && st.recoveryPct !== null
      ? { pct: st.recoveryPct, token: st.promo, label: st.offerLabel }
      : (window.ESB_BINGO || window.ESB_RECOVERY);
    if (offer && offer.pct > 0 && (!best || offer.pct > best.pct)) {
      bestCode = offer.token || "BACK";
      best = { pct: offer.pct, label: offer.label || "Come back offer", ends: "" };
    }
    return { code: bestCode, promo: best };
  }
  window.esbPromo = resolvePromo;

  /* The active bundle for a state, but only while the current climb still
     matches it — mirrors data.active_bundle() in ../../../src/data.py. A
     division change keeps it (same from-tier); a tier or target change drops it. */
  function activeBundle(s) {
    if (s.bundle === null || s.bundle === undefined) return null;
    var b = ((D.bundles && D.bundles[s.game]) || [])[s.bundle | 0];
    if (!b) return null;
    return (tierOf(s.game, s.from) === b.ft && s.to === b.target) ? b : null;
  }
  /* A bundle stores a hand-set flat PRICE (data.py BUNDLES); `disc` is that
     price expressed as a fraction of the full climb, derived server-side in
     pricing.bundle_pct() and shipped in data.js. Reading it rather than
     recomputing it is what keeps this mirror exact: both engines then multiply
     the same double by the same boost and round it the same way. */
  function bundleDiscount(s) {
    var b = activeBundle(s);
    return b ? (b.disc || 0) : 0;
  }

  /* The delivery schedule — a fixed start-up allowance (the claim and the first
     session, before any rung moves) plus a per-rung rate, and on the games with
     no per-tier price table a per-climb term so a high-rank rung costs more time
     than a low-rank one. Mirrors DAYS_* in ../../../src/pricing.py — change one,
     change the other. */
  var DAYS_SETUP = 0.5, DAYS_PER_RUNG = 0.18, DAYS_PER_CLIMB = 0.045;
  var DAYS_PER_WIN = 0.3, DAYS_PER_PLACEMENT = 0.26;

  /* Past three days a single figure is false precision — an order that could
     land anywhere across a week cannot honestly be quoted "7 days" — so the
     estimate is a band opening ON the computed value: "7–9 days". The figures
     ride outside the translated word, per the whole-text-node i18n rule.
     Mirrors eta_text() in pricing.py. */
  function etaText(days) {
    if (days <= 1) return T("about 1 day");
    if (days <= 3) return days + " " + T("days");
    var span = Math.max(2, Math.round(days * 0.3));
    return days + "–" + (days + span) + " " + T("days");
  }

  /* ── accounts: the three derivations, mirroring data.py ────────────────
     One shard table, one price rule, one stock rule. Everything the accounts
     page prints — the promo bar's total, each server card, the server bar and
     each tier card — reduces to these, which is what stops four figures on one
     screen contradicting each other. Change one, change data.py's twin. */
  function accountServer(region) {
    var list = D.accountServers || [];
    for (var i = 0; i < list.length; i++) if (list[i].region === region) return list[i];
    return null;
  }
  /* ⚠ The buyer's currency is a PRICE INPUT here: a listing carries one row
     per market and this picks one, it never converts. Mirrors
     `D.account_price()`; an unknown currency falls back to the base row rather
     than to whichever key happens to be first. The shard is NOT an input — a
     shard changes stock, not price. */
  function accountCur() {
    var base = D.accountBaseCur || "usd";
    return ((window.ESB_LOCALE || {}).currency || base).toLowerCase();
  }
  function accountRow(table) {
    if (!table) return 0;
    var base = D.accountBaseCur || "usd", v = table[accountCur()];
    return typeof v === "number" ? v : (table[base] || 0);
  }
  function accountPrice(acc) { return accountRow(acc && acc.price); }
  function accountWas(acc) { return acc && acc.was ? accountRow(acc.was) : 0; }
  /* Units of one listing on one shard. A sold-out listing stays at zero on
     every shard — Math.max(1, …) must not resurrect it, which is the one way
     this rounding goes wrong. */
  function accountStock(acc, sv) {
    var base = acc && acc.stock ? acc.stock : 0;
    if (base <= 0 || !sv) return 0;
    return Math.max(1, Math.round(base * sv.share));
  }
  function accountUnitsOn(sv) {
    var accs = D.accounts || {}, t = 0;
    for (var k in accs) if (Object.prototype.hasOwnProperty.call(accs, k)) {
      t += accountStock(accs[k], sv);
    }
    return t;
  }

  function quote(s) {
    var per = D.perDivision;
    var factor = D.factors[s.game] || 1;
    var duo = s.mode === "Duo queue" ? 1.55 : 1;
    var base = 0, days = 0, summary = "", invalid = false;

    /* Accounts — the one product that is not a service. The price is the
       listing's flat figure and that is the entire formula: no ladder, no duo,
       no add-ons and no sitewide sale, for the reason pricing.py's branch
       states (an account has a real acquisition cost behind it, so a percentage
       off it is margin, not a discount on labour). There is deliberately no
       `wasPrice` — a reference price nobody was ever charged is not a saving.
       Mirrors pricing.py's `service == "account"` branch. */
    if (s.service === "account") {
      var acc = (D.accounts || {})[s.account];
      // The shard is clamped into the shop's own list, never trusted — mirrors
      // account_pick(). A region carried over from a boost on a shard this shop
      // does not sell on would otherwise reach checkout, and since the shard
      // carries a price delta it would be quoted at the wrong shard's price.
      var aSv = accountServer(s.region) || (D.accountServers || [])[0];
      /* Unknown or sold out both refuse, and both have to: stock is hand-set in
         data.py and nothing decrements it, so this and pricing.account_pick()
         are the only two places a listing that is gone can be stopped. Stock is
         a PER-SHARD figure, so the test is per shard too. The client's refusal
         is only the UI — the server makes the same call. */
      if (!acc || !aSv || !accountStock(acc, aSv)) {
        return {
          invalid: true, price: "—", eta: "—", total: 0,
          summary: T("That account is no longer available"),
          base: 0, addons: 0, days: 0,
          subtotal: 0, discount: 0, wasPrice: "", discountPrice: "",
          promoCode: "", promoLabel: "", promoEnds: ""
        };
      }
      var aTotal = accountPrice(acc);
      var aWas = accountWas(acc);
      var aSub = aWas > aTotal ? aWas : aTotal;
      var aOff = Math.round((aSub - aTotal) * 100) / 100;
      return {
        invalid: false, total: aTotal, base: aSub, addons: 0,
        subtotal: aSub, discount: aOff,
        // Accounts are the one product priced to the cent, so every figure they
        // render carries the cents flag — a total shown as $15 against a card
        // reading $14.99 is the same defect charge_for()'s cents path prevents.
        // ⚠ `cents` is what tells render() and the checkout summary to print
        // this product to the cent. Without it the summary rounds $77.99 to
        // $78 while Stripe charges 7799 — the buyer reads one number and pays
        // another. Mirrors the same flag on pricing.py's account branch.
        // ⚠ `fixed` says this figure is the same digits in every currency —
        // the accounts rule. Mirrors pricing.py's own flag, and the charge
        // skips the rate for the same reason the display does.
        cents: true, fixed: true,
        price: usd(aTotal, true, true),
        wasPrice: aOff ? usd(aSub, true, true) : "",
        discountPrice: aOff ? "−" + usd(aOff, true, true) : "",
        promoCode: "", promoLabel: aOff ? T(D.accountOfferLabel || "Offer price") : "",
        promoEnds: "",
        summary: acc.name + " · " + aSv.code,
        days: 0, eta: T(D.accountEta || "Instant delivery")
      };
    }

    /* Coaching — the booking product. Priced off the coach's rate and the hour
       pack only; the rank engine, duo, add-ons and the sitewide promo never
       touch it. Mirrors pricing.py's `service == "coaching"` branch. */
    if (s.service === "coaching") {
      var coaches = D.coaches || [], packs = D.coachPacks || [];
      var ci = Math.max(0, Math.min(coaches.length - 1, s.coach | 0));
      // Default pack is index 1 (DEFAULT.pack), matching pricing.py's
      // _idx(state.get("pack", 1)); only an OMITTED pack falls back — an explicit
      // 0 is a real selection. Kept in step so a coaching order with no pack in
      // the POST quotes the same on both sides.
      var pi = Math.max(0, Math.min(packs.length - 1, s.pack === undefined ? 1 : s.pack | 0));
      var coach = coaches[ci] || { rate: 0, name: "" };
      var pack = packs[pi] || { hours: 1, disc: 0 };
      var listed = coach.rate * pack.hours;
      var cTotal = Math.round(listed * (1 - pack.disc));
      var cDisc = listed - cTotal;
      var hrs = pack.hours + " " + T(pack.hours === 1 ? "hour" : "hours");
      return {
        invalid: false, total: cTotal, base: listed, addons: 0,
        subtotal: listed, discount: cDisc,
        price: usd(cTotal), wasPrice: cDisc ? usd(listed) : "",
        discountPrice: cDisc ? "−" + usd(cDisc) : "",
        promoCode: "", promoLabel: "", promoEnds: "",
        summary: hrs + " " + T("coaching with") + " " + coach.name,
        days: pack.hours, eta: s.slot || T("First session")
      };
    }

    if (s.service === "wins") {
      var lw = ladderOf(s.game), iw = lw.indexOf(s.from);
      // Clamped to the same 1–5 window pricing.py's _clamp() enforces. load()
      // already migrates a stored value, so this is not reachable from the UI —
      // but quote() is the mirror of the server's formula, and a mirror that
      // agrees only because a caller sanitised its input is not a mirror. With
      // this the two functions return the same number for ANY state.
      var w = Math.max(1, Math.min(5, s.wins | 0));
      var wUnit = winUnit(s.game, s.from);
      if (wUnit !== null) {
        // Per-tier win table: flat price per win within the current tier. No
        // factor/climb bonus — the table ramps by tier. Mirrors pricing.py.
        base = w * wUnit * duo;
      } else {
        var climbW = Math.max(1, iw - 1);
        base = w * per * 0.55 * factor * (1 + climbW * 0.045) * duo;
      }
      days = Math.max(1, Math.round(w * DAYS_PER_WIN));
      summary = w + " " + T(w === 1 ? "net win" : "net wins") + " · " + s.from + " · " + T(s.mode);
    } else if (s.service === "placements") {
      var lp = ladderOf(s.game), ip = lp.indexOf(s.from);
      var p = Math.max(1, Math.min(5, s.placements | 0));   // see wins, above
      var pUnit = placeUnit(s.game, s.from, s.unranked);
      if (pUnit !== null) {
        // Per-tier placement table; unranked reads the ladder floor. Mirrors pricing.py.
        base = p * pUnit * duo;
      } else {
        // Unranked: no MMR to read, so there is no starting rank to price the
        // climb off — fall back to the ladder floor (climb = 1).
        var climbP = s.unranked ? 1 : Math.max(1, ip - 1);
        base = p * per * 0.7 * factor * (1 + climbP * 0.045) * duo;
      }
      days = Math.max(1, Math.round(p * DAYS_PER_PLACEMENT));
      var where = s.unranked ? T("Unranked") : s.from;
      summary = p + " " + T(p === 1 ? "placement game" : "placement games") + " · " + where + " · " + T(s.mode);
    } else {
      var ladder = ladderOf(s.game);
      // A matching bundle is a FLAT price across its whole from-tier: every
      // division quotes as the FULL two-tier climb (the from-tier's bottom
      // division → target), so Emerald I → Diamond IV costs the same as the
      // real Emerald IV → Diamond IV work — the "two tiers up" the card
      // advertises, discounted, never a sliver of it. The buyer's real ranks
      // still show in the summary. Mirrors pricing.py.
      var bundle = s.service === "division" ? activeBundle(s) : null;
      var priceFrom = bundle ? bundle.defFrom : s.from;
      var i = ladder.indexOf(priceFrom), j = ladder.indexOf(s.to);
      var steps = j - i;
      if (steps <= 0) {
        return {
          invalid: true, price: "—", eta: "—", total: 0,
          summary: T("Target must sit above your current rank"),
          base: 0, addons: 0, days: 0,
          subtotal: 0, discount: 0, wasPrice: "", discountPrice: "",
          promoCode: "", promoLabel: "", promoEnds: ""
        };
      }
      if (D.prices && D.prices[s.game]) {
        // per-division tier table: sum the price of each rung climbed. No
        // factor/climb bonus — the table already makes higher tiers cost more.
        base = 0;
        for (var k = i + 1; k <= j; k++) base += rungPrice(s.game, ladder[k]);
        base *= duo;
        days = Math.max(1, Math.round(DAYS_SETUP + steps * DAYS_PER_RUNG));
      } else {
        var climb = Math.max(1, i - 1);
        base = steps * (D.perStep || per) * factor * (1 + climb * 0.045) * duo;
        days = Math.max(1, Math.round(DAYS_SETUP + steps * DAYS_PER_RUNG
                                      + climb * DAYS_PER_CLIMB));
      }
      summary = s.from + " → " + s.to + " · " + T(s.mode);
    }

    // Resolved BEFORE the add-ons, because on a bundle it is what they are a
    // percentage of. Mirrors pricing.py.
    var bpct = s.service === "division" ? bundleDiscount(s) : 0;

    var boost = Math.round(base);
    // An add-on is a percentage of the boost the buyer is paying for. On a
    // bundle that is the bundle's flat PRICE, not the list climb it is
    // discounted from — a bundle prices every division of its from-tier as the
    // tier's full climb, so charging 15% of that list figure billed priority on
    // a $98 order the buyer is paying $67 for, and ticking it made "Apply
    // bundle" cost MORE than not applying it. The sitewide sale deliberately
    // does NOT do this (see below). Mirrors pricing.py.
    var extra = addonTotal(bpct ? base * (1 - bpct) : base, s);
    var subtotal = boost + extra;

    // Discount comes off the boost only — the strikethrough is a real reduction,
    // never a grossed-up reference price. Add-ons are à-la-carte and NOT
    // discounted: on a small order the sale would otherwise grow by the add-on's
    // $1 floor and cancel it, so a ticked option read "+$0". Charging them on top
    // of the discounted boost keeps every add-on worth its ≥$1 in the final
    // total (boost + add-ons − discount = total). Mirrors pricing.py. A live
    // bundle replaces the sitewide sale on a matching division climb.
    var r = bpct ? { code: "BUNDLE", promo: { pct: bpct, label: "Bundle", ends: "" } }
                 : resolvePromo(s.promo, s);
    var discount = r.promo ? Math.round(boost * r.promo.pct) : 0;
    var total = subtotal - discount;

    return {
      invalid: invalid, total: total, base: Math.round(base), addons: extra,
      // The number add-ons are a percentage OF — the list boost normally, the
      // bundle's flat price on a bundle order. Mirrors `addon_base` in
      // pricing.py; the free-but-optional row strikes a figure off it.
      addonBase: bpct ? base * (1 - bpct) : base,
      subtotal: subtotal, discount: discount,
      price: usd(total), wasPrice: discount ? usd(subtotal) : "",
      discountPrice: discount ? "−" + usd(discount) : "",
      promoCode: r.code || "", promoLabel: r.promo ? r.promo.label : "",
      promoEnds: r.promo ? (r.promo.ends || "") : "",
      summary: summary, days: days,
      eta: etaText(days)
    };
  }
  window.esbQuote = quote;

  function itemParams() {
    var q = quote(state);
    return {
      currency: "USD", value: q.total,
      items: [{
        item_id: D.slugs[state.game], item_name: state.game,
        item_category: state.service, item_variant: q.summary,
        price: q.total, quantity: 1
      }]
    };
  }
  window.esbItemParams = itemParams;

  /* ── render ──────────────────────────────────────────────────────────── */
  function each(sel, fn) { Array.prototype.forEach.call(document.querySelectorAll(sel), fn); }

  /* Scroll lock behind the sheet and the auth panel.
     `body { overflow: hidden }` alone does not hold on iOS Safari — the page
     keeps scrolling under the overlay, and closing it leaves the visitor
     somewhere they never navigated to. Pinning the body is what actually
     stops touch scrolling there, so the offset is parked in a negative `top`
     and handed back on release; without that the page jumps to the top every
     time the menu is opened, which is the bug the naive fix trades for.
     `.hd-locked` stays on the body for anything already keyed off it. */
  var lockY = 0, locked = false;
  function lockScroll(on) {
    if (on === locked) return;
    locked = on;
    var b = document.body;
    if (on) {
      lockY = window.pageYOffset || document.documentElement.scrollTop || 0;
      b.style.top = -lockY + "px";
      b.classList.add("hd-locked");
    } else {
      b.classList.remove("hd-locked");
      b.style.top = "";
      // Restore before paint, and instantly: `scroll-behavior: smooth` is
      // global in ashfall.css, so a plain scrollTo animates the restore.
      window.scrollTo({ top: lockY, left: 0, behavior: "instant" });
    }
  }

  function render() {
    var q = quote(state);
    var ladder = ladderOf(state.game);
    var iFrom = ladder.indexOf(state.from), iTo = ladder.indexOf(state.to);
    var steps = iTo - iFrom;

    each("[data-out]", function (el) {
      var k = el.getAttribute("data-out");
      var v = {
        price: q.price, eta: q.eta, summary: q.summary, game: state.game,
        // Whole rank names. The marks beside them carry the numeral and the
        // tier colour; the closing band writes the rank out in words next to
        // each one, which [data-tiername] can't do — that one is the tier alone.
        fromRank: state.from, toRank: state.to,
        steps: steps > 0 ? String(steps) : "—",
        stepsWord: T(steps === 1 ? "division" : "divisions"),
        mode: T(state.mode), region: state.region,
        free: D.boostersFree, total: q.price, booster: state.booster,
        was: q.wasPrice, discount: q.discountPrice,
        promoCode: q.promoCode, promoLabel: q.promoLabel, promoEnds: q.promoEnds,
        saveLine: q.discount ? T("You save") + " " + usd(q.discount, !!q.cents)
                             + (q.promoEnds ? " · " + T("sale ends") + " " + q.promoEnds : "")
                             : "",
        // Same saving, named by the code that produced it — the order card says
        // which discount is in the price, not when the sale ends. A bundle names
        // itself rather than printing the internal "BUNDLE" code.
        saveWith: q.discount
          ? (q.promoCode === "BUNDLE"
              ? T("You save") + " " + usd(q.discount, !!q.cents) + " · " + T("bundle price")
              // A server-issued offer token names ITSELF rather than printing
              // its own 16 characters into a sentence — same treatment BUNDLE
              // gets, and for the same reason: the string is an internal
              // identifier, not something a shopper reads. The real code still
              // shows where it is useful (the modal's copy chip, the email, and
              // checkout's own discount row, which is a receipt).
              : /^(BINGO|BACK)-/.test(q.promoCode || "")
                ? T("You save") + " " + usd(q.discount, !!q.cents) + " · " + T(q.promoLabel)
              : T("You save") + " " + usd(q.discount, !!q.cents)
                + (q.promoCode ? " " + T("with") + " " + q.promoCode : ""))
          : "",
        // The saving as a bare amount, for the sticky bar's "Save $16" pill.
        // `discount` above is the signed receipt figure ("−$16"); a pill that
        // opens with a minus reads as a charge, and the word has to stay its
        // own text node to be translatable.
        saveAmt: q.discount ? usd(q.discount, !!q.cents) : "",
        summaryUpper: q.summary.toUpperCase(),
        // Per-game price for the unit tabs — one win / one placement at the
        // current rank and mode, quoted live so it tracks the rank picker.
        winsUnit: usd(quote(Object.assign({}, state, { service: "wins", wins: 1, addons: [] })).base),
        placementsUnit: usd(quote(Object.assign({}, state, { service: "placements", placements: 1, addons: [] })).base),
        // The card's config line carries the server too, so everything the
        // order is made of reads back in one line above the price.
        configLine: q.invalid ? q.summary.toUpperCase()
                              : q.summary.toUpperCase() + " · " + state.region.toUpperCase(),
        headline: q.invalid ? T("Pick a target above your current rank")
                            : q.summary + " — " + q.price,
        // Coaching CTA lead-in ("Book 3 hours"), swapped in for "Continue to
        // checkout" on that tab; the price rides in its own node after it.
        bookLabel: (function () {
          if (state.service !== "coaching") return "";
          var p = (D.coachPacks || [])[state.pack | 0];
          var h = p ? p.hours : 1;
          return T("Book") + " " + h + " " + T(h === 1 ? "hour" : "hours");
        })()
      }[k];
      if (v !== undefined) el.textContent = v;
    });

    // Discount-only nodes collapse entirely when no promo applies, so an order
    // with no discount never shows an empty row or a bare strikethrough.
    each("[data-when-discount]", function (el) { el.hidden = !q.discount; });

    // Same rule for the named booster: no booster, no row. It costs the order
    // card's fold budget nothing for everyone who didn't come from a Hire.
    each("[data-when-booster]", function (el) { el.hidden = !state.booster; });

    // Rows that belong to the boost/wins/placements products and have no place
    // on Coaching (queue, add-ons, the boosters-free line, the boost CTA verb).
    each("[data-hide-service]", function (el) {
      el.hidden = el.getAttribute("data-hide-service").split(",").indexOf(state.service) >= 0;
    });

    /* Coaching selections. Coach and pack are single-select indices; focus is a
       set of topic indices. All server-rendered, so this only marks state. */
    each("[data-coach]", function (el) {
      el.setAttribute("aria-pressed", (+el.getAttribute("data-coach") === (state.coach | 0)) ? "true" : "false");
    });
    each("[data-pack]", function (el) {
      el.setAttribute("aria-pressed", (+el.getAttribute("data-pack") === (state.pack | 0)) ? "true" : "false");
    });
    each("[data-focus]", function (el) {
      var on = (state.focus || []).indexOf(+el.getAttribute("data-focus")) >= 0;
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
    each("[data-sel-slot]", function (el) {
      fillOptions(el, D.coachSlots || []);
      el.value = state.slot || (D.coachSlots || [])[0] || "";
    });

    /* Net wins / placements 1–5 grid: one selected value per product. */
    each("[data-count]", function (el) {
      var kind = el.getAttribute("data-count");
      el.setAttribute("aria-pressed", (+el.getAttribute("data-n") === (state[kind] | 0)) ? "true" : "false");
    });
    /* Placements' rank / unranked toggle. Unranked hides the rank picker and
       shows the explanatory plate; the two share the `data-when-*` hooks. */
    each("[data-ranked]", function (el) {
      el.setAttribute("aria-pressed", ((el.getAttribute("data-ranked") === "1") === !state.unranked) ? "true" : "false");
    });
    each("[data-when-ranked]", function (el) {
      el.hidden = state.service === "placements" && !!state.unranked;
    });
    each("[data-when-unranked]", function (el) {
      el.hidden = !(state.service === "placements" && state.unranked);
    });

    /* Bundle cards. The struck price is the FULL two-tier climb at full price
       (Solo, no add-ons, no discount) — the from-tier's bottom division up to
       the target; the price beside it is the bundle's own hand-set figure, and
       it is what every division in the tier is charged. That price is read off
       the card, not recomputed: it is a number somebody set, so re-deriving it
       from a percentage here is one rounding step away from the strip quoting a
       dollar the checkout doesn't. Applied = this bundle is the active one and
       the current climb still matches it. */
    each("[data-bundle]", function (el) {
      var i = +el.getAttribute("data-bundle");
      var amt = parseFloat(el.getAttribute("data-bundle-amt")) || 0;
      var full = quote(Object.assign({}, state, {
        service: "division", mode: "Solo", addons: [], promo: "", bundle: null,
        from: el.getAttribute("data-bundle-def"), to: el.getAttribute("data-bundle-to")
      })).subtotal;
      var listEl = el.querySelector("[data-bundle-list]");
      var priceEl = el.querySelector("[data-bundle-price]");
      if (listEl) listEl.textContent = usd(full);
      if (priceEl) priceEl.textContent = usd(amt);
      var applied = state.bundle === i && state.service === "division"
        && state.to === el.getAttribute("data-bundle-to")
        && tierOf(state.game, state.from) === el.getAttribute("data-bundle-tier");
      el.setAttribute("aria-pressed", applied ? "true" : "false");
    });

    /* The climb, drawn as tier tracks — the boost-hero handoff's ladder. One
       segment per tier, striped into its division slots and filled in that
       tier's own colour across the span, with a hollow ring at the current rank
       and an accent dot at the target. You can see which tiers you cross, not
       only how many rungs are lit — the thing the price is actually for. */
    each("[data-ladder]", function (root) {
      var tiers = tiersOf(state.game);
      if (root.getAttribute("data-for") !== state.game || root.children.length !== tiers.length) {
        root.setAttribute("data-for", state.game);
        root.innerHTML = "";
        tiers.forEach(function (t) {
          var seg = document.createElement("span");
          seg.className = "ob-seg";
          seg.style.setProperty("--tier", tierColor(state.game, t));
          seg.style.setProperty("--slots", divsOf(state.game, t).length);
          var track = document.createElement("span"); track.className = "ob-seg-track";
          var fill = document.createElement("span"); fill.className = "ob-seg-fill";
          track.appendChild(fill);
          var ring = document.createElement("span"); ring.className = "ob-seg-ring";
          var dot = document.createElement("span"); dot.className = "ob-seg-dot";
          seg.appendChild(track); seg.appendChild(ring); seg.appendChild(dot);
          root.appendChild(seg);
        });
      }
      var fromT = tiers.indexOf(tierOf(state.game, state.from));
      var toT = tiers.indexOf(tierOf(state.game, state.to));
      Array.prototype.forEach.call(root.children, function (seg, ti) {
        var nodes = divsOf(state.game, tiers[ti]).map(nodeAt);
        var base = nodes[0], k = nodes.length;
        /* A division's slot-centre, as a percentage across its tier — the
           handoff's `slot(i) = ((i % 4) + 0.5) / 4`, generalised to however many
           divisions this tier actually has (CS2's rungs are one slot each). */
        var slot = function (node) { return ((node - base + 0.5) / k) * 100; };
        // The tier is crossed when the span overlaps it at all.
        var crossed = steps > 0 && iTo >= nodes[0] && iFrom <= nodes[k - 1];
        var start = crossed ? (ti === fromT ? slot(iFrom) : 0) : 0;
        var end = crossed ? (ti === toT ? slot(iTo) : 100) : 0;
        var fill = seg.querySelector(".ob-seg-fill");
        fill.style.left = start + "%";
        fill.style.width = Math.max(0, end - start) + "%";
        var ring = seg.querySelector(".ob-seg-ring");
        var dot = seg.querySelector(".ob-seg-dot");
        if (ti === fromT) { ring.style.left = slot(iFrom) + "%"; ring.hidden = false; }
        else ring.hidden = true;
        if (ti === toT && steps > 0) { dot.style.left = slot(iTo) + "%"; dot.hidden = false; }
        else dot.hidden = true;
      });
    });

    each("[data-tier-caps]", function (root) {
      var caps = tiersOf(state.game);
      /* The handoff's ladder is 7 short tiers and its names fit at full size.
         Ours run to nine and to "One Above All", so a ladder that doesn't fit
         steps down a size rather than ellipsing every label. Tier *count* is
         the wrong test — Dota's eight long names overflow where Valorant's
         eight do not — so this measures once, on the only render that can
         change the labels, and never again. */
      var rebuilt = fillCells(root, caps.length, "ob-cap", caps);
      if (rebuilt) root.setAttribute("data-dense", "0");
      /* Measured only when the strip actually has layout. The ladder lives in
         the Division panel, which is `hidden` on the three other tabs — a pass
         that runs there measures every cell as zero, concludes nothing fits and
         latches the smallest size for the rest of the visit, because the answer
         is cached per game. `data-fit` is that cache, kept separate from
         fillCells' `data-for` so a skipped measurement is retried rather than
         remembered. */
      if ((rebuilt || root.getAttribute("data-fit") !== state.game) && root.clientWidth) {
        /* Measure the TEXT, not the cell. A caption is a `1fr` flex item, so
           its box is exactly its track and its own scrollWidth equals its
           clientWidth whether the name fits or not — the previous test compared
           those two and was therefore true on every ladder, which pinned every
           game to the small step and detected nothing. A Range over the
           contents reports what the words actually measure (and, once they are
           allowed to wrap, the widest resulting line). 2px of breathing room,
           so neighbouring captions can never touch. */
        var probe = document.createRange();
        var step = 0;
        for (; step < 2; step++) {
          root.setAttribute("data-dense", String(step));
          var fits = Array.prototype.every.call(root.children, function (c) {
            probe.selectNodeContents(c);
            return probe.getBoundingClientRect().width <= c.clientWidth - 2;
          });
          if (fits) break;
        }
        root.setAttribute("data-dense", String(step));
        root.setAttribute("data-fit", state.game);
      }
      var a = caps.indexOf(tierOf(state.game, state.from));
      var b = caps.indexOf(tierOf(state.game, state.to));
      var lo = Math.min(a, b), hi = Math.max(a, b);
      Array.prototype.forEach.call(root.children, function (c, idx) {
        var within = steps > 0 && idx >= lo && idx <= hi;
        c.setAttribute("data-state", within ? "in" : "out");
        // Tint each in-span caption in its own tier's colour — the same colour
        // the ladder segment above it fills with, so the two read as one mark.
        c.style.setProperty("--tier", tierColor(state.game, caps[idx]));
      });
    });

    // rank marks: the division numeral, tinted by the tier it belongs to
    each("[data-mark]", function (el) {
      var rank = el.getAttribute("data-mark") === "to" ? state.to : state.from;
      el.textContent = divOf(state.game, rank);
      el.style.setProperty("--tier", tierColor(state.game, tierOf(state.game, rank)));
    });

    // the tier name beside each panel's mark
    each("[data-tiername]", function (el) {
      var rank = el.getAttribute("data-tiername") === "to" ? state.to : state.from;
      el.textContent = tierOf(state.game, rank);
    });

    /* The rank plate's tier name never ellipses (the configurator handoff's
       rule, and why it is 17px rather than 19px). That size was measured
       against League, whose longest name fits; "Grandmaster" and "One Above
       All" do not, so the plate steps down instead of truncating — the same
       trade [data-tier-caps] makes for the ladder captions.

       Measured off the game's WIDEST tier name, not the one on screen: sizing
       to the current name would resize the type under the reader on every tier
       change, and would leave the two plates at different sizes. Runs once per
       game, and not at all while the panel is hidden (clientWidth 0). */
    each("[data-tierfit]", function (root) {
      var el = root.querySelector("[data-tiername]");
      if (!el || !root.clientWidth || root.getAttribute("data-for") === state.game) return;
      root.setAttribute("data-for", state.game);
      var names = tiersOf(state.game), keep = el.textContent, step = 0;
      for (; step < 3; step++) {
        root.setAttribute("data-dense", String(step));
        var fits = names.every(function (n) {
          el.textContent = n;
          return el.scrollWidth <= root.clientWidth;
        });
        if (fits) break;
      }
      root.setAttribute("data-dense", String(step));
      el.textContent = keep;
    });

    // Whole rank names that carry the tier colour themselves (the closing band's
    // climb line), so "Iron IV → Gold IV" reads tinted without a separate mark.
    each("[data-rankcolor]", function (el) {
      var rank = el.getAttribute("data-rankcolor") === "to" ? state.to : state.from;
      el.style.setProperty("--tier", tierColor(state.game, tierOf(state.game, rank)));
    });

    /* Tier grids. Selection follows the panel's own end; a tier with no node
       this end could occupy is disabled, never silently corrected. */
    each("[data-tiergrid]", function (root) {
      var which = root.getAttribute("data-tiergrid");
      var tiers = tiersOf(state.game);
      if (root.getAttribute("data-for") !== state.game || root.children.length !== tiers.length) {
        root.setAttribute("data-for", state.game);
        buildTierGrid(root, which);
      }
      var here = tierOf(state.game, which === "to" ? state.to : state.from);
      Array.prototype.forEach.call(root.children, function (b, i) {
        b.setAttribute("aria-pressed", tiers[i] === here ? "true" : "false");
        b.disabled = !tierOk(which, tiers[i]);
      });
    });

    // region chips
    each("[data-regions]", function (root) {
      var list = D.regions[state.game] || [];
      if (root.getAttribute("data-for") !== state.game || root.children.length !== list.length) {
        root.setAttribute("data-for", state.game);
        buildRegions(root);
      }
      Array.prototype.forEach.call(root.children, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-region") === state.region ? "true" : "false");
      });
    });

    /* Read-only rail: the span you chose, drawn over the whole ladder. It is
       deliberately not an input — a click on a two-ended range has to guess
       which end you meant, which is the ambiguity the two panels removed. */
    var span = Math.max(1, ladder.length - 1);
    each("[data-rail]", function (root) {
      var a = (iFrom / span) * 100, b = (iTo / span) * 100;
      var fill = root.querySelector(".bs-rail-fill");
      var h1 = root.querySelector(".bs-rail-h1"), h2 = root.querySelector(".bs-rail-h2");
      if (fill) { fill.style.left = a + "%"; fill.style.width = Math.max(0, b - a) + "%"; }
      if (h1) h1.style.left = a + "%";
      if (h2) h2.style.left = b + "%";
    });

    each("[data-rail-caps]", function (root) {
      var tiers = tiersOf(state.game);
      if (root.getAttribute("data-for") !== state.game || root.children.length !== tiers.length) {
        root.setAttribute("data-for", state.game);
        root.innerHTML = "";
        tiers.forEach(function (t) {
          var s2 = document.createElement("span");
          s2.className = "bs-railcap";
          s2.textContent = t;
          // centred on the tier's middle node, so a caption sits over the run
          // of ticks it names rather than at an evenly-spaced slot
          var nodes = divsOf(state.game, t).map(nodeAt);
          var mid = (nodes[0] + nodes[nodes.length - 1]) / 2;
          s2.style.left = (mid / span) * 100 + "%";
          root.appendChild(s2);
        });
      }
      var lo = tiers.indexOf(tierOf(state.game, state.from));
      var hi = tiers.indexOf(tierOf(state.game, state.to));
      Array.prototype.forEach.call(root.children, function (c, i) {
        c.setAttribute("data-state", (i >= lo && i <= hi) ? "in" : "out");
      });
    });

    // subdivision segments — sub-ranks within the tier of each endpoint
    each("[data-subseg]", function (root) {
      var which = root.getAttribute("data-subseg");
      var rank = which === "from" ? state.from : state.to;
      buildSubseg(root, which, divsOf(state.game, tierOf(state.game, rank)), rank);
    });

    // "Add options" and any other link that follows the selected game
    each("[data-game-link]", function (el) {
      el.setAttribute("href", "/games/" + D.slugs[state.game] + "#configure");
    });

    // game tags (home switcher)
    each("[data-game-tag]", function (el) {
      el.setAttribute("aria-pressed", el.getAttribute("data-game-tag") === state.game ? "true" : "false");
    });

    // selects
    each("[data-sel]", function (el) {
      var k = el.getAttribute("data-sel");
      if (k === "game") { if (el.value !== state.game) el.value = state.game; }
      else if (k === "from" || k === "to") {
        fillOptions(el, ladder);
        el.value = k === "from" ? state.from : state.to;
      } else if (k === "fromTier" || k === "toTier") {
        var side = k === "fromTier" ? "from" : "to";
        fillOptions(el, tiersOf(state.game));
        // Out-of-range tiers become disabled <option>s — the same limit the
        // desktop grid shows, carried into the native control mobile uses.
        Array.prototype.forEach.call(el.options, function (o) {
          o.disabled = !tierOk(side, o.value);
        });
        el.value = tierOf(state.game, side === "from" ? state.from : state.to);
      } else if (k === "region") {
        fillOptions(el, D.regions[state.game] || []);
        el.value = state.region;
      }
    });

    // mode radios
    each("input[data-mode]", function (el) { el.checked = el.value === state.mode; });

    // service tabs
    each("[role=tab][data-service]", function (el) {
      var on = el.getAttribute("data-service") === state.service;
      el.setAttribute("aria-selected", on ? "true" : "false");
      el.tabIndex = on ? 0 : -1;
    });
    each("[data-panel]", function (el) {
      el.hidden = el.getAttribute("data-panel") !== state.service;
    });

    // steppers
    each("[data-stepper]", function (el) {
      var k = el.getAttribute("data-stepper");
      el.querySelector("output").textContent = state[k];
    });

    // addons
    each("input[data-addon]", function (el) {
      var id = el.getAttribute("data-addon");
      var a = addonById(id);
      // A zero-cost add-on is always on, and is never carried in state.addons —
      // it has to render ticked or "Included" sits next to an empty box and
      // reads as the opposite of what it says. The ONE exception is the
      // free-but-optional row (`was_pct`, see data.py): it costs nothing but is
      // still a choice, so it is driven by state like any paid option and opens
      // UNTICKED. Forcing it on would both misreport what the buyer asked for
      // and put a permanent tick beside a struck price.
      el.checked = (a && a.pct === 0 && !isFreeOpt(a))
                || (state.addons || []).indexOf(id) >= 0;
    });

    /* The mode-conditional pair, and the per-game name of the picks add-on.
       Both ship every variant in the DOM with all but one hidden, rather than
       being written in by JS: i18n.js matches whole text nodes, so a label this
       pass invented would arrive untranslated. */
    each("[data-when-mode]", function (el) {
      el.hidden = !addonApplies(el.getAttribute("data-when-mode"), state.mode);
    });
    each("[data-when-game]", function (el) {
      el.hidden = el.getAttribute("data-when-game") !== state.game;
    });

    // continue buttons disabled on an impossible pair
    each("[data-continue]", function (el) {
      el.classList.toggle("is-disabled", !!q.invalid);
      el.setAttribute("aria-disabled", q.invalid ? "true" : "false");
    });

    // checkout breakdown
    each("[data-sum]", function (el) {
      var k = el.getAttribute("data-sum");
      // Every figure in the breakdown is printed at the QUOTE's precision, not
      // at a fixed one: accounts are quoted to the cent and every boosting
      // product to the whole unit, and a summary that rounds one of them
      // disagrees with what Stripe is asked to charge.
      var m = function (v) { return usd(v, !!q.cents, !!q.fixed); };
      var map = {
        base: m(q.base), addons: q.addons ? "+ " + m(q.addons) : "—",
        total: m(q.total), eta: q.eta, summary: q.summary,
        game: state.game, region: state.region, mode: T(state.mode),
        booster: state.booster, was: q.wasPrice, discount: q.discountPrice,
        discountLabel: q.promoLabel
          ? T(q.promoLabel) + (q.promoCode ? " · " + q.promoCode : "") : "",
        /* There is no "climb" key any more. It used to carry the Climb row's
           words, and on a division boost it named only the TARGET tier —
           "Gold · Solo" — on the theory that the two marks beside it said the
           rest. They don't: the marks are division numerals, so an Iron IV →
           Gold IV order rendered "IV → IV Gold · Solo" and never said where the
           buyer started. Both cards now draw the pair as mark + [data-tiername]
           and take the mode from [data-out="mode"], so the row is markup and
           the unit services read [data-sum="summary"] directly. */
        /* The listing's own name, for the Account row. `summary` carries the
           shard too, which is what the row actually prints — this is here so a
           surface that wants the name alone does not have to split a string. */
        account: ((D.accounts || {})[state.account] || {}).name || "",
        addonlist: (state.addons || []).map(function (id) {
          var a = addonById(id);
          return a ? T(addonLabel(a)) : id;
        }).join(", ") || T("None")
      };
      if (map[k] !== undefined) el.textContent = map[k];
    });

    // Inline error, shown only when the chosen pair is invalid (target at or
    // below the current rank). Its text is the whole translatable node
    // "Target must sit above your current rank".
    each("[data-when-invalid]", function (el) { el.hidden = !q.invalid; });

    /* The closing band on a page with no configurator of its own. Both states
       ship in the DOM — the handoff's catalogue-floor fallback and a read-back
       of the visitor's own order — and this picks one. It is not a fabricated
       default: it swaps only when there is a REAL stored order behind it, which
       is also why the server renders the fallback (a static page is cached for
       everybody and cannot know which it is).

       Coaching is deliberately not read back. It is a booking, not a climb:
       "Your climb starts at €79" over a card with an empty Climb row describes
       nothing the visitor bought, and re-quoting their ranks as a boost to fill
       it would invent a price they were never shown. */
    if (FCB) {
      /* Neither booking nor account is read back. "Your climb starts at €62"
         over a card whose Climb row names a Gold account describes nothing that
         was bought, and re-quoting the stored ranks as a boost to fill it would
         invent a price the visitor was never shown. */
      var back = HYDRATED && !q.invalid
        && state.service !== "coaching" && state.service !== "account";
      each("[data-fc-when]", function (el) {
        el.hidden = (el.getAttribute("data-fc-when") === "order") !== back;
      });
      FCB.classList.toggle("fc-solo", !back);
    }

    // Money rows that only exist when they carry a number.
    each("[data-when-addons]", function (el) { el.hidden = !q.addons; });
    each("[data-when-no-discount]", function (el) { el.hidden = !!q.discount; });
    /* "units" is the two unit services together — wins and placements have no
       rank pair, so anything drawn as a climb needs one node for the pair and
       one for everything else, not one node per service. */
    each("[data-when-service]", function (el) {
      var want = el.getAttribute("data-when-service");
      el.hidden = want === "units" ? state.service === "division"
                                   : want !== state.service;
    });

    /* Selected add-ons as receipt rows, so the checkout column can be read
       down: boost + each add-on − discount = total.

       Each row is the difference between two SUBTOTALS, taken in order, which
       makes the arithmetic exact: the boost row is quote(no add-ons).subtotal
       and the rows telescope up to quote(all).subtotal, whatever the rounding.
       They are therefore pre-discount prices — the discount row below takes its
       cut off the lot. That is deliberately not the same figure as the "+$N" on
       the picker above, which answers a different question (what ticking this
       box does to the total, discount and all); the discount row between them
       is what reconciles the two. */
    each("[data-addon-lines]", function (root) {
      var ids = (state.addons || []).filter(function (id) {
        var a = addonById(id);
        // Never a row for something the quote does not charge — a free
        // inclusion, or an option belonging to the queue this order is not in.
        return a && a.pct !== 0 && addonApplies(a.mode, state.mode);
      });
      root.innerHTML = "";
      if (q.invalid) return;
      var running = [];
      var prev = quote(Object.assign({}, state, { addons: [] })).subtotal;
      ids.forEach(function (id) {
        var a = addonById(id);
        running = running.concat([id]);
        var now = quote(Object.assign({}, state, { addons: running })).subtotal;
        var row = document.createElement("div");
        row.className = "co-line";
        var lab = document.createElement("span");
        lab.className = "co-lab";
        lab.textContent = T(addonLabel(a));
        var val = document.createElement("span");
        val.className = "co-val";
        val.textContent = usd(now - prev);
        row.appendChild(lab);
        row.appendChild(val);
        root.appendChild(row);
        prev = now;
      });
    });

    /* Add-on prices in dollars: what having this option actually costs on this
       order, all else equal. Quoting the difference rather than base × pct means
       the figure already accounts for the discount, so it matches the change the
       buyer sees in the total when they tick the box. */
    each("[data-addon-price]", function (el) {
      var id = el.getAttribute("data-addon-price");
      var without = (state.addons || []).filter(function (x) { return x !== id; });
      var off = quote(Object.assign({}, state, { addons: without })).total;
      var on = quote(Object.assign({}, state, { addons: without.concat([id]) })).total;
      el.textContent = q.invalid ? "—" : "+" + usd(on - off);
    });

    /* The struck reference figure on a free-but-optional row. Quoted off this
       order's own addonBase by the same formula a real charge would use, so it
       tracks the climb the way every other number on the card does — a fixed
       "$40" beside a $12 boost is the thing that makes a struck price read as
       invented. It is DISPLAY ONLY: nothing here feeds a total, and the row's
       [data-addon-price] beside it still quotes the real +$0. */
    each("[data-addon-was]", function (el) {
      var was = addonListPrice(q.addonBase, el.getAttribute("data-addon-was"));
      el.textContent = q.invalid || !was ? "" : usd(was);
      el.hidden = !!q.invalid || !was;
    });

    document.dispatchEvent(new CustomEvent("esb:render", { detail: { state: state, quote: q } }));
  }
  window.esbRender = render;

  /* Both text-fitting passes above ([data-tier-caps] and [data-tierfit]) measure
     once and cache the answer against the game. On a cold cache the first render
     happens before Inter has loaded, so they would measure the fallback face and
     keep that verdict for the whole visit — a name that fits in the fallback and
     not in Inter would then overlap its neighbour and never be re-checked. Drop
     the caches once the real font is in and render again. */
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      each("[data-tier-caps]", function (el) { el.removeAttribute("data-fit"); });
      each("[data-tierfit]", function (el) { el.removeAttribute("data-for"); });
      render();
    });
  }

  /* ── the sticky bar's clearance, measured rather than assumed ─────────────
     `body.has-bar` reserves the bar's height at the foot of the page so the last
     row of content is reachable rather than pinned under a fixed element. That
     reserve used to be four hand-set constants (116 / 146 coaching / 146 below
     360px / 150 checkout), each measured against one configuration — and the
     measurement they share is the one thing on the bar that MOVES: `.mb-money`
     is `flex-wrap: wrap`, so the save pill drops to a second line whenever the
     price, its struck original and the pill stop fitting on one, and the bar
     goes 109px → 139px.

     Which totals do that is not a property of the page, it is a property of the
     number: a three-figure total already wraps at 375px in dollars and euros,
     where the constant assumed only sub-360px phones and the coaching CTA could,
     and adding CAD — a "C$" prefix over an amount 1.37× the dollar one — pushes
     far more orders across the line. Chasing that with a fifth constant per
     currency is not a thing anyone can keep true.

     So the bar is measured and the reserve follows it, the same way `--hd-top`
     follows the header's live bottom edge. The constants stay in the CSS as the
     `var()` fallbacks, which is what a no-JS page and the moment before the
     first measurement still get. */
  function initBarReserve() {
    var bar = document.querySelector(".mobile-bar");
    if (!bar) return;
    var last = -1;
    function measure() {
      // Above the bar's breakpoint it is `display: none` and measures 0. Writing
      // that would hand the page a zero reserve; clearing the property instead
      // drops it back to the CSS constant, which is inert while the bar is gone.
      // `translateY`/`visibility` on the un-revealed bar do not change its
      // height, so this is correct before the reveal as well as after.
      var h = Math.ceil(bar.getBoundingClientRect().height);
      if (h === last) return;
      last = h;
      if (h > 0) document.documentElement.style.setProperty("--mb-h", h + "px");
      else document.documentElement.style.removeProperty("--mb-h");
    }
    measure();
    // Every re-quote can change the number of lines the money takes, so the one
    // event that fires on each is the hook. render() dispatches it after its
    // writes, so the read here reflects the total that is now on screen.
    document.addEventListener("esb:render", measure);
    var rt;
    window.addEventListener("resize", function () {
      clearTimeout(rt); rt = setTimeout(measure, 150);
    });
    // A cold cache measures the fallback face; Inter is wider at these sizes and
    // can be what tips the line into wrapping.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
  }

  /* Rebuild a fixed-length strip of spans only when it no longer matches the
     game it was built for — two games can share a rung count (LoL and Rocket
     League both have 29), so the count alone is not enough of a guard. */
  function fillCells(root, n, cls, labels) {
    if (root.getAttribute("data-for") === state.game && root.children.length === n) return false;
    root.setAttribute("data-for", state.game);
    root.innerHTML = "";
    for (var i = 0; i < n; i++) {
      var s = document.createElement("span");
      s.className = cls;
      if (labels) s.textContent = labels[i];
      root.appendChild(s);
    }
    return true;                                   // caller may need to measure
  }

  function fillOptions(sel, list) {
    var current = Array.prototype.map.call(sel.options, function (o) { return o.value; }).join("|");
    if (current === list.join("|")) return;
    sel.innerHTML = "";
    list.forEach(function (r) {
      var o = document.createElement("option");
      o.value = r; o.textContent = r;
      sel.appendChild(o);
    });
  }

  /* ── rank picking ─────────────────────────────────────────────────────
     Ranks are flat node indices, so a division inside a tier and a tier
     boundary are the same kind of step.

     **Clamp the end the user touched; never move the other one.** Moving the
     untouched end is how "set a target" used to silently demote the player's
     current rank, and how Bronze IV → Bronze III became unorderable. What is
     out of range is rendered disabled instead, so the limit is visible before
     the tap rather than corrected after it. ────────────────────────────── */
  function nodeAt(rank) { return ladderOf(state.game).indexOf(rank); }

  // The bundle to keep after a prospective from/to change: it survives a
  // division change (same from-tier, same target) and drops otherwise.
  function bundleAfter(from, to) {
    if (state.bundle === null || state.bundle === undefined) return null;
    var b = ((D.bundles && D.bundles[state.game]) || [])[state.bundle | 0];
    return (b && tierOf(state.game, from) === b.ft && to === b.target) ? state.bundle : null;
  }

  function setNode(which, i) {
    var l = ladderOf(state.game);
    // Every rank is selectable: set exactly the end the user touched (clamped
    // only to the ladder's own range) and never move the other one. A target
    // at or below the current rank is allowed through and surfaces as an inline
    // error via quote().invalid, rather than being blocked before the tap.
    i = Math.min(Math.max(0, i), l.length - 1);
    if (which === "to") {
      if (l[i] !== state.to) set({ to: l[i], bundle: bundleAfter(state.from, l[i]) }, "add_to_cart");
    } else {
      if (l[i] !== state.from) set({ from: l[i], bundle: bundleAfter(l[i], state.to) }, "add_to_cart");
    }
  }

  // Every rank is now reachable for either end — an out-of-range pair is shown
  // as an error, not disabled. Kept as a hook so the render sites read the same.
  function nodeOk() { return true; }

  // one division segment (Current / Target): a button per sub-rank of the tier.
  // An LP-based tier (Immortal, Master, CS2's flat rungs) has no divisions to
  // pick, so the row renders nothing rather than a dead "no divisions" button —
  // CSS hides the empty container off data-single.
  function buildSubseg(root, which, opts, current) {
    var single = opts.length <= 1;
    root.setAttribute("data-single", single ? "true" : "false");
    root.innerHTML = "";
    if (single) return;
    opts.forEach(function (full) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "seg-opt seg-sub-opt";
      b.textContent = divOf(state.game, full);
      b.setAttribute("aria-pressed", full === current ? "true" : "false");
      if (!nodeOk(which, nodeAt(full))) b.disabled = true;
      else b.addEventListener("click", function () { setNode(which, nodeAt(full)); });
      root.appendChild(b);
    });
  }

  /* Switching tier keeps the division numeral you were already on — Bronze IV
     → Silver IV is one click, not a trip back through the division row. */
  function tierNode(which, tier) {
    var cur = which === "to" ? state.to : state.from;
    var here = divsOf(state.game, tierOf(state.game, cur));
    var off = Math.max(0, here.indexOf(cur));
    var next = divsOf(state.game, tier);
    return nodeAt(next[Math.min(off, next.length - 1)]);
  }

  // Every tier is selectable for either end now; an impossible pair errors
  // rather than disabling the tile. Kept so the render sites read one hook.
  function tierOk() { return true; }

  function setTier(which, tier) { setNode(which, tierNode(which, tier)); }

  // tier grid (Best Sellers band): one button per tier, out-of-range disabled
  function buildTierGrid(root, which) {
    var tiers = tiersOf(state.game);
    root.innerHTML = "";
    tiers.forEach(function (t) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "bs-tierbtn";
      b.textContent = t;
      b.addEventListener("click", function () { if (!b.disabled) setTier(which, t); });
      root.appendChild(b);
    });
  }

  // region chips (Best Sellers band)
  function buildRegions(root) {
    var list = D.regions[state.game] || [];
    var shortMap = D.regionShort || {};
    root.innerHTML = "";
    list.forEach(function (r) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "bs-regionbtn";
      b.setAttribute("data-region", r);
      // Both labels ship; CSS shows the short one only where the chips truncate
      // (phone width). The value carried into state is always the full name.
      var full = document.createElement("span");
      full.className = "bs-region-full"; full.textContent = r;
      var abbr = document.createElement("span");
      abbr.className = "bs-region-abbr"; abbr.textContent = shortMap[r] || r;
      b.appendChild(full); b.appendChild(abbr);
      b.addEventListener("click", function () { set({ region: r, regionPicked: true }); });
      root.appendChild(b);
    });
  }

  /* ── wiring ──────────────────────────────────────────────────────────── */
  /* Switching game resets the climb to a sensible mid-ladder default rather
     than trying to carry ranks across two different ladders. */
  /* Move the order onto another game. The ranks cannot travel — the ladders
     name different rungs — so they come from THAT game's own record if the
     visitor has configured it before, and from its ladder default if they
     haven't. Everything that is not about a ladder travels with them, because
     it is what they were just touching (see SHARED).

     Switching used to reset the climb to the ladder default every time, so a
     visitor comparing two titles in the band lost the first one's climb the
     moment they looked at the second. */
  function ensureGame(game) {
    if (state.game === game) return;
    save();                                   // park the game being left
    var rec = readRecord(keyFor(game)) || {};
    SHARED.forEach(function (k) { rec[k] = state[k]; });
    Object.assign(state, normalize(rec, game));
    save();
  }

  /* Discount code. The auto promo is already in the price, so this only ever
     reports something the buyer can act on: a better code took effect, or the
     one they typed isn't valid. A weaker code is accepted silently rather than
     downgrading a price they were already quoted. */
  function wirePromo() {
    var input = document.querySelector("[data-promo]");
    if (!input) return;
    var msg = document.querySelector("[data-promo-msg]");
    var apply = document.querySelector("[data-promo-apply]");

    /* The field starts closed behind "Have a code?". An empty input whose
       placeholder claims a code is already applied reads as the opposite of
       what it says — the applied state is now stated in words beside the
       toggle, and this only opens for a second, better code. Both label
       variants are in the DOM so i18n can translate whole text nodes; the
       toggle just flips aria-expanded and CSS shows the right one. */
    var toggle = document.querySelector("[data-promo-toggle]");
    var box = document.querySelector("[data-promo-box]");
    if (toggle && box) {
      toggle.addEventListener("click", function () {
        var open = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        box.hidden = !open;
        if (open) input.focus();
      });
    }

    if (state.promo) {
      input.value = state.promo;
      // A code carried over from an earlier visit stays visible — hiding the
      // thing the buyer typed is the bug this row was redesigned to fix.
      if (toggle && box) { toggle.setAttribute("aria-expanded", "true"); box.hidden = false; }
    }

    function say(text, ok) {
      if (!msg) return;
      msg.textContent = text;
      msg.setAttribute("data-ok", ok ? "1" : "0");
    }

    /* A server-issued offer token pasted into the box. `data.js` cannot hold
       these — that is the whole reason they exist — so an unknown code that
       LOOKS like one gets one server lookup before it is called invalid. The
       modal already applies the discount for the buyer; this is for the person
       who closed the tab, found the code in their inbox and typed it in, and
       without it their own code would be refused by their own checkout. */
    var TOKEN_RE = /^(BINGO|BACK)-[A-Z0-9]{6,20}$/;
    function resolveToken(typed) {
      var path = typed.indexOf("BINGO-") === 0 ? "/api/bingo" : "/api/cart";
      return fetch(path + "?token=" + encodeURIComponent(typed))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (!j || !j.valid) return false;
          var slot = typed.indexOf("BINGO-") === 0 ? "ESB_BINGO" : "ESB_RECOVERY";
          window[slot] = { token: j.token, pct: j.pct, label: j.label || "" };
          return true;
        }).catch(function () { return false; });
    }

    function submit() {
      var typed = input.value.trim().toUpperCase();
      if (!typed) { set({ promo: "" }); say("", true); return; }

      if (TOKEN_RE.test(typed) && !D.promos[typed] && window.fetch
          && !(window.ESB_BINGO && window.ESB_BINGO.token === typed)
          && !(window.ESB_RECOVERY && window.ESB_RECOVERY.token === typed)) {
        say(T("Checking that code…"), true);
        resolveToken(typed).then(function (ok) {
          if (!ok) { set({ promo: "" }); say(T("That code isn't valid. Your price is unchanged."), false); return; }
          submit();                       // now it resolves like any other code
        });
        return;
      }

      var before = quote(state).total;
      set({ promo: typed });
      var q = quote(state);

      if (q.promoCode === typed) {
        say(T("Code applied") + " — " + T("you save") + " " + usd(q.discount), true);
      } else if (D.promos && D.promos[typed]) {
        say(T("Your current price is already better than that code."), true);
      } else {
        set({ promo: "" });
        say(T("That code isn't valid. Your price is unchanged."), false);
      }
      if (before !== quote(state).total) track("select_promotion", itemParams());
    }

    if (apply) apply.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
    });
    input.addEventListener("blur", submit);
  }

  function param(name) {
    var m = new RegExp("[?&]" + name + "=([^&#]*)").exec(location.search);
    return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : "";
  }

  /* A booster named by a roster Hire or a profile CTA (?booster=<handle>).

     Validated against the roster the build shipped, never trusted from the
     URL: an unknown handle is dropped rather than rendered, and a handle for
     a different game than the page is pinned to is dropped too — otherwise a
     link could put "Ordering with vantaa" on the Valorant page. It reaches the
     order as an attribute only; quote() does not read it and pricing.py has no
     fee for it, so nothing here can move a price. */
  function wireNamedBooster(pinned) {
    var handle = param("booster");
    var roster = D.boosters || {};
    if (handle && roster[handle]) {
      if (!pinned) ensureGame(roster[handle]);
      if (roster[handle] === state.game) set({ booster: handle });
    }
    each("[data-booster-clear]", function (el) {
      el.addEventListener("click", function () {
        set({ booster: "" });
        // Drop the param too, or a reload re-attaches the booster the customer
        // just took off.
        if (window.history && history.replaceState) {
          history.replaceState({}, "", location.pathname + location.hash);
        }
      });
    });
  }

  function wire() {
    // page-scoped game (game detail pages)
    var cfg = document.querySelector("[data-configurator]");
    var pinned = cfg && cfg.getAttribute("data-game");
    if (pinned) ensureGame(pinned);
    wireNamedBooster(!!pinned);

    wirePromo();

    each("[data-game-tag]", function (el) {
      el.addEventListener("click", function () {
        ensureGame(el.getAttribute("data-game-tag"));
        set({}, "select_item");        // render() rebuilds grids/chips/rail
      });
    });

    each("[data-sel]", function (el) {
      el.addEventListener("change", function () {
        var k = el.getAttribute("data-sel");
        if (k === "game") { ensureGame(el.value); set({}, "select_item"); }
        else if (k === "from") set({ from: el.value }, "add_to_cart");
        else if (k === "to") set({ to: el.value }, "add_to_cart");
        else if (k === "fromTier") setTier("from", el.value);
        else if (k === "toTier") setTier("to", el.value);
        else if (k === "region") set({ region: el.value, regionPicked: true });
      });
    });

    each("input[data-mode]", function (el) {
      el.addEventListener("change", function () {
        // Switching queue takes the other queue's add-on off the order with it.
        // Leaving it in state would list a row on the receipt that the server
        // (which applies the same filter) does not charge for.
        if (el.checked) set({ mode: el.value, addons: addonsFor(state.addons, el.value) },
                            "select_item");
      });
    });

    each("[role=tab][data-service]", function (el) {
      el.addEventListener("click", function () { set({ service: el.getAttribute("data-service") }, "select_item"); });
      el.addEventListener("keydown", function (e) {
        var tabs = Array.prototype.slice.call(document.querySelectorAll("[role=tab][data-service]"));
        var i = tabs.indexOf(el);
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          var n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
          n.focus(); n.click();
        }
      });
    });

    each("[data-stepper]", function (el) {
      var k = el.getAttribute("data-stepper");
      var min = +el.getAttribute("data-min") || 1;
      var max = +el.getAttribute("data-max") || 20;
      el.querySelectorAll("[data-step]").forEach(function (b) {
        b.addEventListener("click", function () {
          var v = Math.min(max, Math.max(min, state[k] + (+b.getAttribute("data-step"))));
          var patch = {}; patch[k] = v;
          set(patch, "add_to_cart");
        });
      });
    });

    each("input[data-addon]", function (el) {
      el.addEventListener("change", function () {
        var id = el.getAttribute("data-addon");
        var list = (state.addons || []).slice();
        var at = list.indexOf(id);
        if (el.checked && at < 0) list.push(id);
        if (!el.checked && at >= 0) list.splice(at, 1);
        set({ addons: list }, "add_to_cart");
      });
    });

    /* Net wins / placements 1–5 grid. */
    each("[data-count]", function (el) {
      el.addEventListener("click", function () {
        var patch = {}; patch[el.getAttribute("data-count")] = +el.getAttribute("data-n");
        set(patch, "add_to_cart");
      });
    });
    /* Placements' rank / unranked toggle. */
    each("[data-ranked]", function (el) {
      el.addEventListener("click", function () { set({ unranked: el.getAttribute("data-ranked") === "0" }, "select_item"); });
    });

    /* Coaching controls — coach and pack are single-select, focus toggles. */
    each("[data-coach]", function (el) {
      el.addEventListener("click", function () { set({ coach: +el.getAttribute("data-coach") }, "select_item"); });
    });
    each("[data-pack]", function (el) {
      el.addEventListener("click", function () { set({ pack: +el.getAttribute("data-pack") }, "add_to_cart"); });
    });
    each("[data-focus]", function (el) {
      el.addEventListener("click", function () {
        var i = +el.getAttribute("data-focus");
        var f = (state.focus || []).slice();
        var at = f.indexOf(i);
        if (at >= 0) f.splice(at, 1); else f.push(i);
        set({ focus: f });
      });
    });
    each("[data-sel-slot]", function (el) {
      el.addEventListener("change", function () { set({ slot: el.value }); });
    });

    /* Bundle cards — one click configures a popular climb on the boost tab.
       Keeps the visitor's current division within the lower tier when it can,
       so "from any Platinum division" is honoured rather than reset. */
    each("[data-bundle]", function (el) {
      el.addEventListener("click", function () {
        var i = +el.getAttribute("data-bundle");
        var tier = el.getAttribute("data-bundle-tier");
        var to = el.getAttribute("data-bundle-to");
        var def = el.getAttribute("data-bundle-def");
        // Toggle off if this bundle is already the applied one.
        if (state.bundle === i && state.service === "division"
            && state.to === to && tierOf(state.game, state.from) === tier) {
          set({ bundle: null }); return;
        }
        // Keep the visitor's current division within the lower tier when we can,
        // so "from any Platinum division" is honoured rather than reset.
        var from = def, curDiv = divOf(state.game, state.from);
        divsOf(state.game, tier).forEach(function (r) {
          if (divOf(state.game, r) === curDiv) from = r;
        });
        var l = ladderOf(state.game);
        if (l.indexOf(from) >= l.indexOf(to)) from = def;
        set({ service: "division", from: from, to: to, bundle: i }, "select_item");
        // A bundle starts "from any division" in the lower tier, so the visitor
        // still has to name their current division. Send them up to the "from"
        // rank plate in the configurator, which the bundle strip sits below on
        // the phone, so the one input they must confirm is on screen.
        // scrollIntoView is unusable here: .hero-a is overflow:hidden and traps
        // it, so compute the target and scroll the window past the sticky header.
        var plate = document.querySelector(
          '[data-panel="division"] [data-rankcolor="from"]');
        if (plate) {
          var hd = document.querySelector("[data-hd]");
          var pad = (hd ? hd.getBoundingClientRect().height : 0) + 16;
          var top = plate.getBoundingClientRect().top + window.pageYOffset - pad;
          window.scrollTo(
            { top: Math.max(0, top), left: 0,
              behavior: reduceMotion() ? "auto" : "smooth" });
        }
      });
    });

    // begin_checkout fires BEFORE navigation — the number the audit asked for.
    // Commit this configurator's order into the shared checkout snapshot so
    // the checkout page charges exactly what was configured here.
    each("[data-continue]", function (el) {
      el.addEventListener("click", function (e) {
        if (quote(state).invalid) { e.preventDefault(); return; }
        try { localStorage.setItem(CHECKOUT_KEY, JSON.stringify(state)); } catch (e2) {}
        track("begin_checkout", itemParams());
      });
    });

    // Radio-group arrow keys for every row of buttons in the band, and for the
    // roster's filter chips / segmented controls.
    each("[data-tiergrid], [data-subseg], [data-regions], .rst-chips, .rst-seg, .bp-chips, "
       + ".rvp-chips, .rvp-seg, .ob-packs, .ob-focuses, .ob-counts, .ob-ranked",
      function (root) {
      root.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var btns = Array.prototype.slice.call(root.children)
          .filter(function (b) { return !b.disabled; });
        var i = btns.indexOf(document.activeElement);
        if (i < 0) return;
        e.preventDefault();
        btns[(i + (e.key === "ArrowRight" ? 1 : btns.length - 1)) % btns.length].focus();
      });
    });

    /* The game page's FAQ is single-open: opening one closes the rest. Native
       <details>, so every answer is in the DOM and the band still works with no
       JS — this only enforces the "one at a time" the handoff draws. */
    each("[data-gp-faq]", function (root) {
      var items = Array.prototype.slice.call(root.querySelectorAll("details"));
      items.forEach(function (d) {
        d.addEventListener("toggle", function () {
          if (!d.open) return;
          items.forEach(function (o) { if (o !== d) o.open = false; });
        });
      });
    });

    if (document.querySelector(".mobile-bar")) {
      document.body.classList.add("has-bar");
      // Coaching's CTA ("Book 3 hours") is a wider label than "Checkout", so on
      // that tab the money line wraps the save pill and the sticky bar grows
      // ~30px. Only the three coaching-capable games have that tab; flag them so
      // the page reserves the taller clearance without wasting it on the six
      // that can never reach it.
      if (document.querySelector('[data-service="coaching"]')) {
        document.body.classList.add("has-bar-coach");
      }
      initBarReserve();
    }

    initHeader();
    initOrders();
    render();
    initStats();
    initReveal();
    initCarousel();
    initFeed();
    initRoster();
    initBoosters();
    initProfile();
    initReviews();
    initCatalog();
    initAccounts();
    // Hydrates its own paint (esbHydrate calls render), so it does not have to
    // beat the render() above — but it must run before the first user input, or
    // an edit on checkout would be made against the wrong order.
    accountFromQuery();
    initGuides();
    // The mystery discount. `mydBoot()` runs on EVERY page — a token applied on
    // a game page has to be in the price at checkout too, and checkout has no
    // modal — while `initMystery()` returns immediately without one.
    mydBoot();
    initMystery();
    initScrollHints();
    initStickyBar();

    if (document.querySelector("[data-configurator]")) track("view_item", itemParams());
  }

  /* ── the site header ── design_handoff_site_header ────────────────────────
     Menus, the mobile sheet, the account popover and the auth panel. One
     controller, because they are one surface: only ever one of them is open,
     and every one of them closes on Escape and on an outside click.

     ⚠ The session is a FACADE. There is no account system behind this store —
     checkout is guest-only and orders are tracked by an emailed link — so
     `signIn()` writes a name and an email to localStorage and nothing more. It
     talks to no server, it is not a credential check, and the password is never
     stored, sent or read after the length test on the next line. See
     build.py's AUTH_PLACEHOLDER for everything that has to exist before this
     can take a real visitor. */
  var HD_SESSION = "esb.session.v1";
  // Hover intent. The leave delay is what stops a diagonal mouse path from the
  // nav item to a card in the panel's far corner closing the menu under it.
  var HD_ENTER = 120, HD_LEAVE = 250;

  function hdT(s) { return window.esbT ? window.esbT(s) : s; }

  function initHeader() {
    var hd = document.querySelector("[data-hd]");
    if (!hd) return;                       // the pay flow's reduced header

    /* ── the code chip ─────────────────────────────────────────────────── */
    // It is styled as interactive, so it has to do something — and it has to
    // confirm, or the click reads as a dead control.
    each("[data-hd-copy]", function (btn) {
      var t = null;
      btn.addEventListener("click", function () {
        var code = btn.getAttribute("data-hd-copy");
        var done = function () {
          btn.setAttribute("data-copied", "1");
          clearTimeout(t);
          t = setTimeout(function () { btn.removeAttribute("data-copied"); }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(code).then(done, function () { fallback(code, done); });
        } else fallback(code, done);
      });
    });
    function fallback(text, done) {
      // execCommand is deprecated but still the only path on a non-secure
      // origin, which a staging preview over plain http is.
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:-100px;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) {}
      document.body.removeChild(ta);
    }

    /* ── mega menus / accordion ────────────────────────────────────────── */
    var items = [].slice.call(hd.querySelectorAll("[data-hd-item]"));
    var wide = window.matchMedia("(min-width: 1001px)");
    var fine = window.matchMedia("(hover: hover) and (pointer: fine)");

    function trigger(it) { return it.querySelector("[data-hd-menu]"); }

    function closeMenus(except) {
      items.forEach(function (it) {
        if (it === except || !it.hasAttribute("data-open")) return;
        it.removeAttribute("data-open");
        trigger(it).setAttribute("aria-expanded", "false");
      });
    }
    function openMenu(it) {
      closeMenus(it);
      closeAccount();
      it.setAttribute("data-open", "");
      trigger(it).setAttribute("aria-expanded", "true");
    }

    items.forEach(function (it) {
      var btn = trigger(it), timer = null;
      btn.addEventListener("click", function (e) {
        // On a real pointer at desktop width the trigger is a link: hover has
        // already shown the panel, so let the click follow it to the hub. On
        // the accordion (narrow) or a touch screen (no hover to reveal the
        // panel) it stays a disclosure toggle — navigating away on tap would
        // put the submenu out of reach.
        if (wide.matches && fine.matches) return;
        e.preventDefault();
        e.stopPropagation();
        if (it.hasAttribute("data-open")) {
          it.removeAttribute("data-open");
          btn.setAttribute("aria-expanded", "false");
        } else openMenu(it);
      });
      // Keyboard: tabbing onto the link opens its panel, the hover equivalent,
      // so the submenu is reachable without a pointer. Enter still follows the
      // link to the hub; Tab moves on into the cards.
      btn.addEventListener("focus", function () {
        if (wide.matches && fine.matches) openMenu(it);
      });
      // Hover only on a real pointer at desktop width: on the accordion the
      // same gesture is a tap, and opening a section on hover-then-tap would
      // toggle it straight back shut.
      it.addEventListener("mouseenter", function () {
        if (!wide.matches || !fine.matches) return;
        clearTimeout(timer);
        timer = setTimeout(function () { openMenu(it); }, HD_ENTER);
      });
      it.addEventListener("mouseleave", function () {
        if (!wide.matches || !fine.matches) return;
        clearTimeout(timer);
        timer = setTimeout(function () {
          it.removeAttribute("data-open");
          btn.setAttribute("aria-expanded", "false");
        }, HD_LEAVE);
      });
      // Tabbing out of an open panel closes it — otherwise it hangs over the
      // page while focus is somewhere else entirely.
      it.addEventListener("focusout", function (e) {
        if (!wide.matches) return;
        if (e.relatedTarget && it.contains(e.relatedTarget)) return;
        it.removeAttribute("data-open");
        btn.setAttribute("aria-expanded", "false");
      });
    });

    /* ── the mobile sheet ──────────────────────────────────────────────── */
    var burger = hd.querySelector("[data-hd-sheet]");
    // The sheet is fixed, not in flow: a real page is not the mock's 860px
    // frame, and a sheet that pushes 4,000px of content down leaves the visitor
    // scrolling back up to the header. `--hd-top` is the header's own bottom
    // edge, so the sheet meets the bar whether or not the promo band has
    // scrolled away.
    function placeSheet() {
      document.documentElement.style.setProperty(
        "--hd-top", Math.max(0, Math.round(hd.getBoundingClientRect().bottom)) + "px");
    }
    function setSheet(open) {
      if (open) {
        placeSheet();
        closeAccount();
        hd.setAttribute("data-sheet", "");
        lockScroll(true);
        // The handoff opens section 0 by default — a sheet of five closed rows
        // makes the visitor tap twice to see anything. It cannot be marked open
        // in the HTML: at desktop width that same attribute renders the Games
        // mega menu hanging open on load.
        if (!items.some(function (it) { return it.hasAttribute("data-open"); }) && items[0]) {
          openMenu(items[0]);
        }
      } else {
        hd.removeAttribute("data-sheet");
        lockScroll(false);
      }
      if (burger) burger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    if (burger) burger.addEventListener("click", function (e) {
      e.stopPropagation();
      setSheet(!hd.hasAttribute("data-sheet"));
    });
    window.addEventListener("resize", function () {
      if (hd.hasAttribute("data-sheet")) placeSheet();
      if (wide.matches) setSheet(false);
      placeAccount();
    });
    window.addEventListener("scroll", function () {
      if (hd.hasAttribute("data-sheet")) placeSheet();
      if (accountOpen()) placeAccount();
    }, { passive: true });
    // Following a link out of the sheet has to release the scroll lock, or a
    // same-page anchor leaves the body frozen behind a closed sheet.
    each("[data-hd-panel-root] a", function (a) {
      a.addEventListener("click", function () { setSheet(false); });
    });

    /* ── the account popover ───────────────────────────────────────────── */
    var chip = hd.querySelector("[data-hd-account]");
    var acct = document.querySelector("[data-hd-account-menu]");
    function accountOpen() { return acct && !acct.hidden; }
    function placeAccount() {
      if (!accountOpen() || !chip) return;
      var r = chip.getBoundingClientRect();
      acct.style.top = Math.round(r.bottom + 8) + "px";
      acct.style.right = Math.max(12, Math.round(window.innerWidth - r.right)) + "px";
    }
    function closeAccount() {
      if (!acct || acct.hidden) return;
      acct.hidden = true;
      if (chip) chip.setAttribute("aria-expanded", "false");
    }
    function openAccount() {
      if (!acct) return;
      closeMenus();
      acct.hidden = false;
      if (chip) chip.setAttribute("aria-expanded", "true");
      placeAccount();
    }
    if (chip) chip.addEventListener("click", function (e) {
      e.stopPropagation();
      if (accountOpen()) closeAccount(); else openAccount();
    });
    if (acct) acct.addEventListener("click", function (e) { e.stopPropagation(); });

    /* ── the auth panel ────────────────────────────────────────────────── */
    var panel = document.querySelector("[data-hd-auth-panel]");
    var form = panel && panel.querySelector("[data-hd-form]");
    var pass = panel && panel.querySelector("[data-hd-pass]");
    var mail = panel && panel.querySelector("[data-hd-email]");
    var who = panel && panel.querySelector("[data-hd-dname]");
    var terms = panel && panel.querySelector("[data-hd-terms]");
    var status = panel && panel.querySelector("[data-hd-status]");
    var bars = panel && panel.querySelector("[data-hd-strength]");
    var note = panel && panel.querySelector("[data-hd-strength-note]");
    var opener = null;
    // The sign-in tab's status line doubles as its error slot, so the neutral
    // copy has to be captured before anything overwrites it.
    var HD_STATUS_OK = status ? status.textContent : "";

    function authOpen() { return panel && !panel.hidden; }
    function setMode(mode) {
      if (!panel) return;
      panel.setAttribute("data-mode", mode);
      each("[data-hd-tab]", function (t) {
        t.setAttribute("aria-selected", t.getAttribute("data-hd-tab") === mode ? "true" : "false");
      });
      if (pass) {
        pass.placeholder = hdT(pass.getAttribute("data-hd-ph-" + mode) || "");
        pass.setAttribute("autocomplete", mode === "signup" ? "new-password" : "current-password");
      }
      clearErr();
    }
    function openAuth(mode) {
      if (!panel) return;
      closeMenus(); closeAccount(); setSheet(false);
      opener = document.activeElement;
      panel.hidden = false;
      setMode(mode);
      lockScroll(true);
      var first = panel.querySelector("[data-hd-tab]");
      if (first) first.focus();
      // The top of the account funnel. Every later step (oauth_start, sign_up,
      // login, auth_error) is measured against this, so it has to fire on the
      // open and not on the submit — the people who open the panel and close it
      // again are the ones worth knowing about. Nothing identifying crosses:
      // the mode is "signin" or "signup" and that is all.
      track("auth_open", { mode: mode });
    }
    function closeAuth() {
      if (!authOpen()) return;
      panel.hidden = true;
      lockScroll(false);
      if (pass) pass.value = "";
      strength();
      // Focus goes back to whatever opened the panel — a modal that dumps focus
      // at the top of the document loses a keyboard user their place.
      if (opener && document.contains(opener)) opener.focus();
      opener = null;
    }
    each("[data-hd-auth]", function (b) {
      b.addEventListener("click", function () { openAuth(b.getAttribute("data-hd-auth")); });
    });
    each("[data-hd-auth-close]", function (b) { b.addEventListener("click", closeAuth); });
    each("[data-hd-tab]", function (t) {
      t.addEventListener("click", function () { setMode(t.getAttribute("data-hd-tab")); });
    });
    each("[data-hd-switch]", function (b) {
      b.addEventListener("click", function () {
        setMode(panel.getAttribute("data-mode") === "signup" ? "signin" : "signup");
      });
    });
    each("[data-hd-eye]", function (b) {
      b.addEventListener("click", function () {
        var on = b.getAttribute("aria-pressed") === "true";
        b.setAttribute("aria-pressed", on ? "false" : "true");
        b.setAttribute("aria-label", hdT(on ? "Show password" : "Hide password"));
        var t = on ? "password" : "text";
        if (pass) pass.type = t;
      });
    });
    if (terms) terms.addEventListener("click", function () {
      terms.setAttribute("aria-pressed", terms.getAttribute("aria-pressed") === "true" ? "false" : "true");
      clearErr();
    });
    // OAuth (Google / Discord). A click leaves the SPA for the provider's
    // consent screen via /api/auth/<provider>; the server sets a signed state
    // cookie, the provider redirects back to /api/auth/<provider>/callback, and
    // that mints the session cookie and returns here. Which buttons are actually
    // wired comes from /api/auth/me (loadMe below) — a provider whose app isn't
    // configured keeps the honest facade message instead of a dead redirect.
    var OAUTH = {};                 // {google:bool, discord:bool}, filled by loadMe
    function oauthGo(provider) {
      // Recorded before the redirect, because the round trip may never come
      // back — a consent screen the visitor closes leaves no other trace, and
      // an oauth_start with no matching login or auth_error IS that drop.
      track("oauth_start", { method: provider });
      var rt = location.pathname + location.search + location.hash;
      location.href = "/api/auth/" + encodeURIComponent(provider)
        + "?return_to=" + encodeURIComponent(rt);
    }
    function oauthFacade() {
      if (!status) return;
      setMode("signin");
      status.setAttribute("data-err", "");
      status.textContent = hdT("Social sign-in isn't connected yet. Use your email, "
        + "or buy as a guest — checkout needs no account.");
    }
    each("[data-hd-oauth]", function (b) {
      b.addEventListener("click", function () {
        var provider = b.getAttribute("data-hd-oauth");
        if (OAUTH[provider]) return oauthGo(provider);
        // Availability not known yet (or the probe failed) → ask, then act, so a
        // fast click before loadMe resolves still reaches a configured provider.
        loadMe().then(function () {
          if (OAUTH[provider]) oauthGo(provider); else oauthFacade();
        }, oauthFacade);
      });
    });

    // floor(length / 3), capped at 4 — the handoff's ramp.
    function strength() {
      if (!bars || !pass) return;
      var s = Math.min(4, Math.floor(pass.value.length / 3));
      bars.setAttribute("data-s", String(s));
      if (!note) return;
      if (!pass.value.length) note.textContent = hdT("Six characters or more. A passphrase beats a symbol soup.");
      else if (s <= 1) note.textContent = hdT("Too short to be worth having.");
      else if (s <= 2) note.textContent = hdT("Getting there — add a few more words.");
      else note.textContent = hdT("Strong enough.");
      if (pass.value.length && s <= 1) note.setAttribute("data-weak", "");
      else note.removeAttribute("data-weak");
    }
    if (pass) pass.addEventListener("input", function () { strength(); clearErr(); });
    if (mail) mail.addEventListener("input", clearErr);

    var errBox = panel && panel.querySelector("[data-hd-err]");
    function showErr(msg) {
      panel.setAttribute("data-err", "");
      if (errBox) { errBox.textContent = msg; errBox.hidden = false; }
      if (mail) mail.focus();
    }
    function clearErr() {
      panel.removeAttribute("data-err");
      if (errBox) { errBox.hidden = true; errBox.textContent = ""; }
      if (status) { status.removeAttribute("data-err"); status.textContent = HD_STATUS_OK; }
    }

    if (form) form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = (mail ? mail.value : "").trim();
      var pw = pass ? pass.value : "";
      var mode = panel ? panel.getAttribute("data-mode") : "signin";
      if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email)) {
        showErr(hdT("Enter a valid email address.")); return;
      }
      if (!pw.length) { showErr(hdT("Enter your password.")); return; }
      if (mode === "signup") {
        if (pw.length < 6) {
          showErr(hdT("Choose a password of at least 6 characters.")); return;
        }
        // The terms box must be ticked to create the account.
        if (terms && terms.getAttribute("aria-pressed") !== "true") {
          showErr(hdT("Please accept the terms to create your account.")); return;
        }
      }

      // Real auth: the password goes to the server, which verifies it against the
      // account store (see accounts.py). Nothing is accepted client-side — a wrong
      // password or an unknown email is refused by the server's 401.
      var body = accountBody({
        name: (who && who.value.trim()) || "", email: email
      }, mode);
      body.password = pw;
      var submit = form.querySelector(".hd-submit");
      if (submit) submit.disabled = true;

      postAccount(body).then(function (res) {
        if (submit) submit.disabled = false;
        if (res.status === "network") {
          track("auth_error", { mode: mode, reason: "network" });
          showErr(hdT("Couldn't reach the server. Check your connection and try again."));
          return;
        }
        // Every refusal is recorded with the reason the server gave, because the
        // interesting question is never "how many signed up" but "how many tried
        // and what stopped them" — an "exists" wall and a wrong password are two
        // completely different fixes and they look identical in a raw count.
        if (res.status !== "ok") track("auth_error", { mode: mode, reason: res.status });
        if (mode === "signup") {
          if (res.status === "exists") {
            // Carry the email into the log-in tab so they just add a password.
            setMode("signin");
            showErr(hdT("An account with this email already exists. Log in instead."));
            return;
          }
          if (res.status === "weak") {
            showErr(hdT("Choose a password of at least 6 characters.")); return;
          }
          if (res.status !== "ok") {
            showErr(hdT("Couldn't create the account. Try again.")); return;
          }
        } else if (res.status !== "ok") {
          showErr(hdT("That email and password don't match. Check them, "
            + "or create an account.")); return;
        }
        // The two outcomes, named the way GA4 names them so a tag manager could
        // read the same pushes later. `method` is how they authenticated, never
        // who: the address is already on its way to the accounts store.
        track(mode === "signup" ? "sign_up" : "login", { method: "password" });
        signIn({ name: (res.data && res.data.name) || email.split("@")[0], email: email });
        closeAuth();
      });
    });

    /* ── the facade session ────────────────────────────────────────────── */
    // Nothing here reaches a real auth backend. `orders` / `messages` are read
    // but never written: a real session fills them and the chip's meta line and
    // the popover's count pills light up. They stay empty rather than carrying
    // the handoff's "1 order live" fixture, which would be a claim about a
    // visitor this build knows nothing about.
    function readSession() {
      try { return JSON.parse(localStorage.getItem(HD_SESSION) || "null"); }
      catch (e) { return null; }
    }
    function signIn(s) {
      try { localStorage.setItem(HD_SESSION, JSON.stringify(s)); } catch (e) {}
      paint(s);
    }
    // The credentials a sign-up / sign-in sends to /api/account. The caller adds
    // `password`; tz/lang let the server resolve a country the way the analytics
    // session does, never from an IP.
    function accountBody(s, mode) {
      return {
        email: s.email, name: s.name, mode: mode,
        tz: (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
                           catch (e) { return ""; } })(),
        lang: (window.ESB_LOCALE && window.ESB_LOCALE.lang) || "en"
      };
    }
    // Awaitable POST — maps the server's status code to an outcome the submit
    // handler acts on. 409 → email taken, 400 → weak/invalid, 401 → bad
    // credentials, 2xx → ok, a network failure → 'network' (no silent accept).
    function postAccount(body) {
      return fetch("/api/account", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), keepalive: true
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          var status = r.ok ? "ok"
            : r.status === 409 ? "exists"
            : r.status === 400 ? (data && data.error === "weak" ? "weak" : "email")
            : r.status === 401 ? "invalid"
            : "error";
          return { status: status, data: data || {} };
        });
      }).catch(function () { return { status: "network", data: {} }; });
    }
    function signOut() {
      track("logout", {});
      try { localStorage.removeItem(HD_SESSION); } catch (e) {}
      // Also drop the server session cookie, if there is one (OAuth logins). A
      // static preview has no such route — ignore the failure.
      try {
        fetch("/api/auth/logout", { method: "POST", credentials: "same-origin",
          keepalive: true }).catch(function () {});
      } catch (e) {}
      closeAccount();
      paint(null);
    }
    function paint(s) {
      var login = hd.querySelector("[data-hd-auth]");
      if (login) login.hidden = !!s;
      if (chip) chip.hidden = !s;
      if (!s) return;
      each("[data-hd-initial]", function (el) { el.textContent = (s.name || "?").charAt(0); });
      each("[data-hd-name]", function (el) { el.textContent = s.name || ""; });
      each("[data-hd-mail]", function (el) { el.textContent = s.email || ""; });
      var meta = hd.querySelector("[data-hd-meta]");
      if (meta) meta.textContent = s.orders ? (s.orders + " " + hdT("live")) : "";
      each("[data-hd-badge]", function (el) {
        var v = s[el.getAttribute("data-hd-badge")];
        el.hidden = !v;
        if (v) el.textContent = String(v);
      });
    }
    // Signing in or out on the orders page flips its greeting / guest prompt
    // without a reload — paint() is the one place every session change lands.
    initOrders();
    each("[data-hd-logout]", function (b) { b.addEventListener("click", signOut); });
    paint(readSession());

    // Session hydration + provider availability. /api/auth/me returns the signed
    // server session (OAuth logins) and which providers are wired. It is the
    // source of truth over the localStorage record: a live cookie upgrades the
    // header to the real account; its absence never clears an email/password
    // session (those are localStorage-only). A static preview has no such route,
    // so a failure just leaves the facade in place. Cached so the click handler
    // and this initial hydrate share one request.
    var mePromise = null;
    function loadMe() {
      if (mePromise) return mePromise;
      mePromise = fetch("/api/auth/me", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.providers) OAUTH = d.providers;
          if (d && d.authenticated && d.email) {
            signIn({ name: d.name || d.email.split("@")[0], email: d.email,
                     provider: d.provider || "" });
            initOrders();
          }
          return d || {};
        });
      return mePromise;
    }
    loadMe();

    // The OAuth round trip lands back here carrying its outcome in the query,
    // and both halves are stripped again so a refresh neither re-opens the panel
    // nor re-counts the login. A success returns to ?auth=<provider> (plus
    // &new=1 when the callback created the account rather than recognising it);
    // a failure returns to ?auth_error=<message>. The markers are the ONLY way
    // this side can tell a fresh login from a cookie that was already there —
    // the redirect happens off-page, so nothing else observes it.
    function stripQuery(keys) {
      try {
        var q = new URLSearchParams(location.search);
        keys.forEach(function (k) { q.delete(k); });
        var rest = q.toString();
        history.replaceState(null, "", location.pathname
          + (rest ? "?" + rest : "") + location.hash);
      } catch (e) {}
    }
    (function () {
      var ok = /[?&]auth=([a-z]+)/.exec(location.search);
      if (ok) {
        var fresh = /[?&]new=1(?:&|$)/.test(location.search);
        track(fresh ? "sign_up" : "login", { method: ok[1] });
        stripQuery(["auth", "new"]);
        return;
      }
      var m = /[?&]auth_error=([^&]*)/.exec(location.search);
      if (!m) return;
      var why = decodeURIComponent(m[1].replace(/\+/g, " "));
      track("auth_error", { mode: "oauth", reason: why.slice(0, 80) || "failed" });
      openAuth("signin");
      showErr(why || hdT("Sign-in didn't complete. Please try again."));
      stripQuery(["auth_error"]);
    })();

    /* ── one surface at a time ─────────────────────────────────────────── */
    document.addEventListener("click", function (e) {
      if (hd.contains(e.target)) return;
      closeMenus();
      closeAccount();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (authOpen()) { closeAuth(); return; }
      if (accountOpen()) { closeAccount(); if (chip) chip.focus(); return; }
      var open = items.filter(function (it) { return it.hasAttribute("data-open"); })[0];
      if (open) { closeMenus(); trigger(open).focus(); return; }
      if (hd.hasAttribute("data-sheet")) { setSheet(false); if (burger) burger.focus(); }
    });
    // Focus trap for the modal. Without it Tab walks out of the dialog and
    // through a page the visitor cannot see.
    if (panel) panel.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var f = [].slice.call(panel.querySelectorAll(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])'))
        .filter(function (el) { return el.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }

  /* ── /orders — personalise the account's order history ────────────────────
     The page renders a full sample history server-side (correct with no JS).
     Here we read the facade session and, when present, greet the account by
     name and drop the "you're viewing a sample, log in" guest prompt. Same
     localStorage key the header writes; there is no server round-trip because
     there is no account backend yet. */
  // The signed-in customer's OWN orders, read live from GET /api/orders (the
  // store is email-scoped to the signed session cookie — see src/orders.py).
  // No fabricated data: three states in the DOM are toggled here — signed out,
  // signed in with no orders (empty), and real orders (stats + table). Called on
  // load and again on every session change through paint(), so signing in/out
  // re-renders without a reload.
  function initOrders() {
    var root = document.querySelector("[data-orders]");
    if (!root) return;                            // not the orders page
    var guest = root.querySelector("[data-ord-guest]");
    var hello = root.querySelector("[data-ord-hello]");
    var helloName = root.querySelector("[data-ord-name]");
    var stats = root.querySelector("[data-ord-stats]");
    var empty = root.querySelector("[data-ord-empty]");
    var tableSec = root.querySelector("[data-ord-table-sec]");
    var tbody = root.querySelector("[data-ord-tbody]");

    // The localStorage session: email/password logins have no server cookie yet,
    // so /api/orders can't identify them — but the header still shows them signed
    // in, and they have no real orders to miss, so they get the empty state.
    var ls = null;
    try { ls = JSON.parse(localStorage.getItem("esb.session.v1") || "null"); } catch (e) {}

    function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
    function money(cur, n) {
      try {
        return new Intl.NumberFormat(undefined, { style: "currency", currency: (cur || "usd").toUpperCase(), maximumFractionDigits: 0 }).format(n || 0);
      } catch (e) { return "$" + (n || 0); }
    }
    function when(ts) {
      if (!ts) return "—";
      try { return new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
      catch (e) { return "—"; }
    }
    function pill(st) {
      if (st === "delivered") return '<span class="ord-status is-done">Delivered</span>';
      if (st === "refunded") return '<span class="ord-status is-refunded">Refunded</span>';
      return '<span class="ord-status is-live">In progress</span>';
    }
    function row(o) {
      return '<div class="ord-row">'
        + '<span class="ord-cell ord-c-id"><span class="ord-oid">' + esc(o.order_id) + '</span></span>'
        + '<span class="ord-cell ord-c-game">' + esc(o.gameShort) + '</span>'
        + '<span class="ord-cell ord-c-climb">' + esc(o.summary) + '</span>'
        + '<span class="ord-cell ord-c-mode">' + esc(o.mode || "—") + '</span>'
        + '<span class="ord-cell ord-c-date">' + when(o.at) + '</span>'
        + '<span class="ord-cell ord-c-price">' + money(o.currency, o.total) + '</span>'
        + '<span class="ord-cell ord-c-status">' + pill(o.status) + '</span>'
        + '</div>';
    }
    function show(el, on) { if (el) el.hidden = !on; }
    function setStat(k, v) {
      var el = root.querySelector('[data-ord-stat="' + k + '"]');
      if (el) el.textContent = v;
    }

    function render(data) {
      var authed = !!(data && data.authenticated);
      var name = (data && data.name) || (ls && ls.name) || "";
      var signedIn = authed || !!(ls && ls.name);

      show(hello, signedIn);
      if (helloName && name) helloName.textContent = name;   // own <b>, i18n-safe
      show(guest, !signedIn);

      if (!signedIn) { show(stats, false); show(empty, false); show(tableSec, false); return; }

      var all = ((data && data.active) || []).concat((data && data.delivered) || []);
      if (!authed || !all.length) {               // no verifiable session, or none yet
        show(stats, false); show(tableSec, false); show(empty, true); return;
      }

      all.sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
      setStat("orders", data.orders);
      setStat("inprogress", data.in_progress);
      setStat("delivered", data.delivered_count);
      setStat("spent", money(data.currency, data.spent));
      tbody.innerHTML = all.map(row).join("");
      show(empty, false); show(stats, true); show(tableSec, true);
    }

    fetch("/api/orders", { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(render)
      .catch(function () { render({ authenticated: false }); });
  }

  /* ── the boosters roster: game / availability / sort, all live ────────────
     A 34-person board with no filter is a list, not a tool. Three controls,
     AND-combined in that order, with a count that reflects them.

     Everything here is driven by the documented data-* contract and never by
     the row's markup: the rows carry data-game / data-free / data-win, so the
     same JS keeps working when the board is rendered server-side. The
     prototype filters ten fixture rows in the browser, which will not hold for
     34+ behind pagination — at that point this becomes a request and the
     attributes stay the contract.

     Rows past the first page are already `hidden` from the build, so the page
     is correct with no JS at all and "Load more" reveals real rows rather than
     being a control with nothing behind it. */
  // Page size, mirrored from build.py's ROSTER_PAGE — the server renders the
  // first page unhidden and this reveals the rest, so the two have to agree.
  var RST_PAGE = 12;

  function initRoster() {
    var body = document.querySelector("[data-rst-body]");
    if (!body) return;
    // Re-read from the DOM on every draw so initBoosters() can swap the rows in
    // from /api/boosters and just call the exposed refresh — the filter buttons
    // are bound once below and outlive the row replacement.
    function currentRows() { return [].slice.call(body.querySelectorAll("[data-rst-row]")); }
    if (body.getAttribute("data-rst-bound")) { window.esbRefreshRoster && window.esbRefreshRoster(); return; }
    body.setAttribute("data-rst-bound", "1");
    if (!currentRows().length) return;
    var shownEl = document.querySelector("[data-rst-shown]");
    var fGame = document.querySelector("[data-rst-fgame]");
    var fFree = document.querySelector("[data-rst-ffree]");
    var empty = document.querySelector("[data-rst-empty]");
    var emptyG = document.querySelector("[data-rst-empty-game]");
    var headGame = document.querySelector("[data-rst-empty-game-h]");
    var headAny = document.querySelector("[data-rst-empty-any-h]");
    var emptyN = document.querySelector("[data-rst-empty-n]");
    var more = document.querySelector("[data-rst-more]");
    var st = { game: "", avail: "Everyone", sort: "Win rate", page: 1 };

    function num(el, attr) { return parseInt(el.getAttribute(attr), 10) || 0; }
    function free(el) { return el.getAttribute("data-free") === "1"; }

    function matches(el) {
      if (st.game && el.getAttribute("data-game") !== st.game) return false;
      if (st.avail === "Free now" && !free(el)) return false;
      return true;
    }

    function draw() {
      var rows = currentRows();
      var hits = rows.filter(matches);
      // "Free first" sorts free boosters up and orders within each group by
      // win rate; "Win rate" sorts purely by win rate.
      hits.sort(function (a, b) {
        if (st.sort === "Free first" && free(a) !== free(b)) return free(a) ? -1 : 1;
        return num(b, "data-win") - num(a, "data-win");
      });
      rows.forEach(function (el) { el.hidden = true; });
      var cap = Math.min(hits.length, RST_PAGE * st.page);
      hits.forEach(function (el, i) {
        body.appendChild(el);                    // re-order in place
        if (i < cap) el.hidden = false;
      });

      if (shownEl) shownEl.textContent = cap;
      if (fGame) { fGame.textContent = st.game ? " · " + st.game : ""; fGame.hidden = !st.game; }
      if (fFree) fFree.hidden = st.avail !== "Free now";
      if (more) more.hidden = cap >= hits.length;

      // A game with nobody free right now is normal, and a bare table with no
      // rows reads as a broken page. Say how many cover it and offer the two
      // things that still work: order anyway, or drop the filter.
      if (empty) {
        empty.hidden = hits.length > 0;
        if (!hits.length) {
          var onGame = rows.filter(function (el) {
            return !st.game || el.getAttribute("data-game") === st.game;
          });
          // Two headlines, both in the DOM, one hidden: "Nobody free on DOTA"
          // has no sensible form with the game chip on "All games", and
          // dropping a word out of a sentence is how a string stops being one
          // translatable node.
          if (emptyG) emptyG.textContent = st.game;
          if (headGame) headGame.hidden = !st.game;
          if (headAny) headAny.hidden = !!st.game;
          if (emptyN) emptyN.textContent = onGame.length;
        }
      }
    }

    function group(attr, key, cls) {
      each("[data-rst-" + attr + "]", function (btn) {
        btn.addEventListener("click", function () {
          st[key] = btn.getAttribute("data-rst-" + attr);
          st.page = 1;
          var sibs = btn.parentNode.children;
          for (var i = 0; i < sibs.length; i++) {
            var on = sibs[i] === btn;
            sibs[i].classList.toggle(cls, on);
            sibs[i].setAttribute("aria-checked", on ? "true" : "false");
          }
          draw();
        });
      });
    }
    group("game", "game", "is-on");
    group("avail", "avail", "is-on");
    group("sort", "sort", "is-on");

    if (more) more.addEventListener("click", function () { st.page++; draw(); });

    // "Show everyone" clears both filters through the chips themselves, so the
    // buttons' pressed state can never fall out of step with the board.
    var reset = document.querySelector("[data-rst-reset]");
    if (reset) reset.addEventListener("click", function () {
      var all = document.querySelector('[data-rst-game=""]');
      var everyone = document.querySelector('[data-rst-avail="Everyone"]');
      if (all) all.click();
      if (everyone) everyone.click();
    });

    // initBoosters() calls this after swapping the board rows in from the store.
    window.esbRefreshRoster = function () { st.page = 1; draw(); };

    draw();
  }

  /* ── a booster's page: All / Solo / Duo over the completed orders ──────── */
  var BP_PAGE = 8;

  function initProfile() {
    var body = document.querySelector("[data-bp-body]");
    if (!body) return;
    var rows = [].slice.call(body.querySelectorAll("[data-bp-row]"));
    if (!rows.length) return;
    var shownEl = document.querySelector("[data-bp-shown]");
    var totalEl = document.querySelector("[data-bp-total]");
    var more = document.querySelector("[data-bp-more]");
    var st = { mode: "All", page: 1 };
    // The chip labels carry that queue's real order total, so the footer's
    // "of N" follows the filter instead of always quoting the all-orders one.
    var totals = {};
    each("[data-bp-filter]", function (btn) {
      var b = btn.querySelector("b");
      totals[btn.getAttribute("data-bp-filter")] = b ? b.textContent : "";
    });

    function draw() {
      var hits = rows.filter(function (el) {
        return st.mode === "All" || el.getAttribute("data-mode") === st.mode;
      });
      var cap = Math.min(hits.length, BP_PAGE * st.page);
      rows.forEach(function (el) { el.hidden = true; });
      hits.forEach(function (el, i) { if (i < cap) el.hidden = false; });
      if (shownEl) shownEl.textContent = cap;
      if (totalEl && totals[st.mode]) totalEl.textContent = totals[st.mode];
      if (more) more.hidden = cap >= hits.length;
    }

    each("[data-bp-filter]", function (btn) {
      btn.addEventListener("click", function () {
        st.mode = btn.getAttribute("data-bp-filter");
        st.page = 1;
        var sibs = btn.parentNode.children;
        for (var i = 0; i < sibs.length; i++) {
          var on = sibs[i] === btn;
          sibs[i].classList.toggle("is-on", on);
          sibs[i].setAttribute("aria-checked", on ? "true" : "false");
        }
        draw();
      });
    });
    if (more) more.addEventListener("click", function () { st.page++; draw(); });
    draw();
  }

  /* ── /reviews.html: game, rating and sort over the whole feed ─────────────
     The page's job is to let a sceptic verify the rating rather than take it on
     faith, and these controls are how: the distribution rows and the rating
     segments both write st.rating and are kept in step in both directions, so
     the count beside the feed always answers the question the reader just
     asked. Filters AND-combine in the order game → rating → sort.

     Two rules that are the page's argument, not its styling:
       · "Lowest rated" stays in the sort options. A page that says it hides
         nothing has to let you go straight to the worst of it;
       · a distribution row toggles back to All when it is already selected;
         the segmented control always sets. Otherwise the only way out of "1★"
         is a control on the other side of the screen.

     Every card is server-rendered and everything past the first page ships
     `hidden`, so the first page reads correctly with no JS and "Load N more"
     reveals cards already in the document. At 3,140 reviews the
     filter, sort and page become query parameters and this markup — the
     data-rv-* pair on each card — is the contract for them. */
  var RVP_PAGE = 12;      // cards visible first, mirrored from build.py
  var RVP_MORE = 30;      // what one click costs; the label says so out loud

  function initReviews() {
    var grid = document.querySelector("[data-rvp-grid]");
    if (!grid) return;
    var cards = [].slice.call(grid.querySelectorAll("[data-rv-stars]"));
    if (!cards.length) return;
    var shownEl = document.querySelector("[data-rvp-shown]");
    var totalEl = document.querySelector("[data-rvp-total]");
    var crumb = document.querySelector("[data-rvp-crumb]");
    var empty = document.querySelector("[data-rvp-empty]");
    var more = document.querySelector("[data-rvp-more]");
    var moreLabel = document.querySelector("[data-rvp-more-label]");
    var st = { game: "", rating: "all", sort: "recent", cap: RVP_PAGE };

    cards.forEach(function (el, i) {
      el._s = parseInt(el.getAttribute("data-rv-stars"), 10) || 0;
      el._i = i;                                 // DOM order is recency order
    });

    function matches(el) {
      if (st.game && el.getAttribute("data-rv-game") !== st.game) return false;
      if (st.rating === "all") return true;
      if (st.rating === "low") return el._s <= 3;
      return el._s === parseInt(st.rating, 10);
    }

    // The crumb repeats the active filters beside the count, so a reader who
    // scrolled past the controls still knows what they are looking at. Both
    // parts are read back off the controls themselves, which is also how they
    // come out translated.
    function label() {
      var out = "";
      var chip = st.game && document.querySelector('[data-rvp-game="' + st.game + '"]');
      if (chip) out += " · " + chip.textContent;
      if (st.rating !== "all") {
        var seg = document.querySelector('[data-rvp-rating="' + st.rating + '"]');
        // 3★, 2★ and 1★ come from the distribution rows and have no segment.
        out += " · " + (seg ? seg.textContent : st.rating + "★");
      }
      return out;
    }

    function draw() {
      var hits = cards.filter(matches);
      if (st.sort !== "recent") {
        var sign = st.sort === "high" ? -1 : 1;
        // Ties keep recency, so switching sort never shuffles equal ratings.
        hits = hits.slice().sort(function (a, b) { return sign * (a._s - b._s) || (a._i - b._i); });
      }
      var cap = Math.min(hits.length, st.cap);
      cards.forEach(function (el) { el.hidden = true; });
      hits.forEach(function (el, i) {
        grid.appendChild(el);                    // re-order in place
        if (i < cap) el.hidden = false;
      });

      if (shownEl) shownEl.textContent = cap;
      // The second figure is the *filtered* total — "12 of 3,140" while a
      // filter is on would answer a question nobody asked.
      if (totalEl) totalEl.textContent = hits.length;
      if (crumb) { crumb.textContent = label(); crumb.hidden = !crumb.textContent; }
      if (empty) empty.hidden = hits.length > 0;

      // Nothing to clear, no control offering to: the button appears with the
      // first filter. An empty result always has one, so the empty state's own
      // copy of the button is never hidden underneath it.
      var filtered = !!st.game || st.rating !== "all";
      each("[data-rvp-clear]", function (b) { b.hidden = !filtered; });
      if (more) {
        var left = hits.length - cap;
        more.hidden = left <= 0;
        // Never promise thirty when twelve are left. Both labels are whole
        // text nodes, so both stay translatable.
        if (moreLabel) moreLabel.textContent = left >= RVP_MORE
          ? T("Load " + RVP_MORE + " more") : T("Show the rest");
      }
    }

    function group(attr, key) {
      each("[data-rvp-" + attr + "]", function (btn) {
        btn.addEventListener("click", function () {
          set(key, btn.getAttribute("data-rvp-" + attr));
        });
      });
    }

    // One place where state changes, so the two rating controls cannot fall
    // out of step: whoever writes `rating` re-marks both of them.
    function set(key, val) {
      st[key] = val;
      st.cap = RVP_PAGE;
      mark();
      draw();
    }

    function mark() {
      each("[data-rvp-game]", function (b) { flag(b, b.getAttribute("data-rvp-game") === st.game); });
      each("[data-rvp-sort]", function (b) { flag(b, b.getAttribute("data-rvp-sort") === st.sort); });
      each("[data-rvp-rating]", function (b) { flag(b, b.getAttribute("data-rvp-rating") === st.rating); });
      each("[data-rvp-dist]", function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-rvp-dist") === st.rating ? "true" : "false");
      });
    }
    function flag(b, on) {
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    }

    group("game", "game");
    group("rating", "rating");
    group("sort", "sort");

    // A row already selected clears back to All — the segments cannot express
    // "2★ only", so without the toggle there is no way out of one from here.
    each("[data-rvp-dist]", function (btn) {
      btn.addEventListener("click", function () {
        var v = btn.getAttribute("data-rvp-dist");
        set("rating", st.rating === v ? "all" : v);
      });
    });

    each("[data-rvp-clear]", function (b) {
      b.addEventListener("click", function () {
        st.game = ""; st.rating = "all"; st.cap = RVP_PAGE;
        mark(); draw();
      });
    });

    if (more) more.addEventListener("click", function () { st.cap += RVP_MORE; draw(); });

    // "Read the worst first" is the hero's second action while there is no
    // Trustpilot profile to send anyone to: it sets the sort the paragraph
    // above it promises, then the anchor scrolls to the feed.
    var worst = document.querySelector("[data-rvp-worst]");
    if (worst) worst.addEventListener("click", function () { set("sort", "low"); });

    draw();
  }

  /* ── /games/ — the catalogue's filter, sort and trust rail ────────────────
     design_handoff_games_page. Filter and sort are independent and compose:
     sorting persists across filter changes, filters are single-select with
     `all` as the reset. Every card is already in the DOM in catalogue order —
     this only hides and re-orders, the same trade-off the roster board and the
     reviews feed make, and the reason is the same: this is the page a crawler
     reads to learn which titles exist.

     There is no empty state because no filter can return zero — the counts are
     computed off the catalogue at build time and every chip is a real capability
     with at least one title. If a filter is ever added that can return nothing,
     that state has to be designed rather than left to collapse the grid. */
  function initCatalog() {
    var grid = document.querySelector("[data-gc-grid]");
    if (!grid) return;
    var cards = [].slice.call(grid.querySelectorAll("[data-gc-card]"));
    if (!cards.length) return;
    var foot = document.querySelector("[data-gc-foot]");
    var shown = [].slice.call(document.querySelectorAll("[data-gc-shown]"));
    var sortLabel = document.querySelector("[data-gc-sortlabel]");
    var st = { filter: "all", sort: "featured" };

    cards.forEach(function (el) {
      el._order = parseInt(el.getAttribute("data-gc-order"), 10) || 0;
      el._price = parseInt(el.getAttribute("data-gc-price"), 10) || 0;
      el._name = el.getAttribute("data-gc-name") || "";
    });

    function matches(el) {
      return st.filter === "all" || el.getAttribute("data-gc-" + st.filter) === "1";
    }

    function draw() {
      var hits = cards.filter(matches);
      hits.sort(function (a, b) {
        if (st.sort === "price") return a._price - b._price || a._order - b._order;
        if (st.sort === "az") return a._name.localeCompare(b._name);
        return a._order - b._order;              // Featured — the catalogue's order
      });
      cards.forEach(function (el) { el.hidden = true; });
      hits.forEach(function (el) { grid.appendChild(el); el.hidden = false; });
      shown.forEach(function (el) { el.textContent = hits.length; });
      // The footer only exists while a filter is on: an unfiltered page has
      // nothing to say there and no reset to offer.
      if (foot) foot.hidden = st.filter === "all";
    }

    // One state, two controls per dimension — the segmented control and the
    // native select are both in the DOM at every width (CSS picks one), so both
    // are always re-marked whichever fired.
    function mark(attr, value) {
      each("[data-" + attr + "]", function (btn) {
        var on = btn.getAttribute("data-" + attr) === value;
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    function set(key, value) {
      st[key] = value;
      mark("gc-" + key, value);
      if (key === "sort") {
        var sel = document.querySelector("[data-gc-sortsel]");
        if (sel && sel.value !== value) sel.value = value;
        var opt = sel && sel.options[sel.selectedIndex];
        if (sortLabel && opt) sortLabel.textContent = opt.textContent;
      }
      draw();
    }

    each("[data-gc-filter]", function (btn) {
      btn.addEventListener("click", function () { set("filter", btn.getAttribute("data-gc-filter")); });
    });
    each("[data-gc-sort]", function (btn) {
      btn.addEventListener("click", function () { set("sort", btn.getAttribute("data-gc-sort")); });
    });
    each("[data-gc-sortsel]", function (sel) {
      sel.addEventListener("change", function () { set("sort", sel.value); });
    });
    // Reset through the chip itself, so the pressed state can never fall out of
    // step with the grid — the same wiring the roster's "Show everyone" uses.
    var reset = document.querySelector("[data-gc-reset]");
    if (reset) reset.addEventListener("click", function () {
      var all = document.querySelector('[data-gc-filter="all"]');
      if (all) all.click();
      grid.scrollIntoView({ block: "start" });
    });

    initCatalogRail();
    draw();
  }

  /* The phone's trust rail: three promise cards on scroll-snap, with dots that
     FOLLOW the rail rather than drive a timer. The handoff auto-rotates them
     every 4.6s; these three are the refund, privacy and support promises, and a
     card that slides itself away mid-sentence is exactly the "a moving element
     reads as a sales device" rule the guarantee page is built on. */
  function initCatalogRail() {
    var dots = document.querySelector("[data-gc-dots]");
    var rail = document.querySelector(".gc .sg-promises");
    if (!dots || !rail) return;
    var buttons = [].slice.call(dots.querySelectorAll("[data-gc-dot]"));
    var cards = [].slice.call(rail.children);
    if (buttons.length !== cards.length) return;

    // Card offsets are measured against the rail's own left edge, not the
    // offsetParent's, so the pair works wherever the rail is placed.
    function at(el) { return el.offsetLeft - rail.offsetLeft; }
    function nearest() {
      var mid = rail.scrollLeft + rail.clientWidth / 2, best = 0, dist = Infinity;
      cards.forEach(function (el, i) {
        var d = Math.abs(at(el) + el.offsetWidth / 2 - mid);
        if (d < dist) { dist = d; best = i; }
      });
      return best;
    }
    function mark(i) {
      buttons.forEach(function (b, j) {
        b.classList.toggle("is-on", i === j);
        b.setAttribute("aria-pressed", i === j ? "true" : "false");
      });
    }
    // Above 760px the same element is a three-column grid with nothing to
    // scroll: every card is on screen, so "nearest the centre" would mark the
    // middle dot for a control CSS has already hidden.
    function sync() { mark(rail.scrollWidth - rail.clientWidth > 4 ? nearest() : 0); }
    rail.addEventListener("scroll", function () {
      clearTimeout(rail._t);
      rail._t = setTimeout(sync, 80);
    }, { passive: true });
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () {
        // Marked here rather than waiting on the scroll event: a tap on the dot
        // for a card already at the end of the rail scrolls nowhere, and a dot
        // that does not light up reads as a dead control.
        mark(i);
        rail.scrollTo({ left: at(cards[i]), behavior: reduceMotion() ? "auto" : "smooth" });
      });
    });
    sync();
  }

  function reduceMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* ── delivered-today feed: keep the relative times true ───────────────────
     "2 min ago" is only true at the instant the page was built. This is a
     static site and a tab can sit open for an hour, so every row carries the
     age it was rendered with and both labels are re-derived on a timer.

     Two sources, in order: `data-ts` (the delivery's own epoch seconds — what
     a feed wired to the orders table emits) wins; `data-mins` is the
     placeholder stand-in and counts back from page load. Nothing here invents
     a delivery: the rows are exactly the ones build.py rendered.

     Prepending new deliveries — the other half of the handoff's live feed —
     needs that real source. No JS is required for the treatment: .lf-row's
     newest-row styling keys off :first-child, so a live feed only has to
     insert the row. */
  var feedTimer = null;

  /* ── the accounts shop (/accounts.html) ─────────────────────────────────
     design_handoff_accounts_shop. A TWO-STEP purchase: pick a server, then pick
     a tier. That order is the design, not a preference — an account is
     region-locked and cannot be transferred after sale, so the one irreversible
     choice is made first, on a screen with nothing else on it.

     Everything is SERVER-RENDERED, including all eleven cards and every price,
     and BOTH steps ship visible: with no JS the page is a complete, priced,
     buyable shop on the reference shard and a crawler reads the whole
     catalogue. This function is the enhancement — it gates step 2 behind the
     server choice and re-prices every card in place from the client mirror,
     which is the same derivation the server used (accountPrice / accountStock,
     mirroring data.py).

     ⚠ THE PAGE CHANGE IS THE THING TO VERIFY BY LOOKING AT THE CARDS, never by
     reading the label. A label that updates over a track that did not move is
     how seven of eleven tiers were unreachable through two of the handoff's own
     reviews.

     `data-ac-*` is the whole contract — see CLAUDE.md. */
  var AC_SCARCE = 3;                     // mirrors AC_SCARCE in build.py

  function initAccounts() {
    var shop = document.querySelector("[data-ac-shop]");
    if (!shop) return;
    var step1 = shop.querySelector('[data-ac-step="server"]');
    var step2 = shop.querySelector('[data-ac-step="tiers"]');
    var trackEl = shop.querySelector("[data-ac-track]");
    if (!step1 || !step2 || !trackEl) return;
    var cards = [].slice.call(trackEl.querySelectorAll("[data-ac-card]"));
    if (!cards.length) return;

    var dotsBox = shop.querySelector("[data-ac-dots]");
    var prev = shop.querySelector("[data-ac-prev]");
    var next = shop.querySelector("[data-ac-next]");
    var nojs = shop.querySelector("[data-ac-nojs]");
    var filbar = shop.querySelector("[data-ac-filbar]");
    var st = { server: null, kind: "all", page: 0 };

    // The no-JS line is the one thing that is wrong the moment JS runs: with
    // scripting the shard is chosen, not assumed.
    if (nojs && nojs.parentNode) nojs.parentNode.removeChild(nojs);

    /* Cards per page is CSS's, read back rather than written down twice, so the
       page count follows the layout. Under 2 the rail is a swipe rail (the
       phone) and paging is inert. */
    function perPage() {
      var v = parseFloat(getComputedStyle(shop).getPropertyValue("--ac-per"));
      return isNaN(v) || v < 1 ? 4 : v;
    }
    function paged() { return perPage() >= 2; }

    function visible() {
      return cards.filter(function (c) {
        return st.kind === "all" || c.getAttribute("data-ac-kind") === st.kind;
      });
    }
    function pages(n) {
      var per = perPage();
      return paged() ? Math.max(1, Math.ceil(n / Math.floor(per))) : 1;
    }

    function setText(el, v) { if (el) el.textContent = v; }
    function each(sel, root, fn) {
      [].slice.call((root || shop).querySelectorAll(sel)).forEach(fn);
    }

    /* One card, re-priced and re-stocked for the chosen shard. Every figure
       here comes from the same two mirrors the checkout re-quote uses, so a
       card can never advertise a price or an availability the server refuses. */
    function paintCard(el, sv) {
      var acc = (D.accounts || {})[el.getAttribute("data-ac-id")];
      if (!acc || !sv) return;
      var units = accountStock(acc, sv);
      var state = !units ? "out" : (units <= AC_SCARCE ? "low" : "ok");

      /* ⚠ The money is NOT rewritten here. A shard changes stock, not price,
         and a currency switch is handled by i18n.js's reformatStaticMoney(),
         which picks the listing's own `data-<code>` row off the span. Writing
         a figure here would be a second place the price is decided, and the
         two would disagree the first time one of them was changed. */
      setText(el.querySelector("[data-ac-code]"), sv.code);
      setText(el.querySelector("[data-ac-shard-name]"), sv.region);
      each("[data-ac-units]", el, function (b) { b.textContent = units; });

      var stock = el.querySelector("[data-ac-stock]");
      if (stock) stock.className = "ac-stock is-" + state;
      el.classList.toggle("is-out", state === "out");

      // The CTA is a real link, so the shard rides in it: a visitor who picked
      // EUNE and middle-clicked Buy must not land on a checkout quoting EUW.
      var href = "/checkout.html?account=" + encodeURIComponent(acc.id || el.getAttribute("data-ac-id"))
        + "&region=" + encodeURIComponent(sv.region);
      each("[data-ac-cta]", el, function (a) {
        var kind = a.getAttribute("data-ac-cta");
        a.hidden = kind !== state;
        if (kind !== "out") a.href = href;
      });
    }

    function paint() {
      var sv = st.server ? accountServer(st.server) : null;
      var chosen = !!sv;
      step1.hidden = chosen;
      step2.hidden = !chosen;
      if (!chosen) return;

      each("[data-ac-server-name]", null, function (n) { n.textContent = sv.region; });
      each("[data-ac-server-code]", null, function (n) { n.textContent = sv.code; });
      setText(shop.querySelector("[data-ac-server-stock]"), accountUnitsOn(sv));

      cards.forEach(function (c) {
        c.hidden = !(st.kind === "all" || c.getAttribute("data-ac-kind") === st.kind);
        if (!c.hidden) paintCard(c, sv);
      });

      var shown = visible().length;
      var total = pages(shown);
      if (st.page > total - 1) st.page = total - 1;
      if (st.page < 0) st.page = 0;
      trackEl.style.setProperty("--ac-p", paged() ? st.page : 0);

      each("[data-ac-kind]", null, function (b) {
        var on = b.getAttribute("data-ac-kind") === st.kind;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      // Through T(): the two metas the server never renders would otherwise
      // arrive in English on the French and German pages.
      var meta = (D.accountKinds || {})[st.kind];
      setText(shop.querySelector("[data-ac-kindmeta]"), meta ? T(meta) : "");

      /* "Showing 1–4 of 11 tiers". Every figure rides in its own <b> so the
         words around it stay whole translatable nodes. */
      var per = paged() ? Math.floor(perPage()) : shown;
      var from = shown ? st.page * per + 1 : 0;
      var to = Math.min(shown, from + per - 1);
      var label = shop.querySelector("[data-ac-pagelabel]");
      if (label) {
        var bs = label.querySelectorAll("b");
        if (bs.length === 3) {
          bs[0].textContent = from; bs[1].textContent = to; bs[2].textContent = shown;
        }
      }

      if (prev) prev.disabled = !paged() || st.page <= 0;
      if (next) next.disabled = !paged() || st.page >= total - 1;

      if (dotsBox) {
        // Rebuilt rather than reordered: the page count moves with the filter
        // and with the viewport, so there is no stable list to mutate.
        dotsBox.textContent = "";
        if (paged() && total > 1) {
          for (var i = 0; i < total; i++) {
            (function (n) {
              var d = document.createElement("button");
              d.type = "button";
              d.className = "ac-dot" + (n === st.page ? " is-on" : "");
              d.setAttribute("aria-label", "Page " + (n + 1));
              d.addEventListener("click", function () { st.page = n; paint(); });
              dotsBox.appendChild(d);
            })(i);
          }
        }
      }
    }

    each("[data-ac-server]", null, function (b) {
      b.addEventListener("click", function () {
        // Changing server resets the filter and the page — the handoff's rule,
        // and the honest one: a page-3 Emerald view means nothing on a shard
        // whose stock is a third of the size.
        st.server = b.getAttribute("data-ac-server");
        st.kind = "all"; st.page = 0;
        paint();
        /* ⚠ On the phone this scrolls to the FILTER BAR, not to the top of
           step 2. Step 2's head is the server bar plus a heading — ~230px of
           confirmation — and putting that at the top of an 852px screen with a
           68px sticky header and iOS Safari's ~85px floating toolbar left the
           card's price and "Buy now" 119px under the browser chrome: the one
           action on the card, invisible. Reported from a real iPhone.
           The bar and the heading are one short scroll back up; the cards are
           what the tap was for. Desktop has the room and keeps step 2. */
        var target = (!paged() && filbar) ? filbar : step2;
        /* ⚠ INSTANT, and deferred a frame. paint() has just unhidden step 2 and
           hidden step 1 — several hundred pixels of layout change — and a
           SMOOTH scroll started against that reflow is non-deterministic: it
           landed at 0 on one run and 53 on the next, so the card's price and
           CTA stayed under the browser chrome and it looked like the handler
           was never firing. `scroll-behavior: smooth` is global (ashfall.css),
           so 'auto' would inherit it — 'instant' is the only value that means
           instant, the same reason the guarantee page's deep-link uses it. */
        requestAnimationFrame(function () {
          target.scrollIntoView({ block: "start", behavior: "instant" });
        });
      });
    });
    var change = shop.querySelector("[data-ac-change]");
    if (change) change.addEventListener("click", function () {
      st.server = null; st.kind = "all"; st.page = 0;
      paint();
      step1.scrollIntoView({ block: "center", behavior: "instant" });
    });
    each("[data-ac-kind]", null, function (b) {
      b.addEventListener("click", function () {
        st.kind = b.getAttribute("data-ac-kind"); st.page = 0; paint();
      });
    });
    if (prev) prev.addEventListener("click", function () {
      if (st.page > 0) { st.page--; paint(); }
    });
    if (next) next.addEventListener("click", function () { st.page++; paint(); });

    // --ac-per is a breakpoint's, so a resize can change the page count under a
    // reader sitting on the last page. A currency switch needs nothing here:
    // i18n.js's reformatStaticMoney() re-splits the two-size price itself.
    var rz;
    window.addEventListener("resize", function () {
      clearTimeout(rz); rz = setTimeout(paint, 150);
    });

    // Buy fires begin_checkout and hands the order over, exactly as the board
    // it replaces did. The click is on the real link, so a middle-click still
    // opens checkout and hydrates from the query.
    each("[data-ac-cta]", null, function (a) {
      if (a.getAttribute("data-ac-cta") === "out") return;
      a.addEventListener("click", function (e) {
        var card = a.closest ? a.closest("[data-ac-card]") : null;
        if (!card) return;
        var id = card.getAttribute("data-ac-id");
        var acc = (D.accounts || {})[id];
        if (!acc) return;
        var order = accountOrder(id, st.server || (D.accountServers || [{}])[0].region);
        var q = quote(order);
        if (q.invalid) { e.preventDefault(); return; }
        try { localStorage.setItem(CHECKOUT_KEY, JSON.stringify(order)); } catch (e2) {}
        track("begin_checkout", {
          currency: "USD", value: q.total,
          items: [{ item_id: id, item_name: acc.name, item_category: "account",
                    item_variant: order.region, price: q.total, quantity: 1 }]
        });
      });
    });

    paint();
  }

  /* One order object for an account listing, built from DEFAULT so every field
     the checkout re-quote reads is present. The ranks it inherits are inert —
     quote() returns before the ladder on this service, and build_session()
     blanks metadata[from]/[to] so a climb nobody bought cannot reach the board. */
  function accountOrder(id, region) {
    // The shard list belongs to the SHOP, not to a listing: every tier is sold
    // on every server and stock is what varies. Clamped here the same way
    // pricing.account_pick() clamps it, so a region carried in from a boost on
    // a shard this shop does not sell can never reach the checkout re-quote.
    var sv = accountServer(region) || (D.accountServers || [])[0];
    return Object.assign({}, DEFAULT, {
      game: D.accountGame || DEFAULT.game,
      service: "account", account: id,
      region: sv ? sv.region : "",
      // An account carries none of these, and a stale one riding in from the
      // shared record would show on the checkout summary as something bought.
      addons: [], promo: "", bundle: null, booster: "",
      savedAt: Date.now()
    });
  }

  /* Checkout arriving from an account card: ?account=<id>&region=<shard>.
     The query is untrusted and is never believed — it names a listing, and
     quote() (here) and pricing.account_pick() (on the server, which computes
     the actual charge) both refuse an id that is unknown or sold out. It is
     read on checkout only; the markers are stripped so a refresh cannot
     re-hydrate over an order the buyer has since changed. */
  function accountFromQuery() {
    if (CFG) return;                       // never on a page that configures
    var m = /[?&]account=([^&]+)/.exec(location.search);
    if (!m) return;
    var id = decodeURIComponent(m[1]);
    if (!(D.accounts || {})[id]) return;
    var r = /[?&]region=([^&]*)/.exec(location.search);
    var order = accountOrder(id, r ? decodeURIComponent(r[1].replace(/\+/g, " ")) : "");
    if (quote(order).invalid) return;
    if (window.esbHydrate) window.esbHydrate(order);
    try {
      var q = new URLSearchParams(location.search);
      q.delete("account"); q.delete("region");
      var rest = q.toString();
      history.replaceState(null, "", location.pathname
        + (rest ? "?" + rest : "") + location.hash);
    } catch (e) {}
  }

  function initFeed() {
    // Re-entrant: initBoosters() re-renders the feed from /api/boosters and calls
    // this again, so clear any prior ticker rather than stack a second interval on
    // the same rows.
    if (feedTimer) { clearInterval(feedTimer); feedTimer = null; }
    // Any .lf-ago carrying one of the two timestamp attributes, not just the
    // feed's rows: the demo page's order card states when the last game was in
    // the same relative words, and it has to tick for the same reason.
    var rows = [].slice.call(document.querySelectorAll(".lf-ago[data-ts], .lf-ago[data-mins]"));
    if (!rows.length) return;
    var base = Date.now();                       // what data-mins counts back from

    function at(el) {
      var ts = el.getAttribute("data-ts");
      return ts ? +ts * 1000 : base - (+el.getAttribute("data-mins") || 0) * 60000;
    }
    // Mirrors _ago() in build.py — same thresholds, same flooring, so a page
    // that reloads within the minute does not change its own wording.
    function label(ms) {
      var m = Math.floor((Date.now() - ms) / 60000);
      if (m < 60) return Math.max(1, m) + " " + t("min ago");
      var h = Math.floor(m / 60);
      return h < 24 ? h + " " + t("hr ago") : Math.floor(h / 24) + " " + t("d ago");
    }
    function t(s) { return window.esbT ? window.esbT(s) : s; }
    function pad(n) { return (n < 10 ? "0" : "") + n; }

    function tick() {
      rows.forEach(function (el) {
        var ms = at(el);
        el.textContent = label(ms);
        // The clock follows the visitor's own zone; the server-rendered value
        // is in the server's, which is the best a static build can do.
        var clock = el.parentNode.querySelector(".lf-clock");
        if (clock) {
          var d = new Date(ms);
          clock.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes());
        }
      });
    }
    tick();
    feedTimer = setInterval(tick, 30000);

    // A language switch re-renders through esbRender; the unit words go with it.
    var prev = window.esbRender;
    window.esbRender = function () { if (prev) prev.apply(this, arguments); tick(); };
  }

  /* ── the dynamic roster: board, "On shift now" rail and the feed ───────
     These three panels are server-rendered from data.py so the page is correct
     with no JS and readable to a crawler. When the backend roster store has data,
     /api/boosters serves it live — a rotating rail + feed and the whole board —
     and this swaps the server rows for the store's. A 204 (empty store), a
     non-200 or a network failure leaves the server-rendered fallback in place, so
     the panels never blank. Every glyph comes from D.icons (build.py's own _ico),
     so a JS-built row is drawn with the same marks as its server twin. */
  function escH(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* The face inside the availability ring — build.py's booster_face(), in JS.

     Same order of preference as the server: the real avatar in
     site/assets-in/avatar/ if this booster has one (D.avatars, keyed by handle
     because only build.py can see that folder), else the drawn glyph the server
     names in `face` with the two tints it resolved (see boosters.py's _row), so
     this never picks a face or a colour of its own and a live row can't be
     drawn differently than the server-rendered one it replaces. The initial is
     the last resort — what a data.js cached from before this shipped gives. */
  function faceMark(b, cls) {
    var src = D.avatars && D.avatars[b.handle];
    if (src) {
      return '<img src="' + escH(src) + '" alt="" width="38" height="38" loading="lazy">';
    }
    var g = (D.icons && D.icons.faces && D.icons.faces[b.face]) || "";
    if (!g) return '<span class="' + cls + '">' + escH(b.initial) + "</span>";
    return '<span class="' + cls + ' is-face" style="--face:' + escH(b.faceInk) +
      ";--face-bg:" + escH(b.facePlate) + '">' + g + "</span>";
  }

  function initBoosters() {
    var feedList = document.querySelector(".lf-list");
    var shiftList = document.querySelector(".rc-list");
    var board = document.querySelector("[data-rst-body]");
    // [data-live] is in the header, so it is on every page — the fetch has to
    // run for it even where none of the three panels do.
    var live = document.querySelector("[data-live]");
    if (!feedList && !shiftList && !board && !live) return;

    fetch("/api/boosters", { headers: { Accept: "application/json" } })
      .then(function (r) { return r.status === 200 ? r.json() : null; })
      .then(function (data) {
        if (!data) return;                        // 204 / empty store → keep the fallback
        if (feedList && data.feed && data.feed.length) renderFeed(feedList, data);
        if (shiftList && data.shift && data.shift.length) renderShift(shiftList, data);
        if (board && data.boosters && data.boosters.length) renderBoard(board, data);
        // The header's roster count comes from the same payload the rail and the
        // board are drawn from, so the page can never quote two of them.
        if (data.stats) {
          setLiveStat("online", data.stats.online);
          setLiveStat("free", data.stats.free_now);
        }
      })
      .catch(function () {});                      // network error → keep the fallback
  }

  function feedSide(s, strong) {
    var name = s.tier ? '<span class="lf-tier">' + escH(s.tier) + "</span>" : "";
    return name + '<span class="lf-mark' + (strong ? " is-to" : "") +
      '" style="--tier:' + escH(s.color) + '">' + escH(s.label) + "</span>";
  }

  function renderFeed(list, data) {
    var I = D.icons || {};
    var feed = data.feed;
    list.innerHTML = feed.map(function (f) {
      return '<li class="lf-row">' +
        '<span class="lf-when">' +
          '<span class="lf-ago" data-mins="' + f.mins + '"></span>' +
          '<span class="lf-clock" data-mins="' + f.mins + '"></span>' +
        "</span>" +
        '<span class="lf-rail" aria-hidden="true"><i class="lf-dot"></i></span>' +
        '<span class="lf-climb">' +
          '<span class="lf-letter" aria-hidden="true">' + escH(f.gameShort) + "</span>" +
          '<span class="lf-climb-in">' + feedSide(f.frm, false) + (I.feedArrow || "") + feedSide(f.to, true) + "</span>" +
        "</span>" +
        '<span class="lf-game">' +
          '<span class="lf-game-n">' + escH(f.gameName) + "</span>" +
          '<span class="lf-region">' + escH(f.region) + "</span>" +
        "</span>" +
        '<span class="lf-by">' +
          '<span class="lf-booster">' + escH(f.booster) + "</span>" +
          '<span class="lf-done">' + (I.feedSeal || "") + T("Delivered") + "</span>" +
        "</span>" +
      "</li>";
    }).join("");
    // The rolling "N orders closed in the last 24 hours" figure comes off the
    // store too, so the footer moves with the feed instead of sitting frozen.
    var closed = data.stats && data.stats.closed_24h;
    if (closed != null) {
      var foot = document.querySelector(".lf-foot b");
      if (foot) foot.textContent = closed;
    }
    initFeed();                                    // re-attach the relative-time ticker to the new rows
  }

  function renderShift(list, data) {
    var I = D.icons || {};
    list.innerHTML = data.shift.map(function (b) {
      var chip = b.gameShort ? '<span class="rc-chip">' + escH(b.gameShort) + "</span>" : "";
      var pill = '<span class="rc-pill' + (b.free ? "" : " is-busy") + '">' +
        (b.free ? (I.pillDotRc || "") : (I.pillHourRc || "")) +
        escH(b.free ? T("Free") : b.queue) + "</span>";
      return '<li><a class="rc-row" href="' + escH(b.href) + '">' +
        '<span class="rc-ring' + (b.free ? "" : " is-busy") + '">' + faceMark(b, "rc-initial") + "</span>" +
        '<span class="rc-who">' +
          '<span class="rc-name">' + escH(b.handle) + chip + "</span>" +
          '<span class="rc-rank">' + escH(b.peakFull) + "</span>" +
        "</span>" +
        '<span class="rc-state">' + pill +
          '<span class="rc-wr"><b>' + escH(b.wr) + "</b> " + T("win rate") + "</span>" +
        "</span>" +
      "</a></li>";
    }).join("");
    var n = (data.stats && data.stats.online) || data.shift.length;
    each(".rc-count b", function (el) { el.textContent = n; });
    each(".rc-all b", function (el) { el.textContent = n; });
  }

  function renderBoard(body, data) {
    var I = D.icons || {};
    body.innerHTML = data.boosters.map(function (b, i) {
      var pill = '<span class="rst-pill' + (b.free ? "" : " is-busy") + '">' +
        (b.free ? (I.pillDotRst || "") : (I.pillHourRst || "")) +
        escH(b.free ? T("Free") : b.queue) + "</span>";
      return '<div class="rst-row" data-rst-row data-game="' + escH(b.gameShort) + '"' +
        ' data-free="' + (b.free ? 1 : 0) + '" data-win="' + b.wrN + '"' + (i >= 12 ? " hidden" : "") + ">" +
        '<a class="rst-who" href="' + escH(b.href) + '">' +
          '<span class="rst-ring' + (b.free ? "" : " is-busy") + '">' + faceMark(b, "rst-initial") + "</span>" +
          '<span class="rst-who-t">' +
            '<span class="rst-handle">' + escH(b.handle) + "</span>" +
            '<span class="rst-orders"><b>' + b.orders + "</b> " + T("orders delivered") + "</span>" +
          "</span>" +
        "</a>" +
        '<span class="rst-game">' +
          '<span class="rst-code">' + escH(b.gameShort || "—") + "</span>" +
          '<span class="rst-server">' + escH(b.region) + "</span>" +
        "</span>" +
        '<span class="rst-peak"><span class="rst-mark is-to" style="--tier:' + escH(b.markColor) + '">' + escH(b.markLabel) + "</span>" +
          '<span class="rst-peak-t">' + escH(b.peak) + "</span></span>" +
        '<span class="rst-wr">' +
          '<span class="rst-wr-v">' + escH(b.wr) + "</span>" +
          '<span class="rst-wr-bar"><i style="width:' + b.wrPct + '%"></i></span>' +
        "</span>" +
        pill +
        '<a class="rst-hire" href="' + escH(b.hire) + '" data-rst-hire="' + escH(b.handle) + '">' + T("Hire") + (I.hireArrow || "") + "</a>" +
      "</div>";
    }).join("");
    var total = (data.stats && data.stats.online) || data.boosters.length;
    var count = document.querySelector(".rst-count");
    if (count) { var bs = count.querySelectorAll("b"); if (bs[1]) bs[1].textContent = total; }
    if (window.esbRefreshRoster) window.esbRefreshRoster();   // re-run filters/sort/pager over the new rows
  }

  /* ── horizontal rails: say that there is more to the right ────────────────
     The configurator's tab row scrolls below 1000px, and on a 375px screen
     Coaching sat entirely past the right edge — a fourth product with nothing
     on the row suggesting it moves. The rails that genuinely overflow are
     marked `data-scrollhint`, which CSS draws as a fade on the right edge, and
     `data-scroll-end` clears it once there is nothing further to reach, so the
     fade always means "there is more" rather than being decoration.

     Marked from JS, not in the markup: whether a rail overflows depends on the
     width, the language and the game's own tab set, and a fade over a row that
     already fits points at nothing. */
  function initScrollHints() {
    var rails = [].slice.call(document.querySelectorAll(
      ".ob-tabs, .ob-bundles-grid, .rvp-chips, .rst-chips, .gc-chips, .gc-svcs-grid, .gp-rv-grid, .gp-dps"));
    if (!rails.length) return;
    function sync(el) {
      var over = el.scrollWidth - el.clientWidth;
      if (over <= 4) { el.removeAttribute("data-scrollhint"); return; }
      el.setAttribute("data-scrollhint", "");
      // A sub-pixel scrollWidth leaves a fraction that is never reached, so the
      // end is "within 4px of it" rather than an equality.
      if (el.scrollLeft >= over - 4) el.setAttribute("data-scroll-end", "");
      else el.removeAttribute("data-scroll-end");
    }
    rails.forEach(function (el) {
      sync(el);
      el.addEventListener("scroll", function () { sync(el); }, { passive: true });
    });
    var t;
    window.addEventListener("resize", function () {
      clearTimeout(t);
      t = setTimeout(function () { rails.forEach(sync); }, 120);
    });
    // The tab set is rebuilt when the game changes, and the bundle rail with
    // it, so re-measure after a render rather than only at load.
    document.addEventListener("esb:render", function () { rails.forEach(sync); });
  }

  /* ── sticky checkout bar: reveal on scroll ───────────────────────────────
     The fixed bar (.mobile-bar on a game page, .co-bar on checkout) mirrors the
     page's own primary checkout button but stays hidden until that button has
     scrolled up out of view — so only ever one checkout button is on screen.
     Scrolling back up to the button hides the bar again. */
  function initStickyBar() {
    var bar = document.querySelector(".mobile-bar, .co-bar");
    if (!bar) return;
    // The in-flow "main" button the bar shadows: the card's own CTA on a game
    // page, the form's submit on checkout (never the one inside the bar itself).
    var anchor = bar.classList.contains("co-bar")
      ? [].filter.call(document.querySelectorAll(".co-cta"),
          function (b) { return !b.closest(".co-bar"); })[0]
      : document.querySelector(".ob-cta");
    if (!anchor) return;
    var shown = false, ticking = false;
    function sweep() {
      ticking = false;
      var r = anchor.getBoundingClientRect();
      // Reveal once the button's bottom edge has passed above the viewport top.
      // A display:none anchor (desktop) reports 0, which never crosses — the bar
      // is display:none there anyway, so the class is harmless.
      var past = r.bottom < 0;
      if (past === shown) return;
      shown = past;
      bar.classList.toggle("is-revealed", past);
    }
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(sweep);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    sweep();
  }

  /* ── stat boxes: count-up + rise-in when scrolled into view ──────────── */
  function initStats() {
    var nums = [].slice.call(document.querySelectorAll(".stat b"));
    if (!nums.length) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var hosts = [].slice.call(document.querySelectorAll(".stat"));

    if (reduce) {
      hosts.forEach(function (el) { el.classList.add("is-in"); });   // no motion: just show
      return;
    }
    hosts.forEach(function (el) { el.classList.add("reveal"); });     // arm the hidden start state

    function countUp(el) {
      var raw = el.getAttribute("data-raw");
      if (raw == null) { raw = el.textContent; el.setAttribute("data-raw", raw); }
      var m = raw.match(/^([^\d]*)(\d[\d,]*(?:\.\d+)?)(.*)$/);
      if (!m) return;
      var pre = m[1], numStr = m[2], suf = m[3];
      /* A rating must not count up from zero. "92,400 delivered" ticking up
         reads as momentum; the same easing on "4.8 / 5" spends the first
         second of every load advertising 0.4, 1.2, 2.6 out of 5 — on the pages
         whose entire job is trust, and for longer than that on a slow device
         or a tab that was opened in the background. Ratings render final. */
      if (parseFloat(numStr.replace(/,/g, "")) <= 5 && numStr.indexOf(".") >= 0) {
        el.textContent = raw;
        return;
      }
      var decimals = (numStr.split(".")[1] || "").length;
      var comma = numStr.indexOf(",") >= 0;
      var target = parseFloat(numStr.replace(/,/g, ""));
      var t0 = null, dur = 1100;
      function reformat(v) {
        var s = v.toFixed(decimals);
        if (comma) {
          var p = s.split(".");
          p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
          s = p.join(".");
        }
        return pre + s + suf;
      }
      function step(ts) {
        if (t0 === null) t0 = ts;
        var k = Math.min(1, (ts - t0) / dur);
        el.textContent = reformat(target * (1 - Math.pow(1 - k, 3)));  // easeOutCubic
        if (k < 1) requestAnimationFrame(step); else el.textContent = raw;
      }
      requestAnimationFrame(step);
    }

    function fire(el) {
      var host = el.closest ? el.closest(".stat") : null;
      if (host) host.classList.add("is-in");
      countUp(el);
    }

    // Scroll/rAF driven so above-the-fold stats reveal on the first frame,
    // with no dependency on IntersectionObserver's async first callback.
    var pending = nums.slice();
    function sweep() {
      var vh = window.innerHeight || document.documentElement.clientHeight || 0;
      for (var i = pending.length - 1; i >= 0; i--) {
        var r = pending[i].getBoundingClientRect();
        if (r.top < vh * 0.9 && r.bottom > 0) { fire(pending[i]); pending.splice(i, 1); }
      }
      if (!pending.length) {
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
      }
    }
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; sweep(); });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    sweep();                             // synchronous first pass — reveals above-the-fold now
    window.addEventListener("load", sweep);
  }

  /* ── generic scroll-reveal for [data-reveal] (e.g. homepage review tiles) ─
     Same scroll/rAF sweep as initStats, so items above the fold reveal on the
     first frame. Arms .reveal (hidden), then adds .is-in when in view. */
  function initReveal() {
    var els = [].slice.call(document.querySelectorAll("[data-reveal]"));
    if (!els.length) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { els.forEach(function (el) { el.classList.add("is-in"); }); return; }
    els.forEach(function (el) { el.classList.add("reveal"); });    // arm the hidden start state

    var pending = els.slice();
    function sweep() {
      var vh = window.innerHeight || document.documentElement.clientHeight || 0;
      for (var i = pending.length - 1; i >= 0; i--) {
        var r = pending[i].getBoundingClientRect();
        if (r.top < vh * 0.9 && r.bottom > 0) { pending[i].classList.add("is-in"); pending.splice(i, 1); }
      }
      if (!pending.length) {
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
      }
    }
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () { ticking = false; sweep(); });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    sweep();
    window.addEventListener("load", sweep);
  }

  /* ── review carousel: responsive per-view, paginate, auto-rotate ──────────
     Sizes slides to the viewport, builds one dot per page, auto-advances
     (paused on hover/focus/hidden tab), and supports pointer-swipe. Honors
     prefers-reduced-motion by dropping the auto-rotation. */
  function initCarousel() {
    var roots = [].slice.call(document.querySelectorAll("[data-carousel]"));
    if (!roots.length) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    roots.forEach(function (root) {
      var viewport = root.querySelector("[data-carousel-viewport]");
      var track = root.querySelector("[data-carousel-track]");
      var dotsWrap = root.querySelector("[data-carousel-dots]");
      var prev = root.querySelector("[data-carousel-prev]");
      var next = root.querySelector("[data-carousel-next]");
      var slides = track ? [].slice.call(track.children) : [];
      if (!viewport || !track || !slides.length) return;

      var GAP = 10, index = 0, perView = 1, pages = 1, offset = 0;
      var range = root.querySelector("[data-carousel-range]");
      var total = slides.length;
      root.setAttribute("data-ready", "");   // flips off the no-JS scroll fallback

      /* Asked of the same media queries site.css uses for this section, not of
         a measured width: the stylesheet stacks the head and hides the arrows
         on the assumption of a given cards-per-page, and this is what decides
         it — so the two must read the same breakpoints or a scrollbar's width
         is enough to put them on different layouts. */
      function perViewFor() {
        if (!window.matchMedia) return 3;
        if (window.matchMedia("(min-width: 1161px)").matches) return 3;
        if (window.matchMedia("(min-width: 761px)").matches) return 2;
        return 1;
      }

      function layout() {
        var w = viewport.clientWidth;
        perView = perViewFor();
        var slideW = (w - GAP * (perView - 1)) / perView;
        slides.forEach(function (s) { s.style.flex = "0 0 " + slideW + "px"; s.style.maxWidth = slideW + "px"; });
        pages = Math.max(1, Math.ceil(total / perView));
        if (index > pages - 1) index = pages - 1;
        buildDots();
        go(index, true);
      }

      function buildDots() {
        if (!dotsWrap) return;
        dotsWrap.textContent = "";
        for (var i = 0; i < pages; i++) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "rv-dot";
          b.setAttribute("aria-label", T("Page") + " " + (i + 1));
          (function (n) { b.addEventListener("click", function (e) { go(n); if (e.detail) this.blur(); }); })(i);
          dotsWrap.appendChild(b);
        }
      }

      /* The range label and both arrow states are derived from the page, never
         set by hand — the label is the only thing saying how much is left, so
         it must not be able to disagree with the control beside it. */
      function go(i, instant) {
        index = Math.max(0, Math.min(pages - 1, i));   // clamped, not wrapped
        var w = viewport.clientWidth;
        var maxOffset = Math.max(0, track.scrollWidth - w);
        offset = Math.min(index * (w + GAP), maxOffset);
        track.style.transition = (instant || reduce) ? "none" : "transform .18s cubic-bezier(.4,0,.2,1)";
        track.style.transform = "translateX(" + (-offset) + "px)";
        if (dotsWrap) [].slice.call(dotsWrap.children).forEach(function (d, di) {
          d.classList.toggle("is-active", di === index);
          if (di === index) d.setAttribute("aria-current", "true");
          else d.removeAttribute("aria-current");
        });
        var first = index * perView + 1, last = Math.min(total, (index + 1) * perView);
        if (range) range.textContent = first + "–" + last + " / " + total;
        if (prev) prev.disabled = index === 0;
        if (next) next.disabled = index >= pages - 1;
      }

      if (next) next.addEventListener("click", function (e) { go(index + 1); if (e.detail) this.blur(); });
      if (prev) prev.addEventListener("click", function (e) { go(index - 1); if (e.detail) this.blur(); });

      // pointer swipe
      var startX = null, dragging = false, startOffset = 0;
      viewport.addEventListener("pointerdown", function (e) {
        dragging = true; startX = e.clientX; startOffset = offset;
        track.style.transition = "none";
      });
      window.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        track.style.transform = "translateX(" + (-(startOffset - (e.clientX - startX))) + "px)";
      });
      window.addEventListener("pointerup", function (e) {
        if (!dragging) return;
        dragging = false;
        var dx = e.clientX - startX;
        if (dx < -40) go(index + 1); else if (dx > 40) go(index - 1); else go(index);
      });

      var rt;
      window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(layout, 150); });

      layout();
    });
  }

  /* ── live counts ─────────────────────────────────────────────────────────
     These used to WANDER: every [data-live] figure drifted ±1–2 on a 4–8s timer
     so the page would "read live". Three problems, all of them the kind this
     build exists to avoid. It moved with nothing behind it — no order, no shift
     change, just Math.random() dressed as activity. Its floor was
     data-live-min="36" against a true roster of 88, so the header could claim
     less than half the real board. And it drifted out of step with the numbers
     beside it: the header said 87 while the "On shift now" rail (reading the
     real store) said 84 and the server-rendered HTML said 88 — three roster
     counts on one screen, which is exactly the bug counting from BOOSTERS was
     introduced to kill.

     A figure here now only ever changes when the store says so. initBoosters()
     fetches /api/boosters and calls this with the real counts; until then the
     server-rendered number stands. */
  function setLiveStat(kind, value) {
    if (typeof value !== "number" || !isFinite(value) || value < 0) return;
    each("[data-live=\"" + kind + "\"]", function (el) {
      var was = parseInt((el.getAttribute("data-raw") || el.textContent || "")
                         .replace(/[^\d-]/g, ""), 10);
      el.setAttribute("data-raw", String(value));
      el.textContent = String(value);
      if (was === value) return;
      var host = el.closest ? el.closest("[data-live-stat]") : null;
      if (host) { host.classList.add("bump"); setTimeout(function () { host.classList.remove("bump"); }, 260); }
      el.classList.add("is-up");
      setTimeout(function () { el.classList.remove("is-up"); }, 500);
    });
  }
  window.esbSetLiveStat = setLiveStat;

  /* ── free guides landing ── design_handoff_free_guides ────────────────────
     The lead form. Two guides is a choice inside ONE funnel: one email, one CTA,
     the two covers as selectable cards whose selection changes what gets sent
     (and, in production, is stored with the address as a game-preference signal).

     ⚠ FACADE. There is no POST, no ESP, no double opt-in — a valid-looking
     address flips `sent`. See build.py's page_guides() note and the handoff for
     everything that has to exist before this takes a real signup. The email and
     the guide picks are shared by both capture points (hero card + closing
     band), so a value typed in one appears in the other. The dynamic strings
     (CTA label, helper, note, success line) go through esbT() and their nodes
     are in i18n.js's SKIP list, matching whole-node translation. */
  function gdT(s) { return window.esbT ? window.esbT(s) : s; }
  var GD_RE = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i;

  function initGuides() {
    var root = document.querySelector("[data-gd]");
    if (!root) return;

    var cards = Array.prototype.slice.call(root.querySelectorAll("[data-gd-card]"));
    var emails = Array.prototype.slice.call(root.querySelectorAll("[data-gd-email]"));
    var form = root.querySelector("[data-gd-form]");
    var success = root.querySelector("[data-gd-success]");
    var st = { email: "", err: false, pickErr: false, sent: false };

    function picks() { return cards.filter(function (c) { return c.getAttribute("aria-pressed") === "true"; }); }
    function shortOf(c) { return c.getAttribute("data-gd-short") || ""; }
    function valid() { return GD_RE.test(st.email.trim()); }

    function paint() {
      var chosen = picks();
      var both = chosen.length === 2;
      var one = chosen.length === 1;

      // CTA label — states what will actually be sent.
      var cta = both ? "Send me both guides"
        : one ? "Send me the " + shortOf(chosen[0]) + " guide"
        : "Pick a guide first";
      root.querySelectorAll("[data-gd-cta]").forEach(function (n) { n.textContent = gdT(cta); });

      // Helper line under the cards.
      var pick = st.pickErr ? "Pick at least one guide."
        : both ? "Both guides, one email, two attachments."
        : one ? "Only one? The other is free too."
        : "Pick at least one guide.";
      root.querySelectorAll("[data-gd-pick]").forEach(function (n) {
        n.textContent = gdT(pick);
        if (st.pickErr) n.setAttribute("data-err", ""); else n.removeAttribute("data-err");
      });

      // Email field state + note.
      emails.forEach(function (i) {
        if (i.value !== st.email) i.value = st.email;
        if (st.err) i.setAttribute("data-err", ""); else i.removeAttribute("data-err");
        if (valid() && !st.err) i.setAttribute("data-valid", ""); else i.removeAttribute("data-valid");
      });
      var note = st.err ? "Enter an address we can send the PDFs to."
        : "Used to send the guides. Nothing else unless you tick the box below.";
      root.querySelectorAll("[data-gd-note]").forEach(function (n) {
        n.textContent = gdT(note);
        if (st.err) n.setAttribute("data-err", ""); else n.removeAttribute("data-err");
      });
      // Closing capture note.
      var cnote = st.err ? "That address does not look right — check it and try again."
        : "Arrives in about a minute. No card, no account.";
      root.querySelectorAll("[data-gd-ctanote]").forEach(function (n) { n.textContent = gdT(cnote); });

      // Success line (rendered even while hidden, so a swap shows it correct).
      var sent = both ? "Both guides are" : one ? "The " + shortOf(chosen[0]) + " guide is" : "Your guide is";
      root.querySelectorAll("[data-gd-sentline]").forEach(function (n) { n.textContent = gdT(sent); });
    }

    // Fire-and-forget lead beacon → /api/guides (a separate store from the header
    // sign-up list; see guides.py). tz/lang let the server resolve a country the
    // way the analytics session does, never from an IP. The success UI never waits
    // on it — the guides are "on the way" regardless of whether the store answers.
    function beacon(chosen) {
      var optbtn = root.querySelector("[data-gd-optin]");
      var body = {
        email: st.email.trim(),
        guides: chosen.join(","),
        optin: optbtn ? optbtn.getAttribute("aria-pressed") === "true" : false,
        tz: (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
                           catch (e) { return ""; } })(),
        lang: (window.ESB_LOCALE && window.ESB_LOCALE.lang) || "en"
      };
      try {
        fetch("/api/guides", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body), keepalive: true
        }).catch(function () {});
      } catch (e) {}
    }

    function submit() {
      if (!picks().length) { st.pickErr = true; paint(); return; }
      if (!valid()) { st.err = true; paint(); return; }
      st.sent = true; st.err = false; st.pickErr = false;
      root.querySelectorAll("[data-gd-email-out]").forEach(function (n) { n.textContent = st.email.trim(); });
      paint();
      if (form) form.hidden = true;
      if (success) success.hidden = false;
      var chosen = picks().map(function (c) { return c.getAttribute("data-gd-card"); });
      track("generate_lead", { guides: chosen.join(",") });
      beacon(chosen);
    }

    cards.forEach(function (c) {
      c.addEventListener("click", function () {
        c.setAttribute("aria-pressed", c.getAttribute("aria-pressed") === "true" ? "false" : "true");
        st.pickErr = false;
        paint();
      });
    });

    emails.forEach(function (i) {
      i.addEventListener("input", function () { st.email = i.value; st.err = false; paint(); });
      i.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); submit(); } });
    });

    root.querySelectorAll("[data-gd-send]").forEach(function (b) {
      b.addEventListener("click", submit);
    });

    var optin = root.querySelector("[data-gd-optin]");
    if (optin) optin.addEventListener("click", function () {
      optin.setAttribute("aria-pressed", optin.getAttribute("aria-pressed") === "true" ? "false" : "true");
    });

    var reset = root.querySelector("[data-gd-reset]");
    if (reset) reset.addEventListener("click", function () {
      st.sent = false; st.email = ""; st.err = false;
      if (success) success.hidden = true;
      if (form) form.hidden = false;
      paint();
      var first = root.querySelector("[data-gd-form] [data-gd-email]");
      if (first) first.focus();
    });

    // A language switch re-renders the site through esbRender; the guides' own
    // dynamic strings have to go with it or they stay in the previous language.
    var prev = window.esbRender;
    window.esbRender = function () { if (prev) prev.apply(this, arguments); paint(); };

    paint();
  }

  /* ── the mystery discount — design_handoff_mystery_discount ─────────────
     Eight seconds after the visitor settles their TARGET rank on a game page, a
     sealed card is offered; an email buys the right to open it; the reveal
     shows a 30% code and applying it hands them back to their order with the
     total already discounted.

     What is load-bearing here, in the order it bites:

     * **The trigger is a real interaction, never a restore.** It is armed only
       from `change`/`click` events on the rank controls themselves, so a state
       rehydrated out of localStorage, a `?booster=` deep link, a bundle click
       or a game switch can never fire it. The handoff's rule is "settled means
       settled": ~800ms of no rank input, THEN the delay. Anything else is a
       modal over somebody mid-adjustment.
     * **It fires once per visitor, not once per configuration.** A modal that
       comes back when someone nudges a division is the difference between a
       gift and an ambush. The flag is written the moment the card is shown,
       before anything can go wrong, and a decline is free — there is no
       exit-intent second attempt and no re-fire on the next page. The `passed`
       card's own reversal link is the only way back in, and that is the
       visitor's choice.
     * **It never fires over an order that already has a discount** — a typed
       code, an applied bundle, a recovery token, or a campaign link carrying
       one. Two offers on one order is how a buyer learns the price is a
       negotiation.
     * **The client does not mint or know the discount.** `/api/bingo` issues an
       opaque single-use token, mails it, and answers with the percentage; every
       later page re-validates the token before pricing anything with it, which
       is what makes the one-hour deadline real rather than a countdown in a tab
       somebody can leave open.
     * **Applying survives a reload and a re-configure.** The token is what is
       stored; `window.ESB_BINGO` is re-derived from the server on every load,
       and `quote()` re-prices against the new total rather than dropping the
       discount when the buyer extends their climb. Taking a discount away at
       the moment somebody increases their order is the worst possible time. */
  var MYD_KEY = "esb.bingo.v1";
  var MYD_SETTLE = 800;        // handoff: settled means settled, before any timer
  /* The business's own figure, measured from the visitor's LAST rank input —
     "4 seconds after choosing the desired rank", literally. The settle window
     sits INSIDE it rather than being added to it, so this constant is the
     number that was asked for and not 800ms more than it; change it here and
     nowhere else. */
  var MYD_AFTER_PICK = 4000;
  var MYD_OPENING = 1400;      // the "drawing your code" beat
  var MYD_RE = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i;
  // Every control that moves a rank. `to`/`toTier` are the TARGET — "after
  // choosing his desired rank" is the trigger, so one of those has to have been
  // touched at least once before the timer can start; the others only re-settle
  // it, because someone still correcting their current rank has not finished.
  var MYD_TARGET = '[data-sel="to"],[data-sel="toTier"]';
  var MYD_ANY_RANK = '[data-sel="from"],[data-sel="to"],[data-sel="fromTier"],' +
    '[data-sel="toTier"],[data-tiergrid] button,[data-subseg] button';

  function mydRead() {
    try { return JSON.parse(localStorage.getItem(MYD_KEY) || "{}") || {}; }
    catch (e) { return {}; }
  }
  function mydWrite(patch) {
    var rec = mydRead();
    Object.assign(rec, patch);
    try { localStorage.setItem(MYD_KEY, JSON.stringify(rec)); } catch (e) {}
    return rec;
  }

  /* Adopt a token that arrived by link rather than through the modal — today
     the follow-up mail's /checkout?bingo=…, on a browser that may never have
     seen the card. Exposed so checkout's own script does not have to name
     MYD_KEY: this file owns that key, and a second literal spelling of it is
     how the two come to disagree. `prefillEmail` runs for the same reason it
     runs at boot — the address is already known, so nobody is asked twice. */
  window.esbBingoAdopt = function (rec) {
    if (!rec || !rec.token) return;
    mydWrite({ token: rec.token, pct: rec.pct || 0,
               exp: (rec.expires || 0) * 1000,
               mail: rec.email || mydRead().mail || "" });
    if (rec.email) prefillEmail(rec.email, true);   // server-resolved for this token
  };

  /* Fill an email field the site already knows the address for.

     Marked with `data-prefill-email`, not an id — the wiring in this file is
     attribute-based throughout, and checkout's `#k-email` would be the only id
     hook in it. Only ever fills an EMPTY field: a value on screen is something
     the buyer typed, and overwriting it is worse than asking twice. The `input`
     event is dispatched deliberately, so checkout's own abandoned-cart capture
     sees the address the same way it would if it had been typed — without it,
     a buyer who prefilled and then left would be uncapturable.

     Today there is one source (the mystery modal) and one target (checkout).
     A signed-in visitor's verified address is the obvious second source; it
     goes through here rather than growing a second mechanism. */
  function prefillEmail(addr, vouched) {
    if (!addr) return;
    each("[data-prefill-email]", function (el) {
      /* Never over-type the buyer. The one exception is a `vouched` address —
         one the SERVER just resolved for the token in the link they followed —
         landing on a field this function filled itself and nobody has touched
         since. Without it a stale local record wins over the address the mail
         was actually sent to, and the order confirmation goes to the wrong
         inbox on a shared browser. `data-prefilled` is cleared by the first
         real keystroke below, so a typed value is never at risk. */
      if (el.value && !(vouched && el.hasAttribute("data-prefilled"))) return;
      if (el.value === addr) return;
      el.value = addr;
      el.setAttribute("data-prefilled", "");
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  /* One listener, not one per fill: a keystroke means the value on screen is
     the buyer's, whatever put it there first. */
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el && el.hasAttribute && el.hasAttribute("data-prefilled") && e.isTrusted) {
      el.removeAttribute("data-prefilled");
    }
  }, true);

  /* Publish a validated offer to the pricing engine. Runs on EVERY page, not
     just the ones with the modal on them: the discount has to be in the price
     on checkout too, and checkout has no modal. The token is re-checked against
     the store each time rather than trusted from localStorage — an expired or
     already-spent one simply re-prices at the normal sale, which is the correct
     outcome and never an error the buyer has to read. */
  function mydBoot() {
    var rec = mydRead();
    /* The address they gave the modal, carried to checkout so they are not
       asked for it twice. Read from the local record rather than waiting on the
       token resolve below, for two reasons: it is synchronous, so the field is
       filled before the buyer can start typing over it; and it outlives the
       code, so someone whose hour lapsed still doesn't re-type their email. */
    if (rec.mail) prefillEmail(rec.mail);
    if (!rec.token || !window.fetch) return;
    fetch("/api/bingo?token=" + encodeURIComponent(rec.token))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.valid) { mydWrite({ token: "", pct: 0, exp: 0 }); return; }
        window.ESB_BINGO = { token: j.token, pct: j.pct, label: j.label || "Mystery discount" };
        mydWrite({ pct: j.pct, exp: (j.expires || 0) * 1000 });
        render();                       // repaint every price at the new total
      }).catch(function () {});
  }

  function initMystery() {
    var root = document.querySelector("[data-myd]");
    if (!root) return;                  // only the game pages mount it

    var rec = mydRead();
    // Once per visitor. `seen` is written when the card is shown, `declined`
    // when they say no; either one closes the door for good, and a live token
    // means they already have the discount this modal exists to hand out.
    if (rec.seen || rec.declined || rec.token) return;
    // A campaign, recovery or follow-up link carries its own discount — never
    // stack an offer on top of an offer. `bingo` matters on a FRESH browser:
    // the `rec.token` check above covers the visitor whose own card this is,
    // but a link opened somewhere that has never seen the modal has no record
    // to be stopped by.
    if (/[?&](cart|promo|bingo)=/.test(location.search)) return;

    var cards = Array.prototype.slice.call(root.querySelectorAll("[data-myd-card]"));
    var input = root.querySelector("[data-myd-email]");
    var optin = root.querySelector("[data-myd-optin]");
    var noteEl = root.querySelector("[data-myd-note]");
    var openBtn = root.querySelector("[data-myd-open]");
    var st = { pick: "C", email: "", err: false, sending: false, pct: 0,
               token: "", secs: 0, mailed: true, opener: null };
    var settleT = null, fireT = null, openT = null, tick = null;
    var touchedTarget = false;

    function T2(s) { return window.esbT ? window.esbT(s) : s; }
    function view() { return root.getAttribute("data-myd-view"); }
    function isOpen() { return !root.hidden; }
    function fill(attr, text) {
      root.querySelectorAll("[data-myd-" + attr + "]").forEach(function (n) { n.textContent = text; });
    }

    /* Whether this order already carries a discount of its own. Re-checked at
       fire time, not just at boot: a bundle can be applied in the eight seconds
       between the settle and the modal. */
    function hasOffer() {
      var s = window.esbState ? window.esbState() : {};
      return !!(s.promo || (s.bundle !== null && s.bundle !== undefined)
                || window.ESB_RECOVERY || window.ESB_BINGO);
    }
    /* Never open over another surface. The header's menus, its auth panel and
       the nav sheet all own the viewport when they are up, and a visitor in one
       of them is mid-task on something they chose to do. */
    function busyElsewhere() {
      var auth = document.querySelector("[data-hd-auth-panel]");
      var sheet = document.querySelector("[data-hd][data-sheet]");
      return !!(sheet || (auth && !auth.hidden));
    }

    function paint() {
      fill("pick", st.pick);
      cards.forEach(function (c) {
        c.setAttribute("aria-pressed", c.getAttribute("data-myd-card") === st.pick ? "true" : "false");
      });
      if (input) {
        if (input.value !== st.email) input.value = st.email;
        if (st.err) input.setAttribute("data-err", ""); else input.removeAttribute("data-err");
        if (MYD_RE.test(st.email.trim()) && !st.err) input.setAttribute("data-valid", "");
        else input.removeAttribute("data-valid");
      }
      if (noteEl) {
        var msg = st.err === "server"
          ? "That didn't go through. Try again in a moment."
          : st.err ? "Enter an address we can send the code to."
          : "The card is opened on the next screen either way.";
        noteEl.textContent = T2(msg);
        if (st.err) noteEl.setAttribute("data-err", ""); else noteEl.removeAttribute("data-err");
      }
      if (openBtn) openBtn.disabled = !!st.sending;
    }

    /* The reveal's own figures. Quoted twice off the SAME state — once as it
       stands and once with the offer applied — rather than doing arithmetic on
       a displayed string, so the "you save" here and the total the server
       charges are one computation. */
    function paintPrices() {
      var s = window.esbState ? window.esbState() : null;
      if (!s || !window.esbQuote) return;
      var now = window.esbQuote(s);
      var off = window.esbQuote(Object.assign({}, s, {
        recoveryPct: st.pct, promo: st.token, offerLabel: "Mystery discount"
      }));
      if (!now || now.invalid || !off || off.invalid) return;
      fill("was", now.price);
      fill("full", now.price);
      fill("now", off.price);
      fill("save", usd(Math.max(0, now.total - off.total)));
    }

    function setView(v) {
      root.setAttribute("data-myd-view", v);
      // The attribute is what actually shows the step. `ashfall.css` declares
      // `[hidden] { display: none !important }` globally, so a step rendered
      // with `hidden` cannot be revealed by any CSS rule in site.css at any
      // specificity — the view attribute above is the readable state, this is
      // the switch.
      root.querySelectorAll("[data-myd-step]").forEach(function (n) {
        n.hidden = n.getAttribute("data-myd-step") !== v;
      });
      if (v === "reveal") startClock(); else stopClock();
      /* Where focus lands on each step. The email step gets its field — the
         whole card is one question. Every other step focuses the CARD, not its
         first button: the × is the first button in source order, so "the first
         focusable thing" would put a keyboard user on Dismiss with Enter armed.
         From the card, Tab reaches the real controls in reading order. */
      var card = root.querySelector('[data-myd-step="' + v + '"]');
      if (!card) return;
      var target = card.querySelector("[data-myd-email]") || card;
      setTimeout(function () {
        try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
      }, 0);
    }

    function open() {
      if (isOpen()) return;
      st.opener = document.activeElement;
      root.hidden = false;
      document.documentElement.classList.add("myd-open");
      lockScroll(true);
      mydWrite({ seen: 1, at: Date.now() });
      setView("offer");
      paint();
      track("view_promotion", {});
    }

    function close() {
      if (!isOpen()) return;
      // Not while the card is being opened. The request in flight ISSUES a code
      // and mails it; dismissing mid-call would leave the buyer holding a
      // discount they were never shown, and the response would then start a
      // countdown on a closed dialog. It is 1.4 seconds — the × is absent from
      // that step for the same reason.
      if (st.sending || view() === "opening") return;
      stopClock();
      clearTimeout(openT);
      root.hidden = true;
      document.documentElement.classList.remove("myd-open");
      lockScroll(false);
      // Back to the configurator's summary rather than a trigger button — there
      // is no trigger here, so returning focus to "where it came from" is only
      // meaningful when that element is still on the page.
      var back = (st.opener && document.contains(st.opener)) ? st.opener
        : document.querySelector("[data-configurator] [data-out='price']");
      if (back && back.focus) { try { back.focus({ preventScroll: true }); } catch (e) { back.focus(); } }
      st.opener = null;
    }

    /* ── the countdown ──────────────────────────────────────────────────
       Guarded at 59 minutes on the display: initialising at exactly 3600 with
       an mm:ss format renders "00:00" on the first frame, which reads as
       already-expired at the emotional peak. That bug shipped once. */
    function clockText() {
      var m = Math.floor((st.secs % 3600) / 60), sec = st.secs % 60;
      var pad = function (n) { return (n < 10 ? "0" : "") + n; };
      return pad(Math.min(59, m)) + ":" + pad(sec) + " " + T2("left");
    }
    function startClock() {
      stopClock();
      fill("timer", clockText());
      tick = setInterval(function () {
        st.secs = Math.max(0, st.secs - 1);
        fill("timer", clockText());
        // An hour that runs out means it: the offer is gone from the page the
        // same second the server stops honouring it, rather than sitting there
        // looking live. Anything else teaches buyers to ignore every countdown.
        if (st.secs <= 0) { stopClock(); window.ESB_BINGO = null; render(); close(); }
      }, 1000);
    }
    function stopClock() { clearInterval(tick); tick = null; }

    /* ── the trigger ────────────────────────────────────────────────────── */
    function disarm() { clearTimeout(settleT); clearTimeout(fireT); }
    function arm() {
      if (isOpen() || mydRead().seen) return;
      disarm();
      settleT = setTimeout(function () {
        fireT = setTimeout(function () {
          if (isOpen() || mydRead().seen || hasOffer() || busyElsewhere()) return;
          var s = window.esbState ? window.esbState() : null;
          var q = s && window.esbQuote ? window.esbQuote(s) : null;
          // Nothing to discount yet. Not a miss — the visitor simply has not
          // finished, and the next rank touch re-arms the whole sequence.
          if (!q || q.invalid || !q.total) return;
          open();
        }, Math.max(0, MYD_AFTER_PICK - MYD_SETTLE));
      }, MYD_SETTLE);
    }

    function onRankInput(e) {
      var el = e.target && e.target.closest ? e.target.closest(MYD_ANY_RANK) : null;
      if (!el) return;
      if (el.closest && el.closest("[data-myd]")) return;   // never the modal's own controls
      if (el.matches && el.matches(MYD_TARGET)) touchedTarget = true;
      if (el.closest && el.closest('[data-tiergrid="to"],[data-subseg="to"]')) touchedTarget = true;
      if (!touchedTarget) return;
      arm();
    }
    document.addEventListener("change", onRankInput, true);
    document.addEventListener("click", onRankInput, true);

    /* ── step 1 → 2 ─────────────────────────────────────────────────────── */
    cards.forEach(function (c) {
      c.addEventListener("click", function () { st.pick = c.getAttribute("data-myd-card"); paint(); });
    });
    root.querySelectorAll("[data-myd-take]").forEach(function (b) {
      b.addEventListener("click", function () { st.err = false; setView("email"); paint(); });
    });

    /* ── step 2 → the server ────────────────────────────────────────────
       Validated on SUBMIT, not on blur — an error on every keystroke is what
       the handoff asks to avoid — and the button goes inert while it is in
       flight, because a double tap must not issue two codes. */
    function submit() {
      if (st.sending) return;
      st.email = input ? input.value : "";
      if (!MYD_RE.test(st.email.trim())) { st.err = true; paint(); return; }
      st.sending = true; st.err = false; paint();
      setView("opening");

      var s = window.esbState ? window.esbState() : {};
      var shown = Date.now();
      fetch("/api/bingo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        credentials: "same-origin",   // a signed-in visitor's verified address wins
        body: JSON.stringify({
          email: st.email.trim(), pick: st.pick,
          optin: optin && optin.getAttribute("aria-pressed") === "true" ? 1 : 0,
          game: s.game, service: s.service, from: s.from, to: s.to, mode: s.mode,
          region: s.region, addons: s.addons || [], wins: s.wins,
          placements: s.placements, unranked: !!s.unranked,
          booster: s.booster || "", bundle: s.bundle || "",
          /* The currency they are reading the site in. Stored on the row so the
             follow-up mail quotes them in it — a French buyer chased in dollars
             is the same one-set-of-numbers failure a bare `$5` in the chrome
             is. The server re-checks it against pricing.CHARGE_RATES and falls
             back to their country's market, so a junk value cannot mis-quote. */
          cur: ((window.ESB_LOCALE && window.ESB_LOCALE.currency) || "").toLowerCase(),
          tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
          lang: (navigator.language || "")
        })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, body: d }; }); })
        .then(function (res) {
          st.sending = false;
          var j = res.body || {};
          /* Remember the address for checkout. Stored on any answer the server
             accepted — including "your card is already spent", where the email
             is just as valid and the buyer is just as likely to go on and pay.
             Only a 400 (`reason: "email"`) means it was not an address at all. */
          if (res.ok && j.reason !== "email") mydWrite({ mail: st.email.trim() });
          // Hold the opening beat for its full 1.4s even when the server is
          // faster: the spinner is the anticipation the reveal pays off, and a
          // reveal that lands in 200ms reads as a page glitch, not a card.
          var wait = Math.max(0, MYD_OPENING - (Date.now() - shown));
          clearTimeout(openT);
          openT = setTimeout(function () {
            if (!res.ok || !j.ok) {
              // One card per inbox, ever. Said plainly on the declined card
              // rather than by minting a second 30%.
              if (j.reason === "spent") return showSpent();
              st.err = "server"; setView("email"); paint(); return;
            }
            st.pct = j.pct; st.token = j.token;
            st.secs = Math.max(0, (j.seconds || 0) - 1);
            st.mailed = !!j.mailed;
            fill("code", j.token);
            fill("pct", String(Math.round(j.pct * 100)));
            var inbox = root.querySelector("[data-myd-inbox]");
            var nomail = root.querySelector("[data-myd-nomail]");
            if (inbox) inbox.hidden = !st.mailed;
            if (nomail) nomail.hidden = st.mailed;
            paintPrices();
            setView("reveal");
            track("generate_lead", { promotion: "mystery_discount" });
          }, wait);
        }).catch(function () {
          st.sending = false;
          clearTimeout(openT);
          openT = setTimeout(function () { st.err = "server"; setView("email"); paint(); }, 400);
        });
    }
    if (openBtn) openBtn.addEventListener("click", submit);
    if (input) {
      input.addEventListener("input", function () { st.email = input.value; st.err = false; paint(); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); submit(); }
      });
    }
    if (optin) optin.addEventListener("click", function () {
      optin.setAttribute("aria-pressed", optin.getAttribute("aria-pressed") === "true" ? "false" : "true");
    });

    /* ── step 3 — apply ─────────────────────────────────────────────────
       Applying closes the modal and returns the buyer to their order with the
       total already discounted. There is deliberately NO confirmation screen:
       an extra card after the emotional peak asks them to dismiss the same news
       twice, and the discounted total in the configurator's own summary is
       better proof than a modal saying so. It goes back to the configurator
       rather than to checkout because queue, server and add-ons may still be
       unset, and a percentage scales with the order — time spent configuring
       with −30% visible is worth more than one saved tap. */
    root.querySelectorAll("[data-myd-apply]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!st.token) return;
        window.ESB_BINGO = { token: st.token, pct: st.pct, label: "Mystery discount" };
        mydWrite({ token: st.token, pct: st.pct, exp: Date.now() + st.secs * 1000, applied: 1 });
        render();
        track("select_promotion", { promotion: "mystery_discount" });
        try {
          fetch("/api/bingo", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "apply", token: st.token }), keepalive: true
          }).catch(function () {});
        } catch (e) {}
        close();
      });
    });

    /* ── declining, and the one way back in ─────────────────────────────── */
    function showPassed(reason) {
      mydWrite({ declined: 1 });
      root.querySelectorAll("[data-myd-passed-h],[data-myd-passed-p]").forEach(function (n) { n.hidden = reason === "spent"; });
      root.querySelectorAll("[data-myd-spent-h],[data-myd-spent-p]").forEach(function (n) { n.hidden = reason !== "spent"; });
      // The reversal is only offered where there is something to reverse. An
      // inbox that has spent its card cannot pick another one, and a link that
      // walks back to a dead end is worse than no link.
      var undo = root.querySelector("[data-myd-undo]");
      if (undo) undo.hidden = reason === "spent";
      setView("passed");
    }
    function showSpent() { showPassed("spent"); }
    root.querySelectorAll("[data-myd-pass],[data-myd-fullprice]").forEach(function (b) {
      b.addEventListener("click", function () { showPassed(""); });
    });
    root.querySelectorAll("[data-myd-undo]").forEach(function (b) {
      b.addEventListener("click", function () { mydWrite({ declined: 0 }); setView("offer"); paint(); });
    });

    /* ── the code chip is a copy button ─────────────────────────────────── */
    root.querySelectorAll("[data-myd-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var code = (root.querySelector("[data-myd-code]") || {}).textContent || "";
        if (!code || !navigator.clipboard) return;
        navigator.clipboard.writeText(code).then(function () {
          b.setAttribute("data-copied", "");
          setTimeout(function () { b.removeAttribute("data-copied"); }, 1500);
        }).catch(function () {});
      });
    });

    /* ── dismissal: ×, the backdrop, Escape — and a focus trap while open ── */
    root.querySelectorAll("[data-myd-close],[data-myd-back]").forEach(function (b) {
      b.addEventListener("click", close);
    });
    document.addEventListener("keydown", function (e) {
      if (!isOpen()) return;
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key !== "Tab") return;
      var card = root.querySelector('[data-myd-step="' + view() + '"]');
      if (!card) return;
      var f = Array.prototype.slice.call(card.querySelectorAll(
        'a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])'))
        .filter(function (n) { return n.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    // A language switch re-renders the site through esbRender; this card's own
    // runtime strings have to go with it or they stay in the previous language.
    var prevRender = window.esbRender;
    window.esbRender = function () {
      if (prevRender) prevRender.apply(this, arguments);
      if (isOpen()) { paint(); if (view() === "reveal") { fill("timer", clockText()); paintPrices(); } }
    };

    paint();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();

  // Chrome restores <select> values on reload and bfcache restore, after our
  // first paint. Reassert the stored order over whatever it put back.
  window.addEventListener("load", render);
  window.addEventListener("pageshow", function (e) { if (e.persisted) { state = load(); render(); } });
})();
