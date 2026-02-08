import argparse
import importlib.util
import json
import os
import random
import time
from pathlib import Path


def load_program(path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_dataset(seed: int, count: int, size: int):
    rng = random.Random(seed)
    data = []
    for _ in range(count):
        buf = bytearray()
        while len(buf) < size:
            if rng.random() < 0.6:
                # Run
                b = rng.randint(0, 255)
                run_len = rng.randint(3, 40)
                buf.extend([b] * run_len)
            else:
                # Noise
                buf.append(rng.randint(0, 255))
        data.append(bytes(buf[:size]))
    return data


def verify(program, dataset):
    compress = getattr(program, "compress", None)
    decompress = getattr(program, "decompress", None)
    if compress is None or decompress is None:
        raise RuntimeError("compress and decompress are required")
    for item in dataset:
        enc = compress(item)
        dec = decompress(enc)
        if dec != item:
            raise ValueError("round-trip mismatch")


def benchmark(program, dataset, rounds: int, batch_size: int):
    compress = getattr(program, "compress")
    decompress = getattr(program, "decompress")

    latencies = []
    total_ops = 0
    total_time = 0.0
    total_bytes = 0

    for _ in range(rounds):
        for i in range(0, len(dataset), batch_size):
            batch = dataset[i : i + batch_size]
            t0 = time.perf_counter()
            for item in batch:
                enc = compress(item)
                dec = decompress(enc)
                if dec != item:
                    raise ValueError("round-trip mismatch")
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

    mb_per_sec = (total_bytes / (1024 * 1024)) / total_time

    return {
        "ops_per_sec": ops_per_sec,
        "p99_latency_us": p99 * 1e6,
        "mb_per_sec": mb_per_sec,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--seed", type=int, default=777)
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--batch", type=int, default=50)
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
