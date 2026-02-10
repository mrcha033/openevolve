#!/usr/bin/env python3
"""
perf_parser.py - Parse Linux perf profiling output.

Linux perf provides hardware performance counters (via `perf stat`) and
function-level CPU sampling (via `perf record` + `perf report`). This
parser extracts both and generates LLM-readable optimization guidance.

`perf stat` output format:
```
     12,345,678,901      cycles                    #    3.123 GHz
      9,876,543,210      instructions              #    0.80  insn per cycle
          2,345,678      cache-misses              #    5.14 % of all cache refs
```

`perf report --stdio` output format:
```
# Overhead  Command  Shared Object  Symbol
    25.32%  binary   libfoo.so      [.] some::Function
```
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PerfCounter:
    """A single hardware performance counter reading."""
    name: str
    value: int
    comment: str = ""


@dataclass
class PerfHotspot:
    """A function-level CPU hotspot from perf report."""
    overhead_pct: float
    command: str
    shared_object: str
    symbol: str

    @property
    def location(self) -> str:
        return f"{self.shared_object}:{self.symbol}"

    def __str__(self) -> str:
        return f"{self.symbol} ({self.overhead_pct:.1f}%)"


@dataclass
class PerfResult:
    """Combined perf stat + perf report result."""
    # perf stat counters
    cycles: int = 0
    instructions: int = 0
    cache_references: int = 0
    cache_misses: int = 0
    branches: int = 0
    branch_misses: int = 0
    context_switches: int = 0
    cpu_migrations: int = 0
    page_faults: int = 0
    elapsed_seconds: float = 0.0
    user_seconds: float = 0.0
    sys_seconds: float = 0.0
    all_counters: list[PerfCounter] = field(default_factory=list)
    # perf report hotspots
    hotspots: list[PerfHotspot] = field(default_factory=list)
    raw_stat_output: str = ""
    raw_report_output: str = ""

    @property
    def ipc(self) -> float:
        """Instructions per cycle."""
        return self.instructions / self.cycles if self.cycles > 0 else 0.0

    @property
    def cache_miss_pct(self) -> float:
        return (self.cache_misses / self.cache_references * 100
                if self.cache_references > 0 else 0.0)

    @property
    def branch_miss_pct(self) -> float:
        return (self.branch_misses / self.branches * 100
                if self.branches > 0 else 0.0)

    @property
    def top_hotspots(self) -> list[PerfHotspot]:
        """Return top 10 CPU hotspots."""
        return sorted(self.hotspots, key=lambda h: h.overhead_pct, reverse=True)[:10]

    @property
    def has_significant_hotspot(self) -> bool:
        """True if any single function accounts for >15% CPU."""
        return any(h.overhead_pct > 15.0 for h in self.hotspots)


def _parse_counter_value(raw: str) -> int:
    """Parse a perf counter value like '12,345,678,901' to int."""
    return int(raw.replace(",", "").strip())


def parse_perf_stat(output: str) -> PerfResult:
    """Parse `perf stat` text output into a PerfResult.

    Handles both stderr output (default) and file-based output.
    """
    result = PerfResult(raw_stat_output=output)

    # Map of known counter name fragments to PerfResult attributes
    counter_map = {
        "cycles": "cycles",
        "instructions": "instructions",
        "cache-references": "cache_references",
        "cache-misses": "cache_misses",
        "branches": "branches",
        "branch-misses": "branch_misses",
        "context-switches": "context_switches",
        "cpu-migrations": "cpu_migrations",
        "page-faults": "page_faults",
    }

    # Pattern: leading spaces, number (with commas), spaces, counter-name, optional #comment
    counter_re = re.compile(
        r"^\s*([\d,]+)\s+([\w-]+(?::[\w-]+)?)\s*(?:#\s*(.*))?$"
    )
    # Time patterns
    elapsed_re = re.compile(r"([\d.]+)\s+seconds time elapsed")
    user_re = re.compile(r"([\d.]+)\s+seconds user")
    sys_re = re.compile(r"([\d.]+)\s+seconds sys")

    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("Performance"):
            continue

        m = counter_re.match(line)
        if m:
            raw_val, name, comment = m.group(1), m.group(2), m.group(3) or ""
            value = _parse_counter_value(raw_val)
            result.all_counters.append(PerfCounter(name=name, value=value, comment=comment))

            for frag, attr in counter_map.items():
                if frag in name:
                    setattr(result, attr, value)
                    break

        # Parse timing lines
        em = elapsed_re.search(line)
        if em:
            result.elapsed_seconds = float(em.group(1))
        um = user_re.search(line)
        if um:
            result.user_seconds = float(um.group(1))
        sm = sys_re.search(line)
        if sm:
            result.sys_seconds = float(sm.group(1))

    return result


def parse_perf_report(output: str) -> list[PerfHotspot]:
    """Parse `perf report --stdio` output into a list of hotspots.

    Expected lines:
        25.32%  db_bench     librocksdb.so       [.] rocksdb::DBImpl::WriteImpl
    """
    hotspots = []
    # Pattern: percentage, command, shared object, [./k] symbol
    line_re = re.compile(
        r"^\s*([\d.]+)%\s+(\S+)\s+(\S+)\s+\[.\]\s+(.+)$"
    )
    for line in output.splitlines():
        m = line_re.match(line.strip())
        if m:
            hotspots.append(PerfHotspot(
                overhead_pct=float(m.group(1)),
                command=m.group(2),
                shared_object=m.group(3),
                symbol=m.group(4).strip(),
            ))
    hotspots.sort(key=lambda h: h.overhead_pct, reverse=True)
    return hotspots


def run_perf(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 30,
    output_dir: Path | None = None,
    events: str = "cycles,instructions,cache-references,cache-misses,branches,branch-misses,context-switches,cpu-migrations,page-faults",
) -> PerfResult:
    """Run `perf stat` and `perf record` + `perf report` on a binary.

    Args:
        binary_path: Path to the binary to profile.
        args: Arguments to pass to the binary.
        duration_sec: Maximum runtime for profiling.
        output_dir: Where to store perf.data and reports.
        events: Comma-separated perf stat events.

    Returns:
        PerfResult with hardware counters and function hotspots.
    """
    args = args or []
    output_dir = output_dir or Path("/tmp")
    data_file = output_dir / "perf.data"
    stat_file = output_dir / "perf_stat.txt"

    # --- perf stat ---
    stat_cmd = [
        "perf", "stat",
        "-e", events,
        "-o", str(stat_file),
        "--", binary_path,
    ] + args

    subprocess.run(
        stat_cmd,
        timeout=duration_sec + 60,
        check=True,
        capture_output=True,
    )

    stat_text = stat_file.read_text() if stat_file.exists() else ""
    result = parse_perf_stat(stat_text)

    # --- perf record + report ---
    record_cmd = [
        "perf", "record",
        "-g",
        "-o", str(data_file),
        "--", binary_path,
    ] + args

    subprocess.run(
        record_cmd,
        timeout=duration_sec + 60,
        check=True,
        capture_output=True,
    )

    report_proc = subprocess.run(
        ["perf", "report", "-i", str(data_file), "--stdio", "--no-children"],
        capture_output=True,
        text=True,
    )

    result.raw_report_output = report_proc.stdout
    result.hotspots = parse_perf_report(report_proc.stdout)

    return result


def generate_mutation_context(result: PerfResult, top_n: int = 5) -> str:
    """Generate LLM prompt context from perf profiling results.

    Combines hardware counter analysis with function-level hotspot
    information to give the LLM actionable optimization guidance.
    """
    lines = [
        "## CPU Profiling Results (perf)",
        "",
    ]

    # --- Hardware counters ---
    if result.cycles > 0:
        lines.append("### Hardware Counters")
        lines.append(f"- IPC: {result.ipc:.2f}")
        if result.ipc < 0.5:
            lines.append("  -> Very low IPC. Execution is severely memory-bound or stalled.")
        elif result.ipc < 1.0:
            lines.append("  -> Low IPC. Significant memory-latency stalls.")
        elif result.ipc < 2.0:
            lines.append("  -> Moderate IPC. Some memory stalls present.")
        else:
            lines.append("  -> High IPC. Execution is compute-bound.")

        lines.append(f"- Cache miss rate: {result.cache_miss_pct:.1f}%")
        if result.cache_miss_pct > 10:
            lines.append("  -> HIGH cache miss rate. Consider tiling, blocking, or data-layout changes.")
        elif result.cache_miss_pct > 3:
            lines.append("  -> Moderate cache miss rate. Data layout improvements may help.")

        lines.append(f"- Branch misprediction rate: {result.branch_miss_pct:.1f}%")
        if result.branch_miss_pct > 5:
            lines.append("  -> High branch misprediction. Consider branchless algorithms or lookup tables.")

        if result.context_switches > 100:
            lines.append(f"- Context switches: {result.context_switches:,}")
            lines.append("  -> High context switches suggest lock contention or I/O blocking.")

        lines.append(f"- Wall time: {result.elapsed_seconds:.2f}s (user {result.user_seconds:.2f}s, sys {result.sys_seconds:.2f}s)")
        if result.elapsed_seconds > 0 and result.sys_seconds / result.elapsed_seconds > 0.2:
            lines.append("  -> High system time ratio. Syscall overhead or I/O may be significant.")
        lines.append("")

    # --- Function hotspots ---
    if result.hotspots:
        lines.append("### CPU Hotspots (top functions by sample overhead)")
        for i, h in enumerate(result.top_hotspots[:top_n], 1):
            lines.append(f"{i}. **{h.symbol}** — {h.overhead_pct:.1f}% CPU ({h.shared_object})")
        lines.append("")
        if result.has_significant_hotspot:
            top = result.top_hotspots[0]
            lines.append(
                f"**Primary target:** `{top.symbol}` accounts for "
                f"{top.overhead_pct:.1f}% of CPU time. Focus optimizations here."
            )
        else:
            lines.append(
                "CPU time is spread across many functions. Consider algorithmic "
                "improvements or reducing overall work rather than micro-optimizing one function."
            )

    return "\n".join(lines)


if __name__ == "__main__":
    # Test with mock data
    mock_stat = """
 Performance counter stats for './db_bench':

     12,345,678,901      cycles                    #    3.123 GHz
      9,876,543,210      instructions              #    0.80  insn per cycle
         45,678,901      cache-references          #   11.543 M/sec
          2,345,678      cache-misses              #    5.14 % of all cache refs
        567,890,123      branches                  #  143.508 M/sec
         12,345,678      branch-misses             #    2.17 % of all branches
             12,345      context-switches          #    3.121 K/sec
                 45      cpu-migrations            #   11.380 /sec
              5,678      page-faults               #    1.434 K/sec

       3.952432890 seconds time elapsed
       3.850271000 seconds user
       0.100352000 seconds sys
"""

    mock_report = """
# Overhead  Command   Shared Object       Symbol
# ........  ........  ..................  .........
#
    25.32%  db_bench  librocksdb.so       [.] rocksdb::DBImpl::WriteImpl
    12.45%  db_bench  librocksdb.so       [.] rocksdb::WriteBatchInternal::Append
     8.67%  db_bench  [kernel.kallsyms]   [k] native_queued_spin_lock_slowpath
     6.23%  db_bench  librocksdb.so       [.] rocksdb::InlineSkipList<>::Insert
     4.15%  db_bench  libc.so.6           [.] __memmove_avx_unaligned
"""

    result = parse_perf_stat(mock_stat)
    result.hotspots = parse_perf_report(mock_report)

    print(f"IPC: {result.ipc:.2f}")
    print(f"Cache miss rate: {result.cache_miss_pct:.1f}%")
    print(f"Branch miss rate: {result.branch_miss_pct:.1f}%")
    print(f"Top hotspot: {result.top_hotspots[0]}")
    print()
    print("Mutation context:")
    print(generate_mutation_context(result))
