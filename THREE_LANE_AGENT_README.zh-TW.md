# 3-Lane ADP Experiment Agent Handoff README

這份文件是給後續 agent 或開發者接手 3-lane 實驗用的工作說明。它描述的是目前 `traffic-adp-sumo-3lane` worktree 裡的 3-lane 方法、已實作內容、已知結果、待跑實驗，以及主要候選方法。請不要把這份文件當成原始 proposal 的重述；目前實作已經和 proposal 有明顯差異，後續工作應以現有 codebase 為準。

## 工作目標

目前主線目標是測試：在 3-lane richer action space 下，ADP-like controller 是否能比 Greedy baseline 更穩定，尤其是在 incident 後的 recovery 階段。

目前最重要的觀察是：

- 3-lane action design 確實讓 ADP-like heuristic 有機會 beat Greedy。
- 但目前真正表現最好的不是 learned value weights，而是 `zero_weights` 的 heuristic residual policy。
- 也就是說，目前學習到的 residual correction 還沒有穩定提供幫助，甚至常常會傷害原本強的 heuristic。
- 最新方向是減少 redundant features，讓 residual learning 的自由度變小，然後拉長 training。

## Worktree 與保護原則

3-lane 實驗位於：

```text
D:\Projects\AI\Final\traffic-adp-sumo-3lane
```

原本 2-lane 開發可能仍在另一個 session 的：

```text
D:\Projects\AI\Final\traffic-adp-sumo
```

重要原則：

- 3-lane 工作只修改 `traffic-adp-sumo-3lane`。
- 不要回頭改 `traffic-adp-sumo` 的 2-lane worktree。
- 不要改 `two_lane_8` semantics。
- 3-lane 應維持 additive design：新增 `three_lane_*` configs/scripts/tests，而不是破壞 2-lane。
- 如果需要比較 2-lane 和 3-lane，只比較結果，不要共用輸出資料夾。

## 3-Lane Scenario

Scenario 路徑：

```text
scenarios/grid_4x4_3lane
```

核心設計：

- 每個 normal edge 有 3 lanes。
- lane `0`：right turn。
- lane `1`：straight。
- lane `2`：left turn 與 U-turn。
- U-turn 保留，並歸到 left lane，因為現有 routes/network connection 仍可能包含 U-turn movement。
- Demand calibrated rate 目前使用 `RATE = 6000`。

相關檔案：

```text
scripts/create_three_lane_scenario.py
scripts/validate_three_lane_scenario.py
scripts/calibrate_three_lane_demand.py
src/its_signal_control/scenario_validation.py
tests/test_three_lane_scenario.py
```

Validation 應檢查：

- normal edges 是否都是 3 lanes。
- SUMO connection 是否符合 R/S/L lane split。
- 每個 signal action 是否 conflict-free。
- incident reroute 是否排除 blocked incident edge。
- route generation 是否持續到 configured `TIME`。

## 3-Lane Action Space

Action space label：

```yaml
ACTION_SPACE: "three_lane_8"
```

目前 8 個 actions：

```text
0 NS_SR
1 EW_SR
2 N_LSR_E_R
3 S_LSR_W_R
4 E_LSR_S_R
5 W_LSR_N_R
6 NS_L_EW_R
7 NS_R_EW_L
```

語意：

- `NS_SR`：North/South straight + right lanes。
- `EW_SR`：East/West straight + right lanes。
- `N_LSR_E_R`：North all movements，加上 East right。
- `S_LSR_W_R`：South all movements，加上 West right。
- `E_LSR_S_R`：East all movements，加上 South right。
- `W_LSR_N_R`：West all movements，加上 North right。
- `NS_L_EW_R`：North/South left，加上 East/West right。
- `NS_R_EW_L`：North/South right，加上 East/West left。

這個 action space 的目的不是單純增加 lane capacity，而是增加 traffic light 可選擇的 compatible movement groups。Greedy、Max Pressure、ADP 都應該在完整 8-action space 上比較。3-lane fixed-time baseline 目前也 cycle 全 8 個 actions，作為主要公平比較。

相關檔案：

```text
src/its_signal_control/actions.py
src/its_signal_control/controllers.py
src/its_signal_control/traffic_model.py
```

