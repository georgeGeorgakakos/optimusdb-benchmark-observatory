"""Architecture diagram of the single-machine testbed (draw.io / diagrams.net XML).

    python tools/build_drawio_local.py [out.drawio] [preview.png]

Hosts, IPs, ports and link profiles match tools/gen_local.py defaults and the Table 7 profiles in
the generated testbed.yaml. The optional PNG is a rough layout preview (not a draw.io rendering).
"""
import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else "OptimusDB_Testbed_SingleMachine.drawio"
PNG = sys.argv[2] if len(sys.argv) > 2 else None

cells, boxes, lines = [], [], []
_id = [1]
def nid():
    _id[0] += 1; return f"c{_id[0]}"

def box(x, y, w, h, label, style, parent="1", ax=0, ay=0, fill="#ffffff"):
    i = nid()
    cells.append(f'<mxCell id="{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    boxes.append((ax + x, ay + y, w, h, label, fill))
    return i, (ax + x, ay + y, w, h)

def edge(src, tgt, label, style, pts=None):
    i = nid()
    geo = '<mxGeometry relative="1" as="geometry">'
    if pts:
        geo += '<Array as="points">' + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in pts) + '</Array>'
    geo += '</mxGeometry>'
    cells.append(f'<mxCell id="{i}" value="{escape(label)}" style="{style}" edge="1" parent="1" source="{src[0]}" target="{tgt[0]}">{geo}</mxCell>')
    lines.append((src[1], tgt[1], label, "dashed=1" in style))
    return i

F = "fontFamily=Helvetica;"
GROUP = "rounded=1;whiteSpace=wrap;html=1;container=1;collapsible=0;verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontStyle=1;arcSize=2;" + F
COL = {"cloud": ("#E1D5E7", "#9673A6", "#F7F2FA"), "fog": ("#D5E8D4", "#82B366", "#F3F9F2"),
       "edge": ("#FFE6CC", "#D79B00", "#FFF8EF")}
DS = [("optimusdb", ":8089 HTTP · :4001 libp2p"), ("corrosion", ":8080 API · :8787 gossip"), ("gun", ":7004 API · :8765 relay"),
      ("autobase", ":7005 API · :7305 repl."), ("iroh", ":7006 API · QUIC"), ("opendht", ":8000 proxy · :4222 DHT")]
LIM = {"cloud": "1.5 CPU / 3 GB", "fog": "1.5 CPU / 3 GB", "edge": "1 CPU / 2 GB"}

HW, HH = 330, 262
# ------------------------------------------------------------------ frame
W, H = 1900, 1330
box(20, 10, W - 40, 44, "<b>OptimusDB evaluation testbed — single machine (Docker Desktop on Windows)</b><br>"
    "<font style='font-size:11px'>8 emulated hosts + bench on one private Docker bridge network · only the system under test runs · "
    "Table 7 links emulated with tc/netem on each host's eth0 · partitions with iptables</font>",
    "text;html=1;fillColor=none;strokeColor=none;align=center;verticalAlign=middle;fontSize=16;" + F)
pc, pcg = box(20, 64, W - 40, H - 84, "Windows PC  ›  Docker Desktop (WSL2 VM, e.g. 12 CPUs / 25 GB from .wslconfig)",
              GROUP + "fontSize=13;fillColor=#F5F5F5;strokeColor=#666666;", fill="#F5F5F5")
PX, PY = pcg[0], pcg[1]

# ------------------------------------------------------------------ bench
bench, bg = box(20, 50, 300, 330, "bench  ·  10.88.0.2", GROUP + "fontSize=12;fillColor=#DAE8FC;strokeColor=#6C8EBF;", pc, PX, PY, "#DAE8FC")
BX, BY = bg[0], bg[1]
box(12, 32, 276, 70, "<b>odb-bench</b><br>optimusdb-bench harness<br><i>open-loop load generator, cluster control,<br>netem / partitions, result CSVs</i>",
    "rounded=1;whiteSpace=wrap;html=1;fontSize=10;fillColor=#FFFFFF;strokeColor=#6C8EBF;" + F, bench, BX, BY)
box(12, 112, 276, 100, "<b>Bind mounts (Windows folders)</b><br>out-local\\config → /config (testbed.yaml)<br>results → /results (E*_raw.csv, ops, logs)<br>trace → /trace (E6 trace.jsonl)",
    "rounded=1;whiteSpace=wrap;html=1;fontSize=10;align=left;spacingLeft=6;fillColor=#FFFFFF;strokeColor=#999999;dashed=1;" + F, bench, BX, BY)
box(12, 222, 276, 96, "<b>Talks to every host</b><br>• control: HTTP :9100 (agent, x-token)<br>• data: system API ports (load, queries)<br>• load enters at cloud-a (edge-a for E4)",
    "rounded=1;whiteSpace=wrap;html=1;fontSize=10;align=left;spacingLeft=6;fillColor=#FFFFFF;strokeColor=#999999;" + F, bench, BX, BY)

