"""Rebuild an editable AE TFL DOCX from target SAP requirements.

Source Library DOCX contributes only presentational cues (margins/font size),
never source study row labels, drug names, data values, or footnotes.
"""
from __future__ import annotations
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def _replace_doc_core(doc: Document, source: Path | None) -> dict:
    borrowed = {"source_style_reference": str(source) if source else None,
                "copied_clinical_content": False}
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Inches(11.7), Inches(8.3)
    sec.top_margin, sec.bottom_margin = Inches(0.68), Inches(0.68)
    sec.left_margin, sec.right_margin = Inches(0.60), Inches(0.60)
    font_size = Pt(9)
    if source and source.is_file():
        other = Document(source)
        s = other.sections[0]
        sec.top_margin = s.top_margin
        sec.bottom_margin = s.bottom_margin
        sec.left_margin = s.left_margin
        sec.right_margin = s.right_margin
        if other.tables and other.tables[0].rows and other.tables[0].rows[0].cells:
            first = other.tables[0].rows[0].cells[0]
            if first.paragraphs and first.paragraphs[0].runs:
                fs = first.paragraphs[0].runs[0].font.size
                if fs and 7 <= fs.pt <= 11:
                    font_size = Pt(fs.pt)
        borrowed["borrowed_from_library"] = [
            "margin_settings", "header_font_size_if_reasonable",
        ]
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = font_size
    doc.styles["Normal"].font.color.rgb = RGBColor(30, 40, 55)
    return borrowed


