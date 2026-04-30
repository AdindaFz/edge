import argparse
import json
import numpy as np
import os

# Tier-based configuration
NODE_TIER = os.getenv("NODE_TIER", "mid")  # low | mid | high

TIER_CONFIG = {
    "low": {"vector_size": 128, "compute_rounds": 2},
    "mid": {"vector_size": 256, "compute_rounds": 4},
    "high": {"vector_size": 512, "compute_rounds": 8},
}

VECTOR_SIZE = TIER_CONFIG[NODE_TIER]["vector_size"]
COMPUTE_ROUNDS = TIER_CONFIG[NODE_TIER]["compute_rounds"]

CHECKSUM_WINDOW_BYTES = 32786
MAX_TOUCHED_PAGES = 1024
PAGE_SIZE = 4096
DEFAULT_TOUCH_ROUNDS = 1  # Reduced from 4 to lower task weight


def run_chunk(memory_bytes, seed, touch_rounds):
    rng = np.random.default_rng(seed)

    buf = np.zeros(memory_bytes, dtype=np.uint8)
    page_count = max(1, min(memory_bytes // PAGE_SIZE, MAX_TOUCHED_PAGES))
    page_indices = np.arange(page_count, dtype=np.int64) * PAGE_SIZE

    for r in range(touch_rounds):
        value = np.uint8((seed + r) & 0xFF)
        buf[page_indices] ^= value

    vec = rng.integers(1, 2**31 - 1, size=VECTOR_SIZE, dtype=np.uint64)

    for _ in range(COMPUTE_ROUNDS):
        vec = vec * np.uint64(6364136223846793005) + np.uint64(1)
        vec ^= (vec >> np.uint64(13))
        vec ^= (vec << np.uint64(7))

    checksum = int(np.bitwise_xor.reduce(buf[: min(buf.size, CHECKSUM_WINDOW_BYTES)]).item())
    checksum ^= int(np.bitwise_xor.reduce(vec).item())

    print(json.dumps({
        "checksum": checksum,
        "memory_bytes": int(memory_bytes),
        "seed": int(seed),
        "touch_rounds": int(touch_rounds),
        "vector_size": int(VECTOR_SIZE),
        "compute_rounds": int(COMPUTE_ROUNDS),
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-bytes", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--touch-rounds", type=int, default=DEFAULT_TOUCH_ROUNDS)
    args = parser.parse_args()

    run_chunk(args.memory_bytes, args.seed, args.touch_rounds)
