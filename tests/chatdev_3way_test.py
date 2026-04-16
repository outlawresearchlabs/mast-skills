#!/usr/bin/env python3
"""
ChatDev Dynamic Test: Compare baseline, MAST-full, and MAST-lite configs.
"""
import json
import os
import sys
import re
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_harness import TEST_CASES

GATEWAY_URL = "http://127.0.0.1:11434/v1"
MODEL = "gemma4:31b-cloud"

def extract_role(yaml_path, role_name="Programmer Coding"):
    """Extract a specific agent role from ChatDev YAML."""
    with open(yaml_path) as f:
        content = f.read()
    # Find the role after "id: <role_name>"
    pattern = rf'- id: {re.escape(role_name)}\s+.*?role: \|-?\n(.*?)(?=\n        provider:)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: grab first role
    pattern2 = r'role: \|-?\n(.*?)(?=\n        provider:)'
    match2 = re.search(pattern2, content, re.DOTALL)
    if match2:
        return match2.group(1).strip()
    return ""


def run_test(system_prompt, trigger_prompt, eval_prompt, client):
    """Run a single test and return verdict."""
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": trigger_prompt}
        ]
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.3, timeout=60,
        )
        msg = response.choices[0].message
        agent_response = msg.content if msg.content else (msg.reasoning if hasattr(msg, 'reasoning') and msg.reasoning else str(msg))
    except Exception as e:
        return "ERROR", str(e)
    
    try:
        judge_messages = [
            {"role": "system", "content": "You are a precise binary classifier. Answer ONLY 'PASS' or 'FAIL'."},
            {"role": "user", "content": f"{eval_prompt}\n\nAgent response:\n{agent_response}"}
        ]
        judge_response = client.chat.completions.create(
            model=MODEL, messages=judge_messages, temperature=0.1, timeout=30,
        )
        jmsg = judge_response.choices[0].message
        judge_text = (jmsg.content if jmsg.content else (jmsg.reasoning if hasattr(jmsg, 'reasoning') and jmsg.reasoning else "")).strip().upper()
        verdict = "PASS" if "PASS" in judge_text and "FAIL" not in judge_text else "FAIL"
    except Exception as e:
        verdict = "ERROR"
    
    return verdict, agent_response[:200]


def main():
    print("=" * 70)
    print("CHATDEV DYNAMIC TEST: Baseline vs MAST-Full vs MAST-Lite")
    print("=" * 70)
    
    # ChatDev paths -- clone ChatDev and set CHATDEV_DIR env var
    chatdev_dir = os.environ.get("CHATDEV_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ChatDev"))
    yaml_dir = os.path.join(chatdev_dir, "yaml_instance")
    
    configs = {
        "baseline": os.path.join(yaml_dir, "ChatDev_v1_gw.yaml"),
        "mast_full": os.path.join(yaml_dir, "ChatDev_v1_mast_gw.yaml"),
        "mast_lite": os.path.join(yaml_dir, "ChatDev_v1_mast_lite.yaml"),
    }
    
    prompts = {}
    for name, path in configs.items():
        role = extract_role(path)
        prompts[name] = role
        print(f"  {name}: {len(role)} chars")
    
    client = OpenAI(base_url=GATEWAY_URL, api_key="unused")
    test_map = {tc['id']: tc for tc in TEST_CASES}
    modes = ["FM-1.1", "FM-1.2", "FM-1.3", "FM-1.4", "FM-1.5", 
             "FM-2.1", "FM-2.2", "FM-2.3", "FM-2.4", "FM-2.5", "FM-2.6",
             "FM-3.1", "FM-3.2", "FM-3.3"]
    
    results = {}
    for config_name in ["baseline", "mast_full", "mast_lite"]:
        pass_count = 0
        results[config_name] = {}
        print(f"\n--- {config_name} ---")
        
        for mode in modes:
            tc = test_map.get(mode)
            if not tc:
                continue
            
            verdict, preview = run_test(
                prompts[config_name], tc['trigger_prompt'], tc['evaluation_prompt'], client
            )
            results[config_name][mode] = {"verdict": verdict, "preview": preview}
            if verdict == "PASS":
                pass_count += 1
            print(f"  {mode}: {verdict}")
        
        print(f"  TOTAL: {pass_count}/14")
    
    # Summary comparison
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"\n{'Mode':<8} {'Baseline':>10} {'MAST-Full':>10} {'MAST-Lite':>10}")
    print("-" * 40)
    
    for mode in modes:
        b = results["baseline"].get(mode, {}).get("verdict", "?")
        f = results["mast_full"].get(mode, {}).get("verdict", "?")
        l = results["mast_lite"].get(mode, {}).get("verdict", "?")
        print(f"{mode:<8} {b:>10} {f:>10} {l:>10}")
    
    b_total = sum(1 for m in modes if results["baseline"].get(m, {}).get("verdict") == "PASS")
    f_total = sum(1 for m in modes if results["mast_full"].get(m, {}).get("verdict") == "PASS")
    l_total = sum(1 for m in modes if results["mast_lite"].get(m, {}).get("verdict") == "PASS")
    print(f"\n{'Total':<8} {b_total:>10}/14 {f_total:>10}/14 {l_total:>10}/14")
    
    # Save
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "chatdev_3way_comparison.json")
    with open(output_path, 'w') as f:
        json.dump({
            "model": MODEL,
            "baseline_pass": b_total,
            "mast_full_pass": f_total,
            "mast_lite_pass": l_total,
            "prompt_lengths": {k: len(v) for k, v in prompts.items()},
            "results": results
        }, f, indent=2, default=str)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()