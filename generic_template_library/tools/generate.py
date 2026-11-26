"""Generate shells for a list of content-list entries: match -> Shell Spec -> DOCX, with reviewer answers.

Usage (from Generic_Template_Build/):
  .venv/bin/python tools/generate.py --entries examples/inputs/example_entries.json --out examples/stage4 [--answers] [--round 2]

Inputs : <entries>.json            {"entries": [{"study_id", "entry_id", "expect"}]}
         examples/inputs/study_settings_<study>.json
         examples/inputs/answers_<study>.json   (only with --answers)
Outputs: <out>/<study>/<T|L|F>_<number>.spec.json / .docx (/ .frame.png for figures)
         <out>/<study>/Output_Inventory.csv        content-list entry -> output, template, preset, status
         <out>/<study>/Clarification_Log.round<N>.csv
         <out>/<study>/Question_Registry.json      stable question IDs across regenerations
Library is read-only.
"""
import argparse
import csv
import os
import re
import sys

from tfl_lib import ROOT, STYLE, dump, load, schema_errors, source_library

sys.path.insert(0, os.path.join(ROOT, "renderer"))
import render_figure  # noqa: E402
import render_listing  # noqa: E402
import render_table  # noqa: E402
from build_spec import build_for_entry  # noqa: E402

LIBRARY = os.path.join(source_library(), "studies")
INPUTS = os.path.join(ROOT, "examples", "inputs")


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--answers", action="store_true")
    ap.add_argument("--round", type=int, default=1)
    a = ap.parse_args()
    style = load(STYLE)
    index = load(os.path.join(ROOT, "Template_Index.json"))
    plan = load(os.path.join(ROOT, a.entries))["entries"]
    out_root = os.path.join(ROOT, a.out)
    cache, inv, clar, regs, ok = {}, {}, {}, {}, 0
    for item in plan:
        sid = item["study_id"]
        if sid not in cache:
            cache[sid] = {e["entry_id"]: e for e in load(os.path.join(LIBRARY, sid, "source_registry", "Content_List.json"))["entries"]}
            reg_path = os.path.join(out_root, sid, "Question_Registry.json")
            regs[sid] = load(reg_path) if os.path.exists(reg_path) else {}
        entry = cache[sid][item["entry_id"]]
        settings = load(os.path.join(INPUTS, f"study_settings_{sid}.json"))
        errs = schema_errors("Study_Settings.schema.json", settings)
        if errs:
            raise SystemExit(f"{sid} settings invalid: {errs}")
        answers = []
        ans_path = os.path.join(INPUTS, f"answers_{sid}.json")
        if a.answers and os.path.exists(ans_path):
            answers = load(ans_path)["answers"]
        out_dir = os.path.join(out_root, sid)
        os.makedirs(out_dir, exist_ok=True)
        spec, nomatch = build_for_entry(entry, settings, answers=answers, registry=regs[sid], index=index)
        base = f"{entry['output_type'][0].upper()}_{entry['original_tfl_number']}"
        row = {"entry_id": entry["entry_id"], "output_id": entry["original_tfl_number"], "output_type": entry["output_type"],
               "title": entry["original_title"], "expected": item.get("expect", "")}
        if spec is None:
            dump(nomatch, os.path.join(out_dir, base + ".no_template.json"))
            row.update(status=nomatch["status"], explanation=nomatch["explanation"])
            clar.setdefault(sid, []).append({"output_id": entry["original_tfl_number"], "output_type": entry["output_type"], "question_id": "-",
                                             "kind": nomatch["status"], "element_path": "(whole output)", "question": nomatch["explanation"]})
        else:
            dump(spec, os.path.join(out_dir, base + ".spec.json"))
            docx = os.path.join(out_dir, base + ".docx")
            if spec["output_type"] == "figure":
                tmpl = load(os.path.join(ROOT, "templates", "figure", spec["template_id"] + ".json"))
                render_figure.render(spec, style, tmpl, docx, os.path.join(out_dir, base + ".frame.png"))
            elif spec["output_type"] == "listing":
                render_listing.render(spec, style, docx)
            else:
                render_table.render(spec, style, docx)
            counts = {}
            for _, s in slots(spec):
                counts[f"{s['source']}/{s['status']}"] = counts.get(f"{s['source']}/{s['status']}", 0) + 1
            got = spec["template_id"] + "/" + (spec["preset_ids"][0] if spec["preset_ids"] else "-")
            exp = item.get("expect", "")
            row.update(status="generated", template_id=spec["template_id"], preset_id=";".join(spec["preset_ids"]),
                       matches_expected="yes" if exp and exp.split(" ")[0] == got else ("template only" if exp.split("/")[0] == spec["template_id"] else "no"),
                       docx=os.path.relpath(docx, ROOT), explanation=spec["provenance"]["match"]["explanation"],
                       needs_review_elements=sum(1 for _, s in slots(spec) if s["status"] == "needs_review"),
                       unresolved_elements=sum(1 for _, s in slots(spec) if s["status"] == "unresolved"),
                       slot_counts="; ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            for q in spec["issues"]:
                clar.setdefault(sid, []).append({"output_id": spec["output_id"], "output_type": spec["output_type"], **{k: q[k] for k in ("question_id", "kind", "element_path", "question")}})
            ok += 1
        inv.setdefault(sid, []).append(row)
        print(f"{sid:15s} {entry['output_type'][:3]} {entry['original_tfl_number']:12s} {row['status']:22s} {row.get('template_id',''):34s} {row.get('preset_id',''):28s} {row.get('matches_expected','')}")

    fields = ["entry_id", "output_id", "output_type", "title", "status", "template_id", "preset_id", "expected", "matches_expected", "docx",
              "needs_review_elements", "unresolved_elements", "slot_counts", "explanation"]
    for sid, rows in inv.items():
        with open(os.path.join(out_root, sid, "Output_Inventory.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(out_root, sid, f"Clarification_Log.round{a.round}.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["output_id", "output_type", "question_id", "kind", "element_path", "question"])
            w.writeheader()
            w.writerows(clar.get(sid, []))
        dump(regs[sid], os.path.join(out_root, sid, "Question_Registry.json"))
        # one line per missing study setting, so the reviewer answers each setting once
        agg = {}
        for q in clar.get(sid, []):
            m = re.search(r"study setting\(s\): ([^(]+?) \(", q["question"]) or re.search(r"study setting '([^']+)'", q["question"])
            key = m.group(1).strip() if m else q["element_path"]
            agg.setdefault(key, []).append("%s:%s %s" % (q["output_id"], q["output_type"], q["question_id"]))
        with open(os.path.join(out_root, sid, f"Settings_To_Confirm.round{a.round}.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["setting_or_element", "questions", "count"])
            for k, v in sorted(agg.items(), key=lambda kv: -len(kv[1])):
                w.writerow([k, "; ".join(v), len(v)])
    print(f"generated {ok} of {len(plan)}")


if __name__ == "__main__":
    main()
