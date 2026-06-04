from __future__ import annotations

import csv
import math
import argparse
from pathlib import Path
from statistics import mean, median


REPO_ROOT = Path(__file__).resolve().parents[1]

METHODS = [
    ("checkerboard_ckpt_20", "Checkerboard ckpt 20", "Selected", "adp_eval", "checkerboard_ckpt20_eval24"),
    ("random_zero", "Random zero", "Selected", "adp_eval", "random_zero_eval24"),
    ("grid4x4_transfer", "4x4 grid transfer", "Transfer", "adp_eval", "grid4x4_transfer_eval24"),
    ("greedy", "Greedy", "Baseline", "greedy", "greedy_eval24"),
    ("max_pressure", "Max pressure", "Baseline", "max_pressure", "max_pressure_eval24"),
    ("fixed_time", "Fixed time", "Baseline", "fixed_time_rr", "fixed_time_eval24"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def f(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    try:
        return float(value) if value != "" else math.nan
    except ValueError:
        return math.nan


def fmt(value: float, key: str) -> str:
    if math.isnan(value):
        return "n/a"
    if "rate" in key or "recovery" in key:
        return f"{value:.2f}"
    if abs(value) >= 1000:
        return f"{value:.0f}"
    return f"{value:.1f}"


def build_combined_summary(run_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for method_id, label, group, controller, run_dir in METHODS:
        summary_path = run_root / run_dir / "eval_summary.csv"
        if not summary_path.exists():
            print(f"Skipping missing summary: {summary_path}")
            continue
        summary = read_csv(summary_path)[0]
        rows.append(
            {
                "method_id": method_id,
                "label": label,
                "group": group,
                "controller": controller,
                "episodes": summary["episodes"],
                "success_rate": summary["success_rate"],
                "gridlock_rate": summary["gridlock_rate"],
                "mean_ttr_success_only": summary["mean_ttr_success_only"],
                "mean_queue_excess_area": summary["mean_queue_excess_area"],
                "mean_throughput_recovery": summary["mean_throughput_recovery"],
                "source": str(run_root / run_dir / "eval_summary.csv"),
            }
        )
    return rows


def build_pairwise_vs_greedy(run_root: Path) -> list[dict[str, object]]:
    greedy_metrics = run_root / "greedy_eval24" / "eval_metrics.csv"
    if not greedy_metrics.exists():
        return []
    greedy_rows = read_csv(greedy_metrics)
    greedy_by_key = {
        (row["episode"], row["seed"], row["incident_edges"]): row
        for row in greedy_rows
    }
    pairwise: list[dict[str, object]] = []
    for method_id, label, _, _, run_dir in METHODS:
        if method_id == "greedy":
            continue
        metrics_path = run_root / run_dir / "eval_metrics.csv"
        if not metrics_path.exists():
            continue
        candidate_rows = read_csv(metrics_path)
        candidate_by_key = {
            (row["episode"], row["seed"], row["incident_edges"]): row
            for row in candidate_rows
        }
        shared = sorted(set(candidate_by_key) & set(greedy_by_key))
        queue_diffs = [
            f(candidate_by_key[key], "queue_excess_area") - f(greedy_by_key[key], "queue_excess_area")
            for key in shared
        ]
        ttr_diffs = [
            f(candidate_by_key[key], "ttr") - f(greedy_by_key[key], "ttr")
            for key in shared
            if candidate_by_key[key]["status"] == "SUCCESS" and greedy_by_key[key]["status"] == "SUCCESS"
        ]
        pairwise.append(
            {
                "method_id": method_id,
                "label": label,
                "paired_episodes": len(shared),
                "candidate_successes": sum(1 for key in shared if candidate_by_key[key]["status"] == "SUCCESS"),
                "greedy_successes": sum(1 for key in shared if greedy_by_key[key]["status"] == "SUCCESS"),
                "candidate_only_successes": sum(
                    1
                    for key in shared
                    if candidate_by_key[key]["status"] == "SUCCESS" and greedy_by_key[key]["status"] != "SUCCESS"
                ),
                "greedy_only_successes": sum(
                    1
                    for key in shared
                    if candidate_by_key[key]["status"] != "SUCCESS" and greedy_by_key[key]["status"] == "SUCCESS"
                ),
                "both_success_ttr_pairs": len(ttr_diffs),
                "mean_queue_excess_minus_greedy": mean(queue_diffs) if queue_diffs else "",
                "median_queue_excess_minus_greedy": median(queue_diffs) if queue_diffs else "",
                "queue_excess_wins": sum(1 for diff in queue_diffs if diff < 0),
                "queue_excess_losses": sum(1 for diff in queue_diffs if diff > 0),
                "mean_ttr_minus_greedy_both_success": mean(ttr_diffs) if ttr_diffs else "",
                "median_ttr_minus_greedy_both_success": median(ttr_diffs) if ttr_diffs else "",
            }
        )
    return pairwise


def render_horizontal_chart(rows: list[dict[str, object]], path: Path, title: str) -> None:
    width = 1280
    left = 230
    right = 70
    panel_start = 100
    panel_gap = 52
    bar_h = 24
    row_step = 36
    panel_h = len(rows) * row_step - 12
    chart_w = width - left - right
    metrics = [
        ("success_rate", "Success rate", "higher is better", False),
        ("mean_ttr_success_only", "Mean TTR, success only", "lower is better", True),
        ("mean_queue_excess_area", "Mean queue excess area", "lower is better", True),
        ("mean_throughput_recovery", "Mean throughput recovery", "higher is better", False),
    ]
    colors = {
        "checkerboard_ckpt_20": "#e15759",
        "random_zero": "#4e79a7",
        "grid4x4_transfer": "#b07aa1",
        "greedy": "#59a14f",
        "max_pressure": "#76b7b2",
        "fixed_time": "#9c9c9c",
    }
    height = panel_start + len(metrics) * panel_h + (len(metrics) - 1) * panel_gap + 52
    row_order = ", ".join(str(row["label"]).replace(" ckpt 20", "") for row in rows)

    def value(row: dict[str, object], key: str) -> float:
        try:
            text = str(row[key])
            return float(text) if text != "" else math.nan
        except (KeyError, ValueError):
            return math.nan

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="40" y="44" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700" fill="#222">{title}</text>',
        f'<text x="40" y="70" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#555">Horizontal bar view, 24-episode incident-recovery evaluation. Row order: {row_order}.</text>',
    ]

    for idx, (key, title, note, lower_is_better) in enumerate(metrics):
        y0 = panel_start + idx * (panel_h + panel_gap)
        y1 = y0 + panel_h
        vals = [value(row, key) for row in rows if not math.isnan(value(row, key))]
        max_val = max(vals) if vals else 1.0
        if "rate" in key or "recovery" in key:
            max_val = max(1.0, max_val)
        if max_val <= 0:
            max_val = 1.0
        scale_max = max_val * 1.08
        best_id = None
        if vals:
            candidates = [(str(row["method_id"]), value(row, key)) for row in rows if not math.isnan(value(row, key))]
            best_id = (min if lower_is_better else max)(candidates, key=lambda item: item[1])[0]

        tick_count = 4
        svg.extend(
            [
                f'<text x="40" y="{y0 - 14}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="700" fill="#222">{title} ({note})</text>',
            ]
        )
        for tick in range(tick_count + 1):
            x = left + chart_w * tick / tick_count
            tick_value = max_val * tick / tick_count
            svg.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="#e6e6e6"/>')
            svg.append(
                f'<text x="{x:.1f}" y="{y1 + 18}" text-anchor="middle" '
                f'font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="#666">{fmt(tick_value, key)}</text>'
            )
        for row_idx, row in enumerate(rows):
            method_id = str(row["method_id"])
            label = str(row["label"])
            val = value(row, key)
            y = y0 + 4 + row_idx * row_step
            bar_w = 0.0 if math.isnan(val) else (val / scale_max) * chart_w
            is_best = method_id == best_id
            svg.append(
                f'<text x="216" y="{y + 17}" text-anchor="end" '
                f'font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#333">{label}</text>'
            )
            if math.isnan(val):
                svg.append(
                    f'<text x="{left + 8}" y="{y + 17}" font-family="Segoe UI, Arial, sans-serif" '
                    f'font-size="12" fill="#777">n/a</text>'
                )
                continue
            svg.append(
                f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" '
                f'fill="{colors.get(method_id, "#9c9c9c")}" rx="2"/>'
            )
            svg.append(
                f'<text x="{min(left + bar_w + 8, width - right + 8):.1f}" y="{y + 17}" '
                f'text-anchor="start" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#222">{fmt(val, key)}</text>'
            )
            if is_best:
                svg.append(
                    f'<text x="{min(left + bar_w + 54, width - right + 8):.1f}" y="{y + 17}" '
                    f'font-family="Segoe UI, Arial, sans-serif" font-size="11" fill="#666">best</text>'
                )

    svg.append("</svg>")
    path.write_text("\n".join(svg), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real-map comparison CSVs and SVG chart.")
    parser.add_argument(
        "--run-root",
        default=str(REPO_ROOT / "outputs" / "runs" / "real_world_final_reproduction_rate1000"),
        help="Directory containing *_eval24 result folders.",
    )
    parser.add_argument("--output-dir", default="", help="Defaults to <run-root>/selected_methods_vs_baselines.")
    parser.add_argument("--title", default="Real-world Performance Comparison: ADP vs Baselines")
    args = parser.parse_args()

    run_root = Path(args.run_root)
    out_dir = Path(args.output_dir) if args.output_dir else run_root / "selected_methods_vs_baselines"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_combined_summary(run_root)
    if not summary:
        raise SystemExit(f"No eval_summary.csv files found under {run_root}")
    write_csv(
        out_dir / "combined_summary.csv",
        summary,
        [
            "method_id",
            "label",
            "group",
            "controller",
            "episodes",
            "success_rate",
            "gridlock_rate",
            "mean_ttr_success_only",
            "mean_queue_excess_area",
            "mean_throughput_recovery",
            "source",
        ],
    )
    pairwise = build_pairwise_vs_greedy(run_root)
    if pairwise:
        write_csv(out_dir / "pairwise_vs_greedy.csv", pairwise, list(pairwise[0].keys()))
    render_horizontal_chart(summary, out_dir / "selected_methods_vs_baselines_horizontal_v2.svg", args.title)


if __name__ == "__main__":
    main()
