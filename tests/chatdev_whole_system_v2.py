#!/usr/bin/env python3
"""ChatDev Whole-System Validation Experiment v2

Runs HumanEval benchmark through ChatDev with 3 configurations:
1. Baseline (no MAST defenses)  
2. MAST-hardened (prompt-only defenses)
3. MAST + MCP enforcement (prompt + structural)

Measures task completion rate (pass@1) on HumanEval using the
canonical human-eval execution framework. This gives us the SAME
metric the paper uses for their ChatDev case studies.

The paper reports:
- ChatDev baseline: 25.0% (ProgramDev), 89.6% (HumanEval)
- ChatDev prompt fix: 34.4% (ProgramDev), 90.3% (HumanEval)
- ChatDev topology fix: 40.6% (ProgramDev), 91.5% (HumanEval)

Our experiment uses HumanEval, so direct comparison to 89.6% baseline
is possible. The paper used GPT-3.5-turbo; we use gemma4:31b-cloud,
so numbers won't match exactly but the *improvement* is what matters.

Usage:
    cd /tmp/mast-skills
    python3 -u tests/chatdev_whole_system_v2.py --subset 10 --reps 3

    # Resume interrupted run
    python3 -u tests/chatdev_whole_system_v2.py --subset 10 --reps 3 --resume

    # Single config for quick test
    python3 -u tests/chatdev_whole_system_v2.py --config baseline --subset 3 --reps 1
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# --- Configuration ---

CHATDEV_DIR = os.environ.get(
    "CHATDEV_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ChatDev")
)
CHATDEV_DIR = os.path.abspath(CHATDEV_DIR)

RESULTS_DIR = os.environ.get(
    "MAST_RESULTS_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "whole_system")
)

TIMEOUT_SECONDS = 600  # 10 min per problem

YAML_CONFIGS = {
    "baseline": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_gw.yaml"),
    "mast": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_mast_gw.yaml"),
    "mcp": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_mcp_enforced.yaml"),
}

# HumanEval problems to test (we select a varied subset)
HUMANEVAL_SUBSET = [
    "HumanEval/0",   # has_close_elements - easy
    "HumanEval/2",   # decode_cjk - medium
    "HumanEval/4",   # find_zero - hard (numerical)
    "HumanEval/10",  # make_palindrome - medium
    "HumanEval/17",  # parse_music - medium
    "HumanEval/24",  # factorial - easy
    "HumanEval/37",  # sort_even - medium
    "HumanEval/48",  # is_palindrome - easy
    "HumanEval/53",  # add - easy
    "HumanEval/64",  # vowels_count - easy
    "HumanEval/71",  # triangle_area - easy
    "HumanEval/81",  # numerical_letter_grade - medium
    "HumanEval/89",  # encrypt - medium
    "HumanEval/96",  # count_up_to - medium
    "HumanEval/109", # move_one_ball - medium
    "HumanEval/117", # select_words - medium
    "HumanEval/128", # prod_signs - easy
    "HumanEval/137", # compare - easy
    "HumanEval/149", # sorted_list_sum - medium
    "HumanEval/159", # eat - easy
]


def load_human_eval_problem(task_id: str) -> dict:
    """Load a single HumanEval problem by task_id."""
    from human_eval.data import read_problems
    problems = read_problems()
    if task_id not in problems:
        raise ValueError(f"Task {task_id} not found in HumanEval")
    return problems[task_id]


def format_chatdev_prompt(problem: dict) -> str:
    """Format a HumanEval problem as a ChatDev task description.
    
    ChatDev works best with natural language task descriptions, not bare
    function stubs. We provide the signature and docstring clearly.
    """
    entry_point = problem["entry_point"]
    prompt = problem["prompt"]
    
    return (
        f"Implement the Python function `{entry_point}` according to the "
        f"following specification.\n\n"
        f"```python\n{prompt}\n```\n\n"
        f"The function must pass all the examples given in the docstring. "
        f"Write only the function implementation (including the function "
        f"signature and body). Do not add any extra code, imports not "
        f"needed, or test code."
    )


def run_chatdev_problem(yaml_config: str, task_name: str, task_prompt: str,
                        timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run a single problem through ChatDev.
    
    Returns the WareHouse directory path and metadata.
    """
    env = {
        **os.environ,
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "ollama"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"),
    }
    
    start_time = datetime.now()
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(CHATDEV_DIR, "run.py"),
             "--path", yaml_config, "--name", task_name],
            input=task_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=CHATDEV_DIR,
            env=env,
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": proc.stdout[-5000:] if proc.stdout else "",
            "stderr": proc.stderr[-5000:] if proc.stderr else "",
            "elapsed_seconds": elapsed,
            "exit_code": proc.returncode,
            "error": None,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "stdout": e.stdout[:5000] if e.stdout else "",
            "stderr": e.stderr[:5000] if e.stderr else "",
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


