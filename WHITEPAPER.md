# Technical Whitepaper: Incident-Aware Decentralized ADP Traffic Signal Control

## 1. System Identity

This repository implements a SUMO-based intelligent transportation system for incident-induced congestion recovery. The control model is a decentralized Approximate Dynamic Programming controller over a Decentralized Markov Decision Process.

Default reproducibility preset:

- Traffic demand: `RATE = 2500`
- Decision interval: `DECISION_INTERVAL = 10`
- Queue tolerance: `TAU = 1.1`
- Learning rate: `ALPHA = 0.0005`
- Discount factor: `GAMMA = 0.95`
- Queue priority weight: `ADP_QUEUE_PRIORITY_WEIGHT = 2.0`
- TD error cap: `ADP_MAX_ABS_TD_ERROR = 10.0`
- Weights: `models/historical_best/adp_agent_weights.json`

## 2. Dec-MDP Formulation

Let each signalized intersection be an agent `i in I`. The global system is represented as a Dec-MDP:

- Joint state: `S_t = (s_t^1, s_t^2, ..., s_t^n)`.
- Local state: `s_t^i` contains local incoming queues, current phase, incident-relative geometry, elapsed incident time, and action-conditioned pressure/spillback features.
- Independent action: `a_t^i in {N, E, S, W}` selects the green movement direction for intersection `i`.
- Joint action: `A_t = (a_t^1, a_t^2, ..., a_t^n)`.
- Transition: SUMO provides the real transition; ADP uses a one-step local heuristic model for lookahead.
- Reward: local queue-excess and global gridlock penalties guide incident recovery.
- Policy: each agent selects its own action using local state-action scoring without centralized joint-action optimization.

The implementation is decentralized in action selection and learning updates. Shared global incident features enter each local feature vector, but agents do not solve a centralized joint value function.

## 3. State and Feature Engineering

The ADP agent uses a linear value approximation over clipped numeric features.

Feature groups:

1. Local incoming queues  
   For each incoming edge controlled by the agent:
   `queue_feature = clip(queue / ADP_QUEUE_SCALE)`  
   Current default: `ADP_QUEUE_SCALE = 50.0`.

2. Current phase one-hot  
   Four-dimensional one-hot vector over `N, E, S, W`.

3. Incident direction one-hot  
   Four-dimensional one-hot vector describing the relative direction from the agent to the nearest incident node. If the agent is at the incident or direction cannot be inferred, the vector is all zeros.

4. Candidate action one-hot  
   Four-dimensional one-hot vector for the action being scored.

5. Per-action pressure  
   For the selected action:
   `pressure = upstream_queue - downstream_queue`  
   Feature value:
   `clip(pressure / ADP_QUEUE_SCALE)`.

6. Per-action downstream spillback  
   For the selected action:
   - `selected_downstream_queue`
   - `selected_downstream_capacity`
   - `downstream_occupancy = queue / capacity`
   - `spillback_risk = max(0, (occupancy - threshold) / (1 - threshold))`

7. Global incident features  
   - Bias term: `1.0`
   - Manhattan distance to incident scaled by `ADP_DISTANCE_SCALE = 6.0`
   - Elapsed incident time scaled by `ADP_TIME_SCALE = 120.0`
   - Incident active flag
   - Phase switch flag
   - Alignment with incident direction
   - Opposite-to-incident flag
   - Perpendicular-to-incident flag
   - Incident-active spillback interaction
   - Action-alignment distance interaction

All non-finite feature values are converted to `0.0`. Feature clipping uses `ADP_FEATURE_CLIP = 5.0` unless a feature has a stricter lower bound.

## 4. Action Scoring Heuristic

For each candidate action `a`, the agent estimates:

```text
score(a) = immediate_reward(predicted_next_queues, a)
         + GAMMA * learned_value(predicted_next_features)
         + ADP_QUEUE_PRIORITY_WEIGHT * served_queue(a) / ADP_QUEUE_SCALE
```

