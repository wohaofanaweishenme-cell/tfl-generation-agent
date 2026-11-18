"""Minimal fail-closed DOCX executor for *manually approved* text edits.

Stage B.6 supports only REPLACE_TITLE and REPLACE_HEADER_CANDIDATE.  It never
inserts/deletes Word rows or columns, changes footnotes, or changes statistical
definitions.  Approved text is replaced within a UNIQUE Word bookmark span
in a COPY of the authentic, SHA-verified source DOCX.

An adaptation plan, even with a verified source quotation, is *not* approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.oxml.ns import qn

SUPPORTED_ACTIONS = frozenset(("REPLACE_TITLE", "REPLACE_HEADER_CANDIDATE"))
TITLE_NUMBER_ONLY = re.compile(r"^Table\s+\d[\d.\-]*\s*$", re.IGNORECASE)


def _digest_json(data):
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()


def _normal(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _expected_replacement(op, plan):
    """List only replacements derivable without inventing study-specific data.

    Header alternatives preserve an N=xx / n(%) suffix *only* if the source
    already includes it. Unknown source-study N values are prohibited.
    """
    target = op.get("target") or {}
    source = op.get("source") or {}
    if op["action"] == "REPLACE_TITLE":
        tfl_id = str(plan.get("target_tfl_id") or "")
        title = str(plan.get("target_title") or "")
        if not tfl_id or not title:
            return []
        orig = _normal(source.get("text"))
        short = f"Table {tfl_id}"
        if TITLE_NUMBER_ONLY.fullmatch(orig):
            return [short]
        # A full-title source may be replaced with a target title ONLY
        # after an exact Word bookmark-span verification.
        return [f"{short} {title}"]
    if op["action"] == "REPLACE_HEADER_CANDIDATE":
        name = _normal(target.get("label"))
        original = _normal(source.get("label") or source.get("text"))
        if not name:
            return []
        allowed = [name]
        match = re.search(
            r"(\s*\(\s*N\s*=\s*x{2,3}\s*\)(?:\s*n\s*\(\s*%\s*\))?)\s*$",
            original, re.IGNORECASE,
        )
        if match:
            allowed.append(name + match.group(1))
        return list(dict.fromkeys(allowed))
    return []


def _bookmark_span(document, bookmark):
    """Return (paragraph, text-nodes, old_text); refuse complex Word ranges."""
    root = document.part.element
    starts = [
        n for n in root.xpath(".//w:bookmarkStart")
        if n.get(qn("w:name")) == bookmark
    ]
    if len(starts) != 1:
        raise ValueError(f"Bookmark name must be unique: {bookmark!r}")
    start = starts[0]
    ident = start.get(qn("w:id"))
    ends = [
        n for n in root.xpath(".//w:bookmarkEnd")
        if n.get(qn("w:id")) == ident
    ]
    if len(ends) != 1:
        raise ValueError("Bookmark must have exactly one matching end")
    end = ends[0]
    def parent_paragraph(node):
        p = node
        while p is not None and p.tag != qn("w:p"):
            p = p.getparent()
        return p
    paragraph = parent_paragraph(start)
    if paragraph is None or paragraph is not parent_paragraph(end):
        raise ValueError("Bookmark span must be contained in one Word paragraph")
    all_nodes = list(paragraph.iter())
    begin, finish = all_nodes.index(start), all_nodes.index(end)
    if finish <= begin:
        raise ValueError("Reversed or invalid bookmark span")
    covered = all_nodes[begin+1:finish]
    if any(n.tag in (qn("w:instrText"), qn("w:drawing"), qn("w:tab"),
                     qn("w:br"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"))
           for n in covered):
        raise ValueError("Complex bookmark range cannot be safely text-edited")
    nodes = [n for n in covered if n.tag == qn("w:t")]
    if not nodes:
        raise ValueError("No Word text nodes inside bookmarked range")
    return paragraph, nodes, "".join(n.text or "" for n in nodes)


def _replace_bookmark(document, bookmark, before, after):
    _, nodes, actual = _bookmark_span(document, bookmark)
    if _normal(actual) != _normal(before):
        raise ValueError(
            f"Source bookmark text differs from plan: {bookmark!r}, "
            f"actual={actual[:100]!r}, planned={str(before)[:100]!r}"
        )
    # Replace only text XML; preserve original paragraph/table/run properties.
    nodes[0].text = after
    nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for node in nodes[1:]:
        node.text = ""


def build_pending_review_packet(plan):
    """Create review worksheet (nothing is approved by this function)."""
    choices = []
    for op in plan.get("operations") or []:
        status = (op.get("operation_readiness") or {})
        if (op.get("action") not in SUPPORTED_ACTIONS
                or not status.get("executor_supported_action")):
            continue
        src = op.get("source") or {}
        choices.append({
            "op_id": op["op_id"],
            "action": op["action"],
            "bookmark": src.get("bookmark"),
            "source_text": src.get("text") or src.get("label"),
            "target": op.get("target"),
            "allowed_replacement_texts": _expected_replacement(op, plan),
            "decision": "pending",
            "replacement_text": "",
            "review_note": "",
        })
    return {
        "review_packet_version": "docx-approval-1.0",
        "target_tfl_id": plan.get("target_tfl_id"),
        "source_template_id": plan.get("source_template_id"),
        "source_sha256": (plan.get("source_integrity") or {}).get("sha256"),
        "plan_sha256": _digest_json(plan),
        "reviewer": "",
        "approval_context": "manual_text_replacement_only_not_clinical_approval",
        "operations": choices,
    }


def execute_approved_docx_edits(plan, review_packet, *,
                                source_docx, output_docx):
    """Apply individually approved text edits to a new DOCX, with an audit.

    Validation is deliberately strict. Never call this automatically in a
    planning notebook: a reviewer must explicitly set reviewer, decision,
    and selected replacement_text in a packet bound to the exact plan SHA.
    """
    if (plan.get("planning_gate") or {}).get("status") == "blocked":
        raise ValueError("Blocked target: diagnostic Plan cannot be executed")
    if plan.get("adaptation_mode") not in (
        "structural_edit_candidate", "text_or_structural_edit_candidate"
    ):
        raise ValueError("Incompatible layout for minimal DOCX text executor")
    if plan.get("execution_status") != "not_executed":
        raise ValueError("Unexpected plan execution status")
    src = Path(source_docx).resolve()
    dst = Path(output_docx).resolve()
    if not src.is_file() or src.suffix.lower() != ".docx":
        raise FileNotFoundError("Source DOCX missing")
    if src == dst or dst.parent == src.parent:
        raise ValueError("Executor cannot overwrite source or write into source template folder")
    if dst.exists():
        raise FileExistsError("Destination DOCX already exists")
    if dst.suffix.lower() != ".docx":
        raise ValueError("Destination must be a .docx file")
    source_digest = hashlib.sha256(src.read_bytes()).hexdigest()
    if (plan.get("source_integrity") or {}).get("sha256") != source_digest:
        raise ValueError("Source DOCX SHA does not match adaptation Plan")
    if src.stem != plan.get("source_template_id"):
        raise ValueError("Source template ID differs from approved Plan")
    if not isinstance(review_packet, dict):
        raise ValueError("An explicit review packet is required")
    if review_packet.get("plan_sha256") != _digest_json(plan):
        raise ValueError("Approval packet is stale or belongs to another Plan")
    if review_packet.get("source_sha256") != source_digest:
        raise ValueError("Approval packet source SHA mismatch")
    if (review_packet.get("source_template_id") != plan["source_template_id"]
            or review_packet.get("target_tfl_id") != plan["target_tfl_id"]):
        raise ValueError("Approval packet target/source identity mismatch")
    reviewer = _normal(review_packet.get("reviewer"))
    if len(reviewer) < 3:
        raise ValueError("A named reviewer must explicitly approve edits")

    by_id = {op["op_id"]: op for op in plan["operations"]}
    requested = review_packet.get("operations") or []
    if len({x.get("op_id") for x in requested}) != len(requested):
        raise ValueError("Duplicate approval operation IDs")
    approved = [x for x in requested if x.get("decision") == "approved"]
    if not approved:
        raise ValueError("No approved operations; DOCX remains unchanged")
    doc = Document(src)
    edits = []
    used_bookmarks = set()
    for selected in approved:
        op_id = selected.get("op_id")
        op = by_id.get(op_id)
        if not op or op.get("action") not in SUPPORTED_ACTIONS:
            raise ValueError("Unsupported or nonexistent approved operation")
        r = op.get("operation_readiness") or {}
        if not r.get("executor_supported_action") or r.get("status") != "review_candidate":
            raise ValueError(f"Operation {op_id} is not eligible for executor review")
        item = op.get("source") or {}
        bookmark = item.get("bookmark")
        if not bookmark or bookmark in used_bookmarks:
            raise ValueError("Source bookmark missing or duplicated across edits")
        used_bookmarks.add(bookmark)
        old = item.get("text") or item.get("label")
        replacement = selected.get("replacement_text")
        if not isinstance(replacement, str) or replacement not in _expected_replacement(op, plan):
            raise ValueError(f"Unapproved replacement text for {op_id}")
        _replace_bookmark(doc, bookmark, old, replacement)
        edits.append({
            "op_id": op_id, "bookmark": bookmark, "action": op["action"],
            "old_text": old, "new_text": replacement,
            "reviewer": reviewer,
        })
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Save to temp file in OUTPUT folder, validate it, then atomically publish.
    temp = dst.with_name(dst.stem + ".unapproved_tmp.docx")
    if temp.exists():
        raise FileExistsError("Temporary destination already exists")
    try:
        doc.save(temp)
        verified = Document(temp)
        for changed in edits:
            _, _, new_text = _bookmark_span(verified, changed["bookmark"])
            if _normal(new_text) != _normal(changed["new_text"]):
                raise ValueError("Saved Word text failed bookmark round-trip verification")
        if hashlib.sha256(src.read_bytes()).hexdigest() != source_digest:
            raise ValueError("Original source DOCX changed during execution")
        temp.rename(dst)
    finally:
        if temp.exists():
            temp.unlink()
    return {
        "status": "text_edits_applied_to_unapproved_copy",
        "output_docx": str(dst),
        "source_docx_unchanged": True,
        "source_sha256": source_digest,
        "plan_sha256": _digest_json(plan),
        "applied_operations": edits,
        "applied_count": len(edits),
        "clinical_approval": False,
        "layout_validation": "not_performed",
        "statistical_validation": "not_performed",
        "limitations": [
            "This is NOT a completed target TFL shell",
            "Only explicitly approved bookmarked text fragments were changed",
            "Rows/columns, footnotes, and statistics were not structurally adapted",
            "Rendered-page quality assurance and clinical review are required",
        ],
    }
