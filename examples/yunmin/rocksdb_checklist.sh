#!/usr/bin/env bash
# RocksDB Experiment Setup Checklist
# Run this on the L40s server to gather info needed for experiment design.
# Usage: bash rocksdb_checklist.sh [/path/to/rocksdb]

set -e

ROCKSDB_DIR="${1:-$HOME/rocksdb}"

echo "========================================"
echo " RocksDB Experiment Setup Checklist"
echo "========================================"
echo ""

# --- Step 1: Clone if needed ---
if [ ! -d "$ROCKSDB_DIR" ]; then
    echo "[1/7] RocksDB not found at $ROCKSDB_DIR"
    echo "      Clone it with:"
    echo "        git clone https://github.com/facebook/rocksdb.git $ROCKSDB_DIR"
    echo ""
    echo "      Then re-run this script."
    exit 1
else
    echo "[1/7] RocksDB found at $ROCKSDB_DIR"
    cd "$ROCKSDB_DIR"
    echo "      Branch: $(git rev-parse --abbrev-ref HEAD)"
    echo "      Commit: $(git rev-parse --short HEAD) ($(git log -1 --format='%s'))"
    echo "      Date:   $(git log -1 --format='%ci')"
fi
echo ""

# --- Step 2: Check build tools ---
echo "[2/7] Build tools"
echo "      make:  $(which make 2>/dev/null && make --version | head -1 || echo 'NOT FOUND')"
echo "      g++:   $(which g++ 2>/dev/null && g++ --version | head -1 || echo 'NOT FOUND')"
echo "      cmake: $(which cmake 2>/dev/null && cmake --version | head -1 || echo 'NOT FOUND')"
echo "      nproc: $(nproc 2>/dev/null || echo 'N/A')"
echo ""

# --- Step 3: Full build ---
echo "[3/7] Full build (this may take a few minutes)..."
echo "      Building db_bench with make -j$(nproc) db_bench"
BUILD_START=$(date +%s)
make -j"$(nproc)" db_bench 2>&1 | tail -3
BUILD_END=$(date +%s)
FULL_BUILD_TIME=$((BUILD_END - BUILD_START))
echo "      Full build time: ${FULL_BUILD_TIME}s"
echo ""

# --- Step 4: Incremental build time ---
echo "[4/7] Incremental build timing (touch db/db_impl_write.cc, rebuild)..."
touch db/db_impl_write.cc
INCR_START=$(date +%s)
make -j"$(nproc)" db_bench 2>&1 | tail -3
INCR_END=$(date +%s)
INCR_BUILD_TIME=$((INCR_END - INCR_START))
echo "      Incremental build time: ${INCR_BUILD_TIME}s"
echo ""

# --- Step 5: Quick benchmark test ---
echo "[5/7] Quick benchmark test (fillrandom, 100K ops)..."
BENCH_START=$(date +%s)
./db_bench --benchmarks=fillrandom --num=100000 --threads=1 \
    --db=/tmp/rocksdb_checklist_bench --wal_dir=/tmp/rocksdb_checklist_wal \
    2>&1 | grep -E "^fillrandom|ops/sec"
BENCH_END=$(date +%s)
BENCH_TIME=$((BENCH_END - BENCH_START))
echo "      Benchmark time: ${BENCH_TIME}s"
rm -rf /tmp/rocksdb_checklist_bench /tmp/rocksdb_checklist_wal
echo ""

# --- Step 6: Target file sizes ---
echo "[6/7] Target file sizes (lines of code)"
for f in db/db_impl_write.cc db/db_impl_compaction_flush.cc db/compaction/compaction_job.cc; do
    if [ -f "$f" ]; then
        echo "      $f: $(wc -l < "$f") lines"
    else
        echo "      $f: NOT FOUND"
    fi
done
echo ""

# --- Step 7: Candidate functions for EVOLVE-BLOCK ---
echo "[7/7] Key functions in target files"
echo ""
echo "  --- db/db_impl_write.cc ---"
grep -n "^Status\|^void\|^bool\|^int\|^uint" db/db_impl_write.cc 2>/dev/null | \
    grep -i "DBImpl::" | head -20
echo ""
echo "  --- db/compaction/compaction_job.cc ---"
grep -n "^Status\|^void\|^bool\|^int\|^uint" db/compaction/compaction_job.cc 2>/dev/null | \
    grep -i "CompactionJob::" | head -20
echo ""

# --- Summary ---
echo "========================================"
echo " Summary"
echo "========================================"
echo " RocksDB dir:       $ROCKSDB_DIR"
echo " Full build:        ${FULL_BUILD_TIME}s"
echo " Incremental build: ${INCR_BUILD_TIME}s"
echo " Benchmark (100K):  ${BENCH_TIME}s"
echo " Total eval time:   ~$((INCR_BUILD_TIME + BENCH_TIME))s per iteration"
echo ""
echo " Next steps:"
echo " 1. Pick benchmark params (--num, --threads, --benchmarks)"
echo " 2. For each experiment, pick function(s) to wrap in EVOLVE-BLOCK"
echo " 3. Copy target .cc files as initial_program.cc with markers"
echo " 4. Share this output so we can generate evaluators"
echo "========================================"
