<#
.SYNOPSIS
  Shows the progress of the running (or last) experiment: is it running, which run of how many, the current
  step, finished runs per system, failures and an estimated time left.
.PARAMETER Exp    E1..E6 (default: the experiment with the newest log)
.PARAMETER Watch  Refresh every 30 s until Ctrl+C
.EXAMPLE
  .\progress.ps1
  .\progress.ps1 -Watch
#>
param([ValidateSet('E1', 'E2', 'E3', 'E4', 'E5', 'E6')][string]$Exp, [switch]$Watch)
$Root = $PSScriptRoot

function Show-Progress {
    $logs = Get-ChildItem (Join-Path $Root 'results\logs') -Filter "$(if ($Exp) { $Exp } else { 'E' })*-*.log" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike 'fresh-start-*' } | Sort-Object LastWriteTime
    if (-not $logs) { Write-Host 'No experiment log yet. Start with .\run-all.ps1 -Pilot'; return }
    $log = $logs[-1]; $e = $log.Name.Split('-')[0]
    $isPilot = $log.Name -like '*-pilot-*'; $isQuick = $log.Name -like '*-quick-*'
    $resDir = if ($isPilot) { Join-Path $Root 'results\pilot' } elseif ($isQuick) { Join-Path $Root 'results\quick' } else { Join-Path $Root 'results' }
    $lines = @(Get-Content $log.FullName -ErrorAction SilentlyContinue)

    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $running = [bool](& docker exec odb-bench sh -c "pgrep -f '^python -m bench' >/dev/null && echo yes" 2>$null)
    $ErrorActionPreference = $old
    # campaign chain (run-all): which scenarios are done, running, waiting
    $camp = Get-ChildItem (Join-Path $Root 'results\logs') -Filter 'campaign*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($camp) {
        $cl = @(Get-Content $camp.FullName)
        $planned = if ($cl.Count -and $cl[0] -match ' start (.*)$') { $Matches[1].Replace('-pilot', '').Replace('-quick', '').Split(' ') } else { @() }
        $doneE = @($cl | Where-Object { $_ -match ' end (E\d) ' } | ForEach-Object { if ($_ -match ' end (E\d) exit=(\d+)') { "$($Matches[1]) done$(if ($Matches[2] -ne '0') { " (exit $($Matches[2]))" })" } })
        $cur = @($cl | Where-Object { $_ -match ' begin (E\d)' } | Select-Object -Last 1 | ForEach-Object { if ($_ -match ' begin (E\d)') { $Matches[1] } })
        $ended = @($cl | Where-Object { $_ -match ' end (E\d) ' } | ForEach-Object { if ($_ -match ' end (E\d) ') { $Matches[1] } })
        $waiting = @($planned | Where-Object { $_ -and ($ended -notcontains $_) -and ($cur -notcontains $_) })
        $state = if ($cl -match ' finished$') { 'finished' } elseif ($running) { "running $($cur -join '')" } else { 'stopped' }
        Write-Host ''
        Write-Host ("{0} ({1}): {2}" -f $(if ($camp.Name -like '*pilot*') { 'Pilot' } elseif ($camp.Name -like '*quick*') { 'Quick run' } else { 'Campaign' }), $camp.Name, $state) -ForegroundColor Cyan
        if ($doneE) { Write-Host ("  done:    {0}" -f ($doneE -join ', ')) }
        if ($waiting -and $state -ne 'finished') { Write-Host ("  waiting: {0}" -f ($waiting -join ', ')) }
    }
    Write-Host ''
    Write-Host ("{0}{1}  {2}   log: results\logs\{3}" -f $e, $(if ($isPilot) { ' (pilot)' } elseif ($isQuick) { ' (quick)' } else { '' }), $(if ($running) { 'RUNNING' } else { 'NOT RUNNING' }), $log.Name) -ForegroundColor $(if ($running) { 'Green' } else { 'Yellow' })

    $pos = $lines | Where-Object { $_ -match '\[(\d+)/(\d+)\]' } | Select-Object -Last 1
    $doneHere = @($lines | Where-Object { $_ -match '  done ' }).Count
    if ($pos -and $pos -match '\[(\d+)/(\d+)\]\s+(.*)$') {
        $i = [int]$Matches[1]; $n = [int]$Matches[2]
        Write-Host ("  run {0} of {1} ({2:P0}): {3}" -f $i, $n, (($i - 1) / $n), $Matches[3])
        $step = ($lines | Select-Object -Last 1)
        if ($step -ne $pos) { Write-Host "  now: $($step.Trim())" }
        if ($running -and $doneHere -gt 0) {
            $per = ((Get-Date) - $log.CreationTime).TotalMinutes / $doneHere
            $left = [TimeSpan]::FromMinutes($per * ($n - $i + 1))
            Write-Host ("  about {0:N1} min per run; time left about {1}h {2:00}m (finish around {3:ddd HH:mm})" -f $per, [int][math]::Floor($left.TotalHours), $left.Minutes, (Get-Date).Add($left))
        }
    } elseif ($lines.Count -eq 0) { Write-Host '  starting (no progress lines yet)' }
    else { Write-Host "  last line: $($lines[-1])" }

    $raw = Join-Path $resDir "${e}_raw.csv"
    if (Test-Path $raw) {
        $rows = @(Import-Csv $raw)
        Write-Host ("  finished runs in {0}: {1}" -f $raw.Substring($Root.Length + 1), $rows.Count)
        if ($rows.Count) {
            $rows | Group-Object system | Sort-Object Name | ForEach-Object { Write-Host ("    {0,-10} {1}" -f $_.Name, $_.Count) }
        }
    }
    $fl = Join-Path $resDir 'failures.log'
    $nf = if (Test-Path $fl) { @(Get-Content $fl | Where-Object { $_ -match " $e-" }).Count } else { 0 }
    Write-Host ("  failed runs ({0}): {1}" -f $e, $nf) -ForegroundColor $(if ($nf) { 'Yellow' } else { 'Gray' })
    if ($nf) { Get-Content $fl | Where-Object { $_ -match " $e-" } | Select-Object -Last 3 | ForEach-Object { Write-Host "    $_" } }
}

if ($Watch) { while ($true) { Clear-Host; Show-Progress; Write-Host ''; Write-Host '(refreshes every 30 s; Ctrl+C to stop watching - the experiment keeps running)'; Start-Sleep 30 } }
else { Show-Progress }
