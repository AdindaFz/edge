import os
import json
from datetime import datetime
import matplotlib.pyplot as plt

from central.offline_runner import (
    run_offline_experiment,
    compute_metrics,
    print_metrics,
    print_all_comparison_table,
)
from central.task_generator import generate_batch
from central.node_resources import NODE_RESOURCES


N_TASKS = 25
PLOT_DIR = "outputs"
PLOT_PATH = os.path.join(PLOT_DIR, "tabu_convergence_{n_tasks}.png")
RUN_DIFFUSION_EXPERIMENT = False
CALIBRATION_DIR = os.path.join(PLOT_DIR, "calibration")


def calc_task_clock_per_node(results):
    from collections import defaultdict

    task_clock_per_node = defaultdict(float)

    for r in results:
        node = r.get("executor_node") or r.get("node")
        task_clock_ms = r.get("observed_task_clock_ms") or 0.0
        task_clock_per_node[node] += task_clock_ms

    return dict(task_clock_per_node)


def calc_memory_per_node(results):
    from collections import defaultdict

    memory_per_node = defaultdict(float)

    for r in results:
        node = r.get("executor_node") or r.get("node")
        memory_bytes = r.get("observed_memory_bytes") or 0
        memory_per_node[node] += memory_bytes

    return dict(memory_per_node)


def print_sample_results(results, title, limit=5):
    print(f"\n=== SAMPLE RESULTS: {title} ===")
    for r in results[:limit]:
        print(
            f"task_id={r['task_id']} "
            f"assigned={r['node']} "
            f"executor={r.get('executor_node')} "
            f"task_clock_ms={r.get('observed_task_clock_ms')} "
            f"memory_bytes={r.get('observed_memory_bytes')} "
            f"latency={r.get('latency'):.4f} "
            f"exec_time={r.get('execution_time'):.4f}"
        )


def plot_convergence(history, path):
    if not history or not history.get("obj"):
        print("No convergence history to plot.")
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    plt.figure(figsize=(7, 4))
    plt.plot(history["obj"])
    plt.xlabel("Iteration")
    plt.ylabel("Objective")
    plt.title("Tabu Convergence")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Convergence plot saved: {path}")


def export_calibration_dataset(path, tasks, results_by_mode, nodes):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    task_map = {task["task_id"]: task for task in tasks}

    with open(path, "w") as f:
        for mode, results in results_by_mode.items():
            for row in results:
                task = task_map[row["task_id"]]
                assigned_node_id = row["node"]
                assigned_node = nodes[assigned_node_id]
                executor_node_id = row.get("executor_node") or assigned_node_id
                executor_node = nodes.get(executor_node_id, assigned_node)

                record = {
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                    "mode": mode,
                    "task_id": task["task_id"],
                    "task_type": task["task_type"],
                    "task_size": task.get("task_size"),
                    "cpu_time_target_ms": task["cpu_time_target_ms"],
                    "memory_bytes": task["memory_bytes"],
                    "cpu_demand": task["cpu_demand"],
                    "memory_demand": task["memory_demand"],
                    "assigned_node": assigned_node_id,
                    "executor_node": executor_node_id,
                    "executor_host": row.get("executor_host"),
                    "executor_pid": row.get("executor_pid"),
                    "node_cpu_cap": assigned_node["cpu"],
                    "node_mem_cap": assigned_node["mem"],
                    "node_network_delay": assigned_node["network_delay"],
                    "node_idle_power_w": assigned_node["idle_power_w"],
                    "node_max_power_w": assigned_node["max_power_w"],
                    "executor_cpu_cap": executor_node["cpu"],
                    "executor_mem_cap": executor_node["mem"],
                    "executor_network_delay": executor_node["network_delay"],
                    "executor_idle_power_w": executor_node["idle_power_w"],
                    "executor_max_power_w": executor_node["max_power_w"],
                    "latency": row.get("latency"),
                    "execution_time": row.get("execution_time"),
                    "observed_task_clock_ms": row.get("observed_task_clock_ms"),
                    "observed_cpu_clock_ms": row.get("observed_cpu_clock_ms"),
                    "observed_memory_bytes": row.get("observed_memory_bytes"),
                    "chunks": row.get("chunks"),
                    "worker_output": row.get("output"),
                }
                f.write(json.dumps(record) + "\n")

    print(f"Calibration dataset saved: {path}")


