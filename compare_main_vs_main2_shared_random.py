import json
import os
from pathlib import Path

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


TASK_COUNTS = [
    int(part.strip())
    for part in os.environ.get("TASK_COUNTS", "100,200").split(",")
    if part.strip()
]
TASK_SEED = int(os.environ.get("TASK_SEED", "42"))
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", "5"))
OUTPUT_PATH = Path("/home/adinda-central/edge-computing-system/outputs") / "main_vs_main2_shared_random.json"


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


def summarize_case(n_tasks):
    print("\n============================================================")
    print(f"RUN shared-random comparison n_tasks={n_tasks}")

    tasks = generate_batch(n_tasks, seed=TASK_SEED)

    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print(f"Shared random baseline run {idx + 1}/{N_RANDOM_BASELINES}")
        res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
        random_metric_runs.append(compute_metrics(res_random, tasks, NODE_RESOURCES))
    metrics_random = aggregate_metrics(random_metric_runs)

    e_ref = max(metrics_random["model_total_energy"], 1e-6)
    l_ref = max(metrics_random["model_avg_latency"], 1e-6)

    res_main, _ = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=e_ref,
        L_ref=l_ref,
        return_history=True,
        local_mode="hybrid",
    )
    metrics_main = compute_metrics(res_main, tasks, NODE_RESOURCES)

    res_main2, _ = run_offline_experiment(
        tasks,
        "tabu_legacy",
        E_ref=e_ref,
        L_ref=l_ref,
        return_history=True,
        local_mode="hybrid",
        tabu_energy_weight=0.5,
    )
    metrics_main2 = compute_metrics(res_main2, tasks, NODE_RESOURCES)

    summary = {
        "n_tasks": n_tasks,
        "random": {
            "real_avg_latency": metrics_random["real_avg_latency"],
            "estimated_real_energy_j": metrics_random["estimated_real_energy_j"],
            "real_avg_execution_time": metrics_random["real_avg_execution_time"],
            "real_total_task_clock_ms": metrics_random["real_total_task_clock_ms"],
        },
        "main": {
            "real_avg_latency": metrics_main["real_avg_latency"],
            "estimated_real_energy_j": metrics_main["estimated_real_energy_j"],
            "real_avg_execution_time": metrics_main["real_avg_execution_time"],
            "real_total_task_clock_ms": metrics_main["real_total_task_clock_ms"],
            "latency_gain_vs_random": metrics_random["real_avg_latency"] - metrics_main["real_avg_latency"],
            "energy_gain_vs_random_j": metrics_random["estimated_real_energy_j"] - metrics_main["estimated_real_energy_j"],
        },
        "main2": {
            "real_avg_latency": metrics_main2["real_avg_latency"],
            "estimated_real_energy_j": metrics_main2["estimated_real_energy_j"],
            "real_avg_execution_time": metrics_main2["real_avg_execution_time"],
            "real_total_task_clock_ms": metrics_main2["real_total_task_clock_ms"],
            "latency_gain_vs_random": metrics_random["real_avg_latency"] - metrics_main2["real_avg_latency"],
            "energy_gain_vs_random_j": metrics_random["estimated_real_energy_j"] - metrics_main2["estimated_real_energy_j"],
        },
    }

    print(
        f"Random | latency={summary['random']['real_avg_latency']:.4f} "
        f"energy={summary['random']['estimated_real_energy_j']:.4f} J"
    )
    print(
        f"Main   | latency={summary['main']['real_avg_latency']:.4f} "
        f"energy={summary['main']['estimated_real_energy_j']:.4f} J"
    )
    print(
        f"Main2  | latency={summary['main2']['real_avg_latency']:.4f} "
        f"energy={summary['main2']['estimated_real_energy_j']:.4f} J"
    )

    return summary


def main():
    summaries = [summarize_case(n_tasks) for n_tasks in TASK_COUNTS]
    payload = {
        "task_seed": TASK_SEED,
        "task_counts": TASK_COUNTS,
        "n_random_baselines": N_RANDOM_BASELINES,
        "summaries": summaries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print("\n==================== SHARED RANDOM TABLE ====================")
    print(
        f"{'n_tasks':>8} {'rnd_lat':>10} {'main_lat':>10} {'main2_lat':>10} "
        f"{'rnd_eng':>12} {'main_eng':>12} {'main2_eng':>12}"
    )
    print("-" * 90)
    for summary in summaries:
        print(
            f"{summary['n_tasks']:>8} "
            f"{summary['random']['real_avg_latency']:>10.4f} "
            f"{summary['main']['real_avg_latency']:>10.4f} "
            f"{summary['main2']['real_avg_latency']:>10.4f} "
            f"{summary['random']['estimated_real_energy_j']:>12.4f} "
            f"{summary['main']['estimated_real_energy_j']:>12.4f} "
            f"{summary['main2']['estimated_real_energy_j']:>12.4f}"
        )

    print(f"\nSaved comparison: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