Where:

- `learned_value(features) = dot(weights, features)`
- `served_queue(a)` is the current queue on incoming edges served by action `a`
- `ADP_QUEUE_PRIORITY_WEIGHT = 2.0`
- Evaluation uses deterministic argmax
- Training uses epsilon-greedy exploration from `0.20` to `0.02`

This is an ADP-inspired state-action scorer. It combines a metric-aligned immediate reward, a learned linear value estimate, and a served-queue priority term.

## 5. Reward Function Design

The reward is a negative penalty. Incident edges are excluded from non-incident queue-excess pressure so the controller does not over-optimize impossible blocked queues.

Reward components:

1. Total non-incident queue penalty  
   `ADP_TOTAL_QUEUE_WEIGHT * total_nonincident_queue / ADP_QUEUE_SCALE`

2. Queue-excess penalty  
   For each non-incident edge:
   `max(0, current_queue - TAU * baseline_queue) / ADP_QUEUE_SCALE`  
   Current default: `TAU = 1.1`.

3. Phase-switch penalty  
   Applied when `action != current_phase`.  
   The switch penalty is computed from lost time:
   `SWITCH_PENALTY_SCALE * (YELLOW_SECONDS + ALL_RED_SECONDS) / DECISION_INTERVAL`.

4. Global gridlock failure penalty  
   If gridlock is detected:
   `min(ADP_GRIDLOCK_PENALTY, 5.0 + normalized_gridlock_pressure)`.

Final reward:

```text
reward = -local_queue_penalty - switch_penalty - gridlock_penalty
```

## 6. Transition Heuristic Model

SUMO is the source of truth for real transitions. The ADP lookahead uses a one-step local queue prediction:

```text
next_queues = copy(current_queues)
for blocked incident edge:
    next_queues[edge] = 0

for green edge selected by action:
    green_discharge = min(estimated_green_discharge(edge), downstream_free_space_per_edge)
    next_queues[green_edge] = max(0, current_queue - green_discharge)

for red incoming edge:
    next_queues[red_edge] = current_queue + estimated_red_arrival(edge)
```

The estimates are initialized from defaults and then updated by EWMA:

- Green discharge default: `3.0 * max(1, decision_interval / 10)`
- Red arrival default: `1.0 * interval_scale * demand_scale`
- Demand scale: `traffic_rate / 1500`
- EWMA alpha: `ADP_MODEL_EWMA_ALPHA = 0.05`
- Minimum observations before using learned model: `ADP_MIN_MODEL_OBSERVATIONS = 3`

## 7. Baselines and Evaluation

Supported controllers:

- `fixed_time_rr`: round-robin fixed-time controller.
- `greedy`: selects the phase serving the largest current local queue.
- `max_pressure`: selects the phase with largest upstream-minus-downstream pressure.
- `adp_eval`: deterministic ADP evaluation from packaged or trained weights.

Evaluation protocol:

- Incidents are generated from bidirectional internal grid segments.
- Train/eval incident split uses `TRAIN_INCIDENT_FRACTION = 0.70`.
- Evaluation controllers run on matched seeds and held-out incidents.
- Metrics include success rate, gridlock rate, time to recovery, queue-excess area, halting ratio, throughput recovery, switch rate, and paired ADP-vs-baseline comparisons.

## 8. Extension Anchors

- Vehicle rerouting timing: `routing.py`, `REROUTING_PROBABILITY`, `REROUTING_PERIOD`.
- Intra-episode step logs: `analysis.py`, `outputs/runs/<run_id>/step_logs/`.
- Real-world map ingestion: `maps.py`, `scripts/ingest_osm.py`, SUMO `netconvert`.
- Dynamic intervals and neighbor features: `decision_intervals.py`, `features.py`.

These modules are intentionally separated from the core ADP engine so experiments can expand without destabilizing reproduction of the historical-best baseline.
