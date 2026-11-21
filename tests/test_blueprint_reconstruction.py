"""Regression tests for target-owned, Source IR-guided DOCX reconstruction."""
import json

import pytest
from docx import Document

from tfl_agent.agent.reconstruction_blueprint import build_reconstruction_blueprint
from tfl_agent.agent.blueprint_docx_generator import (
    generate_docx_from_blueprint, validate_reconstructed_shell,
)


def spec(*, title="Baseline Demographics", rows=None, stats=None):
    return {
        "identity": {"tfl_id": "14.1.2.1", "title": title, "output_type": "table"},
        "statistical_requirements": {
            "analysis_population": ["Safety Population"],
            "treatment_groups": ["Arm A", "Arm B"],
            "statistics_to_display": stats or ["n", "Mean", "SD"],
            "analysis_methods": ["Descriptive statistics"],
            "endpoint_name": "Baseline summaries",
        },
        "table_requirements": {
            "row_requirements": rows if rows is not None else ["Age", "Sex"],
            "column_requirements": ["Overall"],
            "footnote_requirements": ["This is a TARGET SAP note."],
            "denominator_rule": None,
        },
        "provenance": {"evidence": [], "field_links": []},
        "readiness": "needs_review",
    }


def source_plan():
    return {
        "source_template_id": "TEST_SOURCE",
        "source_integrity": {"verified": True, "sha256": "f" * 64},
        "retrieval": {"cross_endpoint": False},
        "adaptation_mode": "text_or_structural_edit_candidate",
        "source_ir": {
            "boundary_verified": True,
            "tables": [{"table_index": 0, "row_count": 5}],
            "layout_profile": {"axis_orientation": "treatment_arm_columns"},
            "hierarchical_rows": [
                {"label": "Mean", "row_type": "statistic_subrow"},
                {"label": "SD", "row_type": "statistic_subrow"},
                {"label": "Source-only ethnicity", "row_type": "category_subrow"},
            ],
            "column_candidates": [{
                "table_index": 0, "physical_grid_index": 1,
            }],
        },
    }


def test_demographics_reuses_structure_not_source_clinical_content(tmp_path):
    bp = build_reconstruction_blueprint(spec(), adaptation_plan=source_plan())
    assert bp["source_structure"]["verified_source_ir_used"]
    assert bp["source_structure"]["statistic_subrow_pattern"]
    assert [c["label"] for c in bp["columns"]] == ["Arm A", "Arm B", "Overall"]
    assert [r["label"] for r in bp["rows"]] == [
        "Age", "n", "Mean", "SD", "Sex",
    ]
    assert "Source-only ethnicity" not in json.dumps(bp)
    target = tmp_path / "demog.docx"
    outcome = generate_docx_from_blueprint(bp, target)
    check = validate_reconstructed_shell(target, bp)
    assert outcome["source_word_text_transplanted"] is False
    assert outcome["column_count"] == 4
    assert check["valid_structural_shell"]
    assert check["clinical_validity_verified"] is False
    doc = Document(target)
    assert doc.tables[0].rows[2].cells[0].text == "n"
    assert "This is a TARGET SAP note." in "\n".join(p.text for p in doc.paragraphs)


def test_target_only_fallback_does_not_invent_hierarchy(tmp_path):
    bp = build_reconstruction_blueprint(spec(), adaptation_plan=None)
    assert not bp["source_structure"]["verified_source_ir_used"]
    assert [r["label"] for r in bp["rows"]] == ["Age", "Sex"]
    dest = tmp_path / "plain.docx"
    generate_docx_from_blueprint(bp, dest)
    assert validate_reconstructed_shell(dest, bp)["valid_structural_shell"]


def test_ae_preserves_all_target_categories_and_event_placeholders(tmp_path):
    sample = spec(title="Overall Summary of Adverse Events",
                  rows=["Any TEAE", "Any Serious TEAE", "Fatal TEAE"],
                  stats=["Number of patients (n)", "Percentage (%)", "Number of events"])
    bp = build_reconstruction_blueprint(sample, adaptation_plan=source_plan())
    assert bp["header_rows"] == 2
    assert bp["row_label_header"] == "Adverse Event Category"
    assert len(bp["rows"]) == 3
    dest = tmp_path / "ae.docx"
    generated = generate_docx_from_blueprint(bp, dest)
    assert generated["word_row_count"] == 5
    assert generated["column_count"] == 4
    assert validate_reconstructed_shell(dest, bp)["valid_structural_shell"]
    assert "xx (xx.x%)" in Document(dest).tables[0].cell(2, 1).text


def test_missing_target_rows_fails_closed():
    with pytest.raises(ValueError, match="row requirements"):
        build_reconstruction_blueprint(spec(rows=[]))


def test_rejects_source_content_copy_flag(tmp_path):
    bp = build_reconstruction_blueprint(spec())
    bp["source_content_copied"] = True
    with pytest.raises(ValueError, match="Source-study"):
        generate_docx_from_blueprint(bp, tmp_path / "not_allowed.docx")


def test_drive_notebook_has_valid_python_and_no_upload():
    from pathlib import Path
    notebook = json.loads((
        Path(__file__).resolve().parents[1]
        / "notebooks" / "10_Drive_SAP_Blueprint_Reconstruction.ipynb"
    ).read_text(encoding="utf-8"))
    code = "\n".join("".join(cell.get("source") or [])
                     for cell in notebook["cells"]
                     if cell["cell_type"] == "code")
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "Drive Blueprint notebook", "exec")
    assert 'drive.mount("/content/drive")' in code
    assert "DRIVE_SAP_RELATIVE_PATH" in code
    assert "run_single_sap_ae_pilot" in code
    assert "run_table_blueprint_from_spec" in code
    assert "files.upload(" not in code
    assert 'sys.path.insert(0, str(SOURCE_DIR))' in code
    assert 'PACKAGE_DIR / "__init__.py"' in code
    assert "import tfl_agent" in code


def test_incompatible_source_axis_forces_target_only_structure():
    incompatible = source_plan()
    incompatible["adaptation_mode"] = "rebuild_with_source_style"
    bp = build_reconstruction_blueprint(spec(), adaptation_plan=incompatible)
    assert not bp["source_structure"]["verified_source_ir_used"]
    assert [r["label"] for r in bp["rows"]] == ["Age", "Sex"]
