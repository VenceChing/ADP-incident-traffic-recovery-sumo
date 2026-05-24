import random
from typing import Any

import traci

from .agent import ADPAgent
from .config import *

ACTIVE_ROUTE_FILE = ROUTE_FILE


def set_active_route_file(route_file: str) -> None:
    global ACTIVE_ROUTE_FILE
    ACTIVE_ROUTE_FILE = route_file


def add_keepalive_vehicle() -> None:
    """Ensure SUMO keeps running until the incident time."""
    if KEEPALIVE_ROUTE_ID not in traci.route.getIDList():
        traci.route.add(KEEPALIVE_ROUTE_ID, KEEPALIVE_EDGE_IDS)
    if KEEPALIVE_VEH_ID not in traci.vehicle.getIDList():
        traci.vehicle.add(
            KEEPALIVE_VEH_ID,
            KEEPALIVE_ROUTE_ID,
            depart=str(KEEPALIVE_DEPART),
        )


def get_manhattan_distance(node1: str, node2: str) -> int:
    x1 = ord(node1[0].upper()) - ord("A")
    y1 = int(node1[1:])
    x2 = ord(node2[0].upper()) - ord("A")
    y2 = int(node2[1:])
    return abs(x1 - x2) + abs(y1 - y2)


def get_edge_endpoints(edge_id: str) -> tuple[str, str] | None:
    if edge_id.startswith("-") or edge_id.startswith(":") or len(edge_id) != 4:
        return None
    return edge_id[:2], edge_id[2:]


def build_incident_candidates(edge_ids: list[str], tls_ids: list[str]) -> list[list[str]]:
    tls_set = set(tls_ids)
    edge_set = set(edge_ids)
    candidates = []
    seen_segments = set()

    for edge_id in sorted(edge_ids):
        endpoints = get_edge_endpoints(edge_id)
        if endpoints is None:
            continue
        from_node, to_node = endpoints
        if from_node not in tls_set or to_node not in tls_set:
            continue
        reverse_edge = f"{to_node}{from_node}"
        if reverse_edge not in edge_set:
            continue

        segment_key = tuple(sorted((from_node, to_node)))
        if segment_key in seen_segments:
            continue
        seen_segments.add(segment_key)
        candidates.append(sorted([edge_id, reverse_edge]))

    return candidates or [list(DEFAULT_INCIDENT_EDGES)]


