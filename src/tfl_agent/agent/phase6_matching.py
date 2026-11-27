"""Phase 6.3 A/B/C: full-candidate matching, no LLM.
Forced rankings are diagnostic recommendations, never generation approvals.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re
import numpy as np
from tfl_agent.agent.phase6_context import make_context,write_json
from tfl_agent.agent.phase6_common import cases,study_artifacts,verify_identity,write_csv,read_csv
from tfl_agent.agent.phase6_retrieval import validated_claim_refs
from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.tools.sap_hybrid import LocalEncoder
from tfl_agent.agent.generic_retriever import norm
from tfl_agent.agent.requirement_normalizer import normalize_spec
from tfl_agent.agent.sap_aware_retriever import structure_score,statistical_score,_unit
from tfl_agent.agent.phase5_evaluation import row,aggregate
from tfl_agent.agent.generic_evaluation import evaluate

def terms(d): return sorted({norm(t) for t in [d["name"],*d["keywords"],*d["aliases"]] if norm(t)})
def hit_count(query,words):
    q=" "+norm(query)+" "
    return sum(" "+t+" " in q for t in words)
def doc(d):
    # Deliberately short; no source titles, evidence, defaults or gold labels.
    return " ".join([d["name"],d.get("intended_use",""),*d["keywords"],*d["aliases"]])

class FullMatcher:
    def __init__(self,lib,encoder):
        self.lib,self.encoder=lib,encoder
        self.ts={t["template_id"]:t for k in ("table","figure","listing") for t in make_context(lib,k)["templates"]}
        self.ps={(tid,p["preset_id"]):p for tid,t in self.ts.items() for p in t["presets"]}
        self.tids=sorted(self.ts);self.pids=sorted(self.ps)
        texts=[doc(self.ts[i]) for i in self.tids]+[doc(self.ps[i]) for i in self.pids]
        self.truncations=encoder.truncated_count(texts) if hasattr(encoder,"truncated_count") else None
        if self.truncations: raise ValueError("Library retrieval docs exceed encoder context")
        v=_unit(encoder.encode(texts,is_query=False),len(texts))
        self.tv=v[:len(self.tids)];self.pv=v[len(self.tids):]
    def rank(self,title,kind,mode,normalized=None):
        if mode not in ("keyword","dense","title_joint","cached_sap_joint"): raise ValueError(mode)
        eligible=[i for i,t in enumerate(self.tids) if self.ts[t]["output_type"]==kind]
        if not eligible: return []
        # Evidence remains optional. Only previously accepted, verified claims enter this baseline.
        fields=("endpoint_name","endpoint_definition","analysis_methods","variables_to_display","statistics_to_display","row_requirements","grouping_basis","figure_requirements","listing_requirements")
        evidence=" ".join(v for f in fields for v in (normalized or {}).get("raw_fields",{}).get(f,[]))
        if mode!="cached_sap_joint": evidence=""
        query=title+" "+evidence if evidence else title
        # Long evidence is embedded separately from title; never silently truncate.
        # Split by words; every slice remains in the mean signal, not a gold-derived filter.
        words=evidence.split()
        texts=[title]+[" ".join(words[i:i+100]) for i in range(0,len(words),100)]
        if hasattr(self.encoder,"truncated_count") and self.encoder.truncated_count(texts):
            raise ValueError("Query slice exceeds encoder context")
        q=_unit(self.encoder.encode(texts,is_query=True),len(texts))
        d=self.tv@q.T;p=self.pv@q.T
        tscore=d[:,0] if not evidence else .65*d[:,0]+.35*d[:,1:].mean(axis=1)
        pscore=p[:,0] if not evidence else .65*p[:,0]+.35*p[:,1:].mean(axis=1)
        tk={self.tids[i]:hit_count(query,terms(self.ts[self.tids[i]])) for i in eligible}
        pk={key:hit_count(query,terms(self.ps[key])) for key in self.pids if key[0] in tk}
        mt=max([1,*tk.values()]);mp=max([1,*pk.values()])
        result=[]
        for i in eligible:
            tid=self.tids[i]; t=self.ts[tid]
            candidates=[]
            for j,key in enumerate(self.pids):
                if key[0]!=tid: continue
                k=pk[key]/mp; ds=max(0.,min(1.,float(pscore[j])))
                score=k if mode=="keyword" else ds if mode=="dense" else .5*k+.5*ds
                candidates.append({"preset_id":key[1],"score":score,"keyword":k,"dense":ds})
            candidates.sort(key=lambda p:(-p["score"],p["preset_id"]))
            best=candidates[0] if candidates else None
            k=tk[tid]/mt;ds=max(0.,min(1.,float(tscore[i])))
            # Equal direct-template and best-preset signal; a transparent fixed baseline.
            direct=k if mode=="keyword" else ds if mode=="dense" else .5*k+.5*ds
            s=.5*direct+.5*best["score"] if best else direct
            struct=stat=None
            if mode=="cached_sap_joint" and normalized:
                struct,_=structure_score(normalized,t["structural_signature"])
                stat,_,_=statistical_score(normalized,t["structural_signature"])
                components=[(.7,s)]+([(.2,struct)] if struct is not None else [])+([(.1,stat)] if stat is not None else [])
                s=sum(w*v for w,v in components)/sum(w for w,v in components)
            result.append(dict(template_id=tid,preset_id=best["preset_id"] if best else None,score=s,keyword=k,dense=ds,structure=struct,statistics=stat,presets=candidates,used_cached_evidence=bool(evidence)))
        return sorted(result,key=lambda r:(-r["score"],r["template_id"]))

def run_matching(repo,root,out,encoder=None,benchmark=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    lib=load_generic_library(Path(repo)/"generic_template_library")
    matcher=FullMatcher(lib,encoder or LocalEncoder())
    manifest=cases(root);rows=[];rankings=[];bench_rows=[];history=defaultdict(dict)
    for r in read_csv(root/"Paired_Results.csv"): history[r["study_id"],r["entry_id"]][r["method"]]=r
    for study in sorted({c["study_id"] for c in manifest}):
        store,_,parts,specs,_=study_artifacts(root,study)
        for case in [c for c in manifest if c["study_id"]==study]:
            e=case["entry_id"];spec=specs[e];ident=verify_identity(case,parts[e],spec)
            validated_claim_refs(spec,store)
            n=normalize_spec(spec)
            # No expected label passed to rank().
            for mode in ("keyword","dense","title_joint","cached_sap_joint"):
                rr=matcher.rank(ident["title"],ident["output_type"],mode,n if mode=="cached_sap_joint" else None)
                top=rr[0] if rr else None
                rows.append(row(mode,case,[r["template_id"] for r in rr],top["template_id"] if top else None,top["preset_id"] if top else None))
                rankings.append({"study_id":study,"entry_id":e,"method":mode,"candidates":rr})
            for method,r in history[study,e].items():
                rows.append(row("phase52_"+method,case,[v for v in r["ranking"].split("|") if v],r["selected"] or None,r["selected_preset"] or None))
    if benchmark:
        # Source registry used ONLY for evaluation title/type/labels, never retrieved at inference.
        _,entries=evaluate(repo,lib)
        for case in [c for c in entries if c["expected"]]:
            for mode in ("keyword","dense","title_joint"):
                rr=matcher.rank(case["title"],case["output_type"],mode)
                top=rr[0] if rr else None
                bench_rows.append(row(mode,case,[r["template_id"] for r in rr],top["template_id"] if top else None,top["preset_id"] if top else None))
    write_csv(out/"Challenge_Matching.csv",rows)
    write_json(out/"Challenge_All_Candidates.json",rankings)
    if bench_rows: write_csv(out/"Title_Benchmark.csv",bench_rows)
    s={"challenge_cases":len(manifest),"historical_completed_phase3_calls":44,"new_llm_calls":0,"challenge_all":aggregate(rows),"challenge_type_consistent":aggregate([r for r in rows if not r["type_conflict"]]),"challenge_type_conflict":aggregate([r for r in rows if r["type_conflict"]]),"challenge_by_stratum":{k:aggregate([r for r in rows if r["stratum"]==k]) for k in sorted({r["stratum"] for r in rows})},"title_benchmark":aggregate(bench_rows),"benchmark_cases":len(bench_rows)//3,"preset_accuracy":None,"generation_authorized":False,"limitations":["New methods force top-1 for comparison, not validated selection; compare rank metrics with abstaining historical methods.","C uses only historical accepted SAP claims, not newly retrieved evidence; no claim of improved SAP extraction.","Same in-library development cases; no held-out accuracy.","No independent preset labels. Preset IDs are candidates only.","Fixed scoring weights are provisional baseline, not tuned."]}
    write_json(out/"Summary.json",s)
    return s
