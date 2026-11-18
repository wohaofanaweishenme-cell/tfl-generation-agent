"""Table layout compatibility and conservative source-to-target row alignment.

This stage builds inspectable *candidates*.  It never establishes clinical
equivalence or generates executable Word coordinates from a label score.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from collections import Counter
import re


def normalize_row_label(label):
    """Normalize presentation variation, not clinical definitions."""
    s = str(label or "").casefold()
    s = s.replace("≥", ">=").replace("–", "-")
    s = re.sub(r"\btreatment[\s-]*emergent adverse events?\b", "teae", s)
    s = re.sub(r"\bteaes\b", "teae", s)
    s = re.sub(r"\badverse events?\b", "ae", s)
    s = re.sub(r"\bprogressive disease\b", "pd", s)
    s = re.sub(r"\bcomplete response\b", "cr", s)
    s = re.sub(r"\bpartial response\b", "pr", s)
    s = re.sub(r"\bstable disease\b", "sd", s)
    s = re.sub(r"\bany\b", "", s)
    s = re.sub(r"\b(?:years?|kg|cm)\b", "", s)
    s = re.sub(r"\[[a-z]\]", "", s)  # source-only footnote superscripts
    s = re.sub(r"\s*\((cr|pr|sd|pd|teae)\)", "", s)
    s = re.sub(r"[^a-z0-9><=]+", " ", s)
    return " ".join(s.split())


def _protected_concepts(label):
    s = normalize_row_label(label)
    parts = set(s.split())
    return {
        x for x in (
            "non", "serious", "related", "fatal", "grade", "discontinuation",
            "reduction", "interruption", "pd", "cr", "pr", "sd", "teae",
            "progression", "death", "censored", "biochemistry", "hematology",
        ) if x in parts
    }


def _source_row_pool(source):
    hierarchy = source.get("hierarchical_rows") or []
    pool = []
    seen = set()
    for row in hierarchy:
        pos = row["position"]
        key = (pos.get("table_index"), pos.get("row_index"), pos.get("column_index"))
        if key not in seen:
            pool.append({
                "label": row["label"], "row_id": row["row_id"],
                "parent_row_id": row.get("parent_row_id"),
                "row_type": row.get("row_type"),
                "position": pos,
                "bookmarks": row.get("bookmark_names") or [],
                "origin": "word_hierarchy",
            })
            seen.add(key)
    # The original locator can represent rows omitted by the native first-
    # column reader. Include only *anchored table-cell* rows in the fallback,
    # avoiding fake 'physical' coordinates for free-text paragraphs.
    for row in source.get("row_candidates") or []:
        pos = row.get("position") or {}
        if pos.get("location_type") != "table_cell":
            continue
        key = (pos.get("table_index"), pos.get("row_index"), pos.get("column_index"))
        if key not in seen:
            pool.append({
                "label": row["label"], "row_id": "L" + str(len(pool)+1).zfill(4),
                "parent_row_id": None, "row_type": "unclassified",
                "position": pos,
                "bookmarks": row.get("bookmarks") or [],
                "origin": "locator_backup",
            })
            seen.add(key)
    return pool


def _compatible(a, b):
    aa, bb = _protected_concepts(a), _protected_concepts(b)
    # Clinical qualifiers cannot be erased by similarity.  A synoynm such
    # as Related TEAE / Adverse Reaction is reviewed separately below.
    return aa == bb


def _candidate_for(label, pool, used):
    key = normalize_row_label(label)
    choices = []
    for j, item in enumerate(pool):
        if j in used:
            continue
        other = normalize_row_label(item["label"])
        if not key or not other:
            continue
        sim = SequenceMatcher(None, key, other).ratio()
        if key == other:
            choices.append((3, 1.0, j, item, "lexical_normalized"))
        elif _compatible(label, item["label"]) and sim >= .74:
            choices.append((2, sim, j, item, "fuzzy_requires_review"))
    if choices:
        priority, sim, index, item, relation = max(choices, key=lambda c: (c[0], c[1]))
        return {"source": item, "index": index, "relation": relation,
                "label_similarity": round(sim, 4)}
    # A clinically related concept may exist without safe interchangeability.
    # Keep only specific review proposals rather than equating a related TEAE
    # with any 'Adverse Reaction' in every clinical protocol.
    if "related teae" in key or "related serious teae" in key:
        for j, item in enumerate(pool):
            if j in used:
                continue
            other = normalize_row_label(item["label"])
            if "adverse reaction" in str(item["label"]).casefold():
                if ("serious" in key) == ("serious" in other):
                    return {
                        "source": item, "index": j,
                        "relation": "clinical_alias_requires_definitional_review",
                        "label_similarity": 0.0,
                    }
    return None


def align_target_rows(source, target):
    """Return row alignment candidates including explicit target children."""
    pool = _source_row_pool(source)
    used = set()
    results = []
    for target_row in target.get("rows") or []:
        requested = [{
            "label": target_row["label"],
            "parent": None,
            "origin": "target_spec_requirement",
        }]
        requested.extend({
            "label": child["label"],
            "parent": target_row["label"],
            "origin": child["origin"],
        } for child in target_row.get("explicit_category_children") or [])
        for requested_row in requested:
            m = _candidate_for(requested_row["label"], pool, used)
            if m:
                # This one-to-one assignment is only a planning proposal.
                used.add(m["index"])
                results.append({
                    "target": requested_row,
                    "source": m["source"],
                    "relation": m["relation"],
                    "label_similarity": m["label_similarity"],
                    "status": "requires_review",
                    "reason": (
                        "Normalized row text corresponds; clinical context unverified"
                        if m["relation"] == "lexical_normalized" else
                        "Potential clinical row correspondence; do not execute without definition review"
                    ),
                })
            else:
                results.append({
                    "target": requested_row,
                    "source": None,
                    "relation": "unmatched",
                    "label_similarity": None,
                    "status": "requires_review",
                    "reason": "No safe corresponding source row identified",
                })
        if (">= 3" in normalize_row_label(target_row["label"]) or
                "grade ≥ 3" in target_row["label"].casefold() or
                "grade >= 3" in target_row["label"].casefold()):
            # Severity level aggregation is a structural candidate, never
            # authorization to add category counts across individual patients.
            grades = [
                row for row in pool
                if re.fullmatch(r"grade\s*[345]", row["label"], re.I)
            ]
            if len(grades) >= 2:
                results.append({
                    "target": {"label": target_row["label"], "parent": None,
                               "origin": "target_spec_requirement"},
                    "source": {"source_rows": grades},
                    "relation": "aggregation_candidate",
                    "label_similarity": None,
                    "status": "requires_review",
                    "reason": (
                        "Source has severity categories 3-5; display grouping "
                        "does not imply patient-count arithmetic"
                    ),
                })
    return {
        "matches": results,
        "matched_source_indices": sorted(used),
        "source_pool": pool,
        "unmatched_source_rows": [item for j, item in enumerate(pool) if j not in used],
        "counts_by_relation": dict(Counter(x["relation"] for x in results)),
    }


def _source_method_features(source):
    cells = []
    for table in source.get("tables") or []:
        for row in table.get("grid") or []:
            cells.extend(c.get("text", "") for c in row[:3])
    corpus = " ".join(cells).casefold()
    return {
        "descriptive_mean_sd": (
            bool(re.search(r"\bmean\b", corpus)) and
            bool(re.search(r"\b(?:sd|standard deviation)\b", corpus))
        ),
        "kaplan_meier_explicit": (
            "kaplan" in corpus or "km estimate" in corpus
        ),
        "quartiles_explicit": all(re.search(
            rf"\b{part}\b", corpus
        ) for part in ("q1", "median", "q3")),
        "ci_explicit": "confidence interval" in corpus or "95% ci" in corpus,
    }


def classify_layout_compatibility(source, target):
    """Heuristic class with explicit reasons, no unsupported certainty."""
    profile = source.get("layout_profile") or {}
    axis = profile.get("axis_orientation") or "unclassified"
    source_headers = source.get("column_candidates") or []
    # Only source header anchors actually in a table are counted; physical
    # column indices and number of headings are intentionally distinct.
    physical_headers = [
        c for c in source_headers
        if (c.get("position") or {}).get("location_type") == "table_cell"
    ]
    source_count = len(physical_headers)
    target_count = len(target.get("columns") or [])
    text = " ".join(
        target.get("statistics_to_display", []) +
        target.get("methods", []) +
        [str(target.get("endpoint") or "")]
    ).casefold()
    target_km = "kaplan" in text or "brookmeyer" in text
    src_features = _source_method_features(source)
    reasons = []
    blockers = []
    risks = []
    if not target.get("rows") or not target.get("columns"):
        blockers.append("Target rows/columns not extracted; structural edits must wait")
        mode = "blocked_target_incomplete"
    elif axis == "cohort_rows_statistic_columns":
        mode = "rebuild_with_source_style"
        reasons.append("Source uses cohort rows/statistic columns; target expects treatment-group headings")
        if target_km and not src_features["kaplan_meier_explicit"]:
            risks.append("Target Kaplan-Meier/Brookmeyer-Crowley method not visible in source table grid")
    elif axis == "no_word_table":
        mode = "rebuild_with_source_style"
        reasons.append("Source DOCX has no editable native Word table")
    elif axis == "unclassified":
        mode = "layout_review_before_edit"
        reasons.append("No reliable treatment-group header orientation found")
    elif source_count > max(4, target_count + 2):
        mode = "rebuild_with_source_style"
        reasons.append("Source has substantially more treatment columns than target")
    elif target_count != source_count:
        mode = "structural_edit_candidate"
        reasons.append("Source vs target treatment column count differs")
    else:
        mode = "text_or_structural_edit_candidate"
        reasons.append("Source and target treatment column counts appear compatible")
    if target_km and src_features["descriptive_mean_sd"] and not src_features["kaplan_meier_explicit"]:
        risks.append("Source visibly uses Mean/SD while target requests a survival-analysis method")
    if target.get("unresolved_fields"):
        risks.append("Target Specification gaps remain: " + ", ".join(target["unresolved_fields"]))
    # Never treat a heuristic score as safe-to-edit status.
    return {
        "mode": mode,
        "status": "blocked" if blockers else "review_required",
        "reasons": reasons,
        "blockers": blockers,
        "risks": list(dict.fromkeys(risks)),
        "source_axis": axis,
        "source_header_count": source_count,
        "source_header_coordinates": [
            {"table_index": (c.get("position") or {}).get("table_index"),
             "column_index": (c.get("position") or {}).get("column_index"),
             "label": c["label"]}
            for c in physical_headers
        ],
        "target_column_count": target_count,
        "source_method_features": src_features,
        "target_requires_km": target_km,
        "executor_ready": False,
        "basis": "deterministic Word-grid and target-spec heuristics; not clinical sign-off",
    }
