import argparse
import importlib.util
import json
import random
import string
import time
from pathlib import Path

SAFE_CHARS = string.ascii_letters + string.digits + " _-"


def load_program(path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_random_string(rng: random.Random, min_len=4, max_len=20):
    n = rng.randint(min_len, max_len)
    return "".join(rng.choice(SAFE_CHARS) for _ in range(n))


def make_value(rng: random.Random, depth: int):
    if depth <= 0:
        choice = rng.randint(0, 3)
        if choice == 0:
            return rng.randint(-100000, 100000)
        if choice == 1:
            return make_random_string(rng)
        if choice == 2:
            return True if rng.randint(0, 1) == 0 else False
        return None
    choice = rng.randint(0, 4)
    if choice == 0:
        return rng.randint(-100000, 100000)
    if choice == 1:
        return make_random_string(rng)
    if choice == 2:
        return [make_value(rng, depth - 1) for _ in range(rng.randint(0, 5))]
    if choice == 3:
        obj = {}
        for _ in range(rng.randint(0, 5)):
            obj[make_random_string(rng, 3, 10)] = make_value(rng, depth - 1)
        return obj
    return None


def generate_dataset(seed: int, count: int):
    rng = random.Random(seed)
    data = []
    for _ in range(count):
        obj = make_value(rng, depth=3)
        s = json.dumps(obj, separators=(",", ":"))
        data.append((s, obj))
    return data


def verify(program, dataset):
    parse = getattr(program, "parse_json_subset", None)
    serialize = getattr(program, "serialize_json_subset", None)
    parse_and_serialize = getattr(program, "parse_and_serialize", None)
    if parse is None or serialize is None:
        raise RuntimeError("parse_json_subset and serialize_json_subset are required")

    for s, ref_obj in dataset:
        obj = parse(s)
        if obj != ref_obj:
            raise ValueError("parse mismatch")
        out = serialize(obj)
        round_trip = json.loads(out)
        if round_trip != ref_obj:
            raise ValueError("serialize mismatch")
        if parse_and_serialize is not None:
            out2 = parse_and_serialize(s)
            if json.loads(out2) != ref_obj:
                raise ValueError("parse_and_serialize mismatch")


def benchmark(program, dataset, rounds: int, batch_size: int):
    parse_and_serialize = getattr(program, "parse_and_serialize", None)
    if parse_and_serialize is None:
        parse = getattr(program, "parse_json_subset")
        serialize = getattr(program, "serialize_json_subset")

        def parse_and_serialize(s):
            return serialize(parse(s))

    latencies = []
    total_bytes = 0
    total_ops = 0
    total_time = 0.0
    data = [s for s, _ in dataset]

    for _ in range(rounds):
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            t0 = time.perf_counter()
            for s in batch:
                out = parse_and_serialize(s)
                total_bytes += len(s)
                total_bytes += len(out)
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

    return {
        "ops_per_sec": ops_per_sec,
        "p99_latency_us": p99 * 1e6,
        "bytes_processed": total_bytes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    program = load_program(args.program)
    dataset = generate_dataset(args.seed, args.count)

    if not args.skip_verify:
        verify(program, dataset)

    metrics = benchmark(program, dataset, rounds=args.rounds, batch_size=args.batch)

    if args.json:
        path = Path(args.json)
        path.write_text(json.dumps(metrics), encoding="utf-8")
    else:
        print(json.dumps(metrics))


if __name__ == "__main__":
    main()
