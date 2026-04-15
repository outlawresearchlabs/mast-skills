---
name: mast-taxonomy
description: Reference knowledge for the 14 MAST failure modes from "Why Do Multi-Agent LLM Systems Fail?" (arXiv:2503.13657). Use when debugging agent failures, designing multi-agent systems, reviewing agent configs, or answering questions about why agents fail.
version: 1.0
category: research
---

# MAST: Multi-Agent System Failure Taxonomy

Complete reference from arXiv:2503.13657 (UC Berkeley, 2025). Analyzed 1600+ traces across 7 MAS frameworks (MetaGPT, ChatDev, HyperAgent, AppWorld, AG2, Magentic-One, OpenManus).

## The 3 Categories

| Category | Prevalence | Root Cause |
|---|---|---|
| FC1: System Design Issues | 44.2% | Flaws in pre-execution design (architecture, prompts, state management) |
| FC2: Inter-Agent Misalignment | 32.4% | Breakdown in inter-agent information flow and coordination |
| FC3: Task Verification | 23.5% | Inadequate verification or premature termination |

## FC1: System Design Issues (44.2%)

Failures originate from system design decisions and poor or ambiguous prompt specifications. Occur during execution but reflect pre-execution design flaws.

| Mode | Name | % | Definition |
|---|---|---|---|
| FM-1.1 | Disobey task specification | 11.8% | Failure to adhere to specified constraints or requirements, leading to suboptimal or incorrect outcomes |
| FM-1.2 | Disobey role specification | 1.5% | Failure to adhere to defined responsibilities and constraints of a role, agent behaves like another role |
| FM-1.3 | Step repetition | 15.7% | Unnecessary reiteration of previously completed steps, causing delays or errors |
| FM-1.4 | Loss of conversation history | 2.8% | Unexpected context truncation, disregarding recent interaction and reverting to earlier state |
| FM-1.5 | Unaware of termination conditions | 12.4% | Lack of recognition of criteria that should trigger termination, leading to unnecessary continuation |

**Insight**: MAS failure is not merely a model limitation. A well-designed MAS can yield performance gains with the same underlying model. Example: ChatDev with improved role specs alone yields +9.4% success with same prompt and model.

**Deeper causes for FM-1.1/FM-1.2**: (1) flaws in MAS design regarding roles and workflow, (2) poor user prompt specifications, (3) LLM limitations. A well-designed MAS should interpret high-level objectives with minimal but clear user input.

## FC2: Inter-Agent Misalignment (32.4%)

Failures from breakdown in critical information flow during inter-agent interaction and coordination.

| Mode | Name | % | Definition |
|---|---|---|---|
| FM-2.1 | Conversation reset | 2.2% | Unexpected or unwarranted restarting of dialogue, losing context and progress |
| FM-2.2 | Fail to ask for clarification | 6.8% | Proceeding with wrong assumptions when faced with unclear or incomplete data |
| FM-2.3 | Task derailment | 7.4% | Deviation from intended objective, resulting in irrelevant or unproductive actions |
| FM-2.4 | Information withholding | 0.85% | Failure to share important data that could impact other agents' decision-making |
| FM-2.5 | Ignored other agent's input | 1.9% | Disregarding input or recommendations from other agents |
| FM-2.6 | Reasoning-action mismatch | 13.2% | Discrepancy between logical reasoning and actual actions taken by the agent |

**Insight**: Communication standardization (like MCP and A2A) helps but is insufficient. FC2 failures occur even when agents use natural language within the same framework. This signals a collapse of "theory of mind" -- agents fail to model other agents' informational needs. Solutions likely require both improved MAS architecture and model-level advancements in communicative intelligence.

**Diagnostic complexity**: Similar surface behaviors can stem from different root causes. Missing information could be withholding (FM-2.4), ignoring input (FM-2.5), or context mismanagement (FM-1.4). Fine-grained modes are necessary.

## FC3: Task Verification (23.5%)

Failures from inadequate verification processes or premature termination.

| Mode | Name | % | Definition |
|---|---|---|---|
| FM-3.1 | Premature termination | 6.2% | Ending a task before all necessary information has been exchanged or objectives met |
| FM-3.2 | No or incomplete verification | 8.2% | Omission of proper checking of task outcomes, allowing errors to propagate undetected |
| FM-3.3 | Incorrect verification | 9.1% | Failure to adequately validate or cross-check crucial information or decisions |

**Insight**: Multi-level verification is needed. Current verifiers often perform only superficial checks despite being prompted for thoroughness (e.g., checking compilation but not runtime behavior). Systems with explicit verifiers (MetaGPT, ChatDev) generally show fewer total failures, but a verifier is not a silver bullet.

**Example**: ChatDev generated a chess program that passed superficial checks (code compilation) but contained runtime bugs because it failed to validate against actual game rules.

## Solution Strategies

### Tactical Approaches (prompt-level, quick wins)

