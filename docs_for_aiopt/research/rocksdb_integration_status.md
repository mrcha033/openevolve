# RocksDB Causal Feedback Integration Status

## Overview
The RocksDB integration in OpenEvolve uses evaluator-driven Causal Feedback loops. Evaluators run the benchmark, optionally run BCOZ and bperf, and inject profiler-derived context into prompts via the `{artifacts}` slot in the built-in prompt templates.

## Changes Made

### 1. Evaluator (`examples/yunmin/experiment_*/evaluator.py`)
- **Benchmark Parsing:** Extracts `ops/sec` and `p99` from `db_bench` output (or `AI_OPT_METRICS_JSON` if provided).
- **Profiler Hooks:** Optionally runs BCOZ and/or bperf, controlled via `AI_OPT_RUN_BCOZ` and `AI_OPT_RUN_BPERF` with experiment-specific defaults.
- **Artifacts:** Adds `profiler_bcoz` and/or `profiler_bperf` artifacts using `openevolve.aiopt.bcoz_parser.generate_mutation_context` and `openevolve.aiopt.bperf_parser.generate_mutation_context`.

### 2. Prompting (Built-in Templates)
- **Template Source:** `openevolve/prompt/templates.py` provides the `diff_user` template used in diff-based evolution.
- **Artifacts Injection:** The `{artifacts}` placeholder is filled with evaluator artifacts (e.g., profiler context).
- **Heuristics:** Any additional guidance is encoded in per-experiment prompt blocks inside `examples/yunmin/experiment_*/config.yaml`.

### 3. Configuration (`examples/yunmin/experiment_*/config.yaml`)
- **Feature Dimensions:** Current MAP-Elites coordinates use `ops_per_sec` and `p99_latency_us`. Profiler outputs are logged and can be used in prompts/fitness, but are not MAP-Elites dimensions.
- **Profiling Defaults:** Per-experiment defaults are set in each evaluator (`DEFAULT_RUN_BCOZ`/`DEFAULT_RUN_BPERF`) and can be overridden via env vars.

## Current Blockers (2026-02-04)
- **SSH Connectivity Failure:** The proxy jump host (`192.168.0.4`) is unreachable (100% packet loss). This prevents access to the CSLab server (`165.132.141.223`) for running the autonomous optimization loop.
- **Action Required:** Physical intervention or network troubleshooting on the Windows host side is required to restore the bridge.

## Next Steps
- If desired, add system-pressure parsing to evaluators and include those signals as new feature dimensions.
- Consider extending prompt templates with structured sections for profiler insights once requirements stabilize.
