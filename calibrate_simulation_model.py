import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


CALIBRATION_DIR = Path("/home/adinda-central/edge-computing-system/outputs/calibration")


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


def safe_div(numerator, denominator):
    if denominator in (0, 0.0, None):
        return None
    return float(numerator) / float(denominator)


def summarize(rows):
    service_coeffs = defaultdict(list)
    latency_service_coeffs = defaultdict(list)
    active_coeffs = defaultdict(list)
    latency_by_cap = defaultdict(list)
    exec_by_cap = defaultdict(list)
    task_clock_by_cap = defaultdict(list)
    cpu_clock_by_cap = defaultdict(list)
    counts = defaultdict(int)

    for row in rows:
        cpu_cap = int(round(float(row["executor_cpu_cap"])))
        cpu_demand = float(row["cpu_demand"])

        if cpu_demand <= 0:
            continue

        latency = row.get("latency")
        execution_time = row.get("execution_time")
        task_clock_ms = row.get("observed_task_clock_ms")
        cpu_clock_ms = row.get("observed_cpu_clock_ms")
        network_delay = float(row.get("executor_network_delay") or 0.0)

        if execution_time is not None:
            service_coeff = safe_div(float(execution_time), cpu_demand)
            if service_coeff is not None:
                service_coeffs[cpu_cap].append(service_coeff)
            exec_by_cap[cpu_cap].append(float(execution_time))

        if latency is not None:
            latency_service_coeff = safe_div(max(float(latency) - network_delay, 0.0), cpu_demand)
            if latency_service_coeff is not None:
                latency_service_coeffs[cpu_cap].append(latency_service_coeff)
            latency_by_cap[cpu_cap].append(float(latency))

        if task_clock_ms is not None:
            task_clock_s = float(task_clock_ms) / 1000.0
            active_coeff = safe_div(task_clock_s, cpu_demand)
            if active_coeff is not None:
                active_coeffs[cpu_cap].append(active_coeff)
            task_clock_by_cap[cpu_cap].append(task_clock_s)

        if cpu_clock_ms is not None:
            cpu_clock_by_cap[cpu_cap].append(float(cpu_clock_ms) / 1000.0)

        counts[cpu_cap] += 1

    return {
        "service_coeffs": service_coeffs,
        "latency_service_coeffs": latency_service_coeffs,
        "active_coeffs": active_coeffs,
        "latency_by_cap": latency_by_cap,
        "exec_by_cap": exec_by_cap,
        "task_clock_by_cap": task_clock_by_cap,
        "cpu_clock_by_cap": cpu_clock_by_cap,
        "counts": counts,
    }


def format_mapping(title, mapping):
    print(f"\n{title}")
    print("{")
    for cpu_cap in sorted(mapping):
        print(f"    {cpu_cap}: {mapping[cpu_cap]:.4f},")
    print("}")


def main():
    rows = load_rows()
    if not rows:
        print("No calibration rows found.")
        return

    summary = summarize(rows)

    print(f"Loaded {len(rows)} calibration rows from {CALIBRATION_DIR}")
    print(f"Source files: {len(sorted(set(row['_source_file'] for row in rows)))}")

    recommended_service = {}
    recommended_active = {}

    print("\n=== PER-TIER SUMMARY ===")
    for cpu_cap in sorted(summary["counts"]):
        n = summary["counts"][cpu_cap]
        service_avg = mean(summary["service_coeffs"][cpu_cap]) if summary["service_coeffs"][cpu_cap] else None
        latency_service_avg = (
            mean(summary["latency_service_coeffs"][cpu_cap])
            if summary["latency_service_coeffs"][cpu_cap]
            else None
        )
        active_avg = mean(summary["active_coeffs"][cpu_cap]) if summary["active_coeffs"][cpu_cap] else None
        latency_avg = mean(summary["latency_by_cap"][cpu_cap]) if summary["latency_by_cap"][cpu_cap] else None
        exec_avg = mean(summary["exec_by_cap"][cpu_cap]) if summary["exec_by_cap"][cpu_cap] else None
        task_clock_avg = mean(summary["task_clock_by_cap"][cpu_cap]) if summary["task_clock_by_cap"][cpu_cap] else None
        cpu_clock_avg = mean(summary["cpu_clock_by_cap"][cpu_cap]) if summary["cpu_clock_by_cap"][cpu_cap] else None

        if service_avg is not None:
            recommended_service[cpu_cap] = service_avg
        if active_avg is not None:
            recommended_active[cpu_cap] = active_avg

        print(
            f"cpu={cpu_cap} | n={n} "
            f"| exec_service_coeff={service_avg:.4f} "
            f"| latency_service_coeff={latency_service_avg:.4f} "
            f"| active_coeff={active_avg:.4f} "
            f"| avg_latency={latency_avg:.4f} "
            f"| avg_exec={exec_avg:.4f} "
            f"| avg_task_clock_s={task_clock_avg:.4f} "
            f"| avg_cpu_clock_s={cpu_clock_avg:.4f}"
        )

    print("\n=== RECOMMENDED COEFFICIENTS ===")
    format_mapping("SERVICE_TIME_PER_CPU_DEMAND =", recommended_service)
    format_mapping("ACTIVE_TIME_PER_CPU_DEMAND =", recommended_active)


if __name__ == "__main__":
    main()
