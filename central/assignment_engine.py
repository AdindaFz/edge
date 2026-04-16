import random
import numpy as np
from central.optimizer_runner import hybrid_tabu_diff
from central.local_optimizers import DiffusionLocalOptimizer


# =========================
# RANDOM
# =========================
def random_assignment(tasks, nodes):
    node_ids = list(nodes.keys())

    assignments = {}

    for task in tasks:
        node = random.choice(node_ids)  # 🔥 uniform random
        assignments[task["task_id"]] = node

    return assignments

# =========================
# GREEDY BASELINE
# =========================
def optimized_assignment(tasks, nodes):

    assignments = {}
    node_ids = list(nodes.keys())

    node_load = {nid: 0 for nid in node_ids}

    for task in tasks:
        best_node = None
        best_score = float("inf")

        cpu_demand = task["cpu_demand"]

        for node_id in node_ids:
            node = nodes[node_id]  # ✅ FIX (pakai nodes, bukan NODE_RESOURCES)

            cpu_cap = node["cpu"]
            current_load = node_load[node_id]

            cpu_util = current_load / cpu_cap

            exec_time = cpu_demand * (1 + cpu_util**2) / cpu_cap

            latency = exec_time + node["network_delay"]
            energy = exec_time * node["power"]

            score = latency + energy

            if score < best_score:
                best_score = score
                best_node = node_id

        assignments[task["task_id"]] = best_node
        node_load[best_node] += cpu_demand

    return assignments


# =========================
# TABU + DIFFUSION
# =========================
def tabu_assignment(tasks, nodes, init_assign=None, local_mode="none", E_ref=None, L_ref=None):

    node_ids = list(nodes.keys())
    N = len(node_ids)

    cpu_demands = np.array([t["cpu_demand"] for t in tasks])
    mem_demands = np.array([t["memory_demand"] for t in tasks])
    cpu_caps = np.array([nodes[n]["cpu"] for n in node_ids])
    mem_caps = np.array([nodes[n]["mem"] for n in node_ids])
    latency_ms = np.array([nodes[n]["network_delay"] for n in node_ids])
    
    # ✅ PASTIKAN INI ARRAY
    node_powers = np.array([nodes[n]["power"] for n in node_ids])
    print(f"DEBUG: node_powers type = {type(node_powers)}, shape = {node_powers.shape}")
    print(f"DEBUG: node_powers = {node_powers}")

    adjacency = {i: [j for j in range(N) if j != i] for i in range(N)}
    diffusion = DiffusionLocalOptimizer(adjacency=adjacency, gamma=0.05, max_steps=1, node_powers=node_powers)

    from central.optimizer_runner import hybrid_tabu_diff
    
    best_assign, history = hybrid_tabu_diff(
        cpu_demands,
        cpu_caps,
        mem_demands,
        mem_caps,
        latency_ms,
        node_powers,  # ✅ Pass array
        init_assign=init_assign,
        TABU_MAX_ITER=300,
        TABU_TENURE=30,
        NUM_MOVES=70,
        diffusion=diffusion,
        E_ref=E_ref,
        L_ref=L_ref,
        energy_weight=0.95
    )

    if local_mode == "diffusion":
        best_assign = diffusion.refine(best_assign, cpu_demands, cpu_caps)

    assignments = {}
    for i, task in enumerate(tasks):
        node_id = node_ids[int(best_assign[i])]
        assignments[task["task_id"]] = node_id

    return assignments, history
