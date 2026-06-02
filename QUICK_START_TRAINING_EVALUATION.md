# 🚀 決策順序訓練與評估快速指南

## 📌 核心概念

您的系統現在有 **6 個決策順序策略**，需要分別訓練：

| 策略 | 描述 | 特徵維度 | 鄰近信息 |
|------|------|---------|--------|
| **unified** | 對照組（同時決策） | 30 | ❌ |
| **distance_decay** | 距離最遠優先 | 66 | ✅ |
| **checkerboard** | 棋盤式排列 | 66 | ✅ |
| **ring** | 環形螺旋 | 66 | ✅ |
| **greedy_dynamic** | 動態貪心 | 66 | ✅ |
| **random** | 隨機順序 | 66 | ✅ |

---

## 🎯 快速開始（3 步）

### Step 1: 訓練所有策略（2-3 小時）

```bash
cd d:\114_02\AI\final_project\ADP-incident-traffic-recovery-sumo
python scripts/train_decision_orders.py
```

**預期輸出**：
```
models/decision_order_training_20260602_120000/
  ├── adp_agent_weights_unified.json
  ├── adp_agent_weights_distance_decay.json
  ├── adp_agent_weights_checkerboard.json
  ├── adp_agent_weights_ring.json
  ├── adp_agent_weights_greedy_dynamic.json
  ├── adp_agent_weights_random.json
  ├── training_complete_summary.json
  └── train_metrics.csv
```

### Step 2: 評估所有策略（15-30 分鐘）

```bash
python scripts/benchmark_decision_orders.py models/decision_order_training_20260602_120000
```

**預期輸出**：
```
outputs/decision_order_benchmark_20260602_140000/
  ├── comparison_table.csv
  ├── decision_order_results_20260602_140000.json
  └── eval_metrics.csv
```

### Step 3: 查看結果

```bash
# 查看對比表
cat outputs/decision_order_benchmark_*/comparison_table.csv

# 查看詳細結果
python -m json.tool outputs/decision_order_benchmark_*/decision_order_results_*.json
```

---

## 📊 預期結果示例

### 訓練進度（training 階段，50 episodes 每個策略）

```
=== 訓練對照組 (Unified) ===
Episode  10: 成功率 45% | 鎖定率  8%
Episode  30: 成功率 65% | 鎖定率  3%
Episode  50: 成功率 70% | 鎖定率  2%

=== 訓練距離遞減 (Distance Decay) ===
Episode  10: 成功率 48% | 鎖定率  7%
Episode  30: 成功率 72% | 鎖定率  2%
Episode  50: 成功率 76% | 鎖定率  1%  ← +6% vs 對照組
```

### 評估結果（evaluation 階段，5 episodes 每個策略）

```
策略              成功率    鎖定率    平均TTR   評論
─────────────────────────────────────────────────
Unified            70.0%     2.0%      120s    對照組基準
Distance Decay     76.0%     1.0%      105s    ✓ 最優 (+6%)
Checkerboard       73.0%     1.5%      115s    ✓ 次優 (+3%)
Ring               72.0%     2.0%      118s    ✓ 良好 (+2%)
Greedy Dynamic     68.0%     3.0%      135s    接近對照
Random             65.0%     4.0%      145s    ✗ 最差 (-5%)
```

---

## 🔧 核心實現細節

### 特徵維度與權重

**對照組（Unified）**:
- 決策策略：所有路口**同時決策**
- 特徵維度：30（無鄰近特徵）
- 配置：
  ```python
  DECISION_ORDER_STRATEGY = "unified"
  ALLOW_NEIGHBOR_INFO = False
  ```

**新策略（非 Unified）**:
- 決策策略：按順序決策（distance_decay、checkerboard 等）
- 特徵維度：66（30 基本特徵 + 36 鄰近特徵）
  - 鄰近動作：4 鄰近 × 4 動作 = 16 維
  - 鄰近相位：4 鄰近 × 4 相位 = 16 維
  - 鄰近隊列：4 鄰近 × 1 隊列 = 4 維
- 配置：
  ```python
  DECISION_ORDER_STRATEGY = "distance_decay"  # 或其他
  ALLOW_NEIGHBOR_INFO = True
  ```

### 訓練流程

```python
for strategy in [unified, distance_decay, checkerboard, ...]:
    1. 重置權重（清零）
    2. 執行 50 episodes 訓練（TD 學習）
    3. 保存訓練後的權重到 adp_agent_weights_{strategy}.json
    4. 記錄訓練統計
```

### 評估流程

```python
for strategy in [unified, distance_decay, checkerboard, ...]:
    1. 載入對應的訓練權重
    2. 執行 5 episodes 評估（無學習）
    3. 收集 success_rate, TTR, gridlock_rate, queue_excess
    4. 生成對比報告
```

---

## ⚙️ 配置調整

### 訓練參數

編輯 `scripts/train_decision_orders.py`：

```python
# 改變 episode 數
TRAIN_EPISODES_PER_STRATEGY = 50  # 預設

# 改變訓練策略
STRATEGIES_TO_TRAIN = [
    ("distance_decay", "距離遞減"),
    ("checkerboard", "棋盤式"),
    # 只訓練這兩個
]
```

### 評估參數

編輯 `scripts/benchmark_decision_orders.py`：

```python
# 改變 episode 數
NUM_EPISODES_PER_STRATEGY = 1  # 預設

# 改變評估策略
STRATEGIES = [
    ("unified", "對照組"),
    ("distance_decay", "距離遞減"),
    # 只評估這兩個
]
```

