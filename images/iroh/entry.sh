#!/bin/bash
set -a; [ -f /runtime/iroh.env ] && . /runtime/iroh.env; set +a
export PORT=7006 DATA_DIR=/data/iroh TICKET="${TICKET:-}"
exec iroh_http
