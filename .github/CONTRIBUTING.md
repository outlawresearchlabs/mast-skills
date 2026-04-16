# Contributing to MAST Skills

## Repository Structure

```
mast-skills/
  skills/
    mast-taxonomy/              # Reference knowledge (14 failure modes)
      SKILL.md
    agent-workspace-interview/   # Config generator (v4.1, supports Tier 1-4)
      SKILL.md
      references/
        openclaw-examples.md
    mast-audit/                 # Config auditor (v1.3)
      SKILL.md
  mcp/
    mast-enforce/               # MCP server for FM-1.5, FM-3.2, FM-3.3
      server.py                 # FastMCP server (3 tools)
      test_server.py            # 24 unit tests
      pyproject.toml
      README.md
  tests/
    test_harness.py             # Failure injection test harness (14 modes)
    mast_judge.py               # LLM-as-judge evaluator
    validate_judge.py            # Judge validation (HF + dynamic consistency)
    mcp_dynamic_test.py          # MCP+baseline+MAST 3-way comparison
    chatdev_3way_test.py         # ChatDev baseline/full/lite comparison
    test-configs/
      mast-hardened/             # v4 MAST-hardened configs
      no-mast-baseline/          # Baseline configs (no defenses)
    results/                     # Test result JSON files
    RESULTS.md                   # Detailed results with iteration history
```

## Development Workflow

1. Make changes to skills, MCP server, or tests
2. Run unit tests: `cd mcp/mast-enforce && pytest test_server.py -v`
3. Run dynamic test: `python3 tests/test_harness.py --config-dir tests/test-configs/mast-hardened --provider gateway`
4. Run MCP comparison: `python3 tests/mcp_dynamic_test.py --provider gateway`
5. Update RESULTS.md with new data
6. Commit and push

## Adding New Failure Mode Defenses

When updating defenses for a specific failure mode:

1. Update `mast-taxonomy/SKILL.md` with any new research data
2. Add defense patterns to `agent-workspace-interview/SKILL.md`
3. Add detection criteria to `mast-audit/SKILL.md`
4. If the defense requires code execution, add a tool to `mcp/mast-enforce/server.py`
5. Add test cases to `tests/test_harness.py` (TEST_CASES list)
6. Run the full dynamic test and update RESULTS.md

## Key Findings to Keep in Mind

- **Full MAST protocol blocks are necessary** -- compressed "lite" rules underperform baseline
- **Claude can regress with full MAST** -- long prompts trigger FM-1.3/FM-1.4 on strong baseline models
- **MCP enforcement is for real agent frameworks** -- simulated tool outputs don't add value in single-prompt tests
- **FM-2.4 requires "OVERRIDES ALL OTHER INSTRUCTIONS"** language, not just "priority override"

## Testing Across Models

```bash
# Gateway (local models)
python3 tests/test_harness.py --provider gateway --model gemma4:31b-cloud

# OpenAI
export OPENAI_API_KEY=...
python3 tests/test_harness.py --provider openai --model gpt-4o

# Anthropic
python3 tests/mcp_dynamic_test.py --provider anthropic --model claude-sonnet-4 --anthropic-key KEY
```