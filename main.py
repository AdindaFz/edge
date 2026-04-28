import os
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

res_tabu, history_tabu = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
)
metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

print("\n=== TABU DIFF ===")
print_metrics(metrics_tabu)
print_sample_results(res_tabu, "TABU")

print_all_comparison_table(metrics_random, metrics_tabu, n_tasks=N_TASKS)

print("\n=== TASK CLOCK BREAKDOWN ===")
print(f"RANDOM total task clock ms: {metrics_random['real_total_task_clock_ms']:.2f}")
print(f"TABU total task clock ms:   {metrics_tabu['real_total_task_clock_ms']:.2f}")

print("\n=== ENERGY BREAKDOWN ===")
print(f"RANDOM estimated energy: {metrics_random['estimated_real_energy_j']:.4f} J ({metrics_random['estimated_real_energy_kwh']:.8f} kWh)")
print(f"TABU estimated energy:   {metrics_tabu['estimated_real_energy_j']:.4f} J ({metrics_tabu['estimated_real_energy_kwh']:.8f} kWh)")

print("\nRANDOM task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_random).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\nTABU task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_tabu).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\n=== MEMORY BREAKDOWN ===")
print(f"RANDOM avg observed memory bytes: {metrics_random['real_avg_memory_bytes']:.2f}")
print(f"TABU avg observed memory bytes:   {metrics_tabu['real_avg_memory_bytes']:.2f}")

print("\nRANDOM memory per node:")
for node, mem_bytes in calc_memory_per_node(res_random).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

print("\nTABU memory per node:")
for node, mem_bytes in calc_memory_per_node(res_tabu).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

plot_convergence(history_tabu, PLOT_PATH.format(n_tasks=N_TASKS))
