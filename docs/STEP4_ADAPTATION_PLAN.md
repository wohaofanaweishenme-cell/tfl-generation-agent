# Step 4 — Structure-Aware Adaptation Plan (Stage B.3, planning only)

## Scope and inputs

This implementation builds a **proposed** source-to-target adaptation plan for one Table. It does not alter the official Library, modify a DOCX, call an LLM, or certify statistical correctness.

Inputs:
- Previously extracted target Table `Specification` (with evidence references).
- Top-ranked or selected endpoint-compatible Step 3 source candidate.
- Authentic source `.docx` from the official `library/TFL_Template_Library/table/` directory.
- SHA-bound per-study `DOCX_Locator_Map/<template_id>.json`.

The target PDF shell pages are **not** used as input; they may be held out for evaluation. Six saved target Specifications from the user's previous audit ZIP are accessible to the Colab replay, not stored in the public repository.

## Three stages

**Source IR** (`agent/source_structure_parser.py`) verifies the DOCX SHA-256 and locator boundary; reads native Word table grids; records logical cells, bookmark names/positions, source row/header candidates, source footnotes, and original placeholders. Some studies use paragraph-based shells or generic `body` bookmarks; those remain uncertain candidates, not fabricated table coordinates. The parser never edits source bytes.

**Target Layout IR** (`agent/target_layout_builder.py`) converts the target Specification into treatment columns, required rows, proposed statistical subrows, statistical method and display-format candidates, footnotes, denominators, and evidence-reference IDs. Continuous and categorical classifications are heuristics and flagged for review. Missing categories, visits, denominators and footnotes are explicitly unresolved; source study details are **not** used to fill them.

**Adaptation Plan** (`agent/adaptation_planner.py`) aligns target and source structure. It returns proposed, evidence-linked operations, e.g.:

| Proposed action | Meaning |
|---|---|
| `REPLACE_TITLE` | Change source TFL identity to target identity |
| `KEEP_HEADER` / `REPLACE_HEADER_CANDIDATE` | Compare source and target treatment group columns |
| `INSERT_COLUMN_CANDIDATE` | Target needs a column absent from source (e.g., Overall) |
| `KEEP_ROW` / `REVIEW_ROW_LABEL_REPLACEMENT` | Same or potentially corresponding row labels |
| `INSERT_ROW_CANDIDATE` | Target requirement not matched to source |
| `REVIEW_SOURCE_ONLY_ROW` | Candidate source-only row; never delete automatically |
| `ALIGN_STATISTIC_SUBROWS` | Propose n/Mean/SD/etc. subrow hierarchy where target methods support it |
| `REVIEW_CATEGORY_LEVELS` | Categorical levels not extracted from target SAP |
| `REVIEW_CELL_FORMAT` | Proposed n (%), event-count display; precision still uncertain |
| `SEARCH_TARGET_FOOTNOTE_EVIDENCE` | Target footnote requirements absent; look for target support |
| `REVIEW_SOURCE_FOOTNOTE` | Source footnote must not be inherited automatically |
| `SEARCH_TARGET_DENOMINATOR_EVIDENCE` | Target-specific percentage denominator missing |
| `RESOLVE_TARGET_SPEC_GAP` | Any unresolved target Specification field |

Each operation contains `op_id`, `action`, `scope`, source anchor/coordinate (when available), target field, target `json_pointer` / evidence IDs, explanation, risks, and review status. **`execution_supported: false` for all operations.** A matching label is *not* evidence of identical clinical meaning.

## How to run

1. Open [06_Step4_Adaptation_Plans_Official_Library.ipynb](../notebooks/06_Step4_Adaptation_Plans_Official_Library.ipynb) in Colab.
2. Clone the development branch; the notebook automatically loads all 431 approved Library templates.
3. Mount the user's Google Drive PDF at `Colab Notebooks/agent/midterm demo/SAP_001_00.pdf`.
4. Load the existing `tfl_official_library_deepseek_audit.zip` from Drive or Colab upload. The ZIP contains six real target Table Specifications, so no DeepSeek call is necessary.
5. Run the planning cell. Download `step4_adaptation_plan_outputs.zip` containing per-TFL JSON plans and `adaptation_plan_summary.csv`.

Programmatic API:

```python
from tfl_agent.agent.adaptation_planner import build_adaptation_plan

# candidate is a Step-3 retrieval match with a real source_path,
# template.locator_map_path, template_id, and cross_endpoint flags.
plan = build_adaptation_plan(target_specification, selected_candidate)
assert plan["planning_status"] == "review_required"
assert plan["execution_status"] == "not_executed"
```

