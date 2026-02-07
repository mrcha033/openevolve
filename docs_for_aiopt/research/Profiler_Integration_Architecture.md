# AIOpt: Profiler-in-the-Loop Architecture (Current Implementation)

## Overview
This document reflects the evaluator-driven integration used by `examples/yunmin/experiment_*/evaluator.py`.

```
┌──────────────────────────────────────────────────────────────────┐
│                     OPENEVOLVE LOOP                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   LLM       │    │   Build     │    │   Benchmark         │  │
│  │  Mutation   │───▶│   (cmake)   │───▶│   (db_bench)        │  │
│  │  Generator  │    │             │    │                     │  │
│  └─────────────┘    └─────────────┘    └──────────┬──────────┘  │
│        ▲                                          │              │
│        │                                          ▼              │
│        │                               ┌─────────────────────┐  │
│        │                               │   PROFILER          │  │
│        │                               │   ┌───────────────┐ │  │
│        │                               │   │ bperf         │ │  │
│        │                               │   │ (off-cpu)     │ │  │
│        │                               │   └───────────────┘ │  │
│        │                               │   ┌───────────────┐ │  │
│        │                               │   │ BCOZ          │ │  │
│        │                               │   │ (causal)      │ │  │
│        │                               │   └───────────────┘ │  │
│        │                               └──────────┬──────────┘  │
│        │                                          │              │
│        │         ┌────────────────────────────────┘              │
│        │         ▼                                               │
│  ┌─────────────────────────────────────┐                        │
│  │         FITNESS FUNCTION            │                        │
│  │  ┌────────────────────────────────┐ │                        │
│  │  │ causal_fitness(                │ │                        │
│  │  │   throughput,                  │ │                        │
│  │  │   bcoz_speedup_max,            │ │                        │
│  │  │   bperf_offcpu_ratio,          │ │                        │
│  │  │   compile_success,             │ │                        │
│  │  │   test_pass                    │ │                        │
│  │  │ )                              │ │                        │
│  │  └────────────────────────────────┘ │                        │
│  └─────────────────────────────────────┘                        │
│        │                                                         │
│        ▼                                                         │
│  ┌─────────────────────────────────────┐                        │
│  │         SELECTION / ELITES          │                        │
│  │         (MAP-Elites or GA)          │                        │
│  └─────────────────────────────────────┘                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Profiler Output Parsers

#### bperf Parser
```python
# bperf_parser.py
import subprocess
import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class BperfResult:
    total_samples: int
    off_cpu_samples: int
    off_cpu_ratio: float
    top_blockers: list[dict]  # [{func, samples, pct}, ...]

def run_bperf(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 30,
    output_dir: Path | None = None
) -> BperfResult:
    """Run bperf and parse stdio report output."""
    args = args or []
    output_dir = output_dir or Path("/tmp")
    data_file = output_dir / "bperf.data"
    report_file = output_dir / "bperf_report.txt"
    cmd = [
        "bperf", "record", "-g", "-o", str(data_file),
        "--", binary_path
    ]
    subprocess.run(cmd + args, check=True, capture_output=True)
    
    # Parse bperf report
    report = subprocess.run(
        ["bperf", "report", "-i", str(data_file), "--stdio"],
        capture_output=True, text=True
    )
    report_file.write_text(report.stdout)
    content = report.stdout

    total_match = re.search(r"Total samples:\s*(\d+)", content)
    offcpu_match = re.search(r"Off-CPU samples:\s*(\d+)", content)
    total = int(total_match.group(1)) if total_match else 0
    offcpu = int(offcpu_match.group(1)) if offcpu_match else 0
    
    return BperfResult(
        total_samples=total,
        off_cpu_samples=offcpu,
        off_cpu_ratio=offcpu / total if total > 0 else 0,
        top_blockers=[]  # populated by parse_bperf_report in implementation
    )
```

#### BCOZ Parser
```python
# bcoz_parser.py
import subprocess
import re
from dataclasses import dataclass

@dataclass
class BCOZResult:
    speedup_points: list[dict]  # [{line, file, speedup_pct}, ...]
    max_speedup: float
    max_speedup_location: str

