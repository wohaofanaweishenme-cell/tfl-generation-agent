# Source identification checkpoint — P-VCNA-003

Current update after stage 2: the dependency limitation below is historical and resolved. Required identification validator rerun passed; see qa/Static_Validation_identification_rerun.json.

Stage: identification (v2.4). Source-only library; no DOCX outputs created.

| Measure | Count |
|---|---:|
| Supplied physical PDF pages examined for identification | 86 |
| Actual physical shells | 64 |
| Table / Figure / Listing | 25 / 2 / 37 |
| Embedded Content List entries | 132 |
| Direct shell mappings | 64 |
| No independent shell found in supplied file | 68 |

The original PDF and project brief are copied byte-for-byte into original/. Source IDs, source hashes, physical and printed page indices, 64 individual Source Records, raw page text, page images, and PDFKit line coordinates are persisted. Planned DOCX paths only; no shell duplication, merging, target adaptation, or automatic approval. Same-output panels and continuation pages stay together.

Printed pages 4–29 are absent from the supplied file. Conclusions cover the supplied 86 physical pages only. The appendix study-design image is not a TFL shell and has not been transcribed. All pages received extracted-text and rendered overview identification inspection; fine-resolution verification of every cell/footnote and clinical semantic QA are not_run. The source wording differences and Figure 14.2.6 reference conflict remain unchanged in evidence and issues. No approved style guide: future permitted_defaults=[].

Required package validator was invoked but could not start because python-docx is missing; pypdf is also unavailable. Dependency installation failed because the package host could not resolve. This is **not a validator pass**. The independent exact JSON Schema check passed 71 JSON files, plus source hash, 86-page coverage and region-bound checks.

To resume after dependencies are available:

```sh
python -m pip install -r requirements.txt
python tools/validate_study.py --study-root . --stage identification
```

Stage 2–5 have not run. Human approval remains pending.
