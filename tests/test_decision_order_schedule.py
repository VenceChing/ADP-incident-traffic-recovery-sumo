from its_signal_control.decision_intervals import DecisionOrderSchedule


AGENTS = ["A0", "A1", "B0", "B1", "C0", "C1"]


def test_decision_order_strategies_preserve_agents_without_duplicates() -> None:
    for strategy in ["unified", "distance_decay", "checkerboard", "ring", "random"]:
        schedule = DecisionOrderSchedule(
            strategy=strategy,
            agent_ids=AGENTS,
            incident_edges=["B0B1"],
            random_seed=7,
        )
        order = schedule.decision_order_for_timestep(0.0)

        assert len(order) == len(AGENTS)
        assert set(order) == set(AGENTS)


def test_distance_decay_orders_farther_nodes_first() -> None:
    schedule = DecisionOrderSchedule(
        strategy="distance_decay",
        agent_ids=["B1", "A0", "D3", "B2", "C2"],
        incident_edges=["B1B2"],
    )

    assert schedule.decision_order_for_timestep(0.0) == ["D3", "A0", "C2", "B1", "B2"]


def test_incident_manhattan_decay_alias_orders_farther_nodes_first() -> None:
    schedule = DecisionOrderSchedule(
        strategy="incident_manhattan_distance_decay",
        agent_ids=["B1", "A0", "D3", "B2", "C2"],
        incident_edges=["B1B2"],
    )

    assert schedule.decision_order_for_timestep(0.0) == ["D3", "A0", "C2", "B1", "B2"]


def test_incident_manhattan_premium_orders_nearer_nodes_first() -> None:
    schedule = DecisionOrderSchedule(
        strategy="incident_manhattan_distance_premium",
        agent_ids=["B1", "A0", "D3", "B2", "C2"],
        incident_edges=["B1B2"],
    )

    assert schedule.decision_order_for_timestep(0.0) == ["B1", "B2", "C2", "A0", "D3"]


def test_greedy_dynamic_orders_by_current_queue_total() -> None:
    schedule = DecisionOrderSchedule(
        strategy="greedy_dynamic",
        agent_ids=["A0", "B0", "C0"],
    )

    order = schedule.decision_order_for_timestep(
        0.0,
        {
            "A0": {"A0B0_0": 2.0, "A0B0_1": 3.0},
            "B0": 8.0,
            "C0": {"C0B0_0": 1.0},
        },
    )

    assert order == ["B0", "A0", "C0"]


def test_queue_length_premium_orders_by_longest_queue_total() -> None:
    schedule = DecisionOrderSchedule(
        strategy="queue_length_premium",
        agent_ids=["A0", "B0", "C0"],
    )

    order = schedule.decision_order_for_timestep(
        0.0,
        {
            "A0": {"A0B0_0": 2.0, "A0B0_1": 3.0},
            "B0": 8.0,
            "C0": {"C0B0_0": 1.0},
        },
    )

    assert order == ["B0", "A0", "C0"]


def test_queue_length_decay_orders_by_shortest_queue_total() -> None:
    schedule = DecisionOrderSchedule(
        strategy="queue_length_decay",
        agent_ids=["A0", "B0", "C0"],
    )

    order = schedule.decision_order_for_timestep(
        0.0,
        {
            "A0": {"A0B0_0": 2.0, "A0B0_1": 3.0},
            "B0": 8.0,
            "C0": {"C0B0_0": 1.0},
        },
    )

    assert order == ["C0", "A0", "B0"]


def test_random_order_is_deterministic_for_seed() -> None:
    order1 = DecisionOrderSchedule(
        strategy="random",
        agent_ids=AGENTS,
        random_seed=42,
    ).decision_order_for_timestep(0.0)
    order2 = DecisionOrderSchedule(
        strategy="random",
        agent_ids=AGENTS,
        random_seed=42,
    ).decision_order_for_timestep(0.0)

    assert order1 == order2


def test_get_neighbors_uses_four_connected_spatial_slots() -> None:
    schedule = DecisionOrderSchedule(
        strategy="distance_decay",
        agent_ids=["A0", "A1", "B0", "B1", "C1"],
    )

    assert schedule.get_neighbors("B1") == ["A1", "C1", "B0"]