## Timing Rule

目前已保留的 timing rule：

- Incident 前 warmup：無論最終 controller 是誰，都用 fixed-time。
- fixed-time interval：20 秒。
- incident 後 fixed-time：20 秒。
- incident 後 ADP / Greedy / Max Pressure：10 秒。

相關邏輯：

```text
src/its_signal_control/experiment.py
src/its_signal_control/decision_intervals.py
```

## Decision Order Integration

`traffic-adp-sumo-final` 新增 3-lane Decision Order 支援，詳細說明見：

```text
DECISION_ORDER_3LANE_README.zh-TW.md
```

目前主方法是：

```yaml
DECISION_ORDER_STRATEGY: "distance_decay"
```

預設仍是 `unified`，會保持原本 3-lane 行為。這次只整合 decision ordering，不移植舊 1-lane 的 neighbor-decision features，避免破壞 3-lane feature dimension 與既有 weights 相容性。

## Baselines

目前主要 baseline：

```yaml
EVALUATION_CONTROLLERS:
  ["fixed_time_rr", "greedy", "max_pressure", "adp_eval"]
```

### fixed_time_rr

3-lane main comparison 裡，fixed-time 應 cycle 所有 8 個 `three_lane_8` actions。這和 2-lane 的 naive fixed-time 不同；2-lane 曾被要求只 cycle `[NS_SR, EW_SR, NS_L, EW_L]`，但不要把該規則套到 3-lane。

### greedy

Greedy 在完整 8-action space 裡選擇能服務最多當前 queue 的 action。這是目前最強 baseline，也是主要要 beat 的方法。

### max_pressure

Max Pressure 也在完整 8-action space 裡選擇。實驗結果顯示它在目前 3-lane incident setting 下比 Greedy 和 ADP 弱很多，可能因為 downstream/incident blockage 使 pressure signal 不夠穩。

## ADP-Like Method Overview

ADP agent 位於：

```text
src/its_signal_control/agent.py
```

Agent 建立位於：

```text
src/its_signal_control/traffic_model.py
```

Action 選擇與 controller integration 位於：

```text
src/its_signal_control/controllers.py
```

每個 signalized intersection 有一個 decentralized `ADPAgent`。目前不是 full RL，也不是 deep RL，而是 linear value-function approximation + heuristic action scoring。

### Queue Keys

3-lane mode 使用 lane/movement-level queues，而不是只有 edge-level queues。對每個 incoming approach，queue key 應反映 R/S/L movement lane。這讓 agent 可以看到 right/straight/left lane 的不平衡，而不是只看到 approach aggregate queue。

### Reward

Reward 主要是 penalty 形式：

- non-incident queues 超過 baseline 的 excess queue。
- total non-incident queue penalty。
- switch penalty。
- gridlock penalty。
- lane fairness imbalance penalty。

Incident edge 本身會從部分 queue penalty 中排除，避免 agent 因 blocked edge 的 unavoidable queue 被過度懲罰。

### Lane Fairness

3-lane fairness 會比較同一 approach 的 R/S/L queue imbalance：

```text
imbalance = max(R, S, L) - min(R, S, L)
penalty = max(0, imbalance - margin)
```

目前 configs 常用：

```yaml
ADP_LANE_FAIRNESS_WEIGHT: 0.10
ADP_LANE_FAIRNESS_MARGIN: 5.0
```

### Incident-Action Features

3-lane incident-action features 是 v2 之後的重要設計，位於：

```text
src/its_signal_control/controllers.py
get_incident_action_features()
```

每個 candidate action 會產生 6 個 incident-action features：

```text
blocked_downstream_ratio
incident_node_downstream_ratio
near_incident_downstream_ratio
blocked_ratio * served_queue
incident_node_ratio * served_queue
near_ratio * served_queue
```

這些 feature 只在：

```yaml
ADP_INCIDENT_ACTION_FEATURES_ENABLED: true
ACTION_SPACE: "three_lane_8"
```

時啟用。

## ADP Scoring Modes

目前 relevant scoring modes：

### `value`

舊版線性 value mode。3-lane v1 使用過。效果沒有穩定 beat Greedy。

