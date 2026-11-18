"""Target SAP body to AE TFL specification (rule-based class-project pilot).

Only SAP paragraphs determine clinical content. The source-study shell is
never used to determine target rows, drug arms, or explanatory notes.
"""
from __future__ import annotations
import re
from typing import Any

AE_SECTION = re.compile(r"\b8\.8\.2\s+Adverse Events\b", re.I)
RP_PROTOCOL = re.compile(r"\bRP6530-2101\b", re.I)
TFL_ID = "14.3.1.1"
TFL_TITLE = "Overall Summary of Adverse Events - Safety Analysis Set"


def _n(x: Any) -> str:
    return " ".join(str(x or "").split())


def _find_aes(parsed: dict) -> tuple[dict, dict]:
    blocks = parsed.get("blocks") or []
    header = next((b for b in blocks if AE_SECTION.search(b.get("text") or "")), None)
    if header is None:
        raise ValueError("No '8.8.2 Adverse Events' SAP body section. This pilot only generates Overall AE Shells.")
    start = blocks.index(header)
    detail = next((b for b in blocks[start+1:start+12] if "Any non-TEAE" in b.get("text", "")
                   and "Any TEAE" in b.get("text", "")), None)
    if detail is None:
        raise ValueError("The AE SAP section does not contain a parseable bulleted overall-summary list")
    return header, detail


def _body_range(parsed: dict, ae_header: dict) -> tuple[int, int]:
    """Bound input to body pages before Content List or hold-out TFL shells.

    The known RP6530-2101 SAP uses physical pages 4–21 for the body. Other
    SAPs are accepted only on a conservative short-window heuristic.
    """
    blocks = parsed.get("blocks") or []
    known = any(RP_PROTOCOL.search(b.get("text", "")) for b in blocks[:80])
    if known:
        if ae_header["page"] > 21:
            raise ValueError("Unexpected AE location in RP6530-2101; refusing fixed body boundary")
        return 4, 21
    end = ae_header["page"] + 2
    for b in blocks:
        page = b.get("page", 9999)
        if page > 2 and page <= end:
            t = _n(b.get("text")).casefold()
            if t.startswith(("tfl content list", "list of tables", "table of contents for tables")):
                end = min(end, page - 1)
                break
    if end < ae_header["page"]:
        raise ValueError("SAP AE body appears inside the excluded TFL section")
    return 1, min(end, parsed.get("pages", end))


def _authorized_blocks(parsed: dict, page_range: tuple[int, int]) -> list[dict]:
    a, b = page_range
    return [x for x in parsed.get("blocks") or [] if a <= x["page"] <= b]


def _extract_arms(blocks: list[dict]) -> tuple[list[str], dict]:
    expression = re.compile(
        r"\bGroup\s*1\s*:\s*([^:;.)]+?)\s+and\s+Group\s*2\s*:\s*([^:;.)]+?)"
        r"(?=\)\s*in\s*\d+\s*:\s*\d+\b|\s+in\s*\d+\s*:\s*\d+\b|\s+based\s+on|[;.)])",
        re.I,
    )
    for block in blocks:
        match = expression.search(block.get("text", ""))
        if match:
            labels = [_n(match.group(i)).strip(",;() ") for i in (1, 2)]
            if all(2 < len(x) < 110 for x in labels) and labels[0] != labels[1]:
                return labels, block
    raise ValueError("Could not verify two specific treatment group labels in SAP body; refusing to invent arms")


def _parse_ae_rows(block: dict) -> list[str]:
    text = str(block.get("text") or "")
    if "Summaries showing" in text:
        text = text.split("Summaries showing", 1)[0]
    parts = [_n(x) for x in re.split(r"\s*[•▪]\s*", text) if _n(x)]
    rows = []
    special = None
    for part in parts:
        if part.lower().startswith("protocol-defined adverse events of special interest"):
            special = part.rstrip(" :")
            continue
        if special and part.lower() in ("overdose", "pregnancy, abortion, birth defects/congenital anomalies"):
            rows.append(f"{special}: {part}")
        else:
            rows.append(part)
    if len(rows) < 5 or not any("TEAE" in x for x in rows):
        raise ValueError("Could not recover enough explicit overall AE categories")
    return rows


def _quote_evidence(block: dict) -> dict:
    return {
        "ref_id": block["block_id"],
        "document_kind": "sap_body",
        "page_numbers": [block["page"]],
        "exact_text": block["text"],
        "location": block["block_id"],
    }


