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
*   **Profiler:** For Tracks C/D, `bperf` (eBPF) must be installed.
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

## 4. Evaluation Metrics
The evaluator (`evaluator.py`) calculates a **Combined Fitness Score**:
$$ Fitness = 0.4 \times Throughput + 0.2 \times Latency + 0.4 \times \text{OffCpuReduction} $$

*   **Pipelining Success:** Successful pipelining should manifest as a **decrease in off-CPU time** (less blocking) and an **increase in CPU utilization**, leading to higher throughput.
