#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.patches import Patch


METRICS = [
    ("Real average latency (s)", "real_avg_latency", 4, "real_avg_latency"),
    ("Real total latency (s)", "real_total_latency", 4, "real_total_latency"),
    ("Estimated real energy (J)", "estimated_real_energy_j", 4, "estimated_real_energy"),
    ("Task-clock total (ms)", "real_total_task_clock_ms", 0, "task_clock_total"),
    ("Observed average memory bytes (byte)", "real_avg_memory_bytes", 2, "observed_memory_avg"),
]

METHOD_STYLES = {
    "Random Baseline Average": {
        "color": "#d9d9d9",
        "alpha": 0.95,
        "hatch": "",
        "edgecolor": "#2f2f2f",
    },
    "Tabu + Diffusion": {
        "color": "#1f77b4",
        "alpha": 0.78,
        "hatch": "///",
        "edgecolor": "#2f2f2f",
    },
}


def fmt_id(value, decimals=4):
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_change(random_value, tabu_value):
    random_value = float(random_value)
    tabu_value = float(tabu_value)
    if abs(random_value) < 1e-12:
        return "-"
    pct = (tabu_value - random_value) / abs(random_value) * 100.0
    if abs(pct) < 0.005:
        return "Unchanged"
    label = "Decreased" if pct < 0 else "Increased"
    return f"{label} {fmt_id(abs(pct), 2)}%"


