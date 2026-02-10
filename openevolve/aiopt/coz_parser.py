#!/usr/bin/env python3
"""
coz_parser.py - Parse standard Coz causal profiling output.

Coz (https://github.com/plasma-umass/coz) performs causal profiling by
virtually speeding up source lines and measuring the effect on end-to-end
throughput. Unlike BCOZ (blocked-time variant), standard Coz builds
per-line speedup curves showing predicted impact at multiple virtual
speedup levels.

Output format (.coz profile):
```
startup	time=<nanoseconds>
runtime	time=<nanoseconds>
samples	selected=<file>:<line>	speedup=<fraction>	duration=<ns>	selected-samples=<N>	throughput-delta=<fraction>
throughput-point	name=<location>	delta=<fraction>
latency-point	name=<location>	type=<begin|end>
```
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import subprocess


@dataclass
class SpeedupSample:
    """A single virtual speedup experiment for one source line."""

    speedup_frac: float  # Virtual speedup applied (0.0 to 1.0)
    throughput_delta: float  # Measured throughput change (fraction)
    duration_ns: int = 0
    selected_samples: int = 0


@dataclass
class CozLineProfile:
    """Aggregated speedup curve for a single source line."""

    file: str
    line: int
    samples: list[SpeedupSample] = field(default_factory=list)

    @property
    def location(self) -> str:
        return f"{self.file}:{self.line}"

    @property
    def max_throughput_delta(self) -> float:
        """Maximum observed throughput improvement across all speedup levels."""
        if not self.samples:
            return 0.0
        return max(s.throughput_delta for s in self.samples)

    @property
    def predicted_impact_pct(self) -> float:
        """Predicted global throughput impact as a percentage.

        Uses the throughput-delta at the highest speedup level tested as
        the upper-bound prediction.
        """
        if not self.samples:
            return 0.0
        # Sort by speedup fraction, take the highest
        by_speedup = sorted(
            self.samples, key=lambda s: s.speedup_frac, reverse=True
        )
        return by_speedup[0].throughput_delta * 100

    @property
    def impact_efficiency(self) -> float:
        """Ratio of throughput gain per unit of virtual speedup.

        Higher efficiency = the line has disproportionate impact (true bottleneck).
        """
        if not self.samples:
            return 0.0
        best = max(self.samples, key=lambda s: s.throughput_delta)
        if best.speedup_frac == 0:
            return 0.0
        return best.throughput_delta / best.speedup_frac

    def __str__(self) -> str:
        return f"{self.location} ({self.predicted_impact_pct:.1f}% predicted impact)"


@dataclass
class CozResult:
    """Aggregated Coz causal profiling result."""

    line_profiles: list[CozLineProfile]
    throughput_points: list[str] = field(default_factory=list)
    latency_points: list[str] = field(default_factory=list)
    startup_time_ns: int = 0
    runtime_ns: int = 0
    raw_output: str = ""

    @property
    def max_impact_pct(self) -> float:
        """Maximum predicted impact across all lines."""
        if not self.line_profiles:
            return 0.0
        return max(lp.predicted_impact_pct for lp in self.line_profiles)

    @property
    def max_impact_location(self) -> str:
        """Source location with the highest predicted impact."""
        if not self.line_profiles:
            return "N/A"
        best = max(self.line_profiles, key=lambda lp: lp.predicted_impact_pct)
        return best.location

    @property
    def has_optimization_opportunity(self) -> bool:
        """Returns True if any line shows >2% throughput impact."""
        return self.max_impact_pct > 2.0

    @property
    def top_opportunities(self) -> list[CozLineProfile]:
        """Return top 5 lines ranked by predicted impact."""
        return sorted(
            self.line_profiles,
            key=lambda lp: lp.predicted_impact_pct,
            reverse=True,
        )[:5]


def parse_coz_profile(profile_path: Path) -> CozResult:
    """Parse a standard .coz profile file.

    Builds per-line speedup curves from the `samples` entries and
    extracts throughput-point/latency-point metadata.
    """
    content = profile_path.read_text()

    startup_time = 0
    runtime = 0
    throughput_points = []
    latency_points = []

    # Collect samples by (file, line)
    line_samples: dict[tuple[str, int], list[SpeedupSample]] = defaultdict(list)

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("startup"):
            m = re.search(r"time=(\d+)", line)
            if m:
                startup_time = int(m.group(1))

        elif line.startswith("runtime"):
            m = re.search(r"time=(\d+)", line)
            if m:
                runtime = int(m.group(1))

        elif line.startswith("samples") or line.startswith("experiment"):
            # Both "samples" (newer) and "experiment" (older) formats
            sel = re.search(r"selected=([^:\s]+):(\d+)", line)
            spd = re.search(r"speedup=([\d.]+)", line)
            dur = re.search(r"duration=(\d+)", line)
            sel_samp = re.search(r"selected-samples=(\d+)", line)
            td = re.search(r"throughput-delta=([-\d.]+)", line)

            if sel and spd:
                file_name = sel.group(1)
                line_num = int(sel.group(2))
                speedup_frac = float(spd.group(1))
                duration_ns = int(dur.group(1)) if dur else 0
                selected_samples = int(sel_samp.group(1)) if sel_samp else 0
                throughput_delta = float(td.group(1)) if td else speedup_frac

                line_samples[(file_name, line_num)].append(
                    SpeedupSample(
                        speedup_frac=speedup_frac,
                        throughput_delta=throughput_delta,
                        duration_ns=duration_ns,
                        selected_samples=selected_samples,
                    )
                )

        elif line.startswith("throughput-point"):
            name = re.search(r"name=(\S+)", line)
            if name:
                throughput_points.append(name.group(1))

        elif line.startswith("latency-point"):
            name = re.search(r"name=(\S+)", line)
            if name:
                latency_points.append(name.group(1))

    # Build line profiles
    profiles = []
    for (file_name, line_num), samples in line_samples.items():
        profiles.append(
            CozLineProfile(file=file_name, line=line_num, samples=samples)
        )

    # Sort by predicted impact
    profiles.sort(key=lambda lp: lp.predicted_impact_pct, reverse=True)

    return CozResult(
        line_profiles=profiles,
        throughput_points=throughput_points,
        latency_points=latency_points,
        startup_time_ns=startup_time,
        runtime_ns=runtime,
        raw_output=content,
    )


def run_coz(
    binary_path: str,
    args: list[str] | None = None,
    duration_sec: int = 60,
    output_dir: Path | None = None,
    progress_points: list[str] | None = None,
    scope: str | None = None,
) -> CozResult:
    """Run the standard Coz causal profiler on a binary.

    Args:
        binary_path: Path to the binary to profile.
        args: Arguments to pass to the binary.
        duration_sec: Profiling duration (controls how long the binary runs).
        output_dir: Where to store profile data.
        progress_points: Source locations to use as progress points (file:line).
        scope: Regex to restrict profiling scope (e.g., '%/rocksdb/').

    Returns:
        CozResult with per-line speedup curves.
    """
    args = args or []
    output_dir = output_dir or Path("/tmp")
    profile_file = output_dir / "profile.coz"

    cmd = ["coz", "run"]

    # Output file
    cmd.extend(["-o", str(profile_file)])

    # Progress points
    for pp in progress_points or []:
        cmd.extend(["-p", pp])

    # Scope filter
    if scope:
        cmd.extend(["-s", scope])

    cmd.extend(["---", binary_path] + args)

    subprocess.run(
        cmd,
        timeout=duration_sec + 120,
        check=True,
        capture_output=True,
    )

    return parse_coz_profile(profile_file)


def generate_mutation_context(result: CozResult, top_n: int = 3) -> str:
    """Generate LLM prompt context from Coz causal profiling results.

    Provides per-line speedup predictions so the LLM knows which
    source locations yield the highest global throughput improvement
    when optimized.
    """
    if not result.has_optimization_opportunity:
        return "No significant optimization opportunities detected by Coz causal profiling."

    lines = [
        "## Causal Profiling Results (Coz)",
        "",
        "Coz virtually sped up individual source lines and measured the",
        "resulting change in end-to-end throughput. The following lines",
        "have the highest predicted global impact:",
        "",
    ]

    for i, lp in enumerate(result.top_opportunities[:top_n], 1):
        efficiency = lp.impact_efficiency
        eff_label = ""
        if efficiency > 0.8:
            eff_label = " [HIGH efficiency — true bottleneck]"
        elif efficiency > 0.4:
            eff_label = " [moderate efficiency]"
        lines.append(
            f"{i}. **{lp.location}** — {lp.predicted_impact_pct:.1f}% "
            f"predicted throughput gain{eff_label}"
        )
        # Show the speedup curve if there are multiple data points
        curve_points = sorted(lp.samples, key=lambda s: s.speedup_frac)
        if len(curve_points) > 1:
            curve_str = ", ".join(
                f"{s.speedup_frac:.0%}->{s.throughput_delta:.1%}"
                for s in curve_points
                if s.speedup_frac > 0
            )
            if curve_str:
                lines.append(f"   Speedup curve: {curve_str}")

    lines.extend(
        [
            "",
            f"**Primary target:** `{result.max_impact_location}`",
            f"**Predicted impact:** {result.max_impact_pct:.1f}% global throughput improvement",
            "",
            "Focus your mutation on reducing execution time at the primary target.",
            "Lines with HIGH efficiency are true bottlenecks — even small",
            "improvements there yield disproportionate global gains.",
        ]
    )

    return "\n".join(lines)


if __name__ == "__main__":
    # Test with mock data
    import tempfile

    mock_profile = """
