# PROJECT_PLAN: AIOpt (CSLab Research)

**Status:** Pivoting — task redesign in progress
**Last updated:** 2026-02-08

## Research Question

> When an LLM evolves code for a general performance goal, does runtime profiling feedback shift it from superficial rewrites toward structurally meaningful optimizations?

## Background and Motivation

LLM-driven evolutionary code optimization (AlphaEvolve, OpenEvolve) has shown strong results on self-contained algorithmic tasks: kernel fusion in GPT-Mini C++ (288 tok/s, our checkpoint_100), sorting networks, hash functions (AlphaEvolve). PerfCodeGen showed that runtime execution feedback improves LLM-generated code quality. SysGPT systematized serial optimization into 8 methodologies (batching, caching, precomputing, deferring, relaxation, contextualization, HW specialization, layering).

**The gap:** No work has studied whether *causal profiling* feedback (BCOZ speedup predictions, bperf off-CPU analysis) improves the *evolutionary search* itself — not just the final code quality, but the character and direction of mutations over time.

## Lessons Learned (RocksDB Experiment, 2026-02-08)

The initial approach — evolving C++ diffs for RocksDB kernel code — failed for two reasons:

1. **Task formulation:** A triple-indirection design (Python string containing a C++ diff) made it impossible for the LLM to produce valid mutations. 50 iterations yielded zero applied diffs. See `research/AIOpt_Critical_Review.md`.

2. **Circularity:** All three experiments (WAL write path, lock contention, compaction pipelining) defined the task in terms of what the profiler measures. Showing that bperf helps reduce mutex contention when the task IS "reduce mutex contention" is tautological.

## New Direction: Self-Contained Program Optimization

### Design Principles (from literature)

| Principle | Source | Application |
|-----------|--------|-------------|
| Reliable automated verifiers | Barbarians at the Gate | Programs must be runnable with measurable metrics |
| Contained scope (50–300 lines) | Barbarians / AlphaEvolve | LLM evolves the program directly, no indirection |
| Smooth reward surface | Let the Barbarians In | Fitness improves gradually, not pass/fail |
| Diff-based evolution | AlphaEvolve / OpenEvolve | SEARCH/REPLACE on actual source |
| Runtime execution feedback | PerfCodeGen | Profiler results in the prompt, not just scores |
| Methodology-aware guidance | SysGPT | Prompt can reference the 8 serial optimization methodologies |

### Task Selection Criteria

The optimization target must satisfy:

1. **Self-contained** — single file, LLM sees and evolves the actual code
2. **Fast evaluation** — seconds, not minutes (enables 100+ iterations)
3. **Non-obvious bottleneck** — profiler reveals something the LLM can't predict from source inspection (cache behavior, branch misprediction, blocking patterns)
4. **Rich optimization space** — multiple valid strategies exist (algorithmic, memory layout, SIMD, etc.)
5. **Not circular** — the task description doesn't name the bottleneck the profiler measures

### Candidate Tasks

See `research/AIOpt_Proposal.md` for detailed design. Summary:

| Candidate | Type | Why profiler helps non-obviously |
|-----------|------|----------------------------------|
| C++ program optimization (parser, B-tree, compression) | Direct code evolution | Cache misses, memory stalls invisible from source |
| Heuristic evolution (cache eviction, scheduling) | Small function evolution | Runtime workload behavior unpredictable from code |
| Data structure layout (AoS→SoA, field ordering) | Memory layout evolution | Cache line utilization invisible without profiler |

### Experiment Design: 4-Track Factorial

| Track | Model | Profiler Feedback | Tests |
|-------|-------|-------------------|-------|
| A | Local (Llama 70B) | None (score only) | Baseline LLM capability |
| B | Strong (GPT-5) | None (score only) | Model quality effect |
| C | Local (Llama 70B) | BCOZ + bperf artifacts in prompt | Profiler feedback effect |
| D | Strong (GPT-5) | BCOZ + bperf artifacts in prompt | Combined upper bound |

**Key comparisons:**
- C vs A (same model) → isolates profiler feedback contribution
- B vs A (same feedback) → isolates model quality contribution
- D vs B (same model) → does profiler feedback help even strong models?
- Statistical power: 5 seeds per track, significance threshold from baseline noise

## Infrastructure Status

The OpenEvolve integration is complete and validated:
- `openevolve/aiopt/bperf_parser.py` — parser + `generate_mutation_context()`
- `openevolve/aiopt/bcoz_parser.py` — parser + `generate_mutation_context()`
- `openevolve/aiopt/fitness.py` — causal fitness function
- `openevolve/evaluation_result.py` — `EvaluationResult` with artifact support
- Evaluator → artifact → prompt pipeline verified end-to-end
- `run_track.sh` — 4-track runner with seed support
- `capture_baseline.sh` — automated baseline capture

## Milestones

1. [ ] Finalize task selection (choose from candidates in Proposal)
2. [ ] Implement new initial_program + evaluator for chosen task
3. [ ] Sanity check: 5-iteration run confirming LLM produces valid mutations
4. [ ] Capture baseline metrics and noise floor
5. [ ] Run 4-track experiment (5 seeds each = 20 runs)
6. [ ] Analyze results: mutation quality, score trajectories, diversity
7. [ ] Write up findings

## References

- AlphaEvolve (DeepMind, 2025) — evolutionary coding agent, MAP-Elites
- Barbarians at the Gate (UC Berkeley, 2025) — ADRS framework
- Let the Barbarians In (2025) — extended evaluation, design recommendations
- SysGPT (Park et al., OSDI 2025) — 8 serial optimization methodologies
- PerfCodeGen (Salesforce, 2024) — runtime feedback for LLM code optimization
- Blocked Samples (2024) — BCOZ/bperf causal + off-CPU profiling
