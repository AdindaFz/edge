# Ringkasan Task Generator - Edge Computing System

## 📋 Daftar Isi
1. [Pengenalan](#pengenalan)
2. [Alur Kerja Task Generator](#alur-kerja-task-generator)
3. [Struktur Task](#struktur-task)
4. [Implementasi Workload Nyata](#implementasi-workload-nyata)
5. [Flow Eksekusi Lengkap](#flow-eksekusi-lengkap)

---

## Pengenalan

### Apa Itu Task Generator?

Task Generator adalah komponen dalam sistem edge computing yang bertugas untuk:
- **Menghasilkan tugas-tugas (tasks)** yang akan dieksekusi di edge nodes
- **Mensimulasikan beban kerja (workload)** yang realistis dengan karakteristik CPU dan memori yang bervariasi
- **Mendukung eksperimen** untuk mengoptimalkan penjadwalan dan alokasi resource di edge computing

Task Generator berada di file: `central/task_generator.py`

### Tujuan Utama

Sistem ini digunakan untuk:
1. **Penelitian dan optimasi**: Menguji algoritma penjadwalan (Random, Tabu Search, dll)
2. **Kalibasi model**: Mengumpulkan data untuk melatih model simulasi
3. **Analisis energi**: Mengevaluasi konsumsi energi pada berbagai strategi penjadwalan

---

## Alur Kerja Task Generator

### 1. Konfigurasi Awal

```python
# File: central/task_generator.py (baris 7-15)

TASK_SEED = 42                              # Seed untuk reproducibility
np.random.seed(TASK_SEED)
random.seed(TASK_SEED)

CPU_TIME_MS_RANGE = (200.0, 900.0)         # CPU time antara 200-900ms
MEMORY_MB_RANGE = (128, 768)                # Memori antara 128-768 MB

CPU_TIME_UNIT_MS = 250.0                    # Unit normalisasi CPU
MEMORY_UNIT_BYTES = 1024 ** 3               # 1 GB = unit memori
```

**Penjelasan:**
- **TASK_SEED**: Memastikan task yang dihasilkan dapat direproduksi (konsisten antar eksperimen)
- **Range CPU/Memory**: Mendefinisikan batas minimum dan maksimum resource yang dibutuhkan task

### 1.5 Data-Driven Generation (UPDATE - v2.0)

**PENTING:** Sejak v2.0, Task Generator menggunakan **Data-Driven Generation** dari actual calibration data!

```python
# File: central/task_generator.py

USE_DATA_DRIVEN_GENERATION = True  # Flag untuk enable data-driven mode

def load_calibration_data():
    """
    Load actual task data dari calibration runs (950 tasks)
    Untuk sampling yang lebih representative terhadap real workload
    """
    # Load dari outputs/calibration/*.jsonl
    # Return: list of actual executed tasks dengan metrics

def generate_task(task_id=None, seed=None, use_calibration=None):
    """
    Generate task dengan dua mode:
    
    1. DATA-DRIVEN (default):
       - Sample template dari actual calibration data
       - Extract cpu_demand & memory_demand dari template
       - Add 5% random variation untuk diversity
       - Result: Tasks yang match actual observed patterns
    
    2. THEORETICAL (fallback):
       - Gunakan random uniform dari CPU_TIME_MS_RANGE
       - Cara lama, untuk backward compatibility
    """
```

**Benefit Data-Driven:**
- ✅ Generated tasks match actual calibration distribution (0.6% error)
- ✅ Better task size balance (8% small → 76% medium → 16% large)
- ✅ Capture real correlations antara cpu_demand dan memory_demand
- ✅ More representative workload untuk optimization testing

**Comparison:**

| Aspek | Theoretical | Data-Driven | Actual Calib |
|-------|------------|------------|-------------|
| Mean cpu_demand | 2.1469 | 1.8795 ✅ | 1.8915 |
| Small tasks | 3% | 5% | 8% |
| Medium tasks | 65% | 81% ✓ | 76% |
| Large tasks | 32% | 14% | 16% |
| Accuracy | Generic | Real-pattern | Ground truth |

### 2. Fungsi `classify_task()` - Klasifikasi Ukuran Task

```python
# File: central/task_generator.py (baris 59-73)

def classify_task(cpu_time_target_ms, memory_bytes):
    """
    Classify task size based on CPU time and memory requirements.
    
    Updated boundaries (v2.0 - dari calibration analysis):
    - Small:  < 325ms CPU & < 0.25GB memory  (target ~20%)
    - Medium: < 675ms CPU & < 0.75GB memory  (target ~60%)
    - Large:  >= 675ms CPU | >= 0.75GB memory (target ~20%)
    """
    mem_gb = memory_bytes / (1024 ** 3)

    # Updated thresholds untuk balance lebih baik
    if cpu_time_target_ms < 325 and mem_gb < 0.25:      # ← UPDATED
        return "small"
    elif cpu_time_target_ms < 675 and mem_gb < 0.75:    # ← UPDATED
        return "medium"
    return "large"
```

**Update v2.0 (dari calibration analysis):**

| Kategori | CPU Time (Old) | CPU Time (New) | Memori (Old) | Memori (New) | Keterangan |
|----------|---|---|---|---|---|
| Small    | < 350ms | < 325ms ↓ | < 0.25GB | < 0.25GB | Boundary lebih ketat |
| Medium   | < 650ms | < 675ms ↑ | < 0.75GB | < 0.75GB | Range lebih luas |
| Large    | ≥ 650ms | ≥ 675ms ↑ | ≥ 0.75GB | ≥ 0.75GB | Same |

**Alasan Update:**
- Previous boundaries menghasilkan 76% tasks di medium (terlalu banyak)
- New boundaries lebih balanced: 5% small, 81% medium, 14% large (lebih close ke actual)

### 3. Fungsi `generate_task()` - Generate Task Individual

```python
# File: central/task_generator.py (baris 82-139)

def generate_task(task_id=None, seed=None, use_calibration=None):
    """
    Generate a task dengan dua mode:
    
    MODE 1: DATA-DRIVEN (default, v2.0+)
    ├─ Load calibration data dari 950 actual executions
    ├─ Select random template
    ├─ Extract cpu_demand & memory_demand
    ├─ Add 5% random variation
    └─ Return normalized task dengan real patterns
    
    MODE 2: THEORETICAL (fallback)
    ├─ Random uniform dari CPU_TIME_MS_RANGE
    ├─ Random uniform dari MEMORY_MB_RANGE
    ├─ Normalize untuk optimizer
    └─ Return abstract task
    """
    
    if USE_DATA_DRIVEN_GENERATION and calibration_tasks:
        # Step 1: Select template dari actual calibration
        template = calibration_tasks[seed % len(calibration_tasks)]
        
        # Step 2: Extract dari template
        cpu_demand = float(template['cpu_demand'])
        memory_demand = float(template['memory_demand'])
        
        # Step 3: Add variation (~5%) untuk diversity
        cpu_demand *= np.random.normal(1.0, 0.05)
        memory_demand *= np.random.normal(1.0, 0.05)
        
        # Step 4: Clamp ke bounds
        cpu_demand = np.clip(cpu_demand, 0.8, 3.6)
        memory_demand = np.clip(memory_demand, 0.125, 0.75)
        
        # Step 5: Convert back
        cpu_time_target_ms = cpu_demand * CPU_TIME_UNIT_MS
        memory_bytes = int(memory_demand * MEMORY_UNIT_BYTES)
    
    else:
        # FALLBACK: Theoretical generation
        cpu_time_target_ms = float(np.random.uniform(*CPU_TIME_MS_RANGE))
        memory_mb = int(np.random.uniform(*MEMORY_MB_RANGE))
        memory_bytes = memory_mb * 1024 * 1024
        
        cpu_demand = cpu_time_target_ms / CPU_TIME_UNIT_MS
        memory_demand = memory_bytes / MEMORY_UNIT_BYTES
    
    # Step 6: Compute cost
    compute_cost = cpu_demand * 100.0
    
    # Return task structure
    return {
        "task_id": task_id or str(uuid.uuid4()),
        "cpu_demand": float(cpu_demand),
        "memory_demand": float(memory_demand),
        "compute_cost": float(compute_cost),
        "task_type": "cpu_mem_burn",
        "cpu_time_target_ms": float(cpu_time_target_ms),
        "memory_bytes": int(memory_bytes),
        "payload": {...},
        "arrival_time": 0.0,
        "task_size": classify_task(cpu_time_target_ms, memory_bytes),
        "experiment_id": "exp_1",
    }
```

**Output Contoh Task (Data-Driven):**

```json
{
    "task_id": "task_0",
    "cpu_time_target_ms": 432.1,      // ← dari calibration template
    "memory_bytes": 256000000,         // ← dari calibration template
    "cpu_demand": 1.728,               // ← 432.1 / 250
    "memory_demand": 0.244,            // ← 256MB / 1GB
    "compute_cost": 172.8,
    "task_size": "medium",             // ← updated classification
    "task_type": "cpu_mem_burn",
    "payload": {
        "seed": 420000,
        "touch_rounds": 4
    }
}
```

**Perbedaan Mode:**

| Aspek | Theoretical | Data-Driven |
|-------|-------------|------------|
| Source | `np.random.uniform()` | Calibration data |
| Distribution | Uniform random | Actual observed |
| Correlation | Independent | Correlated |
| Representativeness | Generic | Real workload |
| Use Case | Testing | Production |

### 4. Fungsi `generate_batch()` - Generate Multiple Tasks

```python
# File: central/task_generator.py (baris 60-69)

def generate_batch(n_tasks=50, seed=42):
    """Generate n_tasks dengan seed yang konsisten"""
    np.random.seed(seed)
    random.seed(seed)
    
    tasks = []
    for i in range(n_tasks):
        task_seed = seed * 10000 + i
        tasks.append(generate_task(task_id=f"task_{i}", seed=task_seed))
    
    return tasks
```

**Karakteristik:**
- Menghasilkan batch tasks sekaligus (default 50 tasks)
- Setiap task mendapat unique seed untuk reproducibility
- Arrival time semua 0 (simultaneous)

### 5. Fungsi `generate_poisson_tasks()` - Generate dengan Poisson Distribution

```python
# File: central/task_generator.py (baris 72-88)

def generate_poisson_tasks(n_tasks=50, lambda_rate=2, seed=42):
    """Generate tasks dengan inter-arrival time mengikuti distribution Poisson"""
    np.random.seed(seed)
    random.seed(seed)
    
    tasks = []
    sim_time = 0.0
    
    for i in range(n_tasks):
        # Hitung inter-arrival time berdasarkan Poisson
        inter_arrival = np.random.exponential(1.0 / lambda_rate)
        sim_time += inter_arrival
        
        task_seed = seed * 10000 + i
        task = generate_task(task_id=f"task_{i}", seed=task_seed)
        task["arrival_time"] = float(sim_time)
        tasks.append(task)
    
    return tasks
```

**Penjelasan Poisson:**
- **Lambda (λ)**: Average arrival rate (tasks/time unit)
- **Inter-arrival time**: Waktu antara kedatangan dua task
- Distribusi exponential menghasilkan arrival pattern yang lebih realistis

**Contoh dengan λ=2:**
```
Task 0: arrival_time = 0.0
Task 1: arrival_time = 0.523
Task 2: arrival_time = 1.245
Task 3: arrival_time = 2.891
...
```

### 6. Fungsi `task_stream()` - Stream Tasks dengan Timing Real

```python
# File: central/task_generator.py (baris 91-102)

def task_stream(tasks):
    """Generator yang emit tasks sesuai arrival time mereka (real-time)"""
    start_time = datetime.now().timestamp()
    
    for task in tasks:
        now = datetime.now().timestamp()
        elapsed = now - start_time
        
        wait_time = task["arrival_time"] - elapsed
        if wait_time > 0:
            time.sleep(wait_time)          # Wait hingga arrival time
        
        yield task                         # Emit task
```

**Kegunaan:** Streaming tasks dengan timing yang realistis sesuai arrival time.

---

## Struktur Task

### Task Model (dari `shared/models.py`)

```python
# File: shared/models.py (baris 6-21)

class Task(BaseModel):
    task_id: str                           # Unique identifier
    
    # Untuk optimizer
    cpu_demand: float                      # Normalized CPU demand (0-4)
    memory_demand: float                   # Normalized memory demand (0-1)
    compute_cost: float                    # Cost metric untuk optimizer
    
    # Task details
    task_type: Literal["cpu_mem_burn"]     # Jenis task
    cpu_time_target_ms: float              # Target CPU time dalam ms
    memory_bytes: int                      # Memori dalam bytes
    payload: Dict[str, Any]                # Payload untuk executor
    
    # Metadata
    arrival_time: float = 0.0              # Waktu kedatangan
    task_size: str = "normal"              # Klasifikasi: small/medium/large
    experiment_id: str = "default"         # ID eksperimen
```

---

## Implementasi Workload Nyata

### Cara Task Dieksekusi di Edge Node

#### 1. Task Dikirim ke Edge Node

```python
# File: central/offline_runner.py (baris 89-112)

def send_task_to_node(task, node_id):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks"
    
    print(f"[SEND] task_id={task['task_id']} target_node={node_id}")
    
    response = requests.post(url, json=task, timeout=10)
    response.raise_for_status()
    return response
```

**Alur:**
1. Task dikirim via HTTP POST ke edge node
2. Edge node menerima task definition dan payload

#### 2. Edge Node Mengeksekusi Task

```python
# File: edge/workload_worker.py

def run_chunk(memory_bytes, seed, touch_rounds):
    """Eksekusi workload: CPU burn + memory touch"""
    
    # Step 1: Allocate memory buffer
    buf = np.zeros(memory_bytes, dtype=np.uint8)
    
    # Step 2: Touch memory (penuhi page tables)
    page_count = max(1, min(memory_bytes // PAGE_SIZE, MAX_TOUCHED_PAGES))
    page_indices = np.arange(page_count, dtype=np.int64) * PAGE_SIZE
    
    for r in range(touch_rounds):
        value = np.uint8((seed + r) & 0xFF)
        buf[page_indices] ^= value        # Memory write untuk konsumsi energi
    
    # Step 3: CPU computation (burn cycles)
    vec = rng.integers(1, 2**31 - 1, size=VECTOR_SIZE, dtype=np.uint64)
    
    for _ in range(COMPUTE_ROUNDS):      # Berapa kali loop komputasi
        vec = vec * np.uint64(6364136223846793005) + np.uint64(1)
        vec ^= (vec >> np.uint64(13))
        vec ^= (vec << np.uint64(7))
    
    # Step 4: Compute checksum (verifikasi)
    checksum = int(np.bitwise_xor.reduce(buf[...]).item())
    checksum ^= int(np.bitwise_xor.reduce(vec).item())
    
    return {
        "checksum": checksum,
        "memory_bytes": memory_bytes,
        "seed": seed,
        "touch_rounds": touch_rounds
    }
```

**Workload Characteristics:**

| Node Tier | Vector Size | Compute Rounds | Keterangan |
|-----------|------------|-----------------|-----------|
| low       | 128        | 2               | Untuk edge devices (IoT) |
| mid       | 256        | 4               | Untuk mini-servers |
| high      | 512        | 8               | Untuk powerful nodes |

**Penjelasan Workload:**

1. **Memory Allocation**: Mengalokasi buffer sesuai `memory_bytes` dari task
2. **Memory Touch**: Menulis data ke memory untuk:
   - Trigger page faults (memastikan memory benar-benar digunakan)
   - Mensimulasikan memory access pattern
   - Menghasilkan konsumsi energi dinamis
3. **CPU Burn**: Loop komputasi integer operations untuk mengonsumsi CPU cycles
4. **Verification**: Checksum untuk memastikan workload tidak dioptimasi compiler

#### 3. Hasil Dikapture dan Dikembalikan

```python
# File: central/offline_runner.py (baris 116-137)

def wait_for_result(task_id, node_id, timeout=120):
    """Poll hasil eksekusi dari edge node"""
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks/{task_id}"
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            res = requests.get(url, timeout=3)
            data = res.json()
            
            if data.get("status") in ["done", "completed"]:
                return data    # Return lengkap dengan metrics
            
            if data.get("status") == "failed":
                raise RuntimeError(f"Task failed on node {node_id}")
        
        except Exception as e:
            print(f"[WAIT-ERROR] task_id={task_id}")
        
        time.sleep(0.5)
    
    raise TimeoutError(f"Timeout waiting result for {task_id}")
```

**Result Structure:**

```json
{
    "task_id": "task_0",
    "status": "completed",
    "latency": 0.523,                    // Network latency
    "execution_time": 0.456,             // Task execution time
    "result": {
        "observed_task_clock_ms": 456.2,    // Waktu eksekusi actual (dari perf)
        "observed_cpu_clock_ms": 440.1,     // CPU active time
        "observed_memory_bytes": 268435456, // Memory yang digunakan
        "executor_node": "node_1",
        "executor_host": "192.168.1.10",
        "executor_pid": 1234,
        "output": {...}                     // Workload output
    }
}
```

---

## Flow Eksekusi Lengkap

### Sequence Diagram: Task Generation hingga Completion

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. TASK GENERATION                                                   │
│    generate_batch(n_tasks=25, seed=42)                               │
│    ↓                                                                  │
│    For each task i:                                                  │
│    - Generate: cpu_time ∈ [200, 900]ms                              │
│    - Generate: memory ∈ [128, 768]MB                                │
│    - Normalize: cpu_demand, memory_demand                            │
│    - Classify: task_size = small/medium/large                       │
│    - Output: 25 tasks dengan arrival_time=0                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. ASSIGNMENT (Offline Experiment)                                   │
│    run_offline_experiment(tasks, mode="tabu")                       │
│    ↓                                                                  │
│    Step 1: Load active edge nodes dengan resource info              │
│    Step 2: Select assignment algorithm:                             │
│      - "random": Random assignment                                  │
│      - "tabu": Tabu search optimization                             │
│      - "optimized": Greedy optimization                             │
│    Step 3: Compute assignments[task_id] -> node_id                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. TASK SUBMISSION                                                   │
│    For each task:                                                    │
│      send_task_to_node(task, node_id)                               │
│      ↓                                                               │
│      POST http://node/tasks dengan JSON body                        │
│      Edge node receive dan queue task                               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. EXECUTION di Edge Node                                            │
│    edge_node.execute_task(task):                                     │
│      ↓                                                               │
│      buf = allocate(memory_bytes)                                   │
│      for each touch_round:                                          │
│          buf[pages] ^= seed  # Memory access                        │
│      for each compute_round:                                        │
│          vec = CPU_OP(vec)   # CPU intensive                        │
│      return {                                                        │
│          execution_time,                                            │
│          observed_task_clock_ms,                                    │
│          observed_memory_bytes,                                     │
│          checksum                                                   │
│      }                                                               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. RESULT RETRIEVAL                                                  │
│    wait_for_result(task_id, node_id):                               │
│      Poll: GET http://node/tasks/{task_id}                          │
│      Until: status in [done, completed, failed]                     │
│      Return: Complete result dengan metrics                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. METRICS COMPUTATION                                               │
│    compute_metrics(results, tasks, nodes):                          │
│      ↓                                                               │
│      For each task result:                                          │
│        - Hitung latency, execution_time                            │
│        - Estimate energy = f(task_clock, cpu_clock, power)         │
│        - Track CPU/memory utilization per node                     │
│      ↓                                                               │
│      Return: {                                                       │
│          real_avg_latency,                                          │
│          estimated_real_energy_j,                                   │
│          real_total_task_clock_ms,                                  │
│          model_total_energy,                                        │
│          ...                                                        │
│      }                                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Contoh Eksekusi di main.py

```python
# File: main.py (baris 133-200)

# Step 1: Generate tasks
N_TASKS = 25
tasks = generate_batch(N_TASKS)           # Generate 25 tasks

# Step 2: Run random assignment experiment
res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

print("=== RANDOM ASSIGNMENT ===")
print(f"Avg Latency: {metrics_random['real_avg_latency']:.4f}")
print(f"Estimated Energy: {metrics_random['estimated_real_energy_j']:.4f} J")

# Step 3: Run optimized (Tabu search) experiment  
E_ref = metrics_random["model_total_energy"]
L_ref = metrics_random["model_avg_latency"]

res_tabu, history_tabu = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
    local_mode="none"
)
metrics_tabu = compute_metrics(res_tabu, tasks, NODE_RESOURCES)

# Step 4: Compare results
print("\n=== COMPARISON: RANDOM vs TABU ===")
print(f"Avg Latency - Random: {metrics_random['real_avg_latency']:.4f}")
print(f"Avg Latency - Tabu:   {metrics_tabu['real_avg_latency']:.4f}")
print(f"Energy - Random:      {metrics_random['estimated_real_energy_j']:.4f} J")
print(f"Energy - Tabu:        {metrics_tabu['estimated_real_energy_j']:.4f} J")
```

---

## Energy Estimation Model

### Bagaimana Energi Dihitung?

```python
# File: central/offline_runner.py (baris 23-57)

def estimate_task_energy_joule(task, result_row, node):
    """
    Estimasi energi task berdasarkan:
    1. Observed execution time (task_clock)
    2. Observed CPU active time (cpu_clock)
    3. Node power characteristics
    """
    
    # Step 1: Get timing dari execution result
    task_clock_ms = result_row.get("observed_task_clock_ms")
    cpu_clock_ms = result_row.get("observed_cpu_clock_ms")
    
    active_time_s = float(task_clock_ms) / 1000.0
    cpu_active_time_s = float(cpu_clock_ms) / 1000.0
    
    # Step 2: Calculate resource utilization
    cpu_util = min(float(task["cpu_demand"]) / node["cpu"], 1.0)
    mem_util = min(float(task["memory_demand"]) / node["mem"], 1.0)
    
    # Step 3: Get node power profile
    idle_power = node.get("idle_power_w", 5.0)        # Idle power (watts)
    max_power = node.get("max_power_w", 12.0)         # Max power (watts)
    dynamic_power_span = max_power - idle_power
    
    # Step 4: Compute energy components
    # CPU energy proportional to CPU utilization × CPU active time
    cpu_dynamic_energy = dynamic_power_span * cpu_util * cpu_active_time_s
    
    # Memory energy proportional to mem utilization × total active time
    memory_dynamic_energy = 0.15 * dynamic_power_span * mem_util * active_time_s
    
    # Idle energy during task execution
    idle_energy = idle_power * active_time_s
    
    # Total energy = Idle + CPU dynamic + Memory dynamic
    total_energy = idle_energy + cpu_dynamic_energy + memory_dynamic_energy
    
    return total_energy
```

**Formula Energy:**

```
Total Energy (Joules) = Idle Energy + CPU Dynamic Energy + Memory Dynamic Energy

Idle Energy = idle_power × active_time

CPU Dynamic Energy = (max_power - idle_power) × cpu_utilization × cpu_active_time

Memory Dynamic Energy = 0.15 × (max_power - idle_power) × mem_utilization × active_time
```

**Contoh Kalkulasi:**

```
Task: cpu_demand=2.0, memory_demand=0.3, cpu_time_target_ms=500
Node: cpu=4, mem=1.0, idle_power=5W, max_power=15W

Observed: task_clock_ms=450, cpu_clock_ms=440

active_time_s = 450 / 1000 = 0.45 s
cpu_active_time_s = 440 / 1000 = 0.44 s

cpu_util = min(2.0 / 4, 1.0) = 0.5
mem_util = min(0.3 / 1.0, 1.0) = 0.3

dynamic_power_span = 15 - 5 = 10 W

idle_energy = 5 × 0.45 = 2.25 J
cpu_dynamic = 10 × 0.5 × 0.44 = 2.2 J
mem_dynamic = 0.15 × 10 × 0.3 × 0.45 = 0.2025 J

Total = 2.25 + 2.2 + 0.2025 = 4.6525 J
```

---

## Ringkasan Implementasi Workload

### Keseluruhan Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ Task Generator (central/task_generator.py)                       │
│                                                                  │
│ Input: n_tasks, lambda_rate, seed                              │
│   ↓                                                              │
│ Output: List[Task] dengan properties:                           │
│   - task_id, cpu_demand, memory_demand                          │
│   - cpu_time_target_ms, memory_bytes                            │
│   - task_type="cpu_mem_burn", payload, arrival_time            │
│   - task_size (small/medium/large)                              │
└──────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────────┐
│ Assignment Engine (central/assignment_engine.py)                │
│                                                                  │
│ Input: tasks, active_nodes, assignment_mode                    │
│   ↓                                                              │
│ Output: assignments[task_id] -> node_id                        │
│ Algorithms: random, tabu_search, greedy                        │
└──────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────────┐
│ Edge Nodes (edge/edge_node.py)                                  │
│                                                                  │
│ Input: Task JSON via HTTP                                       │
│   ↓                                                              │
│ Execution: workload_worker.run_chunk()                         │
│   - Allocate memory buffer                                      │
│   - Touch memory (consume memory BW)                            │
│   - Burn CPU (consume CPU cycles)                               │
│   ↓                                                              │
│ Output: Result dengan metrics                                   │
│   - observed_task_clock_ms                                      │
│   - observed_cpu_clock_ms                                       │
│   - observed_memory_bytes                                       │
│   - execution_time, latency                                     │
└──────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────────┐
│ Metrics Computation & Analysis                                   │
│                                                                  │
│ Input: results, tasks, nodes                                    │
│   ↓                                                              │
│ Compute: energy, latency, utilization per node                 │
│   ↓                                                              │
│ Output: metrics[mode] untuk comparison                          │
└──────────────────────────────────────────────────────────────────┘
```

### Key Components dalam Task Execution

| Component | Fungsi | File |
|-----------|--------|------|
| `generate_task()` | Buat 1 task | `central/task_generator.py` |
| `generate_batch()` | Buat N tasks | `central/task_generator.py` |
| `generate_poisson_tasks()` | Buat N tasks dengan Poisson arrival | `central/task_generator.py` |
| `classify_task()` | Klasifikasi ukuran task | `central/task_generator.py` |
| `random_assignment()` | Random task-to-node mapping | `central/assignment_engine.py` |
| `tabu_assignment()` | Optimized mapping via Tabu Search | `central/assignment_engine.py` |
| `send_task_to_node()` | Kirim task ke node via HTTP | `central/offline_runner.py` |
| `wait_for_result()` | Poll hasil eksekusi | `central/offline_runner.py` |
| `run_chunk()` | Eksekusi workload real | `edge/workload_worker.py` |
| `estimate_task_energy_joule()` | Hitung konsumsi energi | `central/offline_runner.py` |
| `compute_metrics()` | Aggregate metrics | `central/offline_runner.py` |

---

## Kesimpulan

### Task Generator Berperan untuk:

1. **Generate Synthetic Workload**: Menciptakan task-task yang realistis dengan CPU dan memory requirements yang bervariasi

2. **Support Optimization Research**: Memungkinkan testing berbagai algorithm penjadwalan (Random, Tabu, dll)

3. **Real Workload Simulation**: Task tidak hanya abstract - benar-benar dieksekusi di edge nodes dengan CPU burn dan memory access patterns

4. **Energy Measurement**: Kapture metrics aktual (task_clock, cpu_clock) untuk estimasi energi yang akurat

5. **Reproducible Experiments**: Menggunakan seed-based generation untuk hasil yang konsisten across runs

Sistem ini adalah comprehensive framework untuk research edge computing resource allocation dengan fokus pada **energy efficiency** dan **latency optimization**.

---

## 🚀 UPDATE v2.0: Data-Driven Task Generation

### Implementation Date: 2026-04-30
### Commit: 8b1b505

**MAJOR CHANGE:** Task Generator sekarang menggunakan **actual calibration data** untuk generate tasks yang lebih representative!

### Apa yang Berubah:

#### 1. New Functions
```python
load_calibration_data()        # Load 950 actual tasks dari calibration runs
```

#### 2. Enhanced generate_task()
```python
# Sebelum: Random uniform (theoretical)
generate_task(task_id, seed)

# Sesudah: Data-driven dengan fallback (v2.0)
generate_task(task_id, seed, use_calibration=True/False/None)
```

#### 3. Updated classify_task()
```python
# Boundaries adjusted untuk better balance berdasarkan calibration data analysis
```

### Results

**Distribution Improvement:**

```
Theoretical (sebelum):    3% small, 65% medium, 32% large
Data-Driven (sesudah):    5% small, 81% medium, 14% large ✓
Actual Calibration:       8% small, 76% medium, 16% large  (target reference)
```

**cpu_demand Accuracy:**

```
Theoretical mean: 2.1469 (error: 13.5% dari actual)
Data-Driven mean: 1.8795 (error: 0.6% dari actual) ✅
Actual calib mean: 1.8915
```

### Key Benefits

✅ **Representative Workload** - Generated tasks match actual observed patterns  
✅ **Better Correlation** - Captures relationship antara cpu_demand dan memory_demand  
✅ **Accurate Distribution** - Task size distribution lebih balanced  
✅ **Backward Compatible** - Fallback ke theoretical jika data unavailable  
✅ **Flexible** - Flag untuk switch antara modes  

### Usage Examples

```python
# DEFAULT (Data-Driven):
from central.task_generator import generate_batch
tasks = generate_batch(n_tasks=25)  # Automatically uses calibration data

# FORCE THEORETICAL (Old behavior):
tasks = generate_batch(n_tasks=25, use_calibration=False)

# PER TASK CONTROL:
from central.task_generator import generate_task
task1 = generate_task(use_calibration=True)   # Data-driven
task2 = generate_task(use_calibration=False)  # Theoretical
```

### Technical Details

- **Calibration Data Source:** `outputs/calibration/workload_calibration_*.jsonl` (950 tasks)
- **Sampling Method:** Random template selection + 5% variation
- **Caching:** Calibration data cached in memory (loaded once)
- **Variation Factor:** 5% (configurable in code)
- **Fallback:** Automatic jika calibration data tidak tersedia

### Integration with Optimization

Data-driven tasks sekarang lebih representative untuk testing optimization algorithms:

1. **More Realistic Workload** - Optimizer tested against actual patterns
2. **Better Calibration Validation** - Coefficients match same distribution
3. **Reliable Results** - Less bias dari task generation

**Recommended:** Re-run optimization experiments setelah update ini untuk validate improvement!
