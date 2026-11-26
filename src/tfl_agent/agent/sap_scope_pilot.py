"""Phase 2.1: dual-scope retrieval and auditable source spans, no extraction."""
import json
from pathlib import Path

from tfl_agent.tools.sap_hybrid import load_sap_body, LocalEncoder, HybridSAPIndex, query_plan
from tfl_agent.tools.sap_scope import segment_blocks, scoped_chunks, target_topic, study_query_plan
from tfl_agent.agent.sap_retrieval_pilot import _write_json, _write_csv, run_sap_retrieval


def run_scope_retrieval(sap_path, page_range, targets, out_dir, *, encoder=None,
                        model_name="BAAI/bge-small-en-v1.5", compare_phase2=True,
                        max_words=160, overlap_words=30, top_k=5, depth=20, rrf_k=60):
    if not targets or len({str(t["tfl_id"]) for t in targets}) != len(targets):
        raise ValueError("Targets must be nonempty with unique IDs")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sap = load_sap_body(sap_path, page_range)
    segments, excluded, headings = segment_blocks(sap["blocks"])
    chunks, meta = scoped_chunks(segments, max_words, overlap_words)
    encoder = encoder if encoder is not None else LocalEncoder(model_name)
    index = HybridSAPIndex(chunks, encoder)
    lookup = {c.chunk_id: c for c in chunks}
    segmap = {s["block_id"]: s for s in segments}
    rows, packages, study_results = [], [], []

    def search(plans, allowed):
        return index.search(plans, top_k=top_k, depth=depth, rrf_k=rrf_k,
                            allowed_chunk_ids=allowed) if allowed else []

    def sources(c):
        return [{"block_id": segmap[s.block_id]["source_block_id"],
                 "page": s.page, "start": segmap[s.block_id]["source_start"] + s.start,
                 "end": segmap[s.block_id]["source_start"] + s.end} for s in c.spans]

    def record(results, pool, target_id):
        for q in results:
            for method, hits in q["methods"].items():
                for h in hits:
                    c = lookup[h["chunk_id"]]
                    rows.append({"target_id": target_id, "pool": pool, "facet": q["facet"],
                                 "query": q["query"], "method": method, **h,
                                 **meta[c.chunk_id], "pages": ";".join(map(str, c.pages)),
                                 "source_block_ids": ";".join(dict.fromkeys(s["block_id"] for s in sources(c))),
                                 "text": c.text})

    def pack(results):
        ids = list(dict.fromkeys(h["chunk_id"] for q in results for h in q["methods"]["hybrid"]))
        return [{"chunk_id": i, **meta[i], "pages": list(lookup[i].pages),
                 "text": lookup[i].text, "source_spans": sources(lookup[i])} for i in ids]

    all_ids = set(lookup)
    for plan in study_query_plan():
        preferred = {i for i, m in meta.items() if m["study_scope"] == plan["facet"]}
        # Fallback excludes explicitly scoped endpoint/topic material; unknown remains unverified.
        fallback = {i for i, m in meta.items() if m["topic_scope"] is None}
        pool = "study_scoped" if preferred else "study_fallback_unverified"
        results = search([plan], preferred or fallback)
        record(results, pool, "STUDY")
        study_results.append({"facet": plan["facet"], "pool": pool,
                              "eligible_chunks": len(preferred or fallback),
                              "results": results, "evidence": pack(results)})

    for target in targets:
        topic = target_topic(target["title"])
        direct = {i for i, m in meta.items() if topic and m["topic_scope"] == topic}
        unknown = {i for i, m in meta.items() if m["topic_scope"] is None and m["study_scope"] is None}
        # If topic is not known or no explicit scope exists, use unknown pool only.
        primary = direct or unknown
        mode = "target_scoped" if direct else "target_fallback_unverified"
        plans = query_plan(target)
        hits = search(plans, primary)
        # Unknown evidence kept separate so the next phase cannot treat it as directly applicable.
        context = search(plans, unknown) if direct else []
        record(hits, mode, target["tfl_id"])
        record(context, "unclassified_context", target["tfl_id"])
        excluded_ids = sorted(all_ids - primary - unknown)
        packages.append({"target": target, "topic": topic, "pool": mode,
                         "eligible_chunks": len(primary), "results": hits,
                         "target_evidence": pack(hits), "context_evidence": pack(context),
                         "excluded_from_target_pool": [{"chunk_id": i, **meta[i]} for i in excluded_ids]})

    chunk_records = [{**c.to_dict(), **meta[c.chunk_id], "source_spans": sources(c)} for c in chunks]
    # Validate exact source reconstruction, including split blocks.
    source = {b["block_id"]: b for b in sap["blocks"]}
    for c in chunk_records:
        rebuilt = "\n".join(source[s["block_id"]]["text"][s["start"]:s["end"]] for s in c["source_spans"])
        if rebuilt != c["text"]:
            raise ValueError(f"Source provenance mismatch: {c['chunk_id']}")
    summary = {
        "sap_filename": sap["filename"], "sap_sha256": sap["sha256"],
        "physical_page_range": sap["body_page_range"], "original_blocks": len(sap["blocks"]),
        "excluded_boilerplate_blocks": len(excluded), "segments": len(segments),
        "chunks": len(chunks), "sections_detected": len({h["section"] for h in headings}),
        "unsectioned_chunks": sum(c.section is None for c in chunks),
        "model": getattr(encoder, "model_name", type(encoder).__name__),
        "embedding_dimension": int(index.dense.shape[1]), "truncated_chunks": index.truncated_chunks,
        "study": [{"facet": r["facet"], "pool": r["pool"], "eligible_chunks": r["eligible_chunks"],
                   "retrieved_chunks": len(r["evidence"])} for r in study_results],
        "targets": [{"tfl_id": p["target"]["tfl_id"], "topic": p["topic"], "pool": p["pool"],
                     "eligible_chunks": p["eligible_chunks"], "target_chunks": len(p["target_evidence"]),
                     "context_chunks": len(p["context_evidence"])} for p in packages],
        "provenance_verified": True,
        "evaluation_status": "unlabelled; scope labels are heuristic, not clinical verification",
    }
    _write_json(out / "Summary.json", summary)
    _write_json(out / "SAP_Blocks.json", sap["blocks"])
    _write_json(out / "Scoped_Segments.json", segments)
    _write_json(out / "Scoped_Chunks.json", chunk_records)
    _write_json(out / "Section_Audit.json", {"headings": headings, "excluded": excluded})
    _write_json(out / "Evidence_Package.json", {"study": study_results, "targets": packages,
                                                "warning": "Candidate evidence only; no applicability or clinical requirements verified."})
    _write_csv(out / "Retrieval_Comparison.csv", rows,
               ["target_id", "pool", "facet", "query", "method", "rank", "score", "chunk_id",
                "pages", "section", "study_scope", "topic_scope", "bm25_rank", "dense_rank",
                "source_block_ids", "text"])
    if compare_phase2:
        run_sap_retrieval(sap_path, page_range, targets, out / "Phase2_Baseline",
                          encoder=encoder, max_words=max_words, overlap_words=overlap_words,
                          top_k=top_k, depth=depth, rrf_k=rrf_k)
    return summary, rows
