# central/gateway.py
from fastapi import Body, FastAPI, HTTPException
import uvicorn
import asyncio
import glob
import json
from datetime import datetime
from typing import Dict
import httpx
import logging
import sys
import os
import random
from fastapi.responses import FileResponse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTRAL_IP, CENTRAL_PORT, EDGE_NODES
from shared.models import Task, TaskResult, NodeStatus
from central.scheduler import select_node
from central.node_resources import NODE_RESOURCES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Edge Computing Central Gateway")

# In-memory task store
tasks_db: Dict[str, TaskResult] = {}
node_status_db: Dict[str, NodeStatus] = {}
experiment_status = {
    "run_id": None,
    "phase": "idle",
    "message": "No experiment is running",
    "updated_at": None,
}
experiment_cpu_stats = {
    "random_run": {"sum": 0.0, "count": 0, "peak": 0.0},
    "optimized_run": {"sum": 0.0, "count": 0, "peak": 0.0},
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "runs")
RUN_LOG_DIR = os.path.join(PROJECT_ROOT, "outputs", "logs")
latest_run_cache = {"path": None, "mtime": None, "payload": None}
experiment_launch_task = None
experiment_process = None

# Scheduler
SCHEDULER_MODE = "heuristic"


def ordered_node_ids():
    def node_number(node_id: str):
        try:
            return int(node_id.split("-")[-1])
        except (TypeError, ValueError):
            return 999

    return sorted(EDGE_NODES.keys(), key=node_number)


def weighted_live_cpu():
    now = datetime.now()
    weighted_sum = 0.0
    total_capacity = 0.0

    for node_id, status in node_status_db.items():
        heartbeat = status.last_heartbeat
        if heartbeat.tzinfo is not None:
            heartbeat = heartbeat.replace(tzinfo=None)
        if (now - heartbeat).total_seconds() > 15:
            continue

        capacity = float(NODE_RESOURCES.get(node_id, {}).get("cpu", 1.0))
        weighted_sum += float(status.cpu_usage) * capacity
        total_capacity += capacity

    return weighted_sum / total_capacity if total_capacity else 0.0


def reset_experiment_cpu_stats():
    for stats in experiment_cpu_stats.values():
        stats.update(sum=0.0, count=0, peak=0.0)


def record_experiment_cpu_sample():
    phase = experiment_status.get("phase")
    if phase not in experiment_cpu_stats:
        return

    value = weighted_live_cpu()
    stats = experiment_cpu_stats[phase]
    stats["sum"] += value
    stats["count"] += 1
    stats["peak"] = max(stats["peak"], value)


def experiment_cpu_snapshot():
    snapshot = {}
    for phase, stats in experiment_cpu_stats.items():
        snapshot[phase] = {
            "average": stats["sum"] / stats["count"] if stats["count"] else None,
            "peak": stats["peak"] if stats["count"] else None,
            "samples": stats["count"],
        }
    return {"live_weighted": weighted_live_cpu(), "phases": snapshot}


async def experiment_cpu_sampler():
    while True:
        record_experiment_cpu_sample()
        await asyncio.sleep(5)


def dashboard_experiment_running():
    return experiment_launch_task is not None and not experiment_launch_task.done()


async def run_dashboard_experiment():
    global experiment_process

    os.makedirs(RUN_LOG_DIR, exist_ok=True)
    launched_at = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(RUN_LOG_DIR, f"main_{launched_at}.log")
    experiment_status.update(
        run_id=None,
        phase="idle",
        message="Starting main.py from dashboard",
        updated_at=datetime.now().isoformat(),
    )

    try:
        with open(log_path, "ab") as log_file:
            experiment_process = await asyncio.create_subprocess_exec(
                sys.executable,
                os.path.join(PROJECT_ROOT, "main.py"),
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
            )
            return_code = await experiment_process.wait()

        if return_code != 0:
            experiment_status.update(
                phase="failed",
                message=f"main.py exited with code {return_code}. See {log_path}",
                updated_at=datetime.now().isoformat(),
            )
            logger.error("Dashboard experiment failed with code %s: %s", return_code, log_path)
        else:
            logger.info("Dashboard experiment completed: %s", log_path)
    except Exception:
        experiment_status.update(
            phase="failed",
            message="Could not start main.py. Check gateway logs.",
            updated_at=datetime.now().isoformat(),
        )
        logger.exception("Could not run dashboard experiment")
    finally:
        experiment_process = None


