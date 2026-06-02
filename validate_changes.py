#!/usr/bin/env python3
"""驗證代碼修改的有效性"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

def validate_imports():
    """驗證所有導入正常"""
    print("檢查導入...")
    try:
        from its_signal_control.decision_intervals import DecisionOrderSchedule, DecisionIntervalSchedule
        print("✓ decision_intervals")
    except Exception as e:
        print(f"✗ decision_intervals: {e}")
        return False

    try:
        from its_signal_control.controllers import DecisionCache
        print("✓ controllers (DecisionCache)")
    except Exception as e:
        print(f"✗ controllers: {e}")
        return False

    try:
        from its_signal_control.agent import ADPAgent
        print("✓ agent")
    except Exception as e:
        print(f"✗ agent: {e}")
        return False

    try:
        from its_signal_control.features import NeighborFeatureConfig, extract_neighbor_features
        print("✓ features")
    except Exception as e:
        print(f"✗ features: {e}")
        return False

    try:
        from its_signal_control.experiment import run_episode
        print("✓ experiment")
    except Exception as e:
        print(f"✗ experiment: {e}")
        return False

    return True


def validate_decision_order_schedule():
    """驗證決策順序排程"""
    print("\n檢查 DecisionOrderSchedule 功能...")
    from its_signal_control.decision_intervals import DecisionOrderSchedule

    agents = [f"ti_{i}_{j}" for i in range(4) for j in range(4)]

    # 測試所有5個策略
    strategies = ["unified", "distance_decay", "checkerboard", "ring", "greedy_dynamic", "random"]
    for strategy in strategies:
        try:
            schedule = DecisionOrderSchedule(
                strategy=strategy,
                agent_ids=agents,
                incident_edges=["B2C2", "C2B2"],
            )
            order = schedule.decision_order_for_timestep(0.0)
            
            # 驗證無重複
            if len(order) != len(set(order)):
                print(f"✗ {strategy}: 順序中有重複")
                return False
            
            # 驗證所有路口都有
            if set(order) != set(agents):
                print(f"✗ {strategy}: 缺少某些路口")
                return False
            
            print(f"✓ {strategy}")
        except Exception as e:
            print(f"✗ {strategy}: {e}")
            return False

    return True


def validate_decision_cache():
    """驗證決策快取"""
    print("\n檢查 DecisionCache 功能...")
    from its_signal_control.controllers import DecisionCache

    cache = DecisionCache()
    
    try:
        # 測試快取決策
        cache.cache_decision("ti_0_0", action=1, current_phase=0, total_queue=10.0, sim_time=100.0)
        assert cache.actions["ti_0_0"] == 1
        print("✓ 快取決策")

        # 測試鄰近信息
        neighbor_actions, _, _ = cache.get_neighbor_info("ti_0_1", ["ti_0_0", "ti_1_1"])
        assert neighbor_actions.get("ti_0_0") == 1
        print("✓ 獲取鄰近信息")

        # 測試防止連續決策
        assert not cache.can_decide("ti_0_0", sim_time=105.0, decision_interval=10.0)
        print("✓ 防止連續決策")

        # 測試清空快取
        cache.clear()
        assert len(cache.actions) == 0
        print("✓ 清空快取")

        return True
    except Exception as e:
        print(f"✗ DecisionCache: {e}")
        return False


def validate_agent_neighbor_features():
    """驗證 agent 鄰近特徵"""
    print("\n檢查 ADPAgent 鄰近特徵...")
    from its_signal_control.agent import ADPAgent

    try:
        agent = ADPAgent(
            agent_id="ti_0_0",
            incoming_edges=["e1", "e2", "e3", "e4"],
            num_phases=4,
        )
        
        # 測試空鄰近特徵
        neighbor_features = agent._extract_neighbor_features()
        expected_size = 4 * 4 + 4 * 4 + 4  # 36
        assert len(neighbor_features) == expected_size
        print(f"✓ 空鄰近特徵 (大小: {len(neighbor_features)})")

        # 測試含鄰近信息的特徵
        current_queues = {"e1": 5.0, "e2": 3.0, "e3": 2.0, "e4": 1.0}
        features = agent.extract_features(
            current_queues=current_queues,
            current_phase=0,
            dist_to_incident=2,
            incident_direction=1,
            time_discrete=0,
            incident_active=False,
            neighbor_actions={"ti_1_0": 1},
            neighbor_phases={"ti_1_0": 2},
            neighbor_queues={"ti_1_0": 10.0},
        )
        assert len(features) > 30
        print(f"✓ 含鄰近信息的特徵 (大小: {len(features)})")

        return True
    except Exception as e:
        print(f"✗ ADPAgent 鄰近特徵: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主驗證"""
    print("="*70)
    print("驗證決策順序代碼修改")
    print("="*70)

    all_ok = True
    
    if not validate_imports():
        all_ok = False
    
    if not validate_decision_order_schedule():
        all_ok = False
    
    if not validate_decision_cache():
        all_ok = False
    
    if not validate_agent_neighbor_features():
        all_ok = False

    print("\n" + "="*70)
    if all_ok:
        print("✓ 所有驗證通過！代碼修改完整有效。")
        return 0
    else:
        print("✗ 有驗證失敗，請檢查上述錯誤。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
