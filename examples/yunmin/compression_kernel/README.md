# Compression / Decompression Kernel Slice (C++)

## Objective
Optimize a small block-compression kernel. Profiler feedback should surface branch and memory behavior.

## Task Summary
- RLE-like compression with a marker byte.
- Correctness: decompress(compress(x)) == x and output format must be decodable by reference.

## Metrics
- `ops_per_sec`
- `p99_latency_us`
- `mb_per_sec`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh compression_kernel
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh compression_kernel
```
