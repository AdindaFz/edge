# Base Knowledge TA Sistem Edge Computing

Tanggal pembaruan: 2026-05-02

Status dokumen: draft kerja sementara untuk upgrade penulisan TA/skripsi. Dokumen ini merangkum sistem saat ini berdasarkan kode, notebook, dataset, output eksperimen, dan catatan metodologi terbaru.

Prinsip penting: penelitian ini tidak boleh dijelaskan sebagai satu alur tunggal yang langsung dari teori ke VPS. Alur yang benar terdiri dari dua fase besar:

1. Fase simulasi program melalui `Comparision.ipynb`.
2. Fase implementasi dan validasi VPS melalui `main3.py`.

Fase simulasi dipakai untuk membandingkan kandidat optimizer pada lingkungan simulasi yang terkontrol. Fase VPS dipakai untuk menjalankan kandidat terpilih pada edge node nyata dan membandingkannya terhadap baseline random.

## 1. Inti Penelitian

Penelitian ini membahas penjadwalan task pada sistem edge computing heterogen. Permasalahan utama adalah bagaimana mendistribusikan sekumpulan task ke beberapa edge node dengan kapasitas berbeda agar performa sistem lebih baik dari baseline.

Tujuan teknis utama:

1. Meminimalkan objective gabungan berbasis energi dan latency pada simulasi.
2. Membandingkan beberapa kombinasi global optimizer dan local optimizer.
3. Memilih kandidat terbaik berdasarkan final objective, time-to-target, dan runtime.
4. Memvalidasi kandidat pada sistem VPS nyata dengan metrik real latency, execution time, task-clock, dan estimasi energi.

Kontribusi yang aman untuk ditulis:

1. Merancang workflow dua fase: simulation-based comparison dan VPS-based validation.
2. Membandingkan kombinasi Tabu Search, BFO, PSO dengan local method none, CPM, dan Diffusion.
3. Menggunakan dataset berbasis Google Cluster Trace untuk simulasi task scheduling.
4. Menggunakan task generator data-driven dari calibration logs untuk implementasi VPS.
5. Mengukur performa VPS dengan workload nyata `cpu_mem_burn` dan metrik `perf`.

Klaim yang harus hati-hati:

1. Jangan menulis bahwa `TABU+DIFFUSION` selalu paling unggul jika hasil final belum membuktikan itu.
2. Saat ini `TABU+DIFFUSION` sangat kompetitif, tetapi pada single-run terbaru final objective terbaik masih `TABU+NONE`.
3. Posisi `TABU+DIFFUSION` tetap kuat sebagai metode hybrid karena mencapai target lebih cepat di keluarga Tabu dan menjadi kandidat implementasi VPS.

## 2. Artefak Utama Sistem

File penting fase simulasi:

| File | Fungsi |
|---|---|
| `Comparision.ipynb` | Notebook utama comparison simulation. |
| `system_model.py` | Model pendukung untuk notebook comparison. |
| `run_comparison_models.py` | Runner otomatis untuk single-run screening dari notebook. |
| `run_comparison_cdf.py` | Runner otomatis untuk CDF top-3 dari notebook. |
| `outputs/comparison_notebook/comparison_summary.csv` | Ringkasan hasil single-run screening. |
| `outputs/comparison_notebook/objective_convergence.svg` | Grafik konvergensi objective. |
| `outputs/comparison_notebook/cdf_top3_objective_50.log` | Log CDF top-3 yang sedang/baru dijalankan. |

File penting fase VPS:

| File | Fungsi |
|---|---|
| `main3.py` | Entry point implementasi VPS terbaru. |
| `central/task_generator.py` | Pembangkitan task data-driven dari calibration logs. |
| `central/offline_runner.py` | Pengiriman task, pengumpulan hasil, dan perhitungan metrik. |
| `central/assignment_engine.py` | Random assignment, optimized seed, Tabu, Tabu legacy, dan Tabu legacy hybrid. |
| `central/optimizer_runner.py` | Implementasi Tabu Search dan objective dengan VPS penalties. |
| `central/local_optimizers.py` | Implementasi Diffusion local optimizer. |
| `central/node_resources.py` | Konfigurasi resource 9 edge node. |
| `edge/workload_worker.py` | Workload CPU-memory burn yang dijalankan di edge node. |
| `outputs/main3_energy_first_selected_200_300_400.json` | Hasil validasi VPS untuk 200, 300, dan 400 task. |

Dokumen pendukung:

| File | Fungsi |
|---|---|
| `BASE_KNOWLEDGE_MAPPING_CURRENT.md` | Pemetaan base knowledge lama terhadap sistem saat ini. |
| `METHODOLOGY_MAIN3_FLOW.md` | Penjelasan metodologi `main3.py`. |
| `TASK_EXECUTION_FLOW.md` | Penjelasan flow task generator dan eksekusi edge. |
| `CPU_DEMAND_GENERATION_ANALYSIS.md` | Analisis pembangkitan CPU demand. |
| `CALIBRATION_VALIDATION_REPORT.md` | Validasi model kalibrasi. |
| `IMPLEMENTATION_SUMMARY_DATA_DRIVEN.md` | Ringkasan implementasi data-driven task generation. |

## 3. Alur Penelitian yang Disarankan

Alur penulisan metodologi sebaiknya dibuat seperti ini:

