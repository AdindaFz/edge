# shared/models.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class Task(BaseModel):
    task_id: str
    name: str
    data: Dict[str, Any]
    priority: int = 1
    created_at: datetime = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_001",
                "name": "image_processing",
                "data": {"image_url": "http://example.com/image.jpg"},
                "priority": 1
            }
        }

class TaskResult(BaseModel):
    task_id: str
    status: str  # "pending", "processing", "completed", "failed"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    node_id: Optional[str] = None
    completed_at: Optional[datetime] = None

class NodeStatus(BaseModel):
    node_id: str
    status: str  # "healthy", "busy", "unhealthy"
    cpu_usage: float
    memory_usage: float
    tasks_count: int
    last_heartbeat: datetime

class SystemMetrics(BaseModel):
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    active_nodes: int
    avg_processing_time: float
    timestamp: datetime