### `heuristic_residual`

目前最重要的 3-lane mode。

Action score：

```text
score(action) =
  immediate_reward(action)
  + ADP_QUEUE_PRIORITY_WEIGHT * served_queue(action) / ADP_QUEUE_SCALE
  + ADP_RESIDUAL_VALUE_WEIGHT * learned_value(features)
```

如果 weights 全部為 0，則：

```text
score(action) =
  immediate_reward(action)
  + queue_priority
```

也就是 strong heuristic policy。

目前最強結果來自 `zero_weights`，因此它實際上是 heuristic residual 的 zero-weight fallback，而不是 learned residual。

### `residual_lookahead`

2-lane 曾使用的 candidate，在 3-lane 主線目前不是主要方向。除非要開新的 comparison branch，否則不要先改這條。

## Feature Sets

### Full Feature Set

Default：

```yaml
ADP_FEATURE_SET: "full"
```

Full feature vector 包含：

- lane/movement queue features。
- current phase one-hot。
- incident direction one-hot。
- selected action one-hot。
- 14 global/action features。
- optional 6 incident-action features。

這個 feature set 表達能力高，但 redundancy 很多。先前訓練結果顯示 learned weights 容易加 noise。

### Compact Residual Feature Set

新增 candidate：

```yaml
ADP_FEATURE_SET: "compact_residual"
```

Compact feature vector 保留：

- lane/movement queues。
- selected action one-hot。
- 6 compact global features：
  - bias。
  - incident active。
  - switch flag。
  - selected pressure。
  - downstream occupancy。
  - spillback risk。
- 6 incident-action features。

Compact feature vector 移除：

- current phase one-hot。
- incident direction one-hot。
- time feature。
- distance feature。
- aligned/opposite/perpendicular global incident-direction encodings。
- duplicated spillback/incident interaction terms。

原因：

- phase one-hot 和 switch flag/action one-hot 有重疊。
- incident direction one-hot 與 incident-action features 的目標有重疊，但比較粗。
- time/distance feature 很可能讓 value function 對 seed/incident combination overfit。
- 目前我們要學的是 small residual correction，不是讓 linear value function 重新主導 policy。

實作位置：

```text
src/its_signal_control/config.py
src/its_signal_control/agent.py
src/its_signal_control/traffic_model.py
tests/test_agent_features.py
```

## Current Main Results

本節是目前最重要的 experiment record。後續 agent 接手時，請先看這些 outputs，不要只看最新 config。這個專案目前的進展不是線性「越訓練越好」，而是經過多次失敗後發現：action-space 和 heuristic design 有效，但 learned residual 尚未穩定有效。

### Result Record Index

值得優先查看的資料夾：

```text
outputs/runs/three_lane_evaluation
outputs/runs/three_lane_training_50_incident_features
outputs/runs/three_lane_evaluation_50_incident_features
outputs/runs/three_lane_checkpoint_selection
outputs/runs/three_lane_evaluation_ep0040_incident_features
outputs/runs/three_lane_training_50_incident_residual
outputs/runs/three_lane_checkpoint_selection_residual
outputs/runs/three_lane_evaluation_best_residual_48
outputs/runs/three_lane_smoke_compact_residual_probe
```

目前待產生或待檢查的 v4 outputs：

```text
outputs/runs/three_lane_training_200_compact_residual
outputs/runs/three_lane_checkpoint_selection_compact_residual
outputs/runs/three_lane_evaluation_best_compact_residual_48
outputs/runs/three_lane_overnight_compact_residual
```

每個 evaluation output 通常要看：

```text
eval_metrics.csv
eval_summary.csv
eval_paired_summary.csv
eval_comparison.svg
```

每個 training output 通常要看：

```text
train_metrics.csv
training_metrics.svg
adp_agent_weights.json
checkpoints/
```

Checkpoint selection output：

```text
checkpoint_selection_summary.csv
checkpoint_eval_preset.yaml
zero_weights/
episode_XXXX/
final/
```

重要：`outputs/` 是 runtime records，不一定適合 commit，但對實驗判斷非常重要。不要在未備份前刪除這些資料夾。

### v1: 3-lane full random baseline ADP

Output：

