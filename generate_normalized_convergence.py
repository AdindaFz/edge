import json
import math
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.optimizer_runner import compute_total_cost_energy_focused
from central.task_generator import generate_batch


TASK_COUNTS = [
    int(part.strip())
    for part in os.environ.get("TASK_COUNTS", "100,200,300,400,500").split(",")
    if part.strip()
]
TASK_SEED = int(os.environ.get("TASK_SEED", "42"))
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", "5"))
OUTPUT_DIR = Path("/home/adinda-central/edge-computing-system/outputs")
SUMMARY_PATH = OUTPUT_DIR / "normalized_convergence_summary.json"


def aggregate_metrics(metric_runs):
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


def compute_limits(values):
    y_min = min(values)
    y_max = max(values)
    if y_max - y_min < 1e-9:
        pad = max(0.01, abs(y_max) * 0.05)
    else:
        pad = max(0.01, (y_max - y_min) * 0.12)
    lower = max(0.0, y_min - pad)
    upper = y_max + pad
    return lower, upper


def plot_single(task_count, normalized_obj, out_path):
    xs = list(range(len(normalized_obj)))
    lower, upper = compute_limits(normalized_obj)

    plt.figure(figsize=(7, 4))
    plt.plot(xs, normalized_obj, linewidth=2.2, color="tab:blue", alpha=0.9)
    plt.xlabel("Iteration")
    plt.ylabel("Normalized Objective")
    plt.title(f"Normalized Tabu Convergence - {task_count} Tasks", fontweight="bold")
    plt.ylim(lower, upper)
    plt.grid(True, alpha=0.3)
    plt.text(
        0.98,
        0.98,
        f"Final: {normalized_obj[-1]:.4f}",
        transform=plt.gca().transAxes,
        fontsize=9,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_combined(collected, out_path):
    if not collected:
        return

    n = len(collected)
    ncols = 2
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.8 * nrows))
    axes = axes.flatten()

    for ax, item in zip(axes, collected):
        task_count = item["task_count"]
        ys = item["normalized_obj"]
        xs = list(range(len(ys)))
        lower, upper = compute_limits(ys)

        ax.plot(xs, ys, linewidth=2.0, color="tab:blue", alpha=0.9)
        ax.set_title(f"{task_count} Tasks", fontsize=11, fontweight="bold")
        ax.set_xlabel("Iteration", fontsize=9)
        ax.set_ylabel("Normalized Objective", fontsize=9)
        ax.set_ylim(lower, upper)
        ax.grid(True, alpha=0.3)
        ax.text(
            0.98,
            0.98,
            f"Final: {ys[-1]:.4f}",
            transform=ax.transAxes,
            fontsize=8.5,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

    for ax in axes[len(collected):]:
        ax.axis("off")

    fig.suptitle("Normalized Objective Function Convergence History", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run_case(task_count):
    print("\n============================================================")
    print(f"RUN normalized convergence n_tasks={task_count}")

    tasks = generate_batch(task_count, seed=TASK_SEED)

    random_runs = []
    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print(f"Random baseline run {idx + 1}/{N_RANDOM_BASELINES}")
        res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
        random_runs.append(res_random)
        random_metric_runs.append(compute_metrics(res_random, tasks, NODE_RESOURCES))

    metrics_random = aggregate_metrics(random_metric_runs)
    e_ref = metrics_random["model_total_energy"]
    l_ref = metrics_random["model_avg_latency"]
    random_reference_cost = compute_reference_cost(
        random_runs[-1],
        tasks,
        NODE_RESOURCES,
        e_ref,
        l_ref,
    )

    _, history = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=e_ref,
        L_ref=l_ref,
        return_history=True,
        local_mode="hybrid",
    )

    raw_obj = [float(v) for v in history["obj"]]
    normalized_obj = [float(v) / max(random_reference_cost, 1e-6) for v in raw_obj]

    out_path = OUTPUT_DIR / f"tabu_convergence_{task_count}_normalized.png"
    plot_single(task_count, normalized_obj, out_path)

    print(
        f"[DONE] {task_count} tasks | "
        f"raw {raw_obj[0]:.4f} -> {raw_obj[-1]:.4f} | "
        f"norm {normalized_obj[0]:.4f} -> {normalized_obj[-1]:.4f} | "
        f"saved {out_path}"
    )

    return {
        "task_count": task_count,
        "random_reference_cost": random_reference_cost,
        "raw_obj_start": raw_obj[0],
        "raw_obj_end": raw_obj[-1],
        "normalized_obj_start": normalized_obj[0],
        "normalized_obj_end": normalized_obj[-1],
        "normalized_obj": normalized_obj,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    collected = [run_case(task_count) for task_count in TASK_COUNTS]
    combined_path = OUTPUT_DIR / "tabu_convergence_combined_normalized.png"
    plot_combined(collected, combined_path)

    serializable = []
    for item in collected:
        serializable.append({
            k: v for k, v in item.items() if k != "normalized_obj"
        })

    with SUMMARY_PATH.open("w") as f:
        json.dump(
            {
                "task_seed": TASK_SEED,
                "n_random_baselines": N_RANDOM_BASELINES,
                "summaries": serializable,
                "combined_plot": str(combined_path),
            },
            f,
            indent=2,
        )

    print(f"\n[DONE] Combined normalized convergence figure saved {combined_path}")
    print(f"[DONE] Summary saved {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
