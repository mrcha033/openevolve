# Experiment D: Local RocksDB-Lite Prototyping (SSH-Independent)

## Objective
Validate OpenEvolve mutation logic on a scaled-down RocksDB instance without requiring CSLab server access. This allows prompt engineering and evolutionary logic testing to proceed in parallel with SSH restoration.

## Environment
- **Host:** Raspberry Pi 4 (arm64) or MacBook Air M3 (arm64)
- **Target:** RocksDB-Lite (reduced feature set, lower resource footprint)
- **Build:** CMake with `-DROCKSDB_LITE=ON -DWITH_TESTS=OFF`

## Scope
This experiment does **not** aim for production-grade performance results. It validates:
1. **Prompt → Mutation → Compile → Test** pipeline
2. **OpenEvolve integration** with RocksDB source tree
3. **Fitness function design** (throughput, latency, error rate)

## Setup Steps
1. Clone RocksDB: `git clone https://github.com/facebook/rocksdb.git --depth 1`
2. Build RocksDB-Lite:
   ```bash
   cd rocksdb
   mkdir build && cd build
   cmake .. -DROCKSDB_LITE=ON -DWITH_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
   make -j4 db_bench
   ```
3. Baseline benchmark:
   ```bash
   ./db_bench --benchmarks=fillseq,readrandom --num=100000
   ```
4. Link OpenEvolve to mutation target (`db/db_impl/db_impl_write.cc`)

## Mutation Targets (Lite-Compatible)
- **WAL Sync Path:** Same as Experiment A, but with reduced write volume
- **MemTable Insertion:** Optimize skip-list insertion logic
- **Block Cache:** Tune LRU eviction heuristics

## Fitness Function
```python
def fitness(mutation_result):
    throughput = mutation_result['ops_per_sec']
    latency_p99 = mutation_result['p99_latency_us']
    compile_success = mutation_result['compiled']
    test_pass = mutation_result['tests_passed']
    
    if not compile_success or not test_pass:
        return 0.0
    
    # Weighted: 70% throughput, 30% latency (lower is better)
    return 0.7 * (throughput / baseline_throughput) + 0.3 * (baseline_p99 / latency_p99)
```

## Success Criteria
- Pipeline runs end-to-end on local hardware
- At least 3 mutation iterations complete without manual intervention
- Fitness function correctly ranks mutations

## Limitations
- No BCOZ/bperf data (requires Linux perf subsystem with PMU access)
- Reduced workload may not expose real bottlenecks
- Results are directional, not publishable
