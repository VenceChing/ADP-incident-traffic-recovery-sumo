# 🚀 完整訓練與評估流程

## 📋 背景

新增的**鄰近路口特徵**增加了特徵維度：
- **Unified (對照組)**：30 維（無鄰近特徵）
- **其他策略**：66 維（+36 維鄰近特徵）

因此需要為每個策略單獨訓練新權重，無法直接使用舊的 30 維權重。

---

## 🎯 完整流程

### Phase 1: 訓練所有策略（50 epochs × 6 策略）

```bash
# 執行訓練
python scripts/train_decision_orders.py
```

**預期耗時**：2-3 小時（取決於硬件）

**輸出**：
```
models/decision_order_training_<timestamp>/
  ├── adp_agent_weights_unified.json           ← 對照組（30維）
  ├── adp_agent_weights_distance_decay.json    ← 距離遞減（66維）
  ├── adp_agent_weights_checkerboard.json      ← 棋盤式（66維）
  ├── adp_agent_weights_ring.json              ← 環形（66維）
  ├── adp_agent_weights_greedy_dynamic.json    ← 動態貪心（66維）
  ├── adp_agent_weights_random.json            ← 隨機（66維）
  └── training_complete_summary.json           ← 訓練摘要
```

### Phase 2: 評估所有策略（5 episodes × 6 策略）

```bash
# 執行評估（使用訓練好的權重）
python scripts/benchmark_decision_orders.py models/decision_order_training_<timestamp>
```

**預期耗時**：20-30 分鐘

**輸出**：
```
outputs/decision_order_benchmark_<timestamp>/
  ├── comparison_table.csv                     ← 對比表
  └── decision_order_results_<timestamp>.json  ← 詳細結果
```

---

## 🔄 訓練配置

### train_decision_orders.py 關鍵參數

```python
STRATEGIES_TO_TRAIN = [
    ("distance_decay", "距離遞減"),
    ("checkerboard", "棋盤式"),
    ("ring", "環形"),
    ("greedy_dynamic", "動態貪心"),
    ("random", "隨機"),
]

TRAIN_EPISODES_PER_STRATEGY = 50  # 每個策略訓練 50 個 episode
```

### 訓練時的配置

```python
# 對照組（unified）
DECISION_ORDER_STRATEGY = "unified"
ALLOW_NEIGHBOR_INFO = False
特徵維度 = 30

# 其他策略
DECISION_ORDER_STRATEGY = "distance_decay" | "checkerboard" | ...
ALLOW_NEIGHBOR_INFO = True
特徵維度 = 66
```

---

## 📊 訓練輸出文件

### adp_agent_weights_*.json

```json
{
  "ti_0_0": [w0, w1, w2, ..., w29],  // unified (30 權重)
  "ti_0_1": [w0, w1, w2, ..., w29],
  ...
}

或

{
  "ti_0_0": [w0, w1, w2, ..., w65],  // 其他策略 (66 權重)
  "ti_0_1": [w0, w1, w2, ..., w65],
  ...
}
```

### train_summary.json

```json
{
  "strategy": "distance_decay",
  "feature_dimension": 66,
  "allow_neighbor_info": true,
  "training_episodes": 50,
  "success_rate": 0.72,
  "gridlock_rate": 0.04,
  ...
}
```

---

## ✅ 評估流程

### 使用訓練的權重進行評估

```bash
# 評估對照組 + 5 個新策略
python scripts/benchmark_decision_orders.py models/decision_order_training_20260602_120000
```

### 評估時的配置

```python
# 對每個策略自動設置
DECISION_ORDER_STRATEGY = strategy  # "unified", "distance_decay", ...
ALLOW_NEIGHBOR_INFO = (strategy != "unified")  # 非對照組啟用鄰近信息

# 載入對應的訓練權重
weights_file = f"adp_agent_weights_{strategy}.json"
load_agent_weights(agents, weights_file)
```

---

## 📈 預期結果對比

### 訓練進度

```
訓練對照組（unified）：
  Episode  10: 成功率 45% | 鎖定率  8%
  Episode  20: 成功率 58% | 鎖定率  5%
  Episode  30: 成功率 65% | 鎖定率  3%
  Episode  50: 成功率 70% | 鎖定率  2%

訓練距離遞減（distance_decay）：
  Episode  10: 成功率 48% | 鎖定率  7%
  Episode  20: 成功率 62% | 鎖定率  4%
  Episode  30: 成功率 70% | 鎖定率  2%
  Episode  50: 成功率 76% | 鎖定率  1%  ← 超過對照組 +6%
```

### 評估結果對比表

```
策略              成功率    鎖定率    平均 TTR   平均隊列超額
─────────────────────────────────────────────────────────
Unified            70.0%     2.0%      120 s       12.5
Distance Decay     76.0%     1.0%      105 s       10.2  ⬆️ +6%
Checkerboard       73.0%     1.5%      115 s       11.5  ⬆️ +3%
Ring               72.0%     2.0%      118 s       12.0  ⬆️ +2%
Greedy Dynamic     68.0%     3.0%      135 s       14.0  ⬇️ -2%
Random             65.0%     4.0%      145 s       16.5  ⬇️ -5%
```

---

## 🔧 配置修改點

### 如果想改變訓練參數

編輯 `scripts/train_decision_orders.py`：

