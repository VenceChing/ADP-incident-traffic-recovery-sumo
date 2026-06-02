#!/usr/bin/env python3
"""
決策順序訓練腳本 - 完整訓練流程

為每個決策順序策略（除了對照組）單獨訓練權重
訓練步驟：
1. 重置權重（清空）
2. 執行訓練 episodes
3. 保存策略特定的權重
4. 回到評估模式
"""

import json
import sys
import random
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from its_signal_control import config
from its_signal_control.experiment import run_episode
from its_signal_control.traffic_model import (
    build_agents,
    build_controller_context,
    build_incident_candidates,
    split_incidents,
)
from its_signal_control.env import SumoEnv
from its_signal_control.metrics import save_agent_weights, reset_agent_weights

# 訓練配置
STRATEGIES_TO_TRAIN = [
    #("distance_decay", "距離遞減：距離事故最遠優先決策"),
    ("checkerboard", "棋盤式：對角線不相鄰，最小衝突"),
    ("ring", "環形：外向內螺旋排列"),
    #("greedy_dynamic", "動態貪心：根據隊列長度排序"),
    #("random", "隨機順序：基準對照"),
]

TRAIN_EPISODES_PER_STRATEGY = 10  # 每個策略訓練 50 個 episode
NUM_PHASES = 4


