from collections import defaultdict, Counter
import os
import numpy as np
import requests
import time

from config import EDGE_NODES
from central.assignment_engine import (
    TABU_ENERGY_WEIGHT,
    TABU_RESOURCE_PRESSURE_PENALTY_WEIGHT,
    random_assignment,
    optimized_assignment,
    tabu_assignment,
)
from central.node_resources import NODE_RESOURCES
from central.simulation_model import (
    calibrated_real_energy_of_configuration,
    energy_of_configuration,
    latency_of_configuration,
)

SECONDS_PER_KWH = 3_600_000.0
BASELINE_SEED = 2026 + 17
HIGH_POWER_ENERGY_PENALTY_WEIGHT = float(os.getenv("HIGH_POWER_ENERGY_PENALTY_WEIGHT", "0.15"))
RANDOM_BASELINE_MODE = os.getenv("RANDOM_BASELINE_MODE", "skewed_random")
RANDOM_BASELINE_DIRICHLET_ALPHA = float(os.getenv("RANDOM_BASELINE_DIRICHLET_ALPHA", "0.25"))


def normalize_perf_clock_seconds(clock_value, execution_time=None):
    if clock_value is None:
        return None

    value = float(clock_value)
    candidates = [
        value / 1_000.0,        # milliseconds
        value / 1_000_000.0,    # nanoseconds
        value / 1_000_000_000.0 # picoseconds, kept as a sanity fallback
    ]

    if execution_time and execution_time > 0:
        max_reasonable = max(float(execution_time) * 16.0, float(execution_time) + 1.0)
        for candidate in candidates:
            if 0.0 <= candidate <= max_reasonable:
                return candidate

    return candidates[0]


def estimate_task_energy_joule(task, result_row, node):
    task_clock_ms = result_row.get("observed_task_clock_ms")
    cpu_clock_ms = result_row.get("observed_cpu_clock_ms")
    execution_time = float(result_row.get("execution_time") or 0.0)

    active_time_s = (
        normalize_perf_clock_seconds(task_clock_ms, execution_time)
        if task_clock_ms is not None
        else execution_time
    )
    cpu_active_time_s = (
        normalize_perf_clock_seconds(cpu_clock_ms, execution_time)
        if cpu_clock_ms is not None
        else active_time_s
    )

    cpu_util = min(float(task["cpu_demand"]) / max(float(node["cpu"]), 1e-6), 1.0)
    mem_util = min(float(task["memory_demand"]) / max(float(node["mem"]), 1e-6), 1.0)

    idle_power = float(node.get("idle_power_w", 5.0 * node.get("power", 1.0)))
    max_power = float(node.get("max_power_w", 12.0 * node.get("power", 1.0)))
    dynamic_power_span = max(0.0, max_power - idle_power)

    # Use real observed clocks from perf:
    # - task_clock tracks wall-clock active runtime seen by the task
    # - cpu_clock tracks actual CPU time consumed
    # This keeps energy tied to the real workload instead of only static demand.
    cpu_dynamic_energy = dynamic_power_span * cpu_util * cpu_active_time_s

    # Memory touches keep some pressure during the task's active lifetime, even
    # when CPU is not fully saturated, so we keep a lighter wall-time term here.
    memory_dynamic_energy = 0.15 * dynamic_power_span * mem_util * active_time_s

    idle_energy = idle_power * active_time_s

    return idle_energy + cpu_dynamic_energy + memory_dynamic_energy


def estimate_high_power_penalty_joule(task, result_row, node, min_max_power_w):
    task_clock_ms = result_row.get("observed_task_clock_ms")
    execution_time = float(result_row.get("execution_time") or 0.0)

    active_time_s = (
        normalize_perf_clock_seconds(task_clock_ms, execution_time)
        if task_clock_ms is not None
        else execution_time
    )

    max_power = float(node.get("max_power_w", 12.0 * node.get("power", 1.0)))
    high_power_span = max(0.0, max_power - float(min_max_power_w))

    return HIGH_POWER_ENERGY_PENALTY_WEIGHT * high_power_span * active_time_s


