# OpenEvolve Causal Mutation Prompt Template: Experiment C (Compaction Pipelining)

## System Context
You are a C++ Performance Optimization Expert. Your goal is to reduce compaction I/O stalls by adding local software pipelining (prefetching the next block while processing the current one).

## Causal Context
- **Tool:** bperf (Off-CPU Analysis)
- **Identified Bottleneck:** Compaction jobs are frequently blocked on SST block reads
- **bperf Signal:** High off-CPU time during compaction block fetch/IO waits

## Target Files
- `db/compaction/compaction_job.cc`

## Mutation Objectives
1. **Prefetch Next Block:** Initiate read/prefetch of the next SST block while processing the current block
2. **Overlap I/O and CPU:** Ensure I/O waits are overlapped with CPU work wherever possible
3. **Local Changes Only:** Keep all changes within `compaction_job.cc` and existing APIs

## Constraints
- **No Signature Changes:** Do not change public function signatures
- **No ThreadPool Changes:** Do not modify RocksDB thread pool or scheduling logic
- **No New Dependencies:** Use existing RocksDB `ReadOptions` / `BlockBasedTable` APIs
- **Correctness:** Compaction output must remain identical
- **Language:** C++17

## Output Format
Provide the mutation in unified diff format. Include:
1. **Rationale:** How prefetch/pipelining reduces compaction I/O stalls
2. **Pipeline Points:** Where the next-block prefetch is issued and consumed
3. **Benchmark Plan:** How to measure off-CPU reduction and throughput gains
