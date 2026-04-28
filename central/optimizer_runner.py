import time
import numpy as np

from central.simulation_model import energy_of_configuration, latency_of_configuration


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
    diffusion=None,
    E_ref=None,
    L_ref=None,
    energy_weight=0.6,
    high_power_penalty_weight=0.12,
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

        if diffusion is not None and (it % 10 == 0 or no_improve_counter > 15):
            refined = diffusion.refine(gbest_assign, cpu_demands, cpu_caps)
            refined_cost, _ = compute_total_cost_energy_focused(
                refined,
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

            if refined_cost < gbest_cost:
                gbest_cost = refined_cost
                gbest_assign = refined.copy()
                print(f"[DIFF] Iter {it} | Cost={gbest_cost:.4f} OK")
                no_improve_counter = 0

        history["obj"].append(gbest_cost)
        history["time"].append(time.perf_counter() - start_time)

        if it % 10 == 0:
            print(f"[TABU+DIFF] Iter {it} | Cost={gbest_cost:.4f}")

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
    energy_weight=0.6,
    high_power_penalty_weight=0.12,
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

    # Hard infeasible memory penalty
    if np.any(mem_util > 1.2):
        overflow = np.sum(np.maximum(mem_util - 1.0, 0.0))
        infeasible_penalty = 1000.0 * overflow
    else:
        infeasible_penalty = 0.0

    model_energy = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        idle_powers=idle_powers,
        max_powers=max_powers,
    )

    # Runtime-aligned proxy energy: same shape as offline estimator
    # (per-task effective util and per-task active service time).
    if idle_powers is None:
        idle_arr = np.full(n_nodes, 8.0)
    else:
        idle_arr = np.asarray(idle_powers, dtype=float)

    if max_powers is None:
        max_arr = np.full(n_nodes, 20.0)
    else:
        max_arr = np.asarray(max_powers, dtype=float)

    # Task generator uses CPU_TIME_UNIT_MS=250. Keep this aligned so
    # proxy energy follows runtime behavior (task-clock driven workload).
    cpu_time_unit_seconds = 0.25
    proxy_energy = 0.0
    for t, node in enumerate(assignments):
        cpu_ratio = min(float(cpu_demands[t]) / max(float(cpu_caps[node]), 1e-6), 1.0)
        mem_ratio = min(float(mem_demands[t]) / max(float(mem_caps[node]), 1e-6), 1.0)
        effective_util = min(0.8 * cpu_ratio + 0.2 * mem_ratio, 1.0)
        power_w = float(idle_arr[node]) + (float(max_arr[node]) - float(idle_arr[node])) * effective_util
        # In runtime, each task burns near target task-clock irrespective of
        # node tier; wall latency changes, but CPU-time demand is workload-driven.
        active_time_s = float(cpu_demands[t]) * cpu_time_unit_seconds
        proxy_energy += power_w * active_time_s

    # Heavier emphasis on runtime-aligned proxy to match offline estimator.
    total_energy = 0.1 * float(model_energy) + 0.9 * float(proxy_energy)

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

    # Penalize assignments that concentrate work on high-power nodes.
    if max_powers is not None and len(max_powers) > 0:
        max_powers_arr = np.asarray(max_powers, dtype=float)
        assigned_power = np.average(max_powers_arr[assignments], weights=np.maximum(cpu_demands, 1e-6))
        fleet_min = float(np.min(max_powers_arr))
        fleet_max = float(np.max(max_powers_arr))
        denom = max(fleet_max - fleet_min, 1e-6)
        # 0..1 where 1 means mostly high-power nodes.
        high_power_ratio = max(0.0, min((assigned_power - fleet_min) / denom, 1.0))
        high_power_penalty = high_power_penalty_weight * high_power_ratio
    else:
        high_power_penalty = 0.0

    cost = (
        energy_weight * energy_norm +
        (1.0 - energy_weight) * latency_norm +
        infeasible_penalty +
        high_power_penalty
    )

    return cost, cpu_util
