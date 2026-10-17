"""Build OptimusDB_Section8_Evidence.xlsx from bench/spec.py.

Raw sheets (<E>_raw) take one row per run from the harness CSVs.
Summary sheets (<E>_sum) compute mean, n, s.d. and 95% CI with Excel-2007
functions only (AVERAGEIFS / COUNTIFS / SUMPRODUCT / T.INV.2T), and native
Excel charts read those summary cells, so charts fill in as data are pasted.
Empty cells yield #N/A on purpose: Excel charts skip #N/A instead of plotting 0.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.chart import BarChart, LineChart, ScatterChart, Reference, Series
from openpyxl.chart.error_bar import ErrorBars
from openpyxl.chart.data_source import NumDataSource, NumRef
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation
from bench import spec

OUT = sys.argv[1] if len(sys.argv) > 1 else 'OptimusDB_Section8_Evidence.xlsx'
FIRST, LAST = 5, 3000           # data rows in raw sheets (row 4 = format example)

F = 'Arial'
H1 = Font(name=F, size=14, bold=True, color='1F3864')
H2 = Font(name=F, size=11, bold=True, color='1F3864')
B = Font(name=F, size=10)
BB = Font(name=F, size=10, bold=True)
HDR = Font(name=F, size=10, bold=True, color='FFFFFF')
EX = Font(name=F, size=9, italic=True, color='808080')
NOTE = Font(name=F, size=9, italic=True, color='595959')
HFILL = PatternFill('solid', fgColor='1F3864')
INFILL = PatternFill('solid', fgColor='FFF2CC')     # cells to fill in
SUBFILL = PatternFill('solid', fgColor='D9E1F2')
thin = Side(style='thin', color='BFBFBF')
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical='top')

wb = Workbook()
EXP = {e['id']: e for e in spec.EXPERIMENTS}

def style_header(ws, row, ncol, start=1):
    for c in range(start, start + ncol):
        cell = ws.cell(row=row, column=c)
        cell.font = HDR; cell.fill = HFILL; cell.alignment = Alignment(wrap_text=True, vertical='center'); cell.border = BOX

def table(ws, r0, headers, rows, widths=None, c0=1):
    for j, h in enumerate(headers): ws.cell(row=r0, column=c0 + j, value=h)
    style_header(ws, r0, len(headers), c0)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = ws.cell(row=r0 + 1 + i, column=c0 + j, value=v); c.font = B; c.alignment = WRAP; c.border = BOX
    if widths:
        for j, w in enumerate(widths): ws.column_dimensions[L(c0 + j)].width = w
    return r0 + 1 + len(rows)

def title(ws, text, sub=None):
    ws['A1'] = text; ws['A1'].font = H1
    if sub: ws['A2'] = sub; ws['A2'].font = NOTE
    ws.sheet_view.showGridLines = False

# ------------------------------------------------------------------ README
ws = wb.active; ws.title = 'README'
title(ws, 'OptimusDB – Section 8 evidence workbook',
      'Companion to the Section 8 manuscript and the optimusdb-bench harness. No results are entered yet: every chart and summary fills in from the *_raw sheets.')
rows = [
    ('1', 'Run an experiment with the harness (see optimusdb-bench/README.md). It writes results/<E>_raw.csv with exactly the columns of sheet <E>_raw.'),
    ('2', 'Open the CSV, copy all data rows (not the header) and paste them into <E>_raw starting at row 5 (Paste Special → Values). Row 4 is a format example and is excluded from all formulas.'),
    ('3', 'The matching <E>_sum sheet recalculates mean, n, standard deviation and 95% CI; its charts update automatically. Cells show #N/A (greyed) until data exist, so charts do not plot zeros.'),
    ('4', 'Copy each chart into the manuscript (Paste Special → Picture (Enhanced Metafile) or keep linked). Figure IDs F1–F11 match the manuscript placeholders.'),
    ('5', 'Record every run in Run_log (date, commit, operator, deviations) and every cloud/device cost in Cost (principle P8).'),
    ('6', 'Statistical tests (Welch / Mann–Whitney, Cliff\'s δ, Holm correction, CDFs) are produced by bench/analyze.py into results/stats_*.csv; paste them into Stats.'),
]
r = table(ws, 4, ['Step', 'What to do'], rows, [8, 120])
ws.cell(row=r + 1, column=1, value='Legend').font = H2
ws.cell(row=r + 2, column=1).fill = INFILL; ws.cell(row=r + 2, column=2, value='Yellow cells: fill in (configuration, versions, costs, gold annotations).').font = B
ws.cell(row=r + 3, column=1, value='EXAMPLE').font = EX; ws.cell(row=r + 3, column=2, value='Grey italic row 4 in each raw sheet shows the expected format only; it is ignored by every formula.').font = B
ws.cell(row=r + 4, column=1, value='#N/A').font = Font(name=F, size=10, color='A6A6A6'); ws.cell(row=r + 4, column=2, value='No data yet for that cell.').font = B
r += 6
ws.cell(row=r, column=1, value='Sheets').font = H2
sheets_list = [('Claims', 'Contribution / RQ → hypothesis → experiment → figure, with status'),
               ('Matrix', 'Full experiment matrix: factors, repetitions, duration, raw sheet'),
               ('Testbed', 'Hardware, software and network-emulation configuration (planned; confirm before runs)'),
               ('Baselines', 'Systems under test, versions and configuration'),
               ('Metrics', 'Metric definitions and units'),
               ('Principles', 'Compliance with the eight methodological principles of Papadopoulos et al. (IEEE TSE 2021)'),
               ('E1_raw … E11_raw', 'Per-run results (input)'),
               ('E1_sum … E11_sum', 'Summaries and charts F1–F11 (formulas only)'),
               ('Stats', 'Paste area for statistical tests from analyze.py'),
               ('Run_log, Cost', 'Provenance and cost records')]
table(ws, r + 1, ['Sheet', 'Content'], sheets_list)

# ------------------------------------------------------------------ Claims
ws = wb.create_sheet('Claims')
title(ws, 'Claims → evidence map', 'Each claim in the paper must point to a row here whose status is "Done" before submission.')
claims = [
    ('C1 OptimusDB system', 'RQ1, RQ2', 'E1, E2, E3, E4, E6, E8, E5'),
    ('C2 Reputation-based election', 'RQ3', 'E9'),
    ('C3 Multi-strategy query engine', 'RQ2', 'E1, E7'),
    ('C4 Decentralized identity and access control', 'RQ2', 'E10'),
    ('C5 AI-assisted metadata enrichment', 'RQ1', 'E11'),
]
r = table(ws, 4, ['Contribution', 'Research questions', 'Experiments'], claims, [42, 18, 30])
r += 1
hyp_rows = [(e['id'], e['section'], e['title'], e['rq'], e['contrib'], e['hypothesis'], e['figure'], 'Not run') for e in spec.EXPERIMENTS]
end = table(ws, r, ['Exp.', '§', 'Title', 'RQ', 'Contribution', 'Hypothesis (falsifiable)', 'Figure', 'Status'], hyp_rows, [8, 8, 34, 14, 14, 80, 8, 12])
dv = DataValidation(type='list', formula1='"Not run,Running,Done,Dropped"', allow_blank=False)
ws.add_data_validation(dv)
for i in range(r + 1, end):
    dv.add(ws.cell(row=i, column=8)); ws.cell(row=i, column=8).fill = INFILL

# ------------------------------------------------------------------ Matrix
ws = wb.create_sheet('Matrix')
title(ws, 'Experiment matrix')
mrows = [(e['id'], e['part'], e['section'], e['title'], e['factors'], e['reps'], e['duration'], e['id'] + '_raw', e['id'] + '_sum', e['figure']) for e in spec.EXPERIMENTS]
table(ws, 4, ['Exp.', 'Part', '§', 'Title', 'Factors and levels', 'Repetitions', 'Duration per run', 'Raw sheet', 'Summary sheet', 'Figure'],
      mrows, [7, 6, 7, 32, 70, 11, 26, 11, 13, 8])

# ------------------------------------------------------------------ Testbed
ws = wb.create_sheet('Testbed')
title(ws, 'Testbed configuration (planned)', 'Planned configuration from the manuscript draft. Confirm every value against the actual deployment before running; edit yellow cells.')
hw = [('Cloud', 'AWS EC2 m5.xlarge', 4, 16, '100 GB gp3 SSD', 2, 'eu-central-1'),
      ('Fog', 'Intel NUC', 4, 8, '256 GB SSD', 2, 'lab'),
      ('Edge', 'Raspberry Pi 4 Model B', 4, 4, '32 GB A2 SD card', 4, 'lab')]
r = table(ws, 4, ['Tier', 'Hardware', 'vCPU / cores', 'RAM (GB)', 'Storage', 'Agents (default 8-agent cluster)', 'Location'], hw, [10, 26, 12, 10, 18, 18, 14])
for i in range(5, r):
    for c in range(2, 8): ws.cell(row=i, column=c).fill = INFILL
r += 1
ws.cell(row=r, column=1, value='Network emulation (tc netem, applied on egress of every agent)').font = H2
net = [('cloud ↔ cloud', 5, 1, 0.0, 1000), ('cloud ↔ fog', 20, 4, 0.1, 100), ('fog ↔ edge', 50, 10, 0.5, 10), ('edge ↔ edge (same site)', 2, 0.5, 0.0, 100)]
r2 = table(ws, r + 1, ['Link', 'One-way delay (ms)', 'Jitter (ms)', 'Loss (%)', 'Rate (Mbit/s)'], net)
for i in range(r + 2, r2):
    for c in range(2, 6): ws.cell(row=i, column=c).fill = INFILL
ws.cell(row=r2, column=1, value='Delay/rate from the draft; jitter and loss are proposed defaults — justify from published continuum measurements or your own traces.').font = NOTE
r2 += 2
ws.cell(row=r2, column=1, value='Software').font = H2
sw = [('OS', 'Ubuntu 22.04 LTS (cloud, fog); Raspberry Pi OS 64-bit (edge)'), ('Container runtime', 'K3s v1.29 (cloud, fog); containerd (edge)'),
      ('Clock sync', 'chrony, offsets logged every 10 s (needed for staleness)'), ('Load generator host', 'Separate m5.large in the cloud region; never co-located with an agent'),
      ('Monitoring', 'cAdvisor + node_exporter → Prometheus, 1 s scrape'), ('Fault injection', 'tc netem, iptables, kill -9 / kubectl delete pod (Chaos Mesh optional)')]
r3 = table(ws, r2 + 1, ['Item', 'Value'], sw)
for i in range(r2 + 2, r3): ws.cell(row=i, column=2).fill = INFILL

# ------------------------------------------------------------------ Baselines
ws = wb.create_sheet('Baselines')
title(ws, 'Systems under test (all decentralized, P2P class of Table 1)', 'Record exact versions/commits; every system runs on the same hardware, network emulation and workload generator.')
r = table(ws, 4, ['ID', 'System', 'Replication / merge', 'Paradigm', 'Version / commit', 'Configuration'], spec.SYSTEMS, [12, 24, 34, 38, 16, 90])
for i in range(5, r): ws.cell(row=i, column=5).fill = INFILL

# ------------------------------------------------------------------ Metrics, Principles
ws = wb.create_sheet('Metrics'); title(ws, 'Metric definitions')
table(ws, 4, ['Metric', 'Unit', 'Definition'], spec.METRICS, [34, 10, 120])
ws = wb.create_sheet('Principles')
title(ws, 'Methodological principles', 'A. V. Papadopoulos et al., "Methodological principles for reproducible performance evaluation in cloud computing," IEEE TSE 47(8), 2021.')
r = table(ws, 4, ['Principle', 'How this evaluation satisfies it', 'Status'], [p + ('Planned',) for p in spec.PRINCIPLES], [36, 100, 12])
for i in range(5, r): ws.cell(row=i, column=3).fill = INFILL

# ------------------------------------------------------------------ raw sheets
EXAMPLES = {
    'E1': ['EXAMPLE', 'optimusdb', 'WO', 1, 15000, 0, 0, 0, 0, 0, 0, 50, '2026-11-02T10:00:00Z', 'format only'],
}
def raw_sheet(name, cols, desc):
    ws = wb.create_sheet(name)
    ws['A1'] = name + ' – raw results (one row per run)'; ws['A1'].font = H1
    ws['A2'] = desc; ws['A2'].font = NOTE
    for j, c in enumerate(cols): ws.cell(row=3, column=j + 1, value=c)
    style_header(ws, 3, len(cols))
    for j, c in enumerate(cols):
        cell = ws.cell(row=4, column=j + 1, value=('EXAMPLE' if j == 0 else ('format only' if c == 'notes' else None)))
        cell.font = EX
        ws.column_dimensions[L(j + 1)].width = max(11, len(c) + 3)
    ws.freeze_panes = 'A5'
    return ws

COL = {}
for e in spec.EXPERIMENTS:
    ws = raw_sheet(e['id'] + '_raw', e['raw'], f"{e['title']} — factors: {e['factors']}. Repetitions: {e['reps']}. Paste harness output from row 5.")
    COL[e['id']] = {c: L(i + 1) for i, c in enumerate(e['raw'])}
for k, cols in spec.EXTRA_RAW.items():
    raw_sheet(k + '_raw', cols, 'Supplementary raw data for ' + k.split('_')[0] + '. Paste harness output from row 5.')
    COL[k] = {c: L(i + 1) for i, c in enumerate(cols)}

def rng(sheet, col):
    return f"{sheet}!${col}${FIRST}:${col}${LAST}"

def crit_args(sheet, cols, conds):
    out = []
    for colname, ref in conds:
        out += [rng(sheet, cols[colname]), ref]
    return out

def f_mean(sheet, cols, metric, conds):
    a = ','.join(crit_args(sheet, cols, conds))
    return f"=IFERROR(AVERAGEIFS({rng(sheet, cols[metric])},{a}),NA())"

def f_n(sheet, cols, metric, conds):
    a = ','.join(crit_args(sheet, cols, conds))
    return f'=COUNTIFS({a},{rng(sheet, cols[metric])},"<>")'

def f_ci(sheet, cols, metric, conds, mean_ref, n_ref):
    prod = '*'.join(f"({rng(sheet, cols[c])}={ref})" for c, ref in conds)
    m = rng(sheet, cols[metric])
    sd = f"SQRT(MAX(0,(SUMPRODUCT({prod}*({m}<>\"\")*{m}^2)-{n_ref}*{mean_ref}^2)/({n_ref}-1)))"
    return f"=IFERROR(TINV(0.05,{n_ref}-1)*{sd}/SQRT({n_ref}),NA())"

def grey_na(ws, ref_range):
    ws.conditional_formatting.add(ref_range, FormulaRule(formula=[f'ISNA({ref_range.split(":")[0]})'], font=Font(color='BFBFBF')))

def block(ws, r0, c0, raw, cols, row_key, row_vals, col_key, col_vals, metric, fixed, label, with_ci=True, col_labels=None):
    """Grid of run means. Rows = row_vals of row_key. Columns = col_vals of col_key,
    or, when col_key is None, each column is a different metric (col_vals = metric names).
    fixed = [(colname, value)] constant conditions, written into visible cells."""
    ws.cell(row=r0, column=c0, value=label).font = H2
    fixed_cells = []
    for k, (fname, fval) in enumerate(fixed):
        ws.cell(row=r0, column=c0 + 3 + 2 * k, value=fname + ' =').font = NOTE
        fc = ws.cell(row=r0, column=c0 + 4 + 2 * k, value=fval); fc.font = BB; fc.fill = SUBFILL
        fixed_cells.append((fname, f"${L(c0 + 4 + 2 * k)}${r0}"))
    hdr = r0 + 1
    ws.cell(row=hdr, column=c0, value=row_key)
    labels = col_labels or col_vals
    for j, v in enumerate(labels): ws.cell(row=hdr, column=c0 + 1 + j, value=v)
    style_header(ws, hdr, 1 + len(col_vals), c0)
    nr = len(row_vals)
    n0 = hdr + nr + 2; ci0 = n0 + nr + 2
    if with_ci:
        ws.cell(row=n0 - 1, column=c0, value='n (runs)').font = NOTE
        ws.cell(row=ci0 - 1, column=c0, value='95% CI half-width').font = NOTE
    for i, rv in enumerate(row_vals):
        rr = hdr + 1 + i
        ws.cell(row=rr, column=c0, value=rv).font = BB
        if with_ci:
            ws.cell(row=n0 + i, column=c0, value=f"={L(c0)}{rr}").font = B
            ws.cell(row=ci0 + i, column=c0, value=f"={L(c0)}{rr}").font = B
        for j, cv in enumerate(col_vals):
            cc = c0 + 1 + j
            conds = [(row_key, f"${L(c0)}{rr}")] + fixed_cells
            if col_key is None:
                m = cv
            else:
                m = metric
                conds.append((col_key, f"{L(cc)}${hdr}"))
            mean_cell = f"{L(cc)}{rr}"
            ws.cell(row=rr, column=cc, value=f_mean(raw, cols, m, conds)).number_format = '0.0'
            if with_ci:
                ws.cell(row=n0 + i, column=cc, value=f_n(raw, cols, m, conds))
                ws.cell(row=ci0 + i, column=cc, value=f_ci(raw, cols, m, conds, mean_cell, f"{L(cc)}{n0 + i}")).number_format = '0.0'
    grey_na(ws, f"{L(c0 + 1)}{hdr + 1}:{L(c0 + len(col_vals))}{hdr + nr}")
    if with_ci:
        grey_na(ws, f"{L(c0 + 1)}{ci0}:{L(c0 + len(col_vals))}{ci0 + nr - 1}")
    return dict(hdr=hdr, first=hdr + 1, last=hdr + nr, c0=c0, ncol=len(col_vals),
                ci_first=ci0 if with_ci else None, end=(ci0 + nr) if with_ci else hdr + nr)

def add_err(series, ws, b, j):
    if not b.get('ci_first'): return
    col = L(b['c0'] + 1 + j)
    ref = f"'{ws.title}'!${col}${b['ci_first']}:${col}${b['ci_first'] + b['last'] - b['first']}"
    series.errBars = ErrorBars(errDir='y', errBarType='both', errValType='cust', noEndCap=False,
                               plus=NumDataSource(numRef=NumRef(f=ref)), minus=NumDataSource(numRef=NumRef(f=ref)))

def _axes(ch):
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ch.legend.position = 'b'

def bar_chart(ws, b, title_, ytitle, anchor, err=True, log=False, w=17, h=8.5, xtitle=None):
    ch = BarChart(); ch.type = 'col'; ch.grouping = 'clustered'; ch.title = title_
    ch.y_axis.title = ytitle; ch.width = w; ch.height = h
    if xtitle: ch.x_axis.title = xtitle
    for j in range(b['ncol']):
        ch.add_data(Reference(ws, min_col=b['c0'] + 1 + j, min_row=b['hdr'], max_row=b['last']), titles_from_data=True)
        if err: add_err(ch.series[-1], ws, b, j)
    ch.set_categories(Reference(ws, min_col=b['c0'], min_row=b['first'], max_row=b['last']))
    if log: ch.y_axis.scaling.logBase = 10
    _axes(ch); ws.add_chart(ch, anchor); return ch

def line_rows_as_series(ws, b, title_, xtitle, ytitle, anchor, w=17, h=8.5, extra_rows=()):
    """Each block row is a series; block columns are the x axis (categories)."""
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.chart.data_source import StrRef
    ch = LineChart(); ch.title = title_; ch.width = w; ch.height = h
    ch.x_axis.title = xtitle; ch.y_axis.title = ytitle
    for i in list(range(b['first'], b['last'] + 1)) + list(extra_rows):
        s = Series(Reference(ws, min_col=b['c0'] + 1, max_col=b['c0'] + b['ncol'], min_row=i))
        s.tx = SeriesLabel(strRef=StrRef(f"'{ws.title}'!${L(b['c0'])}${i}"))
        s.marker.symbol = 'circle'; s.smooth = False
        ch.series.append(s)
    ch.set_categories(Reference(ws, min_col=b['c0'] + 1, max_col=b['c0'] + b['ncol'], min_row=b['hdr']))
    _axes(ch); ws.add_chart(ch, anchor); return ch

def line_cols_as_series(ws, b, title_, xtitle, ytitle, anchor, err=True, w=17, h=8.5):
    ch = LineChart(); ch.title = title_; ch.width = w; ch.height = h
    ch.x_axis.title = xtitle; ch.y_axis.title = ytitle
    for j in range(b['ncol']):
        ch.add_data(Reference(ws, min_col=b['c0'] + 1 + j, min_row=b['hdr'], max_row=b['last']), titles_from_data=True)
        ch.series[-1].marker.symbol = 'circle'; ch.series[-1].smooth = False
        if err: add_err(ch.series[-1], ws, b, j)
    ch.set_categories(Reference(ws, min_col=b['c0'], min_row=b['first'], max_row=b['last']))
    _axes(ch); ws.add_chart(ch, anchor); return ch

def sum_sheet(eid, sub):
    ws = wb.create_sheet(eid + '_sum')
    e = EXP[eid]
    ws['A1'] = f"{eid} – {e['title']} (§{e['section']}, figure {e['figure']})"; ws['A1'].font = H1
    ws['A2'] = sub; ws['A2'].font = NOTE
    ws['A3'] = 'Hypothesis ' + e['hypothesis']; ws['A3'].font = NOTE
    ws.column_dimensions['A'].width = 26
    for c in range(2, 40): ws.column_dimensions[L(c)].width = 12
    ws.sheet_view.showGridLines = False
    return ws

SYS = [s[0] for s in spec.SYSTEMS]
PCT = ['p50_ms', 'p95_ms', 'p99_ms', 'p999_ms']
CH = 'K'   # chart column

# ---- E1 latency
ws = sum_sheet('E1', 'Means over runs of per-run percentiles (ms) with 95% CI. Chart F1 = workload WO; one block per workload.')
r = 5; blocks = []
for wl in ['WO', 'WA', 'WB', 'WC']:
    b = block(ws, r, 1, 'E1_raw', COL['E1'], 'system', SYS, None, PCT, None, [('workload', wl), ('doc_size', '2KB')], f'Workload {wl} (2 KB)',
              col_labels=['P50', 'P95', 'P99', 'P99.9'])
    blocks.append(b); r = b['end'] + 2
bar_chart(ws, blocks[0], 'F1. Latency percentiles, workload WO (50 ops/s, 2 KB)', 'Latency (ms)', f'{CH}5')
bar_chart(ws, blocks[1], 'Latency percentiles, workload WA', 'Latency (ms)', f'{CH}24', w=12, h=7)
# relative P99 vs OptimusDB
rr = r + 1
ws.cell(row=rr, column=1, value='P99 relative to OptimusDB (WO): system P99 / OptimusDB P99').font = H2
for i, s in enumerate(SYS):
    ws.cell(row=rr + 1 + i, column=1, value=s).font = B
    c = ws.cell(row=rr + 1 + i, column=2, value=f"=IFERROR(D{blocks[0]['first'] + i}/D${blocks[0]['first']},NA())"); c.number_format = '0.00'
grey_na(ws, f"B{rr + 1}:B{rr + len(SYS)}")

# ---- E2 throughput / volume
ws = sum_sheet('E2', 'F2a: achieved vs offered load at 10^5 records. F2b: P99 vs data volume at 50 ops/s. Saturation = highest offered load with achieved ≥ 99% offered and P99 ≤ 500 ms.')
loads = list(range(10, 210, 10))
b = block(ws, 5, 1, 'E2_raw', COL['E2'], 'system', SYS, 'offered_ops_s', loads, 'achieved_ops_s', [('dataset_records', 100000)], 'Achieved throughput (ops/s) by offered load', with_ci=True)
# ideal row
ideal_r = b['end'] + 1
ws.cell(row=ideal_r, column=1, value='ideal (= offered)').font = BB
for j, v in enumerate(loads): ws.cell(row=ideal_r, column=2 + j, value=f"={L(2 + j)}${b['hdr']}")
line_rows_as_series(ws, b, 'F2a. Sustained throughput vs offered load (10^5 records)', 'Offered load (ops/s)', 'Achieved (ops/s)', f'A{ideal_r + 2}', w=22, extra_rows=[ideal_r])
p = block(ws, ideal_r + 22, 1, 'E2_raw', COL['E2'], 'system', SYS, 'dataset_records', spec.DATASET_SIZES, 'p99_ms', [('offered_ops_s', 50)], 'P99 latency (ms) by data volume')
line_rows_as_series(ws, p, 'F2b. P99 latency vs data volume (50 ops/s)', 'Records', 'P99 (ms)', f'{L(8)}{ideal_r + 22}')
# saturation: highest load meeting criteria
sr = p['end'] + 2
ws.cell(row=sr, column=1, value='Saturation throughput (ops/s): highest offered load where achieved ≥ 0.99 × offered (needs P99 check in analyze.py)').font = H2
for i, s in enumerate(SYS):
    ws.cell(row=sr + 1 + i, column=1, value=s).font = B
    row = b['first'] + i
    terms = ','.join(f'IFERROR(IF({L(2 + j)}{row}>=0.99*{L(2 + j)}${b["hdr"]},{L(2 + j)}${b["hdr"]},0),0)' for j in range(len(loads)))
    ws.cell(row=sr + 1 + i, column=2, value=f"=MAX({terms})")

# ---- E3 SQL
ws = sum_sheet('E3', 'Mean latency (ms) per query at 10^5 records; correctness = share of runs whose result set equals the reference.')
SQLSYS = ['optimusdb|crdt', 'optimusdb|sqlite', 'corrosion|sql', 'gun|client_filter', 'autobase|range_client_filter', 'iroh|prefix_client_filter', 'opendht|key_only']
# helper key column in raw: system|path  -> use two conditions instead
QS = [q[0] for q in spec.QUERIES]
ws.cell(row=5, column=1, value='Mean latency (ms) by query, 10^5 records').font = H2
ws.cell(row=6, column=1, value='system'); ws.cell(row=6, column=2, value='path')
for j, q in enumerate(QS): ws.cell(row=6, column=3 + j, value=q)
style_header(ws, 6, 2 + len(QS))
ws.cell(row=5, column=9, value='dataset_records =').font = NOTE; ws['J5'] = 100000; ws['J5'].fill = SUBFILL; ws['J5'].font = BB
for i, key in enumerate(SQLSYS):
    sname, path = key.split('|'); rr = 7 + i
    ws.cell(row=rr, column=1, value=sname).font = BB; ws.cell(row=rr, column=2, value=path).font = BB
    for j, q in enumerate(QS):
        conds = [('system', f'$A{rr}'), ('path', f'$B{rr}'), ('query', f'{L(3 + j)}$6'), ('dataset_records', '$J$5')]
        ws.cell(row=rr, column=3 + j, value=f_mean('E3_raw', COL['E3'], 'mean_ms', conds)).number_format = '0.0'
grey_na(ws, f'C7:{L(2 + len(QS))}{6 + len(SQLSYS)}')
# label col for chart
for i, key in enumerate(SQLSYS):
    ws.cell(row=7 + i, column=9, value=f'=A{7 + i}&" ("&B{7 + i}&")"')
ch = BarChart(); ch.type = 'col'; ch.title = 'F3. SQL query latency by system and path (10^5 records)'; ch.y_axis.title = 'Mean latency (ms)'
ch.width = 18; ch.height = 9
for i in range(len(SQLSYS)):
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.chart.data_source import StrRef
    s = Series(Reference(ws, min_col=3, max_col=2 + len(QS), min_row=7 + i)); s.tx = SeriesLabel(strRef=StrRef(f"'E3_sum'!$I${7 + i}"))
    ch.series.append(s)
ch.set_categories(Reference(ws, min_col=3, max_col=2 + len(QS), min_row=6)); ch.y_axis.scaling.logBase = 10; _axes(ch)
ws.add_chart(ch, 'L5')
cr = 7 + len(SQLSYS) + 2
ws.cell(row=cr, column=1, value='Correctness (share of runs with correct=1), 10^5 records').font = H2
ws.cell(row=cr + 1, column=1, value='system'); ws.cell(row=cr + 1, column=2, value='path')
for j, q in enumerate(QS): ws.cell(row=cr + 1, column=3 + j, value=q)
style_header(ws, cr + 1, 2 + len(QS))
for i, key in enumerate(SQLSYS):
    rr = cr + 2 + i; ws.cell(row=rr, column=1, value=f'=A{7 + i}'); ws.cell(row=rr, column=2, value=f'=B{7 + i}')
    for j, q in enumerate(QS):
        conds = [('system', f'$A{rr}'), ('path', f'$B{rr}'), ('query', f'{L(3 + j)}${cr + 1}'), ('dataset_records', '$J$5')]
        c = ws.cell(row=rr, column=3 + j, value=f_mean('E3_raw', COL['E3'], 'correct', conds)); c.number_format = '0%'
grey_na(ws, f'C{cr + 2}:{L(2 + len(QS))}{cr + 1 + len(SQLSYS)}')
ws.cell(row=cr + 2 + len(SQLSYS), column=1, value='Unsupported query on a path: record correct = 0 and notes = "unsupported"; it then shows 0%.').font = NOTE

# ---- E4 edge resources
ws = sum_sheet('E4', '4 × Raspberry Pi 4; per-agent means. A system that does not start sets started_ok = 0 and is reported as infeasible.')
LV = [0, 10, 20, 40]
b1 = block(ws, 5, 1, 'E4_raw', COL['E4'], 'system', SYS, 'offered_ops_s', LV, 'cpu_pct', [], 'CPU utilisation (%)')
line_rows_as_series(ws, b1, 'F4a. CPU on Raspberry Pi 4 vs load', 'Offered load (ops/s)', 'CPU (%)', f'{CH}5', w=14)
b2 = block(ws, b1['end'] + 2, 1, 'E4_raw', COL['E4'], 'system', SYS, 'offered_ops_s', LV, 'rss_mb', [], 'Resident memory (MB)')
lim = b2['end'] + 1
ws.cell(row=lim, column=1, value='512 MB budget').font = BB
for j in range(len(LV)): ws.cell(row=lim, column=2 + j, value=512)
line_rows_as_series(ws, b2, 'F4b. RSS on Raspberry Pi 4 vs load', 'Offered load (ops/s)', 'RSS (MB)', f'{CH}{b1["end"] + 2}', w=14, extra_rows=[lim])
b3 = block(ws, lim + 2, 1, 'E4_raw', COL['E4'], 'system', SYS, 'offered_ops_s', LV, 'net_kb_per_op', [], 'Network traffic per operation (KB)')
b4 = block(ws, b3['end'] + 2, 1, 'E4_raw', COL['E4'], 'system', SYS, 'offered_ops_s', [40], 'started_ok', [], 'Feasibility (share of runs that started)', with_ci=False)

# ---- E6 trace
ws = sum_sheet('E6', 'Captured Swarmchestrate trace replayed at 4× (all systems) and 1× (OptimusDB). Writes lost = write_errors summed over runs.')
T5 = SYS
b = block(ws, 5, 1, 'E6_raw', COL['E6'], 'system', ['optimusdb'], None, ['e2e_mean_ms', 'e2e_p99_ms', 'max_staleness_s', 'convergence_s'], None, [('speed', '1x')], 'Replay at 1×', col_labels=['E2E mean (ms)', 'E2E P99 (ms)', 'Max staleness (s)', 'Convergence (s)'])
b2 = block(ws, b['end'] + 2, 1, 'E6_raw', COL['E6'], 'system', T5, None, ['e2e_mean_ms', 'e2e_p99_ms', 'max_staleness_s', 'convergence_s'], None, [('speed', '4x')], 'Replay at 4×', col_labels=['E2E mean (ms)', 'E2E P99 (ms)', 'Max staleness (s)', 'Convergence (s)'])
ch = BarChart(); ch.type = 'col'; ch.title = 'F6. End-to-end decision latency under trace replay'; ch.y_axis.title = 'ms'; ch.width = 15; ch.height = 8
for bb, lab in [(b, '1×'), (b2, '4×')]:
    for j, nm in [(0, 'mean'), (1, 'P99')]:
        from openpyxl.chart.series import SeriesLabel
        s = Series(Reference(ws, min_col=bb['c0'] + 1 + j, min_row=bb['first'], max_row=bb['last'])); s.tx = SeriesLabel(v=f'{nm} {lab}')
        add_err(s, ws, bb, j); ch.series.append(s)
ch.set_categories(Reference(ws, min_col=1, min_row=b['first'], max_row=b['last'])); _axes(ch); ws.add_chart(ch, f'{CH}5')
er = b2['end'] + 2
ws.cell(row=er, column=1, value='Write errors / writes (all runs)').font = H2
for i, s_ in enumerate(T5):
    ws.cell(row=er + 1 + i, column=1, value=s_).font = B
    ws.cell(row=er + 1 + i, column=2, value=f"=SUMIFS({rng('E6_raw', COL['E6']['write_errors'])},{rng('E6_raw', COL['E6']['system'])},A{er + 1 + i})")
    ws.cell(row=er + 1 + i, column=3, value=f"=SUMIFS({rng('E6_raw', COL['E6']['writes_total'])},{rng('E6_raw', COL['E6']['system'])},A{er + 1 + i})")

# ---- E7 strategies
ws = sum_sheet('E7', '8 agents, 10^5 records; time budget fixed in the blue cell (change it to view 300 or 3000 ms).')
b1 = block(ws, 5, 1, 'E7_raw', COL['E7'], 'strategy', spec.STRATEGIES, 'initiator_tier', spec.TIERS, 'mean_ms', [('time_budget_ms', 1200)], 'Mean latency (ms)')
bar_chart(ws, b1, 'F7a. Query latency by strategy and initiator tier', 'Mean latency (ms, log)', f'{CH}5', log=True)
b2 = block(ws, b1['end'] + 2, 1, 'E7_raw', COL['E7'], 'strategy', spec.STRATEGIES, 'initiator_tier', spec.TIERS, 'completeness_pct', [('time_budget_ms', 1200)], 'Completeness (%)')
bar_chart(ws, b2, 'F7b. Result completeness by strategy and initiator tier', 'Completeness (%)', f'{CH}{b1["end"] + 2}')
b3 = block(ws, b2['end'] + 2, 1, 'E7_raw', COL['E7'], 'strategy', spec.STRATEGIES, 'initiator_tier', spec.TIERS, 'p99_ms', [('time_budget_ms', 1200)], 'P99 latency (ms)')
b4 = block(ws, b3['end'] + 2, 1, 'E7_raw', COL['E7'], 'strategy', spec.STRATEGIES, 'initiator_tier', spec.TIERS, 'staleness_s', [('time_budget_ms', 1200)], 'Staleness (s)')

# ---- E8 scalability
ws = sum_sheet('E8', 'Weak scaling: 10 ops/s per agent. Strong scaling: fixed 80 ops/s total. Efficiency = T(n) / (T(4) × n/4).')
AG = [4, 8, 16, 32, 64]
b = block(ws, 5, 1, 'E8_raw', COL['E8'], 'scaling', ['weak', 'strong'], 'agents', AG, 'achieved_ops_s', [], 'Achieved throughput (ops/s)')
ir = b['end'] + 1
ws.cell(row=ir, column=1, value='ideal weak').font = BB
for j in range(len(AG)): ws.cell(row=ir, column=2 + j, value=f"=IFERROR($B${b['first']}*{L(2 + j)}${b['hdr']}/$B${b['hdr']},NA())")
ws.cell(row=ir + 1, column=1, value='weak efficiency').font = BB
for j in range(len(AG)):
    c = ws.cell(row=ir + 1, column=2 + j, value=f"=IFERROR({L(2 + j)}{b['first']}/{L(2 + j)}{ir},NA())"); c.number_format = '0%'
grey_na(ws, f'B{ir}:{L(1 + len(AG))}{ir + 1}')
line_rows_as_series(ws, dict(b, last=b['first']), 'F8a. Weak-scaling throughput vs ideal', 'Agents', 'Achieved (ops/s)', f'{CH}5', extra_rows=[ir])
b2 = block(ws, ir + 3, 1, 'E8_raw', COL['E8'], 'scaling', ['weak', 'strong'], 'agents', AG, 'convergence_s', [], 'Convergence time (s)')
b3 = block(ws, b2['end'] + 2, 1, 'E8_raw', COL['E8'], 'scaling', ['weak', 'strong'], 'agents', AG, 'gossip_msgs_s_per_agent', [], 'GossipSub messages per agent per second')
line_rows_as_series(ws, b3, 'F8b. Per-agent GossipSub traffic vs agents', 'Agents', 'msgs/s per agent', f'{CH}{b2["hdr"]}')
b4 = block(ws, b3['end'] + 2, 1, 'E8_raw', COL['E8'], 'scaling', ['weak', 'strong'], 'agents', AG, 'p99_ms', [], 'P99 latency (ms)')
b5 = block(ws, b4['end'] + 2, 1, 'E8_raw', COL['E8'], 'scaling', ['weak', 'strong'], 'agents', AG, 'rss_mb_per_agent', [], 'RSS per agent (MB)')

# ---- E5 convergence
ws = sum_sheet('E5', 'Partition shape fixed in the blue cell. Lost acknowledged writes must be 0 in every run; any non-zero value is a correctness bug.')
CT = [0, 5, 15, 30, 50]; PD = [5, 30, 60, 300]
b = block(ws, 5, 1, 'E5_raw', COL['E5'], 'partition_s', PD, 'contention_pct', CT, 'convergence_s', [('partition_shape', '4|4'), ('system', 'optimusdb')], 'Convergence time after heal (s), OptimusDB')
line_rows_as_series(ws, b, 'F5a. Convergence after partition heal vs contention (OptimusDB, 4|4)', 'Hot-key contention (%)', 'Convergence (s)', f'{CH}5')
b2 = block(ws, b['end'] + 2, 1, 'E5_raw', COL['E5'], 'partition_s', PD, 'contention_pct', CT, 'divergent_entries', [('partition_shape', '4|4'), ('system', 'optimusdb')], 'Divergent entries at heal, OptimusDB')
b3 = block(ws, b2['end'] + 2, 1, 'E5_raw', COL['E5'], 'partition_s', PD, 'contention_pct', CT, 'convergence_s', [('partition_shape', '2|6'), ('system', 'optimusdb')], 'Convergence time (s), shape 2|6, OptimusDB')
REFS8 = SYS
b4 = block(ws, b3['end'] + 2, 1, 'E5_raw', COL['E5'], 'system', REFS8, 'contention_pct', [0, 30], 'write_availability_pct', [('partition_shape', '4|4'), ('partition_s', 60)], 'Write availability during a 60 s partition (%), 4|4')
bar_chart(ws, b4, 'F5b. Writes accepted during a 60 s partition (4|4): all systems', 'Accepted writes (%)', f'{CH}{b3["end"] + 2}')
b5 = block(ws, b4['end'] + 2, 1, 'E5_raw', COL['E5'], 'system', REFS8, 'contention_pct', [0, 30], 'convergence_s', [('partition_shape', '4|4'), ('partition_s', 60)], 'Convergence after heal (s), 60 s partition, 4|4')
lr = b5['end'] + 2
ws.cell(row=lr, column=1, value='Correctness totals (all runs, all systems)').font = H2
items = [('Acknowledged writes', f"=SUM({rng('E5_raw', COL['E5']['ack_writes'])})"),
         ('Lost acknowledged writes (must be 0)', f"=SUM({rng('E5_raw', COL['E5']['lost_ack_writes'])})"),
         ('Runs with identical replicas', f"=SUM({rng('E5_raw', COL['E5']['replicas_identical'])})"),
         ('Runs', f"=COUNT({rng('E5_raw', COL['E5']['convergence_s'])})")]
for i, (k, v) in enumerate(items):
    ws.cell(row=lr + 1 + i, column=1, value=k).font = B; ws.cell(row=lr + 1 + i, column=2, value=v)
ws.conditional_formatting.add(f'B{lr + 2}', FormulaRule(formula=[f'B{lr + 2}>0'], fill=PatternFill('solid', fgColor='F4CCCC')))

# ---- E9 election / faults
ws = sum_sheet('E9', '50 trials per cell. Quality ratio = R(elected)/max R(live candidates) at fault time. Agents fixed in the blue cell for F9a.')
b1 = block(ws, 5, 1, 'E9_raw', COL['E9'], 'scenario', spec.FAILURE_SCENARIOS, 'policy', spec.ELECTION_POLICIES, 'recover_s', [('agents', 8)], 'Recovery time (s)')
bar_chart(ws, b1, 'F9a. Recovery time by failure scenario and election policy (8 agents)', 'Recovery (s)', f'{CH}5')
b2 = block(ws, b1['end'] + 2, 1, 'E9_raw', COL['E9'], 'policy', spec.ELECTION_POLICIES, 'agents', [4, 8, 16, 32], 'quality_ratio', [('scenario', 'coordinator_crash')], 'Election quality ratio')
line_rows_as_series(ws, b2, 'F9b. Election quality ratio vs cluster size', 'Agents', 'Quality ratio', f'{CH}{b1["end"] + 2}')
b3 = block(ws, b2['end'] + 2, 1, 'E9_raw', COL['E9'], 'policy', spec.ELECTION_POLICIES, 'agents', [4, 8, 16, 32], 'elect_s', [('scenario', 'coordinator_crash')], 'Election time (s)')
b4 = block(ws, b3['end'] + 2, 1, 'E9_raw', COL['E9'], 'scenario', spec.FAILURE_SCENARIOS, 'policy', spec.ELECTION_POLICIES, 'availability_pct', [('agents', 8)], 'Availability during fault window (%)')
cr_ = b4['end'] + 2
ws.cell(row=cr_, column=1, value='Churn time series (rep 1) — plotted directly from E9_churn_raw').font = H2
sc = ScatterChart(); sc.title = 'F9c. Throughput under churn (one leave + one join every 30 s)'; sc.x_axis.title = 'Time (s)'; sc.y_axis.title = 'ops/s'
sc.width = 18; sc.height = 8; sc.style = 13
xs = Reference(wb['E9_churn_raw'], min_col=1, min_row=FIRST, max_row=FIRST + 1200)
ys = Reference(wb['E9_churn_raw'], min_col=3, min_row=FIRST, max_row=FIRST + 1200)
s = Series(ys, xs, title='throughput'); s.marker.symbol = 'none'; sc.series.append(s); _axes(sc)
ws.add_chart(sc, f'A{cr_ + 1}')
ws.cell(row=cr_ + 18, column=1, value='Paste only rep 1 into E9_churn_raw rows 5–1204 for this chart; keep other reps in the harness CSV.').font = NOTE

# ---- E10 access control
ws = sum_sheet('E10', 'Overhead = mean(on) − mean(off) for granted operations; denials are measured by injecting each failure cause.')
b1 = block(ws, 5, 1, 'E10_raw', COL['E10'], 'outcome', spec.AC_OUTCOMES, 'operation', ['read', 'write'], 'mean_ms', [('ac_mode', 'on')], 'Mean latency with access control (ms)')
b0 = block(ws, b1['end'] + 2, 1, 'E10_raw', COL['E10'], 'outcome', ['granted'], 'operation', ['read', 'write'], 'mean_ms', [('ac_mode', 'off')], 'Mean latency without access control (ms)')
orow = b0['end'] + 1
ws.cell(row=orow, column=1, value='Overhead granted (ms)').font = BB
for j in range(2): ws.cell(row=orow, column=2 + j, value=f"=IFERROR({L(2 + j)}{b1['first']}-{L(2 + j)}{b0['first']},NA())").number_format = '0.00'
bar_chart(ws, b1, 'F10. Latency by access-control outcome (read / write)', 'Mean latency (ms)', f'{CH}5')
b2 = block(ws, orow + 2, 1, 'E10_raw', COL['E10'], 'outcome', spec.AC_OUTCOMES, 'operation', ['read', 'write'], 'verify_us', [('ac_mode', 'on')], 'Server-side verification cost (µs)')
rv = block(ws, b2['end'] + 2, 1, 'E10_revocation_raw', COL['E10_revocation'], 'agents', [4, 8, 16, 32], None, ['propagation_s'], None, [], 'Revocation propagation to all agents (s)', col_labels=['propagation (s)'])

# ---- E11 AI
ws = sum_sheet('E11', 'Precision/recall/F1 from TP/FP/FN summed over the held-out split. Kappa from the annotator agreement table.')
ws.cell(row=5, column=1, value='Per-field scores').font = H2
hdrs = ['field', 'extractor', 'TP', 'FP', 'FN', 'Precision', 'Recall', 'F1']
for j, h in enumerate(hdrs): ws.cell(row=6, column=1 + j, value=h)
style_header(ws, 6, len(hdrs))
rr = 7
for ext in ['tinyllama', 'rules']:
    for fld in spec.AI_FIELDS:
        ws.cell(row=rr, column=1, value=fld).font = BB; ws.cell(row=rr, column=2, value=ext).font = BB
        for k, m in enumerate(['tp', 'fp', 'fn']):
            ws.cell(row=rr, column=3 + k, value=f"=SUMIFS({rng('E11_raw', COL['E11'][m])},{rng('E11_raw', COL['E11']['field'])},$A{rr},{rng('E11_raw', COL['E11']['extractor'])},$B{rr})")
        ws.cell(row=rr, column=6, value=f"=IFERROR(C{rr}/(C{rr}+D{rr}),NA())").number_format = '0.00'
        ws.cell(row=rr, column=7, value=f"=IFERROR(C{rr}/(C{rr}+E{rr}),NA())").number_format = '0.00'
        ws.cell(row=rr, column=8, value=f"=IFERROR(2*F{rr}*G{rr}/(F{rr}+G{rr}),NA())").number_format = '0.00'
        rr += 1
grey_na(ws, f'F7:H{rr - 1}')
ch = BarChart(); ch.type = 'col'; ch.title = 'F11a. TinyLlama vs rule-based extraction: F1 by field'; ch.y_axis.title = 'F1'; ch.width = 16; ch.height = 8
from openpyxl.chart.series import SeriesLabel
s1 = Series(Reference(ws, min_col=8, min_row=7, max_row=11)); s1.tx = SeriesLabel(v='TinyLlama'); ch.series.append(s1)
s2 = Series(Reference(ws, min_col=8, min_row=12, max_row=16)); s2.tx = SeriesLabel(v='Rule-based'); ch.series.append(s2)
ch.set_categories(Reference(ws, min_col=1, min_row=7, max_row=11)); ch.y_axis.scaling.min = 0; ch.y_axis.scaling.max = 1; _axes(ch)
ws.add_chart(ch, 'K5')
lb = block(ws, rr + 2, 1, 'E11_latency_raw', COL['E11_latency'], 'tier', spec.TIERS, 'mode', ['sync', 'async'], 'latency_ms', [], 'Ingest latency per document (ms)')
bar_chart(ws, lb, 'F11b. Ingest latency per document by tier and enrichment mode', 'ms (log)', f'K{rr + 2}', log=True)
kr = lb['end'] + 2
ws.cell(row=kr, column=1, value="Inter-annotator agreement (Cohen's κ) — from E11_agreement_raw").font = H2
kh = ['field', 'both yes', 'A yes B no', 'A no B yes', 'both no', 'p_o', 'p_e', 'kappa']
for j, h in enumerate(kh): ws.cell(row=kr + 1, column=1 + j, value=h)
style_header(ws, kr + 1, len(kh))
A = COL['E11_agreement']
for i, fld in enumerate(spec.AI_FIELDS):
    r_ = kr + 2 + i
    ws.cell(row=r_, column=1, value=fld).font = BB
    for k, m in enumerate(['both_yes', 'a_yes_b_no', 'a_no_b_yes', 'both_no']):
        ws.cell(row=r_, column=2 + k, value=f"=SUMIFS({rng('E11_agreement_raw', A[m])},{rng('E11_agreement_raw', A['field'])},$A{r_})")
    tot = f"(B{r_}+C{r_}+D{r_}+E{r_})"
    ws.cell(row=r_, column=6, value=f"=IFERROR((B{r_}+E{r_})/{tot},NA())").number_format = '0.00'
    ws.cell(row=r_, column=7, value=f"=IFERROR(((B{r_}+C{r_})*(B{r_}+D{r_})+(D{r_}+E{r_})*(C{r_}+E{r_}))/{tot}^2,NA())").number_format = '0.00'
    ws.cell(row=r_, column=8, value=f"=IFERROR((F{r_}-G{r_})/(1-G{r_}),NA())").number_format = '0.00'
grey_na(ws, f'F{kr + 2}:H{kr + 1 + len(spec.AI_FIELDS)}')

# ------------------------------------------------------------------ Stats, Run_log, Cost
ws = wb.create_sheet('Stats')
title(ws, 'Statistical tests (paste from results/stats_*.csv)', 'analyze.py: Shapiro–Wilk → Welch t-test or Mann–Whitney U, Cliff\'s δ with magnitude, Holm–Bonferroni adjusted p across each family of comparisons.')
cols = ['experiment', 'metric', 'condition', 'system_a', 'system_b', 'n_a', 'n_b', 'mean_a', 'mean_b', 'diff_pct', 'test', 'p_raw', 'p_holm', 'cliffs_delta', 'magnitude', 'significant']
for j, c in enumerate(cols): ws.cell(row=4, column=1 + j, value=c)
style_header(ws, 4, len(cols))
for j in range(len(cols)): ws.column_dimensions[L(1 + j)].width = 13
ws.cell(row=6 + 200, column=1, value='Quick check (Excel): Welch p-value for two pasted samples').font = H2
ws.cell(row=207, column=1, value='Sample A in column R from row 210; sample B in column S from row 210.').font = NOTE
ws.cell(row=208, column=1, value='Welch p (two-tailed)').font = BB
ws.cell(row=208, column=2, value='=IFERROR(TTEST(R210:R2000,S210:S2000,2,3),NA())').number_format = '0.0000'
ws.cell(row=209, column=18, value='A').font = BB; ws.cell(row=209, column=19, value='B').font = BB

ws = wb.create_sheet('Run_log')
title(ws, 'Run log (provenance)')
cols = ['date_utc', 'experiment', 'run_id range', 'optimusdb commit', 'harness commit', 'config file', 'operator', 'deviations / incidents']
for j, c in enumerate(cols): ws.cell(row=4, column=1 + j, value=c)
style_header(ws, 4, len(cols))
for j in range(len(cols)): ws.column_dimensions[L(1 + j)].width = 20

ws = wb.create_sheet('Cost')
title(ws, 'Cost (principle P8)')
cols = ['experiment', 'resource', 'units', 'hours', 'unit price (EUR/h)', 'cost (EUR)']
for j, c in enumerate(cols): ws.cell(row=4, column=1 + j, value=c)
style_header(ws, 4, len(cols))
for i in range(5, 30): ws.cell(row=i, column=6, value=f'=IF(OR(C{i}="",D{i}="",E{i}=""),"",C{i}*D{i}*E{i})').number_format = '0.00'
ws.cell(row=30, column=5, value='Total').font = BB; ws.cell(row=30, column=6, value='=SUM(F5:F29)').number_format = '0.00'
for j in range(len(cols)): ws.column_dimensions[L(1 + j)].width = 18

# order: put sums after raws grouped by experiment
order = ['README', 'Claims', 'Matrix', 'Testbed', 'Baselines', 'Metrics', 'Principles']
for e in spec.EXPERIMENTS:
    order += [e['id'] + '_sum', e['id'] + '_raw'] + [k + '_raw' for k in spec.EXTRA_RAW if k.startswith(e['id'] + '_')]
order += ['Stats', 'Run_log', 'Cost']
wb._sheets = [wb[n] for n in order]
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for c in row:
            if c.font and c.font.name != F:
                c.font = Font(name=F, size=c.font.size or 10, bold=c.font.bold, italic=c.font.italic, color=c.font.color)
if os.environ.get('BENCH_SELFTEST') == '1':   # verification only: random TEST rows, never shipped
    import random; random.seed(7)
    def put(sheet, rows):
        w = wb[sheet]
        for i, row in enumerate(rows):
            for j, v in enumerate(row): w.cell(row=FIRST + i, column=j + 1, value=v)
    rows = []
    for s_ in SYS:
        for wl in ['WO', 'WA']:
            for rep in range(1, 6):
                b_ = random.uniform(50, 300); rows.append([f'{s_}{rep}', s_, wl, '2KB', rep, 1, 0, b_, b_, b_ * 1.2, b_ * 1.4, b_ * 1.7, 50, '', 'TEST'])
    put('E1_raw', rows)
    rows = []
    for s_ in SYS:
        cap = random.uniform(40, 200)
        for L_ in range(10, 210, 10):
            for rep in range(1, 3): rows.append([f'{s_}{L_}{rep}', s_, 100000, L_, rep, min(L_, cap) * random.uniform(0.97, 1.0), 100, 0, '', 'TEST'])
    put('E2_raw', rows)
    rows = [[f'c{t}', t, 1, 50 - (8 if t % 30 < 4 else 0) + random.uniform(-2, 2), '', 'TEST'] for t in range(0, 1200)]
    put('E9_churn_raw', rows)
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print('saved', OUT)