def get_active_nodes():
    active = {}
    for node_id, node in EDGE_NODES.items():
        url = f"http://{node['ip']}:{node['port']}/health"
        try:
            res = requests.get(url, timeout=1)
            if res.status_code == 200:
                active[node_id] = node
        except Exception:
            pass
    return active


def get_active_nodes_with_resources():
    active = {}
    for node_id, node in EDGE_NODES.items():
        url = f"http://{node['ip']}:{node['port']}/health"
        try:
            res = requests.get(url, timeout=1)
            if res.status_code == 200:
                active[node_id] = {
                    **node,
                    **NODE_RESOURCES[node_id],
                }
        except Exception:
            pass
    return active


def sorted_node_ids(nodes):
    return sorted(nodes.keys())


def random_baseline_probabilities(nodes, node_ids, rng=None):
    if RANDOM_BASELINE_MODE == "uniform":
        weights = np.ones(len(node_ids), dtype=float)
    elif RANDOM_BASELINE_MODE == "high_power":
        weights = np.array(
            [float(nodes[n].get("max_power_w", 12.0 * nodes[n].get("power", 1.0))) for n in node_ids],
            dtype=float,
        )
    elif RANDOM_BASELINE_MODE in {"skewed_random", "dirichlet", "hotspot_random"}:
        if rng is None:
            rng = np.random.default_rng()
        alpha = max(RANDOM_BASELINE_DIRICHLET_ALPHA, 1e-6)
        return rng.dirichlet(np.full(len(node_ids), alpha, dtype=float))
    else:
        weights = np.array([float(nodes[n].get("cpu", 1.0)) for n in node_ids], dtype=float)

    weights = np.maximum(weights, 1e-9)
    return weights / weights.sum()


def freeze_baseline_assignment(tasks, nodes, node_ids, seed=BASELINE_SEED):
    rng = np.random.default_rng(seed)
    baseline_node_probs = random_baseline_probabilities(nodes, node_ids, rng=rng)
    baseline_indices = rng.choice(
        len(node_ids),
        size=len(tasks),
        replace=True,
        p=baseline_node_probs,
    )
    baseline_assignment = {
        task["task_id"]: node_ids[int(node_idx)]
        for task, node_idx in zip(tasks, baseline_indices)
    }
    print(
        "[BASELINE] random_mode="
        f"{RANDOM_BASELINE_MODE} "
        f"dirichlet_alpha={RANDOM_BASELINE_DIRICHLET_ALPHA:.3f} "
        "probs="
        + ", ".join(
            f"{node_ids[i]}:{baseline_node_probs[i]:.3f}"
            for i in range(len(node_ids))
        )
    )
    return baseline_assignment, baseline_indices


def send_task_to_node(task, node_id):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks"

    print(
        f"[SEND] task_id={task['task_id']} "
        f"type={task.get('task_type')} "
        f"target_node={node_id} "
        f"cpu_time_target_ms={task.get('cpu_time_target_ms')} "
        f"memory_bytes={task.get('memory_bytes')} "
        f"url={url}"
    )

    response = requests.post(url, json=task, timeout=10)

    print(
        f"[SEND-RESP] task_id={task['task_id']} "
        f"target_node={node_id} "
        f"status_code={response.status_code} "
        f"body={response.text}"
    )

    response.raise_for_status()
    return response



def wait_for_result(task_id, node_id, timeout=120):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks/{task_id}"
    start = time.time()

    while time.time() - start < timeout:
        try:
            res = requests.get(url, timeout=3)
            data = res.json()

            if data.get("status") in ["done", "completed"]:
                return data

            if data.get("status") == "failed":
                raise RuntimeError(f"Task failed on node {node_id}: {data}")

        except Exception as e:
            print(f"[WAIT-ERROR] task_id={task_id} node={node_id} error={e}")

        time.sleep(0.5)

    raise TimeoutError(f"Timeout waiting result for {task_id} on {node_id}")


