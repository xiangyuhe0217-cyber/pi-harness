#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export OPENVIKING_URL="${OPENVIKING_URL-http://127.0.0.1:1933}"
PYTHONPATH=src exec python3 web/server.py --host "${HOST:-0.0.0.0}" --port "${PORT:-8765}"
