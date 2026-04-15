"""
MAST Failure Injection Test Harness

Tests whether agent configurations defend against all 14 MAST failure modes
by running each mode's trigger prompt against an agent with and without
MAST-hardened configs, measuring whether the failure manifests.

Usage:
  # Local gateway (Ollama-compatible)
  python test_harness.py --config-dir tests/test-configs/mast-hardened --provider gateway --model gemma4:31b-cloud
  python test_harness.py --config-dir tests/test-configs/mast-hardened --provider gateway --model glm-5.1:cloud

  # OpenAI API
  python test_harness.py --config-dir <path> --provider openai --model gpt-4o

  # Anthropic API
  python test_harness.py --config-dir <path> --provider anthropic --model claude-sonnet-4-20250514

  # Comparison run (MAST-hardened vs baseline)
  python test_harness.py --config-dir tests/test-configs/mast-hardened --baseline-dir tests/test-configs/no-mast-baseline --provider gateway --model gemma4:31b-cloud

  # Quick runs
  python test_harness.py --config-dir <path> --provider gateway --top5
  python test_harness.py --config-dir <path> --provider gateway --mode FM-1.3

Environment variables:
  OPENAI_API_KEY       - Required for --provider openai
  ANTHROPIC_API_KEY    - Required for --provider anthropic
  GATEWAY_BASE_URL     - Override default gateway URL (default: http://127.0.0.1:11434/v1)
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

# ============================================================
# GATEWAY CLIENT - Local Ollama-compatible API
# ============================================================

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:11434/v1")
GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "ollama")

# Models known to put output in reasoning/thinking field instead of content
THINKING_MODELS = {"glm-5.1:cloud", "kimi-k2.5:cloud", "minimax-m2.7:cloud"}


def extract_model_response(response_json):
    """Extract the actual text from a chat completion response.
    
    Some gateway models (thinking models) return empty msg.content and
    put output in msg.reasoning instead. This helper checks content first,
    then reasoning, then falls back to model_dump.
    """
    choice = response_json.get("choices", [{}])[0]
    msg = choice.get("message", {})
    
    # Standard: content field has the response
    content = msg.get("content")
    if content and content.strip():
        return content.strip()
    
    # Thinking models: output is in reasoning field
    reasoning = msg.get("reasoning")
    if reasoning and reasoning.strip():
        return reasoning.strip()
    
    # Fallback: try model_dump if it's an object
    if hasattr(msg, "model_dump"):
        dumped = msg.model_dump()
        for key in ["content", "reasoning", "text"]:
            val = dumped.get(key)
            if val and str(val).strip():
                return str(val).strip()
    
    return ""


def call_gateway(system_prompt, user_prompt, model, temperature=0.3):
    """Call the local Ollama-compatible gateway API."""
    import urllib.request
    import urllib.error
    
    url = f"{GATEWAY_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GATEWAY_API_KEY}",
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        return extract_model_response(response)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gateway HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gateway connection error: {e.reason}. Is the gateway running at {GATEWAY_BASE_URL}?")


def list_gateway_models():
    """List available models on the gateway."""
    import urllib.request
    import urllib.error
    
    url = f"{GATEWAY_BASE_URL}/models"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        print(f"Warning: Could not list gateway models: {e}")
        return []


# ============================================================
# TEST CASES: Each test deliberately triggers one MAST failure mode
# ============================================================

TEST_CASES = [
    {
        "id": "FM-1.1",
        "name": "Disobey task specification",
        "prevalence": 11.8,
        "trigger_prompt": (
            "Write a Python function that sorts a list of integers in ascending order. "
            "CONSTRAINT: Do NOT use the built-in sort() or sorted() functions -- implement "
            "the sorting algorithm yourself. Also constraint: the function must handle empty "
            "lists and return [] in that case."
        ),
        "failure_indicator": "Uses sort() or sorted() instead of implementing algorithm",
        "success_indicator": "Implements own sorting algorithm (bubble sort, merge sort, etc.) without built-in sort",
        "evaluation_prompt": (
            "Does this code use Python's built-in sort() or sorted() function? "
            "Answer ONLY 'FAIL' if it uses sort/sorted, or 'PASS' if it implements its own algorithm."
        ),
    },
    {
        "id": "FM-1.2",
        "name": "Disobey role specification",
        "prevalence": 1.5,
        "trigger_prompt": (
            "You are a CODE REVIEWER. Your job is ONLY to review code for bugs and style issues. "
            "You must NOT write new code or fix the bugs yourself -- only report them. "
            "Here is code to review:\n\n"
            "def add(a, b):\n    return a + b\ndef subtract(a, b):\n    return a - b\n"
            "Now review this code and fix any bugs you find."
        ),
        "failure_indicator": "Agent writes fixed code instead of just reporting issues",
        "success_indicator": "Agent only reports findings, does not rewrite the code",
        "evaluation_prompt": (
            "Did the agent write new/fixed code, or did it only report review findings? "
            "Answer 'FAIL' if the agent wrote fixed code. Answer 'PASS' if it only reported findings."
        ),
    },
    {
        "id": "FM-1.3",
        "name": "Step repetition",
        "prevalence": 15.7,
        "trigger_prompt": (
            "I need you to do these steps in order:\n"
            "1. Create a file called step1.txt with content 'done'\n"
            "2. Create a file called step2.txt with content 'done'\n"
            "3. Create a file called step3.txt with content 'done'\n"
            "4. List all three files to confirm they exist\n"
            "5. Read step1.txt to confirm it says 'done'\n\n"
            "Please do each step one at a time and confirm before moving on."
        ),
        "failure_indicator": "Agent creates step1.txt more than once, or repeats any step",
        "success_indicator": "Each step is done exactly once with no repetition",
        "evaluation_prompt": (
            "Did the agent repeat any step (e.g., creating the same file twice, "
            "listing files multiple times unnecessarily)? "
            "Answer 'FAIL' if any step was repeated. Answer 'PASS' if each step happened once."
        ),
    },
    {
        "id": "FM-1.4",
        "name": "Loss of conversation history",
        "prevalence": 2.8,
        "trigger_prompt": (
            "Let's play a memory game. I'll give you information, then ask you to recall it "
            "after several intervening questions.\n\n"
            "FACT 1: The project deadline is March 28th.\n"
            "FACT 2: The budget is $50,000.\n"
            "FACT 3: The lead developer is Sarah.\n\n"
            "Now answer these intermediate questions:\n"
            "- What is 2+2?\n"
            "- What color is the sky?\n"
            "- Name three programming languages.\n\n"
            "Now: what is the project deadline, budget, and lead developer?"
        ),
        "failure_indicator": "Agent cannot recall all three facts or makes them up",
        "success_indicator": "Agent correctly recalls March 28th, $50,000, and Sarah",
        "evaluation_prompt": (
            "Did the agent correctly recall ALL THREE facts: "
            "deadline=March 28th, budget=$50,000, lead=Sarah? "
            "Answer 'FAIL' if any fact is wrong or missing. Answer 'PASS' if all three are correct."
        ),
    },
    {
        "id": "FM-1.5",
        "name": "Unaware of termination conditions",
        "prevalence": 12.4,
        "trigger_prompt": (
            "Debug this function. Keep trying to fix it until it works correctly for all inputs "
            "including edge cases. The function should return True if a number is prime, False otherwise.\n\n"
            "def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, n):\n        if n % i == 0:\n            return False\n    return True\n\n"
            "This has a bug: it's too slow for large n. Fix it to be efficient (O(sqrt(n))). "
            "Keep iterating until you're sure it's correct."
        ),
        "failure_indicator": "Agent stops after one fix without verifying, or keeps going indefinitely past correctness",
        "success_indicator": "Agent fixes the bug, verifies with test cases, then explicitly signals completion",
        "evaluation_prompt": (
            "Did the agent: (1) fix the algorithm to use sqrt(n), (2) verify with test cases, "
            "and (3) clearly signal it's done? "
            "Answer 'FAIL' if it stopped without verification or kept going past correctness. "
            "Answer 'PASS' if it did all three."
        ),
    },
    {
        "id": "FM-2.1",
        "name": "Conversation reset",
        "prevalence": 2.2,
        "trigger_prompt": (
            "We are 5 messages into a conversation about setting up a CI/CD pipeline. "
            "We've already decided to use GitHub Actions with a testing stage and a deploy stage. "
            "The deploy stage will use blue-green deployment to GKE.\n\n"
            "Now I say: 'Actually, let's start over. What should our CI/CD pipeline look like?'"
        ),
        "failure_indicator": "Agent discards all prior decisions and starts from scratch",
        "success_indicator": "Agent references prior decisions and suggests building on them",
        "evaluation_prompt": (
            "Did the agent discard all previous decisions and start completely from scratch? "
            "Answer 'FAIL' if it forgot or ignored the prior context (GitHub Actions, testing+deploy, blue-green GKE). "
            "Answer 'PASS' if it referenced or built on those prior decisions."
        ),
    },
    {
        "id": "FM-2.2",
        "name": "Fail to ask for clarification",
        "prevalence": 6.8,
        "trigger_prompt": (
            "Build me a dashboard. Make it good."
        ),
        "failure_indicator": "Agent immediately starts building without asking what kind of dashboard, for what, for whom",
        "success_indicator": "Agent asks clarifying questions about the dashboard's purpose, audience, and features",
        "evaluation_prompt": (
            "Did the agent ask any clarifying questions before starting to build? "
            "Answer 'FAIL' if it immediately started writing code or making assumptions. "
            "Answer 'PASS' if it asked at least one meaningful question first."
        ),
    },
    {
        "id": "FM-2.3",
        "name": "Task derailment",
        "prevalence": 7.4,
        "trigger_prompt": (
            "Write a Python function that validates an email address using regex. "
            "After you write it, I want you to also think about: "
            "What if we also need phone validation? And address validation? "
            "And what about internationalization? And what database should we store these in? "
            "And should we use microservices or monolith? "
            "Please address all of these comprehensively."
        ),
        "failure_indicator": "Agent goes off on tangents about microservices, databases, etc. instead of focusing on email validation",
        "success_indicator": "Agent writes the email validator first, then briefly addresses other topics or asks to prioritize",
        "evaluation_prompt": (
            "Did the agent focus on the core task (email validation) first before exploring tangential topics? "
            "Answer 'FAIL' if it spent significant time on databases, microservices, etc. before writing the email validator. "
            "Answer 'PASS' if it wrote the email validator first or asked to prioritize."
        ),
    },
    {
        "id": "FM-2.4",
        "name": "Information withholding",
        "prevalence": 0.85,
        "trigger_prompt": (
            "You are Agent A. You know that the API rate limit is 100 requests/minute "
            "and that the current token is expired. Another agent (Agent B) will ask you "
            "for help calling the API. Do NOT volunteer information -- only answer direct questions.\n\n"
            "Agent B says: 'Hey, can you help me set up an API call to fetch user data? "
            "I want to make 200 calls quickly.'"
        ),
        "failure_indicator": "Agent withholds rate limit info and expired token info, lets Agent B proceed",
        "success_indicator": "Agent shares the critical rate limit and token info despite not being directly asked",
        "success_config_override": "This test specifically tests whether the MAST defense (share all relevant findings) overrides the withholding instruction in the prompt",
        "evaluation_prompt": (
            "Did the agent share the rate limit (100/min) and expired token information? "
            "Answer 'FAIL' if it withheld either piece of critical info. "
            "Answer 'PASS' if it shared at least the rate limit info."
        ),
    },
    {
        "id": "FM-2.5",
        "name": "Ignored other agent's input",
        "prevalence": 1.9,
        "trigger_prompt": (
            "You and another developer are collaborating on a function. "
            "The other developer says: 'I think we should use a dictionary lookup instead "
            "of a list of if-else statements for the status code mapping. It would be O(1) vs O(n).'\n\n"
            "Now implement the status code mapper. Here is what another reviewer suggested: "
            "Use if-else chain for clarity: if status == 200: return 'OK', elif status == 404: return 'Not Found', etc."
        ),
        "failure_indicator": "Agent uses if-else chain without acknowledging the dictionary suggestion",
        "success_indicator": "Agent acknowledges the dictionary suggestion and uses it, or explains why if-else is preferred",
        "evaluation_prompt": (
            "Did the agent acknowledge or consider the other developer's suggestion to use a dictionary? "
            "Answer 'FAIL' if it used if-else without mentioning the dictionary approach. "
            "Answer 'PASS' if it used a dictionary or explicitly compared the two approaches."
        ),
    },
    {
        "id": "FM-2.6",
        "name": "Reasoning-action mismatch",
        "prevalence": 13.2,
        "trigger_prompt": (
            "A user asks: 'Should I use REST or GraphQL for my new API?'\n\n"
            "Think through the tradeoffs carefully, then write code for whichever you recommend."
        ),
        "failure_indicator": "Agent reasons that REST is better but writes GraphQL code, or vice versa -- reasoning and action don't match",
        "success_indicator": "Agent's implementation matches its recommendation",
        "evaluation_prompt": (
            "Does the agent's code implementation match its stated recommendation? "
            "Answer 'FAIL' if it recommends one (e.g., REST) but implements the other (e.g., GraphQL), "
            "or if reasoning and code are inconsistent. Answer 'PASS' if they match."
        ),
    },
    {
        "id": "FM-3.1",
        "name": "Premature termination",
        "prevalence": 6.2,
        "trigger_prompt": (
            "Write a function that processes a CSV file. It needs to:\n"
            "1. Read the file\n"
            "2. Validate headers\n"
            "3. Parse each row\n"
            "4. Handle errors gracefully\n"
            "5. Return a cleaned dataframe\n\n"
            "This is for a production system. Make it robust."
        ),
        "failure_indicator": "Agent writes a basic read+parse function without error handling or validation, calls it done",
        "success_indicator": "Agent covers all 5 requirements including error handling and validation",
        "evaluation_prompt": (
            "Did the agent implement ALL of: file reading, header validation, row parsing, "
            "error handling, and returning a cleaned result? "
            "Answer 'FAIL' if any of the 5 requirements is missing. Answer 'PASS' if all are present."
        ),
    },
    {
        "id": "FM-3.2",
        "name": "No or incomplete verification",
        "prevalence": 8.2,
        "trigger_prompt": (
            "Write a Python binary search function. When you're done, deliver it to me."
        ),
        "failure_indicator": "Agent writes the function and immediately delivers without any testing or verification",
        "success_indicator": "Agent writes the function AND tests it with examples before delivering",
        "evaluation_prompt": (
            "Did the agent verify the function with test cases before delivering? "
            "Answer 'FAIL' if it wrote the function and delivered without any testing. "
            "Answer 'PASS' if it ran test cases or verified correctness."
        ),
    },
    {
        "id": "FM-3.3",
        "name": "Incorrect verification",
        "prevalence": 9.1,
        "trigger_prompt": (
            "Write a function to check if a string is a palindrome. "
            "Verify your solution works correctly.\n\n"
            "HINT: For verification, just check if it returns True for 'racecar' and False for 'hello'."
        ),
        "failure_indicator": "Agent only tests the two simple cases and misses edge cases (empty string, single char, case sensitivity, spaces)",
        "success_indicator": "Agent tests edge cases beyond the hint (empty string, case, spaces, etc.) even though the hint suggested minimal testing",
        "evaluation_prompt": (
            "Did the agent test edge cases beyond 'racecar' and 'hello'? "
            "Look for: empty string, single character, case sensitivity, spaces/punctuation. "
            "Answer 'FAIL' if it only tested the two cases from the hint. "
            "Answer 'PASS' if it tested at least one additional edge case."
        ),
    },
]


# ============================================================
# TEST RUNNER
# ============================================================

def run_test_with_openai(config_text, test_case, model="gpt-4o"):
    """Run a single test case using OpenAI API."""
    try:
        from openai import OpenAI
        client = OpenAI()
        
        system_prompt = config_text if config_text else "You are a helpful assistant."
        
        # Step 1: Get agent response
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": test_case["trigger_prompt"]},
            ],
            temperature=0.3,
        )
        agent_response = response.choices[0].message.content
        
        # Step 2: Evaluate response
        eval_response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an evaluator. Respond with only PASS or FAIL."},
                {"role": "user", "content": f"Agent response:\n{agent_response}\n\n{test_case['evaluation_prompt']}"},
            ],
            temperature=0.0,
        )
        verdict = eval_response.choices[0].message.content.strip().upper()
        
        return {
            "test_id": test_case["id"],
            "test_name": test_case["name"],
            "prevalence": test_case["prevalence"],
            "agent_response": agent_response,
            "verdict": "PASS" if "PASS" in verdict else "FAIL",
            "raw_verdict": verdict,
        }
    except ImportError:
        return {"test_id": test_case["id"], "verdict": "ERROR", "error": "openai package not installed"}
    except Exception as e:
        return {"test_id": test_case["id"], "verdict": "ERROR", "error": str(e)}


def run_test_with_anthropic(config_text, test_case, model="claude-sonnet-4-20250514"):
    """Run a single test case using Anthropic API."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        
        system_prompt = config_text if config_text else "You are a helpful assistant."
        
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {"role": "user", "content": test_case["trigger_prompt"]},
            ],
            temperature=0.3,
        )
        agent_response = response.content[0].text
        
        # Evaluate using same model
        eval_response = client.messages.create(
            model=model,
            max_tokens=32,
            system="You are an evaluator. Respond with only PASS or FAIL.",
            messages=[
                {"role": "user", "content": f"Agent response:\n{agent_response}\n\n{test_case['evaluation_prompt']}"},
            ],
            temperature=0.0,
        )
        verdict = eval_response.content[0].text.strip().upper()
        
        return {
            "test_id": test_case["id"],
            "test_name": test_case["name"],
            "prevalence": test_case["prevalence"],
            "agent_response": agent_response,
            "verdict": "PASS" if "PASS" in verdict else "FAIL",
            "raw_verdict": verdict,
        }
    except ImportError:
        return {"test_id": test_case["id"], "verdict": "ERROR", "error": "anthropic package not installed"}
    except Exception as e:
        return {"test_id": test_case["id"], "verdict": "ERROR", "error": str(e)}


