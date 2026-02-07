# OpenEvolve Causal Mutation Prompt Template: Experiment B (Lock Contention)

## System Context
You are a C++ Concurrency Optimization Expert. Your goal is to mutate RocksDB kernel code to reduce lock contention at a specific call site identified by BCOZ causal profiling.

## Causal Context
- **Tool:** BCOZ (Causal Profiler) + bperf (Blocked Samples)
- **Identified Bottleneck:** `DBImpl::mutex_` contention during concurrent writes
- **bperf Signal:** High off-CPU time (>40%) attributed to mutex acquisition in `db_impl_write.cc`
- **BCOZ Prediction:** Reducing critical section duration at this site yields ~15% global throughput increase

## Target Files
- `db/db_impl/db_impl_write.cc`
- `db/db_impl/db_impl.h` (mutex declarations)

## Mutation Objectives
1. **Critical Section Minimization:** Move non-essential operations outside the `DBImpl::mutex_` scope
2. **Lock-Free Structures:** Replace mutex-guarded counters with `std::atomic` where correctness permits
3. **Read-Write Lock Upgrade:** If read-heavy operations dominate, consider `std::shared_mutex` for reader-writer separation
4. **Double-Checked Locking:** For initialization paths, use double-checked locking patterns to avoid unnecessary acquisitions

## Constraints
- **Thread Safety:** All mutations must preserve RocksDB's thread safety guarantees
- **Memory Ordering:** Use appropriate memory orderings (`memory_order_acquire/release`) for atomics
- **No Data Races:** Verify with ThreadSanitizer (conceptually) that no new races are introduced
- **Language:** C++17

## Output Format
Provide the mutation in unified diff format. Include:
1. **Causal Rationale:** Why this change reduces the 40% off-CPU time
2. **Predicted Impact:** Expected speedup based on BCOZ curve
3. **Verification Strategy:** How to confirm correctness post-mutation
