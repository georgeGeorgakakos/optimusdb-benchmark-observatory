"""Generate the three-site testbed diagram (draw.io / diagrams.net XML)."""
import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else 'OptimusDB_Testbed_3Sites.drawio'
cells = []
_id = [10]
def nid():
    _id[0] += 1; return f'n{_id[0]}'

def box(x, y, w, h, label, style, parent='1'):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i

def edge(src, tgt, label='', style='endArrow=none;html=1;strokeWidth=2;strokeColor=#5F5E5A;'):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{style}" edge="1" parent="1" source="{src}" target="{tgt}">'
                 f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    return i

FONT = 'fontFamily=Helvetica;fontSize=11;'
SITE = 'rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontStyle=1;fontSize=14;arcSize=3;'
HV = 'rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;verticalAlign=top;align=left;spacingLeft=8;spacingTop=4;fontStyle=1;fontSize=12;fillColor=#F5F5F5;strokeColor=#666666;dashed=0;arcSize=3;'
VM = 'rounded=1;whiteSpace=wrap;html=1;' + FONT
C = dict(cloud='fillColor=#E1D5E7;strokeColor=#9673A6;', fog='fillColor=#D5E8D4;strokeColor=#82B366;',
         edge='fillColor=#FFE6CC;strokeColor=#D79B00;', ctrl='fillColor=#F5F5F5;strokeColor=#666666;',
         scale='fillColor=#FFFFFF;strokeColor=#666666;dashed=1;', gw='fillColor=#DAE8FC;strokeColor=#6C8EBF;',
         pi='fillColor=#FFE6CC;strokeColor=#D79B00;dashed=1;')
NET = 'rounded=0;whiteSpace=wrap;html=1;fontStyle=1;' + FONT
SW = 210; SH = 64

def vm(parent, col, row, name, spec, role, kind, x0=14, y0=36, dx=226, dy=78):
    lab = f'<b>{name}</b><br>{spec}<br><i>{role}</i>'
    return box(x0 + col * dx, y0 + row * dy, SW, SH, lab, VM + C[kind], parent)

# ------------------------------------------------------------------ title
box(40, 10, 1560, 40, '<b>OptimusDB evaluation testbed — three sites, three hypervisors</b><br><font style="font-size:11px">Every agent VM runs one instance of each system under test (only one active per run) · tc/netem and iptables on the bench interface · chrony time sync · Prometheus node_exporter + cAdvisor</font>',
    'text;html=1;align=center;verticalAlign=middle;fontSize=16;' )

# ------------------------------------------------------------------ WAN
wan = box(340, 70, 960, 50, '<b>WAN: WireGuard full mesh between site gateways</b> (Internet / GÉANT) — record measured RTT, jitter and loss per link; netem adds delay only up to the target profile',
          NET + 'fillColor=#DAE8FC;strokeColor=#6C8EBF;rounded=1;')

SY = 150; SWD = 500; SHT = 640
sites = {}
# ------------------------------------------------------------------ Site A cloud
sA = box(40, SY, SWD, SHT, 'Site A — Cloud tier (data centre)', SITE + 'fillColor=#FBF8FD;strokeColor=#9673A6;')
hA = box(10, 40, 480, 400, 'Hypervisor A  ·  ≥ 32 cores · 96 GB RAM · 1 TB SSD', HV, sA)
gA = vm(hA, 0, 0, 'gw-a', '2 vCPU · 2 GB · 20 GB', 'WireGuard / router, WAN shaping', 'gw')
vm(hA, 1, 0, 'monitor', '2 vCPU · 8 GB · 200 GB', 'Prometheus, logs, results archive', 'ctrl')
vm(hA, 0, 1, 'cloud-1', '4 vCPU · 16 GB · 100 GB', 'agent (cloud)', 'cloud')
vm(hA, 1, 1, 'cloud-2', '4 vCPU · 16 GB · 100 GB', 'agent (cloud)', 'cloud')
vm(hA, 0, 2, 'loadgen', '4 vCPU · 8 GB · 100 GB', 'optimusdb-bench harness (clients)', 'ctrl')
box(14, 36 + 3 * 78, 436, SH, '<b>scale-a</b> (E8 only)<br>16 vCPU · 32 GB · 200 GB<br><i>up to 28 container agents for 16–64-agent runs</i>', VM + C['scale'], hA)
bA = box(10, 455, 480, 34, 'bench LAN A (VLAN 10) — experiment traffic', NET + 'fillColor=#FFFFFF;strokeColor=#6C8EBF;', sA)
mA = box(10, 498, 480, 34, 'mgmt LAN A (VLAN 20) — SSH, Prometheus, reset hooks', NET + 'fillColor=#FFFFFF;strokeColor=#999999;dashed=1;', sA)
box(10, 545, 480, 82, '• Client traffic originates here (loadgen never runs an agent)<br>• No CPU/RAM overcommit; vCPUs pinned<br>• Corrosion, Gun.js, Autobase, Iroh docs and OpenDHT installed on every agent VM next to OptimusDB; only the system under test runs',
    'text;html=1;align=left;verticalAlign=top;fontSize=10;spacingLeft=4;', sA)

