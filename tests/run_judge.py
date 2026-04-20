#!/usr/bin/env python3
"""Run LLM-as-judge (Level 3) on existing ProgramDev warehouse results.

No re-running ChatDev - just evaluates code already generated.
Uses GPT-5.4 as judge to assess functional correctness.

Usage:
    cd /tmp/mast-skills
    python3 -u tests/run_judge.py --model minimax
    python3 -u tests/run_judge.py --model gpt54 --config lean_inprocess
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from programdev_benchmark import (
    MODEL_CONFIGS, collect_generated_code, evaluate_functional_correctness,
    evaluate_executability, evaluate_completeness, load_programdev_tasks,
    PROGRAMDEV_DATASET, _find_main_py,
)

CHATDEV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ChatDev"))


def main():
    parser = argparse.ArgumentParser(description="Run LLM judge on existing warehouse results")
    parser.add_argument("--model", required=True, help="Model to evaluate")
    parser.add_argument("--config", default="all", choices=["baseline", "inprocess", "lean_inprocess", "all"])
    args = parser.parse_args()

    tasks = load_programdev_tasks(PROGRAMDEV_DATASET)
    task_map = {t["project_name"]: t["description"] for t in tasks}
    warehouse = os.path.join(CHATDEV_DIR, "WareHouse")
    configs = ["baseline", "inprocess", "lean_inprocess"] if args.config == "all" else [args.config]

    for config in configs:
        print(f"\n{'='*60}")
        print(f"JUDGE: {args.model} / {config}")
        print(f"{'='*60}")

        dirs = [d for d in os.listdir(warehouse) if d.startswith("pd_") and f"_{args.model}_{config}_r1_" in d]
        by_task = {}
        for d in dirs:
            task = d.split(f"_{args.model}_")[0].replace("pd_", "")
            by_task[task] = d

        pass_count = 0
        fail_count = 0
        skip_count = 0
        results = {}

        for task_name, d in sorted(by_task.items()):
            ws = os.path.join(warehouse, d, "code_workspace")
            if not os.path.isdir(ws):
                print(f"  {task_name:<25} SKIP (no workspace)")
                skip_count += 1
                continue

            comp = evaluate_completeness(ws)
            if not comp["complete"]:
                print(f"  {task_name:<25} SKIP (no code)")
                skip_count += 1
                continue

            desc = task_map.get(task_name, "")
            code = collect_generated_code(ws)
            judge = evaluate_functional_correctness(desc, code, task_name)

            rating = judge.get("rating", "UNKNOWN")
            reason = judge.get("reason", "")[:60]
            results[task_name] = judge

            if rating == "PASS":
                pass_count += 1
                print(f"  {task_name:<25} PASS  {reason}")
            elif rating == "FAIL":
                fail_count += 1
                print(f"  {task_name:<25} FAIL  {reason}")
            else:
                skip_count += 1
                print(f"  {task_name:<25} {rating}  {reason}")

        partial_count = sum(1 for r in results.values() if r.get("rating") == "PARTIAL")
        total = pass_count + partial_count + fail_count
        score = (pass_count * 2 + partial_count) / (total * 2) * 100 if total else 0
        print(f"\n  JUDGE RESULT: P:{pass_count} PARTIAL:{partial_count} F:{fail_count} = {score:.0f}% score (skipped {skip_count})")
        print(f"  Strict (PASS only): {pass_count}/{total} = {pass_count*100//total if total else 0}%")
        print(f"  Lenient (PASS+PARTIAL): {pass_count+partial_count}/{total} = {(pass_count+partial_count)*100//total if total else 0}%")

        # Save results
        out_dir = Path(os.path.dirname(__file__)) / "results" / "judge" / args.model
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{config}_judge.json", "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
