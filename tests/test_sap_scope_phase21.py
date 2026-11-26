import numpy as np
from tfl_agent.tools.sap_scope import segment_blocks, scoped_chunks, target_topic
from tfl_agent.tools.sap_hybrid import HybridSAPIndex


def b(i, text, page=4):
    return {"block_id": f"sap:p{page}:b{i}", "page": page, "section": None, "text": text}


def test_embedded_sections_and_endpoint_continuation():
    blocks = [
        b(0, "4.3 Method of Assignment of Patients to Treatment Groups This is a randomized study."),
        b(1, "7.1 General Methodology All analyses use descriptive statistics."),
        b(2, "8.3 Analysis Populations The populations follow."),
        b(3, "8.3.1 Safety Population The Safety Population includes treated patients."),
        b(4, "8.4 Demographic and Other Baseline Characteristics All summaries are descriptive."),
        b(5, "8.7.2 Analysis of Secondary Efficacy Variables These are summarized."),
        b(6, "• Overall Response Rate (ORR): response rate. • Progression Free Survival (PFS): time to event."),
        b(7, "• The Q1, median and Q3 will be provided."),
        b(0, "Duration of response: time since response.", 5),
        b(1, "• Censoring rules.", 5),
        b(2, "8.8. 1 Duration of Treatment Exposure and Compliance to Study Treatment The study medication.", 5),
    ]
    segments, excluded, headings = segment_blocks(blocks)
    assert {h["section"] for h in headings} >= {"4.3","7.1","8.3","8.3.1","8.4","8.7.2","8.8.1"}
    assert segments[0]["study_scope"] == "treatment_groups"
    assert any(s["topic_scope"] == "demographics" and s["section"] == "8.4" for s in segments)
    assert any(s["topic_scope"] == "pfs" and "Q1" in s["text"] for s in segments)
    assert any(s["topic_scope"] == "dor" and "Censoring rules" in s["text"] for s in segments)
    by_id = {b["block_id"]: b for b in blocks}
    for s in segments:
        assert s["text"] == by_id[s["source_block_id"]]["text"][s["source_start"]:s["source_end"]]
    chunks, meta = scoped_chunks(segments)
    assert not any("response rate." in c.text and "time to event." in c.text for c in chunks)
    assert target_topic("Summary of Progression Free Survival") == "pfs"
    assert target_topic("PFS rate at 6 months") == "pfs_landmark"


def test_header_footer_and_inline_major():
    blocks = []
    for p in (4,5,6):
        blocks += [b(0, "STATISTICAL ANALYSIS PLAN", p), b(1, "Sponsor metadata", p),
                   b(2, "6.7 Pharmacodynamics Parameters Not Applicable. 7. STATISTICAL METHODS", p),
                   b(3, f"CONFIDENTIAL Page {p} of 20", p)]
    segments, excluded, headings = segment_blocks(blocks)
    assert len(excluded) == 9
    assert any(h["section"] == "7" for h in headings)
    assert all("STATISTICAL ANALYSIS PLAN" not in s["text"] for s in segments)


class FakeEncoder:
    def encode(self, texts, *, is_query=False):
        return np.array([[1 + t.count("survival"), 1 + t.count("response")] for t in texts])


def test_restrict_search_without_changing_default():
    seg, _, _ = segment_blocks([b(0, "Progression Free Survival: survival time"),
                                b(1, "Duration of response: response time")])
    chunks, meta = scoped_chunks(seg)
    index = HybridSAPIndex(chunks, FakeEncoder())
    plan = [{"facet":"target","query":"response survival"}]
    allowed = {c.chunk_id for c in chunks if meta[c.chunk_id]["topic_scope"] == "pfs"}
    assert allowed
    result = index.search(plan, top_k=2, depth=2, allowed_chunk_ids=allowed)
    assert all(h["chunk_id"] in allowed for hits in result[0]["methods"].values() for h in hits)
    assert len(index.search(plan, top_k=2, depth=2)[0]["methods"]["dense"]) == 2
