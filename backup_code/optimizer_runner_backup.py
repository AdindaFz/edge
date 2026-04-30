import numpy as np


# =========================================================
# COST FUNCTION (GLOBAL, CONSISTENT)
# =========================================================
def compute_total_cost(
    assignments,
    cpu_demands,
    cpu_caps,
    network_delays,
    powers,
    weight_latency=0.6,
    weight_energy=0.4,
    LAT_REF=1.5,
    ENG_REF=0.2
):
    N_nodes = len(cpu_caps)
    N_tasks = len(assignments)

    node_load = np.zeros(N_nodes)
    for i in range(N_tasks):
        node_load[assignments[i]] += cpu_demands[i]

    cpu_util = node_load / cpu_caps

    total_cost = 0

    for t in range(N_tasks):
        node = assignments[t]

        # 🔥 VM-ALIGNED MODEL
        exec_time = cpu_demands[t] * (1 + cpu_util[node])

        latency = exec_time + network_delays[node]
        energy = exec_time * powers[node]

        # 🔥 NORMALIZATION
        latency_norm = latency / LAT_REF
        energy_norm = energy / ENG_REF

        total_cost += (
            weight_latency * latency_norm +
            weight_energy * energy_norm
        )

    return total_cost / N_tasks, cpu_util


# =========================================================
# HYBRID TABU + DIFFUSION (FINAL)
# =========================================================
def hybrid_tabu_diff(
    cpu_demands,
    cpu_caps,
    network_delays,
    powers,
    TABU_MAX_ITER=100,
    TABU_TENURE=10,
    NUM_MOVES=30,
    diffusion=None
):

    N_tasks = len(cpu_demands)
    N_nodes = len(cpu_caps)

    # ======================
    # INIT
    # ======================
    current_assign = np.random.randint(0, N_nodes, size=N_tasks)
    best_assign = current_assign.copy()

    best_cost, cpu_util = compute_total_cost(
        current_assign,
        cpu_demands,
        cpu_caps,
        network_delays,
        powers
    )

    tabu_dict = {}
    no_improve_counter = 0

    history = []

    # ======================
    # MAIN LOOP
    # ======================
    for it in range(TABU_MAX_ITER):

        best_candidate = None
        best_candidate_cost = float("inf")
        best_move = None

        # ======================
        # GENERATE MOVES
        # ======================
        for _ in range(NUM_MOVES):

            move_type = np.random.choice(["single", "swap"])

            # ---------- SINGLE MOVE ----------
            if move_type == "single":
                t = np.random.randint(0, N_tasks)

                if np.random.rand() < 0.5:
                    new_node = np.random.randint(0, N_nodes)
                else:
                    weights = 1 / (1 + cpu_util)
                    weights /= weights.sum()
                    new_node = np.random.choice(range(N_nodes), p=weights)

                if new_node == current_assign[t]:
                    continue

                trial = current_assign.copy()
                trial[t] = new_node

                move = ("single", t, new_node)

            # ---------- SWAP MOVE ----------
            else:
                t1 = np.random.randint(0, N_tasks)
                t2 = np.random.randint(0, N_tasks)

                if t1 == t2:
                    continue

                trial = current_assign.copy()
                trial[t1], trial[t2] = trial[t2], trial[t1]

                move = ("swap", min(t1, t2), max(t1, t2))

            # ======================
            # EVALUATE
            # ======================
            trial_cost, trial_util = compute_total_cost(
                trial,
                cpu_demands,
                cpu_caps,
                network_delays,
                powers
            )

            # penalty overload
            trial_cost += 5.0 * np.mean(trial_util**2)

            # ======================
            # TABU CHECK
            # ======================
            is_tabu = move in tabu_dict and tabu_dict[move] > it

            if is_tabu and trial_cost >= best_cost:
                continue

            if trial_cost < best_candidate_cost:
                best_candidate = trial
                best_candidate_cost = trial_cost
                best_move = move

        # ======================
        # APPLY MOVE
        # ======================
        if best_candidate is None:
            continue

        current_assign = best_candidate.copy()
        tabu_dict[best_move] = it + TABU_TENURE

        # ======================
        # UPDATE GLOBAL BEST
        # ======================
        if best_candidate_cost < best_cost:
            best_cost = best_candidate_cost
            best_assign = best_candidate.copy()
            no_improve_counter = 0
        else:
            no_improve_counter += 1

        # ======================
        # DIVERSIFICATION
        # ======================
        if no_improve_counter > 15:

            num_shake = int(0.2 * N_tasks)

            for _ in range(num_shake):
                t = np.random.randint(0, N_tasks)
                current_assign[t] = np.random.randint(0, N_nodes)

            no_improve_counter = 0

        # ======================
        # DIFFUSION
        # ======================
        if diffusion is not None and no_improve_counter > 5:

            refined = diffusion.refine(
                best_assign,
                cpu_demands,
                cpu_caps
            )

            refined_cost, _ = compute_total_cost(
                refined,
                cpu_demands,
                cpu_caps,
                network_delays,
                powers
            )

            if refined_cost < best_cost:
                best_cost = refined_cost
                best_assign = refined.copy()

            print(f"[DIFF] Applied at iter {it} | Cost={best_cost:.4f}")
            no_improve_counter = 0

        # ======================
        # LOG
        # ======================
        history.append(best_cost)
        print(f"[TABU+DIFF] Iter {it} | Cost={best_cost:.4f}")

    return best_assign, history

def compute_total_cost(assignments, cpu_demands, cpu_caps, network_delays, powers,
                       weight_latency=0.6, weight_energy=0.4,
                       LAT_REF=1.5, ENG_REF=0.190):

    N_nodes = len(cpu_caps)
    N_tasks = len(assignments)

    node_load = np.zeros(N_nodes)
    for i in range(N_tasks):
        node_load[assignments[i]] += cpu_demands[i]

    cpu_util = node_load / cpu_caps

    total_cost = 0

    for t in range(N_tasks):
        node = assignments[t]

        exec_time = cpu_demands[t] / (cpu_caps[node] * (1 + cpu_util[node]))
        latency = exec_time + network_delays[node]
        energy = exec_time * powers[node]

        # 🔥 NORMALIZATION
        latency_norm = latency / LAT_REF
        energy_norm = energy / ENG_REF

        total_cost += (
            weight_latency * latency_norm +
            weight_energy * energy_norm
        )

    return total_cost / N_tasks, cpu_util
