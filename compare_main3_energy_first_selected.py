import json
import os
from pathlib import Path

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


TASK_COUNTS = [
    int(part.strip())
    for part in os.environ.get("TASK_COUNTS", "200,300,400").split(",")
    if part.strip()
]
TASK_SEED = int(os.environ.get("TASK_SEED", "42"))
N_RANDOM_BASELINES = int(os.environ.get("N_RANDOM_BASELINES", "5"))
LOCAL_MODE = "hybrid"

# Selected candidate from the energy-first sweep:
# keeps both real latency and estimated real energy below the 5x random baseline,
# while preserving a stronger latency gain than the most conservative option.
ENERGY_WEIGHT = float(os.environ.get("ENERGY_WEIGHT", "0.85"))
HIGH_POWER_PENALTY = float(os.environ.get("HIGH_POWER_PENALTY", "2.25"))
VPS_PENALTY_SCALE = float(os.environ.get("VPS_PENALTY_SCALE", "0.50"))

OUTPUT_PATH = (
    Path("/home/adinda-central/edge-computing-system/outputs")
    / "main3_energy_first_selected_200_300_400.json"
)


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
    print(f"RUN main3 selected energy-first n_tasks={n_tasks}")

    tasks = generate_batch(n_tasks, seed=TASK_SEED)

    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print(f"Random baseline run {idx + 1}/{N_RANDOM_BASELINES}")
        res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
        random_metric_runs.append(compute_metrics(res_random, tasks, NODE_RESOURCES))

    metrics_random = aggregate_metrics(random_metric_runs)

    res_main3, _ = run_offline_experiment(
        tasks,
        "tabu_legacy_hybrid",
        E_ref=metrics_random["model_total_energy"],
        L_ref=metrics_random["model_avg_latency"],
        return_history=True,
        local_mode=LOCAL_MODE,
        tabu_energy_weight=ENERGY_WEIGHT,
        tabu_high_power_penalty_weight=HIGH_POWER_PENALTY,
        tabu_vps_penalty_scale=VPS_PENALTY_SCALE,
    )
    metrics_main3 = compute_metrics(res_main3, tasks, NODE_RESOURCES)

    summary = {
        "n_tasks": n_tasks,
        "random_latency": metrics_random["real_avg_latency"],
        "main3_latency": metrics_main3["real_avg_latency"],
        "latency_gain": metrics_random["real_avg_latency"] - metrics_main3["real_avg_latency"],
        "random_energy_j": metrics_random["estimated_real_energy_j"],
        "main3_energy_j": metrics_main3["estimated_real_energy_j"],
        "energy_gain_j": metrics_random["estimated_real_energy_j"] - metrics_main3["estimated_real_energy_j"],
        "random_exec_time": metrics_random["real_avg_execution_time"],
        "main3_exec_time": metrics_main3["real_avg_execution_time"],
        "random_task_clock_ms": metrics_random["real_total_task_clock_ms"],
        "main3_task_clock_ms": metrics_main3["real_total_task_clock_ms"],
        "random_metrics": metrics_random,
        "main3_metrics": metrics_main3,
    }

    print(
        f"Random latency={summary['random_latency']:.4f} | "
        f"Main3 latency={summary['main3_latency']:.4f} | "
        f"Gain={summary['latency_gain']:.4f}"
    )
    print(
        f"Random energy={summary['random_energy_j']:.4f} J | "
        f"Main3 energy={summary['main3_energy_j']:.4f} J | "
        f"Gain={summary['energy_gain_j']:.4f} J"
    )

    return summary


def main():
    summaries = [run_case(n_tasks) for n_tasks in TASK_COUNTS]

    payload = {
        "task_seed": TASK_SEED,
        "task_counts": TASK_COUNTS,
        "n_random_baselines": N_RANDOM_BASELINES,
        "local_mode": LOCAL_MODE,
        "energy_weight": ENERGY_WEIGHT,
        "high_power_penalty_weight": HIGH_POWER_PENALTY,
        "vps_penalty_scale": VPS_PENALTY_SCALE,
        "summaries": summaries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print("\n================ MAIN3 SELECTED TABLE ================")
    print(
        f"{'n_tasks':>8} {'rnd_lat':>10} {'m3_lat':>10} {'lat_gain':>10} "
        f"{'rnd_energy':>12} {'m3_energy':>12} {'eng_gain':>12}"
    )
    print("-" * 80)
    for summary in summaries:
        print(
            f"{summary['n_tasks']:>8} "
            f"{summary['random_latency']:>10.4f} "
            f"{summary['main3_latency']:>10.4f} "
            f"{summary['latency_gain']:>10.4f} "
            f"{summary['random_energy_j']:>12.4f} "
            f"{summary['main3_energy_j']:>12.4f} "
            f"{summary['energy_gain_j']:>12.4f}"
        )

    print(f"\nSaved comparison: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