# ------------------------------------------------------------------ bridge network (vertical bus)
bus, busg = box(340, 50, 26, 2 * (HH + 76) + HH + 46 - 20, "", "rounded=0;whiteSpace=wrap;html=1;fillColor=#6C8EBF;strokeColor=#3D5A80;", pc, PX, PY, "#6C8EBF")
box(250, 2 * (HH + 76) + HH + 46 + 36, 200, 34, "<b>Docker bridge network <i>odbnet</i></b><br>10.88.0.0/24 · gateway 10.88.0.1",
    "text;html=1;fillColor=none;strokeColor=none;align=center;fontSize=10;" + F, pc, PX, PY)

# ------------------------------------------------------------------ hosts
def host(parent, pg, x, y, name, ip, tier):
    fill, stroke, _ = COL[tier]
    hb, hg = box(x, y, HW, HH, f"{name}  ·  {ip}", GROUP + f"fontSize=12;fillColor=#FFFFFF;strokeColor={stroke};", parent, pg[0], pg[1])
    gx, gy = hg[0], hg[1]
    box(10, 28, HW - 20, 30, f"<b>odb-{name}-net</b>  —  own network namespace · eth0 {ip} · tc netem · iptables",
        f"rounded=1;whiteSpace=wrap;html=1;fontSize=9;fillColor={fill};strokeColor={stroke};" + F, hb, gx, gy, fill)
    box(10, 63, HW - 20, 26, f"<b>odb-{name}-agent</b>  :9100  —  start / stop / wipe / stats via docker.sock",
        "rounded=1;whiteSpace=wrap;html=1;fontSize=9;fillColor=#F5F5F5;strokeColor=#666666;" + F, hb, gx, gy, "#F5F5F5")
    bw = (HW - 20 - 2 * 6) / 3
    for k, (s, ports) in enumerate(DS):
        r, c = divmod(k, 3)
        box(10 + c * (bw + 6), 96 + r * 58, bw, 52, f"<b>odb-{name}-{s}</b><br><font style='font-size:8px'>{ports}</font>",
            "rounded=1;whiteSpace=wrap;html=1;fontSize=9;dashed=1;fillColor=#FFFFFF;strokeColor=#999999;" + F, hb, gx, gy)
    box(10, 214, HW - 20, 40, f"data stores share the net namespace (same IP) · <b>one runs at a time</b><br>limit per data store: <b>{LIM[tier]}</b> · named volumes per system",
        "text;html=1;fillColor=none;strokeColor=none;align=left;verticalAlign=top;fontSize=9;spacingLeft=2;" + F, hb, gx, gy)
    return hb, hg

TX = 400
def tier_group(y, tier, title, names):
    fill, stroke, bgc = COL[tier]
    w = 20 + len(names) * (HW + 16) + 4
    g, gg = box(TX, y, w, HH + 46, title, GROUP + f"fontSize=12;fillColor={bgc};strokeColor={stroke};", pc, PX, PY, bgc)
    hs = []
    for k, (n, ip) in enumerate(names):
        hs.append(host(g, gg, 12 + k * (HW + 16), 34, n, ip, tier))
    return (g, gg), hs

cloud, ch = tier_group(30, "cloud", "Cloud tier  —  cloud ↔ cloud: 5 ms ± 1 ms · 0 % loss · 1 Gbit/s",
                       [("cloud-a", "10.88.0.11"), ("cloud-b", "10.88.0.12")])
fog, fh = tier_group(30 + HH + 76, "fog", "Fog tier  —  fog ↔ fog: 2 ms ± 0.5 ms · 0 % · 1 Gbit/s (derived)",
                     [("fog-a", "10.88.0.13"), ("fog-b", "10.88.0.14")])
edgeg, eh = tier_group(30 + 2 * (HH + 76), "edge", "Edge tier  —  edge ↔ edge: 2 ms ± 0.5 ms · 0 % · 100 Mbit/s  (Raspberry-Pi-sized containers)",
                      [("edge-a", "10.88.0.15"), ("edge-b", "10.88.0.16"), ("edge-c", "10.88.0.17"), ("edge-d", "10.88.0.18")])

# ------------------------------------------------------------------ physical attachment to the bridge
PHY = "endArrow=none;html=1;strokeWidth=3;strokeColor=#6C8EBF;edgeStyle=orthogonalEdgeStyle;exitX=0;exitY=0.5;entryX=1;entryY=0.5;"
edge((bench, bg), (bus, busg), "", PHY.replace("exitX=0;", "exitX=1;").replace("entryX=1;", "entryX=0;"))
for g, lab in ((cloud, "cloud-a .11 · cloud-b .12"), (fog, "fog-a .13 · fog-b .14"), (edgeg, "edge-a .15 · b .16 · c .17 · d .18")):
    edge(g, (bus, busg), lab, PHY + "fontSize=9;labelBackgroundColor=#F5F5F5;")

# ------------------------------------------------------------------ emulated links between tiers (Table 7)
LNK = ("startArrow=classic;endArrow=classic;html=1;dashed=1;strokeWidth=2;fontSize=10;labelBackgroundColor=#FFFFFF;"
       "edgeStyle=orthogonalEdgeStyle;rounded=1;" + F)
