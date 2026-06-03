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


def test_two_lane_feature_vector_uses_eight_actions_and_four_incident_directions() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=[
            "B3B2_0",
            "B1B2_0",
            "B3B2_1",
            "B1B2_1",
            "C2B2_0",
            "A2B2_0",
            "C2B2_1",
            "A2B2_1",
        ],
        action_edges=[
            ["B3B2_0", "B1B2_0"],
            ["C2B2_0", "A2B2_0"],
            ["B3B2_1", "B1B2_1"],
            ["C2B2_1", "A2B2_1"],
            ["B3B2_0", "B3B2_1"],
            ["C2B2_0", "C2B2_1"],
            ["B1B2_0", "B1B2_1"],
            ["A2B2_0", "A2B2_1"],
        ],
        num_phases=8,
        action_approaches=[[0, 2], [1, 3], [0, 2], [1, 3], [0], [1], [2], [3]],
    )

    features = agent.extract_features(
        {"B3B2_0": 10.0, "B3B2_1": 20.0},
        current_phase=4,
        dist_to_incident=2,
        incident_direction=0,
        time_discrete=10,
        incident_active=True,
        action=4,
        action_pressures=[0.0] * 8,
        downstream_queues=[0.0] * 8,
        downstream_capacities=[100.0] * 8,
    )

    assert len(features) == agent.feature_dim
    assert agent.feature_dim == 8 + 8 + 4 + 8 + agent.global_action_feature_count
    assert features[8 + 4] == 1.0
    assert features[8 + 8] == 1.0


def test_residual_lookahead_preserves_greedy_queue_preference() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["north_sr", "east_sr"],
        action_edges=[["north_sr"], ["east_sr"]],
        num_phases=2,
        action_scoring_mode="residual_lookahead",
        residual_greedy_weight=1.0,
        residual_pressure_weight=0.0,
        residual_value_weight=0.0,
        residual_lookahead_weight=0.0,
        residual_downstream_penalty_weight=0.0,
        queue_scale=50.0,
    )

    q_values = agent.estimate_action_values(
        {"north_sr": 5.0, "east_sr": 30.0},
        {"north_sr": 0.0, "east_sr": 0.0},
        tau=1.1,
        current_phase=0,
        dist_to_incident=1,
        incident_direction=0,
        time_discrete=0,
        is_gridlock=False,
        incident_active=True,
        gamma=0.95,
    )

    assert q_values[1] > q_values[0]


def test_residual_lookahead_can_avoid_spillback_action() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["north_sr", "east_sr"],
        action_edges=[["north_sr"], ["east_sr"]],
        num_phases=2,
        action_scoring_mode="residual_lookahead",
        residual_greedy_weight=1.0,
        residual_pressure_weight=0.0,
        residual_value_weight=0.0,
        residual_lookahead_weight=0.0,
        residual_downstream_penalty_weight=3.0,
        queue_scale=50.0,
        spillback_occupancy_threshold=0.85,
    )

    q_values = agent.estimate_action_values(
        {"north_sr": 20.0, "east_sr": 21.0},
        {"north_sr": 0.0, "east_sr": 0.0},
        tau=1.1,
        current_phase=0,
        dist_to_incident=1,
        incident_direction=0,
        time_discrete=0,
        is_gridlock=False,
        incident_active=True,
        gamma=0.95,
        downstream_queues=[0.0, 100.0],
        downstream_capacities=[100.0, 100.0],
    )

    assert q_values[0] > q_values[1]


def test_heuristic_residual_zero_weights_match_immediate_heuristic() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["north_sr", "east_sr"],
        action_edges=[["north_sr"], ["east_sr"]],
        num_phases=2,
        action_scoring_mode="heuristic_residual",
        residual_value_weight=0.1,
        queue_priority_weight=2.0,
        total_queue_weight=0.0,
        lane_fairness_weight=0.0,
        queue_scale=50.0,
    )

    q_values = agent.estimate_action_values(
        {"north_sr": 10.0, "east_sr": 30.0},
        {"north_sr": 0.0, "east_sr": 0.0},
        tau=1.1,
        current_phase=0,
        dist_to_incident=1,
        incident_direction=0,
        time_discrete=0,
        is_gridlock=False,
        incident_active=True,
        gamma=0.95,
    )

    assert q_values[0] == -0.76 + 2.0 * 10.0 / 50.0
    assert q_values[1] == -0.76 + 2.0 * 30.0 / 50.0
    assert q_values[1] > q_values[0]


def test_heuristic_residual_weight_adds_bounded_learned_correction() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["north_sr", "east_sr"],
        action_edges=[["north_sr"], ["east_sr"]],
        num_phases=2,
        action_scoring_mode="heuristic_residual",
        residual_value_weight=0.1,
        queue_priority_weight=2.0,
        total_queue_weight=0.0,
        lane_fairness_weight=0.0,
        queue_scale=50.0,
    )
    action_feature_start = len(agent.incoming_edges) + agent.num_phases + agent.direction_count
    agent.weights[action_feature_start] = 20.0

    q_values = agent.estimate_action_values(
        {"north_sr": 10.0, "east_sr": 30.0},
        {"north_sr": 0.0, "east_sr": 0.0},
        tau=1.1,
        current_phase=0,
        dist_to_incident=1,
        incident_direction=0,
        time_discrete=0,
        is_gridlock=False,
        incident_active=True,
        gamma=0.95,
    )

    assert q_values[0] > q_values[1]


def test_compact_residual_feature_set_drops_redundant_phase_and_direction_features() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["north_r", "north_s", "north_l", "east_r"],
        action_edges=[["north_r", "north_s"], ["east_r"]],
        num_phases=2,
        feature_set="compact_residual",
        incident_action_feature_count=6,
        queue_scale=50.0,
    )

    features = agent.extract_features(
        {"north_r": 10.0, "north_s": 20.0, "north_l": 30.0, "east_r": 40.0},
        current_phase=0,
        dist_to_incident=3,
        incident_direction=2,
        time_discrete=60,
        incident_active=True,
        action=1,
        action_pressures=[5.0, 10.0],
        downstream_queues=[0.0, 20.0],
        downstream_capacities=[100.0, 100.0],
        incident_action_features=[
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [1.0, 0.5, 0.25, 2.0, 1.0, 0.5],
        ],
    )

    expected_dim = 4 + 2 + agent.global_action_feature_count + 6
    assert agent.global_action_feature_count == 6
    assert agent.feature_dim == expected_dim
    assert len(features) == expected_dim
    assert features[:4] == [0.2, 0.4, 0.6, 0.8]
    assert features[4:6] == [0.0, 1.0]
    assert features[-6:] == [1.0, 0.5, 0.25, 2.0, 1.0, 0.5]
