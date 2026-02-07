# Causal Mutation Prompt Template: L0-Compaction Analysis

## BCOZ Context (Input)
- **Bottleneck Path:** `rocksdb::DBImpl::BackgroundCompaction` -> `rocksdb::DBImpl::DoCompactionWork` -> `rocksdb::CompactionJob::Run`
- **Metric:** BCOZ identifies the synchronous I/O wait in `WriteLevel0Table` as a **12% global throughput bottleneck**.
- **Prediction:** A 50% reduction in synchronous latency in this path results in a ~6% global throughput gain.

## LLM Objective
Refactor the compaction write path to use the `OpenEvolve` non-blocking primitive library (v2.1). Specifically, implement a double-buffered asynchronous write-ahead strategy for Level 0 compaction jobs.

## Constraints
1. **Thread Safety:** Use `folly::Future` or equivalent non-blocking primitives already present in the lab build.
2. **Persistence:** Ensure that the completion callback validates the LSM-tree state before acknowledging the job.
3. **No Config Changes:** Modify only the C++ logic in `db/compaction_job.cc`.

## Mutation Prompt (Draft)
```text
Role: High-Performance Systems Engineer.
Task: Causal refactoring of RocksDB compaction write path.
Data: BCOZ identifies 12% bottleneck in WriteLevel0Table.
Context:
{{SOURCE_CODE_EXTRACT}}

Instructions:
Identify the synchronous file write call. Replace it with an asynchronous double-buffering pattern.
Ensure that {{METRIC_VERIFICATION}} is included in the test-harness feedback loop.
```
