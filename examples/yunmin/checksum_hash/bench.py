import argparse
import importlib.util
import json
import random
import time
from pathlib import Path


FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def load_program(path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fnv1a_reference(data: bytes) -> int:
    h = FNV_OFFSET_BASIS
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h


def generate_dataset(seed: int, count: int, size: int):
    rng = random.Random(seed)
    data = []
    for _ in range(count):
        buf = bytearray(rng.getrandbits(8) for _ in range(size))
        data.append(bytes(buf))
    return data


def verify(program, dataset):
    checksum = getattr(program, "checksum32", None)
    if checksum is None:
        raise RuntimeError("checksum32 is required")
    for item in dataset:
        if checksum(item) != fnv1a_reference(item):
            raise ValueError("checksum mismatch")


def benchmark(program, dataset, rounds: int, batch_size: int):
    checksum = getattr(program, "checksum32")
    latencies = []
    total_ops = 0
    total_time = 0.0
    total_bytes = 0

    for _ in range(rounds):
        for i in range(0, len(dataset), batch_size):
            batch = dataset[i : i + batch_size]
            t0 = time.perf_counter()
            for item in batch:
                checksum(item)
                total_bytes += len(item)
            t1 = time.perf_counter()
            dt = t1 - t0
            total_ops += len(batch)
            total_time += dt
            if len(batch) > 0:
                latencies.append(dt / len(batch))

    if total_time <= 0:
        total_time = 1e-9

    ops_per_sec = total_ops / total_time
    latencies_sorted = sorted(latencies)
    p99 = latencies_sorted[int(0.99 * (len(latencies_sorted) - 1))] if latencies_sorted else 0.0
    gb_per_sec = (total_bytes / (1024 * 1024 * 1024)) / total_time

    return {
        "ops_per_sec": ops_per_sec,
        "p99_latency_us": p99 * 1e6,
        "gb_per_sec": gb_per_sec,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--seed", type=int, default=999)
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--batch", type=int, default=200)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    program = load_program(args.program)
    dataset = generate_dataset(args.seed, args.count, args.size)

    if not args.skip_verify:
        verify(program, dataset)

    metrics = benchmark(program, dataset, rounds=args.rounds, batch_size=args.batch)

    if args.json:
        Path(args.json).write_text(json.dumps(metrics), encoding="utf-8")
    else:
        print(json.dumps(metrics))


if __name__ == "__main__":
    main()
