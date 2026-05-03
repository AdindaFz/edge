import numpy as np

from central.offline_runner import (
    run_offline_experiment,
    compute_metrics,
    print_metrics
)
from central.task_generator import generate_batch
from central.system_model import SystemModel

# =========================
# GENERATE TASK
# =========================
tasks = generate_batch(100)

# =========================
# DUMMY DATA UNTUK OPTIMIZER
# =========================
N_tasks = len(tasks)
N_NODES = 2

cpu_demands = np.random.uniform(0.1, 1.0, N_tasks)
mem_demands = np.random.uniform(0.1, 1.0, N_tasks)

cpu_caps = np.array([10, 20])
mem_caps = np.array([10, 20])

latency_ms = np.random.uniform(1, 5, N_tasks)

# =========================
# INIT SYSTEM MODEL
# =========================
system_model_instance = SystemModel()

system_model_instance.cpu_demands = cpu_demands
system_model_instance.mem_demands = mem_demands
system_model_instance.cpu_caps = cpu_caps
system_model_instance.mem_caps = mem_caps
system_model_instance.alpha_cpu = 0.38
system_model_instance.beta_mem = 0.62

# =========================
# TEST RANDOM
# =========================
res_random = run_offline_experiment(tasks, "random")
metrics_random = compute_metrics(res_random)

print("=== RANDOM ===")
print_metrics(metrics_random)

# =========================
# TEST TABU
# =========================
res_tabu = run_offline_experiment(tasks, "tabu")
metrics_tabu = compute_metrics(res_tabu)

print("\n=== TABU ===")
print_metrics(metrics_tabu)
