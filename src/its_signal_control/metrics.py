import csv
import json
import math
import os
import random
from statistics import mean, median
from typing import Any

from .agent import ADPAgent
from .config import *


def get_agent_weight_l1_norms(agents: dict[str, ADPAgent]) -> dict[str, float]:
    return {
        agent_id: sum(abs(weight) for weight in agent.weights if math.isfinite(weight))
        for agent_id, agent in agents.items()
    }


def print_learning_status(
    agents: dict[str, ADPAgent],
    label: str,
    previous_l1_norms: dict[str, float] | None = None,
) -> None:
    l1_norms = get_agent_weight_l1_norms(agents)
    nonzero_agents = 0
    changed_agents = 0
    total_delta = 0.0

    for agent_id, agent in agents.items():
        if any(math.isfinite(weight) and abs(weight) > 1.0e-9 for weight in agent.weights):
            nonzero_agents += 1
        if previous_l1_norms is not None:
            delta = abs(l1_norms[agent_id] - previous_l1_norms.get(agent_id, 0.0))
            total_delta += delta
            if delta > 1.0e-6:
                changed_agents += 1

    avg_l1 = sum(l1_norms.values()) / max(1, len(l1_norms))
    message = (
        f"LEARNING CHECK [{label}]: "
        f"nonzero_agents={nonzero_agents}/{len(agents)}, "
        f"avg_weight_l1={avg_l1:.2f}"
    )
    if previous_l1_norms is not None:
        message += f", changed_agents={changed_agents}/{len(agents)}, total_l1_delta={total_delta:.4f}"
    print(message)


def sanitize_weights(weights: list[float], expected_dim: int) -> list[float] | None:
    if len(weights) != expected_dim:
        return None
    if not all(math.isfinite(weight) for weight in weights):
        return None
    return weights


def load_agent_weights(agents: dict[str, ADPAgent], weights_path: str | None = None) -> None:
    """
    載入 agent 權重
    
    Args:
        agents: Agent 字典
        weights_path: 可選，指定權重檔案路徑。如果不指定，使用預設路徑
    """
    if weights_path is None:
        candidate_paths = [WEIGHTS_PATH]
        if LEGACY_WEIGHTS_PATH != WEIGHTS_PATH:
            candidate_paths.append(LEGACY_WEIGHTS_PATH)
        source_path = next((path for path in candidate_paths if os.path.exists(path)), None)
    else:
        source_path = weights_path if os.path.exists(weights_path) else None
    
    if source_path is None:
        print("WARNING: No saved ADP weights found; evaluation will use current in-memory weights.")
        return
    with open(source_path, "r", encoding="utf-8") as handle:
        weights_data = json.load(handle)
    print(f"Loaded ADP weights from {source_path}.")
    agent_payloads = weights_data.get("agents", weights_data) if isinstance(weights_data, dict) else {}
    for agent_id, payload in agent_payloads.items():
        if agent_id not in agents:
            continue
        weights = payload.get("weights", []) if isinstance(payload, dict) else payload
        sanitized_weights = sanitize_weights(weights, agents[agent_id].feature_dim)
        if sanitized_weights is None:
            print(f"WARNING: Ignoring invalid saved weights for {agent_id}; starting from zeros.")
            continue
        agents[agent_id].weights = sanitized_weights
        if isinstance(payload, dict):
            agents[agent_id].import_transition_model(payload.get("transition_model", {}))


def save_agent_weights(agents: dict[str, ADPAgent], weights_path: str | None = None) -> None:
    """
    保存 agent 權重
    
    Args:
        agents: Agent 字典
        weights_path: 可選，指定權重檔案路徑。如果不指定，使用預設路徑
    """
    if weights_path is None:
        ensure_results_dir()
        save_path = WEIGHTS_PATH
    else:
        save_path = weights_path
    
    weights_data = {
        "schema_version": 2,
        "adp_variant": ADP_VARIANT_LABEL,
        "agents": {
            agent_id: {
                "weights": agent.weights,
                "transition_model": agent.export_transition_model(),
            }
            for agent_id, agent in agents.items()
        },
    }
    with open(save_path, "w", encoding="utf-8") as handle:
        json.dump(weights_data, handle)


def reset_agent_weights(agents: dict[str, ADPAgent]) -> None:
    for agent in agents.values():
        agent.reset_learning()


