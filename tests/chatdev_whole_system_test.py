#!/usr/bin/env python3
"""ChatDev Whole-System Validation Experiment

Runs HumanEval benchmark through ChatDev with 3 configurations:
1. Baseline (no MAST defenses)
2. MAST-hardened (prompt-only defenses)
3. MAST + MCP enforcement (prompt + structural enforcement)

Measures task completion rate (pass@1) on HumanEval, NOT trigger pass rate.
This gives us the same metric the paper uses for their intervention case studies.

Usage:
    export CHATDEV_DIR=/tmp/ChatDev
    export OPENAI_API_KEY=ollama
    export OPENAI_BASE_URL=http://127.0.0.1:11434/v1

    # Run all 3 configs on 10 HumanEval problems (subset for speed)
    python3 -u chatdev_whole_system_test.py --subset 10 --model gemma4:31b-cloud

    # Run specific config only
    python3 -u chatdev_whole_system_test.py --config baseline --subset 5

    # Resume interrupted run
    python3 -u chatdev_whole_system_test.py --subset 10 --resume

Design matches the paper's methodology:
- HumanEval benchmark (164 coding problems)
- Multiple repetitions for statistical significance
- Task completion rate (pass@1) measured by human-eval execution framework
- 10-minute timeout per problem
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
RESULTS_DIR = os.path.abspath(RESULTS_DIR)

YAML_CONFIGS = {
    "baseline": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_gw.yaml"),
    "mast": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_mast_gw.yaml"),
    "mast_mcp": os.path.join(CHATDEV_DIR, "yaml_instance", "ChatDev_v1_mast_gw.yaml"),
}

TIMEOUT_SECONDS = 600  # 10 min per problem
RUN_PY = os.path.join(CHATDEV_DIR, "run.py")


def extract_function_code(completion: str) -> str:
    """Extract Python function implementation from ChatDev output.

    ChatDev produces multi-agent conversation logs with code in various formats.
    We need the final function implementation for HumanEval evaluation.
    """
    # Try markdown code blocks first (most reliable)
    code_blocks = re.findall(r'```python\n(.*?)```', completion, re.DOTALL)
    if code_blocks:
        # Return the LAST code block (most likely the final version)
        return code_blocks[-1].strip()

    # Try looking for saved file content
    save_blocks = re.findall(r'(?:save_file|write_file).*?content.*?["\'](.+?)["\']',
                             completion, re.DOTALL)
    if save_blocks:
        return save_blocks[-1]

    # Fallback: return the raw completion
    return completion.strip()


def run_chatdev_problem(yaml_config: str, task_prompt: str, problem_name: str,
                        timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run a single HumanEval problem through ChatDev.

    Returns dict with completion, elapsed time, and any errors.
    """
    env = {
        **os.environ,
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "ollama"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"),
    }

    start_time = datetime.now()
    try:
        proc = subprocess.run(
            [sys.executable, RUN_PY, "--path", yaml_config, "--name", problem_name],
            input=task_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=CHATDEV_DIR,
            env=env,
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "completion": proc.stdout,
            "stderr": proc.stderr[:5000] if proc.stderr else None,
            "elapsed_seconds": elapsed,
            "error": None,
            "exit_code": proc.returncode,
        }

    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "completion": "",
            "stderr": None,
            "elapsed_seconds": elapsed,
            "error": f"TIMEOUT after {timeout}s",
            "exit_code": -1,
        }

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        return {
            "completion": "",
            "stderr": None,
            "elapsed_seconds": elapsed,
            "error": str(e)[:2000],
            "exit_code": -1,
        }


def evaluate_with_human_eval(results: dict) -> dict:
    """Use human-eval's execution-based evaluation to compute pass@1.

    This reruns the generated code against the canonical test suite.
    """
    # Build samples.jsonl for human-eval evaluation
    samples = []
    for task_id, result in results.items():
        code = extract_function_code(result.get("completion", ""))
        samples.append({
            "task_id": task_id,
            "completion": code,
        })

    # Write samples
    samples_file = Path(RESULTS_DIR) / "samples.jsonl"
    with open(samples_file, 'w') as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")

    # Run human-eval evaluator
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "human_eval.evaluate_functional_correctness",
             str(samples_file)],
            capture_output=True, text=True, timeout=120,
            cwd=RESULTS_DIR,
        )
        eval_output = proc.stdout
        # Parse the results
        # human-eval outputs: {"pass@1": X.XXX, ...}
        eval_results = {}
        for line in eval_output.strip().split('\n'):
            try:
                data = json.loads(line)
                if "pass@1" in data:
                    eval_results = data
            except json.JSONDecodeError:
                continue
        return eval_results

    except Exception as e:
        return {"error": str(e)}


