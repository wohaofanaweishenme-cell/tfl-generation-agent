# Phase 2.1 — Scope-aware SAP retrieval

This additive pilot retains Phase 2 and its notebook. It repairs section metadata
using numbered headings at the start of blocks, inline uppercase major headings,
and explicit colon-labelled endpoint anchors. Repeated page-edge boilerplate is
excluded from the index but preserved in SAP_Blocks.json and Section_Audit.json.
Every fragment and chunk retains exact offsets into the original normalized PDF
block. Scope identification is heuristic, not validated clinical applicability.

Study-level retrieval uses six independent queries (groups, populations, general
statistics, missing data, subgroups, visits). When recognized sections are present,
search is restricted to them; otherwise unclassified non-topic evidence is searched
and marked fallback. Target retrieval prioritizes matching explicitly scoped chunks,
keeps unclassified evidence in a separate context pool, and audits exclusions.
No LLM extraction, clinical confirmation, or template selection is performed.
Scope rules may miss unfamiliar headings/endpoint names; unknown context must not
be silently treated as target evidence. Generic study rules still require downstream
applicability validation.

Run notebooks/06_SAP_Scope_Retrieval_Colab.ipynb. Same Drive SAP and target IDs
as Phase 2. The notebook also runs the unchanged unrestricted baseline using the
same encoder and parameters. Output ZIP includes original blocks, scoped segments,
chunks, section audit, evidence packages, retrieval CSV and Phase2_Baseline/.
Output contains confidential SAP text; share only if authorized. No API key required.
Tests: python -m pytest -q tests/test_sap_scope_phase21.py tests/test_sap_hybrid_phase2.py tests/test_generic_library_phase1.py
