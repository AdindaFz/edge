import numpy as np

def hybrid_tabu_diff(
    cpu_demands,
    cpu_caps,
    network_delays,
    powers,
    weight_energy=0.5,
    weight_latency=0.5,
    TABU_MAX_ITER=30,
    diffusion=None
):

    N_tasks = len(cpu_demands)
    N_NODES = len(cpu_caps)

    current_assign = np.arange(N_tasks) % N_NODES
    best_assign = current_assign.copy()
    best_cost = float("inf")

    no_improve_counter = 0

    for it in range(TABU_MAX_ITER):

        # ======================
        # 🔥 TABU STEP (LOCAL SEARCH)
        # ======================
        best_candidate = None
        best_candidate_cost = float("inf")

        for t in range(N_tasks):

            for new_node in range(N_NODES):

                if new_node == current_assign[t]:
                    continue

                trial = current_assign.copy()
                trial[t] = new_node

                # ===== LOAD =====
                node_load = np.zeros(N_NODES)
                for i in range(N_tasks):
                    node_load[trial[i]] += cpu_demands[i]

                cpu_util = node_load / cpu_caps

                # ===== COST =====
                exec_time = cpu_demands[t] / (cpu_caps[new_node] * (1 + cpu_util[new_node]))
                latency = exec_time + network_delays[new_node]
                energy = exec_time * powers[new_node]

                #cost = weight_latency * latency + weight_energy * energy
                cost, cpu_util = compute_total_cost(
                    trial,
                    cpu_demands,
                    cpu_caps,
                    network_delays,
                    powers)
                # penalty overload (penting!)
                cost += 2.5 * cpu_util[new_node]**2

                if cost < best_candidate_cost:
                    best_candidate_cost = cost
                    best_candidate = trial.copy()

        # ======================
        # 🔥 MOVE
        # ======================
        current_assign = best_candidate.copy()

        # ======================
        # 🔥 GLOBAL UPDATE
        # ======================
        if best_candidate_cost < best_cost:
            best_cost = best_candidate_cost
            best_assign = best_candidate.copy()
            no_improve_counter = 0
        else:
            no_improve_counter += 1

        # ======================
        # 🔥 DIFFUSION TRIGGER
        # ======================
        if diffusion is not None and no_improve_counter >= 5:

            refined = diffusion.refine(
                best_assign,
                cpu_demands,
                cpu_caps
            )

            # ===== EVALUATE DIFF RESULT =====
            node_load = np.zeros(N_NODES)
            for i in range(N_tasks):
                node_load[refined[i]] += cpu_demands[i]

            cpu_util = node_load / cpu_caps

            total_cost = 0

            for t in range(N_tasks):
                node = refined[t]

                exec_time = cpu_demands[t] / (cpu_caps[node] * (1 + cpu_util[node]))
                latency = exec_time + network_delays[node]
                energy = exec_time * powers[node]

                total_cost += weight_latency * latency + weight_energy * energy

            # ===== UPDATE GLOBAL =====
            if total_cost < best_cost:
                best_cost = total_cost
                best_assign = refined.copy()

            no_improve_counter = 0

            print(f"[DIFF] Applied at iter {it} | Cost={best_cost:.4f}")

        # ======================
        # 🔥 LOG
        # ======================
        print(f"[TABU+DIFF] Iter {it} | Cost={best_cost:.4f}")

    return best_assign

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
