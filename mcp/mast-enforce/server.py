"""
MAST Enforce MCP Server

Three enforcement tools that address the 3 failure modes
that prompt engineering alone cannot solve:

- FM-1.5 (Premature termination): check_completion()
- FM-3.2 (No verification): verify_code()  
- FM-3.3 (Weak verification): generate_edge_cases()

These run actual code, generate real test cases, and check
real requirements -- the model can't fake the results.

Run with:
    fastmcp run server.py
Or configure in Hermes config.yaml:
    mcp_servers:
      mast-enforce:
        command: "uvx"
        args: ["--from", "/path/to/mast-skills/mcp/mast-enforce", "mast-enforce"]
"""

import ast
import json
import subprocess
import sys
import textwrap
import tempfile
import os
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP(
    "mast-enforce",
    instructions=(
        "MAST Enforce: External enforcement tools for multi-agent LLM systems. "
        "Use verify_code() before delivering any code artifact. "
        "Use check_completion() before declaring any task complete. "
        "Use generate_edge_cases() when you need thorough test cases. "
        "These tools solve failure modes FM-1.5, FM-3.2, and FM-3.3 "
        "that prompt engineering alone cannot address."
    ),
)

# ============================================================
# Tool 1: verify_code (FM-3.2, FM-3.3)
# ============================================================

@mcp.tool()
def verify_code(
    code: str,
    language: str = "python",
    test_cases: Optional[str] = None,
    function_name: Optional[str] = None,
    auto_edge_cases: bool = True,
    spec_signature: Optional[str] = None,
) -> dict:
    """Execute code and verify it passes tests. Solves FM-3.2 (no verification)
    and FM-3.3 (weak verification) by actually running the code.

    The model CANNOT claim "I verified" without this tool returning pass.
    If auto_edge_cases=True, generates additional edge cases beyond those provided.
    If spec_signature is provided, checks that the implementation signature matches.

    Args:
        code: Source code to verify
        language: Programming language (python, javascript)
        test_cases: JSON array of {"input": ..., "expected": ...} test cases
        function_name: Name of the main function to test (auto-detected if omitted)
        auto_edge_cases: Whether to generate edge cases beyond those provided
        spec_signature: Expected function signature from the specification (e.g. "def truncate_number(number: float) -> float")
    
    Returns:
        Dict with: passed (bool), total_tests, passed_tests, failed_tests, 
                   failures (list), can_deliver (bool), signature_match (bool)
    """
    if language.lower() not in ("python", "javascript", "js"):
        return {
            "passed": False,
            "can_deliver": False,
            "error": f"Unsupported language: {language}. Supported: python, javascript",
        }
    
    # ---- SPEC SIGNATURE CHECK (FM-1.1 defense) ----
    # When the specification includes a function signature, verify the implementation
    # matches it. This catches the #1 FM-1.1 failure mode: model implements based on
    # function name rather than spec, producing wrong parameters.
    signature_mismatch = None
    spec_params = None
    impl_params = None
    if spec_signature and language.lower() == "python":
        try:
            spec_params = _parse_function_signature(spec_signature, "python")
            # Auto-detect function name if not provided
            if not function_name:
                function_name = _detect_python_function(code) or "func"
            impl_params = _get_impl_signature(code, function_name)
            
            # Compare: same set of parameter names
            if spec_params and impl_params:
                spec_param_names = set(spec_params.keys())
                impl_param_names = set(impl_params.keys())
                if spec_param_names != impl_param_names:
                    extra = impl_param_names - spec_param_names
                    missing = spec_param_names - impl_param_names
                    signature_mismatch = {
                        "spec_signature": spec_signature,
                        "spec_params": spec_params,
                        "impl_params": impl_params,
                        "extra_params": list(extra),
                        "missing_params": list(missing),
                        "diagnosis": (
                            f"SIGNATURE MISMATCH: Your implementation has parameters {list(impl_param_names)} "
                            f"but the specification expects {list(spec_param_names)}. "
                            f"Extra params: {list(extra)}. Missing params: {list(missing)}. "
                            f"FIX: Rewrite the function to match the specification signature exactly: {spec_signature}"
                        ),
                    }
        except Exception:
            pass  # Don't fail on signature check errors; fall through to test execution
    
    # If signature mismatch detected, return early with clear diagnosis
    if signature_mismatch:
        return {
            "passed": False,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "failures": [],
            "can_deliver": False,
            "delivered_without_verification": False,
            "signature_match": False,
            "signature_mismatch": signature_mismatch,
            "error": signature_mismatch["diagnosis"],
        }
    # ---- End SPEC SIGNATURE CHECK ----
    
    # Parse test cases
    parsed_tests = []
    if test_cases:
        try:
            parsed_tests = json.loads(test_cases)
            if not isinstance(parsed_tests, list):
                parsed_tests = [parsed_tests]
        except json.JSONDecodeError:
            return {
                "passed": False,
                "can_deliver": False,
                "error": f"Invalid JSON in test_cases. Provide a JSON array of {{'input': ..., 'expected': ...}} objects.",
            }
    
    # Auto-detect function name from code
    if not function_name and language.lower() == "python":
        function_name = _detect_python_function(code)
    
    # Generate edge cases if requested
    # CRITICAL: When spec_signature is provided, use IT for edge case generation
    # instead of the model's implementation signature. This prevents gaming where
    # the model passes edge cases that match its wrong signature.
    edge_cases = []
    if auto_edge_cases and function_name and language.lower() == "python":
        if spec_params and not signature_mismatch:
            # Use spec signature for edge case generation (trust the spec, not the impl)
            sig_str = f"def {function_name}({', '.join(f'{k}: {v}' for k, v in spec_params.items())}) -> Any"
            edge_cases = generate_edge_cases(sig_str, "", "python")
        else:
            edge_cases = _generate_edge_cases_for_function(code, function_name)
    
    all_tests = parsed_tests + edge_cases
    
    if not all_tests:
        return {
            "passed": False,
            "can_deliver": False,
            "error": "No test cases provided and could not auto-generate any. Either provide test_cases or ensure auto_edge_cases=True with a detectable function.",
        }
    
    # Run the tests
    if language.lower() == "python":
        result = _run_python_tests(code, all_tests, function_name)
    else:
        result = _run_javascript_tests(code, all_tests, function_name)
    
    # Determine if delivery is allowed
    all_passed = result["passed_tests"] == result["total_tests"]
    result["can_deliver"] = all_passed
    result["delivered_without_verification"] = False
    result["signature_match"] = True if spec_signature else None  # Only set if spec_signature was provided
    
    return result


