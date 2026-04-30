import time
import numpy as np

from central.simulation_model import (
    energy_of_configuration,
    latency_of_configuration,
    calibrated_active_time,
)

HIGH_TIER_IDLE_POWER_THRESHOLD_W = 20.0
LOW_TIER_QUEUE_RELEASE_UTIL = 0.82
HIGH_TIER_SOFT_GATE_PENALTY = 0.18
HIGH_TIER_HARD_GATE_PENALTY = 1.75


def hybrid_tabu_diff(
    cpu_demands,
    cpu_caps,
    mem_demands,
    mem_caps,
    latency_ms,
    idle_powers=None,
    max_powers=None,
    init_assign=None,
    TABU_MAX_ITER=300,
    TABU_TENURE=30,
    NUM_MOVES=70,
    E_ref=None,
    L_ref=None,
    energy_weight=0.68,
    high_power_penalty_weight=0.0,
):
    n_tasks = len(cpu_demands)
    n_nodes = len(cpu_caps)

    if init_assign is not None:
        current_assign = init_assign.copy()
    else:
        current_assign = np.random.randint(0, n_nodes, size=n_tasks)

    gbest_assign = current_assign.copy()
    gbest_cost, _ = compute_total_cost_energy_focused(
        current_assign,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        latency_ms,
        idle_powers=idle_powers,
        max_powers=max_powers,
        E_ref=E_ref,
        L_ref=L_ref,
        energy_weight=energy_weight,
        high_power_penalty_weight=high_power_penalty_weight,
    )

    print(f"[INIT] Initial cost: {gbest_cost:.4f}, assignment: {np.bincount(current_assign)}")

    tabu_dict = {}
    no_improve_counter = 0
    history = {"obj": [], "time": []}
    start_time = time.perf_counter()

    for it in range(TABU_MAX_ITER):
        _, cpu_util, mem_util = compute_node_utilization(
            current_assign,
            cpu_demands,
            cpu_caps,
            mem_demands,
            mem_caps,
        )

        best_candidate = None
        best_candidate_cost = float("inf")
        best_move = None

        for _ in range(NUM_MOVES):
            if np.random.rand() < 0.6:
                t = np.random.randint(0, n_tasks)

                node_weights = 1.0 / (1.0 + cpu_util)
                node_weights /= node_weights.sum()

                new_node = np.random.choice(range(n_nodes), p=node_weights)

                if new_node == current_assign[t]:
                    continue

                trial_assign = current_assign.copy()
                trial_assign[t] = new_node
                move = ("single", t, new_node)

            else:
                overloaded_nodes = np.where(cpu_util > 0.8)[0]
                underloaded_nodes = np.where(cpu_util < 0.6)[0]

                if len(overloaded_nodes) > 0 and len(underloaded_nodes) > 0:
                    overloaded_tasks = [
                        idx for idx in range(n_tasks)
                        if current_assign[idx] in overloaded_nodes
                    ]
                    underloaded_tasks = [
                        idx for idx in range(n_tasks)
                        if current_assign[idx] in underloaded_nodes
                    ]

                    if len(overloaded_tasks) == 0 or len(underloaded_tasks) == 0:
                        continue

                    t1 = np.random.choice(overloaded_tasks)
                    t2 = np.random.choice(underloaded_tasks)
                else:
                    t1 = np.random.randint(0, n_tasks)
                    t2 = np.random.randint(0, n_tasks)
                    if t1 == t2:
                        continue

                trial_assign = current_assign.copy()
                trial_assign[t1], trial_assign[t2] = trial_assign[t2], trial_assign[t1]
                move = ("swap", min(t1, t2), max(t1, t2))

            trial_cost, _ = compute_total_cost_energy_focused(
                trial_assign,
                cpu_demands,
                mem_demands,
                cpu_caps,
                mem_caps,
                latency_ms,
                idle_powers=idle_powers,
                max_powers=max_powers,
                E_ref=E_ref,
                L_ref=L_ref,
                energy_weight=energy_weight,
                high_power_penalty_weight=high_power_penalty_weight,
            )

            is_tabu = move in tabu_dict and tabu_dict[move] > it
            is_aspiration = trial_cost < gbest_cost

            if (not is_tabu or is_aspiration) and trial_cost < best_candidate_cost:
                best_candidate_cost = trial_cost
                best_candidate = trial_assign.copy()
                best_move = move

        if best_candidate is None:
            no_improve_counter += 1
        else:
            current_assign = best_candidate.copy()
            tabu_dict[best_move] = it + TABU_TENURE

            if best_candidate_cost < gbest_cost:
                gbest_cost = best_candidate_cost
                gbest_assign = best_candidate.copy()
                no_improve_counter = 0
                print(f"[TABU] Iter {it} | Cost={gbest_cost:.4f} OK")
            else:
                no_improve_counter += 1

        if no_improve_counter > 20:
            print(f"[SHAKE] Iter {it}: No improve for 20 iters, diversifying...")
            num_shake = max(1, int(0.2 * n_tasks))
            for _ in range(num_shake):
                t = np.random.randint(0, n_tasks)
                current_assign[t] = np.random.randint(0, n_nodes)
            no_improve_counter = 0

        history["obj"].append(gbest_cost)
        history["time"].append(time.perf_counter() - start_time)

        if it % 10 == 0:
            print(f"[TABU] Iter {it} | Cost={gbest_cost:.4f}")

    return gbest_assign, history


