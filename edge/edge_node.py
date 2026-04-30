from fastapi import FastAPI, HTTPException
import uvicorn
from datetime import datetime
import asyncio
import httpx
import psutil
import logging
import os
import sys
import time
import subprocess
import socket
import json
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTRAL_IP, CENTRAL_PORT
from shared.models import Task, TaskResult, NodeStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NODE_ID = os.getenv("NODE_ID", "edge-6")
NODE_PORT = int(os.getenv("NODE_PORT", "8006"))
MAX_CONCURRENT_TASKS = 2

app = FastAPI(title=f"Edge Node {NODE_ID}")

task_results = {}
task_runtime = {}
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


def append_execution_log(task_id, status, extra=None):
    log_path = f"/tmp/{NODE_ID}_task_execution.log"
    line = {
        "timestamp": datetime.now().isoformat(),
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "task_id": task_id,
        "status": status,
        "extra": extra or {},
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(line) + "\n")


def parse_perf_time_ms(stderr_text, event_name):
    for line in stderr_text.splitlines():
        if event_name not in line:
            continue

        parts = [p.strip() for p in line.split(";")]
        if not parts:
            continue

        raw = parts[0].replace(",", "")
        if raw in {"", "<not counted>", "<not supported>"}:
            continue

        try:
            return float(raw)
        except ValueError:
            continue

    raise RuntimeError(f"Could not parse perf value for {event_name}: {stderr_text}")


