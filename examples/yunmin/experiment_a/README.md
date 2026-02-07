# Experiment A: WAL/L0 Pressure (BCOZ-Guided)

## Goal
Use BCOZ causal profiling to target the Write-Ahead Log (WAL) and L0-compaction
pressure bottleneck. The hypothesis is that mutations addressing the causal
hotspot (e.g., WAL sync path) can improve throughput and reduce L0 stall pressure.

## Intended Target
- RocksDB source tree
- Primary file: `db/db_impl/db_impl_write.cc` (WAL sync)
- Secondary signals: db_bench telemetry (L0 file count, stall %)

## How This Scaffolding Is Used
This experiment is designed for external server execution with BCOZ available.
The evaluator is **profiler-in-the-loop**:
1. Apply the mutation diff to the real RocksDB source tree.
2. Build and benchmark (`db_bench`).
3. Run BCOZ and fold causal speedup into fitness.

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
examples/yunmin/run_track.sh experiment_a

# Example (profiler)
AI_OPT_TRACK=profiler \
AI_OPT_MODEL_PROFILER="<local-model-id>" \
examples/yunmin/run_track.sh experiment_a
```

The runner sets:
- Model via `--primary-model`
- API base via `--api-base`
- `AI_OPT_RUN_BCOZ` / `AI_OPT_RUN_BPERF` automatically

## Required Environment Variables
- `AI_OPT_ROCKSDB_PATH`: path to RocksDB checkout
- `AI_OPT_BUILD_CMD`: build command (e.g., `cmake --build build -j`)
- `AI_OPT_BENCH_CMD`: benchmark command (e.g., `./build/db_bench --benchmarks=...`)

Optional:
- `AI_OPT_TARGET_FILE`: override target file
- `AI_OPT_TARGET_FILES`: comma list of target files to try
- `AI_OPT_BENCH_BIN` / `AI_OPT_BENCH_ARGS`: explicit binary + args for profilers
- `AI_OPT_METRICS_JSON`: parse metrics from a JSON file
- `AI_OPT_RUN_BCOZ`: `1` to enable, `0` to disable (default: on)
- `AI_OPT_BCOZ_DURATION`: seconds (default `60`)
- `AI_OPT_BCOZ_PROGRESS_POINTS`: comma list of progress points

## Expected Metrics
- `combined_score`: weighted throughput + latency (+ BCOZ if enabled)
- `bcoz_max_speedup`: reduced max speedup indicates bottleneck improvement

## Next Step If You Want Code Here
If you want, I can add a server-oriented evaluator that:
- Applies diffs to a RocksDB checkout
- Builds db_bench
- Runs BCOZ and parses the `.coz` output
  
This is not included locally to avoid assumptions about your server layout.
