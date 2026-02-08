# JSON Parser / Serializer (Subset, C++)

## Objective
Optimize a single-file C++ JSON subset parser/serializer. Profiler feedback should reveal non-obvious branch and cache behavior.

## Task Summary
- Parse a restricted JSON subset (strings without escapes, integers, arrays, objects, booleans, null).
- Serialize to a canonical form.
- Correctness: output must match the reference normalization exactly.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
From `/Users/mrcha033/Projects/openevolve/examples/yunmin`:

```bash
AI_OPT_TRACK=baseline ./run_track.sh json_parser
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh json_parser
```
