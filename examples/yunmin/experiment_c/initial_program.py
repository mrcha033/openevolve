# EVOLVE-BLOCK-START
MUTATION_DIFF = r"""
<<<<<<< SEARCH
// Example placeholder (replace with exact code from compaction_job.cc)
// status = input->Next();
// ProcessKeyValue(input->key(), input->value());
=======
// Example mutation: prefetch next block while processing current
// input->PrepareNextBlock();          // async prefetch hint
// status = input->Next();
// ProcessKeyValue(input->key(), input->value());
>>>>>>> REPLACE
"""
# EVOLVE-BLOCK-END


def get_static_context() -> dict:
    return {
        "experiment": "C",
        "goal": "Reduce compaction I/O stalls via prefetching and amortized locking",
        "target_file": "db/compaction/compaction_job.cc",
        "constraints": [
            "Stay local to compaction_job.cc — no scheduler rewrites",
            "Prefetching: overlap next-block I/O with current-block processing",
            "Amortized locking: batch mutex acquisitions to reduce per-key overhead",
            "Preserve correctness — compaction output must remain identical",
            "No new dependencies; use existing ReadOptions / BlockBasedTable APIs",
        ],
    }