def extract_function_code(code: str, entry_point: str) -> str:
    """Extract just the target function from a ChatDev-generated file.
    
    ChatDev produces multi-file projects with imports, docstrings, and test
    harnesses. HumanEval's check_correctness expects just the function body
    (which gets appended to the prompt). We need to:
    1. Find the target function by name
    2. Include necessary imports from the file header
    3. Strip test harnesses, main blocks, and utility functions
    """
    # Find the function definition with proper indentation tracking
    pattern = rf'(def {re.escape(entry_point)}\s*\([^)]*\)[^:]*:.*?)(?=\ndef\s+\w+|\Z)'
    match = re.search(pattern, code, re.DOTALL)
    
    if match:
        func_body = match.group(1).rstrip()
    else:
        # Fallback: return lines between first 'def entry_point' and next top-level def
        lines = code.split('\n')
        func_lines = []
        in_func = False
        for line in lines:
            if line.startswith(f'def {entry_point}'):
                in_func = True
            if in_func:
                # Stop at next top-level definition
                if line and not line[0].isspace() and not line.startswith('def ') and line not in ('', '"""', "'''"):
                    break
                func_lines.append(line)
        func_body = '\n'.join(func_lines).rstrip()
    
    if not func_body:
        return code  # Return raw if extraction fails
    
    # Check which imports the function needs
    needed_imports = []
    import_lines = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')):
            import_lines.append(stripped)
    
    # Check if function uses any imported names
    for imp_line in import_lines:
        # Extract names from import
        if imp_line.startswith('from '):
            # "from typing import List" -> check for "List" in func_body
            parts = imp_line.split(' import ')
            if len(parts) == 2:
                names = [n.strip() for n in parts[1].split(',')]
                for name in names:
                    name = name.split(' as ')[0].strip()  # handle "X as Y"
                    if re.search(rf'\b{re.escape(name)}\b', func_body):
                        needed_imports.append(imp_line)
                        break
        elif imp_line.startswith('import '):
            # "import math" -> check for "math." in func_body
            module = imp_line.replace('import ', '').split(' as ')[0].strip()
            if re.search(rf'\b{re.escape(module)}\b', func_body):
                needed_imports.append(imp_line)
    
    # Combine imports + function
    if needed_imports:
        return '\n'.join(needed_imports) + '\n\n' + func_body
def extract_code_from_warehouse(task_name: str, entry_point: str = "") -> str:
    """Extract Python code from ChatDev's WareHouse output.
    
    ChatDev v2 stores code in code_workspace/ directory. We find the 
    file containing the target function and extract just that function
    (with needed imports) for HumanEval evaluation.
    """
    warehouse = os.path.join(CHATDEV_DIR, "WareHouse")
    
    # Find the most recent directory matching this task name
    matching_dirs = sorted(
        [d for d in os.listdir(warehouse) if d.startswith(task_name)],
        reverse=True
    )
    
    if not matching_dirs:
        return ""
    
    task_dir = os.path.join(warehouse, matching_dirs[0])
    raw_code = ""
    
    # Strategy 1: Look for .py files in code_workspace
    code_ws = os.path.join(task_dir, "code_workspace")
    if os.path.isdir(code_ws):
        non_venv_files = []
        for f in os.listdir(code_ws):
            fpath = os.path.join(code_ws, f)
            if (f.endswith('.py') and f != '__init__.py' 
                and not os.path.isdir(fpath) and '.venv' not in fpath):
                non_venv_files.append(fpath)
        
        if non_venv_files:
            # Prefer solution.py (ChatDev's convention for the implementation)
            for preferred in ['solution.py']:
                preferred_path = os.path.join(code_ws, preferred)
                if os.path.exists(preferred_path):
                    with open(preferred_path, errors='replace') as fh:
                        raw_code = fh.read()
                    # Fix common ChatDev output issues
                    raw_code = raw_code.lstrip('\ufeff')  # Strip UTF-8 BOM
                    raw_code = raw_code.replace('\\"', '"')   # Unescape quotes
                    break
            
            if not raw_code:
                # Find the file containing the target function
                for f in non_venv_files:
                    with open(f, errors='replace') as fh:
                        content = fh.read()
                    content = content.lstrip('\ufeff')  # Strip UTF-8 BOM
                    content = content.replace('\\"', '"')   # Unescape quotes
                    if entry_point and f'def {entry_point}' in content:
                        raw_code = content
                        break
                
                if not raw_code:
                    # Last resort: largest .py file with function definitions
                    for f in non_venv_files:
                        with open(f, errors='replace') as fh:
                            content = fh.read()
                        content = content.lstrip('\ufeff').replace('\\"', '"')
                        if re.search(r'^def\s+\w+', content, re.MULTILINE):
                            raw_code = content
                            break
    
    # Strategy 2: Extract from node_outputs.yaml if no code_workspace
    if not raw_code:
        node_outputs = os.path.join(task_dir, "node_outputs.yaml")
        if os.path.exists(node_outputs):
            import yaml
            with open(node_outputs) as f:
                data = yaml.safe_load(f)
            
            for node_name in ['node_Programmer Code Complete', 'node_Programmer Coding']:
                if node_name in data:
                    results = data[node_name].get('results', [])
                    for r in results:
                        payload = r.get('payload', {})
                        content = payload.get('content', '')
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get('type') == 'text':
                                    text = c.get('text', '')
                                    code_blocks = re.findall(r'```python\n(.*?)```', text, re.DOTALL)
                                    if code_blocks:
                                        raw_code = code_blocks[-1].strip()
                                        break
                        elif isinstance(content, str) and 'def ' in content:
                            code_blocks = re.findall(r'```python\n(.*?)```', content, re.DOTALL)
                            if code_blocks:
                                raw_code = code_blocks[-1].strip()
    
    if not raw_code:
        return ""
    
    # Extract just the target function for HumanEval evaluation
    if entry_point:
        return extract_function_code(raw_code, entry_point)
    return raw_code


