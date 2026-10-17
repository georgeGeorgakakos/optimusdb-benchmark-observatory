<#
.SYNOPSIS
  Deploys the bench host: overlay endpoint (10.88.0.2) and the experiment driver container (odb-bench)
  with the harness, the generated testbed config, results\ and trace\ folders.
.EXAMPLE
  .\deploy-bench.ps1               # host name defaults to the bench row of hosts.csv ("bench")
#>
param([string]$Name = 'bench', [switch]$NoBuild)
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
$hostDir = Get-HostDir $Name
$envFile = Join-Path $hostDir '.env'
if ((Read-EnvFile $envFile).ROLE -ne 'bench') { throw "$Name is not the bench host" }
$env:HOST_DIR = $hostDir
$env:RESULTS_DIR = Join-Path $Root 'results'; $env:TRACE_DIR = Join-Path $Root 'trace'
New-Item -ItemType Directory -Force -Path $env:RESULTS_DIR, $env:TRACE_DIR, (Join-Path $env:RESULTS_DIR 'logs') | Out-Null
Set-Location $Root
if (-not $NoBuild) { Write-Step 'Building bench images'; Invoke-Compose 'bench.compose.yml' $envFile @('build') }
Write-Step 'Starting overlay endpoint and bench container'
Invoke-Compose 'bench.compose.yml' $envFile @('up', '-d')
Start-Sleep -Seconds 3
Invoke-Checked 'docker' @('exec', 'odb-bench', 'python', '-m', 'pytest', '-q', 'tests')
Write-Ok 'Harness self-test passed'
Write-Host ''
Write-Host 'Next: .\test-mesh.ps1   (all hosts must be deployed first)'
