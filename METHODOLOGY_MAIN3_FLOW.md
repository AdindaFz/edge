# Metodologi Sistem Edge Computing

Dokumen ini menjelaskan alur kerja sistem edge computing yang digunakan pada eksperimen saat ini. Fokus utama dokumen ini adalah bagaimana task dibangkitkan, bagaimana baseline dan optimasi dibentuk, bagaimana task benar-benar dijalankan pada edge node, dan bagaimana latency serta energi dihitung dari hasil eksekusi nyata.

Dokumen ini disusun untuk kebutuhan penjelasan metodologi, sehingga penekanan utamanya bukan hanya pada potongan kode, tetapi juga pada makna setiap tahap dalam eksperimen.

## 1. Gambaran Umum Pendekatan

Secara umum, sistem menggunakan alur berikut:

1. sistem membangkitkan sekumpulan task menggunakan generator task yang sudah data-driven,
2. sistem menjalankan baseline `random` beberapa kali untuk mendapatkan referensi rata-rata,
3. sistem menjalankan optimasi assignment berbasis objective hibrida,
4. hasil assignment dari optimasi dikirim ke edge node nyata,
5. setiap edge node mengeksekusi workload CPU dan memori secara riil,
6. hasil eksekusi diukur dengan metrik riil seperti `task-clock`, `cpu-clock`, latency, dan estimasi energi,
7. hasil baseline random dan hasil optimasi dibandingkan.

Pendekatan ini bersifat hibrida karena:

- objective utamanya tetap mempertahankan struktur simulasi program,
- tetapi pencarian solusi diberi penalti tambahan agar lebih sesuai dengan kondisi eksekusi riil pada VPS.

## 2. Alur Eksperimen

Alur eksperimen yang dipakai pada sistem saat ini secara umum dapat diringkas sebagai berikut:

```python
tasks = generate_batch(N_TASKS)

for idx in range(N_RANDOM_BASELINES):
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

res_optimized, _ = run_offline_experiment(
    tasks,
    "tabu_legacy_hybrid",
    E_ref=e_ref,
    L_ref=l_ref,
    return_history=True,
    local_mode=...,
    tabu_energy_weight=...,
    tabu_high_power_penalty_weight=...,
    tabu_vps_penalty_scale=...,
)
metrics_optimized = compute_metrics(res_optimized, tasks, NODE_RESOURCES)
```

Maknanya:

- `generate_batch()` membuat sekumpulan task eksperimen.
- `run_offline_experiment(..., "random")` dipakai untuk membangun baseline.
- baseline random dijalankan beberapa kali, lalu dirata-ratakan agar pembanding lebih stabil.
- hasil baseline itu dipakai untuk membentuk `E_ref` dan `L_ref`.
- `run_offline_experiment(..., "tabu_legacy_hybrid")` menjalankan assignment hasil optimasi hibrida.
- `compute_metrics()` menghitung metrik akhir yang dipakai untuk evaluasi.

## 3. Pembangkitan Task

Task dibangkitkan di [`central/task_generator.py`](/home/adinda-central/edge-computing-system/central/task_generator.py).

### 3.1. Prinsip Umum

Generator task sekarang tidak lagi sepenuhnya teoritis. Sistem mencoba memakai data hasil run sebelumnya sebagai dasar, sehingga task yang dibentuk lebih realistis.

Potongan kode utamanya:

```python
USE_DATA_DRIVEN_GENERATION = True

def generate_task(task_id=None, seed=None, use_calibration=None):
    cpu_time_unit_ms = load_cpu_time_unit_ms()
    calibration_tasks = load_calibration_data() if use_calib else None
```

Artinya:

- generator task secara default berada pada mode data-driven,
- generator akan mencoba membaca data kalibrasi hasil eksperimen sebelumnya,
- jika data kalibrasi tersedia, task baru dibangkitkan dengan mengikuti pola data lama,
- jika data kalibrasi tidak tersedia, generator fallback ke mode teoritis.

### 3.2. Sumber Data Kalibrasi

Data kalibrasi diambil dari folder:

- [`outputs/calibration/`](/home/adinda-central/edge-computing-system/outputs/calibration)

Logika pemuatannya:

```python
for path in sorted(calibration_dir.glob("workload_calibration_*.jsonl")):
    ...
    if "cpu_demand" in row and "memory_demand" in row:
        tasks.append(row)
```

