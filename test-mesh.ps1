<#
.SYNOPSIS
  Bench host: checks that every host's agent answers over the overlay, measures the clock offset of each host,
  and pings every pair of hosts across the overlay. Run after all hosts are deployed and before any experiment.
#>
. "$PSScriptRoot\scripts\lib\common.ps1"
Invoke-Bench @('python', '-m', 'bench.cluster', 'mesh', '--config', '/config/testbed.yaml')
