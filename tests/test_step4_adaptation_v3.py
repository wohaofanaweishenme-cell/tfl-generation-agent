"""Stage B.5 / Adaptation Planner v3 risk-based regression tests."""
from copy import deepcopy
from pathlib import Path

import pytest

from tfl_agent.agent.adaptation_planner import build_adaptation_plan
from tfl_agent.agent.column_roles import map_column_roles, source_column_role
from tfl_agent.agent.planning_gate import evaluate_target_completeness
from tfl_agent.agent.source_structure_parser import parse_source_template
from tfl_agent.agent.structure_alignment import align_target_rows, classify_layout_compatibility
from tfl_agent.agent.target_evidence_resolver import resolve_target_evidence
from tfl_agent.agent.target_layout_builder import build_target_layout
from test_step4_adaptation_planner import _fixtures, _spec, _candidate

LIBRARY = Path(__file__).resolve().parents[1] / "library"


def real_source(study, template):
    docx = LIBRARY / "TFL_Template_Library" / "table" / (template + ".docx")
    locator = (LIBRARY / "studies" / study / "intermediate"
               / "DOCX_Locator_Map" / (template + ".json"))
    if not docx.is_file() or not locator.is_file():
        pytest.skip("Real official Library unavailable in checkout")
    return docx, locator


