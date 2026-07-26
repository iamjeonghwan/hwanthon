#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m apt_screener web --host 0.0.0.0 --port "${PORT:-8000}"
