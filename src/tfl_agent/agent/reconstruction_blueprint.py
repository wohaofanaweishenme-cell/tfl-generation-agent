"""Build a new target-table blueprint using approved Source IR and target SAP Specification.

Source content is ONLY structural evidence. Never copy source-study categories,
treatment names, patient values, denominator rules, or clinical footnotes.
"""
from __future__ import annotations

from collections import Counter

from tfl_agent.agent.target_layout_builder import build_target_layout


def _family(title):
    s = str(title or "").casefold()
    if "adverse event" in s or "teae" in s:
        return "adverse_events"
    if "demograph" in s or "baseline characteristic" in s:
        return "demographics"
    if "disposition" in s or "withdrawal" in s:
        return "disposition"
    if "survival" in s or "progression-free" in s or "pfs" in s:
        return "time_to_event"
    return "general_table"


def _source_structure(plan):
    """Use verified source geometry only when the diagnostic Plan is compatible."""
    if not plan or not plan.get("source_integrity", {}).get("verified"):
        return None
    if plan.get("retrieval", {}).get("cross_endpoint"):
        return None
    # Axis-incompatible plans may still guide *style* in a future renderer,
    # but must not lend a row hierarchy to the target Blueprint.
    if plan.get("adaptation_mode") not in (
        "structural_edit_candidate", "text_or_structural_edit_candidate",
    ):
        return None
    source = plan.get("source_ir") or {}
    if not source.get("boundary_verified"):
        return None
    if not source.get("tables"):
        return None
    return source


def _unique(items):
    return list(dict.fromkeys(str(x).strip() for x in (items or []) if str(x).strip()))


def build_reconstruction_blueprint(spec: dict, *, adaptation_plan: dict | None = None) -> dict:
    """Return an auditable, JSON-serializable layout used DIRECTLY by the DOCX builder.

    Plan/Source IR may influence hierarchy and presentation, not clinical content.
    Target rows, columns, arms, statistics and notes come solely from spec.
    The output is a non-approved structural proposal, not clinical verification.
    """
    target = ((adaptation_plan or {}).get("target_layout_ir")
              or build_target_layout(spec))
    if target["identity"].get("output_type") != "table":
        raise ValueError("Only Table reconstruction is implemented")
    identity = target["identity"]
    if not identity.get("title") or not identity.get("tfl_id"):
        raise ValueError("Target TFL ID/title are required")
    columns = target.get("columns") or []
    if not columns:
        raise ValueError("Target has no verified column requirements")
    target_rows = target.get("rows") or []
    if not target_rows:
        raise ValueError("Target has no row requirements; refusing to invent rows")
    if len(columns) > 16 or len(target_rows) > 150:
        raise ValueError("Target table exceeds the current reconstruction safety limits")

    source = _source_structure(adaptation_plan)
    source_kinds = Counter(
        item.get("row_type") for item in (source or {}).get("hierarchical_rows", [])
    )
    source_pattern = {
        "source_template_id": (adaptation_plan or {}).get("source_template_id"),
        "source_sha256": ((adaptation_plan or {}).get("source_integrity") or {}).get("sha256"),
        "verified_source_ir_used": source is not None,
        "axis_orientation": ((source or {}).get("layout_profile") or {}).get(
            "axis_orientation", "none"
        ),
        "source_word_tables": len((source or {}).get("tables") or []),
        "statistic_subrow_pattern": bool(source_kinds["statistic_subrow"]),
        "category_subrow_pattern": bool(source_kinds["category_subrow"]),
        "source_header_positions": [
            {"table_index": h.get("table_index"),
             "physical_grid_index": h.get("physical_grid_index")}
            for h in (source or {}).get("column_candidates", [])
            if h.get("physical_grid_index") is not None
        ],
        "clinical_source_content_reused": False,
    }
    family = _family(identity["title"])
    stats = _unique(target.get("statistics_to_display"))
    stat_text = " ".join(stats).lower()
    event_count = ("number of events" in stat_text or "event count" in stat_text)
    percent = ("percentage" in stat_text or "percent" in stat_text or "%" in stat_text)
    ae_dual_header = family == "adverse_events" and event_count and percent
    header_rows = 2 if ae_dual_header else 1

    # Word rows are derived exclusively from the target. Source geometry decides
    # whether target-specified descriptive statistics are shown as child rows.
    rows = []
    reuse_stat_hierarchy = bool(source and source_pattern["statistic_subrow_pattern"])
    for target_row in target_rows:
        label = str(target_row.get("label") or "").strip()
        if not label:
            continue
        kind = target_row.get("kind") or "unspecified"
        placeholder = (
            "xx (xx.x%)  |  xx" if ae_dual_header
            else "xx (xx.x%)" if percent and kind != "continuous_candidate"
            else "xx"
        )
        rows.append({
            "label": label, "depth": 0, "kind": kind,
            "placeholder": placeholder, "origin": "target_spec",
            "source_pointer": target_row.get("source_pointer"),
        })
        for child in target_row.get("explicit_category_children") or []:
            child_label = str(child.get("label") or "").strip()
            if child_label:
                rows.append({
                    "label": child_label, "depth": 1, "kind": "explicit_category",
                    "placeholder": placeholder,
                    "origin": "explicit_target_spec_text",
                    "requires_review": True,
                })
        if kind == "continuous_candidate" and reuse_stat_hierarchy:
            for statistic in _unique(target_row.get("proposed_statistic_subrows")):
                rows.append({
                    "label": statistic, "depth": 1, "kind": "statistic_subrow",
                    "placeholder": "xx",
                    "origin": "target_statistics_with_source_hierarchy_pattern",
                    "requires_review": True,
                })

    if not rows or len(rows) > 300:
        raise ValueError("No usable target rows or too many expanded rows")
    notes = [str(x["text"]) for x in target.get("footnotes") or []
             if isinstance(x, dict) and str(x.get("text") or "").strip()]
    unresolved = _unique(target.get("unresolved_fields"))
    if adaptation_plan:
        unresolved = _unique(unresolved + list(
            (adaptation_plan.get("planning_gate") or {}).get("hard_blockers") or []
        ))
    review_flags = [
        "Target Specification is not clinical approval",
        "Statistics, denominator and display precision require independent review",
        "Source hierarchy is a presentation pattern, never proof of clinical equivalence",
    ]
    if not source:
        review_flags.append("No compatible verified Source IR: target-only fallback structure")
    if any(r.get("requires_review") for r in rows):
        review_flags.append("Expanded child rows are structural proposals")
    return {
        "blueprint_version": "table-reconstruction-1.0",
        "identity": {"tfl_id": identity["tfl_id"], "title": identity["title"],
                     "output_type": "table"},
        "family": family,
        "population": _unique(target.get("analysis_population")),
        "columns": [{"label": str(c["label"]), "kind": c.get("kind", "other")}
                    for c in columns],
        "row_label_header": (
            "Adverse Event Category" if family == "adverse_events"
            else "Parameter / Row"
        ),
        "header_rows": header_rows,
        "header_statistic_text": "n (%)  |  Events" if ae_dual_header else None,
        "rows": rows,
        "footnotes": notes,
        "statistics_to_display": stats,
        "denominator_rule": target.get("denominator_rule"),
        "source_structure": source_pattern,
        "adaptation_mode": (adaptation_plan or {}).get("adaptation_mode",
                                                      "target_only_rebuild"),
        "unresolved_requirements": unresolved,
        "review_flags": review_flags,
        "source_content_copied": False,
        "clinical_approval": False,
    }