def run_bcoz(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 60
) -> BCOZResult:
    """Run BCOZ causal profiling and parse output (args provided by evaluator)."""
    args = args or []
    cmd = [
        "bcoz", "run", "-o", "/tmp/bcoz_profile.coz",
        "---", binary_path
    ]
    subprocess.run(cmd + args, check=True, capture_output=True)
    
    # Parse coz profile output
    speedup_points = []
    with open("/tmp/bcoz_profile.coz", "r") as f:
        for line in f:
            # Format: "experiment\tselected=<file>:<line>\tspeedup=<decimal>\tduration=<samples>"
            match = re.search(r"selected=([^:\s]+):(\d+)\s+speedup=([\d.]+)", line)
            if match:
                speedup_points.append({
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "speedup_pct": float(match.group(3)) * 100
                })
    
    speedup_points.sort(key=lambda x: x["speedup_pct"], reverse=True)
    max_point = speedup_points[0] if speedup_points else {"speedup_pct": 0, "file": "", "line": 0}
    
    return BCOZResult(
        speedup_points=speedup_points[:20],
        max_speedup=max_point["speedup_pct"],
        max_speedup_location=f"{max_point['file']}:{max_point['line']}"
    )
```

---

### 2. Causal Fitness Function

```python
# fitness.py
from dataclasses import dataclass
from bperf_parser import BperfResult
from bcoz_parser import BCOZResult

@dataclass
class MutationResult:
    compiled: bool
    tests_passed: bool
    throughput_ops_sec: float
    p99_latency_us: float
    bperf: BperfResult | None
    bcoz: BCOZResult | None

# Baseline values (set from initial unmodified run)
BASELINE_THROUGHPUT = 100000  # ops/sec
BASELINE_P99 = 500  # microseconds
BASELINE_OFFCPU = 0.25  # 25%

def causal_fitness(result: MutationResult) -> float:
    """
    Compute fitness score emphasizing causal speedup potential.
    
    Weights:
    - 30% throughput improvement
    - 20% latency improvement
    - 30% BCOZ causal speedup (most important for bottleneck-aware optimization)
    - 20% off-CPU reduction (bperf)
    
    Returns 0.0 if mutation fails to compile or pass tests.
    """
    if not result.compiled or not result.tests_passed:
        return 0.0
    
    # Throughput score (higher is better)
    throughput_score = result.throughput_ops_sec / BASELINE_THROUGHPUT
    
    # Latency score (lower is better, so invert)
    latency_score = BASELINE_P99 / max(result.p99_latency_us, 1)
    
    # Drop weights for absent profilers and redistribute
    bcoz_weight = 0.30 if result.bcoz else 0.0
    bperf_weight = 0.20 if result.bperf else 0.0
    total_weight = 0.30 + 0.20 + bcoz_weight + bperf_weight
    if total_weight == 0:
        return 0.0
    throughput_weight = 0.30 / total_weight
    latency_weight = 0.20 / total_weight
    bcoz_weight /= total_weight
    bperf_weight /= total_weight

    # BCOZ causal score (max speedup percentage)
    bcoz_score = 0.0
    if result.bcoz and result.bcoz.max_speedup > 0:
        reduction = 15.0 - result.bcoz.max_speedup
        bcoz_score = 1.0 + (reduction / 15.0)
        bcoz_score = max(bcoz_score, 0.1)
    
    # Off-CPU score (lower is better)
    offcpu_score = 0.0
    if result.bperf:
        offcpu_score = BASELINE_OFFCPU / max(result.bperf.off_cpu_ratio, 0.01)
        offcpu_score = min(offcpu_score, 5.0)
    
    # Weighted combination
    fitness = (
        throughput_weight * throughput_score +
        latency_weight * latency_score +
        bcoz_weight * bcoz_score +
        bperf_weight * offcpu_score
    )
    
    return round(fitness, 4)
```

---

### 3. OpenEvolve Integration Hook (Illustrative)

```python
# openevolve_hook.py
"""
This mirrors the evaluator logic used by the experiments; the actual code lives in `examples/yunmin/experiment_*/evaluator.py`.
"""
import subprocess
import tempfile
import shutil
from pathlib import Path

from fitness import causal_fitness, MutationResult
from bperf_parser import run_bperf, BperfResult
from bcoz_parser import run_bcoz, BCOZResult

ROCKSDB_SRC = Path("/path/to/rocksdb")
BUILD_DIR = ROCKSDB_SRC / "build"