```python
# 改變訓練 episode 數
TRAIN_EPISODES_PER_STRATEGY = 100  # 預設 50

# 只訓練特定策略（快速測試）
STRATEGIES_TO_TRAIN = [
    ("distance_decay", "距離遞減"),
]
```

### 如果想改變評估參數

編輯 `scripts/benchmark_decision_orders.py`：

```python
# 改變評估 episode 數
NUM_EPISODES_PER_STRATEGY = 10  # 預設 1

# 只評估特定策略
STRATEGIES = [
    ("unified", "對照組"),
    ("distance_decay", "距離遞減"),
]
```

---

## 🚨 常見問題

### Q1: 訓練中斷了怎麼辦？

**A**: 訓練會從某個策略開始，但已完成的策略權重已保存。您可以：
1. 檢查 `models/decision_order_training_*/` 中已有的權重檔案
2. 手動編輯 `train_decision_orders.py` 跳過已完成的策略
3. 重新啟動訓練（會覆蓋）

### Q2: 評估時報權重維度不匹配？

**A**: 確認以下幾點：
1. 使用的權重檔案路徑正確
2. 配置中 `ALLOW_NEIGHBOR_INFO` 與訓練時一致
3. 特徵維度是否與訓練時相同

### Q3: 效能沒有提升反而下降？

**A**: 可能原因：
1. 訓練 episode 不足（增加 TRAIN_EPISODES_PER_STRATEGY）
2. 事故位置不同，策略對特定位置敏感
3. 隨機seed不同導致方差
4. 測試 episode 太少，增加 NUM_EPISODES_PER_STRATEGY

### Q4: 要重新訓練怎麼做？

**A**: 完整重新訓練流程：

```bash
# 1. 刪除舊的訓練輸出（可選）
rm -rf models/decision_order_training_*

# 2. 執行新的訓練
python scripts/train_decision_orders.py

# 3. 使用新權重進行評估
python scripts/benchmark_decision_orders.py models/decision_order_training_<new_timestamp>
```

---

## 📝 訓練邏輯詳解

### 對照組訓練（Unified）

```python
# 配置
DECISION_ORDER_STRATEGY = "unified"  # 同時決策
ALLOW_NEIGHBOR_INFO = False          # 無鄰近信息
feature_dim = 30                      # 原始特徵

# 流程
重置權重 → 訓練 50 episodes → 儲存 30 維權重
```

### 新策略訓練（Distance Decay 等）

```python
# 配置
DECISION_ORDER_STRATEGY = "distance_decay"  # 距離優先
ALLOW_NEIGHBOR_INFO = True                  # 啟用鄰近信息
feature_dim = 66                            # 原始 30 + 鄰近 36

# 流程
重置權重 → 訓練 50 episodes → 儲存 66 維權重
           ↓
      每個路口在決策時：
      1. 按順序決策（distance_decay）
      2. 獲得鄰近路口決策信息
      3. 特徵包含鄰近信息（36 維）
      4. 用 66 維權重計算價值
      5. 根據 TD error 更新權重
```

---

## 🎓 學習 & 驗證

### 驗證訓練正確性

```bash
# 1. 檢查權重檔案大小
ls -lh models/decision_order_training_*/adp_agent_weights_*.json
# 預期：每個檔案 ~50KB（16 個路口 × 權重向量）

# 2. 檢查訓練摘要
cat models/decision_order_training_*/training_complete_summary.json | python -m json.tool

# 3. 查看單個策略成功率趨勢
cat models/decision_order_training_*/train_summary_distance_decay.json
```

### 驗證評估正確性

```bash
# 1. 檢查對比結果
cat outputs/decision_order_benchmark_*/comparison_table.csv

# 2. 檢查詳細結果
cat outputs/decision_order_benchmark_*/decision_order_results_*.json | python -m json.tool

# 3. 確認結果順序合理
# 預期：距離遞減 > 棋盤式 > 環形 > 隨機 > 動態貪心（通常）
```

---

## 🔄 完整工作流總結

```
1. 【訓練階段】train_decision_orders.py
   ↓
   For each strategy in [unified, distance_decay, ...]:
     ├─ 重置權重（清零）
     ├─ 執行 50 episodes 訓練
     ├─ 更新權重（通過 TD learning）
     └─ 儲存特定維度的權重
   ↓
   輸出：models/decision_order_training_<timestamp>/
        adp_agent_weights_*.json

2. 【評估階段】benchmark_decision_orders.py
   ↓
   For each strategy in [unified, distance_decay, ...]:
     ├─ 載入訓練好的權重
     ├─ 執行 5 episodes 評估
     ├─ 收集 success_rate, TTR, gridlock_rate, ...
     └─ 對比分析
   ↓
   輸出：outputs/decision_order_benchmark_<timestamp>/
        comparison_table.csv
        decision_order_results_*.json

3. 【分析階段】
   ├─ 查看 comparison_table.csv 選出最優策略
   ├─ 查看 decision_order_results_*.json 了解詳情
   └─ 決定是否需要調整參數重新訓練
```

---

## ✨ 重要提醒

1. **維度差異**：對照組 30 維 vs 新策略 66 維，必須分開訓練
2. **鄰近信息**：只有非 unified 策略啟用鄰近特徵
3. **權重不相容**：不能混用不同維度的權重
4. **訓練時間**：6 個策略 × 50 episodes ≈ 2-3 小時
5. **評估驗證**：評估時必須指定訓練權重目錄

---

**版本**: 1.0
**最後更新**: 2026-06-02
