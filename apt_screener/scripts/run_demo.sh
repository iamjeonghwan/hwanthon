#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m apt_screener fetch-shuttle --offline
python3 -m apt_screener screen --demo --offline --top 10
