# 鄰近信息使用修正報告

## 問題
鄰近路口信息被提取但從未實際使用於決策或模型更新中。

## 修正內容

### 1. experiment.py - 決策階段修正（第 183-276 行）
**修改前**：先決策，後才提取鄰近信息
**修改後**：先獲取鄰近信息，再決策

```python
# 修正流程：
1. 檢查防重複（第 187-193 行）
2. 獲取當前隊列和相位（第 195-196 行）
3. 先獲取鄰近信息（第 198-206 行）✓ NEW
   - 調用 decision_cache.get_neighbor_info()
   - 返回 neighbor_actions, neighbor_phases, neighbor_queues
4. 調用 select_adp_action 時傳遞鄰近信息（第 219-233 行）✓ FIXED
   - neighbor_actions 傳遞給決策函數
   - neighbor_phases 傳遞給決策函數
   - neighbor_queues 傳遞給決策函數
5. 快取此路口決策（第 234-236 行）
6. 提取特徵時包含鄰近信息（第 247-276 行）✓ VERIFIED
   - neighbor_actions, neighbor_phases, neighbor_queues 傳遞給 extract_features
```

### 2. experiment.py - 模型更新階段修正（第 397-445 行）
**修改前**：update_adp_agents() 未傳遞鄰近信息
**修改後**：從 step_cache 提取鄰近信息並傳遞

```python
# 第一處調用（終端狀態，第 397-409 行）
neighbor_info = {
    aid: (
        cache.get("neighbor_actions", {}),
        cache.get("neighbor_phases", {}),
        cache.get("neighbor_queues", {}),
    )
    for aid, cache in step_cache.items()
}
update_adp_agents(..., neighbor_info=neighbor_info)  # ✓ FIXED

# 第二處調用（決策週期末，第 434-451 行）
neighbor_info = {...}  # 同上
update_adp_agents(..., neighbor_info=neighbor_info)  # ✓ FIXED
```

### 3. controllers.py - 決策函數（第 75-139 行）
**狀態**：已正確實現
- 接受 neighbor_actions, neighbor_phases, neighbor_queues 參數
- 計算 Q 值時使用含鄰近信息的特徵（第 114-130 行）
- ε-貪心選擇基於鄰近信息的 Q 值（第 134-137 行）

### 4. controllers.py - 更新函數（第 142-230 行）
**狀態**：已正確實現
- 接受 neighbor_info 參數（第 152 行）
- 提取鄰近信息（第 164-167 行）
- 計算下一最優動作時使用鄰近信息（第 186-205 行）
- 提取下一狀態特徵時使用鄰近信息（第 208-222 行）
- 更新權重時使用含鄰近信息的特徵（第 225-230 行）

## 驗證路徑

### 決策循環中的鄰近信息流動
```
experiment.py 決策循環（每個時間步）
  ↓
1. decision_cache.get_neighbor_info()
   └→ 獲取已決策鄰近路口的 actions, phases, queues
  ↓
2. select_adp_action(..., neighbor_actions, neighbor_phases, neighbor_queues)
   ├→ extract_features() 包含鄰近信息
   ├→ 計算每個候選動作的 Q 值：Q = Σ(weights × features_with_neighbor)
   └→ ε-貪心選擇最大 Q 值
  ↓
3. decision_cache.cache_decision(agent_id, action, phase, queue)
   └→ 存儲此路口決策供後續鄰近路口使用
  ↓
4. step_cache[agent_id] 存儲 neighbor_actions, neighbor_phases, neighbor_queues
```

### 模型更新循環中的鄰近信息流動
```
update_adp_agents(..., neighbor_info)
  ↓
1. 獲取 neighbor_info[agent_id] → (neighbor_actions, neighbor_phases, neighbor_queues)
  ↓
2. 計算下一最優動作（include 鄰近信息）
   ├→ extract_features(..., neighbor_actions, neighbor_phases, neighbor_queues)
   ├→ get_value(features_with_neighbor)
   └→ argmax 獲得 next_action
  ↓
3. 提取下一狀態特徵（include 鄰近信息）
   └→ extract_features(..., neighbor_actions, neighbor_phases, neighbor_queues)
  ↓
4. 更新權重（使用含鄰近信息的特徵）
   └→ update_weights(current_features_with_neighbor, reward, next_features_with_neighbor, α, γ)
```

## 總結
✓ 鄰近信息現在在決策時被使用（Q 值計算）
✓ 鄰近信息現在在模型更新時被使用（TD 學習）
✓ 整個決策-學習循環中鄰近信息完整流動
