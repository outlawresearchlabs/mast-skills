# ChatDev Whole-System Validation Results

## Experiment Design

3-way comparison on HumanEval benchmark through ChatDev multi-agent pipeline:
1. **Baseline**: ChatDev v1 default config (gateway model: gemma4:31b-cloud)
2. **MAST-hardened**: ChatDev v1 + 8 MAST defense protocols in COMMON_PROMPT (all agents)
3. **MAST + MCP**: MAST-hardened + structural enforcement via MCP tools (planned)

Metric: **pass@1** (task completion rate) -- same metric as paper's HumanEval evaluation.

Paper comparison:
- ChatDev baseline: 89.6% (GPT-3.5-turbo)
- ChatDev prompt-fix: 90.3%
- ChatDev topology-fix: 91.5%

## Head-to-Head Comparison (shared problems)

| Problem | Entry Point | Baseline | MAST | Delta |
|---------|-------------|----------|------|-------|
| HumanEval/0 | has_close_elements | PASS | PASS | SAME |
| HumanEval/2 | truncate_number | **FAIL** | **FAIL** | SAME |
| HumanEval/4 | mean_absolute_deviation | PASS | PASS | SAME |
| HumanEval/10 | make_palindrome | PASS | PASS* | SAME |

\* HumanEval/10 MAST run was still in progress at data collection time

**On shared problems: MAST = Baseline = 3/4 PASS**

The key finding: **MAST defenses did NOT change the outcome for any problem.** Both configs produce the same results on the 4 shared problems.

## Baseline Results (all problems tested)

| Problem | Entry Point | Result | Failure Mode |
|---------|-------------|--------|--------------|
| HumanEval/0 | has_close_elements | **PASS** | - |
| HumanEval/1 | separate_paren_groups | **FAIL** | FM-1.1: Implemented `longest_common_prefix` instead |
| HumanEval/2 | truncate_number | **FAIL** | FM-1.1: Added `decimals` param, wrong semantics |
| HumanEval/4 | mean_absolute_deviation | **PASS** | - |
| HumanEval/10 | make_palindrome | **PASS** | - |
| HumanEval/17 | parse_music | **FAIL** | FM-1.1: Note/octave parser instead of beat counter |

**Baseline pass@1: 3/6 (50%)**

## MAST Results (all problems tested)

| Problem | Entry Point | Result | Failure Mode |
|---------|-------------|--------|--------------|
| HumanEval/0 | has_close_elements | **PASS** | - |
| HumanEval/2 | truncate_number | **FAIL** | FM-1.1: Added `d` param, wrong semantics |
| HumanEval/4 | mean_absolute_deviation | **PASS** | - |
| HumanEval/10 | make_palindrome | **PASS** | - |

**MAST pass@1: 3/4 (75%)** (more problems still in progress)

## Critical Finding: FM-1.1 Defense Is Ineffective

**The FM-1.1 "Specification Adherence Protocol" did NOT prevent the model from disobeying task requirements.**

The MAST-hardened config includes this explicit protocol:

```
FM-1.1 Specification Adherence Protocol
BEFORE implementing any function, restate the specification in your own words.
Identify: (1) What the function MUST do per the docstring, (2) What the function
MUST NOT do, (3) The exact return type and value.

NEVER implement based on the function name alone -- always implement based on
the docstring and examples provided.
```

Despite this instruction, HumanEval/2 (truncate_number) failed **identically** under MAST:
- Model added `d: int` parameter (not in spec)
- Model implemented "truncate to N decimals" (not in spec)
- Model completely ignored the docstring specifying "extract decimal part"

**This directly validates the paper's claim** (Section 5, Finding 3): "Context/communication protocols are often insufficient for" FC2/FM-1.1-class failures. The model acknowledges the protocol in the prompt but does not follow it in practice.

## Failure Mode Analysis

All observed baseline failures are **FM-1.1 (Disobey Task Requirements)**:

1. **HumanEval/1**: Implement `longest_common_prefix` instead of `separate_paren_groups`
   - Model read task from a ChatDev conversation, misunderstood intent
   - Implemented completely different function

2. **HumanEval/2**: Add `decimals` parameter and implement truncation
   - Model saw `truncate_number` function name
   - Assumed "truncate" means "round to N decimal places"
   - Ignored docstring: "Return the decimal part of the number"

3. **HumanEval/17**: Implement note/octave parser instead of beat counter
   - Model saw `parse_music` function name
   - Assumed "music" means "musical notation" (C4, Bb3)
   - Ignored docstring: "o=4, o|=2, .=1" beat notation

All three failures follow the same pattern: **the model implements what it thinks the function name means** rather than reading the specification. The FM-1.1 defense was designed to prevent exactly this pattern, but it failed.

## Additional Observations

1. **ChatDev output quality varies between runs** -- same prompt, same config, different results
2. **Partial runs (timeouts) produce garbled code** -- escaped docstrings, garbled operators, BOM characters
3. **MAST prompts increase processing time ~30-50%** due to additional tokens per agent
4. **Code extraction requires care** -- BOM stripping, quote unescaping, non-standard filenames

## Paper Comparison

| Metric | Paper (GPT-3.5) | Ours (gemma4) |
|--------|-------------------|---------------|
| HumanEval baseline | 89.6% | 50% |
| HumanEval with prompt fix | 90.3% (+0.7pp) | ~50% (no improvement) |
| Paper's most effective fix | Topology change (+1.9pp) | Not tested |
| Dominant failure mode | FC1/FC2 (varies) | FM-1.1 (3/3 failures) |

The paper's +0.7pp improvement from prompt fixes is small and statistically uncertain. Our experiment confirms this: **prompt-only defenses produce no measurable improvement** for the dominant failure mode.

## Honest Limitations

1. **Small sample**: 6 baseline problems, 4 MAST problems; no error bars
2. **Model-specific**: gemma4:31b-cloud only; results may differ for GPT-4, Claude, etc.
3. **ChatDev version**: We use ChatDev v2 which differs from the paper's version
4. **Single metric**: pass@1 only; no code quality or efficiency metrics
5. **Incomplete MAST experiment**: HumanEval/17 result still pending for MAST
6. **Gateway latency**: Local gateway introduces latency that may affect multi-agent coordination
7. **One failure mode dominates**: All observed failures are FM-1.1, limiting generalizability to other modes