def load_metrics(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    metrics = data["metrics"]
    return data, metrics["random"], metrics["tabu_diffusion"]


def draw_table(data, random_metrics, tabu_metrics, output_path):
    rows = []
    for label, key, decimals, _slug in METRICS:
        rows.append([
            label,
            fmt_id(random_metrics[key], decimals),
            fmt_id(tabu_metrics[key], decimals),
            fmt_change(random_metrics[key], tabu_metrics[key]),
        ])

    fig, ax = plt.subplots(figsize=(13, 6.8), dpi=180)
    fig.patch.set_facecolor("#050505")
    ax.set_facecolor("#050505")
    ax.axis("off")

    title = f"Metric Comparison: Random Baseline Average vs Tabu + Diffusion\nRun {data.get('run_id', '')} | n={data.get('config', {}).get('n_tasks', '')} tasks"
    ax.text(
        0.5,
        0.965,
        title,
        ha="center",
        va="top",
        color="white",
        fontsize=18,
        fontweight="bold",
        transform=ax.transAxes,
    )

    table = ax.table(
        cellText=rows,
        colLabels=["Metric", "Random Baseline\nAverage", "Tabu + Diffusion", "Change"],
        colWidths=[0.40, 0.22, 0.22, 0.16],
        cellLoc="right",
        colLoc="center",
        bbox=[0.035, 0.08, 0.93, 0.78],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 1.85)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#2a2a2a")
        cell.set_linewidth(0.6)
        if row == 0:
            cell.set_facecolor("#101010")
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
            cell.get_text().set_fontsize(12)
            if col == 0:
                cell.get_text().set_ha("left")
        else:
            cell.set_facecolor("#050505")
            cell.get_text().set_color("white")
            if col == 0:
                cell.get_text().set_ha("left")
                cell.get_text().set_fontstyle("italic")
            if col == 3:
                text = cell.get_text().get_text()
                if text.startswith("Decreased"):
                    cell.get_text().set_color("#55d98b")
                elif text.startswith("Increased"):
                    cell.get_text().set_color("#ffbf69")
                else:
                    cell.get_text().set_color("#d9d9d9")

    ax.add_patch(
        plt.Rectangle(
            (0.025, 0.055),
            0.95,
            0.84,
            fill=False,
            edgecolor="white",
            linewidth=1.1,
            transform=ax.transAxes,
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def draw_normalized_bars(data, random_metrics, tabu_metrics, output_path):
    labels = [label for label, _, _, _ in METRICS]
    random_values = [float(random_metrics[key]) for _, key, _, _ in METRICS]
    tabu_values = [float(tabu_metrics[key]) for _, key, _, _ in METRICS]
    tabu_pct = [(t / r * 100.0) if abs(r) > 1e-12 else 0.0 for r, t in zip(random_values, tabu_values)]

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=180)
    fig.patch.set_facecolor("#0b0b0b")
    ax.set_facecolor("#0b0b0b")

    y = range(len(labels))
    ax.barh(y, [100] * len(labels), color="#3b82f6", alpha=0.42, height=0.34, label="Random = 100%")
    ax.barh([i + 0.36 for i in y], tabu_pct, color="#22c55e", alpha=0.85, height=0.34, label="Tabu + Diffusion")

    ax.set_yticks([i + 0.18 for i in y])
    ax.set_yticklabels(labels, color="white", fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Percentage of Random Baseline Average (%)", color="white")
    ax.set_title(
        f"Metrics Normalized to Random Baseline Average - {data.get('run_id', '')}",
        color="white",
        fontsize=14,
        fontweight="bold",
        pad=14,
    )
    ax.tick_params(axis="x", colors="white")
    ax.grid(axis="x", color="#333333", linewidth=0.6, alpha=0.8)
    for spine in ax.spines.values():
        spine.set_color("#444444")

    for i, pct in enumerate(tabu_pct):
        ax.text(
            pct + max(tabu_pct + [100]) * 0.015,
            i + 0.36,
            f"{fmt_id(pct, 2)}%",
            va="center",
            color="white",
            fontsize=9,
            path_effects=[patheffects.withStroke(linewidth=2, foreground="#0b0b0b")],
        )

    ax.legend(facecolor="#151515", edgecolor="#555555", labelcolor="white", loc="lower right")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def draw_metric_grid_bars(data, random_metrics, tabu_metrics, output_path):
    fig, axes = plt.subplots(2, 3, figsize=(15.5, 8.6), dpi=180)
    axes = axes.ravel()
    fig.suptitle(
        f"Metric Comparison: Random Baseline Average vs Tabu + Diffusion - {data.get('config', {}).get('n_tasks', '')} Tasks",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )

    model_labels = ["Random Baseline\nAverage", "Tabu +\nDiffusion"]
    style_keys = ["Random Baseline Average", "Tabu + Diffusion"]

    for ax, metric in zip(axes, METRICS):
        label, key, decimals, _slug = metric
        values = [float(random_metrics[key]), float(tabu_metrics[key])]
        styles = [METHOD_STYLES[name] for name in style_keys]
        x = range(len(values))

        bars = ax.bar(
            x,
            values,
            width=0.36,
            color=[style["color"] for style in styles],
            edgecolor=[style["edgecolor"] for style in styles],
            linewidth=0.8,
        )
        for bar, style in zip(bars, styles):
            bar.set_hatch(style["hatch"])
            bar.set_alpha(style["alpha"])

        clean_label = label.replace("\n", " ")
        ax.set_title(clean_label, fontsize=10.5, fontweight="bold", pad=8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(model_labels, fontsize=8.5)
        ax.set_ylabel(clean_label, fontsize=8.5)
        ax.grid(axis="y", alpha=0.28)
        ax.set_axisbelow(True)
        ax.margins(x=0.34)

        max_value = max(values) if values else 1.0
        ax.set_ylim(0, max_value * 1.22 if max_value > 0 else 1.0)
        ax.tick_params(axis="y", labelsize=8)

        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                fmt_id(value, decimals),
                ha="center",
                va="bottom",
                fontsize=7.6,
                color="#3f3f3f",
                fontweight="bold",
            )

        change_text = fmt_change(values[0], values[1])
        ax.text(
            0.98,
            0.95,
            change_text,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=7.8,
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "#bdbdbd", "alpha": 0.92},
        )

    unused_ax = axes[len(METRICS)]
    unused_ax.axis("off")
    handles = [
        Patch(
            facecolor=METHOD_STYLES["Random Baseline Average"]["color"],
            edgecolor=METHOD_STYLES["Random Baseline Average"]["edgecolor"],
            alpha=METHOD_STYLES["Random Baseline Average"]["alpha"],
            label="Random Baseline Average",
        ),
        Patch(
            facecolor=METHOD_STYLES["Tabu + Diffusion"]["color"],
            edgecolor=METHOD_STYLES["Tabu + Diffusion"]["edgecolor"],
            hatch=METHOD_STYLES["Tabu + Diffusion"]["hatch"],
            alpha=METHOD_STYLES["Tabu + Diffusion"]["alpha"],
            label="Tabu + Diffusion",
        ),
    ]
    unused_ax.legend(handles=handles, frameon=False, loc="center", fontsize=11)

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def draw_individual_metric_bar(data, random_metrics, tabu_metrics, metric, output_path):
    label, key, decimals, _slug = metric
    model_labels = ["Random Baseline Average", "Tabu + Diffusion"]
    values = [float(random_metrics[key]), float(tabu_metrics[key])]
    styles = [METHOD_STYLES[name] for name in model_labels]

    fig, ax = plt.subplots(figsize=(10.5, 6.0), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.bar(
        model_labels,
        values,
        width=0.38,
        color=[style["color"] for style in styles],
        alpha=1.0,
        edgecolor=[style["edgecolor"] for style in styles],
        linewidth=0.9,
    )
    for bar, style in zip(bars, styles):
        bar.set_hatch(style["hatch"])
        bar.set_alpha(style["alpha"])

    clean_label = label.replace("\n", " ")
    ax.set_title(
        f"{clean_label} Comparison",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Method")
    ax.set_ylabel(clean_label)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.margins(x=0.18)

    max_value = max(values) if values else 1.0
    ax.set_ylim(0, max_value * 1.22 if max_value > 0 else 1.0)
    plt.xticks(rotation=18, ha="right")

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            fmt_id(value, decimals),
            ha="center",
            va="bottom",
            fontsize=9,
            color="#3f3f3f",
            fontweight="bold",
        )

    change_text = fmt_change(values[0], values[1])
    change_color = "#18864b" if change_text.startswith("Decreased") else "#b26b00"
    if change_text == "Unchanged":
        change_color = "#555555"
    ax.text(
        0.98,
        0.95,
        f"Change: {change_text}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "#d0d0d0", "alpha": 0.9},
        color=change_color,
        fontweight="bold",
    )

    handles = [
        Patch(
            facecolor=METHOD_STYLES["Random Baseline Average"]["color"],
            edgecolor=METHOD_STYLES["Random Baseline Average"]["edgecolor"],
            alpha=METHOD_STYLES["Random Baseline Average"]["alpha"],
            label="Random Baseline Average",
        ),
        Patch(
            facecolor=METHOD_STYLES["Tabu + Diffusion"]["color"],
            edgecolor=METHOD_STYLES["Tabu + Diffusion"]["edgecolor"],
            hatch=METHOD_STYLES["Tabu + Diffusion"]["hatch"],
            alpha=METHOD_STYLES["Tabu + Diffusion"]["alpha"],
            label="Tabu + Diffusion",
        ),
    ]
    ax.legend(handles=handles, ncol=2, frameon=False, loc="upper left")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def draw_all_individual_metric_bars(data, random_metrics, tabu_metrics, output_dir):
    output_paths = []
    run_id = data.get("run_id", "run")
    for metric in METRICS:
        _label, _key, _decimals, slug = metric
        output_path = output_dir / f"metric_bar_{slug}_{run_id}.png"
        draw_individual_metric_bar(data, random_metrics, tabu_metrics, metric, output_path)
        output_paths.append(output_path)
    return output_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_json", help="Path to run_*.json")
    parser.add_argument("--out-dir", default=None, help="Output directory")
    args = parser.parse_args()

    run_path = Path(args.run_json)
    data, random_metrics, tabu_metrics = load_metrics(run_path)
    out_dir = Path(args.out_dir) if args.out_dir else run_path.parent
    run_id = data.get("run_id", run_path.stem.replace("run_300_", ""))

    table_path = out_dir / f"metric_comparison_table_{run_id}.png"
    bars_path = out_dir / f"metric_comparison_normalized_{run_id}.png"
    grid_path = out_dir / f"metric_comparison_grid_{run_id}.png"

    draw_table(data, random_metrics, tabu_metrics, table_path)
    draw_normalized_bars(data, random_metrics, tabu_metrics, bars_path)
    draw_metric_grid_bars(data, random_metrics, tabu_metrics, grid_path)

    print(table_path)
    print(bars_path)
    print(grid_path)


if __name__ == "__main__":
    main()
