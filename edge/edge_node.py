# edge/edge_node.py
from fastapi import FastAPI
import uvicorn
from datetime import datetime
import asyncio
import httpx
import psutil
import logging
import os
import sys
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CENTRAL_IP, CENTRAL_PORT
from shared.models import Task, TaskResult, NodeStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get node ID dari environment variable
NODE_ID = os.getenv("NODE_ID", "edge-node-1")
NODE_PORT = int(os.getenv("NODE_PORT", "8001"))

app = FastAPI(title=f"Edge Node {NODE_ID}")
task_queue = asyncio.Queue()

@app.on_event("startup")
async def startup():
    logger.info(f"🖥️ Edge Node {NODE_ID} Started")
    logger.info(f"Listening on port {NODE_PORT}")
    logger.info(f"Central Gateway: {CENTRAL_IP}:{CENTRAL_PORT}")
    
    # Start heartbeat & task processing
    asyncio.create_task(heartbeat())
    asyncio.create_task(process_tasks())

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "cpu_usage": cpu_percent,
        "memory_usage": memory_percent,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/tasks")
async def receive_task(task: Task):
    """Terima task dari central gateway"""
    logger.info(f"📥 Task received: {task.task_id}")
    await task_queue.put(task)
    
    return {
        "task_id": task.task_id,
        "status": "queued",
        "node_id": NODE_ID
    }

async def process_tasks():
    """Process tasks dari queue"""
    while True:
        try:
            task = await task_queue.get()
            logger.info(f"⚙️ Processing task: {task.task_id}")
            
            # Simulate processing
            await asyncio.sleep(2)
            
            # Submit result ke central
            result = TaskResult(
                task_id=task.task_id,
                status="completed",
                result={"processed_data": f"Processed by {NODE_ID}"},
                node_id=NODE_ID,
                completed_at=datetime.now()
            )
            
            await submit_result(result)
            logger.info(f"✅ Task completed: {task.task_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing task: {e}")
            await asyncio.sleep(1)

async def submit_result(result: TaskResult):
    """Submit hasil task ke central gateway"""
    try:
        async with httpx.AsyncClient() as client:
            # Convert model to dict untuk JSON serialization
            result_dict = result.model_dump(mode='json')
            
            await client.post(
                f"http://{CENTRAL_IP}:{CENTRAL_PORT}/results/{result.task_id}",
                json=result_dict,
                timeout=10.0
            )
            logger.info(f"📤 Result submitted for {result.task_id}")
    except Exception as e:
        logger.error(f"Failed to submit result: {e}")

async def heartbeat():
    """Send heartbeat ke central gateway"""
    while True:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            tasks_count = task_queue.qsize()
            
            status = NodeStatus(
                node_id=NODE_ID,
                status="healthy",
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                tasks_count=tasks_count,
                last_heartbeat=datetime.now()
            )
            
            async with httpx.AsyncClient() as client:
                # Convert model to dict untuk JSON serialization
                status_dict = status.model_dump(mode='json')
                
                await client.post(
                    f"http://{CENTRAL_IP}:{CENTRAL_PORT}/nodes/status",
                    json=status_dict,
                    timeout=5.0
                )
            
            logger.info(f"💓 Heartbeat sent - CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%")
            
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
        
        await asyncio.sleep(10)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=NODE_PORT,
        log_level="info"
    )
