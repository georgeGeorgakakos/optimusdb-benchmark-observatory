/* OptimusDB Benchmark Observatory - single-page dashboard (no external libraries). */
'use strict';
const SYS = ['optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht'];
const LABEL = { optimusdb: 'OptimusDB', corrosion: 'Corrosion', gun: 'Gun.js', autobase: 'Autobase', iroh: 'Iroh docs', opendht: 'OpenDHT' };
const SLOT = { optimusdb: 1, corrosion: 2, gun: 3, autobase: 4, iroh: 5, opendht: 6 };   // fixed order, never cycled
const col = s => `var(--s${SLOT[s] || 1})`;
const WL = { WA: 'WA · 50 % read / 50 % update', WB: 'WB · 95 % read / 5 % update', WC: 'WC · read only', WO: 'WO · orchestration mix (60/20/10/10)' };
const EXP = {
  E1: { t: 'Latency and tail behaviour', rq: 'RQ2', h: 'H1', q: 'How fast is each operation, and how bad is the slowest 1 %?' },
  E2: { t: 'Throughput and data volume', rq: 'RQ2', h: 'H2', q: 'How much load can each system absorb before it falls behind?' },
  E3: { t: 'Query expressiveness and cost', rq: 'RQ2', h: 'H3', q: 'Can each system answer real orchestration queries, correctly, and how fast?' },
  E4: { t: 'Edge resource cost', rq: 'RQ1', h: 'H4', q: 'What CPU, memory, disk and network does each system cost on an edge host?' },
  E5: { t: 'Partitions, contention and convergence', rq: 'RQ3', h: 'H5', q: 'During a network split, does each system keep accepting writes, and does it lose any after healing?' },
};
const HYP = {
  H1: 'For WO, OptimusDB’s P99 is within 25 % of the best baseline, and its tail ratio P99.9/P50 is not larger than the baselines’ median.',
  H2: 'OptimusDB’s saturation throughput is at least the baselines’ median; its P99 at 50 ops/s grows less than 2× from 10³ to 10⁶ records.',
  H3: 'For Q1–Q3, OptimusDB answers correctly and faster than client-side evaluation (Gun.js, Autobase, Iroh, OpenDHT) and within 25 % of Corrosion.',
  H4: 'At 40 ops/s on an edge device, OptimusDB stays below 60 % CPU and 512 MB resident memory.',
  H5: 'During a partition OptimusDB accepts writes on both sides; after healing it loses no acknowledged write, replicas are identical, and convergence is no slower than the replicating baselines’ median.',
};

const store = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } } };
const S = { mode: store.get('odb.mode') || 'quick', page: location.hash.slice(1) || (window.ODB_STATIC ? 'summary' : 'overview'), P: null, R: null,
            scale: 'log', metric: 'p99', e1size: '2KB', e2rec: null, e3rec: null, lastRuns: -1 };
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v, d = 1) => v == null || Number.isNaN(v) ? '–' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : (+v).toFixed(v >= 100 ? 0 : v >= 10 ? 1 : d + 1);
const ms = v => v == null ? '–' : `${fmt(v)} ms`;
const dur = s => { if (s == null) return '–'; s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h} h ${String(m).padStart(2, '0')} m` : m ? `${m} m` : `${s} s`; };
const sysOf = id => (id || '').split('-')[1];
// result set ids: 'quick' | 'pilot' | 'campaign' (current results) or 'a:<archive folder>/<kind>' (older runs in results-archive\)
const kindOf = m => (m || '').includes('/') ? m.split('/')[1] : m;
const archOf = m => (m || '').startsWith('a:') ? m.slice(2).split('/')[0] : '';
const KIND = { quick: 'Quick', pilot: 'Pilot', campaign: 'Campaign' };
const archLabel = a => { const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(.*)$/.exec(a || ''); return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}${m[7] ? ' ' + m[7].replace(/^-/, '') : ''}` : a; };
const srcLabel = m => archOf(m) ? `${KIND[kindOf(m)]} · archived ${archLabel(archOf(m))}` : `${KIND[kindOf(m)] || m} results (current)`;
const srcPath = m => archOf(m) ? `results-archive\\${archOf(m)}\\${kindOf(m) === 'campaign' ? '' : kindOf(m)}` : `results\\${kindOf(m) === 'campaign' ? '' : kindOf(m)}`;
const clock = t => t ? new Date(t * 1000).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';
const hhmm = t => t ? new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '–';

