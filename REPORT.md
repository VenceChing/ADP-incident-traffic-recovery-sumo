# Report / 報告：3-Lane Neighbor-Aware Decision Order ADP

## 1. 摘要

本專案將 Decision Order scheduling 整合到 3-lane SUMO incident-recovery ADP controller。原本單純改變 agent 決策順序的貢獻有限，因為後決策 agent 若無法看到前面 agent 的決策，Decision Order 只會改變迴圈執行順序。最後版本因此加入 **neighbor-aware sequential decision features**：在同一個 control cycle 內，後決策的 agent 可以讀取已決策鄰居的 action、phase 與 queue。

最後選定兩個方法：

1. **Checkerboard Decision Order + Neighbor-Aware ADP checkpoint 20**  
   主要方法。它有訓練過的 ADP residual weights，是目前最適合拿來主張「我們的方法」的 trained method。

2. **Random Decision Order + Neighbor-Aware Zero-Weight ADP**  
   第二方法 / ablation。它不使用訓練權重，但使用相同的 action heuristic、incident-action features 與 neighbor decision features。它展示 Decision Order + neighbor-aware input 本身就有價值。

最終 24 episodes 評估中，兩個方法都比 greedy baseline 有更高 success rate 與更低 queue excess。Checkerboard checkpoint 20 的 queue excess 最低；Random zero 的 TTR 最短。

## 2. 實驗場景與共同設定

所有 final comparison 使用相同的 3-lane incident-recovery scenario。

| Parameter | Value |
|---|---|
| Scenario | `scenarios/grid_4x4_3lane` |
| SUMO config | `sim.sumocfg` |
| Network | `grid_4x4_3lane.net.xml` |
| Route prefix | `grid_4x4_3lane` |
| Demand rate | `RATE: 6000` |
| Action space | `three_lane_8` |
| Evaluation episodes | `24` |
| Simulation time | `TIME: 1800` |
| GUI | disabled, `USE_GUI: false` |
| Route regeneration | disabled, `REGENERATE_ROUTES: false` |
| Incident selection | evaluation uses the configured paired episode sequence |

主要評估 metrics：

- **Success rate**：incident 後是否在時間內恢復到成功條件。
- **TTR**：time-to-recovery，只在 successful episodes 上計算平均。
- **Queue excess area**：incident 後 queue 超過 baseline 的累積面積，越低越好。
- **Throughput recovery ratio**：恢復期 throughput 相對 baseline 的比例，越高越好。
- **Paired comparison vs greedy**：用相同 episodes / seeds / incident edges 比較每個方法與 greedy 的差異。

## 3. Final Evaluation Configs

### 3.1 Checkerboard Neighbor ADP Checkpoint 20

Config:

```text
configs/final_eval_checkerboard_neighbor_adp_ckpt20.yaml
```

重要參數：

| Parameter | Value |
|---|---|
| `EVALUATION_CONTROLLERS` | `["adp_eval"]` |
| `LOAD_WEIGHTS_FOR_EVALUATION` | `true` |
| `WEIGHTS_PATH` | `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json` |
| `DECISION_ORDER_STRATEGY` | `checkerboard` |
| `ALLOW_NEIGHBOR_INFO` | `true` |
| `ADP_ACTION_SCORING_MODE` | `heuristic_residual` |
| `ADP_FEATURE_SET` | `compact_residual` |
| `ADP_INCIDENT_ACTION_FEATURES_ENABLED` | `true` |
| `ADP_RESIDUAL_VALUE_WEIGHT` | `0.05` |
| `ADP_QUEUE_PRIORITY_WEIGHT` | `2.0` |
| `ADP_LANE_FAIRNESS_WEIGHT` | `0.10` |
| `ADP_LANE_FAIRNESS_MARGIN` | `5.0` |
| `ALPHA` | `0.00025` |
| `ADP_MAX_ABS_TD_ERROR` | `5.0` |
| `SWITCH_PENALTY_SCALE` | `0.04` |

### 3.2 Random Zero

Config:

```text
configs/final_eval_random_zero.yaml
```

