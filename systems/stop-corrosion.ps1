<#
.SYNOPSIS  Bench host: Stops corrosion on every agent host (data is kept).
.PARAMETER Tier  Only the hosts of one tier (e.g. edge, as in E4).
#>
param([ValidateSet('cloud', 'fog', 'edge')][string]$Tier)
. "$PSScriptRoot\..\scripts\lib\common.ps1"
$a = @('python', '-m', 'bench.cluster', 'stop', 'corrosion', '--config', '/config/testbed.yaml')
if ($Tier) { $a += @('--tier', $Tier) }
Invoke-Bench $a
