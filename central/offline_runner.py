from collections import defaultdict, Counter
import numpy as np
import requests
import time

from config import EDGE_NODES
from central.assignment_engine import (
    TABU_ENERGY_WEIGHT,
    TABU_HIGH_POWER_PENALTY_WEIGHT,
    random_assignment,
    optimized_assignment,
    tabu_assignment,
)
from central.node_resources import NODE_RESOURCES
from central.simulation_model import (
    energy_of_configuration,
    latency_of_configuration,
)

SECONDS_PER_KWH = 3_600_000.0


def estimate_task_energy_joule(task, result_row, node):
    task_clock_ms = result_row.get("observed_task_clock_ms")
    cpu_clock_ms = result_row.get("observed_cpu_clock_ms")

    active_time_s = (
        float(task_clock_ms) / 1000.0
        if task_clock_ms is not None
        else float(result_row.get("execution_time") or 0.0)
    )
    cpu_active_time_s = (
        float(cpu_clock_ms) / 1000.0
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
    return_history=False,
    local_mode="none",
    tabu_energy_weight=None,
    tabu_high_power_penalty_weight=None,
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

    node_ids = list(active_nodes.keys())

    assign_random = random_assignment(tasks, active_nodes)
    init_assign = np.array([
        node_ids.index(assign_random[t["task_id"]])
        for t in tasks
    ])

    if mode == "random":
        assignments = random_assignment(tasks, active_nodes)

    elif mode == "tabu":
        assignments, history = tabu_assignment(
            tasks,
            active_nodes,
            init_assign=init_assign,
            local_mode=local_mode,
            E_ref=E_ref,
            L_ref=L_ref,
            energy_weight=(
                tabu_energy_weight
                if tabu_energy_weight is not None
                else TABU_ENERGY_WEIGHT
            ),
            high_power_penalty_weight=(
                tabu_high_power_penalty_weight
                if tabu_high_power_penalty_weight is not None
                else TABU_HIGH_POWER_PENALTY_WEIGHT
            ),
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


def compute_metrics(results, tasks, nodes):
    node_ids = list(nodes.keys())
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

    estimated_real_energy_samples = []
    for t in tasks:
        task_id = t["task_id"]
        r = result_map[task_id]
        node = nodes[r["node"]]
        estimated_real_energy_samples.append(estimate_task_energy_joule(t, r, node))

    total_energy_real_j = float(np.sum(estimated_real_energy_samples))
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
        "estimated_real_energy_per_task_j": float(np.mean(estimated_real_energy_samples)) if estimated_real_energy_samples else 0.0,
        "real_avg_task_clock_ms": float(np.mean(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
        "real_total_task_clock_ms": float(np.sum(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
        "real_avg_memory_bytes": float(np.mean(observed_memory_samples)) if observed_memory_samples else 0.0,
        "model_avg_latency": float(avg_latency_model),
        "model_total_energy": float(total_energy_model),
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
    print(f"Avg Task Clock (ms)   : {metrics['real_avg_task_clock_ms']:.4f}")
    print(f"Total Task Clock (ms) : {metrics['real_total_task_clock_ms']:.4f}")
    print(f"Avg Memory (bytes)    : {metrics['real_avg_memory_bytes']:.2f}")

    print("\n[MODEL]")
    print(f"Avg Latency           : {metrics['model_avg_latency']:.4f}")
    print(f"Model Energy (J)      : {metrics['model_total_energy']:.4f}")

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
        ("Real avg task clock ms", metrics_random["real_avg_task_clock_ms"], metrics_tabu["real_avg_task_clock_ms"]),
        ("Real total task clock ms", metrics_random["real_total_task_clock_ms"], metrics_tabu["real_total_task_clock_ms"]),
        ("Model avg latency", metrics_random["model_avg_latency"], metrics_tabu["model_avg_latency"]),
        ("Model energy J", metrics_random["model_total_energy"], metrics_tabu["model_total_energy"]),
    ]

    print(f"\n=== COMPARISON TABLE (n_tasks={n_tasks}) ===")
    print(f"{'Metric':<28} {'Random':>12} {'Tabu':>12}")
    print("-" * 56)
    for name, r, t in rows:
        print(f"{name:<28} {r:>12.4f} {t:>12.4f}")
