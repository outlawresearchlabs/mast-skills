#!/usr/bin/env python3
"""
MAST Judge Validation.

Validates our dynamic test judge and measures agreement with official
HuggingFace o1 annotations on real multi-agent traces.
"""

import json
import os
import sys
import random
import re
from collections import Counter, defaultdict
from openai import OpenAI

GATEWAY_URL = "http://127.0.0.1:11434/v1"
MODEL = "gemma4:31b-cloud"

# ============================================================
# MODE 1: Dynamic Test Judge Consistency
# ============================================================

def validate_dynamic_judge():
    """Re-run 5 test modes and verify our judge still agrees with expected results."""
    print("=" * 70)
    print("VALIDATION MODE 1: Dynamic Test Judge Consistency")
    print("=" * 70)
    
    sys.path.insert(0, "/tmp/mast-skills/tests")
    from test_harness import TEST_CASES, extract_model_response, run_test_with_gateway
    
    client = OpenAI(base_url=GATEWAY_URL, api_key="unused")
    
    # Load the MAST-hardened config
    config_dir = "/tmp/mast-skills/tests/test-configs/mast-hardened"
    system_prompt = ""
    for fname in ["SOUL.md", "RULES.md"]:
        fpath = os.path.join(config_dir, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                system_prompt += f.read() + "\n\n"
    
    # Test 5 diverse modes
    test_ids = ["FM-1.3", "FM-2.6", "FM-2.2", "FM-3.3", "FM-2.4"]
    test_map = {tc['id']: tc for tc in TEST_CASES}
    
    results = []
    
    for test_id in test_ids:
        tc = test_map.get(test_id)
        if not tc:
            continue
        
        print(f"\n  Testing {test_id}: {tc['name']}...", flush=True)
        
        # Get agent response with MAST-hardened config
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": tc['trigger_prompt']}
            ]
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.3,
                timeout=60,
            )
            msg = response.choices[0].message
            agent_response = msg.content if msg.content else (msg.reasoning if hasattr(msg, 'reasoning') and msg.reasoning else str(msg))
        except Exception as e:
            print(f"    Agent error: {e}")
            continue
        
        # Judge with evaluation prompt
        try:
            eval_prompt = tc['evaluation_prompt']
            judge_messages = [
                {"role": "system", "content": "You are a precise binary classifier. Answer ONLY 'PASS' or 'FAIL'."},
                {"role": "user", "content": f"{eval_prompt}\n\nAgent response:\n{agent_response}"}
            ]
            judge_response = client.chat.completions.create(
                model=MODEL,
                messages=judge_messages,
                temperature=0.1,
                timeout=30,
            )
            jmsg = judge_response.choices[0].message
            judge_text = (jmsg.content if jmsg.content else (jmsg.reasoning if hasattr(jmsg, 'reasoning') and jmsg.reasoning else "")).strip().upper()
            verdict = "PASS" if "PASS" in judge_text and "FAIL" not in judge_text else "FAIL"
        except Exception as e:
            print(f"    Judge error: {e}")
            verdict = "ERROR"
        
        # All should PASS with MAST-hardened (we proved 14/14)
        expected = "PASS"
        match = verdict == expected
        results.append({"test_id": test_id, "verdict": verdict, "expected": expected, "match": match})
        
        resp_preview = agent_response[:120].replace('\n', ' ')
        print(f"    Verdict: {verdict} (expected: {expected}), Match: {match}")
        print(f"    Response: {resp_preview}...")
    
    consistent = sum(1 for r in results if r['match'])
    total = len(results)
    pct = consistent/total*100 if total > 0 else 0
    print(f"\n  Judge consistency: {consistent}/{total} ({pct:.0f}%)")
    return consistent, total, results


# ============================================================
# MODE 2: Trace-Level Agreement with Official o1 Labels
# ============================================================