def extract_ae_spec_from_sap(parsed: dict) -> tuple[dict, dict]:
    """One-target rule extractor; never reads target shell pages for content."""
    ae, detail = _find_aes(parsed)
    page_range = _body_range(parsed, ae)
    blocks = _authorized_blocks(parsed, page_range)
    if ae not in blocks or detail not in blocks:
        raise ValueError("AE summary list lies beyond authorized SAP body pages")
    arms, arm_evidence = _extract_arms(blocks)
    rows = _parse_ae_rows(detail)
    safety = next((x for x in blocks if re.search(r"8\.3\.1\s+Safety Population", x.get("text", ""), re.I)), ae)
    source_notes = []
    if "a patient will only be counted once" in ae["text"].casefold():
        m = re.search(r"a patient will only be counted once.*?grade attained\.", ae["text"], re.I)
        if m:
            source_notes.append({"text": _n(m.group(0)), "ref_id": ae["block_id"], "type": "SAP-derived"})
    m = re.search(r"Treatment Emergent Adverse Events \(TEAEs\) are events[^.]+\.", ae["text"], re.I)
    if m:
        source_notes.append({"text": _n(m.group(0)), "ref_id": ae["block_id"], "type": "SAP-derived"})
    if not source_notes:
        raise ValueError("No verifiable AE definition or counting rules from SAP body")

    study_verified = any(RP_PROTOCOL.search(x.get("text", "")) for x in blocks[:80])
    table_id = TFL_ID if study_verified else "AUTO-AE-001"
    title = TFL_TITLE if study_verified else "Overall Summary of Adverse Events - Safety Population"
    pointers = {
        "/statistical_requirements/analysis_topic": [ae],
        "/statistical_requirements/endpoint_name": [ae],
        "/statistical_requirements/analysis_population": [safety],
        "/statistical_requirements/treatment_groups": [arm_evidence],
        "/statistical_requirements/statistics_to_display": [ae],
        "/statistical_requirements/analysis_methods": [ae],
        "/table_requirements/row_requirements": [detail],
        "/table_requirements/column_requirements": [ae],
        "/table_requirements/footnote_requirements": [ae],
    }
    all_refs = {item["block_id"]: item for group in pointers.values() for item in group}
    prov = {
        "evidence": [_quote_evidence(b) for b in all_refs.values()],
        "field_links": [{
            "json_pointer": path,
            "ref_ids": [b["block_id"] for b in bs],
            "derivation": "rule_extracted_with_exact_sap_quote",
        } for path, bs in pointers.items()],
    }
    spec = {
        "identity": {
            "tfl_id": table_id, "output_type": "table", "title": title,
            "content_list_order": None, "section": "8.8.2",
        },
        "statistical_requirements": {
            "analysis_topic": "Overall summary of adverse events",
            "endpoint_name": "Treatment-emergent adverse events (TEAEs)",
            "endpoint_type": "safety",
            "analysis_population": ["Safety Population"],
            "analysis_methods": ["Patient counts, percentages and event counts by treatment and overall"],
            "treatment_groups": arms,
            "statistics_to_display": ["Number of patients (n)", "Percentage (%)", "Number of events"],
            "variables_to_display": rows,
            "stratification_factors": [], "visits_or_timepoints": [], "notes": [],
        },
        "table_requirements": {
            "row_requirements": rows,
            "column_requirements": ["Overall"],
            "footnote_requirements": [n["text"] for n in source_notes],
            "denominator_rule": None,
        },
        "provenance": prov,
        "readiness": "needs_review",
    }
    analysis = {
        "mode": "AE_STRUCTURAL_REBUILD_MVP",
        "body_page_range": list(page_range),
        "body_page_selection": "known_RP6530_body_4_21" if study_verified else "AE_section_bounded_heuristic",
        "rules": ["8.8.2 AE section", "literal bullet list", "explicit Group 1/2", "SAP-quoted footnotes"],
        "evidence_ref_ids": list(all_refs),
        "tfl_id_is_verified_for_this_study": study_verified,
        "inferred_presentation_elements": [
            "Four-column layout (category / 2 arms / Overall)",
            "n (%) and event-count placeholder formatting",
            "Header N=xx placeholders",
        ],
        "unresolved": [
            "Per-table percentage denominator rule not explicitly confirmed",
            "Cell decimal precision not explicitly confirmed",
            "Patient counts and event counts are not calculated; only placeholders shown",
            "Final layout requires comparison with target held-out shell",
        ],
    }
    return spec, analysis
