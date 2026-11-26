# Phase 5.2 — Challenge batch diagnostic

Notebook 10 reads the Phase 5.1 benchmark ZIP from Drive. Cohort selection is
frozen before SAP predictions: all baseline failures, hybrid regressions, and
two deterministic correct table controls per study. Expected 21+1+12=34
cases for the current benchmark; report actual counts.

Preflight uses Content_List and Shell_Manifest source-region physical pages to
bound the candidate SAP body. It exports PDF previews and mapping diagnostics.
These bounds are NOT validated SAP body pages. Alternate PDF copies are not
assumed interchangeable. Explicitly confirm one PDF, body start/end, and API
authorization per study in the config cell. CPX and P-VCNA may lack usable body.
Leave unverified studies unconfigured; no API call is made for them.

Batch runs scope retrieval, specification extraction, Phase 4 per configured
study, reusing the study evidence across targets. Only title/type/registry ID
are passed, not expected labels or source shell content. Registry type conflicts
are preserved and reported. A study-level runtime failure is logged for all
its eligible cases; raw partial extraction may remain in the study folder.
Paired metrics use the identical completed cases for five methods. Operational
success includes attempted failures. Skips and attempted failures are exported.
No independent holdout or clinical accuracy claim. Output contains potentially
confidential text; share only if authorized.

The first run with empty configurations produces the cohort and local preflight
without API use. Review Page_Review.csv / the original PDFs, then set approved
configs and rerun batch. No need to rerun earlier experiments.
