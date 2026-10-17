#!/bin/bash
# Renders /etc/corrosion/config.toml from the overlay address and the bootstrap list set by the harness.
set -a; [ -f /runtime/corrosion.env ] && . /runtime/corrosion.env; set +a
BOOT=""
IFS=',' read -ra B <<< "${BOOTSTRAP:-}"
for b in "${B[@]}"; do [ -n "$b" ] && BOOT="$BOOT\"$b\","; done
cat > /etc/corrosion/config.toml <<EOF
[db]
path = "/data/corrosion.db"
schema_paths = ["/etc/corrosion/schemas"]

[gossip]
addr = "${OVERLAY_IP}:8787"
client_addr = "0.0.0.0:0"
bootstrap = [${BOOT%,}]
plaintext = true

[api]
addr = "0.0.0.0:8080"

[admin]
path = "/tmp/corrosion-admin.sock"

[log]
format = "plaintext"
EOF
exec corrosion agent -c /etc/corrosion/config.toml
