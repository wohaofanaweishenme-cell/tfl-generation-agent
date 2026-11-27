"""Phase 6.4E: deterministic structural compatibility, not clinical confirmation."""
from __future__ import annotations
import csv, hashlib, io, json, re, zipfile
from collections import Counter
from pathlib import Path

VALIDATION_NAME="20261127T203043132209Z.zip"
VALIDATION_SHA="0c9548df1cec9c36cc9f36cc49a85ee4bb6478d237e6ea7de1d7c75dd81ae228"
PREFLIGHT_NAME="20261127T190148681515Z.zip"
PREFLIGHT_SHA="4e52367c4d70d45c5df7b9619eb062887c314205fa41d0b7b99492298a7ba63d"
PILOT_SHA="74d816887d611c7f53a0d4ed7b9d3e1416aa8ea72d84bf746fc64b0340097aaa"
ARMS=("original_matching","automatic_alignment","reviewed_alignment")

def frozen(path, name, expected):
    b=Path(path).read_bytes()
    if hashlib.sha256(b).hexdigest()!=expected:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            hits=[z.read(n) for n in z.namelist() if n.endswith("/"+name)]
        if len(hits)!=1: raise ValueError("Expected exactly one frozen archive")
        b=hits[0]
    if hashlib.sha256(b).hexdigest()!=expected: raise ValueError("Frozen archive SHA mismatch")
    return zipfile.ZipFile(io.BytesIO(b))

def indexed(rows):
    out={(r["study_id"],r["entry_id"]):r for r in rows}
    if len(rows)!=6 or len(out)!=6: raise ValueError("Expected six distinct cases")
    return out

def load_inputs(validation,preflight):
    with frozen(validation,VALIDATION_NAME,VALIDATION_SHA) as z:
        s=json.loads(z.read("Summary.json"))
        if (s["source_archive_sha256"],s["cases"],s["original_claims"],s["new_llm_calls"])!=(PILOT_SHA,6,52,0):
            raise ValueError("Validation lineage mismatch")
        auto=indexed(json.loads(z.read("Rule_Only_Specifications.json")))
        reviewed=indexed(json.loads(z.read("Development_Reviewed_Specifications.json")))
        rows=json.loads(z.read("Claim_Review.json"))
    with frozen(preflight,PREFLIGHT_NAME,PREFLIGHT_SHA) as z:
        ctx=indexed(json.loads(z.read("Phase64_Preflight/Template_Candidates.json")))
        base=indexed(json.loads(z.read("Replay/Replayed_Decisions.json")))
        targets=indexed(json.loads(z.read("Phase64_Preflight/Extraction_Inputs.json")))
    if not set(auto)==set(reviewed)==set(ctx)==set(base)==set(targets):
        raise ValueError("Case mismatch")
    claims={(r["request_id"],r["claim_index"]):r for r in rows}
    if len(rows)!=52 or len(claims)!=52: raise ValueError("Claim identity mismatch")
    result=[]
    for k in sorted(auto):
        a,b,c,d,t=auto[k],reviewed[k],ctx[k],base[k],targets[k]
        if a["target"]!=b["target"] or a["target"]!=t["payload"]["target"] or a["sap_sha256"]!=b["sap_sha256"]:
            raise ValueError("Target mismatch")
        if a["request_id"]!=b["request_id"] or a["request_id"]!="__".join((*k,"specification_v1")):
            raise ValueError("Specification ID mismatch")
        if c["request_id"]!="__".join((*k,"D_applicability")) or c["request_id"]!=d["request_id"] or c["request_id"]!=t["request_id"]:
            raise ValueError("Matching ID mismatch")
        if c["recommended_template"]!=d["recommended_template"] or c["confirmed_template"] is not None:
            raise ValueError("Original candidate mismatch")
        templates=c["eligible_library_context"]["templates"]
        ids={v["template_id"] for v in templates}
        if len(templates)!=9 or len(ids)!=9 or any(v["structural_signature"]["S1"]!=a["target"]["output_type"] for v in templates):
            raise ValueError("Expected nine same-type templates")
        if c["recommended_template"] not in ids: raise ValueError("Unknown baseline")
        selected=[]
        for spec,field,keep in ((a,"rule_route","unverified_candidate"),(b,"development_review","retain_candidate")):
            picked=[]
            for f,v in spec["fields"].items():
                rs=[claims[(spec["request_id"],i)] for i in v["claim_indices"]]
                if any(r["field"]!=f or r[field]!=keep or not r["exact_match"] or not r["literal_support"] for r in rs):
                    raise ValueError("Specification claim provenance mismatch")
                if list(dict.fromkeys(r["value"] for r in rs))!=v["values"]: raise ValueError("Specification value mismatch")
                picked.extend(rs)
            expected={i for (rid,i),r in claims.items() if rid==spec["request_id"] and r[field]==keep}
            if {r["claim_index"] for r in picked}!=expected: raise ValueError("Missing retained claim")
            selected.append(picked)
        # Evaluation labels are separated from the alignment input.
        result.append({"study_id":k[0],"entry_id":k[1],"request_id":a["request_id"],"target":a["target"],
                       "templates":templates,"baseline":c["recommended_template"],"baseline_preset":c["proposed_preset"],
                       "baseline_protocol_supported":c["protocol_supported_candidate"],
                       "automatic":selected[0],"reviewed":selected[1],"expected":d["expected"]})
    return result

