import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from run_comparison_cdf import (
    NOTEBOOK_PATH,
    OUTPUT_DIR,
    patch_source,
    save_cdf_plots,
    display,
)
from central.optimizer_runner import hybrid_tabu_diff
from central.simulation_model import energy_of_configuration, latency_of_configuration


DEFAULT_CDF_MODELS = ["TABU+DIFFUSION", "TABU+CPM", "TABU+NONE"]
FROZEN_TASK_PATH = OUTPUT_DIR / "frozen_task_sample.csv"
FROZEN_MACHINE_PATH = OUTPUT_DIR / "frozen_machine_nodes.csv"
FROZEN_META_PATH = OUTPUT_DIR / "frozen_instance_meta.json"


def array_fingerprint(*arrays):
    digest = hashlib.sha256()
    for arr in arrays:
        np_arr = np.asarray(arr)
        digest.update(str(np_arr.shape).encode("utf-8"))
        digest.update(np.ascontiguousarray(np_arr).tobytes())
    return digest.hexdigest()


def execute_notebook_before_screening(env):
    nb = json.loads(NOTEBOOK_PATH.read_text())
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") != "code":
            continue

        src = patch_source("".join(cell.get("source", [])))
        if "SECTION 17 - SINGLE-RUN SCREENING" in src:
            print(f"[skip] stopping before screening cell {idx}")
            break

        if src.startswith("%%writefile"):
            lines = src.splitlines()
            target = Path(lines[0].split(maxsplit=1)[1])
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


def bootstrap_cdf_globals(env, cdf_models):
    from system_model import SystemModel

    adjacency = {}
    for i in range(env["N_NODES"]):
        x, y = i // env["Ny"], i % env["Ny"]
        neighbors = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx_new, ny_new = x + dx, y + dy
            if 0 <= nx_new < env["Nx"] and 0 <= ny_new < env["Ny"]:
                neighbors.append(nx_new * env["Ny"] + ny_new)
        adjacency[i] = neighbors

    system_model_instance = SystemModel()
    system_model_instance.cpu_demands = env["cpu_demands"]
    system_model_instance.mem_demands = env["mem_demands"]
    system_model_instance.cpu_caps = env["cpu_caps"]
    system_model_instance.mem_caps = env["mem_caps"]
    system_model_instance.latency_ms = env["latency_ms"]
    system_model_instance.idle_powers = env["idle_powers"]
    system_model_instance.max_powers = env["max_powers"]
    system_model_instance.alpha_cpu = env["alpha_cpu"]
    system_model_instance.beta_mem = env["beta_mem"]

    experiment_combinations = [
        ("tabu", "none"),
        ("tabu", "diffusion"),
        ("tabu", "cpm"),
        ("bfo", "none"),
        ("bfo", "diffusion"),
        ("bfo", "cpm"),
        ("pso", "none"),
        ("pso", "diffusion"),
        ("pso", "cpm"),
    ]

    model_lookup = {
        f"{global_opt.upper()}+{local_opt.upper()}": (global_opt, local_opt)
        for global_opt, local_opt in experiment_combinations
    }

    def run_global_optimizer(optimizer_name, system_model_instance, local_optimizer_name):
        local_opt_instance = env["build_local_optimizer"](local_optimizer_name, env["topology"])

        if optimizer_name == "tabu" and local_optimizer_name in {"diffusion", "none"}:
            best_assign, history = hybrid_tabu_diff(
                env["cpu_demands"],
                env["cpu_caps"],
                env["mem_demands"],
                env["mem_caps"],
                env["latency_ms"],
                idle_powers=env["idle_powers"],
                max_powers=env["max_powers"],
                init_assign=None,
                TABU_MAX_ITER=300,
                TABU_TENURE=30,
                NUM_MOVES=70,
                energy_weight=env["weight_energy"],
                high_power_penalty_weight=0.0,
                diffusion_optimizer=local_opt_instance,
                stagnation_trigger=3,
            )

            final_energy = energy_of_configuration(
                best_assign,
                env["cpu_demands"],
                env["mem_demands"],
                env["cpu_caps"],
                env["mem_caps"],
                idle_powers=env["idle_powers"],
                max_powers=env["max_powers"],
            )
            final_latency, _ = latency_of_configuration(
                best_assign,
                env["cpu_demands"],
                env["mem_demands"],
                env["latency_ms"],
                env["cpu_caps"],
                env["mem_caps"],
            )

            history["energy"] = [final_energy] * len(history["obj"])
            history["latency"] = [final_latency] * len(history["obj"])

            return best_assign, history

        if optimizer_name == "tabu":
            return env["hybrid_tabu"](system_model_instance, local_opt_instance)
        if optimizer_name == "bfo":
            return env["hybrid_bfo"](system_model_instance, local_opt_instance)
        if optimizer_name == "pso":
            return env["hybrid_pso"](system_model_instance, local_opt_instance)
        raise ValueError(f"Unknown optimizer: {optimizer_name}")

    env["adjacency"] = adjacency
    env["topology"] = adjacency
    env["system_model_instance"] = system_model_instance
    env["EXPERIMENT_COMBINATIONS"] = experiment_combinations
    env["MODEL_LOOKUP"] = model_lookup
    env["CDF_MODELS"] = list(cdf_models)
    env["run_global_optimizer"] = run_global_optimizer


