# MAST Skills: Roadmap -- In-Process Middleware

## Direction

We are building in-process Python middleware for structural enforcement in multi-agent systems. The evidence is clear:

- Prompts are unreliable (help or hurt depending on model, -18pp to +2pp)
- MCP tool calls are too slow (900s timeouts) and depend on model agency
- In-process middleware provides structural guarantees with zero LLM overhead

---

## Phase 1: In-Process Verification Middleware for ChatDev

**Goal**: Replace MCP tool calls with Python code that runs inside ChatDev's pipeline.

### 1a: State Gate Hook

ChatDev's `state_gate_manager.py` already checks `execution_context.global_state["verify_code_result"]`. We need to set this programmatically instead of via MCP tool calls.

Implementation:
1. Create `runtime/edge/conditions/inprocess_verify.py`
2. After each Programmer code write, automatically run:
   - Function signature extraction (AST parsing: function name, params, return type)
   - Spec-to-signature matching (compare HumanEval spec to generated signature)
   - Test extraction from docstring (parse `>>>` examples)
   - Test execution (run extracted tests against generated code)
3. Set `global_state["verify_code_result"]` = "PASS" or detailed failure message
4. State gates block progression on failure (existing behavior, no changes needed)

### 1b: Completion Check Hook

After CPO sign-off, before delivery:
1. Parse the task specification for acceptance criteria
2. Check if generated code actually defines the expected entry point
3. Run the full HumanEval test suite against the code
4. Block delivery if any test fails

### 1c: Validation

Benchmark against the same 25 HumanEval problems x 2 reps:
- Compare: baseline, MAST (prompt), lean (prompt), in-process middleware
- Success criteria: in-process middleware >= baseline on both GPT-4o and Gemma4
- Target: catch at least some FM-1.1 failures that prompts miss (signature mismatch detection)

---

## Phase 2: Cyclic Topology with Programmatic Gates

**Goal**: Implement the paper's most effective intervention (topology change) using in-process enforcement instead of MCP.

### 2a: Cyclic Graph with CTO Gate

Current ChatDev: DAG (CEO -> CTO -> Programmer -> Code Reviewer -> Test Engineer -> CPO -> done)

Proposed:
```
CEO -> CTO -> Programmer <-> Code Reviewer (cyclic: reviewer can send back)
              | (only when reviewer approves AND in-process verify passes)
         Test Engineer <-> Programmer (cyclic: test failures go back)
              | (only when tests pass, verified in-process)
         CTO (gate: must confirm ALL criteria met via in-process check)
              | (only when CTO approves)
         CPO -> done
```

The CTO gate is structural enforcement of FM-1.5 (termination awareness). No agent can mark done without CTO sign-off, and CTO can't sign off until programmatic verification passes.

### 2b: Validation

- 25+ HumanEval problems x 2 reps
- Compare: baseline, in-process middleware (linear), in-process middleware (cyclic)
- Target: topology + in-process should exceed all prompt-based approaches

---

## Phase 3: Specification Formalization

**Goal**: Address FM-1.1 (Disobey Task Specification) structurally by formalizing specs into testable contracts.

### 3a: Spec-to-Test Pipeline

1. Before Programmer sees the task, extract:
   - Function signature from HumanEval problem (name, params, return type)
   - Docstring examples as test cases (parse `>>>` blocks)
   - Generate edge cases programmatically (boundary values, type edge cases)
2. Programmer receives BOTH the spec AND the extracted test suite
3. Code must pass all tests via in-process verification before leaving Programmer

This is structural FM-1.1 defense: the spec is encoded as executable tests, not as natural language suggestions.

### 3b: Validation

- FM-1.1 failure rate on HumanEval/2-class problems (where function name misleads)
- Target: reduce FM-1.1 from 100% of failures to < 50%

---

## Phase 4: Multi-Agent Framework Generalization

**Goal**: Make in-process middleware work beyond ChatDev.

### 4a: Generic Middleware Interface

```python
class VerificationMiddleware:
    def after_code_write(self, code, spec, context):
        """Run after any code generation step. Return pass/fail + details."""
        ...

    def before_delivery(self, code, spec, test_results, context):
        """Run before any final delivery. Block if criteria unmet."""
        ...
```

Adapters for specific frameworks (ChatDev, AG2, OpenAI Agents SDK) implement the hooks.

### 4b: Validated Frameworks

- ChatDev (Python) -- primary
- AG2/AutoGen (Python)
- OpenAI Agents SDK (Python)

### 4c: Benchmark Suite

- HumanEval (164 problems) -- code generation
- Compare prompt-only vs in-process middleware on each framework
- Document model-dependent effects and demonstrate middleware eliminates them

---

## Timeline Estimate

| Phase | Scope | Estimated Effort |
|---|---|---|
| Phase 1 | In-process verification for ChatDev | 1-2 sessions |
| Phase 2 | Cyclic topology + expanded benchmark | 2-3 sessions |
| Phase 3 | Spec formalization pipeline | 1-2 sessions |
| Phase 4 | Multi-framework generalization | 3-5 sessions |

---

## Success Criteria (Revised)

We will NOT claim success based on:
- Static audit scores
- Synthetic trigger pass rates
- Keyword presence in config files

We WILL claim success based on:
- **Task completion rate** (pass@1 on HumanEval or equivalent benchmarks)
- **Statistical significance** (minimum 25 problems x 2 reps = 50 trials)
- **Reliability across models** -- the intervention must not regress any model
- **Structural enforcement preventing failures that prompts couldn't**

The bar is: does the system actually complete more tasks correctly, reliably, across all tested models?