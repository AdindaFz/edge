import requests
import time
from config import EDGE_NODES
from central.assignment_engine import random_assignment, optimized_assignment
from central.node_resources import NODE_RESOURCES
from central.assignment_engine import tabu_assignment
import numpy as np
import random
from central.simulation_model import (
    energy_of_configuration,
    latency_of_configuration
)
from collections import Counter

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

from central.node_resources import NODE_RESOURCES

def get_active_nodes_with_resources():
    active = {}

    for node_id, node in EDGE_NODES.items():
        url = f"http://{node['ip']}:{node['port']}/health"

        try:
            res = requests.get(url, timeout=1)
            if res.status_code == 200:
                # 🔥 merge
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

def run_offline_experiment(tasks, mode="random", E_ref=None, L_ref=None):
    results = []

    # 🔥 ambil node aktif
    active_nodes = get_active_nodes_with_resources()

    # fallback kalau semua mati (biar nggak crash)
    if not active_nodes:
        print("⚠️ No active nodes, fallback ke semua node")
        active_nodes = EDGE_NODES
    node_ids = list(active_nodes.keys())

    # 🔥 baseline random
    assign_random = random_assignment(tasks, active_nodes)

    init_assign = np.array([
        node_ids.index(assign_random[t["task_id"]])
        for t in tasks
    ])

    if mode == "random":
        if not active_nodes:
            raise Exception("❌ No active nodes available!")

        assignments = random_assignment(tasks, active_nodes)
#        history = None
    elif mode == "tabu":
        if not active_nodes:
            raise Exception("❌ No active nodes available!")

        assignments, history = tabu_assignment(tasks, active_nodes, init_assign=init_assign, local_mode="diffusion", E_ref=E_ref, L_ref=L_ref)
    else:
        if not active_nodes:
            raise Exception("❌ No active nodes available!")

        assignments = optimized_assignment(tasks, active_nodes)
 #       history = None
    # ======================
    # PHASE 1: SEND ALL
    # ======================
    for task in tasks:
        task_id = task["task_id"]
        node_id = assignments[task_id]

        print(f"🚀 {task_id} → {node_id}")
        print(f"SEND → {task_id} ke {node_id}")

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

                execution_time = result["execution_time"]
                latency = result["latency"]

                power = NODE_RESOURCES[node_id].get("power", 1.5)
                energy = execution_time * power

                results.append({
                    "task_id": task_id,
                    "latency": latency,
                    "execution_time": execution_time,
                    "energy": energy,
                    "node": node_id
                })

                print(f"✅ DONE → {task_id}")
                pending.pop(task_id)

            except:
                pass

        time.sleep(0.2)

    return results

def get_result(task_id):
    import requests

    res = requests.get(f"http://10.33.102.106:8000/tasks/{task_id}")
    return res.json()

