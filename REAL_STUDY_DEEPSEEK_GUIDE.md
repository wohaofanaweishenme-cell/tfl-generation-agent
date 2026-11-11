# Real-study midterm compatibility test (DeepSeek + P-VCNA-003)

Open `notebooks/03_Real_Study_DeepSeek_Colab.ipynb` on Google Colab. It uses a live DeepSeek API, never a fixture fallback.

## Setup

1. **Revoke any API key pasted into a chat**, and issue a fresh DeepSeek API key. Never commit it, copy it into notebook source, or print it.
2. In Colab's **Secrets** (key icon), set `DEEPSEEK_API_KEY` and grant notebook access.
3. Run the installation and Library audit cells. The new loader supports both the original `library/metadata/Template_Metadata.json` and the team's `library/studies/P-VCNA-003/Study_Metadata.json` with actual DOCX paths under `TFL_Template_Library/`.
4. Upload a *text-selectable* target-study SAP PDF. Prefer a **different study** from P-VCNA-003 to avoid leakage.
5. Edit `TARGET_TABLES` with the selected Table ID and title found in the *target SAP*, not the source library. Use 1–2 Tables for the midterm.
6. When the PDF contains both SAP body and source shells, set `SAP_BODY_PAGE_RANGE=(start,end)` using **physical PDF pages** to exclude Content List/shell text from evidence retrieval. `None` does no filtering, so interpret any evidence cautiously.
7. Run the extraction and retrieval cells. These make paid API requests (normally two per Table). Download the output audit archive, including specifications and generation rationale.

## What this version actually supports

- Reads all P-VCNA-003 study-scoped v2.4 metadata and 64 source DOCX template paths, using the keywords and aliases *inside* each template's Metadata. There is no global Keyword Index in that study folder.
- Does live DeepSeek JSON extraction (non-thinking JSON mode by default to limit truncation); verifies text quotations and schema, and **drops unsupported inferred values** rather than silently accepting them.
- Ranks Table templates and shows endpoint, methods, overlapping tokens, score, and a deterministic explanation. A high score is a retrieval heuristic, **not** calibrated model confidence.
- Detects when a real source DOCX uses bookmarks, not MVP `{{PLACEHOLDER}}` tokens. **The current safe generator blocks these unverified adaptations** rather than misrepresenting the result as a generated shell. `source_bookmarks_requires_adaptation` is an expected Stage-A compatibility outcome. The source library remains unchanged.
- If no relevant source template is retrieved, Step 3 shows candidates/no selection. If missing evidence blocks the specification, Step 4 does not produce a DOCX.
- Supports one selected Table per `TFLSession`; the notebook loops over at most two target Tables. **Does not auto-generate the entire study Content List.**

## Next: Stage B generator

Use the source `intermediate/DOCX_Locator_Map/<template_id>.json`, individual DOCX bookmarks and target SAP Specification to build **source-element to target-element adaptation plans**. Only validated edits to title, headers, rows/columns and footnotes may be applied; original sources must never be overwritten. Add independent source/target evidence checks and review reasons for unsupported modifications. No claim of complete Table adaptation until it is implemented and tested.

## Fallback

`notebooks/02_Midterm_Demo_GitHub_Colab.ipynb` is still an offline synthetic fixture test that **can generate one editable example Table**. Do not present its fixture result as evidence that the live DeepSeek run succeeded.
