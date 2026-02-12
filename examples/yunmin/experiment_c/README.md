# Experiment C: Compaction Latency Hiding (Pipelining)

## 1. Scientific Objective
**Goal:** Mask I/O latency in the Compaction Job via local software pipelining.
**Hypothesis:** Compaction jobs spend significant time blocked on I/O (reading SST blocks). Instead of a viral architectural rewrite (Coroutines), we can implement **local software pipelining** (prefetching the next block while processing the current one) to hide this latency.

**Target File:** `db/compaction/compaction_job.cc` (Internal logic only).
**Constraint:** **NO** changes to function signatures or `ThreadPool` (Viral refactoring is forbidden).

**Profiling Signal:**
*   **Off-CPU Ratio:** `bperf` metric (Time spent waiting for I/O).
*   **Throughput:** `ops/sec`.

## 2. Experimental Protocol (4-Track)

We compare **Vision** (Profiler) vs. **Intelligence** (Model Scale).

| Track | Model | Profiler Feedback | Goal |
| :--- | :--- | :--- | :--- |
| **A (Baseline)** | Local (e.g., Qwen/DeepSeek) | **None** (Blind) | Establish performance floor. |
| **B (Competitor)**| **GPT-5** (SOTA) | **None** (Blind) | Can pure intelligence solve systems problems? |
| **C (Method)** | Local (e.g., Qwen/DeepSeek) | **bperf** | Does causal vision beat blind intelligence? |
| **D (Ultimate)** | **GPT-5** (SOTA) | **bperf** | The theoretical upper bound. |

## 3. How to Run

Use the shared runner script `../run_track.sh` from the parent directory.

### Prerequisites
*   **Env:** `AI_OPT_ROCKSDB_PATH` must point to your RocksDB source.
*   **Build Command** e.g. `export AI_OPT_BUILD_CMD='DEBUG_LEVEL=0 DISABLE_WARNING_AS_ERROR=1 make -j96 db_bench'`
*   **Bench Command** e.g. `export AI_OPT_BENCH_CMD='./db_bench --benchmarks=fillrandom --num=1000000 --threads=8 --histogram'`
*   **Profiler:** For Tracks C/D, `bcoz` and `bperf` must be installed.
*   **LLM:** `vllm` or `ollama` running locally, or `OPENAI_API_KEY` set.

### Commands

**Track A (Baseline):**
```bash
export AI_OPT_MODEL_BASELINE="local-model-name"
AI_OPT_TRACK=baseline ../run_track.sh experiment_c
```

**Track B (GPT-5):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5 ../run_track.sh experiment_c
```

**Track C (Profiler-Guided):**
```bash
# Must run on Linux with bperf (root/sudo often required for eBPF)
export AI_OPT_MODEL_PROFILER="local-model-name"
AI_OPT_TRACK=profiler ../run_track.sh experiment_c
```

**Track D (GPT-5 + Profiler):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5_profiler ../run_track.sh experiment_c
```

## 4. Evaluation Metrics
The evaluator (`evaluator.py`) calculates a **Combined Fitness Score**:
$$ Fitness = 0.4 \times Throughput + 0.2 \times Latency + 0.4 \times \text{OffCpuReduction} $$

*   **Pipelining Success:** Successful pipelining should manifest as a **decrease in off-CPU time** (less blocking) and an **increase in CPU utilization**, leading to higher throughput.

## 5. Function-Slicing Design

### Motivation
RocksDB source files are thousands of lines long. Local models (Qwen, DeepSeek)
with limited context windows fail to process the full file, and smaller models
struggle to generate correct SEARCH/REPLACE diffs against such large inputs.

### Architecture
Instead of giving the LLM the full source file, we **slice** out the target
function (the EVOLVE-BLOCK region) and present only that to the LLM:

```
full_source_template.cpp (3188 lines, read-only)
        |
        +- lines 1-1815:     context (includes, helpers)          -- not shown to LLM
        +- lines 1816-1899:  EVOLVE-BLOCK (ProcessKeyValueCompaction) -- initial_program.cpp
        +- lines 1900-3188:  context (other functions)            -- not shown to LLM
```

**Flow:**
1. `initial_program.cpp` contains ONLY the EVOLVE-BLOCK region (~83 lines)
2. OpenEvolve sends this slice to the LLM with diff-based evolution enabled
3. LLM generates SEARCH/REPLACE diffs against the short slice (high reliability)
4. Evaluator reads the evolved slice + `full_source_template.cpp`
5. `_reassemble_source()` patches the slice back into the template
6. Reassembled file is written to the RocksDB tree, compiled, and benchmarked

### Files
| File | Purpose |
|------|---------|
| `initial_program.cpp` | Function slice (~83 lines) -- what the LLM evolves |
| `full_source_template.cpp` | Full original source -- used by evaluator for reassembly |
| `initial_program.py` | (Legacy) Alternative MUTATION_DIFF approach |
| `evaluator.py` | Reassembles slice -> compiles -> benchmarks -> profiles |

### Benefits
- **Context efficiency:** ~2K tokens instead of ~40K
- **Diff reliability:** SEARCH/REPLACE on 83 lines vs 3188 lines
- **Local model compatibility:** Easily fits within smallest context windows
- **Preserved evolution quality:** Diff-based evolution enables small, targeted mutations
