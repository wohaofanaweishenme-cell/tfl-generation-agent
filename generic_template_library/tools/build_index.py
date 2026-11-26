"""Validate templates/presets and generate the three Agent-facing indexes (conventions v1.0 section 5.1).

Outputs (never hand-edited):
  Template_Index.json  - one summary per template (+ its presets) with path, version, SHA-256
  Keyword_Index.json   - normalised keyword/alias -> [{template_id, preset_id, field}]
  Library_Bundle.json  - full templates, presets and the style guide in one file

Checks (the script exits non-zero on any failure):
  - every template validates against schemas/Template.schema.json, every preset against Preset.schema.json
  - every preset referenced by a template exists and points back to that template
  - every keyword is in vocab/Keywords.json
  - every evidence source_id exists in inventory/Signatures.csv

Usage: .venv/bin/python tools/build_index.py
"""
import csv
import os
import sys
from collections import defaultdict

from tfl_lib import INVENTORY, ROOT, STYLE, dump, load, norm, preset_files, rel, schema_errors, sha256, template_files


def main():
    errors = []
    vocab = {k for group in load(os.path.join(ROOT, "vocab", "Keywords.json"))["groups"].values() for k in group}
    known_sources = {r["source_id"] for r in csv.DictReader(open(os.path.join(INVENTORY, "Signatures.csv"), encoding="utf-8-sig"))}
    style = load(STYLE)

    index, bundle_templates, bundle_presets = [], [], []
    kw = defaultdict(list)

    def add_kw(term, template_id, preset_id, field):
        key = norm(term)
        entry = {"template_id": template_id, "preset_id": preset_id, "field": field}
        if key and entry not in kw[key]:
            kw[key].append(entry)

    for tpath in template_files():
        t = load(tpath)
        tid = t["template_id"]
        errors += [f"{rel(tpath)}: {e}" for e in schema_errors("Template.schema.json", t)]
        errors += [f"{tid}: keyword not in vocab: {k}" for k in t["keywords"] if k not in vocab]
        errors += [f"{tid}: unknown evidence source {e['source_id']}" for e in t["evidence"] if e["source_id"] not in known_sources]
        presets = []
        found = {}
        for ppath in preset_files(tid):
            p = load(ppath)
            errors += [f"{rel(ppath)}: {e}" for e in schema_errors("Preset.schema.json", p)]
            if p["template_id"] != tid:
                errors.append(f"{rel(ppath)}: template_id {p['template_id']} != folder {tid}")
            errors += [f"{p['preset_id']}: keyword not in vocab: {k}" for k in p["keywords"] if k not in vocab]
            errors += [f"{p['preset_id']}: unknown evidence source {s}" for s in p["evidence"] if s not in known_sources]
            found[p["preset_id"]] = (p, ppath)
        for pid in t["presets"]:
            if pid not in found:
                errors.append(f"{tid}: preset {pid} listed but no file")
        for pid, (p, ppath) in found.items():
            if pid not in t["presets"]:
                errors.append(f"{tid}: preset file {pid} not listed in template")
            presets.append({"preset_id": pid, "name": p["name"], "keywords": p["keywords"], "aliases": p["aliases"],
                            "path": rel(ppath), "version": p["version"], "sha256": sha256(ppath)})
            bundle_presets.append(p)
            for k in p["keywords"]:
                add_kw(k, tid, pid, "preset_keyword")
            for a in p["aliases"]:
                add_kw(a, tid, pid, "preset_alias")
        for k in t["keywords"]:
            add_kw(k, tid, None, "keyword")
        for a in t["aliases"]:
            add_kw(a, tid, None, "alias")
        index.append({
            "template_id": tid, "version": t["version"], "output_type": t["output_type"], "name": t["name"],
            "intended_use": t["intended_use"], "not_for": t["not_for"], "keywords": t["keywords"], "aliases": t["aliases"],
            "match_cues": t["match_cues"], "required_fields": [f["path"] for f in t["required_fields"]],
            "config_options": {k: {"values": v["values"], "default": v["default"]} for k, v in t["config_options"].items()},
            "presets": presets, "evidence_sources": len(t["evidence"]),
            "evidence_studies": len({e["study_id"] for e in t["evidence"]}), "evidence_level": t["evidence_level"],
            "review_status": t["review_status"], "path": rel(tpath), "sha256": sha256(tpath),
        })
        bundle_templates.append(t)

    # approved files must match the approval record exactly (edits after approval need re-review)
    appr_path = os.path.join(ROOT, "approvals", "Approval_Record.json")
    approved = {i["path"]: i for i in load(appr_path)["current"]["items"]} if os.path.exists(appr_path) else {}
    for tpath in template_files():
        t = load(tpath)
        if t["review_status"] != "approved":
            continue
        for path in [tpath] + preset_files(t["template_id"]):
            rec = approved.get(rel(path))
            if rec is None:
                errors.append(f"{rel(path)}: template marked approved but file has no approval record")
            elif rec["sha256"] != sha256(path):
                errors.append(f"{rel(path)}: changed after approval ({rec['date'] if 'date' in rec else 'recorded'} hash differs) - re-review and re-run tools/record_approval.py")
    if approved and approved.get(rel(STYLE), {}).get("sha256") not in (None, sha256(STYLE)):
        errors.append(f"{rel(STYLE)}: style guide changed after approval")

    if errors:
        print("FAILED:")
        for e in errors:
            print("  " + e)
        sys.exit(1)

    # reference shells (derived DOCX), if built
    man_path = os.path.join(ROOT, "reference", "Reference_Library_Manifest.json")
    if os.path.exists(man_path):
        man = load(man_path)["items"]
        for entry in index:
            entry["reference_shells"] = [{"preset_id": m["preset_id"], "docx": m["docx"], "sha256": m["docx_sha256"]}
                                         for m in man if m["template_id"] == entry["template_id"]]
            stale = [m["docx"] for m in man if m["template_id"] == entry["template_id"] and m["template_sha256"] != entry["sha256"]]
            if stale:
                print("WARNING: reference shells built from an older template version; rerun tools/build_reference_library.py:", stale[:3])

    meta = {"library": "Generic_Template_Build", "style_guide_version": style["version"], "style_guide_sha256": sha256(STYLE)}
    dump({**meta, "templates": index}, os.path.join(ROOT, "Template_Index.json"))
    dump({**meta, "normalisation": "lowercase, non-alphanumerics to space", "terms": dict(sorted(kw.items()))}, os.path.join(ROOT, "Keyword_Index.json"))
    dump({**meta, "style_guide": style, "templates": bundle_templates, "presets": bundle_presets}, os.path.join(ROOT, "Library_Bundle.json"))
    print(f"OK: {len(index)} templates, {len(bundle_presets)} presets, {len(kw)} index terms")


if __name__ == "__main__":
    main()
