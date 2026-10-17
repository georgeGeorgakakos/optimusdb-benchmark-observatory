"""Cluster control for the Docker Desktop (multi-host) deployment.

Every host runs a small control agent (optimusdb-deploy/images/agent) reachable on the WireGuard
overlay at http://<overlay-ip>:9100. This module starts, stops, wipes and joins one system across
all hosts, applies the Table 7 link profiles, and checks the overlay mesh.

    python -m bench.cluster status
    python -m bench.cluster mesh
    python -m bench.cluster deploy  <system> [--tier edge]
    python -m bench.cluster reset   <system> [--tier edge]      # stop everything, wipe, start, join, smoke test
    python -m bench.cluster stop    <system>
    python -m bench.cluster stop-all
    python -m bench.cluster netem | clear-netem
    python -m bench.cluster smoke   <system>

Only the system under test runs at any time: deploy/reset first stop every other data store on
every host, so the six systems never compete for CPU, memory or network.
"""
import argparse, asyncio, json, sys, time, uuid

import httpx
import yaml

from . import adapters as A, faults

SYSTEMS = ["optimusdb", "corrosion", "gun", "autobase", "iroh", "opendht"]
PORTS = {"optimusdb": 8089, "corrosion": 8080, "gun": 7004, "autobase": 7005, "iroh": 7006, "opendht": 8000}


def hosts_of(cfg, tier=None):
    hs = [h for h in cfg["cluster"]["hosts"] if h["role"] != "bench"]
    return [h for h in hs if tier in (None, h["role"])]


# ------------------------------------------------------------------ runtime settings of the systems
# OptimusDB defaults for the benchmark; testbed.yaml `optimusdb_runtime:` overrides any key (null removes it).
OPTIMUSDB_RUNTIME = {
    "log_level": "WARN",     # OPTIMUSDB_LOG_LEVEL: INFO lines are not written at all
    "gogc": 200,             # GOGC: garbage collection half as often as the Go default (100)
    "go_limits": True,       # GOMAXPROCS / GOMEMLIMIT from the container's CPU and memory limits
    "args": "-metrics=false",  # no periodic CPU/RAM sampling inside OptimusDB
    # IPFS: Ed25519 node key (GossipSub signatures ~1-2 ms each with RSA-2048, the profile's largest single CPU
    # item on the write path) and no DHT announcement of every written block (DHT traffic and its lock contention
    # were the largest share of CPU and waiting in the profile; the agents are connected directly, so bitswap
    # finds blocks without provider records)
    # OPTIMUSDB_IPFS_SYNC=false: no fsync per block / per store-head write, i.e. the durability of SQLite WAL with
    # synchronous=NORMAL, which is what Corrosion uses (corro-types/src/sqlite.rs at the pinned commit)
    # OPTIMUSDB_HEADS_INTERVAL / OPTIMUSDB_RECONNECT_INTERVAL: the build's defaults (10 s), written out so the report
    # lists them: heads re-announced when changed (at least every 6th interval) and lost peer connections re-dialled.
    "env": {"OPTIMUSDB_IPFS_KEY": "ed25519", "OPTIMUSDB_IPFS_PROVIDE": "false", "OPTIMUSDB_IPFS_SYNC": "false",
            "OPTIMUSDB_HEADS_INTERVAL": "10", "OPTIMUSDB_RECONNECT_INTERVAL": "10"},
}
# Other systems: same log level policy (warnings only). Iroh's wrapper defaults to warn, OpenDHT runs without -v,
# the Node.js wrappers log only start-up lines.
QUIET_ENV = {"corrosion": {"RUST_LOG": "warn"}}
AUTOBASE_INDEXERS = 3      # indexers among the Autobase writers (testbed.yaml `autobase_indexers` overrides)


def _mem_mib(mem):
    """'3g' / '2048m' / '1.5g' -> MiB (None if unknown)."""
    if mem is None: return None
    m = str(mem).strip().lower().rstrip("b")
    try:
        if m.endswith("g"): return int(float(m[:-1]) * 1024)
        if m.endswith("m"): return int(float(m[:-1]))
        if m.endswith("k"): return int(float(m[:-1]) / 1024)
        return int(float(m) / 1048576)
    except ValueError:
        return None


def optimusdb_runtime(cfg):
    rt = dict(OPTIMUSDB_RUNTIME)
    for k, v in (cfg.get("optimusdb_runtime") or {}).items():
        rt[k] = v
    return rt


