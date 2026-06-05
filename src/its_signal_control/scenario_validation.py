from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .approaches import assign_cardinal_approaches
from .actions import (
    LEFT_TURN_DIRS,
    RIGHT_TURN_DIRS,
    action_matches,
    get_action_definitions,
    movement_group_for_connection,
)


def _normal_edge(edge: ET.Element) -> bool:
    edge_id = edge.get("id", "")
    return not edge_id.startswith(":") and edge.get("function") != "internal"


def _lane_shapes(root: ET.Element) -> dict[str, str]:
    shapes: dict[str, str] = {}
    for edge in root.findall("edge"):
        for lane in edge.findall("lane"):
            lane_id = lane.get("id")
            shape = lane.get("shape")
            if lane_id and shape:
                shapes[lane_id] = shape
    return shapes


def _lane_vector(lane_id: str, lane_shapes: dict[str, str]) -> tuple[float, float] | None:
    shape = lane_shapes.get(lane_id)
    if not shape:
        return None
    points = []
    for point in shape.split():
        x_text, y_text = point.split(",")[:2]
        points.append((float(x_text), float(y_text)))
    if len(points) < 2:
        return None
    x1, y1 = points[0]
    x2, y2 = points[-1]
    return x1 - x2, y1 - y2


def _tls_approach_maps(root: ET.Element, lane_shapes: dict[str, str]) -> dict[str, dict[str, str]]:
    tls_vectors: dict[str, dict[str, tuple[float, float]]] = {}
    for connection in root.findall("connection"):
        from_edge = connection.get("from", "")
        from_lane_index = connection.get("fromLane")
        tls_id = connection.get("tl")
        if not tls_id or from_edge.startswith(":") or from_lane_index is None:
            continue
        vector = _lane_vector(f"{from_edge}_{from_lane_index}", lane_shapes)
        if vector is not None:
            tls_vectors.setdefault(tls_id, {}).setdefault(from_edge, vector)
    return {tls_id: assign_cardinal_approaches(vectors) for tls_id, vectors in tls_vectors.items()}


def _has_conflict(requests: dict[int, str], first: int, second: int) -> bool:
    def bit_is_set(bits: str, index: int) -> bool:
        if index >= len(bits):
            return False
        return bits[-1 - index] == "1"

    return bit_is_set(requests.get(first, ""), second) or bit_is_set(requests.get(second, ""), first)


def _expected_lane_for_turn(turn_dir: str | None, action_space: str) -> str:
    if action_space == "three_lane_8":
        if turn_dir in RIGHT_TURN_DIRS:
            return "0"
        if turn_dir in LEFT_TURN_DIRS:
            return "2"
        return "1"
    return "1" if turn_dir in LEFT_TURN_DIRS else "0"


def validate_movement_lane_network(
    net_path: str | Path,
    *,
    expected_lane_count: int,
    action_space: str,
) -> list[str]:
    root = ET.parse(net_path).getroot()
    issues: list[str] = []
    lane_shapes = _lane_shapes(root)
    tls_approach_maps = _tls_approach_maps(root, lane_shapes)

    for edge in root.findall("edge"):
        if not _normal_edge(edge):
            continue
        lanes = edge.findall("lane")
        if len(lanes) != expected_lane_count:
            issues.append(f"edge {edge.get('id')} has {len(lanes)} lanes, expected {expected_lane_count}")

    tl_connections: dict[str, list[dict[str, object]]] = {}
    for connection in root.findall("connection"):
        from_edge = connection.get("from", "")
        if from_edge.startswith(":"):
            continue
        turn_dir = connection.get("dir")
        from_lane_index = connection.get("fromLane")
        expected_lane = _expected_lane_for_turn(turn_dir, action_space)
        if from_lane_index != expected_lane:
            issues.append(
                f"connection {connection.get('from')}->{connection.get('to')} dir={turn_dir} "
                f"uses fromLane={from_lane_index}, expected {expected_lane}"
            )

        tls_id = connection.get("tl")
        link_index = connection.get("linkIndex")
        if not tls_id or link_index is None:
            continue
        from_lane = f"{connection.get('from')}_{from_lane_index}"
        approach = tls_approach_maps.get(tls_id, {}).get(from_edge)
        movement = movement_group_for_connection(from_lane, turn_dir, action_space=action_space)
        tl_connections.setdefault(tls_id, []).append(
            {
                "link_index": int(link_index),
                "approach": approach,
                "movement": movement,
            }
        )

    junction_requests: dict[str, dict[int, str]] = {}
    for junction in root.findall("junction"):
        junction_id = junction.get("id")
        if not junction_id:
            continue
        requests = {
            int(request.get("index")): request.get("foes", "")
            for request in junction.findall("request")
            if request.get("index") is not None
        }
        if requests:
            junction_requests[junction_id] = requests

    action_definitions = get_action_definitions(action_space)
    for tls_id, connections in tl_connections.items():
        requests = junction_requests.get(tls_id, {})
        for action in action_definitions:
            link_indices = [
                int(connection["link_index"])
                for connection in connections
                if action_matches(
                    action,
                    connection.get("approach"),  # type: ignore[arg-type]
                    connection.get("movement"),  # type: ignore[arg-type]
                )
            ]
            for pos, first in enumerate(link_indices):
                for second in link_indices[pos + 1 :]:
                    if _has_conflict(requests, first, second):
                        issues.append(
                            f"traffic light {tls_id} action {action.name} has conflicting links "
                            f"{first} and {second}"
                        )

    return issues


def validate_two_lane_network(net_path: str | Path, action_space: str = "two_lane_8") -> list[str]:
    return validate_movement_lane_network(
        net_path,
        expected_lane_count=2,
        action_space=action_space,
    )


def validate_three_lane_network(net_path: str | Path, action_space: str = "three_lane_8") -> list[str]:
    return validate_movement_lane_network(
        net_path,
        expected_lane_count=3,
        action_space=action_space,
    )
