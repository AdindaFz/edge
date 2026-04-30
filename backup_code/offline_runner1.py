import requests
import time
from config import EDGE_NODES
from central.assignment_engine import random_assignment, optimized_assignment
from central.node_resources import NODE_RESOURCES
from central.assignment_engine import tabu_assignment

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

def send_task_to_node(task, node_id):
    node = EDGE_NODES[node_id]

    url = f"http://{node['ip']}:{node['port']}/tasks"

    response = requests.post(url, json=task, timeout=5)

    return response

def run_offline_experiment(tasks, mode="random"):
    results = []

    if mode == "random":
        active_nodes = get_active_nodes()

        if not active_nodes:
            raise Exception("❌ No active nodes available!")

        assignments = random_assignment(tasks, active_nodes)
    elif mode == "tabu":
        active_nodes = get_active_nodes()

        if not active_nodes:
            raise Exception("❌ No active nodes available!")

        assignments = tabu_assignment(tasks, active_nodes, local_mode="diffusion")
    else:
        active_nodes = get_active_nodes()

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

def compute_metrics(results):
    import numpy as np
    from collections import Counter

    required_keys = ["latency", "execution_time", "node"]

    latencies = []
    exec_times = []
    nodes = []
    energies = []

    for i, r in enumerate(results):
        for key in required_keys:
            if key not in r:
                raise ValueError(f"Missing '{key}' in result index {i}: {r}")

        latencies.append(r["latency"])
        exec_times.append(r["execution_time"])
        nodes.append(r["node"])
        energies.append(r["energy"])

    return {
        "avg_latency": float(np.mean(latencies)),
        "min_latency": float(np.min(latencies)),
        "max_latency": float(np.max(latencies)),
        "sum_energy": float(np.sum(energies)),
        "avg_energy": float(np.mean(energies)),
        "avg_execution_time": float(np.mean(exec_times)),
        "distribution": dict(Counter(nodes))
    }

def print_metrics(metrics):
    print("\n📊 METRICS")
    print(f"Avg Latency : {metrics['avg_latency']:.3f}")
    print(f"Min Latency : {metrics['min_latency']:.3f}")
    print(f"Max Latency : {metrics['max_latency']:.3f}")
    print(f"Avg Energy  : {metrics['avg_energy']:.3f}")
    print(f"Sum Energy  : {metrics['sum_energy']:.3f}")

    print(f"\nAvg Execution Time : {metrics['avg_execution_time']:.3f}")

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

    raise TimeoutError(f"Task {task_id} timeout")
