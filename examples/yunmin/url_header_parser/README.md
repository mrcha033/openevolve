# URL / HTTP Header Parsing (Fast Path, C++)

## Objective
Optimize a request-line + header parser. Profiler feedback should reveal branch patterns and dominant header cases.

## Task Summary
- Parse minimal HTTP requests from bytes.
- Return a canonical string of request line and headers.

## Metrics
- `ops_per_sec`
- `p99_latency_us`

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh url_header_parser
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh url_header_parser
```