def load_existing_results(config: str, model: str, rep: int) -> dict:
    """Load existing results for resume support."""
    results_file = Path(RESULTS_DIR) / config / model / f"rep{rep}" / "results.json"
    if results_file.exists():
        with open(results_file) as f:
            return json.load(f)
    return {}


def save_results(config: str, model: str, rep: int, results: dict):
    """Save results for a specific config/model/rep combination."""
    results_dir = Path(RESULTS_DIR) / config / model / f"rep{rep}"
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "results.json", 'w') as f:
        json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="ChatDev whole-system validation (HumanEval benchmark)")
    parser.add_argument("--config",
        choices=["baseline", "mast", "mast_mcp", "all"],
        default="all",
        help="Which config(s) to test (default: all)")
    parser.add_argument("--model", default=os.environ.get("CHATDEV_MODEL", "gemma4:31b-cloud"),
        help="Model name (must match ChatDev YAML)")
    parser.add_argument("--subset", type=int, default=0,
        help="Number of HumanEval problems (0=all, recommended: 10-20 for testing)")
    parser.add_argument("--start-idx", type=int, default=0,
        help="Starting problem index")
    parser.add_argument("--reps", type=int, default=3,
        help="Number of repetitions per problem for statistical significance (paper uses 6)")
    parser.add_argument("--resume", action="store_true",
        help="Resume from interrupted run (skip completed problems)")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS,
        help="Timeout per problem in seconds")
    args = parser.parse_args()

    # Validate ChatDev installation
    if not os.path.isfile(RUN_PY):
        print(f"ERROR: ChatDev run.py not found at {RUN_PY}")
        print(f"  Set CHATDEV_DIR environment variable to ChatDev root directory")
        sys.exit(1)

    for config_name, yaml_path in YAML_CONFIGS.items():
        if not os.path.isfile(yaml_path):
            print(f"WARNING: YAML config not found: {yaml_path}")

    # Validate YAML configs exist for requested test
    configs_to_run = (["baseline", "mast", "mast_mcp"] if args.config == "all"
                      else [args.config])

    for config_name in configs_to_run:
        if not os.path.isfile(YAML_CONFIGS[config_name]):
            print(f"ERROR: Config '{config_name}' YAML not found: {YAML_CONFIGS[config_name]}")
            sys.exit(1)

    # Load HumanEval problems
    from human_eval.data import read_problems
    problems = read_problems()
    problem_list = list(problems.values())

    if args.subset > 0:
        problem_list = problem_list[args.start_idx:args.start_idx + args.subset]

    print("=" * 70)
    print("CHATDEV WHOLE-SYSTEM VALIDATION (HumanEval)")
    print("=" * 70)
    print(f"Configs:      {configs_to_run}")
    print(f"Model:        {args.model}")
    print(f"Problems:     {len(problem_list)} (start_idx={args.start_idx})")
    print(f"Repetitions:  {args.reps}")
    print(f"Timeout:       {args.timeout}s per problem")
    print(f"Results dir:   {RESULTS_DIR}")
    print(f"ChatDev dir:  {CHATDEV_DIR}")
    print()
    print(f"Estimated time: {len(problem_list) * len(configs_to_run) * args.reps * 10 / 60:.0f} min")
    print()

    # Build task prompts
    task_prompts = {}
    for problem in problem_list:
        task_id = problem["task_id"]
        prompt = problem["prompt"]
        task_prompts[task_id] = (
            f"Implement the following Python function. The function signature "
            f"and docstring are provided. Write ONLY the function implementation, "
            f"with no additional code.\n\n{prompt}"
        )

    # Run experiments
    all_results = {}

    for config_name in configs_to_run:
        yaml_path = YAML_CONFIGS[config_name]
        config_results = {}

        for rep in range(1, args.reps + 1):
            print(f"\n{'='*60}")
            print(f"Config: {config_name} | Rep: {rep}/{args.reps}")
            print(f"{'='*60}")

            # Load existing results if resuming
            existing = load_existing_results(config_name, args.model, rep) if args.resume else {}
            completed_ids = set(existing.keys())

            for i, problem in enumerate(problem_list):
                task_id = problem["task_id"]
                entry_point = problem["entry_point"]

                if task_id in completed_ids and args.resume:
                    print(f"  [{i+1}/{len(problem_list)}] {task_id} - SKIP (resume)")
                    config_results[task_id] = existing[task_id]
                    continue

                print(f"  [{i+1}/{len(problem_list)}] {task_id} ({entry_point})...", end=" ",
                      flush=True)

                result = run_chatdev_problem(
                    yaml_path,
                    task_prompts[task_id],
                    f"humaneval_{task_id.replace('/', '_')}_{config_name}_r{rep}",
                    timeout=args.timeout,
                )

                result["task_id"] = task_id
                result["config"] = config_name
                result["model"] = args.model
                result["rep"] = rep
                result["timestamp"] = datetime.now().isoformat()
                result["extracted_code"] = extract_function_code(result["completion"])

                # Check for error
                if result["error"]:
                    print(f"ERROR ({result['error'][:40]})")
                else:
                    print(f"done ({result['elapsed_seconds']:.1f}s)")

                config_results[task_id] = result

            # Save after each rep
            save_results(config_name, args.model, rep, config_results)

        all_results[config_name] = config_results

        # Evaluate with human-eval
        print(f"\n--- Evaluating {config_name} with human-eval ---")
        eval_results = evaluate_with_human_eval(config_results)
        pass_at_1 = eval_results.get("pass@1", "N/A")
        print(f"  pass@1: {pass_at_1}")

        # Save eval results
        eval_file = Path(RESULTS_DIR) / config_name / args.model / "eval_results.json"
        eval_file.parent.mkdir(parents=True, exist_ok=True)
        with open(eval_file, 'w') as f:
            json.dump(eval_results, f, indent=2)
        config_results["_eval"] = eval_results

    # Generate samples.jsonl for ALL configs for comparison
    for config_name in configs_to_run:
        for rep in range(1, args.reps + 1):
            results = load_existing_results(config_name, args.model, rep) or all_results.get(config_name, {})
            samples = []
            for task_id, result in results.items():
                if task_id.startswith("_"):
                    continue
                code = result.get("extracted_code", result.get("completion", ""))
                samples.append({"task_id": task_id, "completion": code})

            samples_file = Path(RESULTS_DIR) / config_name / args.model / f"rep{rep}" / "samples.jsonl"
            samples_file.parent.mkdir(parents=True, exist_ok=True)
            with open(samples_file, 'w') as f:
                for s in samples:
                    f.write(json.dumps(s) + "\n")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Model: {args.model}")
    print(f"Problems: {len(problem_list)}")
    print(f"Reps: {args.reps}")
    print()

    for config_name in configs_to_run:
        eval_file = Path(RESULTS_DIR) / config_name / args.model / "eval_results.json"
        if eval_file.exists():
            with open(eval_file) as f:
                eval_results = json.load(f)
            pass_at_1 = eval_results.get("pass@1", "N/A")
        else:
            pass_at_1 = "N/A"

        # Count completed (non-error, non-timeout)
        config_data = all_results.get(config_name, {})
        completed = sum(1 for k, v in config_data.items()
                       if not k.startswith("_") and v.get("error") is None)
        errors = sum(1 for k, v in config_data.items()
                     if not k.startswith("_") and v.get("error") is not None)

        print(f"  {config_name:12s}: pass@1={pass_at_1}, completed={completed}, errors={errors}")

    print()
    print("Comparison to paper results (ChatDev ProgramDev):")
    print(f"  Paper baseline:        25.0%")
    print(f"  Paper prompt fix:      34.4% (+9.4%)")
    print(f"  Paper topology fix:    40.6% (+15.6%)")
    print(f"  Paper HumanEval base:  89.6%")
    print()
    print("Our results use HumanEval (different from ProgramDev).")
    print("Direct comparison to paper's ProgramDev numbers is not possible,")
    print("but HumanEval allows comparison to paper's HumanEval baseline (89.6%).")

    # Save final combined results
    final_file = Path(RESULTS_DIR) / f"final_{args.model}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(final_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull results saved to {final_file}")


if __name__ == "__main__":
    main()