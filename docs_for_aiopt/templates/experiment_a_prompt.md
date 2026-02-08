# Experiment A Prompt Template (WAL/L0 Pressure)

**Status:** ARCHIVED — RocksDB experiments abandoned (2026-02-08)

This was a prompt template for LLM-guided mutation of `db_impl_write.cc` to reduce WAL pressure.
It was never used in practice because the triple-indirection design prevented valid mutations.

See `research/AIOpt_Critical_Review.md` for the post-mortem.
See `research/AIOpt_Proposal.md` for the new experiment design.
