import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Sieve of Eratosthenes benchmark runner")
    parser.add_argument("--program", required=True, help="Path to .cpp file")
    parser.add_argument("--json", default="", help="Output JSON path")
    parser.add_argument("--limit", type=int, default=10000000)
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()

    tmp_dir = Path(tempfile.mkdtemp(prefix="sieve_bench_"))
    bin_path = tmp_dir / "bench_bin"

    # Compile
    cmd = ["g++", "-O3", "-std=c++17", "-DNDEBUG",
           args.program, "-o", str(bin_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Compile error: {result.stderr}")
        return

    # Run
    metrics_path = tmp_dir / "metrics.json"
    run_cmd = [str(bin_path), "--json", str(metrics_path),
               "--limit", str(args.limit), "--rounds", str(args.rounds)]
    result = subprocess.run(run_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Run error: {result.stderr or result.stdout}")
        return

    metrics = json.loads(metrics_path.read_text())
    if args.json:
        Path(args.json).write_text(json.dumps(metrics))
    else:
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
