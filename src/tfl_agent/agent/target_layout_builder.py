"""Target Layout IR from a *previously extracted* Table Specification.

This is planning structure, not clinical data.  Never infer concrete patient
categories, visits, values or footnotes from a source study.  Missing target
details are kept as explicit unresolved requirements.
"""
from __future__ import annotations

import re


def _unique(items):
    return list(dict.fromkeys(
        str(value).strip() for value in (items or [])
        if str(value).strip()
    ))


def _kind_for(label):
    key = str(label).strip().casefold()
    continuous = ("age", "height", "weight", "bmi", "body mass index",
                  "duration", "time from", "blood pressure", "heart rate")
    categorical = ("race", "gender", "sex", "menopausal", "ecog",
                   "smoking", "ethnicity", "childbearing potential")
    if key in ("n", "mean", "sd", "median", "min", "max", "min, max"):
        return "statistic"
    if any(word in key for word in categorical):
        return "categorical_candidate"
    if any(word in key for word in continuous):
        return "continuous_candidate"
    if "teae" in key or "adverse event" in key or "ae" == key:
        return "event_category"
    return "unspecified"


def _display_stats(statistics):
    terms = " ".join(statistics).casefold()
    output = []
    for term, pattern in [
        ("n", r"(?<!\w)n(?!\w)|number of patients|frequenc"),
        ("Mean", r"\bmean\b"),
        ("SD", r"standard deviation|\bsd\b"),
        ("Median", r"\bmedian\b"),
        ("Min", r"\bminimum\b|\bmin\b"),
        ("Max", r"\bmaximum\b|\bmax\b"),
    ]:
        if re.search(pattern, terms):
            output.append(term)
    return output


def _normalize_arm(text):
    # Normalize presentation-only group numbering without changing dose names.
    text = re.sub(r"^Group\s*\d+\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s*\(Group\s*\d+\)\s*$", "", text, flags=re.I)
    return text.strip()


def _field_evidence(spec, pointer):
    """Record link presence; do not pretend that an existing ID proves a quote.

    Target-SAP source-block verification is a separate validator.  Empty
    ref_ids is 'missing', NOT all_refs_present=True evidence of support.
    """
    prov = spec.get("provenance") or {}
    available = {x.get("ref_id"): x for x in prov.get("evidence", [])}
    refs = []
    for link in prov.get("field_links", []):
        path = link.get("json_pointer") or ""
        if path == pointer or path.startswith(pointer + "/"):
            refs.extend(link.get("ref_ids") or [])
    refs = list(dict.fromkeys(refs))
    resolved = [available[r] for r in refs if r in available]
    if not refs:
        status = "missing"
    elif len(resolved) != len(refs):
        status = "invalid"
    else:
        status = "linked_unverified"  # validate against parsed SAP blocks later
    return {
        "json_pointer": pointer,
        "ref_ids": refs,
        "all_refs_present": bool(refs) and len(resolved) == len(refs),
        "supported_excerpt_count": len(resolved),
        "evidence_status": status,
        "quote_previews": [
            str(item.get("exact_text") or item.get("quote") or "")[:220]
            for item in resolved[:4]
        ],
        "claim_scope": "Field-level links only; semantic row equivalence not verified",
    }


def _explicit_children(label):
    """Only expand categories literally named in the target row requirement."""
    text = str(label or "")
    m = re.search(
        r"(?:categories|best overall response)[^:]*:\s*((?:CR|PR|SD|PD)"
        r"(?:\s*[,/]\s*(?:CR|PR|SD|PD))*)",
        text, flags=re.I,
    )
    if not m:
        return []
    dictionary = {
        "CR": "Complete Response (CR)",
        "PR": "Partial Response (PR)",
        "SD": "Stable Disease (SD)",
        "PD": "Progressive Disease (PD)",
    }
    abbreviations = re.findall(r"\b(?:CR|PR|SD|PD)\b", m.group(1), re.I)
    return [{
        "label": dictionary[a.upper()],
        "abbreviation": a.upper(),
        "origin": "explicit_target_spec_text",
        "status": "requires_target_SAP_quote_verification",
    } for a in abbreviations]