def export_frozen_instance(env):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    machine_export = env["machine_subset"].copy().reset_index(drop=True)
    machine_export["sim_node"] = np.arange(len(machine_export))
    machine_export["node_tier"] = np.asarray(env["node_tiers"])
    machine_export["capacity_score"] = np.asarray(env["capacity_scores"], dtype=float)
    machine_export["idle_power_w"] = np.asarray(env["idle_powers"], dtype=float)
    machine_export["max_power_w"] = np.asarray(env["max_powers"], dtype=float)
    machine_export["network_delay_s"] = np.asarray(env["node_network_delay"], dtype=float)

    task_export = env["task_sampled"].copy().reset_index(drop=True)
    task_export["sample_order"] = np.arange(len(task_export))

    machine_export.to_csv(FROZEN_MACHINE_PATH, index=False)
    task_export.to_csv(FROZEN_TASK_PATH, index=False)

    meta = {
        "source_notebook": str(NOTEBOOK_PATH),
        "task_seed": int(env.get("TASK_SEED", -1)),
        "machine_seed": int(env.get("MACHINE_SEED", -1)),
        "optimizer_seed": int(env.get("OPTIMIZER_SEED", -1)),
        "max_tasks": int(env.get("MAX_TASKS", len(task_export))),
        "n_tasks": int(len(task_export)),
        "n_nodes": int(len(machine_export)),
        "node_tiers": machine_export["node_tier"].astype(str).tolist(),
        "cpu_caps": machine_export["cpu_capacity"].astype(float).tolist(),
        "mem_caps": machine_export["memory_capacity"].astype(float).tolist(),
        "idle_powers": machine_export["idle_power_w"].astype(float).tolist(),
        "max_powers": machine_export["max_power_w"].astype(float).tolist(),
        "network_delay_s": machine_export["network_delay_s"].astype(float).tolist(),
        "task_cpu_sum": float(task_export["cpu_req"].sum()),
        "task_mem_sum": float(task_export["mem_req"].sum()),
        "fingerprint": array_fingerprint(
            task_export["cpu_req"].to_numpy(dtype=float),
            task_export["mem_req"].to_numpy(dtype=float),
            machine_export["cpu_capacity"].to_numpy(dtype=float),
            machine_export["memory_capacity"].to_numpy(dtype=float),
            machine_export["idle_power_w"].to_numpy(dtype=float),
            machine_export["max_power_w"].to_numpy(dtype=float),
            machine_export["network_delay_s"].to_numpy(dtype=float),
        ),
    }
    FROZEN_META_PATH.write_text(json.dumps(meta, indent=2))

    print(f"[freeze] saved task sample: {FROZEN_TASK_PATH}")
    print(f"[freeze] saved machine nodes: {FROZEN_MACHINE_PATH}")
    print(f"[freeze] saved metadata: {FROZEN_META_PATH}")
    print(f"[freeze] fingerprint: {meta['fingerprint']}")


