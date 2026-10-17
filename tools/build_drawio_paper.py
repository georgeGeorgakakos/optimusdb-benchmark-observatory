"""Compact black-and-white architecture figure of the single-machine testbed, for the paper.

    python tools/build_drawio_paper.py [out.drawio]

Same hosts, IPs, ports, limits and Table 7 links as tools/gen_local.py (defaults used with
deploy-local -CpusCloud 1.5 -CpusFog 1.5 -CpusEdge 1). No colours: links are told apart by line style.
"""
import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else "OptimusDB_Testbed_Paper.drawio"
FONT = "fontFamily=Helvetica;fontColor=#000000;"
BOX = "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=1;" + FONT
GROUP = BOX + "verticalAlign=top;align=left;spacingLeft=8;spacingTop=2;container=1;collapsible=0;"
TEXT = "text;html=1;fillColor=none;strokeColor=none;whiteSpace=wrap;" + FONT
LINE = "endArrow=none;html=1;strokeColor=#000000;strokeWidth=1;rounded=0;" + FONT
LINK = ("endArrow=open;startArrow=open;endSize=6;startSize=6;dashed=1;dashPattern=6 3;html=1;strokeColor=#000000;"
        "strokeWidth=1;rounded=0;labelBackgroundColor=#FFFFFF;fontSize=9;" + FONT)

cells, nid = [], [1]


def new_id():
    nid[0] += 1
    return f"c{nid[0]}"


def vertex(x, y, w, h, label, style, parent="1"):
    i = new_id()
    cells.append(f'<mxCell id="{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def edge(points, label="", style=LINE):
    i = new_id()
    (sx, sy), (tx, ty), mid = points[0], points[-1], points[1:-1]
    pts = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in mid)
    cells.append(f'<mxCell id="{i}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" edge="1" parent="1">'
                 f'<mxGeometry relative="1" as="geometry"><mxPoint x="{sx}" y="{sy}" as="sourcePoint"/>'
                 f'<mxPoint x="{tx}" y="{ty}" as="targetPoint"/>' + (f'<Array as="points">{pts}</Array>' if pts else "") +
                 '</mxGeometry></mxCell>')
    return i


# outer frame
vertex(20, 20, 980, 455, "<b>Single Windows host · Docker Desktop (WSL2 VM)</b>",
       BOX + "verticalAlign=top;align=left;spacingLeft=8;spacingTop=4;fontSize=11;")

# tiers: (name, x, profile within tier, hosts, first IP)
TIERS = [("Cloud tier", 60, "5 ms ± 1 ms · 0 % loss · 1 Gbit/s", ["cloud-a", "cloud-b"], 11),
         ("Fog tier", 390, "2 ms ± 0.5 ms · 0 % loss · 1 Gbit/s (derived)", ["fog-a", "fog-b"], 13),
         ("Edge tier", 720, "2 ms ± 0.5 ms · 0 % loss · 100 Mbit/s", ["edge-a", "edge-b", "edge-c", "edge-d"], 15)]
TOP, HW, HH = 90, 105, 44
bottoms = {}
for name, gx, prof, hosts, ip0 in TIERS:
    rows = (len(hosts) + 1) // 2
    gh = 40 + rows * (HH + 10)
    g = vertex(gx, TOP, 240, gh, f'<b>{name}</b><br><font style="font-size:9px">{prof}</font>', GROUP + "fontSize=11;")
    for k, h in enumerate(hosts):
        vertex(10 + (k % 2) * (HW + 10), 40 + (k // 2) * (HH + 10), HW, HH,
               f"<b>{h}</b><br>10.88.0.{ip0 + k}", BOX + "fontSize=10;", g)
    bottoms[name] = (gx + 120, TOP + gh, ip0, len(hosts))

# links between tiers (Table 7)
y = TOP + 62
edge([(300, y), (390, y)], "20 ms ± 4 ms<br>0.1 % · 100 Mbit/s", LINK)
edge([(630, y), (720, y)], "50 ms ± 10 ms<br>0.5 % · 10 Mbit/s", LINK)
edge([(180, TOP), (180, 58), (840, 58), (840, TOP)], "cloud–edge (derived): 70 ms ± 11 ms · 0.6 % · 10 Mbit/s", LINK)

# Docker bridge
BY = 278
vertex(40, BY, 940, 18, "Docker bridge network <i>odbnet</i> · 10.88.0.0/24", BOX + "fontSize=10;")
for name, (cx, by, ip0, n) in bottoms.items():
    edge([(cx, by), (cx, BY)], f".{ip0}–.{ip0 + n - 1}",
         LINE + "labelBackgroundColor=#FFFFFF;fontSize=9;")

# bench
vertex(40, 318, 175, 62, "<b>bench</b> · 10.88.0.2<br>load generator, cluster control,<br>netem / partitions, results",
       BOX + "fontSize=9;")
edge([(127, BY + 18), (127, 318)])

# legend
vertex(40, 392, 175, 70, "", BOX)
edge([(50, 410), (85, 410)])
vertex(90, 400, 120, 20, "attachment to the bridge", TEXT + "fontSize=9;")
edge([(50, 432), (85, 432)], "", LINK.replace("labelBackgroundColor=#FFFFFF;", ""))
vertex(90, 422, 120, 20, "emulated link (tc netem)", TEXT + "fontSize=9;")
vertex(46, 442, 165, 18, "tier header: link within the tier", TEXT + "fontSize=9;align=left;")

# inside one emulated host
ins = vertex(240, 318, 740, 144, "<b>Inside each emulated host</b> (one network namespace, one IP)",
             GROUP + "fontSize=10;")
vertex(10, 34, 125, 62, "<b>net</b><br>eth0 · host IP<br>tc netem · iptables", BOX + "fontSize=9;", ins)
vertex(145, 34, 120, 62, "<b>agent</b> :9100<br>start / stop / wipe<br>resource stats", BOX + "fontSize=9;", ins)
ds = vertex(275, 28, 455, 74, "data-store containers (only the system under test runs)",
            BOX + "dashed=1;verticalAlign=top;align=left;spacingLeft=6;fontSize=9;container=1;collapsible=0;", ins)
for k, (s, p) in enumerate([("OptimusDB", 8089), ("Corrosion", 8080), ("Gun.js", 7004),
                            ("Autobase", 7005), ("Iroh docs", 7006), ("OpenDHT", 8000)]):
    vertex(6 + k * 74, 24, 70, 40, f"{s}<br>:{p}", BOX + "fontSize=9;", ds)
vertex(10, 108, 720, 30, "Limit per data store: cloud and fog 1.5 CPU / 3 GB; edge 1 CPU / 2 GB. "
       "E5 partitions: iptables DROP between host groups (bench never blocked).", TEXT + "fontSize=9;align=left;", ins)

xml = ('<mxfile host="app.diagrams.net"><diagram id="testbed-paper" name="Testbed (paper)">'
       '<mxGraphModel dx="1000" dy="500" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
       'fold="1" page="1" pageScale="1" pageWidth="1020" pageHeight="500" math="0" shadow="0" background="#FFFFFF">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + '</root></mxGraphModel></diagram></mxfile>')
open(OUT, "w", encoding="utf-8").write(xml)
print("saved", OUT, len(cells), "cells")
