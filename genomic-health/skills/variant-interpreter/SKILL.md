---
name: variant-interpreter
description: Explain genetic variants and their health implications in plain language. Use whenever someone shares a list of variants (rsIDs, HGVS notation, or a VCF snippet), a lab-reported panel result, or a raw DNA download and wants to understand what specific variants mean, how confident the evidence is, and what questions to ask a clinician or genetic counselor.
---

# Variant interpreter

Translates genetic variant identifiers into plain-language explanations, evidence
summaries, and a structured list of questions for a genetic counselor or physician.

## Step 1 — identify the input format

Accepted inputs:
- A list of rsIDs (e.g., `rs429358`, `rs7412`)
- HGVS notation (e.g., `NM_000059.4:c.5266dupC`)
- A pasted VCF snippet (CHROM / POS / REF / ALT columns)
- A lab panel PDF or text report (paste or describe)
- A 23andMe / AncestryDNA raw data excerpt

Confirm the format before proceeding. If the user pastes raw VCF, extract only the variant identifiers — do not attempt to re-analyze the alignment data.

## Step 2 — look up each variant

For each variant, retrieve and report:

| Field | Description |
|---|---|
| Gene | Gene symbol (e.g., BRCA2) |
| Variant ID | rsID or HGVS notation |
| Clinical significance | ClinVar classification: Pathogenic / Likely pathogenic / VUS / Likely benign / Benign |
| Associated condition(s) | Disease or trait linked in ClinVar or OMIM |
| Inheritance | Autosomal dominant / recessive / X-linked / mitochondrial |
| Evidence strength | High (multiple studies, expert review) / Moderate / Low (single study or limited data) |
| Population frequency | gnomAD allele frequency if available |

If a variant is not in ClinVar or has conflicting interpretations, say so explicitly.

## Step 3 — explain in plain language

For each variant, write 2–4 sentences that:
1. Name the gene and what it normally does.
2. Describe what this variant changes.
3. State the clinical significance and what it means for the user's health, using hedged language where evidence is limited.
4. Note whether being a carrier (one copy) differs from being homozygous (two copies), when relevant.

## Step 4 — produce a provider summary

Write a structured summary:
1. Variant table (from Step 2)
2. Plain-language explanations (from Step 3)
3. A list of 3–5 questions to bring to a genetic counselor or specialist

## Rules

- **Never give a clinical diagnosis.** Describe what the evidence says; recommend the user discuss results with a certified genetic counselor (CGC) or physician.
- **Variants of Uncertain Significance (VUS) must be labeled as uncertain.** Do not imply health risk from a VUS.
- Evidence quality varies widely. Always state the evidence strength and note when data is limited or conflicting.
- Treat all genetic data as highly sensitive private health information. Do not reference it outside this task.
- If a result includes a high-penetrance pathogenic variant (e.g., BRCA1/2 pathogenic, Lynch syndrome gene), note that this finding warrants urgent referral to a genetic counselor — do not minimize it.
