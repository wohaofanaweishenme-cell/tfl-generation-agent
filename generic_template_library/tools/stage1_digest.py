"""Stage 1 step A: build a compact, read-only digest for every source shell in Library.

Reads Library/Template_Index.json and each study's Structured_Shell JSON.
Writes inventory/Source_Digests.jsonl (one JSON object per source).
Never writes into Library.

Usage (from the project root, i.e. the 'content list' folder):
    python3 Generic_Template_Build/tools/stage1_digest.py
"""
import glob
import json
import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tfl_lib import source_library  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LIB = source_library()
LEGACY = os.path.join(ROOT, "Template_Generalization")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inventory", "Source_Digests.jsonl")


def clean(s, n=None):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s[:n] if n else s


def uniq(seq):
    return list(OrderedDict.fromkeys(x for x in seq if x))


def legacy_family_map():
    """source template_id -> legacy family label(s) from old Template_Generalization (reference only)."""
    m = {}
    if not os.path.isdir(LEGACY):  # old Template_Generalization is optional (reference only)
        return m
    pats = []
    for typ in ("Table", "Listing", "Figure"):
        pats += glob.glob(os.path.join(LEGACY, typ, "families", "*", "Family_Metadata.json"))
    for p in pats:
        fam = p.split(os.sep)[-2]
        txt = open(p, encoding="utf-8").read()
        for tid in set(re.findall(r"\b[A-Z0-9]+_[TLF]_[0-9A-Za-z_]+\b", txt)):
            m.setdefault(tid, set()).add(fam)
    for p in glob.glob(os.path.join(LEGACY, "*", "source_mapping", "*.json")):
        fam = os.path.basename(p).replace("_Source_Mapping.json", "").lower()
        txt = open(p, encoding="utf-8").read()
        for tid in set(re.findall(r"\b[A-Z0-9]+_[TLF]_[0-9A-Za-z_]+\b", txt)):
            m.setdefault(tid, set()).add(fam)
    for p in glob.glob(os.path.join(LEGACY, "Restricted_Single_Source", "*", "Source_Mapping.json")):
        fam = "restricted:" + p.split(os.sep)[-2]
        txt = open(p, encoding="utf-8").read()
        for tid in set(re.findall(r"\b[A-Z0-9]+_[TLF]_[0-9A-Za-z_]+\b", txt)):
            m.setdefault(tid, set()).add(fam)
    return {k: sorted(v) for k, v in m.items()}


def table_digest(spec, d):
    rows = sorted(spec.get("rows", []), key=lambda r: r.get("order", 0))
    cols = sorted(spec.get("columns", []), key=lambda c: c.get("order", 0))
    row_labels = uniq(clean(r.get("label"), 70) for r in rows)
    col_labels = uniq(clean(c.get("label"), 60) for c in cols)
    col_roles = [c.get("role") for c in cols]
    placeholders = uniq(clean(c.get("placeholder"), 30) for c in spec.get("cell_rules", []))
    cell_text = uniq(clean(c.get("text"), 40) for c in d.get("physical_cells", []) if not c.get("is_blank"))
    return {
        "n_rows": len(rows),
        "n_cols": len(cols),
        "header_row_count": spec.get("header_row_count"),
        "col_labels": col_labels[:25],
        "col_roles": dict((r, col_roles.count(r)) for r in set(col_roles) if r),
        "row_labels": row_labels[:40],
        "row_roles": dict((r, [x.get("role") for x in rows].count(r)) for r in set(x.get("role") for x in rows) if r),
        "statistics": uniq(clean(s, 40) for s in spec.get("statistics", []) if isinstance(s, str)),
        "placeholders": placeholders[:15],
        "cell_text_sample": cell_text[:40],
        "n_panels": len(spec.get("panels", [])),
    }


def listing_digest(spec):
    cols = sorted(spec.get("columns", []), key=lambda c: c.get("order", 0))
    return {
        "n_cols": len(cols),
        "col_labels": uniq(clean(c.get("label"), 60) for c in cols)[:40],
        "group_by": spec.get("group_by"),
        "sort_by": spec.get("sort_by"),
        "record_unit": spec.get("record_unit"),
        "identifiers_displayed": [clean(x, 40) for x in spec.get("identifiers_displayed") or []],
        "n_panels": len(spec.get("panels", [])),
    }


def figure_digest(spec):
    panels = spec.get("panels", [])
    return {
        "figure_type": clean(spec.get("figure_type"), 120),
        "n_panels": len(panels),
        "panel_titles": [clean(p.get("title"), 120) for p in panels][:6],
        "x_axes": [clean((p.get("x_axis") or {}).get("label"), 80) for p in panels][:6],
        "y_axes": [clean((p.get("y_axis") or {}).get("label"), 80) for p in panels][:6],
        "groupings": spec.get("groupings"),
        "legend_items": [clean(x, 80) for x in spec.get("legend_items") or []][:8],
        "annotations": [clean(x, 120) for x in spec.get("annotations") or []][:5],
        "representation": (spec.get("source_representation") or {}).get("mode"),
        "description": clean((panels[0].get("panel_description") if panels else "") or "", 600),
    }


def main():
    index = json.load(open(os.path.join(LIB, "Template_Index.json"), encoding="utf-8"))["entries"]
    legacy = legacy_family_map()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = 0
    missing = []
    with open(OUT, "w", encoding="utf-8") as fh:
        for e in index:
            tid, study = e["template_id"], e["study_id"]
            path = os.path.join(LIB, "studies", study, "intermediate", "Structured_Shells", tid + ".json")
            if not os.path.exists(path):
                missing.append(tid)
                continue
            d = json.load(open(path, encoding="utf-8"))
            rec = {
                "source_id": tid,
                "study_id": study,
                "output_type": e.get("output_type"),
                "structural_family": d.get("structural_family"),
                "tfl_number": e.get("original_tfl_number"),
                "title": clean(e.get("original_title")),
                "footnotes": [clean(f.get("exact_text"), 200) for f in d.get("footnotes", [])][:10],
                "programming_notes": [clean(p.get("exact_text"), 200) for p in d.get("programming_notes", [])][:8],
                "legacy_family": legacy.get(tid, []),
            }
            if d.get("table_spec"):
                rec["table"] = table_digest(d["table_spec"], d)
            if d.get("listing_spec"):
                rec["listing"] = listing_digest(d["listing_spec"])
            if d.get("figure_spec"):
                rec["figure"] = figure_digest(d["figure_spec"])
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"digests written: {n}; missing structured shells: {len(missing)} {missing[:10]}")


if __name__ == "__main__":
    main()
