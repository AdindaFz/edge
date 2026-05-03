# Dokumentasi Flow Task Generator dan Eksekusi

Dokumen ini menjelaskan alur kode terbaru dengan bahasa yang lebih sederhana. Fokusnya bukan hanya konsep, tapi urutan fungsi yang benar-benar dipanggil di kode.

Kalau disingkat, alurnya seperti ini:

```text
main.py
  -> generate task
  -> pilih node untuk tiap task
  -> kirim task ke edge node
  -> edge node mengeksekusi task
  -> central mengambil hasil
  -> hitung metrik
  -> simpan data kalibrasi baru
```

## 1. Perubahan utama dibanding versi lama

Dulu, task generator lebih banyak membuat task secara acak berdasarkan range teori.

Sekarang, sistem sudah berubah menjadi lebih realistis:

1. Task generator mengambil contoh dari data kalibrasi yang pernah dihasilkan sebelumnya.
2. Edge node mengeksekusi task berdasarkan target CPU time dan memory asli, lalu hasilnya diukur memakai `perf`.
3. Nilai normalisasi CPU time sekarang bisa dikalibrasi dari hasil observasi nyata, jadi tidak selalu memakai konstanta manual lama.

Jadi sekarang ada dua dunia yang berjalan bersamaan:

- dunia optimizer: memakai `cpu_demand` dan `memory_demand`
- dunia eksekusi nyata: memakai `cpu_time_target_ms` dan `memory_bytes`

## 2. Entry point dari `main.py`

File utama eksperimen ada di [main.py](/home/adinda-central/edge-computing-system/main.py).

Potongan kode penting:

```python
tasks = generate_batch(N_TASKS)

for idx in range(N_RANDOM_BASELINES):
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

res_tabu_only, history_tabu_only = run_offline_experiment(
    tasks,
    "tabu",
    E_ref=E_ref,
    L_ref=L_ref,
    return_history=True,
    local_mode="hybrid",
)
metrics_tabu_only = compute_metrics(res_tabu_only, tasks, NODE_RESOURCES)
```

Artinya:

1. `main.py` membuat sekumpulan task.
2. Task itu dijalankan beberapa kali dengan mode `random` sebagai baseline.
3. Setelah itu task yang sama dijalankan lagi dengan mode `tabu`.
4. Semua hasilnya dihitung metriknya.
5. Di akhir, hasil eksperimen disimpan lagi menjadi data kalibrasi.

## 3. Bagaimana task dibuat

Logika generator ada di [central/task_generator.py](/home/adinda-central/edge-computing-system/central/task_generator.py).

### 3.1 `generate_batch()`

Fungsi ini membuat banyak task sekaligus.

Potongan kode:

```python
def generate_batch(n_tasks=50, seed=42):
    np.random.seed(seed)
    random.seed(seed)

    tasks = []
    for i in range(n_tasks):
        task_seed = seed * 10000 + i
        tasks.append(generate_task(task_id=f"task_{i}", seed=task_seed))

    return tasks
```

Penjelasan sederhananya:

- `generate_batch()` melakukan loop sebanyak jumlah task yang diminta
- setiap task diberi ID seperti `task_0`, `task_1`, dan seterusnya
- detail masing-masing task dibuat oleh `generate_task()`

### 3.2 `generate_task()`

Ini fungsi inti generator.

Potongan kode yang paling penting:

```python
cpu_time_unit_ms = load_cpu_time_unit_ms()

use_calib = use_calibration if use_calibration is not None else USE_DATA_DRIVEN_GENERATION
calibration_tasks = load_calibration_data() if use_calib else None

if calibration_tasks:
    template = calibration_tasks[seed % len(calibration_tasks)]

    cpu_demand = float(template.get("cpu_demand", 1.0))
    memory_demand = float(template.get("memory_demand", 0.5))

    cpu_demand *= np.random.normal(1.0, 0.05)
    memory_demand *= np.random.normal(1.0, 0.05)

    cpu_demand = np.clip(cpu_demand, 0.8, 3.6)
    memory_demand = np.clip(memory_demand, 0.125, 0.75)

    cpu_time_target_ms = cpu_demand * cpu_time_unit_ms
    memory_bytes = int(memory_demand * MEMORY_UNIT_BYTES)
else:
    cpu_time_target_ms = float(np.random.uniform(*CPU_TIME_MS_RANGE))
    memory_mb = int(np.random.uniform(*MEMORY_MB_RANGE))
    memory_bytes = memory_mb * 1024 * 1024

    cpu_demand = cpu_time_target_ms / cpu_time_unit_ms
    memory_demand = memory_bytes / MEMORY_UNIT_BYTES
```

