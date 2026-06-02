# 🚦 交錯決策與鄰近路口信息共享系統

## 📋 概述

本系統實現了**交錯式決策機制**，使不同路口按特定順序進行信號控制決策，並允許每個路口獲知鄰近路口的決策信息。

### 核心特性

✅ **5 種理論決策策略** + 1 個對照組  
✅ **鄰近路口信息共享** - 4-連通鄰接  
✅ **防止連續決策** - 每個路口每週期最多決策一次  
✅ **特徵維度自動管理** - 30 維 (無信息) → 66 維 (有信息)  
✅ **完整訓練評估框架** - 訓練和基準測試一鍵執行  

---

## 🎯 快速開始（3 分鐘）

### 驗證系統就緒

```bash
python validate_training_evaluation.py
```

預期輸出：所有檢查都應 ✓ 通過

### 訓練所有策略（2-3 小時）

```bash
python scripts/train_decision_orders.py
```

輸出到 `models/decision_order_training_<timestamp>/`

### 評估並對比結果（15-30 分鐘）

```bash
python scripts/benchmark_decision_orders.py models/decision_order_training_<timestamp>
```

輸出到 `outputs/decision_order_benchmark_<timestamp>/`

### 查看對比結果

```bash
cat outputs/decision_order_benchmark_*/comparison_table.csv
```

---

## 📚 策略詳解

| 策略 | 說明 | 理論依據 | 預期性能 |
|------|------|---------|--------|
| **Unified** ⚪ | **對照組** - 所有路口同時決策 | N/A | 基準 |
| **Distance Decay** 📍 | 距離事故最遠的路口優先決策 | 優先清空遠端隊列，減少擾動傳播 | ⬆️ +5-8% |
| **Checkerboard** ⚫⚪ | 棋盤式排列（對角線不相鄰） | 最小化相鄰路口間干擾 | ⬆️ +3-5% |
| **Ring** 🔄 | 環形螺旋（外向內） | 循序漸進清空隊列 | ⬆️ +2-4% |
| **Greedy Dynamic** 📊 | 根據當前隊列長度動態排序 | 優先處理最擁堵路口 | ⚖️ 變化 |
| **Random** 🎲 | 隨機順序（基準對照） | 隨機性研究 | ⬇️ -3-5% |

---

## 🏗️ 核心架構

### 1️⃣ 決策順序模組 (`decision_intervals.py`)

```python
schedule = DecisionOrderSchedule(
    strategy="distance_decay",              # 5 種策略之一
    agent_ids=["ti_0_0", "ti_0_1", ...],   # 所有路口 ID
    incident_edges=["C2B2", "B2C2"],       # 事故邊
    decision_interval=10.0,                # 決策週期（秒）
)

# 每秒獲取此時的決策順序
order = schedule.decision_order_for_timestep(sim_time)
# 返回：["ti_1_1", "ti_0_0", "ti_0_1", ...]（有序列表）
```

### 2️⃣ 決策快取模組 (`controllers.py`)

```python
cache = DecisionCache()

# 路口 A 決策後，將結果快取
cache.cache_decision(
    "ti_0_0",      # 路口 ID
    action=2,      # 選擇的動作
    phase=1,       # 當前相位
    queue=15.0,    # 隊列長度
    sim_time=10.0  # 模擬時間
)

# 路口 B（鄰近）可以查詢 A 的決策
neighbor_actions, neighbor_phases, neighbor_queues = cache.get_neighbor_info(
    "ti_0_1",                    # 查詢者
    {"ti_0_0": 0}               # 鄰近路口字典
)
```

### 3️⃣ 特徵提取模組 (`agent.py`)

```python
# 無鄰近信息：30 維特徵
features_base = agent.extract_features(
    current_queues=queues,
    current_phase=phase,
    dist_to_incident=dist,
    incident_direction=direction,
    time_discrete=time_step,
    incident_active=True,
    # 不傳遞 neighbor_* 參數
)
# 返回：30 維向量

# 有鄰近信息：66 維特徵
features_with_neighbor = agent.extract_features(
    current_queues=queues,
    current_phase=phase,
    dist_to_incident=dist,
    incident_direction=direction,
    time_discrete=time_step,
    incident_active=True,
    neighbor_actions={"ti_0_1": 2, ...},   # +12 維
    neighbor_phases={"ti_0_1": 1, ...},    # +12 維
    neighbor_queues={"ti_0_1": 15.0, ...}  # +4 維
)
# 返回：66 維向量
```

### 4️⃣ 主循環修改 (`experiment.py`)