def load_frozen_instance(env):
    if not FROZEN_TASK_PATH.exists() or not FROZEN_MACHINE_PATH.exists():
        raise FileNotFoundError(
            "Frozen task/machine files are missing. Run without --no-frozen-instance "
            "or use --refresh-frozen-instance first."
        )

    task_sampled = pd.read_csv(FROZEN_TASK_PATH)
    machine_subset = pd.read_csv(FROZEN_MACHINE_PATH)

    env["task_sampled"] = task_sampled
    env["cpu_demands"] = task_sampled["cpu_req"].to_numpy(dtype=float)
    env["mem_demands"] = task_sampled["mem_req"].to_numpy(dtype=float)
    env["N_tasks"] = int(len(task_sampled))

    env["machine_subset"] = machine_subset
    env["cpu_caps"] = machine_subset["cpu_capacity"].to_numpy(dtype=float)
    env["mem_caps"] = machine_subset["memory_capacity"].to_numpy(dtype=float)
    env["node_tiers"] = machine_subset["node_tier"].astype(str).to_numpy()
    env["capacity_scores"] = machine_subset["capacity_score"].to_numpy(dtype=float)
    env["idle_powers"] = machine_subset["idle_power_w"].to_numpy(dtype=float)
    env["max_powers"] = machine_subset["max_power_w"].to_numpy(dtype=float)
    env["node_network_delay"] = machine_subset["network_delay_s"].to_numpy(dtype=float)
    env["latency_ms"] = env["node_network_delay"]

    fingerprint = array_fingerprint(
        env["cpu_demands"],
        env["mem_demands"],
        env["cpu_caps"],
        env["mem_caps"],
        env["idle_powers"],
        env["max_powers"],
        env["node_network_delay"],
    )
    print(f"[freeze] loaded frozen task/machine fingerprint: {fingerprint}")


def ensure_frozen_instance(refresh=False):
    if not refresh and FROZEN_TASK_PATH.exists() and FROZEN_MACHINE_PATH.exists():
        print(f"[freeze] using existing frozen task sample: {FROZEN_TASK_PATH}")
        print(f"[freeze] using existing frozen machine nodes: {FROZEN_MACHINE_PATH}")
        if FROZEN_META_PATH.exists():
            meta = json.loads(FROZEN_META_PATH.read_text())
            print(f"[freeze] existing fingerprint: {meta.get('fingerprint', 'n/a')}")
        return

    env = {
        "__name__": "__main__",
        "display": display,
    }
    execute_notebook_before_screening(env)
    export_frozen_instance(env)


def prepare_cdf_environment(cdf_models, use_frozen_instance=True):
    env = {
        "__name__": "__main__",
        "display": display,
    }
    execute_notebook_before_screening(env)
    if use_frozen_instance:
        load_frozen_instance(env)
    bootstrap_cdf_globals(env, cdf_models)
    return env


def run_model_cdf(args):
    model_name, runs, use_frozen_instance = args
    env = prepare_cdf_environment([model_name], use_frozen_instance=use_frozen_instance)
    global_opt, local_opt = env["MODEL_LOOKUP"][model_name]

    scores = []
    energy_scores = []
    latency_scores = []

    for run_idx in range(runs):
        run_seed = int(env["OPTIMIZER_SEED"]) + 10_000 + run_idx
        env["rng_optimizer"] = np.random.default_rng(run_seed)

        _, history = env["run_global_optimizer"](
            optimizer_name=global_opt,
            system_model_instance=env["system_model_instance"],
            local_optimizer_name=local_opt,
        )

        scores.append(float(history["obj"][-1]))
        energy_scores.append(float(history["energy"][-1]))
        latency_scores.append(float(history["latency"][-1]))

        print(f"[{model_name}] run {run_idx + 1}/{runs} seed={run_seed}", flush=True)

    return model_name, scores, energy_scores, latency_scores


