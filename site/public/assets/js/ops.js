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
                // The Sessions tab's traffic-source filter — "google.com / referral",
                // the pair that table prints. Applied server-side, before the
                // newest-300 cap, so it reaches the whole period rather than the
                // page: filtering the rows here would answer a different question
                // and look identical.
                source: "",
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
                // The account-stock store — the credentials behind the accounts
                // shop. Its own store, fetched on demand like every other. ⚠ The
                // list never carries a password; `revealed` holds the ones an
                // operator has deliberately read out, for this page load only —
                // it is never persisted to sessionStorage.
                stock: null, stockLoading: false, stockError: null, revealed: {},
                // Which server's shelf is on screen. The tab is organised the
                // way the shop is — one server at a time — because an account
                // is region-locked and a stock decision is only ever about one
                // shard. null = the first server in the payload.
                stockServer: null,
                // The open product, master-detail like Sessions and Orders:
                // {sku, region} plus the slot payload the server returns. This
                // is the one place in the console that WRITES, so the detail is
                // always re-read from the response of the write rather than
                // patched client-side — the store is the authority on what a
                // slot holds after an edit.
                slot: null, slotDetail: null, slotBusy: false, slotMsg: null,
                slotEdit: null,
                // The abandoned-checkout store — captured emails + the config the
                // buyer was about to pay for. Its own store (PII), fetched on
                // demand. Distinct from the "Abandoned" tab, which is the
                // anonymous analytics view with no email attached.
                carts: null, cartsLoading: false, cartsError: null,
                // The mystery-discount store — the emails the configurator
                // modal captured and the live token each one bought. Its own
                // store again (PII + a real discount), fetched on demand.
                mystery: null, mysteryLoading: false, mysteryError: null,
                // Mail discounts — a read-only JOIN over the other stores
                // (maillist.py), fetched on demand like every PII panel.
                ml: null, mlLoading: false, mlError: null,
                // The outbox — every message actually sent, with its body.
                // On demand only: it is the most sensitive payload here.
                ob: null, obLoading: false, obError: null, obKind: "", obOpen: null,
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
                 game: state.game || null, source: state.source || null,
                 synthetic: state.synthetic })
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
          if (state.tab === "stock") loadStock();
          if (state.tab === "mystery") loadMystery();
          if (state.tab === "maildiscounts") loadMailDiscounts();
          if (state.tab === "outbox") loadOutbox();
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

    /* The accounts shop's own funnel. It is a separate card and not extra rows
       on the one above, for the reason SHOP_FUNNEL is separate from FUNNEL in
       insights.py: /accounts is a different product on a page with no
       configurator, so its visitors can never reach "Touched the configurator"
       and folding them in would read as a collapse. Denominator is sessions
       that LANDED on the shop, never all traffic. */
    var sp = d.shop;
    if (sp && (sp.landed || sp.unmeasured)) {
      var since = sp.since
        ? new Date(sp.since * 1000).toLocaleString(undefined,
            { dateStyle: "medium", timeStyle: "short" })
        : null;
      var note = since
        ? "Measured since " + since + ", when the shop's beacons shipped."
        : "The shop's beacons have not arrived yet — deploy, then read this.";
      if (sp.unmeasured) {
        note += " " + num(sp.unmeasured) + " earlier visit" +
          (sp.unmeasured === 1 ? " is" : "s are") + " excluded: they carry no " +
          "shop events at all, so counting them would invent a page fault.";
      }
      g.appendChild(card({
        title: "The accounts shop",
        sub: "Where a visitor to /accounts stops. " + note,
        chart: function (w) { return funnelChart(w, sp.rows); },
        table: {
          head: ["Step", "Sessions", "Of all", "Of previous", "Lost here"],
          num: [1, 2, 3, 4],
          rows: sp.rows.map(function (r) {
            return [r.label, num(r.sessions), pct(r.pct_total), pct(r.pct_prev),
                    num(r.lost)];
          })
        }
      }));

      var sk = document.createElement("div");
      sk.className = "kpis";
      sk.appendChild(kpi("Landed on the shop", num(sp.landed)));
      /* ⚠ THE ONE TO READ FIRST. A session that recorded a page view on
         /accounts and never reported the shop mounting is a browser that ran
         the beacon and then did not render the shop — a broken page, not a
         bounce. Single figures are noise (a visitor who left mid-load); a
         steady share is a bug, and it is the one thing a bounce rate can
         never tell you apart from disinterest. */
      sk.appendChild(kpi("Shop never rendered", num(sp.stalled) +
                         (sp.landed ? " · " + pct(sp.stalled_pct) : "")));
      /* A shard whose whole board was sold out when somebody looked at it.
         That is a page nobody can buy from, and left uncounted it reads as a
         price objection. */
      sk.appendChild(kpi("Sold-out boards seen", num(sp.sold_out_views)));
      sk.appendChild(kpi("Servers picked", sp.shards.length
        ? sp.shards.map(function (r) { return r.shard + " " + num(r.n); }).join(" · ")
        : "—"));
      g.appendChild(wrapCard("What the shop's own steps say",
        "Step 1 is a server, step 2 is the board. These say which one they " +
        "stopped at, and whether the page worked at all.", sk));
    }

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

    // The payload carries the page (capped), the matched total, the menu of
    // sources and the tiles — all computed server-side over every matched
    // session, not over the page below.
    var sd = d.sessions || {};
    if (Array.isArray(sd)) sd = { rows: sd };          // pre-filter payload shape
    var rows = sd.rows || [];
    var st = sd.stats || {};
    var picked = sd.source || "";
    var total = sd.total == null ? rows.length : sd.total;
    var f = document.createDocumentFragment();

    var kr = document.createElement("div");
    kr.className = "kpis";
    // Every tile is the server's, counted over all `total` matched sessions.
    // Recomputing them from `rows` would count the newest 300 only and print
    // that as the period's figure — which is exactly the number a source filter
    // is opened to read.
    kr.appendChild(kpi("Sessions", num(st.sessions == null ? rows.length : st.sessions)));
    kr.appendChild(kpi("Median duration", dur(st.median_duration || 0)));
    kr.appendChild(kpi("Pages per session", (st.pages_per || 0).toFixed(1)));
    kr.appendChild(kpi("Events per session", (st.events_per || 0).toFixed(1)));
    kr.appendChild(kpi("Converted", num(st.converted || 0)));
    kr.appendChild(kpi("Returning", num(st.returning || 0)));
    // Sign-ups made IN these sessions — deliberately not "sessions with an
    // account", which folds in everyone who was already logged in and reads as
    // a far bigger number than the panel actually produced.
    kr.appendChild(kpi("Signed up", num(st.signed_up || 0)));
    f.appendChild(kr);

    // Traffic source: the "source / medium" pair the column prints, tallied
    // over the unfiltered period so the menu never collapses to the one already
    // picked. A pick that has since gone quiet is kept in the list rather than
    // dropped, or the control would silently show "All sources" over an empty
    // table.
    var srcs = (sd.sources || []).slice();
    if (picked && !srcs.some(function (o) { return o.key === picked; })) {
      srcs.unshift({ key: picked, sessions: 0 });
    }
    // Every source's tally adds up to the period's whole session count, which is
    // what the filtered line below compares against.
    var windowTotal = srcs.reduce(function (n, o) { return n + o.sessions; }, 0) || total;
    var srcOpts = '<option value="">All sources (' + num(windowTotal) + ")</option>" +
      srcs.map(function (o) {
        return '<option value="' + esc(o.key) + '"' + (o.key === picked ? " selected" : "") +
               ">" + esc(o.key) + " (" + num(o.sessions) + ")</option>";
      }).join("");

    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every session</h3><span class="spacer"></span>' +
      '<select class="field" data-source-filter aria-label="Filter by traffic source">' +
        srcOpts + "</select>" +
      '<button class="btn btn-sm" type="button" data-export-sessions>Export CSV</button></div>' +
      '<p class="card-sub">Newest first. Click a session id to see everything that visitor did, ' +
      "in order, with the time spent on each page." +
      (picked ? " Showing <strong>" + esc(picked) + "</strong> only — " + num(total) +
                " of " + num(windowTotal) + " sessions in this period." : "") +
      (total > rows.length
        ? ' The table lists the newest ' + num(rows.length) + " of them; the tiles above count all " +
          num(total) + "."
        : "") + "</p>";

    if (!rows.length) {
      el.insertAdjacentHTML("beforeend", picked
        ? '<p class="empty">No sessions from ' + esc(picked) + " in this period.</p>"
        : '<p class="empty">No sessions in this period yet. Browse the site and hit Refresh.</p>');
      wireSourceFilter(el);
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
          (r.returning ? '<span class="chip">returning</span>' : "") +
          acctChip(r.acct) + "</td>" +
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
                  "paid", "value_usd", "returning", "account_step", "shop_step"];
      var lines = [cols.join(",")];
      rows.forEach(function (r) {
        lines.push([new Date(r.start * 1000).toISOString(), new Date(r.end * 1000).toISOString(),
                    r.id, r.anon, r.src, r.med, r.cmp, r.dev, r.co, countryName(r.co),
                    r.cosrc, r.tz, r.lang, r.entry, r.exit,
                    r.pages, r.duration, r.events, r.requotes, r.step, r.paid ? "yes" : "no",
                    r.value, r.returning ? "yes" : "no", r.acct || "guest",
                    // The accounts shop's own furthest step. Blank for every
                    // session that never opened it, which is most of them —
                    // `furthest_step` already carries it in words where it is
                    // the furthest thing that happened.
                    r.shop_step || ""]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      // The file holds exactly what the table holds — the filtered page. Naming
      // the source in it is what stops one source's export being read later as
      // the whole period's.
      a.download = "esb-sessions-" +
        (picked ? picked.replace(/[^a-z0-9.]+/gi, "-").replace(/^-|-$/g, "") + "-" : "") +
        new Date().toISOString().slice(0, 10) + ".csv";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });

    wireSourceFilter(el);
    f.appendChild(el);
    return f;
  }

  /* The traffic-source filter. Server-side, so changing it refetches — the same
     trade the game filter in the top bar makes, and the only way the filter can
     reach past the newest-300 cap the table draws. */
  function wireSourceFilter(el) {
    var sel = el.querySelector("[data-source-filter]");
    if (!sel) return;
    sel.addEventListener("change", function () {
      state.source = sel.value;
      refresh();
    });
  }

  /* The account flow, in words. The events carry a step and an outcome and
     nothing else — no email, no name; the Accounts tab is where the person is.
     `reason` on an email refusal is the server's own status code, and on an
     OAuth one it is the sentence the provider round trip failed with, already
     written for a human, so it passes straight through. */
  var AUTH_MODE = { signin: "log in tab", signup: "sign up tab", oauth: "social sign-in" };
  var AUTH_REASON = {
    exists: "email already registered", invalid: "wrong email or password",
    weak: "password too short", email: "invalid email address",
    error: "server refused it", network: "couldn't reach the server"
  };
  function authNote(t) {
    var m = t.meta || {}, bits = [];
    if (t.e === "session_start" && m.account) {
      bits.push(m.account === "in" ? "arrived already signed in" : "arrived as a guest");
    }
    if (m.mode) bits.push(AUTH_MODE[m.mode] || m.mode);
    if (m.method) bits.push("via " + m.method);
    if (m.reason) bits.push(AUTH_REASON[m.reason] || m.reason);
    return bits;
  }

  /* The session-level marker: the furthest the account flow got in this visit.
     "signed in" is the visitor who arrived with a session already — they emit
     no login, and counting them as guests is what makes an account funnel read
     lower than it is. */
  var ACCT_CHIP = {
    signed_up: { label: "signed up", cls: "chip good" },
    logged_in: { label: "logged in", cls: "chip" },
    signed_in: { label: "signed in", cls: "chip" }
  };
  function acctChip(acct) {
    var c = ACCT_CHIP[acct];
    return c ? '<span class="' + c.cls + '">' + c.label + "</span>" : "";
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
        fact("Account", (ACCT_CHIP[s.acct] || {}).label || "guest") +
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
      bits = bits.concat(authNote(t));
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

  /* ── Stock: the account credentials behind the accounts shop ──────────────
     The one tab in this console that sits next to live secrets. Three rules
     hold here and none is cosmetic:

       * the LIST never carries a password (`stock.summary()` masks the login
         and omits the rest) — this table answers "how much is left", and it is
         rendered into a browser that keeps it in memory;
       * reading one out is a separate, deliberate click per unit
         (`stock_reveal`), logged server-side, and kept in memory for this page
         load only — never sessionStorage, which survives the tab;
       * the first thing on the tab is anything PAID AND NOT DELIVERED, because
         that is a customer sitting with a receipt and no account. */
  function loadStock() {
    if (state.stockLoading) return;
    state.stockLoading = true;
    state.stockError = null;
    api({ action: "stock", token: state.token, days: state.days }).then(function (res) {
      state.stockLoading = false;
      if (res.status === 200 && res.body.stock) {
        state.stock = res.body.stock;
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        state.stockError = "This server doesn't serve the stock store yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.stockError = "Couldn't load the stock — the server returned " + res.status + ".";
      }
      if (state.tab === "stock") render();
    }).catch(function () {
      state.stockLoading = false;
      state.stockError = "Couldn't reach the server. Is it running?";
      if (state.tab === "stock") render();
    });
  }

  /* The 44th product, opened. Every write below re-reads the slot from its own
     response, so the list a operator is looking at is the store's answer and
     never a local guess about what the store now holds. */
  function openSlot(sku, region) {
    state.slot = { sku: sku, region: region };
    state.slotDetail = null;
    state.slotMsg = null;
    state.slotEdit = null;
    render();
    stockCall("stock_slot", { sku: sku, region: region });
  }

  function closeSlot() {
    state.slot = null; state.slotDetail = null; state.slotMsg = null;
    state.slotEdit = null;
    loadStock();                       // the board's counts moved while we were in
    render();
  }

  function stockCall(action, extra, onDone) {
    if (state.slotBusy) return;
    state.slotBusy = true;
    var body = { action: action, token: state.token };
    for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) body[k] = extra[k];
    api(body).then(function (res) {
      state.slotBusy = false;
      if (res.status === 401) return toGate();
      if (res.body && res.body.slot) state.slotDetail = res.body.slot;
      if (res.status !== 200) {
        state.slotMsg = { bad: true, text: "The server refused that: " +
          ((res.body && res.body.error) || res.status) + "." };
      } else if (onDone) {
        onDone(res.body);
      }
      render();
    }).catch(function () {
      state.slotBusy = false;
      state.slotMsg = { bad: true, text: "Couldn't reach the server." };
      render();
    });
  }

  function revealUnit(uid) {
    api({ action: "stock_reveal", token: state.token, unit: uid }).then(function (res) {
      if (res.status === 401) return toGate();
      if (res.status === 200 && res.body.unit) state.revealed[uid] = res.body.unit;
      else state.revealed[uid] = { id: uid, error: "not found" };
      if (state.tab === "stock") render();
    });
  }

  function panelStock() {
    if (state.slot) return panelSlot();
    var f = document.createDocumentFragment();
    var a = state.stock;

    if (state.stockError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.stockError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm";
      retry.type = "button";
      retry.textContent = "Try again";
      retry.style.margin = "0 auto 16px";
      retry.style.display = "block";
      retry.addEventListener("click", function () { state.stockError = null; loadStock(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }
    if (!a) {
      loadStock();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading stock…</p>';
      f.appendChild(wait);
      return f;
    }

    var note = document.createElement("div");
    note.className = "banner synthetic";
    note.innerHTML = '<span class="ico">▲</span><div><strong>Live account credentials.</strong> ' +
      "Every row is a real login. The list below never shows a password — reading one out is a " +
      "separate click, and it is recorded in the server log. Load stock with " +
      "<code>site/tools/stock_import.py</code>, and prune it with <code>--purge-sold</code>.</div>";
    f.appendChild(note);

    // ⚠ An empty store gets the SAME grid, not a dead end. The shop sells
    // `products × shards` accounts and every one of those slots is something an
    // operator fills; replacing the tab with one "nothing here" line hid the
    // whole catalogue behind the fact that none of it was stocked yet.
    if (!a.total) {
      var empty = document.createElement("div");
      empty.className = "card";
      empty.innerHTML = '<p class="empty">Nothing stocked yet — ' +
        "<b>" + num((a.products || 0) * (a.shards || 0)) + "</b> empty slots (" +
        num(a.products || 0) + " tiers on " + num(a.shards || 0) + " servers).<br>" +
        "The shop is quoting <code>data.py</code>'s hand-set figures, and a paid order has " +
        "nothing to hand over.<br>Fill one:<br>" +
        "<code>python3 site/tools/stock_import.py --sku lol-gold --region EUW -f gold-euw.txt</code>" +
        "</p>";
      f.appendChild(empty);
    }

    // ⚠ First, because it is the only thing here that is somebody waiting.
    var undel = a.undelivered || [];
    if (undel.length) {
      var un = document.createElement("div");
      un.className = "card";
      un.innerHTML = '<div class="card-hd"><h3>Paid, not delivered</h3></div>' +
        '<p class="card-sub">These orders were charged and the handover mail did not go out. ' +
        "Reveal the credentials and send them by hand.</p>";
      var uh = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
        ["Order", "Account", "Server", "Customer", "Unit", ""].map(function (h) {
          return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>";
      undel.forEach(function (r) {
        uh += "<tr><td>" + esc(r.order_id || "—") + "</td><td>" + esc(r.listing) + "</td>" +
          '<td class="dim">' + esc(r.region) + "</td><td>" + esc(r.buyer || "—") + "</td>" +
          '<td class="dim">' + esc(r.id) + "</td>" +
          '<td><button class="btn btn-sm" type="button" data-reveal="' + esc(r.id) +
          '">Reveal</button></td></tr>';
      });
      un.insertAdjacentHTML("beforeend", uh + "</tbody></table></div>");
      f.appendChild(un);
    }

    // What has been read out on this page load, and nowhere else.
    var revealedIds = Object.keys(state.revealed);
    if (revealedIds.length) {
      var rv = document.createElement("div");
      rv.className = "card";
      rv.innerHTML = '<div class="card-hd"><h3>Revealed credentials</h3>' +
        '<span class="spacer"></span><button class="btn btn-sm" type="button" data-hide-revealed>' +
        "Hide</button></div>" +
        '<p class="card-sub">This page load only — nothing is stored in the browser. ' +
        "Close the tab when you are done.</p>";
      var rh = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
        ["Unit", "Account", "Server", "Login", "Password", "Inbox", "Inbox password"]
          .map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") +
        "</tr></thead><tbody>";
      revealedIds.forEach(function (uid) {
        var u = state.revealed[uid];
        if (u.error) {
          rh += '<tr><td class="dim">' + esc(uid) + '</td><td colspan="6">' + esc(u.error) + "</td></tr>";
          return;
        }
        rh += '<tr><td class="dim">' + esc(u.id) + "</td><td>" + esc(u.listing || u.sku) + "</td>" +
          '<td class="dim">' + esc(u.region) + "</td><td><code>" + esc(u.login) + "</code></td>" +
          "<td><code>" + esc(u.password) + "</code></td>" +
          "<td>" + esc(u.email || "—") + "</td>" +
          "<td>" + (u.email_password ? "<code>" + esc(u.email_password) + "</code>" : "—") + "</td></tr>";
      });
      rv.insertAdjacentHTML("beforeend", rh + "</tbody></table></div>");
      f.appendChild(rv);
    }

    var servers = a.servers || [];
    var listings = a.listings || [];          // all of them, stocked or not

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Available", num(a.available), undefined, "", true));
    kr.appendChild(kpi("Slots", num((a.products || 0) * (a.shards || 0))));
    kr.appendChild(kpi("Sold, all time", num(a.sold)));
    kr.appendChild(kpi("Not delivered", num(undel.length)));
    f.appendChild(kr);

    if (a.total) {
      var g = document.createElement("div");
      g.className = "grid";
      g.appendChild(card({
        cls: "half", title: "On the shelf, per server",
        sub: "Units that can be sold right now.",
        chart: function (w) {
          return barsH(w, {
            rows: servers.map(function (r) { return { label: r.region, value: r.available }; }),
            color: SERIES[0], alt: "Available per server"
          });
        },
        table: {
          head: ["Server", "On the shelf", "Shown on site"], num: [1, 2],
          rows: servers.map(function (r) {
            return [r.region, num(r.available), num(r.shown)]; })
        }
      }));
      g.appendChild(card({
        cls: "half", title: "On the shelf, per tier",
        sub: "A tier with none left refuses at checkout instead of selling.",
        chart: function (w) {
          return barsH(w, {
            rows: listings.map(function (r) { return { label: r.listing, value: r.available }; }),
            color: SERIES[2], alt: "Available per listing"
          });
        },
        table: {
          head: ["Tier", "Available", "Sold"], num: [1, 2],
          rows: listings.map(function (r) {
            return [r.listing, num(r.available), num(r.sold)]; })
        }
      }));
      f.appendChild(g);
    }

    // The grid the operator actually restocks from: listing × shard.
    /* ── The board, ONE SERVER AT A TIME ──────────────────────────────────
       Organised the way the shop is: an account is region-locked, so every
       stocking decision is about one shard and one tier. A 4-column matrix
       made you read across a row to answer "what do I have on EUW", which is
       the only question this tab gets asked.

       Two figures per tier, and the pair is the point —
         on shelf : real credentials, what a buyer can actually be given
         shown    : what /accounts.html advertises, data.py's hand-set count
       They differ on purpose while STOCK_PUBLIC_COUNTS is off (the business's
       call), and this is the only place the gap is visible. A tier at "·" has
       never been stocked here, so an order for it is taken with nothing
       behind it. */
    if (!state.stockServer && servers.length) state.stockServer = servers[0].region;
    var sv = servers.filter(function (x) { return x.region === state.stockServer; })[0]
             || servers[0] || { region: "", code: "", available: 0, shown: 0 };

    var picker = document.createElement("div");
    picker.className = "card";
    picker.innerHTML = '<div class="card-hd"><h3>Server</h3><span class="spacer"></span>' +
      '<span class="chip">' + num(listings.length) + " products each</span></div>" +
      '<p class="card-sub">An account is locked to the server it was made on, so stock ' +
      "is held per server. Pick one.</p>";
    var chips = document.createElement("div");
    chips.className = "seg";
    servers.forEach(function (x) {
      // A plain child of `.seg` — the console's own segmented control styles
      // it, and `aria-pressed` is what it reads for the active state. A `.btn`
      // in here would bring its own border and break the joined row.
      var b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-pressed", x.region === sv.region ? "true" : "false");
      b.innerHTML = esc(x.code) + ' <span class="dim">' + num(x.available) + "</span>";
      b.title = x.region + " — " + x.available + " on the shelf, " + x.shown + " shown on site";
      b.addEventListener("click", function () { state.stockServer = x.region; render(); });
      chips.appendChild(b);
    });
    picker.appendChild(chips);
    f.appendChild(picker);

    var grid = document.createElement("div");
    grid.className = "card";
    grid.innerHTML = '<div class="card-hd"><h3>' + esc(sv.region) + '</h3>' +
      '<span class="spacer"></span><span class="chip">' + esc(sv.code) + "</span>" +
      '<span class="chip">' + num(sv.available) + " on the shelf</span></div>" +
      '<p class="card-sub">' +
      (a.public_counts
        ? "The shop is publishing these real counts."
        : "<b>On shelf</b> is what we can hand over on " + esc(sv.code) + ". <b>Shown</b> is " +
          "what the site advertises there — <code>data.py</code>'s hand-set figures, because " +
          "publishing the real counts is off. A tier at “·” has never been stocked on this " +
          "server, so an order for it will be taken and have nothing behind it.") + "</p>";
    var gh = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      ["Tier", "Kind", "On shelf", "Shown on site", "Sold"].map(function (h, i) {
        return '<th' + (i >= 2 ? ' class="num"' : "") + ">" + esc(h) + "</th>";
      }).join("") + "</tr></thead><tbody>";
    listings.forEach(function (r) {
      var n = (r.servers || {})[sv.region];
      var shown = (r.shown || {})[sv.region];
      gh += '<tr><td><button type="button" class="link-btn" data-slot="' + esc(r.sku) +
        '">' + esc(r.listing) + "</button></td>" +
        '<td class="dim">' + esc(r.kind || "") + "</td>" +
        '<td class="num">' +
          (n === null || n === undefined ? '<span class="dim">·</span>'
            : (n === 0 ? '<b class="bad">0</b>' : num(n))) + "</td>" +
        '<td class="num dim">' + num(shown) + "</td>" +
        '<td class="num">' + num((r.sold_by || {})[sv.region] || 0) + "</td></tr>";
    });
    gh += "</tbody></table></div>";
    grid.insertAdjacentHTML("beforeend", gh);
    grid.insertAdjacentHTML("beforeend",
      '<p class="card-sub">Click a tier to add, edit or remove its keys. From a ' +
      "shell it is <code>python3 site/tools/stock_import.py --sku &lt;tier id&gt; " +
      "--region " + esc(sv.code) + " -f accounts.txt</code></p>");
    [].slice.call(grid.querySelectorAll("[data-slot]")).forEach(function (b) {
      b.addEventListener("click", function () {
        openSlot(b.getAttribute("data-slot"), sv.region);
      });
    });
    f.appendChild(grid);

    // Every unit, newest first. Nothing to draw on an empty store — the board
    // above is what that case needs.
    var rows = (a.rows || []).filter(function (r) { return r.region === sv.region; });
    if (!rows.length) {
      [].slice.call(f.querySelectorAll("[data-reveal]")).forEach(function (b) {
        b.addEventListener("click", function () { revealUnit(b.getAttribute("data-reveal")); });
      });
      return f;
    }
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML = '<div class="card-hd"><h3>Units on ' + esc(sv.code) + '</h3>' +
      '<span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-stock>Export CSV</button></div>' +
      '<p class="card-sub">Newest first, ' + esc(sv.region) + " only — " +
      num(rows.length) + " of " + num(a.total) +
      " stored. Logins are masked; the CSV carries no credential either.</p>";
    var head = ["Unit", "Tier", "Login", "State", "Order", "Customer", "Mailed", ""];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (r) {
      var stateChip = r.status === "available"
        ? '<span class="chip">available</span>'
        : esc(r.status);
      html += "<tr>" +
        '<td class="dim">' + esc(r.id) + "</td>" +
        "<td>" + esc(r.listing) + "</td>" +
        "<td>" + esc(r.login) + "</td>" +
        "<td>" + stateChip + "</td>" +
        "<td>" + esc(r.order_id || "—") + "</td>" +
        "<td>" + esc(r.buyer || "—") + "</td>" +
        "<td>" + (r.status !== "sold" ? '<span class="dim">—</span>'
          : (r.mailed ? "yes" : '<b class="bad">no</b>')) + "</td>" +
        '<td><button class="btn btn-sm" type="button" data-reveal="' + esc(r.id) +
        '">Reveal</button></td>' +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");
    f.appendChild(el);

    // One delegated handler for every Reveal button on the tab.
    [].slice.call(f.querySelectorAll("[data-reveal]")).forEach(function (b) {
      b.addEventListener("click", function () { revealUnit(b.getAttribute("data-reveal")); });
    });
    var hide = f.querySelector("[data-hide-revealed]");
    if (hide) hide.addEventListener("click", function () { state.revealed = {}; render(); });

    var exp = f.querySelector("[data-export-stock]");
    if (exp) exp.addEventListener("click", function () {
      var cols2 = ["unit", "tier", "server", "login_masked", "status", "order_id",
                   "customer", "mailed", "note"];
      var lines = [cols2.join(",")];
      rows.forEach(function (r) {
        lines.push([r.id, r.listing, r.region, r.login, r.status, r.order_id, r.buyer,
                    r.mailed ? "yes" : "no", r.note]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var blob = new Blob([lines.join("\n")], { type: "text/csv" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "esb-stock-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    return f;
  }

  /* ── One product on one server: add, edit, delete its keys ────────────────
     The console's ONE write surface. Three rules it keeps:

       * a password is never in the list — the rows are masked exactly as the
         board's are, and Reveal is still one deliberate click per unit;
       * every write re-reads the slot from its own response, so what is on
         screen after an edit is the store's answer, not a local guess;
       * an import reports the lines it REFUSED with their numbers. Pasting 300
         accounts and being told "12 added" without hearing about the other
         three is how a truncated password reaches a customer. */
  function panelSlot() {
    var f = document.createDocumentFragment();
    var d = state.slotDetail;

    var back = document.createElement("button");
    back.className = "btn btn-sm back-btn";
    back.type = "button";
    back.textContent = "← All products";
    back.addEventListener("click", closeSlot);
    f.appendChild(back);

    if (!d) {
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading product…</p>';
      f.appendChild(wait);
      return f;
    }

    var head = document.createElement("div");
    head.className = "card";
    head.innerHTML =
      '<div class="card-hd"><h3>' + esc(d.listing) + " · " + esc(d.region) + "</h3>" +
      '<span class="spacer"></span><span class="chip">' + esc(d.code) + "</span>" +
      '<span class="chip">' + esc(d.kind) + "</span></div>" +
      '<p class="card-sub">' +
      "<b>" + num(d.available) + "</b> on the shelf · <b>" + num(d.sold) + "</b> sold" +
      (d.held ? " · <b>" + num(d.held) + "</b> off sale" : "") +
      " · the site advertises <b>" + num(d.shown) + "</b> here" +
      (d.public_counts ? "" : " (<code>data.py</code>'s figure — real counts are unpublished)") +
      ".</p>" +
      (d.undelivered
        ? '<p class="card-sub"><b class="bad">' + num(d.undelivered) +
          " sold unit(s) here were never mailed.</b> Reveal them and send by hand.</p>"
        : "") +
      (d.known && !d.available
        ? '<p class="card-sub"><b class="bad">Nothing left on this server.</b> ' +
          "Checkout refuses this tier on " + esc(d.code) + " until you add keys — the " +
          "page still advertises " + num(d.shown) + ".</p>"
        : "") +
      (!d.known
        ? '<p class="card-sub">Never stocked here. An order for it is <b>taken anyway</b>, ' +
          "against the advertised figure, and has nothing behind it — add keys, or expect to " +
          "refund.</p>"
        : "");
    f.appendChild(head);

    if (state.slotMsg) {
      var msg = document.createElement("div");
      msg.className = "banner" + (state.slotMsg.bad ? " synthetic" : "");
      msg.innerHTML = '<span class="ico">' + (state.slotMsg.bad ? "▲" : "✓") + "</span><div>" +
        state.slotMsg.text + "</div>";
      f.appendChild(msg);
    }

    // ── add keys ─────────────────────────────────────────────────────────
    var addCard = document.createElement("div");
    addCard.className = "card";
    addCard.innerHTML = '<div class="card-hd"><h3>Add accounts</h3></div>' +
      '<p class="card-sub">One per line, <code>user:pass</code>. Two optional fields carry the ' +
      "original inbox: <code>user:pass:inbox@mail.com:inboxpassword</code>. If a password " +
      "contains a colon write that line as <code>user|pass</code>. Lines starting with " +
      "<code>#</code> are ignored.</p>";
    var ta = document.createElement("textarea");
    ta.className = "field ta";
    ta.rows = 6;
    ta.spellcheck = false;
    ta.placeholder = "SmurfKing123:gamepassword\nOtherGuy:pw2:inbox@mail.com";
    addCard.appendChild(ta);
    var noteIn = document.createElement("input");
    noteIn.className = "field";
    noteIn.type = "text";
    noteIn.placeholder = "Note on this batch (optional) — e.g. bought 3 Sep, seller X";
    addCard.appendChild(noteIn);
    var addBtn = document.createElement("button");
    addBtn.className = "btn";
    addBtn.type = "button";
    addBtn.textContent = state.slotBusy ? "Adding…" : "Add to " + d.code;
    addBtn.disabled = !!state.slotBusy;
    addBtn.addEventListener("click", function () {
      var text = ta.value;
      if (!text.trim()) return;
      stockCall("stock_add", { sku: d.sku, region: d.region, text: text,
                               note: noteIn.value || "" }, function (b) {
        var r = (b && b.result) || {};
        var parts = [num(r.added || 0) + " added"];
        if (r.duplicate) parts.push(num(r.duplicate) + " already stored");
        var errs = r.errors || [];
        state.slotMsg = {
          bad: !!errs.length,
          text: "<strong>" + parts.join(", ") + ".</strong>" +
            (errs.length
              ? " " + num(errs.length) + " line(s) refused: " +
                errs.slice(0, 6).map(function (e) {
                  return "line " + e.line + " — " + esc(e.message);
                }).join("; ") + (errs.length > 6 ? "; …" : "") +
                " Fix those and paste them again."
              : "")
        };
      });
    });
    addCard.appendChild(addBtn);
    f.appendChild(addCard);

    // ── the keys ─────────────────────────────────────────────────────────
    var list = document.createElement("div");
    list.className = "card";
    list.innerHTML = '<div class="card-hd"><h3>Keys</h3><span class="spacer"></span>' +
      '<span class="chip">' + num((d.rows || []).length) + " stored</span></div>" +
      '<p class="card-sub">Available first. Logins are masked — Reveal shows one, and every ' +
      "reveal is written to the server log.</p>";

    if (!(d.rows || []).length) {
      list.insertAdjacentHTML("beforeend",
        '<p class="empty">No keys here yet. Paste some above.</p>');
      f.appendChild(list);
      return f;
    }

    var tbl = document.createElement("table");
    tbl.className = "tbl";
    tbl.innerHTML = "<thead><tr>" +
      ["Unit", "Login", "State", "Order", "Mailed", ""].map(function (h) {
        return "<th>" + esc(h) + "</th>";
      }).join("") + "</tr></thead>";
    var tb = document.createElement("tbody");

    (d.rows || []).forEach(function (r) {
      var tr = document.createElement("tr");
      var shown = state.revealed[r.id];
      tr.innerHTML =
        '<td class="dim">' + esc(r.id) + "</td>" +
        "<td>" + (shown && !shown.error
          ? "<code>" + esc(shown.login) + "</code> <code>" + esc(shown.password) + "</code>" +
            (shown.email ? " <span class=\"dim\">" + esc(shown.email) + "</span>" : "")
          : esc(r.login)) + "</td>" +
        "<td>" + (r.status === "available" ? '<span class="chip">available</span>'
          : esc(r.status)) + "</td>" +
        "<td>" + esc(r.order_id || "—") + "</td>" +
        "<td>" + (r.status !== "sold" ? '<span class="dim">—</span>'
          : (r.mailed ? "yes" : '<b class="bad">no</b>')) + "</td>";

      var act = document.createElement("td");
      act.className = "row-actions";
      [["Reveal", function () { revealUnit(r.id); }],
       ["Edit", function () { state.slotEdit = r.id; revealUnit(r.id); }],
       [r.status === "held" ? "Put back" : "Off sale", function () {
         if (r.status === "sold") return;
         stockCall("stock_status", { unit: r.id,
           status: r.status === "held" ? "available" : "held" });
       }],
       ["Delete", function () {
         // Irreversible and it is a real account, so it asks — the only
         // confirm in the console, and it earns it.
         if (!window.confirm("Delete " + r.id + " from " + d.listing + " · " + d.code +
             "?\n\nThis removes the account from the shelf for good. If it was sold, the " +
             "record of that sale goes with it.")) return;
         delete state.revealed[r.id];
         stockCall("stock_delete", { unit: r.id }, function () {
           state.slotMsg = { text: "<strong>Deleted.</strong> " + esc(r.id) + " is gone." };
         });
       }]].forEach(function (pair) {
        if (pair[0] === "Off sale" && r.status === "sold") return;
        if (pair[0] === "Put back" && r.status !== "held") return;
        var b = document.createElement("button");
        b.className = "btn btn-sm";
        b.type = "button";
        b.textContent = pair[0];
        b.disabled = !!state.slotBusy;
        b.addEventListener("click", pair[1]);
        act.appendChild(b);
      });
      tr.appendChild(act);
      tb.appendChild(tr);

      // The edit form opens under its own row, filled from the reveal.
      if (state.slotEdit === r.id) {
        var ed = document.createElement("tr");
        var cell = document.createElement("td");
        cell.colSpan = 6;
        if (!shown || shown.error) {
          cell.innerHTML = '<p class="card-sub">Reading the current values…</p>';
        } else {
          var fields = [["login", "Login"], ["password", "Password"],
                        ["email", "Account inbox"], ["email_password", "Inbox password"],
                        ["note", "Note"]];
          var wrap = document.createElement("div");
          wrap.className = "edit-row";
          var inputs = {};
          fields.forEach(function (fl) {
            var lab = document.createElement("label");
            lab.textContent = fl[1];
            var inp = document.createElement("input");
            inp.className = "field";
            inp.type = "text";
            inp.spellcheck = false;
            inp.value = shown[fl[0]] || "";
            inputs[fl[0]] = inp;
            lab.appendChild(inp);
            wrap.appendChild(lab);
          });
          var save = document.createElement("button");
          save.className = "btn";
          save.type = "button";
          save.textContent = "Save";
          save.disabled = !!state.slotBusy;
          save.addEventListener("click", function () {
            var payload = {};
            for (var k in inputs) payload[k] = inputs[k].value;
            stockCall("stock_update", { unit: r.id, fields: payload }, function () {
              state.slotEdit = null;
              delete state.revealed[r.id];
              state.slotMsg = { text: "<strong>Saved.</strong> " + esc(r.id) + " updated." };
            });
          });
          var cancel = document.createElement("button");
          cancel.className = "btn btn-sm";
          cancel.type = "button";
          cancel.textContent = "Cancel";
          cancel.addEventListener("click", function () {
            state.slotEdit = null; render();
          });
          wrap.appendChild(save);
          wrap.appendChild(cancel);
          cell.appendChild(wrap);
        }
        ed.appendChild(cell);
        tb.appendChild(ed);
      }
    });

    tbl.appendChild(tb);
    var scroll = document.createElement("div");
    scroll.className = "scroll-x";
    scroll.appendChild(tbl);
    list.appendChild(scroll);
    f.appendChild(list);
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
  var CUR_SYM = { usd: "$", eur: "€", gbp: "£" };
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
    division: "Rank boost", wins: "Net wins", placements: "Placements", coaching: "Coaching",
    account: "Account"
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

    var head = ["When", "Order", "Game", "Product", "Config", "Add-ons", "Booster", "Region", "Country", "Status", "Total"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) { return '<th class="' + (i === head.length - 1 ? "num" : "") + '">' + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.at)) + "</td>" +
        '<td><button class="link-btn" type="button" data-order="' + esc(r.order_id) + '">' + esc(r.order_id) + "</button>" +
          (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + esc(r.game) + "</td>" +
        "<td>" + esc(SERVICE_LABEL[r.service] || r.service) + '<span class="dim"> · ' + esc(r.mode || "") + "</span></td>" +
        '<td class="wrap-cell">' + esc(r.summary) + "</td>" +
        '<td class="wrap-cell">' + ((r.addons && r.addons.length)
          ? r.addons.map(function (n) { return '<span class="chip">' + esc(n) + "</span>"; }).join(" ")
          : '<span class="dim">—</span>') + "</td>" +
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
      var cols = ["when", "order_id", "game", "service", "mode", "config", "addons", "booster",
                  "region", "country", "currency", "status", "total", "seeded"];
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([new Date(r.at * 1000).toISOString(), r.order_id, r.game, r.service, r.mode,
                    r.summary, (r.addons || []).join(" | "), r.booster, r.region, r.country,
                    r.currency, r.status, r.total,
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
    boost.innerHTML = '<div class="card-hd"><h3>'
      + (o.service === "account" ? "The account" : "The boost") + '</h3></div>';
    var bf = [
      ["Game", o.game],
      ["Product", SERVICE_LABEL[o.service] || o.service]
    ];
    // An account has no queue. clean_order() defaults the column to "Piloted",
    // which on this product would state a fact about nobody playing anything.
    if (o.service !== "account") bf.push(["Queue", o.mode]);
    if (o.service === "division") {
      bf.push(["From rank", o.from_rank]);
      bf.push(["To rank", o.to_rank]);
    } else if (o.service === "wins" || o.service === "placements") {
      bf.push([o.unranked ? "Starting" : "Current rank", o.unranked ? "Unranked" : o.from_rank]);
      bf.push([o.service === "wins" ? "Net wins" : "Placement games", String(o.units || "—")]);
    } else if (o.service === "coaching") {
      bf.push(["Coach", o.coach || "—"]);
      bf.push(["Hours", String(o.hours || "—")]);
    } else if (o.service === "account") {
      // The listing id is what fulfilment acts on; the name is what makes the
      // row readable if the listing is later retired from data.py.
      bf.push(["Listing", o.account_name || "—"]);
      bf.push(["Listing id", o.account || "—"]);
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

  /* ── Mystery: the configurator's email capture and its live codes ───────
     The seventh store (see mystery.py), and the one whose rows are worth real
     money: each is an email next to a single-use token that takes 30% off for
     one hour. Fetched on demand like Carts and Accounts.

     The tab answers one question — does giving 30% away buy orders — so the
     funnel it draws is the honest one: cards opened → Apply pressed → paid.
     "Applied" is not a sale; only Redeemed is. */
  var BINGO_STATUS = { issued: "Live", redeemed: "Redeemed", expired: "Expired" };
  function bingoChip(s) {
    return '<span class="ostat ostat-' + esc(s) + '">' + esc(BINGO_STATUS[s] || s) + "</span>";
  }

  function loadMystery() {
    if (state.mysteryLoading) return;
    state.mysteryLoading = true;
    state.mysteryError = null;
    api({ action: "mystery", token: state.token, days: state.days }).then(function (res) {
      state.mysteryLoading = false;
      if (res.status === 200 && res.body.mystery) {
        state.mystery = res.body.mystery;
      } else if (res.status === 401) {
        toGate();
        return;
      } else if (res.status === 200) {
        state.mysteryError = "This server doesn't serve the mystery store yet — it is running an " +
          "older build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.mysteryError = "Couldn't load the mystery store — the server returned " + res.status + ".";
      }
      if (state.tab === "mystery") render();
    }).catch(function () {
      state.mysteryLoading = false;
      state.mysteryError = "Couldn't reach the server. Is it running?";
      if (state.tab === "mystery") render();
    });
  }

  function panelMystery() {
    var f = document.createDocumentFragment();
    var a = state.mystery;

    if (state.mysteryError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.mysteryError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm"; retry.type = "button"; retry.textContent = "Try again";
      retry.style.cssText = "margin:0 auto 16px;display:block";
      retry.addEventListener("click", function () { state.mysteryError = null; loadMystery(); render(); });
      er.appendChild(retry);
      f.appendChild(er);
      return f;
    }
    if (!a) {
      loadMystery();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading the mystery store…</p>';
      f.appendChild(wait);
      return f;
    }

    var pct = Math.round((a.pct || 0) * 100);

    // What this tab is. The margin note matters more here than anywhere else on
    // the console: this is a flat give-away, not a blended average, so the cost
    // of the programme is `Redeemed × pct`, and that is what has to be read.
    var intro = document.createElement("div");
    intro.className = "banner";
    intro.innerHTML = '<span class="ico">✉</span><div><strong>Mystery discount — the configurator’s ' +
      "email capture.</strong> Eight seconds after a visitor settles their target rank, the game page offers a " +
      "sealed card; the address buys the right to open it. <b>Every card pays " + pct + "%</b> — the pick is " +
      "theatre and the copy never claims odds. One card per inbox ever, live for " + num(a.ttl_mins) +
      " minutes, single-use, and it replaces the sitewide sale rather than stacking with it. " +
      "Model the cost as a flat " + pct + "% on every <em>Redeemed</em> row, not as an average.</div>";
    f.appendChild(intro);

    // The second mail. Kept as its own banner rather than folded into the one
    // above because it is a SECOND flat give-away on the same order, and the
    // two rates have to be read separately or the programme's cost is
    // understated by the difference on every chased row.
    var fpct = Math.round((a.followup_pct || 0) * 100);
    var chase = document.createElement("div");
    chase.className = "banner";
    chase.innerHTML = '<span class="ico">↻</span><div><strong>The sequence.</strong> Three mails: the ' +
      "code, a warning <b>" + num(a.warn_delay_mins) + " minutes</b> in that adds no offer (<b>" +
      num(a.warned) + " sent</b>), then — if the card lapses unbought — <b>one</b> chase raising it to <b>" +
      fpct + "%</b> for " + num(a.followup_ttl_mins / 60) + " hours. <b>Chased " + num(a.chased) + "</b> · bought " +
      num(a.chased_redeemed) + " (" + a.chase_rate + "%) · " + num(a.chase_due) +
      " waiting on the next sweep · " + num(a.unsubs) + " opted out. Those rows cost <b>" + fpct +
      "%</b>, not " + pct + "% — read the two separately.</div>";
    f.appendChild(chase);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes seeded rows.</strong> ' +
        num(a.synthetic) + " row(s) were written for testing. Clear the store before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Cards opened", num(a.total), undefined, "", true));
    kr.appendChild(kpi("Live right now", num(a.live)));
    kr.appendChild(kpi("Applied", num(a.applied) + " · " + a.apply_rate + "%"));
    kr.appendChild(kpi("Redeemed", num(a.redeemed) + " · " + a.redeem_rate + "%"));
    kr.appendChild(kpi("Bought", usd(a.redeemed_value)));
    kr.appendChild(kpi("Also took the guides mail", num(a.optins)));
    f.appendChild(kr);

    var statuses = (a.statuses || []).filter(function (s) { return s.count > 0; });
    var games = a.games || [];
    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(card({
      cls: "half", title: "By status",
      sub: "Live is inside its hour. Expired is an hour that ran out — the design, not a failure.",
      chart: function (w) {
        return barsH(w, {
          rows: statuses.map(function (s) { return { label: BINGO_STATUS[s.status] || s.status, value: s.count }; }),
          color: SERIES[0], alt: "Mystery codes by status"
        });
      },
      table: {
        head: ["Status", "Codes"], num: [1],
        rows: statuses.map(function (s) { return [BINGO_STATUS[s.status] || s.status, num(s.count)]; })
      }
    }));
    g.appendChild(card({
      cls: "half", title: "By game",
      sub: "Which ladders the modal captures on, and how many of those codes were paid for.",
      chart: function (w) {
        return barsH(w, {
          rows: games.map(function (r) { return { label: r.game, value: r.count }; }),
          color: SERIES[2], alt: "Mystery codes by game"
        });
      },
      table: {
        head: ["Game", "Codes", "Redeemed"], num: [1, 2],
        rows: games.map(function (r) { return [r.game, num(r.count), num(r.redeemed)]; })
      }
    }));
    f.appendChild(g);

    // Which sealed card people tap. It changes nothing about the discount — it
    // is here because C is pre-selected, so a flat A/B/C split would mean the
    // pick is engaging people and a 95% C would mean it is pure friction.
    var picks = a.picks || [];
    var countries = a.countries || [];
    var g2 = document.createElement("div");
    g2.className = "grid";
    g2.appendChild(card({
      cls: "half", title: "Which card they picked",
      sub: "C is pre-selected so the button is never dead. A flat split means the pick engages people; an all-C column means it is friction.",
      chart: function (w) {
        return barsH(w, {
          rows: picks.map(function (r) { return { label: "Card " + r.pick, value: r.count }; }),
          color: SERIES[3], alt: "Mystery card picked"
        });
      },
      table: {
        head: ["Card", "Picks"], num: [1],
        rows: picks.map(function (r) { return ["Card " + r.pick, num(r.count)]; })
      }
    }));
    g2.appendChild(card({
      cls: "half", title: "Where they opened it",
      sub: "Country is resolved server-side, never from an IP — see how each was inferred in the table.",
      chart: function (w) {
        return barsH(w, {
          rows: countries.slice(0, 10).map(function (c) {
            return { label: (flag(c.code) + " " + countryName(c.code)).trim(), value: c.count };
          }),
          color: SERIES[4], alt: "Mystery codes by country"
        });
      },
      table: {
        head: ["Country", "Codes"], num: [1],
        rows: countries.map(function (c) { return [countryName(c.code), num(c.count)]; })
      }
    }));
    f.appendChild(g2);

    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every card</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-mystery>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > recent.length ? ", first " + num(recent.length) + " of " + num(a.total) : "") +
      ". The value is re-priced from each stored configuration; the offer is what the " +
      pct + "% code brings it to. <b>Mailed</b> is whether the code actually left the server — " +
      "an unconfigured mailbox issues the code anyway and the modal drops its inbox line. " +
      "<b>Chased</b> marks a row the follow-up mail revived — those are priced at the " +
      "follow-up rate, so their offer figure is the lower one.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No cards opened in this period. They appear once a visitor sets a target rank on a ' +
        "game page, waits eight seconds and gives the modal an address.</p>");
      f.appendChild(el);
      return f;
    }

    var head = ["When", "Email", "Game", "Config", "Card", "Value", "Offer", "Mailed", "Status"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) { return '<th class="' + (i === 5 || i === 6 ? "num" : "") + '">' + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    recent.forEach(function (r) {
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.at)) + "</td>" +
        "<td>" + esc(r.email) + (r.optin ? ' <span class="chip">guides</span>' : "") +
          (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + esc(r.game) + '<span class="dim"> · ' + esc(r.mode || "") + "</span></td>" +
        '<td class="wrap-cell">' + esc(r.summary) + "</td>" +
        '<td class="dim">' + esc(r.pick) + "</td>" +
        '<td class="num">' + esc(usd(r.value)) + "</td>" +
        '<td class="num">' + (r.offer ? esc(usd(r.offer)) : '<span class="dim">—</span>') + "</td>" +
        "<td>" + (r.mailed ? "Yes" : '<span class="dim">No</span>') +
          (r.warned ? ' <span class="chip">warned</span>' : "") +
          (r.stage === "followup" ? ' <span class="chip">chased</span>' : "") +
          (r.nomail ? ' <span class="chip">opted out</span>' : "") + "</td>" +
        "<td>" + bingoChip(r.status) +
          (r.order_id ? ' <span class="dim">' + esc(r.order_id) + "</span>"
                      : (r.applied_at ? ' <span class="dim">applied</span>' : "")) + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-mystery]").addEventListener("click", function () {
      var cols = ["opened", "email", "token", "game", "config", "mode", "card", "value_usd",
                  "offer_usd", "mailed", "guides_optin", "status", "stage", "followed_up_at",
                  "warned", "opted_out", "expires", "applied_at",
                  "redeemed_at", "order_id", "country_code", "country", "country_source", "seeded"];
      var lines = [cols.join(",")];
      var iso = function (t) { return t ? new Date(t * 1000).toISOString() : ""; };
      recent.forEach(function (r) {
        lines.push([iso(r.at), r.email, r.token, r.game, r.summary, r.mode, r.pick, r.value,
                    r.offer, r.mailed ? "yes" : "no", r.optin ? "yes" : "no", r.status,
                    r.stage || "card", iso(r.followup_at), r.warned ? "yes" : "no",
                    r.nomail ? "yes" : "no",
                    iso(r.expires), iso(r.applied_at), iso(r.redeemed_at), r.order_id,
                    r.co, countryName(r.co), r.cosrc, r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(","));
      });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      link.download = "esb-mystery-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });

    f.appendChild(el);
    return f;
  }

  /* ── Mail discounts — every captured address, and what happened to it ────
     A read-only JOIN, not a store (see maillist.py). One row per person: the
     mails they were sent, what they did about them, and whether they converted.

     The two numbers that matter are deliberately separated. "Converted" over
     every captured address answers "is collecting emails worth it"; converted
     over the people we actually MAILED answers "are the mails worth it". A lead
     nobody could contact belongs in the first and must not drag the second. */
  var ML_STATUS = { converted: "Converted", open: "Offer live",
                    lapsed: "Not converted", unsubscribed: "Opted out" };
  var ML_MAIL = { code: "Code", warning: "Warning", chase: "Last chance", recovery: "Come back" };
  var ML_SOURCE = { mystery: "Mystery card", cart: "Abandoned cart",
                    guides: "Guides list", account: "Sign-up", order: "Paid order" };

  function mlChip(s) {
    var cls = { converted: "recovered", open: "mailed", lapsed: "pending", unsubscribed: "expired" }[s] || "pending";
    return '<span class="ostat ostat-' + cls + '">' + esc(ML_STATUS[s] || s) + "</span>";
  }

  /* ── Outbox: what we actually sent ──────────────────────────────────────
     Written by maillog.py from inside mailer.send(), the one SMTP seam on the
     site, so a message cannot go out without appearing here — including the
     ones that FAILED, because "we tried and the relay refused" and "we never
     tried" are different facts and only one of them is a bug. */
  function loadOutbox() {
    if (state.obLoading) return;
    state.obLoading = true;
    state.obError = null;
    api({ action: "outbox", token: state.token, days: state.days,
          kind: state.obKind }).then(function (res) {
      state.obLoading = false;
      if (res.status === 200 && res.body.outbox) {
        state.ob = res.body.outbox;
      } else if (res.status === 400 || res.status === 404) {
        state.obError = "This server doesn't serve the outbox yet — it is running an " +
          "older build. Restart it after deploying.";
      } else {
        state.obError = "Couldn't load the outbox — the server returned " + res.status + ".";
      }
      if (state.tab === "outbox") render();
    }).catch(function () {
      state.obLoading = false;
      state.obError = "Couldn't reach the server. Is it running?";
      if (state.tab === "outbox") render();
    });
  }

  function panelOutbox() {
    var f = document.createDocumentFragment();
    var a = state.ob;

    if (state.obError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.obError) + "</p>";
      f.appendChild(er);
      return f;
    }
    if (!a) {
      loadOutbox();
      var w = document.createElement("div");
      w.className = "card";
      w.innerHTML = '<p class="empty">Loading the outbox…</p>';
      f.appendChild(w);
      return f;
    }

    var intro = document.createElement("div");
    intro.className = "banner";
    intro.innerHTML = '<span class="ico">✉</span><div><strong>Everything the site has ' +
      "actually sent.</strong> Written from inside <code>mailer.send()</code>, the one SMTP " +
      "seam here, so no message can go out without landing in this list — order " +
      "confirmations, support tickets, applications, cart recovery and all three mystery " +
      "mails. <b>Failures are logged too</b>, so a refused or timed-out message shows as a " +
      "failure rather than simply being absent. Click any row to read exactly what that " +
      "person received. Keeps the last " + num(a.cap) + " messages.</div>";
    f.appendChild(intro);

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Messages sent", num(a.total), undefined, "", true));
    kr.appendChild(kpi("People mailed", num(a.recipients)));
    kr.appendChild(kpi("Failed", num(a.failed)));
    f.appendChild(kr);

    // Filter by kind — the question is almost always "what did the follow-up
    // send", not "what went out in total".
    var bar = document.createElement("div");
    bar.className = "card";
    var chips = '<div class="card-hd"><h3>By kind</h3></div><div class="chips">';
    chips += '<button class="chip' + (state.obKind ? "" : " on") + '" data-ob-kind="">All · ' +
      num(a.total) + "</button>";
    (a.kinds || []).forEach(function (k) {
      chips += '<button class="chip' + (state.obKind === k.kind ? " on" : "") +
        '" data-ob-kind="' + esc(k.kind) + '">' + esc(k.label) + " · " + num(k.count) +
        (k.failed ? " (" + num(k.failed) + " failed)" : "") + "</button>";
    });
    bar.innerHTML = chips + "</div>";
    f.appendChild(bar);

    var rows = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML = '<div class="card-hd"><h3>Messages</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-outbox>Export CSV</button></div>' +
      '<p class="card-sub">Newest first' +
      (a.total > rows.length ? ", first " + num(rows.length) + " of " + num(a.total) : "") +
      ". Times are UTC. Click a row to read the message.</p>";

    if (!rows.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">Nothing sent in this period.</p>');
      f.appendChild(el);
      return f;
    }

    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      ["When (UTC)", "Kind", "To", "Subject", "Result"]
        .map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    rows.forEach(function (r, i) {
      var when = new Date(r.at * 1000).toISOString().replace("T", " ").slice(0, 19);
      html += '<tr data-ob-row="' + i + '" style="cursor:pointer">' +
        '<td class="dim">' + esc(when) + "</td>" +
        "<td>" + esc(r.label) + "</td>" +
        "<td>" + esc(r.to) + "</td>" +
        '<td class="wrap-cell">' + esc(r.subject) + "</td>" +
        "<td>" + (r.ok ? '<span class="ostat ostat-issued">sent</span>'
                       : '<span class="ostat ostat-expired">failed</span>' +
                         (r.error ? ' <span class="dim">' + esc(r.error) + "</span>" : "")) +
        "</td></tr>";
      if (state.obOpen === i) {
        html += '<tr><td colspan="5"><pre class="pre-wrap" style="white-space:pre-wrap;' +
          'margin:0;padding:14px;background:rgba(255,255,255,.03);border-radius:8px;' +
          'font-size:12.5px;line-height:1.6">' + esc(r.text || "(no text part)") +
          "</pre></td></tr>";
      }
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelectorAll("[data-ob-row]").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var i = +tr.getAttribute("data-ob-row");
        state.obOpen = state.obOpen === i ? null : i;
        render();
      });
    });
    el.querySelector("[data-export-outbox]").addEventListener("click", function () {
      var cols = ["sent_at_utc", "kind", "to", "from", "subject", "result", "error", "body"];
      var lines = [cols.join(",")];
      rows.forEach(function (r) {
        lines.push([new Date(r.at * 1000).toISOString(), r.label, r.to, r.from,
                    r.subject, r.ok ? "sent" : "failed", r.error, r.text]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; })
          .join(","));
      });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      link.download = "esb-outbox-" + new Date().toISOString().slice(0, 10) + ".csv";
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });
    f.appendChild(el);

    bar.querySelectorAll("[data-ob-kind]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.obKind = b.getAttribute("data-ob-kind");
        state.ob = null; state.obOpen = null;
        loadOutbox(); render();
      });
    });
    return f;
  }

  function loadMailDiscounts() {
    if (state.mlLoading) return;
    state.mlLoading = true;
    state.mlError = null;
    api({ action: "maildiscounts", token: state.token, days: state.days }).then(function (res) {
      state.mlLoading = false;
      if (res.status === 200 && res.body.maildiscounts) {
        state.ml = res.body.maildiscounts;
      } else if (res.status === 401) { toGate(); return; }
      else if (res.status === 200) {
        state.mlError = "This server doesn't serve the mail list yet — it is running an older " +
          "build. Restart serve.py (the /api routes only reload on restart), then Refresh.";
      } else {
        state.mlError = "Couldn't load mail discounts — the server returned " + res.status + ".";
      }
      if (state.tab === "maildiscounts") render();
    }).catch(function () {
      state.mlLoading = false;
      state.mlError = "Couldn't reach the server. Is it running?";
      if (state.tab === "maildiscounts") render();
    });
  }

  function panelMailDiscounts() {
    var f = document.createDocumentFragment();
    var a = state.ml;

    if (state.mlError && !a) {
      var er = document.createElement("div");
      er.className = "card";
      er.innerHTML = '<p class="empty">' + esc(state.mlError) + "</p>";
      var retry = document.createElement("button");
      retry.className = "btn btn-sm"; retry.type = "button"; retry.textContent = "Try again";
      retry.style.cssText = "margin:0 auto 16px;display:block";
      retry.addEventListener("click", function () { state.mlError = null; loadMailDiscounts(); render(); });
      er.appendChild(retry); f.appendChild(er); return f;
    }
    if (!a) {
      loadMailDiscounts();
      var wait = document.createElement("div");
      wait.className = "card";
      wait.innerHTML = '<p class="empty">Loading mail discounts…</p>';
      f.appendChild(wait); return f;
    }

    var intro = document.createElement("div");
    intro.className = "banner";
    intro.innerHTML = '<span class="ico">✉</span><div><strong>Every address the site has captured, ' +
      'and what happened to it.</strong> One row per person, joined across the mystery cards, the ' +
      "abandoned carts, the guides list and the sign-ups — with the orders store deciding who actually " +
      "paid. Nothing is stored here: this is a read-only view over those stores, so a deletion request " +
      "is honoured in one place, not five. <b>Mailed</b> counts messages that left the server — there " +
      "is no open- or click-tracking on this site, and adding it is a consent decision, not a feature.</div>";
    f.appendChild(intro);

    if (a.synthetic > 0) {
      var syn = document.createElement("div");
      syn.className = "banner synthetic";
      syn.innerHTML = '<span class="ico">▲</span><div><strong>Includes seeded rows.</strong> ' +
        num(a.synthetic) + " address(es) were written for testing. Clear the stores before launch.</div>";
      f.appendChild(syn);
    }

    var kr = document.createElement("div");
    kr.className = "kpis";
    kr.appendChild(kpi("Addresses captured", num(a.total), undefined, "", true));
    kr.appendChild(kpi("Converted", num(a.converted) + " · " + a.conversion_rate + "%"));
    kr.appendChild(kpi("Of those we mailed", a.mailed_conversion_rate + "%",
                       undefined, num(a.mailed_people) + " mailed"));
    kr.appendChild(kpi("Mails sent", num(a.mails_sent),
                       undefined, a.mails_per_person + " per person"));
    kr.appendChild(kpi("Revenue from them", usd(a.revenue)));
    kr.appendChild(kpi("Still in play", usd(a.pipeline)));
    if (a.unsubscribed > 0) kr.appendChild(kpi("Opted out ⚠", num(a.unsubscribed)));
    f.appendChild(kr);

    var statuses = (a.statuses || []).filter(function (s) { return s.count > 0; });
    var kinds = a.mailkinds || [];
    var g = document.createElement("div");
    g.className = "grid";
    g.appendChild(card({
      cls: "half", title: "Converted or not",
      sub: "Converted means a paid order against that address. Offer live means a code of theirs still works.",
      chart: function (w) {
        return barsH(w, {
          rows: statuses.map(function (s) { return { label: ML_STATUS[s.status] || s.status, value: s.count }; }),
          color: SERIES[0], alt: "Addresses by status"
        });
      },
      table: {
        head: ["Status", "People"], num: [1],
        rows: statuses.map(function (s) { return [ML_STATUS[s.status] || s.status, num(s.count)]; })
      }
    }));
    g.appendChild(card({
      cls: "half", title: "Which mails went out",
      sub: "One capture can reach four messages: the code, a warning inside the hour, a last chance after it dies, and the cart's come-back.",
      chart: function (w) {
        return barsH(w, {
          rows: kinds.map(function (r) { return { label: ML_MAIL[r.kind] || r.kind, value: r.count }; }),
          color: SERIES[1], alt: "Mails by kind"
        });
      },
      table: {
        head: ["Mail", "Sent"], num: [1],
        rows: kinds.map(function (r) { return [ML_MAIL[r.kind] || r.kind, num(r.count)]; })
      }
    }));
    f.appendChild(g);

    var sources = (a.sources || []).filter(function (s) { return s.count > 0; });
    var countries = a.countries || [];
    var g2 = document.createElement("div");
    g2.className = "grid";
    g2.appendChild(card({
      cls: "half", title: "Where the address came from",
      sub: "One person can appear in more than one, so these need not sum to the total.",
      chart: function (w) {
        return barsH(w, {
          rows: sources.map(function (r) { return { label: ML_SOURCE[r.source] || r.source, value: r.count }; }),
          color: SERIES[2], alt: "Addresses by source"
        });
      },
      table: {
        head: ["Source", "People"], num: [1],
        rows: sources.map(function (r) { return [ML_SOURCE[r.source] || r.source, num(r.count)]; })
      }
    }));
    g2.appendChild(card({
      cls: "half", title: "Where they are",
      sub: "Resolved server-side, never from an IP.",
      chart: function (w) {
        return barsH(w, {
          rows: countries.slice(0, 10).map(function (c) {
            return { label: (flag(c.code) + " " + countryName(c.code)).trim(), value: c.count };
          }),
          color: SERIES[3], alt: "Addresses by country"
        });
      },
      table: {
        head: ["Country", "People"], num: [1],
        rows: countries.map(function (c) { return [countryName(c.code), num(c.count)]; })
      }
    }));
    f.appendChild(g2);

    var recent = a.recent || [];
    var el = document.createElement("div");
    el.className = "card";
    el.innerHTML =
      '<div class="card-hd"><h3>Every address</h3><span class="spacer"></span>' +
      '<button class="btn btn-sm" type="button" data-export-ml>Export CSV</button></div>' +
      '<p class="card-sub">Most recent activity first' +
      (a.total > recent.length ? ", first " + num(recent.length) + " of " + num(a.total) : "") +
      ". <b>Mails</b> lists what was sent and when; <b>Did</b> is what they did about it.</p>";

    if (!recent.length) {
      el.insertAdjacentHTML("beforeend",
        '<p class="empty">No addresses captured in this period.</p>');
      f.appendChild(el); return f;
    }

    var head = ["Last seen", "Email", "From", "Order", "Value", "Mails", "Did", "Status"];
    var html = '<div class="scroll-x"><table class="tbl"><thead><tr>' +
      head.map(function (h, i) { return '<th class="' + (i === 4 ? "num" : "") + '">' + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    recent.forEach(function (r) {
      var srcs = (r.sources || []).map(function (s) {
        return '<span class="chip">' + esc(ML_SOURCE[s] || s) + "</span>";
      }).join(" ");
      // The mail trail, in order, each with how long ago it went.
      var trail = (r.mails || []).length
        ? r.mails.map(function (m) {
            return '<span class="chip" title="' + esc(m.note || "") + '">' +
                   esc(ML_MAIL[m.kind] || m.kind) + " · " + esc(ago(m.at)) + "</span>";
          }).join(" ")
        : '<span class="dim">none</span>';
      // What they did about it, strongest signal first.
      var did = [];
      if (r.converted) did.push("paid" + (r.order_id ? " " + esc(r.order_id) : ""));
      if (r.applied) did.push("applied the code");
      if (r.pick) did.push("opened card " + esc(r.pick));
      if (r.optin) did.push("took the guides mail");
      if (r.unsubscribed) did.push("opted out");
      var offer = r.offer_live
        ? '<span class="chip">' + Math.round(r.offer_pct * 100) + "% live</span>" : "";
      html += "<tr>" +
        '<td class="dim">' + esc(ago(r.last_seen)) + "</td>" +
        "<td>" + esc(r.email) + (r.syn ? ' <span class="chip">seeded</span>' : "") + "</td>" +
        "<td>" + srcs + "</td>" +
        '<td class="wrap-cell">' + esc(r.summary || "—") +
          (r.game ? '<span class="dim"> · ' + esc(r.game) + "</span>" : "") + "</td>" +
        '<td class="num">' + (r.paid ? esc(usd(r.paid)) : (r.value ? esc(usd(r.value)) : '<span class="dim">—</span>')) + "</td>" +
        "<td>" + trail + "</td>" +
        '<td class="wrap-cell">' + (did.length ? did.join(", ") : '<span class="dim">nothing yet</span>') + "</td>" +
        "<td>" + mlChip(r.status) + " " + offer + "</td>" +
        "</tr>";
    });
    el.insertAdjacentHTML("beforeend", html + "</tbody></table></div>");

    el.querySelector("[data-export-ml]").addEventListener("click", function () {
      var cols = ["last_seen", "first_seen", "email", "sources", "status", "converted", "order_id",
                  "paid_usd", "order", "game", "value_usd", "offer_usd", "offer_pct_live",
                  "mails_sent", "mail_trail", "applied", "card_picked", "guides_optin",
                  "opted_out", "country", "seeded"];
      var iso = function (t) { return t ? new Date(t * 1000).toISOString() : ""; };
      var lines = [cols.join(",")];
      recent.forEach(function (r) {
        lines.push([iso(r.last_seen), iso(r.first_seen), r.email, (r.sources || []).join(" + "),
                    ML_STATUS[r.status] || r.status, r.converted ? "yes" : "no", r.order_id,
                    r.paid, r.summary, r.game, r.value, r.offer_value,
                    r.offer_live ? Math.round(r.offer_pct * 100) + "%" : "",
                    r.mail_count,
                    (r.mails || []).map(function (m) { return (ML_MAIL[m.kind] || m.kind) + "@" + iso(m.at); }).join(" | "),
                    r.applied ? iso(r.applied) : "", r.pick, r.optin ? "yes" : "no",
                    r.unsubscribed ? "yes" : "no", countryName(r.country), r.syn ? "yes" : "no"]
          .map(function (c) { return '"' + String(c == null ? "" : c).replace(/"/g, '""') + '"'; }).join(","));
      });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      link.download = "esb-mail-discounts-" + new Date().toISOString().slice(0, 10) + ".csv";
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
                  : r.service === "account" ? "account"
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
    stock: panelStock,
    mystery: panelMystery,
    maildiscounts: panelMailDiscounts,
    outbox: panelOutbox,
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
      if (state.tab === "stock") loadStock();
      if (state.tab === "mystery") loadMystery();
      if (state.tab === "maildiscounts") loadMailDiscounts();
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
