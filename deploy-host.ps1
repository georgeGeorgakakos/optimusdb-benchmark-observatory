<#
.SYNOPSIS
  Deploys one agent host (cloud, fog or edge): builds all images, starts the overlay (odb-net) and the
  control agent (odb-agent), and creates the six data-store containers in the stopped state.
  The bench host starts, joins and wipes them one system at a time (systems\*.ps1, run-experiment.ps1).
.PARAMETER Name      Host name from hosts.csv.
.PARAMETER NoBuild   Reuse images that are already built on this machine.
.EXAMPLE
  .\deploy-host.ps1 -Name cloud-a
#>
param([Parameter(Mandatory)][string]$Name, [switch]$NoBuild)
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
$hostDir = Get-HostDir $Name
$envFile = Join-Path $hostDir '.env'
$cfg = Read-EnvFile $envFile
if ($cfg.ROLE -eq 'bench') { throw "$Name is the bench host: use deploy-bench.ps1" }
$env:HOST_DIR = $hostDir
Set-Location $Root

if (-not $NoBuild) {
    Write-Step "Building the OptimusDB base image from $($cfg.OPTIMUSDB_SRC)"
    $optSrc = Resolve-OptimusSource $cfg.OPTIMUSDB_SRC
    Invoke-Checked 'docker' @('build', '-t', 'odb-optimusdb-base:latest', $optSrc)
    Write-Step 'Building the testbed images (first build of Corrosion, Iroh and OpenDHT takes 15-30 min)'
    Invoke-Compose 'host.compose.yml' $envFile @('build')
}
Write-Step 'Starting overlay network and control agent'
Invoke-Compose 'host.compose.yml' $envFile @('up', '-d', 'net', 'agent')
Write-Step 'Creating the data-store containers (stopped)'
Invoke-Compose 'host.compose.yml' $envFile (@('create') + $AllSystems)

Start-Sleep -Seconds 3
$wg = (Invoke-Native 'docker' @('exec', 'odb-net', 'wg', 'show', 'wg0') -Merge) -join "`n"
if ($LASTEXITCODE -eq 0) { Write-Ok 'WireGuard overlay is up'; Write-Host $wg } else { Write-Fail "WireGuard did not start: docker logs odb-net`n$wg" }
$h = (Invoke-Native 'docker' @('exec', 'odb-agent', 'wget', '-qO-', '--header', "x-token: $($cfg.AGENT_TOKEN)", 'http://127.0.0.1:9100/health') -Merge) -join ''
if ($h -match 'true') { Write-Ok "Agent listening on $($cfg.OVERLAY_IP):9100" } else { Write-Fail "Agent not answering: docker logs odb-agent`n$h" }
Write-Host ''
Write-Host "Host $Name deployed. When all hosts are up, run test-mesh.ps1 on the bench host."
