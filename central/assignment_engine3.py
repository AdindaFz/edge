import random
from central.node_resources import NODE_RESOURCES
from central.optimizer_runner import hybrid_tabu_diff
from central.local_optimizers import DiffusionLocalOptimizer
import numpy as np

def random_assignment(tasks, nodes):
    node_ids = list(nodes.keys())

    assignments = {}
    for task in tasks:
        assignments[task["task_id"]] = random.choice(node_ids)

    return assignments

def optimized_assignment(tasks, nodes):
    """
    Placeholder untuk optimizer (Tabu / PSO nanti)
    """
    assignments = {}

    for task in tasks:
        best_node = None
        best_score = float("inf")

        for node_id in nodes.keys():
            node = NODE_RESOURCES[node_id]

            compute_cost = task.get("compute_cost", 1000)

            exec_time = compute_cost / node["cpu"]
            latency = exec_time + node.get("network_delay", 1)

            if latency < best_score:
                best_score = latency
                best_node = node_id

        assignments[task["task_id"]] = best_node

    return assignments

def evaluate_assignment(assignments, tasks, nodes):
    results = []

    for task in tasks:
        task_id = task["task_id"]
        node_id = assignments[task_id]

        node = nodes[node_id]

        execution_time = task["cpu"] / node["cpu"]
        latency = execution_time + node.get("network_delay", 1)

        results.append({
            "latency": latency,
            "execution_time": execution_time,
            "node": node_id
        })

    return results

def tabu_assignment(tasks, nodes, local_mode="none"):

    import numpy as np

    node_ids = list(nodes.keys())
    N_tasks = len(tasks)

    # =========================
    # TASK → ARRAY
    # =========================
    cpu_demands = np.array([t["cpu_demand"] for t in tasks])

    # =========================
    # NODE → ARRAY
    # =========================
    cpu_caps = np.array([NODE_RESOURCES[n]["cpu"] for n in node_ids])

    # =========================
    # TABU (GLOBAL)
    # =========================
    diffusion = DiffusionLocalOptimizer(
        adjacency={0: [1], 1: [0]},
        gamma=0.1,
        max_steps=3
    )

    best_assign = hybrid_tabu_diff(
        cpu_demands,
        cpu_caps,
        network_delays=[1, 2],
        powers=[1.2, 2.5],
        diffusion=diffusion
    )

    # =========================
    # DIFFUSION (LOCAL)
    # =========================
    if local_mode == "diffusion":

        diffusion = DiffusionLocalOptimizer(
            adjacency={0: [1], 1: [0]},
            gamma=0.1,
            max_steps=3
        )

        best_assign = diffusion.refine(
            best_assign,
            cpu_demands,
            cpu_caps
        )

    # =========================
    # ARRAY → DICT
    # =========================
    assignments = {}

    for i, task in enumerate(tasks):
        node_id = node_ids[int(best_assign[i])]
        assignments[task["task_id"]] = node_id

    return assignments


def build_local_optimizer(name):

    if name == "diffusion":
        return DiffusionLocalOptimizer(adjacency={0:[1],1:[0]})

    elif name == "none":
        return None