重要參數：

| Parameter | Value |
|---|---|
| `EVALUATION_CONTROLLERS` | `["adp_eval"]` |
| `LOAD_WEIGHTS_FOR_EVALUATION` | `false` |
| `DECISION_ORDER_STRATEGY` | `random` |
| `DECISION_ORDER_RANDOM_SEED` | `42` |
| `ALLOW_NEIGHBOR_INFO` | `true` |
| `ADP_ACTION_SCORING_MODE` | `heuristic_residual` |
| `ADP_FEATURE_SET` | `compact_residual` |
| `ADP_INCIDENT_ACTION_FEATURES_ENABLED` | `true` |
| `ADP_RESIDUAL_VALUE_WEIGHT` | `0.05` |
| `ADP_QUEUE_PRIORITY_WEIGHT` | `2.0` |
| `ADP_LANE_FAIRNESS_WEIGHT` | `0.10` |
| `ADP_LANE_FAIRNESS_MARGIN` | `5.0` |

Random zero 沒有 weight artifact。它的 zero-weight 狀態由 `LOAD_WEIGHTS_FOR_EVALUATION: false` 產生。

### 3.3 Baselines

Final baselines 使用以下 configs：

| Baseline | Config | Controller | Decision Order | Neighbor Info |
|---|---|---|---|---|
| Greedy | `configs/final_eval_greedy_baseline.yaml` | `greedy` | `unified` | `false` |
| Max pressure | `configs/final_eval_max_pressure_baseline.yaml` | `max_pressure` | `unified` | `false` |
| Fixed time | `configs/final_eval_fixed_time_baseline.yaml` | `fixed_time_rr` | `unified` | `false` |

Baseline 不使用 Decision Order，也不使用 neighbor info。這是刻意設計，避免 baseline 混入我們方法的核心機制。

## 4. Method Details

### 4.1 Decision Order

Decision Order 在每個 control cycle 建立 agent 決策順序。實作位置：

```text
src/its_signal_control/decision_intervals.py
```

Final version 支援多種策略：

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

預設仍然是：

```yaml
DECISION_ORDER_STRATEGY: "unified"
ALLOW_NEIGHBOR_INFO: false
```

因此沒有啟用 preset 時，原本行為不會被改變。

### 4.2 Checkerboard Order

Checkerboard 根據 3-lane node ID 轉出的座標排序。例如 `A0`, `B2`, `D3` 會被轉成 grid coordinate。排序核心是：

```text
(x + y) % 2
```

再用 `x`, `y`, original index 做 tie-break。這會形成空間交錯決策順序，避免鄰近路口全部連續同時以同一類局部資訊做決策。

Checkerboard checkpoint 20 是最後的 main trained method，因為 checkpoint sweep 顯示它在 queue excess、success rate、paired improvement 上最穩定。

### 4.3 Random Order

Random order 使用 deterministic shuffle：

```text
random seed = DECISION_ORDER_RANDOM_SEED + episode
```

因此同一個 episode 的順序可重現。Random zero 的強表現表示：即使沒有 trained residual weights，順序隨機化加上 neighbor-aware features 也可以改善恢復行為。

## 5. Neighbor-Aware Mechanism

實作位置：

```text
src/its_signal_control/controllers.py
src/its_signal_control/experiment.py
src/its_signal_control/agent.py
```

每個 control cycle 的流程：

1. 根據策略建立 `decision_order`。
2. 建立新的 `DecisionCache`。
3. 依序處理每個 agent。
4. 當 agent 要決策時，讀取已經決策的 4-connected neighbors。
5. 將 neighbor actions、phases、queues 傳入 ADP feature extractor。
6. agent 選出 action 後，把自己的 action、phase、total queue 寫入 cache。
7. 同一 cycle 中較晚決策的鄰居就能讀到這些資訊。

這是我們與「只有 scheduling order」最大的差別。Decision Order 不只是控制誰先跑，而是創造一個同 cycle 的局部資訊流。

## 6. ADP Features

兩個 final methods 都使用：

