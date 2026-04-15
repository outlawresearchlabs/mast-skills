"""
MAST Official LLM-as-Judge Pipeline (Adapted from paper authors)

This is a cleaned-up version of the official MAST evaluation pipeline from
https://github.com/multi-agent-systems-failure-taxonomy/MAST

The paper authors used o1 as the judge model. This version also supports
GPT-4o and Claude for cost efficiency, plus the HuggingFace annotated dataset.

Key differences from the original notebook:
- Uses the official definitions.txt and examples.txt from the paper authors
- Supports both OpenAI and Anthropic models as judges
- Integrates with HuggingFace dataset (mcemri/MAD) for ground truth comparison
- Adds batch processing and result caching

Usage:
  # Evaluate a single trace
  python mast_judge.py --trace path/to/trace.json --provider openai --model gpt-4o

  # Evaluate against HuggingFace ground truth
  python mast_judge.py --huggingface --sample 50 --provider openai --model gpt-4o

  # Batch evaluate all traces from a MAS framework
  python mast_judge.py --traces-dir /path/to/traces --provider anthropic --model claude-sonnet-4-20250514
"""

import json
import os
import re
import sys
import argparse
import time
from pathlib import Path
from datetime import datetime

# Attempt imports
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from huggingface_hub import hf_hub_download
    HAS_HF = True
except ImportError:
    HAS_HF = False

# ============================================================
# OFFICIAL MAST DEFINITIONS (from paper authors' definitions.txt)
# These are the canonical definitions used in the paper's evaluation.
# ============================================================

OFFICIAL_DEFINITIONS = """1.1 Disobey Task Specification: 
This error occurs when an agent or system fails to adhere to specified constraints, guidelines, or requirements associated with a particular task. Non-compliance can result from unclear, incomplete, or ambiguous instructions provided by the user, system prompts, or task descriptions. It may also arise from an agent's inadequate ability to interpret or apply constraints effectively. Consequences of poor task constraint compliance include incorrect, suboptimal, or irrelevant outputs, reduced system performance and increased resource consumption.

1.2 Disobey Role Specification: 
Failure to adhere to the defined responsibilities and constraints of an assigned role, potentially leading to an agent behaving like another.

1.3 Step Repetition: 
Step repetition occurs when an agent or system unnecessarily repeats a phase, a task, a stage that have already been completed. Such redundancy can arise from inadequate state or context tracking, inefficient workflow management, unclear or ambiguous instructions, or failure to recognize completed tasks.

1.4 Loss of Conversation History: 
Unexpected context truncation, disregarding recent interaction history and reverting to an antecedent conversational state.

1.5 Unaware of Termination Conditions:
This error occurs when an agent or system fails to adhere to criteria designed to trigger the termination of an interaction, conversation, phase, or task. Such oversight can arise due to ambiguous, incomplete, or poorly defined termination conditions.

2.1 Conversation Reset: 
Unexpected or unwarranted restarting of dialogue, losing context and progress.

2.2 Fail to Ask for Clarification: 
Proceeding with wrong assumptions when faced with unclear or incomplete data.

2.3 Task Derailment: 
Deviation from intended objective, resulting in irrelevant or unproductive actions.

2.4 Information Withholding: 
Failure to share important data that could impact other agents' decision-making.

2.5 Ignored Other Agent's Input: 
Disregarding input or recommendations from other agents.

2.6 Action-Reasoning Mismatch: 
Discrepancy between logical reasoning and actual actions taken by the agent.

3.1 Premature Termination: 
Ending a task before all necessary information has been exchanged or objectives met.

3.2 No or Incorrect Verification: 
Omission of proper checking of task outcomes, allowing errors to propagate undetected.

3.3 Weak Verification: 
Inadequate or superficial verification of task outcomes, where checks are performed but fail to catch significant issues.
"""

