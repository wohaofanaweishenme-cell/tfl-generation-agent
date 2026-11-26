"""Build the human-facing reference library: one DOCX per (template, preset) in TFL_Template_Library/<type>/.

The DOCX files are DERIVED from templates/ + presets/ + style/ using neutral reference settings
(reference/Reference_Study_Settings.json: generic group names, no study definitions). Never edit them by
hand: change the JSON and rebuild. Unresolved markers in these shells show exactly what each study
must supply. A manifest with SHA-256 per file is written to reference/Reference_Library_Manifest.json and
picked up by tools/build_index.py.

Usage: .venv/bin/python tools/build_reference_library.py
"""
import os
import shutil
import sys

from build_spec import Builder
from tfl_lib import ROOT, STYLE, dump, load, preset_files, rel, schema_errors, sha256, template_files

sys.path.insert(0, os.path.join(ROOT, "renderer"))
import render_figure  # noqa: E402
import render_listing  # noqa: E402
import render_table  # noqa: E402

OUT = os.path.join(ROOT, "TFL_Template_Library")
REF = os.path.join(ROOT, "reference")


def main():
    style = load(STYLE)
    settings = load(os.path.join(REF, "Reference_Study_Settings.json"))
    errs = schema_errors("Study_Settings.schema.json", settings)
    if errs:
        raise SystemExit(errs)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    specs_dir = os.path.join(REF, "specs")
    if os.path.isdir(specs_dir):
        shutil.rmtree(specs_dir)
    os.makedirs(specs_dir)
    items = []
    for tpath in template_files():
        t = load(tpath)
        typ = t["output_type"]
        os.makedirs(os.path.join(OUT, typ), exist_ok=True)
        for ppath in preset_files(t["template_id"]):
            p = load(ppath)
            name = "%s__%s" % (t["template_id"], p["preset_id"])
            entry = {"entry_id": "REF_" + name, "original_tfl_number": "x.x.x", "output_type": typ,
                     "original_title": p["name"], "population": "[Analysis population]"}
            spec = Builder(entry, settings, t, tpath, p, ppath, style, registry={}).build()
            spec["provenance"]["match"] = {"selected": t["template_id"], "candidates": [], "explanation": "Reference shell: template and preset chosen directly (no matching)."}
            errs = schema_errors("Shell_Spec.schema.json", spec)
            if errs:
                raise SystemExit("%s: %s" % (name, errs[:5]))
            dump(spec, os.path.join(specs_dir, name + ".spec.json"))
            docx = os.path.join(OUT, typ, name + ".docx")
            if typ == "figure":
                png = os.path.join(specs_dir, name + ".frame.png")
                render_figure.render(spec, style, t, docx, png)
            elif typ == "listing":
                render_listing.render(spec, style, docx)
            else:
                render_table.render(spec, style, docx)
            items.append({"template_id": t["template_id"], "template_version": t["version"], "preset_id": p["preset_id"], "preset_version": p["version"],
                          "docx": rel(docx), "docx_sha256": sha256(docx), "spec": rel(os.path.join(specs_dir, name + ".spec.json")),
                          "template_sha256": sha256(tpath), "preset_sha256": sha256(ppath),
                          "unresolved_questions": len(spec["issues"])})
    dump({"description": "Reference shells derived from templates + presets with neutral settings; regenerate, never hand-edit.",
          "settings": rel(os.path.join(REF, "Reference_Study_Settings.json")), "style_guide_version": style["version"],
          "count": len(items), "items": items}, os.path.join(REF, "Reference_Library_Manifest.json"))
    by = {}
    for i in items:
        by[i["docx"].split("/")[1]] = by.get(i["docx"].split("/")[1], 0) + 1
    print("reference shells:", len(items), by)


if __name__ == "__main__":
    main()
