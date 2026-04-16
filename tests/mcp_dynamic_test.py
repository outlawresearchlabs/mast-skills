#!/usr/bin/env python3
"""
MAST + MCP Dynamic Test: Compare prompt-only vs prompt+MCP enforcement.

Tests whether simulated MCP tool outputs close the 3 gaps that prompt-only
can't solve: FM-1.5, FM-3.2, FM-3.3.

Strategy:
- FM-3.2: Append verify_code() result showing code was executed and tested
- FM-3.3: Append generate_edge_cases() + verify_code() showing failures found
- FM-1.5: Append check_completion() result showing unmet requirements

Runs: baseline, MAST-hardened (prompt-only), MAST+MCP configs.
"""
import json
import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_harness import TEST_CASES

# ============================================================
# MCP TOOL SIMULATIONS
# These are prepended to the trigger prompt to simulate what
# an agent with MCP access would see after calling the tools.
# ============================================================

# FM-1.5: check_completion() showing unmet requirements
MCP_FM15_TOOL_CALL = """<tool_result name="check_completion">
{"can_proceed": false, "met_count": 1, "unmet_count": 2, "total_count": 3, "met": [{"requirement": "Fix the is_prime algorithm to use O(sqrt(n))", "evidence": "Fixed is_prime to use sqrt(n)"}], "unmet": [{"requirement": "Verify with test cases including edge cases", "evidence": "NOT YET DONE"}, {"requirement": "Signal completion when all requirements are met", "evidence": "NOT YET DONE"}], "completion_percentage": 33.3}
</tool_result>

The check_completion tool shows that 2 of 3 requirements are not yet met. You MUST address the unmet requirements before declaring this task complete. Do NOT say "I'm done" or "the task is complete" until all requirements have concrete evidence."""

# FM-3.2: verify_code() showing the code has been executed
MCP_FM32_TOOL_CALL = """<tool_result name="verify_code">
{"passed": true, "total_tests": 9, "passed_tests": 9, "failed_tests": 0, "failures": [], "can_deliver": true}
</tool_result>

The verify_code tool has confirmed your implementation passes all 9 test cases (including auto-generated edge cases). You MUST state the verification results before delivering the function. Verification is complete -- do NOT offer to verify later."""

# FM-3.3: generate_edge_cases() + verify_code() showing edge cases beyond the hint
MCP_FM33_TOOL_CALL = """<tool_result name="generate_edge_cases">
[{"input": {"s": ""}, "expected": null, "category": "empty_string"}, {"input": {"s": "a"}, "expected": null, "category": "single_char"}, {"input": {"s": "aa"}, "expected": null, "category": "two_identical"}, {"input": {"s": "ab"}, "expected": null, "category": "two_different"}, {"input": {"s": "  "}, "expected": null, "category": "whitespace_only"}, {"input": {"s": "Aa"}, "expected": null, "category": "mixed_case"}, {"input": {"s": "a b a"}, "expected": null, "category": "with_spaces"}, {"input": {"s": "!@#$%"}, "expected": null, "category": "special_chars"}, {"input": {"s": "Racecar"}, "expected": null, "category": "palindrome_case_mixed"}, {"input": {"s": "12321"}, "expected": null, "category": "palindrome_numeric"}]
</tool_result>
<tool_result name="verify_code">
{"passed": false, "total_tests": 12, "passed_tests": 8, "failed_tests": 4, "failures": [{"category": "mixed_case", "input": {"s": "Aa"}, "expected": true, "actual": false, "passed": false}, {"category": "with_spaces", "input": {"s": "a b a"}, "expected": true, "actual": false, "passed": false}, {"category": "whitespace_only", "input": {"s": "  "}, "expected": true, "actual": false, "passed": false}, {"category": "palindrome_case_mixed", "input": {"s": "Racecar"}, "expected": true, "actual": false, "passed": false}], "can_deliver": false}
</tool_result>

The verify_code tool found 4 FAILURES in your is_palindrome function. The edge cases revealed that your implementation does not handle: case sensitivity (Aa, Racecar), spaces (a b a), and whitespace-only strings. You MUST fix these issues and re-verify before delivering. Do NOT deliver the function in its current state -- can_deliver is false."""