Jadi data kalibrasi bukan data manual dari luar, tetapi merupakan hasil run sistem itu sendiri yang disimpan kembali untuk eksperimen berikutnya.

### 3.3. Kalibrasi `CPU_TIME_UNIT_MS`

Generator juga membaca hasil kalibrasi unit CPU time:

```python
CPU_TIME_UNIT_CALIBRATION_PATH = CALIBRATION_OUTPUT_DIR / "cpu_time_unit_calibration.json"
```

Jika file kalibrasi tersedia, generator akan memakai nilai hasil observasi nyata, bukan hanya konstanta default:

```python
recommended = payload.get("recommended_cpu_time_unit_ms")
```

Maknanya:

- sistem punya unit normalisasi CPU,
- unit ini dipakai untuk mengubah `cpu_demand` ke `cpu_time_target_ms`,
- nilainya sekarang dapat berasal dari hasil kalibrasi riil.

### 3.4. Pembentukan Demand dan Parameter Eksekusi

Jika data kalibrasi tersedia:

```python
cpu_demand = float(template.get("cpu_demand", 1.0))
memory_demand = float(template.get("memory_demand", 0.5))

cpu_demand *= np.random.normal(1.0, 0.05)
memory_demand *= np.random.normal(1.0, 0.05)

cpu_time_target_ms = cpu_demand * cpu_time_unit_ms
memory_bytes = int(memory_demand * MEMORY_UNIT_BYTES)
```

Maknanya:

- generator mengambil `cpu_demand` dan `memory_demand` dari template task lama,
- nilainya diberi variasi kecil agar workload baru tetap beragam,
- setelah itu demand diterjemahkan menjadi:
  - `cpu_time_target_ms`
  - `memory_bytes`

Jika fallback teoritis dipakai:

```python
cpu_time_target_ms = float(np.random.uniform(*CPU_TIME_MS_RANGE))
memory_mb = int(np.random.uniform(*MEMORY_MB_RANGE))
memory_bytes = memory_mb * 1024 * 1024

cpu_demand = cpu_time_target_ms / cpu_time_unit_ms
memory_demand = memory_bytes / MEMORY_UNIT_BYTES
```

Jadi dalam sistem ini:

- `cpu_demand` adalah representasi demand komputasi,
- `memory_demand` adalah representasi demand memori,
- `cpu_time_target_ms` dan `memory_bytes` adalah parameter eksekusi riil yang nantinya benar-benar dijalankan di node.

### 3.5. Struktur Task

Task yang dihasilkan berbentuk seperti ini:

```python
return {
    "task_id": ...,
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
    "task_size": classify_task(...),
    "experiment_id": "exp_1",
}
```

Field penting untuk eksperimen:

- `cpu_demand`
- `memory_demand`
- `cpu_time_target_ms`
- `memory_bytes`
- `task_size`
- `payload.seed`

## 4. Baseline Random

Sebelum optimasi dijalankan, sistem terlebih dahulu membentuk baseline `random`.

```python
for idx in range(N_RANDOM_BASELINES):
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)
```

Saat ini baseline random default dijalankan `5` kali.

Tujuannya:

- mengurangi bias karena satu assignment acak bisa terlalu bagus atau terlalu buruk,
- membuat pembanding lebih stabil,
- menghasilkan referensi yang lebih fair untuk eksperimen optimasi.

Hasil 5 run ini lalu dirata-ratakan:

```python
metrics_random = aggregate_metrics(random_metric_runs)
```

Baseline random ini dipakai untuk:

- membandingkan performa akhir,
- menghitung `E_ref`,
- menghitung `L_ref`.

## 5. Parameter Referensi `E_ref` dan `L_ref`

Setelah baseline random dihitung, sistem membentuk referensi:

```python
e_ref = max(metrics_random["model_total_energy"], 1e-6)
l_ref = max(metrics_random["model_avg_latency"], 1e-6)
```

Maknanya:

- `E_ref` adalah energi model dari baseline random,
- `L_ref` adalah latency model dari baseline random,
- keduanya dipakai untuk normalisasi objective function.

Dengan pendekatan ini, objective menjadi relatif terhadap baseline random, sehingga skala antar eksperimen lebih konsisten.

## 6. Jalur Eksperimen Optimasi Hibrida

