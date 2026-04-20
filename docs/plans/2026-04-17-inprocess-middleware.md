# In-Process Verification Middleware Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace MCP tool calls with in-process Python middleware that verifies code inside ChatDev's pipeline, setting `global_state["verify_code_result"]` directly with zero LLM roundtrips.

**Architecture:** After the Programmer node writes code, a Python hook automatically: (1) extracts the saved code from disk, (2) extracts the spec signature from the original task prompt, (3) compares implementation signature to spec signature, (4) runs the HumanEval docstring examples as tests, (5) generates and runs edge case tests, (6) sets `global_state["verify_code_result"]`. The existing `state_gate_manager.py` already blocks graph edges when this value is bad -- no changes needed there.

**Tech Stack:** Python 3.11, AST parsing, subprocess for test execution (sandboxed), ChatDev graph executor hooks

---

## What Already Exists (DO NOT REBUILD)

1. **`state_gate_manager.py`** at `/tmp/ChatDev/runtime/edge/conditions/state_gate_manager.py` -- checks `global_state["verify_code_result"]` and blocks/opens edges. COMPLETE. NO CHANGES NEEDED.

2. **`_mast_extract_spec_signature()`** at `/tmp/ChatDev/runtime/node/executor/agent_executor.py:1428` -- extracts `def func(...)` from task prompt text. COMPLETE.

3. **MCP verify_code logic** at `/tmp/mast-skills/mcp/mast-enforce/server.py` -- signature comparison (`_get_impl_signature`, `_parse_function_signature`), edge case generation (`_generate_edge_cases_for_function`), test execution (`_run_python_tests`). THIS IS THE REFERENCE IMPLEMENTATION. We port these functions to run without MCP/FastMCP.

4. **MCP result capture** at `/tmp/ChatDev/runtime/node/executor/agent_executor.py:834-877` -- stores verify_code results in `global_state`. This will be REPLACED by the in-process hook (which sets `global_state` directly instead of capturing from MCP tool output).

5. **Benchmark script** at `/tmp/mast-skills/tests/chatdev_benchmark.py` -- runs HumanEval through ChatDev with multiple configs. Will need a new `--config inprocess` option.

---

## Task Sequence

### Task 1: Create the in-process verification module

**Objective:** Port the core verification logic from MCP server.py into a standalone Python module that runs without MCP/FastMCP.

**Files:**
- Create: `/tmp/ChatDev/runtime/edge/conditions/inprocess_verify.py`
- Reference: `/tmp/mast-skills/mcp/mast-enforce/server.py` (lines 51-520)

**Step 1: Create the module with core verification functions**

```python
"""
In-process verification middleware for MAST structural enforcement.

Runs code verification INSIDE ChatDev's pipeline as Python code,
not as MCP tool calls. Sets global_state["verify_code_result"]
directly -- zero LLM roundtrips, milliseconds not minutes.

This replaces the MCP mast-enforce server for ChatDev benchmarks.
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from typing import Any, Optional


def extract_spec_signature(task_prompt: str) -> str | None:
    """Extract the first Python function signature from a task prompt.
    
    Ported from agent_executor._mast_extract_spec_signature().
    Looks for `def function_name(...)` inside ```python ... ``` blocks.
    """
    pattern = r"```python\s*\n(.*?)```"
    blocks = re.findall(pattern, task_prompt, re.DOTALL | re.IGNORECASE)
    
    for block in blocks:
        for line in block.split("\n"):
            line = line.strip()
            match = re.match(r"^def\s+\w+\s*\([^)]*\)\s*(->\s*\w[\w\[\],\s]*\s*)?:", line)
            if match:
                return line
    
    for line in task_prompt.split("\n"):
        line = line.strip()
        match = re.match(r"^def\s+\w+\s*\([^)]*\)\s*(->\s*\w[\w\[\],\s]*\s*)?:", line)
        if match:
            return line
    
    inline_pattern = r"def\s+\w+\s*\([^)]*\)\s*(->\s*\w[\w\[\],\s]*)?"
    inline_match = re.search(inline_pattern, task_prompt)
    if inline_match:
        return inline_match.group(0).rstrip()
    
    return None


def _get_impl_signature(code: str, function_name: str) -> dict[str, str] | None:
    """Parse implementation code to extract function parameter names and types.
    
    Ported from MCP server.py.
    Returns dict of {param_name: type_annotation} or None.
    """
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                params = {}
                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    type_str = ""
                    if arg.annotation:
                        try:
                            type_str = ast.unparse(arg.annotation)
                        except Exception:
                            type_str = "Any"
                    params[arg.arg] = type_str or "Any"
                return params
    except SyntaxError:
        pass
    return None


def _parse_function_signature(signature: str, language: str = "python") -> dict[str, str] | None:
    """Parse a function signature string into {param_name: type} dict.
    
    Ported from MCP server.py.
    """
    if language.lower() != "python":
        return None
    
    signature = signature.strip()
    if not signature.startswith("def "):
        signature = "def " + signature
    if ":" not in signature:
        signature += ": pass"
    else:
        # Add pass after the colon for parsing
        sig_part = signature[:signature.index(":") + 1]
        signature = sig_part + " pass"
    
    try:
        tree = ast.parse(signature)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                params = {}
                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    if arg.annotation:
                        try:
                            params[arg.arg] = ast.unparse(arg.annotation)
                        except Exception:
                            params[arg.arg] = "Any"
                    else:
                        params[arg.arg] = "Any"
                return params
    except SyntaxError:
        pass
    return None


def check_signature_match(code: str, spec_signature: str, function_name: str | None = None) -> dict:
    """Compare implementation signature to spec signature.
    
    Returns dict with signature_match (bool), diagnosis (str), etc.
    """
    if not spec_signature:
        return {"signature_match": None, "diagnosis": None}
    
    if not function_name:
        function_name = _detect_function_name(code) or "func"
    
    impl_params = _get_impl_signature(code, function_name)
    spec_params = _parse_function_signature(spec_signature)
    
    if not impl_params or not spec_params:
        return {"signature_match": None, "diagnosis": "Could not parse signatures"}
    
    spec_param_names = set(spec_params.keys())
    impl_param_names = set(impl_params.keys())
    
    if spec_param_names == impl_param_names:
        return {
            "signature_match": True,
            "diagnosis": None,
            "spec_params": spec_params,
            "impl_params": impl_params,
        }
    
    extra = impl_param_names - spec_param_names
    missing = spec_param_names - impl_param_names
    diagnosis = (
        f"SIGNATURE MISMATCH: Implementation has parameters {list(impl_param_names)} "
        f"but spec expects {list(spec_param_names)}. "
        f"Extra: {list(extra)}. Missing: {list(missing)}. "
        f"FIX: Rewrite function to match: {spec_signature}"
    )
    return {
        "signature_match": False,
        "diagnosis": diagnosis,
        "spec_params": spec_params,
        "impl_params": impl_params,
        "extra_params": list(extra),
        "missing_params": list(missing),
    }


def _detect_function_name(code: str) -> str | None:
    """Auto-detect the main function name from code."""
    try:
        tree = ast.parse(code)
        # First function that's not __main__, private, or test
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                return node.name
    except SyntaxError:
        # Fallback: regex
        match = re.search(r"^def\s+(\w+)\s*\(", code, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def extract_doctest_cases(code: str, function_name: str | None = None) -> list[dict]:
    """Extract test cases from Python docstring examples (>>> patterns).
    
    Returns list of {"call": "...", "expected": "..."} dicts.
    """
    cases = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if function_name and node.name != function_name:
                    continue
                docstring = ast.get_docstring(node)
                if not docstring:
                    continue
                # Parse >>> lines and their expected output
                lines = docstring.split("\n")
                current_call = None
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith(">>> "):
                        current_call = stripped[4:].strip()
                    elif current_call and stripped and not stripped.startswith(">>>"):
                        cases.append({
                            "call": current_call,
                            "expected": stripped,
                        })
                        current_call = None
    except SyntaxError:
        pass
    return cases


def generate_edge_cases(function_name: str, params: dict[str, str]) -> list[dict]:
    """Generate edge case test inputs based on parameter types.
    
    Simplified version of MCP server's _generate_edge_cases_for_function.
    No LLM needed -- deterministic based on type annotations.
    """
    cases = []
    
    for pname, ptype in params.items():
        ptype_lower = ptype.lower() if ptype else ""
        
        if "int" in ptype_lower:
            cases.extend([
                {"args": {pname: 0}, "category": f"{pname}_zero"},
                {"args": {pname: -1}, "category": f"{pname}_negative"},
                {"args": {pname: 1}, "category": f"{pname}_one"},
                {"args": {pname: 999999}, "category": f"{pname}_large"},
            ])
        elif "float" in ptype_lower:
            cases.extend([
                {"args": {pname: 0.0}, "category": f"{pname}_zero"},
                {"args": {pname: -1.0}, "category": f"{pname}_negative"},
                {"args": {pname: 0.5}, "category": f"{pname}_fraction"},
                {"args": {pname: 1e10}, "category": f"{pname}_large"},
                {"args": {pname: -0.0}, "category": f"{pname}_neg_zero"},
            ])
        elif "bool" in ptype_lower:
            cases.extend([
                {"args": {pname: True}, "category": f"{pname}_true"},
                {"args": {pname: False}, "category": f"{pname}_false"},
            ])
        elif "str" in ptype_lower:
            cases.extend([
                {"args": {pname: ""}, "category": f"{pname}_empty"},
                {"args": {pname: "a"}, "category": f"{pname}_single"},
                {"args": {pname: " "}, "category": f"{pname}_whitespace"},
            ])
        elif "list" in ptype_lower:
            cases.extend([
                {"args": {pname: []}, "category": f"{pname}_empty"},
                {"args": {pname: [1]}, "category": f"{pname}_single"},
            ])
    
    return cases


def run_python_tests(code: str, function_name: str, test_calls: list[dict], timeout: int = 10) -> dict:
    """Execute Python code against test cases in a subprocess.
    
    Args:
        code: The implementation code
        function_name: Name of the function to test
        test_calls: List of {"call": "func(arg)", "expected": "result"} or 
                    {"args": {param: value}, "expected": "result"}
        timeout: Seconds before killing the subprocess
    
    Returns:
        Dict with passed_tests, total_tests, failures list, can_deliver bool
    """
    if not test_calls:
        return {
            "passed_tests": 0,
            "total_tests": 0,
            "failures": [],
            "can_deliver": False,
            "error": "No test cases to run",
        }
    
    # Build test script
    test_lines = [
        "import sys, json, traceback",
        "try:",
        textwrap.indent(code, "    "),
        "except Exception as e:",
        f'    print(json.dumps({{"passed_tests": 0, "total_tests": {len(test_calls)}, "failures": [str(e)], "can_deliver": False, "error": "Code failed to load: " + str(e)}}))',
        "    sys.exit(0)",
        "",
        "results = []",
        "failures = []",
    ]
    
    for i, tc in enumerate(test_calls):
        if "call" in tc:
            call_str = tc["call"]
            expected_str = tc.get("expected", "None")
        elif "args" in tc:
            # Build call from args dict
            args_parts = []
            for k, v in tc["args"].items():
                args_parts.append(f"{k}={repr(v)}")
            call_str = f"{function_name}({', '.join(args_parts)})"
            expected_str = tc.get("expected", "None")
        else:
            continue
        
        test_lines.extend([
            f"try:",
            f"    _result_{i} = {call_str}",
            f"    _expected_{i} = {expected_str}",
            f"    if _result_{i} == _expected_{i}:",
            f"        results.append(True)",
            f"    else:",
            f"        results.append(False)",
            f"        failures.append({{'test': {i}, 'call': {repr(call_str)}, 'expected': repr(_expected_{i}), 'got': repr(_result_{i})}})",
            f"except Exception as _e:",
            f"    results.append(False)",
            f"    failures.append({{'test': {i}, 'call': {repr(call_str)}, 'error': str(_e)}})",
        ])
    
    test_lines.extend([
        "",
        "print(json.dumps({",
        '    "passed_tests": sum(results),',
        '    "total_tests": len(results),',
        '    "failures": failures,',
        '    "can_deliver": sum(results) == len(results),',
        "}))",
    ])
    
    test_script = "\n".join(test_lines)
    
    # Run in subprocess with timeout
    try:
        proc = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = proc.stdout.strip()
        if stdout:
            result = json.loads(stdout.split("\n")[-1])  # Last line is JSON
            return result
        else:
            return {
                "passed_tests": 0,
                "total_tests": len(test_calls),
                "failures": [{"error": proc.stderr[:500]}],
                "can_deliver": False,
                "error": "Test script produced no output",
                "stderr": proc.stderr[:500],
            }
    except subprocess.TimeoutExpired:
        return {
            "passed_tests": 0,
            "total_tests": len(test_calls),
            "failures": [],
            "can_deliver": False,
            "error": f"Test execution timed out after {timeout}s",
        }
    except json.JSONDecodeError as e:
        return {
            "passed_tests": 0,
            "total_tests": len(test_calls),
            "failures": [],
            "can_deliver": False,
            "error": f"Could not parse test output: {e}",
        }
    except Exception as e:
        return {
            "passed_tests": 0,
            "total_tests": len(test_calls),
            "failures": [],
            "can_deliver": False,
            "error": f"Unexpected error: {e}",
        }


def verify_code_inprocess(
    code: str,
    spec_signature: str | None = None,
    function_name: str | None = None,
    run_doctests: bool = True,
    run_edge_cases: bool = True,
    timeout: int = 10,
) -> dict:
    """
    Main entry point for in-process verification.
    
    This is the function called by the ChatDev hook after each 
    Programmer code write. It combines signature checking,
    doctest extraction, edge case generation, and test execution
    into a single call that returns the same dict format as 
    MCP verify_code().
    
    Returns:
        Dict with: can_deliver, signature_match, passed_tests,
                   total_tests, failures, etc.
        This dict is stored in global_state["verify_code_result"]
        for state_gate_manager.py to check.
    """
    # 1. Detect function name
    if not function_name:
        function_name = _detect_function_name(code)
    
    if not function_name:
        return {
            "can_deliver": False,
            "signature_match": None,
            "passed_tests": 0,
            "total_tests": 0,
            "failures": [],
            "error": "No function found in code",
        }
    
    # 2. Check signature match (FM-1.1 defense)
    sig_result = check_signature_match(code, spec_signature, function_name)
    if sig_result.get("signature_match") is False:
        return {
            "can_deliver": False,
            "signature_match": False,
            "signature_mismatch": sig_result,
            "passed_tests": 0,
            "total_tests": 0,
            "failures": [],
            "error": sig_result["diagnosis"],
        }
    
    # 3. Build test cases
    test_cases = []
    
    # 3a. Extract doctest examples
    if run_doctests:
        doctests = extract_doctest_cases(code, function_name)
        test_cases.extend(doctests)
    
    # 3b. Generate edge cases from spec signature (trusted source)
    if run_edge_cases and spec_signature:
        spec_params = _parse_function_signature(spec_signature)
        if spec_params:
            edge_cases = generate_edge_cases(function_name, spec_params)
            test_cases.extend(edge_cases)
    
    # 3c. Generate edge cases from implementation if no spec
    elif run_edge_cases:
        impl_params = _get_impl_signature(code, function_name)
        if impl_params:
            edge_cases = generate_edge_cases(function_name, impl_params)
            test_cases.extend(edge_cases)
    
    # 4. Run tests
    test_result = run_python_tests(code, function_name, test_cases, timeout)
    
    # 5. Build final result
    result = {
        "can_deliver": test_result.get("can_deliver", False),
        "signature_match": sig_result.get("signature_match"),  # None if no spec sig provided
        "passed_tests": test_result.get("passed_tests", 0),
        "total_tests": test_result.get("total_tests", 0),
        "failures": test_result.get("failures", []),
    }
    
    if test_result.get("error"):
        result["error"] = test_result["error"]
    
    if sig_result.get("diagnosis"):
        result["signature_mismatch"] = sig_result
    
    return result
```

