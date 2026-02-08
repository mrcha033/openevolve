# LRU Cache (Trace-Driven, C++)

## Objective
Optimize a cache eviction path on a realistic access trace. Profiler feedback should reveal pointer chasing and cache miss hotspots.

## Task Summary
- Implement a fixed-capacity LRU cache.
- access(key) returns hit/miss and updates recency.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh lru_cache
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh lru_cache
```