1. Studi literatur dan perumusan masalah task scheduling pada edge computing.
2. Pembangunan simulasi edge heterogen 3x3.
3. Pembentukan dataset simulasi dari machine dataset dan task dataset.
4. Pembentukan baseline Round-Robin sebagai pembanding simulasi.
5. Perbandingan optimizer pada `Comparision.ipynb`.
6. Evaluasi single-run berdasarkan final objective, time-to-target, dan runtime.
7. Pemilihan top-3 berdasarkan final objective untuk pengujian CDF.
8. Pemilihan kandidat implementasi VPS.
9. Validasi kandidat pada VPS dengan baseline random.
10. Analisis hasil simulasi dan hasil VPS secara terpisah.

Frasa inti yang aman:

```text
Penelitian ini menggunakan pendekatan dua fase. Fase pertama melakukan simulasi dan perbandingan beberapa kandidat optimizer pada lingkungan edge heterogen terkontrol. Fase kedua mengimplementasikan kandidat terpilih pada lingkungan VPS untuk memvalidasi perilaku metode pada eksekusi task nyata.
```

## 4. Dataset

### 4.1 Dataset Simulasi

Fase simulasi memakai dua sumber dataset lokal:

| Dataset | Ukuran lokal | Peran |
|---|---:|---|
| `part-00000-of-00001.csv` | 37,780 baris | Machine/resource dataset. |
| `spreadsheet_export.csv` | 504,567 baris | Task dataset utama untuk comparison terbaru. |
| `cpm_pso_input_part10_19_timeseries.csv` | 291,624 baris | Dataset lama yang masih tersedia, tetapi bukan sumber utama run terbaru. |

Catatan penting:

1. `spreadsheet_export.csv` memiliki kolom seperti `job_id`, `task_index`, `queue_delay`, `service_time`, `cpu_req`, `mem_req`, dan `priority`.
2. Untuk comparison notebook, task yang dipakai disampling menjadi `MAX_TASKS = 300`.
3. Jika kolom latency dataset tidak tersedia, notebook/runner menyediakan fallback kompatibilitas seperti `latency_ms = 0.0`.
4. Penulisan skripsi harus konsisten memilih dataset final. Untuk sistem saat ini, yang paling cocok ditulis adalah `spreadsheet_export.csv` karena itu yang dipakai pada comparison terbaru.

### 4.2 Dataset/Kalibrasi VPS

Fase VPS tidak hanya memakai task acak teoritis. Sistem menggunakan data-driven task generation dari calibration logs untuk membentuk karakteristik beban kerja yang lebih mendekati kondisi nyata.

Sumber:

```text
outputs/calibration/workload_calibration_*.jsonl
outputs/calibration/cpu_time_unit_calibration.json
```

Mekanismenya:

1. `generate_batch(n_tasks, seed=42)` membuat task batch deterministik berdasarkan seed.
2. `generate_task(...)` memanggil `load_cpu_time_unit_ms()` untuk membaca satuan CPU terkalibrasi dari `cpu_time_unit_calibration.json`.
3. Jika calibration logs ditemukan, generator memuat sampel task dari `workload_calibration_*.jsonl` yang memiliki `cpu_demand` dan `memory_demand`.
4. Nilai demand tersebut diberi variasi acak kecil (~5%) untuk menghindari task identik dan tetap menjaga pola kalibrasi.
5. Hasilnya dikunci pada rentang valid: `cpu_demand` antara 0.8 dan 3.6, `memory_demand` antara 0.125 dan 0.75.
6. Nilai demand dikonversi menjadi parameter eksekusi nyata:
   - `cpu_time_target_ms = cpu_demand * cpu_time_unit_ms`
   - `memory_bytes = memory_demand * 1 GB`
7. Jika data kalibrasi tidak tersedia, generator fallback ke mode teoritis dengan `cpu_time_target_ms` seragam di rentang 200-900 ms dan `memory_bytes` seragam di rentang 128-768 MB.

Contoh cuplikan kode dari `central/task_generator.py`:

```python
cpu_time_unit_ms = load_cpu_time_unit_ms()
calibration_tasks = load_calibration_data()
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
```

Dalam `main3.py`, batch task tersebut menjadi input untuk baseline random dan optimasi hybrid:

```python
tasks = generate_batch(N_TASKS)
for idx in range(N_RANDOM_BASELINES):
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)

metrics_random = aggregate_metrics(random_metric_runs)
e_ref = metrics_random["model_total_energy"]
l_ref = metrics_random["model_avg_latency"]
res_tabu_legacy_hybrid, _ = run_offline_experiment(
    tasks,
    "tabu_legacy_hybrid",
    E_ref=e_ref,
    L_ref=l_ref,
    local_mode=LEGACY_LOCAL_MODE,
    tabu_energy_weight=LEGACY_ENERGY_WEIGHT,
)
```

Setiap task yang dibentuk berisi metadata tambahan yang diperlukan untuk eksekusi VPS:

- `task_id`
- `cpu_demand`, `memory_demand`
- `cpu_time_target_ms`, `memory_bytes`
- `task_type = "cpu_mem_burn"`
- `payload` dengan `seed` dan `touch_rounds`
- `arrival_time = 0.0`
- `task_size` klasifikasi `small/medium/large`

Klasifikasi task menggunakan `classify_task(cpu_time_target_ms, memory_bytes)` dengan batas kalibrasi yang disesuaikan:

- small: `cpu_time_target_ms < 325 ms` dan `memory_bytes < 0.25 GB`
- medium: `cpu_time_target_ms < 675 ms` dan `memory_bytes < 0.75 GB`
- large: selain itu

Ini membuat task batch VPS tidak sekadar acak, tetapi masih mempertahankan pembagian ukuran tugas yang mencerminkan distribusi beban kalibrasi.

Dalam alur `main3.py`, batch task ini menjadi input untuk:

- menjalankan beberapa random baseline; lalu rata-ratakan metriknya untuk membentuk `E_ref` dan `L_ref`,
- menjalankan optimasi `tabu_legacy_hybrid` pada task yang sama,
- mengirim assignment ke edge nodes, menunggu eksekusi, dan mengumpulkan metrik nyata.

Catatan metodologis penting:

- Fase VPS menekankan validasi eksekusi nyata dengan menganalisis `real_avg_latency`, `real_total_latency`, `real_avg_execution_time`, dan estimasi energi berdasarkan `observed_task_clock_ms` dan `observed_cpu_clock_ms`.
- `time-to-target` tidak dihitung eksplisit di `main3.py`; pada fase VPS, fokus utama adalah metrik real dan objective hybrid, sementara konvergensi optimasi dicatat dalam sejarah objective `history["obj"]` dan waktu `history["time"]`.

Nilai kalibrasi penting:

```text
CPU_TIME_UNIT_MS sekitar 372.235 ms untuk tier referensi mid.
```

### 4.3 Komunikasi dan Eksekusi Task antar Node

Alur komunikasi antara central node dan edge node dilakukan melalui HTTP. Central memeriksa kesehatan node dengan endpoint `/health`, lalu mengirim task ke node aktif melalui endpoint `/tasks`.

Contoh cuplikan kode di `central/offline_runner.py`:

```python
url = f"http://{node['ip']}:{node['port']}/tasks"
response = requests.post(url, json=task, timeout=10)
response.raise_for_status()
```

Setiap edge node menjalankan FastAPI pada port masing-masing. Ketika task diterima, node menyimpan status `queued` dan menempatkan task ke antrean eksekusi.

Edge node kemudian menjalankan workload nyata dengan `perf` menggunakan `edge/workload_worker.py`, mengumpulkan metrik:

- `task-clock`
- `cpu-clock`
- `execution_time`
- `observed_memory_bytes`

Contoh alur eksekusi di `edge/edge_node.py`:

```python
@app.post("/tasks")
async def receive_task(task: Task):
    await app.state.task_queue.put(task)
    return {"task_id": task.task_id, "status": "queued"}
```

Setelah task selesai, node memperbarui status menjadi `completed` dan informasi hasil dapat diambil oleh central melalui endpoint `/tasks/{task_id}`.

```python
@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    return task_results[task_id]
```

### 4.4 Baseline dan Evaluasi pada VPS

Evaluasi VPS dimulai dengan membentuk random baseline. `main3.py` menjalankan `run_offline_experiment(tasks, "random")` beberapa kali, lalu merata-ratakan metrik hasil run tersebut.

Cuplikan kode baseline di `main3.py`:

```python
random_metric_runs = []
for idx in range(N_RANDOM_BASELINES):
    res_random, _ = run_offline_experiment(tasks, "random", return_history=True)
    metrics_random = compute_metrics(res_random, tasks, NODE_RESOURCES)
    random_metric_runs.append(metrics_random)

metrics_random = aggregate_metrics(random_metric_runs)
```

Hasil rata-rata baseline random digunakan sebagai referensi untuk normalisasi objective VPS:

```python
e_ref = max(metrics_random["model_total_energy"], 1e-6)
l_ref = max(metrics_random["model_avg_latency"], 1e-6)
```

Setelah baseline terbentuk, sistem menjalankan optimasi `tabu_legacy_hybrid` pada task batch yang sama. Perbandingan akhir dilakukan dengan menggunakan metrik real dan model yang dihasilkan oleh `compute_metrics`.

Metrik evaluasi VPS mencakup:

- Real metrics: `real_avg_latency`, `real_total_latency`, `real_avg_execution_time`, `real_total_task_clock_ms`, `estimated_real_energy_j`
- Model metrics: `model_avg_latency`, `model_total_energy`
- Distribusi task per node

Compare table dibuat dengan `print_all_comparison_table(metrics_random, metrics_tabu_legacy_hybrid, n_tasks=N_TASKS)` untuk melihat perbedaan antara random baseline dan optimized assignment.

Bagian ini penting karena menegaskan bahwa baseline VPS adalah random average, bukan Round-Robin, dan evaluasi dilakukan terhadap metrik eksekusi nyata serta estimasi energi yang dihitung dari hasil perf.

## 5. Model Sistem Simulasi

Simulasi pada `Comparision.ipynb` memakai sistem edge heterogen berbentuk grid 3x3. Kapasitas node diambil dari machine dataset dan dikelompokkan menjadi low, mid, dan high berdasarkan skor kapasitas gabungan CPU-memory.

Parameter utama:

| Parameter | Nilai |
|---|---:|
| `Nx, Ny` | 3, 3 |
| Jumlah node | 9 |
| `MAX_TASKS` | 300 |
| `GLOBAL_SEED` | 2026 |
| `MACHINE_SEED` | 111 |
| `TASK_SEED` | 222 |
| `OPTIMIZER_SEED` | 333 |
| `alpha_cpu` | 0.4 |
| `beta_mem` | 0.6 |
| `weight_energy` | 0.5 |
| `weight_latency` | 0.5 |