```text
outputs/runs/three_lane_evaluation
```

Summary：

```text
ADP success:       0.667
ADP mean queue:    21592.05
Greedy success:    0.708
Greedy mean queue: 20462.22
ADP - Greedy:      +1129.84
```

Interpretation：

- v1 did not beat Greedy。
- Full learned value approach not sufficient。
- 這是第一次確認「只把 3-lane action space 接上舊 ADP」不夠。
- 問題動機：需要讓 agent 更直接知道 incident edge location 與 action downstream movement 的關係。

### v2: incident-action features

Output：

```text
outputs/runs/three_lane_evaluation_50_incident_features
```

50-episode trained final weights：

```text
ADP success:       0.708
ADP mean queue:    20708.96
Greedy success:    0.708
Greedy mean queue: 20462.22
ADP - Greedy:      +246.74
```

Interpretation：

- v2 improved over v1。
- It became competitive with Greedy but still slightly worse on mean queue。
- 這表示 incident-action interaction features 的方向是有價值的。
- 但 learned value weights 還沒有穩定超過 Greedy。

Checkpoint selection over 8 seeds once selected `episode_0040`, but full 24-seed evaluation showed that was overfit:

```text
episode_0040 ADP success:    0.625
episode_0040 ADP mean queue: 23016.52
ADP - Greedy:                +2554.30
```

Lesson：

- Small checkpoint-selection seed sets are not reliable。
- Use at least 24 paired eval episodes for checkpoint selection。
- 這個錯誤很重要：不要因為 8-seed checkpoint selection 好看就採用某個 checkpoint。
- `episode_0040` 是一個明確反例，說明 checkpoint selection 本身也會 overfit incident seeds。

### v3: heuristic residual

Configs：

```text
configs/three_lane_training_50_incident_residual.yaml
configs/three_lane_evaluation_50_incident_residual.yaml
configs/three_lane_smoke_incident_residual.yaml
```

Key settings：

```yaml
ADP_VARIANT_LABEL: "three_lane_8_incident_action_heuristic_residual_v3"
ADP_ACTION_SCORING_MODE: "heuristic_residual"
ADP_RESIDUAL_VALUE_WEIGHT: 0.10
ADP_INCIDENT_ACTION_FEATURES_ENABLED: true
ADP_QUEUE_PRIORITY_WEIGHT: 2.0
ADP_LANE_FAIRNESS_WEIGHT: 0.10
ALPHA: 0.0005
ADP_MAX_ABS_TD_ERROR: 10.0
```

48-episode all-controller result for selected best candidate：

```text
outputs/runs/three_lane_evaluation_best_residual_48
```

Summary：

```text
ADP residual zero-weight:
  success rate:            0.792
  mean queue excess area:  20671.90
  mean TTR success only:   412.74

Greedy:
  success rate:            0.646
  mean queue excess area:  23674.52
  mean TTR success only:   426.26

Max Pressure:
  success rate:            0.396
  mean queue excess area:  33824.02

Fixed-time:
  success rate:            0.000
  mean queue excess area:  69862.16
```

Paired ADP vs Greedy：

```text
pairs:                  48
mean queue diff:        -3002.62
median queue diff:      -1822.11
95% CI:                 [-5015.62, -1060.81]
ADP success rate:       0.792
Greedy success rate:    0.646
success diff:           +0.146
```

Interpretation：

- This is the best result so far。
- ADP beats Greedy under the 48-episode paired evaluation。
- But selected candidate was `zero_weights`。
- Therefore, the policy improvement comes from the heuristic residual structure, not from learned weights。
- 這是目前最重要的決策轉折：我們證明 3-lane ADP-like controller 可以 beat Greedy，但不是因為學習成功，而是因為 action heuristic 設計成功。
- 後續方法不應盲目「train longer」；應該先限制 learned residual 的破壞力。

Incident-group behavior：

```text
ADP better groups:
  A2A3|A3A2: mean diff -5909.6, ADP wins 5/6
  C3D3|D3C3: mean diff -5470.8, ADP wins 4/6
  A0B0|B0A0: mean diff -5169.5, ADP wins 5/6
  B2C2|C2B2: mean diff -3385.6, ADP wins 5/6

Greedy still better group:
  C1D1|D1C1: mean diff +891.4, ADP wins 2/6
```

