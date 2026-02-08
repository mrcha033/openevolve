# AIOpt Research Proposal: Profiler-Guided Evolutionary Code Optimization

**Version:** 2.0 (post-pivot)
**Date:** 2026-02-08

## 1. Thesis

Runtime profiling feedback (causal profiling + off-CPU analysis) improves the quality and direction of LLM-driven evolutionary code optimization — not by telling the LLM what to fix, but by revealing performance phenomena invisible from source inspection alone.

## 2. Related Work and Positioning

### What exists

| Work | Contribution | Gap |
|------|-------------|-----|
| **AlphaEvolve** (DeepMind) | Evolutionary coding agent with MAP-Elites, diff-based mutation, LLM ensemble. Discovered novel algorithms (sorting networks, matrix multiplication). | No runtime profiling feedback — fitness is score-only. |
| **Barbarians / Let Barbarians In** (Berkeley) | ADRS framework for AI-driven systems research. 50–300 line scope, reliable verifiers, smooth rewards. | Focuses on problem specification, not on enriching the feedback signal. |
| **PerfCodeGen** (Salesforce) | Runtime execution feedback improves LLM code quality. Two-phase: correctness then performance. | Single-shot refinement, not evolutionary. Feedback is "this test case is slow," not causal profiling. |
| **SysGPT** (Park et al.) | Systematized 8 serial optimization methodologies. Fine-tuned GPT-4o for methodology-aware suggestions. | Advisory only — no automated iteration or evaluation. |
| **Blocked Samples** | BCOZ causal profiling + bperf off-CPU analysis for identifying bottlenecks. | Designed for human engineers, not integrated into automated optimization loops. |

### Our contribution

We close the gap between **evolutionary code optimization** (AlphaEvolve) and **runtime profiling** (Blocked Samples) by feeding causal profiler output into the LLM's mutation prompt as structured artifacts. This creates a closed loop:

```
LLM generates mutation → evaluate (run + profile) → profiler artifacts fed back to LLM → next mutation
```

The hypothesis: this loop produces qualitatively different mutations than score-only feedback. Without profiling, the LLM optimizes based on source-level patterns (algorithmic improvements, code cleanup). With profiling, it discovers and targets micro-architectural bottlenecks (cache misses, lock contention, branch misprediction) that are invisible from code alone.

## 3. Task Design

### Why the previous design failed

The RocksDB experiments had two fatal flaws:

1. **Triple indirection**: The LLM wrote Python containing a string containing a C++ diff targeting code it never saw. Zero valid mutations in 50 iterations.

2. **Circularity**: Tasks were defined by what the profiler measures ("reduce mutex contention" + bperf measuring mutex contention = tautological result).

### Design principles for new tasks

From the literature survey, successful AI-driven optimization tasks share:

1. **Self-contained**: Single file, 50–300 lines. LLM evolves the actual code, no indirection layers.
2. **Fast evaluation**: Seconds, not minutes. Enables 100+ iterations per run.
3. **Non-obvious bottleneck**: The task description says "make it faster" — it does NOT name the bottleneck. The profiler reveals what the LLM can't see from source.
4. **Rich optimization space**: Multiple valid strategies (algorithmic, memory layout, SIMD, concurrency).
5. **Correctness verifiable**: Output can be checked against a reference.
6. **Smooth reward**: Performance varies continuously, not pass/fail.

### Candidate tasks

#### Candidate A: Self-contained C++ program optimization

**Target**: A textbook-quality C++ program (100–200 lines) performing a compute-intensive task: JSON parsing, B-tree operations, LZ4 compression, or matrix operations.

**Why profiler helps non-obviously**: The program has both algorithmic and micro-architectural optimization opportunities. Without profiler feedback, the LLM tends toward algorithmic improvements (better data structures, loop restructuring). With profiler feedback revealing cache miss rates, branch misprediction hotspots, or memory stall cycles, it can discover layout optimizations, prefetch insertion, or loop tiling that are invisible from source inspection.

**Evaluation**: Run program on fixed input, measure throughput. Verify correctness against reference output.

**Precedent**: Our checkpoint_100 result (GPT-Mini C++ → 288 tok/s) proved OpenEvolve can produce sophisticated optimizations (kernel fusion, pointer walking, selective initialization) on self-contained C++ programs.

**Profiler integration**: `perf stat` for cache misses and branch mispredictions (available on Linux without special tools), `bperf` for off-CPU analysis on concurrent variants.

#### Candidate B: Heuristic function evolution

**Target**: A small policy function (50–100 lines) — cache eviction policy, task scheduling priority function, or memory allocation bin selection.

**Why profiler helps non-obviously**: The heuristic's quality depends on workload characteristics that the LLM can't predict from source. Profiler feedback reveals how the heuristic behaves at runtime: cache hit rates, blocking patterns, allocation fragmentation. The LLM sees "your policy causes 40% cache misses on this workload" and adapts.

