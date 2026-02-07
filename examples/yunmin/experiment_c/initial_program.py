# EVOLVE-BLOCK-START
MUTATION_DIFF = r"""
<<<<<<< SEARCH
// Example placeholder (replace with exact code from compaction_job.cc)
// thread_pool_.Schedule(&CompactionJob::Run, this);
=======
// Example mutation (replace with real logic)
// coroutine_scheduler_.Schedule(&CompactionJob::Run, this);
>>>>>>> REPLACE
"""
# EVOLVE-BLOCK-END


def get_static_context() -> dict:
    return {
        "experiment": "C",
        "goal": "Reduce context-switch overhead via coroutinization",
        "target_file": "db/compaction/compaction_job.cc",
        "constraints": [
            "C++20 coroutines preferred (or folly::coro with C++17)",
            "Provide fallback path if coroutines disabled",
            "Minimize invasive refactors",
        ],
    }
