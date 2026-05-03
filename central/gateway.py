# central/gateway.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from datetime import datetime
from typing import Dict
import httpx
import logging
import sys
import os
import random
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTRAL_IP, CENTRAL_PORT, EDGE_NODES
from shared.models import Task, TaskResult, NodeStatus
from fastapi.responses import FileResponse, HTMLResponse
from central.scheduler import select_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Edge Computing Central Gateway")

# In-memory task store
tasks_db: Dict[str, TaskResult] = {}
node_status_db: Dict[str, NodeStatus] = {}

# Scheduler
SCHEDULER_MODE = "heuristic"   # ganti nanti jadi "heuristic"

# Serve dashboard HTML
@app.get("/")
async def root():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    return FileResponse(dashboard_path, media_type="text/html")

@app.on_event("startup")
async def startup():
    logger.info("🚀 Central Gateway Started")
    logger.info(f"Listening on {CENTRAL_IP}:{CENTRAL_PORT}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/tasks")
async def submit_task(task: Task):
    """Submit task dari client ke edge nodes"""
    #task.created_at = datetime.now()
    print("🔥 MASUK submit_task")
    task_id = task.task_id
    
    # Store task
    tasks_db[task_id] = TaskResult(
        task_id=task_id,
        status="pending",
        result=None
    )
    print("🔥 MASUK submit_task")
    
    logger.info(f"📝 Task submitted: {task_id}")
    
    # Distribute ke edge node
    # asyncio.create_task(distribute_task(task))
    print("🚀 MAU DISTRIBUTE")
    await distribute_task(task)
    return {
        "task_id": task_id,
        "status": "accepted",
        "message": "Task will be processed by edge nodes"
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
    logger.info(f"DEBUG nodes_status: {node_status_db}")
    return {
        "nodes": node_status_db,
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
    if task_id in tasks_db:
        tasks_db[task_id] = result
        logger.info(f"✅ Task completed: {task_id}")
    
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

        logger.info(f"🎯 Task {task.task_id} → {node_id}")

    except Exception as e:
        logger.error(f"❌ Failed to send task to {node_id}: {e}")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=CENTRAL_PORT,
        log_level="info"
    )
