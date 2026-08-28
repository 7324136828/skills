---
name: vitals-tracker
description: Analyze exported vital-sign data (blood pressure, heart rate, weight, sleep, blood glucose, SpO2) to identify trends, flag out-of-range readings, and produce a structured provider-ready summary. Use whenever someone shares a wearable export, a CSV or PDF from a health app, or a pasted table of readings and wants a trend, a flag list, or a document to bring to a clinic appointment.
---

# Vitals tracker

Turns raw vital-sign data into a trend summary, a flag list, and a plain-language report
the user can bring to a care appointment.

No data is sent anywhere. All analysis runs on the data the user provides directly.

## Step 1 — identify the data source

Accepted inputs:
- CSV or JSON export from Apple Health, Google Fit, Fitbit, Garmin, Oura, or similar
- Manual table pasted into the conversation
- PDF lab printout (paste or upload)
- Screenshot of a health app (describe what you see)

Confirm the metric(s) involved before starting: blood pressure (systolic/diastolic), heart rate, weight, sleep duration/stages, blood glucose, SpO2, or a mix.

## Step 2 — load and parse

Parse the data into a table:

| Date | Metric | Value | Unit |
|---|---|---|---|

If the format is ambiguous (e.g., "120/80" with no header), ask the user to confirm.

## Step 3 — compute the trend

For each metric, calculate:
- 7-day and 30-day rolling average (or the full-period average if the window is smaller)
- Minimum and maximum with dates
- Direction: improving / stable / worsening (compare first-third to last-third of the series)

## Step 4 — flag out-of-range readings

Use standard adult reference ranges unless the user provides personal targets:

| Metric | Flag condition |
|---|---|
| Systolic BP | < 90 or > 140 mmHg (> 130 if pre-hypertension context) |
| Diastolic BP | < 60 or > 90 mmHg |
| Resting heart rate | < 40 or > 100 bpm |
| Weight | Flag only if user provides a target range |
| Fasting blood glucose | < 70 or > 125 mg/dL |
| SpO2 | < 94 % |
| Sleep | < 6 h or > 10 h total, or REM < 15 % if stage data is present |

List each flagged reading with date, value, and the exceeded threshold.

## Step 5 — produce the provider summary

Write a one-page plain-language summary:
1. Period covered and number of readings
2. Metric-by-metric trend in 1–2 sentences each
3. Flagged readings in a short table
4. Two or three questions the user might want to raise at the appointment

## Rules

- **Never diagnose a condition or recommend a treatment.** Describe what the data shows; recommend the user discuss interpretations with a clinician.
- **Never modify or delete the source data the user shared.**
- Flag readings are informational, not alarms — present them calmly and in context.
- If the dataset is very small (< 5 readings), note that trends are not reliable and describe individual readings instead.
