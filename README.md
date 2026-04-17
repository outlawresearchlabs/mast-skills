# MAST Skills

Tools for preventing the 14 failure modes from the MAST taxonomy (UC Berkeley paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657)).

## Current Status: In-Process Middleware

**Prompt-only MAST defenses are unreliable -- they can help or hurt depending on the model.** On GPT-4o, verbose MAST prompts are actively harmful (-18pp). On Gemma4, even minimal prompts can interfere (-4pp). MCP-based structural enforcement is architecturally sound but too slow in practice.

The viable path is **in-process Python middleware**: programmatically enforcing constraints inside the agent pipeline with zero LLM roundtrips. See [FINDINGS.md](FINDINGS.md) for full results.

### Benchmark Results (25 HumanEval problems x 2 reps = 50 trials each)

| Model | Baseline | MAST (verbose prompts) | Lean (minimal prompt) |
|---|---|---|---|
| GPT-4o | 88.0% (44/50) | 70.0% (-18pp) | 90.0% (+2pp) |
| Gemma4:31b-cloud | 98.0% (49/50) | 96.0% (-2pp) | 94.0% (-4pp) |

MCP structural enforcement: untestable (900s timeout on first problem)

**Key finding**: Same intervention, opposite effects across models. No universal safe prompt exists.

---

## What's Here

### Useful

- **[skills/mast-taxonomy/](skills/mast-taxonomy/)** -- Complete reference for the 14 MAST failure modes, prevalence data, and solution strategies. Genuinely useful for understanding where multi-agent systems fail.
- **[tests/test_harness.py](tests/test_harness.py)** -- Failure injection test harness. Still useful for FC1 (forgetfulness) regression testing. Should not be used as evidence of real defense effectiveness.
- **[tests/chatdev_benchmark.py](tests/chatdev_benchmark.py)** -- Benchmark script for testing MAST configs against HumanEval through ChatDev pipeline. Supports baseline, MAST, lean, and structural configs with resume capability.
- **[tests/results/](tests/results/)** -- Full raw results from all benchmark runs.

### Deprecated (Prompt-Only)

- **skills/agent-workspace-interview/** -- Generates 6-file config suite. The configs are prompt suggestions that help some models and hurt others.
- **skills/mast-audit/** -- Static keyword audit. Can tell you if defense phrases exist, not if they work.
- **mcp/mast-enforce/** -- MCP server with verify_code(), check_completion(), generate_edge_cases(). Right concept, wrong mechanism -- tool call roundtrips are too slow. Should be reimplemented as in-process middleware.
- **tests/test-configs/mast-hardened/** -- The 6-file MAST-hardened config suite. Preserved for reference.
- **ChatDev MAST YAML configs** -- MAST-hardened ChatDev config. -18pp on GPT-4o.

### Results & Documentation

- **[FINDINGS.md](FINDINGS.md)** -- Full experimental findings: benchmark results, analysis, costs, and the case for in-process middleware
- **[ROADMAP.md](ROADMAP.md)** -- Plan for in-process middleware implementation
- **[tests/RESULTS.md](tests/RESULTS.md)** -- Raw results from all testing levels

---

## Key Findings Summary

| Test Level | Method | Result | Validity |
|---|---|---|---|
| Static audit | Keyword matching | 14/14 DEFENDED | Low -- measures text, not behavior |
| Synthetic triggers (gemma4) | Failure injection | 14/14 PASS (+29.1% vs baseline) | Medium -- measures compliance, not real failure reduction |
| Synthetic triggers (GPT-4o) | Failure injection | 14/14 PASS (+18.8% vs baseline) | Low -- strong model doesn't need MAST; baseline already 11/14 |
| Whole-system (ChatDev, 50 trials) | HumanEval pass@1 | See table above | **High -- this is what matters** |
| MCP structural | HumanEval (1 attempt) | 900s timeout | N/A -- too slow to benchmark |

### The prompt reliability problem

Same prompt intervention has opposite effects:
- MAST on GPT-4o: **-18pp** (harmful)
- MAST on Gemma4: **-2pp** (negligible)
- Lean on GPT-4o: **+2pp** (helpful)
- Lean on Gemma4: **-4pp** (harmful)

Prompt-based defenses cannot be relied upon as a safety mechanism.

### What prompts can do (FC1: forgetfulness)

- FM-1.3 (step repetition): Anti-loop tags work as reminders
- FM-2.2 (clarification): `<CLARIFY>` tag prompts a behavior the model can already do
- FM-1.5 (termination): Termination conditions work as reminders on weak models

### What prompts cannot do (FC2/FC3: reasoning/verification)

- FM-1.1 (disobey spec): Model ignores "NEVER implement based on function name" when type priors are strong
- FM-3.2 (no verification): Model can't execute code; "verify before delivery" produces superficial checks
- FM-3.3 (incorrect verification): "Never trust hints" doesn't override the model's tendency to use available information

---

## The Path Forward

Prompt-based defenses are unreliable. MCP tool calls are too slow. The viable approach is **in-process Python middleware**:

1. Hook into agent pipeline after code generation
2. Run Python verification (signature matching, test execution, syntax validation)
3. Set state gates programmatically in milliseconds
4. Structural enforcement regardless of model behavior -- no LLM roundtrips, no model compliance dependency

See [ROADMAP.md](ROADMAP.md) for the implementation plan.

## License

MIT