def task_status_counts():
    counts = {
        "total": len(tasks_db),
        "pending": 0,
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }

    for task in tasks_db.values():
        status = getattr(task, "status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    return counts

# Serve dashboard HTML
@app.get("/")
async def root():
    dashboard_path = os.path.join(os.path.dirname(__file__), "web", "dashboard.html")
    return FileResponse(
        dashboard_path,
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )

@app.on_event("startup")
async def startup():
    logger.info("🚀 Central Gateway Started")
    logger.info(f"Listening on {CENTRAL_IP}:{CENTRAL_PORT}")
    asyncio.create_task(experiment_cpu_sampler())

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/experiment/status")
async def get_experiment_status():
    return {
        **experiment_status,
        "process_running": dashboard_experiment_running(),
        "cpu": experiment_cpu_snapshot(),
    }


@app.post("/experiment/run", status_code=202)
async def start_experiment():
    global experiment_launch_task

    if dashboard_experiment_running():
        raise HTTPException(status_code=409, detail="An experiment is already running")

    experiment_status.update(
        run_id=None,
        phase="idle",
        message="Experiment launch requested",
        updated_at=datetime.now().isoformat(),
    )
    experiment_launch_task = asyncio.create_task(run_dashboard_experiment())
    return {
        "status": "accepted",
        "message": "main.py is starting in the background",
    }


@app.post("/experiment/status")
async def update_experiment_status(payload: dict = Body(...)):
    allowed_phases = {"idle", "random_run", "optimization", "optimized_run", "completed", "failed"}
    phase = payload.get("phase")
    if phase not in allowed_phases:
        raise HTTPException(status_code=400, detail=f"Invalid experiment phase: {phase}")

    incoming_run_id = payload.get("run_id")
    previous_phase = experiment_status.get("phase")
    if previous_phase in experiment_cpu_stats and previous_phase != phase:
        record_experiment_cpu_sample()
    if phase == "random_run" and incoming_run_id != experiment_status.get("run_id"):
        tasks_db.clear()
        reset_experiment_cpu_stats()
        logger.info("Task counters reset for new experiment run: %s", incoming_run_id)

    experiment_status.update(
        run_id=incoming_run_id,
        phase=phase,
        message=payload.get("message") or phase.replace("_", " ").title(),
        updated_at=datetime.now().isoformat(),
    )
    if phase in experiment_cpu_stats and phase != previous_phase:
        record_experiment_cpu_sample()
    logger.info(
        "Experiment phase updated: run_id=%s phase=%s",
        experiment_status["run_id"],
        phase,
    )
    return {**experiment_status, "cpu": experiment_cpu_snapshot()}


def load_latest_run():
    paths = glob.glob(os.path.join(RUN_OUTPUT_DIR, "run_*.json"))
    if not paths:
        return None

    path = max(paths, key=os.path.getmtime)
    mtime = os.path.getmtime(path)
    if latest_run_cache["path"] == path and latest_run_cache["mtime"] == mtime:
        return latest_run_cache["payload"]

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return latest_run_cache["payload"]

    latest_run_cache.update(path=path, mtime=mtime, payload=payload)
    return payload


def latest_artifact_path(artifact):
    payload = load_latest_run()
    if not payload:
        return None

    config_key = {
        "convergence": "plot_path",
        "comparison": "comparison_plot_path",
    }.get(artifact)
    if not config_key:
        return None

    path = payload.get("config", {}).get(config_key)
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)

    resolved = os.path.realpath(path)
    output_root = os.path.realpath(RUN_OUTPUT_DIR) + os.sep
    if not resolved.startswith(output_root) or not os.path.isfile(resolved):
        return None
    return resolved