startup	time=1234567890
runtime	time=9876543210
samples	selected=db_impl_write.cc:234	speedup=0.00	duration=1000000	selected-samples=500	throughput-delta=0
samples	selected=db_impl_write.cc:234	speedup=0.05	duration=1000000	selected-samples=500	throughput-delta=0.02
samples	selected=db_impl_write.cc:234	speedup=0.10	duration=1000000	selected-samples=500	throughput-delta=0.05
samples	selected=db_impl_write.cc:234	speedup=0.20	duration=1000000	selected-samples=500	throughput-delta=0.12
samples	selected=compaction_job.cc:567	speedup=0.00	duration=1000000	selected-samples=300	throughput-delta=0
samples	selected=compaction_job.cc:567	speedup=0.10	duration=1000000	selected-samples=300	throughput-delta=0.08
samples	selected=memtable.cc:123	speedup=0.00	duration=1000000	selected-samples=200	throughput-delta=0
samples	selected=memtable.cc:123	speedup=0.10	duration=1000000	selected-samples=200	throughput-delta=0.01
throughput-point	name=main.cpp:42	delta=0.03
latency-point	name=request_done:78	type=end
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".coz", delete=False) as f:
        f.write(mock_profile)
        f.flush()
        result = parse_coz_profile(Path(f.name))

    print(f"Lines profiled: {len(result.line_profiles)}")
    print(f"Max impact: {result.max_impact_pct:.1f}%")
    print(f"Location: {result.max_impact_location}")
    print(f"Has opportunity: {result.has_optimization_opportunity}")
    print(f"Throughput points: {result.throughput_points}")
    print(f"Latency points: {result.latency_points}")
    print()
    for lp in result.top_opportunities:
        print(
            f"  {lp.location}: {lp.predicted_impact_pct:.1f}% (efficiency={lp.impact_efficiency:.2f})"
        )
    print()
    print("Mutation context:")
    print(generate_mutation_context(result))
