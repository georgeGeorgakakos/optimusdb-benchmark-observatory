<#
.SYNOPSIS  Bench host: applies (default) or clears the Table 7 link profiles on every host's overlay interface.
.EXAMPLE   .\netem.ps1            .\netem.ps1 -Clear
#>
param([switch]$Clear)
. "$PSScriptRoot\scripts\lib\common.ps1"
$act = if ($Clear) { 'clear-netem' } else { 'netem' }
Invoke-Bench @('python', '-m', 'bench.cluster', $act, '--config', '/config/testbed.yaml')
