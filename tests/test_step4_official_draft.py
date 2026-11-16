"""End-to-end Step 4 draft smoke tests; no clinical data or live LLM needed."""
import hashlib
import json
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from tfl_agent.agent.step5_validator import validate_shell
from tfl_agent.session import _choose_draft_source
from tfl_agent.tools.spec_draft import generate_spec_draft


def _bookmarked_source(tmp_path):
    source = tmp_path / "library" / "TFL_Template_Library" / "table" / "SOURCE.docx"
    source.parent.mkdir(parents=True)
    doc = Document()
    paragraph = doc.add_paragraph()
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), "5")
    start.set(qn("w:name"), "O_O00005")
    paragraph._p.append(start)
    paragraph.add_run("SYNTHETIC SOURCE STUDY HEADER")
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), "5")
    paragraph._p.append(end)
    doc.add_table(rows=2, cols=2).cell(0, 0).text = "Source-specific row"
    doc.add_paragraph("Source-only clinical footnote: old denominator")
    doc.save(source)
    locator = tmp_path / "library" / "studies" / "UNIT" / "intermediate" / "DOCX_Locator_Map" / "SOURCE.json"
    locator.parent.mkdir(parents=True)
    locator.write_text(json.dumps({
        "template_id": "SOURCE",
        "docx_boundary": {
            "verification_status": "verified",
            "document_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "source_elements": [{
            "element_type": "title", "occurrences": [{
                "verification_status": "verified",
                "docx_locator": "bookmark:O_O00005",
                "source_text": "SYNTHETIC SOURCE STUDY HEADER",
            }],
        }],
    }), encoding="utf-8")
    return source, locator


def _spec():
    return {
        "identity": {"tfl_id": "14.3.1.1", "title": "Overall Summary of Adverse Events - Safety Analysis Set",
                     "output_type": "table"},
        "statistical_requirements": {
            "analysis_population": ["Safety Population"],
            "treatment_groups": ["Tenalisib 800 mg BID", "Tenalisib 1200 mg BID"],
            "statistics_to_display": ["Number of patients (n)", "Percentage of patients (%)"],
        },
        "table_requirements": {
            "row_requirements": ["Any non-TEAE", "Any TEAE"],
            "column_requirements": ["Treatment group (Tenalisib 800 mg BID, Tenalisib 1200 mg BID)", "Overall"],
            "footnote_requirements": [],
        },
        "readiness": "needs_review",
        "issues": [{"description": "No specific denominator rule found"}],
    }


def test_draft_builds_editable_table_and_keeps_source_read_only(tmp_path):
    source, locator = _bookmarked_source(tmp_path)
    original = source.read_bytes()
    out = tmp_path / "out" / "Table_14.3.1.1_DRAFT.docx"
    path, plan = generate_spec_draft(source, _spec(), out, locator,
                                      source_study_id="UNIT", retrieval_status="auto_selected")
    assert path and Path(path).is_file(), plan
    assert source.read_bytes() == original
    assert plan["source_contents_copied"] is False
    assert plan["verified_locator_bookmark_overlap"] == 1
    doc = Document(path)
    assert len(doc.tables) == 1 and len(doc.tables[0].rows) == 3
    assert len(doc.tables[0].columns) == 4
    assert "Tenalisib 800 mg BID" == doc.tables[0].cell(0, 1).text
    assert "Tenalisib 1200 mg BID" == doc.tables[0].cell(0, 2).text
    assert doc.tables[0].cell(0, 3).text == "Overall"
    assert doc.tables[0].cell(1, 1).text == "xx"
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "DRAFT" in full_text
    assert "Source-only clinical footnote" not in full_text
    assert "Source-specific row" not in full_text
    qa = validate_shell(path, _spec(), plan)
    assert qa["valid"], qa


def test_empty_requirements_still_produce_flagged_incomplete_draft(tmp_path):
    source, locator = _bookmarked_source(tmp_path)
    spec = _spec()
    spec["table_requirements"]["row_requirements"] = []
    spec["table_requirements"]["column_requirements"] = []
    spec["statistical_requirements"]["statistics_to_display"] = []
    out = tmp_path / "out" / "incomplete.docx"
    path, plan = generate_spec_draft(source, spec, out, locator)
    assert path and plan["missing_rows"] and plan["missing_columns"] and plan["missing_footnotes"]
    assert "REVIEW REQUIRED" in Document(path).tables[0].cell(1, 0).text
    assert validate_shell(path, spec, plan)["valid"]