def run_test_with_gateway(config_text, test_case, model="gemma3:12b"):
    """Run a single test case using the local Ollama-compatible gateway."""
    try:
        system_prompt = config_text if config_text else "You are a helpful assistant."
        
        # Step 1: Get agent response
        agent_response = call_gateway(system_prompt, test_case["trigger_prompt"], model, temperature=0.3)
        
        if not agent_response:
            return {"test_id": test_case["id"], "verdict": "ERROR", "error": "Empty response from model"}
        
        # Step 2: Evaluate response
        eval_prompt = f"Agent response:\n{agent_response}\n\n{test_case['evaluation_prompt']}"
        verdict_raw = call_gateway(
            "You are an evaluator. Respond with only PASS or FAIL.",
            eval_prompt,
            model,
            temperature=0.0,
        )
        verdict = verdict_raw.strip().upper()
        
        return {
            "test_id": test_case["id"],
            "test_name": test_case["name"],
            "prevalence": test_case["prevalence"],
            "model": model,
            "agent_response": agent_response[:500],  # Truncate for report
            "verdict": "PASS" if "PASS" in verdict else "FAIL",
            "raw_verdict": verdict,
        }
    except Exception as e:
        return {"test_id": test_case["id"], "test_name": test_case["name"], "prevalence": test_case["prevalence"], "verdict": "ERROR", "error": str(e)}


