"""Regression tests for semantic, hierarchical, physical-grid and evidence safeguards."""
from pathlib import Path

import pytest
from tfl_agent.agent.source_structure_parser import parse_source_template
from tfl_agent.agent.target_layout_builder import build_target_layout
from tfl_agent.agent.structure_alignment import align_target_rows, classify_layout_compatibility
from tfl_agent.agent.adaptation_planner import build_adaptation_plan

from test_step4_adaptation_planner import _fixtures, _spec, _candidate


ROOT = Path(__file__).resolve().parents[1] / "library"


def _real(study, tid):
    source = ROOT / "TFL_Template_Library" / "table" / (tid + ".docx")
    locator = ROOT / "studies" / study / "intermediate" / "DOCX_Locator_Map" / (tid + ".json")
    if not source.is_file() or not locator.is_file():
        pytest.skip("Official template not available in checkout")
    return source, locator


def test_evidence_absence_is_not_evidence(tmp_path):
    spec = _spec()
    ir = build_target_layout(spec)
    assert ir["evidence_by_field"]["title"]["evidence_status"] == "missing"
    assert ir["evidence_by_field"]["title"]["all_refs_present"] is False
    assert ir["evidence_by_field"]["rows"]["evidence_status"] == "linked_unverified"
    assert ir["evidence_by_field"]["rows"]["all_refs_present"] is True
    assert ir["evidence_by_field"]["rows"]["quote_previews"]
    spec["provenance"]["field_links"][0]["ref_ids"] = ["unknown-evidence"]
    bad = build_target_layout(spec)
    assert bad["evidence_by_field"]["rows"]["evidence_status"] == "invalid"
    assert bad["evidence_by_field"]["rows"]["all_refs_present"] is False


def test_synthetic_overall_insertion_uses_word_grid_index(tmp_path):
    docx, locator = _fixtures(tmp_path)
    plan = build_adaptation_plan(_spec(), _candidate(docx, locator))
    insertion = next(op for op in plan["operations"]
                     if op["action"] == "INSERT_COLUMN_CANDIDATE")
    assert insertion["source"]["after_column"]["position"]["column_index"] == 2
    assert insertion["source"]["insertion_physical_grid_index"] == 3
    assert insertion["source"]["target_column_index"] == 2
    assert plan["executor_ready"] is False
    assert plan["schema_version"] == "adaptation-plan-2.0"


