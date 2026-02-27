"""
DSig Experiment — OpenEvolve Evaluator

Pipeline:
  1. Extract C code from evolved program (PROGRAM variable or raw .c)
  2. Compile with gcc -O2 -lsodium
  3. Correctness: run evolved binary --verify → parse (msg, sig) pairs
     → verify each with a KNOWN-GOOD libsodium verifier binary
  4. Benchmark: run evolved binary --bench (3 trials, median)
  5. Optional: run perf stat + perf report, inject into artifacts

Env vars:
  DSIG_PROFILER=1         enable profiler
  DSIG_PROFILER_CADENCE=10  run profiler every N evaluations
  DSIG_EVAL_COUNT=0       current evaluation number (set by runner)
"""

import os
import re
import sys
import json
import hashlib
import tempfile
import subprocess
from pathlib import Path

from openevolve.evaluation_result import EvaluationResult

# ── Config from env ──────────────────────────────────────────────────────

PROFILER_ON    = os.environ.get("DSIG_PROFILER", "0") == "1"
PROFILER_EVERY = int(os.environ.get("DSIG_PROFILER_CADENCE", "10"))
EVAL_COUNT     = int(os.environ.get("DSIG_EVAL_COUNT", "0"))
TIMEOUT_COMPILE  = 30
TIMEOUT_RUN      = 120
TIMEOUT_PROFILER = 90


# ── Known-good verifier (separate binary, never mutated) ────────────────

VERIFIER_C = r"""
/*
 * Reads lines from stdin:  MSG_HEX SIG_HEX
 * First line: PK:HEX
 * Verifies each signature against the public key.
 * Prints PASS or FAIL for each, then summary.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sodium.h>

static int hex_to_bytes(const char *hex, unsigned char *out, int max_len) {
    int len = strlen(hex) / 2;
    if (len > max_len) len = max_len;
    for (int i = 0; i < len; i++) {
        unsigned int b;
        sscanf(hex + 2*i, "%02x", &b);
        out[i] = (unsigned char)b;
    }
    return len;
}

int main(void) {
    if (sodium_init() < 0) return 1;

    char line[8192];
    unsigned char pk[crypto_sign_ed25519_PUBLICKEYBYTES];
    int total = 0, passed = 0;

    /* First line: PK:hex */
    if (!fgets(line, sizeof(line), stdin)) { printf("FAIL:no_input\n"); return 1; }
    if (strncmp(line, "PK:", 3) != 0) { printf("FAIL:no_pk\n"); return 1; }
    char *pk_hex = line + 3;
    pk_hex[strcspn(pk_hex, "\r\n")] = 0;
    hex_to_bytes(pk_hex, pk, sizeof(pk));

    /* Remaining lines: MSG_HEX SIG_HEX */
    while (fgets(line, sizeof(line), stdin)) {
        line[strcspn(line, "\r\n")] = 0;
        if (strlen(line) < 10) continue;

        char *space = strchr(line, ' ');
        if (!space) continue;
        *space = 0;
        char *msg_hex = line;
        char *sig_hex = space + 1;

        unsigned char msg[1024], sig[crypto_sign_ed25519_BYTES];
        int msg_len = hex_to_bytes(msg_hex, msg, sizeof(msg));
        hex_to_bytes(sig_hex, sig, sizeof(sig));

        total++;
        if (crypto_sign_ed25519_verify_detached(sig, msg, msg_len, pk) == 0)
            passed++;
        else
            fprintf(stderr, "FAIL at test %d\n", total);
    }

    if (total == 0) { printf("FAIL:no_tests\n"); return 1; }
    printf("%s %d/%d\n", (passed == total) ? "PASS" : "FAIL", passed, total);
    return (passed == total) ? 0 : 1;
}
"""


# ── Helpers ──────────────────────────────────────────────────────────────

def _run(cmd, timeout=60, cwd=None, stdin_data=None):
    try:
        r = subprocess.run(
            cmd, shell=True, timeout=timeout, cwd=cwd,
            capture_output=True, text=True,
            input=stdin_data
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -2, "", str(e)


def extract_c_code(program_path):
    """
    Extract C source from the evolved program.
    Handles: raw .c files, Python wrapper with PROGRAM variable,
    and markdown-fenced code blocks.
    """
    text = Path(program_path).read_text()

    # Raw C
    if text.lstrip().startswith(("#include", "//")):
        return text

    # Python wrapper: PROGRAM = r\"""...\"""
    for q in ['r"""', "r'''", '"""', "'''"]:
        pat = rf'PROGRAM\s*=\s*{re.escape(q)}(.*?){re.escape(q[-3:])}'
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1)

    # Markdown fenced block
    m = re.search(r'```(?:c|cpp)?\s*\n(.*?)```', text, re.DOTALL)
    if m:
        return m.group(1)

    # Fallback: try importing
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("prog", program_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "get_program"):
            return mod.get_program()
        if hasattr(mod, "PROGRAM"):
            return mod.PROGRAM
    except Exception:
        pass

    return text