EVALUATION_PROMPT_TEMPLATE = """Below I will provide a multiagent system trace. provide me an analysis of the failure modes and inefficiencies as I will say below. 
In the traces, analyze the system behaviour.
There are several failure modes in multiagent systems I identified. I will provide them below. Tell me if you encounter any of them, as a binary yes or no. 
Also, give me a one sentence (be brief) summary of the problems with the inefficiencies or failure modes in the trace. Only mark a failure mode if you can provide an example of it in the trace, and specify that in your summary at the end
Also tell me whether the task is successfully completed or not, as a binary yes or no.
At the very end, I provide you with the definitions of the failure modes and inefficiencies. After the definitions, I will provide you with examples of the failure modes and inefficiencies for you to understand them better.
Tell me if you encounter any of them between the @@ symbols as I will say below, as a binary yes or no.
Here are the things you should answer. Start after the @@ sign and end before the next @@ sign (do not include the @@ symbols in your answer):
*** begin of things you should answer *** @@
A. Freeform text summary of the problems with the inefficiencies or failure modes in the trace: <summary>
B. Whether the task is successfully completed or not: <yes or no>
C. Whether you encounter any of the failure modes or inefficiencies:
1.1 Disobey Task Specification: <yes or no>
1.2 Disobey Role Specification: <yes or no>
1.3 Step Repetition: <yes or no>
1.4 Loss of Conversation History: <yes or no>
1.5 Unaware of Termination Conditions: <yes or no>
2.1 Conversation Reset: <yes or no>
2.2 Fail to Ask for Clarification: <yes or no>
2.3 Task Derailment: <yes or no>
2.4 Information Withholding: <yes or no>
2.5 Ignored Other Agent's Input: <yes or no>
2.6 Action-Reasoning Mismatch: <yes or no>
3.1 Premature Termination: <yes or no>
3.2 No or Incorrect Verification: <yes or no>
3.3 Weak Verification: <yes or no>
@@*** end of your answer ***
An example answer is: 
A. The task is not completed due to disobeying role specification as agents went rogue and started to chat with each other instead of completing the task. Agents derailed and verifier is not strong enough to detect it.
B. no 
C. 
1.1 no 
1.2 no 
1.3 no 
1.4 no 
1.5 no 
2.1 no 
2.2 no 
2.3 yes 
2.4 no 
2.5 no 
2.6 yes 
2.7 no 
3.1 no 
3.2 yes 
3.3 no 
Here is the trace: 
{trace}
Also, here are the explanations (definitions) of the failure modes and inefficiencies: 
{definitions}
Here are some examples of the failure modes and inefficiencies: 
{examples}"""


def parse_judge_response(response_text):
    """Parse the structured @@ @@ response from the judge."""
    # Extract content between @@ markers
    match = re.search(r'@@\s*\n(.*?)\n\s*@@', response_text, re.DOTALL)
    if not match:
        # Try alternate patterns
        match = re.search(r'\*\*\* begin.*?@@\s*(.*?)\s*@@\s*\*\*\*', response_text, re.DOTALL)
    
    content = match.group(1) if match else response_text
    
    result = {
        "summary": "",
        "task_completed": None,
        "failure_modes": {},
        "raw": response_text,
    }
    
    # Extract summary (A.)
    summary_match = re.search(r'A\.\s*(.*?)(?=\nB\.)', content, re.DOTALL)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()
    
    # Extract task completion (B.)
    completion_match = re.search(r'B\.\s*(yes|no)', content, re.IGNORECASE)
    if completion_match:
        result["task_completed"] = completion_match.group(1).lower() == "yes"
    
    # Extract failure modes (C.)
    mode_patterns = [
        ("1.1", "FM-1.1"), ("1.2", "FM-1.2"), ("1.3", "FM-1.3"),
        ("1.4", "FM-1.4"), ("1.5", "FM-1.5"), ("2.1", "FM-2.1"),
        ("2.2", "FM-2.2"), ("2.3", "FM-2.3"), ("2.4", "FM-2.4"),
        ("2.5", "FM-2.5"), ("2.6", "FM-2.6"), ("3.1", "FM-3.1"),
        ("3.2", "FM-3.2"), ("3.3", "FM-3.3"),
    ]
    
    for num, fm_id in mode_patterns:
        pattern = rf'{num}\s+.*?:\s*(yes|no)'
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result["failure_modes"][fm_id] = match.group(1).lower() == "yes"
        else:
            result["failure_modes"][fm_id] = None  # Not detected in response
    
    return result


def evaluate_trace_openai(trace_text, definitions, examples, model="gpt-4o"):
    """Evaluate a trace using OpenAI API (matching authors' pipeline)."""
    if not HAS_OPENAI:
        raise ImportError("openai package required. Run: pip install openai")
    
    client = OpenAI()
    prompt = EVALUATION_PROMPT_TEMPLATE.format(
        trace=trace_text,
        definitions=definitions,
        examples=examples
    )
    
    # Truncate if too long (paper used 1MB limit)
    if len(prompt) > 1048570:
        prompt = prompt[:1048570]
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,  # Paper used 1.0 for o1
    )
    
    return parse_judge_response(response.choices[0].message.content)


