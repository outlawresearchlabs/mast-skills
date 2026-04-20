# MAST Skills

Tools for preventing the 14 failure modes from the MAST taxonomy (UC Berkeley paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

## Current Status: ProgramDev Results

We discovered our previous benchmarking on HumanEval was **testing the wrong thing**. HumanEval tests single-function coding -- all models score 96-100% regardless of middleware. The MAST failure modes (step repetition, task derailment, reasoning-action mismatch) are **multi-agent coordination failures** that only surface on complex, application-level tasks.

We now benchmark on **ProgramDev-v0** (30 application tasks: Chess, Tetris, Snake, etc.) -- the same benchmark used in the MAST paper. Paper baseline (GPT-3.5-turbo): **25.0%**.

### ProgramDev Results - Executability (30 application tasks each)

| Config | Qwen 3.5 | MiniMax | Kimi 2.5 | GPT-5.4 | GLM-5.1 |
|---|---|---|---|---|---|
| Baseline | 28/30 (93%) | 25/30 (83%) | 24/30 (80%) | 21/30 (70%) | 18/30 (60%) |
| Inprocess (gates + syntax) | 28/30 (93%) | 28/30 (93%) | 26/30 (86%) | 25/30 (83%) | 20/30 (66%) |
| **Lean + Inprocess** | **28/30 (93%)** | **29/30 (96%)** | **26/30 (86%)** | **27/30 (90%)** | **21/30 (70%)** |
| **Delta (lean vs baseline)** | **0 (+0pp)** | **+4 (+13pp)** | **+2 (+6pp)** | **+6 (+20pp)** | **+3 (+10pp)** |

### ProgramDev Results - LLM-as-Judge (MiniMax, GPT-5.4 as judge)

Executability ("does it run?") is necessary but not sufficient. The LLM judge evaluates whether the generated code actually **works as intended**.

| Metric | Baseline | Lean+Inprocess | Delta |
|---|---|---|---|
| **Strict PASS** (fully working) | 6/30 (20%) | 13/30 (43%) | **+7 tasks (+23pp)** |
| **PASS + PARTIAL** (core logic works) | 22/30 (73%) | 22/30 (73%) | 0 |
| **Weighted Score** (P=2, PARTIAL=1, F=0) | 47% | 58% | **+11pp** |

**Key insight:** The middleware doesn't reduce failures (8 FAILs in both configs). It **upgrades PARTIALs to PASSes** -- polishing viable code into fully working applications. 7 tasks moved from "core logic present but incomplete" to "fully functional."

Paper comparison (ChatDev, GPT-3.5-turbo):
- Baseline: 25.0% | Improved prompts: 34.4% (+9.4pp) | Cyclic topology: 40.6% (+15.6pp)

**Key findings:**
- **GPT-5.4 shows the largest executability improvement: +6 tasks (+20pp)** from lean+inprocess
- **MiniMax strict judge PASS more than doubled: 20% → 43%** with lean+inprocess
- Strong models (Qwen 3.5 at 93%) see no benefit -- already near ceiling
- Mid-tier models benefit most from structural enforcement
- The 8 persistent FAILs are being tested with CTO-gatekeeper topology (cyclic review)
- Direct API testing (Zhipu for GLM, Moonshot for Kimi) confirmed tool-calling patterns are model capability, not API path

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

### Architecture Comparison: Fixed Pipeline vs Adaptive vs Single-Agent

The core question isn't "multi-agent vs single-agent" -- it's **"does the architecture match the task?"**

#### Same Model Comparison (MiniMax-M2.7)

| Framework | Architecture | Exec | Rate | Avg TTC |
|---|---|---|---|---|
| **Private Agent** | **Adaptive (6 modes, lane orchestration)** | **29/30** | **96%** | **267s** |
| Claude Code | Single-agent + tools | 28/30 | 93% | 273s |
| ChatDev lean+inproc | Fixed pipeline (9 roles) + middleware | 29/30 | 96% | ~900s |
| ChatDev baseline | Fixed pipeline (9 roles) | 25/30 | 83% | ~900s |

#### Cross-Model Comparison

| Framework | Model | Exec | Avg TTC |
|---|---|---|---|
| Claude Code | Opus 4.6 | 30/30 (100%) | ~100s |
| **Private Agent** | **MiniMax** | **29/30 (96%)** | **267s** |
| ChatDev lean+inproc | MiniMax | 29/30 (96%) | ~900s |
| Claude Code | MiniMax | 28/30 (93%) | 273s |
| ChatDev baseline | MiniMax | 25/30 (83%) | ~900s |
| Claude Code | GLM-5.1 | 23/30 (76%) | ~500s |
| Hermes | GLM-5.1 | 21/30 (70%) | ~700s |
| ChatDev lean+inproc | GLM-5.1 | 21/30 (70%) | ~900s |
| ChatDev baseline | GLM-5.1 | 18/30 (60%) | ~900s |

#### LLM-as-Judge (does it actually work?)

| Framework | Model | Strict PASS | PASS+PARTIAL | Score |
|---|---|---|---|---|
| **Claude Code** | **Opus 4.6** | **26/30 (86%)** | **30/30 (100%)** | **93%** |
| ChatDev lean+inproc | MiniMax | 13/30 (43%) | 22/30 (73%) | 58% |
| ChatDev baseline | MiniMax | 6/30 (20%) | 22/30 (73%) | 47% |

**Key findings:**

1. **The problem is fixed-pipeline architecture, not multi-agent itself.** ChatDev forces every task through CEO→CTO→Programmer→Reviewer→Tester whether it needs 1 step or 5. This causes the MAST failure modes (step repetition, task derailment, premature termination).

2. **Adaptive architecture wins.** A private adaptive agent (96%) matches ChatDev+middleware (96%) at **3.4x the speed**, and beats Claude Code single-agent (93%) on the same model.

3. **You can't fix a fixed pipeline.** MAST middleware adds +13-20pp to ChatDev, but the ceiling is the architecture. The 9-agent review chain will always be slower and more failure-prone than adaptive orchestration.

4. **Same model, different architecture = different results.** MiniMax-M2.7 scores 83% in ChatDev baseline, 93% in Claude Code, and 96% in an adaptive agent. The model isn't the bottleneck -- the framework is.

5. **Strong model + simple tools is a strong baseline.** Claude Code (Opus) at 100% shows that a capable model with basic file tools beats any framework with a weaker model.

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
