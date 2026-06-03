# Whitepaper: Neighbor-Aware Decision Order ADP for 3-Lane Incident Recovery

## 1. Purpose

This repository extends the 3-lane SUMO adaptive traffic signal controller with a sequential Decision Order mechanism. The final system keeps the original 3-lane ADP architecture, then adds a controlled ordering layer so that agents can observe earlier neighboring decisions in the same control cycle.

The final claim is based on two selected methods:

1. **Checkerboard Decision Order + neighbor-aware ADP, checkpoint 20**  
   Main trained method. It uses learned residual ADP weights and the checkerboard order.

2. **Random Decision Order + neighbor-aware zero-weight ADP**  
   Strong ablation/simple method. It uses the same ADP action heuristic and neighbor feature channel, but does not load learned weights.

Both methods are evaluated on the 4x4 3-lane incident-recovery scenario with 24 paired episodes at demand rate 6000.

## 2. Codebase Boundary

The final implementation lives in `traffic-adp-sumo-final`. The old repositories were used only as references:

- `ADP-incident-traffic-recovery-sumo`: source of the original Decision Order concept.
- `traffic-adp-sumo-3lane`: source of the 3-lane architecture, lane-level queues, `three_lane_8` action space, compact residual ADP, and incident features.

The final version does not require modifying either source repository.

## 3. Main Implementation Files

- `src/its_signal_control/decision_intervals.py`  
  Implements `DecisionOrderSchedule` and 3-lane node parsing.

- `src/its_signal_control/controllers.py`  
  Implements ADP action selection, incident-action features, max-pressure, greedy, and `DecisionCache`.

- `src/its_signal_control/agent.py`  
  Implements compact residual features, incident-action features, neighbor feature vector sizing, action value estimation, and ADP weight updates.

- `src/its_signal_control/experiment.py`  
  Integrates Decision Order into each control cycle, fills the decision cache, passes neighbor features into action selection and learning, and records metrics.

- `src/its_signal_control/config.py`  
  Adds default-safe Decision Order config keys.

- `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json`  
  Stable copy of the selected trained ADP checkpoint.

## 4. Default Safety

Default behavior remains compatible with the original controller:

```python
DECISION_ORDER_STRATEGY = "unified"
DECISION_ORDER_RANDOM_SEED = 42
ALLOW_NEIGHBOR_INFO = False
```

With these defaults, agents are processed in the normal dictionary insertion order, no neighbor features are appended, and existing non-Decision-Order behavior is preserved.

## 5. Decision Order Schedule

`DecisionOrderSchedule` supports:

- `unified`
- `distance_decay`
- `incident_manhattan_distance_decay`
- `incident_manhattan_distance_premium`
- `checkerboard`
- `ring`
- `greedy_dynamic`
- `queue_length_decay`
- `queue_length_premium`
- `random`

The schedule is built from 3-lane node IDs such as `A0`, `B2`, `D3`. It also keeps compatibility with old IDs like `ti_0_0` when possible.

### 5.1 Checkerboard Order

Checkerboard sorts intersections by coordinate parity:

```text
(x + y) % 2
```

Then it breaks ties by `x`, `y`, and original agent order. This creates a spatially alternating update pattern. Adjacent intersections generally do not decide back-to-back in the same parity group, which reduces immediate local coupling while still making earlier decisions available to later neighbors.

This is the selected trained method because checkpoint 20 produced the best trained result.

### 5.2 Random Order

Random order shuffles the agent list with:

```python
random.Random(DECISION_ORDER_RANDOM_SEED + episode).shuffle(order)
```

The random order is deterministic for a given episode and seed. It is used as a strong ablation because zero-weight random performed very well: it showed that the sequential ordering and neighbor-aware heuristic can contribute even before learned ADP weights help.

## 6. Neighbor-Aware Sequential Decisions

The old Decision Order concept only becomes substantively useful if later agents can observe earlier decisions. The final integration therefore adds a per-cycle `DecisionCache`.

For each control cycle:

1. Build the decision order.
2. Iterate agents in that order.
3. Before an agent chooses an action, query the cache for already-decided 4-connected neighbors.
4. Pass neighbor actions, phases, and queues into the ADP feature extractor.
5. After the agent chooses, cache its action, current phase, and total queue.
6. Use the same neighbor information path during ADP updates.
7. Clear the cache at the end of the control cycle.

Only earlier decisions in the same control cycle are visible. This is intentional: the order defines information direction for that cycle.

## 7. Neighbor Features

Neighbor features are enabled only when:

```yaml
ALLOW_NEIGHBOR_INFO: true
```

The feature size is fixed at agent construction time:

```python
neighbor_feature_count = max_neighbors * (2 * num_phases + 4)
```

For the final `three_lane_8` action space with four neighbor slots:

```text
4 * (2 * 8 + 4) = 80 neighbor features
```

Each neighbor slot contains:

- one-hot earlier neighbor action
- one-hot earlier neighbor current phase
- normalized neighbor queue
- same-action indicator
- different-action indicator
- normalized queue when same action is selected

This fixes a risk found in the old implementation: neighbor features were appended without reliably resizing the agent weight vector. In the final implementation, feature dimension and weight dimension are created consistently.

## 8. ADP Architecture Used by Both Final Methods

Both selected methods use:

```yaml
ACTION_SPACE: "three_lane_8"
ADP_ACTION_SCORING_MODE: "heuristic_residual"
ADP_FEATURE_SET: "compact_residual"
ADP_INCIDENT_ACTION_FEATURES_ENABLED: true
ADP_RESIDUAL_VALUE_WEIGHT: 0.05
ADP_QUEUE_PRIORITY_WEIGHT: 2.0
ADP_LANE_FAIRNESS_WEIGHT: 0.10
ADP_LANE_FAIRNESS_MARGIN: 5.0
ALPHA: 0.00025
ADP_MAX_ABS_TD_ERROR: 5.0
SWITCH_PENALTY_SCALE: 0.04
```

### 8.1 `three_lane_8`

The 3-lane controller uses an 8-action signal space. It is more expressive than the old 1-lane architecture and uses lane-level queue keys.

### 8.2 Compact Residual Features

The compact residual feature set keeps the action-conditioned features needed for residual ADP while dropping redundant full-state phase/direction features. The compact feature vector includes:

- normalized local queue features
- selected action one-hot
- six global action features:
  - bias
  - incident-active flag
  - switch-action flag
  - normalized pressure
  - downstream occupancy
  - spillback risk
- six incident-action features when enabled
- optional neighbor features

### 8.3 Incident-Action Features

For each candidate action, the controller computes six incident-aware features:

- blocked downstream ratio
- incident-node downstream ratio
- near-incident downstream ratio
- blocked downstream ratio multiplied by served queue
- incident-node ratio multiplied by served queue
- near-incident ratio multiplied by served queue

These features are active only after the incident is active and only for the 3-lane action space.

### 8.4 Heuristic Residual Action Scoring

The ADP policy is not purely learned. It scores each action as a heuristic base plus a bounded learned residual. With zero weights, the controller still has a meaningful heuristic policy. With trained weights, ADP can adjust the heuristic ranking.

This matters for the final comparison:

- Checkerboard checkpoint 20 demonstrates useful learned residual contribution.
- Random zero demonstrates the contribution of order and neighbor-aware heuristic behavior without learned weights.

## 9. Final Selected Methods

### 9.1 Main Method: Checkerboard Neighbor ADP, Checkpoint 20

Config:

```text
configs/final_eval_checkerboard_neighbor_adp_ckpt20.yaml
```

Weight:

```text
models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json
```

Properties:

- trained ADP method
- checkerboard decision order
- neighbor features enabled
- compact residual feature set
- incident-action features enabled
- checkpoint selected from 50-episode training sweep

### 9.2 Secondary Method: Random Zero

Config:

```text
configs/final_eval_random_zero.yaml
```

Properties:

- zero learned weights
- random decision order
- neighbor features enabled
- compact residual feature set
- incident-action features enabled
- useful as ablation and simple method

Random zero has no weight artifact by design. It is reproduced by setting:

```yaml
LOAD_WEIGHTS_FOR_EVALUATION: false
DECISION_ORDER_STRATEGY: "random"
ALLOW_NEIGHBOR_INFO: true
```

## 10. Final Evaluation Results

Final summary files:

```text
outputs/runs/selected_methods_vs_baselines/combined_summary.csv
outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv
outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

| Method | Success | TTR | Queue excess | Throughput recovery |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | 79.17% | 417.3 | 18,209 | 1.164 |
| Random zero | 79.17% | 388.3 | 18,249 | 1.143 |
| Greedy | 70.83% | 408.6 | 20,462 | 1.149 |
| Max pressure | 50.00% | 419.1 | 30,815 | 1.059 |
| Fixed time | 0.00% | n/a | 69,305 | 0.919 |

Paired against greedy:

| Method | Queue excess minus greedy | Queue wins | TTR minus greedy on both-success episodes |
|---|---:|---:|---:|
| Checkerboard ckpt 20 | -2,253 | 17/24 | -15.3 |
| Random zero | -2,213 | 17/24 | -35.8 |
| Max pressure | +10,353 | 3/24 | +35.5 |
| Fixed time | +48,843 | 0/24 | n/a |

## 11. Interpretation

Checkerboard checkpoint 20 is the best main method because it is the strongest trained ADP result. It has the lowest queue excess, highest throughput recovery, and a clear paired queue improvement over greedy.

Random zero is not a trained ADP result, but it is valuable because it shows that Decision Order with neighbor-aware sequential information is meaningful even before learning. It is best described as a strong ablation or lightweight variant.

The random trained checkpoint sweep showed degradation as training continued. The checkerboard checkpoint sweep showed that checkpoint 20 is the useful training point, while later checkpoints are less stable.

## 12. Reproducibility Commands

Train checkerboard for 50 episodes and save checkpoints:

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-final
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python -m its_signal_control.cli train --preset configs\final_train_checkerboard_neighbor_adp_50.yaml --headless
```

Evaluate selected checkerboard checkpoint:

```powershell
python -m its_signal_control.cli evaluate --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml --headless
```

Evaluate random zero:

```powershell
python -m its_signal_control.cli evaluate --preset configs\final_eval_random_zero.yaml --headless
```

Evaluate baselines:

```powershell
python -m its_signal_control.cli evaluate --preset configs\final_eval_greedy_baseline.yaml --headless
python -m its_signal_control.cli evaluate --preset configs\final_eval_max_pressure_baseline.yaml --headless
python -m its_signal_control.cli evaluate --preset configs\final_eval_fixed_time_baseline.yaml --headless
```
