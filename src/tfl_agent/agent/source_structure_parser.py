"""Read-only Source Template intermediate representation (IR).

The authoritative Library stores one editable DOCX per TFL and separate,
SHA-bound Bookmark Locator Maps.  A verified bookmark identifies source
content, but is NOT itself a Word table row/column coordinate.  We inspect
both the DOCX table geometry and the locator independently.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from tfl_agent.tools.io_utils import read_json


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value):
    return _clean(value).casefold()


def _meaningful_row(value):
    text = _clean(value)
    if not text or len(text) > 220:
        return False
    if re.fullmatch(r"[\sxX.,%()0-9/+\-]+", text):
        return False
    if re.fullmatch(r"(?:n\s*[\(%].*|n\s*=\s*.*)", text, re.I):
        return False
    if text.lower().startswith(("page ", "program:", "source:", "reference listing", "path\\")):
        return False
    return True


def _is_statistic(text):
    return bool(re.fullmatch(
        r"(?i)(?:n|n\s*\(missing\)|mean|median|sd|standard deviation|min(?:imum)?|"
        r"max(?:imum)?|min\s*,\s*max|q[123]|lower ci|upper ci)",
        _clean(text),
    ))


def _bookmark_locations(doc):
    """Map real Word bookmark names to logical table and cell coordinates.

    This is a geometry index, not a statement that an anchor is editable.
    Merged cells can occupy several logical positions: keep the first and
    retain the whole grid separately for review.
    """
    positions = {}
    for ti, table in enumerate(doc.tables):
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                for start in cell._tc.xpath(".//w:bookmarkStart"):
                    name = start.get(qn("w:name"))
                    if name and name not in positions:
                        positions[name] = {
                            "table_index": ti, "row_index": ri,
                            "column_index": ci, "location_type": "table_cell",
                        }
    for pi, paragraph in enumerate(doc.paragraphs):
        for start in paragraph._p.xpath(".//w:bookmarkStart"):
            name = start.get(qn("w:name"))
            if name and name not in positions:
                positions[name] = {
                    "paragraph_index": pi, "location_type": "body_paragraph",
                }
    return positions


def parse_source_template(template_path, locator_map_path):
    """Return a JSON-serializable IR; reject unverifiable source revisions.

    The caller owns matching and plan approval.  This function never writes.
    """
    template = Path(template_path).resolve()
    locator_path = Path(locator_map_path).resolve()
    if not template.is_file() or not locator_path.is_file():
        raise FileNotFoundError("Source DOCX and verified locator map are both required")
    locator = read_json(locator_path)
    boundary = locator.get("docx_boundary") or {}
    digest = hashlib.sha256(template.read_bytes()).hexdigest()
    if locator.get("template_id") != template.stem:
        raise ValueError("Locator template_id must equal source DOCX filename")
    if boundary.get("verification_status") != "verified":
        raise ValueError("Locator boundary is not verified")
    if digest != boundary.get("document_sha256"):
        raise ValueError("Source DOCX SHA-256 does not match verified locator")
    doc = Document(template)
    positions = _bookmark_locations(doc)
    starts = {
        tag.get(qn("w:name")) for tag in
        doc.part.element.xpath(".//w:bookmarkStart")
    }
    elements = []
    missing_bookmarks = []
    for element in locator.get("source_elements", []):
        role = element.get("element_type") or "unknown"
        for occurrence in element.get("occurrences", []):
            anchor = occurrence.get("docx_locator")
            if not isinstance(anchor, str) or not anchor.startswith("bookmark:"):
                continue
            bookmark = anchor.split(":", 1)[1]
            verified = occurrence.get("verification_status") == "verified"
            if verified and bookmark not in starts:
                missing_bookmarks.append(bookmark)
            elements.append({
                "element_id": element.get("element_id"),
                "occurrence_id": occurrence.get("occurrence_id"),
                "role": role,
                "text": str(occurrence.get("source_text") or ""),
                "bookmark": bookmark,
                "verified": verified and bookmark in starts,
                "position": positions.get(bookmark),
                "source_ref_ids": occurrence.get("source_ref_ids") or [],
            })
    verified_elements = [e for e in elements if e["verified"]]
    if not verified_elements:
        raise ValueError("No verified locator bookmarks found in source DOCX")

    tables = []
    row_candidates = []
    column_candidates = []
    for ti, table in enumerate(doc.tables):
        grid = []
        for ri, row in enumerate(table.rows):
            cells = []
            for ci, cell in enumerate(row.cells):
                # Native cells can span several logical grid positions.
                cells.append({
                    "column_index": ci,
                    "text": _clean(cell.text),
                    "bookmark_names": [
                        start.get(qn("w:name"))
                        for start in cell._tc.xpath(".//w:bookmarkStart")
                        if start.get(qn("w:name"))
                    ],
                })
            grid.append(cells)
            if cells and _meaningful_row(cells[0]["text"]):
                row_candidates.append({
                    "label": cells[0]["text"],
                    "position": {
                        "location_type": "table_cell",
                        "table_index": ti, "row_index": ri, "column_index": 0,
                    },
                    "bookmarks": cells[0]["bookmark_names"],
                    "is_statistic_subrow": _is_statistic(cells[0]["text"]),
                    "source": "docx_first_column",
                })
        tables.append({
            "table_index": ti,
            "row_count": len(table.rows),
            "logical_column_count": max((len(x) for x in grid), default=0),
            "grid": grid,
        })

    # Locator header cells are better than blindly assuming row 0 is the
    # header.  Some studies represent header text in generic body bookmarks.
    seen_header_text = set()
    for e in verified_elements:
        if e["role"] != "header_cell":
            continue
        if not _clean(e["text"]):
            continue
        key = _norm(e["text"])
        if key not in seen_header_text:
            column_candidates.append({
                "label": _clean(e["text"]), "bookmark": e["bookmark"],
                "position": e["position"], "source": "verified_header_cell",
            })
            seen_header_text.add(key)

    # Some studies use body paragraphs / generic 'body' bookmarks rather
    # than a native table.  Expose them as candidates, but do not invent
    # coordinates or pretend they are a hierarchical row structure.
    seen_rows = {_norm(c["label"]) for c in row_candidates}
    for e in verified_elements:
        if e["role"] not in ("body_cell", "body"):
            continue
        label = _clean(e["text"])
        if not _meaningful_row(label) or _norm(label) in seen_rows:
            continue
        row_candidates.append({
            "label": label,
            "position": e["position"],
            "bookmarks": [e["bookmark"]],
            "is_statistic_subrow": _is_statistic(label),
            "source": "verified_locator_" + e["role"],
        })
        seen_rows.add(_norm(label))

    footnotes = [{
        "text": _clean(e["text"]),
        "bookmark": e["bookmark"],
        "position": e["position"],
        "source_ref_ids": e["source_ref_ids"],
    } for e in verified_elements if e["role"] == "footnote" and _clean(e["text"])]

    placeholders = sorted({
        _clean(e["text"]) for e in verified_elements
        if e["role"] in ("placeholder_cell", "placeholder")
        and 0 < len(_clean(e["text"])) <= 55
    })[:40]
    return {
        "ir_version": "source-ir-1.0",
        "template_id": template.stem,
        "source_docx": str(template),
        "locator_map_path": str(locator_path),
        "source_sha256": digest,
        "boundary_verified": True,
        "verified_occurrence_count": len(verified_elements),
        "missing_verified_bookmarks": sorted(set(missing_bookmarks)),
        "table_count": len(tables),
        "tables": tables,
        "row_candidates": row_candidates,
        "column_candidates": column_candidates,
        "footnotes": footnotes,
        "placeholder_formats": placeholders,
        "title_candidates": [{
            "text": _clean(e["text"]), "bookmark": e["bookmark"],
            "position": e["position"],
        } for e in verified_elements if e["role"] == "title"],
        "warnings": (
            ["Some verified locator bookmarks were not present in DOCX: review mapping"]
            if missing_bookmarks else []
        ) + (
            ["No native Word table: structural edits require a specialized executor"]
            if not tables else []
        ) + (
            ["No explicit header_cell roles: column mapping requires geometry review"]
            if not column_candidates else []
        ),
    }
