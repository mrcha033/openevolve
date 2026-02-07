# RocksDB Causal Feedback Integration Status

## Overview
The RocksDB integration in OpenEvolve has been upgraded to support "Causal Feedback" loops. The evolutionary engine is now bottleneck-aware, using telemetry from BCOZ (causal profiling) and bperf (blocked samples) to guide mutations.

## Changes Made

### 1. Evaluator (`evaluator.py`)
- **System Pressure Extraction:** Added regex patterns to parse `db_bench` output for RocksDB-specific pressure signals:
    - `write_stall_percent`: Percentage of time writes were stalled.
    - `avg_l0_files`: Number of files in Level 0 (indicates compaction pressure).
- **Bottleneck Summary Enhancement:** The `bottleneck_summary` artifact now explicitly separates "System Pressure" (RocksDB internal stats) and "Profiler Insights" (BCOZ/bperf).
- **Robust Telemetry:** Improved parsing of `bperf script` and `profile.coz` files to ensure high-impact call stacks and speedup predictions are captured reliably.

### 2. Prompting (`diff_user.txt`)
- **Targeted Optimization:** Added an `## Artifacts & Bottleneck Analysis` section at the top of the user prompt.
- **Explicit Instructions:** Provided the LLM with clear heuristics:
    - Focus on locking/concurrency if `off-cpu` or `mutex` appears in bperf.
    - Target specific lines identified by BCOZ speedup predictions.
    - Tune compaction/write buffers if Write Stall or L0 file counts are high.

### 3. Configuration (`config.yaml`)
- **Hardware-Metric Coordinates:** Added `avg_l0_files` and `write_stall_percent` to `feature_dimensions`. This allows MAP-Elites to maintain a diverse population across different system pressure states, not just across theoretical methodologies.
- **Enabled Profiling:** Ensured `ROCKSDB_BLOCKED_SAMPLES` is active and the system is primed for profile-guided evolution.

## Current Blockers (2026-02-04)
- **SSH Connectivity Failure:** The proxy jump host (`192.168.0.4`) is unreachable (100% packet loss). This prevents access to the CSLab server (`165.132.141.223`) for running the autonomous optimization loop.
- **Action Required:** Physical intervention or network troubleshooting on the Windows host side is required to restore the bridge.

## Next Steps
- Verify the impact of hardware-metric coordinates on population diversity.
- Test with a C++ kernel if moving beyond configuration tuning (as per Pierre's note in the proposal).
