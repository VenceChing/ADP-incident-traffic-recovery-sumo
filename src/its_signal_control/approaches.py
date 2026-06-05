from __future__ import annotations

import math
from itertools import combinations
from typing import Mapping

Point = tuple[float, float]


def _angle(first: Point, second: Point) -> float:
    first_length = math.hypot(*first)
    second_length = math.hypot(*second)
    if first_length == 0.0 or second_length == 0.0:
        return 0.0
    cosine = (first[0] * second[0] + first[1] * second[1]) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _assign_pair(
    result: dict[str, str],
    keys: tuple[str, str],
    vectors: Mapping[str, Point],
    positive_label: str,
    negative_label: str,
    component: int,
) -> None:
    first, second = keys
    if vectors[first][component] >= vectors[second][component]:
        result[first] = positive_label
        result[second] = negative_label
    else:
        result[first] = negative_label
        result[second] = positive_label


def _pair_is_vertical(keys: tuple[str, str], vectors: Mapping[str, Point]) -> bool:
    first = vectors[keys[0]]
    return abs(first[1]) >= abs(first[0])


def assign_cardinal_approaches(vectors: Mapping[str, Point]) -> dict[str, str]:
    """Assign local N/E/S/W labels while preserving opposite road arms."""
    keys = sorted(key for key, vector in vectors.items() if math.hypot(*vector) > 0.0)
    if not keys:
        return {}
    if len(keys) > 4:
        raise ValueError(f"Expected at most four approaches, got {len(keys)}")

    result: dict[str, str] = {}
    if len(keys) == 1:
        key = keys[0]
        x, y = vectors[key]
        result[key] = ("E" if x >= 0 else "W") if abs(x) >= abs(y) else ("N" if y >= 0 else "S")
        return result

    opposite_pair = max(combinations(keys, 2), key=lambda pair: _angle(vectors[pair[0]], vectors[pair[1]]))
    if len(keys) in {2, 3}:
        if _pair_is_vertical(opposite_pair, vectors):
            _assign_pair(result, opposite_pair, vectors, "N", "S", 1)
            remaining_labels = ("E", "W", 0)
        else:
            _assign_pair(result, opposite_pair, vectors, "E", "W", 0)
            remaining_labels = ("N", "S", 1)
        for key in keys:
            if key in result:
                continue
            positive, negative, component = remaining_labels
            result[key] = positive if vectors[key][component] >= 0 else negative
        return result

    pairings = [
        ((keys[0], keys[1]), (keys[2], keys[3])),
        ((keys[0], keys[2]), (keys[1], keys[3])),
        ((keys[0], keys[3]), (keys[1], keys[2])),
    ]
    first_pair, second_pair = min(
        pairings,
        key=lambda pairs: sum(abs(180.0 - _angle(vectors[first], vectors[second])) for first, second in pairs),
    )
    if _pair_is_vertical(first_pair, vectors) and not _pair_is_vertical(second_pair, vectors):
        vertical_pair, horizontal_pair = first_pair, second_pair
    elif _pair_is_vertical(second_pair, vectors) and not _pair_is_vertical(first_pair, vectors):
        vertical_pair, horizontal_pair = second_pair, first_pair
    else:
        first_vertical_score = abs(vectors[first_pair[0]][1]) - abs(vectors[first_pair[0]][0])
        second_vertical_score = abs(vectors[second_pair[0]][1]) - abs(vectors[second_pair[0]][0])
        vertical_pair, horizontal_pair = (
            (first_pair, second_pair)
            if first_vertical_score >= second_vertical_score
            else (second_pair, first_pair)
        )

    _assign_pair(result, vertical_pair, vectors, "N", "S", 1)
    _assign_pair(result, horizontal_pair, vectors, "E", "W", 0)
    return result
