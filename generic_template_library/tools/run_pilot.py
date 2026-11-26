"""Stage 3 end-to-end pilot: content-list entries -> template match -> Shell Spec -> DOCX.

Reads examples/pilot_inputs/pilot_entries.json and study_settings_<study>.json, looks up each
entry in Library (read-only), builds and validates the Shell Spec, renders the DOCX, and writes
per-study Output_Inventory.csv and Clarification_Log.csv under examples/pilot/<study>/.

Usage: .venv/bin/python tools/run_pilot.py
"""
import csv
import os
import sys

from tfl_lib import ROOT, STYLE, dump, load, schema_errors, source_library

sys.path.insert(0, os.path.join(ROOT, "renderer"))
import render_figure  # noqa: E402
import render_table  # noqa: E402
from build_spec import build_for_entry  # noqa: E402

LIBRARY = os.path.join(source_library(), "studies")
INPUTS = os.path.join(ROOT, "examples", "pilot_inputs")
OUT = os.path.join(ROOT, "examples", "pilot")


def slots(obj, path=""):
    if isinstance(obj, dict):
        if "source" in obj and "status" in obj and "value" in obj:
            yield path, obj
        for k, v in obj.items():
            if k != "provenance":
                yield from slots(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from slots(v, f"{path}[{i}]")


def main():
    style = load(STYLE)
    plan = load(os.path.join(INPUTS, "pilot_entries.json"))["entries"]
    cl_cache, inv, clar = {}, {}, {}
    for item in plan:
        sid = item["study_id"]
        if sid not in cl_cache:
            cl_cache[sid] = {e["entry_id"]: e for e in load(os.path.join(LIBRARY, sid, "source_registry", "Content_List.json"))["entries"]}
        entry = cl_cache[sid][item["entry_id"]]
        settings = load(os.path.join(INPUTS, f"study_settings_{sid}.json"))
        errs = schema_errors("Study_Settings.schema.json", settings)
        if errs:
            raise SystemExit(f"{sid} settings invalid: {errs}")
        out_dir = os.path.join(OUT, sid)
        os.makedirs(out_dir, exist_ok=True)
        spec, nomatch = build_for_entry(entry, settings)
        base = f"{entry['output_type'][0].upper()}_{entry['original_tfl_number']}"
        row = {"entry_id": entry["entry_id"], "output_id": entry["original_tfl_number"], "output_type": entry["output_type"],
               "title": entry["original_title"], "expected": item["expect"]}
        if spec is None:
            dump(nomatch, os.path.join(out_dir, base + ".no_template.json"))
            row.update(status="no_compatible_template", template_id="", preset_id="", docx="", explanation=nomatch["explanation"])
            clar.setdefault(sid, []).append({"output_id": entry["original_tfl_number"], "question_id": "-", "kind": "no_compatible_template",
                                             "element_path": "(whole output)", "question": nomatch["explanation"]})
        else:
            dump(spec, os.path.join(out_dir, base + ".spec.json"))
            docx = os.path.join(out_dir, base + ".docx")
            if spec["output_type"] == "figure":
                tmpl = load(os.path.join(ROOT, "templates", "figure", spec["template_id"] + ".json"))
                render_figure.render(spec, style, tmpl, docx, os.path.join(out_dir, base + ".frame.png"))
            else:
                render_table.render(spec, style, docx)
            counts = {}
            for _, s in slots(spec):
                key = f"{s['source']}/{s['status']}"
                counts[key] = counts.get(key, 0) + 1
            row.update(status="generated", template_id=spec["template_id"], preset_id=";".join(spec["preset_ids"]),
                       docx=os.path.relpath(docx, ROOT), explanation=spec["provenance"]["match"]["explanation"],
                       slot_counts="; ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            for q in spec["issues"]:
                clar.setdefault(sid, []).append({"output_id": spec["output_id"], **{k: q[k] for k in ("question_id", "kind", "element_path", "question")}})
            nr = [p for p, s in slots(spec) if s["status"] == "needs_review"]
            row["needs_review_elements"] = len(nr)
        inv.setdefault(sid, []).append(row)
        print(f"{sid:15s} {entry['original_tfl_number']:12s} {row['status']:22s} {row.get('template_id',''):26s} {row.get('preset_id','')}")

    fields = ["entry_id", "output_id", "output_type", "title", "status", "template_id", "preset_id", "expected", "docx", "needs_review_elements", "slot_counts", "explanation"]
    for sid, rows in inv.items():
        with open(os.path.join(OUT, sid, "Output_Inventory.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(OUT, sid, "Clarification_Log.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["output_id", "question_id", "kind", "element_path", "question"])
            w.writeheader()
            w.writerows(clar.get(sid, []))


if __name__ == "__main__":
    main()
