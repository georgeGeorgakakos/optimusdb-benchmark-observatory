"""Answers 'is the running data store alive on every host?' (copied into odb-bench and run by diagnose.ps1).
Sends one HTTP request to the system's API on each host. Any HTTP status (even 404) means the process
answers; a timeout means it is hung or overloaded; 'refused' means it is not running there."""
import json, sys, time, urllib.request, urllib.error
PORTS = {"optimusdb": 8089, "corrosion": 8080, "gun": 7004, "autobase": 7005, "iroh": 7006, "opendht": 8000}
PATHS = {"iroh": "/health", "gun": "/kv/diag-probe", "autobase": "/kv/diag-probe", "corrosion": "/v1/health"}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # direct connections only
sysid = sys.argv[1]
cfg = json.loads(open("/config/testbed.yaml").read().split("\n", 1)[1])
for h in [x for x in cfg["cluster"]["hosts"] if x["role"] != "bench"]:
    url = f"http://{h['ip']}:{PORTS[sysid]}{PATHS.get(sysid, '/')}"
    t0 = time.time()
    try:
        with opener.open(url, timeout=5) as r: st = f"HTTP {r.status}"
    except urllib.error.HTTPError as e: st = f"HTTP {e.code}"
    except Exception as e:
        msg = str(getattr(e, "reason", e))
        st = "TIMEOUT (hung or overloaded)" if "timed out" in msg else "REFUSED (not running)" if "refused" in msg.lower() else msg[:40]
    print(f"  {h['name']:8} {st:30} {1000 * (time.time() - t0):7.0f} ms")
