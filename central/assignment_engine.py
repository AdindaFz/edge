import random
import numpy as np

from central.local_optimizers import DiffusionLocalOptimizer
from central.optimizer_runner import hybrid_tabu_diff


def random_assignment(tasks, nodes):
    node_ids = list(nodes.keys())
    assignments = {}

    for task in tasks:
        node = random.choice(node_ids)
        assignments[task["task_id"]] = node

    return assignments


def optimized_assignment(tasks, nodes):
    assignments = {}
    node_ids = list(nodes.keys())
    node_load = {nid: 0.0 for nid in node_ids}
    node_mem_load = {nid: 0.0 for nid in node_ids}

    for task in tasks:
        best_node = None
        best_score = float("inf")

        cpu_demand = task["cpu_demand"]
        mem_demand = task["memory_demand"]

        for node_id in node_ids:
            node = nodes[node_id]

            cpu_cap = float(node["cpu"])
            mem_cap = float(node["mem"])
            current_cpu = node_load[node_id]
            current_mem = node_mem_load[node_id]

            # Hard infeasible check for a single task
            if mem_demand > mem_cap:
                continue

            cpu_util = current_cpu / max(cpu_cap, 1e-6)
            mem_util = current_mem / max(mem_cap, 1e-6)

            service_time = cpu_demand * 0.18 / max(cpu_cap, 1e-6)
            queue_penalty = max(0.0, cpu_util - 0.8) * 0.5
            mem_penalty = max(0.0, (current_mem + mem_demand) / max(mem_cap, 1e-6) - 1.0) ** 2

            idle_power = float(node.get("idle_power_w", 8.0))
            max_power = float(node.get("max_power_w", 18.0))
            projected_cpu_util = min((current_cpu + cpu_demand) / max(cpu_cap, 1e-6), 1.5)
            projected_mem_util = min((current_mem + mem_demand) / max(mem_cap, 1e-6), 1.5)

            power_w = idle_power + (max_power - idle_power) * min(projected_cpu_util, 1.0)
            power_w += 0.1 * idle_power * min(projected_mem_util, 1.0)

            energy = power_w * service_time
            latency = service_time + float(node["network_delay"]) + queue_penalty + mem_penalty

            score = latency + 0.02 * energy

            if score < best_score:
                best_score = score
                best_node = node_id

        if best_node is None:
            best_node = min(node_ids, key=lambda nid: nodes[nid]["mem"])

        assignments[task["task_id"]] = best_node
        node_load[best_node] += cpu_demand
        node_mem_load[best_node] += mem_demand

    return assignments


def tabu_assignment(tasks, nodes, init_assign=None, local_mode="none", E_ref=None, L_ref=None):
    node_ids = list(nodes.keys())
    n_nodes = len(node_ids)

    cpu_demands = np.array([t["cpu_demand"] for t in tasks], dtype=float)
    mem_demands = np.array([t["memory_demand"] for t in tasks], dtype=float)

    cpu_caps = np.array([float(nodes[n]["cpu"]) for n in node_ids], dtype=float)
    mem_caps = np.array([float(nodes[n]["mem"]) for n in node_ids], dtype=float)
    latency_ms = np.array([float(nodes[n]["network_delay"]) for n in node_ids], dtype=float)

    idle_powers = np.array([float(nodes[n]["idle_power_w"]) for n in node_ids], dtype=float)
    max_powers = np.array([float(nodes[n]["max_power_w"]) for n in node_ids], dtype=float)

    adjacency = {i: [j for j in range(n_nodes) if j != i] for i in range(n_nodes)}
    diffusion = DiffusionLocalOptimizer(
        adjacency=adjacency,
        gamma=0.05,
        max_steps=1,
        node_powers=max_powers,
    )

    best_assign, history = hybrid_tabu_diff(
        cpu_demands,
        cpu_caps,
        mem_demands,
        mem_caps,
        latency_ms,
        idle_powers=idle_powers,
        max_powers=max_powers,
        init_assign=init_assign,
        TABU_MAX_ITER=300,
        TABU_TENURE=30,
        NUM_MOVES=70,
        diffusion=diffusion,
        E_ref=E_ref,
        L_ref=L_ref,
        energy_weight=0.6,
        high_power_penalty_weight=0.35,
    )

    if local_mode == "diffusion":
        best_assign = diffusion.refine(best_assign, cpu_demands, cpu_caps)

    assignments = {}
    for i, task in enumerate(tasks):
        node_id = node_ids[int(best_assign[i])]
        assignments[task["task_id"]] = node_id

    return assignments, history