def _set_cell_shading(cell, fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _set_header_repeat(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _set_cell_text(cell, value: str, *, bold=False, size=8):
    cell.text = ""
    p = cell.paragraphs[0]
    p.space_before = Pt(2)
    p.space_after = Pt(2)
    run = p.add_run(value)
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(size)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def generate_ae_structural_docx(
    spec: dict, output_path: Path, *, style_source: str | Path | None = None
) -> dict:
    """Generate SAP-derived target AE rows and 4 physical columns from scratch."""
    rows = spec["table_requirements"]["row_requirements"]
    groups = spec["statistical_requirements"]["treatment_groups"]
    if len(groups) != 2 or len(rows) < 5:
        raise ValueError("AE pilot requires two SAP-defined groups and a verified category list")
    if "Overall" not in spec["table_requirements"]["column_requirements"]:
        raise ValueError("Missing SAP support for an Overall column")
    if not spec["table_requirements"].get("footnote_requirements"):
        raise ValueError("At least one SAP-grounded note required for this MVP")

    doc = Document()
    style_info = _replace_doc_core(doc, Path(style_source) if style_source else None)
    hdr = doc.sections[0].header.paragraphs[0]
    hdr.text = "TFL SHELL DRAFT  |  NOT CLINICALLY VALIDATED"
    hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for r in hdr.runs:
        r.font.size = Pt(7)
        r.font.color.rgb = RGBColor(145, 55, 55)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"Table {spec['identity']['tfl_id']}  {spec['identity']['title']}")
    run.bold = True
    run.font.size = Pt(11)
    population = doc.add_paragraph("Safety Analysis Set")
    population.alignment = WD_ALIGN_PARAGRAPH.CENTER
    population.runs[0].italic = True
    population.runs[0].font.size = Pt(9)

    table = doc.add_table(rows=2, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Inches(4.30), Inches(2.05), Inches(2.05), Inches(2.05)]
    for idx, width in enumerate(widths):
        for row in table.rows:
            row.cells[idx].width = width
    _set_header_repeat(table.rows[0])
    _set_header_repeat(table.rows[1])
    headers = [
        "Adverse Event Category", f"{groups[0]}\n(N=xx)",
        f"{groups[1]}\n(N=xx)", "Overall\n(N=xx)",
    ]
    for i, text in enumerate(headers):
        _set_cell_text(table.rows[0].cells[i], text, bold=True, size=8)
        _set_cell_shading(table.rows[0].cells[i], "E8EDF2")
    for i, text in enumerate(
        ["", "n (%)  |  Events", "n (%)  |  Events", "n (%)  |  Events"]
    ):
        _set_cell_text(table.rows[1].cells[i], text, bold=True, size=8)
        _set_cell_shading(table.rows[1].cells[i], "F2F5F7")

    for index, row_label in enumerate(rows):
        cells = table.add_row().cells
        for i, width in enumerate(widths):
            cells[i].width = width
        _set_cell_text(cells[0], row_label, size=8)
        for i in (1, 2, 3):
            _set_cell_text(cells[i], "xx (xx.x%)  |  xx", size=8)
        if index % 2:
            for cell in cells:
                _set_cell_shading(cell, "FAFBFC")
    doc.add_paragraph("")
    p = doc.add_paragraph()
    p.add_run("SAP-derived notes (table-specific applicability requires review):").bold = True
    for i, note in enumerate(spec["table_requirements"]["footnote_requirements"], 1):
        n = doc.add_paragraph(style="Normal")
        n.add_run(f"{i}. {note}")
        n.runs[0].font.size = Pt(8)
    p = doc.add_paragraph(
        "Shell placeholders (xx) are not clinical estimates. Percentage denominators "
        "and display precision remain subject to review."
    )
    for run in p.runs:
        run.italic = True
        run.font.size = Pt(8)
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.text = "AUTO-GENERATED DRAFT  •  EVIDENCE/FORMAT REVIEW REQUIRED"
    for run in footer.runs:
        run.font.size = Pt(7)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return {
        **style_info,
        "generator": "AE_STYLE_GUIDED_REBUILD_FROM_SAP_BODY",
        "output_path": str(path),
        "row_count": len(rows),
        "column_count": 4,
        "source_word_text_transplanted": False,
        "claim_clinical_approval": False,
    }


def validate_ae_shell(docx_path: Path, spec: dict) -> dict:
    doc = Document(docx_path)
    items = doc.tables
    groups = spec["statistical_requirements"]["treatment_groups"]
    expected = spec["table_requirements"]["row_requirements"]
    faults = []
    if len(items) != 1:
        faults.append(f"Expected one TFL table, found {len(items)}")
    if items:
        table = items[0]
        if len(table.columns) != 4:
            faults.append("Expected four native Word columns")
        if len(table.rows) != len(expected) + 2:
            faults.append("Target AE row count does not match SAP-extracted requirements")
        first = [c.text for c in table.rows[0].cells]
        for arm in groups:
            if not any(arm in x for x in first):
                faults.append("Treatment arm missing from actual Word header: " + arm)
        if not any("Overall" in x for x in first):
            faults.append("Overall treatment column absent")
        present = [row.cells[0].text for row in table.rows[2:]]
        for label in expected:
            if label not in present:
                faults.append("Missing target adverse event row: " + label)
        for row in table.rows[2:]:
            if any("xx" not in row.cells[j].text for j in (1, 2, 3)):
                faults.append("Missing statistical placeholder for " + row.cells[0].text)
        source_drugs = ("VCN-01", "Gemcitabine", "Nab-paclitaxel")
        table_text = " ".join(c.text for row in table.rows for c in row.cells)
        if any(x.lower() in table_text.lower() for x in source_drugs):
            faults.append("Source-study drug names leaked into target output")
    alltext = " ".join(p.text for p in doc.paragraphs)
    for note in spec["table_requirements"].get("footnote_requirements", []):
        if note not in alltext:
            faults.append("SAP-derived footnote not found")
    return {
        "valid_structural_shell": not faults,
        "structural_errors": faults,
        "word_table_count": len(items),
        "rows_in_target_specification": len(expected),
        "target_treatment_groups": groups,
        "clinical_validity_verified": False,
        "comparative_shell_ground_truth_checked": False,
        "note": (
            "Structural shell is judged against rule-extracted target "
            "Specification, not target held-out SAP Shell."
        ),
    }
