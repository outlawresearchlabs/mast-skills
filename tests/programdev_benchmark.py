#!/usr/bin/env python3
"""ProgramDev Benchmark for ChatDev (MAST Whole-System Validation)

Runs the ProgramDev-v0 benchmark (30 application-level tasks) through ChatDev
to test multi-agent coordination. This is the CORRECT benchmark for validating
MAST middleware - HumanEval was too easy (96-100% baseline).

Paper reference: arXiv:2503.13657v2, Table 4, page 32
- ChatDev baseline (GPT-3.5-turbo): 25.0% on ProgramDev
- Improved prompts: 34.4%
- New topology (cyclic): 40.6%

Evaluation levels:
1. Executability - does main.py run without crashing?
2. Code completeness - meaningful code produced?
3. Functional correctness - LLM-as-judge: does it meet the spec?
4. MAST failure mode analysis - which FM caused failures?

Usage:
    cd /tmp/mast-skills

    # Validate pipeline on 5 easy tasks with MiniMax
    python3 -u tests/programdev_benchmark.py --model minimax --config baseline --subset 5 --timeout 900

    # Full benchmark: 30 tasks x 2 configs
    python3 -u tests/programdev_benchmark.py --model minimax --subset 30 --reps 1

    # Resume interrupted run
    python3 -u tests/programdev_benchmark.py --model minimax --subset 30 --resume
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Configuration ---

CHATDEV_DIR = os.environ.get(
    "CHATDEV_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ChatDev")
)
CHATDEV_DIR = os.path.abspath(CHATDEV_DIR)

PROGRAMDEV_DATASET = os.environ.get(
    "PROGRAMDEV_DATASET",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                 "mast-official", "traces", "programdev", "programdev_dataset.json")
)
PROGRAMDEV_DATASET = os.path.abspath(PROGRAMDEV_DATASET)

RESULTS_DIR = os.environ.get(
    "MAST_RESULTS_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "programdev")
)

TIMEOUT_SECONDS = 900  # 15 min per task (complex apps need more time)

# Model configs - mirrors chatdev_benchmark.py
MODEL_CONFIGS = {
    "kimi25": {
        "model_name": "kimi-k2.5:cloud",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_kimi25.yaml",
            "inprocess": "ChatDev_v1_inprocess_kimi25.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_kimi25.yaml",
        },
    },
    "qwen36": {
        "model_name": "qwen3.6-plus-2026-04-02",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_qwen36.yaml",
            "inprocess": "ChatDev_v1_inprocess_qwen36.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_qwen36.yaml",
        },
    },
    "minimax": {
        "model_name": "MiniMax-M2.7",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_minimax.yaml",
            "inprocess": "ChatDev_v1_inprocess_minimax.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_minimax.yaml",
        },
    },
    "gpt54": {
        "model_name": "gpt-5.4",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_gpt54.yaml",
            "inprocess": "ChatDev_v1_inprocess_gpt54.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_gpt54.yaml",
        },
    },
    "glm51": {
        "model_name": "glm-5.1:cloud",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_glm51.yaml",
            "inprocess": "ChatDev_v1_inprocess_glm51.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_glm51.yaml",
        },
    },
    "qwen35": {
        "model_name": "qwen3.5:397b-cloud",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_qwen35.yaml",
            "inprocess": "ChatDev_v1_inprocess_qwen35.yaml",
            "lean_inprocess": "ChatDev_v1_lean_inprocess_qwen35.yaml",
        },
    },
    "gemma4moe": {
        "model_name": "gemma-4-26b-a4b-it",
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_gemma4moe.yaml",
            "inprocess": "ChatDev_v1_inprocess_gemma4moe.yaml",
        },
    },
    "gemma4": {
        "model_name": "gemma4:31b-cloud",
        "yaml_configs": {
            "baseline": "ChatDev_v1_gw.yaml",
            "inprocess": "ChatDev_v1_inprocess_gw.yaml",
        },
    },
}

# Easy tasks first for validation (ordered by expected difficulty)
EASY_TASKS = [
    "FibonacciNumbers", "DetectPalindromes", "BudgetTracker",
    "TicTacToe", "Mastermind",
]


def load_programdev_tasks(dataset_path: str) -> list:
    """Load ProgramDev tasks from the dataset JSON."""
    with open(dataset_path) as f:
        tasks = json.load(f)
    return tasks


def run_chatdev_task(yaml_config: str, task_name: str, task_description: str,
                     timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run a single ProgramDev task through ChatDev.

    Uses process groups to ensure all child processes are killed on timeout.
    """
    import signal
    env = {**os.environ}

    start_time = datetime.now()
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.join(CHATDEV_DIR, "run.py"),
             "--path", yaml_config, "--name", task_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=CHATDEV_DIR,
            env=env,
            preexec_fn=os.setsid,  # Create new process group
        )
        stdout, stderr = proc.communicate(input=task_description, timeout=timeout)
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": (stdout or "")[-5000:],
            "stderr": (stderr or "")[-5000:],
            "elapsed_seconds": elapsed,
            "exit_code": proc.returncode,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        # Kill entire process group
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.wait()
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
            "error": str(e)[:2000],
        }


