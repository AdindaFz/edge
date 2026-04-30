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


def estimate_energy_from_row(row):
    task_clock_s = float(row["observed_task_clock_ms"]) / 1000.0
    cpu_clock_s = float(row["observed_cpu_clock_ms"]) / 1000.0
    cpu_demand = float(row["cpu_demand"])
    mem_demand = float(row["memory_demand"])
    cpu_cap = float(row["executor_cpu_cap"])
    mem_cap = float(row["executor_mem_cap"])
    idle_power = float(row["executor_idle_power_w"])
    max_power = float(row["executor_max_power_w"])

    cpu_util = min(cpu_demand / max(cpu_cap, 1e-6), 1.0)
    mem_util = min(mem_demand / max(mem_cap, 1e-6), 1.0)
    dynamic_power_span = max(0.0, max_power - idle_power)

    idle_energy = idle_power * task_clock_s
    cpu_dynamic_energy = dynamic_power_span * cpu_util * cpu_clock_s
    memory_dynamic_energy = 0.15 * dynamic_power_span * mem_util * task_clock_s
    total_energy = idle_energy + cpu_dynamic_energy + memory_dynamic_energy

    return {
        "total_energy": total_energy,
        "idle_energy": idle_energy,
        "cpu_dynamic_energy": cpu_dynamic_energy,
        "memory_dynamic_energy": memory_dynamic_energy,
        "task_clock_s": task_clock_s,
        "cpu_clock_s": cpu_clock_s,
    }


def main():
    rows = load_rows()
    if not rows:
        print("No calibration rows found.")
        return

    per_cap = defaultdict(list)
    for row in rows:
        cpu_cap = int(round(float(row["executor_cpu_cap"])))
        enriched = estimate_energy_from_row(row)
        enriched["cpu_demand"] = float(row["cpu_demand"])
        enriched["mem_demand"] = float(row["memory_demand"])
        enriched["idle_power"] = float(row["executor_idle_power_w"])
        enriched["max_power"] = float(row["executor_max_power_w"])
        per_cap[cpu_cap].append(enriched)

    print(f"Loaded {len(rows)} rows from {CALIBRATION_DIR}")
    print(f"Source files: {len(sorted(set(row['_source_file'] for row in rows)))}")

    print("\n=== ENERGY SUMMARY ===")
    for cpu_cap in sorted(per_cap):
        items = per_cap[cpu_cap]
        avg_total = mean(i["total_energy"] for i in items)
        avg_idle = mean(i["idle_energy"] for i in items)
        avg_cpu_dyn = mean(i["cpu_dynamic_energy"] for i in items)
        avg_mem_dyn = mean(i["memory_dynamic_energy"] for i in items)
        avg_task_clock = mean(i["task_clock_s"] for i in items)
        avg_cpu_clock = mean(i["cpu_clock_s"] for i in items)
        avg_idle_power = mean(i["idle_power"] for i in items)
        avg_max_power = mean(i["max_power"] for i in items)
        avg_cpu_demand = mean(i["cpu_demand"] for i in items)
        avg_mem_demand = mean(i["mem_demand"] for i in items)

        dynamic_span = max(0.0, avg_max_power - avg_idle_power)
        cpu_ratio = min(avg_cpu_demand / max(cpu_cap, 1e-6), 1.0)
        mem_ratio = min(avg_mem_demand / max(cpu_cap, 1e-6), 1.0)

        suggested_cpu_multiplier = (
            avg_cpu_dyn / max(dynamic_span * cpu_ratio * avg_task_clock, 1e-6)
        )
        suggested_mem_multiplier = (
            avg_mem_dyn / max(dynamic_span * mem_ratio * avg_task_clock, 1e-6)
        )

        print(
            f"cpu={cpu_cap} | samples={len(items)} "
            f"| avg_total={avg_total:.4f} "
            f"| avg_idle={avg_idle:.4f} "
            f"| avg_cpu_dynamic={avg_cpu_dyn:.4f} "
            f"| avg_mem_dynamic={avg_mem_dyn:.4f} "
            f"| avg_task_clock_s={avg_task_clock:.4f} "
            f"| avg_cpu_clock_s={avg_cpu_clock:.4f} "
            f"| suggested_cpu_multiplier={suggested_cpu_multiplier:.4f} "
            f"| suggested_mem_multiplier={suggested_mem_multiplier:.4f}"
        )


if __name__ == "__main__":
    main()