Eksperimen utama pada alur sistem ini dijalankan dengan mode:

```python
"tabu_legacy_hybrid"
```

Mode ini diproses di [`central/offline_runner.py`](/home/adinda-central/edge-computing-system/central/offline_runner.py):

```python
assignments, history = tabu_assignment_legacy_hybrid_objective(...)
```

Jadi assignment task ke node tidak lagi acak, tetapi dicari dengan optimasi tabu berbasis objective hibrida.

## 7. Objective Hibrida

Bagian penting metodologi `main3.py` ada di [`central/assignment_engine.py`](/home/adinda-central/edge-computing-system/central/assignment_engine.py), yaitu fungsi:

- `tabu_assignment_legacy_hybrid_objective(...)`

Di dalamnya terdapat objective function:

```python
legacy_cost, _, _ = objective_value_legacy(...)
vps_cost, _ = compute_total_cost_energy_focused(...)
return legacy_cost + (vps_penalty_scale * vps_cost), None
```

Maknanya:

- `legacy_cost` berasal dari objective simulasi program lama,
- `vps_cost` berasal dari objective yang lebih sesuai dengan karakter VPS,
- `vps_penalty_scale` mengatur seberapa kuat pengaruh penalti VPS terhadap cost akhir.

Jadi cost yang dioptimasi oleh `main3.py` bukan:

- murni cost simulasi lama,
- dan juga bukan murni cost VPS,

melainkan:

- **cost simulasi lama + penalti kondisi VPS**.

### 7.1. Objective Simulasi Lama

Objective simulasi lama ada di [`central/legacy_simulation_objective.py`](/home/adinda-central/edge-computing-system/central/legacy_simulation_objective.py).

Strukturnya:

```python
cost = (
    weight_energy * (energy / max(e_ref, 1e-6))
    + weight_latency * (latency / max(l_ref, 1e-6))
)
```

Energinya dihitung dari model sederhana:

```python
p_idle = 10.0
p_cpu_dyn = 12.0
p_mem_dyn = 5.0
p_sleep = 2.0
```

Sedangkan latency-nya dihitung dari:

- `service_time`
- `queue_delay`
- `mem_penalty`

Jadi objective lama bersifat abstrak dan agregat.

### 7.2. Penalti VPS

Penalti VPS berasal dari:

```python
compute_total_cost_energy_focused(...)
```

Maknanya:

- assignment tidak hanya dinilai dari model simulasi,
- tetapi juga dikoreksi oleh aspek yang lebih dekat ke karakter node nyata,
- seperti beban CPU, memori, power profile node, dan penalti penggunaan high-tier.

Inilah alasan pendekatan ini disebut hibrida.

## 8. Mekanisme Optimasi Tabu dan Diffusion

Optimasi assignment berjalan melalui:

```python
best_assign, history = hybrid_tabu_diff(...)
```

Parameter utamanya:

```python
TABU_MAX_ITER=300
TABU_TENURE=30
NUM_MOVES=70
```

Maknanya:

- tabu search mengeksplorasi perpindahan task antar node,
- beberapa solusi sementara dilarang untuk mencegah kembali ke pola lama,
- `history["obj"]` menyimpan perkembangan nilai objective terbaik sepanjang iterasi.

Pada mode `hybrid`, diffusion optimizer juga ikut dilibatkan untuk memperbaiki solusi secara lokal.

Setelah itu, assignment akhir dikembalikan dalam bentuk:

```python
assignments[task["task_id"]] = node_id
```

## 9. Seed Assignment Awal

Sebelum tabu search berjalan, sistem membangun assignment awal dari heuristic:

```python
assign_seed = optimized_assignment(tasks, active_nodes)
init_assign = np.array([...])
```

Maknanya:

- optimasi tidak mulai dari assignment acak murni,
- tetapi dari solusi awal yang sudah cukup masuk akal,
- ini membantu tabu search mencapai solusi lebih stabil dan lebih cepat.

## 10. Pengiriman Task ke Edge Node

Setelah assignment dipilih, sistem mulai mengirim task satu per satu ke node yang ditentukan.

Di [`central/offline_runner.py`](/home/adinda-central/edge-computing-system/central/offline_runner.py):

```python
for task in tasks:
    task_id = task["task_id"]
    node_id = assignments[task_id]
    send_task_to_node(task, node_id)
```

