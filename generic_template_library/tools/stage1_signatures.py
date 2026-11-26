"""Stage 1 step B: assign a structural signature (S1-S6, conventions v1.0 section 2.1) to every source.

Input : inventory/Source_Digests.jsonl  (from stage1_digest.py)
        inventory/Signature_Overrides.json (manual decisions, each with a reason)
Output: inventory/Signatures.csv  (one row per source)
        inventory/Signature_Vocabulary.json (allowed values for each dimension)

Signature = structure only. Clinical topic is recorded separately in content_tag and
never decides the signature. Rules are deliberately simple and ordered; anything they
cannot settle is handled by an explicit override, so every assignment is traceable.

Usage (from the 'content list' folder):
    python3 Generic_Template_Build/tools/stage1_signatures.py
"""
import csv
import json
import os
import re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
INV = os.path.join(HERE, "..", "inventory")

VOCAB = {
    "S1_output_type": ["table", "listing", "figure"],
    "S2_row_axis": {
        "VAR_BLOCKS": "Ordered variable blocks; each variable continuous (statistic rows) or categorical (category rows). No timepoint dimension.",
        "CATEGORY_LIST": "One or a few predefined subject-status/category lists (disposition, analysis sets, deviations, deaths, AE overview flags).",
        "CODED_HIERARCHY": "Dictionary-coded terms (SOC/PT, ATC/PN, AESI category/PT, PT only), data-driven rows, 1-2 levels.",
        "BY_TIMEPOINT": "Parameter x visit/timepoint rows; cell content continuous or categorical (S4 decides).",
        "CROSSTAB": "Category-by-category cross-classification (baseline vs post-baseline shift, concordance of two assessments).",
        "ENDPOINT_ANALYSIS": "Endpoint summary rows mixed with inferential rows (rates with CI, KM medians, model estimates, tests).",
        "SUBJECT_RECORDS": "Listing: one row per record; record fields as columns.",
        "REFERENCE_CATALOG": "Listing without subjects: a catalog of protocol items (e.g. eligibility criteria text).",
        "PLOT": "Figure.",
    },
    "S3_col_axis": {
        "GROUPS": "Repeated treatment/cohort group columns, optional Total.",
        "GROUPS_PLUS_COMPARISON": "Group columns followed by between-group comparison columns (difference, OR, HR, p-value).",
        "GROUPS_X_SUBCOL": "Each group split into fixed sub-columns (e.g. n(%) and events, N' and n(%)).",
        "CATEGORY_COLS": "Columns are categories of an outcome (post-baseline category, grade, disposition status).",
        "STATS_COLS": "Columns are statistics (n, Mean, SD, ...); groups/timepoints on rows or pages.",
        "SINGLE": "One summary column (all subjects).",
        "RECORD_FIELDS": "Listing record fields.",
        "AXES": "Figure axes.",
    },
    "S4_cell_semantics": {
        "SUBJ_N_PCT": "Subject counts with percentages.",
        "SUBJ_AND_EVENTS": "Subject counts/percentages plus event counts.",
        "EVENTS": "Event counts (with or without percentage of events).",
        "DESC": "Descriptive statistics of a continuous variable.",
        "DESC_MIXED": "Continuous descriptive and categorical n(%) blocks in the same table.",
        "PK_DESC": "Descriptive statistics including geometric mean / CV%.",
        "RATE_CI": "Proportions with confidence intervals (optionally with between-group test).",
        "MODEL_EST": "Model-based or nonparametric estimates (LS means, differences, Hodges-Lehmann) with CI/p.",
        "TTE_EST": "Time-to-event estimates (events/censored, KM quantiles with CI, HR, log-rank).",
        "RAW_VALUES": "Listing raw/derived record values.",
        "PLOT": "Figure.",
    },
    "S5_nesting": {
        "NONE": "No additional nesting.",
        "BY_PARAMETER": "Repeated per parameter/variable.",
        "BY_VISIT": "Repeated per visit/timepoint.",
        "BY_PARAM_VISIT": "Parameter blocks, each repeated per visit.",
        "BY_GROUP_BLOCK": "Treatment groups appear as row blocks instead of columns.",
        "BY_PERIOD": "Repeated per cycle/phase/period.",
        "SUBROWS_BY_CATEGORY": "Each term row split into category sub-rows (grade, severity, relationship).",
        "LISTING_SUBJECT": "Listing grain: one record per subject.",
        "LISTING_SUBJECT_EVENT": "Listing grain: multiple coded/numbered records per subject (no visit axis).",
        "LISTING_SUBJECT_VISIT": "Listing grain: subject x visit, measures as columns (wide).",
        "LISTING_SUBJECT_PARAM_VISIT": "Listing grain: subject x parameter x visit (long).",
        "LISTING_CATALOG": "Listing grain: protocol items.",
        "PANELS": "Figure: multiple panels.",
    },
    "S6_plot_type": {
        "KM": "Kaplan-Meier survival curves (optional at-risk table).",
        "SUMMARY_OVER_TIME": "Group summary statistic (mean / percentage) over time.",
        "INDIVIDUAL_PROFILE": "Individual subject trajectories over time (spider / spaghetti).",
        "BOX": "Box plot by group.",
        "WATERFALL": "Ordered per-subject bars of best change.",
        "TORNADO": "Mirrored horizontal bars by term for two groups.",
        "": "Not a figure.",
    },
}


