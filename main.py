import os
import json
import sys
from datetime import datetime
import matplotlib.pyplot as plt

from central.offline_runner import (
    BASELINE_SEED,
    RANDOM_BASELINE_DIRICHLET_ALPHA,
    RANDOM_BASELINE_MODE,
    run_offline_experiment,
    compute_metrics,
    print_metrics,
    print_all_comparison_table,
)
from central.task_generator import generate_batch
from central.node_resources import NODE_RESOURCES


N_TASKS = 300
PLOT_DIR = "outputs"
RUN_ID = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
RUN_OUTPUT_DIR = os.path.join(PLOT_DIR, "runs")
PLOT_PATH = os.path.join(RUN_OUTPUT_DIR, "tabu_diffusion_convergence_{n_tasks}_{run_id}.png")
COMPARISON_PLOT_PATH = os.path.join(RUN_OUTPUT_DIR, "random_vs_tabu_metrics_{n_tasks}_{run_id}.png")
RUN_DIFFUSION_EXPERIMENT = False
CALIBRATION_DIR = os.path.join(PLOT_DIR, "calibration")
OBJECTIVE_ENERGY_MODEL = os.getenv("OBJECTIVE_ENERGY_MODEL", "calibrated_real")
OBJECTIVE_ENERGY_WEIGHT = float(os.getenv("OBJECTIVE_ENERGY_WEIGHT", "0.5"))
OBJECTIVE_LATENCY_WEIGHT = 1.0 - OBJECTIVE_ENERGY_WEIGHT


class TeeStdout:
    def __init__(self, stream):
        self.stream = stream
        self.lines = []
        self._buffer = ""

    def write(self, text):
        self.stream.write(text)
        self.stream.flush()

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.lines.append(line)

    def flush(self):
        self.stream.flush()

    def snapshot(self):
        lines = list(self.lines)
        if self._buffer:
            lines.append(self._buffer)
        return lines


TERMINAL_CAPTURE = TeeStdout(sys.stdout)
sys.stdout = TERMINAL_CAPTURE


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


def assignment_map(results):
    return {
        row["task_id"]: row.get("node")
        for row in sorted(results, key=lambda item: item["task_id"])
    }


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


