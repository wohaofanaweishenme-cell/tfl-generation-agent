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