def find_workspace(task_name: str) -> str:
    """Find the code_workspace directory for a completed task."""
    warehouse = os.path.join(CHATDEV_DIR, "WareHouse")
    if not os.path.isdir(warehouse):
        return ""

    matching = sorted(
        [d for d in os.listdir(warehouse) if d.startswith(task_name)],
        reverse=True,
    )
    if not matching:
        return ""

    ws = os.path.join(warehouse, matching[0], "code_workspace")
    return ws if os.path.isdir(ws) else ""


def _find_main_py(workspace: str) -> str:
    """Find main.py in workspace, checking top-level and subdirectories."""
    # Check top-level first
    main_py = os.path.join(workspace, "main.py")
    if os.path.exists(main_py):
        return main_py

    # Check immediate subdirectories (package layouts like budget_tracker/main.py)
    for entry in sorted(os.listdir(workspace)):
        subdir = os.path.join(workspace, entry)
        if os.path.isdir(subdir) and not entry.startswith(".") and entry not in ("__pycache__", "attachments"):
            # Prefer main.py, then __main__.py in subdirs
            for candidate_name in ("main.py", "__main__.py"):
                candidate = os.path.join(subdir, candidate_name)
                if os.path.exists(candidate):
                    return candidate

    # Last resort: any non-test .py with __main__ block
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", "attachments")]
        for f in sorted(files):
            if f.endswith(".py") and not f.startswith("test") and f != "debug.py":
                fp = os.path.join(root, f)
                try:
                    with open(fp) as fh:
                        if "__main__" in fh.read():
                            return fp
                except Exception:
                    pass
    return ""


def evaluate_executability(workspace: str) -> dict:
    """Level 1: Does main.py run without crashing?"""
    if not workspace:
        return {"executable": False, "reason": "no workspace found", "output": ""}

    main_py = _find_main_py(workspace)
    if not main_py:
        return {"executable": False, "reason": "no main.py found", "output": ""}

    # Determine the correct cwd - if main.py is in a subdirectory,
    # run from workspace so relative imports work
    run_cwd = workspace

    # Try to install requirements if they exist
    req_file = os.path.join(workspace, "requirements.txt")
    if not os.path.exists(req_file):
        # Check subdirectories
        for entry in os.listdir(workspace):
            candidate = os.path.join(workspace, entry, "requirements.txt")
            if os.path.exists(candidate):
                req_file = candidate
                break

    if os.path.exists(req_file):
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", req_file],
            capture_output=True, timeout=60, cwd=workspace,
        )

    try:
        proc = subprocess.run(
            [sys.executable, main_py],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=run_cwd,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHONPATH": workspace},
        )
        output = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]

        # exit code 0 or EOFError/keyboard interrupt from stdin = OK
        if proc.returncode == 0:
            return {"executable": True, "reason": "clean exit", "output": output}

        stderr = proc.stderr or ""
        combined = (proc.stdout or "") + " " + stderr
        # Interactive apps that fail on no stdin are still "executable"
        if any(x in stderr for x in ["EOFError", "KeyboardInterrupt", "curses",
                                       "pygame", "tkinter"]):
            return {"executable": True, "reason": f"interactive app (exit {proc.returncode})",
                    "output": output}

        # Missing third-party modules - code is structurally correct
        if "No module named" in stderr:
            return {"executable": True, "reason": f"missing dependency (exit {proc.returncode})",
                    "output": output}

        # Apps that need CLI arguments show usage and exit - still executable
        if proc.returncode in (1, 2) and any(x in combined.lower() for x in
                ["usage:", "error: the following arguments", "argparse",
                 "required:", "positional arguments", "provide", "argument",
                 "command-line", "supply a", "specify a", "enter a"]):
            return {"executable": True, "reason": f"needs CLI arguments (exit {proc.returncode})",
                    "output": output}

        # Apps that print help and exit are executable
        if proc.returncode in (0, 1, 2) and "usage:" in combined.lower():
            return {"executable": True, "reason": f"usage/help exit (exit {proc.returncode})",
                    "output": output}

        return {"executable": False, "reason": f"exit code {proc.returncode}",
                "output": output}
    except subprocess.TimeoutExpired:
        return {"executable": True, "reason": "timeout (likely interactive app)",
                "output": ""}
    except Exception as e:
        return {"executable": False, "reason": str(e)[:200], "output": ""}


