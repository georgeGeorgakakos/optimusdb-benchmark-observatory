<#
.SYNOPSIS
  Checks whether a baseline's failures are its own behaviour or a benchmark problem: runs WA at rising rates on a
  single node and on the 8-host cluster, with CPU and memory, and gives a verdict per system.
  About 10-20 minutes per system and workload. Stops any other data store first; do not run it while a test is running.
  Report: results\logs\calibration-<time>.txt (send this file).
.EXAMPLE
  .\calibrate-baselines.ps1                          # Gun.js, Autobase, OpenDHT
  .\calibrate-baselines.ps1 -Systems gun,autobase,iroh,corrosion
  .\calibrate-baselines.ps1 -Systems autobase -AutobaseIndexers 3   # Autobase with 3 indexers instead of 8
  .\calibrate-baselines.ps1 -NoLinks                                  # cluster without the link profiles
#>
param([string]$Systems = 'gun,autobase,opendht', [string]$Workloads = 'WA,WO', [string]$Rates = '5,10,25,50', [int]$Records = 10000,
      [switch]$NoLinks, [int]$AutobaseIndexers = 0)
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
if ((Get-BenchState) -ne 'running') { Write-Fail 'odb-bench is not running. Run .\fresh-start.ps1 first.'; exit 1 }
$busy = Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes")
if ($busy -eq 'yes') { Write-Fail 'A test is running. Wait for it to finish or stop it with .\stop-experiment.ps1'; exit 1 }
Write-Step "Calibrating $Systems with $Workloads (about 10-20 min per system and workload)"
$envArgs = @('-e', "SYSTEMS=$Systems", '-e', "WORKLOADS=$Workloads", '-e', "RATES=$Rates", '-e', "RECORDS=$Records",
             '-e', "CLUSTER_NETEM=$(if ($NoLinks) { '0' } else { '1' })")
if ($AutobaseIndexers -gt 0) { $envArgs += @('-e', "AUTOBASE_INDEXERS=$AutobaseIndexers") }
Get-Content (Join-Path $Root 'tools\calibrate_baselines.py') -Raw |
  docker exec -i @envArgs odb-bench python - 2>&1 | ForEach-Object { Write-Host $_ }
$rep = Get-ChildItem (Join-Path $Root 'results\logs\calibration-*.txt') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($rep) { Write-Ok "Report: $($rep.FullName)"; Write-Host '  Send this file.' } else { Write-Fail 'No report was written (see the messages above).' }
