"""Stage 2: assign every source to a candidate Template (or Nonstandard) from its structural signature.

Inputs : inventory/Signatures.csv          (stage 1)
         inventory/Template_Candidates.json (candidate templates, accept rules, overrides, nonstandard list)
Outputs: inventory/Template_Clustering.csv  (one row per source: the table the user reviews)
         inventory/Template_Coverage.csv    (one row per template: counts, studies, evidence level, presets)
         inventory/Nonstandard_Sources.json

Rules: a source goes to the first template whose 'accepts' clause matches its signature
(conventions v1.0 section 2.2). Every source must land in exactly one template or in the
nonstandard list; the script fails otherwise. D2 evidence level: multi_study if the template
is supported by >= 2 studies, else single_source.

Usage (from the 'content list' folder):
    python3 Generic_Template_Build/tools/stage2_cluster.py
"""
import csv
import json
import os
from collections import Counter, defaultdict

INV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inventory")

CORE = {
    # signature parts that need no configuration beyond the template's default form
    "TBL_VARIABLE_SUMMARY": {"S3": {"GROUPS"}, "S5": {"NONE", "BY_PARAMETER"}},
    "TBL_CRITERION_COUNTS": {"S3": {"GROUPS"}, "S5": {"NONE"}},
    "TBL_CODED_TERM_HIERARCHY": {"S3": {"GROUPS"}, "S5": {"NONE"}},
    "TBL_PARAMETER_BY_VISIT": {"S3": {"GROUPS"}, "S5": {"BY_PARAM_VISIT"}},
    "TBL_TIMEPOINT_STATISTICS_COLUMNS": {"S3": {"STATS_COLS"}, "S5": {"BY_PARAM_VISIT"}},
    "TBL_SHIFT_CROSSTAB": {"S3": {"CATEGORY_COLS"}, "S5": {"BY_GROUP_BLOCK", "BY_PARAM_VISIT", "BY_PARAMETER", "NONE"}},
    "TBL_RESPONSE_RATE": {"S3": {"GROUPS", "GROUPS_PLUS_COMPARISON"}, "S5": {"NONE"}},
    "TBL_TIME_TO_EVENT": {"S3": {"GROUPS", "GROUPS_PLUS_COMPARISON"}},
    "TBL_CONTINUOUS_COMPARISON": {"S3": {"GROUPS", "GROUPS_PLUS_COMPARISON"}, "S5": {"NONE"}},
}

CONFIG_LABELS = {
    ("S3", "SINGLE"): "single all-subjects column",
    ("S3", "GROUPS_X_SUBCOL"): "group sub-columns",
    ("S3", "GROUPS_PLUS_COMPARISON"): "comparison columns",
    ("S3", "CATEGORY_COLS"): "categories as columns",
    ("S3", "GROUPS"): None,
    ("S5", "BY_GROUP_BLOCK"): "groups as row blocks",
    ("S5", "BY_PERIOD"): "repeat per period",
    ("S5", "SUBROWS_BY_CATEGORY"): "category sub-rows",
    ("S5", "BY_PARAMETER"): "repeat per parameter",
    ("S5", "BY_PARAM_VISIT"): "parameter x visit blocks",
}


def matches(sig, accept):
    for k, v in accept.items():
        val = sig[{"S1": "S1", "S2": "S2_row_axis", "S3": "S3_col_axis", "S4": "S4_cell_semantics", "S6": "S6_plot_type"}[k]]
        if isinstance(v, list):
            if val not in v:
                return False
        elif val != v:
            return False
    return True


DESCRIPTOR_FLAGS = {"threshold_categories", "parameter_specific_denominator", "mixed_rate_and_tte"}