def test_verification_and_library_boundary_fail_closed(tmp_path):
    source, locator = _bookmarked_source(tmp_path)
    before = source.read_bytes()
    inside_lib = source.parent.parent / "should_not_write.docx"
    path, plan = generate_spec_draft(source, _spec(), inside_lib, locator)
    assert path is None and not inside_lib.exists()
    assert source.read_bytes() == before
    doc = Document(source)
    doc.add_paragraph("TAMPERED")
    doc.save(source)
    out = tmp_path / "out" / "tampered.docx"
    path, plan = generate_spec_draft(source, _spec(), out, locator)
    assert path is None and "SHA-256" in plan["reason"]
    assert not out.exists()


def test_draft_candidate_avoids_pfs_os_and_prefers_hematology():
    def candidate(tid, score, title, *, cross=False, endpoint=False):
        return {"template_id": tid, "score": score,
                "cross_endpoint": cross, "requires_endpoint_review": cross,
                "endpoint_match": endpoint,
                "template": {"identity": {"original_title": title}}}
    pairs = [
        candidate("OS", 0.7767, "Overall Survival", cross=True),
        candidate("PFS", 0.6733, "Summary of Progression Free Survival", endpoint=True),
    ]
    assert _choose_draft_source(pairs, "Summary of Progression Free Survival")["template_id"] == "PFS"
    labs = [
        candidate("BIO", 0.6543, "Summary of Biochemistry Parameters"),
        candidate("HEMA", 0.6543, "Summary of Hematology Results"),
    ]
    assert _choose_draft_source(labs, "Descriptive Summary of Hematology")["template_id"] == "HEMA"


def test_actual_official_bookmarked_ae_template_if_present(tmp_path):
    root = Path(__file__).resolve().parents[1] / "library"
    source = root / "TFL_Template_Library" / "table" / "PVCNA003_T_14_3_1_1.docx"
    locator = root / "studies" / "P-VCNA-003" / "intermediate" / "DOCX_Locator_Map" / "PVCNA003_T_14_3_1_1.json"
    if not source.is_file() or not locator.is_file():
        pytest.skip("Official source Library not present")
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    out = tmp_path / "Table_14.3.1.1_DRAFT.docx"
    path, plan = generate_spec_draft(source, _spec(), out, locator,
                                      source_study_id="P-VCNA-003")
    assert path and out.exists(), plan
    assert plan["source_sha256"] == original_sha
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
    assert plan["verified_locator_bookmark_overlap"] > 0
    assert validate_shell(path, _spec(), plan)["valid"]


@pytest.mark.parametrize("study_id, template_id", [
    ("ARV-471-BC-201", "ARV471BC201_T_14_1_2_1"),
    ("CPX-POM-001", "CPXPOM001_T_14_1_3_1"),
    ("WTX-330x2101", "WTX330X2101_T_14_2_1_1"),
    ("OMO-103-01", "OMO10301_T_14_2_1_1"),
    ("P-VCNA-003", "PVCNA003_T_14_3_1_1"),
    ("SP11631", "SP11631_T_14_5_2_1_1"),
])
def test_six_official_study_source_bookmarks_support_drafts(tmp_path, study_id, template_id):
    """Read-only integration of all six real Library studies; no DeepSeek."""
    root = Path(__file__).resolve().parents[1] / "library"
    source = root / "TFL_Template_Library" / "table" / f"{template_id}.docx"
    locator = root / "studies" / study_id / "intermediate" / "DOCX_Locator_Map" / f"{template_id}.json"
    if not source.is_file() or not locator.is_file():
        pytest.skip("Official Library source files not present")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    out = tmp_path / f"{template_id}_DRAFT.docx"
    path, plan = generate_spec_draft(
        source, _spec(), out, locator, source_study_id=study_id,
    )
    assert path and out.is_file(), plan
    assert plan["verified_locator_bookmark_overlap"] > 0
    assert plan["source_sha256"] == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert validate_shell(path, _spec(), plan)["valid"]
