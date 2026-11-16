"""Generate a visibly unapproved Table DOCX draft from target SAP specifications.

This is deliberately NOT a claim of faithful bookmark-level source adaptation.
Source bookmarks and SHA are checked before using the reference template for
page geometry. All rows, columns, data placeholders and notes come from the
target specification; source study table contents and footnotes are NEVER copied.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from tfl_agent.tools.io_utils import read_json


def _source_library_root(source, locator):
    for parent in list(source.parents) + list(locator.parents):
        if parent.name == "library":
            return parent
    raise ValueError("Cannot establish official Library boundary")


def _unique(values):
    return list(dict.fromkeys(str(x).strip() for x in values if str(x).strip()))


def _columns_for_draft(spec):
    table = spec.get("table_requirements") or {}
    stats = spec.get("statistical_requirements") or {}
    raw = _unique(table.get("column_requirements") or [])
    groups = _unique(stats.get("treatment_groups") or [])
    # An aggregate label such as "Treatment group (A, B)" must never replace
    # individual arms with a single ambiguous data column.
    cleaned_groups = [re.sub(r"^Group\s+\d+\s*:\s*", "", s, flags=re.I)
                      for s in groups]
    cleaned_groups = _unique(cleaned_groups)
    if cleaned_groups:
        columns = cleaned_groups
        if any("overall" in x.lower() for x in raw):
            columns.append("Overall")
        # Preserve genuinely additional, explicit non-aggregate column names.
        for x in raw:
            low = x.lower()
            if x not in columns and "treatment group" not in low and not (
                    "by treatment" in low or low == "overall"):
                if x.lower() not in {y.lower() for y in columns}:
                    columns.append(x)
        return _unique(columns), raw
    return raw, raw


def _fail(reason, source, locator):
    return None, {
        "editing_mode": "source_verified_spec_draft",
        "safe_to_generate": False,
        "review_required": True,
        "issues": [reason],
        "reason": reason,
        "template_path": str(source),
        "locator_map_path": str(locator),
        "missing_placeholders": [],
        "unexpected_placeholders": [],
    }


def generate_spec_draft(source_path, spec, out_path, locator_map_path, *,
                        source_study_id=None, retrieval_status=None):
    """Create an editable *DRAFT*, or fail closed if source integrity is unknown.

    The resulting table is reconstructed from target Step-2 requirements; it
    does not reuse source rows/columns/footnotes whose semantics may differ.
    Source study is a verified layout reference and retrieval provenance.
    """
    source, dest = Path(source_path).resolve(), Path(out_path).resolve()
    locator = Path(locator_map_path).resolve() if locator_map_path else None
    if spec.get("identity", {}).get("output_type") != "table":
        return _fail("Only Table drafts are implemented", source, locator)
    if not locator or not locator.is_file() or not source.is_file():
        return _fail("Verified source DOCX or per-study locator is missing", source, locator)
    try:
        library_root = _source_library_root(source, locator)
        if dest == source or dest.is_relative_to(library_root):
            raise ValueError("Draft output path must be outside the entire official Library")
        payload = read_json(locator)
        boundary = payload.get("docx_boundary") or {}
        source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
        if payload.get("template_id") != source.stem:
            raise ValueError("Locator template_id does not match source DOCX")
        if boundary.get("verification_status") != "verified":
            raise ValueError("Source DOCX locator is not verified")
        if source_hash_before != boundary.get("document_sha256"):
            raise ValueError("Source DOCX SHA-256 does not match locator")
        doc_source = Document(source)
        actual_bookmarks = {
            tag.get(qn("w:name"))
            for tag in doc_source.part.element.xpath(".//w:bookmarkStart")
        }
        mapped_verified = {
            occurrence["docx_locator"].split(":", 1)[1]
            for item in payload.get("source_elements", [])
            for occurrence in item.get("occurrences", [])
            if occurrence.get("verification_status") == "verified"
            and isinstance(occurrence.get("docx_locator"), str)
            and occurrence["docx_locator"].startswith("bookmark:")
        }
        overlap = actual_bookmarks & mapped_verified
        if not overlap:
            raise ValueError("No verified source Word bookmarks correspond to locator")
        identity = spec["identity"]
        req = spec.get("table_requirements") or {}
        stats = spec.get("statistical_requirements") or {}
        rows = _unique(req.get("row_requirements") or [])
        columns, raw_columns = _columns_for_draft(spec)
        notes = _unique(req.get("footnote_requirements") or [])
        if len(rows) > 80 or len(columns) > 10:
            raise ValueError("Source requirements exceed draft limits; requires human layout planning")
        if not columns:
            columns = ["[COLUMNS NOT EXTRACTED — REVIEW REQUIRED]"]
        if not rows:
            rows = ["[ROWS NOT EXTRACTED — REVIEW REQUIRED]"]
        target_id, title = identity["tfl_id"], identity["title"]

        # New DOCX avoids accidentally carrying over a source sponsor name,
        # analysis population, statistics, footnotes, or prior-study branding.
        document = Document()
        src_sec, sec = doc_source.sections[0], document.sections[0]
        for key in ("page_width", "page_height", "top_margin", "bottom_margin",
                    "left_margin", "right_margin"):
            value = getattr(src_sec, key)
            if value is not None:
                setattr(sec, key, value)
        normal = document.styles["Normal"]
        normal.font.name = "Arial"
        normal.font.size = Pt(9)

        heading = document.add_paragraph()
        hrun = heading.add_run("DRAFT — NOT FOR CLINICAL OR REGULATORY USE")
        hrun.bold = True
        hrun.font.size = Pt(10)
        document.add_paragraph(f"Table {target_id}")
        title_para = document.add_paragraph(title)
        for run in title_para.runs:
            run.bold = True
        populations = _unique(stats.get("analysis_population") or [])
        if populations:
            document.add_paragraph("Target population: " + "; ".join(populations))
        else:
            document.add_paragraph("Target population: NOT EXTRACTED — REVIEW REQUIRED")

        tbl = document.add_table(rows=1, cols=len(columns) + 1)
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        try:
            tbl.autofit = True
        except AttributeError:
            pass
        labels = ["Parameter / Row"] + columns
        for j, name in enumerate(labels):
            cell = tbl.cell(0, j)
            cell.text = name
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
        trpr = tbl.rows[0]._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:tblHeader"))
        for label in rows:
            cells = tbl.add_row().cells
            cells[0].text = label
            for cell in cells[1:]:
                cell.text = "xx"

        document.add_paragraph(
            "All xx cells are EMPTY DATA PLACEHOLDERS; no patient-level results "
            "or calculated statistics are supplied."
        )
        stat_display = _unique(stats.get("statistics_to_display") or [])
        document.add_paragraph(
            "Target statistical measures: " + (
                "; ".join(stat_display) if stat_display
                else "NOT EXTRACTED — REVIEW REQUIRED"
            )
        )
        document.add_paragraph(
            "Raw target column specification: " + (
                "; ".join(raw_columns) if raw_columns
                else "NOT EXTRACTED — REVIEW REQUIRED"
            )
        )
        document.add_paragraph(
            "Target footnotes: " + (
                "; ".join(notes) if notes
                else "NONE EXTRACTED — inspect target SAP / source shell before approval"
            )
        )
        document.add_paragraph(
            "Adaptation review: Compare all target analysis populations, "
            "arm labels, rows, statistics, denominator, footnotes and layout "
            "against the target SAP and target TFL shell."
        )
        document.add_paragraph(
            f"Source layout reference only: {source.stem}"
            + (f" (study {source_study_id})" if source_study_id else "")
            + f"; retrieval status: {retrieval_status or 'unknown'}. "
            "No source clinical table cells or statistical footnotes were reused."
        )
        if spec.get("issues"):
            document.add_paragraph("Unresolved Step-2 issues (review required):")
            for issue in spec["issues"][:20]:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.add_run(str(issue.get("description") or issue.get("issue_type") or issue))
        dest.parent.mkdir(parents=True, exist_ok=True)
        document.save(dest)
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash_before:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Source DOCX changed while generating draft")
        plan = {
            "editing_mode": "source_verified_spec_draft",
            "safe_to_generate": True,
            "review_required": True,
            "template_path": str(source),
            "locator_map_path": str(locator),
            "template_id": source.stem,
            "source_study_id": source_study_id,
            "source_sha256": source_hash_before,
            "output_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "source_word_bookmark_count": len(actual_bookmarks),
            "verified_locator_bookmark_overlap": len(overlap),
            "target_rows": rows,
            "target_columns": columns,
            "raw_target_columns": raw_columns,
            "target_footnotes": notes,
            "missing_rows": not bool(req.get("row_requirements")),
            "missing_columns": not bool(req.get("column_requirements")),
            "missing_footnotes": not bool(notes),
            "source_contents_copied": False,
            "replacement_counts": {},
            "missing_placeholders": [],
            "unexpected_placeholders": [],
            "reason": "Source bookmarks and SHA checked; target-spec Table draft constructed for review",
            "warnings": [
                "Draft generated from target Step-2 requirements, not source bookmark-level adaptation",
                "Source rows, columns, footnotes and sponsor branding were not reused",
                "Review target SAP, denominator, missing fields and formatting before approval",
            ],
        }
        return str(dest), plan
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        dest.unlink(missing_ok=True)
        return _fail(f"{type(exc).__name__}: {exc}", source, locator)
