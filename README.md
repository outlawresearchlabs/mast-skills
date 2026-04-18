# MAST Skills

Tools for preventing the 14 failure modes from the MAST taxonomy (UC Berkeley paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

## Current Status: ProgramDev Benchmark (In Progress)

We discovered our previous benchmarking on HumanEval was **testing the wrong thing**. HumanEval tests single-function coding -- all models score 96-100% regardless of middleware. The MAST failure modes (step repetition, task derailment, reasoning-action mismatch) are **multi-agent coordination failures** that only surface on complex, application-level tasks.

We are now benchmarking on **ProgramDev-v0** (30 application tasks: Chess, Tetris, Snake, etc.) -- the same benchmark used in the MAST paper. Paper baseline (GPT-3.5-turbo): **25.0%**.

### ProgramDev Results (In Progress)

| Model | Baseline | Inprocess (middleware) | Delta |
|---|---|---|---|
| MiniMax-M2.7 | 60-80% (5 tasks) | pending | pending |
| GPT-5.4 | pending | pending | pending |
| GLM-5.1 | pending | pending | pending |
| Qwen 3.5 | pending | pending | pending |
| Gemma4 MoE | pending | pending | pending |

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

### 2. Prompt-based defenses are model-dependent
Same prompt intervention has opposite effects across models (-18pp on GPT-4o, -2pp on Gemma4). No universal safe prompt exists.

### 3. Dynamic failure injection works at component level
MAST defense configs pass 14/14 trigger tests on both Gemma4 and GPT-4o. The defenses work in isolation but haven't been validated on the correct whole-system benchmark yet.

### 4. In-process middleware is architecturally sound
State gate enforcement with zero LLM roundtrips runs in milliseconds. Whether it improves task completion on ProgramDev is the open question being tested now.

### 5. What prompts can do (FC1: specification issues)
- FM-1.3 (step repetition): Anti-loop tags work as reminders
- FM-2.2 (clarification): `<CLARIFY>` tag prompts useful behavior
- FM-1.5 (termination): Termination conditions work on suggestible models

### 6. What prompts cannot do (FC2/FC3: reasoning/verification)
- FM-1.1 (spec disobedience): Model follows function name over explicit spec
- FM-3.2 (no verification): Model can't execute code to truly verify
- FM-3.3 (incorrect verification): "Never trust hints" doesn't override model tendencies

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