def split_incidents(candidates: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    if len(candidates) <= 1:
        return [list(candidates[0])], [list(candidates[0])]
    shuffled = [list(candidate) for candidate in candidates]
    random.Random(RANDOM_SEED).shuffle(shuffled)
    split_index = max(1, min(len(shuffled) - 1, int(len(shuffled) * TRAIN_INCIDENT_FRACTION)))
    return shuffled[:split_index], shuffled[split_index:]


def get_incident_distance(agent_id: str, incident_edges: list[str]) -> int:
    incident_nodes = set()
    for edge_id in incident_edges:
        endpoints = get_edge_endpoints(edge_id)
        if endpoints is None:
            continue
        incident_nodes.update(endpoints)
    if not incident_nodes:
        return 0
    return min(get_manhattan_distance(agent_id, node_id) for node_id in incident_nodes)


def get_switch_penalty() -> float:
    lost_time = YELLOW_SECONDS + ALL_RED_SECONDS
    return SWITCH_PENALTY_SCALE * lost_time / max(1.0, DECISION_INTERVAL)


def get_train_epsilon(episode: int) -> float:
    if TRAIN_EPISODES <= 1:
        return TRAIN_EPSILON_END
    progress = min(1.0, max(0.0, episode / (TRAIN_EPISODES - 1)))
    return TRAIN_EPSILON_START + progress * (TRAIN_EPSILON_END - TRAIN_EPSILON_START)


def get_incident_direction(agent_id: str, incident_edges: list[str]) -> int | None:
    incident_nodes = set()
    for edge_id in incident_edges:
        endpoints = get_edge_endpoints(edge_id)
        if endpoints is None:
            continue
        incident_nodes.update(endpoints)
    if not incident_nodes:
        return None

    x0 = ord(agent_id[0].upper()) - ord("A")
    y0 = int(agent_id[1:])
    nearest_node = min(
        incident_nodes,
        key=lambda node_id: get_manhattan_distance(agent_id, node_id),
    )
    x1 = ord(nearest_node[0].upper()) - ord("A")
    y1 = int(nearest_node[1:])
    dx = x1 - x0
    dy = y1 - y0
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return 1 if dx > 0 else 3
    return 2 if dy > 0 else 0


def format_incident_direction(direction: int | None) -> str:
    if direction is None:
        return "AT_INCIDENT"
    return ["N", "E", "S", "W"][direction]


def get_total_queue(edge_ids: list[str]) -> float:
    return sum(traci.edge.getLastStepHaltingNumber(edge_id) for edge_id in edge_ids)


def get_queue_excess(
    current_queues_all: dict[str, float],
    baseline_queues: dict[str, float],
    incident_edges: list[str],
    edge_queue_floor: float = 0.0,
) -> tuple[float, float]:
    total_excess = 0.0
    max_excess = 0.0
    for edge_id, current_queue in current_queues_all.items():
        if edge_id in incident_edges:
            continue
        threshold = TAU * baseline_queues.get(edge_id, 0.0) + edge_queue_floor
        excess = max(0.0, current_queue - threshold)
        total_excess += excess
        max_excess = max(max_excess, excess)
    return total_excess, max_excess


def check_episode_status(
    current_queues_all: dict[str, float],
    baseline_queues: dict[str, float],
    current_time: float,
    incident_time: float,
    incident_edges: list[str],
    traffic_rate: float,
    baseline_arrival_rate: float,
    recent_arrival_rate: float,
    baseline_halting_ratio: float,
    recent_halting_ratio: float,
    current_halting_ratio: float,
) -> str:
    total_vehicles = traci.vehicle.getIDCount()
    halting_vehicles = sum(current_queues_all.values())

    expected_warmup_demand = traffic_rate * GRIDLOCK_WARMUP_TIME / 3600.0
    min_critical_vehicles = max(
        GRIDLOCK_MIN_VEHICLE_FLOOR,
        int(expected_warmup_demand * GRIDLOCK_WARMUP_DEMAND_FRACTION),
    )

    if total_vehicles > 0:
        if current_time - check_episode_status.last_debug_time >= GRIDLOCK_DEBUG_INTERVAL:
            print(
                "DEBUG: Gridlock check: "
                f"time={current_time:.1f}, "
                f"halting={halting_vehicles}, "
                f"total={total_vehicles}, "
                f"ratio={current_halting_ratio:.2f}, "
                f"min_critical={min_critical_vehicles}"
            )
            check_episode_status.last_debug_time = current_time

        gridlock_candidate = (
            current_time >= incident_time
            and current_time > GRIDLOCK_WARMUP_TIME
            and total_vehicles >= min_critical_vehicles
            and current_halting_ratio > GRIDLOCK_HALTING_RATIO
        )
        if gridlock_candidate:
            if check_episode_status.gridlock_candidate_since is None:
                check_episode_status.gridlock_candidate_since = current_time
            if current_time - check_episode_status.gridlock_candidate_since >= GRIDLOCK_CONFIRMATION_TIME:
                return "GRIDLOCK"
        else:
            check_episode_status.gridlock_candidate_since = None

    if not baseline_queues:
        return "ONGOING"

    total_success_excess, max_nonincident_excess = get_queue_excess(
        current_queues_all,
        baseline_queues,
        incident_edges,
        edge_queue_floor=SUCCESS_EDGE_QUEUE_FLOOR,
    )
    halting_ratio_threshold = min(
        SUCCESS_HALTING_RATIO_CAP,
        baseline_halting_ratio * SUCCESS_HALTING_RATIO_MULTIPLIER + SUCCESS_HALTING_RATIO_MARGIN,
    )
    halting_ratio_ok = (
        recent_halting_ratio <= halting_ratio_threshold
        and current_halting_ratio <= halting_ratio_threshold
    )
    flow_recovered = (
        baseline_arrival_rate < MIN_BASELINE_ARRIVAL_RATE
        or recent_arrival_rate >= FLOW_RECOVERY_RATIO * baseline_arrival_rate
    )
    success_candidate = (
        current_time >= incident_time + SUCCESS_MIN_DELAY
        and max_nonincident_excess <= 0.0
        and total_success_excess <= SUCCESS_TOTAL_QUEUE_EXCESS_CAP
        and halting_ratio_ok
        and flow_recovered
    )
    if success_candidate:
        if check_episode_status.success_candidate_since is None:
            check_episode_status.success_candidate_since = current_time
        if current_time - check_episode_status.success_candidate_since >= SUCCESS_CONFIRMATION_TIME:
            return "SUCCESS"
    else:
        check_episode_status.success_candidate_since = None

    return "ONGOING"


def reset_episode_detector() -> None:
    check_episode_status.gridlock_candidate_since = None
    check_episode_status.success_candidate_since = None
    check_episode_status.last_debug_time = -GRIDLOCK_DEBUG_INTERVAL


def build_sumo_args(seed: int) -> list[str]:
    sumo_args = [
        "-c",
        SUMO_CONFIG,
        "--route-files",
        ACTIVE_ROUTE_FILE,
        "--start",
        "--step-length",
        str(STEP_LENGTH),
        "--device.rerouting.probability",
        str(REROUTING_PROBABILITY),
        "--device.rerouting.period",
        str(REROUTING_PERIOD),
        "--time-to-teleport",
        "-1",
        "--seed",
        str(seed),
        "--no-warnings",
    ]
    if SIM_END_TIME is not None:
        sumo_args.extend(["--end", str(SIM_END_TIME)])
    return sumo_args


def build_sumo_cmd(seed: int) -> list[str]:
    sumo_binary = "sumo-gui" if USE_GUI else "sumo"
    return [sumo_binary] + build_sumo_args(seed)


def lane_to_dir(lane_id: str) -> str | None:
    shape = traci.lane.getShape(lane_id)
    if len(shape) < 2:
        return None
    x1, y1 = shape[0]
    x2, y2 = shape[-1]
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) >= abs(dy):
        return "W" if dx > 0 else "E"
    return "S" if dy > 0 else "N"


