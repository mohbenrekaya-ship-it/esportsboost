/* eSports Boost — /ops analytics console.
   -------------------------------------------------------------------------
   The whole client: login, one filter row, eight panels, and a small set of
   hand-rolled SVG chart primitives. No dependencies, matching the rest of the
   project — and the charts are simple enough that a library would cost more
   than it saved.

   Chart rules this file is built to (they are easy to regress):
     · one y-scale per plot, ever — two measures of different scale become two
       charts, never a second axis,
     · categorical hues in fixed slot order, never cycled; ordered categories
       (funnel stages, price bands) take the one-hue ordinal ramp instead,
     · thin marks, 4px rounded data-ends, hairline recessive grid,
     · a legend whenever two or more series share a plot,
     · every chart has a table-view twin — the toggle in each card header, so
       no value is reachable only by hovering,
     · colors come from ops.css custom properties; nothing is hardcoded here.
*/
(function () {
  "use strict";

  var root = document.querySelector(".ops");
  if (!root) return;

  var CS = getComputedStyle(root);
  function v(name) { return CS.getPropertyValue(name).trim(); }

  var C = {
    ink: v("--ink"), ink2: v("--ink-2"), muted: v("--muted"),
    grid: v("--grid"), axis: v("--axis"), surface: v("--surface"),
    good: v("--good"), warning: v("--warning"), critical: v("--critical"),
    serious: v("--serious")
  };
  // Fixed categorical order. Assigned by slot, never by rank, so a filter that
  // changes the row order never repaints the survivors.
  var SERIES = [v("--s1"), v("--s2"), v("--s3"), v("--s4"),
                v("--s5"), v("--s6"), v("--s7"), v("--s8")];
  // One-hue ordinal ramp, dark→light: on a dark surface magnitude has to run
  // toward the light end or the biggest values disappear into the background.
  var RAMP = [v("--r1"), v("--r2"), v("--r3"), v("--r4"), v("--r5"), v("--r6")];

  /* ── formatting ──────────────────────────────────────────────────────── */
  var fmtUsd = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0
  });
  var fmtUsd2 = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2
  });
  var fmtNum = new Intl.NumberFormat("en-US");

  function usd(n, cents) { return (cents ? fmtUsd2 : fmtUsd).format(n || 0); }
  function num(n) { return fmtNum.format(n || 0); }
  function pct(n) { return (Math.round((n || 0) * 10) / 10) + "%"; }
  function compact(n) {
    n = n || 0;
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return num(n);
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function ago(ts) {
    var d = Math.max(0, Math.floor(Date.now() / 1000) - ts);
    if (d < 60) return d + "s ago";
    if (d < 3600) return Math.floor(d / 60) + "m ago";
    if (d < 86400) return Math.floor(d / 3600) + "h ago";
    return Math.floor(d / 86400) + "d ago";
  }
  /* ── country display ─────────────────────────────────────────────────── */
  // The flag is derived from the ISO code itself (A→🇦 regional indicators), and
  // the name comes from the browser's own locale data — so neither needs a
  // lookup table that would drift as countries are renamed.
  var regionNames = null;
  try { regionNames = new Intl.DisplayNames(undefined, { type: "region" }); } catch (e) {}

  function flag(code) {
    if (!code || code.length !== 2) return "";
    return String.fromCodePoint.apply(null, code.toUpperCase().split("").map(function (c) {
      return 0x1f1e6 + c.charCodeAt(0) - 65;
    }));
  }
  function countryName(code) {
    if (!code) return "";
    try { return (regionNames && regionNames.of(code)) || code; } catch (e) { return code; }
  }
  // How the country was worked out — shown so it is never read as more precise
  // than it is. Timezone and locale are inferences, not an IP lookup.
  var CO_SRC = {
    edge: "from the network edge",
    timezone: "inferred from browser timezone",
    locale: "inferred from browser language — approximate"
  };
  function countryCell(code, src) {
    if (!code) return '<span class="dim">unknown</span>';
    return '<span title="' + esc(CO_SRC[src] || "") + '">' + flag(code) + " " +
           esc(countryName(code)) + "</span>";
  }

  // How the person arrived. `mode` is the account store's field: "oauth:<p>" for
  // a social sign-in, "signup"/"signin" for the email form. Both OAuth and email
  // are grouped by method (Google / Discord / Email); the email rows keep the
  // sign-up vs log-in nuance as a dim note so nothing the old column showed is
  // lost. A brand-coloured dot makes the method scannable down the column.
  function viaMeta(mode) {
    if (mode === "oauth:google") return { label: "Google", cls: "via-google" };
    if (mode === "oauth:discord") return { label: "Discord", cls: "via-discord" };
    if (mode === "signup") return { label: "Email", cls: "via-email", note: "sign-up" };
    if (mode === "signin") return { label: "Email", cls: "via-email", note: "log in" };
    return null;
  }
  function viaCell(mode) {
    var m = viaMeta(mode);
    if (!m) return '<span class="dim">—</span>';
    return '<span class="via"><i class="via-dot ' + m.cls + '"></i>' + esc(m.label) +
      (m.note ? ' <span class="dim">· ' + esc(m.note) + "</span>" : "") + "</span>";
  }
  function viaText(mode) {          // plain-text form for the CSV export
    var m = viaMeta(mode);
    return m ? m.label + (m.note ? " (" + m.note + ")" : "") : "";
  }

  function dur(s) {
    s = Math.max(0, Math.round(s || 0));
    if (s < 60) return s + "s";
    var m = Math.floor(s / 60), r = s % 60;
    if (m < 60) return m + "m" + (r ? " " + r + "s" : "");
    var h = Math.floor(m / 60);
    m = m % 60;
    return h + "h" + (m ? " " + m + "m" : "");
  }
  function stamp(ts) {
    var d = new Date((ts || 0) * 1000);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " " +
           d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function clock(ts) {
    return new Date((ts || 0) * 1000)
      .toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function shortDate(iso) {
    var p = String(iso).split("-");
    return p.length === 3 ? (+p[2]) + " " +
      ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+p[1] - 1]
      : iso;
  }

  /* ── tooltip — one shared node, driven by data-tip on any mark ───────── */
  var tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "status");
  document.body.appendChild(tip);

  function showTip(el, x, y) {
    var html = el.getAttribute("data-tip");
    if (!html) return;
    tip.innerHTML = html;
    tip.setAttribute("data-show", "1");
    var r = tip.getBoundingClientRect();
    var left = Math.max(r.width / 2 + 6, Math.min(window.innerWidth - r.width / 2 - 6, x));
    var top = Math.max(r.height + 12, y);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() { tip.removeAttribute("data-show"); }

  document.addEventListener("mousemove", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (el) showTip(el, e.clientX, e.clientY);
    else hideTip();
  });
  document.addEventListener("focusin", function (e) {
    var el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) return hideTip();
    var r = el.getBoundingClientRect();
    showTip(el, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", hideTip);
  window.addEventListener("scroll", hideTip, true);

  function tipHtml(head, rows) {
    var h = '<div class="t-hd">' + esc(head) + "</div>";
    for (var i = 0; i < rows.length; i++) {
      h += '<div class="t-row">' + esc(rows[i][0]) + " <b>" + esc(rows[i][1]) + "</b></div>";
    }
    return h;
  }

  /* ══════════════════════════════════════════════════════════════════════
     chart primitives — every one returns an SVG string sized to `w`
     ══════════════════════════════════════════════════════════════════════ */
  function niceMax(max) {
    if (max <= 0) return 1;
    var mag = Math.pow(10, Math.floor(Math.log10(max)));
    var n = max / mag;
    var step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
    return step * mag;
  }
  function yTicks(max, count) {
    var top = niceMax(max), out = [];
    for (var i = 0; i <= count; i++) out.push(top * i / count);
    return out;
  }

  /* Multi-series line chart with a crosshair. One y-scale, always. */
  function lineChart(w, opts) {
    var h = opts.height || 220;
    var m = { t: 12, r: 54, b: 26, l: 52 };
    var pw = Math.max(40, w - m.l - m.r), ph = h - m.t - m.b;
    var xs = opts.x || [], series = opts.series || [];
    var fmt = opts.fmt || num;

    var max = 0;
    series.forEach(function (s) {
      s.values.forEach(function (val) { if (val > max) max = val; });
    });
    var top = niceMax(max);
    var ticks = yTicks(max, 4);
    var X = function (i) { return m.l + (xs.length < 2 ? pw / 2 : pw * i / (xs.length - 1)); };
    var Y = function (val) { return m.t + ph - (top ? (val / top) * ph : 0); };

    var s = '<svg class="chart" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
            '" role="img" aria-label="' + esc(opts.alt || "line chart") + '">';

    ticks.forEach(function (t) {
      var y = Y(t);
      s += '<line class="gridline" x1="' + m.l + '" y1="' + y + '" x2="' + (m.l + pw) + '" y2="' + y + '"/>';
      s += '<text class="tick" x="' + (m.l - 8) + '" y="' + (y + 4) + '" text-anchor="end">' +
           esc(opts.tickFmt ? opts.tickFmt(t) : compact(t)) + "</text>";
    });
    s += '<line class="axis" x1="' + m.l + '" y1="' + (m.t + ph) + '" x2="' + (m.l + pw) + '" y2="' + (m.t + ph) + '"/>';

    // x labels — thinned so they never collide
    var every = Math.max(1, Math.ceil(xs.length / Math.max(3, Math.floor(pw / 68))));
    xs.forEach(function (lab, i) {
      if (i % every && i !== xs.length - 1) return;
      s += '<text class="tick" x="' + X(i) + '" y="' + (m.t + ph + 16) + '" text-anchor="middle">' +
           esc(shortDate(lab)) + "</text>";
    });

    series.forEach(function (ser, si) {
      var col = ser.color || SERIES[si % SERIES.length];
      var d = ser.values.map(function (val, i) { return (i ? "L" : "M") + X(i) + " " + Y(val); }).join(" ");
      if (opts.area && series.length === 1) {
        s += '<path d="' + d + " L" + X(ser.values.length - 1) + " " + (m.t + ph) +
             " L" + X(0) + " " + (m.t + ph) + ' Z" fill="' + col + '" opacity="0.10"/>';
      }
      s += '<path d="' + d + '" fill="none" stroke="' + col +
           '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
      var last = ser.values.length - 1;
      if (last >= 0) {
        s += '<circle class="ring" cx="' + X(last) + '" cy="' + Y(ser.values[last]) +
             '" r="4" fill="' + col + '"/>';
        // Direct end-label — the axis carries everything else.
        s += '<text class="val" x="' + (X(last) + 9) + '" y="' + (Y(ser.values[last]) + 4) +
             '">' + esc(fmt(ser.values[last])) + "</text>";
      }
    });

    // Crosshair band per x position: a full-height hit target, so the pointer
    // never has to find a 2px line.
    xs.forEach(function (lab, i) {
      var bw = xs.length < 2 ? pw : pw / (xs.length - 1);
      var rows = series.map(function (ser) { return [ser.name, fmt(ser.values[i])]; });
      s += '<g><rect class="hit" x="' + (X(i) - bw / 2) + '" y="' + m.t + '" width="' + bw +
           '" height="' + ph + '" tabindex="0" role="img" aria-label="' +
           esc(shortDate(lab) + ": " + rows.map(function (r) { return r[0] + " " + r[1]; }).join(", ")) +
           '" data-tip="' + esc(tipHtml(shortDate(lab), rows)) + '"/></g>';
    });

    return s + "</svg>";
  }

  /* Vertical columns. Single series; `ramp` marks an ordered scale. */
  function columns(w, opts) {
    var rows = opts.rows || [];
    var h = opts.height || 220;
    var m = { t: 22, r: 8, b: opts.xTall ? 42 : 26, l: 46 };
    var pw = Math.max(40, w - m.l - m.r), ph = h - m.t - m.b;
    var fmt = opts.fmt || num;
    var max = 0;
    rows.forEach(function (r) { if (r.value > max) max = r.value; });
    var top = niceMax(max);
    var band = rows.length ? pw / rows.length : pw;
    var bw = Math.min(24, band * 0.62);              // cap thickness; leftover is air

    var s = '<svg class="chart" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
            '" role="img" aria-label="' + esc(opts.alt || "column chart") + '">';
    yTicks(max, 4).forEach(function (t) {
      var y = m.t + ph - (top ? (t / top) * ph : 0);
      s += '<line class="gridline" x1="' + m.l + '" y1="' + y + '" x2="' + (m.l + pw) + '" y2="' + y + '"/>';
      s += '<text class="tick" x="' + (m.l - 8) + '" y="' + (y + 4) + '" text-anchor="end">' +
           esc(opts.tickFmt ? opts.tickFmt(t) : compact(t)) + "</text>";
    });
    s += '<line class="axis" x1="' + m.l + '" y1="' + (m.t + ph) + '" x2="' + (m.l + pw) + '" y2="' + (m.t + ph) + '"/>';

    rows.forEach(function (r, i) {
      var cx = m.l + band * (i + 0.5);
      var bh = top ? Math.max(r.value > 0 ? 2 : 0, (r.value / top) * ph) : 0;
      var y = m.t + ph - bh;
      var col = opts.ramp ? RAMP[Math.min(RAMP.length - 1,
                  Math.round((rows.length < 2 ? 1 : i / (rows.length - 1)) * (RAMP.length - 1)))]
                          : (opts.color || SERIES[0]);
      // 4px rounded data-end, square at the baseline.
      s += '<path class="mark" d="' + roundedTop(cx - bw / 2, y, bw, bh, 4) + '" fill="' + col + '"/>';
      s += '<text class="val" x="' + cx + '" y="' + (y - 7) + '" text-anchor="middle">' +
           esc(fmt(r.value)) + "</text>";
      var labels = String(r.label).split("\n");
      labels.forEach(function (line, li) {
        s += '<text class="lbl" x="' + cx + '" y="' + (m.t + ph + 16 + li * 13) +
             '" text-anchor="middle">' + esc(line) + "</text>";
      });
      s += '<rect class="hit" x="' + (cx - band / 2) + '" y="' + m.t + '" width="' + band +
           '" height="' + ph + '" tabindex="0" role="img" aria-label="' +
           esc(String(r.label).replace("\n", " ") + ": " + fmt(r.value)) +
           '" data-tip="' + esc(tipHtml(String(r.label).replace("\n", " "),
             (r.tip || []).concat([[opts.valueName || "Value", fmt(r.value)]]))) + '"/>';
    });
    return s + "</svg>";
  }

  function roundedTop(x, y, w, h, r) {
    if (h <= 0) return "";
    r = Math.min(r, h, w / 2);
    return "M" + x + " " + (y + h) + " L" + x + " " + (y + r) +
           " Q" + x + " " + y + " " + (x + r) + " " + y +
           " L" + (x + w - r) + " " + y +
           " Q" + (x + w) + " " + y + " " + (x + w) + " " + (y + r) +
           " L" + (x + w) + " " + (y + h) + " Z";
  }
  function roundedRight(x, y, w, h, r) {
    if (w <= 0) return "";
    r = Math.min(r, w, h / 2);
    return "M" + x + " " + y + " L" + (x + w - r) + " " + y +
           " Q" + (x + w) + " " + y + " " + (x + w) + " " + (y + r) +
           " L" + (x + w) + " " + (y + h - r) +
           " Q" + (x + w) + " " + (y + h) + " " + (x + w - r) + " " + (y + h) +
           " L" + x + " " + (y + h) + " Z";
  }

  /* Horizontal bars — the right form when the labels are words. */
  function barsH(w, opts) {
    var rows = opts.rows || [];
    var labW = opts.labelWidth || 150;
    var rowH = opts.rowHeight || 30;
    var m = { t: 6, r: 62, b: 6, l: labW };
    var h = m.t + m.b + rows.length * rowH;
    var pw = Math.max(40, w - m.l - m.r);
    var fmt = opts.fmt || num;
    var max = 0;
    rows.forEach(function (r) { if (r.value > max) max = r.value; });
    var top = niceMax(max);
    var bh = Math.min(24, rowH * 0.56);

    var s = '<svg class="chart" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
            '" role="img" aria-label="' + esc(opts.alt || "bar chart") + '">';
    rows.forEach(function (r, i) {
      var cy = m.t + rowH * i + rowH / 2;
      var bwid = top ? Math.max(r.value > 0 ? 2 : 0, (r.value / top) * pw) : 0;
      var col = opts.ramp ? RAMP[Math.min(RAMP.length - 1,
                  Math.round((rows.length < 2 ? 1 : (rows.length - 1 - i) / (rows.length - 1)) * (RAMP.length - 1)))]
                          : (r.color || opts.color || SERIES[0]);
      s += '<text class="lbl" x="' + (labW - 12) + '" y="' + (cy + 4) + '" text-anchor="end">' +
           esc(r.label) + "</text>";
      s += '<path class="mark" d="' + roundedRight(m.l, cy - bh / 2, bwid, bh, 4) + '" fill="' + col + '"/>';
      s += '<text class="val" x="' + (m.l + bwid + 9) + '" y="' + (cy + 4) + '">' + esc(fmt(r.value)) + "</text>";
      s += '<rect class="hit" x="0" y="' + (cy - rowH / 2) + '" width="' + w + '" height="' + rowH +
           '" tabindex="0" role="img" aria-label="' + esc(r.label + ": " + fmt(r.value)) +
           '" data-tip="' + esc(tipHtml(r.label, (r.tip || []).concat([[opts.valueName || "Value", fmt(r.value)]]))) + '"/>';
    });
    return s + "</svg>";
  }

  /* Funnel: ordered stages, so one-hue ordinal ramp — never categorical. */
  function funnelChart(w, rows) {
    var labW = 168, rowH = 46;
    var m = { t: 8, r: 108, b: 8, l: labW };
    var h = m.t + m.b + rows.length * rowH;
    var pw = Math.max(40, w - m.l - m.r);
    var top = rows.length ? rows[0].sessions : 0;
    var bh = 20;

    var s = '<svg class="chart" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
            '" role="img" aria-label="Funnel from visit to payment">';
    rows.forEach(function (r, i) {
      var cy = m.t + rowH * i + rowH / 2;
      var bwid = top ? Math.max(r.sessions > 0 ? 2 : 0, (r.sessions / top) * pw) : 0;
      var col = RAMP[Math.min(RAMP.length - 1,
                  Math.round(((rows.length - 1 - i) / Math.max(1, rows.length - 1)) * (RAMP.length - 1)))];
      s += '<text class="lbl" x="' + (labW - 14) + '" y="' + (cy + 4) + '" text-anchor="end">' +
           esc(r.label) + "</text>";
      s += '<path class="mark" d="' + roundedRight(m.l, cy - bh / 2, bwid, bh, 4) + '" fill="' + col + '"/>';
      s += '<text class="val" x="' + (m.l + bwid + 10) + '" y="' + (cy + 4) + '">' +
           esc(num(r.sessions) + "  ·  " + pct(r.pct_total)) + "</text>";
      // Drop-off sits between the stages it happened between.
      if (i > 0 && r.lost > 0) {
        s += '<text x="' + (labW - 14) + '" y="' + (cy - rowH / 2 + 4) + '" text-anchor="end" ' +
             'style="fill:' + C.critical + ';font-size:11px">−' + esc(num(r.lost)) + " lost</text>";
        s += '<line class="gridline" x1="' + m.l + '" y1="' + (cy - rowH / 2) + '" x2="' +
             (m.l + pw) + '" y2="' + (cy - rowH / 2) + '"/>';
      }
      s += '<rect class="hit" x="0" y="' + (cy - rowH / 2) + '" width="' + w + '" height="' + rowH +
           '" tabindex="0" role="img" aria-label="' +
           esc(r.label + ": " + num(r.sessions) + " sessions, " + pct(r.pct_total) + " of all") +
           '" data-tip="' + esc(tipHtml(r.label, [
             ["Sessions", num(r.sessions)],
             ["Of all sessions", pct(r.pct_total)],
             ["Of previous step", pct(r.pct_prev)],
             ["Lost here", num(r.lost)]
           ])) + '"/>';
    });
    return s + "</svg>";
  }

  /* Rank-pair heatmap: magnitude on a grid → one-hue sequential ramp. */
  function heatmap(w, opts) {
    var tiers = opts.tiers || [], cells = opts.cells || [];
    if (!tiers.length) return "";
    var m = { t: 22, r: 8, b: 8, l: 92 };
    var size = Math.max(22, Math.min(54, (w - m.l - m.r) / tiers.length));
    var h = m.t + m.b + tiers.length * size;
    var byKey = {};
    var max = 0;
    cells.forEach(function (c) {
      byKey[c.f + "|" + c.t] = c;
      if (c.n > max) max = c.n;
    });

    var s = '<svg class="chart" width="' + (m.l + tiers.length * size + m.r) + '" height="' + h +
            '" viewBox="0 0 ' + (m.l + tiers.length * size + m.r) + ' ' + h +
            '" role="img" aria-label="Rank pairs configured, current rank by target rank">';
    tiers.forEach(function (t, j) {
      s += '<text class="tick" x="' + (m.l + size * (j + 0.5)) + '" y="' + (m.t - 8) +
           '" text-anchor="middle">' + esc(t.slice(0, 4)) + "</text>";
    });
    tiers.forEach(function (f, i) {
      s += '<text class="lbl" x="' + (m.l - 10) + '" y="' + (m.t + size * (i + 0.5) + 4) +
           '" text-anchor="end">' + esc(f) + "</text>";
      tiers.forEach(function (t, j) {
        var c = byKey[f + "|" + t];
        var x = m.l + size * j, y = m.t + size * i;
        if (!c) {
          s += '<rect class="cell" x="' + x + '" y="' + y + '" width="' + size + '" height="' + size +
               '" fill="' + C.grid + '" opacity="0.35"/>';
          return;
        }
        var step = max <= 1 ? RAMP.length - 1
                 : Math.min(RAMP.length - 1, Math.floor((c.n / max) * (RAMP.length - 1) + 0.001));
        s += '<rect class="cell" x="' + x + '" y="' + y + '" width="' + size + '" height="' + size +
             '" fill="' + RAMP[step] + '" tabindex="0" role="img" aria-label="' +
             esc(f + " to " + t + ": " + c.n + " configured, " + c.orders + " paid") +
             '" data-tip="' + esc(tipHtml(f + " → " + t, [
               ["Configured", num(c.n)], ["Paid", num(c.orders)],
               ["Conversion", pct(c.cr)], ["Revenue", usd(c.revenue)]
             ])) + '"/>';
        if (size >= 30) {
          // Ink or white by the fill's lightness, so the count always clears.
          s += '<text x="' + (x + size / 2) + '" y="' + (y + size / 2 + 4) +
               '" text-anchor="middle" style="fill:' + (step >= 3 ? "#0b0b0b" : C.ink) +
               ';font-size:11px;pointer-events:none">' + esc(String(c.n)) + "</text>";
        }
      });
    });
    return s + "</svg>";
  }

  /* Connected dot plot — two measures per item, the GAP is the story. */
  function dumbbell(w, opts) {
    var rows = opts.rows || [];
    var labW = opts.labelWidth || 160, rowH = 30;
    var m = { t: 10, r: 48, b: 10, l: labW };
    var h = m.t + m.b + rows.length * rowH;
    var pw = Math.max(40, w - m.l - m.r);
    var max = 0;
    rows.forEach(function (r) { max = Math.max(max, r.a, r.b); });
    var top = niceMax(max);
    var X = function (val) { return m.l + (top ? (val / top) * pw : 0); };

    var s = '<svg class="chart" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
            '" role="img" aria-label="' + esc(opts.alt || "comparison") + '">';
    rows.forEach(function (r, i) {
      var cy = m.t + rowH * i + rowH / 2;
      s += '<text class="lbl" x="' + (labW - 12) + '" y="' + (cy + 4) + '" text-anchor="end">' +
           esc(r.label) + "</text>";
      s += '<line x1="' + X(Math.min(r.a, r.b)) + '" y1="' + cy + '" x2="' + X(Math.max(r.a, r.b)) +
           '" y2="' + cy + '" stroke="' + C.axis + '" stroke-width="2" stroke-linecap="round"/>';
      s += '<circle class="ring" cx="' + X(r.a) + '" cy="' + cy + '" r="5" fill="' + SERIES[0] + '"/>';
      s += '<circle class="ring" cx="' + X(r.b) + '" cy="' + cy + '" r="5" fill="' + SERIES[1] + '"/>';
      var gap = r.b - r.a;
      s += '<text class="val" x="' + (w - 6) + '" y="' + (cy + 4) + '" text-anchor="end" style="fill:' +
           (gap >= 0 ? C.good : C.critical) + '">' + esc((gap >= 0 ? "+" : "") + gap.toFixed(1)) + "</text>";
      s += '<rect class="hit" x="0" y="' + (cy - rowH / 2) + '" width="' + w + '" height="' + rowH +
           '" tabindex="0" role="img" aria-label="' +
           esc(r.label + ": " + opts.aName + " " + pct(r.a) + ", " + opts.bName + " " + pct(r.b)) +
           '" data-tip="' + esc(tipHtml(r.label, (r.tip || []).concat([
             [opts.aName, pct(r.a)], [opts.bName, pct(r.b)],
             ["Gap", (gap >= 0 ? "+" : "") + gap.toFixed(1) + " pts"]
           ]))) + '"/>';
    });
    return s + "</svg>";
  }

  function sparkline(w, h, values, color) {
    if (!values.length) return "";
    var max = Math.max.apply(null, values) || 1;
    var d = values.map(function (val, i) {
      return (i ? "L" : "M") + (values.length < 2 ? w / 2 : (w * i / (values.length - 1))) +
             " " + (h - (val / max) * (h - 3) - 1.5);
    }).join(" ");
    return '<svg class="spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h +
           '" aria-hidden="true"><path d="' + d + '" fill="none" stroke="' + (color || SERIES[0]) +
           '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>';
  }

  /* ── card factory: chart + its table-view twin ───────────────────────── */
  var painters = [];

  function card(opts) {
    var el = document.createElement("div");
    el.className = "card" + (opts.cls ? " " + opts.cls : "");
    var id = "c" + painters.length;
    el.innerHTML =
      '<div class="card-hd"><h3 id="' + id + '-t">' + esc(opts.title) + "</h3>" +
      '<span class="spacer"></span>' +
      (opts.table ? '<button class="toggle" type="button" aria-pressed="false">Table</button>' : "") +
      "</div>" +
      (opts.sub ? '<p class="card-sub">' + esc(opts.sub) + "</p>" : "") +
      (opts.legend ? legendHtml(opts.legend) : "") +
      '<div class="body scroll-x"></div>';

    var body = el.querySelector(".body");
    var showTable = false;

    function paint() {
      if (showTable) {
        body.innerHTML = tableHtml(opts.table);
        return;
      }
      var w = Math.max(280, body.clientWidth || el.clientWidth - 36);
      var out = opts.chart ? opts.chart(w) : "";
      body.innerHTML = out || '<p class="empty">No data in this period.</p>';
    }
    painters.push(paint);

    var tog = el.querySelector(".toggle");
    if (tog) {
      tog.addEventListener("click", function () {
        showTable = !showTable;
        tog.setAttribute("aria-pressed", showTable ? "true" : "false");
        tog.textContent = showTable ? "Chart" : "Table";
        paint();
      });
    }
    return el;
  }

  function legendHtml(keys) {
    return '<div class="legend">' + keys.map(function (k) {
      return '<span class="key"><i class="' + (k.line ? "line" : "") + '" style="background:' +
             k.color + '"></i>' + esc(k.name) + "</span>";
    }).join("") + "</div>";
  }

  function tableHtml(t) {
    if (!t || !t.rows || !t.rows.length) return '<p class="empty">No data in this period.</p>';
    var h = '<table class="tbl"><thead><tr>';
    t.head.forEach(function (c, i) {
      h += '<th class="' + (t.num && t.num.indexOf(i) >= 0 ? "num" : "") + '">' + esc(c) + "</th>";
    });
    h += "</tr></thead><tbody>";
    t.rows.forEach(function (r) {
      h += "<tr>";
      r.forEach(function (c, i) {
        var isNum = t.num && t.num.indexOf(i) >= 0;
        h += '<td class="' + (isNum ? "num" : "wrap-cell") + '">' +
             (c && c.html ? c.html : esc(c)) + "</td>";
      });
      h += "</tr>";
    });
    return h + "</tbody></table>";
  }

  function plainTable(head, rows, numCols) {
    var el = document.createElement("div");
    el.className = "scroll-x";
    el.innerHTML = tableHtml({ head: head, rows: rows, num: numCols });
    return el;
  }

  /* ══════════════════════════════════════════════════════════════════════
     state & API
     ══════════════════════════════════════════════════════════════════════ */
  var state = { token: null, days: 30, game: "", tab: "liveview", data: null, busy: false,
                // The period, as a preset key plus the absolute pair it resolves
                // to. `days` is kept in step because the Orders / Carts /
                // Accounts / Guides / Boosters actions still take a trailing
                // day count and have no range parameter yet.
                range: "30d", start: null, end: null,
                sessionId: null, sessionDetail: null,
                // Seeded rows are excluded from every number server-side unless
                // this is on. Off by default and deliberately not persisted: a
                // sticky "include synthetic" is how a seeded conversion rate
                // gets read as real three weeks later.
                synthetic: false,
                // The sign-up list is fetched on demand (it is PII, kept off the
                // main payload) and cached until the period changes.
                accounts: null, accountsLoading: false, accountsError: null,
                // The roster store — its own separate store, fetched on demand
                // like the sign-up list and cached until refreshed.
                boosters: null, boostersLoading: false, boostersError: null,
                // The free-guides mailing list — another separate store, fetched
                // on demand (it is PII) and cached until the period changes.
                guides: null, guidesLoading: false, guidesError: null,
                // The orders store — receipts fulfilment writes (PII), fetched on
                // demand. `orderId`/`orderDetail` drive the click-through drill-down,
                // the same master-detail shape as Sessions.
                orders: null, ordersLoading: false, ordersError: null,
                orderId: null, orderDetail: null,
                // The abandoned-checkout store — captured emails + the config the
                // buyer was about to pay for. Its own store (PII), fetched on
                // demand. Distinct from the "Abandoned" tab, which is the
                // anonymous analytics view with no email attached.
                carts: null, cartsLoading: false, cartsError: null,
                // Auto-refresh: poll the dashboard so the numbers stay live
                // without a manual Refresh. Default on.
                live: true };

  try { state.token = sessionStorage.getItem("esb.ops.token") || null; } catch (e) {}

  function api(body) {
    return fetch("/api/ops", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; })
        .then(function (d) { return { status: r.status, body: d }; });
    });
  }

  var gate = document.querySelector("[data-gate]");
  var app = document.querySelector("[data-app]");
  var errBox = document.querySelector("[data-gate-err]");

  var setupNote = document.querySelector("[data-gate-setup]");

  function login(pw) {
    errBox.textContent = "";
    return api({ action: "login", password: pw, days: state.days,
                 start: state.start, end: state.end,
                 tzoff: new Date().getTimezoneOffset() }).then(function (res) {
      if (res.status === 200) {
        state.token = res.body.token;
        try { sessionStorage.setItem("esb.ops.token", state.token); } catch (e) {}
        state.data = res.body.data;
        gate.hidden = true;
        app.hidden = false;
        render();
        startLive();
        return;
      }
      // Distinguish "no password is configured" (a server-side setup problem the
      // note explains) from "that password is wrong" (a typo). Conflating them
      // sends someone editing environment variables to fix a typo.
      var configured = res.status !== 503;
      if (setupNote) setupNote.hidden = configured;
      errBox.textContent =
        res.status === 503 ? (res.body.message || "The dashboard is not configured yet.") :
        res.status === 401 ? "Wrong password." :
        res.status === 429 ? (res.body.message || "Too many attempts. Try again shortly.") :
        "Could not sign in.";
    }).catch(function () {
      errBox.textContent = "Could not reach the server. Is it running?";
    });
  }

  // `silent` skips the dim-hold, so a background live poll refreshes the numbers
  // in place instead of strobing the whole dashboard to 45% every interval.
  function refresh(silent) {
    if (!state.token || state.busy) return Promise.resolve();
    state.busy = true;
    if (!silent) app.classList.add("loading");   // hold the old render, never a skeleton flash
    return api({ action: "data", token: state.token, days: state.days,
                 start: state.start, end: state.end,
                 tzoff: new Date().getTimezoneOffset(),
                 game: state.game || null, synthetic: state.synthetic })
      .then(function (res) {
        state.busy = false;
        app.classList.remove("loading");
        if (res.status === 200) {
          state.data = res.body.data;
          render();
          // The Accounts, Guides and Boosters panels have their own stores, so a
          // data refresh does not carry them — reload alongside so "Live" keeps
          // them fresh.
          if (state.tab === "accounts") loadAccounts();
          if (state.tab === "guides") loadGuides();
          if (state.tab === "boosters") loadBoosters();
          if (state.tab === "orders" && !state.orderId) loadOrders();
          if (state.tab === "carts") loadCarts();
          return;
        }
        toGate();
      }).catch(function () {
        state.busy = false;
        app.classList.remove("loading");
      });
  }

  function toGate() {
    state.token = null;
    try { sessionStorage.removeItem("esb.ops.token"); } catch (e) {}
    stopLive();
    app.hidden = true;
    gate.hidden = false;
  }

  /* ── auto-refresh ─────────────────────────────────────────────────────────
     "Real time" here is a short client poll, not a socket: the store is read
     and every figure recomputed server-side per request (insights.py), and the
     Vercel functions are stateless, so a poll is the honest fit. It pauses when
     the tab is hidden — a backgrounded dashboard should not hammer the store —
     and skips a tick whenever a fetch is still in flight (refresh guards on
     state.busy). */
  var LIVE_MS = 10000;
  var liveTimer = null;

  function liveTick() {
    if (!state.live || document.hidden || state.busy) return;
    refresh(true);           // silent — no dim-hold on a background poll
  }

  function startLive() {
    stopLive();
    if (state.live) liveTimer = setInterval(liveTick, LIVE_MS);
  }

  function stopLive() {
    if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
  }

  document.addEventListener("visibilitychange", function () {
    // Coming back to the tab should feel current, not one interval stale.
    if (!document.hidden && state.live && state.token) refresh();
  });

  /* ══════════════════════════════════════════════════════════════════════
     panels
     ══════════════════════════════════════════════════════════════════════ */
  function kpi(label, value, delta, spark, hero) {
    var el = document.createElement("div");
    el.className = "kpi" + (hero ? " hero" : "");
    var d = "";
    if (delta != null) {
      var up = delta >= 0;
      d = '<div class="delta"><span class="' + (up ? "up" : "down") + '">' +
          (up ? "▲" : "▼") + " " + Math.abs(delta).toFixed(1) + "%</span> vs previous period</div>";
    } else if (delta === null) {
      d = '<div class="delta">no previous period</div>';
    }
    el.innerHTML = '<div class="lab">' + esc(label) + '</div><div class="val">' + esc(value) + "</div>" + d +
                   (spark || "");
    return el;
  }

  function panelOverview(d) {
    var f = document.createDocumentFragment();
    var o = d.overview, ts = d.timeseries;

    var row = document.createElement("div");
    row.className = "kpis";
    var revs = ts.map(function (r) { return r.revenue; });
    var sess = ts.map(function (r) { return r.sessions; });
    row.appendChild(kpi("Revenue", usd(o.revenue), o.delta.revenue, sparkline(120, 26, revs, SERIES[2]), true));
    row.appendChild(kpi("Orders", num(o.orders), o.delta.orders));
    row.appendChild(kpi("Conversion rate", pct(o.cr), o.delta.cr));
    row.appendChild(kpi("Average order", usd(o.aov, true)));
    row.appendChild(kpi("Sessions", num(o.sessions), o.delta.sessions, sparkline(120, 26, sess, SERIES[0])));
    row.appendChild(kpi("Visitors", num(o.visitors)));
    f.appendChild(row);

    var g = document.createElement("div");
    g.className = "grid";

    // Two measures, two charts — never a second y-axis on one plot.
    g.appendChild(card({
      cls: "half", title: "Sessions and orders",
      sub: "Both are counts, so they share one scale honestly.",
      legend: [{ name: "Sessions", color: SERIES[0], line: true },
               { name: "Orders", color: SERIES[1], line: true }],
      chart: function (w) {
        return lineChart(w, {
          x: ts.map(function (r) { return r.d; }),
          series: [{ name: "Sessions", values: sess, color: SERIES[0] },
                   { name: "Orders", values: ts.map(function (r) { return r.orders; }), color: SERIES[1] }],
          alt: "Sessions and orders per day"
        });
      },
      table: {
        head: ["Day", "Sessions", "Visitors", "Orders"], num: [1, 2, 3],
        rows: ts.map(function (r) { return [r.d, num(r.sessions), num(r.visitors), num(r.orders)]; })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Revenue per day",
      sub: "Its own chart because dollars and counts do not share a scale.",
      chart: function (w) {
        return lineChart(w, {
          x: ts.map(function (r) { return r.d; }),
          series: [{ name: "Revenue", values: revs, color: SERIES[2] }],
          area: true, fmt: function (n) { return usd(n); },
          tickFmt: function (n) { return usd(n); },
          alt: "Revenue per day"
        });
      },
      table: {
        head: ["Day", "Revenue", "Orders"], num: [1, 2],
        rows: ts.map(function (r) { return [r.d, usd(r.revenue, true), num(r.orders)]; })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Funnel",
      sub: "Sessions reaching each step. Steps are cumulative, so a later step always implies the earlier ones.",
      chart: function (w) { return funnelChart(w, d.funnel); },
      table: {
        head: ["Step", "Sessions", "Of all", "Of previous", "Lost here"], num: [1, 2, 3, 4],
        rows: d.funnel.map(function (r) {
          return [r.label, num(r.sessions), pct(r.pct_total), pct(r.pct_prev), num(r.lost)];
        })
      }
    }));

    var cf = d.configurator;
    g.appendChild(card({
      cls: "half", title: "Conversion by quoted price",
      sub: "Sessions grouped by the price they were quoted. Where this bends is your ceiling.",
      chart: function (w) {
        return columns(w, {
          rows: cf.price.map(function (r) {
            return { label: r.label, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          fmt: pct, tickFmt: pct, valueName: "Conversion", color: SERIES[0],
          alt: "Conversion rate by quoted price band"
        });
      },
      table: {
        head: ["Price band", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: cf.price.map(function (r) {
          return [r.label, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));
    f.appendChild(g);
    return f;
  }

  function panelFunnel(d) {
    var g = document.createElement("div");
    g.className = "grid";
    var fr = d.friction;

    g.appendChild(card({
      title: "Where sessions are lost",
      sub: "Every step of the order flow, from landing to paid.",
      chart: function (w) { return funnelChart(w, d.funnel); },
      table: {
        head: ["Step", "Sessions", "Of all", "Of previous", "Lost here"], num: [1, 2, 3, 4],
        rows: d.funnel.map(function (r) {
          return [r.label, num(r.sessions), pct(r.pct_total), pct(r.pct_prev), num(r.lost)];
        })
      }
    }));

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Started checkout", num(fr.abandon.began)));
    kr.appendChild(kpi("Reached payment", num(fr.abandon.at_payment + fr.abandon.paid)));
    kr.appendChild(kpi("Paid", num(fr.abandon.paid)));
    kr.appendChild(kpi("Abandon rate", pct(fr.abandon.rate)));
    kr.appendChild(kpi("Value walked away", usd(fr.abandon.lost)));
    kr.appendChild(kpi("Median re-quotes", num(medianRequotes(d))));
    g.appendChild(wrapCard("After checkout starts",
      "Of the sessions that reached checkout, how many finished — and what the ones that didn't were worth.", kr));

    g.appendChild(card({
      cls: "half", title: "Conversion by re-quote count",
      sub: "How many times the configuration changed before the session ended. Heavy re-quoting is price shopping.",
      chart: function (w) {
        return columns(w, {
          rows: d.configurator.thrash.map(function (r) {
            return { label: r.label, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)]] };
          }),
          fmt: pct, tickFmt: pct, valueName: "Conversion", ramp: true,
          alt: "Conversion rate by number of re-quotes"
        });
      },
      table: {
        head: ["Re-quotes", "Sessions", "Orders", "Conversion"], num: [1, 2, 3],
        rows: d.configurator.thrash.map(function (r) {
          return [r.label, num(r.sessions), num(r.orders), pct(r.cr)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Conversion by device",
      chart: function (w) {
        return barsH(w, {
          rows: fr.devices.map(function (r) {
            return { label: r.name, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          fmt: pct, valueName: "Conversion", labelWidth: 100, color: SERIES[0],
          alt: "Conversion rate by device"
        });
      },
      table: {
        head: ["Device", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: fr.devices.map(function (r) {
          return [r.name, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));
    return g;
  }

  function medianRequotes(d) {
    var t = d.configurator.thrash, best = 0, seen = 0, half = 0;
    t.forEach(function (r) { half += r.sessions; });
    half = half / 2;
    for (var i = 0; i < t.length; i++) {
      seen += t[i].sessions;
      if (seen >= half) { best = parseInt(t[i].label, 10) || 0; break; }
    }
    return best;
  }

  function wrapCard(title, sub, node) {
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML = '<div class="card-hd"><h3>' + esc(title) + "</h3></div>" +
                   (sub ? '<p class="card-sub">' + esc(sub) + "</p>" : "");
    el.appendChild(node);
    return el;
  }

  function panelConfigurator(d) {
    var cf = d.configurator;
    var g = document.createElement("div");
    g.className = "grid";

    g.appendChild(card({
      cls: "twothirds",
      title: "Rank pairs configured — " + cf.focus,
      sub: "Rows are the current rank, columns the target. Darker means fewer configured, lighter means more. " +
           "Division orders only; switch game in the filter row.",
      chart: function (w) { return heatmap(w, { tiers: cf.tiers, cells: cf.matrix }); },
      table: {
        head: ["From", "To", "Configured", "Paid", "Conversion", "Revenue"], num: [2, 3, 4, 5],
        rows: cf.matrix.map(function (r) {
          return [r.f, r.t, num(r.n), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "third", title: "Price sensitivity",
      sub: "Conversion by the price quoted.",
      chart: function (w) {
        return barsH(w, {
          rows: cf.price.map(function (r) {
            return { label: r.label, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)]] };
          }),
          fmt: pct, valueName: "Conversion", labelWidth: 90, ramp: true,
          alt: "Conversion rate by price band"
        });
      },
      table: {
        head: ["Band", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: cf.price.map(function (r) {
          return [r.label, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Attention vs revenue by game",
      sub: "Share of configured sessions against share of revenue. A game far below the line is eating traffic without paying for it.",
      legend: [{ name: "Share of sessions", color: SERIES[0] },
               { name: "Share of revenue", color: SERIES[1] }],
      chart: function (w) {
        return dumbbell(w, {
          rows: cf.games.filter(function (r) { return r.sessions > 0; }).map(function (r) {
            return { label: r.name, a: r.share_traffic, b: r.share_revenue,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Revenue", usd(r.revenue)], ["Conversion", pct(r.cr)]] };
          }),
          aName: "Share of sessions", bName: "Share of revenue",
          alt: "Share of sessions versus share of revenue by game"
        });
      },
      table: {
        head: ["Game", "Sessions", "Traffic share", "Orders", "Revenue", "Revenue share", "Conversion"],
        num: [1, 2, 3, 4, 5, 6],
        rows: cf.games.map(function (r) {
          return [r.name, num(r.sessions), pct(r.share_traffic), num(r.orders),
                  usd(r.revenue), pct(r.share_revenue), pct(r.cr)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Add-on attach rate",
      sub: "Share of configured sessions that included each add-on. Lift compares that session's conversion with the " +
           pct(cf.base_cr) + " baseline.",
      chart: function (w) {
        return barsH(w, {
          rows: cf.addons.map(function (r) {
            return { label: r.label.length > 26 ? r.label.slice(0, 25) + "…" : r.label,
                     value: r.attach,
                     tip: [["Sessions", num(r.sessions)], ["Conversion", pct(r.cr)],
                           ["Lift vs baseline", (r.lift >= 0 ? "+" : "") + r.lift + " pts"],
                           ["Revenue", usd(r.revenue)]] };
          }),
          fmt: pct, valueName: "Attach rate", labelWidth: 180, color: SERIES[0],
          alt: "Add-on attach rate"
        });
      },
      table: {
        head: ["Add-on", "Price uplift", "Attach", "Sessions", "Conversion", "Lift", "Revenue"],
        num: [1, 2, 3, 4, 5, 6],
        rows: cf.addons.map(function (r) {
          return [r.label, pct(r.pct * 100), pct(r.attach), num(r.sessions), pct(r.cr),
                  (r.lift >= 0 ? "+" : "") + r.lift, usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Solo vs duo",
      sub: "Duo carries a ×1.55 multiplier — this is where you find out whether it is worth it.",
      chart: function (w) {
        return barsH(w, {
          rows: cf.modes.map(function (r) {
            return { label: r.name, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Average order", usd(r.aov, true)]] };
          }),
          fmt: pct, valueName: "Conversion", labelWidth: 110, color: SERIES[0],
          alt: "Conversion by queue mode"
        });
      },
      table: {
        head: ["Mode", "Sessions", "Orders", "Conversion", "Average order", "Revenue"],
        num: [1, 2, 3, 4, 5],
        rows: cf.modes.map(function (r) {
          return [r.name, num(r.sessions), num(r.orders), pct(r.cr), usd(r.aov, true), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Service mix",
      chart: function (w) {
        return barsH(w, {
          rows: cf.services.map(function (r) {
            return { label: r.name, value: r.sessions,
                     tip: [["Orders", num(r.orders)], ["Conversion", pct(r.cr)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          valueName: "Sessions", labelWidth: 110, color: SERIES[0],
          alt: "Sessions by service type"
        });
      },
      table: {
        head: ["Service", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: cf.services.map(function (r) {
          return [r.name, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));
    return g;
  }

  function panelJourney(d) {
    var j = d.journey;
    var g = document.createElement("div");
    g.className = "grid";

    g.appendChild(card({
      cls: "half", title: "Sessions before paying",
      sub: "Median time from first ever visit to payment: " +
           (j.median_lag_min >= 60 ? (j.median_lag_min / 60).toFixed(1) + " hours"
                                   : j.median_lag_min + " minutes") + ".",
      chart: function (w) {
        return columns(w, {
          rows: j.sessions_to_buy.map(function (r) { return { label: r.n, value: r.count }; }),
          valueName: "Buyers", ramp: true, alt: "Number of sessions before purchase"
        });
      },
      table: {
        head: ["Session number", "Buyers"], num: [1],
        rows: j.sessions_to_buy.map(function (r) { return [r.n, num(r.count)]; })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Time from first visit to payment",
      chart: function (w) {
        return columns(w, {
          rows: j.lag.map(function (r) { return { label: r.label.replace(" ", "\n"), value: r.count }; }),
          valueName: "Buyers", ramp: true, xTall: true, alt: "Time to purchase"
        });
      },
      table: {
        head: ["Window", "Buyers"], num: [1],
        rows: j.lag.map(function (r) { return [r.label, num(r.count)]; })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "First visit vs returning",
      sub: "A returning visitor already has a saved configuration waiting for them.",
      chart: function (w) {
        return barsH(w, {
          rows: j.cohorts.map(function (r) {
            return { label: r.name, value: r.cr,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          fmt: pct, valueName: "Conversion", labelWidth: 110, color: SERIES[0],
          alt: "Conversion by visitor recency"
        });
      },
      table: {
        head: ["Cohort", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: j.cohorts.map(function (r) {
          return [r.name, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Landing page value",
      sub: "Where sessions start, and what each entry point is worth.",
      chart: function (w) {
        return barsH(w, {
          rows: j.entry.slice(0, 8).map(function (r) {
            return { label: r.page, value: r.sessions,
                     tip: [["Orders", num(r.orders)], ["Conversion", pct(r.cr)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          valueName: "Sessions", labelWidth: 150, color: SERIES[0],
          alt: "Sessions by entry page"
        });
      },
      table: {
        head: ["Entry page", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: j.entry.map(function (r) {
          return [r.page, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(wrapCard("Most common paths",
      "The page sequence each session followed, most frequent first.",
      plainTable(["Path", "Sessions", "Orders", "Conversion", "Revenue"],
        j.paths.map(function (r) {
          return [r.path, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        }), [1, 2, 3, 4])));
    return g;
  }

  function panelAcquisition(d) {
    var a = d.acquisition;
    var g = document.createElement("div");
    g.className = "grid";

    g.appendChild(card({
      cls: "half", title: "Revenue per session by source",
      sub: "First-touch attribution. This is the number that decides where the next ad dollar goes.",
      chart: function (w) {
        return barsH(w, {
          rows: a.slice(0, 10).map(function (r) {
            return { label: r.source + " / " + r.medium, value: r.rps,
                     tip: [["Sessions", num(r.sessions)], ["Orders", num(r.orders)],
                           ["Revenue", usd(r.revenue)], ["Conversion", pct(r.cr)]] };
          }),
          fmt: function (n) { return usd(n, true); }, valueName: "Per session",
          labelWidth: 160, color: SERIES[0], alt: "Revenue per session by traffic source"
        });
      },
      table: {
        head: ["Source", "Medium", "Campaign", "Sessions", "Orders", "Conversion", "Revenue", "Per session"],
        num: [3, 4, 5, 6, 7],
        rows: a.map(function (r) {
          return [r.source, r.medium, r.campaign || "—", num(r.sessions), num(r.orders),
                  pct(r.cr), usd(r.revenue), usd(r.rps, true)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Sessions by source",
      chart: function (w) {
        return barsH(w, {
          rows: a.slice(0, 10).map(function (r) {
            return { label: r.source + " / " + r.medium, value: r.sessions,
                     tip: [["Revenue", usd(r.revenue)], ["Conversion", pct(r.cr)]] };
          }),
          valueName: "Sessions", labelWidth: 160, color: SERIES[0],
          alt: "Sessions by traffic source"
        });
      },
      table: {
        head: ["Source", "Medium", "Sessions", "Revenue"], num: [2, 3],
        rows: a.map(function (r) { return [r.source, r.medium, num(r.sessions), usd(r.revenue)]; })
      }
    }));

    g.appendChild(wrapCard("Countries",
      "From the network edge in production, or inferred from the browser's timezone. " +
      "Never from an IP lookup we perform.",
      plainTable(["Country", "Sessions", "Orders", "Conversion", "Revenue"],
        d.friction.countries.map(function (r) {
          var code = r.name && r.name !== "unknown" ? r.name : "";
          return [{ html: countryCell(code, "") }, num(r.sessions), num(r.orders),
                  pct(r.cr), usd(r.revenue)];
        }), [1, 2, 3, 4])));
    return g;
  }

  function panelFriction(d) {
    var fr = d.friction;
    var f = document.createDocumentFragment();

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Checkout abandon rate", pct(fr.abandon.rate)));
    kr.appendChild(kpi("Value walked away", usd(fr.abandon.lost), undefined, "", true));
    kr.appendChild(kpi("Stuck at payment", num(fr.abandon.at_payment)));
    kr.appendChild(kpi("Error events", num(fr.errors.reduce(function (n, r) { return n + r.count; }, 0))));
    kr.appendChild(kpi("Sessions hitting an error",
      num(fr.errors.reduce(function (n, r) { return n + r.sessions; }, 0))));
    kr.appendChild(kpi("Left on an impossible rank pair", num(fr.abandon.invalid)));
    f.appendChild(kr);

    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(wrapCard("Errors seen by customers",
      "Checkout failures and script errors, most frequent first. Every one of these is a paying customer meeting a wall.",
      plainTable(["Kind", "Message", "Events", "Sessions"],
        fr.errors.map(function (r) {
          return [r.kind === "checkout_error" ? "Checkout" : "Script", r.message,
                  num(r.count), num(r.sessions)];
        }), [2, 3])));

    g.appendChild(card({
      cls: "half", title: "Sessions by device",
      chart: function (w) {
        return barsH(w, {
          rows: fr.devices.map(function (r) {
            return { label: r.name, value: r.sessions,
                     tip: [["Orders", num(r.orders)], ["Conversion", pct(r.cr)],
                           ["Revenue", usd(r.revenue)]] };
          }),
          valueName: "Sessions", labelWidth: 100, color: SERIES[0], alt: "Sessions by device"
        });
      },
      table: {
        head: ["Device", "Sessions", "Orders", "Conversion", "Revenue"], num: [1, 2, 3, 4],
        rows: fr.devices.map(function (r) {
          return [r.name, num(r.sessions), num(r.orders), pct(r.cr), usd(r.revenue)];
        })
      }
    }));

    g.appendChild(card({
      cls: "half", title: "Conversion by device",
      chart: function (w) {
        return barsH(w, {
          rows: fr.devices.map(function (r) {
            return { label: r.name, value: r.cr, tip: [["Sessions", num(r.sessions)]] };
          }),
          fmt: pct, valueName: "Conversion", labelWidth: 100, color: SERIES[0],
          alt: "Conversion rate by device"
        });
      },
      table: {
        head: ["Device", "Conversion", "Sessions"], num: [1, 2],
        rows: fr.devices.map(function (r) { return [r.name, pct(r.cr), num(r.sessions)]; })
      }
    }));
    f.appendChild(g);
    return f;
  }

  /* ── Sessions: the list, and one session in full ─────────────────────── */
  function panelSessions(d) {
    if (state.sessionId) return panelSessionDetail();

    var rows = d.sessions || [];
    var f = document.createDocumentFragment();

    var kr = document.createElement("div");
    kr.className = "kpis";
    var withPages = rows.filter(function (r) { return r.duration > 0; });
    var median = 0;
    if (withPages.length) {
      var ds = withPages.map(function (r) { return r.duration; }).sort(function (a, b) { return a - b; });
      median = ds[Math.floor(ds.length / 2)];
    }
    kr.appendChild(kpi("Sessions", num(rows.length)));
    kr.appendChild(kpi("Median duration", dur(median)));
    kr.appendChild(kpi("Pages per session",
      rows.length ? (rows.reduce(function (n, r) { return n + r.pages; }, 0) / rows.length).toFixed(1) : "0"));
    kr.appendChild(kpi("Events per session",
      rows.length ? (rows.reduce(function (n, r) { return n + r.events; }, 0) / rows.length).toFixed(1) : "0"));
    kr.appendChild(kpi("Converted", num(rows.filter(function (r) { return r.paid; }).length)));
    kr.appendChild(kpi("Returning", num(rows.filter(function (r) { return r.returning; }).length)));
    f.appendChild(kr);

    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every session</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-sessions>Export CSV</button></div>' +
      '<p class="card-sub">Newest first. Click a session id to see everything that visitor did, ' +
      "in order, with the time spent on each page.</p>";

    if (!rows.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No sessions in this period yet. Browse the site and hit Refresh.</p>');
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Session", "Source", "Device", "Country", "Entry → Exit",
                "Pages", "Time", "Events", "Got to", "Value"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) {
        return '<th class="' + ([6, 7, 8, 10].indexOf(i) >= 0 ? "num" : "") + '">' + esc(h) + "</th>";
      }).join("") + "</tr></thead><tbody>";

    rows.forEach(function (r) {
      var route = r.entry === r.exit ? r.entry : (r.entry + " → " + r.exit);
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.end)) + "</td>" +
        '<td><button class="link-btn" type="button" data-session="' + esc(r.id) + '">' +
          esc(r.id.slice(0, 10)) + "</button>" +
          (r.returning ? '<span class="chip">returning</span>' : "") + "</td>" +
        "<td>" + esc(r.src) + '<span class="dim"> / ' + esc(r.med) + "</span>" +
          (r.cmp ? '<br><span class="dim">' + esc(r.cmp) + "</span>" : "") + "</td>" +
        "<td>" + esc(r.dev) + "</td>" +
        "<td>" + countryCell(r.co, r.cosrc) + "</td>" +
        '<td class="wrap-cell">' + esc(route) + "</td>" +
        '<td class="num">' + num(r.pages) + "</td>" +
        '<td class="num">' + esc(dur(r.duration)) + "</td>" +
        '<td class="num">' + num(r.events) + "</td>" +
        "<td>" + esc(r.step || "—") +
          (r.paid ? ' <span class="chip good">paid</span>' : "") + "</td>" +
        '<td class="num">' + (r.value ? esc(usd(r.value)) : "—") + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.addEventListener("click", function (e) {
      var b = e.target.closest("[data-session]");
      if (b) openSession(b.getAttribute("data-session"));
    });

    el.querySelector("[data-export-sessions]").addEventListener("click", function () {
      var cols = ["started", "ended", "session_id", "visitor_id", "source", "medium", "campaign",
                  "device", "country_code", "country", "country_source", "timezone", "language",
                  "entry", "exit", "pages", "seconds", "events", "requotes", "furthest_step",
                  "paid", "value_usd", "returning"];
      var lines = [cols.join(",")];
      rows.forEach(function (r) {
        lines.push([new Date(r.start * 1000).toISOString(), new Date(r.end * 1000).toISOString(),
                    r.id, r.anon, r.src, r.med, r.cmp, r.dev, r.co, countryName(r.co),
                    r.cosrc, r.tz, r.lang, r.entry, r.exit,
                    r.pages, r.duration, r.events, r.requotes, r.step, r.paid ? "yes" : "no",
                    r.value, r.returning ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      a.download = "esb-sessions-" + new Date().toISOString().slice(0, 10) + ".csv";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  function fact(label, value) {
    return '<div class="fact"><span class="fact-l">' + esc(label) + '</span>' +
           '<span class="fact-v">' + esc(value || "—") + "</span></div>";
  }

  function panelSessionDetail() {
    var f = document.createDocumentFragment();

    var back = document.createElement("button");
    back.className = "btn btn-sm back-btn";
    back.type = "button";
    back.textContent = "← All sessions";
    back.addEventListener("click", function () {
      state.sessionId = null;
      state.sessionDetail = null;
      render();
    });
    f.appendChild(back);

    var det = state.sessionDetail;
    if (!det) {
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading session…</p>';
      f.appendChild(wait);
      return f;
    }

    var s = det.summary;

    // Who and where from
    var meta = document.createElement("div");
    meta.className = "card";
    meta.innerHTML =
      '<div class="card-hd"><h3>Session ' + esc(s.id.slice(0, 10)) + "</h3>" +
      '<span class="spacer"></span>' +
      (s.paid ? '<span class="chip good">paid ' + esc(usd(s.value)) + "</span>"
              : '<span class="chip">' + esc(s.step || "no activity") + "</span>") + "</div>" +
      '<p class="card-sub">Started ' + esc(stamp(s.start)) + " · lasted " + esc(dur(s.duration)) +
      " · " + num(s.pages) + " page" + (s.pages === 1 ? "" : "s") + " · " +
      num(s.events) + " events</p>" +
      '<div class="facts">' +
        fact("Came from", s.src + " / " + s.med) +
        fact("Campaign", s.cmp) +
        fact("Device", s.dev) +
        fact("Country", s.co ? flag(s.co) + " " + countryName(s.co) : "unknown") +
        fact("How we know", CO_SRC[s.cosrc] || "—") +
        fact("Timezone", s.tz) +
        fact("Language", s.lang) +
        fact("Visitor", s.anon.slice(0, 10) + (s.returning ? " · returning" : " · first visit")) +
        fact("Landed on", s.entry) +
        fact("Left from", s.exit) +
        fact("Re-quotes", String(s.requotes)) +
        fact("Game", s.game) +
        fact("Last configuration", s.summary) +
        fact("Value", s.value ? usd(s.value) : "—") +
      "</div>";
    f.appendChild(meta);

    var g = document.createElement("div");
    g.className = "grid";

    // Time consumed per page
    var pages = (det.pages || []).slice().sort(function (a, b) { return b.seconds - a.seconds; });
    g.appendChild(card({
      cls: "half", title: "Time spent on each page",
      sub: "Measured between events. The last page of a session has no closing event, so its " +
           "time is a floor, not the full dwell.",
      chart: function (w) {
        return barsH(w, {
          rows: pages.map(function (p) {
            return { label: p.path, value: p.seconds,
                     tip: [["Visits", num(p.visits)],
                           ["Measured", p.partial ? "at least this" : "exact"]] };
          }),
          fmt: dur, valueName: "Time", labelWidth: 170, color: SERIES[0],
          alt: "Time spent on each page"
        });
      },
      table: {
        head: ["Page", "Time", "Visits"], num: [1, 2],
        rows: pages.map(function (p) {
          return [p.path, dur(p.seconds) + (p.partial ? "+" : ""), num(p.visits)];
        })
      }
    }));

    // The full timeline
    var tl = document.createElement("div");
    tl.className = "card half";
    var items = (det.timeline || []).map(function (t) {
      var bits = [];
      if (t.summary) bits.push(t.summary);
      if (t.price) bits.push(usd(t.price));
      if (t.invalid) bits.push("impossible rank pair");
      if (t.region) bits.push(t.region);
      if (t.addons && t.addons.length) bits.push("+ " + t.addons.join(", "));
      if (t.meta && t.meta.pct) bits.push("scrolled " + t.meta.pct + "%");
      if (t.meta && t.meta.message) bits.push(t.meta.message);
      if (t.meta && t.meta.transaction_id) bits.push(t.meta.transaction_id);
      return '<li class="ev">' +
        '<span class="ev-t">+' + esc(dur(t.offset)) + "</span>" +
        '<span class="ev-dot" data-e="' + esc(t.e) + '" aria-hidden="true"></span>' +
        '<span class="ev-body"><b>' + esc(t.label) + "</b>" +
          (t.path ? '<span class="ev-path">' + esc(t.path) + "</span>" : "") +
          (bits.length ? '<span class="ev-note">' + esc(bits.join(" · ")) + "</span>" : "") +
          '<span class="ev-clock">' + esc(clock(t.t)) +
            (t.gap ? " · waited " + esc(dur(t.gap)) : "") + "</span>" +
        "</span></li>";
    }).join("");
    tl.innerHTML = '<div class="card-hd"><h3>Everything they did</h3></div>' +
      '<p class="card-sub">In order, from the first event to the last.</p>' +
      '<ol class="timeline">' + items + "</ol>";
    g.appendChild(tl);

    f.appendChild(g);
    return f;
  }

  function openSession(id) {
    state.sessionId = id;
    state.sessionDetail = null;
    render();
    api({ action: "session", token: state.token, session_id: id }).then(function (res) {
      if (res.status === 200) {
        state.sessionDetail = res.body.session;
      } else {
        state.sessionId = null;
      }
      render();
    }).catch(function () {
      state.sessionId = null;
      render();
    });
  }

  /* ── Accounts — the header sign-up list ───────────────────────────────────
     A separate store from the analytics events, fetched on demand because it
     is the one place emails live. There is no password here — the sign-up flow
     drops it in the browser (see app.js). Right now this is effectively a lead
     list: the site has no real account system yet, so every row is someone who
     asked to make one. */
  function loadAccounts() {
    if (state.accountsLoading) return;
    state.accountsLoading = true;
    state.accountsError = null;
    api({ action: "accounts", token: state.token, days: state.days }).then(function (res) {
      state.accountsLoading = false;
      if (res.status === 200 && res.body.accounts) {
        state.accounts = res.body.accounts;         // swaps in place; no loading flash
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        // 200 without an `accounts` payload means the server is running older
        // code that doesn't know this action — the exact symptom of a serve.py
        // started before /api/account existed. Say so instead of spinning.
        state.accountsError = "This server doesn't serve the sign-up list yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.accountsError = "Couldn't load sign-ups — the server returned " + res.status + ".";
      }
      if (state.tab === "accounts") render();
    }).catch(function () {
      state.accountsLoading = false;
      state.accountsError = "Couldn't reach the server. Is it running?";
      if (state.tab === "accounts") render();
    });
  }

  function panelAccounts() {
    var f = document.createDocumentFragment();
    var a = state.accounts;

    // Error, and nothing cached to fall back on: show what went wrong plus a
    // retry, never an endless spinner.
    if (state.accountsError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.accountsError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm";
      retry.type = "button";
      retry.textContent = "Try again";
      retry.style.margin = "0 auto 16px";
      retry.style.display = "block";
      retry.addEventListener("click", function () { state.accountsError = null; loadAccounts(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }

    if (!a) {
      loadAccounts();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading sign-ups…</p>';
      f.appendChild(wait);
      return f;
    }

    // Placeholder banner — the account system is a facade, so these leads are
    // real emails against an auth flow that does not create a real account yet.
    // Say so, the same way the synthetic-data banner does.
    var note = document.createElement("div");
    note.className = "banner synthetic";
    note.innerHTML = '<span class="ico">▲</span><div><strong>Sign-up list, not an account system.</strong> ' +
      "The header auth panel is a facade — there is no session, verification or password store yet " +
      "(passwords never leave the browser). These are the names and emails people submitted, kept so " +
      "the list survives until a real backend lands. Treat them as leads, and as personal data.</div>";
    f.appendChild(note);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes synthetic sign-ups.</strong> ' +
        num(a.synthetic) + " row(s) were seeded for testing. Clear the store before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Sign-ups (all time)", num(a.total), undefined, "", true));
    kr.appendChild(kpi("In this period", num(a.in_window)));
    kr.appendChild(kpi("Last 24 hours", num(a.last_24h)));
    kr.appendChild(kpi("Last 7 days", num(a.last_7d)));
    // Emails are unique by construction (accounts.py dedupes on ingest), so a
    // count here would just echo the total. Surface a repeat only if one ever
    // slips through — it would mean the store's uniqueness broke.
    if (a.repeat > 0) kr.appendChild(kpi("Duplicate emails ⚠", num(a.repeat)));
    f.appendChild(kr);

    var g = document.createElement("div");
    g.className = "grid";

    // Sign-ups per day across the window.
    var series = a.series || [];
    g.appendChild(card({
      cls: "half", title: "Sign-ups per day",
      sub: "New submissions in the selected period, one bar per day.",
      chart: function (w) {
        return columns(w, {
          rows: series.map(function (r) { return { label: shortDate(r.date), value: r.count }; }),
          color: SERIES[0], alt: "Sign-ups per day", valueName: "Sign-ups", xTall: series.length > 20
        });
      },
      table: {
        head: ["Day", "Sign-ups"], num: [1],
        rows: series.map(function (r) { return [r.date, num(r.count)]; })
      }
    }));

    // Country split — same resolution the sessions use (edge / timezone / locale).
    var countries = a.countries || [];
    g.appendChild(card({
      cls: "half", title: "Where they signed up",
      sub: "Country is resolved server-side, never from an IP — see how each was inferred in the table.",
      chart: function (w) {
        return barsH(w, {
          rows: countries.slice(0, 10).map(function (c) {
            return { label: (flag(c.code) + " " + countryName(c.code)).trim(), value: c.count };
          }),
          color: SERIES[2], alt: "Sign-ups by country"
        });
      },
      table: {
        head: ["Country", "Sign-ups"], num: [1],
        rows: countries.map(function (c) { return [countryName(c.code), num(c.count)]; })
      }
    }));
    f.appendChild(g);

    // The list itself.
    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Sign-ups</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-accounts>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > recent.length ? ", most recent " + num(recent.length) + " of " + num(a.total) : "") +
      ". Name and email only — no password is ever stored.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No sign-ups yet. Open the header, create an account, and hit Refresh.</p>');
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Name", "Email", "Country", "Via"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.ts)) + "</td>" +
        "<td>" + esc(r.name || "—") + (r.syn ? ' <span class="chip">synthetic</span>' : "") + "</td>" +
        "<td>" + esc(r.email) + "</td>" +
        "<td>" + countryCell(r.co, r.cosrc) + "</td>" +
        "<td>" + viaCell(r.mode) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-accounts]").addEventListener("click", function () {
      var cols = ["signed_up", "name", "email", "country_code", "country", "country_source", "via", "synthetic"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([new Date(r.ts * 1000).toISOString(), r.name, r.email, r.co, countryName(r.co),
                    r.cosrc, viaText(r.mode), r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "esb-signups-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  /* ── Guides mails — the free-guides mailing list ──────────────────────────
     A separate store again (see guides.py), fetched on demand because it is the
     other place emails live. No password here — the guides form drops a lead
     beacon (see app.js). One address, one row; a repeat is dropped on ingest. */
  var GUIDE_NAMES = { lol: "League", val: "Valorant" };
  function guideLabel(k) { return GUIDE_NAMES[k] || k; }

  function loadGuides() {
    if (state.guidesLoading) return;
    state.guidesLoading = true;
    state.guidesError = null;
    api({ action: "guides", token: state.token, days: state.days }).then(function (res) {
      state.guidesLoading = false;
      if (res.status === 200 && res.body.guides) {
        state.guides = res.body.guides;             // swaps in place; no loading flash
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        // 200 without a `guides` payload means the server is running older code
        // that doesn't know this action — the exact symptom of a serve.py started
        // before /api/guides existed. Say so instead of spinning.
        state.guidesError = "This server doesn't serve the guides list yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.guidesError = "Couldn't load guides mails — the server returned " + res.status + ".";
      }
      if (state.tab === "guides") render();
    }).catch(function () {
      state.guidesLoading = false;
      state.guidesError = "Couldn't reach the server. Is it running?";
      if (state.tab === "guides") render();
    });
  }

  function panelGuides() {
    var f = document.createDocumentFragment();
    var a = state.guides;

    if (state.guidesError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.guidesError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm";
      retry.type = "button";
      retry.textContent = "Try again";
      retry.style.margin = "0 auto 16px";
      retry.style.display = "block";
      retry.addEventListener("click", function () { state.guidesError = null; loadGuides(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }

    if (!a) {
      loadGuides();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading guides mails…</p>';
      f.appendChild(wait);
      return f;
    }

    // These are real email addresses collected against a facade — the guides
    // themselves are placeholder content (see data.py), and no mail is actually
    // sent yet. Say so, the same way the sign-up list banner does.
    var note = document.createElement("div");
    note.className = "banner synthetic";
    note.innerHTML = '<span class="ico">▲</span><div><strong>Mailing list, not a delivery system.</strong> ' +
      "These are the emails people gave the free-guides landing to receive the League and Valorant guides. " +
      "No mail is sent yet and the guides are placeholder content — keep them as leads, and as personal data. " +
      "Wire a real send + unsubscribe flow before mailing them.</div>";
    f.appendChild(note);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes synthetic leads.</strong> ' +
        num(a.synthetic) + " row(s) were seeded for testing. Clear the store before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Guides mails (all time)", num(a.total), undefined, "", true));
    kr.appendChild(kpi("In this period", num(a.in_window)));
    kr.appendChild(kpi("Last 24 hours", num(a.last_24h)));
    kr.appendChild(kpi("Last 7 days", num(a.last_7d)));
    // How many also ticked the monthly-newsletter opt-in.
    kr.appendChild(kpi("Opted into monthly mail", num(a.optins)));
    // Emails are unique by construction (guides.py dedupes on ingest); surface a
    // repeat only if one ever slips through — it would mean uniqueness broke.
    if (a.repeat > 0) kr.appendChild(kpi("Duplicate emails ⚠", num(a.repeat)));
    f.appendChild(kr);

    var g = document.createElement("div");
    g.className = "grid";

    // Mails per day across the window.
    var series = a.series || [];
    g.appendChild(card({
      cls: "half", title: "Guides mails per day",
      sub: "New submissions in the selected period, one bar per day.",
      chart: function (w) {
        return columns(w, {
          rows: series.map(function (r) { return { label: shortDate(r.date), value: r.count }; }),
          color: SERIES[0], alt: "Guides mails per day", valueName: "Mails", xTall: series.length > 20
        });
      },
      table: {
        head: ["Day", "Mails"], num: [1],
        rows: series.map(function (r) { return [r.date, num(r.count)]; })
      }
    }));

    // Which guide they asked for — a lead can pick both, so picks need not sum to
    // the lead total.
    var guides = a.guides || [];
    g.appendChild(card({
      cls: "half", title: "Which guide they wanted",
      sub: "Counts picks, not leads — most people take both.",
      chart: function (w) {
        return barsH(w, {
          rows: guides.map(function (r) { return { label: guideLabel(r.key), value: r.count }; }),
          color: SERIES[1], alt: "Guides requested"
        });
      },
      table: {
        head: ["Guide", "Requests"], num: [1],
        rows: guides.map(function (r) { return [guideLabel(r.key), num(r.count)]; })
      }
    }));
    f.appendChild(g);

    // Country split — same resolution the sessions use (edge / timezone / locale).
    var countries = a.countries || [];
    var g2 = document.createElement("div");
    g2.className = "grid";
    g2.appendChild(card({
      cls: "half", title: "Where they signed up",
      sub: "Country is resolved server-side, never from an IP — see how each was inferred in the table.",
      chart: function (w) {
        return barsH(w, {
          rows: countries.slice(0, 10).map(function (c) {
            return { label: (flag(c.code) + " " + countryName(c.code)).trim(), value: c.count };
          }),
          color: SERIES[2], alt: "Guides mails by country"
        });
      },
      table: {
        head: ["Country", "Mails"], num: [1],
        rows: countries.map(function (c) { return [countryName(c.code), num(c.count)]; })
      }
    }));
    f.appendChild(g2);

    // The list itself.
    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Guides mails</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-guides>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > recent.length ? ", most recent " + num(recent.length) + " of " + num(a.total) : "") +
      ". Email, guides picked and opt-in only.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No guides mails yet. Open /guides.html, submit an email, and hit Refresh.</p>');
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Email", "Guides", "Monthly", "Country"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>";
    recent.forEach(function (r) {
      var picks = (r.guides || "").split(",").filter(Boolean).map(guideLabel).join(", ");
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.ts)) + "</td>" +
        "<td>" + esc(r.email) + (r.syn ? ' <span class="chip">synthetic</span>' : "") + "</td>" +
        "<td>" + esc(picks || "—") + "</td>" +
        "<td>" + (r.optin ? "Yes" : '<span class="dim">No</span>') + "</td>" +
        "<td>" + countryCell(r.co, r.cosrc) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-guides]").addEventListener("click", function () {
      var cols = ["signed_up", "email", "guides", "monthly_optin", "country_code", "country", "country_source", "synthetic"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        var picks = (r.guides || "").split(",").filter(Boolean).map(guideLabel).join(" & ");
        lines.push([new Date(r.ts * 1000).toISOString(), r.email, picks, r.optin ? "yes" : "no",
                    r.co, countryName(r.co), r.cosrc, r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "esb-guides-mails-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  /* ── Boosters: the roster store, read-only ───────────────────────────── */
  function loadBoosters() {
    if (state.boostersLoading) return;
    state.boostersLoading = true;
    state.boostersError = null;
    api({ action: "boosters", token: state.token, days: state.days }).then(function (res) {
      state.boostersLoading = false;
      if (res.status === 200 && res.body.boosters) {
        state.boosters = res.body.boosters;
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        state.boostersError = "This server doesn't serve the roster store yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.boostersError = "Couldn't load the roster — the server returned " + res.status + ".";
      }
      if (state.tab === "boosters") render();
    }).catch(function () {
      state.boostersLoading = false;
      state.boostersError = "Couldn't reach the server. Is it running?";
      if (state.tab === "boosters") render();
    });
  }

  function panelBoosters() {
    var f = document.createDocumentFragment();
    var a = state.boosters;

    if (state.boostersError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.boostersError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm";
      retry.type = "button";
      retry.textContent = "Try again";
      retry.style.margin = "0 auto 16px";
      retry.style.display = "block";
      retry.addEventListener("click", function () { state.boostersError = null; loadBoosters(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }

    if (!a) {
      loadBoosters();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading roster…</p>';
      f.appendChild(wait);
      return f;
    }

    // Placeholder banner — the roster is invented (see data.py) and the store is
    // filled by tools/seed_boosters.py. Say so, like the synthetic-data banner.
    var note = document.createElement("div");
    note.className = "banner synthetic";
    note.innerHTML = '<span class="ico">▲</span><div><strong>Roster store, not a hiring system.</strong> ' +
      "This is the backend behind the boosters page, the “On shift now” rail and the delivered feed. " +
      "The rows are placeholder boosters — there is no application or payout flow yet. " +
      "Wire it to the real roster and clear the store before launch.</div>";
    f.appendChild(note);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes seeded boosters.</strong> ' +
        num(a.synthetic) + " row(s) were written by tools/seed_boosters.py for testing. Clear the store before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("On the board", num(a.total), undefined, "", true));
    kr.appendChild(kpi("Free now", num(a.free)));
    kr.appendChild(kpi("Busy", num(a.busy)));
    kr.appendChild(kpi("Games covered", num((a.games || []).length)));
    f.appendChild(kr);

    // Per-game split — how many boosters cover each ladder, and how many are free.
    var games = a.games || [];
    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(card({
      cls: "half", title: "Boosters per game",
      sub: "How many cover each ladder on the board right now.",
      chart: function (w) {
        return barsH(w, {
          rows: games.map(function (r) { return { label: r.game, value: r.count }; }),
          color: SERIES[0], alt: "Boosters per game"
        });
      },
      table: {
        head: ["Game", "Boosters", "Free now"], num: [1, 2],
        rows: games.map(function (r) { return [r.game, num(r.count), num(r.free)]; })
      }
    }));
    g.appendChild(card({
      cls: "half", title: "Availability",
      sub: "Free vs busy across the whole board.",
      chart: function (w) {
        return barsH(w, {
          rows: [{ label: "Free now", value: a.free }, { label: "Busy", value: a.busy }],
          color: SERIES[2], alt: "Availability split"
        });
      },
      table: {
        head: ["State", "Boosters"], num: [1],
        rows: [["Free now", num(a.free)], ["Busy", num(a.busy)]]
      }
    }));
    f.appendChild(g);

    // The roster itself.
    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Roster</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-boosters>Export CSV</button></div>' +
      '<p class="card-sub">Sorted by win rate' +
      (a.total > recent.length ? ", first " + num(recent.length) + " of " + num(a.total) : "") +
      ".</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">Store is empty. Run <code>python3 site/tools/seed_boosters.py --clear</code>, then Refresh.</p>');
      f.appendChild(el);
      return f;
    }

    var head = ["Handle", "Game", "Region", "Peak", "Win rate", "Orders", "Queue"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        "<td>" + esc(r.handle) + (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + esc(r.game) + "</td>" +
        '<td class="dim">' + esc(r.region || "—") + "</td>" +
        "<td>" + esc(r.peak || "—") + "</td>" +
        "<td>" + esc(r.wr) + "</td>" +
        '<td class="num">' + num(r.orders) + "</td>" +
        "<td>" + (r.free ? '<span class="chip">free</span>' : esc(r.queue || "—")) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-boosters]").addEventListener("click", function () {
      var cols = ["handle", "game", "region", "peak", "win_rate", "win_rate_n", "orders", "queue", "free", "seeded"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([r.handle, r.game, r.region, r.peak, r.wr, r.wr_n, r.orders, r.queue, r.free ? "yes" : "no", r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "esb-boosters-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  /* ── Orders — the fulfilment/receipt store ────────────────────────────────
     A master-detail tab: a list of every order, and clicking an order id opens
     its full configuration — game, climb, booster, add-ons, region, country,
     currency, price breakdown. Its own store (src/orders.py), fetched on demand
     like Accounts because it holds PII. Detail is a second on-click request, the
     same pattern Sessions uses, so the list payload never carries every order's
     full record. */
  // CAD is "C$", never a bare "$" — an operator scanning this list has no other
  // way to tell a 415 Canadian order from a 415 US one, and the fallback below
  // is a dollar sign, so a currency missing from this map is silently mislabelled
  // rather than obviously broken. Mirrored in payments.CURRENCY_SIGNS, i18n.js
  // CUR_MARK and build.py's CURRENCIES icon; test_pricing.py asserts all four.
  var CUR_SYM = { usd: "$", eur: "€", gbp: "£", cad: "C$" };
  function money(n, cur) {
    var sym = CUR_SYM[(cur || "usd").toLowerCase()] || "$";
    return sym + fmtNum.format(Math.round(n || 0));
  }
  var STATUS_LABEL = {
    paid: "Paid", assigned: "Assigned", in_progress: "In progress",
    delivered: "Delivered", unclaimed: "Unclaimed", refunded: "Refunded"
  };
  function statusChip(s) {
    return '<span class="ostat ostat-' + esc(s) + '">' + esc(STATUS_LABEL[s] || s) + "</span>";
  }
  var SERVICE_LABEL = {
    division: "Rank boost", wins: "Net wins", placements: "Placements", coaching: "Coaching"
  };

  function loadOrders() {
    if (state.ordersLoading) return;
    state.ordersLoading = true;
    state.ordersError = null;
    api({ action: "orders", token: state.token, days: state.days }).then(function (res) {
      state.ordersLoading = false;
      if (res.status === 200 && res.body.orders) {
        state.orders = res.body.orders;
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        state.ordersError = "This server doesn't serve the orders store yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.ordersError = "Couldn't load orders — the server returned " + res.status + ".";
      }
      if (state.tab === "orders") render();
    }).catch(function () {
      state.ordersLoading = false;
      state.ordersError = "Couldn't reach the server. Is it running?";
      if (state.tab === "orders") render();
    });
  }

  function openOrder(id) {
    state.orderId = id;
    state.orderDetail = null;
    render();
    api({ action: "order", token: state.token, order_id: id }).then(function (res) {
      if (res.status === 200) {
        state.orderDetail = res.body.order;
      } else {
        state.orderId = null;
      }
      render();
    }).catch(function () {
      state.orderId = null;
      render();
    });
  }

  function panelOrders() {
    if (state.orderId) return panelOrderDetail();

    var f = document.createDocumentFragment();
    var a = state.orders;

    if (state.ordersError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.ordersError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm"; retry.type = "button"; retry.textContent = "Try again";
      retry.style.cssText = "margin:0 auto 16px;display:block";
      retry.addEventListener("click", function () { state.ordersError = null; loadOrders(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }
    if (!a) {
      loadOrders();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading orders…</p>';
      f.appendChild(wait);
      return f;
    }

    // Placeholder banner — the seeded orders are invented (see data.py). Only real
    // Stripe fulfilments should be read as real, and those are unseeded rows.
    if (a.synthetic > 0) {
      var note = document.createElement("div");
      note.className = "banner synthetic";
      note.innerHTML = '<span class="ico">▲</span><div><strong>Includes placeholder orders.</strong> ' +
        num(a.synthetic) + " of " + num(a.total) + " orders here were written by " +
        "<code>site/tools/seed_orders.py</code> for the preview — invented configurations about " +
        "invented boosters. Real orders arrive through the Stripe webhook. Clear the store before launch.</div>";
      f.appendChild(note);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Orders", num(a.total), undefined, "", true));
    kr.appendChild(kpi("Revenue", usd(a.revenue)));
    kr.appendChild(kpi("Avg order", usd(a.aov)));
    kr.appendChild(kpi("Refunded", num(a.refunded)));
    kr.appendChild(kpi("Games", num((a.games || []).length)));
    f.appendChild(kr);

    var statuses = (a.statuses || []).filter(function (s) { return s.count > 0; });
    var games = a.games || [];
    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(card({
      cls: "half", title: "By status",
      sub: "Where every order in this window sits in the lifecycle.",
      chart: function (w) {
        return barsH(w, {
          rows: statuses.map(function (s) { return { label: STATUS_LABEL[s.status] || s.status, value: s.count }; }),
          color: SERIES[0], alt: "Orders by status"
        });
      },
      table: {
        head: ["Status", "Orders"], num: [1],
        rows: statuses.map(function (s) { return [STATUS_LABEL[s.status] || s.status, num(s.count)]; })
      }
    }));
    g.appendChild(card({
      cls: "half", title: "Revenue by game",
      sub: "Which ladders the money came from (refunds excluded).",
      chart: function (w) {
        return barsH(w, {
          rows: games.map(function (r) { return { label: r.game, value: r.revenue }; }),
          color: SERIES[2], alt: "Revenue by game", fmt: function (n) { return usd(n); }
        });
      },
      table: {
        head: ["Game", "Orders", "Revenue"], num: [1, 2],
        rows: games.map(function (r) { return [r.game, num(r.count), usd(r.revenue)]; })
      }
    }));
    f.appendChild(g);

    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every order</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-orders>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > recent.length ? ", first " + num(recent.length) + " of " + num(a.total) : "") +
      ". Click an order id to see the full configuration — the climb, add-ons, booster, region and price.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No orders in this period. Run <code>python3 site/tools/seed_orders.py --clear</code>, then Refresh.</p>');
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Order", "Game", "Product", "Config", "Booster", "Region", "Country", "Status", "Total"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) { return '<th class="' + (i === 9 ? "num" : "") + '">' + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.at)) + "</td>" +
        '<td><button class="link-btn" type="button" data-order="' + esc(r.order_id) + '">' + esc(r.order_id) + "</button>" +
          (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + esc(r.game) + "</td>" +
        "<td>" + esc(SERVICE_LABEL[r.service] || r.service) + '<span class="dim"> · ' + esc(r.mode || "") + "</span></td>" +
        '<td class="wrap-cell">' + esc(r.summary) + "</td>" +
        "<td>" + (r.booster ? esc(r.booster) : '<span class="dim">unassigned</span>') + "</td>" +
        '<td class="dim">' + esc(r.region || "—") + "</td>" +
        "<td>" + countryCell(r.country) + "</td>" +
        "<td>" + statusChip(r.status) + "</td>" +
        '<td class="num">' + esc(money(r.total, r.currency)) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.addEventListener("click", function (e) {
      var b = e.target.closest("[data-order]");
      if (b) openOrder(b.getAttribute("data-order"));
    });

    el.querySelector("[data-export-orders]").addEventListener("click", function () {
      var cols = ["when", "order_id", "game", "service", "mode", "config", "booster",
                  "region", "country", "currency", "status", "total", "seeded"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([new Date(r.at * 1000).toISOString(), r.order_id, r.game, r.service, r.mode,
                    r.summary, r.booster, r.region, r.country, r.currency, r.status, r.total,
                    r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(","));
      });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      link.download = "esb-orders-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  function panelOrderDetail() {
    var f = document.createDocumentFragment();

    var back = document.createElement("button");
    back.className = "btn btn-sm back-btn"; back.type = "button";
    back.textContent = "← All orders";
    back.addEventListener("click", function () {
      state.orderId = null; state.orderDetail = null; render();
    });
    f.appendChild(back);

    var o = state.orderDetail;
    if (!o) {
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading order…</p>';
      f.appendChild(wait);
      return f;
    }

    // Hero — the order id, the product line, and the status, big.
    var hero = document.createElement("div");
    hero.className = "card order-hero";
    hero.innerHTML =
      '<div class="order-hero-top">' +
        '<div><div class="order-id">' + esc(o.order_id) + (o.syn ? ' <span class="chip">seeded</span>' : "") + "</div>" +
          '<div class="order-line">' + esc(o.game) + ' · <b>' + esc(o.summary) + "</b></div></div>" +
        '<div class="order-hero-r">' + statusChip(o.status) +
          '<div class="order-total">' + esc(money(o.total, o.currency)) +
          ' <span class="order-cur">' + esc((o.currency || "usd").toUpperCase()) + "</span></div></div>" +
      "</div>";
    f.appendChild(hero);

    // The boost — everything about what was ordered.
    var boost = document.createElement("div");
    boost.className = "card";
    boost.innerHTML = '<div class="card-hd"><h3>The boost</h3></div>';
    var bf = [
      ["Game", o.game],
      ["Product", SERVICE_LABEL[o.service] || o.service],
      ["Queue", o.mode]
    ];
    if (o.service === "division") {
      bf.push(["From rank", o.from_rank]);
      bf.push(["To rank", o.to_rank]);
    } else if (o.service === "wins" || o.service === "placements") {
      bf.push([o.unranked ? "Starting" : "Current rank", o.unranked ? "Unranked" : o.from_rank]);
      bf.push([o.service === "wins" ? "Net wins" : "Placement games", String(o.units || "—")]);
    } else if (o.service === "coaching") {
      bf.push(["Coach", o.coach || "—"]);
      bf.push(["Hours", String(o.hours || "—")]);
    }
    bf.push(["Region", o.region || "—"]);
    bf.push(["Rank system", o.rankUnit]);
    bf.push(["Booster", o.booster || "Unassigned"]);
    bf.push(["ETA quoted", o.eta || "—"]);
    boost.insertAdjacentHTML("beforeend",
      '<div class="facts">' + bf.map(function (r) { return fact(r[0], r[1]); }).join("") + "</div>");
    f.appendChild(boost);

    // Options / add-ons — the chosen extras, each with its cost on this order.
    var opt = document.createElement("div");
    opt.className = "card";
    opt.innerHTML = '<div class="card-hd"><h3>Options chosen</h3></div>';
    if (!o.addons || !o.addons.length) {
      opt.insertAdjacentHTML("beforeend", '<p class="empty">No add-ons on this order.</p>');
    } else {
      var oh = '<div class="scroll-x"><table class="tbl"><thead><tr><th>Add-on</th><th class="num">Uplift</th><th class="num">Cost on this order</th></tr></thead><tbody>';
      o.addons.forEach(function (ad) {
        oh += "<tr><td>" + esc(ad.label) + "</td>" +
          '<td class="num">' + (ad.pct ? "+" + Math.round(ad.pct * 100) + "%" : "included") + "</td>" +
          '<td class="num">' + (ad.cost == null ? "—" : (ad.cost === 0 ? "included" : usd(ad.cost))) + "</td></tr>";
      });
      opt.insertAdjacentHTML("beforeend", oh + "</tbody></table></div>");
    }
    f.appendChild(opt);

    // Price — the receipt, adds up: subtotal − discount = total.
    var price = document.createElement("div");
    price.className = "card";
    price.innerHTML = '<div class="card-hd"><h3>Payment</h3></div>';
    var pr = '<table class="tbl receipt"><tbody>';
    pr += '<tr><td>Subtotal</td><td class="num">' + esc(money(o.subtotal, o.currency)) + "</td></tr>";
    if (o.discount) {
      pr += '<tr><td>Discount' + (o.promo ? ' <span class="chip">' + esc(o.promo) + "</span>" : "") +
        '</td><td class="num">−' + esc(money(o.discount, o.currency)) + "</td></tr>";
    }
    pr += '<tr class="receipt-total"><td>Total charged</td><td class="num">' +
      esc(money(o.total, o.currency)) + " " + esc((o.currency || "usd").toUpperCase()) + "</td></tr>";
    price.insertAdjacentHTML("beforeend", pr + "</tbody></table>");
    f.appendChild(price);

    // Customer & provenance — the PII and where the order came from.
    var cust = document.createElement("div");
    cust.className = "card";
    cust.innerHTML = '<div class="card-hd"><h3>Customer & provenance</h3></div>' +
      '<div class="facts">' +
        fact("Email", o.email || "—") +
        '<div class="fact"><span class="fact-l">Country</span><span class="fact-v">' +
          countryCell(o.country, o.cosrc) + "</span></div>" +
        fact("Placed", ago(o.at) + " · " + new Date(o.at * 1000).toLocaleString()) +
        fact("Order id", o.order_id) +
      "</div>" +
      (o.notes ? '<p class="card-sub" style="margin-top:14px"><b>Notes:</b> ' + esc(o.notes) + "</p>" : "");
    f.appendChild(cust);

    return f;
  }

  /* ── Carts: the abandoned-checkout store, recoverable emails ──────────── */
  var CART_STATUS = {
    pending: "Waiting", mailed: "Mailed", recovered: "Recovered", expired: "Closed"
  };
  function cartChip(s) {
    return '<span class="ostat ostat-' + esc(s) + '">' + esc(CART_STATUS[s] || s) + "</span>";
  }

  function loadCarts() {
    if (state.cartsLoading) return;
    state.cartsLoading = true;
    state.cartsError = null;
    api({ action: "carts", token: state.token, days: state.days }).then(function (res) {
      state.cartsLoading = false;
      if (res.status === 200 && res.body.carts) {
        state.carts = res.body.carts;
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        state.cartsError = "This server doesn't serve the carts store yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.cartsError = "Couldn't load carts — the server returned " + res.status + ".";
      }
      if (state.tab === "carts") render();
    }).catch(function () {
      state.cartsLoading = false;
      state.cartsError = "Couldn't reach the server. Is it running?";
      if (state.tab === "carts") render();
    });
  }

  function panelCarts() {
    var f = document.createDocumentFragment();
    var a = state.carts;

    if (state.cartsError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.cartsError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm"; retry.type = "button"; retry.textContent = "Try again";
      retry.style.cssText = "margin:0 auto 16px;display:block";
      retry.addEventListener("click", function () { state.cartsError = null; loadCarts(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }
    if (!a) {
      loadCarts();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading carts…</p>';
      f.appendChild(wait);
      return f;
    }

    // What this tab is — and what it is not. A standing note, the same honesty
    // the other PII stores carry: this is a recovery list, not proof of intent
    // to buy, and its emails were typed into checkout or supplied by a session.
    var intro = document.createElement("div");
    intro.className = "banner";
    intro.innerHTML = '<span class="ico">✉</span><div><strong>Abandoned-checkout recovery.</strong> ' +
      "An email lands here when a signed-in visitor configures an order, or when anyone types their " +
      "address on checkout, and then doesn't pay. After " + num(a.delay_mins) + " minutes the sweep mails " +
      "a single-use " + Math.round(a.recovery_pct * 100) + "% code. A paid order burns the code and marks the row " +
      "<em>Recovered</em>. This is the “Carts” store — distinct from the anonymous <b>Abandoned</b> tab, which has no email.</div>";
    f.appendChild(intro);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes seeded carts.</strong> ' +
        num(a.synthetic) + " row(s) were written for testing. Clear the store before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Captured", num(a.total), undefined, "", true));
    kr.appendChild(kpi("Recovered", num(a.recovered)));
    kr.appendChild(kpi("Recovery rate", a.recovery_rate + "%"));
    kr.appendChild(kpi("Won back", usd(a.recovered_value)));
    kr.appendChild(kpi("In flight", usd(a.potential_value)));
    f.appendChild(kr);

    var statuses = (a.statuses || []).filter(function (s) { return s.count > 0; });
    var games = a.games || [];
    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(card({
      cls: "half", title: "By status",
      sub: "Waiting → Mailed → Recovered. Closed is unsubscribed or an expired token.",
      chart: function (w) {
        return barsH(w, {
          rows: statuses.map(function (s) { return { label: CART_STATUS[s.status] || s.status, value: s.count }; }),
          color: SERIES[0], alt: "Carts by status"
        });
      },
      table: {
        head: ["Status", "Carts"], num: [1],
        rows: statuses.map(function (s) { return [CART_STATUS[s.status] || s.status, num(s.count)]; })
      }
    }));
    g.appendChild(card({
      cls: "half", title: "By game",
      sub: "Which ladders visitors abandon, and how many came back.",
      chart: function (w) {
        return barsH(w, {
          rows: games.map(function (r) { return { label: r.game, value: r.count }; }),
          color: SERIES[2], alt: "Carts by game"
        });
      },
      table: {
        head: ["Game", "Carts", "Recovered"], num: [1, 2],
        rows: games.map(function (r) { return [r.game, num(r.count), num(r.recovered)]; })
      }
    }));
    f.appendChild(g);

    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every cart</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-carts>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > recent.length ? ", first " + num(recent.length) + " of " + num(a.total) : "") +
      ". The value is re-priced from each stored configuration; the offer is what the " +
      Math.round(a.recovery_pct * 100) + "% code brings it to.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No captured carts in this period. They appear once a visitor configures while ' +
        "signed in, or types an email on checkout without finishing.</p>");
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Email", "Game", "Config", "Value", "Offer", "Status", "Age"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) { return '<th class="' + (i === 4 || i === 5 ? "num" : "") + '">' + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.at)) + "</td>" +
        "<td>" + esc(r.email) + (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + esc(r.game) + '<span class="dim"> · ' + esc(r.mode || "") + "</span></td>" +
        '<td class="wrap-cell">' + esc(r.summary) + "</td>" +
        '<td class="num">' + esc(usd(r.value)) + "</td>" +
        '<td class="num">' + (r.offer ? esc(usd(r.offer)) : '<span class="dim">—</span>') + "</td>" +
        "<td>" + cartChip(r.status) +
          (r.order_id ? ' <span class="dim">' + esc(r.order_id) + "</span>" : "") + "</td>" +
        '<td class="dim">' + esc(r.status === "mailed" && r.mailed_at ? "mailed " + ago(r.mailed_at) : ago(r.at)) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-carts]").addEventListener("click", function () {
      var cols = ["when", "email", "game", "service", "mode", "config", "region", "country",
                  "value_usd", "offer_usd", "status", "order_id", "mailed_at", "recovered_at", "seeded"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([new Date(r.at * 1000).toISOString(), r.email, r.game, r.service, r.mode,
                    r.summary, r.region, r.country, r.value, r.offer, r.status, r.order_id,
                    r.mailed_at ? new Date(r.mailed_at * 1000).toISOString() : "",
                    r.recovered_at ? new Date(r.recovered_at * 1000).toISOString() : "",
                    r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(","));
      });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      link.download = "esb-carts-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  function panelAbandoned(d) {
    var rows = d.abandoned;
    var f = document.createDocumentFragment();

    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Abandoned configurations</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export>Export CSV</button></div>' +
      '<p class="card-sub">Every session that configured an order and did not pay, most valuable first. ' +
      "These are anonymous — there is no email here unless the customer reached Stripe, by design.</p>";

    el.appendChild(plainTable(
      ["When", "Value", "Game", "Order", "Mode", "Region", "Add-ons", "Left at", "Re-quotes", "Source", "Device"],
      rows.map(function (r) {
        var order = r.service === "division" ? (r.from + " → " + r.to)
                  : (r.service === "wins" ? "net wins from " + r.from
                                          : "placements from " + r.from);
        return [ago(r.at), usd(r.value), r.game, order, r.mode, r.region || "—",
                r.addons.length ? r.addons.join(", ") : "—", r.step, num(r.requotes),
                r.source, r.device];
      }), [1, 8]));

    el.querySelector("[data-export]").addEventListener("click", function () {
      var head = ["at", "value_usd", "game", "service", "from", "to", "mode", "region",
                  "addons", "left_at", "requotes", "source", "country", "device", "returning"];
      var lines = [head.join(",")];
      rows.forEach(function (r) {
        lines.push([new Date(r.at * 1000).toISOString(), r.value, r.game, r.service, r.from,
                    r.to, r.mode, r.region, r.addons.join(" | "), r.step, r.requotes,
                    r.source, r.country, r.device, r.returning ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "esb-abandoned-" + new Date().toISOString().slice(0, 10) + ".csv";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  /* ── Live view: the Shopify-style "right now" panel ────────────────────────
     Every figure is recomputed server-side each poll (insights._mod_liveview)
     over its own short windows, so this panel is always "now" regardless of the
     period selector, and the 10s auto-refresh keeps it moving. Rendered as
     markup rather than measured charts so it survives a full re-render on every
     tick with no painter pass. */
  function lvRankList(rows, opts) {
    if (!rows || !rows.length) {
      return '<p class="lv-empty">Nothing in the last ' + opts.mins + " minutes.</p>";
    }
    var mx = rows.reduce(function (m, r) { return Math.max(m, opts.val(r)); }, 1);
    return '<ul class="lv-rank">' + rows.map(function (r) {
      var v = opts.val(r);
      return "<li>" +
        '<span class="lv-rank-l">' + opts.label(r) + "</span>" +
        '<span class="lv-rank-bar"><i style="width:' + Math.round((v / mx) * 100) + '%"></i></span>' +
        '<span class="lv-rank-v">' + num(v) + "</span></li>";
    }).join("") + "</ul>";
  }

  /* ── world map (self-contained SVG, no external tiles) ─────────────────────
     A dotted equirectangular map: dim dots trace the continents (rough boxes,
     enough to read as a world map), bright dots mark where live visitors are,
     sized by session count. Projection: x = lng + 180, y = 90 − lat, on a
     360×180 viewBox. The land layer never changes, so it is built once. */
  var LV_LAND = [
    [48, 72, -141, -55], [30, 49, -125, -66], [15, 30, -110, -88], [60, 83, -55, -18],
    [-5, 12, -80, -50], [-35, -5, -75, -40], [-55, -35, -75, -58],
    [36, 60, -10, 30], [60, 71, 4, 31],
    [18, 37, -16, 34], [-8, 18, -16, 48], [-35, -8, 10, 40],
    [12, 42, 34, 60], [20, 55, 60, 120], [42, 62, 60, 140], [55, 73, 60, 180],
    [8, 30, 68, 90], [5, 25, 95, 122],
    [-38, -12, 113, 153], [31, 45, 130, 146], [50, 59, -8, 2]
  ];
  function lvIsLand(lat, lng) {
    for (var i = 0; i < LV_LAND.length; i++) {
      var b = LV_LAND[i];
      if (lat >= b[0] && lat <= b[1] && lng >= b[2] && lng <= b[3]) return true;
    }
    return false;
  }
  var LV_CENTROID = {
    US: [38, -97], CA: [56, -106], MX: [23, -102], BR: [-10, -52], AR: [-38, -63],
    CL: [-33, -71], CO: [4, -73], PE: [-10, -76], VE: [8, -66],
    GB: [54, -2], IE: [53, -8], FR: [46, 2], DE: [51, 10], ES: [40, -4], PT: [39, -8],
    IT: [42, 12], NL: [52, 5], BE: [50, 4], CH: [47, 8], AT: [47, 14],
    SE: [62, 15], NO: [62, 10], FI: [64, 26], DK: [56, 9], PL: [52, 19], CZ: [49, 15],
    GR: [39, 22], RO: [46, 25], UA: [49, 32], RU: [61, 90], TR: [39, 35],
    IL: [31, 35], AE: [24, 54], SA: [24, 45], EG: [26, 30], MA: [32, -6], NG: [9, 8],
    ZA: [-29, 24], KE: [0, 38], IN: [22, 78], PK: [30, 70], BD: [24, 90], CN: [35, 105],
    JP: [36, 138], KR: [36, 128], TH: [15, 101], VN: [16, 106], MY: [4, 102],
    SG: [1, 104], ID: [-2, 118], PH: [13, 122], AU: [-25, 133], NZ: [-42, 172]
  };
  var lvMapBase = null;
  function lvLandLayer() {
    if (lvMapBase != null) return lvMapBase;
    var s = "";
    for (var y = 3; y < 180; y += 4.5) {
      for (var x = 3; x < 360; x += 4.5) {
        if (lvIsLand(90 - y, x - 180)) {
          s += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) +
            '" r="0.85" class="lv-map-land"/>';
        }
      }
    }
    lvMapBase = s;
    return s;
  }
  function lvWorldMap(locations) {
    var rows = (locations || []).filter(function (r) { return LV_CENTROID[r.code]; });
    var mx = rows.reduce(function (m, r) { return Math.max(m, r.sessions); }, 1);
    var pts = rows.map(function (r) {
      var c = LV_CENTROID[r.code];
      var x = (c[1] + 180).toFixed(1), y = (90 - c[0]).toFixed(1);
      var rr = 2 + Math.sqrt(r.sessions / mx) * 4.5;
      return '<circle cx="' + x + '" cy="' + y + '" r="' + (rr + 3).toFixed(1) + '" class="lv-map-halo"/>' +
        '<circle cx="' + x + '" cy="' + y + '" r="' + rr.toFixed(1) + '" class="lv-map-hit">' +
        "<title>" + esc(countryName(r.code) + ": " + num(r.sessions)) + "</title></circle>";
    }).join("");
    return '<svg class="lv-map-svg" viewBox="0 0 360 180" preserveAspectRatio="xMidYMid meet" ' +
      'role="img" aria-label="Live visitors by country">' + lvLandLayer() + pts + "</svg>";
  }

  function panelLiveView(d) {
    var lv = d.liveview || {};
    var mins = lv.window_mins || 30;
    var f = document.createDocumentFragment();
    var root = document.createElement("div");
    root.className = "lv";

    /* visitors-now hero + per-minute sparkline */
    var spark = lv.spark || [];
    var smax = spark.reduce(function (m, n) { return Math.max(m, n); }, 1);
    var bars = spark.map(function (n, i) {
      var h = n ? Math.max(8, Math.round((n / smax) * 100)) : 0;
      var mAgo = (lv.spark_minutes || spark.length) - 1 - i;
      var when = mAgo === 0 ? "this minute" : mAgo + " min ago";
      return '<span class="lv-bar' + (i === spark.length - 1 ? " is-now" : "") +
        '" style="height:' + h + '%" title="' +
        esc(num(n) + (n === 1 ? " visitor · " : " visitors · ") + when) + '"></span>';
    }).join("");
    var vnow = lv.visitors || 0;

    /* product view — live sessions grouped by game, split by how far they got.
       This site has no cart, so a per-game stage breakdown replaces the cart
       funnel. A session is attributed by its order or the /games/<slug> page. */
    var STAGES = [
      { key: "browsing",    label: "Browsing" },
      { key: "configuring", label: "Configuring" },
      { key: "checkout",    label: "Checking out" },
      { key: "purchased",   label: "Purchased" }
    ];
    var prod = lv.products || [];
    var games = prod.length ? prod.map(function (r) {
      var tot = r.sessions || 1;
      var segs = STAGES.map(function (st) {
        var n = r[st.key] || 0;
        if (!n) return "";
        return '<i class="lv-seg lv-seg-' + st.key + '" style="width:' +
          (n / tot * 100) + '%" title="' + esc(num(n) + " " + st.label.toLowerCase()) + '"></i>';
      }).join("");
      var counts = STAGES.filter(function (st) { return r[st.key]; }).map(function (st) {
        return '<span class="lv-gc"><i class="lv-dot-' + st.key + '"></i>' +
          num(r[st.key]) + " " + esc(st.label) + "</span>";
      }).join("");
      return '<div class="lv-game">' +
        '<div class="lv-game-top"><span class="lv-game-name">' + esc(r.name) + "</span>" +
          '<span class="lv-game-n">' + num(r.sessions) +
          " session" + (r.sessions === 1 ? "" : "s") + "</span></div>" +
        '<div class="lv-game-bar">' + segs + "</div>" +
        '<div class="lv-game-counts">' + counts + "</div></div>";
    }).join("") : '<p class="lv-empty">No live sessions on any game in the last ' +
      mins + " minutes.</p>";

    /* customers first vs returning */
    var c = lv.customers || { first: 0, returning: 0 };
    var ctot = (c.first + c.returning) || 1;

    /* activity feed — reuse the shared recent-events stream */
    var feed = (d.live || []).slice(0, 14).map(function (r) {
      var bits = [r.game, r.summary].filter(Boolean).join(" · ");
      var val = r.value ? '<span class="lv-feed-val">' + usd(r.value) + "</span>" : "";
      var fl = r.country ? '<span class="lv-feed-flag" title="' + esc(countryName(r.country)) +
        '">' + flag(r.country) + "</span>" : "";
      return '<li class="lv-feed-row lv-ev-' + esc(r.e) + '">' +
        '<span class="lv-feed-dot"></span>' +
        '<span class="lv-feed-when">' + esc(ago(r.t)) + "</span>" +
        '<span class="lv-feed-what">' + esc(r.label) +
          (bits ? ' <span class="lv-feed-cfg">' + esc(bits) + "</span>" : "") + "</span>" +
        val + fl + "</li>";
    }).join("");
    var t = lv.today || { sessions: 0, orders: 0, revenue: 0, cr: 0 };

    /* funnel boxes — what every live session is doing right now (site-wide) */
    var beh = lv.behavior || [];
    var stages = beh.map(function (b) {
      return '<div class="lv-stage lv-stage-' + esc(b.key) + '">' +
        '<span class="lv-stage-n">' + num(b.count) + "</span>" +
        '<span class="lv-stage-l">' + esc(b.label) + "</span></div>";
    }).join('<span class="lv-stage-sep" aria-hidden="true"></span>');

    /* map legend — top countries as flag chips */
    var legend = (lv.locations || []).slice(0, 6).map(function (r) {
      return '<span class="lv-legend-item"><span class="lv-flag">' + flag(r.code) + "</span>" +
        esc(countryName(r.code) || r.code) + " <b>" + num(r.sessions) + "</b></span>";
    }).join("");

    root.innerHTML =
      '<div class="lv-behavior">' + (stages ||
        '<p class="lv-empty">No live sessions in the last ' + mins + " minutes.</p>") + "</div>" +

      '<div class="grid lv-topgrid">' +
        '<div class="card twothirds lv-map-card"><div class="card-hd"><h3>Live traffic</h3></div>' +
          '<p class="card-sub">Where visitors on the site right now are coming from.</p>' +
          '<div class="lv-map">' + lvWorldMap(lv.locations) + "</div>" +
          (legend ? '<div class="lv-legend">' + legend + "</div>" : "") + "</div>" +
        '<div class="card third lv-hero">' +
          '<div class="lv-now">' +
            '<div class="lv-now-n">' + num(vnow) + "</div>" +
            '<div class="lv-now-l"><span class="lv-dot"></span>' +
              (vnow === 1 ? "Visitor right now" : "Visitors right now") + "</div>" +
            '<div class="lv-now-sub">Active in the last 5 minutes · ' +
              num(lv.sessions_live || 0) + " session" + ((lv.sessions_live || 0) === 1 ? "" : "s") +
              " in the last " + mins + " min</div>" +
          "</div>" +
          '<div class="lv-spark" role="img" aria-label="Visitors per minute over the last ' +
            mins + ' minutes">' +
            '<div class="lv-spark-bars">' + bars + "</div>" +
            '<div class="lv-spark-x"><span>' + mins + ' min ago</span><span>now</span></div>' +
          "</div>" +
        "</div>" +
      "</div>" +

      '<div class="kpis lv-kpis">' +
        '<div class="kpi"><div class="lab">Sessions · 24h</div><div class="val">' +
          num(t.sessions) + "</div></div>" +
        '<div class="kpi"><div class="lab">Orders · 24h</div><div class="val">' +
          num(t.orders) + "</div></div>" +
        /* Rolling 24h, so it will not match the Overview tile unless the period
           happens to be a day — the label carries the window for that reason.
           The rate is computed in insights.py, never divided here. */
        '<div class="kpi"><div class="lab">Conversion · 24h</div><div class="val">' +
          pct(t.cr) + "</div>" +
          (t.sessions ? '<div class="delta">' + num(t.orders) + " of " +
            num(t.sessions) + " session" + (t.sessions === 1 ? "" : "s") + "</div>" : "") +
        "</div>" +
        '<div class="kpi"><div class="lab">Revenue · 24h</div><div class="val">' +
          usd(t.revenue) + "</div></div>" +
      "</div>" +

      '<div class="card lv-prod-card">' +
        '<div class="card-hd"><h3>Live by game</h3></div>' +
        '<p class="card-sub">Sessions on each game in the last ' + mins +
          " minutes — including anyone still browsing a game page — split by how far along they are.</p>" +
        '<div class="lv-games">' + games + "</div>" +
      "</div>" +

      '<div class="grid">' +
        '<div class="card half"><div class="card-hd"><h3>Customers</h3></div>' +
          '<p class="card-sub">Live sessions, new vs. returning visitors.</p>' +
          '<div class="lv-split"><span class="lv-split-first" style="width:' +
            Math.round((c.first / ctot) * 100) + '%"></span>' +
          '<span class="lv-split-ret" style="width:' +
            Math.round((c.returning / ctot) * 100) + '%"></span></div>' +
          '<div class="lv-split-key">' +
            '<span><i class="lv-key-first"></i>First-time <b>' + num(c.first) + "</b></span>" +
            '<span><i class="lv-key-ret"></i>Returning <b>' + num(c.returning) + "</b></span>" +
          "</div></div>" +
        '<div class="card half lv-feed-card"><div class="card-hd"><h3>Live activity</h3></div>' +
          '<p class="card-sub">The raw stream, newest first.</p>' +
          (feed ? '<ul class="lv-feed">' + feed + "</ul>"
                : '<p class="lv-empty">No recent activity.</p>') + "</div>" +
      "</div>";

    f.appendChild(root);
    return f;
  }

  function panelLive(d) {
    var f = document.createDocumentFragment();
    var g = document.createElement("div");
    g.className = "grid";

    g.appendChild(wrapCard("Latest events",
      "The raw stream, newest first. Refreshes with the page.",
      plainTable(["When", "Event", "Page", "Game", "Configuration", "Value", "Source", "Device"],
        d.live.map(function (r) {
          return [ago(r.t), r.label, r.path || "—", r.game || "—", r.summary || "—",
                  r.value ? usd(r.value) : "—", r.source || "direct", r.device || "—"];
        }), [5])));

    if (d.stripe) {
      var s = d.stripe;
      var kr = document.createElement("div");
      kr.className = "kpis";
      kr.appendChild(kpi("Stripe revenue", usd(s.revenue), undefined, "", true));
      kr.appendChild(kpi("Paid sessions", num(s.orders)));
      kr.appendChild(kpi("Average order", usd(s.aov, true)));
      kr.appendChild(kpi("Discounts given", usd(s.discount)));
      kr.appendChild(kpi("Customers", num(s.customers)));
      kr.appendChild(kpi("Repeat customers", num(s.repeat)));
      f.appendChild(wrapCard("Straight from Stripe",
        "Independent of the beacon — if an order is here, the money moved.", kr));

      g.appendChild(wrapCard("Recent paid orders", "",
        plainTable(["When", "Order", "Amount", "Game", "Detail", "Region", "Promo"],
          s.recent.map(function (r) {
            return [ago(r.at), r.order_id || "—", usd(r.amount, true), r.game || "—",
                    r.detail || "—", r.region || "—", r.promo || "—"];
          }), [2])));
    } else {
      g.appendChild(wrapCard("Stripe",
        "No STRIPE_SECRET_KEY is configured, so paid-order data is unavailable. " +
        "The revenue figures elsewhere come from the beacon instead.",
        document.createElement("div")));
    }
    f.appendChild(g);
    return f;
  }

  /* ══════════════════════════════════════════════════════════════════════
     render
     ══════════════════════════════════════════════════════════════════════ */
  var PANELS = {
    overview: panelOverview, funnel: panelFunnel, configurator: panelConfigurator,
    journey: panelJourney, sessions: panelSessions, orders: panelOrders,
    carts: panelCarts,
    accounts: panelAccounts,
    guides: panelGuides, boosters: panelBoosters,
    acquisition: panelAcquisition, friction: panelFriction, abandoned: panelAbandoned,
    liveview: panelLiveView, live: panelLive
  };

  function render() {
    var d = state.data;
    if (!d) return;
    painters = [];

    // Store chip — one compact line in the sidebar foot (store + events held).
    var meta = document.querySelector("[data-meta]");
    if (meta) {
      meta.innerHTML =
        '<span class="dot"></span>' + esc(d.meta.store) + " store" +
        ' · <b>' + esc(num(d.meta.stored)) + "</b> events";
    }

    // Topbar reflects the section you are in.
    var title = document.querySelector("[data-tabtitle]");
    var activeTab = document.querySelector('.tabs button[data-tab="' + state.tab + '"]');
    if (title && activeTab) title.textContent = activeTab.textContent;

    var banner = document.querySelector("[data-synthetic]");
    if (d.meta.synthetic > 0) {
      banner.hidden = false;
      banner.innerHTML = '<span class="ico">▲</span><div>' + (d.meta.synthetic_excluded
        ? '<strong>' + num(d.meta.synthetic) + " seeded event(s) excluded.</strong> " +
          "They were generated by <code>site/tools/seed_analytics.py</code> and are left out of " +
          "every number below, so what you are reading is real traffic only. " +
          '<button type="button" data-syn-toggle>Include them</button> ' +
          "(for checking the dashboard renders, never for reading a rate). " +
          "Clear the store before launch."
        : '<strong>Synthetic data — not real traffic.</strong> ' +
          num(d.meta.synthetic) + " of " + num(d.meta.events) +
          " events in this window were generated by <code>site/tools/seed_analytics.py</code>, and " +
          "every number below includes them. " +
          '<button type="button" data-syn-toggle>Exclude them</button>') + "</div>";
      var syn = banner.querySelector("[data-syn-toggle]");
      if (syn) syn.addEventListener("click", function () {
        state.synthetic = !state.synthetic;
        refresh();
      });
    } else {
      banner.hidden = true;
    }

    // Game filter options — only games that actually have data.
    var sel = document.querySelector("[data-game]");
    var want = state.game;
    var opts = ['<option value="">All games</option>'];
    (d.configurator.games_available || []).forEach(function (g) {
      opts.push('<option value="' + esc(g) + '">' + esc(g) + "</option>");
    });
    sel.innerHTML = opts.join("");
    sel.value = want || "";

    var host = document.querySelector("[data-panels]");
    host.innerHTML = "";
    var frag = (PANELS[state.tab] || panelOverview)(d);
    host.appendChild(frag);
    painters.forEach(function (p) { p(); });
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { painters.forEach(function (p) { p(); }); }, 180);
  });

  /* ── the period ──────────────────────────────────────────────────────── */
  /* A preset key becomes an absolute [start, end] pair HERE, in the reader's
     own timezone, and the server is handed epochs. Resolving "today" on the
     server would mean today in UTC — the wrong day for a European operator for
     part of every evening, and the whole reason "Today" and "Yesterday" could
     not be built on the old trailing-days control. */
  function dayStart(d) { var x = new Date(d.getTime()); x.setHours(0, 0, 0, 0); return x; }
  function secs(d) { return Math.floor(d.getTime() / 1000); }

  function resolveRange(key) {
    var now = new Date(), s = dayStart(now), e = new Date(now.getTime());
    if (key === "yesterday") {
      s.setDate(s.getDate() - 1);
      e = dayStart(now); e.setSeconds(e.getSeconds() - 1);
    } else if (key === "7d")  { s.setDate(s.getDate() - 6);
    } else if (key === "30d") { s.setDate(s.getDate() - 29);
    } else if (key === "90d") { s.setDate(s.getDate() - 89);
    } else if (key === "mtd") { s.setDate(1);
    } else if (key === "lastmonth") {
      s.setDate(1); s.setMonth(s.getMonth() - 1);
      e = dayStart(now); e.setDate(1); e.setSeconds(e.getSeconds() - 1);
    } else if (key === "12m") { s.setFullYear(s.getFullYear() - 1);
    }                                     // "today" is dayStart → now, as built
    return { start: secs(s), end: secs(e) };
  }

  /* The two date fields, read as local midnight → end of that day, so a range
     the reader picked as 1–7 August is the whole of the 7th, not 00:00 of it. */
  function customRange() {
    var f = (document.querySelector("[data-date-from]") || {}).value;
    var t = (document.querySelector("[data-date-to]") || {}).value;
    if (!f || !t) return null;
    var s = new Date(f + "T00:00:00"), e = new Date(t + "T23:59:59");
    if (isNaN(s.getTime()) || isNaN(e.getTime()) || e <= s) return null;
    return { start: secs(s), end: secs(e) };
  }

  /* One place writes the period, so `days` can never drift from the pair. */
  function setRange(key, pair) {
    pair = pair || resolveRange(key);
    state.range = key;
    state.start = pair.start;
    state.end = pair.end;
    state.days = Math.max(1, Math.min(365, Math.ceil((pair.end - pair.start) / 86400)));
  }

  /* ── wiring ──────────────────────────────────────────────────────────── */
  setRange(state.range);

  var gateForm = document.querySelector("[data-gate] form");
  gateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var pw = gateForm.querySelector("input").value;
    if (pw) login(pw);
  });

  var rangeSel = document.querySelector("[data-range]");
  var dateBox = document.querySelector("[data-dates]");

  rangeSel.addEventListener("change", function () {
    var key = rangeSel.value;
    dateBox.hidden = key !== "custom";
    if (key === "custom") {
      // Seed the fields with the window already on screen, so the reader edits
      // a range instead of facing two empty boxes.
      var from = document.querySelector("[data-date-from]");
      var to = document.querySelector("[data-date-to]");
      if (!from.value) from.value = isoDate(new Date(state.start * 1000));
      if (!to.value) to.value = isoDate(new Date(state.end * 1000));
      return;                       // nothing is fetched until Apply
    }
    setRange(key);
    refresh();
  });

  function isoDate(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
           "-" + String(d.getDate()).padStart(2, "0");
  }

  document.querySelector("[data-date-apply]").addEventListener("click", function () {
    var pair = customRange();
    if (!pair) return;              // an empty or backwards range fetches nothing
    setRange("custom", pair);
    refresh();
  });

  document.querySelector("[data-game]").addEventListener("change", function (e) {
    state.game = e.target.value;
    refresh();
  });

  document.querySelector("[data-refresh]").addEventListener("click", refresh);

  var liveBtn = document.querySelector("[data-live]");
  if (liveBtn) liveBtn.addEventListener("click", function () {
    state.live = !state.live;
    liveBtn.setAttribute("aria-pressed", state.live ? "true" : "false");
    var lab = liveBtn.querySelector("[data-live-label]");
    if (lab) lab.textContent = state.live ? "Live" : "Paused";
    if (state.live) { startLive(); refresh(); } else { stopLive(); }
  });

  document.querySelector("[data-signout]").addEventListener("click", function () {
    stopLive();
    state.token = null;
    try { sessionStorage.removeItem("esb.ops.token"); } catch (e) {}
    app.hidden = true;
    gate.hidden = false;
    gateForm.querySelector("input").value = "";
  });

  document.querySelectorAll(".tabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      state.tab = b.getAttribute("data-tab");
      // Leaving Sessions/Orders drops the open drill-down, so coming back lands
      // on the list rather than on whichever row was open last time.
      state.sessionId = null;
      state.sessionDetail = null;
      state.orderId = null;
      state.orderDetail = null;
      document.querySelectorAll(".tabs button").forEach(function (o) {
        o.setAttribute("aria-selected", o === b ? "true" : "false");
      });
      render();
      // On a phone the nav is an overlay; picking a section closes it.
      shell.classList.remove("side-open");
      // Entering Accounts / Guides / Boosters / Orders pulls that store fresh (each rides its own request).
      if (state.tab === "accounts") loadAccounts();
      if (state.tab === "guides") loadGuides();
      if (state.tab === "boosters") loadBoosters();
      if (state.tab === "orders") loadOrders();
      if (state.tab === "carts") loadCarts();
    });
  });

  // Sidebar toggle (mobile) — the nav slides in over the content.
  var shell = document.querySelector(".shell");
  var sideToggle = document.querySelector("[data-side-toggle]");
  if (sideToggle && shell) {
    sideToggle.addEventListener("click", function () { shell.classList.toggle("side-open"); });
    document.addEventListener("click", function (e) {
      if (!shell.classList.contains("side-open")) return;
      if (e.target.closest(".side") || e.target.closest("[data-side-toggle]")) return;
      shell.classList.remove("side-open");
    });
  }

  // A token from a previous page load gets us straight in.
  if (state.token) {
    app.hidden = false;
    gate.hidden = true;
    refresh();
    startLive();
  }
})();