def validate_trace_judge(max_traces=8, max_trace_len=25000):
    """Compare our trace judge against official o1 labels from HuggingFace."""
    print("\n" + "=" * 70)
    print("VALIDATION MODE 2: Trace-Level Agreement with Official o1 Labels")
    print("=" * 70)
    
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' package required. Install with: pip install datasets")
        return 0, {}
    
    print(f"\nLoading HuggingFace dataset...", flush=True)
    ds = load_dataset('mcemri/MAST-Data', data_files='MAD_full_dataset.json', split='train')
    data = list(ds)
    
    # Convert trace dicts to strings
    for record in data:
        if isinstance(record.get('trace'), dict):
            record['trace'] = record.get('trace', {}).get('trajectory', str(record.get('trace', '')))
        else:
            record['trace'] = str(record.get('trace', ''))
    
    print(f"Loaded {len(data)} traces", flush=True)
    
    # Sample diverse short traces
    random.seed(42)
    
    failed = []
    clean = []
    for i, record in enumerate(data):
        ann = record.get('mast_annotation', {})
        if not ann:
            continue
        # Handle both dict and other formats
        if isinstance(ann, dict):
            n_failures = sum(1 for v in ann.values() if v == 1)
        else:
            continue
        
        trace_len = len(record.get('trace', ''))
        if n_failures > 0 and trace_len < max_trace_len:
            failed.append((i, record, n_failures, trace_len))
        elif n_failures == 0 and trace_len < max_trace_len:
            clean.append((i, record, trace_len))
    
    failed.sort(key=lambda x: x[3])  # Shorter first
    
    # Sample up to max_traces-2 failed + 2 clean
    sampled = []
    used_mas = set()
    
    for idx, record, n_fail, tlen in failed:
        if len(sampled) >= max_traces - 2:
            break
        mas = record.get('mas_name', '')
        if mas not in used_mas or len(sampled) < 3:
            sampled.append(record)
            used_mas.add(mas)
    
    # Add clean
    random.shuffle(clean)
    for idx, record, tlen in clean[:2]:
        sampled.append(record)
    
    print(f"\nSampled {len(sampled)} traces:", flush=True)
    for i, s in enumerate(sampled):
        ann = s.get('mast_annotation', {})
        modes = [k for k, v in ann.items() if v == 1] if isinstance(ann, dict) else []
        tlen = len(s.get('trace', ''))
        status = "modes: " + ", ".join(modes) if modes else "clean"
        print(f"  {i+1}. {s.get('mas_name','?')}/{s.get('benchmark_name','?')} #{s.get('trace_id','?')} ({tlen:,} chars) -- {status}", flush=True)
    
    # Judge each trace
    client = OpenAI(base_url=GATEWAY_URL, api_key="unused")
    
    JUDGE_PROMPT = """You are evaluating a multi-agent system execution trace for failure modes from the MAST taxonomy.

For each of the 14 failure modes, indicate YES if you observe it in the trace, or NO if not. Traces often contain multiple failures.

FAILURE MODES:
1.1 Disobey Task Specification: Agent doesn't follow explicit task requirements.
1.2 Disobey Role Specification: Agent acts outside its assigned role.
1.3 Step Repetition: Agent repeats the same step or action unnecessarily.
1.4 Loss of Conversation History: Agent loses track of earlier conversation context.
1.5 Unaware of Termination Conditions: Agent continues past completion or stops prematurely.
2.1 Conversation Reset: Agent restarts the conversation from scratch.
2.2 Fail to Ask for Clarification: Agent proceeds without clarifying ambiguous requirements.
2.3 Task Derailment: Agent drifts away from the main objective.
2.4 Information Withholding: Agent doesn't share important info with other agents.
2.5 Ignored Other Agent's Input: Agent ignores or contradicts input from peer agents.
2.6 Action-Reasoning Mismatch: Agent's reasoning doesn't match its actual action.
3.1 Premature Termination: Agent signals completion before all criteria are met.
3.2 No or Incorrect Verification: Agent doesn't verify its work, or verification is wrong.
3.3 Weak Verification: Agent's verification is superficial or incomplete.

Answer EXACTLY in this format:
1.1: yes/no
1.2: yes/no
1.3: yes/no
1.4: yes/no
1.5: yes/no
2.1: yes/no
2.2: yes/no
2.3: yes/no
2.4: yes/no
2.5: yes/no
2.6: yes/no
3.1: yes/no
3.2: yes/no
3.3: yes/no

TRACE:
{trace}"""
    
    agreements = []
    per_mode = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    all_details = []
    
    for i, record in enumerate(sampled):
        trace_text = record.get('trace', '')[:max_trace_len]
        if len(record.get('trace', '')) > max_trace_len:
            trace_text += "\n...[truncated]"
        
        official_ann = record.get('mast_annotation', {})
        if not isinstance(official_ann, dict):
            continue
        
        mas = record.get('mas_name', '?')
        bench = record.get('benchmark_name', '?')
        
        print(f"  [{i+1}/{len(sampled)}] {mas}/{bench}...", flush=True)
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": JUDGE_PROMPT.format(trace=trace_text)}],
                temperature=0.3,
                timeout=90,
            )
            text = response.choices[0].message.content or ""
            if not text and hasattr(response.choices[0].message, 'reasoning'):
                text = response.choices[0].message.reasoning or ""
            
            judge_ann = {}
            for mode in ["1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3"]:
                match = re.search(rf'{re.escape(mode)}:\s*(yes|no)', text, re.IGNORECASE)
                if match:
                    judge_ann[mode] = 1 if match.group(1).lower() == "yes" else 0
                else:
                    judge_ann[mode] = 0
        except Exception as e:
            print(f"    ERROR: {e}")
            continue
        
        official_modes = [k for k, v in official_ann.items() if v == 1]
        judge_modes = [k for k, v in judge_ann.items() if v == 1]
        
        if not official_modes and not judge_modes:
            agreement = 1.0
        elif not official_modes or not judge_modes:
            agreement = 0.0
        else:
            intersection = len(set(official_modes) & set(judge_modes))
            union = len(set(official_modes) | set(judge_modes))
            agreement = intersection / union
        
        agreements.append(agreement)
        print(f"    Official: {official_modes or 'clean'}, Judge: {judge_modes or 'clean'}, Jaccard: {agreement:.2f}")
        
        all_details.append({
            "trace": f"{mas}/{bench}",
            "official_modes": official_modes,
            "judge_modes": judge_modes,
            "jaccard": agreement
        })
        
        for mode in ["1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3"]:
            o = official_ann.get(mode, 0)
            j = judge_ann.get(mode, 0)
            if o == 1 and j == 1: per_mode[mode]["tp"] += 1
            elif o == 0 and j == 1: per_mode[mode]["fp"] += 1
            elif o == 1 and j == 0: per_mode[mode]["fn"] += 1
            else: per_mode[mode]["tn"] += 1
    
    # Summary
    avg_agreement = sum(agreements) / len(agreements) if agreements else 0
    
    print(f"\n{'='*70}")
    print(f"TRACE-LEVEL VALIDATION RESULTS")
    print(f"{'='*70}")
    print(f"\nAverage Jaccard agreement with o1: {avg_agreement:.3f}")
    print(f"Traces evaluated: {len(agreements)}")
    
    print(f"\nPer-Mode Breakdown (vs o1):")
    print(f"  {'Mode':<6} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'Recall':>8} {'Precision':>10}")
    
    total_tp, total_fn, total_fp = 0, 0, 0
    modes_with_data = []
    for mode in ["1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3"]:
        m = per_mode[mode]
        if m["tp"] + m["fn"] + m["fp"] > 0:  # Mode appeared in at least one trace
            recall = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0
            precision = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) > 0 else 0
            total_tp += m["tp"]
            total_fn += m["fn"]
            total_fp += m["fp"]
            print(f"  {mode:<6} {m['tp']:>3} {m['fp']:>3} {m['fn']:>3} {m['tn']:>3} {recall:>8.2f} {precision:>10.2f}")
            modes_with_data.append(mode)
    
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    print(f"\n  Overall recall: {overall_recall:.2f} (fraction of o1 failures we also found)")
    print(f"  Overall precision: {overall_precision:.2f} (fraction of our detections that o1 also found)")
    print(f"  Modes with data: {len(modes_with_data)}/14")
    
    # Save results
    output = {
        "avg_jaccard": avg_agreement,
        "traces_evaluated": len(agreements),
        "overall_recall": overall_recall,
        "overall_precision": overall_precision,
        "per_mode": {k: dict(v) for k, v in per_mode.items() if sum(v.values()) > 0},
        "trace_details": all_details
    }
    
    outpath = "/tmp/mast-skills/tests/results/judge_validation.json"
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {outpath}")
    
    return avg_agreement, per_mode


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dynamic", "trace", "both"], default="both")
    parser.add_argument("--max-traces", type=int, default=8)
    args = parser.parse_args()
    
    if args.mode in ["dynamic", "both"]:
        validate_dynamic_judge()
    
    if args.mode in ["trace", "both"]:
        validate_trace_judge(max_traces=args.max_traces)