# 事故誘發壅塞之 Dec-MDP / ADP 號誌控制系統

English README: [README.md](README.md)

本專案使用 SUMO 建立 4x4 路網事故情境，並以去中心化 Markov 決策流程（Dec-MDP）與近似動態規劃（ADP）控制各路口號誌。預設版本保留目前歷史最佳設定與權重，可直接重現 `RATE=2500` 的評估結果，同時把原本混在一起的程式、設定、模型、場景與輸出資料分開管理。

## 專案簡介與架構說明

```text
configs/                      實驗 preset，包含 historical_best、training、evaluation、smoke
models/historical_best/        預設 ADP 權重與 manifest
scenarios/grid_4x4/            可重現的 SUMO 路網、路徑與 GUI 設定
src/its_signal_control/        核心 Python 套件
scripts/                       一鍵重現、訓練、評估、OSM 匯入腳本
tests/                         不依賴 SUMO GUI 的核心單元測試
outputs/                       執行時產生的 metrics、圖表、權重與 step logs
```

核心模組分工如下：

- `agent.py`：ADP agent、特徵抽取、線性 value function、reward、transition heuristic。
- `experiment.py`：episode loop、訓練與評估流程。
- `controllers.py`：`fixed_time_rr`、`greedy`、`max_pressure`、`adp_eval` 控制器。
- `traffic_model.py`：SUMO 啟動參數、事故候選、路口幾何、成功與 gridlock 判定。
- `metrics.py`：CSV metrics、summary、paired comparison、權重讀寫。
- `routing.py`、`analysis.py`、`maps.py`、`features.py`、`decision_intervals.py`：為後續擴充保留的穩定邊界。

## 環境安裝指南

需求：

- Python 3.10+
- SUMO 1.20+，需包含 `sumo`、`sumo-gui`、`netconvert`、`randomTrips.py`
- Windows PowerShell 或 Bash

Windows PowerShell 範例：

```powershell
cd D:\Projects\AI\Final\traffic-adp-sumo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
$env:Path = "$env:SUMO_HOME\bin;$env:Path"
$env:PYTHONPATH = "$PWD\src;$env:PYTHONPATH"
```

Linux/macOS 範例：

```bash
cd traffic-adp-sumo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export SUMO_HOME=/path/to/sumo
export PATH="$SUMO_HOME/bin:$PATH"
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
```

## 快速重現現有最佳結果

預設重現使用：

- `configs/historical_best.yaml`
- `models/historical_best/adp_agent_weights.json`
- `scenarios/grid_4x4/grid_4x4_rate2500.rou.xml`
- headless SUMO，輸出到 `outputs/runs/historical_best/`

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce_best.ps1
```

跨平台：

```bash
python -m its_signal_control.cli evaluate \
  --preset configs/historical_best.yaml \
  --weights models/historical_best/adp_agent_weights.json \
  --headless
```

完成後會產生：

- `outputs/runs/historical_best/eval_metrics.csv`
- `outputs/runs/historical_best/eval_summary.csv`
- `outputs/runs/historical_best/eval_paired_summary.csv`
- `outputs/runs/historical_best/eval_comparison.svg`
- `outputs/runs/historical_best/eval_comparison_episodes.svg`

若要看 GUI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reproduce_best.ps1 -Gui
```

## 訓練與評估方法

訓練：

```bash
python -m its_signal_control.cli train --preset configs/training.yaml --headless
```

評估：

```bash
python -m its_signal_control.cli evaluate \
  --preset configs/evaluation.yaml \
  --weights models/historical_best/adp_agent_weights.json \
  --headless
```

重要參數：

- `RUN_TRAINING`：是否執行 ADP 訓練。
- `RUN_EVALUATION`：是否評估 baseline 與 ADP。
- `RESET_WEIGHTS_FOR_TRAINING`：訓練前是否清空權重。
- `LOAD_WEIGHTS_FOR_EVALUATION`：評估前是否載入權重。
- `EVALUATION_CONTROLLERS`：預設為 `fixed_time_rr`、`greedy`、`max_pressure`、`adp_eval`。
- `TRAIN_EPISODES`：預設 140。
- `EVAL_EPISODES_PER_CONTROLLER`：預設每個 controller 24 episodes。
- `REGENERATE_ROUTES`：是否重新產生 route file；預設使用已封存的 `grid_4x4_rate2500.rou.xml`。
- `USE_GUI`：是否使用 `sumo-gui`。
- `RENDER_STRESS`：是否在 GUI 中顯示 queue stress polygon。

## 開發者擴充指引

車輛重新導引時機評估：

- 修改 `configs/*.yaml` 的 `REROUTING_PERIOD`、`REROUTING_PROBABILITY` 與事故時間設定。
- 將 timing policy 放在 `src/its_signal_control/routing.py`。
- 評估時固定 baseline 集合，避免只比較 ADP。

Episode 內細粒度分析：

- 在 `analysis.py` 使用 `StepLogWriter` 寫入 queue、speed、reward、phase、action。
- 輸出位置固定為 `outputs/runs/<run_id>/step_logs/`。
- 不要把 step log commit 進 Git。

真實世界地圖匯入：

- 使用 `scripts/ingest_osm.py` 包裝 `netconvert`。
- 匯入後在 `scenarios/real_world/` 建立獨立 scenario。
- 保持 route、net、config 與 outputs 分離。

動態決策間隔與鄰居特徵：

- 在 `decision_intervals.py` 定義 per-agent interval policy。
- 在 `features.py` 擴充 neighbor queue/state feature。
- 保持 `ADPAgent.extract_features()` 的核心輸入相容，避免破壞既有權重載入流程。

## 結果與輸出檔案

所有執行輸出都應放在 `outputs/`：

- `train_metrics.csv`：訓練 episode 指標。
- `eval_metrics.csv`：各 controller 評估 episode 指標。
- `eval_summary.csv`：success rate、gridlock rate、TTR、queue excess、throughput recovery。
- `eval_paired_summary.csv`：ADP 與 baseline 的 paired comparison。
- `adp_agent_weights.json`：訓練後權重。
- `*.svg`：報告用圖表。

## Git 管理原則

應 commit：

- `src/`
- `configs/`
- `models/historical_best/`
- `scenarios/grid_4x4/`
- `README.md`
- `README.zh-TW.md`
- `WHITEPAPER.md`
- `tests/`

不應 commit：

- `outputs/` 內產物
- `results*`、`history/`、`route_tmp/`
- `__pycache__/`
- 大量歷史 sweep archive

歷史最佳權重已被正式封裝在 `models/historical_best/`，因此不需要把舊的 `results_validation/` 或 `results_archive/` 放入 Git。
