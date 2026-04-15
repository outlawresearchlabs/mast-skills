# MAST Skills

Hermes Agent skills for preventing all 14 failure modes identified in the MAST taxonomy (arXiv:2503.13657).

## Structure

```
skills/
  mast-taxonomy/           # Reference knowledge base
    SKILL.md
  agent-workspace-interview/ # Interview + config generator
    SKILL.md
    references/
      openclaw-examples.md
  mast-audit/              # Config auditor
    SKILL.md
```

## Usage with Hermes

1. Copy skill directories to `~/.hermes/skills/` (maintaining category subdirectories)
2. In conversation: the skills auto-load when relevant
3. Or explicitly: "run the agent workspace interview" / "run a MAST audit on my config"

## Maintenance

When the MAST paper is updated or new failure modes are identified:
1. Update `mast-taxonomy/SKILL.md` with new data
2. Add new defense patterns to `agent-workspace-interview/SKILL.md`
3. Add new detection criteria to `mast-audit/SKILL.md`