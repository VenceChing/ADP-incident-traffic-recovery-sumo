from its_signal_control.agent import ADPAgent


def test_feature_vector_length_and_scaling() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["A2B2", "B1B2", "C2B2", "B3B2"],
        action_edges=[["A2B2"], ["B1B2"], ["C2B2"], ["B3B2"]],
        queue_scale=50.0,
        distance_scale=6.0,
        time_scale=120.0,
    )

    features = agent.extract_features(
        {"A2B2": 25.0, "B1B2": 50.0, "C2B2": 75.0, "B3B2": 100.0},
        current_phase=1,
        dist_to_incident=3,
        incident_direction=2,
        time_discrete=60,
        incident_active=True,
        action=2,
        action_pressures=[0.0, 10.0, 20.0, 30.0],
        downstream_queues=[0.0, 5.0, 10.0, 15.0],
        downstream_capacities=[100.0, 100.0, 100.0, 100.0],
    )

    assert len(features) == agent.feature_dim
    assert features[:4] == [0.5, 1.0, 1.5, 2.0]
    assert features[5] == 1.0
    assert features[10] == 1.0
    assert features[14] == 1.0