def optimusdb_env(cfg, h):
    """Environment of the OptimusDB container on host h (written to /runtime/optimusdb.env by the agent)."""
    import math
    rt = optimusdb_runtime(cfg); env = {}
    if rt.get("log_level"): env["OPTIMUSDB_LOG_LEVEL"] = str(rt["log_level"])
    if rt.get("gogc"): env["GOGC"] = str(rt["gogc"])
    if rt.get("go_limits"):
        # Go 1.19 (the OptimusDB build) sizes its scheduler by the host's CPUs, not the container's limit, and
        # is then throttled by the limit; Rust (Corrosion, Iroh) and Node.js read the limit themselves.
        if h.get("cpus"): env["GOMAXPROCS"] = str(max(1, math.ceil(float(h["cpus"]) - 1e-9)))
        mib = _mem_mib(h.get("mem"))
        if mib: env["GOMEMLIMIT"] = f"{int(mib * 0.8)}MiB"
    if rt.get("args"): env["OPTIMUSDB_ARGS"] = str(rt["args"])
    for k, v in (rt.get("env") or {}).items():
        if v is not None: env[str(k)] = str(v)
    return env


def runtime_summary(cfg):
    """What each system runs with, per role (logged at the start of a run and saved with the results)."""
    roles = {}
    for h in hosts_of(cfg):
        roles.setdefault(h["role"], optimusdb_env(cfg, h))
    return {"optimusdb": roles, **QUIET_ENV, "autobase": {"indexers": int(cfg.get("autobase_indexers") or AUTOBASE_INDEXERS)}}


def url(h, sysid, path=""):
    return f"http://{h['ip']}:{PORTS[sysid]}{path}"


class Agents:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = cfg["cluster"]["token"]
        self.client = httpx.AsyncClient(timeout=180.0, headers={"x-token": self.token})

    async def call(self, h, method, path, body=None):
        r = await self.client.request(method, f"http://{h['ip']}:9100{path}", json=body)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def all(self, hosts, method, path, body=None):
        return await asyncio.gather(*(self.call(h, method, path, body) for h in hosts))

    async def close(self):
        await self.client.aclose()


# ------------------------------------------------------------------ readiness
async def wait_ready(sysid, hosts, timeout_s=300):
    probe = {
        "optimusdb": ("GET", "/swarmkb/agent/status", None),
        "corrosion": ("POST", "/v1/queries", "SELECT 1"),
        "gun": ("GET", "/kv/__ready", None),
        "autobase": ("GET", "/admin/key", None),
        "iroh": ("GET", "/ticket", None),
        "opendht": ("GET", "/node/info", None),
    }[sysid]
    t_end = time.time() + timeout_s
    async with httpx.AsyncClient(timeout=5.0) as c:
        pending = list(hosts)
        while pending and time.time() < t_end:
            still = []
            for h in pending:
                try:
                    r = await c.request(probe[0], url(h, sysid, probe[1]), json=probe[2])
                    if r.status_code >= 500 or (r.status_code >= 400 and sysid != "gun"): still.append(h)
                except httpx.HTTPError:
                    still.append(h)
            pending = still
            if pending: await asyncio.sleep(2)
    if pending:
        raise TimeoutError(f"{sysid} not ready on: {', '.join(h['name'] for h in pending)}")


