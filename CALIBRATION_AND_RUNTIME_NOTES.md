# Calibration And Runtime Notes

## Status

Dokumen ini merangkum perubahan terbaru pada sistem edge computing untuk:

- menjalankan task secara nyata di edge node,
- menghitung latency dan energi estimasi dari hasil runtime,
- menyiapkan kalibrasi awal antara workload task dan kapasitas node heterogen.

Catatan penting:

- implementasi ini sudah bisa dipakai sebagai baseline eksperimen,
- tetapi hasilnya masih perlu divalidasi di VPS edge node,
- jadi beberapa bagian masih bersifat sementara dan belum final untuk klaim skripsi.


## Tujuan Perubahan

Sebelumnya task lebih dekat ke simulasi. Sekarang sistem diarahkan agar:

1. task benar-benar dieksekusi oleh edge node,
2. random vs tabu memakai task yang sama,
3. runtime menghasilkan metrik nyata seperti:
   - execution time,
   - latency,
   - observed task clock,
   - observed memory usage,
4. energi tidak lagi salah dimaknai sebagai task-clock mentah.


## Konsep Task Sekarang

Task sekarang merepresentasikan workload komputasi sintetis bertipe `cpu_mem_burn`.

Task punya dua sisi:

- sisi model/optimasi:
  - `cpu_demand`
  - `memory_demand`
  - `compute_cost`
- sisi runtime nyata:
  - `cpu_time_target_ms`
  - `memory_bytes`
  - `payload`

Maknanya:

- `cpu_demand` adalah beban relatif untuk optimizer,
- `cpu_time_target_ms` adalah target total kerja CPU nyata,
- `memory_demand` adalah beban memori relatif untuk optimizer,
- `memory_bytes` adalah ukuran memori nyata yang dialokasikan worker.


## File Yang Sudah Berubah

### 1. `shared/models.py`

Task diperluas agar mendukung workload nyata:

- `task_type`
- `cpu_time_target_ms`
- `memory_bytes`
- `payload`

### 2. `edge/workload_worker.py`

Worker menjalankan satu chunk workload nyata:

- alokasi memori sesuai `memory_bytes`,
- akses halaman memori,
- loop komputasi numerik,
- keluarkan checksum/output JSON.

### 3. `edge/edge_node.py`

Node sekarang:

- menerima task `cpu_mem_burn`,
- menjalankan workload dengan `perf stat`,
- mengulang chunk sampai `observed_task_clock_ms >= cpu_time_target_ms`,
- mengembalikan hasil task lewat endpoint status/result.

Tambahan terbaru:

- sampling `psutil` saat task berjalan,
- hasil tambahan:
  - `psutil_cpu_avg_percent`
  - `psutil_cpu_peak_percent`
  - `psutil_mem_avg_percent`
  - `psutil_mem_peak_percent`

### 4. `central/task_generator.py`

Generator sekarang:

- menghasilkan task runtime nyata,
- memakai konversi:
  - `cpu_demand = cpu_time_target_ms / CPU_TIME_UNIT_MS`
  - `memory_demand = memory_bytes / MEMORY_UNIT_BYTES`

Tambahan terbaru:

- `build_cpu_mem_burn_task(...)`
- `generate_calibration_tasks(...)`

Preset kalibrasi saat ini:

- `light`: `150 ms`, `64 MB`
- `medium`: `400 ms`, `128 MB`
- `heavy`: `800 ms`, `256 MB`

### 5. `central/offline_runner.py`

Runner sekarang:

- bisa polling hasil task langsung ke edge node,
- menyimpan metrik runtime yang lebih lengkap,
- menghitung energi estimasi berbasis runtime,
- mendukung `forced_assignments` untuk kalibrasi terarah ke node tertentu.

### 6. `central/node_resources.py`

Node resource sekarang punya profil daya:

- `idle_power_w`
- `max_power_w`

Tujuannya agar model energi dan estimasi runtime lebih masuk akal.

### 7. `central/simulation_model.py`

Model energi optimizer sekarang memakai:

- `idle_powers`
- `max_powers`

Bukan lagi konstanta generik yang sama untuk semua node.

### 8. `central/calibration_runner.py`

Runner baru untuk kalibrasi.

Fungsi utama:

- memaksa task kalibrasi dikirim ke node tertentu,
- membandingkan perilaku node low/mid/high,
- mencetak ringkasan runtime dan metrik energi/psutil.


## Perubahan Penting Pada Definisi Energi

Sebelumnya `real energy` salah makna, karena task-clock diperlakukan seperti energi.

Sekarang dibedakan:

- `observed_task_clock_ms`
  - waktu CPU terukur dari `perf`,
  - ini bukan energi.
- `estimated_real_energy_j`
  - energi estimasi dalam joule,
  - dihitung dari:
    - `observed_task_clock_ms`,
    - `cpu_demand`,
    - `memory_demand`,
    - `idle_power_w`,
    - `max_power_w`.
- `estimated_real_energy_kwh`
  - konversi dari joule ke kWh.

