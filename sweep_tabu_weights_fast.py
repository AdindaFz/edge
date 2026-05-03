import json
from pathlib import Path

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


N_TASKS = 200
TASK_SEED = 42
LOCAL_MODE = "hybrid"
OUTPUT_PATH = Path("/home/adinda-central/edge-computing-system/outputs") / "tabu_sweep_fast_200.json"

# Keep the grid intentionally small so the sweep stays practical on real nodes.
ENERGY_WEIGHTS = [0.35, 0.45]
HIGH_POWER_PENALTIES = [0.18, 0.35]


def score_summary(summary):
    latency_delta = summary["random_latency"] - summary["tabu_latency"]
    energy_delta = summary["random_energy"] - summary["tabu_energy"]

    both_improved = latency_delta > 0 and energy_delta > 0
    return (
        1 if both_improved else 0,
        latency_delta,
        energy_delta,
        -summary["tabu_latency"],
    )


def run_setting(tasks, energy_weight, high_power_penalty_weight):
    print("\n============================================================")
    print(
        f"SETTING energy_weight={energy_weight:.2f} "
        f"high_power_penalty={high_power_penalty_weight:.2f}"
    )

    res_random, _ = run_offline_experiment(
        tasks,
        "random",
        return_history=True,
    )
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

    res_tabu, _ = run_offline_experiment(
        tasks,
        "tabu",
        E_ref=metrics_random["model_total_energy"],
        L_ref=metrics_random["model_avg_latency"],
        return_history=True,
        local_mode=LOCAL_MODE,
        tabu_energy_weight=energy_weight,
        tabu_high_power_penalty_weight=high_power_penalty_weight,
    )
    metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

    summary = {
        "energy_weight": energy_weight,
        "high_power_penalty_weight": high_power_penalty_weight,
        "random_latency": metrics_random["real_avg_latency"],
        "random_energy": metrics_random["estimated_real_energy_j"],
        "tabu_latency": metrics_tabu["real_avg_latency"],
        "tabu_energy": metrics_tabu["estimated_real_energy_j"],
        "latency_gain": metrics_random["real_avg_latency"] - metrics_tabu["real_avg_latency"],
        "energy_gain": metrics_random["estimated_real_energy_j"] - metrics_tabu["estimated_real_energy_j"],
        "random_metrics": metrics_random,
        "tabu_metrics": metrics_tabu,
    }

    print(
        f"Random latency={summary['random_latency']:.4f} "
        f"energy={summary['random_energy']:.4f} J"
    )
    print(
        f"Tabu   latency={summary['tabu_latency']:.4f} "
        f"energy={summary['tabu_energy']:.4f} J"
    )
    print(
        f"Delta  latency={summary['latency_gain']:.4f} "
        f"energy={summary['energy_gain']:.4f} J"
    )

    return summary


def main():
    tasks = generate_batch(N_TASKS, seed=TASK_SEED)
    summaries = []

    for energy_weight in ENERGY_WEIGHTS:
        for high_power_penalty_weight in HIGH_POWER_PENALTIES:
            summary = run_setting(tasks, energy_weight, high_power_penalty_weight)
            summaries.append(summary)

    ranked = sorted(summaries, key=score_summary, reverse=True)

    payload = {
        "n_tasks": N_TASKS,
        "task_seed": TASK_SEED,
        "local_mode": LOCAL_MODE,
        "ranked_summaries": ranked,
        "best_summary": ranked[0] if ranked else None,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print("\n==================== RANKING ====================")
    for idx, summary in enumerate(ranked, start=1):
        print(
            f"{idx}. energy_weight={summary['energy_weight']:.2f} "
            f"high_power_penalty={summary['high_power_penalty_weight']:.2f} "
            f"latency_gain={summary['latency_gain']:.4f} "
            f"energy_gain={summary['energy_gain']:.4f} J"
        )

    print(f"\nSaved sweep results: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
