"""Step 4 Adaptation Planner: offline tests with real and synthetic Table shells."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from tfl_agent.agent.source_structure_parser import parse_source_template
from tfl_agent.agent.target_layout_builder import build_target_layout
from tfl_agent.agent.adaptation_planner import build_adaptation_plan


def _bookmark(paragraph, name, text, idx):
    a = OxmlElement("w:bookmarkStart")
    a.set(qn("w:name"), name)
    a.set(qn("w:id"), str(idx))
    b = OxmlElement("w:bookmarkEnd")
    b.set(qn("w:id"), str(idx))
    paragraph._p.append(a)
    paragraph.add_run(text)
    paragraph._p.append(b)


def _fixtures(tmp_path):
    source = tmp_path / "library" / "TFL_Template_Library" / "table" / "DEMO_SOURCE.docx"
    source.parent.mkdir(parents=True)
    document = Document()
    _bookmark(document.add_paragraph(), "BOOK_TITLE", "Table source AE Safety", 1)
    table = document.add_table(rows=3, cols=3)
    table.cell(0, 0).text = "Categories"
    _bookmark(table.cell(0, 1).paragraphs[0], "BOOK_ARM1", "Arm A", 2)
    _bookmark(table.cell(0, 2).paragraphs[0], "BOOK_ARM2", "Arm B", 3)
    _bookmark(table.cell(1, 0).paragraphs[0], "BOOK_ANY", "Any TEAE", 4)
    _bookmark(table.cell(2, 0).paragraphs[0], "BOOK_SERIOUS", "Any Serious TEAE", 5)
    _bookmark(document.add_paragraph(), "BOOK_NOTE", "Old-study percentage denominator", 6)
    document.save(source)
    loc = tmp_path / "library" / "studies" / "DEMO" / "intermediate" / "DOCX_Locator_Map" / "DEMO_SOURCE.json"
    loc.parent.mkdir(parents=True)
    entries = [
        ("title", "BOOK_TITLE", "Table source AE Safety"),
        ("header_cell", "BOOK_ARM1", "Arm A"),
        ("header_cell", "BOOK_ARM2", "Arm B"),
        ("body_cell", "BOOK_ANY", "Any TEAE"),
        ("body_cell", "BOOK_SERIOUS", "Any Serious TEAE"),
        ("footnote", "BOOK_NOTE", "Old-study percentage denominator"),
    ]
    loc.write_text(json.dumps({
        "template_id": source.stem,
        "docx_boundary": {
            "verification_status": "verified",
            "document_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "source_elements": [{
            "element_type": role, "element_id": f"e{i}",
            "occurrences": [{
                "docx_locator": f"bookmark:{anchor}",
                "source_text": text, "verification_status": "verified",
                "source_ref_ids": [f"REF{i}"],
            }]
        } for i, (role, anchor, text) in enumerate(entries)],
    }), encoding="utf-8")
    return source, loc


def _spec():
    return {
        "identity": {
            "tfl_id": "14.3.1.1", "title": "Overall Summary of Adverse Events",
            "output_type": "table",
        },
        "readiness": "needs_review",
        "statistical_requirements": {
            "treatment_groups": ["Tenalisib 800 mg BID", "Tenalisib 1200 mg BID"],
            "statistics_to_display": [
                "Number of patients (n)", "Percentage of patients (%)", "Number of events",
            ],
            "analysis_population": ["Safety Population"],
            "analysis_methods": ["Patient counts and percentages and event counts"],
        },
        "table_requirements": {
            "row_requirements": ["Any TEAE", "Fatal TEAEs"],
            "column_requirements": ["Treatment group (Tenalisib 800 mg BID, Tenalisib 1200 mg BID)",
                                     "Overall"],
            "denominator_rule": None, "footnote_requirements": [],
        },
        "issues": [{
            "json_pointer": "/table_requirements/footnote_requirements",
            "description": "Target-specific footnotes were not extracted",
        }],
        "provenance": {
            "evidence": [{"ref_id": "SAP_AE", "exact_text": "AE counts and events"}],
            "field_links": [
                {"json_pointer": "/table_requirements/row_requirements",
                 "ref_ids": ["SAP_AE"]},
                {"json_pointer": "/statistical_requirements/statistics_to_display",
                 "ref_ids": ["SAP_AE"]},
            ],
        },
    }


def _candidate(source, loc):
    return {
        "template_id": source.stem, "source_path": str(source),
        "template": {"locator_map_path": str(loc)},
        "score": 0.9, "source_study_id": "DEMO",
        "cross_endpoint": False, "population_change_required": False,
    }


def test_source_ir_has_real_word_coordinates_and_verified_footnote(tmp_path):
    docx, locator = _fixtures(tmp_path)
    original = docx.read_bytes()
    ir = parse_source_template(docx, locator)
    assert ir["table_count"] == 1
    assert ir["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert ir["tables"][0]["row_count"] == 3
    assert ir["column_candidates"][0]["position"] == {
        "table_index": 0, "row_index": 0,
        "column_index": 1, "location_type": "table_cell",
    }
    assert ir["footnotes"][0]["text"] == "Old-study percentage denominator"
    assert docx.read_bytes() == original


def test_target_ir_never_invents_categories_or_footnotes():
    spec = _spec()
    ir = build_target_layout(spec)
    assert [x["label"] for x in ir["columns"]] == [
        "Tenalisib 800 mg BID", "Tenalisib 1200 mg BID", "Overall",
    ]
    assert ir["footnotes"] == []
    assert "footnote_requirements" in ir["unresolved_fields"]
    assert ir["cell_format_proposal"]["status"] == "inferred_requires_review"
    assert ir["evidence_by_field"]["rows"]["ref_ids"] == ["SAP_AE"]
    demo = copy.deepcopy(spec)
    demo["identity"]["title"] = "Demographics"
    demo["table_requirements"]["row_requirements"] = ["Age", "Race"]
    demo["statistical_requirements"]["statistics_to_display"] = [
        "n", "Mean", "SD", "Median", "Minimum", "Maximum", "Frequency", "Percentage",
    ]
    adapted = build_target_layout(demo)
    age, race = adapted["rows"]
    assert age["proposed_statistic_subrows"] == [
        "n", "Mean", "SD", "Median", "Min", "Max",
    ]
    assert age["subrow_status"] == "inferred_requires_review"
    assert race["proposed_statistic_subrows"] == []
    assert race["subrow_status"] == "categories_not_extracted"


def test_plan_proposes_real_operations_and_preserves_source(tmp_path):
    docx, locator = _fixtures(tmp_path)
    before = docx.read_bytes()
    plan = build_adaptation_plan(_spec(), _candidate(docx, locator))
    assert docx.read_bytes() == before
    assert plan["planning_status"] == "review_required"
    assert plan["execution_status"] == "not_executed"
    assert plan["executable_without_review"] is False
    actions = [x["action"] for x in plan["operations"]]
    assert "REPLACE_TITLE" in actions
    assert "REPLACE_HEADER_CANDIDATE" in actions
    assert "INSERT_COLUMN_CANDIDATE" in actions  # Overall
    assert "KEEP_ROW" in actions  # Any TEAE
    assert "INSERT_ROW_CANDIDATE" in actions  # Fatal TEAE, not in source
    assert "SEARCH_TARGET_FOOTNOTE_EVIDENCE" in actions
    assert "REVIEW_SOURCE_FOOTNOTE" in actions
    assert "SEARCH_TARGET_DENOMINATOR_EVIDENCE" in actions
    assert "REVIEW_CELL_FORMAT" in actions
    keep = next(x for x in plan["operations"] if x["action"] == "KEEP_ROW")
    assert keep["source"]["position"]["table_index"] == 0
    assert keep["target_evidence"]["ref_ids"] == ["SAP_AE"]
    assert all(x["execution_supported"] is False for x in plan["operations"])
    json.dumps(plan)


def test_fails_closed_on_wrong_sha_or_endpoint(tmp_path):
    docx, locator = _fixtures(tmp_path)
    c = _candidate(docx, locator)
    c["cross_endpoint"] = True
    with pytest.raises(ValueError, match="endpoint"):
        build_adaptation_plan(_spec(), c)
    c["cross_endpoint"] = False
    doc = Document(docx)
    doc.add_paragraph("tampering")
    doc.save(docx)
    with pytest.raises(ValueError, match="SHA-256"):
        build_adaptation_plan(_spec(), c)


@pytest.mark.parametrize("study_id,template_id", [
    ("P-VCNA-003", "PVCNA003_T_14_3_1_1"),
    ("SP11631", "SP11631_T_14_5_2_1_1"),
    ("OMO-103-01", "OMO10301_T_14_2_1_1"),
    ("CPX-POM-001", "CPXPOM001_T_14_1_3_1"),
    ("WTX-330x2101", "WTX330X2101_T_14_2_1_1"),
    ("ARV-471-BC-201", "ARV471BC201_T_14_1_2_1"),
])
def test_parse_real_official_source_ir_without_modifying_library(study_id, template_id):
    root = Path(__file__).resolve().parents[1] / "library"
    source = root / "TFL_Template_Library" / "table" / (template_id + ".docx")
    locator = root / "studies" / study_id / "intermediate" / "DOCX_Locator_Map" / (template_id + ".json")
    if not source.is_file() or not locator.is_file():
        pytest.skip("Official Library is not checked out")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    ir = parse_source_template(source, locator)
    assert ir["verified_occurrence_count"] > 0
    assert ir["source_sha256"] == before
    assert ir["row_candidates"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert json.loads(json.dumps(ir))["template_id"] == template_id
    # Real-study AE should reveal source statistical footnotes.
    if template_id == "PVCNA003_T_14_3_1_1":
        assert ir["footnotes"]
        plan = build_adaptation_plan(_spec(), _candidate(source, locator) | {
            "template_id": template_id, "source_study_id": study_id,
        })
        assert plan["summary"]["source_footnotes"] > 0
        assert "SEARCH_TARGET_FOOTNOTE_EVIDENCE" in plan["summary"]["by_action"]
