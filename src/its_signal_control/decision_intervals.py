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
    '''
    def _parse_agent_coords(self, agent_id: str) -> tuple[int, int] | None:
        """從 agent_id 解析座標（如 "ti_0_1" -> (0, 1)）"""
        try:
            parts = agent_id.split("_")
            if len(parts) >= 3:
                return int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            pass
        return None
    '''

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
    '''
    def _checkerboard_order(self) -> list[str]:
        """棋盤式：對角線不相鄰，偶數行列優先"""
        print(f"Building checkerboard order for agents: {self.agent_ids}")
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

        print(f"Checkerboard order - even: {even}, odd: {odd}")
        return even + odd
    '''
    def _parse_agent_coords(self, agent_id: str) -> tuple[int, int] | None:
        """
        將類似 'A3', 'B2', 'C0' 的路口 ID 轉換為 (x, y) 網格座標。
        A->0, B->1, C->2, D->3...
        """
        try:
            agent_id = agent_id.strip()
            if len(agent_id) < 2:
                return None
                
            # 1. 處理第一個字元（字母）當作 X 軸：A=0, B=1, C=2...
            x_letter = agent_id[0].upper()
            if not x_letter.isalpha():
                return None
            x = ord(x_letter) - ord('A')
            
            # 2. 處理後面的字元（數字）當作 Y 軸：'3'->3
            y_str = agent_id[1:]
            if not y_str.isdigit():
                return None
            y = int(y_str)
            
            return (x, y)
        except Exception:
            return None

    def _checkerboard_order(self) -> list[str]:
        """棋盤式：對角線不相鄰，偶數行列優先"""
        print(f"\n[棋盤排序] 開始處理 Agent 列表: {self.agent_ids}")
        even = []
        odd = []
        
        for agent_id in sorted(self.agent_ids):
            coords = self._parse_agent_coords(agent_id)
            
            if coords is not None:
                x, y = coords
                # 印出詳細解析過程，方便你對照
                print(f"  -> 路口 {agent_id} 成功解析為座標: ({x}, {y}) | 和為: {x+y}")
                
                if (x + y) % 2 == 0:
                    even.append(agent_id)
                else:
                    odd.append(agent_id)
            else:
                # 如果還是解析失敗，會跳出警告，但不會讓程式崩潰
                print(f"  ⚠️ [警告] 無法解析路口 {agent_id} 的座標，此路口將被跳過！")

        print(f"[棋盤排序結果] - 偶數組(even): {even}, 奇數組(odd): {odd}")
        
        final_order = even + odd
        print(f"[完成] 最終回傳順序: {final_order}\n")
        return final_order

    def _ring_order(self) -> list[str]:
        """環形：外向內螺旋排列 (由最外圈順時針往內包圍)"""
        print(f"[環形排序] 開始建立外向內螺旋順序...")
        
        # 1. 建立座標到 Agent ID 的雙向對照表
        coords_to_id = {}
        for agent_id in self.agent_ids:
            coords = self._parse_agent_coords(agent_id)
            if coords is not None:
                coords_to_id[coords] = agent_id

        if not coords_to_id:
            return self.agent_ids

        # 2. 找出網格邊界 (對於 4x4 來說，min_x=0, max_x=3, min_y=0, max_y=3)
        all_x = [c[0] for c in coords_to_id.keys()]
        all_y = [c[1] for c in coords_to_id.keys()]
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)

        spiral_order = []
        
        # 3. 剝洋蔥演算法 (層層往內繞)
        while min_x <= max_x and min_y <= max_y:
            # 3a. 上邊：從左到右 (固定在最上方的 y)
            for x in range(min_x, max_x + 1):
                if (x, max_y) in coords_to_id and coords_to_id[(x, max_y)] not in spiral_order:
                    spiral_order.append(coords_to_id[(x, max_y)])
            
            # 3b. 右邊：從上到下 (固定在最右邊的 x)
            for y in range(max_y - 1, min_y - 1, -1):
                if (max_x, y) in coords_to_id and coords_to_id[(max_x, y)] not in spiral_order:
                    spiral_order.append(coords_to_id[(max_x, y)])
            
            # 3c. 下邊：從右到左 (固定在最下方的 y)
            for x in range(max_x - 1, min_x - 1, -1):
                if (x, min_y) in coords_to_id and coords_to_id[(x, min_y)] not in spiral_order:
                    spiral_order.append(coords_to_id[(x, min_y)])
            
            # 3d. 左邊：從下到上 (固定在最左邊的 x)
            for y in range(min_y + 1, max_y):
                if (min_x, y) in coords_to_id and coords_to_id[(min_x, y)] not in spiral_order:
                    spiral_order.append(coords_to_id[(min_x, y)])
            
            # 縮小邊界，往內推一圈
            min_x += 1
            max_x -= 1
            min_y += 1
            max_y -= 1

        print(f"[環形排序結果] 最終回傳外向內順序: {spiral_order}")
        return spiral_order

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
        """獲取某路口的相鄰路口（4連通），支援 A0, B1 字母網格格式"""
        coords = self._parse_agent_coords(agent_id)
        if coords is None:
            return []

        x, y = coords
        neighbors = []
        
        # 4連通：左、右、下、上
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            
            # 🚨 關鍵修正：將數字 nx 轉回對應的英文字母 (0->A, 1->B, 2->C...)
            if nx >= 0:
                nx_letter = chr(ord('A') + nx)
                neighbor_id = f"{nx_letter}{ny}"  # 拼出像 'A1', 'B0' 的格式
                
                # 檢查這個鄰居是不是真的存在於路網中
                if neighbor_id in self.agent_ids:
                    neighbors.append(neighbor_id)
                    
        return neighbors
