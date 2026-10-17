<#
.SYNOPSIS  Stops and removes this host's testbed containers. -Purge also deletes all data volumes.
.EXAMPLE   .\stop-host.ps1 -Name cloud-a -Purge
#>
param([Parameter(Mandatory)][string]$Name, [switch]$Purge)
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
$hostDir = Get-HostDir $Name; $env:HOST_DIR = $hostDir
$cfg = Read-EnvFile (Join-Path $hostDir '.env')
$file = if ($cfg.ROLE -eq 'bench') { 'bench.compose.yml' } else { 'host.compose.yml' }
if ($cfg.ROLE -eq 'bench') { $env:RESULTS_DIR = Join-Path $Root 'results'; $env:TRACE_DIR = Join-Path $Root 'trace' }
$a = @('down') + $(if ($Purge) { @('-v') } else { @() })
Invoke-Compose $file (Join-Path $hostDir '.env') $a
Write-Ok "Stopped $Name$(if ($Purge) { ' and deleted its volumes' })"
