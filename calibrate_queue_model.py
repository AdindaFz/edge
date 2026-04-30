import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


CALIBRATION_DIR = Path("/home/adinda-central/edge-computing-system/outputs/calibration")
MAX_CONCURRENT_TASKS = 2


def load_rows():
    rows = []
    for path in sorted(CALIBRATION_DIR.glob("workload_calibration_*.jsonl")):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row["_source_file"] = str(path)
                rows.append(row)
    return rows


def build_grouped_runs(rows):
    grouped = defaultdict(list)
    for row in rows:
        key = (row["_source_file"], row["mode"])
        grouped[key].append(row)
    return grouped


def main():
    rows = load_rows()
    if not rows:
        print("No calibration rows found.")
        return

    grouped = build_grouped_runs(rows)
    per_cap_records = defaultdict(list)

    for (_, _mode), group_rows in grouped.items():
        tasks_per_node = defaultdict(list)
        for row in group_rows:
            tasks_per_node[row["executor_node"]].append(row)

        for executor_node, node_rows in tasks_per_node.items():
            task_count = len(node_rows)
            queue_factor = max(0.0, (task_count / MAX_CONCURRENT_TASKS) - 1.0)

            for row in node_rows:
                cpu_cap = int(round(float(row["executor_cpu_cap"])))
                latency = float(row["latency"])
                execution_time = float(row["execution_time"])
                network_delay = float(row.get("executor_network_delay") or 0.0)
                cpu_demand = float(row["cpu_demand"])

                service_plus_network = execution_time + network_delay
                queue_residual = max(0.0, latency - service_plus_network)
                normalized_queue = (
                    queue_residual / cpu_demand
                    if cpu_demand > 0
                    else 0.0
                )

                per_cap_records[cpu_cap].append(
                    {
                        "queue_factor": queue_factor,
                        "queue_residual": queue_residual,
                        "normalized_queue": normalized_queue,
                        "task_count": task_count,
                    }
                )

    print(f"Loaded {len(rows)} rows from {CALIBRATION_DIR}")
    print(f"Source files: {len(sorted(set(row['_source_file'] for row in rows)))}")

    print("\n=== QUEUE SUMMARY ===")
    for cpu_cap in sorted(per_cap_records):
        records = per_cap_records[cpu_cap]
        positive = [r for r in records if r["queue_factor"] > 0]

        avg_queue_residual = mean(r["queue_residual"] for r in records)
        avg_positive_queue_residual = mean(r["queue_residual"] for r in positive) if positive else 0.0
        avg_positive_norm = mean(r["normalized_queue"] for r in positive) if positive else 0.0
        avg_positive_factor = mean(r["queue_factor"] for r in positive) if positive else 0.0

        suggested_multiplier = (
            avg_positive_norm / avg_positive_factor
            if positive and avg_positive_factor > 0
            else 0.0
        )

        print(
            f"cpu={cpu_cap} | samples={len(records)} "
            f"| avg_queue_residual={avg_queue_residual:.4f} "
            f"| avg_positive_queue_residual={avg_positive_queue_residual:.4f} "
            f"| avg_positive_norm={avg_positive_norm:.4f} "
            f"| avg_positive_factor={avg_positive_factor:.4f} "
            f"| suggested_queue_multiplier={suggested_multiplier:.4f}"
        )


if __name__ == "__main__":
    main()
