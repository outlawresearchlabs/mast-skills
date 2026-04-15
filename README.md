# MAST Skills

Hermes Agent skills for preventing all 14 failure modes identified in the MAST (Multi-Agent System Failure Taxonomy) from the UC Berkeley paper ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657).

## Validated Results

**14/14 MAST failure modes defeated. 100% prevalence defended. Tested across 2 model families.**

| Model | Baseline (no MAST) | MAST-Hardened v4 | Improvement |
|---|---|---|---|
| gemma4:31b-cloud | 10/14 (70.9%) | **14/14 (100%)** | **+29.1%** |
| gpt-4o | 11/14 (81.2%) | **14/14 (100%)** | **+18.8%** |

Each failure mode tested via failure injection: a deliberate trigger prompt designed to cause the failure, with LLM-as-judge evaluation of whether the response defends against it.

## What Problem This Solves

Multi-agent LLM systems fail in predictable ways. The MAST paper analyzed 1,600+ execution traces across 7 popular frameworks and identified 14 failure modes clustered into 3 categories:

| Category | Prevalence | Description |
|---|---|---|
| FC1: System Design Issues | 44.2% | Flaws in architecture, prompts, state management |
| FC2: Inter-Agent Misalignment | 32.4% | Breakdown in inter-agent information flow and coordination |
| FC3: Task Verification | 23.5% | Inadequate verification or premature termination |

The top 5 failure modes alone account for 60.1% of all observed failures. These skills embed defenses against all 14 modes directly into agent workspace configuration files.

## The 3 Skills

### 1. mast-taxonomy (Reference Knowledge)

Pure knowledge base of the 14 failure modes, their definitions, prevalence percentages, solution strategies, case study results from the paper, and dynamic test results across models.

**Use when**:
- Debugging a failing multi-agent system
- Answering "why does my agent keep doing X?"
- Designing a new multi-agent architecture
- Any scenario where you need to understand or reference MAST failure patterns

### 2. agent-workspace-interview (Config Generator) — v4

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
  tests/
    test_harness.py          # Failure injection test harness
    mast_judge.py            # LLM-as-judge evaluator
    validate_judge.py        # Judge validation script
    test-configs/
      mast-hardened/         # v4 MAST-hardened configs (14/14)
      no-mast-baseline/      # Baseline configs (no defenses)
    results/                 # Test result JSON files
    RESULTS.md               # Full results with iteration history
    chatdev-setup/           # ChatDev paper reproduction setup
```

## Dynamic Testing

Run the failure injection test harness against any model:

```bash
# Local gateway (Ollama-compatible)
cd /tmp/mast-skills && python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --provider gateway --model gemma4:31b-cloud

# OpenAI API
python3 -u tests/test_harness.py \
  --config-dir tests/test-configs/mast-hardened \
  --provider openai --model gpt-4o

# Quick test (top 5 modes = 60.1% of failures)
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

## Sources

- Paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657) (arXiv:2503.13657)
- Authors: Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, Stoica (UC Berkeley)
- OpenClaw workspace guide: [elegantsoftwaresolutions.com](https://www.elegantsoftwaresolutions.com/blog/openclaw-workspace-markdown-files-guide)

## License

MIT