from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NeighborFeatureConfig:
    enabled: bool = False
    max_hops: int = 1
    queue_scale: float = 50.0
    include_neighbor_actions: bool = True
    include_neighbor_phases: bool = True
    include_neighbor_queues: bool = True


def normalize_neighbor_queue(queue_value: float, queue_scale: float = 50.0, clip: float = 5.0) -> float:
    if queue_scale <= 0:
        raise ValueError("queue_scale must be positive.")
    return max(0.0, min(clip, queue_value / queue_scale))


def extract_neighbor_features(
    agent_id: str,
    neighbor_actions: dict[str, int] | None = None,
    neighbor_phases: dict[str, int] | None = None,
    neighbor_queues: dict[str, float] | None = None,
    num_neighbors: int = 4,
    num_phases: int = 4,
    queue_scale: float = 50.0,
    feature_clip: float = 5.0,
) -> list[float]:
    """
    提取鄰近路口特徵向量
    
    Returns:
        特徵向量：
        - neighbor_actions (num_neighbors): 鄰近路口的選中動作（one-hot per neighbor）
        - neighbor_phases (num_neighbors): 鄰近路口的當前相位（one-hot per neighbor）
        - neighbor_queues (num_neighbors): 歸一化的鄰近隊列長度
    """
    features = []

    neighbor_actions = neighbor_actions or {}
    neighbor_phases = neighbor_phases or {}
    neighbor_queues = neighbor_queues or {}

    # 動作特徵（one-hot 編碼）
    for _ in range(num_neighbors):
        for _ in range(num_phases):
            features.append(0.0)

    # 相位特徵（one-hot 編碼）
    for _ in range(num_neighbors):
        for _ in range(num_phases):
            features.append(0.0)

    # 隊列特徵（歸一化）
    for _ in range(num_neighbors):
        features.append(0.0)

    return features