def evaluate_mutation(mutation_diff: str, run_profilers: bool = True) -> MutationResult:
    """
    Apply mutation, build, benchmark, optionally profile.
    
    Args:
        mutation_diff: Unified diff to apply to RocksDB source
        run_profilers: If False, skip bperf/BCOZ (for fast iteration)
    
    Returns:
        MutationResult with all metrics
    """
    # 1. Apply mutation
    with tempfile.NamedTemporaryFile(mode='w', suffix='.patch') as patch_file:
        patch_file.write(mutation_diff)
        patch_file.flush()
        
        apply_result = subprocess.run(
            ["git", "apply", "--check", patch_file.name],
            cwd=ROCKSDB_SRC, capture_output=True
        )
        if apply_result.returncode != 0:
            return MutationResult(compiled=False, tests_passed=False,
                                  throughput_ops_sec=0, p99_latency_us=0,
                                  bperf=None, bcoz=None)
        
        subprocess.run(["git", "apply", patch_file.name], cwd=ROCKSDB_SRC, check=True)
    
    try:
        # 2. Build
        build_result = subprocess.run(
            ["make", "-j4", "db_bench"],
            cwd=BUILD_DIR, capture_output=True, timeout=300
        )
        compiled = build_result.returncode == 0
        
        if not compiled:
            return MutationResult(compiled=False, tests_passed=False,
                                  throughput_ops_sec=0, p99_latency_us=0,
                                  bperf=None, bcoz=None)
        
        # 3. Run quick sanity test
        test_result = subprocess.run(
            [str(BUILD_DIR / "db_bench"), "--benchmarks=fillseq", "--num=1000"],
            capture_output=True, timeout=60
        )
        tests_passed = test_result.returncode == 0
        
        if not tests_passed:
            return MutationResult(compiled=True, tests_passed=False,
                                  throughput_ops_sec=0, p99_latency_us=0,
                                  bperf=None, bcoz=None)
        
        # 4. Full benchmark
        bench_output = subprocess.run(
            [str(BUILD_DIR / "db_bench"), "--benchmarks=fillrandom,readrandom",
             "--num=100000", "--threads=4"],
            capture_output=True, text=True, timeout=300
        )
        throughput, p99 = parse_db_bench_output(bench_output.stdout)
        bench_args = ["--benchmarks=fillrandom,readrandom", "--num=100000", "--threads=4"]
        
        # 5. Profiling (optional, expensive)
        bperf_result = None
        bcoz_result = None
        if run_profilers:
            try:
                bperf_result = run_bperf(
                    str(BUILD_DIR / "db_bench"),
                    args=bench_args,
                    duration_sec=30
                )
            except Exception:
                pass
            try:
                bcoz_result = run_bcoz(
                    str(BUILD_DIR / "db_bench"),
                    args=bench_args,
                    duration_sec=60
                )
            except Exception:
                pass
        
        return MutationResult(
            compiled=True,
            tests_passed=True,
            throughput_ops_sec=throughput,
            p99_latency_us=p99,
            bperf=bperf_result,
            bcoz=bcoz_result
        )
    
    finally:
        # Revert mutation
        subprocess.run(["git", "checkout", "."], cwd=ROCKSDB_SRC)


def parse_db_bench_output(output: str) -> tuple[float, float]:
    """Parse db_bench output for throughput and latency."""
    import re
    
    throughput = 0.0
    p99 = 0.0
    
    # Example: "fillrandom : 123456.789 ops/sec"
    throughput_match = re.search(r"fillrandom\s*:\s*([\d.]+)\s*ops/sec", output)
    if throughput_match:
        throughput = float(throughput_match.group(1))
    
    # Example: "Percentiles: P50: 1.23 P99: 4.56"
    p99_match = re.search(r"P99:\s*([\d.]+)", output)
    if p99_match:
        p99 = float(p99_match.group(1))
    
    return throughput, p99
```

---

## Execution Modes

### Mode A: Full Profiling (Server)
Run on cslab-server with bperf/BCOZ enabled. Each evaluation takes ~2-5 minutes.
```bash
python openevolve_run.py --mode=full --iterations=50
```

### Mode B: Fast Iteration (Local)
Run on RPi/Mac without profilers. Fitness based only on throughput/latency.
```bash
python openevolve_run.py --mode=fast --iterations=200
```

### Mode C: Hybrid
Run fast iterations locally, periodically sync best candidates to server for full profiling.

---

## Files Created
- `bperf_parser.py` — Parse bperf off-CPU data
- `bcoz_parser.py` — Parse BCOZ causal speedup data
- `fitness.py` — Causal-aware fitness function
- `openevolve_hook.py` — Integration with OpenEvolve evaluate()

## Next Steps
1. [ ] Implement parsers with actual bperf/BCOZ output format validation
2. [ ] Test fitness function with synthetic data
3. [ ] Integrate with OpenEvolve's `run.py` evaluate callback
4. [ ] Run Mode B locally to validate pipeline
