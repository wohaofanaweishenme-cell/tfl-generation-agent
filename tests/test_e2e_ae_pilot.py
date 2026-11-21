"""End-to-end AE classroom pilot: one SAP in, one structural DOCX out.

These tests deliberately use invented synthetic SAP words, not the held-out
clinical shell. The actual official 431-template Library remains read-only.
"""
import json
from pathlib import Path

from docx import Document

from tfl_agent.agent.ae_spec_extractor import extract_ae_spec_from_sap
from tfl_agent.agent.end_to_end_ae_pilot import run_single_sap_ae_pilot


PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = PROJECT / "library"


def _synthetic_sap():
    return {
        "filename": "synthetic_AE.pdf", "pages": 21,
        "blocks": [
            {
                "block_id": "sap:p4:b0", "page": 4, "section": None,
                "text": "Statistical analysis plan for RP6530-2101. "
                        "This fixture is synthetic, not real clinical evidence.",
            },
            {
                "block_id": "sap:p5:b0", "page": 5, "section": "4.3",
                "text": "Subjects are assigned in a 1:1 ratio to "
                        "Group 1: Test Drug 100 mg BID and "
                        "Group 2: Test Drug 200 mg BID in 1:1 ratio.",
            },
            {
                "block_id": "sap:p18:b0", "page": 18, "section": "8.3",
                "text": "8.3.1 Safety Population All treated patients are "
                        "included in the descriptive safety set.",
            },
            {
                "block_id": "sap:p19:b0", "page": 19, "section": "8.8",
                "text": "8.8.2 Adverse Events Safety Analysis Set. "
                        "Patient counts and percentages and event counts "
                        "will be presented for each treatment and overall. "
                        "A patient will only be counted once per preferred "
                        "term within a treatment according to the maximum "
                        "grade attained. "
                        "Treatment Emergent Adverse Events (TEAEs) are events "
                        "with start date after the first dose.",
            },
            {
                "block_id": "sap:p19:b1", "page": 19, "section": "8.8",
                "text": "Any non-TEAE • Any TEAE • Any Serious TEAE • "
                        "Fatal TEAEs • Grade >=3 TEAEs • "
                        "AE leading to discontinuation",
            },
            {
                # Held-out shell pages must never be available to extraction.
                "block_id": "sap:p45:b0", "page": 45, "section": None,
                "text": "A held-out target Table Shell with made-up counts.",
            },
        ],
    }


def test_extract_ae_spec_stays_inside_sap_body():
    spec, extraction = extract_ae_spec_from_sap(_synthetic_sap())
    assert spec["identity"]["tfl_id"] == "14.3.1.1"
    assert extraction["body_page_range"] == [4, 21]
    assert len(spec["table_requirements"]["row_requirements"]) == 6
    assert len(spec["statistical_requirements"]["treatment_groups"]) == 2
    assert all(e["page_numbers"][0] <= 21 for e in spec["provenance"]["evidence"])
    assert all("held-out" not in e["exact_text"] for e in spec["provenance"]["evidence"])
    assert spec["readiness"] == "needs_review"


def test_full_pipeline_one_sap_no_intermediate_uploads(tmp_path):
    assert (LIBRARY / "Library_Registry.json").is_file(), (
        "The official Library is required for this integration test"
    )
    result = run_single_sap_ae_pilot(
        "synthetic_AE.pdf", LIBRARY, tmp_path,
        parsed_override=_synthetic_sap(),
    )
    assert result["status"] == "structural_draft_generated"
    assert result["approved_library_count"] == 431
    assert result["manual_adaptation_review_required_to_generate"] is False
    assert result["validation"]["valid_structural_shell"] is True
    assert result["generation"]["row_count"] == 6
    assert result["generation"]["column_count"] == 4
    assert result["generation"]["source_word_text_transplanted"] is False
    word_files = list(tmp_path.glob("*.docx"))
    assert len(word_files) == 1
    doc = Document(word_files[0])
    assert len(doc.tables) == 1
    assert len(doc.tables[0].columns) == 4
    assert len(doc.tables[0].rows) == 8
    all_cells = " ".join(c.text for r in doc.tables[0].rows for c in r.cells)
    assert "Test Drug 100 mg BID" in all_cells
    assert "Test Drug 200 mg BID" in all_cells
    assert "Overall" in all_cells
    assert "VCN-01" not in all_cells
    assert "Gemcitabine" not in all_cells
    for name in (
        "TFL_Specification.json", "TFL_Inventory.json",
        "Template_Retrieval.json", "Automatic_Structural_Adaptation_Plan.json",
        "SAP_Extraction_Evidence.json", "Generation_Rationale.json",
        "Validation_Report.json",
    ):
        assert (tmp_path / name).is_file(), name
    report = json.loads((tmp_path / "Validation_Report.json").read_text())
    assert report["clinical_validity_verified"] is False
    assert report["comparative_shell_ground_truth_checked"] is False


