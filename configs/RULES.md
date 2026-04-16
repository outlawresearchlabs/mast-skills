# RULES.md (FC1-only — forgetfulness defense)

1. **Anti-loop**: If repeating a failed approach, output `<LOOP-DETECTED>` and try differently.
2. **Clarify first**: If requirements are ambiguous, output `<CLARIFY>` and ask before implementing.
3. **Done = all criteria met**: Only declare done when every acceptance criterion is explicitly satisfied.

All other failure modes (FC2/FC3: reasoning, verification) are handled by structural enforcement via MCP tools — not by prompts.