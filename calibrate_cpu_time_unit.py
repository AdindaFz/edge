import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


CALIBRATION_DIR = Path("/home/adinda-central/edge-computing-system/outputs/calibration")
OUTPUT_PATH = CALIBRATION_DIR / "cpu_time_unit_calibration.json"
CPU_CAP_TO_TIER = {
    2: "low",
    4: "mid",
    8: "high",
}
REFERENCE_TIER = "mid"


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


def summarize(rows):
    per_tier_chunk_task_clock_ms = defaultdict(list)
    per_tier_chunk_cpu_clock_ms = defaultdict(list)

    for row in rows:
        task_clock_ms = row.get("observed_task_clock_ms")
        cpu_clock_ms = row.get("observed_cpu_clock_ms")
        chunks = row.get("chunks")
        cpu_cap = row.get("executor_cpu_cap")

        if task_clock_ms in (None, 0) or cpu_clock_ms in (None, 0):
            continue
        if chunks in (None, 0):
            continue
        if cpu_cap is None:
            continue

        tier = CPU_CAP_TO_TIER.get(int(round(float(cpu_cap))), f"cpu_{int(round(float(cpu_cap)))}")
        chunk_task_clock_ms = float(task_clock_ms) / float(chunks)
        chunk_cpu_clock_ms = float(cpu_clock_ms) / float(chunks)

        per_tier_chunk_task_clock_ms[tier].append(chunk_task_clock_ms)
        per_tier_chunk_cpu_clock_ms[tier].append(chunk_cpu_clock_ms)

    return per_tier_chunk_task_clock_ms, per_tier_chunk_cpu_clock_ms


def build_payload(rows):
    task_clock_by_tier, cpu_clock_by_tier = summarize(rows)

    if REFERENCE_TIER not in task_clock_by_tier:
        raise RuntimeError(
            f"No calibration samples found for reference tier '{REFERENCE_TIER}'."
        )

    per_tier = {}
    for tier in sorted(task_clock_by_tier):
        task_samples = task_clock_by_tier[tier]
        cpu_samples = cpu_clock_by_tier.get(tier, [])
        per_tier[tier] = {
            "sample_count": len(task_samples),
            "avg_chunk_task_clock_ms": mean(task_samples),
            "median_chunk_task_clock_ms": median(task_samples),
            "avg_chunk_cpu_clock_ms": mean(cpu_samples) if cpu_samples else None,
            "median_chunk_cpu_clock_ms": median(cpu_samples) if cpu_samples else None,
        }

    recommended = per_tier[REFERENCE_TIER]["median_chunk_task_clock_ms"]

    return {
        "method": (
            "Use the median observed task-clock per chunk on the mid tier as the "
            "CPU normalization unit for generated tasks."
        ),
        "reference_tier": REFERENCE_TIER,
        "recommended_cpu_time_unit_ms": recommended,
        "per_tier_summary": per_tier,
        "source_file_count": len(sorted(set(row["_source_file"] for row in rows))),
        "row_count": len(rows),
    }


def main():
    rows = load_rows()
    if not rows:
        print("No calibration rows found.")
        return

    payload = build_payload(rows)
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(payload, f, indent=2)

    print(f"Loaded {len(rows)} rows from {CALIBRATION_DIR}")
    print(f"Reference tier: {payload['reference_tier']}")
    print(
        "Recommended CPU_TIME_UNIT_MS: "
        f"{payload['recommended_cpu_time_unit_ms']:.3f}"
    )
    print(f"Saved calibration file: {OUTPUT_PATH}")

    print("\n=== PER-TIER CHUNK SUMMARY ===")
    for tier, summary in payload["per_tier_summary"].items():
        print(
            f"{tier:<5} | n={summary['sample_count']:<5} "
            f"| avg_task_clock_ms={summary['avg_chunk_task_clock_ms']:.3f} "
            f"| median_task_clock_ms={summary['median_chunk_task_clock_ms']:.3f} "
            f"| avg_cpu_clock_ms={summary['avg_chunk_cpu_clock_ms']:.3f}"
        )


if __name__ == "__main__":
    main()
