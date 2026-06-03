from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
from pathlib import Path
from statistics import mean, median

from its_signal_control import config


SUMMARY_FIELDNAMES = [
    "controller",
    "episodes",
    "success_rate",
    "gridlock_rate",
    "mean_ttr_success_only",
    "median_ttr_success_only",
    "worst_duration",
    "mean_queue_excess_area",
    "median_queue_excess_area",
    "mean_throughput_recovery",
]

PAIRED_FIELDNAMES = [
    "adp_controller",
    "baseline_controller",
    "pairs",
    "mean_queue_excess_diff",
    "median_queue_excess_diff",
    "queue_excess_diff_ci95_low",
    "queue_excess_diff_ci95_high",
    "adp_success_rate",
    "baseline_success_rate",
    "success_rate_diff",
    "adp_gridlock_rate",
    "baseline_gridlock_rate",
    "gridlock_rate_diff",
    "adp_variant",
]


def _run_eval(preset: Path, output_dir: Path, weights_path: Path | None) -> None:
    cmd = [
        sys.executable,
        "-m",
        "its_signal_control.cli",
        "evaluate",
        "--preset",
        str(preset),
        "--headless",
        "--output-dir",
        str(output_dir),
    ]
    if weights_path is not None:
        cmd.extend(["--weights", str(weights_path)])
    subprocess.run(cmd, check=True)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _metric_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except ValueError:
        return 0.0


def _bootstrap_mean_ci(values: list[float], *, samples: int = 1000, seed: int = 1729) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(mean(draw))
    means.sort()
    low_index = int(0.025 * (len(means) - 1))
    high_index = int(0.975 * (len(means) - 1))
    return means[low_index], means[high_index]


def _summarize_eval_metrics(rows: list[dict[str, str]], output_dir: Path) -> list[dict[str, object]]:
    summary_rows: list[dict[str, object]] = []
    for controller in sorted({row["controller"] for row in rows}):
        controller_rows = [row for row in rows if row["controller"] == controller]
        successful_ttrs = [
            _metric_float(row, "ttr")
            for row in controller_rows
            if row["status"] == "SUCCESS"
        ]
        durations = [_metric_float(row, "duration_after_incident") for row in controller_rows]
        queue_excess = [_metric_float(row, "queue_excess_area") for row in controller_rows]
        throughput = [
            _metric_float(row, "throughput_recovery_ratio")
            for row in controller_rows
            if row.get("throughput_recovery_ratio")
        ]
        total = len(controller_rows)
        gridlocks = sum(1 for row in controller_rows if row["status"] == "GRIDLOCK")
        successes = sum(1 for row in controller_rows if row["status"] == "SUCCESS")
        summary_rows.append(
            {
                "controller": controller,
                "episodes": total,
                "success_rate": successes / max(1, total),
                "gridlock_rate": gridlocks / max(1, total),
                "mean_ttr_success_only": mean(successful_ttrs) if successful_ttrs else "",
                "median_ttr_success_only": median(successful_ttrs) if successful_ttrs else "",
                "worst_duration": max(durations) if durations else "",
                "mean_queue_excess_area": mean(queue_excess) if queue_excess else "",
                "median_queue_excess_area": median(queue_excess) if queue_excess else "",
                "mean_throughput_recovery": mean(throughput) if throughput else "",
            }
        )
    _write_csv(output_dir / "eval_summary.csv", summary_rows, SUMMARY_FIELDNAMES)
    return summary_rows


