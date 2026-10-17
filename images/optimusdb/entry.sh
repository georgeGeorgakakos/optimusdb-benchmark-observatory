#!/bin/bash
# Runs only the OptimusDB agent (the base image's supervisord would also start llama-server).
# Metadata enrichment is disabled for E1-E6: the baselines have no equivalent feature.
set -a; [ -f /runtime/optimusdb.env ] && . /runtime/optimusdb.env; set +a
cd /root
exec /usr/local/bin/optimusdb -http-port 8089 -ipfs-port 4001 ${OPTIMUSDB_ARGS:-}
