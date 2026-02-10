import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from openevolve.aiopt.fitness import Baseline, MutationResult, causal_fitness, fast_fitness
from openevolve.evaluation_result import EvaluationResult

try:
    from openevolve.aiopt.bcoz_parser import run_bcoz, generate_mutation_context as bcoz_context
except Exception:
    run_bcoz = None
    bcoz_context = None

try:
    from openevolve.aiopt.bperf_parser import run_bperf, generate_mutation_context as bperf_context
except Exception:
    run_bperf = None
    bperf_context = None

try:
    from openevolve.aiopt.hw_counter_context import generate_hw_context
except Exception:
    generate_hw_context = None


EXPERIMENT_NAME = "experiment_b"
DEFAULT_TARGET_FILE = "db/db_impl/db_impl_write.cc"
DEFAULT_RUN_BCOZ = True
DEFAULT_RUN_BPERF = True

ROOT = Path(__file__).resolve().parent
BASELINE_FILE = ROOT / "baseline.json"

BUILD_TIMEOUT = 600  # 10 minutes
BENCH_TIMEOUT = 300  # 5 minutes

SLICE_START_MARKER = "// EVOLVE-BLOCK-START"
SLICE_END_MARKER = "// EVOLVE-BLOCK-END"
TEMPLATE_FILE = ROOT / "full_source_template.cpp"


def _load_baseline() -> dict:
    if BASELINE_FILE.exists():
        with BASELINE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "ops_per_sec": 100000.0,
        "p99_latency_us": 500.0,
        "off_cpu_ratio": 0.25,
        "bcoz_max_speedup": 15.0,
    }


def _set_baseline(baseline: dict) -> None:
    Baseline.THROUGHPUT_OPS_SEC = float(baseline.get("ops_per_sec", 100000.0))
    Baseline.P99_LATENCY_US = float(baseline.get("p99_latency_us", 500.0))
    Baseline.OFF_CPU_RATIO = float(baseline.get("off_cpu_ratio", 0.25))
    Baseline.BCOZ_MAX_SPEEDUP = float(baseline.get("bcoz_max_speedup", 15.0))


def _parse_metrics(stdout: str, metrics_path: Optional[str]) -> dict:
    if metrics_path:
        path = Path(metrics_path)
        if not path.is_absolute():
            path = Path(os.getcwd()) / path
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "ops_per_sec": float(data["ops_per_sec"]),
                    "p99_latency_us": float(data["p99_latency_us"]),
                }

    ops_candidates: list[float] = []
    p99 = None
    for line in stdout.splitlines():
        if "ops/sec" in line:
            tokens = line.replace(",", " ").split()
            for i, tok in enumerate(tokens):
                if "ops/sec" in tok and i > 0:
                    try:
                        ops_candidates.append(float(tokens[i - 1]))
                    except ValueError:
                        pass
        if p99 is None and "P99:" in line:
            parts = line.split("P99:")
            if len(parts) > 1:
                tail = parts[1].strip()
                num = tail.split()[0]
                try:
                    p99 = float(num)
                except ValueError:
                    pass

    ops = max(ops_candidates) if ops_candidates else None

    if ops is None or p99 is None:
        raise RuntimeError("Failed to parse ops/sec or p99 from benchmark output.")

    return {"ops_per_sec": ops, "p99_latency_us": p99}


def _split_command(cmd: str) -> Tuple[str, List[str]]:
    parts = shlex.split(cmd)
    if not parts:
        raise RuntimeError("Empty command string.")
    return parts[0], parts[1:]


def _reassemble_source(template: str, evolved_slice: str) -> str:
    """Replace the EVOLVE-BLOCK region in the template with the evolved slice.

    The evolved_slice is expected to include EVOLVE-BLOCK-START/END markers.
    This function finds the corresponding markers in the template and replaces
    that entire region (markers inclusive) with the evolved slice.
    """
    lines = template.split("\n")
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if SLICE_START_MARKER in line and start_idx is None:
            start_idx = i
        if SLICE_END_MARKER in line:
            end_idx = i
    if start_idx is None or end_idx is None:
        raise RuntimeError(
            "EVOLVE-BLOCK markers not found in full_source_template.cpp"
        )
    before = lines[:start_idx]
    after = lines[end_idx + 1:]
    reassembled_lines = before + evolved_slice.rstrip("\n").split("\n") + after
    return "\n".join(reassembled_lines)


