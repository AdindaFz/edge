from statistics import mean

from central.offline_runner import compute_metrics, run_offline_experiment
from central.node_resources import NODE_RESOURCES
from central.task_generator import generate_batch


N_TASKS = 25
N_REPEATS = 3
TASK_SEEDS = [42, 43, 44]
ENERGY_WEIGHTS = [0.55, 0.62, 0.68, 0.75]
HIGH_POWER_PENALTIES = [0.0, 0.08, 0.16]


def avg_metric(rows, key):
    return mean(row[key] for row in rows)


def run_setting(energy_weight, high_power_penalty_weight):
    rows = []

    for seed in TASK_SEEDS[:N_REPEATS]:
        tasks = generate_batch(N_TASKS, seed=seed)

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
            local_mode="none",
            tabu_energy_weight=energy_weight,
            tabu_high_power_penalty_weight=high_power_penalty_weight,
        )
        metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

        rows.append(
            {
                "seed": seed,
                "random_latency": metrics_random["real_avg_latency"],
                "random_energy": metrics_random["estimated_real_energy_j"],
                "tabu_latency": metrics_tabu["real_avg_latency"],
                "tabu_energy": metrics_tabu["estimated_real_energy_j"],
                "latency_gain": metrics_random["real_avg_latency"] - metrics_tabu["real_avg_latency"],
                "energy_gain": metrics_random["estimated_real_energy_j"] - metrics_tabu["estimated_real_energy_j"],
            }
        )

    return {
        "energy_weight": energy_weight,
        "high_power_penalty_weight": high_power_penalty_weight,
        "avg_random_latency": avg_metric(rows, "random_latency"),
        "avg_random_energy": avg_metric(rows, "random_energy"),
        "avg_tabu_latency": avg_metric(rows, "tabu_latency"),
        "avg_tabu_energy": avg_metric(rows, "tabu_energy"),
        "avg_latency_gain": avg_metric(rows, "latency_gain"),
        "avg_energy_gain": avg_metric(rows, "energy_gain"),
        "rows": rows,
    }


def print_summary(summary):
    print(
        "SETTING "
        f"energy_weight={summary['energy_weight']:.2f} "
        f"high_power_penalty={summary['high_power_penalty_weight']:.2f}"
    )
    print(
        "  AVG random     "
        f"latency={summary['avg_random_latency']:.4f} "
        f"energy={summary['avg_random_energy']:.4f} J"
    )
    print(
        "  AVG tabu       "
        f"latency={summary['avg_tabu_latency']:.4f} "
        f"energy={summary['avg_tabu_energy']:.4f} J"
    )
    print(
        "  DELTA random-tabu "
        f"latency={summary['avg_latency_gain']:.4f} "
        f"energy={summary['avg_energy_gain']:.4f} J"
    )


def main():
    summaries = []

    for energy_weight in ENERGY_WEIGHTS:
        for high_power_penalty_weight in HIGH_POWER_PENALTIES:
            print("\n============================================================")
            summary = run_setting(energy_weight, high_power_penalty_weight)
            print_summary(summary)
            summaries.append(summary)

    print("\n==================== RANKING ====================")
    ranked = sorted(
        summaries,
        key=lambda s: (-s["avg_latency_gain"], -s["avg_energy_gain"]),
    )

    for idx, summary in enumerate(ranked, start=1):
        print(
            f"{idx}. energy_weight={summary['energy_weight']:.2f} "
            f"high_power_penalty={summary['high_power_penalty_weight']:.2f} "
            f"latency_gain={summary['avg_latency_gain']:.4f} "
            f"energy_gain={summary['avg_energy_gain']:.4f} J"
        )


if __name__ == "__main__":
    main()
