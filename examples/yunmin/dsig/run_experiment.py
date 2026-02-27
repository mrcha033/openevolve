#!/usr/bin/env python3
"""
DSig OpenEvolve Experiment Runner
==================================
Runs the 4-condition experiment:
  Condition 1: Local LLM, no profiler
  Condition 2: Local LLM + profiler
  Condition 3: SOTA model, no profiler
  Condition 4: SOTA model + profiler

Each condition is an independent OpenEvolve run with different LLM endpoint
and profiler settings. Results are saved for cross-condition analysis.

Usage:
    python run_experiment.py --condition 1 --seed 42
    python run_experiment.py --condition 2 --seed 42
    python run_experiment.py --condition all --seed 42
    python run_experiment.py --condition all --seeds 42,43,44  # 3× replication
"""

import os
import sys
import json
import yaml
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
CONFIG_TEMPLATE = EXPERIMENT_DIR / "config_base.yaml"
INITIAL_PROGRAM = EXPERIMENT_DIR / "initial_program.c"
EVALUATOR = EXPERIMENT_DIR / "evaluator.py"

# -- LLM Endpoints --
# Adjust these to match your actual setup
LOCAL_LLM = {
    "api_base": os.environ.get("LOCAL_LLM_API_BASE", "http://localhost:8000/v1"),
    "model": os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct"),
    "api_key": os.environ.get("LOCAL_LLM_API_KEY", "not-needed"),
}

SOTA_LLM = {
    "api_base": os.environ.get("SOTA_LLM_API_BASE", "https://api.anthropic.com/v1"),
    "model": os.environ.get("SOTA_LLM_MODEL", "claude-sonnet-4-20250514"),
    "api_key": os.environ.get("SOTA_LLM_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "")),
}

# -- Condition definitions --
CONDITIONS = {
    1: {"name": "local_no_profiler",    "llm": "local", "profiler": False},
    2: {"name": "local_with_profiler",  "llm": "local", "profiler": True},
    3: {"name": "sota_no_profiler",     "llm": "sota",  "profiler": False},
    4: {"name": "sota_with_profiler",   "llm": "sota",  "profiler": True},
}

PROFILER_CADENCE = 10  # run profiler every N iterations


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def build_config(condition_id, seed, output_dir):
    """Generate a per-run config YAML from the template."""
    with open(CONFIG_TEMPLATE) as f:
        cfg = yaml.safe_load(f)

    cond = CONDITIONS[condition_id]

    # LLM endpoint
    llm_cfg = LOCAL_LLM if cond["llm"] == "local" else SOTA_LLM
    cfg["llm"]["api_base"] = llm_cfg["api_base"]
    cfg["llm"]["model"] = llm_cfg["model"]
    cfg["llm"]["api_key"] = llm_cfg["api_key"]

    # Profiler injection into system prompt
    if cond["profiler"]:
        cfg["prompt"]["system_message"] += (
            "\n\nIMPORTANT: You will also receive PROFILER DATA (perf stat and "
            "perf report output) showing CPU-level performance counters and "
            "function-level hotspots. Use this data to guide your optimization "
            "decisions. Focus on the highest-% functions first."
        )

    # Seed
    cfg["random_seed"] = seed

    # Save
    config_path = output_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    return config_path


def run_single_condition(condition_id, seed, max_iterations=100):
    """Execute one OpenEvolve run for a given condition and seed."""
    cond = CONDITIONS[condition_id]
    run_name = f"cond{condition_id}_{cond['name']}_seed{seed}"
    run_dir = RESULTS_DIR / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  RUNNING: Condition {condition_id} — {cond['name']} (seed={seed})")
    print(f"  Output:  {run_dir}")
    print(f"{'='*70}\n")

    # Generate config
    config_path = build_config(condition_id, seed, run_dir)

    # Copy initial program and evaluator
    shutil.copy2(INITIAL_PROGRAM, run_dir / "initial_program.c")
    shutil.copy2(EVALUATOR, run_dir / "evaluator.py")

    # Set environment variables for the evaluator
    env = os.environ.copy()
    env["DSIG_PROFILER"] = "1" if cond["profiler"] else "0"
    env["DSIG_PROFILER_CADENCE"] = str(PROFILER_CADENCE)
    env["DSIG_EXPERIMENT_DIR"] = str(run_dir)

    # -- Run OpenEvolve --
    # Try the installed openevolve CLI first; fall back to manual loop
    openevolve_cmd = shutil.which("openevolve-run") or shutil.which("openevolve")

    if openevolve_cmd:
        cmd = [
            openevolve_cmd,
            str(run_dir / "initial_program.c"),
            str(run_dir / "evaluator.py"),
            "--config", str(config_path),
            "--iterations", str(max_iterations),
        ]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, env=env, cwd=str(run_dir))
        return run_dir, result.returncode == 0
    else:
        # Fallback: manual evolution loop (if openevolve not installed)
        print("openevolve CLI not found — running manual evolution loop")
        return run_manual_loop(condition_id, seed, run_dir, env, max_iterations)


