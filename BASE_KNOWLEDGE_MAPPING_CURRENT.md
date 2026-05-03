# Pemetaan Base Knowledge Lama terhadap Sistem Saat Ini

Tanggal cek: 2026-05-02

Dokumen ini memetakan `BASE_KNOWLEDGE_TA (1).md` terhadap kondisi sistem saat ini. Prinsip utamanya: base knowledge lama tidak boleh dibaca sebagai satu sistem tunggal yang semuanya harus cocok dengan `main3.py`. Alur penelitian yang benar terdiri dari dua fase.

1. Fase simulasi program: berbasis `Comparision.ipynb`.
2. Fase implementasi VPS: berbasis `main3.py` dan modul runtime saat ini.

Dengan pemisahan ini, sebagian isi lama masih valid untuk menjelaskan simulasi awal, tetapi sebagian lain perlu diperbarui untuk menjelaskan implementasi VPS terbaru.

## Ringkasan Keputusan

| Area | Status | Catatan |
|---|---|---|
| Narasi dua fase penelitian | Valid, perlu ditegaskan | Simulasi program lebih dulu, lalu metode/kandidat terbaik dibawa ke VPS. |
| Dataset simulasi Google Cluster Trace | Sebagian valid | Machine dataset masih sama, tetapi task CSV lokal yang dipakai runner sekarang berbeda dari file lama. |
| Topologi grid 3x3 pada simulasi | Valid untuk `Comparision.ipynb` | Notebook membangun grid 3x3 dan adjacency 4-neighbor. |
| Heterogeneous node system model | Valid, tetapi berbeda antar fase | Simulasi memakai kapasitas pecahan dari dataset/sintetik; VPS memakai tier low/mid/high 2/4/8. |
| Objective simulasi Round-Robin | Valid untuk notebook | `Comparision.ipynb` masih memakai Round-Robin sebagai baseline objektif simulasi. |
| Baseline VPS Random | Perlu ditambahkan | `main3.py` memakai baseline random multi-run, bukan Round-Robin. |
| Energy/latency model lama | Valid hanya untuk simulasi | VPS memakai model kalibrasi dan hasil eksekusi nyata. |
| Klaim `TABU+DIFFUSION` terbaik | Belum aman sebagai klaim final | Output single-run terbaru menunjukkan `TABU+NONE` sedikit lebih baik dari `TABU+DIFFUSION`; CDF 300 run belum selesai. |
| CDF 300 runs | Belum lengkap | Log CDF berhenti setelah `TABU+NONE` selesai 300 run dan `TABU+DIFFUSION` baru sekitar run 49. |
| Implementasi VPS nyata | Perlu diperluas | Sekarang ada task data-driven, perf measurement, real task-clock/cpu-clock, dan VPS penalties. |

## Fase 1: Simulasi Program (`Comparision.ipynb`)

Fase ini adalah eksperimen awal untuk membandingkan kombinasi global optimizer dan local optimizer pada lingkungan simulasi.

### Yang Masih Sesuai

| Isi base knowledge lama | Status | Bukti/kondisi sekarang |
|---|---|---|
| `GLOBAL_SEED=2026`, `MACHINE_SEED=111`, `TASK_SEED=222`, `OPTIMIZER_SEED=333` | Valid | Masih ada di cell konfigurasi notebook. |
| 9 node dalam grid 3x3 | Valid | `Nx=3`, `Ny=3`, `N_NODES=9`. |
| 300 task untuk simulasi | Valid | `MAX_TASKS=300`. |
| Bobot load CPU/memory `alpha_cpu=0.4`, `beta_mem=0.6` | Valid | Masih dipakai di model simulasi notebook. |
| Objective dual-objective energy-latency | Valid | `weight_energy=0.6`, `weight_latency=0.4` pada notebook. |
| Baseline simulasi Round-Robin | Valid | `baseline_assignment = np.arange(N_tasks) % N_NODES`. |
| Baseline objective simulasi = 1.0 | Valid | Notebook menghitung `E_REF`, `L_REF`, lalu objective baseline menjadi 1.0. |
| Metode pembanding global/local | Sebagian valid | Notebook saat ini menjalankan beberapa kombinasi, tetapi output runner terbaru hanya berisi 7 kombinasi, bukan lengkap 9. |
| CPM sebagai local method berbasis grid | Valid untuk simulasi | CPM masih memakai neighbor 4-arah pada grid. |
| Diffusion sebagai local refinement | Valid, dengan update framing | Diffusion sekarang lebih tepat disebut neighbor-aware local refinement, bukan sekadar aliran fisika beban. |

