# Compression / Decompression Kernel Slice

## Objective
Optimize a small block-compression kernel. The profiler should surface branch and memory behavior that is not obvious from the code alone.

## Task Summary
- RLE-like compression with a marker byte.
- Correctness: `decompress(compress(x)) == x`.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## How To Run
```bash
AI_OPT_TRACK=baseline ../run_track.sh compression_kernel
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ../run_track.sh compression_kernel
```
