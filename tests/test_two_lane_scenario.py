from pathlib import Path

from its_signal_control.experiment import (
    get_active_decision_interval,
    get_controller_decision_interval,
    select_round_robin_action,
)
from its_signal_control.scenario_validation import validate_two_lane_network


def test_two_lane_network_lanes_and_actions_are_valid() -> None:
    issues = validate_two_lane_network(
        Path("scenarios/grid_4x4_2lane/grid_4x4_2lane.net.xml")
    )
    assert issues == []


def test_two_lane_fixed_time_round_robin_uses_protected_axis_phases_only() -> None:
    action_names = ["NS_SR", "EW_SR", "NS_L", "EW_L", "N_SRL", "E_SRL", "S_SRL", "W_SRL"]
    interval = get_controller_decision_interval("fixed_time_rr")
    selected = [select_round_robin_action(t, action_names, interval) for t in [0, 20, 40, 60, 80, 100, 120, 140]]
    assert selected == [0, 1, 2, 3, 0, 1, 2, 3]


def test_non_fixed_controllers_keep_default_decision_interval() -> None:
    assert get_controller_decision_interval("greedy") == 10
    assert get_controller_decision_interval("max_pressure") == 10
    assert get_controller_decision_interval("adp_eval") == 10


def test_pre_incident_fixed_time_warmup_uses_fixed_time_interval_for_all_controllers() -> None:
    assert get_active_decision_interval("greedy", 1190) == 20
    assert get_active_decision_interval("max_pressure", 1190) == 20
    assert get_active_decision_interval("adp_eval", 1190) == 20
    assert get_active_decision_interval("greedy", 1200) == 10
    assert get_active_decision_interval("fixed_time_rr", 1200) == 20