def _summarize_paired_eval_metrics(
    rows: list[dict[str, str]],
    output_dir: Path,
    adp_variant: str,
) -> list[dict[str, object]]:
    adp_rows = {
        (row["episode"], row["seed"], row["incident_edges"]): row
        for row in rows
        if row["controller"] == "adp_eval"
    }
    paired_rows: list[dict[str, object]] = []
    for baseline in sorted({row["controller"] for row in rows} - {"adp_eval", "adp_train"}):
        baseline_rows = {
            (row["episode"], row["seed"], row["incident_edges"]): row
            for row in rows
            if row["controller"] == baseline
        }
        shared_keys = sorted(set(adp_rows) & set(baseline_rows))
        queue_diffs = [
            _metric_float(adp_rows[key], "queue_excess_area")
            - _metric_float(baseline_rows[key], "queue_excess_area")
            for key in shared_keys
        ]
        ci_low, ci_high = _bootstrap_mean_ci(queue_diffs)
        adp_successes = sum(1 for key in shared_keys if adp_rows[key]["status"] == "SUCCESS")
        baseline_successes = sum(1 for key in shared_keys if baseline_rows[key]["status"] == "SUCCESS")
        adp_gridlocks = sum(1 for key in shared_keys if adp_rows[key]["status"] == "GRIDLOCK")
        baseline_gridlocks = sum(1 for key in shared_keys if baseline_rows[key]["status"] == "GRIDLOCK")
        pairs = len(shared_keys)
        adp_success_rate = adp_successes / max(1, pairs)
        baseline_success_rate = baseline_successes / max(1, pairs)
        adp_gridlock_rate = adp_gridlocks / max(1, pairs)
        baseline_gridlock_rate = baseline_gridlocks / max(1, pairs)
        paired_rows.append(
            {
                "adp_controller": "adp_eval",
                "baseline_controller": baseline,
                "pairs": pairs,
                "mean_queue_excess_diff": mean(queue_diffs) if queue_diffs else "",
                "median_queue_excess_diff": median(queue_diffs) if queue_diffs else "",
                "queue_excess_diff_ci95_low": ci_low if queue_diffs else "",
                "queue_excess_diff_ci95_high": ci_high if queue_diffs else "",
                "adp_success_rate": adp_success_rate,
                "baseline_success_rate": baseline_success_rate,
                "success_rate_diff": adp_success_rate - baseline_success_rate,
                "adp_gridlock_rate": adp_gridlock_rate,
                "baseline_gridlock_rate": baseline_gridlock_rate,
                "gridlock_rate_diff": adp_gridlock_rate - baseline_gridlock_rate,
                "adp_variant": adp_variant,
            }
        )
    _write_csv(output_dir / "eval_paired_summary.csv", paired_rows, PAIRED_FIELDNAMES)
    return paired_rows


def _read_adp_summary(output_dir: Path) -> dict[str, str]:
    summary_path = output_dir / "eval_summary.csv"
    for row in _read_csv(summary_path):
        if row["controller"] == "adp_eval":
            return row
    raise RuntimeError(f"No adp_eval row found in {summary_path}")


def _read_adp_vs_greedy(output_dir: Path) -> dict[str, str]:
    paired_path = output_dir / "eval_paired_summary.csv"
    for row in _read_csv(paired_path):
        if row["baseline_controller"] == "greedy":
            return row
    raise RuntimeError(f"No ADP-vs-Greedy row found in {paired_path}")


def _write_temp_preset(
    base_preset: Path,
    target_preset: Path,
    episodes: int,
    controllers: list[str],
) -> None:
    lines = []
    seen_eval = False
    seen_controllers = False
    controller_text = "[" + ", ".join(f'"{controller}"' for controller in controllers) + "]"
    for raw_line in base_preset.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith("EVAL_EPISODES_PER_CONTROLLER:"):
            lines.append(f"EVAL_EPISODES_PER_CONTROLLER: {episodes}")
            seen_eval = True
        elif raw_line.strip().startswith("EVALUATION_CONTROLLERS:"):
            lines.append(f"EVALUATION_CONTROLLERS: {controller_text}")
            seen_controllers = True
        else:
            lines.append(raw_line)
    if not seen_eval:
        lines.append(f"EVAL_EPISODES_PER_CONTROLLER: {episodes}")
    if not seen_controllers:
        lines.append(f"EVALUATION_CONTROLLERS: {controller_text}")
    target_preset.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _baseline_cache_is_complete(output_dir: Path, episodes: int) -> bool:
    rows = _read_csv(output_dir / "eval_metrics.csv")
    greedy_rows = [row for row in rows if row.get("controller") == "greedy"]
    return len(greedy_rows) == episodes


