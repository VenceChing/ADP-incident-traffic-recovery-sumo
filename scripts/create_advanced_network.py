from __future__ import annotations

import argparse
import math
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.actions import LEFT_TURN_DIRS, RIGHT_TURN_DIRS
from its_signal_control.scenario_validation import validate_three_lane_network

DEFAULT_OUTPUT_DIR = REPO_ROOT / "scenarios" / "advanced"
ROAD_SPEED = 13.89
SAMPLES_PER_SPAN = 7

Point = tuple[float, float]


@dataclass(frozen=True)
class Anchor:
    position: Point
    node_id: str | None = None


@dataclass(frozen=True)
class Corridor:
    name: str
    anchors: tuple[Anchor, ...]
    closed: bool = False


@dataclass(frozen=True)
class RoadSegment:
    corridor: str
    index: int
    source: str
    target: str
    shape: tuple[Point, ...]


def _ring_positions() -> dict[str, Point]:
    center_x, center_y = 1000.0, 850.0
    radius_x, radius_y = 700.0, 500.0
    rotation = math.radians(17.0)
    angles = [5, 36, 68, 100, 132, 163, 195, 225, 258, 290, 322, 348]
    scales = [1.02, 0.95, 1.06, 0.97, 1.04, 0.96, 1.05, 0.94, 1.03, 0.98, 1.04, 0.96]
    positions: dict[str, Point] = {}
    for index, (angle, scale) in enumerate(zip(angles, scales)):
        theta = math.radians(angle)
        local_x = radius_x * scale * math.cos(theta)
        local_y = radius_y * scale * math.sin(theta)
        x = center_x + local_x * math.cos(rotation) - local_y * math.sin(rotation)
        y = center_y + local_x * math.sin(rotation) + local_y * math.cos(rotation)
        positions[f"Q{index:02d}"] = (round(x, 2), round(y, 2))
    return positions


def _node_positions() -> dict[str, Point]:
    positions = _ring_positions()
    positions.update(
        {
            "C_AC": (720.0, 900.0),
            "C_AB": (1000.0, 900.0),
            "C_BC": (1200.0, 700.0),
            "XA_W": (-220.0, 610.0),
            "XA_E": (2180.0, 1110.0),
            "XB_N": (1240.0, 1940.0),
            "XB_S": (820.0, -220.0),
            "XC_NW": (120.0, 1880.0),
            "XC_SE": (1920.0, -160.0),
        }
    )
    for ring_index in (0, 1, 4, 6, 7, 10):
        node_id = f"Q{ring_index:02d}"
        normal = _ring_outward_normal(ring_index, positions)
        x, y = positions[node_id]
        positions[f"XS_{ring_index:02d}"] = (x + normal[0] * 760.0, y + normal[1] * 760.0)
    return positions


def _node(node_id: str, positions: dict[str, Point]) -> Anchor:
    return Anchor(positions[node_id], node_id)


def _point(x: float, y: float) -> Anchor:
    return Anchor((x, y))


def _ring_outward_normal(index: int, positions: dict[str, Point]) -> Point:
    previous = positions[f"Q{(index - 1) % 12:02d}"]
    following = positions[f"Q{(index + 1) % 12:02d}"]
    current = positions[f"Q{index:02d}"]
    tangent = (following[0] - previous[0], following[1] - previous[1])
    normal = (-tangent[1], tangent[0])
    if normal[0] * (current[0] - 1000.0) + normal[1] * (current[1] - 850.0) < 0.0:
        normal = (-normal[0], -normal[1])
    length = math.hypot(*normal)
    return normal[0] / length, normal[1] / length


def _spur_corridor(index: int, positions: dict[str, Point]) -> Corridor:
    node_id = f"Q{index:02d}"
    normal = _ring_outward_normal(index, positions)
    x, y = positions[node_id]
    return Corridor(
        f"spur_{index:02d}",
        (
            _node(node_id, positions),
            _point(x + normal[0] * 330.0, y + normal[1] * 330.0),
            _node(f"XS_{index:02d}", positions),
        ),
    )


