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
from tfl_agent.agent.structure_alignment import align_target_rows, classify_layout_compatibility


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
    compatibility = classify_layout_compatibility(source, target)
    row_alignment = align_target_rows(source, target)
    title_source = (source.get("title_mapping") or {}).get("anchor")
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

    if title_source is None:
        _op(
            operations, "REVIEW_TITLE_ANCHOR", "title",
            target={"text": target["identity"]["title"]}, evidence=evidence["title"],
            reason="No source bookmark safely identified as a Table title",
            risk=["Sponsor name must not be replaced as a Table title"],
        )
    else:
        # The initially proposed title replacement remains review-gated even
        # when a real Table marker is found.
        operations[0]["source"] = {
            **title_source,
            "anchor_status": source["title_mapping"]["status"],
            "continuation_candidates": source["title_mapping"]["continuation_candidates"],
        }

    if compatibility["mode"] in (
        "blocked_target_incomplete", "rebuild_with_source_style",
        "layout_review_before_edit",
    ):
        _op(
            operations, "REVIEW_LAYOUT_COMPATIBILITY", "document",
            source={"layout_profile": source.get("layout_profile")},
            target={"adaptation_mode": compatibility["mode"]},
            reason="Source/target Word axes or extraction gaps prevent automatic structural edits",
            risk=compatibility["blockers"] + compatibility["risks"],
        )

    # Column suggestions always preserve their *physical* Word grid index.
    # Header ordinal or candidate count MUST NOT become an insertion index.
    headers = [
        h for h in source["column_candidates"]
        if (h.get("position") or {}).get("location_type") == "table_cell"
    ]
    if headers:
        # Treat panel 1 as the master source column layout. Other panels
        # must be updated consistently by a future executor.
        primary_index = min(h["position"]["table_index"] for h in headers)
        primary_headers = [
            h for h in headers if h["position"]["table_index"] == primary_index
        ]
        primary_headers.sort(key=lambda h: h["position"]["column_index"])
    else:
        primary_headers = []
    target_cols = target["columns"]
    if compatibility["source_axis"] == "cohort_rows_statistic_columns":
        _op(
            operations, "REVIEW_COLUMN_AXIS_TRANSFORMATION", "columns",
            source={"axis": compatibility["source_axis"],
                    "physical_headers": compatibility["source_header_coordinates"]},
            target={"treatment_columns": [c["label"] for c in target_cols]},
            evidence=evidence["columns"],
            reason="Target columns and vertically listed source cohorts use different axes",
            risk=["Cannot map source column header ordinals to target treatment columns"],
        )
    elif compatibility["mode"] in ("blocked_target_incomplete", "rebuild_with_source_style"):
        _op(
            operations, "REBUILD_COLUMN_LAYOUT_CANDIDATE", "columns",
            source={"headers": primary_headers, "source_table_count": source["table_count"]},
            target={"columns": target_cols},
            evidence=evidence["columns"],
            reason="Column count/target extraction requires panel-aware rebuilding, not direct column surgery",
            risk=["Source page continuation, merged cells, repeated headers and population N must be checked"],
        )
    elif not primary_headers:
        _op(
            operations, "REVIEW_COLUMN_GEOMETRY", "columns",
            target={"labels": [c["label"] for c in target_cols]},
            evidence=evidence["columns"],
            reason="No reliable Word header cell candidates",
            risk=["Column insertion positions are unverified"],
        )
    else:
        source_cursor = 0
        for target_index, col in enumerate(target_cols):
            existing_overall = next(
                (h for h in primary_headers if
                 ("overall" in h["label"].casefold() or
                  re.search(r"\btotal\b", h["label"], flags=re.I))),
                None,
            )
            if col["kind"] == "overall" and existing_overall is None:
                after = primary_headers[-1]
                _op(
                    operations, "INSERT_COLUMN_CANDIDATE", "columns",
                    source={
                        "after_column": after,
                        "insert_after_physical_grid_index":
                            after["position"]["column_index"],
                        "insertion_physical_grid_index":
                            after["position"]["column_index"] + 1,
                        "table_index": after["position"]["table_index"],
                        "target_column_index": target_index,
                        "multi_panel_review_required": source["table_count"] > 1,
                    },
                    target=col, evidence=col["basis"],
                    reason="Target explicitly requires Overall; no Overall source treatment header",
                    risk=["Check header grid spans, inserted cells and denominator rules"],
                )
                continue
            if source_cursor >= len(primary_headers):
                after = primary_headers[-1]
                _op(
                    operations, "INSERT_COLUMN_CANDIDATE", "columns",
                    source={
                        "after_column": after,
                        "insert_after_physical_grid_index": after["position"]["column_index"],
                        "insertion_physical_grid_index": after["position"]["column_index"] + 1,
                        "table_index": after["position"]["table_index"],
                        "target_column_index": target_index,
                        "multi_panel_review_required": source["table_count"] > 1,
                    },
                    target=col, evidence=col["basis"],
                    reason="More target columns than source treatment headings",
                    risk=["Cell merges and physical grid must be reviewed before insertion"],
                )
                continue
            original = (
                existing_overall if col["kind"] == "overall" and existing_overall
                else primary_headers[source_cursor]
            )
            if original is primary_headers[source_cursor]:
                source_cursor += 1
            _op(
                operations,
                "KEEP_HEADER" if _canon(original["label"]) == _canon(col["label"])
                else "REPLACE_HEADER_CANDIDATE",
                "columns", source=original, target=col, evidence=col["basis"],
                reason="Candidate treatment column mapping from Word physical grid coordinates",
                risk=["Dose/arm meaning, target N, and merged cells need review"],
            )
        if source_cursor < len(primary_headers):
            remaining = primary_headers[source_cursor:]
            _op(
                operations, "REVIEW_SOURCE_ONLY_COLUMNS", "columns",
                source={"headers": remaining, "count": len(remaining)},
                reason="Some source treatment-group columns have no target mapping",
                risk=["Do not delete physical columns or merge geometry automatically"],
            )

    # Match hierarchical rows, including category children literally listed
    # in target specifications. Normalized or clinical-alias matches are
    # *proposals*, not permissions to edit source clinical content.
    for match in row_alignment["matches"]:
        tr = match["target"]
        evidence_for_row = evidence["rows"]
        relation = match["relation"]
        if relation == "aggregation_candidate":
            _op(
                operations, "AGGREGATE_CATEGORIES_CANDIDATE", "rows",
                source=match["source"], target=tr, evidence=evidence_for_row,
                reason=match["reason"],
                risk=["Never sum category patient counts; patient-level statistics required"],
            )
            continue
        if relation == "unmatched":
            action = "INSERT_ROW_CANDIDATE"
        elif relation == "lexical_normalized":
            action = "KEEP_ROW"
        else:
            action = "REVIEW_SEMANTIC_ROW_MATCH"
        _op(
            operations, action, "rows", source=match["source"],
            target={**tr, "semantic_relation": relation,
                    "label_similarity": match["label_similarity"]},
            evidence=evidence_for_row,
            reason=match["reason"],
            risk=["Target SAP must establish clinical/statistical equivalence"]
            if match["source"] else
            ["Target row hierarchy and physical insertion position are unverified"],
        )

    for row in target["rows"]:
        if row["proposed_statistic_subrows"]:
            _op(
                operations, "ALIGN_STATISTIC_SUBROWS", "rows",
                target={"parent_label": row["label"],
                        "proposed_children": row["proposed_statistic_subrows"],
                        "status": row["subrow_status"]},
                evidence=evidence["statistics"],
                reason="Review proposed descriptive-statistic child hierarchy",
                risk=["Exact parent-child semantics not verified by target shell"],
            )
        if row["subrow_status"] == "categories_not_extracted":
            _op(
                operations, "REVIEW_CATEGORY_LEVELS", "rows",
                target={"parent_label": row["label"], "levels": None},
                evidence=row["evidence"],
                reason="Target categories were not fully extracted; do not borrow source-study levels",
            )

    unmatched_rows = row_alignment["unmatched_source_rows"]
    if not target["rows"] and unmatched_rows:
        _op(
            operations, "REVIEW_SOURCE_ROWS_TARGET_INCOMPLETE", "rows",
            source={
                "unmatched_count": len(unmatched_rows),
                "sample_labels": [r["label"] for r in unmatched_rows[:12]],
            },
            reason="Target row requirements are empty; source cannot be treated as extraneous",
            risk=["Complete target row extraction before editing"],
        )
    else:
        for row in unmatched_rows[:12]:
            _op(
                operations, "REVIEW_SOURCE_ONLY_ROW", "rows", source=row,
                reason="Source row has no mapped target requirement; review rather than delete",
                risk=["Step-2 omissions may make source content appear unnecessary"],
            )
        if len(unmatched_rows) > 12:
            _op(
                operations, "REVIEW_ADDITIONAL_SOURCE_ROWS", "rows",
                source={
                    "additional_unmatched_count": len(unmatched_rows)-12,
                    "see_full_list": "row_alignment.unmatched_source_rows",
                },
                reason="Remaining source rows require review",
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
    for note in source.get("footnote_groups", []):
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

    if (not target["denominator_rule"] and
            target.get("denominator_applicability") == "required"):
        _op(
            operations, "SEARCH_TARGET_DENOMINATOR_EVIDENCE", "denominator",
            target={"rule": None}, evidence=evidence["denominator"],
            reason="No target Table-specific denominator rule extracted",
            risk=["Never inherit a source Study denominator merely from a similar table"],
        )
    elif target["denominator_rule"]:
        _op(
            operations, "REVIEW_TARGET_DENOMINATOR", "denominator",
            target={"rule": target["denominator_rule"]},
            evidence=evidence["denominator"],
            reason="Review denominator consistency across headers, percent cells and footnotes",
        )
    elif target.get("denominator_applicability") == "unknown":
        _op(
            operations, "REVIEW_DENOMINATOR_APPLICABILITY", "denominator",
            target={"rule": None, "applicability": "unknown"},
            evidence=evidence["statistics"],
            reason="Target statistics are absent; cannot determine whether a percentage denominator is needed",
            risk=["Do not claim denominator is irrelevant until the target statistical layout is recovered"],
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
    # Absence of evidence is never interpreted as a validated quotation.
    evidence_issues = [
        {"field": field, "status": rec.get("evidence_status"),
         "ref_ids": rec.get("ref_ids", [])}
        for field, rec in evidence.items()
        if rec.get("evidence_status") in ("missing", "invalid")
    ]
    return {
        "schema_version": "adaptation-plan-2.0",
        "adaptation_mode": compatibility["mode"],
        "layout_compatibility": compatibility,
        "row_alignment": row_alignment,
        "evidence_validation": {
            "status": "review_required",
            "missing_or_invalid_fields": evidence_issues,
            "source_quote_verification_performed": False,
        },
        "executor_ready": False,
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
            "unique_source_footnotes": len(source.get("footnote_groups", [])),
            "row_matching": row_alignment["counts_by_relation"],
            "layout_mode": compatibility["mode"],
            "evidence_gaps": len(evidence_issues),
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