def low(s):
    return (s or "").lower()


def has(pat, text):
    return re.search(pat, text, re.I) is not None


def core_title(title):
    """Title without table number prefix, population qualifier and study-part suffix.

    Population words ('Safety Analysis Set', 'FAS', ...) and part/arm suffixes
    ('Dose Escalation', 'Part 1') must not drive structure or topic decisions.
    """
    t = low(title)
    t = re.sub(r"^table [\d.\-]+\s*-\s*", "", t)
    t = re.sub(r"\([^)]*(set|population|subjects|patients enrolled)[^)]*\)", " ", t)
    t = re.sub(r"[–-]\s*(dose escalation|dose expansion|expansion|part \d)\b.*$", " ", t)
    t = re.sub(r"[–-]\s*(safety analysis set|fas|randomized subjects|all subjects|immunogenicity analysis set)\s*$", " ", t)
    t = re.sub(r"\b(safety|full|intent-to-treat|pharmacodynamic) analysis set\b|\bfas\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def classify_listing(d):
    cols = " | ".join((d.get("listing") or {}).get("col_labels", []))
    t = low(d["title"])
    multi = (d.get("listing") or {}).get("n_panels", 1) > 1
    if not has(r"subject|patient|center", cols) and has(r"criteri", t + cols):
        grain = "LISTING_CATALOG"
        s2 = "REFERENCE_CATALOG"
    else:
        s2 = "SUBJECT_RECORDS"
        visit = has(r"\bvisit|time ?point|assessment timepoint|\bcycle\b|\bperiod\b", cols)
        param = has(r"parameter|\btest\b|analyte|\bscale\b|\bquestion\b|\bitems?\b|tumor marker\b", cols)
        event = has(r"system organ|soc|preferred|atc|event number|deviation|lesion|medication|therapy|criteria number|line of therapy|condition|disease name|procedure|surgery|radiation|agent|cytology|specimen|sample site|biomarker", cols)
        if visit and param:
            grain = "LISTING_SUBJECT_PARAM_VISIT"
        elif visit:
            grain = "LISTING_SUBJECT_VISIT"
        elif event or param:
            grain = "LISTING_SUBJECT_EVENT"
        else:
            grain = "LISTING_SUBJECT"
    return {
        "S1": "listing", "S2": s2, "S3": "RECORD_FIELDS", "S4": "RAW_VALUES", "S5": grain, "S6": "",
        "layout_flags": ";".join(f for f, on in [("multi_panel", multi), ("group_header", bool((d.get("listing") or {}).get("group_by"))), ("stacked_cells", "/" in cols)] if on),
        "rule": "listing_grain_rule",
    }


def classify_figure(d):
    f = d.get("figure") or {}
    t = low(d["title"]) + " " + low(f.get("figure_type"))
    if has(r"kaplan|survival|\brfs\b|ttp", t) and not has(r"ecog", t):
        pt = "KM"
    elif has(r"spider|individual", t):
        pt = "INDIVIDUAL_PROFILE"
    elif has(r"box", t):
        pt = "BOX"
    elif has(r"waterfall", t):
        pt = "WATERFALL"
    elif has(r"tornado", t):
        pt = "TORNADO"
    elif has(r"mean|ecog|changes of", t):
        pt = "SUMMARY_OVER_TIME"
    else:
        pt = "UNKNOWN"
    return {"S1": "figure", "S2": "PLOT", "S3": "AXES", "S4": "PLOT",
            "S5": "PANELS" if f.get("n_panels", 1) > 1 else "NONE", "S6": pt,
            "layout_flags": f.get("representation") or "", "rule": "figure_type_rule"}


def classify_table(d):
    tb = d.get("table") or {}
    t = low(d["title"])
    cols = " | ".join(tb.get("col_labels", []))
    rows = " | ".join(tb.get("row_labels", []))
    allt = " ".join([t, cols, rows])
    comp_cols = has(r"difference|odds ratio|hazard ratio|p-value", cols)
    desc = has(r"\bmean\b|median|standard deviation|\bsd\b|\bstd\b", rows + " " + cols)
    counts = has(r"n ?\(%\)|n\(%\)|\[n \(%\)\]|%", allt)
    visit_rows = has(r"baseline|visit|cycle|day \d|day x|screening|\bbas\b|c\d trt|time ?point", rows + " " + cols)
    out = {"S1": "table", "S6": "", "layout_flags": ""}

    if has(r"shift|concordance", t):
        cat_cols = has(r"normal|grade|\blow\b|\bhigh\b|\b[0-4]\b|score|tumor si", cols)
        grp_rows = has(r"n ?= ?x|\(n=|arv-471 ?200|wtx-330 0\.|f-627|treat[e]?ment group", rows)
        out.update(S2="CROSSTAB", S3="CATEGORY_COLS" if cat_cols else "GROUPS", S4="SUBJ_N_PCT",
                   S5="BY_GROUP_BLOCK" if grp_rows else ("BY_PARAM_VISIT" if visit_rows else "BY_PARAMETER"),
                   rule="crosstab_title")
        return out

    if has(r"system organ class|preferred term|\bsoc\b|\batc\b|therapeutic class|special interest|smq|medical history|prior medication|concomitant medication|subsequent anticancer", t):
        grade_cols = has(r"grade 1|grade 2|ctc grade", cols)
        if has(r"number of events / subjects", cols):
            s4 = "SUBJ_AND_EVENTS"
        elif has(r"number of events", cols):
            s4 = "EVENTS"
        else:
            s4 = "SUBJ_N_PCT"
        sub = has(r"severity|grade|relationship|causality|relation", t) and not grade_cols
        out.update(S2="CODED_HIERARCHY", S3="CATEGORY_COLS" if grade_cols else ("GROUPS_X_SUBCOL" if s4 != "SUBJ_N_PCT" else "GROUPS"),
                   S4=s4, S5="SUBROWS_BY_CATEGORY" if sub else "NONE", rule="coded_term_title")
        return out

    if has(r"overall survival|survival \(|duration of response|recurrence-free|progression free|\bpfs\b|time to", t) and not has(r"landmark", t):
        out.update(S2="ENDPOINT_ANALYSIS", S3="GROUPS_PLUS_COMPARISON" if comp_cols else "GROUPS", S4="TTE_EST",
                   S5="NONE", rule="tte_title")
        return out

    if has(r"lsm|hodges|least square|difference in", rows):
        out.update(S2="ENDPOINT_ANALYSIS", S3="GROUPS_PLUS_COMPARISON" if comp_cols else "GROUPS", S4="MODEL_EST",
                   S5="NONE", rule="model_rows")
        return out

    if has(r"confidence interval|exact ci|\bci\b|wilson|cochran|p-value", rows + " " + cols) and has(r"rate|response|incidence|landmark|benefit", t):
        out.update(S2="ENDPOINT_ANALYSIS", S3="GROUPS_PLUS_COMPARISON" if comp_cols else "GROUPS", S4="RATE_CI",
                   S5="NONE", rule="rate_ci")
        return out

    if has(r"concentration", t):
        out.update(S2="BY_TIMEPOINT", S3="STATS_COLS", S4="PK_DESC", S5="BY_PARAM_VISIT", rule="pk_concentration")
        return out
    if has(r"pharmacokinetic parameter", t):
        out.update(S2="VAR_BLOCKS", S3="GROUPS", S4="PK_DESC", S5="BY_PARAMETER", rule="pk_parameters")
        return out

    t_core = core_title(d["title"])
    if has(r"disposition|^(summary of )?analysis sets?\b|analysis populations|protocol deviation|deviations from|death|overview|overall summary|summary of treatment emergent adverse events|^adverse events|dose-limiting|causality|anti-drug antibody|immunogenicity|radical cystectomy|tumor bio|post-baseline tumor assessment", t_core):
        out.update(S2="CATEGORY_LIST", S3="SINGLE" if has(r"^number of (patients|subjects)|^all subjects", cols) else "GROUPS",
                   S4="SUBJ_N_PCT", S5="NONE", rule="category_title")
        return out

    if visit_rows and has(r"visit|by time|hematology|biochemistry|laboratory|vital|ecg|temperature|physical exam|qlq|questionnaire|tumor marker|pharmacodynamic|autoimmune|ecog|urinalysis|ultrasound|change|qtc|abnormal|clinically significant|categor|pregnancy|response", t):
        out.update(S2="BY_TIMEPOINT", S3="GROUPS", S4="DESC" if desc else "SUBJ_N_PCT",
                   S5="BY_PARAM_VISIT", rule="timepoint_title_rows")
        return out

    out.update(S2="VAR_BLOCKS", S3="GROUPS_PLUS_COMPARISON" if comp_cols else "GROUPS",
               S4="DESC_MIXED" if (desc and counts) else ("DESC" if desc else "SUBJ_N_PCT"),
               S5="NONE", rule="default_var_blocks")
    return out


CONTENT_TAGS = [
    ("deaths", r"death"),
    ("adverse_events", r"adverse|teae|\bsae\b|toxicity|dlt|smq|tornado"),
    ("medical_history", r"medical history|prior disease|concomitant disease"),
    ("medications", r"medication|anti-cancer therap|cancer therap|atc|therapeutic class|anticancer|antineoplastic|chemotherapy|non-drug"),
    ("disposition", r"disposition|withdrawal|enrollment|completion|follow-up|survival status"),
    ("analysis_sets", r"analysis set|analysis population|excluded from|populations"),
    ("protocol_deviations", r"deviation"),
    ("eligibility", r"inclusion|exclusion|eligib"),
    ("demographics_baseline", r"demograph|baseline characteristics|substance|obstetric|menopausal|baseline information"),
    ("efficacy_response", r"response|pcr|ccca|mpepi|\bbcs\b|breast conserving|disease control|lesion|recist|tumor change|primary breast tumor|primary tumor|ki-67|aqua|h-score|tumor marker|psa|efficacy|cystectomy|tumor assessment"),
    ("disease_history", r"disease|cancer history|staging|diagnosis|molecular|surgery|procedure|radiation|turbt|biopsy|biospsy|cytology"),
    ("exposure", r"exposure|administration|dosing|\bdose (adjust|interrupt|change)|compliance|infusion|overdose|pk dosing"),
    ("laboratory", r"hematology|biochemistry|chemistry|laboratory|urinalysis|coagulation|serology|pregnancy|liver function|thyroid|autoimmune|covid|\banc\b"),
    ("vital_signs", r"vital|temperature|weight"),
    ("ecg_cardiac", r"ecg|qtc|holter|cardiac|ejection|doppler"),
    ("physical_exam", r"physical exam|ophthalm|chest|ultrasound|fibroscan|elastograph"),
    ("performance_status", r"ecog"),
    ("efficacy_time_to_event", r"survival|time to|duration of response|pfs|rfs|ttp|recurrence"),
    ("efficacy_other", r"neutropenia|nadir"),
    ("pk", r"concentration|pharmacokinetic|pk "),
    ("pd_biomarker", r"pharmacodynamic|biomarker"),
    ("immunogenicity", r"anti-drug|immunogenicity|\bada\b"),
    ("qol", r"qlq|quality of life|qol|questionnaire"),
    ("visits", r"visit dates"),
]


def content_tag(title):
    t = core_title(title)
    for tag, pat in CONTENT_TAGS:
        if has(pat, t):
            return tag
    return "other"


def main():
    digests = [json.loads(l) for l in open(os.path.join(INV, "Source_Digests.jsonl"), encoding="utf-8")]
    ov_path = os.path.join(INV, "Signature_Overrides.json")
    overrides = json.load(open(ov_path, encoding="utf-8"))["overrides"] if os.path.exists(ov_path) else {}
    rows = []
    for d in digests:
        if d["structural_family"] == "listing":
            sig = classify_listing(d)
        elif d["structural_family"] == "figure":
            sig = classify_figure(d)
        else:
            sig = classify_table(d)
        basis = "rule"
        if d["source_id"] in overrides:
            o = overrides[d["source_id"]]
            for k in ("S1", "S2", "S3", "S4", "S5", "S6", "layout_flags"):
                if k in o:
                    sig[k] = o[k]
            sig["rule"] = "override: " + o["reason"]
            basis = "manual"
        tag = overrides.get(d["source_id"], {}).get("content_tag") or content_tag(d["title"])
        rows.append({
            "source_id": d["source_id"], "study_id": d["study_id"], "source_output_type": d["output_type"],
            "tfl_number": d["tfl_number"], "title": d["title"],
            "S1": sig["S1"], "S2_row_axis": sig["S2"], "S3_col_axis": sig["S3"], "S4_cell_semantics": sig["S4"],
            "S5_nesting": sig["S5"], "S6_plot_type": sig["S6"],
            "signature_key": "|".join([sig["S1"], sig["S2"], sig["S3"], sig["S4"]] + ([sig["S6"]] if sig["S6"] else [])),
            "layout_flags": sig.get("layout_flags", ""), "content_tag": tag,
            "basis": basis, "rule_or_reason": sig["rule"],
            "legacy_family_reference": ";".join(x for x in d.get("legacy_family", []) if not x.startswith("continuous_batch")),
        })
    for r in rows:
        for dim, key in (("S2_row_axis", "S2_row_axis"), ("S3_col_axis", "S3_col_axis"), ("S4_cell_semantics", "S4_cell_semantics"), ("S5_nesting", "S5_nesting")):
            assert r[key] in VOCAB[dim], (r["source_id"], key, r[key])
        assert r["S6_plot_type"] in VOCAB["S6_plot_type"], (r["source_id"], r["S6_plot_type"])
    with open(os.path.join(INV, "Signatures.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(VOCAB, open(os.path.join(INV, "Signature_Vocabulary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    c = Counter(r["signature_key"] for r in rows)
    print(f"sources: {len(rows)}  distinct signature keys: {len(c)}  manual overrides: {sum(r['basis']=='manual' for r in rows)}")
    for k, v in c.most_common():
        studies = len({r["study_id"] for r in rows if r["signature_key"] == k})
        print(f"{v:4d}  studies={studies}  {k}")


if __name__ == "__main__":
    main()
