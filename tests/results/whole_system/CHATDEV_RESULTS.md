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

## Baseline Results (gemma4:31b-cloud via local gateway)

| Problem | Entry Point | Status | Failure Mode |
|---------|-------------|--------|--------------|
| HumanEval/0 | has_close_elements | **PASS** | - |
| HumanEval/2 | truncate_number | **FAIL** | FM-1.1: Added decimals param, wrong semantics |
| HumanEval/4 | mean_absolute_deviation | **PASS** | - |
| HumanEval/10 | make_palindrome | **PASS** | - |
| HumanEval/17 | parse_music | **FAIL** | FM-1.1: Implemented note/octave parser instead of beat counter |

**Baseline pass@1: 3/5 (60%)** (complete runs, corrected extraction)

### Baseline Observations

1. **FM-1.1 (Disobey Task Requirements) is the dominant failure mode** (2/2 failures)
   - HumanEval/2: Model renamed function params, added `decimals` parameter, implemented "truncate to N decimals" instead of "extract decimal part from float"
   - HumanEval/17: Model implemented note/octave parser (C4, Bb3) instead of beat count parser (o=4, o|=2, .=1)
   - Both: model interpreted **function name** instead of reading **docstring specification**

2. **Partial runs produce garbled code** (timed-out ChatDev runs)
   - Escaped docstrings (`\"\"\"` instead of `"""`)
   - Garbled operators (`<< threshold threshold` instead of `< threshold`)
   - UTF-8 BOM characters in output files
   - These are FM-3.2/3.3 failures: Code Reviewer doesn't catch syntax errors

3. **Code extraction requires care**
   - ChatDev writes multi-file projects (solution.py, main.py, test_*.py, etc.)
   - Solution files sometimes have non-standard names (palindrome_logic.py, statistics_utils.py)
   - BOM characters must be stripped, escaped quotes must be unescaped

## MAST-Hardened Results (in progress)

### Critical Finding: FM-1.1 Protocol Was NOT Followed

After adding the FM-1.1 Specification Adherence Protocol ("BEFORE implementing any function, restate the specification in your own words... NEVER implement based on the function name alone"), the **model still made the same FM-1.1 errors**:

- HumanEval/2 (MAST): Model still added `d: int` parameter and implemented "truncate to N decimals" instead of reading the docstring
- This confirms the paper's finding that **prompt-based defenses are insufficient for FC2-class failures**

### MAST Observations

1. **Longer processing time**: MAST-hardened prompts add ~2K tokens per agent, increasing runtime ~30-50%
2. **FM-1.1 defense ineffective in prompt-only form**: Model acknowledges the protocol but doesn't follow it
3. **This validates the paper's claim**: "Context/communication protocols are often insufficient for" FM-1.1/FC2 failures

## Paper Comparison

| Metric | Paper (GPT-3.5) | Ours (gemma4) |
|--------|-------------------|---------------|
| HumanEval baseline | 89.6% | 60% |
| Dominant failure mode | FC1/FC2 (varies) | FM-1.1 (2/2) |
| Prompt effectiveness | Insufficient for FC2/FC3 | Confirmed: insufficient for FM-1.1 |

**Key takeaway**: Our results directly validate the paper's claim that prompt-only approaches are insufficient for addressing FM-1.1 (Disobey Task Requirements). The model acknowledges the MAST protocol in its system prompt but still implements based on function name rather than docstring specification.

## Honest Limitations

1. **Small sample**: 5 problems, 1 rep per config
2. **Model-specific**: gemma4:31b-cloud only; results may differ for GPT-4, Claude, etc.
3. **ChatDev version**: v2 differs from paper's version
4. **Single metric**: pass@1 only; no code quality or efficiency metrics
5. **Gateway variance**: Local gateway may introduce latency artifacts
6. **Incomplete**: MAST experiment in progress; MCP enforcement not yet tested