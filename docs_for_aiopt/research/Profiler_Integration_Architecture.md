# AIOpt: Profiler-in-the-Loop Architecture

**Status:** Implemented and verified (2026-02-08)

## Overview

The profiler integration uses OpenEvolve's existing artifact pipeline to feed profiler results into the LLM's mutation prompt. No framework modifications were needed.

```
┌─────────────────────────────────────────────────────────────────┐
│                     OPENEVOLVE LOOP                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────────────────────────────┐    │
│  │   LLM       │    │   EVALUATOR                          │    │
│  │   Mutation   │───▶│   1. Run program                     │    │
│  │   Generator  │    │   2. Measure performance              │    │
│  └──────▲──────┘    │   3. Run profilers (optional)         │    │
│         │           │   4. Return EvaluationResult           │    │
│         │           │      metrics: {score, ops/sec, ...}    │    │
│         │           │      artifacts: {profiler_bcoz, ...}   │    │
│         │           └──────────────────┬───────────────────┘    │
│         │                              │                         │
│         │  ┌───────────────────────────▼──────────────────────┐  │
│         │  │   ARTIFACT PIPELINE (built into OpenEvolve)      │  │
│         │  │   • Artifacts stored with program in database    │  │
│         │  │   • Retrieved for parent on next iteration       │  │
│         │  │   • Rendered in prompt under "## Last Output"    │  │
│         │  └───────────────────────────┬──────────────────────┘  │
│         │                              │                         │
│         └──────────────────────────────┘                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │   MAP-ELITES DATABASE                                     │   │
│  │   Feature dims: ops_per_sec, p99_latency_us               │   │
│  │   Selection: causal_fitness() or fast_fitness()            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Code Path (verified)

### Profiler → Artifact generation
```
evaluator.py:
  bcoz_result = run_bcoz(...)           # openevolve/aiopt/bcoz_parser.py
  bperf_result = run_bperf(...)         # openevolve/aiopt/bperf_parser.py
  artifacts["profiler_bcoz"] = bcoz_context(bcoz_result)    # generate_mutation_context()
  artifacts["profiler_bperf"] = bperf_context(bperf_result) # generate_mutation_context()
  return EvaluationResult(metrics=response, artifacts=artifacts)
```

### Artifact → Prompt injection (framework handles this)
```
evaluator.py:298-317  _process_evaluation_result() handles EvaluationResult
evaluator.py:216-241  artifacts stored in _pending_artifacts
iteration.py:56       parent_artifacts = database.get_artifacts(parent.id)
iteration.py:82       build_prompt(..., program_artifacts=parent_artifacts)
sampler.py:607-634    _render_artifacts() renders as markdown in prompt
```

### What the LLM sees (example)
```markdown
## Last Execution Output

### profiler_bcoz
## Causal Profiling Results (BCOZ)
1. **db_impl_write.cc:234** — 15.0% potential speedup
Primary target: db_impl_write.cc:234

### profiler_bperf
## Off-CPU Analysis (bperf)
Off-CPU ratio: 35.0%
Top blocking sites:
1. __pthread_mutex_lock — 15.0%
```

## Components

| File | Purpose | Status |
|------|---------|--------|
| `openevolve/aiopt/bcoz_parser.py` | Parse BCOZ causal profiles, `generate_mutation_context()` | Done |
| `openevolve/aiopt/bperf_parser.py` | Parse bperf off-CPU reports, `generate_mutation_context()` | Done |
| `openevolve/aiopt/fitness.py` | `causal_fitness()` and `fast_fitness()` scoring | Done |
| `openevolve/evaluation_result.py` | `EvaluationResult` dataclass with artifact support | Done |

## Track Control

Profiler feedback is controlled per-track via environment variables:

| Track | `AI_OPT_RUN_BCOZ` | `AI_OPT_RUN_BPERF` | LLM sees profiler artifacts? |
|-------|--------------------|---------------------|-------------------------------|
| A (baseline) | 0 | 0 | No — no artifacts generated |
| B (strong model) | 0 | 0 | No |
| C (profiler) | 1 | 1 | Yes — injected via artifact pipeline |
| D (upper bound) | 1 | 1 | Yes |

When profilers are disabled, the evaluator returns a plain `dict` (no artifacts). The prompt has no profiler section. This ensures clean separation between tracks.
