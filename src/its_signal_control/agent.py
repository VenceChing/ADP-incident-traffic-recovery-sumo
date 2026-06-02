from typing import Any, Dict
import math
import random


class ADPAgent:
    def __init__(
        self,
        agent_id: str,
        incoming_edges: list,
        action_edges: list[list[str]] | None = None,
        decision_interval: float = 10.0,
        traffic_rate: float = 1500.0,
        num_phases: int = 4,
        switch_penalty: float = 0.0,
        gridlock_penalty: float = 20.0,
        queue_priority_weight: float = 0.5,
        total_queue_weight: float = 0.05,
        queue_scale: float = 50.0,
        distance_scale: float = 6.0,
        time_scale: float = 120.0,
        feature_clip: float = 5.0,
        max_abs_weight: float = 50.0,
        max_abs_td_error: float = 20.0,
        spillback_occupancy_threshold: float = 0.85,
        unbounded_downstream_capacity: float = 1.0e6,
        model_ewma_alpha: float = 0.05,
        min_model_observations: int = 3,
    ) -> None:
        self.agent_id = agent_id
        self.incoming_edges = incoming_edges
        self.decision_interval = decision_interval
        self.traffic_rate = traffic_rate
        self.action_edges = action_edges or [
            [incoming_edges[action]] if action < len(incoming_edges) else []
            for action in range(num_phases)
        ]
        self.num_phases = num_phases
        self.switch_penalty = switch_penalty
        self.gridlock_penalty = gridlock_penalty
        self.global_action_feature_count = 14
        self.feature_dim = len(incoming_edges) + num_phases + num_phases + num_phases + self.global_action_feature_count
        self.weights = [0.0] * self.feature_dim
        self.queue_scale = queue_scale
        self.distance_scale = distance_scale
        self.time_scale = time_scale
        self.feature_clip = feature_clip
        self.max_abs_weight = max_abs_weight
        self.max_abs_td_error = max_abs_td_error
        self.queue_priority_weight = queue_priority_weight
        self.total_queue_weight = total_queue_weight
        self.spillback_occupancy_threshold = spillback_occupancy_threshold
        self.unbounded_downstream_capacity = unbounded_downstream_capacity
        self.model_ewma_alpha = model_ewma_alpha
        self.min_model_observations = min_model_observations
        self.green_discharge_ewma: dict[str, float] = {}
        self.red_arrival_ewma: dict[str, float] = {}
        self.green_observations: dict[str, int] = {}
        self.red_observations: dict[str, int] = {}

    def _clip_feature(self, value: float, lower: float | None = None, upper: float | None = None) -> float:
        if not math.isfinite(value):
            return 0.0
        low = -self.feature_clip if lower is None else lower
        high = self.feature_clip if upper is None else upper
        return max(low, min(high, value))

    def _normalized_queue(self, value: float) -> float:
        return self._clip_feature(value / self.queue_scale, lower=0.0)

    def _default_green_discharge(self) -> float:
        interval_scale = max(1.0, self.decision_interval / 10.0)
        return 3.0 * interval_scale

    def _default_red_arrival(self) -> float:
        interval_scale = max(1.0, self.decision_interval / 10.0)
        demand_scale = max(0.1, self.traffic_rate / 1500.0)
        return 1.0 * interval_scale * demand_scale

    def _green_discharge_for_edge(self, edge_id: str) -> float:
        if self.green_observations.get(edge_id, 0) >= self.min_model_observations:
            return self.green_discharge_ewma.get(edge_id, self._default_green_discharge())
        return self._default_green_discharge()

    def _red_arrival_for_edge(self, edge_id: str) -> float:
        if self.red_observations.get(edge_id, 0) >= self.min_model_observations:
            return self.red_arrival_ewma.get(edge_id, self._default_red_arrival())
        return self._default_red_arrival()

    def reset_learning(self) -> None:
        self.weights = [0.0] * self.feature_dim
        self.green_discharge_ewma = {}
        self.red_arrival_ewma = {}
        self.green_observations = {}
        self.red_observations = {}

    def export_transition_model(self) -> dict[str, Any]:
        return {
            "green_discharge_ewma": self.green_discharge_ewma,
            "red_arrival_ewma": self.red_arrival_ewma,
            "green_observations": self.green_observations,
            "red_observations": self.red_observations,
        }

    def import_transition_model(self, data: dict[str, Any]) -> None:
        self.green_discharge_ewma = {
            str(edge_id): float(value)
            for edge_id, value in data.get("green_discharge_ewma", {}).items()
            if math.isfinite(float(value))
        }
        self.red_arrival_ewma = {
            str(edge_id): float(value)
            for edge_id, value in data.get("red_arrival_ewma", {}).items()
            if math.isfinite(float(value))
        }
        self.green_observations = {
            str(edge_id): int(value)
            for edge_id, value in data.get("green_observations", {}).items()
        }
        self.red_observations = {
            str(edge_id): int(value)
            for edge_id, value in data.get("red_observations", {}).items()
        }

    def calculate_reward(
        self,
        current_queues: Dict[str, float],
        baseline_queues: Dict[str, float],
        tau: float,
        current_phase: int,
        action: int,
        is_gridlock: bool,
        incident_edges: list[str] | None = None,
    ) -> float:
        incident_edge_set = set(incident_edges or [])
        total_queue = sum(
            current_queue
            for edge_id, current_queue in current_queues.items()
            if edge_id not in incident_edge_set
        )
        local_sum = self.total_queue_weight * total_queue / self.queue_scale
        for edge_id, current_queue in current_queues.items():
            if edge_id in incident_edge_set:
                continue
            threshold = tau * baseline_queues.get(edge_id, 0.0)
            local_sum += max(0.0, current_queue - threshold) / self.queue_scale
        local_penalty = -local_sum

        switch_penalty = self.switch_penalty if action != current_phase else 0.0
        normalized_gridlock_pressure = total_queue / max(1.0, self.queue_scale)
        global_penalty = (
            min(self.gridlock_penalty, 5.0 + normalized_gridlock_pressure)
            if is_gridlock
            else 0.0
        )

        return local_penalty - switch_penalty - global_penalty

    def extract_features(
        self,
        current_queues: Dict[str, float],
        current_phase: int,
        dist_to_incident: float,
        incident_direction: int | None,
        time_discrete: int,
        incident_active: bool,
        action: int | None = None,
        action_pressures: list[float] | None = None,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
    ) -> list[float]:
        queue_features = [
            self._normalized_queue(current_queues.get(edge_id, 0.0))
            for edge_id in self.incoming_edges
        ]

        phase_features = [0.0] * self.num_phases
        if 0 <= current_phase < self.num_phases:
            phase_features[current_phase] = 1.0

        incident_direction_features = [0.0] * self.num_phases
        if incident_direction is not None and 0 <= incident_direction < self.num_phases:
            incident_direction_features[incident_direction] = 1.0

        action_features = [0.0] * self.num_phases
        selected_action = current_phase if action is None else action
        if 0 <= selected_action < self.num_phases:
            action_features[selected_action] = 1.0

        selected_pressure = (
            action_pressures[selected_action]
            if action_pressures and 0 <= selected_action < len(action_pressures)
            else 0.0
        )
        selected_downstream_queue = (
            downstream_queues[selected_action]
            if downstream_queues and 0 <= selected_action < len(downstream_queues)
            else 0.0
        )
        selected_downstream_capacity = (
            downstream_capacities[selected_action]
            if downstream_capacities and 0 <= selected_action < len(downstream_capacities)
            else self.unbounded_downstream_capacity
        )
        selected_downstream_capacity = max(1.0, selected_downstream_capacity)
        downstream_occupancy = selected_downstream_queue / selected_downstream_capacity
        spillback_risk = max(
            0.0,
            (downstream_occupancy - self.spillback_occupancy_threshold)
            / max(0.01, 1.0 - self.spillback_occupancy_threshold),
        )

        aligned_with_incident = (
            1.0
            if incident_direction is not None and selected_action == incident_direction
            else 0.0
        )
        opposite_incident = (
            1.0
            if incident_direction is not None and selected_action == (incident_direction + 2) % self.num_phases
            else 0.0
        )
        perpendicular_incident = (
            1.0
            if incident_direction is not None
            and selected_action in {
                (incident_direction + 1) % self.num_phases,
                (incident_direction + 3) % self.num_phases,
            }
            else 0.0
        )

        dist_feature = self._clip_feature(float(dist_to_incident) / self.distance_scale, lower=0.0)
        time_feature = self._clip_feature(float(time_discrete) / self.time_scale, lower=0.0)
        global_features = [
            1.0,
            dist_feature,
            time_feature,
            1.0 if incident_active else 0.0,
            1.0 if selected_action != current_phase else 0.0,
            self._clip_feature(selected_pressure / self.queue_scale),
            self._normalized_queue(selected_downstream_queue),
            self._clip_feature(downstream_occupancy, lower=0.0),
            self._clip_feature(spillback_risk, lower=0.0),
            aligned_with_incident,
            opposite_incident,
            perpendicular_incident,
            self._clip_feature(spillback_risk if incident_active else 0.0, lower=0.0),
            self._clip_feature(aligned_with_incident * dist_feature, lower=0.0),
        ]

        # 鄰近路口特徵（可選）
        neighbor_features = self._extract_neighbor_features(neighbor_actions, neighbor_phases, neighbor_queues)

        return (
            queue_features
            + phase_features
            + incident_direction_features
            + action_features
            + global_features
            + neighbor_features
        )

    def _extract_neighbor_features(
        self,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
    ) -> list[float]:
        """提取鄰近路口特徵（one-hot 編碼動作和相位 + 歸一化隊列）"""
        neighbor_actions = neighbor_actions or {}
        neighbor_phases = neighbor_phases or {}
        neighbor_queues = neighbor_queues or {}

        features = []

        # 最多 4 個鄰近路口（4-連通）
        max_neighbors = 4
        for _ in range(max_neighbors):
            # 動作特徵（one-hot）
            for _ in range(self.num_phases):
                features.append(0.0)

        for _ in range(max_neighbors):
            # 相位特徵（one-hot）
            for _ in range(self.num_phases):
                features.append(0.0)

        for _ in range(max_neighbors):
            # 隊列特徵
            features.append(0.0)

        if not neighbor_actions and not neighbor_phases and not neighbor_queues:
            return features

        # 填充實際鄰近資料
        for idx, (nid, action) in enumerate(neighbor_actions.items()):
            if idx >= max_neighbors:
                break
            if 0 <= action < self.num_phases:
                features[idx * self.num_phases + action] = 1.0

        for idx, (nid, phase) in enumerate(neighbor_phases.items()):
            if idx >= max_neighbors:
                break
            offset = max_neighbors * self.num_phases
            if 0 <= phase < self.num_phases:
                features[offset + idx * self.num_phases + phase] = 1.0

        for idx, (nid, queue) in enumerate(neighbor_queues.items()):
            if idx >= max_neighbors:
                break
            offset = max_neighbors * self.num_phases * 2
            features[offset + idx] = self._normalized_queue(queue)

        return features

    def get_value(self, features: list[float]) -> float:
        value = sum(w * x for w, x in zip(self.weights, features))
        return value if math.isfinite(value) else 0.0

    def estimate_state_value(
        self,
        current_queues: Dict[str, float],
        current_phase: int,
        dist_to_incident: float,
        incident_direction: int | None,
        time_discrete: int,
        incident_active: bool,
        action_pressures: list[float] | None = None,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
    ) -> float:
        values = []
        for candidate_action in range(self.num_phases):
            features = self.extract_features(
                current_queues,
                current_phase,
                dist_to_incident,
                incident_direction,
                time_discrete,
                incident_active,
                action=candidate_action,
                action_pressures=action_pressures,
                downstream_queues=downstream_queues,
                downstream_capacities=downstream_capacities,
            )
            values.append(self.get_value(features))
        return max(values) if values else 0.0

    def predict_next_features(
        self,
        current_queues: Dict[str, float],
        action: int,
        current_phase: int,
        dist_to_incident: float,
        incident_direction: int | None,
        time_discrete: int,
        incident_active: bool,
        action_pressures: list[float] | None = None,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
        incident_edges: list[str] | None = None,
    ) -> list[float]:
        next_queues = self.predict_next_queues(
            current_queues,
            action,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
            blocked_edges=incident_edges,
        )
        return self.extract_features(
            next_queues,
            action,
            dist_to_incident,
            incident_direction,
            time_discrete,
            incident_active,
            action=action,
            action_pressures=action_pressures,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
        )

    def select_action(
        self,
        current_queues: Dict[str, float],
        baseline_queues: Dict[str, float],
        tau: float,
        current_phase: int,
        dist_to_incident: float,
        incident_direction: int | None,
        time_discrete: int,
        is_gridlock: bool,
        incident_active: bool,
        epsilon: float,
        gamma: float,
        incident_edges: list[str] | None = None,
        action_pressures: list[float] | None = None,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
    ) -> int:
        if random.random() < epsilon:
            return random.randint(0, self.num_phases - 1)

        q_values = self.estimate_action_values(
            current_queues,
            baseline_queues,
            tau,
            current_phase,
            dist_to_incident,
            incident_direction,
            time_discrete,
            is_gridlock,
            incident_active,
            gamma,
            incident_edges,
            action_pressures,
            downstream_queues,
            downstream_capacities,
        )
        best_action = max(range(self.num_phases), key=lambda action: q_values[action])
        return best_action

    def estimate_action_values(
        self,
        current_queues: Dict[str, float],
        baseline_queues: Dict[str, float],
        tau: float,
        current_phase: int,
        dist_to_incident: float,
        incident_direction: int | None,
        time_discrete: int,
        is_gridlock: bool,
        incident_active: bool,
        gamma: float,
        incident_edges: list[str] | None = None,
        action_pressures: list[float] | None = None,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
    ) -> list[float]:
        q_values = [float("-inf")] * self.num_phases
        best_action = 0
        max_q = float("-inf")
        for action in range(self.num_phases):
            predicted_queues = self.predict_next_queues(
                current_queues,
                action,
                downstream_queues=downstream_queues,
                downstream_capacities=downstream_capacities,
                blocked_edges=incident_edges,
            )
            served_queue = sum(
                current_queues.get(edge_id, 0.0)
                for edge_id in self.action_edges[action]
            )
            reward = self.calculate_reward(
                predicted_queues,
                baseline_queues,
                tau,
                current_phase,
                action,
                is_gridlock,
                incident_edges=incident_edges,
            )
            future_value = self.estimate_state_value(
                predicted_queues,
                action,
                dist_to_incident,
                incident_direction,
                time_discrete,
                incident_active,
                action_pressures,
                downstream_queues,
                downstream_capacities,
            )
            q_value = reward + gamma * future_value
            # problem!!!
            q_value += self.queue_priority_weight * served_queue / self.queue_scale
            if not math.isfinite(q_value):
                continue
            q_values[action] = q_value
            #if getattr(self, "agent_id", "") == "A3":
                #print(f"[📊 Q值成分拆解] 行動 {action} | Reward: {reward:.2f} | Future(AI大腦): {gamma * future_value:.2f} | Greedy(排隊項): {self.queue_priority_weight * served_queue / self.queue_scale:.2f} | 總分: {q_value:.2f}")
            if q_value > max_q:
                max_q = q_value
                best_action = action

        if max_q == float("-inf"):
            q_values = [0.0] * self.num_phases
        return q_values

    def predict_next_queues(
        self,
        current_queues: Dict[str, float],
        action: int,
        downstream_queues: list[float] | None = None,
        downstream_capacities: list[float] | None = None,
        blocked_edges: list[str] | None = None,
    ) -> Dict[str, float]:
        next_queues = dict(current_queues)
        blocked_edge_set = set(blocked_edges or [])
        for blocked_edge in blocked_edge_set:
            if blocked_edge in next_queues:
                next_queues[blocked_edge] = 0.0
        green_edges = set(self.action_edges[action]) if 0 <= action < len(self.action_edges) else set()
        downstream_queue = (
            downstream_queues[action]
            if downstream_queues and 0 <= action < len(downstream_queues)
            else 0.0
        )
        downstream_capacity = (
            downstream_capacities[action]
            if downstream_capacities and 0 <= action < len(downstream_capacities)
            else self.unbounded_downstream_capacity
        )
        free_space = max(0.0, downstream_capacity - downstream_queue)
        per_edge_free_space = free_space / max(1, len(green_edges))
        for green_edge in green_edges:
            if green_edge in blocked_edge_set:
                continue
            green_discharge = min(self._green_discharge_for_edge(green_edge), per_edge_free_space)
            next_queues[green_edge] = max(0.0, next_queues.get(green_edge, 0.0) - green_discharge)
        for edge_id in self.incoming_edges:
            if edge_id in green_edges or edge_id in blocked_edge_set:
                continue
            next_queues[edge_id] = next_queues.get(edge_id, 0.0) + self._red_arrival_for_edge(edge_id)
        return next_queues

    def update_transition_model(
        self,
        current_queues: Dict[str, float],
        next_queues: Dict[str, float],
        action: int,
        blocked_edges: list[str] | None = None,
    ) -> None:
        blocked_edge_set = set(blocked_edges or [])
        green_edges = set(self.action_edges[action]) if 0 <= action < len(self.action_edges) else set()
        for edge_id in self.incoming_edges:
            if edge_id in blocked_edge_set:
                continue
            before = current_queues.get(edge_id, 0.0)
            after = next_queues.get(edge_id, 0.0)
            if edge_id in green_edges:
                observed_discharge = max(0.0, before - after)
                if before <= 0.0 and observed_discharge <= 0.0:
                    continue
                previous = self.green_discharge_ewma.get(edge_id, self._default_green_discharge())
                self.green_discharge_ewma[edge_id] = (
                    (1.0 - self.model_ewma_alpha) * previous
                    + self.model_ewma_alpha * observed_discharge
                )
                self.green_observations[edge_id] = self.green_observations.get(edge_id, 0) + 1
            else:
                observed_arrival = max(0.0, after - before)
                previous = self.red_arrival_ewma.get(edge_id, self._default_red_arrival())
                self.red_arrival_ewma[edge_id] = (
                    (1.0 - self.model_ewma_alpha) * previous
                    + self.model_ewma_alpha * observed_arrival
                )
                self.red_observations[edge_id] = self.red_observations.get(edge_id, 0) + 1

    def update_weights(
        self,
        features: list[float],
        reward: float,
        next_features: list[float],
        alpha: float,
        gamma: float,
    ) -> None:
        current_v = self.get_value(features)
        next_v = self.get_value(next_features)
        td_error = reward + gamma * next_v - current_v
        if not math.isfinite(td_error):
            return
        td_error = max(-self.max_abs_td_error, min(self.max_abs_td_error, td_error))
        for i in range(len(self.weights)):
            feature = features[i]
            if not math.isfinite(feature):
                continue
            self.weights[i] += alpha * td_error * feature
            if not math.isfinite(self.weights[i]):
                self.weights[i] = 0.0
            self.weights[i] = max(-self.max_abs_weight, min(self.max_abs_weight, self.weights[i]))