tasks = generate_batch(N_TASKS)

print("=== GENERATED TASKS ===")
for t in tasks[:5]:
    print(
        f"task_id={t['task_id']} "
        f"type={t['task_type']} "
        f"cpu_time_target_ms={t['cpu_time_target_ms']:.2f} "
        f"memory_bytes={t['memory_bytes']} "
        f"cpu_demand={t['cpu_demand']:.3f} "
        f"memory_demand={t['memory_demand']:.3f}"
    )

res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

print("\n=== RANDOM ===")
print_metrics(metrics_random)
print_sample_results(res_random, "RANDOM")

E_ref = metrics_random["model_total_energy"]
L_ref = metrics_random["model_avg_latency"]

res_tabu_only, history_tabu_only = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
    local_mode="none",
)
metrics_tabu_only = compute_metrics(res_tabu_only, tasks, NODE_RESOURCES)

print("\n=== TABU ONLY ===")
print_metrics(metrics_tabu_only)
print_sample_results(res_tabu_only, "TABU ONLY")

print("\n=== COMPARISON: RANDOM vs TABU ONLY ===")
print_all_comparison_table(metrics_random, metrics_tabu_only, n_tasks=N_TASKS)

print("\n=== TASK CLOCK BREAKDOWN ===")
print(f"RANDOM total task clock ms: {metrics_random['real_total_task_clock_ms']:.2f}")
print(f"TABU ONLY total task clock ms:   {metrics_tabu_only['real_total_task_clock_ms']:.2f}")

print("\n=== ENERGY BREAKDOWN ===")
print(f"RANDOM estimated energy: {metrics_random['estimated_real_energy_j']:.4f} J ({metrics_random['estimated_real_energy_kwh']:.8f} kWh)")
print(f"TABU ONLY estimated energy:   {metrics_tabu_only['estimated_real_energy_j']:.4f} J ({metrics_tabu_only['estimated_real_energy_kwh']:.8f} kWh)")

print("\nRANDOM task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_random).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\nTABU ONLY task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_tabu_only).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\n=== MEMORY BREAKDOWN ===")
print(f"RANDOM avg observed memory bytes: {metrics_random['real_avg_memory_bytes']:.2f}")
print(f"TABU ONLY avg observed memory bytes:   {metrics_tabu_only['real_avg_memory_bytes']:.2f}")

print("\nRANDOM memory per node:")
for node, mem_bytes in calc_memory_per_node(res_random).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

print("\nTABU ONLY memory per node:")
for node, mem_bytes in calc_memory_per_node(res_tabu_only).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

plot_convergence(history_tabu_only, PLOT_PATH.format(n_tasks=N_TASKS))
export_calibration_dataset(
    os.path.join(
        CALIBRATION_DIR,
        f"workload_calibration_{N_TASKS}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.jsonl",
    ),
    tasks,
    {
        "random": res_random,
        "tabu": res_tabu_only,
    },
    NODE_RESOURCES,
)

if RUN_DIFFUSION_EXPERIMENT:
    res_tabu_diff, _ = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=E_ref,
        L_ref=L_ref,
        return_history=True,
        local_mode="diffusion",
    )
    metrics_tabu_diff = compute_metrics(res_tabu_diff, tasks, NODE_RESOURCES)

    print("\n=== EXPERIMENT: TABU + FINAL DIFFUSION ===")
    print_metrics(metrics_tabu_diff)
    print_sample_results(res_tabu_diff, "TABU + FINAL DIFFUSION")
    print("\n=== COMPARISON: TABU ONLY vs TABU + FINAL DIFFUSION ===")
    print_all_comparison_table(metrics_tabu_only, metrics_tabu_diff, n_tasks=N_TASKS)
