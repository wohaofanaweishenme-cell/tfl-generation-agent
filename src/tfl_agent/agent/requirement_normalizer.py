"""Phase 4: deterministic normalization with claim-level evidence retained."""
from __future__ import annotations
import re
from collections import defaultdict
from tfl_agent.agent.generic_retriever import norm

STAT_PATTERNS = {
    "n": r"\bn\b|\bnumber\b|\bcounts?\b|\bfrequenc(?:y|ies)\b",
    "percentage": r"%|\bpercent(?:age)?s?\b",
    "mean": r"\bmean\b", "sd": r"\bSD\b|\bstandard deviation\b",
    "median": r"\bmedian\b", "min": r"\bmin(?:imum)?\b", "max": r"\bmax(?:imum)?\b",
    "q1": r"\bQ1\b|\b25th percentile\b|\bfirst quartile\b",
    "q3": r"\bQ3\b|\b75th percentile\b|\bthird quartile\b",
    "ci": r"\bCI(?:s)?\b|\bconfidence intervals?\b",
    "hazard_ratio": r"\bhazard ratio\b|\bHR\b",
    "odds_ratio": r"\bodds ratio\b", "p_value": r"\bp[- ]value\b",
}
METHOD_PATTERNS = {
    "kaplan_meier": r"\bKaplan[- ]Meier\b",
    "descriptive": r"\bdescriptive statistics\b",
    "brookmeyer_crowley": r"\bBrookmeyer[- ]Crowley\b",
    "log_rank": r"\blog[- ]rank\b",
    "cox": r"\bCox\b",
    "ancova": r"\bANCOVA\b|\banalysis of covariance\b",
    "mmrm": r"\bMMRM\b|\bmixed model for repeated measures\b",
}
VARIABLE_ALIASES = {"gender":"sex","bmi":"body mass index","ecog":"ecog performance status"}
POP_ALIASES = {"safety":"safety","itt":"itt","pp":"pp","fas":"fas"}


def canonical_variable(text):
    n = norm(text)
    return VARIABLE_ALIASES.get(n,n)


def matches(text, patterns):
    return [k for k,p in patterns.items() if re.search(p,text,re.I)]


def normalize_spec(spec):
    from tfl_agent.agent.scoped_specification import population_kinds
    # Phase 3 review/rejected claims are intentionally excluded from scoring.
    claims = [c for c in spec["claims"] if c["status"]=="evidence_backed_candidate"]
    stat, methods, variables, groups, pops = defaultdict(list), defaultdict(list), defaultdict(list), [], defaultdict(list)
    feature_text = defaultdict(list)
    for i,c in enumerate(claims):
        f,v=c["field"],c["value"]
        ref={"claim_index":i,"chunk_id":c["chunk_id"],"value":v,"source_spans":c["source_spans"]}
        feature_text[f].append(v)
        if f in ("statistics_to_display","row_requirements","analysis_methods"):
            for k in matches(v,STAT_PATTERNS):
                stat[k].append(ref)
        if f in ("analysis_methods","ci_methods","comparison_requirements"):
            for k in matches(v,METHOD_PATTERNS):
                methods[k].append(ref)
        if f=="variables_to_display":
            variables[canonical_variable(v)].append(ref)
        if f=="analysis_population":
            for k in population_kinds(v):
                pops[k].append(ref)
        if f in ("column_requirements","grouping_basis","subgroup_requirements"):
            groups.append(ref)
    # Layout is not inferred from "by treatment group". Retain reporting dimensions.
    text=" ".join(v for f in ("analysis_methods","row_requirements","statistics_to_display","endpoint_definition","variables_to_display","censoring_rules","comparison_requirements") for v in feature_text[f])
    structures=[]
    def feature(axis,values,reason,fields):
        structures.append({"axis":axis,"allowed":values,"reason":reason,
                           "claim_indices":[i for i,c in enumerate(claims) if c["field"] in fields]})
    if spec["identity"]["output_type"]=="table":
        if "kaplan_meier" in methods and (feature_text["censoring_rules"] or re.search(r"\btime (?:from|to)\b",text,re.I)):
            feature("S2",["ENDPOINT_ANALYSIS"],"Time-to-event analysis with event-time/censoring evidence",("analysis_methods","endpoint_definition","censoring_rules"))
            feature("S4",["TTE_EST"],"Kaplan-Meier plus event-time/censoring evidence",("analysis_methods","endpoint_definition","censoring_rules"))
        elif re.search(r"\b(?:shift table|cross[- ]classification|cross[- ]tabulation)\b",text,re.I):
            feature("S2",["CROSSTAB"],"Explicit cross-classification",("row_requirements","analysis_methods"))
        elif re.search(r"\b(?:system organ class|SOC)\b",text,re.I) and re.search(r"\b(?:preferred term|PT)\b",text,re.I):
            feature("S2",["CODED_HIERARCHY"],"Explicit SOC and PT hierarchy",("row_requirements","variables_to_display","analysis_methods"))
        elif re.search(r"\b(?:by visit|each visit|per visit|by timepoint)\b",text,re.I):
            feature("S2",["BY_TIMEPOINT"],"Explicit repeated visit/timepoint summary",("row_requirements","analysis_methods","statistics_to_display"))
        elif set(methods)&{"ancova","mmrm"}:
            feature("S4",["MODEL_EST"],"Explicit model-based method",("analysis_methods","comparison_requirements"))
        elif "descriptive" in methods and variables and set(stat)&{"mean","sd","median","min","max"}:
            feature("S4",["DESC","DESC_MIXED","PK_DESC"],"Continuous descriptive statistics",("analysis_methods","statistics_to_display","row_requirements"))
            # Variable distribution is only a soft hint; repeated visits may be unspecified.
    return {"identity":spec["identity"],"topic":spec.get("topic"),"statistics":dict(stat),
            "methods":dict(methods),"variables":dict(variables),"populations":dict(pops),
            "reporting_dimensions":groups,"structural_features":structures,
            "raw_fields":dict(feature_text),"accepted_claims":claims,
            "review_claims":spec.get("review_claims",[]),
            "missing_required_fields":spec.get("missing_required_fields",[]),
            "clinical_confirmation":False}


def enumeration_review(part, normalized):
    """Surface explicit variable enumeration not captured by Phase 3.

    Conservative sentence pattern; never automatically promote omissions.
    Parenthetic qualifiers are kept with each candidate. This is not full recall.
    """
    captured=set(normalized["variables"])
    out=[]
    for chunk in part.get("target_evidence",[]):
        for m in re.finditer(r"\b([A-Za-z][A-Za-z ]{0,50}characteristics)\s+will include\s+([^.;]+)",chunk["text"],re.I):
            text=m.group(2)
            pieces=re.split(r",\s*(?![^()]*\))",text)
            for p in pieces:
                v=p.strip(" ,.;")
                if not v or v.lower() in {"etc","and","etc."} or v.startswith("("):
                    continue
                key=canonical_variable(re.sub(r"\s*\([^)]*\)\s*$","",v))
                if key not in captured:
                    out.append({"value":v,"enumeration":m.group(1).strip(),"chunk_id":chunk["chunk_id"],
                                "quote":m.group(0),"status":"needs_review",
                                "reason":"Explicit enumeration not captured as target variable; confirm whether same TFL or separate table"})
    return out
