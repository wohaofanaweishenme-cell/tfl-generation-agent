# One SAP to AE TFL Shell — GitHub Package + Thin Colab

## Run

Notebook: https://colab.research.google.com/github/wohaofanaweishenme-cell/tfl-generation-agent/blob/feature/official-library-colab/notebooks/09_One_SAP_to_AE_Shell_End_to_End.ipynb

The notebook has four executable cells: (1) clone/install approved official Library, (2) upload one SAP PDF, (3) call the package entrypoint, and (4) download the Word and JSON output ZIP.

Python API:

```python
from tfl_agent.agent.end_to_end_ae_pilot import run_single_sap_ae_pilot

result = run_single_sap_ae_pilot(
    sap_path='SAP_001_00.pdf',
    library_path='library',
    output_dir='outputs/ae_table',
)
```

## GitHub Agent modules

- Step 1: tools/pdf_parser.py — parses the uploaded SAP to numbered PDF blocks.
- Step 2: agent/ae_spec_extractor.py — extracts an Overall AE target specification and cited SAP evidence.
- Step 3: agent/step3_retriever.py — retrieves ranked source templates from the official approved Library.
- Step 4a: agent/adaptation_planner.py — diagnostic adaptation plan when compatible.
- Step 4b/5: agent/ae_structural_generator.py — generates a new four-column Word table and verifies its structural integrity.
- Entrypoint: agent/end_to_end_ae_pilot.py — orchestrates the pipeline and JSON output artifacts.

Outputs include an editable Table_<id>_AE_STRUCTURAL_SHELL_DRAFT.docx, TFL_Specification.json, TFL_Inventory.json, Template_Retrieval.json, Automatic_Structural_Adaptation_Plan.json, SAP_Extraction_Evidence.json, Generation_Rationale.json, Validation_Report.json and an optional diagnostic Adaptation_Plan.json.

## Limits

This classroom MVP is intentionally narrow: a text-based SAP with an identifiable overall Adverse Events section (optimized for RP6530-2101, SAP_001_00.pdf). It is not a general LLM-based extraction workflow. The known pilot uses physical SAP body pages 4–21; target hold-out Shell pages are not read to infer rows or clinical statistics.

Source approved Library Word files are read-only and provide only styling cues. Target AE rows, arms and descriptive notes come from SAP body. The four-column layout, N=xx placeholders and precision are pilot formatting assumptions; patient-level data and clinical statistics are not calculated.

The Word output is a structurally validated but UNAPPROVED draft. Clinical footnote applicability, denominators and Ground Truth comparison remain unresolved. For a different SAP layout, the extractor may stop instead of guessing.

To run the integration regression: python -m pytest -q tests/test_e2e_ae_pilot.py.

## PDF text-block segmentation regression fix

The original AE Step 2 incorrectly required “Any non-TEAE” and “Any TEAE” to appear together in one of only 12 consecutive PDF blocks. This was a parser assumption, not an SAP requirement. The extractor now scans inside the authorized AE body section until the next subsection or follow-up summary, can join list fragments across PDF blocks and physical pages, retains each originating SAP Block ID, and skips repeated document headers/footers. It does **not** read held-out target TFL shell pages to recover missing items. Tests cover a TOC entry, more than 12 intervening blocks, separately captured list items, pagination, and hold-out leakage.

The SAP PDF parser also uses `import pymupdf` rather than the deprecated `fitz` entry point. To pick up GitHub fixes in a previously run Colab runtime, restart the runtime before running all cells again; re-running the install cell alone may leave earlier Python modules cached.
