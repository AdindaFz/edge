import numpy as np

from central.simulation_model import calibrated_active_time, calibrated_service_time

class DiffusionLocalOptimizer:
    def __init__(
        self,
        adjacency,
        gamma=0.05,
        max_steps=5,
        node_powers=None,
        idle_powers=None,
        max_powers=None,
        latency_ms=None,
        energy_weight=0.68,
    ):
        self.adjacency = adjacency
        self.gamma = gamma
        self.max_steps = max_steps
        self.node_powers = node_powers
        self.idle_powers = idle_powers
        self.max_powers = max_powers
        self.latency_ms = latency_ms
        self.energy_weight = energy_weight

    def _local_cost(self, task_idx, node_idx, cpu_demands, cpu_caps, cpu_util, mem_demands=None, mem_caps=None, mem_util=None):
        cpu_demand = float(cpu_demands[task_idx])
        cpu_cap = float(cpu_caps[node_idx])
        cpu_ratio = min(cpu_demand / max(cpu_cap, 1e-6), 1.0)
        service_time = calibrated_service_time(cpu_demand, cpu_cap)

        current_cpu_util = float(cpu_util[node_idx])
        projected_cpu_util = current_cpu_util + (cpu_demand / max(cpu_cap, 1e-6))
        queue_penalty = service_time * max(0.0, projected_cpu_util - 0.8) * 1.35

        mem_penalty = 0.0
        mem_ratio = 0.0
        if mem_demands is not None and mem_caps is not None and mem_util is not None:
            mem_demand = float(mem_demands[task_idx])
            mem_cap = float(mem_caps[node_idx])
            mem_ratio = min(mem_demand / max(mem_cap, 1e-6), 1.0)
            projected_mem_util = float(mem_util[node_idx]) + (mem_demand / max(mem_cap, 1e-6))
            mem_penalty = max(0.0, projected_mem_util - 1.0) ** 2

        latency = service_time + queue_penalty + mem_penalty
        if self.latency_ms is not None:
            latency += float(self.latency_ms[node_idx])

        if self.idle_powers is not None and self.max_powers is not None:
            effective_util = min(0.8 * cpu_ratio + 0.2 * mem_ratio, 1.0)
            power_w = float(self.idle_powers[node_idx]) + (
                float(self.max_powers[node_idx]) - float(self.idle_powers[node_idx])
            ) * effective_util
            energy = power_w * calibrated_active_time(cpu_demand, cpu_cap)
        elif self.node_powers is not None:
            energy = float(self.node_powers[node_idx]) * projected_cpu_util
        else:
            energy = projected_cpu_util

        return self.energy_weight * energy + (1.0 - self.energy_weight) * latency
    
    def refine(self, assignments, cpu_demands, cpu_caps, mem_demands=None, mem_caps=None):
        best_assign = assignments.copy()
        N_nodes = len(cpu_caps)
        N_tasks = len(cpu_demands)
        
        for _ in range(self.max_steps):
            cpu_used = np.zeros(N_nodes)
            mem_used = np.zeros(N_nodes)
            for t, node in enumerate(best_assign):
                cpu_used[node] += cpu_demands[t]
                if mem_demands is not None:
                    mem_used[node] += mem_demands[t]
            
            cpu_util = cpu_used / cpu_caps
            mem_util = mem_used / np.maximum(mem_caps, 1e-6) if mem_demands is not None and mem_caps is not None else None
            
            for t in range(N_tasks):
                current_node = best_assign[t]
                neighbors = self.adjacency[current_node]

                current_score = self._local_cost(
                    t,
                    current_node,
                    cpu_demands,
                    cpu_caps,
                    cpu_util,
                    mem_demands=mem_demands,
                    mem_caps=mem_caps,
                    mem_util=mem_util,
                )
                best_neighbor = current_node
                best_score = current_score

                for neighbor in neighbors:
                    projected_neighbor = cpu_util[neighbor] + cpu_demands[t] / cpu_caps[neighbor]
                    if projected_neighbor > 1.2:
                        continue

                    if mem_demands is not None and mem_caps is not None and mem_util is not None:
                        projected_mem_neighbor = mem_util[neighbor] + mem_demands[t] / max(mem_caps[neighbor], 1e-6)
                        if projected_mem_neighbor > 1.2:
                            continue

                    neighbor_score = self._local_cost(
                        t,
                        neighbor,
                        cpu_demands,
                        cpu_caps,
                        cpu_util,
                        mem_demands=mem_demands,
                        mem_caps=mem_caps,
                        mem_util=mem_util,
                    )

                    if neighbor_score + self.gamma < best_score:
                        best_score = neighbor_score
                        best_neighbor = neighbor

                if best_neighbor != current_node:
                    best_assign[t] = best_neighbor
                    cpu_used[current_node] -= cpu_demands[t]
                    cpu_used[best_neighbor] += cpu_demands[t]
                    cpu_util = cpu_used / cpu_caps
                    if mem_demands is not None:
                        mem_used[current_node] -= mem_demands[t]
                        mem_used[best_neighbor] += mem_demands[t]
                        mem_util = mem_used / np.maximum(mem_caps, 1e-6)
        
        return best_assign
