# Real-study midterm compatibility test (DeepSeek + P-VCNA-003)

Open `notebooks/03_Real_Study_DeepSeek_Colab.ipynb` on Google Colab. It uses a live DeepSeek API, never a fixture fallback.

## Setup

1. **Revoke any API key pasted into a chat**, and issue a fresh DeepSeek API key. Never commit it, copy it into notebook source, or print it.
2. In Colab's **Secrets** (key icon), set `DEEPSEEK_API_KEY` and grant notebook access.
3. Run the installation and Library audit cells. The new loader supports both the original `library/metadata/Template_Metadata.json` and the team's `library/studies/P-VCNA-003/Study_Metadata.json` with actual DOCX paths under `TFL_Template_Library/`.
4. In Google Drive create **My Drive/TFL_Project/studies/** and upload the text-selectable target-study SAP **SAP_001_00.pdf** there once. The Notebook mounts Drive using `drive.mount('/content/drive')` and points `SAP_PATH` to `/content/drive/MyDrive/TFL_Project/studies/SAP_001_00.pdf`. Adjust `DRIVE_SAP_RELATIVE_PATH` if you use another folder or filename. The PDF is *not* committed to GitHub. Prefer a different study from P-VCNA-003 to avoid leakage.
5. For SAP_001_00.pdf the notebook starts with Table 14.1.3.1 (Demographic and Baseline Characteristics), with Table 14.2.3.1 (Summary of Progression Free Survival) commented out for an optional second test. Edit `TARGET_TABLES` with the target Table ID/title, not the source-library template ID; the demo supports 1–2 Tables.
6. For SAP_001_00.pdf the default `SAP_BODY_PAGE_RANGE=(4,21)` restricts retrieval to the statistical SAP body, excluding Content List on pages 23–26 and source shells from page 27. For other PDFs update this range using **physical PDF pages** (1-indexed); `None` does no filtering.
7. Run the extraction and retrieval cells. These make paid API requests (two per Table, or three when completeness repair is required). Download the output audit archive, including specifications and generation rationale.

## What this version actually supports

- Reads all P-VCNA-003 study-scoped v2.4 metadata and 64 source DOCX template paths, using the keywords and aliases *inside* each template's Metadata. There is no global Keyword Index in that study folder.
- Does live DeepSeek JSON extraction (non-thinking JSON mode by default to limit truncation); verifies text quotations and schema, and **drops unsupported inferred values** rather than silently accepting them.
- Ranks Table templates and shows endpoint, methods, overlapping tokens, score, and a deterministic explanation. A high score is a retrieval heuristic, **not** calibrated model confidence.
- Supports verified v2.4 Word bookmark text changes through the Stage B.1 adapter. Unverified locators and unapproved source-to-target mappings are still blocked. **Any generated bookmark DOCX is a draft needing clinical and source-attribution review**, never an approved shell. The source library remains unchanged.
- If no relevant source template is retrieved, Step 3 shows candidates/no selection. If missing evidence blocks the specification, Step 4 does not produce a DOCX.
- Supports one selected Table per `TFLSession`; the notebook loops over at most two target Tables. **Does not auto-generate the entire study Content List.**

## Stage B.1 Bookmark draft generator and remaining work

The implemented adapter uses the source `intermediate/DOCX_Locator_Map/<template_id>.json`, verified bookmarks and the target SAP Specification to build auditable, narrowly scoped source-to-target **text** plans. The original Library is never overwritten. It cannot yet safely insert or delete rows/columns, repair merged cells, or remove original sponsor/source branding. For a Step-3 candidate with different analysis populations, use an explicit manual review record (see [Step 4 guide](STEP4_BOOKMARK_ADAPTATION.md)); a high retrieval score alone is not permission to adapt.

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

## Targeted completion and manual adaptation review (current code)

- After initial query planning and evidence extraction, Step 2 checks required fields by target Table category. When some remain unfilled it performs **one additional DeepSeek JSON request**, focusing on missing fields such as treatment groups or row requirements. It may still return `blocked` if the relevant source evidence is absent or unverifiable. There is no synthetic fallback for API errors.
- The extraction audit saved under `evidence/<tfl_id>_retrieval.json` now includes `completion.attempted`, `missing_before`, `raw_completion`, `verified_filled_fields`, and `missing_after`. Source quotations must match target SAP text; first-pass verified fields are not overwritten.
- Step 3 records both `best_candidate_template_id` and `selected_template_id`. For different known analysis populations (e.g. target Safety versus source ITT), selection status is `retrieved_needs_adaptation_review`, with `selected_template_id: null`. No automatic DOCX modification is permitted from that result. Cross-endpoint templates have the same safeguard.
- When reusing a currently open Colab runtime, restart the runtime and rerun from the first cell to avoid using cached Python modules from a previous GitHub commit.
- The default Google Drive source path is `MyDrive/Colab Notebooks/agent/midterm demo/SAP_001_00.pdf`; adjust `DRIVE_SAP_RELATIVE_PATH` if your location differs.
- **Step 4 verified Bookmark draft editing is now implemented for simple text anchors**, but an end-to-end clinically correct Table (especially cross-population Demographics) is not yet demonstrated. See [STEP4_BOOKMARK_ADAPTATION.md](STEP4_BOOKMARK_ADAPTATION.md).
