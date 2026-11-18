"""Build a reviewable Source-to-Target Table Adaptation Plan.

No DOCX writes, LLM calls, or clinical approvals.  The plan deliberately
separates same-label KEEP proposals from inferred structural edits.  It does
not silently delete source-only rows or transplant source-study footnotes.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re

from tfl_agent.agent.source_structure_parser import parse_source_template
from tfl_agent.agent.target_layout_builder import build_target_layout


def _canon(text):
    s = str(text or "").casefold()
    s = re.sub(r"treatment[\s-]*emergent adverse events?", "teae", s)
    s = re.sub(r"\bteae\s*\(\s*teae\s*\)", "teae", s)
    s = re.sub(r"\btreatment[\s-]*emergent\b", "teae", s)
    s = s.replace(">=", "≥")
    s = re.sub(r"[^a-z0-9≥]+", " ", s)
    return " ".join(s.split())


def _similarity(first, second):
    a, b = _canon(first), _canon(second)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _clinical_tokens(text):
    return set(_canon(text).split()) & {
        "non", "serious", "fatal", "grade", "related", "dose", "teae",
        "discontinuation", "death", "progression", "safety", "response",
        "censored", "baseline", "hematology", "biochemistry", "ecg",
    }


def _candidate_pair(target, options, used):
    """Exact labels first; fuzzy alternatives are always REVIEW-only.

    Require matching protected clinical tokens for fuzzy substitutions so a
    serious event is not silently paired with an unrelated event.
    """
    best = None
    for i, option in enumerate(options):
        if i in used:
            continue
        value = option["label"]
        score = _similarity(target, value)
        same = _canon(target) == _canon(value)
        if not same and _clinical_tokens(target) != _clinical_tokens(value):
            continue
        if same or score >= 0.76:
            if best is None or (same, score) > (best[2], best[3]):
                best = (i, option, same, score)
    return best


def _op(operations, action, scope, *,
        source=None, target=None, evidence=None,
        reason="", status="review_required", risk=None):
    item = {
        "op_id": f"OP{len(operations)+1:04d}",
        "action": action,
        "scope": scope,
        "status": status,
        "source": source,
        "target": target,
        "target_evidence": evidence or {"ref_ids": [], "json_pointer": None},
        "requires_review": status != "verified_no_edit",
        "reason": reason,
        "risk": risk or [],
        "execution_supported": False,
    }
    operations.append(item)
    return item


def build_adaptation_plan(spec, candidate):
    """Build a source-backed plan for one approved, real Table candidate.

    Args:
      spec: previously extracted target Table Specification, with provenance.
      candidate: Step-3 match (source_path, template.locator_map_path,
                 template_id, score, cross_endpoint, source_study_id).
    Returns:
      A JSON-serializable plan including source_ir and target_ir.
      This function is PLANNING ONLY and always requires review.
    """
    if candidate.get("cross_endpoint") or candidate.get("requires_endpoint_review"):
        raise ValueError("Known endpoint mismatch: source cannot be planned without manual selection")
    source_path = candidate["source_path"]
    locator_path = candidate["template"].get("locator_map_path")
    if not locator_path:
        raise ValueError("Step-3 candidate has no verified bookmark locator map")
    source = parse_source_template(source_path, locator_path)
    target = build_target_layout(spec)
    if source["template_id"] != candidate["template_id"]:
        raise ValueError("Step-3 candidate and source locator identify different templates")

    operations = []
    evidence = target["evidence_by_field"]
    title_candidates = source["title_candidates"]
    title_source = title_candidates[0] if title_candidates else None
    _op(
        operations, "REPLACE_TITLE", "title",
        source=title_source,
        target={"tfl_id": target["identity"]["tfl_id"],
                "text": target["identity"]["title"]},
        evidence=evidence["title"],
        reason="Target study TFL title and number supersede source study title",
        risk=["Source header, protocol number and repeated page headings require review"],
    )

    if candidate.get("population_change_required"):
        _op(
            operations, "REVIEW_POPULATION_MISMATCH", "analysis_population",
            target={"population": target["analysis_population"]},
            evidence=evidence["population"],
            reason="Step 3 identified a source/target population mismatch",
            risk=["Denominators and analysis population definitions can change"],
        )

    # Header/arm mapping: the locator's 'header_cell' gives a candidate anchor,
    # not proof of a one-to-one clinical treatment mapping.
    raw_headers = source["column_candidates"]
    target_columns = target["columns"]
    if not raw_headers:
        _op(
            operations, "REVIEW_COLUMN_GEOMETRY", "columns",
            target={"labels": [x["label"] for x in target_columns]},
            evidence=evidence["columns"],
            reason="Source has no verified header_cell roles; inspect actual table/paragraph geometry",
            risk=["Cannot assign source treatment-group bookmarks deterministically"],
        )
    else:
        source_index = 0
        for column in target_columns:
            if column["kind"] == "overall" and not any(
                "overall" in x["label"].casefold() or "total" in x["label"].casefold()
                for x in raw_headers
            ):
                _op(
                    operations, "INSERT_COLUMN_CANDIDATE", "columns",
                    source={"after_column": raw_headers[-1], "logical_index": len(raw_headers)},
                    target=column, evidence=column["basis"],
                    reason="Target explicitly requests Overall; no explicit Overall source header",
                    risk=["Merged header geometry and denominators require review"],
                )
                continue
            if source_index >= len(raw_headers):
                _op(
                    operations, "INSERT_COLUMN_CANDIDATE", "columns",
                    source={"after_column": raw_headers[-1], "logical_index": len(raw_headers)},
                    target=column, evidence=column["basis"],
                    reason="More target columns than verified source header candidates",
                    risk=["Physical column insertion and cell merges are not automatic"],
                )
                continue
            original = raw_headers[source_index]
            source_index += 1
            _op(
                operations, "KEEP_HEADER" if _canon(original["label"]) == _canon(column["label"])
                else "REPLACE_HEADER_CANDIDATE",
                "columns",
                source=original, target=column, evidence=column["basis"],
                reason="Candidate source column order; verify its treatment group and header geometry",
                risk=["Source population N, allocation and column-level footnotes may differ"],
            )
        for header in raw_headers[source_index:]:
            _op(
                operations, "REVIEW_SOURCE_ONLY_COLUMN", "columns", source=header,
                reason="Source column has no mapped target column",
                risk=["Do not remove merged source columns without structural review"],
            )

    # Row matching is label-based, not evidence of statistical equivalence.
    # Source statistics such as Mean/SD might occur below several parent rows;
    # never match these globally to an unrelated target variable.
    source_rows = [x for x in source["row_candidates"]
                   if not x["is_statistic_subrow"]]
    used = set()
    for row in target["rows"]:
        match = _candidate_pair(row["label"], source_rows, used)
        if match:
            idx, src_row, exact, score = match
            used.add(idx)
            _op(
                operations,
                "KEEP_ROW" if exact else "REVIEW_ROW_LABEL_REPLACEMENT",
                "rows", source=src_row,
                target={"label": row["label"], "kind": row["kind"],
                        "label_similarity": round(score, 4)},
                evidence=row["evidence"],
                reason=(
                    "Matching normalized label; keep structural row pending clinical review"
                    if exact else "Possible corresponding row; semantic equivalence unverified"
                ),
                status="verified_no_edit" if exact else "review_required",
                risk=[] if exact else ["A fuzzy label match must not be applied automatically"],
            )
        else:
            _op(
                operations, "INSERT_ROW_CANDIDATE", "rows",
                target={"label": row["label"], "kind": row["kind"]},
                evidence=row["evidence"],
                reason="Target-required row not matched to a source row label",
                risk=["Row hierarchy, correct insertion position and formula format unknown"],
            )
        if row["proposed_statistic_subrows"]:
            _op(
                operations, "ALIGN_STATISTIC_SUBROWS", "rows",
                target={"parent_label": row["label"],
                        "proposed_children": row["proposed_statistic_subrows"],
                        "status": row["subrow_status"]},
                evidence=evidence["statistics"],
                reason="Continuous-variable subrow hierarchy is suggested by target methods",
                risk=["Subrow placement and exact formatting are not confirmed by target SAP text"],
            )
        if row["subrow_status"] == "categories_not_extracted":
            _op(
                operations, "REVIEW_CATEGORY_LEVELS", "rows",
                target={"parent_label": row["label"], "levels": None},
                evidence=row["evidence"],
                reason="Target specification contains a categorical variable but not its categories",
                risk=["Do not borrow levels from another clinical study"],
            )

    for i, row in enumerate(source_rows):
        if i not in used:
            _op(
                operations, "REVIEW_SOURCE_ONLY_ROW", "rows", source=row,
                reason="Source row not mapped by target Specification; review for retention or removal",
                risk=["Step-2 omissions may make an important source row appear unnecessary"],
            )

    cell_format = target["cell_format_proposal"]
    if cell_format["suggested_shell_token"]:
        _op(
            operations, "REVIEW_CELL_FORMAT", "cells",
            source={"available_source_formats": source["placeholder_formats"]},
            target=cell_format, evidence=evidence["statistics"],
            reason="Target statistics suggest a display format, but precision is not verified",
            risk=["Event count vs patient count, precision and missing-value rules require review"],
        )

    # Source footnotes are NEVER carried over implicitly.  Missing target
    # footnotes are a search/review requirement, not authorization to delete.
    if not target["footnotes"]:
        _op(
            operations, "SEARCH_TARGET_FOOTNOTE_EVIDENCE", "footnotes",
            target={"footnotes": None},
            evidence=evidence["footnotes"],
            reason="Step-2 footnote_requirements is empty; inspect target SAP before editing",
            risk=["Empty extraction does not mean the target Table has no footnotes"],
        )
    for note in source["footnotes"]:
        _op(
            operations, "REVIEW_SOURCE_FOOTNOTE", "footnotes", source=note,
            target={"matched_target_footnote": None},
            evidence=evidence["footnotes"],
            reason="Source-study footnote cannot be automatically inherited",
            risk=["Source study population, denominator, methods or definitions may differ"],
        )
    for footnote in target["footnotes"]:
        _op(
            operations, "INSERT_TARGET_FOOTNOTE_CANDIDATE", "footnotes",
            target=footnote, evidence=footnote["basis"],
            reason="Target footnote is explicitly specified; map to an anchored Word paragraph",
            risk=["Footnote order, symbols and source note removal require review"],
        )

    if not target["denominator_rule"]:
        _op(
            operations, "SEARCH_TARGET_DENOMINATOR_EVIDENCE", "denominator",
            target={"rule": None}, evidence=evidence["denominator"],
            reason="No target Table-specific denominator rule extracted",
            risk=["Never inherit a source Study denominator merely from a similar table"],
        )
    else:
        _op(
            operations, "REVIEW_TARGET_DENOMINATOR", "denominator",
            target={"rule": target["denominator_rule"]},
            evidence=evidence["denominator"],
            reason="Review denominator consistency across headers, percent cells and footnotes",
        )

    if not source["tables"]:
        _op(
            operations, "REVIEW_NON_TABLE_DOCX_LAYOUT", "document",
            reason="The source DOCX contains no native Word table to edit",
            risk=["Reconstruction rather than table surgery may be required"],
        )
    for missing in target["unresolved_fields"]:
        _op(
            operations, "RESOLVE_TARGET_SPEC_GAP", "validation",
            target={"field": missing},
            evidence=evidence.get(missing) or {"ref_ids": []},
            reason="The target specification is incomplete; obtain target SAP evidence",
            risk=["Cannot certify planned source-to-target equivalence"],
        )

    counts = dict(Counter(x["action"] for x in operations))
    return {
        "schema_version": "adaptation-plan-1.0",
        "planning_status": "review_required",
        "execution_status": "not_executed",
        "executable_without_review": False,
        "clinical_approval": False,
        "target_tfl_id": target["identity"]["tfl_id"],
        "target_title": target["identity"]["title"],
        "source_template_id": source["template_id"],
        "source_study_id": candidate.get("source_study_id"),
        "retrieval": {
            "heuristic_score": candidate.get("score"),
            "cross_endpoint": bool(candidate.get("cross_endpoint")),
            "population_change_required": bool(candidate.get("population_change_required")),
            "not_a_probability": True,
        },
        "source_integrity": {
            "sha256": source["source_sha256"],
            "verified": source["boundary_verified"],
            "bookmark_occurrences_verified": source["verified_occurrence_count"],
            "missing_bookmarks": source["missing_verified_bookmarks"],
        },
        "source_ir": source,
        "target_layout_ir": target,
        "operations": operations,
        "summary": {
            "operation_count": len(operations),
            "by_action": counts,
            "source_word_table_count": source["table_count"],
            "source_candidate_rows": len(source["row_candidates"]),
            "target_rows": len(target["rows"]),
            "target_columns": len(target["columns"]),
            "source_footnotes": len(source["footnotes"]),
            "target_footnotes": len(target["footnotes"]),
            "target_unresolved_fields": target["unresolved_fields"],
            "source_warnings": source["warnings"],
        },
        "human_review_checklist": [
            "Confirm target/source endpoint and analysis population",
            "Verify each treatment column and its N denominator",
            "Inspect every row and candidate statistical subrow/visit hierarchy",
            "Confirm target cell-display precision and event/count semantics",
            "Retrieve target-SAP evidence for all footnotes and denominator rules",
            "Confirm Word grid merges, continuation pages and document styling",
        ],
        "next_step": (
            "Review/approve operation mappings before an OOXML DOCX executor; "
            "this JSON does not authorize structural edits"
        ),
    }