def run_offline_experiment(
    tasks,
    mode="random",
    E_ref=None,
    L_ref=None,
    P_ref=None,
    return_history=False,
    local_mode="none",
    tabu_energy_weight=None,
    tabu_resource_pressure_penalty_weight=None,
    tabu_energy_model="comparison",
):
    results = []
    active_nodes = get_active_nodes_with_resources()
    history = None

    if not active_nodes:
        print("[WARN] No active nodes detected, fallback ke semua node")
        active_nodes = {
            nid: {**EDGE_NODES[nid], **NODE_RESOURCES[nid]}
            for nid in EDGE_NODES.keys()
        }

    node_ids = sorted_node_ids(active_nodes)
    baseline_assignment, baseline_indices = freeze_baseline_assignment(tasks, active_nodes, node_ids)
    init_assign = np.array(baseline_indices, dtype=int)

    if mode == "random":
        assignments = baseline_assignment

    elif mode == "tabu":
        assignments, history = tabu_assignment(
            tasks,
            active_nodes,
            init_assign=init_assign,
            local_mode=local_mode,
            E_ref=E_ref,
            L_ref=L_ref,
            P_ref=P_ref,
            energy_weight=(
                tabu_energy_weight
                if tabu_energy_weight is not None
                else TABU_ENERGY_WEIGHT
            ),
            resource_pressure_penalty_weight=(
                tabu_resource_pressure_penalty_weight
                if tabu_resource_pressure_penalty_weight is not None
                else TABU_RESOURCE_PRESSURE_PENALTY_WEIGHT
            ),
            energy_model=tabu_energy_model,
        )

    else:
        assignments = optimized_assignment(tasks, active_nodes)

    pending = {}

    for task in tasks:
        task_id = task["task_id"]
        node_id = assignments[task_id]

        print(f"[ASSIGN] task_id={task_id} -> {node_id}")

        try:
            send_task_to_node(task, node_id)
            pending[task_id] = node_id
        except Exception as e:
            print(f"[SEND-FAIL] task_id={task_id} node={node_id} error={e}")

        time.sleep(0.05)


    while pending:
        for task_id, node_id in list(pending.items()):
            try:
                result = wait_for_result(task_id, node_id, timeout=120)
                result_payload = result.get("result", {})

                row = {
                    "task_id": task_id,
                    "latency": result.get("latency"),
                    "execution_time": result.get("execution_time"),
                    "energy": result_payload.get("energy"),
                    "node": node_id,
                    "executor_node": result_payload.get("executor_node", node_id),
                    "executor_host": result_payload.get("executor_host"),
                    "executor_pid": result_payload.get("executor_pid"),
                    "observed_task_clock_ms": result_payload.get("observed_task_clock_ms"),
                    "observed_cpu_clock_ms": result_payload.get("observed_cpu_clock_ms"),
                    "observed_memory_bytes": result_payload.get("observed_memory_bytes"),
                    "chunks": result_payload.get("chunks"),
                    "output": result_payload.get("output"),
                }

                results.append(row)

                print(
                    f"[DONE] task_id={task_id} "
                    f"assigned_node={node_id} "
                    f"executor_node={row['executor_node']} "
                    f"task_clock_ms={row['observed_task_clock_ms']} "
                    f"memory_bytes={row['observed_memory_bytes']} "
                    f"latency={row['latency']:.4f} "
                    f"exec_time={row['execution_time']:.4f}"
                )

                pending.pop(task_id)

            except Exception:
                pass

        time.sleep(0.2)

    if return_history:
        return results, history
    return results


