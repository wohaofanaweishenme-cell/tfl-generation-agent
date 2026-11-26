"""Phase 4: exhaustive small-library keyword + dense retrieval and reranking.

Scores are heuristic and not calibrated probabilities. Unknown structure is not
a contradiction. No shell is authorized or rendered.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict
import numpy as np

from tfl_agent.agent.generic_retriever import (
    norm, core_title, retrieve_generic_baseline,
)
from tfl_agent.agent.requirement_normalizer import (
    canonical_variable, normalize_spec, enumeration_review, matches, STAT_PATTERNS,
)

WEIGHTS={"keyword":.20,"semantic":.25,"structure":.25,"statistics":.20,"preset":.10}
STAT_CAPABILITIES={
    "DESC":{"n","mean","sd","median","min","max","q1","q3"},
    "DESC_MIXED":{"n","mean","sd","median","min","max","q1","q3","percentage"},
    "PK_DESC":{"n","mean","sd","median","min","max"},
    "SUBJ_N_PCT":{"n","percentage"},
    "SUBJ_AND_EVENTS":{"n","percentage"},
    "EVENTS":{"n"},
    "RATE_CI":{"n","percentage","ci","odds_ratio","p_value"},
    "TTE_EST":{"n","percentage","q1","median","q3","ci","hazard_ratio","p_value","min","max"},
    "MODEL_EST":{"n","mean","sd","median","min","max","ci","p_value"},
}
# Actual structural signatures remain authoritative; this small crosswalk is
# provisional, not a complete list of renderer capabilities.
STRONG_AXES={"S2","S4"}


def flatten(x):
    if isinstance(x,dict):
        return " ".join(flatten(v) for k,v in x.items() if k not in ("evidence","note","footnote_refs"))
    if isinstance(x,list):
        return " ".join(flatten(v) for v in x)
    return str(x) if x is not None else ""


def template_doc(t):
    return " ".join([t["name"],t["intended_use"]," ".join(t["keywords"]+t["aliases"]),
                     flatten(t["structural_signature"])])
# Exclude not_for from positive embedding text to avoid rewarding contraindications.


def preset_doc(p):
    return " ".join([p["name"]," ".join(p["keywords"]+p["aliases"]),flatten(p["defaults"])])


def _unit(a,n):
    a=np.asarray(a,dtype=float)
    if a.ndim!=2 or len(a)!=n or not np.isfinite(a).all():
        raise ValueError("Invalid embedding matrix")
    lengths=np.linalg.norm(a,axis=1,keepdims=True)
    if (lengths==0).any():
        raise ValueError("Zero embedding")
    return a/lengths


def _has(text,term):
    return bool(term) and (" "+term+" ") in (" "+text+" ")


def _lexical(text,library):
    text=norm(text)
    template,preset=defaultdict(set),defaultdict(set)
    for term,refs in library.terms.items():
        if _has(text,norm(term)):
            for ref in refs:
                tid,pid=ref["template_id"],ref["preset_id"]
                template[tid].add(term)
                if pid is not None:
                    preset[tid,pid].add(term)
    return template,preset


def _sigvalues(sig,axis):
    v=sig.get(axis,[])
    return {v} if isinstance(v,str) else set(v)


def structure_score(normalized,sig):
    checks=[]
    for feature in normalized["structural_features"]:
        axis=feature["axis"]
        actual=_sigvalues(sig,axis)
        good=bool(actual & set(feature["allowed"]))
        checks.append({**feature,"template_values":sorted(actual),"compatible":good})
    return (sum(c["compatible"] for c in checks)/len(checks) if checks else None),checks


def statistical_score(normalized,sig):
    required=set(normalized["statistics"])
    codes=_sigvalues(sig,"S4")
    supported=set().union(*(STAT_CAPABILITIES.get(c,set()) for c in codes))
    # Unknown/statistical display for figures/listings is not treated as zero.
    score=len(required & supported)/len(required) if required and supported else None
    return score,sorted(required & supported),sorted(required-supported) if supported else []


def preset_variables(p):
    return {canonical_variable(b["label"]):b["label"] for b in p["defaults"].get("row_blocks",[])
            if b.get("block_type") in ("continuous","categorical") and b.get("label")}


def weighted(components):
    usable={k:v for k,v in components.items() if v is not None}
    return sum(WEIGHTS[k]*v for k,v in usable.items())/sum(WEIGHTS[k] for k in usable)


class SAPAwareRetriever:
    def __init__(self,library,encoder):
        self.library,self.encoder=library,encoder
        self.templates={tid:library.template(tid) for tid in library.templates}
        self.presets={key:library.preset(*key) for key in library.presets}
        self.tids=list(self.templates)
        self.pids=list(self.presets)
        texts=[template_doc(self.templates[i]) for i in self.tids]+[preset_doc(self.presets[i]) for i in self.pids]
        # Full metadata stays available; model input is a bounded retrieval document.
        # Check any encoder truncation diagnostic rather than assume full text was embedded.
        self.document_truncations=encoder.truncated_count(texts) if hasattr(encoder,"truncated_count") else None
        vec=_unit(encoder.encode(texts,is_query=False),len(texts))
        self.tv=vec[:len(self.tids)]
        self.pv=vec[len(self.tids):]

    def retrieve(self,normalized):
        target=normalized["identity"]
        entry={"original_title":target["title"],"original_tfl_number":target["tfl_id"],"output_type":target["output_type"]}
        baseline=retrieve_generic_baseline(entry,self.library)
        title=core_title(entry)
        fields=normalized["raw_fields"]
        # Do not use population/treatment labels, general study rules or unverified review claims for template discovery.
        wanted=("endpoint_name","endpoint_definition","analysis_methods","variables_to_display",
                "statistics_to_display","row_requirements","grouping_basis","censoring_rules","ci_methods",
                "figure_requirements","listing_requirements")
        evidence_query=" ".join(v for f in wanted for v in fields.get(f,[]))
        query=(title+" "+evidence_query).strip()
        lex_t,lex_p=_lexical(query,self.library)
        title_t,title_p=_lexical(title,self.library)
        q=_unit(self.encoder.encode([title,query],is_query=True),2)
        dense=(self.tv @ q[1])
        title_dense=self.tv @ q[0]
        pdense=self.pv @ q[1]
        ptitle=self.pv @ q[0]
        candidates=[]
        eligible=[i for i in self.tids if self.templates[i]["output_type"]==target["output_type"]]
        if not eligible:
            return {"status":"no_compatible_template","baseline":baseline,"candidates":[],"template_id":None,"preset_id":None,"generation_authorized":False}
        maxlex=max([len(lex_t[i]) for i in eligible]+[1])
        for ix,tid in enumerate(self.tids):
            if tid not in eligible: continue
            t=self.templates[tid]
            sig=t["structural_signature"]
            structure,checks=structure_score(normalized,sig)
            stats,covered,uncovered=statistical_score(normalized,sig)
            p_options=[]
            for px,key in enumerate(self.pids):
                if key[0]!=tid: continue
                p=self.presets[key]
                # Title/topic keyword signals plus evidence-based variable overlap;
                # avoid treating a candidate preset's defaults as verified study facts.
                hits=len(lex_p[key]); title_hits=len(title_p[key])
                overlap=set(normalized["variables"]) & set(preset_variables(p))
                var_score=len(overlap)/len(normalized["variables"]) if normalized["variables"] else None
                semantic=max(0.,min(1.,float((pdense[px]+ptitle[px])/2)))
                kw=min(1.,(hits+title_hits)/4)
                comps=[(.45,semantic),(.35,kw)]+([(.20,var_score)] if var_score is not None else [])
                ps=sum(w*v for w,v in comps)/sum(w for w,v in comps)
                p_options.append({"preset_id":key[1],"score":ps,"matched_terms":sorted(lex_p[key]),
                                  "title_terms":sorted(title_p[key]),"variable_overlap":sorted(overlap),
                                  "dense_cosine":float(pdense[px])})
            p_options.sort(key=lambda p:(-p["score"],p["preset_id"]))
            best=p_options[0] if p_options else None
            semantic=max(0.,min(1.,float((dense[ix]+title_dense[ix])/2)))
            kw=len(lex_t[tid])/maxlex
            # Negative title cues are audit signals only: many are overlapping generic terms.
            negatives=[w for w in t["match_cues"].get("negative_terms",[]) if norm(w) in norm(title)]
            components={"keyword":kw,"semantic":semantic,"structure":structure,"statistics":stats,
                        "preset":best["score"] if best else None}
            # Strong contradictory SAP-derived structure gates selection. Missing evidence is neutral.
            conflict=any(not c["compatible"] and c["axis"] in STRONG_AXES and
                         (c["axis"]=="S2" or c["allowed"]==["TTE_EST"]) for c in checks)
            candidates.append({"template_id":tid,"preset_id":best["preset_id"] if best else None,
                               "score":weighted(components),"components":components,
                               "dense_cosine":float(dense[ix]),"title_dense_cosine":float(title_dense[ix]),
                               "matched_terms":sorted(lex_t[tid]),"title_terms":sorted(title_t[tid]),
                               "negative_title_cues":negatives,"structural_checks":checks,
                               "statistical_capability_match":covered,"statistical_capability_gap":uncovered,
                               "structural_conflict":conflict,"preset_candidates":p_options})
        candidates.sort(key=lambda c:(c["structural_conflict"],-c["score"],c["template_id"]))
        # All candidates scored; report separate ablation rankings using the same library.
        dense_rank=sorted(candidates,key=lambda c:(-c["title_dense_cosine"],c["template_id"]))
        hybrid_rank=sorted(candidates,key=lambda c:(-(.45*c["components"]["keyword"]+.55*c["components"]["semantic"]),c["template_id"]))
        viable=[c for c in candidates if not c["structural_conflict"]]
        top=viable[0] if viable else None
        margin=top["score"]-viable[1]["score"] if len(viable)>1 else None
        flags=[]
        if top is None: flags.append("no_structurally_compatible_candidate")
        else:
            if top["score"]<.35: flags.append("weak_match")
            if margin is not None and margin<.04: flags.append("small_template_margin")
            if not normalized["accepted_claims"]: flags.append("no_accepted_sap_evidence")
            if not top["matched_terms"] and not top["structural_checks"]: flags.append("no_lexical_or_structural_support")
            if top["negative_title_cues"]: flags.append("negative_title_cues_review")
            if not top["preset_candidates"]: flags.append("no_preset")
        # A title/type mismatch must not silently redirect to another output type.
        if (target["output_type"]=="table" and re.match(r"^\s*(listing|figure)\b",title,re.I)):
            flags.append("title_output_type_conflict")
        if re.search(r"\b(?:preface|catalog(?:ue)?)\b.*\b(?:eligibility|inclusion|exclusion)\b",title,re.I):
            flags.append("possible_nonstandard_output")
        blocking={"no_structurally_compatible_candidate","weak_match","small_template_margin",
                  "no_accepted_sap_evidence","no_lexical_or_structural_support","title_output_type_conflict","possible_nonstandard_output"}
        selected=top if top and not (set(flags)&blocking) else None
        pid=selected["preset_id"] if selected else None
        if selected and len(selected["preset_candidates"])>1:
            ps=selected["preset_candidates"]
            if ps[0]["score"]-ps[1]["score"]<.04:
                flags.append("small_preset_margin")
                pid=None
        if selected and pid and not selected["preset_candidates"][0]["matched_terms"] and not selected["preset_candidates"][0]["variable_overlap"]:
            flags.append("preset_requires_topic_review")
        return {"status":"retrieved_candidate" if selected else "needs_review",
                "template_id":selected["template_id"] if selected else None,"preset_id":pid,
                "best_candidate_template_id":top["template_id"] if top else None,
                "best_candidate_preset_id":top["preset_id"] if top else None,
                "template_margin":margin,"flags":flags,"baseline":baseline,
                "candidates":candidates,
                "ablation_rankings":{"title_dense":[c["template_id"] for c in dense_rank],
                                     "keyword_dense_no_structure":[c["template_id"] for c in hybrid_rank]},
                "query":query,"document_truncations":self.document_truncations,
                "query_truncations":self.encoder.truncated_count([query]) if hasattr(self.encoder,"truncated_count") else None,
                "weights":WEIGHTS,"generation_authorized":False,"clinical_confirmation":False,
                "warning":"Heuristic candidate ranking, not calibrated confidence or independent evaluation."}


def _row_stats(p):
    codes={"n":{"n"},"mean_sd":{"mean","sd"},"median":{"median"},"min_max":{"min","max"},
           "n_pct":{"n","percentage"},"median_ci":{"median","ci"},"estimate_ci":{"ci"},
           "p_value":{"p_value"}}
    result=set()
    for block in p["defaults"].get("row_blocks",[]):
        if block.get("block_type")=="categorical": result.update(("n","percentage"))
        for s in block.get("statistics",[]): result.update(codes.get(s,{s}))
        for item in block.get("items",[]):
            if item.get("where")=="comparison": continue
            label=item.get("label","")
            found=set(matches(label,STAT_PATTERNS))
            kind=item.get("kind")
            item_stats=codes.get(kind,set()).copy()
            if kind=="median_ci" and ("q1" in found or "q3" in found): item_stats.discard("median")
            result.update(found|item_stats)
    return result


def gap_analysis(normalized,study,part,result,library):
    tid,pid=result["template_id"],result["preset_id"]
    plan={"identity":normalized["identity"],"template_id":tid,"preset_id":pid,
          "generation_authorized":False,"clinical_confirmation":False,"actions":[],
          "coverage_review":enumeration_review(part,normalized)}
    actions=plan["actions"]
    if not tid:
        actions.append({"action":"review","element":"template","reason":"No safe candidate selection; inspect ranked candidates"})
        return plan
    t=library.template(tid)
    p=library.preset(tid,pid) if pid else None
    if not p:
        actions.append({"action":"review","element":"preset","reason":"No unambiguous topic preset"})
    if p:
        pv=preset_variables(p)
        # Variable-level comparison only where preset explicitly defines continuous/categorical blocks.
        if pv:
            for k,refs in normalized["variables"].items():
                actions.append({"action":"keep" if k in pv else "add_candidate","element":"variable",
                                "value":k,"preset_label":pv.get(k),"evidence":refs,
                                "reason":"Matched variable label/alias; category/unit/statistic details still require review" if k in pv else "SAP-supported variable absent from preset"})
            for k,label in pv.items():
                if k not in normalized["variables"]:
                    actions.append({"action":"review","element":"preset_variable","value":label,
                                    "reason":"Not confirmed by accepted target claims; absence does not imply exclusion"})
        stats=_row_stats(p)
        if stats:
            for stat,refs in normalized["statistics"].items():
                actions.append({"action":"keep" if stat in stats else "add_candidate","element":"statistic",
                                "value":stat,"evidence":refs,"reason":"Preset statistic present; verify variable-level applicability" if stat in stats else "Not explicit in preset rows"})
            for stat in sorted(stats-set(normalized["statistics"])):
                actions.append({"action":"review","element":"preset_statistic","value":stat,
                                "reason":"Preset default not confirmed by target SAP claims"})
    field_map={"population":"analysis_population","columns.total":"column_requirements",
               "footnotes[FN_DENOM]":"denominator_rule","footnotes[FN_CENSOR]":"censoring_rules",
               "footnotes[FN_CI]":"ci_methods","columns.comparison_columns":"comparison_requirements"}
    for req in t["required_fields"]:
        path=req["path"]
        if path=="title":
            actions.append({"action":"modify_candidate","element":path,"value":normalized["identity"]["title"],
                            "source":"explicit_target","reason":"Use requested title, not reference title"})
        elif path=="columns.groups":
            groups=study.get("values",{}).get("treatment_groups",[])
            actions.append({"action":"modify_candidate" if groups else "review","element":path,"value":groups,
                            "source":"study_candidate","reason":"Study arms identified; target applicability and display labels not confirmed"})
        else:
            vals=normalized["raw_fields"].get(field_map.get(path,""),[])
            if path=="columns.total":
                vals=[v for v in vals if re.search(r"\b(?:overall|total|pooled)\b",v,re.I)]
            actions.append({"action":"modify_candidate" if vals else "review","element":path,"value":vals,
                            "reason":"Evidence-backed candidate; verify placement/applicability" if vals else "Required library slot not established by target claims"})
    # Shared denominator rules are useful review context, not target-confirmed footnotes.
    if "footnotes[FN_DENOM]" in [r["path"] for r in t["required_fields"]] and not normalized["raw_fields"].get("denominator_rule"):
        for i,c in enumerate(study.get("claims",[])):
            if c["field"]=="denominator_rules" and c["status"]=="evidence_backed_candidate":
                actions.append({"action":"review","element":"shared_denominator_rule","value":c["value"],
                                "evidence":[{"study_claim_index":i,"chunk_id":c["chunk_id"],"source_spans":c["source_spans"]}],
                                "reason":"General SAP rule found; target applicability not confirmed"})
    for ref in normalized["reporting_dimensions"]:
        actions.append({"action":"review","element":"reporting_dimension","value":ref["value"],"evidence":[ref],
                        "reason":"Reporting by groups/subgroups does not establish row vs column layout"})
    if pid and _sigvalues(t["structural_signature"],"S4")=={"TTE_EST"}:
        for i,c in enumerate(normalized["accepted_claims"]):
            if c["field"]=="statistics_to_display" and re.search(r"\b(?:further divided|reasons for censoring)\b",c["value"],re.I):
                actions.append({"action":"add_candidate","element":"endpoint_row_detail","value":c["value"],
                                "evidence":[{"claim_index":i,"chunk_id":c["chunk_id"]}],
                                "reason":"Explicit reporting detail; generic Events/Censored rows may need subdivision"})
    return plan