def _build_corridors(positions: dict[str, Point]) -> list[Corridor]:
    ring = Corridor(
        "ring",
        tuple(_node(f"Q{index:02d}", positions) for index in range(12)),
        closed=True,
    )
    arterial_a = Corridor(
        "arterial_a",
        (
            _node("XA_W", positions),
            _point(60.0, 700.0),
            _node("Q05", positions),
            _node("C_AC", positions),
            _node("C_AB", positions),
            _node("Q11", positions),
            _point(1940.0, 1030.0),
            _node("XA_E", positions),
        ),
    )
    arterial_b = Corridor(
        "arterial_b",
        (
            _node("XB_N", positions),
            _point(1170.0, 1680.0),
            _node("Q02", positions),
            _node("C_AB", positions),
            _node("C_BC", positions),
            _node("Q08", positions),
            _point(930.0, 70.0),
            _node("XB_S", positions),
        ),
    )
    arterial_c = Corridor(
        "arterial_c",
        (
            _node("XC_NW", positions),
            _point(470.0, 1580.0),
            _node("Q03", positions),
            _point(720.0, 1080.0),
            _node("C_AC", positions),
            _point(720.0, 790.0),
            _point(990.0, 700.0),
            _node("C_BC", positions),
            _point(1390.0, 700.0),
            _node("Q09", positions),
            _point(1630.0, 150.0),
            _node("XC_SE", positions),
        ),
    )
    spurs = [_spur_corridor(index, positions) for index in (0, 1, 4, 6, 7, 10)]
    return [ring, arterial_a, arterial_b, arterial_c, *spurs]


def _distance(first: Point, second: Point) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _tangents(points: list[Point], closed: bool) -> list[Point]:
    tangents: list[Point] = []
    for index, current in enumerate(points):
        if closed:
            previous = points[(index - 1) % len(points)]
            following = points[(index + 1) % len(points)]
            tangents.append(((following[0] - previous[0]) * 0.45, (following[1] - previous[1]) * 0.45))
        elif index == 0:
            following = points[1]
            tangents.append(((following[0] - current[0]) * 0.75, (following[1] - current[1]) * 0.75))
        elif index == len(points) - 1:
            previous = points[-2]
            tangents.append(((current[0] - previous[0]) * 0.75, (current[1] - previous[1]) * 0.75))
        else:
            previous = points[index - 1]
            following = points[index + 1]
            tangents.append(((following[0] - previous[0]) * 0.45, (following[1] - previous[1]) * 0.45))
    return tangents


def _sample_span(start: Point, end: Point, start_tangent: Point, end_tangent: Point) -> list[Point]:
    points = []
    for step in range(SAMPLES_PER_SPAN + 1):
        t = step / SAMPLES_PER_SPAN
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        x = h00 * start[0] + h10 * start_tangent[0] + h01 * end[0] + h11 * end_tangent[0]
        y = h00 * start[1] + h10 * start_tangent[1] + h01 * end[1] + h11 * end_tangent[1]
        points.append((round(x, 2), round(y, 2)))
    return points


def _corridor_segments(corridor: Corridor) -> list[RoadSegment]:
    anchors = list(corridor.anchors)
    points = [anchor.position for anchor in anchors]
    tangents = _tangents(points, corridor.closed)
    segments: list[RoadSegment] = []

    if corridor.closed:
        if any(anchor.node_id is None for anchor in anchors):
            raise RuntimeError(f"Closed corridor {corridor.name} may not contain geometry-only anchors")
        for index, anchor in enumerate(anchors):
            next_index = (index + 1) % len(anchors)
            shape = _sample_span(points[index], points[next_index], tangents[index], tangents[next_index])
            segments.append(
                RoadSegment(
                    corridor.name,
                    index,
                    anchor.node_id or "",
                    anchors[next_index].node_id or "",
                    tuple(shape),
                )
            )
        return segments

    if anchors[0].node_id is None or anchors[-1].node_id is None:
        raise RuntimeError(f"Open corridor {corridor.name} must start and end at nodes")

    source = anchors[0].node_id
    current_shape: list[Point] = [points[0]]
    segment_index = 0
    for index in range(len(anchors) - 1):
        span = _sample_span(points[index], points[index + 1], tangents[index], tangents[index + 1])
        current_shape.extend(span[1:])
        target = anchors[index + 1].node_id
        if target is None:
            continue
        segments.append(RoadSegment(corridor.name, segment_index, source, target, tuple(current_shape)))
        source = target
        current_shape = [points[index + 1]]
        segment_index += 1
    return segments


def _build_segments(corridors: list[Corridor]) -> list[RoadSegment]:
    return [segment for corridor in corridors for segment in _corridor_segments(corridor)]


def _angle_between(first: Point, second: Point) -> float:
    first_length = math.hypot(*first)
    second_length = math.hypot(*second)
    cosine = (first[0] * second[0] + first[1] * second[1]) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _outward_vectors(segments: list[RoadSegment]) -> dict[str, list[Point]]:
    vectors: dict[str, list[Point]] = defaultdict(list)
    for segment in segments:
        start = segment.shape[0]
        after_start = segment.shape[1]
        before_end = segment.shape[-2]
        end = segment.shape[-1]
        vectors[segment.source].append((after_start[0] - start[0], after_start[1] - start[1]))
        vectors[segment.target].append((before_end[0] - end[0], before_end[1] - end[1]))
    return vectors