Satuan `cpu_capacity`, `memory_capacity`, `cpu_req`, dan `mem_req` pada dataset adalah normalized resource fraction, bukan GHz, core, atau GB absolut. Karena kapasitas node dan demand task berasal dari skema normalisasi yang sama, nilai demand task dapat dibandingkan langsung dengan kapasitas node untuk menghitung utilisasi.

Skor kapasitas node:

```text
capacity_score = alpha_cpu * cpu_capacity + beta_mem * memory_capacity
```

Pengelompokan tier dilakukan pada level kapasitas unik agar tidak bias terhadap jumlah mesin yang memiliki nilai kapasitas sama. Setelah itu, notebook mengambil 3 node low, 3 node mid, dan 3 node high.

Karakteristik node pada simulasi diselaraskan dengan konfigurasi VPS agar model tidak hanya heterogen pada kapasitas CPU dan memori, tetapi juga pada estimasi daya dan delay jaringan.

| Tier | Node simulasi | Idle power | Max power | Network delay |
|---|---|---:|---:|---:|
| Low | 0, 1, 2 | 8 W | 18 W | 0.030-0.040 s |
| Mid | 3, 4, 5 | 14 W | 32 W | 0.022-0.028 s |
| High | 6, 7, 8 | 24 W | 55 W | 0.015-0.020 s |

Topologi local method:

```text
Grid 3x3 dengan 4-neighbor adjacency:
atas, bawah, kiri, kanan.
```

Baseline simulasi:

```text
Round-Robin assignment
baseline objective = 1.0
```

Objective simulasi:

```text
objective = weight_energy * (E / E_ref) + weight_latency * (L / L_ref)
```

Makna:

1. `E_ref` adalah energy baseline Round-Robin.
2. `L_ref` adalah latency baseline Round-Robin.
3. Objective lebih kecil berarti solusi lebih baik.
4. Improvement terhadap Round-Robin dihitung dari `1.0 - final_obj`.
5. Bobot objective simulasi diselaraskan dengan default objective VPS, yaitu energy 0.5 dan latency 0.5.
6. Energy simulasi memakai pendekatan power-aware berdasarkan `idle_power`, `max_power`, utilisasi CPU, utilisasi memori, dan penalti overload.
7. Latency simulasi memakai pendekatan network-aware dengan komponen service time, queue delay, memory overload penalty, dan per-node network delay.

## 6. Metode pada Fase Simulasi

Comparison notebook menjalankan 9 kombinasi:

| Global optimizer | Local method |
|---|---|
| Tabu Search | None |
| Tabu Search | Diffusion |
| Tabu Search | CPM |
| BFO | None |
| BFO | Diffusion |
| BFO | CPM |
| PSO | None |
| PSO | Diffusion |
| PSO | CPM |

### 6.1 Tabu Search

Tabu Search dipakai sebagai global optimizer berbasis pencarian neighborhood.

Parameter terbaru pada notebook:

| Parameter | Nilai |
|---|---:|
| `TABU_MAX_ITER` | 300 |
| `TABU_TENURE` | 30 |
| `TABU_CANDIDATE_MOVES` | 70 |

Konsep yang sesuai teori:

1. Menghasilkan kandidat solusi dari perubahan assignment task.
2. Menyimpan move tertentu dalam tabu list agar pencarian tidak kembali berputar pada solusi yang sama.
3. Memakai aspiration criterion ketika kandidat tabu menghasilkan solusi global yang lebih baik.
4. Memakai mekanisme diversifikasi ketika stagnasi.

Catatan:

```text
Tabu-Diffusion saat ini masih berada dalam koridor teori Tabu Search karena Diffusion dipakai sebagai local refinement/escape mechanism, bukan mengganti mekanisme Tabu utama.
```

### 6.2 Diffusion Local Refinement

Diffusion adalah local method berbasis perpindahan task ke node tetangga yang lebih baik menurut local cost.

Parameter tuning notebook:

| Parameter | Nilai |
|---|---:|
| `gamma` | 0.08 |
| `max_steps` | 1 |
| `objective_epsilon` | 1e-12 |
| Trigger | adaptif, hanya saat Tabu stagnan |

Makna:

1. Diffusion mengevaluasi perpindahan lokal task ke node kandidat menggunakan local cost berbasis energy-latency.
2. Local cost mempertimbangkan projected CPU utilization, projected memory utilization, power tier, dan network delay.
3. Task hanya dipindahkan ke node kandidat jika local score membaik setidaknya sebesar `gamma`.
4. Pada notebook yang diselaraskan dengan VPS, adjacency Diffusion memakai all-to-all candidate nodes.
5. Diffusion tidak lagi dipanggil secara periodik setiap beberapa iterasi. Diffusion hanya dipicu ketika Tabu Search mengalami stagnasi, sehingga berfungsi sebagai mekanisme escape/refinement yang konservatif.
6. Hasil Diffusion hanya diterima oleh Tabu jika memperbaiki global best atau minimal memperbaiki current search basin.

### 6.3 CPM Local Method

CPM dipakai sebagai local refinement berbasis hubungan node pada grid. Di notebook, CPM membantu mengevaluasi perpindahan assignment pada neighborhood lokal.

