# AIOpt Project: Critical Review and Experiment Design (2026-02-04)

## 1. Critical Review of Current Direction
My previous focus on "running the loop" was a tactical error. While automation is a secondary goal, the primary academic objective of this internship is the **design of bottleneck-aware evolutionary experiments**. 

*   **Failure in "Blind" Evolution:** Simply tuning `rocksdb_tuning()` dictionaries is configuration tuning, not kernel mutation. We need to move the mutation target to the C++ code itself (e.g., `db_bench.cc` or core RocksDB logic) where `bperf` and `BCOZ` provide granular signals.
*   **Contextual Mismatch:** The model was attempting to optimize for "throughput" generally. It must optimize for the **causal speedup** predicted by BCOZ at specific call sites.

## 2. Refined Objective: Bottleneck-Aware Experiment Design
The goal is to transform `OpenEvolve` into a "Scientific Method" agent that:
1.  Analyzes `bperf` (Blocked Samples) to identify *why* threads are off-CPU.
2.  Analyzes `BCOZ` (Causal Profiling) to identify *where* optimization will yield the most global speedup.
3.  Synthesizes a **hypothesis-driven mutation** (e.g., "If I reorder this write-ahead-log (WAL) flushing task, lock contention at Site X will decrease by 15%").

## 3. Planned Experiments

### Experiment A: The L0-Compaction Bottleneck (Hardware-Metric Driven)
*   **Hypothesis:** MAP-Elites can find distinct optimization strategies for different "pressure zones" (High L0 File Count vs High Write Stall %). (Not implemented in current configs.)
*   **Profile Signal:** `db_bench` telemetry + BCOZ signal on compaction threads.
*   **Action:** Vary the methodology prompts based on the *current* pressure state of the database.

### Experiment B: Lock Contention Reduction (Causal Signal Driven)
*   **Hypothesis:** Injecting BCOZ call-stack speedup predictions into the LLM's mutation prompt will lead to more effective code-level reordering than standard throughput feedback.
*   **Profile Signal:** BCOZ speedup curves showing >10% gains on specific mutex lock-paths.
*   **Action:** Prompt the model to specifically refactor the identified C++ lock paths to reduce critical section duration.

### Experiment C: Compaction Latency Hiding (Pipelining)
*   **Hypothesis:** Local software pipelining in `CompactionJob` can hide SST block I/O latency without viral refactors.
*   **Profile Signal:** High `off-cpu` time in `bperf` during compaction block reads.
*   **Action:** Evaluate if evolutionary mutations can prefetch the next block while processing the current block, staying within `compaction_job.cc`.

## 4. Operational Alignment
- **Canonical Repository:** `/home/rpi/Repositories/openevolve` (linked to `~/workspace/openevolve`).
- **Mode of Operation:** I will prepare and validate the **experiment logic** and **LLM prompt templates** locally. Once designed, I will provide you with the command/package to execute on the `cslab-server`.