def test_notebook_is_thin_git_package_client():
    notebook_path = PROJECT / "notebooks" / "09_One_SAP_to_AE_Shell_End_to_End.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(c.get("source") or [])
        for c in notebook["cells"] if c["cell_type"] == "code"
    )
    assert code.count("files.upload()") == 1
    assert "from tfl_agent.agent.end_to_end_ae_pilot import run_single_sap_ae_pilot" in code
    assert "def extract_ae_spec_from_sap" not in code
    assert "def generate_ae_structural_docx" not in code
    assert "def run_single_sap_ae_pilot" not in code
    assert len(code) < 4200
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "Colab 09", "exec")



def test_ae_list_can_span_many_pdf_blocks_and_pages():
    """Regression: earlier Step 2 expected both row anchors within 12 blocks."""
    sap = _synthetic_sap()
    original = sap["blocks"]
    # The TOC can mention 8.8.2 before the actual AE section.
    toc = {
        "block_id": "sap:p2:b4", "page": 2, "section": None,
        "text": "8.8.2 Adverse Events ................................ 19",
    }
    header = next(b for b in original if b["block_id"] == "sap:p19:b0")
    first = {
        "block_id": "sap:p19:b30", "page": 19, "section": "8.8",
        "text": "Any non-TEAE",
    }
    second = {
        "block_id": "sap:p20:b2", "page": 20, "section": "8.8",
        "text": "Any TEAE • Any Serious TEAE • Fatal TEAEs • "
                "Grade >=3 TEAEs • AE leading to discontinuation. "
                "Summaries showing number of events by SOC and PT",
    }
    filler = [{
        "block_id": f"sap:p19:b{i+4}", "page": 19, "section": "8.8",
        "text": f"Non-category section formatting block {i}",
    } for i in range(16)]
    sap["blocks"] = [
        toc,
        *[b for b in original if b["page"] < 19],
        header,
        *filler,
        first,
        {"block_id": "sap:p19:b99", "page": 19,
         "text": "CONFIDENTIAL Page 19 of 106", "section": "8.8"},
        {"block_id": "sap:p20:b0", "page": 20,
         "text": "STATISTICAL ANALYSIS PLAN", "section": "8.8"},
        {"block_id": "sap:p20:b1", "page": 20,
         "text": "Sponsor Name: Test Protocol", "section": "8.8"},
        second,
        {"block_id": "sap:p20:b5", "page": 20, "section": "8.8",
         "text": "8.8.3 Clinical Laboratory Evaluations"},
        *[b for b in original if b["page"] > 20],
    ]
    spec, analysis = extract_ae_spec_from_sap(sap)
    assert spec["table_requirements"]["row_requirements"] == [
        "Any non-TEAE",
        "Any TEAE",
        "Any Serious TEAE",
        "Fatal TEAEs",
        "Grade >=3 TEAEs",
        "AE leading to discontinuation.",
    ]
    links = next(x["ref_ids"] for x in spec["provenance"]["field_links"]
                 if x["json_pointer"] == "/table_requirements/row_requirements")
    assert links == ["sap:p19:b30", "sap:p20:b2"]
    assert all(ref in analysis["evidence_ref_ids"] for ref in links)
    assert analysis["body_page_range"] == [4, 21]


def test_ae_parser_never_borrows_held_out_template_categories():
    import pytest
    sap = _synthetic_sap()
    sap["blocks"] = [
        block for block in sap["blocks"]
        if block["block_id"] != "sap:p19:b1"
    ]
    sap["blocks"].append({
        "block_id": "sap:p44:b1", "page": 44, "section": None,
        "text": "Any non-TEAE • Any TEAE • Any Serious TEAE • "
                "Fatal TEAEs • Grade >=3 TEAEs • AE leading to discontinuation",
    })
    with pytest.raises(ValueError, match="Overall Summary list could not"):
        extract_ae_spec_from_sap(sap)


def test_ae_heading_and_rows_may_be_separate_blocks():
    sap = _synthetic_sap()
    header = next(b for b in sap["blocks"] if b["block_id"] == "sap:p19:b0")
    # Real PDFs may render a short 8.8.2 heading separately from the prose.
    header["text"] = "8.8.2 Adverse Events " + header["text"].split("8.8.2 Adverse Events", 1)[1]
    spec, analysis = extract_ae_spec_from_sap(sap)
    assert len(spec["table_requirements"]["row_requirements"]) == 6
    assert analysis["body_page_range"] == [4, 21]