def build_target_layout(spec):
    """Return an evidence-indexed, JSON-serializable layout specification.

    Inferred subrows and cell display tokens are *proposals*, not sourced
    literal target-SAP shell geometry.
    """
    identity = spec.get("identity") or {}
    if identity.get("output_type") != "table":
        raise ValueError("Target Layout IR currently supports Table specifications only")
    if not identity.get("tfl_id") or not identity.get("title"):
        raise ValueError("Target TFL ID and title are required")
    stats = spec.get("statistical_requirements") or {}
    table = spec.get("table_requirements") or {}
    row_labels = _unique(table.get("row_requirements"))
    groups = _unique(stats.get("treatment_groups"))
    raw_columns = _unique(table.get("column_requirements"))
    columns = []
    for group in groups:
        name = _normalize_arm(group)
        if name.casefold() not in {x["label"].casefold() for x in columns}:
            columns.append({
                "label": name,
                "kind": "treatment_group",
                "basis": _field_evidence(spec, "/statistical_requirements/treatment_groups"),
                "origin": "target_spec",
            })
    for label in raw_columns:
        if label.casefold() == "overall":
            if "overall" not in {x["label"].casefold() for x in columns}:
                columns.append({
                    "label": "Overall", "kind": "overall",
                    "basis": _field_evidence(spec, "/table_requirements/column_requirements"),
                    "origin": "target_spec",
                })
            continue
        if "treatment group" in label.casefold() and columns:
            continue
        normal = _normalize_arm(label)
        if normal.casefold() not in {x["label"].casefold() for x in columns}:
            columns.append({
                "label": normal, "kind": "other",
                "basis": _field_evidence(spec, "/table_requirements/column_requirements"),
                "origin": "target_spec",
            })
    if not groups and not raw_columns:
        columns = []

    all_stats = _unique(stats.get("statistics_to_display"))
    suggested_subrows = _display_stats(all_stats)
    methods = _unique(stats.get("analysis_methods"))
    rows = []
    for label in row_labels:
        kind = _kind_for(label)
        # These are target-layout *proposals*, never claims that the SAP
        # explicitly specified the corresponding hierarchy.  A human or a
        # later evidence-retrieval step must confirm subrows/category levels.
        subrows = suggested_subrows if kind == "continuous_candidate" else []
        rows.append({
            "label": label,
            "kind": kind,
            "origin": "target_spec",
            "source_pointer": "/table_requirements/row_requirements",
            "evidence": _field_evidence(spec, "/table_requirements/row_requirements"),
            "proposed_statistic_subrows": subrows,
            "explicit_category_children": _explicit_children(label),
            "subrow_status": (
                "inferred_requires_review" if subrows else
                "categories_not_extracted" if kind == "categorical_candidate"
                else "not_specified"
            ),
        })
    notes = _unique(table.get("footnote_requirements"))
    footnotes = [{
        "text": note, "origin": "target_spec",
        "basis": _field_evidence(spec, "/table_requirements/footnote_requirements"),
    } for note in notes]
    stat_str = " ".join(all_stats).lower()
    if ("number of events" in stat_str and
            ("percentage" in stat_str or "%" in stat_str)):
        cell_format = {
            "display_components": ["n", "percent", "event_count"],
            "suggested_shell_token": "xx (xx.x), xx",
            "status": "inferred_requires_review",
            "note": "Target spec supports components, not literal decimal precision",
        }
    elif any(x in stat_str for x in ("frequency", "percentage", "percent")):
        cell_format = {
            "display_components": ["n", "percent"],
            "suggested_shell_token": "xx (xx.x)",
            "status": "inferred_requires_review",
            "note": "Exact precision and denominator require target support",
        }
    else:
        cell_format = {
            "display_components": all_stats,
            "suggested_shell_token": None,
            "status": "unresolved",
            "note": "Cannot derive a single cell format from the target specification",
        }

    # Denominator rules matter for percentages, not for every continuous-only
    # table.  n and N alone do not establish a percentage denominator.
    display_text = " ".join(all_stats + methods + row_labels).casefold()
    denominator_applicability = (
        "unknown" if not all_stats and not methods else
        "required" if any(token in display_text for token in (
            "percentage", "percent", "n (%)", "n(%)", "%", "frequency", "frequencies"
        )) else "not_applicable_for_current_spec"
    )
    unresolved = []
    if not rows:
        unresolved.append("row_requirements")
    if not columns:
        unresolved.append("column_requirements")
    if not notes:
        unresolved.append("footnote_requirements")
    if not table.get("denominator_rule") and denominator_applicability == "required":
        unresolved.append("denominator_rule")
    if not all_stats:
        unresolved.append("statistics_to_display")

    return {
        "ir_version": "target-layout-ir-2.0",
        "identity": identity,
        "readiness": spec.get("readiness"),
        "rows": rows,
        "columns": columns,
        "statistics_to_display": all_stats,
        "methods": methods,
        "analysis_population": _unique(stats.get("analysis_population")),
        "endpoint": stats.get("endpoint_name"),
        "visits_or_timepoints": _unique(stats.get("visits_or_timepoints")),
        "cell_format_proposal": cell_format,
        "footnotes": footnotes,
        "denominator_rule": table.get("denominator_rule"),
        "denominator_applicability": denominator_applicability,
        "evidence_by_field": {
            name: _field_evidence(spec, pointer)
            for name, pointer in {
                "title": "/identity/title",
                "rows": "/table_requirements/row_requirements",
                "columns": "/table_requirements/column_requirements",
                "footnotes": "/table_requirements/footnote_requirements",
                "denominator": "/table_requirements/denominator_rule",
                "statistics": "/statistical_requirements/statistics_to_display",
                "methods": "/statistical_requirements/analysis_methods",
                "population": "/statistical_requirements/analysis_population",
                "treatment_groups": "/statistical_requirements/treatment_groups",
                "endpoint": "/statistical_requirements/endpoint_name",
            }.items()
        },
        "unresolved_fields": unresolved,
        "spec_issues": spec.get("issues") or [],
        "rules": {
            "categories_not_invented": True,
            "visits_not_invented": True,
            "footnotes_not_borrowed_from_source": True,
            "subrow_hierarchy_requires_review": True,
        },
    }
