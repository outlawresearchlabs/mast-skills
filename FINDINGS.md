# MAST Skills: Experimental Findings

## TL;DR

Prompt-only MAST defenses are unreliable -- they can help or hurt depending on the model. On strong models (GPT-4o), verbose MAST prompts are actively harmful (-18pp). On weaker models (Gemma4), even minimal prompts can interfere (-4pp). Structural enforcement via MCP tool calls is architecturally sound but adds unacceptable latency. The viable path is in-process Python middleware: same structural guarantees, zero LLM roundtrips.

---

## Benchmark Results (25 HumanEval problems x 2 reps = 50 trials each)

### GPT-4o (OpenAI API)

| Config | Score | Rep1 | Rep2 | Delta vs Baseline |
|---|---|---|---|---|
| Baseline | 44/50 (88.0%) | 23/25 (92%) | 21/25 (84%) | -- |
| MAST (verbose prompts) | 35/50 (70.0%) | 18/25 (72%) | 17/25 (68%) | **-18.0pp** |
| Lean (minimal verify prompt) | 45/50 (90.0%) | 23/25 (92%) | 22/25 (88%) | **+2.0pp** |

### Gemma4:31b-cloud (Ollama cloud inference)

| Config | Score | Rep1 | Rep2 | Delta vs Baseline |
|---|---|---|---|---|
| Baseline | 49/50 (98.0%) | 25/25 (100%) | 24/25 (96%) | -- |
| MAST (verbose prompts) | 48/50 (96.0%) | 24/25 (96%) | 24/25 (96%) | **-2.0pp** |
| Lean (minimal verify prompt) | 47/50 (94.0%) | 23/25 (92%) | 24/25 (96%) | **-4.0pp** |

### Summary Table

| Model | Baseline | MAST | Lean |
|---|---|---|---|
| GPT-4o | 88.0% | 70.0% (-18pp) | 90.0% (+2pp) |
| Gemma4 | 98.0% | 96.0% (-2pp) | 94.0% (-4pp) |

### MCP Structural Enforcement: Untestable

We could not benchmark MCP-based structural enforcement. A single HumanEval problem timed out at 900s. Each MCP tool call adds seconds of LLM -> subprocess -> LLM roundtrip. This made the approach operationally infeasible for benchmarking.

**Important caveat**: This reflects our implementation quality, not the MCP protocol itself. A well-optimized MCP server (persistent process, caching, async) would be faster. However, even with perfect MCP implementation, enforcement via tool calls fundamentally requires LLM roundtrips that in-process middleware does not.

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

**What it measures**: Whether a model resists a deliberately crafted failure trigger prompt when the config tells it not to.

**Why it's misleading**:
- The test PROMPTS the model to fail, then checks if the CONFIG told it not to. The model's compliance with the config is what's measured, not whether the defense works in practice.
- On strong models (GPT-4o, Claude), the baseline already passes most modes without MAST. MAST adds nothing.
- On weak models (gemma4), the model is suggestible -- it follows config instructions because it follows most instructions. This is not a defense property; it's a model property.
- MAST-Lite (compressed rules) actively UNDERPERFORMS baseline. This means the defense effectiveness depends on prompt length/format, not defense content.

### Level 3: Whole-System Validation (actual task completion)

**This is the only test that matters.** Results are in the benchmark tables above.

---

## What the Data Shows

### Finding 1: MAST prompts are actively harmful on strong models

GPT-4o with MAST verbose prompts dropped from 88% to 70% (-18pp). The failure modes introduced by MAST:
- 5 instances of FM-1.1 (no code produced) -- the model spent so many tokens on following MAST protocols that it failed to produce code
- 9 instances of syntax/extraction errors -- backslash continuations, unterminated strings, and other formatting artifacts from verbose prompt compliance

This is not random noise. MAST adds ~80% more prompt text per role (2,942 -> 5,310 chars in ChatDev). On a strong model that already knows how to code, this dilutes the task context with irrelevant defense instructions.

### Finding 2: Prompt effects are model-dependent and unpredictable

Same intervention, opposite effects:
- MAST prompts on GPT-4o: **-18pp** (harmful)
- MAST prompts on Gemma4: **-2pp** (negligible)
- Lean prompts on GPT-4o: **+2pp** (slightly helpful)
- Lean prompts on Gemma4: **-4pp** (harmful)

There is no prompt configuration that reliably improves all models. The sign and magnitude of the effect depend on model capability, prompt verbosity, and task difficulty. This makes prompt-based defenses fundamentally unreliable as a safety mechanism.

### Finding 3: MCP structural enforcement is the right concept, wrong mechanism

ChatDev's `state_gate_manager.py` checks `execution_context.global_state["verify_code_result"]`. The MCP approach sets this state via expensive LLM -> tool call -> LLM roundtrips. In our testing, this caused 900s timeouts on a single problem.

Our MCP implementation was not optimized (subprocess per call, no caching). A better implementation would be faster. But even with perfect MCP, enforcement via tool calls requires:
1. The LLM to decide to call the tool (agency dependency)
2. Token generation for the tool call
3. Context feeding the result back