**Step 2: Verify the module loads and basic tests pass**

Run: `cd /tmp/ChatDev && python3 -c "from runtime.edge.conditions.inprocess_verify import verify_code_inprocess, extract_spec_signature; print('IMPORT OK'); sig = extract_spec_signature('Implement \`def truncate_number(number: float) -> float\`'); print(f'SIG: {sig}')"`

Expected: `IMPORT OK` and `SIG: def truncate_number(number: float) -> float`

**Step 3: Verify signature mismatch detection works**

Run: `cd /tmp/ChatDev && python3 -c "from runtime.edge.conditions.inprocess_verify import verify_code_inprocess; result = verify_code_inprocess('def truncate_number(number: float, d: int) -> float:\\n    return float(Decimal(str(number)).quantize(Decimal(\"1.\" + \"0\"*d)))', spec_signature='def truncate_number(number: float) -> float'); print(f'can_deliver={result[\"can_deliver\"]}, signature_match={result[\"signature_match\"]}')"`

Expected: `can_deliver=False, signature_match=False`

**Step 4: Commit**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "feat: in-process verification module (port of MCP verify_code logic)"
```

---

### Task 2: Hook inprocess_verify into ChatDev's Programmer node

**Objective:** After the Programmer finishes writing code, automatically run inprocess verification and set `global_state["verify_code_result"]`. This replaces both the MCP tool call AND the MCP result capture logic.

**Files:**
- Modify: `/tmp/ChatDev/runtime/node/executor/agent_executor.py` (replace MCP capture at lines 834-877)
- Reference: `/tmp/ChatDev/runtime/edge/conditions/inprocess_verify.py` (from Task 1)

**Step 1: Replace the MCP result capture block with in-process verification**

In agent_executor.py, find the block at line 834 that starts with `# --- MAST Structural Enforcement: capture verify_code results ---` and ends at line 877 `# --- End MAST injection ---`.

