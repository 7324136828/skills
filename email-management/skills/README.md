# Skills

Each folder is a self-contained skill: a `SKILL.md` with YAML frontmatter
(`name`, `description`) and instructions for driving the scripts in the parent
directory.

| Skill | Use it for |
|---|---|
| `inbox-audit` | Which services is this mailbox registered with, and how do I unsubscribe? |
| `email-digest` | Download recent mail, summarize it locally, narrate it to MP3. |
| `html-split` | Break one oversized HTML document into per-section text files. |

## Installing

Copy (or symlink) the folders to wherever your assistant looks for skills:

- **Claude Code, one project:** `<project>/.claude/skills/`
- **Claude Code, everywhere:** `~/.claude/skills/`

```bash
cp -r inbox-audit email-digest html-split ~/.claude/skills/
```

```powershell
Copy-Item -Recurse inbox-audit,email-digest,html-split "$env:USERPROFILE\.claude\skills\"
```

The skills reference the scripts by relative name (`eml_extract.py`,
`run_audit.sh`, ...). If you install the skills away from the toolkit, tell the
assistant where the toolkit lives — or record the absolute path in the
project's `CLAUDE.md`.

Nothing here is Claude-specific: any agent that can read a markdown file and run
a shell command can follow these.
