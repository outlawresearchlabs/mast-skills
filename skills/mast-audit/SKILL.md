---
name: mast-audit
description: Audits existing AI agent config files against all 14 MAST failure modes. Reports coverage, gaps, and prioritized fixes by failure prevalence. Works with any platform's config format.
version: 1.0
category: software-development
---

# MAST Audit

Audit existing agent workspace config files against all 14 MAST failure modes. Reports what's defended, what's missing, and prioritizes fixes by failure prevalence.

**Prerequisite**: Load `mast-taxonomy` skill for full failure mode definitions.

## When to Use

- You have existing agent config files and want to know if they're MAST-hardened
- Your multi-agent system is failing and you need to know which failure modes aren't defended
- You're reviewing someone else's agent setup
- You just generated files with agent-workspace-interview and want to verify coverage
- You're comparing two different agent configurations

## Process

### Step 1: Collect Config Files

Ask the user:

"Where are your agent config files? Provide path(s) or paste content. Common locations:
- OpenClaw: workspace/ directory (SOUL.md, rules file, USER.md, MEMORY.md, BOOTSTRAP.md, PROMPT.md)
- Anthropic CLI: CLAUDE.md in project root
- Anysphere: .cursorrules in project root
- Codeium: .windsurfrules in project root
- Cline: .clinerules in project root
- Other: any markdown/text config file"

Use read_file or terminal to load all config files. If a directory is given, read all .md and .rules files in it.

### Step 2: Check Each Failure Mode

For each of the 14 MAST failure modes, scan the config files for evidence of a defense. A defense is present if the config contains instructions that would prevent or mitigate that failure mode.

Score each mode:

| Score | Meaning |
|---|---|
| DEFENDED | Explicit defense found that directly addresses this failure mode |
| PARTIAL | Some related instruction exists but doesn't fully address the mode |
| UNDEFENDED | No defense found |

#### Detection Rules (what to look for)

| Mode | Detection Criteria |
|---|---|
| FM-1.1 Disobey task spec (11.8%) | Look for: restate-requirements-before-acting, task constraints section, "verify against requirements" |
| FM-1.2 Disobey role spec (1.5%) | Look for: explicit role boundary ("you are X, not Y"), role specification, scope limitations |
| FM-1.3 Step repetition (15.7%) | Look for: check-before-repeat, progress tracking, mark-completed-steps, anti-loop, "already done" |
| FM-1.4 Loss of conversation history (2.8%) | Look for: session checkpoint, memory summarization, context preservation, state logging |
| FM-1.5 Unaware of termination (12.4%) | Look for: stop conditions, completion criteria, "when to stop", termination triggers |
| FM-2.1 Conversation reset (2.2%) | Look for: "never restart unless asked", continuity instruction, no-reset rule |
| FM-2.2 Fail to ask clarification (6.8%) | Look for: "when in doubt, ask", clarify-ambiguity, ask-before-assuming |
| FM-2.3 Task derailment (7.4%) | Look for: objective re-centering, "verify action serves goal", stay-on-task, drift prevention |
| FM-2.4 Information withholding (0.85%) | Look for: "share all findings", "communicate relevant info", no-withholding rule |
| FM-2.5 Ignored other input (1.9%) | Look for: "acknowledge peer input", "consider other agents", respond-to-collaborators |
| FM-2.6 Reasoning-action mismatch (13.2%) | Look for: alignment check, "if reasoning and action diverge, stop", consistency verification |
| FM-3.1 Premature termination (6.2%) | Look for: "check all criteria before done", no-early-stop, completion-checklist |
| FM-3.2 No/incomplete verification (8.2%) | Look for: mandatory verification, verify-before-deliver, self-check step, test requirement |
| FM-3.3 Incorrect verification (9.1%) | Look for: multi-level verification, "verify objectives not just syntax", high-level + low-level checks |

#### Partial Credit Guidance

Score PARTIAL when:
- A general "be careful" or "check your work" instruction exists but isn't specific to the failure mode
- A defense exists for a different but related failure mode that partially covers this one
- The instruction is present but buried in a wall of text (likely to be ignored by the agent)

Score DEFENDED when:
- An explicit, specific instruction targets this exact failure pattern
- The instruction is in a prominent position (heading, first bullet, rules section)
- The instruction includes what to do, not just what not to do

### Step 3: Calculate Coverage

```
Overall Coverage: [defended + 0.5 * partial] / 14 * 100%

FC1 Coverage: [defended + 0.5 * partial] / 5 * 100%  (System Design)
FC2 Coverage: [defended + 0.5 * partial] / 6 * 100%  (Inter-Agent)
FC3 Coverage: [defended + 0.5 * partial] / 3 * 100%  (Verification)
```

Also calculate weighted coverage by prevalence:
```
Weighted Coverage: sum of (prevalence% for each DEFENDED mode) / total prevalence (100%)
```
This is more meaningful -- it shows what % of actual failures you're protected against.

