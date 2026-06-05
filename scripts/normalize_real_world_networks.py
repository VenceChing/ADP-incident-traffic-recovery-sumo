from __future__ import annotations

import argparse
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ROAD_SPEED = 13.89
CLUSTER_DISTANCE = 36.0
SCALE_FACTOR = 3.0
RESAMPLE_POINTS = 13
PRESERVED_CLEARANCE = 42.0
MIN_PRESERVED_LENGTH = 3.0

Point = tuple[float, float]


@dataclass
class SourceRoad:
    source: str
    target: str
    shape: list[Point]


@dataclass
class Road:
    source: str
    target: str
    shape: list[Point]


@dataclass
class PreservedEdge:
    source: str
    target: str
    shape: list[Point]
    lane_count: int
    speed: float
    allow: str | None
    disallow: str | None


class DisjointSet:
    def __init__(self, values: set[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: str, second: str) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[second_root] = first_root


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return cleaned if cleaned and not cleaned[0].isdigit() else f"N_{cleaned}"


def _point_text(points: list[Point]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _parse_shape(shape: str) -> list[Point]:
    points = []
    for item in shape.split():
        x_text, y_text = item.split(",")[:2]
        points.append((float(x_text), float(y_text)))
    return points


def _distance(first: Point, second: Point) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _road_length(points: list[Point]) -> float:
    return sum(_distance(first, second) for first, second in zip(points, points[1:]))


def _normal_edge(edge: ET.Element) -> bool:
    edge_id = edge.get("id", "")
    return not edge_id.startswith(":") and edge.get("function") != "internal"


def _allows_passenger(edge: ET.Element) -> bool:
    for lane in edge.findall("lane"):
        allow = set((lane.get("allow") or "").split())
        disallow = set((lane.get("disallow") or "").split())
        if allow:
            if "passenger" in allow or "private" in allow:
                return True
        elif "passenger" not in disallow and "all" not in disallow:
            return True
    return False


def _edge_shape(edge: ET.Element, node_positions: dict[str, Point]) -> list[Point]:
    lane = edge.find("lane")
    if lane is not None and lane.get("shape"):
        return _parse_shape(lane.get("shape", ""))
    return [node_positions[edge.get("from", "")], node_positions[edge.get("to", "")]]


def _read_source(net_path: Path) -> tuple[dict[str, Point], list[SourceRoad], list[PreservedEdge]]:
    root = ET.parse(net_path).getroot()
    node_positions: dict[str, Point] = {}
    for junction in root.findall("junction"):
        node_id = junction.get("id")
        if node_id and not node_id.startswith(":"):
            node_positions[node_id] = (float(junction.get("x", "0")), float(junction.get("y", "0")))

    usable_pairs: dict[frozenset[str], SourceRoad] = {}
    preserved: list[PreservedEdge] = []
    for edge in root.findall("edge"):
        if not _normal_edge(edge):
            continue
        source = edge.get("from", "")
        target = edge.get("to", "")
        if not source or not target or source == target or source not in node_positions or target not in node_positions:
            continue
        shape = _edge_shape(edge, node_positions)
        if len(shape) < 2 or _distance(shape[0], shape[-1]) < 0.05:
            continue
        if _allows_passenger(edge):
            if _distance(shape[0], shape[-1]) < 1.0:
                continue
            key = frozenset((source, target))
            if key not in usable_pairs or _road_length(shape) > _road_length(usable_pairs[key].shape):
                usable_pairs[key] = SourceRoad(source, target, shape)
            continue

        lane = edge.find("lane")
        preserved.append(
            PreservedEdge(
                source=source,
                target=target,
                shape=shape,
                lane_count=max(1, len(edge.findall("lane"))),
                speed=float(lane.get("speed", "5.0")) if lane is not None else 5.0,
                allow=lane.get("allow") if lane is not None and lane.get("allow") else None,
                disallow=lane.get("disallow") if lane is not None and lane.get("disallow") else "passenger",
            )
        )
    return node_positions, list(usable_pairs.values()), preserved


def _adjacency(roads: list[SourceRoad] | list[Road]) -> dict[str, list[tuple[str, int]]]:
    adjacency: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for index, road in enumerate(roads):
        adjacency[road.source].append((road.target, index))
        adjacency[road.target].append((road.source, index))
    return adjacency


def _oriented_source_shape(road: SourceRoad, source: str, target: str) -> list[Point]:
    if road.source == source and road.target == target:
        return list(road.shape)
    if road.source == target and road.target == source:
        return list(reversed(road.shape))
    raise ValueError(f"{road.source}->{road.target} does not connect {source}->{target}")


def _append_shape(shape: list[Point], addition: list[Point]) -> None:
    if not shape:
        shape.extend(addition)
    elif shape[-1] == addition[0]:
        shape.extend(addition[1:])
    else:
        shape.extend(addition)


def _collapse_source_degree_two(roads: list[SourceRoad]) -> list[SourceRoad]:
    adjacency = _adjacency(roads)
    significant = {node_id for node_id, edges in adjacency.items() if len(edges) != 2}
    if not significant and adjacency:
        significant.add(next(iter(adjacency)))

    collapsed: list[SourceRoad] = []
    visited: set[int] = set()
    for start in sorted(significant):
        for next_node, road_index in adjacency[start]:
            if road_index in visited:
                continue
            current = start
            following = next_node
            shape: list[Point] = []
            while True:
                visited.add(road_index)
                _append_shape(shape, _oriented_source_shape(roads[road_index], current, following))
                if following in significant:
                    collapsed.append(SourceRoad(start, following, shape))
                    break
                candidates = [(node, index) for node, index in adjacency[following] if index != road_index]
                if not candidates:
                    collapsed.append(SourceRoad(start, following, shape))
                    break
                current, following, road_index = following, candidates[0][0], candidates[0][1]
                if road_index in visited:
                    break
    return collapsed


def _cluster_nodes(roads: list[SourceRoad], node_positions: dict[str, Point]) -> tuple[dict[str, str], dict[str, Point]]:
    road_nodes = {road.source for road in roads} | {road.target for road in roads}
    dsu = DisjointSet(road_nodes)
    nodes = sorted(road_nodes)
    for index, first in enumerate(nodes):
        first_pos = node_positions[first]
        for second in nodes[index + 1 :]:
            if _distance(first_pos, node_positions[second]) <= CLUSTER_DISTANCE:
                dsu.union(first, second)

    clusters: dict[str, list[str]] = defaultdict(list)
    for node_id in nodes:
        clusters[dsu.find(node_id)].append(node_id)

    node_to_cluster: dict[str, str] = {}
    cluster_positions: dict[str, Point] = {}
    for ordinal, members in enumerate(sorted(clusters.values(), key=lambda group: sorted(group)[0])):
        cluster_id = _safe_id(members[0]) if len(members) == 1 else f"CL_{ordinal:04d}_{_safe_id(members[0])}"
        x = sum(node_positions[member][0] for member in members) / len(members)
        y = sum(node_positions[member][1] for member in members) / len(members)
        cluster_positions[cluster_id] = (x, y)
        for member in members:
            node_to_cluster[member] = cluster_id
    return node_to_cluster, cluster_positions


def _resample(points: list[Point], count: int = RESAMPLE_POINTS) -> list[Point]:
    if len(points) <= 1:
        return points
    total = _road_length(points)
    if total <= 0.0:
        return [points[0] for _ in range(count)]
    samples: list[Point] = []
    distances = [0.0]
    for first, second in zip(points, points[1:]):
        distances.append(distances[-1] + _distance(first, second))
    for sample_index in range(count):
        target = total * sample_index / (count - 1)
        segment_index = 0
        while segment_index + 1 < len(distances) and distances[segment_index + 1] < target:
            segment_index += 1
        start = points[segment_index]
        end = points[min(segment_index + 1, len(points) - 1)]
        span = max(1e-9, distances[min(segment_index + 1, len(distances) - 1)] - distances[segment_index])
        ratio = (target - distances[segment_index]) / span
        samples.append((start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio))
    return samples


def _average_centerline(shapes: list[list[Point]], source_pos: Point, target_pos: Point) -> list[Point]:
    if len(shapes) == 1:
        shape = list(shapes[0])
        shape[0] = source_pos
        shape[-1] = target_pos
        return shape

    samples = [_resample(shape) for shape in shapes]
    averaged: list[Point] = []
    for index in range(RESAMPLE_POINTS):
        x = sum(sample[index][0] for sample in samples) / len(samples)
        y = sum(sample[index][1] for sample in samples) / len(samples)
        averaged.append((x, y))
    averaged[0] = source_pos
    averaged[-1] = target_pos
    return averaged


def _merge_parallel_roads(
    roads: list[SourceRoad],
    node_to_cluster: dict[str, str],
    cluster_positions: dict[str, Point],
) -> list[Road]:
    groups: dict[tuple[str, str], list[list[Point]]] = defaultdict(list)
    for road in roads:
        source = node_to_cluster[road.source]
        target = node_to_cluster[road.target]
        if source == target:
            continue
        first, second = sorted((source, target))
        shape = list(road.shape) if source == first else list(reversed(road.shape))
        groups[(first, second)].append(shape)

    merged: list[Road] = []
    for (source, target), shapes in sorted(groups.items()):
        merged.append(
            Road(
                source,
                target,
                _average_centerline(shapes, cluster_positions[source], cluster_positions[target]),
            )
        )
    return merged


def _oriented_road_shape(road: Road, source: str, target: str) -> list[Point]:
    if road.source == source and road.target == target:
        return list(road.shape)
    if road.source == target and road.target == source:
        return list(reversed(road.shape))
    raise ValueError(f"{road.source}->{road.target} does not connect {source}->{target}")


def _merge_duplicate_roads(roads: list[Road], positions: dict[str, Point]) -> list[Road]:
    groups: dict[tuple[str, str], list[list[Point]]] = defaultdict(list)
    for road in roads:
        if road.source == road.target:
            continue
        source, target = sorted((road.source, road.target))
        groups[(source, target)].append(_oriented_road_shape(road, source, target))
    return [
        Road(source, target, _average_centerline(shapes, positions[source], positions[target]))
        for (source, target), shapes in sorted(groups.items())
    ]


def _collapse_road_degree_two(roads: list[Road], positions: dict[str, Point]) -> tuple[list[Road], dict[str, Point]]:
    changed = True
    roads = list(roads)
    positions = dict(positions)
    while changed:
        changed = False
        adjacency = _adjacency(roads)
        candidates = sorted(node for node, incident in adjacency.items() if len(incident) == 2)
        if not candidates:
            break
        node = candidates[0]
        first_neighbor, first_index = adjacency[node][0]
        second_neighbor, second_index = adjacency[node][1]
        first = roads[first_index]
        second = roads[second_index]
        if first_neighbor == second_neighbor:
            roads = [road for index, road in enumerate(roads) if index not in {first_index, second_index}]
        else:
            shape = _oriented_road_shape(first, first_neighbor, node)
            _append_shape(shape, _oriented_road_shape(second, node, second_neighbor))
            replacement = Road(first_neighbor, second_neighbor, shape)
            roads = [road for index, road in enumerate(roads) if index not in {first_index, second_index}]
            roads.append(replacement)
        positions.pop(node, None)
        roads = _merge_duplicate_roads(roads, positions)
        changed = True
    used = {road.source for road in roads} | {road.target for road in roads}
    return roads, {node: position for node, position in positions.items() if node in used}


def _angle_between(first: Point, second: Point) -> float:
    first_len = math.hypot(*first)
    second_len = math.hypot(*second)
    if first_len == 0.0 or second_len == 0.0:
        return 0.0
    cosine = (first[0] * second[0] + first[1] * second[1]) / (first_len * second_len)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _incident_vector(road: Road, node: str) -> Point:
    shape = _oriented_road_shape(road, node, road.target if road.source == node else road.source)
    return shape[1][0] - shape[0][0], shape[1][1] - shape[0][1]


def _prune_high_degree_roads(roads: list[Road], positions: dict[str, Point]) -> tuple[list[Road], dict[str, Point]]:
    roads = list(roads)
    positions = dict(positions)
    while True:
        adjacency = _adjacency(roads)
        high_nodes = sorted(node for node, incident in adjacency.items() if len(incident) > 4)
        if not high_nodes:
            return _collapse_road_degree_two(roads, positions)
        node = high_nodes[0]
        incident = adjacency[node]
        candidates = []
        for neighbor, index in incident:
            vector = _incident_vector(roads[index], node)
            candidates.append((index, vector, _road_length(roads[index].shape)))
        candidates.sort(key=lambda item: item[2], reverse=True)

        keep: list[tuple[int, Point, float]] = []
        for candidate in candidates:
            if len(keep) >= 4:
                break
            if all(_angle_between(candidate[1], kept[1]) >= 25.0 for kept in keep):
                keep.append(candidate)
        for candidate in candidates:
            if len(keep) >= 4:
                break
            if candidate not in keep:
                keep.append(candidate)
        keep_indices = {index for index, _, _ in keep}
        roads = [road for index, road in enumerate(roads) if index not in {item[0] for item in candidates} or index in keep_indices]
        roads, positions = _collapse_road_degree_two(roads, positions)
        roads = _merge_duplicate_roads(roads, positions)


def _scale_point(point: Point, min_x: float, min_y: float, scale: float) -> Point:
    return ((point[0] - min_x) * scale, (point[1] - min_y) * scale)


def _scale_all(
    positions: dict[str, Point],
    roads: list[Road],
    preserved: list[PreservedEdge],
    scale: float,
) -> tuple[dict[str, Point], list[Road], list[PreservedEdge]]:
    all_points = list(positions.values())
    for road in roads:
        all_points.extend(road.shape)
    for edge in preserved:
        all_points.extend(edge.shape)
    min_x = min(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)

    scaled_positions = {node: _scale_point(point, min_x, min_y, scale) for node, point in positions.items()}
    scaled_roads = [
        Road(road.source, road.target, [_scale_point(point, min_x, min_y, scale) for point in road.shape])
        for road in roads
    ]
    scaled_preserved = [
        PreservedEdge(
            edge.source,
            edge.target,
            [_scale_point(point, min_x, min_y, scale) for point in edge.shape],
            edge.lane_count,
            edge.speed,
            edge.allow,
            edge.disallow,
        )
        for edge in preserved
    ]
    return scaled_positions, scaled_roads, scaled_preserved


def _move_endpoint_outside_clearance(point: Point, next_point: Point, usable_positions: dict[str, Point]) -> Point:
    if not usable_positions:
        return point
    nearest = min(usable_positions.values(), key=lambda position: _distance(point, position))
    distance = _distance(point, nearest)
    if distance >= PRESERVED_CLEARANCE:
        return point

    direction_x = point[0] - nearest[0]
    direction_y = point[1] - nearest[1]
    direction_length = math.hypot(direction_x, direction_y)
    if direction_length < 1e-6:
        direction_x = point[0] - next_point[0]
        direction_y = point[1] - next_point[1]
        direction_length = math.hypot(direction_x, direction_y)
    if direction_length < 1e-6:
        direction_x, direction_y, direction_length = 1.0, 0.0, 1.0

    ratio = PRESERVED_CLEARANCE / direction_length
    return nearest[0] + direction_x * ratio, nearest[1] + direction_y * ratio


def _prepare_preserved_edges(
    preserved_edges: list[PreservedEdge],
    usable_positions: dict[str, Point],
) -> tuple[dict[str, Point], list[PreservedEdge]]:
    preserved_positions: dict[str, Point] = {}
    prepared_edges: list[PreservedEdge] = []
    for index, edge in enumerate(preserved_edges):
        shape = list(edge.shape)
        if len(shape) < 2:
            continue
        shape[0] = _move_endpoint_outside_clearance(shape[0], shape[1], usable_positions)
        shape[-1] = _move_endpoint_outside_clearance(shape[-1], shape[-2], usable_positions)
        if _road_length(shape) < MIN_PRESERVED_LENGTH:
            continue
        source = f"U{index:05d}_from"
        target = f"U{index:05d}_to"
        preserved_positions[source] = shape[0]
        preserved_positions[target] = shape[-1]
        prepared_edges.append(
            PreservedEdge(
                source=source,
                target=target,
                shape=shape,
                lane_count=edge.lane_count,
                speed=edge.speed,
                allow=edge.allow,
                disallow=edge.disallow,
            )
        )
    return preserved_positions, prepared_edges


def _build_normalized_roads(
    node_positions: dict[str, Point],
    usable_roads: list[SourceRoad],
) -> tuple[dict[str, Point], list[Road]]:
    collapsed = _collapse_source_degree_two(usable_roads)
    node_to_cluster, cluster_positions = _cluster_nodes(collapsed, node_positions)
    roads = _merge_parallel_roads(collapsed, node_to_cluster, cluster_positions)
    roads, cluster_positions = _collapse_road_degree_two(roads, cluster_positions)
    roads, cluster_positions = _prune_high_degree_roads(roads, cluster_positions)
    return cluster_positions, roads


def _write_nodes(
    path: Path,
    usable_positions: dict[str, Point],
    usable_roads: list[Road],
    preserved_positions: dict[str, Point],
) -> None:
    root = ET.Element("nodes")
    degree: Counter[str] = Counter()
    for road in usable_roads:
        degree[road.source] += 1
        degree[road.target] += 1

    for node_id, (x, y) in sorted(usable_positions.items()):
        node_type = "traffic_light" if degree[node_id] in {3, 4} else "priority"
        ET.SubElement(root, "node", id=node_id, x=f"{x:.2f}", y=f"{y:.2f}", type=node_type)
    for node_id, (x, y) in sorted(preserved_positions.items()):
        if node_id in usable_positions:
            continue
        ET.SubElement(root, "node", id=node_id, x=f"{x:.2f}", y=f"{y:.2f}", type="unregulated")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _write_edges(
    path: Path,
    usable_roads: list[Road],
    preserved_edges: list[PreservedEdge],
) -> set[str]:
    root = ET.Element("edges")
    usable_edge_ids: set[str] = set()
    for index, road in enumerate(usable_roads):
        edge_id = f"R{index:05d}_{road.source}_{road.target}"
        reverse_id = f"R{index:05d}_{road.target}_{road.source}"
        attributes = {"priority": "3", "numLanes": "3", "speed": f"{ROAD_SPEED:.2f}"}
        ET.SubElement(
            root,
            "edge",
            id=edge_id,
            **{"from": road.source, "to": road.target, "shape": _point_text(road.shape), **attributes},
        )
        ET.SubElement(
            root,
            "edge",
            id=reverse_id,
            **{
                "from": road.target,
                "to": road.source,
                "shape": _point_text(list(reversed(road.shape))),
                **attributes,
            },
        )
        usable_edge_ids.update({edge_id, reverse_id})

    for index, edge in enumerate(preserved_edges):
        attrs = {
            "from": edge.source,
            "to": edge.target,
            "shape": _point_text(edge.shape),
            "priority": "1",
            "numLanes": str(edge.lane_count),
            "speed": f"{edge.speed:.2f}",
        }
        if edge.allow:
            attrs["allow"] = edge.allow
        elif edge.disallow:
            attrs["disallow"] = edge.disallow
        ET.SubElement(root, "edge", id=f"U{index:05d}_{edge.source}_{edge.target}", **attrs)

    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return usable_edge_ids


def _turn_lane(turn_direction: str | None) -> str:
    if turn_direction in {"r", "R"}:
        return "0"
    if turn_direction in {"l", "L", "t"}:
        return "2"
    return "1"


def _write_connections(path: Path, preliminary_net: Path, usable_edge_ids: set[str]) -> None:
    root = ET.Element("connections")
    preliminary_root = ET.parse(preliminary_net).getroot()
    seen: set[tuple[str, str]] = set()
    for connection in preliminary_root.findall("connection"):
        source = connection.get("from", "")
        target = connection.get("to", "")
        if source.startswith(":") or target.startswith(":"):
            continue
        if source not in usable_edge_ids or target not in usable_edge_ids:
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        lane = _turn_lane(connection.get("dir"))
        ET.SubElement(root, "connection", **{"from": source, "to": target, "fromLane": lane, "toLane": lane})
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


def _validate_usable_structure(net_path: Path) -> list[str]:
    root = ET.parse(net_path).getroot()
    issues: list[str] = []
    usable_edges = [
        edge
        for edge in root.findall("edge")
        if edge.get("id", "").startswith("R") and edge.get("function") != "internal"
    ]
    directed_pairs = {(edge.get("from", ""), edge.get("to", "")) for edge in usable_edges}
    for edge in usable_edges:
        if len(edge.findall("lane")) != 3:
            issues.append(f"{edge.get('id')} has {len(edge.findall('lane'))} lanes")
        source = edge.get("from", "")
        target = edge.get("to", "")
        if (target, source) not in directed_pairs:
            issues.append(f"{edge.get('id')} has no reverse edge")

    degree: Counter[str] = Counter()
    for source, target in {tuple(sorted(pair)) for pair in directed_pairs}:
        degree[source] += 1
        degree[target] += 1
    for node_id, node_degree in degree.items():
        if node_degree not in {1, 3, 4}:
            issues.append(f"usable node {node_id} has degree {node_degree}")
    for junction in root.findall("junction"):
        node_id = junction.get("id", "")
        if node_id in degree and degree[node_id] in {3, 4} and junction.get("type") != "traffic_light":
            issues.append(f"usable intersection {node_id} is {junction.get('type')}, expected traffic_light")
    return issues


def normalize_network(source_net: Path, output_net: Path, *, preserve_unusable: bool, scale: float) -> Path:
    output_net.parent.mkdir(parents=True, exist_ok=True)
    plain_dir = output_net.parent / f"{output_net.stem}.plain"
    plain_dir.mkdir(parents=True, exist_ok=True)

    node_positions, usable_source_roads, preserved_edges = _read_source(source_net)
    usable_positions, usable_roads = _build_normalized_roads(node_positions, usable_source_roads)
    if not preserve_unusable:
        preserved_edges = []

    all_positions = dict(usable_positions)
    scaled_positions, scaled_roads, scaled_preserved = _scale_all(
        all_positions,
        usable_roads,
        preserved_edges,
        scale,
    )
    scaled_usable_positions = {node_id: scaled_positions[node_id] for node_id in usable_positions}
    scaled_preserved_positions, scaled_preserved = _prepare_preserved_edges(
        scaled_preserved,
        scaled_usable_positions,
    )

    node_path = plain_dir / f"{output_net.stem}.nod.xml"
    edge_path = plain_dir / f"{output_net.stem}.edg.xml"
    connection_path = plain_dir / f"{output_net.stem}.con.xml"
    _write_nodes(node_path, scaled_usable_positions, scaled_roads, scaled_preserved_positions)
    usable_edge_ids = _write_edges(edge_path, scaled_roads, scaled_preserved)

    with tempfile.TemporaryDirectory(prefix="real_world_norm_") as temp_name:
        temp_dir = Path(temp_name)
        preliminary_edges = temp_dir / "norm_1lane.edg.xml"
        preliminary_net = temp_dir / "norm_1lane.net.xml"
        preliminary_ids = _write_edges(preliminary_edges, [Road(r.source, r.target, r.shape) for r in scaled_roads], [])
        _run_netconvert(node_path, preliminary_edges, preliminary_net)
        _write_connections(connection_path, preliminary_net, preliminary_ids)

    _run_netconvert(node_path, edge_path, output_net, connection_path)
    issues = _validate_usable_structure(output_net)
    if issues:
        raise RuntimeError(f"{output_net} failed validation:\n" + "\n".join(issues[:40]))
    return output_net


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create normalized real-world SUMO maps with merged bidirectional three-lane usable roads."
    )
    parser.add_argument("--scale", type=float, default=SCALE_FACTOR)
    parser.add_argument("--drop-unusable", action="store_true")
    parser.add_argument(
        "--real-world-net",
        type=Path,
        default=REPO_ROOT / "scenarios" / "real_world" / "map.net.xml",
    )
    parser.add_argument(
        "--real-world-output",
        type=Path,
        default=REPO_ROOT / "scenarios" / "real_world" / "map_3lane_norm.net.xml",
    )
    parser.add_argument(
        "--real-world2-net",
        type=Path,
        default=REPO_ROOT / "scenarios" / "real_world2" / "map2.net.xml",
    )
    parser.add_argument(
        "--real-world2-output",
        type=Path,
        default=REPO_ROOT / "scenarios" / "real_world2" / "map2_3lane_norm.net.xml",
    )
    args = parser.parse_args()

    for source, output in (
        (args.real_world_net, args.real_world_output),
        (args.real_world2_net, args.real_world2_output),
    ):
        generated = normalize_network(
            source,
            output,
            preserve_unusable=not args.drop_unusable,
            scale=args.scale,
        )
        print(f"Generated {generated}")


if __name__ == "__main__":
    main()
