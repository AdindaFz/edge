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
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTRAL_IP, CENTRAL_PORT
from shared.models import Task, TaskResult, NodeStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NODE_ID = os.getenv("NODE_ID", "edge-6")
NODE_PORT = int(os.getenv("NODE_PORT", "8006"))

NODE_RESOURCE_CAPS = {
    "edge-1": {"cpu": 2.0, "mem": 2.0},
    "edge-2": {"cpu": 2.0, "mem": 2.0},
    "edge-3": {"cpu": 2.0, "mem": 2.0},
    "edge-4": {"cpu": 4.0, "mem": 4.0},
    "edge-5": {"cpu": 4.0, "mem": 4.0},
    "edge-6": {"cpu": 4.0, "mem": 4.0},
    "edge-7": {"cpu": 8.0, "mem": 8.0},
    "edge-8": {"cpu": 8.0, "mem": 8.0},
    "edge-9": {"cpu": 8.0, "mem": 8.0},
}


def default_hard_cap(cpu_cap):
    if cpu_cap >= 8:
        return 4
    if cpu_cap >= 4:
        return 3
    return 2


NODE_CAPS = NODE_RESOURCE_CAPS.get(
    NODE_ID,
    {
        "cpu": float(os.cpu_count() or 1),
        "mem": psutil.virtual_memory().total / (1024 ** 3),
    },
)
NODE_CPU_CAP = float(os.getenv("NODE_CPU_CAP", NODE_CAPS["cpu"]))
NODE_MEM_CAP = float(os.getenv("NODE_MEM_CAP", NODE_CAPS["mem"]))
CPU_ADMISSION_THRESHOLD = float(os.getenv("CPU_ADMISSION_THRESHOLD", "0.85"))
MEM_ADMISSION_THRESHOLD = float(os.getenv("MEM_ADMISSION_THRESHOLD", "0.80"))
MAX_CONCURRENT_TASKS = int(
    os.getenv("MAX_CONCURRENT_TASKS", str(default_hard_cap(NODE_CPU_CAP)))
)

app = FastAPI(title=f"Edge Node {NODE_ID}")

task_results = {}
task_runtime = {}
running_task_resources = {}
running_cpu_demand = 0.0
running_memory_demand = 0.0


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
            value = float(raw)
        except ValueError:
            continue

        unit = parts[1].lower() if len(parts) > 1 else "msec"
        if unit in {"ns", "nsec", "nanosecond", "nanoseconds"}:
            return value / 1_000_000.0
        if unit in {"us", "usec", "microsecond", "microseconds"}:
            return value / 1_000.0
        if unit in {"s", "sec", "second", "seconds"}:
            return value * 1_000.0
        return value

    raise RuntimeError(f"Could not parse perf value for {event_name}: {stderr_text}")


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

    append_execution_log(
        task.task_id,
        "processing",
        {
            "target_cpu_ms": target_cpu_ms,
            "memory_bytes": memory_bytes,
            "touch_rounds": touch_rounds,
        },
    )

    while total_task_clock_ms < target_cpu_ms:
        chunk_seed = base_seed + chunks

        task_clock_ms, cpu_clock_ms, worker_output = await asyncio.to_thread(
            run_perf_chunk,
            memory_bytes,
            chunk_seed,
            touch_rounds,
        )

        total_task_clock_ms += task_clock_ms
        total_cpu_clock_ms += cpu_clock_ms
        chunks += 1
        last_output = worker_output

    execution_time = time.perf_counter() - started

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
        "output": last_output,
    }

    append_execution_log(task.task_id, "completed", result_payload)

    return result_payload, execution_time


@app.on_event("startup")
async def startup():
    logger.info(f"Edge Node started: {NODE_ID}")
    logger.info(f"Listening on port {NODE_PORT}")
    logger.info(f"Central Gateway: {CENTRAL_IP}:{CENTRAL_PORT}")
    logger.info(
        "Admission control: "
        f"cpu_cap={NODE_CPU_CAP} mem_cap={NODE_MEM_CAP} "
        f"hard_cap={MAX_CONCURRENT_TASKS} "
        f"cpu_threshold={CPU_ADMISSION_THRESHOLD} "
        f"mem_threshold={MEM_ADMISSION_THRESHOLD}"
    )

    app.state.task_queue = deque()
    app.state.queue_condition = asyncio.Condition()

    asyncio.create_task(dispatcher_loop())
    asyncio.create_task(heartbeat())


