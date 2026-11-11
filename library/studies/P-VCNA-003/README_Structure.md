# Structure extraction checkpoint — P-VCNA-003

Stage 2 only. No DOCX, plot or target-study output generated.

| Measure | Count |
|---|---:|
| Physical manifest shells / structure records | 64 / 64 |
| Structural extraction complete / needs review | 57 / 7 |
| Physical cells / blank physical cells | 3327 / 985 |
| Physical footnotes | 73 |
| Source output types: Table / Figure / Listing | 25 / 2 / 37 |
| Structural families: table / figure / listing | 23 / 2 / 39 |

Every shell has a persisted Structured_Shell JSON. Physical text blocks cover all source PDFKit tokens in each owned source region, with zero missing/extra token counts. Native columns, example rows, empty continuation cells, placeholders, source ordering, observed spanning headers, separate source/programming/form-footer text and panel/page ownership are retained. Superscript/font and line/character evidence are retained in checkpoints. Blank stubs are never filled down; unlabeled result-only rows retain no inferred statistical owner.

The figures are text specification boxes in the source and remain description mode. No plot frame, curve, data or executable code was added. Source programming instructions about other outputs remain notes only.

## Remaining physical review items

| Template ID | Reason |
|---|---|
| `PVCNA003_L_16_2_19` | Sparse alternating example lines; no unseen rowspans or fill-down asserted. |
| `PVCNA003_L_16_2_6_1` | Second example row is visibly inconsistent with some headers; original preserved, not repaired. |
| `PVCNA003_L_16_2_7_1` | Paired AE panels and superscript Yes1 need final physical typography review. |
| `PVCNA003_T_14_2_1_1` | p-value placeholder is not vertically aligned with its statistical row label; no row ownership inferred. |
| `PVCNA003_T_14_3_10` | Multi-page nested treatment sections and [a]/[b]/[c] marker scopes need final physical confirmation. |
| `PVCNA003_T_14_3_1_1` | Unlabelled source placeholder rows retained; confirm intended physical row treatment. |
| `PVCNA003_T_14_3_2_1` | Paired listing-like table panels, note-only continuation and superscript Yes1 need final physical typography review. |

Footnote semantic_extraction_status remains needs_review with semantic_rules=[] as permitted in stage 2. Explicit *, **, [a], [b], [c] marker associations link to persisted row IDs where source-supported; other scopes remain typed unknown/unresolved. Independent final visual/clinical QA is not_run. Extraction completion is not approval.

## Validation

Required package validator: structure pass_with_review_warnings, zero errors; all 64 structure records checked. Warnings identify 5,982 unverified source occurrences with null DOCX locators before stage 3. Identification was also rerun successfully (pass, zero errors/warnings). Earlier dependency failure is resolved and its historical log retained.

## Reproduction

Run tools/extract_word_coordinates.swift and tools/extract_pdf_geometry.py to regenerate coordinate checkpoints, then tools/build_structures.py, tools/enrich_structure_hierarchy.py, tools/audit_structure_coverage.py, tools/finalize_structure_checkpoint.py and tools/link_placeholder_blocks.py. The geometry plan is explicitly agent-authored and source-specific. It is not a generic visual extractor and does not supply clinical facts.

Corporate header/footer text remains separately identified for traceability. Corporate logo graphics are treated as wrapper images, excluded from clinical shell content consistently; source page PNGs preserve them. No substantive source figure image was excluded.
