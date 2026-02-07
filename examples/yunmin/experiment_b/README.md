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
*   **Profiler:** For Tracks C/D, `bperf` (eBPF) and `coz` must be installed.
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
