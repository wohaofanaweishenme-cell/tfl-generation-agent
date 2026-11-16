# Six-study source-template Library

Current baseline: 431 approved source templates, 0 pending; 208 Tables, 203 Listings,
20 Figures. The global keyword index covers all 431 IDs with 435 indexed terms.
Source limitations, needs_review, historical not_run and original approval evidence remain.
Approval is for source-template Library use; it is not a declaration that all QA passed,
that source ambiguities were resolved, or that Figure plotting is implemented.

## Layout

- `TFL_Template_Library/{table,listing,figure}/`: the **single centralized set of 431 physical DOCX files**.
- `studies/<study_id>/Study_Metadata.json`: full authoritative per-study Metadata records.
- `studies/<study_id>/source_registry/`: necessary source inventories, records and source locations.
- `studies/<study_id>/intermediate/`: Structured Shells and DOCX Locator Maps.
- `studies/<study_id>/qa/`: current QA, approval evidence and specifically referenced history.
- `studies/<study_id>/original/`: source PDFs required for provenance.
- `Study_Metadata.json`: existing unified derived Metadata, with the original schema and fields.
- `All_Study_Metadata.json`: Git symbolic alias to the identical unified Metadata.
- `Template_Index.json`, `Metadata_Index.json`, `Keyword_Index.json`, `Library_Registry.json`: current unified registration and indexes.
- `approved_view/Study_Metadata.json`: approved-source Metadata view, retained separately.
- `approved_view/TFL_Template_Library`: directory link to the centralized DOCX collection.
- `metadata/Template_Metadata.json`, `index/Keyword_Index.json`, `templates`: aliases/derived keyword wrapper preserving the existing repository directory categories.
- `publication/`: relocation map, export hashes and publication checks; these are derived audit records, not another approval authority.

All current DOCX indexes point to the centralized location. No current source DOCX is
physically stored separately inside the Study folders. Metadata `identity.file_path`
is relative to the shared `TFL_Template_Library/`; study-specific Metadata remains
referenced by the unified Metadata_Index. Approval-view membership is the current
approved collection, not a new independent manual list.

## Deduplication and compatibility

Git symbolic links avoid duplicate DOCX entities while preserving unified and approved
view paths. On Linux/macOS/Colab, use a normal `git clone` to materialize the links.
GitHub's ZIP download or Windows configurations that do not restore symlinks can expose
link text instead of linked files; the physical canonical DOCX collection is always
`TFL_Template_Library/`. The repository's pre-existing `metadata/`, `index/` and `templates`
entry names are preserved. No agent code or notebook is modified by this update.

`index/Keyword_Index.json` is a derived compatibility wrapper around the same root
keyword mapping. It is not independently maintained. Source/template approval does not
grant automatic target-study adaptation. Direct single-Study loaders that assume a
private DOCX directory must instead select the shared Library and filter by study;
no reading-code changes are included in this Library-only update.

## Evidence and historical records

Unreferenced old checkpoints, backups, caches, repetitive renders and process logs are
omitted. Specifically referenced approval and unresolved-issue evidence is retained,
including necessary files inside historical folders. Differing workspace copies are
preserved as attributed evidence in `publication/local_evidence/`, rather than replacing
the registered current records. Historical evidence text is preserved verbatim.

`publication/Path_Map.json` resolves original project-relative locations to published
files. The original project-root string there is provenance only, not a required runtime
path. Current operational JSON paths use lowercase `library/` and repository-relative
locations. `publication/Export_Manifest.json` records original and export hashes; metadata
was compacted and operational paths relocated without changing clinical content or approvals.
Old metadata-hash statements inside historical QA describe their original records;
they are not rewritten to pretend a new historical verification occurred.

## Scope

Figure source DOCX templates are included. `Figure_Development/` code, plotting configs,
synthetic test data and generated plots are **not included**. No source extraction,
DOCX rebuilding, rendering, semantic re-review or approval was performed in this sync.
The original local project and its complete construction history remain unchanged.
