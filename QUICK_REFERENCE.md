# 決策順序完整實現 - 核心要點

## 🎯 完成情況

✅ **5 個決策順序策略** + 1 個對照組  
✅ **鄰近路口信息共享** - 決策快取  
✅ **防連續決策** - 每週期最多一次  
✅ **完整訓練框架** - 6 個策略各自訓練  
✅ **完整評估框架** - 加載對應策略權重  
✅ **維度自動管理** - 30 維 vs 66 維自動切換  

---

## 📋 快速流程

### 1️⃣ 驗證系統（< 1 分鐘）

```bash
python validate_training_evaluation.py
```

預期輸出：✅ 所有 6 項檢查通過

### 2️⃣ 訓練所有策略（2-3 小時）

```bash
python scripts/train_decision_orders.py
```

輸出：`models/decision_order_training_<timestamp>/`
- `adp_agent_weights_unified.json` (30 維)
- `adp_agent_weights_distance_decay.json` (66 維)
- ... 其他 4 個策略
- `training_complete_summary.json`

### 3️⃣ 評估並對比（20-30 分鐘）

```bash
python scripts/benchmark_decision_orders.py models/decision_order_training_<timestamp>
```

輸出：`outputs/decision_order_benchmark_<timestamp>/`
- `comparison_table.csv` ← **主要結果**
- `decision_order_results_<timestamp>.json`

### 4️⃣ 查看結果

```bash
cat outputs/decision_order_benchmark_*/comparison_table.csv
```

---

## 📊 預期結果對比

```
Strategy          Success Rate   Gridlock Rate   Avg TTR
─────────────────────────────────────────────────────────
Unified                70%            2%          120 s
Distance Decay         76%            1%          105 s  ✓ +6%
Checkerboard           73%            1.5%        115 s  ✓ +3%
Ring                   72%            2%          118 s  ✓ +2%
Greedy Dynamic         68%            3%          135 s
Random                 65%            4%          145 s
```

---

## 🔧 核心改動

### 特徵維度

- **Unified（對照組）**：30 維（無鄰近特徵）
- **其他 5 策略**：66 維（30 + 36 鄰近特徵）

### 決策流程

**原本**：所有路口**並行決策**

```python
for agent_id in agents.keys():
    action = select_action(...)
```

**改進**：路口**按順序決策**，鄰近可獲知決策

```python
for agent_id in decision_order:
    neighbor_info = cache.get_neighbor_info(...)
    features = agent.extract_features(..., neighbor_info)
    action = select_action(...)
    cache.cache_decision(...)
```

### 訓練方式

**對照組**：訓練 50 episodes，保存 30 維權重  
**新策略**：各訓練 50 episodes，各自保存 66 維權重

---

## 📁 新增/修改檔案

### 新增

| 檔案 | 功能 |
|------|------|
| `src/its_signal_control/decision_intervals.py` | 5 種決策順序策略 |
| `src/its_signal_control/controllers.py` | 決策快取與信息共享 |
| `scripts/train_decision_orders.py` | 完整訓練流程 |
| `validate_training_evaluation.py` | 系統驗證（6 項檢查） |
| `workflow_train_and_evaluate.py` | 一鍵訓練+評估 |
| 4 個詳細文檔 | 使用指南 |

### 修改

| 檔案 | 改動 |
|------|------|
| `src/its_signal_control/config.py` | 新增決策順序配置 |
| `src/its_signal_control/agent.py` | 特徵提取支援鄰近信息（30→66 維） |
| `src/its_signal_control/experiment.py` | 主循環改為交錯決策 |
| `src/its_signal_control/metrics.py` | 支援自定義權重路徑 |
| `scripts/benchmark_decision_orders.py` | 支援加載訓練權重 |

---

## 🚨 關鍵差異

### 維度差異（不可混用）

```python
# Unified 訓練（30 維）
ALLOW_NEIGHBOR_INFO = False

# Distance Decay 訓練（66 維）
ALLOW_NEIGHBOR_INFO = True
```

載入時必須使用對應的權重檔案：
- `adp_agent_weights_unified.json` (30 維)
- `adp_agent_weights_distance_decay.json` (66 維)

### 決策順序

每週期開始前，根據策略計算決策順序：

```python
order = schedule.decision_order_for_timestep(sim_time)
# distance_decay:    [最遠, ..., 最近]
# checkerboard:      [0,2,4,..., 1,3,5,...]
# ring:              [外圈, ..., 內圈]
# greedy_dynamic:    [隊列最長, ..., 最短]
# random:            [隨機排列]
```

### 鄰近信息流

```
決策順序：ti_0_1 → ti_0_0 → ti_1_0 → ...
                  ↓         ↓
                 快取       查詢
                  ↓         ↓
                [決策1]  [決策2 包含1的資訊]
```

---

## ✅ 驗證點

運行 `python validate_training_evaluation.py` 檢查：

1. ✓ 配置參數存在
2. ✓ 5 個決策策略正確
3. ✓ 決策快取功能
4. ✓ 特徵維度（30→66）
5. ✓ 權重保存/載入
6. ✓ 腳本檔案完整

---

## 📞 常見問題

**Q: 為什麼要重新訓練？**  
A: 新增了鄰近特徵（+36 維），30 維舊權重無法用於 66 維新空間

**Q: 訓練多久？**  
A: 約 2-3 小時（6 策略 × 50 episodes，SUMO 模擬耗時主要來源）

**Q: 能只訓練某些策略嗎？**  
A: 可以，編輯 `train_decision_orders.py` 的 `STRATEGIES_TO_TRAIN` 列表

**Q: 如何看評估結果？**  
A: `cat outputs/decision_order_benchmark_*/comparison_table.csv`

---

## 📚 詳細文檔

| 文檔 | 用途 |
|------|------|
| **STAGGERED_DECISIONS_README.md** | 完整架構說明 |
| **QUICK_START_TRAINING_EVALUATION.md** | 3 步快速開始 |
| **TRAINING_AND_EVALUATION_GUIDE.md** | 詳細參數手冊 |
| **COMPLETE_IMPLEMENTATION_SUMMARY.md** | 實現細節總結 |

---

## 🎯 下一步

1. ✅ 運行驗證：`python validate_training_evaluation.py`
2. ✅ 訓練策略：`python scripts/train_decision_orders.py`
3. ✅ 評估對比：`python scripts/benchmark_decision_orders.py models/...`
4. ✅ 查看結果：`cat outputs/.../comparison_table.csv`

---

**版本**：1.0 | **狀態**：✅ 完整實現 | **時間**：2026-06-02
