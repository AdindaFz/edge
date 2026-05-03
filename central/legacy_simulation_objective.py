import numpy as np


def energy_of_configuration_legacy(
    assignments,
    cpu_demands,
    mem_demands,
    cpu_caps,
    mem_caps,
):
    n_nodes = len(cpu_caps)

    cpu_used = np.zeros(n_nodes)
    mem_used = np.zeros(n_nodes)

    for task_idx, node_idx in enumerate(assignments):
        cpu_used[node_idx] += cpu_demands[task_idx]
        mem_used[node_idx] += mem_demands[task_idx]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    p_idle = 10.0
    p_cpu_dyn = 12.0
    p_mem_dyn = 5.0
    p_sleep = 2.0
    delta_t = 1.0

    energy_nodes = np.zeros(n_nodes)
    for node_idx in range(n_nodes):
        if cpu_util[node_idx] > 0.01:
            power = (
                p_idle
                + p_cpu_dyn * min(cpu_util[node_idx], 1.0)
                + p_mem_dyn * min(mem_util[node_idx], 1.0)
            )
        else:
            power = p_sleep

        if cpu_util[node_idx] <= 0.8:
            overload_penalty = 0.0
        elif cpu_util[node_idx] <= 1.0:
            overload_penalty = 15.0 * (cpu_util[node_idx] - 0.8)
        else:
            overload_penalty = 15.0 * 0.2 + 40.0 * (cpu_util[node_idx] - 1.0)

        energy_nodes[node_idx] = power * delta_t + overload_penalty

    active_nodes = np.sum(cpu_util > 0.05)
    active_penalty = 3.0 * active_nodes

    return float(np.sum(energy_nodes) + active_penalty)


def latency_of_configuration_legacy(
    assignments,
    cpu_demands,
    mem_demands,
    latency_ms,
    cpu_caps,
    mem_caps,
):
    del latency_ms

    n_nodes = len(cpu_caps)

    cpu_used = np.zeros(n_nodes)
    mem_used = np.zeros(n_nodes)

    for task_idx, node_idx in enumerate(assignments):
        cpu_used[node_idx] += cpu_demands[task_idx]
        mem_used[node_idx] += mem_demands[task_idx]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    latencies = np.zeros(len(assignments))
    for task_idx, node_idx in enumerate(assignments):
        service_time = cpu_demands[task_idx] / max(cpu_caps[node_idx], 1e-6)
        rho = min(cpu_util[node_idx], 0.95)
        queue_delay = service_time * rho / (1.0 - rho + 0.05)
        mem_over = max(0.0, mem_util[node_idx] - 1.0)
        mem_penalty = 2.0 * (mem_over ** 2)
        latencies[task_idx] = service_time + queue_delay + mem_penalty

    return float(np.mean(latencies)), latencies


def objective_value_legacy(
    assignments,
    cpu_demands,
    mem_demands,
    latency_ms,
    cpu_caps,
    mem_caps,
    e_ref,
    l_ref,
    weight_energy,
    weight_latency,
):
    energy = energy_of_configuration_legacy(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
    )
    latency, _ = latency_of_configuration_legacy(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms,
        cpu_caps,
        mem_caps,
    )

    cost = (
        weight_energy * (energy / max(e_ref, 1e-6))
        + weight_latency * (latency / max(l_ref, 1e-6))
    )

    return float(cost), float(energy), float(latency)
