<#
.SYNOPSIS
  Runs several scenarios one after the other, unattended, inside the bench container. The chain keeps running if
  you close this window; only the PC (and Docker Desktop) must stay on.
    -Pilot   quick functional check (default E1 only): 1 rep, 30 s warm-up + 120 s measured, E1 on 5 cells per
             system; results in results\pilot\ (never mixed with the campaign). About 2-3 hours.
    -Quick   every scenario E1-E5 once on 10^4 records, short windows and reduced grids, in about 2 hours;
             results in results\quick\. A first look and an end-to-end check, not for statistics.
    (none)   the campaign, default E1 E2 E3 E4 E5, plus E6 if trace\trace.jsonl exists. Several days.
  Earlier results are kept automatically, nothing to do by hand:
    * the previous run of the same kind FINISHED and you run any of its experiments again -> it is moved to
      results-archive\<its start time>-<kind>\ (viewable in the dashboard: Run history) and a new run starts;
    * the previous run was INTERRUPTED (stopped, PC restart)                     -> it is continued: finished runs are skipped;
    * you add experiments that are not in the results yet (e.g. E5 after E1,E3)  -> they are added to the same results.
  -New always starts a new run (keeping the old one in results-archive\); -Resume always continues / adds.
  Watch it with:  .\progress.ps1 -Watch
.PARAMETER Exps     Scenarios to run, in order (e.g. -Exps E2,E3)
.PARAMETER Systems  Subset of systems (default: all six)
.PARAMETER Pilot    Pilot mode (see above)
.PARAMETER Workloads  E1 only: run just these workloads, e.g. -Workloads WO (WO includes its document-size series)
.PARAMETER Quick    Quick mode (see above)
.PARAMETER New      Start a new run even if the previous one was interrupted (the old results go to results-archive\)
.PARAMETER Resume   Continue / add to the current results even if the previous run finished
.EXAMPLE
  .\run-all.ps1 -Quick          # E1-E5 once, about 2 hours
  .\run-all.ps1 -Pilot          # the 2-3 hour pilot of E1
  .\run-all.ps1 -Pilot -Workloads WO -Systems optimusdb,corrosion   # load-generator check: WO cells only (~40 min)
  .\run-all.ps1 -Pilot -Exps E2,E3,E4,E5                             # pilot of the other scenarios at campaign sizes
  .\run-all.ps1                 # then: the whole campaign
  .\run-all.ps1 -Exps E3,E4     # only some scenarios
  .\run-all.ps1 -Quick -Exps E1,E3 -New   # start over even if the last quick run was interrupted
#>
param([ValidateSet('E1', 'E2', 'E3', 'E4', 'E5', 'E6')][string[]]$Exps, [string[]]$Systems, [switch]$Pilot, [switch]$Quick,
      [switch]$New, [switch]$Resume, [ValidateSet('WA', 'WB', 'WC', 'WO')][string[]]$Workloads)
if ($Pilot -and $Quick) { throw 'Use either -Pilot or -Quick, not both' }
if ($New -and $Resume) { throw 'Use either -New or -Resume, not both' }
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker

if (-not $Exps) { $Exps = if ($Pilot) { @('E1') } elseif ($Quick) { @('E1', 'E2', 'E3', 'E4', 'E5') } else { @('E1', 'E2', 'E3', 'E4', 'E5', 'E6') } }
$hasTrace = Test-Path (Join-Path $Root 'trace\trace.jsonl')
if ($Exps -contains 'E6' -and -not $hasTrace) {
    if ($PSBoundParameters.ContainsKey('Exps')) { throw 'E6 needs the captured trace at trace\trace.jsonl (format in harness\bench\trace.py)' }
    Write-Warn2 'trace\trace.jsonl not found: E6 is skipped (run it later with .\run-all.ps1 -Exps E6)'
    $Exps = @($Exps | Where-Object { $_ -ne 'E6' })
}
if (($Pilot -or $Quick) -and $Exps -contains 'E6') { throw 'E6 has no pilot or quick mode; leave it out of -Exps' }

$busy = Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes")
if ($busy) { throw 'An experiment is already running. Watch it with .\progress.ps1, or stop it with .\stop-experiment.ps1' }

