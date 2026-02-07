# EVOLVE-BLOCK-START
MUTATION_DIFF = r"""
<<<<<<< SEARCH
// Example placeholder (replace with exact code from db_impl_write.cc)
// std::lock_guard<std::mutex> lock(mutex_);
=======
// Example mutation (replace with real logic)
// std::unique_lock<std::mutex> lock(mutex_);
>>>>>>> REPLACE
"""
# EVOLVE-BLOCK-END


def get_static_context() -> dict:
    return {
        "experiment": "B",
        "goal": "Reduce DBImpl::mutex_ contention using BCOZ + bperf signals",
        "target_file": "db/db_impl/db_impl_write.cc",
        "constraints": [
            "Preserve thread safety",
            "Use correct memory ordering for atomics",
            "C++17 only",
        ],
    }