Replace it with:

```python
                    # --- MAST Structural Enforcement: In-process verification ---
                    # After tool execution, check if this was a code-writing tool
                    # and run in-process verification automatically.
                    # This replaces MCP tool-call-based verification with 
                    # Python code that runs in milliseconds, not minutes.
                    if tool_name in ("write_file", "save_file", "create_file"):
                        try:
                            from runtime.edge.conditions.inprocess_verify import (
                                verify_code_inprocess,
                                extract_spec_signature,
                            )
                            
                            # Extract the written code from tool arguments
                            file_content = arguments.get("content", arguments.get("text", ""))
                            filename = arguments.get("filename", arguments.get("path", ""))
                            
                            # Only verify Python files
                            if file_content and filename and filename.endswith(".py"):
                                task_prompt = self.context.global_state.get("_mast_task_prompt", "")
                                spec_sig = extract_spec_signature(task_prompt) if task_prompt else None
                                
                                # Strip BOM and fix escaped quotes (same as evaluation code)
                                clean_code = file_content.lstrip('\ufeff')
                                clean_code = clean_code.replace('\\"', '"')
                                
                                verify_result = verify_code_inprocess(
                                    code=clean_code,
                                    spec_signature=spec_sig,
                                    run_doctests=True,
                                    run_edge_cases=True,
                                    timeout=10,
                                )
                                
                                self.context.global_state["verify_code_result"] = verify_result
                                self.log_manager.info(
                                    f"[MAST] In-process verification: "
                                    f"can_deliver={verify_result.get('can_deliver')}, "
                                    f"signature_match={verify_result.get('signature_match')}, "
                                    f"passed={verify_result.get('passed_tests', '?')}/{verify_result.get('total_tests', '?')}"
                                )
                                
                                # If verification failed, inject diagnostic feedback into tool result
                                if not verify_result.get("can_deliver"):
                                    diag = ""
                                    if verify_result.get("signature_match") is False:
                                        mismatch = verify_result.get("signature_mismatch", {})
                                        diag = mismatch.get("diagnosis", "SIGNATURE MISMATCH detected")
                                    elif verify_result.get("error"):
                                        diag = f"Verification error: {verify_result['error']}"
                                    elif verify_result.get("failures"):
                                        first_fail = verify_result["failures"][0]
                                        diag = f"Test failed: {first_fail}"
                                    
                                    if diag:
                                        # Append diagnostic to tool result so the model sees WHY
                                        diag_message = (
                                            f"\n\n--- VERIFICATION FAILED ---\n"
                                            f"{diag}\n"
                                            f"--- You MUST fix the code before proceeding. ---"
                                        )
                                        # Inject into result
                                        if isinstance(result, list):
                                            for block in result:
                                                if hasattr(block, "text"):
                                                    block.text += diag_message
                                                    break
                                                elif isinstance(block, dict) and block.get("type") == "text":
                                                    block["text"] += diag_message
                                                    break
                                        elif isinstance(result, str):
                                            result += diag_message
                        except Exception as e:
                            self.log_manager.info(
                                f"[MAST] In-process verification exception: {e}"
                            )
                    # --- End MAST in-process enforcement ---
```

