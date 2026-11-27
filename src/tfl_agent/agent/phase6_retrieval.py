"""Phase 6.2: exhaustive SAP body retrieval, soft scope only."""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path
from tfl_agent.agent.phase6_common import cases,study_artifacts,verify_identity,write_json,write_csv,read_csv,sha
from tfl_agent.tools.sap_hybrid import Chunk,Span,HybridSAPIndex,LocalEncoder,query_plan
from tfl_agent.tools.sap_scope import target_topic
from tfl_agent.agent.scoped_specification import literal_support

def topic_for(title):
    # Correct singular/plural miss, but never require a topic match.
    if re.search(r"\bprotocol deviations?\b",title,re.I): return "protocol_deviations"
    return target_topic(title)

def expanded_query_plan(target):
    """Title-conditioned extensions; hints are search terms, never extracted facts."""
    title=target["title"]
    plans=query_plan(target)
    extras=[]
    rules=[
        (r"\b(?:deviations?|disposition|analysis sets?|analysis populations?)\b","criteria_status","status criteria reasons severity categories analysis membership summarized"),
        (r"\b(?:response|recist|mrecist|efficacy|survival|progression)\b","endpoint_definition","endpoint definition response categories assessment timepoint estimation censoring"),
        (r"\b(?:visit|timepoint|baseline|ecog|laboratory|haematology|hematology|biochemistry|ecg|qtc)\b","longitudinal_display","assessment schedule visit baseline postbaseline change shift grade measurement parameter"),
        (r"\b(?:exposure|dose|medication|compliance|treatment duration)\b","exposure_definition","exposure duration cumulative dose dose intensity compliance interruptions"),
        (r"\b(?:immunogenicity|antibodies|ada|neutralizing)\b","assay_definition","anti drug antibodies baseline treatment induced treatment boosted assay status"),
        (r"\b(?:adverse events?|teaes?|safety)\b","safety_display","overview predefined categories serious severity relationship incidence system organ class preferred term"),
    ]
    for pattern,facet,hint in rules:
        if re.search(pattern,title,re.I):
            extras.append({"facet":facet,"query":title+" "+hint})
    return plans+extras

def relation(topic,c):
    if topic and c["topic_scope"]==topic: return "same_topic"
    if topic and c["topic_scope"] and c["topic_scope"]!=topic: return "different_topic"
    if c["study_scope"]: return "study_context"
    return "unknown"

def soft_rank(hits,byid,topic,rrf_k=60):
    # Scope is a small bounded bonus/penalty on RRF scale. No deletion.
    # Unknown is neutral. Different-topic evidence stays visible but lower-ranked.
    out=[]
    for h in hits:
        rel=relation(topic,byid[h["chunk_id"]])
        delta={"same_topic":.15,"different_topic":-.10,"study_context":0.,"unknown":0.}[rel]/(rrf_k+1)
        out.append({**h,"rrf_score":h["score"],"scope_relation":rel,"scope_adjustment":delta,"soft_score":h["score"]+delta})
    out.sort(key=lambda h:(-h["soft_score"],h["rank"],h["chunk_id"]))
    return [{**h,"rank":i} for i,h in enumerate(out,1)]

def legacy_order(part):
    # Reconstruct the historical initial target evidence order via round-robin across facets,
    # using exactly the same aggregation policy as the new arms.
    return round_robin([q["methods"]["hybrid"] for q in part["results"]])

def round_robin(rankings):
    seen=set();out=[]
    for i in range(max((len(x) for x in rankings),default=0)):
        for hits in rankings:
            if i<len(hits):
                cid=hits[i]["chunk_id"]
                if cid not in seen:
                    seen.add(cid);out.append(cid)
    return out

def validated_claim_refs(spec,store):
    out=[]
    for group in ("claims","review_claims"):
        for c in spec[group]:
            flags=c["checks"]["scope_flags"]
            if not c["checks"]["exact_quote"] or not c["checks"]["literal_support"]: continue
            if not literal_support(c["value"],c["exact_quote"]) or store.locate(c["chunk_id"],c["exact_quote"])!=c["source_spans"]: raise ValueError("Cached claim provenance mismatch")
            out.append({"chunk_id":c["chunk_id"],"field":c["field"],"value":c["value"],"exact_quote":c["exact_quote"],"historical_status":c["status"],"scope_flags":"|".join(flags),"scope_only_review":group=="review_claims" and set(flags)=={"target_scope_not_established"}})
    return out