### Yang Harus Direvisi untuk Fase Simulasi

| Bagian lama | Revisi yang diperlukan |
|---|---|
| Dataset task disebut `cpm_pso_input_part10_19_timeseries.csv` dengan 291,623 task | Runner lokal sekarang mem-patch notebook ke `spreadsheet_export.csv` dengan 504,567 baris. File lama masih ada, tetapi bukan yang dipakai oleh `run_comparison_models.py`/`run_comparison_cdf.py`. |
| Kolom task lama memuat `latency_ms` dan `latency_norm` | `spreadsheet_export.csv` tidak punya `latency_ms`; runner menambahkan `latency_ms=0.0` saat eksekusi. Ini harus dijelaskan sebagai mode kompatibilitas, atau dikembalikan ke dataset lama jika ingin konsisten dengan base knowledge lama. |
| Parameter Tabu lama `150/25/60` | Notebook sekarang sudah diselaraskan ke VPS: `TABU_MAX_ITER=300`, `TABU_TENURE=30`, `TABU_CANDIDATE_MOVES=70`, `TABU_STAGNATION_TRIGGER=12`. |
| Diffusion lama `gamma=0.03`, `max_steps=8` | Notebook markdown dan kode menunjukkan tuning berbeda pada beberapa bagian. Perlu dikunci satu versi final agar tidak kontradiktif. |
| Klaim `Time-to-Target 4.26s` dan runtime `13s` | Output terbaru tidak sama. Single-run terbaru menunjukkan `TABU+DIFFUSION` runtime sekitar 22s dan threshold 0.60 tidak tercapai. |

### Output Simulasi Terbaru yang Ada

Berdasarkan `outputs/comparison_notebook/comparison_summary.csv`:

| Model | Final objective | Runtime |
|---|---:|---:|
| `TABU+NONE` | 0.655021 | 21.843s |
| `TABU+DIFFUSION` | 0.655252 | 22.007s |
| `TABU+CPM` | 0.655751 | 21.919s |
| `BFO+NONE` | 0.685052 | 34.292s |
| `BFO+DIFFUSION` | 0.686503 | 38.425s |
| `PSO+CPM` | 0.708618 | 6.801s |
| `BFO+CPM` | 0.734469 | 36.013s |

Catatan penting: tabel ini adalah hasil single-run/convergence report, bukan bukti statistik final 300 runs.

### Celah pada Fase Simulasi

1. Klaim metode terbaik belum stabil.
   `TABU+DIFFUSION` sangat kompetitif, tetapi pada output terbaru `TABU+NONE` sedikit lebih rendah objective-nya. Selisihnya kecil, tetapi tetap tidak boleh diabaikan.

2. CDF 300 runs belum selesai.
   `outputs/comparison_notebook/cdf_run.log` menunjukkan `TABU+NONE` selesai 300 run, kemudian `TABU+DIFFUSION` baru berjalan sampai sekitar run 49. Belum ada `cdf_summary.csv`.

3. Jumlah kombinasi belum konsisten.
   Narasi lama menyebut 9 kombinasi, tetapi output terbaru hanya menampilkan 7 kombinasi. `PSO+NONE` dan `PSO+DIFFUSION` belum muncul di summary terbaru.

4. Target time-to-target berubah.
   Base knowledge lama memakai target 0.75, sedangkan report terbaru memakai `time_to_target_0_60_s`. Karena tidak ada model mencapai 0.60, kolom TTT kosong. Untuk penulisan, target harus dikunci: 0.75 untuk continuity lama atau 0.60 untuk standar baru.

