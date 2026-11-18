"""Deterministic target-SAP quote audit and missing-evidence candidate search.

ONLY parsed, explicitly authorized SAP *body* pages can be used.  Source
Library templates, target-shell pages, and free-form LLM completions are not
evidence.  Candidate retrieval does not populate a Specification or approve
an Adaptation Operation.  No embedding index/API call is required.
"""
from __future__ import annotations

import re

from tfl_agent.agent.planning_gate import table_family


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _keywords(target, field):
    family = table_family(target)
    baseline = {
        "footnote_requirements": ("note", "definition", "percentage", "analysis", "baseline"),
        "denominator_rule": ("denominator", "percent", "number of patients", "population"),
        "statistics_to_display": ("summary", "statistics", "mean", "median", "percentage"),
        "analysis_population": ("analysis set", "safety population", "intent-to-treat"),
        "row_requirements": ("summarized", "tabular", "reported", "include"),
    }
    family_terms = {
        "adverse_events": ("adverse event", "teae", "discontinuation", "dose reduction"),
        "demographics": ("demographic", "baseline", "race", "gender"),
        "tumor_response": ("response", "recist", "clinical benefit", "orr"),
        "time_to_event": ("progression free", "censor", "kaplan", "survival"),
        "laboratory": ("hematology", "biochemistry", "change from baseline"),
        "disposition": ("disposition", "screened", "dropout"),
    }
    return tuple(dict.fromkeys(
        baseline.get(field, ()) + family_terms.get(family, ())
    ))


def _body_blocks(parsed, allowed_body_pages):
    if not isinstance(parsed, dict):
        return {}
    if (not isinstance(allowed_body_pages, (tuple, list))
            or len(allowed_body_pages) != 2
            or any(not isinstance(x, int) for x in allowed_body_pages)
            or allowed_body_pages[0] < 1
            or allowed_body_pages[1] < allowed_body_pages[0]):
        raise ValueError("Explicit 1-based SAP body-page range is required")
    lo, hi = allowed_body_pages
    blocks = {}
    for block in parsed.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        page = block.get("page")
        name = block.get("block_id")
        if not isinstance(page, int) or not (lo <= page <= hi) or not name:
            continue
        # Preserve only the allowed body area, no later holdout shell pages.
        blocks[name] = {
            "page": page, "block_id": name,
            "text": str(block.get("text") or ""),
        }
    return blocks


def resolve_target_evidence(spec, parsed_sap_blocks, *, allowed_body_pages,
                            max_candidates=4):
    """Verify linked quotes bytewise modulo whitespace, return candidate blocks.

    Matching a quote in a permitted SAP block establishes textual provenance,
    NOT clinical/statistical support for any specific row/column edit.
    """
    blocks = _body_blocks(parsed_sap_blocks, allowed_body_pages)
    target = {
        "identity": spec.get("identity") or {},
    }
    provenance = spec.get("provenance") or {}
    indexed = {e.get("ref_id"): e for e in provenance.get("evidence") or []}
    checks = []
    for ref_id, evidence in indexed.items():
        block = blocks.get(ref_id)
        quote = _norm(evidence.get("exact_text") or evidence.get("quote"))
        actual = _norm(block.get("text")) if block else ""
        if not block:
            status = "reference_not_in_authorized_sap_body"
        elif not quote:
            status = "empty_evidence_quote"
        elif quote not in actual:
            status = "quote_mismatch"
        else:
            status = "quote_text_verified"
        checks.append({
            "ref_id": ref_id,
            "page": block.get("page") if block else None,
            "status": status,
            "exact_text_preview": quote[:240],
        })

    field_status = {}
    for link in provenance.get("field_links") or []:
        pointer = str(link.get("json_pointer") or "")
        ids = list(dict.fromkeys(link.get("ref_ids") or []))
        if not pointer:
            continue
        checked = {x["ref_id"]: x["status"] for x in checks}
        status = (
            "missing" if not ids else
            "quote_text_verified" if all(
                checked.get(ref) == "quote_text_verified" for ref in ids
            ) else "invalid_or_unverified"
        )
        field_status[pointer] = {
            "ref_ids": ids,
            "status": status,
            "semantic_support_verified": False,
        }

    missing = []
    table = spec.get("table_requirements") or {}
    stats = spec.get("statistical_requirements") or {}
    for pointer, field, empty in [
        ("/table_requirements/footnote_requirements", "footnote_requirements",
         not table.get("footnote_requirements")),
        ("/table_requirements/denominator_rule", "denominator_rule",
         not table.get("denominator_rule")),
        ("/table_requirements/row_requirements", "row_requirements",
         not table.get("row_requirements")),
        ("/statistical_requirements/statistics_to_display", "statistics_to_display",
         not stats.get("statistics_to_display")),
        ("/statistical_requirements/analysis_population", "analysis_population",
         not stats.get("analysis_population")),
    ]:
        if not empty:
            continue
        queries = _keywords(target, field)
        ranked = []
        for b in blocks.values():
            text = _norm(b["text"])
            count = sum(1 for term in queries if term in text)
            if not count or len(text) < 30:
                continue
            ranked.append((count, b["page"], b["block_id"], b))
        ranked.sort(key=lambda a: (-a[0], a[1], a[2]))
        missing.append({
            "json_pointer": pointer,
            "field": field,
            "status": "evidence_retrieval_candidates_only",
            "candidate_blocks": [{
                "ref_id": b["block_id"],
                "page": b["page"],
                "text_preview": b["text"][:650],
                "keyword_match_count": count,
                "verification": "candidate_only_not_semantically_validated",
            } for count, _, _, b in ranked[:max_candidates]],
        })
    invalid = [x for x in checks if x["status"] != "quote_text_verified"]
    return {
        "resolver_version": "target-sap-evidence-v3",
        "source": "previously_parsed_target_sap_body_only",
        "allowed_body_pages": list(allowed_body_pages),
        "authorized_block_count": len(blocks),
        "linked_evidence_quote_checks": checks,
        "field_evidence_status": field_status,
        "invalid_quotes": invalid,
        "unverified_required_fields": [
            pointer for pointer, record in field_status.items()
            if record["status"] != "quote_text_verified"
        ],
        "missing_requirement_candidates": missing,
        "target_spec_modified": False,
        "clinical_semantic_support_verified": False,
        "note": (
            "Text-in-block verification is not a proof of statistical applicability. "
            "Candidate blocks require independent review before inclusion in a target Specification."
        ),
    }
