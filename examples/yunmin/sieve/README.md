# Sieve of Eratosthenes (C++)

## Objective
Optimize a prime-counting sieve for N = 10^7.

## Why This Task
- **Looks algorithmic but IS a cache problem**: Naive byte-array sieve (10MB) thrashes L2 cache during marking
- **Rich optimization space**: Bit packing (8x memory reduction), segmented sieve (L2-fitting chunks), wheel factorization, skip-even optimization
- **Profiler adds value**: BCOZ pinpoints the marking loop; bperf reveals the cache-miss stall ratio that the LLM cannot infer from source code alone

## Task Summary
- Count all primes up to 10,000,000 (expected: 664,579)
- Correctness verified against reference implementation
- Naive baseline uses uint8_t array (1 byte per element)

## Metrics
- `ops_per_sec` — complete sieve runs per second
- `p99_latency_us` — p99 latency of one sieve run

## Requirements
- C++17 toolchain (`g++`)
- bcoz/bperf for profiler tracks (optional)

## How To Run
```bash
AI_OPT_TRACK=baseline ./run_track.sh sieve
```

Profiler track:
```bash
AI_OPT_TRACK=profiler ./run_track.sh sieve
```

Standalone benchmark:
```bash
python bench.py --program initial_program.cpp
```
