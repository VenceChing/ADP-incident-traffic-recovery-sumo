# History Log

## 1. Repository Setup

- Created `traffic-adp-sumo-final` as the final working copy.
- Preserved the original `traffic-adp-sumo-3lane` and `ADP-incident-traffic-recovery-sumo` repositories as references.
- Kept the 3-lane scenario, `three_lane_8` action space, lane-level queue handling, incident-recovery metrics, compact residual ADP, and existing CLI workflow.

## 2. Initial Decision Order Port

- Studied the old 1-lane `DecisionOrderSchedule`.
- Ported scheduling into `src/its_signal_control/decision_intervals.py`.
- Adapted node parsing from old `ti_0_0` style to 3-lane IDs like `A0`, `B2`, `D3`.
- Added strategies:
  - `unified`
  - `distance_decay`
  - `checkerboard`
  - `ring`
  - `greedy_dynamic`
  - `random`
- Kept the default strategy as `unified`.

## 3. New Decision Order Strategies

- Reviewed the updated teammate Decision Order notes.
- Added:
  - `incident_manhattan_distance_decay`
  - `incident_manhattan_distance_premium`
  - `queue_length_decay`
  - `queue_length_premium`
- Added flat YAML presets for exploratory training/evaluation.
- Verified that these presets load through the existing no-PyYAML loader.

## 4. Neighbor Decision Features

- Confirmed that order alone only changes scheduling unless later agents can read earlier decisions.
- Added `DecisionCache` in `controllers.py`.
- Added 4-connected neighbor lookup in `DecisionOrderSchedule`.
- Added neighbor action/phase/queue inputs to:
  - ADP action selection
  - action-value estimation
  - ADP training update
- Fixed feature dimension handling by constructing neighbor feature count at agent initialization.
- Added tests for feature dimension and action-rank changes from neighbor features.

## 5. Feature and Architecture Preservation

- Preserved `three_lane_8`.
- Preserved lane-level queue keys.
- Preserved incident-action features.
- Preserved `heuristic_residual`.
- Preserved `compact_residual`.
- Preserved lane fairness and queue priority settings.

## 6. Exploratory Experiments

- Ran distance-decay Decision Order smoke/training/evaluation.
- Compared zero-weight, trained ADP, and greedy baseline.
- Found that without neighbor decision features, Decision Order mainly changed iteration order and did not provide enough input-level coordination.
- Enabled neighbor decision features.
- Tested top strategy candidates:
  - checkerboard
  - random
  - distance decay
  - incident Manhattan variants
  - queue-length variants
- Produced early 20/10 episode comparisons.

## 7. Baseline Handling

- Evaluated against:
  - greedy
  - fixed-time round robin
  - max-pressure
- Kept baselines as plain baselines with `DECISION_ORDER_STRATEGY: "unified"` and `ALLOW_NEIGHBOR_INFO: false`.
- Confirmed greedy baseline does not need Decision Order.

## 8. Checkpoint Sweeps

- Trained random Decision Order for 50 episodes.
- Evaluated random checkpoints at 10, 20, 30, 40, and 50 episodes.
- Found random zero was stronger than trained random checkpoints.
- Trained checkerboard Decision Order for 50 episodes.
- Evaluated checkerboard checkpoints at 10, 20, 30, 40, and 50 episodes.
- Found checkerboard checkpoint 20 was the best trained method.

## 9. Final Method Selection

Selected methods:

1. Checkerboard Decision Order + neighbor-aware ADP checkpoint 20
2. Random Decision Order + neighbor-aware zero-weight ADP

Final baselines:

1. Greedy
2. Max pressure
3. Fixed time

## 10. Final Artifacts

- Copied the selected trained checkpoint to:

```text
models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json
```

- Created final configs:

```text
configs/final_train_checkerboard_neighbor_adp_50.yaml
configs/final_eval_checkerboard_neighbor_adp_ckpt20.yaml
configs/final_eval_random_zero.yaml
configs/final_eval_greedy_baseline.yaml
configs/final_eval_max_pressure_baseline.yaml
configs/final_eval_fixed_time_baseline.yaml
```

- Created final summary chart:

```text
outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```