def signals(claims):
    """Positive shape signals only. No inference from missing fields.
    Rules are development heuristics derived from library structural signatures.
    """
    out=[]
    def add(name,dimension,allowed,rs,strength):
        out.append({"signal":name,"dimension":dimension,"allowed":allowed,"strength":strength,
                    "claim_indices":sorted({r["claim_index"] for r in rs}),
                    "source_types":sorted({r["source"] for r in rs}),
                    "values":list(dict.fromkeys(r["value"] for r in rs))})
    def find(fields,pattern):
        return [r for r in claims if r["field"] in fields and re.search(pattern,r["value"],re.I)]
    row={"row_requirements"}
    coded=find(row,r"\b(?:SOC\s*(?:and|/)\s*PT|system organ class\s*(?:and|/)\s*preferred term|ATC class)\b")
    if coded: add("coded_hierarchy","S2",["CODED_HIERARCHY"],coded,"shape")
    # Explicit non-exclusive criterion flags, or deviation/status rows by severity/category.
    criteria=find(row,r"\b(?:deaths?|serious adverse events|SAEs|grade\s*\d+\s*or greater|drug.related TEAEs|discontinued|withdrawn)\b")
    deviation=find({"endpoint"},r"\bprotocol deviations?\b")
    categorized=find(row,r"\bseverity and categories\b")
    if criteria: add("criterion_flags","S2",["CATEGORY_LIST"],criteria,"shape")
    if deviation and categorized: add("deviation_categories","S2",["CATEGORY_LIST"],deviation+categorized,"shape")
    # Explicit list of at least three named category abbreviations in a single value,
    # together with observed frequency/percentage. Not a general proof of exhaustiveness.
    enum=[r for r in claims if r["field"] in {"endpoint","row_requirements"} and r["source"]=="sap"
          and len(re.findall(r"\([A-Z][A-Z0-9]{0,4}\)",r["value"]))>=3
          and r["value"].count(",")>=2]
    pct=find({"statistics"},r"\b(?:number and percentage|percentage of (?:subjects|participants)|frequencies)\b|n\s*[,/(]\s*%")
    if enum and pct: add("named_category_distribution","S2",["VAR_BLOCKS"],enum+pct,"shape")
    desc=find({"statistics"},r"\b(?:arithmetic mean|standard deviation|median|minimum|maximum)\b")
    if desc: add("descriptive_statistics","S4",["DESC","DESC_MIXED","PK_DESC"],desc,"statistic")
    if pct: add("frequency_percentage","S4",["SUBJ_N_PCT","SUBJ_AND_EVENTS","DESC_MIXED"],pct,"statistic")
    events=find({"statistics"},r"\bnumber of cases and number of events\b")
    if events: add("cases_and_events","S4",["SUBJ_AND_EVENTS"],events,"statistic")
    # Only explicit positive CI and rate requirements jointly suggest RATE_CI.
    # Do not use conditional/general CI conventions as display evidence.
    ci=[r for r in find({"confidence_intervals"},r"\bCI\b|confidence interval") if r.get("applicability")=="target_specific" and r["source"]=="sap"]
    rate=find({"statistics"},r"\b(?:response rate|proportion of responders)\b")
    if ci and rate: add("response_rate_with_ci","S4",["RATE_CI"],ci+rate,"statistic")
    return out

