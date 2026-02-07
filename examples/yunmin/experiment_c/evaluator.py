import importlib.util
import json
import os
import shlex
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import subprocess

from openevolve.utils.code_utils import apply_diff


EXPERIMENT_NAME = "experiment_c"
DEFAULT_TARGET_FILE = "db/compaction/compaction_job.cc"
DEFAULT_RUN_BCOZ = False
DEFAULT_RUN_BPERF = True

ROOT = Path(__file__).resolve().parent
BASELINE_FILE = ROOT / "baseline.json"
DOCS_SRC = ROOT.parents[2] / "docs_for_aiopt" / "src"

sys.path.insert(0, str(DOCS_SRC))
try:
    from bcoz_parser import run_bcoz  # noqa: E402
except Exception:
    run_bcoz = None  # type: ignore
try:
    from bperf_parser import run_bperf  # noqa: E402
except Exception:
    run_bperf = None  # type: ignore
from fitness import Baseline, MutationResult, causal_fitness, fast_fitness  # noqa: E402


def _load_program(program_path: str):
    spec = importlib.util.spec_from_file_location("evolve_program", program_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load program spec.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    ops = None
    p99 = None
    for line in stdout.splitlines():
        if ops is None:
            if "ops/sec" in line:
                tokens = line.replace(",", " ").split()
                for i, tok in enumerate(tokens):
                    if "ops/sec" in tok and i > 0:
                        try:
                            ops = float(tokens[i - 1])
                        except ValueError:
                            pass
        if p99 is None:
            lowered = line.lower()
            if "p99" in lowered:
                numbers = [t for t in lowered.replace(",", " ").split() if t.replace(".", "").isdigit()]
                if numbers:
                    p99 = float(numbers[-1])

    if ops is None or p99 is None:
        raise RuntimeError("Failed to parse ops/sec or p99 from benchmark output.")

    return {"ops_per_sec": ops, "p99_latency_us": p99}


def _split_command(cmd: str) -> Tuple[str, List[str]]:
    parts = shlex.split(cmd)
    if not parts:
        raise RuntimeError("Empty command string.")
    return parts[0], parts[1:]


def evaluate(program_path: str) -> dict:
    try:
        module = _load_program(program_path)
        diff_text = getattr(module, "MUTATION_DIFF", "")
        if not isinstance(diff_text, str) or not diff_text.strip():
            return {"combined_score": 0.0, "error": "Empty MUTATION_DIFF string."}
    except Exception as exc:
        return {"combined_score": 0.0, "error": f"Load failed: {exc}"}

    rocksb_path = os.getenv("AI_OPT_ROCKSDB_PATH")
    if not rocksb_path:
        return {"combined_score": 0.0, "error": "AI_OPT_ROCKSDB_PATH is required."}

    baseline = _load_baseline()
    _set_baseline(baseline)

    target_files_env = os.getenv("AI_OPT_TARGET_FILES")
    if target_files_env:
        target_files = [Path(rocksb_path) / p.strip() for p in target_files_env.split(",") if p.strip()]
    else:
        target_file = os.getenv("AI_OPT_TARGET_FILE", DEFAULT_TARGET_FILE)
        target_files = [Path(rocksb_path) / target_file]

    build_cmd = os.getenv("AI_OPT_BUILD_CMD")
    bench_cmd = os.getenv("AI_OPT_BENCH_CMD")
    if not bench_cmd:
        return {"combined_score": 0.0, "error": "AI_OPT_BENCH_CMD is required."}

    run_bcoz_flag = os.getenv("AI_OPT_RUN_BCOZ")
    run_bperf_flag = os.getenv("AI_OPT_RUN_BPERF")
    run_bcoz_enabled = DEFAULT_RUN_BCOZ if run_bcoz_flag is None else run_bcoz_flag == "1"
    run_bperf_enabled = DEFAULT_RUN_BPERF if run_bperf_flag is None else run_bperf_flag == "1"

    if run_bcoz_enabled and run_bcoz is None:
        return {"combined_score": 0.0, "error": "bcoz_parser unavailable (disable AI_OPT_RUN_BCOZ or install parser)."}
    if run_bperf_enabled and run_bperf is None:
        return {"combined_score": 0.0, "error": "bperf_parser unavailable (disable AI_OPT_RUN_BPERF or install parser)."}

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

    applied_path = None
    original_text = None

    try:
        for path in target_files:
            if not path.exists():
                return {"combined_score": 0.0, "error": f"Target file missing: {path}"}

        for path in target_files:
            original_text = path.read_text(encoding="utf-8")
            updated = apply_diff(original_text, diff_text)
            if updated != original_text:
                path.write_text(updated, encoding="utf-8")
                applied_path = path
                break

        if applied_path is None:
            return {"combined_score": 0.0, "error": "Diff did not apply to any target file."}

        if build_cmd:
            build_result = subprocess.run(
                build_cmd,
                shell=True,
                cwd=rocksb_path,
                capture_output=True,
                text=True,
            )
            if build_result.returncode != 0:
                return {
                    "combined_score": 0.0,
                    "error": build_result.stderr.strip() or "Build failed.",
                }

        bench_result = subprocess.run(
            bench_cmd,
            shell=True,
            cwd=rocksb_path,
            capture_output=True,
            text=True,
        )
        if bench_result.returncode != 0:
            return {
                "combined_score": 0.0,
                "error": bench_result.stderr.strip() or "Benchmark failed.",
            }

        metrics = _parse_metrics(bench_result.stdout, metrics_json)
        bcoz_result = None
        bperf_result = None

        if run_bcoz_enabled:
            bcoz_result = run_bcoz(
                bin_path,
                args=args,
                duration_sec=bcoz_duration,
                output_dir=Path("/tmp"),
                progress_points=progress_list,
            )

        if run_bperf_enabled:
            bperf_result = run_bperf(
                bin_path,
                args=args,
                duration_sec=bperf_duration,
                output_dir=Path("/tmp"),
            )

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
        }
        if bcoz_result:
            response["bcoz_max_speedup"] = bcoz_result.max_speedup
            response["bcoz_max_speedup_location"] = bcoz_result.max_speedup_location
        if bperf_result:
            response["bperf_offcpu_ratio"] = bperf_result.off_cpu_ratio

        return response

    except Exception as exc:
        return {"combined_score": 0.0, "error": f"{EXPERIMENT_NAME} failed: {exc}"}

    finally:
        if applied_path and original_text is not None:
            applied_path.write_text(original_text, encoding="utf-8")
