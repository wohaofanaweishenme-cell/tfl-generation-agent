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




# Stage B.4: structural geometry and hierarchical row analysis.
# These fields are additive: v1 readers can continue to use row_candidates.
def _statistic_kind(label):
    s = _clean(label).casefold()
    match = re.fullmatch(
        r"(?:n(?:\s*\(missing\))?|mean(?:\s*\(sd\))?|median|sd|"
        r"standard deviation|min(?:imum)?(?:\s*,\s*max(?:imum)?)?|"
        r"max(?:imum)?|q[123]|95% ci|lower ci|upper ci)",
        s,
    )
    return bool(match)


def _source_category_parent(label):
    s = _clean(label).casefold()
    return bool(
        re.search(
            r"\b(?:race|sex|gender|age group|menopausal|ethnicity|"
            r"severity|relationship|bor|best overall response|"
            r"disposition reason|visit|baseline)\b",
            s,
        )
    )


def _column_header_like(label):
    s = _clean(label)
    return bool(re.search(
        r"\b(?:arm\s+(?:i|ii|iii|\d+)|cohort\s*\d+|"
        r"(?:n\s*=\s*[^)]*)|dose|mg(?:/kg|/m|/day)|overall|total|"
        r"safety population|treatment)\b", s, flags=re.I,
    ))


def _native_header_columns(tables, locator_headers):
    """Detect header positions from actual Word cells, not bookmark counts.

    The output uses 0-based *physical logical grid coordinates*.  A distinct
    header index is not a column coordinate; merged cells are documented.
    """
    result = []
    seen = set()
    for table in tables:
        ti, grid = table["table_index"], table["grid"]
        if not grid:
            continue
        # Header rows may be sparse or repeated across continuation panels.
        for ri, cells in enumerate(grid[:min(3, len(grid))]):
            labels = [c["text"] for c in cells if c["text"]]
            if not labels:
                continue
            if (ri > 0 and not any(_column_header_like(x) for x in labels)):
                continue
            for cell in cells:
                value = cell["text"]
                if not value or not _column_header_like(value):
                    continue
                if _norm(value) in {"parameter", "statistic", "cohort"}:
                    continue
                pos = {"location_type": "table_cell", "table_index": ti,
                       "row_index": ri, "column_index": cell["column_index"]}
                key = (ti, ri, cell["column_index"])
                if key in seen:
                    continue
                seen.add(key)
                matches = [h for h in locator_headers if
                           h.get("position") == pos]
                result.append({
                    "label": value,
                    "physical_grid_index": cell["column_index"],
                    "table_index": ti, "header_row_index": ri,
                    "position": pos,
                    "bookmark": matches[0]["bookmark"] if matches else (
                        cell["bookmark_names"][0] if cell["bookmark_names"] else None
                    ),
                    "source": "verified_header_cell" if matches else "word_grid_header_heuristic",
                    "is_reviewed": False,
                    "geometry_inferred": not bool(matches),
                    "grid_span": cell.get("grid_span", 1),
                    "vertical_merge": cell.get("vertical_merge"),
                })
            if result and any(c["table_index"] == ti for c in result):
                break
    return result


def _hierarchical_rows(tables):
    """Group repeated n/Mean/SD under a local parent, keeping all Word coords.

    Category inference is conservative: a subrow carries 'inferred' status;
    Word indentation and source-study labels are not clinical proof.
    """
    rows = []
    for table in tables:
        ti = table["table_index"]
        current_parent = None
        for ri, cells in enumerate(table["grid"]):
            if ri == 0 or not cells:
                continue
            main = _clean(cells[0]["text"])
            sub = _clean(cells[1]["text"]) if len(cells) > 1 else ""
            is_sub = False
            if not main and sub and current_parent and _source_category_parent(current_parent["label"]):
                # Only child content next to a row-family label, never a
                # Cohort/Statistic matrix where column 1 is a data axis.
                if not re.search(r"\b(?:cohort|dose|n\s*=)\b", sub, flags=re.I):
                    main, is_sub = sub, True
                    chosen_col = 1
                else:
                    continue
            elif main:
                chosen_col = 0
                is_sub = _statistic_kind(main)
            else:
                continue
            if not _meaningful_row(main) and not is_sub:
                continue
            row_id = f"T{ti:02d}R{ri:04d}C{chosen_col:02d}"
            parent = current_parent["row_id"] if is_sub and current_parent else None
            item = {
                "row_id": row_id, "label": main,
                "parent_row_id": parent,
                "row_type": ("statistic_subrow" if _statistic_kind(main)
                             else "category_subrow" if parent else "section_or_variable"),
                "inference_status": "inferred_requires_review" if parent else "word_grid_observed",
                "position": {"location_type": "table_cell",
                             "table_index": ti, "row_index": ri,
                             "column_index": chosen_col},
                "bookmark_names": cells[chosen_col]["bookmark_names"],
            }
            rows.append(item)
            if not is_sub:
                current_parent = item
    return rows


