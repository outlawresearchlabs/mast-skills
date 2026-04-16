# MAST Skills: Roadmap -- Structural Enforcement

## Direction Change

We are pivoting from prompt-only defenses (SOUL.md etc.) to structural enforcement (MCP integration, topology changes, code execution). The evidence is clear: prompts suggest, architecture enforces. Only enforcement closes the gap on FM-1.1, FM-3.2, and FM-3.3.

---

## Phase 0: Archive Prompt-Only Work (Current)

**Status**: Complete

All prompt-only artifacts are preserved in the repo as-is. FINDINGS.md documents the honest results. No prompt-only artifacts will be deleted, but they are deprecated for FC2/FC3 defenses.

**What we keep**:
- `skills/mast-taxonomy/` -- the 14-mode knowledge base is still genuinely useful
- `mcp/mast-enforce/` -- the MCP server is the starting point for structural work
- `tests/test_harness.py` -- still useful for FC1 regression testing
- All results data in `tests/results/`

**What we deprecate**:
- 6-file config suite (SOUL.md, RULES.md, PROMPT.md, MEMORY.md, BOOTSTRAP.md, USER.md) as a defense mechanism
- `skills/agent-workspace-interview/` in its current form -- generates prompt-only configs
- ChatDev MAST-hardened YAML as a standalone defense
- Static audit as a validation method

---

## Phase 1: Minimal FC1 Reminders + MCP Integration

**Goal**: Replace 6-file config suite with a single minimal RULES.md that only covers what prompts can actually do (FC1 forgetfulness modes), then integrate the MCP server into a real agent loop.

### 1a: Minimal Config

Replace the 6-file config suite with a single file containing only FC1 reminders:

```
# Agent Rules (FC1 Only)

## Anti-Loop (FM-1.3)
If you are about to repeat an action you already attempted, output <LOOP-DETECTED> and try a different approach.

## Clarification (FM-2.2)  
If requirements are ambiguous, output <CLARIFY> and ask before implementing.

## Termination (FM-1.5)
Only declare done when ALL acceptance criteria are explicitly met. Never mark partial work as complete.
```

Three rules. ~350 chars instead of 5,310. Covers only what prompts can actually enforce.

### 1b: MCP Server Integration

The existing `mcp/mast-enforce/` server has 3 tools:
- `verify_code(code, test_cases)` -- runs code against test cases, returns pass/fail
- `check_completion(task, acceptance_criteria, current_state)` -- checks if criteria are met
- `generate_edge_cases(function_spec, hints)` -- generates test cases beyond hints

**Integration target**: ChatDev agent loop

Current ChatDev flow:
1. CEO defines task → CTO breaks down → Programmer writes code → Code Reviewer reviews → Test Engineer tests → CPO finalizes

MAST-enforced flow:
1. CEO defines task → CTO breaks down → **Programmer writes code → [MCP: verify_code]** → Code Reviewer reviews → **[MCP: check_completion before CPO]** → **[MCP: generate_edge_cases for Test Engineer]** → CPO finalizes

The system blocks progression if verification fails. The agent cannot deliver unverified code because the next stage requires a passing `verify_code()` result.

### 1c: Integration Architecture

```
ChatDev Agent Loop
    |
    v
Programmer writes code
    |
    v
[MCP Tool Call: verify_code(code, test_cases)]
    |
    ├── PASS → proceed to Code Reviewer
    └── FAIL → return error to Programmer (must fix)
    
Code Reviewer reviews
    |
    v
Before CPO sign-off:
[MCP Tool Call: check_completion(task, criteria, state)]
    |
    ├── ALL_MET → proceed to CPO
    └── NOT_MET → return to Programmer with missing criteria
    
Test Engineer phase:
[MCP Tool Call: generate_edge_cases(spec, hints)]
    |
    v
Test Engineer must run both hints AND generated edge cases
    |
    v
[MCP Tool Call: verify_code(code, all_test_cases)]
    |
    ├── PASS → proceed
    └── FAIL → return to Programmer
```