Pengiriman dilakukan melalui HTTP:

```python
url = f"http://{node['ip']}:{node['port']}/tasks"
response = requests.post(url, json=task, timeout=10)
```

Jadi task benar-benar dikirim ke edge node tertentu sesuai hasil optimasi.

## 11. Penerimaan Task di Edge Node

Di sisi node, task diterima oleh FastAPI pada [`edge/edge_node.py`](/home/adinda-central/edge-computing-system/edge/edge_node.py):

```python
@app.post("/tasks")
async def receive_task(task: Task):
    ...
    await app.state.task_queue.put(task)
```

Maknanya:

- node menerima task dari central,
- task dimasukkan ke queue,
- worker loop kemudian memproses task tersebut.

Sistem juga menyimpan status:

- `queued`
- `processing`
- `completed`

## 12. Eksekusi Riil Workload di Edge Node

Task tidak hanya direpresentasikan sebagai angka. Task benar-benar dijalankan sebagai workload CPU dan memori.

Di [`edge/edge_node.py`](/home/adinda-central/edge-computing-system/edge/edge_node.py):

```python
while total_task_clock_ms < target_cpu_ms:
    task_clock_ms, cpu_clock_ms, worker_output = await asyncio.to_thread(
        run_perf_chunk,
        memory_bytes,
        chunk_seed,
        touch_rounds,
    )
```

Maknanya:

- node akan menjalankan workload per chunk,
- setiap chunk diukur dengan `perf`,
- loop terus berjalan sampai total `task-clock` mencapai target `cpu_time_target_ms`.

Jadi `cpu_time_target_ms` bukan hanya angka teoritis, tetapi menjadi target eksekusi nyata.

## 13. Penggunaan `perf`