# ------------------------------------------------------------------ Site B fog
sB = box(570, SY, SWD, SHT, 'Site B — Fog tier (regional site)', SITE + 'fillColor=#F7FBF6;strokeColor=#82B366;')
hB = box(10, 40, 480, 400, 'Hypervisor B  ·  ≥ 28 cores · 64 GB RAM · 1 TB SSD', HV, sB)
gB = vm(hB, 0, 0, 'gw-b', '2 vCPU · 2 GB · 20 GB', 'WireGuard / router, WAN shaping', 'gw')
vm(hB, 0, 1, 'fog-1', '4 vCPU · 8 GB · 256 GB', 'agent (fog)', 'fog')
vm(hB, 1, 1, 'fog-2', '4 vCPU · 8 GB · 256 GB', 'agent (fog)', 'fog')
box(14, 36 + 2 * 78, 436, SH, '<b>scale-b</b> (E8 only)<br>16 vCPU · 32 GB · 200 GB<br><i>up to 28 container agents for 16–64-agent runs</i>', VM + C['scale'], hB)
box(14, 36 + 3 * 78 + 6, 436, 70, '<i>Spare capacity: second load generator for the trace replay (E6) or larger E8 runs</i>',
    'rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=none;strokeColor=#B3B3B3;fontSize=10;fontColor=#666666;', hB)
bB = box(10, 455, 480, 34, 'bench LAN B (VLAN 10) — experiment traffic', NET + 'fillColor=#FFFFFF;strokeColor=#6C8EBF;', sB)
mB = box(10, 498, 480, 34, 'mgmt LAN B (VLAN 20)', NET + 'fillColor=#FFFFFF;strokeColor=#999999;dashed=1;', sB)
box(10, 545, 480, 82, '• Fog agents aggregate regional data (default 8-agent cluster: 2 of 8)<br>• Holds the second half of the E8 container agents<br>• Partition 4|4 in E5 = Site A ∪ part of B vs rest (iptables on bench LANs)',
    'text;html=1;align=left;verticalAlign=top;fontSize=10;spacingLeft=4;', sB)

# ------------------------------------------------------------------ Site C edge
sC = box(1100, SY, SWD, SHT, 'Site C — Edge tier (lab / field site)', SITE + 'fillColor=#FFFBF5;strokeColor=#D79B00;')
hC = box(10, 40, 480, 270, 'Hypervisor C  ·  ≥ 24 cores · 32 GB RAM · 500 GB SSD', HV, sC)
gC = vm(hC, 0, 0, 'gw-c', '2 vCPU · 2 GB · 20 GB', 'WireGuard / router, WAN shaping', 'gw')
vm(hC, 0, 1, 'edge-1', '4 vCPU (capped) · 4 GB · 32 GB', 'agent (edge, emulated)', 'edge')
vm(hC, 1, 1, 'edge-2', '4 vCPU (capped) · 4 GB · 32 GB', 'agent (edge, emulated)', 'edge')
vm(hC, 0, 2, 'edge-3', '4 vCPU (capped) · 4 GB · 32 GB', 'agent (edge, emulated)', 'edge')
vm(hC, 1, 2, 'edge-4', '4 vCPU (capped) · 4 GB · 32 GB', 'agent (edge, emulated)', 'edge')
pis = box(10, 322, 480, 118, '', 'rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;fillColor=#FFF7EC;strokeColor=#D79B00;dashed=1;', sC)
box(8, 6, 300, 20, '<b>Physical edge devices (E4 and edge realism)</b>', 'text;html=1;align=left;fontSize=11;', pis)
for k in range(4):
    box(8 + k * 116, 32, 106, 50, f'<b>rpi-{k + 1}</b><br>Raspberry Pi 4 · 4 GB', VM + C['pi'] + 'fontSize=10;', pis)
