from pathlib import Path

from its_signal_control import config


def test_historical_best_preset_loads_expected_values() -> None:
    preset = config.load_preset(Path("configs/historical_best.yaml"))
    assert preset["RATE"] == 2500
    assert preset["ADP_QUEUE_PRIORITY_WEIGHT"] == 2.0
    assert preset["ALPHA"] == 0.0005
    assert preset["EVALUATION_CONTROLLERS"] == ["fixed_time_rr", "greedy", "max_pressure", "adp_eval"]
