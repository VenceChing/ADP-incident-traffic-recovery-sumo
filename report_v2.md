# Pure ADP Solver to ADP-inspired Controller

## Pure ADP Solver

在標準的馬可夫決策過程（MDP）中，尋求最佳策略的核心是求解**貝爾曼最佳化方程式（Bellman Optimality Equation）**：

$$V^*(s) = \max_{a \in \mathcal{A}} \left\{ R(s, a) + \gamma \sum_{s' \in \mathcal{S}} P(s' | s, a) V^*(s') \right\}$$

當狀態空間 $\mathcal{S}$ 維度過大無法建表時，**純粹的近似動態規劃（Pure ADP）**會引入價值函數近似（Value Function Approximation，如線性模型）：

$$V(s) \approx \mathbf{w}^\top \boldsymbol{\phi}(s)$$

$\boldsymbol{\phi}(s)$ 是 $s$ 的特徵向量，$\mathbf{w}$ 是權重

在這種標準的 $V(s)$ solver 架構下，動作的選擇必須**嚴格遵循**以下公式：

$$a^* = \arg\max_{a \in \mathcal{A}} \left\{ R(s, a) + \gamma \sum_{s'} P(s' | s, a) V^*(s') \right\}$$

這意味著 pure ADP solver，必須高度依賴一個能精準預測執行動作 $a$ 後、下一狀態機率分佈的全域轉移模型 $P(s' | s, a)$。


## ADP-inspired

對照上述標準理論，我捨棄 Pure ADP Solver，改用較務實的 **ADP-inspired Controller**：

1. **Heuristic / Local Transition**：微觀交通（如車輛跟車與換道）極度複雜，我們無法寫出閉式數學公式 $P(s'|s,a)$，只能在程式碼中寫入一個簡單的、基於 local queue 增減的 **heuristic one-step predictor** (例如估算綠燈放行幾輛、紅燈累積幾輛)
2. **非演算法本質的干預（Tie-breaker）**：為了讓紅綠燈順利運作，當演算法算出的行動價值過於接近時，我們引入了 `served_queue` 優先級作為打破平局的外部機制。
3. **去中心化獨立代理人**：系統將 16 個路口切分為獨立運作的 Agent，每個 Agent 僅根據局部觀測決策，而非求解全域的聯合 Dec-MDP。


## $V_i(s)$ to $V_i(s,a)$

在舊有的 $V_i(s)$ 架構下，系統期望透過局部轉移模型預測不同動作帶來的下一狀態（$s'_1, s'_2$），並透過 $V(s'_1)$ 與 $V(s'_2)$ 的不同來辨識動作好壞。

### 舊架構的問題
由於我們的轉移模型是 heuristic & local，預測出的下一狀態差異不夠大。丟進線性模型 $V(s) = \mathbf{w}^\top \boldsymbol{\phi}(s)$ 後，算出的價值幾乎相同。這導致 $R + \gamma V(s')$ **失去了動作鑑別度**，控制器最後只能被迫依賴外加的 `served_queue`（Greedy 邏輯），造成模型「名義上叫 ADP，實際上在跑 Greedy」。

### 新架構: Action-conditioned $V_i(s,a)$

為了解決上述問題，我們將價值函數改寫為 Action-conditioned：

$$V_i(s, a) \approx \mathbf{w}^\top \boldsymbol{\phi}_i(s, a)$$

此調整讓特徵向量 $\boldsymbol{\phi}_i(s, a)$ 直接將「狀態」與「特定動作」進行綁定。如此一來，即使單步轉移模型的預測不夠完美，模型的權重 $\mathbf{w}$ 也能直接在特徵層面上捕捉到特定動作的遠期風險，例如：
* 當前狀態下選擇 **東向 (East)**：特徵直接編碼「下游車道接近飽和（Spillback Risk 高）」。
* 當前狀態下選擇 **北向 (North)**：特徵直接編碼「雖然當前佇列短，但它是往遠離事故方向的安全路徑」。

---

# ADP Feature Design

在新的實作中，特徵向量已從單純的狀態特徵 $\boldsymbol{\phi}_i(s)$，改成 **Action-conditioned feature vector**：

$$\boldsymbol{\phi}_i(s, a)$$

這個修改很關鍵。因為在交通號誌控制中，像是 **pressure**、**downstream spillback risk**、以及「是否朝向事故方向」這些資訊，本質上都不是單純描述「目前狀態」而已，而是和「當下正在評估的特定動作 $a$」高度相關。

換句話說，我們希望模型學到的是：

* 在同一個狀態 $s$ 下，選擇 **North** 可能是安全的，但選擇 **East** 可能會把車流推向事故壅塞區。
* 因此，這些資訊應該直接進入 $\boldsymbol{\phi}_i(s, a)$，而不是只作為幾乎固定不變的 state feature。

目前主要使用的 feature groups 如下：

| Feature Group | 說明 |
| --- | --- |
| **Local incoming queues** | 描述該路口周圍的局部壅塞程度 |
| **Current phase one-hot** | 編碼目前正在放行的號誌方向 `N, E, S, W` |
| **Incident direction one-hot** | 編碼事故位置相對於該 Agent 的方向 `N, E, S, W, None` |
| **Candidate action one-hot** | 明確標示目前正在評估的候選動作 |
| **Candidate pressure** | `upstream queue - downstream queue` as a learnable feature |
| **Downstream occupancy / spillback risk** | 描述接收車道是否接近飽和，避免將車流送入壅塞區。 |
| **Candidate incident alignment** | 編碼候選動作是朝向事故、遠離事故，或與事故方向垂直。 |
| **Distance and time features** | 表示路口距離事故的遠近，以及事故發生後經過的時間。 |
| **Cross-features** | 將 spillback、candidate direction、incident activity、distance 等資訊綁定在一起。 |

這些 feature 的目的不是直接寫死控制規則，而是讓線性價值函數可以透過訓練自行決定哪些訊號重要。例如：

* **Candidate pressure** 讓模型具備類似 Max Pressure 的資訊，但不強迫它一定選最大 pressure 的方向。
* **Downstream spillback feature** 讓模型知道某個方向雖然 queue 很長，但下游可能已經沒有容量可以接收更多車流。
* **Incident alignment feature** 則讓模型區分「往事故方向送車」與「幫助車流繞開事故」之間的差異。

為了避免數值尺度過大導致訓練不穩定，feature scaling 和 clipping 也被明確加入：

```python
ADP_QUEUE_SCALE = 50.0
ADP_DISTANCE_SCALE = 6.0
ADP_TIME_SCALE = 120.0
ADP_FEATURE_CLIP = 5.0
ADP_MAX_ABS_WEIGHT = 50.0
ADP_MAX_ABS_TD_ERROR = 20.0
```

其中，`ADP_QUEUE_SCALE`、`ADP_DISTANCE_SCALE`、`ADP_TIME_SCALE` 用來將 queue、distance、time 等不同尺度的變數轉成較接近的數值範圍；`ADP_FEATURE_CLIP`、`ADP_MAX_ABS_WEIGHT`、`ADP_MAX_ABS_TD_ERROR` 則用來避免極端狀態下的 feature 或 TD error 造成權重爆炸。

需要特別強調的是，目前 **pressure bonus**、**spillback penalty**、以及 **incident-direction penalty** 仍然不是 hard-coded action-score override。它們只作為 **learnable inputs** 存在於 feature vector 中，讓 ADP 權重自行學習如何使用這些資訊。

---

# Reward and Transition Model

## Reward Design

Reward 的設計也進行了調整，使它和最終評估指標 **`queue_excess_area`** 更一致。

過去如果只懲罰 total queue，模型可能會把所有 queue 都視為同等重要；但在 incident recovery 的場景中，真正需要避免的是「超過正常 baseline 的額外壅塞」。因此，目前的 local queue cost 主要懲罰 non-incident local queue 中，超過 baseline threshold 的部分：

$$
\text{queue\_cost}
= \sum_e \max(0, q'_e - \tau \tilde{q}_e)
$$

其中，$\tilde{q}_e$ 代表對應 edge 的 baseline queue，$\tau$ 則是容忍倍率。這讓訓練目標更接近 evaluation 中使用的 **queue excess** 概念。

同時，系統仍保留一個小的 total-queue stabilizer：

```python
ADP_TOTAL_QUEUE_WEIGHT = 0.05
```

這個項目的作用是避免模型完全忽略總 queue 水準，只關注超過 threshold 的部分。

## Switch Penalty

號誌切換仍然會產生 lost-time-based penalty。原因是實際交通號誌在切換相位時，通常需要 yellow time 與 all-red time，這段時間內有效放行能力會下降。

目前設定為：

```python
SWITCH_PENALTY_SCALE = 0.10
YELLOW_SECONDS = 3
ALL_RED_SECONDS = 1
DECISION_INTERVAL = 10
```

因此每次切換相位的 penalty 為：

$$
0.10 \cdot \frac{3 + 1}{10} = 0.04
$$

這個 penalty 的目的不是禁止切換，而是避免控制器在行動價值差距很小時過度頻繁地切換相位。

## Gridlock Penalty

Gridlock penalty 也被調整為 capped and normalized，而不是過去那種非常大的 shock penalty：

```python
ADP_GRIDLOCK_PENALTY = 20.0
```

這樣可以讓模型仍然明確知道 gridlock 是嚴重失敗，但不至於因為單次極端懲罰讓訓練過程變得不穩定。

---

## Transition Model

目前的 one-step queue predictor 仍然是 approximate model，而不是從 SUMO 中完整學得的轉移模型。

然而，相比早期固定常數的做法，新的 transition predictor 更保守，也更貼近實際交通限制。主要差異包括：

1. **Green discharge 會受 downstream free space 限制**：即使上游有很多車，如果下游車道已接近飽和，模型不會假設綠燈可以無限制放行。
2. **Downstream capacity 由 SUMO lane length 與固定車距估算**：這讓 spillback risk 可以更合理地反映道路容量。
3. **Green discharge 與 red arrival rate 會在訓練中更新**：系統使用 observed SUMO queue deltas，透過 EWMA 估計更合理的放行與到達速率。
4. **Transition statistics 會與 ADP weights 一起保存**：訓練完成後，這些統計量在 evaluation 階段會被 frozen，避免測試時再繼續改變模型。
5. **Incident-blocked local approaches 不再被合成累積 queue**：避免 predictor 對已封閉或受事故影響的道路產生不合理的 queue growth 假設。

相關預設值如下：

```python
ADP_VEHICLE_SPACING = 7.5
ADP_MODEL_EWMA_ALPHA = 0.05
ADP_MIN_MODEL_OBSERVATIONS = 3
```

因此，雖然目前模型仍不是完整的 learned transition model，它已經比早期的固定常數模型更能反映 downstream capacity、demand variation 與 incident blockage 的影響。

TD update 使用的是 SUMO 執行後觀測到的 realized next queues：

$$
\delta
= r_i(s', a)
+ \gamma \max_{a'} V_i(s', a')
- V_i(s, a)
$$

這代表模型不是只依賴 heuristic predictor 做學習；實際權重更新仍會根據 SUMO 回傳的真實下一狀態進行修正。

---

# Evaluation Metrics

Evaluation 不直接使用內部 reward 判斷控制器好壞，而是使用外部交通表現指標。主要評估指標是：

```text
queue_excess_area
```

此指標衡量的是 non-incident congestion 超過 baseline queue threshold 後所累積的面積。換句話說，它關注的是事故後額外產生、且真正需要恢復的壅塞量。

`TTR`（Time to Recovery）則是次要指標，且只在成功恢復的 episodes 中有意義。原因是若某個 controller 雖然很快達到 recovery condition，但過程中產生大量 queue excess，它不一定代表整體控制效果較好。

目前報告使用的主要 metrics 如下：

| Metric | 說明 |
| --- | --- |
| **`queue_excess_area`** | 主要指標；衡量超過 baseline threshold 的累積壅塞量。 |
| **`success_rate`** | 符合 recovery condition 的 episode 比例。 |
| **`gridlock_rate`** | 最後進入 gridlock 的 episode 比例。 |
| **`TTR`** | 成功 episode 的恢復時間。 |
| **`throughput_recovery`** | 事故後 throughput 相對於 baseline 的恢復程度。 |
| **`switch_rate`** | 控制器切換號誌相位的頻率。 |

目前 success condition 維持較嚴格的設定：

* `TAU = 1.1`
* Rolling halting ratio
* Flow recovery
* Sustained confirmation window
* Incident-edge queues 會獨立報告，不再被用來隱藏 spillback 問題

此外，evaluation tooling 現在也會輸出：

```text
results/eval_paired_summary.csv
```

這個檔案用來呈現 paired comparison，包括：

* ADP vs. Greedy 的 queue-excess difference
* ADP vs. Max Pressure 的 queue-excess difference
* success / gridlock difference
* bootstrap confidence intervals

這樣的 paired summary 比單純比較平均值更可靠，因為它能在相同事故場景下直接比較不同 controller 的差異。

---

# Baselines

本研究比較的 controllers 如下：

| Controller | 說明 |
| --- | --- |
| **`fixed_time_rr`** | 固定順序輪流放行的 one-direction round-robin 控制器。 |
| **`greedy`** | 選擇目前 local queue 最大的方向。 |
| **`max_pressure`** | 選擇 upstream-minus-downstream pressure 最大的方向。 |
| **`adp_eval`** | 訓練後的 ADP-inspired controller。 |

所有 controllers 都遵守相同的 **one-direction-green phase constraint**。也就是說，任一時間點每個路口只能選擇一個方向放行，避免因號誌限制不同而造成不公平比較。

需要注意的是，**Greedy** 和 **Max Pressure** 不能被刻意削弱，也不應該在事後調參來讓 ADP 看起來更好。這點對報告的可信度很重要，因為本研究的目標是建立公平比較，而不是證明 ADP 必然勝出。

---

# Main Archived Result

目前最具可辯護性的 archived result 仍然是：

```text
results_archive/20260524_033708_rate2500_pre_adp_pressure_baseline
```

| Controller | Success Rate | Mean TTR | Mean Queue Excess Area | Throughput Recovery |
| --- | ---: | ---: | ---: | ---: |
| **ADP** | **87.5%** | 404.9 | 196,982 | 1.078 |
| **Greedy** | **87.5%** | **392.9** | **191,964** | **1.108** |
| **Max Pressure** | 75.0% | 357.7 | 338,356 | 0.955 |
| **Fixed-time RR** | 12.5% | 394.0 | 956,495 | 0.612 |

這個結果支援的是一個較保守、但更嚴謹的結論：

* **ADP 明顯優於 fixed-time round-robin control**。
* **ADP 與 greedy control 具有競爭力**。
* 在此 archived run 中，**ADP 的 queue excess 低於 max-pressure**。
* 但 **ADP 並沒有明確優於 greedy**，因為 greedy 在 Mean TTR、Mean Queue Excess Area 與 Throughput Recovery 上都略好。

因此，報告中不應該宣稱 ADP 是 absolute best controller。更合適的說法是：

> ADP-inspired controller 在 incident recovery 場景下具有競爭力，且明顯改善 fixed-time baseline，但目前證據尚不足以支持它穩定優於 greedy。

最後，新的 implementation changes 應該被視為 **optimization candidate**，而不是已被證明有效的最終結果。短時間的 smoke run 只能確認程式能正常執行，不能作為演算法優越性的證據。真正的效能主張仍需要透過 staged sweep 與 held-out final evaluation 驗證。

