/* Esportsboost V3 — faithful vanilla port of the "Classical" dark-editorial handoff.
   The design prototype was authored in a proprietary <x-dc> runtime; per the handoff that
   runtime is NOT ported. This reimplements the same state model, pricing math and markup
   as a plain client-side SPA. Pricing is display-only here (a real deployment recomputes
   server-side — see the original site's serve.py / pricing.py). */
(function () {
  'use strict';

  // ── constants (from the handoff logic class) ──────────────────────────────
  var TIERS = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Ascendant', 'Immortal', 'Radiant'];
  var TP = [6, 8, 10, 13, 17, 23, 32, 48];
  var OPTS = [
    { k: 'duo', n: 'Duo queue', d: 'The booster joins your lobby. Your login never leaves your hands.', pct: 45 },
    { k: 'priority', n: 'Priority start', d: 'A booster is assigned within thirty minutes, day or night.', pct: 20 },
    { k: 'agent', n: 'Specific agent', d: 'Name the agent or role your booster is to play.', pct: 10 },
    { k: 'stream', n: 'Live stream', d: 'Watch every match privately, in real time, from your dashboard.', pct: 15 },
    { k: 'region', n: 'Region match', d: 'Booster plays on a VPN pinned to your own region and server.', pct: 5 }
  ];
  var CUR = { USD: { s: '$', r: 1 }, EUR: { s: '€', r: 0.92 }, GBP: { s: '£', r: 0.79 } };
  var NAV = [
    { id: 'home', n: 'Home' }, { id: 'game', n: 'Games' }, { id: 'coaching', n: 'Coaching' },
    { id: 'pricing', n: 'Pricing' }, { id: 'boosters', n: 'Boosters' },
    { id: 'dashboard', n: 'Track order' }, { id: 'about', n: 'About' }
  ];
  var MAPS = ['Ascent', 'Haven', 'Lotus', 'Split', 'Bind', 'Sunset', 'Icebox', 'Abyss'];

  var CELL_BASE = {
    padding: '11px 4px', fontFamily: 'var(--font-heading)', fontSize: '12.5px',
    letterSpacing: '.05em', textTransform: 'uppercase', background: 'transparent',
    cursor: 'pointer', borderRadius: 'var(--radius-md)', border: '1px solid',
    transition: 'border-color .15s, color .15s', width: '100%'
  };

  // props (design-time knobs; app config in production)
  var props = { currency: 'USD', showLiveOrders: true };

  // ── state ─────────────────────────────────────────────────────────────────
  var state = {
    screen: 'home', mode: 'division',
    fromTier: 2, fromDiv: 0, toTier: 3, toDiv: 1,
    wins: 5, placements: 5,
    opts: {}, coupon: '', terms: false, pay: 'card', paid: false, extra: 0
  };

  // ── helpers ───────────────────────────────────────────────────────────────
  function st(o) {
    var out = [];
    for (var k in o) {
      if (!o.hasOwnProperty(k)) continue;
      out.push(k.replace(/[A-Z]/g, function (m) { return '-' + m.toLowerCase(); }) + ':' + o[k]);
    }
    return out.join(';');
  }
  function assign(a, b) { for (var k in b) if (b.hasOwnProperty(k)) a[k] = b[k]; return a; }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function cur() { return CUR[props.currency] || CUR.USD; }
  function money(usd) {
    var c = cur();
    return c.s + (usd * c.r).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function moneyShort(usd) { return cur().s + Math.round(usd * cur().r); }
  function idx(t, d) { return t >= 8 ? 24 : t * 3 + d; }
  function label(t, d) { return t >= 8 ? 'Radiant' : TIERS[t] + ' ' + (3 - d); }
  function step(i) { return i === 23 ? 120 : TP[Math.floor(i / 3)]; }

  function base() {
    var s = state;
    if (s.mode === 'wins') return s.wins * (9 + s.fromTier * 3.4);
    if (s.mode === 'placement') return s.placements * (11 + s.fromTier * 3.8);
    var a = idx(s.fromTier, s.fromDiv), b = idx(s.toTier, s.toDiv);
    if (b <= a) return 0;
    var sum = 0;
    for (var i = a; i < b; i++) sum += step(i);
    return sum;
  }
  function mult() {
    var m = 1;
    OPTS.forEach(function (o) { if (state.opts[o.k]) m += o.pct / 100; });
    return m;
  }
  function discountRate() { return state.coupon.trim().toUpperCase() === 'CLIMB10' ? 0.1 : 0; }
  function totalUsd() { return base() * mult() * (1 - discountRate()); }
  function units() {
    var s = state;
    if (s.mode === 'wins') return s.wins;
    if (s.mode === 'placement') return s.placements;
    return Math.max(0, idx(s.toTier, s.toDiv) - idx(s.fromTier, s.fromDiv));
  }
  function etaHours() {
    var h = units() * (state.mode === 'division' ? 3.4 : 1.5) + 2;
    return state.opts.priority ? h * 0.72 : h;
  }
  function etaLabel() {
    var h = etaHours();
    if (!units()) return '—';
    if (h < 24) return Math.round(h) + ' hrs';
    return Math.round(h / 24 * 10) / 10 + ' days';
  }
  function route() {
    var s = state;
    if (s.mode === 'wins') return s.wins + ' net wins at ' + label(s.fromTier, s.fromDiv);
    if (s.mode === 'placement') return s.placements + ' placement matches';
    return label(s.fromTier, s.fromDiv) + ' → ' + label(s.toTier, s.toDiv);
  }
  function cell(sel) {
    return sel
      ? assign(assign({}, CELL_BASE), { borderColor: 'var(--color-accent)', color: 'var(--color-accent-300)', background: 'rgba(182,130,53,.12)' })
      : assign(assign({}, CELL_BASE), { borderColor: 'rgba(243,242,242,.18)', color: 'rgba(243,242,242,.66)' });
  }
  function modeStyle(sel) {
    return {
      padding: '20px 18px', textAlign: 'left', cursor: 'pointer', border: 'none', width: '100%',
      fontFamily: 'var(--font-body)',
      background: sel ? 'rgba(182,130,53,.12)' : '#171613',
      color: sel ? 'var(--color-accent-300)' : 'rgba(243,242,242,.66)',
      boxShadow: sel ? 'inset 0 0 0 1px var(--color-accent)' : 'none'
    };
  }

  // ── small markup helpers ────────────────────────────────────────────────
  var CTA_NOTCH = 'clip-path:polygon(0 0,100% 0,100% 68%,calc(100% - 11px) 100%,0 100%)';
  // ids that have generated key art in assets/keyart/ (see gen_art.py)
  var ART = { 'eb-hero': 1, 'eb-g1': 1, 'eb-g2': 1, 'eb-g3': 1, 'eb-g4': 1, 'eb-g5': 1, 'eb-g6': 1, 'eb-val-banner': 1, 'eb-coach': 1 };
  function slot(id, ph) {
    if (ART[id]) {
      return '<img class="eb-art" src="assets/keyart/' + esc(id) + '.svg" alt="' + esc(ph) + '" ' +
        'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block" ' +
        'onerror="this.className=\'eb-slot\';this.removeAttribute(\'src\')">';
    }
    return '<div class="eb-slot" data-slot="' + esc(id) + '">' + esc(ph) + '</div>';
  }
  function primaryBtn(navOrAttr, text, extra) {
    return '<button type="button" class="btn btn-primary" ' + navOrAttr +
      ' style="border-color:var(--color-accent);color:var(--color-accent-400);' + (extra || '') + '">' + esc(text) + '</button>';
  }

  // ── header + footer ───────────────────────────────────────────────────────
  function header() {
    var links = NAV.map(function (n) {
      var active = state.screen === n.id;
      var s = 'font-size:13px;letter-spacing:.04em;padding-bottom:3px;color:' +
        (active ? 'var(--color-accent-400)' : 'rgba(243,242,242,.68)') +
        ';border-bottom:1px solid ' + (active ? 'var(--color-accent)' : 'transparent');
      return '<a href="#" data-nav="' + n.id + '" style="' + s + '">' + esc(n.n) + '</a>';
    }).join('');
    return '' +
      '<header style="position:sticky;top:0;z-index:40;background:rgba(23,22,19,.94);backdrop-filter:blur(8px);border-bottom:1px solid rgba(243,242,242,.13)">' +
      '<div style="display:flex;align-items:center;gap:34px;max-width:1200px;margin:0 auto;padding:15px 34px">' +
      '<a href="#" data-nav="home" style="display:flex;align-items:center;gap:11px;margin-right:auto;color:#f3f2f2">' +
      '<span style="display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:13px;letter-spacing:.02em;clip-path:polygon(0 0,100% 0,100% 72%,72% 100%,0 100%)">EB</span>' +
      '<span style="font-family:var(--font-heading);font-size:19px;letter-spacing:.16em;text-transform:uppercase;font-weight:400">Esports<span style="color:var(--color-accent-400)">boost</span></span>' +
      '</a>' +
      '<nav class="eb-nav-links" style="display:flex;align-items:center;gap:26px">' + links + '</nav>' +
      '<button type="button" class="btn btn-primary" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);letter-spacing:.1em;text-transform:uppercase;font-size:12px;padding:9px 16px;clip-path:polygon(0 0,100% 0,100% 68%,calc(100% - 9px) 100%,0 100%)">Build your boost</button>' +
      '</div></header>';
  }

  function footer() {
    var cols = [
      { h: 'Games', links: ['Valorant', 'League of Legends', 'Counter-Strike 2', 'Apex Legends', 'Overwatch 2', 'Rocket League'], go: 'game' },
      { h: 'Services', links: ['Division boost', 'Net wins', 'Placements', 'Coaching', 'Season pass'], go: 'pricing' },
      { h: 'Support', links: ['Track an order', 'Refund policy', 'Account safety', 'Contact support', 'Terms of service'], go: 'dashboard' }
    ].map(function (c) {
      var ls = c.links.map(function (l) {
        return '<a href="#" data-nav="' + c.go + '" style="font-size:13px;color:rgba(243,242,242,.62)" onmouseover="this.style.color=\'var(--color-accent-400)\'" onmouseout="this.style.color=\'rgba(243,242,242,.62)\'">' + esc(l) + '</a>';
      }).join('');
      return '<div><div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:16px">' + esc(c.h) + '</div>' +
        '<div style="display:flex;flex-direction:column;gap:10px">' + ls + '</div></div>';
    }).join('');
    return '' +
      '<footer style="border-top:1px solid rgba(243,242,242,.13);background:#131210">' +
      '<div class="eb-grid-footer" style="max-width:1200px;margin:0 auto;padding:60px 34px 30px;display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1.3fr);gap:34px">' +
      '<div>' +
      '<div style="display:flex;align-items:center;gap:11px;margin-bottom:16px">' +
      '<span style="display:grid;place-items:center;width:28px;height:28px;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:12px;clip-path:polygon(0 0,100% 0,100% 72%,72% 100%,0 100%)">EB</span>' +
      '<span style="font-family:var(--font-heading);font-size:17px;letter-spacing:.16em;text-transform:uppercase">Esports<span style="color:var(--color-accent-400)">boost</span></span></div>' +
      '<p style="font-size:12.5px;line-height:1.8;color:rgba(243,242,242,.5);margin:0 0 18px;max-width:34ch">Rank boosting, net wins, placements and coaching across six titles. Verified boosters, fixed quotes, refundable orders.</p>' +
      '<div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--color-accent-400)">4.8 / 5 · Trustpilot</div></div>' +
      cols +
      '<div><div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:16px">Order updates</div>' +
      '<p style="font-size:12.5px;line-height:1.7;color:rgba(243,242,242,.5);margin:0 0 14px">Drops, rate changes and seasonal resets. One email a month.</p>' +
      '<div style="display:flex;gap:9px"><input class="input" placeholder="you@mail.com" style="color:#f3f2f2;border-color:rgba(243,242,242,.24)">' +
      '<button type="button" class="btn btn-primary" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:0 15px">Join</button></div></div>' +
      '</div>' +
      '<div style="max-width:1200px;margin:0 auto;padding:22px 34px 40px;border-top:1px solid rgba(243,242,242,.1);display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:rgba(243,242,242,.38)">' +
      '<span>© 2026 eSports Boost — all rights reserved</span>' +
      '<span>All game names and trademarks are the property of their respective owners</span>' +
      '</div></footer>';
  }

  // ── HOME ───────────────────────────────────────────────────────────────────
  function home() {
    var heroStats = [
      { v: '4.8', k: 'Trustpilot' }, { v: '1,142', k: 'Boosters' },
      { v: '04:11', k: 'Avg. pickup' }, { v: '0', k: 'Bans on record' }
    ].map(function (s) {
      return '<div style="background:#171613;padding:15px 14px">' +
        '<div style="font-family:var(--font-heading);font-size:27px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + esc(s.v) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-top:7px">' + esc(s.k) + '</div></div>';
    }).join('');

    var trust = [
      { h: '4.8 / 5 on Trustpilot', d: '11,204 verified reviews across ten years of trading.' },
      { h: 'Money back, no argument', d: 'Miss the quoted estimate and the refund is automatic.' },
      { h: 'VPN and region matched', d: 'Your account never logs in from a country it has not seen.' },
      { h: 'Support answers in minutes', d: 'Staffed around the clock in English, German and Portuguese.' }
    ].map(function (t) {
      return '<div style="background:#171613;padding:26px 30px">' +
        '<div style="font-family:var(--font-heading);font-size:19px;color:#f3f2f2;margin-bottom:5px">' + esc(t.h) + '</div>' +
        '<div style="font-size:12.5px;line-height:1.6;color:rgba(243,242,242,.55)">' + esc(t.d) + '</div></div>';
    }).join('');

    var games = [
      { n: 'Valorant', d: 'Iron to Radiant, every act. Agent requests honoured.', from: 6, tags: ['Division', 'Wins', 'Placements'], slot: 'eb-g1' },
      { n: 'League of Legends', d: 'Solo/Duo and Flex across all five regions.', from: 5, tags: ['Division', 'Wins', 'Coaching'], slot: 'eb-g2' },
      { n: 'Counter-Strike 2', d: 'Premier rating, Faceit levels and wingman.', from: 7, tags: ['Rating', 'Faceit', 'Wins'], slot: 'eb-g3' },
      { n: 'Apex Legends', d: 'Ranked splits, badges and Predator pushes.', from: 9, tags: ['Division', 'Badges'], slot: 'eb-g4' },
      { n: 'Overwatch 2', d: 'Role queue and open queue, all three roles.', from: 6, tags: ['Division', 'Placements'], slot: 'eb-g5' },
      { n: 'Rocket League', d: 'Doubles, standard and tournament ranks.', from: 5, tags: ['Division', 'Tournaments'], slot: 'eb-g6' }
    ].map(function (g) {
      var tags = g.tags.map(function (tg) {
        return '<span style="font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:4px 9px;border:1px solid rgba(243,242,242,.18);color:rgba(243,242,242,.6)">' + esc(tg) + '</span>';
      }).join('');
      return '<a href="#" data-nav="game" class="eb-card" style="display:block;border:1px solid rgba(243,242,242,.12);background:#1b1a17;color:#f3f2f2">' +
        '<div style="height:168px;position:relative;border-bottom:1px solid rgba(243,242,242,.1)">' + slot(g.slot, 'Key art') + '</div>' +
        '<div style="padding:17px 19px 19px">' +
        '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px">' +
        '<span style="font-family:var(--font-heading);font-size:21px;letter-spacing:-.01em">' + esc(g.n) + '</span>' +
        '<span style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums">From ' + moneyShort(g.from) + '</span></div>' +
        '<div style="font-size:12.5px;line-height:1.65;color:rgba(243,242,242,.52);margin-top:8px">' + esc(g.d) + '</div>' +
        '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:14px">' + tags + '</div></div></a>';
    }).join('');

    var featured = [
      { game: 'Valorant', title: 'Gold to Platinum', price: 74, stats: [{ v: '06', k: 'Div' }, { v: '18', k: 'Hrs' }, { v: '71', k: 'Win %' }, { v: '340', k: 'Pool' }], rows: [{ i: '01', n: 'Kryos', v: '92%' }, { i: '02', n: 'Nevermore', v: '89%' }, { i: '03', n: 'Talis', v: '87%' }] },
      { game: 'League of Legends', title: 'Emerald climb', price: 96, stats: [{ v: '08', k: 'Div' }, { v: '26', k: 'Hrs' }, { v: '68', k: 'Win %' }, { v: '412', k: 'Pool' }], rows: [{ i: '01', n: 'Sablier', v: '94%' }, { i: '02', n: 'Orinth', v: '90%' }, { i: '03', n: 'Vell', v: '86%' }] },
      { game: 'Counter-Strike 2', title: 'Premier 20k', price: 128, stats: [{ v: '4k', k: 'Rating' }, { v: '31', k: 'Hrs' }, { v: '74', k: 'Win %' }, { v: '188', k: 'Pool' }], rows: [{ i: '01', n: 'Halvard', v: '95%' }, { i: '02', n: 'Rask', v: '91%' }, { i: '03', n: 'Juno', v: '88%' }] }
    ].map(function (f) {
      var stats = f.stats.map(function (stt) {
        return '<div style="background:#1b1a17;padding:12px 6px;text-align:center">' +
          '<div style="font-family:var(--font-heading);font-size:17px;font-variant-numeric:tabular-nums;color:#f3f2f2">' + esc(stt.v) + '</div>' +
          '<div style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42);margin-top:4px">' + esc(stt.k) + '</div></div>';
      }).join('');
      var rows = f.rows.map(function (r) {
        return '<div style="display:flex;align-items:center;gap:11px;padding:10px 0;border-bottom:1px solid rgba(243,242,242,.09)">' +
          '<span style="display:grid;place-items:center;width:26px;height:26px;flex:none;border:1px solid rgba(243,242,242,.2);font-family:var(--font-heading);font-size:11px;color:rgba(243,242,242,.7)">' + esc(r.i) + '</span>' +
          '<span style="font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:rgba(243,242,242,.72);margin-right:auto">' + esc(r.n) + '</span>' +
          '<span style="font-size:12px;font-variant-numeric:tabular-nums;color:var(--color-accent-400)">' + esc(r.v) + '</span></div>';
      }).join('');
      return '<div style="border:1px solid rgba(243,242,242,.13);background:#1b1a17;position:relative">' +
        '<div style="position:absolute;top:0;left:0;background:var(--color-accent-900);border-right:1px solid var(--color-accent);border-bottom:1px solid var(--color-accent);padding:7px 20px 7px 14px;font-family:var(--font-heading);font-size:16px;font-variant-numeric:tabular-nums;color:var(--color-accent-300);clip-path:polygon(0 0,100% 0,calc(100% - 13px) 100%,0 100%)">' + moneyShort(f.price) + '</div>' +
        '<div style="padding:58px 22px 22px;text-align:center;border-bottom:1px solid rgba(243,242,242,.1)">' +
        '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45)">' + esc(f.game) + '</div>' +
        '<div style="font-family:var(--font-heading);font-size:26px;letter-spacing:.02em;text-transform:uppercase;color:var(--color-accent-300);margin-top:9px">' + esc(f.title) + '</div>' +
        '<div style="width:34px;height:1px;background:var(--color-accent);margin:15px auto 0"></div></div>' +
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(243,242,242,.1)">' + stats + '</div>' +
        '<div style="padding:18px 22px 8px">' + rows + '</div>' +
        '<div style="padding:12px 22px 22px"><button type="button" class="btn btn-primary btn-block" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:12px;letter-spacing:.12em;text-transform:uppercase;padding:12px">Configure</button></div></div>';
    }).join('');

    var live = [
      { mono: 'KR', booster: 'Kryos', game: 'Valorant', route: 'Gold 2 → Platinum 1', won: '7 / 9', left: '2 games', w: '78%' },
      { mono: 'SB', booster: 'Sablier', game: 'League of Legends', route: 'Plat IV → Emerald II', won: '12 / 18', left: '6 games', w: '66%' },
      { mono: 'HL', booster: 'Halvard', game: 'Counter-Strike 2', route: '14,200 → 20,000 Premier', won: '21 / 30', left: '9 games', w: '70%' },
      { mono: 'JN', booster: 'Juno', game: 'Overwatch 2', route: 'Diamond 3 → Master 5', won: '4 / 11', left: '7 games', w: '36%' }
    ].map(function (o) {
      return '<div class="eb-row" style="display:grid;grid-template-columns:180px minmax(0,1fr) 110px 120px 110px;gap:22px;align-items:center;border:1px solid rgba(243,242,242,.12);background:#1b1a17;padding:16px 20px">' +
        '<div style="display:flex;align-items:center;gap:13px">' +
        '<span style="display:grid;place-items:center;width:38px;height:38px;flex:none;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:13px;clip-path:polygon(0 0,100% 0,100% 70%,70% 100%,0 100%)">' + esc(o.mono) + '</span>' +
        '<div><div style="font-family:var(--font-heading);font-size:16px">' + esc(o.booster) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">' + esc(o.game) + '</div></div></div>' +
        '<div><div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:rgba(243,242,242,.72);margin-bottom:9px">' + esc(o.route) + '</div>' +
        '<div style="height:2px;background:rgba(243,242,242,.14)"><div style="height:2px;width:' + o.w + ';background:var(--color-accent)"></div></div></div>' +
        '<div><div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">Won</div>' +
        '<div style="font-family:var(--font-heading);font-size:16px;font-variant-numeric:tabular-nums;color:var(--color-accent-300);margin-top:3px">' + esc(o.won) + '</div></div>' +
        '<div><div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">Remaining</div>' +
        '<div style="font-family:var(--font-heading);font-size:16px;font-variant-numeric:tabular-nums;color:#f3f2f2;margin-top:3px">' + esc(o.left) + '</div></div>' +
        '<button type="button" class="btn btn-secondary" data-nav="dashboard" style="border-color:rgba(243,242,242,.22);color:rgba(243,242,242,.78);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:9px 12px">Watch</button></div>';
    }).join('');
    var liveSection = props.showLiveOrders === false ? '' :
      '<section style="border-top:1px solid rgba(243,242,242,.13)">' +
      '<div style="max-width:1200px;margin:0 auto;padding:74px 34px">' +
      '<div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px">' +
      '<div><div style="display:flex;align-items:center;gap:10px;font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">' +
      '<span style="display:inline-block;width:7px;height:7px;background:var(--color-accent);animation:eb-pulse 1.6s ease-in-out infinite"></span>Running now</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;letter-spacing:-.02em;margin:0;color:#f3f2f2">Live orders</h2></div>' +
      '<a href="#" data-nav="dashboard" style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;border-bottom:1px solid var(--color-accent);padding-bottom:3px">Open the board</a></div>' +
      '<div style="display:flex;flex-direction:column;gap:12px">' + live + '</div></div></section>';

    var safety = [
      { i: '01', h: 'Region-pinned VPN', d: 'Every session runs from a residential address in your own region, matched to your last login.' },
      { i: '02', h: 'Offline mode by default', d: 'Friends see nothing. No profile changes, no messages sent, no games shared.' },
      { i: '03', h: 'Credentials in the vault', d: 'Logins are entered in the encrypted order room, used once, and purged on delivery.' },
      { i: '04', h: 'Duo instead, if you like', d: 'Play your own games with the booster on your team and hand over nothing at all.' },
      { i: '05', h: 'Contracted boosters', d: 'Legal identity verified, contract signed, payouts withheld against conduct.' },
      { i: '06', h: 'No third parties', d: 'We do not resell orders to freelancers. The roster on this site is the roster that plays.' }
    ].map(function (s) {
      return '<div style="background:#131210;padding:24px 22px">' +
        '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums;margin-bottom:12px">' + esc(s.i) + '</div>' +
        '<div style="font-family:var(--font-heading);font-size:19px;margin-bottom:8px;color:#f3f2f2">' + esc(s.h) + '</div>' +
        '<div style="font-size:12.5px;line-height:1.7;color:rgba(243,242,242,.55)">' + esc(s.d) + '</div></div>';
    }).join('');

    var reviews = [
      { stars: '★★★★★', q: 'Quoted eighteen hours, finished in eleven, and the log showed every game. Nothing to argue about.', by: 'Marek D. — Platinum push, Valorant' },
      { stars: '★★★★★', q: 'Duo queue was the whole reason I ordered. Never gave up my login and still climbed two divisions.', by: 'Ivy R. — Emerald climb, League' },
      { stars: '★★★★★', q: 'Booster went quiet for a day, support refunded the unplayed part before I asked twice.', by: 'Tobias K. — Premier rating, CS2' }
    ].map(function (r) {
      return '<figure style="background:#171613;padding:30px 26px;margin:0">' +
        '<div style="letter-spacing:.28em;color:var(--color-accent);font-size:13px;margin-bottom:16px">' + r.stars + '</div>' +
        '<blockquote style="font-family:var(--font-heading);font-size:20px;line-height:1.42;margin:0 0 18px;color:#f3f2f2">' + esc(r.q) + '</blockquote>' +
        '<figcaption style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.45);margin:0">' + esc(r.by) + '</figcaption></figure>';
    }).join('');

    var faq = homeFaq().map(function (f) {
      return '<div style="border-top:1px solid rgba(243,242,242,.13);padding:22px 0">' +
        '<div style="display:grid;grid-template-columns:34px 1fr;gap:18px;align-items:start">' +
        '<span style="font-size:11px;letter-spacing:.1em;color:var(--color-accent-400);font-variant-numeric:tabular-nums;padding-top:4px">' + esc(f.i) + '</span>' +
        '<div><div style="font-family:var(--font-heading);font-size:22px;margin-bottom:9px;color:#f3f2f2">' + esc(f.q) + '</div>' +
        '<p style="font-size:14px;line-height:1.8;color:rgba(243,242,242,.6);margin:0;text-align:justify;hyphens:auto">' + esc(f.a) + '</p></div></div></div>';
    }).join('');

    return '<main>' +
      // hero
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);position:relative">' +
      '<div class="eb-2col" style="display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:56px;align-items:center;max-width:1200px;margin:0 auto;padding:86px 34px 78px">' +
      '<div>' +
      '<div style="display:flex;align-items:center;gap:12px;font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums;margin-bottom:26px">' +
      '<span style="display:inline-block;width:7px;height:7px;background:var(--color-accent);animation:eb-pulse 2s ease-in-out infinite"></span>Est. 2016 · <span style="font-variant-numeric:tabular-nums">214,860</span> orders delivered</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:78px;line-height:.98;letter-spacing:-.025em;margin:0 0 24px;color:#f3f2f2">Climb without<br>the grind.</h1>' +
      '<p style="font-size:16px;line-height:1.8;color:rgba(243,242,242,.68);max-width:44ch;margin:0 0 34px">Verified top-500 players take your account exactly as far as you tell them to. Fixed price before you pay, live tracking while it runs, and a full refund if it stalls.</p>' +
      '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:40px">' +
      '<button type="button" class="btn btn-primary" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:13px;letter-spacing:.12em;text-transform:uppercase;padding:14px 26px;' + CTA_NOTCH + '">Build your boost</button>' +
      '<button type="button" class="btn btn-secondary" data-nav="dashboard" style="border-color:rgba(243,242,242,.24);color:rgba(243,242,242,.82);font-size:13px;letter-spacing:.12em;text-transform:uppercase;padding:14px 26px">Track an order</button></div>' +
      '<div class="eb-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13)">' + heroStats + '</div></div>' +
      '<div><div class="plate" style="border-color:#22211d;outline-color:rgba(243,242,242,.16);position:relative;height:392px">' + slot('eb-hero', 'Hero art') + '</div>' +
      '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:11px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">' +
      '<span>Plate I — Immortal 3, Frankfurt</span><span style="font-variant-numeric:tabular-nums">04:11 avg. start</span></div></div>' +
      '</div></section>' +
      // trust strip
      '<section style="border-bottom:1px solid rgba(243,242,242,.13)">' +
      '<div class="eb-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(243,242,242,.13);max-width:1200px;margin:0 auto">' + trust + '</div></section>' +
      // catalogue
      '<section style="max-width:1200px;margin:0 auto;padding:74px 34px">' +
      '<div class="eb-2col" style="display:flex;justify-content:space-between;align-items:flex-end;gap:30px;margin-bottom:38px">' +
      '<div><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">Catalogue</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;line-height:1.03;letter-spacing:-.02em;margin:0;color:#f3f2f2">Pick your game</h2></div>' +
      '<p style="font-size:14px;line-height:1.75;color:rgba(243,242,242,.6);max-width:38ch;margin:0;text-align:right">Six titles, one standard. Every booster on every roster sits in the top half-percent of their region.</p></div>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px">' + games + '</div></section>' +
      // most ordered
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:74px 34px">' +
      '<div style="text-align:center;margin-bottom:44px"><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">This week</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;letter-spacing:-.02em;margin:0;color:#f3f2f2">Most ordered services</h2></div>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:22px">' + featured + '</div></div></section>' +
      liveSection +
      // safety
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:74px 34px">' +
      '<div class="eb-2col" style="display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:56px;align-items:start">' +
      '<div><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">Safety</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;line-height:1.04;letter-spacing:-.02em;margin:0 0 20px;color:#f3f2f2">Your account, untouched</h2>' +
      '<p style="font-size:14.5px;line-height:1.85;color:rgba(243,242,242,.62);margin:0 0 12px;text-align:justify;hyphens:auto">Ten years of orders and no ban attributable to our process. That record is the product. Everything below is how we keep it.</p>' +
      '<p style="font-size:14.5px;line-height:1.85;color:rgba(243,242,242,.62);margin:0;text-align:justify;hyphens:auto">Prefer not to hand over a login at all? Duo queue puts the booster in your lobby instead of your account, and it is available on every service we sell.</p></div>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13)">' + safety + '</div></div></div></section>' +
      // reviews
      '<section style="border-top:1px solid rgba(243,242,242,.13)"><div style="max-width:1200px;margin:0 auto;padding:74px 34px">' +
      '<div style="text-align:center;margin-bottom:42px"><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">4.8 / 5 on Trustpilot · 11,204 reviews</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;letter-spacing:-.02em;margin:0;color:#f3f2f2">What buyers say</h2></div>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13)">' + reviews + '</div></div></section>' +
      // faq
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:920px;margin:0 auto;padding:74px 34px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">Questions</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:46px;letter-spacing:-.02em;margin:0 0 32px;color:#f3f2f2">Before you order</h2>' + faq + '</div></section>' +
      // closing cta
      '<section style="border-top:1px solid rgba(243,242,242,.13)"><div style="max-width:1200px;margin:0 auto;padding:88px 34px;text-align:center">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:58px;line-height:1.05;letter-spacing:-.025em;margin:0 0 18px;color:#f3f2f2">Name the rank.<br>We\'ll quote it in one screen.</h2>' +
      '<p style="font-size:15px;line-height:1.8;color:rgba(243,242,242,.62);max-width:52ch;margin:0 auto 32px">No account details needed to see a price.</p>' +
      '<button type="button" class="btn btn-primary" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:13px;letter-spacing:.14em;text-transform:uppercase;padding:15px 34px;clip-path:polygon(0 0,100% 0,100% 68%,calc(100% - 12px) 100%,0 100%)">Build your boost</button></div></section>' +
      '</main>';
  }

  function homeFaq() {
    return [
      { i: '01', q: 'Can my account be banned for this?', a: 'Riot and Valve police account sharing, so the honest answer is that no service can promise immunity. What we can promise is process: region-pinned residential VPNs, offline mode, human play patterns, no scripts, and no account touched by more than one booster. Ten years and 214,860 orders have produced no ban attributable to that process. If you want the risk at zero, order duo queue instead — nobody logs in but you.' },
      { i: '02', q: 'What happens if the booster stalls?', a: 'Every order carries the estimate you were quoted. If a booster goes quiet past it, support reassigns the order within the hour at no extra cost, or refunds the unplayed portion — your choice, and you do not have to chase it. Refunds go back to the original payment method inside three working days.' },
      { i: '03', q: 'Do you keep my login?', a: 'No. Credentials are entered into the encrypted order room, are visible only to the assigned booster, and are deleted when the order closes. We will never ask for them by email, Discord or chat, and any message that does is not from us.' },
      { i: '04', q: 'Will the price change after I order?', a: 'No. The configurator adds up the published rate card and that figure is the figure you pay. There is no service fee, no currency surcharge and nothing added at the payment step.' },
      { i: '05', q: 'Can I keep playing while the order runs?', a: 'On a piloted order, not on the same queue — concurrent logins end the session. Duo orders are the opposite: you play every game yourself. Either way you can pause a running order from the dashboard whenever you want the account back.' }
    ];
  }

  // ── GAME PAGE ──────────────────────────────────────────────────────────────
  function game() {
    var valStats = [
      { v: '340', k: 'Valorant boosters' }, { v: '04:11', k: 'Avg. pickup' },
      { v: '71%', k: 'Average win rate' }, { v: '4.8', k: 'Rated by buyers' }
    ].map(function (s) {
      return '<div style="background:#171613;padding:24px 26px">' +
        '<div style="font-family:var(--font-heading);font-size:30px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + esc(s.v) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-top:8px">' + esc(s.k) + '</div></div>';
    }).join('');

    var services = [
      { k: 'Most ordered', h: 'Division boost', d: 'Pick where you are and where you want to be. We play until it is done.', p: 6, go: 'order' },
      { k: 'Pay per game', h: 'Net wins', d: 'Buy a number of wins instead of a rank. Losses along the way are replayed free.', p: 9, go: 'order' },
      { k: 'Season start', h: 'Placements', d: 'Five placement matches played to the highest rank your MMR allows.', p: 11, go: 'order' },
      { k: 'Learn it', h: 'Coaching', d: 'Sixty minutes with a Radiant coach, VOD review and a written plan.', p: 28, go: 'coaching' }
    ].map(function (s) {
      return '<div style="border:1px solid rgba(243,242,242,.13);background:#1b1a17;padding:24px 22px;display:flex;flex-direction:column;gap:12px">' +
        '<div style="font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--color-accent-400)">' + esc(s.k) + '</div>' +
        '<div style="font-family:var(--font-heading);font-size:23px;color:#f3f2f2">' + esc(s.h) + '</div>' +
        '<p style="font-size:12.5px;line-height:1.7;color:rgba(243,242,242,.56);margin:0;flex:1">' + esc(s.d) + '</p>' +
        '<div style="border-top:1px solid rgba(243,242,242,.11);padding-top:13px;display:flex;justify-content:space-between;align-items:baseline">' +
        '<span style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">From</span>' +
        '<span style="font-family:var(--font-heading);font-size:20px;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + moneyShort(s.p) + '</span></div>' +
        '<button type="button" class="btn btn-primary" data-nav="' + s.go + '" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:11px">Configure</button></div>';
    }).join('');

    var rate = TIERS.slice(0, 8).map(function (t, i) {
      return '<tr>' +
        '<td style="border-color:rgba(243,242,242,.11);font-family:var(--font-heading);font-size:16px">' + esc(t) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + money(TP[i]) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums">' + money(TP[i] * 3) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;text-align:right;color:rgba(243,242,242,.6)">' + ((i + 1) * 2 + '–' + ((i + 1) * 2 + 5)) + '</td></tr>';
    }).join('');

    return '<main>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);background:#131210;position:relative;overflow:hidden">' +
      '<div style="position:absolute;inset:0;opacity:.2">' + slot('eb-val-banner', 'Banner') + '</div>' +
      '<div style="position:relative;max-width:1200px;margin:0 auto;padding:70px 34px 62px;pointer-events:none">' +
      '<div style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-bottom:20px">Home <span style="color:var(--color-accent)">·</span> Games <span style="color:var(--color-accent)">·</span> <span style="color:var(--color-accent-400)">Valorant</span></div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:70px;line-height:1;letter-spacing:-.025em;margin:0 0 18px;color:#f3f2f2">Valorant rank boosting</h1>' +
      '<p style="font-size:15.5px;line-height:1.8;color:rgba(243,242,242,.7);max-width:56ch;margin:0">Iron through Radiant, every act. 340 Immortal-plus boosters across NA, EU, AP and BR — average pickup four minutes after payment clears.</p></div></section>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13)"><div class="eb-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(243,242,242,.13);max-width:1200px;margin:0 auto">' + valStats + '</div></section>' +
      '<section style="max-width:1200px;margin:0 auto;padding:70px 34px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">Services</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;letter-spacing:-.02em;margin:0 0 32px;color:#f3f2f2">Four ways to buy</h2>' +
      '<div class="eb-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:18px">' + services + '</div></section>' +
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:70px 34px">' +
      '<div class="eb-2col" style="display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:52px;align-items:start">' +
      '<div><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:14px">Rate card</div>' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;line-height:1.04;letter-spacing:-.02em;margin:0 0 18px;color:#f3f2f2">Price per division</h2>' +
      '<p style="font-size:14px;line-height:1.85;color:rgba(243,242,242,.6);margin:0 0 12px;text-align:justify;hyphens:auto">One division is one rank step — Gold 2 to Gold 1. The rate rises with the tier because the games get longer and the booster pool gets thinner.</p>' +
      '<p style="font-size:14px;line-height:1.85;color:rgba(243,242,242,.6);margin:0;text-align:justify;hyphens:auto">These are the numbers the configurator adds up. Nothing is added at checkout.</p></div>' +
      '<table class="table" style="color:#f3f2f2"><thead><tr>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Tier</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Per division</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Whole tier</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5);text-align:right">Typical hours</th></tr></thead><tbody>' + rate + '</tbody></table>' +
      '</div></div></section>' +
      '<section style="border-top:1px solid rgba(243,242,242,.13)"><div style="max-width:1200px;margin:0 auto;padding:70px 34px;text-align:center">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:50px;letter-spacing:-.025em;margin:0 0 26px;color:#f3f2f2">Ready when you are</h2>' +
      '<button type="button" class="btn btn-primary" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:13px;letter-spacing:.14em;text-transform:uppercase;padding:15px 34px;clip-path:polygon(0 0,100% 0,100% 68%,calc(100% - 12px) 100%,0 100%)">Open the configurator</button></div></section>' +
      '</main>';
  }

  // ── CONFIGURATOR ───────────────────────────────────────────────────────────
  function stepHead(num, title, right) {
    return '<div style="display:flex;align-items:baseline;gap:14px;border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:22px">' +
      '<span style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums">' + num + '</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:27px;margin:0;color:#f3f2f2">' + esc(title) + '</h3>' +
      (right ? '<span style="margin-left:auto;font-family:var(--font-heading);font-size:19px;color:var(--color-accent-300)">' + esc(right) + '</span>' : '') +
      '</div>';
  }
  function tierGrid(sel, attr) {
    return '<div class="eb-tiers" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:8px;margin-bottom:12px">' +
      TIERS.map(function (t, i) {
        return '<button type="button" ' + attr + '="' + i + '" style="' + st(cell(sel === i)) + '">' + esc(t) + '</button>';
      }).join('') + '</div>';
  }
  function divGrid(selDiv, tier, attr) {
    return '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:340px">' +
      [0, 1, 2].map(function (d) {
        return '<button type="button" ' + attr + '="' + d + '" style="' + st(cell(selDiv === d && tier < 8)) + '">Division ' + (3 - d) + '</button>';
      }).join('') + '</div>';
  }

  function order() {
    var s = state;
    var invalid = s.mode === 'division' && idx(s.toTier, s.toDiv) <= idx(s.fromTier, s.fromDiv);

    var modes = [
      { n: 'Division boost', d: 'Rank to rank', v: 'division' },
      { n: 'Net wins', d: 'Pay per game', v: 'wins' },
      { n: 'Placements', d: 'Season start', v: 'placement' }
    ].map(function (m) {
      return '<button type="button" data-mode="' + m.v + '" style="' + st(modeStyle(s.mode === m.v)) + '">' +
        '<span style="font-family:var(--font-heading);font-size:19px;display:block">' + esc(m.n) + '</span>' +
        '<span style="font-size:11px;letter-spacing:.06em;opacity:.6;display:block;margin-top:5px">' + esc(m.d) + '</span></button>';
    }).join('');

    var stepBlock;
    if (s.mode === 'division') {
      stepBlock =
        '<div style="margin-bottom:38px">' + stepHead('01', 'Current rank', label(s.fromTier, s.fromDiv)) +
        tierGrid(s.fromTier, 'data-ft') + divGrid(s.fromDiv, s.fromTier, 'data-fd') + '</div>' +
        '<div style="margin-bottom:38px">' + stepHead('02', 'Desired rank', label(s.toTier, s.toDiv)) +
        tierGrid(s.toTier, 'data-tt') + divGrid(s.toDiv, s.toTier, 'data-td') +
        (invalid ? '<div style="margin-top:16px;border-left:2px solid var(--color-accent);padding:8px 14px;font-size:13px;color:var(--color-accent-300)">Desired rank must sit above your current rank.</div>' : '') +
        '</div>';
    } else {
      var count = s.mode === 'wins' ? s.wins : s.placements;
      var title = s.mode === 'wins' ? 'How many wins' : 'How many placement matches';
      var hint = s.mode === 'wins' ? 'Net wins — every loss on the way is replayed at no charge.' : 'Five is the standard set. Order more to cover a second queue.';
      stepBlock =
        '<div style="margin-bottom:38px">' + stepHead('01', title, '') +
        '<div style="display:flex;align-items:center;gap:22px;margin-bottom:24px">' +
        '<button type="button" data-count="dec" class="btn" style="width:46px;height:46px;padding:0;border:1px solid rgba(243,242,242,.24);color:#f3f2f2;font-size:20px">−</button>' +
        '<div style="font-family:var(--font-heading);font-size:52px;font-variant-numeric:tabular-nums;min-width:76px;text-align:center;color:var(--color-accent-300)">' + count + '</div>' +
        '<button type="button" data-count="inc" class="btn" style="width:46px;height:46px;padding:0;border:1px solid rgba(243,242,242,.24);color:#f3f2f2;font-size:20px">+</button>' +
        '<span style="font-size:13px;color:rgba(243,242,242,.55);max-width:30ch;line-height:1.7">' + esc(hint) + '</span></div>' +
        stepHead('02', 'Your rank', label(s.fromTier, s.fromDiv)) +
        '<div class="eb-tiers" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:8px">' +
        TIERS.map(function (t, i) { return '<button type="button" data-ft="' + i + '" style="' + st(cell(s.fromTier === i)) + '">' + esc(t) + '</button>'; }).join('') +
        '</div></div>';
    }

    var boxBase = { display: 'grid', placeItems: 'center', width: '20px', height: '20px', flex: 'none', border: '1px solid', fontSize: '12px', fontFamily: 'var(--font-heading)' };
    var options = OPTS.map(function (o) {
      var on = !!s.opts[o.k];
      var boxStyle = st(assign(assign({}, boxBase), on ? { borderColor: 'var(--color-accent)', color: 'var(--color-accent-300)' } : { borderColor: 'rgba(243,242,242,.28)', color: 'transparent' }));
      var rowStyle = st({
        display: 'flex', alignItems: 'flex-start', gap: '15px', width: '100%', textAlign: 'left',
        padding: '17px 18px', cursor: 'pointer', background: on ? 'rgba(182,130,53,.08)' : 'transparent',
        border: 'none', borderBottom: '1px solid rgba(243,242,242,.11)', fontFamily: 'var(--font-body)'
      });
      return '<button type="button" data-opt="' + o.k + '" style="' + rowStyle + '">' +
        '<span style="' + boxStyle + '">' + (on ? '✓' : '') + '</span>' +
        '<span style="text-align:left;flex:1"><span style="font-family:var(--font-heading);font-size:18px;display:block;color:#f3f2f2">' + esc(o.n) + '</span>' +
        '<span style="font-size:12.5px;line-height:1.6;color:rgba(243,242,242,.55);display:block;margin-top:3px">' + esc(o.d) + '</span></span>' +
        '<span style="font-size:13px;font-variant-numeric:tabular-nums;color:var(--color-accent-400);flex:none">+' + o.pct + '%</span></button>';
    }).join('');

    var couponNote = discountRate() ? '10% off applied' : '';

    return '<main style="max-width:1200px;margin:0 auto;padding:52px 34px 90px">' +
      '<div style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-bottom:16px">Home <span style="color:var(--color-accent)">·</span> Valorant <span style="color:var(--color-accent)">·</span> <span style="color:var(--color-accent-400)">Configure</span></div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:56px;letter-spacing:-.025em;margin:0 0 40px;color:#f3f2f2">Build your boost</h1>' +
      '<div class="eb-order-grid" style="display:grid;grid-template-columns:minmax(0,1fr) 372px;gap:36px;align-items:start">' +
      '<div>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13);margin-bottom:38px">' + modes + '</div>' +
      stepBlock +
      '<div style="margin-bottom:38px"><div style="display:flex;align-items:baseline;gap:14px;border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:6px">' +
      '<span style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums">03</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:27px;margin:0;color:#f3f2f2">Options</h3></div>' + options + '</div>' +
      '<div><div style="display:flex;align-items:baseline;gap:14px;border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:18px">' +
      '<span style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums">04</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:27px;margin:0;color:#f3f2f2">Promo code</h3></div>' +
      '<div style="display:flex;gap:10px;max-width:400px">' +
      '<input class="input" id="eb-coupon" value="' + esc(s.coupon) + '" placeholder="Try CLIMB10" style="color:#f3f2f2;border-color:rgba(243,242,242,.24);background:transparent">' +
      '<span style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--color-accent-300);align-self:center;white-space:nowrap">' + esc(couponNote) + '</span></div></div>' +
      '</div>' +
      // rail
      '<aside class="eb-rail" style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;position:sticky;top:96px">' +
      '<div style="padding:22px 24px 18px;border-bottom:1px solid rgba(243,242,242,.12)">' +
      '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:8px">Valorant · ' + esc(modeLabel()) + '</div>' +
      '<div style="font-family:var(--font-heading);font-size:25px;color:#f3f2f2;line-height:1.2">' + esc(route()) + '</div></div>' +
      '<div style="padding:18px 24px">' + breakdownRows() + '</div>' +
      '<div style="padding:18px 24px;border-top:1px solid rgba(243,242,242,.12);display:flex;justify-content:space-between;align-items:flex-end">' +
      '<div><div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:6px">Total</div>' +
      '<div style="font-family:var(--font-heading);font-size:44px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + money(totalUsd()) + '</div></div>' +
      '<div style="text-align:right"><div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:6px">Est. delivery</div>' +
      '<div style="font-family:var(--font-heading);font-size:22px;font-variant-numeric:tabular-nums;color:#f3f2f2">' + esc(etaLabel()) + '</div></div></div>' +
      '<div style="padding:0 24px 24px">' +
      '<button type="button" class="btn btn-primary btn-block" data-checkout style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:12px;letter-spacing:.14em;text-transform:uppercase;padding:14px;margin-top:8px;clip-path:polygon(0 0,100% 0,100% 66%,calc(100% - 11px) 100%,0 100%)"' + (invalid ? ' disabled' : '') + '>Continue to checkout</button>' +
      '<div style="display:flex;gap:14px;justify-content:center;margin-top:16px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(243,242,242,.42)">' +
      '<span>Refundable</span><span style="color:var(--color-accent)">·</span><span>VPN matched</span><span style="color:var(--color-accent)">·</span><span>No logs kept</span></div></div>' +
      '</aside></div></main>';
  }

  function modeLabel() { return state.mode === 'division' ? 'Division boost' : (state.mode === 'wins' ? 'Net wins' : 'Placements'); }
  function breakdownRows() {
    var s = state, baseUsd = base(), disc = discountRate();
    var rows = [{ k: s.mode === 'division' ? units() + ' divisions' : 'Base service', v: money(baseUsd) }];
    OPTS.forEach(function (o) { if (s.opts[o.k]) rows.push({ k: o.n, v: '+ ' + money(baseUsd * o.pct / 100) }); });
    if (disc) rows.push({ k: 'Promo CLIMB10', v: '− ' + money(baseUsd * mult() * disc) });
    return rows.map(function (b) {
      return '<div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;font-size:13px">' +
        '<span style="color:rgba(243,242,242,.62)">' + esc(b.k) + '</span>' +
        '<span style="font-variant-numeric:tabular-nums;color:#f3f2f2">' + esc(b.v) + '</span></div>';
    }).join('');
  }

  // ── CHECKOUT ───────────────────────────────────────────────────────────────
  function checkout() {
    var s = state;
    var payBase = { padding: '13px 8px', fontFamily: 'var(--font-heading)', fontSize: '13px', letterSpacing: '.08em', textTransform: 'uppercase', background: 'transparent', cursor: 'pointer', borderRadius: 'var(--radius-md)', border: '1px solid', width: '100%' };
    var payNotes = {
      paypal: 'You will be handed to PayPal to approve the payment. Buyer protection applies and the order opens the moment PayPal confirms.',
      crypto: 'BTC, ETH, USDT and LTC. The invoice holds its rate for fifteen minutes and the order opens after one confirmation.',
      apple: 'Confirm with Face ID or Touch ID. Nothing is stored on our side beyond the transaction reference.'
    };
    var methods = [{ id: 'card', n: 'Card' }, { id: 'paypal', n: 'PayPal' }, { id: 'crypto', n: 'Crypto' }, { id: 'apple', n: 'Apple Pay' }].map(function (p) {
      var style = s.pay === p.id
        ? st(assign(assign({}, payBase), { borderColor: 'var(--color-accent)', color: 'var(--color-accent-300)', background: 'rgba(182,130,53,.12)' }))
        : st(assign(assign({}, payBase), { borderColor: 'rgba(243,242,242,.2)', color: 'rgba(243,242,242,.66)' }));
      return '<button type="button" data-pay="' + p.id + '" style="' + style + '">' + esc(p.n) + '</button>';
    }).join('');

    var payDetail = s.pay === 'card'
      ? '<div class="eb-row" style="display:grid;grid-template-columns:minmax(0,1fr) 100px 100px;gap:14px;margin-bottom:14px">' +
        '<div class="field"><label style="color:rgba(243,242,242,.6)">Card number</label><input class="input" placeholder="4242 4242 4242 4242" style="color:#f3f2f2;border-color:rgba(243,242,242,.24);font-variant-numeric:tabular-nums"></div>' +
        '<div class="field"><label style="color:rgba(243,242,242,.6)">Expiry</label><input class="input" placeholder="04 / 29" style="color:#f3f2f2;border-color:rgba(243,242,242,.24);font-variant-numeric:tabular-nums"></div>' +
        '<div class="field"><label style="color:rgba(243,242,242,.6)">CVC</label><input class="input" placeholder="123" style="color:#f3f2f2;border-color:rgba(243,242,242,.24);font-variant-numeric:tabular-nums"></div></div>'
      : '<div style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;padding:20px 22px;margin-bottom:14px;font-size:13.5px;line-height:1.75;color:rgba(243,242,242,.66)">' + esc(payNotes[s.pay] || '') + '</div>';

    var termsBox = st(assign({ display: 'grid', placeItems: 'center', width: '20px', height: '20px', flex: 'none', border: '1px solid', fontSize: '12px', fontFamily: 'var(--font-heading)' }, s.terms ? { borderColor: 'var(--color-accent)', color: 'var(--color-accent-300)' } : { borderColor: 'rgba(243,242,242,.28)', color: 'transparent' }));
    var payBtnStyle = st({
      borderColor: s.terms ? 'var(--color-accent)' : 'rgba(243,242,242,.2)',
      color: s.terms ? 'var(--color-accent-400)' : 'rgba(243,242,242,.4)',
      fontSize: '12px', letterSpacing: '.14em', textTransform: 'uppercase', padding: '14px',
      marginTop: '8px', cursor: s.terms ? 'pointer' : 'not-allowed'
    });

    return '<main style="max-width:1060px;margin:0 auto;padding:52px 34px 90px">' +
      '<div style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-bottom:16px">Configure <span style="color:var(--color-accent)">·</span> <span style="color:var(--color-accent-400)">Checkout</span></div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:56px;letter-spacing:-.025em;margin:0 0 40px;color:#f3f2f2">Checkout</h1>' +
      '<div class="eb-order-grid" style="display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:36px;align-items:start"><div>' +
      '<div style="border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:20px;display:flex;align-items:baseline;gap:14px">' +
      '<span style="font-size:11px;letter-spacing:.2em;color:var(--color-accent-400);font-variant-numeric:tabular-nums">01</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:26px;margin:0;color:#f3f2f2">Where do we reach you</h3></div>' +
      '<div class="eb-row" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:36px">' +
      '<div class="field"><label style="color:rgba(243,242,242,.6)">Email</label><input class="input" type="email" placeholder="you@mail.com" style="color:#f3f2f2;border-color:rgba(243,242,242,.24)"></div>' +
      '<div class="field"><label style="color:rgba(243,242,242,.6)">Discord</label><input class="input" placeholder="handle#0000" style="color:#f3f2f2;border-color:rgba(243,242,242,.24)"></div></div>' +
      '<div style="border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:20px;display:flex;align-items:baseline;gap:14px">' +
      '<span style="font-size:11px;letter-spacing:.2em;color:var(--color-accent-400);font-variant-numeric:tabular-nums">02</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:26px;margin:0;color:#f3f2f2">Payment</h3></div>' +
      '<div class="eb-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:22px">' + methods + '</div>' +
      payDetail +
      '<p style="font-size:12.5px;line-height:1.75;color:rgba(243,242,242,.5);margin:0 0 36px">We never store card details. Account credentials, if your order needs them, are requested after payment inside the encrypted order room — never by email.</p>' +
      '<div style="border-bottom:1px solid rgba(243,242,242,.13);padding-bottom:12px;margin-bottom:20px;display:flex;align-items:baseline;gap:14px">' +
      '<span style="font-size:11px;letter-spacing:.2em;color:var(--color-accent-400);font-variant-numeric:tabular-nums">03</span>' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:26px;margin:0;color:#f3f2f2">Confirm</h3></div>' +
      '<button type="button" data-terms style="display:flex;align-items:flex-start;gap:14px;background:transparent;border:none;padding:0;cursor:pointer;font-family:var(--font-body)">' +
      '<span style="' + termsBox + '">' + (s.terms ? '✓' : '') + '</span>' +
      '<span style="font-size:13px;line-height:1.7;color:rgba(243,242,242,.66);text-align:left">I have read the terms of service and the refund policy, and I confirm I am the account holder.</span></button>' +
      '</div>' +
      '<aside class="eb-rail" style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;position:sticky;top:96px">' +
      '<div style="padding:22px 24px 18px;border-bottom:1px solid rgba(243,242,242,.12)">' +
      '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:8px">Order</div>' +
      '<div style="font-family:var(--font-heading);font-size:23px;color:#f3f2f2;line-height:1.2">' + esc(route()) + '</div></div>' +
      '<div style="padding:18px 24px">' + breakdownRows() + '</div>' +
      '<div style="padding:18px 24px;border-top:1px solid rgba(243,242,242,.12)">' +
      '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:6px">Amount due</div>' +
      '<div style="font-family:var(--font-heading);font-size:44px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + money(totalUsd()) + '</div></div>' +
      '<div style="padding:0 24px 24px">' +
      '<button type="button" class="btn btn-primary btn-block" data-paynow style="' + payBtnStyle + '">' + (s.terms ? 'Pay ' + money(totalUsd()) : 'Accept the terms to pay') + '</button>' +
      '<div style="text-align:center;margin-top:14px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(243,242,242,.42)">Money back if we miss the estimate</div></div>' +
      '</aside></div></main>';
  }

  // ── DASHBOARD ──────────────────────────────────────────────────────────────
  function dashboard() {
    var s = state;
    var pctDone = s.paid ? 12 + s.extra * 9 : 62 + s.extra * 4;
    var pct = Math.min(96, pctDone);
    var nLog = 6 + s.extra;
    var logSrc = [];
    for (var i = 0; i < nLog; i++) {
      var won = i % 5 !== 3;
      logSrc.push({
        i: nLog - i, res: won ? 'Win' : 'Loss', map: MAPS[(i * 3 + 1) % MAPS.length],
        score: won ? '13 : ' + (5 + (i % 7)) : (7 + (i % 4)) + ' : 13',
        kda: (17 + (i * 5) % 12) + ' / ' + (9 + i % 6) + ' / ' + (4 + i % 8),
        rr: won ? '+' + (18 + (i * 3) % 9) : '−' + (14 + i % 6), won: won
      });
    }
    var log = logSrc.map(function (m) {
      var resStyle = 'font-size:10px;letter-spacing:.14em;text-transform:uppercase;padding:3px 8px;border:1px solid ' +
        (m.won ? 'var(--color-accent)' : 'rgba(243,242,242,.24)') + ';color:' + (m.won ? 'var(--color-accent-300)' : 'rgba(243,242,242,.55)');
      return '<tr>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;color:rgba(243,242,242,.5)">' + m.i + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11)"><span style="' + resStyle + '">' + m.res + '</span></td>' +
        '<td style="border-color:rgba(243,242,242,.11)">' + esc(m.map) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums">' + esc(m.score) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;color:rgba(243,242,242,.7)">' + esc(m.kda) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;text-align:right;color:var(--color-accent-300)">' + m.rr + '</td></tr>';
    }).join('');

    var orderStats = [
      { v: units() || 6, k: s.mode === 'division' ? 'Divisions' : 'Games' },
      { v: nLog, k: 'Played' },
      { v: nLog - Math.floor(nLog / 5), k: 'Won' },
      { v: etaLabel(), k: 'Remaining' },
      { v: money(totalUsd()), k: 'Order value' }
    ].map(function (st2) {
      return '<div style="background:#1b1a17;padding:16px 18px">' +
        '<div style="font-family:var(--font-heading);font-size:23px;font-variant-numeric:tabular-nums;color:#f3f2f2">' + esc(st2.v) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-top:5px">' + esc(st2.k) + '</div></div>';
    }).join('');

    var facts = [
      { k: 'Orders delivered', v: '1,284' }, { k: 'Win rate, 30 days', v: '92%' },
      { k: 'Buyer rating', v: '4.9 / 5' }, { k: 'Response time', v: '3 min' }
    ].map(function (f) {
      return '<div style="display:flex;justify-content:space-between;font-size:12.5px;border-bottom:1px solid rgba(243,242,242,.09);padding-bottom:7px">' +
        '<span style="color:rgba(243,242,242,.55)">' + esc(f.k) + '</span>' +
        '<span style="font-variant-numeric:tabular-nums;color:#f3f2f2">' + esc(f.v) + '</span></div>';
    }).join('');

    var messages = [
      { who: 'Kryos', at: '14:02', text: 'Two more games tonight, then I will hand it back for the day. Agent request noted — Jett only.' },
      { who: 'Support', at: '11:47', text: 'Order assigned and VPN pinned to EU West. Offline mode is on for the whole run.' },
      { who: 'You', at: '11:31', text: 'Please avoid queueing after midnight, my friends will notice.' }
    ].map(function (m) {
      return '<div style="border-left:2px solid var(--color-accent);padding:2px 0 2px 13px;margin-bottom:15px">' +
        '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:5px">' + esc(m.who) + ' · ' + esc(m.at) + '</div>' +
        '<div style="font-size:13px;line-height:1.65;color:rgba(243,242,242,.78)">' + esc(m.text) + '</div></div>';
    }).join('');

    var orderId = s.paid ? 'EB-90412' : 'EB-88117';
    var banner = s.paid
      ? '<div style="border:1px solid var(--color-accent);background:var(--color-accent-900);padding:16px 22px;margin-bottom:30px;display:flex;align-items:center;gap:16px">' +
        '<span style="display:inline-block;width:8px;height:8px;background:var(--color-accent-300);animation:eb-pulse 1.4s ease-in-out infinite;flex:none"></span>' +
        '<span style="font-family:var(--font-heading);font-size:19px;color:var(--color-accent-200)">Paid. Order ' + orderId + ' is in the queue — a booster is being assigned now.</span></div>'
      : '';

    return '<main style="max-width:1200px;margin:0 auto;padding:52px 34px 90px">' + banner +
      '<div class="eb-2col" style="display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:38px">' +
      '<div><div style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-bottom:14px">Order ' + orderId + '</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:52px;letter-spacing:-.025em;margin:0;color:#f3f2f2">' + esc(route()) + '</h1></div>' +
      '<div style="display:flex;gap:10px">' +
      '<button type="button" class="btn btn-secondary" data-refresh style="border-color:rgba(243,242,242,.24);color:rgba(243,242,242,.82);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:11px 16px">Refresh log</button>' +
      '<button type="button" class="btn btn-secondary" style="border-color:rgba(243,242,242,.24);color:rgba(243,242,242,.82);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:11px 16px">Pause order</button></div></div>' +
      '<div style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;padding:28px 30px;margin-bottom:22px">' +
      '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px">' +
      '<span style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45)">Progress</span>' +
      '<span style="font-family:var(--font-heading);font-size:28px;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + pct + '%</span></div>' +
      '<div style="height:4px;background:rgba(243,242,242,.13);position:relative;overflow:hidden;margin-bottom:22px">' +
      '<div style="height:4px;width:' + pct + '%;background:var(--color-accent)"></div>' +
      '<div style="position:absolute;inset:0;width:22%;background:linear-gradient(90deg,transparent,rgba(250,203,141,.28),transparent);animation:eb-creep 3.4s linear infinite"></div></div>' +
      '<div class="eb-grid-5" style="display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13)">' + orderStats + '</div></div>' +
      '<div class="eb-order-grid" style="display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px;align-items:start">' +
      '<div style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;padding:26px 28px">' +
      '<h3 style="font-family:var(--font-heading);font-weight:400;font-size:25px;margin:0 0 18px;color:#f3f2f2">Match log</h3>' +
      '<table class="table" style="color:#f3f2f2"><thead><tr>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">#</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Result</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Map</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Score</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">K / D / A</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5);text-align:right">RR</th></tr></thead><tbody>' + log + '</tbody></table></div>' +
      '<div style="display:flex;flex-direction:column;gap:22px">' +
      '<div style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;padding:24px 26px">' +
      '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:16px">Your booster</div>' +
      '<div style="display:flex;align-items:center;gap:14px;margin-bottom:18px">' +
      '<span style="display:grid;place-items:center;width:46px;height:46px;flex:none;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:15px;clip-path:polygon(0 0,100% 0,100% 70%,70% 100%,0 100%)">KR</span>' +
      '<div><div style="font-family:var(--font-heading);font-size:20px;color:#f3f2f2">Kryos</div>' +
      '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--color-accent-400)">Radiant · EU West</div></div></div>' +
      '<div style="display:flex;flex-direction:column;gap:9px">' + facts + '</div>' +
      '<button type="button" class="btn btn-primary btn-block" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:11px;margin-top:18px">Open order room</button></div>' +
      '<div style="border:1px solid rgba(243,242,242,.16);background:#1b1a17;padding:24px 26px">' +
      '<div style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:rgba(243,242,242,.45);margin-bottom:14px">Messages</div>' + messages + '</div>' +
      '</div></div></main>';
  }

  // ── BOOSTERS ───────────────────────────────────────────────────────────────
  function boosters() {
    var list = [
      { mono: 'KR', n: 'Kryos', rank: 'Radiant · EU West', bio: 'Ex-academy duelist. Takes agent requests and plays them properly rather than filling.', games: ['Valorant', 'CS2'], stats: [{ v: '1,284', k: 'Orders' }, { v: '92%', k: 'Wins' }, { v: '4.9', k: 'Rating' }] },
      { mono: 'SB', n: 'Sablier', rank: 'Challenger · EUW', bio: 'Jungle and mid. Writes a short note after every session on what actually lost the game.', games: ['League', 'TFT'], stats: [{ v: '2,061', k: 'Orders' }, { v: '89%', k: 'Wins' }, { v: '4.9', k: 'Rating' }] },
      { mono: 'HL', n: 'Halvard', rank: 'Level 10 · Faceit', bio: 'Premier and Faceit specialist. Comfortable on every map in the active duty pool.', games: ['CS2'], stats: [{ v: '944', k: 'Orders' }, { v: '95%', k: 'Wins' }, { v: '5.0', k: 'Rating' }] },
      { mono: 'JN', n: 'Juno', rank: 'Top 500 · NA', bio: 'Support main who climbs on utility rather than aim. Very steady, rarely tilts an order.', games: ['Overwatch 2'], stats: [{ v: '612', k: 'Orders' }, { v: '87%', k: 'Wins' }, { v: '4.8', k: 'Rating' }] },
      { mono: 'VL', n: 'Vell', rank: 'Predator · EU', bio: 'Apex ranked and badge runs. Plays late European hours, which suits overnight orders.', games: ['Apex'], stats: [{ v: '733', k: 'Orders' }, { v: '84%', k: 'Wins' }, { v: '4.8', k: 'Rating' }] },
      { mono: 'TS', n: 'Talis', rank: 'Grand Champ · NA', bio: 'Doubles and standard. Also the most requested coach on the roster for mechanics.', games: ['Rocket League'], stats: [{ v: '1,105', k: 'Orders' }, { v: '90%', k: 'Wins' }, { v: '4.9', k: 'Rating' }] }
    ].map(function (b) {
      var stats = b.stats.map(function (s) {
        return '<div style="background:#1b1a17;padding:14px 8px;text-align:center">' +
          '<div style="font-family:var(--font-heading);font-size:19px;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + esc(s.v) + '</div>' +
          '<div style="font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:rgba(243,242,242,.42);margin-top:4px">' + esc(s.k) + '</div></div>';
      }).join('');
      var tags = b.games.map(function (g) {
        return '<span style="font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:4px 9px;border:1px solid rgba(243,242,242,.18);color:rgba(243,242,242,.6)">' + esc(g) + '</span>';
      }).join('');
      return '<div style="border:1px solid rgba(243,242,242,.13);background:#1b1a17">' +
        '<div style="display:flex;align-items:center;gap:15px;padding:22px 22px 18px;border-bottom:1px solid rgba(243,242,242,.1)">' +
        '<span style="display:grid;place-items:center;width:52px;height:52px;flex:none;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:17px;clip-path:polygon(0 0,100% 0,100% 72%,72% 100%,0 100%)">' + esc(b.mono) + '</span>' +
        '<div style="flex:1"><div style="font-family:var(--font-heading);font-size:22px;color:#f3f2f2">' + esc(b.n) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--color-accent-400);margin-top:3px">' + esc(b.rank) + '</div></div>' +
        '<span style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;border:1px solid var(--color-accent);color:var(--color-accent-400);padding:4px 8px">Verified</span></div>' +
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(243,242,242,.1)">' + stats + '</div>' +
        '<div style="padding:18px 22px 22px"><p style="font-size:12.5px;line-height:1.7;color:rgba(243,242,242,.58);margin:0 0 14px">' + esc(b.bio) + '</p>' +
        '<div style="display:flex;gap:7px;flex-wrap:wrap">' + tags + '</div></div></div>';
    }).join('');

    return '<main>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:66px 34px 58px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:16px">The roster · 1,142 active</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:66px;line-height:1;letter-spacing:-.025em;margin:0 0 18px;color:#f3f2f2">Who plays your games</h1>' +
      '<p style="font-size:15.5px;line-height:1.8;color:rgba(243,242,242,.68);max-width:58ch;margin:0">Every booster signs a contract under a verified legal identity, passes a live screen-share trial, and keeps a rolling 30-day rating. Three strikes removes them from the roster permanently.</p></div></section>' +
      '<section style="max-width:1200px;margin:0 auto;padding:60px 34px 84px">' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px">' + list + '</div></section></main>';
  }

  // ── COACHING ───────────────────────────────────────────────────────────────
  function coaching() {
    var sessions = [
      { len: '60 minutes', p: 28, h: 'Single session', items: ['Live screen share', 'One VOD reviewed', 'Written summary you keep', 'Booked within 24 hours'] },
      { len: '4 × 60 minutes', p: 96, h: 'Four-week block', items: ['Same coach throughout', 'Weekly homework and review', 'Rank checkpoint each week', 'Reschedule twice, free'] },
      { len: '90 minutes', p: 52, h: 'Deep VOD audit', items: ['Three games torn down frame by frame', 'Positioning and economy notes', 'Role-specific drill list', 'No live play required'] }
    ].map(function (s) {
      var items = s.items.map(function (it) {
        return '<div style="display:grid;grid-template-columns:14px 1fr;gap:10px;font-size:12.5px;line-height:1.6;color:rgba(243,242,242,.6)">' +
          '<span style="color:var(--color-accent)">·</span><span>' + esc(it) + '</span></div>';
      }).join('');
      return '<div style="border:1px solid rgba(243,242,242,.13);background:#1b1a17;padding:26px 24px;display:flex;flex-direction:column;gap:14px">' +
        '<div style="display:flex;justify-content:space-between;align-items:baseline">' +
        '<span style="font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--color-accent-400)">' + esc(s.len) + '</span>' +
        '<span style="font-family:var(--font-heading);font-size:24px;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + moneyShort(s.p) + '</span></div>' +
        '<div style="font-family:var(--font-heading);font-size:25px;color:#f3f2f2">' + esc(s.h) + '</div>' +
        '<div style="display:flex;flex-direction:column;gap:9px;flex:1">' + items + '</div>' +
        '<button type="button" class="btn btn-primary" data-nav="checkout" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:11px">Book</button></div>';
    }).join('');

    var coaches = [
      { mono: 'KR', n: 'Kryos', rank: 'Radiant', spec: 'Valorant duelist mechanics, entry timing, crosshair discipline', count: '312', rate: 28 },
      { mono: 'SB', n: 'Sablier', rank: 'Challenger', spec: 'League jungle pathing, tempo and objective trading', count: '486', rate: 32 },
      { mono: 'HL', n: 'Halvard', rank: 'Faceit 10', spec: 'CS2 utility usage, retakes and default setups', count: '198', rate: 35 },
      { mono: 'TS', n: 'Talis', rank: 'Grand Champ', spec: 'Rocket League rotation, aerial control, kickoff theory', count: '274', rate: 26 }
    ].map(function (c) {
      return '<div class="eb-row" style="display:grid;grid-template-columns:190px minmax(0,1fr) 110px 110px 100px;gap:22px;align-items:center;padding:18px 22px;border-bottom:1px solid rgba(243,242,242,.1)">' +
        '<div style="display:flex;align-items:center;gap:13px">' +
        '<span style="display:grid;place-items:center;width:40px;height:40px;flex:none;border:1px solid var(--color-accent);color:var(--color-accent-400);font-family:var(--font-heading);font-size:14px;clip-path:polygon(0 0,100% 0,100% 70%,70% 100%,0 100%)">' + esc(c.mono) + '</span>' +
        '<div><div style="font-family:var(--font-heading);font-size:18px;color:#f3f2f2">' + esc(c.n) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--color-accent-400)">' + esc(c.rank) + '</div></div></div>' +
        '<div style="font-size:12.5px;line-height:1.65;color:rgba(243,242,242,.58)">' + esc(c.spec) + '</div>' +
        '<div><div style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">Sessions</div><div style="font-family:var(--font-heading);font-size:17px;font-variant-numeric:tabular-nums;color:#f3f2f2;margin-top:3px">' + esc(c.count) + '</div></div>' +
        '<div><div style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:rgba(243,242,242,.42)">Per hour</div><div style="font-family:var(--font-heading);font-size:17px;font-variant-numeric:tabular-nums;color:var(--color-accent-300);margin-top:3px">' + moneyShort(c.rate) + '</div></div>' +
        '<button type="button" class="btn btn-secondary" data-nav="checkout" style="border-color:rgba(243,242,242,.22);color:rgba(243,242,242,.78);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:9px 12px">Book</button></div>';
    }).join('');

    return '<main>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13)"><div class="eb-2col" style="display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:52px;align-items:center;max-width:1200px;margin:0 auto;padding:70px 34px 64px">' +
      '<div><div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:16px">Coaching</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:66px;line-height:1;letter-spacing:-.025em;margin:0 0 20px;color:#f3f2f2">Learn the climb instead of buying it</h1>' +
      '<p style="font-size:15.5px;line-height:1.82;color:rgba(243,242,242,.68);max-width:50ch;margin:0 0 30px">One-to-one sessions with the same players who boost. Screen share, live VOD review, a written plan you keep. Sessions run 60 or 90 minutes and you pick the coach yourself.</p>' +
      '<button type="button" class="btn btn-primary" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:13px;letter-spacing:.12em;text-transform:uppercase;padding:14px 26px;' + CTA_NOTCH + '">Book a session</button></div>' +
      '<div class="plate" style="border-color:#22211d;outline-color:rgba(243,242,242,.16);height:340px;position:relative">' + slot('eb-coach', 'Coaching photo') + '</div></div></section>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:64px 34px">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;letter-spacing:-.02em;margin:0 0 30px;color:#f3f2f2">Session formats</h2>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px">' + sessions + '</div></div></section>' +
      '<section style="max-width:1200px;margin:0 auto;padding:64px 34px 84px">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;letter-spacing:-.02em;margin:0 0 28px;color:#f3f2f2">Available coaches</h2>' +
      '<div style="border:1px solid rgba(243,242,242,.13);background:#1b1a17">' + coaches + '</div></section></main>';
  }

  // ── PRICING ────────────────────────────────────────────────────────────────
  function pricing() {
    var packages = [
      { k: 'Pay as you go', n: 'Single order', price: 6, unit: '/ division', badge: '', hero: false, items: ['Full rate card, nothing hidden', 'Live match log', 'Offline mode and VPN matching', 'Refund if we miss the estimate', 'Support in minutes, not days'] },
      { k: 'Most chosen', n: 'Season pass', price: 24, unit: '/ month', badge: 'Popular', hero: true, items: ['15% off every order, all games', 'Priority start included free', 'Booster of your choice from the roster', 'Two free replays per month', 'Cancel any month, no notice'] },
      { k: 'For teams', n: 'Roster plan', price: 180, unit: '/ month', badge: '', hero: false, items: ['Five accounts under one invoice', 'Named account manager', 'Shared coaching hours pool', 'Scrim scheduling assistance', 'Consolidated monthly billing'] }
    ].map(function (p) {
      var cardStyle = 'display:flex;flex-direction:column;border:1px solid ' + (p.hero ? 'var(--color-accent)' : 'rgba(243,242,242,.13)') + ';background:' + (p.hero ? '#201d17' : '#1b1a17');
      var badge = p.badge ? '<span style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;border:1px solid var(--color-accent);color:var(--color-accent-400);padding:4px 9px">' + esc(p.badge) + '</span>' : '<span></span>';
      var items = p.items.map(function (it) {
        return '<div style="display:grid;grid-template-columns:14px 1fr;gap:10px;font-size:13px;line-height:1.6;color:rgba(243,242,242,.64)">' +
          '<span style="color:var(--color-accent)">·</span><span>' + esc(it) + '</span></div>';
      }).join('');
      return '<div style="' + cardStyle + '">' +
        '<div style="padding:26px 24px 20px;border-bottom:1px solid rgba(243,242,242,.11)">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
        '<span style="font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--color-accent-400)">' + esc(p.k) + '</span>' + badge + '</div>' +
        '<div style="font-family:var(--font-heading);font-size:30px;color:#f3f2f2;margin-bottom:12px">' + esc(p.n) + '</div>' +
        '<div style="display:flex;align-items:baseline;gap:8px">' +
        '<span style="font-family:var(--font-heading);font-size:46px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + moneyShort(p.price) + '</span>' +
        '<span style="font-size:12px;color:rgba(243,242,242,.5)">' + esc(p.unit) + '</span></div></div>' +
        '<div style="padding:22px 24px;display:flex;flex-direction:column;gap:11px;flex:1">' + items + '</div>' +
        '<div style="padding:0 24px 24px"><button type="button" class="btn btn-primary btn-block" data-nav="order" style="border-color:var(--color-accent);color:var(--color-accent-400);font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding:12px">Choose</button></div></div>';
    }).join('');

    var gameRates = [
      { n: 'Valorant', div: 6, win: 9, plc: 11, coach: 28, pool: '340' },
      { n: 'League of Legends', div: 5, win: 8, plc: 10, coach: 32, pool: '412' },
      { n: 'Counter-Strike 2', div: 7, win: 11, plc: '—', coach: 35, pool: '188' },
      { n: 'Apex Legends', div: 9, win: 12, plc: '—', coach: 30, pool: '96' },
      { n: 'Overwatch 2', div: 6, win: 9, plc: 12, coach: 27, pool: '134' },
      { n: 'Rocket League', div: 5, win: 7, plc: 9, coach: 26, pool: '110' }
    ].map(function (g) {
      function cellv(v) { return typeof v === 'number' ? moneyShort(v) : v; }
      return '<tr>' +
        '<td style="border-color:rgba(243,242,242,.11);font-family:var(--font-heading);font-size:17px">' + esc(g.n) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + cellv(g.div) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums">' + cellv(g.win) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums">' + cellv(g.plc) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums">' + cellv(g.coach) + '</td>' +
        '<td style="border-color:rgba(243,242,242,.11);font-variant-numeric:tabular-nums;text-align:right;color:rgba(243,242,242,.6)">' + esc(g.pool) + '</td></tr>';
    }).join('');

    return '<main>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:66px 34px 58px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:16px">Pricing</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:66px;line-height:1;letter-spacing:-.025em;margin:0 0 18px;color:#f3f2f2">What things cost</h1>' +
      '<p style="font-size:15.5px;line-height:1.8;color:rgba(243,242,242,.68);max-width:56ch;margin:0">Every price on this page is the price you pay. No service fee, no currency surcharge, no upsell at the payment step.</p></div></section>' +
      '<section style="max-width:1200px;margin:0 auto;padding:60px 34px">' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:22px">' + packages + '</div></section>' +
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:64px 34px 84px">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;letter-spacing:-.02em;margin:0 0 26px;color:#f3f2f2">Starting price by game</h2>' +
      '<table class="table" style="color:#f3f2f2"><thead><tr>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Game</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Division</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Net win</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Placements</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5)">Coaching / hr</th>' +
      '<th style="border-color:rgba(243,242,242,.2);color:rgba(243,242,242,.5);text-align:right">Boosters</th></tr></thead><tbody>' + gameRates + '</tbody></table></div></section></main>';
  }

  // ── ABOUT ──────────────────────────────────────────────────────────────────
  function about() {
    var stats = [
      { v: '2016', k: 'Founded' }, { v: '214,860', k: 'Orders delivered' },
      { v: '1,142', k: 'Contracted boosters' }, { v: '6', k: 'Titles covered' }, { v: '0', k: 'Bans on record' }
    ].map(function (s) {
      return '<div style="background:#131210;padding:30px 24px">' +
        '<div style="font-family:var(--font-heading);font-size:34px;line-height:1;font-variant-numeric:tabular-nums;color:var(--color-accent-300)">' + esc(s.v) + '</div>' +
        '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,242,242,.5);margin-top:9px">' + esc(s.k) + '</div></div>';
    }).join('');

    var guarantees = [
      { i: '01', h: 'The quote is the price', d: 'The configurator totals the published rate card and adds nothing at the payment step. No service fee, no currency surcharge, no rounding in our favour.' },
      { i: '02', h: 'Refund on a missed estimate', d: 'Every order carries the delivery estimate you were shown. Miss it and you may take a reassignment or a refund of the unplayed portion, without arguing for it.' },
      { i: '03', h: 'One booster per order', d: 'Orders are not resold or split between freelancers. The name you see on the dashboard is the only person who logs in.' },
      { i: '04', h: 'Credentials purged on delivery', d: 'Logins live in the encrypted order room, are visible only to the assigned booster, and are deleted when the order closes.' },
      { i: '05', h: 'Rewards stay yours', d: 'Drops, battle pass progress, currency and cosmetics earned during your order remain on your account. We take nothing.' },
      { i: '06', h: 'Pause whenever', d: 'Need the account back for an evening? Pause from the dashboard and the booster stands down until you resume.' }
    ].map(function (g) {
      return '<div style="background:#171613;padding:28px 26px">' +
        '<div style="font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--color-accent-400);font-variant-numeric:tabular-nums;margin-bottom:13px">' + esc(g.i) + '</div>' +
        '<div style="font-family:var(--font-heading);font-size:22px;color:#f3f2f2;margin-bottom:10px">' + esc(g.h) + '</div>' +
        '<p style="font-size:13px;line-height:1.8;color:rgba(243,242,242,.58);margin:0;text-align:justify;hyphens:auto">' + esc(g.d) + '</p></div>';
    }).join('');

    var logos = ['Visa', 'Mastercard', 'Amex', 'PayPal', 'Apple Pay', 'Google Pay', 'Bitcoin', 'USDT'].map(function (p) {
      return '<span style="border:1px solid rgba(243,242,242,.18);padding:11px 18px;font-family:var(--font-heading);font-size:14px;letter-spacing:.06em;color:rgba(243,242,242,.72)">' + esc(p) + '</span>';
    }).join('');

    return '<main>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13)"><div style="max-width:1200px;margin:0 auto;padding:70px 34px 62px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:16px">Since 2016</div>' +
      '<h1 class="eb-h1" style="font-family:var(--font-heading);font-weight:400;font-size:70px;line-height:1;letter-spacing:-.025em;margin:0 0 34px;max-width:20ch;color:#f3f2f2">A boosting service that behaves like a business</h1>' +
      '<div class="eb-2col" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:44px;max-width:960px">' +
      '<p style="font-size:14.5px;line-height:1.9;color:rgba(243,242,242,.64);margin:0;text-align:justify;hyphens:auto">eSports Boost started as four friends taking orders in a Discord server. The industry we joined ran on screenshots and trust — no contracts, no receipts, and no way to tell a good booster from a lucky one. We built the opposite: signed boosters, itemised quotes, and an order room that logs every game so nothing depends on anyone\'s word.</p>' +
      '<p style="font-size:14.5px;line-height:1.9;color:rgba(243,242,242,.64);margin:0;text-align:justify;hyphens:auto">Ten years on, the promise hasn\'t changed shape. You see the price before you pay it. You see every match while it happens. If we miss the estimate we quoted, you get your money back without arguing for it. That is the entire pitch, and it is the reason people order twice.</p></div></div></section>' +
      '<section style="border-bottom:1px solid rgba(243,242,242,.13);background:#131210"><div class="eb-grid-5" style="display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:rgba(243,242,242,.13);max-width:1200px;margin:0 auto">' + stats + '</div></section>' +
      '<section style="max-width:1200px;margin:0 auto;padding:64px 34px">' +
      '<h2 class="eb-h2" style="font-family:var(--font-heading);font-weight:400;font-size:44px;letter-spacing:-.02em;margin:0 0 30px;color:#f3f2f2">The guarantees, in full</h2>' +
      '<div class="eb-grid-3" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1px;background:rgba(243,242,242,.13);border:1px solid rgba(243,242,242,.13)">' + guarantees + '</div></section>' +
      '<section style="border-top:1px solid rgba(243,242,242,.13);background:#131210"><div style="max-width:1200px;margin:0 auto;padding:56px 34px">' +
      '<div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--color-accent-400);margin-bottom:22px">Accepted payment</div>' +
      '<div style="display:flex;gap:12px;flex-wrap:wrap">' + logos + '</div></div></section></main>';
  }

  // ── router / render ─────────────────────────────────────────────────────────
  var SCREENS = { home: home, game: game, order: order, checkout: checkout, dashboard: dashboard, boosters: boosters, coaching: coaching, pricing: pricing, about: about };

  function render() {
    var body = (SCREENS[state.screen] || home)();
    document.getElementById('app').innerHTML = header() + body + footer();
  }

  function go(id) { state.screen = id; render(); window.scrollTo(0, 0); }

  // event delegation
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-nav],[data-mode],[data-ft],[data-tt],[data-fd],[data-td],[data-opt],[data-count],[data-pay],[data-terms],[data-paynow],[data-checkout],[data-refresh]');
    if (!t) return;
    if (t.tagName === 'A') e.preventDefault();

    if (t.hasAttribute('data-nav')) return go(t.getAttribute('data-nav'));
    if (t.hasAttribute('data-mode')) { state.mode = t.getAttribute('data-mode'); return render(); }
    if (t.hasAttribute('data-ft')) { var i = +t.getAttribute('data-ft'); state.fromTier = i; if (i >= 8) state.fromDiv = 0; return render(); }
    if (t.hasAttribute('data-tt')) { var j = +t.getAttribute('data-tt'); state.toTier = j; if (j >= 8) state.toDiv = 0; return render(); }
    if (t.hasAttribute('data-fd')) { state.fromDiv = +t.getAttribute('data-fd'); return render(); }
    if (t.hasAttribute('data-td')) { state.toDiv = +t.getAttribute('data-td'); return render(); }
    if (t.hasAttribute('data-opt')) { var k = t.getAttribute('data-opt'); state.opts[k] = !state.opts[k]; return render(); }
    if (t.hasAttribute('data-count')) {
      var inc = t.getAttribute('data-count') === 'inc';
      if (state.mode === 'wins') state.wins = inc ? Math.min(40, state.wins + 1) : Math.max(1, state.wins - 1);
      else state.placements = inc ? Math.min(20, state.placements + 1) : Math.max(1, state.placements - 1);
      return render();
    }
    if (t.hasAttribute('data-pay')) { state.pay = t.getAttribute('data-pay'); return render(); }
    if (t.hasAttribute('data-terms')) { state.terms = !state.terms; return render(); }
    if (t.hasAttribute('data-checkout')) {
      var invalid = state.mode === 'division' && idx(state.toTier, state.toDiv) <= idx(state.fromTier, state.fromDiv);
      if (invalid) return;
      return go('checkout');
    }
    if (t.hasAttribute('data-paynow')) { if (state.terms) { state.paid = true; state.extra = 0; return go('dashboard'); } return; }
    if (t.hasAttribute('data-refresh')) { state.extra = Math.min(9, state.extra + 1); return render(); }
  });

  // coupon: live re-quote without losing focus
  document.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'eb-coupon') {
      state.coupon = e.target.value;
      render();
      var f = document.getElementById('eb-coupon');
      if (f) { f.focus(); var v = f.value.length; try { f.setSelectionRange(v, v); } catch (x) {} }
    }
  });

  render();
})();