/* ------------------------------------------------------------------ theme + nav */
(function initTheme() {
  const t = localStorage.getItem('odb.theme'); if (t) document.documentElement.dataset.theme = t;
  $('#theme').onclick = () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'light' : 'dark'; localStorage.setItem('odb.theme', document.documentElement.dataset.theme); render();
  };
})();
document.querySelectorAll('#nav button').forEach(b => b.onclick = () => { location.hash = b.dataset.page; });
window.addEventListener('hashchange', () => { $('#modal').classList.remove('open'); S.page = location.hash.slice(1) || 'overview'; render(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#modal').classList.remove('open'); });
$('#mode').onchange = e => setSource(e.target.value);
function setSource(m) { S.mode = m; store.set('odb.mode', m); S.R = null; $('#mode').value = m; loadResults().then(render); }
$('#modal').onclick = e => { if (e.target.id === 'modal' || e.target.classList.contains('x')) { $('#modal').classList.remove('open'); $('#modalBox').classList.remove('wide'); } };

/* ------------------------------------------------------------------ data */
/* Published snapshot (tools/build_site.py, e.g. GitHub Pages): the API answers are JSON files under site-data/. */
const STATIC = window.ODB_STATIC || null;
function apiUrl(url) {
  if (!STATIC) return url;
  const u = new URL(url, 'http://x'), q = n => u.searchParams.get(n) || '', k = (q('mode') || 'quick').replace(/[^\w.-]/g, '_'), b = STATIC.base;
  return { '/api/progress': b + 'progress.json', '/api/results': `${b}results/${k}.json`, '/api/report': `${b}report/${k}.json`,
           '/api/ops': `${b}ops/${k}/${encodeURIComponent(q('run'))}.json`, '/api/report-copy': `${b}reports/${k}/${encodeURIComponent(q('name'))}` }[u.pathname] || null;
}
async function j(url) {
  const s = apiUrl(url); if (!s) throw new Error('not part of the published snapshot');
  const r = await fetch(s, { cache: 'no-store' });
  if (!r.ok) throw new Error(STATIC && r.status === 404 ? 'not included in the published snapshot' : r.status); return r.json();
}
async function loadProgress() {
  try { S.P = await j('/api/progress'); setLive(); } catch (e) { S.P = null; setLive(e); }
  const src = (S.P && S.P.sources) || [{ id: 'quick', archive: '', has_data: false }, { id: 'pilot', archive: '', has_data: false }, { id: 'campaign', archive: '', has_data: false }];
  if (S.P && !src.some(x => x.id === S.mode)) { S.mode = 'quick'; S.R = null; }   // an archive folder that was removed
  const opt = x => `<option value="${esc(x.id)}" ${x.id === S.mode ? 'selected' : ''}>${esc(x.archive ? `${KIND[x.kind]} · archived ${archLabel(x.archive)}` : KIND[x.kind] + ' results' + (x.has_data ? '' : ' (none yet)'))}</option>`;
  const groups = {}; src.filter(x => x.archive).forEach(x => (groups[x.archive] = groups[x.archive] || []).push(x));
  const html = `<optgroup label="Current results">${src.filter(x => !x.archive).map(opt).join('')}</optgroup>` +
    Object.keys(groups).map(a => `<optgroup label="Archived ${esc(archLabel(a))}">${groups[a].map(opt).join('')}</optgroup>`).join('');
  const sel = $('#mode'); if (sel.dataset.html !== html) { sel.innerHTML = html; sel.dataset.html = html; }
}
async function loadResults() { try { S.R = await j(`/api/results?mode=${encodeURIComponent(S.mode)}`); S.rerr = null; } catch (e) { S.rerr = String(e); /* keep the last good results on screen */ } S.rkey = S.R ? JSON.stringify(S.R.completion) + S.mode : ''; }
function setLive(err) {
  const d = $('#liveDot'), t = $('#liveText');
  if (STATIC) { d.className = err ? 'dot bad' : 'dot done'; t.textContent = err ? 'snapshot not found' : `Published snapshot · ${STATIC.built}`; document.title = 'OptimusDB Benchmark Observatory · ICCS'; return; }
  if (err || !S.P) { d.className = 'dot bad'; t.textContent = 'dashboard server not reachable'; return; }
  const e = S.P.experiment || {}, c = S.P.campaign || {};
  if (e.stalled) { d.className = 'dot warn'; t.textContent = `${e.exp} silent for ${Math.round(e.idle_min)} min`; }
  else if (S.P.running) { d.className = 'dot live'; t.textContent = `${e.exp || c.current || ''} running${e.pos ? ` · run ${e.pos.i}/${e.pos.n}` : ''}`; }
  else if (c.status === 'finished') { d.className = 'dot done'; t.textContent = `${KIND[c.kind]} finished ${hhmm(c.end)}`; }
  else if (c.status === 'finished_errors') { d.className = 'dot warn'; t.textContent = `${KIND[c.kind]} finished ${hhmm(c.end)} · ${c.failed.join(', ')} failed`; }
  else if (c.status === 'stopped') { d.className = 'dot warn'; t.textContent = `${KIND[c.kind]} stopped before the end`; }
  else { d.className = 'dot'; t.textContent = 'idle'; }
  // the browser tab shows the state too, so a finished run is visible from another tab
  const pct = e.pos ? Math.round((e.pos.i - 1) / e.pos.n * 100) : null;
  document.title = (e.stalled ? '⚠ Stuck? · ' : S.P.running ? `▶ ${e.exp || c.current || 'Running'}${pct != null ? ' ' + pct + '%' : ''} · ` : c.status === 'finished' ? '✓ Finished · ' : c.status === 'finished_errors' ? '⚠ Finished with errors · ' : c.status === 'stopped' ? '■ Stopped · ' : '') + 'OptimusDB Benchmark Observatory · ICCS';
  notifyOnFinish(c);
  const nf = (S.P.failures || []).length; $('#failCount').textContent = nf ? nf : '';
}

/* ------------------------------------------------------------------ finish notification (while the page is open) */
function notifyOnFinish(c) {
  const key = c.log ? c.log + '|' + c.status : '';
  if (S.lastStatus && S.lastStatus.startsWith(c.log + '|running') && key !== S.lastStatus && c.status !== 'running') {
    const msg = c.status === 'finished' ? `${KIND[c.kind]} run finished at ${hhmm(c.end)}: ${c.planned.join(', ')}` :
      c.status === 'finished_errors' ? `${KIND[c.kind]} run finished with errors in ${c.failed.join(', ')}` : `${KIND[c.kind]} run stopped before the end`;
    try { if ('Notification' in window && Notification.permission === 'granted') new Notification('OptimusDB benchmark', { body: msg, icon: 'favicon.png' }); } catch (e) { /* not available */ }
    try { const a = new AudioContext(), o = a.createOscillator(), g = a.createGain(); o.connect(g); g.connect(a.destination); o.frequency.value = 880; g.gain.value = .08; o.start(); o.stop(a.currentTime + .35); } catch (e) { /* no sound */ }
  }
  S.lastStatus = key;
}
function askNotify() { try { Notification.requestPermission().then(render); } catch (e) { /* not available */ } }
const canNotify = () => { try { return 'Notification' in window; } catch (e) { return false; } };

/* ------------------------------------------------------------------ finished / stopped banner (every page) */
function banner() {
  const P = S.P; if (!P || !P.campaign) return '';
  const c = P.campaign; if (!['finished', 'finished_errors', 'stopped'].includes(c.status)) return '';
  const id = c.log + '|' + c.status; if (store.get('odb.dismiss') === id) return '';
  const took = c.end && c.start ? ` (took ${dur(c.end - c.start)})` : '';
  const exps = c.planned.map(x => x in c.ended ? `${x} ${c.ended[x] ? '✕' : '✓'}` : `${x} –`).join(' · ');
  const [cls, ic, title, text] = c.status === 'finished'
    ? ['good', '✓', `${KIND[c.kind]} run finished ${clock(c.end)}${took}`, `${exps}. The results are in ${srcPath(c.kind)}.`]
    : c.status === 'finished_errors'
    ? ['warn', '!', `${KIND[c.kind]} run finished ${clock(c.end)} with errors`, `${exps}. ${c.failed.join(', ')} exited with an error: see Run health and the experiment log.`]
    : ['warn', '■', `${KIND[c.kind]} run stopped before the end`, `${exps}. It was stopped or the PC restarted. Run the same run-all command again to continue: finished runs are skipped.`];
  return `<div class="banner ${cls}"><span class="ic">${ic}</span><div class="bt"><b>${esc(title)}</b><div>${esc(text)}</div></div>
    <div class="ba">${S.mode !== c.kind ? `<button class="btn" data-src="${esc(c.kind)}">Show these results</button>` : `<button class="btn" data-go="summary">Findings &amp; hypotheses</button>`}
    <button class="btn ghost" data-dismiss="${esc(id)}" title="Hide until the next run">Dismiss</button></div></div>`;
}
document.addEventListener('click', e => {
  const s = e.target.closest('[data-src]'); if (s) { setSource(s.dataset.src); if (s.dataset.go) location.hash = s.dataset.go; else if (S.page === 'history') location.hash = 'summary'; return; }
  const g = e.target.closest('[data-go]'); if (g) { location.hash = g.dataset.go; return; }
  const d = e.target.closest('[data-dismiss]'); if (d) { store.set('odb.dismiss', d.dataset.dismiss); render(); return; }
  const n = e.target.closest('[data-notify]'); if (n) askNotify();
});

/* ------------------------------------------------------------------ tooltip */
const tip = $('#tip');
document.addEventListener('mousemove', e => {
  const el = e.target.closest('[data-tip]');
  if (!el) { tip.style.opacity = 0; return; }
  tip.innerHTML = el.dataset.tip; tip.style.opacity = 1;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(innerWidth - w - 8, e.clientX + 14) + 'px'; tip.style.top = Math.max(8, e.clientY - h - 12) + 'px';
});
document.addEventListener('click', e => { const el = e.target.closest('[data-run]'); if (el) openRun(el.dataset.run); });
const tipRows = (title, rows) => `<b>${esc(title)}</b>` + rows.map(([k, v]) => `<div class="r"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('');

/* ------------------------------------------------------------------ charts (SVG) */
function scaleY(min, max, h, log) {
  if (log) { const a = Math.log10(Math.max(min, 1e-3)), b = Math.log10(Math.max(max, min * 10)); return { f: v => h - (Math.log10(Math.max(v, 1e-3)) - a) / (b - a) * h, ticks: logTicks(min, max) }; }
  const nice = niceMax(max); return { f: v => h - v / nice * h, ticks: [0, .25, .5, .75, 1].map(k => k * nice) };
}
function niceMax(v) { if (!(v > 0)) return 1; const p = 10 ** Math.floor(Math.log10(v)); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p; return 10 * p; }
function logTicks(min, max) {
  const t = [], dec = Math.log10(max) - Math.log10(Math.max(min, 1e-3)), steps = dec < 1.5 ? [1, 2, 5] : dec < 3 ? [1, 3] : [1];
  for (let e = Math.floor(Math.log10(Math.max(min, 1e-3))); e <= Math.ceil(Math.log10(max)); e++) steps.forEach(m => { const v = m * 10 ** e; if (v >= min * 0.999 && v <= max * 1.001) t.push(v); });
  return t;
}
const fmtV = v => v >= 1000 ? +(v / 1000).toPrecision(3) + 'k' : String(+(+v).toPrecision(3));
const tickLbl = v => v >= 1000 ? (v / 1000) + 'k' : v >= 1 ? String(+v.toFixed(2)) : String(+v.toPrecision(2));

function legend(systems) { return `<div class="legend">${systems.map(s => `<span${s === 'optimusdb' ? ' class="od"' : ''}><i class="sw" style="background:${col(s)}"></i>${LABEL[s] || s}</span>`).join('')}</div>`; }

/* Every chart is registered so it can be opened enlarged with its own zoom controls (openZoom). OptimusDB is drawn
   last (on top), with a heavier line or a value label, so it stays visible next to baselines that are 100× slower. */
let CH = [];
const ODB = 'optimusdb';
function chartBox(kind, args, svg) {
  const id = CH.push({ kind, args }) - 1;
  return `<div class="chart zoomable">${svg}<button class="zbtn" type="button" data-zoom="${id}" title="Enlarge, zoom and export this chart" aria-label="Enlarge chart"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button></div>`;
}
/* grouped bars: groups x systems; val(g, s) -> {v, tip, run} */
function bars(args) { return chartBox('bars', args, barsSvg(args)); }
function barsSvg({ groups, systems, val, log = false, unit = '', height = 280, glabel = g => g, refLine, w = 900, ymax = null }) {
  const W = w, H = height, L = 52, B = 34, T = ymax != null ? 34 : unit ? 26 : 12, iw = W - L - 10, ih = H - T - B;
  const vals = []; groups.forEach(g => systems.forEach(s => { const x = val(g, s); if (x && x.v > 0) vals.push(x.v); if (x && x.mark > 0) vals.push(x.mark); }));
  if (!vals.length) return empty('No values yet for this view.');
  if (refLine && refLine.v > 0 && ymax == null) vals.push(refLine.v);
  const min = Math.min(...vals), top = ymax != null ? ymax : Math.max(...vals) * 1.08, sc = scaleY(log ? Math.min(min, top / 10) / 1.5 : 0, top, ih, log);
  const gw = iw / groups.length, bw = Math.max(4, Math.min(26, (gw - 14) / systems.length - 2));
  let o = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  sc.ticks.forEach(t => { const y = T + sc.f(t); if (y < T - 1 || y > T + ih + 1) return; o += `<line class="gridline" x1="${L}" x2="${W - 10}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${tickLbl(t)}</text>`; });
  o += `<line class="axis" x1="${L}" x2="${W - 10}" y1="${T + ih}" y2="${T + ih}"/>`;
  if (unit) o += `<text x="${L}" y="12">${esc(unit)}</text>`;
  let nclip = 0;
  groups.forEach((g, gi) => {
    const x0 = L + gi * gw + (gw - systems.length * (bw + 2)) / 2;
    systems.forEach((s, si) => {
      const x = val(g, s); const bx = x0 + si * (bw + 2);
      if (!x) return;
      if (x.unsupported) { o += `<text x="${bx + bw / 2}" y="${T + ih - 4}" text-anchor="middle" style="font-size:10px" data-tip="${esc(tipRows(LABEL[s], [['', 'not supported']]))}">n/s</text>`; return; }
      if (!(x.v > 0)) return;
      const clip = x.v > top, yv = clip ? T : Math.min(T + sc.f(x.v), T + ih - 3), hgt = T + ih - yv, r = Math.min(4, bw / 2, hgt);
      o += `<path d="M${bx},${T + ih} V${yv + r} q0,-${r} ${r},-${r} h${bw - 2 * r} q${r},0 ${r},${r} V${T + ih} Z" fill="${col(s)}"/>`;
      if (clip) { nclip++; o += `<path d="M${bx - 1},${T + 9} l${bw / 2 + 1},-5 l${bw / 2 + 1},5" fill="none" stroke="var(--surface)" stroke-width="2.5"/><text x="${bx + bw / 2}" y="${T - 3 - (nclip % 2 ? 0 : 11)}" text-anchor="middle" style="font-size:9.5px;font-weight:650">${esc(fmtV(x.v))}</text>`; }
      else if (s === ODB) o += `<text x="${bx + bw / 2}" y="${yv - 5}" text-anchor="middle" class="odbval">${esc(fmtV(x.v))}</text>`;
      if (x.mark != null && x.mark > 0 && x.mark <= top) { const my = T + sc.f(x.mark); o += `<line x1="${bx - 2}" x2="${bx + bw + 2}" y1="${my}" y2="${my}" stroke="var(--ink)" stroke-width="2"/>`; }
      o += `<rect class="hit" x="${bx - 1}" y="${T}" width="${bw + 2}" height="${ih}" data-tip="${esc(x.tip || '')}" ${x.run ? `data-run="${esc(x.run)}"` : ''}/>`;
    });
    o += `<text class="lbl" x="${L + gi * gw + gw / 2}" y="${H - 12}" text-anchor="middle">${esc(glabel(g))}</text>`;
  });
  if (refLine != null && refLine.v <= top) { const y = T + sc.f(refLine.v); o += `<line x1="${L}" x2="${W - 10}" y1="${y}" y2="${y}" stroke="var(--ink-2)" stroke-dasharray="4 4"/><text x="${W - 12}" y="${y - 4}" text-anchor="end">${esc(refLine.label)}</text>`; }
  return o + '</svg>';
}

/* lines: series [{key,label,color,points:[{x,y,tip}]}] */
function lines(args) { return chartBox('lines', args, linesSvg(args)); }
function linesSvg({ series, log = false, xLabel = '', yLabel = '', diagonal = false, height = 280, logX = false, w = 900, ymax = null }) {
  const pts = series.flatMap(s => s.points).filter(p => p.y != null && p.x != null);
  if (!pts.length) return empty('No values yet for this view.');
  const W = w, H = height, L = 52, B = 36, T = yLabel ? 26 : 12, R = 16, iw = W - L - R, ih = H - T - B;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys);
  const top = ymax != null ? ymax : Math.max(...ys, diagonal ? xmax : 0) * 1.08;
  const fx = logX ? v => L + (Math.log10(v) - Math.log10(xmin)) / ((Math.log10(xmax) - Math.log10(xmin)) || 1) * iw : v => L + v / (niceMax(xmax) || 1) * iw;
  const sc = scaleY(log ? Math.max(Math.min(ymin, top / 10) / 1.5, 1e-3) : 0, top, ih, log);
  const cid = 'c' + Math.random().toString(36).slice(2, 8);
  let o = `<svg viewBox="0 0 ${W} ${H}" role="img"><defs><clipPath id="${cid}"><rect x="${L - 6}" y="${T - 6}" width="${iw + 12}" height="${ih + 12}"/></clipPath></defs>`;
  sc.ticks.forEach(t => { const y = T + sc.f(t); if (y < T - 1 || y > T + ih + 1) return; o += `<line class="gridline" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${tickLbl(t)}</text>`; });
  const allInt = xs.every(Number.isInteger);
  const xt = logX ? [...new Set(xs)].sort((a, b) => a - b) : [...new Set([0, .25, .5, .75, 1].map(k => allInt ? Math.round(k * niceMax(xmax)) : k * niceMax(xmax)))];
  xt.forEach(t => o += `<text x="${fx(t)}" y="${H - 18}" text-anchor="middle">${tickLbl(t)}</text>`);
  o += `<line class="axis" x1="${L}" x2="${W - R}" y1="${T + ih}" y2="${T + ih}"/>`;
  if (xLabel) o += `<text x="${L + iw / 2}" y="${H - 2}" text-anchor="middle">${esc(xLabel)}</text>`;
  if (yLabel) o += `<text x="${L}" y="12">${esc(yLabel)}</text>`;
  o += `<g clip-path="url(#${cid})">`;
  if (diagonal) { const m = niceMax(xmax); o += `<line x1="${fx(0)}" y1="${T + sc.f(0)}" x2="${fx(m)}" y2="${T + sc.f(Math.min(m, top))}" stroke="var(--muted)" stroke-dasharray="4 4"/><text x="${fx(m * 0.62) + 8}" y="${T + sc.f(Math.min(m * 0.62, top)) + 18}">ideal: achieved = offered</text>`; }
  const order = series.filter(s => s.key !== ODB).concat(series.filter(s => s.key === ODB));
  const labels = [];
  order.forEach(s => {
    const od = s.key === ODB, p = s.points.filter(q => q.y != null).sort((a, b) => a.x - b.x); if (!p.length) return;
    const Y = q => T + sc.f(Math.min(q.y, top * 1.05));
    const d = p.map((q, i) => `${i ? 'L' : 'M'}${fx(q.x)},${Y(q)}`).join('');
    if (od) o += `<path d="${d}" fill="none" stroke="var(--surface)" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>`;
    o += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${od ? 3.2 : 2}" stroke-linejoin="round"${od ? '' : ' stroke-opacity=".9"'}/>`;
    p.forEach(q => o += `<circle cx="${fx(q.x)}" cy="${Y(q)}" r="${od ? 5.5 : 4}" fill="${s.color}" stroke="var(--surface)" stroke-width="2"/><circle class="hit" cx="${fx(q.x)}" cy="${Y(q)}" r="11" data-tip="${esc(q.tip || '')}" ${q.run ? `data-run="${esc(q.run)}"` : ''}/>`);
    const last = p[p.length - 1]; if (series.length <= 4 || od) labels.push({ x: fx(last.x) + 8, y: Y(last) + 4, t: s.label, od });
  });
  o += '</g>';
  labels.forEach(l => o += `<text class="lbl${l.od ? ' odbval' : ''}" x="${Math.min(l.x, W - R - 4)}" y="${l.y}" ${l.x > W - R - 60 ? 'text-anchor="end"' : ''}>${esc(l.t)}</text>`);
  return o + '</svg>';
}

/* ------------------------------------------------------------------ chart zoom: enlarged copy with its own controls */
const Z = { i: -1, focus: false, log: null, top: null };
document.addEventListener('click', e => { const b = e.target.closest('[data-zoom]'); if (b) { e.stopPropagation(); openZoom(+b.dataset.zoom); } }, true);
function zoomRange(c) {   // [smallest useful y max, full y max, OptimusDB's largest value]
  const a = c.args; let all = [], od = [];
  if (c.kind === 'bars') a.groups.forEach(g => a.systems.forEach(s => { const x = a.val(g, s); if (x && x.v > 0) { all.push(x.v); if (s === ODB) od.push(x.v); } }));
  else a.series.forEach(s => s.points.forEach(p => { if (p.y != null) { all.push(p.y); if (s.key === ODB) od.push(p.y); } }));
  const full = Math.max(...all, a.diagonal ? Math.max(...a.series.flatMap(s => s.points.map(p => p.x))) : 0) * 1.08;
  const odm = od.length ? Math.max(...od) : null;
  return [Math.max(Math.min(...all) * 1.5, (odm || full / 50) * 1.2), full, odm];
}
function openZoom(i) {
  const c = CH[i]; if (!c) return;
  if (Z.i !== i) { Z.i = i; Z.focus = false; Z.log = !!c.args.log; Z.top = null; }
  const [lo, full, odm] = zoomRange(c), top = Z.top == null ? full : Math.min(full, Math.max(lo, Z.top));
  const a = { ...c.args, w: 1180, height: Math.min(560, Math.max(380, innerHeight - 330)), log: Z.log, ymax: top < full * 0.999 ? top : null };
  const svg = c.kind === 'bars' ? barsSvg(a) : linesSvg(a);
  const sysList = c.kind === 'bars' ? a.systems : a.series.map(s => s.key);
  const pos = Math.round(1000 * Math.log(top / lo) / Math.log(full / lo || 2));
  const box = $('#modalBox'); $('#modal').classList.add('open'); box.classList.add('wide');
  box.innerHTML = `<button class="x">Close</button><div class="tag muted" style="font-size:11px;letter-spacing:.18em">CHART · ZOOM</div>
    <div class="zoombar"><div class="seg"><button class="${!Z.focus ? 'on' : ''}" data-zf="0">All systems</button><button class="${Z.focus ? 'on' : ''}" data-zf="1" ${odm == null ? 'disabled' : ''}>Focus on OptimusDB</button></div>
      <div class="seg"><button class="${Z.log ? 'on' : ''}" data-zl="1">log</button><button class="${!Z.log ? 'on' : ''}" data-zl="0">linear</button></div>
      <label class="zr">Y-axis up to <input type="range" min="0" max="1000" value="${isFinite(pos) ? pos : 1000}" id="zRange"> <b id="zVal">${esc(fmtV(top))}</b></label>
      <span class="sp"></span><button class="btn ghost" data-zx="svg">SVG</button><button class="btn ghost" data-zx="png">PNG</button></div>
    ${legend(sysList.filter(s => LABEL[s]))}<div class="chart big" id="zChart">${svg}</div>
    <div class="hint">Bars or points above the chosen maximum are cut at the top and labelled with their value. OptimusDB is drawn on top and labelled. Drag the slider or use the mouse wheel over the chart to zoom the y-axis.</div>`;
  box.querySelectorAll('[data-zf]').forEach(b => b.onclick = () => { Z.focus = b.dataset.zf === '1'; Z.top = Z.focus && odm ? odm * 2.5 : null; openZoom(i); });
  box.querySelectorAll('[data-zl]').forEach(b => b.onclick = () => { Z.log = b.dataset.zl === '1'; openZoom(i); });
  const rg = $('#zRange'); rg.oninput = () => { Z.top = lo * Math.pow(full / lo, rg.value / 1000); Z.focus = false; openZoom(i); $('#zRange').focus(); };
  $('#zChart').onwheel = ev => { ev.preventDefault(); Z.top = Math.min(full, Math.max(lo, top * (ev.deltaY > 0 ? 1.25 : 0.8))); Z.focus = false; openZoom(i); };
  box.querySelectorAll('[data-zx]').forEach(b => b.onclick = () => exportChart($('#zChart svg'), b.dataset.zx, 'optimusdb-' + S.page.toLowerCase() + '-chart'));
}
/* standalone SVG of an on-screen chart: theme colours and fonts written into the elements */
function inlineSvg(svg) {
  const c = svg.cloneNode(true), src = svg.querySelectorAll('*'), dst = c.querySelectorAll('*');
  src.forEach((el, k) => { const cs = getComputedStyle(el), d = dst[k];
    ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'fill-opacity', 'stroke-opacity', 'font-size', 'font-weight', 'font-family'].forEach(p => { const v = cs.getPropertyValue(p); if (v && v !== 'normal' && v !== 'none' || p === 'fill' || p === 'stroke') d.setAttribute(p, v); });
    if (d.classList.contains('hit')) d.remove(); });
  c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const vb = c.getAttribute('viewBox').split(' '); c.setAttribute('width', vb[2]); c.setAttribute('height', vb[3]);
  c.insertAdjacentHTML('afterbegin', `<rect width="${vb[2]}" height="${vb[3]}" fill="${getComputedStyle(svg.closest('.chart') || document.body).backgroundColor || '#fff'}"/>`);
  return new XMLSerializer().serializeToString(c);
}
function exportChart(svgEl, kind, name) {
  const txt = typeof svgEl === 'string' ? svgEl : inlineSvg(svgEl);
  const dl = (blob, fn) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fn; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); };
  if (kind === 'svg') return dl(new Blob([txt], { type: 'image/svg+xml' }), name + '.svg');
  const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(txt), w = +m[1], h = +m[2], k = 3, img = new Image();
  img.onload = () => { const cv = document.createElement('canvas'); cv.width = w * k; cv.height = h * k; const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, w * k, h * k); cv.toBlob(b => dl(b, name + '.png')); };
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(txt);
}
const empty = msg => `<div class="empty"><div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><path d="M8 15h8M9 9h.01M15 9h.01"/></svg><div>${esc(msg)}</div></div></div>`;
const badge = st => st === 'supported' ? '<span class="badge good"><i>✓</i>Supported</span>' : st === 'not_supported' ? '<span class="badge bad"><i>✕</i>Not supported</span>' : '<span class="badge na"><i>?</i>Insufficient data</span>';
const explain = (title, items) => `<div class="explain"><h4>${esc(title)}</h4><ul class="findings">${items.map(x => `<li>${x}</li>`).join('')}</ul></div>`;
function caveat() {
  const r = S.R; if (!r) return '';
  const reps = r.max_reps || 0;
  const arch = archOf(S.mode) ? `<div class="callout"><span class="ic" style="background:var(--silver-3);color:#fff">⟲</span><div><b>Archived results from ${esc(archLabel(archOf(S.mode)))}.</b> You are looking at an older run kept in <span class="mono">${esc(srcPath(S.mode))}</span>. Switch to the current results with the selector at the top.</div></div>` : '';
  if (kindOf(S.mode) === 'campaign' && reps >= 10) return arch;
  return arch + `<div class="callout"><span class="ic">!</span><div><b>${kindOf(S.mode) === 'quick' ? 'Quick-mode results' : kindOf(S.mode) === 'pilot' ? 'Pilot results' : 'Campaign in progress'}: indicative only.</b>
    ${reps} repetition(s) per cell; the paper’s statistics (Mann-Whitney with Holm correction, Cliff’s δ) need 10. Use these to spot problems and trends, not to claim differences.</div></div>`;
}

