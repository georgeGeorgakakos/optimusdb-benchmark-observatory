<#  .SYNOPSIS  Bench host: shows the state of the testbed containers on every host.  #>
. "$PSScriptRoot\scripts\lib\common.ps1"
Invoke-Bench @('python', '-m', 'bench.cluster', 'status', '--config', '/config/testbed.yaml')
