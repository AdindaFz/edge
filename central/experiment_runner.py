import requests
import time
import json

GATEWAY_URL = "http://192.168.56.109:8000"
from central.task_generator import generate_batch

def send_task(task):
    response = requests.post(
        f"{GATEWAY_URL}/tasks",
        json=task,
        timeout=5
    )
    print("POST STATUS:", response.status_code)
    print("POST RESPONSE:", response.text)

    return response

def get_result(task_id):
    try:
        response = requests.get(
            f"{GATEWAY_URL}/tasks/{task_id}",
            timeout=5
        )
        return response.json()
    except:
        return {"status": "error"}

def run_experiment(tasks):
    results = []

    task_start_time = {}

    # submit
    for task in tasks:
        send_task(task)
        time.sleep(0.2)
        task_start_time[task["task_id"]] = time.time()

    print("🚀 All tasks submitted")

    pending = set([t["task_id"] for t in tasks])

    while pending:
        for task_id in list(pending):
            res = get_result(task_id)

            if res.get("status") == "completed":

                latency = time.time() - task_start_time[task_id]

                results.append({
                    "task_id": task_id,
                    "node": res.get("node_id"),
                    "latency": latency,
                    "execution_time": res.get("result", {}).get("execution_time")
                })

                print(f"✅ Done {task_id}")
                pending.remove(task_id)

        time.sleep(0.5)

    return results

def print_metrics(results):
    import numpy as np
    from collections import Counter

    latencies = [r["latency"] for r in results]

    print("\n📊 METRICS")
    print("Avg latency:", np.mean(latencies))
    print("Min latency:", np.min(latencies))
    print("Max latency:", np.max(latencies))

    nodes = [r["node"] for r in results]
    print("\n📊 DISTRIBUTION")
    print(Counter(nodes))

def print_distribution(results):
    from collections import Counter

    nodes = [r["node"] for r in results]
    print("\n📊 NODE DISTRIBUTION:")
    print(Counter(nodes))

def save_results(results, filename="results.json"):
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

def analyze_results(results):

    latencies = [r["latency"] for r in results]
    nodes = [r["node"] for r in results]

    return {
        "avg_latency": sum(latencies) / len(latencies),
        "max_latency": max(latencies),
        "min_latency": min(latencies),
        "total_tasks": len(results),
        "distribution": {
            n: nodes.count(n) for n in set(nodes)
        }
    }

def run_multiple(n_runs=5, n_tasks=20):

    all_results = []

    for i in range(n_runs):
        print(f"\nRUN {i+1}")

        tasks = generate_batch(n_tasks)
        results = run_experiment(tasks)

        summary = analyze_results(results)
        all_results.append(summary)

    return all_results

def generate_fixed_tasks(n_tasks=20):
    from central.task_generator import generate_batch
    return generate_batch(n_tasks)