def _validate_junction_angles(traffic_nodes: set[str], segments: list[RoadSegment]) -> None:
    vectors = _outward_vectors(segments)
    issues: list[str] = []
    for node_id in sorted(traffic_nodes):
        node_vectors = vectors[node_id]
        if len(node_vectors) == 3:
            pairs = list(combinations(range(3), 2))
            straight_pair = max(pairs, key=lambda pair: _angle_between(node_vectors[pair[0]], node_vectors[pair[1]]))
            straight_angle = _angle_between(node_vectors[straight_pair[0]], node_vectors[straight_pair[1]])
            branch = next(index for index in range(3) if index not in straight_pair)
            branch_angles = [
                _angle_between(node_vectors[branch], node_vectors[straight_pair[0]]),
                _angle_between(node_vectors[branch], node_vectors[straight_pair[1]]),
            ]
            if straight_angle < 150.0 or min(branch_angles) < 45.0:
                issues.append(
                    f"{node_id} is not T-shaped: straight={straight_angle:.1f}, branches={branch_angles}"
                )
        elif len(node_vectors) == 4:
            pairings = [
                ((0, 1), (2, 3)),
                ((0, 2), (1, 3)),
                ((0, 3), (1, 2)),
            ]
            pairing = min(
                pairings,
                key=lambda pairs: sum(
                    abs(180.0 - _angle_between(node_vectors[first], node_vectors[second]))
                    for first, second in pairs
                ),
            )
            opposite_angles = [
                _angle_between(node_vectors[first], node_vectors[second]) for first, second in pairing
            ]
            axis_angle = _angle_between(node_vectors[pairing[0][0]], node_vectors[pairing[1][0]])
            crossing_angle = min(axis_angle, 180.0 - axis_angle)
            if min(opposite_angles) < 150.0 or crossing_angle < 45.0:
                issues.append(
                    f"{node_id} is not cross-shaped: opposite={opposite_angles}, crossing={crossing_angle:.1f}"
                )
    if issues:
        raise RuntimeError("Invalid junction geometry:\n" + "\n".join(issues))


def _orientation(first: Point, second: Point, third: Point) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )


def _strictly_crosses(first: Point, second: Point, third: Point, fourth: Point) -> bool:
    return (
        _orientation(first, second, third) * _orientation(first, second, fourth) < -1e-7
        and _orientation(third, fourth, first) * _orientation(third, fourth, second) < -1e-7
    )


def _validate_no_unplanned_crossings(segments: list[RoadSegment]) -> None:
    crossings: list[str] = []
    for first, second in combinations(segments, 2):
        for first_start, first_end in zip(first.shape, first.shape[1:]):
            for second_start, second_end in zip(second.shape, second.shape[1:]):
                if _strictly_crosses(first_start, first_end, second_start, second_end):
                    crossings.append(
                        f"{first.corridor}:{first.source}->{first.target} crosses "
                        f"{second.corridor}:{second.source}->{second.target}"
                    )
                    break
            if crossings and crossings[-1].startswith(f"{first.corridor}:{first.source}->{first.target}"):
                break
    if crossings:
        raise RuntimeError("Roads cross outside declared junctions:\n" + "\n".join(crossings[:20]))


def _validate_topology(positions: dict[str, Point], segments: list[RoadSegment]) -> set[str]:
    degree: Counter[str] = Counter()
    neighbors: dict[str, set[str]] = defaultdict(set)
    for segment in segments:
        degree[segment.source] += 1
        degree[segment.target] += 1
        neighbors[segment.source].add(segment.target)
        neighbors[segment.target].add(segment.source)
        if _distance(segment.shape[0], segment.shape[-1]) < 90.0:
            raise RuntimeError(f"Road segment {segment.source}->{segment.target} is too short")

    traffic_nodes = {node_id for node_id in positions if not node_id.startswith("X")}
    invalid_traffic = {node_id: degree[node_id] for node_id in traffic_nodes if degree[node_id] not in {3, 4}}
    invalid_boundary = {
        node_id: degree[node_id] for node_id in positions if node_id.startswith("X") and degree[node_id] != 1
    }
    if invalid_traffic or invalid_boundary:
        raise RuntimeError(
            f"Invalid node degrees; traffic={invalid_traffic}, boundary={invalid_boundary}"
        )

    start = next(iter(positions))
    reached = {start}
    queue = deque([start])
    while queue:
        node_id = queue.popleft()
        for neighbor in neighbors[node_id]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    if reached != set(positions):
        raise RuntimeError(f"Road network is disconnected; missing={sorted(set(positions) - reached)}")

    _validate_junction_angles(traffic_nodes, segments)
    _validate_no_unplanned_crossings(segments)
    return traffic_nodes