### 3.3 Arti flow di atas

Bahasa sederhananya:

1. Sistem cek dulu apakah ada data kalibrasi.
2. Kalau ada, sistem mengambil satu contoh task dari data kalibrasi lama.
3. Nilai `cpu_demand` dan `memory_demand` dari contoh itu dipakai lagi.
4. Nilainya sedikit diacak sekitar 5% supaya task baru tidak 100% sama.
5. Dari demand itu, sistem menghitung target eksekusi nyatanya:
   - berapa lama CPU perlu bekerja
   - berapa banyak memori yang harus disentuh
6. Kalau data kalibrasi tidak ada, barulah fallback ke random teoritis.

Jadi perubahan utamanya adalah:

- dulu: task dibuat dari angka acak teori
- sekarang: task meniru pola workload yang pernah benar-benar terjadi

### 3.4 Kalibrasi `CPU_TIME_UNIT_MS`

Sebelumnya generator memakai konstanta:

```python
CPU_TIME_UNIT_MS = 250.0
```

Sekarang generator bisa membaca hasil kalibrasi dari file:

- [outputs/calibration/cpu_time_unit_calibration.json](/home/adinda-central/edge-computing-system/outputs/calibration/cpu_time_unit_calibration.json)

Potongan kode:

```python
def load_cpu_time_unit_ms():
    if CPU_TIME_UNIT_CALIBRATION_PATH.exists():
        with CPU_TIME_UNIT_CALIBRATION_PATH.open() as f:
            payload = json.load(f)

        recommended = payload.get("recommended_cpu_time_unit_ms")
        if recommended is not None and float(recommended) > 0:
            return float(recommended)

    return CPU_TIME_UNIT_MS
```

Artinya:

1. Generator cek dulu apakah ada file hasil kalibrasi.
2. Kalau ada, generator memakai nilai `recommended_cpu_time_unit_ms`.
3. Kalau tidak ada, barulah kembali ke default lama `250.0`.

Saat ini hasil kalibrasi yang sudah dihitung dari data run sebelumnya adalah sekitar:

- `CPU_TIME_UNIT_MS = 372.235 ms` untuk tier referensi `mid`

Jadi sekarang angka normalisasi itu sudah punya dasar observasi nyata, bukan hanya konstanta manual.

### 3.5 Struktur task yang dihasilkan

Potongan kode return task:

```python
return {
    "task_id": task_id or str(uuid.uuid4()),
    "cpu_demand": float(cpu_demand),
    "memory_demand": float(memory_demand),
    "compute_cost": float(compute_cost),
    "task_type": "cpu_mem_burn",
    "cpu_time_target_ms": float(cpu_time_target_ms),
    "memory_bytes": int(memory_bytes),
    "payload": {
        "seed": int(seed),
        "touch_rounds": 4,
    },
    "arrival_time": 0.0,
    "task_size": classify_task(cpu_time_target_ms, memory_bytes),
    "experiment_id": "exp_1",
}
```

Supaya mudah dipahami, arti field pentingnya:

- `cpu_demand`: angka untuk optimizer menghitung beban CPU task
- `memory_demand`: angka untuk optimizer menghitung beban memori task
- `cpu_time_target_ms`: target lama kerja CPU saat task benar-benar dijalankan
- `memory_bytes`: target penggunaan memori saat task dijalankan
- `payload.seed`: seed agar pola kerja worker bisa diulang
- `payload.touch_rounds`: berapa kali pola sentuh memori diulang

## 4. Bagaimana node dipilih untuk task

Bagian ini ditangani oleh [central/offline_runner.py](/home/adinda-central/edge-computing-system/central/offline_runner.py) dan [central/assignment_engine.py](/home/adinda-central/edge-computing-system/central/assignment_engine.py).

### 4.1 `run_offline_experiment()`

Potongan kode utama:

```python
active_nodes = get_active_nodes_with_resources()

assign_random = random_assignment(tasks, active_nodes)
init_assign = np.array([
    node_ids.index(assign_random[t["task_id"]])
    for t in tasks
])

if mode == "random":
    assignments = random_assignment(tasks, active_nodes)
elif mode == "tabu":
    assignments, history = tabu_assignment(
        tasks,
        active_nodes,
        init_assign=init_assign,
        local_mode=local_mode,
        E_ref=E_ref,
        L_ref=L_ref,
    )
else:
    assignments = optimized_assignment(tasks, active_nodes)
```

