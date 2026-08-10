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
    from: "Gold IV", to: "Diamond I", mode: "Solo",
    wins: 5, placements: 5, region: "EUW", addons: [], next: "from"
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
        s.from = l[Math.min(3, l.length - 2)];
        s.to = l[Math.min(5, l.length - 1)];
        s.next = "from";
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
  function hasDivs(game, tier) { return divsOf(game, tier).length > 1; }

  function addonPct() {
    var pct = 0;
    (state.addons || []).forEach(function (id) {
      var a = D.addons.filter(function (x) { return x.id === id; })[0];
      if (a) pct += a.pct;
    });
    return pct;
  }

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
          base: 0, addons: 0, days: 0
        };
      }
      var climb = Math.max(1, i - 1);
      base = steps * (D.perStep || per) * factor * (1 + climb * 0.045) * duo;
      days = Math.max(1, Math.round(steps * 0.35 + climb * 0.08));
      summary = s.from + " → " + s.to + " · " + T(s.mode);
    }

    var extra = base * addonPct();
    var total = Math.round(base + extra);
    return {
      invalid: invalid, total: total, base: Math.round(base), addons: Math.round(extra),
      price: usd(total), summary: summary, days: days,
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

    each("[data-out]", function (el) {
      var k = el.getAttribute("data-out");
      var v = {
        price: q.price, eta: q.eta, summary: q.summary, game: state.game,
        mode: T(state.mode), region: state.region,
        free: D.boostersFree, total: q.price,
        summaryUpper: q.summary.toUpperCase(),
        headline: q.invalid ? T("Pick a target above your current rank")
                            : q.summary + " — " + q.price
      }[k];
      if (v !== undefined) el.textContent = v;
    });

    // tier chips (main divisions) — highlighted by the tier each endpoint sits in
    each("[data-ladder]", function (root) {
      var tiers = tiersOf(state.game);
      var i = tiers.indexOf(tierOf(state.game, state.from));
      var j = tiers.indexOf(tierOf(state.game, state.to));
      Array.prototype.forEach.call(root.children, function (chip, idx) {
        var st = (idx === i || idx === j) ? "end"
               : (i >= 0 && j > i && idx > i && idx < j) ? "range" : "idle";
        chip.setAttribute("data-state", st);
        chip.setAttribute("aria-pressed", st === "end" ? "true" : "false");
        chip.querySelector(".tier-tag").textContent =
          (idx === i && idx === j) ? T("YOU · TGT") : idx === i ? T("YOU") : idx === j ? T("TARGET") : "";
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
      el.checked = (state.addons || []).indexOf(el.getAttribute("data-addon")) >= 0;
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
        addonlist: (state.addons || []).map(function (id) {
          var a = D.addons.filter(function (x) { return x.id === id; })[0];
          return a ? T(a.label) : id;
        }).join(", ") || T("None")
      };
      if (map[k] !== undefined) el.textContent = map[k];
    });

    document.dispatchEvent(new CustomEvent("esb:render", { detail: { state: state, quote: q } }));
  }
  window.esbRender = render;

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

  /* ── ladder building (home) — main tiers only; sub-ranks live in the
        two division segments below the ladder ─────────────────────────── */
  function buildLadder(root) {
    var tiers = tiersOf(state.game);
    root.innerHTML = "";
    tiers.forEach(function (name, idx) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "tier";
      b.innerHTML = '<span class="tier-name"></span><span class="tier-tag"></span>';
      b.querySelector(".tier-name").textContent = name;
      b.addEventListener("click", function () { pick(idx); });
      root.appendChild(b);
    });
  }

  // one division segment (Current / Target): a button per sub-rank of the tier
  function buildSubseg(root, which, opts, current) {
    var single = opts.length <= 1;
    root.setAttribute("data-single", single ? "true" : "false");
    root.innerHTML = "";
    opts.forEach(function (full) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "seg-opt seg-sub-opt";
      var div = full.slice(tierOf(state.game, full).length).trim();
      b.textContent = single ? T("No divisions") : div;
      b.setAttribute("aria-pressed", full === current ? "true" : "false");
      if (single) b.disabled = true;
      else b.addEventListener("click", function () { setDiv(which, full); });
      root.appendChild(b);
    });
  }

  // picking a main tier lands you at its entry (lowest) sub-rank
  function pick(idx) {
    var tiers = tiersOf(state.game);
    var t = tiers[idx];
    var subs = divsOf(state.game, t);
    var lo = subs[0], top = subs[subs.length - 1];
    var fromIdx = tiers.indexOf(tierOf(state.game, state.from));

    if (state.next === "from") {
      // choosing the current tier: land on its floor, aim one tier up
      // (or within-tier at an apex tier that has no higher tier to target)
      var up = tiers[Math.min(idx + 1, tiers.length - 1)];
      var toRank = up === t ? top : divsOf(state.game, up)[0];
      set({ from: lo, to: toRank, next: "to" }, "select_item");
    } else if (idx > fromIdx) {
      // target sits in a higher tier → aim at that tier's entry division
      set({ to: lo, next: "from" }, "add_to_cart");
    } else if (idx === fromIdx && top !== state.from) {
      // same tier as current → a within-tier climb (e.g. Bronze IV → Bronze I),
      // then the Target Division segment refines the exact division
      set({ to: top, next: "from" }, "add_to_cart");
    } else {
      // clicked at/below the current tier → restart the pick from here
      var up2 = tiers[Math.min(idx + 1, tiers.length - 1)];
      var toRank2 = up2 === t ? top : divsOf(state.game, up2)[0];
      set({ from: lo, to: toRank2, next: "to" }, "select_item");
    }
  }

  // picking a sub-rank inside a tier; keep the pair valid (target above current)
  function setDiv(which, rank) {
    var full = ladderOf(state.game), at = full.indexOf(rank);
    if (which === "from") {
      var p = { from: rank };
      if (at >= full.indexOf(state.to)) p.to = full[Math.min(at + 1, full.length - 1)];
      set(p, "add_to_cart");
    } else {
      var q = { to: rank };
      if (at <= full.indexOf(state.from)) q.from = full[Math.max(at - 1, 0)];
      set(q, "add_to_cart");
    }
  }

  /* ── wiring ──────────────────────────────────────────────────────────── */
  function ensureGame(game) {
    if (state.game === game) return;
    var tiers = tiersOf(game);
    state.game = game;
    state.from = divsOf(game, tiers[Math.min(2, tiers.length - 2)])[0];
    state.to = divsOf(game, tiers[Math.min(4, tiers.length - 1)])[0];
    state.next = "from";
    if ((D.regions[game] || []).indexOf(state.region) < 0) state.region = (D.regions[game] || [])[0];
    save();
  }

  function wire() {
    // page-scoped game (game detail pages)
    var cfg = document.querySelector("[data-configurator]");
    if (cfg && cfg.getAttribute("data-game")) ensureGame(cfg.getAttribute("data-game"));

    each("[data-ladder]", buildLadder);

    each("[data-game-tag]", function (el) {
      el.addEventListener("click", function () {
        ensureGame(el.getAttribute("data-game-tag"));
        each("[data-ladder]", buildLadder);
        set({}, "select_item");
      });
    });

    each("[data-sel]", function (el) {
      el.addEventListener("change", function () {
        var k = el.getAttribute("data-sel");
        if (k === "game") { ensureGame(el.value); set({}, "select_item"); }
        else if (k === "from") set({ from: el.value }, "add_to_cart");
        else if (k === "to") set({ to: el.value }, "add_to_cart");
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

    // ladder arrow-key navigation
    each("[data-ladder]", function (root) {
      root.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var chips = Array.prototype.slice.call(root.children);
        var i = chips.indexOf(document.activeElement);
        if (i < 0) return;
        e.preventDefault();
        chips[(i + (e.key === "ArrowRight" ? 1 : chips.length - 1)) % chips.length].focus();
      });
    });

    var tgl = document.querySelector("[data-nav-toggle]");
    if (tgl) tgl.addEventListener("click", function () {
      var links = document.querySelector(".nav-links");
      var open = links.classList.toggle("open");
      tgl.setAttribute("aria-expanded", open ? "true" : "false");
    });

    if (document.querySelector(".mobile-bar")) document.body.classList.add("has-bar");

    render();
    initStats();
    initLiveStats();

    if (document.querySelector("[data-configurator]")) track("view_item", itemParams());
  }

  /* ── stat boxes: count-up + rise-in when scrolled into view ──────────── */
  function initStats() {
    var nums = [].slice.call(document.querySelectorAll(".stat b, .statband .v"));
    if (!nums.length) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var hosts = [].slice.call(document.querySelectorAll(".stat, .statband .wrap > div"));

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
      var host = el.closest ? el.closest(".stat, .statband .wrap > div") : null;
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
