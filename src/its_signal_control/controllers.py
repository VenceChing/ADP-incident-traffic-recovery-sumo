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

'''
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
    neighbor_actions: dict[str, int] | None = None,
    neighbor_phases: dict[str, int] | None = None,
    neighbor_queues: dict[str, float] | None = None,
) -> tuple[int, list[float]]:
    incident_active = sim_time >= INCIDENT_TIME
    dist_to_incident = get_incident_distance(agent_id, incident_edges)
    incident_direction = get_incident_direction(agent_id, incident_edges)
    time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
    action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
    
    # 提取特徵（包含鄰近信息）
    features = agent.extract_features(
        current_queues,
        current_phase,
        dist_to_incident,
        incident_direction,
        time_discrete,
        incident_active,
        action_pressures=action_pressures,
        downstream_queues=downstream_queues,
        downstream_capacities=downstream_capacities,
        neighbor_actions=neighbor_actions,
        neighbor_phases=neighbor_phases,
        neighbor_queues=neighbor_queues,
    )
    
    # 計算所有動作的 Q 值（使用鄰近特徵）
    q_values = []
    for candidate_action in range(agent.num_phases):
        candidate_features = agent.extract_features(
            current_queues,
            current_phase,
            dist_to_incident,
            incident_direction,
            time_discrete,
            incident_active,
            action=candidate_action,
            action_pressures=action_pressures,
            downstream_queues=downstream_queues,
            downstream_capacities=downstream_capacities,
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
        )
        #print(f"Candidate action {candidate_action} features: {candidate_features}")
        q_value = sum(w * f for w, f in zip(agent.weights, candidate_features))
        q_values.append(q_value)
    
    # ε-貪心選擇
    import random
    if random.random() < epsilon:
        action = random.choice(range(agent.num_phases))
    else:
        action = max(range(agent.num_phases), key=lambda a: q_values[a])
    
    return action, q_values
'''
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
    neighbor_actions: dict[str, int] | None = None,
    neighbor_phases: dict[str, int] | None = None,
    neighbor_queues: dict[str, float] | None = None,
) -> tuple[int, list[float]]:
    import random
    
    # 1. 基礎環境狀態與時間參數計算
    incident_active = sim_time >= INCIDENT_TIME
    dist_to_incident = get_incident_distance(agent_id, incident_edges)
    incident_direction = get_incident_direction(agent_id, incident_edges)
    time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
    action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
    
    is_gridlock = context.get("is_gridlock", False) # 從模擬上下文或狀態獲取是否死鎖
    
    # 3. 🚨 核心改動：呼叫你寫好的新邏輯來估算所有動作的 Q 值（內部已包含鄰居訊息與預測）
    q_values = agent.estimate_action_values(
        current_queues=current_queues,
        baseline_queues=baseline_queues,
        tau=TAU,
        current_phase=current_phase,
        dist_to_incident=dist_to_incident,
        incident_direction=incident_direction,
        time_discrete=time_discrete,
        is_gridlock=is_gridlock,
        incident_active=incident_active,
        gamma=GAMMA,
        incident_edges=incident_edges,
        action_pressures=action_pressures,
        downstream_queues=downstream_queues,
        downstream_capacities=downstream_capacities,
        neighbor_actions=neighbor_actions,  # 順利傳遞鄰居動作
        neighbor_phases=neighbor_phases,    # 順利傳遞鄰居相位
        neighbor_queues=neighbor_queues,    # 順利傳遞鄰居隊列
    )
    
    # 4. ε-貪心策略選擇動作
    if random.random() < epsilon:
        # 隨機探索
        action = random.choice(range(agent.num_phases))
    else:
        # 根據剛剛計算出來包含鄰居考量的新 Q 值，選擇最優動作
        action = max(range(agent.num_phases), key=lambda a: q_values[a])
        
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
    neighbor_info: dict[str, tuple[dict[str, int], dict[str, int], dict[str, float]]] | None = None,
) -> None:
    neighbor_info = neighbor_info or {}
    
    for agent_id, agent in agents.items():
        incident_active = sim_time >= INCIDENT_TIME
        next_queues = get_agent_queues(env, agent_id, sim_time, incident_edges)
        dist_to_incident = get_incident_distance(agent_id, incident_edges)
        incident_direction = get_incident_direction(agent_id, incident_edges)
        time_discrete = 0 if sim_time < INCIDENT_TIME else int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
        action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
        
        # 獲取鄰近信息
        neighbor_actions, neighbor_phases, neighbor_queues = neighbor_info.get(
            agent_id, ({}, {}, {})
        )
        
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
        
        # 計算下一狀態的最優動作（包含鄰近信息）
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
                    neighbor_actions=neighbor_actions,
                    neighbor_phases=neighbor_phases,
                    neighbor_queues=neighbor_queues,
                )
            ),
        )
        
        # 提取下一狀態特徵（包含鄰近信息）
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
            neighbor_actions=neighbor_actions,
            neighbor_phases=neighbor_phases,
            neighbor_queues=neighbor_queues,
        )
        
        # 更新權重（使用含鄰近信息的特徵）
        agent.update_weights(
            step_cache[agent_id]["features"],
            reward,
            next_features,
            ALPHA,
            GAMMA,
        )


class DecisionCache:
    """存儲本決策週期內已決策的路口信息"""

    def __init__(self) -> None:
        self.actions: dict[str, int] = {}  # agent_id -> action
        self.phases: dict[str, int] = {}  # agent_id -> current_phase
        self.queues: dict[str, float] = {}  # agent_id -> total_queue
        self.last_decision_time: dict[str, float] = {}  # agent_id -> sim_time

    def cache_decision(
        self,
        agent_id: str,
        action: int,
        current_phase: int,
        total_queue: float,
        sim_time: float,
    ) -> None:
        """快取某路口的決策信息"""
        self.actions[agent_id] = action
        self.phases[agent_id] = current_phase
        self.queues[agent_id] = total_queue
        self.last_decision_time[agent_id] = sim_time

    def get_neighbor_info(
        self,
        agent_id: str,
        neighbors: list[str],
    ) -> tuple[dict[str, int], dict[str, int], dict[str, float]]:
        """獲取鄰近路口的決策信息"""
        neighbor_actions = {}
        neighbor_phases = {}
        neighbor_queues = {}

        for nid in neighbors:
            if nid in self.actions:
                neighbor_actions[nid] = self.actions[nid]
                neighbor_phases[nid] = self.phases[nid]
                neighbor_queues[nid] = self.queues[nid]

        return neighbor_actions, neighbor_phases, neighbor_queues

    def can_decide(
        self,
        agent_id: str,
        sim_time: float,
        decision_interval: float,
    ) -> bool:
        """檢查是否應該決策（防止連續決策）"""
        last_time = self.last_decision_time.get(agent_id, -float("inf"))
        return (sim_time - last_time) >= decision_interval

    def clear(self) -> None:
        """清空快取（準備下一個決策週期）"""
        self.actions.clear()
        self.phases.clear()
        self.queues.clear()
