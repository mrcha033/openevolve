# Experiment C Prompt Template (Compaction Pipelining)

**Status:** ARCHIVED — RocksDB experiments abandoned (2026-02-08)

This was a prompt template for LLM-guided mutation of `compaction_job.cc` to reduce I/O stalls via prefetching.
It was never used in practice because the triple-indirection design prevented valid mutations.

See `research/AIOpt_Critical_Review.md` for the post-mortem.
See `research/AIOpt_Proposal.md` for the new experiment design.
