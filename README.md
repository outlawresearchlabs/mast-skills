# MAST Skills: Architecture Matters More Than Agents

Empirical study of multi-agent system (MAS) failures, extending the UC Berkeley MAST taxonomy (["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657), arXiv:2503.13657).

**Key finding:** The 14 MAST failure modes are not inherent to multi-agent systems -- they are symptoms of **fixed-pipeline architecture**. Adaptive single-agent tools and adaptive multi-mode agents eliminate these failures entirely, while being 3-9x faster.

## Results Summary

### Same-Model Comparison (MiniMax-M2.7, ProgramDev-v0, 30 tasks)

| Framework | Architecture | Pass Rate | Avg TTC |
|---|---|---|---|
| **Private Agent** | Adaptive (6 modes, lane orchestration) | **29/30 (96%)** | **267s** |
| Claude Code | Single-agent + tools | 28/30 (93%) | 273s |
| ChatDev + lean+inprocess | Fixed pipeline (9 roles) + middleware | 29/30 (96%) | ~900s |
| ChatDev baseline | Fixed pipeline (9 roles) | 25/30 (83%) | ~900s |

### Cross-Model, Cross-Framework Comparison

| Framework | Model | Pass Rate | Avg TTC |
|---|---|---|---|
| Claude Code | Opus 4.6 | 30/30 (100%) | ~100s |
| **Private Agent** | MiniMax-M2.7 | 29/30 (96%) | 267s |
| ChatDev lean+inproc | MiniMax-M2.7 | 29/30 (96%) | ~900s |
| Claude Code | MiniMax-M2.7 | 28/30 (93%) | 273s |
| ChatDev lean+inproc | GPT-5.4 | 27/30 (90%) | ~900s |
| ChatDev lean+inproc | Kimi 2.5 | 26/30 (86%) | ~900s |
| ChatDev baseline | MiniMax-M2.7 | 25/30 (83%) | ~900s |
| ChatDev baseline | Kimi 2.5 | 24/30 (80%) | ~900s |
| Claude Code | GLM-5.1 | 23/30 (76%) | ~500s |
| ChatDev baseline | GPT-5.4 | 21/30 (70%) | ~900s |
| Hermes | GLM-5.1 | 21/30 (70%) | ~700s |
| ChatDev lean+inproc | GLM-5.1 | 21/30 (70%) | ~900s |
| ChatDev baseline | GLM-5.1 | 18/30 (60%) | ~900s |

### LLM-as-Judge Evaluation (GPT-5.4 as judge)

Does the generated code actually **work as intended**, not just run without crashing?

| Framework | Model | Strict PASS | PASS+PARTIAL | Score | FAILs |
|---|---|---|---|---|---|
| Claude Code | **Opus 4.6** | **26/30 (86%)** | **30/30 (100%)** | **93%** | **0** |
| **Private Agent** | MiniMax | 13/30 (43%) | **29/30 (96%)** | **70%** | **1** |
| Claude Code | MiniMax | 12/29 (41%) | 26/29 (89%) | 66% | 3 |
| ChatDev lean+inproc | MiniMax | 13/30 (43%) | 22/30 (73%) | 58% | 8 |
| ChatDev baseline | MiniMax | 6/30 (20%) | 22/30 (73%) | 47% | 8 |

Same model (MiniMax): Private Agent produces fewest outright failures (1) and highest PASS+PARTIAL (96%). Claude Code Opus dominates overall with 0 FAILs and 86% strict PASS.

Additional reps in progress for statistical validation (4 reps planned for key comparisons).

---

## Research Findings

### 1. Fixed-pipeline architecture causes MAST failures

The MAST paper identified 14 failure modes in multi-agent systems. At least 5 of them are **architectural failures** caused by fixed coordination patterns:

- **FM-1.3 Step repetition** (15.7%): forced review loops repeat completed work
- **FM-2.6 Reasoning-action mismatch** (13.2%): context lost in agent handoffs
- **FM-1.5 Unaware of termination** (9.8%): no adaptive exit criteria
- **FM-2.3 Task derailment** (7.2%): role-based agents pursue role goals over task goals
- **FM-3.1 Premature termination** (7.8%): fixed pipelines exit on loop count, not completion

These failures disappear when using adaptive single-agent tools (Claude Code) or adaptive multi-mode agents (Private Agent), because there is no fixed coordination to fail.

### 2. You can't fully fix a fixed pipeline

We tried three approaches to fix ChatDev's fixed pipeline:

| Intervention | Effect on ChatDev | What it fixes |
|---|---|---|
| Verbose MAST prompts | -18pp to +2pp (model-dependent) | Nothing reliably |
| Lean caveman prompts | +2-6pp | Import structure, spec adherence |
| In-process middleware (state gates) | +6-13pp | Syntax errors, import validation |
| Lean + inprocess combined | +10-20pp | Best fix available |

Even the best combination (+20pp on GPT-5.4) can't close the gap vs adaptive architecture at the same speed.

### 3. Architecture > model > prompts

The hierarchy of what matters:

1. **Architecture** (adaptive vs fixed): +13-40pp depending on model
2. **Model capability** (Opus vs GLM): +24-40pp depending on framework
3. **Middleware** (state gates): +6-13pp within fixed pipeline
4. **Prompt engineering** (lean rules): +2-6pp on top of middleware
5. **Verbose prompts** (MAST): -18pp to +2pp (unreliable)

### 4. Adaptive architecture matches fixed pipeline + middleware at 3.4x speed

Private Agent (adaptive, 6 modes) achieves 96% at 267s/task. ChatDev lean+inprocess achieves 96% at 900s/task. Same pass rate, 3.4x faster. The adaptive agent doesn't need middleware because it doesn't have the failures middleware fixes.

### 5. Single strong agent is a strong baseline

Claude Code + Opus 4.6 achieves 100% executability, 86% judge PASS, at ~100s/task. No framework, no middleware, no multi-agent coordination -- just a capable model with file tools.

### 6. HumanEval is the wrong benchmark for MAS research

All models score 96-100% on HumanEval regardless of framework or middleware. MAST failure modes only surface on complex, multi-step application tasks (ProgramDev).

---

## Methodology

### Benchmark: ProgramDev-v0

30 application-building tasks from the MAST paper: Checkers, Chess, Sudoku, Tetris, Snake, Wordle, Minesweeper, etc. These require multi-step planning, code generation, testing, and integration -- exactly where multi-agent coordination matters.

Paper baseline (ChatDev, GPT-3.5-turbo): 25.0%

### Evaluation Levels

1. **Executability** (automated): Does main.py run without crashing?
2. **Code completeness** (automated): Meaningful code produced? (>10 LOC, has entry point)
3. **Functional correctness** (LLM-as-judge, GPT-5.4): Does the app meet the spec? PASS/PARTIAL/FAIL
4. **MAST failure mode analysis** (LLM-as-judge): Which of the 14 failure modes caused failures?

### Frameworks Tested

| Framework | Type | Architecture |
|---|---|---|
| ChatDev | Multi-agent (9 roles) | Fixed DAG pipeline |
| Claude Code | Single-agent | Adaptive with sub-agent helpers |
| Hermes | Single-agent | Tool-calling agent |
| Private Agent | Adaptive multi-mode | 6 modes, lane orchestration, on-demand specialists |

### Models Tested

| Model | Provider | Used In |
|---|---|---|
| MiniMax-M2.7 | MiniMax API / Ollama | ChatDev, Claude Code, Private Agent |
| Opus 4.6 | Anthropic | Claude Code |
| GLM-5.1 | Ollama cloud | ChatDev, Claude Code, Hermes |
| GPT-5.4 | OpenAI | ChatDev |
| Qwen 3.5 397B | Ollama cloud | ChatDev |
| Kimi K2.5 | Ollama cloud | ChatDev |

### MAST Interventions Tested

| Config | Description |
|---|---|
| Baseline | No MAST defenses |
| Inprocess | State gates with syntax/import validation (zero LLM roundtrips) |
| Lean + inprocess | Compressed "caveman" MAST rules + state gates |
| Verbose MAST | Full MAST prompt defenses (from paper) |
| CTO topology | Cyclic CTO sign-off gate (from paper's +15.6pp finding) |

---

## The 9 Lean Caveman MAST Rules

Inspired by [Caveman](https://github.com/JuliusBrussee/caveman) -- compress prompts to reduce context dilution.

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

---

## Repository Structure

### Benchmarks
- **[tests/programdev_benchmark.py](tests/programdev_benchmark.py)** -- ProgramDev benchmark for ChatDev (multi-agent)
- **[tests/claude_code_benchmark.py](tests/claude_code_benchmark.py)** -- ProgramDev benchmark for Claude Code (single-agent)
- **[tests/hermes_benchmark.py](tests/hermes_benchmark.py)** -- ProgramDev benchmark for Hermes Agent
- **[tests/arcx_benchmark.py](tests/arcx_benchmark.py)** -- ProgramDev benchmark for adaptive agent
- **[tests/run_judge.py](tests/run_judge.py)** -- LLM-as-judge evaluation on existing results
- **[tests/chatdev_benchmark.py](tests/chatdev_benchmark.py)** -- HumanEval benchmark (completed, wrong benchmark)

### MAST Reference
- **[skills/mast-taxonomy/](skills/mast-taxonomy/)** -- Complete 14 failure mode reference
- **[tests/test_harness.py](tests/test_harness.py)** -- Dynamic failure injection (14 trigger prompts)
- **[tests/mast_judge.py](tests/mast_judge.py)** -- LLM-as-a-Judge pipeline

### Documentation
- **[PROGRAMDEV_TEST_PLAN.md](PROGRAMDEV_TEST_PLAN.md)** -- Detailed test methodology
- **[BENCHMARK_PLAN.md](BENCHMARK_PLAN.md)** -- Overview and lessons learned
- **[FINDINGS.md](FINDINGS.md)** -- Earlier HumanEval findings

---

## Paper Reference

**"Why Do Multi-Agent LLM Systems Fail?"** -- Cemri et al., UC Berkeley, 2025
arXiv: [2503.13657](https://arxiv.org/abs/2503.13657) | [Project Page](https://sites.google.com/berkeley.edu/mast/) | [GitHub](https://github.com/multi-agent-systems-failure-taxonomy/MAST)

Our work extends the MAST findings by showing that the 14 failure modes are architectural symptoms, not fundamental multi-agent limitations. The fix is not better prompts or middleware -- it's better architecture.

## License

MIT
