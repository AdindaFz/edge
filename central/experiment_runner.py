import requests
import time

GATEWAY_URL = "http://192.168.56.109:8000"

def send_task(task):
    response = requests.post(
        f"{GATEWAY_URL}/tasks",
        json=task,
        timeout=5
    )
    return response.json()


def run_experiment(tasks):
    results = []

    for task in tasks:
        start = time.time()

        send_task(task)

        latency = time.time() - start

        results.append({
            "task_id": task["task_id"],
            "latency": latency
        })

    return results