def print_action_trace(
    agent_id: str,
    agent: ADPAgent,
    current_queues: dict[str, float],
    current_phase: int,
    action: int,
    q_values: list[float],
) -> None:
    action_names = ["N", "E", "S", "W"]
    queue_by_action = [
        sum(current_queues.get(edge_id, 0.0) for edge_id in action_edges)
        for action_edges in agent.action_edges
    ]
    q_text = ", ".join(
        f"{action_names[idx]}={q_value:.1f}" if math.isfinite(q_value) else f"{action_names[idx]}=-inf"
        for idx, q_value in enumerate(q_values)
    )
    queue_text = ", ".join(
        f"{action_names[idx]}={queue_value:.0f}"
        for idx, queue_value in enumerate(queue_by_action)
    )
    print(
        f"TRACE {agent_id}: phase={action_names[current_phase]}, "
        f"queues[{queue_text}], q[{q_text}], chosen={action_names[action]}"
    )


def ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def reset_metrics_file(path: str) -> None:
    ensure_results_dir()
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDNAMES)
        writer.writeheader()


def append_episode_metrics(path: str, row: dict[str, Any]) -> None:
    ensure_results_dir()
    needs_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDNAMES)
        if needs_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in METRIC_FIELDNAMES})


def read_metrics(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def metric_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except ValueError:
        return 0.0


def summarize_eval_metrics() -> list[dict[str, Any]]:
    rows = read_metrics(EVAL_METRICS_CSV_PATH)
    summary_rows = []
    controllers = sorted({row["controller"] for row in rows})
    for controller in controllers:
        controller_rows = [row for row in rows if row["controller"] == controller]
        successful_ttrs = [metric_float(row, "ttr") for row in controller_rows if row["status"] == "SUCCESS"]
        durations = [metric_float(row, "duration_after_incident") for row in controller_rows]
        queue_excess = [metric_float(row, "queue_excess_area") for row in controller_rows]
        throughput = [
            metric_float(row, "throughput_recovery_ratio")
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

    ensure_results_dir()
    fieldnames = [
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
    with open(EVAL_SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)
    return summary_rows


def bootstrap_mean_ci(values: list[float], *, samples: int = 1000, seed: int = 1729) -> tuple[float, float]:
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


def summarize_paired_eval_metrics() -> list[dict[str, Any]]:
    rows = read_metrics(EVAL_METRICS_CSV_PATH)
    adp_rows = {
        (row["episode"], row["seed"], row["incident_edges"]): row
        for row in rows
        if row["controller"] == "adp_eval"
    }
    paired_rows = []
    for baseline in ["greedy", "max_pressure"]:
        baseline_rows = {
            (row["episode"], row["seed"], row["incident_edges"]): row
            for row in rows
            if row["controller"] == baseline
        }
        shared_keys = sorted(set(adp_rows) & set(baseline_rows))
        queue_diffs = [
            metric_float(adp_rows[key], "queue_excess_area")
            - metric_float(baseline_rows[key], "queue_excess_area")
            for key in shared_keys
        ]
        ci_low, ci_high = bootstrap_mean_ci(queue_diffs)
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
                "adp_variant": ADP_VARIANT_LABEL,
            }
        )

    ensure_results_dir()
    fieldnames = [
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
    with open(EVAL_PAIRED_SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(paired_rows)
    return paired_rows


def render_line_chart(path: str, rows: list[dict[str, str]], title: str, panels: list[tuple[str, list[str]]]) -> None:
    if not rows:
        return
    width = 1200
    panel_height = 170
    left = 80
    right = 30
    top = 45
    gap = 34
    height = top + len(panels) * panel_height + (len(panels) - 1) * gap + 45
    plot_width = width - left - right
    colors = {
        "queue_excess_area": "#2563eb",
        "avg_queue_excess": "#0f766e",
        "duration_after_incident": "#dc2626",
        "ttr": "#16a34a",
        "throughput_recovery_ratio": "#f59e0b",
        "final_halting_ratio": "#7c3aed",
        "total_l1_delta": "#0891b2",
    }

    def x_at(index: int) -> float:
        if len(rows) == 1:
            return left + plot_width / 2
        return left + plot_width * index / (len(rows) - 1)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="24" font-family="Arial" font-size="18" font-weight="700">{title}</text>',
    ]
    for idx, row in enumerate(rows):
        fill = {"SUCCESS": "#22c55e", "GRIDLOCK": "#ef4444", "TIMEOUT": "#64748b"}.get(
            row.get("status", ""),
            "#94a3b8",
        )
        svg.append(f'<circle cx="{x_at(idx):.1f}" cy="32" r="4" fill="{fill}"/>')

    for panel_idx, (panel_title, keys) in enumerate(panels):
        y0 = top + panel_idx * (panel_height + gap)
        y1 = y0 + panel_height
        values = [metric_float(row, key) for row in rows for key in keys]
        max_value = max(values) if values else 1.0
        if max_value <= 0:
            max_value = 1.0
        if "ratio" in panel_title.lower() or "recovery" in panel_title.lower():
            max_value = max(1.0, max_value)

        svg.extend(
            [
                f'<text x="{left}" y="{y0 - 10}" font-family="Arial" font-size="14" font-weight="700">{panel_title}</text>',
                f'<line x1="{left}" y1="{y1}" x2="{width - right}" y2="{y1}" stroke="#cbd5e1"/>',
                f'<line x1="{left}" y1="{y0}" x2="{left}" y2="{y1}" stroke="#cbd5e1"/>',
                f'<text x="10" y="{y1}" font-family="Arial" font-size="11" fill="#64748b">0</text>',
                f'<text x="10" y="{y0 + 10}" font-family="Arial" font-size="11" fill="#64748b">{max_value:.2f}</text>',
            ]
        )
        for key in keys:
            points = []
            for idx, row in enumerate(rows):
                value = metric_float(row, key)
                x = x_at(idx)
                y = y1 - (value / max_value) * panel_height
                points.append(f"{x:.1f},{y:.1f}")
            svg.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{colors.get(key, "#334155")}" stroke-width="2"/>'
            )
        legend_x = left + 10
        for key in keys:
            svg.append(
                f'<rect x="{legend_x}" y="{y0 + 10}" width="10" height="10" '
                f'fill="{colors.get(key, "#334155")}"/>'
            )
            svg.append(
                f'<text x="{legend_x + 15}" y="{y0 + 20}" font-family="Arial" '
                f'font-size="11" fill="#334155">{key}</text>'
            )
            legend_x += 220

    svg.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(svg))


