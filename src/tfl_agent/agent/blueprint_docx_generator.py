"""DOCX reconstruction from a target-owned Blueprint; never transplant source rows."""
from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def _write_cell(cell, text, *, bold=False, italic=False, indent=0):
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.space_after = Pt(2)
    p.space_before = Pt(2)
    p.paragraph_format.left_indent = Inches(indent * 0.16)
    r = p.add_run(str(text))
    r.bold = bold
    r.italic = italic
    r.font.name = "Arial"
    r.font.size = Pt(8)


def _shade(cell, fill):
    el = OxmlElement("w:shd")
    el.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(el)


def _repeat_header(row):
    element = OxmlElement("w:tblHeader")
    element.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(element)


def _configure_page(doc, blueprint, style_source):
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Inches(11.7), Inches(8.3)
    section.left_margin = section.right_margin = Inches(0.60)
    section.top_margin = section.bottom_margin = Inches(0.68)
    details = {"verified_style_reference_used": False,
               "source_width_fraction_used": False}
    ref = blueprint["source_structure"]
    if not (style_source and ref.get("verified_source_ir_used")):
        return 0.42, details
    source = Path(style_source).resolve()
    if not source.is_file():
        raise FileNotFoundError("Verified style source DOCX disappeared")
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != ref.get("source_sha256"):
        raise ValueError("Source style DOCX SHA-256 changed after planning")
    other = Document(source)
    if other.sections:
        s = other.sections[0]
        # Copy only nonclinical page style attributes.
        for field in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            value = getattr(s, field, None)
            if value is not None:
                setattr(section, field, value)
    details["verified_style_reference_used"] = True
    # The first logical column of a verified source Word grid provides only
    # a layout proportion; never copy its label or any patient information.
    if other.tables and len(other.tables[0].columns) >= 2:
        source_widths = [c.width for c in other.tables[0].columns]
        if all(x is not None and x > 0 for x in source_widths):
            ratio = float(source_widths[0]) / float(sum(source_widths))
            details["source_width_fraction_used"] = True
            return min(0.54, max(0.32, ratio)), details
    return 0.42, details


