# Penjelasan Lengkap Task Generator di Sistem Edge Computing

## Pengantar
Task generator adalah komponen kunci dalam sistem edge computing ini. Ia bertugas membuat sekumpulan task (tugas) yang akan dijadwalkan ke edge node. Task ini tidak sepenuhnya acak, tetapi didasarkan pada data kalibrasi dari eksekusi sebelumnya untuk membuat simulasi lebih realistis. Ini penting untuk fase validasi VPS (Virtual Private Server), di mana kita menguji penjadwalan task pada node nyata.

## Alur Kode Task Generator
Task generator terletak di file `central/task_generator.py`. Alurnya dimulai dari fungsi `generate_batch(n_tasks, seed=42)` yang membuat batch task, lalu memanggil `generate_task(...)` untuk setiap task.

### Langkah 1: Membuat Batch Task
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
- Fungsi ini membuat `n_tasks` task dengan seed yang unik untuk setiap task.
- Seed memastikan hasil deterministik (bisa diulang).

### Langkah 2: Membuat Satu Task
```python
def generate_task(task_id=None, seed=None, use_calibration=None):
    cpu_time_unit_ms = load_cpu_time_unit_ms()
    # ... (load calibration data)
    if calibration_tasks:
        template = calibration_tasks[seed % len(calibration_tasks)]
        cpu_demand = float(template.get("cpu_demand", 1.0))
        memory_demand = float(template.get("memory_demand", 0.5))
        cpu_demand *= np.random.normal(1.0, 0.05)  # Variasi 5%
        memory_demand *= np.random.normal(1.0, 0.05)
        cpu_demand = np.clip(cpu_demand, 0.8, 3.6)
        memory_demand = np.clip(memory_demand, 0.125, 0.75)
        cpu_time_target_ms = cpu_demand * cpu_time_unit_ms
        memory_bytes = int(memory_demand * MEMORY_UNIT_BYTES)
    else:
        # Fallback teoritis
        cpu_time_target_ms = float(np.random.uniform(200, 900))
        memory_mb = int(np.random.uniform(128, 768))
        memory_bytes = memory_mb * 1024 * 1024
    # ... (return task dict)
```
- **Kalibrasi**: Jika ada data kalibrasi, ambil template dari log eksekusi sebelumnya.
- **Variasi**: Tambahkan variasi kecil (5%) agar task tidak identik.
- **Fallback**: Jika tidak ada kalibrasi, gunakan nilai acak teoritis.

### Langkah 3: Klasifikasi Task
```python
def classify_task(cpu_time_target_ms, memory_bytes):
    mem_gb = memory_bytes / (1024 ** 3)
    if cpu_time_target_ms < 325 and mem_gb < 0.25:
        return "small"
    elif cpu_time_target_ms < 675 and mem_gb < 0.75:
        return "medium"
    return "large"
```
- Task diklasifikasi berdasarkan CPU time dan memori untuk analisis distribusi.

## Kalibrasi Task Generator
Kalibrasi menggunakan data dari eksekusi sebelumnya di `outputs/calibration/workload_calibration_*.jsonl`.

### Sumber Data Kalibrasi
- File JSONL berisi hasil eksekusi task nyata.
- Setiap baris: `{"cpu_demand": 1.2, "memory_demand": 0.4, ...}`

### Fungsi Load Kalibrasi
```python
def load_calibration_data():
    calibration_dir = Path("outputs/calibration")
    tasks = []
    for path in sorted(calibration_dir.glob("workload_calibration_*.jsonl")):
        with path.open() as f:
            for line in f:
                row = json.loads(line)
                if "cpu_demand" in row and "memory_demand" in row:
                    tasks.append(row)
    return tasks
```
- Membaca semua file kalibrasi dan menyimpan sebagai list template.

### CPU Time Unit
```python
def load_cpu_time_unit_ms():
    try:
        with CPU_TIME_UNIT_CALIBRATION_PATH.open() as f:
            payload = json.load(f)
        recommended = payload.get("recommended_cpu_time_unit_ms")
        if recommended:
            return float(recommended)
    except:
        pass
    return CPU_TIME_UNIT_MS  # Default 250.0 ms
```
- Menggunakan nilai kalibrasi untuk konversi demand ke waktu nyata.

## Contoh Perhitungan Task
Misalkan kita buat task dengan seed=42, menggunakan kalibrasi.

### Data Kalibrasi Contoh
- Template dari log: `{"cpu_demand": 1.5, "memory_demand": 0.6}`
- CPU_TIME_UNIT_MS = 372.235 ms (dari kalibrasi)

### Perhitungan
1. **Ambil template**: `cpu_demand = 1.5`, `memory_demand = 0.6`
2. **Tambah variasi**: 
   - `cpu_demand *= np.random.normal(1.0, 0.05)` → Misal hasil 1.52
   - `memory_demand *= np.random.normal(1.0, 0.05)` → Misal hasil 0.61
3. **Clip ke rentang**: Tetap dalam 0.8-3.6 dan 0.125-0.75
4. **Konversi**:
   - `cpu_time_target_ms = 1.52 * 372.235 ≈ 566.2 ms`
   - `memory_bytes = 0.61 * 1 GB ≈ 654 MB`
5. **Klasifikasi**: `566.2 < 675` dan `0.654 < 0.75` → "medium"

### Task Final
```json
{
  "task_id": "task_0",
  "cpu_demand": 1.52,
  "memory_demand": 0.61,
  "cpu_time_target_ms": 566.2,
  "memory_bytes": 671088640,
  "task_size": "medium",
  "task_type": "cpu_mem_burn"
}
```

## Kesimpulan
Task generator membuat task yang realistis dengan data kalibrasi, memungkinkan validasi penjadwalan pada VPS. Ini membedakan sistem ini dari simulasi murni, karena task didasarkan pada eksekusi nyata. Untuk presentasi, tunjukkan alur kode, kalibrasi, dan contoh perhitungan ini agar dosen memahami bagaimana sistem menghasilkan beban kerja yang akurat. Jika ada pertanyaan, saya siap bantu!