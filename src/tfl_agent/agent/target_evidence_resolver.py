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


_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\s+([A-Z][^\n]{2,120})")
_SECTION_PREFERENCES = {
    "adverse_events": ("8.8.2", "6.6"),
    "demographics": ("8.4", "6.3"),
    "tumor_response": ("8.7.2", "6.4.2", "8.7"),
    "time_to_event": ("8.7.2", "6.4.2", "8.7"),
    "laboratory": ("8.8.3", "6.6.2", "8.8"),
    "disposition": ("8.1", "8.3"),
}


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
    current_section = None
    previous_page = None
    # Preserve the order from parsed PDF; no external shell material.
    for seq, block in enumerate(parsed.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        page = block.get("page")
        name = block.get("block_id")
        if not isinstance(page, int) or not (lo <= page <= hi) or not name:
            continue
        value = str(block.get("text") or "")
        match = _SECTION_RE.match(value)
        if match:
            current_section = match.group(1)
        # A headingless page can continue the prior section.
        blocks[name] = {
            "page": page, "block_id": name,
            "text": value, "section_id": current_section,
            "is_section_heading": bool(match),
            "sequence": seq,
        }
        previous_page = page
    return blocks


def _is_glossary(block):
    text = str(block.get("text") or "").strip()
    if re.search(r"^(?:list of )?abbreviations\b|^acronyms\b", text, re.I):
        return True
    # Abbreviation lists contain many all-caps definitions on the same page.
    return block.get("page", 99) <= 5 and len(re.findall(
        r"\b[A-Z]{2,6}\s+[A-Z][a-z]{3,}", text
    )) >= 5


def _section_matches(section, favored):
    if not section:
        return False
    return any(section == x or section.startswith(x + ".") for x in favored)


def _rank_requirement_candidates(blocks, *, family, field, limit):
    """Endpoint section first; generic methodology may only be a fallback.

    Scoring is a candidate discovery heuristic, not proof of a Table-specific
    denominator, footnote, or statistical method.
    """
    preferred = _SECTION_PREFERENCES.get(family, ())
    query = _keywords({"identity": {"title": {
        "adverse_events": "adverse events",
        "demographics": "demographics",
        "tumor_response": "overall response",
        "time_to_event": "progression free survival",
        "laboratory": "hematology",
        "disposition": "disposition",
    }.get(family, "")}}, field)
    anchors = [b for b in blocks.values()
               if b["is_section_heading"] and _section_matches(b["section_id"], preferred)]
    scored = []
    for block in blocks.values():
        text = _norm(block["text"])
        if len(text) < 30 or _is_glossary(block):
            continue
        hits = sum(1 for term in query if term in text)
        belongs = _section_matches(block.get("section_id"), preferred)
        neighbors = [
            anchor for anchor in anchors
            if abs(block["sequence"]-anchor["sequence"]) <= 2 and
            abs(block["page"]-anchor["page"]) <= 1
        ]
        is_generic = bool(re.match(r"^(?:7\.1|7\.2|7\.3)(?:\.|$)",
                                   str(block.get("section_id") or "")))
        # Section-oriented matching is enough to nominate a paragraph even
        # when it contains a family definition but few generic keywords.
        if not (hits or belongs or neighbors):
            continue
        source_type = ("target_section" if belongs
                       else "adjacent_to_target_section" if neighbors
                       else "general_methodology" if is_generic
                       else "cross_section_candidate")
        # Avoid the common error: score 4 generic hits above a 2-hit
        # endpoint-specific definition. Generic methodology is still
        # available but cannot be presented as target-specific.
        section_priority = {
            "target_section": 4,
            "adjacent_to_target_section": 3,
            "cross_section_candidate": 1,
            "general_methodology": 0,
        }[source_type]
        score = 10 * section_priority + min(hits, 9)
        scored.append((
            -score, block["page"], block["sequence"], block, hits,
            source_type, score,
        ))
    scored.sort(key=lambda row: row[:3])
    result = []
    for _, _, _, b, hits, source_type, score in scored[:limit]:
        result.append({
            "ref_id": b["block_id"], "page": b["page"],
            "section_id": b.get("section_id"),
            "source_section_relevance": source_type,
            "ranking_score": score,
            "text_preview": b["text"][:650],
            "keyword_match_count": hits,
            "verification": "candidate_only_not_semantically_validated",
        })
    return result


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
        section_candidates = _rank_requirement_candidates(
            blocks, family=table_family(target), field=field,
            limit=max_candidates,
        )
        missing.append({
            "json_pointer": pointer,
            "field": field,
            "status": "evidence_retrieval_candidates_only",
            "retrieval_strategy": "endpoint_section_first_with_general_fallback",
            "candidate_blocks": section_candidates,
        })
    invalid = [x for x in checks if x["status"] != "quote_text_verified"]
    return {
        "resolver_version": "target-sap-evidence-v4",
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
