#!/usr/bin/env python3
"""
MAST Judge Validation: Multi-model comparison against official o1 annotations.

Runs the official MAST LLM-as-judge pipeline against HuggingFace traces,
using multiple models through the local gateway. Compares each model's
failure mode labels against the paper's o1 annotations.
"""

import json
import os
import re
import sys
import random
import time
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

from openai import OpenAI

GATEWAY_URL = "http://127.0.0.1:11434/v1"
MODELS = ["gemma4:31b-cloud", "minimax-m2.7:cloud", "kimi-k2.5:cloud", "glm-5.1:cloud"]

# Load official definitions and examples
OFFICIAL_DEFINITIONS = open("/tmp/mast-official/taxonomy_definitions_examples/definitions.txt").read()
OFFICIAL_EXAMPLES = open("/tmp/mast-official/taxonomy_definitions_examples/examples.txt").read()

JUDGE_PROMPT = """Below I will provide a multiagent system trace. provide me an analysis of the failure modes and inefficiencies as I will say below. 
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
3.1 no 
3.2 yes 
3.3 no 
Here is the trace: 
{trace}
Also, here are the explanations (definitions) of the failure modes and inefficiencies: 
{definitions}
Here are some examples of the failure modes and inefficiencies: 
{examples}"""


def parse_response(text):
    # Try multiple @@ patterns -- models vary slightly
    # Some put @@ at very start, some after newline, some with spaces
    for pattern in [
        r'@@\s*\n(.*?)\n\s*@@',     # @@\n content \n@@
        r'@@\s*\n(.*?)@@',          # @@\n content @@
        r'@@(.*?)@@',               # @@ content @@
        r'\*{3} begin.*?@@\s*\n(.*?)\n\s*@@',  # with begin marker
    ]:
        match = re.search(pattern, text, re.DOTALL)
        if match and len(match.group(1).strip()) > 20:  # Must have substantial content
            content = match.group(1)
            break
    else:
        # Last resort: look for the answer block between any @@ markers
        parts = text.split('@@')
        # The answer should be in the section between first and last @@
        if len(parts) >= 3:
            content = parts[1]
        else:
            content = text
    
    result = {"summary": "", "task_completed": None, "failure_modes": {}}
    
    summary_match = re.search(r'A\.\s*(.*?)(?=\nB\.)', content, re.DOTALL)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()[:200]
    
    comp_match = re.search(r'B\.\s*(yes|no)', content, re.IGNORECASE)
    if comp_match:
        result["task_completed"] = comp_match.group(1).lower() == "yes"
    
    for num in ["1.1", "1.2", "1.3", "1.4", "1.5", 
                "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
                "3.1", "3.2", "3.3"]:
        pattern = rf'{num}\s+.*?:\s*(yes|no)'
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            result["failure_modes"][num] = 1 if match.group(1).lower() == "yes" else 0
    
    return result


def get_trace_text(record):
    """Extract trajectory text from a record. Handles nested dict structure."""
    trace = record.get("trace", "")
    if isinstance(trace, dict):
        return trace.get("trajectory", "")
    return str(trace)


def get_official_annotation(record):
    """Get the official o1 annotation. Keys are '1.1'-'3.3' with values 0/1."""
    ann = record.get("mast_annotation", {})
    if isinstance(ann, str):
        try:
            ann = json.loads(ann)
        except:
            return {}
    normalized = {}
    for k, v in ann.items():
        try:
            normalized[str(k)] = int(v)
        except (ValueError, TypeError):
            pass
    return normalized


def extract_model_response(msg):
    """Extract text from model response, handling both content and reasoning fields."""
    # Standard: content field
    if msg.content:
        return msg.content
    # Thinking models: reasoning field
    reasoning = getattr(msg, 'reasoning', None)
    if reasoning:
        return reasoning
    # Fallback: model_dump
    d = msg.model_dump() if hasattr(msg, 'model_dump') else {}
    return d.get("reasoning", d.get("content", ""))


def run_judge(client, model, trace_text, definitions, examples):
    """Run the judge on a single trace."""
    # Trim to fit context window (use conservative limits)
    ex = examples
    if len(trace_text) + len(definitions) + len(ex) > 100000:
        ex = ex[:15000]
    if len(trace_text) > 80000:
        trace_text = trace_text[:80000]
    
    prompt = JUDGE_PROMPT.format(
        trace=trace_text,
        definitions=definitions,
        examples=ex
    )
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            timeout=180,
        )
        text = extract_model_response(response.choices[0].message)
        return parse_response(text)
    except Exception as e:
        return {"error": str(e)}


