from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NeighborFeatureConfig:
    enabled: bool = False
    max_hops: int = 1
    queue_scale: float = 50.0


def normalize_neighbor_queue(queue_value: float, queue_scale: float = 50.0, clip: float = 5.0) -> float:
    if queue_scale <= 0:
        raise ValueError("queue_scale must be positive.")
    return max(0.0, min(clip, queue_value / queue_scale))
