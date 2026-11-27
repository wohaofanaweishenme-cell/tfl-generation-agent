# Phase 6: simplified RAG and structural reasoning
Branch simplified-rag-v3, based on cb743a1. Generic Library remains unchanged.
Run Colab 12, 13, 14 in that order. They independently clone the same branch and read the original Phase52 run ZIP from Drive, not the browser's parent-folder ZIP. All three make zero LLM requests. Local BGE model inference in 13 and 14 is new embedding computation; it may download model weights. Output archives are separate from Phase52.
- 6.1: approved JSON only, complete same-type contexts, no gold labels. Compact JSON length reported, exact LLM token count not asserted.
- 6.2: cached verified body chunks and source spans; global hybrid vs global soft scope vs old scoped, equal per-facet top 5 and target budget 15, round-robin merge. Full depth before soft adjustment. Historical claim overlap and one directly inspected protocol-deviation anchor are diagnostics, not independent gold. Review pooled CSV (0/1) and call evaluate_review before reporting pooled Recall/Precision/MRR. No scope-only claims promoted.
- 6.3: compare all eligible templates/presets using keyword, dense, title joint, and cached accepted-claim joint; fixed provisional weights, forced rank recommendations only. Old five methods retained in paired challenge metrics. 431 title benchmark uses source registry only for evaluation labels/title/type, never as runtime retrieval. No preset ground truth or held-out claim. No new evidence extraction yet.
- 6.3 D, 6.4, 6.5 deferred pending review and authorization of 18-call pilot. Do not trigger LLM automatically. No generation.
Tests: python -m pytest -q tests/test_phase6_offline.py

Phase 6.2 also reports a separate `soft_scope_expanded` arm with deterministic title-conditioned facet extensions. Its candidate budget is identical; extension hints are not clinical facts. Both original-query soft-scope and expanded-query evidence are saved for comparison.
