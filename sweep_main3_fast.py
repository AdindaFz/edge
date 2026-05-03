import json
from pathlib import Path

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


TASK_COUNT = 100
TASK_SEED = 42
LOCAL_MODE = "hybrid"
N_RANDOM_BASELINES = 5
OUTPUT_PATH = Path("/home/adinda-central/edge-computing-system/outputs") / "main3_sweep_fast_100.json"

ENERGY_WEIGHTS = [0.45, 0.55]
HIGH_POWER_PENALTIES = [0.35, 1.35]
VPS_PENALTY_SCALES = [0.10, 0.25]


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


def rank_key(summary):
    energy_gain = summary["energy_gain_j"]
    latency_gain = summary["latency_gain"]

    both_improved = energy_gain > 0 and latency_gain > 0
    return (
        0 if both_improved else 1,
        -energy_gain,
        -latency_gain,
        summary["tabu_energy_j"],
        summary["tabu_latency"],
    )


def run_case(tasks, metrics_random, energy_weight, high_power_penalty, vps_penalty_scale):
    res_tabu, _ = run_offline_experiment(
        tasks,
        "tabu_legacy_hybrid",
        E_ref=metrics_random["model_total_energy"],
        L_ref=metrics_random["model_avg_latency"],
        return_history=True,
        local_mode=LOCAL_MODE,
        tabu_energy_weight=energy_weight,
        tabu_high_power_penalty_weight=high_power_penalty,
        tabu_vps_penalty_scale=vps_penalty_scale,
    )
    metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

    return {
        "energy_weight": energy_weight,
        "high_power_penalty_weight": high_power_penalty,
        "vps_penalty_scale": vps_penalty_scale,
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
    }


def main():
    tasks = generate_batch(TASK_COUNT, seed=TASK_SEED)

    random_metric_runs = []
    for idx in range(N_RANDOM_BASELINES):
        print("\n============================================================")
        print(f"RUN main3 random baseline {idx + 1}/{N_RANDOM_BASELINES}")
        res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
        random_metric_runs.append(compute_metrics(res_random, tasks, NODE_RESOURCES))

    metrics_random = aggregate_metrics(random_metric_runs)

    summaries = []
    for energy_weight in ENERGY_WEIGHTS:
        for high_power_penalty in HIGH_POWER_PENALTIES:
            for vps_penalty_scale in VPS_PENALTY_SCALES:
                print("\n============================================================")
                print(
                    "RUN main3 sweep "
                    f"energy_weight={energy_weight} "
                    f"high_power_penalty={high_power_penalty} "
                    f"vps_penalty_scale={vps_penalty_scale}"
                )
                summaries.append(
                    run_case(
                        tasks,
                        metrics_random,
                        energy_weight,
                        high_power_penalty,
                        vps_penalty_scale,
                    )
                )

    ranked = sorted(summaries, key=rank_key)
    payload = {
        "task_count": TASK_COUNT,
        "task_seed": TASK_SEED,
        "local_mode": LOCAL_MODE,
        "n_random_baselines": N_RANDOM_BASELINES,
        "random_metrics": {
            "real_avg_latency": metrics_random["real_avg_latency"],
            "estimated_real_energy_j": metrics_random["estimated_real_energy_j"],
            "real_avg_execution_time": metrics_random["real_avg_execution_time"],
            "real_total_task_clock_ms": metrics_random["real_total_task_clock_ms"],
        },
        "summaries": summaries,
        "ranked": ranked,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print("\n==================== MAIN3 SWEEP TABLE ====================")
    print(
        f"{'ew':>6} {'hpp':>6} {'vps':>6} "
        f"{'lat_rnd':>10} {'lat_tabu':>10} {'lat_gain':>10} "
        f"{'eng_rnd':>12} {'eng_tabu':>12} {'eng_gain':>12}"
    )
    print("-" * 96)
    for summary in ranked:
        print(
            f"{summary['energy_weight']:>6.2f} "
            f"{summary['high_power_penalty_weight']:>6.2f} "
            f"{summary['vps_penalty_scale']:>6.2f} "
            f"{summary['random_latency']:>10.4f} "
            f"{summary['tabu_latency']:>10.4f} "
            f"{summary['latency_gain']:>10.4f} "
            f"{summary['random_energy_j']:>12.4f} "
            f"{summary['tabu_energy_j']:>12.4f} "
            f"{summary['energy_gain_j']:>12.4f}"
        )

    print(f"\nSaved sweep: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