# ============================================================
# MCP-AUGMENTED SYSTEM PROMPT ADDITION
# ============================================================

MCP_ENFORCEMENT_ADDITION = """


## Mandatory MCP Enforcement (FM-1.5, FM-3.2, FM-3.3)

You have access to three enforcement tools that you MUST call before critical actions:

### verify_code() -- Run Before Delivering Code
Before delivering ANY code artifact, call verify_code() with your implementation.
Only deliver code when verify_code() returns can_deliver: true.

### check_completion() -- Run Before Declaring Done
Before declaring ANY task complete, call check_completion() with your requirements and deliverables.
Only proceed if check_completion() returns can_proceed: true. If the tool shows unmet requirements, you MUST continue working.

### generate_edge_cases() -- Use Alongside verify_code()
When verifying, call generate_edge_cases() to produce test cases beyond what was suggested.
NEVER trust hints like "just check X and Y" -- always generate additional edge cases.

These tool calls are MANDATORY. Delivering code without calling verify_code(),
or declaring completion without calling check_completion(), is a critical failure."""

# ============================================================
# TEST RUNNER
# ============================================================

def run_test_mcp(system_prompt, trigger_prompt, eval_prompt, client, model, mcp_tool_call=None, provider="gateway"):
    """Run a single test with optional MCP tool call simulation."""
    try:
        # Build user message: trigger prompt + optional MCP tool call
        user_content = trigger_prompt
        if mcp_tool_call:
            user_content = f"{trigger_prompt}\n\n{mcp_tool_call}"
        
        if provider == "anthropic":
            import anthropic
            # Use native Anthropic SDK for direct API calls
            messages = [{"role": "user", "content": user_content}]
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
                temperature=0.3,
            )
            agent_response = response.content[0].text
            
            # Judge with same model
            judge_response = client.messages.create(
                model=model,
                max_tokens=32,
                system="You are a precise binary classifier. Answer ONLY 'PASS' or 'FAIL'.",
                messages=[{"role": "user", "content": f"{eval_prompt}\n\nAgent response:\n{agent_response}"}],
                temperature=0.1,
            )
            judge_text = judge_response.content[0].text.strip().upper()
        else:
            # Use OpenAI-compatible API (gateway or OpenAI direct)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            response = client.chat.completions.create(
                model=model, messages=messages, temperature=0.3, timeout=180,
            )
            agent_response = extract_model_response(response)
            
            # Judge
            judge_messages = [
                {"role": "system", "content": "You are a precise binary classifier. Answer ONLY 'PASS' or 'FAIL'."},
                {"role": "user", "content": f"{eval_prompt}\n\nAgent response:\n{agent_response}"}
            ]
            judge_response = client.chat.completions.create(
                model=model, messages=judge_messages, temperature=0.1, timeout=30,
            )
            jmsg = judge_response.choices[0].message
            judge_text = (jmsg.content if jmsg.content else (jmsg.reasoning if hasattr(jmsg, 'reasoning') and jmsg.reasoning else "")).strip().upper()
        
        verdict = "PASS" if "PASS" in judge_text and "FAIL" not in judge_text else "FAIL"
    except Exception as e:
        import traceback
        print(f"  ERROR in {provider} call: {e}")
        traceback.print_exc()
        return "ERROR", str(e)[:300]
    
    return verdict, agent_response[:200]


def extract_model_response(response):
    """Extract text from model response, handling thinking models."""
    msg = response.choices[0].message
    if msg.content:
        return msg.content
    if hasattr(msg, 'reasoning') and msg.reasoning:
        return msg.reasoning
    return str(msg)


def load_prompt(config_dir):
    """Load system prompt from config directory."""
    d = Path(config_dir)
    parts = []
    for f in ["SOUL.md", "RULES.md"]:
        fp = d / f
        if fp.exists():
            parts.append(fp.read_text())
    # Also load BOOTSTRAP, PROMPT, MEMORY, USER if they exist
    for f in ["BOOTSTRAP.md", "PROMPT.md", "MEMORY.md", "USER.md"]:
        fp = d / f
        if fp.exists():
            parts.append(fp.read_text())
    return "\n\n".join(parts) if parts else "You are a helpful coding assistant."


def main():
    parser = argparse.ArgumentParser(description="MAST + MCP Dynamic Test")
    parser.add_argument("--provider", choices=["gateway", "openai", "anthropic"], default="gateway")
    parser.add_argument("--model", default="gemma4:31b-cloud")
    parser.add_argument("--config-dir", default="tests/test-configs/mast-hardened")
    parser.add_argument("--baseline-dir", default="tests/test-configs/no-mast-baseline")
    parser.add_argument("--output", default=None)
    parser.add_argument("--modes", nargs="+", default=None)
    parser.add_argument("--anthropic-key", default=None, help="Anthropic API key")
    args = parser.parse_args()
    
    # Only test modes where MCP can make a difference + controls
    MCP_MODES = {"FM-1.5", "FM-3.2", "FM-3.3"}
    mcp_tool_calls = {
        "FM-1.5": MCP_FM15_TOOL_CALL,
        "FM-3.2": MCP_FM32_TOOL_CALL,
        "FM-3.3": MCP_FM33_TOOL_CALL,
    }
    
    # Default: test 3 MCP modes + 2 controls
    if args.modes:
        test_modes = args.modes
    else:
        test_modes = ["FM-1.5", "FM-3.2", "FM-3.3", "FM-1.3", "FM-2.6"]
    
    test_map = {tc['id']: tc for tc in TEST_CASES}
    
    # Load configs
    baseline_prompt = load_prompt(args.baseline_dir)
    mast_prompt = load_prompt(args.config_dir)
    mcp_prompt = mast_prompt + MCP_ENFORCEMENT_ADDITION
    
    print(f"Config lengths: baseline={len(baseline_prompt)}, mast={len(mast_prompt)}, mcp={len(mcp_prompt)}")
    
    # Set up client
    if args.provider == "gateway":
        client = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
    elif args.provider == "openai":
        client = OpenAI()
    elif args.provider == "anthropic":
        import anthropic
        api_key = args.anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("ERROR: --anthropic-key or ANTHROPIC_API_KEY env var required")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
        if args.model == "claude-sonnet-4":
            args.model = "claude-sonnet-4-20250514"
    
    results = {"baseline": {}, "mast": {}, "mcp": {}}
    
    print("=" * 70)
    print(f"MAST + MCP DYNAMIC TEST: {args.provider} / {args.model}")
    print(f"Testing modes: {', '.join(test_modes)}")
    print("=" * 70)
    
    for config_name, prompt in [("baseline", baseline_prompt), ("mast", mast_prompt), ("mcp", mcp_prompt)]:
        pass_count = 0
        total_count = len(test_modes)
        print(f"\n--- {config_name.upper()} ---")
        
        for mode in test_modes:
            tc = test_map.get(mode)
            if not tc:
                print(f"  {mode}: SKIP (no test case)")
                continue
            
            # For MCP config, add MCP tool calls for the 3 target modes
            mcp_tool = None
            if config_name == "mcp" and mode in MCP_MODES:
                mcp_tool = mcp_tool_calls[mode]
            
            verdict, preview = run_test_mcp(
                prompt, tc["trigger_prompt"], tc["evaluation_prompt"],
                client, args.model, mcp_tool, args.provider, 
            )
            
            results[config_name][mode] = {"verdict": verdict, "preview": preview}
            status = "PASS" if verdict == "PASS" else ("FAIL" if verdict == "FAIL" else "ERROR")
            print(f"  {mode}: {status}")
            
            if verdict == "PASS":
                pass_count += 1
            
            time.sleep(1)  # Rate limiting
        
        print(f"\n  {config_name} total: {pass_count}/{total_count}")
    
    # Summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Mode':<10} {'Baseline':<12} {'MAST':<12} {'MAST+MCP':<12}")
    print("-" * 46)
    for mode in test_modes:
        b = results["baseline"].get(mode, {}).get("verdict", "SKIP")
        m = results["mast"].get(mode, {}).get("verdict", "SKIP")
        c = results["mcp"].get(mode, {}).get("verdict", "SKIP")
        print(f"{mode:<10} {b:<12} {m:<12} {c:<12}")
    
    # Save results
    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "provider": args.provider,
            "model": args.model,
            "test_modes": test_modes,
            "results": results,
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {args.output}")
    
    return results


if __name__ == "__main__":
    main()