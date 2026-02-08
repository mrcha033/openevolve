# JSON Parser / Serializer (Subset)

## Objective
Optimize a single-file JSON subset parser and serializer. The profiler should surface non-obvious branch and cache behavior in the state machine and scanning loops.

## Task Summary
- Parse a restricted JSON subset (strings without escapes, integers, arrays, objects, booleans, null).
- Serialize the object back to JSON.
- Correctness: `json.loads(output) == json.loads(input)` for all cases.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## How To Run
Use the shared runner from `examples/yunmin`:

```bash
AI_OPT_TRACK=baseline ../run_track.sh json_parser
```

Optional profiler tracks:

```bash
AI_OPT_TRACK=profiler ../run_track.sh json_parser
```
