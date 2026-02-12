# Experiment A: WAL/L0 Pressure Optimization

## 1. Scientific Objective
**Goal:** Reduce Write Stalls and L0 saturation by optimizing the Write-Ahead Log (WAL) path.
**Hypothesis:** The standard `DBImpl::Write` path suffers from blocking I/O (`fsync`) and coarse-grained locking. Causal profiling (`BCOZ`) can identify the exact lines causing latency, allowing an LLM to inject **asynchronous writes** or **atomic primitives** where they matter most.

**Target File:** `db/db_impl/db_impl_write.cc`
**Profiling Signal:**
*   **Throughput:** `ops/sec` (db_bench).
*   **Latency:** `p99` (db_bench).
*   **Causal Speedup:** `BCOZ` virtual speedup prediction.

## 2. Experimental Protocol (4-Track)

We compare **Vision** (Profiler) vs. **Intelligence** (Model Scale).

| Track | Model | Profiler Feedback | Goal |
| :--- | :--- | :--- | :--- |
| **A (Baseline)** | Local (e.g., Qwen/DeepSeek) | **None** (Blind) | Establish performance floor. |
| **B (Competitor)**| **GPT-5** (SOTA) | **None** (Blind) | Can pure intelligence solve systems problems? |
| **C (Method)** | Local (e.g., Qwen/DeepSeek) | **BCOZ + bperf** | Does causal vision beat blind intelligence? |
| **D (Ultimate)** | **GPT-5** (SOTA) | **BCOZ + bperf** | The theoretical upper bound. |

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
AI_OPT_TRACK=baseline ../run_track.sh experiment_a
```

**Track B (GPT-5):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5 ../run_track.sh experiment_a
```

**Track C (Profiler-Guided):**
```bash
# Must run on Linux with Coz installed
export AI_OPT_MODEL_PROFILER="local-model-name"
AI_OPT_TRACK=profiler ../run_track.sh experiment_a
```

**Track D (GPT-5 + Profiler):**
```bash
export OPENAI_API_KEY="sk-..."
AI_OPT_TRACK=gpt5_profiler ../run_track.sh experiment_a
```

## 4. Evaluation Metrics
The evaluator (`evaluator.py`) calculates a **Combined Fitness Score**:
$$ Fitness = 0.3 \times Throughput + 0.2 \times Latency + 0.3 \times \text{CausalRealization} $$

*   **Causal Realization:** In Track C/D, we reward mutations that specifically eliminate the bottleneck identified by BCOZ in the previous generation.

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
        +- lines 1-369:     context (includes, helpers) -- not shown to LLM
        +- lines 370-971:   EVOLVE-BLOCK (WriteImpl) ---- initial_program.cpp
        +- lines 972-2959:  context (other functions)  -- not shown to LLM
```

**Flow:**
1. `initial_program.cpp` contains ONLY the EVOLVE-BLOCK region (~601 lines)
2. OpenEvolve sends this slice to the LLM with diff-based evolution enabled
3. LLM generates SEARCH/REPLACE diffs against the short slice (high reliability)
4. Evaluator reads the evolved slice + `full_source_template.cpp`
5. `_reassemble_source()` patches the slice back into the template
6. Reassembled file is written to the RocksDB tree, compiled, and benchmarked

### Files
| File | Purpose |
|------|---------|
| `initial_program.cpp` | Function slice (~601 lines) -- what the LLM evolves |
| `full_source_template.cpp` | Full original source -- used by evaluator for reassembly |
| `initial_program.py` | (Legacy) Alternative MUTATION_DIFF approach |
| `evaluator.py` | Reassembles slice -> compiles -> benchmarks -> profiles |

### Benefits
- **Context efficiency:** ~5K tokens instead of ~37K
- **Diff reliability:** SEARCH/REPLACE on 601 lines vs 2959 lines
- **Local model compatibility:** Fits within 8K-16K context windows
- **Preserved evolution quality:** Diff-based evolution enables small, targeted mutations
