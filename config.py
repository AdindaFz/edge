# config.py
import os

# Network Configuration
CENTRAL_IP = "192.168.56.109"  # ← Update dengan IP vm-central Anda
CENTRAL_PORT = 8000

EDGE_NODES = {
    "edge-1": {
        "ip": "192.168.56.108",    # ← Update dengan IP vm-edge-1
        "port": 8001
    },
    "edge-2": {
        "ip": "192.168.56.110",    # ← Update dengan IP vm-edge-2
        "port": 8002
    }
}

# System Configuration
LOG_LEVEL = "INFO"
MAX_WORKERS = 4
TASK_TIMEOUT = 300  # seconds
HEALTH_CHECK_INTERVAL = 10  # seconds
