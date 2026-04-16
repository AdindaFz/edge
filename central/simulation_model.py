import numpy as np
from config import MAX_CONCURRENT_TASKS
# ------------------------------------------------------------
# ENERGY MODEL (SOFT PENALTY)
# ------------------------------------------------------------
def energy_of_configuration(assignments,
                            cpu_demands,
                            mem_demands,
                            cpu_caps,
                            mem_caps,
                            node_powers=None):

    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / cpu_caps
    mem_util = mem_used / mem_caps

    # 🔥 CLAMP
    cpu_util = np.clip(cpu_util, 0, 1.5)
    mem_util = np.clip(mem_util, 0, 1.5)

    # 🔥 REALISTIC POWER MODEL
    P_idle = 0.5
    P_cpu_dyn = 1.0
    P_mem_dyn = 0.3
    P_sleep = 0.1

    energy_nodes = np.zeros(N_nodes)

    if node_powers is None:
        node_powers = np.ones(N_nodes)

    for i in range(N_nodes):

        if cpu_util[i] > 0.01:
            power = (
                P_idle
                + P_cpu_dyn * cpu_util[i]
                + P_mem_dyn * mem_util[i]
            )
        else:
            power = P_sleep

        # 🔥 EXECUTION-BASED ENERGY
        execution_time = cpu_used[i]

        # 🔥 OVERLOAD PENALTY
        #overload_penalty = 2.0 * max(0, cpu_util[i] - 1.0) ** 2

        if cpu_util[i] <= 0.8:
            overload_penalty = 0
        elif cpu_util[i] <= 1.0:
            overload_penalty = 15 * (cpu_util[i] - 0.8)
        else:
            overload_penalty = 15 * 0.2 + 40 * (cpu_util[i] - 1.0)

        energy_nodes[i] = power * execution_time + overload_penalty

    # 🔥 CONSOLIDATION
    active_nodes = np.sum(cpu_util > 0.05)
    active_penalty = 0.5 * active_nodes

    total_energy = np.sum(energy_nodes) + active_penalty

    return float(total_energy)


# ------------------------------------------------------------
# LATENCY MODEL (SOFT CONGESTION)
# ------------------------------------------------------------
def latency_of_configuration(assignments,
                             cpu_demands,
                             mem_demands,
                             latency_ms,
                             cpu_caps,
                             mem_caps):

    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / cpu_caps
    mem_util = mem_used / mem_caps
    task_count = np.zeros(N_nodes, dtype=int)

    for node in assignments:
        task_count[node] += 1

    latencies = np.zeros(len(assignments))

    BASE_COMPUTE = 0.15
    NETWORK_DELAY = 0.02

    for t, node in enumerate(assignments):

        # 🔥 SERVICE TIME (REALISTIC)
        service_time = cpu_demands[t] * BASE_COMPUTE

        # 🔥 SIMPLE QUEUE
        queue_factor = max(0.0, (task_count[node] / MAX_CONCURRENT_TASKS) - 1.0)
        queue_delay = service_time * queue_factor

        # 🔥 MEMORY PENALTY
        mem_over = max(0.0, mem_util[node] - 1.0)
        mem_penalty = 2.0 * (mem_over ** 2)

        # 🔥 QUEUE PRESSURE
        queue_pressure = max(0, cpu_util[node] - 0.7)
        queue_penalty = 0.5 * queue_pressure

        latencies[t] = (
            service_time
            + queue_delay
            + mem_penalty
            #+ NETWORK_DELAY
            #+ queue_penalty
        )

    mean_latency = np.mean(latencies)

    return float(mean_latency), latencies