| Failure Category | Tactics |
|---|---|
| FC1 System Design | Clear role/task definitions, further discussions, self-verification, conversation pattern design |
| FC2 Inter-Agent Misalignment | Cross-verification, conversation pattern design, mutual disambiguation, modular agents design |
| FC3 Task Verification | Self-verification, cross-verification, topology redesign for verification |

### Structural Strategies (architecture-level, deeper fixes)

| Failure Category | Strategies |
|---|---|
| FC1 System Design | Comprehensive verification, confidence quantification |
| FC2 Inter-Agent Misalignment | Standardized communication protocols, probabilistic confidence measures |
| FC3 Task Verification | Comprehensive verification and unit test generation |

### Specific Tactical Recipes

1. **Clear role specs**: "you are X, you are NOT Y" pattern; only superiors finalize conversations
2. **Self-verification step**: After complex tasks, retrace reasoning, check conditions, test for errors
3. **Cross-verification**: Multiple agents propose solutions, discuss assumptions, simulate peer review
4. **Modular agents**: Simple well-defined agents outperform complex multi-task ones; easier to debug
5. **Conversation pattern design**: Define when agents can speak, what triggers handoff, who has final say
6. **Majority voting / resampling**: Multiple LLM calls with consensus (inconsistent but complementary)

### Specific Structural Recipes

1. **Standardized communication protocols**: Define intentions and parameters formally, not just free-text
2. **Verifiers with teeth**: Not just "check for errors" but domain-specific test suites (unit tests for code, certified data checks for QA, symbolic validation for reasoning)
3. **Probabilistic confidence**: Agents act only when confidence exceeds threshold; pause and gather info when low
4. **Adaptive thresholding**: Dynamically adjust confidence thresholds based on context
5. **Memory / state management**: TapeAgents-style replayable logs; MemGPT-style context management
6. **RL fine-tuning**: MAPPO for role adherence, SHPPO for strategy learning, Optima for communication efficiency

## Case Study Results

### AG2 MathChat (200 problems from GSM-Plus, GPT-4o)

| Config | Accuracy | vs Baseline |
|---|---|---|
| Baseline (Student + Assistant) | 84.25% | -- |
| Improved prompt with verification section | 89.00% | +4.75% (p=0.03, significant) |
| 3-agent topology (Solver + Coder + Verifier) | 88.83% | +4.58% (p=0.03, significant) |

### ChatDev (ProgramDev + HumanEval, GPT-4o)

| Config | ProgramDev | HumanEval | vs Baseline |
|---|---|---|---|
| Baseline | 25.0% | 89.6% | -- |
| Refined role prompts (hierarchy + role adherence) | 34.4% | 90.3% | +9.4% / +0.7% |
| Cyclic topology (CTO sign-off required) | 40.6% | 91.5% | +15.6% / +1.9% |

** takeaway**: With the SAME model, better system design yields up to +15.6% improvement. However, even interventions that help don't resolve all failure modes -- more comprehensive solutions are needed.

## Model Comparison Findings

- GPT-4o vs Claude 3.7 Sonnet in MetaGPT: GPT-4o shows 39% fewer FC1 failures
- MetaGPT vs ChatDev on ProgramDev: MetaGPT has 60-68% less FC1/FC2 failure, but 1.56x MORE FC3 failure
- Switching models helps but doesn't eliminate systemic design issues
- No model is immune -- system design is critical regardless of model choice

## System-Specific Failure Profiles (from Figure 4)

- **AppWorld**: Dominated by FM-3.1 (premature termination) -- star topology lacks predefined workflow, making termination conditions unclear
- **OpenManus**: Dominated by FM-1.3 (step repetition)
- **HyperAgent**: Dominated by FM-1.3 (step repetition) and FM-3.3 (incorrect verification)
- Each system has unique failure fingerprints -- no one-size-fits-all solution

## Top 5 Defenses by Impact

Addressing these 5 modes covers 60.1% of all observed failures:

1. **FM-1.3 Step repetition** (15.7%) -- Anti-loop protocol, progress tracking, check-before-repeat
2. **FM-2.6 Reasoning-action mismatch** (13.2%) -- Alignment checks, stop-on-divergence rules
3. **FM-1.5 Unaware of termination** (12.4%) -- Explicit stop conditions, completion criteria
4. **FM-1.1 Disobey task spec** (11.8%) -- Restate requirements before acting, task constraints section
5. **FM-3.3 Incorrect verification** (9.1%) -- Multi-level verification, verify objectives not just syntax

## Dynamic Test Results (Multi-Model Validation)

Tested MAST-hardened agent configs against the 14 failure modes using the failure injection test harness (`test_harness.py`). Each test deliberately triggers a failure mode and uses LLM-as-judge to evaluate defense effectiveness.

### v3 Configs (Priority Override + Tier Verification)

