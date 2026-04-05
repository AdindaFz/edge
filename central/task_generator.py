import numpy as np
import random
import uuid
from datetime import datetime

# =========================
# CONFIG
# =========================
TASK_SEED = 42
np.random.seed(TASK_SEED)
random.seed(TASK_SEED)

# scaling control (biar nggak absurd)
CPU_RANGE = (0.05, 0.5)
MEM_RANGE = (0.1, 1.0)
LATENCY_RANGE = (1e4, 1e6)  # ms

# =========================
# CORE GENERATOR
# =========================

def generate_task(task_id=None):
    cpu = np.random.uniform(*CPU_RANGE)
    mem = np.random.uniform(*MEM_RANGE)
    latency = np.random.uniform(*LATENCY_RANGE)

    compute_cost = cpu * latency

    return {
        "task_id": task_id or str(uuid.uuid4()),
        "cpu_demand": float(cpu),
        "memory_demand": float(mem),
        "compute_cost": float(compute_cost),
        "arrival_time": 0.0,
        "created_at": datetime.now().isoformat()
    }


# =========================
# BATCH MODE (FOR EXPERIMENT)
# =========================

def generate_batch(n_tasks=50):
    tasks = []

    for i in range(n_tasks):
        task = generate_task(task_id=f"task_{i}")
        tasks.append(task)

    return tasks


# =========================
# POISSON ARRIVAL MODE
# =========================

def generate_poisson_tasks(n_tasks=50, lambda_rate=2):
    tasks = []
    sim_time = 0.0

    for i in range(n_tasks):
        inter_arrival = np.random.exponential(1.0 / lambda_rate)
        sim_time += inter_arrival

        task = generate_task(task_id=f"task_{i}")
        task["arrival_time"] = float(sim_time)

        tasks.append(task)

    return tasks


# =========================
# STREAMING GENERATOR
# =========================

def task_stream(tasks):
    """
    Yield task berdasarkan arrival_time (real-time simulation)
    """
    start_time = datetime.now().timestamp()

    for task in tasks:
        now = datetime.now().timestamp()
        elapsed = now - start_time

        wait_time = task["arrival_time"] - elapsed
        if wait_time > 0:
            time.sleep(wait_time)

        yield task