Also KEEP the existing spec_signature injection code (lines 650-669) AND the task prompt capture (lines 75-79) since inprocess_verify uses `_mast_task_prompt` from global_state.

**Step 2: Verify the hook fires on a real ChatDev run**

Run a quick single-problem test with the inprocess config:
```bash
cd /tmp/mast-skills
python3 -u tests/chatdev_benchmark.py --model gemma4 --config inprocess --subset 1 --reps 1 --timeout 300
```

Expected: `[MAST] In-process verification:` lines in the ChatDev log showing can_deliver and signature_match values.

**Step 3: Commit**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "feat: in-process verification hook in agent_executor (replaces MCP capture)"
```

---

### Task 3: Create the inprocess YAML config

**Objective:** Create a ChatDev YAML config that uses in-process verification + state gates WITHOUT MCP tooling.

**Files:**
- Create: `/tmp/ChatDev/yaml_instance/ChatDev_v1_inprocess_gw.yaml` (gemma4)
- Create: `/tmp/ChatDev/yaml_instance/ChatDev_v1_inprocess_gpt4o.yaml` (gpt-4o)
- Reference: `/tmp/ChatDev/yaml_instance/ChatDev_v1_mcp_enforced.yaml` (MCP config -- we copy its topology but remove MCP tooling)

**Step 1: Create gemma4 inprocess config**

Copy the baseline gemma4 config, then apply these changes:
1. Keep the SAME graph topology as baseline (no cyclic changes yet -- that's Phase 2)
2. Add `state_gate` edge conditions on Programmer Code Complete → Code Review:
   - `state_key: verify_code_result`
   - `check_field: can_deliver`
   - `expected_value: true`
3. Disable the keyword shortcut edge (`<INFO> FINISHED`) from Code Complete with `always_false`
4. NO MCP tooling entries (no `mcp_remote`)
5. NO MAST verbose prompts (use baseline prompt text)
6. Add a minimal common prompt note: "Before saving code, ensure function signature matches specification."

The key difference from MCP config: no `mcp_remote` tooling, no `verify_code` in tool list. The in-process hook fires automatically on `write_file` calls.

**Step 2: Create gpt-4o inprocess config**

Same as above but with `gpt-4o` as model name instead of `gemma4:31b-cloud`, and using OpenAI base URL.

**Step 3: Update benchmark script to support --config inprocess**

In `/tmp/mast-skills/tests/chatdev_benchmark.py`, add the `inprocess` config to `MODEL_CONFIGS` for both models:
```python
"inprocess": {
    "yaml_file": "ChatDev_v1_inprocess_{model}.yaml",
    "description": "In-process Python verification + state gates (no MCP, no verbose prompts)",
}
```

**Step 4: Commit**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "feat: inprocess YAML configs for gemma4 and gpt-4o"
```

