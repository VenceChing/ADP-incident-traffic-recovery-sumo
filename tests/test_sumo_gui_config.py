from pathlib import Path

from its_signal_control import config
from its_signal_control import traffic_model


def test_gui_sumo_args_include_demo_settings_and_delay(monkeypatch) -> None:
    monkeypatch.setattr(traffic_model, "USE_GUI", True)
    monkeypatch.setattr(traffic_model, "GUI_SETTINGS_FILE", "configs/demo_gui_settings.xml")
    monkeypatch.setattr(traffic_model, "GUI_DELAY_MS", 80)
    monkeypatch.setattr(traffic_model, "GUI_WINDOW_SIZE", "960,1040")
    monkeypatch.setattr(traffic_model, "GUI_WINDOW_POS", "0,0")

    args = traffic_model.build_sumo_args(seed=7)

    settings_index = args.index("--gui-settings-file")
    delay_index = args.index("--delay")
    size_index = args.index("--window-size")
    position_index = args.index("--window-pos")
    assert Path(args[settings_index + 1]) == config.REPO_ROOT / "configs/demo_gui_settings.xml"
    assert args[delay_index + 1] == "80"
    assert args[size_index + 1] == "960,1040"
    assert args[position_index + 1] == "0,0"


def test_headless_sumo_args_exclude_gui_only_settings(monkeypatch) -> None:
    monkeypatch.setattr(traffic_model, "USE_GUI", False)
    monkeypatch.setattr(traffic_model, "GUI_SETTINGS_FILE", "configs/demo_gui_settings.xml")
    monkeypatch.setattr(traffic_model, "GUI_DELAY_MS", 80)
    monkeypatch.setattr(traffic_model, "GUI_WINDOW_SIZE", "960,1040")
    monkeypatch.setattr(traffic_model, "GUI_WINDOW_POS", "0,0")

    args = traffic_model.build_sumo_args(seed=7)

    assert "--gui-settings-file" not in args
    assert "--delay" not in args
    assert "--window-size" not in args
    assert "--window-pos" not in args


def test_negative_gui_delay_omits_delay_argument(monkeypatch) -> None:
    monkeypatch.setattr(traffic_model, "USE_GUI", True)
    monkeypatch.setattr(traffic_model, "GUI_DELAY_MS", -1)

    args = traffic_model.build_sumo_args(seed=7)

    assert "--delay" not in args
