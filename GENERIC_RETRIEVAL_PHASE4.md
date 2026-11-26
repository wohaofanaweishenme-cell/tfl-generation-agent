# Phase 4 — SAP-aware template and preset retrieval

Run notebooks/08_SAP_Aware_Template_Retrieval_Colab.ipynb.
Reads the existing Phase3_Outputs ZIP from Drive (latest timestamp by default;
change ZIP_NAME to choose a specific run). Validates the saved artifact's SAP
hash against the current Drive PDF. Does not call DeepSeek or regenerate SAP
retrieval. Local BGE encoder downloads weights only.

- Normalize accepted Phase 3 claims into canonical statistic/method/variable
  features, retain exact claim references; keep reporting dimensions separate
  from layout. Flag unextracted enumerations for review, not automatic addition.
- Retrieve across all approved templates of the requested output type and their
  presets. Use actual Keyword_Index phrase matches and dense cosine (title and
  SAP requirements); re-rank by structural signature and statistical
  capability crosswalk, with independent preset signals. Weights 20/25/25/20/10
  are provisional, renormalized for unknown components. Strong contradictions
  in explicit structural evidence gate selection; low scores and small margins
  are review conditions. No inferred output-type change. Scores are heuristic,
  not probabilities. All candidates remain in the audit.
- Report title rule baseline, title-only dense, keyword+dense without
  structure, and SAP-aware ranked candidates. These are diagnostic comparisons,
  not a controlled held-out evaluation or proof of improvement.
- Gap Analysis compares actual preset variable labels/statistic rows and
  template required slots; keep means candidate match, add means candidate
  addition, modify means candidate setting, review means unresolved. Never
  remove absent SAP variables automatically. Study-level groups and general
  rules remain unconfirmed; no shell generation or library mutation.
- Coverage pattern is limited to explicit "characteristics will include"
  enumerations, not a general completeness proof. Structure and statistics
  crosswalks are limited; unsupported layouts, preset semantics and mixed
  output types require review. Figure/listing selection is not independently
  validated. Generic renderer integration is deferred.
- Outputs: Summary.json, Normalized_Requirements.json, Template_Retrieval.json,
  Candidate_Rankings.csv, Gap_Analysis.json. Confidential SAP claim text may be
  included, share only with authorization. Phase 3 artifacts stay private.

Tests: python -m pytest -q tests/test_sap_aware_retrieval_phase4.py
