# Sparse Matrix-Vector Multiply (CSR, C++)

## Objective
Optimize CSR SpMV where performance is dominated by indirect memory accesses. Profiler feedback should surface cache misses and low IPC.

## Task Summary
- Multiply CSR matrix by dense vector.
- Correctness: max absolute error <= 1e-9 vs reference.

## Metrics
- `ops_per_sec`
- `p99_latency_us`
- `gflops`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh spmv
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh spmv
```
