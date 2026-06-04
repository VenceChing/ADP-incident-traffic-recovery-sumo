import math
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import traci

from .agent import ADPAgent
from .actions import (
    DIRECTION_TO_INDEX,
    action_matches,
    direction_indices_for_action,
    get_action_definitions,
    movement_group_for_connection,
)
from .config import *

ACTIVE_ROUTE_FILE = ROUTE_FILE
_NETWORK_TOPOLOGY: dict[str, Any] | None = None


def set_active_route_file(route_file: str) -> None:
    global ACTIVE_ROUTE_FILE
    ACTIVE_ROUTE_FILE = route_file


def _network_file_path() -> Path | None:
    candidates = [Path(NETWORK_FILE), REPO_ROOT / SCENARIO_DIR / NETWORK_FILE]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_network_topology() -> dict[str, Any]:
    global _NETWORK_TOPOLOGY
    if _NETWORK_TOPOLOGY is not None:
        return _NETWORK_TOPOLOGY

    topology: dict[str, Any] = {
        "edge_endpoints": {},
        "node_positions": {},
        "passenger_edges": set(),
    }
    network_path = _network_file_path()
    if network_path is None:
        _NETWORK_TOPOLOGY = topology
        return topology

    root = ET.parse(network_path).getroot()
    for junction in root.findall("junction"):
        node_id = junction.get("id")
        if not node_id or node_id.startswith(":"):
            continue
        try:
            x = float(junction.get("x", "0"))
            y = float(junction.get("y", "0"))
        except ValueError:
            continue
        topology["node_positions"][node_id] = (x, y)

    for edge in root.findall("edge"):
        edge_id = edge.get("id")
        if not edge_id or edge_id.startswith(":") or edge.get("function") == "internal":
            continue
        from_node = edge.get("from")
        to_node = edge.get("to")
        if from_node and to_node:
            topology["edge_endpoints"][edge_id] = (from_node, to_node)
        for lane in edge.findall("lane"):
            allow = set((lane.get("allow") or "").split())
            disallow = set((lane.get("disallow") or "").split())
            if allow:
                lane_allows_passenger = "passenger" in allow or "private" in allow
            else:
                lane_allows_passenger = "passenger" not in disallow and "all" not in disallow
            if lane_allows_passenger:
                topology["passenger_edges"].add(edge_id)
                break

    _NETWORK_TOPOLOGY = topology
    return topology


def _node_position(node_id: str) -> tuple[float, float] | None:
    return _load_network_topology()["node_positions"].get(node_id)


def _node_distance(node1: str, node2: str) -> float | None:
    pos1 = _node_position(node1)
    pos2 = _node_position(node2)
    if pos1 is None or pos2 is None:
        return None
    return math.hypot(pos2[0] - pos1[0], pos2[1] - pos1[1]) / 100.0


def _candidate_keepalive_routes() -> list[list[str]]:
    edge_ids = {edge_id for edge_id in traci.edge.getIDList() if not edge_id.startswith(":")}
    passenger_edges = _load_network_topology()["passenger_edges"] or edge_ids
    usable_edge_ids = edge_ids & passenger_edges
    candidates: list[list[str]] = []
    if KEEPALIVE_EDGE_IDS and all(edge_id in usable_edge_ids for edge_id in KEEPALIVE_EDGE_IDS):
        candidates.append(list(KEEPALIVE_EDGE_IDS))
    candidates.extend([[edge_id] for edge_id in sorted(usable_edge_ids)])
    return candidates


def add_keepalive_vehicle() -> None:
    """Ensure SUMO keeps running until the incident time."""
    if KEEPALIVE_VEH_ID not in traci.vehicle.getIDList():
        for idx, route_edges in enumerate(_candidate_keepalive_routes()):
            route_id = KEEPALIVE_ROUTE_ID if idx == 0 else f"{KEEPALIVE_ROUTE_ID}_{idx}"
            try:
                if route_id not in traci.route.getIDList():
                    traci.route.add(route_id, route_edges)
                traci.vehicle.add(
                    KEEPALIVE_VEH_ID,
                    route_id,
                    depart=str(KEEPALIVE_DEPART),
                )
                return
            except traci.TraCIException:
                continue
        print("WARNING: Could not add a keepalive vehicle; continuing without one.")


def get_manhattan_distance(node1: str, node2: str) -> int:
    topology_distance = _node_distance(node1, node2)
    if topology_distance is not None:
        return int(round(topology_distance))
    if len(node1) < 2 or len(node2) < 2:
        return 0
    x1 = ord(node1[0].upper()) - ord("A")
    y1 = int(node1[1:]) if node1[1:].isdigit() else 0
    x2 = ord(node2[0].upper()) - ord("A")
    y2 = int(node2[1:]) if node2[1:].isdigit() else 0
    return abs(x1 - x2) + abs(y1 - y2)


