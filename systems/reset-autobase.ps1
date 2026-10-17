<#
.SYNOPSIS  Bench host: Stops everything, wipes the autobase data on every host, then starts, joins and smoke-tests autobase (what the harness does before each run).
.PARAMETER Tier  Only the hosts of one tier (e.g. edge, as in E4).
#>
param([ValidateSet('cloud', 'fog', 'edge')][string]$Tier)
. "$PSScriptRoot\..\scripts\lib\common.ps1"
$a = @('python', '-m', 'bench.cluster', 'reset', 'autobase', '--config', '/config/testbed.yaml')
if ($Tier) { $a += @('--tier', $Tier) }
Invoke-Bench $a
