# Phase 3 — Evidence-linked candidate specification extraction

Run notebooks/07_Scoped_Specification_DeepSeek_Colab.ipynb on generic-retrieval-v2.
Same Drive input, physical SAP body pages, and two demo target tables. Rebuilds
Phase 2.1 once (no Phase 2 comparison), then uses DeepSeekJSONClient with
DEEPSEEK_API_KEY in Colab Secrets. Real API requests are billed. Only proceed if
authorized to send confidential SAP excerpts to the provider. No key in GitHub.

One study-level and one target-level extraction per target, with at most one
missing-field completion call per scope. For two targets, 3–6 logical LLM calls
(excluding underlying API retries). Supplemental BM25/dense/RRF retrieval uses
the existing scoped chunks and keeps known other endpoints out of the pool.
Existing accepted fields are not overwritten by completion.

Each claim must have a literal value (or limited alias) and an exact quote in a
supplied chunk. Original source offsets are reconstructed and preserved.
Known scope mismatch, unclassified context, conflicting target population and
other output type evidence are kept for review, not automatically accepted.
Scope/lexical checks are NOT a semantic entailment model or clinical review;
a quote can be real but misleading. Output type checks are conservative and
may over-reject mixed sentences. Missing fields stay unresolved; no template
defaults or forced layout.

Outputs: Study_Settings.json (candidate envelope, deliberately NOT confirmed
Generic Library settings), TFL_Requirements.json, Study_Extraction_Audit.json,
TFL_Extraction_Audit.json and Summary.json. Retrieval evidence is included
under Retrieval/. All claims have clinical_confirmation=false; shell generation
is not authorized. No automatic human confirmation. The next phase will consume
candidate facts and preserve review flags. Existing legacy session and libraries
are unchanged.

Tests use synthetic claims; real DeepSeek extraction and clinical relevance
are evaluated in the user's Colab. Test command:
python -m pytest -q tests/test_scoped_specification_phase3.py tests/test_sap_scope_phase21.py tests/test_sap_hybrid_phase2.py tests/test_generic_library_phase1.py
