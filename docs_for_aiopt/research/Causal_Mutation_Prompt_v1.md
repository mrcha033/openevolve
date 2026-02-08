# Causal Mutation Prompt Template v1

**Status:** ARCHIVED — Superseded by task redesign (2026-02-08)

This template was designed for RocksDB compaction pipelining (Experiment C). The RocksDB experiment design was abandoned due to:
1. Triple-indirection making valid mutations impossible
2. Circularity in task design (task defined by what profiler measures)

See `AIOpt_Critical_Review.md` for the full post-mortem.
See `AIOpt_Proposal.md` for the new task design approach.

---

## Original Content (for reference)

### BCOZ Context (Input)
- **Bottleneck Path:** `rocksdb::DBImpl::BackgroundCompaction` -> `rocksdb::CompactionJob::Run`
- **Metric:** BCOZ identifies I/O waits in compaction block processing as a global throughput bottleneck.

### LLM Objective
Implement local software pipelining in `db/compaction/compaction_job.cc`.

### Why this was circular
The task ("reduce compaction I/O stalls") was defined by exactly what bperf measures (off-CPU time during compaction). Showing bperf helps with this task is tautological.
