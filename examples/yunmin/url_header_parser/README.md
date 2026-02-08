# URL / HTTP Header Parsing (Fast Path)

## Objective
Optimize a request-line + header parser. The profiler should surface branch patterns and dominant header cases that are not obvious from the source.

## Task Summary
- Parse minimal HTTP requests from bytes.
- Return `(method, path, version, headers)` with lowercase header names.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## How To Run
```bash
AI_OPT_TRACK=baseline ../run_track.sh url_header_parser
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ../run_track.sh url_header_parser
```
