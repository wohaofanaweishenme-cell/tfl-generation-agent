"""Offline Step-4 bookmark integration tests.  No trial data or network calls."""
import hashlib
import json
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from tfl_agent.tools.bookmark_adapter import plan_bookmark_adaptation
from tfl_agent.tools.docx_editor import generate_shell, plan_modifications


def _bookmark(paragraph, name, value, number):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:name"), name)
    start.set(qn("w:id"), str(number))
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(number))
    paragraph._p.append(start)
    paragraph.add_run(value)
    paragraph._p.append(end)


def _source(tmp_path, *, footnotes=True):
    folder = tmp_path / "library" / "TFL_Template_Library" / "table"
    folder.mkdir(parents=True)
    path = folder / "SOURCE_DEMO.docx"
    doc = Document()
    title = "Table 1.1 Demographic Characteristics (ITT Set)"
    _bookmark(doc.add_paragraph(), "O_O00001", title, 1)
    table = doc.add_table(rows=2, cols=2)
    _bookmark(table.cell(0, 0).paragraphs[0], "O_O00002", "Source Arm A", 2)
    _bookmark(table.cell(0, 1).paragraphs[0], "O_O00003", "Source Arm B", 3)
    _bookmark(table.cell(1, 0).paragraphs[0], "O_O00004", "Age", 4)
    _bookmark(table.cell(1, 1).paragraphs[0], "O_O00005", "xx", 5)
    if footnotes:
        _bookmark(doc.add_paragraph(), "O_O00006", "Percentages use column N", 6)
    doc.save(path)
    source_elements = []
    for i, (role, value) in enumerate([
        ("title", title), ("header_cell", "Source Arm A"),
        ("header_cell", "Source Arm B"), ("body_cell", "Age"),
        ("placeholder_cell", "xx"),
    ] + ([("footnote", "Percentages use column N")] if footnotes else []), 1):
        source_elements.append({
            "element_id": f"E{i:05d}", "element_type": role,
            "occurrences": [{
                "occurrence_id": f"O{i:05d}", "docx_locator": f"bookmark:O_O{i:05d}",
                "source_text": value, "verification_status": "verified",
            }],
        })
    locator = {
        "schema_version": "2.4", "template_id": path.stem,
        "docx_boundary": {
            "verification_status": "verified",
            "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "source_elements": source_elements,
    }
    loc = tmp_path / "library" / "intermediate" / "DOCX_Locator_Map" / "SOURCE_DEMO.json"
    loc.parent.mkdir(parents=True)
    loc.write_text(json.dumps(locator), encoding="utf-8")
    return path, loc


def _spec(columns=None, footnotes=None):
    return {
        "identity": {"output_type": "table", "tfl_id": "14.1.3.1",
                     "title": "Demographic Characteristics (Safety Set)"},
        "table_requirements": {
            "row_requirements": ["Age"],
            "column_requirements": columns if columns is not None else
                                   ["Source Arm A", "Source Arm B"],
            "footnote_requirements": footnotes if footnotes is not None else
                                     ["Percentages use column N"],
        },
    }


def _approval(*edits):
    return {
        "template_id": "SOURCE_DEMO", "tfl_id": "14.1.3.1",
        "reviewed_by": "Test statistician", "review_reason": "Approved synthetic header mapping",
        "edits": list(edits),
    }


def test_verified_bookmark_draft_is_new_docx_and_source_is_untouched(tmp_path):
    source, locator = _source(tmp_path)
    original = source.read_bytes()
    out = tmp_path / "output" / "Table_14.1.3.1.docx"
    plan = plan_modifications(source, _spec(), locator_map_path=locator)
    assert plan["safe_to_generate"]
    assert plan["editing_mode"] == "verified_bookmark_draft"
    path, applied = generate_shell(source, _spec(), out, locator_map_path=locator)
    assert Path(path) == out and out.exists()
    assert source.read_bytes() == original
    doc = Document(out)
    assert "Table 14.1.3.1 Demographic Characteristics (Safety Set)" in (
        "\n".join(p.text for p in doc.paragraphs))
    assert len(doc.tables) == 1
    assert doc.tables[0].cell(0, 0).text == "Source Arm A"
    assert applied["applied_bookmarks"] == ["O_O00001"]
    assert applied["output_sha256"] != applied["source_sha256"]


def test_unmapped_new_treatment_arms_block_without_review(tmp_path):
    source, locator = _source(tmp_path)
    spec = _spec(columns=["Target Arm A", "Target Arm B"])
    plan = plan_bookmark_adaptation(source, spec, locator)
    assert not plan["safe_to_generate"]
    assert any("Unmapped target columns" in x for x in plan["issues"])
    path, _ = generate_shell(source, spec, tmp_path / "output" / "result.docx",
                             locator_map_path=locator)
    assert path is None


def test_reviewed_header_replacement_is_bookmark_scoped(tmp_path):
    source, locator = _source(tmp_path)
    spec = _spec(columns=["Target Arm A", "Target Arm B"])
    approved = _approval(
        {"bookmark": "O_O00002", "expected_source_text": "Source Arm A",
         "new_text": "Target Arm A", "reason": "Target SAP arm A"},
        {"bookmark": "O_O00003", "expected_source_text": "Source Arm B",
         "new_text": "Target Arm B", "reason": "Target SAP arm B"},
    )
    out = tmp_path / "output" / "reviewed.docx"
    path, plan = generate_shell(source, spec, out, locator_map_path=locator,
                                reviewed_adaptation=approved)
    assert path and plan["safe_to_generate"]
    assert Document(path).tables[0].cell(0, 0).text == "Target Arm A"
    assert Document(path).tables[0].cell(0, 1).text == "Target Arm B"


def test_missing_target_footnotes_require_explicit_review(tmp_path):
    source, locator = _source(tmp_path)
    spec = _spec(footnotes=[])
    blocked = plan_bookmark_adaptation(source, spec, locator)
    assert not blocked["safe_to_generate"]
    assert "footnotes retained" in blocked["reason"]
    approved = _approval({
        "bookmark": "O_O00006",
        "expected_source_text": "Percentages use column N",
        "new_text": "", "reason": "This footnote does not apply to target study",
    })
    path, plan = generate_shell(source, spec, tmp_path / "output" / "review.docx",
                                locator_map_path=locator, reviewed_adaptation=approved)
    assert path and plan["safe_to_generate"]
    assert "Percentages use column N" not in "\n".join(
        p.text for p in Document(path).paragraphs)


def test_tampered_source_and_wrong_expected_text_fail_closed(tmp_path):
    source, locator = _source(tmp_path)
    approved = _approval({
        "bookmark": "O_O00002", "expected_source_text": "not source text",
        "new_text": "Source Arm A", "reason": "test mismatch",
    })
    plan = plan_bookmark_adaptation(source, _spec(), locator, approved)
    assert not plan["safe_to_generate"]
    assert "mismatch" in plan["reason"]
    doc = Document(source)
    doc.add_paragraph("Unreviewed modification")
    doc.save(source)
    after = plan_bookmark_adaptation(source, _spec(), locator)
    assert not after["safe_to_generate"]
    assert "SHA-256" in after["reason"]


def test_missing_locator_and_source_output_protection(tmp_path):
    source, locator = _source(tmp_path)
    assert not plan_bookmark_adaptation(source, _spec(), tmp_path / "missing.json")["safe_to_generate"]
    path, plan = generate_shell(source, _spec(), source.parent / "unsafe.docx",
                                locator_map_path=locator)
    assert path is None and not plan["safe_to_generate"]
    assert not (source.parent / "unsafe.docx").exists()
    other_library_location = locator.parents[2] / "should_not_write.docx"
    path, plan = generate_shell(source, _spec(), other_library_location,
                                locator_map_path=locator)
    assert path is None and not other_library_location.exists()
