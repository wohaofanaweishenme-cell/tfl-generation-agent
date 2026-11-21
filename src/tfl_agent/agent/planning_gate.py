"""Conservative pre-execution gate for Table adaptation planning.

Readiness and target-field completeness are checked *before* an adaptation
mode can be promoted to a structural edit candidate.  The planner is always
permitted to produce diagnostics; the executor is not permitted to act on
incomplete or clinically unverified requirements.
"""
from __future__ import annotations

import re


def table_family(target):
    title = str((target.get("identity") or {}).get("title") or "").casefold()
    if re.search(r"hematology|biochemistry|laboratory", title):
        return "laboratory"
    if re.search(r"adverse events?|teae|safety events", title):
        return "adverse_events"
    if re.search(r"demograph|baseline characteristics", title):
        return "demographics"
    if re.search(r"\b(pfs|progression.free survival)\b", title):
        return "time_to_event"
    if re.search(r"overall response|clinical benefit|objective response|\borr\b|\bcbr\b", title):
        return "tumor_response"
    if "disposition" in title:
        return "disposition"
    return "general_table"


def evaluate_target_completeness(target, *, evidence_assessment=None):
    """Return an auditable planning gate; never grant execution permission.

    A missing per-table footnote does not prove an incorrect target; it is a
    review condition. In contrast, no row/column requirements or explicit
    readiness='blocked' are hard blockers.
    """
    family = table_family(target)
    readiness = str(target.get("readiness") or "unknown").casefold()
    rows = target.get("rows") or []
    columns = target.get("columns") or []
    statistics = target.get("statistics_to_display") or []
    methods = target.get("methods") or []
    population = target.get("analysis_population") or []
    hard = []
    review = []
    requirements = {}

    def require(name, ok, *, blocking):
        requirements[name] = "present" if ok else "missing"
        if not ok:
            (hard if blocking else review).append(f"{name} missing or unverified")

    if readiness == "blocked":
        hard.append("Target Specification readiness is blocked")
    elif readiness != "ready":
        review.append("Target Specification readiness requires review")
    require("row_requirements", bool(rows), blocking=True)
    require("column_requirements", bool(columns), blocking=True)
    require("statistics_to_display", bool(statistics), blocking=True)
    require("analysis_population", bool(population), blocking=False)

    if family == "time_to_event":
        text = " ".join(statistics + methods).casefold()
        require("survival_method", bool(re.search(r"kaplan|km\b|survival|brookmeyer", text)), blocking=True)
        require("event_or_censoring_definition", any(
            "event" in r["label"].casefold() or "censor" in r["label"].casefold()
            for r in rows
        ), blocking=False)
    elif family == "laboratory":
        require("visits_or_timepoints", bool(target.get("visits_or_timepoints")), blocking=False)
        require("measurement_or_change_structure",
                any("actual" in r["label"].casefold() or "change" in r["label"].casefold()
                    for r in rows), blocking=False)
    elif family == "adverse_events":
        require("event_category_rows", any(
            "teae" in r["label"].casefold() or "adverse" in r["label"].casefold()
            for r in rows
        ), blocking=True)
        require("denominator_rule",
                bool(target.get("denominator_rule"))
                or target.get("denominator_applicability") == "not_applicable_for_current_spec",
                blocking=False)
    elif family == "tumor_response":
        require("response_rate_or_response_categories", any(
            "response" in r["label"].casefold() or "benefit" in r["label"].casefold()
            for r in rows
        ), blocking=True)
    elif family == "demographics":
        require("variable_rows", bool(rows), blocking=True)
        if any(r.get("kind") == "categorical_candidate" for r in rows):
            review.append("Target categories require source-SAP confirmation")
    elif family == "disposition":
        require("disposition_events", any(
            "complet" in r["label"].casefold() or "discontinu" in r["label"].casefold()
            for r in rows
        ), blocking=False)
    if target.get("denominator_applicability") == "unknown":
        review.append("Percentage-denominator applicability is unknown")
    if not target.get("footnotes"):
        review.append("Target footnotes not extracted: evidence review required")
    if evidence_assessment:
        if evidence_assessment.get("invalid_quotes"):
            hard.append("Linked SAP evidence failed exact-source verification")
        if evidence_assessment.get("unverified_required_fields"):
            review.append("Critical field-level evidence has not been verified against SAP blocks")
    status = "blocked" if hard else "review_required"
    return {
        "gate_version": "target-completeness-v3",
        "table_family": family,
        "target_readiness": readiness,
        "status": status,
        "hard_blockers": list(dict.fromkeys(hard)),
        "review_items": list(dict.fromkeys(review)),
        "required_field_status": requirements,
        "planning_allowed": True,
        "executor_ready": False,
        "reason": ("No clinical execution is authorized by a target-SAP planning gate"),
    }