def build_summary(scores, energy_scores, latency_scores):
    rows = []
    for name in scores:
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
    df = df.reset_index(drop=True)
    best_mean = float(df["objective_mean"].iloc[0])
    df["gap_vs_best_mean"] = df["objective_mean"] - best_mean
    df["gap_vs_best_pct"] = 100.0 * df["gap_vs_best_mean"] / max(best_mean, 1e-12)
    return df


def parse_models(raw_models):
    if not raw_models:
        return None
    models = []
    for item in raw_models:
        models.extend(part.strip() for part in item.split(",") if part.strip())
    return models


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional model names, e.g. TABU+DIFFUSION TABU+CPM TABU+NONE",
    )
    parser.add_argument(
        "--no-frozen-instance",
        action="store_true",
        help="Use the notebook's deterministic sampling directly instead of frozen task/machine CSV files.",
    )
    parser.add_argument(
        "--refresh-frozen-instance",
        action="store_true",
        help="Re-export task and machine samples from the current saved Comparision.ipynb before running CDF.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    requested_models = parse_models(args.models)
    if requested_models is None:
        cdf_models = DEFAULT_CDF_MODELS
    else:
        cdf_models = requested_models

    workers = max(1, min(int(args.workers), len(cdf_models)))
    use_frozen_instance = not args.no_frozen_instance

    if use_frozen_instance:
        ensure_frozen_instance(refresh=args.refresh_frozen_instance)

    print(f"Parallel CDF models: {cdf_models}")
    print(f"Runs per model: {args.runs}")
    print(f"Workers: {workers}")
    print(f"Frozen task/machine: {use_frozen_instance}")

    scores = {}
    energy_scores = {}
    latency_scores = {}

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_model_cdf, (model_name, args.runs, use_frozen_instance)): model_name
            for model_name in cdf_models
        }
        for future in as_completed(futures):
            model_name, model_scores, model_energy, model_latency = future.result()
            scores[model_name] = model_scores
            energy_scores[model_name] = model_energy
            latency_scores[model_name] = model_latency
            print(f"[done] {model_name}", flush=True)

    summary_df = build_summary(scores, energy_scores, latency_scores)

    summary_path = OUTPUT_DIR / "cdf_summary_parallel.csv"
    summary_df.to_csv(summary_path, index=False)

    cache_payload = {
        "runs": int(args.runs),
        "models": cdf_models,
        "scores": scores,
        "energy_scores": energy_scores,
        "latency_scores": latency_scores,
        "summary": summary_df.to_dict(orient="records"),
        "frozen_instance": {
            "enabled": bool(use_frozen_instance),
            "task_path": str(FROZEN_TASK_PATH) if use_frozen_instance else None,
            "machine_path": str(FROZEN_MACHINE_PATH) if use_frozen_instance else None,
            "meta_path": str(FROZEN_META_PATH) if use_frozen_instance else None,
            "meta": json.loads(FROZEN_META_PATH.read_text()) if use_frozen_instance and FROZEN_META_PATH.exists() else None,
        },
    }
    cache_path = OUTPUT_DIR / f"cdf_parallel_top3_{args.runs}.json"
    latest_path = OUTPUT_DIR / "cdf_parallel_latest.json"
    cache_path.write_text(json.dumps(cache_payload, indent=2))
    latest_path.write_text(json.dumps(cache_payload, indent=2))

    plot_path = save_cdf_plots(scores)

    print("\n=== PARALLEL CDF SUMMARY ===")
    print(summary_df.to_string(index=False))
    print(f"\nSaved cache JSON: {cache_path}")
    print(f"Saved latest JSON: {latest_path}")
    print(f"Saved summary CSV: {summary_path}")
    print(f"Saved CDF plot: {plot_path}")


if __name__ == "__main__":
    main()
