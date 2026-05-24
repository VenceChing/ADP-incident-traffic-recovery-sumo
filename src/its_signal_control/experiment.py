import os
from typing import Any

import random
import traci

from .agent import ADPAgent
from .config import *
from .controllers import (
    get_action_pressure_features,
    get_agent_queues,
    select_adp_action,
    select_greedy_action,
    select_max_pressure_action,
    update_adp_agents,
)
from .env import SumoEnv
from .metrics import (
    append_episode_metrics,
    get_agent_weight_l1_norms,
    load_agent_weights,
    print_action_trace,
    print_learning_status,
    read_metrics,
    render_eval_comparison,
    render_line_chart,
    reset_agent_weights,
    reset_metrics_file,
    save_agent_weights,
    summarize_eval_metrics,
    summarize_paired_eval_metrics,
)
from .traffic_model import (
    add_keepalive_vehicle,
    build_agents,
    build_controller_context,
    build_incident_candidates,
    build_sumo_cmd,
    build_sumo_args,
    build_tls_state,
    check_episode_status,
    format_incident_direction,
    get_incident_distance,
    get_incident_direction,
    get_queue_excess,
    get_switch_penalty,
    get_train_epsilon,
    reset_episode_detector,
    set_active_route_file,
    split_incidents,
)
from .utils import generate_routes
from .utils import cleanup_route_temp_files


