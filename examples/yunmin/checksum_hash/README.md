# Checksumming / Hashing Pipeline

## Objective
Optimize a byte-wise checksum kernel where vectorization and memory bandwidth dominate.

## Task Summary
- Compute FNV-1a 32-bit hash for each input block.
- Correctness vs reference implementation.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## How To Run
```bash
AI_OPT_TRACK=baseline ../run_track.sh checksum_hash
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ../run_track.sh checksum_hash
```
