from collections import defaultdict, Counter
import numpy as np
import requests
import time
from config import EDGE_NODES
from central.assignment_engine import random_assignment, optimized_assignment
from central.node_resources import NODE_RESOURCES
from central.assignment_engine import tabu_assignment
from central.simulation_model import (
    energy_of_configuration,
    latency_of_configuration
)

def get_active_nodes():
    active = {}
    for node_id, node in EDGE_NODES.items():
        url = f"http://{node['ip']}:{node['port']}/health"
        try:
            res = requests.get(url, timeout=1)
            if res.status_code == 200:
                active[node_id] = node
        except:
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
                    **NODE_RESOURCES[node_id]
                }
        except:
            pass
    return active

def send_task_to_node(task, node_id):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks"
    response = requests.post(url, json=task, timeout=5)
    return response

def run_offline_experiment(tasks, mode="random", E_ref=None, L_ref=None, return_history=False):
    results = []
    active_nodes = get_active_nodes_with_resources()
    history = None

    if not active_nodes:
        print("⚠️ No active nodes, fallback ke semua node")
        active_nodes = {nid: {**EDGE_NODES[nid], **NODE_RESOURCES[nid]}
                       for nid in EDGE_NODES.keys()}

    node_ids = list(active_nodes.keys())
    assign_random = random_assignment(tasks, active_nodes)
    init_assign = np.array([
        node_ids.index(assign_random[t["task_id"]])
        for t in tasks
    ])

    if mode == "random":
        if not active_nodes:
            raise Exception("❌ No active nodes available!")
        assignments = random_assignment(tasks, active_nodes)

    elif mode == "tabu":
        if not active_nodes:
            raise Exception("❌ No active nodes available!")
        assignments, history = tabu_assignment(
            tasks, active_nodes,
            init_assign=init_assign,
            local_mode="diffusion",
            E_ref=E_ref,
            L_ref=L_ref
        )
    else:
        if not active_nodes:
            raise Exception("❌ No active nodes available!")
        assignments = optimized_assignment(tasks, active_nodes)

    # ======================
    # PHASE 1: SEND ALL
    # ======================
    for task in tasks:
        task_id = task["task_id"]
        node_id = assignments[task_id]
        print(f"🚀 {task_id} → {node_id}")

        try:
            send_task_to_node(task, node_id)
        except Exception as e:
            print(f"❌ FAIL SEND {task['task_id']} → {node_id}: {e}")
        time.sleep(0.05)

    # ======================
    # PHASE 2: COLLECT
    # ======================
    pending = {t["task_id"]: assignments[t["task_id"]] for t in tasks}

    while pending:
        for task_id, node_id in list(pending.items()):
            try:
                result = wait_for_result(task_id, node_id, timeout=5)
                results.append({
                    "task_id": task_id,
                    "latency": result["latency"],
                    "execution_time": result["execution_time"],
                    "energy": result.get("energy"),
                    "node": node_id
                })
                print(f"✅ DONE → {task_id}")
                pending.pop(task_id)
            except:
                pass
        time.sleep(0.2)
    if return_history:
        return results, history
    return results

