import os

# Network Configuration
SYSTEM_MODE = "online"
# "online" | "offline"

# Menggunakan IP dari adinda-central
CENTRAL_IP = "10.33.102.106"
CENTRAL_PORT = 8000

EDGE_NODES = {
    "edge-1": {
        "ip": "10.33.102.107",    # adinda1
        "port": 8001
    },
    "edge-2": {
        "ip": "10.33.102.108",    # adinda2
        "port": 8002
    },
    "edge-3": {
        "ip": "10.33.102.109",    # adinda3
        "port": 8003
    },
    "edge-4": {
        "ip": "10.33.102.110",    # adinda4
        "port": 8004
    },
    "edge-5": {
        "ip": "10.33.102.111",    # adinda5
        "port": 8005
    },
    "edge-6": {
        "ip": "10.33.102.112",    # adinda6
        "port": 8006
    },
    "edge-7": {
        "ip": "10.33.102.113",    # adinda7
        "port": 8007
    },
    "edge-8": {
        "ip": "10.33.102.114",    # adinda8
        "port": 8008
    },
    "edge-9": {
        "ip": "10.33.102.115",    # adinda9
        "port": 8009
    }
}

# System Configuration
LOG_LEVEL = "INFO"
MAX_WORKERS = 4
TASK_TIMEOUT = 300  # seconds
HEALTH_CHECK_INTERVAL = 10  # seconds
