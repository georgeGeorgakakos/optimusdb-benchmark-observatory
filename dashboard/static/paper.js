/* Paper export: every figure of the selected run in a form ready for the manuscript.
   Figures come from the evaluation report's builders (report/report.js) plus the summary figure (summary-fig.js),
   so the numbers are the report's. Per figure: SVG (vector), PNG at 300 dpi for the chosen column width, CSV of the
   plotted values. "Download all" packs them with the captions, LaTeX tables (booktabs) and a README into one ZIP
   (written here, no library). "Print figures" opens one figure per page for a vector PDF. */
'use strict';
window.PaperExport = (function () {
  const SYS = ['optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht'];
  const LBL = { optimusdb: 'OptimusDB', corrosion: 'Corrosion', gun: 'Gun.js', autobase: 'Autobase', iroh: 'Iroh docs', opendht: 'OpenDHT' };
  const FONTS = { sans: 'Helvetica, Arial, sans-serif', serif: '"Times New Roman", Times, serif', system: 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif' };
  const WIDTHS = { double: { in: 7.16, label: 'Double column (7.16 in)' }, single: { in: 3.5, label: 'Single column (3.5 in)' }, full: { in: 6.3, label: 'Full text width (16 cm)' } };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const st = { data: null, mode: null, figs: [], font: 'sans', width: 'double' };
  try { st.font = localStorage.getItem('odb.paper.font') || 'sans'; st.width = localStorage.getItem('odb.paper.width') || 'double'; } catch (e) { /* private window */ }

  const tag = () => `optimusdb-${(st.data.meta.archive || st.data.kind)}`;
  const fname = f => `fig${String(f.n).padStart(2, '0')}-${f.id}`;
  /* physical size: width attribute in inches, height in proportion (viewBox unchanged) */
  function sized(svg) {
    const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg); if (!m) return svg;
    const wi = WIDTHS[st.width].in, hi = wi * (+m[2]) / (+m[1]);
    return svg.replace(/<svg([^>]*?) width="[^"]*" height="[^"]*"/, `<svg$1 width="${wi}in" height="${hi.toFixed(3)}in"`);
  }
  function png(svg) {
    return new Promise((ok, bad) => {
      const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg), w = +m[1], h = +m[2], px = Math.round(WIDTHS[st.width].in * 300), k = px / w;
      const img = new Image();
      img.onload = () => { const c = document.createElement('canvas'); c.width = px; c.height = Math.round(h * k); const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
        c.toBlob(b => b ? b.arrayBuffer().then(a => ok(new Uint8Array(a))) : bad(new Error('PNG failed')), 'image/png'); };
      img.onerror = () => bad(new Error('SVG could not be drawn'));
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg.replace(/ width="[\d.]+in" height="[\d.]+in"/, ` width="${w}" height="${h}"`));
    });
  }
  const csvText = rows => rows.map(r => r.map(v => v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v).join(',')).join('\n') + '\n';

  /* ------------------------------------------------------------------ LaTeX tables (booktabs) */
  const tex = s => String(s ?? '').replace(/([&%$#_{}])/g, '\\$1').replace(/~/g, '\\textasciitilde{}').replace(/×/g, '$\\times$').replace(/≥/g, '$\\geq$').replace(/–/g, '--').replace(/⁴/g, '$^4$').replace(/⁵/g, '$^5$').replace(/⁶/g, '$^6$').replace(/³/g, '$^3$');
  const num = (v, d) => v == null || isNaN(v) ? '--' : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US').replace(/,/g, '{,}') : (+v).toFixed(d != null ? d : Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
  function latex() {
    const D = st.data, out = [`% OptimusDB evaluation, ${D.meta.label}, build ${(D.meta.commit || '').slice(0, 7)}, generated ${D.meta.generated}`,
      `% Requires \\usepackage{booktabs}. One repetition per cell is indicative only.`, ''];
    const e1 = D.E1 || [];
    if (e1.length) {
      const wls = ['WA', 'WB', 'WC', 'WO'].filter(w => e1.some(c => c.workload === w && c.doc_size === '2KB'));
      out.push('\\begin{table}[t]\\centering\\small', `\\caption{E1: latency in ms at 50 ops/s, 2\\,KB documents (P50 / P99 / P99.9${D.max_reps > 1 ? ', medians over repetitions' : ''}).}`, '\\label{tab:e1}',
        `\\begin{tabular}{l${'r'.repeat(wls.length)}}`, '\\toprule', `System & ${wls.join(' & ')} \\\\`, '\\midrule');
      SYS.filter(s => e1.some(c => c.system === s)).forEach(s => out.push(`${s === 'optimusdb' ? '\\textbf{OptimusDB}' : LBL[s]} & ${wls.map(w => { const c = e1.find(x => x.system === s && x.workload === w && x.doc_size === '2KB'); return c && c.p99 != null ? `${num(c.p50)} / ${num(c.p99)} / ${num(c.p999)}` : '--'; }).join(' & ')} \\\\`));
      out.push('\\bottomrule', '\\end{tabular}', '\\end{table}', '');
    }
    const e3 = D.E3 || [];
    if (e3.length) {
      const n = Math.max(...e3.map(c => c.records || 0)), qs = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'].filter(q => e3.some(c => c.query === q && c.records === n));
      const targets = [...new Map(e3.filter(c => c.records === n).map(c => [c.system + '|' + c.path, 1])).keys()].sort((a, b) => SYS.indexOf(a.split('|')[0]) - SYS.indexOf(b.split('|')[0]));
      out.push('\\begin{table}[t]\\centering\\small', `\\caption{E3: mean query time in ms at ${tex(n.toLocaleString('en-US'))} records; $\\times$ = wrong or incomplete answer, n/s = not supported.}`, '\\label{tab:e3}',
        `\\begin{tabular}{ll${'r'.repeat(qs.length)}}`, '\\toprule', `System & Path & ${qs.join(' & ')} \\\\`, '\\midrule');
      targets.forEach(t => { const [s, p] = t.split('|'); out.push(`${s === 'optimusdb' ? '\\textbf{OptimusDB}' : LBL[s]} & \\texttt{${tex(p)}} & ${qs.map(q => { const c = e3.find(x => x.system === s && x.path === p && x.query === q && x.records === n);
        if (!c) return ''; if (c.unsupported) return 'n/s'; if (c.failed || c.mean == null) return 'failed'; return ((c.correct || 0) >= 0.5 ? '' : '$\\times$\\,') + num(c.mean); }).join(' & ')} \\\\`); });
      out.push('\\bottomrule', '\\end{tabular}', '\\end{table}', '');
    }
    const e4 = D.E4 || [];
    if (e4.length) {
      const lv = [...new Set(e4.map(c => c.offered))].sort((a, b) => a - b);
      out.push('\\begin{table}[t]\\centering\\small', '\\caption{E4: CPU (\\% of one core) and resident memory (MB) on an edge host.}', '\\label{tab:e4}',
        `\\begin{tabular}{l${'rr'.repeat(lv.length)}}`, '\\toprule', `& ${lv.map(l => `\\multicolumn{2}{c}{${num(l, 0)} ops/s}`).join(' & ')} \\\\`, `System & ${lv.map(() => 'CPU & MB').join(' & ')} \\\\`, '\\midrule');
      SYS.filter(s => e4.some(c => c.system === s)).forEach(s => out.push(`${s === 'optimusdb' ? '\\textbf{OptimusDB}' : LBL[s]} & ${lv.map(l => { const c = e4.find(x => x.system === s && x.offered === l); return c ? `${num(c.cpu)} & ${num(c.rss, 0)}` : '-- & --'; }).join(' & ')} \\\\`));
      out.push('\\bottomrule', '\\end{tabular}', '\\end{table}', '');
    }
    const e5 = D.E5 || [];
    if (e5.length) {
      out.push('\\begin{table}[t]\\centering\\small', '\\caption{E5: partition behaviour (contention, partition length, split); convergence in s.}', '\\label{tab:e5}',
        '\\begin{tabular}{llrrrl}', '\\toprule', 'System & Cell & Availability & Convergence & Lost & Identical \\\\', '\\midrule');
      [...e5].sort((a, b) => SYS.indexOf(a.system) - SYS.indexOf(b.system)).forEach(c => out.push(`${c.system === 'optimusdb' ? '\\textbf{OptimusDB}' : LBL[c.system]} & ${num(c.contention, 0)}\\,\\% · ${num(c.partition_s, 0)}\\,s · ${tex(c.shape)} & ${num(c.availability, 0)}\\,\\% & ${c.convergence == null ? '--' : num(c.convergence)} & ${c.lost ?? '--'} & ${(c.identical || 0) >= 1 ? 'yes' : 'no'} \\\\`.replace(/·/g, '/')));
      out.push('\\bottomrule', '\\end{tabular}', '\\end{table}', '');
    }
    const H = D.hypotheses || {};
    out.push('\\begin{table}[t]\\centering\\small', `\\caption{Hypotheses: indicative verdicts of this run (${tex(D.meta.label)}).}`, '\\label{tab:hyp}', '\\begin{tabular}{llp{0.62\\linewidth}}', '\\toprule', 'Id & Verdict & Evidence \\\\', '\\midrule');
    ['H1', 'H2', 'H3', 'H4', 'H5'].forEach(h => { const x = H[h] || {}; out.push(`${h} & ${x.state === 'supported' ? 'supported' : x.state === 'not_supported' ? 'not supported' : 'insufficient data'} & ${tex(x.text || '')} \\\\`); });
    out.push('\\bottomrule', '\\end{tabular}', '\\end{table}', '');
    return out.join('\n');
  }

  /* ------------------------------------------------------------------ ZIP (store, no compression) */
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = b => { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  function zip(files) {   // files: [{name, data: Uint8Array}]
    const enc = new TextEncoder(), parts = [], cen = []; let off = 0;
    const d = new Date(), dt = ((d.getFullYear() - 1980) << 25) | ((d.getMonth() + 1) << 21) | (d.getDate() << 16) | (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
    files.forEach(f => {
      const nm = enc.encode(f.name), c = crc32(f.data), h = new DataView(new ArrayBuffer(30));
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); h.setUint16(8, 0, true); h.setUint32(10, dt, true);
      h.setUint32(14, c, true); h.setUint32(18, f.data.length, true); h.setUint32(22, f.data.length, true); h.setUint16(26, nm.length, true);
      parts.push(new Uint8Array(h.buffer), nm, f.data);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true); ch.setUint32(12, dt, true);
      ch.setUint32(16, c, true); ch.setUint32(20, f.data.length, true); ch.setUint32(24, f.data.length, true); ch.setUint16(28, nm.length, true); ch.setUint32(42, off, true);
      cen.push(new Uint8Array(ch.buffer), nm); off += 30 + nm.length + f.data.length;
    });
    const csize = cen.reduce((a, x) => a + x.length, 0), e = new DataView(new ArrayBuffer(22));
    e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true); e.setUint32(12, csize, true); e.setUint32(16, off, true);
    return new Blob([...parts, ...cen, new Uint8Array(e.buffer)], { type: 'application/zip' });
  }
  function save(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); }

  /* ------------------------------------------------------------------ page */
  function page(srcLabel) {
    return `<div class="card"><div class="card-head"><div><h3>Figures for the manuscript</h3><div class="hint">Every figure of the run selected at the top (${esc(srcLabel)}), white background, sized for the column you choose. SVG is vector (convert to PDF or EPS if the journal asks); PNG is 300 dpi at that width. The numbers are the evaluation report's.</div></div></div>
      <div class="paper-opts"><label>Font <select id="ppFont">${Object.entries({ sans: 'Helvetica / Arial', serif: 'Times', system: 'Screen font (as the dashboard)' }).map(([k, v]) => `<option value="${k}" ${st.font === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>Width <select id="ppWidth">${Object.entries(WIDTHS).map(([k, v]) => `<option value="${k}" ${st.width === k ? 'selected' : ''}>${v.label}</option>`).join('')}</select></label>
        <span style="flex:1"></span><button class="btn" id="ppZip" type="button">Download all (ZIP)</button><button class="btn ghost" id="ppPrint" type="button">Print figures (one per page)</button></div>
      <div class="muted" id="ppStatus" style="font-size:12px;margin-top:8px">Loading…</div></div>
      <div class="paper-grid" id="ppGrid"></div>`;
  }
  async function load(mode, getJSON) {
    try {
      if (st.mode !== mode || !st.data) { st.data = await getJSON(`/api/report?mode=${encodeURIComponent(mode)}`); st.mode = mode; }
      draw();
    } catch (e) { const s = document.getElementById('ppStatus'); if (s) s.textContent = 'Could not load the run: ' + e; }
    const f = document.getElementById('ppFont'), w = document.getElementById('ppWidth');
    if (f) f.onchange = () => { st.font = f.value; try { localStorage.setItem('odb.paper.font', st.font); } catch (e) { /* */ } draw(); };
    if (w) w.onchange = () => { st.width = w.value; try { localStorage.setItem('odb.paper.width', st.width); } catch (e) { /* */ } draw(); };
    const z = document.getElementById('ppZip'); if (z) z.onclick = downloadAll;
    const p = document.getElementById('ppPrint'); if (p) p.onclick = printAll;
  }
  function draw() {
    const grid = document.getElementById('ppGrid'), status = document.getElementById('ppStatus'); if (!grid || !st.data) return;
    st.figs = window.OptimusReport.figures(st.data, { font: FONTS[st.font] });
    if (!st.figs.length) { grid.innerHTML = ''; status.textContent = 'No figures: this run has no results yet.'; return; }
    status.textContent = `${st.figs.length} figures · ${st.data.meta.label}${st.data.meta.commit ? ' · build ' + st.data.meta.commit.slice(0, 7) : ''}${st.data.max_reps > 1 ? '' : ' · one repetition per cell (indicative only)'} · ${WIDTHS[st.width].label}, ${Math.round(WIDTHS[st.width].in * 300)} px PNG`;
    grid.innerHTML = st.figs.map(f => `<div class="paper-fig" ${f.id === 'glance' ? 'style="grid-column:1/-1"' : ''}><div class="pf-h"><b>Figure ${f.n}. ${esc(f.title)}</b><span class="pf-x"><button data-pp="svg" data-n="${f.n}">SVG</button><button data-pp="png" data-n="${f.n}">PNG</button><button data-pp="csv" data-n="${f.n}">CSV</button></span></div>${f.svg}<div class="pf-c">${esc(f.caption)}</div></div>`).join('');
    grid.querySelectorAll('[data-pp]').forEach(b => b.onclick = async () => { const f = st.figs.find(x => x.n === +b.dataset.n);
      if (b.dataset.pp === 'svg') save(new Blob([sized(f.svg)], { type: 'image/svg+xml' }), `${tag()}-${fname(f)}.svg`);
      if (b.dataset.pp === 'csv') save(new Blob([csvText(f.csv)], { type: 'text/csv' }), `${tag()}-${fname(f)}.csv`);
      if (b.dataset.pp === 'png') save(new Blob([await png(f.svg)], { type: 'image/png' }), `${tag()}-${fname(f)}.png`); });
  }
  async function downloadAll() {
    const status = document.getElementById('ppStatus'), enc = new TextEncoder(), D = st.data, files = [];
    status.textContent = 'Preparing the ZIP…';
    try {
      for (const f of st.figs) {
        files.push({ name: `figures/${fname(f)}.svg`, data: enc.encode(sized(f.svg)) });
        files.push({ name: `figures/${fname(f)}.png`, data: await png(f.svg) });
        files.push({ name: `data/${fname(f)}.csv`, data: enc.encode(csvText(f.csv)) });
      }
      files.push({ name: 'captions.md', data: enc.encode(`# Figure captions\n\nRun: ${D.meta.label}${D.meta.commit ? ', build ' + D.meta.commit.slice(0, 7) : ''}; generated ${D.meta.generated}.\n\n` + st.figs.map(f => `**Figure ${f.n}. ${f.title}.** ${f.caption}\n`).join('\n')) });
      files.push({ name: 'tables.tex', data: enc.encode(latex()) });
      files.push({ name: 'README.txt', data: enc.encode([`OptimusDB evaluation: figures for the manuscript`, ``, `Run:        ${D.meta.label} (${D.meta.folder})`, `Build:      ${D.meta.commit || 'unknown'} ${D.meta.commit_msg || ''}`, `Generated:  ${D.meta.generated}`,
        `Repetitions per cell: up to ${D.max_reps || 1}${(D.max_reps || 1) > 1 ? '' : ' (indicative only; the paper uses the campaign)'}`, `Font: ${FONTS[st.font]}   Width: ${WIDTHS[st.width].label}   PNG: 300 dpi at that width`, ``,
        `figures/  SVG (vector) and PNG per figure`, `data/     the plotted values per figure (CSV)`, `captions.md  captions, numbered as in this export`, `tables.tex   LaTeX tables (booktabs): E1, E3, E4, E5, hypotheses`, ``,
        `Every value comes from the run's result files through the evaluation report; nothing is edited by hand.`].join('\n') + '\n') });
      save(zip(files), `${tag()}-paper-figures.zip`);
      status.textContent = `ZIP saved: ${st.figs.length} figures (SVG, PNG, CSV), captions, LaTeX tables.`;
    } catch (e) { status.textContent = 'Could not build the ZIP: ' + e; }
  }
  function printAll() {
    let host = document.getElementById('paperPrint'); if (!host) { host = document.createElement('div'); host.id = 'paperPrint'; document.body.appendChild(host); }
    host.innerHTML = st.figs.map(f => `<div class="pp">${f.svg}<div class="cap"><b>Figure ${f.n}.</b> ${esc(f.title)}. ${esc(f.caption)}</div></div>`).join('');
    document.body.classList.add('paper-printing');
    const done = () => { document.body.classList.remove('paper-printing'); window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done); window.print(); setTimeout(done, 60000);
  }
  return { page, load, latex: () => latex(), _zip: zip };
})();
