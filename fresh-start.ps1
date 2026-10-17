<#
.SYNOPSIS
  Single-machine mode: one command from any state to a clean, verified testbed.
    1. unblocks all scripts in this folder (no more security prompts)
    2. starts Docker Desktop if it is not running and waits for it
    3. stops any running experiment, removes every testbed container, data volume and the network
    4. moves the old results to results-archive\<timestamp> (or deletes them with -DeleteResults)
    5. builds the images (cached; -Rebuild = from scratch) and starts the testbed (deploy-local)
    6. smoke-tests all six data stores and prints a pass/fail table
  Everything is logged to results\logs\fresh-start-<timestamp>.log.
.PARAMETER CpusCloud/MemCloud/CpusFog/MemFog/CpusEdge/MemEdge
  Limits per data store. Default: the limits of the previous deployment, else cloud/fog 1.5 CPU 3g, edge 1 CPU 2g.
.PARAMETER Rebuild        Rebuild all images without the Docker cache and re-clone OptimusDB (slow: 30-60 min).
.PARAMETER DeleteResults  Delete old results instead of archiving them.
.PARAMETER SkipSmoke      Do not run the six smoke tests at the end.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1     (Windows PowerShell 5.1; use pwsh for PowerShell 7)
  powershell -ExecutionPolicy Bypass -File .\fresh-start.ps1 -Rebuild
#>
param([string]$CpusCloud, [string]$MemCloud, [string]$CpusFog, [string]$MemFog, [string]$CpusEdge, [string]$MemEdge,
      [switch]$Rebuild, [switch]$DeleteResults, [switch]$SkipSmoke)
# Continue: native tools write progress to stderr, which Windows PowerShell 5.1 would turn into terminating
# errors under 'Stop'. Real failures still stop the script (deploy-local throws).
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
Set-Location $Root

