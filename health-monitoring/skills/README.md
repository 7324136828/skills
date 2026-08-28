# Skills

Each folder is a self-contained skill: a `SKILL.md` with YAML frontmatter
(`name`, `description`) and instructions for working with health data.

| Skill | Use it for |
|---|---|
| `vitals-tracker` | Analyze exported vital-sign data (blood pressure, heart rate, weight, sleep). |
| `symptom-journal` | Log and review symptoms over time; produce a structured provider summary. |
| `medication-tracker` | Manage medication schedules, doses, refill windows, and adherence streaks. |

## Installing

Copy (or symlink) the folders to wherever your assistant looks for skills:

- **Claude Code, one project:** `<project>/.claude/skills/`
- **Claude Code, everywhere:** `~/.claude/skills/`

```bash
cp -r vitals-tracker symptom-journal medication-tracker ~/.claude/skills/
```

```powershell
Copy-Item -Recurse vitals-tracker,symptom-journal,medication-tracker "$env:USERPROFILE\.claude\skills\"
```

Nothing here is Claude-specific: any agent that can read a markdown file and run
a shell command can follow these skills.