Catatan metodologis:

- ini masih `estimated runtime energy`,
- belum `measured hardware energy`,
- karena belum memakai sensor seperti RAPL, PDU, atau IPMI.


## Bagaimana Task Berhenti Saat Runtime

Task tidak berhenti karena timer biasa atau `sleep`.

Logikanya:

1. node membaca `cpu_time_target_ms`,
2. node menjalankan satu chunk workload,
3. `perf` mengukur `task-clock`,
4. task diulang sampai total `task-clock` melewati target.

Jadi jika target `cpu_time_target_ms = 200`, maka task akan berhenti ketika akumulasi `observed_task_clock_ms` sudah melewati sekitar `200 ms`.

Akibatnya:

- hasil nyata tidak harus persis `200.000 ms`,
- bisa sedikit lewat karena eksekusi dilakukan per chunk.


## Kenapa Kalibrasi Diperlukan

Masalah utamanya:

- optimizer masih bekerja dengan skala model,
- runtime bekerja dengan beban nyata,
- node heterogen belum tentu benar-benar cocok dengan skala `cpu = 2/4/8`.

Risikonya:

- di model task terlihat pas,
- di runtime task bisa terlalu ringan atau terlalu berat,
- hasil optimasi terlihat bagus di model tapi lemah di real world.

Karena itu kalibrasi diperlukan untuk menjawab:

1. apakah task `light/medium/heavy` benar-benar terasa beda di runtime,
2. apakah node low/mid/high benar-benar menunjukkan kapasitas berbeda,
3. apakah skala `cpu_demand` vs `cpu` node sudah cukup masuk akal.


## Tujuan Kalibrasi Sekarang

Kalibrasi awal dipakai untuk:

- memeriksa apakah task terlalu ringan atau terlalu berat,
- melihat apakah `psutil` mendukung pembacaan `perf`,
- melihat apakah node low/mid/high membentuk pola realistis.

Node wakil default:

- low: `edge-1`
- mid: `edge-4`
- high: `edge-7`


## Cara Menjalankan Kalibrasi

Saat semua VPS edge node sudah siap, jalankan:

```bash
python3 -m central.calibration_runner
```

Yang dihasilkan:

- ringkasan per node,
- detail per task kalibrasi,
- JSON report di stdout.


## Checklist Yang Perlu Dicek Di Setiap Edge Node

Minimal yang harus sama/tersedia:

1. kode terbaru sinkron:
   - `edge/edge_node.py`
   - `edge/workload_worker.py`
   - `shared/models.py`
2. dependency Python tersedia:
   - `fastapi`
   - `uvicorn`
   - `httpx`
   - `psutil`
   - `numpy`
3. binary `perf` tersedia
4. izin `perf` cukup untuk user yang menjalankan node
5. `NODE_ID` dan `NODE_PORT` benar
6. `CENTRAL_IP` dan `CENTRAL_PORT` di `config.py` benar
7. endpoint node sehat:
   - `GET /health`
   - `POST /tasks`
   - `GET /tasks/{task_id}`


## Apa Yang Belum Final

Bagian yang masih perlu diuji sebelum dijadikan dasar skripsi final:

1. apakah workload kalibrasi `150/400/800 ms` sudah pas,
2. apakah `CPU_TIME_UNIT_MS` sudah masuk akal,
3. apakah kapasitas node `cpu = 2/4/8` masih layak, atau perlu diganti dengan kapasitas efektif hasil benchmark,
4. apakah energi estimasi cukup stabil terhadap hasil real runtime,
5. apakah random vs tabu menunjukkan penurunan latency/energy yang konsisten di beberapa pengulangan.


## Bahasa Aman Untuk Penulisan Skripsi Sementara

Kalau mau menulis sekarang, lebih aman gunakan istilah:

- `runtime-executed synthetic workloads`
- `estimated runtime energy`
- `observed task-clock`
- `preliminary calibration`
- `heterogeneous edge node tiers`

Hindari dulu klaim seperti:

- `ground-truth real energy`
- `fully calibrated heterogeneous capacity`

sebelum hasil kalibrasi node benar-benar keluar.


## Langkah Berikutnya

Saat VPS sudah bisa dipakai lagi:

1. jalankan edge node dengan kode terbaru,
2. jalankan `python3 -m central.calibration_runner`,
3. baca hasil low/mid/high,
4. putuskan apakah perlu:
   - ubah `CPU_TIME_UNIT_MS`,
   - ubah preset task kalibrasi,
   - ubah kapasitas `cpu` node berdasarkan benchmark nyata.


## Kesimpulan Sementara

Implementasi saat ini sudah:

- bergerak dari simulasi menuju eksekusi nyata,
- memisahkan task-clock dari energi,
- menambahkan estimasi energi yang lebih masuk akal,
- menyiapkan jalur kalibrasi untuk node heterogen.

Tetapi hasilnya masih perlu diverifikasi di VPS edge node sebelum diperlakukan sebagai konfigurasi final eksperimen skripsi.
