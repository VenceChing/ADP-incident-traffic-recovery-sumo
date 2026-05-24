import csv
import json
import math
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import its_signal_control.config as config
import its_signal_control.controllers as controllers
import its_signal_control.experiment as experiment
import its_signal_control.metrics as metrics
import its_signal_control.traffic_model as traffic_model


MODULES = [config, controllers, experiment, metrics, traffic_model]
SWEEP_ROOT = Path("../../outputs/results_validation")


def set_constant(name: str, value) -> None:
    for module in MODULES:
        if hasattr(module, name):
            setattr(module, name, value)


def configure_run(
    *,
    rate: int,
    switch_penalty_scale: float,
    queue_priority_weight: float,
    alpha: float,
    td_error_cap: float,
    results_dir: Path,
    train_episodes: int,
    eval_episodes: int,
    controllers_to_eval: list[str],
) -> None:
    route_file = f"grid_4x4_rate{rate}.rou.xml"
    set_constant("RATE", rate)
    set_constant("ROUTE_FILE", route_file)
    set_constant("SWITCH_PENALTY_SCALE", switch_penalty_scale)
    set_constant("ADP_QUEUE_PRIORITY_WEIGHT", queue_priority_weight)
    set_constant("ALPHA", alpha)
    set_constant("ADP_MAX_ABS_TD_ERROR", td_error_cap)
    set_constant("RESULTS_DIR", str(results_dir))
    set_constant("WEIGHTS_PATH", str(results_dir / "adp_agent_weights.json"))
    set_constant("TRAIN_METRICS_CSV_PATH", str(results_dir / "train_metrics.csv"))
    set_constant("EVAL_METRICS_CSV_PATH", str(results_dir / "eval_metrics.csv"))
    set_constant("EVAL_SUMMARY_CSV_PATH", str(results_dir / "eval_summary.csv"))
    set_constant("EVAL_PAIRED_SUMMARY_CSV_PATH", str(results_dir / "eval_paired_summary.csv"))
    set_constant("TRAINING_SVG_PATH", str(results_dir / "training_metrics.svg"))
    set_constant("EVAL_SVG_PATH", str(results_dir / "eval_comparison.svg"))
    set_constant("RUN_SINGLE_DEMO", False)
    set_constant("RUN_TRAINING", True)
    set_constant("RUN_EVALUATION", True)
    set_constant("RESET_WEIGHTS_FOR_TRAINING", True)
    set_constant("LOAD_WEIGHTS_FOR_EVALUATION", True)
    set_constant("TRAIN_EPISODES", train_episodes)
    set_constant("EVAL_EPISODES_PER_CONTROLLER", eval_episodes)
    set_constant("EVALUATION_CONTROLLERS", controllers_to_eval)
    set_constant("USE_GUI", False)
    set_constant("RENDER_STRESS", False)
    set_constant("REGENERATE_ROUTES", False)


def read_summary_row(path: Path, controller: str) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["controller"] == controller:
            return row
    raise RuntimeError(f"Missing {controller} summary in {path}")


def read_paired_row(path: Path, baseline_controller: str) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["baseline_controller"] == baseline_controller:
            return row
    raise RuntimeError(f"Missing paired summary for {baseline_controller} in {path}")