def _layout_profile(tables, header_columns):
    if not tables:
        return {
            "axis_orientation": "no_word_table",
            "column_coordinates_verified": False,
            "notes": ["Source has no native Word table"],
        }
    vertical = False
    for table in tables:
        grid = table["grid"]
        if grid and len(grid[0]) >= 3:
            head = [_norm(c["text"]) for c in grid[0]]
            if "cohort" in head and "statistic" in head:
                vertical = True
                break
    if vertical:
        mode = "cohort_rows_statistic_columns"
    elif header_columns:
        mode = "treatment_arm_columns"
    else:
        mode = "unclassified"
    return {
        "axis_orientation": mode,
        "column_coordinates_verified": False,  # not independently reviewed
        "word_table_count": len(tables),
        "panel_column_counts": [t["logical_column_count"] for t in tables],
        "notes": (["Cohorts appear vertically; horizontal arm-column surgery is unsafe"]
                  if vertical else []),
    }


def _group_footnotes(footnotes):
    result = []
    by_key = {}
    for item in footnotes:
        key = _norm(item["text"])
        if not key:
            continue
        if key not in by_key:
            group = {
                "footnote_id": f"FN{len(result)+1:03d}",
                "text": item["text"],
                "occurrences": [],
                "origin": "source_study_not_target_evidence",
            }
            result.append(group)
            by_key[key] = group
        by_key[key]["occurrences"].append({
            "bookmark": item["bookmark"],
            "position": item["position"],
            "source_ref_ids": item["source_ref_ids"],
        })
    return result


def _title_mapping(title_candidates):
    # Sponsor identifiers can be tagged 'title'. Prefer a literal Table
    # marker; retain heading continuation fragments without silently
    # equating them to a single safe bookmark-edit range.
    anchored = [
        c for c in title_candidates if
        re.search(r"\btable\s*\d[\d.\-]*\b", c["text"], flags=re.I)
    ]
    primary = anchored[0] if anchored else None
    if primary is not None:
        idx = title_candidates.index(primary)
        continuation = []
        for item in title_candidates[idx+1:idx+3]:
            if re.search(r"\b(?:safety|analysis|population)\b", item["text"], re.I):
                break
            continuation.append(item)
        return {
            "anchor": primary, "continuation_candidates": continuation,
            "status": "title_anchor_candidate_requires_review",
        }
    return {"anchor": None, "continuation_candidates": [],
            "status": "title_anchor_missing"}


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
                tcpr = cell._tc.tcPr
                span_nodes = tcpr.xpath("./w:gridSpan") if tcpr is not None else []
                merge_nodes = tcpr.xpath("./w:vMerge") if tcpr is not None else []
                span = int(span_nodes[0].get(qn("w:val"), "1")) if span_nodes else 1
                vmerge = (merge_nodes[0].get(qn("w:val"), "continue")
                          if merge_nodes else None)
                cells.append({
                    "column_index": ci,
                    "grid_span": span, "vertical_merge": vmerge,
                    "physical_cell_key": str(id(cell._tc)),
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

    # Prefer native Word grid geometry and bookmarked positions.
    # Preserve v1 candidates independently for backward compatibility.
    structural_headers = _native_header_columns(tables, column_candidates)
    hierarchy = _hierarchical_rows(tables)
    layout = _layout_profile(tables, structural_headers)
    grouped_footnotes = _group_footnotes(footnotes)
    title_nodes = [{
        "text": _clean(e["text"]), "bookmark": e["bookmark"],
        "position": e["position"],
    } for e in verified_elements if e["role"] == "title"]
    title_mapping = _title_mapping(title_nodes)

    placeholders = sorted({
        _clean(e["text"]) for e in verified_elements
        if e["role"] in ("placeholder_cell", "placeholder")
        and 0 < len(_clean(e["text"])) <= 55
    })[:40]
    return {
        "ir_version": "source-ir-2.0",
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
        "column_candidates": structural_headers or column_candidates,
        "locator_header_candidates": column_candidates,
        "layout_profile": layout,
        "hierarchical_rows": hierarchy,
        "footnote_groups": grouped_footnotes,
        "title_mapping": title_mapping,
        "footnotes": footnotes,
        "placeholder_formats": placeholders,
        "title_candidates": title_nodes,
        "warnings": (
            ["Some verified locator bookmarks were not present in DOCX: review mapping"]
            if missing_bookmarks else []
        ) + (
            ["No native Word table: structural edits require a specialized executor"]
            if not tables else []
        ) + (
            ["No explicit header_cell roles: column mapping requires geometry review"]
            if not structural_headers else []
        ),
    }
