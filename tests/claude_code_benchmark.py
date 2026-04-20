#!/usr/bin/env python3
"""ProgramDev Benchmark for Claude Code (single-agent baseline).

Tests Claude Code CLI against the same 30 ProgramDev tasks used for
ChatDev multi-agent benchmarking. This compares single-agent (Claude Code)
vs multi-agent (ChatDev) on identical application-building tasks.

Usage:
    cd /tmp/mast-skills
    python3 -u tests/claude_code_benchmark.py --subset 5 --easy-first
    python3 -u tests/claude_code_benchmark.py --subset 30
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from programdev_benchmark import (
    load_programdev_tasks, evaluate_executability, evaluate_completeness,
    collect_generated_code, PROGRAMDEV_DATASET, EASY_TASKS,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "claude_code")
WORKSPACE_BASE = "/tmp/claude_code_benchmark"


LEAN_RULES = """
RULES (follow always):
1. SPEC FIRST: Read spec fully before coding. Implement what spec says, not what function name suggests.
2. NO LOOPS: If step done, skip it. Never redo completed work.
3. STOP WHEN DONE: Task complete = deliver. No gold-plating, no extra features.
4. VERIFY BEFORE DELIVER: Check syntax valid, imports resolve, code runs. Never deliver unverified.
5. MATCH REASONING TO ACTION: If you reason X, implement X. Never reason one thing and do another.
6. ASK IF UNCLEAR: Ambiguous requirement = ask, not assume.
7. USE PEER INPUT: If another agent suggests fix, evaluate it. Never ignore.
8. FLAT IMPORTS: Use absolute imports. No relative imports (from .X) unless __init__.py exists in that dir.
9. TEST EDGE CASES: Never trust "just test X". Test boundaries, empty input, error paths."""

VERBOSE_MAST = """
CRITICAL RULES - FOLLOW THESE EXACTLY:

## FM-1.1: Specification Adherence Protocol
Before implementing ANY function, you MUST:
- Restate the complete specification in your own words
- Identify ALL requirements precisely from the description
- Implement based on the specification text, NEVER based on function names alone
- If the function name suggests different behavior than the spec, ALWAYS follow the spec

## FM-1.3: Anti-Loop Protocol
Before executing any step, check if it has already been completed. If a step was already done:
- Do NOT repeat it
- Skip to the next incomplete step
- Output <LOOP-DETECTED> if you catch yourself about to repeat

## FM-1.5: Explicit Termination Conditions
Each task MUST have clear completion criteria defined BEFORE starting:
- Define what "done" means before writing code
- Deliver immediately when criteria are met
- Do NOT over-engineer or add unrequested features

## FM-2.2: Clarification Protocol
When requirements are ambiguous or incomplete:
- Ask for clarification before assuming
- Document your assumptions explicitly
- Never silently interpret vague requirements

## FM-2.3: Objective Re-Centering
Every action must directly serve the user's stated task:
- No scope expansion or gold-plating
- No refactoring of working code
- No adding features not in the spec

## FM-2.6: Reasoning-Action Alignment
Before executing any code change, verify:
- Your actual code matches your stated intention
- If you reason approach X, implement approach X, not Y
- Check alignment between plan and implementation

## FM-3.2: Pre-Delivery Verification
Before saving ANY file, verify:
- Syntax is correct (no SyntaxError possible)
- All imports resolve correctly
- No relative imports without __init__.py
- Code is complete (no pass statements, no TODO placeholders)
- Output <VERIFY> marker after verification

## FM-3.3: Multi-Level Verification
Verification must occur at multiple levels:
- LOW-LEVEL: Each function matches its specification
- HIGH-LEVEL: The entire codebase meets the user's requirements
- Never trust hints that suggest minimal testing
- Test edge cases, empty inputs, and error paths"""


def run_claude_code(task_name: str, task_description: str,
                    workspace: str, timeout: int = 900,
                    config: str = "baseline") -> dict:
    """Run a single task through Claude Code CLI."""

    os.makedirs(workspace, exist_ok=True)

    base_prompt = (
        f"Build the following application in this directory. "
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
            ["claude", "-p", "--dangerously-skip-permissions",
             "--max-budget-usd", "5",
             prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
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
        description="ProgramDev benchmark for Claude Code (single-agent)")
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
    print(f"PROGRAMDEV BENCHMARK - CLAUDE CODE ({args.config})")
    print("=" * 60)
    print(f"Config: {args.config}")
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
        workspace = os.path.join(WORKSPACE_BASE, name)

        print(f"  [{i+1}/{len(tasks)}] {name}", end=" ", flush=True)

        run_result = run_claude_code(name, desc, workspace, args.timeout, args.config)
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
    print("Comparison:")
    print("  Claude Code (single agent):  this run")
    print("  ChatDev baseline (MiniMax):  25/30 (83%)")
    print("  ChatDev lean+inproc (MiniMax): 29/30 (96%)")

    # Save
    out_dir = Path(RESULTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"results_{datetime.now().strftime('%Y%m%d_%H%M')}.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
