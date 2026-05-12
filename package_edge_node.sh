#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$ROOT_DIR/dist"
OUT_FILE="$OUT_DIR/edge-node-payload.tar.gz"

mkdir -p "$OUT_DIR"

tar \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='dist' \
    -czf "$OUT_FILE" \
    -C "$ROOT_DIR" \
    edge \
    shared \
    config.py \
    requirements.txt \
    run_edge_node.sh

echo "$OUT_FILE"
