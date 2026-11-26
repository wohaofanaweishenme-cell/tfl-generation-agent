"""Conservative section/endpoint segmentation of parser-normalized SAP blocks.

All segments retain source block IDs and exact character offsets. Scope labels
are heuristic retrieval metadata, NOT clinical validation or proof of applicability.
"""
from __future__ import annotations
import re
from collections import defaultdict
from itertools import groupby
from tfl_agent.tools.sap_hybrid import make_chunks

# Require a dotted section number and an alphabetic title; avoid numbered
# footnotes, dates, decimals and ordinary list items where possible.
SUB = re.compile(r"^\s*(\d+(?:\.\s*\d+){1,4})\s+([A-Z][A-Za-z])")
MAJOR = re.compile(r"(?:^|(?<=[.!?])\s+)(\d{1,2})\.\s+([A-Z][A-Z &/-]+(?:\b|$))")
ENDPOINTS = {
    "pfs": r"progression[\s-]+free survival|\bPFS\b",
    "os": r"overall survival|\bOS\b",
    "orr": r"overall response rate|\bORR\b",
    "cbr": r"clinical benefit rate|\bCBR\b",
    "dor": r"duration of response|\bDoR\b",
    "docb": r"duration of clinical benefit|\bDoCB\b",
    "treatment_duration": r"duration of treatment(?: exposure)?",
    "pfs_landmark": r"PFS rate at [^:.;•]{1,45}|proportion of patients with [^:.;•]{1,45}PFS",
}
# Only explicit starts/colon-labelled headings change active endpoint;
# mentioning another endpoint in a sentence does not.
ANCHOR = re.compile(r"(?:^|(?<=•)|(?<=\n))\s*(?:•\s*)?("
                    + "|".join("(?:"+v+")" for v in ENDPOINTS.values())
                    + r")\s*(?:\([A-Za-z]+\))?\s*:", re.I)
STUDY_PATTERNS = {
    "treatment_groups": r"method of assignment|assignment.{0,30}treatment|general design|study design|randomi[sz]ation",
    "populations": r"analysis populations?|(?:safety|intent.to.treat|per.protocol|protocol|pharmacokinetics).{0,35}population",
    "general_statistics": r"general methodology|general statistical|statistical methods",
    "missing_data": r"missing data|dropouts|imputation",
    "subgroups": r"examination of subgroups|subgroup analyses|subgroup analysis",
    "visits": r"schedule of evaluations|schedule of assessments|time point algorithms|relative day|windows",
}
TOPIC_PATTERNS = {
    "demographics": r"demographic|baseline characteristics",
    "ae": r"adverse events?|safety summary",
    "laboratory": r"clinical laboratory|laboratory evaluations?",
    "physical_exam": r"physical examination",
    "ecg": r"electrocardiogram|\becg\b",
    "vital_signs": r"vital signs?",
    "disposition": r"disposition of patients|patient disposition",
    "medications": r"concomitant therapy|concomitant medication|prior therapy|prior therapies",
    "protocol_deviations": r"protocol deviations",
}
STUDY_QUERIES = {
    "treatment_groups": "method of assignment of patients to treatment groups randomization dose cohort arms regimen",
    "populations": "analysis population definitions inclusion criteria safety intent to treat per protocol analysis set",
    "general_statistics": "general methodology descriptive statistics continuous categorical frequency percentage denominator confidence interval",
    "missing_data": "handling of dropouts missing data imputation missing dates rules",
    "subgroups": "examination of subgroups stratification subgroup definitions analysis by subgroup",
    "visits": "schedule of evaluations study visits time point algorithms relative day analysis windows baseline",
}


def _match_label(text, patterns):
    if patterns is ENDPOINTS and re.search(patterns["pfs_landmark"], text, re.I):
        return "pfs_landmark"
    for key, pattern in patterns.items():
        if re.search(pattern, text, re.I):
            return key
    return None


def target_topic(title):
    # Landmark summaries are separate from general PFS time-to-event.
    if re.search(r"\b(?:pfs|progression[\s-]+free survival)\b", title, re.I) and re.search(r"\b(?:rate|landmark)\b", title, re.I):
        return "pfs_landmark"
    return _match_label(title, ENDPOINTS) or _match_label(title, TOPIC_PATTERNS)


def _boilerplate(block, repeated):
    text = block["text"].strip()
    return (text in repeated or
            bool(re.fullmatch(r"CONFIDENTIAL\s+Page\s+\d+\s+of\s+\d+.*", text, re.I)))