def select_round_robin_action(sim_time: float) -> int:
    return int(sim_time // DECISION_INTERVAL) % 4


def run_episode(
    *,
    phase: str,
    controller: str,
    episode: int,
    seed: int,
    incident_edges: list[str],
    env: SumoEnv,
    agents: dict[str, ADPAgent],
    context: dict[str, Any],
    metrics_path: str,
    train_adp: bool,
) -> dict[str, Any]:
    random.seed(seed)
    traci.load(build_sumo_args(seed))
    env.incident_triggered = False
    add_keepalive_vehicle()
    reset_episode_detector()

    print(f"--- {phase.upper()} {controller} episode {episode} seed={seed} incident={incident_edges} ---")

    edge_ids = [edge_id for edge_id in traci.edge.getIDList() if not edge_id.startswith(":")]
    if RENDER_STRESS:
        env.init_stress_polygons(edge_ids)

    baseline_queues = {edge_id: 0.0 for edge_id in edge_ids}
    baseline_queue_sums = {edge_id: 0.0 for edge_id in edge_ids}
    baseline_queue_counts = {edge_id: 0 for edge_id in edge_ids}
    baseline_arrival_total = 0
    baseline_arrival_start = None
    arrival_history: list[tuple[float, int]] = []
    halting_ratio_history: list[tuple[float, float]] = []

    pre_total_queue_sum = 0.0
    pre_total_queue_count = 0
    pre_halting_ratio_sum = 0.0
    pre_halting_ratio_count = 0
    post_total_queue_sum = 0.0
    post_total_queue_count = 0
    max_post_total_queue = 0.0
    post_halting_ratio_sum = 0.0
    post_halting_ratio_count = 0
    max_post_halting_ratio = 0.0

    queue_excess_area = 0.0
    max_nonincident_queue_excess = 0.0
    final_nonincident_queue_excess = 0.0
    final_incident_queue = 0.0
    max_incident_queue = 0.0
    final_total_queue = 0.0
    final_halting_ratio = 0.0
    final_recent_halting_ratio = 0.0
    final_status = "TIMEOUT"
    final_baseline_arrival_rate = 0.0
    final_recent_arrival_rate = 0.0
    final_baseline_halting_ratio = 0.0
    final_success_halting_ratio_threshold = 0.0

    python_current_phases = {agent_id: 0 for agent_id in agents.keys()}
    episode_start_l1_norms = get_agent_weight_l1_norms(agents)
    fixed_rr_control = controller in {"fixed_time", "fixed_time_rr"}
    adp_control = controller in {"adp_train", "adp_eval"}
    epsilon = get_train_epsilon(episode) if train_adp else 0.0
    switch_count = 0
    keep_count = 0
    step = 0
    sim_time = traci.simulation.getTime()
    episode_ended = False

    while traci.simulation.getMinExpectedNumber() > 0 and not episode_ended:
        sim_time = traci.simulation.getTime()
        if sim_time >= SIM_END_TIME:
            final_status = "TIMEOUT"
            break

        step_cache: dict[str, dict[str, Any]] = {}
        target_actions: dict[str, int] = {}
        learning_active = sim_time >= INCIDENT_TIME
        rr_action = select_round_robin_action(sim_time)

        for agent_id, agent in agents.items():
            current_queues = get_agent_queues(env, agent_id, sim_time, incident_edges)
            current_phase = python_current_phases[agent_id]

            if not learning_active or fixed_rr_control:
                action = rr_action
                q_values = [0.0] * agent.num_phases
            elif controller == "greedy":
                action = select_greedy_action(agent, current_queues)
                q_values = [0.0] * agent.num_phases
            elif controller == "max_pressure":
                action = select_max_pressure_action(agent_id, context)
                q_values = [0.0] * agent.num_phases
            else:
                action, q_values = select_adp_action(
                    agent_id,
                    agent,
                    current_queues,
                    baseline_queues,
                    current_phase,
                    sim_time,
                    incident_edges,
                    epsilon,
                    context,
                )

            target_actions[agent_id] = action
            if adp_control and learning_active:
                dist_to_incident = get_incident_distance(agent_id, incident_edges)
                incident_direction = get_incident_direction(agent_id, incident_edges)
                time_discrete = int((sim_time - INCIDENT_TIME) // DECISION_INTERVAL)
                action_pressures, downstream_queues, downstream_capacities = get_action_pressure_features(agent_id, context)
                step_cache[agent_id] = {
                    "features": agent.extract_features(
                        current_queues,
                        current_phase,
                        dist_to_incident,
                        incident_direction,
                        time_discrete,
                        True,
                        action=action,
                        action_pressures=action_pressures,
                        downstream_queues=downstream_queues,
                        downstream_capacities=downstream_capacities,
                    ),
                    "action": action,
                    "current_queues": current_queues,
                    "current_phase": current_phase,
                    "action_pressures": action_pressures,
                    "downstream_queues": downstream_queues,
                    "downstream_capacities": downstream_capacities,
                }

            if TRACE_ACTIONS and step % (DECISION_INTERVAL * TRACE_ACTION_INTERVALS) == 0:
                print_action_trace(agent_id, agent, current_queues, current_phase, action, q_values)

        for sec in range(DECISION_INTERVAL):
            for agent_id in agents.keys():
                current_p = python_current_phases[agent_id]
                target_p = target_actions[agent_id]
                if current_p == target_p:
                    state_str = build_tls_state(context, agent_id, current_p, "G")
                elif sec < YELLOW_SECONDS:
                    state_str = build_tls_state(context, agent_id, current_p, "y")
                elif sec < YELLOW_SECONDS + ALL_RED_SECONDS:
                    state_str = context["tls_all_red"][agent_id]
                else:
                    state_str = build_tls_state(context, agent_id, target_p, "G")
                traci.trafficlight.setRedYellowGreenState(agent_id, state_str)

            substeps_per_second = max(1, int(round(1.0 / STEP_LENGTH)))
            for _ in range(substeps_per_second):
                traci.simulationStep()
                step += 1
                sim_time = traci.simulation.getTime()
                arrived_count = traci.simulation.getArrivedNumber()

                if BASELINE_WARMUP_TIME <= sim_time < INCIDENT_TIME:
                    baseline_arrival_total += arrived_count
                    if baseline_arrival_start is None:
                        baseline_arrival_start = sim_time
                if sim_time >= INCIDENT_TIME:
                    arrival_history.append((sim_time, arrived_count))
                    while arrival_history and sim_time - arrival_history[0][0] > FLOW_WINDOW:
                        arrival_history.pop(0)

                env.trigger_incident(incident_edges, current_time=sim_time, start_time=INCIDENT_TIME)

                if sim_time < INCIDENT_TIME:
                    for edge_id in edge_ids:
                        current_q = traci.edge.getLastStepHaltingNumber(edge_id)
                        if sim_time >= BASELINE_WARMUP_TIME:
                            baseline_queue_sums[edge_id] += current_q
                            baseline_queue_counts[edge_id] += 1
                            baseline_queues[edge_id] = (
                                baseline_queue_sums[edge_id] / baseline_queue_counts[edge_id]
                            )
                elif RENDER_STRESS:
                    env.render_queue_stress(baseline_queues, TAU, incident_edges)

                current_queues_all = {
                    edge_id: traci.edge.getLastStepHaltingNumber(edge_id)
                    for edge_id in edge_ids
                }
                total_queue = sum(current_queues_all.values())
                total_vehicles = traci.vehicle.getIDCount()
                halting_ratio = total_queue / total_vehicles if total_vehicles > 0 else 0.0
                nonincident_queue_excess, nonincident_max_excess = get_queue_excess(
                    current_queues_all,
                    baseline_queues,
                    incident_edges,
                )
                incident_queue = sum(current_queues_all.get(edge_id, 0.0) for edge_id in incident_edges)

                final_total_queue = total_queue
                final_halting_ratio = halting_ratio
                final_nonincident_queue_excess = nonincident_queue_excess
                final_incident_queue = incident_queue
                max_incident_queue = max(max_incident_queue, incident_queue)
                max_nonincident_queue_excess = max(max_nonincident_queue_excess, nonincident_max_excess)

                if BASELINE_WARMUP_TIME <= sim_time < INCIDENT_TIME:
                    pre_total_queue_sum += total_queue
                    pre_total_queue_count += 1
                    pre_halting_ratio_sum += halting_ratio
                    pre_halting_ratio_count += 1
                if sim_time >= INCIDENT_TIME:
                    post_total_queue_sum += total_queue
                    post_total_queue_count += 1
                    max_post_total_queue = max(max_post_total_queue, total_queue)
                    post_halting_ratio_sum += halting_ratio
                    post_halting_ratio_count += 1
                    max_post_halting_ratio = max(max_post_halting_ratio, halting_ratio)
                    queue_excess_area += nonincident_queue_excess * STEP_LENGTH
                    halting_ratio_history.append((sim_time, halting_ratio))
                    while halting_ratio_history and sim_time - halting_ratio_history[0][0] > FLOW_WINDOW:
                        halting_ratio_history.pop(0)

                final_baseline_arrival_rate = (
                    baseline_arrival_total / max(1.0, INCIDENT_TIME - baseline_arrival_start)
                    if baseline_arrival_start is not None
                    else 0.0
                )
                final_recent_arrival_rate = sum(count for _, count in arrival_history) / FLOW_WINDOW
                final_recent_halting_ratio = (
                    sum(value for _, value in halting_ratio_history) / len(halting_ratio_history)
                    if halting_ratio_history
                    else 0.0
                )
                final_baseline_halting_ratio = pre_halting_ratio_sum / max(1, pre_halting_ratio_count)
                final_success_halting_ratio_threshold = min(
                    SUCCESS_HALTING_RATIO_CAP,
                    final_baseline_halting_ratio * SUCCESS_HALTING_RATIO_MULTIPLIER
                    + SUCCESS_HALTING_RATIO_MARGIN,
                )

                status = check_episode_status(
                    current_queues_all,
                    baseline_queues,
                    current_time=sim_time,
                    incident_time=INCIDENT_TIME,
                    incident_edges=incident_edges,
                    traffic_rate=RATE,
                    baseline_arrival_rate=final_baseline_arrival_rate,
                    recent_arrival_rate=final_recent_arrival_rate,
                    baseline_halting_ratio=final_baseline_halting_ratio,
                    recent_halting_ratio=final_recent_halting_ratio,
                    current_halting_ratio=halting_ratio,
                )
                if status in {"GRIDLOCK", "SUCCESS"}:
                    final_status = status
                    if train_adp and adp_control and learning_active:
                        update_adp_agents(
                            agents,
                            env,
                            step_cache,
                            baseline_queues,
                            python_current_phases,
                            sim_time,
                            incident_edges,
                            is_gridlock=status == "GRIDLOCK",
                            context=context,
                        )
                    episode_ended = True
                    break

                if sim_time >= SIM_END_TIME:
                    final_status = "TIMEOUT"
                    episode_ended = True
                    break

            if episode_ended or sim_time >= SIM_END_TIME:
                break

        if episode_ended:
            break

        for agent_id in agents.keys():
            if learning_active:
                if python_current_phases[agent_id] == target_actions[agent_id]:
                    keep_count += 1
                else:
                    switch_count += 1
            python_current_phases[agent_id] = target_actions[agent_id]

        if train_adp and adp_control and learning_active:
            update_adp_agents(
                agents,
                env,
                step_cache,
                baseline_queues,
                python_current_phases,
                sim_time,
                incident_edges,
                is_gridlock=False,
                context=context,
            )

    episode_end_l1_norms = get_agent_weight_l1_norms(agents)
    total_l1_delta = sum(
        abs(episode_end_l1_norms[agent_id] - episode_start_l1_norms.get(agent_id, 0.0))
        for agent_id in episode_end_l1_norms
    )
    changed_agents = sum(
        abs(episode_end_l1_norms[agent_id] - episode_start_l1_norms.get(agent_id, 0.0)) > 1.0e-6
        for agent_id in episode_end_l1_norms
    )
    avg_weight_l1 = sum(episode_end_l1_norms.values()) / max(1, len(episode_end_l1_norms))
    gridlock_candidate_seconds = (
        max(0.0, sim_time - check_episode_status.gridlock_candidate_since)
        if check_episode_status.gridlock_candidate_since is not None
        else 0.0
    )
    success_candidate_seconds = (
        max(0.0, sim_time - check_episode_status.success_candidate_since)
        if check_episode_status.success_candidate_since is not None
        else 0.0
    )
    duration_after_incident = max(0.0, sim_time - INCIDENT_TIME)
    throughput_recovery_ratio = (
        final_recent_arrival_rate / final_baseline_arrival_rate
        if final_baseline_arrival_rate >= MIN_BASELINE_ARRIVAL_RATE
        else None
    )
    incident_direction_summary = ";".join(
        f"{agent_id}:{format_incident_direction(get_incident_direction(agent_id, incident_edges))}"
        for agent_id in sorted(agents.keys())
    )
    action_decisions = switch_count + keep_count
    switch_rate = switch_count / action_decisions if action_decisions > 0 else 0.0
    row = {
        "phase": phase,
        "controller": controller,
        "episode": episode,
        "seed": seed,
        "status": final_status,
        "incident_edges": "|".join(incident_edges),
        "incident_direction": incident_direction_summary,
        "end_time": f"{sim_time:.1f}",
        "duration_after_incident": f"{duration_after_incident:.1f}",
        "ttr": f"{duration_after_incident:.1f}" if final_status == "SUCCESS" else "",
        "avg_pre_total_queue": f"{pre_total_queue_sum / max(1, pre_total_queue_count):.4f}",
        "avg_post_total_queue": f"{post_total_queue_sum / max(1, post_total_queue_count):.4f}",
        "max_post_total_queue": f"{max_post_total_queue:.4f}",
        "final_total_queue": f"{final_total_queue:.4f}",
        "queue_excess_area": f"{queue_excess_area:.4f}",
        "avg_queue_excess": f"{queue_excess_area / max(1.0, duration_after_incident):.4f}",
        "max_nonincident_queue_excess": f"{max_nonincident_queue_excess:.4f}",
        "final_nonincident_queue_excess": f"{final_nonincident_queue_excess:.4f}",
        "final_incident_queue": f"{final_incident_queue:.4f}",
        "max_incident_queue": f"{max_incident_queue:.4f}",
        "avg_post_halting_ratio": f"{post_halting_ratio_sum / max(1, post_halting_ratio_count):.6f}",
        "recent_halting_ratio": f"{final_recent_halting_ratio:.6f}",
        "max_post_halting_ratio": f"{max_post_halting_ratio:.6f}",
        "final_halting_ratio": f"{final_halting_ratio:.6f}",
        "baseline_halting_ratio": f"{final_baseline_halting_ratio:.6f}",
        "success_halting_ratio_threshold": f"{final_success_halting_ratio_threshold:.6f}",
        "baseline_arrival_rate": f"{final_baseline_arrival_rate:.6f}",
        "recent_arrival_rate": f"{final_recent_arrival_rate:.6f}",
        "throughput_recovery_ratio": f"{throughput_recovery_ratio:.6f}"
        if throughput_recovery_ratio is not None
        else "",
        "success_candidate_seconds": f"{success_candidate_seconds:.1f}",
        "gridlock_candidate_seconds": f"{gridlock_candidate_seconds:.1f}",
        "switch_count": switch_count,
        "keep_count": keep_count,
        "switch_rate": f"{switch_rate:.6f}",
        "changed_agents": changed_agents,
        "total_l1_delta": f"{total_l1_delta:.6f}",
        "avg_weight_l1": f"{avg_weight_l1:.6f}",
        "adp_variant": ADP_VARIANT_LABEL if controller in {"adp_train", "adp_eval"} else "",
        "heuristic_note": (
            "ADP-inspired linear state-action value function with metric-aligned reward, scaled action features, and capacity-aware EWMA transition model"
            if controller in {"adp_train", "adp_eval"}
            else ""
        ),
    }
    append_episode_metrics(metrics_path, row)
    print(
        f"{phase} {controller} episode {episode}: status={final_status}, "
        f"duration={duration_after_incident:.1f}, excess_area={queue_excess_area:.1f}, "
        f"throughput={throughput_recovery_ratio if throughput_recovery_ratio is not None else 'n/a'}, "
        f"epsilon={epsilon:.3f}, switch_rate={switch_rate:.3f}"
    )
    return row


def main() -> None:
    active_route_file = ROUTE_FILE
    if REGENERATE_ROUTES or not os.path.exists(ROUTE_FILE):
        active_route_file = generate_routes(insertion_rate=RATE, generate_time=TIME, route_file=ROUTE_FILE)
    set_active_route_file(active_route_file)
    print(f"Using route file: {active_route_file}")

    env = SumoEnv(use_gui=USE_GUI, step_length=STEP_LENGTH)
    traci.start(build_sumo_cmd(RANDOM_SEED))

    try:
        tls_ids = list(traci.trafficlight.getIDList())
        edge_ids = [edge_id for edge_id in traci.edge.getIDList() if not edge_id.startswith(":")]
        print(f"Available traffic lights: {tls_ids}")

        context = build_controller_context(tls_ids)
        agents = build_agents(tls_ids)
        incident_candidates = build_incident_candidates(edge_ids, tls_ids)
        train_incidents, eval_incidents = split_incidents(incident_candidates)
        print(f"Incident split: train={len(train_incidents)}, eval={len(eval_incidents)}")
        print(f"ADP switch penalty from lost-time ratio: {get_switch_penalty():.3f}")

        if RUN_SINGLE_DEMO:
            reset_metrics_file(DEMO_METRICS_CSV_PATH)
            if DEMO_CONTROLLER in {"adp_train", "adp_eval"} and LOAD_WEIGHTS_FOR_EVALUATION:
                load_agent_weights(agents)
                print_learning_status(agents, "before demo")
            demo_incident_edges = (
                list(DEMO_INCIDENT_EDGES)
                if DEMO_INCIDENT_EDGES
                else list(eval_incidents[0] if eval_incidents else incident_candidates[0])
            )
            row = run_episode(
                phase="demo",
                controller=DEMO_CONTROLLER,
                episode=0,
                seed=DEMO_SEED,
                incident_edges=demo_incident_edges,
                env=env,
                agents=agents,
                context=context,
                metrics_path=DEMO_METRICS_CSV_PATH,
                train_adp=DEMO_CONTROLLER == "adp_train",
            )
            print(f"Demo result: {row}")

        if RUN_TRAINING:
            reset_metrics_file(TRAIN_METRICS_CSV_PATH)
            if RESET_WEIGHTS_FOR_TRAINING:
                reset_agent_weights(agents)
                print_learning_status(agents, "training reset")
            else:
                load_agent_weights(agents)
                print_learning_status(agents, "loaded before training")

            for episode in range(TRAIN_EPISODES):
                incident_edges = train_incidents[episode % len(train_incidents)]
                seed = RANDOM_SEED + episode
                run_episode(
                    phase="train",
                    controller="adp_train",
                    episode=episode,
                    seed=seed,
                    incident_edges=incident_edges,
                    env=env,
                    agents=agents,
                    context=context,
                    metrics_path=TRAIN_METRICS_CSV_PATH,
                    train_adp=True,
                )
                print_learning_status(agents, f"episode {episode} end")
            save_agent_weights(agents)
            render_line_chart(
                TRAINING_SVG_PATH,
                read_metrics(TRAIN_METRICS_CSV_PATH),
                "ADP training metrics by episode",
                [
                    ("Queue excess", ["queue_excess_area", "avg_queue_excess"]),
                    ("Duration", ["duration_after_incident", "ttr"]),
                    ("Flow recovery", ["throughput_recovery_ratio"]),
                    ("Learning delta", ["total_l1_delta"]),
                ],
            )

        if RUN_EVALUATION:
            reset_metrics_file(EVAL_METRICS_CSV_PATH)
            if not RUN_TRAINING and LOAD_WEIGHTS_FOR_EVALUATION:
                load_agent_weights(agents)
            print_learning_status(agents, "before evaluation")

            for controller in EVALUATION_CONTROLLERS:
                for episode in range(EVAL_EPISODES_PER_CONTROLLER):
                    incident_edges = eval_incidents[episode % len(eval_incidents)]
                    seed = RANDOM_SEED + 10_000 + episode
                    run_episode(
                        phase="eval",
                        controller=controller,
                        episode=episode,
                        seed=seed,
                        incident_edges=incident_edges,
                        env=env,
                        agents=agents,
                        context=context,
                        metrics_path=EVAL_METRICS_CSV_PATH,
                        train_adp=False,
                    )

            summary_rows = summarize_eval_metrics()
            paired_summary_rows = summarize_paired_eval_metrics()
            render_eval_comparison(summary_rows)
            render_line_chart(
                EVAL_SVG_PATH.replace(".svg", "_episodes.svg"),
                read_metrics(EVAL_METRICS_CSV_PATH),
                "Evaluation episode metrics",
                [
                    ("Queue excess", ["queue_excess_area", "avg_queue_excess"]),
                    ("Duration", ["duration_after_incident", "ttr"]),
                    ("Flow recovery", ["throughput_recovery_ratio"]),
                    ("Final halting ratio", ["final_halting_ratio"]),
                ],
            )
            print("Evaluation summary:")
            for row in summary_rows:
                print(row)
            print("Paired ADP comparison summary:")
            for row in paired_summary_rows:
                print(row)

    finally:
        try:
            traci.close(False)
        except traci.TraCIException:
            pass
        if active_route_file != ROUTE_FILE:
            cleanup_route_temp_files(ROUTE_FILE)
