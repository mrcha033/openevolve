# LRU Cache (Trace-Driven)

## Objective
Optimize a cache eviction path on a realistic access trace. The profiler should reveal pointer-chasing and cache miss hotspots.

## Task Summary
- Implement a fixed-capacity LRU cache.
- access(key) returns hit/miss and updates recency.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## How To Run
```bash
AI_OPT_TRACK=baseline ../run_track.sh lru_cache
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ../run_track.sh lru_cache
```
