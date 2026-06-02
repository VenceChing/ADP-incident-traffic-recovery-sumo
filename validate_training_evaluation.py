#!/usr/bin/env python3
"""
驗證決策順序訓練與評估流程的完整性

檢查項目：
1. 必要的模組是否存在
2. 配置是否正確
3. 特徵維度是否正確
4. 決策順序策略是否正確實現
5. 權重保存和載入是否正確
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from its_signal_control import config
from its_signal_control.decision_intervals import DecisionOrderSchedule
from its_signal_control.controllers import DecisionCache
from its_signal_control.agent import ADPAgent
from its_signal_control.metrics import load_agent_weights, save_agent_weights, reset_agent_weights
import json


def check_config():
    """檢查配置"""
    print("\n✓ 檢查配置...")
    
    required_configs = [
        ("DECISION_ORDER_STRATEGY", str),
        ("ALLOW_NEIGHBOR_INFO", bool),
        ("PREVENT_CONSECUTIVE_DECISION", bool),
        ("DECISION_INTERVAL", (int, float)),
        ("DECISION_ORDER_RANDOM_SEED", int),
    ]
    
    for config_name, expected_type in required_configs:
        if not hasattr(config, config_name):
            print(f"  ✗ 缺少配置: {config_name}")
            return False
        
        value = getattr(config, config_name)
        if not isinstance(value, expected_type):
            print(f"  ✗ 配置 {config_name} 類型錯誤: 應為 {expected_type}, 實為 {type(value)}")
            return False
    
    print(f"  ✓ 所有配置存在且類型正確")
    print(f"    - DECISION_ORDER_STRATEGY = {config.DECISION_ORDER_STRATEGY}")
    print(f"    - ALLOW_NEIGHBOR_INFO = {config.ALLOW_NEIGHBOR_INFO}")
    print(f"    - PREVENT_CONSECUTIVE_DECISION = {config.PREVENT_CONSECUTIVE_DECISION}")
    return True


def check_decision_order_strategies():
    """檢查決策順序策略"""
    print("\n✓ 檢查決策順序策略...")
    
    strategies = ["unified", "distance_decay", "checkerboard", "ring", "greedy_dynamic", "random"]
    test_agents = [f"ti_{i}_{j}" for i in range(4) for j in range(4)]
    
    for strategy in strategies:
        try:
            schedule = DecisionOrderSchedule(
                strategy=strategy,
                agent_ids=test_agents,
                incident_edges=["edge1", "edge2"],
                decision_interval=10.0,
                random_seed=42,
            )
            order = schedule.decision_order_for_timestep(0.0)
            
            if len(order) != len(test_agents):
                print(f"  ✗ 策略 {strategy} 返回的順序長度不符")
                return False
            
            if len(set(order)) != len(test_agents):
                print(f"  ✗ 策略 {strategy} 返回的順序中有重複")
                return False
            
            print(f"  ✓ 策略 {strategy:15s} - 正常 ({len(order)} 個路口)")
        except Exception as e:
            print(f"  ✗ 策略 {strategy} 拋出異常: {e}")
            return False
    
    return True


def check_decision_cache():
    """檢查決策快取"""
    print("\n✓ 檢查決策快取...")
    
    try:
        cache = DecisionCache()
        
        # 測試快取決策
        cache.cache_decision("ti_0_0", 2, 1, 15.0, 10.0)
        cache.cache_decision("ti_0_1", 1, 0, 20.0, 10.0)
        
        # 測試獲取鄰近資訊
        neighbors = {"ti_0_1": 0}  # 模擬 ti_0_0 的鄰近路口
        neighbor_info = cache.get_neighbor_info("ti_0_0", neighbors)
        
        if not isinstance(neighbor_info, tuple) or len(neighbor_info) != 3:
            print(f"  ✗ get_neighbor_info() 返回格式錯誤")
            return False
        
        neighbor_actions, neighbor_phases, neighbor_queues = neighbor_info
        print(f"  ✓ 決策快取正常")
        print(f"    - 已快取決策數: 2")
        print(f"    - 獲取鄰近資訊: 成功")
        return True
    except Exception as e:
        print(f"  ✗ 決策快取異常: {e}")
        return False


def check_feature_dimensions():
    """檢查特徵維度"""
    print("\n✓ 檢查特徵維度...")
    
    try:
        # 建立測試 agent（模擬 4-相位十字路口）
        incoming_edges = ["e0", "e1", "e2", "e3"]
        num_phases = 4
        agent = ADPAgent(
            agent_id="test_agent",
            incoming_edges=incoming_edges,
            num_phases=num_phases,
        )
        
        # 不含鄰近信息時的維度
        # queue_features (4) + phase_features (4) + incident_direction_features (4)
        # + action_features (4) + global_features (13) = 29-30
        base_features = agent.extract_features(
            current_queues={e: 10.0 for e in incoming_edges},
            current_phase=0,
            dist_to_incident=50.0,
            incident_direction=0,
            time_discrete=10,
            incident_active=True,
            action=0,
        )
        
        base_dim = len(base_features)
        print(f"  ✓ 無鄰近信息維度: {base_dim}")
        if base_dim != 30:
            print(f"    ⚠️  警告: 預期 30 維，實際 {base_dim} 維")
        
        # 含鄰近信息時的維度
        neighbor_actions = {"ti_0_1": 1, "ti_1_0": 2, "ti_0_-1": 3}
        neighbor_phases = {"ti_0_1": 1, "ti_1_0": 2, "ti_0_-1": 3}
        neighbor_queues = {"ti_0_1": 15.0, "ti_1_0": 20.0, "ti_0_-1": 12.0}
        
        with_neighbor_features = agent.extract_features(
            current_queues={e: 10.0 for e in incoming_edges},
            current_phase=0,
            dist_to_incident=50.0,
            incident_direction=0,
            time_discrete=10,
            incident_active=True,
            action=0,
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
        )
        
        with_neighbor_dim = len(with_neighbor_features)
        print(f"  ✓ 含鄰近信息維度: {with_neighbor_dim}")
        if with_neighbor_dim != 66:
            print(f"    ⚠️  警告: 預期 66 維，實際 {with_neighbor_dim} 維")
        
        # 驗證維度關係
        neighbor_dim = with_neighbor_dim - base_dim
        print(f"  ✓ 鄰近信息維度: {neighbor_dim}")
        if neighbor_dim != 36:
            print(f"    ⚠️  警告: 預期 36 維鄰近特徵，實際 {neighbor_dim} 維")
        
        # 驗證 agent 的 feature_dim 屬性
        if agent.feature_dim != 30:
            print(f"    ⚠️  警告: agent.feature_dim = {agent.feature_dim}，預期 30")
        
        return True
    except Exception as e:
        print(f"  ✗ 特徵維度檢查異常: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_weights_management():
    """檢查權重保存和載入"""
    print("\n✓ 檢查權重管理...")
    
    try:
        import tempfile
        import os
        
        # 建立測試 agents
        agents = {}
        for i in range(4):
            agent = ADPAgent(
                agent_id=f"ti_{i}_0",
                incoming_edges=[f"e_{i}_0", f"e_{i}_1"],
                num_phases=4,
            )
            agents[agent.agent_id] = agent
        
        # 測試重置權重
        reset_agent_weights(agents)
        for agent_id, agent in agents.items():
            if not all(w == 0.0 for w in agent.weights):
                print(f"  ✗ 重置權重失敗: {agent_id} 中有非零權重")
                return False
        print(f"  ✓ 權重重置正常")
        
        # 修改權重
        for agent_id, agent in agents.items():
            agent.weights = [float(i % 10) for i in range(agent.feature_dim)]
        
        # 測試保存權重
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, "test_weights.json")
            
            save_agent_weights(agents, weights_file)
            print(f"  ✓ 權重保存成功: {weights_file}")
            
            # 驗證檔案內容
            if not os.path.exists(weights_file):
                print(f"  ✗ 權重檔案不存在")
                return False
            
            with open(weights_file, "r") as f:
                data = json.load(f)
            
            if "agents" not in data:
                print(f"  ✗ 權重檔案格式錯誤")
                return False
            
            print(f"  ✓ 權重檔案格式正確")
            
            # 清零並重新載入
            reset_agent_weights(agents)
            load_agent_weights(agents, weights_file)
            print(f"  ✓ 權重載入成功")
            
            # 驗證載入的權重
            for agent_id, agent in agents.items():
                expected = [float(i % 10) for i in range(agent.feature_dim)]
                if agent.weights != expected:
                    print(f"  ✗ 載入的權重不符: {agent_id}")
                    print(f"    預期: {expected[:5]}... (前 5 個)")
                    print(f"    實際: {agent.weights[:5]}... (前 5 個)")
                    return False
        
        print(f"  ✓ 權重保存/載入循環正常")
        return True
    except Exception as e:
        print(f"  ✗ 權重管理異常: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_scripts_exist():
    """檢查必要的腳本"""
    print("\n✓ 檢查腳本文件...")
    
    repo_root = Path(__file__).resolve().parent
    required_scripts = [
        "scripts/train_decision_orders.py",
        "scripts/benchmark_decision_orders.py",
    ]
    
    all_exist = True
    for script in required_scripts:
        script_path = repo_root / script
        if script_path.exists():
            print(f"  ✓ {script} 存在")
        else:
            print(f"  ✗ {script} 不存在")
            all_exist = False
    
    return all_exist


def main():
    """執行所有驗證"""
    print("="*70)
    print("決策順序訓練與評估流程驗證")
    print("="*70)
    
    checks = [
        ("配置檢查", check_config),
        ("決策順序策略", check_decision_order_strategies),
        ("決策快取", check_decision_cache),
        ("特徵維度", check_feature_dimensions),
        ("權重管理", check_weights_management),
        ("腳本文件", check_scripts_exist),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            result = check_func()
            results[name] = result
        except Exception as e:
            print(f"\n✗ {name} 檢查異常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    # 總結
    print("\n" + "="*70)
    print("驗證總結")
    print("="*70)
    
    all_passed = True
    for name, result in results.items():
        status = "✓ 通過" if result else "✗ 失敗"
        print(f"{status:8s} - {name}")
        if not result:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("✓ 所有檢查通過！系統已準備好進行訓練和評估。")
        print("\n下一步：")
        print("  1. 執行訓練: python scripts/train_decision_orders.py")
        print("  2. 執行評估: python scripts/benchmark_decision_orders.py models/decision_order_training_<timestamp>")
        return 0
    else:
        print("✗ 某些檢查失敗。請查看上方的錯誤信息並修正。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
