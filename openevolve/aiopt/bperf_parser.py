#!/usr/bin/env python3
"""
bperf_parser.py - Parse bperf off-CPU profiling output.

bperf provides blocked-time analysis showing where threads spend time waiting.
This parser extracts off-CPU ratios and top blocking call stacks.
"""

import subprocess
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BlockingSite:
    """A single blocking call site identified by bperf."""
    function: str
    samples: int
    percentage: float
    call_stack: list[str] = field(default_factory=list)


@dataclass 
class BperfResult:
    """Aggregated bperf profiling result."""
    total_samples: int
    off_cpu_samples: int
    off_cpu_ratio: float
    top_blockers: list[BlockingSite]
    raw_output: str = ""
    
    @property
    def has_significant_blocking(self) -> bool:
        """Returns True if off-CPU time exceeds 20%."""
        return self.off_cpu_ratio > 0.20


def parse_bperf_report(report_path: Path) -> BperfResult:
    """
    Parse bperf report file.
    
    Expected format (simplified):
    ```
    # Total samples: 10000
    # Off-CPU samples: 2500
    
    25.00%  [kernel]  schedule
            |
            ---__schedule
               |          
               |--15.00%--futex_wait_queue_me
               |          |
               |          ---DBImpl::mutex_.lock()
    ```
    """
    content = report_path.read_text()
    
    # Extract totals
    total_match = re.search(r"Total samples:\s*(\d+)", content)
    offcpu_match = re.search(r"Off-CPU samples:\s*(\d+)", content)
    
    total = int(total_match.group(1)) if total_match else 0
    offcpu = int(offcpu_match.group(1)) if offcpu_match else 0
    
    # Parse blocking sites
    blockers = []
    blocker_pattern = re.compile(
        r"(\d+\.?\d*%)\s+\[?\w+\]?\s+(\w+)"
    )
    
    for match in blocker_pattern.finditer(content):
        pct_str = match.group(1).rstrip('%')
        func = match.group(2)
        pct = float(pct_str)
        samples = int(total * pct / 100) if total > 0 else 0
        
        blockers.append(BlockingSite(
            function=func,
            samples=samples,
            percentage=pct
        ))
    
    # Sort by percentage descending, take top 10
    blockers.sort(key=lambda x: x.percentage, reverse=True)
    
    return BperfResult(
        total_samples=total,
        off_cpu_samples=offcpu,
        off_cpu_ratio=offcpu / total if total > 0 else 0,
        top_blockers=blockers[:10],
        raw_output=content
    )


def run_bperf(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 30,
    output_dir: Path | None = None
) -> BperfResult:
    """
    Run bperf profiling on a binary and return parsed results.
    
    Args:
        binary_path: Path to the binary to profile
        args: Arguments to pass to the binary
        duration_sec: How long to profile
        output_dir: Where to store profiling data (default: /tmp)
    
    Returns:
        BperfResult with off-CPU analysis
    """
    args = args or []
    output_dir = output_dir or Path("/tmp")
    data_file = output_dir / "bperf.data"
    report_file = output_dir / "bperf_report.txt"
    
    # Record
    record_cmd = [
        "bperf", "record",
        "-g",  # Call graphs
        "-o", str(data_file),
        "--", binary_path
    ] + args
    
    subprocess.run(
        record_cmd,
        timeout=duration_sec + 30,
        check=True,
        capture_output=True
    )
    
    # Generate report
    report_cmd = [
        "bperf", "report",
        "-i", str(data_file),
        "--stdio"
    ]
    
    report_result = subprocess.run(
        report_cmd,
        capture_output=True,
        text=True
    )
    
    report_file.write_text(report_result.stdout)
    
    return parse_bperf_report(report_file)


def generate_mutation_context(result: BperfResult, top_n: int = 3) -> str:
    """
    Generate LLM prompt context from bperf off-CPU results.

    This is injected into the mutation prompt to guide the LLM
    toward reducing blocking and contention hotspots.
    """
    if not result.has_significant_blocking:
        return "No significant off-CPU blocking detected by bperf."

    lines = [
        "## Off-CPU Analysis (bperf)",
        "",
        "The program spends significant time blocked (off-CPU).",
        "Reducing contention at these call sites will improve throughput:",
        "",
        f"**Off-CPU ratio:** {result.off_cpu_ratio:.1%} "
        f"({result.off_cpu_samples}/{result.total_samples} samples)",
        "",
    ]

    for i, blocker in enumerate(result.top_blockers[:top_n], 1):
        lines.append(
            f"{i}. **{blocker.function}** — {blocker.percentage:.1f}% of blocked time"
        )

    lines.extend([
        "",
        "Focus your mutation on reducing lock contention and blocking at the top sites."
    ])

    return '\n'.join(lines)


if __name__ == "__main__":
    # Test with mock data
    import tempfile
    
    mock_report = """
    # Total samples: 10000
    # Off-CPU samples: 3500
    
    35.00%  [kernel]  schedule
    15.00%  libpthread  __pthread_mutex_lock
    10.00%  rocksdb  DBImpl::Write
    5.00%   rocksdb  Compaction::DoCompaction
    """
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(mock_report)
        f.flush()
        result = parse_bperf_report(Path(f.name))
    
    print(f"Off-CPU ratio: {result.off_cpu_ratio:.2%}")
    print(f"Significant blocking: {result.has_significant_blocking}")
    print(f"Top blockers: {[b.function for b in result.top_blockers]}")