# 1. Unblock (files from a downloaded zip carry a "from the internet" mark)
if ($env:OS -eq 'Windows_NT') { Get-ChildItem -Path $Root -Recurse -Include *.ps1 | Unblock-File }
. "$Root\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'   # common.ps1 sets 'Stop'; see the note at the top

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tmpLog = Join-Path $env:TEMP "odb-fresh-start-$stamp.log"
Start-Transcript -Path $tmpLog | Out-Null
try {
    # 2. Docker Desktop
    Write-Step 'Checking Docker Desktop'
    $null = Invoke-Native 'docker' @('info')
    if ($LASTEXITCODE -ne 0) {
        $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path $exe)) { throw "Docker is not running and Docker Desktop was not found at $exe. Start it manually and run this script again." }
        Write-Host '  starting Docker Desktop ...'
        Start-Process $exe
        $deadline = (Get-Date).AddMinutes(4)
        do { Start-Sleep -Seconds 5; $null = Invoke-Native 'docker' @('info') } until ($LASTEXITCODE -eq 0 -or (Get-Date) -gt $deadline)
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop did not become ready within 4 minutes. Open it, wait for "Engine running", and run this script again.' }
    }
    Assert-Docker
    Write-Ok 'Docker is running'

    # Limits: parameters > previous deployment > defaults
    $prev = @{}
    $compose = Join-Path $Root 'compose\local.compose.yml'
    if (Test-Path $compose) {
        try {
            $c = (Get-Content $compose | Select-Object -Skip 1) -join "`n" | ConvertFrom-Json
            foreach ($t in 'cloud', 'fog', 'edge') {
                $svc = $c.services.PSObject.Properties | Where-Object { $_.Name -like "optimusdb-$t-*" } | Select-Object -First 1
                if ($svc) { $prev["cpus_$t"] = [string]$svc.Value.cpus; $prev["mem_$t"] = [string]$svc.Value.mem_limit }
            }
        } catch { Write-Warn2 'Could not read the previous limits; using defaults' }
    }
    function Pick($given, $key, $default) { if ($given) { $given } elseif ($prev[$key]) { $prev[$key] } else { $default } }
    $L = @{ CpusCloud = (Pick $CpusCloud 'cpus_cloud' '1.5'); MemCloud = (Pick $MemCloud 'mem_cloud' '3g')
            CpusFog = (Pick $CpusFog 'cpus_fog' '1.5'); MemFog = (Pick $MemFog 'mem_fog' '3g')
            CpusEdge = (Pick $CpusEdge 'cpus_edge' '1'); MemEdge = (Pick $MemEdge 'mem_edge' '2g') }
    Write-Ok ("Limits per data store: cloud {0} CPU/{1}, fog {2} CPU/{3}, edge {4} CPU/{5}" -f $L.CpusCloud, $L.MemCloud, $L.CpusFog, $L.MemFog, $L.CpusEdge, $L.MemEdge)

    # 3. Clean up everything the testbed created
    Write-Step 'Removing the old testbed'
    if ((Get-BenchState) -eq 'running') {
        $null = Invoke-Native 'docker' @('exec', 'odb-bench', 'pkill', '-f', 'logs/campaign')      # the run-all chain first, then the runner
        $null = Invoke-Native 'docker' @('exec', 'odb-bench', 'pkill', '-f', '^python -m bench')
        Write-Ok 'Stopped any running experiment'
    }
    if (Test-Path $compose) { Invoke-Native 'docker' @('compose', '-f', $compose, 'down', '-v', '--remove-orphans') -Merge | Out-Host }
    $left = @(Invoke-Native 'docker' @('ps', '-aq', '--filter', 'name=^odb-') | Where-Object { $_ })
    if ($left.Count) { $null = Invoke-Native 'docker' (@('rm', '-f') + $left) }
    $vols = @(Invoke-Native 'docker' @('volume', 'ls', '-q', '--filter', 'label=com.docker.compose.project=odb-local') | Where-Object { $_ })
    if ($vols.Count) { $null = Invoke-Native 'docker' (@('volume', 'rm', '-f') + $vols) }
    $null = Invoke-Native 'docker' @('network', 'rm', 'odbnet')
    Write-Ok "Containers, data volumes and network removed"

    # 4. Old results
    $res = Join-Path $Root 'results'
    if ((Test-Path $res) -and (Get-ChildItem $res -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike 'fresh-start-*' })) {
        if ($DeleteResults) { Remove-Item $res -Recurse -Force -ErrorAction Stop; Write-Ok 'Old results deleted' }
        else {
            $arch = Join-Path $Root "results-archive\$stamp"
            New-Item -ItemType Directory -Force -Path (Split-Path $arch) | Out-Null
            Move-Item $res $arch -ErrorAction Stop
            Write-Ok "Old results moved to results-archive\$stamp"
        }
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $res 'logs') | Out-Null

    if ($Rebuild) {
        Write-Step 'Full rebuild requested: removing the OptimusDB clone and the testbed images'
        $src = Join-Path $Root '.src'
        if (Test-Path $src) { Remove-Item $src -Recurse -Force }
        $imgs = @(Invoke-Native 'docker' @('images', '-q', '--filter', 'reference=odb-*') | Where-Object { $_ } | Sort-Object -Unique)
        if ($imgs.Count) { $null = Invoke-Native 'docker' (@('rmi', '-f') + $imgs) }
    }

    # 5. Build and start
    $dl = @{ CpusCloud = $L.CpusCloud; MemCloud = $L.MemCloud; CpusFog = $L.CpusFog; MemFog = $L.MemFog; CpusEdge = $L.CpusEdge; MemEdge = $L.MemEdge }
    if ($Rebuild) { $dl.NoCache = $true }
    $env:ODB_FRESH_START = '1'
    & "$Root\deploy-local.ps1" @dl

    # 6. Smoke tests
    $failed = @()
    if (-not $SkipSmoke) {
        $summary = @(); $failed = @()
        foreach ($s in $AllSystems) {
            Write-Step "Smoke test: $s"
            $out = Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '-m', 'bench.cluster', 'deploy', $s, '--config', '/config/testbed.yaml') -Merge
            $code = $LASTEXITCODE
            $out | Out-Host
            $t = if ("$out" -match '"smoke_s":\s*([0-9.]+)') { $Matches[1] } else { '' }
            $summary += [pscustomobject]@{ System = $s; Result = $(if ($code -eq 0) { 'PASS' } else { 'FAIL' }); Seconds = $t }
        }
        $null = Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '-m', 'bench.cluster', 'stop-all', '--config', '/config/testbed.yaml')
        Write-Step 'Smoke test summary'
        Write-Host ('  {0,-10} {1,-6} {2}' -f 'System', 'Result', 'Visible on last host (s)')
        foreach ($r in $summary) {
            $col = if ($r.Result -eq 'PASS') { 'Green' } else { 'Red' }
            Write-Host ('  {0,-10} {1,-6} {2}' -f $r.System, $r.Result, $r.Seconds) -ForegroundColor $col
        }
        $failed = @($summary | Where-Object Result -eq 'FAIL')
        if ($failed.Count) {
            Write-Fail ("Failed: {0}. Logs: docker logs --tail 50 odb-cloud-a-<system>" -f (($failed.System) -join ', '))
        } else { Write-Ok 'All six data stores form a cluster and replicate' }
    }
    # The dashboard is removed with the other containers: start it again so older runs stay viewable
    & "$Root\dashboard.ps1" -NoBrowser | Out-Null
    Write-Ok 'Dashboard: http://localhost:8501  (older runs: Run history page, or "Archived" in the selector)'
    Write-Host ''
    if ($failed.Count) { Write-Host 'Testbed is up, but fix the failed systems before the campaign (send the logs above).' }
    else { Write-Host 'Fresh testbed ready. Next:  .\run-all.ps1 -Pilot   then   .\progress.ps1 -Watch' }
}
finally {
    Remove-Item Env:ODB_FRESH_START -ErrorAction SilentlyContinue
    Stop-Transcript | Out-Null
    $dst = Join-Path $Root "results\logs\fresh-start-$stamp.log"
    if (Test-Path (Split-Path $dst)) { Copy-Item $tmpLog $dst -Force; Write-Host "Log: results\logs\fresh-start-$stamp.log" }
    else { Write-Host "Log: $tmpLog" }
}