@app.get("/experiment/results/latest")
async def get_latest_experiment_results():
    payload = load_latest_run()
    if not payload:
        raise HTTPException(status_code=404, detail="No completed run available")

    random_metrics = payload.get("metrics", {}).get("random") or {}
    tabu_metrics = payload.get("metrics", {}).get("tabu_diffusion") or {}
    convergence = payload.get("convergence", {}).get("tabu_diffusion") or {}
    metric_specs = [
        ("Real avg latency", "real_avg_latency"),
        ("Real total latency", "real_total_latency"),
        ("Estimated energy J", "estimated_real_energy_j"),
        ("Base energy J", "estimated_base_energy_j"),
        ("High-power penalty J", "estimated_high_power_penalty_j"),
    ]

    return {
        "run_id": payload.get("run_id"),
        "captured_at": payload.get("captured_at"),
        "n_tasks": payload.get("config", {}).get("n_tasks"),
        "comparison_rows": [
            {"metric": label, "random": random_metrics.get(key), "tabu": tabu_metrics.get(key)}
            for label, key in metric_specs
        ],
        "convergence": {
            "available": convergence.get("available", False),
            "iterations": convergence.get("iterations"),
            "initial_objective": convergence.get("initial_objective"),
            "final_objective": convergence.get("final_objective"),
            "best_objective": convergence.get("best_objective"),
            "best_iteration": convergence.get("best_iteration"),
            "improvement_pct": convergence.get("improvement_pct"),
        },
        "images": {
            "convergence": f"/experiment/results/latest/convergence?v={payload.get("run_id")}",
            "comparison": f"/experiment/results/latest/comparison?v={payload.get("run_id")}",
        },
    }


@app.get("/experiment/results/latest/{artifact}")
async def get_latest_experiment_artifact(artifact: str):
    path = latest_artifact_path(artifact)
    if not path:
        raise HTTPException(status_code=404, detail="Run artifact not found")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/tasks")
async def submit_task(task: Task):
    """Submit task dari client ke edge nodes"""
    #task.created_at = datetime.now()
    task_id = task.task_id
    
    # Store task
    tasks_db[task_id] = TaskResult(
        task_id=task_id,
        status="pending",
        result=None
    )
    logger.info(f"📝 Task submitted: {task_id}")
    
    # Distribute ke edge node
    # asyncio.create_task(distribute_task(task))
    await distribute_task(task)
    return {
        "task_id": task_id,
        "status": "accepted",
        "message": "Task will be processed by edge nodes"
    }


@app.get("/tasks")
async def get_tasks():
    """Get all task statuses for dashboard polling."""
    return {
        "tasks": tasks_db,
        "counts": task_status_counts(),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get status dari task"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks_db[task_id]

@app.get("/nodes/status")
async def get_nodes_status():
    """Get status dari semua edge nodes"""
    ordered_nodes = {}
    for node_id in ordered_node_ids():
        status = node_status_db.get(node_id)
        ordered_nodes[node_id] = status

    return {
        "nodes": ordered_nodes,
        "node_order": ordered_node_ids(),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/nodes/status")
async def update_node_status(status: NodeStatus):
    """Edge node send heartbeat"""
    node_id = status.node_id
    node_status_db[node_id] = status
    logger.info(f"💓 Heartbeat from {node_id}: CPU {status.cpu_usage:.1f}%, Memory {status.memory_usage:.1f}%")
    return {"status": "received"}

@app.post("/results/{task_id}")
async def submit_result(task_id: str, result: TaskResult):
    """Edge node submit hasil task"""
    tasks_db[task_id] = result
    logger.info(f"✅ Task updated: {task_id} ({result.status})")
    
    return {"status": "received"}

async def distribute_task(task: Task):
    """Distribute task ke 1 node (scheduler)"""

    logger.info(f"🚀 Distribute {task.task_id}")
    logger.info(f"DEBUG nodes_status: {node_status_db}")

    # 🔥 pilih node dari scheduler
    node_id = select_node(task, node_status_db, mode=SCHEDULER_MODE)

    # 🔥 fallback kalau belum ada heartbeat
    if node_id is None:
        import random
        node_id = random.choice(list(EDGE_NODES.keys()))
        logger.warning("⚠️ Fallback to random node")

    node_config = EDGE_NODES[node_id]
    node_url = f"http://{node_config['ip']}:{node_config['port']}"

    try:
        logger.info(f"➡️ Sending to {node_id}: {node_url}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{node_url}/tasks",
                json=task.model_dump(mode='json'),
                timeout=5.0
            )

        tasks_db[task.task_id] = TaskResult(
            task_id=task.task_id,
            status="queued",
            result=None,
            node_id=node_id,
        )
        logger.info(f"🎯 Task {task.task_id} → {node_id}")

    except Exception as e:
        logger.error(f"❌ Failed to send task to {node_id}: {e}")
        tasks_db[task.task_id] = TaskResult(
            task_id=task.task_id,
            status="failed",
            result=None,
            error=str(e),
            node_id=node_id,
            completed_at=datetime.now(),
        )

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=CENTRAL_PORT,
        log_level="info"
    )