---

### Task 4: Validate inprocess on HumanEval/2 (the known FM-1.1 failure)

**Objective:** Run the single problem that FAILS on baseline/MAST but PASSES on MCP+gates+trusted-spec. Verify inprocess also passes it.

**Files:**
- No new files
- Results: `/tmp/mast-skills/tests/results/benchmark/gemma4/inprocess/rep1/`

**Step 1: Run HumanEval/2 only**

```bash
cd /tmp/mast-skills
python3 -u tests/chatdev_benchmark.py --model gemma4 --config inprocess --subset 1 --problem 2 --reps 1 --timeout 300
```

Expected: PASS. The in-process hook should detect the signature mismatch on `truncate_number(number, d)` vs spec `truncate_number(number)`, set `can_deliver: false`, state gate blocks, model gets SIGNATURE MISMATCH diagnosis, fixes code.

**Step 2: If it fails, debug**

Check ChatDev log for:
- `[MAST] In-process verification:` lines -- is the hook firing?
- `[MAST] verify_code_result stored` -- is global_state being set?
- State gate evaluations -- are they checking the right key?

Common issues:
- `write_file` tool name might differ in ChatDev v2 (could be `save_to_file`, `write`, etc.)
- Code might not be in `arguments["content"]` -- check actual argument names
- BOM/escaped quote handling might differ from evaluation code