In-process middleware eliminates all three by running verification as Python code inside the pipeline, setting `global_state` programmatically in milliseconds.

### Finding 4: The paper's hierarchy (topology > prompts) is confirmed

The paper found prompt improvements +0.7pp vs topology changes +1.9pp on ChatDev HumanEval. Our results are consistent:
- Prompt-only interventions: range from -18pp to +2pp (unpredictable, model-dependent)
- Structural enforcement (conceptually): the only approach that can provide reliable guarantees

But "structural" must mean in-process programmatic enforcement, not MCP tool calls or prompt-based keyword gates.

---

## Costs of Prompt-Only Defenses

| Cost | Impact |
|---|---|
| Token overhead | +80% prompt text per role (2,942 -> 5,310 chars in ChatDev) |
| Latency | More tokens = slower inference, especially on local models |
| Context noise | Irrelevant defense instructions dilute the actual task context |
| Regression risk | -18pp on GPT-4o, -4pp on Gemma4 with lean. Adding instructions can actively hurt |
| False confidence | 14/14 static audit and 100% trigger pass rate look impressive but don't mean the system is actually more reliable |

---

## What We Confirmed (That IS a Contribution)

1. **Prompt-only defenses are not just zero-effect -- they can be actively harmful** -- we demonstrated -18pp on GPT-4o with MAST prompts. The community has not widely tested this.
2. **The effect is model-dependent and unpredictable** -- same prompt helps GPT-4o (+2pp lean) but hurts Gemma4 (-4pp lean). No universal safe prompt exists.
3. **The paper's hierarchy (topology > prompts) is correct** -- our data confirms prompts are unreliable, structure is needed.
4. **MCP-based structural enforcement has practical issues** -- our implementation was too slow (900s timeouts), but even with better implementation, tool-call-based enforcement requires LLM roundtrips and model agency that in-process middleware does not.
5. **In-process middleware is the viable path** -- programmatically enforcing constraints in the pipeline (setting `global_state` directly) provides structural guarantees without any LLM overhead or model compliance dependency.

---

## Honest Assessment of Our Artifacts

| Artifact | Current State | Actual Value |
|---|---|---|
| `skills/mast-taxonomy/` | 14 failure mode knowledge base | **Useful** -- the taxonomy and prevalence data are genuinely valuable for understanding where systems fail |
| `skills/mast-audit/` | Static keyword audit tool | **Limited** -- can tell you if defense keywords exist, not if they work. Best used as a quick checklist, not a validation |
| `skills/agent-workspace-interview/` | Generates 6-file config suite (SOUL.md etc.) | **Not effective** -- the generated configs are prompt suggestions that help some models and hurt others |
| `mcp/mast-enforce/` | MCP server with 3 tools | **Right concept, wrong mechanism** -- verification is structurally correct but tool-call roundtrips are too slow. Should be reimplemented as in-process middleware |
| Config suite (6 files) | SOUL.md, RULES.md, PROMPT.md, MEMORY.md, BOOTSTRAP.md, USER.md | **Harmful on strong models** -- 6 files of prompt suggestions add cost and can reduce performance. Replace with in-process enforcement |
| `tests/test_harness.py` | Failure injection test | **Useful for FC1** -- catches whether anti-loop/clarification prompts are present. Should not be used as evidence of real defense effectiveness |
| ChatDev YAML configs | MAST-hardened workflow | **Harmful on strong models** -- -18pp on GPT-4o. Lean config slightly helpful on GPT-4o (+2pp) but harmful on Gemma4 (-4pp) |

---

## The Path Forward: In-Process Middleware

### Why not prompts?
Prompts are suggestions the model can ignore. They're also noise the model might follow instead of the task. The effect is unpredictable across models.

### Why not MCP tool calls?
1. Latency: each tool call adds seconds of LLM -> subprocess -> LLM roundtrip
2. Agency dependency: the model must decide to call the tool and call it correctly
3. Our implementation was slow, but even a perfect MCP implementation has fundamental overhead from LLM roundtrips

### Why in-process middleware?
1. **Zero latency**: verification runs as Python code in milliseconds
2. **Zero agency dependency**: the model doesn't need to call anything -- verification runs automatically
3. **Structural guarantees**: state gates block progression until verification passes, regardless of model behavior
4. **Arbitrarily complex checks**: AST parsing, import validation, parameter matching, test execution -- all as Python, no LLM needed for the check itself

### How it works in ChatDev

ChatDev has `state_gate_manager.py` that checks `execution_context.global_state["verify_code_result"]`. Currently this is set by MCP tool calls (slow). In-process middleware would:

1. Hook into ChatDev after each code generation step
2. Run Python verification (signature matching, test extraction, syntax validation, test execution)
3. Set `global_state["verify_code_result"]` directly
4. State gates enforce pass/fail -- no LLM involvement in the verification step

This is not a model training issue -- it's an architecture issue. We don't need to train models to be better at following safety instructions. We need to build systems where safety is structurally enforced regardless of what the model wants to do.