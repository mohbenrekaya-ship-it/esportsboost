/* eSports Boost — first-party analytics beacon.
   -------------------------------------------------------------------------
   app.js already emits a clean funnel into window.dataLayer; until now nothing
   read it. This file is the other end: it mirrors those pushes to
   /api/collect, adds the events the dataLayer never had (page_view, configure,
   scroll, errors), and attaches the configurator state to every one of them —
   which is the whole point, because on this site the interesting question is
   never "how many visits" but "what were they configuring when they left".

   Anonymous by construction: a random id in localStorage, no cookie, no
   fingerprint, no personal field, and the server stores no IP. That keeps the
   whole pipeline inside the cookieless audience-measurement exemption, so
   there is no consent banner to add — please keep it that way.

   Opt-outs honoured: Global Privacy Control, and window.ESB_NO_ANALYTICS for
   local debugging. The /ops dashboard never reports on itself.

   Loaded after app.js, so window.esbState / esbQuote / dataLayer already exist.
*/
(function () {
  "use strict";

  var ENDPOINT = "/api/collect";
  var SESSION_IDLE = 30 * 60 * 1000;   // a new session after 30 min idle
  var FLUSH_MS = 2000;                 // batch window
  var MAX_QUEUE = 10;

  // The browser's own IANA timezone. No lookup, no IP, no third party — and
  // on a local or non-Vercel host it is the only thing that can tell you which
  // country a visitor is in.
  var TZ = (function () {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }
    catch (e) { return ""; }
  })();

  var K_ANON = "esb.anon.v1";
  var K_SESS = "esb.sess.v1";
  var K_TOUCH = "esb.touch.v1";
  var K_INTERNAL = "esb.internal.v1";

  if (window.navigator && window.navigator.globalPrivacyControl) return;
  if (window.ESB_NO_ANALYTICS) return;
  if (location.pathname.indexOf("/ops") === 0) return;

  /* Internal traffic — our own browser, permanently. Test orders used to walk
     into the funnel as ordinary sessions, and over a few dozen clicks a handful
     of them moves the conversion rate further than anything a real visitor did:
     `paid` is simply "this session emitted purchase", so a test checkout counts
     exactly like a customer's. Load any page with ?esb_internal=1 to mark this
     browser and ?esb_internal=0 to clear it. A marked browser beacons NOTHING,
     so the store stays clean rather than carrying rows every future reader has
     to remember to filter out. It is per browser AND per profile — mark each
     one you test from, and re-mark after clearing site data.
     `window.ESB_NO_ANALYTICS` is still the one-page-load version of this. */
  function internalBrowser() {
    try {
      var q = new URLSearchParams(location.search);
      if (q.has("esb_internal")) {
        if (q.get("esb_internal") === "0") {
          localStorage.removeItem(K_INTERNAL);
          if (window.console) console.log("[esb] analytics ON — this browser is counted again");
        } else {
          localStorage.setItem(K_INTERNAL, "1");
          if (window.console) console.log("[esb] analytics OFF — this browser is marked internal");
        }
      }
      return localStorage.getItem(K_INTERNAL) === "1";
    } catch (e) { return false; }
  }
  if (internalBrowser()) return;

  /* ── storage helpers — analytics must never break a page ─────────────── */
  function get(key) {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; }
  }
  function put(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }
  function rid() {
    return (Math.random().toString(36).slice(2, 10) +
            Math.random().toString(36).slice(2, 6));
  }

  /* ── identity: one anonymous visitor id, one rolling session ─────────── */
  var anon = get(K_ANON);
  if (typeof anon !== "string" || !anon) { anon = rid(); put(K_ANON, anon); }

  var now = Date.now();
  var sess = get(K_SESS);
  var fresh = false;
  if (!sess || typeof sess.id !== "string" || (now - (sess.last || 0)) > SESSION_IDLE) {
    sess = { id: rid(), last: now, n: 0 };
    fresh = true;
  }

  /* ── first touch: where this visitor originally came from ────────────── */
  var touch = get(K_TOUCH);
  if (!touch) {
    var q = new URLSearchParams(location.search);
    var ref = "";
    try {
      // Host only — never the full referring URL, which can carry a query.
      if (document.referrer) {
        var h = new URL(document.referrer).hostname;
        if (h && h !== location.hostname) ref = h.replace(/^www\./, "");
      }
    } catch (e) {}
    touch = {
      src: q.get("utm_source") || ref || "direct",
      med: q.get("utm_medium") || (ref ? "referral" : "none"),
      cmp: q.get("utm_campaign") || "",
      ref: ref
    };
    put(K_TOUCH, touch);
  }

  /* ── the configurator snapshot carried by every event ────────────────── */
  function snapshot() {
    if (!window.esbState || !window.esbQuote) return null;
    var s, q;
    try { s = window.esbState(); q = window.esbQuote(s); } catch (e) { return null; }
    if (!s) return null;
    var cfg = {
      game: s.game, service: s.service, from: s.from, to: s.to,
      mode: s.mode, region: s.region, addons: (s.addons || []).slice(0, 10)
    };
    if (s.promo) cfg.promo = s.promo;
    if (s.service === "wins") cfg.wins = s.wins;
    if (s.service === "placements") cfg.placements = s.placements;
    if (q) {
      cfg.total = q.total;
      cfg.summary = q.summary || "";
      if (q.invalid) cfg.invalid = true;
    }
    return cfg;
  }

  /* ── queue & flush ───────────────────────────────────────────────────── */
  var queue = [];
  var timer = null;

  function flush() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!queue.length) return;
    var body = JSON.stringify({ events: queue.splice(0, queue.length) });
    try {
      if (navigator.sendBeacon) {
        // A Blob with an explicit type keeps this a simple request (no preflight)
        // and lets it survive the pagehide that usually kills the last event.
        navigator.sendBeacon(ENDPOINT, new Blob([body], { type: "application/json" }));
        return;
      }
    } catch (e) {}
    try {
      fetch(ENDPOINT, {
        method: "POST", body: body, keepalive: true,
        headers: { "Content-Type": "application/json" }
      }).catch(function () {});
    } catch (e) {}
  }

  function emit(name, extra) {
    sess.n += 1;
    sess.last = Date.now();
    put(K_SESS, sess);

    var ev = {
      e: name, a: anon, s: sess.id, n: sess.n,
      p: location.pathname,
      src: touch.src, med: touch.med, cmp: touch.cmp, ref: touch.ref,
      lang: (navigator.language || "").slice(0, 12),
      tz: TZ
    };
    var cfg = snapshot();
    if (cfg) ev.cfg = cfg;
    if (extra) {
      if (extra.val != null) ev.val = extra.val;
      if (extra.meta) ev.meta = extra.meta;
      if (extra.cfg) ev.cfg = extra.cfg;
    }
    queue.push(ev);

    if (queue.length >= MAX_QUEUE) flush();
    else if (!timer) timer = setTimeout(flush, FLUSH_MS);
  }
  window.esbEmit = emit;

  /* ── bridge: every dataLayer push app.js already makes ───────────────── */
  // select_item / add_to_cart are configuration changes under other names —
  // the signature watcher below is the single, de-duplicated source for those,
  // so mirroring them here too would double-count every re-quote.
  var BRIDGE = {
    view_item: "view_item", select_promotion: "select_promotion",
    begin_checkout: "begin_checkout", add_payment_info: "add_payment_info",
    purchase: "purchase", generate_lead: "generate_lead"
  };

  function bridge(payload) {
    if (!payload || typeof payload !== "object") return;
    var name = BRIDGE[payload.event];
    if (!name) return;
    var extra = {};
    if (typeof payload.value === "number") extra.val = payload.value;
    var meta = {};
    if (payload.transaction_id) meta.transaction_id = String(payload.transaction_id);
    if (payload.method) meta.method = String(payload.method);
    if (Object.keys(meta).length) extra.meta = meta;
    emit(name, extra);
  }

  var dl = window.dataLayer = window.dataLayer || [];
  for (var i = 0; i < dl.length; i++) bridge(dl[i]);   // anything already pushed
  var push = dl.push.bind(dl);
  dl.push = function (payload) {
    var out = push(payload);
    try { bridge(payload); } catch (e) {}
    return out;
  };

  /* ── configure: fires only when the quote actually changed ───────────── */
  // Watching the DOM contract (data-sel / data-service / data-mode / …) rather
  // than app.js internals, then comparing signatures, so a click that lands on
  // the same configuration is not a re-quote.
  var lastSig = JSON.stringify(snapshot());
  var configTimer = null;

  function maybeConfigure() {
    if (configTimer) clearTimeout(configTimer);
    configTimer = setTimeout(function () {
      var sig = JSON.stringify(snapshot());
      if (sig === lastSig || sig === "null") return;
      lastSig = sig;
      emit("configure");
    }, 350);
  }

  var WATCH = "[data-sel],[data-service],[data-mode],[data-addon],[data-stepper]," +
              "[data-ladder],[data-promo-apply],[data-panel]";
  document.addEventListener("change", function (e) {
    if (e.target && e.target.closest && e.target.closest(WATCH)) maybeConfigure();
  }, true);
  document.addEventListener("click", function (e) {
    if (e.target && e.target.closest && e.target.closest(WATCH)) maybeConfigure();
  }, true);

  /* ── scroll depth ────────────────────────────────────────────────────── */
  var marks = [25, 50, 75, 100], hit = {}, scrollTimer = null;
  window.addEventListener("scroll", function () {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () {
      scrollTimer = null;
      var h = document.documentElement.scrollHeight - window.innerHeight;
      if (h <= 0) return;
      var pct = Math.min(100, Math.round((window.scrollY / h) * 100));
      for (var j = 0; j < marks.length; j++) {
        if (pct >= marks[j] && !hit[marks[j]]) {
          hit[marks[j]] = 1;
          emit("scroll", { meta: { pct: marks[j] } });
        }
      }
    }, 500);
  }, { passive: true });

  /* ── errors ──────────────────────────────────────────────────────────── */
  window.addEventListener("error", function (e) {
    emit("js_error", {
      meta: {
        message: String((e && e.message) || "error").slice(0, 160),
        source: String((e && e.filename) || "").slice(0, 120),
        line: (e && e.lineno) || 0
      }
    });
  });

  /* ── lifecycle ───────────────────────────────────────────────────────── */
  if (fresh) emit("session_start");
  emit("page_view");

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);
})();
