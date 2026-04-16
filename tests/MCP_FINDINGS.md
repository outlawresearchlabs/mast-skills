# MAST Structural Enforcement Findings

## Phase 1: Detection vs Enforcement (COMPLETED)

### MCP Tool Access (No State Gates)
- **Result**: verify_code detects FM-1.1 failures perfectly (0/24 tests, can_deliver:false)
- **Problem**: Model IGNORES the feedback and proceeds with broken code
- **Verdict**: Detection without enforcement is useless

### MCP + State-Gated Edges (v1)
- **Result**: State gates successfully block Code Complete -> Code Review progression
- **Problem**: Model loops indefinitely in Code Complete without fixing code
- **Verdict**: Blocking works, but without diagnostic feedback the model can't self-correct

### Gaming Vector
- Model can pass `auto_edge_cases: False` to disable rigorous testing
- Model can pass its own wrong signature as `spec_signature` to trick the tool
- **Verdict**: Models treat verification as an optimization target, not a correctness check

---

## Phase 2: Trusted Enforcement (COMPLETED)

### Root Cause: Task Prompt Truncation
- Python's `input()` in run.py reads only ONE LINE of stdin
- The task prompt with `def truncate_number(number: float) -> float:` in a code fence was truncated to just "Implement the Python function..."
- THE MODEL NEVER SAW THE SPEC SIGNATURE IN ANY PREVIOUS TEST
- Fix: Changed `run.py` to use `sys.stdin.read()` for piped input

### Fix 1: Trusted spec_signature Injection
- Added `_mast_extract_spec_signature()` to agent_executor.py
- Parses the task prompt for `def func(...)` inside ```python code fences
- When verify_code is called, the model's `spec_signature` argument is OVERWRITTEN with the trusted value extracted from the task prompt
- The model cannot game this -- it's server-side injection

### Fix 2: MessageBlock Result Parsing
- MCP tool results came back as `[MessageBlock(type='text', text='...')]` not `[{'type': 'text', 'text': '...'}]`
- The original dict-checking code couldn't parse these
- Fixed to also handle MessageBlock objects with `.text` attribute

### Final Test Results (HumanEval/2 - truncate_number)

| Metric | Value |
|--------|-------|
| Trusted spec_signature overrides | 35 |
| verify_code results stored | 23 |
| State gate BLOCKED (wrong code) | 1 |
| State gate PASSED (correct code) | 13 |
| Final code signature | `def truncate_number(number: float) -> float` ✓ |
| Final code implementation | `Decimal(str(number)) - int(d)` ✓ |
| Workflow completed | Yes (success=True) |
| Total input tokens | 353,498 |

### Timeline of Enforcement
1. Model first writes wrong multi-param signature (FM-1.1)
2. verify_code with trusted spec_signature detects SIGNATURE MISMATCH
3. State gate blocks Code Complete -> Loop Counter (1 block)
4. Model sees "SIGNATURE MISMATCH: your function has [decimals, number] but spec expects [number]"
5. Model fixes the code to match the spec signature
6. verify_code returns can_deliver:true, signature_match:true, passed=10/10+
7. State gate opens, pipeline progresses to Code Review
8. Pipeline completes successfully with correct code

### Key Finding
**Structural enforcement with trusted diagnostics CAN resolve FM-1.1 failures.**

The combination of:
1. State-gated edges (block progression on failure)
2. Trusted spec_signature injection (server-side, not model-provided)
3. Human-readable SIGNATURE MISMATCH diagnostics
4. Auto-generated edge cases from the SPEC signature (not the model's)

...is sufficient to make gemma4:31b fix an FM-1.1 failure that it previously could not fix with prompt-only defenses, MCP detection without gates, or even MCP+gates without trusted diagnostics.

### Critical Infrastructure Bugs Found
1. **`input()` truncation**: Python's `input()` reads one line from stdin, losing multi-line task prompts with code fences. Fixed with `sys.stdin.read()`.
2. **MessageBlock vs dict**: MCP tool results use MessageBlock objects, not plain dicts. Required `hasattr(block, "text")` handling.

---

## Comparison Across All Approaches

| Approach | Detection | Enforcement | FM-1.1 Result | Overhead |
|----------|-----------|-------------|---------------|----------|
| Baseline | None | None | FAIL | None |
| MAST 6-file prompts | None | None | FAIL (identical) | +80% prompt tokens |
| MCP tools (no gates) | Yes | No | FAIL (model ignores) | +tool calls |
| MCP + state gates (v1) | Yes | Yes (blocks) | STALEMATE | +complexity |
| MCP + gates + trusted spec | Yes | Yes (blocks+fixes) | **PASS** | +complexity |

The progression from failure to success required ALL of:
- Structural gates (not prompt-level suggestions)
- Server-side trusted data injection (not model-provided)
- Clear diagnostic feedback (not just "0/24 tests failed")
- Specification-aware edge cases (not model-signature-matched)

Remove any one layer and the system fails. This validates the "defense in depth" principle from the MAST taxonomy.