/* ------------------------------------------------------------------ pages */
const PAGES = { overview, history: historyPage, health, summary, E1: e1, E2: e2, E3: e3, E4: e4, E5: e5, report: reportPage, paper: paperPage, guide };
function render() {
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('on', b.dataset.page === S.page));
  const f = PAGES[S.page] || overview; const y = scrollY; CH = []; Z.i = -1;
  $('#main').innerHTML = banner() + f() + `<footer class="foot"><img src="iccs-logo.png" alt="">Institute of Communication and Computer Systems (ICCS) · OptimusDB evaluation testbed · data from <span class="mono">${esc(srcPath(S.mode))}</span></footer>`;
  scrollTo(0, y); afterRender();
}
function head(tag, title, sub) { return `<div class="page-head"><div><div class="tag">${esc(tag)}</div><h2>${esc(title)}</h2>${sub ? `<div class="sub">${sub}</div>` : ''}</div></div>`; }

function overview() {
  const P = S.P; if (!P) return head('Monitor', 'Live progress') + empty('Waiting for the dashboard server…');
  const e = P.experiment || {}, c = P.campaign || {}, pos = e.pos;
  const fin = c.finished && !P.running;
  const frac = fin ? 1 : pos ? Math.max(0, (pos.i - 1) / pos.n) : 0;
  const state = e.stalled ? ['Possibly stuck', 'warn', `No log line for ${Math.round(e.idle_min)} min. Run .\\diagnose.ps1.`]
    : P.running ? ['Running', 'live', pos ? `Run ${pos.i} of ${pos.n}: ${esc(pos.what)}` : 'starting']
    : c.status === 'finished' ? ['Finished', 'done', `${KIND[c.kind]} run completed ${clock(c.end)}${c.start && c.end ? ' after ' + dur(c.end - c.start) : ''}`]
    : c.status === 'finished_errors' ? ['Finished with errors', 'warn', `${KIND[c.kind]} run ended ${clock(c.end)}; ${esc(c.failed.join(', '))} exited with an error`]
    : c.status === 'stopped' ? ['Stopped', 'warn', `${KIND[c.kind]} run did not reach the end (stopped or the PC restarted). Run the same command again to continue.`]
    : ['Idle', '', 'No test is running.'];
  const notify = canNotify() && P.running ? (Notification.permission === 'granted' ? '<div class="muted" style="margin-top:8px;font-size:12px">🔔 You will get a desktop notification when it finishes (while this page is open).</div>'
    : Notification.permission === 'default' ? '<button class="btn" style="margin-top:10px" data-notify="1">🔔 Notify me when it finishes</button>' : '') : '';
  const R = 58, C = 2 * Math.PI * R;
  const runs = e.runs || []; const errs = runs.filter(r => r.errors > 0).length;
  const planned = c.planned || [];
  const stages = planned.map((x, i) => {
    const ended = c.ended && x in c.ended, cur = c.current === x;
    const cls = ended ? (c.ended[x] ? 'fail' : 'done') : cur ? 'run' : '';
    const p = cur && pos ? Math.round((pos.i - 1) / pos.n * 100) : 0;
    return (i ? '<div class="link"></div>' : '') + `<div class="stage ${cls}" style="--p:${p}%"><div class="n">${x}</div><div><b>${EXP[x] ? EXP[x].t.split(' ')[0] : x}</b><small>${ended ? (c.ended[x] ? `exit ${c.ended[x]}` : 'done') : cur ? `${p}%` : 'waiting'}</small></div></div>`;
  }).join('');
  const feed = runs.slice(-60).map((r, i) => ({ x: i + 1, y: r.p99, tip: tipRows(r.run_id, [['p50', ms(r.p50)], ['p99', ms(r.p99)], ['ops', r.ops], ['errors', r.errors], ['finished', r.t]]), run: r.run_id, s: sysOf(r.run_id) }));
  const bySys = SYS.filter(s => feed.some(f => f.s === s)).map(s => ({ key: s, label: LABEL[s], color: col(s), points: feed.filter(f => f.s === s) }));
  const h = P.host || {};
  return head('Monitor', 'Live progress', 'What the benchmark is doing right now. Updates every 5 seconds; click any finished run to see its operations.') +
  `<div class="grid g4">
    <div class="card kpi span2"><div class="ring-wrap">
      <svg class="ring" viewBox="0 0 150 150"><circle class="track" cx="75" cy="75" r="${R}" fill="none" stroke-width="12"/>
        <circle class="bar" cx="75" cy="75" r="${R}" fill="none" stroke-width="12" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - frac)}" transform="rotate(-90 75 75)"/>
        <text x="75" y="72" text-anchor="middle" style="font-size:28px;font-weight:700">${Math.round(frac * 100)}%</text>
        <text x="75" y="94" text-anchor="middle" style="font-size:11px;fill:var(--muted)">${fin ? 'all done' : pos ? `${pos.i - 1} of ${pos.n} runs` : '—'}</text></svg>
      <div><div class="label" style="font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)">${esc(e.exp || '')} ${e.exp && EXP[e.exp] ? '· ' + EXP[e.exp].t : ''}</div>
        <div class="big-state"><span class="dot ${state[1]}" style="display:inline-block;margin-right:8px"></span>${state[0]}</div>
        <div class="ink2" style="margin-top:4px">${state[2]}</div>${notify}
        <div class="muted" style="margin-top:8px;font-size:12px">log <span class="mono">${esc(e.log || '–')}</span> · last line ${e.idle_min != null ? `${e.idle_min} min ago` : '–'}${P.running_inferred ? ' · running state inferred from the log' : ''}</div></div>
    </div></div>
    <div class="card kpi"><div class="label">Time left</div><div class="value">${P.running && e.eta_s ? dur(e.eta_s) : '–'}</div><div class="note">${P.running && e.eta_s ? 'finish ≈ ' + new Date(Date.now() + e.eta_s * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' (this experiment)' : 'estimated from finished runs'}</div></div>
    <div class="card kpi"><div class="label">Runs finished</div><div class="value">${runs.length}</div><div class="note">${errs ? `<b style="color:var(--critical)">${errs}</b> with failed operations` : 'no failed operations'} · ${(P.failures || []).length} failed runs logged</div></div>
  </div>
  ${planned.length ? `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>${esc((c.kind || '').replace(/^./, m => m.toUpperCase()))} pipeline</h3><div class="hint">Experiments run one after another in the background (${esc(c.log)})</div></div></div><div class="pipeline">${stages}</div></div>` : ''}
  ${(e.warnings || []).length ? `<div class="card" style="margin-top:16px"><h3>Warnings in this experiment</h3><div class="hint">Replication not complete before measuring, or similar. These runs are kept but flagged.</div>${e.warnings.map(w => `<div class="callout" style="margin-top:6px"><span class="ic">!</span><span class="mono">${esc(w)}</span></div>`).join('')}</div>` : ''}
  <div class="grid g3" style="margin-top:16px">
    <div class="card span2"><div class="card-head"><div><h3>P99 latency of each finished run</h3><div class="hint">Most recent 60 runs of ${esc(e.exp || 'the experiment')}, in order; log scale. Click a point to drill down.</div></div></div>
      ${legend(bySys.map(s => s.key))}${lines({ series: bySys, log: true, xLabel: 'run (order finished)', yLabel: 'ms', height: 250 })}</div>
    <div class="card"><h3>Testbed</h3><div class="hint">From the newest fresh-start log</div>
      <table class="t"><tbody>
        <tr><td class="muted">Docker VM</td><td>${esc(h.vm || '–')}</td></tr>
        <tr><td class="muted">Limits</td><td>${esc(h.limits || '–')}</td></tr>
        <tr><td class="muted">Link emulation</td><td>${esc(h.netem || '–')}</td></tr>
        <tr><td class="muted">OptimusDB build</td><td class="mono">${esc((h.optimusdb_source || '–').slice(0, 70))}</td></tr>
        <tr><td class="muted">Smoke test</td><td>${esc(h.smoke || '–')}</td></tr></tbody></table></div>
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Live log</h3><div class="hint">Last 30 lines of <span class="mono">${esc(e.log || '')}</span></div><div class="console" id="console">${colorLog(e.last_lines || [])}</div></div>
    <div class="card"><h3>Recently finished runs</h3><div class="hint">Click a row for latency over time and error breakdown</div>
      <div class="scroll" style="max-height:320px"><table class="t"><thead><tr><th>Run</th><th class="num">ops</th><th class="num">errors</th><th class="num">p50</th><th class="num">p99</th><th>at</th></tr></thead><tbody>
      ${runs.slice(-40).reverse().map(r => `<tr class="click" data-run="${esc(r.run_id)}"><td><i class="sw" style="background:${col(sysOf(r.run_id))}"></i>${esc(r.run_id)}</td><td class="num">${r.ops}</td><td class="num" style="${r.errors ? 'color:var(--critical);font-weight:650' : ''}">${r.errors}</td><td class="num">${ms(r.p50)}</td><td class="num">${ms(r.p99)}</td><td class="muted">${esc(r.t)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">No finished runs yet.</td></tr>'}
      </tbody></table></div></div>
  </div>`;
}
function historyPage() {
  const P = S.P; if (!P) return head('Monitor', 'Run history') + empty('Waiting for the dashboard server…');
  const H = P.history || [];
  const st = s => s === 'finished' ? '<span class="badge good"><i>✓</i>Finished</span>' : s === 'finished_errors' ? '<span class="badge warn"><i>!</i>Finished with errors</span>'
    : s === 'running' ? '<span class="badge"><span class="dot live"></span>Running</span>' : '<span class="badge na"><i>■</i>Stopped</span>';
  const rows = H.map(c => {
    const exps = c.planned.map(x => `<span class="mono" style="color:${x in c.ended ? (c.ended[x] ? 'var(--critical)' : 'var(--good)') : c.current === x ? 'var(--ink)' : 'var(--muted)'}">${x}${x in c.ended ? (c.ended[x] ? '✕' : '✓') : c.current === x ? '…' : ''}</span>`).join(' ');
    const where = c.archive ? `results-archive\\${c.archive}` : 'results (current)';
    const btn = c.has_data ? `<button class="btn${c.source === S.mode ? ' on' : ''}" data-src="${esc(c.source)}">${c.source === S.mode ? 'Showing' : 'View results'}</button>` : '<span class="muted">no results</span>';
    return `<tr><td>${esc(clock(c.start))}</td><td>${esc(KIND[c.kind])}</td><td>${exps}</td><td>${st(c.status)}</td><td>${c.end ? esc(clock(c.end)) : '–'}</td><td class="num">${c.end ? dur(c.end - c.start) : c.status === 'running' ? dur(P.now - c.start) + ' so far' : '–'}</td><td class="mono" style="font-size:12px">${esc(where)}</td><td>${btn}</td></tr>`;
  }).join('');
  return head('Monitor', 'Run history', 'Every run-all.ps1 run found on disk, newest first: the current results folder and every archive folder. Nothing is lost when you close the browser: the dashboard reads the files.') +
  `<div class="card"><h3>All runs</h3><div class="hint">“View results” switches every results page to that run’s data. Several runs of the same kind in one folder share its results (a repeated command resumes and skips finished runs).</div>
    <div style="overflow-x:auto"><table class="t"><thead><tr><th>Started</th><th>Kind</th><th>Experiments</th><th>Status</th><th>Finished</th><th class="num">Duration</th><th>Folder</th><th></th></tr></thead>
    <tbody>${rows || '<tr><td colspan="8" class="muted">No runs found in results\\logs or results-archive\\.</td></tr>'}</tbody></table></div></div>
  <div class="card" style="margin-top:16px"><h3>Where older runs are kept</h3><ul class="findings">
    <li><b>fresh-start.ps1</b> moves the whole <span class="mono">results\\</span> folder to <span class="mono">results-archive\\&lt;date-time&gt;\\</span> before it starts (unless you pass <span class="mono">-DeleteResults</span>).</li>
    <li><b>run-all.ps1</b> does it by itself: when the previous run of the same kind finished and you run its experiments again, it moves that run to <span class="mono">results-archive\\&lt;its start time&gt;-&lt;kind&gt;\\</span> first. An interrupted run is continued instead, and new experiments are added to the current results (<span class="mono">-New</span> / <span class="mono">-Resume</span> override this).</li>
    <li>Every archive folder appears here and in the selector at the top as “Archived …”.</li></ul></div>`;
}
function colorLog(ls) { return ls.map(l => { const e = esc(l); return /WARNING|readable sample/.test(l) ? `<span class="w">${e}</span>` : /Error|Traceback|FAIL/.test(l) ? `<span class="e">${e}</span>` : / done /.test(l) ? `<span class="d">${e}</span>` : /^\S+ (==|\[\d+\/)/.test(l) ? `<span class="b">${e}</span>` : e; }).join('\n'); }

function health() {
  const P = S.P || {}, R = S.R;
  const fl = P.failures || [];
  const comp = R ? R.completion : null;
  const errs = Object.entries((R && R.errors) || {}).map(([k, v]) => `${k}: ${v}`).concat(S.rerr ? [`results not refreshed: ${S.rerr}`] : []);
  const flags = R ? Object.entries(R.analysis).filter(([k]) => /^E\d$/.test(k)).map(([k, v]) => ({ e: k, ...v.flags, n: v.n_runs })) : [];
  return head('Monitor', 'Run health', 'Problems that make results incomplete or less trustworthy: failed runs, data not replicated before measuring, unsupported operations.') +
  (errs.length ? `<div class="callout" style="margin-bottom:16px"><span class="ic">!</span><div><b>Dashboard could not read part of the results.</b><div class="mono">${errs.map(esc).join('<br>')}</div></div></div>` : '') +
  `<div class="grid g2">
    <div class="card"><h3>Completion matrix</h3><div class="hint">Finished runs per system and experiment (${esc(srcLabel(S.mode))})</div>
      ${comp ? `<table class="t matrix"><thead><tr><th>System</th>${['E1', 'E2', 'E3', 'E4', 'E5'].map(e => `<th class="num">${e}</th>`).join('')}</tr></thead><tbody>
      ${SYS.map(s => `<tr><td><i class="sw" style="background:${col(s)}"></i>${LABEL[s]}</td>${['E1', 'E2', 'E3', 'E4', 'E5'].map(e => `<td class="m"><span class="mbox ${comp[s][e] ? 'has' : ''}">${comp[s][e] || '·'}</span></td>`).join('')}</tr>`).join('')}</tbody></table>` : empty('No results loaded.')}</div>
    <div class="card"><h3>Data-quality flags</h3><div class="hint">Counted from the notes column of each result file</div>
      <table class="t"><thead><tr><th>Exp.</th><th class="num">runs</th><th class="num">not replicated in time</th><th class="num">unsupported</th><th class="num">dropped ops</th><th class="num">node died</th><th class="num">client-limited</th></tr></thead><tbody>
      ${flags.map(f => `<tr><td>${f.e}</td><td class="num">${f.n}</td><td class="num" style="${f.settle_timeout ? 'color:var(--critical);font-weight:650' : ''}">${f.settle_timeout}</td><td class="num">${f.unsupported}</td><td class="num">${f.dropped}</td><td class="num" style="${f.node_down ? 'color:var(--critical);font-weight:650' : ''}">${f.node_down || 0}</td><td class="num" style="${f.client_limited ? 'color:var(--critical);font-weight:650' : ''}">${f.client_limited || 0}</td></tr>`).join('')}</tbody></table>
      <p class="muted" style="font-size:12px">“Not replicated in time”: the preloaded data was not readable on every host before measuring started; that run measured a partly replicated store. “Dropped ops”: the load generator could not issue every scheduled operation (the system was saturated). “Node died”: a node of the system stopped answering during the run; the testbed redeploys it before the next run, and that run's numbers include the failure. “Client-limited”: the load generator itself ran out of CPU or issued operations late (median &gt; 10 ms), so the run measures the client, not the system; E2 does not count such a step against the system.</p></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>Failed runs</h3><div class="hint">From failures.log; a failed run is not written to the results and is retried when the experiment is started again</div>
    ${fl.length ? `<div class="console" style="height:220px">${fl.map(f => `<span class="e">[${esc(f.mode)}]</span> ${esc(f.line)}`).join('\n')}</div>` : '<div class="muted">No failed runs logged.</div>'}</div>
  <div class="card" style="margin-top:16px"><div class="card-head"><div><h3>Full experiment log</h3><div class="hint">Last 300 lines of ${esc((P.experiment || {}).log || '')}</div></div><div class="tools"><button class="iconbtn" style="background:var(--charcoal)" onclick="loadFullLog()">Load</button></div></div><div class="console" id="fullLog" style="height:420px">Press Load.</div></div>`;
}
async function loadFullLog() { if (STATIC) { $('#fullLog').textContent = 'Logs are not part of the published snapshot; open the dashboard on the testbed PC.'; return; } const n = (S.P.experiment || {}).log; if (!n) return; const r = await j(`/api/log?name=${encodeURIComponent(n)}&n=300`); $('#fullLog').innerHTML = colorLog(r.lines); $('#fullLog').scrollTop = 1e9; }

function summary() {
  const R = S.R; if (!R) return head('Results', 'Findings & hypotheses') + empty(`No results in ${srcPath(S.mode)} yet.`);
  const H = R.hypotheses, A = R.analysis;
  const st = A.E1.stats || [];
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const G = window.OptimusSummary ? OptimusSummary.build(OptimusSummary.fromResults(R), dark ? { pal: { bg: '#1a1a19', ink: '#f0efec', ink2: '#c3c2b7', muted: '#898781', rule: '#3a3936', cell0: '#262624', cellHi: '#2f8fa6' } } : {}) : null;
  S.glance = G;
  return head('Results', 'Findings & hypotheses', 'Each hypothesis from Section 8, checked against the data present, with the evidence in plain words.') + caveat() +
  (G ? `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>Results at a glance</h3><div class="hint">Every experiment in one view. Radar: each axis runs from the worst measured value (inner ring) to the best (outer ring), log scale; OptimusDB filled. Right: the values themselves and the hypothesis verdicts. Not a weighted score.</div></div>
     <div class="tools"><button class="btn ghost" type="button" onclick="exportChart(OptimusSummary.build(OptimusSummary.fromResults(S.R)).svg,'svg','optimusdb-results-at-a-glance')">SVG</button><button class="btn ghost" type="button" onclick="exportChart(OptimusSummary.build(OptimusSummary.fromResults(S.R)).svg,'png','optimusdb-results-at-a-glance')">PNG</button><button class="btn ghost" type="button" data-go="paper">Paper figures</button></div></div>
     <div class="glance">${G.svg}</div></div>` : '') +
  `<div class="grid g2" style="margin-top:16px">${['H1', 'H2', 'H3', 'H4', 'H5'].map(h => `<div class="card"><div class="card-head"><div><div class="muted" style="font-size:11px;letter-spacing:.16em">${h} · ${Object.keys(EXP).find(e => EXP[e].h === h)}</div><h3 style="font-size:15px">${esc(HYP[h])}</h3></div><div class="tools">${badge(H[h].state)}</div></div>
     <div class="ink2">${esc(H[h].text)}</div>${H[h].detail ? `<div class="muted" style="font-size:12px;margin-top:6px">${esc(H[h].detail)}</div>` : ''}</div>`).join('')}
   </div><div class="card" style="margin-top:16px"><h3>What the results say</h3><div class="hint">Generated from the numbers; each line names its source</div>
     ${['E1', 'E2', 'E3', 'E4', 'E5'].map(e => (A[e].text || []).length ? `<div style="margin:8px 0 2px;font-weight:650">${e} · ${EXP[e].t}</div><ul class="findings" style="margin:0;padding-left:18px">${A[e].text.map(t => `<li>${esc(t)}</li>`).join('')}</ul>` : '').join('') || '<div class="muted">No findings yet.</div>'}</div>
  <div class="card" style="margin-top:16px"><h3>E1 statistics: OptimusDB vs each baseline (P99 per repetition)</h3><div class="hint">Mann-Whitney U, Holm-corrected within each workload; Cliff’s δ &lt; 0 means OptimusDB is faster. Needs at least 3 repetitions per cell.</div>
    ${st.length && st.some(x => x.p != null) ? `<table class="t"><thead><tr><th>Workload</th><th>Baseline</th><th class="num">p</th><th class="num">p (Holm)</th><th class="num">Cliff’s δ</th><th>Reading</th></tr></thead><tbody>
    ${st.map(x => `<tr><td>${x.workload}</td><td><i class="sw" style="background:${col(x.baseline)}"></i>${LABEL[x.baseline]}</td><td class="num">${x.p == null ? '–' : x.p.toFixed(4)}</td><td class="num">${x.p_holm == null ? '–' : x.p_holm.toFixed(4)}</td><td class="num">${x.cliffs_delta == null ? '–' : x.cliffs_delta.toFixed(2)}</td>
      <td>${x.p_holm != null && x.p_holm < 0.05 ? (x.cliffs_delta < 0 ? 'OptimusDB faster (significant)' : 'baseline faster (significant)') : 'no significant difference'}${x.cliffs_delta != null ? ` · effect ${Math.abs(x.cliffs_delta) >= .474 ? 'large' : Math.abs(x.cliffs_delta) >= .33 ? 'medium' : Math.abs(x.cliffs_delta) >= .147 ? 'small' : 'negligible'}` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="muted">Not enough repetitions yet (quick and pilot runs have one).</div>'}</div>`;
}

function e1() {
  const R = S.R; if (!R) return head('E1', EXP.E1.t) + empty(`No results in ${srcPath(S.mode)} yet.`);
  const cells = R.analysis.E1.cells; if (!cells.length) return head('E1', EXP.E1.t, EXP.E1.q) + empty('No E1 runs yet.');
  const m = S.metric, key = { p50: 'p50', p99: 'p99', p999: 'p999' }[m];
  const systems = SYS.filter(s => cells.some(c => c.system === s));
  const wls = ['WA', 'WB', 'WC', 'WO'].filter(w => cells.some(c => c.workload === w && c.doc_size === '2KB'));
  const get = (w, s) => cells.find(c => c.workload === w && c.system === s && c.doc_size === '2KB');
  const v = (w, s) => { const c = get(w, s); if (!c) return null; if (c.unsupported) return { unsupported: true };
    return { v: c[key], mark: key === 'p99' ? c.p50 : null, run: c.reps === 1 ? `E1-${s}-${w}-2KB-1` : null,
             tip: tipRows(`${LABEL[s]} · ${w}`, [['P50', ms(c.p50)], ['P95', ms(c.p95)], ['P99', ms(c.p99)], ['P99.9', ms(c.p999)], ['errors', c.error_pct == null ? '–' : c.error_pct.toFixed(2) + ' %'], ['achieved', fmt(c.achieved) + ' ops/s'], ['repetitions', c.reps]]) }; };
  const sizes = ['256B', '2KB', '8KB', '64KB'];
  const bytes = { '256B': 256, '2KB': 2048, '8KB': 8192, '64KB': 65536 };
  const sizeSeries = systems.map(s => ({ key: s, label: LABEL[s], color: col(s), points: sizes.map(z => { const c = cells.find(x => x.system === s && x.workload === 'WO' && x.doc_size === z); return c && c.p99 != null ? { x: bytes[z], y: c.p99, tip: tipRows(`${LABEL[s]} · WO ${z}`, [['P99', ms(c.p99)], ['P50', ms(c.p50)], ['repetitions', c.reps]]) } : null; }).filter(Boolean) }));
  const hasSizes = sizeSeries.some(s => s.points.length > 1);
  return head('E1 · ' + EXP.E1.rq, EXP.E1.t, EXP.E1.q) + caveat() +
  `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>${m === 'p50' ? 'Median (P50)' : m === 'p99' ? 'P99 (slowest 1 %)' : 'P99.9 (slowest 0.1 %)'} latency per workload, 2 KB documents</h3><div class="hint">Lower is better. ${m === 'p99' ? 'The black tick on each bar is the median (P50); the gap between tick and top is the tail. ' : ''}Hover for all percentiles; click a bar (single-repetition runs) for its operations.</div></div>
     <div class="tools"><div class="seg">${['p50', 'p99', 'p999'].map(x => `<button class="${S.metric === x ? 'on' : ''}" onclick="S.metric='${x}';render()">${x === 'p999' ? 'P99.9' : x.toUpperCase()}</button>`).join('')}</div>
     <div class="seg">${['log', 'linear'].map(x => `<button class="${S.scale === x ? 'on' : ''}" onclick="S.scale='${x}';render()">${x}</button>`).join('')}</div></div></div>
     ${legend(systems)}${bars({ groups: wls, systems, val: v, log: S.scale === 'log', unit: 'ms', glabel: w => WL[w].split(' · ')[0] + ' · ' + WL[w].split(' · ')[1].split(' (')[0] })}</div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Document size series (WO, P99)</h3><div class="hint">How latency grows with document size; log axes</div>${hasSizes ? legend(systems) + lines({ series: sizeSeries, log: true, logX: true, xLabel: 'document size (bytes)', yLabel: 'ms', height: 300, w: 560 }) : empty('Only one document size in these results (quick mode measures 2 KB only).')}</div>
    <div>${explain('What this shows', (R.analysis.E1.text.length ? R.analysis.E1.text : ['No comparable results yet.']).map(esc))}
      <div style="height:12px"></div>${explain('How to read it', ['<b>P50</b>: the typical operation. <b>P99</b>: 1 in 100 operations is slower than this — what users notice. <b>P99.9</b>: the extreme tail.',
        'Latency is measured from the <i>scheduled</i> start of each operation (open-loop load), so queueing inside a struggling system shows up instead of being hidden.',
        'A system with many failed operations can look fast: its latency covers only the operations that succeeded. Check the error column.',
        'OpenDHT has no search: its query share in WO is reported as <i>unsupported</i> and excluded, and 64 KB documents exceed its 64 KiB value limit.'])}</div>
  </div>
  <div class="card" style="margin-top:16px"><h3>All E1 cells</h3><div class="hint">Medians over repetitions</div><div class="scroll"><table class="t"><thead><tr><th>System</th><th>Workload</th><th>Size</th><th class="num">reps</th><th class="num">P50</th><th class="num">P95</th><th class="num">P99</th><th class="num">P99.9</th><th class="num">errors</th><th class="num">ops/s</th></tr></thead><tbody>
    ${[...cells].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system)).map(c => `<tr class="${c.reps === 1 ? 'click' : ''}" ${c.reps === 1 ? `data-run="E1-${c.system}-${c.workload}-${c.doc_size}-1"` : ''}><td><i class="sw" style="background:${col(c.system)}"></i>${LABEL[c.system]}</td><td>${c.workload}</td><td>${c.doc_size}</td><td class="num">${c.reps}</td>${c.unsupported ? '<td colspan="6" class="muted">unsupported</td>' : `<td class="num">${ms(c.p50)}</td><td class="num">${ms(c.p95)}</td><td class="num">${ms(c.p99)}</td><td class="num">${ms(c.p999)}</td><td class="num" style="${(c.error_pct || 0) > 1 ? 'color:var(--critical);font-weight:650' : ''}">${c.error_pct == null ? '–' : c.error_pct.toFixed(2) + ' %'}</td><td class="num">${fmt(c.achieved)}</td>`}</tr>`).join('')}</tbody></table></div></div>`;
}

function e2() {
  const R = S.R; if (!R) return head('E2', EXP.E2.t) + empty(`No results in ${srcPath(S.mode)} yet.`);
  const ser = R.analysis.E2.series; if (!ser.length) return head('E2 · ' + EXP.E2.rq, EXP.E2.t, EXP.E2.q) + empty('No E2 runs yet.');
  const recs = [...new Set(ser.map(s => s.records))].sort((a, b) => a - b); if (!recs.includes(S.e2rec)) S.e2rec = recs[recs.length - 1];
  const cur = ser.filter(s => s.records === S.e2rec); const systems = SYS.filter(s => cur.some(c => c.system === s));
  const ach = systems.map(s => { const c = cur.find(x => x.system === s); return { key: s, label: LABEL[s], color: col(s), points: c.points.map(p => ({ x: p.offered, y: p.achieved, tip: tipRows(`${LABEL[s]} @ ${p.offered} ops/s`, [['achieved', fmt(p.achieved) + ' ops/s'], ['P99', ms(p.p99)], ['errors', p.error_rate == null ? '–' : (p.error_rate * 100).toFixed(2) + ' %'], ['repetitions', p.reps]]) })) }; });
  const p99 = systems.map(s => { const c = cur.find(x => x.system === s); return { key: s, label: LABEL[s], color: col(s), points: c.points.map(p => ({ x: p.offered, y: p.p99, tip: tipRows(`${LABEL[s]} @ ${p.offered} ops/s`, [['P99', ms(p.p99)], ['achieved', fmt(p.achieved) + ' ops/s']]) })) }; });
  return head('E2 · ' + EXP.E2.rq, EXP.E2.t, EXP.E2.q) + caveat() +
  `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>Achieved vs offered load (WO)</h3><div class="hint">On the dashed line a system serves everything asked of it; where its curve bends away, it is saturated.</div></div>
    <div class="tools"><div class="seg">${recs.map(r => `<button class="${S.e2rec === r ? 'on' : ''}" onclick="S.e2rec=${r};render()">${(+r).toLocaleString()} records</button>`).join('')}</div></div></div>
    ${legend(systems)}${lines({ series: ach, diagonal: true, xLabel: 'offered load (ops/s)', yLabel: 'achieved ops/s' })}</div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>P99 latency vs offered load</h3><div class="hint">Latency climbs steeply as a system approaches saturation; log scale</div>${legend(systems)}${lines({ series: p99, log: true, xLabel: 'offered load (ops/s)', yLabel: 'ms', height: 320, w: 560 })}</div>
    <div>${explain('What this shows', R.analysis.E2.text.map(esc))}<div style="height:12px"></div>
      <div class="card"><h3>Saturation point</h3><div class="hint">Highest offered load still served at ≥ 90 % with < 1 % errors</div><table class="t"><tbody>${ser.map(s => `<tr><td><i class="sw" style="background:${col(s.system)}"></i>${LABEL[s.system]}</td><td class="muted">${(+s.records).toLocaleString()} records</td><td class="num"><b>${s.saturation == null ? '–' : s.saturation + ' ops/s'}</b></td></tr>`).join('')}</tbody></table></div></div>
  </div>`;
}

function e3() {
  const R = S.R; if (!R) return head('E3', EXP.E3.t) + empty(`No results in ${srcPath(S.mode)} yet.`);
  const cells = R.analysis.E3.cells; if (!cells.length) return head('E3 · ' + EXP.E3.rq, EXP.E3.t, EXP.E3.q) + empty('No E3 runs yet.');
  const recs = [...new Set(cells.map(c => c.records))].sort((a, b) => a - b); if (!recs.includes(S.e3rec)) S.e3rec = recs[recs.length - 1];
  const cur = cells.filter(c => c.records === S.e3rec);
  const targets = [...new Map(cur.map(c => [`${c.system}|${c.path}`, c])).keys()].sort((a, b) => SYS.indexOf(a.split('|')[0]) - SYS.indexOf(b.split('|')[0]));
  const qs = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'].filter(q => cur.some(c => c.query === q));
  const vals = cur.map(c => c.mean).filter(v => v > 0); const lo = Math.log10(Math.min(...vals, 1)), hi = Math.log10(Math.max(...vals, 10));
  const shade = v => { const k = Math.max(0, Math.min(4, Math.floor((Math.log10(v) - lo) / ((hi - lo) || 1) * 4.999))); return [`var(--seq-${k})`, k >= 3 ? '#fff' : '#0b0b0b']; };
  const QD = { Q1: 'one resource by id', Q2: 'all resources with status Running', Q3: 'eu-west resources with ≥ 4 CPU and ≥ 8 GB', Q4: 'count and CPU per region (GROUP BY)', Q5: 'allocations of eu-west resources (join)' };
  return head('E3 · ' + EXP.E3.rq, EXP.E3.t, EXP.E3.q) + caveat() +
  `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>Mean query time and correctness</h3><div class="hint">Darker = slower (log-scaled shading). ✓ correct row count · ✕ wrong or incomplete · n/s not supported by the system’s interface · failed = the query raised an error (hover for it).</div></div>
    <div class="tools"><div class="seg">${recs.map(r => `<button class="${S.e3rec === r ? 'on' : ''}" onclick="S.e3rec=${r};render()">${(+r).toLocaleString()} records</button>`).join('')}</div></div></div>
    <div class="scroll"><table class="t heat"><thead><tr><th>System · path</th>${qs.map(q => `<th class="num" title="${QD[q]}">${q}</th>`).join('')}</tr></thead><tbody>
    ${targets.map(t => { const [s, p] = t.split('|'); return `<tr><td><i class="sw" style="background:${col(s)}"></i>${LABEL[s]} <span class="muted">· ${esc(p)}</span></td>${qs.map(q => { const c = cur.find(x => x.system === s && x.path === p && x.query === q);
      if (!c) return '<td></td>'; if (c.unsupported) return '<td class="cell muted" data-tip="' + esc(tipRows(`${LABEL[s]} ${q}`, [['', 'not supported']])) + '">n/s</td>';
      if (c.failed || c.mean == null) return '<td class="cell" style="color:var(--critical);font-weight:650" data-tip="' + esc(tipRows(`${LABEL[s]} ${q}`, [['', 'failed'], ['error', c.error || 'no measurement']])) + '">failed</td>';
      const [bg, fg] = shade(c.mean); const ok = (c.correct || 0) >= .5;
      return `<td class="cell" style="background:${bg};color:${fg}" data-tip="${esc(tipRows(`${LABEL[s]} · ${p} · ${q}`, [['mean', ms(c.mean)], ['P95', ms(c.p95)], ['rows returned', fmt(c.rows_returned, 0)], ['rows expected', fmt(c.rows_expected, 0)], ['correct', ok ? 'yes' : 'NO'], ['repetitions', c.reps]]))}">${ok ? '✓' : '✕'} ${ms(c.mean)}</td>`; }).join('')}</tr>`; }).join('')}
    </tbody></table></div>
    <div class="legend" style="margin-top:10px">${qs.map(q => `<span><b>${q}</b>&nbsp;${QD[q]}</span>`).join('')}</div></div>
  <div class="grid g2" style="margin-top:16px">${explain('What this shows', R.analysis.E3.text.map(esc))}
    ${explain('How to read it', ['Systems without a query language answer by fetching documents and filtering in the client (“client_filter”); their time grows with the data volume.', 'A time is only comparable when the answer is <b>correct</b>: a fast but incomplete answer (✕) is not a win.', 'OptimusDB appears twice: <i>crdt</i> (its document query) and <i>sqlite</i> (its SQL engine).'])}</div>`;
}

function e4() {
  const R = S.R; if (!R) return head('E4', EXP.E4.t) + empty(`No results in ${srcPath(S.mode)} yet.`);
  const cells = R.analysis.E4.cells; if (!cells.length) return head('E4 · ' + EXP.E4.rq, EXP.E4.t, EXP.E4.q) + empty('No E4 runs yet.');
  const systems = SYS.filter(s => cells.some(c => c.system === s)); const lv = [...new Set(cells.map(c => c.offered))].sort((a, b) => a - b);
  const mk = k => (l, s) => { const c = cells.find(x => x.system === s && x.offered === l); return c && c[k] != null ? { v: c[k], tip: tipRows(`${LABEL[s]} @ ${l} ops/s`, [['CPU', fmt(c.cpu) + ' %'], ['memory', fmt(c.rss) + ' MB'], ['disk / 1k docs', fmt(c.disk) + ' MB'], ['network / op', fmt(c.net) + ' KB']]) } : null; };
  return head('E4 · ' + EXP.E4.rq, EXP.E4.t, EXP.E4.q) + caveat() +
  `<div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>CPU per edge host</h3><div class="hint">% of one core, by offered load</div>${legend(systems)}${bars({ groups: lv, systems, val: mk('cpu'), unit: '% CPU', glabel: l => l + ' ops/s', height: 320, w: 560, refLine: { v: 60, label: 'H4 limit 60 %' } })}</div>
    <div class="card"><h3>Resident memory per edge host</h3><div class="hint">MB, by offered load</div>${legend(systems)}${bars({ groups: lv, systems, val: mk('rss'), unit: 'MB', glabel: l => l + ' ops/s', height: 320, w: 560, refLine: { v: 512, label: 'H4 limit 512 MB' } })}</div>
  </div>
  <div class="card" style="margin-top:16px"><h3>All E4 cells</h3><table class="t"><thead><tr><th>System</th><th class="num">ops/s</th><th class="num">reps</th><th>started</th><th class="num">CPU %</th><th class="num">memory MB</th><th class="num">disk MB / 1k docs</th><th class="num">network KB / op</th></tr></thead><tbody>
    ${cells.map(c => `<tr><td><i class="sw" style="background:${col(c.system)}"></i>${LABEL[c.system]}</td><td class="num">${c.offered}</td><td class="num">${c.reps}</td><td>${c.started_ok ? '<span class="badge good"><i>✓</i>yes</span>' : '<span class="badge bad"><i>✕</i>no</span>'}</td><td class="num">${fmt(c.cpu)}</td><td class="num">${fmt(c.rss)}</td><td class="num">${fmt(c.disk)}</td><td class="num">${fmt(c.net)}</td></tr>`).join('')}</tbody></table></div>
  <div class="grid g2" style="margin-top:16px">${explain('What this shows', (R.analysis.E4.text.length ? R.analysis.E4.text : ['Resource figures per system and load level.']).map(esc))}
    ${explain('Caveat', ['The single-machine testbed emulates edge hosts as containers with CPU and memory limits; H4 is stated for Raspberry Pi 4 boards, so these figures are indicative of relative cost, not absolute Pi figures.'])}</div>`;
}

function e5() {
  const R = S.R; if (!R) return head('E5', EXP.E5.t) + empty(`No results in ${srcPath(S.mode)} yet.`);
  const cells = R.analysis.E5.cells; if (!cells.length) return head('E5 · ' + EXP.E5.rq, EXP.E5.t, EXP.E5.q) + empty('No E5 runs yet.');
  const systems = SYS.filter(s => cells.some(c => c.system === s));
  const groups = [...new Set(cells.map(c => `${c.contention}% · ${c.partition_s}s · ${c.shape}`))];
  const v = (g, s) => { const c = cells.find(x => x.system === s && `${x.contention}% · ${x.partition_s}s · ${x.shape}` === g); return c && c.convergence != null ? { v: c.convergence, tip: tipRows(`${LABEL[s]} · ${g}`, [['convergence', fmt(c.convergence) + ' s'], ['write availability', fmt(c.availability) + ' %'], ['acknowledged writes', c.ack], ['lost acknowledged', c.lost], ['replicas identical', c.identical === 1 ? 'yes' : 'NO'], ['repetitions', c.reps]]) } : null; };
  return head('E5 · ' + EXP.E5.rq, EXP.E5.t, EXP.E5.q) + caveat() +
  `<div class="card" style="margin-top:16px"><h3>Time to converge after the partition heals</h3><div class="hint">Seconds until every replica holds identical data; lower is better. Groups: write contention · partition length · split shape.</div>
    ${legend(systems)}${bars({ groups, systems, val: v, log: S.scale === 'log', unit: 's', height: 260 })}</div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h3>Safety: lost writes and identical replicas</h3><div class="hint">The two properties H5 requires</div><div class="scroll"><table class="t"><thead><tr><th>System</th><th>Cell</th><th class="num">availability</th><th class="num">lost</th><th>identical</th></tr></thead><tbody>
      ${cells.map(c => `<tr><td><i class="sw" style="background:${col(c.system)}"></i>${LABEL[c.system]}</td><td class="muted">${c.contention}% · ${c.partition_s}s · ${esc(c.shape)}</td><td class="num">${fmt(c.availability)} %</td><td class="num">${c.lost ? `<span class="badge bad"><i>✕</i>${c.lost}</span>` : '<span class="badge good"><i>✓</i>0</span>'}</td><td>${c.identical === 1 ? '<span class="badge good"><i>✓</i>yes</span>' : '<span class="badge bad"><i>✕</i>no</span>'}</td></tr>`).join('')}</tbody></table></div></div>
    <div>${explain('What this shows', R.analysis.E5.text.map(esc))}<div style="height:12px"></div>${explain('How to read it', ['<b>Write availability</b>: share of writes accepted on both sides during the split.', '<b>Lost acknowledged writes</b>: writes the system confirmed but that are missing after healing — must be 0.', '<b>Identical</b>: all replicas end with the same data.'])}</div>
  </div>`;
}

function guide() {
  return head('Reference', 'How to read this dashboard') + `<div class="grid g2">
  ${explain('The setup', ['8 emulated hosts (2 cloud, 2 fog, 4 edge) with CPU and memory limits; links between them get the delays, jitter and loss of Table 7 (applied on outgoing traffic, so values are one-way).', 'Only the system under test runs; data are preloaded on an unshaped network, then replication is confirmed on every host before measuring.', 'Load is open-loop: operations are issued on a Poisson schedule, independent of how fast the system answers.'])}
  ${explain('Workloads (E1, E2)', Object.values(WL).map(esc).concat(['Keys follow a Zipfian distribution (some documents are much hotter than others), as in YCSB.']))}
  ${explain('Percentiles', ['P50: the median operation. P95, P99, P99.9: 5 %, 1 %, 0.1 % of operations are slower.', 'Tail ratio P99.9/P50: how much worse the extreme tail is than the typical case.'])}
  ${explain('Modes', ['<b>Quick</b>: every experiment once on 10⁴ records, short windows — a functional check.', '<b>Pilot</b>: E1 on a few cells — timing check.', '<b>Campaign</b>: the full design with 5–10 repetitions — the results for the paper.'])}
  ${explain('Statistics', ['Repetitions are the unit of analysis: percentiles are computed inside each run and compared across runs.', 'Differences are tested with Mann-Whitney U, Holm-corrected for multiple baselines; effect sizes with Cliff’s δ (|δ| ≥ 0.147 small, 0.33 medium, 0.474 large).'])}
  ${explain('Verdict badges', ['<span class="badge good"><i>✓</i>Supported</span> the data satisfy the hypothesis’ criterion.', '<span class="badge bad"><i>✕</i>Not supported</span> they do not.', '<span class="badge na"><i>?</i>Insufficient data</span> the needed runs are missing. With fewer than 10 repetitions every verdict is indicative.'])}
  </div>`;
}

/* ------------------------------------------------------------------ run drill-down */
async function openRun(run) {
  const box = $('#modalBox'); box.classList.remove('wide'); $('#modal').classList.add('open');
  box.innerHTML = `<button class="x">Close</button><h3 style="margin-top:0">${esc(run)}</h3><div class="muted">loading operations…</div>`;
  let d; try { d = await j(`/api/ops?mode=${encodeURIComponent(S.mode)}&run=${encodeURIComponent(run)}`); } catch (e) { d = { error: String(e) }; }
  if (d.error) { box.innerHTML = `<button class="x">Close</button><h3 style="margin-top:0">${esc(run)}</h3>${empty(d.error)}`; return; }
  const ok = d.points.filter(p => p[2]), bad = d.points.filter(p => !p[2]);
  const W = 900, H = 300, L = 52, T = 10, B = 34, iw = W - L - 12, ih = H - T - B;
  const xmax = Math.max(...d.points.map(p => p[0]), 1), ys = d.points.map(p => p[1]).filter(v => v > 0);
  const sc = scaleY(Math.max(Math.min(...ys, 1) / 1.5, 0.01), Math.max(...ys, 10) * 1.1, ih, true);
  let o = `<svg viewBox="0 0 ${W} ${H}">`;
  sc.ticks.forEach(t => { const y = T + sc.f(t); if (y < T - 1 || y > T + ih + 1) return; o += `<line class="gridline" x1="${L}" x2="${W - 12}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${tickLbl(t)}</text>`; });
  o += `<line class="axis" x1="${L}" x2="${W - 12}" y1="${T + ih}" y2="${T + ih}"/><text x="4" y="${T + 10}">ms</text><text x="${L + iw / 2}" y="${H - 4}" text-anchor="middle">seconds since start</text>`;
  [0, .25, .5, .75, 1].forEach(k => o += `<text x="${L + k * iw}" y="${H - 18}" text-anchor="middle">${Math.round(k * xmax)}</text>`);
  ok.forEach(p => o += `<circle cx="${L + p[0] / xmax * iw}" cy="${T + sc.f(Math.max(p[1], .01))}" r="2" fill="${col(sysOf(run))}" opacity=".55"/>`);
  bad.forEach(p => o += `<path d="M${L + p[0] / xmax * iw - 3},${T + sc.f(Math.max(p[1], .01)) - 3}l6,6m0,-6l-6,6" stroke="var(--critical)" stroke-width="1.6"/>`);
  o += '</svg>';
  const kinds = Object.entries(d.kinds), errs = Object.entries(d.errors);
  box.innerHTML = `<button class="x">Close</button><div class="tag muted" style="font-size:11px;letter-spacing:.18em">RUN DRILL-DOWN</div><h3 style="margin:2px 0 4px;font-size:18px">${esc(run)}</h3>
    <div class="hint">${d.n.toLocaleString()} operations · dots: successful operations · <span style="color:var(--critical)">✕</span>: failed (drawn at the time they gave up) · log scale</div>
    <div class="chart">${o}</div>
    <div class="grid g2" style="margin-top:12px"><div><h3>By operation type</h3><table class="t"><thead><tr><th>Type</th><th class="num">ok</th><th class="num">failed</th></tr></thead><tbody>${kinds.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v[0]}</td><td class="num" style="${v[1] ? 'color:var(--critical);font-weight:650' : ''}">${v[1]}</td></tr>`).join('')}</tbody></table></div>
    <div><h3>Failures by cause</h3>${errs.length ? `<table class="t"><tbody>${errs.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v}</td></tr>`).join('')}</tbody></table>
      <p class="muted" style="font-size:12px">TimeoutError: no answer within 10 s · ConnectError/ReadError: the service refused or dropped the connection · HTTPStatusError: it answered with an error code · NotImplementedError: operation not supported (excluded from errors).</p>` : '<div class="muted">No failed operations.</div>'}</div></div>`;
}

