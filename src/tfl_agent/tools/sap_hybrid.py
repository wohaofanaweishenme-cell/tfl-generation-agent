"""Phase 2: section-aware SAP chunks, BM25, local dense retrieval and RRF.

Retrieval returns candidate evidence, NOT validated clinical requirements.
All text spans are exact within the existing parser's whitespace-normalized blocks.
No clinical text is sent to a remote embedding API.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from tfl_agent.tools.pdf_parser import parse_sap
from tfl_agent.tools.sap_search import BM25Okapi


def tokens(text):
    # Split hyphenated and non-hyphenated clinical terms consistently.
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass(frozen=True)
class Span:
    block_id: str
    page: int
    start: int
    end: int


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    section: str | None
    pages: tuple[int, ...]
    text: str
    spans: tuple[Span, ...]

    def to_dict(self):
        return asdict(self)


def load_sap_body(path, page_range):
    """Require explicit physical PDF page bounds to avoid shell leakage."""
    import fitz
    path = Path(path)
    first, last = page_range
    with fitz.open(str(path)) as pdf:
        if not 1 <= first <= last <= len(pdf):
            raise ValueError(f"Invalid physical page range {page_range}; PDF has {len(pdf)} pages")
    sap = parse_sap(path)
    sap["blocks"] = [b for b in sap["blocks"] if first <= b["page"] <= last]
    if not sap["blocks"]:
        raise ValueError("No selectable text in the SAP body range")
    sap["body_page_range"] = [first, last]
    sap["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sap


def make_chunks(blocks, max_words=160, overlap_words=30):
    """Pack whole blocks within contiguous sections; split unusually long blocks.

    Overlap uses complete spans where possible, never crosses section boundaries.
    Offsets are Python character offsets into the parsed block, not PDF byte offsets.
    """
    if max_words < 2 or not 0 <= overlap_words < max_words:
        raise ValueError("Require 0 <= overlap_words < max_words and max_words >= 2")
    ids = [b["block_id"] for b in blocks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate block IDs")
    lookup = {b["block_id"]: b for b in blocks}
    chunks, pending = [], []
    section = None
    count = 0

    def emit():
        if not pending:
            return
        spans = tuple(p[0] for p in pending)
        raw = "\n".join(lookup[s.block_id]["text"][s.start:s.end] for s in spans)
        key = "|".join(f"{s.block_id}:{s.start}:{s.end}" for s in spans)
        cid = "chunk:" + hashlib.sha256(key.encode()).hexdigest()[:20]
        chunks.append(Chunk(cid, section, tuple(sorted({s.page for s in spans})), raw, spans))

    for b in blocks:
        if b.get("section") != section:
            emit()
            pending, count = [], 0
            section = b.get("section")
        text = b["text"]
        words = list(re.finditer(r"\S+", text))
        # Preserve full original block when short. Long blocks are sliced at word boundaries.
        for start in range(0, len(words), max_words):
            end = min(start + max_words, len(words))
            a = 0 if start == 0 else words[start].start()
            z = len(text) if end == len(words) else words[end].start()
            span = Span(b["block_id"], b["page"], a, z)
            n = end - start
            if count + n > max_words:
                emit()
                keep, kept = [], 0
                for item in reversed(pending):
                    if kept + item[1] > min(overlap_words, max_words - n):
                        break
                    keep.insert(0, item)
                    kept += item[1]
                pending, count = keep, kept
            pending.append((span, n))
            count += n
    emit()
    if not chunks:
        raise ValueError("No SAP chunks")
    return chunks



def split_oversized_chunks(chunks, metadata, segments, count_tokens, token_limit):
    """Only split over-limit chunks, preserving exact source intervals and scope.

    Recursively bisect, preferring nearby whitespace / span boundaries. The
    separator newline between source spans is synthetic; it is not a PDF
    character and need not occur between two separate child chunks. All actual
    source characters are retained, with no added overlap inside split parents.
    Retokenize each child (including special tokens); never assume additivity.
    """
    if type(token_limit) is not int or token_limit < 2:
        raise ValueError("Invalid embedding token limit")
    lookup = {s["block_id"]: s["text"] for s in segments}
    output, meta, audit = [], {}, []

    def build(parent, spans):
        text = "\n".join(lookup[s.block_id][s.start:s.end] for s in spans)
        key = "|".join(f"{s.block_id}:{s.start}:{s.end}" for s in spans)
        # Parent identity prevents collisions with pre-existing overlapped chunks.
        cid = "chunk:" + hashlib.sha256(("token-split-v1|" + parent.chunk_id + "|" + key).encode()).hexdigest()[:20]
        return Chunk(cid, parent.section, tuple(sorted({s.page for s in spans})), text, tuple(spans))

    def divide(parent, node):
        n = count_tokens(node.text)
        if n <= token_limit:
            return [(node, n)]
        # Locate each real source span in the joined text.
        offsets, pos = [], 0
        for s in node.spans:
            stop = pos + s.end - s.start
            offsets.append((pos, stop, s))
            pos = stop + 1
        size = len(node.text)
        mid = size // 2
        # Prefer a reasonably central whitespace boundary, otherwise split a
        # long unbroken string by character offset.
        lo, hi = max(1, size // 4), min(size - 1, 3 * size // 4)
        preferred = [i for i in range(lo, hi + 1)
                     if node.text[i-1].isspace() or node.text[i].isspace()]
        choices = sorted(set(preferred + [mid]), key=lambda i: (i == mid and i not in preferred, abs(i-mid), i))
        # Whitespace-only fragments cannot enter the evidence store. Search
        # other cuts if the central ones would create such a fragment.
        used = set(choices)
        choices += [i for i in range(1, size) if i not in used]
        for cut in choices:
            if not 0 < cut < size:
                continue
            left, right = [], []
            for begin, end, s in offsets:
                k = min(max(cut-begin, 0), end-begin)
                if k:
                    left.append(Span(s.block_id, s.page, s.start, s.start+k))
                if k < end-begin:
                    right.append(Span(s.block_id, s.page, s.start+k, s.end))
            if not left or not right:
                continue
            a, b = build(parent, left), build(parent, right)
            if not a.text.strip() or not b.text.strip():
                continue
            if max(len(a.text), len(b.text)) >= size:
                continue
            return divide(parent, a) + divide(parent, b)
        raise ValueError(f"Cannot split oversized chunk without losing source content: {parent.chunk_id}")

    def coverage(spans):
        # Preserve ordered intervals, coalescing only adjacent parts of the
        # same original span. This catches loss, duplication and reordering.
        out = []
        for s in spans:
            if out and out[-1][:2] == (s.block_id, s.page) and out[-1][3] == s.start:
                out[-1] = (*out[-1][:3], s.end)
            else:
                out.append((s.block_id, s.page, s.start, s.end))
        return out

    for parent in chunks:
        before = count_tokens(parent.text)
        if before <= token_limit:
            children = [(parent, before)]
        else:
            children = divide(parent, parent)
            if coverage(parent.spans) != coverage(s for c, _ in children for s in c.spans):
                raise ValueError("Token split source coverage mismatch")
            audit.append({"parent_chunk_id": parent.chunk_id, "parent_tokens": before,
                          "children": [{"chunk_id": c.chunk_id, "tokens": n} for c, n in children]})
        for c, n in children:
            if n > token_limit or c.chunk_id in meta:
                raise ValueError("Invalid token split output")
            output.append(c)
            meta[c.chunk_id] = dict(metadata[parent.chunk_id])
    return output, meta, {"policy": "oversized_only_v1", "token_limit": token_limit,
                          "original_chunks": len(chunks), "final_chunks": len(output),
                          "split_parents": len(audit), "splits": audit}


def query_plan(target):
    """Deterministic title-conditioned queries; no LLM, no inferred requirements."""
    title = target["title"].strip()
    if not title:
        raise ValueError("Target title is empty")
    t = " ".join(tokens(title))
    queries = [
        ("target", title),
        ("population", title + " analysis population analysis set eligibility"),
        ("statistics", title + " descriptive statistics summary measures statistical analysis methods"),
        ("structure", title + " variables categories rows columns grouping visits timepoints"),
        ("footnotes", title + " denominator missing data definition conventions"),
    ]
    if any(w in t for w in ("adverse event", "teae", "safety summary")):
        queries += [
            ("ae_definition", title + " treatment emergent adverse event definition onset"),
            ("ae_granularity", title + " overall incidence serious grade severity system organ class preferred term MedDRA"),
        ]
    if any(w in t for w in ("survival", "pfs", "time to event")):
        queries += [
            ("endpoint", title + " endpoint definition event progression death"),
            ("survival_methods", title + " Kaplan Meier censoring median confidence interval landmark time"),
        ]
    if any(w in t for w in ("physical examination", "laboratory", "vital sign", "ecg")):
        queries += [
            ("change_structure", title + " baseline post baseline shift normal abnormal visit change from baseline CTCAE grade"),
        ]
    if any(w in t for w in ("demographic", "baseline characteristic")):
        queries += [("demographic_variables", title + " age sex race ethnicity weight height descriptive statistics")]
    return [{"facet": f, "query": q} for f, q in queries]


class LocalEncoder:
    """Local inference; downloads model weights from Hugging Face on first use."""
    def __init__(self, model_name="BAAI/bge-small-en-v1.5", device=None, batch_size=32):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device, trust_remote_code=False)
        self.batch_size = batch_size
        self.query_prefix = ("Represent this sentence for searching relevant passages: "
                             if model_name.startswith("BAAI/bge-") else "")
        self.max_seq_length = self.model.max_seq_length

    def encode(self, texts, *, is_query=False):
        prefix = self.query_prefix if is_query else ""
        return self.model.encode([prefix + t for t in texts], batch_size=self.batch_size,
                                 normalize_embeddings=True, convert_to_numpy=True,
                                 show_progress_bar=False)

    def truncated_count(self, texts):
        # Explicit diagnostic: count inputs exceeding the model's token limit.
        return sum(self.token_count(t) > self.max_seq_length for t in texts)

    def token_count(self, text):
        return len(self.model.tokenizer.encode(text, add_special_tokens=True, truncation=False))


def _rank(scores, depth, positive_only=False):
    valid = [(i, float(s)) for i, s in enumerate(scores)
             if math.isfinite(float(s)) and (not positive_only or s > 0)]
    return sorted(valid, key=lambda x: (-x[1], x[0]))[:depth]


def rrf(sparse, dense, k=60):
    """Rank fusion over method-specific candidate lists; no raw score mixing."""
    if k <= 0:
        raise ValueError("RRF k must be positive")
    scores = Counter()
    for ranking in (sparse, dense):
        for rank, (idx, _) in enumerate(ranking, 1):
            scores[idx] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


class HybridSAPIndex:
    def __init__(self, chunks, encoder):
        import numpy as np
        self.chunks = list(chunks)
        if not self.chunks:
            raise ValueError("Empty chunk index")
        self.encoder = encoder
        self.sparse = BM25Okapi([tokens(c.text) or ["_empty_"] for c in self.chunks])
        texts = [c.text for c in self.chunks]
        self.dense = self._unit(encoder.encode(texts, is_query=False), len(texts))
        self.truncated_chunks = (encoder.truncated_count(texts)
                                 if hasattr(encoder, "truncated_count") else None)
        if self.truncated_chunks:
            raise ValueError(f"{self.truncated_chunks} chunks exceed dense model token limit; reduce max_words")

    @staticmethod
    def _unit(values, n):
        import numpy as np
        a = np.asarray(values, dtype=float)
        if a.ndim != 2 or a.shape[0] != n or not np.isfinite(a).all():
            raise ValueError("Invalid encoder output shape or non-finite embeddings")
        norm = np.linalg.norm(a, axis=1, keepdims=True)
        if (norm == 0).any():
            raise ValueError("Zero embedding vector")
        return a / norm

    def search(self, plans, top_k=5, depth=20, rrf_k=60, allowed_chunk_ids=None):
        if not 0 < top_k <= depth:
            raise ValueError("Require 0 < top_k <= depth")
        if not plans:
            raise ValueError("No queries")
        queries = [q["query"] for q in plans]
        qvec = self._unit(self.encoder.encode(queries, is_query=True), len(queries))
        if qvec.shape[1] != self.dense.shape[1]:
            raise ValueError("Query/document embedding dimension mismatch")
        allowed = None if allowed_chunk_ids is None else set(allowed_chunk_ids)
        def mask(scores):
            return [s if allowed is None or c.chunk_id in allowed else float('-inf')
                    for c, s in zip(self.chunks, scores)]
        out = []
        for plan, vec in zip(plans, qvec):
            sparse = _rank(mask(self.sparse.get_scores(tokens(plan["query"]))), depth, positive_only=True)
            dense = _rank(mask(self.dense @ vec), depth)
            fused = rrf(sparse, dense, rrf_k)
            sparse_ranks = {i: r for r, (i, _) in enumerate(sparse, 1)}
            dense_ranks = {i: r for r, (i, _) in enumerate(dense, 1)}
            methods = {}
            for name, ranking in (("bm25", sparse), ("dense", dense), ("hybrid", fused)):
                methods[name] = [
                    {"rank": r, "score": float(score), "chunk_id": self.chunks[i].chunk_id,
                     "pages": list(self.chunks[i].pages), "section": self.chunks[i].section,
                     "bm25_rank": sparse_ranks.get(i), "dense_rank": dense_ranks.get(i)}
                    for r, (i, score) in enumerate(ranking[:top_k], 1)
                ]
            out.append({**plan, "methods": methods})
        return out


def candidate_blocks(sap, chunks, results, method="hybrid"):
    """Bridge to old quote verifier: return original whole blocks, deduplicated.

    This may include text beyond the retrieved span; retain chunk provenance separately.
    """
    by_chunk = {c.chunk_id: c for c in chunks}
    seen = {s.block_id for q in results for hit in q["methods"][method]
            for s in by_chunk[hit["chunk_id"]].spans}
    return [b for b in sap["blocks"] if b["block_id"] in seen]