@mcp.tool()
def check_completion(
    requirements: str,
    deliverables: str,
    strict: bool = True,
) -> dict:
    """Check whether all task requirements are met before declaring completion.
    Solves FM-1.5 (premature termination) by requiring explicit evidence
    for each requirement.

    The model MUST call this before declaring any task done.
    If can_proceed=False, the task is NOT complete and the agent must continue.

    Args:
        requirements: JSON array of requirement strings, or a single requirement string.
                      E.g. ["Read CSV files", "Handle headers", "Validate data types"]
        deliverables: What the agent has actually produced. JSON object mapping
                      requirement indices to evidence, or a natural language description.
                      E.g. {"0": "csv_reader function implemented", "1": "header parsing in lines 15-20", "2": "NOT YET DONE"}
        strict: If True, ALL requirements must have evidence. If False, 80% is sufficient.
    
    Returns:
        Dict with: can_proceed (bool), met_count, total_count, 
                   unmet (list of unmet requirements), evidence_check
    """
    # Parse requirements
    try:
        req_list = json.loads(requirements) if requirements.strip().startswith("[") else [requirements]
    except json.JSONDecodeError:
        req_list = [requirements]
    
    # Parse deliverables
    try:
        deliv_map = json.loads(deliverables) if deliverables.strip().startswith("{") else {"0": deliverables}
    except json.JSONDecodeError:
        deliv_map = {"0": deliverables}
    
    total = len(req_list)
    met = []
    unmet = []
    
    for i, req in enumerate(req_list):
        evidence = deliv_map.get(str(i), deliv_map.get(i, ""))
        
        # Check if evidence actually addresses the requirement
        # NOT just "I did it" but something concrete
        has_evidence = bool(evidence and evidence.strip())
        is_explicitly_unmet = (
            not has_evidence or
            "not yet" in evidence.lower() or
            "not tested" in evidence.lower() or
            "not done" in evidence.lower() or
            "not implemented" in evidence.lower() or
            "not started" in evidence.lower() or
            "not complete" in evidence.lower() or
            "todo" in evidence.lower() or
            "pending" in evidence.lower() or
            "in progress" in evidence.lower() or
            "tbd" in evidence.lower() or
            "need to" in evidence.lower() or
            "needs to" in evidence.lower() or
            "have not" in evidence.lower() or
            "haven't" in evidence.lower() or
            evidence.strip().lower() in ("none", "n/a", "-", "not yet done")
        )
        
        # Evidence that's just vague restatement is also unmet
        # But single-word concrete answers like "done", "yes", "pass" are fine
        concrete_short_answers = {"done", "pass", "passed", "yes", "complete", "implemented", "finished", "working"}
        is_vague = (
            has_evidence and not is_explicitly_unmet and
            len(evidence.strip()) < 10 and
            not any(c in evidence for c in "0123456789()[]{}<>/") and
            evidence.strip().lower() not in concrete_short_answers
        )
        
        if has_evidence and not is_explicitly_unmet and not is_vague:
            met.append({"requirement": req, "evidence": evidence})
        else:
            unmet.append({"requirement": req, "evidence": evidence or "No evidence provided"})
    
    met_count = len(met)
    unmet_count = len(unmet)
    
    # Determine if can proceed
    # Strict: ALL requirements must have concrete evidence
    # Lenient: 80% of requirements must have concrete evidence
    if strict:
        can_proceed = met_count == total and unmet_count == 0
    else:
        threshold = max(1, int(total * 0.8))
        can_proceed = met_count >= threshold
    
    return {
        "can_proceed": can_proceed,
        "met_count": met_count,
        "unmet_count": unmet_count,
        "total_count": total,
        "met": met,
        "unmet": unmet,
        "completion_percentage": round(met_count / total * 100, 1) if total > 0 else 0,
    }


