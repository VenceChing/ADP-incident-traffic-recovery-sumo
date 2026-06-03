from pathlib import Path

from its_signal_control.actions import action_matches, get_action_definitions, movement_group_for_connection
from its_signal_control.agent import ADPAgent
from its_signal_control import controllers
from its_signal_control.experiment import get_controller_decision_interval, select_round_robin_action
from its_signal_control.scenario_validation import validate_three_lane_network


def test_three_lane_action_names_and_mixed_phase_matching() -> None:
    actions = get_action_definitions("three_lane_8")
    assert [action.name for action in actions] == [
        "NS_SR",
        "EW_SR",
        "N_LSR_E_R",
        "S_LSR_W_R",
        "E_LSR_S_R",
        "W_LSR_N_R",
        "NS_L_EW_R",
        "NS_R_EW_L",
    ]

    north_plus_east_right = actions[2]
    assert action_matches(north_plus_east_right, "N", "L")
    assert action_matches(north_plus_east_right, "N", "S")
    assert action_matches(north_plus_east_right, "N", "R")
    assert action_matches(north_plus_east_right, "E", "R")
    assert not action_matches(north_plus_east_right, "E", "S")
    assert not action_matches(north_plus_east_right, "E", "L")


def test_three_lane_movement_groups_follow_right_straight_left_lane_split() -> None:
    assert movement_group_for_connection("A0B0_0", action_space="three_lane_8") == "R"
    assert movement_group_for_connection("A0B0_1", action_space="three_lane_8") == "S"
    assert movement_group_for_connection("A0B0_2", action_space="three_lane_8") == "L"
    assert movement_group_for_connection("A0B0_1", "r", action_space="three_lane_8") == "R"
    assert movement_group_for_connection("A0B0_1", "l", action_space="three_lane_8") == "L"


def test_three_lane_feature_vector_uses_twelve_lane_queues_and_eight_actions() -> None:
    incoming_edges = [
        "N_R",
        "N_S",
        "N_L",
        "E_R",
        "E_S",
        "E_L",
        "S_R",
        "S_S",
        "S_L",
        "W_R",
        "W_S",
        "W_L",
    ]
    agent = ADPAgent(
        "B2",
        incoming_edges=incoming_edges,
        action_edges=[incoming_edges[:2], incoming_edges[3:5], incoming_edges[:3], incoming_edges[6:9]],
        num_phases=8,
        action_approaches=[[0, 2], [1, 3], [0, 1], [2, 3], [1, 2], [3, 0], [0, 2, 1, 3], [0, 2, 1, 3]],
    )

    features = agent.extract_features(
        {"N_R": 10.0, "N_S": 20.0, "N_L": 30.0},
        current_phase=0,
        dist_to_incident=2,
        incident_direction=0,
        time_discrete=10,
        incident_active=True,
        action=2,
        action_pressures=[0.0] * 8,
        downstream_queues=[0.0] * 8,
        downstream_capacities=[100.0] * 8,
    )

    assert len(features) == agent.feature_dim
    assert agent.feature_dim == 12 + 8 + 4 + 8 + agent.global_action_feature_count


def test_three_lane_incident_action_features_expand_feature_vector_when_enabled() -> None:
    incoming_edges = [
        "N_R",
        "N_S",
        "N_L",
        "E_R",
        "E_S",
        "E_L",
        "S_R",
        "S_S",
        "S_L",
        "W_R",
        "W_S",
        "W_L",
    ]
    agent = ADPAgent(
        "B2",
        incoming_edges=incoming_edges,
        action_edges=[incoming_edges[:2], incoming_edges[3:5], incoming_edges[:3], incoming_edges[6:9]],
        num_phases=8,
        incident_action_feature_count=6,
    )

    features = agent.extract_features(
        {"N_R": 10.0},
        current_phase=0,
        dist_to_incident=2,
        incident_direction=0,
        time_discrete=10,
        incident_active=True,
        action=2,
        action_pressures=[0.0] * 8,
        downstream_queues=[0.0] * 8,
        downstream_capacities=[100.0] * 8,
        incident_action_features=[[0.0] * 6, [0.0] * 6, [1.0, 0.5, 0.5, 2.0, 1.0, 1.0]],
    )

    assert len(features) == agent.feature_dim
    assert agent.feature_dim == 12 + 8 + 4 + 8 + agent.global_action_feature_count + 6
    assert features[-6:] == [1.0, 0.5, 0.5, 2.0, 1.0, 1.0]


