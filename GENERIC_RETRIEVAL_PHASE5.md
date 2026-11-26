# Phase 5 — Evaluation protocol (part 1)

Run Notebook 09. It reproduces the 431 labelled in-library cases and runs
title-only dense and title-only keyword+dense on exactly those same cases.
The 21 original failures are exported with original PDF paths where present.
These are development diagnostics, not independent test data. The title-only
methods force a ranked candidate; ranking metrics and selection/abstention
metrics are reported separately. No claim that title-only is SAP-aware.

The previous two Phase 4 targets are optionally evaluated against explicitly
provisional expected template IDs, with four methods on the same saved result.
No new DeepSeek calls. No preset ground truth is asserted.

Challenge SAP experiment is not run automatically: original PDFs may be
incomplete or contain only shells. Confirm physical SAP body pages and the
source mapping for each study before any extraction. Never index reference
shell pages. The manifest intentionally leaves body bounds blank.

For next experiment, freeze code/library, select an external study not used
to build the generic library, confirm exact output titles/types and label
template/preset and required atomic facts from source shell/SAP independently
of predictions. Report all attempts, missing evidence and abstentions, same
cases for all methods. Do not tune weights on this held-out set. Requirement
coverage requires independent fact labels, not count of accepted LLM claims.
No generation or library modification.
