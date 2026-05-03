import numpy as np
from config import MAX_CONCURRENT_TASKS


# Calibrated from observed runs:
# - mid tier (`cpu=4`) averages ~0.50s wall time and ~1.36x target task-clock
# - high tier (`cpu=8`) averages ~0.21s wall time and ~1.9x target task-clock
SERVICE_TIME_PER_CPU_DEMAND = {
    2: 0.32,
    4: 0.2125,
    8: 0.1557,
}

ACTIVE_TIME_PER_CPU_DEMAND = {
    2: 0.30,
    4: 0.3230,
    8: 0.5418,
}

QUEUE_DELAY_MULTIPLIER = {
    2: 0.10,
    4: 0.0783,
    8: 0.0071,
}

CPU_DYNAMIC_ENERGY_MULTIPLIER = {
    2: 1.00,
    4: 1.0637,
    8: 1.0122,
}

MEMORY_DYNAMIC_ENERGY_MULTIPLIER = {
    2: 0.15,
    4: 0.1484,
    8: 0.1487,
}


def calibrated_service_time(cpu_demand, cpu_cap):
    cpu_key = int(round(float(cpu_cap)))
    coeff = SERVICE_TIME_PER_CPU_DEMAND.get(cpu_key, 0.88 / max(np.sqrt(cpu_cap), 1e-6))
    return float(cpu_demand) * float(coeff)


def calibrated_active_time(cpu_demand, cpu_cap):
    cpu_key = int(round(float(cpu_cap)))
    coeff = ACTIVE_TIME_PER_CPU_DEMAND.get(cpu_key, 0.25)
    return float(cpu_demand) * float(coeff)


def calibrated_cpu_active_time(cpu_demand, cpu_cap):
    # Keep CPU-dynamic energy aligned with the real estimator, which uses
    # actual CPU-active time separately from wall/task active time.
    return calibrated_active_time(cpu_demand, cpu_cap)


def calibrated_queue_delay(cpu_demand, cpu_cap, queue_factor):
    cpu_key = int(round(float(cpu_cap)))
    coeff = QUEUE_DELAY_MULTIPLIER.get(cpu_key, 0.05)
    return float(cpu_demand) * float(coeff) * float(queue_factor)


def calibrated_cpu_dynamic_energy(cpu_ratio, active_time_s, cpu_cap, dynamic_power_span):
    cpu_key = int(round(float(cpu_cap)))
    coeff = CPU_DYNAMIC_ENERGY_MULTIPLIER.get(cpu_key, 1.0)
    return float(dynamic_power_span) * float(cpu_ratio) * float(active_time_s) * float(coeff)


def calibrated_memory_dynamic_energy(mem_ratio, active_time_s, cpu_cap, dynamic_power_span):
    cpu_key = int(round(float(cpu_cap)))
    coeff = MEMORY_DYNAMIC_ENERGY_MULTIPLIER.get(cpu_key, 0.15)
    return float(dynamic_power_span) * float(mem_ratio) * float(active_time_s) * float(coeff)


def estimate_task_energy(cpu_demand, mem_demand, cpu_cap, mem_cap, idle_power, max_power):
    cpu_ratio = min(float(cpu_demand) / max(float(cpu_cap), 1e-6), 1.0)
    mem_ratio = min(float(mem_demand) / max(float(mem_cap), 1e-6), 1.0)
    dynamic_power_span = max(0.0, float(max_power) - float(idle_power))

    active_time_s = calibrated_active_time(cpu_demand, cpu_cap)
    cpu_active_time_s = calibrated_cpu_active_time(cpu_demand, cpu_cap)

    idle_energy = float(idle_power) * active_time_s
    cpu_dynamic_energy = calibrated_cpu_dynamic_energy(
        cpu_ratio,
        cpu_active_time_s,
        cpu_cap,
        dynamic_power_span,
    )
    memory_dynamic_energy = calibrated_memory_dynamic_energy(
        mem_ratio,
        active_time_s,
        cpu_cap,
        dynamic_power_span,
    )

    return idle_energy + cpu_dynamic_energy + memory_dynamic_energy


def estimate_task_energy_with_queue(
    cpu_demand,
    mem_demand,
    cpu_cap,
    mem_cap,
    idle_power,
    max_power,
    queue_factor,
    mem_util,
):
    cpu_ratio = min(float(cpu_demand) / max(float(cpu_cap), 1e-6), 1.0)
    mem_ratio = min(float(mem_demand) / max(float(mem_cap), 1e-6), 1.0)
    dynamic_power_span = max(0.0, float(max_power) - float(idle_power))

    service_time_s = calibrated_service_time(cpu_demand, cpu_cap)
    queue_delay_s = calibrated_queue_delay(cpu_demand, cpu_cap, queue_factor)
    mem_over = max(0.0, float(mem_util) - 1.0)
    mem_delay_s = 0.75 * (mem_over ** 2)

    # Match the real estimator more closely:
    # - idle and memory terms scale with task-clock-like active lifetime
    # - CPU dynamic term scales with CPU-active time only
    active_time_s = service_time_s + queue_delay_s + mem_delay_s
    cpu_active_time_s = calibrated_cpu_active_time(cpu_demand, cpu_cap)

    idle_energy = float(idle_power) * active_time_s
    cpu_dynamic_energy = calibrated_cpu_dynamic_energy(
        cpu_ratio,
        cpu_active_time_s,
        cpu_cap,
        dynamic_power_span,
    )
    memory_dynamic_energy = calibrated_memory_dynamic_energy(
        mem_ratio,
        active_time_s,
        cpu_cap,
        dynamic_power_span,
    )

    return idle_energy + cpu_dynamic_energy + memory_dynamic_energy


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

    if idle_powers is None:
        idle_powers = np.full(N_nodes, 8.0)

    if max_powers is None:
        max_powers = np.full(N_nodes, 20.0)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)
    task_count = np.zeros(N_nodes, dtype=int)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]
        task_count[node] += 1

    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    total_energy = 0.0
    for t, node in enumerate(assignments):
        queue_factor = max(0.0, (task_count[node] / MAX_CONCURRENT_TASKS) - 1.0)
        total_energy += estimate_task_energy_with_queue(
            cpu_demands[t],
            mem_demands[t],
            cpu_caps[node],
            mem_caps[node],
            idle_powers[node],
            max_powers[node],
            queue_factor,
            mem_util[node],
        )

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

    for t, node in enumerate(assignments):
        service_time = calibrated_service_time(cpu_demands[t], cpu_caps[node])

        queue_factor = max(0.0, (task_count[node] / MAX_CONCURRENT_TASKS) - 1.0)
        queue_delay = calibrated_queue_delay(cpu_demands[t], cpu_caps[node], queue_factor)

        mem_over = max(0.0, mem_util[node] - 1.0)
        mem_penalty = 0.75 * (mem_over ** 2)

        network_delay = float(latency_ms[node]) if latency_ms is not None else 0.0

        latencies[t] = service_time + queue_delay + mem_penalty + network_delay

    mean_latency = np.mean(latencies)
    return float(mean_latency), latencies
