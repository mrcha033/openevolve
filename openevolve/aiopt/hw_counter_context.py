"""Generate human-readable mutation context from hardware performance counters.

The hw_* fields come from perf_event_open in the C++ benchmark harness.
This replaces BCOZ/bperf for environments without sudo or perf CLI.
"""


def generate_hw_context(metrics: dict) -> str:
    """Generate LLM-readable profiler summary from hardware counters.

    Returns empty string if counters are unavailable (non-Linux or perf denied).
    """
    cycles = metrics.get("hw_cycles", 0)
    instructions = metrics.get("hw_instructions", 0)
    cache_misses = metrics.get("hw_cache_misses", 0)
    cache_refs = metrics.get("hw_cache_refs", 0)
    branch_misses = metrics.get("hw_branch_misses", 0)
    branches = metrics.get("hw_branches", 0)

    if cycles <= 0:
        return ""

    ipc = instructions / cycles if cycles > 0 else 0
    cache_miss_pct = cache_misses / cache_refs * 100 if cache_refs > 0 else 0
    branch_miss_pct = branch_misses / branches * 100 if branches > 0 else 0

    lines = ["## Hardware Performance Counters", ""]

    # IPC analysis
    lines.append(f"Instructions Per Cycle (IPC): {ipc:.2f}")
    if ipc < 0.5:
        lines.append("  -> Very low IPC. Execution is severely memory-bound or stalled.")
    elif ipc < 1.0:
        lines.append("  -> Low IPC. Significant memory latency stalls.")
    elif ipc < 2.0:
        lines.append("  -> Moderate IPC. Some memory stalls present.")
    else:
        lines.append("  -> High IPC. Execution is compute-bound.")

    # Cache analysis
    lines.append("")
    lines.append(
        f"Cache miss rate: {cache_miss_pct:.1f}% "
        f"({cache_misses:,} misses / {cache_refs:,} references)"
    )
    if cache_miss_pct > 10:
        lines.append(
            "  -> HIGH cache miss rate. The working set exceeds cache capacity. "
            "Consider tiling/blocking to fit data in L2, or change data layout "
            "to improve spatial locality."
        )
    elif cache_miss_pct > 3:
        lines.append(
            "  -> Moderate cache miss rate. Data layout or access pattern "
            "improvements may help. Consider structure-of-arrays layout or "
            "loop reordering."
        )
    else:
        lines.append("  -> Low cache miss rate. Cache is not the primary bottleneck.")

    # Branch analysis
    lines.append("")
    lines.append(
        f"Branch misprediction rate: {branch_miss_pct:.1f}% "
        f"({branch_misses:,} / {branches:,})"
    )
    if branch_miss_pct > 5:
        lines.append(
            "  -> High branch misprediction. Consider branchless algorithms, "
            "lookup tables, or conditional moves."
        )
    elif branch_miss_pct > 2:
        lines.append("  -> Moderate branch misprediction. May benefit from branchless code.")
    else:
        lines.append("  -> Branch prediction is not a significant bottleneck.")

    # Summary
    lines.append("")
    lines.append("### Summary")
    bottlenecks = []
    if cache_miss_pct > 5:
        bottlenecks.append("cache misses")
    if ipc < 1.0:
        bottlenecks.append("memory latency")
    if branch_miss_pct > 3:
        bottlenecks.append("branch misprediction")
    if not bottlenecks:
        if ipc >= 2.0:
            bottlenecks.append("compute throughput (already efficient)")
        else:
            bottlenecks.append("instruction-level parallelism")
    lines.append(f"Primary bottleneck(s): {', '.join(bottlenecks)}")

    return "\n".join(lines)
