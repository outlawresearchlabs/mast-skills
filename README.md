# MAST Skills

Hermes Agent skills for preventing all 14 failure modes identified in the MAST (Multi-Agent System Failure Taxonomy) from the UC Berkeley paper ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657).

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

Pure knowledge base of the 14 failure modes, their definitions, prevalence percentages, solution strategies, and case study results from the paper.

**Use when**:
- Debugging a failing multi-agent system
- Answering "why does my agent keep doing X?"
- Designing a new multi-agent architecture
- Any scenario where you need to understand or reference MAST failure patterns

### 2. agent-workspace-interview (Config Generator)

Runs a 5-question interview and generates MAST-hardened workspace configuration files for any agent platform.

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

### 3. mast-audit (Config Auditor)

Scans existing agent config files against all 14 MAST failure modes. Scores each mode as DEFENDED / PARTIAL / UNDEFENDED, calculates weighted coverage, and outputs prioritized gaps with copy-paste fix snippets.

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

## Installation

Copy the skill directories into your Hermes skills folder:

```bash
# For Hermes Agent
cp -r skills/mast-taxonomy ~/.hermes/skills/research/
cp -r skills/agent-workspace-interview ~/.hermes/skills/software-development/
cp -r skills/mast-audit ~/.hermes/skills/software-development/
```

## Key Findings from the Paper

- Better system design with the **same** model yields up to **+15.6%** improvement
- No one-size-fits-all solution -- each MAS has different failure profiles
- Model choice matters but is insufficient alone
- Current verifiers only do superficial checks -- multi-level verification is needed
- Modular agents with clear, simple roles outperform complex multi-task agents

## Sources

- Paper: ["Why Do Multi-Agent LLM Systems Fail?"](https://arxiv.org/abs/2503.13657) (arXiv:2503.13657)
- Authors: Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, Stoica (UC Berkeley)
- OpenClaw workspace guide: [elegantsoftwaresolutions.com](https://www.elegantsoftwaresolutions.com/blog/openclaw-workspace-markdown-files-guide)

## License

MIT