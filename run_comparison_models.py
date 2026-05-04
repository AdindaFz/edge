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


def execute_notebook_cells():
    nb = json.loads(NOTEBOOK_PATH.read_text())
    env = {
        "__name__": "__main__",
        "display": display,
    }

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

        # The current VPS-compatible task CSV does not have latency_ms.
        if "task_df = pd.read_csv" in src:
            src += (
                "\nif 'latency_ms' not in task_df.columns:\n"
                "    task_df['latency_ms'] = 0.0\n"
            )

        print(f"[exec] cell {idx}")
        exec(compile(src, f"Comparision.ipynb:cell_{idx}", "exec"), env)

        if "SECTION 17 - SINGLE-RUN SCREENING" in src:
            break

    return env


TARGET_OBJECTIVE = 0.75


def build_summary(results, time_to_target_fn, target=TARGET_OBJECTIVE):
    rows = []
    for global_opt in sorted(results.keys()):
        for local_opt in sorted(results[global_opt].keys()):
            history = results[global_opt][local_opt]
            runtime = float(history.get("runtime", 0.0))
            ttt = time_to_target_fn(history, runtime, threshold=target)
            final_obj = float(history["obj"][-1])
            best_obj = float(np.min(history["obj"]))
            rows.append(
                {
                    "model": f"{global_opt.upper()}+{local_opt.upper()}",
                    "final_obj": final_obj,
                    "best_obj": best_obj,
                    "runtime_s": runtime,
                    "time_to_target_0_75_s": ttt if ttt is not None else np.nan,
                }
            )
    df = pd.DataFrame(rows)
    return df.sort_values(["runtime_s", "final_obj"], ascending=[True, True]).reset_index(drop=True)


def save_convergence_plot(results):
    def _draw(x_key, xlabel, png_name, svg_name, fallback_to_iteration=False):
        fig, axes = plt.subplots(3, 3, figsize=(16, 12))
        fig.suptitle(f"Objective Function Convergence History - {xlabel}", fontsize=16, fontweight="bold")

        row_idx = 0
        col_idx = 0
        for global_opt in ["tabu", "bfo", "pso"]:
            for local_opt in ["none", "cpm", "diffusion"]:
                ax = axes[row_idx, col_idx]
                if global_opt in results and local_opt in results[global_opt]:
                    history = results[global_opt][local_opt]
                    objs = history["obj"]
                    x_vals = history.get(x_key, [])
                    if fallback_to_iteration or len(x_vals) != len(objs):
                        x_vals = list(range(1, len(objs) + 1))
                    ax.plot(x_vals, objs, linewidth=2, color="tab:blue")
                    ax.set_title(f"{global_opt.upper()} + {local_opt.upper()}", fontsize=11, fontweight="bold")
                    ax.set_xlabel(xlabel)
                    ax.set_ylabel("Objective")
                    ax.grid(True, alpha=0.3)
                    ax.text(
                        0.98,
                        0.98,
                        f"Final: {objs[-1]:.6f}",
                        transform=ax.transAxes,
                        ha="right",
                        va="top",
                        fontsize=9,
                        bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
                    )
                else:
                    ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                col_idx += 1
                if col_idx == 3:
                    col_idx = 0
                    row_idx += 1

        plt.tight_layout()
        png_path = OUTPUT_DIR / png_name
        fig.savefig(png_path, dpi=160, bbox_inches="tight")
        fig.savefig(OUTPUT_DIR / svg_name, bbox_inches="tight")
        plt.close(fig)
        return png_path

    time_plot = _draw("time", "Time (s)", "objective_convergence.png", "objective_convergence.svg")
    _draw("iteration", "Iteration", "objective_convergence_iteration.png", "objective_convergence_iteration.svg", fallback_to_iteration=True)
    return time_plot


def save_html_report(summary, plot_path):
    html_path = OUTPUT_DIR / "comparison_report.html"
    fastest = summary.sort_values(["runtime_s", "final_obj"], ascending=[True, True])
    fastest_target = summary.dropna(subset=["time_to_target_0_75_s"]).sort_values(
        ["time_to_target_0_75_s", "final_obj"], ascending=[True, True]
    )
    best_final = summary.sort_values(["final_obj", "runtime_s"], ascending=[True, True])

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Comparison Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1, h2 {{ margin-bottom: 8px; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 28px; }}
    th, td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .note {{ color: #555; margin-bottom: 18px; }}
  </style>
</head>
<body>
  <h1>Comparison Notebook Report</h1>
  <p class="note">Generated from Comparision.ipynb using local VPS datasets.</p>

  <h2>Objective Convergence</h2>
  <img src="{plot_path.name}" alt="Objective convergence plot">

  <h2>Fastest Runtime</h2>
  {fastest.to_html(index=False)}

  <h2>Fastest to Objective 0.75</h2>
  {fastest_target.to_html(index=False)}

  <h2>Best Final Objective</h2>
  {best_final.to_html(index=False)}
</body>
</html>
"""
    html_path.write_text(html)
    return html_path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = execute_notebook_cells()
    results = env["RESULTS"]
    summary = build_summary(results, env["time_to_target"])

    summary_path = OUTPUT_DIR / "comparison_summary.csv"
    summary.to_csv(summary_path, index=False)
    plot_path = save_convergence_plot(results)
    html_path = save_html_report(summary, plot_path)

    fastest = summary.sort_values(["runtime_s", "final_obj"], ascending=[True, True])
    fastest_target = summary.dropna(subset=["time_to_target_0_75_s"]).sort_values(
        ["time_to_target_0_75_s", "final_obj"], ascending=[True, True]
    )
    best_final = summary.sort_values(["final_obj", "runtime_s"], ascending=[True, True])

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)

    print("\n=== SUMMARY: FASTEST RUNTIME ===")
    print(fastest.to_string(index=False))

    print("\n=== SUMMARY: FASTEST TO OBJECTIVE 0.75 ===")
    if fastest_target.empty:
        print("No model reached objective <= 0.75")
    else:
        print(fastest_target.to_string(index=False))

    print("\n=== SUMMARY: BEST FINAL OBJECTIVE ===")
    print(best_final.to_string(index=False))

    print(f"\nSaved plot: {plot_path}")
    print(f"Saved html report: {html_path}")
    print(f"Saved summary CSV: {summary_path}")


if __name__ == "__main__":
    main()