def build_controller_context(tls_ids: list[str]) -> dict[str, Any]:
    dir_to_action = {"N": 0, "E": 1, "S": 2, "W": 3}
    tls_state_len = {}
    tls_dir_links = {}
    tls_all_red = {}
    action_downstream_edges: dict[str, dict[int, list[tuple[str, str | None]]]] = {}
    edge_capacities: dict[str, float] = {}

    for edge_id in traci.edge.getIDList():
        if edge_id.startswith(":"):
            continue
        capacity = 0.0
        try:
            lane_count = traci.edge.getLaneNumber(edge_id)
            for lane_index in range(lane_count):
                lane_id = f"{edge_id}_{lane_index}"
                capacity += traci.lane.getLength(lane_id) / ADP_VEHICLE_SPACING
        except traci.TraCIException:
            capacity = 0.0
        edge_capacities[edge_id] = max(1.0, capacity)

    for tls_id in tls_ids:
        links = traci.trafficlight.getControlledLinks(tls_id)
        tls_state_len[tls_id] = len(links)
        tls_all_red[tls_id] = "r" * len(links)
        action_indices = {0: [], 1: [], 2: [], 3: []}
        action_downstream_edges[tls_id] = {0: [], 1: [], 2: [], 3: []}

        for idx, link_group in enumerate(links):
            if not link_group:
                continue
            from_lane = link_group[0][0]
            to_lane = link_group[0][1]
            if from_lane is None:
                continue
            direction = lane_to_dir(from_lane)
            if direction is None:
                continue
            action = dir_to_action[direction]
            action_indices[action].append(idx)

            from_edge = traci.lane.getEdgeID(from_lane)
            try:
                to_edge = traci.lane.getEdgeID(to_lane) if to_lane else None
            except traci.TraCIException:
                to_edge = None
            if from_edge and not from_edge.startswith(":"):
                action_downstream_edges[tls_id][action].append((from_edge, to_edge))

        tls_dir_links[tls_id] = action_indices

    return {
        "tls_state_len": tls_state_len,
        "tls_dir_links": tls_dir_links,
        "tls_all_red": tls_all_red,
        "action_downstream_edges": action_downstream_edges,
        "edge_capacities": edge_capacities,
    }