cy, fy, ey = PY + 30, PY + 30 + (HH + 76), PY + 30 + 2 * (HH + 76)
gh = HH + 46
gx0 = PX + TX; wcf = 20 + 2 * (HW + 16) + 4; wed = 20 + 4 * (HW + 16) + 4
xr1, xr2, xr3 = gx0 + wcf + 40, gx0 + wcf + 140, gx0 + wcf + 300
edge(cloud, fog, "cloud ↔ fog<br>20 ms ± 4 · 0.1 % loss<br>100 Mbit/s",
     LNK + "strokeColor=#9673A6;exitX=1;exitY=0.6;entryX=1;entryY=0.3;", pts=[(xr1, cy + 0.6 * gh), (xr1, fy + 0.3 * gh)])
edge(fog, edgeg, "fog ↔ edge<br>50 ms ± 10 · 0.5 % loss<br>10 Mbit/s",
     LNK + f"strokeColor=#82B366;exitX=1;exitY=0.75;entryX={(xr2 - gx0) / wed:.3f};entryY=0;", pts=[(xr2, fy + 0.75 * gh)])
edge(cloud, edgeg, "cloud ↔ edge (derived)<br>70 ms ± 11 · 0.6 % loss<br>10 Mbit/s",
     LNK + f"strokeColor=#D79B00;exitX=1;exitY=0.25;entryX={(xr3 - gx0) / wed:.3f};entryY=0;", pts=[(xr3, cy + 0.25 * gh)])

# ------------------------------------------------------------------ legend
lg, lgg = box(20, 400, 300, 470, "Legend and notes", GROUP + "fontSize=12;fillColor=#FFFFFF;strokeColor=#CCCCCC;", pc, PX, PY)
items = [("#6C8EBF", "solid", "attachment to the Docker bridge (all traffic)"),
         ("#9673A6", "dashed", "emulated link profile (tc netem on eth0,<br>per destination IP)"),
         ("#999999", "dashed-box", "data-store container (created; started<br>only for the system under test)")]
for k, (c, kind, txt) in enumerate(items):
    st = f"rounded=1;html=1;fillColor=#FFFFFF;strokeColor={c};" + ("dashed=1;" if "dashed" in kind else "") + ("strokeWidth=2;" if kind != "dashed-box" else "")
    box(12, 34 + k * 46, 30, 18, "", st, lg, lgg[0], lgg[1])
    box(50, 26 + k * 46, 240, 40, txt, "text;html=1;fillColor=none;strokeColor=none;align=left;verticalAlign=middle;fontSize=10;" + F, lg, lgg[0], lgg[1])
box(12, 176, 276, 284,
    "<b>Per run (harness → agents)</b><br>1. stop all data stores on all hosts<br>2. wipe the system's volumes<br>3. start it on all 8 hosts and join:<br>"
    "&nbsp;&nbsp;OptimusDB libp2p connect · Corrosion gossip<br>&nbsp;&nbsp;bootstrap · Gun peers · Autobase TCP repl. +<br>&nbsp;&nbsp;writers · Iroh ticket · OpenDHT bootstrap<br>"
    "4. smoke test: write on cloud-a, read on edge-d<br>5. load / faults / sampling, then results CSV<br><br>"
    "<b>Faults</b>: E5 partitions = iptables DROP between<br>host groups (e.g. cloud+fog | edge); bench is never<br>blocked.<br><br>"
    "<b>Containers</b>: 17 running (bench, 8 × net, 8 ×<br>agent) · 48 created (8 hosts × 6 data stores).",
    "text;html=1;fillColor=none;strokeColor=none;align=left;verticalAlign=top;fontSize=10;spacingLeft=4;whiteSpace=wrap;" + F, lg, lgg[0], lgg[1])

xml = ('<mxfile host="app.diagrams.net"><diagram id="local" name="Single-machine testbed"><mxGraphModel dx="1900" dy="1330" grid="1" gridSize="10" '
       'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1920" pageHeight="1360" math="0" shadow="0">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + '</root></mxGraphModel></diagram></mxfile>')
open(OUT, "w", encoding="utf-8").write(xml)
print("saved", OUT, len(cells), "cells")

if PNG:   # rough preview of the layout
    import re
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    for x, y, w, h, label, fill in boxes:
        d.rectangle([x, y, x + w, y + h], outline="#555555", fill=fill if fill != "#ffffff" else None)
        t = re.sub(r"<br\s*/?>", "\n", label); t = re.sub(r"<[^>]+>", "", t).replace("&nbsp;", " ")
        d.multiline_text((x + 4, y + 3), "\n".join(l[:70] for l in t.split("\n")[:6]), fill="black")
    for (a, b, label, dashed) in lines:
        ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2; bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
        d.line([ax, ay, bx, by], fill="#3366aa" if not dashed else "#aa3366", width=2)
        if label: d.text(((ax + bx) / 2, (ay + by) / 2), label, fill="#aa3366")
    im.save(PNG); print("preview", PNG)
