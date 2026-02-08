# N-Body Gravitational Simulation (C++)

## Objective
Optimize an O(N^2) pairwise gravitational force computation.

## Why This Task
- **Looks compute-bound but IS memory-bound**: AoS layout causes cache-line waste (56 bytes/body, only 24 used for position)
- **Rich optimization space**: AoS-to-SoA conversion, SIMD vectorization, spatial tiling, reciprocal sqrt approximation, loop unrolling
- **Profiler adds value**: BCOZ identifies the sqrt bottleneck; bperf reveals cache miss stalls invisible to the LLM

## Task Summary
- 1024 particles with mass, position, velocity
- Compute all-pairs gravitational forces with softening
- Correctness verified against reference implementation (1e-6 tolerance)

## Metrics
- `ops_per_sec` — force computations per second
- `p99_latency_us` — p99 latency of one force computation

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks (optional)

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh nbody
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh nbody
```

Standalone benchmark:
```bash
python bench.py --program initial_program.cpp
```
