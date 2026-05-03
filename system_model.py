
import numpy as np


# ============================================================
# SYSTEM MODEL
# ============================================================


# ------------------------------------------------------------
# COMPUTE LOAD
# ------------------------------------------------------------

class SystemModel:

    def compute_computing_load(self, assignments):
        return compute_computing_load(
            assignments,
            self.cpu_demands,
            self.mem_demands,
            self.cpu_caps,
            self.mem_caps,
            self.alpha_cpu,
            self.beta_mem
        )


def compute_computing_load(assignments,
                           cpu_demands,
                           mem_demands,
                           cpu_caps,
                           mem_caps,
                           alpha_cpu,
                           beta_mem):

    N_nodes = len(cpu_caps)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    load = alpha_cpu * cpu_util + beta_mem * mem_util

    return load, cpu_util, mem_util


# ------------------------------------------------------------
# ENERGY MODEL 
# ------------------------------------------------------------
def energy_of_configuration(assignments,
                            cpu_demands,
                            mem_demands,
                            cpu_caps,
                            mem_caps,
                            idle_powers=None,
                            max_powers=None):

    N_nodes = len(cpu_caps)

    if idle_powers is None:
        idle_powers = np.full(N_nodes, 8.0)
    if max_powers is None:
        max_powers = np.full(N_nodes, 20.0)

    cpu_used = np.zeros(N_nodes)
    mem_used = np.zeros(N_nodes)
    task_count = np.zeros(N_nodes, dtype=float)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]
        task_count[node] += 1.0

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    total_energy = 0.0
    for i in range(N_nodes):
        active = task_count[i] > 0
        if active:
            effective_util = min(0.8 * min(cpu_util[i], 1.0) + 0.2 * min(mem_util[i], 1.0), 1.0)
            power_w = idle_powers[i] + (max_powers[i] - idle_powers[i]) * effective_util
        else:
            # Sleep-like idle for unused nodes; high tier remains costlier than low tier.
            power_w = 0.25 * idle_powers[i]

        overload_penalty = 0.0
        if cpu_util[i] > 0.85:
            overload_penalty += (max_powers[i] - idle_powers[i]) * (cpu_util[i] - 0.85) ** 2
        if mem_util[i] > 0.90:
            overload_penalty += 0.5 * idle_powers[i] * (mem_util[i] - 0.90) ** 2

        total_energy += power_w + overload_penalty

    return float(total_energy)


# ------------------------------------------------------------
# LATENCY MODEL 
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
    task_count = np.zeros(N_nodes, dtype=float)

    for t, node in enumerate(assignments):
        cpu_used[node] += cpu_demands[t]
        mem_used[node] += mem_demands[t]
        task_count[node] += 1.0

    cpu_util = cpu_used / np.maximum(cpu_caps, 1e-6)
    mem_util = mem_used / np.maximum(mem_caps, 1e-6)

    latencies = np.zeros(len(assignments))

    for t, node in enumerate(assignments):
        service_time = cpu_demands[t] / max(cpu_caps[node], 1e-6)
        rho = min(cpu_util[node], 0.95)
        queue_delay = service_time * rho / (1 - rho + 0.05)
        mem_over = max(0.0, mem_util[node] - 1.0)
        mem_penalty = 0.75 * (mem_over ** 2)
        network_delay = float(latency_ms[node]) if latency_ms is not None else 0.0

        latencies[t] = service_time + queue_delay + mem_penalty + network_delay

    mean_latency = np.mean(latencies)

    return float(mean_latency), latencies


# ------------------------------------------------------------
# OBJECTIVE FUNCTION
# ------------------------------------------------------------
def objective_value(assignments,
                    cpu_demands,
                    mem_demands,
                    latency_ms,
                    cpu_caps,
                    mem_caps,
                    E_ref,
                    L_ref,
                    weight_energy,
                    weight_latency,
                    idle_powers=None,
                    max_powers=None):

    E = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        idle_powers=idle_powers,
        max_powers=max_powers
    )

    L, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms,
        cpu_caps,
        mem_caps
    )

    cost = (
        weight_energy * (E / E_ref) +
        weight_latency * (L / L_ref)
    )

    return cost, E, L


# ------------------------------------------------------------
# GREEDY REFINEMENT (SEARCH IMPROVEMENT OPERATOR)
# ------------------------------------------------------------
def greedy_refinement(assignments,
                      cpu_demands,
                      mem_demands,
                      latency_ms,
                      cpu_caps,
                      mem_caps,
                      E_ref,
                      L_ref,
                      weight_energy,
                      weight_latency,
                      rng,
                      steps=20,
                      idle_powers=None,
                      max_powers=None):

    best_assign = assignments.copy()

    best_cost, _, _ = objective_value(
        best_assign,
        cpu_demands,
        mem_demands,
        latency_ms,
        cpu_caps,
        mem_caps,
        E_ref,
        L_ref,
        weight_energy,
        weight_latency,
        idle_powers=idle_powers,
        max_powers=max_powers
    )

    N_nodes = len(cpu_caps)

    for _ in range(steps):
        t = rng.integers(0, len(best_assign))
        current_node = best_assign[t]

        for node in range(N_nodes):
            if node == current_node:
                continue

            trial = best_assign.copy()
            trial[t] = node

            trial_cost, _, _ = objective_value(
                trial,
                cpu_demands,
                mem_demands,
                latency_ms,
                cpu_caps,
                mem_caps,
                E_ref,
                L_ref,
                weight_energy,
                weight_latency,
                idle_powers=idle_powers,
                max_powers=max_powers
            )

            if trial_cost < best_cost:
                best_cost = trial_cost
                best_assign = trial
                break

    return best_assign, best_cost

