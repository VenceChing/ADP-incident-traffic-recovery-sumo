# Traffic ADP SUMO Final

Final 3-lane SUMO incident-recovery controller with neighbor-aware Decision Order ADP.

## Selected Methods

The final repository keeps two selected methods:

1. **Checkerboard Decision Order + neighbor-aware ADP checkpoint 20**  
   Main trained method. Uses learned ADP residual weights.

2. **Random Decision Order + neighbor-aware zero-weight ADP**  
   Strong ablation/simple method. Uses no learned weights.

The selected trained checkpoint is stored at:

```text
models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json
```

## What Was Implemented

This final version adds a Decision Order layer on top of the existing 3-lane ADP controller. The important difference from a simple scheduling loop is that later agents can consume earlier neighboring decisions from the same control cycle.

At each control cycle:

1. `DecisionOrderSchedule` builds an agent order.
2. Each agent is processed in that order.
3. If `ALLOW_NEIGHBOR_INFO: true`, the agent reads already-decided 4-connected neighbors from `DecisionCache`.
4. The agent receives neighbor action, phase, and queue features.
5. After selecting its action, the agent writes its own action, phase, and total queue into the cache.
6. The cache is cleared before the next control cycle.

The implementation keeps legacy behavior safe by default:

```yaml
DECISION_ORDER_STRATEGY: "unified"
ALLOW_NEIGHBOR_INFO: false
```

So old presets do not receive Decision Order behavior unless they explicitly enable it.

## Final Config Parameters

The two selected methods and three baselines share the same 3-lane evaluation setup:

| Parameter | Value |
|---|---|
| `SCENARIO_DIR` | `scenarios/grid_4x4_3lane` |
| `SUMO_CONFIG` | `sim.sumocfg` |
| `NETWORK_FILE` | `grid_4x4_3lane.net.xml` |
| `ROUTE_FILE_PREFIX` | `grid_4x4_3lane` |
| `RATE` | `6000` |
| `ACTION_SPACE` | `three_lane_8` |
| `EVAL_EPISODES_PER_CONTROLLER` | `24` |
| `TIME` | `1800` |
| `USE_GUI` | `false` |
| `REGENERATE_ROUTES` | `false` |

ADP method parameters:

| Parameter | Checkerboard ckpt 20 | Random zero |
|---|---|---|
| Config | `configs/final_eval_checkerboard_neighbor_adp_ckpt20.yaml` | `configs/final_eval_random_zero.yaml` |
| Controller | `adp_eval` | `adp_eval` |
| Load weights | `true` | `false` |
| Weight path | `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json` | none |
| Decision order | `checkerboard` | `random` |
| Neighbor info | `true` | `true` |
| Action scoring | `heuristic_residual` | `heuristic_residual` |
| Feature set | `compact_residual` | `compact_residual` |
| Incident-action features | `true` | `true` |
| Queue priority weight | `2.0` | `2.0` |
| Lane fairness weight | `0.10` | `0.10` |
| Residual value weight | `0.05` | `0.05` |

Baseline parameters:

| Baseline | Config | Controller | Decision order | Neighbor info |
|---|---|---|---|---|
| Greedy | `configs/final_eval_greedy_baseline.yaml` | `greedy` | `unified` | `false` |
| Max pressure | `configs/final_eval_max_pressure_baseline.yaml` | `max_pressure` | `unified` | `false` |
| Fixed time | `configs/final_eval_fixed_time_baseline.yaml` | `fixed_time_rr` | `unified` | `false` |

## Final Results

| Method | Success | TTR | Queue excess | Throughput recovery |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | 79.17% | 417.3 | 18,209 | 1.164 |
| Random zero | 79.17% | 388.3 | 18,249 | 1.143 |
| Greedy | 70.83% | 408.6 | 20,462 | 1.149 |
| Max pressure | 50.00% | 419.1 | 30,815 | 1.059 |
| Fixed time | 0.00% | n/a | 69,305 | 0.919 |

Final chart and CSVs:

```text
outputs/runs/selected_methods_vs_baselines/combined_summary.csv
outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv
outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

Paired against greedy:

| Method | Queue excess minus greedy | Queue wins | Successes | TTR minus greedy |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | -2,253 | 17/24 | 19/24 | -15.3 |
| Random zero | -2,213 | 17/24 | 19/24 | -35.8 |
| Max pressure | +10,353 | 3/24 | 12/24 | +35.5 |
| Fixed time | +48,843 | 0/24 | 0/24 | n/a |

## Requirements

- Python environment with the project runtime dependencies.
- SUMO installed.
- `SUMO_HOME` set.
- `PYTHONPATH` includes `src` and SUMO tools.

PowerShell setup:

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-final
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
```

## Final Evaluation Commands

Each command writes to the `RESULTS_DIR` defined in its preset. To run them in parallel, open separate PowerShell terminals after setting `PYTHONPATH`.

Checkerboard trained main method:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml `
  --headless
```

Random zero method:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_random_zero.yaml `
  --headless
```

Greedy baseline:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_greedy_baseline.yaml `
  --headless
```

Max-pressure baseline:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_max_pressure_baseline.yaml `
  --headless
```

Fixed-time baseline:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_fixed_time_baseline.yaml `
  --headless
```

After running all five eval commands, the final report chart can be regenerated from the CSVs. The current final chart is already stored under:

```text
outputs/runs/selected_methods_vs_baselines/
```

## Reproduce Checkerboard Training

Train 50 episodes and save checkpoints every 10 episodes:

```powershell
python -m its_signal_control.cli train `
  --preset configs\final_train_checkerboard_neighbor_adp_50.yaml `
  --headless
```

After training, evaluate a specific checkpoint:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml `
  --weights outputs\runs\final_reproduction\checkerboard_train_50\checkpoints\episode_0020.json `
  --output-dir outputs\runs\final_reproduction\checkerboard_ckpt20_eval24 `
  --headless
```

The stored final model is checkpoint 20 from the checkerboard 50-episode training sweep. If you retrain and want to replace the final model, copy the regenerated checkpoint:

```powershell
Copy-Item `
  -LiteralPath outputs\runs\final_reproduction\checkerboard_train_50\checkpoints\episode_0020.json `
  -Destination models\main_methods\checkerboard_neighbor_adp_checkpoint_0020.json `
  -Force
```

## Repository Guide

Important source files:

- `src/its_signal_control/decision_intervals.py`: decision interval and Decision Order schedule.
- `src/its_signal_control/controllers.py`: greedy, max-pressure, ADP action selection, incident features, decision cache.
- `src/its_signal_control/agent.py`: ADP features, value estimation, neighbor feature vector, TD update.
- `src/its_signal_control/experiment.py`: SUMO episode loop and Decision Order integration.
- `src/its_signal_control/config.py`: defaults and flat YAML preset loader.

Important final artifacts:

- `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json`: selected trained model.
- `outputs/runs/selected_methods_vs_baselines/combined_summary.csv`: final aggregate table.
- `outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv`: paired deltas against greedy.
- `outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg`: final comparison chart.

Important tests:

- `tests/test_decision_order_schedule.py`: order strategies and neighbor lookup.
- `tests/test_agent_features.py`: compact residual and neighbor feature behavior.
- `tests/test_config_loading.py`: final and exploratory preset loading.

Important docs:

- `WHITEPAPER.md`: detailed implementation description.
- `REPORT.md`: bilingual method and result report.
- `HISTORY_LOG.md`: chronological development record.
- `decision_order.md`: comparison with teammate Decision Order implementation.

## Configs

Use the `final_*` configs for final reproduction. Older configs are retained where they are useful for tests or experiment traceability.

## Notes

- Random zero intentionally has no weight file. It is reproduced by `LOAD_WEIGHTS_FOR_EVALUATION: false`.
- Baselines use `DECISION_ORDER_STRATEGY: "unified"` and `ALLOW_NEIGHBOR_INFO: false`.
- Default config remains `unified`, so Decision Order does not affect legacy behavior unless enabled by preset.
- Checkerboard checkpoint 20 is selected because checkpoint sweep showed checkpoint 50 degraded.
- Random trained checkpoints were not selected because random zero performed better overall.