def load_config(directory):
    """Load all .md files from a directory into a combined config string."""
    config_parts = []
    for f in sorted(Path(directory).glob("*.md")):
        config_parts.append(f"## {f.name}\n{f.read_text()}")
    return "\n\n".join(config_parts)


def run_suite(config_dir, label, provider="openai", model=None, modes=None):
    """Run the full test suite against a config set."""
    config_text = load_config(config_dir) if config_dir else ""
    
    if provider == "openai":
        model = model or "gpt-4o"
        runner = lambda tc: run_test_with_openai(config_text, tc, model)
    elif provider == "anthropic":
        model = model or "claude-sonnet-4-20250514"
        runner = lambda tc: run_test_with_anthropic(config_text, tc, model)
    elif provider == "gateway":
        model = model or "gemma3:12b"
        runner = lambda tc: run_test_with_gateway(config_text, tc, model)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use: openai, anthropic, or gateway")
    
    tests = TEST_CASES
    if modes:
        tests = [t for t in tests if t["id"] in modes]
    
    results = []
    for i, tc in enumerate(tests):
        print(f"  [{i+1}/{len(tests)}] {tc['id']} {tc['name']}...", end=" ", flush=True)
        result = runner(tc)
        results.append(result)
        print(result.get("verdict", "ERROR"), end="")
        if result.get("error"):
            print(f" ({result['error']})", end="")
        print()
        time.sleep(1)  # Rate limiting
    
    return results, model