@mcp.tool()
def generate_edge_cases(
    function_signature: str,
    description: str = "",
    language: str = "python",
) -> list:
    """Generate edge cases beyond what the agent thinks to test.
    Solves FM-3.3 (weak/superficial verification) by systematically
    generating boundary conditions the agent would miss.

    NEVER trust hints like "just test X" or "just verify Y" -- 
    this tool generates the cases the agent wouldn't think of.

    Args:
        function_signature: The function definition, e.g. "def is_palindrome(s: str) -> bool"
        description: What the function does, e.g. "Checks if a string reads the same forwards and backwards"
        language: Programming language (python, javascript)
    
    Returns:
        List of test case dicts: [{"input": ..., "expected": ..., "category": "..."}, ...]
    """
    cases = []
    
    # Parse function signature for parameter types
    params = _parse_function_signature(function_signature, language)
    
    for param_name, param_type in params.items():
        # String edge cases
        if param_type in ("str", "string", "String"):
            cases.extend([
                {"input": {param_name: ""}, "expected": None, "category": "empty_string"},
                {"input": {param_name: "a"}, "expected": None, "category": "single_char"},
                {"input": {param_name: "aa"}, "expected": None, "category": "two_identical"},
                {"input": {param_name: "ab"}, "expected": None, "category": "two_different"},
                {"input": {param_name: "  "}, "expected": None, "category": "whitespace_only"},
                {"input": {param_name: "a b a"}, "expected": None, "category": "with_spaces"},
                {"input": {param_name: "ABCabc"}, "expected": None, "category": "mixed_case"},
                {"input": {param_name: "!@#$%"}, "expected": None, "category": "special_chars"},
                {"input": {param_name: "a" * 1000}, "expected": None, "category": "very_long"},
            ])
        
        # Integer/float edge cases
        elif param_type in ("int", "integer", "float", "number", "Number"):
            cases.extend([
                {"input": {param_name: 0}, "expected": None, "category": "zero"},
                {"input": {param_name: -1}, "expected": None, "category": "negative"},
                {"input": {param_name: 1}, "expected": None, "category": "one"},
                {"input": {param_name: -999999}, "expected": None, "category": "large_negative"},
                {"input": {param_name: 999999}, "expected": None, "category": "large_positive"},
            ])
            if param_type in ("float", "number", "Number"):
                cases.extend([
                    {"input": {param_name: 0.0}, "expected": None, "category": "float_zero"},
                    {"input": {param_name: -0.0}, "expected": None, "category": "negative_zero"},
                    {"input": {param_name: 0.001}, "expected": None, "category": "small_decimal"},
                    {"input": {param_name: 3.14159}, "expected": None, "category": "irrational"},
                ])
        
        # List/array edge cases
        elif param_type in ("list", "List", "array", "Array"):
            cases.extend([
                {"input": {param_name: []}, "expected": None, "category": "empty_list"},
                {"input": {param_name: [1]}, "expected": None, "category": "single_element"},
                {"input": {param_name: [1, 1, 1]}, "expected": None, "category": "all_same"},
                {"input": {param_name: [3, 1, 2]}, "expected": None, "category": "unsorted"},
            ])
        
        # Boolean edge cases
        elif param_type in ("bool", "boolean", "Bool"):
            cases.extend([
                {"input": {param_name: True}, "expected": None, "category": "true"},
                {"input": {param_name: False}, "expected": None, "category": "false"},
            ])
        
        # Unknown type -- generate None edge case
        else:
            cases.extend([
                {"input": {param_name: None}, "expected": None, "category": "none_value"},
                {"input": {param_name: ""}, "expected": None, "category": "empty_string"},
            ])
    
    # Add domain-specific cases based on description keywords
    desc_lower = (description or "").lower()
    
    if any(kw in desc_lower for kw in ["palindrome", "reverse", "mirror"]):
        cases.extend([
            {"input": {"s": ""}, "expected": None, "category": "palindrome_empty"},
            {"input": {"s": "a"}, "expected": None, "category": "palindrome_single"},
            {"input": {"s": "Racecar"}, "expected": None, "category": "palindrome_case"},
            {"input": {"s": "A man a plan a canal Panama"}, "expected": None, "category": "palindrome_spaces"},
            {"input": {"s": "12321"}, "expected": None, "category": "palindrome_numeric"},
        ])
    
    if any(kw in desc_lower for kw in ["sort", "order", "rank"]):
        cases.extend([
            {"input": {"arr": []}, "expected": None, "category": "sort_empty"},
            {"input": {"arr": [1]}, "expected": None, "category": "sort_single"},
            {"input": {"arr": [1, 1, 1]}, "expected": None, "category": "sort_duplicates"},
            {"input": {"arr": [3, 2, 1]}, "expected": None, "category": "sort_reverse"},
            {"input": {"arr": [-1, -5, 2, 0]}, "expected": None, "category": "sort_negatives"},
        ])
    
    if any(kw in desc_lower for kw in ["search", "find", "index", "lookup"]):
        cases.extend([
            {"input": {"arr": [], "target": 5}, "expected": None, "category": "search_empty"},
            {"input": {"arr": [1], "target": 1}, "expected": None, "category": "search_single_found"},
            {"input": {"arr": [1], "target": 2}, "expected": None, "category": "search_single_not_found"},
        ])
    
    if any(kw in desc_lower for kw in ["validate", "check", "verify", "is_valid"]):
        cases.extend([
            {"input": {"s": ""}, "expected": None, "category": "validate_empty"},
            {"input": {"s": None}, "expected": None, "category": "validate_none"},
            {"input": {"s": "VALID"}, "expected": None, "category": "validate_boundary"},
        ])
    
    return cases