Workload dijalankan melalui:

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
    ...
]
```

Metrik yang diambil:

- `task-clock`
- `cpu-clock`

Kemudian diparse:

```python
task_clock_ms = parse_perf_time_ms(proc.stderr, "task-clock")
cpu_clock_ms = parse_perf_time_ms(proc.stderr, "cpu-clock")
```

Dengan demikian, sistem memperoleh pengukuran aktivitas CPU riil, bukan hanya asumsi model.

## 14. Workload Worker

Workload chunk dijalankan di [`edge/workload_worker.py`](/home/adinda-central/edge-computing-system/edge/workload_worker.py).

Di sana ada konfigurasi tier:

```python
TIER_CONFIG = {
    "low": {"vector_size": 128, "compute_rounds": 2},
    "mid": {"vector_size": 256, "compute_rounds": 4},
    "high": {"vector_size": 512, "compute_rounds": 8},
}
```

Maknanya:

- node low-tier menjalankan chunk yang lebih ringan,
- node mid-tier menjalankan chunk sedang,
- node high-tier menjalankan chunk lebih berat.

Workload yang dijalankan meliputi:

- alokasi buffer memori,
- touch halaman memori,
- komputasi vektor berulang,
- checksum hasil.

Jadi task benar-benar menggunakan:

- CPU
- memori

sesuai karakter node dan parameter task.

## 15. Hasil Eksekusi yang Dikembalikan Node

Setelah task selesai, node mengembalikan hasil seperti:

```python
result_payload = {
    "task_type": task.task_type,
    "executor_node": NODE_ID,
    "execution_time": execution_time,
    "observed_task_clock_ms": float(total_task_clock_ms),
    "observed_cpu_clock_ms": float(total_cpu_clock_ms),
    "observed_memory_bytes": int(memory_bytes),
    "chunks": int(chunks),
    "output": last_output,
}
```

Metrik penting:

- `execution_time`
- `observed_task_clock_ms`
- `observed_cpu_clock_ms`
- `observed_memory_bytes`
- `chunks`

## 16. Pengumpulan Hasil di Central

Central menunggu semua hasil task:

```python
result = wait_for_result(task_id, node_id, timeout=120)
```

Lalu menyimpannya ke struktur hasil:

```python
row = {
    "task_id": task_id,
    "latency": result.get("latency"),
    "execution_time": result.get("execution_time"),
    "node": node_id,
    "executor_node": ...,
    "observed_task_clock_ms": ...,
    "observed_cpu_clock_ms": ...,
    "observed_memory_bytes": ...,
}
```

Jadi setelah semua task selesai, central memiliki data lengkap untuk evaluasi.

## 17. Perhitungan Metrik Akhir

Perhitungan metrik dilakukan oleh `compute_metrics(...)` di [`central/offline_runner.py`](/home/adinda-central/edge-computing-system/central/offline_runner.py).

Metrik yang dihitung antara lain:

- `real_avg_latency`
- `real_total_latency`
- `real_avg_execution_time`
- `real_total_execution_time`
- `estimated_real_energy_j`
- `estimated_real_energy_kwh`
- `real_avg_task_clock_ms`
- `real_total_task_clock_ms`
- `model_avg_latency`
- `model_total_energy`

Dengan kata lain, evaluasi akhir dilakukan dari dua sisi:

- sisi real execution,
- sisi model.

## 18. Perhitungan Energi Riil

Energi riil tidak diambil dari objective simulasi lama. Energi riil dihitung dari hasil observasi task nyata.

Di [`central/offline_runner.py`](/home/adinda-central/edge-computing-system/central/offline_runner.py):

```python
task_clock_ms = result_row.get("observed_task_clock_ms")
cpu_clock_ms = result_row.get("observed_cpu_clock_ms")
```

Lalu dikombinasikan dengan:

- `cpu_demand`
- `memory_demand`
- `idle_power_w`
- `max_power_w`

Jadi evaluasi energi tetap memakai evaluator yang sama dengan sistem VPS saat ini. Yang berubah dalam pendekatan ini hanyalah objective optimasinya.

## 19. Makna Metodologis Pendekatan Ini

Secara metodologi, pendekatan ini dapat dijelaskan sebagai berikut:

- task generator sudah data-driven,
- task dibangkitkan dari pola hasil kalibrasi sebelumnya,
- baseline random dijalankan beberapa kali untuk stabilitas,
- objective optimasi memakai model simulasi lama,
- tetapi cost simulasi lama ditambah penalti VPS agar solusi lebih sesuai dengan kondisi node nyata,
- task hasil assignment dijalankan sungguhan di edge node,
- hasil akhirnya dievaluasi memakai latency riil dan energi hasil konversi dari data riil.

Dengan demikian, pendekatan ini menjadi jembatan antara:

- simulasi program,
- dan implementasi VPS riil.

## 20. Ringkasan Alur Lengkap

Ringkasan alur kerja sistem:

1. `main3.py` memanggil `generate_batch(N_TASKS)`.
2. `task_generator.py` membentuk task dari data kalibrasi atau fallback teoritis.
3. `main3.py` menjalankan baseline `random` sebanyak `N_RANDOM_BASELINES`.
4. hasil baseline dirata-ratakan untuk membentuk `metrics_random`.
5. `E_ref` dan `L_ref` dibentuk dari hasil baseline random.
6. `run_offline_experiment(..., "tabu_legacy_hybrid")` dipanggil.
7. `assignment_engine.py` menjalankan tabu search dengan objective:
   `legacy_cost + vps_penalty_scale * vps_cost`.
8. assignment task ke node dihasilkan.
9. `offline_runner.py` mengirim task ke edge node yang dipilih.
10. `edge_node.py` menerima task dan memasukkannya ke queue.
11. `edge_node.py` mengeksekusi workload per chunk menggunakan `perf`.
12. `workload_worker.py` menjalankan beban CPU dan memori nyata.
13. hasil `task-clock`, `cpu-clock`, latency, dan memory usage dikembalikan.
14. central mengumpulkan seluruh hasil task.
15. `compute_metrics()` menghitung metrik real dan model.
16. hasil random dan hasil optimasi dibandingkan.

## 21. Posisi Dokumen Ini dalam Metodologi

Jika dipakai di bagian metodologi laporan, dokumen ini bisa dibagi menjadi beberapa subbagian:

- pembangkitan task
- baseline random
- objective function hibrida
- mekanisme optimasi tabu-diffusion
- eksekusi riil pada edge node
- pengukuran metrik real
- evaluasi latency dan energi

Jika diperlukan, dokumen ini masih bisa dikembangkan lagi menjadi:

- versi yang lebih formal untuk laporan akhir,
- versi yang lebih ringkas untuk presentasi,
- atau versi yang ditambah diagram alur dan sequence diagram.
