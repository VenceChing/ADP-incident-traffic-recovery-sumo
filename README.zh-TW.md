# Traffic ADP SUMO Final 使用說明

這是最終版 3-lane SUMO incident-recovery controller。主要新增功能是 **neighbor-aware Decision Order ADP**：每個 control cycle 內，agent 依照指定順序決策，後決策的 agent 可以讀取先決策鄰居的 action、phase 與 queue。

## 最終選定方法

本 repo 最後保留兩個主要方法：

1. **Checkerboard Decision Order + neighbor-aware ADP checkpoint 20**  
   主要 trained method。使用 ADP residual 權重。

2. **Random Decision Order + neighbor-aware zero-weight ADP**  
   強 ablation / 輕量方法。不使用訓練權重。

主要權重檔：

```text
models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json
```

Random zero 沒有權重檔，因為它刻意使用 zero weights。

## 實作重點

這個 final version 不是只把 agent 的迴圈順序換掉，而是讓 Decision Order 真的影響後續 agent 的輸入資訊。

每個 control cycle 的流程：

1. `DecisionOrderSchedule` 產生 agent 順序。
2. agent 依照順序逐一決策。
3. 如果 `ALLOW_NEIGHBOR_INFO: true`，agent 會讀取同一 cycle 中已經決策的 4-connected neighbors。
4. 讀到的資訊包含 neighbor action、phase、queue。
5. agent 決策後，把自己的 action、phase、total queue 寫入 `DecisionCache`。
6. 下一個較晚決策的鄰居就能把這些資訊當成 features。
7. 每個 control cycle 結束後清空 cache。

預設仍然保持原本行為：

```yaml
DECISION_ORDER_STRATEGY: "unified"
ALLOW_NEIGHBOR_INFO: false
```

因此只有 final presets 或其他明確啟用的 config 會使用 Decision Order + neighbor features。

## Final Config 主要參數

兩個選定方法與三個 baseline 使用相同的 3-lane evaluation setup：

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

ADP 方法設定：

| Parameter | Checkerboard ckpt 20 | Random zero |
|---|---|---|
| Config | `configs/final_eval_checkerboard_neighbor_adp_ckpt20.yaml` | `configs/final_eval_random_zero.yaml` |
| Controller | `adp_eval` | `adp_eval` |
| Load weights | `true` | `false` |
| Weight path | `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json` | 無 |
| Decision order | `checkerboard` | `random` |
| Neighbor info | `true` | `true` |
| Action scoring | `heuristic_residual` | `heuristic_residual` |
| Feature set | `compact_residual` | `compact_residual` |
| Incident-action features | `true` | `true` |
| Queue priority weight | `2.0` | `2.0` |
| Lane fairness weight | `0.10` | `0.10` |
| Residual value weight | `0.05` | `0.05` |

Baseline 設定：

| Baseline | Config | Controller | Decision order | Neighbor info |
|---|---|---|---|---|
| Greedy | `configs/final_eval_greedy_baseline.yaml` | `greedy` | `unified` | `false` |
| Max pressure | `configs/final_eval_max_pressure_baseline.yaml` | `max_pressure` | `unified` | `false` |
| Fixed time | `configs/final_eval_fixed_time_baseline.yaml` | `fixed_time_rr` | `unified` | `false` |

## 最終結果

| Method | Success | TTR | Queue excess | Throughput recovery |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | 79.17% | 417.3 | 18,209 | 1.164 |
| Random zero | 79.17% | 388.3 | 18,249 | 1.143 |
| Greedy | 70.83% | 408.6 | 20,462 | 1.149 |
| Max pressure | 50.00% | 419.1 | 30,815 | 1.059 |
| Fixed time | 0.00% | n/a | 69,305 | 0.919 |

最終圖表與 CSV：

```text
outputs/runs/selected_methods_vs_baselines/combined_summary.csv
outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv
outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg
```

和 greedy 的 paired comparison：

| Method | Queue excess minus greedy | Queue wins | Successes | TTR minus greedy |
|---|---:|---:|---:|---:|
| Checkerboard ckpt 20 | -2,253 | 17/24 | 19/24 | -15.3 |
| Random zero | -2,213 | 17/24 | 19/24 | -35.8 |
| Max pressure | +10,353 | 3/24 | 12/24 | +35.5 |
| Fixed time | +48,843 | 0/24 | 0/24 | n/a |

