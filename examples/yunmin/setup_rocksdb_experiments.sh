#!/usr/bin/env bash
# Setup RocksDB experiments by extracting target .cc files as initial_program.cpp
# with EVOLVE-BLOCK markers around the target function(s).
#
# Usage:
#   bash setup_rocksdb_experiments.sh /path/to/rocksdb [experiment_a|experiment_b|experiment_c|all]
#
# This script:
#   1. Copies the target .cc file from the RocksDB source tree
#   2. Inserts // EVOLVE-BLOCK-START / // EVOLVE-BLOCK-END markers around the target function(s)
#   3. Rebuilds RocksDB in release mode (DEBUG_LEVEL=0)
#   4. Runs a quick baseline benchmark to populate baseline.json
#
# Prerequisites:
#   - RocksDB source tree with db_bench already built (or buildable)
#   - The experiment directories (experiment_a, experiment_b, experiment_c) must exist

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 /path/to/rocksdb [experiment_a|experiment_b|experiment_c|all]"
    echo ""
    echo "If no experiment is specified, runs for all three."
    exit 1
fi

ROCKSDB_DIR="$1"
EXPERIMENT="${2:-all}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NPROC=$(nproc 2>/dev/null || echo 4)

if [[ ! -d "$ROCKSDB_DIR" ]]; then
    echo "Error: RocksDB directory not found: $ROCKSDB_DIR"
    exit 1
fi

# --- Ensure release build ---
echo "=== Ensuring release build (DEBUG_LEVEL=0) ==="
cd "$ROCKSDB_DIR"
DEBUG_LEVEL=0 make -j"$NPROC" db_bench 2>&1 | tail -5
echo ""

# --- Helper: insert EVOLVE-BLOCK markers around a function ---
# Usage: insert_markers <source_file> <output_file> <function_signature_pattern> [end_pattern]
#
# This finds the function definition matching the pattern and wraps it with markers.
# If end_pattern is not given, it finds the matching closing brace.
insert_markers() {
    local src="$1"
    local out="$2"
    local start_pattern="$3"
    local end_pattern="${4:-}"

    if [[ ! -f "$src" ]]; then
        echo "Error: source file not found: $src"
        return 1
    fi

    python3 << 'PYEOF' "$src" "$out" "$start_pattern" "$end_pattern"
import sys, re

src_path, out_path, start_pat, end_pat = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with open(src_path, 'r') as f:
    lines = f.readlines()

# Find the function start line
start_line = None
for i, line in enumerate(lines):
    if re.search(start_pat, line):
        start_line = i
        break

if start_line is None:
    print(f"Warning: pattern '{start_pat}' not found in {src_path}", file=sys.stderr)
    print(f"Copying file without markers. You will need to add them manually.", file=sys.stderr)
    with open(out_path, 'w') as f:
        f.writelines(lines)
    sys.exit(0)

# Find the function end (matching brace)
if end_pat:
    end_line = None
    for i in range(start_line + 1, len(lines)):
        if re.search(end_pat, lines[i]):
            end_line = i
            break
    if end_line is None:
        print(f"Warning: end pattern '{end_pat}' not found after line {start_line}", file=sys.stderr)
        end_line = start_line + 50  # fallback
else:
    # Find matching closing brace by tracking brace depth
    depth = 0
    found_open = False
    end_line = start_line
    for i in range(start_line, len(lines)):
        for ch in lines[i]:
            if ch == '{':
                depth += 1
                found_open = True
            elif ch == '}':
                depth -= 1
                if found_open and depth == 0:
                    end_line = i
                    break
        if found_open and depth == 0:
            break

# Insert markers
result = []
result.extend(lines[:start_line])
result.append('// EVOLVE-BLOCK-START\n')
result.extend(lines[start_line:end_line + 1])
result.append('// EVOLVE-BLOCK-END\n')
result.extend(lines[end_line + 1:])

with open(out_path, 'w') as f:
    f.writelines(result)

block_lines = end_line - start_line + 1
print(f"Inserted markers around lines {start_line + 1}-{end_line + 1} ({block_lines} lines)")
PYEOF
}