def compute_metrics(results, tasks, nodes):
    """
    ✅ FIXED: Real latency = total end-to-end latency
    """
    node_ids = list(nodes.keys())
    result_map = {r["task_id"]: r for r in results}

    latencies = []
    exec_times = []
    nodes_used = []
    
    # Per-node aggregation
    cpu_usage_per_node = defaultdict(float)
    assignments = []
    cpu_demands = []
    mem_demands = []

    # ✅ SINGLE PASS: Collect real metrics
    for t in tasks:
        task_id = t["task_id"]
        r = result_map[task_id]
        node = r["node"]
        node_idx = node_ids.index(node)

        total_system_latency = r["latency"]
        
        latencies.append(total_system_latency)
        exec_times.append(r["execution_time"])
        nodes_used.append(node)
        assignments.append(node_idx)
        cpu_demands.append(t["cpu_demand"])
        mem_demands.append(t["memory_demand"])

        cpu_usage_per_node[node] += t["cpu_demand"]

    # Convert to numpy arrays
    assignments = np.array(assignments)
    cpu_demands = np.array(cpu_demands)
    mem_demands = np.array(mem_demands)
    cpu_caps = np.array([nodes[n]["cpu"] for n in node_ids])
    mem_caps = np.array([nodes[n]["mem"] for n in node_ids])

    # Calculate CPU utilization
    cpu_util = {}
    for n in node_ids:
        cap = nodes[n]["cpu"]
        usage = cpu_usage_per_node[n]
        cpu_util[n] = min(usage / cap if cap > 0 else 0, 1.5)

    # ✅ REAL ENERGY (keep same)
    real_energy_samples = [r.get("energy") for r in results if r.get("energy") is not None]
    if real_energy_samples:
        total_energy_real = float(np.sum(real_energy_samples))
    else:
        total_energy_real = 0
        P_idle = 0.5
        P_cpu_dyn = 1.0
        P_mem_dyn = 0.3
        P_sleep = 0.1

        for n in node_ids:
            util = cpu_util[n]
            power = P_idle + P_cpu_dyn * util + P_mem_dyn * 0 if util > 0.01 else P_sleep
            execution_time = cpu_usage_per_node[n]
            if util <= 0.8:
                overload_penalty = 0
            elif util <= 1.0:
                overload_penalty = 15 * (util - 0.8)
            else:
                overload_penalty = 15 * 0.2 + 40 * (util - 1.0)
            total_energy_real += power * execution_time + overload_penalty
        total_energy_real += 0.5 * sum(1 for v in cpu_util.values() if v > 0.05)

    # ✅ MODEL METRICS
    node_powers = np.array([nodes[n]["power"] for n in node_ids])

    total_energy_model = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps,
        node_powers=node_powers
    )

    avg_latency_model, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms=None,
        cpu_caps=cpu_caps,
        mem_caps=mem_caps
    )

    return {
        "real_avg_latency": float(np.mean(latencies)),
        "real_total_latency": float(np.sum(latencies)),
        "real_avg_execution_time": float(np.mean(exec_times)),
        "real_total_execution_time": float(np.sum(exec_times)),
        "real_min_latency": float(np.min(latencies)),
        "real_max_latency": float(np.max(latencies)),
        "real_total_energy": float(total_energy_real),
        "model_avg_latency": float(avg_latency_model),
        "model_total_energy": float(total_energy_model),
        "distribution": dict(Counter(nodes_used))
    }

def print_metrics(metrics):
    print("\n📊 METRICS")
    print("\n🔴 REAL METRICS")
    print(f"Avg Latency        : {metrics['real_avg_latency']:.4f}")
    print(f"Total Latency      : {metrics['real_total_latency']:.4f}")
    print(f"\nAvg Execution Time : {metrics['real_avg_execution_time']:.4f}")
    print(f"Total Execution    : {metrics['real_total_execution_time']:.4f}")
    print(f"Min Latency : {metrics['real_min_latency']:.4f}")
    print(f"Max Latency : {metrics['real_max_latency']:.4f}")
    print(f"\nTotal Energy       : {metrics['real_total_energy']:.4f}")

    print("\n🧠 MODEL METRICS")
    print(f"Avg Latency        : {metrics['model_avg_latency']:.4f}")
    print(f"Total Energy       : {metrics['model_total_energy']:.4f}")

    print("\n📊 Distribution:")
    print(metrics["distribution"])

def print_all_comparison_table(metrics_random, metrics_tabu, n_tasks):
    rows = [
        ("Real avg latency", metrics_random["real_avg_latency"], metrics_tabu["real_avg_latency"]),
        ("Real total latency", metrics_random["real_total_latency"], metrics_tabu["real_total_latency"]),
        ("Real avg exec time", metrics_random["real_avg_execution_time"], metrics_tabu["real_avg_execution_time"]),
        ("Real total exec time", metrics_random["real_total_execution_time"], metrics_tabu["real_total_execution_time"]),
        ("Real total energy", metrics_random["real_total_energy"], metrics_tabu["real_total_energy"]),
        ("Model avg latency", metrics_random["model_avg_latency"], metrics_tabu["model_avg_latency"]),
        ("Model total energy", metrics_random["model_total_energy"], metrics_tabu["model_total_energy"]),
    ]

    print(f"\n=== COMPARISON TABLE (n_tasks={n_tasks}) ===")
    print(f"{'Metric':<24} {'Random':>12} {'Tabu':>12}")
    print("-" * 50)
    for name, r, t in rows:
        print(f"{name:<24} {r:>12.4f} {t:>12.4f}")

def wait_for_result(task_id, node_id, timeout=10):
    from config import EDGE_NODES
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks/{task_id}"
    start = time.time()

    while time.time() - start < timeout:
        try:
            res = requests.get(url, timeout=3)
            data = res.json()
            if data.get("status") in ["done", "completed"]:
                return data
        except Exception as e:
            print(f"WAIT ERROR: {e}")
        time.sleep(0.5)
