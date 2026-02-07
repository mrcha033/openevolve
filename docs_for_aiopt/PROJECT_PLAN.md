# PROJECT_PLAN: AIOpt (CSLab Research)
Status: Blocked (SSH ProxyJump Down)

## Objectives
1.  Optimize RocksDB performance using C++ kernel mutation.
2.  Use BCOZ speedup predictions to guide evolutionary mutations via OpenEvolve.
3.  Target: CSLab Server (165.132.141.223).

## Technical Requirements
-   **Environment:** Ubuntu 24.04, Kernel 6.17.
-   **Tools:** `bperf`, `BCOZ`, `coz` (verified working on server).
-   **Build:** Custom `gflags` in `~/local` (no sudo).

## Current Status
-   **SSH ProxyJump:** 192.168.0.4 (Windows host) is currently timed out/down.
-   **RocksDB Setup:** Pending environment access.

## Next Milestones
1. [ ] Restore SSH access to `cslab-server`.
2. [x] **Experiment B/C Prompt Templates:** Drafted Lock Contention and Coroutinization prompts (2026-02-05).
3. [x] **Experiment D Design:** Local RocksDB-Lite prototyping plan for SSH-independent validation (2026-02-05).
4. [x] **Profiler-in-the-Loop Architecture:** Designed BCOZ/bperf integration into OpenEvolve fitness loop (2026-02-05).
5. [x] **Core Implementation:** `bperf_parser.py`, `bcoz_parser.py`, `fitness.py` created in `src/` (2026-02-05).
6. [ ] Execute Experiment D locally (RPi or Mac) to validate OpenEvolve pipeline.
7. [ ] Initialize containerized environment (Ubuntu 20.04/24.04) if local prototyping is needed.
8. [ ] Verify RocksDB build with local `gflags`.
9. [ ] Execute initial BCOZ profiling on baseline RocksDB (requires server).
10. [ ] Implement first round of C++ kernel mutations via OpenEvolve.

## Experiment Design & Critical Review
- **Bottleneck-Aware Experimentation:** The primary goal is designing experiments that leverage `bperf` and `BCOZ` context.
- **Hypothesis-Driven Mutation:** Move from general tuning to specific, BCOZ-guided code refactoring.
- **Reference:** See `memory/projects/cslab/aiopt/research/AIOpt_Critical_Review.md` for the full audit and design strategy.

## Alternative Optimization Paths (Blocked Context)
- **Local Simulation (RocksDB-Lite):** Prototype mutations on a scaled-down RocksDB instance on the RPi/Mac to test `OpenEvolve` logic before server deployment.
- **Coroutinization Analysis:** Investigate the 2023 "coroutine program" approach to RocksDB (200 lines of code rewrite) as a potential mutation template for CPU optimization.
- **Genetic Configuration Tuning (K2vTune):** Adapt `K2vTune` (2023) genetic algorithm concepts for automated RocksDB configuration tuning in parallel with kernel mutations.
- **TiKV Multi-Batch Integration:** Model the "Shared LSM" flow control from TiKV (2025) as a higher-level structural mutation target.