# --- Experiment A: WAL write path ---
setup_experiment_a() {
    local exp_dir="$SCRIPT_DIR/experiment_a"
    local target_file="db/db_impl/db_impl_write.cc"
    local src="$ROCKSDB_DIR/$target_file"
    local out="$exp_dir/initial_program.cpp"

    echo "=== Setting up experiment_a: WAL write path ==="
    echo "    Source: $src"
    echo "    Target: $out"

    if [[ ! -f "$src" ]]; then
        echo "Error: $src not found"
        return 1
    fi

    echo "    File size: $(wc -l < "$src") lines"

    # Target function: DBImpl::WriteImpl — the main write entry point
    # This is typically the hottest function in the write path
    insert_markers "$src" "$out" "DBImpl::WriteImpl"

    echo "    Created: $out ($(wc -l < "$out") lines)"
    echo ""
}

# --- Experiment B: Mutex contention ---
setup_experiment_b() {
    local exp_dir="$SCRIPT_DIR/experiment_b"
    local target_file="db/db_impl/db_impl_write.cc"
    local src="$ROCKSDB_DIR/$target_file"
    local out="$exp_dir/initial_program.cpp"

    echo "=== Setting up experiment_b: Mutex contention ==="
    echo "    Source: $src"
    echo "    Target: $out"

    if [[ ! -f "$src" ]]; then
        echo "Error: $src not found"
        return 1
    fi

    echo "    File size: $(wc -l < "$src") lines"

    # Target function: DBImpl::WriteToWAL — where WAL sync contention occurs
    insert_markers "$src" "$out" "DBImpl::WriteToWAL"

    echo "    Created: $out ($(wc -l < "$out") lines)"
    echo ""
}

# --- Experiment C: Compaction ---
setup_experiment_c() {
    local exp_dir="$SCRIPT_DIR/experiment_c"
    local target_file="db/compaction/compaction_job.cc"
    local src="$ROCKSDB_DIR/$target_file"
    local out="$exp_dir/initial_program.cpp"

    echo "=== Setting up experiment_c: Compaction ==="
    echo "    Source: $src"
    echo "    Target: $out"

    if [[ ! -f "$src" ]]; then
        echo "Error: $src not found"
        return 1
    fi

    echo "    File size: $(wc -l < "$src") lines"

    # Target function: CompactionJob::ProcessKeyValueCompaction — inner compaction loop
    insert_markers "$src" "$out" "CompactionJob::ProcessKeyValueCompaction"

    echo "    Created: $out ($(wc -l < "$out") lines)"
    echo ""
}

# --- Run setup ---
case "$EXPERIMENT" in
    experiment_a) setup_experiment_a ;;
    experiment_b) setup_experiment_b ;;
    experiment_c) setup_experiment_c ;;
    all)
        setup_experiment_a
        setup_experiment_b
        setup_experiment_c
        ;;
    *)
        echo "Unknown experiment: $EXPERIMENT"
        echo "Expected: experiment_a, experiment_b, experiment_c, or all"
        exit 1
        ;;
esac

# --- Summary ---
echo "========================================="
echo " Setup Complete"
echo "========================================="
echo ""
echo "Created initial_program.cpp files with EVOLVE-BLOCK markers."
echo ""
echo "IMPORTANT: Review the EVOLVE-BLOCK placement in each file!"
echo "  The script targeted these functions:"
echo "    experiment_a: DBImpl::WriteImpl"
echo "    experiment_b: DBImpl::WriteToWAL"
echo "    experiment_c: CompactionJob::ProcessKeyValueCompaction"
echo ""
echo "You may want to adjust the markers to cover more/fewer lines."
echo "The LLM will ONLY modify code between the markers."
echo ""
echo "Next steps:"
echo "  1. Review each initial_program.cpp and adjust EVOLVE-BLOCK if needed"
echo "  2. Run baseline capture:"
echo "     export AI_OPT_ROCKSDB_PATH=$ROCKSDB_DIR"
echo "     export AI_OPT_BUILD_CMD='DEBUG_LEVEL=0 make -j$NPROC db_bench'"
echo "     export AI_OPT_BENCH_CMD='./db_bench --benchmarks=fillrandom --num=1000000 --threads=8 --histogram'"
echo "     ./capture_baseline.sh experiment_a"
echo "  3. Run experiments:"
echo "     AI_OPT_TRACK=baseline ./run_track.sh experiment_a"
echo "========================================="