def evaluate(program_path: str) -> dict:
    """Evaluate a function slice of a RocksDB .cc file.

    program_path: path to the evolved function slice (EVOLVE-BLOCK region only).
    The evaluator reads the full source template, patches in the evolved slice,
    copies the reassembled file into the RocksDB source tree, rebuilds,
    benchmarks, and restores the original file.
    """
    rocksdb_path = os.getenv("AI_OPT_ROCKSDB_PATH")
    if not rocksdb_path:
        return {"combined_score": 0.0, "error": "AI_OPT_ROCKSDB_PATH is required."}

    baseline = _load_baseline()
    _set_baseline(baseline)

    target_file = os.getenv("AI_OPT_TARGET_FILE", DEFAULT_TARGET_FILE)
    target_path = Path(rocksdb_path) / target_file

    build_cmd = os.getenv("AI_OPT_BUILD_CMD")
    bench_cmd = os.getenv("AI_OPT_BENCH_CMD")
    if not bench_cmd:
        return {"combined_score": 0.0, "error": "AI_OPT_BENCH_CMD is required."}

    run_bcoz_flag = os.getenv("AI_OPT_RUN_BCOZ")
    run_bperf_flag = os.getenv("AI_OPT_RUN_BPERF")
    run_bcoz_enabled = DEFAULT_RUN_BCOZ if run_bcoz_flag is None else run_bcoz_flag == "1"
    run_bperf_enabled = DEFAULT_RUN_BPERF if run_bperf_flag is None else run_bperf_flag == "1"

    bench_bin = os.getenv("AI_OPT_BENCH_BIN")
    bench_args = os.getenv("AI_OPT_BENCH_ARGS")
    if bench_bin:
        bin_path = bench_bin
        args = shlex.split(bench_args) if bench_args else []
    else:
        bin_path, args = _split_command(bench_cmd)

    metrics_json = os.getenv("AI_OPT_METRICS_JSON")
    bcoz_duration = int(os.getenv("AI_OPT_BCOZ_DURATION", "60"))
    bperf_duration = int(os.getenv("AI_OPT_BPERF_DURATION", "30"))
    progress_points = os.getenv("AI_OPT_BCOZ_PROGRESS_POINTS")
    progress_list = [p.strip() for p in progress_points.split(",")] if progress_points else []

    original_text = None

    try:
        if not target_path.exists():
            return {"combined_score": 0.0, "error": f"Target file missing: {target_path}"}

        # Function-slice reassembly: read the evolved slice and patch it
        # into the full source template before compiling.
        original_text = target_path.read_text(encoding="utf-8")
        evolved_slice = Path(program_path).read_text(encoding="utf-8")
        template_text = TEMPLATE_FILE.read_text(encoding="utf-8")
        reassembled = _reassemble_source(template_text, evolved_slice)
        target_path.write_text(reassembled, encoding="utf-8")

        # Incremental build
        if build_cmd:
            build_result = subprocess.run(
                build_cmd,
                shell=True,
                cwd=rocksdb_path,
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT,
            )
            if build_result.returncode != 0:
                return {
                    "combined_score": 0.0,
                    "error": build_result.stderr.strip() or "Build failed.",
                }

        # Run benchmark
        bench_result = subprocess.run(
            bench_cmd,
            shell=True,
            cwd=rocksdb_path,
            capture_output=True,
            text=True,
            timeout=BENCH_TIMEOUT,
        )
        if bench_result.returncode != 0:
            return {
                "combined_score": 0.0,
                "error": bench_result.stderr.strip() or "Benchmark failed.",
            }

        metrics = _parse_metrics(bench_result.stdout, metrics_json)

        # Profiler runs (wrapped in try/except for graceful fallback)
        bcoz_result = None
        bperf_result = None
        profiler_dir = Path(tempfile.mkdtemp(prefix="aiopt_"))

        if run_bcoz_enabled and run_bcoz is not None:
            try:
                bcoz_result = run_bcoz(
                    bin_path,
                    args=args,
                    duration_sec=bcoz_duration,
                    output_dir=profiler_dir,
                    progress_points=progress_list,
                )
            except Exception:
                bcoz_result = None

        if run_bperf_enabled and run_bperf is not None:
            try:
                bperf_result = run_bperf(
                    bin_path,
                    args=args,
                    duration_sec=bperf_duration,
                    output_dir=profiler_dir,
                )
            except Exception:
                bperf_result = None

        result = MutationResult(
            mutation_id="iteration",
            compiled=True,
            tests_passed=True,
            throughput_ops_sec=metrics["ops_per_sec"],
            p99_latency_us=metrics["p99_latency_us"],
            bperf=bperf_result,
            bcoz=bcoz_result,
        )

        score = causal_fitness(result) if (bcoz_result or bperf_result) else fast_fitness(result)

        response = {
            "combined_score": score,
            "ops_per_sec": metrics["ops_per_sec"],
            "p99_latency_us": metrics["p99_latency_us"],
            "bcoz_max_speedup": Baseline.BCOZ_MAX_SPEEDUP,
            "bperf_offcpu_ratio": Baseline.OFF_CPU_RATIO,
        }

        if bcoz_result:
            response["bcoz_max_speedup"] = bcoz_result.max_speedup
            response["bcoz_max_speedup_location"] = bcoz_result.max_speedup_location
        if bperf_result:
            response["bperf_offcpu_ratio"] = bperf_result.off_cpu_ratio

        artifacts = {}
        if bcoz_result and bcoz_context:
            artifacts["profiler_bcoz"] = bcoz_context(bcoz_result)
        if bperf_result and bperf_context:
            artifacts["profiler_bperf"] = bperf_context(bperf_result)
        if generate_hw_context:
            hw_ctx = generate_hw_context(metrics)
            if hw_ctx:
                artifacts["profiler_hw_counters"] = hw_ctx

        if artifacts:
            return EvaluationResult(metrics=response, artifacts=artifacts)
        return response

    except Exception as exc:
        return {"combined_score": 0.0, "error": f"{EXPERIMENT_NAME} failed: {exc}"}

    finally:
        if original_text is not None:
            target_path.write_text(original_text, encoding="utf-8")
