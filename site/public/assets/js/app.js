/* ─────────────────────────────────────────────────────────────────────────
   esportsboost — client runtime
   One quote function, one render pass. Every price on a given page is derived
   from the same computation, so that page's calculator, sticky bar and CTA
   band can never disagree.

   Each configurator context keeps its OWN order, so independent calculators
   don't mirror each other: the homepage price calculator and a game page's
   wizard are separate configurations. Whichever one you "Continue" from is
   snapshotted into CHECKOUT_KEY, which the checkout page reads.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  var D = window.ESB_DATA;

  // The checkout page reads this snapshot; a configurator commits to it only
  // when the customer clicks Continue (see the [data-continue] handler).
  var CHECKOUT_KEY = "esb.order.v1";

  // Working key for THIS page's configurator. Distinct per context so the
  // homepage calculator and each game-page wizard remember their own picks
  // independently. Pages with no configurator (checkout, success) read the
  // committed snapshot instead.
  function orderKey() {
    var cfg = document.querySelector("[data-configurator]");
    if (!cfg) return CHECKOUT_KEY;
    var g = cfg.getAttribute("data-game");
    if (g) return "esb.order.g." + ((D.slugs && D.slugs[g]) || g);
    return "esb.order.home.v1";
  }
  var KEY = orderKey();

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
  function usd(n, cents) {
    if (window.esbMoney) return window.esbMoney(n, cents);
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

  /* ── state ───────────────────────────────────────────────────────────── */
  var DEFAULT = {
    game: "League of Legends", service: "division",
    from: "Iron IV", to: "Gold IV", mode: "Solo",
    wins: 5, placements: 5, region: "EUW", addons: [], promo: "",
    // A named booster, arriving from a roster Hire or a profile CTA. It is an
    // order attribute, never a price input: pricing.py charges no fee for it,
    // so quote() must not read it. If naming a booster ever costs money it
    // goes into the formula on BOTH sides first.
    booster: ""
  };

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return Object.assign({}, DEFAULT);
      var s = Object.assign({}, DEFAULT, JSON.parse(raw));
      if (!D.ladders[s.game]) return Object.assign({}, DEFAULT);
      var l = D.ladders[s.game];
      var i = l.indexOf(s.from), j = l.indexOf(s.to);
      // A stored pair can only be invalid through tampering or a stale schema;
      // never hand the page a quote that renders as an em dash on first paint.
      if (i < 0 || j < 0 || j <= i) {
        s.from = l[0];
        s.to = l[Math.min(12, l.length - 1)];
      }
      if ((D.regions[s.game] || []).indexOf(s.region) < 0) s.region = (D.regions[s.game] || ["EU"])[0];
      if (s.mode !== "Solo" && s.mode !== "Duo queue") s.mode = "Solo";  // migrate old "Piloted"
      return s;
    } catch (e) { return Object.assign({}, DEFAULT); }
  }

  var state = load();

  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }

  function set(patch, evt) {
    Object.assign(state, patch);
    save();
    render();
    if (evt) track(evt, itemParams());
  }
  window.esbState = function () { return state; };

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

  /* Reads the add-ons off the state it is given, not the live page state —
     pricing.py's _addon_pct() takes them from its argument, so a quote() over
     any state other than the current one used to silently disagree with the
     amount the server charges. */
  function addonPct(s) {
    var pct = 0;
    ((s || state).addons || []).forEach(function (id) {
      var a = D.addons.filter(function (x) { return x.id === id; })[0];
      if (a) pct += a.pct;
    });
    return pct;
  }

  /* Pick the one discount that applies. Mirrors resolve_promo() in
     ../../../src/pricing.py — the auto promo applies with nothing typed, a
     typed code replaces it only when worth more, and discounts never stack. */
  function resolvePromo(code) {
    var promos = D.promos || {}, bestCode = null, best = null;
    for (var k in promos) { if (promos[k].auto) { bestCode = k; best = promos[k]; break; } }
    if (code) {
      var typed = promos[String(code).trim().toUpperCase()];
      if (typed && (!best || typed.pct > best.pct)) {
        bestCode = String(code).trim().toUpperCase(); best = typed;
      }
    }
    return { code: bestCode, promo: best };
  }
  window.esbPromo = resolvePromo;

  function quote(s) {
    var per = D.perDivision;
    var factor = D.factors[s.game] || 1;
    var duo = s.mode === "Duo queue" ? 1.55 : 1;
    var base = 0, days = 0, summary = "", invalid = false;

    if (s.service === "wins") {
      var lw = ladderOf(s.game), iw = lw.indexOf(s.from);
      var w = Math.max(1, s.wins | 0);
      var climbW = Math.max(1, iw - 1);
      base = w * per * 0.55 * factor * (1 + climbW * 0.045) * duo;
      days = Math.max(1, Math.round(w * 0.45));
      summary = w + " " + T(w === 1 ? "net win" : "net wins") + " · " + s.from + " · " + T(s.mode);
    } else if (s.service === "placements") {
      var lp = ladderOf(s.game), ip = lp.indexOf(s.from);
      var p = Math.max(1, s.placements | 0);
      var climbP = Math.max(1, ip - 1);
      base = p * per * 0.7 * factor * (1 + climbP * 0.045) * duo;
      days = Math.max(1, Math.round(p * 0.4));
      summary = p + " " + T(p === 1 ? "placement game" : "placement games") + " · " + s.from + " · " + T(s.mode);
    } else {
      var ladder = ladderOf(s.game);
      var i = ladder.indexOf(s.from), j = ladder.indexOf(s.to);
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
        days = Math.max(1, Math.round(steps * 0.35));
      } else {
        var climb = Math.max(1, i - 1);
        base = steps * (D.perStep || per) * factor * (1 + climb * 0.045) * duo;
        days = Math.max(1, Math.round(steps * 0.35 + climb * 0.08));
      }
      summary = s.from + " → " + s.to + " · " + T(s.mode);
    }

    var extra = base * addonPct(s);
    var subtotal = Math.round(base + extra);

    // Discount comes off the computed price — the strikethrough is a real
    // reduction, never a grossed-up reference price. Mirrors pricing.py.
    var r = resolvePromo(s.promo);
    var discount = r.promo ? Math.round(subtotal * r.promo.pct) : 0;
    var total = subtotal - discount;

    return {
      invalid: invalid, total: total, base: Math.round(base), addons: Math.round(extra),
      subtotal: subtotal, discount: discount,
      price: usd(total), wasPrice: discount ? usd(subtotal) : "",
      discountPrice: discount ? "−" + usd(discount) : "",
      promoCode: r.code || "", promoLabel: r.promo ? r.promo.label : "",
      promoEnds: r.promo ? (r.promo.ends || "") : "",
      summary: summary, days: days,
      eta: days === 1 ? T("about 1 day") : days + " " + T("days")
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
        saveLine: q.discount ? T("You save") + " " + usd(q.discount)
                             + (q.promoEnds ? " · " + T("sale ends") + " " + q.promoEnds : "")
                             : "",
        // Same saving, named by the code that produced it — the order card says
        // which discount is in the price, not when the sale ends.
        saveWith: q.discount ? T("You save") + " " + usd(q.discount)
                             + (q.promoCode ? " " + T("with") + " " + q.promoCode : "")
                             : "",
        summaryUpper: q.summary.toUpperCase(),
        // The card's config line carries the server too, so everything the
        // order is made of reads back in one line above the price.
        configLine: q.invalid ? q.summary.toUpperCase()
                              : q.summary.toUpperCase() + " · " + state.region.toUpperCase(),
        headline: q.invalid ? T("Pick a target above your current rank")
                            : q.summary + " — " + q.price
      }[k];
      if (v !== undefined) el.textContent = v;
    });

    // Discount-only nodes collapse entirely when no promo applies, so an order
    // with no discount never shows an empty row or a bare strikethrough.
    each("[data-when-discount]", function (el) { el.hidden = !q.discount; });

    // Same rule for the named booster: no booster, no row. It costs the order
    // card's fold budget nothing for everyone who didn't come from a Hire.
    each("[data-when-booster]", function (el) { el.hidden = !state.booster; });

    /* The climb, drawn: one tick per rung of the flat ladder with the crossed
       span filled, and the tier names underneath lit for the tiers it covers.
       This is what the two bare rank <select>s never showed — the distance
       being bought, which is the thing the price is actually for. */
    each("[data-ticks]", function (root) {
      fillCells(root, ladder.length, "ob-tick");
      Array.prototype.forEach.call(root.children, function (t, idx) {
        t.setAttribute("data-state",
          (idx === iFrom || idx === iTo) ? "end"
          : (steps > 0 && idx > iFrom && idx < iTo) ? "span" : "idle");
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
      if (fillCells(root, caps.length, "ob-cap", caps)) {
        root.setAttribute("data-dense", "0");
        if (root.scrollWidth > root.clientWidth) root.setAttribute("data-dense", "1");
      }
      var a = caps.indexOf(tierOf(state.game, state.from));
      var b = caps.indexOf(tierOf(state.game, state.to));
      var lo = Math.min(a, b), hi = Math.max(a, b);
      Array.prototype.forEach.call(root.children, function (c, idx) {
        c.setAttribute("data-state", (idx >= lo && idx <= hi) ? "in" : "out");
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
        b.setAttribute("aria-pressed", b.textContent === state.region ? "true" : "false");
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
      el.setAttribute("href", "/games/" + D.slugs[state.game] + ".html#configure");
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
      var a = D.addons.filter(function (x) { return x.id === id; })[0];
      // A zero-cost add-on is always on, and is never carried in state.addons —
      // it has to render ticked or "Included" sits next to an empty box and
      // reads as the opposite of what it says.
      el.checked = (a && a.pct === 0) || (state.addons || []).indexOf(id) >= 0;
    });

    // continue buttons disabled on an impossible pair
    each("[data-continue]", function (el) {
      el.classList.toggle("is-disabled", !!q.invalid);
      el.setAttribute("aria-disabled", q.invalid ? "true" : "false");
    });

    // checkout breakdown
    each("[data-sum]", function (el) {
      var k = el.getAttribute("data-sum");
      var map = {
        base: usd(q.base), addons: q.addons ? "+ " + usd(q.addons) : "—",
        total: usd(q.total), eta: q.eta, summary: q.summary,
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
        addonlist: (state.addons || []).map(function (id) {
          var a = D.addons.filter(function (x) { return x.id === id; })[0];
          return a ? T(a.label) : id;
        }).join(", ") || T("None")
      };
      if (map[k] !== undefined) el.textContent = map[k];
    });

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
        var a = D.addons.filter(function (x) { return x.id === id; })[0];
        return a && a.pct !== 0;
      });
      root.innerHTML = "";
      if (q.invalid) return;
      var running = [];
      var prev = quote(Object.assign({}, state, { addons: [] })).subtotal;
      ids.forEach(function (id) {
        var a = D.addons.filter(function (x) { return x.id === id; })[0];
        running = running.concat([id]);
        var now = quote(Object.assign({}, state, { addons: running })).subtotal;
        var row = document.createElement("div");
        row.className = "co-line";
        var lab = document.createElement("span");
        lab.className = "co-lab";
        lab.textContent = T(a.label);
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

    document.dispatchEvent(new CustomEvent("esb:render", { detail: { state: state, quote: q } }));
  }
  window.esbRender = render;

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

  function setNode(which, i) {
    var l = ladderOf(state.game);
    if (which === "to") {
      i = Math.max(Math.min(l.length - 1, i), nodeAt(state.from) + 1);
      if (l[i] !== state.to) set({ to: l[i] }, "add_to_cart");
    } else {
      i = Math.min(Math.max(0, i), nodeAt(state.to) - 1);
      if (l[i] !== state.from) set({ from: l[i] }, "add_to_cart");
    }
  }

  // Is this node reachable for this end, given where the other end sits?
  function nodeOk(which, i) {
    return which === "to" ? i > nodeAt(state.from) : i < nodeAt(state.to);
  }

  // one division segment (Current / Target): a button per sub-rank of the tier
  function buildSubseg(root, which, opts, current) {
    var single = opts.length <= 1;
    root.setAttribute("data-single", single ? "true" : "false");
    root.innerHTML = "";
    opts.forEach(function (full) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "seg-opt seg-sub-opt";
      b.textContent = single ? T("LP-based — no divisions") : divOf(state.game, full);
      b.setAttribute("aria-pressed", full === current ? "true" : "false");
      if (single) b.disabled = true;
      else if (!nodeOk(which, nodeAt(full))) b.disabled = true;
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

  // A tier is out of range when none of its nodes can serve this end.
  function tierOk(which, tier) {
    var nodes = divsOf(state.game, tier).map(nodeAt);
    return which === "to" ? nodes[nodes.length - 1] > nodeAt(state.from)
                          : nodes[0] < nodeAt(state.to);
  }

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
    root.innerHTML = "";
    list.forEach(function (r) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "bs-regionbtn";
      b.textContent = r;
      b.addEventListener("click", function () { set({ region: r }); });
      root.appendChild(b);
    });
  }

  /* ── wiring ──────────────────────────────────────────────────────────── */
  /* Switching game resets the climb to a sensible mid-ladder default rather
     than trying to carry ranks across two different ladders. */
  function ensureGame(game) {
    if (state.game === game) return;
    var l = ladderOf(game);
    state.game = game;
    state.from = l[0];
    state.to = l[Math.min(12, l.length - 1)];
    if ((D.regions[game] || []).indexOf(state.region) < 0) state.region = (D.regions[game] || [])[0];
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

    function submit() {
      var typed = input.value.trim().toUpperCase();
      if (!typed) { set({ promo: "" }); say("", true); return; }

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
        else if (k === "region") set({ region: el.value });
      });
    });

    each("input[data-mode]", function (el) {
      el.addEventListener("change", function () { if (el.checked) set({ mode: el.value }, "select_item"); });
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
       + ".rvp-chips, .rvp-seg",
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

    if (document.querySelector(".mobile-bar")) document.body.classList.add("has-bar");

    initHeader();
    initOrders();
    render();
    initStats();
    initReveal();
    initCarousel();
    initLiveStats();
    initFeed();
    initRoster();
    initProfile();
    initReviews();

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
        e.stopPropagation();
        if (it.hasAttribute("data-open")) {
          it.removeAttribute("data-open");
          btn.setAttribute("aria-expanded", "false");
        } else openMenu(it);
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
        document.body.classList.add("hd-locked");
        // The handoff opens section 0 by default — a sheet of five closed rows
        // makes the visitor tap twice to see anything. It cannot be marked open
        // in the HTML: at desktop width that same attribute renders the Games
        // mega menu hanging open on load.
        if (!items.some(function (it) { return it.hasAttribute("data-open"); }) && items[0]) {
          openMenu(items[0]);
        }
      } else {
        hd.removeAttribute("data-sheet");
        document.body.classList.remove("hd-locked");
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
    var pass2 = panel && panel.querySelector("[data-hd-pass2]");
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
      document.body.classList.add("hd-locked");
      var first = panel.querySelector("[data-hd-tab]");
      if (first) first.focus();
    }
    function closeAuth() {
      if (!authOpen()) return;
      panel.hidden = true;
      document.body.classList.remove("hd-locked");
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
        if (pass2) pass2.type = t;          // reveal both entries together
      });
    });
    if (pass2) pass2.addEventListener("input", clearErr);
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
        // "Verify" the password: the confirm field has to match.
        if (pass2 && pass2.value !== pw) {
          showErr(hdT("The passwords don't match.")); return;
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
          showErr(hdT("Couldn't reach the server. Check your connection and try again."));
          return;
        }
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

    // A failed OAuth round trip returns to ?auth_error=<message>; surface it in
    // the panel and strip it from the URL so a refresh doesn't re-open it.
    (function () {
      var m = /[?&]auth_error=([^&]*)/.exec(location.search);
      if (!m) return;
      openAuth("signin");
      showErr(decodeURIComponent(m[1].replace(/\+/g, " "))
        || hdT("Sign-in didn't complete. Please try again."));
      try {
        var q = location.search.replace(/([?&])auth_error=[^&]*/, "$1")
          .replace(/[?&]$/, "").replace(/^\?$/, "");
        history.replaceState(null, "", location.pathname + q + location.hash);
      } catch (e) {}
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
  function initOrders() {
    var guest = document.querySelector("[data-ord-guest]");
    var hello = document.querySelector("[data-ord-hello]");
    if (!guest && !hello) return;                 // not the orders page
    var s = null;
    try { s = JSON.parse(localStorage.getItem("esb.session.v1") || "null"); } catch (e) {}
    var on = !!(s && s.name);
    if (guest) guest.hidden = on;
    if (hello) {
      hello.hidden = !on;
      var n = hello.querySelector("[data-ord-name]");
      if (n && on) n.textContent = s.name;        // in its own <b>, i18n-safe
    }
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
    var rows = [].slice.call(body.querySelectorAll("[data-rst-row]"));
    if (!rows.length) return;
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
  function initFeed() {
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
    setInterval(tick, 30000);

    // A language switch re-renders through esbRender; the unit words go with it.
    var prev = window.esbRender;
    window.esbRender = function () { if (prev) prev.apply(this, arguments); tick(); };
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

  /* ── "boosters free now": wander the count so the band reads live ─────── */
  function initLiveStats() {
    var el = document.querySelector('[data-live="free"]');
    if (!el) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    var host = el.closest ? el.closest("[data-live-stat]") : null;
    var base = parseInt((el.getAttribute("data-raw") || el.textContent || "").replace(/[^\d-]/g, ""), 10);
    if (isNaN(base)) return;
    var cur = base, lo = Math.max(1, base - 3), hi = base + 4;

    function tween(to) {
      var from = cur, t0 = null, dur = 650;
      if (host) host.classList.add("bump");
      function step(ts) {
        if (t0 === null) t0 = ts;
        var k = Math.min(1, (ts - t0) / dur);
        el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)));
        if (k < 1) requestAnimationFrame(step);
        else { el.textContent = to; el.setAttribute("data-raw", String(to)); cur = to;
               if (host) setTimeout(function () { host.classList.remove("bump"); }, 260); }
      }
      requestAnimationFrame(step);
    }

    function tick() {
      var next = cur + (Math.random() < 0.5 ? -1 : 1) * (1 + Math.floor(Math.random() * 2));
      next = Math.max(lo, Math.min(hi, next));
      if (next !== cur) tween(next);
      schedule();
    }
    function schedule() { setTimeout(tick, 3800 + Math.random() * 4200); }
    schedule();                          // first wander lands after the count-up settles
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();

  // Chrome restores <select> values on reload and bfcache restore, after our
  // first paint. Reassert the stored order over whatever it put back.
  window.addEventListener("load", render);
  window.addEventListener("pageshow", function (e) { if (e.persisted) { state = load(); render(); } });
})();
