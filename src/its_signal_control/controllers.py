from typing import Any

import traci

from .agent import ADPAgent
from .config import *
from .env import SumoEnv
from .traffic_model import get_edge_endpoints, get_incident_direction, get_incident_distance, get_manhattan_distance


def get_agent_queues(
    env: SumoEnv,
    agent_id: str,
    sim_time: float,
    incident_edges: list[str],
    context: dict[str, Any] | None = None,
) -> dict[str, float]:
    state = env.get_agent_state(agent_id, INCIDENT_TIME, sim_time, incident_edges)
    current_queues: dict[str, float] = {}
    for lane_id, current_q in state["queue_lengths"].items():
        edge_id = traci.lane.getEdgeID(lane_id)
        queue_key = (
            context.get("lane_to_queue_key", {}).get(lane_id, edge_id)
            if context is not None
            else edge_id
        )
        current_queues[queue_key] = current_queues.get(queue_key, 0.0) + current_q
    return current_queues


def select_greedy_action(agent: ADPAgent, current_queues: dict[str, float]) -> int:
    return max(
        range(agent.num_phases),
        key=lambda action: sum(current_queues.get(edge_id, 0.0) for edge_id in agent.action_edges[action]),
    )


def select_max_pressure_action(
    agent: ADPAgent,
    agent_id: str,
    context: dict[str, Any],
) -> int:
    action_pressures, _, _ = get_action_pressure_features(agent_id, context)
    return max(range(agent.num_phases), key=lambda action: action_pressures[action])


def get_queue_value(queue_key: str | None, context: dict[str, Any]) -> float:
    if not queue_key:
        return 0.0
    if context.get("queue_key_mode") == "lane":
        try:
            return traci.lane.getLastStepHaltingNumber(queue_key)
        except traci.TraCIException:
            return 0.0
    return traci.edge.getLastStepHaltingNumber(queue_key)


def get_action_pressure_features(
    agent_id: str,
    context: dict[str, Any],
) -> tuple[list[float], list[float], list[float]]:
    scores = []
    downstream_queues = []
    downstream_capacities = []
    for action in range(len(context["action_names"])):
        if context.get("queue_key_mode") == "edge":
            pressure = 0.0
            downstream_total = 0.0
            downstream_capacity = 0.0
            has_bounded_downstream = False
            for from_key, to_key in context["action_downstream_edges"][agent_id].get(action, []):
                upstream_queue = get_queue_value(from_key, context)
                downstream_queue = get_queue_value(to_key, context) if to_key else 0.0
                pressure += upstream_queue - downstream_queue
                downstream_total += downstream_queue
                if to_key:
                    downstream_capacity += context["queue_key_capacities"].get(
                        to_key,
                        ADP_UNBOUNDED_DOWNSTREAM_CAPACITY,
                    )
                    has_bounded_downstream = True
            scores.append(pressure)
            downstream_queues.append(downstream_total)
            downstream_capacities.append(
                downstream_capacity if has_bounded_downstream else ADP_UNBOUNDED_DOWNSTREAM_CAPACITY
            )
            continue

        upstream_keys = context["action_upstream_keys"][agent_id].get(action, [])
        downstream_keys = context["action_downstream_keys"][agent_id].get(action, [])
        upstream_total = sum(get_queue_value(queue_key, context) for queue_key in upstream_keys)
        downstream_total = sum(get_queue_value(queue_key, context) for queue_key in downstream_keys)
        scaled_downstream = (
            downstream_total * len(upstream_keys) / len(downstream_keys)
            if downstream_keys and upstream_keys
            else downstream_total
        )
        pressure = upstream_total - scaled_downstream
        downstream_capacity = 0.0
        has_bounded_downstream = False
        for queue_key in downstream_keys:
            downstream_capacity += context["queue_key_capacities"].get(
                queue_key,
                ADP_UNBOUNDED_DOWNSTREAM_CAPACITY,
            )
            has_bounded_downstream = True
        scores.append(pressure)
        downstream_queues.append(downstream_total)
        downstream_capacities.append(
            downstream_capacity if has_bounded_downstream else ADP_UNBOUNDED_DOWNSTREAM_CAPACITY
        )
    return scores, downstream_queues, downstream_capacities