### 1d: Validation Criteria

This phase succeeds if:
- ChatDev with MCP enforcement achieves > 3/5 pass@1 on the same 5 HumanEval problems
- Zero regressions on problems that baseline already passes
- FM-1.1 failures are reduced (the structural block catches spec violations via verify_code running actual test cases)

---

## Phase 2: Topology Changes

**Goal**: Implement the paper's most effective intervention -- changing the agent graph topology from DAG to cyclic with enforcement gates.

### 2a: Cyclic Graph with CTO Gate

Current ChatDev: DAG (CEO → CTO → Programmer → Code Reviewer → Test Engineer → CPO → done)

Paper's effective topology: Cyclic (any agent can send back to a previous agent, CTO must confirm all reviews satisfied before delivery)

Modified ChatDev topology:
```
CEO → CTO → Programmer ↔ Code Reviewer (cyclic: reviewer can send back)
              ↓ (only when reviewer approves)
         Test Engineer ↔ Programmer (cyclic: test failures go back)
              ↓ (only when tests pass, verified by MCP)
         CTO (gate: must confirm ALL criteria met)
              ↓ (only when CTO approves)
         CPO → done
```

The CTO gate is structural enforcement of FM-1.5 (termination awareness). No agent can mark done without CTO sign-off, and CTO can't sign off until `check_completion()` returns ALL_MET.

### 2b: Validation

Test the cyclic topology against:
- Same 5 HumanEval problems from Phase 1
- Additional 10-15 HumanEval problems for statistical power
- Compare: baseline DAG vs cyclic + MCP vs cyclic + MCP + minimal FC1 rules

---

## Phase 3: Specification Formalization

**Goal**: Address FM-1.1 (Disobey Task Specification) at the structural level by formalizing specs into testable contracts.

### 3a: Spec-to-Test Pipeline

Current problem: Programmers read a natural language spec and implement what they think it means. When function name/type signatures contradict the spec, the name wins.

Solution: Before the Programmer sees the task, the system:
1. Extracts the function signature from the HumanEval problem
2. Runs `generate_edge_cases()` against the spec to create a comprehensive test suite
3. The Programmer receives BOTH the spec AND the test suite
4. Code must pass the test suite via `verify_code()` before leaving the Programmer

This is structural FM-1.1 defense: the spec is encoded as executable tests, not as natural language suggestions.

### 3b: Validation

- FM-1.1 failure rate on HumanEval/2-class problems (where function name misleads)
- Target: reduce FM-1.1 from 100% of failures to < 50%

---

## Phase 4: Multi-Agent Framework Generalization

**Goal**: Make the structural enforcement approach work beyond ChatDev.

### 4a: Agent Framework Adapter

Create a generic adapter layer that:
- Hooks into any MCP-compatible agent framework
- Injects `verify_code()`, `check_completion()`, `generate_edge_cases()` at configurable workflow points
- Supports both cyclic and DAG topologies

### 4b: Validated Frameworks

- ChatDev (Python)
- AG2/AutoGen (Python)
- OpenAI Agents SDK (Python)
- Claude Code / Anthropic CLI

### 4c: Benchmark Suite

Run all validated frameworks against:
- HumanEval (164 problems) -- code generation
- SWE-Bench Lite -- real-world bug fixes
- Compare prompt-only vs structural enforcement on each

---

## Timeline Estimate

| Phase | Scope | Estimated Effort |
|---|---|---|
| Phase 1 | Minimal config + MCP integration into ChatDev | 1-2 sessions |
| Phase 2 | Cyclic topology + expanded HumanEval | 2-3 sessions |
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
- **Statistical significance** (minimum 20 problems, preference for 50+)
- **Zero regressions** on problems baseline already solves
- **Structural enforcement** preventing failures that prompts couldn't

The bar is: does the system actually complete more tasks correctly? Everything else is noise.