MODE_NAMES = {
    "1.1": "Disobey Task Spec", "1.2": "Disobey Role Spec", "1.3": "Step Repetition",
    "1.4": "Loss of Conv History", "1.5": "Unaware of Termination",
    "2.1": "Conversation Reset", "2.2": "Fail to Ask Clarification",
    "2.3": "Task Derailment", "2.4": "Information Withholding",
    "2.5": "Ignored Agent Input", "2.6": "Reasoning-Action Mismatch",
    "3.1": "Premature Termination", "3.2": "No/Incorrect Verification",
    "3.3": "Weak Verification",
}

MODE_LIST = ["1.1", "1.2", "1.3", "1.4", "1.5", 
             "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
             "3.1", "3.2", "3.3"]


def main():
    print("=" * 70, flush=True)
    print("MAST JUDGE VALIDATION: 4 models vs o1 ground truth", flush=True)
    print("=" * 70, flush=True)
    
    # Load dataset
    dataset_path = "/home/djones/.cache/huggingface/hub/datasets--mcemri--MAD/snapshots/5a82e32347f70a701a3c68637de12f8a0be3de3c/MAD_full_dataset.json"
    print(f"\nLoading dataset...", flush=True)
    with open(dataset_path) as f:
        data = json.load(f)
    print(f"Loaded {len(data)} traces", flush=True)
    
    # Verify trace structure
    sample_trace_len = len(get_trace_text(data[0]))
    print(f"Sample trace length: {sample_trace_len} chars", flush=True)
    if sample_trace_len < 50:
        print("WARNING: Trace text too short, extraction broken!", flush=True)
        sys.exit(1)
    
    # Distribution
    mode_counts = Counter()
    for d in data:
        ann = get_official_annotation(d)
        for k, v in ann.items():
            if v == 1:
                mode_counts[k] += 1
    
    print(f"\nOfficial o1 annotation distribution:", flush=True)
    for k in sorted(mode_counts.keys()):
        print(f"  {k}: {mode_counts[k]} ({mode_counts[k]/len(data)*100:.1f}%)", flush=True)
    
    # Sample traces for diversity
    random.seed(42)
    
    failed_traces = [(i, d) for i, d in enumerate(data) 
                    if any(v == 1 for v in get_official_annotation(d).values())]
    clean_traces = [(i, d) for i, d in enumerate(data) 
                   if all(v == 0 for v in get_official_annotation(d).values())]
    
    sampled = []
    used_indices = set()
    
    # Pick 1-2 traces per well-represented mode
    for mode in ["1.5", "2.2", "2.6", "3.3", "1.1", "1.3", "3.2", "3.1"]:
        candidates = [i for i, d in failed_traces 
                     if i not in used_indices 
                     and get_official_annotation(d).get(mode) == 1
                     and len(get_trace_text(d)) < 50000]  # Skip very long traces for speed
        if candidates:
            pick = random.choice(candidates)
            sampled.append(data[pick])
            used_indices.add(pick)
    
    # Add one trace with multiple failures (short)
    multi = [i for i, d in failed_traces 
            if i not in used_indices 
            and sum(v for v in get_official_annotation(d).values()) >= 4
            and len(get_trace_text(d)) < 20000]
    if multi:
        pick = random.choice(multi)
        sampled.append(data[pick])
        used_indices.add(pick)
    
    # Clean traces (short)
    clean_short = [i for i, d in clean_traces 
                  if i not in used_indices 
                  and len(get_trace_text(d)) < 30000]
    for _ in range(min(3, len(clean_short))):
        pick = random.choice(clean_short)
        sampled.append(data[pick])
        used_indices.add(pick)
        clean_short = [c for c in clean_short if c != pick]
    
    print(f"\nSampled {len(sampled)} traces:", flush=True)
    for i, s in enumerate(sampled):
        ann = get_official_annotation(s)
        modes = [k for k, v in ann.items() if v == 1]
        tlen = len(get_trace_text(s))
        print(f"  {i+1}. {s['mas_name']}/{s['benchmark_name']} #{s['trace_id']} ({tlen:,} chars) -- modes: {', '.join(modes) if modes else 'clean'}", flush=True)
    
    # Create gateway client
    client = OpenAI(base_url=GATEWAY_URL, api_key="unused")
    
    # Run judge on each model
    all_results = {}
    
    for model_idx, model in enumerate(MODELS):
        print(f"\n{'='*70}", flush=True)
        print(f"MODEL {model_idx+1}/{len(MODELS)}: {model}", flush=True)
        print(f"{'='*70}", flush=True)
        
        model_results = []
        errors = 0
        
        for i, record in enumerate(sampled):
            trace_text = get_trace_text(record)
            official_ann = get_official_annotation(record)
            mas = record.get("mas_name", "?")
            bench = record.get("benchmark_name", "?")
            tid = record.get("trace_id", "?")
            
            print(f"  [{i+1}/{len(sampled)}] {mas}/{bench} #{tid} ({len(trace_text):,} chars)...", end=" ", flush=True)
            
            result = run_judge(client, model, trace_text, OFFICIAL_DEFINITIONS, OFFICIAL_EXAMPLES)
            
            if "error" in result:
                print(f"ERROR: {result['error'][:60]}", flush=True)
                errors += 1
                model_results.append({
                    "mas_name": mas, "benchmark": bench, "trace_id": tid,
                    "trace_len": len(trace_text), "official": official_ann,
                    "ours": {}, "error": result["error"],
                })
            else:
                modes_found = [k for k, v in result["failure_modes"].items() if v == 1]
                official_modes = [k for k, v in official_ann.items() if v == 1]
                print(f"found {len(modes_found)} (o1: {len(official_modes)})", flush=True)
                
                model_results.append({
                    "mas_name": mas, "benchmark": bench, "trace_id": tid,
                    "trace_len": len(trace_text), "official": official_ann,
                    "ours": result["failure_modes"],
                    "summary": result.get("summary", "")[:150],
                })
            
            time.sleep(3)
        
        all_results[model] = model_results
        valid = len(model_results) - errors
        print(f"\n  Model {model}: {valid}/{len(sampled)} valid, {errors} errors", flush=True)
    
    # ============================================================
    # Calculate agreement with o1 for each model
    # ============================================================
    
    print(f"\n\n{'='*70}", flush=True)
    print(f"CROSS-MODEL COMPARISON AGAINST o1 GROUND TRUTH", flush=True)
    print(f"{'='*70}", flush=True)
    
    model_stats = {}
    for model in MODELS:
        results = all_results[model]
        stats = {}
        total_tp = total_fp = total_tn = total_fn = 0
        
        for mode in MODE_LIST:
            tp = fp = tn = fn = 0
            for r in results:
                if "error" in r:
                    continue
                official = r["official"].get(mode, 0)
                ours = r["ours"].get(mode, 0)
                if ours == 1 and official == 1: tp += 1
                elif ours == 1 and official == 0: fp += 1
                elif ours == 0 and official == 0: tn += 1
                elif ours == 0 and official == 1: fn += 1
            
            total = tp + fp + tn + fn
            accuracy = (tp + tn) / total if total > 0 else 0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            stats[mode] = {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
                           "accuracy": accuracy, "precision": precision,
                           "recall": recall, "f1": f1}
            total_tp += tp; total_fp += fp; total_tn += tn; total_fn += fn
        
        overall_total = total_tp + total_fp + total_tn + total_fn
        overall_acc = (total_tp + total_tn) / overall_total if overall_total > 0 else 0
        overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0
        
        model_stats[model] = {
            "per_mode": stats,
            "overall": {
                "accuracy": overall_acc, "precision": overall_prec,
                "recall": overall_rec, "f1": overall_f1,
                "tp": total_tp, "fp": total_fp, "tn": total_tn, "fn": total_fn,
            }
        }
    
    # Sort by F1
    sorted_models = sorted(MODELS, key=lambda m: model_stats[m]["overall"]["f1"], reverse=True)
    
    # Overall comparison table
    print(f"\n{'Model':<22} {'Acc':>7} {'Prec':>7} {'Rec':>7} {'F1':>7} {'TP':>4} {'FP':>4} {'TN':>4} {'FN':>4}", flush=True)
    print(f"{'-'*22} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*4} {'-'*4} {'-'*4} {'-'*4}", flush=True)
    
    for model in sorted_models:
        s = model_stats[model]["overall"]
        marker = " <-- BEST" if model == sorted_models[0] else ""
        print(f"{model:<22} {s['accuracy']:>6.1%} {s['precision']:>6.1%} {s['recall']:>6.1%} {s['f1']:>6.1%} {s['tp']:>4} {s['fp']:>4} {s['tn']:>4} {s['fn']:>4}{marker}", flush=True)
    
    # Per-mode detail for best model
    best_model = sorted_models[0]
    best_stats = model_stats[best_model]["per_mode"]
    
    print(f"\n{'='*70}", flush=True)
    print(f"PER-MODE DETAIL (BEST: {best_model})", flush=True)
    print(f"{'='*70}", flush=True)
    
    print(f"\n{'Mode':<6} {'Name':<30} {'TP':>3} {'FP':>3} {'TN':>3} {'FN':>3} {'Acc':>7} {'Prec':>7} {'Rec':>7} {'F1':>7}", flush=True)
    print(f"{'-'*6} {'-'*30} {'-'*3} {'-'*3} {'-'*3} {'-'*3} {'-'*7} {'-'*7} {'-'*7} {'-'*7}", flush=True)
    
    for mode in MODE_LIST:
        s = best_stats[mode]
        name = MODE_NAMES.get(mode, "?")[:30]
        print(f"{mode:<6} {name:<30} {s['tp']:>3} {s['fp']:>3} {s['tn']:>3} {s['fn']:>3} {s['accuracy']:>6.1%} {s['precision']:>6.1%} {s['recall']:>6.1%} {s['f1']:>6.1%}", flush=True)
    
    # Per-trace comparison across models
    print(f"\n{'='*70}", flush=True)
    print(f"PER-TRACE COMPARISON", flush=True)
    print(f"{'='*70}", flush=True)
    
    for i in range(len(sampled)):
        record = sampled[i]
        mas = record.get("mas_name", "?")
        bench = record.get("benchmark_name", "?")
        official = get_official_annotation(record)
        official_modes = sorted([k for k, v in official.items() if v == 1])
        
        print(f"\nTrace {i+1}: {mas}/{bench} #{record.get('trace_id',0)} ({len(get_trace_text(record)):,} chars)", flush=True)
        print(f"  o1:       {', '.join(official_modes) if official_modes else 'clean'}", flush=True)
        
        for model in sorted_models:
            r = all_results[model][i]
            if r.get("error"):
                print(f"  {model:>20}: ERROR", flush=True)
            else:
                our_modes = sorted([k for k, v in r["ours"].items() if v == 1])
                missed = set(official_modes) - set(our_modes)
                extra = set(our_modes) - set(official_modes)
                match = "OK" if not missed and not extra else f"missed={','.join(sorted(missed))} extra={','.join(sorted(extra))}"
                print(f"  {model:>20}: {', '.join(our_modes) if our_modes else 'clean':>12} {match}", flush=True)
    
    # Inter-model agreement
    print(f"\n{'='*70}", flush=True)
    print(f"INTER-MODEL AGREEMENT (pairwise)", flush=True)
    print(f"{'='*70}", flush=True)
    
    for i, m1 in enumerate(MODELS):
        for m2 in MODELS[i+1:]:
            agree = 0
            total = 0
            for mode in MODE_LIST:
                for r1, r2 in zip(all_results[m1], all_results[m2]):
                    if r1.get("error") or r2.get("error"):
                        continue
                    v1 = r1["ours"].get(mode, 0)
                    v2 = r2["ours"].get(mode, 0)
                    if v1 == v2:
                        agree += 1
                    total += 1
            pct = agree / total * 100 if total > 0 else 0
            print(f"  {m1} vs {m2}: {agree}/{total} agree ({pct:.1f}%)", flush=True)
    
    # Final summary
    print(f"\n{'='*70}", flush=True)
    print(f"SUMMARY", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"Sample:      {len(sampled)} traces from {len(data)} total", flush=True)
    print(f"Ground truth: o1 annotations (paper authors)", flush=True)
    print(f"Models:       {', '.join(MODELS)}", flush=True)
    print(f"", flush=True)
    print(f"Rankings by F1:", flush=True)
    for rank, model in enumerate(sorted_models, 1):
        s = model_stats[model]["overall"]
        print(f"  {rank}. {model}: Acc={s['accuracy']:.1%} Prec={s['precision']:.1%} Rec={s['recall']:.1%} F1={s['f1']:.1%}", flush=True)
    
    # Save
    output_path = "/tmp/mast-skills/tests/judge_validation_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "models": MODELS,
            "sample_size": len(sampled),
            "total_traces": len(data),
            "model_stats": {k: {"per_mode": v["per_mode"], "overall": v["overall"]} for k, v in model_stats.items()},
            "per_trace": all_results,
        }, f, indent=2, default=str)
    
    print(f"\nFull results saved to: {output_path}", flush=True)


if __name__ == "__main__":
    main()