5. Dataset task perlu diputuskan.
   Ada dua sumber: file lama `cpm_pso_input_part10_19_timeseries.csv` dan file runner sekarang `spreadsheet_export.csv`. Kalau skripsi memakai angka lama, gunakan file lama. Kalau memakai output terbaru, dokumentasi dataset harus ikut berubah.

## Fase 2: Implementasi VPS (`main3.py`)

Fase ini adalah validasi/implementasi setelah fase simulasi. Tujuannya bukan lagi membandingkan semua optimizer dari nol, tetapi menjalankan kandidat Tabu hybrid pada edge nodes nyata dan membandingkannya terhadap baseline random.

### Alur VPS Saat Ini

1. `main3.py` membuat task dengan `generate_batch(N_TASKS)`.
2. Baseline `random` dijalankan `N_RANDOM_BASELINES`, default 5 kali.
3. Hasil baseline random dirata-ratakan.
4. `E_ref` dan `L_ref` dibentuk dari baseline random.
5. Mode optimasi utama adalah `tabu_legacy_hybrid`.
6. Task dikirim ke edge node melalui HTTP.
7. Edge node menjalankan workload nyata `cpu_mem_burn`.
8. Hasil real seperti latency, execution time, task-clock, cpu-clock, dan memory bytes dikumpulkan.
9. Metrik random vs Tabu hybrid dibandingkan.

### Yang Perlu Ditambahkan ke Base Knowledge

| Update sistem VPS | Penjelasan |
|---|---|
| Baseline VPS bukan Round-Robin | `main3.py` memakai random baseline beberapa kali, default 5 run. |
| Task generator data-driven | Task baru diambil dari calibration logs, diberi variasi 5%, lalu diubah menjadi `cpu_time_target_ms` dan `memory_bytes`. |
| Ada kalibrasi `CPU_TIME_UNIT_MS` | Generator membaca `outputs/calibration/cpu_time_unit_calibration.json`; nilai saat ini sekitar 372.235 ms menurut dokumen flow. |
| Node VPS memakai tier resource | `edge-1` sampai `edge-3`: 2 CPU/2 GB; `edge-4` sampai `edge-6`: 4 CPU/4 GB; `edge-7` sampai `edge-9`: 8 CPU/8 GB. |
| Power model VPS lebih realistis | Setiap tier punya `idle_power_w` dan `max_power_w`, bukan parameter statis lama. |
| Workload dieksekusi nyata | Edge node menjalankan worker dengan `perf stat` untuk membaca `task-clock` dan `cpu-clock`. |
| Objective VPS punya penalti tambahan | Ada penalti high-tier usage, resource pressure, concurrency, dan energy overshoot. |
| Metrik VPS punya dua kelompok | `REAL`: latency, execution time, estimated real energy, task-clock. `MODEL`: model latency dan model energy. |

### Hasil VPS Terbaru yang Bisa Dipakai Hati-hati

Berdasarkan `outputs/main3_energy_first_selected_200_300_400.json`, konfigurasi yang tercatat:

```text
N_RANDOM_BASELINES = 5
local_mode = hybrid
energy_weight = 0.85
high_power_penalty_weight = 2.25
vps_penalty_scale = 0.5
```

Ringkasan hasil:

| N tasks | Random latency | Main3 latency | Latency gain | Random energy J | Main3 energy J | Energy gain J |
|---:|---:|---:|---:|---:|---:|---:|
| 200 | 1.1382 | 0.8754 | +0.2628 | 4969.18 | 5266.40 | -297.22 |
| 300 | 1.3441 | 1.0095 | +0.3347 | 7482.81 | 7506.28 | -23.47 |
| 400 | 1.3700 | 1.1335 | +0.2365 | 10018.14 | 9863.46 | +154.68 |

Interpretasi hati-hati:

1. VPS menunjukkan peningkatan latency yang konsisten untuk 200, 300, dan 400 task.
2. Energy nyata belum selalu membaik. Pada 200 dan 300 task, estimated real energy naik sedikit dibanding random; pada 400 task energy membaik.
3. Model energy selalu turun cukup besar, tetapi real energy tidak selalu mengikuti. Ini harus dibahas sebagai gap model-vs-real, bukan disembunyikan.