box(8, 88, 464, 24, 'USB power meter on each Pi (optional energy figures) · same bench VLAN as the edge VMs',
    'text;html=1;align=left;fontSize=10;fontColor=#666666;', pis)
bC = box(10, 455, 480, 34, 'bench LAN C (VLAN 10) — experiment traffic', NET + 'fillColor=#FFFFFF;strokeColor=#6C8EBF;', sC)
mC = box(10, 498, 480, 34, 'mgmt LAN C (VLAN 20)', NET + 'fillColor=#FFFFFF;strokeColor=#999999;dashed=1;', sC)
box(10, 545, 480, 82, '• Edge VMs are CPU-capped (≈ 1/3 host core per vCPU) for E1–E3 and E5–E10<br>• E4 (resource cost) runs on the four real Raspberry Pis<br>• Churn in E9: edge agents leave / join every 30 s',
    'text;html=1;align=left;verticalAlign=top;fontSize=10;spacingLeft=4;', sC)

# ------------------------------------------------------------------ links
WANE = 'endArrow=none;html=1;strokeWidth=3;strokeColor=#6C8EBF;'
edge(gA, wan, 'A↔B: target 20 ms / 100 Mbit/s', WANE + 'fontSize=10;')
edge(gB, wan, 'B↔C: target 50 ms / 10 Mbit/s', WANE + 'fontSize=10;')
edge(gC, wan, 'A↔C: target 70 ms / 10 Mbit/s', WANE + 'fontSize=10;')
for h, b, m in [(hA, bA, mA), (hB, bB, mB), (hC, bC, mC)]:
    edge(h, b, '', 'endArrow=none;html=1;strokeWidth=2;strokeColor=#6C8EBF;')
edge(pis, bC, '', 'endArrow=none;html=1;strokeWidth=2;strokeColor=#6C8EBF;dashed=1;')

# ------------------------------------------------------------------ legend
lg = box(40, 805, 1560, 150, '', 'rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;fillColor=#FFFFFF;strokeColor=#CCCCCC;')
box(10, 6, 200, 20, '<b>Legend and totals</b>', 'text;html=1;align=left;fontSize=12;', lg)
items = [('cloud', 'Cloud agent VM'), ('fog', 'Fog agent VM'), ('edge', 'Edge agent VM (CPU-capped)'), ('pi', 'Physical Raspberry Pi 4'),
         ('ctrl', 'Control VM (loadgen, monitor)'), ('gw', 'Site gateway (WireGuard)'), ('scale', 'Scale host, E8 only')]
for k, (kind, lab) in enumerate(items):
    box(10 + k * 220, 34, 26, 18, '', 'rounded=1;html=1;' + C[kind], lg)
    box(42 + k * 220, 32, 175, 22, lab, 'text;html=1;align=left;fontSize=10;', lg)
box(10, 64, 1540, 80,
    '<b>VMs:</b> 15 in total — 8 agents (2 cloud, 2 fog, 4 edge), loadgen, monitor, 3 site gateways, 2 scale hosts (powered on for E8 only). Plus 4 physical Raspberry Pi 4.<br>'
    '<b>Network:</b> bench VLAN per site joined into one routed experiment network through the WireGuard mesh; separate management VLAN so fault injection never cuts the harness off.<br>'
    '<b>Emulation:</b> measure the real inter-site RTT/jitter/loss first; netem on each agent adds only the difference to the target profile (cloud↔cloud 5 ms, cloud↔fog 20 ms, fog↔edge 50 ms, edge↔edge 2 ms) and the real values are reported in Section 8.1.<br>'
    '<b>Rules:</b> no CPU/RAM overcommit, pinned vCPUs, chrony on every VM (same NTP source), fresh deployment (reset hook) before every run.',
    'text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=10;', lg)

xml = ('<mxfile host="app.diagrams.net"><diagram id="testbed" name="OptimusDB 3-site testbed"><mxGraphModel dx="1600" dy="1000" grid="1" gridSize="10" '
       'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" pageHeight="1000" math="0" shadow="0">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + ''.join(cells) + '</root></mxGraphModel></diagram></mxfile>')
open(OUT, 'w').write(xml)
print('saved', OUT, len(cells), 'cells')
