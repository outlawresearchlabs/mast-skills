#!/usr/bin/env bash
# run_baseline.sh - Run HumanEval benchmark with baseline ChatDev prompts
# Usage: ./run_baseline.sh [--subset N] [--start IDX] [--model MODEL_NAME]
#
# Environment variables:
#   OPENAI_API_KEY   - Required. OpenAI API key
#   OPENAI_BASE_URL  - Optional. Custom API base URL
#   CHATDEV_MODEL    - Optional. Model name (default: gpt-4o)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATDEV_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$CHATDEV_ROOT/venv"

# Defaults
SUBSET=0          # 0 = all problems
START_IDX=0       # Starting index
MODEL="${CHATDEV_MODEL:-gpt-4o}"
YAML_CONFIG="$CHATDEV_ROOT/yaml_instance/ChatDev_v1.yaml"
RESULTS_DIR="$CHATDEV_ROOT/mast_hardened/results/baseline"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --subset)   SUBSET="$2"; shift 2 ;;
        --start)    START_IDX="$2"; shift 2 ;;
        --model)    MODEL="$2"; shift 2 ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate env
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "ERROR: OPENAI_API_KEY environment variable is required"
    exit 1
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install human-eval if needed
pip install human-eval -q 2>/dev/null || true

mkdir -p "$RESULTS_DIR"

echo "=== ChatDev Baseline HumanEval Benchmark ==="
echo "Config:  $YAML_CONFIG"
echo "Model:   $MODEL"
echo "Results: $RESULTS_DIR"
echo ""

# Generate the problem list and run each through ChatDev
python3 << 'PYEOF'
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

from human_eval.data import read_problems

results_dir = os.environ.get("MAST_RESULTS_DIR", "/tmp/results/baseline")
yaml_config = os.environ.get("MAST_YAML_CONFIG", "yaml_instance/ChatDev_v1.yaml")
model = os.environ.get("MAST_MODEL", "gpt-4o")
subset = int(os.environ.get("MAST_SUBSET", "0"))
start_idx = int(os.environ.get("MAST_START_IDX", "0"))

problems = read_problems()
problem_list = list(problems.values())
if subset > 0:
    problem_list = problem_list[start_idx:start_idx + subset]
else:
    problem_list = problem_list[start_idx:]

results = {}
for i, problem in enumerate(problem_list):
    task_id = problem["task_id"]
    prompt = problem["prompt"]
    entry_point = problem["entry_point"]

    print(f"\n[{i+1}/{len(problem_list)}] {task_id} ({entry_point})")
    print(f"  Prompt: {prompt[:80]}...")

    result_file = Path(results_dir) / f"{task_id.replace('/', '_')}.json"
    if result_file.exists():
        print(f"  SKIP: result already exists")
        with open(result_file) as f:
            results[task_id] = json.load(f)
        continue

    # Construct a HumanEval-style task prompt for ChatDev
    task_prompt = (
        f"Implement the following Python function. The function signature and docstring are provided. "
        f"Write ONLY the function implementation, with no additional code.\n\n"
        f"{prompt}"
    )

    # Run ChatDev via the run.py entry point
    # Note: This requires the ChatDev server/runtime to be set up with API keys
    start_time = datetime.now()
    try:
        proc = subprocess.run(
            ["python3", "run.py", "--path", yaml_config, "--name", f"humaneval_{task_id.replace('/', '_')}"],
            input=task_prompt,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per problem
            env={
                **os.environ,
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
                "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", ""),
            }
        )
        output = proc.stdout
        error = proc.stderr
        elapsed = (datetime.now() - start_time).total_seconds()

        result = {
            "task_id": task_id,
            "prompt": prompt,
            "completion": output,
            "error": error[:2000] if error else None,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "config": "baseline",
        }

    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start_time).total_seconds()
        result = {
            "task_id": task_id,
            "prompt": prompt,
            "completion": "",
            "error": "TIMEOUT: exceeded 600s limit",
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "config": "baseline",
        }
        print(f"  TIMEOUT after {elapsed:.1f}s")

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        result = {
            "task_id": task_id,
            "prompt": prompt,
            "completion": "",
            "error": str(e)[:2000],
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "config": "baseline",
        }
        print(f"  ERROR: {e}")

    # Extract code from output (look for Python code blocks)
    completion = result["completion"]
    # Try to find the function implementation in the ChatDev output
    import re
    code_match = re.search(r'```python\n(.*?)```', completion, re.DOTALL)
    if code_match:
        result["extracted_code"] = code_match.group(1)
    else:
        result["extracted_code"] = completion

    # Save individual result
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)

    results[task_id] = result
    print(f"  Done in {result['elapsed_seconds']:.1f}s")

# Save combined results
combined_file = Path(results_dir) / "all_results.json"
with open(combined_file, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nAll results saved to {combined_file}")

# Generate HumanEval-compatible samples.json for evaluation
samples = []
for task_id, result in results.items():
    samples.append({
        "task_id": task_id,
        "completion": result.get("extracted_code", result.get("completion", "")),
    })
samples_file = Path(results_dir) / "samples.jsonl"
with open(samples_file, 'w') as f:
    for s in samples:
        f.write(json.dumps(s) + "\n")
print(f"Samples for evaluation saved to {samples_file}")
PYEOF

echo ""
echo "=== Baseline run complete ==="
echo "Results directory: $RESULTS_DIR"