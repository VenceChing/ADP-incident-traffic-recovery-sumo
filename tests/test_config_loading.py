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


def test_three_lane_training_preset_selects_three_lane_action_space() -> None:
    preset = config.load_preset(Path("configs/three_lane_training_50_random.yaml"))
    assert preset["SCENARIO_DIR"] == "scenarios/grid_4x4_3lane"
    assert preset["ACTION_SPACE"] == "three_lane_8"
    assert preset["ROUTE_FILE_PREFIX"] == "grid_4x4_3lane"
    assert preset["TRAIN_EPISODES"] == 50
    assert preset["TRAIN_INCIDENT_SELECTION"] == "random"


def test_three_lane_incident_feature_presets_enable_v2_features() -> None:
    train_preset = config.load_preset(Path("configs/three_lane_training_50_incident_features.yaml"))
    eval_preset = config.load_preset(Path("configs/three_lane_evaluation_incident_features.yaml"))

    assert train_preset["ACTION_SPACE"] == "three_lane_8"
    assert train_preset["ADP_INCIDENT_ACTION_FEATURES_ENABLED"] is True
    assert train_preset["ADP_VARIANT_LABEL"] == "three_lane_8_incident_action_features_v2"
    assert "incident_features" in train_preset["RESULTS_DIR"]
    assert eval_preset["LOAD_WEIGHTS_FOR_EVALUATION"] is True
    assert "three_lane_training_full_incident_features" in eval_preset["WEIGHTS_PATH"]


def test_three_lane_incident_residual_presets_use_heuristic_residual_mode() -> None:
    train_preset = config.load_preset(Path("configs/three_lane_training_50_incident_residual.yaml"))
    eval_preset = config.load_preset(Path("configs/three_lane_evaluation_50_incident_residual.yaml"))

    assert train_preset["ACTION_SPACE"] == "three_lane_8"
    assert train_preset["ADP_ACTION_SCORING_MODE"] == "heuristic_residual"
    assert train_preset["ADP_RESIDUAL_VALUE_WEIGHT"] == 0.10
    assert train_preset["ADP_INCIDENT_ACTION_FEATURES_ENABLED"] is True
    assert train_preset["ADP_VARIANT_LABEL"] == "three_lane_8_incident_action_heuristic_residual_v3"
    assert "three_lane_training_50_incident_residual" in eval_preset["WEIGHTS_PATH"]


def test_three_lane_compact_residual_long_training_preset_reduces_features() -> None:
    train_preset = config.load_preset(Path("configs/three_lane_training_200_compact_residual.yaml"))
    eval_preset = config.load_preset(Path("configs/three_lane_evaluation_200_compact_residual.yaml"))

    assert train_preset["ACTION_SPACE"] == "three_lane_8"
    assert train_preset["TRAIN_EPISODES"] == 200
    assert train_preset["ADP_ACTION_SCORING_MODE"] == "heuristic_residual"
    assert train_preset["ADP_FEATURE_SET"] == "compact_residual"
    assert train_preset["ADP_INCIDENT_ACTION_FEATURES_ENABLED"] is True
    assert train_preset["ADP_VARIANT_LABEL"] == "three_lane_8_compact_residual_v4"
    assert "three_lane_training_200_compact_residual" in eval_preset["WEIGHTS_PATH"]


def test_decision_order_defaults_to_unified() -> None:
    assert config.DECISION_ORDER_STRATEGY == "unified"
    assert config.DECISION_ORDER_RANDOM_SEED == 42


def test_three_lane_decision_order_presets_enable_distance_decay() -> None:
    demo_preset = config.load_preset(Path("configs/three_lane_demo_decision_order_distance_decay.yaml"))
    smoke_preset = config.load_preset(Path("configs/three_lane_smoke_decision_order_distance_decay.yaml"))
    train_preset = config.load_preset(Path("configs/three_lane_training_50_decision_order_distance_decay.yaml"))
    eval_preset = config.load_preset(Path("configs/three_lane_evaluation_24_decision_order_distance_decay.yaml"))

    assert demo_preset["RUN_SINGLE_DEMO"] is True
    assert demo_preset["DEMO_CONTROLLER"] == "adp_eval"
    assert demo_preset["DECISION_ORDER_STRATEGY"] == "distance_decay"
    assert smoke_preset["DECISION_ORDER_STRATEGY"] == "distance_decay"
    assert train_preset["DECISION_ORDER_STRATEGY"] == "distance_decay"
    assert eval_preset["DECISION_ORDER_STRATEGY"] == "distance_decay"
    assert train_preset["TRAIN_EPISODES"] == 50
    assert eval_preset["EVAL_EPISODES_PER_CONTROLLER"] == 24
    assert train_preset["ADP_FEATURE_SET"] == "compact_residual"


def test_two_lane_residual_training_preset_enables_residual_lookahead() -> None:
    preset = config.load_preset(Path("configs/two_lane_training_residual_200_random.yaml"))
    assert preset["TRAIN_EPISODES"] == 200
    assert preset["TRAIN_INCIDENT_SELECTION"] == "random"
    assert preset["ADP_ACTION_SCORING_MODE"] == "residual_lookahead"
    assert preset["ADP_LOOKAHEAD_DEPTH"] == 2
    assert preset["ADP_LANE_FAIRNESS_WEIGHT"] == 0.0
