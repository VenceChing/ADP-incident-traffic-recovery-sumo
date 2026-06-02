看final_submission_summary
# ADP Incident Traffic Recovery in SUMO

Traditional Chinese teammate guide: [README.zh-TW.md](README.zh-TW.md)

This repository contains a SUMO-based traffic signal control system for recovering from incident-induced congestion. The control approach models the network as a Decentralized Markov Decision Process and uses Approximate Dynamic Programming with linear value-function approximation at each signalized intersection.

The default setup packages the current historical-best configuration and weights for immediate reproduction:

- `RATE = 2500`
- `SWITCH_PENALTY_SCALE = 0.04`
- `ADP_QUEUE_PRIORITY_WEIGHT = 2.0`
- `ALPHA = 0.0005`
- `ADP_MAX_ABS_TD_ERROR = 10.0`
- Packaged weights: `models/historical_best/adp_agent_weights.json`

## Project Structure

```text
configs/                      Experiment presets: historical_best, training, evaluation, smoke
models/historical_best/        Default ADP weights and manifest
scenarios/grid_4x4/            Reproducible SUMO network, route, and GUI files
src/its_signal_control/        Core Python package
scripts/                       Reproduction, training, evaluation, and OSM ingestion scripts
tests/                         Core unit tests that do not require SUMO GUI
outputs/                       Runtime metrics, plots, weights, and step logs
```

Core modules:

- `agent.py`: ADP agent, feature extraction, linear value function, reward, and transition heuristic.
- `experiment.py`: episode loop plus training and evaluation orchestration.
- `controllers.py`: `fixed_time_rr`, `greedy`, `max_pressure`, and `adp_eval` controllers.
- `traffic_model.py`: SUMO launch arguments, incident candidates, geometry helpers, and episode status logic.
- `metrics.py`: CSV metrics, summaries, paired comparisons, plots, and weight persistence.
- `routing.py`, `analysis.py`, `maps.py`, `features.py`, `decision_intervals.py`: extension boundaries for upcoming experiments.

## Installation

Requirements:

- Python 3.10+
- SUMO 1.20+ with `sumo`, `sumo-gui`, `netconvert`, and `randomTrips.py`
- Windows PowerShell or Bash

Windows PowerShell:

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
$env:PYTHONPATH = "$PWD\src;$env:PYTHONPATH"
```

Linux/macOS:

```bash
cd traffic-adp-sumo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export SUMO_HOME=/path/to/sumo
export PATH="$SUMO_HOME/bin:$PATH"
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
```

## Reproduce the Historical-Best Result

The default reproduction run uses:

- `configs/historical_best.yaml`
- `models/historical_best/adp_agent_weights.json`
- `scenarios/grid_4x4/grid_4x4_rate2500.rou.xml`
- Headless SUMO
- Output directory: `outputs/runs/historical_best/`

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce_best.ps1
```

Cross-platform:

```bash
python -m its_signal_control.cli evaluate \
  --preset configs/historical_best.yaml \
  --weights models/historical_best/adp_agent_weights.json \
  --headless
```

Expected outputs:

- `outputs/runs/historical_best/eval_metrics.csv`
- `outputs/runs/historical_best/eval_summary.csv`
- `outputs/runs/historical_best/eval_paired_summary.csv`
- `outputs/runs/historical_best/eval_comparison.svg`
- `outputs/runs/historical_best/eval_comparison_episodes.svg`

To run with SUMO GUI on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce_best.ps1 -Gui
```

## Training and Evaluation

Train ADP from the configured preset:

```bash
python -m its_signal_control.cli train --preset configs/training.yaml --headless
```

Evaluate packaged weights against all baselines:

```bash
python -m its_signal_control.cli evaluate \
  --preset configs/evaluation.yaml \
  --weights models/historical_best/adp_agent_weights.json \
  --headless
```

Important configuration fields:

- `RUN_TRAINING`: enables ADP training.
- `RUN_EVALUATION`: enables baseline and ADP evaluation.
- `RESET_WEIGHTS_FOR_TRAINING`: clears ADP weights before training.
- `LOAD_WEIGHTS_FOR_EVALUATION`: loads weights before evaluation.
- `EVALUATION_CONTROLLERS`: default is `fixed_time_rr`, `greedy`, `max_pressure`, `adp_eval`.
- `TRAIN_EPISODES`: default is 140.
- `EVAL_EPISODES_PER_CONTROLLER`: default is 24 per controller.
- `REGENERATE_ROUTES`: regenerates the route file when intentionally enabled.
- `USE_GUI`: selects `sumo-gui` instead of headless `sumo`.
- `RENDER_STRESS`: renders queue stress polygons in GUI mode.

## Extension Guide

Vehicle rerouting timing evaluation:

- Configure `REROUTING_PERIOD`, `REROUTING_PROBABILITY`, and incident timing in `configs/*.yaml`.
- Put timing policy logic in `src/its_signal_control/routing.py`.
- Always evaluate against the same baseline set: `fixed_time_rr`, `greedy`, `max_pressure`, and `adp_eval`.

Intra-episode fine-grained analysis:

- Use `StepLogWriter` in `analysis.py` for queue, speed, reward, phase, and action logs.
- Write step-level outputs to `outputs/runs/<run_id>/step_logs/`.
- Do not commit step logs to Git.

Real-world map ingestion:

- Use `scripts/ingest_osm.py` as the `netconvert` wrapper.
- Create isolated real-world scenarios under `scenarios/real_world/`.
- Keep generated routes, networks, and outputs separate from source code.

Dynamic decision intervals and neighbor-state features:

- Define per-agent interval policies in `decision_intervals.py`.
- Extend neighbor queue/state features in `features.py`.
- Keep `ADPAgent.extract_features()` compatible with existing weight loading unless a deliberate model-version migration is added.

## Outputs

All runtime outputs should stay under `outputs/`:

- `train_metrics.csv`: per-episode training metrics.
- `eval_metrics.csv`: per-controller evaluation metrics.
- `eval_summary.csv`: success rate, gridlock rate, TTR, queue excess, and throughput recovery.
- `eval_paired_summary.csv`: paired ADP-vs-baseline comparisons.
- `adp_agent_weights.json`: trained ADP weights.
- `*.svg`: report-ready plots.

## Git Hygiene

Commit:

- `src/`
- `configs/`
- `models/historical_best/`
- `scenarios/grid_4x4/`
- `README.md`
- `README.zh-TW.md`
- `WHITEPAPER.md`
- `tests/`

Do not commit:

- Runtime files under `outputs/`
- `results*`, `history/`, `route_tmp/`
- `__pycache__/`
- Historical sweep archives

The historical-best weights are already packaged in `models/historical_best/`, so old `results_validation/` and `results_archive/` folders are intentionally excluded from Git.
