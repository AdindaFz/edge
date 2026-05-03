import json
import os
from pathlib import Path

from central.assignment_engine import (
    TABU_ENERGY_WEIGHT,
    TABU_HIGH_POWER_PENALTY_WEIGHT,
)
from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


TASK_COUNTS = [
    int(part.strip())
    for part in os.environ.get("TASK_COUNTS", "100,200,300,400,500").split(",")
    if part.strip()
]
TASK_SEED = 42
LOCAL_MODE = os.environ.get("LOCAL_MODE", "hybrid")
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", "5"))
OUTPUT_PATH = Path("/home/adinda-central/edge-computing-system/outputs") / "best_setting_comparison.json"


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


def run_case(n_tasks):
    print("\n============================================================")
    print(f"RUN n_tasks={n_tasks}")

    tasks = generate_batch(n_tasks, seed=TASK_SEED)

    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print(f"Random baseline run {idx + 1}/{N_RANDOM_BASELINES}")
        res_random, _ = run_offline_experiment(
            tasks,
            "random",
            return_history=True,
        )
        random_metric_runs.append(compute_metrics(res_random, tasks, NODE_RESOURCES))
    metrics_random = aggregate_metrics(random_metric_runs)

    res_tabu, _ = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=metrics_random["model_total_energy"],
        L_ref=metrics_random["model_avg_latency"],
        return_history=True,
        local_mode=LOCAL_MODE,
        tabu_energy_weight=TABU_ENERGY_WEIGHT,
        tabu_high_power_penalty_weight=TABU_HIGH_POWER_PENALTY_WEIGHT,
    )
    metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

    summary = {
        "n_tasks": n_tasks,
        "random_latency": metrics_random["real_avg_latency"],
        "tabu_latency": metrics_tabu["real_avg_latency"],
        "latency_gain": metrics_random["real_avg_latency"] - metrics_tabu["real_avg_latency"],
        "random_energy_j": metrics_random["estimated_real_energy_j"],
        "tabu_energy_j": metrics_tabu["estimated_real_energy_j"],
        "energy_gain_j": metrics_random["estimated_real_energy_j"] - metrics_tabu["estimated_real_energy_j"],
        "random_exec_time": metrics_random["real_avg_execution_time"],
        "tabu_exec_time": metrics_tabu["real_avg_execution_time"],
        "random_task_clock_ms": metrics_random["real_total_task_clock_ms"],
        "tabu_task_clock_ms": metrics_tabu["real_total_task_clock_ms"],
        "random_metrics": metrics_random,
        "tabu_metrics": metrics_tabu,
    }

    print(
        f"Random latency={summary['random_latency']:.4f} | "
        f"Tabu latency={summary['tabu_latency']:.4f} | "
        f"Gain={summary['latency_gain']:.4f}"
    )
    print(
        f"Random energy={summary['random_energy_j']:.4f} J | "
        f"Tabu energy={summary['tabu_energy_j']:.4f} J | "
        f"Gain={summary['energy_gain_j']:.4f} J"
    )

    return summary


def main():
    summaries = [run_case(n_tasks) for n_tasks in TASK_COUNTS]

    payload = {
        "energy_weight": TABU_ENERGY_WEIGHT,
        "high_power_penalty_weight": TABU_HIGH_POWER_PENALTY_WEIGHT,
        "task_seed": TASK_SEED,
        "local_mode": LOCAL_MODE,
        "n_random_baselines": N_RANDOM_BASELINES,
        "summaries": summaries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print("\n==================== COMPARISON TABLE ====================")
    print(
        f"{'n_tasks':>8} {'rnd_lat':>10} {'tabu_lat':>10} {'lat_gain':>10} "
        f"{'rnd_energy':>12} {'tabu_energy':>12} {'eng_gain':>12}"
    )
    print("-" * 80)
    for summary in summaries:
        print(
            f"{summary['n_tasks']:>8} "
            f"{summary['random_latency']:>10.4f} "
            f"{summary['tabu_latency']:>10.4f} "
            f"{summary['latency_gain']:>10.4f} "
            f"{summary['random_energy_j']:>12.4f} "
            f"{summary['tabu_energy_j']:>12.4f} "
            f"{summary['energy_gain_j']:>12.4f}"
        )

    print(f"\nSaved comparison: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