def plot_random_vs_tabu_metrics(metrics_random, metrics_tabu, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    panel_specs = [
        (
            "Real Estimated Energy",
            "Joule",
            [
                metrics_random["estimated_real_energy_j"],
                metrics_tabu["estimated_real_energy_j"],
            ],
        ),
        (
            "Real Average Latency",
            "Second",
            [
                metrics_random["real_avg_latency"],
                metrics_tabu["real_avg_latency"],
            ],
        ),
        (
            "Model Energy",
            "Model unit",
            [
                metrics_random["model_energy"],
                metrics_tabu["model_energy"],
            ],
        ),
        (
            "Model Latency",
            "Model unit",
            [
                metrics_random["model_avg_latency"],
                metrics_tabu["model_avg_latency"],
            ],
        ),
    ]

    fig = plt.figure(figsize=(13, 7))
    grid = fig.add_gridspec(2, 3, width_ratios=[1.0, 1.0, 0.95])
    axes = [
        fig.add_subplot(grid[0, 0]),
        fig.add_subplot(grid[0, 1]),
        fig.add_subplot(grid[1, 0]),
        fig.add_subplot(grid[1, 1]),
    ]
    labels = ["Random", "Tabu + Diffusion"]
    colors = ["#6b7280", "#0ea5a3"]

    for ax, (title, ylabel, values) in zip(axes, panel_specs):
        bars = ax.bar(labels, values, color=colors, width=0.62)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        ax.tick_params(axis="x", rotation=8)

        ymax = max(values) if values else 0
        for bar, value in zip(bars, values):
            label = f"{value:.4f}" if abs(value) < 100 else f"{value:.2f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(ymax * 0.015, 1e-9),
                label,
                ha="center",
                va="bottom",
                fontsize=8,
            )

    improvement_ax = fig.add_subplot(grid[:, 2])
    improvement_ax.axis("off")
    energy_delta = metrics_tabu["estimated_real_energy_j"] - metrics_random["estimated_real_energy_j"]
    latency_delta = metrics_tabu["real_avg_latency"] - metrics_random["real_avg_latency"]
    energy_pct = energy_delta / max(metrics_random["estimated_real_energy_j"], 1e-9) * 100.0
    latency_pct = latency_delta / max(metrics_random["real_avg_latency"], 1e-9) * 100.0
    model_energy_delta = (
        metrics_tabu["model_energy"]
        - metrics_random["model_energy"]
    )
    model_energy_pct = (
        model_energy_delta
        / max(metrics_random["model_energy"], 1e-9)
        * 100.0
    )

    summary_text = (
        "Tabu - Random\n\n"
        f"Real energy: {energy_delta:+.2f} J ({energy_pct:+.2f}%)\n"
        f"Real latency: {latency_delta:+.4f} s ({latency_pct:+.2f}%)\n"
        f"Model energy: {model_energy_delta:+.2f} ({model_energy_pct:+.2f}%)"
    )
    improvement_ax.text(
        0.02,
        0.94,
        summary_text,
        va="top",
        fontsize=11,
        family="monospace",
    )

    fig.suptitle("Random vs Tabu + Diffusion", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Comparison metrics plot saved: {path}")


def summarize_convergence(history):
    if not history or not history.get("obj"):
        return {
            "available": False,
            "iterations": 0,
            "initial_objective": None,
            "final_objective": None,
            "best_objective": None,
            "best_iteration": None,
            "improvement_abs": None,
            "improvement_pct": None,
            "samples": [],
        }

    obj = [float(v) for v in history["obj"]]
    times = [float(v) for v in history.get("time", [])]
    best_objective = min(obj)
    best_iteration = obj.index(best_objective)
    initial_objective = obj[0]
    final_objective = obj[-1]
    improvement_abs = initial_objective - best_objective
    improvement_pct = (
        (improvement_abs / abs(initial_objective)) * 100.0
        if initial_objective
        else 0.0
    )

    sample_iterations = sorted(
        set(
            [0, len(obj) - 1, best_iteration]
            + [i for i in range(0, len(obj), 25)]
        )
    )
    samples = []
    for i in sample_iterations:
        if 0 <= i < len(obj):
            samples.append(
                {
                    "iteration": i,
                    "objective": obj[i],
                    "elapsed_seconds": times[i] if i < len(times) else None,
                }
            )

    return {
        "available": True,
        "iterations": len(obj),
        "initial_objective": initial_objective,
        "final_objective": final_objective,
        "best_objective": best_objective,
        "best_iteration": best_iteration,
        "improvement_abs": improvement_abs,
        "improvement_pct": improvement_pct,
        "samples": samples,
    }


def print_convergence_summary(summary, title):
    print(f"\n=== CONVERGENCE: {title} ===")
    if not summary["available"]:
        print("No convergence history.")
        return

    print(f"Iterations       : {summary['iterations']}")
    print(f"Initial objective: {summary['initial_objective']:.6f}")
    print(f"Final objective  : {summary['final_objective']:.6f}")
    print(f"Best objective   : {summary['best_objective']:.6f}")
    print(f"Best iteration   : {summary['best_iteration']}")
    print(f"Improvement      : {summary['improvement_abs']:.6f} ({summary['improvement_pct']:.2f}%)")

    print("\nSampled objective trace:")
    print(f"{'Iter':>6} {'Objective':>14} {'Elapsed(s)':>12}")
    print("-" * 36)
    for row in summary["samples"]:
        elapsed = row["elapsed_seconds"]
        elapsed_text = f"{elapsed:.4f}" if elapsed is not None else "-"
        print(f"{row['iteration']:>6} {row['objective']:>14.6f} {elapsed_text:>12}")


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    return value


def save_run_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(json_safe(payload), f, indent=2)
    print(f"Run JSON saved: {path}")


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


print(f"=== RUN ID: {RUN_ID} ===")
print(
    "=== OBJECTIVE CONFIG ===\n"
    f"energy_model={OBJECTIVE_ENERGY_MODEL} "
    f"energy_weight={OBJECTIVE_ENERGY_WEIGHT:.2f} "
    f"latency_weight={OBJECTIVE_LATENCY_WEIGHT:.2f}"
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

res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
metrics_random = compute_metrics(
    res_random,
    tasks,
    NODE_RESOURCES,
    energy_model=OBJECTIVE_ENERGY_MODEL,
)

print("\n=== RANDOM ===")
print_metrics(metrics_random)
print_sample_results(res_random, "RANDOM")

E_ref = metrics_random["model_energy"]
L_ref = metrics_random["model_avg_latency"]

res_tabu_diff, history_tabu_diff = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
    local_mode="diffusion",
    tabu_energy_weight=OBJECTIVE_ENERGY_WEIGHT,
    tabu_energy_model=OBJECTIVE_ENERGY_MODEL,
)
P_ref = (
    history_tabu_diff.get("resource_pressure_ref")
    if history_tabu_diff is not None
    else None
)
metrics_tabu_diff = compute_metrics(
    res_tabu_diff,
    tasks,
    NODE_RESOURCES,
    energy_model=OBJECTIVE_ENERGY_MODEL,
)

print("\n=== TABU + DIFFUSION ===")
print_metrics(metrics_tabu_diff)
print_sample_results(res_tabu_diff, "TABU + DIFFUSION")

print("\n=== COMPARISON: RANDOM vs TABU + DIFFUSION ===")
print_all_comparison_table(metrics_random, metrics_tabu_diff, n_tasks=N_TASKS)

print("\n=== TASK CLOCK BREAKDOWN ===")
print(f"RANDOM total task clock ms: {metrics_random['real_total_task_clock_ms']:.2f}")
print(f"TABU + DIFFUSION total task clock ms:   {metrics_tabu_diff['real_total_task_clock_ms']:.2f}")

print("\n=== ENERGY BREAKDOWN ===")
print(f"RANDOM estimated energy: {metrics_random['estimated_real_energy_j']:.4f} J ({metrics_random['estimated_real_energy_kwh']:.8f} kWh)")
print(f"TABU + DIFFUSION estimated energy:   {metrics_tabu_diff['estimated_real_energy_j']:.4f} J ({metrics_tabu_diff['estimated_real_energy_kwh']:.8f} kWh)")

print("\nRANDOM task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_random).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\nTABU + DIFFUSION task clock per node:")
for node, clock_ms in calc_task_clock_per_node(res_tabu_diff).items():
    print(f"  {node}: {clock_ms:.2f} ms")

print("\n=== MEMORY BREAKDOWN ===")
print(f"RANDOM avg observed memory bytes: {metrics_random['real_avg_memory_bytes']:.2f}")
print(f"TABU + DIFFUSION avg observed memory bytes:   {metrics_tabu_diff['real_avg_memory_bytes']:.2f}")

print("\nRANDOM memory per node:")
for node, mem_bytes in calc_memory_per_node(res_random).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

print("\nTABU + DIFFUSION memory per node:")
for node, mem_bytes in calc_memory_per_node(res_tabu_diff).items():
    print(f"  {node}: {mem_bytes:.0f} bytes")

plot_path = PLOT_PATH.format(n_tasks=N_TASKS, run_id=RUN_ID)
comparison_plot_path = COMPARISON_PLOT_PATH.format(n_tasks=N_TASKS, run_id=RUN_ID)
convergence_tabu_diff = summarize_convergence(history_tabu_diff)
print_convergence_summary(convergence_tabu_diff, "TABU + DIFFUSION")
plot_convergence(history_tabu_diff, plot_path)
plot_random_vs_tabu_metrics(metrics_random, metrics_tabu_diff, comparison_plot_path)
export_calibration_dataset(
    os.path.join(
        CALIBRATION_DIR,
        f"workload_calibration_{N_TASKS}_{RUN_ID}.jsonl",
    ),
    tasks,
    {
        "random": res_random,
        "tabu_diffusion": res_tabu_diff,
    },
    NODE_RESOURCES,
)

res_tabu_final_diff = None
metrics_tabu_final_diff = None

if RUN_DIFFUSION_EXPERIMENT:
    res_tabu_final_diff, _ = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=E_ref,
        L_ref=L_ref,
        P_ref=P_ref,
        return_history=True,
        local_mode="final_diffusion",
    )
    metrics_tabu_final_diff = compute_metrics(
        res_tabu_final_diff,
        tasks,
        NODE_RESOURCES,
        energy_model=OBJECTIVE_ENERGY_MODEL,
    )

    print("\n=== EXPERIMENT: TABU + FINAL DIFFUSION ===")
    print_metrics(metrics_tabu_final_diff)
    print_sample_results(res_tabu_final_diff, "TABU + FINAL DIFFUSION")
    print("\n=== COMPARISON: TABU + DIFFUSION vs TABU + FINAL DIFFUSION ===")
    print_all_comparison_table(metrics_tabu_diff, metrics_tabu_final_diff, n_tasks=N_TASKS)

