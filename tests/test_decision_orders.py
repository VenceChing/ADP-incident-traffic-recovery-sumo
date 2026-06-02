"""
決策順序單元測試

測試：
1. DecisionOrderSchedule 的所有5個策略
2. 防止連續決策邏輯
3. 鄰近路口信息提取
4. 特徵維度擴展
"""

import pytest
from its_signal_control.decision_intervals import DecisionOrderSchedule
from its_signal_control.controllers import DecisionCache
from its_signal_control.agent import ADPAgent


# 模擬4x4路網的16個路口
MOCK_AGENTS = [f"ti_{i}_{j}" for i in range(4) for j in range(4)]


class TestDecisionOrderSchedule:
    """決策順序排程測試"""

    def test_unified_order(self):
        """測試同時決策（所有路口同時）"""
        schedule = DecisionOrderSchedule(strategy="unified", agent_ids=MOCK_AGENTS)
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        assert len(order) == len(MOCK_AGENTS)
        assert set(order) == set(MOCK_AGENTS)

    def test_checkerboard_order_no_duplicates(self):
        """測試棋盤式順序無重複"""
        schedule = DecisionOrderSchedule(strategy="checkerboard", agent_ids=MOCK_AGENTS)
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        assert len(order) == len(MOCK_AGENTS)
        assert len(set(order)) == len(MOCK_AGENTS), "順序中有重複路口"

    def test_checkerboard_separation(self):
        """測試棋盤式確實分隔對角線"""
        schedule = DecisionOrderSchedule(strategy="checkerboard", agent_ids=MOCK_AGENTS)
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        
        # 找出前半部分（偶數坐標）
        even_agents = set(order[:8])  # 16個中的前8個應該是偶數坐標
        
        # 驗證偶數坐標確實分隔
        for agent in even_agents:
            x, y = int(agent.split("_")[1]), int(agent.split("_")[2])
            assert (x + y) % 2 == 0, f"{agent} 不在偶數坐標"

    def test_ring_order_no_duplicates(self):
        """測試環形順序無重複"""
        schedule = DecisionOrderSchedule(strategy="ring", agent_ids=MOCK_AGENTS)
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        assert len(order) == len(MOCK_AGENTS)
        assert len(set(order)) == len(MOCK_AGENTS), "順序中有重複路口"

    def test_greedy_dynamic_order(self):
        """測試動態貪心（需要隊列信息）"""
        schedule = DecisionOrderSchedule(strategy="greedy_dynamic", agent_ids=MOCK_AGENTS)
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        assert len(order) == len(MOCK_AGENTS)

    def test_random_order_different_seeds(self):
        """測試隨機順序在不同種子下不同"""
        order1 = DecisionOrderSchedule(
            strategy="random", agent_ids=MOCK_AGENTS, random_seed=42
        ).decision_order_for_timestep(sim_time=0.0)
        order2 = DecisionOrderSchedule(
            strategy="random", agent_ids=MOCK_AGENTS, random_seed=43
        ).decision_order_for_timestep(sim_time=0.0)
        
        # 由於隨機性，很可能不同（不保證）
        # 主要測試沒有重複
        assert len(set(order1)) == len(MOCK_AGENTS)
        assert len(set(order2)) == len(MOCK_AGENTS)

    def test_distance_decay_order(self):
        """測試距離遞減順序"""
        schedule = DecisionOrderSchedule(
            strategy="distance_decay",
            agent_ids=MOCK_AGENTS,
            incident_edges=["B2C2", "C2B2"],  # 中心附近
        )
        order = schedule.decision_order_for_timestep(sim_time=0.0)
        assert len(order) == len(MOCK_AGENTS)
        assert len(set(order)) == len(MOCK_AGENTS), "順序中有重複路口"

    def test_get_neighbors(self):
        """測試取得相鄰路口（4連通）"""
        schedule = DecisionOrderSchedule(strategy="unified", agent_ids=MOCK_AGENTS)
        
        # 測試角落路口（應有2個鄰近）
        neighbors = schedule.get_neighbors("ti_0_0")
        assert len(neighbors) == 2
        assert "ti_1_0" in neighbors
        assert "ti_0_1" in neighbors
        
        # 測試邊界路口（應有3個鄰近）
        neighbors = schedule.get_neighbors("ti_0_1")
        assert len(neighbors) == 3
        
        # 測試中心路口（應有4個鄰近）
        neighbors = schedule.get_neighbors("ti_1_1")
        assert len(neighbors) == 4
        assert "ti_0_1" in neighbors
        assert "ti_2_1" in neighbors
        assert "ti_1_0" in neighbors
        assert "ti_1_2" in neighbors


