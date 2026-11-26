import json
from pathlib import Path

import numpy as np
import pytest

from tfl_agent.tools.sap_hybrid import (
    make_chunks, HybridSAPIndex, query_plan, rrf, candidate_blocks, load_sap_body,
)
from tfl_agent.agent.sap_retrieval_pilot import run_sap_retrieval


def block(i, text, section="7.1", page=4):
    return {"block_id": f"sap:p{page}:b{i}", "page": page, "section": section, "text": text}


class FakeEncoder:
    model_name = "deterministic-test-only"

    def encode(self, texts, *, is_query=False):
        return np.array([[1 + t.lower().count("survival"), 1 + t.lower().count("adverse")]
                         for t in texts])


def test_chunks_exact_offsets_and_sections():
    blocks = [block(0, "a b c d"), block(1, "e f g h i"),
              block(2, " ".join(map(str, range(29))), "7.2"),
              block(3, "next section", "7.3", 5)]
    chunks = make_chunks(blocks, max_words=10, overlap_words=4)
    lookup = {b["block_id"]: b for b in blocks}
    coverage = {b["block_id"]: set() for b in blocks}
    for c in chunks:
        assert len(c.text.split()) <= 10
        assert all(lookup[s.block_id]["section"] == c.section for s in c.spans)
        assert c.text == "\n".join(lookup[s.block_id]["text"][s.start:s.end] for s in c.spans)
        for s in c.spans:
            coverage[s.block_id].update(range(s.start, s.end))
    for b in blocks:
        assert all(i in coverage[b["block_id"]] for i, ch in enumerate(b["text"]) if not ch.isspace())
    assert chunks == make_chunks(blocks, max_words=10, overlap_words=4)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_overlap_and_invalid_parameters():
    blocks = [block(i, "one two three") for i in range(3)]
    chunks = make_chunks(blocks, max_words=6, overlap_words=3)
    assert chunks[0].spans[-1] == chunks[1].spans[0]
    with pytest.raises(ValueError):
        make_chunks(blocks, max_words=3, overlap_words=3)


def test_rrf_consensus():
    assert rrf([(0, 100), (1, 1)], [(1, .8), (2, .7)])[0][0] == 1


def test_query_facets_and_methods():
    blocks = [block(0, "Kaplan Meier survival censoring", "7.1"),
              block(1, "adverse events safety", "7.2"),
              block(2, "demographic age sex", "7.3")]
    chunks = make_chunks(blocks)
    index = HybridSAPIndex(chunks, FakeEncoder())
    plan = query_plan({"title": "Progression Free Survival"})
    assert "survival_methods" in {q["facet"] for q in plan}
    results = index.search(plan, top_k=2, depth=3)
    assert set(results[0]["methods"]) == {"bm25", "dense", "hybrid"}
    assert results[0]["methods"]["bm25"][0]["chunk_id"] == chunks[0].chunk_id
    assert results[0]["methods"]["hybrid"][0]["chunk_id"] == chunks[0].chunk_id
    original = candidate_blocks({"blocks": blocks}, chunks, results)
    assert original and all(b in blocks for b in original)


def test_pdf_page_bound_and_audit(tmp_path):
    import fitz
    path = tmp_path / "test.pdf"
    doc = fitz.open()
    for text in ("outside shell marker", "7 Analysis Methods", "survival censoring",
                 "other shell marker"):
        page = doc.new_page()
        page.insert_text((70, 80), text)
    doc.save(path)
    doc.close()
    sap = load_sap_body(path, (2, 3))
    assert {b["page"] for b in sap["blocks"]} == {2, 3}
    with pytest.raises(ValueError):
        load_sap_body(path, (2, 5))
    output = tmp_path / "audit"
    s, rows = run_sap_retrieval(path, (2, 3),
                               [{"tfl_id": "T1", "title": "Overall Survival"}], output,
                               encoder=FakeEncoder(), top_k=2, depth=3)
    assert s["physical_page_range"] == [2, 3]
    assert s["evaluation_status"].startswith("unlabelled")
    assert rows and all("shell marker" not in r["text"] for r in rows)
    assert len(list(output.iterdir())) == 6
    assert json.loads((output / "Summary.json").read_text()) == s
