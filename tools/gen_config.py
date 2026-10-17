"""Generate per-host configuration bundles from hosts.csv.

    docker run --rm -v <deploy-dir>:/work -w /work odb-net:latest python3 tools/gen_config.py hosts.csv out

hosts.csv columns: name,role,lan_ip[,ds_cpus,ds_mem]
  role  = bench | cloud | fog | edge   (exactly one bench row)
  ds_cpus / ds_mem = per-container limits for the data stores on that host (default: none on cloud/fog,
                     4 CPUs and 4g on edge, i.e. Raspberry Pi 4 size, as in Table 7)

Output: out/<name>/.env, out/<name>/wg/wg0.conf for every host, and out/bench/config/testbed.yaml
for the harness. Keys are WireGuard X25519 keys generated with `wg genkey`; re-running keeps existing keys.
"""
import csv, json, os, secrets, subprocess, sys

PIN = {}
for line in open(os.path.join(os.path.dirname(__file__), "..", "versions.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); PIN[k] = v

src, out = sys.argv[1], sys.argv[2]
rows = [r for r in csv.DictReader(open(src)) if r.get("name") and not r["name"].startswith("#")]
roles = [r["role"].strip() for r in rows]
if roles.count("bench") != 1: sys.exit("hosts.csv needs exactly one row with role=bench")
for r in rows:
    if r["role"].strip() not in ("bench", "cloud", "fog", "edge"): sys.exit(f"bad role for {r['name']}")
    if r["name"].strip()[-1].isdigit():
        sys.exit(f"host name {r['name']} ends with a digit: OptimusDB treats such names as preferred coordinators; use e.g. cloud-a")

os.makedirs(out, exist_ok=True)
tokfile = os.path.join(out, ".agent_token")
token = open(tokfile).read().strip() if os.path.exists(tokfile) else secrets.token_hex(24)
open(tokfile, "w").write(token)

hosts, k = [], 0
for r in rows:
    role = r["role"].strip(); name = r["name"].strip()
    ip = "10.88.0.2" if role == "bench" else f"10.88.0.{11 + k}"
    if role != "bench": k += 1
    d = os.path.join(out, name); os.makedirs(os.path.join(d, "wg"), exist_ok=True)
    kf = os.path.join(d, "wg", "private.key")
    if not os.path.exists(kf):
        open(kf, "w").write(subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True).stdout.strip())
    priv = open(kf).read().strip()
    pub = subprocess.run(["wg", "pubkey"], input=priv, capture_output=True, text=True, check=True).stdout.strip()
    cpus = (r.get("ds_cpus") or "").strip() or ("4" if role == "edge" else "0")
    mem = (r.get("ds_mem") or "").strip() or ("4g" if role == "edge" else "0")
    hosts.append(dict(name=name, role=role, lan_ip=r["lan_ip"].strip(), ip=ip, priv=priv, pub=pub, cpus=cpus, mem=mem, dir=d))

# hosts sharing a machine (same LAN IP) need different WireGuard ports
seen = {}
for h in hosts:
    seen.setdefault(h["lan_ip"], 0); h["wg_port"] = 51820 + seen[h["lan_ip"]]; seen[h["lan_ip"]] += 1

for h in hosts:
    peers = "".join(f"\n[Peer]\n# {o['name']} ({o['role']})\nPublicKey = {o['pub']}\nAllowedIPs = {o['ip']}/32\n"
                    f"Endpoint = {o['lan_ip']}:{o['wg_port']}\nPersistentKeepalive = 15\n" for o in hosts if o is not h)
    open(os.path.join(h["dir"], "wg", "wg0.conf"), "w").write(
        f"# overlay of the OptimusDB evaluation testbed — host {h['name']} ({h['role']})\n[Interface]\n"
        f"PrivateKey = {h['priv']}\nAddress = {h['ip']}/24\nListenPort = {h['wg_port']}\nMTU = 1380\n{peers}")
    env = {"HOST_NAME": h["name"], "ROLE": h["role"], "OVERLAY_IP": h["ip"], "LAN_IP": h["lan_ip"], "WG_PORT": h["wg_port"],
           "AGENT_TOKEN": token, "DS_CPUS": h["cpus"], "DS_MEM": h["mem"], **PIN}
    open(os.path.join(h["dir"], ".env"), "w").write("".join(f"{a}={b}\n" for a, b in env.items()))
    os.chmod(os.path.join(h["dir"], "wg", "private.key"), 0o600)

agents = [h for h in hosts if h["role"] != "bench"]
first_of = lambda role: next((h for h in agents if h["role"] == role), agents[0])
P = {"optimusdb": 8089, "corrosion": 8080, "gun": 7004, "autobase": 7005, "iroh": 7006, "opendht": 8000}
TYPE = {"optimusdb": {"type": "optimusdb", "strategy": "LOCAL_THEN_REMOTE_MERGE"}, "corrosion": {"type": "corrosion"},
        "gun": {"type": "http", "name": "gun"}, "autobase": {"type": "http", "name": "autobase"},
        "iroh": {"type": "http", "name": "iroh"}, "opendht": {"type": "opendht"}}
c1, e1 = first_of("cloud"), first_of("edge")
cfg = {
    "seed": 20261101, "settle_s": 20,
    "run": {"rate": 50, "duration_s": 300, "warmup_s": 60, "poisson": True, "client_workers": 4},
    "data": {"records": 100000},
    "cluster": {"token": token, "hosts": [{"name": h["name"], "role": h["role"], "ip": h["ip"]} for h in hosts]},
    "agents": [f"http://{h['ip']}:8089" for h in agents],
    "initiators": {t: f"http://{first_of(t)['ip']}:8089" for t in ("cloud", "fog", "edge")},
    "links": {   # Table 7 of the paper; applied on wg0 by `bench.cluster netem`
        "cloud-cloud": {"delay_ms": 5, "jitter_ms": 1, "loss_pct": 0.0, "rate_mbit": 1000},
        "cloud-fog": {"delay_ms": 20, "jitter_ms": 4, "loss_pct": 0.1, "rate_mbit": 100},
        # derived (not in Table 7 yet): fog hosts share a regional site; cloud-edge traffic crosses the fog link
        "fog-fog": {"delay_ms": 2, "jitter_ms": 0.5, "loss_pct": 0.0, "rate_mbit": 1000},
        "fog-edge": {"delay_ms": 50, "jitter_ms": 10, "loss_pct": 0.5, "rate_mbit": 10},
        "cloud-edge": {"delay_ms": 70, "jitter_ms": 11, "loss_pct": 0.6, "rate_mbit": 10},
        "edge-edge": {"delay_ms": 2, "jitter_ms": 0.5, "loss_pct": 0.0, "rate_mbit": 100},
    },
    "systems": {s: dict(TYPE[s], base_url=f"http://{c1['ip']}:{P[s]}") for s in P},
    "replicas": {s: [f"http://{h['ip']}:{P[s]}" for h in agents] for s in P if s != "optimusdb"},
    "edge_override": {s: {"base_url": f"http://{e1['ip']}:{P[s]}"} for s in P},
    "e3_targets": [{"system": "optimusdb", "path": "crdt"}, {"system": "optimusdb", "path": "sqlite", "override": {"sql_tables": True}},
                   {"system": "corrosion", "path": "sql"}, {"system": "gun", "path": "client_filter"},
                   {"system": "autobase", "path": "range_client_filter"}, {"system": "iroh", "path": "prefix_client_filter"},
                   {"system": "opendht", "path": "key_only"}],
    "edge_systems": list(P),
    "reset": {s: "cluster" for s in P} | {f"{s}_edge": "cluster" for s in P},
}
bench_dir = [h for h in hosts if h["role"] == "bench"][0]["dir"]
os.makedirs(os.path.join(bench_dir, "config"), exist_ok=True)
# JSON is valid YAML, so the harness reads this file with yaml.safe_load
with open(os.path.join(bench_dir, "config", "testbed.yaml"), "w") as f:
    f.write("# generated by tools/gen_config.py from hosts.csv - edit hosts.csv and re-run instead of editing this file\n")
    json.dump(cfg, f, indent=2)
summary = [{k: h[k] for k in ("name", "role", "lan_ip", "ip", "wg_port", "cpus", "mem")} for h in hosts]
json.dump(summary, open(os.path.join(out, "hosts.json"), "w"), indent=2)
print(f"{'host':10} {'role':6} {'LAN IP':16} {'overlay':12} {'wg port':7} limits")
for h in summary: print(f"{h['name']:10} {h['role']:6} {h['lan_ip']:16} {h['ip']:12} {h['wg_port']:<7} cpus={h['cpus']} mem={h['mem']}")
print(f"bundles written to {out}/<host>/ ; harness config: {bench_dir}/config/testbed.yaml")
