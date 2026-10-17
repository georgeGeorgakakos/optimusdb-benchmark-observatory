<#
.SYNOPSIS
  Stops the running experiment or campaign chain. Finished runs stay in results\ (the run in progress is lost);
  start again with the same run-all / run-experiment command and finished runs are skipped.
#>
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
$null = Invoke-Native 'docker' @('exec', 'odb-bench', 'pkill', '-f', 'logs/campaign')      # the chain first, so it does not start the next scenario
$null = Invoke-Native 'docker' @('exec', 'odb-bench', 'pkill', '-f', '^python -m bench')
Start-Sleep -Seconds 2
$null = Invoke-Native 'docker' @('exec', 'odb-bench', 'python', '-m', 'bench.cluster', 'stop-all', '--config', '/config/testbed.yaml')
Write-Ok 'Experiment stopped and all data stores stopped. Finished runs are kept in results\.'