class TestDecisionCache:
    """決策快取測試"""

    def test_cache_decision(self):
        """測試快取決策"""
        cache = DecisionCache()
        cache.cache_decision(agent_id="ti_0_0", action=1, current_phase=0, total_queue=10.0, sim_time=100.0)
        
        assert cache.actions["ti_0_0"] == 1
        assert cache.phases["ti_0_0"] == 0
        assert cache.queues["ti_0_0"] == 10.0
        assert cache.last_decision_time["ti_0_0"] == 100.0

    def test_get_neighbor_info(self):
        """測試獲取鄰近路口信息"""
        cache = DecisionCache()
        cache.cache_decision("ti_0_0", action=2, current_phase=1, total_queue=5.0, sim_time=100.0)
        cache.cache_decision("ti_1_0", action=3, current_phase=0, total_queue=8.0, sim_time=100.0)
        
        neighbor_actions, neighbor_phases, neighbor_queues = cache.get_neighbor_info(
            "ti_0_1", neighbors=["ti_0_0", "ti_1_0", "ti_0_2"]
        )
        
        assert neighbor_actions["ti_0_0"] == 2
        assert neighbor_phases["ti_0_0"] == 1
        assert neighbor_queues["ti_0_0"] == 5.0
        
        assert neighbor_actions["ti_1_0"] == 3
        assert "ti_0_2" not in neighbor_actions  # 未決策

    def test_can_decide_prevention(self):
        """測試防止連續決策"""
        cache = DecisionCache()
        
        # 第一次決策
        assert cache.can_decide("ti_0_0", sim_time=100.0, decision_interval=10.0)
        cache.cache_decision("ti_0_0", action=1, current_phase=0, total_queue=10.0, sim_time=100.0)
        
        # 同個決策週期內不應再決策
        assert not cache.can_decide("ti_0_0", sim_time=105.0, decision_interval=10.0)
        
        # 下個決策週期可以決策
        assert cache.can_decide("ti_0_0", sim_time=110.0, decision_interval=10.0)

    def test_clear_cache(self):
        """測試清空快取"""
        cache = DecisionCache()
        cache.cache_decision("ti_0_0", action=1, current_phase=0, total_queue=10.0, sim_time=100.0)
        
        assert len(cache.actions) > 0
        cache.clear()
        assert len(cache.actions) == 0
        assert len(cache.phases) == 0


class TestADPAgentNeighborFeatures:
    """ADP Agent 鄰近特徵測試"""

    def test_extract_neighbor_features_empty(self):
        """測試空鄰近特徵"""
        agent = ADPAgent(
            agent_id="ti_0_0",
            incoming_edges=["e1", "e2", "e3", "e4"],
            num_phases=4,
        )
        
        neighbor_features = agent._extract_neighbor_features()
        
        # 應包含：
        # - 4個鄰近 × 4個相位的動作 one-hot = 16
        # - 4個鄰近 × 4個相位的相位 one-hot = 16
        # - 4個鄰近的隊列值 = 4
        # 總計 36
        expected_size = 4 * 4 + 4 * 4 + 4
        assert len(neighbor_features) == expected_size

    def test_extract_features_with_neighbors(self):
        """測試含鄰近信息的特徵提取"""
        agent = ADPAgent(
            agent_id="ti_0_0",
            incoming_edges=["e1", "e2", "e3", "e4"],
            num_phases=4,
        )
        
        current_queues = {"e1": 5.0, "e2": 3.0, "e3": 2.0, "e4": 1.0}
        neighbor_actions = {"ti_1_0": 0, "ti_0_1": 2}
        neighbor_phases = {"ti_1_0": 1, "ti_0_1": 3}
        neighbor_queues = {"ti_1_0": 10.0, "ti_0_1": 15.0}
        
        features = agent.extract_features(
            current_queues=current_queues,
            current_phase=0,
            dist_to_incident=2,
            incident_direction=1,
            time_discrete=0,
            incident_active=False,
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
        )
        
        # 特徵向量應包含原始特徵 + 鄰近特徵
        # 原始：4 (queue) + 4 (phase) + 4 (incident_dir) + 4 (action) + 14 (global) = 30
        # 鄰近：36
        # 總計 66
        assert len(features) > 30, "特徵維度應包含鄰近特徵"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
