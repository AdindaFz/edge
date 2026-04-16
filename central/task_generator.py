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
CPU_RANGE = (1.0, 5.0)
MEM_RANGE = (0.5, 2.0)
LATENCY_RANGE = (50, 300)  # ms

# =========================
# CORE GENERATOR
# =========================

def generate_task(task_id=None):
    cpu = np.random.uniform(*CPU_RANGE)
    mem = np.random.uniform(*MEM_RANGE)
    latency = np.random.uniform(*LATENCY_RANGE)

    compute_cost = cpu * latency

    task = {
      "task_id": task_id or str(uuid.uuid4()),
      "cpu_demand": float(cpu),
      "memory_demand": float(mem),
      "compute_cost": float(compute_cost),
      "arrival_time": 0.0,
      "task_size": classify_task(compute_cost),
      "experiment_id": "exp_1"}
    
    return task


# =========================
# BATCH MODE (FOR EXPERIMENT)
# =========================

def generate_batch(n_tasks=50, seed=42):
    np.random.seed(seed)
    random.seed(seed)
    tasks = []

    for i in range(n_tasks):
        task = generate_task(task_id=f"task_{i}")
        tasks.append(task)

    return tasks

# =========================
# CLASSIFY TASK 
# =========================
def classify_task(compute_cost):
    if compute_cost < 80000:
        return "small"
    elif compute_cost < 200000:
        return "medium"
    else:
        return "large"
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
