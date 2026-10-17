<#
.SYNOPSIS  Bench host: Starts opendht on every agent host (other systems are stopped first), joins the nodes into one cluster and checks that a write on the first host is readable on the last.
.PARAMETER Tier  Only the hosts of one tier (e.g. edge, as in E4).
#>
param([ValidateSet('cloud', 'fog', 'edge')][string]$Tier)
. "$PSScriptRoot\..\scripts\lib\common.ps1"
$a = @('python', '-m', 'bench.cluster', 'deploy', 'opendht', '--config', '/config/testbed.yaml')
if ($Tier) { $a += @('--tier', $Tier) }
Invoke-Bench $a
