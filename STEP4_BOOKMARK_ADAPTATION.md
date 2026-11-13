# Step 4 — Verified Bookmark DOCX Adaptation (Stage B.1)

This extends the five-step Agent architecture without modifying Steps 1–3 or any teammate-maintained files under library/. It creates **auditable Table DOCX drafts**, not approved clinical/statistical shells.

## Source and safety checks

- Read the original DOCX and its source-authored v2.4 DOCX_Locator_Map/<template_id>.json, both read-only.
- Verify the locator boundary status, template ID, and exact SHA-256 of the source DOCX.
- Resolve each source occurrence to a verified unique Word bookmark. Verify its XML start/end and the exact expected source text before changing any text.
- Edit only a simple bounded title, treatment-header, body-cell, or footnote occurrence. No blind document-wide search and replace.
- The target's requested rows, columns, and footnotes must remain visible after edits; unmapped items block generation.
- Source-only statistical footnotes must not silently carry over to an unrelated target; require explicit reviewed edits.
- Reject unsupported merges, insertions, row/column changes and nested/cross-parent bookmark ranges. Never fabricate observed data.

The agent proposes one title change from the Step 2 specification automatically. Header, body, and footnote differences require separately reviewed, bookmark-addressed changes. The original source file is never saved or overwritten; only a new DOCX is written under output/.

**Source contamination warning:** Original study logos, corporate attribution, programming notes, source lines, and original study metadata may remain. Stage B.1 does not automatically remove/rewrite them, and every generated document is marked **draft_needs_review**. A structural validity check is not clinical approval.

## Automatically export an unapproved review scaffold

After Step 3, call session.export_bookmark_review_scaffold(). This works even when Step 3 appropriately leaves selected_template_id null. It writes a JSON file under output/<target>/review_scaffolds/ listing the original title/header/body/footnote bookmarks beside the requested target requirements. The output starts with blank reviewer fields and an empty edits list; no automatic semantic source-to-target mapping is inferred. The real-study Colab notebook now displays a download link to this file. Review and complete this JSON outside library/ before providing it as reviewed_adaptation.

## Review-gated candidate selection

When Step 3 reports retrieved_needs_adaptation_review (including the real Demographics case with heuristic retrieval score 0.8108), selected_template_id remains null. To draft from that candidate, supply an **explicit, standalone review record**, not edits to the Library:

~~~python
reviewed = {
    "template_id": "SOURCE_TEMPLATE_ID",
    "tfl_id": "14.1.3.1",
    "reviewed_by": "Name or role of reviewer",
    "review_reason": "Reason for using the different source population",
    "edits": [
        {
            "bookmark": "O_O00004",
            "expected_source_text": "Exact text from source locator map",
            "new_text": "Reviewed text from target SAP",
            "reason": "Verified SAP evidence for this header change"
        }
    ]
}
session = TFLSession(
    # ... usual parameters ...
    allow_review=True,
    reviewed_adaptation=reviewed,
)
session.step1_parse()
session.step2_build_specification()
session.step3_retrieve_templates()
print(session.preview_modification_plan())
result = session.step4_generate_shell()
report = session.step5_validate_and_export()
~~~

The example strings above are illustrative, not a real approved mapping. Real changes must use the exact verified occurrence source text and supporting target SAP evidence. Manual review is an explicit user input and **is not automatically inferred from a high retrieval score**. Step 2 readiness=blocked always blocks generation; readiness=needs_review requires allow_review=True.

## Output and limitations

The usual modification plan JSON now includes editing_mode, proposed verified edits, issues, warnings, source_sha256, output_sha256, and applied_bookmarks. Step 5 validates the output and records any failures, but even a technically valid adaptation remains draft_needs_review.

This first implementation does **not** handle insertion/deletion/reordering of rows or columns, merged-cell restructuring, end-to-end population/denominator reasoning, source-branding cleanup, or Figure/Listing adaptation. The real P-VCNA-003 demographics document needs a reviewer-authored mapping and visual QA; a score of 0.8108 alone is insufficient.

## Regression tests

~~~bash
python -m pytest -q tests/test_step4_bookmark_adapter.py tests/test_session.py tests/test_study_library_compatibility.py
~~~

All new test fixtures are synthetic. Existing placeholder-based demo generation remains supported. Do not commit real SAP excerpts, model outputs, or manually reviewed confidential adaptation inputs to the public repository.
