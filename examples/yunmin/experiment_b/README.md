# Experiment B: Lock Contention Reduction

## 1. Scientific Objective
**Goal:** Reduce mutex contention in the critical Write Path (`DBImpl::mutex_`).
**Hypothesis:** High-concurrency workloads spend significant time blocked on locks. `bperf` (off-CPU profiling) can precisely identify the hottest critical sections. An LLM can optimize these by **splitting locks**, **reducing critical section scope**, or **using lock-free atomics**.

**Target File:** `db/db_impl/db_impl_write.cc` (Focus on `mutex_` usage)
**Profiling Signal:**
*   **Off-CPU Ratio:** `bperf` metric (Time spent sleeping/blocked).
*   **Causal Speedup:** `BCOZ` speedup on mutex acquisition lines.

## 2. Experimental Protocol (4-Track)

We compare **Vision** (Profiler) vs. **Intelligence** (Model Scale).

| Track | Model | Profiler Feedback | Goal |
| :--- | :--- | :--- | :--- |
| **A (Baseline)** | Local (e.g., Qwen/DeepSeek) | **None** (Blind) | Establish performance floor. |
| **B (Competitor)**| **GPT-5** (SOTA) | **None** (Blind) | Can pure intelligence solve systems problems? |
| **C (Method)** | Local (e.g., Qwen/DeepSeek) | **bperf + BCOZ** | Does causal vision beat blind intelligence? |
| **D (Ultimate)** | **GPT-5** (SOTA) | **bperf + BCOZ** | The theoretical upper bound. |

## 3. How to Run

Use the shared runner script `../run_track.sh` from the parent directory.

### Prerequisites
*   **Env:** `AI_OPT_ROCKSDB_PATH` must point to your RocksDB source.
*   **Profiler:** For Tracks C/D, `bperf` (eBPF) and `bcoz` must be installed.
*   **LLM:** `vllm` or `ollama` running locally, or `OPENAI_API_KEY` set.

### Commands

**Track A (Baseline):**
```bash
export AI_OPT_MODEL_BASELINE="local-model-name"
AI_OPT_TRACK=baseline ../run_track.sh experiment_b
```

**Track B (GPT-5):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5 ../run_track.sh experiment_b
```

**Track C (Profiler-Guided):**
```bash
# Must run on Linux with bperf (root/sudo often required for eBPF)
export AI_OPT_MODEL_PROFILER="local-model-name"
AI_OPT_TRACK=profiler ../run_track.sh experiment_b
```

**Track D (GPT-5 + Profiler):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5_profiler ../run_track.sh experiment_b
```

## 4. Evaluation Metrics
The evaluator (`evaluator.py`) calculates a **Combined Fitness Score**:
$$ Fitness = 0.3 \times Throughput + 0.2 \times Latency + 0.3 \times \text{OffCpuReduction} $$

*   **Off-CPU Reduction:** In Track C/D, we heavily reward mutations that lower the `off_cpu_ratio` reported by `bperf`.

## 5. Function-Slicing Design

### Motivation
RocksDB source files are thousands of lines long. Local models (Qwen, DeepSeek)
with limited context windows fail to process the full file, and smaller models
struggle to generate correct SEARCH/REPLACE diffs against such large inputs.

### Architecture
Instead of giving the LLM the full source file, we **slice** out the target
function (the EVOLVE-BLOCK region) and present only that to the LLM:

```
full_source_template.cpp (2959 lines, read-only)
        |
        +- lines 1-1652:     context (includes, helpers)  -- not shown to LLM
        +- lines 1653-1700:  EVOLVE-BLOCK (WriteToWAL)    -- initial_program.cpp
        +- lines 1701-2959:  context (other functions)     -- not shown to LLM
```

**Flow:**
1. `initial_program.cpp` contains ONLY the EVOLVE-BLOCK region (~47 lines)
2. OpenEvolve sends this slice to the LLM with diff-based evolution enabled
3. LLM generates SEARCH/REPLACE diffs against the short slice (high reliability)
4. Evaluator reads the evolved slice + `full_source_template.cpp`
5. `_reassemble_source()` patches the slice back into the template
6. Reassembled file is written to the RocksDB tree, compiled, and benchmarked

### Files
| File | Purpose |
|------|---------|
| `initial_program.cpp` | Function slice (~47 lines) -- what the LLM evolves |
| `full_source_template.cpp` | Full original source -- used by evaluator for reassembly |
| `initial_program.py` | (Legacy) Alternative MUTATION_DIFF approach |
| `evaluator.py` | Reassembles slice -> compiles -> benchmarks -> profiles |

### Benefits
- **Context efficiency:** ~1K tokens instead of ~37K
- **Diff reliability:** SEARCH/REPLACE on 47 lines vs 2959 lines
- **Local model compatibility:** Easily fits within smallest context windows
- **Preserved evolution quality:** Diff-based evolution enables small, targeted mutations
