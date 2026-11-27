"""Offline replay of Phase 5.2 candidate artifacts. No encoder or LLM.
Experimental policies are provisional; gold labels are only used for evaluation.
"""
from __future__ import annotations
import csv, json, math, hashlib, tempfile, zipfile
from pathlib import Path, PurePosixPath
from collections import defaultdict

METHODS=("title_rule","title_dense_forced","title_keyword_dense_forced","sap_keyword_dense_forced","sap_aware")
POLICIES=("title_anchor","soft_structure","guarded_selection","combined")
BLOCKING={"no_structurally_compatible_candidate","weak_match","small_template_margin","no_accepted_sap_evidence","no_lexical_or_structural_support","title_output_type_conflict","possible_nonstandard_output"}
RECOMPUTE={"weak_match","small_template_margin","no_structurally_compatible_candidate","no_lexical_or_structural_support","negative_title_cues_review","no_preset","small_preset_margin","preset_requires_topic_review"}

def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def read_csv(p):
    with Path(p).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))
def write_csv(p,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ids(s):
    return [v for v in (s or "").split("|") if v]
def key(r):
    return r["study_id"],r["entry_id"]
def boolean(v):
    if str(v).lower() not in ("true","false"):
        raise ValueError("Invalid boolean: "+str(v))
    return str(v).lower()=="true"
def clip(v):
    return max(0.,min(1.,float(v)))

def policy(result,mode):
    cs=result["candidates"]
    anchor=mode in ("title_anchor","combined")
    soft=mode in ("soft_structure","combined")
    guard=mode in ("guarded_selection","combined")
    if not cs:
        return dict(ranked=[],selected=None,preset=None,flags=["no_candidates"],scores=[])
    if len({c["template_id"] for c in cs})!=len(cs):
        raise ValueError("Duplicate candidate")
    mx=max(1,max(len(c["title_terms"]) for c in cs))
    title={c["template_id"]:.45*len(c["title_terms"])/mx+.55*clip(c["title_dense_cosine"]) for c in cs}
    tr=sorted(title,key=lambda t:(-title[t],t))
    gap=title[tr[0]]-title[tr[1]] if len(tr)>1 else 0.
    scored=[]
    for c in cs:
        base=float(c["score"])
        if not math.isfinite(base):
            raise ValueError("Non-finite score")
        s=.65*base+.35*title[c["template_id"]] if anchor else base
        if soft and c["structural_conflict"]:
            s-=.20
        scored.append(dict(template_id=c["template_id"],score=s,cached_score=base,title_score=title[c["template_id"]],structural_conflict=c["structural_conflict"]))
    scored.sort(key=lambda c:(False if soft else c["structural_conflict"],-c["score"],c["template_id"]))
    ranked=[c for c in scored if soft or not c["structural_conflict"]]
    flags=[f for f in result.get("flags",[]) if f not in RECOMPUTE]
    top=ranked[0] if ranked else None
    if top is None:
        flags.append("no_structurally_compatible_candidate")
    else:
        c=next(x for x in cs if x["template_id"]==top["template_id"])
        margin=top["score"]-ranked[1]["score"] if len(ranked)>1 else None
        if top["score"]<.35: flags.append("weak_match")
        if margin is not None and margin<.04: flags.append("small_template_margin")
        if not c["matched_terms"] and not c["structural_checks"]: flags.append("no_lexical_or_structural_support")
        if c["negative_title_cues"]: flags.append("negative_title_cues_review")
        if not c["preset_candidates"]: flags.append("no_preset")
        if c["structural_conflict"]: flags.append("top_has_structural_conflict")
        if guard and "small_template_margin" in flags and c["template_id"]==tr[0]==result["baseline"].get("template_id") and gap>=.08 and title[tr[0]]>=.55 and not c["negative_title_cues"]:
            flags.remove("small_template_margin")
            flags.append("margin_waived_title_rule_agreement")
    selected=preset=None
    if top and not (set(flags)&(BLOCKING|{"top_has_structural_conflict"})):
        selected=top["template_id"]
        p=c["preset_candidates"]
        preset=c["preset_id"]
        if len(p)>1 and p[0]["score"]-p[1]["score"]<.04:
            flags.append("small_preset_margin"); preset=None
        if preset and p and not p[0]["matched_terms"] and not p[0]["variable_overlap"]:
            flags.append("preset_requires_topic_review")
    return dict(ranked=[c["template_id"] for c in ranked],selected=selected,preset=preset,flags=flags,scores=scored)

def evaluate(case,method,ranking,selected,preset=None):
    labels=set(ids(case["expected"]))
    rank=next((i for i,t in enumerate(ranking,1) if t in labels),0)
    return dict(case,method=method,ranking="|".join(ranking),selected=selected or "",selected_preset=preset or "",rank=rank,correct=(not selected if labels=={"NONSTANDARD"} else selected in labels))

def metrics(rows):
    standard=[r for r in rows if r["expected"]!="NONSTANDARD"]
    selected=[r for r in rows if r["selected"]]
    non=[r for r in rows if r["expected"]=="NONSTANDARD"]
    div=lambda a,b:a/b if b else None
    return dict(n=len(rows),correct=sum(r["correct"] for r in rows),selection_accuracy=div(sum(r["correct"] for r in rows),len(rows)),coverage=div(len(selected),len(rows)),selective_accuracy=div(sum(r["correct"] for r in selected),len(selected)),standard_n=len(standard),rank_top1=div(sum(r["rank"]==1 for r in standard),len(standard)),recall_at_3=div(sum(0<r["rank"]<=3 for r in standard),len(standard)),mrr=div(sum(1/r["rank"] for r in standard if r["rank"]),len(standard)),nonstandard_n=len(non),nonstandard_abstention=div(sum(not r["selected"] for r in non),len(non)))

def run(source,out,expected_n=19,expected_calls=44):
    source,out=Path(source),Path(out)
    if out.exists(): raise FileExistsError(out)
    if not zipfile.is_zipfile(source): raise ValueError("Expected a Phase 5.2 ZIP")
    with tempfile.TemporaryDirectory(prefix="phase521-") as tmp:
        with zipfile.ZipFile(source) as z:
            for m in z.infolist():
                p=PurePosixPath(m.filename)
                if p.is_absolute() or ".." in p.parts or "\\" in m.filename:
                    raise ValueError("Unsafe archive path")
            z.extractall(tmp)
        roots=[p.parent for p in Path(tmp).rglob("Paired_Results.csv") if (p.parent/"Studies").is_dir() and (p.parent/"Summary.json").is_file()]
        if len(roots)!=1: raise ValueError("Expected one Phase 5.2 output root")
        return replay(roots[0],source,out,expected_n,expected_calls)

def replay(root,source,out,expected_n,expected_calls):
    summary=read(root/"Summary.json")
    grouped=defaultdict(dict)
    for r in read_csv(root/"Paired_Results.csv"):
        if r["method"] in grouped[key(r)]: raise ValueError("Duplicate method")
        grouped[key(r)][r["method"]]=r
    if len(grouped)!=expected_n or summary["completed"]!=expected_n or summary["completed_phase3_llm_calls"]!=expected_calls:
        raise ValueError(f"Wrong archive: {len(grouped)} paired cases, {summary.get('completed')} completed, {summary.get('completed_phase3_llm_calls')} historical calls")
    completed={key(r):r for r in read(root/"Case_Status.json") if r["status"]=="completed"}
    if set(completed)!=set(grouped): raise ValueError("Case status mismatch")
    conflicts={k for k,r in completed.items() if r["detail"]=="type_conflict_in_registry"}
    hashes={str(p.relative_to(root)):sha(p) for p in (root/"Summary.json",root/"Paired_Results.csv",root/"Case_Status.json")}
    rows=[]; changes=[]; scores=[]; checks=[]; cache={}
    for k,methods in sorted(grouped.items()):
        if set(methods)!=set(METHODS): raise ValueError("Missing baseline methods")
        orig=methods["sap_aware"]; study,entry=k
        if study not in cache:
            sd=root/"Studies"/study
            p=sd/"Phase4"/"Template_Retrieval.json"
            ps=sd/"Phase4"/"Summary.json"
            phase3=sd/"Summary.json"
            for f in (p,ps,phase3,sd/"Phase4"/"Normalized_Requirements.json"):
                hashes[str(f.relative_to(root))]=sha(f)
            if read(ps)["sap_sha256"]!=read(phase3)["sap_sha256"]: raise ValueError("SAP hash mismatch")
            data=read(p); rr={r["identity"]["tfl_id"]:r for r in data}
            if len(rr)!=len(data): raise ValueError("Duplicate cached target")
            cache[study]=rr
        r=cache[study][entry]; ident=r["identity"]
        if ident["title"]!=orig["title"] or ident["output_type"]!=orig["output_type"]: raise ValueError("Target identity mismatch")
        viable=[c["template_id"] for c in r["candidates"] if not c["structural_conflict"]]
        if viable!=ids(orig["ranking"]) or (r["template_id"] or "")!=orig["selected"] or (r["preset_id"] or "")!=orig["selected_preset"]:
            raise ValueError("Baseline replay mismatch: "+str(k))
        checks.append(dict(study_id=study,entry_id=entry,match=True))
        # Candidate decisions are made without expected labels.
        variants={m:policy(r,m) for m in POLICIES}
        case={f:orig[f] for f in ("study_id","entry_id","output_id","output_type","title","expected","outcome","stratum")}
        case["type_conflict"]=k in conflicts
        for name,o in methods.items():
            if any(o[f]!=orig[f] for f in ("title","output_type","expected","stratum")):
                raise ValueError("Paired case mismatch")
            row=evaluate(case,name,ids(o["ranking"]),o["selected"],o["selected_preset"])
            if row["correct"]!=boolean(o["correct"]) or row["rank"]!=int(o["rank"] or 0): raise ValueError("Baseline metric mismatch")
            rows.append(row)
        for name,d in variants.items():
            row=evaluate(case,name,d["ranked"],d["selected"],d["preset"]); rows.append(row)
            changes.append(dict(study_id=study,entry_id=entry,policy=name,baseline_selected=orig["selected"],optimized_selected=d["selected"] or "",baseline_rank=int(orig["rank"] or 0),optimized_rank=row["rank"],baseline_correct=boolean(orig["correct"]),optimized_correct=row["correct"],flags="|".join(d["flags"]),type_conflict=k in conflicts))
            scores.extend(dict(study_id=study,entry_id=entry,policy=name,**s) for s in d["scores"])
    def agg(rs):
        return {m:metrics([r for r in rs if r["method"]==m]) for m in (*METHODS,*POLICIES)}
    by={"all":agg(rows),"type_consistent":agg([r for r in rows if not r["type_conflict"]]),"type_conflict":agg([r for r in rows if r["type_conflict"]])}
    by["by_stratum"]={s:agg([r for r in rows if r["stratum"]==s]) for s in sorted({r["stratum"] for r in rows})}
    report=dict(status="offline_development_diagnostic",cases=len(grouped),type_consistent=len(grouped)-len(conflicts),type_conflict=len(conflicts),historical_completed_phase3_calls=expected_calls,new_llm_calls=0,new_embedding_calls=0,baseline_verified=len(checks),source_archive_sha256=sha(source),source_files_sha256=hashes,metrics=by,generation_authorized=False,limitations=["Provisional policies; previous decisions not independently recovered.","Same development cohort, not a holdout.","Soft structure ranks contradictory candidates for diagnostic review; never auto-selects them.","No clinical or preset correctness claim.","Historical completed calls exclude unrecorded retries."])
    out.mkdir(parents=True,exist_ok=False)
    for name,rs in (("Paired_Replay_Results.csv",rows),("Case_Changes.csv",changes),("Candidate_Scores.csv",scores),("Baseline_Checks.csv",checks)):
        write_csv(out/name,rs)
    (out/"Summary.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report
