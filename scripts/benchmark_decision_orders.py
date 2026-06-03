#!/usr/bin/env python3
"""
完整決策順序對比基準測試腳本

測試5個有理論依據的決策順序策略 + 1個對照組（原始同時決策）：
1. unified          - 同時決策（對照組）
2. distance_decay   - 距離遞減（距離事故最遠優先）
3. checkerboard     - 棋盤式（對角線不相鄰）
4. ring             - 環形螺旋
5. greedy_dynamic   - 動態貪心（根據隊列優先）
6. random           - 隨機順序

輸出：
- comparison_table.csv - 聚合對比表
- decision_order_results_<timestamp>.json - 詳細結果
- comparison_chart.svg - 視覺化對比圖
"""

import json
import os
import sys
import random
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from its_signal_control import config
from its_signal_control.experiment import run_episode
from its_signal_control.traffic_model import build_agents, build_controller_context, build_incident_candidates
from its_signal_control.env import SumoEnv
from its_signal_control.metrics import (
    load_agent_weights,
    summarize_eval_metrics,
    summarize_paired_eval_metrics,
)


STRATEGIES = [
    ("unified", "對照組：同時決策（無鄰近資訊）"),
    ("distance_decay", "距離遞減：距離事故最遠優先決策"),
    ("checkerboard", "棋盤式：對角線不相鄰，最小衝突"),
    ("ring", "環形：外向內螺旋排列"),
    ("greedy_dynamic", "動態貪心：根據隊列長度排序"),
    ("random", "隨機順序：基準對照"),
]

NUM_EPISODES_PER_STRATEGY = 10
EVAL_CONTROLLERS = ["adp_eval"]


