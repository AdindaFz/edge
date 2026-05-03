#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/edge_node.py" ]; then
  REPO_ROOT="$SCRIPT_DIR"
else
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

export NODE_ID=edge-9
export NODE_PORT=8009
export NODE_TIER=high

cd "$REPO_ROOT"
if [ -x "$REPO_ROOT/venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" edge/edge_node.py
