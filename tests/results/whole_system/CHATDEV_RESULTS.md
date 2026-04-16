# ChatDev Whole-System Validation Results

## Final Results (5 shared HumanEval problems)

**Model**: gemma4:31b-cloud via local Ollama-compatible gateway

### Head-to-Head Comparison

| Problem | Entry Point | Baseline | MAST | Delta |
|---------|-------------|----------|------|-------|
| HumanEval/0 | has_close_elements | PASS | PASS | SAME |
| HumanEval/2 | truncate_number | **FAIL** | **FAIL** | SAME |
| HumanEval/4 | mean_absolute_deviation | PASS | PASS | SAME |
| HumanEval/10 | make_palindrome | PASS | PASS | SAME |
| HumanEval/17 | parse_music | **FAIL** | **FAIL** | SAME |

**Baseline pass@1: 3/5 (60%)**
**MAST pass@1: 3/5 (60%)**
**Improvement: 0/5 (ZERO)**

### Failure Mode Analysis

All failures in both configs are **FM-1.1 (Disobey Task Requirements)**:

| Problem | Baseline Failure | MAST Failure |
|---------|-----------------|--------------|
| HumanEval/2 | Added `decimals` param, implemented truncation-to-N-decimals instead of extracting decimal part | Added `d` param, implemented truncation-to-N-decimals **(identical FM-1.1 error)** |
| HumanEval/17 | Implemented note/octave parser (C4, Bb3) instead of beat counter (o=4, o\|=2, .=1) | Produced no code at all (empty code_workspace) **(worse outcome)** |

### Critical Finding

**FM-1.1 "Specification Adherence Protocol" produced ZERO improvement.**

The MAST-hardened config includes:
> "BEFORE implementing any function, restate the specification in your own words. Identify: (1) What the function MUST do per the docstring, (2) What the function MUST NOT do, (3) The exact return type and value. If your restatement differs from the specification, STOP and re-read the specification. NEVER implement based on the function name alone -- always implement based on the docstring and examples provided."

Despite this instruction, the model:
1. Did NOT restate the specification
2. Did NOT identify what the function must do per the docstring
3. DID implement based on the function name alone
4. The FM-1.1 error on HumanEval/2 was **identical** in both configs

### What This Validates

1. **Paper's Finding 3** (Section 5): "Context/communication protocols are often insufficient" for FC2-class failures
2. **Our 8-gap analysis (Gap #2)**: Prompt insufficiency for specification adherence
3. **Paper's Section 5.2**: ChatDev prompt improvement was only +0.7pp (89.6% → 90.3%) -- statistically negligible
4. **The need for structural enforcement**: MCP tools that validate code against specifications are necessary

### Paper Comparison

| Metric | Paper (GPT-3.5) | Ours (gemma4) |
|--------|-------------------|---------------|
| HumanEval baseline | 89.6% | 60% |
| HumanEval with prompts | 90.3% (+0.7pp) | 60% (+0.0pp) |
| Dominant failure mode | FC1/FC2 (varies) | FM-1.1 (100%) |
| Most effective fix | Topology change (+1.9pp) | Not tested |

The lower absolute numbers (60% vs 89.6%) reflect the weaker model (gemma4:31b-cloud vs GPT-3.5-turbo). The key finding is the **zero relative improvement** from prompt defenses, which is consistent with the paper's small +0.7pp finding (within noise).

### Additional Observations

1. **ChatDev output quality varies between runs** -- same prompt, same config, different results
2. **Partial runs (timeouts) produce garbled code** -- escaped docstrings, garbled operators, BOM chars
3. **MAST prompts increase processing time ~30-50%** (avg 421s vs ~300s per problem)
4. **Code extraction requires care** -- BOM stripping, quote unescaping, non-standard filenames
5. **HumanEval/17 MAST produced NO code** -- the model failed to generate any implementation

## Honest Limitations

1. **Small sample**: 5 problems per config; no error bars or statistical significance
2. **Model-specific**: gemma4:31b-cloud only; results may differ for GPT-4, Claude, etc.
3. **ChatDev version**: We use ChatDev v2 which differs from the paper's version
4. **Single metric**: pass@1 only; no code quality or efficiency metrics
5. **One dominant failure mode**: All failures are FM-1.1; can't generalize to other modes
6. **Gateway latency**: Local gateway may affect multi-agent coordination quality
7. **FM-1.1 may be model-specific**: Stronger models may better follow FM-1.1 protocols
8. **No topology change test**: Paper's most effective intervention (+15.6%) not tested here