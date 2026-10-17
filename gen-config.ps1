<#
.SYNOPSIS
  Generates the per-host bundles (out\<host>\.env, WireGuard config) and the harness config from hosts.csv.
  Run once, on any one machine with Docker Desktop; then copy the whole folder (including out\) to every host.
.EXAMPLE
  .\gen-config.ps1                 # uses .\hosts.csv
  .\gen-config.ps1 -Hosts my.csv
#>
param([string]$Hosts = 'hosts.csv')
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
Set-Location $Root
if (-not (Test-Path $Hosts)) { throw "$Hosts not found. Copy hosts.example.csv to hosts.csv and fill in names, roles and LAN IPs." }
Write-Step 'Building the network/tools image (odb-net)'
Invoke-Checked 'docker' @('build', '-q', '-t', 'odb-net:latest', '-f', 'images/net/Dockerfile', '.')
Write-Step "Generating bundles from $Hosts"
Invoke-Checked 'docker' @('run', '--rm', '-v', "${Root}:/work", '-w', '/work', 'odb-net:latest', 'python3', 'tools/gen_config.py', $Hosts, 'out')
Write-Host ''
Write-Host 'Next: copy this whole folder (with out\) to every host, then on each host run'
Write-Host '  .\check-host.ps1 -Name <host>   and   .\deploy-host.ps1 -Name <host>   (bench host: .\deploy-bench.ps1)'