Lesson：

- Incident-location/action heuristic works。
- Learned residual correction is still unreliable。
- More training alone is not enough if feature vector remains redundant/noisy。

### v3 Checkpoint Selection Details

Output：

```text
outputs/runs/three_lane_checkpoint_selection_residual
```

`checkpoint_selection_summary.csv` showed:

```text
zero_weights:
  episodes:                 24
  success rate:             0.792
  mean queue excess area:   18677.66
  ADP - Greedy mean queue:  -1784.56

episode_0050/final:
  episodes:                 24
  success rate:             0.792
  mean queue excess area:   19254.93
  ADP - Greedy mean queue:  -1207.28
```

Interpretation：

- final trained weights were not terrible, but still worse than zero weights。
- learned residual moved in a somewhat useful direction compared with older v2, but did not beat the no-learning heuristic。
- 這支持「降低 residual weight、降低 alpha、減 feature」的下一步，而不是直接放棄 learning。

### Smoke / Debug Records

有用的 smoke records：

```text
outputs/runs/three_lane_smoke_probe
outputs/runs/three_lane_smoke_incident_features_probe
outputs/runs/three_lane_smoke_incident_residual_probe
outputs/runs/three_lane_smoke_compact_residual_probe
```

用途：

- 確認 SUMO episode 可以跑完。
- 確認 ADP feature vector dimension 沒壞。
- 確認 zero-weight fallback 沒有誤載 stale weights。
- 快速比較單一 incident seed 下 Greedy vs ADP 的大致行為。

不要用 smoke result 做最終 performance claim。Smoke 只用於 runtime validation。

### Demand / Incident Variance Records

Demand calibration record：

```text
outputs/runs/three_lane_demand_calibration
```

目前選用：

```text
RATE = 6000
```

原因：

- 3-lane capacity 比 2-lane 高，沿用舊 demand 會太容易。
- `RATE=6000` 在 pre-incident traffic 仍可維持穩定，但 post-incident recovery 有足夠壓力。
- final claims 應在 calibrated 3-lane setting 內比較 controller，不要把 1-lane/2-lane/3-lane raw throughput 直接互比。

Incident/seed variance probe：

```text
outputs/runs/three_lane_incident_seed_probe
```

重要觀察：

- Performance variation 很可能主要來自 incident edge selection，而不是 vehicle generation seed。
- 因為車流量高時，route/vehicle distribution 較接近穩態，incident location 對 recovery difficulty 的影響更大。
- 這也是後來加入 incident-action interaction features 的主要動機。

## Current Pending Experiment: v4 Compact Residual Long Training

This is the current recommended next experiment.

Goal：

- Reduce redundant features。
- Train longer。
- Keep heuristic base strong。
- Let learned residual make smaller corrections instead of dominating。

Configs：

```text
configs/three_lane_training_200_compact_residual.yaml
configs/three_lane_evaluation_200_compact_residual.yaml
configs/three_lane_smoke_compact_residual.yaml
```

Script：

```text
scripts/run_compact_residual_long_experiment.ps1
```

Key settings：

```yaml
ADP_VARIANT_LABEL: "three_lane_8_compact_residual_v4"
ADP_ACTION_SCORING_MODE: "heuristic_residual"
ADP_FEATURE_SET: "compact_residual"
ADP_RESIDUAL_VALUE_WEIGHT: 0.05
ADP_INCIDENT_ACTION_FEATURES_ENABLED: true
ADP_QUEUE_PRIORITY_WEIGHT: 2.0
ADP_LANE_FAIRNESS_WEIGHT: 0.10
ALPHA: 0.00025
ADP_MAX_ABS_TD_ERROR: 5.0
TRAIN_EPISODES: 200
TRAIN_WEIGHT_CHECKPOINT_INTERVAL: 20
```

The lower `ADP_RESIDUAL_VALUE_WEIGHT`, lower `ALPHA`, and lower TD cap are intentional. The point is not to let learned weights override the heuristic, but to see whether compact residual features can add a stable small correction.

