# ChatDev MAST Benchmark Reproduction

This directory contains MAST-hardened prompt variants and benchmark scripts for
evaluating ChatDev against the HumanEval benchmark with and without MAST defenses.

## What is MAST?

MAST (Multi-Agent System Testing) defines 14 failure modes for multi-agent LLM systems.
This setup embeds defenses against 7 key failure modes into ChatDev's agent role prompts:

| MAST Code | Failure Mode | Defense Applied |
|-----------|-------------|-----------------|
| FM-1.3    | Infinite loops / re-entry cycles | Anti-loop protocol: check if step already done before repeating |
| FM-1.5    | Premature / delayed termination | Explicit termination conditions before each task |
| FM-2.2    | Assumption without clarification | Ask for clarification when uncertain |
| FM-2.3    | Objective drift / scope creep | Objective re-centering: verify actions serve the goal |
| FM-2.6    | Reasoning-action misalignment | Alignment check between reasoning and chosen action |
| FM-3.2    | Unverified outputs | Mandatory verification before delivering |
| FM-3.3    | Shallow single-level verification | Multi-level verification (low-level correctness + high-level objectives) |

## ChatDev Roles Modified

- **Chief Executive Officer** (CEO) - Decision-making, strategy
- **Programmer** (appears in 5 nodes: Coding, Code Complete, Code Review, Test Error Summary, Test Modification)
- **Code Reviewer** - Code quality assessment
- **Software Test Engineer** - Testing and bug reporting
- **Chief Product Officer** (CPO) - Documentation and product specs

## File Inventory

### Core Files
- `ChatDev_v1_mast.yaml` - MAST-hardened ChatDev workflow configuration
- `generate_mast_yaml.py` - Script to generate MAST YAML from baseline
- `setup.sh` - Complete setup script (clone, install, generate)

### Role Prompt Files (standalone references)
- `ceo_prompt.txt` - MAST-hardened CEO prompt
- `programmer_prompt.txt` - MAST-hardened Programmer prompt
- `code_reviewer_prompt.txt` - MAST-hardened Code Reviewer prompt
- `test_engineer_prompt.txt` - MAST-hardened Test Engineer prompt
- `cpo_prompt.txt` - MAST-hardened CPO prompt

### Benchmark Scripts
- `run_baseline.sh` - Run HumanEval with baseline ChatDev prompts
- `run_mast.sh` - Run HumanEval with MAST-hardened prompts
- `compare_results.py` - Comparison and analysis report generator

### Results (created after running benchmarks)
- `results/baseline/` - Baseline run results
- `results/mast/` - MAST-hardened run results
- `results/comparison_report.txt` - Generated comparison report

## Quick Start

```bash
# 1. Full setup (clone + install + generate)
cd /tmp/mast-chatdev-setup/ChatDev
./mast_hardened/setup.sh

# 2a. Run benchmarks with LOCAL GATEWAY (free, no API key needed)
source venv/bin/activate
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1

# Run on a subset for quick testing (5 problems)
./mast_hardened/run_baseline.sh --subset 5 --model gemma4:31b-cloud
./mast_hardened/run_mast.sh --subset 5 --model gemma4:31b-cloud

# Full run with a different model
./mast_hardened/run_baseline.sh --model glm-5.1:cloud
./mast_hardened/run_mast.sh --model glm-5.1:cloud

# 2b. Run benchmarks with OpenAI API
source venv/bin/activate
export OPENAI_API_KEY=sk-...

# Run on a subset for quick testing
./mast_hardened/run_baseline.sh --subset 5
./mast_hardened/run_mast.sh --subset 5

# Full run (164 problems, takes hours)
./mast_hardened/run_baseline.sh
./mast_hardened/run_mast.sh

# 3. Compare results
python mast_hardened/compare_results.py
```

## Benchmark Script Options

```bash
./run_baseline.sh [OPTIONS]    # Same for run_mast.sh
  --subset N      Run only N problems (default: 0 = all 164)
  --start IDX     Start from problem index IDX (default: 0)
  --model MODEL   Use MODEL instead of gpt-4o
```

## How MAST Hardening is Embedded

Each agent role prompt has a `=== MAST HARDENING PROTOCOLS ===` section appended
with 7 protocol blocks. Each protocol:

1. Is labeled with its MAST failure mode code (e.g., `[FM-1.3 Anti-Loop Protocol]`)
2. Provides specific behavioral instructions for that role
3. Defines explicit output markers (e.g., `<LOOP-DETECTED>`, `<VERIFY>`, `<CLARIFY>`)
4. Includes role-specific examples and constraints

These markers are detectable in the output logs, allowing automated measurement
of whether MAST defenses are triggering and whether they affect task performance.

## Evaluation Methodology

1. Run identical HumanEval problems through both baseline and MAST configs
2. Extract generated code from ChatDev outputs
3. Evaluate with `human-eval` execution-based testing
4. Compare:
   - Pass@1 rates (correctness)
   - Time per problem (efficiency overhead)
   - MAST marker counts (defense activation)
   - Loop/violation rates (failure mode reduction)

## Notes

- ChatDev uses function-calling agents that write code to a workspace
- Each HumanEval problem is wrapped as a ChatDev task prompt
- The MAST YAML uses `${COMMON_PROMPT}` and `${BASE_URL}`/`${API_KEY}` variables
  resolved at runtime by ChatDev's config loader
- Results include both raw ChatDev output and extracted completions for HumanEval evaluation