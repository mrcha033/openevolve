import json
import os
import subprocess
import tempfile
from pathlib import Path

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


EXPERIMENT_NAME = "sieve"
ROOT = Path(__file__).resolve().parent
BASELINE_FILE = ROOT / "baseline.json"

DEFAULT_RUN_BCOZ = True
DEFAULT_RUN_BPERF = True


def _load_baseline() -> dict:
    if BASELINE_FILE.exists():
        with BASELINE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "ops_per_sec": 50.0,
        "p99_latency_us": 20000.0,
        "off_cpu_ratio": 0.02,
        "bcoz_max_speedup": 5.0,
    }


def _set_baseline(baseline: dict) -> None:
    Baseline.THROUGHPUT_OPS_SEC = float(baseline.get("ops_per_sec", 50.0))
    Baseline.P99_LATENCY_US = float(baseline.get("p99_latency_us", 20000.0))
    Baseline.OFF_CPU_RATIO = float(baseline.get("off_cpu_ratio", 0.02))
    Baseline.BCOZ_MAX_SPEEDUP = float(baseline.get("bcoz_max_speedup", 5.0))


def _compile(program_path: str, out_path: Path) -> None:
    build_cmd = os.getenv("AI_OPT_BUILD_CMD")
    if build_cmd:
        subprocess.run(build_cmd, shell=True, check=True, cwd=str(ROOT))
        return
    cmd = [
        "g++",
        "-O3",
        "-g",
        "-std=c++17",
        "-DNDEBUG",
        program_path,
        "-o",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "compile failed")


def _run_bench(bin_path: str, metrics_path: Path) -> dict:
    cmd = [bin_path, "--json", str(metrics_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "bench failed")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def evaluate(program_path: str) -> dict:
    baseline = _load_baseline()
    _set_baseline(baseline)

    run_bcoz_flag = os.getenv("AI_OPT_RUN_BCOZ")
    run_bperf_flag = os.getenv("AI_OPT_RUN_BPERF")
    run_bcoz_enabled = DEFAULT_RUN_BCOZ if run_bcoz_flag is None else run_bcoz_flag == "1"
    run_bperf_enabled = DEFAULT_RUN_BPERF if run_bperf_flag is None else run_bperf_flag == "1"

    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="aiopt_sieve_"))
        bin_path = tmp_dir / "bench_bin"
        _compile(program_path, bin_path)

        metrics_path = tmp_dir / "metrics.json"
        metrics = _run_bench(str(bin_path), metrics_path)

        bcoz_result = None
        bperf_result = None
        profiler_dir = Path(tempfile.mkdtemp(prefix="aiopt_profiler_"))

        if run_bcoz_enabled and run_bcoz is not None:
            try:
                bcoz_result = run_bcoz(
                    str(bin_path),
                    args=["--json", str(metrics_path)],
                    duration_sec=int(os.getenv("AI_OPT_BCOZ_DURATION", "30")),
                    output_dir=profiler_dir,
                    progress_points=[],
                )
            except Exception:
                bcoz_result = None

        if run_bperf_enabled and run_bperf is not None:
            try:
                bperf_result = run_bperf(
                    str(bin_path),
                    args=["--json", str(metrics_path)],
                    duration_sec=int(os.getenv("AI_OPT_BPERF_DURATION", "20")),
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
        return {"combined_score": 0.0, "error": f"{EXPERIMENT_NAME} failed: {exc}", "ops_per_sec": 0.0, "p99_latency_us": 0.0}
