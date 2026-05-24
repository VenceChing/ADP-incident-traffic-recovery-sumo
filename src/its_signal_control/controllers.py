from typing import Any

import traci

from .agent import ADPAgent
from .config import *
from .env import SumoEnv
from .traffic_model import get_incident_direction, get_incident_distance


def get_agent_queues(
    env: SumoEnv,
    agent_id: str,
    sim_time: float,
    incident_edges: list[str],
) -> dict[str, float]:
    state = env.get_agent_state(agent_id, INCIDENT_TIME, sim_time, incident_edges)
    current_queues: dict[str, float] = {}
    for lane_id, current_q in state["queue_lengths"].items():
        edge_id = traci.lane.getEdgeID(lane_id)
        current_queues[edge_id] = current_queues.get(edge_id, 0.0) + current_q
    return current_queues


def select_greedy_action(agent: ADPAgent, current_queues: dict[str, float]) -> int:
    return max(
        range(agent.num_phases),
        key=lambda action: sum(current_queues.get(edge_id, 0.0) for edge_id in agent.action_edges[action]),
    )


def select_max_pressure_action(
    agent_id: str,
    context: dict[str, Any],
) -> int:
    action_pressures, _, _ = get_action_pressure_features(agent_id, context)
    return max(range(4), key=lambda action: action_pressures[action])


def get_action_pressure_features(
    agent_id: str,
    context: dict[str, Any],
) -> tuple[list[float], list[float], list[float]]:
    scores = []
    downstream_queues = []
    downstream_capacities = []
    for action in range(4):
        pressure = 0.0
        downstream_total = 0.0
        downstream_capacity = 0.0
        has_bounded_downstream = False
        for from_edge, to_edge in context["action_downstream_edges"][agent_id].get(action, []):
            upstream_queue = traci.edge.getLastStepHaltingNumber(from_edge)
            downstream_queue = (
                traci.edge.getLastStepHaltingNumber(to_edge)
                if to_edge and not to_edge.startswith(":")
                else 0.0
            )
            pressure += upstream_queue - downstream_queue
            downstream_total += downstream_queue
            if to_edge and not to_edge.startswith(":"):
                downstream_capacity += context["edge_capacities"].get(
                    to_edge,
                    ADP_UNBOUNDED_DOWNSTREAM_CAPACITY,
                )
                has_bounded_downstream = True
        scores.append(pressure)
        downstream_queues.append(downstream_total)
        downstream_capacities.append(
            downstream_capacity if has_bounded_downstream else ADP_UNBOUNDED_DOWNSTREAM_CAPACITY
        )
    return scores, downstream_queues, downstream_capacities


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
) -> tuple[int, list[float]]:
    incident_active = sim_time >= INCIDENT_TIME
    dist_to_incident = get_incident_distance(agent_id, incident_edges)
    incident_direction = get_incident_direction(agent_id, incident_edges)
    time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
    action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
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
) -> None:
    for agent_id, agent in agents.items():
        incident_active = sim_time >= INCIDENT_TIME
        next_queues = get_agent_queues(env, agent_id, sim_time, incident_edges)
        dist_to_incident = get_incident_distance(agent_id, incident_edges)
        incident_direction = get_incident_direction(agent_id, incident_edges)
        time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
        action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
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
        )
        agent.update_weights(
            step_cache[agent_id]["features"],
            reward,
            next_features,
            ALPHA,
            GAMMA,
        )