# ---- keep earlier results automatically (see the help above)
$kind = if ($Pilot) { 'pilot' } elseif ($Quick) { 'quick' } else { 'campaign' }
$tag = if ($Pilot) { '-pilot' } elseif ($Quick) { '-quick' } else { '' }
$resRoot = Join-Path $Root 'results'; $logsDir = Join-Path $resRoot 'logs'
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$kindDir = if ($kind -eq 'campaign') { $resRoot } else { Join-Path $resRoot $kind }
$isKindLog = { param($n) if ($kind -eq 'campaign') { $n -match '^(campaign|E\d)-\d{8}-\d{6}\.log$' } else { $n -like "*$tag-*.log" -and $n -notlike 'fresh-start-*' } }
$prev = Get-ChildItem $logsDir -File -Filter 'campaign*.log' -ErrorAction SilentlyContinue | Where-Object { & $isKindLog $_.Name } | Sort-Object Name | Select-Object -Last 1
$have = @($Exps | Where-Object { Test-Path (Join-Path $kindDir "$($_)_raw.csv") })
$prevFinished = [bool]($prev -and (Select-String -Path $prev.FullName -Pattern ' finished\s*$' -Quiet))
$prevStart = if ($prev -and $prev.Name -match '(\d{8})-(\d{2})(\d{2})(\d{2})') { '{0}/{1}/{2} {3}:{4}' -f $Matches[1].Substring(6, 2), $Matches[1].Substring(4, 2), $Matches[1].Substring(0, 4), $Matches[2], $Matches[3] } else { '' }
$archive = if ($Resume) { $false } elseif ($New) { [bool]($have -or (Test-Path (Join-Path $kindDir 'ops'))) } else { $prevFinished -and $have.Count -gt 0 }
if ($archive) {
    $label = if ($prev -and $prev.Name -match '(\d{8}-\d{6})') { $Matches[1] } else { Get-Date -Format 'yyyyMMdd-HHmmss' }
    $dst = Join-Path $Root "results-archive\$label-$kind"; $i = 2
    while (Test-Path $dst) { $dst = Join-Path $Root "results-archive\$label-$kind-$i"; $i++ }
    New-Item -ItemType Directory -Force -Path (Join-Path $dst 'logs') | Out-Null
    if ($kind -eq 'campaign') {   # the campaign lives at the top of results\: everything except quick\, pilot\ and logs\
        Get-ChildItem $resRoot | Where-Object { $_.Name -notin @('quick', 'pilot', 'logs') } | Move-Item -Destination $dst
    } else {
        Move-Item $kindDir (Join-Path $dst $kind)
    }
    Get-ChildItem $logsDir -File | Where-Object { & $isKindLog $_.Name } | Move-Item -Destination (Join-Path $dst 'logs')
    $fs = Get-ChildItem $logsDir -File -Filter 'fresh-start-*.log' | Sort-Object Name | Select-Object -Last 1
    if ($fs) { Copy-Item $fs.FullName (Join-Path $dst 'logs') }   # records which build and limits that run used
    Write-Ok ("Previous {0} run{1} kept in results-archive\{2} (dashboard: Run history). Starting a new {0} run." -f $kind, $(if ($prevStart) { " (started $prevStart)" } else { '' }), (Split-Path $dst -Leaf))
} elseif ($prev -and -not $prevFinished -and $have.Count) {
    Write-Ok "Continuing the interrupted $kind run started $prevStart`: finished runs are skipped. (Use -New to start over.)"
} elseif ($have.Count) {
    Write-Ok "Adding to the current $kind results ($($have -join ', ') already there: finished runs are skipped)."
} elseif (Get-ChildItem $kindDir -File -Filter 'E*_raw.csv' -ErrorAction SilentlyContinue) {
    Write-Ok "Adding $($Exps -join ', ') to the current $kind results."
}

Write-Step 'Applying the Table 7 link profiles'
Invoke-Bench @('python', '-m', 'bench.cluster', 'netem', '--config', '/config/testbed.yaml')

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$clog = "/results/logs/campaign$tag-$stamp.log"
# No double quotes inside the chain: Windows PowerShell 5.1 mangles them when passing arguments to docker.
$parts = @("echo `$(date +%F_%T) start $($Exps -join ' ')$tag >> $clog")
foreach ($e in $Exps) {
    $log = "/results/logs/$e$tag-$stamp.log"
    $cmd = if ($e -eq 'E6') { 'python -m bench.trace --campaign --trace /trace/trace.jsonl --config /config/testbed.yaml' }
           else { "python -m bench.runner $e --config /config/testbed.yaml" + $(if ($Pilot) { ' --pilot' } elseif ($Quick) { ' --quick' } else { '' }) }
    if ($Systems) { $cmd += ' --systems ' + ($Systems -join ' ') }
    if ($Workloads -and $e -eq 'E1') { $cmd += ' --workloads ' + ($Workloads -join ' ') }
    $parts += "echo `$(date +%F_%T) begin $e >> $clog"
    $parts += "$cmd > $log 2>&1; echo `$(date +%F_%T) end $e exit=`$? >> $clog"
}
$parts += "echo `$(date +%F_%T) finished >> $clog"
# Then save the evaluation report of this run (self-contained HTML in its results folder; a failure here does not affect the results)
$parts += "python /dashboard/report_cli.py --results /results --mode $kind --stamp $stamp > /results/logs/report$tag-$stamp.log 2>&1 || true"
Invoke-Bench @('sh', '-c', ($parts -join '; ')) -Detach

Write-Ok ("Started {0}: {1}" -f $(if ($Pilot) { 'pilot' } elseif ($Quick) { 'quick run' } else { 'campaign' }), ($Exps -join ' -> '))
Write-Host ''
Write-Host 'It runs in the background inside Docker; you can close this window.'
$dash = Invoke-Native 'docker' @('inspect', '--type', 'container', '-f', '{{.State.Status}}', 'odb-dashboard')
if ($dash -ne 'running') { & (Join-Path $PSScriptRoot 'dashboard.ps1') -NoBrowser | Out-Null }
Write-Host 'Dashboard:  http://localhost:8501   (open it with: powershell -ExecutionPolicy Bypass -File .\dashboard.ps1)'
Write-Host 'Watch it:   powershell -ExecutionPolicy Bypass -File .\progress.ps1 -Watch'
Write-Host 'Stop it:    powershell -ExecutionPolicy Bypass -File .\stop-experiment.ps1'
