# Real-study midterm compatibility test (DeepSeek + P-VCNA-003)

Open `notebooks/03_Real_Study_DeepSeek_Colab.ipynb` on Google Colab. It uses a live DeepSeek API, never a fixture fallback.

## Setup

1. **Revoke any API key pasted into a chat**, and issue a fresh DeepSeek API key. Never commit it, copy it into notebook source, or print it.
2. In Colab's **Secrets** (key icon), set `DEEPSEEK_API_KEY` and grant notebook access.
3. Run the installation and Library audit cells. The new loader supports both the original `library/metadata/Template_Metadata.json` and the team's `library/studies/P-VCNA-003/Study_Metadata.json` with actual DOCX paths under `TFL_Template_Library/`.
4. In Google Drive create **My Drive/TFL_Project/studies/** and upload the text-selectable target-study SAP **SAP_001_00.pdf** there once. The Notebook mounts Drive using `drive.mount('/content/drive')` and points `SAP_PATH` to `/content/drive/MyDrive/TFL_Project/studies/SAP_001_00.pdf`. Adjust `DRIVE_SAP_RELATIVE_PATH` if you use another folder or filename. The PDF is *not* committed to GitHub. Prefer a different study from P-VCNA-003 to avoid leakage.
5. For SAP_001_00.pdf the notebook starts with Table 14.1.3.1 (Demographic and Baseline Characteristics), with Table 14.2.3.1 (Summary of Progression Free Survival) commented out for an optional second test. Edit `TARGET_TABLES` with the target Table ID/title, not the source-library template ID; the demo supports 1–2 Tables.
6. For SAP_001_00.pdf the default `SAP_BODY_PAGE_RANGE=(4,21)` restricts retrieval to the statistical SAP body, excluding Content List on pages 23–26 and source shells from page 27. For other PDFs update this range using **physical PDF pages** (1-indexed); `None` does no filtering.
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

## Google Drive troubleshooting

- If `FileNotFoundError` occurs, run the Drive cell and check whether it prints the exact missing path and any PDF names detected in that folder. Put the PDF in the configured location or change `DRIVE_SAP_RELATIVE_PATH`.
- A fresh Colab runtime may require mounting Drive again, but the PDF remains in Drive and does **not** need to be uploaded again.
- `OUTPUT_DIR` still points to temporary Colab storage. The last cell exports a ZIP; save it privately if you need persistent audit results.
- Ensure authorization to store or transmit any confidential study content, especially when using an external model provider.


## Step 2 / Step 3 evidence and ranking update

See [STEP2_STEP3_RETRIEVAL_CHANGES.md](STEP2_STEP3_RETRIEVAL_CHANGES.md) for implementation and limitations.

- A verified SAP enumeration may substantiate multiple explicitly mentioned statistics, but unsupported claims are still discarded with review issues.
- Descriptive Demographics/Disposition/Safety tables do not require a named efficacy endpoint.
- The new ranking uses output family (45%), title terms (27%), statistics (13%), methods (10%) and analysis population (5%); scores are heuristics, not probabilities.
- PFS may rank a structurally similar OS template, but a known different endpoint **must be manually reviewed** and is **not auto-selected**.
- Use full target titles, including **Safety Analysis Set** or **ITT Analysis Set**, to avoid merging requirements for related populations.
- Reopen the GitHub Notebook before testing: an old Colab browser tab may retain earlier cell code. The target PDF stays on Google Drive.
