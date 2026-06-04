from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

MAP_PRESETS = {
    "real_world": {
        "adp": "configs/final_real_world_eval_checkerboard_neighbor_adp_ckpt20.yaml",
        "greedy": "configs/final_real_world_eval_greedy_baseline.yaml",
        "max_pressure": "configs/final_real_world_eval_max_pressure_baseline.yaml",
        "fixed_time": "configs/final_real_world_eval_fixed_time_baseline.yaml",
        "output": "outputs/runs/real_world_seed_search",
    },
    "real_world2": {
        "adp": "configs/final_real_world2_eval_checkerboard_neighbor_adp_ckpt20.yaml",
        "greedy": "configs/final_real_world2_eval_greedy_baseline.yaml",
        "max_pressure": "configs/final_real_world2_eval_max_pressure_baseline.yaml",
        "fixed_time": "configs/final_real_world2_eval_fixed_time_baseline.yaml",
        "output": "outputs/runs/real_world2_seed_search",
    },
}


def read_preset(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def write_seed_preset(base_preset: Path, output: Path, *, seed: int, episodes: int, results_dir: Path) -> None:
    lines = []
    replaced = set()
    replacements = {
        "RANDOM_SEED": str(seed),
        "EVAL_EPISODES_PER_CONTROLLER": str(episodes),
        "RESULTS_DIR": f'"{results_dir.as_posix()}"',
    }
    for line in read_preset(base_preset):
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            lines.append(line)
            continue
        key = stripped.split(":", 1)[0].strip()
        if key in replacements:
            lines.append(f"{key}: {replacements[key]}")
            replaced.add(key)
        else:
            lines.append(line)
    for key, value in replacements.items():
        if key not in replaced:
            lines.append(f"{key}: {value}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_summary(summary_path: Path) -> dict[str, str]:
    with summary_path.open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))


def run_eval(command: list[str]) -> None:
    env = os.environ.copy()
    pythonpath_parts = [str(REPO_ROOT / "src")]
    sumo_home = env.get("SUMO_HOME")
    if sumo_home:
        pythonpath_parts.append(str(Path(sumo_home) / "tools"))
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def as_float(row: dict[str, object], key: str, default: float = math.nan) -> float:
    try:
        value = row.get(key, "")
        return float(value) if value != "" else default
    except (TypeError, ValueError):
        return default


def rank_seeds(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    adp_rows = [row for row in rows if row["controller"] == "adp"]
    ranked = sorted(
        adp_rows,
        key=lambda row: (
            -as_float(row, "success_rate", 0.0),
            as_float(row, "gridlock_rate", 1.0),
            as_float(row, "mean_ttr_success_only", 1_000_000.0),
            as_float(row, "mean_queue_excess_area", 1_000_000_000.0),
            -as_float(row, "mean_throughput_recovery", 0.0),
        ),
    )
    return [
        {
            "rank": index,
            "map": row["map"],
            "seed": row["seed"],
            "controller_used_for_ranking": "adp",
            "episodes": row["episodes"],
            "success_rate": row["success_rate"],
            "gridlock_rate": row["gridlock_rate"],
            "mean_ttr_success_only": row["mean_ttr_success_only"],
            "mean_queue_excess_area": row["mean_queue_excess_area"],
            "mean_throughput_recovery": row["mean_throughput_recovery"],
            "run_dir": row["run_dir"],
        }
        for index, row in enumerate(ranked, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small seed sweep for real-map evaluation.")
    parser.add_argument("--map", choices=sorted(MAP_PRESETS), default="real_world")
    parser.add_argument("--seeds", default="7,17,27")
    parser.add_argument("--episodes", type=int, default=6)
    parser.add_argument(
        "--controllers",
        default="adp,greedy,max_pressure,fixed_time",
        help="Comma-separated names from: adp,greedy,max_pressure,fixed_time",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    map_config = MAP_PRESETS[args.map]
    seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    controllers = [name.strip() for name in args.controllers.split(",") if name.strip()]
    output_root = REPO_ROOT / map_config["output"]
    generated_dir = REPO_ROOT / "configs" / "generated_seed_sweeps" / args.map
    rows: list[dict[str, object]] = []

    for seed in seeds:
        for controller in controllers:
            if controller not in map_config:
                raise ValueError(f"Unsupported controller key: {controller}")
            run_dir = output_root / f"seed_{seed}" / controller
            generated_preset = generated_dir / f"seed_{seed}_{controller}.yaml"
            write_seed_preset(
                REPO_ROOT / map_config[controller],
                generated_preset,
                seed=seed,
                episodes=args.episodes,
                results_dir=run_dir,
            )
            command = [
                sys.executable,
                "-m",
                "its_signal_control.cli",
                "evaluate",
                "--preset",
                str(generated_preset.relative_to(REPO_ROOT)),
                "--headless",
            ]
            if args.dry_run:
                print(" ".join(command))
                continue
            run_eval(command)
            summary = read_summary(run_dir / "eval_summary.csv")
            rows.append(
                {
                    "map": args.map,
                    "seed": seed,
                    "controller": controller,
                    "episodes": summary["episodes"],
                    "success_rate": summary["success_rate"],
                    "gridlock_rate": summary["gridlock_rate"],
                    "mean_ttr_success_only": summary["mean_ttr_success_only"],
                    "mean_queue_excess_area": summary["mean_queue_excess_area"],
                    "mean_throughput_recovery": summary["mean_throughput_recovery"],
                    "run_dir": str(run_dir),
                }
            )

    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        summary_path = output_root / "seed_sweep_summary.csv"
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            fieldnames = list(rows[0].keys()) if rows else [
                "map",
                "seed",
                "controller",
                "episodes",
                "success_rate",
                "gridlock_rate",
                "mean_ttr_success_only",
                "mean_queue_excess_area",
                "mean_throughput_recovery",
                "run_dir",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {summary_path}")
        ranking = rank_seeds(rows)
        if ranking:
            ranking_path = output_root / "best_seed_ranking.csv"
            with ranking_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(ranking[0].keys()))
                writer.writeheader()
                writer.writerows(ranking)
            best = ranking[0]
            (output_root / "best_seed.txt").write_text(
                f"best_seed={best['seed']}\n"
                "ranking_controller=adp\n"
                "ranking_order=success_rate desc, gridlock_rate asc, "
                "mean_ttr_success_only asc, mean_queue_excess_area asc, "
                "mean_throughput_recovery desc\n",
                encoding="utf-8",
            )
            print(f"Wrote {ranking_path}")


if __name__ == "__main__":
    main()
