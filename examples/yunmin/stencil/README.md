# 2D Stencil / Heat Equation (C++)

## Objective
Optimize a 5-point Jacobi stencil on a 1024x1024 grid.

## Why This Task
- **Looks cache-friendly but IS bandwidth-saturated**: Row-major traversal appears sequential, but two 8MB grids exceed L2 capacity, making each timestep memory-bound
- **Rich optimization space**: Spatial tiling (fit tiles in L2), temporal tiling (multiple timesteps per tile load), loop interchange, vectorization, cache-oblivious algorithms
- **Profiler adds value**: BCOZ identifies the inner loop; bperf quantifies memory stall fraction — temporal tiling is the key insight that profiler data can guide toward

## Task Summary
- 1024x1024 grid, Jacobi relaxation (Laplace equation)
- `out[i][j] = 0.25 * (in[i-1][j] + in[i+1][j] + in[i][j-1] + in[i][j+1])`
- Correctness verified via checksum against reference (10 steps, 1e-6 tolerance)
- Benchmark: 100 timesteps x 5 rounds

## Metrics
- `ops_per_sec` — timesteps per second
- `p99_latency_us` — p99 latency of one timestep
- `gflops` — effective GFLOP/s

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks (optional)

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh stencil
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh stencil
```

Standalone benchmark:
```bash
python bench.py --program initial_program.cpp
```
