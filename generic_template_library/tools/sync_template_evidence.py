"""Copy each template's evidence list from the reviewed assignment table (inventory/Template_Clustering.csv).

The clustering table is the authority for which sources support which template; this keeps
template files in step with it. Only the 'evidence' and 'evidence_level' fields are rewritten.

Usage: .venv/bin/python tools/sync_template_evidence.py
"""
import csv
import os

from tfl_lib import INVENTORY, dump, load, rel, template_files


def main():
    rows = list(csv.DictReader(open(os.path.join(INVENTORY, "Template_Clustering.csv"), encoding="utf-8-sig")))
    for path in template_files():
        t = load(path)
        ev = [
            {k: v for k, v in {"source_id": r["source_id"], "study_id": r["study_id"], "fit": r["fit"],
                               "config_used": r["config_used"], "note": r["note"]}.items() if v != ""}
            for r in rows if r["template_id"] == t["template_id"]
        ]
        if not ev:
            raise SystemExit(f"{t['template_id']}: no sources in Template_Clustering.csv")
        t["evidence"] = ev
        t["evidence_level"] = "multi_study" if len({e["study_id"] for e in ev}) >= 2 else "single_source"
        dump(t, path)
        print(f"{rel(path)}: {len(ev)} sources, {t['evidence_level']}")


if __name__ == "__main__":
    main()
