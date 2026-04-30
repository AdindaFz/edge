import random
import uuid
import numpy as np
import time
import json
from datetime import datetime
from pathlib import Path

TASK_SEED = 42
np.random.seed(TASK_SEED)
random.seed(TASK_SEED)

CPU_TIME_MS_RANGE = (200.0, 900.0)
MEMORY_MB_RANGE = (128, 768)

CPU_TIME_UNIT_MS = 250.0
MEMORY_UNIT_BYTES = 1024 ** 3  # 1 GB

# Calibration data cache
_CALIBRATION_CACHE = None
USE_DATA_DRIVEN_GENERATION = True  # Flag to enable data-driven generation


def load_calibration_data():
    """Load actual task data from calibration runs for data-driven generation."""
    global _CALIBRATION_CACHE

    if _CALIBRATION_CACHE is not None:
        return _CALIBRATION_CACHE

    try:
        calibration_dir = Path(__file__).parent.parent / "outputs" / "calibration"

        if not calibration_dir.exists():
            print("[WARN] Calibration data directory not found, using theoretical generation")
            return None

        tasks = []
        for path in sorted(calibration_dir.glob("workload_calibration_*.jsonl")):
            try:
                with path.open() as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                            # Only include tasks with required fields
                            if "cpu_demand" in row and "memory_demand" in row:
                                tasks.append(row)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"[WARN] Error reading calibration file {path}: {e}")
                continue

        if tasks:
            _CALIBRATION_CACHE = tasks
            print(f"[INFO] Loaded {len(tasks)} calibration tasks from {calibration_dir}")
            return tasks
        else:
            print("[WARN] No calibration data found, using theoretical generation")
            return None

    except Exception as e:
        print(f"[WARN] Error loading calibration data: {e}")
        return None


def classify_task(cpu_time_target_ms, memory_bytes):
    """
    Classify task size based on CPU time and memory requirements.

    Updated boundaries based on calibration data analysis:
    - Small:  < 325ms CPU & < 0.25GB memory  (target ~20%)
    - Medium: < 675ms CPU & < 0.75GB memory  (target ~60%)
    - Large:  >= 675ms CPU | >= 0.75GB memory (target ~20%)
    """
    mem_gb = memory_bytes / (1024 ** 3)

    # Updated thresholds for better balance (from calibration analysis)
    if cpu_time_target_ms < 325 and mem_gb < 0.25:
        return "small"
    elif cpu_time_target_ms < 675 and mem_gb < 0.75:
        return "medium"
    return "large"


def generate_task(task_id=None, seed=None, use_calibration=None):
    """
    Generate a task with CPU and memory demands.

    Two modes:
    1. Data-driven (default): Sample from actual calibration distribution
    2. Theoretical: Use uniform random generation from CPU_TIME_MS_RANGE

    Args:
        task_id: Optional task identifier
        seed: Random seed for reproducibility
        use_calibration: Override to force use/non-use of calibration data
    """
    if seed is None:
        seed = random.randint(0, 1_000_000)

    # Determine if should use calibration data
    use_calib = use_calibration if use_calibration is not None else USE_DATA_DRIVEN_GENERATION
    calibration_tasks = load_calibration_data() if use_calib else None

    if calibration_tasks:
        # Data-driven generation: Sample from actual calibration distribution
        template = calibration_tasks[seed % len(calibration_tasks)]

        # Extract from template with slight variation
        cpu_demand = float(template.get("cpu_demand", 1.0))
        memory_demand = float(template.get("memory_demand", 0.5))

        # Add small random variation (~5%) to generate diversity
        cpu_demand *= np.random.normal(1.0, 0.05)
        memory_demand *= np.random.normal(1.0, 0.05)

        # Clamp to valid ranges
        cpu_demand = np.clip(cpu_demand, 0.8, 3.6)
        memory_demand = np.clip(memory_demand, 0.125, 0.75)

        # Convert back to time and bytes
        cpu_time_target_ms = cpu_demand * CPU_TIME_UNIT_MS
        memory_bytes = int(memory_demand * MEMORY_UNIT_BYTES)

    else:
        # Theoretical generation: Uniform random from defined ranges
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
            "touch_rounds": 4,
        },
        "arrival_time": 0.0,
        "task_size": classify_task(cpu_time_target_ms, memory_bytes),
        "experiment_id": "exp_1",
    }


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
