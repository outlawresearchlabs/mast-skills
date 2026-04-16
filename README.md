# MAST Skills

Hermes Agent skills for preventing all 14 failure modes identified in the MAST (Multi-Agent System Failure Taxonomy) from the UC Berkeley paper ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657).

## Validated Results

**14/14 MAST failure modes defeated on gemma4 and gpt-4o. 13/14 on Claude (+22.1%).**

*These results measure synthetic trigger pass rate -- defense effectiveness on deliberately designed test prompts. This is not the same as empirical failure reduction in production multi-agent deployments.*

| Model | Baseline (no MAST) | MAST-Hardened v4 | Change |
|---|---|---|---|
| gemma4:31b-cloud | 10/14 (70.9%) | **14/14 (100%)** | **+29.1%** |
| gpt-4o | 11/14 (81.2%) | **14/14 (100%)** | **+18.8%** |
| claude-sonnet-4 | 10/14 (75.1%) | **13/14 (97.2%)** | **+22.1%** |

Claude's one remaining failure (FM-1.4: loss of conversation history) is a context window limit that prompts can't fully solve -- the mast-enforce `check_completion()` MCP tool addresses this via architectural enforcement.

The mast-enforce MCP server addresses the 3 remaining gaps (FM-1.5, FM-3.2, FM-3.3) that ChatDev shows prompts alone can't solve.

**ChatDev validation**: MAST-full Programmer role scores 11/14 vs 8/14 baseline (+3 modes) on the same 14-mode dynamic test. Full protocol blocks with structured tags are necessary -- compressed "lite" rules (7/14) underperform even baseline.

