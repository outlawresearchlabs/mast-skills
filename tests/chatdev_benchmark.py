#!/usr/bin/env python3
"""ChatDev Whole-System Benchmark (Publication-Ready)

Runs HumanEval benchmark through ChatDev with 3 configurations x 2 models:
- baseline: No MAST defenses
- mast: MAST prompt-only defenses
- mcp: MAST structural enforcement (MCP tools + state gates)

Models:
- gemma4:31b-cloud (local Ollama gateway)
- gpt-4o (OpenAI API)

Produces publication-ready results for a position paper on MAST structural enforcement.

Usage:
    # Full benchmark: 3 configs x 2 models x 25 problems x 2 reps
    cd /tmp/mast-skills
    python3 -u tests/chatdev_benchmark.py --model gemma4 --subset 20 --reps 2
    python3 -u tests/chatdev_benchmark.py --model gpt4o --subset 20 --reps 2
    OPENAI_API_KEY=sk-xxx OPENAI_BASE_URL=https://api.openai.com/v1 python3 -u tests/chatdev_benchmark.py --model gpt4o --subset 20

    # Quick test
    python3 -u tests/chatdev_benchmark.py --model gemma4 --config baseline --subset 3 --reps 1 --timeout 600

    # Resume interrupted run
    python3 -u tests/chatdev_benchmark.py --model gemma4 --subset 20 --reps 2 --resume
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
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "benchmark")
)

TIMEOUT_SECONDS = 900  # 15 min per problem (MCP runs take longer)

# Model-specific configs
MODEL_CONFIGS = {
    "gemma4": {
        "model_name": "gemma4:31b-cloud",
        "base_url": os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key": os.environ.get("OPENAI_API_KEY", "ollama"),
        "yaml_configs": {
            "baseline": "ChatDev_v1_gw.yaml",
            "mast": "ChatDev_v1_mast_gw.yaml",
            "mcp": "ChatDev_v1_mcp_enforced.yaml",
            "lean": "ChatDev_v1_lean_gw.yaml",
            "inprocess": "ChatDev_v1_inprocess_gw.yaml",
        },
    },
    "gpt4o": {
        "model_name": "gpt-4o",
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "yaml_configs": {
            "baseline": "ChatDev_v1_gpt4o_baseline.yaml",
            "mast": "ChatDev_v1_mast_gpt4o.yaml",
            "mcp": "ChatDev_v1_mcp_gpt4o.yaml",
            "structural": "ChatDev_v1_structural_gpt4o.yaml",
            "lean": "ChatDev_v1_lean_gpt4o.yaml",
            "inprocess": "ChatDev_v1_inprocess_gpt4o.yaml",
        },
    },
    "gpt54": {
        "model_name": "gpt-5.4",
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_gpt54.yaml",
            "inprocess": "ChatDev_v1_inprocess_gpt54.yaml",
        },
    },
    "opus47": {
        "model_name": "claude-opus-4-7",
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_opus.yaml",
            "inprocess": "ChatDev_v1_inprocess_opus.yaml",
        },
    },
    "glm51": {
        "model_name": "glm-5.1:cloud",
        "base_url": os.environ.get("BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key": os.environ.get("API_KEY", "ollama"),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_glm51.yaml",
            "inprocess": "ChatDev_v1_inprocess_glm51.yaml",
        },
    },
    "gemma4moe": {
        "model_name": "gemma-4-26b-a4b-it",
        "base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        "api_key": os.environ.get("GEMINI_API_KEY", ""),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_gemma4moe.yaml",
            "inprocess": "ChatDev_v1_inprocess_gemma4moe.yaml",
        },
    },
    "qwen35": {
        "model_name": "qwen3.5:397b-cloud",
        "base_url": os.environ.get("BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key": os.environ.get("API_KEY", "ollama"),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_qwen35.yaml",
            "inprocess": "ChatDev_v1_inprocess_qwen35.yaml",
        },
    },
    "minimax": {
        "model_name": "MiniMax-M2.7",
        "base_url": os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
        "api_key": os.environ.get("MINIMAX_API_KEY", ""),
        "yaml_configs": {
            "baseline": "ChatDev_v1_baseline_minimax.yaml",
            "inprocess": "ChatDev_v1_inprocess_minimax.yaml",
        },
    },
}

# HumanEval problems -- selected for diversity and FM-1.1 vulnerability
# Mixed easy/medium/hard, with emphasis on function-name-misleading specs
HUMANEVAL_SUBSET = [
    # FM-1.1 vulnerable (function name suggests different behavior than spec)
    "HumanEval/0",    # has_close_elements - easy, clear spec
    "HumanEval/2",    # truncate_number - THE canonical FM-1.1 failure
    "HumanEval/17",   # parse_music - another FM-1.1 failure we've seen
    "HumanEval/37",   # sort_even - name could mislead
    "HumanEval/89",   # encrypt - name could mislead
    "HumanEval/96",   # count_up_to - name ambiguous
    # Medium difficulty
    "HumanEval/4",    # mean_absolute_deviation - easy, we've tested
    "HumanEval/10",   # make_palindrome - medium
    "HumanEval/24",   # factorial - easy
    "HumanEval/48",   # is_palindrome - easy
    "HumanEval/53",   # add - easy
    "HumanEval/64",   # vowels_count - easy
    "HumanEval/71",   # triangle_area - easy
    "HumanEval/81",   # numerical_letter_grade - medium
    "HumanEval/109",  # move_one_ball - medium
    "HumanEval/117",  # select_words - medium
    "HumanEval/128",  # prod_signs - easy
    "HumanEval/137",  # compare - easy
    "HumanEval/149",  # sorted_list_sum - medium
    "HumanEval/159",  # eat - easy
    # Extra for statistical power
    "HumanEval/1",    # separate_paren_groups
    "HumanEval/5",    # intersperse
    "HumanEval/14",   # all_prefixes
    "HumanEval/32",   # find_zero
    "HumanEval/55",   # fibfib
]


def load_human_eval_problem(task_id: str) -> dict:
    """Load a single HumanEval problem by task_id."""
    from human_eval.data import read_problems
    problems = read_problems()
    if task_id not in problems:
        raise ValueError(f"Task {task_id} not found in HumanEval")
    return problems[task_id]


def format_chatdev_prompt(problem: dict) -> str:
    """Format a HumanEval problem as a ChatDev task description."""
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
                        base_url: str, api_key: str,
                        timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run a single problem through ChatDev.
    
    Returns the run metadata (not the code -- extract from WareHouse).
    """
    env = {
        **os.environ,
        "OPENAI_API_KEY": api_key,
        "OPENAI_BASE_URL": base_url,
        "BASE_URL": base_url,
        "API_KEY": api_key,
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
    """Extract just the target function from a ChatDev-generated file."""
    pattern = rf'(def {re.escape(entry_point)}\s*\([^)]*\)[^:]*:.*?)(?=\ndef\s+\w+|\Z)'
    match = re.search(pattern, code, re.DOTALL)
    
    if match:
        func_body = match.group(1).rstrip()
    else:
        lines = code.split('\n')
        func_lines = []
        in_func = False
        for line in lines:
            if line.startswith(f'def {entry_point}'):
                in_func = True
            if in_func:
                if line and not line[0].isspace() and not line.startswith('def ') and line not in ('', '"""', "'''"):
                    break
                func_lines.append(line)
        func_body = '\n'.join(func_lines).rstrip()
    
    if not func_body:
        return code
    
    needed_imports = []
    import_lines = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')):
            import_lines.append(stripped)
    
    for imp_line in import_lines:
        if imp_line.startswith('from '):
            parts = imp_line.split(' import ')
            if len(parts) == 2:
                names = [n.strip() for n in parts[1].split(',')]
                for name in names:
                    name = name.split(' as ')[0].strip()
                    if re.search(rf'\b{re.escape(name)}\b', func_body):
                        needed_imports.append(imp_line)
                        break
        elif imp_line.startswith('import '):
            module = imp_line.replace('import ', '').split(' as ')[0].strip()
            if re.search(rf'\b{re.escape(module)}\b', func_body):
                needed_imports.append(imp_line)
    
    if needed_imports:
        return '\n'.join(needed_imports) + '\n\n' + func_body
    return func_body


def extract_code_from_warehouse(task_name: str, entry_point: str = "") -> str:
    """Extract Python code from ChatDev's WareHouse output."""
    warehouse = os.path.join(CHATDEV_DIR, "WareHouse")
    
    matching_dirs = sorted(
        [d for d in os.listdir(warehouse) if d.startswith(task_name)],
        reverse=True
    )
    
    if not matching_dirs:
        return ""
    
    task_dir = os.path.join(warehouse, matching_dirs[0])
    raw_code = ""
    
    code_ws = os.path.join(task_dir, "code_workspace")
    if os.path.isdir(code_ws):
        non_venv_files = []
        for f in os.listdir(code_ws):
            fpath = os.path.join(code_ws, f)
            if (f.endswith('.py') and f != '__init__.py' 
                and not os.path.isdir(fpath) and '.venv' not in fpath):
                non_venv_files.append(fpath)
        
        if non_venv_files:
            for preferred in ['solution.py']:
                preferred_path = os.path.join(code_ws, preferred)
                if os.path.exists(preferred_path):
                    with open(preferred_path, errors='replace') as fh:
                        raw_code = fh.read()
                    raw_code = raw_code.lstrip('\ufeff').replace('\\"', '"')
                    break
            
            if not raw_code:
                for f in non_venv_files:
                    with open(f, errors='replace') as fh:
                        content = fh.read()
                    content = content.lstrip('\ufeff').replace('\\"', '"')
                    if entry_point and f'def {entry_point}' in content:
                        raw_code = content
                        break
                
                if not raw_code:
                    for f in non_venv_files:
                        with open(f, errors='replace') as fh:
                            content = fh.read()
                        content = content.lstrip('\ufeff').replace('\\"', '"')
                        if re.search(r'^def\s+\w+', content, re.MULTILINE):
                            raw_code = content
                            break
    
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
    
    if entry_point:
        return extract_function_code(raw_code, entry_point)
    return raw_code


def evaluate_code(task_id: str, code: str) -> dict:
    """Evaluate extracted code against HumanEval test suite."""
    from human_eval.execution import check_correctness
    from human_eval.data import read_problems
    
    problems = read_problems()
    problem = problems[task_id]
    
    try:
        result = check_correctness(problem, code, timeout=10.0)
        return {
            "passed": result["passed"],
            "result": result["result"],
            "completion": code[:2000],
        }
    except Exception as e:
        return {
            "passed": False,
            "result": f"Evaluation error: {str(e)[:200]}",
            "completion": code[:2000],
        }


def analyze_failure_mode(task_id: str, code: str, problem: dict) -> str:
    """Classify pass/fail and identify likely MAST failure mode."""
    entry_point = problem["entry_point"]
    prompt = problem["prompt"]
    
    if not code:
        return "FM-1.1: no code produced"
    
    # Extract function signature from the spec
    spec_sig_match = re.search(rf'def {re.escape(entry_point)}\s*\([^)]*\)', prompt)
    
    # Check if the implementation has a different signature than the spec
    impl_sig_match = re.search(rf'def {re.escape(entry_point)}\s*\([^)]*\)', code)
    
    if spec_sig_match and impl_sig_match:
        spec_params = spec_sig_match.group(0)
        impl_params = impl_sig_match.group(0)
        if spec_params != impl_params:
            return f"FM-1.1: signature mismatch ({impl_params} vs {spec_params})"
    
    # Check for common FM-1.1 patterns
    spec_lines = [l.strip() for l in prompt.split('\n') if l.strip()]
    
    return "unknown"  # Will be refined by actual evaluation


def main():
    parser = argparse.ArgumentParser(
        description="ChatDev whole-system benchmark (publication-ready)")
    parser.add_argument("--model", choices=["gemma4", "gpt4o", "gpt54", "opus47", "glm51", "gemma4moe", "qwen35", "minimax"], required=True,
        help="Which model to test")
    parser.add_argument("--config",
        choices=["baseline", "mast", "mcp", "structural", "lean", "inprocess", "all"],
        default="all",
        help="Which config(s) to test")
    parser.add_argument("--subset", type=int, default=20,
        help="Number of HumanEval problems (0=all 164)")
    parser.add_argument("--reps", type=int, default=2,
        help="Repetitions per problem")
    parser.add_argument("--resume", action="store_true",
        help="Resume from interrupted run")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS,
        help="Timeout per problem in seconds")
    parser.add_argument("--skip-eval", action="store_true",
        help="Skip evaluation (just run ChatDev)")
    args = parser.parse_args()
    
    mc = MODEL_CONFIGS[args.model]
    configs_to_run = ["baseline", "mast", "structural", "lean", "inprocess"] if args.config == "all" else [args.config]
    
    # Validate API key
    if not mc["api_key"]:
        print(f"ERROR: No API key for {args.model}. Set OPENAI_API_KEY environment variable.")
        sys.exit(1)
    
    # Validate YAML configs exist
    yaml_dir = os.path.join(CHATDEV_DIR, "yaml_instance")
    for cfg in configs_to_run:
        yaml_path = os.path.join(yaml_dir, mc["yaml_configs"][cfg])
        if not os.path.isfile(yaml_path):
            print(f"ERROR: Config '{cfg}' YAML not found: {yaml_path}")
            sys.exit(1)
    
    # Validate ChatDev
    run_py = os.path.join(CHATDEV_DIR, "run.py")
    if not os.path.isfile(run_py):
        print(f"ERROR: ChatDev not found at {CHATDEV_DIR}")
        sys.exit(1)
    
    # Select problems
    problem_ids = HUMANEVAL_SUBSET[:args.subset] if args.subset > 0 else list(range(164))
    
    # Load problems
    from human_eval.data import read_problems
    all_problems = read_problems()
    
    problems = []
    for pid in problem_ids:
        if pid in all_problems:
            problems.append((pid, all_problems[pid]))
        else:
            print(f"WARNING: {pid} not found in HumanEval, skipping")
    
    total_runs = len(problems) * len(configs_to_run) * args.reps
    est_min = total_runs * 5  # ~5 min average per run
    
    print("=" * 70)
    print("CHATDEV WHOLE-SYSTEM BENCHMARK (Publication-Ready)")
    print("=" * 70)
    print(f"Model: {mc['model_name']}")
    print(f"Base URL: {mc['base_url']}")
    print(f"Configs: {configs_to_run}")
    print(f"Problems: {len(problems)}")
    print(f"Reps: {args.reps}")
    print(f"Timeout: {args.timeout}s")
    print(f"Total runs: {total_runs}")
    print(f"Est. time: ~{est_min:.0f} min ({est_min/60:.1f} hrs)")
    print(f"Results dir: {RESULTS_DIR}")
    print()
    
    # Run experiments
    all_results = {}
    
    for config_name in configs_to_run:
        yaml_path = os.path.join(yaml_dir, mc["yaml_configs"][config_name])
        config_results = {}
        
        for rep in range(1, args.reps + 1):
            results_dir = Path(RESULTS_DIR) / args.model / config_name / f"rep{rep}"
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
                    print(f"  [{i+1}/{len(problems)}] {task_id} ({entry_point}) [{config_name} r{rep}] - SKIP (resume)")
                    config_results[task_id] = existing[task_id]
                    continue
                
                task_name = f"bm_{task_id.replace('/', '_')}_{args.model}_{config_name}_r{rep}"
                task_prompt = format_chatdev_prompt(problem)
                
                print(f"  [{i+1}/{len(problems)}] {task_id} ({entry_point}) [{config_name} r{rep}]",
                      end=" ", flush=True)
                
                # Run ChatDev
                start = time.time()
                run_result = run_chatdev_problem(
                    yaml_path, task_name, task_prompt,
                    mc["base_url"], mc["api_key"],
                    args.timeout
                )
                elapsed = time.time() - start
                
                # Extract code
                extracted_code = extract_code_from_warehouse(task_name, entry_point)
                
                # Evaluate
                eval_result = {"passed": False, "result": "no code extracted"}
                if extracted_code and not args.skip_eval:
                    eval_result = evaluate_code(task_id, extracted_code)
                elif args.skip_eval:
                    eval_result = {"passed": None, "result": "skipped", "completion": extracted_code}
                
                # Classify failure mode
                failure_mode = None
                if not eval_result.get("passed", False):
                    failure_mode = analyze_failure_mode(task_id, extracted_code or "", problem)
                
                result = {
                    "task_id": task_id,
                    "entry_point": entry_point,
                    "config": config_name,
                    "model": mc["model_name"],
                    "rep": rep,
                    "elapsed_seconds": elapsed,
                    "error": run_result.get("error"),
                    "exit_code": run_result.get("exit_code", -1),
                    "extracted_code": extracted_code[:2000] if extracted_code else "",
                    "code_length": len(extracted_code) if extracted_code else 0,
                    "passed": eval_result.get("passed"),
                    "eval_result": eval_result.get("result", ""),
                    "failure_mode": failure_mode,
                    "timestamp": datetime.now().isoformat(),
                }
                
                config_results[task_id] = result
                status = "PASS" if result["passed"] else "FAIL" if result["passed"] is False else "SKIP"
                fm = f" ({failure_mode})" if failure_mode else ""
                print(f"{status}{fm} ({elapsed:.0f}s)")
                
                # Save after each problem for resume support
                with open(results_file, 'w') as f:
                    json.dump(config_results, f, indent=2)
        
        all_results[config_name] = config_results
        
        # Compute pass@1
        passed = sum(1 for r in config_results.values() if r.get("passed"))
        total = len(config_results)
        pass_at_1 = passed / total if total > 0 else 0
        print(f"\n  {config_name}: pass@1 = {passed}/{total} = {pass_at_1:.1%}")
        
        # Save summary
        summary_file = Path(RESULTS_DIR) / args.model / config_name / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump({
                "model": mc["model_name"],
                "config": config_name,
                "pass_at_1": pass_at_1,
                "passed": passed,
                "total": total,
                "problems": [pid for pid, _ in problems],
                "reps": args.reps,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)
    
    # Comparison table
    print("\n" + "=" * 70)
    print(f"COMPARISON TABLE ({mc['model_name']})")
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
    
    # Failure mode breakdown
    print("\n" + "=" * 70)
    print("FAILURE MODE BREAKDOWN")
    print("=" * 70)
    for config_name in configs_to_run:
        r = all_results.get(config_name, {})
        fm_counts = defaultdict(int)
        for v in r.values():
            if not v.get("passed"):
                fm = v.get("failure_mode", "unknown")
                # Simplify FM categories
                if "FM-1.1" in fm:
                    fm_counts["FM-1.1 (spec disobedience)"] += 1
                elif "no code" in fm:
                    fm_counts["FM-1.1 (no code produced)"] += 1
                else:
                    fm_counts["Other"] += 1
        if fm_counts:
            print(f"\n{config_name} failures:")
            for fm, count in sorted(fm_counts.items(), key=lambda x: -x[1]):
                print(f"  {fm}: {count}")
    
    print()
    print("Paper comparison (GPT-3.5-turbo, different model):")
    print(f"  Paper baseline:        89.6% (HumanEval)")
    print(f"  Paper prompt fix:      90.3% (HumanEval, +0.7pp)")
    print(f"  Paper topology fix:    91.5% (HumanEval, +1.9pp)")
    print()
    
    # Save combined results
    final_file = Path(RESULTS_DIR) / args.model / f"final_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    with open(final_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Full results saved to {final_file}")


if __name__ == "__main__":
    main()