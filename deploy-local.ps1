<#
.SYNOPSIS
  Single-machine mode: builds all images and starts the whole testbed in this Docker Desktop.
  Eight emulated hosts (2 cloud, 2 fog, 4 edge), each with its own IP on a private Docker network,
  a control agent and the six data stores (created stopped). The bench container drives everything.
.PARAMETER CpusCloud/MemCloud/CpusFog/MemFog/CpusEdge/MemEdge
  Limits per data-store container (= per emulated host; only the system under test runs).
.PARAMETER NoBuild  Skip image builds (images already built).
.PARAMETER NoCache  Rebuild every image from scratch (docker build --no-cache).
.EXAMPLE
  .\deploy-local.ps1                                     # defaults: cloud/fog 2 CPU 3g, edge 1 CPU 2g
  .\deploy-local.ps1 -CpusEdge 0.5 -MemEdge 1g           # smaller machine (pilot only)
#>
param([string]$CpusCloud = '2', [string]$MemCloud = '3g', [string]$CpusFog = '2', [string]$MemFog = '3g',
      [string]$CpusEdge = '1', [string]$MemEdge = '2g', [string]$Subnet = '10.88.0', [switch]$NoBuild, [switch]$NoCache)
. "$PSScriptRoot\scripts\lib\common.ps1"
Assert-Docker
Set-Location $Root
$pins = Read-EnvFile (Join-Path $Root 'versions.env')

$ncpu = [int](& docker info --format '{{.NCPU}}'); $memGB = [math]::Round([double](& docker info --format '{{.MemTotal}}') / 1GB, 1)
$needC = 2 * [double]$CpusCloud + 2 * [double]$CpusFog + 4 * [double]$CpusEdge + 1.5
Write-Step "Docker Desktop VM: $ncpu CPUs, $memGB GB RAM; testbed needs about $needC CPUs while one system runs"
if ($ncpu -lt $needC) { Write-Warn2 'Fewer CPUs than the limits add up to: the emulated hosts will compete for CPU. Fine for the pilot; for the campaign lower the limits or raise processors in %UserProfile%\.wslconfig' }

if (-not $NoBuild) {
    $b = @('build') + $(if ($NoCache) { @('--no-cache') } else { @() })
    Write-Step 'Building images (first time: 30-60 min, mostly Corrosion, Iroh and OpenDHT)'
    Invoke-Checked 'docker' ($b + @('-t', 'odb-net:latest', '-f', 'images/net/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-agent:latest', '-f', 'images/agent/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-bench:latest', '-f', 'images/bench/Dockerfile', '.'))
    $optSrc = Resolve-OptimusSource $pins.OPTIMUSDB_SRC
    Invoke-Checked 'docker' ($b + @('-t', 'odb-optimusdb-base:latest', $optSrc))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-optimusdb:latest', '-f', 'images/optimusdb/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-corrosion:latest', '--build-arg', "CORROSION_REF=$($pins.CORROSION_REF)", '-f', 'images/corrosion/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-gun:latest', '-f', 'images/gun/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-autobase:latest', '-f', 'images/autobase/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-iroh:latest', '-f', 'images/iroh/Dockerfile', '.'))
    Invoke-Checked 'docker' ($b + @('-t', 'odb-opendht:latest', '--build-arg', "OPENDHT_REF=$($pins.OPENDHT_REF)", '-f', 'images/opendht/Dockerfile', '.'))
}

Write-Step 'Checking netem and iptables in the Docker Desktop kernel'
$probe = (& docker run --rm --cap-add NET_ADMIN odb-net:latest bash -c 'tc qdisc add dev eth0 root netem delay 1ms 1ms distribution normal 2>/dev/null && echo NETEM; iptables -I OUTPUT -d 192.0.2.1 -j DROP 2>/dev/null && echo IPTABLES') -join ' '
if ($probe -match 'NETEM') { Write-Ok 'tc netem available' } else { Write-Fail 'tc netem not available: link emulation (Table 7) will fail; update Docker Desktop' }
if ($probe -match 'IPTABLES') { Write-Ok 'iptables available' } else { Write-Fail 'iptables not available: partitions (E5) will fail' }

Write-Step 'Generating the single-machine layout'
Invoke-Checked 'docker' @('run', '--rm', '-v', "${Root}:/work", '-w', '/work', 'odb-net:latest', 'python3', 'tools/gen_local.py',
    '--cpus-cloud', $CpusCloud, '--mem-cloud', $MemCloud, '--cpus-fog', $CpusFog, '--mem-fog', $MemFog,
    '--cpus-edge', $CpusEdge, '--mem-edge', $MemEdge, '--subnet', $Subnet)
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'results\logs'), (Join-Path $Root 'trace') | Out-Null

$compose = Join-Path $Root 'compose\local.compose.yml'
$svc = (& docker compose -f $compose config --services)
$always = @($svc | Where-Object { $_ -eq 'bench' -or $_ -like 'net-*' -or $_ -like 'agent-*' })
$stores = @($svc | Where-Object { $_ -notin $always })
if ($stores.Count -eq 0) { throw 'compose\local.compose.yml has no data-store services: layout generation failed (see above)' }
Write-Step "Starting bench, $(($always.Count - 1) / 2) emulated hosts and their agents"
Invoke-Checked 'docker' (@('compose', '-f', $compose, 'up', '-d') + $always)
Write-Step "Creating $($stores.Count) data-store containers (stopped)"
Invoke-Checked 'docker' (@('compose', '-f', $compose, 'create') + $stores)

Start-Sleep -Seconds 5
Invoke-Checked 'docker' @('exec', 'odb-bench', 'python', '-m', 'pytest', '-q', 'tests')
Write-Ok 'Harness self-test passed'
Invoke-Bench @('python', '-m', 'bench.cluster', 'mesh', '--config', '/config/testbed.yaml')
if (-not $env:ODB_FRESH_START) {
    Write-Host ''
    Write-Host 'Testbed is up. Next:  .\systems\deploy-gun.ps1   (first smoke test), then .\run-all.ps1 -Pilot'
}
