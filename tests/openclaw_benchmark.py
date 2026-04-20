#!/usr/bin/env python3
"""ProgramDev Benchmark for OpenClaw Agent (single-agent baseline).

Tests OpenClaw against the same 30 ProgramDev tasks.
Uses --local mode with MiniMax-M2.7 for same-model comparison with ChatDev.

Usage:
    cd /tmp/mast-skills
    python3 -u tests/openclaw_benchmark.py --subset 5 --easy-first
    python3 -u tests/openclaw_benchmark.py --subset 30
    python3 -u tests/openclaw_benchmark.py --subset 30 --config lean
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from programdev_benchmark import (
    load_programdev_tasks, evaluate_executability, evaluate_completeness,
    PROGRAMDEV_DATASET, EASY_TASKS,
)
from claude_code_benchmark import LEAN_RULES, VERBOSE_MAST

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "openclaw")
WORKSPACE_BASE = "/tmp/openclaw_benchmark"


def run_openclaw(task_name: str, task_description: str,
                 workspace: str, timeout: int = 900,
                 config: str = "baseline") -> dict:
    """Run a single task through OpenClaw Agent CLI."""

    os.makedirs(workspace, exist_ok=True)

    base_prompt = (
        f"Build the following application in this directory ({workspace}). "
        f"Create all necessary Python files with a main.py entry point. "
        f"Use absolute imports (not relative). "
        f"Make sure the code is complete and runnable.\n\n"
        f"Task: {task_description}\n\n"
        f"Requirements:\n"
        f"- Create a working Python application\n"
        f"- Include a main.py that can be run directly\n"
        f"- Use only standard library or common packages\n"
        f"- Make it fully functional, not just stubs"
    )

    if config == "lean":
        prompt = base_prompt + "\n\n" + LEAN_RULES
    elif config == "verbose_mast":
        prompt = base_prompt + "\n\n" + VERBOSE_MAST
    else:
        prompt = base_prompt

    start_time = datetime.now()
    try:
        proc = subprocess.run(
            ["openclaw", "agent", "--local", "-m", prompt,
             "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 30,  # extra buffer for CLI overhead
            cwd=workspace,
            env={**os.environ},
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": (proc.stdout or "")[-3000:],
            "stderr": (proc.stderr or "")[-3000:],
            "elapsed_seconds": elapsed,
            "exit_code": proc.returncode,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": "",
            "stderr": "",
            "elapsed_seconds": elapsed,
            "exit_code": -1,
            "error": f"TIMEOUT after {timeout}s",
        }
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": "",
            "stderr": "",
            "elapsed_seconds": elapsed,
            "exit_code": -1,
            "error": str(e)[:500],
        }


def main():
    parser = argparse.ArgumentParser(
        description="ProgramDev benchmark for OpenClaw Agent")
    parser.add_argument("--subset", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--easy-first", action="store_true")
    parser.add_argument("--config", choices=["baseline", "lean", "verbose_mast"], default="baseline")
    args = parser.parse_args()

    all_tasks = load_programdev_tasks(PROGRAMDEV_DATASET)
    if args.easy_first:
        easy = [t for t in all_tasks if t["project_name"] in EASY_TASKS]
        rest = [t for t in all_tasks if t["project_name"] not in EASY_TASKS]
        all_tasks = easy + rest

    tasks = all_tasks[:args.subset]

    print("=" * 60)
    print(f"PROGRAMDEV BENCHMARK - OPENCLAW ({args.config})")
    print("=" * 60)
    print(f"Config: {args.config}")
    print(f"Model: MiniMax-M2.7 (via Ollama cloud)")
    print(f"Tasks: {len(tasks)}")
    print(f"Timeout: {args.timeout}s")
    print(f"Workspace: {WORKSPACE_BASE}")
    print()

    results = {}
    pass_count = 0
    fail_count = 0

    for i, task in enumerate(tasks):
        name = task["project_name"]
        desc = task["description"]
        workspace = os.path.join(WORKSPACE_BASE, f"{name}_{args.config}")

        print(f"  [{i+1}/{len(tasks)}] {name}", end=" ", flush=True)

        run_result = run_openclaw(name, desc, workspace, args.timeout, args.config)
        exec_r = evaluate_executability(workspace)
        comp_r = evaluate_completeness(workspace)
        passed = exec_r["executable"] and comp_r["complete"]

        if passed:
            pass_count += 1
        else:
            fail_count += 1

        status = "PASS" if passed else "FAIL"
        e = "E" if exec_r["executable"] else "x"
        c = "C" if comp_r["complete"] else "x"
        elapsed = run_result["elapsed_seconds"]
        print(f"{status} [{e}{c}] {comp_r['py_files']}py/{comp_r['total_lines']}loc ({elapsed:.0f}s) {exec_r['reason'][:40]}")

        results[name] = {
            "passed": passed,
            "executable": exec_r["executable"],
            "exec_reason": exec_r["reason"],
            "py_files": comp_r["py_files"],
            "total_lines": comp_r["total_lines"],
            "elapsed": elapsed,
            "error": run_result.get("error"),
        }

    total = pass_count + fail_count
    print(f"\nRESULT: {pass_count}/{total} = {pass_count*100//total if total else 0}%")
    print()
    print("Same-model comparison (MiniMax-M2.7):")
    print(f"  OpenClaw (single agent):       this run")
    print("  ChatDev baseline (multi-agent): 25/30 (83%)")
    print("  ChatDev lean+inproc:            29/30 (96%)")

    out_dir = Path(RESULTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{args.config}_{datetime.now().strftime('%Y%m%d_%H%M')}.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
