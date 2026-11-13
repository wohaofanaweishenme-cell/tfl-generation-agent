"""Conservative, auditable adaptation of *verified* source DOCX bookmarks.

The source Library is read-only.  A successful structural edit is a DRAFT,
never clinical/statistical approval.  No row/column geometry is invented.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from tfl_agent.tools.io_utils import read_json

EDITABLE_ROLES = {"title", "header_cell", "body_cell", "footnote"}
NORMALIZE_WS = re.compile(r"\s+")


def _norm(value):
    return NORMALIZE_WS.sub(" ", str(value or "")).strip().casefold()


def _bookmarks(doc):
    starts, ends = {}, {}
    for tag in doc.part.element.xpath(".//w:bookmarkStart"):
        name, ident = tag.get(qn("w:name")), tag.get(qn("w:id"))
        if name in starts:
            raise ValueError(f"Duplicate Word bookmark name: {name}")
        starts[name] = (ident, tag)
    for tag in doc.part.element.xpath(".//w:bookmarkEnd"):
        ident = tag.get(qn("w:id"))
        if ident in ends:
            raise ValueError(f"Duplicate Word bookmark end id: {ident}")
        ends[ident] = tag
    return starts, ends


def _range(start, end):
    """Only modify a wholly bounded, single-parent OOXML bookmark range."""
    parent = start.getparent()
    if parent is None or parent is not end.getparent():
        raise ValueError("Bookmark spans different OOXML parents: manual reconstruction required")
    siblings = list(parent)
    a, b = siblings.index(start), siblings.index(end)
    if b <= a:
        raise ValueError("Bookmark end precedes start")
    covered = siblings[a + 1:b]
    # Prevent accidental edits to a whole table, a nested bookmark, or another cell.
    if any(n.tag in (qn("w:tbl"), qn("w:tc"), qn("w:bookmarkStart"),
                         qn("w:bookmarkEnd")) or
           any(child.tag in (qn("w:tbl"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"))
               for child in n.iter() if child is not n)
           for n in covered):
        raise ValueError("Complex or nested bookmark range is not auto-editable")
    texts = [t for node in covered for t in node.iter(qn("w:t"))]
    breaks = [t for node in covered for t in node.iter()
              if t.tag in (qn("w:br"), qn("w:tab"))]
    return texts, breaks


def _index_locator(locator):
    occurrences = {}
    for element in locator.get("source_elements", []):
        role = element.get("element_type")
        for occurrence in element.get("occurrences", []):
            name = occurrence.get("docx_locator")
            if not isinstance(name, str) or not name.startswith("bookmark:"):
                continue
            name = name.split(":", 1)[1]
            if name in occurrences:
                raise ValueError(f"Duplicate locator occurrence: {name}")
            occurrences[name] = {
                "element_id": element.get("element_id"),
                "element_type": role,
                "source_text": occurrence.get("source_text", ""),
                "verified": occurrence.get("verification_status") == "verified",
                "occurrence_id": occurrence.get("occurrence_id"),
                "bookmark": name,
            }
    return occurrences


def _title_for(spec):
    title = spec["identity"]["title"].strip()
    tfl_id = spec["identity"]["tfl_id"].strip()
    return title if re.match(r"(?i)^table\s+" + re.escape(tfl_id) + r"\b", title) else f"Table {tfl_id} {title}"


def _coverage(text, requirements):
    # Conservative: do not guess semantic equivalence of variables, units or footnotes.
    haystack = _norm(text)
    return [str(value) for value in requirements if _norm(value) not in haystack]


def plan_bookmark_adaptation(template_path, spec, locator_map_path, reviewed_adaptation=None):
    """Build a source-verified plan; never change the source DOCX here.

    reviewed_adaptation is a separately supplied human review record:
    {template_id, tfl_id, reviewed_by, review_reason,
     edits:[{bookmark, expected_source_text, new_text, reason}, ...]}
    """
    path = Path(template_path).resolve()
    result = {
        "template_path": str(path), "locator_map_path": str(locator_map_path),
        "editing_mode": "source_bookmarks_requires_adaptation",
        "safe_to_generate": False, "replacements": {},
        "missing_placeholders": [], "unexpected_placeholders": [],
        "edits": [], "issues": [], "warnings": [],
        "review_required": True, "bookmark_count": 0,
    }
    if spec["identity"].get("output_type") != "table":
        result["issues"].append("Bookmark adaptation currently supports Table shells only")
        result["reason"] = "; ".join(result["issues"])
        return result
    locator_file = Path(locator_map_path) if locator_map_path else None
    if not locator_file or not locator_file.is_file():
        result["issues"].append("Source DOCX locator map is absent")
        result["reason"] = "; ".join(result["issues"])
        return result
    try:
        locator = read_json(locator_file)
        boundary = locator.get("docx_boundary") or {}
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if locator.get("template_id") != path.stem:
            raise ValueError("Locator template_id does not match DOCX filename")
        if boundary.get("verification_status") != "verified":
            raise ValueError("Source DOCX locator boundary is not verified")
        if boundary.get("document_sha256") != sha:
            raise ValueError("Source DOCX SHA-256 differs from verified locator boundary")
        doc = Document(path)
        starts, ends = _bookmarks(doc)
        result["bookmark_count"] = len(starts)
        locs = _index_locator(locator)
        result["source_sha256"] = sha
        result["template_id"] = locator["template_id"]

        approval = reviewed_adaptation or {}
        if approval:
            for name in ("template_id", "tfl_id", "reviewed_by", "review_reason"):
                if not isinstance(approval.get(name), str) or not approval[name].strip():
                    raise ValueError(f"Review approval must include nonblank {name}")
            if approval["template_id"] != locator["template_id"]:
                raise ValueError("Review approval targets a different template")
            if approval["tfl_id"] != spec["identity"]["tfl_id"]:
                raise ValueError("Review approval targets a different TFL")
            if not isinstance(approval.get("edits", []), list):
                raise ValueError("Review edits must be an array")
            result["review_record"] = {k:approval[k] for k in
                                       ("template_id", "tfl_id", "reviewed_by", "review_reason")}

        title_locs = [v for v in locs.values() if v["element_type"] == "title"]
        if len(title_locs) != 1:
            raise ValueError(f"Expected exactly one bookmark-mapped title, found {len(title_locs)}")
        proposed = [{
            "bookmark": title_locs[0]["bookmark"],
            "expected_source_text": title_locs[0]["source_text"],
            "new_text": _title_for(spec),
            "reason": "Target TFL identity from Step 2",
            "field": "title",
        }]
        for edit in approval.get("edits", []):
            if not isinstance(edit, dict):
                raise ValueError("Each review edit must be an object")
            if not all(isinstance(edit.get(k), str) for k in
                       ("bookmark", "expected_source_text", "new_text", "reason")):
                raise ValueError("Review edit needs bookmark, expected_source_text, new_text, reason")
            if not edit["reason"].strip():
                raise ValueError("Review edit reason must not be blank")
            proposed.append({**edit, "field": "reviewed"})

        seen = set()
        for change in proposed:
            name = change["bookmark"]
            if name in seen:
                raise ValueError(f"Multiple edits to the same bookmark: {name}")
            seen.add(name)
            rec = locs.get(name)
            if rec is None or not rec["verified"]:
                raise ValueError(f"Missing or unverified source occurrence: {name}")
            if rec["element_type"] not in EDITABLE_ROLES:
                raise ValueError(f"Unsupported bookmark role for editing: {rec['element_type']}")
            if _norm(rec["source_text"]) != _norm(change["expected_source_text"]):
                raise ValueError(f"Source expected_text mismatch at {name}")
            item = starts.get(name)
            if not item or item[0] not in ends:
                raise ValueError(f"Source bookmark missing its start/end: {name}")
            texts, _ = _range(item[1], ends[item[0]])
            current = "".join(t.text or "" for t in texts)
            if _norm(current) != _norm(rec["source_text"]):
                raise ValueError(f"Bookmark text mismatch against verified locator: {name}")
            if not texts:
                raise ValueError(f"Bookmark has no editable text run: {name}")
            result["edits"].append({
                **change, "source_role": rec["element_type"],
                "element_id": rec["element_id"],
                "occurrence_id": rec["occurrence_id"],
                "verified": True,
            })

        # Metadata/source table geometry and statistical requirements must be
        # reconciled independently; inserting or deleting rows/columns is NOT assumed.
        rewritten = "\n".join(
            (next((e["new_text"] for e in result["edits"]
                   if e["bookmark"] == name), rec["source_text"]))
            for name, rec in locs.items()
        )
        table = spec["table_requirements"]
        requirements = {
            "rows": table.get("row_requirements", []),
            "columns": table.get("column_requirements", []),
            "footnotes": table.get("footnote_requirements", []),
        }
        for kind, values in requirements.items():
            missing = _coverage(rewritten, values)
            if missing:
                result["issues"].append(
                    f"Unmapped target {kind}: " + ", ".join(missing[:12])
                )
        source_notes = [v for v in locs.values() if v["element_type"] == "footnote"
                        and _norm(v["source_text"])]
        if source_notes:
            target_footnotes = table.get("footnote_requirements", [])
            retained = [v["source_text"] for v in source_notes
                        if v["bookmark"] not in seen]
            if not target_footnotes and retained:
                result["issues"].append(
                    "Source statistical footnotes retained without target SAP support; "
                    "explicit review and anchored replacement/removal required"
                )
            elif target_footnotes and any(_norm(x) not in {_norm(v) for v in target_footnotes}
                                          for x in retained):
                result["issues"].append(
                    "Source footnotes not supported by target specification; "
                    "edit or remove them explicitly"
                )
        # The source may contain unbookmarked sponsor branding, source
        # listings, and program notes. Never call an adapted source 'approved'.
        if any(v["element_type"] in ("other", "source_line", "programming_note")
               for v in locs.values()) or any(e.get("element_type") in
               ("other", "source_line", "programming_note")
               for e in locator.get("source_elements", [])):
            result["warnings"].append(
                "Review source-study attribution, sponsor branding, source lines, "
                "programming notes, and document headers/footers in the draft"
            )
        result["safe_to_generate"] = not result["issues"] and bool(result["edits"])
        if result["safe_to_generate"]:
            result["editing_mode"] = "verified_bookmark_draft"
        result["reason"] = ("All planned OOXML anchors verified; draft still needs statistical "
                            "and source-attribution review" if result["safe_to_generate"]
                            else "; ".join(result["issues"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["issues"].append(f"{type(exc).__name__}: {exc}")
        result["reason"] = "; ".join(result["issues"])
    return result


def _apply_one(doc, edit):
    starts, ends = _bookmarks(doc)
    ident, start = starts[edit["bookmark"]]
    texts, breaks = _range(start, ends[ident])
    if _norm("".join(t.text or "" for t in texts)) != _norm(edit["expected_source_text"]):
        raise ValueError("Bookmark content changed since plan was validated")
    first = texts[0]
    for extra in texts[1:]:
        extra.text = ""
    for node in breaks:
        node.getparent().remove(node)
    value = edit["new_text"].replace("\r\n", "\n")
    lines = value.split("\n")
    first.text = lines[0]
    if lines[0].startswith(" ") or lines[0].endswith(" "):
        first.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run = first.getparent()
    if run.tag != qn("w:r"):
        raise ValueError("Bookmarked text not held in a normal Word run")
    insert = list(run).index(first) + 1
    for line in lines[1:]:
        run.insert(insert, OxmlElement("w:br"))
        insert += 1
        t = OxmlElement("w:t")
        t.text = line
        run.insert(insert, t)
        insert += 1


def generate_bookmark_draft(template_path, spec, out_path, locator_map_path,
                            reviewed_adaptation=None):
    plan = plan_bookmark_adaptation(template_path, spec, locator_map_path, reviewed_adaptation)
    if not plan["safe_to_generate"]:
        return None, plan
    source = Path(template_path).resolve()
    dest = Path(out_path).resolve()
    if dest == source or dest.is_relative_to(source.parent):
        plan["safe_to_generate"] = False
        plan["issues"].append("Output must be outside source template directory")
        return None, plan
    doc = Document(source)
    for edit in plan["edits"]:
        _apply_one(doc, edit)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    if hashlib.sha256(source.read_bytes()).hexdigest() != plan["source_sha256"]:
        dest.unlink(missing_ok=True)
        raise RuntimeError("Source DOCX changed during generation; draft removed")
    plan["output_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
    plan["applied_bookmarks"] = [x["bookmark"] for x in plan["edits"]]
    plan["replacement_counts"] = {x["bookmark"]: 1 for x in plan["edits"]}
    return str(dest), plan