def get_edge_endpoints(edge_id: str) -> tuple[str, str] | None:
    topology_endpoints = _load_network_topology()["edge_endpoints"].get(edge_id)
    if topology_endpoints is not None:
        return topology_endpoints
    if edge_id.startswith("-") or edge_id.startswith(":") or len(edge_id) != 4:
        return None
    return edge_id[:2], edge_id[2:]


def build_incident_candidates(edge_ids: list[str], tls_ids: list[str]) -> list[list[str]]:
    tls_set = set(tls_ids)
    passenger_edges = _load_network_topology()["passenger_edges"]
    edge_set = set(edge_ids) & (passenger_edges or set(edge_ids))
    candidates = []
    seen_segments = set()
    endpoint_to_edges: dict[tuple[str, str], list[str]] = {}

    for edge_id in sorted(edge_set):
        endpoints = get_edge_endpoints(edge_id)
        if endpoints is None:
            continue
        from_node, to_node = endpoints
        endpoint_to_edges.setdefault((from_node, to_node), []).append(edge_id)

    if endpoint_to_edges:
        paired_candidates = []
        unpaired_candidates = []
        for (from_node, to_node), edges in sorted(endpoint_to_edges.items()):
            reverse_edges = endpoint_to_edges.get((to_node, from_node), [])
            segment_key = tuple(sorted((from_node, to_node)))
            if segment_key in seen_segments:
                continue
            seen_segments.add(segment_key)
            if reverse_edges:
                candidate = sorted([sorted(edges)[0], sorted(reverse_edges)[0]])
                paired_candidates.append(candidate)
            elif from_node in tls_set or to_node in tls_set:
                unpaired_candidates.append([sorted(edges)[0]])

        if paired_candidates:
            return paired_candidates
        if unpaired_candidates:
            return unpaired_candidates

    seen_segments = set()
    for edge_id in sorted(edge_set):
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


def filter_vehicle_edge_ids(edge_ids: list[str]) -> list[str]:
    passenger_edges = _load_network_topology()["passenger_edges"]
    if not passenger_edges:
        return edge_ids
    filtered = [edge_id for edge_id in edge_ids if edge_id in passenger_edges]
    return filtered or edge_ids


def get_agent_positions(agent_ids: list[str]) -> dict[str, tuple[float, float]]:
    node_positions = _load_network_topology()["node_positions"]
    return {
        agent_id: node_positions[agent_id]
        for agent_id in agent_ids
        if agent_id in node_positions
    }


def get_agent_neighbor_map(agent_ids: list[str]) -> dict[str, list[str]]:
    agent_set = set(agent_ids)
    edge_endpoints = _load_network_topology()["edge_endpoints"]
    neighbor_sets: dict[str, set[str]] = {agent_id: set() for agent_id in agent_ids}
    for from_node, to_node in edge_endpoints.values():
        if from_node in agent_set and to_node in agent_set and from_node != to_node:
            neighbor_sets[from_node].add(to_node)
            neighbor_sets[to_node].add(from_node)

    positions = get_agent_positions(agent_ids)

    def neighbor_key(agent_id: str, neighbor_id: str) -> tuple[float, str]:
        if agent_id in positions and neighbor_id in positions:
            ax, ay = positions[agent_id]
            nx, ny = positions[neighbor_id]
            return (math.atan2(ny - ay, nx - ax), neighbor_id)
        return (0.0, neighbor_id)

    return {
        agent_id: sorted(neighbors, key=lambda neighbor_id: neighbor_key(agent_id, neighbor_id))
        for agent_id, neighbors in neighbor_sets.items()
    }


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
    topology_distances = []
    for node_id in incident_nodes:
        distance = _node_distance(agent_id, node_id)
        if distance is not None:
            topology_distances.append(distance)
    if topology_distances:
        return int(round(min(topology_distances)))
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

    agent_position = _node_position(agent_id)
    positioned_nodes = [
        (node_id, _node_position(node_id))
        for node_id in incident_nodes
        if _node_position(node_id) is not None
    ]
    if agent_position is not None and positioned_nodes:
        x0, y0 = agent_position
        nearest_node, nearest_position = min(
            positioned_nodes,
            key=lambda item: math.hypot(item[1][0] - x0, item[1][1] - y0),  # type: ignore[index]
        )
        del nearest_node
        x1, y1 = nearest_position  # type: ignore[misc]
        dx = x1 - x0
        dy = y1 - y0
        if dx == 0 and dy == 0:
            return None
        if abs(dx) >= abs(dy):
            return 1 if dx > 0 else 3
        return 2 if dy > 0 else 0

    if not (len(agent_id) >= 2 and agent_id[0].isalpha() and agent_id[1:].isdigit()):
        return None

    x0 = ord(agent_id[0].upper()) - ord("A")
    y0 = int(agent_id[1:])
    nearest_node = min(
        incident_nodes,
        key=lambda node_id: get_manhattan_distance(agent_id, node_id),
    )
    if not (len(nearest_node) >= 2 and nearest_node[0].isalpha() and nearest_node[1:].isdigit()):
        return None
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
        "--ignore-route-errors",
        "--seed",
        str(seed),
        "--no-warnings",
        "--no-step-log",
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


