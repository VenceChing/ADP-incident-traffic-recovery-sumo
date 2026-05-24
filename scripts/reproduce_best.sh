#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -z "${SUMO_HOME:-}" ]]; then
  echo "SUMO_HOME is not set. Install SUMO and export SUMO_HOME before running reproduction." >&2
  exit 1
fi

export PYTHONPATH="$repo_root/src:${PYTHONPATH:-}"
python -m its_signal_control.cli evaluate \
  --preset configs/historical_best.yaml \
  --weights models/historical_best/adp_agent_weights.json \
  --headless
