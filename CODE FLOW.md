# 📚 DOKUMENTASI TEKNIS LENGKAP DENGAN CODE FLOW

## Daftar Isi
1. [Gambaran Arsitektur](#gambaran-arsitektur)
2. [Alur Sistem Keseluruhan](#alur-sistem-keseluruhan)
3. [Code Flow Detail - Central Gateway](#code-flow-detail---central-gateway)
4. [Code Flow Detail - Edge Node](#code-flow-detail---edge-node)
5. [Alur Komunikasi HTTP](#alur-komunikasi-http)
6. [Data Models](#data-models)
7. [Execution Time Calculation](#execution-time-calculation)

---

## Gambaran Arsitektur

### Diagram Sistem Keseluruhan

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT APPLICATION                           │
│                    (Submit Task & Polling Result)                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                   POST /tasks (JSON)
                             │
                             ▼
        ┌────────────────────────────────────┐
        │   CENTRAL GATEWAY (10.33.102.106)  │
        │        Port: 8000                  │
        │                                    │
        │  ┌──────────────────────────────┐ │
        │  │  tasks_db: Dict[task_id]     │ │
        │  │  node_status_db: Dict[node]  │ │
        │  └──────────────────────────────┘ │
        │                                    │
        │  Endpoints:                        │
        │  - POST /tasks                    │
        │  - GET /tasks/{id}                │
        │  - POST /nodes/status (heartbeat) │
        │  - GET /nodes/status              │
        │  - POST /results/{id}             │
        │                                    │
        └───────────┬──────────────────────┬─┘
                    │                      │
        ┌───────────┴─────┬─────────┬─────┴──────┐
        │                 │         │            │
    Broadcast Task to All Nodes (Async)
        │                 │         │            │
        ▼                 ▼         ▼            ▼
    ┌────────┐        ┌────────┐┌────────┐   ┌────────┐
    │Node 1  │        │Node 2  ││Node 3  │   │Node 9  │
    │:8001   │        │:8002   ││:8003   │...│:8009   │
    └────────┘        └────────┘└────────┘   └────────┘
    [Parallel Processing on Each Node]
```

---

## Alur Sistem Keseluruhan

### Timeline Sequence

```
TIME    CLIENT          CENTRAL         EDGE-1         EDGE-2  ... EDGE-9
────────────────────────────────────────────────────────────────────────
T0:00   │                │                │              │            │
        ├─ POST /tasks   │                │              │            │
        │  (task_001)    │                │              │            │
        │                ├─ Store in      │              │            │
        │                │  tasks_db      │              │            │
        │                │  (status:      │              │            │
        │                │   pending)     │              │            │
        │                │                │              │            │
T0:05   │                ├─ Async         │              │            │
        │                │  broadcast     │              │            │
        │                │  task to all   │              │            │
        │                │  nodes...      │              │            │
        │                │                ├─ POST /tasks │              │
        │                │                │  (receive)   │              │
        │                │                ├─ add to      │              │
        │                │                │  queue       ├─ POST /tasks│
        │                │                │              │ (receive)   │
        │                │                │              ├─ add to     │
        │                │                │              │  queue      │
        │                │                │              │         ├──┤
        │                │                │              │         │  │
T0:10   │  Every 10s     │                │              │         │  │
        │  GET /tasks    │                ├─ Process     ├─ Process│  │
        │  /task_001 ◄───┼─ Check status  │  task        │ task    │  │
        │  (still pending│  (may still be │  [simulate   │ [simul  │  │
        │  or completed) │   processing)  │   execution] │ exec]   │  │
        │                │                │              │         │  │
T0:15   │                │                ├─ Result done ├─ Result │  │
        │                │                │  POST        │ done    │  │
        │                │                │  /results    │ POST    │  │
        │                │                │  /task_001   │ /resul  │  │
        │                │    (Result)    │              │ ts      │  │
        │                ├─ Update        │              │  /task  │  │
        │                │  tasks_db      │              │  _001   │  │
        │                │  (status:      │              │         │  │
        │                │   completed)   │              │         │  │
        │                │                │              │         │  │
T0:20   │  GET /tasks    │                │              │         │  │
        │  /task_001 ◄───┼─ Return result │              │         │  │
        │  (completed)   │  from db       │              │         │  │
        │                │                │              │         │  │
        └────────────────────────────────────────────────────────────┘
```

### Heartbeat Mechanism (Parallel)

```
Every 10 seconds:
┌─────────────────────────────────┐
│  EDGE-1 Collect Metrics         │
│  ├─ CPU: 45.2%                  │
│  ├─ Memory: 62.8%               │
│  └─ Queue: 3 tasks              │
└────────────┬────────────────────┘
             ├─ POST /nodes/status
             │  to central
             └─ Update node_status_db

┌─────────────────────────────────┐
│  EDGE-2 Collect Metrics         │
│  ├─ CPU: 38.5%                  │
│  ├─ Memory: 71.2%               │
│  └─ Queue: 2 tasks              │
└────────────┬────────────────────┘
             ├─ POST /nodes/status
             │  to central
             └─ Update node_status_db

(All nodes in parallel)
```

---

## Code Flow Detail - Central Gateway

### File: `central/gateway.py`

#### 1. Initialization & Setup (Lines 1-25)

```python
# LINE 1-20: Import section
from fastapi import FastAPI
import uvicorn, asyncio, httpx, logging
from config import CENTRAL_IP, CENTRAL_PORT, EDGE_NODES
from shared.models import Task, TaskResult, NodeStatus

# LINE 22-23: Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LINE 25: Initialize FastAPI app
app = FastAPI(title="Edge Computing Central Gateway")

# LINE 28-29: In-memory databases
tasks_db: Dict[str, TaskResult] = {}        # Stores all tasks
node_status_db: Dict[str, NodeStatus] = {}  # Stores node status
```

#### 2. Startup Event (Lines 37-40)

```python
@app.on_event("startup")
async def startup():
    logger.info("🚀 Central Gateway Started")
    logger.info(f"Listening on {CENTRAL_IP}:{CENTRAL_PORT}")
```

#### 3. Task Submission Endpoint (Lines 49-71)

**Kode Asli:**
```python
@app.post("/tasks")
async def submit_task(task: Task):
    """Submit task dari client ke edge nodes"""
    task.created_at = datetime.now()
    task_id = task.task_id
    
    # Store task
    tasks_db[task_id] = TaskResult(
        task_id=task_id,
        status="pending",
        result=None
    )
    
    logger.info(f"📝 Task submitted: {task_id}")
    
    # Distribute ke edge node
    asyncio.create_task(distribute_task(task))
    
    return {
        "task_id": task_id,
        "status": "accepted",
        "message": "Task will be processed by edge nodes"
    }
```

**Flow Diagram:**
```
CLIENT
  │
  ├─ POST /tasks dengan payload
  │  {task_id: "task_001", name: "...", data: {...}}
  │
  ▼
CENTRAL GATEWAY submit_task()
  │
  ├─ LINE 52: Set timestamp
  │  └─ task.created_at = datetime.now()
  │
  ├─ LINE 53: Extract task ID
  │  └─ task_id = "task_001"
  │
  ├─ LINE 56-60: Store in database
  │  └─ tasks_db["task_001"] = TaskResult(
  │     task_id="task_001",
  │     status="pending",    ◄── Status: PENDING
  │     result=None
  │  )
  │
  ├─ LINE 62: Log
  │  └─ logger.info("📝 Task submitted: task_001")
  │
  ├─ LINE 65: Create async background task (NON-BLOCKING!)
  │  └─ asyncio.create_task(distribute_task(task))
  │     ↑ Returns immediately, distribute happens in background
  │
  └─ LINE 67-71: Return response
     └─ Return {
         task_id: "task_001",
         status: "accepted",
         message: "Task will be processed by edge nodes"
        }
```

#### 4. Task Distribution (Lines 106-119)

**Kode Asli:**
```python
async def distribute_task(task: Task):
    """Distribute task ke edge nodes"""
    async with httpx.AsyncClient() as client:
        for node_name, node_config in EDGE_NODES.items():
            try:
                node_url = f"http://{node_config['ip']}:{node_config['port']}"
                await client.post(
                    f"{node_url}/tasks",
                    json=task.model_dump(mode='json'),
                    timeout=5.0
                )
                logger.info(f"📤 Task {task.task_id} sent to {node_name}")
            except Exception as e:
                logger.error(f"❌ Failed to send task to {node_name}: {e}")
```

**Flow Diagram:**
```
distribute_task(task) [Background]
  │
  ├─ LINE 108: Create HTTP async client
  │  └─ async with httpx.AsyncClient() as client:
  │
  └─ LINE 109: Loop semua nodes dari config
     │
     └─ For each node:
        │  (Contoh: "edge-1")
        │
        ├─ LINE 111: Build URL
        │  └─ node_url = "http://10.33.102.107:8001"
        │
        ├─ LINE 112-116: Send POST request (Async!)
        │  └─ await client.post(
        │     "http://10.33.102.107:8001/tasks",
        │     json={task_001 data},  ◄── Convert task to JSON
        │     timeout=5.0
        │  )
        │  ↓ (If success)
        │  ├─ NODE receives on /tasks endpoint
        │  └─ Add to task_queue
        │
        └─ LINE 117: Log success
           └─ logger.info("📤 Task sent to edge-1")
           
        (If timeout or error)
           └─ LINE 119: Log error
              └─ logger.error("Failed to send task to edge-1")

Hasil: Semua 9 nodes menerima task secara paralel!
```

**Config Reference:**
```python
# config.py
EDGE_NODES = {
    "edge-1": {"ip": "10.33.102.107", "port": 8001},
    "edge-2": {"ip": "10.33.102.108", "port": 8002},
    "edge-3": {"ip": "10.33.102.109", "port": 8003},
    ...
    "edge-9": {"ip": "10.33.102.115", "port": 8009},
}
```

#### 5. Get Task Status (Lines 73-79)

**Kode Asli:**
```python
@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get status dari task"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks_db[task_id]
```

**Flow:**
```
CLIENT GET /tasks/task_001
  │
  ▼
CENTRAL get_task_status("task_001")
  │
  ├─ LINE 76-77: Check if exists
  │  └─ if "task_001" not in tasks_db:
  │     └─ Return 404 error
  │
  └─ LINE 79: Return task
     └─ return tasks_db["task_001"]
        └─ Return: {
           task_id: "task_001",
           status: "pending" OR "completed",  ◄── Status depends on processing
           result: null OR {...},
           node_id: null OR "edge-1",
           completed_at: null OR "2026-04-19T..."
        }
```

#### 6. Receive Result from Node (Lines 97-104)

**Kode Asli:**
```python
@app.post("/results/{task_id}")
async def submit_result(task_id: str, result: TaskResult):
    """Edge node submit hasil task"""
    if task_id in tasks_db:
        tasks_db[task_id] = result
        logger.info(f"✅ Task completed: {task_id}")
    
    return {"status": "received"}
```

**Flow:**
```
EDGE-1 (Background)
  │
  └─ Task processing completed
     │
     └─ Create result object:
        result = TaskResult(
          task_id="task_001",
          status="completed",
          result={
            "processed_data": "Processed by edge-1",
            "execution_time": 1.234
          },
          node_id="edge-1",
          completed_at="2026-04-19T10:30:45Z"
        )
        │
        └─ POST http://10.33.102.106:8000/results/task_001
           with result payload
           │
           ▼
CENTRAL submit_result("task_001", result)
  │
  ├─ LINE 100-101: Check if task exists
  │  └─ if "task_001" in tasks_db:
  │
  ├─ LINE 101: Update task_db
  │  └─ tasks_db["task_001"] = result
  │     └─ Replaces pending entry dengan completed result
  │        OLD: {task_id, status:"pending", result:null, ...}
  │        NEW: {task_id, status:"completed", result:{...}, node_id:"edge-1", ...}
  │
  ├─ LINE 102: Log
  │  └─ logger.info("✅ Task completed: task_001")
  │
  └─ LINE 104: Return
     └─ return {"status": "received"}

CLIENT GET /tasks/task_001
  │
  └─ Get dari tasks_db
     └─ Return completed result dengan data!
```

#### 7. Node Heartbeat Reception (Lines 89-95)

**Kode Asli:**
```python
@app.post("/nodes/status")
async def update_node_status(status: NodeStatus):
    """Edge node send heartbeat"""
    node_id = status.node_id
    node_status_db[node_id] = status
    logger.info(f"💓 Heartbeat from {node_id}: CPU {status.cpu_usage:.1f}%, Memory {status.memory_usage:.1f}%")
    return {"status": "received"}
```

**Flow (Every 10 seconds from each node):**
```
EDGE-1 heartbeat() [Background, every 10s]
  │
  └─ POST /nodes/status
     {
       node_id: "edge-1",
       status: "healthy",
       cpu_usage: 45.2,
       memory_usage: 62.8,
       tasks_count: 3,
       last_heartbeat: "2026-04-19T10:30:50Z"
     }
     │
     ▼
CENTRAL update_node_status(status)
  │
  ├─ LINE 92: Extract node_id
  │  └─ node_id = "edge-1"
  │
  ├─ LINE 93: Store in database
  │  └─ node_status_db["edge-1"] = status object
  │
  ├─ LINE 94: Log
  │  └─ logger.info("💓 Heartbeat from edge-1: CPU 45.2%, Memory 62.8%")
  │
  └─ LINE 95: Return ack
     └─ return {"status": "received"}
```

---

## Code Flow Detail - Edge Node

### File: `edge/edge_node.py`

#### 1. Initialization (Lines 1-27)

```python
# LINE 1-11: Imports
from fastapi import FastAPI
import uvicorn, asyncio, httpx, psutil

# LINE 16: Get config
from config import CENTRAL_IP, CENTRAL_PORT

# LINE 23-24: Get node identity from env variables
NODE_ID = os.getenv("NODE_ID", "edge-node-5")      # Default: "edge-node-5"
NODE_PORT = int(os.getenv("NODE_PORT", "8005"))    # Default: 8005

# LINE 26: Create FastAPI app (per node)
app = FastAPI(title=f"Edge Node {NODE_ID}")  # e.g., "Edge Node edge-1"

# LINE 27: Create async queue untuk task
task_queue = asyncio.Queue()  # FIFO queue, unbounded
```

**Environment Variables:**
```bash
# When starting each node
export NODE_ID="edge-1"    # or edge-2, edge-3, etc
export NODE_PORT="8001"    # or 8002, 8003, etc
python edge/edge_node.py
```

#### 2. Startup Event (Lines 68-76)

```python
@app.on_event("startup")
async def startup():
    logger.info(f"🖥️ Edge Node {NODE_ID} Started")
    logger.info(f"Listening on port {NODE_PORT}")
    logger.info(f"Central Gateway: {CENTRAL_IP}:{CENTRAL_PORT}")
    
    # Start heartbeat & task processing
    asyncio.create_task(heartbeat())          # Line 75
    asyncio.create_task(process_tasks())      # Line 76
```

**Flow:**
```
Node startup
  │
  ├─ Log initialization
  │  └─ "🖥️ Edge Node edge-1 Started"
  │
  ├─ LINE 75: Start heartbeat() [Background, infinite loop]
  │  └─ Runs every 10 seconds until shutdown
  │
  ├─ LINE 76: Start process_tasks() [Background, infinite loop]
  │  └─ Continuously processes queue
  │
  └─ Wait for incoming requests/signals
```

#### 3. Receive Task from Central (Lines 92-102)

**Kode Asli:**
```python
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
```

**Flow:**
```
CENTRAL (background distribute_task)
  │
  └─ POST http://10.33.102.107:8001/tasks
     with task_001 data
     │
     ▼
EDGE-1 receive_task(task_001)
  │
  ├─ LINE 95: Log
  │  └─ logger.info("📥 Task received: task_001")
  │
  ├─ LINE 96: Add to async queue (NON-BLOCKING!)
  │  └─ await task_queue.put(task_001)
  │     └─ Add task to end of queue
  │
  └─ LINE 98-102: Return immediately
     └─ return {
        task_id: "task_001",
        status: "queued",      ◄── Status: QUEUED
        node_id: "edge-1"
       }

NOTE: Task tidak diproses sekarang, hanya di-queue!
      process_tasks() background worker akan menanganinya.
```

#### 4. Process Tasks (Lines 104-130)

**Kode Asli:**
```python
async def process_tasks():
    """Process tasks dari queue"""
    while True:
        try:
            task = await task_queue.get()
            logger.info(f"⚙️ Processing task: {task.task_id}")

            exec_time = await simulate_execution(task)

            # Submit result ke central
            result = TaskResult(
                task_id=task.task_id,
                status="completed",
                result={
                    "processed_data": f"Processed by {NODE_ID}",
                    "execution_time": exec_time
                },
                node_id=NODE_ID,
                completed_at=datetime.now()
            )

            await submit_result(result)
            logger.info(f"✅ Task completed: {task.task_id}")

        except Exception as e:
            logger.error(f"❌ Error processing task: {e}")
            await asyncio.sleep(1)
```

**Flow (Per Task, runs continuously):**
```
process_tasks() [Background, Infinite Loop]
  │
  └─ While True:
     │
     ├─ LINE 108: Get task from queue (wait if empty)
     │  └─ task = await task_queue.get()
     │     └─ Blocks until task available
     │
     ├─ LINE 109: Log
     │  └─ logger.info("⚙️ Processing task: task_001")
     │
     ├─ LINE 111: Execute task
     │  └─ exec_time = await simulate_execution(task)
     │     └─ This takes time (0.1s - 5.0s)
     │     └─ See next section for details
     │
     ├─ LINE 114-123: Build result
     │  └─ result = TaskResult(
     │     task_id="task_001",
     │     status="completed",
     │     result={
     │       "processed_data": "Processed by edge-1",
     │       "execution_time": 1.234
     │     },
     │     node_id="edge-1",
     │     completed_at="2026-04-19T10:30:45Z"
     │  )
     │
     ├─ LINE 125: Send result to central
     │  └─ await submit_result(result)
     │
     ├─ LINE 126: Log completion
     │  └─ logger.info("✅ Task completed: task_001")
     │
     └─ (Loop back to get next task)
        └─ Go back to LINE 108
```

#### 5. Task Execution Simulation (Lines 31-66)

**Kode Asli:**
```python
async def simulate_execution(task: Task):
    """
    Simulate execution berdasarkan resource demand task
    """

    # Ambil dari task (fallback kalau belum ada field)
    cpu_demand = getattr(task, "cpu_demand", 0.1)
    memory_demand = getattr(task, "memory_demand", 0.1)
    compute_cost = getattr(task, "compute_cost", 1000)

    # Normalize supaya nggak terlalu lama
    SCALING_FACTOR = 5e6
    base_time = compute_cost / SCALING_FACTOR

    # CPU load saat ini
    current_cpu = psutil.cpu_percent() / 100.0

    # Queue pressure
    queue_factor = min(task_queue.qsize() * 0.05, 1.0)

    # Random noise (biar realistis)
    noise = random.uniform(0.9, 1.1)

    # Final execution time
    exec_time = base_time * (1 + current_cpu + queue_factor) * noise

    # Batas biar nggak absurd
    exec_time = max(0.1, min(exec_time, 5))

    logger.info(
        f"⏱️ Exec time: {exec_time:.2f}s | CPU load: {current_cpu:.2f} | Queue: {task_queue.qsize()}"
    )

    await asyncio.sleep(exec_time)

    return exec_time
```

**Formula Calculation Flow:**
```
simulate_execution(task)
  │
  ├─ LINE 37-39: Get compute cost
  │  └─ compute_cost = 1000 (default)
  │
  ├─ LINE 42-43: Calculate base time
  │  └─ base_time = 1000 / 5e6 = 0.0002s
  │
  ├─ LINE 46: Get current CPU usage
  │  └─ current_cpu = psutil.cpu_percent() / 100.0
  │     Example: 45.2% → 0.452
  │
  ├─ LINE 49: Calculate queue pressure
  │  └─ queue_factor = min(task_queue.qsize() * 0.05, 1.0)
  │     Example: 10 tasks in queue → 0.5
  │     Example: 20+ tasks → capped at 1.0
  │
  ├─ LINE 52: Add randomness
  │  └─ noise = random.uniform(0.9, 1.1)
  │     Example: 1.05
  │
  ├─ LINE 55: MAIN FORMULA
  │  └─ exec_time = base_time * (1 + current_cpu + queue_factor) * noise
  │     Example: 0.0002 * (1 + 0.452 + 0.5) * 1.05
  │     Example: 0.0002 * 1.952 * 1.05 = 0.000410 seconds
  │
  ├─ LINE 58: Clamp to bounds
  │  └─ exec_time = max(0.1, min(exec_time, 5))
  │     Result: 0.1s (minimum enforcement)
  │
  ├─ LINE 64: Sleep (simulate execution)
  │  └─ await asyncio.sleep(0.1)  ◄── Wait 0.1 seconds
  │
  └─ LINE 66: Return execution time
     └─ return 0.1
```

**Example Scenarios:**

Scenario 1 - Low Load:
```
- compute_cost = 1000
- CPU = 20% → 0.2
- Queue = 0 tasks → 0
- Noise = 1.0

exec_time = 0.0002 * (1 + 0.2 + 0) * 1.0
         = 0.0002 * 1.2 * 1.0
         = 0.00024s
After clamp: 0.1s ◄── Hit minimum
```

Scenario 2 - High Load:
```
- compute_cost = 100000
- CPU = 80% → 0.8
- Queue = 20 tasks → 1.0 (capped)
- Noise = 1.1

exec_time = 0.02 * (1 + 0.8 + 1.0) * 1.1
         = 0.02 * 2.8 * 1.1
         = 0.0616s
After clamp: 0.0616s ◄── Within bounds
```

#### 6. Submit Result to Central (Lines 132-146)

**Kode Asli:**
```python
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
```

**Flow:**
```
[After task execution]
  │
  ├─ Build result object
  │
  └─ submit_result(result) [from process_tasks()]
     │
     ├─ LINE 135: Create HTTP client
     │  └─ async with httpx.AsyncClient() as client:
     │
     ├─ LINE 137: Convert to JSON
     │  └─ result_dict = result.model_dump(mode='json')
     │
     ├─ LINE 139-143: POST to central
     │  └─ await client.post(
     │     "http://10.33.102.106:8000/results/task_001",
     │     json=result_dict,
     │     timeout=10.0
     │  )
     │  └─ Payload:
     │  {
     │    "task_id": "task_001",
     │    "status": "completed",
     │    "result": {
     │      "processed_data": "Processed by edge-1",
     │      "execution_time": 0.1234
     │    },
     │    "node_id": "edge-1",
     │    "completed_at": "2026-04-19T10:30:45Z"
     │  }
     │
     ├─ LINE 144: Log success
     │  └─ logger.info("📤 Result submitted for task_001")
     │
     └─ If error → LINE 146: Log error
        └─ logger.error("Failed to submit result: ...")
```

#### 7. Heartbeat Mechanism (Lines 148-180)

**Kode Asli:**
```python
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
```

**Flow (Parallel to task processing, every 10 seconds):**
```
heartbeat() [Background, Infinite Loop]
  │
  └─ While True:
     │
     ├─ LINE 152: Collect CPU usage
     │  └─ cpu_percent = psutil.cpu_percent(interval=1)
     │     └─ Measure CPU for 1 second
     │     └─ Returns 0-100
     │
     ├─ LINE 153: Collect memory usage
     │  └─ memory_percent = psutil.virtual_memory().percent
     │     └─ Returns percentage used
     │
     ├─ LINE 154: Get queue size
     │  └─ tasks_count = task_queue.qsize()
     │     └─ Count of tasks waiting
     │
     ├─ LINE 156-163: Build status object
     │  └─ status = NodeStatus(
     │     node_id="edge-1",
     │     status="healthy",
     │     cpu_usage=45.2,
     │     memory_usage=62.8,
     │     tasks_count=3,
     │     last_heartbeat="2026-04-19T10:30:50Z"
     │  )
     │
     ├─ LINE 165: Create HTTP client
     │  └─ async with httpx.AsyncClient() as client:
     │
     ├─ LINE 167: Convert to JSON
     │  └─ status_dict = status.model_dump(mode='json')
     │
     ├─ LINE 169-173: POST to central
     │  └─ await client.post(
     │     "http://10.33.102.106:8000/nodes/status",
     │     json=status_dict,
     │     timeout=5.0
     │  )
     │  └─ Central receives on /nodes/status endpoint
     │     └─ Updates node_status_db["edge-1"]
     │
     ├─ LINE 175: Log
     │  └─ logger.info("💓 Heartbeat sent - CPU: 45.2%, Memory: 62.8%")
     │
     ├─ LINE 177-178: If error
     │  └─ logger.error("Heartbeat failed: ...")
     │
     └─ LINE 180: Wait 10 seconds
        └─ await asyncio.sleep(10)
           └─ Go back to LINE 151, repeat
```

---

## Alur Komunikasi HTTP

### Endpoint Reference

**Central Gateway Endpoints:**

| Endpoint | Method | Purpose | Source |
|----------|--------|---------|--------|
| `/` | GET | Dashboard | Browser |
| `/health` | GET | Health check | Client |
| `/tasks` | POST | Submit task | Client |
| `/tasks/{id}` | GET | Get task status | Client |
| `/nodes/status` | GET | All nodes status | Client |
| `/nodes/status` | POST | Receive heartbeat | Edge Node |
| `/results/{id}` | POST | Receive result | Edge Node |

**Edge Node Endpoints:**

| Endpoint | Method | Purpose | Source |
|----------|--------|---------|--------|
| `/health` | GET | Node health | Client |
| `/tasks` | POST | Receive task | Central |

---

## Data Models

### shared/models.py

```python
class Task(BaseModel):
    """Task definition"""
    task_id: str              # Unique task ID
    name: str                 # Task name
    data: Dict[str, Any]      # Task parameters
    priority: int = 1         # Priority level (default 1)
    created_at: datetime = None

class TaskResult(BaseModel):
    """Task result"""
    task_id: str              # Reference to task
    status: str               # pending | completed | failed
    result: Optional[Dict[str, Any]] = None    # Result data
    error: Optional[str] = None                # Error message
    node_id: Optional[str] = None              # Processing node
    completed_at: Optional[datetime] = None    # Completion time

class NodeStatus(BaseModel):
    """Node status/health"""
    node_id: str              # e.g., "edge-1"
    status: str               # healthy | busy | unhealthy
    cpu_usage: float          # 0-100 %
    memory_usage: float       # 0-100 %
    tasks_count: int          # Pending tasks
    last_heartbeat: datetime  # Last update time
```

---

## Summary Visual

### Central Gateway Flow

```
┌─────────────────────────────────────────┐
│        CENTRAL GATEWAY FLOW             │
├─────────────────────────────────────────┤
│                                         │
│  [1] POST /tasks                        │
│      └─ submit_task()                   │
│         ├─ Store (status=pending)       │
│         ├─ Create background task       │
│         └─ Return task_id               │
│                                         │
│  [2] distribute_task() [Background]     │
│      └─ For each node:                  │
│         └─ POST /tasks                  │
│                                         │
│  [3] GET /tasks/{id}                    │
│      └─ get_task_status()               │
│         └─ Return from tasks_db         │
│                                         │
│  [4] POST /nodes/status [From Node]     │
│      └─ update_node_status()            │
│         └─ Update node_status_db        │
│                                         │
│  [5] POST /results/{id} [From Node]     │
│      └─ submit_result()                 │
│         └─ Update task (completed)      │
│                                         │
└─────────────────────────────────────────┘
```

### Edge Node Flow

```
┌─────────────────────────────────────────┐
│         EDGE NODE FLOW                  │
├─────────────────────────────────────────┤
│                                         │
│  [1] Startup                            │
│      ├─ Start heartbeat()               │
│      └─ Start process_tasks()           │
│                                         │
│  [2] POST /tasks [From Central]         │
│      └─ receive_task()                  │
│         ├─ Add to queue                 │
│         └─ Return immediately           │
│                                         │
│  [3] process_tasks() [Background]       │
│      └─ While True:                     │
│         ├─ Get task from queue          │
│         ├─ simulate_execution()         │
│         ├─ Create result                │
│         ├─ submit_result()              │
│         └─ Loop                         │
│                                         │
│  [4] heartbeat() [Background, 10s]      │
│      └─ While True:                     │
│         ├─ Collect metrics              │
│         ├─ POST /nodes/status           │
│         └─ Sleep 10s                    │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🎯 Kesimpulan

Dokumentasi ini menunjukkan:

✅ **Line-by-line code explanation** dari semua main functions
✅ **Flow diagrams** untuk setiap alur
✅ **HTTP request/response** format
✅ **Execution time calculation** dengan examples
✅ **Parallel processing** mechanisms
✅ **Background tasks** handling
✅ **Queue management** in edge nodes
✅ **Heartbeat mechanism** (10s interval)

**Siap untuk dijadikan referensi skripsi untuk BAB 4 (Implementasi)!** 📖