def metric(row: dict[str, str], key: str, default: float = math.inf) -> float:
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def archive_results(results_dir: Path, label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = Path("../../outputs/results_archive") / f"{timestamp}_{label}"
    destination.mkdir(parents=True, exist_ok=True)
    if results_dir.exists():
        for path in results_dir.iterdir():
            target = destination / path.name
            if path.is_dir():
                shutil.copytree(path, target, dirs_exist_ok=True)
            else:
                shutil.copy2(path, target)
    return destination


def main() -> None:
    os.chdir(REPO_ROOT / config.SCENARIO_DIR)
    SWEEP_ROOT.mkdir(parents=True, exist_ok=True)
    archive_results(Path("../../outputs/runs/validation_final"), "pre_validation_sweep")
    final_train_episodes = config.TRAIN_EPISODES
    final_eval_episodes = config.EVAL_EPISODES_PER_CONTROLLER

    sweep_rows: list[dict[str, str]] = []
    for rate in config.VALIDATION_RATE_CANDIDATES:
        for switch_scale in config.VALIDATION_SWITCH_PENALTY_SCALES:
            for queue_weight in config.VALIDATION_QUEUE_PRIORITY_WEIGHTS:
                for alpha in config.VALIDATION_ALPHA_CANDIDATES:
                    for td_error_cap in config.VALIDATION_TD_ERROR_CAPS:
                        run_name = (
                            f"rate{rate}_switch{switch_scale:g}_queue{queue_weight:g}_"
                            f"alpha{alpha:g}_td{td_error_cap:g}"
                        )
                        results_dir = SWEEP_ROOT / run_name
                        print(f"=== VALIDATION {run_name} ===")
                        configure_run(
                            rate=rate,
                            switch_penalty_scale=switch_scale,
                            queue_priority_weight=queue_weight,
                            alpha=alpha,
                            td_error_cap=td_error_cap,
                            results_dir=results_dir,
                            train_episodes=config.VALIDATION_TRAIN_EPISODES,
                            eval_episodes=config.VALIDATION_EVAL_EPISODES,
                            controllers_to_eval=["greedy", "max_pressure", "adp_eval"],
                        )
                        experiment.main()
                        summary = read_summary_row(results_dir / "eval_summary.csv", "adp_eval")
                        greedy_summary = read_summary_row(results_dir / "eval_summary.csv", "greedy")
                        max_pressure_summary = read_summary_row(results_dir / "eval_summary.csv", "max_pressure")
                        paired_greedy = read_paired_row(
                            results_dir / "eval_paired_summary.csv",
                            "greedy",
                        )
                        paired_max_pressure = read_paired_row(
                            results_dir / "eval_paired_summary.csv",
                            "max_pressure",
                        )
                        sweep_row = {
                            "run_name": run_name,
                            "rate": str(rate),
                            "switch_penalty_scale": str(switch_scale),
                            "queue_priority_weight": str(queue_weight),
                            "alpha": str(alpha),
                            "td_error_cap": str(td_error_cap),
                            "greedy_success_rate": greedy_summary["success_rate"],
                            "greedy_gridlock_rate": greedy_summary["gridlock_rate"],
                            "max_pressure_success_rate": max_pressure_summary["success_rate"],
                            "max_pressure_gridlock_rate": max_pressure_summary["gridlock_rate"],
                            "paired_greedy_mean_queue_diff": paired_greedy["mean_queue_excess_diff"],
                            "paired_max_pressure_mean_queue_diff": paired_max_pressure["mean_queue_excess_diff"],
                            **summary,
                        }
                        sweep_rows.append(sweep_row)

    sweep_summary_path = SWEEP_ROOT / "sweep_summary.csv"
    fieldnames = list(sweep_rows[0].keys())
    with sweep_summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sweep_rows)

    feasible_rows = [
        row
        for row in sweep_rows
        if (
            metric(row, "success_rate", 0.0) >= metric(row, "greedy_success_rate", 0.0)
            and metric(row, "gridlock_rate", math.inf) <= metric(row, "greedy_gridlock_rate", math.inf)
        )
    ]
    candidate_rows = feasible_rows or sweep_rows
    best = min(
        candidate_rows,
        key=lambda row: (
            metric(row, "paired_greedy_mean_queue_diff"),
            metric(row, "paired_max_pressure_mean_queue_diff"),
            metric(row, "mean_queue_excess_area"),
            metric(row, "mean_ttr_success_only"),
            -metric(row, "success_rate", 0.0),
        ),
    )
    with (SWEEP_ROOT / "best_config.json").open("w", encoding="utf-8") as handle:
        json.dump(best, handle, indent=2)

    print(f"Best validation config: {best}")

    final_results_dir = Path("../../outputs/runs/validation_final")
    configure_run(
        rate=int(best["rate"]),
        switch_penalty_scale=float(best["switch_penalty_scale"]),
        queue_priority_weight=float(best["queue_priority_weight"]),
        alpha=float(best["alpha"]),
        td_error_cap=float(best["td_error_cap"]),
        results_dir=final_results_dir,
        train_episodes=final_train_episodes,
        eval_episodes=final_eval_episodes,
        controllers_to_eval=["fixed_time_rr", "greedy", "max_pressure", "adp_eval"],
    )
    experiment.main()
    archive_results(
        final_results_dir,
        (
            f"rate{best['rate']}_adp_metric_reward_action_features_capacity_final_"
            f"switch{best['switch_penalty_scale']}_queue{best['queue_priority_weight']}_"
            f"alpha{best['alpha']}_td{best['td_error_cap']}"
        ),
    )


if __name__ == "__main__":
    main()
