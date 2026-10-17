#!/bin/bash
# Bring up the WireGuard overlay (kernel module first, userspace wireguard-go as fallback) and stay alive.
set -u
CONF=/etc/wireguard/wg0.conf
if [ "$#" -gt 0 ]; then exec "$@"; fi          # tools mode: docker run odb-net python3 ...
[ -f "$CONF" ] || { echo "no WireGuard config: single-machine mode (peers on the docker network, eth0)"; exec sleep infinity; }
cp "$CONF" /tmp/wg0.conf && chmod 600 /tmp/wg0.conf
up() { wg-quick up /tmp/wg0.conf; }
case "${WG_USERSPACE:-auto}" in
  1|true)  export WG_QUICK_USERSPACE_IMPLEMENTATION=wireguard-go; up ;;
  0|false) up ;;
  *) if ! up; then echo "kernel WireGuard unavailable, using wireguard-go"; ip link del wg0 2>/dev/null
       export WG_QUICK_USERSPACE_IMPLEMENTATION=wireguard-go; up; fi ;;
esac || { echo "WireGuard failed to start"; sleep infinity; }
wg show
trap 'wg-quick down /tmp/wg0.conf; exit 0' TERM INT
while true; do sleep 3600 & wait $!; done
