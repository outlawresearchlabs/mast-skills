# MAST Skills: Experimental Findings

## TL;DR

Prompt-only MAST defenses (SOUL.md, RULES.md, PROMPT.md, etc.) show **zero improvement** on real task completion. All claimed improvements are on synthetic proxy metrics that do not translate to actual multi-agent system performance. This confirms the paper's finding that structural enforcement, not communication protocols, is required for specification adherence and verification failures.

---

## The 3 Testing Levels

We tested MAST defenses at 3 levels of increasing real-world validity. Only level 3 matters.

### Level 1: Static Audit (keyword matching)

**Result**: 14/14 DEFENDED (100%)

**What it measures**: Whether config files contain keywords/phrases matching each failure mode's defense pattern.

**Why it's misleading**: Having "NEVER implement based on the function name alone" in SOUL.md does not mean the model will actually follow that instruction. This is a text search, not a behavioral test.

### Level 2: Dynamic Failure Injection (synthetic triggers)

**Results across models**:

| Model | Baseline | MAST-Hardened | Delta |
|---|---|---|---|
| gemma4:31b-cloud | 10/14 (70.9%) | 14/14 (100%) | +29.1% trigger pass rate |
| gpt-4o | 11/14 (81.2%) | 14/14 (100%) | +18.8% trigger pass rate |
| claude-sonnet-4 | 10/14 (75.1%) | 13/14 (97.2%) | +22.1% trigger pass rate |

**ChatDev Programmer role (gemma4)**:
| Config | Score | Delta vs Baseline |
|---|---|---|
| Baseline (no MAST) | 8/14 | -- |
| MAST-Lite (compressed bullets) | 7/14 | -1 (worse than baseline!) |
| MAST-Full (structured tags) | 11/14 | +3 |

**What it measures**: Whether a model resists a deliberately crafted failure trigger prompt when the config tells it not to.

**Why it's misleading**:
- The test PROMPTS the model to fail, then checks if the CONFIG told it not to. The model's compliance with the config is what's measured, not whether the defense works in practice.
- On strong models (GPT-4o, Claude), the baseline already passes most modes without MAST. MAST adds nothing.
- On weak models (gemma4), the model is suggestible -- it follows config instructions because it follows most instructions. This is not a defense property; it's a model property.
- MAST-Lite (compressed rules) actively UNDERPERFORMS baseline. This means the defense effectiveness depends on prompt length/format, not defense content.

### Level 3: Whole-System Validation (actual task completion)

**Result**: Baseline = MAST = 3/5 pass@1 (60%), **ZERO improvement**

| Problem | Baseline | MAST | Delta |
|---|---|---|---|
| HumanEval/0 | PASS | PASS | SAME |
| HumanEval/2 | FAIL (FM-1.1) | FAIL (FM-1.1) | SAME |
| HumanEval/4 | PASS | PASS | SAME |
| HumanEval/10 | PASS | PASS | SAME |
| HumanEval/17 | FAIL (FM-1.1) | FAIL (FM-1.1) | SAME |

**Model**: gemma4:31b-cloud via local gateway
**Pipeline**: ChatDev multi-agent (CEO → CTO → Programmer → Code Reviewer → Test Engineer → CPO)

**Critical details**:
- ALL failures are FM-1.1 (Disobey Task Specification)
- The MAST config includes an explicit "Specification Adherence Protocol" telling the model "NEVER implement based on the function name alone"
- HumanEval/2 (`truncate_number`) failed **identically** in both configs: the model added a `d: int` parameter and implemented "truncate to N decimals" instead of "extract decimal part"
- The model simply ignored the instruction when the function name strongly suggested a different implementation

**This is the only test that matters** and it shows prompt-only MAST defenses do nothing.

---

## What Actually Works (From Our Data + The Paper)

### The paper's hierarchy of intervention effectiveness:

| Intervention Type | ChatDev ProgramDev Improvement | ChatDev HumanEval Improvement |
|---|---|---|
| Prompt improvements | +9.4% | +0.7pp (0.8%) |
| Topology change (DAG → cyclic) | +15.6% | +1.9pp (2.1%) |

**Our result**: +0.0pp on HumanEval with prompt-only MAST defenses. Consistent with the paper's +0.7pp finding.

### Why topology > prompts:

Prompt defenses are **suggestions**. The model can ignore them. When `truncate_number` strongly implies decimal truncation, the model implements decimal truncation regardless of what SOUL.md says.

Structural defenses are **enforcement**. When the ChatDev topology requires CTO sign-off before delivery, the code literally cannot ship without it. When the system blocks premature completion, the agent cannot mark the task as done.

### What prompts CAN do (FC1 -- Specification/Roulette):

Our data shows prompts are most effective for the "forgetfulness" failure modes:
- **FM-1.3 (Step repetition)**: Anti-loop tags like `<LOOP-DETECTED>` work because the model just needs a reminder, not a behavior change
- **FM-1.5 (Unaware of termination)**: Termination conditions work as reminders on weak models
- **FM-2.2 (Fail to ask clarification)**: The `<CLARIFY>` tag prompts a behavior the model is already capable of

These work because the model WANTS to do the right thing but forgets. Prompts serve as reminders, not enforcers.

### What prompts CANNOT do (FC2/FC3):

- **FM-1.1 (Disobey task spec)**: The model reads the spec, understands it, and implements something different anyway due to strong naming/type priors. No amount of "NEVER implement based on function name" prevents this.
- **FM-3.2 (No/incomplete verification)**: The model can't execute code. Telling it to "verify before delivery" produces superficial checks, not actual test execution.
- **FM-3.3 (Incorrect verification)**: The model verifies against hints in the problem statement, not against edge cases. "Never trust hints" doesn't override the model's tendency to use available information.

These fail because the model needs capabilities it doesn't have (code execution, spec formalization, independent test generation), not reminders.

---

## Costs of Prompt-Only Defenses

| Cost | Impact |
|---|---|
| Token overhead | +80% prompt text per role (2,942 → 5,310 chars in ChatDev) |
| Latency | More tokens = slower inference, especially on local models |
| Context noise | Irrelevant defense instructions dilute the actual task context |
| Regression risk | Claude regressed 1 mode (FM-1.4) with MAST -- adding instructions can actively hurt |
| False confidence | 14/14 static audit and 100% trigger pass rate look impressive but don't mean the system is actually more reliable |

---

## Honest Assessment of Our Artifacts

| Artifact | Current State | Actual Value |
|---|---|---|
| `skills/mast-taxonomy/` | 14 failure mode knowledge base | **Useful** -- the taxonomy and prevalence data are genuinely valuable for understanding where systems fail |
| `skills/mast-audit/` | Static keyword audit tool | **Limited** -- can tell you if defense keywords exist, not if they work. Best used as a quick checklist, not a validation |
| `skills/agent-workspace-interview/` | Generates 6-file config suite (SOUL.md etc.) | **Not effective for FC2/FC3** -- the generated configs are primarily prompt suggestions. Some FC1 defenses (anti-loop, clarification) have limited value |
| `mcp/mast-enforce/` | MCP server with 3 tools | **Right direction, unvalidated** -- `verify_code()`, `check_completion()`, `generate_edge_cases()` are structurally correct but have never been integrated into a real agent loop |
| Config suite (6 files) | SOUL.md, RULES.md, PROMPT.md, MEMORY.md, BOOTSTRAP.md, USER.md | **Overweight** -- 6 files of prompt suggestions add cost with no proven benefit. Should be replaced with a minimal single-file containing only FC1 reminders |
| `tests/test_harness.py` | Failure injection test | **Useful for FC1** -- catches whether anti-loop/clarification prompts are present. Should not be used as evidence of real defense effectiveness |
| ChatDev YAML configs | MAST-hardened workflow | **Zero proven value** -- identical task completion to baseline |

---

## What We Confirmed (That IS a Contribution)

1. **Prompt-only defenses produce zero improvement on real task completion** -- we ran the experiment the community hadn't (most MAST implementations only test synthetic triggers)
2. **The paper's hierarchy (topology > prompts) is correct** -- our +0.0pp result is consistent with their +0.7pp finding
3. **Synthetic trigger pass rate is a misleading metric** -- 14/14 on triggers vs 3/5 on tasks shows a massive gap between component and system tests
4. **MAST-Lite (compressed rules) actively hurts** -- 7/14 vs baseline 8/14. Vague suggestions are worse than no defense
5. **Strong models don't need MAST prompts** -- GPT-4o baseline already passes 12/14 modes. The defenses target the model's weakness, which strong models don't have