def task_demands(task: Task):
    return float(task.cpu_demand), float(task.memory_demand)


def running_count():
    return len(running_task_resources)


def queued_count():
    return len(app.state.task_queue)


def capacity_snapshot():
    return {
        "running_count": running_count(),
        "queue_size": queued_count(),
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
        "node_cpu_cap": NODE_CPU_CAP,
        "node_mem_cap": NODE_MEM_CAP,
        "cpu_admission_threshold": CPU_ADMISSION_THRESHOLD,
        "mem_admission_threshold": MEM_ADMISSION_THRESHOLD,
        "running_cpu_demand": running_cpu_demand,
        "running_memory_demand": running_memory_demand,
        "available_cpu_budget": max(
            0.0,
            (NODE_CPU_CAP * CPU_ADMISSION_THRESHOLD) - running_cpu_demand,
        ),
        "available_memory_budget": max(
            0.0,
            (NODE_MEM_CAP * MEM_ADMISSION_THRESHOLD) - running_memory_demand,
        ),
    }


def can_start_task(task: Task):
    cpu_demand, memory_demand = task_demands(task)

    if running_count() >= MAX_CONCURRENT_TASKS:
        return False

    if running_count() == 0:
        return memory_demand <= NODE_MEM_CAP * 0.95

    projected_cpu = running_cpu_demand + cpu_demand
    projected_memory = running_memory_demand + memory_demand

    return (
        projected_cpu <= NODE_CPU_CAP * CPU_ADMISSION_THRESHOLD
        and projected_memory <= NODE_MEM_CAP * MEM_ADMISSION_THRESHOLD
    )


def find_startable_task_index():
    for index, task in enumerate(app.state.task_queue):
        if can_start_task(task):
            return index
    return None


def reserve_task_resources(task: Task):
    global running_cpu_demand, running_memory_demand

    cpu_demand, memory_demand = task_demands(task)
    running_task_resources[task.task_id] = {
        "cpu_demand": cpu_demand,
        "memory_demand": memory_demand,
    }
    running_cpu_demand += cpu_demand
    running_memory_demand += memory_demand


def release_task_resources(task_id: str):
    global running_cpu_demand, running_memory_demand

    resources = running_task_resources.pop(task_id, None)
    if resources is None:
        return

    running_cpu_demand = max(
        0.0,
        running_cpu_demand - float(resources.get("cpu_demand", 0.0)),
    )
    running_memory_demand = max(
        0.0,
        running_memory_demand - float(resources.get("memory_demand", 0.0)),
    )


async def notify_dispatcher():
    async with app.state.queue_condition:
        app.state.queue_condition.notify_all()


async def dispatcher_loop():
    while True:
        async with app.state.queue_condition:
            while True:
                task_index = find_startable_task_index()
                if task_index is not None:
                    task = app.state.task_queue[task_index]
                    del app.state.task_queue[task_index]
                    reserve_task_resources(task)
                    break

                await app.state.queue_condition.wait()

        asyncio.create_task(process_task(task))


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "cpu_usage": psutil.cpu_percent(interval=None),
        "memory_usage": psutil.virtual_memory().percent,
        **capacity_snapshot(),
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
        "admission": capacity_snapshot(),
    }

    async with app.state.queue_condition:
        app.state.task_queue.append(task)
        app.state.queue_condition.notify_all()

    return {
        "task_id": task.task_id,
        "status": "queued",
        "node_id": NODE_ID,
        "admission": capacity_snapshot(),
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
        "admission": capacity_snapshot(),
        "running_tasks": running_task_resources,
    }


async def process_task(task: Task):
    runtime = task_runtime.setdefault(task.task_id, {})
    runtime["started_at"] = time.time()

    task_results[task.task_id] = {
        "task_id": task.task_id,
        "status": "processing",
        "node_id": NODE_ID,
        "admission": capacity_snapshot(),
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

        result = TaskResult(
            task_id=task.task_id,
            status="failed",
            result=None,
            error=str(e),
            node_id=NODE_ID,
            completed_at=datetime.now(),
        )
        await submit_result(result)

    finally:
        release_task_resources(task.task_id)
        await notify_dispatcher()


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
                tasks_count=queued_count() + running_count(),
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