### Step 4: Prioritize Gaps

Sort undefended and partial modes by prevalence (highest first). This tells the user where to invest effort first.

```
Priority Gaps (undefended modes sorted by failure prevalence):
1. FM-1.3 Step repetition (15.7%) -- UNDEFENDED
2. FM-2.6 Reasoning-action mismatch (13.2%) -- PARTIAL
3. ...
```

### Step 5: Generate Fixes

For each gap (UNDEFENDED or PARTIAL), output a copy-paste snippet the user can add to their config to close the gap. Use the defense patterns from the mast-taxonomy skill.

```
RECOMMENDED FIXES (sorted by impact):

--- FM-1.3 Step repetition (15.7%) [UNDEFENDED] ---
Add to personality/identity section:
  ## Anti-Loop Protocol
  - Before repeating any step, check: has this already been completed?
  - If about to repeat an action, stop and state what has already been done
  - Track progress explicitly: mark completed steps

--- FM-2.6 Reasoning-action mismatch (13.2%) [PARTIAL] ---
Add to operational rules:
  ## Alignment Check
  - If reasoning says X but you are about to do Y, STOP
  - Resolve the mismatch before proceeding
  - State both the reasoning and the intended action to surface conflicts

...
```

### Step 6: Output Report

```
===========================================
MAST AUDIT REPORT
===========================================

Config files analyzed:
  [file path] ([word count] words)
  ...

-------------------------------------------
FAILURE MODE COVERAGE
-------------------------------------------

DEFENDED (score [N]/14):
  FM-1.3 Step repetition (15.7%)
  FM-3.2 No/incomplete verification (8.2%)
  ...

PARTIAL (score [N]/14):
  FM-2.6 Reasoning-action mismatch (13.2%)
  ...

UNDEFENDED (score [N]/14):
  FM-1.1 Disobey task spec (11.8%)
  FM-1.5 Unaware of termination (12.4%)
  ...

-------------------------------------------
COVERAGE SCORES
-------------------------------------------

Overall:      [N]% ([defended+partial]/14 modes addressed)
FC1 Design:   [N]% ([N]/5 modes)
FC2 Alignment:[N]% ([N]/6 modes)
FC3 Verification: [N]% ([N]/3 modes)

Weighted by prevalence: [N]% of observed failures are defended

-------------------------------------------
PRIORITY GAPS (by failure frequency)
-------------------------------------------

1. FM-1.3 Step repetition (15.7%) -- UNDEFENDED
   Fix: [one-line description]
2. FM-2.6 Reasoning-action mismatch (13.2%) -- PARTIAL
   Fix: [one-line description]
3. ...

-------------------------------------------
RECOMMENDED FIXES
-------------------------------------------

[copy-paste snippets from Step 5]

-------------------------------------------
BOTTOM LINE
-------------------------------------------

Your config defends against [N]% of observed multi-agent failures.
The single highest-impact fix would be: [top undefended mode].
Adding the top 3 fixes would raise coverage to [N]%.

Run agent-workspace-interview to generate a complete MAST-hardened config from scratch.
===========================================
```

### Step 7: Optionally Apply Fixes

Ask: "Want me to apply these fixes to your config files now?"

If yes, use patch to insert the recommended defense snippets into the appropriate files.

## Special Cases

- **Single combined config file** (Anthropic CLI, Anysphere, etc.): Treat the entire file as both personality and rules sections. Look for MAST defenses anywhere in the file.
- **No config files found**: Ask the user to create them using agent-workspace-interview first.
- **Very large config files** (1000+ words): Flag that long configs are less reliable -- agents miss rules buried in walls of text. Suggest trimming.
- **No multi-agent context found**: Still check all 14 modes. Even single agents can exhibit FM-2.5 (ignoring user input), FM-2.6 (reasoning-action mismatch), etc.

## Quick Audit Mode

If the user just wants a fast check without the full report, scan for the top 5 modes only:

1. FM-1.3 Step repetition (15.7%)
2. FM-2.6 Reasoning-action mismatch (13.2%)
3. FM-1.5 Unaware of termination (12.4%)
4. FM-1.1 Disobey task spec (11.8%)
5. FM-3.3 Incorrect verification (9.1%)

These 5 modes cover 60.1% of all failures. A quick check of just these is often sufficient.

## Pitfalls

- Do NOT count vague instructions like "be careful" or "do good work" as DEFENDED -- they don't specifically address the failure mode
- Do NOT double-count a single instruction for multiple modes -- each mode needs its own targeted defense
- An instruction buried in paragraph 47 of a 2000-word file is practically UNDEFENDED -- be realistic about what agents actually follow
- Do NOT confuse "has a verifier agent" with "has FM-3.3 defense" -- the paper shows verifiers often do superficial checks only
- PARTIAL is better than UNDEFENDED but don't overscore it -- a vague instruction is not a real defense