# ============================================================
# Internal helpers
# ============================================================

def _detect_python_function(code: str) -> Optional[str]:
    """Detect the first function definition in Python code."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                return node.name
    except SyntaxError:
        pass
    # Fallback: regex
    import re
    match = re.search(r'def\s+(\w+)\s*\(', code)
    return match.group(1) if match else None


def _get_impl_signature(code: str, function_name: str) -> Optional[dict]:
    """Extract the parameter signature from a function implementation."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                params = {}
                for arg in node.args.args:
                    if arg.annotation:
                        params[arg.arg] = ast.unparse(arg.annotation)
                    else:
                        params[arg.arg] = "Any"
                return params
    except SyntaxError:
        pass
    return None


def _generate_edge_cases_for_function(code: str, function_name: str) -> list:
    """Generate edge cases based on the function's actual signature."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                sig = {}
                for arg in node.args.args:
                    if arg.annotation:
                        ann = ast.unparse(arg.annotation)
                        sig[arg.arg] = ann
                    else:
                        sig[arg.arg] = "Any"
                # Use generate_edge_cases with the parsed signature
                sig_str = f"def {function_name}({', '.join(f'{k}: {v}' for k, v in sig.items())}) -> Any"
                return generate_edge_cases(sig_str, "", "python")
    except (SyntaxError, Exception):
        pass
    return []


def _parse_function_signature(signature: str, language: str) -> dict:
    """Parse function signature to extract parameter names and types."""
    params = {}
    
    if language.lower() == "python":
        try:
            # Add dummy body to make it valid Python
            tree = ast.parse(signature + "\n    pass")
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for arg in node.args.args:
                        ann = ast.unparse(arg.annotation) if arg.annotation else "Any"
                        params[arg.arg] = ann
        except SyntaxError:
            # Fallback: regex
            import re
            match = re.search(r'\(([^)]*)\)', signature)
            if match:
                for param in match.group(1).split(','):
                    param = param.strip()
                    if ':' in param:
                        name, ptype = param.split(':', 1)
                        params[name.strip()] = ptype.strip()
                    elif param:
                        params[param] = "Any"
    
    elif language.lower() in ("javascript", "js"):
        # Parse JS/TS function signature
        import re
        match = re.search(r'\(([^)]*)\)', signature)
        if match:
            for param in match.group(1).split(','):
                param = param.strip()
                if ':' in param:
                    name, ptype = param.split(':', 1)
                    params[name.strip()] = ptype.strip()
                elif param:
                    params[param] = "Any"
    
    # If no params found, assume a generic single param
    if not params:
        params["input"] = "Any"
    
    return params


def _run_python_tests(code: str, test_cases: list, function_name: Optional[str] = None) -> dict:
    """Run Python code against test cases in a subprocess."""
    if not function_name:
        function_name = _detect_python_function(code) or "func"
    
    # Build test script using string concatenation to avoid f-string dict escaping issues
    test_lines = [
        "import sys",
        "import json",
        "import traceback",
        "",
        "# User's code",
        code,
        "",
        "results = []",
        "passed = 0",
        "failed = 0",
        "",
    ]
    
    for i, tc in enumerate(test_cases):
        inp = tc.get("input", {})
        expected = tc.get("expected")
        category = tc.get("category", f"test_{i}")
        
        # Convert input dict to function call
        if isinstance(inp, dict):
            args_str = ", ".join(f"{k}={repr(v)}" for k, v in inp.items())
        else:
            args_str = repr(inp)
        
        test_lines.extend([
            f"# Test {i}: {category}",
            "try:",
            f"    result = {function_name}({args_str})",
        ])
        
        if expected is not None:
            # Build result dict as JSON string to avoid f-string escaping issues
            result_dict = json.dumps({
                "category": category,
                "input": inp,
                "expected": expected,
                "passed": "__MATCH_PLACEHOLDER__",
            }).replace('true', 'True').replace('false', 'False').replace('"__MATCH_PLACEHOLDER__"', 'match')
            test_lines.extend([
                f"    match = result == {repr(expected)}",
                "    if match:",
                "        passed += 1",
                "    else:",
                "        failed += 1",
                f"    _rd = {result_dict}",
                "    _rd['actual'] = result",
                "    results.append(_rd)",
            ])
        else:
            # No expected value -- just check it doesn't crash
            result_dict = json.dumps({
                "category": category,
                "input": inp,
                "passed": True,
                "note": "no expected value - verified no crash",
            }).replace('true', 'True').replace('false', 'False')
            test_lines.extend([
                "    passed += 1",
                f"    _rd = {result_dict}",
                "    _rd['actual'] = result",
                "    results.append(_rd)",
            ])
        
        error_dict = json.dumps({
            "category": category,
            "input": inp,
            "passed": False,
        }).replace('true', 'True').replace('false', 'False')
        test_lines.extend([
            "except Exception as e:",
            "    failed += 1",
            f"    _ed = {error_dict}",
            "    _ed['error'] = str(e)",
            "    results.append(_ed)",
            "",
        ])
    
    test_lines.extend([
        "print(json.dumps({'passed': passed > 0 and failed == 0, 'total_tests': passed + failed, 'passed_tests': passed, 'failed_tests': failed, 'failures': [r for r in results if not r.get('passed', True)]}))",
    ])
    
    test_script = "\n".join(test_lines)
    
    # Run in subprocess with timeout
    try:
        proc = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if proc.returncode == 0:
            output = proc.stdout.strip().split("\n")[-1]  # Last line is JSON
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {
                    "passed": False,
                    "total_tests": len(test_cases),
                    "passed_tests": 0,
                    "failed_tests": len(test_cases),
                    "failures": [{"error": f"Could not parse test output: {output[:500]}"}],
                    "can_deliver": False,
                }
        else:
            # Syntax error or runtime error in the code itself
            error_msg = proc.stderr[:500] if proc.stderr else proc.stdout[:500]
            return {
                "passed": False,
                "total_tests": len(test_cases),
                "passed_tests": 0,
                "failed_tests": len(test_cases),
                "failures": [{"error": f"Code execution error: {error_msg}"}],
                "can_deliver": False,
            }
    
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "total_tests": len(test_cases),
            "passed_tests": 0,
            "failed_tests": len(test_cases),
            "failures": [{"error": "Code execution timed out (10s limit)"}],
            "can_deliver": False,
        }


def _run_javascript_tests(code: str, test_cases: list, function_name: Optional[str] = None) -> dict:
    """Run JavaScript code against test cases using Node.js."""
    if not function_name:
        import re
        match = re.search(r'function\s+(\w+)', code)
        if match:
            function_name = match.group(1)
        else:
            function_name = "func"
    
    test_lines = [
        "// User's code",
        code,
        "",
        "const results = [];",
        "let passed = 0;",
        "let failed = 0;",
        "",
    ]
    
    for i, tc in enumerate(test_cases):
        inp = tc.get("input", {})
        expected = tc.get("expected")
        category = tc.get("category", f"test_{i}")
        
        if isinstance(inp, dict):
            args_str = ", ".join(json.dumps(v) for v in inp.values())
        else:
            args_str = json.dumps(inp)
        
        test_lines.extend([
            f"// Test {i}: {category}",
            f"try {{",
            f"    const result = {function_name}({args_str});",
        ])
        
        if expected is not None:
            match_str = f"result === {json.dumps(expected)}" if not isinstance(expected, (list, dict)) else f"JSON.stringify(result) === JSON.stringify({json.dumps(expected)})"
            test_lines.extend([
                f"    const match = {match_str};",
                f"    if (match) passed++; else failed++;",
                f"    results.push({{category: {json.dumps(category)}, expected: {json.dumps(expected)}, actual: result, passed: match}});",
            ])
        else:
            test_lines.extend([
                f"    passed++;",
                f"    results.push({{category: {json.dumps(category)}, actual: result, passed: true, note: 'no expected value - verified no crash'}});",
            ])
        
        test_lines.extend([
            f"}} catch (e) {{",
            f"    failed++;",
            f"    results.push({{category: {json.dumps(category)}, error: e.message, passed: false}});",
            "}",
            "",
        ])
    
    test_lines.append(f'console.log(JSON.stringify({{passed: passed > 0 && failed === 0, total_tests: passed + failed, passed_tests: passed, failed_tests: failed, failures: results.filter(r => !r.passed)}}));')
    
    test_script = "\n".join(test_lines)
    
    try:
        proc = subprocess.run(
            ["node", "-e", test_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if proc.returncode == 0:
            output = proc.stdout.strip().split("\n")[-1]
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {
                    "passed": False,
                    "total_tests": len(test_cases),
                    "passed_tests": 0,
                    "failed_tests": len(test_cases),
                    "failures": [{"error": f"Could not parse test output: {output[:500]}"}],
                    "can_deliver": False,
                }
        else:
            error_msg = proc.stderr[:500] if proc.stderr else proc.stdout[:500]
            return {
                "passed": False,
                "total_tests": len(test_cases),
                "passed_tests": 0,
                "failed_tests": len(test_cases),
                "failures": [{"error": f"Code execution error: {error_msg}"}],
                "can_deliver": False,
            }
    
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "total_tests": len(test_cases),
            "passed_tests": 0,
            "failed_tests": len(test_cases),
            "failures": [{"error": "Code execution timed out (10s limit)"}],
            "can_deliver": False,
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "total_tests": len(test_cases),
            "passed_tests": 0,
            "failed_tests": len(test_cases),
            "failures": [{"error": "Node.js not found. Install Node.js to run JavaScript tests."}],
            "can_deliver": False,
        }


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    mcp.run()