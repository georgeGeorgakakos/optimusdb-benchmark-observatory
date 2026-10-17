<#
.SYNOPSIS
  Keeps a copy of the current results\ folder in results-archive\<date-time>[-<Name>]\, so a run stays viewable
  in the dashboard (Run history page, "Archived" in the selector) after the folder changes.
  fresh-start.ps1 already does this automatically; use this script to keep results without a fresh start.
.PARAMETER Name   Optional label added to the folder name, e.g. quick-ed25519 (letters, digits, - and _ only).
.PARAMETER Move   Move instead of copy: results\ is emptied, so the next run-all starts from zero instead of
                  resuming (a repeated run-all command skips runs that are already in results\).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\save-results.ps1 -Name quick-run2
  powershell -ExecutionPolicy Bypass -File .\save-results.ps1 -Name quick-run2 -Move
#>
param([string]$Name, [switch]$Move)
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Stop'
if ($Name -and $Name -notmatch '^[A-Za-z0-9_-]+$') { Write-Fail 'Name: use letters, digits, - and _ only'; exit 1 }
$res = Join-Path $Root 'results'
if (-not (Test-Path $res)) { Write-Fail 'There is no results\ folder yet.'; exit 1 }
$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$busy = & docker exec odb-bench sh -c "pgrep -f '^python -m bench' >/dev/null && echo yes" 2>$null
$ErrorActionPreference = $old
if ($busy) { Write-Fail 'An experiment is running: wait until it finishes (or stop it with .\stop-experiment.ps1), then save.'; exit 1 }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dst = Join-Path $Root ("results-archive\$stamp" + $(if ($Name) { "-$Name" } else { '' }))
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
if ($Move) {
    Move-Item $res $dst
    New-Item -ItemType Directory -Force -Path (Join-Path $res 'logs') | Out-Null
    Write-Ok "Results moved to $(Split-Path $dst -Leaf) in results-archive\; results\ is empty for the next run"
} else {
    Copy-Item $res $dst -Recurse
    Write-Ok "Results copied to $(Split-Path $dst -Leaf) in results-archive\"
}
Write-Host '  View them in the dashboard: Run history page, or "Archived ..." in the selector at the top.'
