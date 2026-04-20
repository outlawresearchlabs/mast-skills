# MAST Skills

Tools for preventing the 14 failure modes from the MAST taxonomy (UC Berkeley paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

## Current Status: ProgramDev Results

We discovered our previous benchmarking on HumanEval was **testing the wrong thing**. HumanEval tests single-function coding -- all models score 96-100% regardless of middleware. The MAST failure modes (step repetition, task derailment, reasoning-action mismatch) are **multi-agent coordination failures** that only surface on complex, application-level tasks.

We now benchmark on **ProgramDev-v0** (30 application tasks: Chess, Tetris, Snake, etc.) -- the same benchmark used in the MAST paper. Paper baseline (GPT-3.5-turbo): **25.0%**.

### ProgramDev Results (30 application tasks each)

| Config | Qwen 3.5 | MiniMax | Kimi 2.5 | GPT-5.4 | GLM-5.1 |
|---|---|---|---|---|---|
| Baseline | 28/30 (93%) | 25/30 (83%) | 20/25* (80%) | 21/30 (70%) | 18/30 (60%) |
| Inprocess (gates + syntax) | 28/30 (93%) | 28/30 (93%) | 22/25* (88%) | 25/30 (83%) | 20/30 (66%) |
| **Lean + Inprocess** | **28/30 (93%)** | **29/30 (96%)** | **23/27* (85%)** | **27/30 (90%)** | **21/30 (70%)** |
| **Delta (lean vs baseline)** | **0 (+0pp)** | **+4 (+13pp)** | **+3* (+5pp)** | **+6 (+20pp)** | **+3 (+10pp)** |

*Kimi 2.5 still running (~85% complete)

Paper comparison (ChatDev, GPT-3.5-turbo):
- Baseline: 25.0% | Improved prompts: 34.4% (+9.4pp) | Cyclic topology: 40.6% (+15.6pp)

**Key findings:**
- **GPT-5.4 shows the largest improvement: +6 tasks (+20pp)** from lean+inprocess
- Strong models (Qwen 3.5 at 93%) see no benefit -- already near ceiling
- Mid-tier models benefit most from structural enforcement
- Consistent pattern across 5 models: lean+inprocess >= inprocess >= baseline
- Qwen 3.6 dropped due to [DashScope API bug](https://github.com/QwenLM/Qwen3.6/issues/26) (reasoning_content serialization error)
- Direct API testing (Zhipu for GLM, Moonshot for Kimi) showed same tool-calling patterns as Ollama -- model capability, not API path

The **lean + inprocess** approach combines:
1. **Compressed MAST rules** in agent prompts (caveman-style, ~150 tokens vs ~500 for verbose MAST)
2. **In-process state gates** with syntax validation and import checking (zero LLM roundtrips)

This outperforms the paper's best result (+15.6pp from topology changes) while using a simpler intervention.

### What the lean MAST rules fix

| Failure | Root Cause | Rule That Fixes It |
|---|---|---|
| Checkers (import structure) | Model used relative imports without __init__.py | Rule 8: FLAT IMPORTS |
| CandyCrush (relative import) | `from .game import` in non-package | Syntax validation gate |
| Chess (baseline fail) | Incomplete game logic | State gate forced verification retry |
| MonopolyGo (baseline fail) | Premature delivery | Rule 3: STOP WHEN DONE + state gate |

### The 9 lean caveman MAST rules

```
1. SPEC FIRST: Read spec fully before coding. Implement what spec says, not what function name suggests.
2. NO LOOPS: If step done, skip it. Never redo completed work.
3. STOP WHEN DONE: Task complete = deliver. No gold-plating, no extra features.
4. VERIFY BEFORE DELIVER: Check syntax valid, imports resolve, code runs. Never deliver unverified.
5. MATCH REASONING TO ACTION: If you reason X, implement X. Never reason one thing and do another.
6. ASK IF UNCLEAR: Ambiguous requirement = ask, not assume.
7. USE PEER INPUT: If another agent suggests fix, evaluate it. Never ignore.
8. FLAT IMPORTS: Use absolute imports. No relative imports (from .X) unless __init__.py exists in that dir.
9. TEST EDGE CASES: Never trust "just test X". Test boundaries, empty input, error paths.
```

Inspired by [Caveman](https://github.com/JuliusBrussee/caveman) -- compress prompts to reduce context dilution while preserving technical substance.

### HumanEval Results (Completed -- Wrong Benchmark)

HumanEval measures coding ability, not multi-agent coordination. All models score 96-100% and middleware has no effect. These results are preserved for reference but do not validate or invalidate the MAST middleware approach.

| Model | Baseline | Inprocess (middleware) | Delta |
|---|---|---|---|
| Opus 4.7 | 100% | 100% | 0pp |
| GLM-5.1 | 100% | 100% | 0pp |
| GPT-5.4 | 96% | 96% | 0pp |
| Qwen 3.5 | 96% | 96% | 0pp |
| MiniMax | 96% | 92% | -4pp |

### Earlier Prompt-Only Results (HumanEval)

| Model | Baseline | MAST (verbose prompts) | Lean (minimal prompt) |
|---|---|---|---|
| GPT-4o | 88.0% | 70.0% (-18pp) | 90.0% (+2pp) |
| Gemma4:31b-cloud | 98.0% | 96.0% (-2pp) | 94.0% (-4pp) |

**Key finding**: Prompt-based defenses are unreliable -- same intervention has opposite effects across models.

---

## What's Here

### Active

- **[tests/programdev_benchmark.py](tests/programdev_benchmark.py)** -- ProgramDev benchmark runner. Tests multi-agent coordination on 30 application tasks (games, tools). 4-level evaluation: executability, code completeness, LLM-as-judge, MAST failure mode analysis.
- **[tests/chatdev_benchmark.py](tests/chatdev_benchmark.py)** -- HumanEval benchmark runner. Supports 8 models (GPT-5.4, Opus 4.7, GLM-5.1, MiniMax, Qwen 3.5, Gemma4, Gemma4 MoE, GPT-4o). Completed -- showed middleware is neutral on simple tasks.
- **[skills/mast-taxonomy/](skills/mast-taxonomy/)** -- Complete reference for the 14 MAST failure modes, prevalence data, and solution strategies.
- **[tests/test_harness.py](tests/test_harness.py)** -- Dynamic failure injection harness with 14 trigger prompts. Tests component-level defense effectiveness (14/14 PASS on Gemma4 and GPT-4o).
- **[tests/mast_judge.py](tests/mast_judge.py)** -- LLM-as-a-Judge pipeline adapted from the paper's evaluation methodology.

### Documentation

- **[PROGRAMDEV_TEST_PLAN.md](PROGRAMDEV_TEST_PLAN.md)** -- Detailed test plan for ProgramDev benchmark: dataset, evaluation methodology, execution steps
- **[BENCHMARK_PLAN.md](BENCHMARK_PLAN.md)** -- Overview of benchmark phases and lessons learned
- **[FINDINGS.md](FINDINGS.md)** -- Full experimental findings from HumanEval and prompt-only testing
- **[ROADMAP.md](ROADMAP.md)** -- Plan for in-process middleware implementation
- **[tests/RESULTS.md](tests/RESULTS.md)** -- Raw results from all testing levels

### Deprecated (Prompt-Only)

- **skills/agent-workspace-interview/** -- Generates 6-file config suite. Prompt suggestions that help some models and hurt others.
- **skills/mast-audit/** -- Static keyword audit. Measures text presence, not behavioral effectiveness.
- **mcp/mast-enforce/** -- MCP server for structural enforcement. Right concept, wrong mechanism -- tool call roundtrips are too slow.
- **tests/test-configs/mast-hardened/** -- 6-file MAST-hardened config suite. Preserved for reference.

---

## Key Findings

### 1. HumanEval is the wrong benchmark for MAST
Models score 96-100% on HumanEval (single-function coding) with or without middleware. MAST failure modes are multi-agent coordination failures that only trigger on complex, multi-step tasks like building full applications.

### 2. Verbose MAST prompts hurt, lean prompts help
Verbose MAST prompts cause context dilution (-18pp on GPT-4o). But compressed "caveman-style" rules (~150 tokens) improve performance by avoiding dilution while still guiding the model. The key insight from [Caveman](https://github.com/JuliusBrussee/caveman): constraining models to brief responses can improve accuracy.

### 3. In-process middleware works on hard tasks
State gates with syntax/import validation give +13pp on ProgramDev (80% → 93%). Combined with lean prompts: +17pp (80% → 97%). This exceeds the paper's best result (+15.6pp from topology changes).

### 4. The winning formula: lean prompts + structural enforcement
Neither prompts nor middleware alone is sufficient. The combination works because:
- **Lean prompts** guide the model to avoid common mistakes (flat imports, spec adherence)
- **State gates** catch mistakes the model makes anyway (syntax errors, broken imports)
- **Syntax validation** forces retries before delivery -- zero LLM roundtrips

### 5. What the state gates catch
- `SyntaxError` / `IndentationError` in generated code
- Relative imports without `__init__.py` (common in multi-file apps)
- Signature mismatches against task spec

### 6. What the lean rules prevent
- FM-1.1 (spec disobedience): "SPEC FIRST" rule
- FM-1.3 (step repetition): "NO LOOPS" rule
- FM-2.6 (reasoning-action mismatch): "MATCH REASONING TO ACTION" rule
- Import structure bugs: "FLAT IMPORTS" rule

---

## Models Tested

| Model | Provider | API |
|---|---|---|
| GPT-5.4 | OpenAI | OpenAI API |
| Opus 4.7 | Anthropic | Anthropic API |
| MiniMax-M2.7 | MiniMax | MiniMax API |
| GLM-5.1 | Zhipu | Ollama cloud gateway |
| Gemma4 31B | Google | Ollama cloud gateway |
| Gemma4 MoE 26B | Google | Gemini API |
| Qwen 3.5 397B | Alibaba | Ollama cloud gateway |
| GPT-4o | OpenAI | OpenAI API |

---

## Paper Reference

**"Why Do Multi-Agent LLM Systems Fail?"** -- Cemri et al., UC Berkeley, 2025  
arXiv: [2503.13657](https://arxiv.org/abs/2503.13657) | [Project Page](https://sites.google.com/berkeley.edu/mast/) | [GitHub](https://github.com/multi-agent-systems-failure-taxonomy/MAST)

Key paper results (Table 4):
- ChatDev baseline (GPT-3.5-turbo): 25.0% on ProgramDev, 89.6% on HumanEval
- Improved prompts: 34.4% on ProgramDev (+9.4pp)
- Cyclic topology: 40.6% on ProgramDev (+15.6pp)

## License

MIT
