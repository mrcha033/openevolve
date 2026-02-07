# Experiment B: Lock Contention Reduction (Profiler-in-the-Loop)

## Goal
Reduce `DBImpl::mutex_` contention using **BCOZ + bperf** feedback to guide
code-level refactoring. The evaluator integrates both profilers into fitness.

## Intended Target
- RocksDB source tree
- Primary file: `db/db_impl/db_impl_write.cc`

## Required Environment Variables
- `AI_OPT_ROCKSDB_PATH`: path to RocksDB checkout
- `AI_OPT_BUILD_CMD`: build command (e.g., `cmake --build build -j`)
- `AI_OPT_BENCH_CMD`: benchmark command (e.g., `./build/db_bench --benchmarks=...`)

Optional:
- `AI_OPT_TARGET_FILE` or `AI_OPT_TARGET_FILES`
- `AI_OPT_BENCH_BIN` / `AI_OPT_BENCH_ARGS`: explicit binary + args for profilers
- `AI_OPT_METRICS_JSON`: parse metrics from a JSON file
- `AI_OPT_RUN_BCOZ`: `1` to enable, `0` to disable (default: on)
- `AI_OPT_RUN_BPERF`: `1` to enable, `0` to disable (default: on)
- `AI_OPT_BCOZ_DURATION`: seconds (default `60`)
- `AI_OPT_BPERF_DURATION`: seconds (default `30`)

## Expected Metrics
- `combined_score`: throughput + latency + causal signals
- `bcoz_max_speedup`
- `bperf_offcpu_ratio`

## 3-Track Protocol (Shared)
We run a **single experiment scaffold** with a `track` switch:
- **baseline:** local model, **no profiler feedback** (scalar reward only).
- **gpt5:** GPT-5, **no profiler feedback** (scalar reward only).
- **profiler:** local model + **BCOZ/bperf** feedback.

### One-Command Runner (No per-track config edits)
Use the shared runner (auto-applies model + profiler toggles):
```bash
# Example (baseline)
AI_OPT_TRACK=baseline \
AI_OPT_MODEL_BASELINE="<local-model-id>" \
examples/yunmin/run_track.sh experiment_b

# Example (profiler)
AI_OPT_TRACK=profiler \
AI_OPT_MODEL_PROFILER="<local-model-id>" \
examples/yunmin/run_track.sh experiment_b
```

The runner sets:
- Model via `--primary-model`
- API base via `--api-base`
- `AI_OPT_RUN_BCOZ` / `AI_OPT_RUN_BPERF` automatically

## Notes
This scaffold assumes **real RocksDB** with profilers available.
If you want a local synthetic test, use `examples/yunmin/local_prototype/lock_hotspot`.
