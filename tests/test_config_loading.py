from pathlib import Path

from its_signal_control import config


def test_historical_best_preset_loads_expected_values() -> None:
    preset = config.load_preset(Path("configs/historical_best.yaml"))
    assert preset["RATE"] == 2500
    assert preset["ADP_QUEUE_PRIORITY_WEIGHT"] == 2.0
    assert preset["ALPHA"] == 0.0005
    assert preset["EVALUATION_CONTROLLERS"] == ["fixed_time_rr", "greedy", "max_pressure", "adp_eval"]


def test_two_lane_smoke_preset_selects_two_lane_action_space() -> None:
    preset = config.load_preset(Path("configs/two_lane_smoke.yaml"))
    assert preset["SCENARIO_DIR"] == "scenarios/grid_4x4_2lane"
    assert preset["ACTION_SPACE"] == "two_lane_8"
    assert preset["ROUTE_FILE_PREFIX"] == "grid_4x4_2lane"


def test_two_lane_random_training_preset_uses_random_incidents() -> None:
    preset = config.load_preset(Path("configs/two_lane_training_50_random.yaml"))
    assert preset["TRAIN_EPISODES"] == 50
    assert preset["TRAIN_INCIDENT_SELECTION"] == "random"
    assert preset["RUN_EVALUATION"] is False


def test_two_lane_residual_training_preset_enables_residual_lookahead() -> None:
    preset = config.load_preset(Path("configs/two_lane_training_residual_200_random.yaml"))
    assert preset["TRAIN_EPISODES"] == 200
    assert preset["TRAIN_INCIDENT_SELECTION"] == "random"
    assert preset["ADP_ACTION_SCORING_MODE"] == "residual_lookahead"
    assert preset["ADP_LOOKAHEAD_DEPTH"] == 2
    assert preset["ADP_LANE_FAIRNESS_WEIGHT"] == 0.0
