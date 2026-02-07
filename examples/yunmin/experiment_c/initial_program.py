# EVOLVE-BLOCK-START
# Empty diff means "no-op" for the initial program; evaluator will run baseline.
MUTATION_DIFF = r""
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