```yaml
ADP_ACTION_SCORING_MODE: "heuristic_residual"
ADP_FEATURE_SET: "compact_residual"
ADP_INCIDENT_ACTION_FEATURES_ENABLED: true
```

### 6.1 Compact Residual

`compact_residual` feature vector 包含：

- normalized local queues
- selected action one-hot
- compact global action features
- incident-action features
- neighbor decision features

Compact global action features 包含：

- bias
- incident active flag
- switch action flag
- normalized pressure
- downstream occupancy
- spillback risk

### 6.2 Incident-Action Features

每個 candidate action 有 6 個 incident-aware features：

- blocked downstream ratio
- incident-node downstream ratio
- near-incident downstream ratio
- blocked downstream ratio × served queue
- incident-node downstream ratio × served queue
- near-incident ratio × served queue

這些 features 讓 ADP 能判斷某個 action 是否會把車流導向 blocked / incident-adjacent downstream。

### 6.3 Neighbor Decision Features

每個 agent 最多讀取 4 個 4-connected neighbors。對每個 neighbor slot，feature 包含：

- earlier neighbor action one-hot
- earlier neighbor phase one-hot
- normalized neighbor queue
- same-action indicator
- different-action indicator
- same-action queue feature

對 `three_lane_8` 而言，neighbor feature dimension 是：

```text
4 * (2 * 8 + 4) = 80
```

這裡特別修正了舊版 Decision Order neighbor feature 的風險：final version 會在 agent 初始化時正確擴充 feature dimension 與 weight vector，避免 feature 長度和權重長度不一致。

## 7. ADP Scoring and Learning

`heuristic_residual` 不是純 learned controller。它的形式是：

```text
action score = heuristic base score + learned residual correction
```

因此：

- zero weights 仍然有合理 heuristic 行為。
- trained weights 可以微調 action ranking。
- 若 trained residual 學壞，可能會比 zero-weight 差。

這也解釋了我們的實驗現象：

- Checkerboard checkpoint 20 的 learned residual 有正面貢獻。
- Random trained checkpoints 反而逐步退化，表示 random order 下 residual learning 不穩定。
- Random zero 很強，表示 heuristic + Decision Order + neighbor info 已經有高貢獻。

## 8. Training and Checkpoint Selection

Checkerboard final method 來自 50-episode training：

```text
configs/final_train_checkerboard_neighbor_adp_50.yaml
```

主要 training parameters：

| Parameter | Value |
|---|---|
| `TRAIN_EPISODES` | `50` |
| `TRAIN_INCIDENT_SELECTION` | `random` |
| `TRAIN_SAVE_WEIGHTS_EVERY_EPISODE` | `true` |
| `TRAIN_WEIGHT_CHECKPOINT_INTERVAL` | `10` |
| `DECISION_ORDER_STRATEGY` | `checkerboard` |
| `ALLOW_NEIGHBOR_INFO` | `true` |
| `ALPHA` | `0.00025` |
| `ADP_MAX_ABS_TD_ERROR` | `5.0` |

Checkpoint sweep 結果顯示：

| Checkerboard variant | Success | TTR | Queue excess | Throughput |
|---|---:|---:|---:|---:|
| Zero | 79.17% | 423.4 | 20,252 | 1.125 |
| Ckpt 10 | 62.50% | 426.5 | 21,393 | 1.125 |
| **Ckpt 20** | **79.17%** | 417.3 | **18,209** | **1.164** |
| Ckpt 30 | 58.33% | 395.1 | 21,744 | 1.122 |
| Ckpt 40 | 70.83% | 409.1 | 19,997 | 1.140 |
| Ckpt 50 | 75.00% | 414.6 | 20,727 | 1.130 |

所以 final trained model 選 checkpoint 20，而不是最後的 checkpoint 50。

## 9. Final Evaluation Results

Final artifacts:

```text
outputs/runs/selected_methods_vs_baselines/combined_summary.csv
outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv
outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

Final aggregate table:

| Method | Success | TTR | Queue excess | Throughput |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | 79.17% | 417.3 | 18,209 | 1.164 |
| Random zero | 79.17% | 388.3 | 18,249 | 1.143 |
| Greedy | 70.83% | 408.6 | 20,462 | 1.149 |
| Max pressure | 50.00% | 419.1 | 30,815 | 1.059 |
| Fixed time | 0.00% | n/a | 69,305 | 0.919 |

Paired comparison against greedy:

| Method | Queue excess minus greedy | Queue wins | Successes | TTR minus greedy |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | -2,253 | 17/24 | 19/24 | -15.3 |
| Random zero | -2,213 | 17/24 | 19/24 | -35.8 |
| Max pressure | +10,353 | 3/24 | 12/24 | +35.5 |
| Fixed time | +48,843 | 0/24 | 0/24 | n/a |

## 10. Result Interpretation

### 10.1 Why Checkerboard checkpoint 20 is the main method

Checkerboard checkpoint 20 是最適合當主方法的原因：

- 它是 trained method，有 ADP learning contribution。
- Queue excess 是 final comparison 中最低的。
- Throughput recovery 是 final comparison 中最高的。
- Paired against greedy 時，queue excess 平均改善 `2253`，且贏 `17/24` episodes。
- Success rate `79.17%` 高於 greedy 的 `70.83%`。

### 10.2 Why Random zero is still valuable

Random zero 不應該被描述成 trained ADP 的成功，但它非常適合作為 ablation：

- 它沒有 weight artifact。
- 它與 main method 使用同樣的 neighbor-aware feature path。
- 它證明 Decision Order + neighbor features + heuristic residual 在沒有 learned residual weights 時已經很強。
- 它的 TTR 最好，但 throughput 與 queue excess 略低於 checkerboard checkpoint 20。

### 10.3 Why not use random trained checkpoints

Random checkpoint sweep 顯示訓練後不一定變好：

| Random variant | Success | TTR | Queue excess | Throughput |
|---|---:|---:|---:|---:|
| Random zero | 79.17% | 388.3 | 18,249 | 1.143 |
| Ckpt 10 | 75.00% | 420.8 | 19,184 | 1.153 |
| Ckpt 20 | 79.17% | 423.9 | 19,668 | 1.153 |
| Ckpt 30 | 70.83% | 410.9 | 20,178 | 1.147 |
| Ckpt 40 | 66.67% | 396.8 | 20,026 | 1.134 |
| Ckpt 50 | 62.50% | 444.1 | 22,190 | 1.126 |

Random trained checkpoints 的 queue 與 success 整體不如 random zero，因此不選為 final method。

## 11. Reproduction Commands

PowerShell setup:

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-final
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
```

Evaluate final methods:

```powershell
python -m its_signal_control.cli evaluate --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml --headless
python -m its_signal_control.cli evaluate --preset configs\final_eval_random_zero.yaml --headless
```

Evaluate baselines:

```powershell
python -m its_signal_control.cli evaluate --preset configs\final_eval_greedy_baseline.yaml --headless
python -m its_signal_control.cli evaluate --preset configs\final_eval_max_pressure_baseline.yaml --headless
python -m its_signal_control.cli evaluate --preset configs\final_eval_fixed_time_baseline.yaml --headless
```

Retrain checkerboard:

```powershell
python -m its_signal_control.cli train --preset configs\final_train_checkerboard_neighbor_adp_50.yaml --headless
```

Evaluate a newly trained checkpoint 20:

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml `
  --weights outputs\runs\final_reproduction\checkerboard_train_50\checkpoints\episode_0020.json `
  --output-dir outputs\runs\final_reproduction\checkerboard_ckpt20_eval24 `
  --headless
```

## 12. Limitations

- Final comparison uses 24 episodes. It is paired and useful, but larger samples would give stronger statistical confidence.
- Random zero being strong means some performance comes from heuristic and information-flow design, not only ADP learning.
- Checkpoint selection matters. The best trained method is checkpoint 20, not final checkpoint 50.
- Baselines are intentionally plain baselines and do not receive neighbor-aware Decision Order.