def _merge_cached_baseline(
    candidate_output_dir: Path,
    baseline_output_dir: Path,
    adp_variant: str,
) -> None:
    baseline_rows = [
        row
        for row in _read_csv(baseline_output_dir / "eval_metrics.csv")
        if row.get("controller") == "greedy"
    ]
    adp_rows = [
        row
        for row in _read_csv(candidate_output_dir / "eval_metrics.csv")
        if row.get("controller") == "adp_eval"
    ]
    if not baseline_rows:
        raise RuntimeError(f"No cached greedy rows found in {baseline_output_dir}")
    if not adp_rows:
        raise RuntimeError(f"No adp_eval rows found in {candidate_output_dir}")

    merged_rows = baseline_rows + adp_rows
    fieldnames = list(adp_rows[0].keys())
    _write_csv(candidate_output_dir / "eval_metrics.csv", merged_rows, fieldnames)
    _summarize_eval_metrics(merged_rows, candidate_output_dir)
    _summarize_paired_eval_metrics(merged_rows, candidate_output_dir, adp_variant)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ADP checkpoint candidates on identical eval seeds.")
    parser.add_argument(
        "--preset",
        default="configs/three_lane_evaluation_50_incident_features.yaml",
        help="Base evaluation preset to reuse.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="outputs/runs/three_lane_training_50_incident_features/checkpoints",
        help="Directory containing episode_XXXX.json checkpoint files.",
    )
    parser.add_argument(
        "--final-weights",
        default="outputs/runs/three_lane_training_50_incident_features/adp_agent_weights.json",
        help="Final weights file to include if present.",
    )
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument(
        "--output-root",
        default="outputs/runs/three_lane_checkpoint_selection",
    )
    parser.add_argument(
        "--only-zero-final",
        action="store_true",
        help="Evaluate only zero weights and final weights; skip checkpoint files.",
    )
    args = parser.parse_args()

    repo_root = config.REPO_ROOT
    base_preset = repo_root / args.preset
    adp_variant = str(config.load_preset(base_preset).get("ADP_VARIANT_LABEL", config.ADP_VARIANT_LABEL))
    output_root = repo_root / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    baseline_preset = output_root / "checkpoint_eval_greedy_preset.yaml"
    adp_preset = output_root / "checkpoint_eval_adp_preset.yaml"
    _write_temp_preset(base_preset, baseline_preset, args.episodes, ["greedy"])
    _write_temp_preset(base_preset, adp_preset, args.episodes, ["adp_eval"])

    baseline_output_dir = output_root / "baseline_greedy_cache"
    if _baseline_cache_is_complete(baseline_output_dir, args.episodes):
        print(f"Reusing cached greedy baseline: {baseline_output_dir}")
    else:
        print(f"Evaluating cached greedy baseline: {baseline_output_dir}")
        _run_eval(baseline_preset, baseline_output_dir, None)

    candidates: list[tuple[str, Path | None]] = [("zero_weights", output_root / "missing_zero_weights.json")]
    if not args.only_zero_final:
        checkpoint_dir = repo_root / args.checkpoint_dir
        if checkpoint_dir.exists():
            candidates.extend((path.stem, path) for path in sorted(checkpoint_dir.glob("episode_*.json")))
    final_weights = repo_root / args.final_weights
    if final_weights.exists():
        candidates.append(("final", final_weights))
    else:
        print(f"WARNING: final weights not found; skipping final candidate: {final_weights}")

    rows = []
    for label, weights_path in candidates:
        output_dir = output_root / label
        print(f"Evaluating {label} ADP weights={weights_path or 'none'}")
        _run_eval(adp_preset, output_dir, weights_path)
        _merge_cached_baseline(output_dir, baseline_output_dir, adp_variant)
        summary = _read_adp_summary(output_dir)
        paired = _read_adp_vs_greedy(output_dir)
        rows.append(
            {
                "candidate": label,
                "weights_path": str(weights_path or ""),
                "episodes": summary["episodes"],
                "success_rate": summary["success_rate"],
                "mean_ttr_success_only": summary["mean_ttr_success_only"],
                "mean_queue_excess_area": summary["mean_queue_excess_area"],
                "mean_throughput_recovery": summary["mean_throughput_recovery"],
                "adp_vs_greedy_mean_queue_diff": paired["mean_queue_excess_diff"],
                "adp_vs_greedy_median_queue_diff": paired["median_queue_excess_diff"],
                "adp_success_rate": paired["adp_success_rate"],
                "greedy_success_rate": paired["baseline_success_rate"],
            }
        )

    summary_path = output_root / "checkpoint_selection_summary.csv"
    _write_csv(summary_path, rows, list(rows[0].keys()))

    best = min(rows, key=lambda row: float(row["mean_queue_excess_area"]))
    print(f"Wrote {summary_path}")
    print(f"Best by ADP mean queue excess: {best['candidate']} ({best['mean_queue_excess_area']})")


if __name__ == "__main__":
    main()