After running Steps 1–3 through `TFLSession`:

```python
summary = session.step4_build_adaptation_plan()
print(summary["path"])
```

The existing Step 4 draft generator remains separate. Plan JSON is saved under `adaptation_plans/`; the old draft construction plan is under `modification_plans/`.

## Validation and restrictions

- Hard fail on wrong source template ID, unverified locator boundary, changed SHA-256, or a Step-3 candidate explicitly flagged as a known cross-endpoint mismatch.
- Do not infer clinical equivalence from a similarity score. The structural source may differ from the highest-ranked candidate.
- Do not copy source footnotes, source patient population definitions, categories, or numerator/denominator rules into the target plan.
- Do not automatically delete source-only rows: an incomplete Step-2 Specification can omit clinically required rows.
- All plans remain `review_required`, `executable_without_review=false`, and `clinical_approval=false`.
- Source IR is read-only. Target Layout IR is a *planning proposal*, not a fully validated table shell.
- Listing and Figure planning remain unsupported in Stage B.3.

## Evaluation after planning

Use the source SAP body for extraction and planning, and compare final reviewed/generated Table shells against the target study's held-out original TFL shells. Evaluate row/column coverage, hierarchical statistics, footnotes, denominator definitions, and Word visual fidelity separately. Never interpret successful JSON schema validation as clinical correctness.

## Stage B.4 — Adaptation Planner v2

Enhancements added without modifying the official Library:

- Source IR v2: Word physical logical grid columns, grid-span/merge flags, hierarchy row IDs and parent IDs, title anchors favoring literal Table numbers, duplicate footnote grouping with original occurrences.
- Target Layout IR v2: explicit BOR categories CR/PR/SD/PD as reviewable child rows, unresolved categories retained, denominator applicability as required / not_applicable_for_current_spec / unknown.
- Semantic row alignment: normalized TEAE spelling and plurals, distinct clinical alias review, category aggregation review; no clinical equivalence is auto-approved.
- Layout compatibility: detects vertical Cohort/statistic axes (PFS), excessive source treatment columns, missing target row requirements (Hematology), and targets that require reconstruction.
- Physical column insertion: stores source table index, insert-after grid column and insertion physical grid index, separately from target column index; never equates header ordinal with Word column.
- Evidence statuses: missing, invalid, linked_unverified; presence of a provenance ID is not evidence that a row-level clinical edit has been proven.
- Plan 2.0 output: adaptation_mode, layout_compatibility, row_alignment, evidence_validation, executor_ready:false, plus all earlier proposed operations.

All v2 plans remain review_required with execution_supported:false. DOCX structural editing, clinical approval, and independent per-operation source quote validation are not implemented.

The standalone Colab 06 shows adaptation mode, row match counts and evidence gaps and exports plan-only JSON. Tests: tests/test_step4_adaptation_v2.py (real AE geometry, demographic hierarchy, PFS axis, BOR children, footnotes, missing evidence and incomplete Hematology).


## Stage B.5 — Adaptation Planner v3: evidence-gated, role-aware planning

This stage **does not generate or modify any DOCX files**. All operations
continue to have `execution_supported=false` and the plan has
`executor_ready=false`; a verified SAP quote is not clinical approval.

### Planning gate (`agent/planning_gate.py`)

`evaluate_target_completeness` classifies requirements by Table family
(Adverse Events, Demographics, PFS, Response, Disposition, Laboratory).
The gate reports `hard_blockers` and `review_items`. A target with
`readiness=blocked` always has `planning_gate.status=blocked`. Missing
rows, columns, or statistics are hard blockers. Unverified population,
categorical levels, footnotes, or denominator rules are separately reported.
A diagnostic Plan may still be produced for blocked inputs, but physical
edits may not execute.

### Column Role Matcher (`agent/column_roles.py`)

Source Word headers are classified as `treatment_arm_candidate`,
`overall`, `cohort_axis`, `statistic_or_measurement` or `unknown`
before matching. Source `Total` can match target `Overall` but must
NEVER be mapped to a Tenalisib treatment arm merely because it is the first
available header. An arm-to-arm text edit remains a candidate requiring
dose/patient-count review.

Proposed columns use `table_index`, `insert_after_physical_grid_index`
and `insertion_physical_grid_index`, all distinct from target ordinal
`target_column_index`. AE's proposed Overall insertion remains at
physical Word grid index 4 after source Arm II, not index 2.

