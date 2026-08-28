---
name: symptom-journal
description: Help the user log and review symptoms over time, identify patterns (timing, severity, triggers), and produce a structured summary they can share with a healthcare provider. Use whenever someone describes recurring or ongoing symptoms and wants to track them, spot patterns, or prepare for a medical appointment.
---

# Symptom journal

Turns free-text symptom descriptions into a structured log, a pattern summary,
and a provider-ready timeline the user can hand to a clinician.

## Step 1 — capture the entry

When the user describes a symptom, capture:

| Field | Description |
|---|---|
| Date / time | When it occurred or started |
| Symptom | Plain description (e.g., "headache", "fatigue", "nausea") |
| Severity | 1–10 or mild / moderate / severe |
| Duration | How long it lasted |
| Possible trigger | What the user was doing or had done recently |
| Relieved by | What helped, if anything |
| Notes | Anything else the user mentions |

If the user provides a batch of past entries, parse each one into this structure before analyzing.

## Step 2 — build and display the log

Maintain the log as a markdown table sorted by date. When the user asks to "see the log" or "show me my entries," print the full table.

## Step 3 — identify patterns

When asked to review or summarize, analyze the log for:
- **Frequency** — how often does each symptom appear?
- **Timing** — time of day, day of week, monthly cycle
- **Severity trend** — getting better, worse, or stable?
- **Co-occurrence** — symptoms that tend to appear together
- **Triggers** — repeated activities or foods preceding onset

Describe patterns in plain language. Note when the dataset is too small (< 5 entries per symptom) to draw reliable conclusions.

## Step 4 — produce the provider summary

Write a structured summary:
1. Symptom list with frequency and average severity
2. Notable patterns (timing, triggers, clusters)
3. Timeline of most significant episodes (table: date, symptom, severity)
4. Questions the user might want to raise with their provider

## Rules

- **Never suggest a diagnosis.** Describe what the log shows; leave interpretation to a clinician.
- **Never recommend stopping, starting, or changing any medication.**
- Treat all symptom data as private. Do not reference entries in any context outside this task.
- If a symptom description suggests an emergency (chest pain, difficulty breathing, sudden severe headache, signs of stroke), immediately advise the user to call emergency services or go to an emergency department — do not continue the journal task until that is addressed.
