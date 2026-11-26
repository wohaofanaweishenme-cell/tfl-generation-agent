"""Phase 5: separate in-library title benchmark, paired SAP diagnostics and held-out protocol."""
import json
from pathlib import Path
from collections import defaultdict
import numpy as np
from tfl_agent.agent.generic_evaluation import evaluate
from tfl_agent.agent.generic_retriever import core_title, retrieve_generic_baseline
from tfl_agent.agent.sap_aware_retriever import SAPAwareRetriever, _unit, _lexical
from tfl_agent.agent.sap_retrieval_pilot import _write_json, _write_csv
from tfl_agent.tools.generic_library import load_generic_library
from tfl_agent.tools.sap_hybrid import LocalEncoder


def metrics(rows):
    """Ranking metrics exclude NONSTANDARD; selection metrics include explicit abstention."""
    n=len(rows)
    if not n:
        return {"n":0,"selection_accuracy":None,"coverage":None,"recall_at_3":None,"mrr":None}
    standard=[r for r in rows if r["expected"]!="NONSTANDARD"]
    selected=[r for r in rows if r["selected"] is not None]
    nonstandard=[r for r in rows if r["expected"]=="NONSTANDARD"]
    return {"n":n,"correct":sum(r["correct"] for r in rows),
            "selection_accuracy":sum(r["correct"] for r in rows)/n,
            "coverage":len(selected)/n,
            "selective_accuracy":sum(r["correct"] for r in selected)/len(selected) if selected else None,
            "standard_n":len(standard),
            "rank_top1":sum(r["rank"]==1 for r in standard)/len(standard) if standard else None,
            "recall_at_3":sum(r["rank"] is not None and r["rank"]<=3 for r in standard)/len(standard) if standard else None,
            "mrr":sum(1/r["rank"] if r["rank"] else 0 for r in standard)/len(standard) if standard else None,
            "nonstandard_n":len(nonstandard),
            "nonstandard_abstention":sum(r["selected"] is None for r in nonstandard)/len(nonstandard) if nonstandard else None}


def row(method, case, ranked, selected, preset=None):
    expected=case["expected"]
    labels=set(expected.split("|"))
    rank=next((i for i,t in enumerate(ranked,1) if t in labels),None)
    correct=selected is None if expected=="NONSTANDARD" else selected in labels
    return {**case,"method":method,"selected":selected,"selected_preset":preset,
            "rank":rank,"correct":correct,"ranking":"|".join(ranked)}


def aggregate(rows):
    groups=defaultdict(list)
    for r in rows: groups[r["method"]].append(r)
    return {k:metrics(v) for k,v in groups.items()}


def title_benchmark(root, retriever):
    base, allrows=evaluate(root,retriever.library)
    cases=[r for r in allrows if r["expected"]]
    entries={}
    for study in sorted({r["study_id"] for r in cases}):
        reg=Path(root)/"library/studies"/study/"source_registry/Content_List.json"
        for e in json.loads(reg.read_text())["entries"]:
            entries[study,e["entry_id"]]=e
    titles=[core_title(entries[r["study_id"],r["entry_id"]]) for r in cases]
    q=_unit(retriever.encoder.encode(titles,is_query=True),len(titles))
    sim=q@retriever.tv.T
    rows=[]
    for i,c in enumerate(cases):
        entry=entries[c["study_id"],c["entry_id"]]
        b=retrieve_generic_baseline(entry,retriever.library)
        eligible=[(j,t) for j,t in enumerate(retriever.tids) if retriever.templates[t]["output_type"]==c["output_type"]]
        lex,_=_lexical(titles[i],retriever.library)
        mx=max([len(lex[t]) for j,t in eligible]+[1])
        dense=sorted(eligible,key=lambda x:(-sim[i,x[0]],x[1]))
        hybrid=sorted(eligible,key=lambda x:(-(.45*len(lex[x[1]])/mx+.55*max(0,float(sim[i,x[0]]))),x[1]))
        case={k:c[k] for k in ("study_id","entry_id","output_id","output_type","title","expected","outcome")}
        rows.append(row("title_rule",case,[x["template_id"] for x in b["candidates"]],b["template_id"],b["preset_id"]))
        for name,ranking in (("title_dense_forced",dense),("title_keyword_dense_forced",hybrid)):
            ids=[t for _,t in ranking]
            rows.append(row(name,case,ids,ids[0] if ids else None))
    return base,cases,rows


def paired_case(case,result):
    """Same saved Phase 4 inputs for all four methods. Rank and abstention separate."""
    b=result["baseline"]
    ar=result["ablation_rankings"]
    viable=[c["template_id"] for c in result["candidates"] if not c["structural_conflict"]]
    out=[row("title_rule",case,[c["template_id"] for c in b["candidates"]],b["template_id"],b["preset_id"])]
    for name,key in (("title_dense_forced","title_dense"),("sap_keyword_dense_forced","keyword_dense_no_structure")):
        ranking=ar[key]
        out.append(row(name,case,ranking,ranking[0] if ranking else None))
    out.append(row("sap_aware",case,viable,result["template_id"],result["preset_id"]))
    return out


def load_paired(phase4_dir, labels):
    """Require explicit label and SAP identity match; missing labels never count as correct."""
    p=Path(phase4_dir)
    summary=json.loads((p/"Summary.json").read_text())
    results=json.loads((p/"Template_Retrieval.json").read_text())
    byid={r["identity"]["tfl_id"]:r for r in results}
    rows=[]
    for c in labels:
        if c["sap_sha256"]!=summary["sap_sha256"]:
            raise ValueError("Label/SAP hash mismatch")
        r=byid[c["output_id"]]
        if c["title"]!=r["identity"]["title"] or c["output_type"]!=r["identity"]["output_type"]:
            raise ValueError("Label/target identity mismatch")
        rows.extend(paired_case(c,r))
    return rows


def run_phase5(repo_root,out_dir,*,encoder=None,paired_dir=None,paired_labels=None):
    root,out=Path(repo_root),Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    lib=load_generic_library(root/"generic_template_library")
    enc=encoder if encoder is not None else LocalEncoder()
    retriever=SAPAwareRetriever(lib,enc)
    base,cases,rows=title_benchmark(root,retriever)
    challenge=[c for c in cases if c["outcome"]!="correct"]
    registry=[]
    for c in challenge:
        pdfs=sorted((root/"library/studies"/c["study_id"]/"original").glob("*.pdf"))
        registry.append({**c,"available_pdf_paths":"|".join(str(p.relative_to(root)) for p in pdfs),
                         "sap_body_first":"","sap_body_last":"","approved_for_api":False,
                         "status":"requires_body_range_and_mapping_verification"})
    _write_csv(out/"Challenge_Manifest.csv",registry,list(registry[0]) if registry else ["study_id"])
    _write_csv(out/"Title_Benchmark.csv",rows,list(rows[0]))
    paired=load_paired(paired_dir,paired_labels) if paired_dir is not None and paired_labels else []
    if paired: _write_csv(out/"Paired_SAP_Diagnostic.csv",paired,list(paired[0]))
    summary={"library":lib.summary(),"baseline_reproduction":base,
             "title_benchmark":aggregate(rows),
             "title_challenge_subset":aggregate([r for r in rows if r["outcome"]!="correct"]),
             "challenge_cases":len(challenge),"challenge_sap_evaluated":0,
             "paired_demo":aggregate(paired),"paired_demo_label_status":"provisional reviewer expectations, not independent gold standard" if paired else "not evaluated",
             "unseen_study":{"status":"not evaluated","n":0},
             "llm_calls":0,"limitations":["Title benchmark uses the same studies that built the library.",
                 "Forced dense methods always return a candidate when one exists; compare rank metrics separately from abstention.",
                 "Challenge subset selected by baseline failures, not a representative sample.",
                 "Original PDFs require verified SAP-body ranges; shell pages must not be indexed.",
                 "No preset accuracy or requirement recall without independent labels."]}
    _write_json(out/"Summary.json",summary)
    return summary,rows,registry
