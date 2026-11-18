"""Unapproved automatic text-only preview of a review-gated Table Plan.

This module is deliberately separate from the human-approved DOCX executor.
It MUST NOT create manual approval packets or pretend any operation was
approved. It is a safe draft preview for non-blocked plans only.

Only source-hash-bound, bookmark-anchored title and treatment-arm text may
change. All unexecuted row, column, footnote, denominator and layout work is
reported explicitly; this is NOT a completed target TFL Shell.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from docx import Document

from tfl_agent.agent.docx_text_executor import (
    SUPPORTED_ACTIONS, _replace_bookmark, _expected_replacement,
    _bookmark_span,
)


def _display_only_allowed(op, plan):
    candidates = _expected_replacement(op, plan)
    if op["action"] == "REPLACE_TITLE":
        # Title spelling is a proposal from the extracted target identity;
        # preserve the exact target text, do not add invented descriptors.
        return candidates[0] if candidates else None
    if op["action"] == "REPLACE_HEADER_CANDIDATE":
        # Prefer preserving only existing generic placeholder tokens.
        # Never infer a numerical N or a percentage denominator.
        return candidates[-1] if candidates else None
    return None


def _header_evidence_confirmed(plan, op):
    """Require linked target-body text to visibly name the target arm.

    This is a *textual presence* check, not a claim of proven clinical
    equivalence between source and target treatment groups.
    """
    evidence = op.get("target_evidence") or {}
    refs = evidence.get("ref_ids") or []
    if not refs:
        return False
    resolver = plan.get("target_evidence_lookup") or {}
    statuses = {
        check["ref_id"]: check.get("status")
        for check in resolver.get("linked_evidence_quote_checks") or []
    }
    if not all(statuses.get(ref) == "quote_text_verified" for ref in refs):
        return False
    target_name = str((op.get("target") or {}).get("label") or "").strip().casefold()
    if not target_name:
        return False
    # Target arm name must literally occur in the SAP quotations provided.
    previews = " ".join(
        str(x) for x in evidence.get("quote_previews") or []
    ).casefold()
    # Step-2 quote_previews are clipped to 220 characters; the second
    # Tenalisib arm occurs near that limit. Use only independently verified
    # quote previews from the authorized SAP-body resolver as additional
    # evidence, never raw target template content.
    verified_quote_previews = " ".join(
        str(item.get("exact_text_preview") or "")
        for item in resolver.get("linked_evidence_quote_checks") or []
        if item.get("ref_id") in refs
        and item.get("status") == "quote_text_verified"
    ).casefold()
    return target_name in previews or target_name in verified_quote_previews


def _summary(plan, applied, skipped, *, status, output=None, warnings=None):
    pending_by_action = Counter(
        op["action"] for op in plan.get("operations") or []
        if op["op_id"] not in {x["op_id"] for x in applied}
    )
    return {
        "status": status,
        "output_docx": str(output) if output else None,
        "source_template_id": plan.get("source_template_id"),
        "target_tfl_id": plan.get("target_tfl_id"),
        "applied_unapproved_preview_edits": applied,
        "applied_count": len(applied),
        "skipped_preview_edits": skipped,
        "remaining_operations_by_action": dict(pending_by_action),
        "target_unresolved_fields": (plan.get("summary") or {}).get(
            "target_unresolved_fields", []
        ),
        "planning_gate": (plan.get("planning_gate") or {}).get("status"),
        "clinical_approval": False,
        "auto_approval_performed": False,
        "word_layout_validated": False,
        "shell_complete": False,
        "warnings": warnings or [],
        "next_action": (
            "Complete structural adaptation, statistical definitions, "
            "footnotes and validation before treating this as a TFL shell"
        ),
    }


def build_unapproved_auto_text_draft(plan, *, source_docx, output_docx):
    """Create a *nonapproved* text draft with stringent deterministic guards.

    This function does NOT call the manual-approval executor or set any
    operation's approved flag. If the plan is blocked, layout is incompatible,
    or source hash is wrong, it does not produce a DOCX.
    """
    gate = (plan.get("planning_gate") or {}).get("status")
    if gate == "blocked":
        return _summary(
            plan, [], [], status="skipped_blocked",
            warnings=["Blocked target Specification. No DOCX created."],
        )
    if plan.get("adaptation_mode") not in (
        "structural_edit_candidate", "text_or_structural_edit_candidate"
    ):
        return _summary(
            plan, [], [], status="skipped_layout_incompatible",
            warnings=["Source and target layout cannot be safely text-edited."],
        )
    if plan.get("schema_version") != "adaptation-plan-4.0":
        raise ValueError("Auto preview expects adaptation-plan-4.0")
    source = Path(source_docx).resolve()
    destination = Path(output_docx).resolve()
    if source == destination or destination.is_relative_to(source.parent):
        raise ValueError("Cannot modify original Library or save into source directory")
    if destination.exists():
        raise FileExistsError("Output DOCX already exists")
    if destination.suffix.lower() != ".docx":
        raise ValueError("Output must be a DOCX")
    if not source.is_file() or source.stem != plan.get("source_template_id"):
        raise ValueError("Missing or wrong source DOCX")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != (plan.get("source_integrity") or {}).get("sha256"):
        raise ValueError("Source checksum does not match Plan")
    if (plan.get("source_integrity") or {}).get("verified") is not True:
        raise ValueError("Source integrity not verified")

    operations = plan.get("operations") or []
    candidates = [
        op for op in operations
        if op.get("action") in SUPPORTED_ACTIONS
        and (op.get("operation_readiness") or {}).get(
            "executor_supported_action") is True
    ]
    if not candidates:
        return _summary(
            plan, [], [], status="no_safe_text_edit_candidates",
            warnings=["No eligible source-bookmarked text edits in Plan."],
        )

    doc = Document(source)
    applied, skipped, used_bookmarks = [], [], set()
    for op in candidates:
        op_id = op["op_id"]
        item = op.get("source") or {}
        bookmark = item.get("bookmark")
        target = op.get("target") or {}
        allowed = _display_only_allowed(op, plan)
        if not bookmark or bookmark in used_bookmarks or not allowed:
            skipped.append({"op_id": op_id, "reason": "No unique bookmark or target text"})
            continue
        if op["action"] == "REPLACE_HEADER_CANDIDATE":
            if not _header_evidence_confirmed(plan, op):
                skipped.append({
                    "op_id": op_id, "reason": "Target SAP quote did not verify arm label"
                })
                continue
            if target.get("kind") != "treatment_group":
                skipped.append({
                    "op_id": op_id,
                    "reason": "Only treatment-arm header text is eligible for auto preview",
                })
                continue
        old = item.get("text") or item.get("label")
        try:
            # Required: unique bookmark, single paragraph, no complex fields,
            # and exact old text before mutation.
            _replace_bookmark(doc, bookmark, old, allowed)
        except ValueError as err:
            skipped.append({"op_id": op_id, "reason": str(err)})
            continue
        used_bookmarks.add(bookmark)
        applied.append({
            "op_id": op_id,
            "action": op["action"],
            "bookmark": bookmark,
            "old_text": old,
            "draft_text": allowed,
            "evidence_status": (
                "target_quote_verified_text_only"
                if op["action"] == "REPLACE_HEADER_CANDIDATE"
                else "target_title_from_unapproved_specification"
            ),
            "approved": False,
        })
    if not applied:
        return _summary(
            plan, applied, skipped, status="no_safe_text_edit_candidates",
            warnings=["All attempted edits were rejected by safety preconditions."],
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.stem + ".tmp.docx")
    if temp.exists():
        raise FileExistsError("Temporary output already exists")
    try:
        doc.save(temp)
        reopened = Document(temp)
        for op in applied:
            _, _, actual = _bookmark_span(reopened, op["bookmark"])
            if " ".join(actual.split()) != " ".join(op["draft_text"].split()):
                raise ValueError("Text did not survive DOCX bookmark round-trip")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("Source DOCX changed during preview generation")
        temp.rename(destination)
    finally:
        if temp.exists():
            temp.unlink()
    return _summary(
        plan, applied, skipped, status="unapproved_text_preview_generated",
        output=destination,
        warnings=[
            "Automatic preview is NOT human approval and NOT a completed Table Shell.",
            "Unresolved row/column/footnote/statistical edits remain untouched.",
        ],
    )
