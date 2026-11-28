"""Offline regression tests for source-preserving token-limit fallback."""
from tfl_agent.tools.sap_hybrid import make_chunks, split_oversized_chunks
from tfl_agent.agent.unified_pipeline import source_records


def fixture(texts):
    blocks = [{"block_id": f"b{i}", "page": i+1, "section": "1", "text": t}
              for i,t in enumerate(texts)]
    segments = [{**b, "block_id": f"{b['block_id']}:0:{len(b['text'])}",
                 "source_block_id": b["block_id"], "source_start": 0,
                 "source_end": len(b["text"])} for b in blocks]
    chunks = make_chunks(segments)
    meta = {c.chunk_id: {"section": "1", "study_scope": None, "topic_scope": None} for c in chunks}
    return blocks, segments, chunks, meta


def count(text):
    # Deliberately adversarial tokenizer proxy: each character plus special tokens.
    return len(text) + 2


def test_normal_chunk_is_identical():
    blocks, segments, chunks, meta = fixture(["age and sex"])
    out, updated, audit = split_oversized_chunks(chunks, meta, segments, count, 32)
    assert out == chunks and updated == meta
    assert audit["split_parents"] == 0
    source_records(blocks, segments, out, updated)


def test_unbroken_string_preserves_every_character():
    blocks, segments, chunks, meta = fixture(["x.β/" * 250])
    out, updated, audit = split_oversized_chunks(chunks, meta, segments, count, 64)
    assert len(chunks) == 1 and len(out) > 1
    assert len({c.chunk_id for c in out}) == len(out)
    assert all(count(c.text) <= 64 for c in out)
    assert "".join(c.text for c in out) == blocks[0]["text"]
    assert audit["split_parents"] == 1
    assert source_records(blocks, segments, out, updated)
    assert split_oversized_chunks(chunks, meta, segments, count, 64) == (out, updated, audit)


def test_multi_page_source_intervals_and_scope():
    blocks, segments, chunks, meta = fixture(["First " * 20, "Second " * 20, "Third " * 15])
    assert len(chunks) == 1
    out, updated, audit = split_oversized_chunks(chunks, meta, segments, count, 60)
    records = source_records(blocks, segments, out, updated)
    by_block = {b["block_id"]: [] for b in blocks}
    for c in records:
        assert count(c["text"]) <= 60
        assert updated[c["chunk_id"]] == meta[chunks[0].chunk_id]
        for span in c["source_spans"]:
            by_block[span["block_id"]].append((span["start"], span["end"]))
    for b in blocks:
        pos = 0
        for a,z in by_block[b["block_id"]]:
            assert a == pos and z > a
            pos = z
        assert pos == len(b["text"])
    assert audit["final_chunks"] == len(out)