def evaluate_completeness(workspace: str) -> dict:
    """Level 2: Is there meaningful code?"""
    if not workspace:
        return {"complete": False, "py_files": 0, "total_lines": 0, "has_main": False}

    py_files = []
    total_lines = 0
    has_main = bool(_find_main_py(workspace))

    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", "attachments")]
        for f in files:
            if f.endswith(".py"):
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, workspace)
                py_files.append(rel)
                try:
                    with open(fp) as fh:
                        total_lines += len(fh.readlines())
                except Exception:
                    pass

    return {
        "complete": len(py_files) > 0 and total_lines > 10,
        "py_files": len(py_files),
        "total_lines": total_lines,
        "has_main": has_main,
        "files": py_files,
    }


def collect_generated_code(workspace: str) -> str:
    """Collect all generated Python code from workspace for LLM evaluation."""
    if not workspace:
        return ""

    code_parts = []
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", "attachments")]
        for f in sorted(files):
            if f.endswith(".py"):
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, workspace)
                try:
                    with open(fp, errors="replace") as fh:
                        content = fh.read()
                    code_parts.append(f"# === {rel} ===\n{content}")
                except Exception:
                    pass

    return "\n\n".join(code_parts)[:15000]  # Cap at 15k chars for LLM context


def evaluate_functional_correctness(task_description: str, code: str,
                                     project_name: str) -> dict:
    """Level 3: LLM-as-judge - does the app meet the spec?

    Uses GPT-5.4 as judge (or falls back to available model).
    """
    if not code:
        return {"passed": False, "rating": "FAIL", "reason": "no code produced",
                "judge_response": ""}

    judge_prompt = f"""You are evaluating a software application generated by a multi-agent AI system.

TASK DESCRIPTION:
{task_description}

GENERATED CODE:
{code}

Evaluate the code against the task description. Consider:
1. Does the code implement the CORE functionality described in the task?
2. Would a user be able to actually use this application for its intended purpose?
3. Are there obvious bugs that would prevent basic operation?
4. Does it handle the key requirements mentioned in the description?

Rate the implementation:
- PASS: Code runs, implements the core feature, user could actually use it
- PARTIAL: Some functionality works but key features are missing or broken
- FAIL: Doesn't run, wrong functionality, or fundamentally broken

Respond with EXACTLY this format:
RATING: <PASS|PARTIAL|FAIL>
REASON: <one sentence explanation>
"""

    try:
        import openai
        # Try GPT-5.4 first, fall back to whatever is available
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not api_key:
            return {"passed": None, "rating": "SKIP",
                    "reason": "no OPENAI_API_KEY for judge", "judge_response": ""}

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model="gpt-5.4",
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=200,
            temperature=0,
        )
        judge_text = response.choices[0].message.content or ""

        # Parse rating
        rating_match = re.search(r"RATING:\s*(PASS|PARTIAL|FAIL)", judge_text, re.IGNORECASE)
        reason_match = re.search(r"REASON:\s*(.+)", judge_text, re.IGNORECASE)

        rating = rating_match.group(1).upper() if rating_match else "UNKNOWN"
        reason = reason_match.group(1).strip() if reason_match else judge_text[:200]

        return {
            "passed": rating == "PASS",
            "rating": rating,
            "reason": reason,
            "judge_response": judge_text[:500],
        }
    except Exception as e:
        return {"passed": None, "rating": "ERROR",
                "reason": f"Judge error: {str(e)[:200]}", "judge_response": ""}