def _edge_min_distance_to_nodes(edge_id: str | None, node_ids: set[str]) -> int | None:
    if edge_id is None or not node_ids:
        return None
    endpoints = get_edge_endpoints(edge_id)
    if endpoints is None:
        return None
    return min(
        get_manhattan_distance(endpoint, node_id)
        for endpoint in endpoints
        for node_id in node_ids
    )


def get_incident_action_features(
    agent_id: str,
    current_queues: dict[str, float],
    incident_edges: list[str],
    incident_active: bool,
    context: dict[str, Any],
) -> list[list[float]] | None:
    if not ADP_INCIDENT_ACTION_FEATURES_ENABLED:
        return None
    if context.get("action_space") != "three_lane_8":
        return None

    incident_edge_set = set(incident_edges)
    incident_nodes: set[str] = set()
    for edge_id in incident_edges:
        endpoints = get_edge_endpoints(edge_id)
        if endpoints is not None:
            incident_nodes.update(endpoints)

    feature_rows: list[list[float]] = []
    for action in range(len(context["action_names"])):
        movement_edges = context["action_movement_edges"][agent_id].get(action, [])
        downstream_edges = [to_edge for _, to_edge in movement_edges if to_edge is not None]
        denominator = max(1, len(downstream_edges))
        blocked_downstream = 0
        incident_node_downstream = 0
        near_incident_downstream = 0

        for to_edge in downstream_edges:
            endpoints = get_edge_endpoints(to_edge)
            if to_edge in incident_edge_set:
                blocked_downstream += 1
            if endpoints is not None and incident_nodes.intersection(endpoints):
                incident_node_downstream += 1
            min_distance = _edge_min_distance_to_nodes(to_edge, incident_nodes)
            if min_distance is not None and min_distance <= 1:
                near_incident_downstream += 1

        blocked_ratio = blocked_downstream / denominator
        incident_node_ratio = incident_node_downstream / denominator
        near_ratio = near_incident_downstream / denominator
        served_queue = sum(
            current_queues.get(queue_key, 0.0)
            for queue_key in context["action_upstream_keys"][agent_id].get(action, [])
        )
        active_multiplier = 1.0 if incident_active else 0.0
        feature_rows.append(
            [
                active_multiplier * blocked_ratio,
                active_multiplier * incident_node_ratio,
                active_multiplier * near_ratio,
                active_multiplier * blocked_ratio * served_queue / ADP_QUEUE_SCALE,
                active_multiplier * incident_node_ratio * served_queue / ADP_QUEUE_SCALE,
                active_multiplier * near_ratio * served_queue / ADP_QUEUE_SCALE,
            ]
        )

    return feature_rows


def select_adp_action(
    agent_id: str,
    agent: ADPAgent,
    current_queues: dict[str, float],
    baseline_queues: dict[str, float],
    current_phase: int,
    sim_time: float,
    incident_edges: list[str],
    epsilon: float,
    context: dict[str, Any],
    neighbor_ids: list[str] | None = None,
    neighbor_actions: dict[str, int] | None = None,
    neighbor_phases: dict[str, int] | None = None,
    neighbor_queues: dict[str, float] | None = None,
) -> tuple[int, list[float]]:
    incident_active = sim_time >= INCIDENT_TIME
    dist_to_incident = get_incident_distance(agent_id, incident_edges)
    incident_direction = get_incident_direction(agent_id, incident_edges)
    time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
    action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
    incident_action_features = get_incident_action_features(
        agent_id,
        current_queues,
        incident_edges,
        incident_active,
        context,
    )
    q_values = agent.estimate_action_values(
        current_queues,
        baseline_queues,
        TAU,
        current_phase,
        dist_to_incident,
        incident_direction,
        time_discrete,
        is_gridlock=False,
        incident_active=incident_active,
        gamma=GAMMA,
        incident_edges=incident_edges,
        action_pressures=action_pressures,
        downstream_queues=downstream_queues,
        downstream_capacities=downstream_capacities,
        incident_action_features=incident_action_features,
        neighbor_ids=neighbor_ids,
        neighbor_actions=neighbor_actions,
        neighbor_phases=neighbor_phases,
        neighbor_queues=neighbor_queues,
    )
    action = agent.select_action(
        current_queues,
        baseline_queues,
        TAU,
        current_phase,
        dist_to_incident,
        incident_direction,
        time_discrete,
        is_gridlock=False,
        incident_active=incident_active,
        epsilon=epsilon,
        gamma=GAMMA,
        incident_edges=incident_edges,
        action_pressures=action_pressures,
        downstream_queues=downstream_queues,
        downstream_capacities=downstream_capacities,
        incident_action_features=incident_action_features,
        neighbor_ids=neighbor_ids,
        neighbor_actions=neighbor_actions,
        neighbor_phases=neighbor_phases,
        neighbor_queues=neighbor_queues,
    )
    return action, q_values