## Pemetaan BAB dari Base Knowledge Lama

| Bagian lama | Aksi revisi |
|---|---|
| 1. Gambaran Umum Penelitian | Pertahankan dua objective, tetapi ubah narasi menjadi dua fase: simulasi menentukan kandidat, VPS memvalidasi kandidat. Jangan langsung klaim final `TABU+DIFFUSION` terbaik sebelum CDF selesai. |
| 2. Dataset | Pecah menjadi dataset simulasi dan dataset VPS. Simulasi: Google machine dataset + task CSV. VPS: data-driven task generator dari calibration logs. |
| 3. Pemodelan Sistem | Pecah menjadi model simulasi grid 3x3 dan model VPS tier-based. Heterogeneity tetap system model, tetapi bentuknya berbeda di dua fase. |
| 4. Implementasi Solusi | Untuk simulasi, jelaskan objective lama `0.6 E + 0.4 L`. Untuk VPS, jelaskan objective hybrid dengan baseline random dan penalty tambahan. |
| 5. Metode yang Dibandingkan | Untuk simulasi, tetap bahas global optimizer dan local optimizer. Untuk VPS, fokus pada random baseline vs `tabu_legacy_hybrid`. |
| 6. Pengujian | Pisahkan: simulasi convergence/CDF dan VPS real execution. Jangan campur metric simulation objective dengan real VPS latency/energy. |
| 7. Analisis Hasil | Perlu diperbarui total setelah CDF selesai. Untuk VPS, tulis bahwa latency konsisten membaik, energy real masih trade-off pada beberapa ukuran task. |
| 8. Pertanyaan Terbuka | Ganti dengan daftar gap final: CDF incomplete, dataset decision, target TTT, missing combinations, model-real energy gap. |
| 9. Terminologi Final | Pertahankan prinsip konsistensi, tetapi update istilah agar cocok dengan dua fase. |

## Terminologi yang Disarankan

Gunakan istilah berikut supaya narasi tidak bertabrakan:

| Konteks | Istilah disarankan |
|---|---|
| Metode penelitian umum | Hybrid Tabu-Diffusion Scheduling |
| Fase simulasi | Simulation-based optimizer comparison |
| Fase VPS | VPS-based implementation and validation |
| Global optimizer | Heterogeneity-aware Tabu Search |
| Local mechanism | Diffusion Local Refinement atau Diffusion Local Balancing Mechanism |
| Baseline simulasi | Round-Robin baseline |
| Baseline VPS | Random baseline average |
| Sistem simulasi | Heterogeneous grid-based edge simulation |
| Sistem VPS | Tier-based heterogeneous edge deployment |

Catatan: istilah `Diffusion Local Balancing Mechanism` masih bisa dipakai, tetapi untuk kode sekarang lebih akurat jika dijelaskan sebagai task-level neighbor-aware refinement yang dipicu saat stagnasi.

## Celah Penelitian yang Harus Dibuka Jujur

1. `TABU+DIFFUSION` belum terbukti paling baik pada output terbaru.
   Secara naratif, metode ini tetap kandidat utama karena menjadi arah implementasi VPS. Namun secara angka single-run terbaru, `TABU+NONE` sedikit lebih baik. Solusinya: selesaikan CDF 300 runs atau revisi klaim menjadi "competitive and selected for VPS validation because it combines global search and local refinement".

2. CDF statistik belum lengkap.
   Skripsi sebaiknya tidak menulis "300 runs per method" sebagai hasil final sebelum semua kombinasi selesai dan `cdf_summary.csv` tersedia.

3. Ada inkonsistensi dataset task.
   Base lama menyebut 291,623 tasks dari `cpm_pso_input_part10_19_timeseries.csv`. Runner terbaru memakai `spreadsheet_export.csv` 504,567 rows. Ini perlu diputuskan agar bab dataset tidak terlihat berubah-ubah.

