# Step 2 / Step 3 — Evidence validation and template retrieval (midterm MVP)

## Scope

This update changes **source-evidence post-processing** and **template retrieval**. It does **not** train an embedding index, overwrite the P-VCNA-003 study library, implement Word bookmark editing, or certify clinical/statistical correctness.

### Step 2: verify, don't guess

1. A SAP text excerpt is valid only if `block_id` exists among the retrieved blocks and `exact_quote` is an exact substring. Missing or invalid citations are not rescued.
2. When a **verified quote literally enumerates several values in the same array field**, uncited sibling values may reuse that exact quote *only if the full normalized value (or a limited predefined alias) occurs in it*. Every accepted item gets its own provenance field-link and a `normalized` derivation. Arbitrary other text in the same block cannot support a value.
3. Table category determines whether `endpoint_name` is mandatory. Demographics, safety and disposition summaries may legitimately have `endpoint_name: null`. Endpoint analyses still require an endpoint.
4. When the target title explicitly says ITT/PP/Safety, contradictory population entries from generic SAP passages are excluded with a review issue and renumbered provenance links. If target population is not specified and multiple populations remain, the result is flagged as ambiguous rather than guessed.
5. The final `readiness` can remain `needs_review` despite passing JSON Schema. A missing explicit SAP footnote and general-versus-target-output scope limitations are not automatically resolved.

Saved raw LLM responses can be replayed offline by importing `build_specification_from_extraction` from `tfl_agent.agent.step2_spec_builder`. The ZIP of real API audit records stays outside the GitHub repository.

### Step 3: rank what the table *does*

Candidate features, deterministic and auditable (not calibrated probabilities):

| Feature | Weight |
| --- | ---: |
| Named Table family (demographics, time-to-event, AE, etc.) | 45% |
| Informative title similarity (stopwords suppressed) | 27% |
| Requested statistics overlap with source `table_spec.statistics` / row labels | 13% |
| Statistical method similarity | 10% |
| Analysis-population match | 5% |

A clearly mismatched **Table family** is excluded. Time-to-event PFS and OS may appear as structurally related candidates, **but a different known endpoint cannot be auto-selected**, even with a high score. Population differences are disclosed as required adaptation, not treated as equivalence. Keep the 0.55 minimum threshold and 0.04 top-two margin for automatic selection; neither number represents model confidence.

### Regression checks

Synthetic tests cover: exact enumeration citations (including rejection of unsupported values), invalid block/quote, ITT-vs-PP population scoping and pointer integrity, demographics vs AE ranking, and PFS-vs-OS manual-review safety. Additional integration tests inspect **the actual P-VCNA-003 library** when it is available in the GitHub checkout.

Offline replay of the user's saved November midterm run (without calling DeepSeek):

- `14.1.3.1` demographics: `statistics_to_display` **2 → 8**; `variables_to_display` **2 → 11**; readiness **blocked → needs_review**.
- `14.2.3.1` PFS: **ITT-only population** when the requested title explicitly includes “ITT Analysis Set”; remains **needs_review**.

**Do not claim these changes resolve all Table-level scope errors**. In particular, PFS-rate, subgroup, listing and curve details from a general SAP section may still require separate review, and Step 4 bookmark-based DOCX adaptation is not implemented.

## Run from Colab

Reopen `notebooks/03_Real_Study_DeepSeek_Colab.ipynb` from GitHub and run the initialization cell to pull and reinstall the latest package. The target PDF stays in your private Google Drive. Choose exact Table titles including analysis populations, and continue using a SAP-body-only page range. No API key or real SAP is committed to GitHub.
