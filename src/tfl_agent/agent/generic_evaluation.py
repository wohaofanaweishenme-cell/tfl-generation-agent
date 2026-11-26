"""Offline reproduction of the teammate's in-library matching benchmark.

No LLM calls, no template mutation, no generated clinical shells.
Run: python -m tfl_agent.agent.generic_evaluation --repo-root . --out output/generic_phase1
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.agent.generic_retriever import retrieve_generic_baseline


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(repo_root, library=None):
    root = Path(repo_root)
    generic = root / "generic_template_library"
    library = library or load_generic_library(generic)
    with (generic / "inventory/Template_Clustering.csv").open(encoding="utf-8-sig", newline="") as f:
        cluster = {r["source_id"]: r["template_id"] for r in csv.DictReader(f)}
    nonstandard = {r["source_id"] for r in _read(generic / "inventory/Nonstandard_Sources.json")["sources"]}
    rows = []
    for study in sorted((root / "library/studies").iterdir()):
        reg = study / "source_registry"
        if not reg.is_dir():
            continue
        entries = _read(reg / "Content_List.json")["entries"]
        mapping = {m["entry_id"]: m for m in _read(reg / "Shell_Manifest.json").get("content_list_mappings", [])}
        for entry in entries:
            m = mapping.get(entry["entry_id"], {})
            expected = None
            if m.get("relation") == "direct_shell" and m.get("template_ids"):
                labels = sorted({"NONSTANDARD" if t in nonstandard else cluster[t] for t in m["template_ids"]})
                expected = "|".join(labels)
            result = retrieve_generic_baseline(entry, library)
            predicted = result["template_id"] or ("AMBIGUOUS" if result["status"] == "ambiguous_match" else "NO_TEMPLATE")
            if expected is None:
                outcome = "no_ground_truth"
            elif expected == "NONSTANDARD":
                outcome = "correct" if predicted in ("NO_TEMPLATE", "AMBIGUOUS") else "should_be_no_template"
            elif predicted in expected.split("|"):
                outcome = "correct"
            elif predicted == "AMBIGUOUS":
                outcome = "ambiguous"
            elif predicted == "NO_TEMPLATE":
                outcome = "missed"
            else:
                outcome = "wrong_template"
            rows.append({"study_id": study.name, "entry_id": entry["entry_id"],
                         "output_id": entry["original_tfl_number"], "output_type": entry["output_type"],
                         "title": entry["original_title"], "expected": expected or "",
                         "predicted": predicted, "preset": result["preset_id"] or "",
                         "outcome": outcome, "explanation": result["explanation"]})
    gt = [r for r in rows if r["outcome"] != "no_ground_truth"]
    if not gt:
        raise ValueError("No labelled source entries; cannot evaluate")
    by_type = defaultdict(Counter)
    for r in gt:
        by_type[r["output_type"]][r["outcome"]] += 1
    outcomes = Counter(r["outcome"] for r in gt)
    summary = {
        "library": library.summary(), "entries_total": len(rows), "with_ground_truth": len(gt),
        "correct": outcomes["correct"], "accuracy": round(outcomes["correct"] / len(gt), 3),
        "outcomes": dict(outcomes), "by_output_type": {k: dict(v) for k, v in by_type.items()},
        "caveat": "In-library reproduction only; not independent generalisation or clinical correctness.",
    }
    return summary, rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--out", default="output/generic_phase1")
    args = p.parse_args()
    summary, rows = evaluate(args.repo_root)
    out = Path(args.out).resolve()
    root = Path(args.repo_root).resolve()
    if any(out.is_relative_to(root / d) for d in ("library", "generic_template_library")):
        raise ValueError("Do not write into either Library")
    out.mkdir(parents=True, exist_ok=True)
    (out / "Summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (out / "Matching_Evaluation.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