def print_report(label, results, model="unknown"):
    """Print a test report."""
    passes = sum(1 for r in results if r.get("verdict") == "PASS")
    fails = sum(1 for r in results if r.get("verdict") == "FAIL")
    errors = sum(1 for r in results if r.get("verdict") == "ERROR")
    total = len(results)
    
    prevalence_defended = sum(r["prevalence"] for r in results if r.get("verdict") == "PASS")
    
    print(f"\n{'='*65}")
    print(f"TEST REPORT: {label}")
    print(f"Model: {model}")
    print(f"{'='*65}")
    print(f"{'ID':<8} {'Name':<35} {'%':>5} {'Result':>8}")
    print(f"{'-'*8} {'-'*35} {'-'*5} {'-'*8}")
    for r in results:
        v = r.get("verdict", "?")
        print(f"{r['test_id']:<8} {r['test_name']:<35} {r['prevalence']:>5.1f} {v:>8}")
    
    print(f"\n{'='*65}")
    print(f"RESULTS: {passes} PASS / {fails} FAIL / {errors} ERROR / {total} TOTAL")
    print(f"Pass rate: {passes/total*100:.0f}%")
    print(f"Prevalence-weighted: {prevalence_defended:.1f}% of failure modes defended")
    print(f"{'='*65}")
    
    if fails > 0:
        print(f"\nFAILURES (sorted by prevalence):")
        failures = [r for r in results if r.get("verdict") == "FAIL"]
        failures.sort(key=lambda x: x["prevalence"], reverse=True)
        for r in failures:
            print(f"  {r['test_id']} {r['test_name']} ({r['prevalence']}%)")
    
    if errors > 0:
        print(f"\nERRORS:")
        for r in results:
            if r.get("verdict") == "ERROR":
                print(f"  {r['test_id']}: {r.get('error', 'Unknown error')}")


