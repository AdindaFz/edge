import random

def select_node(task, nodes_status, mode="random"):
    """
    Scheduler with multiple modes:
    - random (baseline)
    - heuristic (cpu + queue aware)
    """

    if not nodes_status:
        return None

    # =========================
    # RANDOM BASELINE
    # =========================
    if mode == "random":
        return random.choice(list(nodes_status.keys()))

    # =========================
    # HEURISTIC (CPU + QUEUE)
    # =========================
    elif mode == "heuristic":

        best_node = None
        best_score = float("inf")

        for node_id, n in nodes_status.items():

            cpu = n.cpu_usage / 100.0
            queue = n.tasks_count
            score = cpu + (queue * 0.3)
            # latency proxy
            latency_est = queue * 0.1

            # energy proxy
            energy_est = cpu

            # weighted cost
            cost = 0.6 * energy_est + 0.4 * latency_est
            cost += queue * 0.3
            if queue > 3:
                cost *= 2

            if cost < best_score:
                best_score = cost
                best_node = node_id

        return best_node

    # =========================
    # UNKNOWN MODE
    # =========================
    else:
        raise ValueError(f"Unknown scheduler mode: {mode}")
