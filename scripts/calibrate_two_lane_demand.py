from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import its_signal_control.config as config
import its_signal_control.controllers as controllers
import its_signal_control.experiment as experiment
import its_signal_control.metrics as metrics
import its_signal_control.traffic_model as traffic_model
import its_signal_control.utils as utils


MODULES = [config, controllers, experiment, metrics, traffic_model, utils]
OUTPUT_ROOT = REPO_ROOT / "outputs" / "runs" / "two_lane_demand_calibration"


def set_constant(name: str, value) -> None:
    for module in MODULES:
        if hasattr(module, name):
            setattr(module, name, value)


def configure_rate(rate: int, episodes: int) -> Path:
    results_dir = OUTPUT_ROOT / f"rate{rate}"
    results_dir.mkdir(parents=True, exist_ok=True)
    route_path = results_dir / f"grid_4x4_2lane_rate{rate}.rou.xml"
    set_constant("RATE", rate)
    set_constant("ROUTE_FILE_PREFIX", "grid_4x4_2lane")
    set_constant("ROUTE_FILE", str(route_path))
    set_constant("SCENARIO_DIR", "scenarios/grid_4x4_2lane")
    set_constant("SUMO_CONFIG", "sim.sumocfg")
    set_constant("NETWORK_FILE", "grid_4x4_2lane.net.xml")
    set_constant("ACTION_SPACE", "two_lane_8")
    set_constant("RESULTS_DIR", str(results_dir))
    set_constant("WEIGHTS_PATH", str(results_dir / "adp_agent_weights.json"))
    set_constant("TRAIN_METRICS_CSV_PATH", str(results_dir / "train_metrics.csv"))
    set_constant("EVAL_METRICS_CSV_PATH", str(results_dir / "eval_metrics.csv"))
    set_constant("EVAL_SUMMARY_CSV_PATH", str(results_dir / "eval_summary.csv"))
    set_constant("EVAL_PAIRED_SUMMARY_CSV_PATH", str(results_dir / "eval_paired_summary.csv"))
    set_constant("TRAINING_SVG_PATH", str(results_dir / "training_metrics.svg"))
    set_constant("EVAL_SVG_PATH", str(results_dir / "eval_comparison.svg"))
    set_constant("RUN_SINGLE_DEMO", False)
    set_constant("RUN_TRAINING", False)
    set_constant("RUN_EVALUATION", True)
    set_constant("LOAD_WEIGHTS_FOR_EVALUATION", False)
    set_constant("EVALUATION_CONTROLLERS", ["fixed_time_rr", "greedy"])
    set_constant("EVAL_EPISODES_PER_CONTROLLER", episodes)
    set_constant("TIME", 1800)
    set_constant("SIM_END_TIME", max(config.TIME, config.INCIDENT_TIME + 1))
    set_constant("USE_GUI", False)
    set_constant("RENDER_STRESS", False)
    set_constant("REGENERATE_ROUTES", not route_path.exists())
    set_constant("ADP_VARIANT_LABEL", "two_lane_8_action_lane_fairness_v1")
    set_constant("ADP_LANE_FAIRNESS_WEIGHT", 0.10)
    set_constant("ADP_LANE_FAIRNESS_MARGIN", 5.0)
    return results_dir


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def metric(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "") or 0.0)
    except ValueError:
        return 0.0


def main() -> None:
    scenario_dir = REPO_ROOT / "scenarios" / "grid_4x4_2lane"
    os.chdir(scenario_dir)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    rates = list(config.TWO_LANE_RATE_CANDIDATES)
    episodes = 1
    all_rows: list[dict[str, str]] = []

    for rate in rates:
        print(f"=== TWO-LANE DEMAND CALIBRATION rate={rate} ===")
        results_dir = configure_rate(rate, episodes)
        experiment.main()
        for row in read_rows(results_dir / "eval_metrics.csv"):
            all_rows.append(
                {
                    "rate": str(rate),
                    "controller": row["controller"],
                    "status": row["status"],
                    "avg_pre_total_queue": row["avg_pre_total_queue"],
                    "baseline_halting_ratio": row["baseline_halting_ratio"],
                    "queue_excess_area": row["queue_excess_area"],
                    "duration_after_incident": row["duration_after_incident"],
                    "throughput_recovery_ratio": row["throughput_recovery_ratio"],
                }
            )

    summary_path = OUTPUT_ROOT / "calibration_summary.csv"
    fieldnames = [
        "rate",
        "controller",
        "status",
        "avg_pre_total_queue",
        "baseline_halting_ratio",
        "queue_excess_area",
        "duration_after_incident",
        "throughput_recovery_ratio",
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    selected_rate = rates[0]
    for rate in rates:
        rate_rows = [row for row in all_rows if int(row["rate"]) == rate]
        pre_stable = rate_rows and max(metric(row, "baseline_halting_ratio") for row in rate_rows) <= 0.85
        greedy_rows = [row for row in rate_rows if row["controller"] == "greedy"]
        greedy_not_immediate_recovery = any(
            row["status"] != "SUCCESS" or metric(row, "duration_after_incident") >= 500.0
            for row in greedy_rows
        )
        nontrivial = (
            max((metric(row, "queue_excess_area") for row in rate_rows), default=0.0) >= 1000.0
            and greedy_not_immediate_recovery
        )
        if pre_stable and nontrivial:
            selected_rate = rate
            break

    (OUTPUT_ROOT / "selected_rate.txt").write_text(f"{selected_rate}\n", encoding="utf-8")
    print(f"Selected two-lane rate: {selected_rate}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
