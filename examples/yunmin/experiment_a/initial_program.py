# EVOLVE-BLOCK-START
MUTATION_DIFF = r"""
<<<<<<< SEARCH
// Example placeholder (replace with exact code from db_impl_write.cc)
// Status s = logfile_->Sync();
=======
// Example mutation (replace with real logic)
// Status s = logfile_->Sync();
>>>>>>> REPLACE
"""
# EVOLVE-BLOCK-END


def get_static_context() -> dict:
    return {
        "experiment": "A",
        "goal": "Reduce WAL/L0 pressure using BCOZ-guided mutations",
        "target_file": "db/db_impl/db_impl_write.cc",
        "constraints": [
            "Preserve durability/ACID semantics",
            "C++17 only",
            "Minimize changes outside WAL sync path",
        ],
    }
