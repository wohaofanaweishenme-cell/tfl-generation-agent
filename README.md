# TFL Generation Agent (Midterm MVP)

[![Open Midterm Demo in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/wohaofanaweishenme-cell/tfl-generation-agent/blob/main/notebooks/02_Midterm_Demo_GitHub_Colab.ipynb)

A **Python package plus Jupyter/Colab notebooks** for a clinical-trial TFL (Tables, Figures, Listings) shell-generation research project. The current *midterm MVP* demonstrates the pipeline from a Statistical Analysis Plan (SAP) to **one editable Table shell**, with evidence references, template retrieval, and automated checks.

> **Research prototype — not validated for clinical or regulatory use.** The included SAP, template library, and default LLM response are **synthetic fixtures**. A successful fixture run demonstrates software integration, **not** real-world model extraction accuracy or statistical correctness.

## At a glance

**Input:** SAP PDF + a target TFL ID/title + an indexed template library  
**Pipeline:** Parse SAP → Extract evidence-backed specification → Retrieve template → Generate DOCX → Validate/export  
**Outputs:** TFL specification JSON, retrieval and rationale records, editable `.docx` table shell, validation report.

The package (`src/tfl_agent/`) contains the implementation; notebooks only configure and call it.

## Quick start: Google Colab (recommended for the presentation)

1. [Open the short Midterm Demo notebook](https://colab.research.google.com/github/wohaofanaweishenme-cell/tfl-generation-agent/blob/main/notebooks/02_Midterm_Demo_GitHub_Colab.ipynb).
2. Choose **Runtime → Run all** or execute the cells one by one. The setup cell clones this repository and installs the Python package automatically.
3. Keep `MODE = "fixture"` for a fully reproducible **synthetic integration demo**, no API key required.
4. Inspect the extracted specification, template match, generated Table shell, and validation report. Download the DOCX from the final cell.

**No ZIP upload is required** when opening the notebook from GitHub. Fresh Colab runtimes still need to rerun the setup cell. The direct Colab link works after this repository is populated and its default branch is `main`. See [GitHub and Colab setup (中文)](GITHUB_COLAB_SETUP.md) for upload and troubleshooting details.

For the optional **real LLM call**, change the notebook to `MODE = "api"` and provide an `OPENAI_API_KEY` through Colab Secrets. This does not automatically turn the included **synthetic SAP and Library** into clinical validation data; you must configure actual SAPs and an independently reviewed library and inspect the resulting evidence.

## Real-study + DeepSeek compatibility demo (new)

[Open Real-Study / DeepSeek Colab notebook](https://colab.research.google.com/github/wohaofanaweishenme-cell/tfl-generation-agent/blob/main/notebooks/03_Real_Study_DeepSeek_Colab.ipynb) · [Detailed steps](REAL_STUDY_DEEPSEEK_GUIDE.md)

The source-only study library at `library/studies/P-VCNA-003/` is read-only.
The loader supports its `Study_Metadata.json` + `TFL_Template_Library/` layout.
This first **Stage-A** run makes real DeepSeek calls to extract target SAP requirements,
then shows evidence, ranked templates, and adaptation feasibility.
**Authentic bookmarked source DOCX files cannot yet be safely adapted by the old placeholder editor;
these are flagged `needs_review`, not claimed as generated documents.**
Revoke exposed API keys; store a new key only in Colab Secrets as `DEEPSEEK_API_KEY`.

## Local development

Requires **Python 3.11+** and Git. From the **repository root**:

```bash
git clone https://github.com/wohaofanaweishenme-cell/tfl-generation-agent.git
cd tfl-generation-agent
python -m pip install -e ".[notebook,test]"
python -m pytest -q
jupyter lab
```

Open `notebooks/01_TFL_Generation_MVP.ipynb` for more detailed step-by-step debugging. For a concise presentation, use `notebooks/02_Midterm_Demo_GitHub_Colab.ipynb` instead. The first notebook's original Colab initialization may still offer ZIP upload; the second is tailored to GitHub cloning.

### Example package usage

```python
from tfl_agent import TFLSession
from tfl_agent.tools.llm_client import FixtureJSONClient

session = TFLSession(
    sap_path="input/synthetic_sap.pdf",
    library_path="library",
    schema_path="schemas/TFL_Specification.schema.json",
    prompts_dir="prompts",
    output_dir="output/demo",
    llm=FixtureJSONClient("examples/demo_llm_output.json"),
    tfl_id="14.2.1",
    title="Summary of Overall Survival",
)

session.step1_parse()
session.step2_build_specification()
session.step3_retrieve_templates()
session.preview_modification_plan()
session.step4_generate_shell()
report = session.step5_validate_and_export()
print(report)
```

## Repository layout

```text
.
├── src/tfl_agent/                      # Installable Python package
│   ├── session.py                       # Five-step orchestration
│   ├── agent/                           # Parser/spec/retriever/generator/validator
│   └── tools/                           # PDF, search, LLM, DOCX, JSON helpers
├── notebooks/
│   ├── 01_TFL_Generation_MVP.ipynb       # Full developer notebook
│   └── 02_Midterm_Demo_GitHub_Colab.ipynb # Short presentation notebook
├── library/                             # Synthetic library and metadata
├── input/synthetic_sap.pdf              # Synthetic demonstration SAP
├── examples/                            # Synthetic LLM fixture and examples
├── prompts/                             # Extraction prompts
├── schemas/                             # Output specification schema
├── tests/                               # Tests; run with pytest
├── pyproject.toml                       # Installable package configuration
├── requirements.txt
└── GITHUB_COLAB_SETUP.md                # GitHub/Colab setup + demo checklist
```

## Workflow and what the current MVP does

| Stage | Purpose | Current scope |
| --- | --- | --- |
| 1. Parse SAP | Read PDF blocks and identify target context | Text-selectable PDFs, one selected target |
| 2. Build specification | Extract populations, endpoint, statistics and cited SAP snippets | Fixture response or API; evidence checks are limited |
| 3. Retrieve template | Match specification to a metadata/keyword-indexed library | Simple ranking, synthetic example library |
| 4. Generate shell | Safely fill supported placeholders in a DOCX template | One **Table**; figure/listing not implemented |
| 5. Validate/export | Check schemas, source quotes, document structure and generate reports | Structural checks, **not** clinical correctness |

The optional Content List is **not required** for the current workflow. The current demonstration takes a single predefined target TFL rather than automatically generating all TFLs for an entire study. Source templates in `library/` are not modified.

## Current limitations and planned work

- **Fixture mode** uses a prewritten LLM output, so it is not evidence of model performance. API mode requires separate testing and evaluation.
- Scanned PDFs without extractable text are not supported (no OCR); cross-section retrieval and inference may fail on longer SAPs.
- Current generator handles **Table DOCX placeholders only**. Unsupported or mismatched templates are flagged for review rather than silently rewritten.
- Footnotes are represented as ordinary document paragraphs, not Word's native footnote XML. Verify they match the source SAP.
- Validation does not guarantee the correct population, statistical methods, denominator, censoring rules or medical interpretation.
- Planned: real reviewed library, systematic success/failure evaluation, broader TFL coverage, retrieval improvements, polished outputs.

## Testing and responsible data handling

```bash
python -m pip install -e ".[notebook,test]"
python -m pytest -q
```

The repository includes tests for the package and notebook workflow. Local checks on the prepared midterm package passed **11 tests**; GitHub CI results (if configured) should be evaluated separately. Generated files belong in ignored `output/`.

**Do not commit** API keys, tokens, `.env` files, proprietary SAPs, identifiable patient information or unreviewed private study data. Keep real inputs in a separately managed private location and configure paths at runtime. No code in this repository is intended to replace statistical review or regulatory validation.
