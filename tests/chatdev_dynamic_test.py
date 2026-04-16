#!/usr/bin/env python3
"""
ChatDev Prompt Comparison: Extract system prompts from baseline and MAST-hardened
ChatDev YAMLs, then run our 14-mode dynamic test harness against them.

This validates whether MAST-hardened ChatDev prompts reduce failure mode
susceptibility in the same ChatDev agents used in the MAST paper.
"""
import json
import os
import sys
import re
from openai import OpenAI

sys.path.insert(0, "/tmp/mast-skills/tests")
from test_harness import TEST_CASES, extract_model_response

GATEWAY_URL = "http://127.0.0.1:11434/v1"
MODEL = "gemma4:31b-cloud"

# Extract ChatDev agent prompts by parsing YAML with regex
def extract_chatdev_prompts(yaml_path):
    """Extract all agent role prompts from a ChatDev YAML."""
    with open(yaml_path) as f:
        content = f.read()
    
    # Find COMMON_PROMPT from vars section
    common_match = re.search(r'COMMON_PROMPT:\s*(.*?)(?=\n\s*\w+:|\n\s*$)', content, re.DOTALL)
    common = common_match.group(1).strip() if common_match else ""
    # Clean up YAML multiline
    common = re.sub(r'\s+', ' ', common)
    
    # Find all agent role sections
    roles = {}
    # Pattern: after "role: |-" until next config key
    role_pattern = re.finditer(
        r'-\s*id:\s+([^\n]+)\s*\n\s+type:\s+agent\s*\n\s+config:\s*\n.*?role:\s*\|-?\n(.*?)(?=\n\s+provider:|\n\s+base_url:|\n\s+api_key:)',
        content, re.DOTALL
    )
    
    for match in role_pattern:
        node_id = match.group(1)
        role_text = match.group(2).strip()
        # Replace ${COMMON_PROMPT} with actual common prompt
        role_text = role_text.replace("${COMMON_PROMPT}", common)
        roles[node_id] = role_text
    
    return common, roles


def build_system_prompt(roles, include_mast=False):
    """Build a combined system prompt from ChatDev agent roles."""
    # Use the Programmer role as primary (most coding-focused)
    programmer_role = roles.get("Programmer Coding", "")
    
    if not programmer_role:
        # Fallback: combine all roles
        programmer_role = "\n\n".join(f"Agent {name}:\n{role}" for name, role in roles.items())
    
    return programmer_role


def run_chatdev_comparison():
    """Run our 14-mode dynamic test against both ChatDev configs."""
    
    print("=" * 70)
    print("CHATDEV MAST REPRODUCTION: Dynamic Test Comparison")
    print("Testing ChatDev baseline vs MAST-hardened agent prompts")
    print("=" * 70)
    
    # Extract prompts from both YAMLs
    baseline_path = "/tmp/ChatDev/yaml_instance/ChatDev_v1_gw.yaml"
    mast_path = "/tmp/ChatDev/yaml_instance/ChatDev_v1_mast_gw.yaml"
    
    print("\nExtracting ChatDev agent prompts...")
    _, baseline_roles = extract_chatdev_prompts(baseline_path)
    _, mast_roles = extract_chatdev_prompts(mast_path)
    
    print(f"  Baseline agents: {list(baseline_roles.keys())[:5]}...")
    print(f"  MAST agents: {list(mast_roles.keys())[:5]}...")
    
    # Use the Programmer Coding role (most relevant to our failure modes)
    baseline_prompt = baseline_roles.get("Programmer Coding", "")
    mast_prompt = mast_roles.get("Programmer Coding", "")
    
    if not baseline_prompt:
        print("ERROR: Could not extract Programmer Coding role from baseline YAML")
        return
    
    # Check MAST additions
    mast_additions = []
    for marker in ["Anti-Loop", "MAST", "FM-1.3", "FM-2.4", "FM-3.2", "FM-3.3", "TERMINATION", "VERIFICATION"]:
        if marker in mast_prompt and marker not in baseline_prompt:
            mast_additions.append(marker)
    print(f"  MAST additions found: {mast_additions}")
    
    # Run against our 14 test modes
    client = OpenAI(base_url=GATEWAY_URL, api_key="unused")
    
    modes = ["FM-1.1", "FM-1.2", "FM-1.3", "FM-1.4", "FM-1.5", 
             "FM-2.1", "FM-2.2", "FM-2.3", "FM-2.4", "FM-2.5", "FM-2.6",
             "FM-3.1", "FM-3.2", "FM-3.3"]
    
    test_map = {tc['id']: tc for tc in TEST_CASES}
    
    results = {"baseline": {}, "mast": {}}
    
    for config_name, system_prompt in [("baseline", baseline_prompt), ("mast", mast_prompt)]:
        pass_count = 0
        print(f"\n{'='*50}")
        print(f"Testing {config_name} ChatDev config")
        print(f"{'='*50}")
        
        for mode in modes:
            tc = test_map.get(mode)
            if not tc:
                continue
            
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
                print(f"  {mode}: ERROR - {e}")
                results[config_name][mode] = {"verdict": "ERROR", "error": str(e)}
                continue
            
            # Judge
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
                verdict = "ERROR"
            
            results[config_name][mode] = {
                "verdict": verdict,
                "response_preview": agent_response[:200]
            }
            
            if verdict == "PASS":
                pass_count += 1
            status = "PASS" if verdict == "PASS" else "FAIL"
            print(f"  {mode}: {status}")
        
        print(f"\n  {config_name} total: {pass_count}/14")
    
    # Compare
    print(f"\n{'='*70}")
    print("COMPARISON: ChatDev Baseline vs MAST-Hardened")
    print(f"{'='*70}")
    print(f"\n{'Mode':<8} {'Baseline':>10} {'MAST':>10} {'Delta':>10}")
    print("-" * 38)
    
    baseline_pass = 0
    mast_pass = 0
    for mode in modes:
        b = results["baseline"].get(mode, {}).get("verdict", "?")
        m = results["mast"].get(mode, {}).get("verdict", "?")
        delta = ""
        if b == "FAIL" and m == "PASS":
            delta = "+DEFENDED"
        elif b == "PASS" and m == "FAIL":
            delta = "-REGRESS"
        elif b == m:
            delta = "same"
        print(f"{mode:<8} {b:>10} {m:>10} {delta:>10}")
        
        if b == "PASS": baseline_pass += 1
        if m == "PASS": mast_pass += 1
    
    print(f"\n{'Total':<8} {baseline_pass:>10}/14 {mast_pass:>10}/14")
    
    # Save
    output_path = "/tmp/mast-skills/tests/results/chatdev_dynamic_comparison.json"
    with open(output_path, 'w') as f:
        json.dump({
            "model": MODEL,
            "baseline_system_prompt_len": len(baseline_prompt),
            "mast_system_prompt_len": len(mast_prompt),
            "baseline_pass": baseline_pass,
            "mast_pass": mast_pass,
            "results": results
        }, f, indent=2, default=str)
    
    print(f"\nResults saved to {output_path}")
    
    return baseline_pass, mast_pass


if __name__ == "__main__":
    run_chatdev_comparison()