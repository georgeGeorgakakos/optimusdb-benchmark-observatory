"""Host control agent (one per host, port 9100 on the WireGuard overlay only).

Used by the bench harness (bench/cluster.py, bench/faults.py, bench/observe.py) to drive this host:
  GET  /health                     liveness
  GET  /time                       host clock (for clock-offset logging)
  GET  /status                     state of the odb-* containers
  POST /system/<sys>/start {env}   write /runtime/<sys>.env and (re)start odb-<sys>
  POST /system/<sys>/stop          stop odb-<sys>
  POST /system/<sys>/wipe          stop odb-<sys> and delete its data volume contents
  POST /systems/stop-all           stop every data store on this host
  GET  /stats/<container>          docker stats (CPU %, memory MB) + data size (MB) + overlay bytes
  GET  /logs/<sys>?tail=N          container logs
  POST /exec {cmd}                 run a command in this host's network namespace (tc, iptables, ping)
Every request must carry the header  x-token: <AGENT_TOKEN>  (from the host's .env).
"""
import json, os, re, shlex, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

TOKEN = os.environ.get("AGENT_TOKEN", "")
PREFIX = os.environ.get("CONTAINER_PREFIX", "odb-")      # single-machine mode: odb-<host>-<system>
IFACE = os.environ.get("IFACE", "wg0")                    # overlay interface (wg0) or docker network (eth0)
SYSTEMS = ["optimusdb", "corrosion", "gun", "autobase", "iroh", "opendht"]
VOLUMES = {"optimusdb": ["/volumes/optimusdb-root", "/volumes/optimusdb-data"], "corrosion": ["/volumes/corrosion"],
           "gun": ["/volumes/gun"], "autobase": ["/volumes/autobase"], "iroh": ["/volumes/iroh"], "opendht": []}
LOCK = threading.Lock()


def run(cmd, timeout=120):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
    return {"rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def container(sysid): return f"{PREFIX}{sysid}"


def resolve(name):
    """Accept a system id, 'odb-<system>' (as the harness sends) or a full container name."""
    if name in SYSTEMS: return name, container(name)
    if name.startswith("odb-") and name[4:] in SYSTEMS: return name[4:], container(name[4:])
    return name.replace(PREFIX, ""), name


def running(name):
    r = run(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return r["rc"] == 0 and r["stdout"].strip() == "true"


def write_env(sysid, env):
    os.makedirs("/runtime", exist_ok=True)
    with open(f"/runtime/{sysid}.env", "w") as f:
        for k, v in (env or {}).items():
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", k): raise ValueError(f"bad env name {k}")
            f.write(f"{k}={shlex.quote(str(v))}\n")


def stop(sysid):
    return run(["docker", "stop", "-t", "15", container(sysid)])


def start(sysid, env):
    with LOCK:
        write_env(sysid, env)
        if running(container(sysid)): stop(sysid)
        r = run(["docker", "start", container(sysid)])
        if r["rc"] != 0: raise RuntimeError(r["stderr"].strip() or "docker start failed")
    return {"started": container(sysid)}


def wipe(sysid):
    stop(sysid)
    for v in VOLUMES[sysid]:
        run(f"find {shlex.quote(v)} -mindepth 1 -maxdepth 1 -exec rm -rf {{}} +")
    if os.path.exists(f"/runtime/{sysid}.env"): open(f"/runtime/{sysid}.env", "w").close()
    return {"wiped": sysid}


def stop_all():
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda s: stop(s) if running(container(s)) else None, SYSTEMS))
    return {"stopped": SYSTEMS}


def to_mb(s):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)", s.strip())
    if not m: return None
    v, u = float(m.group(1)), m.group(2)
    return round(v * {"B": 1 / 2**20, "KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024, "TiB": 2**20}.get(u, 1), 2)


def stats(name):
    sysid, name = resolve(name)
    r = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", name], timeout=30)
    out = {"container": name, "t": time.time()}
    if r["rc"] == 0 and r["stdout"].strip():
        js = json.loads(r["stdout"].strip().splitlines()[0])
        out["cpu_pct"] = float(js.get("CPUPerc", "0%").rstrip("%") or 0)
        out["mem_mb"] = to_mb(js.get("MemUsage", "0B / 0B").split("/")[0])
    vols = VOLUMES.get(sysid, [])
    if vols:
        du = run("du -sm " + " ".join(shlex.quote(v) for v in vols) + " 2>/dev/null | awk '{s+=$1} END {print s+0}'")
        out["disk_mb"] = float(du["stdout"].strip() or 0)
    try:
        rx = int(open(f"/sys/class/net/{IFACE}/statistics/rx_bytes").read()); tx = int(open(f"/sys/class/net/{IFACE}/statistics/tx_bytes").read())
        out["net_bytes"] = rx + tx
    except OSError:
        out["net_bytes"] = None
    return out


def status():
    r = run(["docker", "ps", "-a", "--filter", f"name={PREFIX}", "--format", "{{.Names}}\t{{.Status}}"])
    return {"host": os.environ.get("HOST_NAME"), "role": os.environ.get("ROLE"), "overlay_ip": os.environ.get("OVERLAY_IP"),
            "containers": dict(l.split("\t", 1) for l in r["stdout"].splitlines() if "\t" in l)}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _auth(self):
        if TOKEN and self.headers.get("x-token") != TOKEN:
            self._send(401, {"error": "bad token"}); return False
        return True

    def log_message(self, fmt, *args): pass

    def do_GET(self):
        if not self._auth(): return
        u = urlparse(self.path); p = u.path.strip("/").split("/")
        try:
            if p == ["health"]: return self._send(200, {"ok": True})
            if p == ["time"]: return self._send(200, {"t": time.time()})
            if p == ["status"]: return self._send(200, status())
            if len(p) == 2 and p[0] == "stats": return self._send(200, stats(p[1]))
            if len(p) == 2 and p[0] == "logs" and p[1] in SYSTEMS:
                tail = parse_qs(u.query).get("tail", ["200"])[0]
                return self._send(200, run(["docker", "logs", "--tail", tail, container(p[1])]))
            self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})

    def do_POST(self):
        if not self._auth(): return
        p = urlparse(self.path).path.strip("/").split("/")
        try:
            b = self._body()
            if p == ["exec"]: return self._send(200, run(b["cmd"], timeout=int(b.get("timeout", 120))))
            if p == ["systems", "stop-all"]: return self._send(200, stop_all())
            if len(p) == 3 and p[0] == "system" and p[1] in SYSTEMS:
                act = p[2]
                if act == "start": return self._send(200, start(p[1], b.get("env")))
                if act == "stop": return self._send(200, stop(p[1]))
                if act == "wipe": return self._send(200, wipe(p[1]))
            self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", "9100"))
    print(f"agent on :{port} host={os.environ.get('HOST_NAME')} overlay={os.environ.get('OVERLAY_IP')}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
