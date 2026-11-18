"""Stage B.6: section-aware SAP retrieval and approved-only DOCX executor."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
from docx import Document

from tfl_agent.agent.adaptation_planner import build_adaptation_plan
from tfl_agent.agent.docx_text_executor import (
    build_pending_review_packet, execute_approved_docx_edits,
)
from tfl_agent.agent.target_evidence_resolver import resolve_target_evidence
from test_step4_adaptation_planner import _fixtures, _spec, _candidate
from test_step4_adaptation_v3 import real_source


def _make_approval(plan, *, op_id=None):
    packet = build_pending_review_packet(plan)
    packet["reviewer"] = "SAP Table Reviewer"
    allowed = packet["operations"]
    if op_id is None:
        selected = next(x for x in allowed if x["action"] == "REPLACE_HEADER_CANDIDATE")
    else:
        selected = next(x for x in allowed if x["op_id"] == op_id)
    selected["decision"] = "approved"
    selected["replacement_text"] = selected["allowed_replacement_texts"][0]
    selected["review_note"] = "Reviewed table-label text in source and target specification."
    return packet, selected


def test_endpoint_section_ranking_avoids_abbreviation_glossary():
    spec = _spec()
    blocks = {"blocks": [
        {"page": 4, "block_id": "sap:p4:b2",
         "text": "CR Complete Response PR Partial Response ECG Electrocardiogram "
                 "TEAE Treatment Emergent Adverse Event AE Adverse Event "
                 "GCP Good Clinical Practice ITT Intention To Treat"},
        {"page": 11, "block_id": "sap:p11:b11",
         "text": "7.1 General Methodology Percentages and summaries by analysis "
                 "population will be reported. Missing data and baseline rules."},
        {"page": 19, "block_id": "sap:p19:b3",
         "text": "8.8.2 Adverse Events Adverse events will be summarized by "
                 "treatment and patient counts using Safety Analysis Set."},
        {"page": 19, "block_id": "sap:p19:b4",
         "text": "Related TEAEs, Serious TEAEs, Grade >=3 TEAEs and adverse events "
                 "leading to discontinuation will be summarized by treatment."},
        {"page": 20, "block_id": "sap:p20:b4",
         "text": "8.8.3 Clinical Laboratory Evaluations Hematology results are summarized."},
        {"page": 49, "block_id": "HOLDOUT",
         "text": "Final approved Table 14.3.1.1 is NOT allowed in evidence."},
    ]}
    result = resolve_target_evidence(spec, blocks, allowed_body_pages=(4, 21))
    notes = next(x for x in result["missing_requirement_candidates"]
                 if x["field"] == "footnote_requirements")
    assert notes["retrieval_strategy"] == "endpoint_section_first_with_general_fallback"
    assert notes["candidate_blocks"][0]["ref_id"] == "sap:p19:b3"
    assert notes["candidate_blocks"][0]["section_id"] == "8.8.2"
    assert notes["candidate_blocks"][0]["source_section_relevance"] == "target_section"
    assert "HOLDOUT" not in [x["ref_id"] for x in notes["candidate_blocks"]]
    assert "sap:p4:b2" not in [x["ref_id"] for x in notes["candidate_blocks"]]
    assert not result["clinical_semantic_support_verified"]


def test_blocked_plans_are_only_diagnostic_and_all_ops_unapproved(tmp_path):
    source, locator = _fixtures(tmp_path)
    spec = _spec()
    spec["readiness"] = "blocked"
    p = build_adaptation_plan(spec, _candidate(source, locator))
    assert p["planning_gate"]["status"] == "blocked"
    assert p["execution_policy"]["blocked_plans_diagnostic_only"]
    assert all(not x["execution_supported"] for x in p["operations"])
    assert all(not x["operation_readiness"]["executor_supported_action"]
               for x in p["operations"])
    assert not any(op["action"].startswith(("INSERT_", "REPLACE_"))
                   for op in p["operations"])
    assert any(op["action"] == "DIAGNOSTIC_TITLE_MAPPING" for op in p["operations"])
    assert build_pending_review_packet(p)["operations"] == []
    with pytest.raises(ValueError, match="Blocked target"):
        execute_approved_docx_edits(
            p, {"reviewer": "Clinical Reviewer"}, source_docx=source,
            output_docx=tmp_path / "output" / "no.docx"
        )


def test_explicit_approval_is_required_and_source_unchanged(tmp_path):
    source, locator = _fixtures(tmp_path)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    plan = build_adaptation_plan(_spec(), _candidate(source, locator))
    assert plan["schema_version"] == "adaptation-plan-4.0"
    packet, approved = _make_approval(plan)
    assert packet["review_packet_version"] == "docx-approval-1.0"
    assert len(approved["allowed_replacement_texts"]) >= 1
    assert all(op["decision"] != "approved" for op in
               build_pending_review_packet(plan)["operations"])
    destination = tmp_path / "output" / "AE_approved_text_only.docx"
    result = execute_approved_docx_edits(
        plan, packet, source_docx=source, output_docx=destination,
    )
    assert result["status"] == "text_edits_applied_to_unapproved_copy"
    assert result["applied_count"] == 1
    assert result["clinical_approval"] is False
    assert result["source_docx_unchanged"] is True
    assert destination.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert Document(destination).tables[0].cell(0, 1).text == "Tenalisib 800 mg BID"
    assert Document(source).tables[0].cell(0, 1).text == "Arm A"


def test_pending_approval_or_stale_plan_fails_closed(tmp_path):
    source, locator = _fixtures(tmp_path)
    plan = build_adaptation_plan(_spec(), _candidate(source, locator))
    packet = build_pending_review_packet(plan)
    packet["reviewer"] = "Clinical Reviewer"
    output = tmp_path / "output" / "rejected.docx"
    with pytest.raises(ValueError, match="No approved"):
        execute_approved_docx_edits(plan, packet, source_docx=source,
                                    output_docx=output)
    packet, selected = _make_approval(plan)
    selected["replacement_text"] = "Fabricated treatment data"
    with pytest.raises(ValueError, match="Unapproved replacement"):
        execute_approved_docx_edits(plan, packet, source_docx=source,
                                    output_docx=output)
    packet, selected = _make_approval(plan)
    packet["plan_sha256"] = "deadbeef"
    with pytest.raises(ValueError, match="stale"):
        execute_approved_docx_edits(plan, packet, source_docx=source,
                                    output_docx=output)
    packet, selected = _make_approval(plan)
    with pytest.raises(ValueError, match="source template folder"):
        execute_approved_docx_edits(
            plan, packet, source_docx=source,
            output_docx=source.parent / "do_not_write.docx"
        )
    assert not output.exists()


def test_source_bookmark_content_mismatch_blocks_and_preserves_source(tmp_path):
    source, locator = _fixtures(tmp_path)
    plan = build_adaptation_plan(_spec(), _candidate(source, locator))
    packet, _ = _make_approval(plan)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    # A forged source-text claim is caught even if an attacker has recomputed
    # the packet digest: physical Word bookmark content must match.
    target_op = next(x for x in plan["operations"]
                     if x["action"] == "REPLACE_HEADER_CANDIDATE")
    target_op["source"]["label"] = "Not the real header text"
    from tfl_agent.agent.docx_text_executor import _digest_json
    packet["plan_sha256"] = _digest_json(plan)
    output = tmp_path / "output" / "bad.docx"
    with pytest.raises(ValueError, match="Source bookmark text differs"):
        execute_approved_docx_edits(plan, packet, source_docx=source,
                                    output_docx=output)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert not output.exists()


def test_real_ae_plan_offers_only_reviewable_bookmarked_header_edits():
    source, locator = real_source("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    p = build_adaptation_plan(_spec(), _candidate(source, locator))
    packet = build_pending_review_packet(p)
    action_names = [x["action"] for x in packet["operations"]]
    assert "REPLACE_HEADER_CANDIDATE" in action_names
    assert all(x["decision"] == "pending" for x in packet["operations"])
    assert any("Tenalisib 800 mg BID" in str(x["target"])
               for x in packet["operations"])
    assert all(x["bookmark"] for x in packet["operations"])
