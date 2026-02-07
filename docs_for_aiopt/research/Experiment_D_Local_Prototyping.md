# Experiment D: Local Prototyping (Not Implemented)

## Objective
This document describes a possible local prototyping path. It is not implemented in the current codebase or experiments.

## Current Implementation
- Experiments run against a full RocksDB source tree configured via `AI_OPT_ROCKSDB_PATH`.
- Evaluators are defined in `examples/yunmin/experiment_*/evaluator.py`.

## Scope (If Implemented Later)
This would validate a local end-to-end loop with limited profiler support. It is intentionally out of scope for the current pipeline.

## Setup Steps
Not applicable to the current implementation.

## Mutation Targets
Use the targets in `examples/yunmin`:
- Experiment A: `db/db_impl/db_impl_write.cc`
- Experiment B: `db/db_impl/db_impl_write.cc`
- Experiment C: `db/compaction/compaction_job.cc`

## Fitness Function
See `openevolve/aiopt/fitness.py`.

## Success Criteria
Not applicable to the current implementation.

## Limitations
Not applicable to the current implementation.
