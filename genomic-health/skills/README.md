# Skills

Each folder is a self-contained skill: a `SKILL.md` with YAML frontmatter
(`name`, `description`) and instructions for working with genetic data.

| Skill | Use it for |
|---|---|
| `variant-interpreter` | Explain genetic variants and their health implications in plain language. |
| `ancestry-health-report` | Summarize an ancestry DNA download for health-relevant insights. |
| `pharmacogenomics-review` | Flag drug–gene interactions based on reported pharmacogenomic markers. |

## Installing

Copy (or symlink) the folders to wherever your assistant looks for skills:

- **Claude Code, one project:** `<project>/.claude/skills/`
- **Claude Code, everywhere:** `~/.claude/skills/`

```bash
cp -r variant-interpreter ancestry-health-report pharmacogenomics-review ~/.claude/skills/
```

```powershell
Copy-Item -Recurse variant-interpreter,ancestry-health-report,pharmacogenomics-review "$env:USERPROFILE\.claude\skills\"
```

Nothing here is Claude-specific: any agent that can read a markdown file and run
a shell command can follow these skills.
