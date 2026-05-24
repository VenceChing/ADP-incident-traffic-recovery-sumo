from __future__ import annotations


class DecisionIntervalSchedule:
    def __init__(self, default_interval_seconds: int, per_agent: dict[str, int] | None = None) -> None:
        if default_interval_seconds <= 0:
            raise ValueError("default_interval_seconds must be positive.")
        self.default_interval_seconds = default_interval_seconds
        self.per_agent = per_agent or {}

    def interval_for(self, agent_id: str) -> int:
        interval = self.per_agent.get(agent_id, self.default_interval_seconds)
        if interval <= 0:
            raise ValueError(f"Decision interval for {agent_id} must be positive.")
        return interval

    def should_decide(self, agent_id: str, sim_time: float) -> bool:
        interval = self.interval_for(agent_id)
        return int(sim_time) % interval == 0
