import argparse
import importlib.util
import json
import random
import time
from collections import OrderedDict
from pathlib import Path


def load_program(path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_trace(seed: int, length: int, keyspace: int):
    rng = random.Random(seed)
    trace = []
    for _ in range(length):
        if rng.random() < 0.7:
            # Hot set bias
            trace.append(rng.randint(0, keyspace // 5))
        else:
            trace.append(rng.randint(0, keyspace))
    return trace


def reference_hits(trace, capacity: int) -> int:
    cache = OrderedDict()
    hits = 0
    for key in trace:
        if key in cache:
            hits += 1
            cache.move_to_end(key)
        else:
            if len(cache) >= capacity:
                cache.popitem(last=False)
            cache[key] = True
    return hits


def verify(program, trace, capacity: int, expected_hits: int):
    cache_cls = getattr(program, "LRUCache", None)
    if cache_cls is None:
        raise RuntimeError("LRUCache class is required")

    cache = cache_cls(capacity)
    hits = 0
    for key in trace:
        if cache.access(key):
            hits += 1
    if hits != expected_hits:
        raise ValueError("hit count mismatch")


def benchmark(program, trace, capacity: int, rounds: int, batch_size: int):
    cache_cls = getattr(program, "LRUCache")
    latencies = []
    total_ops = 0
    total_time = 0.0

    for _ in range(rounds):
        cache = cache_cls(capacity)
        for i in range(0, len(trace), batch_size):
            batch = trace[i : i + batch_size]
            t0 = time.perf_counter()
            for key in batch:
                cache.access(key)
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

    return {"ops_per_sec": ops_per_sec, "p99_latency_us": p99 * 1e6}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--seed", type=int, default=121)
    parser.add_argument("--length", type=int, default=200000)
    parser.add_argument("--keyspace", type=int, default=5000)
    parser.add_argument("--capacity", type=int, default=1024)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--batch", type=int, default=2000)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    program = load_program(args.program)
    trace = generate_trace(args.seed, args.length, args.keyspace)
    expected_hits = reference_hits(trace, args.capacity)

    if not args.skip_verify:
        verify(program, trace, args.capacity, expected_hits)

    metrics = benchmark(program, trace, args.capacity, rounds=args.rounds, batch_size=args.batch)

    if args.json:
        Path(args.json).write_text(json.dumps(metrics), encoding="utf-8")
    else:
        print(json.dumps(metrics))


if __name__ == "__main__":
    main()
