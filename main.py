import os
import json
import sys
from datetime import datetime
import numpy as np
try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None

from central.offline_runner import (
    run_offline_experiment,
    compute_metrics,
    print_metrics,
    print_all_comparison_table,
)
from central.optimizer_runner import (
    compute_total_cost_energy_focused,
    reporting_objective_scores,
)
from central.task_generator import generate_batch
from central.node_resources import NODE_RESOURCES


N_TASKS = int(os.environ.get("N_TASKS", sys.argv[1] if len(sys.argv) > 1 else 50))
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", sys.argv[2] if len(sys.argv) > 2 else 5))
PLOT_DIR = "outputs"
PLOT_PATH = os.path.join(PLOT_DIR, "tabu_convergence_{n_tasks}.png")
RUN_DIFFUSION_EXPERIMENT = False
CALIBRATION_DIR = os.path.join(PLOT_DIR, "calibration")
TEST_MODE = os.environ.get("TEST_MODE", "0").lower() in {"1", "true", "yes", "on"}
TABU_ENERGY_WEIGHT_OVERRIDE = os.environ.get("TABU_ENERGY_WEIGHT")
TABU_HIGH_POWER_PENALTY_OVERRIDE = os.environ.get("TABU_HIGH_POWER_PENALTY_WEIGHT")

if TEST_MODE:
    N_RANDOM_BASELINES = 1


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


def aggregate_metrics(metric_runs):
    from collections import defaultdict

    aggregated = {}
    metric_keys = [
        key for key, value in metric_runs[0].items()
        if isinstance(value, (int, float))
    ]
    for key in metric_keys:
        aggregated[key] = sum(run[key] for run in metric_runs) / len(metric_runs)

    distribution_keys = set()
    for run in metric_runs:
        distribution_keys.update(run.get("distribution", {}).keys())

    aggregated_distribution = {}
    for node in sorted(distribution_keys):
        aggregated_distribution[node] = (
            sum(run.get("distribution", {}).get(node, 0) for run in metric_runs) / len(metric_runs)
        )
    aggregated["distribution"] = aggregated_distribution
    return aggregated


def print_random_baseline_summary(metric_runs):
    print(f"\n=== RANDOM BASELINE SUMMARY ({len(metric_runs)} runs) ===")
    real_latency = [run["real_avg_latency"] for run in metric_runs]
    energy_j = [run["estimated_real_energy_j"] for run in metric_runs]
    task_clock = [run["real_total_task_clock_ms"] for run in metric_runs]

    print(
        "Avg real latency  : "
        f"{sum(real_latency) / len(real_latency):.4f} "
        f"(min={min(real_latency):.4f}, max={max(real_latency):.4f})"
    )
    print(
        "Avg energy (J)    : "
        f"{sum(energy_j) / len(energy_j):.4f} "
        f"(min={min(energy_j):.4f}, max={max(energy_j):.4f})"
    )
    print(
        "Total task clock  : "
        f"{sum(task_clock) / len(task_clock):.2f} ms "
        f"(min={min(task_clock):.2f}, max={max(task_clock):.2f})"
    )


def build_reporting_scores(metrics, E_ref, L_ref):
    energy_norm = (
        metrics["model_total_energy"] / max(E_ref, 1e-6)
        if E_ref is not None
        else metrics["model_total_energy"]
    )
    latency_norm = (
        metrics["model_avg_latency"] / max(L_ref, 1e-6)
        if L_ref is not None
        else metrics["model_avg_latency"]
    )
    return {
        "energy_norm": energy_norm,
        "latency_norm": latency_norm,
        **reporting_objective_scores(energy_norm, latency_norm),
    }


def print_reporting_scores(title, scores):
    print(f"\n=== REPORTING SCORE: {title} ===")
    print(f"Energy norm            : {scores['energy_norm']:.4f}")
    print(f"Latency norm           : {scores['latency_norm']:.4f}")
    print(f"Bounded energy score   : {scores['bounded_energy_score']:.4f}")
    print(f"Bounded latency score  : {scores['bounded_latency_score']:.4f}")


