# MAST Testing Infrastructure

## Overview

Three complementary approaches to testing MAST-hardened agent configs, plus the official paper evaluation pipeline.

## 1. Internal Validation (Static Audit)

**Status**: COMPLETE -- Results in RESULTS.md

Automated keyword-based audit of generated config files against all 14 MAST failure modes.

Results:
- MAST-hardened configs: 13/14 DEFENDED (98.5% prevalence covered)
- Baseline configs (no MAST defenses): 0/14 DEFENDED (0% prevalence covered)
- Only gap: FM-1.2 Disobey role specification (1.5% prevalence -- trivial to fix)

## 2. Failure Injection Tests

**File**: test_harness.py
**Status**: Ready to run (requires OpenAI or Anthropic API key)

14 test prompts that deliberately trigger each MAST failure mode, with LLM-as-judge evaluation.

```bash
# Test MAST-hardened configs vs baseline
python test_harness.py \
  --config-dir test-configs/mast-hardened \
  --baseline-dir test-configs/no-mast-baseline \
  --provider openai

# Quick test: top 5 modes only (covers 62.2% of failures)
python test_harness.py \
  --config-dir test-configs/mast-hardened \
  --top5 \
  --provider openai

# Test specific modes
python test_harness.py \
  --config-dir test-configs/mast-hardened \
  --mode FM-1.3 --mode FM-2.6 \
  --provider anthropic
```

## 3. Official MAST LLM-as-Judge Pipeline

**File**: mast_judge.py
**Status**: Ready to run (requires API key + optionally HuggingFace access)

Adapted from the paper authors' official evaluation pipeline at
https://github.com/multi-agent-systems-failure-taxonomy/MAST

Uses the same prompt format and evaluation structure the paper authors used (with o1 as judge).

This is the most rigorous approach because:
- Uses the canonical definitions.txt and examples.txt from the paper authors
- Matches the exact evaluation format from the paper
- Can be validated against HuggingFace human annotations (ground truth)
- Inter-annotator agreement data available for calibration

```bash
# Evaluate a single trace
python mast_judge.py --trace path/to/trace.json --provider openai --model gpt-4o

# Evaluate against HuggingFace ground truth (validates our judge)
python mast_judge.py --huggingface --sample 50 --provider openai --model gpt-4o

# Batch evaluate traces
python mast_judge.py --traces-dir /path/to/traces --provider anthropic

# Validate our test harness against official ground truth
python mast_judge.py --validate
```

### HuggingFace Dataset

The paper authors released 1K+ annotated traces:
- Full dataset: `mcemri/MAD` -> `MAD_full_dataset.json`
- Human-labeled: `mcemri/MAD` -> `MAD_human_labelled_dataset.json`

```python
from huggingface_hub import hf_hub_download
REPO_ID = "mcemri/MAD"
file_path = hf_hub_download(repo_id=REPO_ID, filename="MAD_human_labelled_dataset.json", repo_type="dataset")
```

## 4. ChatDev Paper Reproduction

**Directory**: chatdev-setup/
**Status**: ChatDev cloned, venv installed, MAST-hardened YAML created

Reproduces the paper's ChatDev experiments (Table 2) with:
- Baseline prompts vs MAST-hardened prompts
- HumanEval and ProgramDev benchmarks
- MAST defense markers for automated detection (<LOOP-DETECTED>, <VERIFY>, <CLARIFY>)

```bash
cd chatdev-setup
bash setup.sh          # Clone + install ChatDev
bash run_baseline.sh   # Run with baseline prompts
bash run_mast.sh       # Run with MAST-hardened prompts
python compare_results.py  # Compare results
```

Expected improvement: >=9.4% (paper showed up to +15.6% with partial MAST defenses)

## Testing Strategy (Recommended Order)

1. **Run internal validation** (done, instant, no cost)
2. **Run failure injection** on MAST-hardened vs baseline (14 API calls, ~$0.50)
3. **Validate judge accuracy** against HuggingFace human annotations (50 API calls, ~$2)
4. **Run ChatDev benchmarks** (expensive, hours of runtime, ~$50+ in API costs)
5. **Run official judge** on your own agent traces (variable cost)

## Validation Against Ground Truth

The key question: does our LLM-as-judge agree with the paper's human annotators?

Run this:
```bash
python mast_judge.py --huggingface --sample 50 --provider openai --model gpt-4o --output judge_validation.json
```

Then compare judge_validation.json failure mode labels against the human annotations.
Target: >=80% agreement per mode (paper authors achieved high inter-annotator agreement).

## Sources

- Paper: arXiv:2503.13657
- Official repo: https://github.com/multi-agent-systems-failure-taxonomy/MAST
- HuggingFace dataset: https://huggingface.co/datasets/mcemri/MAD
- ChatDev: https://github.com/OpenBMB/ChatDev