def test_aes_real_word_grid_col_index_is_not_header_ordinal():
    docx, locator = _real("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    source = parse_source_template(docx, locator)
    assert [c["position"]["column_index"] for c in source["column_candidates"][:2]] == [2, 3]
    assert source["layout_profile"]["axis_orientation"] == "treatment_arm_columns"
    plan = build_adaptation_plan(_spec(), _candidate(docx, locator))
    insertion = next(op for op in plan["operations"]
                     if op["action"] == "INSERT_COLUMN_CANDIDATE")
    assert insertion["source"]["insertion_physical_grid_index"] == 4
    assert insertion["source"]["target_column_index"] == 2
    assert insertion["execution_supported"] is False
    assert plan["layout_compatibility"]["executor_ready"] is False
    assert plan["source_integrity"]["verified"] is True


def test_serious_teae_is_candidate_not_false_insert():
    source, locator = _real("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    ir = parse_source_template(source, locator)
    spec = _spec()
    spec["table_requirements"]["row_requirements"] = ["Serious TEAEs"]
    matches = align_target_rows(ir, build_target_layout(spec))["matches"]
    assert matches[0]["source"]["label"] == "Any Serious TEAE"
    assert matches[0]["relation"] == "lexical_normalized"


def test_source_title_chooses_table_number_not_study_id_pfs():
    source, locator = _real("OMO-103-01", "OMO10301_T_14_2_1_1")
    ir = parse_source_template(source, locator)
    assert ir["title_mapping"]["anchor"]["text"].lower().startswith("table 14.")
    assert ir["title_mapping"]["anchor"]["text"] != "OMO-103-01"
    target = _spec()
    target["identity"]["title"] = "Progression Free Survival"
    target["statistical_requirements"]["analysis_methods"] = ["Kaplan-Meier methodology"]
    target["statistical_requirements"]["statistics_to_display"] = [
        "Q1, median and Q3", "Brookmeyer-Crowley 95% confidence intervals",
    ]
    p = build_adaptation_plan(target, _candidate(source, locator))
    assert p["adaptation_mode"] == "rebuild_with_source_style"
    assert p["layout_compatibility"]["source_axis"] == "cohort_rows_statistic_columns"
    title_op = next(op for op in p["operations"] if op["action"] == "REPLACE_TITLE")
    assert title_op["source"]["text"].lower().startswith("table 14.")
    assert any(op["action"] == "REVIEW_COLUMN_AXIS_TRANSFORMATION"
               for op in p["operations"])


def test_demographics_has_actual_header_grid_and_statistical_hierarchy():
    source, locator = _real("CPX-POM-001", "CPXPOM001_T_14_1_3_1")
    ir = parse_source_template(source, locator)
    assert ir["table_count"] >= 2
    assert len(ir["column_candidates"]) >= 7
    assert ir["column_candidates"][0]["position"]["column_index"] == 1
    age = next(r for r in ir["hierarchical_rows"] if r["label"].startswith("Age"))
    mean = next(r for r in ir["hierarchical_rows"] if r["label"] == "Mean")
    assert mean["parent_row_id"] == age["row_id"]
    assert mean["row_type"] == "statistic_subrow"
    assert len(ir["footnote_groups"]) <= len(ir["footnotes"])


def test_bor_explicit_children_match_real_source():
    source, locator = _real("WTX-330x2101", "WTX330X2101_T_14_2_1_1")
    ir = parse_source_template(source, locator)
    spec = _spec()
    spec["identity"]["title"] = "Objective Response Rate"
    spec["table_requirements"]["row_requirements"] = [
        "Best overall response categories: CR, PR, SD, PD",
    ]
    layout = build_target_layout(spec)
    children = layout["rows"][0]["explicit_category_children"]
    assert len(children) == 4
    matches = align_target_rows(ir, layout)
    matched_children = [x for x in matches["matches"] if x["target"]["parent"]]
    assert len(matched_children) == 4
    assert all(x["relation"] == "lexical_normalized" for x in matched_children)
    assert all(x["source"]["position"]["location_type"] == "table_cell"
               for x in matched_children)


def test_blocked_hematology_preserves_uncertainty():
    source, locator = _real("SP11631", "SP11631_T_14_5_2_1_1")
    ir = parse_source_template(source, locator)
    spec = _spec()
    spec["table_requirements"]["row_requirements"] = []
    spec["statistical_requirements"]["statistics_to_display"] = []
    spec["table_requirements"]["column_requirements"] = []
    spec["statistical_requirements"]["treatment_groups"] = []
    layout = build_target_layout(spec)
    compatibility = classify_layout_compatibility(ir, layout)
    assert compatibility["mode"] == "blocked_target_incomplete"
    assert compatibility["executor_ready"] is False
    assert layout["denominator_applicability"] == "not_applicable_for_current_spec"
    plan = build_adaptation_plan(spec, _candidate(source, locator))
    assert "REVIEW_SOURCE_ROWS_TARGET_INCOMPLETE" in plan["summary"]["by_action"]
    assert "REVIEW_SOURCE_ONLY_ROW" not in plan["summary"]["by_action"]
    assert "SEARCH_TARGET_DENOMINATOR_EVIDENCE" not in plan["summary"]["by_action"]


def test_source_footnotes_grouped_in_plan_and_no_implicit_copy():
    source, locator = _real("CPX-POM-001", "CPXPOM001_T_14_1_3_1")
    ir = parse_source_template(source, locator)
    spec = _spec()
    p = build_adaptation_plan(spec, _candidate(source, locator))
    notes = [op for op in p["operations"] if op["action"] == "REVIEW_SOURCE_FOOTNOTE"]
    assert len(notes) == len(ir["footnote_groups"])
    assert p["summary"]["source_footnotes"] == len(ir["footnotes"])
    assert all(op["execution_supported"] is False for op in notes)
