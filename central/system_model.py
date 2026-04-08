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

    cpu_util = cpu_used / cpu_caps
    mem_util = mem_used / mem_caps

    load = alpha_cpu * cpu_util + beta_mem * mem_util

    return load, cpu_util, mem_util


# ------------------------------------------------------------
# ENERGY MODEL (SOFT PENALTY)
# ------------------------------------------------------------
def energy_of_configuration(assignments,
                            cpu_demands,
                            mem_demands,
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

    # Power parameters
    P_idle = 10
    P_cpu_dyn = 12
    P_mem_dyn = 5
    P_sleep = 2
    delta_t = 1

    energy_nodes = np.zeros(N_nodes)

    for i in range(N_nodes):

        if cpu_util[i] > 0.01:
            power = (
                P_idle
                + P_cpu_dyn * min(cpu_util[i], 1.0)
                + P_mem_dyn * min(mem_util[i], 1.0)
            )
        else:
            power = P_sleep

        # Soft CPU stress penalty
        if cpu_util[i] <= 0.8:
            overload_penalty = 0
        elif cpu_util[i] <= 1.0:
            overload_penalty = 15 * (cpu_util[i] - 0.8)
        else:
            overload_penalty = 15 * 0.2 + 40 * (cpu_util[i] - 1.0)

        energy_nodes[i] = power * delta_t + overload_penalty

    # Soft consolidation penalty
    active_nodes = np.sum(cpu_util > 0.05)
    active_penalty = 3 * active_nodes

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

    latencies = np.zeros(len(assignments))

    for t, node in enumerate(assignments):

        service_time = cpu_demands[t] / cpu_caps[node]

        rho = min(cpu_util[node], 0.95)
        queue_delay = service_time * rho / (1 - rho + 0.05)

        mem_over = max(0.0, mem_util[node] - 1.0)
        mem_penalty = 2.0 * (mem_over ** 2)

        latencies[t] = service_time + queue_delay + mem_penalty

    mean_latency = np.mean(latencies)

    return float(mean_latency), latencies


# ------------------------------------------------------------
# OBJECTIVE FUNCTION (IDENTICAL STRUCTURE)
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
                    weight_latency):

    E = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps
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
                      steps=20):

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
        weight_latency
    )

    N_nodes = len(cpu_caps)

    for _ in range(steps):

        # random pilih 1 task
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
                weight_latency
            )

            # first improvement
            if trial_cost < best_cost:
                best_cost = trial_cost
                best_assign = trial
                break

    return best_assign, best_cost