def generate_docx_from_blueprint(blueprint: dict, output_path: str | Path,
                                 *, style_source: str | Path | None = None) -> dict:
    """Create an editable native Word table and preserve provenance in metadata."""
    if blueprint.get("blueprint_version") != "table-reconstruction-1.0":
        raise ValueError("Unsupported Blueprint schema")
    cols, rows = blueprint.get("columns") or [], blueprint.get("rows") or []
    if not cols or not rows:
        raise ValueError("Cannot build a shell without target columns and rows")
    if blueprint.get("source_content_copied") is not False:
        raise ValueError("Source-study content must not enter target reconstruction")
    if blueprint.get("header_rows") not in (1, 2):
        raise ValueError("Unsupported header depth")
    if len(cols) > 16 or len(rows) > 300:
        raise ValueError("Blueprint exceeds document safety limits")

    dest = Path(output_path).resolve()
    if style_source and dest == Path(style_source).resolve():
        raise ValueError("Source Library DOCX must never be overwritten")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError("Refusing to overwrite an existing generated draft")

    doc = Document()
    ratio, style_info = _configure_page(doc, blueprint, style_source)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(9)
    doc.styles["Normal"].font.color.rgb = RGBColor(30, 40, 55)
    doc.sections[0].header.paragraphs[0].text = (
        "AUTO-GENERATED TFL STRUCTURAL DRAFT  |  NOT CLINICALLY VALIDATED"
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title = blueprint["identity"]
    run = p.add_run(f"Table {title['tfl_id']}  {title['title']}")
    run.bold = True
    run.font.size = Pt(11)
    populations = blueprint.get("population") or []
    if populations:
        p = doc.add_paragraph("; ".join(populations))
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:
            r.italic = True

    ncols = len(cols) + 1
    table = doc.add_table(rows=blueprint["header_rows"], cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    # Widths are presentation choices; source can affect the label-width ratio.
    usable = 10.65
    label_width = usable * ratio
    widths = [Inches(label_width)] + [
        Inches((usable - label_width) / len(cols)) for _ in cols
    ]
    for row in table.rows:
        _repeat_header(row)
    for index, label in enumerate(
        [blueprint["row_label_header"]] + [
            f"{col['label']}\n(N=xx)" if col.get("kind") in (
                "treatment_group", "overall"
            ) else col["label"]
            for col in cols
        ]
    ):
        _write_cell(table.rows[0].cells[index], label, bold=True)
        _shade(table.rows[0].cells[index], "E8EDF2")
    if blueprint["header_rows"] == 2:
        for ci, text in enumerate(
            [""] + [blueprint.get("header_statistic_text") or ""] * len(cols)
        ):
            _write_cell(table.rows[1].cells[ci], text, bold=True)
            _shade(table.rows[1].cells[ci], "F2F5F7")

    for i, row_info in enumerate(rows):
        cells = table.add_row().cells
        depth = int(row_info.get("depth") or 0)
        _write_cell(cells[0], row_info["label"],
                    bold=bool(depth == 0 and row_info["kind"] == "group"),
                    italic=bool(depth and row_info["kind"] == "statistic_subrow"),
                    indent=depth)
        for j in range(1, ncols):
            _write_cell(cells[j], row_info.get("placeholder", "xx"))
        if i % 2:
            for cell in cells:
                _shade(cell, "FAFBFC")
    for row in table.rows:
        for j, cell in enumerate(row.cells):
            cell.width = widths[j]

    doc.add_paragraph("")
    if blueprint.get("footnotes"):
        p = doc.add_paragraph("Target SAP-derived notes (verify table applicability):")
        p.runs[0].bold = True
        for i, note in enumerate(blueprint["footnotes"], 1):
            doc.add_paragraph(f"{i}. {note}")
    doc.add_paragraph(
        "All xx values are placeholders. Denominator, precision, structure and "
        "clinical applicability require independent review."
    )
    doc.sections[0].footer.paragraphs[0].text = (
        "UNAPPROVED RECONSTRUCTED SHELL  |  SAP & GROUND-TRUTH REVIEW REQUIRED"
    )
    doc.save(dest)
    return {
        "generator": "BLUEPRINT_DRIVEN_DOCX_RECONSTRUCTION",
        "output_path": str(dest),
        "row_count": len([r for r in rows if int(r.get("depth") or 0) == 0]),
        "word_row_count": len(rows) + blueprint["header_rows"],
        "column_count": ncols,
        "source_word_text_transplanted": False,
        "source_structure_used": bool(
            blueprint["source_structure"].get("verified_source_ir_used")
        ),
        "clinical_approval": False,
        **style_info,
    }


def validate_reconstructed_shell(docx_path: str | Path, blueprint: dict) -> dict:
    """Validate target-owned Word structure; NOT clinical or ground-truth quality."""
    doc = Document(docx_path)
    problems = []
    if len(doc.tables) != 1:
        problems.append(f"Expected one native Word table, found {len(doc.tables)}")
    if doc.tables:
        table = doc.tables[0]
        expected_cols = len(blueprint["columns"]) + 1
        expected_rows = len(blueprint["rows"]) + blueprint["header_rows"]
        if len(table.columns) != expected_cols:
            problems.append("Native Word column count does not match Blueprint")
        if len(table.rows) != expected_rows:
            problems.append("Native Word row count does not match Blueprint")
        first = [c.text for c in table.rows[0].cells]
        for col in blueprint["columns"]:
            if not any(col["label"] in x for x in first):
                problems.append(f"Missing target column: {col['label']}")
        actual_rows = table.rows[blueprint["header_rows"]:]
        for expected, actual in zip(blueprint["rows"], actual_rows):
            if actual.cells[0].text != expected["label"]:
                problems.append(f"Row mismatch: {expected['label']}")
            for cell in actual.cells[1:]:
                if cell.text != expected.get("placeholder", "xx"):
                    problems.append(f"Placeholder mismatch for {expected['label']}")
    paragraphs = "\n".join(p.text for p in doc.paragraphs)
    for note in blueprint.get("footnotes") or []:
        if note not in paragraphs:
            problems.append("Target footnote missing from generated Word")
    return {
        "valid_structural_shell": not problems,
        "structural_errors": problems,
        "word_table_count": len(doc.tables),
        "rows_in_target_specification": sum(
            1 for r in blueprint["rows"] if r.get("depth") == 0
        ),
        "target_treatment_groups": [c["label"] for c in blueprint["columns"]
                                    if c.get("kind") == "treatment_group"],
        "source_content_copied": False,
        "clinical_validity_verified": False,
        "comparative_shell_ground_truth_checked": False,
        "note": "Compared with Blueprint only, not independent clinical ground truth.",
    }
