from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime


class Task(BaseModel):
    task_id: str

    # Tetap dipertahankan untuk optimizer lama
    cpu_demand: float
    memory_demand: float
    compute_cost: float

    task_type: Literal["cpu_mem_burn"] = "cpu_mem_burn"
    cpu_time_target_ms: float
    memory_bytes: int
    payload: Dict[str, Any] = Field(default_factory=dict)

    arrival_time: float = 0.0
    task_size: str = "normal"
    experiment_id: str = "default"


class TaskResult(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    node_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class NodeStatus(BaseModel):
    node_id: str
    status: str
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
