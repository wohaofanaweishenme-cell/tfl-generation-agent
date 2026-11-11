# Source metadata checkpoint — P-VCNA-003

Study_Metadata.json uses the exact v2.4 root: schema_version, library_id, templates. It contains 64 actual-source records tied to 64 existing DOCX files. Source types remain 25 Table, 2 Figure, 37 Listing; actual structural families remain 23 table, 2 figure, 39 listing. No directory-only outputs were created or expanded.

73 individual physical footnotes were preserved without changing IDs, original text, markers, display order or existing typed physical applicability. They now contain 112 agent-authored source-supported semantic clauses. Repeated physical footnotes remain separate records. Rule-specific inferred scopes are marked as inferred and do not overwrite physical scope. Unresolved physical note applicability remains explicit.

The dose-exposure shell retains separate general column-N and dose-reduction-patient denominator rules; table_spec.denominator_rule stays null rather than flattening those differences. Count/event/patient display concepts are distinct. Source coding-version placeholders are not guessed. No target-study rules or approved defaults were introduced.

Identity, specification, actual DOCX boundary, occurrence bookmarks, source text, repeated positions, and documented unlocated wrapper occurrences were copied from the persisted structures and Locator Maps. Keywords/aliases and retrieval_text are source-supported indexing summaries, not embeddings or a retrieval contract. All actual DOCX hashes and prior physical structures were independently compared with the stage-3 input snapshot and remain unchanged.

The supplied file lacks original printed SAP pages 4–29. Shell display statements are not labelled as SAP-body statistical definitions. Endpoint types, source dataset variables, and unsupplied analysis settings remain explicitly not_found/unreviewed as appropriate.

An additional potential source inconsistency was found: the OS table defines survival from randomization, whereas the actual OS figure axis says Time Post-Dose (months). Both evidence texts are stored without choosing a preferred origin. The existing Figure 14.2.6 numbering/title inconsistency and directory/shell wording variants are also retained.

56 records complete current extraction; 8 remain for source/physical review (the earlier 7 plus the OS figure). All 64 quality.review_status values are pending. Full study completion remains false; independent semantic review is not_run, and there is no human approval. Stage 5 final QA has not been executed.

The actual JSON Schema validation passed, and the required validator --stage metadata returned pass_with_review_warnings with zero errors. The 900 technical warnings represent 300 intentionally excluded corporate wrapper occurrences in three layers, not 900 missing clinical elements. Scope/source-review issues remain in Metadata_Issues.json and per-template issues; static success does not resolve them.

Main records: Study_Metadata.json, qa/Metadata_Issues.json, qa/Footnote_Semantic_Extraction.json, qa/Metadata_Parity_Check.json, qa/Static_Validation_metadata.json and qa/Extraction_Progress.json. Raw pre-metadata structures/maps remain under checkpoints/Metadata_Input_Snapshot/.
