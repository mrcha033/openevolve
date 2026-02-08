# RocksDB Causal Feedback Integration Status

**Status:** ARCHIVED — RocksDB experiments suspended (2026-02-08)

The RocksDB integration is technically functional but the experiment design was abandoned. See `AIOpt_Critical_Review.md` for the post-mortem.

## What was built (still usable)

- Evaluator pattern: benchmark parsing, profiler hooks, artifact generation
- `EvaluationResult` with profiler artifacts via `generate_mutation_context()`
- Track control via `AI_OPT_RUN_BCOZ` / `AI_OPT_RUN_BPERF` env vars
- MAP-Elites with `ops_per_sec` and `p99_latency_us` feature dimensions
- 4-track runner (`run_track.sh`) with seed support
- Automated baseline capture (`capture_baseline.sh`)

## Why it was shelved

1. Triple-indirection (Python → string → C++ diff) prevented valid mutations
2. Task circularity (task defined by what profiler measures)
3. Slow evaluation cycle (~100s per iteration)

## If revisiting RocksDB later

The infrastructure is ready. The key fix would be:
- Evolve the C++ file directly (put EVOLVE-BLOCK markers in the actual `.cc` file)
- Or evolve RocksDB configuration parameters instead of source code
- Use a generic task description ("make this benchmark faster") instead of naming the bottleneck
