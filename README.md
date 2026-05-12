# Edge Computing System

## Overview
Distributed edge computing system with central gateway and multiple edge nodes.

## Architecture
- Central Gateway: task distribution & monitoring
- Edge Nodes: task execution
- Shared Models: data contract

## Setup

### 1. Clone repo
```bash
git clone https://github.com/AdindaFz/edge.git
cd edge
```

## Edge Node Deployment

Gunakan package khusus edge node untuk dikirim ke setiap node `adinda1` sampai `adinda9`.

### Buat package dari central
```bash
cd /home/adinda-central/edge
./package_edge_node.sh
```

Output:
```bash
dist/edge-node-payload.tar.gz
```

### Jalankan di masing-masing node
Setelah package diekstrak di node:
```bash
cd ~/edge
python3 -m pip install -r requirements.txt
./run_edge_node.sh
```

Script `run_edge_node.sh` otomatis membaca hostname:

| Hostname | NODE_ID | NODE_PORT |
|---|---|---:|
| adinda1 | edge-1 | 8001 |
| adinda2 | edge-2 | 8002 |
| adinda3 | edge-3 | 8003 |
| adinda4 | edge-4 | 8004 |
| adinda5 | edge-5 | 8005 |
| adinda6 | edge-6 | 8006 |
| adinda7 | edge-7 | 8007 |
| adinda8 | edge-8 | 8008 |
| adinda9 | edge-9 | 8009 |

Jika hostname belum sesuai, jalankan manual:
```bash
EDGE_INDEX=1 ./run_edge_node.sh
```

Cek mapping tanpa menjalankan server:
```bash
EDGE_INDEX=1 ./run_edge_node.sh --print-config
```

Catatan: workload worker menggunakan command system `perf`, jadi pastikan paket `perf`/`linux-tools` tersedia di setiap node.