**Step 3: Once passing, commit**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "validate: inprocess passes HumanEval/2 (FM-1.1 failure)"
```

---

### Task 5: Run the full benchmark -- gemma4 inprocess (25 problems × 2 reps)

**Objective:** Get publication numbers for gemma4 inprocess config.

**Files:**
- Results: `/tmp/mast-skills/tests/results/benchmark/gemma4/inprocess/`

**Step 1: Run the benchmark (sequentially on local gateway)**

```bash
cd /tmp/mast-skills
python3 -u tests/chatdev_benchmark.py --model gemma4 --config inprocess --subset 25 --reps 2 --resume --timeout 600
```

This will take ~3-5 hours. Use `--resume` so it can be interrupted and restarted. Each problem writes results.json so completed problems are skipped on resume.

**Step 2: While benchmark runs, monitor**

Check results as they come in:
```bash
cat /tmp/mast-skills/tests/results/benchmark/gemma4/inprocess/rep1/results.json | python3 -c "import json,sys; d=json.load(sys.stdin); passed=sum(1 for r in d if r.get('passed')); print(f'{passed}/{len(d)} pass@1')"
```

**Step 3: When complete, tabulate results**

Compare against existing baseline (98%) and MAST (96%):
```bash
# After both reps complete
python3 -c "
import json
rep1 = json.load(open('/tmp/mast-skills/tests/results/benchmark/gemma4/inprocess/rep1/results.json'))
rep2 = json.load(open('/tmp/mast-skills/tests/results/benchmark/gemma4/inprocess/rep2/results.json'))
total = len(rep1) + len(rep2)
passed = sum(1 for r in rep1 if r.get('passed')) + sum(1 for r in rep2 if r.get('passed'))
print(f'Inprocess: {passed}/{total} ({passed/total*100:.1f}%)')
"
```

**Step 4: Commit results**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "benchmark: gemma4 inprocess results (25x2)"
```

---

### Task 6: Run the full benchmark -- gpt-4o inprocess (25 problems × 2 reps)

**Objective:** Get publication numbers for gpt-4o inprocess config.

**Files:**
- Results: `/tmp/mast-skills/tests/results/benchmark/gpt4o/inprocess/`

**Step 1: Run the benchmark (OpenAI API, can run 2 reps concurrently)**

```bash
cd /tmp/mast-skills
export OPENAI_API_KEY=sk-proj-3hv9...
export OPENAI_BASE_URL=https://api.openai.com/v1

# Run both reps simultaneously (OpenAI handles concurrency)
python3 -u tests/chatdev_benchmark.py --model gpt4o --config inprocess --subset 25 --reps 1 --resume --timeout 300 &
python3 -u tests/chatdev_benchmark.py --model gpt4o --config inprocess --subset 25 --reps 2 --resume --timeout 300 &
```

This will take ~50 minutes (1 min/problem × 25 problems × 2 reps, concurrent).

**Step 2: Tabulate and compare against baseline (88%), MAST (70%), lean (90%)**

**Step 3: Commit results**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "benchmark: gpt-4o inprocess results (25x2)"
```

---

### Task 7: Zero-regression check

**Objective:** Verify inprocess doesn't break problems that baseline already passes. Any regression means the hook is breaking good code.

**Files:**
- No new files -- uses results from Tasks 5-6

**Step 1: Compare problem-by-problem**

```bash
python3 -c "
import json

