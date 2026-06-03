# Decision Order Changes From Latest ADP-incident-traffic-recovery-sumo

This document explains how `traffic-adp-sumo-final` adapts the latest Decision Order implementation from `ADP-incident-traffic-recovery-sumo`, and what was intentionally changed.

## Source Behavior Acknowledged

The latest `ADP-incident-traffic-recovery-sumo` now includes the core Decision Order communication idea:

- A `DecisionOrderSchedule` decides the per-cycle agent order.
- Earlier agents store their selected action, current phase, and queue in `DecisionCache`.
- Later neighboring agents read already-cached neighbor decisions.
- Neighbor actions, phases, and queues are passed into ADP action selection and ADP update.

That is the correct high-level mechanism: Decision Order matters because later agents can condition their decision on earlier neighboring decisions.

## Problem Found In The Latest ADP Repo

The pulled repo passes neighbor inputs into the code path, but the learned feature vector is not sized correctly.

Runtime diagnostic from the latest ADP repo:

```text
pulled_feature_dim 30
pulled_weights_len 30
pulled_base_len 66
pulled_neighbor_len 66
pulled_neighbor_tail_nonzero 3
```

Meaning:

- `extract_features()` returns 66 features.
- `weights` only has 30 entries.
- `get_value()` uses `zip(self.weights, features)`.
- Therefore the neighbor feature tail is truncated and cannot be learned by the ADP value function.

So the latest ADP repo has neighbor inputs in the flow, but its learned linear residual does not properly use the appended neighbor features.

## Changes Made In traffic-adp-sumo-final

### 1. Added Explicit Neighbor Feature Dimensions

File:

```text
src/its_signal_control/agent.py
```

Final now adds neighbor feature capacity only when enabled:

```python
neighbor_feature_max_neighbors
neighbor_feature_count
```

Default behavior remains unchanged:

```yaml
ALLOW_NEIGHBOR_INFO: false
```

When disabled, feature dimensions and existing non-neighbor weights stay compatible.

When enabled, the agent allocates matching feature and weight dimensions.

Diagnostic from final:

```text
final_feature_dim 32
final_weights_len 32
final_neighbor_feature_count 8
final_base_len 32
final_neighbor_len 32
```

### 2. Added Stable Neighbor Slots

File:

```text
src/its_signal_control/decision_intervals.py
```

Final adds:

```python
DecisionOrderSchedule.get_neighbors(agent_id)
```

It returns 4-connected neighbors in stable spatial order:

```text
left, right, down, up
```

Why this matters:

- If neighbor `A1` has not decided yet, its slot stays zero.
- Other neighbors do not shift into that slot.
- A learned weight for one neighbor slot keeps a stable meaning.

The latest ADP repo fills features by iterating available dictionaries, which can make feature positions depend on which neighbors have already decided.

### 3. Added Action-Conditioned Neighbor Features

File:

```text
src/its_signal_control/agent.py
```

The latest ADP version mostly appends neighbor action, phase, and queue as state features. In a linear action scorer, those values can add the same value to every candidate action, which often cannot change the action ranking.

Final adds compact action-conditioned features:

- neighbor action one-hot
- neighbor phase one-hot
- neighbor queue
- candidate action equals neighbor action
- candidate action differs from neighbor action
- neighbor queue when candidate action equals neighbor action

This lets the ADP residual learn rules such as:

```text
prefer matching an already-decided upstream neighbor
avoid matching a congested neighbor
react differently depending on candidate action
```

Controlled result:

```text
final_neighbor_weighted_q [4.64, -0.36]
```

This proves a neighbor-decision feature can change candidate action ranking.

### 4. Preserved 3-Lane Architecture

Final did not replace the 3-lane ADP design with the old 1-lane design.

Preserved:

- `three_lane_8` action space
- lane-level queue keys
- incident-action features
- `heuristic_residual`
- `compact_residual`
- 8-action signal control
- 3-lane scenario presets

Neighbor Decision Order was integrated into that architecture instead of overwriting it.

