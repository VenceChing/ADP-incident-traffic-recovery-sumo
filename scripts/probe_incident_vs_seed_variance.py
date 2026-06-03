from __future__ import annotations

import csv
import os
from pathlib import Path

import traci

from its_signal_control import config


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _controller_rows(rows: list[dict[str, str]], probe: str, controller: str) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["phase"] == probe and row["controller"] == controller
    ]


def _queue_values(rows: list[dict[str, str]]) -> list[float]:
    return [float(row["queue_excess_area"]) for row in rows]


def _success_rate(rows: list[dict[str, str]]) -> float:
    return sum(1 for row in rows if row["status"] == "SUCCESS") / max(1, len(rows))


def _summarize(metrics_path: Path, summary_path: Path) -> None:
    rows = list(csv.DictReader(metrics_path.open(newline="", encoding="utf-8")))
    probes = sorted({row["phase"] for row in rows})
    controllers = sorted({row["controller"] for row in rows})

    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "probe",
                "controller",
                "episodes",
                "success_rate",
                "mean_queue_excess_area",
                "min_queue_excess_area",
                "max_queue_excess_area",
                "range_queue_excess_area",
            ],
        )
        writer.writeheader()
        for probe in probes:
            for controller in controllers:
                subset = _controller_rows(rows, probe, controller)
                if not subset:
                    continue
                values = _queue_values(subset)
                writer.writerow(
                    {
                        "probe": probe,
                        "controller": controller,
                        "episodes": len(subset),
                        "success_rate": f"{_success_rate(subset):.6f}",
                        "mean_queue_excess_area": f"{_mean(values):.4f}",
                        "min_queue_excess_area": f"{min(values):.4f}",
                        "max_queue_excess_area": f"{max(values):.4f}",
                        "range_queue_excess_area": f"{max(values) - min(values):.4f}",
                    }
                )


def main() -> None:
    config.apply_preset(config.REPO_ROOT / "configs" / "three_lane_evaluation.yaml")
    results_dir = config.REPO_ROOT / "outputs" / "runs" / "three_lane_incident_seed_probe"
    weights_path = config.REPO_ROOT / "outputs" / "runs" / "three_lane_training_full_random" / "adp_agent_weights.json"
    config.apply_overrides(
        {
            "RESULTS_DIR": str(results_dir),
            "WEIGHTS_PATH": str(weights_path),
            "EVAL_EPISODES_PER_CONTROLLER": 0,
            "RUN_EVALUATION": False,
            "RUN_TRAINING": False,
            "RUN_SINGLE_DEMO": False,
            "LOAD_WEIGHTS_FOR_EVALUATION": True,
            "USE_GUI": False,
            "RENDER_STRESS": False,
        }
    )

    scenario_dir = config.REPO_ROOT / config.SCENARIO_DIR
    os.chdir(scenario_dir)

    from its_signal_control.experiment import run_episode
    from its_signal_control.metrics import load_agent_weights, print_learning_status, reset_metrics_file
    from its_signal_control.traffic_model import (
        build_agents,
        build_controller_context,
        build_incident_candidates,
        build_sumo_cmd,
        set_active_route_file,
        split_incidents,
    )

    results_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = results_dir / "probe_metrics.csv"
    summary_path = results_dir / "probe_summary.csv"
    reset_metrics_file(str(metrics_path))
    set_active_route_file(config.ROUTE_FILE)

    traci.start(build_sumo_cmd(config.RANDOM_SEED))
    try:
        tls_ids = list(traci.trafficlight.getIDList())
        edge_ids = [edge_id for edge_id in traci.edge.getIDList() if not edge_id.startswith(":")]
        context = build_controller_context(tls_ids)
        agents = build_agents(tls_ids, context)
        load_agent_weights(agents)
        print_learning_status(agents, "before incident/seed probe")

        _, eval_incidents = split_incidents(build_incident_candidates(edge_ids, tls_ids))
        fixed_incident = ["B2C2", "C2B2"]
        if fixed_incident not in eval_incidents:
            fixed_incident = list(eval_incidents[0])

        controllers = ["greedy", "adp_eval"]
        fixed_incident_seeds = [10007, 10008, 10009, 10010, 10011, 10012, 10013, 10014]
        fixed_seed = 10007

        episode = 0
        for controller in controllers:
            for seed in fixed_incident_seeds:
                run_episode(
                    phase="fixed_incident_vary_seed",
                    controller=controller,
                    episode=episode,
                    seed=seed,
                    incident_edges=list(fixed_incident),
                    env=__import__("its_signal_control.env", fromlist=["SumoEnv"]).SumoEnv(
                        use_gui=False,
                        step_length=config.STEP_LENGTH,
                    ),
                    agents=agents,
                    context=context,
                    metrics_path=str(metrics_path),
                    train_adp=False,
                )
                episode += 1

        for controller in controllers:
            for incident_edges in eval_incidents:
                run_episode(
                    phase="fixed_seed_vary_incident",
                    controller=controller,
                    episode=episode,
                    seed=fixed_seed,
                    incident_edges=list(incident_edges),
                    env=__import__("its_signal_control.env", fromlist=["SumoEnv"]).SumoEnv(
                        use_gui=False,
                        step_length=config.STEP_LENGTH,
                    ),
                    agents=agents,
                    context=context,
                    metrics_path=str(metrics_path),
                    train_adp=False,
                )
                episode += 1
    finally:
        try:
            traci.close(False)
        except traci.TraCIException:
            pass

    _summarize(metrics_path, summary_path)
    print(f"Wrote {metrics_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
