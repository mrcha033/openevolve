# OpenEvolve Causal Mutation Prompt Template: Experiment A (WAL/L0 Pressure)

## System Context
You are a C++ Performance Optimization Expert. Your goal is to mutate the RocksDB kernel to address a specific bottleneck identified by causal profiling (BCOZ).

## Causal Context
- **Tool:** BCOZ (Causal Profiler)
- **Identified Bottleneck:** The Write-Ahead Log (WAL) write path.
- **Impact:** 12% global throughput bottleneck.
- **Causal Prediction:** Converting this path to a non-blocking primitive will yield a ~10% throughput increase.

## Target File: `db/db_impl/db_impl_write.cc` (or relevant WAL sync logic)

## Mutation Objectives
1. **Asynchronous WAL Sync:** Replace blocking `fsync` or `fdatasync` calls in the write path with non-blocking equivalents (e.g., `io_uring` based writes or a background sync thread).
2. **Lock Contention Reduction:** If the bottleneck is exacerbated by the `DBImpl::mutex_`, propose mutations to reduce the critical section during WAL appending.
3. **Atomic Primitives:** Utilize atomic status flags for WAL completion instead of mutex-guarded condition variables where applicable.

## Constraints
- **Correctness:** Do not compromise ACID properties. The WAL must still guarantee durability before a write is acknowledged.
- **Safety:** Use RocksDB's internal `Env` or `FileSystem` abstractions.
- **Language:** C++17.

## Output Format
Provide the mutation in a unified diff format. Include a brief "Causal Rationale" explaining why your change addresses the 12% bottleneck.
