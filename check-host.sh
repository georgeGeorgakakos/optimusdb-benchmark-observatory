#!/usr/bin/env bash
# Pre-flight check of one Linux host (or WSL shell) — same checks as check-host.ps1.
source "$(dirname "$0")/scripts/lib/common.sh"
NAME="${1:?usage: check-host.sh <host-name>}"
failed=0; HD="$(host_dir "$NAME")"; E="$HD/.env"
step "Host $NAME role=$(env_get "$E" ROLE) overlay=$(env_get "$E" OVERLAY_IP) LAN=$(env_get "$E" LAN_IP)"
assert_docker && ok "Docker $(docker version --format '{{.Server.Version}}')"
docker compose version >/dev/null 2>&1 && ok "docker compose available" || { fail "docker compose missing"; failed=$((failed+1)); }
LAN="$(env_get "$E" LAN_IP)"
if ip -4 addr 2>/dev/null | grep -q "inet $LAN/"; then ok "LAN IP $LAN present"; else warn "LAN IP $LAN not found on this machine (fine inside WSL; check on Windows)"; fi
ok "Docker VM: $(docker info --format '{{.NCPU}}') CPUs, $(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 )) GB RAM"
step "Kernel features"
docker build -q -t odb-net:latest -f "$ROOT/images/net/Dockerfile" "$ROOT" >/dev/null
RES="$(docker run --rm --cap-add NET_ADMIN --device /dev/net/tun odb-net:latest bash -c 'ip link add wgt type wireguard 2>/dev/null && echo WG_KERNEL; ip link del wgt 2>/dev/null; tc qdisc add dev eth0 root netem delay 1ms 1ms distribution normal 2>/dev/null && echo NETEM; iptables -I OUTPUT -d 192.0.2.1 -j DROP 2>/dev/null && echo IPTABLES; [ -c /dev/net/tun ] && echo TUN; command -v wireguard-go >/dev/null && echo WG_GO' | tr '\n' ' ')"
case "$RES" in *WG_KERNEL*) ok "WireGuard kernel module";; *TUN*WG_GO*) warn "userspace wireguard-go will be used";; *) fail "no WireGuard"; failed=$((failed+1));; esac
case "$RES" in *NETEM*) ok "tc netem";; *) fail "tc netem unavailable"; failed=$((failed+1));; esac
case "$RES" in *IPTABLES*) ok "iptables";; *) fail "iptables unusable"; failed=$((failed+1));; esac
warn "Open inbound UDP $(env_get "$E" WG_PORT) in the host firewall (e.g. sudo ufw allow $(env_get "$E" WG_PORT)/udp)"
if command -v chronyc >/dev/null; then chronyc tracking | grep -E "Reference|System time" | sed 's/^/  /'; else warn "chrony not installed: use the same NTP server on all hosts"; fi
FREE=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc 0-9); [ "$FREE" -ge 40 ] && ok "$FREE GB free" || warn "only $FREE GB free (need >= 40 GB)"
echo; [ $failed -eq 0 ] && ok "Host ready" || { fail "$failed check(s) failed"; exit 1; }