def config_used(tid, s):
    """Return (config, descriptors): config = options the source needs beyond the template's
    default form; descriptors = informative facts that are not configuration (cell type, grain)."""
    cfg, desc = [], []
    core = CORE.get(tid, {})
    for dim, col in (("S3", "S3_col_axis"), ("S5", "S5_nesting")):
        val = s[col]
        if dim in core and val in core[dim]:
            continue
        lab = CONFIG_LABELS.get((dim, val))
        if lab:
            cfg.append(lab)
    sem = s["S4_cell_semantics"]
    if tid == "TBL_VARIABLE_SUMMARY":
        desc.append({"DESC": "continuous blocks only", "SUBJ_N_PCT": "categorical blocks only", "PK_DESC": "continuous blocks only", "DESC_MIXED": "continuous and categorical blocks"}[sem])
        if sem == "PK_DESC":
            cfg.append("geometric statistics")
    if tid == "TBL_CODED_TERM_HIERARCHY" and sem != "SUBJ_N_PCT":
        cfg.append("event counts")
    if tid == "TBL_PARAMETER_BY_VISIT":
        desc.append("continuous cells" if sem == "DESC" else "categorical cells")
    if tid == "TBL_SHIFT_CROSSTAB" and s["S3_col_axis"] == "GROUPS":
        cfg.append("long layout with transition rows")
    if tid == "LST_SUBJECT_RECORDS":
        desc.append("grain=" + s["S5_nesting"].replace("LISTING_", "").lower())
    for f in s["layout_flags"].split(";"):
        if not f or f in ("description", "image", "mixed"):
            continue
        (desc if f in DESCRIPTOR_FLAGS else cfg).append(f)
    return "; ".join(cfg), "; ".join(desc)


def main():
    sigs = list(csv.DictReader(open(os.path.join(INV, "Signatures.csv"), encoding="utf-8-sig")))
    cand = json.load(open(os.path.join(INV, "Template_Candidates.json"), encoding="utf-8"))
    tmap = {t["template_id"]: t for t in cand["templates"]}
    ov = cand["assignment_overrides"]
    nonstd = cand["nonstandard"]
    rows, nonstandard = [], []
    for s in sigs:
        sid = s["source_id"]
        if sid in nonstd:
            nonstandard.append({"source_id": sid, "study_id": s["study_id"], "title": s["title"], "signature_key": s["signature_key"], "reason": nonstd[sid]})
            continue
        hits = [t["template_id"] for t in cand["templates"] if any(matches(s, a) for a in t["accepts"])]
        o = ov.get(sid, {})
        tid = o.get("template_id") or (hits[0] if hits else None)
        if not tid:
            raise SystemExit(f"unassigned source: {sid} {s['signature_key']}")
        cfg, desc = config_used(tid, s)
        fit = o.get("fit") or ("config" if cfg else "core")
        rows.append({
            "source_id": sid, "study_id": s["study_id"], "tfl_number": s["tfl_number"], "title": s["title"],
            "template_id": tid, "template_name": tmap[tid]["name"], "fit": fit, "config_used": cfg, "descriptors": desc,
            "preset_candidate": s["content_tag"], "signature_key": s["signature_key"], "S5_nesting": s["S5_nesting"],
            "assignment_basis": "override" if "template_id" in o else "signature_rule",
            "note": o.get("note", "") or o.get("review_note", ""),
            "legacy_family_reference": s["legacy_family_reference"],
        })
    assert len(rows) + len(nonstandard) == len(sigs)
    rows.sort(key=lambda r: (list(tmap).index(r["template_id"]), r["study_id"], r["source_id"]))
    with open(os.path.join(INV, "Template_Clustering.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump({"policy": "conventions v1.0 section 2.3: not in main library; Agent must report 'no compatible template'", "sources": nonstandard},
              open(os.path.join(INV, "Nonstandard_Sources.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    by = defaultdict(list)
    for r in rows:
        by[r["template_id"]].append(r)
    cov = []
    for tid, t in tmap.items():
        rs = by.get(tid, [])
        studies = sorted({r["study_id"] for r in rs})
        cov.append({
            "template_id": tid, "output_type": t["output_type"], "name": t["name"], "sources": len(rs),
            "studies": len(studies), "study_ids": ";".join(studies),
            "evidence_level": "multi_study" if len(studies) >= 2 else "single_source",
            "fit_core": sum(r["fit"] == "core" for r in rs), "fit_config": sum(r["fit"] in ("config", "config_extension") for r in rs),
            "fit_partial": sum(r["fit"] == "partial" for r in rs),
            "preset_candidates": "; ".join(f"{k}({v})" for k, v in Counter(r["preset_candidate"] for r in rs).most_common()),
        })
    with open(os.path.join(INV, "Template_Coverage.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cov[0].keys()))
        w.writeheader()
        w.writerows(cov)
    print(f"assigned {len(rows)}  nonstandard {len(nonstandard)}  templates {len(tmap)}")
    for c in cov:
        print(f"{c['template_id']:34s} src={c['sources']:3d} studies={c['studies']} {c['evidence_level']:13s} core={c['fit_core']} config={c['fit_config']} partial={c['fit_partial']}")


if __name__ == "__main__":
    main()
