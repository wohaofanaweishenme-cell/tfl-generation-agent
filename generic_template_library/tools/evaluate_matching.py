"""Evaluate template selection on every content-list entry of the six studies.

Ground truth: entries whose Shell_Manifest mapping is relation=direct_shell are linked to physical
source shells; the source shell's template in inventory/Template_Clustering.csv (or 'NONSTANDARD')
is the expected template. Entries without a direct shell (shared-layout / reference-only) have no
ground truth and are reported descriptively. This is an in-library evaluation: the same sources were
used to build the templates, so it measures reproduction, not generalisation to new studies.

Usage: .venv/bin/python tools/evaluate_matching.py
Outputs: qa/matching_eval/Matching_Evaluation.csv, qa/matching_eval/Summary.json
"""
import csv
import json
import os
from collections import Counter, defaultdict

from build_spec import match
from tfl_lib import INVENTORY, ROOT, dump, load, source_library

LIBRARY = os.path.join(source_library(), "studies")


def main():
    index = load(os.path.join(ROOT, "Template_Index.json"))
    clus = {r["source_id"]: r["template_id"] for r in csv.DictReader(open(os.path.join(INVENTORY, "Template_Clustering.csv"), encoding="utf-8-sig"))}
    nonstd = {s["source_id"] for s in load(os.path.join(INVENTORY, "Nonstandard_Sources.json"))["sources"]}
    rows = []
    for study in sorted(os.listdir(LIBRARY)):
        reg = os.path.join(LIBRARY, study, "source_registry")
        if not os.path.isdir(reg):
            continue
        entries = load(os.path.join(reg, "Content_List.json"))["entries"]
        maps = {m["entry_id"]: m for m in load(os.path.join(reg, "Shell_Manifest.json")).get("content_list_mappings", [])}
        for e in entries:
            m = maps.get(e["entry_id"], {})
            exp = None
            if m.get("relation") == "direct_shell" and m.get("template_ids"):
                ts = sorted({"NONSTANDARD" if t in nonstd else clus.get(t, "UNASSIGNED") for t in m["template_ids"]})
                exp = ts[0] if len(ts) == 1 else "|".join(ts)
            tid, pid, cands, expl = match(e, index)
            pred = tid or ("AMBIGUOUS" if expl.startswith("Ambiguous") else "NO_TEMPLATE")
            if exp is None:
                outcome = "no_ground_truth"
            elif exp == "NONSTANDARD":
                outcome = "correct" if pred in ("NO_TEMPLATE", "AMBIGUOUS") else "should_be_no_template"
            elif pred == exp or pred in exp.split("|"):
                outcome = "correct"
            elif pred == "AMBIGUOUS":
                outcome = "ambiguous"
            elif pred == "NO_TEMPLATE":
                outcome = "missed"
            else:
                outcome = "wrong_template"
            rows.append({"study_id": study, "entry_id": e["entry_id"], "output_id": e["original_tfl_number"], "output_type": e["output_type"],
                         "title": e["original_title"], "relation": m.get("relation", ""), "expected": exp or "", "predicted": pred,
                         "preset": pid or "", "outcome": outcome, "explanation": expl})
    out = os.path.join(ROOT, "qa", "matching_eval")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "Matching_Evaluation.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    gt = [r for r in rows if r["outcome"] != "no_ground_truth"]
    by_type = defaultdict(Counter)
    for r in gt:
        by_type[r["output_type"]][r["outcome"]] += 1
    confusions = Counter((r["expected"], r["predicted"]) for r in gt if r["outcome"] != "correct")
    summary = {
        "entries_total": len(rows), "with_ground_truth": len(gt),
        "correct": sum(r["outcome"] == "correct" for r in gt),
        "accuracy": round(sum(r["outcome"] == "correct" for r in gt) / max(1, len(gt)), 3),
        "outcomes": dict(Counter(r["outcome"] for r in gt)),
        "by_output_type": {k: dict(v) for k, v in by_type.items()},
        "by_study": {s: dict(Counter(r["outcome"] for r in gt if r["study_id"] == s)) for s in sorted({r["study_id"] for r in gt})},
        "top_confusions": [{"expected": a, "predicted": b, "count": n} for (a, b), n in confusions.most_common(15)],
        "no_ground_truth_predictions": dict(Counter(r["predicted"] for r in rows if r["outcome"] == "no_ground_truth")),
        "caveat": "In-library evaluation: templates were derived from these same studies.",
    }
    dump(summary, os.path.join(out, "Summary.json"))
    print(json.dumps(summary, indent=1)[:3000])


if __name__ == "__main__":
    main()
