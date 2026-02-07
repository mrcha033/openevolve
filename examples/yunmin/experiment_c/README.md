# Experiment C: Coroutinization (bperf Context Switch Reduction)

## Goal
Use bperf off-CPU analysis to find synchronization-heavy paths and introduce
coroutine-based async patterns to reduce context-switch overhead.

## Intended Target
- RocksDB source tree
- Primary files:
  - `db/compaction/compaction_job.cc`
  - `db/flush_job.cc`
  - `util/threadpool_imp.cc`

## How This Scaffolding Is Used
This experiment is designed for external server execution with bperf available.
The evaluator is **profiler-in-the-loop**:
1. Apply the mutation diff to the real RocksDB source tree.
2. Build and benchmark (`db_bench`).
3. Run bperf and fold off-CPU ratio into fitness.

## Required Environment Variables
- `AI_OPT_ROCKSDB_PATH`: path to RocksDB checkout
- `AI_OPT_BUILD_CMD`: build command (e.g., `cmake --build build -j`)
- `AI_OPT_BENCH_CMD`: benchmark command (e.g., `./build/db_bench --benchmarks=...`)

Optional:
- `AI_OPT_TARGET_FILE` or `AI_OPT_TARGET_FILES`
- `AI_OPT_BENCH_BIN` / `AI_OPT_BENCH_ARGS`: explicit binary + args for profilers
- `AI_OPT_METRICS_JSON`: parse metrics from a JSON file
- `AI_OPT_RUN_BPERF`: `1` to enable, `0` to disable (default: on)
- `AI_OPT_BPERF_DURATION`: seconds (default `30`)

## Expected Metrics
- `combined_score`: throughput + latency + bperf
- `off_cpu_ratio`: reduced ratio indicates fewer context switches
- Optional: thread pool queue depth, compaction duration

## 3-Track Protocol (Shared)
We run a **single experiment scaffold** with a `track` switch:
- **baseline:** local model, **no profiler feedback** (scalar reward only).
- **gpt5:** GPT-5, **no profiler feedback** (scalar reward only).
- **profiler:** local model + **BCOZ/bperf** feedback.

Set `track` in `config.yaml` or pass `AI_OPT_TRACK`.
If `track != profiler`, set `AI_OPT_RUN_BCOZ=0` and `AI_OPT_RUN_BPERF=0`.

## Notes
This experiment may require C++20 or a coroutine library (folly/cppcoro).
Pick a single coroutine strategy to keep refactors minimal and testable.
