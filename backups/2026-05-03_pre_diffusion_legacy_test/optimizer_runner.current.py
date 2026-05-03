import time
import numpy as np

from config import MAX_CONCURRENT_TASKS
from central.simulation_model import (
    energy_of_configuration,
    latency_of_configuration,
    calibrated_active_time,
)

HIGH_TIER_IDLE_POWER_THRESHOLD_W = 20.0
NON_HIGH_TIER_QUEUE_RELEASE_UTIL = 0.86
NON_HIGH_TIER_AVG_RELEASE_UTIL = 0.76
HIGH_TIER_SOFT_GATE_PENALTY = 0.24
HIGH_TIER_HARD_GATE_PENALTY = 2.10
HIGH_TIER_EARLY_LOAD_PENALTY = 0.70
HIGH_TIER_ENERGY_SHARE_PENALTY = 1.55
HIGH_TIER_TASK_SHARE_PENALTY = 1.10
HIGH_TIER_ACTIVE_NODE_PENALTY = 0.24
TASK_CONCURRENCY_PENALTY = 0.18
ENERGY_OVERSHOOT_PENALTY = 1.6
MID_LARGE_TASK_OVERSHOOT_PENALTY = 2.8
MID_LARGE_TASK_RANGE_MIN = 351
MID_LARGE_TASK_RANGE_MAX = 450
REFERENCE_WINDOW_WIDTH = 1.0
SMALL_TASK_CPU_DEMAND_MAX = 1.45
MEDIUM_TASK_CPU_DEMAND_MAX = 2.35
SMALL_TASK_MEM_DEMAND_MAX = 0.30
MEDIUM_TASK_MEM_DEMAND_MAX = 0.62
HIGH_TIER_SMALL_TASK_PENALTY = 0.30
HIGH_TIER_MEDIUM_TASK_PENALTY = 0.16
HIGH_TIER_AVAILABLE_CPU_UTIL = 0.68
HIGH_TIER_AVAILABLE_MEM_UTIL = 0.74


def bounded_objective_score(value, reference=1.0, window=REFERENCE_WINDOW_WIDTH):
    # Map values to 0..1 using a linear window around the reference:
    # - scores <= 0 map to 0
    # - reference maps to 0.5
    # - scores >= reference + window map to 1
    value = max(float(value), 0.0)
    reference = max(float(reference), 1e-6)
    window = max(float(window), 1e-6)
    upper = reference + window

    if value <= 0.0:
        return 0.0
    if value >= upper:
        return 1.0

    return (value - 0.0) / (upper - 0.0)