## 環境設定

需要：

- Python project dependencies
- SUMO
- `SUMO_HOME`
- `PYTHONPATH` 包含 `src` 與 SUMO tools

PowerShell：

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo-final
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
```

## 執行最終評估

每個 command 會輸出到 preset 裡設定的 `RESULTS_DIR`。如果要平行跑，可以開多個 PowerShell terminal，各自設定 `PYTHONPATH` 後執行。

Checkerboard trained main method：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml `
  --headless
```

Random zero：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_random_zero.yaml `
  --headless
```

Greedy baseline：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_greedy_baseline.yaml `
  --headless
```

Max-pressure baseline：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_max_pressure_baseline.yaml `
  --headless
```

Fixed-time baseline：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_fixed_time_baseline.yaml `
  --headless
```

目前 final chart / CSV 已經放在：

```text
outputs/runs/selected_methods_vs_baselines/
```

## 重現 Checkerboard Training

訓練 50 episodes，並每 10 episodes 儲存 checkpoint：

```powershell
python -m its_signal_control.cli train `
  --preset configs\final_train_checkerboard_neighbor_adp_50.yaml `
  --headless
```

評估 checkpoint 20：

```powershell
python -m its_signal_control.cli evaluate `
  --preset configs\final_eval_checkerboard_neighbor_adp_ckpt20.yaml `
  --weights outputs\runs\final_reproduction\checkerboard_train_50\checkpoints\episode_0020.json `
  --output-dir outputs\runs\final_reproduction\checkerboard_ckpt20_eval24 `
  --headless
```

如果重新訓練後要替換 final model，把新的 checkpoint 20 複製到 main model 位置：

```powershell
Copy-Item `
  -LiteralPath outputs\runs\final_reproduction\checkerboard_train_50\checkpoints\episode_0020.json `
  -Destination models\main_methods\checkerboard_neighbor_adp_checkpoint_0020.json `
  -Force
```

## 程式碼導覽

- `src/its_signal_control/decision_intervals.py`  
  Decision Order schedule 與 3-lane node ID parsing。

- `src/its_signal_control/controllers.py`  
  greedy、max-pressure、ADP action selection、incident-action features、DecisionCache。

- `src/its_signal_control/agent.py`  
  ADP feature extraction、neighbor feature vector、value estimation、TD update。

- `src/its_signal_control/experiment.py`  
  SUMO episode loop，將 Decision Order 與 neighbor cache 接進每個 control cycle。

- `src/its_signal_control/config.py`  
  預設值與 flat YAML loader。

重要 final artifacts：

- `models/main_methods/checkerboard_neighbor_adp_checkpoint_0020.json`  
  最終選定 trained model。

- `outputs/runs/selected_methods_vs_baselines/combined_summary.csv`  
  final aggregate table。

- `outputs/runs/selected_methods_vs_baselines/pairwise_vs_greedy.csv`  
  和 greedy 的 paired deltas。

- `outputs/runs/selected_methods_vs_baselines/selected_methods_vs_baselines_horizontal_v2.svg`  
  final comparison chart。

重要 tests：

- `tests/test_decision_order_schedule.py`  
  Decision Order strategies 與 neighbor lookup。

- `tests/test_agent_features.py`  
  compact residual、incident features、neighbor features。

- `tests/test_config_loading.py`  
  final 與探索用 presets 是否能被 flat YAML loader 正確讀取。

## 文件

- `WHITEPAPER.md`：最詳細的實作說明。
- `REPORT.md`：中英雙語方法與結果報告。
- `HISTORY_LOG.md`：完整開發歷程。
- `decision_order.md`：和隊友新版 Decision Order 的差異整理。

## 注意事項

- 預設仍然是 `DECISION_ORDER_STRATEGY: "unified"`，所以不會破壞原本行為。
- 只有 preset 啟用 `ALLOW_NEIGHBOR_INFO: true` 時才會加入 neighbor features。
- Baseline 不使用 Decision Order，也不使用 neighbor info。
- Checkerboard checkpoint 20 是 final trained model，因為 checkpoint sweep 顯示 checkpoint 50 退化。
- Random trained checkpoints 沒有被選入 final methods，因為 Random zero 整體更穩。
