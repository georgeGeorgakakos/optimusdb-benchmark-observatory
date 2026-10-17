/* "Results at a glance": one figure that summarises every experiment of a run.
   Left: a radar with one axis per measure; each system is placed between the worst (centre) and the best (edge)
   value measured on that axis, on a log scale (the values span several orders of magnitude). Right: the measured
   values themselves, shaded by the same position, and the hypothesis verdicts. No weights and no total score:
   the figure shows where each system stands per measure, the numbers next to it say by how much.
   Used by the dashboard (Findings page), the evaluation report and the paper export. No libraries. */
'use strict';
window.OptimusSummary = (function () {
  const SYS = ['optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht'];
  const LBL = { optimusdb: 'OptimusDB', corrosion: 'Corrosion', gun: 'Gun.js', autobase: 'Autobase', iroh: 'Iroh docs', opendht: 'OpenDHT' };
  const COL = { optimusdb: '#2a78d6', corrosion: '#eb6834', gun: '#1baf7a', autobase: '#eda100', iroh: '#e87ba4', opendht: '#008300' };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const f1 = v => v == null || isNaN(v) ? '–' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US') : Math.abs(v) >= 100 ? (+v).toFixed(0) : Math.abs(v) >= 10 ? (+v).toFixed(1) : (+v).toFixed(2);
  const med = xs => { xs = xs.filter(x => typeof x === 'number' && !isNaN(x)).sort((a, b) => a - b); const n = xs.length; return n ? (n % 2 ? xs[(n - 1) / 2] : (xs[n / 2 - 1] + xs[n / 2]) / 2) : null; };
  const gmean = xs => Math.exp(xs.reduce((a, x) => a + Math.log(x), 0) / xs.length);
  const recs = n => n >= 1e6 ? '10⁶' : n >= 1e5 ? '10⁵' : n >= 1e4 ? '10⁴' : n >= 1e3 ? '10³' : String(n);

  /* inputs from the dashboard (/api/results) or the report (report_data.build) */
  const fromResults = R => ({ e1: R.analysis.E1.cells || [], e2: R.analysis.E2.series || [], e3: R.analysis.E3.cells || [], e4: R.analysis.E4.cells || [], e5: R.analysis.E5.cells || [], hyp: R.hypotheses || {}, reps: R.max_reps || 0 });
  const fromReport = D => ({ e1: D.E1 || [], e2: D.E2_series || [], e3: D.E3 || [], e4: D.E4 || [], e5: D.E5 || [], hyp: D.hypotheses || {}, reps: D.max_reps || 0 });

  /* one row per measure: values per system ({v, txt, ok, flag}) and whether lower is better */
  function measures(I) {
    const M = [];
    const wo = s => I.e1.find(c => c.system === s && c.workload === 'WO' && c.doc_size === '2KB' && c.p99 != null);
    const partial = c => (c.error_pct || 0) > 1 || (c.unsupported_ops || 0) > 0;
    if (I.e1.some(c => c.workload === 'WO')) {
      M.push({ key: 'p99', name: 'WO latency', sub: 'E1 · P99, lower is better', low: true, vals: Object.fromEntries(SYS.map(s => { const c = wo(s); return [s, c ? { v: c.p99, txt: f1(c.p99) + ' ms', ok: true, flag: partial(c) } : null]; })) });
      M.push({ key: 'tail', name: 'Tail', sub: 'E1 · P99.9 ÷ P50, lower is better', low: true, vals: Object.fromEntries(SYS.map(s => { const c = wo(s); return [s, c && c.p999 && c.p50 ? { v: c.p999 / c.p50, txt: '×' + f1(c.p999 / c.p50), ok: true, flag: partial(c) } : null]; })) });
    }
    if (I.e2.length) {
      const n = Math.max(...I.e2.map(x => x.records || 0));
      M.push({ key: 'sat', name: 'Throughput', sub: `E2 · saturation, ${recs(n)} records, higher is better`, low: false, vals: Object.fromEntries(SYS.map(s => { const x = I.e2.find(q => q.system === s && q.records === n); if (!x) return [s, null];
        const v = x.saturation == null ? 0 : x.saturation; return [s, { v, txt: (x.lower_bound ? '≥ ' : '') + (v ? f1(v) : '0') + ' ops/s', ok: v > 0, flag: !!x.lower_bound }]; })) });
    }
    if (I.e3.length) {
      const n = Math.max(...I.e3.map(c => c.records || 0));
      M.push({ key: 'query', name: 'Queries', sub: `E3 · Q1–Q3 geo. mean, ${recs(n)}, lower is better`, low: true, vals: Object.fromEntries(SYS.map(s => {
        const cs = I.e3.filter(c => c.system === s && c.records === n); if (!cs.length) return [s, null];
        const best = ['Q1', 'Q2', 'Q3'].map(q => { const ok = cs.filter(c => c.query === q && c.mean != null && (c.correct || 0) >= 0.5 && !c.unsupported); return ok.length ? Math.min(...ok.map(c => c.mean)) : null; });
        return [s, best.every(x => x != null) ? { v: gmean(best), txt: f1(gmean(best)) + ' ms', ok: true } : { v: null, txt: 'not all', ok: false }]; })) });
    }
    if (I.e4.length) {
      const lv = Math.max(...I.e4.map(c => c.offered || 0));
      const at = s => I.e4.find(c => c.system === s && c.offered === lv);
      M.push({ key: 'cpu', name: 'Edge CPU', sub: `E4 · % of a core at ${Math.round(lv)} ops/s, lower is better`, low: true, vals: Object.fromEntries(SYS.map(s => { const c = at(s); return [s, c && c.cpu != null ? { v: Math.max(c.cpu, 0.01), txt: f1(c.cpu) + ' %', ok: true } : null]; })) });
      M.push({ key: 'mem', name: 'Edge memory', sub: `E4 · resident MB at ${Math.round(lv)} ops/s, lower is better`, low: true, vals: Object.fromEntries(SYS.map(s => { const c = at(s); return [s, c && c.rss != null ? { v: c.rss, txt: f1(c.rss) + ' MB', ok: true } : null]; })) });
    }
    if (I.e5.length) {
      const cont = I.e5.some(c => c.contention === 30) ? 30 : Math.max(...I.e5.map(c => c.contention || 0));
      M.push({ key: 'conv', name: 'Convergence', sub: `E5 · ${cont} % contention, lower is better`, low: true, vals: Object.fromEntries(SYS.map(s => {
        const cs = I.e5.filter(c => c.system === s && c.contention === cont); if (!cs.length) return [s, null];
        const lost = cs.reduce((a, c) => a + (c.lost || 0), 0), same = cs.every(c => (c.identical || 0) >= 1), v = med(cs.map(c => c.convergence));
        if (lost || !same) return [s, { v: null, txt: lost ? `${lost} lost` : 'diverged', ok: false }];
        return [s, v == null ? null : { v, txt: f1(v) + ' s', ok: true }]; })) });
    }
    // position on each axis: 0.12 (worst measured) … 1 (best), log scale; failed or missing answers sit at 0
    M.forEach(m => {
      const good = SYS.map(s => m.vals[s]).filter(x => x && x.ok && x.v > 0).map(x => x.v);
      const lo = Math.min(...good), hi = Math.max(...good);
      SYS.forEach(s => { const x = m.vals[s]; if (!x) return;
        if (!x.ok || !(x.v > 0)) { x.score = 0; return; }
        if (hi === lo) { x.score = 1; return; }
        const t = (Math.log(x.v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo));
        x.score = 0.12 + 0.88 * (m.low ? 1 - t : t); });
      const ranked = SYS.filter(s => m.vals[s] && m.vals[s].ok).sort((a, b) => m.vals[b].score - m.vals[a].score);
      ranked.forEach((s, i) => { m.vals[s].rank = i + 1; });
    });
    return M;
  }

  /* the figure; pal: colours of text and rules (light by default; the dashboard passes its dark palette) */
  function build(I, o = {}) {
    const pal = Object.assign({ bg: '#ffffff', ink: '#111111', ink2: '#4a4945', muted: '#85837d', rule: '#e3e2dc', cell0: '#f4f3ef', cellHi: '#0f5f73' }, o.pal || {});
    const font = o.font || 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif';
    const M = measures(I); const present = SYS.filter(s => M.some(m => m.vals[s]));
    if (M.length < 3 || present.length < 2) return null;
    const W = 1040, H = 480, cx = 262, cy = 226, R = 146, n = M.length;
    const T = (x, y, s, a = {}) => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${a.size || 11}" fill="${a.fill || pal.ink2}"${a.anchor ? ` text-anchor="${a.anchor}"` : ''}${a.weight ? ` font-weight="${a.weight}"` : ''}${a.style ? ` font-style="${a.style}"` : ''}>${esc(s)}</text>`;
    const ang = i => -Math.PI / 2 + i * 2 * Math.PI / n, pt = (i, r) => [cx + Math.cos(ang(i)) * r, cy + Math.sin(ang(i)) * r];
    let s = '';
    // rings and spokes
    [0.25, 0.5, 0.75, 1].forEach(k => { s += `<polygon points="${M.map((_, i) => pt(i, R * k).map(v => v.toFixed(1)).join(',')).join(' ')}" fill="${k === 1 ? pal.cell0 : 'none'}" fill-opacity="${k === 1 ? 0.55 : 0}" stroke="${pal.rule}" stroke-width="1"${k < 1 ? ' stroke-dasharray="3 3"' : ''}/>`; });
    M.forEach((m, i) => { const [x, y] = pt(i, R); s += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${pal.rule}"/>`;
      const [lx, ly] = pt(i, R + 26), a = Math.cos(ang(i)); const anchor = a > 0.3 ? 'start' : a < -0.3 ? 'end' : 'middle';
      s += T(lx, ly - 2, m.name, { size: 12, fill: pal.ink, weight: 700, anchor }) + T(lx, ly + 11, m.low ? 'lower is better' : 'higher is better', { size: 9.5, fill: pal.muted, anchor }); });
    // baselines first (thin), OptimusDB last (filled) so it is never hidden
    const order = present.filter(x => x !== 'optimusdb').concat(present.includes('optimusdb') ? ['optimusdb'] : []);
    order.forEach(sy => { const od = sy === 'optimusdb';
      const P = M.map((m, i) => pt(i, R * Math.max(0.02, (m.vals[sy] && m.vals[sy].score) || 0)));
      const d = P.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ');
      s += od ? `<polygon points="${d}" fill="${COL[sy]}" fill-opacity="0.18" stroke="${pal.bg}" stroke-width="6" stroke-linejoin="round"/><polygon points="${d}" fill="none" stroke="${COL[sy]}" stroke-width="2.8" stroke-linejoin="round"/>`
              : `<polygon points="${d}" fill="none" stroke="${COL[sy]}" stroke-width="1.5" stroke-opacity="0.85" stroke-linejoin="round"/>`;
      P.forEach((p, i) => { const x = M[i].vals[sy]; if (!x) return; s += `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${od ? 4.2 : 2.6}" fill="${x.ok ? COL[sy] : pal.bg}" stroke="${COL[sy]}" stroke-width="${od ? 1.6 : 1.2}"/>`; }); });
    // legend under the radar
    present.forEach((sy, i) => { const x = 40 + (i % 3) * 145, y = H - 40 + Math.floor(i / 3) * 18;
      s += `<rect x="${x}" y="${y - 9}" width="16" height="${sy === 'optimusdb' ? 10 : 3}" rx="1.5" fill="${COL[sy]}" ${sy === 'optimusdb' ? 'fill-opacity="0.6"' : ''} transform="translate(0 ${sy === 'optimusdb' ? 0 : 3.5})"/>` + T(x + 22, y, LBL[sy], { size: 11, fill: pal.ink, weight: sy === 'optimusdb' ? 700 : 400 }); });
    // value matrix
    const x0 = 512, lw = 142, cw = (W - 12 - x0 - lw) / present.length, top = 34, rh = 34;
    present.forEach((sy, j) => { const x = x0 + lw + j * cw + cw / 2; s += `<rect x="${(x - 7).toFixed(1)}" y="${top - 25}" width="14" height="4" rx="2" fill="${COL[sy]}"/>` + T(x, top - 8, LBL[sy], { size: 11, fill: pal.ink, weight: sy === 'optimusdb' ? 700 : 600, anchor: 'middle' }); });
    if (present.includes('optimusdb')) { const j = present.indexOf('optimusdb'); s += `<rect x="${(x0 + lw + j * cw + 1).toFixed(1)}" y="${top - 2}" width="${(cw - 2).toFixed(1)}" height="${M.length * rh + 2}" rx="5" fill="none" stroke="${COL.optimusdb}" stroke-width="2"/>`; }
    let dagger = false;
    M.forEach((m, i) => { const y = top + i * rh;
      s += T(x0, y + 15, m.name, { size: 11.5, fill: pal.ink, weight: 650 }) + T(x0, y + 28, m.sub.replace(/, (lower|higher) is better$/, ''), { size: 8.5, fill: pal.muted });
      present.forEach((sy, j) => { const v = m.vals[sy], x = x0 + lw + j * cw + 3, w = cw - 6;
        if (!v) { s += T(x + w / 2, y + 21, '–', { size: 11, fill: pal.muted, anchor: 'middle' }); return; }
        const k = v.score || 0, fill = mix(pal.cell0, pal.cellHi, k * 0.92), fg = k > 0.55 ? '#ffffff' : pal.ink;
        s += `<rect x="${x.toFixed(1)}" y="${y + 3}" width="${w.toFixed(1)}" height="${rh - 6}" rx="4" fill="${v.ok ? fill : pal.bg}" ${v.ok ? '' : `stroke="#d03b3b" stroke-width="1.2" stroke-dasharray="3 2"`}/>`;
        s += T(x + w / 2, y + 21, (v.flag ? '† ' : '') + v.txt, { size: 10, fill: v.ok ? fg : '#b42318', anchor: 'middle', weight: v.rank === 1 ? 750 : 450 });
        if (v.rank === 1) s += `<circle cx="${(x + w - 6).toFixed(1)}" cy="${y + 9}" r="3.2" fill="${k > 0.55 ? '#ffffff' : pal.cellHi}"/>`;
        if (v.flag) dagger = true; }); });
    // hypotheses strip
    const hy = top + M.length * rh + 18; s += T(x0, hy + 14, 'Hypotheses', { size: 11.5, fill: pal.ink, weight: 650 });
    const hw = (W - 12 - x0 - lw) / 5;
    ['H1', 'H2', 'H3', 'H4', 'H5'].forEach((h, i) => { const st = (I.hyp[h] || {}).state || 'insufficient', x = x0 + lw + i * hw + 3, w = hw - 6;
      const [bg, fg, mk] = st === 'supported' ? ['#e6f4e6', '#0a7a0a', '✓'] : st === 'not_supported' ? ['#fbe9e9', '#b42318', '✕'] : ['#efeee9', '#6b6a65', '?'];
      s += `<rect x="${x.toFixed(1)}" y="${hy}" width="${w.toFixed(1)}" height="22" rx="11" fill="${bg}"/>` + T(x + w / 2, hy + 15, `${mk} ${h}`, { size: 11, fill: fg, weight: 700, anchor: 'middle' }); });
    const notes = ['Radar: each axis runs from the worst measured value (inner ring) to the best (outer ring), log scale.',
      'Open markers at the centre: no valid value (failed, diverged or not supported). Not a weighted score.',
      'Cells: measured values, shaded by the same position; dot = best on that measure; dashed red = failed.',
      (dagger ? '† covers only the operations that succeeded, or a lower bound. ' : '') + (I.reps > 1 ? `Medians over up to ${I.reps} repetitions.` : 'One repetition per cell: indicative only.')];
    notes.forEach((t, i) => { s += T(x0, hy + 46 + i * 13, t, { size: 8.8, fill: pal.muted }); });
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="${font}"><rect width="${W}" height="${H}" fill="${pal.bg}"/>${s}</svg>`;
    const csv = [['measure', 'system', 'value', 'shown', 'position_0_1', 'rank']].concat(...M.map(m => present.map(sy => { const v = m.vals[sy]; return [m.key, sy, v ? v.v : '', v ? v.txt : '', v && v.score != null ? v.score.toFixed(3) : '', v && v.rank ? v.rank : '']; })));
    return { svg, csv, measures: M, present };
  }
  function mix(a, b, t) { const h = x => [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16)); const A = h(a), B = h(b); return '#' + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, '0')).join(''); }

  return { build, fromResults, fromReport, measures };
})();
