import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path("/home/adinda-central/edge-computing-system")
NOTEBOOK_PATH = REPO_ROOT / "Comparision.ipynb"
MACHINE_CSV = REPO_ROOT / "part-00000-of-00001.csv"
TASK_CSV = REPO_ROOT / "spreadsheet_export.csv"
OUTPUT_DIR = REPO_ROOT / "outputs" / "comparison_notebook"


def display(obj):
    if hasattr(obj, "to_string"):
        print(obj.to_string())
    else:
        print(obj)


def patch_source(src: str) -> str:
    src = src.replace(
        r'machine_path = r"C:\Users\Matebook\Documents\Penelitian\Dataset\part-00000-of-00001.csv"',
        f'machine_path = r"{MACHINE_CSV}"',
    )
    src = src.replace(
        r'task_path = r"C:\Users\Matebook\Documents\Penelitian\Dataset\cpm_pso_input_part10_19_timeseries.csv"',
        f'task_path = r"{TASK_CSV}"',
    )
    return src


def execute_code_cells_until(env, marker):
    nb = json.loads(NOTEBOOK_PATH.read_text())
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") != "code":
            continue
        src = patch_source("".join(cell.get("source", [])))
        if src.startswith("%%writefile"):
            lines = src.splitlines()
            target = REPO_ROOT / lines[0].split(maxsplit=1)[1]
            target.write_text("\n".join(lines[1:]) + "\n")
            print(f"[writefile] {target}")
            continue
        if "task_df = pd.read_csv" in src:
            src += (
                "\nif 'latency_ms' not in task_df.columns:\n"
                "    task_df['latency_ms'] = 0.0\n"
            )
        print(f"[exec] cell {idx}")
        exec(compile(src, f"Comparision.ipynb:cell_{idx}", "exec"), env)
        if marker in src:
            break


def execute_code_cells_matching(env, predicates):
    nb = json.loads(NOTEBOOK_PATH.read_text())
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") != "code":
            continue
        src = patch_source("".join(cell.get("source", [])))
        if not any(predicate(src) for predicate in predicates):
            continue
        print(f"[exec] cell {idx}")
        exec(compile(src, f"Comparision.ipynb:cell_{idx}", "exec"), env)


def build_environment():
    env = {
        "__name__": "__main__",
        "display": display,
    }
    execute_code_cells_until(env, "SECTION 17 - SINGLE-RUN SCREENING")
    return env


def run_multirun(env, runs):
    env["runs"] = runs
    execute_code_cells_matching(
        env,
        [
            lambda src: "SECTION 18 - TOP-3 CDF SETUP" in src,
        ],
    )
    env["runs"] = runs
    env["CDF_RUNS"] = runs
    env["scores"], env["energy_scores"], env["latency_scores"] = env["run_cdf_for_models"](
        env["CDF_MODELS"],
        runs,
    )
    return env["scores"], env["energy_scores"], env["latency_scores"]


def save_summary(scores, energy_scores, latency_scores):
    rows = []
    for name in sorted(scores.keys()):
        obj = np.array(scores[name], dtype=float)
        energy = np.array(energy_scores[name], dtype=float)
        latency = np.array(latency_scores[name], dtype=float)
        rows.append(
            {
                "model": name,
                "runs": len(obj),
                "objective_mean": float(np.mean(obj)),
                "objective_std": float(np.std(obj)),
                "objective_min": float(np.min(obj)),
                "objective_max": float(np.max(obj)),
                "energy_mean": float(np.mean(energy)),
                "latency_mean": float(np.mean(latency)),
            }
        )
    df = pd.DataFrame(rows).sort_values(["objective_mean", "objective_std"], ascending=[True, True])
    out = OUTPUT_DIR / "cdf_summary.csv"
    df.to_csv(out, index=False)
    return df, out


def compute_cdf(data):
    sorted_data = np.sort(np.array(data, dtype=float))
    cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
    return sorted_data, cdf


def save_cdf_plots(scores):
    all_plot = OUTPUT_DIR / "cdf_all_models.png"
    fig = plt.figure(figsize=(11, 7))
    sorted_names = sorted(scores.keys(), key=lambda n: np.mean(scores[n]))
    for name in sorted_names:
        x_cdf, y_cdf = compute_cdf(scores[name])
        plt.plot(x_cdf, y_cdf, linewidth=2, label=f"{name} (mean={np.mean(scores[name]):.6f})")
    plt.title("CDF of Objective Values")
    plt.xlabel("Objective Value")
    plt.ylabel("Cumulative Probability")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    fig.savefig(all_plot, dpi=160, bbox_inches="tight")
    plt.close(fig)

    for family in ["TABU", "BFO", "PSO"]:
        family_names = [name for name in sorted_names if family in name.upper()]
        if not family_names:
            continue
        fig = plt.figure(figsize=(10, 6))
        for name in family_names:
            x_cdf, y_cdf = compute_cdf(scores[name])
            plt.plot(x_cdf, y_cdf, linewidth=2.2, label=f"{name} (mean={np.mean(scores[name]):.6f})")
        plt.title(f"CDF - {family}")
        plt.xlabel("Objective Value")
        plt.ylabel("Cumulative Probability")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
        plt.tight_layout()
        fig.savefig(OUTPUT_DIR / f"cdf_{family.lower()}.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

    return all_plot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = build_environment()
    scores, energy_scores, latency_scores = run_multirun(env, args.runs)
    summary_df, summary_path = save_summary(scores, energy_scores, latency_scores)
    all_plot = save_cdf_plots(scores)

    print("\n=== CDF SUMMARY ===")
    print(summary_df.to_string(index=False))
    print(f"\nSaved summary CSV: {summary_path}")
    print(f"Saved CDF plot: {all_plot}")
    print(f"Saved outputs directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
