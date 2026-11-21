"""Per-operation review/execution preconditions for adaptation plan v4.

The planner emits candidates, never approvals.  A blocked target carries
diagnostic-only operations; executors must fail closed if an operation was not
explicitly approved for the exact plan and exact source DOCX SHA-256.
"""
from __future__ import annotations

import copy


_ALLOWED_EXECUTOR_ACTIONS = frozenset({
    "REPLACE_TITLE",
    "REPLACE_HEADER_CANDIDATE",
})
_DIAGNOSTIC_PREFIXES = (
    "REVIEW_", "SEARCH_", "RESOLVE_", "BLOCKED_", "DIAGNOSTIC_",
)


def _diagnostic_action(old_action):
    if old_action == "REPLACE_TITLE":
        return "DIAGNOSTIC_TITLE_MAPPING"
    if old_action in ("KEEP_ROW", "REVIEW_SEMANTIC_ROW_MATCH"):
        return "DIAGNOSTIC_ROW_MAPPING"
    if old_action in ("MATCH_GROUP",):
        return "DIAGNOSTIC_GROUP_MAPPING"
    if old_action in ("KEEP_HEADER", "REPLACE_HEADER_CANDIDATE",
                      "INSERT_COLUMN_CANDIDATE"):
        return "DIAGNOSTIC_COLUMN_MAPPING"
    if old_action in ("INSERT_ROW_CANDIDATE", "AGGREGATE_CATEGORIES_CANDIDATE"):
        return "DIAGNOSTIC_ROW_REQUIREMENT"
    return "DIAGNOSTIC_MAPPING"


def gate_adaptation_operations(operations, gate, compatibility, evidence):
    """Annotate operation preconditions and demote blocked edits to diagnostics.

    Returns an independent list; callers can preserve raw row/column alignment
    separately as evidence of what the matcher compared.
    """
    blocked = gate.get("status") == "blocked"
    plan_mode = compatibility.get("mode")
    issues = evidence.get("missing_or_invalid_fields") or []
    invalid_fields = {
        x.get("field") for x in issues if x.get("status") == "invalid"
    }
    out = []
    for original in operations:
        item = copy.deepcopy(original)
        previous_action = item["action"]
        supported = previous_action in _ALLOWED_EXECUTOR_ACTIONS
        source = item.get("source") or {}
        anchor = source.get("bookmark") if isinstance(source, dict) else None
        target = item.get("target") or {}
        requires_docx_copy = supported
        preconditions = [
            "source_docx_sha256_matches_plan",
            "source_template_id_matches_plan",
            "approved_op_id_and_plan_digest_match",
            "approval_has_named_reviewer",
        ] if requires_docx_copy else []
        if supported:
            preconditions += [
                "source_bookmark_start_and_end_are_unique",
                "bookmark_span_is_single_paragraph",
                "bookmark_text_equals_planned_original_text",
                "replacement_text_matches_approved_target_field",
                "source_word_file_is_never_modified",
            ]
        status = "review_required"
        reasons = []
        if blocked:
            if not previous_action.startswith(_DIAGNOSTIC_PREFIXES):
                item["action"] = _diagnostic_action(previous_action)
                item["original_proposed_action"] = previous_action
            status = "blocked_diagnostic"
            reasons.extend(gate.get("hard_blockers") or [])
        elif plan_mode not in (
            "structural_edit_candidate", "text_or_structural_edit_candidate",
        ) and supported:
            status = "unsupported_layout"
            reasons.append(f"Executor not allowed for adaptation mode {plan_mode}")
        elif supported and not anchor:
            status = "missing_anchor"
            reasons.append("Source Word bookmark was not identified")
        elif supported and invalid_fields:
            status = "invalid_evidence"
            reasons.append("An applicable target provenance link was invalid")
        elif supported:
            status = "review_candidate"
            reasons.append("Explicit human approval and verified source bookmark are required")
        else:
            reasons.append("This operation is diagnostic or needs semantic/layout review")
        item["operation_readiness"] = {
            "status": status,
            "manual_approval_required": True,
            "reviewed": False,
            "approved": False,
            "executor_supported_action": bool(
                supported and not blocked and status == "review_candidate"
            ),
            "preconditions": preconditions,
            "unmet_conditions": reasons,
        }
        item["execution_supported"] = False
        item["requires_review"] = True
        out.append(item)
    return out
