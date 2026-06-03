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
        action_names: list[str] | None = None,
        action_approaches: list[list[int]] | None = None,
        queue_movements: dict[str, str] | None = None,
        queue_approaches: dict[str, str] | None = None,
        switch_penalty: float = 0.0,
        gridlock_penalty: float = 20.0,
        action_scoring_mode: str = "value",
        feature_set: str = "full",
        queue_priority_weight: float = 0.5,
        total_queue_weight: float = 0.05,
        lane_fairness_weight: float = 0.0,
        lane_fairness_margin: float = 5.0,
        residual_greedy_weight: float = 1.0,
        residual_pressure_weight: float = 0.0,
        residual_value_weight: float = 1.0,
        residual_lookahead_weight: float = 0.0,
        residual_downstream_penalty_weight: float = 0.0,
        lookahead_depth: int = 1,
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
        incident_action_feature_count: int = 0,
        neighbor_feature_max_neighbors: int = 0,
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
        self.direction_count = 4
        self.action_names = action_names or [str(action) for action in range(num_phases)]
        self.action_approaches = action_approaches or [
            [action] if action < self.direction_count else []
            for action in range(num_phases)
        ]
        self.queue_movements = queue_movements or {}
        self.queue_approaches = queue_approaches or {}
        self.switch_penalty = switch_penalty
        self.gridlock_penalty = gridlock_penalty
        self.action_scoring_mode = action_scoring_mode
        self.feature_set = feature_set
        self.global_action_feature_count = 6 if feature_set == "compact_residual" else 14
        self.incident_action_feature_count = max(0, int(incident_action_feature_count))
        self.neighbor_feature_max_neighbors = max(0, int(neighbor_feature_max_neighbors))
        self.neighbor_feature_count = self.neighbor_feature_max_neighbors * (2 * num_phases + 1)
        if feature_set == "compact_residual":
            self.feature_dim = (
                len(incoming_edges)
                + num_phases
                + self.global_action_feature_count
                + self.incident_action_feature_count
                + self.neighbor_feature_count
            )
        else:
            self.feature_dim = (
                len(incoming_edges)
                + num_phases
                + self.direction_count
                + num_phases
                + self.global_action_feature_count
                + self.incident_action_feature_count
                + self.neighbor_feature_count
            )
        self.weights = [0.0] * self.feature_dim
        self.queue_scale = queue_scale
        self.distance_scale = distance_scale
        self.time_scale = time_scale
        self.feature_clip = feature_clip
        self.max_abs_weight = max_abs_weight
        self.max_abs_td_error = max_abs_td_error
        self.queue_priority_weight = queue_priority_weight
        self.total_queue_weight = total_queue_weight
        self.lane_fairness_weight = lane_fairness_weight
        self.lane_fairness_margin = lane_fairness_margin
        self.residual_greedy_weight = residual_greedy_weight
        self.residual_pressure_weight = residual_pressure_weight
        self.residual_value_weight = residual_value_weight
        self.residual_lookahead_weight = residual_lookahead_weight
        self.residual_downstream_penalty_weight = residual_downstream_penalty_weight
        self.lookahead_depth = max(1, int(lookahead_depth))
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
        if self.lane_fairness_weight > 0.0:
            local_penalty -= self.lane_fairness_weight * self._lane_fairness_imbalance(current_queues)

        switch_penalty = self.switch_penalty if action != current_phase else 0.0
        normalized_gridlock_pressure = total_queue / max(1.0, self.queue_scale)
        global_penalty = (
            min(self.gridlock_penalty, 5.0 + normalized_gridlock_pressure)
            if is_gridlock
            else 0.0
        )

        return local_penalty - switch_penalty - global_penalty

    def _lane_fairness_imbalance(self, current_queues: Dict[str, float]) -> float:
        by_approach: dict[str, dict[str, float]] = {}
        for queue_key, queue_value in current_queues.items():
            approach = self.queue_approaches.get(queue_key)
            movement = self.queue_movements.get(queue_key)
            if approach is None or movement not in {"SR", "L", "R", "S"}:
                continue
            movement_totals = by_approach.setdefault(approach, {})
            movement_totals[movement] = movement_totals.get(movement, 0.0) + queue_value

        imbalance = 0.0
        for movement_queues in by_approach.values():
            if {"R", "S"} & set(movement_queues):
                values = [
                    movement_queues.get("R", 0.0),
                    movement_queues.get("S", 0.0),
                    movement_queues.get("L", 0.0),
                ]
                difference = max(values) - min(values)
            else:
                difference = abs(movement_queues.get("SR", 0.0) - movement_queues.get("L", 0.0))
            imbalance += max(0.0, difference - self.lane_fairness_margin)
        return imbalance / self.queue_scale

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
        incident_action_features: list[list[float]] | None = None,
        neighbor_ids: list[str] | None = None,
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

        incident_direction_features = [0.0] * self.direction_count
        if incident_direction is not None and 0 <= incident_direction < self.direction_count:
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

        selected_approaches = (
            self.action_approaches[selected_action]
            if 0 <= selected_action < len(self.action_approaches)
            else []
        )
        aligned_with_incident = (
            1.0
            if incident_direction is not None and incident_direction in selected_approaches
            else 0.0
        )
        opposite_direction = (incident_direction + 2) % self.direction_count if incident_direction is not None else None
        opposite_incident = (
            1.0
            if opposite_direction is not None and opposite_direction in selected_approaches
            else 0.0
        )
        perpendicular_directions = (
            {
                (incident_direction + 1) % self.direction_count,
                (incident_direction + 3) % self.direction_count,
            }
            if incident_direction is not None
            else set()
        )
        perpendicular_incident = (
            1.0
            if perpendicular_directions and any(direction in selected_approaches for direction in perpendicular_directions)
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
        if self.feature_set == "compact_residual":
            global_features = [
                1.0,
                1.0 if incident_active else 0.0,
                1.0 if selected_action != current_phase else 0.0,
                self._clip_feature(selected_pressure / self.queue_scale),
                self._clip_feature(downstream_occupancy, lower=0.0),
                self._clip_feature(spillback_risk, lower=0.0),
            ]
        selected_incident_action_features = [0.0] * self.incident_action_feature_count
        if (
            incident_action_features
            and 0 <= selected_action < len(incident_action_features)
            and self.incident_action_feature_count > 0
        ):
            raw_features = incident_action_features[selected_action]
            selected_incident_action_features = [
                self._clip_feature(float(raw_features[idx]), lower=0.0)
                if idx < len(raw_features)
                else 0.0
                for idx in range(self.incident_action_feature_count)
            ]

        neighbor_features = self._extract_neighbor_features(
            neighbor_ids,
            neighbor_actions,
            neighbor_phases,
            neighbor_queues,
        )

        if self.feature_set == "compact_residual":
            return (
                queue_features
                + action_features
                + global_features
                + selected_incident_action_features
                + neighbor_features
            )

        return (
            queue_features
            + phase_features
            + incident_direction_features
            + action_features
            + global_features
            + selected_incident_action_features
            + neighbor_features
        )

    def _extract_neighbor_features(
        self,
        neighbor_ids: list[str] | None = None,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
    ) -> list[float]:
        if self.neighbor_feature_max_neighbors <= 0:
            return []

        neighbor_actions = neighbor_actions or {}
        neighbor_phases = neighbor_phases or {}
        neighbor_queues = neighbor_queues or {}
        ordered_ids: list[str] = []
        if neighbor_ids:
            ordered_ids.extend(neighbor_ids)
        else:
            for mapping in (neighbor_actions, neighbor_phases, neighbor_queues):
                for neighbor_id in mapping:
                    if neighbor_id not in ordered_ids:
                        ordered_ids.append(neighbor_id)
        ordered_ids = ordered_ids[: self.neighbor_feature_max_neighbors]

        features = [0.0] * self.neighbor_feature_count
        action_offset = 0
        phase_offset = self.neighbor_feature_max_neighbors * self.num_phases
        queue_offset = phase_offset + self.neighbor_feature_max_neighbors * self.num_phases

        for idx, neighbor_id in enumerate(ordered_ids):
            action = neighbor_actions.get(neighbor_id)
            if action is not None and 0 <= action < self.num_phases:
                features[action_offset + idx * self.num_phases + action] = 1.0

            phase = neighbor_phases.get(neighbor_id)
            if phase is not None and 0 <= phase < self.num_phases:
                features[phase_offset + idx * self.num_phases + phase] = 1.0

            if neighbor_id in neighbor_queues:
                features[queue_offset + idx] = self._normalized_queue(neighbor_queues[neighbor_id])

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
        incident_action_features: list[list[float]] | None = None,
        neighbor_ids: list[str] | None = None,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
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
                incident_action_features=incident_action_features,
                neighbor_ids=neighbor_ids,
                neighbor_actions=neighbor_actions,
                neighbor_phases=neighbor_phases,
                neighbor_queues=neighbor_queues,
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
        incident_action_features: list[list[float]] | None = None,
        neighbor_ids: list[str] | None = None,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
    ) -> list[float]:
        next_queues = self.predict_next_queues(
            current_queues,
            action,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
            blocked_edges=incident_edges,
            neighbor_actions=neighbor_actions,
            neighbor_queues=neighbor_queues,
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
            incident_action_features=incident_action_features,
            neighbor_ids=neighbor_ids,
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
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
        incident_action_features: list[list[float]] | None = None,
        neighbor_ids: list[str] | None = None,
        neighbor_actions: dict[str, int] | None = None,
        neighbor_phases: dict[str, int] | None = None,
        neighbor_queues: dict[str, float] | None = None,
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
            incident_action_features,
            neighbor_ids,
            neighbor_actions,
            neighbor_phases,
            neighbor_queues,
        )
        best_action = max(range(self.num_phases), key=lambda action: q_values[action])
        return best_action

    def _served_queue_for_action(self, current_queues: Dict[str, float], action: int) -> float:
        if not 0 <= action < len(self.action_edges):
            return 0.0
        return sum(current_queues.get(edge_id, 0.0) for edge_id in self.action_edges[action])

    def _downstream_spillback_penalty(
        self,
        action: int,
        downstream_queues: list[float] | None,
        downstream_capacities: list[float] | None,
    ) -> float:
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
        downstream_capacity = max(1.0, downstream_capacity)
        occupancy = downstream_queue / downstream_capacity
        if occupancy <= self.spillback_occupancy_threshold:
            return 0.0
        return (occupancy - self.spillback_occupancy_threshold) / max(
            0.01,
            1.0 - self.spillback_occupancy_threshold,
        )

    def _estimate_residual_lookahead_values(
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
        incident_edges: list[str] | None,
        action_pressures: list[float] | None,
        downstream_queues: list[float] | None,
        downstream_capacities: list[float] | None,
        incident_action_features: list[list[float]] | None,
        depth: int,
    ) -> list[float]:
        q_values = [float("-inf")] * self.num_phases
        for action in range(self.num_phases):
            predicted_queues = self.predict_next_queues(
                current_queues,
                action,
                downstream_queues=downstream_queues,
                downstream_capacities=downstream_capacities,
                blocked_edges=incident_edges,
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
            features = self.extract_features(
                current_queues,
                current_phase,
                dist_to_incident,
                incident_direction,
                time_discrete,
                incident_active,
                action=action,
                action_pressures=action_pressures,
                downstream_queues=downstream_queues,
                downstream_capacities=downstream_capacities,
                incident_action_features=incident_action_features,
            )
            served_score = self._served_queue_for_action(current_queues, action) / self.queue_scale
            pressure_score = (
                action_pressures[action] / self.queue_scale
                if action_pressures and 0 <= action < len(action_pressures)
                else 0.0
            )
            learned_residual = self.get_value(features)
            downstream_penalty = self._downstream_spillback_penalty(
                action,
                downstream_queues,
                downstream_capacities,
            )

            q_value = (
                reward
                + self.residual_greedy_weight * served_score
                + self.residual_pressure_weight * pressure_score
                + self.residual_value_weight * learned_residual
                - self.residual_downstream_penalty_weight * downstream_penalty
            )
            if depth > 1:
                future_values = self._estimate_residual_lookahead_values(
                    predicted_queues,
                    baseline_queues,
                    tau,
                    action,
                    dist_to_incident,
                    incident_direction,
                    time_discrete + 1,
                    is_gridlock,
                    incident_active,
                    gamma,
                    incident_edges,
                    None,
                    downstream_queues,
                    downstream_capacities,
                    incident_action_features,
                    depth - 1,
                )
                q_value += gamma * self.residual_lookahead_weight * max(future_values)

            if math.isfinite(q_value):
                q_values[action] = q_value

        if all(value == float("-inf") for value in q_values):
            return [0.0] * self.num_phases
        return q_values

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
        incident_action_features: list[list[float]] | None = None,
    ) -> list[float]:
        if self.action_scoring_mode == "residual_lookahead":
            return self._estimate_residual_lookahead_values(
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
                incident_action_features,
                self.lookahead_depth,
            )

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
                incident_action_features,
            )
            heuristic_score = reward + self.queue_priority_weight * served_queue / self.queue_scale
            if self.action_scoring_mode == "heuristic_residual":
                features = self.extract_features(
                    current_queues,
                    current_phase,
                    dist_to_incident,
                    incident_direction,
                    time_discrete,
                    incident_active,
                    action=action,
                    action_pressures=action_pressures,
                    downstream_queues=downstream_queues,
                    downstream_capacities=downstream_capacities,
                    incident_action_features=incident_action_features,
                )
                q_value = heuristic_score + self.residual_value_weight * self.get_value(features)
            else:
                q_value = heuristic_score + gamma * future_value
            if not math.isfinite(q_value):
                continue
            q_values[action] = q_value
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
