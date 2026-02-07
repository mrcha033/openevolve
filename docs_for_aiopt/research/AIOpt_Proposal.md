# Current Design Summary: OpenEvolve + Causal Profiling

## 1. Thesis
OpenEvolve is bottleneck-aware by injecting **Causal Profiling (BCOZ)** and **Blocked-Sample Analysis (bperf)** context into each mutation prompt and by scoring mutations with causal-aware fitness.

## 2. Current Integration

### A. Evaluator-Augmented Context (The "Delta" Feed)
- **Blocked Samples (bperf):** Evaluators optionally run bperf and inject summarized context into `{artifacts}` via `openevolve.aiopt.bperf_parser.generate_mutation_context`.
- **Causal Signal (BCOZ):** Evaluators optionally run BCOZ and inject predicted speedup locations via `openevolve.aiopt.bcoz_parser.generate_mutation_context`.

### B. Evolutionary Mechanism
- **Multi-Objective MAP-Elites:** Feature dimensions are `ops_per_sec` and `p99_latency_us` (see `examples/yunmin/experiment_*/config.yaml`).
- **Prompting:** The built-in `diff_user` template in `openevolve/prompt/templates.py` is used; per-experiment guidance is in `examples/yunmin/experiment_*/config.yaml`.

### C. RocksDB Experiments
- **Current Status:** You are using 8 binary methodologies as coordinates.
- **Current Coordinates:** MAP-Elites uses performance metrics only; profiler metrics are not used as feature dimensions.

## 3. Immediate Next Steps
1. **Tool Verification:** Confirm bperf/BCOZ availability on target hardware (Linux perf/PMU access required).
2. **Prompt Clarity:** Keep per-experiment prompt blocks tight and aligned with evaluator defaults.
3. **Mutation Targets:** Continue focusing on C++ kernel mutations in the RocksDB source (`examples/yunmin`).

---
*Note: This document reflects the current implementation, not a future plan.*