Artinya:

1. Central mengecek edge node mana yang aktif.
2. Setelah itu central memilih assignment task ke node.
3. Cara memilihnya tergantung mode eksperimen:
   - `random`
   - `tabu`
   - `optimized`

### 4.2 Mode `random`

Kode:

```python
def random_assignment(tasks, nodes):
    node_ids = list(nodes.keys())
    assignments = {}

    for task in tasks:
        node = random.choice(node_ids)
        assignments[task["task_id"]] = node

    return assignments
```

Bahasa sederhananya:

- setiap task dilempar ke node secara acak
- ini dipakai sebagai baseline pembanding

### 4.3 Mode `optimized`

Kode penting:

```python
service_time = calibrated_service_time(cpu_demand, cpu_cap)
queue_penalty = service_time * max(0.0, ((current_cpu + cpu_demand) / max(cpu_cap, 1e-6)) - 0.8) * 1.35
mem_penalty = max(0.0, (current_mem + mem_demand) / max(mem_cap, 1e-6) - 1.0) ** 2

energy = power_w * calibrated_active_time(cpu_demand, cpu_cap)
latency = service_time + float(node["network_delay"]) + queue_penalty + mem_penalty

score = latency + 0.05 * energy
```

Bahasa sederhananya:

Saat memilih node, sistem melihat:

- beban CPU task
- beban memori task
- kapasitas CPU node
- kapasitas memori node
- delay network node
- kemungkinan antrean
- estimasi energi

Lalu sistem menghitung skor. Node dengan skor paling kecil dipilih.

### 4.4 Mode `tabu`

Kode penting:

```python
best_assign, history = hybrid_tabu_diff(
    cpu_demands,
    cpu_caps,
    mem_demands,
    mem_caps,
    latency_ms,
    idle_powers=idle_powers,
    max_powers=max_powers,
    init_assign=init_assign,
    TABU_MAX_ITER=300,
    TABU_TENURE=30,
    NUM_MOVES=70,
    E_ref=E_ref,
    L_ref=L_ref,
    energy_weight=energy_weight,
    high_power_penalty_weight=high_power_penalty_weight,
    diffusion_optimizer=diffusion if use_search_diffusion else None,
    stagnation_trigger=12,
)
```

Cara mudah memahaminya:

1. Sistem mulai dari assignment awal random.
2. Lalu assignment itu diperbaiki berkali-kali dengan tabu search.
3. Kalau mode mendukung diffusion, hasil tabu akan dipoles lagi.
4. Hasil terbaik dipakai sebagai assignment final.

Jadi mode `tabu` bukan random murni. Ia adalah proses pencarian assignment yang lebih baik.

## 5. Bagaimana task dikirim ke edge node

Masih di [central/offline_runner.py](/home/adinda-central/edge-computing-system/central/offline_runner.py).

### 5.1 Mengirim task

Kode:

```python
def send_task_to_node(task, node_id):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks"
    response = requests.post(url, json=task, timeout=10)
    response.raise_for_status()
    return response
```

Artinya:

- central mengirim seluruh isi task ke endpoint `/tasks` pada edge node target
- task dikirim dalam bentuk JSON

### 5.2 Menunggu hasil

Kode:

```python
def wait_for_result(task_id, node_id, timeout=120):
    node = EDGE_NODES[node_id]
    url = f"http://{node['ip']}:{node['port']}/tasks/{task_id}"

    while time.time() - start < timeout:
        res = requests.get(url, timeout=3)
        data = res.json()

        if data.get("status") in ["done", "completed"]:
            return data
```

Artinya:

- central tidak langsung mendapat hasil
- central akan menanyakan status task berkali-kali
- kalau status sudah `completed`, hasil diambil

## 6. Apa yang terjadi di edge node saat task masuk

Logika utamanya ada di [edge/edge_node.py](/home/adinda-central/edge-computing-system/edge/edge_node.py).

### 6.1 Task diterima dulu, belum langsung dijalankan

Kode:

```python
@app.post("/tasks")
async def receive_task(task: Task):
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
```

Bahasa sederhananya:

- task yang datang dimasukkan ke queue
- status awalnya `queued`
- jadi task tidak selalu langsung dieksekusi saat diterima

### 6.2 Worker background mengambil task dari queue

Kode:

```python
async def worker_loop():
    while True:
        task = await app.state.task_queue.get()
        try:
            await process_task(task)
        finally:
            app.state.task_queue.task_done()
```

Artinya:

- edge node punya worker loop
- worker akan terus mengambil task dari queue satu per satu

