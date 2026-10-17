<#
.SYNOPSIS
  Measures where OptimusDB's request time goes, with and without INFO logging, and collects its logs.
  Takes about 5-8 minutes. Stops any other data store first; do not run it while a test is running.
  Report: results\logs\diag-optimusdb-<time>.txt (send this file).
#>
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
if ((Get-BenchState) -ne 'running') { Write-Fail 'odb-bench is not running. Run .\fresh-start.ps1 first.'; exit 1 }
$busy = Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes")
if ($busy -eq 'yes') { Write-Fail 'A test is running. Wait for it to finish or stop it with .\stop-experiment.ps1'; exit 1 }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$rep = Join-Path $Root "results\logs\diag-optimusdb-$stamp.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $rep) | Out-Null
Write-Step 'Running the OptimusDB diagnosis (5-8 min)'
Get-Content (Join-Path $Root 'tools\diag_optimusdb.py') -Raw | docker exec -i odb-bench python - 2>&1 | Tee-Object -FilePath $rep
Add-Content $rep "`n=== OptimusDB build"
Invoke-Native 'docker' @('image', 'inspect', '-f', '{{.Created}}', 'odb-optimusdb:latest') -Merge | Add-Content $rep
Select-String (Get-ChildItem (Join-Path $Root 'results\logs\fresh-start-*.log') | Sort-Object LastWriteTime | Select-Object -Last 1) -Pattern 'OptimusDB source' | ForEach-Object { $_.Line } | Add-Content $rep
Add-Content $rep "`n=== cloud-a OptimusDB internal log (last 150 lines) and log volume"
Invoke-Native 'docker' @('exec', 'odb-cloud-a-optimusdb', 'sh', '-c', 'cd /root; ls -la logs *.db data 2>/dev/null | head -30; wc -l logs/optimusdb.log 2>/dev/null; tail -n 150 logs/optimusdb.log 2>/dev/null') -Merge | Add-Content $rep
Add-Content $rep "`n=== cloud-a container log (last 40 lines)"
Invoke-Native 'docker' @('logs', '--tail', '40', 'odb-cloud-a-optimusdb') -Merge | Add-Content $rep
Write-Ok "Report: $rep"
Write-Host '  Send this file.'
