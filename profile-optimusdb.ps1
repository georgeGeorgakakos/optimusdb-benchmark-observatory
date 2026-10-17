<#
.SYNOPSIS
  Profiles OptimusDB under the update-heavy workload (WA): where CPU time goes and which locks requests wait on.
  Takes about 5 minutes. Stops any other data store first; do not run it while a test is running.
  Needs an OptimusDB build that contains pprof.go (OPTIMUSDB_PPROF); the profiler is on only for this script.
  Result: results\logs\profile-<time>.zip (send this file).
.EXAMPLE
  .\profile-optimusdb.ps1                 # WA at the benchmark rate (50 ops/s)
  .\profile-optimusdb.ps1 -Workload WO -Rate 100
#>
param([string]$Workload = 'WA', [int]$Rate = 0)
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
if ((Get-BenchState) -ne 'running') { Write-Fail 'odb-bench is not running. Run .\fresh-start.ps1 first.'; exit 1 }
$busy = Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes")
if ($busy -eq 'yes') { Write-Fail 'A test is running. Wait for it to finish or stop it with .\stop-experiment.ps1'; exit 1 }
Write-Step "Profiling OptimusDB under $Workload (about 5 min)"
$envArgs = @('-e', "WORKLOAD=$Workload")
if ($Rate -gt 0) { $envArgs += @('-e', "RATE=$Rate") }
$out = Get-Content (Join-Path $Root 'tools\profile_optimusdb.py') -Raw | docker exec -i @envArgs odb-bench python - 2>&1
$out | ForEach-Object { Write-Host $_ }
$dirLine = $out | Where-Object { $_ -match '^PROFILE_DIR ' } | Select-Object -Last 1
if (-not $dirLine) { Write-Fail 'No profile was collected (see the messages above).'; exit 1 }
$name = ($dirLine -replace '^PROFILE_DIR ', '').Trim()
$dir = Join-Path $Root "results\logs\$name"
Invoke-Native 'docker' @('logs', '--tail', '60', 'odb-cloud-a-optimusdb') -Merge | Set-Content (Join-Path $dir 'cloud-a-container.log')
$zip = "$dir.zip"
Compress-Archive -Path (Join-Path $dir '*') -DestinationPath $zip -Force
Write-Ok "Profile: $zip"
Write-Host '  Send this file.'
