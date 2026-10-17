<#
.SYNOPSIS
  Starts the OptimusDB benchmark dashboard (ICCS) on http://localhost:8501 and opens it in the browser.
  Live progress of the running test, a finished / stopped banner, the history of all runs (current results and
  results-archive\), per-experiment dashboards, plain-language findings and an indicative check of hypotheses H1-H5. It only reads results\ and results-archive\ (mounted read-only); it never starts or stops a test.
.PARAMETER Port       Local port (default 8501)
.PARAMETER Stop       Stop the dashboard
.PARAMETER NoBrowser  Do not open the browser
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\dashboard.ps1
  powershell -ExecutionPolicy Bypass -File .\dashboard.ps1 -Stop
#>
param([int]$Port = 8501, [switch]$Stop, [switch]$NoBrowser)
. "$PSScriptRoot\scripts\lib\common.ps1"
$ErrorActionPreference = 'Continue'
Assert-Docker
$null = Invoke-Native 'docker' @('rm', '-f', 'odb-dashboard')
if ($Stop) { Write-Ok 'Dashboard stopped'; return }

$null = Invoke-Native 'docker' @('image', 'inspect', 'odb-bench:latest')
if ($LASTEXITCODE -ne 0) { Write-Fail 'Image odb-bench:latest not found. Run .\fresh-start.ps1 first.'; exit 1 }
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'results\logs') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'results-archive') | Out-Null
# results-archive\ holds older runs (moved there by fresh-start.ps1 or copied by save-results.ps1): shown as "Archived"
$args2 = @('run', '-d', '--name', 'odb-dashboard', '-p', "127.0.0.1:${Port}:8501",
           '-v', "$(Join-Path $Root 'results'):/results:ro", '-v', "$(Join-Path $Root 'results-archive'):/archive:ro",
           '-v', "$(Join-Path $Root 'dashboard'):/app:ro")
# Sharing odb-bench's process table lets the dashboard see whether the benchmark is running.
if ((Get-BenchState) -eq 'running') { $args2 += @('--pid', 'container:odb-bench') }
$args2 += @('--entrypoint', 'python', 'odb-bench:latest', '/app/server.py', '--results', '/results', '--archive', '/archive')
$out = Invoke-Native 'docker' $args2 -Merge
if ($LASTEXITCODE -ne 0) { Write-Fail "Could not start the dashboard: $out"; exit 1 }
Start-Sleep -Seconds 2
Write-Ok "Dashboard: http://localhost:$Port"
if (-not $NoBrowser) { Start-Process "http://localhost:$Port" }
Write-Host '  Stop it with: powershell -ExecutionPolicy Bypass -File .\dashboard.ps1 -Stop'