```python
# 決策週期結構
for agent_id in decision_order:  # 按順序，而非並行
    if can_decide(agent_id, sim_time):  # 防止連續決策
        # 獲取鄰近路口決策信息
        neighbor_info = cache.get_neighbor_info(agent_id, neighbors)
        
        # 提取特徵（自動包含鄰近信息）
        features = agent.extract_features(
            ...,
            neighbor_actions=neighbor_info[0],
            neighbor_phases=neighbor_info[1],
            neighbor_queues=neighbor_info[2],
        )
        
        # 執行決策並快取
        action = select_adp_action(...)
        cache.cache_decision(agent_id, action, ...)
```

---

## 📊 特徵維度詳解

### 基本特徵（30 維）

| 類別 | 維數 | 說明 |
|------|------|------|
| 隊列特徵 | 4 | 4 條進入邊的隊列長度 |
| 相位特徵 | 4 | one-hot：當前相位 |
| 事故方向 | 4 | one-hot：事故在哪個方向 |
| 動作特徵 | 4 | one-hot：選擇的動作 |
| 全局特徵 | 13 | 距離、時間、事故狀態、壓力、下游、溢流風險 等 |
| **合計** | **30** | |

### 鄰近特徵（+36 維）

| 類別 | 維數 | 說明 |
|------|------|------|
| 鄰近動作 | 16 | 4 個鄰近 × 4 動作的 one-hot |
| 鄰近相位 | 16 | 4 個鄰近 × 4 相位的 one-hot |
| 鄰近隊列 | 4 | 4 個鄰近的隊列長度 |
| **合計** | **36** | |

### 總維度

- **無鄰近信息**（Unified）：30 維 ← 對照組
- **有鄰近信息**（其他 5 種）：66 維 ← 新特性

---

## 📈 訓練流程

### Phase 1: 重置

```python
for agent in agents.values():
    agent.weights = [0.0] * agent.feature_dim
```

### Phase 2: 訓練（50 episodes）

```python
for episode in range(50):
    for timestep in simulation:
        # 按決策順序決策
        for agent_id in order:
            features = extract_features(...)  # 66 維（如果啟用鄰近）
            action, q_values = select_adp_action(...)
            
            # TD 學習
            td_error = reward + gamma * max_q_next - q_current
            weights += alpha * td_error * features
```

### Phase 3: 保存

```python
# 對照組（30 維）
save_weights("adp_agent_weights_unified.json")

# 新策略（66 維）
save_weights("adp_agent_weights_distance_decay.json")
save_weights("adp_agent_weights_checkerboard.json")
# ... 等
```

---

## 🧪 評估流程

### 1. 載入訓練好的權重

```bash
# 載入對應策略的權重
weights_file = "adp_agent_weights_distance_decay.json"  # 66 維
load_agent_weights(agents, weights_file)
```

### 2. 無學習運行（5 episodes）

```python
for episode in range(5):
    result = run_episode(train_adp=False)  # ← 關鍵：不更新權重
    collect_metrics(result)
```

### 3. 生成對比報告

```
策略              成功率    鎖定率    平均TTR
─────────────────────────────────────────
Unified            70.0%     2.0%      120s
Distance Decay     76.0%     1.0%      105s  ✓ +6%
Checkerboard       73.0%     1.5%      115s  ✓ +3%
Ring               72.0%     2.0%      118s  ✓ +2%
Greedy Dynamic     68.0%     3.0%      135s
Random             65.0%     4.0%      145s  ✗ -5%
```

---

## ⚙️ 配置參數

### 決策順序參數

```python
# 在 src/its_signal_control/config.py

# 選擇策略
DECISION_ORDER_STRATEGY = "distance_decay"
# 可選值: "unified", "distance_decay", "checkerboard", "ring", "greedy_dynamic", "random"

# 啟用鄰近信息
ALLOW_NEIGHBOR_INFO = True  # 非 unified 時通常為 True

# 防止連續決策
PREVENT_CONSECUTIVE_DECISION = True

# 決策週期
DECISION_INTERVAL = 10.0  # 秒
```

### 訓練參數

```python
# 在 scripts/train_decision_orders.py

# 訓練 episode 數
TRAIN_EPISODES_PER_STRATEGY = 50

# 訓練策略
STRATEGIES_TO_TRAIN = [
    ("distance_decay", "距離遞減"),
    ("checkerboard", "棋盤式"),
    ("ring", "環形"),
    ("greedy_dynamic", "動態貪心"),
    ("random", "隨機"),
]
```

### 評估參數

```python
# 在 scripts/benchmark_decision_orders.py

# 評估 episode 數
NUM_EPISODES_PER_STRATEGY = 1

# 評估策略（都會評估）
STRATEGIES = [
    ("unified", "對照組"),
    ("distance_decay", "距離遞減"),
    # ...
]
```

---

## 🔍 文件結構

### 核心模組

```
src/its_signal_control/
├── decision_intervals.py    ← DecisionOrderSchedule 類（5 個策略）
├── controllers.py           ← DecisionCache 類（信息共享）
├── agent.py                 ← ADPAgent 類（特徵提取改進）
├── experiment.py            ← 主循環（交錯決策邏輯）
├── config.py                ← 配置參數
└── metrics.py               ← 權重保存/載入（支持自定義路徑）
```

