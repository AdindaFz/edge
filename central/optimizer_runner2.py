import numpy as np

def hybrid_tabu(
    cpu_demands,
    mem_demands,
    latency_ms,
    cpu_caps,
    mem_caps,
    weight_energy=0.5,
    weight_latency=0.5,
    TABU_MAX_ITER=30
):

    import time
    N_tasks = len(cpu_demands)
    N_NODES = len(cpu_caps)

    network_delays = [1, 2]
    powers = [1.2, 2.5]

    current_assign = np.arange(N_tasks) % N_NODES
    best_assign = current_assign.copy()
    best_cost = float("inf")

    for it in range(TABU_MAX_ITER):

        # 🔥 diversification
        if it % 5 == 0:
            t_rand = np.random.randint(0, N_tasks)
            current_assign[t_rand] = np.random.randint(0, N_NODES)

        for t in range(N_tasks):

            current_node = current_assign[t]

            for new_node in range(N_NODES):

                if new_node == current_node:
                    continue

                trial = current_assign.copy()
                trial[t] = new_node

                # LOAD
                node_load = np.zeros(N_NODES)
                for i in range(N_tasks):
                    node_load[trial[i]] += cpu_demands[i]

                cpu_util = node_load / cpu_caps

                # 🔥 REALISTIC EXEC TIME
                exec_time = cpu_demands[t] / (cpu_caps[new_node] * (1 + cpu_util[new_node]))

                latency = exec_time + network_delays[new_node]
                energy = exec_time * powers[new_node]

                # NORMALIZE
                latency_norm = latency / 5
                energy_norm = energy / 0.01

                base_cost = weight_latency * latency_norm + weight_energy * energy_norm

                overload = cpu_util[new_node]

                cost = base_cost + 2.5 * overload**2

                if cost < best_cost:
                    best_cost = cost
                    best_assign = trial.copy()

        current_assign = best_assign.copy()

        # PRINT BEST UTIL
        best_load = np.zeros(N_NODES)
        for i in range(N_tasks):
            best_load[best_assign[i]] += cpu_demands[i]

        best_util = best_load / cpu_caps

        print(f"[UTIL] {best_util}")
        print(f"[TABU] Iter {it} | Cost={best_cost:.4f}")

    return best_assign