def align(templates, baseline, claims):
    sig=signals(claims); matrix=[]
    for t in templates:
        signature=t["structural_signature"]
        matches=[]; tensions=[]
        for s in sig:
            v=signature[s["dimension"]]; values=[v] if isinstance(v,str) else v
            (matches if set(values)&set(s["allowed"]) else tensions).append(s["signal"])
        matrix.append({"template_id":t["template_id"],"structural_signature":signature,
                       "not_for":t["not_for"],"matching_signals":matches,"tension_signals":tensions,
                       "unassessed_dimensions":[d for d in ("S2","S3","S4","S5") if not any(s["dimension"]==d for s in sig)]})
    # Strict policy: unique shape signal intersection + no positive statistic
    # tension for challenger. Conflicting shapes never trigger an override.
    shapes=[s for s in sig if s["strength"]=="shape"]
    shape_candidates=[m for m in matrix if all(s["signal"] in m["matching_signals"] for s in shapes)] if shapes else []
    compatible=[m for m in shape_candidates if not m["tension_signals"]]
    rec=baseline
    if shapes and not shape_candidates:
        decision="conflicting_shape_evidence"
    elif len(compatible)==1:
        rec=compatible[0]["template_id"]
        decision="provisional_revision" if rec!=baseline else "structure_supported_candidate"
    elif shapes and not compatible:
        decision="shape_statistic_tension"
    elif shapes:
        decision="multiple_shape_candidates"
    else:
        decision="insufficient_discriminating_shape"
    return {"recommended_template":rec,"decision":decision,"signals":sig,"matrix":matrix,
            "shape_candidates":[m["template_id"] for m in shape_candidates],
            "compatible_shape_candidates":[m["template_id"] for m in compatible],
            "confirmed_template":None,"confirmed_preset":None,"generation_authorized":False}

def evaluate(cases):
    decisions=[]; matrix=[]; gap_rows=[]; evaluations=[]
    for case in cases:
        identity={k:case[k] for k in ("request_id","study_id","entry_id","target")}
        for arm in ARMS:
            if arm=="original_matching":
                d={"recommended_template":case["baseline"],"decision":"frozen_original","signals":[],"matrix":[],
                   "shape_candidates":[],"compatible_shape_candidates":[],"confirmed_template":None,"confirmed_preset":None,"generation_authorized":False}
            else:
                d=align(case["templates"],case["baseline"],case["automatic" if arm=="automatic_alignment" else "reviewed"])
            rec=d["recommended_template"]
            original_preset=case["baseline_preset"] if rec==case["baseline"] else None
            t=next(t for t in case["templates"] if t["template_id"]==rec)
            if original_preset is not None and original_preset not in {p["preset_id"] for p in t["presets"]}:
                raise ValueError("Baseline preset ownership mismatch")
            decisions.append({**identity,"arm":arm,"baseline":case["baseline"],**{k:v for k,v in d.items() if k!="matrix"},
                              "original_preset_retained_unvalidated":original_preset,"development_reference_arm":arm=="reviewed_alignment"})
            matrix.extend({**identity,"arm":arm,**m} for m in d["matrix"])
            # Required field paths are the actual library contract. Do not infer
            # fulfillment from similarly named specification fields or preset defaults.
            for f in t["required_fields"]:
                gap_rows.append({**identity,"arm":arm,"template_id":rec,**f,
                                 "status":"title_available_not_bound" if f["path"]=="title" else "not_validated",
                                 "generation_authorized":False})
            evaluations.append({**identity,"arm":arm,"expected":case["expected"],
                                "recommended_template":rec,"correct_reference_match":rec in case["expected"].split("|"),
                                "changed":rec!=case["baseline"],"decision":d["decision"]})
    metrics={}
    for arm in ARMS:
        rs=[r for r in evaluations if r["arm"]==arm]
        metrics[arm]={"n":len(rs),"correct":sum(r["correct_reference_match"] for r in rs),
                      "reference_top1":sum(r["correct_reference_match"] for r in rs)/len(rs),
                      "changed":sum(r["changed"] for r in rs),"decision_counts":dict(Counter(r["decision"] for r in rs))}
    return decisions,matrix,gap_rows,evaluations,metrics

def save_json(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def write_csv(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})

def run(validation,preflight,out):
    cases=load_inputs(validation,preflight)
    decisions,matrix,gaps,ev,metrics=evaluate(cases)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    report={"version":"6.4E-v1","source_sha256":{"validation":VALIDATION_SHA,"preflight":PREFLIGHT_SHA},
            "new_llm_calls":0,"cases":6,"metrics":metrics,"matrix_rows":len(matrix),
            "confirmed_templates":0,"confirmed_presets":0,"independent_semantic_labels":0,
            "generation_authorized":False,
            "caveats":["Development-only heuristics and reference labels, not held-out accuracy.",
                       "Original matching is D_applicability replay recommendation, not title-only.",
                       "Reviewed alignment uses prior qualitative annotations, not automatic inference.",
                       "Missing evidence is unknown, not a negative compatibility signal.",
                       "Library not_for text is preserved for audit; rules approximate selected boundaries, not full semantic interpretation.",
                       "Shape and statistic signals are candidates, not clinical facts; no preset rebinding or required-field fulfillment."]}
    save_json(out/"Summary.json",report)
    save_json(out/"Alignment_Decisions.json",decisions)
    write_csv(out/"Compatibility_Matrix.csv",matrix)
    write_csv(out/"Required_Field_Gaps.csv",gaps)
    write_csv(out/"Paired_Comparison.csv",ev)
    return report,decisions
