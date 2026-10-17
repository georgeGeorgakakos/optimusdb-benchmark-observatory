<#
.SYNOPSIS  Single-machine mode: stops and removes all testbed containers. -Purge also deletes all data volumes.
#>
param([switch]$Purge)
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
$a = @('compose', '-f', (Join-Path $Root 'compose\local.compose.yml'), 'down') + $(if ($Purge) { @('-v') } else { @() })
Invoke-Checked 'docker' $a
Write-Ok "Testbed stopped$(if ($Purge) { ' and volumes deleted' })"
