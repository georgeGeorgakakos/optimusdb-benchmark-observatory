<#
.SYNOPSIS
  Bench host: runs one common scenario (E1-E6) across the six systems. Before every run the harness stops the
  other systems, wipes the system under test, starts and joins it on all hosts and checks replication.
  Runs are resumable: finished run_ids in results\<E>_raw.csv are skipped, so re-running continues a campaign.
.PARAMETER Exp      E1 | E2 | E3 | E4 | E5 | E6
.PARAMETER Systems  Subset of systems (default: all six)
.PARAMETER Reps     Override the number of repetitions
.PARAMETER Pilot    Quick check: 1 rep, 30 s warm-up + 120 s, E1 on 5 cells; results in results\pilot\
.PARAMETER Follow   Stay attached and stream the log (default: run in the background)
.EXAMPLE
  .\run-experiment.ps1 -Exp E1 -Pilot -Follow                   # pilot of one scenario (run-all.ps1 -Pilot does the same unattended)
  .\run-experiment.ps1 -Exp E5 -Systems optimusdb,corrosion
#>
param([Parameter(Mandatory)][ValidateSet('E1', 'E2', 'E3', 'E4', 'E5', 'E6')][string]$Exp,
      [string[]]$Systems, [int]$Reps, [switch]$Follow, [switch]$NoNetem, [switch]$Pilot)
. "$PSScriptRoot\scripts\lib\common.ps1"
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = "/results/logs/$Exp$(if ($Pilot) { '-pilot' })-$stamp.log"
if ($Exp -eq 'E6') {
    if ($Pilot) { throw 'E6 has no pilot mode' }
    if (-not (Test-Path (Join-Path $Root 'trace\trace.jsonl'))) { throw 'E6 needs the captured trace at trace\trace.jsonl (format in harness\bench\trace.py)' }
    $cmd = @('python', '-m', 'bench.trace', '--campaign', '--trace', '/trace/trace.jsonl', '--config', '/config/testbed.yaml')
    if ($Reps) { $cmd += @('--reps', "$Reps") }
} else {
    $cmd = @('python', '-m', 'bench.runner', $Exp, '--config', '/config/testbed.yaml')
    if ($Reps) { $cmd += @('--reps', "$Reps") }
    if ($Pilot) { $cmd += '--pilot' }
}
if ($Systems) { $cmd += @('--systems') + $Systems }
if (-not $NoNetem) {
    Write-Step 'Applying the Table 7 link profiles'
    Invoke-Bench @('python', '-m', 'bench.cluster', 'netem', '--config', '/config/testbed.yaml')
}
$line = ($cmd -join ' ') + " > $log 2>&1"
Write-Step "Running $Exp  (log: results\logs\$Exp-$stamp.log)"
Invoke-Bench @('sh', '-c', $line) -Detach
if ($Follow) { & docker exec odb-bench sh -c "sleep 1; tail -n +1 -f $log" }
else { Write-Host "Running in the background. Follow with:  docker exec odb-bench tail -f $log" }