Run：

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-3lane
powershell -ExecutionPolicy Bypass -File scripts\run_compact_residual_long_experiment.ps1
```

This script does：

1. Train compact residual ADP for 200 random-incident episodes。
2. Evaluate zero/final/checkpoints on 24 paired episodes。
3. Select best candidate by mean queue excess。
4. Evaluate selected candidate against all controllers for 48 episodes。

Morning outputs：

```text
outputs/runs/three_lane_training_200_compact_residual/train_metrics.csv
outputs/runs/three_lane_checkpoint_selection_compact_residual/checkpoint_selection_summary.csv
outputs/runs/three_lane_evaluation_best_compact_residual_48/eval_summary.csv
outputs/runs/three_lane_evaluation_best_compact_residual_48/eval_paired_summary.csv
```

Logs：

```text
outputs/runs/three_lane_overnight_compact_residual/logs/train_compact_residual_200.log
outputs/runs/three_lane_overnight_compact_residual/logs/checkpoint_selection_24.log
outputs/runs/three_lane_overnight_compact_residual/logs/best_compact_residual_all_controllers_48.log
```

Smoke validation already passed：

```text
configs/three_lane_smoke_compact_residual.yaml
```

One-episode smoke result：

```text
ADP compact zero-weight queue excess: 16195.4
Greedy queue excess:                  20458.3
```

## Main Method Candidates

### Candidate A: v3 zero-weight heuristic residual

Status：

- Best proven result so far。
- No learned weight benefit。
- Should be treated as current strong baseline / floor for ADP-like methods。

Pros：

- Beats Greedy in 48-episode paired evaluation。
- Simple and robust。
- No training required。

Cons：

- Not really learning。
- May be hard to justify as ADP unless framed as ADP-like heuristic controller with value component disabled。
- Still loses on some incident groups, especially `C1D1|D1C1`。

Use when：

- Need best current demo/evaluation result。
- Need stable comparison against Greedy。

### Candidate B: v3 trained full residual

Status：

- Trained 50 episodes。
- Checkpoints sometimes improve but not consistently。
- Final weights did not beat zero-weight heuristic。

Pros：

- Uses the current ADP residual update machinery。
- Incident-action features are useful。

Cons：

- Feature vector likely too redundant。
- Learned value correction can damage heuristic action ordering。
- Checkpoint selection can overfit if seed set too small。

Use when：

- Need comparison showing why compact feature reduction was introduced。

### Candidate C: v4 compact residual, 200 episodes

Status：

- Implemented。
- Smoke passed。
- Long experiment pending。

Pros：

- Smaller feature vector。
- Less redundant state/action encoding。
- Lower residual weight and lower TD cap reduce damage risk。
- More training may produce a useful small correction。

Cons：

- Not evaluated yet。
- May still select `zero_weights` if learned residual remains noisy。
- Dropping incident direction one-hot may help generalization, but if incident-action features miss some topology detail, it could hurt specific incident groups。

Use when：

- Current recommended next experiment。

### Candidate D: Per-incident-group residual tuning

Status：

- Not implemented。

Idea：

- Keep v3/v4 heuristic base。
- Add small incident-group-specific correction or weighting。
- Focus on groups where ADP still loses to Greedy, especially `C1D1|D1C1`。

Pros：

- Directly targets observed failure modes。
- Could improve remaining weak incident groups。

Cons：

- Higher risk of overfitting to the fixed 4x4 incident candidates。
- Harder to justify as general method。

Use when：

- v4 compact residual still fails on specific incident groups。

### Candidate E: Conservative residual regularization

Status：

- Partially approximated by v4 lower alpha/residual weight/TD cap。
- Explicit L2/L1 regularization not implemented。

Ideas：

- Weight decay during update。
- Per-feature learning-rate scaling。
- Freeze high-risk features。
- Clip residual contribution directly:

```text
score = heuristic_score + clamp(residual_weight * V(features), -delta, +delta)
```

Pros：

- Directly prevents learned value from overriding strong heuristic。
- Useful if compact residual learns some signal but has outlier failures。

Cons：

- More hyperparameters。
- Needs careful validation。

Use when：

- v4 checkpoints show some trained candidates close to zero-weight but unstable。

### Candidate F: Residual target redesign

Status：

- Not implemented。

Current update still uses TD-style value learning. But the action score is mostly heuristic. A more aligned target may be to learn correction to heuristic ranking or to predict paired outcome advantage.

Ideas：

- Learn residual only from cases where chosen action beats heuristic expectation。
- Learn action advantage relative to zero-weight heuristic。
- Use validation-selected residual checkpoint。

Pros：

- Better aligned with current discovery that heuristic is strong。

Cons：

- Larger implementation change。
- Needs more careful experiment design。

Use when：

- Compact residual still cannot make learned weights useful。

## Recommended Experiment Workflow

For any new 3-lane method:

1. Add a new variant label。
2. Add separate train/eval/smoke configs。
3. Run 1-episode smoke。
4. Run training with checkpoint saving。
5. Run checkpoint selection on at least 24 paired eval episodes。
6. Run selected best candidate on 48 all-controller eval episodes。
7. Compare against v3 zero-weight residual, not only against Greedy。

Minimum comparison files：

```text
eval_summary.csv
eval_paired_summary.csv
checkpoint_selection_summary.csv
train_metrics.csv
```

Important metrics：

- success rate。
- gridlock rate。
- mean TTR success only。
- mean queue excess area。
- median queue excess area。
- throughput recovery。
- switch rate。
- lane fairness imbalance。
- ADP-vs-Greedy paired queue diff。
- ADP-vs-Greedy confidence interval。

## How To Run Common Commands

Set environment in PowerShell：

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-3lane
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
```