def compute_metrics(results, tasks, nodes, energy_model="calibrated_real"):
    node_ids = sorted_node_ids(nodes)
    result_map = {r["task_id"]: r for r in results}

    latencies = []
    exec_times = []
    nodes_used = []

    cpu_usage_per_node = defaultdict(float)
    assignments = []
    cpu_demands = []
    mem_demands = []

    observed_task_clock_samples = []
    observed_memory_samples = []

    for t in tasks:
        task_id = t["task_id"]
        r = result_map[task_id]
        node = r["node"]
        node_idx = node_ids.index(node)

        latencies.append(r["latency"])
        exec_times.append(r["execution_time"])
        nodes_used.append(node)
        assignments.append(node_idx)
        cpu_demands.append(t["cpu_demand"])
        mem_demands.append(t["memory_demand"])

        cpu_usage_per_node[node] += t["cpu_demand"]

        if r.get("observed_task_clock_ms") is not None:
            observed_task_clock_samples.append(r["observed_task_clock_ms"])

        if r.get("observed_memory_bytes") is not None:
            observed_memory_samples.append(r["observed_memory_bytes"])

    assignments = np.array(assignments)
    cpu_demands = np.array(cpu_demands)
    mem_demands = np.array(mem_demands)
    cpu_caps = np.array([nodes[n]["cpu"] for n in node_ids])
    mem_caps = np.array([nodes[n]["mem"] for n in node_ids])
    latency_ms = np.array([nodes[n]["network_delay"] for n in node_ids], dtype=float)

    cpu_util = {}
    for n in node_ids:
        cap = nodes[n]["cpu"]
        usage = cpu_usage_per_node[n]
        cpu_util[n] = min(usage / cap if cap > 0 else 0, 1.5)

    min_max_power_w = min(
        float(nodes[n].get("max_power_w", 12.0 * nodes[n].get("power", 1.0)))
        for n in node_ids
    )
    estimated_real_energy_samples = []
    high_power_penalty_samples = []
    for t in tasks:
        task_id = t["task_id"]
        r = result_map[task_id]
        node = nodes[r["node"]]
        estimated_real_energy_samples.append(estimate_task_energy_joule(t, r, node))
        high_power_penalty_samples.append(
            estimate_high_power_penalty_joule(t, r, node, min_max_power_w)
        )

    total_energy_base_real_j = float(np.sum(estimated_real_energy_samples))
    total_high_power_penalty_j = float(np.sum(high_power_penalty_samples))
    total_energy_real_j = total_energy_base_real_j + total_high_power_penalty_j
    total_energy_real_kwh = total_energy_real_j / SECONDS_PER_KWH

    idle_powers = np.array([nodes[n].get("idle_power_w", 5.0 * nodes[n]["power"]) for n in node_ids])
    max_powers = np.array([nodes[n].get("max_power_w", 12.0 * nodes[n]["power"]) for n in node_ids])

    total_energy_model = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        idle_powers=idle_powers,
        max_powers=max_powers,
    )
    total_energy_calibrated_model = calibrated_real_energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        idle_powers=idle_powers,
        max_powers=max_powers,
    )
    selected_model_energy = (
        total_energy_calibrated_model
        if energy_model == "calibrated_real"
        else total_energy_model
    )

    avg_latency_model, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms=latency_ms,
        cpu_caps=cpu_caps,
        mem_caps=mem_caps,
    )

    return {
        "real_avg_latency": float(np.mean(latencies)),
        "real_total_latency": float(np.sum(latencies)),
        "real_avg_execution_time": float(np.mean(exec_times)),
        "real_total_execution_time": float(np.sum(exec_times)),
        "real_min_latency": float(np.min(latencies)),
        "real_max_latency": float(np.max(latencies)),
        "estimated_real_energy_j": total_energy_real_j,
        "estimated_real_energy_kwh": total_energy_real_kwh,
        "estimated_real_energy_per_task_j": total_energy_real_j / max(len(estimated_real_energy_samples), 1),
        "estimated_base_energy_j": total_energy_base_real_j,
        "estimated_high_power_penalty_j": total_high_power_penalty_j,
        "high_power_penalty_weight": HIGH_POWER_ENERGY_PENALTY_WEIGHT,
        "real_avg_task_clock_ms": float(np.mean(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
        "real_total_task_clock_ms": float(np.sum(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
        "real_avg_memory_bytes": float(np.mean(observed_memory_samples)) if observed_memory_samples else 0.0,
        "model_avg_latency": float(avg_latency_model),
        "model_energy": float(selected_model_energy),
        "model_energy_source": energy_model,
        "model_total_energy": float(total_energy_model),
        "model_calibrated_real_energy": float(total_energy_calibrated_model),
        "distribution": dict(Counter(nodes_used)),
    }


def print_metrics(metrics):
    print("\n=== METRICS ===")
    print("\n[REAL]")
    print(f"Avg Latency           : {metrics['real_avg_latency']:.4f}")
    print(f"Total Latency         : {metrics['real_total_latency']:.4f}")
    print(f"Avg Execution Time    : {metrics['real_avg_execution_time']:.4f}")
    print(f"Total Execution Time  : {metrics['real_total_execution_time']:.4f}")
    print(f"Min Latency           : {metrics['real_min_latency']:.4f}")
    print(f"Max Latency           : {metrics['real_max_latency']:.4f}")
    print(f"Estimated Energy (J)  : {metrics['estimated_real_energy_j']:.4f}")
    print(f"Estimated Energy (kWh): {metrics['estimated_real_energy_kwh']:.8f}")
    print(f"Energy / Task (J)     : {metrics['estimated_real_energy_per_task_j']:.4f}")
    print(f"Base Energy (J)       : {metrics['estimated_base_energy_j']:.4f}")
    print(f"High-Power Penalty (J): {metrics['estimated_high_power_penalty_j']:.4f}")
    print(f"High-Power Weight     : {metrics['high_power_penalty_weight']:.4f}")
    print(f"Avg Task Clock (ms)   : {metrics['real_avg_task_clock_ms']:.4f}")
    print(f"Total Task Clock (ms) : {metrics['real_total_task_clock_ms']:.4f}")
    print(f"Avg Memory (bytes)    : {metrics['real_avg_memory_bytes']:.2f}")

    print("\n[MODEL]")
    print(f"Avg Latency           : {metrics['model_avg_latency']:.4f}")
    print(f"Model Energy (J)      : {metrics['model_energy']:.4f}")

    print("\n[Distribution]")
    print(metrics["distribution"])


def print_all_comparison_table(metrics_random, metrics_tabu, n_tasks):
    rows = [
        ("Real avg latency", metrics_random["real_avg_latency"], metrics_tabu["real_avg_latency"]),
        ("Real total latency", metrics_random["real_total_latency"], metrics_tabu["real_total_latency"]),
        ("Real avg exec time", metrics_random["real_avg_execution_time"], metrics_tabu["real_avg_execution_time"]),
        ("Real total exec time", metrics_random["real_total_execution_time"], metrics_tabu["real_total_execution_time"]),
        ("Estimated energy J", metrics_random["estimated_real_energy_j"], metrics_tabu["estimated_real_energy_j"]),
        ("Estimated energy kWh", metrics_random["estimated_real_energy_kwh"], metrics_tabu["estimated_real_energy_kwh"]),
        ("Base energy J", metrics_random["estimated_base_energy_j"], metrics_tabu["estimated_base_energy_j"]),
        ("High-power penalty J", metrics_random["estimated_high_power_penalty_j"], metrics_tabu["estimated_high_power_penalty_j"]),
        ("Real avg task clock ms", metrics_random["real_avg_task_clock_ms"], metrics_tabu["real_avg_task_clock_ms"]),
        ("Real total task clock ms", metrics_random["real_total_task_clock_ms"], metrics_tabu["real_total_task_clock_ms"]),
        ("Model avg latency", metrics_random["model_avg_latency"], metrics_tabu["model_avg_latency"]),
        ("Model energy J", metrics_random["model_energy"], metrics_tabu["model_energy"]),
    ]

    print(f"\n=== COMPARISON TABLE (n_tasks={n_tasks}) ===")
    print(f"{'Metric':<28} {'Random':>12} {'Tabu':>12}")
    print("-" * 56)
    for name, r, t in rows:
        print(f"{name:<28} {r:>12.4f} {t:>12.4f}")
