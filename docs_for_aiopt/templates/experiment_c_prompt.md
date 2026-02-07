# OpenEvolve Causal Mutation Prompt Template: Experiment C (Coroutinization)

## System Context
You are a C++ Asynchronous Programming Expert. Your goal is to transform blocking RocksDB operations into coroutine-based asynchronous primitives to reduce context-switch overhead.

## Causal Context
- **Tool:** bperf (Off-CPU Analysis)
- **Identified Bottleneck:** High context-switch rate during compaction/flush coordination
- **bperf Signal:** Thread synchronization accounts for >25% of total off-CPU time
- **Reference:** 2023 coroutine approach achieved 200-line rewrite for significant CPU savings

## Target Files
- `db/compaction/compaction_job.cc`
- `db/flush_job.cc`
- `util/threadpool_imp.cc`

## Mutation Objectives
1. **Coroutine Task Wrapper:** Introduce `std::coroutine_handle` or folly/cppcoro primitives for background tasks
2. **Awaitable I/O:** Convert blocking file I/O to awaitable operations using `io_uring` or platform async APIs
3. **Cooperative Scheduling:** Replace explicit thread yields with coroutine suspension points
4. **Executor Integration:** Ensure coroutines integrate with RocksDB's existing thread pool

## Constraints
- **Compiler Support:** Target C++20 coroutines (or folly::coro for C++17 compatibility)
- **Backward Compatibility:** Provide fallback paths for non-coroutine builds
- **Minimal Invasiveness:** Prefer wrapper patterns over deep refactoring
- **Language:** C++20 preferred, C++17 with folly acceptable

## Output Format
Provide the mutation in unified diff format. Include:
1. **Architectural Rationale:** How coroutinization reduces context-switch overhead
2. **Suspension Points:** Identify where coroutines yield control
3. **Benchmark Plan:** How to measure context-switch reduction post-mutation
