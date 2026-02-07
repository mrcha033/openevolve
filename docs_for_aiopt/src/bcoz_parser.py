#!/usr/bin/env python3
"""
bcoz_parser.py - Parse BCOZ/Coz causal profiling output.

Coz performs "causal profiling" by virtually speeding up code regions
to predict their impact on end-to-end performance. BCOZ extends this
with blocked-time awareness.

Output format (.coz profile):
```
startup	time=12345
runtime	time=67890
throughput-point	name=main	delta=0.05
progress-point	name=ops	delta=0.03
experiment	selected=db_impl.cc:234	speedup=0.10	duration=1000
experiment	selected=compaction.cc:567	speedup=0.25	duration=1000
```
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import subprocess


@dataclass
class SpeedupPoint:
    """A code location with predicted speedup impact."""
    file: str
    line: int
    speedup_pct: float
    duration_samples: int = 0
    
    @property
    def location(self) -> str:
        return f"{self.file}:{self.line}"
    
    def __str__(self) -> str:
        return f"{self.location} ({self.speedup_pct:.1f}% potential)"


@dataclass
class BCOZResult:
    """Aggregated BCOZ causal profiling result."""
    speedup_points: list[SpeedupPoint]
    max_speedup: float
    max_speedup_location: str
    startup_time_ns: int = 0
    runtime_ns: int = 0
    raw_output: str = ""
    
    @property
    def has_optimization_opportunity(self) -> bool:
        """Returns True if any location shows >5% speedup potential."""
        return self.max_speedup > 5.0
    
    @property
    def top_opportunities(self) -> list[SpeedupPoint]:
        """Return top 5 optimization opportunities."""
        return sorted(self.speedup_points, key=lambda x: x.speedup_pct, reverse=True)[:5]


def parse_coz_profile(profile_path: Path) -> BCOZResult:
    """
    Parse a .coz profile file.
    
    Expected format:
    ```
    startup	time=<nanoseconds>
    runtime	time=<nanoseconds>
    experiment	selected=<file>:<line>	speedup=<decimal>	duration=<samples>
    ```
    """
    content = profile_path.read_text()
    
    speedup_points = []
    startup_time = 0
    runtime = 0
    
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Parse startup time
        if line.startswith('startup'):
            match = re.search(r'time=(\d+)', line)
            if match:
                startup_time = int(match.group(1))
        
        # Parse runtime
        elif line.startswith('runtime'):
            match = re.search(r'time=(\d+)', line)
            if match:
                runtime = int(match.group(1))
        
        # Parse experiments (speedup predictions)
        elif line.startswith('experiment'):
            # Format: experiment	selected=file.cc:123	speedup=0.15	duration=1000
            selected_match = re.search(r'selected=([^:\s]+):(\d+)', line)
            speedup_match = re.search(r'speedup=([\d.]+)', line)
            duration_match = re.search(r'duration=(\d+)', line)
            
            if selected_match and speedup_match:
                file = selected_match.group(1)
                line_num = int(selected_match.group(2))
                speedup = float(speedup_match.group(1)) * 100  # Convert to percentage
                duration = int(duration_match.group(1)) if duration_match else 0
                
                speedup_points.append(SpeedupPoint(
                    file=file,
                    line=line_num,
                    speedup_pct=speedup,
                    duration_samples=duration
                ))
    
    # Sort by speedup potential
    speedup_points.sort(key=lambda x: x.speedup_pct, reverse=True)
    
    max_point = speedup_points[0] if speedup_points else SpeedupPoint("", 0, 0.0)
    
    return BCOZResult(
        speedup_points=speedup_points,
        max_speedup=max_point.speedup_pct,
        max_speedup_location=max_point.location if max_point.file else "N/A",
        startup_time_ns=startup_time,
        runtime_ns=runtime,
        raw_output=content
    )


def run_bcoz(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 60,
    output_dir: Path | None = None,
    progress_points: list[str] | None = None
) -> BCOZResult:
    """
    Run BCOZ/Coz causal profiling on a binary.
    
    Args:
        binary_path: Path to the binary to profile
        args: Arguments to pass to the binary
        duration_sec: Profiling duration
        output_dir: Where to store profile data
        progress_points: Source locations to use as progress points
    
    Returns:
        BCOZResult with causal speedup predictions
    """
    args = args or []
    output_dir = output_dir or Path("/tmp")
    profile_file = output_dir / "profile.coz"
    
    cmd = [
        "bcoz", "run",
        "-o", str(profile_file)
    ]
    
    # Add progress points if specified
    for pp in (progress_points or []):
        cmd.extend(["-p", pp])
    
    cmd.extend(["---", binary_path] + args)
    
    subprocess.run(
        cmd,
        timeout=duration_sec + 60,
        check=True,
        capture_output=True
    )
    
    return parse_coz_profile(profile_file)


def generate_mutation_context(result: BCOZResult, top_n: int = 3) -> str:
    """
    Generate LLM prompt context from BCOZ results.
    
    This is injected into the mutation prompt to guide the LLM
    toward the highest-impact optimization targets.
    """
    if not result.has_optimization_opportunity:
        return "No significant optimization opportunities detected by causal profiling."
    
    lines = [
        "## Causal Profiling Results (BCOZ)",
        "",
        "The following code locations have been identified as bottlenecks.",
        "Optimizing these locations will yield the predicted global speedup:",
        ""
    ]
    
    for i, point in enumerate(result.top_opportunities[:top_n], 1):
        lines.append(f"{i}. **{point.location}** — {point.speedup_pct:.1f}% potential speedup")
    
    lines.extend([
        "",
        f"**Primary target:** `{result.max_speedup_location}`",
        f"**Predicted impact:** {result.max_speedup:.1f}% global throughput improvement",
        "",
        "Focus your mutation on reducing execution time at the primary target location."
    ])
    
    return '\n'.join(lines)


if __name__ == "__main__":
    # Test with mock data
    import tempfile
    
    mock_profile = """
startup	time=1234567890
runtime	time=9876543210
experiment	selected=db_impl_write.cc:234	speedup=0.15	duration=1000
experiment	selected=compaction_job.cc:567	speedup=0.08	duration=1000
experiment	selected=memtable.cc:123	speedup=0.12	duration=1000
experiment	selected=wal_manager.cc:89	speedup=0.05	duration=500
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.coz', delete=False) as f:
        f.write(mock_profile)
        f.flush()
        result = parse_coz_profile(Path(f.name))
    
    print(f"Max speedup: {result.max_speedup:.1f}%")
    print(f"Location: {result.max_speedup_location}")
    print(f"Has opportunity: {result.has_optimization_opportunity}")
    print()
    print("Mutation context:")
    print(generate_mutation_context(result))
