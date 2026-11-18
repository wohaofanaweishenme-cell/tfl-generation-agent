"""No-review automatic text draft tests.

These are intentionally UNAPPROVED outputs, separate from human-approved
DOCX text execution. Source studies and genuine target-SAP evidence remain
separate; no clinical-statistical approval is ever implied.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from docx import Document
from tfl_agent.agent.adaptation_planner import build_adaptation_plan
from tfl_agent.agent.auto_text_draft import build_unapproved_auto_text_draft
from test_step4_adaptation_planner import _fixtures, _spec, _candidate
from test_step4_adaptation_v3 import real_source


SYNTHETIC_SAP_QUOTE = (
    "4.3 Method of Assignment of Patients to Treatment Groups "
    "Eligible patients will be randomized in 1:1 ratio to Group 1: "
    "Tenalisib 800 mg BID or Group 2: Tenalisib 1200 mg BID."
)


def _verified_spec():
    spec = _spec()
    spec["provenance"]["evidence"].append({
        "ref_id": "sap:p5:b10", "exact_text": SYNTHETIC_SAP_QUOTE,
    })
    spec["provenance"]["field_links"].append({
        "json_pointer": "/statistical_requirements/treatment_groups",
        "ref_ids": ["sap:p5:b10"],
    })
    return spec


def _parsed_body():
    return {
        "blocks": [
            {"block_id": "sap:p5:b10", "page": 5, "text": SYNTHETIC_SAP_QUOTE},
            {"block_id": "SAP_AE", "page": 19,
             "text": "AE counts and events are summarized."},
            {"block_id": "held-out-shell", "page": 55,
             "text": "HOLDOUT; not authorized as evidence"},
        ]
    }


def test_zero_approval_auto_draft_edits_only_evidence_verified_headers(tmp_path):
    src, loc = _fixtures(tmp_path)
    initial_sha = hashlib.sha256(src.read_bytes()).hexdigest()
    p = build_adaptation_plan(
        _verified_spec(), _candidate(src, loc),
        parsed_sap_blocks=_parsed_body(), sap_body_page_range=(4, 21),
    )
    assert p["schema_version"] == "adaptation-plan-4.0"
    assert p["planning_gate"]["status"] != "blocked"
    output = tmp_path / "drafts" / "AE_TEXT_ONLY_UNAPPROVED.docx"
    result = build_unapproved_auto_text_draft(
        p, source_docx=src, output_docx=output
    )
    assert result["status"] == "unapproved_text_preview_generated"
    assert result["applied_count"] == 2  # Source title bookmark intentionally not safely anchored
    assert result["auto_approval_performed"] is False
    assert result["clinical_approval"] is False
    assert result["word_layout_validated"] is False
    assert result["shell_complete"] is False
    assert output.exists()
    doc = Document(output)
    assert "Tenalisib 800 mg BID" in doc.tables[0].cell(0, 1).text
    assert "Tenalisib 1200 mg BID" in doc.tables[0].cell(0, 2).text
    assert hashlib.sha256(src.read_bytes()).hexdigest() == initial_sha


def test_no_auto_header_without_verified_specific_sap_arm_quote(tmp_path):
    src, loc = _fixtures(tmp_path)
    plan = build_adaptation_plan(_spec(), _candidate(src, loc))
    dest = tmp_path / "draft" / "no_approval.docx"
    result = build_unapproved_auto_text_draft(
        plan, source_docx=src, output_docx=dest
    )
    assert result["status"] == "no_safe_text_edit_candidates"
    assert not dest.exists()
    assert result["applied_count"] == 0
    assert result["skipped_preview_edits"]


def test_blocked_or_incompatible_layout_is_skipped_without_word(tmp_path):
    src, loc = _fixtures(tmp_path)
    blocked = _verified_spec()
    blocked["readiness"] = "blocked"
    plan = build_adaptation_plan(blocked, _candidate(src, loc))
    outfile = tmp_path / "output" / "blocked.docx"
    summary = build_unapproved_auto_text_draft(
        plan, source_docx=src, output_docx=outfile
    )
    assert summary["status"] == "skipped_blocked"
    assert summary["output_docx"] is None
    assert not outfile.exists()

    incompatible = build_adaptation_plan(_verified_spec(), _candidate(src, loc))
    incompatible["adaptation_mode"] = "rebuild_with_source_style"
    summary = build_unapproved_auto_text_draft(
        incompatible, source_docx=src, output_docx=outfile
    )
    assert summary["status"] == "skipped_layout_incompatible"
    assert not outfile.exists()


def test_hash_mismatch_and_source_directory_write_fail_closed(tmp_path):
    src, loc = _fixtures(tmp_path)
    p = build_adaptation_plan(_verified_spec(), _candidate(src, loc))
    dest = tmp_path / "output" / "example.docx"
    bad = deepcopy(p)
    bad["source_integrity"]["sha256"] = "invalid-digest"
    import pytest
    with pytest.raises(ValueError, match="checksum"):
        build_unapproved_auto_text_draft(
            bad, source_docx=src, output_docx=dest
        )
    with pytest.raises(ValueError, match="source directory"):
        build_unapproved_auto_text_draft(
            p, source_docx=src,
            output_docx=src.parent / "should_not_exist.docx"
        )
    assert not dest.exists()


def test_real_ae_auto_preview_read_only_and_not_a_completed_shell(tmp_path):
    src, loc = real_source("P-VCNA-003", "PVCNA003_T_14_3_1_1")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    plan = build_adaptation_plan(
        _verified_spec(), _candidate(src, loc),
        parsed_sap_blocks=_parsed_body(), sap_body_page_range=(4, 21),
    )
    dest = tmp_path / "ae" / "AE_UNAPPROVED_TEXT_PREVIEW.docx"
    out = build_unapproved_auto_text_draft(
        plan, source_docx=src, output_docx=dest
    )
    assert out["status"] == "unapproved_text_preview_generated"
    assert out["applied_count"] >= 2
    assert not out["shell_complete"]
    assert out["remaining_operations_by_action"].get("INSERT_COLUMN_CANDIDATE", 0) >= 1
    assert dest.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha
