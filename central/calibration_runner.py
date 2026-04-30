from collections import defaultdict
import json

from central.node_resources import NODE_RESOURCES
from central.offline_runner import run_offline_experiment, compute_metrics
from central.task_generator import generate_calibration_tasks


CALIBRATION_NODE_GROUPS = {
    "low": [],  # Not available yet
    "mid": ["edge-6"],
    "high": ["edge-7"],
}


def build_forced_assignments(tasks, node_id):
    return {task["task_id"]: node_id for task in tasks}


def summarize_results(results):
    rows = []
    for row in results:
        rows.append(
            {
                "task_id": row["task_id"],
                "executor_node": row.get("executor_node"),
                "latency": row.get("latency"),
                "execution_time": row.get("execution_time"),
                "observed_task_clock_ms": row.get("observed_task_clock_ms"),
                "observed_cpu_clock_ms": row.get("observed_cpu_clock_ms"),
                "observed_memory_bytes": row.get("observed_memory_bytes"),
                "psutil_cpu_avg_percent": row.get("psutil_cpu_avg_percent"),
                "psutil_cpu_peak_percent": row.get("psutil_cpu_peak_percent"),
                "psutil_mem_avg_percent": row.get("psutil_mem_avg_percent"),
                "psutil_mem_peak_percent": row.get("psutil_mem_peak_percent"),
                "chunks": row.get("chunks"),
            }
        )
    return rows


def run_node_calibration(node_id, seed=42):
    tasks = generate_calibration_tasks(seed=seed)
    forced_assignments = build_forced_assignments(tasks, node_id)
    results, _ = run_offline_experiment(
        tasks,
        mode="random",
        return_history=True,
        forced_assignments=forced_assignments,
    )
    metrics = compute_metrics(results, tasks, NODE_RESOURCES)
    return tasks, results, metrics


def print_node_report(node_id, tasks, results, metrics):
    print(f"\n=== CALIBRATION NODE {node_id} ===")
    print(
        f"Avg latency={metrics['real_avg_latency']:.4f} | "
        f"Avg exec={metrics['real_avg_execution_time']:.4f} | "
        f"Estimated energy={metrics['estimated_real_energy_j']:.4f} J | "
        f"Avg psutil CPU={metrics['real_avg_psutil_cpu_percent']:.2f}% | "
        f"Peak psutil CPU={metrics['real_peak_psutil_cpu_percent']:.2f}%"
    )

    task_map = {task["task_id"]: task for task in tasks}
    for row in results:
        task = task_map[row["task_id"]]
        print(
            f"{task['task_id']:<10} "
            f"target_cpu_ms={task['cpu_time_target_ms']:<7.1f} "
            f"memory_mb={task['memory_bytes'] / (1024 * 1024):<6.0f} "
            f"task_clock_ms={row.get('observed_task_clock_ms', 0):<8.2f} "
            f"exec_time={row.get('execution_time', 0):<7.3f} "
            f"latency={row.get('latency', 0):<7.3f} "
            f"psutil_avg={row.get('psutil_cpu_avg_percent', 0) or 0:<6.2f} "
            f"psutil_peak={row.get('psutil_cpu_peak_percent', 0) or 0:<6.2f}"
        )


def run_group_calibration(node_groups=None, seed=42):
    node_groups = node_groups or CALIBRATION_NODE_GROUPS
    full_report = defaultdict(dict)

    for group_name, node_ids in node_groups.items():
        for idx, node_id in enumerate(node_ids):
            tasks, results, metrics = run_node_calibration(node_id=node_id, seed=seed + idx)
            full_report[group_name][node_id] = {
                "tasks": tasks,
                "results": summarize_results(results),
                "metrics": metrics,
            }
            print_node_report(node_id, tasks, results, metrics)

    return full_report


if __name__ == "__main__":
    report = run_group_calibration()
    print("\n=== CALIBRATION JSON ===")
    print(json.dumps(report, indent=2))