4. `latency_ms` pada runner terbaru diisi 0.0 jika tidak ada.
   Ini tidak salah untuk mode kompatibilitas, tetapi perlu dijelaskan. Kalau tidak, pembaca bisa mengira latency dataset dipakai padahal yang dominan adalah model service/queue/memory.

5. Model energy dan real energy belum sepenuhnya selaras.
   Pada VPS 200 dan 300 task, model energy turun tetapi estimated real energy naik. Ini bukan kegagalan fatal, tetapi harus dibingkai sebagai trade-off dan batasan model.

6. Semua metode tidak diimplementasikan di VPS.
   VPS saat ini memvalidasi `tabu_legacy_hybrid` terhadap random baseline, bukan menjalankan PSO/BFO/CPM/Diffusion lengkap seperti simulasi. Ini harus dijelaskan sebagai tahap implementasi kandidat terpilih, bukan perbandingan semua metode di VPS.

7. Topologi local refinement berbeda antar fase.
   Simulasi memakai grid 4-neighbor. Implementasi VPS saat ini memakai adjacency semua-node-ke-semua-node pada assignment engine. Jika ingin mempertahankan klaim grid topology sampai VPS, kode atau dokumentasi perlu diselaraskan.

## Rekomendasi Sebelum Update Base Knowledge Final

1. Putuskan dataset simulasi final.
   Pilih apakah laporan memakai hasil lama dari `cpm_pso_input_part10_19_timeseries.csv` atau hasil terbaru dari `spreadsheet_export.csv`.

2. Selesaikan run CDF statistik.
   Minimal hasilkan `cdf_summary.csv` untuk semua metode yang diklaim dibandingkan. Jika runtime terlalu lama, gunakan jumlah run yang lebih kecil tapi jujur, misalnya 50 atau 100 runs, dan tulis sebagai keterbatasan.

3. Kunci target TTT.
   Gunakan satu target saja, misalnya objective <= 0.75 untuk continuity base lama, atau objective <= 0.60 jika memang ingin standar baru. Jangan campur keduanya.

4. Revisi klaim metode terbaik.
   Sebelum CDF lengkap, gunakan kalimat aman: "Tabu-Diffusion dipilih sebagai kandidat implementasi VPS karena menggabungkan pencarian global Tabu dan refinement lokal Diffusion, serta menunjukkan performa kompetitif pada simulasi."

5. Pisahkan hasil simulasi dan hasil VPS dalam BAB 4.
   Simulasi membahas objective, convergence, CDF. VPS membahas real latency, execution time, task-clock, cpu-clock, estimated real energy, dan distribusi node.

6. Jelaskan gap model-real sebagai keterbatasan.
   Ini justru membuat skripsi lebih kuat karena menunjukkan evaluasi dilakukan pada sistem nyata, bukan hanya model yang selalu mendukung klaim.

## Draft Struktur Base Knowledge Baru

Struktur yang disarankan:

1. Gambaran umum penelitian
2. Dua fase penelitian
3. Dataset dan workload
4. Pemodelan simulasi program
5. Metode simulasi dan objective function
6. Hasil simulasi program
7. Implementasi VPS
8. Model workload dan kalibrasi VPS
9. Objective dan penalti VPS
10. Hasil validasi VPS
11. Gap, keterbatasan, dan keputusan terminologi
12. Quick reference final

## Kesimpulan Pemetaan

Base knowledge lama masih sangat berguna, tetapi harus dijadikan fondasi fase simulasi, bukan dokumentasi tunggal untuk seluruh sistem saat ini. Pembaruan paling penting adalah memisahkan dengan tegas:

1. `Comparision.ipynb` sebagai simulasi pembanding algoritma.
2. `main3.py` sebagai implementasi dan validasi VPS dari kandidat Tabu hybrid.

Klaim paling berisiko saat ini adalah menyatakan `TABU+DIFFUSION` sudah terbukti paling baik secara statistik. Klaim yang lebih aman dan jujur: `TABU+DIFFUSION` adalah kandidat utama yang dipilih untuk implementasi VPS karena performanya kompetitif di simulasi dan karena mekanismenya paling cocok diterjemahkan ke validasi sistem nyata.
