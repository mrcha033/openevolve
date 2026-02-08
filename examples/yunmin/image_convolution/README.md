# Image Convolution (Gaussian Blur, C++)

## Objective
Optimize a 5x5 Gaussian blur. Profiler feedback should show cache misses in the vertical pass and memory bandwidth limits.

## Task Summary
- Apply 5x5 convolution over a 4096×4096 image.
- Correctness: max absolute error <= 1e-4 vs reference.

## Metrics
- `ops_per_sec`
- `p99_latency_us`
- `mpix_per_sec`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh image_convolution
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh image_convolution
```