### 6.3 `process_task()`

Kode penting:

```python
task_results[task.task_id] = {
    "task_id": task.task_id,
    "status": "processing",
    "node_id": NODE_ID,
}

result_payload, exec_time = await execute_task(task)

completed_ts = time.time()
queued_at = runtime.get("queued_at", completed_ts)
latency = completed_ts - queued_at
```

Artinya:

1. status task berubah dari `queued` menjadi `processing`
2. lalu task benar-benar dijalankan oleh `execute_task()`
3. setelah selesai, latency dihitung dari waktu antre sampai selesai

## 7. Bagaimana task benar-benar dieksekusi

Bagian terpenting ada di `execute_task()`.

### 7.1 Task dibaca sebagai target kerja nyata

Kode:

```python
target_cpu_ms = float(task.cpu_time_target_ms)
memory_bytes = int(task.memory_bytes)
touch_rounds = int(task.payload.get("touch_rounds", 4))
base_seed = int(task.payload.get("seed", 0))
```

Artinya:

task sekarang dibaca sebagai instruksi kerja nyata:

- CPU harus bekerja kira-kira berapa lama
- memori harus disentuh sebesar apa
- pola kerja worker diatur oleh seed dan touch rounds

### 7.2 Eksekusi dilakukan per chunk

Kode paling penting:

```python
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
```

Bahasa sederhananya:

1. Task tidak selalu selesai dalam satu kali kerja.
2. Node menjalankan worker kecil per chunk.
3. Setiap chunk menghasilkan ukuran waktu CPU nyata.
4. Chunk diulang sampai total `task_clock` mencapai target task.

Ini salah satu perubahan terbesar dibanding pendekatan lama.

## 8.1 Dari mana nilai kalibrasi CPU time didapat

Sekarang ada skrip baru:

- [calibrate_cpu_time_unit.py](/home/adinda-central/edge-computing-system/calibrate_cpu_time_unit.py)

Skrip ini membaca semua file:

- `outputs/calibration/workload_calibration_*.jsonl`

Lalu menghitung durasi chunk nyata dari hasil:

```python
chunk_task_clock_ms = float(task_clock_ms) / float(chunks)
chunk_cpu_clock_ms = float(cpu_clock_ms) / float(chunks)
```

Setelah itu, skrip mengelompokkan data berdasarkan tier node:

- `low` untuk `cpu=2`
- `mid` untuk `cpu=4`
- `high` untuk `cpu=8`

Dan memilih nilai median chunk `task-clock` pada tier `mid` sebagai baseline normalisasi.

Itulah kenapa nilai `CPU_TIME_UNIT_MS` sekarang bisa dijelaskan berdasarkan hasil observasi, bukan hanya asumsi.

## 8. Peran `perf` dalam eksekusi

Fungsi `run_perf_chunk()` memakai `perf` untuk mengukur chunk.

Kode:

```python
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
```

Lalu hasilnya diambil dengan:

```python
task_clock_ms = parse_perf_time_ms(proc.stderr, "task-clock")
cpu_clock_ms = parse_perf_time_ms(proc.stderr, "cpu-clock")
```

Artinya:

- worker dijalankan sambil diukur oleh `perf`
- sistem mengambil nilai `task-clock` dan `cpu-clock`
- hasil ini dipakai sebagai ukuran eksekusi nyata

Jadi sekarang sistem tidak hanya menebak workload, tapi benar-benar mengukurnya.

## 9. Bentuk hasil yang dikembalikan edge node

Setelah task selesai, edge node membentuk hasil seperti ini:

```python
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
```

Artinya hasil task sekarang sudah jauh lebih kaya. Bukan cuma "task selesai", tapi juga ada:

- dijalankan di node mana
- berapa lama waktu eksekusi
- berapa total `task-clock`
- berapa total `cpu-clock`
- task ini butuh berapa chunk

## 10. Bagaimana central mengumpulkan hasil

Setelah edge node selesai, `offline_runner` membuat row hasil seperti ini:

```python
row = {
    "task_id": task_id,
    "latency": result.get("latency"),
    "execution_time": result.get("execution_time"),
    "energy": result_payload.get("energy"),
    "node": node_id,
    "executor_node": result_payload.get("executor_node", node_id),
    "executor_host": result_payload.get("executor_host"),
    "executor_pid": result_payload.get("executor_pid"),
    "observed_task_clock_ms": result_payload.get("observed_task_clock_ms"),
    "observed_cpu_clock_ms": result_payload.get("observed_cpu_clock_ms"),
    "observed_memory_bytes": result_payload.get("observed_memory_bytes"),
    "chunks": result_payload.get("chunks"),
    "output": result_payload.get("output"),
}
```

