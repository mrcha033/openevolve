#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: $0 experiment_a|experiment_b|experiment_c [--with-profilers]"
  echo ""
  echo "Runs the benchmark on unmodified RocksDB and writes baseline.json"
  echo "to the experiment directory."
  echo ""
  echo "Required env vars:"
  echo "  AI_OPT_ROCKSDB_PATH  - path to RocksDB source"
  echo "  AI_OPT_BENCH_CMD     - benchmark command"
  echo ""
  echo "Optional env vars:"
  echo "  AI_OPT_BUILD_CMD     - build command (run before benchmark)"
  echo "  AI_OPT_METRICS_JSON  - path to JSON metrics file (alternative to stdout parsing)"
  echo "  AI_OPT_BENCH_BIN     - binary for profiler runs"
  echo "  AI_OPT_BENCH_ARGS    - arguments for profiler runs"
  echo "  AI_OPT_BCOZ_DURATION - BCOZ profiling duration in seconds (default: 60)"
  echo "  AI_OPT_BPERF_DURATION - bperf profiling duration in seconds (default: 30)"
  echo "  AI_OPT_BCOZ_PROGRESS_POINTS - comma-separated BCOZ progress points"
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

EXP="$1"
WITH_PROFILERS=0
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-profilers) WITH_PROFILERS=1; shift ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
done

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
EXP_DIR="$BASE_DIR/$EXP"

if [[ ! -d "$EXP_DIR" ]]; then
  echo "Error: experiment folder not found: $EXP_DIR"
  exit 1
fi

ROCKSDB_PATH="${AI_OPT_ROCKSDB_PATH:?AI_OPT_ROCKSDB_PATH is required}"
BENCH_CMD="${AI_OPT_BENCH_CMD:?AI_OPT_BENCH_CMD is required}"
BUILD_CMD="${AI_OPT_BUILD_CMD:-}"
METRICS_JSON="${AI_OPT_METRICS_JSON:-}"

# Build if needed
if [[ -n "$BUILD_CMD" ]]; then
  echo "Building RocksDB..."
  (cd "$ROCKSDB_PATH" && eval "$BUILD_CMD")
fi

# Run benchmark
echo "Running baseline benchmark..."
BENCH_OUTPUT=$(cd "$ROCKSDB_PATH" && eval "$BENCH_CMD" 2>&1) || {
  echo "Benchmark failed:"
  echo "$BENCH_OUTPUT"
  exit 1
}

# Parse metrics using a small inline Python script that reuses the evaluator's logic
BASELINE_JSON=$(python3 -c "
import json, os, sys
sys.path.insert(0, '$EXP_DIR')
from evaluator import _parse_metrics

stdout = '''$BENCH_OUTPUT'''
metrics_path = '$METRICS_JSON' or None
metrics = _parse_metrics(stdout, metrics_path)
print(json.dumps(metrics))
") || {
  echo "Failed to parse metrics from benchmark output."
  echo "Benchmark stdout:"
  echo "$BENCH_OUTPUT"
  exit 1
}

echo "Parsed metrics: $BASELINE_JSON"

# Optionally run profilers for baseline values
PROFILER_JSON="{}"
if [[ "$WITH_PROFILERS" -eq 1 ]]; then
  BENCH_BIN="${AI_OPT_BENCH_BIN:-}"
  BENCH_ARGS="${AI_OPT_BENCH_ARGS:-}"
  BCOZ_DURATION="${AI_OPT_BCOZ_DURATION:-60}"
  BPERF_DURATION="${AI_OPT_BPERF_DURATION:-30}"
  PROGRESS_POINTS="${AI_OPT_BCOZ_PROGRESS_POINTS:-}"

  if [[ -z "$BENCH_BIN" ]]; then
    # Extract binary from BENCH_CMD
    BENCH_BIN=$(echo "$BENCH_CMD" | awk '{print $1}')
  fi

  PROFILER_JSON=$(python3 -c "
import json, sys, tempfile
from pathlib import Path

result = {}
profiler_dir = Path(tempfile.mkdtemp(prefix='aiopt_baseline_'))

try:
    from openevolve.aiopt.bcoz_parser import run_bcoz
    import shlex
    args = shlex.split('$BENCH_ARGS') if '$BENCH_ARGS' else []
    points = [p.strip() for p in '$PROGRESS_POINTS'.split(',') if p.strip()]
    bcoz = run_bcoz('$BENCH_BIN', args=args, duration_sec=$BCOZ_DURATION,
                    output_dir=profiler_dir, progress_points=points)
    result['bcoz_max_speedup'] = bcoz.max_speedup
    print('BCOZ max speedup: {:.1f}%'.format(bcoz.max_speedup), file=sys.stderr)
except Exception as e:
    print(f'BCOZ skipped: {e}', file=sys.stderr)

try:
    from openevolve.aiopt.bperf_parser import run_bperf
    import shlex
    args = shlex.split('$BENCH_ARGS') if '$BENCH_ARGS' else []
    bperf = run_bperf('$BENCH_BIN', args=args, duration_sec=$BPERF_DURATION,
                      output_dir=profiler_dir)
    result['off_cpu_ratio'] = bperf.off_cpu_ratio
    print('bperf off-CPU ratio: {:.1%}'.format(bperf.off_cpu_ratio), file=sys.stderr)
except Exception as e:
    print(f'bperf skipped: {e}', file=sys.stderr)

print(json.dumps(result))
") || {
    echo "Profiler run failed (non-fatal, writing metrics-only baseline)."
    PROFILER_JSON="{}"
  }
fi

# Merge metrics + profiler results and write baseline.json
OUTPUT="$EXP_DIR/baseline.json"
python3 -c "
import json
metrics = json.loads('$BASELINE_JSON')
profiler = json.loads('$PROFILER_JSON')
baseline = {**metrics, **profiler}
with open('$OUTPUT', 'w') as f:
    json.dump(baseline, f, indent=2)
print(json.dumps(baseline, indent=2))
"

echo ""
echo "Baseline written to: $OUTPUT"
