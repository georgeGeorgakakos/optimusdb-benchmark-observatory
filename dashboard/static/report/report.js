/* OptimusDB evaluation report: figures, tables and rule-based text from one run's data (report_data.build), then A4
   pagination. Used by the dashboard's Report page and by the copy saved when a run finishes. No libraries.
   Text rules state facts computed from the data; interpretation comes only from the run's analyst notes file. */
'use strict';
window.OptimusReport = (function () {
  const SYS = ['optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht'];
  const LBL = { optimusdb: 'OptimusDB', corrosion: 'Corrosion', gun: 'Gun.js', autobase: 'Autobase', iroh: 'Iroh docs', opendht: 'OpenDHT' };
  const COL = { optimusdb: '#2a78d6', corrosion: '#eb6834', gun: '#1baf7a', autobase: '#eda100', iroh: '#e87ba4', opendht: '#008300' };
  const INK = '#111111', INK2 = '#4a4945', MUTED = '#85837d', RULE = '#e3e2dc', AXIS = '#bdbcb2', GOOD = '#0ca30c', BAD = '#d03b3b', WARN = '#c98a00';
  const FONT0 = 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif'; let FONT = FONT0;
  const W = 674, PAGE_W = 794, PAGE_H = 1123;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const f1 = v => v == null || isNaN(v) ? '–' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US') : Math.abs(v) >= 100 ? (+v).toFixed(0) : Math.abs(v) >= 10 ? (+v).toFixed(1) : (+v).toFixed(2);
  const ms = v => v == null ? '–' : f1(v) + ' ms';
  const fo = v => v == null || isNaN(v) ? '–' : Math.abs(v - Math.round(v)) < 1e-9 ? Math.round(v).toLocaleString('en-US') : f1(v);
  const pct = v => v == null ? '–' : (+v).toFixed(v >= 10 ? 0 : 1) + ' %';
  const L = s => LBL[s] || s;
  const med = xs => { xs = xs.filter(x => typeof x === 'number' && !isNaN(x)).sort((a, b) => a - b); const n = xs.length; return n ? (n % 2 ? xs[(n - 1) / 2] : (xs[n / 2 - 1] + xs[n / 2]) / 2) : null; };
  const list = a => a.length <= 1 ? (a[0] || '') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
  const recs = n => n >= 1e6 ? '10⁶' : n >= 1e5 ? '10⁵' : n >= 1e4 ? '10⁴' : n >= 1e3 ? '10³' : String(n);
  let D = null, BUILT = {}, figN = 0, tabN = 0;

  /* ---------------------------------------------------------------- svg primitives */
  const T = (x, y, s, o = {}) => `<text x="${x}" y="${y}" font-size="${o.size || 10}" fill="${o.fill || INK2}"${o.anchor ? ` text-anchor="${o.anchor}"` : ''}${o.weight ? ` font-weight="${o.weight}"` : ''}>${esc(s)}</text>`;
  const LN = (x1, y1, x2, y2, c = RULE, w = 1, dash = '') => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''}/>`;
  const R = (x, y, w, h, fill, o = {}) => `<rect x="${x}" y="${y}" width="${Math.max(0, w)}" height="${Math.max(0, h)}" fill="${fill}" rx="${o.rx ?? 2}"${o.op ? ` fill-opacity="${o.op}"` : ''}${o.stroke ? ` stroke="${o.stroke}" stroke-width="${o.sw || 1}"` : ''}/>`;
  const svgWrap = (w, h, inner) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" font-family="${FONT}"><defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="#ffffff" stroke-width="2"/></pattern></defs><rect width="${w}" height="${h}" fill="#ffffff"/>${inner}</svg>`;
  const logS = (min, max, a, b) => { const l0 = Math.log10(min), l1 = Math.log10(max); return v => a + (Math.log10(Math.max(v, min)) - l0) / (l1 - l0) * (b - a); };
  const linS = (min, max, a, b) => v => a + (v - min) / (max - min) * (b - a);
  function logTicks(min, max, decades) { const t = []; for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) for (const m of (decades ? [1] : [1, 3])) { const v = +(m * 10 ** e).toPrecision(3); if (v >= min * 0.999 && v <= max * 1.001) t.push(v); } return t; }
  const tickMs = v => v >= 1000 ? (v / 1000) + ' s' : v + ' ms';
  function niceMax(v) { if (!(v > 0)) return 1; const p = 10 ** Math.floor(Math.log10(v)); for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p; return 10 * p; }
  function linTicks(max, n = 5) { const st = niceMax(max / n); const t = []; for (let v = 0; v <= max + 1e-9; v += st) t.push(+v.toFixed(6)); return t; }
  function hbars(x0, y0, w, rows, o = {}) {
    const lw = o.labelW ?? 92, rowH = o.rowH ?? 15, ax0 = x0 + lw, ax1 = x0 + w - 52;
    const vals = rows.filter(r => r.v != null).map(r => r.v); if (!vals.length) vals.push(1);
    const lo = o.min ?? (o.log ? 10 ** Math.floor(Math.log10(Math.min(...vals) * 0.9)) : 0);
    const hi = o.max ?? (o.log ? 10 ** Math.ceil(Math.log10(Math.max(...vals, o.ref ?? 0) * 1.05)) : niceMax(Math.max(...vals, o.ref ?? 0) * 1.08));
    const sx = o.log ? logS(lo, hi, ax0, ax1) : linS(lo, hi, ax0, ax1);
    let s = o.title ? T(x0, y0 + 9, o.title, { size: 10.5, fill: INK, weight: 700 }) : '';
    const top = y0 + (o.title ? 16 : 2), bot = top + rows.length * rowH;
    (o.log ? logTicks(lo, hi, o.decades) : linTicks(hi, 4)).forEach(t => { const x = sx(t); s += LN(x, top - 2, x, bot) + T(x, bot + 11, o.log ? tickMs(t) : (o.fmt ? o.fmt(t) : t), { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    if (o.ref != null) { const x = sx(o.ref); s += LN(x, top - 4, x, bot + 2, o.refColor || INK, 1.2, '3 2') + T(x + 3, top - 5, o.refLabel || '', { size: 8.5, fill: o.refColor || INK, weight: 650 }); }
    rows.forEach((r, i) => {
      const y = top + i * rowH, h = rowH - 5;
      s += T(ax0 - 6, y + h / 2 + 3.5, r.label, { size: 9.5, anchor: 'end' });
      if (r.v == null) { s += T(ax0 + 4, y + h / 2 + 3.5, r.note || 'n/a', { size: 9, fill: MUTED }); return; }
      const x1 = sx(Math.min(Math.max(r.v, lo), hi));
      s += r.hollow ? R(ax0, y, x1 - ax0, h, '#ffffff', { stroke: r.color, sw: 1.4 }) : R(ax0, y, x1 - ax0, h, r.color, { op: r.op });
      if (r.hatch) s += R(ax0, y, x1 - ax0, h, 'url(#hatch)', { op: 0.9 });
      s += T(x1 + 4, y + h / 2 + 3.5, (r.prefix || '') + (o.vfmt ? o.vfmt(r.v) : f1(r.v)) + (r.note ? ' ' + r.note : ''), { size: 9, fill: INK, weight: r.bold ? 700 : 400 });
    });
    return { svg: s + LN(ax0, top - 2, ax0, bot, AXIS), h: bot + 16 - y0 };
  }
  const present = arr => SYS.filter(s => arr.some(x => x.system === s));

  /* ---------------------------------------------------------------- derived values */
  const e1c = (s, w, size = '2KB') => (D.E1 || []).find(c => c.system === s && c.workload === w && c.doc_size === size);
  function h1v() {
    const wo = SYS.map(s => e1c(s, 'WO')).filter(c => c && c.p99 != null);
    const od = wo.find(c => c.system === 'optimusdb'), base = wo.filter(c => c.system !== 'optimusdb');
    if (!od || !base.length) return null;
    const best = base.reduce((a, b) => a.p99 < b.p99 ? a : b), tr = c => c.p999 && c.p50 ? c.p999 / c.p50 : null;
    const mtr = med(base.map(tr)); return { od, best, base, tr, mtr, limit: 1.25 * best.p99, rank: [...wo].sort((a, b) => a.p99 - b.p99).indexOf(od) + 1, n: wo.length };
  }
  const e3recs = () => [...new Set((D.E3 || []).map(c => c.records))].sort((a, b) => a - b);
  const e3reg = () => e3recs().filter(n => n === 1e5 || n === 1e6);
  const e3show = () => { const r = e3recs(); return r.length ? r[r.length - 1] : null; };
  const e3c = (s, p, q, n) => (D.E3 || []).find(c => c.system === s && c.path === p && c.query === q && c.records === n);
  const TARGETS = [['optimusdb', 'sqlite', 'OptimusDB sqlite'], ['optimusdb', 'crdt', 'OptimusDB crdt'], ['corrosion', 'sql', 'Corrosion'], ['gun', 'client_filter', 'Gun.js'], ['autobase', 'range_client_filter', 'Autobase'], ['iroh', 'prefix_client_filter', 'Iroh docs'], ['opendht', 'key_only', 'OpenDHT']];
  function h3rows(n) {
    return ['Q1', 'Q2', 'Q3'].map(q => {
      const ods = ['sqlite', 'crdt'].map(p => e3c('optimusdb', p, q, n)).filter(c => c && c.mean != null && (c.correct || 0) >= 0.5);
      const cor = e3c('corrosion', 'sql', q, n);
      const cl = TARGETS.slice(3).map(([s, p]) => e3c(s, p, q, n)).filter(c => c && c.mean != null && (c.correct || 0) >= 0.5);
      if (!ods.length) return null;
      const o = ods.reduce((a, b) => a.mean < b.mean ? a : b), fast = cl.length ? cl.reduce((a, b) => a.mean < b.mean ? a : b) : null;
      return { q, n, o, cor, fast, rc: cor && cor.mean ? o.mean / cor.mean : null, rf: fast ? o.mean / fast.mean : null };
    }).filter(Boolean);
  }
  const e4c = (s, o) => (D.E4 || []).find(c => c.system === s && c.offered === o);
  const e4load = () => { const o = [...new Set((D.E4 || []).map(c => c.offered))].filter(x => x > 0); return o.length ? Math.max(...o) : null; };
  function e5cell(s) {
    const cs = (D.E5 || []).filter(c => c.system === s); if (!cs.length) return null;
    const maxCont = Math.max(...cs.map(c => c.contention || 0)); const pick = cs.filter(c => (c.contention || 0) === (cs.some(c => c.contention === 30) ? 30 : maxCont) && (c.shape || '4|4') === '4|4');
    const pool = pick.length ? pick : cs; const maxP = Math.max(...pool.map(c => c.partition_s || 0)); return pool.find(c => c.partition_s === maxP) || pool[0];
  }
  const e5limit = () => D.kind === 'campaign' ? 600 : 120;
  const sat = () => { const ser = D.E2_series || []; if (!ser.length) return null; const big = Math.max(...ser.map(s => s.records || 0)); return ser.filter(s => (s.records || 0) === big); };
  function satOf(s) { const ss = (sat() || []).find(x => x.system === s); if (!ss) return null; return { v: ss.saturation, lower: ss.lower_bound, pts: ss.points }; }
  function limitsNote(r) { const n = r.notes || ''; const m = /node_cpu=([\d.]+)\/(\d+)/.exec(n); return { client: /client_limited=1/.test(n), node: /node_cpu_bound=1/.test(n), nodeCpu: m ? +m[1] : null, nodeLim: m ? +m[2] : null, recorded: /client_cpu=/.test(n) }; }
  const verdictState = h => h === 'H3' && !e3reg().length && D.hypotheses.H3.state !== 'insufficient' ? 'indicative' : D.hypotheses[h].state;
  const modeNote = () => D.kind === 'campaign' ? (D.max_reps >= 10 ? '' : `campaign in progress (${D.max_reps} of 10 repetitions)`) : `indicative (${D.kind} mode)`;

  /* ---------------------------------------------------------------- figures */
  const FIGS = {};
  const fig = (id, title, caption, build) => { FIGS[id] = { title, caption, build }; };
  fig('timeline', 'Run timeline', () => 'Start and end of each scenario from the run log (container clock, UTC; Athens time is UTC+3).', () => {
    const ev = (D.meta.campaign_lines || []).map(l => { const m = /^(\S+)_(\S+) (\w+)(?: (E\d))?/.exec(l); return m && { t: new Date(m[1] + 'T' + m[2] + 'Z').getTime(), k: m[3], e: m[4] }; }).filter(Boolean);
    if (ev.length < 2) return null;
    const t0 = ev[0].t, span = Math.max(1, (ev[ev.length - 1].t - t0) / 60000);
    const bars = [...new Set(ev.filter(x => x.e).map(x => x.e))].map(e => { const b = ev.find(x => x.k === 'begin' && x.e === e), en = ev.find(x => x.k === 'end' && x.e === e); return b && { e, b: (b.t - t0) / 60000, d: ((en || ev[ev.length - 1]).t - t0) / 60000, open: !en }; }).filter(Boolean);
    const mx = niceMax(span), sx = linS(0, mx, 90, W - 50); let s = ''; const top = 6, names = { E1: 'E1 Latency', E2: 'E2 Throughput', E3: 'E3 Queries', E4: 'E4 Edge cost', E5: 'E5 Partitions', E6: 'E6 Trace' };
    linTicks(mx, 6).forEach(t => { s += LN(sx(t), top, sx(t), top + bars.length * 20) + T(sx(t), top + bars.length * 20 + 12, mx > 600 ? (t / 60).toFixed(t % 60 ? 1 : 0) + ' h' : t + ' min', { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    bars.forEach((b, i) => { const y = top + i * 20 + 3; s += T(84, y + 10, names[b.e] || b.e, { size: 9.5, anchor: 'end' }) + R(sx(b.b), y, sx(b.d) - sx(b.b), 13, b.open ? '#8e8e93' : '#3a3a3e') + T(sx(b.d) + 5, y + 10, (b.d - b.b >= 120 ? ((b.d - b.b) / 60).toFixed(1) + ' h' : Math.round(b.d - b.b) + ' min') + (b.open ? ' (not finished)' : ''), { size: 9, fill: INK }); });
    return { svg: svgWrap(W, top + bars.length * 20 + 18, s), csv: [['experiment', 'start_min', 'end_min'], ...bars.map(b => [b.e, b.b.toFixed(1), b.d.toFixed(1)])] };
  });
  fig('lag', 'Load-generator issue delay per run', () => 'Median delay between each operation\'s scheduled and actual issue time (log scale). Dashed: the 10 ms limit of the load-generator check. Hatched: runs in which more than 1 % of operations failed. E1 shows the median over each system\'s runs.', () => {
    const rows = [];
    SYS.forEach(s => { if (D.E1_lag && D.E1_lag[s] != null) rows.push({ label: 'E1 · ' + L(s), v: Math.max(0.5, D.E1_lag[s]), color: COL[s] }); });
    const e2 = [...(D.E2 || [])].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system) || a.offered_ops_s - b.offered_ops_s || a.rep - b.rep);
    const showRep = D.max_reps > 1;
    e2.forEach(r => { const lg = D.E2_lag[r.run_id]; if (lg && lg.p50 != null) rows.push({ label: `E2 · ${L(r.system)} · ${r.offered_ops_s}${r.dataset_records !== (sat() || [{}])[0].records ? ' · ' + recs(r.dataset_records) : ''}${showRep ? ' · r' + r.rep : ''}`, v: Math.max(0.5, lg.p50), color: COL[r.system], hatch: (r.error_rate || 0) > 0.01 }); });
    if (!rows.length) return null;
    const cut = rows.slice(0, 60); const p = hbars(0, 0, W, cut, { log: true, min: 0.5, max: 1000, labelW: 170, rowH: 13, ref: 10, refLabel: '10 ms', refColor: WARN });
    return { svg: svgWrap(W, p.h, p.svg), csv: [['run', 'issue_delay_p50_ms'], ...rows.map(r => [r.label, r.v])], note: rows.length > 60 ? `${rows.length - 60} more runs in the CSV.` : '' };
  });
  fig('e1p99', 'P99 latency by workload and system (2 KB)', () => `${D.max_reps > 1 ? 'Median over repetitions' : 'One run per cell'}; 50 ops/s; log scale, one grid line per factor of 10. WO includes the matchmaking query.`, () => {
    const wls = ['WA', 'WB', 'WC', 'WO'].filter(w => SYS.some(s => e1c(s, w))); if (!wls.length) return null;
    const names = { WA: 'WA · 50 % read, 50 % update', WB: 'WB · 95 % read', WC: 'WC · read only', WO: 'WO · orchestration mix' };
    const pw = (W - 24) / 2; let s = '', hmax = 0;
    wls.forEach((w, i) => { const p = hbars((i % 2) * (pw + 24), Math.floor(i / 2) * 140, pw, SYS.filter(sy => e1c(sy, w)).map(sy => ({ label: L(sy), v: e1c(sy, w).p99, color: COL[sy], bold: sy === 'optimusdb' })), { log: true, min: 1, max: 30000, title: names[w], labelW: 64, decades: true }); s += p.svg; hmax = Math.max(hmax, Math.floor(i / 2) * 140 + p.h); });
    return { svg: svgWrap(W, hmax, s), csv: [['system', 'workload', 'doc_size', 'reps', 'p50_ms', 'p99_ms', 'p999_ms'], ...(D.E1 || []).map(c => [c.system, c.workload, c.doc_size, c.reps, c.p50, c.p99, c.p999])] };
  });
  fig('e1size', 'WO P99 by document size', () => 'Median P99 per system and document size (log scale). The 64 KB series uses 1.25 × 10⁴ records, keeping the data volume per replica equal to the 8 KB series.', () => {
    const sizes = ['256B', '2KB', '8KB', '64KB'].filter(z => SYS.some(s => e1c(s, 'WO', z))); if (sizes.length < 2) return null;
    const h = 230, x0 = 50, x1 = W - 90, y0 = 8, y1 = h - 28, sy = logS(1, 30000, y1, y0), sx = i => x0 + i * (x1 - x0) / (sizes.length - 1); let s = '';
    logTicks(1, 30000, true).forEach(t => { s += LN(x0, sy(t), x1, sy(t)) + T(x0 - 6, sy(t) + 3, tickMs(t), { size: 8.5, fill: MUTED, anchor: 'end' }); });
    sizes.forEach((z, i) => { s += T(sx(i), y1 + 14, z.replace('B', ' B'), { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    SYS.forEach(k => { const pts = sizes.map((z, i) => [i, e1c(k, 'WO', z)?.p99]).filter(p => p[1] != null); if (!pts.length) return;
      s += `<polyline fill="none" stroke="${COL[k]}" stroke-width="${k === 'optimusdb' ? 2.4 : 1.6}" points="${pts.map(p => sx(p[0]) + ',' + sy(p[1])).join(' ')}"/>` + pts.map(p => `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="2.6" fill="${COL[k]}"/>`).join('');
      const l = pts[pts.length - 1]; s += T(sx(l[0]) + 8, sy(l[1]) + 3, L(k), { size: 9, fill: INK }); });
    return { svg: svgWrap(W, h, s + LN(x0, y1, x1, y1, AXIS)), legend: SYS, csv: [['system', ...sizes], ...SYS.map(k => [k, ...sizes.map(z => e1c(k, 'WO', z)?.p99)])] };
  });
  fig('e1q', 'WO latency at increasing percentiles', () => 'Latency of successful WO operations at P50 … P99.9 (log scale), pooled over the runs\' per-operation files. A flat line means a short tail.', () => {
    const Q = D.E1_wo_quantiles || {}; const ks = SYS.filter(k => Q[k] && Q[k].v[0] != null); if (!ks.length) return null;
    const ps = Q[ks[0]].p, h = 240, x0 = 50, x1 = W - 80, y0 = 8, y1 = h - 28, sy = logS(1, 30000, y1, y0), sx = i => x0 + i * (x1 - x0) / (ps.length - 1); let s = '';
    logTicks(1, 30000).forEach(t => { s += LN(x0, sy(t), x1, sy(t)) + T(x0 - 6, sy(t) + 3, tickMs(t), { size: 8.5, fill: MUTED, anchor: 'end' }); });
    ps.forEach((p, i) => { s += T(sx(i), y1 + 14, 'P' + String(+(p * 100).toFixed(1)), { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    const ends = [];
    ks.forEach(k => { const v = Q[k].v; s += `<polyline fill="none" stroke="${COL[k]}" stroke-width="${k === 'optimusdb' ? 2.4 : 1.6}" points="${v.map((y, i) => sx(i) + ',' + sy(y)).join(' ')}"/>` + v.map((y, i) => `<circle cx="${sx(i)}" cy="${sy(y)}" r="2.6" fill="${COL[k]}" stroke="#fff" stroke-width="1"/>`).join(''); ends.push({ k, y: sy(v[v.length - 1]) }); });
    ends.sort((a, b) => a.y - b.y); for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 11) ends[i].y = ends[i - 1].y + 11;
    ends.forEach(e => { s += T(x1 + 8, e.y + 3, L(e.k), { size: 9, fill: INK, weight: e.k === 'optimusdb' ? 700 : 400 }); });
    return { svg: svgWrap(W, h, s + LN(x0, y1, x1, y1, AXIS)), legend: ks, csv: [['system', ...ps.map(p => 'p' + p)], ...ks.map(k => [k, ...Q[k].v])] };
  });
  fig('e1kinds', 'WO by operation kind: OptimusDB and the best baseline', () => { const v = h1v(); return `Bars: P99; white tick: P50. Best baseline = lowest WO P99 among the baselines (${v ? L(v.best.system) : '–'}).`; }, () => {
    const v = h1v(); if (!v) return null; const pair = ['optimusdb', v.best.system], K = D.E1_kinds || {};
    if (!K.optimusdb || !K[v.best.system]) return null;
    const kinds = ['read', 'update', 'insert', 'query'].filter(k => K.optimusdb[k] && K[v.best.system][k]);
    const h = 210, x0 = 40, x1 = W - 10, y0 = 14, y1 = h - 34, mx = niceMax(Math.max(...pair.flatMap(s => kinds.map(k => K[s][k].p99 || 0))) * 1.1);
    const sy = linS(0, mx, y1, y0), gw = (x1 - x0) / kinds.length, bw = Math.min(46, gw / 2 - 8); let s = '';
    linTicks(mx, 5).forEach(t => { s += LN(x0, sy(t), x1, sy(t)) + T(x0 - 6, sy(t) + 3, t + ' ms', { size: 8.5, fill: MUTED, anchor: 'end' }); });
    kinds.forEach((k, i) => { const cx = x0 + gw * i + gw / 2;
      pair.forEach((sys, j) => { const d = K[sys][k], x = cx - bw - 2 + j * (bw + 4); s += R(x, sy(d.p99), bw, y1 - sy(d.p99), COL[sys]) + LN(x + 4, sy(d.p50), x + bw - 4, sy(d.p50), '#ffffff', 2.4) + T(x + bw / 2, sy(d.p99) - 4, f1(d.p99), { size: 9, fill: INK, anchor: 'middle' }) + T(x + bw / 2, y1 + 11, 'P50 ' + f1(d.p50), { size: 8, fill: MUTED, anchor: 'middle' }); });
      s += T(cx, y1 + 25, `${k} (${K.optimusdb[k].n})`, { size: 10, fill: INK, anchor: 'middle', weight: 650 }); });
    return { svg: svgWrap(W, h, s + LN(x0, y1, x1, y1, AXIS)), legend: pair, csv: [['system', 'kind', 'n', 'p50_ms', 'p95_ms', 'p99_ms'], ...pair.flatMap(sy => kinds.map(k => [sy, k, K[sy][k].n, K[sy][k].p50, K[sy][k].p95, K[sy][k].p99]))] };
  });
  fig('h1', 'H1: the two conditions', () => 'Shaded green: the range that satisfies each condition. Top: OptimusDB\'s WO P99 against 1.25 × the best baseline. Bottom: its tail ratio P99.9/P50 against the baselines\' median.', () => {
    const v = h1v(); if (!v || v.mtr == null || v.tr(v.od) == null) return null; let s = '';
    const row = (y, title, val, ref, lim, unit, refLabel) => {
      const mx = niceMax(Math.max(val, lim, ref) * 1.2), sx = linS(0, mx, 150, W - 60); let r = T(0, y + 12, title, { size: 10, fill: INK, weight: 650 });
      r += R(150, y, sx(lim) - 150, 20, '#eefaee', { rx: 0 }) + R(sx(lim), y, W - 60 - sx(lim), 20, '#fdf0f0', { rx: 0 });
      linTicks(mx, 5).forEach(t => { r += LN(sx(t), y + 20, sx(t), y + 24, AXIS) + T(sx(t), y + 34, t + unit, { size: 8.5, fill: MUTED, anchor: 'middle' }); });
      r += LN(sx(lim), y - 4, sx(lim), y + 24, GOOD, 1.4, '3 2') + T(sx(lim) + 3, y - 6, 'limit ' + f1(lim) + unit + (ref === lim ? ' (= ' + refLabel + ')' : ''), { size: 8.5, fill: GOOD, weight: 650 });
      if (ref !== lim) r += LN(sx(ref), y - 4, sx(ref), y + 24, INK2, 1.6) + T(sx(ref) - 3, y - 6, refLabel + ' ' + f1(ref) + unit, { size: 8.5, fill: INK2, anchor: 'end' });
      return r + R(150, y + 6, sx(val) - 150, 8, COL.optimusdb) + T(sx(val) + 4, y + 13, 'OptimusDB ' + f1(val) + unit, { size: 9.5, fill: INK, weight: 700 });
    };
    s += row(16, 'WO P99 (ms)', v.od.p99, v.best.p99, v.limit, ' ms', L(v.best.system)) + row(78, 'Tail ratio P99.9/P50', v.tr(v.od), v.mtr, v.mtr, '×', 'median');
    return { svg: svgWrap(W, 120, s), csv: [['quantity', 'optimusdb', 'reference', 'limit'], ['wo_p99_ms', v.od.p99, v.best.p99, v.limit], ['tail_ratio', v.tr(v.od), v.mtr, v.mtr]] };
  });
  fig('e2', 'Achieved versus offered load (WO)', () => `Dashed diagonal: achieved = offered. Hollow markers: steps with more than 1 % failed operations. ${D.max_reps > 1 ? 'Medians over repetitions. ' : ''}Records: ${recs((sat() || [{}])[0].records || 0)}.`, () => {
    const ser = sat(); if (!ser || !ser.length) return null;
    const mxo = Math.max(...ser.flatMap(s => s.points.map(p => p.offered))), mx = niceMax(mxo * 1.05), h = 256, x0 = 46, x1 = W - 110, y0 = 16, y1 = h - 30, sx = linS(0, mx, x0, x1), sy = linS(0, mx, y1, y0); let s = '';
    linTicks(mx, 5).forEach(t => { s += LN(x0, sy(t), x1, sy(t)) + T(x0 - 6, sy(t) + 3, t, { size: 8.5, fill: MUTED, anchor: 'end' }) + LN(sx(t), y0, sx(t), y1) + T(sx(t), y1 + 13, t, { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    s += LN(sx(0), sy(0), sx(mx), sy(mx), AXIS, 1, '4 3') + T(x0 + 4, y0 - 4, 'achieved ops/s', { size: 8.5, fill: MUTED }) + T(x1, y1 + 25, 'offered ops/s', { size: 8.5, fill: MUTED, anchor: 'end' });
    const ends = [];
    SYS.forEach(k => { const ss = ser.find(x => x.system === k); if (!ss) return; const pts = ss.points.filter(p => p.achieved != null);
      s += `<polyline fill="none" stroke="${COL[k]}" stroke-width="${k === 'optimusdb' ? 2.4 : 1.6}" points="${pts.map(p => sx(p.offered) + ',' + sy(p.achieved)).join(' ')}"/>`;
      pts.forEach(p => { const bad = (p.error_rate || 0) > 0.01; s += `<circle cx="${sx(p.offered)}" cy="${sy(p.achieved)}" r="4" fill="${bad ? '#ffffff' : COL[k]}" stroke="${COL[k]}" stroke-width="${bad ? 1.8 : 1}"/>`; });
      const l = pts[pts.length - 1]; if (l) ends.push({ k, x: sx(l.offered), y: sy(l.achieved), v: l }); });
    ends.sort((a, b) => a.y - b.y); for (let i = 1; i < ends.length; i++) if (Math.abs(ends[i].y - ends[i - 1].y) < 11 && Math.abs(ends[i].x - ends[i - 1].x) < 70) ends[i].y = ends[i - 1].y + 11;
    ends.forEach(e => { s += T(e.x + 8, e.y + 3, L(e.k) + ' ' + f1(e.v.achieved), { size: 9, fill: INK, weight: e.k === 'optimusdb' ? 700 : 400 }); });
    return { svg: svgWrap(W, h, s + LN(x0, y1, x1, y1, AXIS)), legend: SYS.filter(k => ser.some(x => x.system === k)), csv: [['system', 'records', 'offered', 'achieved', 'p99_ms', 'error_rate', 'client_limited'], ...ser.flatMap(x => x.points.map(p => [x.system, x.records, p.offered, p.achieved, p.p99, p.error_rate, p.client_limited ? 1 : 0]))] };
  });
  fig('e2tl', 'Failed steps over time: OptimusDB and Corrosion', () => 'Left: median issue delay of the load generator per 2 s interval. Right: failed operations per 2 s interval. Each line is one failed step (system · offered load).', () => {
    const tl = D.E2_timelines || {}; const ids = Object.keys(tl).slice(0, 4); if (!ids.length) return null;
    const pw = (W - 30) / 2, h = 190, y0 = 18, y1 = h - 28; let s = '';
    const tmax = Math.max(...ids.flatMap(id => tl[id].map(p => p.t + 2))), tmin = Math.min(...ids.flatMap(id => tl[id].map(p => p.t)));
    const sysOf = id => id.split('-')[1], dash = (id, i) => ids.filter(x => sysOf(x) === sysOf(id)).indexOf(id) ? '4 2' : '';
    const panel = (px, key, title, unit) => {
      const mx = niceMax(Math.max(1, ...ids.flatMap(id => tl[id].map(p => p[key] || 0)))), sx = linS(tmin, tmax, px + 40, px + pw - 8), sy = linS(0, mx, y1, y0); let r = T(px, 10, title, { size: 10.5, fill: INK, weight: 700 });
      linTicks(mx, 4).forEach(t => { r += LN(px + 40, sy(t), px + pw - 8, sy(t)) + T(px + 34, sy(t) + 3, t + unit, { size: 8.5, fill: MUTED, anchor: 'end' }); });
      linTicks(tmax, 4).filter(t => t >= tmin).forEach(t => { r += T(sx(t), y1 + 13, t + ' s', { size: 8.5, fill: MUTED, anchor: 'middle' }); });
      ids.forEach((id, i) => { r += `<polyline fill="none" stroke="${COL[sysOf(id)]}" stroke-width="2"${dash(id, i) ? ` stroke-dasharray="${dash(id, i)}"` : ''} points="${tl[id].map(p => sx(p.t + 1) + ',' + sy(p[key] || 0)).join(' ')}"/>`; });
      return r + LN(px + 40, y1, px + pw - 8, y1, AXIS);
    };
    s += panel(0, 'lag50', 'Issue delay (median)', ' ms') + panel(pw + 30, 'err', 'Failed operations', '');
    return { svg: svgWrap(W, h, s), legend: [...new Set(ids.map(sysOf))], csv: [['run', 't_s', 'ok', 'failed', 'issue_delay_p50_ms'], ...ids.flatMap(id => tl[id].map(p => [id, p.t, p.ok, p.err, p.lag50]))], note: 'Steps: ' + ids.map(id => `${L(sysOf(id))} ${id.split('-')[3]} ops/s`).join(', ') + '.' };
  });
  fig('e3', 'Mean query latency', () => `Records: ${recs(e3show() || 0)}. ${D.max_reps > 1 ? 'Median over repetitions of the mean' : 'Mean'} of the measured executions (log scale). Hatched: wrong number of rows. Light bar: OptimusDB's sqlite path.`, () => {
    const n = e3show(); if (n == null) return null; const qs = { Q1: 'Q1 · point lookup', Q2: 'Q2 · status = Running', Q3: 'Q3 · conjunctive range', Q4: 'Q4 · GROUP BY', Q5: 'Q5 · join' };
    const pw = (W - 24) / 2; let s = '', hmax = 0;
    Object.keys(qs).forEach((q, i) => { const rows = TARGETS.filter(([sy, p]) => e3c(sy, p, q, n)).map(([sy, p, l]) => { const c = e3c(sy, p, q, n); return { label: l, v: c.mean, color: COL[sy], op: p === 'sqlite' ? 0.55 : 1, hatch: c.mean != null && (c.correct || 0) < 0.5, note: c.mean == null ? (c.unsupported ? 'unsupported' : 'failed') : '', bold: sy === 'optimusdb' }; });
      if (!rows.length) return; const y = Math.floor(i / 2) * 136, p = hbars((i % 2) * (pw + 24), y, pw, rows, { log: true, min: 0.5, max: 30000, title: qs[q], labelW: 92, rowH: 14, decades: true }); s += p.svg; hmax = Math.max(hmax, y + p.h); });
    return { svg: svgWrap(W, hmax, s), csv: [['system', 'path', 'query', 'records', 'mean_ms', 'p95_ms', 'rows', 'expected', 'correct'], ...(D.E3 || []).map(c => [c.system, c.path, c.query, c.records, c.mean, c.p95, c.rows_returned, c.rows_expected, c.correct])] };
  });
  fig('h3', 'H3: OptimusDB relative to the references', () => `Ratio of OptimusDB's fastest correct path to Corrosion (must be ≤ 1.25) and to the fastest correct client-side system (must be < 1). Log scale. Records: ${list((e3reg().length ? e3reg() : [e3show()]).map(recs))}.`, () => {
    const ns = e3reg().length ? e3reg() : (e3show() != null ? [e3show()] : []); const rows = [];
    ns.forEach(n => h3rows(n).forEach(r => { const sfx = ns.length > 1 ? ` @${recs(n)}` : ''; if (r.rc != null) rows.push({ label: `${r.q}${sfx} vs Corrosion`, v: r.rc, lim: 1.25 }); if (r.rf != null) rows.push({ label: `${r.q}${sfx} vs ${L(r.fast.system)}`, v: r.rf, lim: 1 }); }));
    if (!rows.length) return null;
    const rowH = 20, top = 16, sx = logS(0.01, 4, 170, W - 190), h = top + rows.length * rowH + 22; let s = '';
    [0.01, 0.03, 0.1, 0.3, 1, 3].forEach(t => { s += LN(sx(t), top - 4, sx(t), top + rows.length * rowH) + T(sx(t), top + rows.length * rowH + 12, t + '×', { size: 8.5, fill: MUTED, anchor: 'middle' }); });
    rows.forEach((r, i) => { const y = top + i * rowH + 9, ok = r.lim === 1.25 ? r.v <= r.lim : r.v < r.lim;
      s += T(164, y + 3, r.label, { size: 9.5, anchor: 'end' }) + LN(sx(r.lim), y - 8, sx(r.lim), y + 8, ok ? GOOD : BAD, 1.4, '3 2') + `<circle cx="${sx(Math.min(Math.max(r.v, 0.01), 4))}" cy="${y}" r="5" fill="${ok ? GOOD : BAD}" stroke="#fff" stroke-width="1"/>` + T(W - 180, y + 3, `${f1(r.v)}×  ${ok ? 'meets' : 'fails'} (limit ${r.lim === 1 ? '< 1' : '≤ 1.25'}×)`, { size: 9, fill: ok ? INK : BAD, weight: ok ? 400 : 700 }); });
    return { svg: svgWrap(W, h, s), csv: [['comparison', 'ratio', 'limit'], ...rows.map(r => [r.label, r.v, r.lim])] };
  });
  fig('e4', 'Edge CPU and memory', () => `Median over the four edge containers (limit 1 CPU, 2 GB). Light bar: idle; solid bar: ${e4load()} ops/s WO. Dashed: H4 limits for OptimusDB.`, () => {
    const lo = e4load(); if (lo == null) return null; const pw = (W - 24) / 2, ss = SYS.filter(s => e4c(s, lo));
    const rows = key => ss.flatMap(sy => [{ label: L(sy) + ' idle', v: e4c(sy, 0)?.[key], color: COL[sy], op: 0.4 }, { label: `${L(sy)} ${lo}/s`, v: e4c(sy, lo)?.[key], color: COL[sy], bold: sy === 'optimusdb' }]);
    const a = hbars(0, 0, pw, rows('cpu'), { title: 'CPU (% of one core)', max: 100, labelW: 96, rowH: 13, ref: 60, refLabel: 'H4 60 %', refColor: BAD, vfmt: v => f1(v) + ' %' });
    const b = hbars(pw + 24, 0, pw, rows('rss'), { title: 'Memory (MB)', labelW: 96, rowH: 13, ref: 512, refLabel: 'H4 512 MB', refColor: BAD });
    return { svg: svgWrap(W, Math.max(a.h, b.h), a.svg + b.svg), csv: [['system', 'offered', 'cpu_pct', 'rss_mb', 'disk_mb_per_1k', 'net_kb_per_op'], ...(D.E4 || []).map(c => [c.system, c.offered, c.cpu, c.rss, c.disk, c.net])] };
  });
  fig('e4b', 'Edge disk and network cost under load', () => `At ${e4load()} ops/s. Disk: data volume per 1,000 stored documents. Network: bytes per operation. OpenDHT keeps its data in memory.`, () => {
    const lo = e4load(); if (lo == null) return null; const pw = (W - 24) / 2, ss = SYS.filter(s => e4c(s, lo));
    const a = hbars(0, 0, pw, ss.map(sy => ({ label: L(sy), v: e4c(sy, lo).disk, color: COL[sy], note: e4c(sy, lo).disk == null ? 'in memory' : '', bold: sy === 'optimusdb' })), { title: 'Disk (MB per 1,000 documents)', labelW: 70 });
    const b = hbars(pw + 24, 0, pw, ss.map(sy => ({ label: L(sy), v: e4c(sy, lo).net, color: COL[sy], bold: sy === 'optimusdb' })), { title: 'Network (KB per operation)', labelW: 70 });
    return { svg: svgWrap(W, Math.max(a.h, b.h), a.svg + b.svg), csv: [['system', 'disk_mb_per_1k_docs', 'net_kb_per_op'], ...ss.map(sy => [sy, e4c(sy, lo).disk, e4c(sy, lo).net])] };
  });
  fig('e5', 'Partition behaviour', () => { const ex = SYS.map(e5cell).filter(Boolean); const c0 = ex[0]; return `Per system: the cell with ${c0 ? c0.contention : 30} % contention, split 4 | 4, longest partition measured${D.max_reps > 1 ? ' (medians over repetitions)' : ''}. Hatched: stopped at the ${e5limit()} s convergence limit (true value at least the limit). Right: acknowledged keys not readable at their acknowledged version.`; }, () => {
    const cells = SYS.map(e5cell).filter(Boolean); if (!cells.length) return null; const pw = (W - 24) / 2, lim = e5limit();
    const a = hbars(0, 0, pw, cells.map(c => ({ label: L(c.system), v: c.convergence, color: COL[c.system], hatch: c.convergence >= lim, prefix: c.convergence >= lim ? '≥ ' : '', note: c.convergence == null ? 'not defined' : '', bold: c.system === 'optimusdb' })), { title: 'Convergence (s)', max: niceMax(lim * 1.1), labelW: 70, vfmt: v => f1(v) + ' s' });
    const b = hbars(pw + 24, 0, pw, cells.map(c => ({ label: L(c.system), v: c.ack ? Math.max(0.001, 100 * c.lost / c.ack) : null, color: COL[c.system], bold: c.system === 'optimusdb', note: c.ack ? `(${c.lost}/${c.ack})` : '' })), { title: 'Not readable at acknowledged version (%)', max: 100, labelW: 70, vfmt: v => v < 0.01 ? '0 %' : f1(v) + ' %' });
    return { svg: svgWrap(W, Math.max(a.h, b.h), a.svg + b.svg), csv: [['system', 'contention', 'partition_s', 'shape', 'reps', 'availability', 'ack', 'lost', 'convergence_s', 'identical_share'], ...(D.E5 || []).map(c => [c.system, c.contention, c.partition_s, c.shape, c.reps, c.availability, c.ack, c.lost, c.convergence, c.identical])] };
  });

  fig('glance', 'Results at a glance', () => 'Left: each axis places every system between the worst (inner ring) and the best (outer ring) value measured on that measure, on a log scale; markers at the centre: no valid value (failed, diverged or not supported). Right: the measured values, shaded by the same position, and the hypothesis verdicts. Not a weighted score.', () => {
    if (!window.OptimusSummary) return null;
    const out = window.OptimusSummary.build(window.OptimusSummary.fromReport(D), { font: FONT });
    return out ? { svg: out.svg, csv: out.csv } : null;
  });

  /* ---------------------------------------------------------------- tables */
  function table(cols, rows, caption) {
    return `<table>${caption ? `<caption>${caption}</caption>` : ''}<thead><tr>${cols.map(c => `<th class="${c.n ? 'n' : ''}"${c.w ? ` style="width:${c.w}"` : ''}>${c.h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map((c, i) => `<td class="${c.n ? 'n' : ''}">${r[i] ?? '–'}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }
  const chip = st => st === 'supported' ? '<span class="chip ok">✓ Supported</span>' : st === 'not_supported' ? '<span class="chip no">✕ Not supported</span>' : st === 'indicative' ? '<span class="chip warn">? Undecided</span>' : '<span class="chip na">? Insufficient data</span>';
  const okc = (b, t) => b ? `<span class="chip ok">✓ ${t || 'met'}</span>` : `<span class="chip no">✕ ${t || 'not met'}</span>`;
  const sw = s => `<i class="sw" style="background:${COL[s]}"></i>${L(s)}`;
  const kpiText = { H1: () => { const v = h1v(); return v ? `WO P99 ${ms(v.od.p99)}, ${v.rank === 1 ? 'best' : 'rank ' + v.rank} of ${v.n}` : 'needs E1'; },
    H2: () => { const o = satOf('optimusdb'); return o ? `${o.lower ? '≥ ' : ''}${fo(o.v ?? 0)} ops/s saturation` : 'needs E2'; },
    H3: () => e3reg().length ? `at ${list(e3reg().map(recs))}` : (e3show() ? `decided at 10⁵ and 10⁶` : 'needs E3'),
    H4: () => { const c = e4c('optimusdb', e4load()); return c ? `${pct(c.cpu)} CPU · ${f1(c.rss)} MB` : 'needs E4'; },
    H5: () => { const c = e5cell('optimusdb'); return c ? `${c.lost} lost · ${f1(c.convergence)} s` : 'needs E5'; } };
  const TABLES = {
    hyp: () => table([{ h: 'Hyp.', w: '38px' }, { h: 'Verdict', w: '118px' }, { h: 'Evidence (computed)' }], ['H1', 'H2', 'H3', 'H4', 'H5'].map(h => [`<b>${h}</b>`, chip(verdictState(h)), esc(D.hypotheses[h].text) + (D.hypotheses[h].detail ? `<div class="muted" style="font-size:.92em;margin-top:3px">${esc(D.hypotheses[h].detail)}</div>` : '')])),
    systems: () => [['optimusdb', 'Documents in a Merkle-CRDT log over IPFS (OrbitDB); embedded SQLite', 'Criteria queries with operators; SQL on its SQLite store', (D.meta.commit || '').slice(0, 7) || '–'],
      ['corrosion', 'SQLite tables replicated with cr-sqlite CRDTs over gossip', 'SQL', 'ef243dd'], ['gun', 'Graph of nodes with HAM conflict resolution', 'Key lookup; client filtering', '0.2020.1239'],
      ['autobase', 'Multi-writer append-only logs (Hypercore) with a Hyperbee view', 'Key and range scans; client filtering', '7.28.2'], ['iroh', 'Key-value documents with range-based set reconciliation', 'Key and prefix; client filtering', '0.101.0'],
      ['opendht', 'Distributed hash table (Kademlia); values on the closest nodes', 'Key lookup only', 'v4.4.1']].map(r => `<tr><td>${sw(r[0])}</td><td>${r[1]}</td><td>${r[2]}</td><td class="mono">${r[3]}</td></tr>`).join(''),
    settings: () => { const s = D.meta.settings && D.meta.settings.optimusdb; if (!s) return '<p class="note">No runtime-settings.json in this run.</p>';
      const why = { OPTIMUSDB_LOG_LEVEL: 'warnings only, as for Corrosion and Iroh', GOGC: 'fewer garbage collections at moderate memory cost', GOMAXPROCS: 'container CPU limit, rounded up (Go 1.19 ignores cgroups)', GOMEMLIMIT: '80 % of the container memory limit', OPTIMUSDB_ARGS: 'internal metrics sampling off', OPTIMUSDB_IPFS_KEY: 'Ed25519 node key (kubo default since v0.13)', OPTIMUSDB_IPFS_PROVIDE: 'no DHT announcement per block; peers are connected directly', OPTIMUSDB_IPFS_SYNC: 'no fsync per write, like Corrosion\'s synchronous=NORMAL', OPTIMUSDB_HEADS_INTERVAL: 'latest log entries re-announced every 10 s (large ones when changed, at least every 60 s), so replicas catch up after a partition', OPTIMUSDB_RECONNECT_INTERVAL: 'lost peer connections dialled again every 10 s' };
      const tiers = Object.keys(s); const keys = Object.keys(s[tiers[0]]);
      return table([{ h: 'Setting' }, ...tiers.map(t => ({ h: t })), { h: 'Reason' }], keys.map(k => [`<span class="mono">${k}</span>`, ...tiers.map(t => `<span class="mono">${esc(s[t][k])}</span>`), why[k] || ''])); },
    build: () => { const c = D.meta.campaign; return table([{ h: 'Check', w: '160px' }, { h: 'Value' }, { h: 'Result', w: '74px' }], [
      ['OptimusDB source', D.meta.commit ? `<span class="mono">${esc(D.meta.commit)}</span><br>${esc(D.meta.commit_msg)}` : 'not found in the fresh-start log', D.meta.commit ? okc(true, 'found') : okc(false, 'missing')],
      ['Runtime settings', D.meta.settings ? 'recorded in runtime-settings.json' : 'not recorded', okc(!!D.meta.settings, D.meta.settings ? 'recorded' : 'missing')],
      ['Run log', c ? `${esc(c.log)} · planned ${esc(c.planned.join(', '))}` : 'no run log', c ? okc(c.finished && !c.failed.length, c.finished ? (c.failed.length ? 'errors' : 'finished') : 'not finished') : okc(false, 'missing')],
      ['Result files', `${D.meta.files.results} experiments · ${D.meta.files.ops} per-operation files · ${D.meta.files.logs} logs`, okc(D.meta.files.results > 0, 'present')],
      ['Analysis', Object.keys(D.errors || {}).length ? esc(Object.entries(D.errors).map(([k, v]) => k + ': ' + v).join('; ')) : 'every result file analysed', okc(!Object.keys(D.errors || {}).length, Object.keys(D.errors || {}).length ? 'errors' : 'ok')]]); },
    completion: () => table([{ h: 'System' }, ...['E1', 'E2', 'E3', 'E4', 'E5'].map(e => ({ h: e, n: 1 }))], SYS.map(s => [sw(s), ...['E1', 'E2', 'E3', 'E4', 'E5'].map(e => (D.completion[s] || {})[e] || 0)]), 'Finished runs per system and experiment'),
    flags: () => table([{ h: 'Exp.' }, { h: 'Not replicated in time', n: 1 }, { h: 'Unsupported', n: 1 }, { h: 'Dropped ops', n: 1 }, { h: 'Node died', n: 1 }, { h: 'Client-limited', n: 1 }], ['E1', 'E2', 'E3', 'E4', 'E5'].map(e => { const f = D.flags[e] || {}; return [e, f.settle_timeout || 0, f.unsupported || 0, f.dropped || 0, f.node_down || 0, f.client_limited || 0]; }), 'Data-quality flags counted from the notes column'),
    e1: () => table([{ h: 'System' }, { h: 'Workload' }, { h: 'Size' }, { h: 'Reps', n: 1 }, { h: 'Errors', n: 1 }, { h: 'P50', n: 1 }, { h: 'P95', n: 1 }, { h: 'P99', n: 1 }, { h: 'P99.9', n: 1 }, { h: 'ops/s', n: 1 }],
      [...(D.E1 || [])].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system) || a.workload.localeCompare(b.workload)).map(c => [sw(c.system), c.workload, c.doc_size, c.reps, c.error_pct == null ? '–' : pct(c.error_pct), f1(c.p50), f1(c.p95), f1(c.p99), f1(c.p999), f1(c.achieved)]), `E1 results in milliseconds (${D.max_reps > 1 ? 'medians over repetitions' : 'one run per cell'})`),
    h1: () => { const v = h1v(); if (!v) return '<p class="note">H1 needs E1 WO results for OptimusDB and at least one baseline.</p>'; const t = v.tr(v.od);
      return table([{ h: 'Condition' }, { h: 'OptimusDB', n: 1 }, { h: 'Reference', n: 1 }, { h: 'Limit', n: 1 }, { h: 'Result' }], [
        ['WO P99 within 25 % of the best baseline', ms(v.od.p99), `${L(v.best.system)} ${ms(v.best.p99)}`, '≤ ' + ms(v.limit), okc(v.od.p99 <= v.limit)],
        ['Tail ratio P99.9/P50 not above the baselines\' median', t == null ? '–' : f1(t) + '×', 'median ' + f1(v.mtr) + '× of ' + v.base.map(c => L(c.system) + ' ' + f1(v.tr(c))).join(', '), '≤ ' + f1(v.mtr) + '×', okc(t != null && v.mtr != null && t <= v.mtr)]]); },
    e2: () => { const rows = [...(D.E2 || [])].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system) || (a.dataset_records || 0) - (b.dataset_records || 0) || a.offered_ops_s - b.offered_ops_s || a.rep - b.rep);
      return table([{ h: 'System' }, { h: 'Records', n: 1 }, { h: 'Offered', n: 1 }, { h: 'Rep', n: 1 }, { h: 'Achieved', n: 1 }, { h: 'P99 (ms)', n: 1 }, { h: 'Errors', n: 1 }, { h: 'Issue delay', n: 1 }, { h: 'Limit' }],
        rows.map(r => { const ln = limitsNote(r), lg = D.E2_lag[r.run_id]; return [sw(r.system), recs(r.dataset_records), r.offered_ops_s, r.rep, f1(r.achieved_ops_s), f1(r.p99_ms), pct(100 * (r.error_rate || 0)), lg ? ms(lg.p50) : '–', ln.client ? '<span class="chip warn">client</span>' : ln.node ? '<span class="chip no">node CPU</span>' : ln.recorded ? '<span class="chip na">neither</span>' : '<span style="color:#85837d">not recorded</span>']; }), 'E2 runs; “Limit” is the load-generator check (client = generator was the limit, node CPU = node at its CPU limit)'); },
    h2: () => { const ser = sat(); if (!ser) return '<p class="note">H2 needs E2 results.</p>'; const base = ser.filter(s => s.system !== 'optimusdb');
      const vals = base.map(s => s.saturation == null ? (s.lower_bound ? null : 0) : s.saturation).filter(v => v != null); const m = med(vals), o = satOf('optimusdb');
      return table([{ h: 'System' }, { h: 'Saturation (ops/s)', n: 1 }, { h: 'Note' }], [...ser.sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system)).map(s => [sw(s.system), s.saturation == null ? (s.lower_bound ? 'not measurable' : '0') : (s.lower_bound ? '≥ ' : '') + fo(s.saturation),
        s.saturation == null ? (s.lower_bound ? 'load generator was the limit from the first step' : 'did not keep up at the lowest load (counts as 0)') : s.lower_bound ? 'next step failed while the load generator was the limit' : (() => { const f = s.points.find(p => p.offered > s.saturation); return f ? `fails at ${f.offered} ops/s (${pct(100 * (f.error_rate || 0))} errors)` : 'kept up at every step'; })()]),
        ['<b>Baselines\' median</b>', `<b>${fo(m)}</b>`, o && o.v != null && m != null ? `OptimusDB ${fo(o.v)} vs ${fo(m)}: first clause ${okc(o.v >= m)}` : '–']]); },
    e3: () => { const n = e3show(); return table([{ h: 'Target' }, ...['Q1', 'Q2', 'Q3', 'Q4', 'Q5'].map(q => ({ h: q + ' mean / P95', n: 1 }))], TARGETS.filter(([s, p]) => (D.E3 || []).some(c => c.system === s && c.path === p && c.records === n)).map(([s, p, l]) => [`<i class="sw" style="background:${COL[s]}"></i>${l}`, ...['Q1', 'Q2', 'Q3', 'Q4', 'Q5'].map(q => { const c = e3c(s, p, q, n); if (!c || c.mean == null) return `<span style="color:#85837d">${c && c.unsupported ? 'unsupported' : 'failed'}</span>`; return `${f1(c.mean)} / ${f1(c.p95)}${(c.correct || 0) < 0.5 ? ` <span class="chip no">${f1(c.rows_returned)} rows</span>` : ''}`; })]), `E3 latency in milliseconds at ${recs(n || 0)} records; a red chip marks a wrong row count`); },
    h3: () => { const ns = e3reg().length ? e3reg() : (e3show() != null ? [e3show()] : []); const rows = ns.flatMap(n => h3rows(n));
      if (!rows.length) return '<p class="note">H3 needs correct E3 answers from OptimusDB.</p>';
      return table([{ h: 'Query' }, { h: 'Records', n: 1 }, { h: 'OptimusDB best (path)', n: 1 }, { h: 'Corrosion', n: 1 }, { h: 'Ratio', n: 1 }, { h: 'Fastest client-side', n: 1 }, { h: 'Result' }], rows.map(r => [r.q, recs(r.n), `${ms(r.o.mean)} (${r.o.path})`, r.cor ? ms(r.cor.mean) : '–', r.rc == null ? '–' : f1(r.rc) + '×', r.fast ? `${L(r.fast.system)} ${ms(r.fast.mean)}` : '–',
        (r.rc == null || r.rc <= 1.25) && (r.rf == null || r.rf < 1) ? okc(true, 'both') : okc(false, r.rc != null && r.rc > 1.25 ? 'over 1.25 × Corrosion' : 'client-side faster')])); },
    e4: () => { const lo = e4load(); return table([{ h: 'System' }, { h: 'CPU idle', n: 1 }, { h: `CPU ${lo}/s`, n: 1 }, { h: 'RSS idle (MB)', n: 1 }, { h: `RSS ${lo}/s (MB)`, n: 1 }, { h: 'Disk MB / 1k docs', n: 1 }, { h: 'KB / op', n: 1 }], SYS.filter(s => e4c(s, lo)).map(s => [sw(s), pct(e4c(s, 0)?.cpu), pct(e4c(s, lo).cpu), f1(e4c(s, 0)?.rss), f1(e4c(s, lo).rss), f1(e4c(s, lo).disk), f1(e4c(s, lo).net)]), 'E4 medians over the four edge containers'); },
    h4: () => { const c = e4c('optimusdb', e4load()); if (!c) return '<p class="note">H4 needs E4 results for OptimusDB.</p>'; return table([{ h: 'Condition' }, { h: `OptimusDB at ${e4load()} ops/s`, n: 1 }, { h: 'Limit', n: 1 }, { h: 'Margin', n: 1 }, { h: 'Result' }], [
      ['CPU', pct(c.cpu), '60 %', f1(60 - c.cpu) + ' points', okc(c.cpu < 60)], ['Resident memory', f1(c.rss) + ' MB', '512 MB', f1(512 - c.rss) + ' MB', okc(c.rss < 512)]]); },
    e5: () => table([{ h: 'System' }, { h: 'Cont.', n: 1 }, { h: 'Part.', n: 1 }, { h: 'Shape' }, { h: 'Reps', n: 1 }, { h: 'Avail.', n: 1 }, { h: 'Ack. keys', n: 1 }, { h: 'Lost', n: 1 }, { h: 'Convergence', n: 1 }, { h: 'Identical', n: 1 }],
      [...(D.E5 || [])].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system)).map(c => [sw(c.system), (c.contention ?? '–') + ' %', (c.partition_s ?? '–') + ' s', esc(c.shape || ''), c.reps, pct(c.availability), c.ack, c.lost, c.convergence == null ? 'n/a' : (c.convergence >= e5limit() ? '≥ ' + e5limit() + ' s' : f1(c.convergence) + ' s'), c.identical == null ? 'n/a' : Math.round(100 * c.identical) + ' %']), 'E5 cells (sums of keys over repetitions; medians of availability and convergence)'),
    e5states: () => (D.E5_states || []).length ? table([{ h: 'Run', w: '120px' }, { h: 'Documents and content hash per host when the limit was reached' }], D.E5_states.map(x => [`<span class="mono">${esc(x.run)}</span>`, `<span class="mono">${esc(x.states)}</span>`])) : '',
    h5: () => { const os = (D.E5 || []).filter(c => c.system === 'optimusdb'); if (!os.length) return '<p class="note">H5 needs E5 results for OptimusDB.</p>';
      const bc = SYS.filter(s => ['corrosion', 'gun', 'autobase', 'iroh'].includes(s)).map(e5cell).filter(c => c && c.convergence != null); const m = med(bc.map(c => c.convergence)); const oc = med(os.map(c => c.convergence));
      return table([{ h: 'Condition' }, { h: 'OptimusDB', n: 1 }, { h: 'Reference', n: 1 }, { h: 'Result' }], [
        ['Accepts writes on both sides', 'min ' + pct(Math.min(...os.map(c => c.availability ?? 0))), '> 0 %', okc(Math.min(...os.map(c => c.availability ?? 0)) > 0)],
        ['No acknowledged write lost', String(os.reduce((a, c) => a + c.lost, 0)), '0', okc(os.every(c => c.lost === 0))],
        ['Replicas identical in every run', os.every(c => (c.identical || 0) === 1) ? 'yes' : 'no', 'yes', okc(os.every(c => (c.identical || 0) === 1))],
        ['Convergence not above the replicating baselines\' median', f1(oc) + ' s', `median ${f1(m)} s of ${bc.map(c => `${L(c.system)} ${c.convergence >= e5limit() ? '≥ ' : ''}${f1(c.convergence)}`).join(', ')}`, okc(oc != null && (m == null || oc <= m))]]); },
    stats: () => { const st = (D.E1_stats || []).filter(r => r.p != null); if (!st.length) return ''; return table([{ h: 'Workload' }, { h: 'Baseline' }, { h: 'p (Mann–Whitney)', n: 1 }, { h: 'p (Holm)', n: 1 }, { h: 'Cliff\'s δ', n: 1 }, { h: 'Reading' }], st.map(r => [r.workload, sw(r.baseline), r.p.toFixed(4), r.p_holm == null ? '–' : r.p_holm.toFixed(4), r.cliffs_delta == null ? '–' : r.cliffs_delta.toFixed(2), r.p_holm != null && r.p_holm < 0.05 ? (r.cliffs_delta < 0 ? 'OptimusDB lower P99' : 'baseline lower P99') : 'no significant difference'])); },
    raw: e => { const rows = D[e + '_raw'] || []; if (!rows.length) return '';
      const want = { E1: ['run_id', 'ops', 'errors', 'mean_ms', 'p50_ms', 'p95_ms', 'p99_ms', 'p999_ms', 'achieved_ops_s'], E2: ['run_id', 'achieved_ops_s', 'p99_ms', 'error_rate', 'bottleneck'],
        E3: ['run_id', 'mean_ms', 'p95_ms', 'rows_returned', 'rows_expected', 'correct'], E4: ['run_id', 'started_ok', 'cpu_pct', 'rss_mb', 'disk_mb_per_1k_docs', 'net_kb_per_op'],
        E5: ['run_id', 'write_availability_pct', 'ack_writes', 'lost_ack_writes', 'divergent_entries', 'convergence_s', 'replicas_identical', 'keys_readable_pct'] }[e] || Object.keys(rows[0]);
      const cols = want.filter(k => k in rows[0]); const num = v => typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en-US') : f1(v)) : esc(v ?? '');
      const head = `<thead><tr>${cols.map(k => `<th class="${k === 'run_id' ? '' : 'n'}"${k === 'run_id' ? ' style="width:150px"' : ''}>${esc(k.replace(/_/g, ' '))}</th>`).join('')}</tr></thead>`;
      const body = rows.map(r => `<tr>${cols.map(k => k === 'run_id' ? `<td class="rawid">${esc(r[k])}</td>` : `<td class="n">${num(r[k])}</td>`).join('')}</tr>` + (r.notes ? `<tr class="note-row"><td colspan="${cols.length}"><span class="mono">${esc(r.notes)}</span></td></tr>` : '')).join('');
      return `<table><caption>${e}_raw.csv (notes on the line below each run)</caption>${head}<tbody>${body}</tbody></table>`; },
  };

  /* ---------------------------------------------------------------- rule-based text */
  const P = s => `<p>${s}</p>`, NOTE = (cls, s) => `<div class="note ${cls}">${s}</div>`;
  function sumE1() { const v = h1v(); if (!v) return null; const K = D.E1_kinds || {}; const b = v.best.system;
    let s = `<b>Latency (E1).</b> Under the orchestration mix WO at 50 ops/s, OptimusDB's P99 was ${ms(v.od.p99)}, ${v.rank === 1 ? `the lowest of the ${v.n} systems` : `rank ${v.rank} of ${v.n}`}; the best baseline was ${L(b)} at ${ms(v.best.p99)}.`;
    if (K.optimusdb && K[b]) { const kinds = ['read', 'update', 'insert', 'query'].filter(k => K.optimusdb[k] && K[b][k]); const faster = kinds.filter(k => K.optimusdb[k].p50 < K[b][k].p50), slower = kinds.filter(k => K.optimusdb[k].p50 > K[b][k].p50);
      if (faster.length) s += ` At P50, OptimusDB is faster on ${list(faster)}`; if (slower.length) s += `${faster.length ? ' and' : ' At P50,'} ${L(b)} is faster on ${list(slower)}`; if (faster.length || slower.length) s += '.'; }
    return s; }
  function sumE2() { const ser = sat(); if (!ser) return null; const o = satOf('optimusdb'); const base = ser.filter(s => s.system !== 'optimusdb');
    const m = med(base.map(s => s.saturation == null ? (s.lower_bound ? null : 0) : s.saturation).filter(x => x != null));
    let s = `<b>Throughput (E2).</b> At ${recs(ser[0].records || 0)} records OptimusDB kept up to ${o ? (o.lower ? 'at least ' : '') + fo(o.v ?? 0) : '–'} ops/s; the baselines' median is ${fo(m)} ops/s (${base.map(x => `${L(x.system)} ${x.saturation == null ? (x.lower_bound ? 'n/a' : 0) : (x.lower_bound ? '≥ ' : '') + fo(x.saturation)}`).join(', ')}).`;
    const late = (D.E2 || []).filter(r => (r.error_rate || 0) > 0.01 && D.E2_lag[r.run_id] && D.E2_lag[r.run_id].p50 > 10);
    if (late.length) s += ` In ${late.length} failed step${late.length > 1 ? 's' : ''} the load generator issued operations more than 10 ms late (chapter on E2).`;
    return s; }
  function sumE3() { const n = e3show(); if (n == null) return null; const od = (D.E3 || []).filter(c => c.system === 'optimusdb' && c.records === n);
    const wrong = od.filter(c => c.mean != null && (c.correct || 0) < 0.5), un = od.filter(c => c.mean == null);
    let s = `<b>Queries (E3).</b> ${wrong.length || un.length ? `OptimusDB answered ${od.length - wrong.length - un.length} of ${od.length} query–path combinations correctly` : 'OptimusDB answered every query correctly on both of its query paths'} at ${recs(n)} records.`;
    const ns = e3reg().length ? e3reg() : [n]; const rows = ns.flatMap(x => h3rows(x));
    const cor = rows.filter(r => r.rc != null), fail = rows.filter(r => r.rf != null && r.rf >= 1);
    if (cor.length) s += ` Against Corrosion its ratios on Q1–Q3 are ${cor.map(r => f1(r.rc)).join(', ')} (limit 1.25).`;
    if (fail.length) s += ` Client-side evaluation was faster on ${list(fail.map(r => `${r.q} (${L(r.fast.system)} ${ms(r.fast.mean)} vs ${ms(r.o.mean)})`))}.`;
    if (!e3reg().length) s += ` H3 is registered at 10⁵ and 10⁶ records, so at ${recs(n)} the verdict is indicative.`;
    return s; }
  function sumE4() { const lo = e4load(), c = e4c('optimusdb', lo); if (!c) return null; const rank = SYS.filter(s => e4c(s, lo) && e4c(s, lo).rss != null).sort((a, b) => e4c(b, lo).rss - e4c(a, lo).rss).indexOf('optimusdb') + 1;
    return `<b>Edge cost (E4).</b> At ${lo} ops/s on an edge-sized container OptimusDB used ${pct(c.cpu)} CPU and ${f1(c.rss)} MB (H4 limits 60 % and 512 MB); its memory ranks ${rank} of ${SYS.filter(s => e4c(s, lo)).length}, highest first.`; }
  function sumE5() { const os = (D.E5 || []).filter(c => c.system === 'optimusdb'); if (!os.length) return null; const c = e5cell('optimusdb');
    const bc = ['corrosion', 'gun', 'autobase', 'iroh'].map(e5cell).filter(x => x && x.convergence != null); const fastest = bc.length ? bc.reduce((a, b) => a.convergence < b.convergence ? a : b) : null;
    return `<b>Partitions (E5).</b> OptimusDB accepted ${pct(Math.min(...os.map(x => x.availability ?? 0)))} of writes during the split (lowest over its cells), lost ${os.reduce((a, x) => a + x.lost, 0)} acknowledged writes in total and converged in ${f1(c.convergence)} s in its main cell${fastest ? `; the fastest replicating baseline took ${f1(fastest.convergence)} s (${L(fastest.system)})` : ''}.`; }
  function supportText() {
    if (D.kind === 'campaign' && D.max_reps >= 10) return P('All cells have the campaign\'s repetitions; the statistics chapter tests the differences. Verdicts are as registered.');
    return P(`${D.max_reps <= 1 ? 'One repetition per cell' : `Up to ${D.max_reps} repetitions per cell`}${D.kind !== 'campaign' ? ', short measurement windows and reduced grids make every number indicative' : ', so the campaign is not complete'}. This report is suited to checking the pipeline and spotting problems; it does not support significance claims, which need the campaign (10 repetitions, 300 s windows, 10⁵–10⁶ records).`);
  }
  function md(text) {   // tiny Markdown subset for the analyst notes: headings, bullets, bold, paragraphs
    const inl = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<span class="mono">$1</span>');
    const out = []; let ul = null;
    text.split(/\r?\n/).forEach(l => { const t = l.trim();
      if (/^[-*] /.test(t)) { if (!ul) { ul = []; } ul.push(`<li>${inl(t.slice(2))}</li>`); return; }
      if (ul) { out.push(`<ul>${ul.join('')}</ul>`); ul = null; }
      if (!t) return; const h = /^(#{1,3}) (.*)$/.exec(t); out.push(h ? `<h${h[1].length + 1}>${inl(h[2])}</h${h[1].length + 1}>` : `<p>${inl(t)}</p>`); });
    if (ul) out.push(`<ul>${ul.join('')}</ul>`); return out;
  }

  /* ---------------------------------------------------------------- chapters */
  function sec(name, src, inner) { return `<section data-chapter="${esc(name)}" data-src="${src}">${inner}</section>`; }
  const FIG = id => `<figure class="fig" data-fig="${id}"></figure>`, TAB = id => `<div data-table="${id}"></div>`;
  function buildChapters(tpl) {
    const fixed = {}; const t = document.createElement('div'); t.innerHTML = tpl; t.querySelectorAll('section[data-fixed]').forEach(s => { fixed[s.dataset.fixed] = s.outerHTML; });
    const out = []; let n = 0; const num = () => ++n; const fx = k => { const c = num(); return (fixed[k] || '').replace(/\{n\}/g, c); };
    const has = e => (D.completion && SYS.some(s => (D.completion[s] || {})[e] > 0));
    out.push(sec('Contents', 'fixed', `<div class="chn">Report structure</div><h1 class="ch">Contents</h1><ol class="toc" id="toc"></ol><div class="note">Every figure and table is computed from the result files of this run (${esc(D.meta.folder)}). Verdicts use the same code as the dashboard's “Findings &amp; hypotheses” page. Each figure exports as SVG or PNG and its data as CSV.</div>`));
    let c = num();
    out.push(sec(`${c}. Executive summary`, 'rule', `<div class="chn">Chapter ${c}</div><h1 class="ch" data-toc="${c}. Executive summary">Executive summary</h1>
      <p class="lede">This ${esc(D.meta.label)} ran ${esc(list(['E1', 'E2', 'E3', 'E4', 'E5'].filter(has)))} on the eight-host emulated edge–fog–cloud testbed${D.max_reps > 1 ? `, up to ${D.max_reps} repetitions per cell` : ', once per cell'}.${D.meta.campaign && !D.meta.campaign.finished ? ' The run did not reach its end; finished experiments are reported.' : ''}</p>
      <div data-block="kpis"></div>${FIGS.glance.build() ? FIG('glance') : ''}<h2>Hypotheses at a glance</h2>${TAB('hyp')}<h2>Main findings</h2><ul>${[sumE1(), sumE2(), sumE3(), sumE4(), sumE5()].filter(Boolean).map(x => `<li>${x}</li>`).join('')}</ul>
      <h2>What this run can and cannot support</h2>${supportText()}${(D.observations || []).length ? P(`<b>${D.observations.length} automatic observation${D.observations.length > 1 ? 's' : ''}</b> about this run are listed in the integrity chapter.`) : ''}`));
    if (D.notes) out.push(sec('Analyst notes', 'notes', `<div class="chn">Written after review · ${esc(D.notes_path)}</div><h1 class="ch" data-toc="Analyst notes">Analyst notes</h1><p class="lede">Interpretation that the data alone cannot establish, written by a person after reviewing this run and shown unchanged. Everything else in the report is generated from the result files.</p>${md(D.notes).join('')}`));
    out.push(fx('scope')); out.push(fx('method'));
    c = num();
    const obs = D.observations || [];
    out.push(sec(`${c}. Run integrity`, 'rule', `<div class="chn">Chapter ${c}</div><h1 class="ch" data-toc="${c}. Run integrity">Run integrity</h1><p class="lede">Was the intended code built, did every scenario finish, and did anything happen during the run that limits what a result can show?</p>
      <h2>Build and configuration</h2>${TAB('build')}${FIGS.timeline.build() ? `<h2>Timeline</h2>${FIG('timeline')}` : ''}<h2>Completion and data-quality flags</h2>${TAB('completion')}${TAB('flags')}
      <h2>Automatic observations</h2>${obs.length ? `<p>Facts found in the result files and logs, without interpretation. Causes, where known, are in the analyst notes.</p><ul class="obs">${obs.map(o => `<li><span class="lv ${o.level}">${o.level === 'bad' ? 'Problem' : 'Check'}${o.exp ? ' · ' + o.exp : ''}</span><span>${esc(o.text)}</span></li>`).join('')}</ul>` : P('None: no flags, failed checks or warnings in the result files and logs.')}
      ${FIGS.lag.build() ? `<h2>Was the load generator keeping up?</h2>${P('The load generator is one Python process; if it runs short of CPU it issues operations late and every system looks slow. The delay between each operation\'s scheduled and actual issue time shows this directly.')}${FIG('lag')}` : ''}`));
    if (has('E1')) { c = num(); const v = h1v();
      const y = ['WA', 'WB', 'WC'].map(w => SYS.map(s => e1c(s, w)).filter(x => x && x.p99 != null).sort((a, b) => a.p99 - b.p99)).filter(a => a.length);
      const yText = y.length ? P(`On the YCSB workloads the lowest P99 belongs to ${list(y.map(a => `${L(a[0].system)} under ${a[0].workload} (${ms(a[0].p99)})`))}; OptimusDB's P99 is ${list(['WA', 'WB', 'WC'].map(w => e1c('optimusdb', w)).filter(Boolean).map(x => `${ms(x.p99)} (${x.workload})`))}.`) : '';
      const bad = (D.E1 || []).filter(x => (x.error_pct || 0) > 1);
      out.push(sec(`${c}. E1 Latency`, 'rule', `<div class="chn">Chapter ${c} · RQ2 · H1</div><h1 class="ch" data-toc="${c}. E1 · Latency and tail behaviour">E1 · Latency and tail behaviour</h1><p class="lede">How fast does each system answer at a moderate, steady load of 50 operations per second, including its slowest requests?</p>
        <h2>Design</h2>${P('Each system runs on all eight hosts with the preloaded documents; the client sends every operation to cloud-a. OptimusDB answers reads and queries from its local replica first (<span class="mono">LOCAL_THEN_REMOTE_MERGE</span>) and asks peers only when it has no matching rows.')}
        <h2>Results</h2>${FIG('e1p99')}${TAB('e1')}${yText}${bad.length ? NOTE('warn', `More than 1 % of operations failed in ${list(bad.map(x => `${L(x.system)} ${x.workload} ${x.doc_size} (${pct(x.error_pct)})`))}; their latency describes only the operations that succeeded.`) : ''}
        ${FIGS.e1size.build() ? FIG('e1size') : ''}${FIG('e1q')}${v && FIGS.e1kinds.build() ? `<h2>Where the WO tail comes from</h2>${P('WO mixes single-document operations with a matchmaking query that returns about 1/16 of the records. Queries are 10 % of operations, so the WO P99 falls inside the query distribution when queries are the slowest kind.')}${FIG('e1kinds')}` : ''}
        <h2>Hypothesis H1</h2>${FIGS.h1.build() ? FIG('h1') : ''}${TAB('h1')}${D.hypotheses.H1.detail && /note:/.test(D.hypotheses.H1.detail) ? P(`<b>Comparison detail (does not change the verdict).</b> ${esc(D.hypotheses.H1.detail.slice(D.hypotheses.H1.detail.indexOf('note:') + 5).trim())}`) : ''}${v ? NOTE(D.hypotheses.H1.state === 'supported' ? 'ok' : 'bad', `<b>H1 ${D.hypotheses.H1.state === 'supported' ? 'supported' : 'not supported'}${modeNote() ? ' (' + modeNote() + ')' : ''}.</b> OptimusDB's WO P99 is ${f1(Math.abs(100 * (v.od.p99 / v.best.p99 - 1)))} % ${v.od.p99 <= v.best.p99 ? 'below' : 'above'} the best baseline (limit: 25 % above).`) + P(`<b>How much the verdict depends on the numbers.</b> ${v.od.p99 <= v.limit ? `The P99 condition would still hold if ${L(v.best.system)}'s P99 were up to ${f1(Math.max(0, 100 * (1 - v.od.p99 / 1.25 / v.best.p99)))} % lower than measured.` : `OptimusDB's P99 would need to fall by ${f1(100 * (1 - v.limit / v.od.p99))} % to meet the limit.`} ${(() => { const ops = med((D.E1_raw || []).filter(r => r.system === 'optimusdb' && r.workload === 'WO' && r.doc_size === '2KB').map(r => r.ops)) || 0; const k = Math.max(1, Math.round(ops / 1000)); return ops >= 10000 ? `P99.9 rests on about ${k} samples per run (${f1(ops)} operations).` : `P99.9 rests on about ${k} sample${k > 1 ? 's' : ''} per run (${f1(ops)} operations); the campaign's 15,000 operations per run are needed before the tail-ratio condition can be claimed.`; })()}`) : ''}`));
    }
    if (has('E2')) { c = num(); const fails = (D.E2 || []).filter(r => (r.error_rate || 0) > 0.01 && ['optimusdb', 'corrosion'].includes(r.system));
      const failText = fails.map(r => { const ln = limitsNote(r), lg = D.E2_lag[r.run_id]; return `${L(r.system)} at ${r.offered_ops_s} ops/s (${pct(100 * r.error_rate)} errors): ${ln.client ? 'marked client-limited, so not counted against the system' : ln.node ? `node CPU at its limit (${f1(ln.nodeCpu)} of ${ln.nodeLim} %), a limit of the system` : ln.recorded ? 'neither the generator nor the node CPU was at its limit' : `load-generator check not recorded in this run; operations issued a median ${lg ? ms(lg.p50) : '–'} late`}.`; });
      out.push(sec(`${c}. E2 Throughput`, 'rule', `<div class="chn">Chapter ${c} · RQ2 · H2</div><h1 class="ch" data-toc="${c}. E2 · Throughput and saturation">E2 · Throughput and saturation</h1><p class="lede">How much load can each system sustain before it falls behind?</p>
        <h2>Design</h2>${P('WO runs at rising offered loads on one deployment per system; stepping stops after the first step where a system achieves less than 90 % of the offered load. Saturation is the highest step achieved at ≥ 90 % with &lt; 1 % errors.')}
        <h2>Results</h2>${FIG('e2')}${TAB('e2')}${fails.length ? `<h2>Failed steps of OptimusDB and Corrosion</h2><ul>${failText.map(x => `<li>${x}</li>`).join('')}</ul>${FIGS.e2tl.build() ? FIG('e2tl') : ''}` : ''}
        <h2>Hypothesis H2</h2>${TAB('h2')}${P('H2\'s second clause (P99 growth from 10³ to 10⁶ records at 50 ops/s) needs the campaign\'s data-volume series' + ((D.meta.records.E2 || []).length > 1 ? '; the records measured here are ' + list(D.meta.records.E2.map(recs)) + '.' : '.'))}`));
    }
    if (has('E3')) { c = num(); const n = e3show();
      const nat = ['Q4', 'Q5'].map(q => { const sq = e3c('optimusdb', 'sqlite', q, n), cr = e3c('optimusdb', 'crdt', q, n), co = e3c('corrosion', 'sql', q, n); return sq || co ? `${q}: OptimusDB sqlite ${ms(sq?.mean)}, Corrosion ${ms(co?.mean)}${cr ? `, OptimusDB crdt (client-evaluated) ${ms(cr.mean)}` : ''}` : null; }).filter(Boolean);
      const cl = TARGETS.slice(3).map(([s, p]) => ['Q2', 'Q3', 'Q4', 'Q5'].map(q => e3c(s, p, q, n)?.mean).filter(x => x != null)).flat();
      out.push(sec(`${c}. E3 Queries`, 'rule', `<div class="chn">Chapter ${c} · RQ2 · H3</div><h1 class="ch" data-toc="${c}. E3 · Query expressiveness and cost">E3 · Query expressiveness and cost</h1><p class="lede">Which orchestration queries can each system answer, are the answers correct, and how long do they take?</p>
        <h2>Queries and query paths</h2><table><thead><tr><th>Id</th><th>Kind</th><th>SQL form</th></tr></thead><tbody><tr><td><b>Q1</b></td><td>point lookup</td><td class="mono">… WHERE id = 'res-&lt;N/2&gt;'</td></tr><tr><td><b>Q2</b></td><td>single predicate</td><td class="mono">… WHERE status = 'Running'</td></tr><tr><td><b>Q3</b></td><td>conjunctive range</td><td class="mono">… region = 'eu-west' AND cpu ≥ 4 AND memory ≥ 8192</td></tr><tr><td><b>Q4</b></td><td>aggregation</td><td class="mono">region, COUNT(*), AVG(cpu) … GROUP BY region</td></tr><tr><td><b>Q5</b></td><td>two-table join</td><td class="mono">resources ⋈ allocations WHERE region = 'eu-west'</td></tr></tbody></table>
        ${P('OptimusDB is measured on its <b>sqlite</b> path (SQL through <span class="mono">sqldml</span>) and its <b>crdt</b> path (document query on the replicated store; GROUP BY and the join are evaluated in the client). Corrosion answers in SQL. Gun.js, Autobase, Iroh and OpenDHT have no query language: the client reads the data and filters it.')}
        <h2>Results</h2>${FIG('e3')}${TAB('e3')}${cl.length ? P(`Client-side evaluation over the whole dataset took ${ms(Math.min(...cl))} to ${ms(Math.max(...cl))} for Q2–Q5 at ${recs(n)} records.`) : ''}${nat.length ? P('Native execution of Q4 and Q5: ' + nat.join('; ') + '.') : ''}
        <h2>Hypothesis H3</h2>${FIGS.h3.build() ? FIG('h3') : ''}${TAB('h3')}${!e3reg().length ? NOTE('', `<b>Indicative only.</b> H3 is registered at 10⁵ and 10⁶ records; this run measured ${list(e3recs().map(recs))}.`) : ''}`));
    }
    if (has('E4')) { c = num(); out.push(sec(`${c}. E4 Edge resources`, 'rule', `<div class="chn">Chapter ${c} · RQ1 · H4</div><h1 class="ch" data-toc="${c}. E4 · Edge resource cost">E4 · Edge resource cost</h1><p class="lede">What does each system cost in CPU, memory, disk and network on an edge-sized node (1 CPU, 2 GB)?</p>
      <h2>Design</h2>${P('Each system runs on the four edge hosts only. The client drives WO through edge-a at each load level while every container is sampled once per second.')}<h2>Results</h2>${FIG('e4')}${FIGS.e4b.build() ? FIG('e4b') : ''}${TAB('e4')}<h2>Hypothesis H4</h2>${TAB('h4')}${NOTE('', 'Edge hosts in this testbed are containers with Raspberry Pi 4-like limits, not Raspberry Pi boards.')}`)); }
    if (has('E5')) { c = num(); const lim = e5limit(); const nc = SYS.map(e5cell).filter(x => x && x.convergence != null && x.convergence >= lim);
      out.push(sec(`${c}. E5 Partitions`, 'rule', `<div class="chn">Chapter ${c} · RQ3 · H5</div><h1 class="ch" data-toc="${c}. E5 · Partitions and convergence">E5 · Partitions, contention and convergence</h1><p class="lede">During a network split, does each system keep accepting writes, does it lose acknowledged writes, and how fast do its replicas agree after healing?</p>
        <h2>Design</h2>${P(`The hosts are split by dropping traffic in both directions; one writer per host sends WA (50 ops/s in total), with the given share of updates on 100 hot keys so both sides update the same keys. After healing, replicas are compared every 0.5 s until identical (limit ${lim} s), and every acknowledged key is read back.`)}
        <h2>Results</h2>${FIG('e5')}${TAB('e5')}${nc.length ? P(`${list(nc.map(x => L(x.system)))} did not reach identical replicas within ${lim} s in the cell shown.`) : ''}${(D.E5_states || []).length ? `<h3>Replica states when the limit was reached</h3>${TAB('e5states')}` : ''}
        <h2>Hypothesis H5</h2>${TAB('h5')}${nc.length ? P(`Values at the ${lim} s limit are lower bounds. ${(() => { const oc = e5cell('optimusdb'), bc = ['corrosion', 'gun', 'autobase', 'iroh'].map(e5cell).filter(x => x && x.convergence != null); const lo = bc.length ? Math.min(...bc.map(x => x.convergence)) : null; return oc && lo != null && oc.convergence <= lo ? `OptimusDB's ${f1(oc.convergence)} s is at or below the fastest replicating baseline (${f1(lo)} s), so the verdict does not depend on how they are counted.` : 'Counting them at the limit can only raise the median.'; })()}`) : ''}`));
    }
    if ((D.E1_stats || []).some(r => r.p != null)) { c = num(); out.push(sec(`${c}. Statistics`, 'rule', `<div class="chn">Chapter ${c}</div><h1 class="ch" data-toc="${c}. Statistics">Statistical tests (E1)</h1><p class="lede">OptimusDB against each baseline on the per-repetition P99 of each workload: Mann–Whitney U with Holm correction across baselines, and Cliff's δ as effect size (negative: OptimusDB lower).</p>${TAB('stats')}`)); }
    out.push(fx('threats')); out.push(fx('changes'));
    out.push(sec('Appendix A. Raw data', 'data', `<div class="chn">Appendix A</div><h1 class="ch" data-toc="Appendix A. Raw data">Raw data</h1><p class="lede">The rows of the result files as written by the harness.</p>${['E1', 'E2', 'E3', 'E4', 'E5'].map(e => `<div data-table="raw:${e}"></div>`).join('')}`));
    out.push(fixed.glossary || '');
    return out.join('\n');
  }

  /* ---------------------------------------------------------------- assemble, paginate */
  function buildContent(root) {
    root.querySelectorAll('[data-v]').forEach(el => { el.textContent = D.meta[el.dataset.v] || '–'; });
    root.querySelectorAll('[data-block="kpis"]').forEach(el => { el.outerHTML = `<div class="kpis">${['H1', 'H2', 'H3', 'H4', 'H5'].map(h => `<div class="kpi"><div class="l">${h}</div><div class="v">${chip(verdictState(h))}</div><div class="t">${esc(kpiText[h]())}</div></div>`).join('')}</div>`; });
    root.querySelectorAll('[data-tbody]').forEach(el => { el.innerHTML = TABLES[el.dataset.tbody](); });
    root.querySelectorAll('[data-table]').forEach(el => { const [k, a] = el.dataset.table.split(':'); const html = TABLES[k](a); if (!html) { el.remove(); return; }
      const t = document.createElement('div'); t.innerHTML = html; const nodes = Array.from(t.children);
      nodes.forEach(nd => { const cap = nd.querySelector && nd.querySelector('caption'); if (cap) { tabN++; cap.innerHTML = `Table ${tabN} · ${cap.innerHTML}`; } });
      el.replaceWith(...nodes); });
    root.querySelectorAll('figure[data-fig]').forEach(el => { const id = el.dataset.fig, F = FIGS[id], out = F.build(); if (!out) { el.remove(); return; }
      figN++; out.n = figN; BUILT[id] = out;
      el.innerHTML = `<div class="fh"><div class="ft2"><span class="fn">Figure ${figN}</span>${esc(F.title)}</div><div class="ex"><button type="button" data-ex="svg" data-id="${id}">SVG</button><button type="button" data-ex="png" data-id="${id}">PNG</button><button type="button" data-ex="csv" data-id="${id}">CSV</button><button type="button" data-ex="copy" data-id="${id}">Copy SVG</button></div></div>${out.svg}${out.legend ? `<div class="legend">${out.legend.map(k => `<span><i class="sw" style="background:${COL[k]}"></i>${esc(L(k))}</span>`).join('')}</div>` : ''}<figcaption>${esc(F.caption())}${out.note ? ' ' + esc(out.note) : ''}</figcaption>`; });
    const toc = root.querySelector('#toc');
    root.querySelectorAll('[data-toc],[data-toc-sub]').forEach((h, i) => { h.id = 'rh' + i; toc.insertAdjacentHTML('beforeend', `<li class="${h.dataset.toc ? 'ch0' : 'sub'}"><span class="t">${esc(h.dataset.toc || h.dataset.tocSub)}</span><span class="pg" data-for="rh${i}">–</span></li>`); });
  }
  function newSheet(chapter) {
    const s = document.createElement('div'); s.className = 'sheet';
    s.innerHTML = `<div class="hd"><span>${esc(chapter)}</span><span>OptimusDB evaluation · ${esc(D.meta.label)}</span></div><div class="body"></div><div class="ft"><span>ICCS · Swarmchestrate · build ${esc((D.meta.commit || '–').slice(0, 7))}${modeNote() ? ' · ' + esc(modeNote()) : ''}</span><span class="pgno"></span></div>`;
    return s;
  }
  function paginate(sections, meas) {
    const sheets = [];
    sections.forEach(sec => {
      const chapter = sec.dataset.chapter; let sheet = newSheet(chapter); meas.appendChild(sheet); sheets.push(sheet); let body = sheet.querySelector('.body');
      const over = () => body.scrollHeight > body.clientHeight + 1, fresh = () => { sheet = newSheet(chapter); meas.appendChild(sheet); sheets.push(sheet); body = sheet.querySelector('.body'); };
      const blocks = Array.from(sec.children);
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i];
        if (!b.dataset.src && !b.matches('h1, h2, h3, .chn')) b.dataset.src = b.matches('figure, table, .kpis') && sec.dataset.src !== 'fixed' ? 'data' : (sec.dataset.src || '');
        body.appendChild(b);
        if ((/^(H2|H3)$/.test(b.tagName) || b.classList.contains('chn')) && blocks[i + 1] && blocks[i + 1].tagName !== 'H1') {
          const nx = blocks[i + 1].cloneNode(true); if (nx.tagName === 'TABLE') nx.querySelectorAll('tbody tr').forEach((r, j) => { if (j > 1) r.remove(); });
          body.appendChild(nx); const bad = over(); nx.remove(); if (bad && body.children.length > 1) { body.removeChild(b); fresh(); body.appendChild(b); } continue;
        }
        if (!over()) continue;
        if (b.tagName === 'TABLE' || (b.tagName === 'UL' && b.children.length > 3)) {
          const isT = b.tagName === 'TABLE', host = isT ? b.querySelector('tbody') : b, rows = Array.from(host.children); host.innerHTML = '';
          let k = 0; while (k < rows.length) { host.appendChild(rows[k]); if (over()) { host.removeChild(rows[k]); break; } k++; }
          if (k === 0) { body.removeChild(b); if (body.children.length) fresh(); body.appendChild(b); while (k < rows.length) { host.appendChild(rows[k]); if (over() && k > 0) { host.removeChild(rows[k]); break; } k++; } }
          while (k < rows.length) { const cont = b.cloneNode(true), ch = isT ? cont.querySelector('tbody') : cont; ch.innerHTML = ''; const cap = cont.querySelector && cont.querySelector('caption'); if (cap) cap.innerHTML += ' (continued)';
            fresh(); body.appendChild(cont); let m = 0; while (k < rows.length) { ch.appendChild(rows[k]); if (over() && m > 0) { ch.removeChild(rows[k]); break; } k++; m++; } }
          continue;
        }
        if (body.children.length > 1) { body.removeChild(b); fresh(); body.appendChild(b); }
      }
    });
    return sheets;
  }
  function coverSheet() {
    const s = document.createElement('div'); s.className = 'sheet'; const c = D.meta.campaign;
    const fmt = t => t ? new Date(t * 1000).toLocaleString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '–';
    const short = { H1: 'Latency under the orchestration mix (E1)', H2: 'Saturation throughput (E2)', H3: 'Query cost and correctness (E3)', H4: 'Edge CPU and memory (E4)', H5: 'Availability and convergence under partition (E5)' };
    s.innerHTML = `<div class="cover"><div class="band"><div class="k">ΕΠΙΣΕΥ · ICCS · Swarmchestrate · Evaluation report</div><h1><b>OptimusDB</b><br>against five decentralised data stores</h1><div class="sub">Latency, throughput, query cost, edge resource use and partition behaviour on an emulated edge–fog–cloud testbed</div><div class="ring"><span>ICCS</span></div></div>
      ${modeNote() ? `<div class="stamp">${esc(modeNote())}</div>` : ''}
      <div class="meta"><div><div class="l">Run</div><div class="v">${esc(D.meta.label)} · ${esc(c ? c.planned.join(', ') : '–')}</div></div><div><div class="l">Dates</div><div class="v">${esc(fmt(c && c.start))} → ${esc(fmt(c && c.end))}</div></div>
        <div><div class="l">OptimusDB build</div><div class="v mono" style="font-size:11.5px">${esc(D.meta.commit || '–')}</div></div><div><div class="l">Testbed</div><div class="v">8 emulated hosts · ${esc(D.meta.vm || '–')}</div></div>
        <div><div class="l">Baselines</div><div class="v">Corrosion, Gun.js, Autobase, Iroh docs, OpenDHT</div></div><div><div class="l">Repetitions</div><div class="v">${D.max_reps > 1 ? 'up to ' + D.max_reps + ' per cell' : 'one per cell'}</div></div></div>
      <div class="verdicts">${['H1', 'H2', 'H3', 'H4', 'H5'].map(h => `<div class="row"><span class="h">${h}</span><span>${short[h]}</span>${chip(verdictState(h))}</div>`).join('')}</div>
      <div class="foot"><span>Institute of Communication and Computer Systems (ICCS), National Technical University of Athens</span><span>Generated ${esc(D.meta.generated)} from ${esc(D.meta.folder)}</span></div></div>`;
    return s;
  }
  let HOST = null;
  function layout() {
    if (!HOST) return; const sc = Math.min(1, (HOST.clientWidth - 32) / PAGE_W);
    HOST.querySelectorAll('.wrap').forEach(w => { w.style.width = PAGE_W * sc + 'px'; w.style.height = PAGE_H * sc + 'px'; w.firstChild.style.transform = `scale(${sc})`; });
  }
  function render(opts) {
    D = opts.data; BUILT = {}; figN = 0; tabN = 0; HOST = opts.host;
    const holder = document.createElement('div'); holder.innerHTML = buildChapters(opts.template); buildContent(holder);
    const meas = opts.measure; meas.innerHTML = '';
    const sheets = [coverSheet(), ...paginate(Array.from(holder.querySelectorAll('section')), meas)];
    HOST.innerHTML = '';
    sheets.forEach((s, i) => { const pn = s.querySelector('.pgno'); if (pn) pn.textContent = `Page ${i + 1} of ${sheets.length}`; const w = document.createElement('div'); w.className = 'wrap'; w.appendChild(s); HOST.appendChild(w); });
    const toc = [];
    sheets.forEach((s, i) => s.querySelectorAll('[id^="rh"]').forEach(h => { const p = HOST.querySelector(`[data-for="${h.id}"]`); if (p) p.textContent = i + 1; toc.push({ title: h.dataset.toc || h.dataset.tocSub, sub: !h.dataset.toc, page: i + 1 }); }));
    meas.innerHTML = ''; layout();
    return { pages: sheets.length, figures: figN, tables: tabN, toc };
  }

  /* ---------------------------------------------------------------- export */
  let toastEl = null;
  function toast(msg) { if (!toastEl) return; toastEl.textContent = msg; toastEl.classList.add('on'); clearTimeout(toast.h); toast.h = setTimeout(() => toastEl.classList.remove('on'), 2200); }
  function save(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
  const fname = id => `optimusdb-${(D.meta.archive || D.kind)}-fig${String(BUILT[id].n).padStart(2, '0')}-${id}`;
  function exportFig(kind, id) {
    const out = BUILT[id]; if (!out) return;
    if (kind === 'svg') { save(new Blob([out.svg], { type: 'image/svg+xml' }), fname(id) + '.svg'); toast('SVG saved'); }
    if (kind === 'csv') { const txt = out.csv.map(r => r.map(v => v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v).join(',')).join('\n'); save(new Blob([txt], { type: 'text/csv' }), fname(id) + '.csv'); toast('CSV saved'); }
    if (kind === 'copy') { navigator.clipboard.writeText(out.svg).then(() => toast('SVG copied'), () => toast('Copying is blocked here; use the SVG button')); }
    if (kind === 'png') { const m = /viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/.exec(out.svg); const w = +m[1], h = +m[2], k = 3; const img = new Image();
      img.onload = () => { const c = document.createElement('canvas'); c.width = w * k; c.height = h * k; c.getContext('2d').drawImage(img, 0, 0, w * k, h * k); c.toBlob(b => { save(b, fname(id) + '.png'); toast('PNG saved (300 dpi at column width)'); }); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(out.svg); }
  }
  function exportAll() { Object.keys(BUILT).forEach((id, i) => setTimeout(() => exportFig('svg', id), i * 250)); }
  document.addEventListener('click', e => { const b = e.target.closest('.rpt [data-ex]'); if (b) exportFig(b.dataset.ex, b.dataset.id); });
  window.addEventListener('resize', layout);
  /* every figure of a run, built on their own (paper export); opts.font replaces the font family */
  function figures(data, opts = {}) {
    D = data; FONT = opts.font || FONT0; const out = []; let n = 0;
    try {
      const order = ['glance', ...Object.keys(FIGS).filter(k => k !== 'glance')];
      order.forEach(id => { let r = null; try { r = FIGS[id].build(); } catch (e) { r = null; }
        if (r) out.push({ id, n: ++n, title: FIGS[id].title, caption: FIGS[id].caption() + (r.note ? ' ' + r.note : ''), svg: r.svg, csv: r.csv || [] }); });
    } finally { FONT = FONT0; }
    return out;
  }
  return { render, layout, exportAll, figures, setToast: el => { toastEl = el; } };
})();
