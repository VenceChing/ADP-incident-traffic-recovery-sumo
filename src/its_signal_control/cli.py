from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from . import config


def _repo_path(path: str | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config.REPO_ROOT / candidate


def _apply_runtime_config(args: argparse.Namespace, mode: str) -> Path:
    preset_path = _repo_path(args.preset)
    if preset_path is not None:
        config.apply_preset(preset_path)

    overrides: dict[str, Any] = {
        "RUN_SINGLE_DEMO": mode == "demo",
        "RUN_TRAINING": mode == "train",
        "RUN_EVALUATION": mode == "evaluate",
    }
    if mode == "train":
        overrides["RESET_WEIGHTS_FOR_TRAINING"] = not args.resume
        overrides["LOAD_WEIGHTS_FOR_EVALUATION"] = False
    if mode == "evaluate":
        overrides["LOAD_WEIGHTS_FOR_EVALUATION"] = True
    if args.headless:
        overrides["USE_GUI"] = False
        overrides["RENDER_STRESS"] = False
    if args.gui:
        overrides["USE_GUI"] = True
    if args.gui_window_size:
        overrides["GUI_WINDOW_SIZE"] = args.gui_window_size
    if args.gui_window_pos:
        overrides["GUI_WINDOW_POS"] = args.gui_window_pos
    if args.output_dir:
        overrides["RESULTS_DIR"] = str(_repo_path(args.output_dir))
    if args.weights:
        overrides["WEIGHTS_PATH"] = str(_repo_path(args.weights))
    config.apply_overrides(overrides)

    scenario_dir = _repo_path(config.SCENARIO_DIR)
    if scenario_dir is None or not scenario_dir.exists():
        raise FileNotFoundError(f"Scenario directory not found: {config.SCENARIO_DIR}")
    return scenario_dir


def _run(args: argparse.Namespace, mode: str) -> None:
    scenario_dir = _apply_runtime_config(args, mode)
    os.chdir(scenario_dir)

    # Import after presets are applied because the current implementation uses
    # module-level constants copied from config for compatibility.
    from . import experiment

    experiment.main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="its-signal-control")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--preset", default="configs/historical_best.yaml")
        subparser.add_argument("--weights")
        subparser.add_argument("--output-dir")
        subparser.add_argument("--headless", action="store_true")
        subparser.add_argument("--gui", action="store_true")
        subparser.add_argument("--gui-window-size")
        subparser.add_argument("--gui-window-pos")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate controllers.")
    add_common(evaluate)

    train = subparsers.add_parser("train", help="Train ADP weights.")
    add_common(train)
    train.add_argument("--resume", action="store_true")

    demo = subparsers.add_parser("demo", help="Run one configured demonstration episode.")
    add_common(demo)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        _run(args, "evaluate")
    elif args.command == "train":
        _run(args, "train")
    elif args.command == "demo":
        _run(args, "demo")
    else:
        parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