# ------------------------------------------------------------------ start + join, per system
async def start_joined(ag, sysid, hosts):
    """Start `sysid` on `hosts` and form one cluster over the overlay. Returns when all nodes answer."""
    first, rest = hosts[0], hosts[1:]
    ips = [h["ip"] for h in hosts]

    if sysid == "optimusdb":
        await asyncio.gather(*(ag.call(h, "POST", "/system/optimusdb/start", {"env": optimusdb_env(ag.cfg, h)})
                               for h in hosts))
        await wait_ready(sysid, hosts)
        async with httpx.AsyncClient(timeout=30.0) as c:
            ids = {}
            for h in hosts:
                js = (await c.get(url(h, sysid, "/swarmkb/agent/status"))).json()
                ids[h["ip"]] = (js.get("agent") or {}).get("peer_id")
            # full mesh of libp2p connections on the overlay addresses (mDNS does not cross the overlay)
            for h in hosts:
                for o in hosts:
                    if o is h or not ids.get(o["ip"]): continue
                    body = {"method": {"cmd": "connect", "argcnt": 1},
                            "args": [f"/ip4/{o['ip']}/tcp/4001/p2p/{ids[o['ip']]}"], "dstype": "", "sqldml": "",
                            "criteria": [{}], "graph_traversal": [{}]}
                    await c.post(url(h, sysid, "/swarmkb/command"), json=body)
        return

    if sysid == "corrosion":
        for h in hosts:
            boot = ",".join(f"{ip}:8787" for ip in ips if ip != h["ip"])
            await ag.call(h, "POST", "/system/corrosion/start", {"env": {"BOOTSTRAP": boot, **QUIET_ENV["corrosion"]}})
        await wait_ready(sysid, hosts); return

    if sysid == "gun":
        # One connection per pair of nodes: each node dials only the nodes after it in the host list (connections
        # are bidirectional). When every node dialled every other one, each pair had two connections and every
        # update travelled both, which roughly doubled Gun's relay traffic and drove a node out of heap memory
        # during the 50 % update workload.
        for i, h in enumerate(hosts):
            peers = ",".join(f"http://{ip}:8765/gun" for ip in ips[i + 1:])
            await ag.call(h, "POST", "/system/gun/start", {"env": {"PEERS": peers}})
        await wait_ready(sysid, hosts); return

    if sysid == "opendht":
        await ag.call(first, "POST", "/system/opendht/start", {"env": {"DHT_BOOTSTRAP": ""}})
        await wait_ready(sysid, [first])
        await asyncio.gather(*(ag.call(h, "POST", "/system/opendht/start", {"env": {"DHT_BOOTSTRAP": f"{first['ip']}:4222"}}) for h in rest))
        await wait_ready(sysid, hosts); return

    if sysid == "iroh":
        await ag.call(first, "POST", "/system/iroh/start", {"env": {"TICKET": ""}})
        await wait_ready(sysid, [first])
        async with httpx.AsyncClient(timeout=10.0) as c:
            ticket = (await c.get(url(first, sysid, "/ticket"))).text.strip()
        await asyncio.gather(*(ag.call(h, "POST", "/system/iroh/start", {"env": {"TICKET": ticket}}) for h in rest))
        await wait_ready(sysid, hosts); return

    if sysid == "autobase":
        # one replication stream per pair of nodes (each node dials the nodes after it; the other side accepts)
        peers_of = lambda h: ",".join(f"{ip}:7305" for ip in ips[ips.index(h["ip"]) + 1:])
        await ag.call(first, "POST", "/system/autobase/start", {"env": {"BOOTSTRAP": "", "PEERS": peers_of(first)}})
        await wait_ready(sysid, [first])
        async with httpx.AsyncClient(timeout=10.0) as c:
            base_key = (await c.get(url(first, sysid, "/admin/key"))).json()["base"]
            await asyncio.gather(*(ag.call(h, "POST", "/system/autobase/start", {"env": {"BOOTSTRAP": base_key, "PEERS": peers_of(h)}}) for h in rest))
            await wait_ready(sysid, hosts)
            # every node becomes a writer; the first `autobase_indexers` nodes (default 3) are also indexers, i.e. take
            # part in Autobase's ordering checkpoints. With all 8 as indexers the calibration showed 13-27 % timeouts
            # from 10 ops/s in the cluster; with 3, no errors up to 50 ops/s (WA and WO, with link profiles).
            n_idx = int(ag.cfg.get("autobase_indexers") or AUTOBASE_INDEXERS)
            for i, h in enumerate(rest, start=2):
                wk = (await c.get(url(h, sysid, "/admin/key"))).json()["writer"]
                await c.post(url(first, sysid, "/admin/add-writer"), json={"key": wk, "indexer": i <= n_idx})
        return

    raise ValueError(sysid)


def adapter_for(cfg, sysid, h, local=True):
    c = dict(cfg["systems"][sysid]); c["base_url"] = url(h, sysid)
    if sysid == "optimusdb" and local: c["strategy"] = "LOCAL_ONLY"
    return A.make(c)


async def smoke(cfg, sysid, hosts, timeout_s=120):
    """Write one document on the first host and wait until the last host can read it."""
    key = f"smoke-{uuid.uuid4().hex[:8]}"
    # The smoke document stays in the store; its values match none of Q2, Q3 or Q5 and add no new Q4 group,
    # so E3 row counts are not affected.
    doc = {"_id": key, "region": "eu-west", "status": "Stopped", "cpu_capacity": 2, "memory_capacity": 2048, "version": 1}
    w, r = adapter_for(cfg, sysid, hosts[0], local=False), adapter_for(cfg, sysid, hosts[-1])
    await w.open(); await r.open()
    try:
        t0 = time.time()
        await w.execute("insert", key, doc)
        while time.time() - t0 < timeout_s:
            try:
                if await r.execute("read", key, None): return round(time.time() - t0, 2)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(1)
        raise TimeoutError(f"{sysid}: write on {hosts[0]['name']} not visible on {hosts[-1]['name']} after {timeout_s}s")
    finally:
        await w.close(); await r.close()


