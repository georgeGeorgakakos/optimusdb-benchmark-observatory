"""Network emulation and fault injection.

Every node is reached through a `Node` with a command channel: either the host agent of the
Docker Desktop deployment (`agent_url`, commands run inside the host's network namespace that
owns the wg0 overlay interface), or a shell prefix (ssh, kubectl exec or docker exec).
Faults follow the Jepsen approach: inject, keep the workload running, heal,
then check the recorded history.
"""
import asyncio, random, shlex, subprocess, time
from dataclasses import dataclass


@dataclass
class Node:
    name: str
    tier: str
    ip: str
    exec_prefix: str = ""     # e.g. "ssh pi@10.0.0.21 sudo" | "kubectl exec -n optimusddc optimusdb-3 --"
    iface: str = "eth0"
    kill_cmd: str = "pkill -9 -f optimusdb"
    start_cmd: str = "systemctl start optimusdb"
    agent_url: str = ""       # Docker Desktop deployment: http://<overlay-ip>:9100
    token: str = ""

    def sh(self, cmd, check=True):
        if self.agent_url:
            import json, urllib.request
            req = urllib.request.Request(f"{self.agent_url}/exec", data=json.dumps({"cmd": cmd}).encode(),
                                         headers={"content-type": "application/json", "x-token": self.token}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = json.loads(resp.read())
            if check and out.get("rc", 1) != 0:
                raise RuntimeError(f"{self.name}: {cmd} -> {out.get('stderr', '').strip()}")
            return out.get("stdout", "")
        full = f"{self.exec_prefix} sh -c {shlex.quote(cmd)}"
        r = subprocess.run(full, shell=True, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"{self.name}: {cmd} -> {r.stderr.strip()}")
        return r.stdout


# ------------------------------------------------------------------ netem
def apply_netem(nodes, links):
    """links: {(tier_a, tier_b): dict(delay_ms, jitter_ms, loss_pct, rate_mbit)}.
    Builds a prio qdisc per node with one netem class per destination tier and u32
    filters on destination IP, so each pair of tiers gets its own link profile."""
    by_tier = {}
    for n in nodes: by_tier.setdefault(n.tier, []).append(n)
    for n in nodes:
        n.sh(f"tc qdisc del dev {n.iface} root 2>/dev/null || true", check=False)
        n.sh(f"tc qdisc add dev {n.iface} root handle 1: htb default 99")
        n.sh(f"tc class add dev {n.iface} parent 1: classid 1:99 htb rate 10gbit")
        for k, peer_tier in enumerate(sorted(by_tier), start=1):
            prof = links.get((n.tier, peer_tier)) or links.get((peer_tier, n.tier))
            if not prof: continue
            n.sh(f"tc class add dev {n.iface} parent 1: classid 1:{k} htb rate {prof['rate_mbit']}mbit")
            jit = f"{prof.get('jitter_ms', 0)}ms distribution normal" if prof.get('jitter_ms') else ""
            n.sh(f"tc qdisc add dev {n.iface} parent 1:{k} handle {10 + k}: netem delay {prof['delay_ms']}ms "
                 f"{jit} loss {prof.get('loss_pct', 0)}%")
            for peer in by_tier[peer_tier]:
                if peer is n: continue
                n.sh(f"tc filter add dev {n.iface} protocol ip parent 1: prio 1 u32 match ip dst {peer.ip}/32 flowid 1:{k}")


def clear_netem(nodes):
    for n in nodes: n.sh(f"tc qdisc del dev {n.iface} root 2>/dev/null || true", check=False)


# ------------------------------------------------------------------ partitions
def partition(groups):
    """groups: list of node lists; traffic between different groups is dropped (both directions)."""
    t = time.time()
    for gi, g in enumerate(groups):
        others = [m for gj, h in enumerate(groups) if gj != gi for m in h]
        for n in g:
            for o in others:
                n.sh(f"iptables -I INPUT -s {o.ip} -j DROP && iptables -I OUTPUT -d {o.ip} -j DROP")
    return t


def heal(nodes):
    t = time.time()
    for n in nodes:
        n.sh("iptables -F INPUT && iptables -F OUTPUT", check=False)
    return t


# ------------------------------------------------------------------ crashes and churn
def crash(node):
    t = time.time(); node.sh(node.kill_cmd, check=False); return t


def restart(node):
    t = time.time(); node.sh(node.start_cmd, check=False); return t


async def churn(nodes, every_s=30, duration_s=1200, protect=(), log=None, seed=1):
    """Every `every_s` seconds stop one random running node and start one stopped node."""
    rng = random.Random(seed)
    up = [n for n in nodes if n.name not in protect]; down = []
    t_end = time.time() + duration_s
    while time.time() < t_end:
        await asyncio.sleep(every_s)
        if up:
            v = rng.choice(up); up.remove(v); crash(v); down.append(v)
            if log: log(time.time(), "leave", v.name)
        if len(down) > 1:
            j = down.pop(0); restart(j); up.append(j)
            if log: log(time.time(), "join", j.name)
