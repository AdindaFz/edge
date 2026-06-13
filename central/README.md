# Central Module

Folder ini berisi layanan central gateway, scheduler, model, dan optimizer.
Modul Python runtime dipertahankan pada level ini agar import `central.*` dan
perintah menjalankan gateway tetap kompatibel.

## Struktur

```text
central/
|-- gateway.py              # FastAPI central gateway dan dashboard API
|-- scheduler.py            # Scheduler untuk task yang masuk melalui gateway
|-- task_generator.py       # Generator workload CPU dan memori
|-- node_resources.py       # Profil kapasitas dan daya edge node
|-- offline_runner.py       # Orkestrasi eksekusi eksperimen ke edge node
|-- assignment_engine.py    # Pembentukan assignment Random/Tabu
|-- optimizer_runner.py     # Implementasi pencarian Tabu hibrida
|-- local_optimizers.py     # Local refinement berbasis Diffusion
|-- simulation_model.py     # Model energi, latensi, dan kalibrasi aktif
|-- system_model.py         # Model historis/eksperimental
|-- experiment_runner.py    # Runner historis untuk pengiriman melalui gateway
`-- web/
    |-- dashboard.html      # Dashboard yang aktif digunakan gateway
    `-- legacy/
        |-- dashboard_v1.html
        `-- dashboard_v2.html
```

## Menjalankan Gateway

Perintah tetap sama:

```bash
cd /home/adinda-central/edge
venv/bin/python central/gateway.py
```

atau melalui modul:

```bash
venv/bin/python -m uvicorn central.gateway:app --host 0.0.0.0 --port 8000
```

Dashboard aktif dilayani oleh route `/`. File di `web/legacy/` hanya disimpan
sebagai referensi versi lama dan tidak digunakan saat runtime.