# ── Pipeline stages ──────────────────────────────────────────────────────

def compile_evolved(c_code, workdir):
    """Compile evolved C code. Returns (ok, binary_path, message)."""
    src = os.path.join(workdir, "evolved.c")
    binary = os.path.join(workdir, "evolved")
    Path(src).write_text(c_code)
    rc, out, err = _run(
        f"gcc -O2 -o {binary} {src} -lsodium -lpthread -lm",
        timeout=TIMEOUT_COMPILE, cwd=workdir
    )
    msg = (out + "\n" + err).strip()
    if rc != 0:
        return False, None, f"compile error (rc={rc}):\n{msg}"
    if not os.path.isfile(binary):
        return False, None, f"no binary produced:\n{msg}"
    return True, binary, msg


def compile_verifier(workdir):
    """Compile the known-good verifier (runs once, cached in workdir)."""
    src = os.path.join(workdir, "verifier.c")
    binary = os.path.join(workdir, "verifier")
    Path(src).write_text(VERIFIER_C)
    rc, _, err = _run(
        f"gcc -O2 -o {binary} {src} -lsodium",
        timeout=TIMEOUT_COMPILE, cwd=workdir
    )
    if rc != 0:
        return None, f"verifier compile failed: {err}"
    return binary, ""


def check_correctness(evolved_bin, verifier_bin, workdir):
    """
    Run evolved --verify to get (msg, sig) pairs,
    pipe into verifier to check each signature.
    This catches any mutation that breaks Ed25519 correctness.
    """
    # Step 1: get signatures from evolved binary
    rc, sigs_out, err = _run(
        f"{evolved_bin} --verify",
        timeout=30, cwd=workdir
    )
    if rc != 0:
        return False, f"evolved --verify failed (rc={rc}): {err}"
    if not sigs_out.strip():
        return False, "evolved --verify produced no output"

    lines = [l for l in sigs_out.strip().split("\n") if l.strip()]
    if len(lines) < 2:  # at least PK + 1 test
        return False, f"too few lines from --verify: {len(lines)}"

    # Step 2: pipe into verifier
    rc, result, err = _run(
        verifier_bin, timeout=30, cwd=workdir,
        stdin_data=sigs_out
    )
    if rc != 0 or "PASS" not in result:
        return False, f"verification FAILED: {result.strip()} {err.strip()}"

    return True, result.strip()


