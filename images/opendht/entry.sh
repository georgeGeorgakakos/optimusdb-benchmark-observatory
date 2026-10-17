#!/bin/bash
# Private DHT network (-n 42), service mode, no rate limit (-U, so the benchmark is not throttled),
# REST proxy on 8000. In-memory storage (OpenDHT default).
set -a; [ -f /runtime/opendht.env ] && . /runtime/opendht.env; set +a
ARGS=(-s -U -n 42 -p 4222 --proxyserver 8000)
[ -n "${DHT_BOOTSTRAP:-}" ] && ARGS+=(-b "$DHT_BOOTSTRAP")
exec dhtnode "${ARGS[@]}"
