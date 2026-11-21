# Blueprint-driven TFL Table Reconstruction (Stage B.8 MVP)

## Goal

Reuse structure knowledge from a retrieved, approved Library DOCX without
copying study-specific clinical content. Reconstruct a **new editable Word
Table** from the target SAP's Specification. The authentic Library files remain
read-only. This is **reconstruction, not editing the source DOCX**.

## Workflow

1. Read the SAP PDF from Google Drive using Notebook 10 (no upload dialog).
2. Obtain the target Specification:
   - Default SAP-only mode: one Overall AE Table with two arms, using the
     existing targeted AE Step 2 extractor.
   - General Table mode: read a separately extracted target SAP-derived
     Specification JSON from Drive. Generic Step 2 is not yet implemented.
3. Retrieve approved source candidates from the official Library.
4. Build a diagnostic Adaptation Plan with Source IR / Target Layout IR,
   alignment, evidence checks, and unresolved requirements.
5. Build a reconstruction Blueprint using both IRs. Target spec owns all
   rows, columns, arm labels, statistics and footnotes; verified source may
   supply structural patterns and presentation conventions.
6. Build a new editable DOCX using this exact Blueprint, without copying
   source clinical labels or source clinical content.
7. Validate native Word structure against the Blueprint. This is NOT an
   independent ground-truth or clinical validation.

## Google Drive Notebook

[Notebook 10: Drive SAP to Blueprint Reconstruction](../notebooks/10_Drive_SAP_Blueprint_Reconstruction.ipynb)

Set DRIVE_SAP_RELATIVE_PATH to the SAP's existing path under MyDrive.
Default: Colab Notebooks/agent/midterm demo/SAP_001_00.pdf

For AE SAP-only mode, leave TARGET_SPEC_RELATIVE_PATH = None.
For non-AE tables set TARGET_SPEC_RELATIVE_PATH to a target Specification JSON
already in Drive, and optionally specify SAP_BODY_PAGES = (start, end).
If SAP_BODY_PAGES is absent, no whole-SAP quote search is attempted because
the PDF may contain held-out TFL shells.

Outputs are stored in
<SAP folder>/Blueprint_Reconstruction_Outputs/<SAP stem>_<timestamp>/
with a ZIP, one DOCX, Blueprint JSON, evidence and validation reports.

## Python APIs

SAP-only AE:

    from tfl_agent.agent.end_to_end_ae_pilot import run_single_sap_ae_pilot
    result = run_single_sap_ae_pilot(
        sap_path=".../new_SAP.pdf", library_path="library",
        output_dir=".../outputs")

General Table from target Specification:

    from tfl_agent.agent.table_blueprint_pipeline import run_table_blueprint_from_spec
    result = run_table_blueprint_from_spec(
        sap_path=".../new_SAP.pdf", spec_path=".../target_spec.json",
        library_path="library", output_dir=".../outputs",
        sap_body_page_range=None)

## Output files

- TFL_Specification.json: target-owned requirements
- Template_Retrieval.json: top retrieved template candidates
- Adaptation_Plan.json: diagnostic plan, if compatible
- Reconstruction_Blueprint.json: target row/column hierarchy used in generation
- Generation_Rationale.json: source structure reuse, status, warnings
- Validation_Report.json: native Word structure and footnotes
- Table_<id>_...DRAFT.docx: editable, UNAPPROVED Word shell

## Current limits

- SAP-only generic extraction is NOT done: automatic Step 2 remains Overall AE
  with two explicit treatment arms and recognizable SAP section.
- Table only, not Figure or Listing. A single native Word table is created.
- Source IR may influence the presentation of statistic subrows and page
  geometry, never source treatment names, categories, footnotes or denominators.
- Explicit target category labels may be expanded; inferred statistic subrows
  remain flagged for review.
- Unknown per-table denominators, precision, category values, visit structure
  and actual patient counts are not fabricated.
- Source mismatch or Plan failure triggers target-only reconstruction, and the
  report indicates whether verified Source IR was actually reused.
- A passing structural check does NOT mean the shell matches an independently
  held-out authentic TFL shell. Run separate row/column/format/footnote and
  ground-truth evaluation before claiming general generation quality.

Regression suite:

    python -m pytest -q tests/test_blueprint_reconstruction.py tests/test_e2e_ae_pilot.py
