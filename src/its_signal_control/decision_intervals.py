from __future__ import annotations

import random
from typing import Any


class DecisionIntervalSchedule:
    def __init__(self, default_interval_seconds: int, per_agent: dict[str, int] | None = None) -> None:
        if default_interval_seconds <= 0:
            raise ValueError("default_interval_seconds must be positive.")
        self.default_interval_seconds = default_interval_seconds
        self.per_agent = per_agent or {}

    def interval_for(self, agent_id: str) -> int:
        interval = self.per_agent.get(agent_id, self.default_interval_seconds)
        if interval <= 0:
            raise ValueError(f"Decision interval for {agent_id} must be positive.")
        return interval

    def should_decide(self, agent_id: str, sim_time: float) -> bool:
        interval = self.interval_for(agent_id)
        return int(sim_time) % interval == 0


class DecisionOrderSchedule:
    """決策順序排程：定義每個決策週期中各路口的決策順序"""

    def __init__(
        self,
        strategy: str = "unified",
        agent_ids: list[str] | None = None,
        incident_edges: list[str] | None = None,
        decision_interval: float = 10.0,
        random_seed: int = 42,
    ) -> None:
        """
        Args:
            strategy: "unified", "distance_decay", "checkerboard", "ring", "greedy_dynamic", "random"
            agent_ids: 所有路口 ID 列表（如 ["ti_0_0", "ti_0_1", ...]）
            incident_edges: 事故邊 ID（用於距離遞減策略）
            decision_interval: 決策週期（秒）
            random_seed: 隨機種子
        """
        self.strategy = strategy
        self.agent_ids = agent_ids or []
        self.incident_edges = incident_edges or []
        self.decision_interval = decision_interval
        self.random_seed = random_seed
        self.order = self._build_order()

    def _build_order(self) -> list[str]:
        """構建決策順序"""
        if self.strategy == "unified":
            return self.agent_ids  # 所有同時決策
        elif self.strategy == "distance_decay":
            return self._distance_decay_order()
        elif self.strategy == "checkerboard":
            return self._checkerboard_order()
        elif self.strategy == "ring":
            return self._ring_order()
        elif self.strategy == "greedy_dynamic":
            return self.agent_ids  # 動態順序，每步重新計算
        elif self.strategy == "random":
            return self._random_order()
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def _parse_agent_coords(self, agent_id: str) -> tuple[int, int] | None:
        """從 agent_id 解析座標（如 "ti_0_1" -> (0, 1)）"""
        try:
            parts = agent_id.split("_")
            if len(parts) >= 3:
                return int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            pass
        return None

    def _distance_decay_order(self) -> list[str]:
        """距離遞減：距離事故最遠的路口優先決策"""
        if not self.incident_edges:
            return self.agent_ids

        def distance_to_incident(agent_id: str) -> int:
            """計算到事故的曼哈頓距離"""
            coords = self._parse_agent_coords(agent_id)
            if coords is None:
                return 0
            x, y = coords
            min_dist = float("inf")
            for edge in self.incident_edges:
                if len(edge) >= 4:
                    try:
                        ex1 = ord(edge[0].upper()) - ord("A")
                        ey1 = int(edge[1])
                        ex2 = ord(edge[2].upper()) - ord("A")
                        ey2 = int(edge[3])
                        dist1 = abs(x - ex1) + abs(y - ey1)
                        dist2 = abs(x - ex2) + abs(y - ey2)
                        min_dist = min(min_dist, dist1, dist2)
                    except (ValueError, IndexError):
                        pass
            return min_dist if min_dist != float("inf") else 0

        # 降序排列（距離遠的優先）
        return sorted(self.agent_ids, key=distance_to_incident, reverse=True)

    def _checkerboard_order(self) -> list[str]:
        """棋盤式：對角線不相鄰，偶數行列優先"""
        even = []
        odd = []
        for agent_id in sorted(self.agent_ids):
            coords = self._parse_agent_coords(agent_id)
            if coords is not None:
                x, y = coords
                if (x + y) % 2 == 0:
                    even.append(agent_id)
                else:
                    odd.append(agent_id)
        return even + odd

    def _ring_order(self) -> list[str]:
        """環形：外向內螺旋排列"""
        coords_map = {}
        for agent_id in self.agent_ids:
            coords = self._parse_agent_coords(agent_id)
            if coords is not None:
                coords_map[agent_id] = coords

        if not coords_map:
            return self.agent_ids

        # 計算螺旋距離
        def spiral_distance(coords: tuple[int, int]) -> tuple[int, int, int]:
            x, y = coords
            max_coord = max(x, y)
            ring = max_coord
            if x == max_coord:  # 右邊
                pos = y
            elif y == 0:  # 下邊
                pos = 2 * max_coord - x
            elif x == 0:  # 左邊
                pos = 2 * max_coord + max_coord - y
            else:  # 上邊
                pos = 4 * max_coord - x
            return (ring, pos, x + y)

        return sorted(coords_map.keys(), key=lambda aid: spiral_distance(coords_map[aid]))

    def _random_order(self) -> list[str]:
        """隨機順序"""
        order = list(self.agent_ids)
        random.Random(self.random_seed).shuffle(order)
        return order

    def decision_order_for_timestep(
        self, sim_time: float, current_queues: dict[str, dict[str, float]] | None = None
    ) -> list[str]:
        """獲取某時間點的決策順序"""
        if self.strategy == "greedy_dynamic" and current_queues:
            return self._greedy_dynamic_order(current_queues)
        return self.order

    def _greedy_dynamic_order(self, current_queues: dict[str, dict[str, float]]) -> list[str]:
        """動態貪心：根據隊列長度排序（隊列越長優先決策）"""

        def total_queue(agent_id: str) -> float:
            return sum(current_queues.get(agent_id, {}).values())

        return sorted(self.agent_ids, key=total_queue, reverse=True)

    def get_neighbors(self, agent_id: str) -> list[str]:
        """獲取某路口的相鄰路口（4連通）"""
        coords = self._parse_agent_coords(agent_id)
        if coords is None:
            return []

        x, y = coords
        neighbors = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            neighbor_id = f"ti_{nx}_{ny}"
            if neighbor_id in self.agent_ids:
                neighbors.append(neighbor_id)
        return neighbors
