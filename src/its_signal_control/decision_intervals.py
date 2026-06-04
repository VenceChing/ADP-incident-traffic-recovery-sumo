from __future__ import annotations

import math
import random


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
    """Deterministic per-cycle ordering for decentralized signal decisions."""

    VALID_STRATEGIES = {
        "unified",
        "distance_decay",
        "incident_manhattan_distance_decay",
        "incident_manhattan_distance_premium",
        "checkerboard",
        "ring",
        "greedy_dynamic",
        "queue_length_decay",
        "queue_length_premium",
        "random",
    }

    def __init__(
        self,
        *,
        strategy: str = "unified",
        agent_ids: list[str] | None = None,
        incident_edges: list[str] | None = None,
        random_seed: int = 42,
        agent_positions: dict[str, tuple[float, float]] | None = None,
        neighbor_map: dict[str, list[str]] | None = None,
    ) -> None:
        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(
                f"Unknown decision order strategy {strategy!r}; "
                f"expected one of {sorted(self.VALID_STRATEGIES)}."
            )
        self.strategy = strategy
        self.agent_ids = list(agent_ids or [])
        self.incident_edges = list(incident_edges or [])
        self.random_seed = random_seed
        self.agent_positions = dict(agent_positions or {})
        self.neighbor_map = {agent_id: list(neighbors) for agent_id, neighbors in (neighbor_map or {}).items()}
        self._position_coords = self._build_position_coords()
        self._static_order = self._build_static_order()

    def _build_position_coords(self) -> dict[str, tuple[int, int]]:
        if not self.agent_positions:
            return {}
        xs = sorted({position[0] for position in self.agent_positions.values()})
        ys = sorted({position[1] for position in self.agent_positions.values()})
        x_rank = {value: index for index, value in enumerate(xs)}
        y_rank = {value: index for index, value in enumerate(ys)}
        return {
            agent_id: (x_rank[position[0]], y_rank[position[1]])
            for agent_id, position in self.agent_positions.items()
        }

    def _build_static_order(self) -> list[str]:
        if self.strategy in {"unified", "greedy_dynamic", "queue_length_decay", "queue_length_premium"}:
            return list(self.agent_ids)
        if self.strategy in {"distance_decay", "incident_manhattan_distance_decay"}:
            return self._incident_manhattan_order(farthest_first=True)
        if self.strategy == "incident_manhattan_distance_premium":
            return self._incident_manhattan_order(farthest_first=False)
        if self.strategy == "checkerboard":
            return self._checkerboard_order()
        if self.strategy == "ring":
            return self._ring_order()
        if self.strategy == "random":
            return self._random_order()
        return list(self.agent_ids)

    def decision_order_for_timestep(
        self,
        sim_time: float,
        current_queues: dict[str, dict[str, float] | float] | None = None,
    ) -> list[str]:
        if self.strategy == "greedy_dynamic" and current_queues is not None:
            return self._greedy_dynamic_order(current_queues)
        if self.strategy == "queue_length_decay" and current_queues is not None:
            return self._queue_length_order(current_queues, longest_first=False)
        if self.strategy == "queue_length_premium" and current_queues is not None:
            return self._queue_length_order(current_queues, longest_first=True)
        return list(self._static_order)

    def _agent_coords(self, agent_id: str) -> tuple[int, int] | None:
        if agent_id in self._position_coords:
            return self._position_coords[agent_id]

        if len(agent_id) >= 2 and agent_id[0].isalpha() and agent_id[1:].isdigit():
            return ord(agent_id[0].upper()) - ord("A"), int(agent_id[1:])

        parts = agent_id.split("_")
        if len(parts) >= 3:
            try:
                return int(parts[-2]), int(parts[-1])
            except ValueError:
                return None
        return None

    def _edge_endpoints(self, edge_id: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if len(edge_id) != 4:
            return None
        from_node = edge_id[:2]
        to_node = edge_id[2:]
        from_coords = self._agent_coords(from_node)
        to_coords = self._agent_coords(to_node)
        if from_coords is None or to_coords is None:
            return None
        return from_coords, to_coords

    def _distance_to_incident(self, agent_id: str) -> float:
        if agent_id in self.agent_positions and self.incident_edges:
            x, y = self.agent_positions[agent_id]
            distances: list[float] = []
            for edge_id in self.incident_edges:
                endpoints = self._edge_endpoints(edge_id)
                if endpoints is None:
                    continue
                for ex, ey in endpoints:
                    distances.append(abs(x - ex) + abs(y - ey))
            if distances:
                return min(distances)

        coords = self._agent_coords(agent_id)
        if coords is None or not self.incident_edges:
            return 0.0
        x, y = coords
        distances: list[int] = []
        for edge_id in self.incident_edges:
            endpoints = self._edge_endpoints(edge_id)
            if endpoints is None:
                continue
            for ex, ey in endpoints:
                distances.append(abs(x - ex) + abs(y - ey))
        return min(distances) if distances else 0.0

    def _incident_manhattan_order(self, *, farthest_first: bool) -> list[str]:
        indexed_agents = list(enumerate(self.agent_ids))
        return [
            agent_id
            for _, agent_id in sorted(
                indexed_agents,
                key=lambda item: (
                    -self._distance_to_incident(item[1])
                    if farthest_first
                    else self._distance_to_incident(item[1]),
                    item[0],
                ),
            )
        ]

    def _checkerboard_order(self) -> list[str]:
        indexed_agents = list(enumerate(self.agent_ids))

        def key(item: tuple[int, str]) -> tuple[int, int, int, int]:
            index, agent_id = item
            coords = self._agent_coords(agent_id)
            if coords is None:
                return (2, 0, 0, index)
            x, y = coords
            return ((x + y) % 2, x, y, index)

        return [agent_id for _, agent_id in sorted(indexed_agents, key=key)]

    def _ring_order(self) -> list[str]:
        coords_by_agent = {
            agent_id: coords
            for agent_id in self.agent_ids
            if (coords := self._agent_coords(agent_id)) is not None
        }
        if not coords_by_agent:
            return list(self.agent_ids)

        xs = [coords[0] for coords in coords_by_agent.values()]
        ys = [coords[1] for coords in coords_by_agent.values()]
        center_x = (min(xs) + max(xs)) / 2.0
        center_y = (min(ys) + max(ys)) / 2.0
        original_index = {agent_id: index for index, agent_id in enumerate(self.agent_ids)}

        def key(agent_id: str) -> tuple[float, float, int]:
            x, y = coords_by_agent[agent_id]
            ring = max(abs(x - center_x), abs(y - center_y))
            angle = math.atan2(y - center_y, x - center_x)
            return (-ring, angle, original_index[agent_id])

        ordered_known = sorted(coords_by_agent, key=key)
        unknown = [agent_id for agent_id in self.agent_ids if agent_id not in coords_by_agent]
        return ordered_known + unknown

    def _random_order(self) -> list[str]:
        order = list(self.agent_ids)
        random.Random(self.random_seed).shuffle(order)
        return order

    def _greedy_dynamic_order(
        self,
        current_queues: dict[str, dict[str, float] | float],
    ) -> list[str]:
        return self._queue_length_order(current_queues, longest_first=True)

    def _queue_length_order(
        self,
        current_queues: dict[str, dict[str, float] | float],
        *,
        longest_first: bool,
    ) -> list[str]:
        original_index = {agent_id: index for index, agent_id in enumerate(self.agent_ids)}

        def total_queue(agent_id: str) -> float:
            value = current_queues.get(agent_id, 0.0)
            if isinstance(value, dict):
                return sum(float(queue) for queue in value.values())
            return float(value)

        return sorted(
            self.agent_ids,
            key=lambda agent_id: (
                -total_queue(agent_id) if longest_first else total_queue(agent_id),
                original_index[agent_id],
            ),
        )

    def get_neighbors(self, agent_id: str) -> list[str]:
        """Return 4-connected neighboring agents in stable spatial slot order."""
        if self.neighbor_map:
            return list(self.neighbor_map.get(agent_id, []))

        coords = self._agent_coords(agent_id)
        if coords is None:
            return []

        x, y = coords
        neighbors: list[str] = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            candidate_coords = (x + dx, y + dy)
            for candidate_id in self.agent_ids:
                if self._agent_coords(candidate_id) == candidate_coords:
                    neighbors.append(candidate_id)
                    break
        return neighbors
