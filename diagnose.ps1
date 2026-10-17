<#
.SYNOPSIS
  Is the running experiment progressing or stuck? Shows the current step and how long ago the log last moved,
  which data store is running, whether it answers on every host, its CPU/memory, recent errors in its logs,
  and what to do. Read-only: it changes nothing.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\diagnose.ps1
#>
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
Assert-Docker

Write-Step 'Experiment'
$log = Get-ChildItem (Join-Path $Root 'results\logs') -Filter 'E*-*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
$running = [bool](Invoke-Native 'docker' @('exec', 'odb-bench', 'sh', '-c', "pgrep -f '^python -m bench' >/dev/null && echo yes"))
if (-not $log) { Write-Host '  no experiment log yet'; return }
$idle = [int]((Get-Date) - $log.LastWriteTime).TotalMinutes
$last = @(Get-Content $log.FullName -Tail 4)
Write-Host ("  log: results\logs\{0}   process: {1}" -f $log.Name, $(if ($running) { 'running' } else { 'NOT running' }))
$last | ForEach-Object { Write-Host "    $_" }
Write-Host ("  last log line written {0} min ago" -f $idle)

# Longest step that legitimately writes nothing: a 300 s measured window plus warm-up, a 900 s settle wait,
# a 600 s convergence wait, or a large preload. More than 20 minutes of silence is suspicious.
$limit = 20

Write-Step 'Data store containers running now'
$ds = @(Invoke-Native 'docker' @('ps', '--filter', 'name=^odb-', '--format', '{{.Names}}') | Where-Object { $_ -and $_ -notmatch '-(net|agent)$' -and $_ -ne 'odb-bench' })
if (-not $ds) { Write-Host '  none (between runs, or loading has not started)' }
$sys = $null
foreach ($n in $ds) { if ($n -match '^odb-[a-z]+-[a-z]-([a-z]+)$') { $sys = $Matches[1] } }
if ($sys) {
    Write-Host "  system: $sys on $($ds.Count) hosts"
    Invoke-Native 'docker' (@('stats', '--no-stream', '--format', '  {{.Name}}  CPU {{.CPUPerc}}  MEM {{.MemUsage}}') + $ds) | Out-Host

    Write-Step "Does $sys answer on every host? (5 s per host)"
    $null = Invoke-Native 'docker' @('cp', (Join-Path $Root 'tools\probe.py'), 'odb-bench:/tmp/probe.py')
    Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '/tmp/probe.py', $sys) -Merge | Out-Host

    Write-Step "Recent problems in the $sys logs"
    $found = $false
    foreach ($n in $ds) {
        $bad = @(Invoke-Native 'docker' @('logs', '--tail', '200', $n) -Merge | Select-String -Pattern 'out of memory|FATAL|panic|Error|ERROR|Killed' | Select-Object -Last 2)
        if ($bad) { $found = $true; Write-Host "  $n"; $bad | ForEach-Object { Write-Host "    $($_.Line.Trim().Substring(0, [Math]::Min(160, $_.Line.Trim().Length)))" } }
    }
    if (-not $found) { Write-Host '  no errors in the last 200 lines of any host' }
}
$dead = @(Invoke-Native 'docker' @('ps', '-a', '--filter', 'name=^odb-', '--filter', 'status=exited', '--format', '{{.Names}} {{.Status}}') |
          Where-Object { $_ -and $_ -notmatch 'Exited \((0|143)\)' })
if ($dead) {
    Write-Step 'Containers that stopped with an error'
    foreach ($d in $dead) {
        $name = $d.Split(' ')[0]
        $oom = (Invoke-Native 'docker' @('inspect', '--type', 'container', '-f', '{{.State.OOMKilled}}', $name)) -join ''
        $why = if ($oom -eq 'true') { '   <-- killed: out of memory' }
               elseif ($d -match 'Exited \(137\)') { '   (forced stop: did not shut down within 10 s; harmless unless it happened during a run)' }
               elseif ($d -match 'Exited \(139\)') { '   <-- crashed (segmentation fault)' }
               elseif ($d -match 'Exited \(134\)') { '   <-- aborted (often Node.js out of memory)' } else { '' }
        Write-Host ("  {0}{1}" -f $d, $why)
    }
}

Write-Step 'Failed runs'
$fl = Get-ChildItem (Join-Path $Root 'results') -Recurse -Filter 'failures.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($fl) { Get-Content $fl.FullName -Tail 3 | ForEach-Object { Write-Host "  $_" } } else { Write-Host '  none' }

Write-Step 'Verdict'
if (-not $running) {
    Write-Host '  The experiment is not running. If it has not finished, run the same run-all command again: finished runs are skipped.'
} elseif ($idle -lt $limit) {
    Write-Host "  Progressing: the log moved $idle min ago. Wait; no action needed."
} else {
    Write-Host "  Possibly stuck: no log line for $idle min (normal maximum about $limit)."
    Write-Host '  If a host above shows TIMEOUT or a container was killed, that system is hung. Options:'
    Write-Host '    1. wait up to 10 more minutes: the harness abandons a request that gets no answer for 10 min and moves on;'
    Write-Host '    2. or stop and continue:  .\stop-experiment.ps1  then the same run-all command (finished runs are kept);'
    Write-Host '    3. or continue without that system:  .\run-all.ps1 -Quick -Systems <the other systems>'
    Write-Host '  Send this output if it keeps happening.'
}