def _shape_text(points: tuple[Point, ...]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _write_nodes(path: Path, positions: dict[str, Point], traffic_nodes: set[str]) -> None:
    root = ET.Element("nodes")
    for node_id, (x, y) in sorted(positions.items()):
        node_type = "traffic_light" if node_id in traffic_nodes else "priority"
        ET.SubElement(root, "node", id=node_id, x=f"{x:.2f}", y=f"{y:.2f}", type=node_type)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _write_edges(path: Path, segments: list[RoadSegment], lane_count: int) -> None:
    root = ET.Element("edges")
    for segment in segments:
        attributes = {
            "numLanes": str(lane_count),
            "speed": f"{ROAD_SPEED:.2f}",
            "priority": "3",
        }
        edge_id = f"{segment.source}_{segment.target}"
        ET.SubElement(
            root,
            "edge",
            id=edge_id,
            **{
                "from": segment.source,
                "to": segment.target,
                "shape": _shape_text(segment.shape),
                **attributes,
            },
        )
        ET.SubElement(
            root,
            "edge",
            id=f"{segment.target}_{segment.source}",
            **{
                "from": segment.target,
                "to": segment.source,
                "shape": _shape_text(tuple(reversed(segment.shape))),
                **attributes,
            },
        )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _turn_lane(turn_direction: str) -> str:
    normalized = turn_direction.lower()
    if normalized in RIGHT_TURN_DIRS:
        return "0"
    if normalized in LEFT_TURN_DIRS:
        return "2"
    return "1"


def _write_connections(path: Path, preliminary_net: Path) -> None:
    root = ET.Element("connections")
    preliminary_root = ET.parse(preliminary_net).getroot()
    seen: set[tuple[str, str]] = set()
    for connection in preliminary_root.findall("connection"):
        source = connection.get("from", "")
        target = connection.get("to", "")
        if source.startswith(":") or target.startswith(":"):
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        lane = _turn_lane(connection.get("dir", "s"))
        ET.SubElement(
            root,
            "connection",
            **{"from": source, "to": target, "fromLane": lane, "toLane": lane},
        )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _run_netconvert(nodes: Path, edges: Path, output: Path, connections: Path | None = None) -> None:
    command = [
        "netconvert",
        "--node-files",
        str(nodes),
        "--edge-files",
        str(edges),
        "--output-file",
        str(output),
        "--no-turnarounds",
        "true",
        "--junctions.limit-turn-speed",
        "5.50",
        "--no-warnings",
    ]
    if connections is not None:
        command.extend(["--connection-files", str(connections)])
    subprocess.run(command, check=True)


def create_advanced_network(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    plain_dir = output_dir / "plain"
    plain_dir.mkdir(parents=True, exist_ok=True)

    positions = _node_positions()
    corridors = _build_corridors(positions)
    segments = _build_segments(corridors)
    traffic_nodes = _validate_topology(positions, segments)

    node_path = plain_dir / "advanced.nod.xml"
    edge_path = plain_dir / "advanced.edg.xml"
    connection_path = plain_dir / "advanced.con.xml"
    output_path = output_dir / "advanced.net.xml"

    _write_nodes(node_path, positions, traffic_nodes)
    _write_edges(edge_path, segments, lane_count=3)

    with tempfile.TemporaryDirectory(prefix="advanced_net_") as temp_name:
        temp_dir = Path(temp_name)
        preliminary_edges = temp_dir / "advanced_1lane.edg.xml"
        preliminary_net = temp_dir / "advanced_1lane.net.xml"
        _write_edges(preliminary_edges, segments, lane_count=1)
        _run_netconvert(node_path, preliminary_edges, preliminary_net)
        _write_connections(connection_path, preliminary_net)

    _run_netconvert(node_path, edge_path, output_path, connection_path)

    issues = validate_three_lane_network(output_path)
    if issues:
        raise RuntimeError("Generated network failed three-lane validation:\n" + "\n".join(issues[:30]))
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an organic, non-grid three-lane SUMO network.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    output_path = create_advanced_network(args.output_dir)
    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