def reporting_objective_scores(effective_energy_norm, effective_latency_norm):
    return {
        "bounded_energy_score": bounded_objective_score(effective_energy_norm),
        "bounded_latency_score": bounded_objective_score(effective_latency_norm),
    }


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
    diffusion_optimizer=None,
    stagnation_trigger=12,
    objective_fn=None,
):
    n_tasks = len(cpu_demands)
    n_nodes = len(cpu_caps)

    if objective_fn is None:
        objective_fn = compute_total_cost_energy_focused

    if init_assign is not None:
        current_assign = init_assign.copy()
    else:
        current_assign = np.random.randint(0, n_nodes, size=n_tasks)

    gbest_assign = current_assign.copy()
    gbest_cost, _ = objective_fn(
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

            trial_cost, _ = objective_fn(
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

        if diffusion_optimizer is not None and no_improve_counter >= stagnation_trigger:
            diff_assign = diffusion_optimizer.refine(
                current_assign,
                cpu_demands,
                cpu_caps,
                mem_demands=mem_demands,
                mem_caps=mem_caps,
            )
            diff_cost, _ = objective_fn(
                diff_assign,
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

            if diff_cost + 1e-12 < best_candidate_cost:
                best_candidate_cost = diff_cost

            if diff_cost + 1e-12 < gbest_cost:
                current_assign = diff_assign.copy()
                gbest_assign = diff_assign.copy()
                gbest_cost = diff_cost
                no_improve_counter = 0
                print(f"[DIFF] Iter {it} | Cost={gbest_cost:.4f} ESCAPE")
            elif diff_cost + 1e-12 < objective_fn(
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
            )[0]:
                current_assign = diff_assign.copy()
                no_improve_counter = max(0, stagnation_trigger - 4)
                print(f"[DIFF] Iter {it} | Improved current search basin to {diff_cost:.4f}")

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
    n_tasks = len(assignments)
    n_nodes = len(cpu_caps)

    cpu_used = np.zeros(n_nodes)
    mem_used = np.zeros(n_nodes)
    task_count = np.zeros(n_nodes, dtype=float)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]
        task_count[node] += 1.0

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)
    cpu_util = np.clip(cpu_util, 0, 2.0)
    mem_util = np.clip(mem_util, 0, 2.0)

    high_tier_gate_penalty = 0.0
    high_tier_energy_penalty = 0.0
    task_tier_mismatch_penalty = 0.0
    high_tier_task_penalty = 0.0
    if idle_powers is not None:
        high_tier_nodes = [
            idx for idx, idle_power in enumerate(idle_powers)
            if float(idle_power) >= HIGH_TIER_IDLE_POWER_THRESHOLD_W
        ]
        non_high_tier_nodes = [idx for idx in range(n_nodes) if idx not in high_tier_nodes]

        if high_tier_nodes and non_high_tier_nodes:
            non_high_peak_util = float(np.max(cpu_util[non_high_tier_nodes]))
            non_high_avg_util = float(np.mean(cpu_util[non_high_tier_nodes]))
            if (
                non_high_peak_util < NON_HIGH_TIER_QUEUE_RELEASE_UTIL
                or non_high_avg_util < NON_HIGH_TIER_AVG_RELEASE_UTIL
            ):
                high_tier_cpu_share = float(np.sum(cpu_used[high_tier_nodes]))
                total_cpu_share = float(np.sum(cpu_used))
                if total_cpu_share > 0:
                    capacity_share = float(np.sum(cpu_caps[high_tier_nodes]) / np.sum(cpu_caps))
                    cpu_share_ratio = high_tier_cpu_share / total_cpu_share
                    high_tier_task_share = float(np.sum(task_count[high_tier_nodes]) / max(np.sum(task_count), 1.0))
                    active_high_tier_nodes = float(np.sum(task_count[high_tier_nodes] > 0))
                    early_load_gap = max(
                        NON_HIGH_TIER_QUEUE_RELEASE_UTIL - non_high_peak_util,
                        NON_HIGH_TIER_AVG_RELEASE_UTIL - non_high_avg_util,
                    )
                    high_tier_gate_penalty = (
                        HIGH_TIER_SOFT_GATE_PENALTY *
                        cpu_share_ratio *
                        early_load_gap
                    )
                    if high_tier_cpu_share > 0:
                        high_tier_gate_penalty += HIGH_TIER_HARD_GATE_PENALTY * cpu_share_ratio
                        high_tier_gate_penalty += HIGH_TIER_EARLY_LOAD_PENALTY * max(
                            0.0,
                            cpu_share_ratio - capacity_share,
                        )
                    high_tier_energy_penalty = HIGH_TIER_ENERGY_SHARE_PENALTY * max(
                        0.0,
                        cpu_share_ratio - capacity_share,
                    ) ** 2
                    high_tier_task_penalty = HIGH_TIER_TASK_SHARE_PENALTY * max(
                        0.0,
                        high_tier_task_share - capacity_share,
                    ) ** 2
                    high_tier_task_penalty += HIGH_TIER_ACTIVE_NODE_PENALTY * active_high_tier_nodes

            # Penalize routing small and medium tasks to high-tier nodes while
            # non-high nodes still have enough spare CPU and memory headroom.
            for task_idx, node_idx in enumerate(assignments):
                if node_idx not in high_tier_nodes:
                    continue

                cpu_demand = float(cpu_demands[task_idx])
                mem_demand = float(mem_demands[task_idx])

                task_class_penalty = 0.0
                if (
                    cpu_demand <= SMALL_TASK_CPU_DEMAND_MAX
                    and mem_demand <= SMALL_TASK_MEM_DEMAND_MAX
                ):
                    task_class_penalty = HIGH_TIER_SMALL_TASK_PENALTY
                elif (
                    cpu_demand <= MEDIUM_TASK_CPU_DEMAND_MAX
                    and mem_demand <= MEDIUM_TASK_MEM_DEMAND_MAX
                ):
                    task_class_penalty = HIGH_TIER_MEDIUM_TASK_PENALTY

                if task_class_penalty <= 0.0:
                    continue

                # Only penalize if at least one non-high-tier node still has
                # enough projected capacity to host this task more efficiently.
                has_non_high_option = False
                for candidate_idx in non_high_tier_nodes:
                    projected_cpu = (
                        cpu_used[candidate_idx] + cpu_demand
                    ) / max(cpu_caps[candidate_idx], 1e-6)
                    projected_mem = (
                        mem_used[candidate_idx] + mem_demand
                    ) / max(mem_caps[candidate_idx], 1e-6)

                    if (
                        projected_cpu <= HIGH_TIER_AVAILABLE_CPU_UTIL
                        and projected_mem <= HIGH_TIER_AVAILABLE_MEM_UTIL
                    ):
                        has_non_high_option = True
                        break

                if has_non_high_option:
                    task_tier_mismatch_penalty += task_class_penalty

    cpu_overload_penalty = np.sum(np.maximum(cpu_util - 0.85, 0.0) ** 2)
    mem_pressure_penalty = np.sum(np.maximum(mem_util - 0.9, 0.0) ** 2)
    concurrency_pressure_penalty = np.sum(
        np.maximum((task_count / max(MAX_CONCURRENT_TASKS, 1)) - 1.0, 0.0) ** 2
    )
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

    energy_overshoot_coeff = ENERGY_OVERSHOOT_PENALTY
    if MID_LARGE_TASK_RANGE_MIN <= n_tasks <= MID_LARGE_TASK_RANGE_MAX:
        energy_overshoot_coeff = MID_LARGE_TASK_OVERSHOOT_PENALTY

    energy_overshoot_penalty = energy_overshoot_coeff * max(0.0, energy_norm - 1.0) ** 2

    effective_energy_norm = (
        energy_norm +
        energy_overshoot_penalty +
        high_tier_energy_penalty +
        high_tier_task_penalty +
        resource_pressure_penalty +
        TASK_CONCURRENCY_PENALTY * concurrency_pressure_penalty
    )
    effective_latency_norm = latency_norm + high_tier_gate_penalty

    cost = (
        energy_weight * effective_energy_norm +
        task_tier_mismatch_penalty +
        (1.0 - energy_weight) * effective_latency_norm
    )

    return cost, cpu_util