def run_chunk_timed(memory_bytes, seed, touch_rounds):
    """Run workload without perf stat - uses time.perf_counter() for timing."""
    worker_path = os.path.join(os.path.dirname(__file__), "workload_worker.py")

    start = time.perf_counter()

    # Pass NODE_TIER to subprocess
    env = os.environ.copy()
    env["NODE_TIER"] = NODE_TIER

    proc = subprocess.run(
        [
            sys.executable,
            worker_path,
            "--memory-bytes",
            str(memory_bytes),
            "--seed",
            str(seed),
            "--touch-rounds",
            str(touch_rounds),
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )

    elapsed_s = time.perf_counter() - start
    elapsed_ms = elapsed_s * 1000

    stdout_text = proc.stdout.strip()
    worker_output = json.loads(stdout_text) if stdout_text else {}

    # Use elapsed time as both task_clock and cpu_clock
    return elapsed_ms, elapsed_ms, worker_output


def run_perf_chunk(memory_bytes, seed, touch_rounds):
    worker_path = os.path.join(os.path.dirname(__file__), "workload_worker.py")

    cmd = [
        "perf",
        "stat",
        "-x",
        ";",
        "-e",
        "task-clock,cpu-clock",
        sys.executable,
        worker_path,
        "--memory-bytes",
        str(memory_bytes),
        "--seed",
        str(seed),
        "--touch-rounds",
        str(touch_rounds),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    task_clock_ms = parse_perf_time_ms(proc.stderr, "task-clock")
    cpu_clock_ms = parse_perf_time_ms(proc.stderr, "cpu-clock")

    stdout_text = proc.stdout.strip()
    worker_output = json.loads(stdout_text) if stdout_text else {}

    return task_clock_ms, cpu_clock_ms, worker_output


def sample_system_metrics(stop_event, interval_s=0.1):
    samples = []

    while not stop_event.is_set():
        samples.append(
            {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
            }
        )
        time.sleep(interval_s)

    return samples


async def execute_task(task: Task):
    if task.task_type != "cpu_mem_burn":
        raise ValueError(f"Unsupported task_type: {task.task_type}")

    target_cpu_ms = float(task.cpu_time_target_ms)
    memory_bytes = int(task.memory_bytes)
    touch_rounds = int(task.payload.get("touch_rounds", 4))
    base_seed = int(task.payload.get("seed", 0))

    total_task_clock_ms = 0.0
    total_cpu_clock_ms = 0.0
    chunks = 0
    last_output = None

    started = time.perf_counter()
    stop_event = threading.Event()
    metrics_samples = []

    append_execution_log(
        task.task_id,
        "processing",
        {
            "target_cpu_ms": target_cpu_ms,
            "memory_bytes": memory_bytes,
            "touch_rounds": touch_rounds,
        },
    )

    def sampler():
        nonlocal metrics_samples
        metrics_samples = sample_system_metrics(stop_event)

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()

    while total_task_clock_ms < target_cpu_ms:
        chunk_seed = base_seed + chunks

        task_clock_ms, cpu_clock_ms, worker_output = await asyncio.to_thread(
            run_chunk_timed,
            memory_bytes,
            chunk_seed,
            touch_rounds,
        )

        total_task_clock_ms += task_clock_ms
        total_cpu_clock_ms += cpu_clock_ms
        chunks += 1
        last_output = worker_output

    stop_event.set()
    sampler_thread.join(timeout=1.0)

    execution_time = time.perf_counter() - started
    cpu_samples = [sample["cpu_percent"] for sample in metrics_samples]
    mem_samples = [sample["memory_percent"] for sample in metrics_samples]

    result_payload = {
        "task_type": task.task_type,
        "executor_node": NODE_ID,
        "executor_host": socket.gethostname(),
        "executor_pid": os.getpid(),
        "execution_time": execution_time,
        "observed_task_clock_ms": float(total_task_clock_ms),
        "observed_cpu_clock_ms": float(total_cpu_clock_ms),
        "observed_memory_bytes": int(memory_bytes),
        "chunks": int(chunks),
        "psutil_cpu_avg_percent": float(sum(cpu_samples) / len(cpu_samples)) if cpu_samples else None,
        "psutil_cpu_peak_percent": float(max(cpu_samples)) if cpu_samples else None,
        "psutil_mem_avg_percent": float(sum(mem_samples) / len(mem_samples)) if mem_samples else None,
        "psutil_mem_peak_percent": float(max(mem_samples)) if mem_samples else None,
        "psutil_sample_count": int(len(metrics_samples)),
        "output": last_output,
    }

    append_execution_log(task.task_id, "completed", result_payload)

    return result_payload, execution_time


@app.on_event("startup")
async def startup():
    logger.info(f"Edge Node started: {NODE_ID}")
    logger.info(f"Listening on port {NODE_PORT}")
    logger.info(f"Central Gateway: {CENTRAL_IP}:{CENTRAL_PORT}")

    app.state.task_queue = asyncio.Queue()

    for _ in range(MAX_CONCURRENT_TASKS):
        asyncio.create_task(worker_loop())

    asyncio.create_task(heartbeat())


async def worker_loop():
    while True:
        task = await app.state.task_queue.get()
        try:
            await process_task(task)
        finally:
            app.state.task_queue.task_done()


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "cpu_usage": psutil.cpu_percent(interval=None),
        "memory_usage": psutil.virtual_memory().percent,
        "queue_size": app.state.task_queue.qsize(),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/tasks")
async def receive_task(task: Task):
    logger.info(f"Task received: {task.task_id} on {NODE_ID}")

    append_execution_log(
        task.task_id,
        "received",
        {
            "task_type": task.task_type,
            "cpu_time_target_ms": task.cpu_time_target_ms,
            "memory_bytes": task.memory_bytes,
            "payload": task.payload,
        },
    )

    task_runtime[task.task_id] = {
        "queued_at": time.time(),
        "started_at": None,
        "completed_at_ts": None,
    }

    task_results[task.task_id] = {
        "task_id": task.task_id,
        "status": "queued",
        "node_id": NODE_ID,
    }

    await app.state.task_queue.put(task)

    return {
        "task_id": task.task_id,
        "status": "queued",
        "node_id": NODE_ID,
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_results[task_id]


@app.get("/executions")
async def get_executions():
    return {
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "tasks": task_results,
    }


async def process_task(task: Task):
    async with semaphore:
        runtime = task_runtime.setdefault(task.task_id, {})
        runtime["started_at"] = time.time()

        task_results[task.task_id] = {
            "task_id": task.task_id,
            "status": "processing",
            "node_id": NODE_ID,
        }

        try:
            result_payload, exec_time = await execute_task(task)

            completed_ts = time.time()
            queued_at = runtime.get("queued_at", completed_ts)
            latency = completed_ts - queued_at
            runtime["completed_at_ts"] = completed_ts

            task_results[task.task_id] = {
                "task_id": task.task_id,
                "status": "completed",
                "node_id": NODE_ID,
                "latency": latency,
                "execution_time": exec_time,
                "result": result_payload,
            }

            result = TaskResult(
                task_id=task.task_id,
                status="completed",
                result={
                    **result_payload,
                    "latency": latency,
                },
                node_id=NODE_ID,
                completed_at=datetime.now(),
            )

            await submit_result(result)

            logger.info(
                f"Task completed: {task.task_id} | task_clock_ms={result_payload['observed_task_clock_ms']:.3f} | mem={result_payload['observed_memory_bytes']}"
            )

        except Exception as e:
            logger.error(f"Task failed: {task.task_id} | error={e}")

            append_execution_log(
                task.task_id,
                "failed",
                {"error": str(e)},
            )

            task_results[task.task_id] = {
                "task_id": task.task_id,
                "status": "failed",
                "node_id": NODE_ID,
                "error": str(e),
            }


async def submit_result(result: TaskResult):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://{CENTRAL_IP}:{CENTRAL_PORT}/results/{result.task_id}",
                json=result.model_dump(mode="json"),
                timeout=10.0,
            )
        logger.info(f"Result submitted: {result.task_id}")
    except Exception as e:
        logger.error(f"Submit result failed: {e}")


async def heartbeat():
    while True:
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory_percent = psutil.virtual_memory().percent

            status = NodeStatus(
                node_id=NODE_ID,
                status="healthy",
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                tasks_count=app.state.task_queue.qsize(),
                last_heartbeat=datetime.now(),
            )

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"http://{CENTRAL_IP}:{CENTRAL_PORT}/nodes/status",
                    json=status.model_dump(mode="json"),
                    timeout=5.0,
                )

        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")

        await asyncio.sleep(5)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=NODE_PORT,
        log_level="info",
    )