# ------------------------------------------------------------------ public operations
async def stop_all(cfg, ag=None):
    own = ag is None; ag = ag or Agents(cfg)
    try: await ag.all(hosts_of(cfg), "POST", "/systems/stop-all")
    finally:
        if own: await ag.close()


async def deploy(cfg, sysid, tier=None, wipe=False, check=True):
    ag = Agents(cfg); hosts = hosts_of(cfg, tier)
    try:
        await ag.all(hosts_of(cfg), "POST", "/systems/stop-all")
        if wipe: await ag.all(hosts, "POST", f"/system/{sysid}/wipe")
        await start_joined(ag, sysid, hosts)
        took = await smoke(cfg, sysid, hosts) if check else None
        return {"system": sysid, "hosts": [h["name"] for h in hosts], "smoke_s": took}
    finally:
        await ag.close()


async def reset(cfg, sysid, tier=None):
    """Hook used by bench.runner before every run: fresh data, fresh cluster, verified replication."""
    return await deploy(cfg, sysid, tier=tier, wipe=True, check=True)


async def stop(cfg, sysid):
    ag = Agents(cfg)
    try: await ag.all(hosts_of(cfg), "POST", f"/system/{sysid}/stop")
    finally: await ag.close()


def nodes(cfg):
    tok = cfg["cluster"]["token"]
    return [faults.Node(name=h["name"], tier=h["role"], ip=h["ip"], iface=cfg["cluster"].get("iface", "wg0"),
                        agent_url=f"http://{h['ip']}:9100", token=tok) for h in hosts_of(cfg)]


def links(cfg):
    return {tuple(k.split("-")): v for k, v in cfg["links"].items()}


async def mesh(cfg):
    ag = Agents(cfg); hosts = hosts_of(cfg); out = []
    try:
        for h in hosts:
            t0 = time.time(); st = await ag.call(h, "GET", "/time"); t1 = time.time()
            offset_ms = (st["t"] - (t0 + t1) / 2) * 1000
            pings = {}
            for o in hosts:
                if o is h: continue
                r = await ag.call(h, "POST", "/exec", {"cmd": f"ping -c 3 -q -W 2 {o['ip']} | tail -1"})
                pings[o["name"]] = (r.get("stdout") or "unreachable").strip()
            out.append({"host": h["name"], "ip": h["ip"], "clock_offset_ms": round(offset_ms, 1),
                        "rtt_to_bench_ms": round((t1 - t0) * 1000, 1), "pings": pings})
        return out
    finally:
        await ag.close()


async def status(cfg):
    ag = Agents(cfg)
    try: return {h["name"]: await ag.call(h, "GET", "/status") for h in hosts_of(cfg)}
    finally: await ag.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["status", "mesh", "deploy", "reset", "stop", "stop-all", "netem", "clear-netem", "smoke"])
    p.add_argument("system", nargs="?", choices=SYSTEMS)
    p.add_argument("--tier", choices=["cloud", "fog", "edge"])
    p.add_argument("--config", default="/config/testbed.yaml")
    a = p.parse_args()
    cfg = yaml.safe_load(open(a.config))
    if a.action in ("deploy", "reset", "stop", "smoke") and not a.system: p.error("system required")
    if a.action == "status": res = asyncio.run(status(cfg))
    elif a.action == "mesh": res = asyncio.run(mesh(cfg))
    elif a.action == "deploy": res = asyncio.run(deploy(cfg, a.system, a.tier))
    elif a.action == "reset": res = asyncio.run(reset(cfg, a.system, a.tier))
    elif a.action == "stop": res = asyncio.run(stop(cfg, a.system)) or "stopped"
    elif a.action == "stop-all": res = asyncio.run(stop_all(cfg)) or "stopped"
    elif a.action == "netem": faults.apply_netem(nodes(cfg), links(cfg)); res = "netem applied"
    elif a.action == "clear-netem": faults.clear_netem(nodes(cfg)); res = "netem cleared"
    else: res = {"smoke_s": asyncio.run(smoke(cfg, a.system, hosts_of(cfg, a.tier)))}
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