def test_ae_grade3_aggregates_severity_group_not_patient_counts():
    docx, loc = real_source("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    ir = parse_source_template(docx, loc)
    stats = {
        r["label"]: r for r in ir["hierarchical_rows"]
        if r["label"] in ("Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5")
    }
    assert len(stats) == 5
    assert len({r["parent_row_id"] for r in stats.values()}) == 1
    assert stats["Grade 1"]["position"]["column_index"] == 1
    assert stats["Grade 1"]["parent_row_id"] is not None
    for spelling in ("Grade >=3 TEAEs", "Grade >= 3 TEAEs",
                     "Grade ≥3 TEAEs", "Grade ≥ 3 TEAEs"):
        spec = _spec()
        spec["table_requirements"]["row_requirements"] = [spelling]
        match = align_target_rows(ir, build_target_layout(spec))["matches"]
        assert len(match) == 1
        assert match[0]["relation"] == "aggregation_candidate"
        assert [x["label"] for x in match[0]["source"]["source_rows"]] == [
            "Grade 3", "Grade 4", "Grade 5"
        ]
        assert match[0]["source"]["requires_patient_level_calculation"] is True
    spec["table_requirements"]["row_requirements"] = ["Related Grade >=3 TEAEs"]
    related = align_target_rows(ir, build_target_layout(spec))["matches"]
    assert not any(x["relation"] == "aggregation_candidate" for x in related)


def test_gender_sex_review_alias_and_race_hierarchy():
    docx, loc = real_source("CPX-POM-001", "CPXPOM001_T_14_1_3_1")
    ir = parse_source_template(docx, loc)
    sex = next(r for r in ir["hierarchical_rows"] if r["label"].startswith("Sex ["))
    race = next(r for r in ir["hierarchical_rows"] if r["label"].startswith("Race ["))
    male = next(r for r in ir["hierarchical_rows"] if r["label"] == "Male")
    white = next(r for r in ir["hierarchical_rows"] if r["label"] == "White")
    asian = next(r for r in ir["hierarchical_rows"] if r["label"] == "Asian")
    assert male["parent_row_id"] == sex["row_id"]
    assert white["parent_row_id"] == race["row_id"]
    assert asian["parent_row_id"] == race["row_id"]
    spec = _spec()
    spec["identity"]["title"] = "Demographic and Baseline Characteristics"
    spec["table_requirements"]["row_requirements"] = ["gender"]
    match = align_target_rows(ir, build_target_layout(spec))["matches"][0]
    assert match["source"]["label"].startswith("Sex [")
    assert match["relation"] == "domain_synonym_requires_review"


def test_bor_parent_is_group_not_insert_when_four_children_match():
    docx, loc = real_source("WTX-330x2101", "WTX330X2101_T_14_2_1_1")
    spec = _spec()
    spec["identity"]["title"] = "Overall Response Rate and Clinical Benefit Rate"
    spec["table_requirements"]["row_requirements"] = [
        "Best overall response categories: CR, PR, SD, PD"
    ]
    plan = build_adaptation_plan(spec, _candidate(docx, loc))
    group = [x for x in plan["row_alignment"]["matches"]
             if x["relation"] == "group_covered_by_children"]
    assert len(group) == 1
    assert len(group[0]["source"]["matched_children"]) == 4
    assert any(x["action"] == "MATCH_GROUP" for x in plan["operations"])
    assert not any(x["action"] == "INSERT_ROW_CANDIDATE" and
                   "Best overall response categories" in (x.get("target") or {}).get("label", "")
                   for x in plan["operations"])


def test_patient_disposition_total_is_overall_and_blocked():
    docx, loc = real_source("ARV-471-BC-201", "ARV471BC201_T_14_1_2_1")
    spec = _spec()
    spec["identity"]["tfl_id"] = "14.1.1.1"
    spec["identity"]["title"] = "Patient Disposition"
    spec["readiness"] = "blocked"
    spec["table_requirements"]["row_requirements"] = [
        "number of patients screened", "number of patients completed cycle 3"
    ]
    spec["statistical_requirements"]["statistics_to_display"] = ["frequency counts", "percentages"]
    spec["table_requirements"]["column_requirements"] = ["Overall"]
    plan = build_adaptation_plan(spec, _candidate(docx, loc))
    assert plan["planning_gate"]["status"] == "blocked"
    assert plan["adaptation_mode"] == "blocked_target_readiness"
    assert plan["executor_ready"] is False
    assert source_column_role("Total (N=xx)") == "overall"
    align = plan["column_alignment"]
    assert any(x["source_header"]["label"].startswith("Total") and
               x["target_role"] == "overall"
               for x in align["target_matches"])
    assert not any(x["action"] == "REPLACE_HEADER_CANDIDATE" and
                   "Total" in str(x["source"])
                   for x in plan["operations"])
    assert any(x["action"] == "BLOCKED_TARGET_COLUMN_OPERATIONS"
               for x in plan["operations"])


def test_only_total_source_cannot_replace_treatment_group_even_if_first():
    source = {
        "column_candidates": [{
            "label": "Total",
            "position": {"location_type": "table_cell", "table_index": 0,
                         "row_index": 0, "column_index": 3},
        }],
        "table_count": 1,
    }
    target = {"columns": [
        {"label": "Tenalisib 800 mg BID", "kind": "treatment_group"},
        {"label": "Tenalisib 1200 mg BID", "kind": "treatment_group"},
        {"label": "Overall", "kind": "overall"},
    ]}
    result = map_column_roles(
        source, target,
        {"mode": "blocked_target_readiness", "source_axis": "treatment_arm_columns"},
        completeness={"status": "blocked"},
    )
    assert len(result["target_matches"]) == 1
    assert result["target_matches"][0]["target"]["kind"] == "overall"
    assert len([x for x in result["proposed_operations"]
                if x["action"] == "REVIEW_MISSING_TREATMENT_GROUP_COLUMN"]) == 2
    assert not any(x["action"] == "REPLACE_HEADER_CANDIDATE"
                   for x in result["proposed_operations"])


def test_ae_overall_insertion_index_four_and_alias_not_autoapproved():
    docx, loc = real_source("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    plan = build_adaptation_plan(_spec(), _candidate(docx, loc))
    op = next(op for op in plan["operations"]
              if op["action"] == "INSERT_COLUMN_CANDIDATE")
    assert op["source"]["insertion_physical_grid_index"] == 4
    assert op["source"]["target_column_index"] == 2
    assert not any(x["execution_supported"] for x in plan["operations"])
    related = [
        x for x in plan["row_alignment"]["matches"]
        if x["relation"] == "clinical_alias_requires_definitional_review"
    ]
    assert related, [(m['target']['label'], m['relation'], (m.get('source') or {}).get('label')) for m in plan['row_alignment']['matches'][:8]]


def test_pfs_rebuild_and_incomplete_hema_blocked():
    pfs, loc = real_source("OMO-103-01", "OMO10301_T_14_2_1_1")
    spec = _spec()
    spec["identity"]["title"] = "Progression Free Survival (PFS)"
    spec["statistical_requirements"]["analysis_methods"] = [
        "Kaplan-Meier and Brookmeyer-Crowley 95% CI"
    ]
    spec["statistical_requirements"]["statistics_to_display"] = [
        "Q1", "median", "Q3", "95% confidence intervals"
    ]
    plan = build_adaptation_plan(spec, _candidate(pfs, loc))
    assert plan["adaptation_mode"] == "rebuild_with_source_style"
    assert plan["layout_compatibility"]["source_axis"] == "cohort_rows_statistic_columns"
    hema, hloc = real_source("SP11631", "SP11631_T_14_5_2_1_1")
    spec["identity"]["title"] = "Hematology"
    spec["readiness"] = "blocked"
    spec["table_requirements"]["row_requirements"] = []
    spec["statistical_requirements"]["statistics_to_display"] = []
    hp = build_adaptation_plan(spec, _candidate(hema, hloc))
    assert hp["adaptation_mode"] == "blocked_target_incomplete"
    assert hp["planning_gate"]["status"] == "blocked"
    assert hp["executor_ready"] is False


def test_quote_verification_and_body_only_targeted_retrieval():
    spec = _spec()
    blocks = {
        "blocks": [
            {"block_id": "SAP_AE", "page": 19,
             "text": "AE counts and events are summarized for the safety set."},
            {"block_id": "S_12", "page": 12,
             "text": "Unless otherwise specified, the denominator for percentages "
                     "is the number of patients with a non-missing assessment."},
            {"block_id": "HOLDOUT", "page": 49,
             "text": "The final approved source TFL shell footnote must NEVER leak."},
        ],
    }
    result = resolve_target_evidence(spec, blocks, allowed_body_pages=(4, 21))
    assert result["authorized_block_count"] == 2
    assert result["linked_evidence_quote_checks"][0]["status"] == "quote_text_verified"
    denom = next(x for x in result["missing_requirement_candidates"]
                 if x["field"] == "denominator_rule")
    assert any(x["ref_id"] == "S_12" for x in denom["candidate_blocks"])
    assert all(x["page"] <= 21 for y in result["missing_requirement_candidates"]
               for x in y["candidate_blocks"])
    assert not result["target_spec_modified"]
    bad = deepcopy(spec)
    bad["provenance"]["evidence"][0]["exact_text"] = "Fabricated quote"
    checked = resolve_target_evidence(bad, blocks, allowed_body_pages=(4, 21))
    assert checked["invalid_quotes"]
    with pytest.raises(ValueError, match="SAP body-page range"):
        resolve_target_evidence(spec, blocks, allowed_body_pages=None)


def test_planner_plan_only_with_verified_target_blocks(tmp_path):
    docx, locator = _fixtures(tmp_path)
    blocks = {"blocks": [
        {"block_id": "SAP_AE", "page": 19,
         "text": "AE counts and events are summarized by treatment group."}
    ]}
    plan = build_adaptation_plan(
        _spec(), _candidate(docx, locator),
        parsed_sap_blocks=blocks, sap_body_page_range=(4, 21),
    )
    assert plan["schema_version"] == "adaptation-plan-3.0"
    assert plan["evidence_validation"]["source_quote_verification_performed"] is True
    assert plan["target_evidence_lookup"]["authorized_block_count"] == 1
    assert plan["target_evidence_lookup"]["invalid_quotes"] == []
    assert plan["target_evidence_lookup"]["clinical_semantic_support_verified"] is False
    assert plan["executor_ready"] is False
    assert not list(tmp_path.rglob("*DRAFT.docx"))