def segment_blocks(blocks):
    """Split numeric headers and explicit endpoint labels; preserve all source spans.

    Repeated identical blocks at page edges only are suppressed. Numbered sections
    and endpoint continuations carry forward across pages. Unknown text remains.
    """
    occurrences = defaultdict(set)
    per_page = defaultdict(list)
    for b in blocks:
        per_page[b["page"]].append(b)
    for page, items in per_page.items():
        for b in items[:2] + items[-1:]:
            occurrences[b["text"].strip()].add(page)
    repeated = {t for t, pages in occurrences.items() if len(pages) >= 3 and len(t) <= 350}
    segments, excluded, headings = [], [], []
    section, study, topic = None, None, None
    section_study = {}
    for block in blocks:
        text = block["text"]
        if _boilerplate(block, repeated):
            excluded.append({"block_id": block["block_id"], "reason": "repeated_page_edge_or_footer"})
            continue
        events = {}
        sub = SUB.match(text)
        if sub:
            events[0] = ("section", re.sub(r"\s+", "", sub.group(1)), text[sub.end(1):].strip())
        for m in MAJOR.finditer(text):
            # All-caps major heading only; require at least two alphabetic words.
            if len(re.findall(r"[A-Z]{2,}", m.group(2))) >= 2:
                pos = m.start(1)
                events[pos] = ("section", m.group(1), m.group(2).strip())
        if re.match(r"^\s*(?:•\s*)?(?:additional efficacy variables|other efficacy variables)\s*[:.]?\s*$", text, re.I):
            events[0] = ("endpoint", None, text)
        if re.match(r"^\s*(?:•\s*)?(?:PFS rate at|proportion of patients with [^:.;•]{1,45}PFS)", text, re.I):
            events[0] = ("endpoint", "pfs_landmark", text[:100])
        # Match anchors after a numbered heading too, when an explicit bullet occurs.
        for m in ANCHOR.finditer(text):
            pos = m.start()
            if pos == 0 and 0 in events:
                continue
            label = _match_label(m.group(1), ENDPOINTS)
            if label:
                events[pos] = ("endpoint", label, m.group(1))
        # Numbered efficacy heading plus endpoint label in same block without a bullet:
        # detect explicit colon label only after title-like words, not arbitrary mentions.
        if sub:
            for m in re.finditer(r"\b(Duration of Treatment(?: Exposure)?|Duration of Response|Duration of Clinical Benefit)\s*:", text, re.I):
                if m.start() < 110:
                    events.setdefault(m.start(), ("endpoint", _match_label(m.group(1), ENDPOINTS), m.group(1)))
                    break
        starts = sorted({0, len(text), *events})
        for a, z in zip(starts, starts[1:]):
            if a in events:
                kind, value, label = events[a]
                if kind == "section":
                    section = value
                    # Limit classification to leading heading words; avoid incidental body mentions.
                    lead = re.split(r"\b(?:This|The|All|For|A|An|No|Not|Patients|Data|Continuous|Absolute)\b", label, maxsplit=1)[0][:100]
                    # Heading "The..." may yield empty; retain unknown rather than invent.
                    study = _match_label(lead, STUDY_PATTERNS)
                    if study is None:
                        parent = section.rpartition(".")[0]
                        study = section_study.get(parent)
                    section_study[section] = study
                    topic = _match_label(lead, TOPIC_PATTERNS)
                    headings.append({"section": section, "source_block_id": block["block_id"],
                                     "source_start": a, "heading_preview": label[:100]})
                else:
                    topic, study = value, None
            fragment = text[a:z]
            if not fragment.strip():
                continue
            segments.append({
                "block_id": f"{block['block_id']}:{a}:{z}",
                "source_block_id": block["block_id"], "source_start": a, "source_end": z,
                "page": block["page"], "section": section, "study_scope": study,
                "topic_scope": topic, "text": fragment,
            })
    return segments, excluded, headings


def scoped_chunks(segments, max_words=160, overlap_words=30):
    chunks, metadata = [], {}
    # Group only contiguous matching scope. Never pack two known endpoints together.
    for key, group in groupby(segments, key=lambda s: (s["section"], s["study_scope"], s["topic_scope"])):
        group = list(group)
        for c in make_chunks(group, max_words=max_words, overlap_words=overlap_words):
            chunks.append(c)
            metadata[c.chunk_id] = {"section": key[0], "study_scope": key[1], "topic_scope": key[2]}
    return chunks, metadata


def study_query_plan():
    return [{"facet": k, "query": v} for k, v in STUDY_QUERIES.items()]