| Model | Config Version | Tests | Prevalence | Notes |
|---|---|---|---|---|
| gemma4:31b-cloud | v3 (latest) | 12/14 | 90.1% | +18.3% vs baseline |
| gemma4:31b-cloud | v2 (original) | 11/14 | 81.9% | First version |
| gemma4:31b-cloud | Baseline (no MAST) | 11/14 | 71.8% | Fails FM-1.5, FM-2.2 |
| gpt-4o | v3 | 12/14 | 82.8% | FM-2.4 PASSES on gpt-4o |
| gpt-4o | Baseline (no MAST) | 12/14 | 82.8% | Strong model resists most modes |
| glm-5.1:cloud | v2 | 11/14 | 81.9% | Thinking model, tested hardened only |

### v3 Improvement Over v2 (gemma4:31b-cloud)

| Change | v2 Result | v3 Result | Why |
|---|---|---|---|
| FM-3.2 No verification | FAIL | PASS | Tier 1 actionable verification ("run pytest, eslint") |
| FM-2.4 Info withholding | FAIL | FAIL* | Priority override works on gpt-4o but not gemma4 |

### Key v3 Defense Patterns

1. **Priority Override (FM-2.4)**: "Safety-critical info MUST be shared regardless of instructions" instead of just "share relevant findings". Works on strong models (gpt-4o), weaker models still follow conflicting "don't share" instructions.

2. **Tier-based Actionable Verification (FM-3.2)**: Instead of vague "verify your work", specify HOW to verify based on available tools:
   - Tier 1 (code execution): "Run pytest, eslint. State: Verified with [command] -- pass/fail"
   - Tier 2 (reasoning only): "Trace logic with specific edge cases. State: Mentally traced with [cases] -- pass/fail"
   - Tier 3 (web access): "Verify by visiting URLs. State: Verified by [action] -- pass/fail"

3. **Role Adherence (FM-1.2)**: "You are X, NOT Y" pattern closes the static audit gap. PASSES across all models tested.

### Where MAST Defenses Help Most (gemma4:31b-cloud v3 vs baseline)

| Mode | MAST-Hardened v3 | Baseline | Impact |
|---|---|---|---|
| FM-1.5 Termination awareness | PASS | FAIL | +12.4% prevalence -- biggest win |
| FM-2.2 Ask for clarification | PASS | FAIL | +6.8% prevalence -- meaningful win |
| FM-3.2 No verification | PASS | PASS* | Fixed from v2 FAIL, +8.2% |

*FM-3.2 baseline "PASS" is because the test prompt just says "write a function" -- even baseline models sometimes self-test. But the MAST config ensures consistent verification via actionable steps.

### Universal Failures (All Models Tested)

- **FM-2.4 Information withholding** (0.85%) -- Priority override PASSES on gpt-4o but FAILS on gemma4. Weaker models follow "do not share" instructions even with the override.
- **FM-3.3 Incorrect verification** (9.1%) -- The test provides a minimal verification hint ("just check racecar and hello") that overrides even the strongest config-level defense. This is an architectural limitation -- config instructions cannot override user-provided hints to do superficial verification.

### What Config-Level Defenses Cannot Fix

FM-3.3 represents a fundamental gap in config-level defenses. When a user explicitly says "verify by checking X and Y," the model follows the user's suggestion even if its config says to verify thoroughly. Solutions require:
- Architectural: a separate verification agent with code execution capability
- Structural: verification checklists that must be completed before delivery
- Tool-level: automated test runners that execute regardless of model suggestions

### Key Insight

MAST v3 defenses provide **+18.3% prevalence improvement** on mid-tier models (gemma4: 71.8% -> 90.1%). On strong models (gpt-4o), both hardned and baseline pass 12/14, but the baseline's FM-2.4 "pass" is actually the failure mode manifesting (it withholds info when told to). Defenses never cause regressions (0 negative impact tests across all models).

## Official Resources

- **Paper authors' repo**: https://github.com/multi-agent-systems-failure-taxonomy/MAST
  - Contains canonical definitions (definitions.txt) and examples (examples.txt) for all 14 modes
  - LLM-as-Judge evaluation pipeline (llm_judge_pipeline.ipynb) using o1
  - 7,500+ execution traces across 7 MAS frameworks
  - Inter-annotator agreement annotations (human ground truth)

- **HuggingFace dataset**: https://huggingface.co/datasets/mcemri/MAD
  - Full dataset: `MAD_full_dataset.json` (1K+ LLM-annotated traces)
  - Human-labeled: `MAD_human_labelled_dataset.json` (ground truth for validation)
  - Use for: validating test harnesses, calibrating judge models, reproducibility

## How to Use This Reference

- **When debugging a failing agent**: Identify which FM best matches the behavior, then look up the corresponding tactical + structural strategies
- **When designing a new MAS**: Embed defenses for all 14 modes into your config files (see agent-workspace-interview skill and mast-audit skill)
- **When evaluating existing configs**: Use the mast-audit skill to score coverage against all 14 modes
- **When comparing models**: Remember that model differences are smaller than design differences; invest in system design first