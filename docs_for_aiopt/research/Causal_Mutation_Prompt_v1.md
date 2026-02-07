# Causal Mutation Prompt Template: Experiment C (Compaction Pipelining)

## BCOZ Context (Input)
- **Bottleneck Path:** `rocksdb::DBImpl::BackgroundCompaction` -> `rocksdb::DBImpl::DoCompactionWork` -> `rocksdb::CompactionJob::Run`
- **Metric:** BCOZ identifies I/O waits in compaction block processing as a global throughput bottleneck.
- **Prediction:** Reducing compaction I/O stalls should improve throughput and reduce off-CPU time.

## LLM Objective
Implement local software pipelining in `db/compaction/compaction_job.cc`: prefetch the next SST block while processing the current block.

## Constraints
1. **Thread Safety:** Preserve existing synchronization and correctness guarantees.
2. **No New Dependencies:** Use existing RocksDB APIs (e.g., `ReadOptions`, block/table interfaces).
3. **No Signature Changes:** Do not change public function signatures.
4. **No Config Changes:** Modify only the C++ logic in `db/compaction/compaction_job.cc`.

## Mutation Prompt (Draft)
```text
Role: High-Performance Systems Engineer.
Task: Causal refactoring of RocksDB compaction write path.
Data: BCOZ/bperf indicate compaction block I/O stalls.
Context:
{{SOURCE_CODE_EXTRACT}}

Instructions:
Identify the block read/iteration loop. Add a prefetch of the next block while processing the current block.
Keep changes local to compaction_job.cc and maintain identical output.
```
