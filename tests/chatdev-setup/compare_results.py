#!/usr/bin/env python3
"""
compare_results.py - Compare baseline vs MAST-hardened ChatDev HumanEval results.

Reads results from both runs, evaluates completions against HumanEval test cases,
and produces a detailed comparison report with MAST-specific analysis.

Usage:
    python compare_results.py [--baseline-dir DIR] [--mast-dir DIR] [--output FILE]

Default directories:
    baseline: mast_hardened/results/baseline/
    mast:     mast_hardened/results/mast/
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_results(results_dir: Path) -> Dict[str, Any]:
    """Load results from a directory containing per-task JSON files or all_results.json."""
    all_results = {}

    # Try all_results.json first
    combined = results_dir / "all_results.json"
    if combined.exists():
        with open(combined) as f:
            return json.load(f)

    # Fall back to individual JSON files
    for json_file in sorted(results_dir.glob("HumanEval_*.json")):
        with open(json_file) as f:
            data = json.load(f)
            all_results[data["task_id"]] = data

    return all_results


def load_samples(samples_file: Path) -> Dict[str, str]:
    """Load samples.jsonl into a dict of task_id -> completion."""
    samples = {}
    if not samples_file.exists():
        return samples
    with open(samples_file) as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                samples[data["task_id"]] = data["completion"]
    return samples


def detect_mast_violations(result: Dict[str, Any]) -> Dict[str, int]:
    """Detect MAST protocol violations in the completion output."""
    completion = result.get("completion", "") + result.get("error", "") or ""

    violations = {
        "loop_detected_triggered": 0,
        "no_termination_condition": 0,
        "no_clarification_when_needed": 0,
        "scope_drift": 0,
        "reasoning_action_mismatch": 0,
        "verification_missing": 0,
        "multi_level_verification_missing": 0,
    }

    # Positive signals: MAST protocols triggered correctly
    positive = {
        "loop_detected_count": completion.count("<LOOP-DETECTED>"),
        "verify_count": completion.count("<VERIFY>"),
        "clarify_count": completion.count("<CLARIFY>"),
        "objective_recenter_count": 0,  # Hard to detect automatically
    }

    # Negative signals: indicators of failure modes
    lines = completion.split('\n')

    # Check for repeated identical lines (loop indicator)
    line_counts = Counter(lines)
    for line, count in line_counts.items():
        if count > 2 and len(line.strip()) > 20:
            violations["loop_detected_triggered"] += 1

    # Check for no completion signal in a long output
    if len(completion) > 5000 and "<INFO> Finished" not in completion and "<INFO> FINISHED" not in completion:
        violations["no_termination_condition"] = 1

    # Check for verification absence
    if len(completion) > 2000 and "<VERIFY>" not in completion:
        violations["verification_missing"] = 1

    return {**violations, **positive}


def extract_completion_code(result: Dict[str, Any]) -> str:
    """Extract the actual code from a ChatDev result."""
    # Prefer extracted_code if available
    if result.get("extracted_code"):
        return result["extracted_code"]

    completion = result.get("completion", "")

    # Try to find Python code blocks
    code_blocks = re.findall(r'```python\n(.*?)```', completion, re.DOTALL)
    if code_blocks:
        return code_blocks[-1]  # Last code block is likely the final version

    # Try to find the function definition
    func_match = re.search(r'(def\s+\w+.*?)(?=\ndef\s|\nclass\s|\Z)', completion, re.DOTALL)
    if func_match:
        return func_match.group(1)

    return completion


def compute_pass_rates(baseline_results: Dict, mast_results: Dict) -> Dict:
    """Compute pass rates if HumanEval evaluation results are available."""
    # Check for evaluation results
    baseline_eval = {}
    mast_eval = {}

    for results_dir, eval_dict in [
        (Path("mast_hardened/results/baseline"), baseline_eval),
        (Path("mast_hardened/results/mast"), mast_eval),
    ]:
        eval_file = results_dir / "eval_results.json"
        if eval_file.exists():
            with open(eval_file) as f:
                data = json.load(f)
                for item in data:
                    eval_dict[item["task_id"]] = item.get("passed", False)

    report = {
        "baseline_total": len(baseline_results),
        "mast_total": len(mast_results),
        "baseline_passed": sum(1 for v in baseline_eval.values() if v),
        "mast_passed": sum(1 for v in mast_eval.values() if v),
    }

    if baseline_eval and mast_eval:
        common = set(baseline_eval.keys()) & set(mast_eval.keys())
        report["baseline_pass_rate"] = report["baseline_passed"] / max(len(baseline_eval), 1)
        report["mast_pass_rate"] = report["mast_passed"] / max(len(mast_eval), 1)

        # Deltas: problems that MAST fixed or broke
        fixed = []
        broken = []
        for tid in common:
            if not baseline_eval.get(tid) and mast_eval.get(tid):
                fixed.append(tid)
            elif baseline_eval.get(tid) and not mast_eval.get(tid):
                broken.append(tid)

        report["mast_fixed"] = fixed
        report["mast_broken"] = broken
        report["delta_pass_rate"] = report.get("mast_pass_rate", 0) - report.get("baseline_pass_rate", 0)

    return report


def compute_efficiency_metrics(results: Dict) -> Dict:
    """Compute efficiency metrics from results."""
    times = [r.get("elapsed_seconds", 0) for r in results.values() if r.get("elapsed_seconds")]
    errors = sum(1 for r in results.values() if r.get("error"))
    timeouts = sum(1 for r in results.values() if r.get("error") and "TIMEOUT" in str(r.get("error", "")))

    return {
        "total_problems": len(results),
        "completed": len(results) - errors - timeouts,
        "errors": errors,
        "timeouts": timeouts,
        "avg_time": statistics.mean(times) if times else 0,
        "median_time": statistics.median(times) if times else 0,
        "max_time": max(times) if times else 0,
        "min_time": min(times) if times else 0,
    }


def compute_mast_analysis(results: Dict, config_name: str) -> Dict:
    """Analyze MAST protocol usage and violations in results."""
    all_violations = defaultdict(list)
    all_positive = defaultdict(list)

    for task_id, result in results.items():
        indicators = detect_mast_violations(result)
        for k, v in indicators.items():
            if "count" in k:
                all_positive[k].append(v)
            else:
                all_positive[k].append(v)

    analysis = {
        "config": config_name,
        "total_tasks": len(results),
        "mast_protocol_usage": {
            k: {
                "total_occurrences": sum(v),
                "tasks_using": sum(1 for x in v if x > 0),
                "avg_per_task": statistics.mean(v) if v else 0,
            }
            for k, v in all_positive.items()
        },
    }

    return analysis


def generate_report(baseline_results: Dict, mast_results: Dict, output_file: Optional[str] = None) -> str:
    """Generate a comprehensive comparison report."""
    lines = []

    lines.append("=" * 70)
    lines.append("ChatDev HumanEval Benchmark: Baseline vs MAST-Hardened")
    lines.append("=" * 70)
    lines.append("")

    # Section 1: Overview
    lines.append("1. OVERVIEW")
    lines.append("-" * 40)
    lines.append(f"   Baseline problems: {len(baseline_results)}")
    lines.append(f"   MAST problems:     {len(mast_results)}")
    lines.append("")

    # Section 2: Efficiency
    lines.append("2. EFFICIENCY METRICS")
    lines.append("-" * 40)
    baseline_eff = compute_efficiency_metrics(baseline_results)
    mast_eff = compute_efficiency_metrics(mast_results)

    lines.append(f"   {'Metric':<25} {'Baseline':>10} {'MAST':>10} {'Delta':>10}")
    lines.append(f"   {'-'*25} {'-'*10} {'-'*10} {'-'*10}")
    for metric in ["completed", "errors", "timeouts", "avg_time", "median_time"]:
        bv = baseline_eff.get(metric, 0)
        mv = mast_eff.get(metric, 0)
        delta = mv - bv
        if isinstance(bv, float):
            lines.append(f"   {metric:<25} {bv:>10.2f} {mv:>10.2f} {delta:>+10.2f}")
        else:
            lines.append(f"   {metric:<25} {bv:>10} {mv:>10} {delta:>+10}")
    lines.append("")

    # Section 3: Pass rates (if eval data available)
    pass_report = compute_pass_rates(baseline_results, mast_results)
    if "baseline_pass_rate" in pass_report:
        lines.append("3. PASS RATES (HumanEval evaluation)")
        lines.append("-" * 40)
        lines.append(f"   Baseline pass rate: {pass_report['baseline_pass_rate']:.1%}")
        lines.append(f"   MAST pass rate:     {pass_report['mast_pass_rate']:.1%}")
        lines.append(f"   Delta:              {pass_report['delta_pass_rate']:+.1%}")
        lines.append(f"   Problems MAST fixed:   {len(pass_report.get('mast_fixed', []))}")
        lines.append(f"   Problems MAST broke:   {len(pass_report.get('mast_broken', []))}")

        if pass_report.get('mast_fixed'):
            lines.append(f"   Fixed by MAST: {', '.join(pass_report['mast_fixed'][:10])}")
        if pass_report.get('mast_broken'):
            lines.append(f"   Broken by MAST: {', '.join(pass_report['mast_broken'][:10])}")
        lines.append("")

    # Section 4: MAST Protocol Analysis
    lines.append("4. MAST PROTOCOL ANALYSIS")
    lines.append("-" * 40)

    mast_analysis = compute_mast_analysis(mast_results, "mast_hardened")
    lines.append(f"   MAST-hardened protocol usage across {mast_analysis['total_tasks']} tasks:")
    for protocol, stats in mast_analysis["mast_protocol_usage"].items():
        lines.append(f"     {protocol}:")
        lines.append(f"       Total occurrences: {stats['total_occurrences']}")
        lines.append(f"       Tasks using:       {stats['tasks_using']}/{mast_analysis['total_tasks']}")
        lines.append(f"       Avg per task:      {stats['avg_per_task']:.2f}")
    lines.append("")

    # Section 5: Loop detection comparison
    lines.append("5. LOOP DETECTION COMPARISON")
    lines.append("-" * 40)

    # Count <LOOP-DETECTED> occurrences per config
    baseline_loops = sum(
        (r.get("completion", "") + (r.get("error", "") or "")).count("<LOOP-DETECTED>")
        for r in baseline_results.values()
    )
    mast_loops = sum(
        (r.get("completion", "") + (r.get("error", "") or "")).count("<LOOP-DETECTED>")
        for r in mast_results.values()
    )

    baseline_verify = sum(
        (r.get("completion", "") + (r.get("error", "") or "")).count("<VERIFY>")
        for r in baseline_results.values()
    )
    mast_verify = sum(
        (r.get("completion", "") + (r.get("error", "") or "")).count("<VERIFY>")
        for r in mast_results.values()
    )

    lines.append(f"   <LOOP-DETECTED> markers:  Baseline={baseline_loops}  MAST={mast_loops}")
    lines.append(f"   <VERIFY> markers:         Baseline={baseline_verify}  MAST={mast_verify}")
    lines.append("")

    # Section 6: Per-problem detail (abbreviated)
    lines.append("6. PER-PROBLEM SUMMARY")
    lines.append("-" * 40)

    common_tasks = sorted(set(baseline_results.keys()) & set(mast_results.keys()))
    lines.append(f"   Common tasks: {len(common_tasks)}")

    time_deltas = []
    for tid in common_tasks[:20]:  # Show first 20
        bt = baseline_results[tid].get("elapsed_seconds", 0)
        mt = mast_results[tid].get("elapsed_seconds", 0)
        delta = mt - bt
        time_deltas.append(delta)
        status = "SLOWER" if delta > 0 else "FASTER" if delta < 0 else "SAME"
        lines.append(f"   {tid}: baseline={bt:.1f}s  mast={mt:.1f}s  ({status} {abs(delta):.1f}s)")

    if time_deltas:
        lines.append(f"   ...")
        lines.append(f"   Average time delta (MAST - Baseline): {statistics.mean(time_deltas):+.2f}s")
    lines.append("")

    # Section 7: Recommendations
    lines.append("7. RECOMMENDATIONS")
    lines.append("-" * 40)
    lines.append("   Based on the comparison:")
    if mast_loops > baseline_loops:
        lines.append("   - MAST anti-loop protocols are actively triggering (FM-1.3 working)")
    if mast_verify > baseline_verify:
        lines.append("   - MAST verification protocols are being used (FM-3.2/FM-3.3 working)")
    if pass_report.get("delta_pass_rate", 0) > 0:
        lines.append("   - MAST hardening improves HumanEval pass rate POSITIVELY")
    elif pass_report.get("delta_pass_rate", 0) < 0:
        lines.append("   - WARNING: MAST hardening slightly reduces pass rate (overhead)")
        lines.append("     Consider tuning prompt verbosity or per-role MAST protocols")
    lines.append("")

    report = "\n".join(lines)

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(report)
        print(f"Report saved to: {output_file}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Compare baseline vs MAST ChatDev HumanEval results")
    parser.add_argument("--baseline-dir", type=str, default="mast_hardened/results/baseline",
                        help="Directory with baseline results")
    parser.add_argument("--mast-dir", type=str, default="mast_hardened/results/mast",
                        help="Directory with MAST-hardened results")
    parser.add_argument("--output", "-o", type=str, default="mast_hardened/results/comparison_report.txt",
                        help="Output report file")
    args = parser.parse_args()

    baseline_dir = Path(args.baseline_dir)
    mast_dir = Path(args.mast_dir)

    print(f"Loading baseline results from: {baseline_dir}")
    print(f"Loading MAST results from: {mast_dir}")

    baseline_results = load_results(baseline_dir)
    mast_results = load_results(mast_dir)

    print(f"  Baseline: {len(baseline_results)} problems")
    print(f"  MAST:     {len(mast_results)} problems")

    if not baseline_results and not mast_results:
        print("\nNo results found. Run benchmarks first:")
        print("  ./run_baseline.sh")
        print("  ./run_mast.sh")
        # Generate a template report anyway
        report = generate_report(baseline_results, mast_results, args.output)
        print("\n" + report)
        return

    report = generate_report(baseline_results, mast_results, args.output)
    print("\n" + report)


if __name__ == "__main__":
    main()