def render_eval_comparison(summary_rows: list[dict[str, Any]]) -> None:
    if not summary_rows:
        return
    width = 1050
    height = 520
    left = 90
    top = 70
    chart_height = 330
    bar_width = 26
    group_gap = 62
    metric_gap = 32
    metrics = [
        ("success_rate", "#16a34a"),
        ("gridlock_rate", "#dc2626"),
        ("mean_ttr_success_only", "#0891b2"),
        ("mean_queue_excess_area", "#2563eb"),
        ("mean_throughput_recovery", "#f59e0b"),
    ]
    max_by_metric = {}
    for key, _ in metrics:
        values = [float(row[key]) for row in summary_rows if row[key] != ""]
        max_by_metric[key] = max(max(values) if values else 1.0, 1.0)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="32" font-family="Arial" font-size="20" font-weight="700">Evaluation comparison by controller</text>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{width - 40}" y2="{top + chart_height}" stroke="#cbd5e1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" stroke="#cbd5e1"/>',
    ]
    group_width = len(metrics) * metric_gap
    for group_idx, row in enumerate(summary_rows):
        x0 = left + 40 + group_idx * (group_width + group_gap)
        for metric_idx, (key, color) in enumerate(metrics):
            value = float(row[key]) if row[key] != "" else 0.0
            normalized = value / max_by_metric[key]
            bar_height = normalized * chart_height
            x = x0 + metric_idx * metric_gap
            y = top + chart_height - bar_height
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width}" height="{bar_height:.1f}" fill="{color}"/>')
        label_x = x0 + group_width / 2 - 20
        svg.append(
            f'<text x="{label_x:.1f}" y="{top + chart_height + 24}" font-family="Arial" '
            f'font-size="12" fill="#334155">{row["controller"]}</text>'
        )

    legend_x = left
    legend_y = height - 70
    for key, color in metrics:
        svg.append(f'<rect x="{legend_x}" y="{legend_y}" width="12" height="12" fill="{color}"/>')
        svg.append(
            f'<text x="{legend_x + 18}" y="{legend_y + 11}" font-family="Arial" '
            f'font-size="12" fill="#334155">{key}</text>'
        )
        legend_x += 195
    svg.append("</svg>")
    with open(EVAL_SVG_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(svg))
