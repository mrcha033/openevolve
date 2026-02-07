#!/usr/bin/env python3
"""
fitness.py - Causal-aware fitness function for OpenEvolve.

This fitness function weighs:
1. Raw performance (throughput, latency)
2. Causal speedup potential reduction (BCOZ)
3. Off-CPU time reduction (bperf)

The goal is to reward mutations that not only improve performance
but specifically address the causal bottlenecks identified by profiling.
"""

from dataclasses import dataclass
from typing import Optional

from openevolve.aiopt.bcoz_parser import BCOZResult
from openevolve.aiopt.bperf_parser import BperfResult


@dataclass
class MutationResult:
    """Complete result of evaluating a mutation."""
    mutation_id: str
    compiled: bool
    tests_passed: bool
    throughput_ops_sec: float
    p99_latency_us: float
    bperf: Optional[BperfResult] = None
    bcoz: Optional[BCOZResult] = None
    
    @property
    def is_valid(self) -> bool:
        """Returns True if mutation compiled and passed tests."""
        return self.compiled and self.tests_passed


# Baseline values - set these from initial unmodified run
class Baseline:
    THROUGHPUT_OPS_SEC = 100000.0
    P99_LATENCY_US = 500.0
    OFF_CPU_RATIO = 0.25  # 25%
    BCOZ_MAX_SPEEDUP = 15.0  # 15% (initial bottleneck)


def causal_fitness(
    result: MutationResult,
    throughput_weight: float = 0.30,
    latency_weight: float = 0.20,
    bcoz_weight: float = 0.30,
    bperf_weight: float = 0.20
) -> float:
    """
    Compute fitness score emphasizing causal speedup.
    
    The key insight: we want to REDUCE the max_speedup from BCOZ.
    A lower max_speedup means the mutation has already captured
    that optimization opportunity.
    
    Args:
        result: MutationResult from evaluation
        throughput_weight: Weight for throughput improvement (0-1)
        latency_weight: Weight for latency improvement (0-1)
        bcoz_weight: Weight for BCOZ bottleneck reduction (0-1)
        bperf_weight: Weight for off-CPU reduction (0-1)
    
    Returns:
        Fitness score (0.0 = failed, 1.0 = baseline, >1.0 = improvement)
    """
    # Failed mutations get zero fitness
    if not result.is_valid:
        return 0.0
    
    # Drop weights for absent profilers and redistribute
    if result.bcoz is None:
        bcoz_weight = 0.0
    if result.bperf is None:
        bperf_weight = 0.0

    total_weight = throughput_weight + latency_weight + bcoz_weight + bperf_weight
    if total_weight == 0:
        return 0.0
    throughput_weight /= total_weight
    latency_weight /= total_weight
    bcoz_weight /= total_weight
    bperf_weight /= total_weight
    
    # 1. Throughput score (higher is better)
    throughput_score = result.throughput_ops_sec / Baseline.THROUGHPUT_OPS_SEC
    
    # 2. Latency score (lower is better, so invert)
    latency_score = Baseline.P99_LATENCY_US / max(result.p99_latency_us, 1.0)
    
    # 3. BCOZ causal score
    # If mutation reduces max_speedup, it means it's addressing the bottleneck
    bcoz_score = 0.0
    if result.bcoz is not None and result.bcoz.max_speedup > 0:
        # Score = (baseline_bottleneck - new_bottleneck) / baseline_bottleneck + 1
        # If new bottleneck is smaller, score > 1
        reduction = Baseline.BCOZ_MAX_SPEEDUP - result.bcoz.max_speedup
        bcoz_score = 1.0 + (reduction / Baseline.BCOZ_MAX_SPEEDUP)
        bcoz_score = max(bcoz_score, 0.1)  # Floor to prevent negative
    
    # 4. Off-CPU score (lower is better)
    bperf_score = 0.0
    if result.bperf is not None:
        bperf_score = Baseline.OFF_CPU_RATIO / max(result.bperf.off_cpu_ratio, 0.01)
        bperf_score = min(bperf_score, 5.0)  # Cap to prevent outliers
    
    # Weighted combination
    fitness = (
        throughput_weight * throughput_score
        + latency_weight * latency_score
        + bcoz_weight * bcoz_score
        + bperf_weight * bperf_score
    )
    
    return round(fitness, 4)


def fast_fitness(result: MutationResult) -> float:
    """
    Fast fitness function for local iteration (no profiling data).
    
    Used in Mode B (local RocksDB-Lite) where bperf/BCOZ aren't available.
    """
    if not result.is_valid:
        return 0.0
    
    throughput_score = result.throughput_ops_sec / Baseline.THROUGHPUT_OPS_SEC
    latency_score = Baseline.P99_LATENCY_US / max(result.p99_latency_us, 1.0)
    
    return round(0.7 * throughput_score + 0.3 * latency_score, 4)


def fitness_summary(result: MutationResult, fitness: float) -> str:
    """Generate human-readable fitness summary."""
    lines = [
        f"Mutation: {result.mutation_id}",
        f"Valid: {result.is_valid}",
        f"Fitness: {fitness:.4f}",
        f"",
        f"Performance:",
        f"  Throughput: {result.throughput_ops_sec:.0f} ops/sec "
        f"({result.throughput_ops_sec / Baseline.THROUGHPUT_OPS_SEC:.2%} of baseline)",
        f"  P99 Latency: {result.p99_latency_us:.1f} µs "
        f"({Baseline.P99_LATENCY_US / result.p99_latency_us:.2%} improvement)",
    ]
    
    if result.bcoz:
        lines.extend([
            f"",
            f"Causal Profiling (BCOZ):",
            f"  Max speedup potential: {result.bcoz.max_speedup:.1f}%",
            f"  Bottleneck location: {result.bcoz.max_speedup_location}",
        ])
    
    if result.bperf:
        lines.extend([
            f"",
            f"Blocked Time (bperf):",
            f"  Off-CPU ratio: {result.bperf.off_cpu_ratio:.1%}",
            f"  Top blocker: {result.bperf.top_blockers[0].function if result.bperf.top_blockers else 'N/A'}",
        ])
    
    return '\n'.join(lines)


if __name__ == "__main__":
    # Test with mock data
    mock_bperf = BperfResult(
        total_samples=10000,
        off_cpu_samples=2000,
        off_cpu_ratio=0.20,
        top_blockers=[]
    )
    
    mock_bcoz = BCOZResult(
        speedup_points=[],
        max_speedup=10.0,  # Reduced from baseline 15%
        max_speedup_location="db_impl_write.cc:234"
    )
    
    result = MutationResult(
        mutation_id="test_001",
        compiled=True,
        tests_passed=True,
        throughput_ops_sec=120000,  # 20% improvement
        p99_latency_us=400,  # 20% improvement
        bperf=mock_bperf,
        bcoz=mock_bcoz
    )
    
    fitness = causal_fitness(result)
    print(fitness_summary(result, fitness))
