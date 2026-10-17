/* OptimusDB Benchmark Observatory - interactive testbed architecture (window.ArchDiagram). No external libraries.
   ArchDiagram.mount(el) draws the diagram into el; the state (system, scenario, selection) survives re-renders. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* ------------------------------------------------------------ testbed facts (tools/gen_local.py, fresh-start.ps1, faults.py) */
  const SYS = {
    optimusdb: { n: 'OptimusDB', port: 8089, slot: 1, type: 'Document store on OrbitDB/IPFS, with an embedded SQLite copy for queries', rep: 'IPFS pubsub head announcements, periodic heads announcer', q: 'On the node (document query or SQL)' },
    corrosion: { n: 'Corrosion', port: 8080, slot: 2, type: 'Replicated SQL store: SQLite with CRDT tables (cr-sqlite)', rep: 'Gossip', q: 'On the node (SQL)' },
    gun: { n: 'Gun.js', port: 7004, slot: 3, type: 'Graph store with a per-property CRDT', rep: 'Peer relay over WebSocket', q: 'In the wrapper (client-side filter)' },
    autobase: { n: 'Autobase', port: 7005, slot: 4, type: 'Multi-writer append-only log (Hypercore) with a Hyperbee view', rep: 'Hyperswarm', q: 'In the wrapper (range scan + filter)' },
    iroh: { n: 'Iroh docs', port: 7006, slot: 5, type: 'Key-value document replicas; values are content-addressed blobs', rep: 'Range-based set reconciliation', q: 'In the wrapper (prefix scan + filter)' },
    opendht: { n: 'OpenDHT', port: 8000, slot: 6, type: 'Distributed hash table (Kademlia), key-value', rep: 'Each key stored on the closest nodes', q: 'None: lookups by key only' },
  };
  const ORDER = ['optimusdb', 'corrosion', 'gun', 'autobase', 'iroh', 'opendht'];
  const TIER = {
    cloud: { x: 40, n: 'Cloud tier', sub: '5 ms ± 1 ms · 0 % loss · 1 Gbit/s', drop: 200, range: '.11–.12', cpu: '1.5 CPU', mem: '3 GB', link: 'cc',
      role: 'Data-centre class hosts. Entry point of the client load in E1–E3 (cloud-a).' },
    fog: { x: 440, n: 'Fog tier', sub: '2 ms ± 0.5 ms · 0 % loss · 1 Gbit/s (derived)', drop: 600, range: '.13–.14', cpu: '1.5 CPU', mem: '3 GB', link: 'ff',
      role: 'Regional site between cloud and edge; both fog hosts share it.' },
    edge: { x: 840, n: 'Edge tier', sub: '2 ms ± 0.5 ms · 0 % loss · 100 Mbit/s', drop: 1000, range: '.15–.18', cpu: '1 CPU', mem: '2 GB', link: 'ee',
      role: 'Constrained devices. E4 measures the resource cost on edge-a.' },
  };
  const TY = 100, TH = 230, TW = 320, HW = 124, HH = 66;
  const HOSTS = [
    ['cloud-a', 'cloud', 11, 56, 192], ['cloud-b', 'cloud', 12, 220, 192],
    ['fog-a', 'fog', 13, 456, 192], ['fog-b', 'fog', 14, 620, 192],
    ['edge-a', 'edge', 15, 856, 158], ['edge-b', 'edge', 16, 1020, 158], ['edge-c', 'edge', 17, 856, 248], ['edge-d', 'edge', 18, 1020, 248],
  ].map(([id, tier, o, x, y], i) => ({ id, tier, ip: '10.88.0.' + o, x, y, i, cx: x + HW / 2, cy: y + HH / 2 }));
  const H = Object.fromEntries(HOSTS.map(h => [h.id, h]));
  const PROF = {
    cc: { n: 'cloud ↔ cloud', d: 5, j: 1, l: 0, r: '1 Gbit/s' },
    ff: { n: 'fog ↔ fog', d: 2, j: 0.5, l: 0, r: '1 Gbit/s', der: 'Derived: the fog hosts share one regional site.' },
    ee: { n: 'edge ↔ edge', d: 2, j: 0.5, l: 0, r: '100 Mbit/s' },
    cf: { n: 'cloud ↔ fog', d: 20, j: 4, l: 0.1, r: '100 Mbit/s' },
    fe: { n: 'fog ↔ edge', d: 50, j: 10, l: 0.5, r: '10 Mbit/s' },
    ce: { n: 'cloud ↔ edge', d: 70, j: 11, l: 0.6, r: '10 Mbit/s', der: 'Derived: cloud–edge traffic crosses the fog link (20 + 50 ms; √(4² + 10²) ≈ 11 ms jitter; losses compound to 0.6 %; the slower rate).' },
  };
  const ARC = 'M200,100 V72 Q200,62 210,62 H990 Q1000,62 1000,72 V100';
  // links drawn on the canvas: [id, profile, path, label x, label y]
  const LINKS = [
    ['l-cc', 'cc', 'M180,225 H220', null],
    ['l-ff', 'ff', 'M580,225 H620', null],
    ['l-ee1', 'ee', 'M980,191 H1020', null], ['l-ee2', 'ee', 'M980,281 H1020', null],
    ['l-ee3', 'ee', 'M918,224 V248', null], ['l-ee4', 'ee', 'M1082,224 V248', null],
    ['l-cf', 'cf', 'M344,225 H456', 400, 214],
    ['l-fe', 'fe', 'M744,225 H796 Q800,225 800,221 V195 Q800,191 804,191 H856 M800,229 V277 Q800,281 804,281 H856', 800, 150],
    ['l-ce', 'ce', ARC, 600, 54],
  ];
  // host-to-host routes used by the replication animation (centre to centre, drawn under the host cards)
  const via = (a, b) => {
    const A = H[a], B = H[b], ta = A.tier, tb = B.tier;
    if (ta === tb) return { p: `M${A.cx},${A.cy} L${B.cx},${B.cy}`, prof: TIER[ta].link };
    const key = [ta, tb].sort().join();
    if (key === 'cloud,fog') return { p: `M${A.cx},${A.cy} L${B.cx},${B.cy}`, prof: 'cf' };
    if (key === 'edge,fog') { const f = ta === 'fog' ? A : B, e = ta === 'fog' ? B : A; const p = `M${f.cx},${f.cy} H800 V${e.cy} H${e.cx}`; return { p, prof: 'fe', rev: ta !== 'fog' }; }
    const c = ta === 'cloud' ? A : B, e = ta === 'cloud' ? B : A;      // cloud-edge: over the derived arc
    return { p: `M${c.cx},${c.y} V${c.y - 20} L200,100 ${ARC.slice(9)} L${e.cx},${e.y}`, prof: 'ce', rev: ta !== 'cloud' };
  };
  const BUS = 430, BENCH = { x: 40, y: 486, w: 290, h: 100 };
  const toHost = h => `M185,${BENCH.y} V${BUS + 13} H${TIER[h.tier].drop} V${TY + TH} L${h.cx},${h.cy}`;
  const SPLIT = { '4|4': { x: 800, ax: 800, a: 'cloud + fog', b: 'edge', side: h => h.i < 4 ? 'A' : 'B' },
                  '2|6': { x: 400, ax: 400, a: 'cloud', b: 'fog + edge', side: h => h.i < 2 ? 'A' : 'B' } };
  const MODES = {
    overview: { n: 'Overview', t: 'The whole testbed at rest: requests from the benchmark container reach the entry host, and the data store replicates between hosts over the emulated links.' },
    load: { n: 'Client load', t: 'An open-loop Poisson generator in <b>bench</b> issues requests to the entry host. Traffic between bench and the hosts is <b>not shaped</b>, so the measured latency is the data store’s own, including the replication it waits for.' },
    repl: { n: 'Replication', t: 'Hosts exchange updates over the emulated links. Every packet leaving a host passes the netem class of its destination tier, so each pair of tiers sees its own delay, jitter, loss and rate (one-way, on egress). Animation speed follows the configured delay; not to scale.' },
    part: { n: 'Partition (E5)', t: 'iptables DROP rules split the hosts into two groups for 5–300 s while writers keep running on every host. Bench is never blocked, so both sides stay observable. After healing, the harness checks for lost acknowledged writes, identical replicas and the time to converge.' },
  };
  const ENTRY = { e13: { n: 'cloud-a · E1–E3', hosts: ['cloud-a'] }, e4: { n: 'edge-a · E4', hosts: ['edge-a'] }, e5: { n: 'every host · E5 writers', hosts: HOSTS.map(h => h.id) } };

  const A = window.ArchDiagram = { state: { sys: 'optimusdb', mode: 'overview', split: '4|4', entry: 'e13', sel: null, paused: false }, raf: 0 };
  const reduce = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const scol = s => `var(--s${SYS[s].slot})`;

  /* ------------------------------------------------------------ static drawing */
  function svg() {
    const st = A.state, sp = SPLIT[st.split], part = st.mode === 'part', sys = SYS[st.sys], c = scol(st.sys);
    let o = `<svg viewBox="0 0 1200 660" role="img" aria-label="Testbed architecture: 8 emulated hosts in cloud, fog and edge tiers on one Docker bridge network, with a benchmark container">
    <defs>
      <filter id="agGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <pattern id="agDots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" class="ag-dot"/></pattern>
      <linearGradient id="agBus" x1="0" x2="1"><stop offset="0" class="ag-bus0"/><stop offset=".5" class="ag-bus1"/><stop offset="1" class="ag-bus0"/></linearGradient>
    </defs>
    <rect x="12" y="12" width="1176" height="636" rx="16" class="ag-frame"/><rect x="12" y="12" width="1176" height="636" rx="16" fill="url(#agDots)" opacity=".7"/>
    <text x="34" y="40" class="ag-title">Single Windows host · Docker Desktop (WSL2 VM)</text>
    <text x="1166" y="40" text-anchor="end" class="ag-kicker">${esc(MODES[st.mode].n.toUpperCase())}${part ? ' · SPLIT ' + st.split : st.mode === 'load' ? ' · ' + esc(ENTRY[st.entry].n.toUpperCase()) : ''}</text>`;
    // tiers
    for (const [k, t] of Object.entries(TIER)) {
      o += `<g class="ag-tier${st.sel === 'tier:' + k ? ' sel' : ''}" data-ag="tier:${k}"><rect x="${t.x}" y="${TY}" width="${TW}" height="${TH}" rx="12"/>
        <text x="${t.x + 16}" y="${TY + 24}" class="ag-tn">${t.n}</text><text x="${t.x + 16}" y="${TY + 41}" class="ag-ts">${esc(t.sub)}</text></g>`;
    }
    // links (visible + fat hit area)
    for (const [id, p, d, lx, ly] of LINKS) {
      const pr = PROF[p], crosses = part && ((st.split === '4|4' && (p === 'fe' || p === 'ce')) || (st.split === '2|6' && (p === 'cf' || p === 'ce')));
      o += `<g class="ag-link${pr.der ? ' der' : ''}${crosses ? ' cut' : ''}${st.sel === 'link:' + p ? ' sel' : ''}" data-ag="link:${p}">
        <path d="${d}" class="ag-lv"/><path d="${d}" class="ag-lflow"/><path d="${d}" class="ag-lhit"/>
        ${lx != null ? `<g class="ag-lbl" transform="translate(${lx},${ly})"><rect x="-${p === 'ce' ? 168 : 30}" y="-10" width="${p === 'ce' ? 336 : 60}" height="18" rx="9"/><text y="3" text-anchor="middle">${p === 'ce' ? 'cloud–edge (derived) · 70 ms ± 11 ms · 0.6 % · 10 Mbit/s' : pr.d + ' ms'}</text></g>` : ''}</g>`;
    }
    o += `<g id="agRoutes" style="visibility:hidden" fill="none"></g><g id="agPk"></g>`;
    // hosts
    for (const h of HOSTS) {
      const side = part ? sp.side(h) : '';
      o += `<g class="ag-host${st.sel === 'host:' + h.id ? ' sel' : ''}${side ? ' side' + side : ''}" data-ag="host:${h.id}" tabindex="0" role="button" aria-label="${h.id}, ${h.ip}">
        <rect x="${h.x}" y="${h.y}" width="${HW}" height="${HH}" rx="10" class="ag-hb"/>
        <text x="${h.x + 12}" y="${h.y + 21}" class="ag-hn">${h.id}</text><text x="${h.x + 12}" y="${h.y + 36}" class="ag-hip">${h.ip}</text>
        <g transform="translate(${h.x + 10},${h.y + 43})"><rect width="${HW - 20}" height="16" rx="8" class="ag-pill" style="--c:${c}"/><circle cx="9" cy="8" r="3.2" fill="${c}"/><text x="17" y="11.5" class="ag-pt">${esc(sys.n)} :${sys.port}</text></g>
        <circle cx="${h.x + HW - 14}" cy="${h.y + 15}" r="4.5" class="ag-led" fill="${c}" id="agLed-${h.id}"/>
        ${st.mode === 'load' && st.entry !== 'e5' && ENTRY[st.entry].hosts.includes(h.id) ? `<g class="ag-entry" transform="translate(${h.cx},${h.y - 9})"><rect x="-38" y="-9" width="76" height="16" rx="8" style="fill:${c}"/><text y="3" text-anchor="middle">ENTRY HOST</text></g>` : ''}
        ${side ? `<text x="${h.x + HW - 28}" y="${h.y + 19}" text-anchor="end" class="ag-side">${side}</text>` : ''}</g>`;
    }
    // partition wall
    if (part) {
      let z = `M${sp.x},74`; for (let y = 74; y < 340; y += 14) z += ` L${sp.x + (((y - 74) / 14) % 2 ? -5 : 5)},${y + 14}`;
      o += `<g class="ag-wall"><path d="${z}"/><path d="M${sp.ax - 7},55 l14,14 m0,-14 l-14,14"/>
        <g transform="translate(${sp.x},352)"><rect x="-74" y="-12" width="148" height="22" rx="11"/><text y="4" text-anchor="middle">iptables DROP · ${st.split}</text></g>
        <text x="${sp.x - 14}" y="${TY + TH + 54}" text-anchor="end" class="ag-sidelbl">A · ${sp.a}</text><text x="${sp.x + 14}" y="${TY + TH + 54}" class="ag-sidelbl">B · ${sp.b}</text></g>`;
    }
    // bridge, drops, bench
    o += `<g class="ag-busg" data-ag="bus"><rect x="40" y="${BUS}" width="1120" height="26" rx="8" class="ag-bus"/><text x="600" y="${BUS + 17}" text-anchor="middle" class="ag-bt">Docker bridge network <tspan font-style="italic">odbnet</tspan> · 10.88.0.0/24</text></g>`;
    for (const t of Object.values(TIER)) o += `<line x1="${t.drop}" x2="${t.drop}" y1="${TY + TH}" y2="${BUS}" class="ag-drop"/><text x="${t.drop + 8}" y="${TY + TH + 24}" class="ag-ts">${t.range}</text>`;
    o += `<line x1="185" x2="185" y1="${BUS + 26}" y2="${BENCH.y}" class="ag-drop"/>
      <g class="ag-bench${st.sel === 'bench' ? ' sel' : ''}" data-ag="bench" tabindex="0" role="button" aria-label="bench, 10.88.0.2"><rect x="${BENCH.x}" y="${BENCH.y}" width="${BENCH.w}" height="${BENCH.h}" rx="12"/>
        <text x="${BENCH.x + 16}" y="${BENCH.y + 26}" class="ag-hn">bench <tspan class="ag-hip">10.88.0.2</tspan></text>
        <text x="${BENCH.x + 16}" y="${BENCH.y + 46}" class="ag-ts">load generator (4 worker processes)</text>
        <text x="${BENCH.x + 16}" y="${BENCH.y + 62}" class="ag-ts">cluster control · netem · partitions</text>
        <text x="${BENCH.x + 16}" y="${BENCH.y + 78}" class="ag-ts">result files → this dashboard</text></g>`;
    // inside a host
    const h = st.sel && st.sel.startsWith('host:') ? H[st.sel.slice(5)] : null, t = TIER[h ? h.tier : 'cloud'];
    const IX = 360, IY = 476;
    o += `<g class="ag-inside"><rect x="${IX}" y="${IY}" width="800" height="160" rx="12" class="ag-ib"/>
      <text x="${IX + 18}" y="${IY + 24}" class="ag-tn">${h ? `Inside ${h.id} <tspan class="ag-hip">${h.ip}</tspan>` : 'Inside each emulated host'} <tspan class="ag-ts">· one network namespace, one IP</tspan></text>
      <g class="ag-box"><rect x="${IX + 18}" y="${IY + 40}" width="170" height="74" rx="8"/><text x="${IX + 103}" y="${IY + 62}" text-anchor="middle" class="ag-hn">net</text>
        <text x="${IX + 103}" y="${IY + 80}" text-anchor="middle" class="ag-ts">eth0 · host IP</text><text x="${IX + 103}" y="${IY + 96}" text-anchor="middle" class="ag-ts">tc netem · iptables</text></g>
      <g class="ag-box"><rect x="${IX + 200}" y="${IY + 40}" width="150" height="74" rx="8"/><text x="${IX + 275}" y="${IY + 62}" text-anchor="middle" class="ag-hn">agent :9100</text>
        <text x="${IX + 275}" y="${IY + 80}" text-anchor="middle" class="ag-ts">start · stop · wipe</text><text x="${IX + 275}" y="${IY + 96}" text-anchor="middle" class="ag-ts">resource stats</text></g>
      <rect x="${IX + 364}" y="${IY + 34}" width="420" height="86" rx="10" class="ag-dash"/><text x="${IX + 374}" y="${IY + 48}" class="ag-tiny">data-store containers · only the system under test runs</text>`;
    ORDER.forEach((s, k) => {
      const x = IX + 370 + k * 69, on = s === st.sys;
      o += `<g class="ag-ds${on ? ' on' : ''}" data-ag="sys:${s}" style="--c:${scol(s)}"><rect x="${x}" y="${IY + 56}" width="64" height="56" rx="8"/>
        <text x="${x + 32}" y="${IY + 80}" text-anchor="middle">${SYS[s].n}</text><text x="${x + 32}" y="${IY + 97}" text-anchor="middle" class="ag-port">:${SYS[s].port}</text></g>`;
    });
    o += `<text x="${IX + 18}" y="${IY + 137}" class="ag-ts">${h ? `Limit per data store on this ${h.tier} host: ${t.cpu} · ${t.mem}.` : 'Limit per data store: cloud and fog 1.5 CPU / 3 GB · edge 1 CPU / 2 GB.'}</text>
      <text x="${IX + 18}" y="${IY + 153}" class="ag-ts">E5 partitions: iptables DROP between host groups (bench never blocked).</text></g>`;
    return o + '</svg>';
  }

  /* ------------------------------------------------------------ side panel */
  const row = (k, v) => `<div class="ag-kv"><span>${k}</span><b>${v}</b></div>`;
  const profRows = p => row('one-way delay', `${p.d} ms ± ${p.j} ms`) + row('loss', `${p.l} %`) + row('rate', p.r);
  function panel() {
    const st = A.state, sel = st.sel || '', sys = SYS[st.sys];
    let head = '', body = '';
    if (sel.startsWith('host:')) {
      const h = H[sel.slice(5)], t = TIER[h.tier];
      head = `${h.id}<small>${h.tier} tier · ${h.ip}</small>`;
      body = `<p>${t.role}</p>${row('data store', `${sys.n} :${sys.port}`)}${row('limits', `${t.cpu} · ${t.mem}`)}${row('host agent', ':9100')}
        <h5>Links from this host</h5>` + Object.keys(TIER).map(k => {
          const p = PROF[k === h.tier ? t.link : ({ 'cloud,fog': 'cf', 'edge,fog': 'fe', 'cloud,edge': 'ce' })[[h.tier, k].sort().join()]];
          return row(`to ${k}`, `${p.d} ms · ${p.l} % · ${p.r}`);
        }).join('') + (st.mode === 'part' ? `<p class="ag-note">In split ${st.split} this host is on side <b>${SPLIT[st.split].side(h)}</b>.</p>` : '');
    } else if (sel.startsWith('link:')) {
      const p = PROF[sel.slice(5)];
      head = `${p.n}<small>emulated link · tc netem</small>`;
      body = profRows(p) + `<p>Applied on the egress of every host in one tier towards every host of the other: an htb class with a netem qdisc per destination tier, selected by u32 filters on the destination IP. Values are one-way, so a round trip pays twice.</p>${p.der ? `<p class="ag-note">${p.der}</p>` : ''}`;
    } else if (sel.startsWith('tier:')) {
      const k = sel.slice(5), t = TIER[k];
      head = `${t.n}<small>${HOSTS.filter(h => h.tier === k).length} hosts · 10.88.0${t.range}</small>`;
      body = `<p>${t.role}</p>${row('within the tier', t.sub.replace(/ · /g, ' · '))}${row('limits per host', `${t.cpu} · ${t.mem}`)}`;
    } else if (sel === 'bench') {
      head = 'bench<small>10.88.0.2 · benchmark container</small>';
      body = `<p>Runs the harness: the open-loop Poisson load generator (4 worker processes on a shared monotonic clock), cluster control through the host agents, network emulation and partitions, and writes the result files this dashboard reads.</p>
        ${row('to the hosts', 'not shaped')}${row('during partitions', 'never blocked')}<p class="ag-note">Its own CPU is recorded for every run; a run counts as client-limited at ≥ 85 % of a core.</p>`;
    } else if (sel === 'bus') {
      head = 'odbnet<small>Docker bridge · 10.88.0.0/24</small>';
      body = `<p>One flat bridge connects all nine containers. The tiers exist only through the per-destination netem classes on each host, so changing the network profile needs no change to the topology.</p>`;
    } else {
      head = `${sys.n}<small>system under test · port ${sys.port}</small>`;
      body = row('data store type', sys.type) + row('replication', sys.rep) + row('queries', sys.q) +
        `<p class="ag-note">Click a host, a link, a tier, the bridge or bench for its details. Pick another data store in the bar above or inside the host panel.</p>`;
    }
    return `<div class="ag-pl"><div class="ag-ph">${head}</div><div class="ag-mode"><b>${MODES[st.mode].n}.</b> ${MODES[st.mode].t}</div></div><div class="ag-pr">${body}</div>`;
  }

  function controls() {
    const st = A.state;
    const seg = (key, opts) => `<div class="seg ag-seg">${Object.entries(opts).map(([k, v]) => `<button type="button" data-agset="${key}:${k}" class="${st[key] === k ? 'on' : ''}">${v}</button>`).join('')}</div>`;
    return `<div class="ag-ctl">
      <div class="ag-chips">${ORDER.map(s => `<button type="button" class="ag-chip${s === st.sys ? ' on' : ''}" data-agset="sys:${s}" style="--c:${scol(s)}"><i></i>${SYS[s].n}</button>`).join('')}</div>
      <div class="ag-row">${seg('mode', Object.fromEntries(Object.entries(MODES).map(([k, v]) => [k, v.n])))}
        ${st.mode === 'part' ? seg('split', { '4|4': 'split 4 | 4', '2|6': 'split 2 | 6' }) : ''}
        ${st.mode === 'load' ? seg('entry', Object.fromEntries(Object.entries(ENTRY).map(([k, v]) => [k, v.n]))) : ''}
        <span class="ag-sp"></span>
        <button type="button" class="abtn ghost ag-btn" data-agact="pause">${st.paused ? '▶ Play' : '❚❚ Pause'}</button>
        <button type="button" class="abtn ghost ag-btn" data-agact="full">⤢ Full screen</button></div></div>`;
  }

  /* ------------------------------------------------------------ animation */
  let pk = [], acc = {}, last = 0, root = null;
  function routeEl(d) { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); root.querySelector('#agRoutes').appendChild(p); return p; }
  function cutAt(p, x) {          // length along p where it first crosses the vertical line at x, or null
    const L = p.getTotalLength(); let prev = p.getPointAtLength(0);
    for (let s = 6; s <= L; s += 6) { const q = p.getPointAtLength(s); if ((prev.x - x) * (q.x - x) <= 0 && prev.x !== q.x && q.y < 345) return s; prev = q; }
    return null;
  }
  function spawn(d, opt) {
    const g = root.querySelector('#agPk'); if (!g) return;
    const p = routeEl(d), L = p.getTotalLength();
    const c = document.createElementNS(NS, 'circle'); c.setAttribute('r', opt.r || 3.6); c.setAttribute('class', 'ag-pk' + (opt.cls ? ' ' + opt.cls : ''));
    if (opt.color) c.style.fill = opt.color; c.setAttribute('filter', 'url(#agGlow)'); g.appendChild(c);
    let stop = null;
    if (opt.cutx != null) stop = cutAt(p, opt.cutx);
    pk.push({ p, c, L, t: 0, dur: opt.dur, rev: !!opt.rev, stop, then: opt.then, done: false });
  }
  function burst(x, y) {
    const g = root.querySelector('#agPk'); if (!g) return;
    const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', 3); c.setAttribute('class', 'ag-burst'); g.appendChild(c);
    pk.push({ burst: c, t: 0, dur: 0.6 });
  }
  const durOf = prof => 0.55 + PROF[prof].d * 0.032;
  function replicate(from, cut) {
    const others = HOSTS.filter(h => h.id !== from);
    const to = others[Math.floor(Math.random() * others.length)].id, r = via(from, to);
    spawn(r.p, { dur: durOf(r.prof), rev: r.rev, cls: 'repl', r: 3, cutx: cut });
  }
  function tick(now) {
    if (!root || !root.isConnected) { A.raf = 0; pk = []; return; }
    const dt = last ? Math.min((now - last) / 1000, 0.1) : 0; last = now;
    const st = A.state;
    if (!st.paused && !document.hidden && !reduce()) {
      const rate = (k, r, fn) => { acc[k] = (acc[k] || 0) + dt * r; while (acc[k] >= 1) { acc[k] -= 1; fn(); } };
      const sp = SPLIT[st.split], c = scol(st.sys);
      const entries = st.mode === 'load' ? ENTRY[st.entry].hosts : st.mode === 'part' ? HOSTS.map(h => h.id) : ['cloud-a'];
      const load = () => { const h = H[entries[Math.floor(Math.random() * entries.length)]];
        spawn(toHost(h), { dur: 1.1, color: c, then: () => { spawn(toHost(h), { dur: 1.1, rev: true, cls: 'resp', r: 2.6 }); if (Math.random() < (st.mode === 'load' ? 0.5 : 0.8)) replicate(h.id, st.mode === 'part' ? sp.x : null); } }); };
      if (st.mode === 'overview') { rate('l', 1.4, load); rate('r', 1.6, () => replicate(HOSTS[Math.floor(Math.random() * 8)].id)); }
      if (st.mode === 'load') rate('l', st.entry === 'e5' ? 4 : 3, load);
      if (st.mode === 'repl') rate('r', 5, () => replicate(HOSTS[Math.floor(Math.random() * 8)].id));
      if (st.mode === 'part') { rate('l', 1.5, load); rate('r', 4, () => replicate(HOSTS[Math.floor(Math.random() * 8)].id, sp.x)); }
      for (const q of pk) {
        q.t += dt / q.dur;
        if (q.burst) { if (q.t >= 1) { q.burst.remove(); q.done = true; } else { q.burst.setAttribute('r', 3 + q.t * 14); q.burst.style.opacity = 1 - q.t; } continue; }
        let s = (q.rev ? 1 - Math.min(q.t, 1) : Math.min(q.t, 1)) * q.L;
        const blocked = q.stop != null && (q.rev ? s <= q.stop : s >= q.stop);
        if (blocked) s = q.stop;
        const pt = q.p.getPointAtLength(s); q.c.setAttribute('cx', pt.x); q.c.setAttribute('cy', pt.y);
        if (blocked) { burst(pt.x, pt.y); q.c.remove(); q.p.remove(); q.done = true; continue; }
        if (q.t >= 1) { q.c.remove(); q.p.remove(); q.done = true; if (q.then) q.then(); }
      }
      pk = pk.filter(q => !q.done);
      HOSTS.forEach(h => { const e = root.querySelector('#agLed-' + h.id); if (e) e.style.opacity = 0.55 + 0.45 * Math.abs(Math.sin(now / 600 + h.i)); });
    }
    A.raf = requestAnimationFrame(tick);
  }

  /* ------------------------------------------------------------ mount + events */
  function draw() {
    root.querySelector('.ag-controls').innerHTML = controls();
    root.querySelector('.ag-canvas').innerHTML = svg();
    root.querySelector('.ag-panel').innerHTML = panel();
    root.style.setProperty('--c', scol(A.state.sys));
    root.classList.toggle('ag-motion-off', A.state.paused || reduce());
    pk = []; acc = {};
  }
  function tip(e, show) {
    const t = root.querySelector('.ag-tip'); const g = e.target.closest && e.target.closest('[data-ag]');
    if (!show || !g) { t.classList.remove('on'); return; }
    const [k, v] = g.dataset.ag.split(':'); let s = '';
    if (k === 'link') { const p = PROF[v]; s = `<b>${p.n}</b><br>${p.d} ms ± ${p.j} ms · ${p.l} % loss · ${p.r}${p.der ? '<br><i>derived</i>' : ''}`; }
    else if (k === 'host') { const h = H[v]; s = `<b>${h.id}</b> · ${h.ip}<br>${SYS[A.state.sys].n} :${SYS[A.state.sys].port} · ${TIER[h.tier].cpu} · ${TIER[h.tier].mem}`; }
    else if (k === 'tier') s = `<b>${TIER[v].n}</b><br>${esc(TIER[v].sub)}`;
    else if (k === 'sys') s = `<b>${SYS[v].n}</b> :${SYS[v].port}<br>${esc(SYS[v].type)}`;
    else if (k === 'bench') s = '<b>bench</b> · 10.88.0.2<br>load generator · not shaped';
    else if (k === 'bus') s = '<b>odbnet</b> · Docker bridge 10.88.0.0/24';
    t.innerHTML = s; t.classList.add('on');
    const r = t.parentElement.getBoundingClientRect(); let x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
    if (x + 260 > r.width) x = e.clientX - r.left - 270;
    t.style.left = x + 'px'; t.style.top = y + 'px';
  }
  A.mount = function (el) {
    if (!el) return;
    if (A.raf) cancelAnimationFrame(A.raf);
    root = el; last = 0;
    el.style.setProperty('--c', scol(A.state.sys));
    el.innerHTML = `<div class="ag-controls"></div><div class="ag-grid"><div class="ag-stage"><div class="ag-canvas"></div><div class="ag-tip"></div></div><aside class="ag-panel" aria-live="polite"></aside></div>
      <div class="ag-legend"><span><i class="lg-solid"></i>attachment to the bridge (not shaped)</span><span><i class="lg-link"></i>emulated link (tc netem, one-way)</span><span><i class="lg-der"></i>derived link</span><span><i class="lg-pk" style="background:var(--c);box-shadow:0 0 6px var(--c)"></i>request (colour of the data store)</span><span><i class="lg-resp"></i>response</span><span><i class="lg-repl"></i>replication</span><span><i class="lg-cut"></i>partition (iptables DROP)</span></div>`;
    draw();
    el.addEventListener('click', e => {
      const s = e.target.closest('[data-agset]');
      if (s) { const [k, v] = s.dataset.agset.split(':'); A.state[k] = v; draw(); return; }
      const a = e.target.closest('[data-agact]');
      if (a) { if (a.dataset.agact === 'pause') { A.state.paused = !A.state.paused; draw(); }
               else { const f = el.closest('.card') || el; document.fullscreenElement ? document.exitFullscreen() : f.requestFullscreen && f.requestFullscreen(); } return; }
      const g = e.target.closest('[data-ag]');
      if (g) { const v = g.dataset.ag; if (v.startsWith('sys:')) A.state.sys = v.slice(4); else A.state.sel = A.state.sel === v ? null : v; draw(); }
      else if (e.target.closest('.ag-canvas')) { A.state.sel = null; draw(); }
    });
    el.addEventListener('keydown', e => { const g = e.target.closest('[data-ag]'); if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); g.dispatchEvent(new MouseEvent('click', { bubbles: true })); } });
    el.addEventListener('mousemove', e => tip(e, true));
    el.addEventListener('mouseleave', e => tip(e, false));
    A.raf = requestAnimationFrame(tick);
  };
})();
