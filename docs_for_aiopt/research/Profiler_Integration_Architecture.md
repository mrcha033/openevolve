# AIOpt: Profiler-in-the-Loop Architecture

## Overview
This document specifies the integration of BCOZ/bperf profiling into OpenEvolve's evolutionary loop as **automated fitness feedback**, not static prompts.

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
import json
from dataclasses import dataclass

@dataclass
class BperfResult:
    total_samples: int
    off_cpu_samples: int
    off_cpu_ratio: float
    top_blockers: list[dict]  # [{func, samples, pct}, ...]

def run_bperf(binary_path: str, duration_sec: int = 30) -> BperfResult:
    """Run bperf and parse output."""
    cmd = [
        "bperf", "record", "-g", "-o", "/tmp/bperf.data",
        "--", binary_path, "--benchmarks=fillrandom", f"--duration={duration_sec}"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Parse bperf report
    report = subprocess.run(
        ["bperf", "report", "-i", "/tmp/bperf.data", "--json"],
        capture_output=True, text=True
    )
    data = json.loads(report.stdout)
    
    total = data.get("total_samples", 0)
    offcpu = data.get("off_cpu_samples", 0)
    
    return BperfResult(
        total_samples=total,
        off_cpu_samples=offcpu,
        off_cpu_ratio=offcpu / total if total > 0 else 0,
        top_blockers=data.get("top_off_cpu_stacks", [])[:10]
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

def run_bcoz(binary_path: str, duration_sec: int = 60) -> BCOZResult:
    """Run BCOZ causal profiling and parse output."""
    cmd = [
        "coz", "run", "-o", "/tmp/bcoz_profile.coz",
        "---", binary_path, "--benchmarks=fillrandom", f"--duration={duration_sec}"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Parse coz profile output
    speedup_points = []
    with open("/tmp/bcoz_profile.coz", "r") as f:
        for line in f:
            # Format: "speedup\t<file>:<line>\t<percentage>"
            match = re.match(r"speedup\t(.+):(\d+)\t([\d.]+)", line)
            if match:
                speedup_points.append({
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "speedup_pct": float(match.group(3))
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
    
    # BCOZ causal score (max speedup percentage)
    bcoz_score = 1.0
    if result.bcoz and result.bcoz.max_speedup > 0:
        # Reward mutations that reduce the max speedup potential
        # (meaning they've already captured that optimization)
        bcoz_score = 1.0 + (0.01 * (100 - result.bcoz.max_speedup))
    
    # Off-CPU score (lower is better)
    offcpu_score = 1.0
    if result.bperf:
        offcpu_score = BASELINE_OFFCPU / max(result.bperf.off_cpu_ratio, 0.01)
    
    # Weighted combination
    fitness = (
        0.30 * throughput_score +
        0.20 * latency_score +
        0.30 * bcoz_score +
        0.20 * offcpu_score
    )
    
    return round(fitness, 4)
```

---

### 3. OpenEvolve Integration Hook

```python
# openevolve_hook.py
"""
Integration point for OpenEvolve's evaluate() callback.
This replaces static throughput-only evaluation with causal profiling.
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
        
        # 5. Profiling (optional, expensive)
        bperf_result = None
        bcoz_result = None
        if run_profilers:
            try:
                bperf_result = run_bperf(str(BUILD_DIR / "db_bench"), duration_sec=30)
            except Exception:
                pass
            try:
                bcoz_result = run_bcoz(str(BUILD_DIR / "db_bench"), duration_sec=60)
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