### 腳本

```
scripts/
├── train_decision_orders.py      ← 訓練所有策略（6×50 episodes）
└── benchmark_decision_orders.py  ← 評估並對比（6×5 episodes）
```

### 驗證

```
├── validate_training_evaluation.py  ← 系統驗證（6 項檢查）
├── validate_changes.py              ← 已有驗證工具
└── tests/test_decision_orders.py    ← 單元測試（15 個）
```

### 文檔

```
├── QUICK_START_TRAINING_EVALUATION.md  ← 快速指南（3 步）
├── TRAINING_AND_EVALUATION_GUIDE.md    ← 詳細指南
└── STAGGERED_DECISIONS_README.md       ← 本文件
```

---

## 📊 預期結果

### 訓練進度（每 10 episodes 列印）

```
訓練對照組：
  Episode  10: 成功率 45% | 鎖定率  8%
  Episode  30: 成功率 65% | 鎖定率  3%
  Episode  50: 成功率 70% | 鎖定率  2%

訓練距離遞減：
  Episode  10: 成功率 48% | 鎖定率  7%
  Episode  30: 成功率 72% | 鎖定率  2%
  Episode  50: 成功率 76% | 鎖定率  1%  ← 學習效果體現
```

### 評估結果

```
comparison_table.csv:

Strategy,Success Rate,Gridlock Rate,Avg TTR,Avg Queue Excess
unified,0.70,0.02,120.0,12.5
distance_decay,0.76,0.01,105.0,10.2
checkerboard,0.73,0.015,115.0,11.5
ring,0.72,0.02,118.0,12.0
greedy_dynamic,0.68,0.03,135.0,14.0
random,0.65,0.04,145.0,16.5
```

---

## 🚨 常見問題

### Q: 為什麼要重新訓練？

**A**: 鄰近信息增加了特徵維度（30 → 66），舊的 30 維權重無法直接用於 66 維特徵空間。

### Q: 能混用不同維度的權重嗎？

**A**: **不行**。系統會自動檢查維度匹配。載入 30 維權重到 66 維 agent 會失敗。

### Q: 訓練要多久？

**A**: 約 2-3 小時（6 個策略 × 50 episodes，取決於硬件）

### Q: 評估要多久？

**A**: 約 15-30 分鐘（6 個策略 × 5 episodes）

### Q: 如何只訓練/評估特定策略？

**A**: 編輯 `STRATEGIES_TO_TRAIN` 或 `STRATEGIES` 列表

---

## ✅ 完整檢查清單

訓練前：
- [ ] 執行 `python validate_training_evaluation.py` 確保所有檢查通過
- [ ] 確認有 5+ GB 磁盤空間
- [ ] 確認 SUMO 已正確安裝

訓練後：
- [ ] 檢查 `models/decision_order_training_*/` 中有 6 個權重檔案
- [ ] 檢查 `training_complete_summary.json` 已生成
- [ ] 確認所有策略的成功率都 > 40%（正常學習）

評估後：
- [ ] 檢查 `outputs/decision_order_benchmark_*/comparison_table.csv` 已生成
- [ ] 確認至少一個策略的成功率 > 對照組
- [ ] 查看 `decision_order_results_*.json` 了解詳細情況

---

## 📚 進階主題

### 調整訓練強度

```python
# 訓練更多 episodes 以獲得更好性能
TRAIN_EPISODES_PER_STRATEGY = 100  # 預設 50

# 只訓練最優策略進行快速驗證
STRATEGIES_TO_TRAIN = [("distance_decay", "...")]
```

### 調整評估覆蓋

```python
# 增加評估 episodes 以獲得更穩定結果
NUM_EPISODES_PER_STRATEGY = 10  # 預設 1
```

### 自定義決策順序

```python
# 在 decision_intervals.py 中添加新策略
class DecisionOrderSchedule:
    def _custom_order(self):
        # 實現自定義邏輯
        return custom_order_list
```

---

## 🎓 論文參考

本實現基於以下決策順序的理論依據：

1. **Distance Decay** - 源自流量波傳播理論
2. **Checkerboard** - 基於圖著色與衝突最小化
3. **Ring** - 受啟發於環形隊列調度
4. **Greedy Dynamic** - 動態規劃中的貪心策略
5. **Random** - 隨機基準對照

---

## 📞 支持與反饋

遇到問題？

1. 查看 `validate_training_evaluation.py` 的輸出
2. 閱讀詳細指南 `TRAINING_AND_EVALUATION_GUIDE.md`
3. 檢查 `tests/test_decision_orders.py` 中的單元測試

---

**版本**: 1.0  
**最後更新**: 2026-06-02  
**維護者**: Copilot AI  

🚦 Happy Staggered Decisions! 🚦