def run_manual_loop(condition_id, seed, run_dir, env, max_iterations):
    """
    Manual evolution loop when openevolve is not installed.
    Uses the OpenAI-compatible API directly.

    This is a simplified single-program hill-climbing loop
    (no island model) suitable for the 4-condition comparison.
    """
    import importlib.util
    import re

    cond = CONDITIONS[condition_id]

    # Load config
    with open(run_dir / "config.yaml") as f:
        cfg = yaml.safe_load(f)

    # Load evaluator
    spec = importlib.util.spec_from_file_location("evaluator", run_dir / "evaluator.py")
    evaluator_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator_mod)

    # Load initial program (raw C file)
    current_code = (run_dir / "initial_program.c").read_text()

    # History tracking
    history = []
    best_score = 0.0
    best_code = current_code
    best_ops = 0.0

    # Latest profiler output (only for profiler conditions)
    latest_profiler = ""

    # LLM client setup (OpenAI-compatible)
    try:
        from openai import OpenAI
    except ImportError:
        print("Installing openai package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "openai",
                        "--break-system-packages", "-q"])
        from openai import OpenAI

    client = OpenAI(
        base_url=cfg["llm"]["api_base"],
        api_key=cfg["llm"]["api_key"],
    )

    system_prompt = cfg["prompt"]["system_message"]

    for iteration in range(1, max_iterations + 1):
        env["DSIG_ITERATION"] = str(iteration)
        os.environ["DSIG_ITERATION"] = str(iteration)

        print(f"\n--- Iteration {iteration}/{max_iterations} ---")

        # Build user prompt
        user_parts = []
        user_parts.append(f"Current best performance: {best_ops:.2f} ops/sec\n")

        # Include profiler data if condition enables it and data is available
        if cond["profiler"] and latest_profiler:
            user_parts.append("=== PROFILER DATA (from perf) ===")
            user_parts.append(latest_profiler)
            user_parts.append("=== END PROFILER DATA ===\n")

        user_parts.append("=== CURRENT BEST CODE ===")
        user_parts.append(best_code)
        user_parts.append("=== END CODE ===\n")

        # Include recent history (last 5 attempts)
        if history:
            recent = history[-5:]
            user_parts.append("Recent optimization attempts:")
            for h in recent:
                status = "improved" if h["improved"] else "no improvement"
                user_parts.append(
                    f"  Iter {h['iteration']}: {h['ops_sec']:.2f} ops/sec ({status})"
                )
            user_parts.append("")

        user_parts.append(
            "Propose an improved version of the code to increase ops/sec. "
            "Output ONLY the complete C source code, nothing else."
        )

        user_prompt = "\n".join(user_parts)

        # Query LLM
        try:
            response = client.chat.completions.create(
                model=cfg["llm"]["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=cfg["llm"]["temperature"],
                max_tokens=cfg["llm"].get("max_tokens", 8192),
            )
            evolved_text = response.choices[0].message.content
        except Exception as e:
            print(f"  LLM call failed: {e}")
            history.append({
                "iteration": iteration, "ops_sec": 0, "improved": False,
                "error": str(e)
            })
            continue

        # Extract C code from LLM response (strip markdown fences etc.)
        evolved_code = _extract_c_from_response(evolved_text)
        if not evolved_code:
            print("  Could not extract valid C code from LLM response")
            history.append({
                "iteration": iteration, "ops_sec": 0, "improved": False,
                "error": "no_c_code"
            })
            continue

        # Write evolved program to temp file
        evolved_path = run_dir / f"evolved_iter{iteration}.c"
        evolved_path.write_text(evolved_code)

        # Evaluate
        eval_result = evaluator_mod.evaluate(str(evolved_path))
        # Handle both EvaluationResult and plain dict
        if hasattr(eval_result, "metrics"):
            metrics = eval_result.metrics
            artifacts = eval_result.artifacts
        else:
            metrics = eval_result
            artifacts = eval_result.get("artifacts", {})
        ops = metrics.get("ops_sec", 0.0)
        score = metrics.get("score", 0.0)
        improved = ops > best_ops

        if improved:
            best_ops = ops
            best_score = score
            best_code = evolved_code
            # Save best
            (run_dir / "best_program.c").write_text(evolved_code)
            print(f"  ★ NEW BEST: {ops:.2f} ops/sec (score={score:.2f})")
        else:
            print(f"  → {ops:.2f} ops/sec (best remains {best_ops:.2f})")

        # Extract profiler output if available
        if "profiler_output" in artifacts:
            latest_profiler = artifacts["profiler_output"]

        history.append({
            "iteration": iteration,
            "ops_sec": ops,
            "score": score,
            "improved": improved,
            "code_hash": artifacts.get("code_hash", ""),
            "error": artifacts.get("compile_error", artifacts.get("benchmark_error", "")),
        })

        # Save history incrementally
        with open(run_dir / "history.json", "w") as f:
            json.dump(history, f, indent=2, default=str)

    # Final summary
    summary = {
        "condition": condition_id,
        "condition_name": cond["name"],
        "seed": int(env.get("DSIG_SEED", seed)),
        "best_ops_sec": best_ops,
        "best_score": best_score,
        "total_iterations": len(history),
        "improvements": sum(1 for h in history if h.get("improved")),
        "compile_failures": sum(1 for h in history if h.get("error") and "compil" in str(h["error"]).lower()),
        "timestamp": datetime.now().isoformat(),
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*70}")
    print(f"  DONE: Condition {condition_id} — {cond['name']}")
    print(f"  Best: {best_ops:.2f} ops/sec after {len(history)} iterations")
    print(f"  Results saved to: {run_dir}")
    print(f"{'='*70}\n")

    return run_dir, True


def _extract_c_from_response(text):
    """Extract C code from an LLM response that may contain markdown fences."""
    if not text:
        return None

    # Remove markdown code fences
    # Try ```c ... ``` first
    m = re.search(r'```(?:c|cpp)?\s*\n(.*?)```', text, re.DOTALL)
    if m:
        code = m.group(1).strip()
        if "#include" in code:
            return code

    # If the response starts with #include, treat it as raw C
    stripped = text.strip()
    if stripped.startswith("#include") or stripped.startswith("//"):
        # Remove any trailing markdown or explanation
        lines = stripped.split("\n")
        c_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                break
            c_lines.append(line)
        return "\n".join(c_lines)

    # Last resort: find the largest block containing #include
    blocks = re.split(r'```', text)
    for block in blocks:
        if "#include" in block and "main" in block:
            return block.strip()

    return None


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="DSig OpenEvolve Experiment Runner"
    )
    parser.add_argument(
        "--condition", type=str, default="all",
        help="Condition to run: 1, 2, 3, 4, or 'all'"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for single run"
    )
    parser.add_argument(
        "--seeds", type=str, default=None,
        help="Comma-separated seeds for replicated runs (e.g., 42,43,44)"
    )
    parser.add_argument(
        "--iterations", type=int, default=100,
        help="Max iterations per run"
    )
    parser.add_argument(
        "--profiler-cadence", type=int, default=10,
        help="Run profiler every N iterations (for conditions 2 and 4)"
    )
    args = parser.parse_args()

    global PROFILER_CADENCE
    PROFILER_CADENCE = args.profiler_cadence
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Determine seeds
    if args.seeds:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
    else:
        seeds = [args.seed]

    # Determine conditions
    if args.condition.lower() == "all":
        condition_ids = [1, 2, 3, 4]
    else:
        condition_ids = [int(args.condition)]

    # Run
    all_results = []
    for cid in condition_ids:
        for seed in seeds:
            run_dir, success = run_single_condition(cid, seed, args.iterations)
            all_results.append({
                "condition": cid,
                "seed": seed,
                "run_dir": str(run_dir),
                "success": success,
            })

    # Save master index
    with open(RESULTS_DIR / "experiment_index.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n\n" + "=" * 70)
    print("  ALL RUNS COMPLETE")
    print("=" * 70)
    for r in all_results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} Condition {r['condition']} seed={r['seed']} → {r['run_dir']}")
    print(f"\nResults index: {RESULTS_DIR / 'experiment_index.json'}")


if __name__ == "__main__":
    main()