def test_three_lane_incident_action_features_identify_blocked_and_near_downstream() -> None:
    previous_enabled = controllers.ADP_INCIDENT_ACTION_FEATURES_ENABLED
    previous_scale = controllers.ADP_QUEUE_SCALE
    controllers.ADP_INCIDENT_ACTION_FEATURES_ENABLED = True
    controllers.ADP_QUEUE_SCALE = 50.0
    try:
        context = {
            "action_space": "three_lane_8",
            "action_names": ["feed_blocked", "feed_far"],
            "action_movement_edges": {
                "B2": {
                    0: [("B1B2", "B2C2"), ("A2B2", "B2B3")],
                    1: [("B2A2", "A2A3")],
                }
            },
            "action_upstream_keys": {
                "B2": {
                    0: ["B1B2_0", "A2B2_1"],
                    1: ["B2A2_0"],
                }
            },
        }
        features = controllers.get_incident_action_features(
            "B2",
            {"B1B2_0": 30.0, "A2B2_1": 20.0, "B2A2_0": 40.0},
            ["B2C2", "C2B2"],
            True,
            context,
        )

        assert features is not None
        assert features[0] == [0.5, 1.0, 1.0, 0.5, 1.0, 1.0]
        assert features[1][0] == 0.0
    finally:
        controllers.ADP_INCIDENT_ACTION_FEATURES_ENABLED = previous_enabled
        controllers.ADP_QUEUE_SCALE = previous_scale


def test_three_lane_reward_fairness_penalizes_r_s_l_imbalance() -> None:
    agent = ADPAgent(
        "B2",
        incoming_edges=["N_R", "N_S", "N_L"],
        action_edges=[["N_R"], ["N_S"], ["N_L"]],
        num_phases=3,
        queue_movements={"N_R": "R", "N_S": "S", "N_L": "L"},
        queue_approaches={"N_R": "N", "N_S": "N", "N_L": "N"},
        lane_fairness_weight=1.0,
        lane_fairness_margin=5.0,
        queue_scale=50.0,
    )

    balanced = agent.calculate_reward(
        {"N_R": 10.0, "N_S": 12.0, "N_L": 14.0},
        {"N_R": 0.0, "N_S": 0.0, "N_L": 0.0},
        tau=1.1,
        current_phase=0,
        action=0,
        is_gridlock=False,
    )
    imbalanced = agent.calculate_reward(
        {"N_R": 2.0, "N_S": 10.0, "N_L": 50.0},
        {"N_R": 0.0, "N_S": 0.0, "N_L": 0.0},
        tau=1.1,
        current_phase=0,
        action=0,
        is_gridlock=False,
    )

    assert imbalanced < balanced


def test_three_lane_fixed_time_round_robin_cycles_all_eight_actions() -> None:
    action_names = [action.name for action in get_action_definitions("three_lane_8")]
    interval = get_controller_decision_interval("fixed_time_rr")
    selected = [select_round_robin_action(t, action_names, interval) for t in range(0, 160, 20)]
    assert selected == list(range(8))


def test_three_lane_network_lanes_and_actions_are_valid() -> None:
    net_path = Path("scenarios/grid_4x4_3lane/grid_4x4_3lane.net.xml")
    if net_path.exists():
        assert validate_three_lane_network(net_path) == []
