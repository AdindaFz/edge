import numpy as np
from config import MAX_CONCURRENT_TASKS


def energy_of_configuration(
    assignments,
    cpu_demands,
    mem_demands,
    cpu_caps,
    mem_caps,
    idle_powers=None,
    max_powers=None,
):
    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    cpu_util = np.clip(cpu_util, 0, 1.5)
    mem_util = np.clip(mem_util, 0, 1.5)

    if idle_powers is None:
        idle_powers = np.full(N_nodes, 8.0)

    if max_powers is None:
        max_powers = np.full(N_nodes, 20.0)

    energy_nodes = np.zeros(N_nodes)
    BASE_COMPUTE = 0.18

    for i in range(N_nodes):
        # Align power shape with runtime estimator in offline_runner.
        effective_util = min(0.8 * min(cpu_util[i], 1.0) + 0.2 * min(mem_util[i], 1.0), 1.0)
        power_w = idle_powers[i] + (max_powers[i] - idle_powers[i]) * effective_util

        # Service time scales down on stronger nodes (more CPU capacity).
        execution_time_s = cpu_used[i] * BASE_COMPUTE / max(cpu_caps[i], 1e-6)

        if cpu_util[i] <= 0.8:
            overload_penalty = 0.0
        elif cpu_util[i] <= 1.0:
            overload_penalty = 3.0 * (cpu_util[i] - 0.8)
        else:
            overload_penalty = 0.6 + 6.0 * (cpu_util[i] - 1.0)

        energy_nodes[i] = power_w * execution_time_s + overload_penalty

    active_nodes = np.sum(cpu_util > 0.05)
    active_penalty = 1.0 * active_nodes

    total_energy = np.sum(energy_nodes) + active_penalty
    return float(total_energy)


def latency_of_configuration(
    assignments,
    cpu_demands,
    mem_demands,
    latency_ms,
    cpu_caps,
    mem_caps,
):
    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)
    task_count = np.zeros(N_nodes, dtype=int)

    for node in assignments:
        task_count[node] += 1

    latencies = np.zeros(len(assignments))

    BASE_COMPUTE = 0.18

    for t, node in enumerate(assignments):
        # Larger nodes should process same cpu_demand faster
        service_time = cpu_demands[t] * BASE_COMPUTE / max(cpu_caps[node], 1e-6)

        queue_factor = max(0.0, (task_count[node] / MAX_CONCURRENT_TASKS) - 1.0)
        queue_delay = service_time * queue_factor

        mem_over = max(0.0, mem_util[node] - 1.0)
        mem_penalty = 1.5 * (mem_over ** 2)

        network_delay = float(latency_ms[node]) if latency_ms is not None else 0.0

        latencies[t] = service_time + queue_delay + mem_penalty + network_delay

    mean_latency = np.mean(latencies)
    return float(mean_latency), latencies
