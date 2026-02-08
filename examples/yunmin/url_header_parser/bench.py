import argparse
import importlib.util
import json
import random
import time
from pathlib import Path


HEADER_NAMES = [
    "host",
    "user-agent",
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "connection",
    "content-type",
    "x-request-id",
    "x-forwarded-for",
]


def load_program(path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_request(rng: random.Random):
    method = rng.choice(["GET", "POST", "PUT", "DELETE"])
    path = "/api/" + str(rng.randint(1, 1000)) + "/items"
    version = "HTTP/1.1"
    headers = {}
    for _ in range(rng.randint(6, 10)):
        name = rng.choice(HEADER_NAMES)
        if name == "host":
            value = "service.local"
        elif name == "user-agent":
            value = "bench/1.0"
        elif name == "accept":
            value = "*/*"
        elif name == "accept-encoding":
            value = "gzip, deflate"
        elif name == "connection":
            value = "keep-alive"
        elif name == "content-type":
            value = "application/json"
        elif name == "x-request-id":
            value = f"{rng.randint(100000, 999999)}"
        elif name == "x-forwarded-for":
            value = f"192.168.0.{rng.randint(1, 250)}"
        else:
            value = "no-cache"
        headers[name] = value

    lines = [f"{method} {path} {version}"]
    for name, value in headers.items():
        lines.append(f"{name}: {value}")
    lines.append("")
    lines.append("")
    raw = "\r\n".join(lines).encode("ascii")
    return raw, (method, path, version, headers)


def generate_dataset(seed: int, count: int):
    rng = random.Random(seed)
    data = []
    for _ in range(count):
        data.append(make_request(rng))
    return data


def verify(program, dataset):
    parse = getattr(program, "parse_http_request", None)
    if parse is None:
        raise RuntimeError("parse_http_request is required")

    for raw, ref in dataset:
        method, path, version, headers = parse(raw)
        if (method, path, version) != ref[:3]:
            raise ValueError("request line mismatch")
        if headers != ref[3]:
            raise ValueError("header mismatch")


def benchmark(program, dataset, rounds: int, batch_size: int):
    parse = getattr(program, "parse_http_request")
    latencies = []
    total_ops = 0
    total_time = 0.0

    raws = [raw for raw, _ in dataset]

    for _ in range(rounds):
        for i in range(0, len(raws), batch_size):
            batch = raws[i : i + batch_size]
            t0 = time.perf_counter()
            for raw in batch:
                parse(raw)
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
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--batch", type=int, default=100)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    program = load_program(args.program)
    dataset = generate_dataset(args.seed, args.count)

    if not args.skip_verify:
        verify(program, dataset)

    metrics = benchmark(program, dataset, rounds=args.rounds, batch_size=args.batch)

    if args.json:
        Path(args.json).write_text(json.dumps(metrics), encoding="utf-8")
    else:
        print(json.dumps(metrics))


if __name__ == "__main__":
    main()