def _queue_key_for_lane(lane_id: str | None, queue_key_mode: str) -> str | None:
    if lane_id is None:
        return None
    if queue_key_mode == "lane":
        return lane_id if not lane_id.startswith(":") else None
    try:
        edge_id = traci.lane.getEdgeID(lane_id)
    except traci.TraCIException:
        return None
    return edge_id if edge_id and not edge_id.startswith(":") else None


def _append_unique(values: list[str], value: str | None) -> None:
    if value is not None and value not in values:
        values.append(value)


def _append_unique_pair(values: list[tuple[str, str | None]], value: tuple[str, str | None]) -> None:
    if value not in values:
        values.append(value)


def _lane_capacity(lane_id: str) -> float:
    try:
        return max(1.0, traci.lane.getLength(lane_id) / ADP_VEHICLE_SPACING)
    except traci.TraCIException:
        return 1.0


def build_controller_context(tls_ids: list[str]) -> dict[str, Any]:
    action_definitions = get_action_definitions(ACTION_SPACE)
    action_names = [definition.name for definition in action_definitions]
    queue_key_mode = "lane" if ACTION_SPACE in {"two_lane_8", "three_lane_8"} else "edge"
    tls_state_len = {}
    tls_action_links = {}
    tls_all_red = {}
    action_upstream_keys: dict[str, dict[int, list[str]]] = {}
    action_downstream_keys: dict[str, dict[int, list[str]]] = {}
    action_downstream_edges: dict[str, dict[int, list[tuple[str, str | None]]]] = {}
    action_movement_edges: dict[str, dict[int, list[tuple[str, str | None]]]] = {}
    edge_capacities: dict[str, float] = {}
    queue_key_capacities: dict[str, float] = {}
    lane_to_queue_key: dict[str, str] = {}
    queue_key_approaches: dict[str, str] = {}
    queue_key_movements: dict[str, str] = {}

    for edge_id in traci.edge.getIDList():
        if edge_id.startswith(":"):
            continue
        capacity = 0.0
        try:
            lane_count = traci.edge.getLaneNumber(edge_id)
            for lane_index in range(lane_count):
                lane_id = f"{edge_id}_{lane_index}"
                lane_capacity = _lane_capacity(lane_id)
                capacity += lane_capacity
                if queue_key_mode == "lane":
                    queue_key_capacities[lane_id] = lane_capacity
        except traci.TraCIException:
            capacity = 0.0
        edge_capacities[edge_id] = max(1.0, capacity)
        if queue_key_mode == "edge":
            queue_key_capacities[edge_id] = edge_capacities[edge_id]

    for tls_id in tls_ids:
        links = traci.trafficlight.getControlledLinks(tls_id)
        tls_state_len[tls_id] = len(links)
        tls_all_red[tls_id] = "r" * len(links)
        action_indices = {action: [] for action in range(len(action_definitions))}
        action_upstream_keys[tls_id] = {action: [] for action in range(len(action_definitions))}
        action_downstream_keys[tls_id] = {action: [] for action in range(len(action_definitions))}
        action_downstream_edges[tls_id] = {action: [] for action in range(len(action_definitions))}
        action_movement_edges[tls_id] = {action: [] for action in range(len(action_definitions))}

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
            movement_group = movement_group_for_connection(from_lane, action_space=ACTION_SPACE)
            from_key = _queue_key_for_lane(from_lane, queue_key_mode)
            to_key = _queue_key_for_lane(to_lane, queue_key_mode) if to_lane else None
            from_edge = traci.lane.getEdgeID(from_lane)
            to_edge = traci.lane.getEdgeID(to_lane) if to_lane else None

            if from_key is not None:
                lane_to_queue_key[from_lane] = from_key
                queue_key_approaches[from_key] = direction
                queue_key_movements[from_key] = movement_group

            for action, definition in enumerate(action_definitions):
                if not action_matches(definition, direction, movement_group):
                    continue
                action_indices[action].append(idx)
                _append_unique(action_upstream_keys[tls_id][action], from_key)
                _append_unique(action_downstream_keys[tls_id][action], to_key)
                _append_unique_pair(action_movement_edges[tls_id][action], (from_edge, to_edge))
                if from_key is not None:
                    action_downstream_edges[tls_id][action].append((from_key, to_key))

        tls_action_links[tls_id] = action_indices

    return {
        "action_space": ACTION_SPACE,
        "action_names": action_names,
        "action_definitions": action_definitions,
        "action_approaches": [
            direction_indices_for_action(definition)
            for definition in action_definitions
        ],
        "queue_key_mode": queue_key_mode,
        "tls_state_len": tls_state_len,
        "tls_dir_links": tls_action_links,
        "tls_action_links": tls_action_links,
        "tls_all_red": tls_all_red,
        "action_upstream_keys": action_upstream_keys,
        "action_downstream_keys": action_downstream_keys,
        "action_downstream_edges": action_downstream_edges,
        "action_movement_edges": action_movement_edges,
        "lane_to_queue_key": lane_to_queue_key,
        "queue_key_approaches": queue_key_approaches,
        "queue_key_movements": queue_key_movements,
        "queue_key_capacities": queue_key_capacities,
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


def build_agents(tls_ids: list[str], context: dict[str, Any] | None = None) -> dict[str, ADPAgent]:
    if context is None:
        context = build_controller_context(tls_ids)
    agents = {}
    for tls_id in tls_ids:
        incoming_edges = []
        action_edge_lists = []
        for action in range(len(context["action_names"])):
            action_edges = list(context["action_upstream_keys"][tls_id].get(action, []))
            action_edge_lists.append(action_edges)
            for edge in action_edges:
                if edge not in incoming_edges:
                    incoming_edges.append(edge)

        agents[tls_id] = ADPAgent(
            agent_id=tls_id,
            incoming_edges=incoming_edges,
            action_edges=action_edge_lists,
            num_phases=len(context["action_names"]),
            action_names=context["action_names"],
            action_approaches=context["action_approaches"],
            queue_movements={
                queue_key: context["queue_key_movements"].get(queue_key, "")
                for queue_key in incoming_edges
            },
            queue_approaches={
                queue_key: context["queue_key_approaches"].get(queue_key, "")
                for queue_key in incoming_edges
            },
            decision_interval=DECISION_INTERVAL,
            traffic_rate=RATE,
            switch_penalty=get_switch_penalty(),
            gridlock_penalty=ADP_GRIDLOCK_PENALTY,
            action_scoring_mode=ADP_ACTION_SCORING_MODE,
            feature_set=ADP_FEATURE_SET,
            queue_priority_weight=ADP_QUEUE_PRIORITY_WEIGHT,
            total_queue_weight=ADP_TOTAL_QUEUE_WEIGHT,
            lane_fairness_weight=ADP_LANE_FAIRNESS_WEIGHT,
            lane_fairness_margin=ADP_LANE_FAIRNESS_MARGIN,
            residual_greedy_weight=ADP_RESIDUAL_GREEDY_WEIGHT,
            residual_pressure_weight=ADP_RESIDUAL_PRESSURE_WEIGHT,
            residual_value_weight=ADP_RESIDUAL_VALUE_WEIGHT,
            residual_lookahead_weight=ADP_RESIDUAL_LOOKAHEAD_WEIGHT,
            residual_downstream_penalty_weight=ADP_RESIDUAL_DOWNSTREAM_PENALTY_WEIGHT,
            lookahead_depth=ADP_LOOKAHEAD_DEPTH,
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
            incident_action_feature_count=(
                ADP_INCIDENT_ACTION_FEATURE_COUNT
                if ADP_INCIDENT_ACTION_FEATURES_ENABLED and ACTION_SPACE == "three_lane_8"
                else 0
            ),
            neighbor_feature_max_neighbors=(
                ADP_NEIGHBOR_FEATURE_MAX_NEIGHBORS if ALLOW_NEIGHBOR_INFO else 0
            ),
        )

    return agents


check_episode_status.gridlock_candidate_since = None
check_episode_status.success_candidate_since = None
check_episode_status.last_debug_time = -GRIDLOCK_DEBUG_INTERVAL