def update_adp_agents(
    agents: dict[str, ADPAgent],
    env: SumoEnv,
    step_cache: dict[str, dict[str, Any]],
    baseline_queues: dict[str, float],
    python_current_phases: dict[str, int],
    sim_time: float,
    incident_edges: list[str],
    is_gridlock: bool,
    context: dict[str, Any],
    neighbor_info: dict[str, tuple[list[str], dict[str, int], dict[str, int], dict[str, float]]] | None = None,
) -> None:
    neighbor_info = neighbor_info or {}
    for agent_id, agent in agents.items():
        incident_active = sim_time >= INCIDENT_TIME
        next_queues = get_agent_queues(env, agent_id, sim_time, incident_edges, context)
        dist_to_incident = get_incident_distance(agent_id, incident_edges)
        incident_direction = get_incident_direction(agent_id, incident_edges)
        time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
        action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
        incident_action_features = get_incident_action_features(
            agent_id,
            next_queues,
            incident_edges,
            incident_active,
            context,
        )
        neighbor_ids, neighbor_actions, neighbor_phases, neighbor_queues = neighbor_info.get(
            agent_id,
            ([], {}, {}, {}),
        )
        reward = agent.calculate_reward(
            next_queues,
            baseline_queues,
            TAU,
            step_cache[agent_id]["current_phase"],
            step_cache[agent_id]["action"],
            is_gridlock=is_gridlock,
            incident_edges=incident_edges,
        )
        agent.update_transition_model(
            step_cache[agent_id]["current_queues"],
            next_queues,
            step_cache[agent_id]["action"],
            blocked_edges=incident_edges,
        )
        next_action = max(
            range(agent.num_phases),
            key=lambda candidate_action: agent.get_value(
                agent.extract_features(
                    next_queues,
                    python_current_phases[agent_id],
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
            ),
        )
        next_features = agent.extract_features(
            next_queues,
            python_current_phases[agent_id],
            dist_to_incident,
            incident_direction,
            time_discrete,
            incident_active,
            action=next_action,
            action_pressures=action_pressures,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
            incident_action_features=incident_action_features,
            neighbor_ids=neighbor_ids,
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
        )
        agent.update_weights(
            step_cache[agent_id]["features"],
            reward,
            next_features,
            ALPHA,
            GAMMA,
        )


class DecisionCache:
    """Per-cycle cache of earlier decisions for later neighboring agents."""

    def __init__(self) -> None:
        self.actions: dict[str, int] = {}
        self.phases: dict[str, int] = {}
        self.queues: dict[str, float] = {}

    def cache_decision(
        self,
        agent_id: str,
        action: int,
        current_phase: int,
        total_queue: float,
    ) -> None:
        self.actions[agent_id] = action
        self.phases[agent_id] = current_phase
        self.queues[agent_id] = total_queue

    def get_neighbor_info(
        self,
        neighbors: list[str],
    ) -> tuple[dict[str, int], dict[str, int], dict[str, float]]:
        neighbor_actions: dict[str, int] = {}
        neighbor_phases: dict[str, int] = {}
        neighbor_queues: dict[str, float] = {}
        for neighbor_id in neighbors:
            if neighbor_id in self.actions:
                neighbor_actions[neighbor_id] = self.actions[neighbor_id]
                neighbor_phases[neighbor_id] = self.phases[neighbor_id]
                neighbor_queues[neighbor_id] = self.queues[neighbor_id]
        return neighbor_actions, neighbor_phases, neighbor_queues

    def clear(self) -> None:
        self.actions.clear()
        self.phases.clear()
        self.queues.clear()
