from its_signal_control.agent import ADPAgent


def test_reward_excludes_incident_edges_and_penalizes_switch() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["A2B2", "B1B2"],
        action_edges=[["A2B2"], ["B1B2"], [], []],
        switch_penalty=0.2,
        total_queue_weight=0.05,
        queue_scale=50.0,
    )

    keep_reward = agent.calculate_reward(
        {"A2B2": 100.0, "B1B2": 20.0},
        {"A2B2": 0.0, "B1B2": 10.0},
        tau=1.1,
        current_phase=0,
        action=0,
        is_gridlock=False,
        incident_edges=["A2B2"],
    )
    switch_reward = agent.calculate_reward(
        {"A2B2": 100.0, "B1B2": 20.0},
        {"A2B2": 0.0, "B1B2": 10.0},
        tau=1.1,
        current_phase=0,
        action=1,
        is_gridlock=False,
        incident_edges=["A2B2"],
    )

    assert switch_reward == keep_reward - 0.2
    assert keep_reward > -1.0


def test_gridlock_penalty_reduces_reward() -> None:
    agent = ADPAgent("B2", ["A2B2"], action_edges=[["A2B2"], [], [], []], gridlock_penalty=20.0)
    normal = agent.calculate_reward({"A2B2": 10.0}, {"A2B2": 0.0}, 1.1, 0, 0, False)
    gridlock = agent.calculate_reward({"A2B2": 10.0}, {"A2B2": 0.0}, 1.1, 0, 0, True)
    assert gridlock < normal