### 5. Added Per-Cycle DecisionCache To Final

Files:

```text
src/its_signal_control/controllers.py
src/its_signal_control/experiment.py
```

Final now does this each decision cycle:

```text
1. Compute decision_order.
2. For each agent in order:
   - read already-cached neighbor decisions if ALLOW_NEIGHBOR_INFO is true
   - pass neighbor inputs into ADP scoring
   - select action
   - cache this agent's action, phase, queue
3. Apply all selected signal actions after the cycle's decisions are complete.
4. Clear cache before the next decision cycle.
```

Important interpretation:

- Decision Order changes information availability.
- It does not make SUMO signal actuation asynchronous.
- Later agents see earlier decisions from the same control cycle.
- Earlier agents do not see later decisions from that cycle.

### 6. Passed Neighbor Inputs Into TD Update

File:

```text
src/its_signal_control/controllers.py
```

The current step features and next-state features both include the same neighbor context captured during action selection.

This is necessary because if action selection uses neighbor features but TD update does not, the model trains on a different feature space from the one used for decisions.

### 7. Added Config Switches

File:

```text
src/its_signal_control/config.py
```

Added:

```yaml
ALLOW_NEIGHBOR_INFO: false
ADP_NEIGHBOR_FEATURE_MAX_NEIGHBORS: 4
```

Default remains conservative:

```yaml
DECISION_ORDER_STRATEGY: "unified"
ALLOW_NEIGHBOR_INFO: false
```

Distance-decay Decision Order presets enable neighbor info:

```yaml
DECISION_ORDER_STRATEGY: "distance_decay"
ALLOW_NEIGHBOR_INFO: true
```

### 8. Avoided Stale Weight Reuse

Because enabling neighbor info changes feature dimensions, final moved the Decision Order preset output paths to `..._neighbor_info`.

Examples:

```text
outputs/runs/three_lane_training_50_decision_order_distance_decay_neighbor_info
outputs/runs/three_lane_evaluation_24_decision_order_distance_decay_neighbor_info
```

This prevents accidentally evaluating neighbor-aware ADP with old order-only weights.

## Runtime Evidence

Unit tests:

```text
43 passed
```

Focused diagnostics:

```text
pulled_feature_dim 30
pulled_weights_len 30
pulled_neighbor_len 66

final_feature_dim 32
final_weights_len 32
final_neighbor_len 32
final_neighbor_weighted_q [4.64, -0.36]
```

Smoke evaluation:

```text
Preset:
configs/three_lane_smoke_decision_order_distance_decay.yaml

Output:
outputs/runs/three_lane_smoke_decision_order_neighbor_info_probe
```

Smoke result:

```text
Greedy:
SUCCESS, TTR 501s, queue excess 20458.2704

ADP zero-weight with neighbor-aware distance-decay:
SUCCESS, TTR 364s, queue excess 12716.9948

Paired queue excess diff:
-7741.2756
```

This is a smoke test, not a statistical performance claim. It proves the mechanism runs end-to-end and that zero-weight ADP can already react through the neighbor-aware queue prediction path.

## What Still Needs Training And Evaluation

Because neighbor info changes feature dimensions, new training is required.

Train:

```powershell
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python -m its_signal_control.cli train `
  --preset configs\three_lane_training_50_decision_order_distance_decay.yaml `
  --headless
```

Evaluate:

```powershell
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python scripts\evaluate_adp_checkpoints.py `
  --preset configs\three_lane_evaluation_24_decision_order_distance_decay.yaml `
  --episodes 24 `
  --only-zero-final `
  --output-root outputs\runs\three_lane_checkpoint_selection_decision_order_neighbor_info
```

Minimum interpretation:

- If trained final beats zero-weight ADP, learning contributed beyond Decision Order heuristics.
- If zero-weight ADP beats Greedy but trained final does not improve, Decision Order and handcrafted prediction help, but learning does not.
- If neither beats Greedy, this neighbor-aware Decision Order design is not strong enough yet.

