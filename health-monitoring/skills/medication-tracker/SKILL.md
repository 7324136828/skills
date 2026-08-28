---
name: medication-tracker
description: Help the user manage a medication list, track doses and scheduled times, calculate adherence rates, flag upcoming refill windows, and produce a medication summary card. Use whenever someone wants to set up a medication schedule, record that they took or missed a dose, check adherence, or prepare a medication list for a care appointment.
---

# Medication tracker

Maintains a medication schedule, tracks dose history, and surfaces adherence
stats and refill reminders — all from the conversation, without any external app.

## Step 1 — set up the medication list

When the user adds a medication, capture:

| Field | Description |
|---|---|
| Name | Generic or brand name |
| Dose | Amount per dose (e.g., "10 mg") |
| Form | Tablet, capsule, liquid, patch, etc. |
| Frequency | How often (e.g., "once daily", "twice daily", "every 8 hours") |
| Time(s) | Scheduled time(s) of day |
| With food | Yes / No / Either |
| Start date | When the user began this medication |
| Refill date | When the current supply runs out (if known) |
| Prescriber | Optional — for the summary card |

Display the full list as a table whenever the user asks to "see my medications."

## Step 2 — record doses

When the user says they took a dose (or missed one), log:

| Date | Time | Medication | Taken? | Notes |
|---|---|---|---|---|

Accept natural language ("just took my metformin", "forgot my evening pill").

## Step 3 — calculate adherence

On request, compute per-medication adherence:

```
adherence % = (doses taken / doses scheduled) × 100
```

Report the rate, the count of missed doses, and the most common missed time slot if a pattern exists.

## Step 4 — flag refill windows

Warn the user when a refill date is within 7 days (or when supply math suggests it — e.g., pills remaining × dose interval ≤ 7 days).

## Step 5 — produce the medication summary card

On request, produce a clean plain-text card:

```
MEDICATION LIST — [Date]
Name          Dose    Frequency    Prescriber
──────────────────────────────────────────
...
```

This card is suitable for sharing at urgent care, ER, or any appointment where the user's regular provider is not present.

## Rules

- **Never recommend adding, stopping, or changing a medication.** Only track what the user tells you they have been prescribed.
- **Never recommend a dose adjustment** even if the user asks — direct them to their prescriber or pharmacist.
- Treat the medication list as private. Do not reference it outside this task.
- If the user reports a potential overdose or adverse reaction, immediately advise them to call Poison Control (1-800-222-1222 in the US) or emergency services — do not continue the tracker task until that is addressed.
