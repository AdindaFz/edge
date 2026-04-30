import random
import uuid
import numpy as np
import time
from datetime import datetime

TASK_SEED = 42
np.random.seed(TASK_SEED)
random.seed(TASK_SEED)

CPU_TIME_MS_RANGE = (200.0, 900.0)
MEMORY_MB_RANGE = (128, 768)

CPU_TIME_UNIT_MS = 250.0
MEMORY_UNIT_BYTES = 1024 ** 3  # 1 GB


def classify_task(cpu_time_target_ms, memory_bytes):
    mem_gb = memory_bytes / (1024 ** 3)

    if cpu_time_target_ms < 350 and mem_gb < 0.25:
        return "small"
    elif cpu_time_target_ms < 650 and mem_gb < 0.75:
        return "medium"
    return "large"


def generate_task(task_id=None, seed=None):
    if seed is None:
        seed = random.randint(0, 1_000_000)

    cpu_time_target_ms = float(np.random.uniform(*CPU_TIME_MS_RANGE))
    memory_mb = int(np.random.uniform(*MEMORY_MB_RANGE))
    memory_bytes = memory_mb * 1024 * 1024

    # Normalized demand for optimizer
    cpu_demand = cpu_time_target_ms / CPU_TIME_UNIT_MS
    memory_demand = memory_bytes / MEMORY_UNIT_BYTES

    compute_cost = cpu_demand * 100.0

    return {
        "task_id": task_id or str(uuid.uuid4()),
        "cpu_demand": float(cpu_demand),
        "memory_demand": float(memory_demand),
        "compute_cost": float(compute_cost),
        "task_type": "cpu_mem_burn",
        "cpu_time_target_ms": float(cpu_time_target_ms),
        "memory_bytes": int(memory_bytes),
        "payload": {
            "seed": int(seed),
            "touch_rounds": 1,
        },
        "arrival_time": 0.0,
        "task_size": classify_task(cpu_time_target_ms, memory_bytes),
        "experiment_id": "exp_1",
    }


def build_cpu_mem_burn_task(
    task_id,
    cpu_time_target_ms,
    memory_mb,
    seed,
    touch_rounds=1,
    experiment_id="exp_calibration",
):
    memory_bytes = int(memory_mb) * 1024 * 1024

    cpu_demand = float(cpu_time_target_ms) / CPU_TIME_UNIT_MS
    memory_demand = memory_bytes / MEMORY_UNIT_BYTES
    compute_cost = cpu_demand * 100.0

    return {
        "task_id": str(task_id),
        "cpu_demand": float(cpu_demand),
        "memory_demand": float(memory_demand),
        "compute_cost": float(compute_cost),
        "task_type": "cpu_mem_burn",
        "cpu_time_target_ms": float(cpu_time_target_ms),
        "memory_bytes": int(memory_bytes),
        "payload": {
            "seed": int(seed),
            "touch_rounds": int(touch_rounds),
        },
        "arrival_time": 0.0,
        "task_size": classify_task(cpu_time_target_ms, memory_bytes),
        "experiment_id": experiment_id,
    }


def generate_calibration_tasks(seed=42):
    presets = [
        ("light", 150.0, 64),
        ("medium", 400.0, 128),
        ("heavy", 800.0, 256),
    ]

    tasks = []
    for idx, (label, cpu_time_target_ms, memory_mb) in enumerate(presets):
        tasks.append(
            build_cpu_mem_burn_task(
                task_id=f"cal_{label}",
                cpu_time_target_ms=cpu_time_target_ms,
                memory_mb=memory_mb,
                seed=seed * 10000 + idx,
                experiment_id="exp_calibration",
            )
        )

    return tasks


def generate_batch(n_tasks=50, seed=42):
    np.random.seed(seed)
    random.seed(seed)

    tasks = []
    for i in range(n_tasks):
        task_seed = seed * 10000 + i
        tasks.append(generate_task(task_id=f"task_{i}", seed=task_seed))

    return tasks


def generate_poisson_tasks(n_tasks=50, lambda_rate=2, seed=42):
    np.random.seed(seed)
    random.seed(seed)

    tasks = []
    sim_time = 0.0

    for i in range(n_tasks):
        inter_arrival = np.random.exponential(1.0 / lambda_rate)
        sim_time += inter_arrival

        task_seed = seed * 10000 + i
        task = generate_task(task_id=f"task_{i}", seed=task_seed)
        task["arrival_time"] = float(sim_time)
        tasks.append(task)

    return tasks


def task_stream(tasks):
    start_time = datetime.now().timestamp()

    for task in tasks:
        now = datetime.now().timestamp()
        elapsed = now - start_time

        wait_time = task["arrival_time"] - elapsed
        if wait_time > 0:
            time.sleep(wait_time)

        yield task
