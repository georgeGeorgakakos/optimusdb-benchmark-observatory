<#
.SYNOPSIS
  Starts the OptimusDB cluster (no test) and checks that everything that must be off for the benchmark is off:
  metadata enrichment, llama-server / TinyLlama, the semantic index, Loki shipping; and shows the runtime
  settings (log level, Go limits, group commit, field indexes, request concurrency), the build and the libp2p
  mesh. Do not run it while a test is running.
#>
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
if ((Get-BenchState) -ne 'running') { Write-Fail 'odb-bench is not running. Run .\fresh-start.ps1 first.'; exit 1 }
$busy = Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes")
if ($busy -eq 'yes') { Write-Fail 'A test is running. Wait for it to finish first.'; exit 1 }
Write-Step 'Starting the OptimusDB cluster (about 1 minute)'
Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '-m', 'bench.cluster', 'deploy', 'optimusdb', '--config', '/config/testbed.yaml') -Merge | Select-Object -Last 3 | Out-Host
Start-Sleep -Seconds 20
$c = 'odb-cloud-a-optimusdb'
# Environment of the running OptimusDB process (PID 1): container variables plus /runtime/optimusdb.env.
function Get-ProcEnv($name) { Invoke-Native 'docker' @('exec', $name, 'sh', '-c', "tr '\0' '\n' < /proc/1/environ") -Merge }
$envs = Get-ProcEnv $c
$procs = Invoke-Native 'docker' @('exec', $c, 'sh', '-c', 'ps -eo comm 2>/dev/null || ls /proc | grep -E "^[0-9]+$" | while read p; do cat /proc/$p/comm 2>/dev/null; done') -Merge
$log = Invoke-Native 'docker' @('exec', $c, 'sh', '-c', 'cat /root/logs/optimusdb.log 2>/dev/null') -Merge
function Show($ok, $msg) { if ($ok) { Write-Ok $msg } else { Write-Warn2 $msg } }
Write-Step 'Settings that must be off'
Show ($envs -match '^METADATA_AUTO_ENRICH=false$') 'METADATA_AUTO_ENRICH=false (metadata enrichment off)'
Show ($envs -match '^METADATA_ENRICHMENT_ENABLED=false$') 'METADATA_ENRICHMENT_ENABLED=false'
Show (-not ($procs -match 'llama|supervisord')) 'no llama-server / supervisord process (only the OptimusDB agent runs)'
Show (-not ($envs -match '^LOKI_URL=.+')) 'LOKI_URL not set (no log shipping to Loki)'
Show (-not ($log -match 'Semantic search index initialized')) 'semantic index not initialised (needs llama-server)'
Show (-not ($log -match 'TinyLlama client initialized and healthy')) 'TinyLlama metadata client not active'
Write-Step 'Settings to report in Section 8'
function Val($e, $name, $default) { $m = ($e | Where-Object { $_ -match "^$name=" } | Select-Object -First 1); if ($m) { $m.Substring($name.Length + 1) } else { $default } }
foreach ($h in @('cloud-a', 'edge-a')) {
  $e = if ($h -eq 'cloud-a') { $envs } else { Get-ProcEnv "odb-$h-optimusdb" }
  Write-Host "  [$h]"
  Write-Host ("    log level:           {0}" -f (Val $e 'OPTIMUSDB_LOG_LEVEL' 'INFO (default; every INFO line is also written to SQLite)'))
  Write-Host ("    GOMAXPROCS:          {0}" -f (Val $e 'GOMAXPROCS' 'not set (Go uses all host CPUs and is throttled by the container limit)'))
  Write-Host ("    GOMEMLIMIT / GOGC:   {0} / {1}" -f (Val $e 'GOMEMLIMIT' 'not set'), (Val $e 'GOGC' '100 (default)'))
  Write-Host ("    arguments:           {0}" -f (Val $e 'OPTIMUSDB_ARGS' '(none)'))
}
Write-Host ("  request concurrency: {0}" -f (Val $envs 'SERVICE_CONCURRENCY' 'default 32'))
Write-Host ("  group commit:        {0}" -f (Val $envs 'OPTIMUSDB_GROUP_COMMIT' 'on (default)'))
Write-Host ("  field indexes:       {0}" -f (Val $envs 'OPTIMUSDB_INDEX_FIELDS' 'type,status,region,resource_id (default)'))
Write-Host ("  document cache:      {0}" -f (Val $envs 'OPTIMUSDB_DOC_CACHE_MB' '128 MiB per store (default)'))
Write-Host ("  IPFS key / provide / fsync:  {0} / {1} / {2}" -f (Val $envs 'OPTIMUSDB_IPFS_KEY' 'rsa (default)'), (Val $envs 'OPTIMUSDB_IPFS_PROVIDE' 'on (default)'), (Val $envs 'OPTIMUSDB_IPFS_SYNC' 'on (default)'))
Write-Host ("  processes:          {0}" -f (($procs | Where-Object { $_ -and $_ -notmatch '^(COMMAND|ps|sh|cat|grep|ls|while|read)$' } | Select-Object -Unique) -join ', '))
$fsLog = Get-ChildItem (Join-Path $Root 'results\logs\fresh-start-*.log') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($fsLog) {
  Select-String $fsLog -Pattern 'OptimusDB source' | ForEach-Object { Write-Host "  build:             $($_.Line.Trim())" }
  if (Select-String $fsLog -Pattern 'Performance code found' -Quiet) { Write-Ok 'Performance code found in this build (group commit, field indexes, document cache)' }
  else { Write-Warn2 'The last fresh start did not report the performance code: push the OptimusDB changes and run fresh-start.ps1 again' }
}
Write-Step 'Mesh and API'
# Connected peers come from libp2p; the role appears once the election controller has started, which OptimusDB
# does only after its mesh has stabilised (up to a few minutes after start), so this waits up to 3 minutes.
$py = @"
import httpx, time
t_end = time.time() + 180
while True:
    r = httpx.get('http://10.88.0.11:8089/swarmkb/agent/status', timeout=10).json()
    c = r.get('cluster', {}); a = r.get('agent') or {}; e = r.get('election') or {}
    if a.get('role') not in (None, '', 'Unknown') or time.time() > t_end: break
    time.sleep(10)
print('  cloud-a: connected peers', c.get('connected_peers'), 'of 7, role', a.get('role'), ', leader', (e.get('current_leader') or '-')[-8:], ', term', e.get('current_term'))
"@
Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '-c', $py) -Merge | Out-Host
Write-Host ''
Write-Host 'OptimusDB keeps running; the next test run stops it.'
