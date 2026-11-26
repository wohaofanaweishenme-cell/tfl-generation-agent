# Generic Retrieval v2 — Phase 1

## Scope

This branch adds an opt-in, read-only adapter for the approved Generic TFL Library.
The original TFLSession, source Library, generic library definitions, and main branch
are unchanged. The new baseline copies the teammate's title-only matching logic at
commit 00c0c91d1cddc6260855d771cc5afda894e0c407 verbatim (including ambiguity and rejection rules).

This is not yet a SAP-aware retriever, and does not authorize shell generation.
Phase 1 intentionally does not assign scores to SAP evidence or infer study settings.

## Run in Colab

Open notebooks/04_Generic_Library_Baseline.ipynb on this branch. No SAP, Google Drive
or API key is needed for the offline in-library evaluation.

## Run locally

```sh
git clone --branch generic-retrieval-v2 --depth 1 https://github.com/wohaofanaweishenme-cell/tfl-generation-agent.git
cd tfl-generation-agent
python -m pip install -e ".[test]"
python -m pytest -q tests/test_generic_library_phase1.py
python -m tfl_agent.agent.generic_evaluation --repo-root . --out output/generic_phase1
```

The published reference is 410/431 labelled entries (95.1%); 775 total entries.
Do not report successful reproduction until the benchmark has actually run and
matched the stored summary. The 344 entries without a directly linked source shell
are not labelled and are excluded from accuracy. This is not a held-out evaluation.

## Interfaces

- GenericLibrary: validate template/preset/style hashes against approval and index,
  check identity, keyword references and index metadata, return authoritative JSON.
- retrieve_generic_baseline: rank title/type, return selected IDs, candidates and
  rationale. Always marks generation_authorized=false and sap_evidence_used=false.
- entry_from_spec: convert the legacy target specification identity to a title-only
  entry, without claiming any extracted population is verified.

## Next phases (not implemented here)

1. SAP section-aware chunking, BM25 and dense retrieval with citation traceability.
2. Study-level and TFL-level evidence extraction and scoped verification.
3. SAP-aware reranking and gap analysis; evaluate against this frozen baseline.
4. Pass selected IDs and validated settings into the generic builder/renderer.

The existing legacy tests have assumptions about the older Library layout (one fixture
at the root and per-study DOCX folders). They are not changed here and may fail against
the already-centralized original source library. Use the targeted Phase 1 tests above.