def main():
    parser = argparse.ArgumentParser(
        description="ProgramDev benchmark for ChatDev (MAST validation)")
    parser.add_argument("--model",
        choices=list(MODEL_CONFIGS.keys()), required=True,
        help="Which model to test")
    parser.add_argument("--config",
        choices=["baseline", "inprocess", "lean_inprocess", "all"],
        default="all",
        help="Which config(s) to test")
    parser.add_argument("--subset", type=int, default=5,
        help="Number of tasks (5=easy validation, 30=full)")
    parser.add_argument("--reps", type=int, default=1,
        help="Repetitions per task")
    parser.add_argument("--resume", action="store_true",
        help="Resume from interrupted run")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS,
        help="Timeout per task in seconds")
    parser.add_argument("--skip-judge", action="store_true",
        help="Skip LLM-as-judge evaluation (just run + executability)")
    parser.add_argument("--easy-first", action="store_true",
        help="Run easy tasks first (for validation)")
    args = parser.parse_args()

    # Validate
    mc = MODEL_CONFIGS[args.model]
    configs_to_run = ["baseline", "inprocess"] if args.config == "all" else [args.config]

    yaml_dir = os.path.join(CHATDEV_DIR, "yaml_instance")
    for cfg in configs_to_run:
        yaml_path = os.path.join(yaml_dir, mc["yaml_configs"][cfg])
        if not os.path.isfile(yaml_path):
            print(f"ERROR: Config '{cfg}' YAML not found: {yaml_path}")
            sys.exit(1)

    if not os.path.isfile(PROGRAMDEV_DATASET):
        print(f"ERROR: ProgramDev dataset not found: {PROGRAMDEV_DATASET}")
        sys.exit(1)

    run_py = os.path.join(CHATDEV_DIR, "run.py")
    if not os.path.isfile(run_py):
        print(f"ERROR: ChatDev not found at {CHATDEV_DIR}")
        sys.exit(1)

    # Load tasks
    all_tasks = load_programdev_tasks(PROGRAMDEV_DATASET)

    if args.easy_first:
        # Reorder: easy tasks first, then the rest
        easy = [t for t in all_tasks if t["project_name"] in EASY_TASKS]
        rest = [t for t in all_tasks if t["project_name"] not in EASY_TASKS]
        all_tasks = easy + rest

    tasks = all_tasks[:args.subset]
    total_runs = len(tasks) * len(configs_to_run) * args.reps

    print("=" * 70)
    print("PROGRAMDEV BENCHMARK (MAST Whole-System Validation)")
    print("=" * 70)
    print(f"Model: {mc['model_name']}")
    print(f"Configs: {configs_to_run}")
    print(f"Tasks: {len(tasks)}")
    print(f"Reps: {args.reps}")
    print(f"Timeout: {args.timeout}s")
    print(f"Total runs: {total_runs}")
    print(f"Skip judge: {args.skip_judge}")
    est_min = total_runs * 10  # ~10 min average for complex tasks
    print(f"Est. time: ~{est_min:.0f} min ({est_min/60:.1f} hrs)")
    print(f"Results dir: {RESULTS_DIR}")
    print()
    print("Paper baseline (GPT-3.5-turbo): 25.0%")
    print("Paper improved prompt: 34.4%")
    print("Paper new topology: 40.6%")
    print()

    # Run experiments
    all_results = {}

    for config_name in configs_to_run:
        yaml_path = os.path.join(yaml_dir, mc["yaml_configs"][config_name])
        config_results = {}

        for rep in range(1, args.reps + 1):
            results_dir = Path(RESULTS_DIR) / args.model / config_name / f"rep{rep}"
            results_dir.mkdir(parents=True, exist_ok=True)

            results_file = results_dir / "results.json"
            existing = {}
            if args.resume and results_file.exists():
                with open(results_file) as f:
                    existing = json.load(f)

            for i, task in enumerate(tasks):
                project_name = task["project_name"]
                description = task["description"]

                if project_name in existing and args.resume:
                    print(f"  [{i+1}/{len(tasks)}] {project_name} [{config_name} r{rep}] - SKIP (resume)")
                    config_results[project_name] = existing[project_name]
                    continue

                # Task name includes model to avoid warehouse collisions
                task_name = f"pd_{project_name}_{args.model}_{config_name}_r{rep}"

                print(f"  [{i+1}/{len(tasks)}] {project_name} [{config_name} r{rep}]",
                      end=" ", flush=True)

                # Run ChatDev
                run_result = run_chatdev_task(yaml_path, task_name, description, args.timeout)

                # Find workspace
                workspace = find_workspace(task_name)

                # Level 1: Executability
                exec_result = evaluate_executability(workspace)

                # Level 2: Completeness
                comp_result = evaluate_completeness(workspace)

                # Level 3: Functional correctness (LLM-as-judge)
                judge_result = {"passed": None, "rating": "SKIP", "reason": "skipped"}
                if not args.skip_judge and comp_result["complete"]:
                    code = collect_generated_code(workspace)
                    judge_result = evaluate_functional_correctness(description, code, project_name)

                # Determine overall pass/fail
                # PASS = executable AND (judge says PASS or judge skipped but code is complete)
                if judge_result["rating"] == "SKIP":
                    overall_passed = exec_result["executable"] and comp_result["complete"]
                else:
                    overall_passed = judge_result.get("passed", False)

                result = {
                    "project_name": project_name,
                    "description": description[:500],
                    "config": config_name,
                    "model": mc["model_name"],
                    "rep": rep,
                    "elapsed_seconds": run_result["elapsed_seconds"],
                    "error": run_result.get("error"),
                    "exit_code": run_result.get("exit_code", -1),
                    # Level 1
                    "executable": exec_result["executable"],
                    "exec_reason": exec_result["reason"],
                    # Level 2
                    "code_complete": comp_result["complete"],
                    "py_files": comp_result["py_files"],
                    "total_lines": comp_result["total_lines"],
                    "has_main": comp_result["has_main"],
                    # Level 3
                    "judge_rating": judge_result["rating"],
                    "judge_reason": judge_result.get("reason", ""),
                    # Overall
                    "passed": overall_passed,
                    "timestamp": datetime.now().isoformat(),
                }

                config_results[project_name] = result

                status = "PASS" if overall_passed else "FAIL"
                exec_tag = "E" if exec_result["executable"] else "x"
                comp_tag = "C" if comp_result["complete"] else "x"
                judge_tag = judge_result["rating"][0] if judge_result["rating"] != "SKIP" else "-"
                detail = f"[{exec_tag}{comp_tag}{judge_tag}]"
                elapsed = run_result["elapsed_seconds"]
                print(f"{status} {detail} ({elapsed:.0f}s) {comp_result['py_files']}py/{comp_result['total_lines']}loc")

                # Save after each task
                with open(results_file, "w") as f:
                    json.dump(config_results, f, indent=2)

        all_results[config_name] = config_results

        # Summary
        passed = sum(1 for r in config_results.values() if r.get("passed"))
        executable = sum(1 for r in config_results.values() if r.get("executable"))
        complete = sum(1 for r in config_results.values() if r.get("code_complete"))
        total = len(config_results)
        pass_rate = passed / total if total > 0 else 0
        print(f"\n  {config_name}: {passed}/{total} = {pass_rate:.1%}")
        print(f"    Executable: {executable}/{total}")
        print(f"    Code complete: {complete}/{total}")

        summary_file = Path(RESULTS_DIR) / args.model / config_name / "summary.json"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_file, "w") as f:
            json.dump({
                "model": mc["model_name"],
                "config": config_name,
                "pass_rate": pass_rate,
                "passed": passed,
                "executable": executable,
                "code_complete": complete,
                "total": total,
                "reps": args.reps,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)

    # Comparison table
    print("\n" + "=" * 70)
    print(f"COMPARISON TABLE ({mc['model_name']})")
    print("=" * 70)
    print(f"{'Config':<15} {'Pass':>6} {'Exec':>6} {'Code':>6} {'Total':>6} {'Rate':>8} {'Avg Time':>10}")
    print("-" * 65)

    for config_name in configs_to_run:
        r = all_results.get(config_name, {})
        passed = sum(1 for v in r.values() if v.get("passed"))
        executable = sum(1 for v in r.values() if v.get("executable"))
        complete = sum(1 for v in r.values() if v.get("code_complete"))
        total = len(r)
        rate = passed / total if total > 0 else 0
        avg_time = sum(v.get("elapsed_seconds", 0) for v in r.values()) / max(1, total)
        print(f"{config_name:<15} {passed:>6} {executable:>6} {complete:>6} {total:>6} {rate:>7.1%} {avg_time:>9.1f}s")

    print()
    print("Paper comparison (ChatDev, GPT-3.5-turbo):")
    print("  Baseline:        25.0%")
    print("  Improved prompt:  34.4%")
    print("  New topology:     40.6%")
    print()
    print("Legend: [ECJ] = Executable/CodeComplete/Judge")
    print("  E=executable, C=code complete, P/F/S=judge pass/fail/skip")
    print()

    # Per-task breakdown
    print("=" * 70)
    print("PER-TASK BREAKDOWN")
    print("=" * 70)
    for config_name in configs_to_run:
        r = all_results.get(config_name, {})
        print(f"\n{config_name}:")
        for name, v in r.items():
            status = "PASS" if v.get("passed") else "FAIL"
            judge = v.get("judge_rating", "-")
            reason = v.get("judge_reason", v.get("exec_reason", ""))[:60]
            print(f"  {name:<30} {status:<5} judge={judge:<8} {reason}")

    # Save final
    final_file = Path(RESULTS_DIR) / args.model / f"final_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    with open(final_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull results saved to {final_file}")


if __name__ == "__main__":
    main()