Run compact smoke：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\three_lane_smoke_compact_residual.yaml `
  --headless `
  --output-dir outputs\runs\three_lane_smoke_compact_residual_probe
```

Run v4 compact long experiment：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_compact_residual_long_experiment.ps1
```

Run v3 residual checkpoint selection only：

```powershell
python scripts\evaluate_adp_checkpoints.py `
  --preset configs\three_lane_evaluation_50_incident_residual.yaml `
  --checkpoint-dir outputs\runs\three_lane_training_50_incident_residual\checkpoints `
  --final-weights outputs\runs\three_lane_training_50_incident_residual\adp_agent_weights.json `
  --output-root outputs\runs\three_lane_checkpoint_selection_residual `
  --episodes 24
```

Run final selected v3 residual 48-eval resume：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_best_residual_eval_48.ps1
```

## Known Pitfalls

### Do not trust small checkpoint selection

8-seed checkpoint selection previously picked a checkpoint that failed on 24-seed eval. Use 24 as minimum for selection, 48 for final all-controller comparison.

### `zero_weights` may be the best candidate

If `zero_weights` wins, that means training did not improve the policy. This is not a bug by itself. It means the heuristic action scoring is strong and learned residual is not yet useful.

### Missing weights path is intentional for zero weights

Checkpoint evaluation uses a missing weights file path to force zero in-memory weights. Make sure no stale `agent_weights.json` exists inside the scenario directory, or zero-weight eval could accidentally load legacy weights.

### PowerShell UTF-8 BOM issue

The project has a lightweight YAML parser. PowerShell `Set-Content -Encoding utf8` on older Windows PowerShell may write a BOM, which can make the first YAML key invalid. Scripts that generate temporary presets should use:

```powershell
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($Path, [string[]]$Lines, $Utf8NoBom)
```

### Do not compare unfair action spaces

Every controller in a 3-lane comparison should operate on the same `three_lane_8` action space unless explicitly running an ablation.

### Do not overclaim ADP learning

Current best result is ADP-like heuristic residual with zero learned weights. It is fair to say the ADP-like controller beats Greedy, but not fair to say learned ADP weights beat Greedy unless a trained checkpoint/final weights actually wins.

## Acceptance Criteria For Next Useful Result

v4 compact residual should be considered successful only if:

- A trained checkpoint or final weights beats `zero_weights` on 24-seed checkpoint selection。
- The selected trained candidate remains competitive on 48-episode all-controller eval。
- ADP-vs-Greedy paired queue diff stays negative with CI mostly or fully below zero。
- Success rate is at least close to v3 zero-weight residual (`0.792`)。
- It does not improve mean queue by sacrificing fairness or causing high failure on specific incident groups。

