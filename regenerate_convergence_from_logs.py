import math
import re
from pathlib import Path

import matplotlib.pyplot as plt


OUTPUT_DIR = Path("/home/adinda-central/edge-computing-system/outputs")
RUN_LOG_DIR = OUTPUT_DIR / "run_logs"
TASK_COUNTS = [100, 200, 300, 400, 500]

TABU_RE = re.compile(r"\[TABU\] Iter (\d+) \| Cost=([0-9.]+)")
RANDOM_LAT_RE = re.compile(r"Real avg latency\s+([0-9.]+)")
RANDOM_ENG_RE = re.compile(r"Model Energy \(J\)\s+([0-9.]+)")
COMP_RE = re.compile(r"=== COMPARISON TABLE \(n_tasks=(\d+)\) ===")


def latest_log(task_count: int) -> Path | None:
    matches = sorted(RUN_LOG_DIR.glob(f"main_{task_count}_*.log"))
    return matches[-1] if matches else None


def parse_log(path: Path):
    lines = path.read_text().splitlines()

    random_model_energy = None
    random_model_latency = None
    in_random_metrics = False
    in_model_block = False
    tabu_points = []

    for line in lines:
        if line.strip() == "=== RANDOM BASELINE AVERAGE ===":
            in_random_metrics = True
            in_model_block = False
            continue

        if in_random_metrics and line.strip() == "[MODEL]":
            in_model_block = True
            continue

        if in_random_metrics and line.startswith("=== TABU + DIFFUSION ==="):
            in_random_metrics = False
            in_model_block = False

        if in_random_metrics and in_model_block:
            lat_match = RANDOM_LAT_RE.search(line)
            if lat_match:
                random_model_latency = float(lat_match.group(1))
            eng_match = RANDOM_ENG_RE.search(line)
            if eng_match:
                random_model_energy = float(eng_match.group(1))

        m = TABU_RE.search(line)
        if m:
            tabu_points.append((int(m.group(1)), float(m.group(2))))

    if not tabu_points:
        raise ValueError(f"No TABU convergence points found in {path}")

    reference_cost = None
    if random_model_energy is not None and random_model_latency is not None:
        # In current reporting both refs come from average random model metrics,
        # so the normalized random baseline is 1.0 by construction.
        # We approximate the plotted normalization using the first tabu point's
        # corresponding random-reference scale extracted from the run itself.
        # Since the log does not store reference_cost directly, we reconstruct
        # the visual curve by normalizing all points to the first point's scale
        # only if needed later. For this script we keep raw points and scale
        # them to their own range for readability.
        reference_cost = None

    return tabu_points, reference_cost


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


def plot_from_points(task_count: int, points, out_path: Path):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]

    lower, upper = compute_limits(ys)

    plt.figure(figsize=(7, 4))
    plt.plot(xs, ys, linewidth=2.2, color="tab:blue", alpha=0.9)
    plt.xlabel("Iteration")
    plt.ylabel("Objective Value")
    plt.title(f"Tabu Convergence - {task_count} Tasks", fontweight="bold")
    plt.ylim(lower, upper)
    plt.grid(True, alpha=0.3)
    plt.text(
        0.98,
        0.98,
        f"Final: {ys[-1]:.4f}",
        transform=plt.gca().transAxes,
        fontsize=9,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_combined(all_points, out_path: Path):
    if not all_points:
        return

    n = len(all_points)
    ncols = 2
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.8 * nrows))
    axes = axes.flatten()

    for ax, (task_count, points) in zip(axes, all_points):
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        lower, upper = compute_limits(ys)

        ax.plot(xs, ys, linewidth=2.0, color="tab:blue", alpha=0.9)
        ax.set_title(f"{task_count} Tasks", fontsize=11, fontweight="bold")
        ax.set_xlabel("Iteration", fontsize=9)
        ax.set_ylabel("Objective Value", fontsize=9)
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

    for ax in axes[len(all_points):]:
        ax.axis("off")

    fig.suptitle("Objective Function Convergence History", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    collected = []
    for task_count in TASK_COUNTS:
        log_path = latest_log(task_count)
        if log_path is None:
            print(f"[SKIP] No log found for {task_count} tasks")
            continue
        points, _ = parse_log(log_path)
        out_path = OUTPUT_DIR / f"tabu_convergence_{task_count}_zoomed.png"
        plot_from_points(task_count, points, out_path)
        collected.append((task_count, points))
        print(
            f"[DONE] {task_count} tasks | "
            f"{points[0][1]:.4f} -> {points[-1][1]:.4f} | "
            f"saved {out_path}"
        )

    if collected:
        combined_path = OUTPUT_DIR / "tabu_convergence_combined_zoomed.png"
        plot_combined(collected, combined_path)
        print(f"[DONE] Combined convergence figure saved {combined_path}")


if __name__ == "__main__":
    main()