def build_tls_state(context: dict[str, Any], tls_id: str, action: int, green_char: str) -> str:
    chars = ["r"] * context["tls_state_len"][tls_id]
    for link_index in context["tls_dir_links"][tls_id].get(action, []):
        chars[link_index] = green_char
    return "".join(chars)


def infer_current_action(context: dict[str, Any], tls_id: str, fallback: int = 0) -> int:
    state = traci.trafficlight.getRedYellowGreenState(tls_id)
    best_action = fallback
    best_green_count = -1
    for action, link_indices in context["tls_dir_links"][tls_id].items():
        green_count = sum(
            1
            for link_index in link_indices
            if link_index < len(state) and state[link_index] in {"G", "g"}
        )
        if green_count > best_green_count:
            best_green_count = green_count
            best_action = action
    return best_action if best_green_count > 0 else fallback


def build_agents(tls_ids: list[str]) -> dict[str, ADPAgent]:
    dir_to_action = {"N": 0, "E": 1, "S": 2, "W": 3}
    agents = {}
    for tls_id in tls_ids:
        lanes = traci.trafficlight.getControlledLanes(tls_id)
        action_edges = {0: [], 1: [], 2: [], 3: []}
        for lane in lanes:
            try:
                edge = traci.lane.getEdgeID(lane)
            except traci.TraCIException:
                continue
            if not edge or edge.startswith(":"):
                continue
            direction = lane_to_dir(lane)
            if direction is None:
                continue
            action = dir_to_action[direction]
            if edge not in action_edges[action]:
                action_edges[action].append(edge)

        incoming_edges = []
        action_edge_lists = []
        for action in range(4):
            action_edge_lists.append(action_edges[action])
            for edge in action_edges[action]:
                if edge not in incoming_edges:
                    incoming_edges.append(edge)

        agents[tls_id] = ADPAgent(
            agent_id=tls_id,
            incoming_edges=incoming_edges,
            action_edges=action_edge_lists,
            decision_interval=DECISION_INTERVAL,
            traffic_rate=RATE,
            switch_penalty=get_switch_penalty(),
            gridlock_penalty=ADP_GRIDLOCK_PENALTY,
            queue_priority_weight=ADP_QUEUE_PRIORITY_WEIGHT,
            total_queue_weight=ADP_TOTAL_QUEUE_WEIGHT,
            queue_scale=ADP_QUEUE_SCALE,
            distance_scale=ADP_DISTANCE_SCALE,
            time_scale=ADP_TIME_SCALE,
            feature_clip=ADP_FEATURE_CLIP,
            max_abs_weight=ADP_MAX_ABS_WEIGHT,
            max_abs_td_error=ADP_MAX_ABS_TD_ERROR,
            spillback_occupancy_threshold=ADP_SPILLBACK_OCCUPANCY_THRESHOLD,
            unbounded_downstream_capacity=ADP_UNBOUNDED_DOWNSTREAM_CAPACITY,
            model_ewma_alpha=ADP_MODEL_EWMA_ALPHA,
            min_model_observations=ADP_MIN_MODEL_OBSERVATIONS,
        )

    return agents


check_episode_status.gridlock_candidate_since = None
check_episode_status.success_candidate_since = None
check_episode_status.last_debug_time = -GRIDLOCK_DEBUG_INTERVAL
