from its_signal_control.agent import ADPAgent


def test_predict_next_queues_applies_green_discharge_and_red_arrival() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["A2B2", "B1B2"],
        action_edges=[["A2B2"], ["B1B2"], [], []],
        decision_interval=10.0,
        traffic_rate=1500.0,
    )

    next_queues = agent.predict_next_queues(
        {"A2B2": 10.0, "B1B2": 5.0},
        action=0,
        downstream_queues=[0.0, 0.0, 0.0, 0.0],
        downstream_capacities=[100.0, 100.0, 100.0, 100.0],
    )

    assert next_queues["A2B2"] == 7.0
    assert next_queues["B1B2"] == 6.0


def test_predict_next_queues_clears_blocked_edges() -> None:
    agent = ADPAgent("B2", ["A2B2"], action_edges=[["A2B2"], [], [], []])
    next_queues = agent.predict_next_queues({"A2B2": 10.0}, action=0, blocked_edges=["A2B2"])
    assert next_queues["A2B2"] == 0.0
