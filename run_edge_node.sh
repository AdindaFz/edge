#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTNAME_SHORT="${HOSTNAME_OVERRIDE:-$(hostname -s)}"

if [ -n "${EDGE_INDEX:-}" ]; then
    NODE_NUMBER="$EDGE_INDEX"
else
    NODE_NUMBER="$(printf '%s' "$HOSTNAME_SHORT" | sed -n 's/^adinda\([1-9]\)$/\1/p')"
fi

if ! printf '%s' "$NODE_NUMBER" | grep -Eq '^[1-9]$'; then
    echo "Could not infer edge node number from hostname: $HOSTNAME_SHORT" >&2
    echo "Set EDGE_INDEX manually, for example: EDGE_INDEX=1 ./run_edge_node.sh" >&2
    exit 1
fi

export NODE_ID="${NODE_ID:-edge-${NODE_NUMBER}}"
export NODE_PORT="${NODE_PORT:-800${NODE_NUMBER}}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x "$ROOT_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/venv/bin/python"
fi

echo "Starting edge node"
echo "  hostname : $HOSTNAME_SHORT"
echo "  NODE_ID  : $NODE_ID"
echo "  NODE_PORT: $NODE_PORT"
echo "  python   : $PYTHON_BIN"

if [ "${1:-}" = "--print-config" ]; then
    exit 0
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m uvicorn edge.edge_node:app --host 0.0.0.0 --port "$NODE_PORT"