Catatan penulisan:

```text
CPM sebaiknya dijelaskan sebagai local/topology-aware refinement, bukan sebagai global optimizer.
```

### 6.4 BFO dan PSO

BFO dan PSO dipakai sebagai pembanding global optimizer. Keduanya penting untuk menunjukkan bahwa metode berbasis Tabu tidak dibandingkan hanya terhadap satu baseline sederhana.

Peran dalam skripsi:

1. BFO dan PSO menjadi pembanding metaheuristik.
2. Hasilnya dipakai untuk menunjukkan trade-off kualitas objective dan waktu komputasi.
3. PSO cenderung lebih cepat, tetapi objective pada hasil terbaru lebih tinggi dibanding keluarga Tabu.

## 7. Metrik Evaluasi Simulasi

Urutan metrik utama yang disarankan untuk reviewer:

1. `final_obj / best_obj`
2. `time_to_target`
3. `runtime`

Definisi:

| Metrik | Makna | Arah terbaik |
|---|---|---|
| `final_obj` | Objective pada solusi akhir | Lebih kecil |
| `best_obj` | Objective terbaik yang pernah ditemukan | Lebih kecil |
| `time_to_target` | Waktu mencapai objective <= 0.75 | Lebih kecil |
| `runtime` | Total waktu komputasi optimizer | Lebih kecil |
| `energy` | Komponen energy simulasi | Lebih kecil |
| `latency` | Komponen latency simulasi | Lebih kecil |
| `improvement_vs_rr_pct` | Improvement terhadap Round-Robin | Lebih besar |

Ranking utama pada notebook terbaru:

```text
final_obj -> time_to_target_s -> runtime_s
```

Top-3 untuk CDF dipilih berdasarkan final objective terbaik, bukan `rank_total`.

Alasan:

```text
Dalam problem optimasi, kualitas solusi harus menjadi kriteria utama. Runtime dan time-to-target tetap penting, tetapi tidak boleh mengeluarkan model dengan objective terbaik dari validasi statistik.
```

## 8. Hasil Simulasi Terbaru

Sumber: `outputs/comparison_notebook/comparison_summary.csv`

Catatan status: tabel hasil pada bagian ini berasal dari konfigurasi objective sebelumnya. Setelah bobot simulasi diselaraskan menjadi energy 0.5 dan latency 0.5 serta model energy-latency dibuat VPS-aware, screening dan CDF perlu dijalankan ulang sebelum angka final digunakan dalam skripsi.

| Model | Final objective | Best objective | Runtime (s) | TTT 0.75 (s) |
|---|---:|---:|---:|---:|
| `TABU+NONE` | 0.6534216 | 0.6534216 | 31.2294 | 3.1346 |
| `TABU+CPM` | 0.6534964 | 0.6534964 | 31.6344 | 3.2560 |
| `TABU+DIFFUSION` | 0.6535456 | 0.6535456 | 32.0331 | 3.0194 |
| `BFO+DIFFUSION` | 0.6824875 | 0.6824875 | 42.5672 | 7.8659 |
| `BFO+NONE` | 0.6839014 | 0.6839014 | 34.4618 | 8.1628 |
| `PSO+DIFFUSION` | 0.7183386 | 0.7183386 | 9.0084 | 2.4381 |
| `PSO+CPM` | 0.7191137 | 0.7191137 | 6.7837 | 0.9018 |
| `PSO+NONE` | 0.7227598 | 0.7227598 | 6.2312 | 1.5537 |
| `BFO+CPM` | 0.7341181 | 0.7341181 | 36.0411 | 18.9017 |

Interpretasi sementara:

1. Top-3 berdasarkan final objective adalah `TABU+NONE`, `TABU+CPM`, dan `TABU+DIFFUSION`.
2. Seluruh top-3 berasal dari keluarga Tabu, sehingga Tabu Search terbukti kuat pada simulasi ini.
3. `TABU+DIFFUSION` tidak menjadi final objective terbaik pada single-run ini, tetapi selisihnya sangat kecil.
4. `TABU+DIFFUSION` memiliki time-to-target terbaik di antara varian Tabu.
5. PSO lebih cepat secara runtime, tetapi final objective lebih tinggi dibanding keluarga Tabu.

Selisih penting:

```text
TABU+NONE vs TABU+DIFFUSION:
0.6535456 - 0.6534216 = 0.0001240
```

Narasi aman:

```text
Pada single-run screening, keluarga Tabu menghasilkan kualitas solusi terbaik. Varian Tabu-Diffusion menunjukkan performa yang sangat kompetitif dan mencapai target lebih cepat dibanding varian Tabu lain, meskipun final objective terbaik pada run ini diperoleh Tabu tanpa local refinement.
```

## 9. CDF Top-3

Tujuan CDF:

1. Menguji stabilitas model top-3 dari single-run.
2. Melihat distribusi objective dari banyak run.
3. Menghindari klaim hanya berdasarkan satu run.

Top-3 yang dipilih:

```text
TABU+NONE
TABU+CPM
TABU+DIFFUSION
```

Default run saat ini:

```text
50 runs per model
```

Status CDF 50 run:

```text
CDF top-3 sudah selesai pada log `outputs/comparison_notebook/cdf_top3_objective_50.log`.
Ringkasan tersimpan pada `outputs/comparison_notebook/cdf_summary.csv`.
```

Ringkasan hasil CDF 50 run:

| Model | Objective mean | Objective std | Objective min | Objective max |
|---|---:|---:|---:|---:|
| `TABU+NONE` | 0.653943 | 0.001194 | 0.651007 | 0.656073 |
| `TABU+DIFFUSION` | 0.654083 | 0.001045 | 0.651519 | 0.655889 |
| `TABU+CPM` | 0.654571 | 0.003443 | 0.651477 | 0.671120 |

Kalimat yang boleh dipakai:

```text
Pengujian CDF dilakukan pada tiga kandidat terbaik berdasarkan final objective untuk mengevaluasi stabilitas hasil optimasi. Hasil CDF digunakan sebagai validasi statistik tambahan setelah single-run screening.
```

```text
Berdasarkan CDF 50 run, TABU+NONE memperoleh rata-rata objective terbaik. TABU+DIFFUSION menghasilkan performa yang sangat kompetitif dengan variasi objective yang lebih kecil, sehingga menunjukkan stabilitas pencarian yang baik meskipun mean objective-nya sedikit lebih tinggi.
```

Kalimat yang belum boleh dipakai:

```text
Tabu-Diffusion terbukti paling stabil secara statistik.
```

Kalimat itu baru aman jika CDF summary final mendukung.

## 10. Model Sistem VPS

Fase VPS memakai 1 central node dan 9 edge node.

Konfigurasi dari `config.py`:

| Node | IP | Port |
|---|---|---:|
| Central | `10.33.102.106` | 8000 |
| `edge-1` | `10.33.102.107` | 8001 |
| `edge-2` | `10.33.102.108` | 8002 |
| `edge-3` | `10.33.102.109` | 8003 |
| `edge-4` | `10.33.102.110` | 8004 |
| `edge-5` | `10.33.102.111` | 8005 |
| `edge-6` | `10.33.102.112` | 8006 |
| `edge-7` | `10.33.102.113` | 8007 |
| `edge-8` | `10.33.102.114` | 8008 |
| `edge-9` | `10.33.102.115` | 8009 |

Konfigurasi resource dari `central/node_resources.py`:

| Tier | Node | CPU | Mem | Delay | Idle power | Max power |
|---|---|---:|---:|---:|---:|---:|
| Low | `edge-1` sampai `edge-3` | 2 | 2 GB | 0.030-0.040 | 8 W | 18 W |
| Mid | `edge-4` sampai `edge-6` | 4 | 4 GB | 0.022-0.028 | 14 W | 32 W |
| High | `edge-7` sampai `edge-9` | 8 | 8 GB | 0.015-0.020 | 24 W | 55 W |

Konfigurasi tambahan:

```text
MAX_CONCURRENT_TASKS = 2
TASK_TIMEOUT = 300 seconds
```

Catatan untuk Bab 3.1 perangkat:

1. Jika sudah punya Bab 3.1 perangkat, masukkan tabel central dan edge node di atas.
2. Jelaskan node heterogen sebagai low/mid/high tier.
3. Jelaskan power model bukan daya listrik ukur langsung dari wattmeter, tetapi estimasi berbasis idle power, max power, dan observed task-clock/cpu-clock.

## 11. Alur Implementasi VPS `main3.py`

Alur utama:

1. `main3.py` membaca jumlah task dari argumen atau environment variable.
2. Task dibuat oleh `generate_batch(N_TASKS)`.
3. Baseline random dijalankan sebanyak `N_RANDOM_BASELINES`, default 5 run.
4. Metrik baseline random dirata-ratakan.
5. `E_ref` dan `L_ref` dibentuk dari baseline random.
6. Optimizer `tabu_legacy_hybrid` dijalankan pada task yang sama.
7. Assignment dikirim ke edge node aktif melalui HTTP.
8. Edge node menjalankan workload `cpu_mem_burn`.
9. Central menunggu hasil eksekusi setiap task.
10. Sistem menghitung metrik real dan model.
11. Random baseline dan Tabu hybrid dibandingkan.

Baseline VPS:

```text
Random baseline average, bukan Round-Robin.
```

Mode optimasi utama:

```text
tabu_legacy_hybrid
```

Parameter `main3.py` yang dapat diatur:

| Environment variable | Makna |
|---|---|
| `N_TASKS` | Jumlah task. |
| `N_RANDOM_BASELINES` | Jumlah run random baseline. |
| `LEGACY_ENERGY_WEIGHT` | Bobot energy objective legacy hybrid. |
| `LEGACY_LOCAL_MODE` | Mode local refinement, default `hybrid`. |
| `LEGACY_HIGH_POWER_PENALTY` | Penalti penggunaan high-power node. |
| `LEGACY_VPS_PENALTY_SCALE` | Skala penalti VPS pada objective hybrid. |

## 12. Objective VPS

VPS memakai objective hybrid yang menggabungkan:

1. Legacy simulation objective.
2. VPS-aware energy-focused cost.
3. Penalti high-tier usage.
4. Penalti resource pressure.
5. Penalti concurrency.
6. Penalti energy overshoot.
7. Penalti task-tier mismatch untuk small/medium task yang terlalu cepat dikirim ke high-tier node.

Secara konseptual:

```text
legacy_hybrid_cost = legacy_cost + vps_penalty_scale * vps_cost
```

Tujuannya bukan hanya mengejar latency rendah, tetapi juga menghindari penggunaan high-power node secara terlalu agresif ketika low/mid tier masih memadai.

