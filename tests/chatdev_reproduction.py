#!/usr/bin/env python3
"""
ChatDev MAST Reproduction: Run tasks with baseline and MAST-hardened configs.
Compares failure mode counts between the two configurations.
"""
import subprocess
import json
import os
import sys
import time
import re
from pathlib import Path

CHATDEV_DIR = os.environ.get("CHATDEV_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ChatDev"))
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "chatdev")
BASELINE_YAML = "yaml_instance/ChatDev_v1_gw.yaml"
MAST_YAML = "yaml_instance/ChatDev_v1_mast_gw.yaml"

# 3 tasks from the HuggingFace ChatDev dataset
TASKS = [
    {
        "id": "crossword",
        "trace_id": 2,
        "hf_modes": [],  # Clean in HuggingFace
        "prompt": "Implement a crossword puzzle. Provide a grid of squares with clues for across and down entries. The user can enter words and the game validates them."
    },
    {
        "id": "palindrome",
        "trace_id": 3,
        "hf_modes": ["2.2", "2.3"],  # FM-2.2, FM-2.3 in HuggingFace
        "prompt": "develop a program that detects palindromes in a given text file"
    },
    {
        "id": "chess",
        "trace_id": 8,
        "hf_modes": ["1.1", "1.3", "1.5", "2.2", "2.3", "2.4", "2.6", "3.1", "3.3"],  # 9 failures in HuggingFace
        "prompt": "Design a chess game, allowing two players to take turns and determining the winner. It should be playable from Linux Terminal."
    }
]

CONFIGS = [
    {"name": "baseline", "yaml": BASELINE_YAML},
    {"name": "mast", "yaml": MAST_YAML}
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_chatdev(task_id, task_prompt, config_name, yaml_path, timeout=600):
    """Run ChatDev with a given task and config, capture output."""
    name = f"{task_id}_{config_name}"
    logfile = os.path.join(OUTPUT_DIR, f"{name}.log")
    
    print(f"  Running {name}...", flush=True)
    
    env = os.environ.copy()
    env["BASE_URL"] = "http://127.0.0.1:11434/v1"
    env["API_KEY"] = "ollama"
    
    try:
        proc = subprocess.run(
            ["python3", "-u", "run.py", "--path", yaml_path, "--name", name],
            input=task_prompt + "\n",
            capture_output=True,
            text=True,
            cwd=CHATDEV_DIR,
            env=env,
            timeout=timeout,
        )
        
        combined = proc.stdout + proc.stderr
        
        with open(logfile, 'w') as f:
            f.write(combined)
        
        # Extract key events from log
        events = []
        for line in combined.split('\n'):
            if 'MODEL_CALL' in line or 'NODE_START' in line or 'NODE_END' in line or 'WORKFLOW_START' in line or 'WORKFLOW_END' in line or 'ERROR' in line.upper():
                events.append(line[:200])
        
        # Count agent calls
        n_calls = combined.count('MODEL_CALL')
        n_errors = combined.upper().count('ERROR')
        
        # Check for completion
        completed = 'WORKFLOW_END' in combined or 'completed' in combined.lower()
        
        print(f"    Done: {n_calls} model calls, {n_errors} errors, completed={completed}")
        
        return {
            "name": name,
            "n_model_calls": n_calls,
            "n_errors": n_errors,
            "completed": completed,
            "log_size": len(combined),
            "events": events[:50],
            "log_file": logfile
        }
        
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT after {timeout}s")
        return {"name": name, "error": "timeout"}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"name": name, "error": str(e)}


def analyze_trace_with_judge(log_file, task_info):
    """Analyze a ChatDev trace log for MAST failure modes."""
    with open(log_file) as f:
        trace = f.read()
    
    # Simple heuristics for failure mode detection in ChatDev traces
    # These are pattern-matching approximations - not as rigorous as o1
    
    modes_found = {}
    
    # FM-1.3: Step repetition - same agent calling same function multiple times unnecessarily
    # Look for duplicate MODEL_CALL with same content
    model_calls = re.findall(r"Model call for node (\w+.*?)(?:\n|$)", trace[:50000])
    call_counts = {}
    for call in model_calls:
        call_counts[call] = call_counts.get(call, 0) + 1
    repeated_calls = sum(1 for c, n in call_counts.items() if n > 2)
    if repeated_calls > 0:
        modes_found["1.3"] = f"{repeated_calls} agents called 3+ times"
    
    # FM-1.5: Unaware of termination - continues past completion
    if trace.count('Code Complete All Phase Loop Counter') > 3:
        modes_found["1.5"] = "Multiple loop iterations past expected completion"
    
    # FM-2.2: No clarification asked
    # If task is ambiguous and agent doesn't ask questions
    if not re.search(r'(?i)(clarif|what (do|is)|could you (explain|specify))', trace):
        # Only flag for ambiguous tasks
        if task_info.get("hf_modes") and "2.2" in task_info.get("hf_modes", []):
            modes_found["2.2"] = "No clarification detected in ambiguous task"
    
    # FM-2.6: Reasoning-action mismatch
    if re.search(r'(?i)(I will (not|skip)|skip the).*?(saving|writing|implementing)', trace):
        modes_found["2.6"] = "Reasoning-action mismatch detected"
    
    # FM-3.2: No verification
    if not re.search(r'(?i)(test|verify|check|run.*pytest|unittest)', trace):
        modes_found["3.2"] = "No verification detected"
    
    # FM-3.3: Weak verification
    if re.search(r'(?i)(basic test|simple test|just check)', trace):
        modes_found["3.3"] = "Weak/superficial verification"
    
    # FM-1.1: Disobey spec
    if re.search(r'(?i)(pass\n|TODO|placeholder|not implemented)', trace):
        modes_found["1.1"] = "Incomplete implementation with placeholders"
    
    return modes_found


def main():
    print("=" * 70)
    print("CHATDEV MAST REPRODUCTION")
    print("3 tasks x 2 configs = 6 runs")
    print("=" * 70)
    
    all_results = {}
    
    for task in TASKS:
        print(f"\n{'='*50}")
        print(f"Task: {task['id']} (HF trace #{task['trace_id']})")
        print(f"Prompt: {task['prompt'][:80]}...")
        print(f"HF failure modes: {task['hf_modes'] or 'clean'}")
        print(f"{'='*50}")
        
        all_results[task['id']] = {"hf_modes": task['hf_modes'], "configs": {}}
        
        for config in CONFIGS:
            result = run_chatdev(
                task['id'],
                task['prompt'],
                config['name'],
                config['yaml'],
                timeout=600
            )
            
            # Analyze trace if log exists
            if 'log_file' in result and os.path.exists(result.get('log_file', '')):
                modes = analyze_trace_with_judge(result['log_file'], task)
                result['mast_modes_found'] = modes
                result['n_mast_modes'] = len(modes)
                print(f"    Failure modes found: {list(modes.keys()) or 'none'}")
            
            all_results[task['id']]['configs'][config['name']] = result
    
    # Save results
    results_path = os.path.join(OUTPUT_DIR, "chatdev_comparison.json")
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    # Print summary
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"\n{'Task':<15} {'HF Modes':<10} {'Baseline':<15} {'MAST':<15}")
    print("-" * 55)
    
    for task in TASKS:
        tid = task['id']
        hf = len(task['hf_modes'])
        baseline_modes = all_results[tid]['configs'].get('baseline', {}).get('n_mast_modes', '?')
        mast_modes = all_results[tid]['configs'].get('mast', {}).get('n_mast_modes', '?')
        print(f"{tid:<15} {hf:<10} {baseline_modes:<15} {mast_modes:<15}")
    
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()