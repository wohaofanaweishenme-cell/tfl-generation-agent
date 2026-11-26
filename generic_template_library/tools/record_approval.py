"""Record a human approval of the current template library version.

Writes approvals/Approval_Record.json with the SHA-256 of every approved template, preset and the
style guide. tools/build_index.py refuses to build if an approved file no longer matches its recorded
hash, so any edit after approval is caught and must be re-reviewed and re-recorded.

Usage: .venv/bin/python tools/record_approval.py --approved-by "<role or name>" --date YYYY-MM-DD --basis "<how approval was given>"
Only run this when the person responsible has explicitly approved the library.
"""
import argparse
import os

from tfl_lib import ROOT, STYLE, dump, load, preset_files, rel, sha256, template_files

SCOPE = (
    "Approval covers each template's structure, intended use / not-for boundaries, required fields, config options, "
    "skeleton footnotes and programming notes (approved display conventions), and each preset as an approved set of "
    "CANDIDATE topic content. It does not approve study-specific values: preset variable / category / field lists remain "
    "needs_review in every generated shell until the study team confirms them, and analysis definitions remain unresolved "
    "until supplied in study settings."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved-by", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--basis", required=True)
    a = ap.parse_args()
    items = []
    for tp in template_files():
        t = load(tp)
        if t["review_status"] != "approved":
            continue
        items.append({"kind": "template", "id": t["template_id"], "version": t["version"], "path": rel(tp), "sha256": sha256(tp)})
        for pp in preset_files(t["template_id"]):
            p = load(pp)
            items.append({"kind": "preset", "id": "%s/%s" % (t["template_id"], p["preset_id"]), "version": p["version"], "path": rel(pp), "sha256": sha256(pp)})
    style = load(STYLE)
    items.append({"kind": "style_guide", "id": "HOUSE_STYLE", "version": style["version"], "path": rel(STYLE), "sha256": sha256(STYLE)})
    path = os.path.join(ROOT, "approvals", "Approval_Record.json")
    history = load(path)["history"] if os.path.exists(path) else []
    record = {"approved_by": a.approved_by, "date": a.date, "basis": a.basis, "scope": SCOPE, "items": items}
    dump({"current": record, "history": history + [{k: record[k] for k in ("approved_by", "date", "basis")} | {"item_count": len(items)}]}, path)
    print(f"recorded approval of {sum(i['kind']=='template' for i in items)} templates, {sum(i['kind']=='preset' for i in items)} presets and the style guide")


if __name__ == "__main__":
    main()