Catatan penting:

```text
VPS objective bukan salinan persis objective simulasi notebook. VPS objective adalah adaptasi implementasi agar assignment lebih cocok dengan kondisi node nyata.
```

## 13. Eksekusi Task Nyata

Edge node menjalankan workload melalui `edge/workload_worker.py`.

Workload:

```text
cpu_mem_burn
```

Parameter workload:

1. `memory_bytes`: ukuran buffer memori yang disentuh.
2. `seed`: seed untuk reproduktibilitas pola kerja.
3. `touch_rounds`: jumlah putaran sentuh memori.
4. `NODE_TIER`: low, mid, high.

Perbedaan tier worker:

| Tier | Vector size | Compute rounds |
|---|---:|---:|
| Low | 128 | 2 |
| Mid | 256 | 4 |
| High | 512 | 8 |

Metrik yang dikumpulkan dari hasil eksekusi:

1. `latency`
2. `execution_time`
3. `observed_task_clock_ms`
4. `observed_cpu_clock_ms`
5. `observed_memory_bytes`
6. `executor_node`
7. `executor_host`

## 14. Metrik Evaluasi VPS

Metrik dibagi menjadi dua kelompok.

Metrik real:

| Metrik | Makna |
|---|---|
| `real_avg_latency` | Rata-rata latency hasil eksekusi nyata. |
| `real_total_latency` | Total latency semua task. |
| `real_avg_execution_time` | Rata-rata execution time. |
| `real_total_execution_time` | Total execution time. |
| `estimated_real_energy_j` | Estimasi energi berbasis observed clocks dan power model. |
| `estimated_real_energy_per_task_j` | Estimasi energi per task. |
| `real_avg_task_clock_ms` | Rata-rata task-clock dari perf. |
| `real_total_task_clock_ms` | Total task-clock dari perf. |
| `real_avg_memory_bytes` | Rata-rata memori terobservasi. |

Metrik model:

| Metrik | Makna |
|---|---|
| `model_avg_latency` | Latency dari model simulasi/estimasi. |
| `model_total_energy` | Energy dari model. |
| `distribution` | Distribusi task per node. |

Catatan:

```text
Metrik real dan metrik model harus dibedakan dalam penulisan. Jika model energy turun tetapi estimated real energy tidak selalu turun, itu harus dibahas sebagai gap model-vs-real.
```

## 15. Hasil VPS Terbaru

Sumber: `outputs/main3_energy_first_selected_200_300_400.json`

Konfigurasi:

```text
task_seed = 42
N_RANDOM_BASELINES = 5
local_mode = hybrid
energy_weight = 0.85
high_power_penalty_weight = 2.25
vps_penalty_scale = 0.5
```

Ringkasan:

| N tasks | Random latency | Main3 latency | Latency gain | Random energy J | Main3 energy J | Energy gain J |
|---:|---:|---:|---:|---:|---:|---:|
| 200 | 1.1382 | 0.8754 | +0.2628 | 4969.18 | 5266.40 | -297.22 |
| 300 | 1.3441 | 1.0095 | +0.3347 | 7482.81 | 7506.28 | -23.47 |
| 400 | 1.3700 | 1.1335 | +0.2365 | 10018.14 | 9863.46 | +154.68 |

Interpretasi:

1. Latency real membaik konsisten pada 200, 300, dan 400 task.
2. Execution time juga cenderung membaik.
3. Energy real belum selalu membaik. Pada 200 dan 300 task, estimated real energy masih lebih tinggi dari random; pada 400 task energy membaik.
4. Model energy turun cukup besar, tetapi real energy tidak selalu sejalan. Ini menjadi batasan penelitian yang perlu dijelaskan.

Narasi aman:

```text
Implementasi VPS menunjukkan peningkatan latency yang konsisten dibanding random baseline. Namun, peningkatan latency tersebut masih memiliki trade-off pada estimasi energi nyata untuk beberapa ukuran workload. Hal ini menunjukkan bahwa model simulasi dan perilaku real execution tidak selalu identik.
```

## 16. Pemetaan ke Bab Skripsi

### Bab 1 Pendahuluan

Masukkan:

1. Edge computing membutuhkan penjadwalan task karena resource node heterogen.
2. Assignment task yang tidak optimal dapat meningkatkan latency dan konsumsi energi.
3. Metaheuristik dipilih karena problem scheduling bersifat kombinatorial.
4. Penelitian memakai pendekatan dua fase: simulasi dan validasi VPS.

Jangan terlalu cepat mengklaim:

```text
Metode hybrid pasti paling unggul.
```

Lebih aman:

```text
Metode hybrid dievaluasi untuk melihat pengaruh kombinasi global search dan local refinement terhadap kualitas scheduling.
```

### Bab 2 Tinjauan Pustaka

Topik yang perlu ada:

1. Edge computing.
2. Task scheduling.
3. Heterogeneous edge nodes.
4. Energy-latency trade-off.
5. Metaheuristic optimization.
6. Tabu Search.
7. Particle Swarm Optimization.
8. Bacterial Foraging Optimization.
9. Local refinement/diffusion-inspired balancing.
10. CDF/statistical repeated-run evaluation.

### Bab 3 Metodologi

Struktur yang disarankan:

1. Perangkat dan lingkungan penelitian.
2. Dataset penelitian.
3. Desain sistem simulasi.
4. Desain objective function simulasi.
5. Metode optimasi yang dibandingkan.
6. Skenario eksperimen simulasi.
7. Kriteria evaluasi simulasi.
8. Pemilihan top-3 dan CDF.
9. Desain implementasi VPS.
10. Task generator data-driven.
11. Mekanisme eksekusi task pada edge node.
12. Metrik evaluasi VPS.

Karena kamu sudah punya Bab 3.1 perangkat, tambahkan:

1. Tabel central dan edge node.
2. Tabel tier low/mid/high.
3. Python environment dan library utama jika diperlukan.
4. Keterangan bahwa notebook dan VPS memakai environment yang berbeda secara tujuan, tetapi berada dalam project yang sama.

### Bab 4 Hasil dan Pembahasan

Pisahkan menjadi dua bagian:

1. Hasil simulasi.
2. Hasil VPS.

Hasil simulasi membahas:

1. Grafik konvergensi.
2. Single-run screening.
3. Ranking final objective, time-to-target, runtime.
4. CDF top-3.
5. Analisis kenapa keluarga Tabu dominan.
6. Analisis kenapa Tabu-Diffusion tidak selalu final objective terbaik.

Hasil VPS membahas:

1. Random baseline average.
2. Tabu legacy hybrid.
3. Real latency.
4. Execution time.
5. Estimated real energy.
6. Model energy dan model latency.
7. Distribusi task antar node.
8. Gap model-vs-real.

### Bab 5 Kesimpulan

Kesimpulan harus mengikuti hasil final nanti.

Jika hasil tetap seperti saat ini:

1. Tabu Search memberi kualitas objective terbaik pada simulasi.
2. Tabu-Diffusion kompetitif dan cepat mencapai target pada keluarga Tabu.
3. Implementasi VPS meningkatkan latency dibanding random baseline.
4. Energy real masih menjadi trade-off dan perlu penyempurnaan model.

## 17. Celah Penelitian yang Harus Disampaikan Jujur

1. `TABU+DIFFUSION` belum terbukti selalu paling unggul.
2. CDF top-3 masih perlu diselesaikan sebelum klaim statistik final.
3. Dataset lama dan dataset terbaru berbeda; penulisan harus konsisten.
4. Simulasi memakai Round-Robin baseline, sedangkan VPS memakai random baseline average.
5. Topologi Diffusion pada simulasi berbasis grid 4-neighbor, sedangkan VPS saat ini memakai adjacency semua node.
6. Energy model simulasi sudah mulai diselaraskan dengan power tier VPS, tetapi estimated real energy tetap bersifat estimasi dan belum menggantikan pengukuran wattmeter langsung.
7. Semua metode pembanding tidak dijalankan di VPS; VPS fokus pada kandidat terpilih.
8. Power model VPS masih estimasi, bukan pengukuran wattmeter langsung.
9. Time-to-target memakai threshold 0.75; jangan dicampur dengan threshold lain tanpa penjelasan.

## 18. Rekomendasi Finalisasi

Sebelum dokumen skripsi difinalkan:

1. Selesaikan run CDF top-3.
2. Ambil tabel `cdf_summary_df` dan grafik CDF.
3. Kunci klaim metode terbaik berdasarkan hasil CDF.
4. Pastikan output notebook sudah bersih dan urutannya final.
5. Jangan campur hasil output lama di notebook dengan hasil terbaru dari CSV.
6. Jika memungkinkan, jalankan VPS tambahan untuk workload yang sama agar hasil real energy lebih kuat.
7. Pisahkan semua istilah "simulasi" dan "VPS" secara eksplisit.

## 19. Istilah Final yang Disarankan

| Istilah | Gunakan untuk |
|---|---|
| Simulation-based comparison | Fase `Comparision.ipynb`. |
| VPS-based validation | Fase `main3.py`. |
| Round-Robin baseline | Baseline simulasi. |
| Random baseline average | Baseline VPS. |
| Hybrid Tabu-Diffusion | Metode yang menggabungkan Tabu Search dan Diffusion local refinement. |
| Diffusion local refinement | Local optimizer berbasis perpindahan task ke neighbor yang lebih baik. |
| Final objective | Kualitas solusi akhir. |
| Time-to-target | Kecepatan mencapai objective threshold. |
| Runtime | Waktu komputasi optimizer. |
| Real metrics | Metrik hasil eksekusi task nyata di VPS. |
| Model metrics | Metrik hasil model estimasi. |

## 20. Satu Paragraf Ringkasan untuk Pembuka Metodologi

Penelitian ini menggunakan pendekatan dua fase untuk mengevaluasi metode penjadwalan task pada sistem edge computing heterogen. Fase pertama dilakukan melalui simulasi pada notebook comparison dengan topologi edge 3x3, baseline Round-Robin, dan objective gabungan energi-latency. Pada fase ini, beberapa kombinasi optimizer seperti Tabu Search, BFO, dan PSO dibandingkan dengan local method none, CPM, dan Diffusion. Model terbaik dipilih berdasarkan final objective, time-to-target, dan runtime, kemudian diuji lebih lanjut menggunakan CDF. Fase kedua mengimplementasikan kandidat terpilih pada lingkungan VPS dengan 9 edge node heterogen, task generator data-driven, baseline random average, dan pengukuran real execution menggunakan latency, execution time, task-clock, cpu-clock, serta estimasi energi nyata.