If v4 again selects `zero_weights`, the conclusion should be:

- Feature reduction helped runtime simplicity but did not solve learning usefulness。
- Next promising direction is explicit residual regularization or redesigning the residual learning target。

## Decision Timeline And Motivation

這段是給後續 agent 快速理解「為什麼走到現在這個方向」。不要只看最後的 v4 config，因為很多選擇是由前面失敗結果推導出來的。

### Step 1: 3-lane richer action space

Problem：

- 2-lane setting 下 ADP-like method 已經接近 plateau。
- Greedy baseline 仍很強。
- 單純增加 lane capacity 不是目標；目標是讓 signal actions 有更豐富的 compatible movement groups。

Decision：

- 建立獨立 `grid_4x4_3lane` scenario。
- 每個 approach 使用 R/S/L lane split。
- 設計 `three_lane_8` mixed action space。

Expected benefit：

- ADP 可以選擇比 Greedy 更有 recovery structure 的 phase。
- Incident 附近可以透過 mixed compatible movements 提供 relief。

Observed：

- richer action space 本身有效，但舊 ADP features 不足。

### Step 2: v1 full ADP failed to beat Greedy

Problem：

- v1 使用 full feature/value approach 後，ADP mean queue worse than Greedy。
- 表示 agent 有 action space，但不懂 incident location/action interaction。

Decision：

- 不先改 network/action space。
- 改 features：加入 incident-action downstream relation。

Record：

```text
outputs/runs/three_lane_evaluation
```

### Step 3: v2 incident-action features made ADP competitive

Problem：

- Agent 需要知道某 action 是否會把車導向 blocked/near-incident downstream。
- 只用 incident direction 或 distance 太粗。

Decision：

- 加入 6 個 incident-action features。

Observed：

- v2 ADP 變得接近 Greedy。
- 但 trained weights still slightly worse。
- 小 seed checkpoint selection 會 overfit。

Records：

```text
outputs/runs/three_lane_training_50_incident_features
outputs/runs/three_lane_evaluation_50_incident_features
outputs/runs/three_lane_checkpoint_selection
outputs/runs/three_lane_evaluation_ep0040_incident_features
```

### Step 4: v3 heuristic residual beat Greedy, but with zero weights

Problem：

- Learned value function 不穩，但 heuristic action score 明顯有價值。
- 需要讓 ADP-like controller 保留 heuristic base，而不是讓 noisy value 完全主導。

Decision：

- 使用 `heuristic_residual`：

```text
score = immediate reward + queue priority + residual_weight * learned_value
```

Observed：

- 48-episode eval 中 ADP beat Greedy。
- 但 selected candidate 是 `zero_weights`。

Records：

```text
outputs/runs/three_lane_training_50_incident_residual
outputs/runs/three_lane_checkpoint_selection_residual
outputs/runs/three_lane_evaluation_best_residual_48
```

Interpretation：

- This validates the heuristic/action design。
- This does not validate learned residual weights。

### Step 5: v4 compact residual is the current hypothesis

Problem：

- Full feature vector 太大且 redundant。
- Learned residual correction 有太多機會 overfit 或改壞 action ordering。

Decision：

- 新增 `ADP_FEATURE_SET: "compact_residual"`。
- 移除 phase/direction/time/distance 等高 redundancy features。
- 保留 queue、action one-hot、pressure/downstream/spillback、incident-action features。
- Train longer，但更 conservative：

```text
TRAIN_EPISODES = 200
ADP_RESIDUAL_VALUE_WEIGHT = 0.05
ALPHA = 0.00025
ADP_MAX_ABS_TD_ERROR = 5.0
```

Pending record：

```text
outputs/runs/three_lane_training_200_compact_residual
outputs/runs/three_lane_checkpoint_selection_compact_residual
outputs/runs/three_lane_evaluation_best_compact_residual_48
```

Expected possible outcomes：

- Best case：trained compact checkpoint beats zero_weights and Greedy。
- Acceptable case：trained compact checkpoint matches zero_weights with smaller variance。
- Negative case：zero_weights still wins。Then learned residual target needs redesign, not just longer training。