Perbedaan penting:

- `node`: node yang dipilih scheduler
- `executor_node`: node yang benar-benar menjalankan task

Saat ini biasanya sama, tapi dipisah supaya data lebih jelas.

## 11. Bagaimana metrik dihitung

Metrik dihitung oleh `compute_metrics()` di [central/offline_runner.py](/home/adinda-central/edge-computing-system/central/offline_runner.py).

### 11.1 Metrik real

Contoh return value:

```python
return {
    "real_avg_latency": float(np.mean(latencies)),
    "real_total_latency": float(np.sum(latencies)),
    "real_avg_execution_time": float(np.mean(exec_times)),
    "estimated_real_energy_j": total_energy_real_j,
    "real_avg_task_clock_ms": float(np.mean(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
    "real_total_task_clock_ms": float(np.sum(observed_task_clock_samples)) if observed_task_clock_samples else 0.0,
    "real_avg_memory_bytes": float(np.mean(observed_memory_samples)) if observed_memory_samples else 0.0,
    "model_avg_latency": float(avg_latency_model),
    "model_total_energy": float(total_energy_model),
    "distribution": dict(Counter(nodes_used)),
}
```

Metrik real artinya dihitung dari hasil task yang benar-benar dijalankan.

Contohnya:

- latency nyata
- execution time nyata
- total task clock nyata
- rata-rata memory observasi

### 11.2 Energi real bukan angka sembarang

Energi dihitung dari fungsi `estimate_task_energy_joule()`.

Kode penting:

```python
active_time_s = float(task_clock_ms) / 1000.0
cpu_active_time_s = float(cpu_clock_ms) / 1000.0

cpu_util = min(float(task["cpu_demand"]) / max(float(node["cpu"]), 1e-6), 1.0)
mem_util = min(float(task["memory_demand"]) / max(float(node["mem"]), 1e-6), 1.0)

cpu_dynamic_energy = dynamic_power_span * cpu_util * cpu_active_time_s
memory_dynamic_energy = 0.15 * dynamic_power_span * mem_util * active_time_s
idle_energy = idle_power * active_time_s
```

Bahasa sederhananya:

energi dihitung dari gabungan:

- waktu aktif task
- CPU clock nyata
- demand task
- kapasitas node
- profil daya node

Jadi perhitungan energinya sekarang lebih dekat ke kondisi nyata.

## 12. Bagaimana data kalibrasi baru dibuat

Di akhir `main.py`, ada fungsi `export_calibration_dataset(...)`.

Tujuannya adalah menyimpan hasil eksperimen ke `outputs/calibration/` supaya nanti bisa dipakai lagi oleh generator task.

Intinya sistem bekerja seperti siklus:

```text
buat task
  -> jalankan task
  -> ukur hasil nyata
  -> simpan hasil
  -> pakai hasil itu untuk membuat task eksperimen berikutnya
```

Ini yang membuat generator sekarang disebut data-driven.

## 13. Ringkasan flow paling mudah

Kalau mau mengingat sistem ini dengan cara paling sederhana, bayangkan seperti ini:

1. `main.py` membuat daftar task.
2. Task itu bukan lagi task acak murni, tapi meniru data kalibrasi lama.
3. Central memilih node untuk tiap task.
4. Task dikirim ke edge node.
5. Edge node memasukkan task ke queue.
6. Worker edge mengeksekusi task per chunk sampai target CPU time tercapai.
7. Setiap chunk diukur dengan `perf`.
8. Hasil task dikirim dan dipoll oleh central.
9. Central menghitung latency, energi, task clock, dan metrik lain.
10. Hasil eksperimen disimpan lagi sebagai data kalibrasi baru.

## 14. Kesimpulan paling penting

Ada 3 ide utama yang perlu diingat:

1. Generator sekarang memakai data nyata sebagai template.
2. Optimizer tetap bekerja dengan versi ter-normalisasi dari task, yaitu `cpu_demand` dan `memory_demand`.
3. Eksekusi nyata task ditentukan oleh `cpu_time_target_ms` dan `memory_bytes`, lalu diukur menggunakan `perf`.

Kalau mau diringkas dalam satu kalimat:

Sistem sekarang membuat task dari data eksperimen lama, menjalankannya secara nyata di edge node, mengukur hasilnya, lalu memakai hasil itu lagi untuk eksperimen berikutnya.