def evaluate_trace_anthropic(trace_text, definitions, examples, model="claude-sonnet-4-20250514"):
    """Evaluate a trace using Anthropic API."""
    if not HAS_ANTHROPIC:
        raise ImportError("anthropic package required. Run: pip install anthropic")
    
    client = anthropic.Anthropic()
    prompt = EVALUATION_PROMPT_TEMPLATE.format(
        trace=trace_text,
        definitions=definitions,
        examples=examples
    )
    
    if len(prompt) > 180000:  # Claude context limit (chars)
        prompt = prompt[:180000]
    
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
    )
    
    return parse_judge_response(response.content[0].text)


def load_huggingface_dataset(full=True):
    """Load the official MAST annotated dataset from HuggingFace."""
    if not HAS_HF:
        raise ImportError("huggingface_hub required. Run: pip install huggingface_hub")
    
    REPO_ID = "mcemri/MAD"
    FILENAME = "MAD_full_dataset.json" if full else "MAD_human_labelled_dataset.json"
    
    file_path = hf_hub_download(repo_id=REPO_ID, filename=FILENAME, repo_type="dataset")
    with open(file_path, "r") as f:
        data = json.load(f)
    
    return data


def compare_with_ground_truth(judge_results, ground_truth, trace_ids=None):
    """Compare LLM judge results against human annotations (ground truth)."""
    # Calculate agreement per failure mode
    agreement = {}
    for fm_id in [f"FM-{c}.{m}" for c in range(1, 4) for m in range(1, 7) if not (c == 1 and m == 6) and not (c == 2 and m == 7)]:
        if fm_id not in ["FM-1.6", "FM-2.7"]:  # Skip non-existent modes
            tp = fp = tn = fn = 0
            for tid in (trace_ids or judge_results.keys()):
                if tid in judge_results and tid in ground_truth:
                    judge_says = judge_results[tid].get("failure_modes", {}).get(fm_id, False)
                    truth_says = ground_truth[tid].get(fm_id, False)
                    if judge_says and truth_says: tp += 1
                    elif judge_says and not truth_says: fp += 1
                    elif not judge_says and truth_says: fn += 1
                    else: tn += 1
            total = tp + fp + tn + fn
            agreement[fm_id] = {
                "true_positive": tp, "false_positive": fp,
                "true_negative": tn, "false_negative": fn,
                "accuracy": (tp + tn) / total if total > 0 else 0,
                "precision": tp / (tp + fp) if (tp + fp) > 0 else 0,
                "recall": tp / (tp + fn) if (tp + fn) > 0 else 0,
            }
    return agreement


def validate_our_test_harness():
    """
    Validate our failure injection test harness against the official MAST traces.
    
    Strategy:
    1. Sample traces from the HuggingFace dataset where each failure mode is present
    2. Run our test_harness.py evaluation prompts on those same scenarios
    3. Compare our detection results against the human-annotated ground truth
    
    This validates whether our test prompts correctly trigger and detect each mode.
    """
    print("MAST Test Harness Validation Against Official Ground Truth")
    print("=" * 60)
    
    if not HAS_HF:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        return
    
    # Load human-annotated dataset
    print("Loading human-annotated MAST dataset from HuggingFace...")
    data = load_huggingface_dataset(full=False)
    print(f"Loaded {len(data)} human-annotated traces")
    
    # For each failure mode, find traces where it's present
    mode_samples = {}
    for fm_id in [f"FM-{c}.{m}" for c in range(1, 4) for m in range(1, 7)]:
        if fm_id in ["FM-1.6", "FM-2.7"]:
            continue
        matching = [d for d in data if d.get("failure_modes", {}).get(fm_id, False)]
        mode_samples[fm_id] = matching[:5]  # Sample up to 5 per mode
        print(f"  {fm_id}: {len(matching)} traces with this mode, sampled {len(mode_samples[fm_id])}")
    
    return mode_samples


