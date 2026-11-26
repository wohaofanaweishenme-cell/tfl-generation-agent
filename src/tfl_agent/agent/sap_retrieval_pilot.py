"""Read-only Phase 2 SAP retrieval pilot and audit export."""
import csv
import json
from pathlib import Path

from tfl_agent.tools.sap_hybrid import (
    load_sap_body, make_chunks, LocalEncoder, HybridSAPIndex, query_plan, candidate_blocks,
)


def _write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run_sap_retrieval(sap_path, page_range, targets, out_dir, *,
                      encoder=None, model_name="BAAI/bge-small-en-v1.5",
                      max_words=160, overlap_words=30, top_k=5, depth=20, rrf_k=60):
    """Index once per SAP, reuse for all targets. No LLM or shell generation."""
    if not targets or len({str(t["tfl_id"]) for t in targets}) != len(targets):
        raise ValueError("Targets must be nonempty with unique IDs")
    sap = load_sap_body(sap_path, page_range)
    chunks = make_chunks(sap["blocks"], max_words=max_words, overlap_words=overlap_words)
    encoder = encoder if encoder is not None else LocalEncoder(model_name)
    index = HybridSAPIndex(chunks, encoder)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lookup = {c.chunk_id: c for c in chunks}
    all_results, flat, annotations = [], [], []
    annotation_keys = set()
    for target in targets:
        results = index.search(query_plan(target), top_k=top_k, depth=depth, rrf_k=rrf_k)
        blocks = candidate_blocks(sap, chunks, results)
        all_results.append({"target": target, "queries": results,
                            "hybrid_candidate_block_ids": [b["block_id"] for b in blocks]})
        for q in results:
            for method, hits in q["methods"].items():
                for h in hits:
                    c = lookup[h["chunk_id"]]
                    row = {"tfl_id": target["tfl_id"], "title": target["title"],
                           "facet": q["facet"], "query": q["query"], "method": method,
                           **h, "pages": ";".join(map(str, c.pages)),
                           "block_ids": ";".join(dict.fromkeys(s.block_id for s in c.spans)),
                           "text": c.text}
                    flat.append(row)
                    key = (target["tfl_id"], q["facet"], c.chunk_id)
                    if key not in annotation_keys:
                        annotation_keys.add(key)
                        annotations.append({k: row[k] for k in ("tfl_id", "facet", "chunk_id", "pages", "text")}
                                           | {"relevant_0_or_1": "", "notes": ""})
    summary = {
        "sap_filename": sap["filename"], "sap_sha256": sap["sha256"],
        "physical_page_range": sap["body_page_range"], "block_count": len(sap["blocks"]),
        "chunk_count": len(chunks), "section_count": len({c.section for c in chunks if c.section is not None}),
        "unsectioned_chunks": sum(c.section is None for c in chunks),
        "model": getattr(encoder, "model_name", type(encoder).__name__),
        "embedding_dimension": int(index.dense.shape[1]),
        "truncated_chunks": index.truncated_chunks,
        "config": {"max_words": max_words, "overlap_words": overlap_words, "top_k": top_k,
                   "candidate_depth": depth, "rrf_k": rrf_k},
        "targets": [{"tfl_id": r["target"]["tfl_id"], "title": r["target"]["title"],
                     "queries": len(r["queries"]),
                     "hybrid_candidate_blocks": len(r["hybrid_candidate_block_ids"])}
                    for r in all_results],
        "retrieval_rows": len(flat),
        "evaluation_status": "unlabelled; no relevance accuracy or recall claimed",
        "warning": "Retrieved text is candidate evidence, not verified requirements. Source SAP text is confidential if the SAP is confidential.",
    }
    _write_json(out / "Summary.json", summary)
    _write_json(out / "SAP_Blocks.json", sap["blocks"])
    _write_json(out / "SAP_Chunks.json", [c.to_dict() for c in chunks])
    _write_json(out / "Retrieval_Results.json", all_results)
    _write_csv(out / "Retrieval_Comparison.csv", flat,
               ["tfl_id", "title", "facet", "query", "method", "rank", "score", "chunk_id",
                "pages", "section", "bm25_rank", "dense_rank", "block_ids", "text"])
    _write_csv(out / "Evidence_Annotation.csv", annotations,
               ["tfl_id", "facet", "chunk_id", "pages", "text", "relevant_0_or_1", "notes"])
    return summary, flat
