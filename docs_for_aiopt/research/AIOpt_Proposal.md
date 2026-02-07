# Proposal: Enhancing OpenEvolve with Causal Profiling and Evolutionary Refinement

## 1. Thesis
Classical evolutionary algorithms in code generation often suffer from "blind" exploration. By integrating **Causal Profiling (BCOZ)** and **Blocked-Sample Analysis (bperf)** directly into the **Selection and Mutation** phases of OpenEvolve, we can transform it from a stochastic search into a bottleneck-aware optimization engine.

## 2. Technical Integration Plan

### A. Evaluator-Augmented Context (The "Delta" Feed)
- **Blocked Samples (bperf):** Modify `evaluator.py` to parse the `bperf` output and extract specific call stacks associated with `task-clock` or `off-cpu` events.
- **Causal Signal (BCOZ):** Integrate BCOZ speedup predictions as a primary metric. A candidate's score shouldn't just be its throughput, but its *responsiveness to optimization* in its current bottlenecked state.

### B. Evolutionary Mechanism Enhancements
- **Multi-Objective MAP-Elites:** Instead of just 8 binary flags for SysGPT methodologies, we should use **BCOZ-identified bottlenecks** as feature dimensions.
    - *Example:* Dimension 1: Lock Contention (LDB/BCOZ), Dimension 2: Context Switching, Dimension 3: Cache Misses.
    - *Goal:* Maintain a population that explores different ways to solve *specific* hardware/system bottlenecks.
- **In-Context Learning (ICL) for Mutation:**
    - Inject the `bperf` stack traces and BCOZ speedup curves directly into the `diff_user.txt` template.
    - **Prompt Engineering:** "The profiler shows 40% of time blocked in `std::mutex::lock` at `rocksdb_tuning:L142`. Suggest a task reordering or deferring strategy to minimize this contention."

### C. The RocksDB Experiment: "Semantic Bottlenecking"
- **Current Status:** You are using 8 binary methodologies as coordinates.
- **Proposed Change:** Shift to **Hardware-Metric Coordinates**.
    - Let the LLM see the `db_bench` statistics (L0 files, compaction pressure).
    - Map the cells in the grid to these pressures. This forces the model to find the best configuration for "High Write Pressure" vs "High Read Tail Latency."

## 3. Immediate Next Steps
1. **Tool Verification:** Can we run `bperf` or `bcoz` on the current RPi infrastructure, or should we prepare a containerized environment (Ubuntu 20.04) as suggested in the papers?
2. **Template Customization:** I am prepared to modify `openevolve/prompts/defaults/diff_user.txt` to explicitly include an `## Optimization Context` section for the LLM.
3. **Task Definition:** We should move from `rocksdb_tuning()` (which is just a dict) to a more complex C++ kernel where the LLM can apply **Task Reordering** at the source code level, not just the config level.

---
*Pierre's Note: This transition from "configuration tuning" to "architectural refinement" is where the true epsilon of systems intelligence lies.*
