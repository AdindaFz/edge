import os
import sys

from central.offline_runner import (
    run_offline_experiment,
    compute_metrics,
    print_metrics,
    print_all_comparison_table,
)
from central.task_generator import generate_batch
from central.node_resources import NODE_RESOURCES


N_TASKS = int(os.environ.get("N_TASKS", sys.argv[1] if len(sys.argv) > 1 else 50))
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", sys.argv[2] if len(sys.argv) > 2 else 5))
TEST_MODE = os.environ.get("TEST_MODE", "0").lower() in {"1", "true", "yes", "on"}
LEGACY_ENERGY_WEIGHT = float(os.environ.get("LEGACY_ENERGY_WEIGHT", "0.5"))
LEGACY_LOCAL_MODE = os.environ.get("LEGACY_LOCAL_MODE", "hybrid")
LEGACY_HIGH_POWER_PENALTY = os.environ.get("LEGACY_HIGH_POWER_PENALTY")
LEGACY_VPS_PENALTY_SCALE = os.environ.get("LEGACY_VPS_PENALTY_SCALE")

if TEST_MODE:
    N_RANDOM_BASELINES = 1


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


def print_sample_results(results, title, limit=5):
    print(f"\n=== SAMPLE RESULTS: {title} ===")
    for row in results[:limit]:
        print(
            f"task_id={row['task_id']} "
            f"assigned={row['node']} "
            f"executor={row.get('executor_node')} "
            f"task_clock_ms={row.get('observed_task_clock_ms')} "
            f"latency={row.get('latency'):.4f} "
            f"exec_time={row.get('execution_time'):.4f}"
        )


def main():
    if TEST_MODE:
        print("=== TEST MODE ENABLED (MAIN3) ===")
        print("Using fast verification settings: N_RANDOM_BASELINES=1.")

    tasks = generate_batch(N_TASKS)

    print("=== GENERATED TASKS (MAIN3) ===")
    for task in tasks[:5]:
        print(
            f"task_id={task['task_id']} "
            f"type={task['task_type']} "
            f"cpu_time_target_ms={task['cpu_time_target_ms']:.2f} "
            f"memory_bytes={task['memory_bytes']} "
            f"cpu_demand={task['cpu_demand']:.3f} "
            f"memory_demand={task['memory_demand']:.3f}"
        )

    random_runs = []
    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print(f"\n=== RANDOM RUN {idx + 1}/{N_RANDOM_BASELINES} (MAIN3) ===")
        res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
        metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)
        random_runs.append(res_random)
        random_metric_runs.append(metrics_random)
        print_metrics(metrics_random)

    res_random = random_runs[0]
    metrics_random = aggregate_metrics(random_metric_runs)
    print("\n=== RANDOM BASELINE AVERAGE (MAIN3) ===")
    print_metrics(metrics_random)
    print_random_baseline_summary(random_metric_runs)
    print_sample_results(res_random, "RANDOM SAMPLE")

    e_ref = max(metrics_random["model_total_energy"], 1e-6)
    l_ref = max(metrics_random["model_avg_latency"], 1e-6)

    res_tabu_legacy_hybrid, _ = run_offline_experiment(
        tasks,
        "tabu_legacy_hybrid",
        E_ref=e_ref,
        L_ref=l_ref,
        return_history=True,
        local_mode=LEGACY_LOCAL_MODE,
        tabu_energy_weight=LEGACY_ENERGY_WEIGHT,
        tabu_high_power_penalty_weight=(
            float(LEGACY_HIGH_POWER_PENALTY)
            if LEGACY_HIGH_POWER_PENALTY is not None
            else None
        ),
        tabu_vps_penalty_scale=(
            float(LEGACY_VPS_PENALTY_SCALE)
            if LEGACY_VPS_PENALTY_SCALE is not None
            else None
        ),
    )
    metrics_tabu_legacy_hybrid = compute_metrics(res_tabu_legacy_hybrid, tasks, NODE_RESOURCES)

    print("\n=== TABU LEGACY OBJECTIVE + VPS PENALTIES ===")
    print_metrics(metrics_tabu_legacy_hybrid)
    print_sample_results(res_tabu_legacy_hybrid, "TABU LEGACY HYBRID SAMPLE")

    print("\n=== COMPARISON: RANDOM vs TABU LEGACY HYBRID ===")
    print_all_comparison_table(metrics_random, metrics_tabu_legacy_hybrid, n_tasks=N_TASKS)


if __name__ == "__main__":
    main()