---

## 🔍 驗證結果

### 1. 檢查權重檔案

```bash
# 查看訓練輸出
ls -lh models/decision_order_training_*/adp_agent_weights_*.json

# 預期：每個 ~50-100 KB
```

### 2. 檢查訓練日誌

```bash
# 查看訓練摘要
cat models/decision_order_training_*/training_complete_summary.json | python -m json.tool

# 預期：
# - unified: 成功率 ~70%, 鎖定率 ~2%
# - 其他策略: 成功率 ~72-76%, 鎖定率 ~1-2%
```

### 3. 檢查評估結果

```bash
# 查看對比表
cat outputs/decision_order_benchmark_*/comparison_table.csv

# 預期：distance_decay 應該至少比 unified 好 3-5%
```

---

## 🚨 常見問題排查

### Q1: 訓練中斷或權重維度不匹配？

**症狀**：
```
ValueError: Expected 66 dimensions but got 30
```

**原因**：權重檔案的維度與當前配置不匹配

**解決**：
1. 確認 `ALLOW_NEIGHBOR_INFO` 設置正確
   - Unified: `False`
   - 其他: `True`
2. 確認載入的權重是對應策略的
   ```bash
   # 檢查權重檔案
   cat models/decision_order_training_*/adp_agent_weights_distance_decay.json | head -20
   ```

### Q2: 評估時權重無法載入？

**症狀**：
```
WARNING: No saved ADP weights found; evaluation will use current in-memory weights.
```

**原因**：權重路徑不存在

**解決**：
```bash
# 1. 確認訓練目錄存在
ls models/decision_order_training_*/

# 2. 使用正確的路徑執行評估
python scripts/benchmark_decision_orders.py models/decision_order_training_<exact_timestamp>
```

### Q3: 評估結果異常（成功率低於預期）？

**可能原因**：
1. 訓練 episode 不足 → 增加 `TRAIN_EPISODES_PER_STRATEGY`
2. 評估 episode 太少 → 增加 `NUM_EPISODES_PER_STRATEGY`
3. 種子不同 → 結果有隨機方差

**快速驗證**：
```bash
# 跑更多 episode
sed -i 's/NUM_EPISODES_PER_STRATEGY = 1/NUM_EPISODES_PER_STRATEGY = 5/' scripts/benchmark_decision_orders.py
python scripts/benchmark_decision_orders.py models/decision_order_training_...
```

### Q4: 如何完全重新訓練？

```bash
# 1. 刪除舊訓練輸出（可選）
rm -rf models/decision_order_training_*

# 2. 執行新訓練
python scripts/train_decision_orders.py

# 3. 用新權重評估
python scripts/benchmark_decision_orders.py models/decision_order_training_<new>
```

---

## 📈 性能優化建議

### 訓練階段

如果想看到更好的性能改進：

```python
# 增加訓練 episodes（耗時較長）
TRAIN_EPISODES_PER_STRATEGY = 100  # 從 50 增加到 100

# 或只訓練最有潛力的策略
STRATEGIES_TO_TRAIN = [
    ("distance_decay", "距離遞減"),      # 最優理論
    ("checkerboard", "棋盤式"),          # 次優理論
]
```

### 評估階段

如果想確保評估結果穩定：

```python
# 增加評估 episodes
NUM_EPISODES_PER_STRATEGY = 10  # 從 1 增加到 10
```

---

## 📝 文件結構說明

### 訓練輸出

```
models/decision_order_training_20260602_120000/
├── adp_agent_weights_unified.json          # 對照組權重（30 維）
├── adp_agent_weights_distance_decay.json   # 距離遞減權重（66 維）
├── adp_agent_weights_checkerboard.json
├── adp_agent_weights_ring.json
├── adp_agent_weights_greedy_dynamic.json
├── adp_agent_weights_random.json
├── training_complete_summary.json          # 訓練總摘要
├── train_summary_baseline.json             # Unified 訓練摘要
├── train_summary_distance_decay.json       # 距離遞減訓練摘要
├── train_metrics.csv                       # 訓練指標（原始）
└── train_metrics_baseline.csv
```

### 評估輸出

```
outputs/decision_order_benchmark_20260602_140000/
├── comparison_table.csv                    # 對比表（主要結果）
├── decision_order_results_*.json           # 詳細結果
└── eval_metrics.csv                        # 評估指標（原始）
```

---

## ✅ 完整檢查清單

在運行訓練前，確認：

- [ ] Python 環境已安裝
- [ ] SUMO 已安裝並在 PATH 中
- [ ] 磁盤空間足夠（至少 5 GB）
- [ ] 硬件足夠（建議 4+ CPU 核心）

訓練完成後，驗證：

- [ ] 所有 6 個權重檔案都存在（unified + 5 個策略）
- [ ] `training_complete_summary.json` 已生成
- [ ] 訓練過程中沒有錯誤

評估完成後，驗證：

- [ ] `comparison_table.csv` 已生成
- [ ] `decision_order_results_*.json` 已生成
- [ ] 至少一個策略的成功率 > 對照組

---

## 🎓 下一步

評估完成後，您可以：

1. **分析結果**：查看哪個策略性能最優
2. **優化策略**：根據結果調整訓練參數
3. **長期評估**：在不同網路/場景下測試
4. **部署**：將最優策略的權重集成到生產系統

---

**版本**: 1.0  
**最後更新**: 2026-06-02  
**維護者**: Copilot
