# ProgramDev Benchmark Test Plan

## Background

### What We Tested Wrong (HumanEval)
We ran 7 models on HumanEval (single-function coding) and found middleware is neutral (96-100% baseline). HumanEval is too easy to trigger multi-agent coordination failures.

### What The Paper Actually Tested (ProgramDev)
The MAST paper (arXiv:2503.13657v2) evaluated ChatDev on **ProgramDev-v0**: 30 application-level tasks (games, tools). Results from **Table 4, page 32**:

| Configuration | ProgramDev-v0 | HumanEval |
|---|---|---|
| Baseline (GPT-3.5-turbo) | 25.0% | 89.6% |
| Improved prompts | 34.4% | 90.3% |
| New topology (cyclic) | 40.6% | 91.5% |

The paper used their **MAST LLM-as-a-Judge annotator** to evaluate traces. They also used 6 human annotators (Cohen's Kappa = 0.88).

### Why ProgramDev Matters
- Baseline is only 25% vs 96-100% on HumanEval
- Tasks require multi-agent coordination (CEO→CTO→Programmer→Reviewer→Tester)
- Triggers the actual MAST failure modes: FM-1.3 (step repetition), FM-2.6 (reasoning-action mismatch), FM-3.2 (incomplete verification)
- Room for middleware to actually help

---

## Existing Work (Don't Redo)

### Already built:
- `chatdev_benchmark.py` - HumanEval benchmark runner (DONE, but wrong benchmark)
- `test_harness.py` - Dynamic failure injection for 14 MAST modes (DONE, 14/14 pass)
- `mast_judge.py` - LLM-as-a-Judge pipeline adapted from paper (DONE)
- Anthropic provider for ChatDev (DONE)
- YAML configs for all 7 models (DONE)
- Task name collision fix (DONE - model name in task name)

### Need to build:
- `programdev_benchmark.py` - ProgramDev benchmark runner (NEW)
- Evaluation pipeline for ProgramDev tasks (NEW)

---

## ProgramDev Dataset

**Location:** `/tmp/mast-official/traces/programdev/programdev_dataset.json`
**Format:** 30 tasks, each with `project_name` and `description`

### Task List:
1. Checkers - 8x8 board game with capture/kinging rules
2. Sudoku - 9x9 puzzle with row/column/subgrid constraints
3. TheCrossword - Grid puzzle with across/down clues
4. DetectPalindromes - Palindrome detection in text files
5. BudgetTracker - Expense/savings monitor
6. FibonacciNumbers - Fibonacci generator
7. TicTacToe - Two-player game with UI
8. Gomoku - 15x15 board, two players
9. Chess - Full chess with castling, en passant, promotion
10. 2048 - 4x4 tile merging game
11. Tiny Rouge - Roguelike on 80x80 grid
12. Wordle - Daily 5-letter word game
13. Minesweeper - 3 difficulty levels
14. ConnectionsNYT - Group 16 words into 4 sets
15. StrandsNYT - Word search puzzle
16. SnakeGame - Classic snake with directional control
17. ConnectFour - Two-player disc-dropping game
18. TriviaQuiz - Multiple-choice quiz
19. DouDizhuPoker - Chinese poker for 3 players
20. Tetris - Falling tetrominoes with rotation/clearing
21. ReversiOthello - Disc-flipping board game
22. StrandsGame - Word segmentation puzzle
23. MonopolyGo - Simplified Monopoly
24. EpisodeChooseYourStory - Interactive branching narrative
25. CandyCrush - Match-3 puzzle
26. FlappyBird - Side-scrolling bird game
27. TextBasedSpaceInvaders - Text-based shooter
28. GoldMiner - Timed claw-grabbing game
29. Pong - Two-player paddle game
30. Mastermind - Code-breaking game

### Reference Traces:
The paper's ChatDev traces for each task are at:
`/tmp/mast-official/traces/programdev/chatdev/<TaskName>/`

Each contains: generated .py files, meta.txt, execution logs, configs.

---

## Evaluation Methodology

### Level 1: Executability (Automated)
**Does main.py run without crashing?**
```
cd code_workspace
timeout 30 python3 main.py < /dev/null
# exit code 0 = executable, non-zero = crash
```
- Captures: ImportError, SyntaxError, NameError, runtime crashes
- Quick, automated, no LLM cost
- This alone won't catch "runs but wrong behavior" bugs

### Level 2: Code Completeness (Automated)
**Did the pipeline produce meaningful code?**
- Count .py files generated
- Check if main.py exists
- Check total lines of code (< 10 lines = likely empty/stub)
- Check if key game elements are present (board, player, move, etc.)

### Level 3: Functional Correctness (LLM-as-Judge)
**Does the application meet the spec?**
Use `mast_judge.py` or a custom evaluation prompt:

```
Given the task description:
"{task_description}"

And the generated code:
"{generated_code}"

Evaluate:
1. Does the code implement the core functionality described? (Y/N)
2. Would a user be able to use this as described? (Y/N)
3. Are there obvious bugs that would prevent basic operation? (Y/N)
4. Rate overall correctness: PASS / PARTIAL / FAIL

A PASS means: the code runs, implements the core feature, and a user
could actually use it for the described purpose.
A PARTIAL means: some functionality works but key features are missing or broken.
A FAIL means: doesn't run, wrong functionality, or fundamentally broken.
```

### Level 4: MAST Failure Mode Analysis (LLM-as-Judge)
**What specific failure modes caused failures?**
For each FAIL/PARTIAL result, run the MAST annotator to classify:
- Which of the 14 failure modes occurred?
- At which conversation stage?
- Which agent was responsible?

This tells us if the middleware is reducing specific failure modes.

---

## Test Configurations

### Phase 1: Baseline vs Inprocess (Current Priority)
Test on 5 models (skip Opus to save money):

| Model | baseline YAML | inprocess YAML |
|---|---|---|
| MiniMax-M2.7 | ChatDev_v1_baseline_minimax.yaml | ChatDev_v1_inprocess_minimax.yaml |
| GPT-5.4 | ChatDev_v1_baseline_gpt54.yaml | ChatDev_v1_inprocess_gpt54.yaml |
| GLM-5.1 | ChatDev_v1_baseline_glm51.yaml | ChatDev_v1_inprocess_glm51.yaml |
| Qwen 3.5 | ChatDev_v1_baseline_qwen35.yaml | ChatDev_v1_inprocess_qwen35.yaml |
| Gemma4 MoE | ChatDev_v1_baseline_gemma4moe.yaml | ChatDev_v1_inprocess_gemma4moe.yaml |

### Phase 2: Lean + Inprocess (If Phase 1 shows middleware helps)
- Same 5 models
- Add lean MAST prompts on top of state gates

### Phase 3: Full MAST + Inprocess (If Phase 2 shows improvement)
- Best-performing models only

---

## Execution Plan

### Step 1: Build programdev_benchmark.py
- Load 30 tasks from programdev_dataset.json
- Feed task description to ChatDev via run.py
- Include model name in task name (avoid collision bug)
- 1 rep per task initially (30 runs per config)
- 15-minute timeout per task (these are complex)
- Save results to results/programdev/

### Step 2: Validate with MiniMax first
- Run MiniMax baseline on 5 easy tasks: TicTacToe, DetectPalindromes, FibonacciNumbers, BudgetTracker, Mastermind
- Verify: code extraction works, evaluation pipeline works, no collisions
- Fix any issues before scaling

### Step 3: Run MiniMax full (30 tasks x 2 configs)
- baseline + inprocess on all 30 tasks
- Evaluate Level 1 (executability) + Level 3 (LLM-as-judge)

### Step 4: Run remaining 4 models
- GPT-5.4, GLM-5.1, Qwen 3.5, Gemma4 MoE
- Same 30 tasks x 2 configs each

### Step 5: Analyze
- Per-model: baseline vs inprocess pass rate
- Cross-model: is the middleware effect consistent?
- MAST failure mode breakdown for failures
- Compare to paper's Table 4 numbers

---

## Known Bugs To Avoid
1. **Task name collision**: MUST include model name in task name
2. **Warehouse cleanup**: Clean bm_*/pd_* dirs before fresh runs
3. **Anthropic base_url**: No trailing /v1
4. **Credits**: Check API credits before starting
5. **Code extraction**: extractor picks latest matching dir - duplicates cause false failures
6. **Timeout**: ProgramDev tasks need 15min+ (more complex than HumanEval)

---

## API Keys & Rate Limits
All in `/tmp/ChatDev/.env`:
- OPENAI_API_KEY → GPT-5.4
- ANTHROPIC_API_KEY → Opus 4.7 (skip in ProgramDev to save money)
- MINIMAX_API_KEY → MiniMax-M2.7 (4500 req/5hr on current plan)
- GEMINI_API_KEY → Gemma4 MoE 26B
- BASE_URL/API_KEY → Ollama gateway (GLM-5.1, Gemma4 31B, Qwen 3.5)

## Key Files
- ProgramDev dataset: `/tmp/mast-official/traces/programdev/programdev_dataset.json`
- Reference traces: `/tmp/mast-official/traces/programdev/chatdev/`
- MAST judge: `/tmp/mast-skills/tests/mast_judge.py`
- Dynamic test harness: `/tmp/mast-skills/tests/test_harness.py`
- HumanEval benchmark (done): `/tmp/mast-skills/tests/chatdev_benchmark.py`
- YAML configs: `/tmp/ChatDev/yaml_instance/`
- Paper: arXiv:2503.13657v2 (Table 4, page 32 has key results)
