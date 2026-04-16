# MAST Skills

Tools for preventing the 14 failure modes from the MAST taxonomy (UC Berkeley paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

## Current Status: Pivoting to Structural Enforcement

**Prompt-only MAST defenses (config files like SOUL.md, RULES.md, etc.) produce zero improvement on real task completion.** This is our key finding, documented in [FINDINGS.md](FINDINGS.md).

What we learned:
- Static audit (14/14 DEFENDED) measures keyword presence, not behavior
- Synthetic trigger tests (100% pass rate) measure whether a model obeys config instructions when explicitly tested -- not whether defenses work in practice
- ChatDev HumanEval (the only real test): **MAST = Baseline = 3/5 pass@1. Zero improvement.**
- All failures were FM-1.1 (Disobey Task Specification). The "Specification Adherence Protocol" in the config did not prevent a single failure.

This confirms the paper's finding: **structural enforcement (topology, code execution, system gates) outperforms prompt engineering**. The paper showed +0.7pp for prompts vs +1.9pp for topology changes on ChatDev HumanEval.

**We are now building structural enforcement.** See [ROADMAP.md](ROADMAP.md) for the plan.

## What's Here

### Useful

- **[skills/mast-taxonomy/](skills/mast-taxonomy/)** -- Complete reference for the 14 MAST failure modes, prevalence data, and solution strategies. This is genuinely useful for understanding where multi-agent systems fail.
- **[mcp/mast-enforce/](mcp/mast-enforce/)** -- MCP server with 3 structural enforcement tools: `verify_code()`, `check_completion()`, `generate_edge_cases()`. Currently unit-tested but not yet integrated into a real agent loop.
- **[tests/test_harness.py](tests/test_harness.py)** -- Failure injection test harness. Still useful for FC1 (forgetfulness) regression testing. Should not be used as evidence of real defense effectiveness.

### Deprecated (Prompt-Only)

- **skills/agent-workspace-interview/** -- Generates 6-file config suite. The configs are prompt suggestions that don't improve real task completion.
- **skills/mast-audit/** -- Static keyword audit. Can tell you if defense phrases exist, not if they work.
- **tests/test-configs/mast-hardened/** -- The 6-file MAST-hardened config suite. Preserved for reference.
- **tests/chatdev-setup/ChatDev_v1_mast.yaml** -- MAST-hardened ChatDev config. Identical task completion to baseline.

### Results

- **[FINDINGS.md](FINDINGS.md)** -- Honest assessment of what works and what doesn't across all testing levels
- **[tests/RESULTS.md](tests/RESULTS.md)** -- Full raw results including static audit, dynamic tests, HuggingFace validation, ChatDev whole-system, and MCP simulation
- **[ROADMAP.md](ROADMAP.md)** -- Plan for structural enforcement approach

## Key Findings Summary

| Test Level | Method | Result | Validity |
|---|---|---|---|
| Static audit | Keyword matching | 14/14 DEFENDED | Low -- measures text, not behavior |
| Synthetic triggers (gemma4) | Failure injection | 14/14 PASS (+29.1% vs baseline) | Medium -- measures compliance, not real failure reduction |
| Synthetic triggers (GPT-4o) | Failure injection | 14/14 PASS (+18.8% vs baseline) | Low -- strong model doesn't need MAST; baseline already 11/14 |
| Whole-system (ChatDev) | HumanEval pass@1 | MAST = Baseline = 3/5 | **High -- this is what matters** |

### The gap between component and system tests

On synthetic triggers, MAST-hardened gemma4 scores 14/14 (100%). On actual HumanEval tasks through ChatDev, it scores 3/5 (60%). The 14/14 number tells you the model will follow config instructions when explicitly tested. It does NOT tell you the defenses prevent real failures.

### What prompts can do (FC1: forgetfulness)

- FM-1.3 (step repetition): Anti-loop tags work as reminders
- FM-2.2 (clarification): `<CLARIFY>` tag prompts a behavior the model can already do
- FM-1.5 (termination): Termination conditions work as reminders on weak models

### What prompts cannot do (FC2/FC3: reasoning/verification)

- FM-1.1 (disobey spec): Model ignores "NEVER implement based on function name" when type priors are strong
- FM-3.2 (no verification): Model can't execute code; "verify before delivery" produces superficial checks
- FM-3.3 (incorrect verification): "Never trust hints" doesn't override the model's tendency to use available information

## The Paper's Intervention Hierarchy

| Intervention | ChatDev ProgramDev | ChatDev HumanEval |
|---|---|---|
| Prompt improvements | +9.4% | +0.7pp |
| Topology change (DAG → cyclic) | +15.6% | +1.9pp |

Our result: +0.0pp with prompt-only MAST defenses. Consistent with the paper.

## Next Steps

See [ROADMAP.md](ROADMAP.md) for the full plan. Short version:

1. **Replace 6-file config suite** with a single minimal RULES.md (3 rules, ~350 chars, FC1 only)
2. **Integrate MCP server** into ChatDev's agent loop so verification is structurally enforced
3. **Implement cyclic topology** with CTO sign-off gate (the paper's most effective intervention)
4. **Build spec-to-test pipeline** that formalizes specs as executable tests (structural FM-1.1 defense)
5. **Generalize** to other agent frameworks (AG2, OpenAI Agents SDK, etc.)

## License

MIT