run_json_path = os.path.join(RUN_OUTPUT_DIR, f"run_{N_TASKS}_{RUN_ID}.json")
save_run_json(
    run_json_path,
    {
        "run_id": RUN_ID,
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "config": {
            "n_tasks": N_TASKS,
            "run_diffusion_experiment": RUN_DIFFUSION_EXPERIMENT,
            "primary_mode": "tabu_diffusion",
            "plot_path": plot_path,
            "comparison_plot_path": comparison_plot_path,
            "objective_weights": {
                "energy": OBJECTIVE_ENERGY_WEIGHT,
                "latency": OBJECTIVE_LATENCY_WEIGHT,
            },
            "objective_energy_model": OBJECTIVE_ENERGY_MODEL,
            "random_baseline_mode": RANDOM_BASELINE_MODE,
            "random_baseline_dirichlet_alpha": RANDOM_BASELINE_DIRICHLET_ALPHA,
            "random_baseline_seed": BASELINE_SEED,
        },
        "references": {
            "E_ref": E_ref,
            "L_ref": L_ref,
            "P_ref": P_ref,
        },
        "tasks": tasks,
        "metrics": {
            "random": metrics_random,
            "tabu_diffusion": metrics_tabu_diff,
            "tabu_final_diffusion": metrics_tabu_final_diff,
        },
        "histories": {
            "tabu_diffusion": history_tabu_diff,
        },
        "results": {
            "random": res_random,
            "tabu_diffusion": res_tabu_diff,
            "tabu_final_diffusion": res_tabu_final_diff,
        },
        "assignments": {
            "random": assignment_map(res_random),
            "tabu_diffusion": assignment_map(res_tabu_diff),
            "tabu_final_diffusion": (
                assignment_map(res_tabu_final_diff)
                if res_tabu_final_diff is not None
                else None
            ),
        },
        "convergence": {
            "tabu_diffusion": convergence_tabu_diff,
        },
        "terminal_output": TERMINAL_CAPTURE.snapshot(),
    },
)
