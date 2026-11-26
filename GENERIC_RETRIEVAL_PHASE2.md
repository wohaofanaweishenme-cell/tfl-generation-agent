# Phase 2 — SAP Hybrid Retrieval

This phase adds an independent, read-only evidence retrieval pilot. It does not yet
change TFLSession, Step 2 specification extraction, the Phase 1 matcher or the libraries.

- Existing PyMuPDF parser supplies original 1-based page/block IDs and section numbers
  (heading detection is heuristic; section IDs may be missing or wrong).
- Explicit SAP-body physical page bounds are mandatory; do not index embedded TFL
  shells or Content Lists as clinical evidence.
- Chunks pack adjacent blocks within contiguous section boundaries (160 words, up to
  30 words of whole-span overlap). Long blocks are split at word boundaries. Every
  chunk retains exact offsets into parser-normalized blocks, not raw PDF bytes.
- BM25 reuses existing implementation with normalized tokenization.
- Local BAAI/bge-small-en-v1.5 dense encoder (384 dimensions expected); downloads
  weights at first use, but no SAP text goes to an embedding API. Token limit
  diagnostics fail closed if document chunks would be truncated.
- RRF k=60, depth=20, top 5 per facet and method. Parameters are initial defaults,
  not calibrated; scores are not confidence probabilities.
- Deterministic title-conditioned query facets; no LLM or extraction claims.
- Candidate original block IDs are retained for the future Step 2 quote verifier.
- CSV compares BM25, dense, hybrid; blank relevance annotation is a pooled judging
  sheet, not a gold standard. Do not report accuracy/recall without independent labels.
  No evidence retrieval improvement has been established yet.

## Colab

Open notebooks/05_SAP_Hybrid_Retrieval_Colab.ipynb on generic-retrieval-v2.
It mounts Drive, reads the existing SAP_001_00.pdf (physical pages 4–21), runs two
previously configured target tables, writes six audit files, saves a timestamped
ZIP to the same private Drive folder by default and offers download. No API key.
For a different SAP, explicitly configure the page range and exact target titles.
Outputs contain original SAP text; share only if authorized. Do not commit them.

## Tests

Install with python -m pip install -e ".[notebook,test]" and numpy if needed.
Run python -m pytest -q tests/test_sap_hybrid_phase2.py tests/test_generic_library_phase1.py.
Tests use a deterministic fake encoder and synthetic PDF; the actual pretrained
model and target SAP are exercised in Colab. Existing legacy suite failures are
not suppressed or modified.