def print_convergence_summary(history, reference_cost):
    if not history or not history.get("obj") or reference_cost is None or reference_cost <= 0:
        print("\n=== CONVERGENCE SUMMARY ===")
        print("Normalized convergence summary unavailable.")
        return

    first_raw = float(history["obj"][0])
    last_raw = float(history["obj"][-1])
    first_norm = first_raw / reference_cost
    last_norm = last_raw / reference_cost
    improvement = first_norm - last_norm

    print("\n=== CONVERGENCE SUMMARY ===")
    print(
        f"Raw objective        : {first_raw:.4f} -> {last_raw:.4f}"
    )
    print(
        f"Normalized objective : {first_norm:.4f} -> {last_norm:.4f}"
    )
    print(
        f"Improvement vs start : {improvement:.4f}"
    )


def build_assignment_vector(results, tasks, nodes):
    node_ids = list(nodes.keys())
    node_index = {node_id: idx for idx, node_id in enumerate(node_ids)}
    result_map = {row["task_id"]: row for row in results}
    return np.array(
        [node_index[result_map[task["task_id"]]["node"]] for task in tasks],
        dtype=int,
    )


def compute_reference_cost(results, tasks, nodes, E_ref, L_ref):
    assignments = build_assignment_vector(results, tasks, nodes)
    cpu_demands = np.array([task["cpu_demand"] for task in tasks], dtype=float)
    mem_demands = np.array([task["memory_demand"] for task in tasks], dtype=float)
    cpu_caps = np.array([float(nodes[node_id]["cpu"]) for node_id in nodes.keys()], dtype=float)
    mem_caps = np.array([float(nodes[node_id]["mem"]) for node_id in nodes.keys()], dtype=float)
    latency_ms = np.array([float(nodes[node_id]["network_delay"]) for node_id in nodes.keys()], dtype=float)
    idle_powers = np.array([float(nodes[node_id]["idle_power_w"]) for node_id in nodes.keys()], dtype=float)
    max_powers = np.array([float(nodes[node_id]["max_power_w"]) for node_id in nodes.keys()], dtype=float)

    reference_cost, _ = compute_total_cost_energy_focused(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        latency_ms,
        idle_powers=idle_powers,
        max_powers=max_powers,
        E_ref=E_ref,
        L_ref=L_ref,
    )
    return reference_cost


def plot_convergence(history, path, reference_cost=None):
    if plt is None:
        print("Skipping convergence plot because matplotlib is not installed.")
        return

    if not history or not history.get("obj"):
        print("No convergence history to plot.")
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    if reference_cost is not None and reference_cost > 0:
        plotted_obj = [min(max(value / reference_cost, 0.0), 1.0) for value in history["obj"]]
        ylabel = "Objective / Random Baseline Cost"
        title = "Tabu Convergence (Relative to Random Baseline)"
    else:
        plotted_obj = history["obj"]
        ylabel = "Objective"
        title = "Tabu Convergence"

    plt.figure(figsize=(7, 4))
    plt.plot(plotted_obj)
    plt.xlabel("Iteration")
    plt.ylabel(ylabel)
    plt.title(title)
    y_min = min(plotted_obj)
    y_max = max(plotted_obj)
    if y_max - y_min < 1e-9:
        pad = max(0.01, abs(y_max) * 0.05)
    else:
        pad = max(0.01, (y_max - y_min) * 0.12)
    lower = max(0.0, y_min - pad)
    upper = y_max + pad
    plt.ylim(lower, upper)
    plt.grid(True, alpha=0.3)
    if reference_cost is not None and reference_cost > 0:
        plt.axhline(1.0, color="tab:red", linestyle="--", linewidth=1, alpha=0.7)
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


if TEST_MODE:
    print("=== TEST MODE ENABLED ===")
    print(
        "Using fast verification settings: "
        "N_RANDOM_BASELINES=1, skip plots/export, no optional diffusion experiment."
    )
    if TABU_ENERGY_WEIGHT_OVERRIDE is not None or TABU_HIGH_POWER_PENALTY_OVERRIDE is not None:
        print(
            "Tabu overrides: "
            f"energy_weight={TABU_ENERGY_WEIGHT_OVERRIDE or 'default'}, "
            f"high_power_penalty={TABU_HIGH_POWER_PENALTY_OVERRIDE or 'default'}"
        )

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