def compute_metrics(results, tasks, nodes):
    import numpy as np
    from collections import Counter

    node_ids = list(nodes.keys())

    # ======================
    # REAL METRICS
    # ======================
    latencies = []
    exec_times = []
    nodes_used = []
    energies_real = []

    # ======================
    # MODEL INPUT
    # ======================
    assignments = []
    cpu_demands = []
    mem_demands = []

    # 🔥 mapping biar O(1)
    result_map = {r["task_id"]: r for r in results}

    for t in tasks:
        task_id = t["task_id"]
        r = result_map[task_id]

        node = r["node"]
        node_idx = node_ids.index(node)

        # REAL
        latencies.append(r["latency"])
        exec_times.append(r["execution_time"])
        nodes_used.append(node)

        power = nodes[node].get("power", 1.5)
        energies_real.append(r["execution_time"] * power)

        energy_per_node = defaultdict(float)
        cpu_usage_per_node = defaultdict(float)

        for t in tasks:
            task_id = t["task_id"]
            r = result_map[task_id]

            node = r["node"]
            power = nodes[node].get("power", 1.5)

            # 🔥 pakai execution_time (anggap compute_time proxy)
            compute_time = r["execution_time"]

            energy_task = compute_time * power

            energy_per_node[node] += energy_task
            cpu_usage_per_node[node] += t["cpu_demand"]
        cpu_util = {}

        for n in node_ids:
            cap = nodes[n]["cpu"]
            usage = cpu_usage_per_node[n]

            cpu_util[n] = usage / cap if cap > 0 else 0

        # clamp biar stabil
        cpu_util = {k: min(v, 1.5) for k, v in cpu_util.items()}
        
        total_energy_real = 0

        for n in node_ids:
            util = cpu_util[n]

            if util > 0.01:
                power_model = 0.5 + 1.0 * util
            else:
                power_model = 0.1

            execution_time = cpu_usage_per_node[n]

            # 🔥 overload penalty (copy dari simulation)
            if util <= 0.8:
                overload_penalty = 0
            elif util <= 1.0:
                overload_penalty = 15 * (util - 0.8)
            else:
                overload_penalty = 15 * 0.2 + 40 * (util - 1.0)

            energy_node = power_model * execution_time + overload_penalty

            total_energy_real += energy_node
        
        active_nodes = sum(1 for v in cpu_util.values() if v > 0.05)

        total_energy_real += 0.5 * active_nodes
        
        # MODEL
        assignments.append(node_idx)
        cpu_demands.append(t["cpu_demand"])
        mem_demands.append(t["memory_demand"])

    # ======================
    # CONVERT
    # ======================
    assignments = np.array(assignments)
    cpu_demands = np.array(cpu_demands)
    mem_demands = np.array(mem_demands)

    cpu_caps = np.array([nodes[n]["cpu"] for n in node_ids])
    mem_caps = np.array([nodes[n]["mem"] for n in node_ids])

    # ======================
    # MODEL METRICS
    # ======================
    total_energy_model = energy_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        cpu_caps,
        mem_caps
    )

    avg_latency_model, _ = latency_of_configuration(
        assignments,
        cpu_demands,
        mem_demands,
        latency_ms=None,
        cpu_caps=cpu_caps,
        mem_caps=mem_caps
    )

    # ======================
    # RETURN
    # ======================
    return {
        # 🔥 REAL
        "real_avg_latency": float(np.mean(latencies)),
        "real_total_latency": float(np.sum(latencies)),

        "real_avg_execution_time": float(np.mean(exec_times)),
        "real_total_execution_time": float(np.sum(exec_times)),

        "real_min_latency": float(np.min(latencies)),
        "real_max_latency": float(np.max(latencies)),

        "real_total_energy": float(np.sum(total_energy_real)),

        # 🧠 MODEL
        "model_avg_latency": float(avg_latency_model),
        "model_total_energy": float(total_energy_model),

        # COMMON
        "distribution": dict(Counter(nodes_used))
    }

def print_metrics(metrics):
    print("\n📊 METRICS")

    # ======================
    # REAL
    # ======================
    print("\n🔴 REAL METRICS")
    print(f"Avg Latency        : {metrics['real_avg_latency']:.4f}")
    print(f"Total Latency      : {metrics['real_total_latency']:.4f}")

    print(f"\nAvg Execution Time : {metrics['real_avg_execution_time']:.4f}")
    print(f"Total Execution    : {metrics['real_total_execution_time']:.4f}")

    print(f"Min Latency : {metrics['real_min_latency']:.4f}")
    print(f"Max Latency : {metrics['real_max_latency']:.4f}")

    print(f"\nTotal Energy       : {metrics['real_total_energy']:.4f}")

    # ======================
    # MODEL
    # ======================
    print("\n🧠 MODEL METRICS")
    print(f"Avg Latency        : {metrics['model_avg_latency']:.4f}")
    print(f"Total Energy       : {metrics['model_total_energy']:.4f}")

    # ======================
    # DISTRIBUTION
    # ======================
    print("\n📊 Distribution:")
    print(metrics["distribution"])

import time
import requests

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
