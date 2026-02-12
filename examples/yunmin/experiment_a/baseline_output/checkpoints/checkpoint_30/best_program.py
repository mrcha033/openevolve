# EVOLVE-BLOCK-START
# Empty diff means "no-op" for the initial program; evaluator will run baseline.
MUTATION_DIFF = r""
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