/* ------------------------------------------------------------------ loop */
function afterRender() { const c = $('#console'); if (c) c.scrollTop = 1e9; document.body.classList.toggle('on-report', S.page === 'report'); if (S.page === 'report') loadReport();
  if (S.page === 'paper') PaperExport.load(S.mode, j); }
function paperPage() { return head('Report', 'Paper figures', 'Publication-ready figures, data and LaTeX tables of the selected run, in one download.') + caveat() + PaperExport.page(srcLabel(S.mode)); }

/* ------------------------------------------------------------------ evaluation report (report/report.js renders the pages) */
const REP = { tpl: null, io: null };
function reportPage() {
  return head('Report', 'Evaluation report', 'Built from the result files of the run selected at the top, current or archived. A copy is also saved with each run when it finishes, so the report of every run stays as it was.') +
  `<div class="rpt" id="rptRoot">
    <div class="card rpt-top"><div class="rpt-src" id="rptSrc"><div><div class="l">Run</div><div class="v">${esc(srcLabel(S.mode))}</div></div><div><div class="l">Status</div><div class="v">Building the report…</div></div></div>
      <div class="rpt-actions"><button class="abtn" type="button" id="rptPrint">Print / Save as PDF</button><button class="abtn ghost" type="button" id="rptSvg">Export all figures (SVG)</button>
        <a class="abtn ghost" id="rptCopy" href="#" aria-disabled="true">Download saved copy</a><span class="sp"></span>
        <label class="srcsw"><input type="checkbox" id="rptShowSrc"> Show where the text comes from</label></div>
      <div class="srclegend" id="rptLegend" hidden><span><i style="background:var(--src-data)"></i>Data: figures and tables computed from the run</span><span><i style="background:var(--src-rule)"></i>Generated text: sentences filled from the data by fixed rules</span><span><i style="background:var(--src-fixed)"></i>Method text: fixed, changes only with the configuration</span><span><i style="background:var(--src-notes)"></i>Analyst notes: written by a person after review</span></div></div>
    <div class="rpt-layout"><aside class="card rpt-outline" aria-label="Report contents"><h3>Contents</h3><ol id="rptOutline"></ol></aside>
      <div class="rpt-pages"><div id="pages"><div class="rpt-empty">Building the report…</div></div></div></div>
    <div id="measure"></div><div class="toast" id="rptToast"></div></div>`;
}
async function loadReport() {
  const mode = S.mode;
  try {
    if (!REP.tpl) REP.tpl = await (await fetch('report/template.html', { cache: 'no-store' })).text();
    const data = await j(`/api/report?mode=${encodeURIComponent(mode)}`);
    if (!$('#rptRoot') || S.mode !== mode) return;           // the page or the run changed meanwhile
    const m = data.meta, saved = m.saved || [];
    const runs = Object.values(data.completion || {}).reduce((a, x) => a + Object.values(x).reduce((p, v) => p + v, 0), 0);
    const cell = (l, v) => `<div><div class="l">${l}</div><div class="v">${v}</div></div>`;
    const src = (extra) => cell('Run', `${esc(srcLabel(mode))}${m.commit ? ` · build <span class="mono">${esc(m.commit.slice(0, 7))}</span>` : ''}`) +
      cell('Built from', `${m.files.results} result files · ${m.files.ops} per-operation files · ${m.files.logs} logs`) + cell('Generated', STATIC ? `${esc(m.generated)}, when the snapshot was built` : `${esc(m.generated)}, when this page opened`) +
      cell('Saved copy', saved.length ? `<span class="mono">${esc(srcPath(mode))}\\${esc(saved[saved.length - 1])}</span>` : 'none yet (written when a run finishes)') +
      cell('Analyst notes', data.notes ? `<span class="mono">${esc(data.notes_path)}</span>` : `none · add <span class="mono">${esc(data.notes_path)}</span> to include them`) + extra;
    if (!runs) { $('#rptSrc').innerHTML = src(cell('Pages', '–')); $('#pages').innerHTML = `<div class="rpt-empty">No results in ${esc(srcPath(mode))} yet. The report appears once a run has written results.</div>`; return; }
    OptimusReport.setToast($('#rptToast'));
    const info = OptimusReport.render({ data, template: REP.tpl, host: $('#pages'), measure: $('#measure') });
    $('#rptSrc').innerHTML = src(cell('Pages', `${info.pages} pages · ${info.figures} figures · ${info.tables} numbered tables`));
    const cp = $('#rptCopy');
    if (saved.length) { cp.href = apiUrl(`/api/report-copy?mode=${encodeURIComponent(mode)}&name=${encodeURIComponent(saved[saved.length - 1])}`); cp.setAttribute('download', saved[saved.length - 1]); cp.removeAttribute('aria-disabled'); }
    else { cp.addEventListener('click', e => { e.preventDefault(); }); cp.title = 'A copy is saved when a run finishes'; }
    $('#rptPrint').onclick = () => window.print();
    $('#rptSvg').onclick = () => OptimusReport.exportAll();
    $('#rptShowSrc').onchange = e => { $('#rptRoot').classList.toggle('show-src', e.target.checked); $('#rptLegend').hidden = !e.target.checked; };
    // contents panel with page numbers; the current chapter is highlighted while scrolling
    const wraps = Array.from(document.querySelectorAll('#pages .wrap')), ol = $('#rptOutline');
    ol.innerHTML = info.toc.map(t => `<li class="${t.sub ? 'sub' : ''}"><a href="#" data-pg="${t.page}"><span>${esc(t.title)}</span><span class="pg">${t.page}</span></a></li>`).join('');
    ol.querySelectorAll('a').forEach(a => a.addEventListener('click', e => { e.preventDefault(); wraps[+a.dataset.pg - 1].scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
    if (REP.io) REP.io.disconnect();
    const links = Array.from(ol.querySelectorAll('a'));
    REP.io = new IntersectionObserver(es => es.forEach(en => { if (!en.isIntersecting) return; const p = wraps.indexOf(en.target) + 1; let cur = null; links.forEach(l => { if (+l.dataset.pg <= p) cur = l; }); links.forEach(l => l.classList.toggle('on', l === cur)); }), { rootMargin: '-40% 0px -55% 0px' });
    wraps.forEach(w => REP.io.observe(w));
  } catch (e) {
    if ($('#pages')) $('#pages').innerHTML = `<div class="rpt-empty">Could not build the report: ${esc(String(e))}</div>`;
  }
}
async function tick() {
  await loadProgress();
  const n = ((S.P || {}).experiment || {}).runs ? S.P.experiment.runs.length : 0;
  const before = S.rkey;
  // results are re-read when a run finishes, when the experiment log changes, and at least every 15 s
  const logKey = ((S.P || {}).experiment || {}).log + '|' + (((S.P || {}).campaign || {}).finished ? 'f' : '');
  if (!S.R || n !== S.lastRuns || logKey !== S.lastLog || Date.now() - (S.lastLoad || 0) > 15000) {
    S.lastRuns = n; S.lastLog = logKey; S.lastLoad = Date.now(); await loadResults();
  }
  // live pages refresh every tick; result pages only when the results changed (so reading is not interrupted)
  const live = S.page === 'overview' || S.page === 'health' || !S.rendered;
  const typing = document.activeElement && document.activeElement.tagName === 'SELECT';
  if ((live || S.rkey !== before) && !typing && !$('#modal').classList.contains('open')) { render(); S.rendered = true; }
}
if (STATIC) { const f = document.querySelector('#nav .foot'); if (f) f.innerHTML = `Published snapshot of the result files, built ${esc(STATIC.built)}. Nothing here runs a test.`; }
tick(); if (!STATIC) setInterval(tick, 5000);
