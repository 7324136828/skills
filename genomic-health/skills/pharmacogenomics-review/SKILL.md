---
name: pharmacogenomics-review
description: Flag potential drug–gene interactions based on pharmacogenomic markers reported by a lab panel, a consumer DNA service, or a list of CYP/transporter/receptor genotypes. Use whenever someone shares PGx panel results and wants to understand how their genetics might affect drug metabolism, efficacy, or adverse-event risk — especially before starting a new medication or investigating an unexpected drug response.
---

# Pharmacogenomics review

Translates reported pharmacogenomic (PGx) genotypes into plain-language explanations
of metabolizer status, flags clinically actionable drug–gene pairs, and prepares
the user for a conversation with a pharmacist or prescriber.

## Step 1 — identify the input

Accepted inputs:
- A lab PGx panel report (paste text or describe the PDF)
- A consumer DNA result listing CYP genotypes (23andMe, GeneSight, etc.)
- A manually entered list of genotypes (e.g., `CYP2C19 *1/*2`)
- A list of current medications the user wants screened

Confirm what is available before proceeding. If the user has only a medication list and no genotype data, explain what a PGx panel covers and recommend they ask their provider about ordering one.

## Step 2 — parse the genotypes

For each reported gene, extract:

| Gene | Diplotype (star alleles) | Phenotype | Source |
|---|---|---|---|
| CYP2C19 | *1/*2 | Intermediate metabolizer | Lab panel |
| CYP2D6 | *4/*4 | Poor metabolizer | Lab panel |
| DPYD | *1/*1 | Normal function | Lab panel |

Common genes covered by PGx panels: CYP2C19, CYP2D6, CYP3A5, CYP2C9, CYP1A2, DPYD, TPMT, UGT1A1, SLCO1B1, VKORC1, F5 (Factor V Leiden), MTHFR.

## Step 3 — explain metabolizer status

For each gene, explain in plain language:
1. What the gene does (which drugs it metabolizes or transports)
2. What the user's phenotype means (poor / intermediate / normal / rapid / ultrarapid metabolizer)
3. The general clinical implication (e.g., "drugs broken down by CYP2C19 may accumulate at normal doses" for a poor metabolizer)

## Step 4 — screen for drug–gene interactions

If the user provides a current medication list, cross-reference against the reported genotypes:

| Medication | Gene | Interaction type | Guidance |
|---|---|---|---|
| Clopidogrel | CYP2C19 | Reduced activation → reduced efficacy | CPIC recommends alternative antiplatelet for poor/intermediate metabolizers |
| Codeine | CYP2D6 | Ultrarapid: excess morphine conversion (toxicity risk) | CPIC: avoid in ultrarapid metabolizers |
| Fluorouracil | DPYD | Poor function: severe toxicity risk | CPIC: dose reduction or alternative |

Use CPIC (Clinical Pharmacogenomics Implementation Consortium) guidelines as the primary reference. Note the CPIC level (A, B, C) for each interaction.

## Step 5 — produce the provider summary

Write a structured summary:
1. Genotype and phenotype table (from Step 2)
2. Plain-language explanations (from Step 3)
3. Drug–gene interaction table (from Step 4), if applicable
4. Three to five questions to bring to a pharmacist or prescribing physician

## Rules

- **Never recommend starting, stopping, or changing a medication.** Present the interaction data; the prescribing decision belongs to a licensed clinician.
- Always cite the evidence tier (CPIC level) for each flagged interaction. Do not treat Level C or unannotated interactions with the same weight as Level A.
- Treat all genetic and medication data as private health information. Do not reference it outside this task.
- If the analysis reveals a high-severity interaction for a medication the user is currently taking (e.g., DPYD deficiency + active fluorouracil), advise the user to contact their prescriber or pharmacist promptly — do not minimize it.
