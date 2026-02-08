# AIOpt: Critical Review and Post-Mortem

**Version:** 2.0 (post-experiment analysis)
**Date:** 2026-02-08

## 1. What We Tried

### Original design (2026-02-04)

Three RocksDB kernel mutation experiments using OpenEvolve with causal profiling:

| Experiment | Target | Profiler | Goal |
|-----------|--------|----------|------|
| A | `db_impl_write.cc` | BCOZ | Reduce WAL/L0 pressure |
| B | `db_impl_write.cc` | BCOZ + bperf | Reduce lock contention |
| C | `compaction_job.cc` | bperf | Compaction latency hiding |

Model: Llama 3.3 70B AWQ (local, via vLLM). 50 iterations per experiment. Track A (baseline, no profiler) ran first.

### Architecture

```
LLM mutates Python file → Python contains MUTATION_DIFF string → evaluator reads string →
applies as SEARCH/REPLACE diff to C++ file → builds RocksDB → benchmarks → scores
```

## 2. What Happened (Track A Results)

**50 iterations, zero valid mutations.**

The best program (id: `52aadada`, score: 1.3534) has `MUTATION_DIFF = r""` — an empty diff. Every program in the archive is the initial program with no modifications.

### Score distribution (all benchmark noise)

| Metric | Min | Max | Note |
|--------|-----|-----|------|
| ops_per_sec | 759,061 | 877,311 | ~14% variance, run-to-run noise |
| p99_latency_us | 9.57 | 14.19 | mostly 9.5–9.7, two outliers |
| combined_score | 1.27 | 1.35 | entirely within noise band |
| bcoz_max_speedup | 15.0 | 15.0 | always baseline default (profilers disabled in Track A) |

The LLM (Llama 70B) generated pseudo-C++ SEARCH/REPLACE blocks like:
```
<<<<<<< SEARCH
Status DBImpl::Write(const WriteOptions& options, WriteBatch* batch) {
    // ...
    if (options.sync) {
        // Synchronous WAL write
```

These are fictional code snippets that don't match anything in the actual `db_impl_write.cc`. `apply_diff()` found no match, the diff didn't apply, and each iteration was just re-benchmarking unmodified RocksDB.

## 3. Root Cause Analysis

### Failure 1: Triple indirection made valid mutations impossible

The LLM's task was:
1. Write a SEARCH/REPLACE diff targeting the Python program file
2. That diff should modify the `MUTATION_DIFF` string variable
3. That string is itself a SEARCH/REPLACE diff targeting C++ code
4. The SEARCH block in that inner diff must exactly match real code in `db_impl_write.cc`

The LLM never saw `db_impl_write.cc`. It generated plausible-but-fictional C++ snippets. Even if the LLM understood the indirection, it couldn't write matching SEARCH blocks for code it hadn't read.

**Lesson:** The LLM must evolve the actual code it's optimizing, or at minimum see the target code in its prompt context.

### Failure 2: Circularity in experiment design

All three experiments defined the optimization task in terms of what the profiler measures:
- Experiment A: "Reduce WAL pressure" → BCOZ measures WAL bottleneck → showing BCOZ helps is tautological
- Experiment B: "Reduce mutex contention" → bperf measures mutex blocking → same
- Experiment C: "Hide compaction I/O stalls" → bperf measures off-CPU time → same

A reviewer would say: "Of course profiler feedback helps when the task IS the bottleneck the profiler identifies." The result is pre-determined by the experiment design.

**Lesson:** The task description should be generic ("make this program faster"), and the profiler should reveal non-obvious bottlenecks that the LLM discovers, not just confirms.

### Failure 3: Evaluation cycle too slow

Each iteration took ~100 seconds (benchmark) + ~10 seconds (LLM). With 50 iterations, a single run took ~1.5 hours. This is too slow for iterating on the experimental design itself.

**Lesson:** Fast evaluation (seconds, not minutes) enables both more iterations and faster research iteration.

## 4. What We Salvaged

### Positive outcomes

1. **Infrastructure works.** The evaluator → artifact → prompt pipeline is verified end-to-end. `EvaluationResult` with profiler artifacts, `generate_mutation_context()` for both parsers, `run_track.sh` with 4-track + seed support — all functional.

2. **Baseline noise quantified.** Track A gave us 42 data points of unmodified RocksDB benchmark noise: ~±7% ops/sec variance. This establishes the significance threshold for future experiments.

3. **checkpoint_100 proves the framework.** The earlier GPT-Mini C++ experiment (separate from RocksDB) reached 288 tok/s with genuine optimizations: kernel fusion, pointer walking, selective initialization. OpenEvolve works when the task is well-formulated.

4. **Evaluator improvements.** Robust `_parse_metrics()` (ops_candidates with max, explicit P99 parsing), `noop_diff` support for baseline measurement, default feature dimension handling.

### What to preserve

| Component | Keep? | Reason |
|-----------|-------|--------|
| `openevolve/aiopt/bperf_parser.py` | Yes | Parser + `generate_mutation_context()` ready |
| `openevolve/aiopt/bcoz_parser.py` | Yes | Parser + `generate_mutation_context()` ready |
| `openevolve/aiopt/fitness.py` | Yes | Causal fitness function ready |
| `run_track.sh` | Yes | 4-track + seed support ready |
| `capture_baseline.sh` | Yes | Automated baseline capture ready |
| RocksDB evaluators | Archive | Useful as reference for evaluator patterns |
| RocksDB experiment data | Archive | Baseline noise data, lessons learned |

## 5. What Changes

See `AIOpt_Proposal.md` for the full redesigned approach. Summary:

| Before | After |
|--------|-------|
| Evolve Python wrapper containing C++ diff | Evolve the actual program directly |
| RocksDB-specific task (10 min build) | Self-contained program (seconds to evaluate) |
| Task names the bottleneck | Task says "make it faster" |
| 3 experiments, all RocksDB | Task chosen for non-obvious bottleneck |
| Single run, no statistical power | 5 seeds × 4 tracks = 20 runs |

## 6. Key Takeaways for Future Work

1. **Validate the simplest possible version first.** Before running 50-iteration experiments, do a 5-iteration sanity check: does the LLM produce at least one valid, performance-changing mutation?

2. **The LLM must see what it's optimizing.** No indirection layers. The evolved program is the evaluated program.

3. **Don't design the experiment to confirm your hypothesis.** If the task is "fix the thing the profiler measures," the result is predetermined. Design for genuine discovery.

4. **Fast iteration > long runs.** A 2-second evaluation cycle with 100 iterations is more useful than a 100-second cycle with 50 iterations, both for the evolution and for research iteration speed.