def setup_training_dir(strategy: str) -> Path:
    """建立策略特定的訓練輸出目錄"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = config.REPO_ROOT / "models" / f"decision_order_{strategy}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def train_strategy(
    strategy: str,
    description: str,
    env: SumoEnv,
    agents: dict[str, Any],
    context: dict[str, Any],
    train_incident_edges: list[list[str]],
    training_dir: Path,
) -> dict[str, Any]:
    """
    訓練某個策略
    
    訓練流程：
    1. 重置所有 agent 的權重（清零）
    2. 執行 TRAIN_EPISODES_PER_STRATEGY 個 episode
    3. 保存訓練後的權重
    4. 返回訓練統計
    """
    print(f"\n{'='*70}")
    print(f"訓練策略: {strategy}")
    print(f"描述: {description}")
    print(f"{'='*70}")

    # 保存原始配置
    original_strategy = config.DECISION_ORDER_STRATEGY
    original_neighbor_info = config.ALLOW_NEIGHBOR_INFO
    original_load_weights = config.LOAD_WEIGHTS_FOR_EVALUATION

    try:
        # 配置設定
        config.DECISION_ORDER_STRATEGY = strategy
        config.ALLOW_NEIGHBOR_INFO = True  # 訓練時啟用鄰近信息
        config.LOAD_WEIGHTS_FOR_EVALUATION = False  # 不載入舊權重
        config.RESET_WEIGHTS_FOR_TRAINING = True  # 重置權重

        # Step 1: 重置所有 agent 的權重（清零）
        print(f"\n[Step 1/3] 重置權重（清零所有 {len(agents)} 個路口）...")
        reset_agent_weights(agents)
        for agent_id, agent in agents.items():
            if not all(w == 0.0 for w in agent.weights):
                print(f"  警告：{agent_id} 權重未完全重置")
        print(f"✓ 所有權重已重置")

        # Step 2: 執行訓練 episodes
        print(f"\n[Step 2/3] 執行訓練 ({TRAIN_EPISODES_PER_STRATEGY} episodes)...")

        train_results = []
        episode_start_time = datetime.now()

        for episode in range(TRAIN_EPISODES_PER_STRATEGY):
            # 循環使用訓練事故
            incident_edges = train_incident_edges[episode % len(train_incident_edges)]
            seed = episode * 10000 + hash(strategy) % 1000

            if (episode + 1) % 10 == 0:
                elapsed = (datetime.now() - episode_start_time).total_seconds()
                avg_time_per_episode = elapsed / (episode + 1)
                remaining = avg_time_per_episode * (TRAIN_EPISODES_PER_STRATEGY - episode - 1)
                print(
                    f"  Episode {episode + 1:3d}/{TRAIN_EPISODES_PER_STRATEGY} "
                    f"[{elapsed:6.1f}s elapsed, {remaining:6.1f}s remaining] "
                    f"seed={seed} incident={incident_edges}"
                )

            result = run_episode(
                phase="training",
                controller="adp_train",
                episode=episode,
                seed=seed,
                incident_edges=incident_edges,
                env=env,
                agents=agents,
                context=context,
                metrics_path=str(training_dir / "train_metrics.csv"),
                train_adp=True,
            )

            # 🔥 【核心修正 1：精準對齊真實 row 字典的 status 欄位】 🔥
            ep_status = result.get("status", "UNKNOWN")
            
            train_results.append(
                {
                    "episode": episode,
                    "status": ep_status,
                    # 根據 status 的字串內容，動態生成真實的布林值
                    "success": ep_status == "SUCCESS",
                    "gridlock": ep_status == "GRIDLOCK",
                }
            )

        total_elapsed = (datetime.now() - episode_start_time).total_seconds()
        success_count = sum(1 for r in train_results if r["success"])
        gridlock_count = sum(1 for r in train_results if r["gridlock"])

        print(f"\n✓ 訓練完成")
        print(f"  總耗時: {total_elapsed:.1f} 秒")
        print(f"  成功: {success_count}/{TRAIN_EPISODES_PER_STRATEGY} ({success_count*100/TRAIN_EPISODES_PER_STRATEGY:.1f}%)")
        print(f"  鎖定: {gridlock_count}/{TRAIN_EPISODES_PER_STRATEGY} ({gridlock_count*100/TRAIN_EPISODES_PER_STRATEGY:.1f}%)")

        # Step 3: 保存訓練後的權重
        print(f"\n[Step 3/3] 保存訓練後的權重...")

        # 權重保存為 JSON
        weights_file = training_dir / f"adp_agent_weights_{strategy}.json"
        save_agent_weights(agents, str(weights_file))
        print(f"✓ 權重已保存: {weights_file}")

        # 保存訓練統計
        train_summary = {
            "strategy": strategy,
            "description": description,
            "feature_dimension": agents[list(agents.keys())[0]].feature_dim,
            "allow_neighbor_info": True,
            "training_episodes": TRAIN_EPISODES_PER_STRATEGY,
            "total_elapsed_seconds": total_elapsed,
            "success_count": success_count,
            "success_rate": success_count / TRAIN_EPISODES_PER_STRATEGY,
            "gridlock_count": gridlock_count,
            "gridlock_rate": gridlock_count / TRAIN_EPISODES_PER_STRATEGY,
            "training_details": train_results,
        }

        summary_file = training_dir / "train_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(train_summary, f, indent=2, ensure_ascii=False)
        print(f"✓ 訓練摘要已保存: {summary_file}")

        return train_summary

    finally:
        # 恢復原始配置
        config.DECISION_ORDER_STRATEGY = original_strategy
        config.ALLOW_NEIGHBOR_INFO = original_neighbor_info
        config.LOAD_WEIGHTS_FOR_EVALUATION = original_load_weights


def train_unified_baseline(
    env: SumoEnv,
    agents: dict[str, Any],
    context: dict[str, Any],
    train_incident_edges: list[list[str]],
    training_dir: Path,
) -> dict[str, Any]:
    """
    訓練對照組（Unified - 同時決策，無鄰近信息）
    
    這個作為基準對照，用來比較新策略的改進
    """
    print(f"\n{'='*70}")
    print(f"訓練對照組: unified")
    print(f"描述: 同時決策，無鄰近資訊（基準對照）")
    print(f"{'='*70}")

    original_strategy = config.DECISION_ORDER_STRATEGY
    original_neighbor_info = config.ALLOW_NEIGHBOR_INFO
    original_load_weights = config.LOAD_WEIGHTS_FOR_EVALUATION

    try:
        config.DECISION_ORDER_STRATEGY = "unified"
        config.ALLOW_NEIGHBOR_INFO = False
        config.LOAD_WEIGHTS_FOR_EVALUATION = False
        config.RESET_WEIGHTS_FOR_TRAINING = True

        print(f"\n[Step 1/3] 重置權重（清零所有 {len(agents)} 個路口）...")
        reset_agent_weights(agents)
        print(f"✓ 所有權重已重置")

        print(f"\n[Step 2/3] 執行訓練 ({TRAIN_EPISODES_PER_STRATEGY} episodes)...")

        train_results = []
        episode_start_time = datetime.now()

        for episode in range(TRAIN_EPISODES_PER_STRATEGY):
            incident_edges = train_incident_edges[episode % len(train_incident_edges)]
            seed = episode * 10000 + 9999

            if (episode + 1) % 10 == 0:
                elapsed = (datetime.now() - episode_start_time).total_seconds()
                avg_time_per_episode = elapsed / (episode + 1)
                remaining = avg_time_per_episode * (TRAIN_EPISODES_PER_STRATEGY - episode - 1)
                print(
                    f"  Episode {episode + 1:3d}/{TRAIN_EPISODES_PER_STRATEGY} "
                    f"[{elapsed:6.1f}s elapsed, {remaining:6.1f}s remaining]"
                )

            result = run_episode(
                phase="training",
                controller="adp_train",
                episode=episode,
                seed=seed,
                incident_edges=incident_edges,
                env=env,
                agents=agents,
                context=context,
                metrics_path=str(training_dir / "train_metrics_baseline.csv"),
                train_adp=True,
            )

            # 🔥 【核心修正 1：精準對齊真實 row 字典的 status 欄位】 🔥
            ep_status = result.get("status", "UNKNOWN")
            
            train_results.append(
                {
                    "episode": episode,
                    "status": ep_status,
                    # 根據 status 的字串內容，動態生成真實的布林值
                    "success": ep_status == "SUCCESS",
                    "gridlock": ep_status == "GRIDLOCK",
                }
            )

        total_elapsed = (datetime.now() - episode_start_time).total_seconds()
        success_count = sum(1 for r in train_results if r["success"])
        gridlock_count = sum(1 for r in train_results if r["gridlock"])

        print(f"\n✓ 訓練完成")
        print(f"  成功: {success_count}/{TRAIN_EPISODES_PER_STRATEGY} ({success_count*100/TRAIN_EPISODES_PER_STRATEGY:.1f}%)")
        print(f"  鎖定: {gridlock_count}/{TRAIN_EPISODES_PER_STRATEGY} ({gridlock_count*100/TRAIN_EPISODES_PER_STRATEGY:.1f}%)")

        print(f"\n[Step 3/3] 保存訓練後的權重...")

        weights_file = training_dir / "adp_agent_weights_unified.json"
        save_agent_weights(agents, str(weights_file))
        print(f"✓ 權重已保存: {weights_file}")

        train_summary = {
            "strategy": "unified",
            "description": "同時決策，無鄰近資訊（基準對照）",
            "feature_dimension": agents[list(agents.keys())[0]].feature_dim,
            "allow_neighbor_info": False,
            "training_episodes": TRAIN_EPISODES_PER_STRATEGY,
            "total_elapsed_seconds": total_elapsed,
            "success_count": success_count,
            "success_rate": success_count / TRAIN_EPISODES_PER_STRATEGY,
            "gridlock_count": gridlock_count,
            "gridlock_rate": gridlock_count / TRAIN_EPISODES_PER_STRATEGY,
        }

        summary_file = training_dir / "train_summary_baseline.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(train_summary, f, indent=2, ensure_ascii=False)

        return train_summary

    finally:
        config.DECISION_ORDER_STRATEGY = original_strategy
        config.ALLOW_NEIGHBOR_INFO = original_neighbor_info
        config.LOAD_WEIGHTS_FOR_EVALUATION = original_load_weights


def main():
    """主訓練函數"""
    print("="*70)
    print("決策順序訓練流程")
    print("="*70)
    print()
    print(f"訓練配置：")
    print(f"  - 對照組訓練: unified (無鄰近信息)")
    print(f"  - 策略訓練: {len(STRATEGIES_TO_TRAIN)} 個（含鄰近信息）")
    print(f"  - 每個策略訓練 episode 數: {TRAIN_EPISODES_PER_STRATEGY}")
    print(f"  - 特徵維度擴展: 30 維 (unified) → 66 維 (with neighbor info)")
    print()

    training_root = config.REPO_ROOT / "models" / f"decision_order_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    training_root.mkdir(parents=True, exist_ok=True)
    print(f"訓練輸出目錄: {training_root}\n")

    # 初始化 SUMO 環境
    print("初始化 SUMO 環境...")
    env = SumoEnv(use_gui=False, step_length=0.1)
    env.start_simulation()

    # 構建 agents 和 context
    print("構建 agents 和 context...")
    node_ids = [tls.getID() for tls in env.net.getTrafficLights()]
    agents = build_agents(node_ids)
    context = build_controller_context(node_ids)

    # 構建事故候選
    all_incident_edges = [edge.getID() for edge in env.net.getEdges()]
    incident_candidates = build_incident_candidates(all_incident_edges, list(agents.keys()))
    train_incident_edges, eval_incident_edges = split_incidents(incident_candidates)

    print(f"路口數: {len(agents)}")
    print(f"訓練事故: {len(train_incident_edges)}")
    print(f"評估事故: {len(eval_incident_edges)}\n")

    training_summaries = {}

    # Step 1: 訓練對照組（無鄰近信息）
    print(f"\n{'#'*70}")
    print(f"# Step 1/6: 訓練對照組 (Unified)")
    print(f"{'#'*70}")
    #summary = train_unified_baseline(env, agents, context, train_incident_edges, training_root)
    #training_summaries["unified"] = summary

    # Step 2-6: 訓練各策略（含鄰近信息）
    for idx, (strategy, description) in enumerate(STRATEGIES_TO_TRAIN, 2):
        print(f"\n{'#'*70}")
        print(f"# Step {idx}/{len(STRATEGIES_TO_TRAIN)+1}: 訓練策略 ({strategy})")
        print(f"{'#'*70}")

        summary = train_strategy(strategy, description, env, agents, context, train_incident_edges, training_root)
        training_summaries[strategy] = summary

    # 生成訓練總結報告
    print(f"\n{'='*70}")
    print("訓練完成！")
    print(f"{'='*70}\n")

    print("訓練結果摘要：\n")
    for strategy, summary in training_summaries.items():
        print(f"策略: {strategy:20s} | 成功率: {summary['success_rate']*100:5.1f}% | 鎖定率: {summary['gridlock_rate']*100:5.1f}%")

    # 保存訓練總結
    all_summaries = {
        "timestamp": datetime.now().isoformat(),
        "training_config": {
            "episodes_per_strategy": TRAIN_EPISODES_PER_STRATEGY,
            "feature_dimension_no_neighbor": 30,
            "feature_dimension_with_neighbor": 66,
        },
        "strategies": training_summaries,
    }

    summary_file = training_root / "training_complete_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, ensure_ascii=False)

    print(f"\n✓ 訓練總結已保存: {summary_file}")
    print(f"\n🎉 訓練流程完全完成！")
    print(f"   權重已保存至: {training_root}")
    print(f"   下一步：執行評估以驗證訓練效果")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n中斷訓練")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n錯誤: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