for model in ['gemma4', 'gpt4o']:
    base_r1 = json.load(open(f'/tmp/mast-skills/tests/results/benchmark/{model}/baseline/rep1/results.json'))
    base_r2 = json.load(open(f'/tmp/mast-skills/tests/results/benchmark/{model}/baseline/rep2/results.json'))
    inp_r1 = json.load(open(f'/tmp/mast-skills/tests/results/benchmark/{model}/inprocess/rep1/results.json'))
    inp_r2 = json.load(open(f'/tmp/mast-skills/tests/results/benchmark/{model}/inprocess/rep2/results.json'))
    
    base_pass = {}
    for r in base_r1 + base_r2:
        key = r['task_id']
        base_pass.setdefault(key, []).append(r.get('passed', False))
    inp_pass = {}
    for r in inp_r1 + inp_r2:
        key = r['task_id']
        inp_pass.setdefault(key, []).append(r.get('passed', False))
    
    regressions = []
    improvements = []
    for key in set(base_pass) & set(inp_pass):
        b_rate = sum(base_pass[key]) / len(base_pass[key])
        i_rate = sum(inp_pass[key]) / len(inp_pass[key])
        if b_rate > i_rate:
            regressions.append(key)
        elif i_rate > b_rate:
            improvements.append(key)
    
    print(f'{model}: {len(regressions)} regressions, {len(improvements)} improvements')
    if regressions:
        print(f'  REGRESSIONS: {regressions}')
    if improvements:
        print(f'  IMPROVEMENTS: {improvements}')
"
```

Expected: 0 regressions. If there are regressions, investigate whether the inprocess hook is producing false negatives (setting can_deliver=false on correct code).

**Step 2: Commit analysis**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "analysis: inprocess zero-regression check"
```

---

### Task 8: Update FINDINGS.md and README.md with inprocess results

**Objective:** Document the results honestly.

**Files:**
- Modify: `/tmp/mast-skills/FINDINGS.md`
- Modify: `/tmp/mast-skills/README.md`

**Step 1: Add inprocess results to the benchmark table**

Add a row to the existing tables:

```
| In-process | ??/??.?% | ??/? (?) | ??/? (?) | ??pp |
```

**Step 2: Update the summary table**

```
| Model | Baseline | MAST | Lean | In-process |
|-------|----------|------|------|------------|
| gpt-4o | 88% | 70% (-18pp) | 90% (+2pp) | ??% (??pp) |
| gemma4 | 98% | 96% (-2pp) | 94% (-4pp) | ??% (??pp) |
```

**Step 3: Add finding about in-process vs MCP**

Whether the result is positive, neutral, or negative, document it. If inprocess >= baseline: "In-process structural enforcement is the first defense approach that improves (or matches) both models." If inprocess < baseline on any model: document why (false negatives from overzealous verification).

**Step 4: Commit**

```bash
cd /tmp/mast-skills && git add -A && git commit -m "docs: inprocess benchmark results and analysis"
```

---

## Success Criteria

1. Inprocess module loads and passes unit tests (Task 1)
2. Hook fires automatically after Programmer writes code (Task 2)
3. Inprocess PASSES HumanEval/2 -- the canonical FM-1.1 failure (Task 4)
4. Inprocess >= baseline on BOTH models (Tasks 5-6)
5. Zero regressions on problems baseline already passes (Task 7)
6. Results documented honestly (Task 8)

## Expected Outcome

If the approach works as theorized:
- Inprocess should catch FM-1.1 failures that baseline misses (like HumanEval/2)
- Inprocess should NOT regress on problems baseline already passes
- Inprocess should be >= baseline on both models
- Inprocess overhead should be ~1s/problem (just Python subprocess), not 900s/problem (MCP)

The result would be: **prompt-only defenses are unreliable (-18pp to +2pp), but in-process structural enforcement matches or exceeds baseline with zero LLM overhead.**

If inprocess doesn't improve on baseline, that's also a valid finding: it means the verification hook's false negatives cancel out the FM-1.1 catches, and we need a different approach (pure spec-to-test pipeline, cyclic topology, etc.).