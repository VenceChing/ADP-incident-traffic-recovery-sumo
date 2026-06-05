from __future__ import annotations

from dataclasses import dataclass


DIRECTION_TO_INDEX = {"N": 0, "E": 1, "S": 2, "W": 3}
INDEX_TO_DIRECTION = ["N", "E", "S", "W"]
LEFT_TURN_DIRS = {"l", "L", "t"}
RIGHT_TURN_DIRS = {"r", "R"}


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    approaches: tuple[str, ...]
    movements: tuple[str, ...]
    movement_pairs: tuple[tuple[str, str], ...] = ()


def get_action_definitions(action_space: str) -> list[ActionDefinition]:
    if action_space == "three_lane_8":
        return [
            ActionDefinition("NS_SR", ("N", "S"), ("S", "R")),
            ActionDefinition("EW_SR", ("E", "W"), ("S", "R")),
            ActionDefinition(
                "N_LSR_E_R",
                ("N", "E"),
                ("L", "S", "R"),
                (("N", "L"), ("N", "S"), ("N", "R"), ("E", "R")),
            ),
            ActionDefinition(
                "S_LSR_W_R",
                ("S", "W"),
                ("L", "S", "R"),
                (("S", "L"), ("S", "S"), ("S", "R"), ("W", "R")),
            ),
            ActionDefinition(
                "E_LSR_S_R",
                ("E", "S"),
                ("L", "S", "R"),
                (("E", "L"), ("E", "S"), ("E", "R"), ("S", "R")),
            ),
            ActionDefinition(
                "W_LSR_N_R",
                ("W", "N"),
                ("L", "S", "R"),
                (("W", "L"), ("W", "S"), ("W", "R"), ("N", "R")),
            ),
            ActionDefinition(
                "NS_L_EW_R",
                ("N", "S", "E", "W"),
                ("L", "R"),
                (("N", "L"), ("S", "L"), ("E", "R"), ("W", "R")),
            ),
            ActionDefinition(
                "NS_R_EW_L",
                ("N", "S", "E", "W"),
                ("R", "L"),
                (("N", "R"), ("S", "R"), ("E", "L"), ("W", "L")),
            ),
        ]
    if action_space == "two_lane_8":
        return [
            ActionDefinition("NS_SR", ("N", "S"), ("SR",)),
            ActionDefinition("EW_SR", ("E", "W"), ("SR",)),
            ActionDefinition("NS_L", ("N", "S"), ("L",)),
            ActionDefinition("EW_L", ("E", "W"), ("L",)),
            ActionDefinition("N_SRL", ("N",), ("SR", "L")),
            ActionDefinition("E_SRL", ("E",), ("SR", "L")),
            ActionDefinition("S_SRL", ("S",), ("SR", "L")),
            ActionDefinition("W_SRL", ("W",), ("SR", "L")),
        ]
    if action_space in {"legacy_4", "direction_4"}:
        return [
            ActionDefinition("N", ("N",), ("SR", "L")),
            ActionDefinition("E", ("E",), ("SR", "L")),
            ActionDefinition("S", ("S",), ("SR", "L")),
            ActionDefinition("W", ("W",), ("SR", "L")),
        ]
    raise ValueError(f"Unsupported action space: {action_space}")


def get_action_names(action_space: str) -> list[str]:
    return [definition.name for definition in get_action_definitions(action_space)]


def direction_indices_for_action(definition: ActionDefinition) -> list[int]:
    return [DIRECTION_TO_INDEX[approach] for approach in definition.approaches]


def lane_index(lane_id: str | None) -> int | None:
    if not lane_id or "_" not in lane_id:
        return None
    suffix = lane_id.rsplit("_", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def movement_group_for_connection(
    from_lane: str | None,
    turn_dir: str | None = None,
    *,
    action_space: str = "legacy_4",
) -> str:
    if action_space == "three_lane_8":
        if turn_dir in LEFT_TURN_DIRS:
            return "L"
        if turn_dir in RIGHT_TURN_DIRS:
            return "R"
        lane = lane_index(from_lane)
        if lane == 0:
            return "R"
        if lane == 2:
            return "L"
        return "S"
    if action_space == "two_lane_8":
        if turn_dir in LEFT_TURN_DIRS:
            return "L"
        return "L" if lane_index(from_lane) == 1 else "SR"
    return "L" if turn_dir in LEFT_TURN_DIRS else "SR"


def action_matches(definition: ActionDefinition, approach: str | None, movement_group: str | None) -> bool:
    if approach is None or movement_group is None:
        return False
    if definition.movement_pairs:
        return (approach, movement_group) in definition.movement_pairs
    return approach in definition.approaches and movement_group in definition.movements