random_runs = []
random_metric_runs = []
for idx in range(N_RANDOM_BASELINES):
    print(f"\n=== RANDOM RUN {idx + 1}/{N_RANDOM_BASELINES} ===")
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)
    random_runs.append(res_random)
    random_metric_runs.append(metrics_random)
    print_metrics(metrics_random)

res_random = random_runs[0]
metrics_random = aggregate_metrics(random_metric_runs)
print_random_baseline_summary(random_metric_runs)
print("\n=== RANDOM BASELINE AVERAGE ===")
print_metrics(metrics_random)
print_sample_results(res_random, "RANDOM SAMPLE")

E_ref = metrics_random["model_total_energy"]
L_ref = metrics_random["model_avg_latency"]
random_reference_cost = compute_reference_cost(
    random_runs[-1],
    tasks,
    NODE_RESOURCES,
    E_ref,
    L_ref,
)

res_tabu_only, history_tabu_only = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
    local_mode="hybrid",
    tabu_energy_weight=(
        float(TABU_ENERGY_WEIGHT_OVERRIDE)
        if TABU_ENERGY_WEIGHT_OVERRIDE is not None
        else None
    ),
    tabu_high_power_penalty_weight=(
        float(TABU_HIGH_POWER_PENALTY_OVERRIDE)
        if TABU_HIGH_POWER_PENALTY_OVERRIDE is not None
        else None
    ),
)
metrics_tabu_only = compute_metrics(res_tabu_only, tasks, NODE_RESOURCES)
reporting_random = build_reporting_scores(metrics_random, E_ref, L_ref)
reporting_tabu_only = build_reporting_scores(metrics_tabu_only, E_ref, L_ref)

print("\n=== TABU + DIFFUSION ===")
print_metrics(metrics_tabu_only)
print_sample_results(res_tabu_only, "TABU + DIFFUSION")
print_reporting_scores("AVERAGE RANDOM", reporting_random)
print_reporting_scores("TABU + DIFFUSION", reporting_tabu_only)

print("\n=== COMPARISON: AVERAGE RANDOM vs TABU + DIFFUSION ===")
print_all_comparison_table(metrics_random, metrics_tabu_only, n_tasks=N_TASKS)
print_convergence_summary(history_tabu_only, random_reference_cost)

print("\n=== TASK CLOCK BREAKDOWN ===")
print(f"AVERAGE RANDOM total task clock ms: {metrics_random['real_total_task_clock_ms']:.2f}")
print(f"TABU + DIFFUSION total task clock ms:   {metrics_tabu_only['real_total_task_clock_ms']:.2f}")

print("\n=== ENERGY BREAKDOWN ===")
print(f"AVERAGE RANDOM estimated energy: {metrics_random['estimated_real_energy_j']:.4f} J ({metrics_random['estimated_real_energy_kwh']:.8f} kWh)")
print(f"TABU + DIFFUSION estimated energy:   {metrics_tabu_only['estimated_real_energy_j']:.4f} J ({metrics_tabu_only['estimated_real_energy_kwh']:.8f} kWh)")

print("\nRANDOM SAMPLE task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_random).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\nTABU + DIFFUSION task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_tabu_only).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\n=== MEMORY BREAKDOWN ===")
print(f"AVERAGE RANDOM avg observed memory bytes: {metrics_random['real_avg_memory_bytes']:.2f}")
print(f"TABU + DIFFUSION avg observed memory bytes:   {metrics_tabu_only['real_avg_memory_bytes']:.2f}")

print("\nRANDOM SAMPLE memory per node:")
for node, mem_bytes in calc_memory_per_node(res_random).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

print("\nTABU + DIFFUSION memory per node:")
for node, mem_bytes in calc_memory_per_node(res_tabu_only).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

if not TEST_MODE:
    plot_convergence(
        history_tabu_only,
        PLOT_PATH.format(n_tasks=N_TASKS),
        reference_cost=random_reference_cost,
    )
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
else:
    print("\n=== TEST MODE ===")
    print("Skipping convergence plot and calibration dataset export.")

if RUN_DIFFUSION_EXPERIMENT and not TEST_MODE:
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
