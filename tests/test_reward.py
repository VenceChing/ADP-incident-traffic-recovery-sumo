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


def test_lane_fairness_penalizes_imbalanced_two_lane_queues() -> None:
    agent = ADPAgent(
        "B2",
        ["B3B2_0", "B3B2_1"],
        action_edges=[["B3B2_0"], ["B3B2_1"], [], []],
        queue_movements={"B3B2_0": "SR", "B3B2_1": "L"},
        queue_approaches={"B3B2_0": "N", "B3B2_1": "N"},
        lane_fairness_weight=1.0,
        lane_fairness_margin=0.0,
        queue_scale=50.0,
    )
    balanced = agent.calculate_reward(
        {"B3B2_0": 10.0, "B3B2_1": 10.0},
        {"B3B2_0": 0.0, "B3B2_1": 0.0},
        1.1,
        0,
        0,
        False,
    )
    imbalanced = agent.calculate_reward(
        {"B3B2_0": 20.0, "B3B2_1": 0.0},
        {"B3B2_0": 0.0, "B3B2_1": 0.0},
        1.1,
        0,
        0,
        False,
    )

    assert imbalanced < balanced