def compute_node_utilization(assignments, cpu_demands, cpu_caps, mem_demands, mem_caps):
    n_nodes = len(cpu_caps)
    cpu_used = np.zeros(n_nodes)
    mem_used = np.zeros(n_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    return cpu_used, cpu_util, mem_util


def compute_total_cost_energy_focused(
    assignments,
    cpu_demands,
    mem_demands,
    cpu_caps,
    mem_caps,
    latency_ms,
    idle_powers=None,
    max_powers=None,
    E_ref=None,
    L_ref=None,
    energy_weight=0.68,
    high_power_penalty_weight=0.0,
):
    n_nodes = len(cpu_caps)

    cpu_used = np.zeros(n_nodes)
    mem_used = np.zeros(n_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)
    cpu_util = np.clip(cpu_util, 0, 2.0)
    mem_util = np.clip(mem_util, 0, 2.0)

    high_tier_gate_penalty = 0.0
    if idle_powers is not None:
        high_tier_nodes = [
            idx for idx, idle_power in enumerate(idle_powers)
            if float(idle_power) >= HIGH_TIER_IDLE_POWER_THRESHOLD_W
        ]
        low_tier_nodes = [idx for idx in range(n_nodes) if idx not in high_tier_nodes]

        if high_tier_nodes and low_tier_nodes:
            low_tier_peak_util = float(np.max(cpu_util[low_tier_nodes])) if low_tier_nodes else 0.0
            if low_tier_peak_util < LOW_TIER_QUEUE_RELEASE_UTIL:
                high_tier_cpu_share = float(np.sum(cpu_used[high_tier_nodes]))
                total_cpu_share = float(np.sum(cpu_used))
                if total_cpu_share > 0:
                    high_tier_gate_penalty = (
                        HIGH_TIER_SOFT_GATE_PENALTY *
                        (high_tier_cpu_share / total_cpu_share) *
                        (LOW_TIER_QUEUE_RELEASE_UTIL - low_tier_peak_util)
                    )
                    if high_tier_cpu_share > 0:
                        high_tier_gate_penalty += HIGH_TIER_HARD_GATE_PENALTY * (
                            high_tier_cpu_share / total_cpu_share
                        )

    cpu_overload_penalty = np.sum(np.maximum(cpu_util - 0.85, 0.0) ** 2)
    mem_pressure_penalty = np.sum(np.maximum(mem_util - 0.9, 0.0) ** 2)
    resource_pressure_penalty = high_power_penalty_weight * (
        1.6 * cpu_overload_penalty + 0.8 * mem_pressure_penalty
    )

    total_energy = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        idle_powers=idle_powers,
        max_powers=max_powers,
    )

    latency, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms,
        cpu_caps,
        mem_caps,
    )

    if E_ref is not None and L_ref is not None:
        energy_norm = total_energy / max(E_ref, 1e-6)
        latency_norm = latency / max(L_ref, 1e-6)
    else:
        energy_norm = total_energy
        latency_norm = latency

    effective_energy_norm = energy_norm + resource_pressure_penalty

    cost = (
        energy_weight * effective_energy_norm +
        (1.0 - energy_weight) * latency_norm +
        high_tier_gate_penalty
    )

    return cost, cpu_util
