# BASE KNOWLEDGE — TUGAS AKHIR
## Optimasi Task Scheduling di Edge Computing dengan Pendekatan Hybrid: Tabu Search + Diffusion Local Balancing

---

## DAFTAR ISI

1. [Gambaran Umum Penelitian](#1-gambaran-umum-penelitian)
2. [Dataset](#2-dataset)
3. [Pemodelan Sistem (BAB 3.3)](#3-pemodelan-sistem-bab-33)
4. [Implementasi Solusi (BAB 3.4)](#4-implementasi-solusi-bab-34)
5. [Metode yang Dibandingkan](#5-metode-yang-dibandingkan)
6. [Pengujian (BAB 3.5)](#6-pengujian-bab-35)
7. [Analisis Hasil (BAB 4)](#7-analisis-hasil-bab-4)
8. [Pertanyaan Terbuka / Perlu Klarifikasi Lanjut](#8-pertanyaan-terbuka--perlu-klarifikasi-lanjut)

---

## 1. GAMBARAN UMUM PENELITIAN

### Tujuan
Menemukan metode optimasi task scheduling di edge computing yang secara simultan meminimalkan **energy consumption** dan **latency** sebagai dual-objective function.

### Pendekatan Utama: Hybrid Optimization
Masalah utama metode global optimization (Tabu Search, PSO, BFO) adalah kecenderungan terjebak di **local search space** sehingga tidak mencapai solusi optimal secara efisien. Untuk mengatasi ini, digunakan pendekatan **hybrid** dengan dua lapis:

| Layer | Peran | Metode yang Diuji |
|-------|-------|-------------------|
| **Global Optimizer** | Memberikan keputusan task scheduling secara keseluruhan (search space luas) | Tabu Search, PSO, BFO |
| **Local Balancer** | Menyeimbangkan beban antar node setelah keputusan global (fine-tuning lokal) | CPM, Diffusion, None |

### Kesimpulan Penelitian
**TABU + DIFFUSION** adalah kombinasi terbaik karena:
- Mencapai objective function terbaik (nilai paling rendah)
- Waktu konvergensi paling cepat (Time-to-Target 4.26 detik)
- Total runtime paling efisien (13 detik)

---

## 2. DATASET

### 2.1 Machine Dataset
- **Sumber**: Google Cluster Trace
- **File**: `part-00000-of-00001.csv`
- **Total raw rows**: 37,780 entri
- **Kolom**: `time`, `machine_id`, `event_type`, `platform_id`, `cpu_capacity`, `memory_capacity`
- **Filter**: Hanya event_type == 0 (ADD event), deduplicated by machine_id → **12,583 mesin unik**

### 2.2 Task Dataset
- **Sumber**: Google Cluster Trace (preprocessed)
- **File**: `cpm_pso_input_part10_19_timeseries.csv`
- **Total tasks**: 291,623 tasks (setelah cleaning)
- **Kolom**:

| Kolom | Keterangan |
|-------|-----------|
| `job_id` | ID unik pekerjaan |
| `task_index` | Indeks task dalam job |
| `t_submit` | Waktu submit task |
| `time_window` | Jendela waktu eksekusi |
| `latency_ms` | Latency aktual (milidetik) |
| `latency_norm` | Latency ternormalisasi (0–1) |
| `cpu_req` | Kebutuhan CPU (0–1) |
| `mem_req` | Kebutuhan memory (0–1) |

- **Tasks yang digunakan dalam simulasi**: 300 tasks (disampling dari 291,623)

### 2.3 Seed & Reproducibility
```
GLOBAL_SEED    : 2026
MACHINE_SEED   : 111   → untuk konfigurasi node
TASK_SEED      : 222   → untuk sampling tasks
OPTIMIZER_SEED : 333   → untuk proses optimasi
```
Seed dipisah agar masing-masing komponen tidak saling mempengaruhi.

---

## 3. PEMODELAN SISTEM (BAB 3.3)

### 3.1 Diagram Sistem (Topologi Grid 3×3)

Sistem terdiri dari **9 edge nodes** dalam topologi **grid 3×3** dengan 1 **Central Gateway** sebagai pengatur pusat. Implementasi menggunakan Virtual Machine (VM).

```
[ Central Gateway ]
  IP: 10.33.102.106
  Port: 8000
        │
        ├── Broadcast task ke semua nodes (async)
        │
  ┌─────┼─────┐
  │     │     │
Node0  Node1  Node2   (baris 0)
  │     │     │
Node3  Node4  Node5   (baris 1)
  │     │     │
Node6  Node7  Node8   (baris 2)

IP Nodes: 10.33.102.107–10.33.102.115
Port Nodes: 8001–8009
```

Topologi grid mendefinisikan **adjacency** antar node (atas, bawah, kiri, kanan), yang digunakan oleh **Diffusion Local Optimizer** untuk menentukan arah migrasi task.

### 3.2 Konfigurasi Node (Heterogen)
9 node dikonfigurasi dengan kapasitas **heterogen** (tidak seragam), disampling dari dataset mesin nyata dan diskalakan:

| Node | CPU Capacity | Memory Capacity |
|------|-------------|----------------|
| 0 | 0.938260 | 0.162958 |
| 1 | 1.036793 | 0.166857 |
| 2 | 1.300792 | 0.502479 |
| 3 | 0.855310 | 0.578480 |
| 4 | 1.091207 | 0.633157 |
| 5 | 1.078421 | 0.304309 |
| 6 | 1.457196 | 0.323491 |
| 7 | 1.013797 | 0.733639 |
| 8 | 1.226275 | 0.186214 |

- CPU: fully synthetic, uniform (0.8–1.5)
- Memory: raw dari dataset × heterogeneity factor (0.5–1.5)

### 3.3 Pemodelan dengan Program

**Computing Load Model:**
```python
# Menghitung beban tiap node berdasarkan task yang di-assign
cpu_util[i] = sum(cpu_req tasks di node i) / cpu_cap[i]
mem_util[i] = sum(mem_req tasks di node i) / mem_cap[i]
load[i] = alpha_cpu * cpu_util[i] + beta_mem * mem_util[i]

# Bobot
alpha_cpu = 0.4   # bobot CPU
beta_mem  = 0.6   # bobot memory
```

**Interaksi Antar Node:**
- Setiap node berjalan sebagai **FastAPI server** independen
- Berkomunikasi via **HTTP REST API**
- Central Gateway mem-broadcast task ke semua 9 node secara **asinkron (non-blocking)**
- Setiap node mengirim **heartbeat** setiap 10 detik (CPU%, Memory%, queue size)

**Data Models:**
```python
Task:       task_id, name, data, priority, created_at
TaskResult: task_id, status, result, error, node_id, completed_at
NodeStatus: node_id, status, cpu_usage, memory_usage, tasks_count, last_heartbeat
```

### 3.4 Pemodelan pada VPS (Program Task Generator)
- Client mengirim task via `POST /tasks` ke Central Gateway
- Central Gateway menyimpan task dengan status `pending`
- Task didistribusikan ke semua 9 node secara paralel (async broadcast)
- Node memproses task dari queue, lalu mengirim hasil ke Central via `POST /results/{id}`
- Status task bisa di-polling via `GET /tasks/{id}`

---

## 4. IMPLEMENTASI SOLUSI (BAB 3.4)

### 4.1 Perancangan Objective Function

Objective function bersifat **dual-objective** (dua tujuan sekaligus):

```
OF = weight_energy * (E / E_REF) + weight_latency * (L / L_REF)

weight_energy  = 0.6
weight_latency = 0.4
```

Nilai OF dinormalisasi terhadap **baseline (Round-Robin)**:
- `E_REF` = 358.580982 (energy baseline Round-Robin)
- `L_REF` = 9028.895352 (latency baseline Round-Robin)
- Baseline objective = **1.0** (acuan perbandingan)

Nilai OF < 1.0 berarti **lebih baik dari Round-Robin**.

**Energy Model:**
```python
# Power tiap node:
P_idle    = 10  W   (node aktif tapi idle)
P_cpu_dyn = 12  W   (dinamis berdasarkan CPU utilization)
P_mem_dyn = 5   W   (dinamis berdasarkan memory utilization)
P_sleep   = 2   W   (node tidak aktif)

# Soft overload penalty (CPU):
if cpu_util <= 0.8  : penalty = 0
if cpu_util <= 1.0  : penalty = 15 * (cpu_util - 0.8)
if cpu_util >  1.0  : penalty = 15*0.2 + 40*(cpu_util - 1.0)

# Consolidation penalty:
active_penalty = 3 * jumlah_node_aktif

total_energy = sum(power * delta_t + overload_penalty) + active_penalty
```

**Latency Model:**
- Menggunakan `latency_ms` dari dataset Google Cluster Trace
- Dipengaruhi oleh kondisi queue (congestion) di tiap node
- Dinormalisasi dengan `L_REF`

### 4.2 Perancangan Search Space

**Definisi Search Space:**
- Setiap solusi adalah sebuah **assignment vector** berukuran N_tasks = 300
- Setiap elemen merepresentasikan **node tujuan** dari suatu task
- Range nilai: integer 0 sampai 8 (9 node)

```
Contoh assignment vector:
[0, 3, 7, 2, 5, 1, 8, 4, 6, 0, ...]
 ↑  ↑  ↑
task0 → node0
task1 → node3
task2 → node7
```

**Dimensi search space**: 9^300 kemungkinan kombinasi (sangat besar, NP-hard)

**Inisialisasi Search Space di Program:**

*PSO - Inisialisasi Swarm:*
```python
# Setiap partikel = 1 assignment vector
# Posisi awal: random integer 0–8
population = [rng_optimizer.integers(0, N_NODES, size=N_tasks) for _ in range(SWARM_SIZE)]
# PSO_SWARM_SIZE = 40
```

*Tabu Search - Inisialisasi:*
```python
# Dimulai dari baseline_assignment (Round-Robin)
current_assign = baseline_assignment.copy()
# TABU_MAX_ITER = 150, TABU_TENURE = 25, TABU_CANDIDATE_MOVES = 60
```

*BFO - Inisialisasi Populasi:*
```python
# N_bacteria = 40, setiap bakteria = 1 assignment vector
population = [rng_optimizer.integers(0, N_NODES, size=N_tasks) for _ in range(N_bacteria)]
```

**Representasi Posisi:**
- **PSO/BFO**: setiap partikel/bakteri adalah integer array berukuran 300
- **Tabu**: single solution yang bergerak dengan move "single task reassignment" atau "swap"

### 4.3 Penerapan Algoritma Optimasi

#### A. TABU SEARCH (Global Optimizer)

**Parameter:**
```
TABU_MAX_ITER         = 150   iterasi maksimum
TABU_TENURE           = 25    lamanya move dilarang (masuk tabu list)
TABU_CANDIDATE_MOVES  = 60    kandidat move yang dievaluasi per iterasi
```

**Representasi Partikel di Search Space:**
```
current_assign = [node_0, node_1, ..., node_299]   ← solusi saat ini
tabu_dict      = {move: expiry_iter}               ← daftar move terlarang
gbest_assign   = best solution yang pernah ditemukan
```

**Tipe Move:**
1. **Single Move**: Satu task dipindah ke node berbeda (weighted by cpu_util)
2. **Swap Move**: Tukar assignment antara 1 task di node overloaded dan 1 task di node underloaded

**Aspiration Criterion**: Move yang tabu boleh dilakukan jika menghasilkan solusi lebih baik dari `gbest_val`.

#### B. PSO — Particle Swarm Optimization (Global Optimizer)

**Parameter:**
```
PSO_SWARM_SIZE = 40    jumlah partikel
PSO_MAX_ITER   = 150   iterasi maksimum
PSO_W          = 0.73  inertia weight
PSO_C1         = 1.6   cognitive coefficient (pbest)
PSO_C2         = 1.6   social coefficient (gbest)
```

**Representasi Partikel:**
```
position[i] = assignment vector partikel ke-i   [int 0–8, size=300]
velocity[i] = perubahan posisi partikel ke-i
pbest[i]    = posisi terbaik partikel ke-i
gbest       = posisi terbaik seluruh swarm
```

#### C. BFO — Bacterial Foraging Optimization (Global Optimizer)

**Parameter:**
```
N_bacteria = 40    jumlah bakteri
Nc         = 12    chemotactic steps
Nre        = 6     reproduction steps
Ned        = 6     elimination-dispersal events
Ped        = 0.2   probabilitas eliminasi
```

**Representasi Bakteri:**
```
population[i] = assignment vector bakteri ke-i   [int 0–8, size=300]
```

**Mekanisme:**
- **Chemotaxis**: Tumble (random move) + Swim (lanjut jika membaik)
- **Reproduction**: Bakteri terbaik diperbanyak, terburuk dieliminasi
- **Elimination-Dispersal**: Bakteri berpeluang direset ke posisi random (Ped = 0.2)

#### D. CPM — Cellular Potts Model (Local Optimizer)

**Konsep**: Model berbasis fisika statistik (Metropolis algorithm) yang menyeimbangkan beban node berdasarkan **topologi grid** (bukan task migration langsung).

**Cara Kerja:**
- Setiap node punya "state" (0, 1, atau 2)
- Metropolis step: coba ubah state → terima jika menurunkan "local energy"
- Local energy mempertimbangkan perbedaan state dengan tetangga + overload penalty
- Dijalankan 10 step per pemanggilan

**Limitation**: CPM tidak langsung memindahkan task, lebih ke representasi status node.

#### E. DIFFUSION LOCAL OPTIMIZER (Local Optimizer) ← TERBAIK

**Konsep**: Simulasi proses **difusi fisika** — beban mengalir dari node dengan beban tinggi ke node tetangga dengan beban rendah, seperti penyebaran panas atau konsentrasi zat.

**Parameter:**
```python
gamma      = 0.03   # laju difusi (seberapa cepat beban mengalir)
max_steps  = 8      # maksimum langkah difusi per pemanggilan
max_migrations = 1  # maksimum task yang boleh dipindah per step
```

**Cara Kerja (3 tahap):**

1. **Observe Load**: Hitung beban aktual tiap node
```python
load[i] = alpha_cpu * cpu_util[i] + beta_mem * mem_util[i]
```

2. **Diffusion Flow**: Hitung aliran beban antar tetangga
```python
for setiap edge (i, j) di adjacency:
    flow = gamma * (load[i] - load[j])   # hanya jika load[i] > load[j]
    load[i] -= flow
    load[j] += flow
```

3. **Task Migration**: Pindahkan 1 task dari node overloaded ke tetangga paling ringan
```python
if load[i] > mean_load * 1.05:   # node dianggap overloaded
    lightest_neighbor = min(neighbors[i], key=load)
    pilih 1 task random dari node i
    coba pindah ke lightest_neighbor
    terima jika objective value membaik
```

**Keunggulan Diffusion vs CPM:**
- Diffusion langsung **memindahkan task** → dampak nyata ke objective function
- CPM hanya mengubah state representasi → dampak tidak langsung
- Diffusion mempertimbangkan **adjacency topologi** grid secara eksplisit
- Diffusion melakukan **greedy verification** sebelum menerima migrasi

---

## 5. METODE YANG DIBANDINGKAN

| No | Metode | Global | Local | Keterangan |
|----|--------|--------|-------|------------|
| 1 | **TABU + NONE** | Tabu Search | - | Baseline Tabu tanpa local balancing |
| 2 | **TABU + CPM** | Tabu Search | CPM | Tabu + Cellular Potts Model |
| 3 | **TABU + DIFFUSION** ⭐ | Tabu Search | Diffusion | **TERBAIK** |
| 4 | **PSO + CPM** | PSO | CPM | Swarm-based + CPM |
| 5 | **BFO + DIFFUSION** | BFO | Diffusion | Bio-inspired + Diffusion |

### Kenapa TABU + DIFFUSION Terbaik?

1. **Tabu Search** efektif menghindari revisit solusi buruk (memory-based), cocok untuk discrete assignment problem
2. **Diffusion** secara fisik menyeimbangkan beban dengan cara yang natural dan langsung mempengaruhi objective
3. Kombinasi keduanya saling melengkapi: Tabu menjelajah global space, Diffusion merapikan distribusi lokal

### Metrik Perbandingan

| Metrik | Keterangan | Satuan |
|--------|-----------|--------|
| **Objective Value (OF)** | Nilai akhir energy*0.6 + latency*0.4 (ternormalisasi) | dimensionless |
| **Energy** | Total konsumsi daya semua node | Watt |
| **Latency** | Total latency terbobot semua task | ms |
| **Time-to-Target (TTT)** | Waktu untuk mencapai OF ≤ 0.75 | detik |
| **Total Runtime** | Waktu total eksekusi optimizer | detik |
| **CDF** | Distribusi kumulatif OF dari 300 runs | probabilitas |

### Hasil Waktu Konvergensi (Single Run)

| Metode | TTT (detik) | Runtime (detik) |
|--------|------------|----------------|
| TABU + NONE | 7.95 | 26.82 |
| TABU + CPM | 7.63 | 18.67 |
| **TABU + DIFFUSION** | **4.26** | **13.00** |
| BFO + NONE | 17.84 | 40.37 |
| BFO + CPM | 27.24 | 31.28 |
| BFO + DIFFUSION | 7.23 | 35.25 |

### Jumlah Runs untuk Perbandingan Statistik
Setiap metode dijalankan **300 kali** untuk mendapatkan distribusi yang representatif.

---

## 6. PENGUJIAN (BAB 3.5)

### 6.1 Pengujian Simulasi Program

**Cara Pengujian:**
- Semua optimizer dijalankan pada **problem instance yang sama** (dataset, node config, seed identik) → reproducible
- Setiap metode dijalankan 300 kali → distribusi hasil
- Evaluasi menggunakan fungsi `evaluate_solution()` yang memanggil `objective_value()`

**Kriteria Kinerja:**
1. **Objective Value terendah** → nilai OF terkecil = terbaik
2. **Hasil optimasi** → konvergensi curve (history OF per iterasi)
3. **CDF (Cumulative Distribution Function)** → distribusi OF dari 300 runs
   - CDF yang bergeser ke kiri = konsisten menghasilkan OF rendah = lebih baik
   - Diplot per metode dan gabungan untuk perbandingan

**Landasan Rekomendasi:**
- Metode dengan mean OF terendah dari 300 runs
- Metode dengan TTT tercepat (konvergen lebih cepat)
- Metode dengan CDF paling konsisten (variance rendah)

### 6.2 Pengujian Simulasi di VPS

**Perbedaan dengan Simulasi Program:**

| Aspek | Simulasi Program | Simulasi VPS |
|-------|-----------------|-------------|
| Environment | Python notebook lokal | VM nyata (9 node + 1 central) |
| Network | Tidak ada (lokal) | HTTP REST API (10.33.102.x) |
| Task | Synthetic/sampled dataset | Task Generator real-time |
| Beban | Controlled, static | Dynamic, real HTTP requests |
| Tujuan | Validasi algoritma | Proof-of-concept implementasi nyata |

**Cara Pengujian di VPS:**
1. Deploy Central Gateway di `10.33.102.106:8000`
2. Deploy 9 Edge Nodes di `10.33.102.107–115`, port `8001–8009`
3. Jalankan Task Generator → kirim batch tasks via `POST /tasks`
4. Amati distribusi pemrosesan task di setiap node
5. Bandingkan: **tanpa optimasi** (Round-Robin default) vs **dengan optimasi** (metode terbaik)

**Dashboard Monitoring:**
- `GET /nodes/status` → real-time CPU%, Memory%, queue size semua node
- `GET /tasks/{id}` → status dan hasil setiap task
- Heartbeat tiap 10 detik dari masing-masing node → status node selalu update

---

## 7. ANALISIS HASIL (BAB 4)

### 4.1 Hasil Pengujian Simulasi Program

**Yang Dianalisis:**
- Tabel perbandingan mean OF, mean energy, mean latency dari 300 runs semua metode
- Grafik CDF per metode (individual) dan gabungan
- Grafik konvergensi (history OF per iterasi) metode terbaik vs terburuk
- Statistical significance (apakah perbedaan signifikan secara statistik)
- **Metode terbaik: TABU + DIFFUSION** (OF terendah, TTT tercepat, CDF paling kiri)

**Perbandingan Baseline:**
- Round-Robin (baseline): OF = 1.0
- Semua metode optimasi diharapkan menghasilkan OF < 1.0
- Penurunan OF menunjukkan persentase improvement terhadap Round-Robin

### 4.2 Hasil Pengujian Simulasi di VPS

**Yang Dianalisis:**
- Perbandingan kinerja sistem **tanpa optimasi** vs **dengan optimasi (TABU + DIFFUSION)**
- Metrik yang diamati:
  - CPU utilization per node (apakah merata?)
  - Memory utilization per node
  - Queue length per node (apakah ada bottleneck?)
  - Task completion time
  - Energy consumption estimasi dari monitoring

**Cara Membaca Perbedaan:**
- Tanpa optimasi: distribusi beban tidak merata (Round-Robin tidak mempertimbangkan kapasitas)
- Dengan optimasi: beban lebih merata, node overloaded berkurang, energi lebih efisien

---

## 8. PERTANYAAN TERBUKA / PERLU KLARIFIKASI LANJUT

Beberapa hal yang **belum saya ketahui** dari informasi yang diberikan dan perlu Anda isi nanti:

1. **Hasil numerik final dari 300 runs**: Mean OF, mean energy, mean latency masing-masing metode (setelah bug PSO diperbaiki dan re-run)

2. **Latency Model detail**: Fungsi `latency_of_configuration()` di `system_model.py` tidak terbaca lengkap (terpotong). Perlu penjelasan formula lengkap latency model.

3. **PSO Implementation detail**: File atau fungsi `hybrid_pso()` tidak ada di notebook — apakah terpisah? Perlu kode lengkapnya.

4. **Hasil VPS**: Data aktual monitoring VPS (CPU%, memory%, queue) belum tersedia.

5. **Jumlah iterasi total BFO**: `Ned × Nre × Nc = 6 × 6 × 12 = 432` evaluasi per bakteria — apakah ini konsisten dengan MAX_ITER = 150 di Tabu/PSO?

6. **Greedy Refinement**: Ada fungsi `greedy_refinement()` di `system_model.py` — apakah digunakan di metode tertentu? Bagaimana cara kerjanya?

7. **Gambar/Visualisasi**: Grafik CDF dan konvergensi aktual dari notebook perlu disimpan untuk dimasukkan ke laporan.

---

## RINGKASAN CEPAT (Quick Reference)

```
TOPOLOGI   : Grid 3×3 → 9 edge nodes + 1 central gateway
DATASET    : Google Cluster Trace → 300 tasks, 9 nodes heterogen
OF         : 0.6 × (E/E_REF) + 0.4 × (L/L_REF)   [target < 1.0]
BASELINE   : Round-Robin → OF = 1.0, E = 358.58, L = 9028.90
TERBAIK    : TABU + DIFFUSION → TTT = 4.26s, runtime = 13s
RUNS       : 300 per metode untuk statistik CDF
METODE     : 5 kombinasi (TABU/PSO/BFO × NONE/CPM/DIFFUSION)
VPS        : 10 VM (1 central + 9 nodes), FastAPI, HTTP REST
VALIDASI   : Simulasi program → VPS implementation
```

---

*Dokumen ini dibuat sebagai acuan penyusunan Laporan Tugas Akhir.*
*Update terakhir: April 2026*
