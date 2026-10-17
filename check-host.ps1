<#
.SYNOPSIS
  Pre-flight check of one Windows host before deploy-host / deploy-bench.
  Checks Docker Desktop, the kernel features the testbed needs (WireGuard, netem, iptables, TUN),
  resources against the data-store limits, the firewall rule for the overlay port, time sync, sleep settings and disk.
.PARAMETER Name        Host name from hosts.csv (bundle in out\<Name>).
.PARAMETER FixFirewall Add the inbound UDP firewall rule for the overlay port (run PowerShell as Administrator).
.PARAMETER FixTime     Point Windows Time at -NtpServer and resync (Administrator). Use the same server on all hosts.
.EXAMPLE
  .\check-host.ps1 -Name edge-a -FixFirewall -FixTime
#>
param([Parameter(Mandatory)][string]$Name, [switch]$FixFirewall, [switch]$FixTime, [string]$NtpServer = 'pool.ntp.org')
. "$PSScriptRoot\scripts\lib\common.ps1"
$failed = 0
$hostDir = Get-HostDir $Name
$cfg = Read-EnvFile (Join-Path $hostDir '.env')
Write-Step "Host $Name  role=$($cfg.ROLE)  overlay=$($cfg.OVERLAY_IP)  LAN=$($cfg.LAN_IP)"

# 1. Docker Desktop
try { Assert-Docker; Write-Ok ("Docker Desktop " + (& docker version --format '{{.Server.Version}}') + ', Linux containers') }
catch { Write-Fail $_; exit 1 }
$null = Invoke-Native 'docker' @('compose', 'version')
if ($LASTEXITCODE -eq 0) { Write-Ok 'docker compose available' } else { Write-Fail 'docker compose missing (update Docker Desktop)'; $failed++ }

# 2. LAN IP present on this machine
$ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
if ($ips -contains $cfg.LAN_IP) { Write-Ok "LAN IP $($cfg.LAN_IP) is configured on this machine" }
else { Write-Fail "LAN IP $($cfg.LAN_IP) from hosts.csv is not on this machine (found: $($ips -join ', '))"; $failed++ }

# 3. Resources of the Docker Desktop VM
$ncpu = [int](& docker info --format '{{.NCPU}}'); $memGB = [math]::Round([double](& docker info --format '{{.MemTotal}}') / 1GB, 1)
Write-Ok "Docker VM: $ncpu CPUs, $memGB GB RAM"
if ($cfg.DS_CPUS -ne '0' -and $ncpu -lt [double]$cfg.DS_CPUS) { Write-Warn2 "VM has fewer CPUs than the data-store limit ($($cfg.DS_CPUS)); raise processors in %UserProfile%\.wslconfig" }
if ($cfg.DS_MEM -match '^(\d+)g$' -and $memGB -lt ([double]$Matches[1] + 2)) { Write-Warn2 "VM RAM should exceed the data-store limit ($($cfg.DS_MEM)) by >= 2 GB; raise memory in %UserProfile%\.wslconfig and run 'wsl --shutdown'" }

# 4. Kernel features inside the Docker Desktop VM
Write-Step 'Kernel features (WireGuard, netem, iptables, TUN)'
Invoke-Checked 'docker' @('build', '-q', '-t', 'odb-net:latest', '-f', (Join-Path $Root 'images/net/Dockerfile'), $Root) | Out-Null
$probe = 'ip link add wgt type wireguard 2>/dev/null && echo WG_KERNEL; ip link del wgt 2>/dev/null; ' +
         'tc qdisc add dev eth0 root netem delay 1ms 1ms distribution normal 2>/dev/null && echo NETEM; ' +
         'iptables -I OUTPUT -d 192.0.2.1 -j DROP 2>/dev/null && echo IPTABLES; [ -c /dev/net/tun ] && echo TUN; ' +
         'command -v wireguard-go >/dev/null && echo WG_GO'
$res = (& docker run --rm --cap-add NET_ADMIN --device /dev/net/tun odb-net:latest bash -c $probe) -join ' '
if ($res -match 'WG_KERNEL') { Write-Ok 'WireGuard kernel module' } elseif ($res -match 'TUN' -and $res -match 'WG_GO') { Write-Warn2 'No WireGuard kernel module: userspace wireguard-go will be used (slower, still fine)' } else { Write-Fail 'Neither kernel WireGuard nor /dev/net/tun available'; $failed++ }
if ($res -match 'NETEM') { Write-Ok 'tc netem (delay, jitter, loss)' } else { Write-Fail 'tc netem not available in the Docker Desktop kernel: link emulation (Table 7) will not work'; $failed++ }
if ($res -match 'IPTABLES') { Write-Ok 'iptables (partitions for E5)' } else { Write-Fail 'iptables not usable: partitions (E5) will not work'; $failed++ }

# 5. Firewall: inbound UDP for the overlay
$port = $cfg.WG_PORT
$rule = Get-NetFirewallRule -DisplayName "OptimusDB overlay UDP $port" -ErrorAction SilentlyContinue
if ($rule) { Write-Ok "Firewall rule for inbound UDP $port exists" }
elseif ($FixFirewall) {
    New-NetFirewallRule -DisplayName "OptimusDB overlay UDP $port" -Direction Inbound -Protocol UDP -LocalPort $port -Action Allow -Profile Any | Out-Null
    Write-Ok "Firewall rule for inbound UDP $port added"
} else { Write-Warn2 "No firewall rule for inbound UDP $port. Re-run as Administrator with -FixFirewall, or: New-NetFirewallRule -DisplayName 'OptimusDB overlay UDP $port' -Direction Inbound -Protocol UDP -LocalPort $port -Action Allow" }

# 6. Time synchronisation (staleness metrics compare timestamps across hosts)
if ($FixTime) {
    & w32tm /config /manualpeerlist:$NtpServer /syncfromflags:manual /update | Out-Null
    Restart-Service w32time -ErrorAction SilentlyContinue; & w32tm /resync /force | Out-Null
}
$st = (Invoke-Native 'w32tm' @('/query', '/status')) -join "`n"
if ($st -match 'Source:\s*(.+)') { $src = $Matches[1].Trim(); if ($src -match 'Local CMOS|Free-running') { Write-Warn2 "Windows Time is not synchronised ($src). Use -FixTime (Administrator) with the same -NtpServer on all hosts" } else { Write-Ok "Windows Time source: $src" } }
else { Write-Warn2 'Could not query Windows Time (w32tm). Make sure the time service runs and syncs with a common NTP server' }

# 7. Sleep / power (a sleeping host breaks long runs)
$ac = (Invoke-Native 'powercfg' @('/query', 'SCHEME_CURRENT', 'SUB_SLEEP', 'STANDBYIDLE')) -join "`n"
if ($ac -match 'Current AC Power Setting Index:\s*0x00000000') { Write-Ok 'Sleep on AC power is disabled' } else { Write-Warn2 "Sleep on AC power is enabled. Disable it for the campaign: powercfg /change standby-timeout-ac 0" }

# 8. Disk space for images and data
$drive = (Get-Item $Root).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB, 0)
if ($freeGB -ge 40) { Write-Ok "$freeGB GB free on $($drive.Name):" } else { Write-Warn2 "Only $freeGB GB free on $($drive.Name): (images + 10^6-record loads need >= 40 GB)" }

Write-Host ''
if ($failed) { Write-Fail "$failed check(s) failed: fix them before deploy-host"; exit 1 } else { Write-Ok 'Host ready' }
