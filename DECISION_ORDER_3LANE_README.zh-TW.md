# 3-Lane Decision Order 整合說明

本文說明如何在 `traffic-adp-sumo-final` 的 3-lane 架構中啟用 Decision Order。

## 整合範圍

此版本只整合「決策排序」本身，不整合舊 1-lane 程式中的 neighbor-decision features。

原因：

- 目前 3-lane agent 已經有 lane-level queues、`three_lane_8` action space、incident-action features、`heuristic_residual` 與 `compact_residual` feature set。
- 舊版 neighbor features 會改變 feature vector 維度，若直接套用會讓既有 3-lane weights 與 checkpoint 不相容。
- 舊版實作中 neighbor features 也有權重維度風險，因此本次先保守保留 3-lane feature formulation。

## 策略

新增設定：

```yaml
DECISION_ORDER_STRATEGY: "unified"
DECISION_ORDER_RANDOM_SEED: 42
```

可用策略：

- `unified`：預設值，保持原本 3-lane 行為與 agent iteration order。
- `distance_decay`：距離 incident endpoints 最遠的 signal 先決策。
- `checkerboard`：依路口座標奇偶分組。
- `ring`：外圈到內圈排序。
- `greedy_dynamic`：每個 decision cycle 依目前總 queue 由大到小排序。
- `random`：固定 seed 的隨機順序。

本次主方法選擇 `distance_decay`，因為 incident recovery 的目標是讓遠端與上游區域先形成疏散決策，再讓靠近事故的路口接續決策。它也最容易用 incident edge endpoints 解釋，且不需要改變 3-lane reward、feature 或 action semantics。

## 如何啟用

單次 demo：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_decision_order_demo.ps1
```

觀看 SUMO GUI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_decision_order_demo.ps1 -Gui
```

使用已訓練的 50-episode distance-decay 權重：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_decision_order_demo.ps1 -UseTrainedWeights
```

Smoke：

```powershell
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python -m its_signal_control.cli evaluate `
  --preset configs\three_lane_smoke_decision_order_distance_decay.yaml `
  --headless `
  --output-dir outputs\runs\three_lane_smoke_decision_order_distance_decay_probe
```

50-episode training：

```powershell
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python -m its_signal_control.cli train `
  --preset configs\three_lane_training_50_decision_order_distance_decay.yaml `
  --headless
```

24-episode evaluation：

```powershell
$env:PYTHONPATH = "$PWD\src;$env:SUMO_HOME\tools"
python -m its_signal_control.cli evaluate `
  --preset configs\three_lane_evaluation_24_decision_order_distance_decay.yaml `
  --headless `
  --output-dir outputs\runs\three_lane_evaluation_24_decision_order_distance_decay
```

## 如何停用

保留或設定：

```yaml
DECISION_ORDER_STRATEGY: "unified"
```

`unified` 會使用原本 `agents.keys()` 順序，不改變既有 3-lane method、feature dimension、權重載入方式或 controller timing。

## 評估注意事項

- 本次 Decision Order 不啟用 neighbor features，因此不應宣稱 feature sharing 或 communication。
- 在沒有 neighbor features 的前提下，排序主要是可配置的 simulation/controller sequencing hook；它不會改變 ADP feature vector。
- 若之後要讓排序對 policy 有更強行為效果，下一步應設計 3-lane 原生 communication/neighbor features，並明確增加 feature dimensions 與重新訓練權重。