**Evaluation**: Run the heuristic within a driver program on representative workloads. Measure hit rate, throughput, or latency.

**Precedent**: AlphaEvolve's strongest results were on heuristic evolution (data center scheduling, bin packing).

**Profiler integration**: Application-level metrics from the driver + `perf stat` hardware counters.

#### Candidate C: Data structure layout optimization

**Target**: A data-intensive program where the bottleneck is memory layout — array-of-structures vs structure-of-arrays, field ordering for cache line utilization, padding and alignment.

**Why profiler helps non-obviously**: Cache behavior is completely invisible from source code. Two programs with identical algorithms but different struct layouts can differ by 5× in performance. Profiler feedback showing L1/LLC cache miss rates directly reveals whether the layout is cache-friendly.

**Evaluation**: Run program on large dataset, measure throughput. Verify correctness.

**Profiler integration**: `perf stat` cache-miss counters, `perf mem` for memory access patterns.

### Recommended starting point

**Candidate A** is the strongest first choice because:
- Proven precedent (checkpoint_100)
- Richest optimization space (algorithmic + micro-architectural)
- Most natural fit for both BCOZ and bperf
- Most generalizable results

If Candidate A shows positive results, Candidate B would be a strong second experiment demonstrating generality across task types.

## 4. Experiment Design

### 4-Track Factorial

| Track | LLM | Profiler in Prompt | What it tests |
|-------|-----|-------------------|---------------|
| A — baseline | Local (Llama 70B) | No | What can a local model do with score-only feedback? |
| B — strong model | GPT-5 | No | How much does model quality alone help? |
| C — profiler feedback | Local (Llama 70B) | Yes (BCOZ + bperf artifacts) | Does profiler feedback compensate for weaker model? |
| D — upper bound | GPT-5 | Yes (BCOZ + bperf artifacts) | What's the ceiling with both advantages? |

### Statistical design

- **Seeds**: 5 independent runs per track (20 total)
- **Iterations**: 50–100 per run (fast evaluation enables this)
- **Baseline noise**: Measured from `capture_baseline.sh` (±N% establishes significance threshold)
- **Metrics**: Best score, score trajectory over iterations, number of valid mutations, mutation diversity (MAP-Elites cell coverage)

### Analysis plan

**Quantitative:**
- Compare final best scores across tracks (Mann-Whitney U test, 5 samples per track)
- Compare score improvement trajectories (area under curve)
- Count structurally distinct mutations per track (MAP-Elites diversity)

**Qualitative:**
- Categorize mutations by SysGPT's 8 methodologies
- Compare: do profiler-feedback tracks produce different *types* of optimization? (e.g., more "Hardware Specialization" and "Reordering" vs. "Removal" and "Replacement")
- Case studies of mutations that were only discovered with profiler feedback

### Expected outcomes

| Comparison | Hypothesis | If confirmed |
|------------|-----------|-------------|
| C > A | Profiler feedback helps even weak models | Core thesis validated |
| D > B | Profiler feedback helps even strong models | Generality across model tiers |
| D > C | Model quality still matters with profiling | Not just about feedback signal |
| B ≈ C | Strong model without profiling ≈ weak model with profiling | Profiling as "equalizer" — compelling narrative |

## 5. Infrastructure (Ready)

All framework components are implemented and verified:

| Component | Status | Location |
|-----------|--------|----------|
| bperf parser + `generate_mutation_context()` | Done | `openevolve/aiopt/bperf_parser.py` |
| BCOZ parser + `generate_mutation_context()` | Done | `openevolve/aiopt/bcoz_parser.py` |
| Causal fitness function | Done | `openevolve/aiopt/fitness.py` |
| EvaluationResult with artifact support | Done | `openevolve/evaluation_result.py` |
| Evaluator → artifact → prompt pipeline | Verified | Built into OpenEvolve framework |
| 4-track runner with seed support | Done | `examples/yunmin/run_track.sh` |
| Baseline capture script | Done | `examples/yunmin/capture_baseline.sh` |

**What's needed**: New `initial_program` + `evaluator.py` + `config.yaml` for the chosen task. The evaluator calls `generate_mutation_context()` and returns `EvaluationResult` with profiler artifacts — same pattern as the existing RocksDB evaluators, but simpler (no diff-of-diff indirection).

## 6. Timeline

| Week | Activity |
|------|----------|
| 1 | Select task, implement initial_program + evaluator, sanity check (5 iterations) |
| 2 | Run 4-track experiment (20 runs × 50–100 iterations) |
| 3 | Analyze results, mutation categorization, case studies |
| 4 | Write up, figures, related work positioning |