def run_retrieval(root,out,encoder=None,top_k=5,budget=15):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    enc=encoder or LocalEncoder()
    manifest=cases(root); allrows=[]; packages=[]; review=[]; diagnostics=[]; seeds=[]; claimrows=[]
    for study in sorted({c["study_id"] for c in manifest}):
        store,raw,parts,specs,summary=study_artifacts(root,study)
        byid=store.chunks
        chunks=[Chunk(c["chunk_id"],c["section"],tuple(c["pages"]),c["text"],tuple(Span(**s) for s in c["spans"])) for c in raw]
        index=HybridSAPIndex(chunks,enc)
        for case in [c for c in manifest if c["study_id"]==study]:
            entry=case["entry_id"]; part=parts[entry]; spec=specs[entry]
            ident=verify_identity(case,part,spec)
            topic=topic_for(ident["title"])
            plans=query_plan(ident)
            expanded=expanded_query_plan(ident)
            # Same query set in the first three arms; isolate expansion in a fourth arm.
            expanded_full=index.search(expanded,top_k=len(chunks),depth=len(chunks),rrf_k=60)
            full=expanded_full[:len(plans)]
            arms={"legacy_scoped":legacy_order(part),"full_hybrid":round_robin([q["methods"]["hybrid"][:top_k] for q in full]),"soft_scope":round_robin([soft_rank(q["methods"]["hybrid"],byid,topic)[:top_k] for q in full]),"soft_scope_expanded":round_robin([soft_rank(q["methods"]["hybrid"],byid,topic)[:top_k] for q in expanded_full])}
            # Fixed target budget; short lists are not padded.
            arms={k:v[:budget] for k,v in arms.items()}
            base={"study_id":study,"entry_id":entry,"title":ident["title"],"output_type":ident["output_type"]}
            for name,ids in arms.items():
                for rank,cid in enumerate(ids,1):
                    c=byid[cid]
                    allrows.append({**base,"method":name,"rank":rank,"chunk_id":cid,"scope_relation":relation(topic,c),"topic_scope":c["topic_scope"],"section":c["section"],"pages":"|".join(map(str,c["pages"]))})
            for cid in sorted(set().union(*map(set,arms.values()))):
                c=byid[cid];review.append({**base,"chunk_id":cid,"pages":"|".join(map(str,c["pages"])),"section":c["section"],"text":c["text"],"relevance":"","review_note":""})
            refs=validated_claim_refs(spec,store)
            for r in refs: claimrows.append({**base,**r})
            refids={r["chunk_id"] for r in refs}
            for name,ids in arms.items():
                diagnostics.append({**base,"method":name,"retrieved":len(ids),"available_chunks":len(chunks),"historical_claim_chunk_count":len(refids),"historical_claim_chunk_hits":len(refids&set(ids)),"historical_claim_overlap":len(refids&set(ids))/len(refids) if refids else None,"different_topic_chunks":sum(relation(topic,byid[i])=="different_topic" for i in ids)})
            # Previously inspected explicit SAP quotation: one diagnostic anchor, not a gold set.
            if study=="ARV-471-BC-201" and entry=="CL005":
                quote="All protocol deviations in each arm will be summarized by severity and categories."
                found=[i for i,c in byid.items() if quote in c["text"]]
                if not found: raise ValueError("Known diagnostic quote missing")
                for name,ids in arms.items(): seeds.append({**base,"method":name,"quote":quote,"matching_chunk_ids":"|".join(found),"rank":next((j for j,i in enumerate(ids,1) if i in found),None)})
            # Per-facet ranking audit, including RRF and scope effect.
            q_audit=[]
            for q in expanded_full:
                q_audit.append({"facet":q["facet"],"query":q["query"],"bm25":q["methods"]["bm25"][:top_k],"dense":q["methods"]["dense"][:top_k],"hybrid":q["methods"]["hybrid"][:top_k],"soft_scope":soft_rank(q["methods"]["hybrid"],byid,topic)[:top_k]})
            packages.append({"study_id":study,"target":ident,"sap_sha256":summary["sap_sha256"],"topic":topic,"candidate_ids":arms,"query_audit":q_audit,"legacy_initial_evidence":part["target_evidence"],"new_evidence":[byid[i] for i in arms["soft_scope"]],"expanded_evidence":[byid[i] for i in arms["soft_scope_expanded"]],"generation_authorized":False})
    write_json(out/"Evidence_Packages.json",packages)
    write_csv(out/"Candidate_Rankings.csv",allrows)
    write_csv(out/"Evidence_Review_Blinded.csv",review)
    write_csv(out/"Historical_Claim_Diagnostics.csv",claimrows)
    write_csv(out/"Retrieval_Diagnostics.csv",diagnostics)
    write_csv(out/"Known_Anchor_Check.csv",seeds)
    s={"cases":len(manifest),"historical_completed_phase3_calls":44,"new_llm_calls":0,"encoder":getattr(enc,"model_name",type(enc).__name__),"per_facet_top_k":top_k,"target_budget":budget,"ranking_depth":"all cached body chunks","review_rows":len(review),"known_anchor":seeds,"independent_evidence_labels":0,"evaluation_status":"Candidate diagnostics only; historical claim overlap and one known anchor are not independent Recall/Precision. Review pooled candidates before claiming evidence accuracy."}
    write_json(out/"Summary.json",s)
    return s

def evaluate_review(rank_path,review_path,out):
    """Pooled adjudication: relevance 1/0 for every pooled chunk; never infer unjudged=0."""
    ranks=read_csv(rank_path); review=read_csv(review_path)
    def k(r): return r["study_id"],r["entry_id"],r["chunk_id"]
    labels={}
    for r in review:
        if k(r) in labels: raise ValueError("Duplicate review row")
        if r["relevance"] not in ("0","1"): raise ValueError("Complete all pooled relevance labels (0/1)")
        labels[k(r)]=int(r["relevance"])
    if set(labels)!={k(r) for r in ranks}: raise ValueError("Review pool mismatch")
    groups=defaultdict(list); total=defaultdict(int)
    for kk,v in labels.items(): total[kk[:2]]+=v
    for r in ranks: groups[(r["study_id"],r["entry_id"],r["method"])].append(r)
    outrows=[]
    caseset={kk[:2] for kk in labels}
    for study,entry in sorted(caseset):
        for method in ("legacy_scoped","full_hybrid","soft_scope","soft_scope_expanded"):
            rs=groups[study,entry,method]; relevant=[int(r["rank"]) for r in rs if labels[k(r)]]
            n=total[study,entry]
            outrows.append(dict(study_id=study,entry_id=entry,method=method,retrieved=len(rs),pooled_relevant=n,precision=len(relevant)/len(rs) if rs else None,pooled_recall=len(relevant)/n if n else None,mrr=(1/min(relevant) if relevant else 0) if n else None))
    write_csv(out,outrows)
    return outrows
