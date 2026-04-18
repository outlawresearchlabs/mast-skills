# MAST Benchmark Plan

## What We've Proven So Far

### HumanEval (WRONG benchmark - too easy)
Middleware is neutral on single-function coding tasks. All models score 96-100%.

| Model | Baseline | Inprocess | Delta |
|---|---|---|---|
| Opus 4.7 | 100% | 100% | 0pp |
| GLM-5.1 | 100% | 100% | 0pp |
| Gemma4 31B | 98% | pending | - |
| GPT-5.4 | 96% | 96% | 0pp |
| Qwen 3.5 | 96% | 96% | 0pp |
| MiniMax | 96% | 92% | -4pp |
| Gemma4 MoE | pending | pending | - |

**Conclusion:** HumanEval doesn't trigger multi-agent coordination failures. Not the right test.

### Dynamic Failure Injection (14 MAST triggers)
MAST skill configs DO work at component level:
- Gemma4: 14/14 PASS (100%)
- GPT-4o: 14/14 PASS (100%)
- Claude Sonnet: 13/14 PASS (97.2%)

**Conclusion:** The defenses work in isolation. Need whole-system validation on hard tasks.

---

## What We Need To Do Next

### Phase 1: ProgramDev Benchmark (THE RIGHT TEST)
The MAST paper used ProgramDev - 32 game/app projects that require real multi-agent coordination.

**Dataset:** `/tmp/mast-official/traces/programdev/programdev_dataset.json`

**Paper baseline:** 25.0% (ChatDev with GPT-3.5-turbo)
- With improved prompts: 34.4% (+9.4pp)
- With cyclic topology: 40.6% (+15.6pp)

**Tasks include:** Chess, Tetris, Snake, 2048, Sudoku, Minesweeper, Wordle, Checkers, etc.

**Why this works:** These tasks trigger the actual MAST failure modes:
- FM-1.3 (step repetition): Agent rewrites the same game logic repeatedly
- FM-2.6 (reasoning-action mismatch): Agent plans one architecture, builds another
- FM-3.2 (incomplete verification): Code compiles but crashes at runtime
- FM-1.1 (spec disobedience): Agent ignores game rules in spec

**What to build:**
- [ ] ProgramDev benchmark runner (like chatdev_benchmark.py but for app tasks)
- [ ] Evaluation criteria (does the app run? does it meet the spec?)
- [ ] Include model name in task names (learned from HumanEval collision bug)

**Models to test (skip Opus to save money):**
- GPT-5.4 (baseline + inprocess)
- GLM-5.1 (baseline + inprocess)
- MiniMax (baseline + inprocess)
- Qwen 3.5 (baseline + inprocess)
- Gemma4 MoE (baseline + inprocess)

### Phase 2: Lean + Inprocess (if Phase 1 shows middleware helps)
Stack minimal MAST prompts with in-process middleware:
- Same 5 models
- Config: lean prompts + state gates
- Compare against Phase 1 baseline and inprocess-only results

### Phase 3: Full MAST + Inprocess (if Phase 2 shows improvement)
Full MAST prompt defenses + middleware on best-performing models only.

---

## Bugs Fixed (Don't Repeat)
1. **Warehouse collision:** Task names must include model name (`bm_HumanEval_2_gpt54_inprocess_r1`)
2. **Anthropic base_url:** Must be `https://api.anthropic.com` NOT `https://api.anthropic.com/v1`
3. **Anthropic timeout:** Don't put `timeout` in the API payload body
4. **Credits:** Check API credits before running expensive benchmarks
5. **Clean warehouse:** Always `rm -rf /tmp/ChatDev/WareHouse/bm_*` before fresh runs

---

## API Keys
All in `/tmp/ChatDev/.env`:
- OPENAI_API_KEY (GPT-5.4)
- ANTHROPIC_API_KEY (Opus 4.7)
- MINIMAX_API_KEY (MiniMax-M2.7)
- GEMINI_API_KEY (Gemma4 MoE via Gemini API)
- BASE_URL / API_KEY (Ollama gateway for GLM-5.1, Gemma4 31B, Qwen 3.5)

## Key Files
- Benchmark script: `/tmp/mast-skills/tests/chatdev_benchmark.py`
- ProgramDev dataset: `/tmp/mast-official/traces/programdev/programdev_dataset.json`
- Dynamic test harness: `/tmp/mast-skills/tests/test_harness.py`
- MAST taxonomy: `/tmp/mast-skills/skills/mast-taxonomy/SKILL.md`
- Anthropic provider: `/tmp/ChatDev/runtime/node/agent/providers/anthropic_provider.py`
- YAML configs: `/tmp/ChatDev/yaml_instance/ChatDev_v1_*.yaml`
- MAST findings: `/tmp/mast-skills/FINDINGS.md`
