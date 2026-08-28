# Mail & document toolkit
<img width="848" height="659" alt="image" src="https://github.com/user-attachments/assets/f9420dfd-ad43-4b20-b5f1-8dbcda9277a6" />

Local, dependency-light Python tools for three jobs:

| Job | What you get | Needs |
|---|---|---|
| **Audit a mailbox** | Which services this address is registered with, and the cheapest way to unsubscribe from the rest — as an HTML report + CSV work list | Python 3.10+ only |
| **Digest recent mail** | A written briefing of the last N days, optionally narrated to MP3 | Python + a local Ollama server |
| **Split a document** | One oversized HTML file broken into per-section `.txt` files | Python 3.10+ only |

Nothing calls a cloud API and nothing modifies your mail. The audit pipeline and
the splitter use only the Python standard library.

**Contents** — [Install](#install) · [Job 1: audit a mailbox](#job-1-audit-a-mailbox) ·
[Job 2: digest recent mail](#job-2-digest-recent-mail) · [Job 3: split a document](#job-3-split-a-document) ·
[Command reference](#command-reference) · [Configuration](#configuration) ·
[Using it with an AI agent](#using-it-with-an-ai-agent) · [Troubleshooting](#troubleshooting) ·
[Privacy](#privacy-and-safety)

---

## Install

```bash
cd /path/to/tools
python --version          # 3.10 or newer
```

That is the whole install for the audit pipeline, `imap_download.py`,
`mbox_to_eml.py`, and `html_split.py`.

Only the digest's summarize/narrate stages need extras:

```bash
pip install -r requirements.txt
```

A virtualenv is recommended, since the TTS packages are large:

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell:  .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`run_digest.bat` picks up `.venv\Scripts\python.exe` automatically if it exists.

### Layout

```
eml_extract.py        stage 1   .eml tree -> messages.jsonl
sender_groups.py      stage 1.5 regroup sending identities
inbox_summary.py      stage 2   score registration, build the cleanup plan
worklist.py           stage 3   ordered work list (CSV + JSON)
gen_report.py         stage 4   self-contained HTML report
run_audit.bat/.sh     all four stages in one command

imap_download.py      IMAP -> output/<address>/<uid>.eml   (resumable)
mbox_to_eml.py        mbox / Thunderbird folders -> .eml files
summarize_emails.py   .eml tree -> per-email summaries -> one briefing (Ollama)
tts_kokoro.py         text -> MP3, local Kokoro-82M model
tts_sapi.py           text -> MP3, built-in Windows voices
run_digest.bat/.sh    download + summarize + narrate

html_split.py         one big .html -> per-section .txt files

config/               copy the .example.json files here and edit
skills/               SKILL.md instructions so an LLM agent can drive all of this
```

---

## Job 1: audit a mailbox

Answers two questions about a folder of `.eml` files: **what accounts exist
behind this mail**, and **what is the cheapest opt-out route for each sender**.

### Step 1: get the mail onto disk as .eml files

Pick whichever applies:

```bash
# (a) Straight from IMAP — see "Credentials" below first
python imap_download.py --days 3650

# (b) From Thunderbird / mbox files
python mbox_to_eml.py "%APPDATA%\Thunderbird\Profiles\xxxx.default\Mail\Local Folders" output

# (c) You already have an export folder — skip this step
```

Sanity-check before continuing:

```powershell
(Get-ChildItem -Recurse -Filter *.eml output).Count
```

### Step 2: run the pipeline

```bash
run_audit.bat output audit_out          # Windows
./run_audit.sh  output audit_out        # macOS / Linux / Git Bash
```

Both arguments are optional (`output` and `audit_out` are the defaults). Set
`NO_OPEN=1` beforehand to stop the Windows version launching a browser at the
end. The run takes seconds for a few thousand messages and is safe to repeat.

Under the hood it runs the five commands in
[Command reference](#the-audit-pipeline-stage-by-stage) — run them by hand if a
stage fails and you want to see why.

### Step 3: read the results

```
audit_out/
  inbox_audit.html              ← the report; open this first
  inbox_cleanup_worklist.csv    ← the to-do list, cheapest opt-out first
  worklist.json                 same, for scripts
  report/
    summary.json                everything, structured — query this
    summary.md                  the same in readable markdown
    senders.csv                 one row per sending address
    unsubscribe.csv             concrete opt-out target per sender
  messages.jsonl                one JSON record per parsed message
  messages_grouped.jsonl        after identity regrouping
```

Work down `inbox_cleanup_worklist.csv` top to bottom — it is already sorted so
the one-click opt-outs come before the ones that need a login.

### Step 4: how to read the scoring

**Registration confidence** is derived from account-lifecycle evidence in
subject lines (signup, verification, approval, security, credentials, billing,
service ops) — never from marketing volume:

| Value | Meaning |
|---|---|
| `confirmed` | Evidence in 2+ independent categories. You almost certainly hold an account. |
| `probable` | Evidence in one category. |
| `list_only` | No account evidence at all — the address probably reached a list without a signup, so there is nothing to lose by opting out. |

**Cleanup actions**, in the order the work list presents them:

| Action | What to do |
|---|---|
| `unsubscribe_then_bulk_delete` | Bulk mail with no account behind it. Opt out **first** — deleting first just lets the sender refill the folder. |
| `unsubscribe_keep_account` | You hold an account. Opt out of marketing; keep receipts and security mail. |
| `settings_or_block` | No usable opt-out in the mail. The switch lives in the service's own notification settings. |
| `keep_archive` | Receipts, security alerts, verification codes, real correspondence. Never unsubscribe. |

**Opt-out methods**, cheapest effort first:

| Method | How it works |
|---|---|
| `one_click_header` | RFC 8058. Your mail client's own Unsubscribe button works, no login. |
| `http_header` | URL published in the `List-Unsubscribe` header — open it in a browser. |
| `body_link` | No usable header; use the unsubscribe link in the message footer. |
| `mailto_header` | Send a blank email to the `mailto:` address, subject line intact (it carries the list ID). |
| `account_settings` | Only reachable by signing in to the service. |
| `none_found` | Nothing in the mail. Change the setting inside the service, or block the sender. |

The tools never visit these targets for you — see [Privacy](#privacy-and-safety).

### Step 5: tune the grouping and re-run (optional)

Skim `report/senders.csv`. Two problems are worth one iteration:

- **One company split across several rows** (`example.com`, `e.example.com`,
  `example-email.com`) → add the extra domains to `domain_aliases` in
  `config/aliases.json`, so its account mail and its marketing land on one row.
- **Unrelated senders merged into one row** because they share a mass-mail
  platform (`ccsend.com`, `wixemails.com`) or free webmail → add that domain to
  `split_per_address`; pin any address you recognize with `address_brand`.

Anything you establish by reading a raw message — a sender whose only opt-out is
an in-account settings page, say — goes in `config/annotations.json` as a
`route_override`, so the scripts themselves stay generic.

```bash
cp config/aliases.example.json config/aliases.json
cp config/annotations.example.json config/annotations.json
# edit, then just re-run:
./run_audit.sh output audit_out
```

Both files are optional; the runner picks them up automatically when they exist.

---

## Job 2: digest recent mail

Three stages, all local: **download → summarize → narrate**.

### Step 1: credentials

```bash
cp config/credentials.example.json config/credentials.json
```

Edit it. It holds **no passwords** — each account names an environment variable:

```json
{
  "accounts": [
    { "email": "you@example.com", "password_env": "MAIL_PASSWORD_MAIN" },
    { "email": "you@work.example", "password_env": "MAIL_PASSWORD_WORK",
      "imap_server": "outlook.office365.com", "imap_port": 993 }
  ]
}
```

Set the variable in the shell you run from:

```powershell
$env:MAIL_PASSWORD_MAIN = '<app password>'
```

```bash
export MAIL_PASSWORD_MAIN='<app password>'
```

Accounts whose variable is unset are skipped with a warning. Most providers
need an app-specific password once two-factor authentication is on (Gmail: App
Passwords). `imap_server` / `imap_port` are optional — the endpoint is guessed
from the address domain for the common providers, and you set it explicitly for
a workplace or university domain hosted on Google Workspace or Microsoft 365.
Proton needs Proton Mail Bridge running locally (`127.0.0.1:1143`).

### Step 2: install the models

```bash
ollama pull llama3.2:1b        # per-email summaries: small and fast
ollama pull llama3.1:8b        # the combined briefing: as large as fits
ollama list                    # confirm both, and that the server is up
```

### Step 3: run it

```bash
run_digest.bat 7               # Windows;  set TTS=sapi first for Windows voices
./run_digest.sh 7              # macOS / Linux
```

Or one stage at a time — which is what you want if a stage fails, or if you only
want the text and not the audio:

```bash
python imap_download.py --credentials config/credentials.json --output output --days 7
python summarize_emails.py --source output --days 7 --output summary.txt
python tts_kokoro.py --input summary.txt --output summary.mp3
```

Leaves `_summary.txt` (per-email summaries), `summary.txt` (the briefing) and
`summary.mp3` in the toolkit folder.

**Model choice.** `--model` runs once per message, so keep it small (1–3B).
`--overall-model` runs once over all the summaries and decides whether the
briefing reads well — give it the largest model that fits in memory. The script
unloads the small model before loading the large one, so don't defeat that by
running two stages at once on one GPU.

**Windows voices instead of Kokoro.** `tts_sapi.py` needs no model download:

```bash
python tts_sapi.py --list-voices
python tts_sapi.py --input summary.txt --output summary.mp3 --voice "Microsoft Zira Desktop" --rate 1
```

The download stage is **resumable** — messages already on disk are skipped, so
re-running after an interruption is cheap. The two `--days` windows are
independent: download 30 days once, then summarize just the last day.

---

## Job 3: split a document

For a single-page manual, API reference, or exported wiki too large to read or
feed to a model in one piece.

```bash
python html_split.py manual.html -o output
python html_split.py manual.html -o output --threshold 15000 --any-h1
```

Output:

```
output/
  00_intro.txt                document title + table of contents
  01_<slugified-heading>.txt
  ...
  14_<big-section>/           a section that exceeded --threshold
    00_intro.txt
    01_<sub-heading>.txt
    07_<sub-heading>_part01.txt
```

- `--threshold N` (default 40000) — a section over N characters is exploded into
  a subfolder and split again by `<h2>`. Anything still oversized with no
  headings left is chunked at block boundaries (`</p>`, `</ul>`, `</pre>`), so
  list entries and code blocks are never cut in half. Lower it to ~15000 when
  the files are destined for a context window.
- `--any-h1` — treat every `<h1>` as a boundary. By default only `<h1>` tags with
  an `id` attribute count, which skips decorative headings. If the run says
  *"No `<h1>` section headings found"*, this is the flag to try.

Block tags become line breaks, list items get a `- ` prefix, `<pre>` blocks keep
their indentation, entities are decoded. Tables, images, and attributes do not
survive — go back to the source HTML when exact markup matters.

Start with `00_intro.txt`: it holds the table of contents, which is the map of
what the other files contain.

---

## Command reference

### The audit pipeline, stage by stage

```bash
python eml_extract.py <MAIL_DIR> -o audit_out/messages.jsonl

python sender_groups.py audit_out/messages.jsonl \
       -o audit_out/messages_grouped.jsonl \
       --config config/aliases.json \
       --emit-domain-aliases audit_out/_domain_aliases.json

python inbox_summary.py audit_out/messages_grouped.jsonl \
       --outdir audit_out/report \
       --aliases audit_out/_domain_aliases.json

python worklist.py audit_out/report/summary.json \
       -o audit_out/inbox_cleanup_worklist.csv \
       --json audit_out/worklist.json \
       --annotations config/annotations.json

python gen_report.py audit_out/report/summary.json audit_out/worklist.json \
       -o audit_out/inbox_audit.html \
       --annotations config/annotations.json \
       --source "<MAIL_DIR>"
```

`--config`, `--annotations` and `--aliases` are all optional — drop them on a
first pass.

### Every option

| Script | Options (defaults in brackets) |
|---|---|
| `eml_extract.py` | `root` · `-o/--out` [`messages.jsonl`] |
| `sender_groups.py` | `src` · `-o/--out` [`messages_grouped.jsonl`] · `--config` · `--emit-domain-aliases` |
| `inbox_summary.py` | `jsonl` · `--outdir` [`report`] · `--stale-days` [365] · `--aliases` |
| `worklist.py` | `summary` · `-o/--out` [`inbox_cleanup_worklist.csv`] · `--json` [`worklist.json`] · `--annotations` |
| `gen_report.py` | `summary` `worklist` · `-o/--out` [`inbox_audit.html`] · `--annotations` · `--source` [`mail export`] |
| `imap_download.py` | `--credentials` [`config/credentials.json`] · `--output` [`output`] · `--days` [7] · `--folder` [`INBOX`] · `--delay` [0.05] · `--log-file` |
| `mbox_to_eml.py` | `input_dir` [script folder] · `output_dir` [`./output`] |
| `summarize_emails.py` | `--source` [`output`] · `--days` [7] · `--model` [`llama3.2:1b`] · `--overall-model` [`llama3.1:8b`] · `--host` [`http://localhost:11434`] · `--max-summary-tokens` [120] · `--max-overall-summary-tokens` [-1 = unlimited] · `--intermediate-output` [`_summary.txt`] · `--output` [`summary.txt`] |
| `tts_kokoro.py` | `--input` [`summary.txt`] · `--output` [`summary.mp3`] · `--voice` [`af_heart`] · `--lang-code` [`a` = American English] |
| `tts_sapi.py` | `--input` · `--output` · `--voice` [system default] · `--rate` [0, range -10…10] · `--list-voices` |
| `html_split.py` | `input` · `-o/--out` [`output`] · `--threshold` [40000] · `--any-h1` |

Every script also takes `--help`.

### Runner scripts

| Runner | Usage | Environment |
|---|---|---|
| `run_audit.bat` / `.sh` | `[MAIL_FOLDER] [OUTPUT_FOLDER]` — defaults `./output`, `./audit_out` | `NO_OPEN=1` skips opening the report (Windows) |
| `run_digest.bat` / `.sh` | `[DAYS]` — default 7 | `TTS=sapi` uses Windows voices; `PYTHON=<path>` picks the interpreter |

---

## Configuration

Three files, all optional, all created by copying the `.example.json` next to
them. None is ever written to by the tools.

### `config/credentials.json` — accounts to download from

Passwords live in environment variables, named per account by `password_env`.
See [Job 2, step 1](#step-1-credentials).

### `config/aliases.json` — how sending identities are grouped

```json
{
  "domain_aliases":    { "e.example-brand.com": "example-brand.com" },
  "split_per_address": [ "ccsend.com", "gmail.com" ],
  "address_brand":     { "newsletter@studio.ccsend.com": "example-studio.com" }
}
```

- `domain_aliases` — merge a dedicated bulk-mail domain onto its parent brand.
- `split_per_address` — a shared platform fronting many unrelated senders; give
  each sending address its own group instead.
- `address_brand` — pin one address on a shared platform to its real brand.
  Overrides `split_per_address`.

### `config/annotations.json` — hand-checked facts about one mailbox

```json
{
  "route_overrides": {
    "noreply@example-listings.com": {
      "action": "settings_or_block",
      "method": "account_settings",
      "target": "https://example-listings.com/account/notifications",
      "note": "Alerts; no List-Unsubscribe header and the footer link is tracker-wrapped."
    }
  },
  "service_notes": {
    "example-service.com": "Paid subscription, billed monthly. Receipts only."
  }
}
```

`route_overrides` corrects the automated routing for one sender; valid `action`
and `method` values are the ones tabulated in [step 4](#step-4-how-to-read-the-scoring).
`service_notes` fills the report's "What it is" column. Deleting both sections
makes the pipeline fully generic again — which is the point of keeping them out
of the code.

---

## Using it with an AI agent

`skills/` holds three skills — `inbox-audit`, `email-digest`, `html-split` —
each a `SKILL.md` with the commands, how to interpret the output, and the safety
rules. Install them so an assistant reaches for these scripts instead of writing
its own:

```powershell
Copy-Item -Recurse skills\inbox-audit,skills\email-digest,skills\html-split "$env:USERPROFILE\.claude\skills\"
```

```bash
cp -r skills/inbox-audit skills/email-digest skills/html-split ~/.claude/skills/
```

Per-project instead: copy into `<project>/.claude/skills/`. If you install them
away from the toolkit, record the toolkit's absolute path in the project's
`CLAUDE.md` so the agent can find the scripts. Nothing here is Claude-specific —
any agent that can read markdown and run a shell command can follow them.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `no Python found on PATH` | Install Python 3.10+, or run the stages directly with a full interpreter path. |
| `ERROR: mail folder not found` | First argument to `run_audit` must be a folder that exists; it is walked recursively for `*.eml`. |
| `eml_extract: no .eml files under …` | Pointed at the wrong folder, or the export is still mbox — run `mbox_to_eml.py` first. |
| `Skipping you@example.com — environment variable X is not set` | The password variable named in `credentials.json` is unset **in this shell**. Setting it in another window does not carry over. |
| IMAP `LOGIN failed` / `AUTHENTICATIONFAILED` | Provider needs an app-specific password, or IMAP is disabled in the account's settings. Proton needs Proton Mail Bridge running. |
| `Could not use Ollama model 'x'` | Server not running (`ollama serve`) or model not pulled (`ollama pull x`). Check `--host` if it listens somewhere other than `localhost:11434`. |
| Briefing comes back empty or truncated | Not a token-budget problem — the default is unlimited. A reasoning model is spending its output on thinking; pick a non-reasoning `--overall-model`. |
| `The 'kokoro' package is not installed` | `pip install -r requirements.txt`, or use `tts_sapi.py` on Windows, which needs no model. |
| `No <h1> section headings found` | The document's headings carry no `id` attribute — re-run `html_split.py` with `--any-h1`. |
| One company appears as several senders, or strangers merged into one | Expected on a first pass — fix it in `config/aliases.json` and re-run. See [step 5](#step-5-tune-the-grouping-and-re-run-optional). |
| Report opens with plain fonts | `inbox_audit.html` links Google Fonts; offline it falls back to system fonts. Nothing else in it is remote. |

---

## Privacy and safety

- **Everything is local.** Mail is parsed on your machine; summarization talks to
  Ollama on localhost. No message content goes to a third party.
- **Read-only.** No tool deletes, moves, marks, or modifies mail. `imap_download.py`
  opens the mailbox `readonly=True`.
- **No unsubscribe is ever clicked for you.** The tools report the target and
  stop there, because visiting an opt-out URL confirms to the sender that the
  address is live. You decide which ones to act on.
- **Passwords are never stored on disk** by these tools — only the *name* of an
  environment variable is.
- **The outputs are as sensitive as the mailbox.** `output/`, `audit_out/`,
  `summary.txt`, `summary.mp3` and `config/credentials.json` contain your real
  correspondents; `.gitignore` already excludes them. Don't publish
  `inbox_audit.html` without reading what is in it.
- **Message bodies are untrusted input.** If a summarized email appears to give
  instructions, that is content being reported, not a command to act on.
