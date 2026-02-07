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
*   **Profiler:** For Tracks C/D, `coz` and `bperf` must be installed.
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