### Row Hierarchy and Clinical Review (`source_structure_parser.py`,
`structure_alignment.py`, `target_layout_builder.py`)

The parser recognizes category children displayed in the first-column
(Race -> White/Asian; Sex -> Male/Female) and on the *same* Word row
(TEAEs by Severity -> Grade 1, with Grades 2–5 underneath).
Statistical subrows (Age -> n/Mean/SD) retain parent IDs.

- `Gender` vs `Sex` produces `domain_synonym_requires_review`, not
  a silently approved clinical equivalence.
- `Grade >=3`, `Grade >= 3`, `Grade ≥3` and `Grade ≥ 3` match a
  source severity family with Grades 3–5 only as
  `aggregation_candidate`. It explicitly prohibits summing patient
  counts across grades; a patient-level union is needed. Related Grade >=3
  is NOT matched to an unrelated severity-only source group.
- BOR's explicit CR/PR/SD/PD children are aligned individually. When all
  four are matched, its parent becomes `MATCH_GROUP`, not an additional
  `INSERT_ROW_CANDIDATE`.

### Read-only SAP Evidence Resolver (`agent/target_evidence_resolver.py`)

The optional `parsed_sap_blocks` and `sap_body_page_range` inputs
verify cached target-SAP quotations against the **explicitly permitted**
SAP body pages. This study uses physical pages 4–21 (not the target
study's held-out shell pages). A quote's presence in a block establishes
only textual provenance, not support for a proposed clinical/statistical
edit. Missing footnotes, percentage denominators, and other requirements
return ranked *candidate* SAP body blocks, without modifying the
Specification. Source-study footnotes are never copied.

Call after Step 3:

```python
result = session.step4_build_adaptation_plan(
    parsed_sap_blocks=saved_parsed_sap_blocks,
    sap_body_page_range=(4, 21),
)
```

The v3 plan JSON adds `planning_gate`, `column_alignment`, and
`target_evidence_lookup` (or null without saved SAP blocks). It keeps
the v2 Source IR, Target IR and operation list.

### Testing and limits

Run:
```bash
python -m pytest -q tests/test_step4_official_draft.py tests/test_step4_adaptation_planner.py tests/test_step4_adaptation_v2.py tests/test_step4_adaptation_v3.py
```

The focused official-library workflow passed **44 tests** after these
changes. Separate full-project legacy demo fixture tests still fail from
mismatches between legacy fixtures and the official 431-template Library;
that broader issue is outside this milestone.

Not implemented: LLM-based clinical relation adjudication, updating
Specifications from candidates, independent semantic validation of each
operation against SAP evidence, human approval UI, OOXML document editing,
or evidence-backed final clinical approval.


## Stage B.6 — Section-aware Evidence Retrieval + manual DOCX text executor

**Section-aware evidence retrieval** (target_evidence_resolver.py):
- The resolver detects numbered SAP headings and tracks each body's current section.
- Target families prioritize their corresponding sections: AE 8.8.2,
  Demographics 8.4, Disposition 8.1, Response/PFS 8.7.2, Hematology 8.8.3.
- It prefers a relevant section and its close neighboring paragraphs over
  generic Section 7.1 methodology; abbreviation glossaries are excluded.
- It **never** reads outside explicitly supplied body pages (this demo: 4–21).
- Results contain section_id, source_section_relevance and ranking_score;
  they are still **candidates**, not confirmed table-specific footnotes.

**Operation readiness** (operation_readiness.py):
- Every operation contains operation_readiness.status, missing preconditions,
  and whether its action type could be handled by the minimal executor.
- Targets with planning_gate.status = blocked are **diagnostic-only**.
  Their INSERT/REPLACE/KEEP proposals are demoted to DIAGNOSTIC_* operations;
  original mapping hypotheses remain auditable in row_alignment and
  column_alignment.
- A nonblocked plan also remains executor_ready=false. There is **no**
  automatic "approve" action.

**Strict minimal Word executor** (docx_text_executor.py):
- The only supported actions are REPLACE_TITLE and
  REPLACE_HEADER_CANDIDATE, never rows, columns, footnotes or statistics.
- A reviewer must explicitly edit a **pending** approval packet to provide
  a named reviewer, approve specific op_ids, and choose an allowed exact
  replacement_text. A packet is bound to the SHA-256 of both the source DOCX
  and the full JSON plan; stale packets fail.
- It verifies a single unambiguous Word bookmark span, checks bookmarked
  source text against the plan, and writes only a **new DOCX outside the
  Library template directory**. Original source SHA-256 is checked again.
- Source N=xx placeholders may be preserved only when already present in
  that header; no patient N or statistical value is invented.
- Report status is text_edits_applied_to_unapproved_copy and clinical_approval
  is always false. Rendered page review and actual clinical TFL validation
  remain explicitly unfinished.

### Usage in Colab

1. Run Notebook 06 (plan-only) using the saved DeepSeek Audit ZIP. The output
   includes per-table adaptation-plan-v4 JSON and
   <TFL_ID>_review_packet_PENDING.json. No Word changes occur here.
2. Open Notebook 07_Step4_Approved_Text_Executor.ipynb, upload the plan ZIP,
   select the target, inspect the pending review packet.
3. A qualified reviewer manually sets reviewer and selectively marks an
   operation approved with one of the listed allowed_replacement_texts;
   other entries remain pending. Upload the resulting *separate* JSON file.
4. The executor checks the precise source, Plan digest, bookmark and approval
   before saving one Word copy plus its JSON audit report. It never changes
   a source Library DOCX.

Python API:

```python
from tfl_agent.agent.docx_text_executor import (
    build_pending_review_packet, execute_approved_docx_edits,
)
pending = build_pending_review_packet(plan)    # never preapproved
# Explicit external review/edit of pending -> approved_packet required here.
report = execute_approved_docx_edits(
    plan, approved_packet,
    source_docx="library/TFL_Template_Library/table/<source>.docx",
    output_docx="outputs/TFL_REVIEW_REQUIRED.docx",
)
```

The actual target Table Shell remains incomplete after the minimal executor
unless its rows, columns, footnotes, statistical methods, and formatting are
separately verified. **Do not use the resulting DOCX as a final clinical TFL.**

Focused regression suite:
```bash
python -m pytest -q tests/test_step4_official_draft.py tests/test_step4_adaptation_planner.py tests/test_step4_adaptation_v2.py tests/test_step4_adaptation_v3.py tests/test_step4_adaptation_v4.py
```


## Stage B.7 — Zero-approval automatic **unapproved** text previews

The six real v4 Plans produced **only three pending text-eligible operations
and all three are in AE Table 14.3.1.1**: one title and two Tenalisib arm
labels. All other five pending review packets are empty because the source
layout must be rebuilt or the target Specification is blocked. Human approval
of these three text fields is not the principal barrier to end-to-end shell
generation.

To avoid one-by-one approval **during prototype/demonstration**, use:

- [Notebook 08 — Batch Auto Text Drafts](../notebooks/08_Step4_Batch_Auto_Text_Drafts.ipynb).
- Input: Notebook 06 \`step4_adaptation_plan_outputs.zip\`; no DeepSeek call.
- Source: \`src/tfl_agent/agent/auto_text_draft.py\`.
- Output: one summary CSV, one risk/exception JSON per table, and an unapproved
  text-only DOCX **copy** where deterministic checks permit edits.

This is an *automatic draft mode*, not a bypass that forges human approval.
It does not use, modify or auto-fill the manual approval packets required by
Notebook 07. Each preview edit verifies the source SHA-256, the source Table
ID, the unique Word bookmark, and the exact source text. A treatment-arm
header additionally requires that the same target arm name occurs literally
in a **verified target SAP-body quote**. Generic \`N=xx\` placeholders may be
preserved; patient counts are never invented. If any check fails, it skips
that particular edit. Blocked or rebuild-mode plans generate **no** Word
output; they instead yield a diagnostic report.

All generated text copies are named
\`Table_<id>_AUTO_TEXT_PREVIEW_UNAPPROVED.docx\`, with
\`auto_approval_performed=false\`, \`clinical_approval=false\`,
\`shell_complete=false\`, and \`word_layout_validated=false\`. The source
Library is never overwritten. The exception report retains unperformed
INSERT_ROW, INSERT_COLUMN, footnote, denominator and statistical-method
operations.

The strict human-approved Notebook 07 remains optional for formal review
workflows. **Notebook 08 is recommended for the classroom MVP**, but its
text-only preview does NOT replace a structure-aware DOCX Executor. To make
the final project truly end-to-end, next prioritize generating/editing missing
rows and Overall columns, target-SAP-based footnotes, and systematic
post-generation verification.

Test suite includes:
\`tests/test_step4_auto_text_draft.py\` (synthetic and actual AE source Word
bookmarks, evidence-gated labels, zero approvals, source integrity and
blocked/incompatible skip behavior).