def setup_output_dir() -> str:
    """建立輸出目錄"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = config.REPO_ROOT / "outputs" / f"decision_order_benchmark_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir)


def run_strategy_evaluation(
    strategy: str,
    allow_neighbor_info: bool,
    env: SumoEnv,
    agents: dict[str, Any],
    context: dict[str, Any],
    train_incident_edges: list[list[str]],
    eval_incident_edges: list[list[str]],
    output_dir: str,
    weights_dir: Path,
) -> dict[str, Any]:
    """
    執行某個策略的評估
    
    Returns:
        {
            'strategy': str,
            'success_rate': float,
            'gridlock_rate': float,
            'avg_ttr': float,
            'avg_queue_excess': float,
        }
    """
    print(f"\n{'='*70}")
    print(f"評估策略: {strategy}")
    print(f"允許鄰近資訊: {allow_neighbor_info}")
    print(f"{'='*70}")

    # 臨時保存原始配置
    original_strategy = config.DECISION_ORDER_STRATEGY
    original_neighbor_info = config.ALLOW_NEIGHBOR_INFO

    try:
        # 修改配置
        config.DECISION_ORDER_STRATEGY = strategy
        config.ALLOW_NEIGHBOR_INFO = allow_neighbor_info
        config.LOAD_WEIGHTS_FOR_EVALUATION = True

        # 載入對應策略的訓練權重
        weights_file = weights_dir / f"adp_agent_weights_{strategy}.json"
        if weights_file.exists():
            print(f"  載入權重: {weights_file}")
            load_agent_weights(agents, str(weights_file))
        else:
            print(f"  ⚠️  警告: 未找到權重檔案 {weights_file}")
            print(f"  將使用現有的 agent 權重")

        episodes_data = []
        metrics_file = config.REPO_ROOT / "outputs" / "eval_metrics.csv"

        for episode in range(NUM_EPISODES_PER_STRATEGY):
            # 選擇評估用事故
            incident_edges = eval_incident_edges[episode % len(eval_incident_edges)]

            for controller in EVAL_CONTROLLERS:
                seed = episode * 1000 + hash(strategy) % 100

                print(
                    f"  Episode {episode + 1}/{NUM_EPISODES_PER_STRATEGY} | "
                    f"Controller: {controller} | Seed: {seed}"
                )

                result = run_episode(
                    phase="evaluation",
                    controller=controller,
                    episode=episode,
                    seed=seed,
                    incident_edges=incident_edges,
                    env=env,
                    agents=agents,
                    context=context,
                    metrics_path=str(metrics_file),
                    train_adp=False,
                )

                # 🔥 🔥 🔥 【終極對齊修正】 🔥 🔥 🔥
                episodes_data.append(
                    {
                        "episode": episode,
                        "controller": controller,
                        "incident_edges": incident_edges,
                        # 1. row 裡面是 "status" (SUCCESS 或 GRIDLOCK)
                        "status": result.get("status", "UNKNOWN"),
                        
                        # 2. 為了相容你之前在 main() 改好的統計，這裡直接把 row 的 ttr 和 avg_queue_excess 轉型存進去
                        "ttr": result.get("ttr", "0.0"),
                        "avg_queue_excess": result.get("avg_queue_excess", "0.0000"),
                    }
                )

        # 計算統計
        '''
        total_episodes = len(episodes_data)
        success_count = sum(1 for e in episodes_data if e["success"])
        gridlock_count = sum(1 for e in episodes_data if e["gridlock"])
        avg_ttr = sum(e["ttr"] for e in episodes_data) / max(1, total_episodes)
        # 修改後：安全轉換型態，過濾掉無法轉成數字的字串
        valid_queue_excesses = []
        for e in episodes_data:
            val = e.get("queue_excess", 0)
            # 如果是字串，先看看能不能轉成數字，不能的話（如 "N/A"）就當作 0
            if isinstance(val, str):
                try:
                    valid_queue_excesses.append(float(val))
                except ValueError:
                    valid_queue_excesses.append(0.0)  # 無法解析的字串當作 0
            else:
                valid_queue_excesses.append(float(val))

        avg_queue_excess = sum(valid_queue_excesses) / max(1, total_episodes)

        return {
            "strategy": strategy,
            "allow_neighbor_info": allow_neighbor_info,
            "episodes": episodes_data,
            "total_episodes": total_episodes,
            "success_count": success_count,
            "success_rate": success_count / max(1, total_episodes),
            "gridlock_count": gridlock_count,
            "gridlock_rate": gridlock_count / max(1, total_episodes),
            "avg_ttr": avg_ttr,
            "avg_queue_excess": avg_queue_excess,
        }'''

        # ======================================================================
        # 🔥 【終極修正】完全對齊 row 欄位並進行字串轉數字的型態防禦
        # ======================================================================
        total_episodes = len(episodes_data)
        
        success_count = 0
        gridlock_count = 0
        valid_ttrs = []
        valid_queue_excesses = []

        for e in episodes_data:
            # 1. 讀取狀態並統計
            status = e.get("status")
            if status == "SUCCESS":
                success_count += 1
            elif status == "GRIDLOCK":
                gridlock_count += 1

            # 2. 安全讀取 TTR (因為 row 裡面儲存的是字串，需要轉成 float)
            ttr_val = e.get("ttr", "")
            if ttr_val and ttr_val != "":
                try:
                    valid_ttrs.append(float(ttr_val))
                except (ValueError, TypeError):
                    pass

            # 3. 安全讀取平均隊列超額 (row 裡面是字串如 "12.3456")
            queue_val = e.get("avg_queue_excess", "0.0000")
            try:
                valid_queue_excesses.append(float(queue_val))
            except (ValueError, TypeError):
                valid_queue_excesses.append(0.0)

        # 4. 計算最終的統計指標
        success_rate = success_count / max(1, total_episodes)
        gridlock_rate = gridlock_count / max(1, total_episodes)
        
        # 平均 TTR：只計算成功恢復的場次之平均時間
        avg_ttr = sum(valid_ttrs) / max(1, len(valid_ttrs)) if valid_ttrs else 0.0
        
        # 平均隊列超額
        avg_queue_excess = sum(valid_queue_excesses) / max(1, total_episodes) if valid_queue_excesses else 0.0

        # 5. 回傳給 main() 的結果字典 (對齊 main 裡面讀取的 Key)
        print(f"  統計結果 - 成功率: {success_rate*100:.1f}%, 鎖定率: {gridlock_rate*100:.1f}%, 平均 TTR: {avg_ttr:.1f} 秒, 平均隊列超額: {avg_queue_excess:.1f}")
        return {
            "success_rate": success_rate,
            "gridlock_rate": gridlock_rate,
            "avg_ttr": avg_ttr,
            "avg_queue_excess": avg_queue_excess,
        }

    finally:
        # 恢復原始配置
        config.DECISION_ORDER_STRATEGY = original_strategy
        config.ALLOW_NEIGHBOR_INFO = original_neighbor_info


def main():
    """主函數"""
    print("="*70)
    print("決策順序完整對比基準測試")
    print("="*70)

    # 要求提供訓練權重目錄
    import sys
    if len(sys.argv) < 2:
        print("\n使用方式:")
        print(f"  python {sys.argv[0]} <weights_dir>")
        print("\n範例:")
        print(f"  python {sys.argv[0]} models/decision_order_training_20260602_120000")
        print("\n說明:")
        print("  <weights_dir> 應該是包含以下檔案的目錄：")
        print("    - adp_agent_weights_unified.json")
        print("    - adp_agent_weights_distance_decay.json")
        print("    - adp_agent_weights_checkerboard.json")
        print("    - adp_agent_weights_ring.json")
        print("    - adp_agent_weights_greedy_dynamic.json")
        print("    - adp_agent_weights_random.json")
        sys.exit(1)

    from pathlib import Path

    weights_dir = Path(sys.argv[1])
    if not weights_dir.exists():
        print(f"\n✗ 錯誤: 權重目錄不存在: {weights_dir}")
        sys.exit(1)

    output_dir = setup_output_dir()
    print(f"\n輸出目錄: {output_dir}\n")

    # 初始化 SUMO 環境
    print("初始化 SUMO 環境...")
    env = SumoEnv(use_gui=False, step_length=0.1)
    env.start_simulation()
    
    # 構建 agents 和 context
    print("構建 agents 和 context...")
    # 🔥 【核心修正】只篩選出路網中真正是紅綠燈（Traffic Light）的節點 ID
    node_ids = [tls.getID() for tls in env.net.getTrafficLights()]
    agents = build_agents(node_ids)
    # 修改後：傳入剛才篩選出來的紅綠燈 ID 列表 (node_ids)
    context = build_controller_context(node_ids)

    # 構建事故候選
    # 【修正 3】sumolib.Net 沒有 getEdgeIDs()，修正為從 getEdges() 提取 ID 列表
    all_incident_edges = [edge.getID() for edge in env.net.getEdges()]
    incident_candidates = build_incident_candidates(all_incident_edges, list(agents.keys()))

    # 分割訓練和評估事故
    from its_signal_control.traffic_model import split_incidents

    train_incident_edges, eval_incident_edges = split_incidents(incident_candidates)

    print(f"訓練事故: {len(train_incident_edges)}")
    print(f"評估事故: {len(eval_incident_edges)}")

    # 運行所有策略
    results = {}
    for idx, (strategy, description) in enumerate(STRATEGIES, 1):
        print(f"\n[{idx}/{len(STRATEGIES)}] {description}")

        # 對於無鄰近資訊的策略（對照組），禁用鄰近資訊
        allow_neighbor_info = strategy != "unified"

        result = run_strategy_evaluation(
            strategy=strategy,
            allow_neighbor_info=allow_neighbor_info,
            env=env,
            agents=agents,
            context=context,
            train_incident_edges=train_incident_edges,
            eval_incident_edges=eval_incident_edges,
            output_dir=output_dir,
            weights_dir=weights_dir,
        )

        results[strategy] = result

    # 輸出對比表
    print(f"\n{'='*70}")
    print("對比結果總結")
    print(f"{'='*70}\n")

    comparison_data = []
    for strategy, description in STRATEGIES:
        if strategy not in results:
            continue

        result = results[strategy]
        comparison_data.append(
            {
                "策略": strategy,
                "描述": description,
                "成功率 %": f"{result['success_rate']*100:.1f}%",
                "鎖定率 %": f"{result['gridlock_rate']*100:.1f}%",
                "平均 TTR (秒)": f"{result['avg_ttr']:.1f}",
                "平均隊列超額": f"{result['avg_queue_excess']:.1f}",
            }
        )

        print(f"策略: {strategy}")
        print(f"  描述: {description}")
        print(f"  成功率: {result['success_rate']*100:.1f}%")
        print(f"  鎖定率: {result['gridlock_rate']*100:.1f}%")
        print(f"  平均 TTR: {result['avg_ttr']:.1f} 秒")
        print(f"  平均隊列超額: {result['avg_queue_excess']:.1f}")
        print()

    # 保存結果
    from datetime import datetime
    import json
    from pathlib import Path
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = Path(output_dir) / f"decision_order_results_{timestamp}.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"✓ 詳細結果已保存: {results_file}")

    # 保存對比表
    comparison_file = Path(output_dir) / "comparison_table.csv"
    import csv

    with open(comparison_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=comparison_data[0].keys())
        writer.writeheader()
        writer.writerows(comparison_data)
    print(f"✓ 對比表已保存: {comparison_file}")

    # 找出最優策略
    best_strategy = max(
        results.items(),
        key=lambda x: x[1]["success_rate"] - 0.5 * x[1]["gridlock_rate"],
    )
    print(f"\n★ 推薦策略: {best_strategy[0]} (成功率: {best_strategy[1]['success_rate']*100:.1f}%)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n中斷測試")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n錯誤: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