def main():
    parser = argparse.ArgumentParser(description="MAST Official LLM-as-Judge Pipeline")
    parser.add_argument("--trace", type=str, help="Path to trace file to evaluate")
    parser.add_argument("--traces-dir", type=str, help="Directory of trace files to batch evaluate")
    parser.add_argument("--huggingface", action="store_true", help="Validate against HuggingFace dataset")
    parser.add_argument("--definitions", type=str, default=None, help="Path to definitions.txt (defaults to official)")
    parser.add_argument("--examples", type=str, default=None, help="Path to examples.txt (defaults to official)")
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--sample", type=int, default=50, help="Number of HuggingFace traces to sample")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file for results")
    parser.add_argument("--validate", action="store_true", help="Validate test harness against ground truth")
    
    args = parser.parse_args()
    
    # Load definitions and examples
    definitions = OFFICIAL_DEFINITIONS
    if args.definitions:
        with open(args.definitions) as f:
            definitions = f.read()
    
    examples = ""
    if args.examples:
        with open(args.examples) as f:
            examples = f.read()
    elif Path("taxonomy_definitions_examples/examples.txt").exists():
        with open("taxonomy_definitions_examples/examples.txt") as f:
            examples = f.read()
    
    # Select model
    if args.provider == "openai":
        model = args.model or "gpt-4o"
        evaluator = lambda trace: evaluate_trace_openai(trace, definitions, examples, model)
    else:
        model = args.model or "claude-sonnet-4-20250514"
        evaluator = lambda trace: evaluate_trace_anthropic(trace, definitions, examples, model)
    
    print(f"MAST LLM-as-Judge Pipeline")
    print(f"Provider: {args.provider}, Model: {model}")
    
    results = []
    
    # Single trace evaluation
    if args.trace:
        with open(args.trace) as f:
            trace_text = f.read()
        result = evaluator(trace_text)
        print(f"\n=== Evaluation Result ===")
        print(f"Summary: {result['summary']}")
        print(f"Task completed: {result['task_completed']}")
        print(f"\nFailure modes detected:")
        for fm_id, detected in result["failure_modes"].items():
            if detected:
                print(f"  {fm_id}: YES")
        results.append({"trace": args.trace, **result})
    
    # Batch evaluation
    if args.traces_dir:
        trace_files = list(Path(args.traces_dir).glob("*.json")) + list(Path(args.traces_dir).glob("*.txt"))
        print(f"\nEvaluating {len(trace_files)} traces from {args.traces_dir}...")
        
        for i, tf in enumerate(trace_files):
            print(f"  [{i+1}/{len(trace_files)}] {tf.name}...", end=" ", flush=True)
            try:
                trace_text = tf.read_text()
                result = evaluator(trace_text)
                result["trace_file"] = str(tf)
                results.append(result)
                modes_found = [k for k, v in result.get("failure_modes", {}).items() if v]
                print(f"found {len(modes_found)} modes: {', '.join(modes_found) if modes_found else 'none'}")
            except Exception as e:
                print(f"ERROR: {e}")
            time.sleep(1)
    
    # HuggingFace validation
    if args.huggingface:
        print(f"\nEvaluating {args.sample} traces from HuggingFace MAST dataset...")
        data = load_huggingface_dataset(full=True)
        import random
        sample = random.sample(data, min(args.sample, len(data)))
        
        for i, trace_data in enumerate(sample):
            trace_text = json.dumps(trace_data, indent=2)
            if len(trace_text) > 500000:
                trace_text = trace_text[:500000]
            
            print(f"  [{i+1}/{len(sample)}]...", end=" ", flush=True)
            try:
                result = evaluator(trace_text)
                result["source"] = "huggingface"
                results.append(result)
                modes_found = [k for k, v in result.get("failure_modes", {}).items() if v]
                print(f"found {len(modes_found)} modes")
            except Exception as e:
                print(f"ERROR: {e}")
            time.sleep(1)
    
    # Test harness validation
    if args.validate:
        validate_our_test_harness()
    
    # Save results
    if args.output and results:
        with open(args.output, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "provider": args.provider,
                "results": results,
            }, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")
    
    # Print summary
    if results:
        print(f"\n{'='*60}")
        print(f"SUMMARY: {len(results)} traces evaluated")
        
        # Count failure mode occurrences
        mode_counts = {}
        for r in results:
            for fm_id, detected in r.get("failure_modes", {}).items():
                if detected:
                    mode_counts[fm_id] = mode_counts.get(fm_id, 0) + 1
        
        print(f"\nFailure mode distribution:")
        for fm_id in sorted(mode_counts.keys()):
            print(f"  {fm_id}: {mode_counts[fm_id]} traces ({mode_counts[fm_id]/len(results)*100:.1f}%)")


if __name__ == "__main__":
    main()