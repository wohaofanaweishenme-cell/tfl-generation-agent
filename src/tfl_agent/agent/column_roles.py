"""Role-aware mapping of physical Word grid columns to target Table columns.

Role classification is deliberately conservative.  Source 'Total' is an
Overall candidate, NEVER a source treatment arm, and cannot be renamed to a
treatment group by ordinal matching.  The returned positions identify grid
coordinates for review, not executable OOXML commands.
"""
from __future__ import annotations

import re


def source_column_role(label):
    text = str(label or "").casefold().strip()
    if re.search(r"\b(overall|total|all patients|pooled)\b", text):
        return "overall"
    if re.search(r"\b(?:actual values?|change from baseline|statistic|mean|median|sd)\b", text):
        return "statistic_or_measurement"
    if re.search(r"\bcohort\s*(?:\d+|i|ii|iii)\b", text):
        return "cohort_axis"
    if re.search(r"\b(?:arm\s*(?:i|ii|iii|iv|\d+)|treatment|dose|\d+(?:\.\d+)?\s*mg|n\s*=\s*\w+)\b", text):
        return "treatment_arm_candidate"
    return "unknown"


def _physical(ref):
    pos = (ref or {}).get("position") or {}
    return {
        "table_index": pos.get("table_index"),
        "row_index": pos.get("row_index"),
        "physical_grid_index": pos.get("column_index"),
        "location_type": pos.get("location_type"),
        "grid_span": (ref or {}).get("grid_span", 1),
        "vertical_merge": (ref or {}).get("vertical_merge"),
    }


def map_column_roles(source, target, compatibility, *, completeness=None):
    """Return column alignment with candidate operations and panel warnings."""
    headers = [
        h for h in source.get("column_candidates") or []
        if (h.get("position") or {}).get("location_type") == "table_cell"
    ]
    for h in headers:
        h.setdefault("role", source_column_role(h.get("label")))
    if headers:
        main_table = min(h["position"]["table_index"] for h in headers)
        primary = sorted(
            [h for h in headers if h["position"]["table_index"] == main_table],
            key=lambda h: (h["position"]["column_index"], h["position"]["row_index"]),
        )
    else:
        main_table = None
        primary = []
    typed = [
        {"header": h, "role": source_column_role(h["label"]),
         "coordinate": _physical(h)} for h in primary
    ]
    targets = target.get("columns") or []
    matches, actions = [], []
    used = set()
    block = bool(completeness and completeness.get("status") == "blocked")
    axis = compatibility.get("source_axis")
    mode = compatibility.get("mode")
    risks = ["Word gridSpan/vMerge, panel continuity, denominator and source-group meaning require review"]

    def emit(action, *, source=None, target=None, reason="", risk=None):
        actions.append({
            "action": action, "source": source, "target": target,
            "reason": reason, "risk": risk if risk is not None else risks,
        })

    if axis == "cohort_rows_statistic_columns":
        emit(
            "REVIEW_COLUMN_AXIS_TRANSFORMATION",
            source={"source_axis": axis, "source_headers": typed},
            target={"columns": targets},
            reason="Source cohort/statistic axes are not target horizontal treatment columns",
        )
        return {
            "source_columns": typed, "target_matches": [],
            "proposed_operations": actions, "status": "axis_mismatch",
            "physical_positions_independent_of_target_order": True,
            "source_panel_count": source.get("table_count", 0),
        }

    if mode in ("rebuild_with_source_style", "blocked_target_incomplete", "layout_review_before_edit") and not block:
        emit(
            "REBUILD_COLUMN_LAYOUT_CANDIDATE" if mode == "rebuild_with_source_style"
            else "REVIEW_COLUMN_GEOMETRY",
            source={"headers": typed, "source_table_count": source.get("table_count")},
            target={"columns": targets},
            reason="Incompatible or unclassified source/target Word column geometry",
        )
        return {
            "source_columns": typed, "target_matches": [],
            "proposed_operations": actions, "status": "review_required",
            "physical_positions_independent_of_target_order": True,
            "source_panel_count": source.get("table_count", 0),
        }

    for target_index, target_column in enumerate(targets):
        desired = target_column.get("kind")
        expected = "overall" if desired == "overall" else "treatment_arm_candidate" if desired == "treatment_group" else None
        choices = [
            (i, h) for i, h in enumerate(typed) if i not in used
            and (h["role"] == expected if expected is not None else False)
        ]
        if choices:
            i, mapped = choices[0]
            used.add(i)
            match = {
                "target_column_index": target_index, "target": target_column,
                "source_header": mapped["header"],
                "source_role": mapped["role"], "target_role": desired,
                "source_physical_grid": mapped["coordinate"],
                "status": "candidate_requires_review",
            }
            matches.append(match)
            name_same = str(mapped["header"]["label"]).strip().casefold() == str(target_column["label"]).strip().casefold()
            if desired == "overall":
                action = "KEEP_HEADER" if name_same else "REVIEW_OVERALL_ALIAS"
                reason = "Source Overall/Total maps only to target Overall, never a treatment arm"
            else:
                action = "KEEP_HEADER" if name_same else "REPLACE_HEADER_CANDIDATE"
                reason = "Source and target treatment-arm *roles* match; drug/dose semantics unverified"
            emit(action, source=mapped["header"], target={
                **target_column, "target_column_index": target_index,
            }, reason=reason)
            continue

        # Missing overall with verified treatment-arm physical columns:
        if desired == "overall":
            treatment = [h for h in typed if h["role"] == "treatment_arm_candidate"]
            if treatment and not block and mode == "structural_edit_candidate":
                after = max(treatment, key=lambda x: x["coordinate"]["physical_grid_index"])
                pos = after["coordinate"]
                emit("INSERT_COLUMN_CANDIDATE", source={
                    "after_column": after["header"],
                    "table_index": pos["table_index"],
                    "insert_after_physical_grid_index": pos["physical_grid_index"],
                    "insertion_physical_grid_index": pos["physical_grid_index"] + 1,
                    "target_column_index": target_index,
                    "multi_panel_review_required": source.get("table_count", 0) > 1,
                }, target=target_column,
                reason="No source Overall column; append after physical treatment-arm grid position")
            else:
                emit("REVIEW_MISSING_OVERALL_COLUMN", source={"existing_headers": typed},
                     target=target_column, reason="Overall column not located; safe insertion point unknown")
        elif desired == "treatment_group":
            emit(
                "REVIEW_MISSING_TREATMENT_GROUP_COLUMN",
                source={"existing_headers": typed, "target_column_index": target_index},
                target=target_column,
                reason="No remaining source treatment-arm column; Total/Overall cannot substitute for an arm",
            )
        else:
            emit("REVIEW_UNCLASSIFIED_TARGET_COLUMN", target=target_column,
                 reason="Target column role must be determined before mapping")

    for i, item in enumerate(typed):
        if i not in used:
            emit("REVIEW_SOURCE_ONLY_COLUMN", source=item,
                 reason="Source header has no role-compatible target match")
    if block:
        emit(
            "BLOCKED_TARGET_COLUMN_OPERATIONS",
            source={"source_role_counts": {
                role: sum(x["role"] == role for x in typed)
                for role in sorted({x["role"] for x in typed})
            }},
            reason="Readiness or minimum requirements block all physical column edits",
        )
    return {
        "source_columns": typed, "target_matches": matches,
        "proposed_operations": actions,
        "status": "blocked" if block else "review_required",
        "physical_positions_independent_of_target_order": True,
        "source_panel_count": source.get("table_count", 0),
    }