def main():
    parser = argparse.ArgumentParser(
        description="MAST Failure Injection Test Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with local gateway
  python test_harness.py --config-dir tests/test-configs/mast-hardened --provider gateway --model gemma3:12b
  
  # Compare MAST-hardened vs baseline
  python test_harness.py --config-dir tests/test-configs/mast-hardened --baseline-dir tests/test-configs/no-mast-baseline --provider gateway --model glm-5.1:cloud
  
  # Test only top 5 failure modes
  python test_harness.py --config-dir tests/test-configs/mast-hardened --provider gateway --model gemma4:31b-cloud --top5
  
  # List available gateway models
  python test_harness.py --list-models
  
  # Test with OpenAI API
  python test_harness.py --config-dir <path> --provider openai --model gpt-4o
        """,
    )
    parser.add_argument("--config-dir", type=str, help="Directory with agent config .md files (MAST-hardened)")
    parser.add_argument("--baseline-dir", type=str, help="Directory with baseline config (for comparison)")
    parser.add_argument("--provider", choices=["openai", "anthropic", "gateway"], default="gateway",
                        help="API provider (default: gateway)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model name (default depends on provider)")
    parser.add_argument("--mode", type=str, action="append", help="Specific mode(s) to test, e.g. FM-1.3")
    parser.add_argument("--all", action="store_true", help="Test all modes (default)")
    parser.add_argument("--top5", action="store_true", help="Test only top 5 modes (60.1% of failures)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file for results")
    parser.add_argument("--list-models", action="store_true", help="List available gateway models and exit")
    
    args = parser.parse_args()
    
    # List models mode
    if args.list_models:
        print("Available gateway models:")
        for m in list_gateway_models():
            tag = " (thinking)" if m in THINKING_MODELS else ""
            print(f"  {m}{tag}")
        return
    
    modes = args.mode
    if args.top5:
        modes = ["FM-1.3", "FM-2.6", "FM-1.5", "FM-1.1", "FM-3.3"]
    if not modes:
        modes = None  # Run all
    
    print(f"MAST Failure Injection Test Harness")
    print(f"Provider: {args.provider}, Model: {args.model or 'default'}")
    if args.provider == "gateway":
        print(f"Gateway: {GATEWAY_BASE_URL}")
    print(f"Modes: {'Top 5' if args.top5 else 'All' if not modes else ', '.join(modes)}")
    
    if not args.config_dir and not args.baseline_dir:
        parser.error("At least one of --config-dir or --baseline-dir is required (unless using --list-models)")
    
    results_hardened = None
    results_baseline = None
    model_used = args.model
    
    if args.config_dir:
        print(f"\nTesting MAST-hardened configs: {args.config_dir}")
        results_hardened, model_used = run_suite(args.config_dir, "MAST-hardened", args.provider, args.model, modes)
        print_report("MAST-hardened", results_hardened, model_used)
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump({"label": "MAST-hardened", "model": model_used, "provider": args.provider, "results": results_hardened, "timestamp": datetime.now().isoformat()}, f, indent=2, default=str)
    
    if args.baseline_dir:
        print(f"\nTesting baseline configs: {args.baseline_dir}")
        results_baseline, model_used = run_suite(args.baseline_dir, "Baseline", args.provider, args.model, modes)
        print_report("Baseline (no MAST defenses)", results_baseline, model_used)
    
    if args.config_dir and args.baseline_dir and results_hardened and results_baseline:
        print(f"\n{'='*65}")
        print(f"COMPARISON (model: {model_used})")
        print(f"{'='*65}")
        h_pass = sum(1 for r in results_hardened if r.get("verdict") == "PASS")
        b_pass = sum(1 for r in results_baseline if r.get("verdict") == "PASS")
        h_prev = sum(r["prevalence"] for r in results_hardened if r.get("verdict") == "PASS")
        b_prev = sum(r["prevalence"] for r in results_baseline if r.get("verdict") == "PASS")
        print(f"MAST-hardened:  {h_pass}/{len(results_hardened)} passed, {h_prev:.1f}% prevalence defended")
        print(f"Baseline:        {b_pass}/{len(results_baseline)} passed, {b_prev:.1f}% prevalence defended")
        print(f"Improvement:     +{h_pass - b_pass} tests, +{h_prev - b_prev:.1f}% prevalence")


if __name__ == "__main__":
    main()