import json
import os
import sys

import matplotlib.pyplot as plt


def plot_random_vs_tabu_metrics(metrics_random, metrics_tabu, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    panels = [
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
            "Model Latency",
            "Model unit",
            [
                metrics_random["model_avg_latency"],
                metrics_tabu["model_avg_latency"],
            ],
        ),
        (
            "Comparison Model Energy",
            "Model unit",
            [
                metrics_random["model_total_energy"],
                metrics_tabu["model_total_energy"],
            ],
        ),
        (
            "Calibrated Model Energy",
            "Model unit",
            [
                metrics_random["model_calibrated_real_energy"],
                metrics_tabu["model_calibrated_real_energy"],
            ],
        ),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    axes = axes.flatten()
    labels = ["Random", "Tabu + Diffusion"]
    colors = ["#6b7280", "#0ea5a3"]

    for ax, (title, ylabel, values) in zip(axes, panels):
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

    summary_ax = axes[-1]
    summary_ax.axis("off")
    energy_delta = metrics_tabu["estimated_real_energy_j"] - metrics_random["estimated_real_energy_j"]
    latency_delta = metrics_tabu["real_avg_latency"] - metrics_random["real_avg_latency"]
    energy_pct = energy_delta / max(metrics_random["estimated_real_energy_j"], 1e-9) * 100.0
    latency_pct = latency_delta / max(metrics_random["real_avg_latency"], 1e-9) * 100.0
    calibrated_delta = (
        metrics_tabu["model_calibrated_real_energy"]
        - metrics_random["model_calibrated_real_energy"]
    )
    calibrated_pct = (
        calibrated_delta
        / max(metrics_random["model_calibrated_real_energy"], 1e-9)
        * 100.0
    )
    summary_ax.text(
        0.02,
        0.94,
        "Tabu - Random\n\n"
        f"Real energy: {energy_delta:+.2f} J ({energy_pct:+.2f}%)\n"
        f"Real latency: {latency_delta:+.4f} s ({latency_pct:+.2f}%)\n"
        f"Calibrated model energy: {calibrated_delta:+.2f} ({calibrated_pct:+.2f}%)",
        va="top",
        fontsize=11,
        family="monospace",
    )

    fig.suptitle("Random vs Tabu + Diffusion", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python plot_run_comparison.py <run.json> [<run.json> ...]")

    for json_path in sys.argv[1:]:
        with open(json_path) as f:
            payload = json.load(f)

        metrics = payload["metrics"]
        run_id = payload["run_id"]
        n_tasks = payload["config"]["n_tasks"]
        out_path = os.path.join(
            os.path.dirname(json_path),
            f"random_vs_tabu_metrics_{n_tasks}_{run_id}.png",
        )
        plot_random_vs_tabu_metrics(
            metrics["random"],
            metrics["tabu_diffusion"],
            out_path,
        )
        print(out_path)


if __name__ == "__main__":
    main()