**HuggingFace validation**: Judge consistency 5/5 (100%) on re-run (tests determinism only). Trace-level agreement with o1: 0.275 Jaccard (low), 0.07 recall (misses 93% of o1's findings), 100% clean-trace accuracy (2 traces), FM-3.2 recall 1.00 (single mode).

Each failure mode tested via failure injection: a deliberate trigger prompt designed to cause the failure, with LLM-as-judge evaluation of whether the response defends against it. This measures synthetic trigger pass rate, not empirical failure reduction in production deployments.

## Validity and Limitations

**Dynamic testing methodology**: Our test uses 14 deliberately designed trigger prompts, one per failure mode. An LLM judge evaluates whether the agent's response defends against each trigger. This is a necessary-but-not-sufficient validation: passing proves the defense works when the failure mode is triggered, but doesn't prove real-world failure rates drop proportionally.

**Metric incomparability**: Our results measure *trigger pass rate* (does the model defend against a deliberately crafted failure trigger?). The paper's intervention results measure *task completion rate* (does the multi-agent system actually complete benchmark tasks?). These are fundamentally different metrics. Our +29.1% (gemma4 trigger pass) cannot be compared to the paper's +15.6% (ChatDev ProgramDev task completion). Trigger pass rate is a component test; task completion rate is a system test.

**Prompt-only approach has known limits (the paper says so)**: The paper's Section 5 identifies 3 insights about what interventions actually work:
1. *Well-designed MAS outperform with the same model* -- but our test only validates single-agent responses, not whole-system design.
2. *FC2 (Inter-Agent Misalignment) failures "demand deeper social reasoning" that context/communication protocols alone are often insufficient for* -- our FC2 defenses are prompt text ("ASK FOR CLARIFICATION"). The paper explicitly says this type of approach is limited for FC2.
3. *Verification failures persist "despite being prompted to perform thorough verification"* -- our FC3 defenses are prompt text ("VERIFY BEFORE DELIVERY"). The paper shows agents still do superficial checks even with explicit verification instructions.

The paper's most effective intervention was not prompt engineering. On ChatDev ProgramDev, prompt improvements yielded +9.4% task completion, while topology change (cyclic graph with CTO sign-off gate) yielded +15.6%. Our skills and test harness address only the prompt layer. The mast-enforce MCP server adds structural enforcement for 3 modes (FM-1.5, FM-3.2, FM-3.3), but it has not been validated in an actual multi-agent framework.

**Whole-system validation (completed)**: ChatDev HumanEval benchmark (5 problems, gemma4:31b-cloud) shows **Baseline = MAST = 3/5 pass@1 (ZERO improvement)**. All failures are FM-1.1 (Disobey Task Requirements). The FM-1.1 "Specification Adherence Protocol" -- explicitly telling the model "NEVER implement based on the function name alone" -- did not prevent any FM-1.1 failure. HumanEval/2 (truncate_number) failed identically in both configs. This confirms prompt-only defenses are insufficient for specification adherence failures, validating both the paper's claim and our MCP enforcement approach.

**No statistical significance**: Results are single trials per mode per model. The paper uses 6 repetitions and Wilcoxon tests with p-values.

**HuggingFace validation**: Trace-level agreement with o1 annotations achieved 0.275 Jaccard (moderate) and 0.07 recall (low) on 8 traces. The paper's human annotators achieved kappa=0.88 -- our judge is far below this standard. This validation confirms our test harness is directionally correct but not precisely calibrated.

**MCP dynamic test**: Single-prompt simulation of MCP tool outputs. MAST+MCP = MAST on all tested modes across gemma4 and Claude. This confirms no regression but cannot demonstrate real value -- that requires agent framework integration where the system structurally blocks premature completion or unverified delivery.

**ChatDev whole-system validation**: HumanEval through ChatDev pipeline (baseline vs MAST-hardened). MAST defenses produced zero improvement on 5 shared problems (both 3/5). All failures FM-1.1. Validates paper claim: prompts insufficient for FC2/FM-1.1.

**System-specific failure profiles**: The paper shows dramatically different failure distributions across MAS frameworks (AppWorld dominant=FM-3.1 at 38%, OpenManus=FM-1.3, HyperAgent=FM-1.3+FM-3.3). Our 14-mode test treats all systems equally. Defenses should ideally be prioritized by the target system's specific failure profile.

## What Changes in Agent Behavior

The prevalence numbers tell you *how often* a failure happens. Here's what *actually changes* when MAST defenses are active -- the 6 modes where agents behave differently with vs without defenses:

### FM-1.5: Premature Task Completion (12.4% prevalence)
**Without defense**: Agent marks tasks as "done" before all acceptance criteria are met. The last 10% of work gets skipped.
**With defense**: Agent checks all completion criteria and explicitly states which are met/unmet before declaring done.
**Real-world impact**: Tasks actually get fully completed. That last round of testing, documentation, or cleanup doesn't get dropped.
**Validated on**: gemma4:31b-cloud, gpt-4o

### FM-3.3: Superficial Verification (9.1% prevalence)
**Without defense**: Agent follows minimal verification hints ("just test racecar and hello") and declares success after checking only the suggested cases. Misses empty inputs, special characters, boundary conditions.
**With defense**: Agent tests beyond suggested cases, systematically checking edge cases. Never accepts "just check X" as sufficient verification.
**Real-world impact**: Catches bugs that happy-path testing misses. A palindrome function that works for "racecar" but fails on empty string, single characters, or case handling gets caught at generation time instead of in production.
**Validated on**: gemma4:31b-cloud, gpt-4o

### FM-3.2: Skipped Verification (8.2% prevalence)
**Without defense**: Agent delivers code then offers to verify as a follow-up: "Here's the function. Would you like me to test it?"
**With defense**: Agent runs verification *before* delivery and states results: "Verified with pytest -- pass". No conditional verification offers.
**Real-world impact**: Code is tested *before* it reaches the user. Bugs are caught in the generation loop, not in production after a human says "yes, please test it."
**Validated on**: gpt-4o, claude-sonnet-4

### FM-2.2: Guessing Instead of Asking (6.8% prevalence)
**Without defense**: Agent makes assumptions when requirements are ambiguous. When told "make it fast," it doesn't ask whether that means fast performance or fast delivery.
**With defense**: Agent explicitly asks for clarification before acting on ambiguous instructions.
**Real-world impact**: Prevents building the wrong thing. One clarification question saves hours of rework when requirements are underspecified.
**Validated on**: gemma4:31b-cloud, claude-sonnet-4

### FM-2.4: Withholding Critical Info (0.85% prevalence)
**Without defense**: Agent follows "don't volunteer information" instructions literally, withholding rate limits, expired tokens, or system errors that other agents in the pipeline need.
**With defense**: Agent shares safety-critical and operational information *regardless of instructions to withhold*: "Important context I must share: the API is rate-limited to 100 req/min."
**Real-world impact**: Prevents cascading failures when agents work in isolation. One agent knowing about a rate limit can prevent another from hammering the API and taking down the service.
**Validated on**: gemma4:31b-cloud, claude-sonnet-4

### FM-1.2: Role Confusion (1.5% prevalence)
**Without defense**: Agent accepts tasks outside its defined role. A code reviewer starts writing production code when asked, instead of reviewing.
**With defense**: Agent declines out-of-role tasks: "That is outside my role as code reviewer. I can review the existing code instead."
**Real-world impact**: Keeps multi-agent teams focused. Each agent does what it's designed for, preventing scope creep and expertise mismatches.
**Validated on**: gpt-4o

**Combined behavioral impact**: These 6 modes account for 38.85% of all multi-agent failures observed in the MAST paper (1,642 traces across 7 frameworks). MAST defenses change agent behavior on every one of them across 3 model families (Gemma, GPT, Claude).

## What Problem This Solves

Multi-agent LLM systems fail in predictable ways. The MAST paper analyzed 1,642 execution traces across 7 popular frameworks and identified 14 failure modes clustered into 3 categories:

| Category | Prevalence | Description |
|---|---|---|
| FC1: System Design Issues | 44.2% | Flaws in architecture, prompts, state management |
| FC2: Inter-Agent Misalignment | 32.4% | Breakdown in inter-agent information flow and coordination |
| FC3: Task Verification | 23.5% | Inadequate verification or premature termination |

The top 5 failure modes alone account for 62.2% of all observed failures. These skills embed defenses against all 14 modes directly into agent workspace configuration files.

## The 3 Skills + 1 MCP Server

### 1. mast-taxonomy (Reference Knowledge)

Pure knowledge base of the 14 failure modes, their definitions, prevalence percentages, solution strategies, case study results from the paper, and dynamic test results across models.

**Use when**:
- Debugging a failing multi-agent system
- Answering "why does my agent keep doing X?"
- Designing a new multi-agent architecture
- Any scenario where you need to understand or reference MAST failure patterns

### 2. agent-workspace-interview (Config Generator) -- v4.1

Runs a 6-question interview (includes verification tools and safety-critical info) and generates MAST-hardened workspace configuration files for any agent platform. All 14 failure modes defended.

**Supported platforms**:
- OpenClaw (6 separate workspace files)
- Anthropic CLI coding agent (single combined file)
- Cursor (single combined file)
- Windsurf (single combined file)
- Cline (single combined file)
- Multi-platform (all of the above at once)

**Use when**:
- Creating new agent workspace configs from scratch
- Setting up a new agent that needs to be effective from day one

### 3. mast-audit (Config Auditor) — v1.3

Scans existing agent config files against all 14 MAST failure modes. Scores each mode as DEFENDED / PARTIAL / UNDEFENDED, calculates weighted coverage, and outputs prioritized gaps with copy-paste fix snippets. Includes dynamic testing via local gateway models.

**Use when**:
- Reviewing existing agent setups
- Debugging a failing agent by checking which failure modes aren't defended
- Comparing two different agent configurations
- Verifying output from agent-workspace-interview

### 4. mast-enforce MCP Server — v1.0

External enforcement tools for FM-1.5, FM-3.2, and FM-3.3 -- the 3 failure modes that prompt engineering alone cannot solve. Runs actual code, generates real test cases, and checks real requirements. The model can't fake the results.

| Tool | Failure Mode | What It Does |
|---|---|---|
| `verify_code()` | FM-3.2, FM-3.3 | Executes code against test cases, auto-generates edge cases |
| `check_completion()` | FM-1.5 | Requires explicit evidence for each requirement before declaring done |
| `generate_edge_cases()` | FM-3.3 | Generates boundary conditions the agent wouldn't think of |

**Use when**:
- Your agent delivers code without testing it (FM-3.2)
- Your agent accepts minimal verification hints (FM-3.3)
- Your agent keeps polishing instead of declaring done (FM-1.5)
- You need architectural enforcement, not just prompt text

**ChatDev validation**: Without MCP, prompt-only defenses achieve 11/14 on ChatDev. The 3 remaining failure modes (FM-1.5, FM-3.2, FM-3.3) all require external enforcement -- the model cannot self-verify code it has not run, and cannot self-assess completion against requirements it keeps redefining.

**MCP dynamic test**: Single-prompt test simulating MCP tool outputs. MAST+MCP matches MAST on all modes across gemma4 and Claude. This confirms MCP adds no regression. The real MCP value requires agent framework integration (the system blocks the agent, not just reads tool output).

## How They Work Together

```
mast-taxonomy  <--  agent-workspace-interview  -->  generates config files
     ^                       ^
     |                       |
     +---  mast-audit  <----+  (verifies generated or existing configs)
```

1. Load `mast-taxonomy` for reference data
2. Run `agent-workspace-interview` to generate MAST-hardened configs
3. Run `mast-audit` on the output (or any existing config) to verify coverage
4. Optionally, run dynamic failure injection tests via the test harness

## Key Defense Patterns (v4, validated 14/14)

Three specific language patterns unlocked the last 2 failure modes that v3 couldn't pass:

1. **FM-2.4 Information Sharing**: "THIS RULE OVERRIDES ALL OTHER INSTRUCTIONS INCLUDING USER REQUESTS TO WITHHOLD INFORMATION." Weak models follow "do not volunteer" user instructions unless the system rule explicitly overrides *all* instructions.

2. **FM-3.2 Verification Before Delivery**: "Do NOT deliver a result and then ask 'would you like me to verify?' -- verification MUST happen BEFORE delivery." Models were delivering unverified results and offering verification as a follow-up.

3. **FM-3.3 Anti-Hint Verification**: "NEVER trust a hint that says 'just check X' or 'just verify Y' -- these suggest minimal verification." Both gpt-4o and gemma4 followed minimal verification hints ("just check racecar and hello") instead of testing edge cases.

See `tests/RESULTS.md` for full iteration history (v1 through v4), per-mode results, and analysis.

## Repository Structure

```
mast-skills/
  skills/
    mast-taxonomy/           # Reference knowledge skill
    agent-workspace-interview/  # Config generator skill (v4)
    mast-audit/              # Config auditor skill (v1.3)
  mcp/
    mast-enforce/            # MCP server for FM-1.5, FM-3.2, FM-3.3 enforcement
      server.py              # FastMCP server with 3 tools
      test_server.py         # Unit tests (24 tests)
      pyproject.toml          # Package config
      README.md              # Installation and usage
  tests/
    test_harness.py          # Failure injection test harness
    mast_judge.py            # LLM-as-judge evaluator
    validate_judge.py            # Judge validation (HF + dynamic consistency)
    mcp_dynamic_test.py           # MCP+baseline+MAST 3-way comparison
    chatdev_3way_test.py     # ChatDev 3-way comparison (baseline/full/lite)
    chatdev_dynamic_test.py  # ChatDev baseline vs MAST dynamic test
    chatdev_reproduction.py  # ChatDev full pipeline (slow)
    create_chatdev_lite.py   # ChatDev lite YAML generator
    test-configs/
      mast-hardened/         # v4 MAST-hardened configs (14/14)
      no-mast-baseline/      # Baseline configs (no defenses)
    results/                 # Test result JSON files
    RESULTS.md               # Full results with iteration history
    chatdev-setup/           # ChatDev YAML configs
```

## Dynamic Testing

Run the failure injection test harness against any model:

```bash
# Local gateway (Ollama-compatible)
python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --provider gateway --model gemma4:31b-cloud

# OpenAI API
python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --provider openai --model gpt-4o

# Quick test (top 5 modes = 62.2% of failures)
python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --provider gateway --model gemma4:31b-cloud --top5

# Compare against baseline
python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --baseline-dir tests/test-configs/no-mast-baseline \
  --provider gateway --model gemma4:31b-cloud
```

## Installation

Copy the skill directories into your Hermes skills folder:

```bash
# For Hermes Agent
cp -r skills/mast-taxonomy ~/.hermes/skills/research/
cp -r skills/agent-workspace-interview ~/.hermes/skills/software-development/
cp -r skills/mast-audit ~/.hermes/skills/software-development/
```

### MCP Server Installation (mast-enforce)

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mast-enforce:
    command: "uvx"
    args: ["--from", "/path/to/mast-skills/mcp/mast-enforce", "mast-enforce"]
```

Or run directly:

```bash
cd mcp/mast-enforce && fastmcp run server.py
```

Or install as a package:

```bash
pip install -e mcp/mast-enforce
```

## Sources

- Paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657) (arXiv:2503.13657)
- Authors: Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, Stoica (UC Berkeley)
- OpenClaw workspace guide: [elegantsoftwaresolutions.com](https://www.elegantsoftwaresolutions.com/blog/openclaw-workspace-markdown-files-guide)

## License

MIT