def evaluate_code(task_id: str, code: str) -> dict:
    """Evaluate extracted code against HumanEval test suite.
    
    Uses the human-eval execution framework for pass@1.
    """
    from human_eval.execution import check_correctness
    from human_eval.data import read_problems
    
    problems = read_problems()
    problem = problems[task_id]
    
    # Construct the full program: prompt + completion
    completion = code
    # Remove duplicate function signature if code includes it
    if completion.strip().startswith(problem["prompt"].strip()):
        program = completion
    else:
        program = problem["prompt"] + completion
    
    try:
        result = check_correctness(problem, completion, timeout=10.0)
        return {
            "passed": result["passed"],
            "result": result["result"],
            "completion": completion,
        }
    except Exception as e:
        return {
            "passed": False,
            "result": f"Evaluation error: {str(e)[:200]}",
            "completion": completion,
        }


def main():
    parser = argparse.ArgumentParser(
        description="ChatDev whole-system validation (HumanEval benchmark)")
    parser.add_argument("--config",
        choices=["baseline", "mast", "mcp", "all"],
        default="all",
        help="Which config(s) to test")
    parser.add_argument("--subset", type=int, default=10,
        help="Number of HumanEval problems (0=all)")
    parser.add_argument("--reps", type=int, default=3,
        help="Repetitions per problem (paper uses 6)")
    parser.add_argument("--resume", action="store_true",
        help="Resume from interrupted run")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS,
        help="Timeout per problem in seconds")
    parser.add_argument("--skip-eval", action="store_true",
        help="Skip evaluation (just run ChatDev, don't evaluate)")
    args = parser.parse_args()
    
    # Validate ChatDev
    run_py = os.path.join(CHATDEV_DIR, "run.py")
    if not os.path.isfile(run_py):
        print(f"ERROR: ChatDev not found at {CHATDEV_DIR}")
        sys.exit(1)
    
    configs_to_run = ["baseline", "mast", "mcp"] if args.config == "all" else [args.config]
    
    for cfg in configs_to_run:
        if not os.path.isfile(YAML_CONFIGS[cfg]):
            print(f"ERROR: Config '{cfg}' YAML not found: {YAML_CONFIGS[cfg]}")
            sys.exit(1)
    
    # Select problems
    problem_ids = HUMANEVAL_SUBSET[:args.subset] if args.subset > 0 else list(range(164))
    
    print("=" * 70)
    print("CHATDEV WHOLE-SYSTEM VALIDATION (HumanEval v2)")
    print("=" * 70)
    print(f"Configs: {configs_to_run}")
    print(f"Problems: {len(problem_ids)}")
    print(f"Reps: {args.reps}")
    print(f"Timeout: {args.timeout}s")
    print(f"Results: {RESULTS_DIR}")
    est_min = len(problem_ids) * len(configs_to_run) * args.reps * 3
    print(f"Est. time: ~{est_min:.0f} min ({est_min/60:.1f} hrs)")
    print()
    
    # Load problems
    from human_eval.data import read_problems
    all_problems = read_problems()
    
    problems = []
    for pid in problem_ids:
        if pid in all_problems:
            problems.append((pid, all_problems[pid]))
        else:
            print(f"WARNING: {pid} not found in HumanEval, skipping")
    
    # Run experiments
    all_results = {}
    
    for config_name in configs_to_run:
        yaml_path = YAML_CONFIGS[config_name]
        config_results = {}
        
        for rep in range(1, args.reps + 1):
            results_dir = Path(RESULTS_DIR) / config_name / f"rep{rep}"
            results_dir.mkdir(parents=True, exist_ok=True)
            
            # Load existing if resuming
            results_file = results_dir / "results.json"
            existing = {}
            if args.resume and results_file.exists():
                with open(results_file) as f:
                    existing = json.load(f)
            
            for i, (task_id, problem) in enumerate(problems):
                entry_point = problem["entry_point"]
                
                if task_id in existing and args.resume:
                    print(f"  [{i+1}/{len(problems)}] {task_id} ({entry_point}) - SKIP (resume)")
                    config_results[task_id] = existing[task_id]
                    continue
                
                task_name = f"he_{task_id.replace('/', '_')}_{config_name}_r{rep}"
                task_prompt = format_chatdev_prompt(problem)
                
                print(f"  [{i+1}/{len(problems)}] {task_id} ({entry_point}) [{config_name} r{rep}]", 
                      end=" ", flush=True)
                
                # Run ChatDev
                start = time.time()
                run_result = run_chatdev_problem(yaml_path, task_name, task_prompt, args.timeout)
                elapsed = time.time() - start
                
                # Extract code
                extracted_code = extract_code_from_warehouse(task_name, entry_point)
                
                # Evaluate
                eval_result = {"passed": False, "result": "no code extracted"}
                if extracted_code and not args.skip_eval:
                    eval_result = evaluate_code(task_id, extracted_code)
                elif args.skip_eval:
                    eval_result = {"passed": None, "result": "skipped", "completion": extracted_code}
                
                result = {
                    "task_id": task_id,
                    "entry_point": entry_point,
                    "config": config_name,
                    "rep": rep,
                    "elapsed_seconds": elapsed,
                    "error": run_result.get("error"),
                    "exit_code": run_result.get("exit_code", -1),
                    "extracted_code": extracted_code[:2000] if extracted_code else "",
                    "code_length": len(extracted_code) if extracted_code else 0,
                    "passed": eval_result.get("passed"),
                    "eval_result": eval_result.get("result", ""),
                    "timestamp": datetime.now().isoformat(),
                }
                
                config_results[task_id] = result
                status = "PASS" if result["passed"] else "FAIL" if result["passed"] is False else "SKIP"
                print(f"{status} ({elapsed:.0f}s)")
                
                # Save after each problem for resume support
                with open(results_file, 'w') as f:
                    json.dump(config_results, f, indent=2)
        
        all_results[config_name] = config_results
        
        # Compute pass@1
        passed = sum(1 for r in config_results.values() if r.get("passed"))
        total = len(config_results)
        pass_at_1 = passed / total if total > 0 else 0
        print(f"\n  {config_name}: pass@1 = {passed}/{total} = {pass_at_1:.1%}")
        
        # Save eval summary
        summary_file = Path(RESULTS_DIR) / config_name / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump({
                "config": config_name,
                "pass_at_1": pass_at_1,
                "passed": passed,
                "total": total,
                "problems": problem_ids,
                "reps": args.reps,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)
    
    # Comparison table
    print("\n" + "=" * 70)
    print("COMPARISON TABLE")
    print("=" * 70)
    print(f"{'Config':<15} {'pass@1':>8} {'Passed':>8} {'Total':>8} {'Avg Time':>10}")
    print("-" * 55)
    
    for config_name in configs_to_run:
        r = all_results.get(config_name, {})
        passed = sum(1 for v in r.values() if v.get("passed"))
        total = len(r)
        pass_at_1 = passed / total if total > 0 else 0
        avg_time = sum(v.get("elapsed_seconds", 0) for v in r.values()) / max(1, total)
        print(f"{config_name:<15} {pass_at_1:>7.1%} {passed:>8} {total:>8} {avg_time:>9.1f}s")
    
    print()
    print("Paper comparison (GPT-3.5-turbo, different model):")
    print(f"  Paper baseline:        89.6% (HumanEval)")
    print(f"  Paper prompt fix:      90.3% (HumanEval)")
    print(f"  Paper topology fix:    91.5% (HumanEval)")
    print()
    
    # Save combined results
    final_file = Path(RESULTS_DIR) / f"final_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(final_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Full results saved to {final_file}")


if __name__ == "__main__":
    main()