def benchmark(binary, workdir, trials=3):
    """Run evolved --bench N times, return median ops/sec."""
    values = []
    for _ in range(trials):
        rc, out, err = _run(binary, timeout=TIMEOUT_RUN, cwd=workdir)
        if rc != 0:
            continue
        # Last line of stdout should be the ops/sec float
        lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
        if not lines:
            continue
        try:
            values.append(float(lines[-1]))
        except ValueError:
            continue

    if not values:
        return 0.0, "all benchmark trials failed"
    values.sort()
    return values[len(values) // 2], f"trials={values}"


def profile(binary, workdir):
    """
    Run perf stat + perf report on the evolved binary.
    Returns formatted text for LLM consumption.
    All data is LIVE — measured on this machine.
    """
    parts = ["=" * 50, "PERF PROFILER OUTPUT (live measurement)", "=" * 50]

    # ── perf stat ──
    events = (
        "cycles,instructions,cache-misses,cache-references,"
        "branch-misses,branch-instructions,"
        "L1-dcache-load-misses,LLC-load-misses,LLC-loads"
    )
    rc, out, _ = _run(
        f"perf stat -e {events} -r 3 {binary} 2>&1",
        timeout=TIMEOUT_PROFILER, cwd=workdir
    )
    parts.append("\n[perf stat — hardware counters, 3-run avg]")
    if rc == 0:
        for line in out.split("\n"):
            s = line.strip()
            if any(k in s for k in [
                "cycles", "instructions", "cache", "branch",
                "LLC", "L1-dcache", "seconds", "GHz", "insn per cycle"
            ]):
                parts.append(f"  {s}")
    else:
        parts.append(f"  (failed, rc={rc})")

    # ── perf report ──
    data = os.path.join(workdir, "perf.data")
    rc, _, _ = _run(
        f"perf record -g --call-graph dwarf -F 999 -o {data} -- {binary} 2>&1",
        timeout=TIMEOUT_PROFILER, cwd=workdir
    )
    if rc == 0 and os.path.isfile(data):
        rc2, report, _ = _run(
            f"perf report -i {data} --stdio --sort sym --percent-limit 0.5 2>&1",
            timeout=30, cwd=workdir
        )
        if rc2 == 0:
            parts.append("\n[perf report — function-level CPU hotspots]")
            for line in report.split("\n")[:50]:
                if line.strip():
                    parts.append(f"  {line.rstrip()}")

    parts.append("\n[hints]")
    parts.append(
        "  - Top function by CPU% = primary optimization target\n"
        "  - IPC < 1.0 on superscalar = execution is serialized\n"
        "  - High cache-miss rate = data layout problem\n"
        "  - Consider: precomputation, SIMD batching, parallelism"
    )
    return "\n".join(parts)


def should_profile():
    """Check env vars at call time (runner updates them between evals)."""
    on = os.environ.get("DSIG_PROFILER", "0") == "1"
    if not on:
        return False
    count = int(os.environ.get("DSIG_EVAL_COUNT", "0"))
    cadence = int(os.environ.get("DSIG_PROFILER_CADENCE", "10"))
    if count <= 1:
        return True  # always profile first iteration
    return (count % cadence) == 0


# ── OpenEvolve entry point ───────────────────────────────────────────────

def evaluate(program_path):
    """
    OpenEvolve evaluator interface.

    Args:
        program_path: path to the evolved program file (.c)

    Returns:
        EvaluationResult with metrics and artifacts
    """
    artifacts = {}

    with tempfile.TemporaryDirectory(prefix="dsig_") as workdir:

        # 1. Extract C code
        try:
            c_code = extract_c_code(program_path)
        except Exception as e:
            return EvaluationResult(
                metrics={"score": 0.0},
                artifacts={"error": f"extract: {e}"},
            )

        artifacts["code_hash"] = hashlib.md5(c_code.encode()).hexdigest()[:12]
        artifacts["code_lines"] = str(c_code.count("\n"))

        # 2. Compile evolved program
        ok, evolved_bin, msg = compile_evolved(c_code, workdir)
        artifacts["compile_output"] = msg[:500]
        if not ok:
            return EvaluationResult(
                metrics={"score": 0.0}, artifacts=artifacts,
            )

        # 3. Compile known-good verifier
        verifier_bin, verr = compile_verifier(workdir)
        if verifier_bin is None:
            artifacts["error"] = verr
            return EvaluationResult(
                metrics={"score": 0.0}, artifacts=artifacts,
            )

        # 4. Correctness: evolved --verify | verifier
        correct, corr_msg = check_correctness(evolved_bin, verifier_bin, workdir)
        artifacts["correctness"] = corr_msg
        if not correct:
            # Score 0 for incorrect signatures — no partial credit
            return EvaluationResult(
                metrics={"score": 0.0, "correctness": 0.0},
                artifacts=artifacts,
            )

        # 5. Benchmark
        ops_sec, bench_detail = benchmark(evolved_bin, workdir)
        artifacts["ops_sec"] = str(ops_sec)
        artifacts["bench_detail"] = str(bench_detail)
        if ops_sec <= 0:
            return EvaluationResult(
                metrics={"score": 0.0}, artifacts=artifacts,
            )

        # 6. Size penalty (discourages bloated binaries)
        bin_size = os.path.getsize(evolved_bin)
        artifacts["binary_bytes"] = str(bin_size)
        size_factor = 0.5 if bin_size > 10_000_000 else 1.0

        score = ops_sec * size_factor

        # 7. Profiler (conditional)
        if should_profile():
            try:
                prof_text = profile(evolved_bin, workdir)
                artifacts["profiler_output"] = prof_text
            except Exception as e:
                artifacts["profiler_error"] = str(e)

        return EvaluationResult(
            metrics={
                "score": score,
                "ops_sec": ops_sec,
                "correctness": 1.0,
                "binary_bytes": float(bin_size),
            },
            artifacts=artifacts,
        )


# ── CLI usage ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <program_path>")
        print(f"  Env: DSIG_PROFILER=1 DSIG_EVAL_COUNT=0")
        sys.exit(1)
    result = evaluate(sys.argv[1])
    output = {"metrics": result.metrics, "artifacts": {k: str(v) for k, v in result.artifacts.items()}}
    print(json.dumps(output, indent=2, default=str))
