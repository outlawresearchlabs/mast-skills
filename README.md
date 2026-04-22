# Agent Architecture Benchmark

Empirical study comparing agent architectures on application building and security tasks. Extends the UC Berkeley MAST taxonomy (["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

**Key findings:**
1. **Architecture > model > prompts** for task completion
2. Adaptive architecture (Private Agent) achieves **98.3%** on ProgramDev with a mid-tier model
3. Prompts **hurt** adaptive architectures (-5 to -29pp) but can **help** strong models on simple frameworks (+6.7pp Opus verbose)
4. Fixed-pipeline multi-agent (ChatDev) is the worst architecture regardless of model or prompts
5. Tool sprawl (unnecessary MCP servers) degrades agent performance

## ProgramDev Results (30 application tasks, 4 reps each)

### Prompt Comparison (all 4-rep means)

| Framework | Model | Baseline | Lean | Verbose |
|---|---|---|---|---|
| **Private Agent** | **MiniMax** | **98.3%** | 92.5% (-5.8pp) | 94.2% (-4.1pp) |
| CC (Claude Code) | Opus 4.6 | 92.5% | 92.5% (0pp) | **99.2%** (+6.7pp) |
| CC | MiniMax | 88.3% | 90.0% (+1.7pp) | 89.2% (+0.9pp) |
| Hermes | MiniMax | 87.5% | 85.7% (-1.8pp) | 84.2% (-3.3pp) |
| **Private Agent** | **GLM-5.1** | **82.5%** | 65.0% (-17.5pp) | 53.3% (-29.2pp) |
| CC | GLM-5.1 | 59.2% | 64.2% (+5.0pp) | 57.5% (-1.7pp) |
| **Hermes** | **GLM-5.1** | **56.7%** | **88.3% (+31.6pp)** | **80.0% (+23.3pp)** |
| ChatDev lean+inproc | MiniMax | 96%* | - | - |
| ChatDev lean+inproc | GPT-5.4 | 90%* | - | - |
| ChatDev lean+inproc | Kimi 2.5 | 86%* | - | - |
| ChatDev lean+inproc | Qwen 3.5 | 93%* | - | - |
| ChatDev lean+inproc | GLM-5.1 | 70%* | - | - |
| ChatDev inprocess | MiniMax | 93%* | - | - |
| ChatDev inprocess | GPT-5.4 | 83%* | - | - |
| ChatDev inprocess | Kimi 2.5 | 86%* | - | - |
| ChatDev inprocess | GLM-5.1 | 66%* | - | - |
| ChatDev baseline | MiniMax | 83%* | - | - |
| ChatDev baseline | GPT-5.4 | 70%* | - | - |
| ChatDev baseline | Kimi 2.5 | 80%* | - | - |
| ChatDev baseline | Qwen 3.5 | 93%* | - | - |
| ChatDev baseline | GLM-5.1 | 60%* | - | - |

*ChatDev results are single rep. Paper reference (GPT-3.5-turbo): baseline 25%, +prompts 34.4%, +topology 40.6%.

### Key Prompt Findings

**Prompts hurt adaptive architectures:**
- Private Agent MiniMax: baseline 98.3% → lean 92.5% (-5.8pp) → verbose 94.2% (-4.1pp)
- Private Agent GLM: baseline 82.5% → lean 65% (-17.5pp) → verbose 53.3% (-29.2pp)

**Prompts massively help simple frameworks without built-in guidance:**
- Hermes GLM: baseline 56.7% → **lean 88.3% (+31.6pp)** → verbose 80% (+23.3pp)
- CC Opus: baseline 92.5% → verbose 99.2% (+6.7pp)
- CC MiniMax: baseline 88.3% → lean 90% (+1.7pp)

**Why:** Adaptive architectures have built-in guidance (20 native modules: recovery-recipes, policy-engine, self-improvement). External prompt rules conflict with internal ones. Simple frameworks (Hermes, Claude Code) have no built-in guidance, so prompts fill a real gap — up to +31.6pp improvement.

### Statistical Validation (4 reps)

Private Agent + MiniMax:

| Rep | Executability | Judge Strict PASS | Judge Score | Judge FAILs |
|---|---|---|---|---|
| r1 | 29/30 (96%) | 13/30 (43%) | 70% | 1 |
| r2 | 29/30 (96%) | 9/30 (30%) | 63% | 1 |
| r3 | 30/30 (100%) | 12/30 (40%) | 70% | 0 |
| r4 | 30/30 (100%) | 10/30 (33%) | 67% | 0 |
| **Mean** | **29.5/30 (98.3%)** | **11/30 (36.7%)** | **67.5%** | **0.5** |

Claude Code + Opus 4.6:

| Rep | Executability | Judge Strict PASS | Judge Score | Judge FAILs |
|---|---|---|---|---|
| r1 | 30/30 (100%) | 26/30 (86%) | 93% | 0 |
| r2 | 27/30 (90%) | 25/30 (83%) | 90% | 1 |
| r3 | 27/30 (90%) | 27/30 (90%) | 95% | 0 |
| r4 | 27/30 (90%) | 25/30 (83%) | 92% | 0 |
| **Mean** | **27.75/30 (92.5%)** | **25.75/30 (85.8%)** | **92.5%** | **0.25** |

### LLM-as-Judge (GPT-5.4 as judge)

| Framework | Model | Strict PASS | PASS+PARTIAL | Score | FAILs |
|---|---|---|---|---|---|
| CC | **Opus 4.6** | **25.75/30 (85.8%)** | **29.75/30 (99.2%)** | **92.5%** | **0.25** |
| **Private Agent** | MiniMax | 11/30 (36.7%) | 29.5/30 (98.3%) | 67.5% | 0.5 |
| CC | MiniMax | 12/30 (40%)† | 26/30 (86.7%)† | 66% | 3 |
| Private Agent | GLM-5.1 | 19/30 (63.3%)‡ | 25/30 (83.3%)‡ | 83%‡ | 0 |
| ChatDev lean+inproc | MiniMax | 13/30 (43%) | 22/30 (73%) | 58% | 8 |
| ChatDev baseline | MiniMax | 6/30 (20%) | 22/30 (73%) | 47% | 8 |

*Claude Code Opus and Private Agent MiniMax are 4-rep averages. Others are single rep.*
*† 29/30 judged. ‡ 25/30 judged. Skipped tasks counted as non-PASS.*

## CyberGym Results (10 vulnerability tasks)

Preliminary results on real-world vulnerability analysis (PoC generation):

| Agent | Config | PoCs Generated | Notes |
|---|---|---|---|
| Private Agent (stripped) | Baseline | 4/10 (40%) | Single run, sequential |
| Private Agent (full MCP) | Baseline | 1/4 (25%) | MCP overhead hurt |

CyberGym requires sequential runs (parallel causes API contention). Full 10-rep validation with security-focused prompts planned.

**Tool sprawl finding:** Adding MCP servers (git, browser, web, workspace, secrets, tasks) to the agent **reduced** CyberGym performance from 40% to 25%. The agent got distracted by irrelevant tool options instead of focusing on code analysis and PoC crafting.

## Research Findings

### 1. Architecture hierarchy

| Rank | Factor | Effect | Evidence |
|---|---|---|---|
| 1 | **Architecture** | +10-40pp | Private Agent 98.3% vs ChatDev 83% (same model) |
| 2 | **Model** | +10-39pp | Opus 92.5% vs GLM 59.2% (same framework) |
| 3 | **Prompts** | -29pp to +32pp | Massive help for simple frameworks, hurts adaptive ones |
| 4 | **Middleware** | +6-13pp | Helps fixed pipelines only (ChatDev) |

### 2. Prompts interact with architecture unpredictably

Same prompt, opposite effects depending on framework:

| Prompt | Hermes GLM | CC Opus | CC MiniMax | Private Agent MiniMax | Private Agent GLM |
|---|---|---|---|---|---|
| Lean | **+31.6pp** | 0pp | +1.7pp | **-5.8pp** | **-17.5pp** |
| Verbose | **+23.3pp** | **+6.7pp** | +0.9pp | -4.1pp | **-29.2pp** |

**Rule:** Prompts help frameworks WITHOUT built-in guidance (Hermes: +32pp). Prompts hurt frameworks WITH built-in guidance (arcx: -29pp). The more internal guidance a framework has, the more external prompts conflict.

### 3. Fixed-pipeline architecture causes MAST failures

The MAST paper's 14 failure modes are architectural symptoms:
- FM-1.3 Step repetition (15.7%): forced review loops
- FM-2.6 Reasoning-action mismatch (13.2%): context lost in handoffs
- FM-1.5 Unaware of termination (9.8%): no adaptive exit criteria

These disappear in adaptive architectures.

### 4. Tool sprawl hurts

Adding unnecessary tools degrades performance. Agents waste reasoning on irrelevant options ("should I use the browser server? the git server?"). Minimum viable toolkit per task outperforms maximum capability.

### 5. Single-rep results are unreliable

| Metric | 1-rep | 4-rep mean | Difference |
|---|---|---|---|
| CC MiniMax baseline | 93% | 88.3% | -4.7pp |
| CC GLM baseline | 76% | 59.2% | -16.8pp |
| Private Agent GLM baseline | 83% | 82.5% | -0.5pp |

Single reps can overestimate by up to 17pp. Minimum 4 reps needed.

## Benchmark

### ProgramDev-v0
30 application-building tasks from the MAST paper: Checkers, Chess, Sudoku, Tetris, Snake, Wordle, etc.

Paper baseline (ChatDev, GPT-3.5-turbo): 25.0%

### CyberGym
10 real-world vulnerability analysis tasks. Agent must analyze vulnerable code and generate proof-of-concept exploits.

### Evaluation
1. **Executability** (automated): Does main.py run?
2. **Code completeness** (automated): Meaningful code produced?
3. **Functional correctness** (LLM-as-judge, GPT-5.4): Does it work as intended?
4. **MAST failure mode analysis**: Which FM caused failures?

## Frameworks Tested

| Framework | Architecture | Native Modules | Built-in Tools |
|---|---|---|---|
| Private Agent | Adaptive (6 modes, lane orchestration) | 20 (memory, recovery, self-improvement...) | 16 (bash, read, write, edit...) |
| Claude Code | Single-agent + sub-agent helpers | 0 | ~10 (file, bash, search) |
| Hermes | Single-agent + tool calling | 0 | ~8 (file, bash) |
| ChatDev | Fixed pipeline (9 roles) | 0 | ~10 (via function calling) |

## Models Tested

| Model | Provider |
|---|---|
| Opus 4.6 | Anthropic |
| MiniMax-M2.7 | MiniMax API / Ollama cloud |
| GLM-5.1 | Ollama cloud |
| GPT-5.4, Qwen 3.5, Kimi 2.5 | Various (ChatDev only) |

## Future Work

1. **Tool sprawl hypothesis**: Test adding MCP servers to Claude Code/Hermes - predict scores drop
2. **CyberGym sequential validation**: 10-rep runs with security-focused prompts
3. **Redteam skill impact**: Does auto-routing to security methodology improve PoC generation?
4. **Cross-domain validation**: Test on data science, DevOps tasks to confirm generalization
5. **Full Private Agent rebuild**: 7 new native modules (team, messaging, scheduler, simulator, trainer, skill-evolution, harness) — 20 → 27 modules

## The 9 Lean Caveman MAST Rules

```
1. SPEC FIRST: Read spec fully before coding. Implement what spec says, not what function name suggests.
2. NO LOOPS: If step done, skip it. Never redo completed work.
3. STOP WHEN DONE: Task complete = deliver. No gold-plating, no extra features.
4. VERIFY BEFORE DELIVER: Check syntax valid, imports resolve, code runs. Never deliver unverified.
5. MATCH REASONING TO ACTION: If you reason X, implement X. Never reason one thing and do another.
6. ASK IF UNCLEAR: Ambiguous requirement = ask, not assume.
7. USE PEER INPUT: If another agent suggests fix, evaluate it. Never ignore.
8. FLAT IMPORTS: Use absolute imports. No relative imports (from .X) unless __init__.py exists.
9. TEST EDGE CASES: Never trust "just test X". Test boundaries, empty input, error paths.
```

Inspired by [Caveman](https://github.com/JuliusBrussee/caveman).

## Paper Reference

**"Why Do Multi-Agent LLM Systems Fail?"** — Cemri et al., UC Berkeley, 2025
[arXiv:2503.13657](https://arxiv.org/abs/2503.13657) | [Project](https://sites.google.com/berkeley.edu/mast/) | [GitHub](https://github.com/multi-agent-systems-failure-taxonomy/MAST)

## License

MIT
