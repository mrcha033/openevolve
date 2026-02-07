# EVOLVE-BLOCK-START
# Empty diff means "no-op" for the initial program; evaluator will run baseline.
MUTATION_DIFF = r""
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
